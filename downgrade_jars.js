/**
 * downgrade_jars.js
 *
 * Downgrades .class files inside JAR archives from Java 21 (class version 65)
 * to Java 17 (class version 61) so they can run on CheerpJ.
 *
 * This only changes the version stamp in the class file header.
 * The actual bytecode is untouched — safe for typical Swing/AWT games.
 *
 * Usage: node downgrade_jars.js
 */

const AdmZip = require("adm-zip");
const fs = require("fs");
const path = require("path");

const GAMES_DIR = "./games";
const OUTPUT_DIR = "./games-jdk17";
const TARGET_MAJOR_VERSION = 61; // Java 17

// Java version mapping for display
const VERSION_MAP = {
  45: "Java 1.1",
  46: "Java 1.2",
  47: "Java 1.3",
  48: "Java 1.4",
  49: "Java 5",
  50: "Java 6",
  51: "Java 7",
  52: "Java 8",
  53: "Java 9",
  54: "Java 10",
  55: "Java 11",
  56: "Java 12",
  57: "Java 13",
  58: "Java 14",
  59: "Java 15",
  60: "Java 16",
  61: "Java 17",
  62: "Java 18",
  63: "Java 19",
  64: "Java 20",
  65: "Java 21",
  66: "Java 22",
  67: "Java 23",
};

function getJavaVersion(major) {
  return VERSION_MAP[major] || `Unknown (class version ${major})`;
}

// Create output directory
if (!fs.existsSync(OUTPUT_DIR)) {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
}

const jarFiles = fs.readdirSync(GAMES_DIR).filter((f) => f.endsWith(".jar"));

if (jarFiles.length === 0) {
  console.log("No .jar files found in", GAMES_DIR);
  process.exit(1);
}

console.log(
  `Found ${jarFiles.length} JAR file(s). Downgrading to ${getJavaVersion(TARGET_MAJOR_VERSION)}...\n`,
);

let totalModified = 0;
let totalSkipped = 0;

jarFiles.forEach((file) => {
  const inputPath = path.join(GAMES_DIR, file);
  const outputPath = path.join(OUTPUT_DIR, file);

  console.log(`📦 Processing: ${file}`);

  try {
    const zip = new AdmZip(inputPath);
    const entries = zip.getEntries();
    let modified = 0;
    let skipped = 0;
    let originalVersion = null;

    entries.forEach((entry) => {
      if (!entry.entryName.endsWith(".class")) return;

      const data = entry.getData();

      // Verify CAFEBABE magic bytes
      if (data.length < 8) return;
      if (
        data[0] !== 0xca ||
        data[1] !== 0xfe ||
        data[2] !== 0xba ||
        data[3] !== 0xbe
      )
        return;

      // Read major version (bytes 6-7, big-endian)
      const majorVersion = (data[6] << 8) | data[7];

      if (originalVersion === null) {
        originalVersion = majorVersion;
      }

      if (majorVersion > TARGET_MAJOR_VERSION) {
        // Write new major version
        data[6] = (TARGET_MAJOR_VERSION >> 8) & 0xff;
        data[7] = TARGET_MAJOR_VERSION & 0xff;
        // Reset minor version to 0
        data[4] = 0;
        data[5] = 0;
        entry.setData(data);
        modified++;
      } else {
        skipped++;
      }
    });

    zip.writeZip(outputPath);

    const fromVersion = originalVersion
      ? getJavaVersion(originalVersion)
      : "N/A";
    console.log(
      `   ✅ ${modified} classes downgraded (${fromVersion} → ${getJavaVersion(TARGET_MAJOR_VERSION)}), ${skipped} already OK`,
    );
    console.log(`   → Saved to: ${outputPath}`);

    totalModified += modified;
    totalSkipped += skipped;
  } catch (err) {
    console.error(`   ❌ Error processing ${file}: ${err.message}`);
  }

  console.log();
});

console.log("═".repeat(50));
console.log(
  `Done! ${totalModified} classes downgraded, ${totalSkipped} already compatible.`,
);
console.log(`Output folder: ${OUTPUT_DIR}/`);
console.log(
  `\nNext step: Update your website to point to games-jdk17/ instead of games/`,
);
