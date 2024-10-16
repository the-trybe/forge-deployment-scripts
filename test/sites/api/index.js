// Import the express module
const express = require('express');
require("dotenv").config();

// Create an instance of express
const app = express();

// Define a port number
const PORT = process.env.PORT || 3000;
const name = process.env.NAME;
// Define a route handler for the default home page
app.get('/', (req, res) => {
  res.send(`Hello ${name}!`);
});

// Start the server and listen on the specified port
app.listen(PORT, () => {
  console.log(`Server is running on http://localhost:${PORT}`);
});
