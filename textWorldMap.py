import textworld
from textworld import GameMaker

def generate_village_map(output_file="./village_game.z8"):
    """
    Generates a village-themed text world map with rooms and objects.
    
    Args:
        output_file (str): Path where the game file should be saved. Defaults to './village_game.z8'
    
    Returns:
        tuple: (game, game_maker) - The created game and GameMaker instances
    """
    # Create GameMaker instance
    gm = GameMaker()

    # --- 1. Create 9 rooms (3×3 square layout) ---
    # Top row (Row1)
    r11 = gm.new_room(name="Shop", desc="A store with various goods on display.") 
    r12 = gm.new_room(name="Village Committee", desc="A place where villagers gather to discuss community affairs.")
    r13 = gm.new_room(name="Hospital", desc="Provides medical services to villagers.")

    # Middle row (Row2)
    r21 = gm.new_room(name="School", desc="Where children receive their education.")
    r22 = gm.new_room(name="Central Square", desc="The heart of the village, with an ancient well in the center.")
    r23 = gm.new_room(name="Police Station", desc="Responsible for maintaining village security.")

    # Bottom row (Row3)
    r31 = gm.new_room(name="House 1", desc="A typical resident's home.")
    r32 = gm.new_room(name="House 2", desc="Another resident's home.")
    r33 = gm.new_room(name="Forest", desc="A forest dangerous for villagers.")

    # --- 2. Establish connections between rooms ---
    # Horizontal connections (East-West)
    gm.connect(r11.east, r12.west)  # Shop -> Village Committee
    gm.connect(r12.east, r13.west)  # Village Committee -> Hospital
    gm.connect(r21.east, r22.west)  # School -> Central Square
    gm.connect(r22.east, r23.west)  # Central Square -> Police Station
    gm.connect(r31.east, r32.west)  # House 1 -> House 2
    gm.connect(r32.east, r33.west)  # House 2 -> Forest

    # Vertical connections (North-South)
    gm.connect(r11.south, r21.north)  # Village Committee -> School
    gm.connect(r12.south, r22.north)  # Shop -> Central Square
    gm.connect(r13.south, r23.north)  # Police Station -> Hospital
    gm.connect(r21.south, r31.north)  # School -> House 1
    gm.connect(r22.south, r32.north)  # Central Square -> House 2
    gm.connect(r23.south, r33.north)  # Hospital -> Forest

    # --- 3. Add interactive objects ---
    # Add a well at the central square
    well = gm.new("c", name="well", desc="An ancient well. You might need a rope to explore it.")
    gm.add_fact("in", well, r22)

    # Add a treasure in the well
    treasure = gm.new("o", name="treasure", desc="A mysterious ancient treasure!")
    gm.add_fact("in", treasure, well)

    # Add a rope in the forest
    rope = gm.new("o", name="rope", desc="A strong rope that could be useful.")
    gm.add_fact("in", rope, r33)
    gm.add_fact("takeable", rope)

    # Make the well require the rope to access
    gm.add_fact("locked", well)
    gm.add_fact("match", rope, well)

    # Set player's starting position at House 1
    gm.set_player(r31)
    # Create a win condition when player has the treasure
    gm.add_fact("winnable", treasure)
    gm.add_fact("winning", treasure)
    quest_commands = [
        "Go north"
    ]
    gm.set_quest_from_commands(quest_commands)
    # Build and save the game
    game = gm.build()
    gm.compile(output_file)
    
    return game, gm

if __name__ == "__main__":
    # Only run this if the file is run directly (not imported)
    game, gm = generate_village_map()
    print(f"Game saved as village_game.z8")
    print(f"You can play it by typing: tw-play village_game.z8")