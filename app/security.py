import os
import bcrypt
import jwt


def hash_password(password):
    # bcrypt works on bytes, so turn the text into bytes first
    password_bytes = password.encode()
    salt = bcrypt.gensalt()                  # a random value added so equal passwords get different hashes
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode()                   # turn bytes back into text so it can go in the database


def verify_password(password, hashed):
    # True if the typed password matches the stored hash, otherwise False
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_token(user_id):
    # A token is a signed note that says "this is user X"
    data = {"user_id": user_id}
    secret = os.getenv("JWT_SECRET")         # the secret from your .env file
    return jwt.encode(data, secret, algorithm="HS256")

def get_user_id_from_token(token):
    # Reverse of create_token: open the signed note and read the user id
    try:
        data = jwt.decode(token, os.getenv("JWT_SECRET"), algorithms=["HS256"])
        return data["user_id"]
    except Exception:
        return None      # token was fake, damaged or signed with a different secret