<template>
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
</template>

<script>
import axios from 'axios'

export default {
  name: 'ChatWindow',
  data() {
    return {
      messages: [],
      userInput: '',
      isLoading: false
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
.chat-window {
  height: 100%;
  display: flex;
  flex-direction: column;
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