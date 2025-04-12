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
    r11 = gm.new_room(name="Shop", desc="A store, vendor is here, he is selling wine and rope.") 
    r12 = gm.new_room(name="Village Committee", desc="A place where villagers gather to discuss community affairs.")
    r13 = gm.new_room(name="Hospital", desc="Provides medical services to villagers.")

    # Middle row (Row2)
    r21 = gm.new_room(name="School", desc="Where children receive their education.")
    r22 = gm.new_room(name="Center Park", desc="A peaceful park with a mysterious well in the center.")
    r23 = gm.new_room(name="Sheriff Office", desc="Responsible for maintaining village security, sheriff is here.")

    # Bottom row (Row3)
    r31 = gm.new_room(name="Home", desc="Cozy home, but player died here, has blood on the floor.")
    r32 = gm.new_room(name="House", desc="Another resident's home, helpful villager live here.")
    r33 = gm.new_room(name="Forest", desc="A forest, a drunker is lying on the ground.")

    # --- 2. Establish connections between rooms ---
    # Horizontal connections (East-West)
    gm.connect(r11.east, r12.west)  # Shop -> Village Committee
    gm.connect(r12.east, r13.west)  # Village Committee -> Hospital
    gm.connect(r21.east, r22.west)  # School -> Park
    gm.connect(r22.east, r23.west)  # Park -> Sheriff's Office
    gm.connect(r31.east, r32.west)  # Home -> House
    gm.connect(r32.east, r33.west)  # House -> Forest

    # Vertical connections (North-South)
    gm.connect(r11.south, r21.north)  # Village Committee -> School
    gm.connect(r12.south, r22.north)  # Shop -> Park
    gm.connect(r13.south, r23.north)  # Sheriff's Office -> Hospital
    gm.connect(r21.south, r31.north)  # School -> Home
    gm.connect(r22.south, r32.north)  # Park -> House
    gm.connect(r23.south, r33.north)  # Hospital -> Forest

    # --- 3. Add interactive objects ---
    # Add the Sheriff character
    sheriff = gm.new('c', 'Sheriff', "A stern-looking law enforcement officer")
    sheriff.add_property('open')
    r23.add(sheriff)  # Add sheriff to the Sheriff's Office

    # Add a locked well in the Park
    well = gm.new('c', 'Well', "A well in the center of the village")
    well.add_property('open')
    r22.add(well)

    # add vendor
    vendor = gm.new('c', 'Vendor', "A vendor selling goods")
    vendor.add_property('locked')
    r11.add(vendor)

    # Add a rope that can be used with the well
    rope1 = gm.new('o', 'rope', "a rope")
    vendor.add(rope1)

    # add wine
    wine = gm.new('k', 'wine', "a bottle of wine")
    vendor.add(wine)

    # add knife
    knife = gm.new('o', 'knife', "a sharp knife, with blood on it, finger prints shows it's vendor's")
    well.add(knife)

    # money
    money = gm.new('k', 'money', "a bag of money")
    gm.add_fact("match", money, vendor)
    r31.add(money)

    #drunker
    drunker = gm.new('c', 'Drunker', "a drunker lying on the ground")
    drunker.add_property('locked')
    gm.add_fact("match", wine, drunker)
    rope2 = gm.new('o', 'rope', "a rope")
    drunker.add(rope2)
    r33.add(drunker)

    gm.set_player(r31)
    # Build and save the game

    # quest_commands = [
    #     "go east"
    # ]
    # gm.set_quest_from_commands(quest_commands)
    
    game = gm.build()
    gm.compile(output_file)

    #add helpful villager
    Villager = gm.new('c','Helpful villager live in house ','A helpful villager willing to share information') 
    r32.add(Villager)
    
    return game, gm

if __name__ == "__main__":
    # Only run this if the file is run directly (not imported)
    game, gm = generate_village_map()
    print(f"Game saved as village_game.z8")
    print(f"You can play it by typing: tw-play village_game.z8")