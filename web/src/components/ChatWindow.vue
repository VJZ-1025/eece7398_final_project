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
          :disabled="isGameEnded"
        ></textarea>
        <button v-if="!isGameEnded" @click="sendMessage" class="send-button" :disabled="isLoading">Send</button>
        <button v-else @click="handleNext" class="next-button">Next</button>
      </div>
    </div>

    <!-- Right side: Game Map and Dialogue -->
    <div class="right-panel">
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

      <!-- Dialogue Display -->
      <div class="dialogue-container">
        <div class="dialogue-content">
          <div class="dialogue-header">
            <span class="speaker">NPC Dialogue</span>
          </div>
          <div class="dialogue-text">
            <template v-if="dialogue.talk">
              <div v-for="(item, index) in dialogue.history" :key="index">
                <div class="llm-response">
                  <span class="speaker-name">Alex:</span> {{ item.llm_response }}
                </div>
                <div class="npc-response">
                  <span class="speaker-name">{{ item.npc_name }}:</span> {{ item.npc_response }}
                </div>
              </div>
            </template>
            <template v-else>
              <div class="placeholder-text">No active conversation</div>
            </template>
          </div>
        </div>
      </div>
    </div>

    <!-- Game End Overlay -->
    <GameEnd 
      :gameStatus="gameStatus"
      @next="handleNext"
    />
  </div>
</template>

<script>
import axios from 'axios'
import { useDataStore } from '../DataStore'
import GameEnd from './GameEnd.vue'

export default {
  name: 'ChatWindow',
  components: {
    GameEnd
  },
  setup() {
    const store = useDataStore()
    return { store }
  },
  data() {
    return {
      messages: [],
      isLoading: false,
      userInput: '',
      dialogue: {
        talk: false,
        npc_name: '',
        npc_response: '',
        llm_response: '',
        history: []
      },
      gameStatus: 'incomplete'
    }
  },
  computed: {
    currentLocation() {
      return this.store.currentLocation
    },
    isGameEnded() {
      return this.gameStatus === 'good_end' || this.gameStatus === 'bad_end'
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

        // Update game status if it's in the response
        if (response.data.win) {
          this.gameStatus = response.data.win
        }

        // Update current location if it's in the response
        if (response.data.location) {
          this.store.setCurrentLocation(response.data.location)
        }

        // Update dialogue if it's in the response
        if (response.data.talk) {
          // If talk_action is true, add to history
          if (response.data.talk.talk_action) {
            this.dialogue.history.push({
              npc_name: response.data.talk.npc_name,
              npc_response: response.data.talk.npc_response,
              llm_response: response.data.talk.llm_response
            })
            this.dialogue.talk = true
          } else {
            // If talk_action is false, clear history
            this.dialogue.history = []
            this.dialogue.talk = false
          }
        } else {
          // If no talk object, clear history
          this.dialogue.history = []
          this.dialogue.talk = false
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
    handleNext() {
      // Reset game state
      this.gameStatus = 'incomplete'
      this.dialogue.history = []
      this.dialogue.talk = false
      this.messages = []
      // Reset location to Home
      this.store.setCurrentLocation('Home')
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
  min-width: 0; 
}

.game-map {
  flex: 1;
  background-color: #343541;
  border-radius: 8px;
  padding: 1rem;
  min-width: 0;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding-top: 1rem;
  margin-bottom: 420px;
}

.map-container {
  width: 100%;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding: 1rem;
}

.map-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  grid-template-rows: repeat(3, 1fr);
  gap: 0.5rem;
  width: 100%;
  max-width: 300px;
  aspect-ratio: 1;
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
  font-size: clamp(0.7rem, 1.2vw, 0.9rem);
  color: white;
  transition: all 0.3s ease;
  word-break: break-word;
  overflow: hidden;
}

.map-cell:hover {
  background-color: #565869;
  transform: scale(1.05);
}

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

.right-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 1rem;
  position: relative;
}

.dialogue-container {
  background-color: #343541;
  border-radius: 8px;
  padding: 1rem;
  margin-top: 1rem;
  min-height: 400px;
  max-height: 400px;
  overflow-y: auto;
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
}

.dialogue-content {
  background-color: #444654;
  border-radius: 4px;
  padding: 1rem;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.dialogue-header {
  margin-bottom: 0.5rem;
  padding-bottom: 0.5rem;
  border-bottom: 1px solid #565869;
}

.speaker {
  font-weight: bold;
  color: #19c37d;
}

.speaker-name {
  font-weight: bold;
  color: #19c37d;
  margin-right: 0.5rem;
}

.dialogue-text {
  line-height: 1.5;
  color: white;
  flex: 1;
  overflow-y: auto;
  padding-right: 0.5rem;
}

/* Custom scrollbar styles */
.dialogue-text::-webkit-scrollbar,
.dialogue-container::-webkit-scrollbar {
  width: 6px;
}

.dialogue-text::-webkit-scrollbar-track,
.dialogue-container::-webkit-scrollbar-track {
  background: #343541;
  border-radius: 3px;
}

.dialogue-text::-webkit-scrollbar-thumb,
.dialogue-container::-webkit-scrollbar-thumb {
  background: #565869;
  border-radius: 3px;
}

.dialogue-text::-webkit-scrollbar-thumb:hover,
.dialogue-container::-webkit-scrollbar-thumb:hover {
  background: #666;
}

.placeholder-text {
  color: #565869;
  font-style: italic;
  text-align: center;
  padding: 2rem 0;
}

.npc-response {
  color: white;
  margin-bottom: 1rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid #565869;
}

.llm-response {
  color: white;
  margin-bottom: 1rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid #565869;
}

.next-button {
  padding: 0.75rem 1.5rem;
  background-color: #19c37d;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-weight: bold;
}

.next-button:hover {
  background-color: #15a76c;
}

.input-field:disabled {
  background-color: #565869;
  cursor: not-allowed;
}
</style> 