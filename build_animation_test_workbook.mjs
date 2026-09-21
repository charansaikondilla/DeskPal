import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const root = process.cwd();
const outDir = path.join(root, "outputs", "animation-testing");
const planDir = path.join(root, "assets", "ganesh", "planning-v3");
await fs.mkdir(outDir, { recursive: true });

const wb = Workbook.create();
const overview = wb.worksheets.add("Test Overview");
const log = wb.worksheets.add("Test Log");
const refs = wb.worksheets.add("Concept Boards");

const font = "Arial";
const navy = "#17365D";
const blue = "#DDEBF7";
const amber = "#FFF2CC";
const green = "#E2F0D9";
const red = "#FCE4D6";
const gray = "#F2F2F2";

const groups = [
  ["🧍 Standing & blink", "Standing", [
    ["Neutral pose", "Arms relaxed; feet share the floor anchor; crown and feather are not clipped."],
    ["Idle loop", "Frames 0–11 loop without a visible snap or foot drift."],
    ["Blink insert", "Blink plays without restarting or popping the idle body cycle."],
    ["Desktop edge", "No white or magenta halo on both light and dark desktop backgrounds."],
  ]],
  ["🧘 Breathe & meditation peek", "Breathe", [
    ["Breath phase", "Inhale and exhale follow the active breathing timer; they do not use an unrelated loop."],
    ["Seated anchor", "Crown stays stable and the seated pose has no sliding or scale change."],
    ["One-eye peek", "Optional peek occurs between rounds and does not reset the countdown."],
    ["Interrupt", "Dragging or ending breathing stops the pose cleanly and returns to the correct idle."],
  ]],
  ["🍬 Modak jump & catch", "Modak jump", [
    ["Start pose", "Begins holding one cream-gold modak before the throw."],
    ["Release", "Modak detaches at release and travels on one continuous arc."],
    ["Jump arc", "Feet leave and return to the shared floor line; character size stays constant."],
    ["Mouth catch", "Modak visibly reaches the mouth before it is hidden."],
    ["After catch", "No second modak or sweet-through-body artifact during chew and tummy pat."],
    ["Settle", "Ends in the common idle anchor without a position jump."],
  ]],
  ["🪟 Window-edge peek", "Window peek", [
    ["Entry", "Ear, crown, and fingertips appear progressively from the edge."],
    ["Occlusion", "Uses clipping/masking only; no white window card is baked into the sprite."],
    ["Left/right", "Both directions are fully visible and preserve crown/feather orientation."],
    ["Safety", "Does not appear during dragging, full-screen work, breathing, or near typing fields."],
  ]],
  ["💧 Thirst, drink & recover", "Drink water", [
    ["Soft slump", "Tired movement reads as a gentle cartoon sit, not a painful fall."],
    ["Reminder hold", "Tired pose holds calmly and does not replay the collapse."],
    ["Cup contact", "Blue cup follows the hand and reaches a believable drinking position."],
    ["Acknowledgement", "‘Drank it’ triggers drink then recovery; snooze exits gracefully."],
    ["Return", "Recovery stands and returns to idle without timer or callback errors."],
  ]],
  ["🙏 Blessing", "Blessing", [
    ["Hand raise", "Palm rises smoothly without covering the face, trunk, or crown."],
    ["Blessing hold", "Held pose is calm; any gold glow is subtle and behind the palm."],
    ["Hand orientation", "Uses the intended blessing hand; no incorrect mirrored clip."],
    ["Exit", "Hand lowers and returns to idle without a pop."],
  ]],
  ["📖 Study", "Study", [
    ["Entry", "Sits and opens the book without clipping the lap or hands."],
    ["Reading loop", "Eyes, finger, nod, and blink vary gently while the book stays anchored."],
    ["Page turn", "Page turn is occasional, hinged at the book, and does not restart every loop."],
    ["Focus control", "Focus start uses study; completion exits study before happy jump."],
  ]],
  ["🐭 Play with mouse", "Mouse play", [
    ["Greeting", "Ganesh kneels and the mouse sniffs at the offered hand."],
    ["Chase gait", "Chase uses a true two-sided gait with a variable, bounded mouse lead."],
    ["Gentle catch", "Hands cup the mouse gently; never grab the tail."],
    ["Cancel", "Dragging Ganesh cancels the chase cleanly; actors stay on one monitor."],
  ]],
  ["🐁 Ride mouse", "Mouse ride", [
    ["Mount", "Ganesh settles onto the deliberately larger ride mouse without hovering."],
    ["Trot loop", "Mouse leg contacts alternate; rider bounce, trunk, and feather lag naturally."],
    ["Seat anchor", "Rider remains attached to the mouse back throughout travel."],
    ["Dismount", "Decelerates and steps off cleanly; left-facing version is reviewed."],
  ]],
  ["🎉 Happy jump", "Happy jump", [
    ["Anticipation", "Knees bend and arms sweep before takeoff."],
    ["Airborne pose", "Whole actor follows a continuous arc with stable scale."],
    ["Landing", "Feet contact the shared floor, then trunk, ears, and feather settle late."],
    ["One-shot", "Manual replay works; clip returns to the previous appropriate idle."],
  ]],
  ["🧪 Shared runtime checks", "All animations", [
    ["Registration", "No crown, tail, prop, or airborne sweet is clipped in any frame."],
    ["Transparent export", "No white/grid remnants or magenta fringe on light and dark backgrounds."],
    ["Frame integrity", "All referenced files decode; frame count and metadata match; consecutive frames change intentionally."],
    ["Priority", "Dragging > guided session > reminder action > manual emote > idle play."],
    ["Stress replay", "Replay and Stop repeatedly without stale callbacks, exceptions, or timer drift."],
  ]],
];

// Overview
overview.showGridLines = false;
overview.getRange("A2").values = [["Ganesh animation test board"]];
overview.getRange("A2").format = { font: { name: font, size: 16, bold: true, color: navy } };
overview.getRange("A3").values = [["Test one item at a time. Choose a status in Test Log, then record the issue or evidence."]];
overview.getRange("A3").format = { font: { name: font, size: 10, italic: true, color: "#666666" } };
overview.getRange("A5:B9").values = [
  ["Total checks", "=COUNTA('Test Log'!$A$6:$A$70)"],
  ["✅ Passed", "=COUNTIF('Test Log'!$D$6:$D$70,\"✅ Pass\")"],
  ["🔴 Failed", "=COUNTIF('Test Log'!$D$6:$D$70,\"🔴 Fail\")"],
  ["🟡 Needs review", "=COUNTIF('Test Log'!$D$6:$D$70,\"🟡 Needs review\")"],
  ["Progress", "=IF(B5=0,0,(B6+B7+B8)/B5)"],
];
overview.getRange("B5:B9").formulas = [["=COUNTA('Test Log'!$A$6:$A$70)"],["=COUNTIF('Test Log'!$D$6:$D$70,\"✅ Pass\")"],["=COUNTIF('Test Log'!$D$6:$D$70,\"🔴 Fail\")"],["=COUNTIF('Test Log'!$D$6:$D$70,\"🟡 Needs review\")"],["=IF(B5=0,0,(B6+B7+B8)/B5)"]];
overview.getRange("A5:B9").format = { font: { name: font, size: 11 }, borders: { preset: "all", style: "thin", color: "#D9E2F3" } };
overview.getRange("A5:A9").format.fill = blue;
overview.getRange("A5:A9").format.font = { name: font, bold: true, color: navy };
overview.getRange("B5:B8").format = { font: { name: font, size: 12, bold: true }, horizontalAlignment: "center" };
overview.getRange("B9").format.numberFormat = "0%";
overview.getRange("A11:D11").values = [["Section", "Emote", "Checks", "Action"]];
overview.getRange("A11:D11").format = { fill: navy, font: { name: font, bold: true, color: "#FFFFFF" }, horizontalAlignment: "center" };
const overviewRows = groups.map(([section, emote, items]) => [section, emote, items.length, "Test in Test Log"]);
overview.getRange(`A12:D${11 + overviewRows.length}`).values = overviewRows;
overview.getRange(`A12:D${11 + overviewRows.length}`).format = { font: { name: font, size: 10 }, borders: { preset: "insideHorizontal", style: "thin", color: "#E7E6E6" } };
overview.getRange(`C12:C${11 + overviewRows.length}`).format.horizontalAlignment = "center";
overview.getRange("A5:H25").format.verticalAlignment = "center";
overview.getRange("A:A").format.columnWidth = 30;
overview.getRange("B:B").format.columnWidth = 20;
overview.getRange("C:C").format.columnWidth = 14;
overview.getRange("D:D").format.columnWidth = 22;
overview.getRange("E:H").format.columnWidth = 12;

// Test log
log.showGridLines = false;
log.getRange("A2:F2").merge();
log.getRange("A2").values = [["Animation test log"]];
log.getRange("A2").format = { font: { name: font, size: 16, bold: true, color: navy } };
log.getRange("A3:F3").merge();
log.getRange("A3").values = [["Work top to bottom. Status and notes are editable. Use ‘Not tested’ before you start."]];
log.getRange("A3").format = { font: { name: font, size: 10, italic: true, color: "#666666" } };
log.getRange("A5:F5").values = [["Section", "Emote", "Test", "Status", "Issue / evidence", "Retest"]];
log.getRange("A5:F5").format = { fill: navy, font: { name: font, bold: true, color: "#FFFFFF" }, horizontalAlignment: "center", verticalAlignment: "center", wrapText: true };
let rows = [];
for (const [section, emote, items] of groups) {
  for (const [test, expected] of items) rows.push([section, emote, test, "⚪ Not tested", expected, ""]);
}
log.getRange(`A6:F${5 + rows.length}`).values = rows;
log.getRange(`A6:F${5 + rows.length}`).format = { font: { name: font, size: 10 }, verticalAlignment: "center", wrapText: true, borders: { insideHorizontal: { style: "thin", color: "#E7E6E6" } } };
log.getRange(`D6:D${5 + rows.length}`).format.fill = amber;
log.getRange(`F6:F${5 + rows.length}`).format.fill = amber;
log.getRange(`D6:D${5 + rows.length}`).dataValidation = { rule: { type: "list", values: ["⚪ Not tested", "🟡 Needs review", "✅ Pass", "🔴 Fail"] } };
log.getRange(`F6:F${5 + rows.length}`).dataValidation = { rule: { type: "list", values: ["", "Retest needed", "Retested OK"] } };
log.getRange(`D6:D${5 + rows.length}`).conditionalFormats.add("containsText", { text: "✅ Pass", format: { fill: green, font: { color: "#006100", bold: true } } });
log.getRange(`D6:D${5 + rows.length}`).conditionalFormats.add("containsText", { text: "🔴 Fail", format: { fill: red, font: { color: "#9C0006", bold: true } } });
log.getRange(`D6:D${5 + rows.length}`).conditionalFormats.add("containsText", { text: "🟡 Needs review", format: { fill: amber, font: { color: "#9C6500", bold: true } } });
log.freezePanes.freezeRows(5);
log.freezePanes.freezeColumns(2);
log.getRange("A:A").format.columnWidth = 28;
log.getRange("B:B").format.columnWidth = 16;
log.getRange("C:C").format.columnWidth = 20;
log.getRange("D:D").format.columnWidth = 18;
log.getRange("E:E").format.columnWidth = 62;
log.getRange("F:F").format.columnWidth = 18;
log.getRange(`A6:F${5 + rows.length}`).format.rowHeight = 34;

// Concept references
refs.showGridLines = false;
refs.getRange("A2:H2").merge();
refs.getRange("A2").values = [["Concept boards — pose reference only"]];
refs.getRange("A2").format = { font: { name: font, size: 16, bold: true, color: navy } };
refs.getRange("A3:H3").merge();
refs.getRange("A3").values = [["Use these boards to compare expression and story beats. Production playback needs the Test Log checks, not just matching poses."]];
refs.getRange("A3").format = { font: { name: font, size: 10, italic: true, color: "#666666" } };
const images = [
  ["🧍 Personality concepts", "01-personality-concepts.png", 5],
  ["🐭 Play and jump concepts", "02-play-and-jump-concepts.png", 30],
];
for (const [label, filename, row] of images) {
  refs.getRange(`A${row}:H${row}`).merge();
  refs.getRange(`A${row}`).values = [[label]];
  refs.getRange(`A${row}`).format = { fill: navy, font: { name: font, bold: true, color: "#FFFFFF" } };
  const data = await fs.readFile(path.join(planDir, filename));
  refs.images.add({ dataUrl: `data:image/png;base64,${data.toString("base64")}`, anchor: { from: { row, col: 0 }, extent: { widthPx: 820, heightPx: filename.startsWith("01") ? 534 : 410 } } });
}
refs.getRange("A:A").format.columnWidth = 16;
refs.getRange("B:H").format.columnWidth = 16;

wb.recalculate();
const check = await wb.inspect({ kind: "table", range: "Test Overview!A2:D23", include: "values,formulas", tableMaxRows: 24, tableMaxCols: 6 });
console.log(check.ndjson);
const errors = await wb.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!", options: { useRegex: true, maxResults: 100 }, summary: "final formula error scan" });
console.log(errors.ndjson);
for (const [sheetName, range] of [["Test Overview", "A2:D23"], ["Test Log", `A2:F${5 + rows.length}`], ["Concept Boards", "A2:H50"]]) {
  const preview = await wb.render({ sheetName, range, scale: 1, format: "png" });
  await fs.writeFile(path.join(outDir, `${sheetName.replaceAll(" ", "_")}.png`), new Uint8Array(await preview.arrayBuffer()));
}
const xlsx = await SpreadsheetFile.exportXlsx(wb);
await xlsx.save(path.join(outDir, "ganesh_animation_test_workbook.xlsx"));
