import { defineStore } from 'pinia'

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
  }
})