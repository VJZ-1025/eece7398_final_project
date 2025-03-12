import textworld.gym
from textworld import gym
from textworld import EnvInfos

# Specify your game file
game_file = "village_game.z8"
# Request admissible_commands and facts information
infos = EnvInfos(admissible_commands=True, facts=True)
env_id = textworld.gym.register_games([game_file], request_infos=infos, max_episode_steps=None)
print("Registered environment id:", env_id)
env = gym.make(env_id)

obs, infos = env.reset()
done = False

# TODO: This while loop should be modified to use an LLM agent instead of human input
# The game contains NPCs (non-player characters) like:
# - Sheriff (indicated by type 'c' in textWorldMap.py)
# These containers/NPCs can hold items and interact with the player

while not done:
    # Display current observation and available actions
    print("Current observation:")
    print(obs)
    
    # Get current game facts list
    facts = infos.get("facts", [])
    print("\nCurrent facts:")
    for fact in facts:
        if "in(knife: o, Sheriff: c)" in str(fact):
            print("knife given to sheriff, game over")
            done = True
    

    if done:
        break
    # Display available actions and wait for player input
    print("\nAvailable actions:")
    print(infos.get("admissible_commands", []))
    action = input("Please enter your action: ").strip()
    
    obs, reward, done, infos = env.step(action)

print("Game Over!")