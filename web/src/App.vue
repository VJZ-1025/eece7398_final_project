<template>
  <div class="app">
    <header class="header">
      <h1>TextWorld Chat</h1>
    </header>
    <main class="main">
      <ChatWindow />
    </main>
  </div>
</template>

<script>
import ChatWindow from './components/ChatWindow.vue'

export default {
  name: 'App',
  components: {
    ChatWindow
  }
}
</script>

<style>
.app {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background-color: #343541;
  color: white;
}

.header {
  padding: 1rem;
  text-align: center;
  background-color: #444654;
  border-bottom: 1px solid #565869;
}

.main {
  flex: 1;
  overflow: hidden;
}

* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen,
    Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif;
}
</style> 