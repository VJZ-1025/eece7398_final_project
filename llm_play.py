import textworld.gym
from textworld import gym
from textworld import EnvInfos
import json
from openai import OpenAI
import os
from dotenv import load_dotenv
from pprint import pprint
from datetime import datetime
from sentence_transformers import SentenceTransformer
from elasticsearch import Elasticsearch


load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_API_KEY_Villager = os.getenv("DEEPSEEK_API_KEY_Villager")
ES_HOST = os.getenv("ES_HOST")

import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('llm_play.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# TODO: This while loop should be modified to use an LLM agent instead of human input
# The game contains NPCs (non-player characters) like:
# - Sheriff (indicated by type 'c' in textWorldMap.py)
# These containers/NPCs can hold items and interact with the player
# 

class ElasticsearchMemory:
    def __init__(self, es: Elasticsearch):
        self.es = es
        self.index_name = "memory"
        self.mapping = {
            "mappings": {
                "properties": {
                    "character": {"type": "keyword"},
                    "memory_type": {"type": "keyword"},
                    "summary": {"type": "text"},
                    "raw_input": {"type": "text"}, 
                    "keywords": {"type": "keyword"},
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
        self.model = SentenceTransformer('BAAI/bge-small-en-v1.5')

    def _initialize_index(self):
        if self.es.indices.exists(index=self.index_name):
            self.es.indices.delete(index=self.index_name)
        
        self.es.indices.create(index=self.index_name, body=self.mapping)

    def create_embedding(self, text):
        return self.model.encode(text, show_progress_bar=False)
    
    def search(self, query_template):
        return self.es.search(index=self.index_name, body=query_template)
    
    def insert(self, data):
        return self.es.index(index=self.index_name, body=data)
    def delete(self,id):
        return self.es.delete(index="memory", id=id)






def clean_json_prefix(json_str):
    return json_str.replace("```json", "").replace("```", "")

class LLM_Agent:
    def __init__(self):
        self.game_file = "./textworld_map/village_game.z8"
        self.es = Elasticsearch(ES_HOST)
        self.elasticsearch_memory = ElasticsearchMemory(self.es)
        self.action_client = OpenAI(api_key=OPENAI_API_KEY)
        self.main_client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")
        self.villager = OpenAI(api_key =DEEPSEEK_API_KEY_Villager,base_url = "https://api.deepseek.com")
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
            "sheriff": []
            
        }
        # npc location
        self.npc_locations ={
            "villager": "House 2"
        }

        self.npc_traits = {
            "Villager": "A friendly local with gossip and knowledge about the village."
        }

        self.chat_round = 0
    def reset_game(self):
        self.obs, self.infos = self.env.reset()
        self.done = False
        self.chat_round = 0
        self.dialog_history = {
            "main_character": [],
            "villager": [],
            "vendor": [],
            "drunker": [],
            "sheriff": []
        }
        self.elasticsearch_memory._initialize_index()
        logger.info('''
------------------------------------------------------







                    reset game







------------------------------------------------------
                    ''')

    
    def initial_process(self, user_input):
        """
        Main LLM for user communication
        """
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
            - first you need to determine which npc the player want you to talk to.
            - then you need determine the npc is in the current location, if not, you should set npc to "no npc"
                for example:
                current location: Home
                npc_name: Sheriff
                because the sheriff is not in the home, so you should set npc to "no npc"
            - npc_name: the name of the npc the player wants to talk to
            - if the conversation based on the memory, you should set memory to true, else you should set memory to false
            - if the memory is true, you should set memory_query to the memory query, else you should set memory_query to ""
            - content format: {{"npc": "villager|Sheriff|Drunker|Vendor|no npc","dialog": "<a short description of the dialog>", "memory": true|false, "memory_query": "<a short description of the memory query>"}}
        - Chat: The player wants to chat with you, and you need to generate the dialog as a villager based on the user's input
            - content formmat "<a short description of the dialog>"
        - Other: a reason why the player's intent is not clear, or the player's intent is not related to the game
            - content format: "<a short description of the reason>"
        </status content>
        
        <game status>
        current location: {self.get_current_location()}
        inventory: {self.get_current_inventory()}
        </game status>
        <game map>
            - Shop is at the northwest corner. Its east is the Village Committee, and its south is the School.
            - Village Committee is at the north-central position. Its west is the Shop, its east is the Hospital, and its south is the Center Park.
            - Hospital is at the northeast corner. Its west is the Village Committee, and its south is the Sheriff Office.
            - School is at the middle row, west side. Its north is the Shop, its east is the Center Park, and its south is Home.
            - Center Park is at the center of the map. Its north is the Village Committee, its west is the School, its east is the Sheriff Office, and its south is House.
            - Sheriff Office is at the middle row, east side. Its north is the Hospital, its west is the Center Park, and its south is the Forest.
            - Home is at the southwest corner. Its north is the School, and its east is House.
            - House is at the south-central position. Its north is the Center Park, its west is Home, and its east is Forest.
            - Forest is at the southeast corner. Its north is the Sheriff Office, and its west is House.
        </game map>
        <npc location>
            - Villager: House
            - Sheriff: Sheriff Office
            - Drunker: Forest
            - Vendor: Shop
        </npc location>

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
        response = self.main_client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "system", "content": prompt},
                      {"role": "user", "content": user_input}],
            max_tokens=300,
            temperature=0.3,
        )
        list_actions = json.loads(clean_json_prefix(response.choices[0].message.content))["CoT"]
        inner_thinking = list_actions[:(len(list_actions) - 1)]
        logger.info(f"""
------------------------------------------------------
Initial inner thinking: 
{json.dumps(inner_thinking, indent=4)}
------------------------------------------------------
""")
        content = list_actions[len(list_actions) - 1]
        return content
    
    def make_action(self, plain_text_explanation):
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
                    - Hospital is at the northeast corner. Its west is the Village Committee, and its south is the Sheriff Office.
                    - School is at the middle row, west side. Its north is the Shop, its east is the Center Park, and its south is Home.
                    - Center Park is at the center of the map. Its north is the Village Committee, its west is the School, its east is the Sheriff Office, and its south is House.
                    - Sheriff Office is at the middle row, east side. Its north is the Hospital, its west is the Center Park, and its south is the Forest.
                    - Home is at the southwest corner. Its north is the School, and its east is House.
                    - House is at the south-central position. Its north is the Center Park, its west is Home, and its east is Forest.
                    - Forest is at the southeast corner. Its north is the Sheriff Office, and its west is House.
                
                - Container:
                    - Vendor:
                        - Location: Shop
                        - Has items: {self.check_items_in_container('Vendor')}
                    - Well:
                        - Location: Center Park
                        - Has items: {self.check_items_in_container('Well')}
                    - Sheriff:
                        - Location: Sheriff Office
                        - Has items: {self.check_items_in_container('Sheriff')}
                    - Drunker:
                        - Location: Forest
                        - Has items: {self.check_items_in_container('Drunker')}
                - NPCs (non-player characters):
                    - Villager:
                        - Location: House
                    - Drunker:
                        - Location: Forest
                    - Sheriff:
                        - Location: Sheriff Office
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
                            {{"action": "Verifiy Thinking", "title": "Simulate the command check the result, and determine the NPC", "content": "..."}},
                            {{"action": "Instruction Summarization", "status": "approved|rejected|confused", "npc": "None|Sherriff|Drunker|Villager|Vendor", "content": ["...command 1", "...command 2"]}}
                        ]
                    }}
                ***Do NOT include any extra text outside of the JSON format, do NOT modify the action and title, DO NOT modify the number of CoT***
                </response requirements>

                <example>
                Golden standard:
                - command explanation: Take the money and go to shop then buy rope
                - current location: Home
                    {{
                        "CoT": [
                            {{"action": "Inner Thinking", "title": "Identify current situation and the target", "content": "The player is currently at Home, which is in the bottom row, left column of the grid, the player inventory is empty. The target is take the money then go to shop, and buy rope, because buy rope is a special command, so it should divde to unlock vendor with money, open vendor, take rope from vendor, insert money into vendor, close vendor."}},
                            {{"action": "Inner Thinking", "title": "Determine the optimal path and commands and make draft of the command", "content": "Take money, then from Home to shop go north to school, then go north to shop, then unlock vendor with money, open vendor, take rope from vendor, insert money into vendor, close vendor. Hence, the command is: ['take money', 'go north', 'go north', 'unlock vendor with money', 'open vendor', 'take rope from vendor', 'insert money into vendor', 'close vendor']"}},
                            {{"action": "Verifiy Thinking", "title": "Simulate the command check the result", "content": "The command is correct and the npc is the Vendor. 'go north' moves the player from Home to School, and 'go north' moves the player from School to shop, then unlock vendor with money, open vendor, take rope from vendor, insert money into vendor, close vendor."}},
                            {{"action": "Instruction Summarization", "status": "approved", npc: "Vendor", "content": ["take money", "go north", "go north", "unlock vendor with money", "open vendor", "take rope from vendor", "insert money into vendor", "close vendor"]}}
                        ]
                    }}
                </example>
            """
        response = self.action_client.chat.completions.create(
            model="o3-mini",
            messages=[{"role": "system", "content": prompt_template},
                    {"role": "user", "content": f"Here is the command explanation: {plain_text_explanation}"}],
        )
        jsonfy_response = json.loads(response.choices[0].message.content)
        status = jsonfy_response["CoT"][len(jsonfy_response["CoT"]) - 1]["status"]
        if status == "rejected":
            self.obs, self.reward, self.done, self.infos = self.env.step("")
            return False
        list_of_commands = jsonfy_response["CoT"][len(jsonfy_response["CoT"]) - 1]["content"]
        if list_of_commands == ["reject command"]:
            self.obs, self.reward, self.done, self.infos = self.env.step("")
            return False
        for command in list_of_commands:
            self.obs, self.reward, self.done, self.infos = self.env.step(command)
            if self.done:
                return True
        inner_thinking = jsonfy_response["CoT"][:-1]
        logger.info(f"""
------------------------------------------------------
Action inner thinking: 
{json.dumps(inner_thinking, indent=4)}
------------------------------------------------------
""")

        return jsonfy_response["CoT"][-1], True


    def get_memory(self, original_sentence, memory_query):
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
                    "character": {{"type": "keyword"}},
                    "memory_type": {{"type": "keyword"}}, 
                    "summary": {{"type": "text"}},
                    "raw_input": {{"type": "text"}},
                    "keywords": {{"type": "keyword"}},
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

        <structure_explanation>
        - "character": Indicates which character the memory is related to. This can be the player or a non-player character (NPC), or even an ambiguous entity (such as "alex" or "unknown"). It is used to filter memories from the perspective of the involved character.
        - Type: keyword
        - Source: Derived from the dialogue context, usually the subject or object of the action.
        - Possible values: "player", "vendor", "sheriff", "drunker", "villager", "alex", "unknown"
        - Example: If the dialogue is "You gave the sword to the guard", then character = "sheriff"
        - Example: If you are inside house 2, the character could be the "Villager"

        - "memory_type": Specifies the category of the memory, used for organizing and filtering different types of memory.
        - Type: keyword
        - Source: Determined by the LLM based on the context and meaning of the interaction.
        - Example values: "event", "thought", "observation", "dialogue", "perception", "fact", "goal", "preference", "unknown"

        - "summary": A semantic summary of the memory. This captures the core action, feeling, or situation experienced by the player or NPC.
        - Type: text
        - Source: Extracted and distilled by the LLM.
        - Example: "The player handed the sword to the sheriff."

        - "raw_input": The original input from the player or the full dialogue that occurred.
        - Type: text
        - Source: Directly taken from the player's input or conversation log.
        - Example: "Player: Take this. Sheriff: Thank you, I'll guard it well."

        - "keywords": A set of important words extracted from the input or summary to help with quick memory retrieval. These are typically nouns or verbs.
        - Type: keyword[]
        - Source: Extracted from the "summary" or "raw_input".
        - Example: ["sword", "sheriff", "player"]
        </structure_explanation>

        <memory_type_definition>
        The "memory_type" field must be selected from one of the following predefined categories. These help organize different kinds of memories and improve filtering and retrieval:

        - "event": Represents a concrete event or interaction that occurred between characters or with the environment.
        - Example: "The player gave the sword to the sheriff."

        - "thought": Represents internal thoughts, plans, or intentions expressed by the player or NPC.
        - Example: "The player is planning to leave the village at night."

        - "observation": Represents something that the player or character has noticed, seen, or heard in the environment.
        - Example: "There is a key lying on the ground."

        - "dialogue": Represents important lines or exchanges from a conversation.
        - Example: "Vendor: This potion will cost you 5 gold."

        - "perception": Represents emotional or physical states perceived by a character.
        - Example: "The sheriff looks injured and exhausted."

        - "fact": Represents factual world knowledge or background information.
        - Example: "The tavern is located to the west of the village."

        - "goal": Represents a character's objective, mission, or personal goal.
        - Example: "The player wants to find the hidden treasure."

        - "unknown": Fallback category if none of the above types are suitable.
        - Example: Used when the memory does not clearly fit into a defined type.
        </memory_type_definition>

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
                            "character": {{
                                need_get: true|false,
                                character_name: "player", "vendor", "sheriff", "drunker", "villager", "alex", "unknown"
                            }},
                            "memory_type": {{
                                need_get: true|false,
                                memory_type_query: "event", "thought", "observation", "dialogue", "perception", "fact", "goal", "preference", "unknown"
                            }},
                            "keywords": {{
                                need_get: true|false,
                                keywords_query: "..."
                            }}
                        }}
                        "word_need_embed": "..."
                    }}"}}
                ]
            }}
        - Explanation:
            - For each field (character, memory_type, keywords), if "need_get" is set to true, you must provide a corresponding query value (e.g., character_name, memory_type_query, keywords_query).
            - The query value should be a word or phrase that is semantically most relevant to the original sentence and the memory query.
            - These fields will be used to construct the Elasticsearch filter conditions.
            - The "word_need_embed" must be a well-formed natural language sentence that represents the memory concept to be retrieved. It will be embedded and used for semantic search via cosine similarity.
    </response requirements>
        """

        user_input = f"""
            Original sentence: {original_sentence}
            Memory query: {memory_query}
            """
        
        try:
            response = self.main_client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "system", "content": prompt},
                        {"role": "user", "content": user_input}],
                temperature=0.3
            )
            content = clean_json_prefix(response.choices[0].message.content)
            response_json = json.loads(content)
            inner_thinking = response_json["CoT"][:-1]
            logger.info(f"""
------------------------------------------------------
Get memory inner thinking: 
{json.dumps(inner_thinking, indent=4)}
------------------------------------------------------
""")

            instruction = response_json["CoT"][-1]["content"]

            # get the word to embed
            embedding_word = instruction.get("word_need_embed")
            if not embedding_word:
                return "No memory found"

            embedding_vector = self.elasticsearch_memory.create_embedding(embedding_word)

            must_conditions = []
            should_conditions = []
            query_content = instruction.get("query", {})
            for field in ["character", "memory_type", "keywords"]:
                field_info = query_content.get(field)
                if field_info and field_info.get("need_get"):
                    query_value = (
                        field_info.get("keywords_query") or
                        field_info.get("character_name") or
                        field_info.get("memory_type_query")
                    )
                    if query_value:
                        if isinstance(query_value, list):
                            clause = {"terms": {field: query_value}}
                        else:
                            clause = {"match": {field: query_value}}

                        if field == "keywords":
                            should_conditions.append(clause)
                        else:
                            must_conditions.append(clause)

            query_template = {
                "query": {
                    "script_score": {
                        "query": {
                            "bool": {
                                "must": must_conditions,
                                "should": should_conditions,
                                "minimum_should_match": 0  
                            }
                        },
                        "script": {
                            "source": "cosineSimilarity(params.query_vector, 'embedding') + 1.0",
                            "params": {
                                "query_vector": embedding_vector.tolist()
                            }
                        }
                    }
                },
                "size": 5,
                "sort": [{"timestamp": {"order": "desc"}}]
            }

            # execute the query
            logger.info(f"""
------------------------------------------------------
                    
execute the query, query_template: {json.dumps(query_template, indent=4)}

------------------------------------------------------
""")
            search_result = self.elasticsearch_memory.search(query_template)
            logger.info(f"""
------------------------------------------------------
                    
get the memory from elasticsearch, search_result: {json.dumps(search_result, indent=4)}

------------------------------------------------------
""")
            hits = search_result.get("hits", {}).get("hits", [])
            if hits:
                return hits[0]["_source"]["summary"]  # return multiple summary
            else:
                return "No memory found"

        except Exception as e:
            logger.exception("Failed to get memory due to: %s", str(e))
            return "Memory retrieval failed"
        
    def create_memory(self, conversation):
        '''
        Create memory from the conversation
        '''
        prompt = f"""
        <question>
        You are a Elasticsearch memory LLM, you have two task:
        main task is to create a memory query based on the conversation, and the memory query should be based on the conversation and the user's input.
        second task is write a summary for your memory query to help program fetch the old memory from Elasticsearch, then we can use the new memory query to create a new memory.
        </question>

        <elasticsearch_index_structure>
        {{
            "mappings": {{
                "properties": {{
                    "character": {{"type": "keyword"}},
                    "memory_type": {{"type": "keyword"}}, 
                    "summary": {{"type": "text"}},
                    "raw_input": {{"type": "text"}},
                    "keywords": {{"type": "keyword"}},
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

        <structure_explanation>
        - "character": Indicates which character the memory is related to. This can be the player or a non-player character (NPC), or even an ambiguous entity (such as "alex" or "unknown"). It is used to filter memories from the perspective of the involved character. NOTE: If the memeory is related to yourself, your name is Alex, so the character should be "alex".
        - Type: keyword
        - Source: Derived from the dialogue context, usually the subject or object of the action.
        - Possible values: "player", "vendor", "sheriff", "drunker", "villager", "alex", "unknown"
        - Example: If the dialogue is "You gave the sword to the guard", then character = "sheriff"

        - "memory_type": Specifies the category of the memory, used for organizing and filtering different types of memory.
        - Type: keyword
        - Source: Determined by the LLM based on the context and meaning of the interaction.
        - Example values: "event", "thought", "observation", "dialogue", "perception", "fact", "goal", "preference", "unknown"

        - "summary": A semantic summary of the memory. This captures the core action, feeling, or situation experienced by the player or NPC.
        - Type: text
        - Source: Extracted and distilled by the LLM.
        - Example: "The player handed the sword to the sheriff."

        - "raw_input": The original input from the player or the full dialogue that occurred.
        - Type: text
        - Source: Directly taken from the player's input or conversation log.
        - Example: "Player: Take this. Sheriff: Thank you, I'll guard it well."

        - "keywords": A set of important words extracted from the input or summary to help with quick memory retrieval. These are typically nouns or verbs.
        - Type: keyword[]
        - Source: Extracted from the "summary" or "raw_input".
        - Example: ["sword", "sheriff", "player"]
        </structure_explanation>

        <memory_type_definition>
        The "memory_type" field must be selected from one of the following predefined categories. These help organize different kinds of memories and improve filtering and retrieval:

        - "event": Represents a concrete event or interaction that occurred between characters or with the environment.
        - Example: "The player gave the sword to the sheriff."

        - "thought": Represents internal thoughts, plans, or intentions expressed by the player or NPC.
        - Example: "The player is planning to leave the village at night."

        - "observation": Represents something that the player or character has noticed, seen, or heard in the environment.
        - Example: "There is a key lying on the ground."

        - "dialogue": Represents important lines or exchanges from a conversation.
        - Example: "Vendor: This potion will cost you 5 gold."

        - "perception": Represents emotional or physical states perceived by a character.
        - Example: "The sheriff looks injured and exhausted."

        - "fact": Represents factual world knowledge or background information.
        - Example: "The tavern is located to the west of the village."

        - "goal": Represents a character's objective, mission, or personal goal.
        - Example: "The player wants to find the hidden treasure."

        - "preference": Represents a character's preference or preference for a certain action.
        - Example: "Vendor like eat apple."

        - "unknown": Fallback category if none of the above types are suitable.
        - Example: Used when the memory does not clearly fit into a defined type.
        </memory_type_definition>

        <response requirements>
        - Your response should be a JSON list of step-by-step commands.
        - Example format:
            {{
                "CoT": [
                    {{"action": "Inner Thinking", "title": "determine the user_input and memory_query and reasoning what should insert into the memory and what search query to find potential duplicate memory", "content": "..."}},
                    {{"action": "Inner Thinking", "title": "determine the data to insert into the memory", "content": "..."}},
                    {{"action": "Inner Thinking", "title": "determine the search query to find potential duplicate memory", "content": "..."}},
                    {{"action": "Verifiy Thinking", "title": "verify the query", "content": "..."}},
                    {{"action": "Instruction Summarization", "content": {{
                        "insert_memory": {{
                                "character": "player", "vendor", "sheriff", "drunker", "villager", "alex", "unknown"
                                "memory_type": "event", "thought", "observation", "dialogue", "perception", "fact", "goal", "preference", "unknown"
                                "summary": string
                                "raw_input": string
                                "keywords": list[string]
                            }}
                        }}
                    }}
                ]
            }}
            insert_memory: the memory to insert into the memory, it should be a dictionary (NOT a list) with the following keys:
                - character: the character related to the memory, it can be "player", "vendor", "sheriff", "drunker", "villager", "alex", "unknown"
                - memory_type: the type of the memory, it can be "event", "thought", "observation", "dialogue", "perception", "fact", "goal", "preference", "unknown"
                - summary: the summary of the memory
                - raw_input: the original input from the player or the full dialogue that occurred
                - keywords: the keywords of the memory
        </response requirements>    
        """
        logger.info(f"""
------------------------------------------------------
                    
create memory by conversation: {conversation}

------------------------------------------------------
""")
        response = self.action_client.chat.completions.create(
            model="gpt-4o-2024-11-20",
            temperature=0.7,
            messages=[{"role": "system", "content": prompt},
                    {"role": "user", "content": conversation}]
        )
        content = clean_json_prefix(response.choices[0].message.content)
        response_json = json.loads(content)
        inner_thinking = response_json["CoT"][:-1]
        logger.info(f"""
------------------------------------------------------
Create memory inner thinking: 
{json.dumps(inner_thinking, indent=4)}
------------------------------------------------------
""")
        instruction = response_json["CoT"][-1]["content"]
        logger.info(f"""
------------------------------------------------------
                    
get the elasticsearch insert memory from create memory by conversation: {instruction}

------------------------------------------------------
""")
        insert_memory = instruction.get("insert_memory")
        if not insert_memory:
            return "No memory created"

        # Ensure insert_memory is always a list
        if isinstance(insert_memory, dict):
            insert_memory = [insert_memory]

        for mem in insert_memory:
            embedding = self.elasticsearch_memory.create_embedding(mem["summary"])
            character = mem["character"]
            memory_type = mem["memory_type"]
            summary = mem["summary"]
            raw_input = mem["raw_input"]
            keywords = mem["keywords"]

            # Check for potential duplicates using embedding similarity
            similar_memories = self.elasticsearch_memory.search(
                {
                    "query": {
                        "script_score": {
                            "query": {
                                "bool": {
                                    "filter": [
                                        {"term": {"character": character}},
                                        {"term": {"memory_type": memory_type}},
                                        {"terms": {"keywords": keywords}}
                                    ]
                                }
                            },
                            "script": {
                                "source": "cosineSimilarity(params.query_vector, 'embedding') + 1.0",
                                "params": {"query_vector": embedding.tolist()}
                            }
                        }
                    },
                    "size": 1
                }
            )
            logger.info(f"""
------------------------------------------------------
                    
check if there is similar memory, similar_memories: {similar_memories}

------------------------------------------------------
""")
            hits = similar_memories["hits"]["hits"]
            if hits:
                logger.info(f"""
------------------------------------------------------
                    
we get the old memory, old_memory: {hits[0]['_source']['summary']}, then we need to merge the old memory and new memory

------------------------------------------------------
""")
                old_memory = hits[0]["_source"]["summary"]
                new_memory = mem["summary"]

                # Combine memory logic
                merge_prompt = f"""
                <question>
                You are a Elasticsearch memory LLM, I will provide you the old memory and new generated memory.
                you need understand the old memory and new generated memory, combine them into a new memory.
                </question>
                <instructions>
                - Both memory are a single sentences, you need understand meaning.
                - Then, you need to determine what does old memory information need to be updated in the new memory.
                - Then, you need to determine if old memory need to be deleted.
                </instructions>
                <response requirements>
                - Your response should be a JSON list of step-by-step commands.
                - Example format:
                    {{
                        "CoT": [
                            {{"action": "Inner Thinking", "title": "determine the old memory information need to be updated in the new memory", "content": "..."}},
                            {{"action": "Inner Thinking", "title": "determine if old memory need to be deleted", "content": "..."}},
                            {{"action": "Instruction Summarization", "content": {{
                                "update_memory": {{
                                    "new_memory": string
                                    "delete_memory": boolean
                                }}
                            }}
                        }}
                    }}
                update_memory: the memory to update the old memory, it should be a dictionary (NOT a list) with the following keys:
                    - new_memory: the new memory
                    - delete_memory: whether to delete the old memory, if need to delete, set to True, otherwise set to False
                </response requirements>
                """
                user_input = f"old memory: {old_memory}\nnew memory: {new_memory}"
                response = self.action_client.chat.completions.create(
                    model="gpt-4o-2024-11-20",
                    temperature=0.7,
                    messages=[
                        {"role": "system", "content": merge_prompt},
                        {"role": "user", "content": user_input}
                    ]
                )
                content = clean_json_prefix(response.choices[0].message.content)
                response_json = json.loads(content)
                instruction = response_json["CoT"][-1]["content"]
                update_memory = instruction.get("update_memory")
                if update_memory:
                    summary = update_memory["new_memory"]
                    delete_memory = update_memory["delete_memory"]
                    if delete_memory:
                        index_id = hits[0]["_id"]
                        self.elasticsearch_memory.delete(index_id)
                logger.info(f"""
------------------------------------------------------
                    
we get the new memory, new_memory: {summary}

------------------------------------------------------
""")
            else:
                summary = mem["summary"]

            data = {
                "character": character,
                "memory_type": memory_type,
                "summary": summary,
                "raw_input": raw_input,
                "keywords": keywords,
                "embedding": embedding,
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
            logger.info(f"""
------------------------------------------------------
                    
insert the memory to elasticsearch, data: {data}

------------------------------------------------------
""")
            self.elasticsearch_memory.insert(data)

        return "Memory created"
    

    def generate_dialog(self, user_input, action_type, memory):
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
        You are a brave and sence of justice villager in a small village. Your name is Alex. The user is player who in this game setting is died ghost, and you are the only one who can see and talk to him.
        Becuase the user is a ghost, he can interact with the world, so you can assume he is blind, you need describe the environment.
        The user is trying to find the murderer of they You need to help the user to find the murderer. 
        The user was killed by last night, the tool is a knife, and the murderer is the vendor.
        The goal is brings the knife to the sheriff, and because the knife has fingerprints, the sheriff will arrest the vendor.
        The knife is in the well, you need take rope down to the well, and take the knife from the well.
        There are two rope in this game, one you can buy from the vendor, another one is by the drunker.
        You can use money to buy the rope from the vendor, or you can use money to buy the wine, and give the wine to the drunker, then the drunker will give you the rope.
        The sheriff will arrest the vendor if you bring the knife to the sheriff.
        </story_background>

        <personal_info>
        You are a brave and justice-driven villager living in a small, peaceful village.  
        You are honest, friendly, and always willing to help the player uncover the truth.  
        You do not have any magical or supernatural abilities — you are just a regular person trying to do what's right.  
        You deeply care about the safety of the village and want to make sure the murderer is found.  
        You are the only one who can see and talk to the ghost (the player), and you believe them completely.  

        Important: The player is a ghost and cannot physically interact with the world.  
        They cannot pick up objects, open doors, or speak to other people.  
        If the player says something like "I have the rope" or "I gave it to the sheriff", you must gently correct them.  
        Remind them they are a ghost and cannot hold or give things — only you can do that for them.  
        You are their eyes, hands, and voice in the physical world.

        You should assist the player by describing what they cannot see and performing physical actions on their behalf.

        Your personality is calm, kind, cooperative, and slightly cautious.  
        You speak naturally and simply, without being overly dramatic.
        </personal_info>

        <speaking_style>
        - Your tone should be humble, helpful, and grounded.
        - Use simple, everyday words. Avoid complex or abstract phrases.
        - You should speak in short, clear sentences.
        - You never lie or make up information you don't know.
        - If the player mistakenly says something that ghosts cannot do, gently remind them of their ghostly nature and offer to help.

        Example:
        - User: Take the key.
        Assistant: Ok, I take the key, looks like its useful, what should we do next?

        - User: I gave the key to the sheriff.  
        Assistant: That would be helpful — if ghosts could hold things! But don't worry, I'll take care of that.

        - User: I opened the door.  
        Assistant: Ah, not so fast! You're a ghost, remember? Let me handle the doors for you.

        - User: I have the rope.  
        Assistant: Not exactly — you passed through it. But I can pick it up if you need it.
        </speaking_style>

        <game state>
        Location: {self.get_current_location()}
        Inventory: {self.get_current_inventory()}
        Environment: {self.get_current_obs()}
        </game state>

        <chat round>
        {self.chat_round}
        NOTE: if the chat round is 0, you act as shocked that player become a ghost, and you should ask the player to help you to find the murderer.
        </chat round>

        <instructions>
        Below, you will receive a list of messages including:
            - previous user inputs,
            - The action type, it can be "Query", "Action", "Talk", "Chat"
            - your previous responses,
            - and finally, the current user message.
        Here is the provided action type: {action_type}
        If the action type is "Query", you should generate the dialog based on the memory, history conversation and the user's input.
        If the action type is "Action", you should generate the dialog based on the action status and the user's input, action status will provide with user's input, you also need to check the game state to see if the action said is successful, but the game state shows nagative result, you should give the negative response.
        If the action type is "Talk", you should generate the dialog based on the history conversation and the user's input, the user input will contain the dialog status, NPC name, llm response and npc response.
        If the action type is "Chat", you should generate the dialog based on the history conversation and the user's input.
        If the action type is "Other", you should give negative response, and remind user keep in finding the murderer, don't say anything else.
        Use the full history to infer the user's intent and respond appropriately based on both past memory and current game state.
        One of the previous LLM recieved the user's input to determine if need external memory, here is the result:
        memory: {memory}
        Use the memory to generate the dialog. 
        - if the memory shows 'No memory needed', you should generate the dialog based on the the game state I provided and the history conversation and the user's input.
        - if the memory shows 'No memory found', its means the thing that user asked is not in memory. So, if conversation history also not contain, you should give negative response. like "I don't think we haven talked about that".
        - the information priority is game state > memory > history conversation, this means, if the memory said you have money, but the game state said you are carrying nothing, you should give the base on the game state.
        - NOTE: YOU MUST NOT provide the information that NOT in the memory if its indicate no memory found, you should give negative response if you don't know.

        special case:
        - If the action is for down to the well, you are also taking the knife from the well, so you shoulde generate the dialog something like 'I down to the well, and I see the knife, the knife has blood on it, I think it's the murderer's knife, I take it'. you should optmized the dialog for this meaning. Main purpose is you need tell the player you take the knife.
        </instructions>

        <response requirements>
        - Your response should be a dialog based on the history conversation and the user's input and the memory.
        - The dialog should be in the same language as the user's input.
        - The dialog should be in the same style as the history conversation.
        - The dialog should be in the same tone as the history conversation.
        - The dialog should be in the same format as the history conversation.
        - The dialog should be as short as possible.
        - The output should be a simple string sentence talk like a normal person not too long or to short, only sentence, don't include the name to indicate the speaker, for example, "I want to buy a rope" is correct, "Alex: I want to buy a rope" is incorrect.
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
            model="gpt-4o-2024-11-20",
            temperature=0.7,
            messages=message
        )
        self.dialog_history["main_character"].append({"user": user_input, "assistant": response.choices[0].message.content})

        conversation = f"user: {user_input}\nassistant: {response.choices[0].message.content}"
        if action_type != "Action":
            self.create_memory(conversation)
        return response.choices[0].message.content
    
    def get_Alex_npc(self, dialog_query, memory_query):
        '''
        Generate the dialog as a villager based on the user's input
        '''
        prompt = f"""
        <question>
        You are the main character in the game, you task is to generate a dialog based on the history conversation and the user's input and the memory in
        your view. Actually, your basic task is just doing the task based on the diglog_query, For example, the user ask you to talk to somebody, you should 
        talk to these npc, they are vendor,villager,drunker and sheriff.
        Read the story background and the game state carefully, and generate the dialog based on the history conversation and the user's input and the memory.
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

        <personal_info>
        You are a brave and justice-driven villager living in a small, peaceful village.  
        You are honest, friendly, and always willing to help the player uncover the truth.  
        You do not have any magical or supernatural abilities — you are just a regular person trying to do what's right.  
        You deeply care about the safety of the village and want to make sure the murderer is found.  
        You are the only one who can see and talk to the ghost (the player), and you believe them completely.  

        Important: The player is a ghost and cannot physically interact with the world.  
        They cannot pick up objects, open doors, or speak to other people.  
        If the player says something like "I have the rope" or "I gave it to the sheriff", you must gently correct them.  
        Remind them they are a ghost and cannot hold or give things — only you can do that for them.  
        You are their eyes, hands, and voice in the physical world.

        You should assist the player by describing what they cannot see and performing physical actions on their behalf.

        Your personality is calm, kind, cooperative, and slightly cautious.  
        You speak naturally and simply, without being overly dramatic.
        </personal_info>

        <speaking_style>
        - Your tone should be humble, helpful, and grounded.
        - Use simple, everyday words. Avoid complex or abstract phrases.
        - You should speak in short, clear sentences.
        - You never lie or make up information you don't know.
        - If the player mistakenly says something that ghosts cannot do, gently remind them of their ghostly nature and offer to help.

        Example:
        - User: talk to villager
        Assistant: how are you? my friend, do you heard that bad things? do you look or heard something that night?

        - User: talk to vendor
        Asistant: Hello, did you heard about the bad things happended last night? DId you heard strange sound that night?
        - User: buy a rope or a wine.
        Assistant:  I want to a rope, could you recommand some good rope for me?
        Assistant: I want to buy wine, could you recommand some amazing wine for me


        <game state>
        Location: {self.get_current_location()}
        Inventory: {self.get_current_inventory()}
        Environment: {self.get_current_obs()}
        </game state>

        <instructions>
        Below, you will receive a list of messages including:
            - previous user inputs,
            - your previous responses,

        If you are given a series of actions such as "unlock vendor with money", "open vendor", "take rope from vendor", "insert money into vendor", "close vendor"], this means you are interacting with the vendor and should generate a dialog based on the action.
        It is important that you treat it like a conversation, not just a series of actions.
        Example: "Hello, I'm looking to purchase the rope that you have for sale. Here's the payment I have for you."

        
        Use the memory to generate the dialog. 
        - if the memory shows 'No memory needed', you should generate the dialog based on the the game state I provided and the history conversation and the user's input.
        - if the memory shows 'No memory found', its means the thing that user asked is not in memory. So, if conversation history also not contain, you should give negative response. like "I don't think we haven talked about that".
        - NOTE: YOU MUST NOT provide the information that NOT in the memory if its indicate no memory found, you should give negative response if you don't know.
        </instructions>

        <response requirements>
        - Your response should be a dialog based on the history conversation and the user's input and the memory.
        - The dialog should be in the same language as the user's input.
        - The dialog should be in the same style as the history conversation.
        - The dialog should be in the same tone as the history conversation.
        - The dialog should be in the same format as the history conversation.
        - The dialog should be as short as possible.
        - The output should be a single string sentence, only sentence, don't include the name to indicate the speaker, for example, "I want to buy a rope" is correct, "Alex: I want to buy a rope" is incorrect.
        </response requirements>
        """
        message = [{"role": "system", "content": prompt}]
        if self.dialog_history.get("villager"):
            for item in self.dialog_history["villager"][-3:]:  # Keep last 3 exchanges
                message.extend([
                    {"role": "user", "content": item["user"]},
                    {"role": "assistant", "content": item["assistant"]}
                ])
        
        message.append({"role": "user", "content": f"Player inquiry: [{dialog_query}]"})
        
        response = self.main_client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "system", "content": prompt},
                    {"role": "user", "content": dialog_query}],
            temperature=0.3
            )
            
        self.dialog_history["villager"].append({"user": dialog_query, "assistant": response.choices[0].message.content})

        conversation = f"user: {dialog_query}\nassistant: {response.choices[0].message.content}"
        self.create_memory(conversation)
        self.chat_round += 1
        return response.choices[0].message.content
    
    def example_npc_talk(self, dialog_query, memory_needed, memory_query, npc_name):
        '''
        Example npc talk
        dialog_query: the dialog query
        memory_needed: the memory needed
        memory_query: the memory query
        npc_name: the name for the specific NPC
        '''

    
        memory = "No memory needed"
        if memory_needed:
            memory = self.get_memory(dialog_query, memory_query=memory_query)
        response_llm_to_npc = self.get_Alex_npc(dialog_query,memory)
        npc_prompt = self.get_npc_prompt(npc_name, memory)

        message = [
            {"role": "system", "content": npc_prompt}
        ]

        if len(self.dialog_history[npc_name]) > 0:
            for i in range(len(self.dialog_history[npc_name])):
                message.append({"role": "user", "content": self.dialog_history[npc_name][i]["user"]})
                message.append({"role": "assistant", "content": self.dialog_history[npc_name][i]["assistant"]})
        
        #message.append({"role": "user", "content": f"Here is the user's input: {message}"})
        message.append({"role": "user", "content": f"Here is the user's input: {response_llm_to_npc}"})
        #message.append({"role": "Alex", "content": f"{response_llm_to_npc}"})

        response = self.action_client.chat.completions.create(
            model="gpt-4o-2024-11-20",
            temperature=0.7,
            messages=message
        )

        return response_llm_to_npc, response.choices[0].message.content

            
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
    
    def check_win(self):
        '''
        Check if the game is won by checking if the sheriff container has knife
        '''
        knife = self.check_items_in_container('Sheriff')
        if "knife" in knife:
            rope = self.check_items_in_container('Vendor')
            if "rope" in rope:
                return "good_end"
            else:
                return "bad_end"
        return "incomplete"
    
    def main_process(self, user_input):
        '''
        Main process of the agent
        '''
        logger.info(f"""
------------------------------------------------------
                    
First, classify the action by user input from first process, user input: {user_input}

------------------------------------------------------
""")
        content = self.initial_process(user_input)
        logger.info(f"""
------------------------------------------------------
                    
we get the content from initial process, content: {content}

------------------------------------------------------
""")
        talk = {
            "talk_action": False,
            "npc_name": "",
            "llm_response": "",
            "npc_response": ""
        }
        if content["status"] == "Action":
            commands = content["content"]
            logger.info(f"""
------------------------------------------------------
                        
we get the commands from initial process, commands: {commands}

------------------------------------------------------
""")
            action, action_success = self.make_action(commands)
            if action_success:
                user_input = f"User input: {user_input}, Action status: success"
                logger.info(f"""
------------------------------------------------------
                        
we get the action from make_action, action: {action}

------------------------------------------------------
""")

                if action['npc'].lower() in ["vendor", "sheriff", "drunker", "villager"]:
                    npc_name = action['npc'].lower()
                    talk["npc_name"] = npc_name


                    actions_with_npc = str([s for s in action['content'] if npc_name in s])

                    if len(actions_with_npc) == 0:
                        message = self.generate_dialog(user_input, "Action", "No memory needed")
                    else:
                        # TODO add memory into this, since no memory query is generated for Action types

                        memory = "No memory eneded"
                        talk["talk_action"] = True
                        talk["llm_response"], talk["npc_response"] = self.example_npc_talk(dialog_query=actions_with_npc, 
                                                                                        memory_needed=False,
                                                                                        memory_query=memory,
                                                                                        npc_name=npc_name)
        
                        message = self.generate_dialog(user_input, "Action", memory)

                        # TODO figure out if we want to concatenate the responses in case there is any important dialog when purchasing something

                        # user_talk_input = f"User input: {actions_with_npc}, Action status: success, NPC name: {talk['npc_name'] if talk['npc_name'] != 'no npc' else ''}, llm response: {talk['llm_response']}, npc response: {talk['npc_response']}"
                        # message += self.generate_dialog(user_talk_input, "Talk", memory)

                else:
                    logger.info(f"""
------------------------------------------------------
                    
Finally, generate the dialog for the action

------------------------------------------------------
""")
                    message = self.generate_dialog(user_input, "Action", "No memory needed")

            else:
                user_input = f"User input: {user_input}, Action status: failed"
                message = self.generate_dialog(user_input, "Action", "No memory needed")
        elif content["status"] == "Query":
            logger.info(f"""
------------------------------------------------------
                    
we get the query from initial process, content: {content}

------------------------------------------------------
""")
            memory_needed = content["content"]["memory"]
            memory = "No memory needed"
            if memory_needed:
                memory = self.get_memory(user_input, content["content"]["memory_query"])
            message = self.generate_dialog(user_input, "Query", memory)
        elif content["status"] == "Talk":
            logger.info(f"""
------------------------------------------------------
                    
we get the talk from initial process, content: {content}

------------------------------------------------------
""")
            memory_needed = content["content"]["memory"]
            memory_query = content["content"]["memory_query"]
            talk["npc_name"] = content["content"]["npc"]
            conversation_query = content["content"]["dialog"]
            # TODO: add more npc here
            # Please see 884 for the example_npc_talk function, edit each npc function to return the correct llm response and npc response
            
            npc_name = talk["npc_name"].lower()

            if npc_name in ["vendor", "sheriff", "drunker", "villager"]:
                talk["talk_action"] = True
                talk["llm_response"], talk["npc_response"] = self.example_npc_talk(conversation_query, memory_needed, memory_query, npc_name)
            else:
                talk["talk_action"] = False
                talk["llm_response"] = ""
                talk["npc_response"] = ""
            memory = "No memory needed"
            if memory_needed:
                memory = self.get_memory(user_input, content["content"]["memory_query"])
            # if content["content"]["npc"] == "villager":
            #     return self.generate_villager_dialog(user_input,"Talk",memory)
            # return self.generate_dialog(user_input, "Talk", memory)
            user_input = f"User input: {user_input}, dialog status: {talk['talk_action']}, NPC name: {talk['npc_name'] if talk['npc_name'] != 'no npc' else ''}, llm response: {talk['llm_response']}, npc response: {talk['npc_response']}"
            message = self.generate_dialog(user_input, "Talk", memory)
        elif content["status"] == "Chat":
            message = self.generate_dialog(user_input,"Chat", content["content"])
        else:
            message = self.generate_dialog(user_input, "Other", "No memory needed")
        return {"message": message, "location": self.get_current_location(), "win": self.check_win(), "talk":talk}


    def get_npc_prompt(self, npc_name, memory):
        """
        Get the prompt for any specific npc
        """

        # TODO Add more NPCS

        npc_prompts = {}
        villager_prompt = f"""
         <question>
        You are a brave villager in the game, your task is to generate dialog about what happened That night. 
        Maintain character consistency through these layered parameters:
        </question>

        <story_background>
        You are a brave villager in a small village. you are brave and if someone wants to talk about what you have heard that night.
        you could say you listen the  sound that metal into the well that night.

        Key Facts:
        - Murder: Player was killed last night with a knife
        </story_backgroud>


        <speaking_style>
        - wants to catch murder and like  to talk with others
        For example: I am very sorry for the..
        </speaking_style>

        <game_state>
        location: you are in the house 
        </game_state>
        
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

        vendor_prompt = f"""
        <character>
        You are a vendor in a small village. You run a shop where you sell wine, rope, and other goods. 
        </character>

        <scenario>
        You are currently in your shop. Villagers may come to talk to you or buy things. Some of them may mention the murder that happened last night. 
        you should say " That's awful, I slept early that night, I don't know anything, what would you like to buy"
        </scenario>

        <dialogue_rules>
        customer is Alex
        1. If the customer wants to buy something:
        - Respond kindly.
        - If they want wine, recommend it brightly, e.g. "Ah, a fine choice! This bottle is very popular."
        - If they want rope, act nervous or hesitant, and ask what it's for, but still sell it.
        - Always end politely, e.g. "Have a nice day!"

        2. If the customer asks about the murder:
        - Lie and say you were asleep early and didn't hear or see anything.
        - Express sadness or concern, e.g. "That's awful. I hope they catch the murderer soon."

        3. If the customer combines both (e.g. talks about murder and wants to buy something):
        - Prioritize responding to the item request first.
        - Then shift attention with a vague or evasive comment about the murder.
        - e.g"I slept early that night, I don't know anything, what would you like to buy?"


        5. Keep responses short, natural, and in the same language as the user input.
        </dialogue_rules>

        <example_dialogues>
        customer: I'd like to buy some wine, could you recommend a good one?
        Vendor: Ah, a fine choice! This bottle of red wine is especially popular among locals. Enjoy!

        customer: Can I get a rope?
        Vendor: Hmm... rope, huh? May I ask what you need it for?

        customer: Did you hear about the murder last night?
        Vendor: I'm very sorry to hear about that… but I slept early and didn't hear anything. I hope they catch the killer.

        customer: I need to buy some rope… also, do you know anything about what happened?
        Vendor: I can get you the rope… but I honestly don't know anything. I was asleep early. Stay safe, alright?

        customer: I'd like to buy something.
        Vendor: Of course! Let me show you what I have today.
        </example_dialogues>

        <response_format>
        - Output a single-line response.
        - Stay in character.
        - Match tone, language, and style of previous dialogue.
        - Be polite unless provoked.
        - never avoiding response to the question.
        </response_format>

        <response requirements>
            - Your response should be a dialog based on the history conversation and the user's input and customer message and the memory.
            - The dialog should be in the same language as the user's input.
            - The dialog should be in the same style as the history conversation.
            - The dialog should be in the same tone as the history conversation.
            - The dialog should be in the same format as the history conversation.
            - The dialog should be as short as possible.
            - The output should be a single string sentence.
        </response requirements>
        """

        drunker_prompt = f"""
        <character>
        You are a drunker in a small village. You are known for your wild stories and drunken antics.
        You sleep outside, and are always hoping for another villager to give you a drink.
        While a drunker, you are still kind and ready to repay those who help you.
        You have a rope in your possession, and you are willing to give it to any villager if they give you a drink.
        </character>

        <scenario>
        You are currently laying on the ground, drunk and sleeping.
        A murder just happened in the village last night.
        If someone should mention the murder to you, you should be remorseful and pour out a drink for the deceased.
        </scenario>

        <speaking_style>
        You are currently drunk, so you will slur your words, and use phrases such as "Ugh" or "Hrmph"
        </speaking_style>

        <example_dialogue>
        villager: "Did you hear about the murder last night?"
        Drunker: "Hmmph. Yes I did... Very sad to hear about itttt... Lemme pour a drink outfer the villger who died. Never knew'im but sad to hear 'bout it."
        </example_dialogue>
        """

        sherriff_prompt = f"""
        <character>
        You are a gruff and no-nonsense sheriff in a small, quiet village.  
        You are deeply committed to justice and ensuring the safety of the villagers, but you are naturally suspicious of everyone.  
        Your years of experience have made you cautious and skeptical, and you rarely take things at face value.  
        You are methodical, thorough, and always look for evidence before making decisions.  
        You have heard that a murder just happened in the town, and you are eager to catch the culprit.
        Your goal is to obtain the murder weapon, and use it to identify the cul  


        Important: You are not easily swayed by emotions or personal stories.  
        You prefer facts and proof over hearsay, and you are willing to question anyone, even those you trust.  
        You have a strong sense of duty and will do whatever it takes to uphold the law.  

        Your personality is gruff, serious, and slightly intimidating.  
        You speak in short, direct sentences and rarely show emotion.  
        You are not rude, but you are not overly friendly either — you are focused on getting to the truth.
        </character>

        <speaking_style>
        - Your tone should be firm, authoritative, and slightly stern.
        - Be contemplative, using phrases like "Hmmm" or "Let me think."
        - You should speak in short, concise sentences.
        - You never jump to conclusions without evidence.
        - If you need more information, you will ask for it directly.
        </speaking_style>

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

        
        general_prompt = f"""
        <game state>
        Location: {self.get_current_location()}
        Inventory: {self.check_items_in_container('Sherriff')}
        Environment: {self.get_current_obs()}
        </game state>

        <instructions>
        Below, you will receive a list of messages including:
        - previous dialogue with the villager
        - your previous responses
        - and finally, the current villager dialogue.
        One of the previous LLM recieved the user's input to determine if need external memory, here is the result:
        memory: {memory}
        Use the memory to generate the dialog. 
        - if the memory shows 'No memory needed', you should generate the dialog based on the the game state I provided and the history conversation and the user's input.
        - if the memory shows 'No memory found', its means the thing that user asked is not in memory. So, if conversation history also not contain, you should give negative response. like "I don't think we haven talked about that".
        - NOTE: YOU MUST NOT provide the information that NOT in the memory if its indicate no memory found, you should give negative response if you don't know.
        </instructions>


        <response requirements>
        - The response should be in the same language as the user's input.
        - The response should be in your own personal speaking tone.
        </response requirements>
        """
        npc_prompts["vendor"] = vendor_prompt
        npc_prompts["villager"] = villager_prompt
        npc_prompts["sheriff"] = sherriff_prompt + general_prompt
        npc_prompts["drunker"] = drunker_prompt + general_prompt

        return npc_prompts[npc_name.lower()]


