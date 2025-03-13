import textworld.gym
from textworld import gym
from textworld import EnvInfos
import json
from openai import OpenAI

client = OpenAI(api_key="API_KEY")

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
        Commands include movement ("go <dir>"), interaction ("take ...", "open ...", if in container, "take ... from ...", if locked, "unlock ... with ...").
        </valid actions>

        <response requirements>
        Your response must follow a structured reasoning process with two distinct action types: **"Inner Thinking"**, **"Verifiy Thinking"**, and **"Instruction Summarization"**.

        1. **Inner Thinking**: Reconstruct the reasoning process step by step. Each step should have a brief title for clarity.
            - Grid Layout:
                - Shop is at the northwest corner. Its east is the Village Committee, and its south is the School.
                - Village Committee is at the north-central position. Its west is the Shop, its east is the Hospital, and its south is the Park.
                - Hospital is at the northeast corner. Its west is the Village Committee, and its south is the Sheriff's Office.
                - School is at the middle row, west side. Its north is the Shop, its east is the Park, and its south is House 1.
                - Park is at the center of the map. Its north is the Village Committee, its west is the School, its east is the Sheriff's Office, and its south is House 2.
                - Sheriff's Office is at the middle row, east side. Its north is the Hospital, its west is the Park, and its south is the Forest.
                - House 1 is at the southwest corner. Its north is the School, and its east is House 2.
                - House 2 is at the south-central position. Its north is the Park, its west is House 1, and its east is Forest.
                - Forest is at the southeast corner. Its north is the Sheriff's Office, and its west is House 2.
            
            - Consider the player's current location: 
                {current_location}
            - Inventory: {infos.get("inventory", [])}
                
            - Identify the target location and determine the optimal path.

            - Use logical reasoning to determine the **shortest path** to the target location while considering obstacles and key items.

        2. **Verifiy Thinking**: If a mistake is found, correct it by backtracking.
        3. **Instruction Summarization**: Summarize key takeaways from the new reasoning process and provide actionable instructions.
            - Output should strictly be a JSON list of step-by-step commands.
            - Example format:
            {{
                "CoT": [
                    {{"action": "Inner Thinking", "title": "Identify current position", "content": "..."}},
                    {{"action": "Inner Thinking", "title": "Identify the target location", "content": "..."}},
                    {{"action": "Inner Thinking", "title": "Determine shortest path", "content": "..."}},
                    {{"action": "Inner Thinking", "title": "Make draft of the command", "content": "..."}},
                    {{"action": "Verifiy Thinking", "title": "Simulate the command check the result", "content": "..."}},
                    {{"action": "Instruction Summarization", "content": ["...command 1", "...command 2"]}}
                ]
            }}
            Do NOT include any extra text outside of the JSON format.
            </response requirements>

            <example>
            Golden standard:
            - command explanation: Go to the Park
            - current location: House 1
                {{
                    "CoT": [
                        {{"action": "Inner Thinking", "title": "Identify current position", "content": "The player is currently at House 1, which is in the bottom row, left column of the grid."}},
                        {{"action": "Inner Thinking", "title": "Identify the target location", "content": "The target location is the Park, which is in the middle row, center column of the grid."}},
                        {{"action": "Inner Thinking", "title": "Determine shortest path", "content": "From House 1, move north to School, then move east to Park."}},
                        {{"action": "Inner Thinking", "title": "Make draft of the command", "content": "The commands should be: ['go north', 'go east']."}},
                        {{"action": "Verifiy Thinking", "title": "Simulate the command check the result", "content": "The command is correct. 'go north' moves the player from House 1 to School, and 'go east' moves the player from School to Park."}},
                        {{"action": "Instruction Summarization", "content": ["go north", "go east"]}}
                    ]
                }}
            </example>
        """
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": prompt_template},
                  {"role": "user", "content": f"Here is the command explanation: {plain_text_explanation}"}],
        max_tokens=1000,
        temperature=0.3,
    )
    print(response.choices[0].message.content)
    list_of_commands = json.loads(response.choices[0].message.content)["CoT"][5]["content"]
    for command in list_of_commands:
        print(f"\nExecuting command: {command}")
        print(obs)
        obs, reward, done, infos = env.step(command)
        print(obs)
        if done:
            return obs, reward, done, infos
    return obs, reward, done, infos
    
#  test the make_action function
obs, reward, done, infos = make_action(obs, infos, "go to the Shop")
obs, reward, done, infos = make_action(obs, infos, "go to the House 2")
obs, reward, done, infos = make_action(obs, infos, "go to the Forest")
obs, reward, done, infos = make_action(obs, infos, "go to the Sheriff's Office")
obs, reward, done, infos = make_action(obs, infos, "go to the Hospital")
obs, reward, done, infos = make_action(obs, infos, "go to the Park")
obs, reward, done, infos = make_action(obs, infos, "go to the Village Committee")
obs, reward, done, infos = make_action(obs, infos, "go to the School")

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
