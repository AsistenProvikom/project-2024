const fs = require("fs");
const path = require("path");

const gamesDir = "./games-jdk17";
const imagesDir = "./images";
const outputDir = "./data";

if (!fs.existsSync(outputDir)) fs.mkdirSync(outputDir);

const files = fs.readdirSync(gamesDir);
const games = [];

files.forEach((file) => {
  if (file.endsWith(".jar")) {
    const base = path.basename(file, ".jar");
    const imagePath = `${imagesDir}/${base}.png`;
    games.push({
      name: base.charAt(0).toUpperCase() + base.slice(1),
      file: `${gamesDir}/${file}`,
      image: fs.existsSync(imagePath) ? imagePath : `${imagesDir}/default.png`,
    });
  }
});

fs.writeFileSync(`${outputDir}/games.json`, JSON.stringify(games, null, 2));
console.log("✅ games.json generated!");
