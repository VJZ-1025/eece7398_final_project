import textworld.gym
from textworld import gym
from textworld import EnvInfos
import json
from openai import OpenAI
import os
from dotenv import load_dotenv
from pprint import pprint
from elasticsearch import Elasticsearch

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
ES_HOST = "http://localhost:9200"
# TODO: This while loop should be modified to use an LLM agent instead of human input
# The game contains NPCs (non-player characters) like:
# - Sheriff (indicated by type 'c' in textWorldMap.py)
# These containers/NPCs can hold items and interact with the player
# 


class LLM_Agent:
    def __init__(self):
        self.game_file = "./textworld_map/village_game.z8"
        self.action_client = OpenAI(api_key=OPENAI_API_KEY)
        self.main_client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")
        self.infos = EnvInfos(admissible_commands=True, facts=True, inventory=True)
        self.env_id = textworld.gym.register_games([self.game_file], request_infos=self.infos, max_episode_steps=None)
        self.env = gym.make(self.env_id)
        self.obs, self.infos = self.env.reset()
        self.done = False
        self.memory = []
    def reset_game(self):
        self.obs, self.infos = self.env.reset()
        self.done = False
    
    def initial_process(self, user_input):
        """
        Main LLM for user communication
        """
        print("Initial process...")
        prompt = f"""
        <Background>
        You are the main dialogue LLM communicating with the player. You need act as a villager who is assisting the player.
        The player is a ghost who cannot interact directly with the world, but you are the only one who can help him by communicating with him.
        </Background>
        
        <Question>
        You need to understand the player's intent based on the player's input, and classify the player's intent into one of the following categories:
        - Action: the player wants to take an action
        - Query: the player wants to ask a question
        - Talk: the player wants you to talk to someone
        - Chat: The player wants to chat with you, first you need determine is the input is related to the game, if yes you need to generate the dialog as a villager based on the user's input, else you decide as "other"
        - Other: the player's intent is not clear, or the player's intent is not related to the game. NOTE: all other intents including asking about weather, time, etc. should be classified as "other"

        IMPORTANT: You MUST classify the player's intent into one of the above categories, and you MUST return the classification in the format provided below.
        </Question>

        <status content>
        - Action: the content should be a short description of the action the player wants to take
            - content format: "<a short description of the action>"
        - Query: the content should determin the question the player wants to ask, and decide if need extra memory to answer the question, format should be json
            - content format: {{"question": "<a short description of the question>", "memory": true|false, "memory_query": "<a short description of the memory query>"}}
        - Talk: the content should generate the dialog as a villager based on the user's input, format should be json
            - content format: {{"npc": "villager|Sheriff|Drunker|Vendor","dialog": "<a short description of the dialog>"}}
        - Chat: The player wants to chat with you, and you need to generate the dialog as a villager based on the user's input
            - content formmat "<a short description of the dialog>"
        - Other: a reason why the player's intent is not clear, or the player's intent is not related to the game
            - content format: "<a short description of the reason>"
        </status content>
        
        <game status>
        current location: {self.get_current_location()}
        inventory: {self.get_current_inventory()}
        </game status>

        <response requirements>
        Your response must follow a structured reasoning process with two distinct action types: **"Inner Thinking"**, **"Verifiy Thinking"**, and **"Instruction Summarization"**.
        - Inner Thinking: Reconstruct the reasoning process step by step. Each step should have a brief title for clarity.
        - Verifiy Thinking: If a mistake is found, correct it by backtracking.
        - Instruction Summarization: Summarize key takeaways from the new reasoning process and provide actionable instructions.
        </response requirements>
        
        <output format>
        {{
            "CoT": [
                {{"action": "Inner Thinking", "title": "understand the player's intent", "content": "..."}},
                {{"action": "Inner Thinking", "title": "classify the player's intent", "content": "..."}},
                {{"action": "Verifiy Thinking", "title": "verify the classification", "content": "..."}},
                {{"action": "Instruction Summarization", "status": "Action|Query|Talk|Other", "content": "..."}}
            ]
        }}
        """
        response = self.main_client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "system", "content": prompt},
                      {"role": "user", "content": user_input}],
            max_tokens=300,
            temperature=0.3,
        )
        print(response.choices[0].message.content)
        list_actions = json.loads(response.choices[0].message.content)["CoT"]
        print(list_actions)
        inner_thinking = list_actions[:(len(list_actions) - 1)]
        pprint(list_actions)
        content = list_actions[len(list_actions) - 1]
        return content
    
    def make_action(self, plain_text_explanation):
        print("Action thinking...")
        
        prompt_template = f"""
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
            - give <item> to <npc>: This is is a shortcut that combines multiple actions:
                1. insert <item> into <npc>
                output: ['insert <item> into <npc>']
                - check inventory has item, if not, reject the command, return ["reject command"]
                - check current location at npc, if not, go to npc first, then execute the command
                - IMPORTANT: if the npc is "Drunker", do below steps:
                1. unlock Drunker with <item>
                2. open Drunker
                4. insert <item> into Drunker
            
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
                        - Has items: {self.check_items_in_container('Vendor')}
                    - Well:
                        - Location: Center Park
                        - Has items: {self.check_items_in_container('Well')}
                    - Sheriff:
                        - Location: Sheriff's Office
                        - Has items: {self.check_items_in_container('Sheriff')}
                    - Drunker:
                        - Location: Forest
                        - Has items: {self.check_items_in_container('Drunker')}
                - NPCs (non-player characters):
                    - Villager:
                        - Location: House 2
                    - Drunker:
                        - Location: Forest
                    - Sheriff:
                        - Location: Sheriff's Office
                    - Vendor:
                        - Location: Shop
                
                - NOTE:
                    - Container Sheriff, Drunk, Vendor are NPCs that can hold items, indicated by container: c.
                    - NPC villagers cannot hold items.
                    - Container Well is a well, which is a container that can hold items, its not a NPC.
                
                - Consider the player's current location: 
                    {self.get_current_location()}
                - Inventory: {self.get_current_inventory()}
                    
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
                            {{"action": "Inner Thinking", "title": "Identify current situation and the target", "content": "..."}},
                            {{"action": "Inner Thinking", "title": "Determine the optimal path and commands and make draft of the command", "content": "..."}},
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
                            {{"action": "Inner Thinking", "title": "Identify current situation and the target", "content": "The player is currently at House 1, which is in the bottom row, left column of the grid, the player inventory is empty. The target is take the money then go to shop, and buy rope, because buy rope is a special command, so it should divde to unlock vendor with money, open vendor, take rope from vendor, insert money into vendor, close vendor."}},
                            {{"action": "Inner Thinking", "title": "Determine the optimal path and commands and make draft of the command", "content": "Take money, then from house 1 to shop go north to school, then go north to shop, then unlock vendor with money, open vendor, take rope from vendor, insert money into vendor, close vendor. Hence, the command is: ['take money', 'go north', 'go north', 'unlock vendor with money', 'open vendor', 'take rope from vendor', 'insert money into vendor', 'close vendor']"}},
                            {{"action": "Verifiy Thinking", "title": "Simulate the command check the result", "content": "The command is correct. 'go north' moves the player from House 1 to School, and 'go north' moves the player from School to shop, then unlock vendor with money, open vendor, take rope from vendor, insert money into vendor, close vendor."}},
                            {{"action": "Instruction Summarization", "status": "approved", "content": ["take money", "go north", "go north", "unlock vendor with money", "open vendor", "take rope from vendor", "insert money into vendor", "close vendor"]}}
                        ]
                    }}
                </example>
            """
        response = self.action_client.chat.completions.create(
            model="o3-mini",
            messages=[{"role": "system", "content": prompt_template},
                    {"role": "user", "content": f"Here is the command explanation: {plain_text_explanation}"}],
        )
        print(response.choices[0].message.content)
        jsonfy_response = json.loads(response.choices[0].message.content)
        status = jsonfy_response["CoT"][len(jsonfy_response["CoT"]) - 1]["status"]
        if status == "rejected":
            print("enh enh, you can't do that")
            self.obs, self.reward, self.done, self.infos = self.env.step("")
            return False
        list_of_commands = jsonfy_response["CoT"][len(jsonfy_response["CoT"]) - 1]["content"]
        if list_of_commands == ["reject command"]:
            print("nah nah, you can't do that")
            self.obs, self.reward, self.done, self.infos = self.env.step("")
            return False
        for command in list_of_commands:
            # print(f"\nExecuting command: {command}")
            self.obs, self.reward, self.done, self.infos = self.env.step(command)
            print(self.obs)
            if self.done:
                print("Game Over!")
                return True
        return True


    def get_memory(self, oringinal_sentence, memory_query):
        '''
        Get memory from the original sentence and the memory query
        Original sentence: the sentence that the player inputs
        Memory query: The query that LLM generates
        '''
        # TODO: add memory mechanism
        return self.memory
    
    def generate_dialog(self, user_input, memory):
        '''
        Generate the dialog as a villager based on the user's input
        '''
        return "not yet implemented"

    def check_items_in_container(self, container):
        '''
        Check if the container has items, and return the items in a string
        '''
        items = []
        for prop in self.infos.get('facts', []):
            if prop.name == 'in' and prop.arguments[1].name == container:
                items.append(prop.arguments[0].name)
        
        if len(items) == 0:
            return ''
        else:
            return ', '.join(items)
    
    def get_current_obs(self):
        return self.obs

    def get_current_inventory(self):
        return self.infos.get("inventory", [])
    
    def get_current_location(self):
        return self.obs.split("-= ")[1].split(" =-")[0] if "-= " in self.obs and " =-" in self.obs else ""
    
    def main_process(self, user_input):
        '''
        Main process of the agent
        '''
        content = self.initial_process(user_input)
        if content["status"] == "Action":
            commands = content["content"]
            action = self.make_action(commands)
            if action:
                return "action success"
            else:
                return "action failed"

        elif content["status"] == "Query":
            memory_needed = content["content"]["memory"]
            memory = "No memory needed"
            if memory_needed:
                memory = self.get_memory(user_input, content["content"]["memory_query"])
            return self.generate_dialog(user_input, memory)
        elif content["status"] == "Talk":
            return "not yet implemented"
        elif content["status"] == "Chat":
            return self.generate_dialog(user_input, content["content"])
        else:
            return "not yet implemented"


# obs, reward, done, infos = make_action(obs, infos, "take money, buy wine, give wine to drunker, take rope from Drunker, down to well")
# obs, reward, done, infos = make_action(obs, infos, "give knife to Sheriff")

# TEST:
# agent = LLM_Agent("village_game.z8", OPENAI_API_KEY, DEEPSEEK_API_KEY)
# agent.main_process("You should talk to the sheriff about the money")
# agent.make_action("buy wine")




# def main():
#     history = []  # 用于保存对话与游戏推进的历史记录
#     global obs, infos, done
#     while not done:
#         print("\nCurrent scene:")
#         print(obs)
#         current_location = obs.split("-= ")[1].split(" =-")[0] if "-= " in obs and " =-" in obs else ""
#         user_input = input("\nEnter your action (e.g., 'buy rope', 'talk to Vendor', 'down to well'): \n")
#         history.append({"event": "Player Input", "detail": user_input})
        
#         # Step 1: 调用 Main LLM 进行用户对话，获取玩家判断
#         main_judgment = main_llm_interaction(user_input, history, current_location, infos.get("inventory", []))
#         print("Main LLM judgment:", main_judgment)
#         history.append({"event": "Main LLM Judgment", "detail": main_judgment})
        
#         # Step 2: 将 Main LLM judgment 提交给 Master LLM，生成具体的行动命令
#         commands = make_action(obs, infos, main_judgment)
#         for cmd in commands:
#             print(f"\nExecuting command: {cmd}")
#             obs, reward, done, infos = env.step(cmd)
#             print(obs)
#             history.append({"event": "Game Progress", "detail": f"Executed command: {cmd}"})
#             if done:
#                 break
        
#     print("Game Over!")

