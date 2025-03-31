import { defineStore } from 'pinia'
import axios from 'axios'

export const useDataStore = defineStore('DataStore', {
  state: () => ({
    currentLocation: 'Home',
    currentWindow: 'GameFlow',
  }),
  actions: {
    setCurrentLocation(location) {
      this.currentLocation = location
    },
    setCurrentWindow(window) {
      this.currentWindow = window
    },
    resetGame() {
      axios.post('http://localhost:8000/reset')
    }
  }
})