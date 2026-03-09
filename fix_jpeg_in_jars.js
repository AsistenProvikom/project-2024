/**
 * fix_jpeg_in_jars.js
 *
 * CheerpJ cannot load JPEG images (no javajpeg native library).
 * This script converts all .jpg/.jpeg files inside JARs to .png format,
 * and patches .class files to reference .png instead of .jpg/.jpeg.
 */

const AdmZip = require("adm-zip");
const sharp = require("sharp");
const fs = require("fs");
const path = require("path");

const INPUT_DIR = "./games-jdk17";
const OUTPUT_DIR = "./games-jdk17"; // overwrite in place

async function processJar(filePath) {
  const fileName = path.basename(filePath);
  console.log(`Processing: ${fileName}`);

  const zip = new AdmZip(filePath);
  const entries = zip.getEntries();

  let jpegCount = 0;
  let patchedClasses = 0;

  // Step 1: Convert JPEG entries to PNG
  const renames = []; // { oldName, newName }

  for (const entry of entries) {
    const name = entry.entryName;
    const lower = name.toLowerCase();

    if (lower.endsWith(".jpg") || lower.endsWith(".jpeg")) {
      try {
        const jpegData = entry.getData();
        const pngData = await sharp(jpegData).png().toBuffer();

        // New name: replace .jpg/.jpeg with .png
        const newName = name.replace(/\.jpe?g$/i, ".png");

        // Remove old entry, add new PNG entry
        zip.deleteFile(entry);
        zip.addFile(newName, pngData);

        renames.push({ oldName: name, newName: newName });
        jpegCount++;
        console.log(
          `   Converted: ${name} -> ${newName} (${jpegData.length} -> ${pngData.length} bytes)`,
        );
      } catch (err) {
        console.log(`   SKIP (not a valid image): ${name} - ${err.message}`);
      }
    }
  }

  // Step 2: Patch .class files to reference .png instead of .jpg/.jpeg
  if (renames.length > 0) {
    const updatedEntries = zip.getEntries();
    for (const entry of updatedEntries) {
      if (!entry.entryName.endsWith(".class")) continue;

      let data = entry.getData();
      let modified = false;

      for (const { oldName, newName } of renames) {
        // Get just the filename parts for patching
        const oldBasename = path.basename(oldName);
        const newBasename = path.basename(newName);

        // Also try with path separators
        const variants = [oldBasename, oldName, oldName.replace(/\//g, "\\")];

        for (const variant of variants) {
          const replacement = variant.replace(/\.jpe?g$/i, ".png");
          const oldBuf = Buffer.from(variant, "utf8");
          const newBuf = Buffer.from(replacement, "utf8");

          // Only replace if same length (to not corrupt constant pool)
          // For .jpg -> .png they're same length (3 chars each)
          if (oldBuf.length === newBuf.length) {
            let idx = data.indexOf(oldBuf);
            while (idx !== -1) {
              newBuf.copy(data, idx);
              modified = true;
              idx = data.indexOf(oldBuf, idx + newBuf.length);
            }
          } else {
            // .jpeg -> .png (4 chars vs 3 chars) - need to handle constant pool properly
            // This is trickier - we need to patch the UTF8 constant pool entry
            // For safety, we'll scan for the CONSTANT_Utf8 pattern
            let idx = data.indexOf(oldBuf);
            while (idx !== -1) {
              // Check if this is inside a UTF8 constant (tag=1, then 2-byte length)
              // The length bytes should be 2 bytes before the string start
              if (idx >= 2) {
                const len = (data[idx - 2] << 8) | data[idx - 1];
                if (len === oldBuf.length) {
                  // Update length
                  const newLen = newBuf.length;
                  data[idx - 2] = (newLen >> 8) & 0xff;
                  data[idx - 1] = newLen & 0xff;

                  // Replace content - need to rebuild buffer since size changed
                  const before = data.slice(0, idx);
                  const after = data.slice(idx + oldBuf.length);
                  data = Buffer.concat([before, newBuf, after]);
                  modified = true;
                }
              }
              idx = data.indexOf(oldBuf, idx + 1);
            }
          }
        }
      }

      if (modified) {
        entry.setData(data);
        patchedClasses++;
      }
    }
  }

  zip.writeZip(filePath);
  console.log(
    `   Done: ${jpegCount} images converted, ${patchedClasses} classes patched\n`,
  );
  return { jpegCount, patchedClasses };
}

async function main() {
  const files = fs.readdirSync(INPUT_DIR).filter((f) => f.endsWith(".jar"));
  console.log(`Found ${files.length} JAR(s) in ${INPUT_DIR}\n`);

  let totalImages = 0;
  let totalClasses = 0;

  for (const file of files) {
    const result = await processJar(path.join(INPUT_DIR, file));
    totalImages += result.jpegCount;
    totalClasses += result.patchedClasses;
  }

  console.log("=".repeat(50));
  console.log(
    `Total: ${totalImages} JPEGs converted to PNG, ${totalClasses} classes patched`,
  );
}

main().catch(console.error);
