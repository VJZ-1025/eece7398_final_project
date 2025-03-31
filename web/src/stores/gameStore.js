import { defineStore } from 'pinia'

export const useGameStore = defineStore('game', {
  state: () => ({
    messages: [],
    currentLocation: 'Home',
    isLoading: false,
    userInput: ''
  }),

  actions: {
    addMessage(message) {
      this.messages.push(message)
    },

    setCurrentLocation(location) {
      this.currentLocation = location
    },

    setLoading(status) {
      this.isLoading = status
    },

    setUserInput(input) {
      this.userInput = input
    },

    clearUserInput() {
      this.userInput = ''
    }
  }
}) 