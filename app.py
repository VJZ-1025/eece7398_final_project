from contextlib import asynccontextmanager
from fastapi import FastAPI
from llm_play import LLM_Agent
from fastapi.middleware.cors import CORSMiddleware

agent = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize LLM agent before serving
    global agent
    agent = LLM_Agent()
    yield
    # Clean up resources if needed
    pass

app = FastAPI(
    root_path="/",
    lifespan=lifespan
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
    print(user_input)
    chat_result = agent.main_process(user_input["user_input"])
    location = agent.get_current_location()
    win = agent.check_win()
    return {"message": chat_result, "location": location, "win": win}

@app.get("/check_inventory")
def check_inventory():
    return {"inventory": agent.get_current_inventory()}

@app.get("/check_location")
def check_location():
    return {"location": agent.get_current_location()}

@app.get("/check_obs")
def check_obs():
    return {"obs": agent.get_current_obs()}