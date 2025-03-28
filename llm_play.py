import textworld.gym
from textworld import gym
from textworld import EnvInfos
import json
from openai import OpenAI
import os
from dotenv import load_dotenv
from pprint import pprint
from sentence_transformers import SentenceTransformer
from elasticsearch import Elasticsearch


load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
ES_HOST = os.getenv("ES_HOST")
# TODO: This while loop should be modified to use an LLM agent instead of human input
# The game contains NPCs (non-player characters) like:
# - Sheriff (indicated by type 'c' in textWorldMap.py)
# These containers/NPCs can hold items and interact with the player
# 

class ElasticsearchMemory:
    def __init__(self, es: Elasticsearch):
        self.es = es
        logger.info(f"Connected to Elasticsearch cluster: {es.info()}")
        self.index_name = "memory"
        self.mapping = {
            "mappings": {
                "properties": {
                    "npc": {"type": "keyword"},
                    "type": {"type": "keyword"},
                    "summary": {"type": "text"},
                    "raw_input": {"type": "text"}, 
                    "memory_query": {"type": "text"},
                    "location": {"type": "keyword"},
                    "inventory": {"type": "keyword"},
                    "timestamp": {"type": "date"},
                    "embedding": {
                        "type": "dense_vector",
                        "dims": 384,
                        "index": True,
                        "similarity": "cosine"
                    }
                }
            }
        }
        self._initialize_index()
        self.model = SentenceTransformer('BAAI/bge-base-en-v1.5')

    def _initialize_index(self):
        if self.es.indices.exists(index=self.index_name):
            self.es.indices.delete(index=self.index_name)
            logger.info(f"Existing index '{self.index_name}' deleted.")
        
        self.es.indices.create(index=self.index_name, body=self.mapping)
        logger.info(f"Index '{self.index_name}' created.")

    def create_embedding(self, text):
        return self.model.encode(text, show_progress_bar=False)
    
    def search(self, query_template):
        return self.es.search(index=self.index_name, body=query_template)






def clean_json_prefix(json_str):
    return json_str.replace("```json", "").replace("```", "")

class LLM_Agent:
    def __init__(self):
        self.game_file = "./textworld_map/village_game.z8"
        self.es = Elasticsearch(ES_HOST)
        self.elasticsearch_memory = ElasticsearchMemory(self.es)
        self.action_client = OpenAI(api_key=OPENAI_API_KEY)
        self.main_client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")
        
        #add NPC
        self.teacher_npc = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")
        self.vender_npc = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")
        self.sheriff_npc = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")
        
        
        self.infos = EnvInfos(admissible_commands=True, facts=True, inventory=True)
        self.env_id = textworld.gym.register_games([self.game_file], request_infos=self.infos, max_episode_steps=None)
        self.env = gym.make(self.env_id)
        self.obs, self.infos = self.env.reset()
        self.done = False
        self.dialog_history = {
            "main_character": [],
            "villager": [],
            "vendor": [],
            "drunker": [],
            "sheriff": [],
            "teacher": []
            
        }
        
        #NPC 位置
        self.npc_locations ={
            "teacher": "School",
            "vendor"": "Shop",
            "sheriff": "Sheriff's Office"
        }
        
        # NPC 特性和知识
        self.npc_traits = {
            "Vendor": "A grumpy merchant selling goods for money. Suspicious of strangers.",
            "Sheriff": "A stern law enforcement officer investigating a murder case.",
            "Drunker": "An intoxicated character who might share secrets if given wine.",
            "Villager": "A friendly local with gossip and knowledge about the village.",
            "Teacher": "A wise and patient educator who knows much about the village history and its inhabitants. Can provide guidance to newcomers."
        }
        
    def reset_game(self):
        self.obs, self.infos = self.env.reset()
        self.done = False
    
    def initial_process(self, user_input):
        """
        Main LLM for user communication
        """
        logger.info("Initial process...")
        
        # 获取当前位置
        current_location = self.get_current_location()
        
        # 获取当前位置的 NPC
        npcs_here = [npc for npc, location in self.npc_locations.items() if location == current_location]
        npcs_info = "No NPCs present." if not npcs_here else f"NPCs present: {', '.join(npcs_here)}"
        
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
            - for memory, if you can answer the question based on the current information you have, you should set memory to false, else you should set memory to true
            - content format: {{"question": "<a short description of the question>", "memory": true|false, "memory_query": "<a short description of the memory query>"}}
        - Talk: the content should generate the dialog as a villager based on the user's input, format should be json
             current location: {self.get_current_location()}
            - content format: {{"npc": "Villager|Sheriff|Drunker|Vendor|Teacher","dialog": "<a short description of the dialog>"}}
        - Chat: The player wants to chat with you, and you need to generate the dialog as a villager based on the user's input
            - content formmat "<a short description of the dialog>"
        - Other: a reason why the player's intent is not clear, or the player's intent is not related to the game
            - content format: "<a short description of the reason>"
        </status content>
        
        <game status>
        current location: {self.get_current_location()}
        inventory: {self.get_current_inventory()}
        {npcs_info}
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
        Your output must be **pure JSON only**. 
        You MUST NOT include markdown syntax like ```json or ``` at the beginning or end of the response.
        Only return raw JSON. Do NOT wrap or format the output in any way.
        ***Do NOT include any extra text outside of the JSON format, DO NOT USE MARKDOWN(```json) DO! NOT! USE! MARKDOWN!, please only return the string of JSON format, DO NOT use ```json, DO NOT modify the action and title, DO NOT modify the number of CoT***
        </output format>
        """
        
        # 剩余部分保持不变
        response = self.main_client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "system", "content": prompt},
                      {"role": "user", "content": user_input}],
            max_tokens=300,
            temperature=0.3,
        )
        logger.info(response.choices[0].message.content)
        list_actions = json.loads(clean_json_prefix(response.choices[0].message.content))["CoT"]
        logger.info(list_actions)
        inner_thinking = list_actions[:(len(list_actions) - 1)]
        pprint(list_actions)
        content = list_actions[len(list_actions) - 1]
        return content
    
    def make_action(self, plain_text_explanation):
        logger.info("Action thinking...")
        
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
        logger.info(response.choices[0].message.content)
        jsonfy_response = json.loads(response.choices[0].message.content)
        status = jsonfy_response["CoT"][len(jsonfy_response["CoT"]) - 1]["status"]
        if status == "rejected":
            logger.info("enh enh, you can't do that")
            self.obs, self.reward, self.done, self.infos = self.env.step("")
            return False
        list_of_commands = jsonfy_response["CoT"][len(jsonfy_response["CoT"]) - 1]["content"]
        if list_of_commands == ["reject command"]:
            logger.info("nah nah, you can't do that")
            self.obs, self.reward, self.done, self.infos = self.env.step("")
            return False
        for command in list_of_commands:
            # print(f"\nExecuting command: {command}")
            self.obs, self.reward, self.done, self.infos = self.env.step(command)
            logger.info(self.obs)
            if self.done:
                logger.info("Game Over!")
                return True
        return True


    def get_memory(self, oringinal_sentence, memory_query):
        '''
        Get memory from the original sentence and the memory query
        Original sentence: the sentence that the player inputs
        Memory query: The query that LLM generates
        '''
        # TODO: add memory mechanism
        prompt = f"""
        <question>
        You are a Elasticsearch memory LLM, you need build a qurey and word need embeded to get the memory from Elasticsearch, the query should be based on the original sentence and the memory query, and the word need embeded.
        </question>

        <elasticsearch_index_structure>
         {{
            "mappings": {{
                "properties": {{
                    "npc": {{"type": "keyword"}},
                    "type": {{"type": "keyword"}},
                    "summary": {{"type": "text"}},
                    "raw_input": {{"type": "text"}},
                    "memory_query": {{"type": "text"}},
                    "location": {{"type": "keyword"}},
                    "inventory": {{"type": "keyword"}},
                    "timestamp": {{"type": "date"}},
                    "embedding": {{
                        "type": "dense_vector",
                        "dims": 384,
                        "index": True,
                        "similarity": "cosine"
                    }}
                }}
            }}
        }}
        </elasticsearch_index_structure>

        <response requirements>
        Your response must follow a structured reasoning process with two distinct action types: **"Inner Thinking"**, **"Verifiy Thinking"**, and **"Instruction Summarization"**.
        - Inner Thinking: Reconstruct the reasoning process step by step. Each step should have a brief title for clarity.
        - Verifiy Thinking: If a mistake is found, correct it by backtracking.
        - Instruction Summarization: Summarize key takeaways from the new reasoning process and provide actionable instructions.
        - Output should strictly be a JSON list of step-by-step commands.
        - Example format:
            {{
                "CoT": [
                    {{"action": "Inner Thinking", "title": "determine the user_input and memory_query and reasoning what qurey to search in Elasticsearch", "content": "..."}},
                    {{"action": "Inner Thinking", "title": "determine the query to search in Elasticsearch", "content": "..."}},
                    {{"action": "Verifiy Thinking", "title": "verify the query", "content": "..."}},
                    {{"action": "Instruction Summarization", "content": "{{
                        "query": {{
                            "npc": {{
                                need_get: true|false,
                                npc_name: "..."
                            }},
                            "type": {{
                                need_get: true|false,
                                type_query: "..."
                            }},
                            "summary": {{
                                need_get: true|false,
                                summary_query: "..."
                            }},
                            "location": {{
                                need_get: true|false,
                                location_query: "..."
                            }},
                            "inventory": {{
                                need_get: true|false,
                                inventory_query: "..."
                            }}
                        }}
                        "word_need_embed": "..."
                    }}"}}
                ]
            }}
        - Explaination:
            - if the need_get is true, you must have a query to search in Elasticsearch, the query is the key word that you think is most relevant to the original sentence and the memory query
        </response requirements>
        """

        user_input = f"""
        Original sentence: {oringinal_sentence}
        Memory query: {memory_query}
        """
        response = self.main_client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "system", "content": prompt},
                      {"role": "user", "content": user_input}],
            temperature=0.3
        )
        response_json = json.loads(clean_json_prefix(response.choices[0].message.content))
        embedding_word = response_json["CoT"][-1]["content"]["word_need_embed"]
        embedding_vector = self.elasticsearch_memory.create_embedding(embedding_word)
        qurey_template = {
            "query": {
                "bool": {
                    "must": [
                        {
                            "script_score": {
                                "query": {"match_all": {}},
                                "script": {
                                    "source": "cosineSimilarity(params.query_vector, 'embedding') + 1.0",
                                    "params": {"query_vector": embedding_vector.tolist()}
                                }
                            }
                        }
                    ]
                }
            },
            "size": 10,
            "sort": [
                {
                    "timestamp": {"order": "desc"}
                }
            ]
        }
        logger.info(response_json)
        query_content = response_json["CoT"][-1]["content"]["query"]
        query_fields = ["npc", "type", "summary", "location", "inventory"]
        
        for field in query_fields:
            if query_content[field]["need_get"]:
                qurey_template["query"]["bool"]["must"].append({
                    "match": {
                        field: query_content[field][f"{field}_query" if field != "npc" else "npc_name"]
                    }
                })
        
        search_result = self.elasticsearch_memory.search(qurey_template)
        if search_result["hits"]["hits"]:
            return search_result["hits"]["hits"][0]["_source"]["summary"]
        else:
            return "No memory found"
    
    def generate_dialog(self, user_input, memory):
        '''
        Generate the dialog as a villager based on the user's input
        '''

        prompt = f"""
        <question>
        You are the main character in the game, you task is to generate a dialog based on the history conversation and the user's input and the memory.
        Read the story background and the game state carefully, and generate the dialog based on the history conversation and the user's input and the memory.
        The story background already provide who is the murderer, but you need to pretend you don't know and help the user to find the murderer.
        You don't need to make decision because You are one component of a larger system working together to assist the user, the previous LLM has already made the decision.
        You should follow the instructions strictly and generate the dialog based on the history conversation and the user's input and the memory.
        </question>

        <story_background>
        You are a brave and sence of justice villager in a small village. The user is player who in this game setting is died ghost, and you are the only one who can see and talk to him.
        Becuase the user is a ghost, he can interact with the world, so you can assume he is blind, you need describe the environment.
        The user is trying to find the murderer of they You need to help the user to find the murderer. 
        The user was killed by last night, the tool is a knife, and the murderer is the vendor.
        The goal is brings the knife to the sheriff, and because the knife has fingerprints, the sheriff will arrest the vendor.
        The knife is in the well, you need take rope down to the well, and take the knife from the well.
        There are two rope in this game, one you can buy from the vendor, another one is by the drunker.
        You can use money to buy the rope from the vendor, or you can use money to buy the wine, and give the wine to the drunker, then the drunker will give you the rope.
        The sheriff will arrest the vendor if you bring the knife to the sheriff.
        </story_background>

        <game state>
        {self.obs}
        </game state>

        <instructions>
        Below, you will receive a list of messages including:
            - previous user inputs,
            - your previous responses,
            - and finally, the current user message.
        Use the full history to infer the user's intent and respond appropriately based on both past memory and current game state.
        One of the previous LLM recieved the user's input to determine if need external memory, here is the result:
        memory: {memory}
        Use the memory to generate the dialog. 
        - if the memory shows 'No memory needed', you should generate the dialog based on the the game state I provided and the history conversation and the user's input.
        - if the memory shows 'No memory found', its means the thing that user asked is not in memory, you should generate the dialog based on the the game state I provided and the history conversation and the user's input.
        </instructions>

        <response requirements>
        - Your response should be a dialog based on the history conversation and the user's input and the memory.
        - The dialog should be in the same language as the user's input.
        - The dialog should be in the same style as the history conversation.
        - The dialog should be in the same tone as the history conversation.
        - The dialog should be in the same format as the history conversation.
        - The dialog should be as short as possible.
        - The output should be a single string sentence.
        </response requirements>
        """
        message = [
            {"role": "system", "content": prompt}
        ]
        if len(self.dialog_history["main_character"]) > 0:
            for i in range(len(self.dialog_history["main_character"])):
                message.append({"role": "user", "content": self.dialog_history["main_character"][i]["user"]})
                message.append({"role": "assistant", "content": self.dialog_history["main_character"][i]["assistant"]})
        message.append({"role": "user", "content": f"Here is the user's input: {user_input}"})
        response = self.action_client.chat.completions.create(
            model="o3-mini",
            messages=message
        )
        logger.info(response.choices[0].message.content)
        self.dialog_history["main_character"].append({"user": user_input, "assistant": response.choices[0].message.content})
        return response.choices[0].message.content

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
    
    def interact_with_teacher(self, user_input):
        """
        与教师 NPC 交互
        """
        current_location = self.get_current_location()
        
        # 检查用户是否在正确的位置
        if current_location != "School":
            return "The Teacher is not here. You need to go to the School to talk to the Teacher."
        
        logger.info("Interacting with Teacher NPC...")
        
        # 构建教师角色的提示
        prompt = f"""
        <npc_character>
        You are the Teacher in the village school. You are a wise and patient educator who knows much about the village history and its inhabitants. 
        You are helpful to students and visitors, and can provide guidance about the village and its mysteries.
        
        Character traits:
        - Knowledgeable about village history and residents
        - Patient and willing to explain things
        - Observant and notices unusual events in the village
        - Cares about the well-being of villagers
        - Maintains a formal but friendly tone
        - Suspicious of the recent murder but tries not to spread rumors
        
        Special knowledge:
        - You've heard rumors about strange activities at the well at night
        - You know most of the villagers, including their habits and backgrounds
        - You are aware that the vendor sometimes acts suspiciously
        - You've seen someone near the forest at night recently
        </npc_character>
        
        <game_state>
        Current location: {current_location}
        Player's inventory: {self.get_current_inventory()}
        Game observation: {self.obs}
        </game_state>
        
        <instructions>
        Respond to the player as the Teacher would. Maintain your character's personality and knowledge.
        Your responses should be helpful but not reveal too much at once about the murder mystery.
        The player is a ghost trying to solve their own murder, but you don't need to explicitly mention this.
        Keep your responses relatively brief and in the style of a village teacher.
        </instructions>
        
        <player_question>
        {user_input}
        </player_question>
        """
        
        # 获取对话历史
        conversation_history = []
        if self.dialog_history["teacher"]:
            for i in range(min(5, len(self.dialog_history["teacher"]))):  # 最多包含最近5次对话
                idx = len(self.dialog_history["teacher"]) - 1 - i
                conversation_history.insert(0, {"role": "user", "content": self.dialog_history["teacher"][idx]["user"]})
                conversation_history.insert(1, {"role": "assistant", "content": self.dialog_history["teacher"][idx]["assistant"]})
        
        messages = [{"role": "system", "content": prompt}]
        messages.extend(conversation_history)
        messages.append({"role": "user", "content": user_input})
        
        # 调用教师 NPC 的 LLM
        response = self.teacher_npc.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            temperature=0.7
        )
        
        teacher_response = response.choices[0].message.content
        logger.info(f"Teacher NPC response: {teacher_response}")
        
        # 保存对话历史
        self.dialog_history["teacher"].append({"user": user_input, "assistant": teacher_response})
        
        return teacher_response

    def main_process(self, user_input):
        '''
        Main process of the agent
        '''
        content = self.initial_process(user_input)
        if content["status"] == "Action":
            commands = content["content"]
            action = self.make_action(commands)
            if action:
                # 检查行动后是否有 NPC
                current_location = self.get_current_location()
                npcs_here = [npc for npc, location in self.npc_locations.items() if location == current_location]
                
                if npcs_here:
                    return f"Action successful. You notice: {', '.join(npcs_here)} here."
                return "Action successful."
            else:
                return "Action failed."

        elif content["status"] == "Query":
            memory_needed = content["content"]["memory"]
            memory = "No memory needed"
            if memory_needed:
                memory = self.get_memory(user_input, content["content"]["memory_query"])
            return self.generate_dialog(user_input, memory)
            
        elif content["status"] == "Talk":
            # 与 NPC 交互
            npc = content["content"]["npc"]
            dialog = content["content"]["dialog"]
            
            # 根据 NPC 类型调用相应的交互方法
            if npc.lower() == "teacher":
                return self.interact_with_teacher(dialog)
            elif npc.lower() == "vendor":
                # 如果实现了与 vendor 的交互方法，可以调用
                # return self.interact_with_vendor(dialog)
                return f"Talking to {npc}: {dialog}"
            elif npc.lower() == "sheriff":
                # 如果实现了与 sheriff 的交互方法，可以调用  
                # return self.interact_with_sheriff(dialog)
                return f"Talking to {npc}: {dialog}"
            else:
                return f"Talking to {npc}: {dialog}"
            
        elif content["status"] == "Chat":
            return self.generate_dialog(user_input, content["content"])
            
        else:
            return "not yet implemented, please try again"


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

