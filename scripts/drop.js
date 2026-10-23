// Drop database script for the tectora database.
// Run with: mongosh "mongodb://localhost:27020/?directConnection=true" drop.js

use("tectora");

db.dropDatabase();
