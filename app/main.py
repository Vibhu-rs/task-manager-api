from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import HTTPBearer

from pydantic import BaseModel
from app.database import get_connection, init_db
from app.security import hash_password, verify_password, create_token, get_user_id_from_token

app = FastAPI(title="Task Manager API")

init_db()

# This tells FastAPI: "protected routes expect a Bearer token".
# It also makes the Authorize button appear in /docs.
bearer = HTTPBearer(auto_error=False)


def get_user_id(credentials=Depends(bearer)):
    if credentials is None:
        raise HTTPException(status_code=401, detail="Please log in first")

    token = credentials.credentials      # just the token part, without the word "Bearer"
    user_id = get_user_id_from_token(token)

    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid token")

    return user_id

def find_task(conn, task_id, user_id):
    # Look for a task with this id AND this owner
    task = conn.execute(
        "SELECT * FROM tasks WHERE id = ? AND user_id = ?", (task_id, user_id)
    ).fetchone()

    if task is None:
        conn.close()
        raise HTTPException(status_code=404, detail="Task not found")

    return task

# Think of this as a C struct: the fields a register request must contain
class RegisterData(BaseModel):
    name: str
    email: str
    password: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/register", status_code=201)
def register(data: RegisterData):
    if len(data.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    conn = get_connection()
    user = conn.execute("SELECT id FROM users WHERE email = ?", (data.email,)).fetchone()
    if user:
        conn.close()
        raise HTTPException(status_code=409, detail="Email already used")

    conn.execute(
        "INSERT INTO users (name, email, password) VALUES (?, ?, ?)",
        (data.name, data.email, hash_password(data.password)),
    )
    conn.commit()
    conn.close()
    return {"message": "User created"}

class LoginData(BaseModel):
    email: str
    password: str

@app.post("/login")
def login(data: LoginData):
    conn = get_connection()
    user = conn.execute("SELECT * FROM users WHERE email = ?", (data.email,)).fetchone()
    conn.close()

    # Same message for "no such email" and "wrong password"
    if user is None or not verify_password(data.password, user["password"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    return {"token": create_token(user["id"])}

@app.get("/me")
def me(user_id=Depends(get_user_id)):
    conn = get_connection()
    user = conn.execute("SELECT id, name, email FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()

    return {"id": user["id"], "name": user["name"], "email": user["email"]}

class TaskData(BaseModel):
    title: str
    description: str = ""        # a default value, so this field is optional
    status: str = "todo"
    priority: str = "medium"
    due_date: str | None = None        # optional, written like 2026-11-01

class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: str | None = None
    priority: str | None = None
    due_date: str | None = None

@app.post("/tasks", status_code=201)
def create_task(data: TaskData, user_id=Depends(get_user_id)):
    # Check the values are allowed
    if data.title.strip() == "":
        raise HTTPException(status_code=400, detail="Title cannot be empty")
    if data.status not in ["todo", "in_progress", "done"]:
        raise HTTPException(status_code=400, detail="Status must be todo, in_progress or done")
    if data.priority not in ["low", "medium", "high"]:
        raise HTTPException(status_code=400, detail="Priority must be low, medium or high")

    conn = get_connection()
    cursor = conn.execute(
        "INSERT INTO tasks (user_id, title, description, status, priority, due_date) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, data.title.strip(), data.description, data.status, data.priority, data.due_date),
    )
    conn.commit()
    task_id = cursor.lastrowid

    # Read the saved task back so we can return it
    task = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    conn.close()

    return dict(task)

@app.get("/tasks/{task_id}")
def get_task(task_id: int, user_id=Depends(get_user_id)):
    conn = get_connection()
    task = find_task(conn, task_id, user_id)
    conn.close()
    return dict(task)

@app.delete("/tasks/{task_id}")
def delete_task(task_id: int, user_id=Depends(get_user_id)):
    conn = get_connection()
    find_task(conn, task_id, user_id)      # stops with 404 if it isn't theirs

    conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()
    return {"message": "Task deleted"}

@app.put("/tasks/{task_id}")
def update_task(task_id: int, data: TaskUpdate, user_id=Depends(get_user_id)):
    # Check the values that were sent (None means "not sent", so skip it)
    if data.title is not None and data.title.strip() == "":
        raise HTTPException(status_code=400, detail="Title cannot be empty")
    if data.status is not None and data.status not in ["todo", "in_progress", "done"]:
        raise HTTPException(status_code=400, detail="Status must be todo, in_progress or done")
    if data.priority is not None and data.priority not in ["low", "medium", "high"]:
        raise HTTPException(status_code=400, detail="Priority must be low, medium or high")

    conn = get_connection()
    task = find_task(conn, task_id, user_id)

    # Start with the old values, and replace only the ones that were sent
    title = task["title"]
    description = task["description"]
    status = task["status"]
    priority = task["priority"]
    due_date = task["due_date"]

    if data.title is not None:
        title = data.title.strip()
    if data.description is not None:
        description = data.description
    if data.status is not None:
        status = data.status
    if data.priority is not None:
        priority = data.priority
    if data.due_date is not None:
        due_date = data.due_date

    conn.execute(
        "UPDATE tasks SET title = ?, description = ?, status = ?, priority = ?, "
        "due_date = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (title, description, status, priority, due_date, task_id),
    )
    conn.commit()

    updated = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    conn.close()
    return dict(updated)