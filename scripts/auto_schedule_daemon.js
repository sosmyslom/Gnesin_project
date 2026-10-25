import { execFile } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(__dirname, '..');

const nodeBin = process.execPath;
const npxBin = path.join(path.dirname(nodeBin), 'npx');

async function triggerDispatch() {
  return new Promise((resolve) => {
    execFile(
      npxBin,
      ['@tgcloud/cli', 'run', 'endpoints/dispatchAutoSchedule', '{}', '--ctx', '{ initData: { user: { id: 1 } } }'],
      { cwd: projectRoot, env: process.env },
      (error, stdout, stderr) => {
        if (error) {
          console.error(`[${new Date().toISOString()}] Dispatch error:`, error.message);
        } else {
          const out = stdout.trim();
          if (out && !out.includes('{sent:0,checked:0}')) {
            console.log(`[${new Date().toISOString()}] Dispatch result:`, out);
          }
        }
        resolve();
      }
    );
  });
}

async function loop() {
  console.log(`[${new Date().toISOString()}] Gnesinka AutoSchedule Daemon started`);
  while (true) {
    const now = new Date();
    // Wait until the next minute boundary (:00 seconds)
    const msUntilNextMinute = (60 - now.getSeconds()) * 1000 - now.getMilliseconds() + 500;
    await new Promise((r) => setTimeout(r, msUntilNextMinute));
    await triggerDispatch();
  }
}

loop();
