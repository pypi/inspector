/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./inspector/templates/**/*.{html,js}",
    "./inspector/templates/*.html"
  ],
  theme: {
    extend: {
      colors: {
        'python-blue': '#3776AB',
        'python-yellow': '#FFD43B',
        'python-blue-dark': '#2D5E8B',
        'python-blue-light': '#4E8DC8',
        'python-yellow-dark': '#FFCA00',
        'python-yellow-light': '#FFE57F',
      },
      fontFamily: {
        'mono': ['ui-monospace', 'SFMono-Regular', 'Consolas', 'Liberation Mono', 'Menlo', 'monospace'],
      }
    },
  },
  plugins: [],
}