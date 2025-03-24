from fastapi import FastAPI
from llm_play import LLM_Agent
from fastapi.middleware.cors import CORSMiddleware
agent = LLM_Agent()

app = FastAPI(
    root_path="/"
)
origins = [
    "*"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



@app.post("/chat")
def chat(user_input: dict):
    chat_result = agent.main_process(user_input["user_input"])
    print(chat_result)
    return {"message": chat_result}