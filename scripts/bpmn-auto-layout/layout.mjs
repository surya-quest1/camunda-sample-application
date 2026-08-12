// Adds BPMNDI (diagram layout) to every .bpmn file in models/ and
// fixtures/, in place, via bpmn-io's own bpmn-auto-layout. The generator
// (bpmn_builder.py) deliberately emits semantic-only XML -- the assessment
// tool's analyser never reads BPMNDI -- but Operate's process viewer does,
// so without this every deployed process renders as a blank canvas.
//
// Verified to preserve the semantic census byte-for-byte (diffed the real
// analyser's output before/after) -- this only adds bpmndi:BPMNDiagram,
// never touches existing bpmn: elements.
import { layoutProcess } from 'bpmn-auto-layout';
import { readFileSync, writeFileSync, readdirSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, '..', '..');
const dirs = ['models', 'fixtures'];

let ok = 0, failed = 0;
for (const dir of dirs) {
  const full = join(root, dir);
  let files;
  try {
    files = readdirSync(full).filter(f => f.endsWith('.bpmn'));
  } catch {
    continue;
  }
  for (const f of files) {
    const path = join(full, f);
    const xml = readFileSync(path, 'utf-8');
    if (xml.includes('bpmndi:BPMNDiagram')) {
      console.log('skip (already laid out):', dir + '/' + f);
      continue;
    }
    try {
      const laidOut = await layoutProcess(xml);
      writeFileSync(path, laidOut);
      console.log('laid out:', dir + '/' + f);
      ok++;
    } catch (e) {
      console.error('FAILED:', dir + '/' + f, '--', e.message);
      failed++;
    }
  }
}
console.log(`\n${ok} laid out, ${failed} failed`);
if (failed > 0) process.exit(1);
