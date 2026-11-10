import { randomUUID } from "node:crypto";

const releaseNotes = process.env.RELEASE_NOTES?.trim();
const releaseNoteBanner = process.env.RELEASE_NOTE_BANNER?.trim();
const sectionTitles = new Map([
  ["Features", "⭐ New Features"],
  ["Bug Fixes", "🐞 Bug Fixes"],
  ["Reverts", "🐞 Bug Fixes"],
]);
const miscellaneousSections = new Set([
  "Build System",
  "Build Systems",
  "Continuous Integration",
  "Tests",
]);
const sectionOrder = new Map([
  ["⚠ BREAKING CHANGES", 0],
  ["⭐ New Features", 10],
  ["⚡ Performance Improvements", 20],
  ["🐞 Bug Fixes", 30],
  ["📦 Dependency Upgrades", 40],
  ["📔 Documentation", 50],
  ["⚙️ Miscellaneous", 60],
  ["Reverts", 70],
]);

if (!releaseNotes) {
  throw new Error("RELEASE_NOTES must contain generated release notes.");
}
if (releaseNoteBanner?.includes("\n")) {
  throw new Error("RELEASE_NOTE_BANNER must be a single line.");
}

const lines = releaseNotes.split("\n");
const sectionIndexes = lines.flatMap((line, index) =>
  /^### (?!\[)(.+)$/.test(line) ? [index] : [],
);
if (sectionIndexes.length === 0) {
  throw new Error("Generated release notes do not contain any sections.");
}

const formattedSections = [];
for (const [index, start] of sectionIndexes.entries()) {
  const end = sectionIndexes[index + 1] ?? lines.length;
  const [, sourceTitle] = /^### (.+)$/.exec(lines[start]);
  const title = sectionTitles.get(sourceTitle) ?? (
    miscellaneousSections.has(sourceTitle) ? "⚙️ Miscellaneous" : sourceTitle
  );
  const body = lines.slice(start + 1, end).join("\n").trim();
  const existing = formattedSections.find((section) => section.title === title);
  if (existing) existing.body = `${existing.body}\n\n${body}`.trim();
  else formattedSections.push({ title, body, index });
}

const orderedSections = formattedSections.sort(
  (left, right) =>
    (sectionOrder.get(left.title) ?? Number.MAX_SAFE_INTEGER) -
      (sectionOrder.get(right.title) ?? Number.MAX_SAFE_INTEGER) ||
    left.index - right.index,
);
const formattedNotes = [
  ...lines.slice(0, sectionIndexes[0]),
  ...(releaseNoteBanner ? [`**${releaseNoteBanner}**`, ""] : []),
  ...orderedSections.flatMap((section) => [
    `### ${section.title}`,
    "",
    section.body,
    "",
  ]),
].join("\n").trim();
const delimiter = randomUUID();
process.stdout.write(`changelog<<${delimiter}\n${formattedNotes}\n${delimiter}\n`);
