from pydantic import BaseModel

class UserInfo(BaseModel):
    user_name: str
    team_name: str


