import textworld.gym
from textworld import gym
from textworld import EnvInfos
import ast
from openai import OpenAI

client = OpenAI(api_key="key here")

# Specify your game file
game_file = "village_game.z8"
# Request admissible_commands and facts information
infos = EnvInfos(admissible_commands=True, facts=True, inventory=True)
env_id = textworld.gym.register_games([game_file], request_infos=infos, max_episode_steps=None)
print("Registered environment id:", env_id)
env = gym.make(env_id)

obs, infos = env.reset()
done = False

# TODO: This while loop should be modified to use an LLM agent instead of human input
# The game contains NPCs (non-player characters) like:
# - Sheriff (indicated by type 'c' in textWorldMap.py)
# These containers/NPCs can hold items and interact with the player
# 
def make_action(obs, infos, plain_text_explanation):
    prompt_template = f"""
    You are a textwold command generator.
    another LLM will provide you the command explanation.
    You need to generate the step by step command to finish the task.
    Player are now in the following location:
    {obs.split("-= ")[1].split(" =-")[0] if "-= " in obs and " =-" in obs else ""}
    Inventory:
    {infos.get("inventory", [])}
    A village map with 9 rooms in a 3x3 grid layout:
    Top row:
    - Shop (contains Vendor)
    - Village Committee 
    - Hospital

    Middle row:
    - School
    - Park (contains Well)
    - Sheriff's Office (contains Sheriff)

    Bottom row:
    - House 1
    - House 2
    - Forest (contains Drunker)

    Available items and their locations:
    {infos.get("facts", [])}
    
    You can check if an item is in a container/NPC by looking for facts like:
    'in(item_name: type, container_name: type)'
    For example:
    - 'in(rope: o, Vendor: c)' means Vendor has a rope
    - 'in(knife: o, Well: c)' means Well contains a knife
    
    Item types:
    - o: objects (rope, knife)
    - k: key items (wine, money) 
    - c: containers/NPCs (Vendor, Sheriff, Well, Drunker)

    Rooms are connected horizontally and vertically to adjacent rooms.
    Your output should be a list of commands, each command is a string.
    for example:
    if user want to go to the shop, and current location is the house 1, you should return:
    ["go north", "go north"]
    if user want to go to the shop, and current location is the house 2, you should return:
    ["go west", "go north", "go north"]
    You can only do one action at a time.
    so, if current location is the house 1 and want to go to the shop, you can only return ["go north", "go north"] not just ["go north"]
    you can only return the command list, no other text.
    """

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": prompt_template},
                  {"role": "user", "content": f"Here is the command explanation: {plain_text_explanation}"}],
        max_tokens=1000,
        temperature=0.0,
    )
    list_of_commands = ast.literal_eval(response.choices[0].message.content)
    for command in list_of_commands:
        print(f"\nExecuting command: {command}")
        print(obs)
        obs, reward, done, infos = env.step(command)
        print(obs)
        if done:
            return obs, reward, done, infos
    return obs, reward, done, infos
    
#  test the make_action function
make_action(obs, infos, "go to the Forest")
# print(infos.get("location", []))

# while not done:
#     # Display current observation and available actions
#     print("Current observation:")
#     print(obs)
#     print(infos.get("location", []))
    
#     # Get current game facts list
#     facts = infos.get("facts", [])
#     print("\nCurrent facts:")
#     for fact in facts:
#         if "in(knife: o, Sheriff: c)" in str(fact):
#             print("knife given to sheriff, game over")
#             done = True
    

#     if done:
#         break
#     # Display available actions and wait for player input
#     print("\nAvailable actions:")
#     print(infos.get("admissible_commands", []))
#     action = input("Please enter your action: ").strip()
    
#     obs, reward, done, infos = env.step(action)

# print("Game Over!")