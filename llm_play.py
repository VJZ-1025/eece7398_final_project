import textworld.gym
from textworld import gym
from textworld import EnvInfos
import json
from openai import OpenAI
import os
from dotenv import load_dotenv
load_dotenv()
API_KEY = os.getenv("API_KEY")

client = OpenAI(api_key=API_KEY)

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
    current_location = obs.split("-= ")[1].split(" =-")[0] if "-= " in obs and " =-" in obs else ""
    prompt_template = prompt_template = f"""
        <question>
        A player is navigating a TextWorld Microsoft research game and needs to execute a step-by-step sequence of commands to reach the desired destination or complete a task. The map is 3x3 grid layout, each command only has one action, which means a action can only move the player one grid per time.
        </question>
        <game rules>
        - The player can only take one action per time.
        - The player can only move one grid per time.
        - The player can only move to the adjacent grid.
        </game rules>

        <valid actions>
        - movement: go <dir> (dir: north, south, east, west)    
        - interaction: take <item>, open <container>, take <item> from <container>, unlock <container> with <key>
        </valid actions>

        <special commands>
        ***NOTE: Special commands MUST be executed in the order as listed below***
        - buy <item>: This command is a shortcut that combines multiple actions:
            1. unlock vendor with money
            2. open vender
            3. take <item> from vendor
            4. insert money into vendor
            5. close vendor
            output: ['unlock vendor with money', 'open vendor', 'take <item> from vendor', 'insert money into vendor', 'close vendor']
            - check inventory has money, if not, reject the command, return ["reject command"]
            - check current location at shop, if not, go to shop first, then execute the command
        - down to well: This is is a shortcut that combines multiple actions:
            1. insert rope into well
            2. take knife from from well
            output: ['insert rope into well', 'take knife from well']
            - check inventory has rope, if not, reject the command, return ["reject command"]
            - check current location at well, if not, go to well first, then execute the command
        </special commands>

        <response requirements>
        Your response must follow a structured reasoning process with two distinct action types: **"Inner Thinking"**, **"Verifiy Thinking"**, and **"Instruction Summarization"**.

        1. **Inner Thinking**: Reconstruct the reasoning process step by step. Each step should have a brief title for clarity.
            - Grid Layout:
                - Shop is at the northwest corner. Its east is the Village Committee, and its south is the School.
                - Village Committee is at the north-central position. Its west is the Shop, its east is the Hospital, and its south is the Center Park.
                - Hospital is at the northeast corner. Its west is the Village Committee, and its south is the Sheriff's Office.
                - School is at the middle row, west side. Its north is the Shop, its east is the Center Park, and its south is House 1.
                - Center Park is at the center of the map. Its north is the Village Committee, its west is the School, its east is the Sheriff's Office, and its south is House 2.
                - Sheriff's Office is at the middle row, east side. Its north is the Hospital, its west is the Center Park, and its south is the Forest.
                - House 1 is at the southwest corner. Its north is the School, and its east is House 2.
                - House 2 is at the south-central position. Its north is the Center Park, its west is House 1, and its east is Forest.
                - Forest is at the southeast corner. Its north is the Sheriff's Office, and its west is House 2.
            
            - Container:
                - Vendor:
                    - Location: Shop
                - Well:
                    - Location: Center Park
                - Sheriff:
                    - Location: Sheriff's Office
                - Drunk:
                    - Location: Forest

            
            - Consider the player's current location: 
                {current_location}
            - Inventory: {infos.get("inventory", [])}
                
            - Identify the target and determine the optimal path.

            - Use logical reasoning to determine the **shortest path** to the target location while considering obstacles and key items.

            - Final output should shows the status of the command, which is "approved", "rejected", or "confused"
            - If the command is rejected, return status: "rejected" and content: ["reject command"]
            - If the command is confused, return status: "confused" and content: ["confused command"]
            - If the command is approved, return status: "approved" and content: ["...command 1", "...command 2"]

        2. **Verifiy Thinking**: If a mistake is found, correct it by backtracking.
        3. **Instruction Summarization**: Summarize key takeaways from the new reasoning process and provide actionable instructions.
            - Output should strictly be a JSON list of step-by-step commands.
            - Example format:
            {{
                "CoT": [
                    {{"action": "Inner Thinking", "title": "Identify current situation", "content": "..."}},
                    {{"action": "Inner Thinking", "title": "Identify the target", "content": "..."}},
                    {{"action": "Inner Thinking", "title": "Determine the optimal path and commands", "content": "..."}},
                    {{"action": "Inner Thinking", "title": "Make draft of the command", "content": "..."}},
                    {{"action": "Verifiy Thinking", "title": "Simulate the command check the result", "content": "..."}},
                    {{"action": "Instruction Summarization", "status": "approved|rejected|confused", "content": ["...command 1", "...command 2"]}}
                ]
            }}
            ***Do NOT include any extra text outside of the JSON format, do NOT modify the action and title, DO NOT modify the number of CoT***
            </response requirements>

            <example>
            Golden standard:
            - command explanation: Take the money and go to shop then buy rope
            - current location: House 1
                {{
                    "CoT": [
                        {{"action": "Inner Thinking", "title": "Identify current situation", "content": "The player is currently at House 1, which is in the bottom row, left column of the grid, the player inventory is empty."}},
                        {{"action": "Inner Thinking", "title": "Identify the target", "content": "The target is take the money then go to shop, and buy rope, because buy rope is a special command, so it should divde to unlock vendor with money, open vendor, take rope from vendor, insert money into vendor, close vendor."}},
                        {{"action": "Inner Thinking", "title": "Determine the optimal path and commands", "content": "Take money, then from house 1 to shop go north to school, then go north to shop, then unlock vendor with money, open vendor, take rope from vendor, insert money into vendor, close vendor."}},
                        {{"action": "Inner Thinking", "title": "Make draft of the command", "content": ['take money', 'go north', 'go north', 'unlock vendor with money', 'open vendor', 'take rope from vendor', 'insert money into vendor', 'close vendor']}},
                        {{"action": "Verifiy Thinking", "title": "Simulate the command check the result", "content": "The command is correct. 'go north' moves the player from House 1 to School, and 'go north' moves the player from School to shop, then unlock vendor with money, open vendor, take rope from vendor, insert money into vendor, close vendor."}},
                        {{"action": "Instruction Summarization", "status": "approved", "content": ["take money", "go north", "go north", "unlock vendor with money", "open vendor", "take rope from vendor", "insert money into vendor", "close vendor"]}}
                    ]
                }}
            </example>
        """
    response = client.chat.completions.create(
        model="o3-mini",
        messages=[{"role": "system", "content": prompt_template},
                  {"role": "user", "content": f"Here is the command explanation: {plain_text_explanation}"}],
    )
    print(response.choices[0].message.content)
    status = json.loads(response.choices[0].message.content)["CoT"][5]["status"]
    if status == "rejected":
        print("enh enh, you can't do that")
        obs, reward, done, infos = env.step("")
        return obs, reward, done, infos
    list_of_commands = json.loads(response.choices[0].message.content)["CoT"][5]["content"]
    if list_of_commands == ["reject command"]:
        print("nah nah, you can't do that")
        return obs, reward, done, infos
    for command in list_of_commands:
        # print(f"\nExecuting command: {command}")
        print(obs)
        obs, reward, done, infos = env.step(command)
        print(obs)
        if done:
            return obs, reward, done, infos
    return obs, reward, done, infos
    
#  test the make_action function
obs, reward, done, infos = make_action(obs, infos, "buy rope")
obs, reward, done, infos = make_action(obs, infos, "take the money buy rope")
obs, reward, done, infos = make_action(obs, infos, "down to well")
# obs, reward, done, infos = make_action(obs, infos, "Buy wine")
# obs, reward, done, infos = make_action(obs, infos, "go to the Forest")
# obs, reward, done, infos = make_action(obs, infos, "go to the Sheriff's Office")
# obs, reward, done, infos = make_action(obs, infos, "go to the Hospital")
# obs, reward, done, infos = make_action(obs, infos, "go to the Center Park")
# obs, reward, done, infos = make_action(obs, infos, "go to the Village Committee")
# obs, reward, done, infos = make_action(obs, infos, "go to the School")

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


# prompt_template = """<question>
# {}
# </question>
# <previous reasoning>
# {}
# </previous reasoning>
# <response requirements>
# Your response must follow a structured reasoning process with two distinct action types: **"Inner Thinking"**, and **"Instruction Summarization"**.
# 2. **Inner Thinking**: Reconstruct the reasoning process step by step. Each step should have a brief title for clarity.
# 3. **Instruction Summarization**: Summarize key takeaways from the new reasoning process and provide actionable instructions and reasons. Do not mention past mistakes.
# </response requirements>
# <question> contains the main query, while <previous reasoning> documents prior reasoning. Your task is to continue with the **Inner Thinking** step. I have manually reviewed the reasoning and determined that the Conclusion is incorrect. I will secretly provide the correct answer as "{}", but you must not reveal that you know it. Instead, refine the reasoning through **Inner Thinking**, leading to a well-structured **Instruction Summarization**.
# ### Output Format
# Adhere strictly to the following JSON format:
# ```json
# {{
# "CoT": [
#     {{"action": "Inner Thinking", "title": "...", "content": "..."}},
#     ...,
#     {{"action": "Instruction Summarization", "content": "..."}}
# ]
# }}
# ```
# """
