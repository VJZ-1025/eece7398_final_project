<template>
  <div id="app">
    <header class="header">
      <div class="header-content">
        <h1>TextWorld Chat</h1>
      </div>
    </header>
    <div class="header-content" style="margin-top: 1rem">
      <button v-if="store.currentWindow === 'ChatWindow'" 
              @click="store.setCurrentWindow('GameFlow')" 
              class="back-button">
        Back to Home
      </button>
    </div>
    <GameFlow v-if="store.currentWindow === 'GameFlow'" />
    <ChatWindow v-if="store.currentWindow === 'ChatWindow'" />
  </div>
</template>

<script>
import GameFlow from './components/GameFlow.vue'
import ChatWindow from './components/ChatWindow.vue'
import { useDataStore } from './DataStore'

export default {
  name: 'App',
  components: {
    GameFlow,
    ChatWindow
  },
  setup() {
    const store = useDataStore()
    return { store }
  }
}
</script>

<style>
#app {
  font-family: Arial, sans-serif;
  height: 100vh;
  display: flex;
  flex-direction: column;
  background-color: #343541;
  color: white;
}

.header {
  padding: 1rem;
  background-color: #444654;
  border-bottom: 1px solid #565869;
}

.header-content {
  display: flex;
  align-items: center;
  max-width: 1200px;
  margin: 0 auto;
  width: 100%;
}

.back-button {
  margin-right: 2rem;
  padding: 0.5rem 1rem;
  background-color: #565869;
  border: none;
  border-radius: 4px;
  color: white;
  cursor: pointer;
}

.back-button:hover {
  background-color: #676980;
}

h1 {
  margin: 0 auto;
}

* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  margin: 0;
  padding: 0;
  background-color: #343541;
  color: white;
}

.title {
  text-align: center;
  padding-top: 20px;
}

</style>