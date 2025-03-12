# eece7398_final_project

Current basic idea:

# Village Mystery Game

The goal of this text adventure game is to solve a mystery by finding a knife and delivering it to the Sheriff. Here's the key gameplay elements:

## Core Objective
- Ultimate goal: Give the knife to the Sheriff
- This requires several steps and gathering information from NPCs

## Key Game Flow
1. First, you need money (starts in House 1) to buy a rope from the Vendor
   - The Vendor is initially locked/won't trade
   - Need to learn about the rope's availability through NPC dialogue
   - Must convince an NPC to tell you about the shop's inventory

2. Use the rope to access the Well
   - The Well is initially locked
   - A knife is hidden inside
   - Need to learn about strange sounds at the Well at night through NPC gossip
   - An NPC must be convinced to share what they heard (knife dropping sound)

3. Finally, deliver the knife to the Sheriff
   - Completes the main quest

## Planned NPC Interactions
- NPCs will have conditional dialogue
- Players must engage in conversation and gain trust
- Information is gated behind successful NPC interactions
- Creates a more dynamic and investigative gameplay experience

## Implementation Notes
- Using TextWorld for game engine
- NPCs implemented as containers ('c' type)
- Conditional logic controls NPC dialogue and item accessibility
- LLM integration planned for dynamic NPC conversations
