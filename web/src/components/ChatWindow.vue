<template>
  <div class="chat-container">
    <!-- Left side: Chat Window -->
    <div class="chat-window">
      <div class="chat-messages" ref="messagesContainer">
        <div v-for="(message, index) in messages" :key="index" 
             :class="['message', message.role]">
          <div class="message-content">
            <div class="message-text">{{ message.content }}</div>
          </div>
        </div>
        <div v-if="isLoading" class="message assistant">
          <div class="message-content">
            <div class="loading-circle"></div>
          </div>
        </div>
      </div>
      <div class="input-container">
        <textarea 
          v-model="userInput"
          @keydown.enter.prevent="sendMessage"
          placeholder="Type your command here..."
          rows="1"
          class="input-field"
        ></textarea>
        <button @click="sendMessage" class="send-button" :disabled="isLoading">Send</button>
      </div>
    </div>

    <!-- Right side: Game Map -->
    <div class="game-map">
      <div class="map-container">
        <div class="map-grid">
          <!-- Top row -->
          <div class="map-cell shop" :class="{ current: currentLocation === 'Shop' }">Shop</div>
          <div class="map-cell village-committee" :class="{ current: currentLocation === 'Village Committee' }">Village Committee</div>
          <div class="map-cell hospital" :class="{ current: currentLocation === 'Hospital' }">Hospital</div>
          
          <!-- Middle row -->
          <div class="map-cell school" :class="{ current: currentLocation === 'School' }">School</div>
          <div class="map-cell center-park" :class="{ current: currentLocation === 'Center Park' }">Center Park</div>
          <div class="map-cell sheriff" :class="{ current: currentLocation === 'Sheriff Office' }">Sheriff Office</div>
          
          <!-- Bottom row -->
          <div class="map-cell house1" :class="{ current: currentLocation === 'Home' }">Home</div>
          <div class="map-cell house2" :class="{ current: currentLocation === 'House' }">House</div>
          <div class="map-cell forest" :class="{ current: currentLocation === 'Forest' }">Forest</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import axios from 'axios'
import { useDataStore } from '../DataStore'

export default {
  name: 'ChatWindow',
  setup() {
    const store = useDataStore()
    return { store }
  },
  data() {
    return {
      messages: [],
      isLoading: false,
      userInput: ''
    }
  },
  computed: {
    currentLocation() {
      return this.store.currentLocation
    }
  },
  methods: {
    async sendMessage() {
      if (!this.userInput.trim()) return

      // Add user message to chat
      this.messages.push({
        role: 'user',
        content: this.userInput
      })

      const userMessage = this.userInput
      this.userInput = ''
      this.isLoading = true

      try {
        // Send request to backend
        const response = await axios.post('http://localhost:8000/chat', {
          user_input: userMessage
        })

        // Add assistant response to chat
        this.messages.push({
          role: 'assistant',
          content: response.data.message
        })

        // Update current location if it's in the response
        if (response.data.location) {
          this.store.setCurrentLocation(response.data.location)
        }
      } catch (error) {
        console.error('Error:', error)
        this.messages.push({
          role: 'assistant',
          content: 'Sorry, there was an error processing your command.'
        })
      } finally {
        this.isLoading = false
      }

      // Scroll to bottom after message is added
      this.$nextTick(() => {
        this.scrollToBottom()
      })
    },
    scrollToBottom() {
      const container = this.$refs.messagesContainer
      container.scrollTop = container.scrollHeight
    }
  }
}
</script>

<style scoped>
.chat-container {
  display: flex;
  height: 100%;
  gap: 1rem;
  padding: 1rem;
}

.chat-window {
  flex: 1;
  display: flex;
  flex-direction: column;
  background-color: #343541;
  border-radius: 8px;
  min-width: 0; /* 防止flex子元素溢出 */
}

.game-map {
  flex: 1;
  background-color: #343541;
  border-radius: 8px;
  padding: 1rem;
  min-width: 0;
  display: flex;
  align-items: flex-start;
  justify-content: center; /* 改回居中对齐 */
  padding-top: 2rem;
  padding-left: 25%; /* 添加左侧内边距，使地图整体向右偏移 */
}

.map-container {
  width: 100%;
  display: flex;
  align-items: flex-start;
  justify-content: center; /* 改回居中对齐 */
}

.map-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  grid-template-rows: repeat(3, 1fr);
  gap: 0.5rem;
  width: 100%;
  aspect-ratio: 1;
  max-width: 400px; /* 减小最大宽度 */
}

.map-cell {
  background-color: #444654;
  border: 1px solid #565869;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 0.5rem;
  font-size: 0.9rem; /* 稍微减小字体 */
  color: white;
  transition: all 0.3s ease;
}

.map-cell:hover {
  background-color: #565869;
  transform: scale(1.05);
}

/* 添加当前位置高亮效果 */
.map-cell.current {
  background-color: #19c37d;
  border-color: #15a76c;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 1rem;
}

.message {
  margin-bottom: 1rem;
  padding: 1rem;
}

.message.user {
  background-color: #343541;
}

.message.assistant {
  background-color: #444654;
}

.message-content {
  max-width: 800px;
  margin: 0 auto;
}

.input-container {
  padding: 1rem;
  background-color: #444654;
  border-top: 1px solid #565869;
  display: flex;
  gap: 1rem;
}

.input-field {
  flex: 1;
  padding: 0.75rem;
  border-radius: 4px;
  border: 1px solid #565869;
  background-color: #40414f;
  color: white;
  resize: none;
  font-family: inherit;
}

.send-button {
  padding: 0.75rem 1.5rem;
  background-color: #19c37d;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-weight: bold;
}

.send-button:hover {
  background-color: #15a76c;
}

.send-button:disabled {
  background-color: #666;
  cursor: not-allowed;
}

.loading-circle {
  width: 24px;
  height: 24px;
  border: 3px solid #565869;
  border-top: 3px solid #19c37d;
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin: 0 auto;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}
</style> 