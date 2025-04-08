<template>
  <div class="game-end-container" v-if="showEnding">
    <div class="ending-content">
      <h2 class="ending-title">{{ endingTitle }}</h2>
      <div class="ending-text">{{ endingText }}</div>
      <button @click="handleNext" class="next-button">Next</button>
    </div>
  </div>
</template>

<script>
export default {
  name: 'GameEnd',
  props: {
    gameStatus: {
      type: String,
      default: 'incomplete'
    }
  },
  computed: {
    showEnding() {
      return this.gameStatus === 'good_end' || this.gameStatus === 'bad_end'
    },
    endingTitle() {
      return this.gameStatus === 'good_end' ? 'Good Ending' : 'Bad Ending'
    },
    endingText() {
      if (this.gameStatus === 'good_end') {
        return 'After you handed the knife to the sheriff, he quickly deduced that the vendor was the true murderer. Without hesitation, the sheriff confronted and arrested the culprit. Justice was served, and peace returned to the village.'
      } else if (this.gameStatus === 'bad_end') {
        return 'When you handed the knife to the sheriff, he quickly identified the vendor as the killer. But the vendor wasn’t careless — he remembered selling you the rope and sensed that you were onto him. Before the sheriff could act, the vendor vanished without a trace.'
      }
      return ''
    }
  },
  methods: {
    handleNext() {
      this.$emit('next')
    }
  }
}
</script>

<style scoped>
.game-end-container {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.8);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 1000;
}

.ending-content {
  background-color: #343541;
  padding: 2rem;
  border-radius: 8px;
  max-width: 600px;
  text-align: center;
}

.ending-title {
  color: #19c37d;
  font-size: 2rem;
  margin-bottom: 1rem;
}

.ending-text {
  color: white;
  font-size: 1.2rem;
  line-height: 1.6;
  margin-bottom: 2rem;
}

.next-button {
  padding: 0.75rem 2rem;
  background-color: #19c37d;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-weight: bold;
  font-size: 1.1rem;
}

.next-button:hover {
  background-color: #15a76c;
}
</style> 