<template>
  <div class="game-flow">
    <!-- Start Screen -->
    <div v-if="currentScreen === 'start'" class="screen start-screen">
      <h1>Welcome to the Village Adventure</h1>
      <button @click="nextScreen" class="start-button">Start Game</button>
    </div>

    <!-- Story Background Screen -->
    <div v-if="currentScreen === 'story'" class="screen story-screen">
      <div class="story-content">
        <h2>You are died</h2>
        <p>On a peaceful evening, you were sleeping in your bed as usual. Suddenly, a chill swept over you, and you felt powerless—everything went black. You had died.</p>
        <p>You became a ghost. You shouted loudly, but soon realized you couldn't do anything—you had no way to interact with the world around you.</p>
        <p>Suddenly, you realized that your friend, Alex, seemed to notice you. You began to say to him:</p>
      </div>
      <button @click="nextScreen" class="next-button">Continue</button>
    </div>
  </div>
</template>

<script>
import { useDataStore } from '../DataStore'

export default {
  name: 'GameFlow',
  setup() {
    const store = useDataStore()
    return { store }
  },
  data() {
    return {
      currentScreen: 'start'
    }
  },
  methods: {
    nextScreen() {
      if (this.currentScreen === 'start') {
        this.currentScreen = 'story'
      } else if (this.currentScreen === 'story') {
        this.store.setCurrentWindow('ChatWindow')
      }
    }
  }
}
</script>

<style scoped>
.game-flow {
  height: 100vh;
  width: 100vw;
  background-color: #343541;
  color: white;
  display: flex;
  flex-direction: column;
}

.screen {
  flex: 1;
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 2rem;
}

.start-screen {
  text-align: center;
}

.start-screen h1 {
  font-size: 2.5rem;
  margin-bottom: 2rem;
}

.story-screen {
  text-align: center;
  max-width: 800px;
  margin: 0 auto;
}

.story-content {
  margin-bottom: 2rem;
}

.story-content h2 {
  font-size: 2rem;
  margin-bottom: 1.5rem;
}

.story-content p {
  font-size: 1.2rem;
  line-height: 1.6;
  margin-bottom: 1rem;
}

.start-button, .next-button {
  padding: 0.75rem 1.5rem;
  background-color: #19c37d;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-weight: bold;
  font-size: 1.1rem;
  transition: background-color 0.3s ease;
}

.start-button:hover, .next-button:hover {
  background-color: #15a76c;
}
</style>