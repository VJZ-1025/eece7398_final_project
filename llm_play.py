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
        logger.info(f"Connected to Elasticsearch cluster: {es.info()}")
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
            logger.info(f"Existing index '{self.index_name}' deleted.")
        
        self.es.indices.create(index=self.index_name, body=self.mapping)
        logger.info(f"Index '{self.index_name}' created.")

    def create_embedding(self, text):
        return self.model.encode(text, show_progress_bar=False)
    
    def search(self, query_template):
        return self.es.search(index=self.index_name, body=query_template)
    
    def insert(self, data):
        return self.es.index(index=self.index_name, body=data)






def clean_json_prefix(json_str):
    return json_str.replace("```json", "").replace("```", "")

class LLM_Agent:
    def __init__(self):
        self.game_file = "./textworld_map/village_game.z8"
        self.es = Elasticsearch(ES_HOST)
        self.elasticsearch_memory = ElasticsearchMemory(self.es)
        self.action_client = OpenAI(api_key=OPENAI_API_KEY)
        self.main_client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")
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
        self.chat_round = 0
    def reset_game(self):
        self.obs, self.infos = self.env.reset()
        self.done = False
    
    def initial_process(self, user_input):
        """
        Main LLM for user communication
        """
        logger.info("Initial process...")
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
            - if the conversation based on the memory, you should set memory to true, else you should set memory to false
            - if the memory is true, you should set memory_query to the memory query, else you should set memory_query to ""
            - content format: {{"npc": "villager|Sheriff|Drunker|Vendor","dialog": "<a short description of the dialog>", "memory": true|false, "memory_query": "<a short description of the memory query>"}}
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
        logger.info('debug: initial_process 183')
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
                            {{"action": "Verifiy Thinking", "title": "Simulate the command check the result", "content": "..."}},
                            {{"action": "Instruction Summarization", "status": "approved|rejected|confused", "content": ["...command 1", "...command 2"]}}
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
                            {{"action": "Verifiy Thinking", "title": "Simulate the command check the result", "content": "The command is correct. 'go north' moves the player from Home to School, and 'go north' moves the player from School to shop, then unlock vendor with money, open vendor, take rope from vendor, insert money into vendor, close vendor."}},
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
        - "character": Indicates which character the memory is related to. This can be the player or a non-player character (NPC), or even an ambiguous entity (such as "yourself" or "unknown"). It is used to filter memories from the perspective of the involved character.
        - Type: keyword
        - Source: Derived from the dialogue context, usually the subject or object of the action.
        - Possible values: "player", "vendor", "sheriff", "drunker", "villager", "yourself", "unknown"
        - Example: If the dialogue is "You gave the sword to the guard", then character = "sheriff"

        - "memory_type": Specifies the category of the memory, used for organizing and filtering different types of memory.
        - Type: keyword
        - Source: Determined by the LLM based on the context and meaning of the interaction.
        - Example values: "event", "thought", "observation", "action", "dialogue", "perception"

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
                                character_name: "..."
                            }},
                            "memory_type": {{
                                need_get: true|false,
                                memory_type_query: "..."
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
            logger.info("LLM returned query reasoning: %s", response_json)
            pprint(response_json)
            instruction = response_json["CoT"][-1]["content"]

            # get the word to embed
            embedding_word = instruction.get("word_need_embed")
            if not embedding_word:
                logger.warning("No word to embed returned from LLM.")
                return "No memory found"

            embedding_vector = self.elasticsearch_memory.create_embedding(embedding_word)

            # build the query template
            query_template = {
                "query": {
                    "bool": {
                        "must": [],
                        "should": [
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
                "size": 5,  # can be changed based on the need
                "sort": [{"timestamp": {"order": "desc"}}]
            }

            # add the structured field filter
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
                            query_template["query"]["bool"]["must"].append({
                                "terms": {field: query_value}
                            })
                        else:
                            query_template["query"]["bool"]["must"].append({
                                "match": {field: query_value}
                            })

            # execute the query
            logger.info('debug: query_template 541')
            logger.info(query_template)
            search_result = self.elasticsearch_memory.search(query_template)
            logger.info('debug: search_result 541')
            logger.info(search_result)
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
        - "character": Indicates which character the memory is related to. This can be the player or a non-player character (NPC), or even an ambiguous entity (such as "yourself" or "unknown"). It is used to filter memories from the perspective of the involved character.
        - Type: keyword
        - Source: Derived from the dialogue context, usually the subject or object of the action.
        - Possible values: "player", "vendor", "sheriff", "drunker", "villager", "yourself", "unknown"
        - Example: If the dialogue is "You gave the sword to the guard", then character = "sheriff"

        - "memory_type": Specifies the category of the memory, used for organizing and filtering different types of memory.
        - Type: keyword
        - Source: Determined by the LLM based on the context and meaning of the interaction.
        - Example values: "event", "thought", "observation", "action", "dialogue", "perception"

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
                                "character": string
                                "memory_type": string
                                "summary": string
                                "raw_input": string
                                "keywords": list[string]
                            }},
                            "search_query": string
                        }}
                    }}
                ]
            }}
            insert_memory: the memory to insert into the memory, it should be a dictionary (NOT a list) with the following keys:
                character: the character related to the memory, it can be "player", "vendor", "sheriff", "drunker", "villager", "yourself", "unknown"
                memory_type: the type of the memory, it can be "event", "thought", "observation", "action", "dialogue", "perception", "fact", "goal", "unknown"
                summary: the summary of the memory
                raw_input: the original input from the player or the full dialogue that occurred
            keywords: the keywords of the memory
            search_query: the search query to find potential duplicate memory, it should a single sentence
        </response requirements>    
        """

        response = self.action_client.chat.completions.create(
            model="gpt-4o-2024-11-20",
            temperature=0.7,
            messages=[{"role": "system", "content": prompt},
                    {"role": "user", "content": conversation}]
        )
        content = clean_json_prefix(response.choices[0].message.content)
        logger.info(content)
        response_json = json.loads(content)
        pprint(response_json)
        instruction = response_json["CoT"][-1]["content"]
        insert_memory = instruction.get("insert_memory")
        search_query = instruction.get("search_query")
        if insert_memory:
            character = insert_memory["character"]
            memory_type = insert_memory["memory_type"]
            summary = insert_memory["summary"]
            raw_input = insert_memory["raw_input"]
            keywords = insert_memory["keywords"]
            embedding = self.elasticsearch_memory.create_embedding(summary)
            data = {
                "character": character,
                "memory_type": memory_type,
                "summary": summary,
                "raw_input": raw_input,
                "keywords": keywords,
                "embedding": embedding,
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
            self.elasticsearch_memory.insert(data)
            return "Memory created"
        else:
            return "No memory created"
    
    def generate_dialog(self, user_input, action_type, memory):
        '''
        Generate the dialog as a villager based on the user's input
        '''
        logger.info(f"Generating dialog with memory: {self.obs}")
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
        If the action type is "Action", you should generate the dialog based on the action status and the user's input, action status will provide with user's input.
        If the action type is "Talk", you should generate the dialog based on the history conversation and the user's input.
        If the action type is "Chat", you should generate the dialog based on the history conversation and the user's input.
        If the action type is "Other", you should give negative response, and remind user keep in finding the murderer, don't say anything else.
        Use the full history to infer the user's intent and respond appropriately based on both past memory and current game state.
        One of the previous LLM recieved the user's input to determine if need external memory, here is the result:
        memory: {memory}
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
            model="gpt-4o-2024-11-20",
            temperature=0.7,
            messages=message
        )
        logger.info('debug: generate_dialog 812')
        logger.info(response.choices[0].message.content)
        self.dialog_history["main_character"].append({"user": user_input, "assistant": response.choices[0].message.content})

        conversation = f"user: {user_input}\nassistant: {response.choices[0].message.content}"
        self.create_memory(conversation)
        self.chat_round += 1
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
    
    def check_win(self):
        '''
        Check if the game is won by checking if the sheriff container has knife
        '''
        items = self.check_items_in_container('Sheriff')
        return 'knife' in items
    
    def main_process(self, user_input):
        '''
        Main process of the agent
        '''
        content = self.initial_process(user_input)
        if content["status"] == "Action":
            commands = content["content"]
            action = self.make_action(commands)
            if action:
                user_input = f"User input: {user_input}, Action status: success"
                return self.generate_dialog(user_input, "Action", "No memory needed")
            else:
                user_input = f"User input: {user_input}, Action status: failed"
                return self.generate_dialog(user_input, "Action", "No memory needed")
        elif content["status"] == "Query":
            memory_needed = content["content"]["memory"]
            memory = "No memory needed"
            if memory_needed:
                memory = self.get_memory(user_input, content["content"]["memory_query"])
            return self.generate_dialog(user_input, "Query", memory)
        elif content["status"] == "Talk":
            memory_needed = content["content"]["memory"]
            memory = "No memory needed"
            if memory_needed:
                memory = self.get_memory(user_input, content["content"]["memory_query"])
            return self.generate_dialog(user_input, "Talk", memory)
        elif content["status"] == "Chat":
            return self.generate_dialog(user_input,"Chat", content["content"])
        else:
            return self.generate_dialog(user_input, "Other", "No memory needed")


