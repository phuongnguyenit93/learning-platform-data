# Limiting Size, Entry Count, and Decompression Ratio — Protecting Java ZIP Extraction

## 1. Why Must Limits Be Enforced During Extraction?

In Java Core I/O, APIs such as `ZipFile`, `ZipInputStream`, and `ZipEntry` make reading ZIP files relatively easy. However, a ZIP file from an untrusted source can be very small on disk while producing massive amounts of data, huge numbers of child files, or complex directory trees when extracted.

Common risks:

- **ZIP bomb / decompression bomb:** compressed data of only a few kilobytes or megabytes expands into gigabytes, exhausting disk space, CPU, RAM, or processing time.
- **Too many entries:** hundreds of thousands of tiny files can exhaust inodes, file handles, metadata, and file creation time, even when total decompressed bytes are small.
- **One oversized entry:** a single file exceeds business thresholds, overloading downstream storage or parsing systems.
- **Excessively high decompression ratio:** a tiny compressed entry expands to an abnormally large uncompressed byte count.
- **Zip Slip / path traversal:** an entry named like `../../outside.txt` attempts to write outside the permitted directory.
- **File overwrites, duplicate names, symlinks, and filesystem quirks:** overwrite existing documents or cause the final path to resolve to an unintended location.

**No single threshold solves every risk.** Systems should enforce independent limits on input ZIP size, entry count, decompressed size per entry, total decompressed size, and compression ratio; then supplement them with resource limits and path validation.

Goals of this lesson: design a defensive policy, understand the decompression ratio formula, handle unknown/untrusted metadata, enforce limits **while streaming bytes**, and write a standalone Java 17+ example.

## 2. Three Primary Limits and How to Compute Them

### 2.1. Size

There are at least three distinct numbers:

1. **Input ZIP size:** size of the archive file on disk, e.g., `Files.size(zipPath)`. Reject huge input archives before deep parsing.
2. **Decompressed size of a single entry:** actual bytes produced by `InputStream.read(...)` for that entry alone. Block a single oversized file.
3. **Total decompressed size of the archive:** sum of actual bytes across all entries read. Block cases with many small files, each under the per-entry cap, whose total grows too large.

An **illustrative** policy example for a service receiving configuration ZIP files:

| Property | Example Limit | Purpose |
| --- | ---: | --- |
| Input archive size | 4 MiB | Bounds uploading and handling the ZIP file |
| Entry count (including directories) | 100 | Caps file/folder count and metadata overhead |
| Decompressed size per entry | 1 MiB | Prevents any single file from getting too large |
| Total decompressed bytes | 2 MiB | Prevents total data explosion |
| Max decompression ratio per file | 100:1 | Blocks abnormally expanding data |

These numbers **are not a universal Java security standard**. In practice, tune them to business requirements, infrastructure, quotas, SLAs, valid file types, and benchmark results. If a service accepts multi-gigabyte backups, these example thresholds are clearly inappropriate.

**MiB = 1,048,576 bytes** (2^20); do not confuse with decimal MB = 1,000,000 bytes.

### 2.2. Entry Count Limit

An entry in a ZIP can represent a file or a directory. For example:

~~~text
project/
project/docs/
project/docs/readme.md
project/config.json
~~~

The archive above has **4 entries** if both directories are recorded as explicit entries. Another archive might store only two files without separate directory entries; the entry count depends on how it was packaged.

Count every entry you traverse, **including directory entries**, rather than only files with payloads. If duplicate names appear, define a rejection policy so later entries never silently overwrite earlier ones. If you need a separate limit on **actual files** distinct from total entries, track an additional counter; do not replace the total entry counter.

Limiting entry count mitigates archives containing tens of thousands of 0-byte files. Limiting total bytes alone is **not** enough to stop that case.

### 2.3. Decompression Ratio

For a single entry:

\[
\text{ratio} = \frac{\text{decompressed bytes}}{\text{compressed data bytes}}
\]

Examples:

- Entry has 500,000 decompressed bytes and 100,000 compressed bytes: ratio **5:1**.
- Entry has 500,000 decompressed bytes and 1,000 compressed bytes: ratio **500:1**.
- If the policy allows at most 100:1, the second case is rejected.

To avoid unnecessary division, you can check:

~~~java
// Only valid when compressedBytes > 0 and multiplication does not overflow long.
boolean tooHigh = uncompressedBytes > compressedBytes * maxRatio;
~~~

If compressed bytes equal **0** while decompressed bytes are **positive**, the ratio is undefined/infinite: treat it as anomalous and reject. If both are 0, it may be a valid empty entry.

**Warning:** compression ratio by itself does not tell the whole risk story. A huge file with a 2:1 ratio can still fill a disk; conversely, a small legitimate file with a 200:1 ratio might get blocked by a strict ratio rule. Therefore combine ratio checks with **absolute byte limits**, time limits, and resource quotas.

## 3. Is Checking Only ZipEntry.getSize() Enough?

**No.** `ZipEntry.getSize()` reports the uncompressed size declared in metadata, and `ZipEntry.getCompressedSize()` reports the compressed size per ZIP metadata. In certain reading paths, these can be `-1`, meaning unknown.

~~~java
ZipEntry entry = /* a read entry */;
long declaredSize = entry.getSize();
long declaredCompressedSize = entry.getCompressedSize();
~~~

This is merely an **API illustration snippet**, not a standalone program. Those two values are useful to **reject early** entries clearly exceeding thresholds. Yet metadata comes from untrusted input, so it must never be treated as final proof of safety when handling untrusted archives.

Distinguish two defensive layers:

- **Preflight metadata:** inspect entry count, names, declared size, declared compressed size, and declared ratio. Reject violations before creating files.
- **Streaming enforcement:** on every `read(...)`, accumulate **actual bytes** and abort immediately if one entry or the archive total exceeds quotas. This layer is mandatory so you never trust declarations blindly.

With `ZipFile`, information read from the central directory normally provides concrete sizes; still, code must decide how to handle missing/invalid values. The example in this article **rejects unknown-size metadata** to enforce ratios conservatively. Another application might support streaming `ZipInputStream` where sizes are unknown upfront, in which case real-time actual byte limits are even more critical; computing exact compression ratios requires measuring actual compressed bytes consumed per entry, not guessing from decompressed stream counts.

**Never use `Files.size(zipPath)` as the ratio denominator for each entry.** Archive size also includes headers, filenames, the central directory, and other entries' data. Per-entry ratios use the compressed data size of **that entry itself**.

## 4. Types of ZIP Bombs to Understand

### 4.1. Abnormally Large Entry

An entry holding huge runs of identical bytes, such as millions of `'A'` characters, compresses extremely well. On disk it is tiny; upon decompression it overwhelms storage or downstream parsers.

**Protection:** limit per-entry size and decompression ratio, checking on every `read` iteration.

### 4.2. Massive Numbers of Tiny Files

An archive with 100,000 entries of just a few bytes each. Total bytes may be small, yet opening/creating/closing files, metadata, inodes, permissions, and antivirus scans consume massive resources.

**Protection:** limit entry count, name length, directory depth, and created files; combine with quotas and timeouts. The 100-entry limit in the upcoming example is an illustrative choice.

### 4.3. Nested ZIPs (ZIP inside ZIP)

An outer archive contains multiple inner archives; the application then automatically extracts each child archive. Enforcing quotas only **per layer** allows total cost to grow explosively.

**Protection:** ideally **do not recursively auto-extract** unless business logic strictly requires it. If required, enforce a **global** budget across the whole tree (depth, total entries, total bytes, total time, ratios) and reject upon breach. Never reset quotas back to full defaults for each child archive.

### 4.4. Entries with Intentionally Malformed Metadata or Names

Strange names, overly long names, duplicate paths, parent paths `..`, absolute paths, foreign OS separators, symlinks, or corrupted files can cause errors or out-of-bounds side effects.

**Protection:** validate paths, naming policies, and entry types; extract into a fresh, isolated directory with no pre-existing files. `ZipFile` only exposes the ZIP metadata readable through the public API; never assume it is a complete validator for every kind of ZIP metadata, permission, or symbolic link.

## 5. Multi-Layer Extraction Defense Model

A safer pipeline:

~~~text
Archive input
      |
      v
Upload limits + ZIP size + ownership
      |
      v
Open ZIP, inspect metadata: count, path, size, ratio
      |
      +-- Violation --> REJECT (do not publish output)
      |
      v
Create fresh target directory in staging area
      |
      v
Stream each entry sequentially using a fixed buffer
      |
      +-- Byte/ratio/time quota exceeded --> ABORT & CLEANUP
      |
      v
Check schema, library-verified CRC, content, policies
      |
      v
Publish verified result, record state/audit
~~~

**Design point:** extraction **should never write directly into an active application directory**. If a bomb is detected midway, partially written files must be treated as untrusted staging data. Publish only after the entire archive passes all relevant checks.

### Shared Budget

The total byte limit must **accumulate across all entries**, never resetting to 0 for each file. Overflow-safe check pattern:

~~~java
if (n > maxEntryBytes - entryBytes
        || n > maxTotalBytes - totalBytes) {
    throw new IOException("Exceeded decompression quota");
}

entryBytes += n;
totalBytes += n;
~~~

This illustrative snippet assumes `n` is a **positive** count of newly read bytes, with counters initialized non-negative and kept within bounds. Comparing via `limit - used` prevents `used + n` from overflowing `long`.

Reading with a `byte[8192]` buffer only holds about 8 KiB per read and **does not** cap the output file size. You must accumulate and block based on actual total bytes.

## 6. Complete Java 17+ Example: ZipFile with Strict Limits

The example creates a valid two-file ZIP, extracts it into a new directory, and verifies its contents. Then it creates a ZIP containing entry `../outside.txt` to show the path validator rejecting it before any write escapes outside.

The example uses small policies for clarity:

- Original ZIP file max 4 MiB.
- Max 100 entries.
- Each decompressed file max 1 MiB.
- Total decompressed data max 2 MiB.
- Each file max 100:1 ratio; reject unknown size metadata.
- Reject entries with `..`, absolute paths, `\`, Windows drive prefixes, blank names, or duplicate normalized paths.
- Create a **non-existent output directory**, using `CREATE_NEW` to prevent overwrites.

Save as **`SafeZipExtractionDemo.java`**:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.Enumeration;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;
import java.util.zip.ZipOutputStream;

public class SafeZipExtractionDemo {
    private static final long MAX_ZIP = 4L * 1024 * 1024;
    private static final long MAX_ENTRY = 1L * 1024 * 1024;
    private static final long MAX_TOTAL = 2L * 1024 * 1024;
    private static final long MAX_RATIO = 100;
    private static final int MAX_COUNT = 100;

    public static void main(String[] args) throws Exception {
        Path work = Files.createTempDirectory("zip-limits-");
        try {
            Path goodZip = work.resolve("good.zip");
            try (ZipOutputStream out =
                         new ZipOutputStream(Files.newOutputStream(goodZip))) {
                addEntry(out, "docs/readme.txt", "hello");
                addEntry(out, "metadata.txt", "v1");
            }

            Path goodOutput = work.resolve("unpacked");
            int files = extract(goodZip, goodOutput);
            System.out.println("Files extracted: " + files);
            System.out.println("Readme: " + Files.readString(
                    goodOutput.resolve("docs/readme.txt"),
                    StandardCharsets.UTF_8));

            Path badZip = work.resolve("bad.zip");
            try (ZipOutputStream out =
                         new ZipOutputStream(Files.newOutputStream(badZip))) {
                addEntry(out, "../outside.txt", "forbidden");
            }

            boolean rejected = false;
            try {
                extract(badZip, work.resolve("blocked"));
            } catch (IOException expected) {
                rejected = true;
            }
            System.out.println("Traversal rejected: " + rejected);
        } finally {
            cleanup(work);
        }
    }

    private static void addEntry(
            ZipOutputStream out, String name, String text)
            throws IOException {
        out.putNextEntry(new ZipEntry(name));
        out.write(text.getBytes(StandardCharsets.UTF_8));
        out.closeEntry();
    }

    private static int extract(Path zipPath, Path outputRoot)
            throws IOException {
        if (Files.size(zipPath) > MAX_ZIP) {
            throw new IOException("ZIP input too large");
        }

        try (ZipFile zip = new ZipFile(zipPath.toFile())) {
            List<ZipEntry> entries = new ArrayList<>();
            Set<Path> usedNames = new HashSet<>();
            Enumeration<? extends ZipEntry> it = zip.entries();

            // First pass: do not write before validating all entries.
            while (it.hasMoreElements()) {
                ZipEntry entry = it.nextElement();
                if (entries.size() >= MAX_COUNT) {
                    throw new IOException("Too many ZIP entries");
                }

                Path relative = validateName(entry.getName());
                if (!usedNames.add(relative)) {
                    throw new IOException("Duplicate path: " + relative);
                }

                long size = entry.getSize();
                long compressed = entry.getCompressedSize();
                if (size < 0 || compressed < 0) {
                    throw new IOException("Unknown ZIP entry size");
                }
                if (size > MAX_ENTRY || compressed > MAX_ZIP) {
                    throw new IOException("Entry size exceeded");
                }
                if (exceedsRatio(size, compressed)) {
                    throw new IOException("Ratio exceeded");
                }
                if (entry.isDirectory() && size != 0) {
                    throw new IOException("Directory entry with data");
                }
                entries.add(entry);
            }

            // A fresh, unshared output directory limits overwrite risk.
            Files.createDirectory(outputRoot);
            long total = 0;
            int fileCount = 0;
            byte[] chunk = new byte[8192];

            for (ZipEntry entry : entries) {
                Path relative = validateName(entry.getName());
                Path output = outputRoot.resolve(relative).normalize();
                if (!output.startsWith(outputRoot)) {
                    throw new IOException("Path escaped target directory");
                }

                if (entry.isDirectory()) {
                    Files.createDirectories(output);
                    continue;
                }

                Files.createDirectories(output.getParent());
                long entryBytes = 0;
                long compressed = entry.getCompressedSize();

                try (InputStream in = zip.getInputStream(entry);
                     OutputStream out = Files.newOutputStream(
                             output,
                             StandardOpenOption.CREATE_NEW,
                             StandardOpenOption.WRITE)) {

                    int n;
                    while ((n = in.read(chunk)) != -1) {
                        if (n == 0) {
                            throw new IOException("Input made no progress");
                        }
                        if (n > MAX_ENTRY - entryBytes
                                || n > MAX_TOTAL - total) {
                            throw new IOException("Byte quota exceeded");
                        }

                        entryBytes += n;
                        total += n;
                        if (exceedsRatio(entryBytes, compressed)) {
                            throw new IOException("Ratio exceeded");
                        }
                        out.write(chunk, 0, n);
                    }
                }

                // Count only files written successfully.
                fileCount++;
            }
            return fileCount;
        }
    }

    private static boolean exceedsRatio(
            long uncompressed, long compressed) {
        if (uncompressed == 0) {
            return false;
        }
        if (compressed == 0) {
            return true;
        }
        // MAX_ZIP constrains compressed values before calling here.
        return compressed <= Long.MAX_VALUE / MAX_RATIO
                && uncompressed > compressed * MAX_RATIO;
    }

    private static Path validateName(String name) throws IOException {
        if (name.isBlank()
                || name.indexOf('\\') >= 0
                || name.indexOf('\0') >= 0
                || name.startsWith("/")
                || name.matches("^[A-Za-z]:.*")) {
            throw new IOException("Unsafe name: " + name);
        }

        Path relative;
        try {
            relative = Path.of(name);
        } catch (RuntimeException invalidName) {
            throw new IOException("Invalid ZIP path", invalidName);
        }
        if (relative.isAbsolute()) {
            throw new IOException("Absolute ZIP path");
        }
        for (Path part : relative) {
            if (part.toString().equals("..")) {
                throw new IOException("Parent traversal forbidden");
            }
        }
        relative = relative.normalize();
        if (relative.toString().isEmpty()
                || relative.toString().equals(".")) {
            throw new IOException("Empty path");
        }
        return relative;
    }

    private static void cleanup(Path root) throws IOException {
        try (var paths = Files.walk(root)) {
            for (Path path : paths.sorted(
                    Comparator.reverseOrder()).toList()) {
                Files.deleteIfExists(path);
            }
        }
    }
}
~~~

Compile/run with JDK 17 or later:

~~~bash
javac -encoding UTF-8 SafeZipExtractionDemo.java
java SafeZipExtractionDemo
~~~

**Expected stdout on a standard filesystem:**

~~~text
Files extracted: 2
Readme: hello
Traversal rejected: true
~~~

### Code Explanation

1. `Files.size(zipPath)` bounds the input archive size before deeply reading contents. This is **not** the decompressed size limit; it is a separate quota.
2. The `zip.entries()` loop scans all entries once to validate every name, entry count, and metadata before writing. `entries.size() >= MAX_COUNT` rejects the 101st entry.
3. `usedNames` rejects duplicate normalized names so new entries cannot intentionally overwrite earlier ones. Whether distinct-cased names collide on a case-insensitive filesystem depends on the platform; `CREATE_NEW` adds another layer of defense.
4. `validateName` rejects blank names, NUL bytes, backslashes, drive-letter paths, absolute paths, and any `..` segment. It blocks basic traversal patterns and requires `/` separators for the demo ZIP.
5. `Files.createDirectory(outputRoot)` requires the output directory not to exist yet. Never write into an active system directory or an existing path holding important files.
6. For each file, the program reads chunks of up to 8192 bytes and **checks quotas before writing that chunk**. `entryBytes` and `total` track actual bytes rather than trusting `entry.getSize()` alone.
7. `exceedsRatio` handles a zero denominator and prevents `long` overflow. In the example, metadata `compressed` is already bounded ≤ 4 MiB.
8. `ZipFile.getInputStream(entry)` opens only the specific entry's stream; `try-with-resources` closes it even when a quota breach occurs.
9. After processing completes, the program prints the extracted file count and content. A malicious archive containing `../outside.txt` is rejected during the first validation pass.
10. `cleanup` deletes the temporary tree in the demo. Demo code is not a durable storage system; production requires staging workflows, failure cleanup, race/symlink defenses, and safer publishing.

**Intentional limitations:** This example teaches counting size, entries, ratios, and basic Zip Slip prevention. It is **not a complete ZIP sandbox**. It lacks watchdog timeouts, OS sandboxing, business format verification, POSIX symlink handling in ZIPs, depth/name-length limits, cross-request concurrency quotas, and atomic publishing. Do not deploy it verbatim to process hostile archives in multi-tenant environments without adding those protections.

## 7. Why Check Ratios Both Before and During Decompression?

### Preflight Check (Declared Ratio)

If a ZIP declares `uncompressedSize = 10_000_000` and `compressedSize = 1_000`, the 10,000:1 ratio exceeds 100:1; you can reject immediately without creating files or decompressing the payload.

Early rejection saves resources, yet **is not enough**: metadata cannot be assumed trustworthy, and parsers may still confront corrupted data or complex archive structures.

### In-Loop Check (Actual Output)

If metadata claims an entry is small while the actual stream yields far more bytes, real counters will exceed `MAX_ENTRY` or `MAX_TOTAL`. Checking every chunk limits how much data the application writes to disk.

For ratios, the example uses **actually decompressed** bytes against **declared** compressed bytes from the central directory. That acts as an **early circuit breaker**, not an exact meter of physical compressed bytes read at each instant. If compressed-size metadata is untrusted, absolute output limits remain the stronger safeguard.

To measure exact compression ratios in a streaming pipeline lacking trusted metadata, you must instrument the actual compressed byte source per entry, accounting for buffering, data descriptors, and ZIP framing; never take bytes read from an arbitrary wrapper stream and call that per-entry `compressedSize`.

### Archive-Wide Ratio

You can compute:

\[
\text{archive ratio} =
\frac{\text{total uncompressed bytes}}{\text{ZIP size on disk}}
\]

as an extra metric, though this differs from **per-entry** ratios because a ZIP includes headers, metadata, and the central directory. It could miss a single extreme entry when other large entries inflate the denominator. Thus, when needed, enforce both per-entry and archive-wide ratio limits without replacing absolute byte limits.

## 8. ZipFile or ZipInputStream?

| Factor | `ZipFile` | `ZipInputStream` |
| --- | --- | --- |
| Access model | Opens archive, inspects central directory entries, opens streams per entry | Sequentially reads entries from an `InputStream` |
| Size metadata | Usually available from the central directory before opening payload | May be `-1` until entry finishes if using data descriptors |
| Convenience for preflighting all entries | **Yes**, though metadata still requires validation and runtime quotas | Harder when all entries must be inspected prior to extraction |
| Non-seekable input | Not a direct option | Fits streaming input, though input quotas are still required |
| Stopping ZIP bombs | Requires actual streaming byte limits | Also requires actual streaming byte limits |
| File-writing rules | Application-controlled; must prevent traversal/overwrites | Application-controlled; not inherently safer |

**Do not confuse `getNextEntry()` with an entry having finished decompressing.** With `ZipInputStream`, read through the entry or close the entry before advancing to the next one per the API contract. Because metadata may be unknown, actual byte limits are even more essential.

When ZIPs are uploaded over a network, upload size limits must also be enforced **while receiving bytes**, rather than waiting for the entire upload to finish before checking. With `ZipFile`, uploads typically stream into a size-bounded staging file first before opening the ZIP.

## 9. Account for Resources Beyond Byte Counts

Size/count/ratio limits form the core of this lesson, yet do not mitigate every denial-of-service vector.

### 9.1. CPU and Time

An archive can burn substantial CPU during decompression/inspection even when final output stays below byte quotas. There is no built-in universal timeout on every ZIP `InputStream.read`. In production, enforce request deadlines, monitor elapsed time, and consider process/container isolation with CPU, RAM, and disk quotas.

Checking time inside the read loop helps stop between chunks, yet if **a single read call stalls**, an out-of-band timer or process-level watchdog is needed. `Thread.interrupt()` does not guarantee immediate termination of all decompression work.

### 9.2. Concurrent Request Volume

Capping each ZIP at 2 MiB output while accepting 10,000 concurrent archives still causes massive aggregate data and I/O. Bound **concurrency**, queues, total staging bytes, open file descriptors, and request rate. Quotas should cover both per-request and per-tenant/service scopes.

### 9.3. Name Length and Directory Depth

Very long entry names or deeply nested folder hierarchies can trigger path errors, metadata bloat, or trees hard to clean up. Real systems should define `MAX_NAME_LENGTH`, `MAX_DEPTH`, and platform-banned characters/device names.

Paths with special characters must be normalized under a cross-platform policy. For example, rejecting `\` in ZIP names is a simple policy preventing one OS from treating it as a separator while another treats it as a literal character.

### 9.4. File Permissions, Symlinks, and Race Conditions

ZIP archives can store Unix permission bits or metadata representing symbolic links. The standard `ZipEntry` API does not expose all POSIX archive attributes needed by a high-security extraction engine. Never infer that every entry not ending in `/` is guaranteed to be a safe regular file.

Furthermore, checking `output.startsWith(outputRoot)` is a **lexical** path check and does not protect against another process creating a symlink in a parent directory right after the check. Therefore:

- Use a fresh, isolated staging output directory modifiable only by the trusted process/domain.
- Do not follow symlinks that untrusted actors might place inside staging.
- Avoid extracting directly into paths with existing files or concurrent multi-actor writes.
- Under strict threat models, use handle-based path operations, sandboxing, and attribute checks.

`CREATE_NEW` blocks overwriting an existing file at the final leaf name, but **is not a complete guarantee** against symlink races in parent directories.

## 10. Checking Corrupted Archives and CRCs

ZIP includes CRC-32, and decompression APIs can detect certain structural or CRC corruptions. However:

- **CRC-32 is not a cryptographic signature or sender authentication mechanism.**
- Successful decompression does not mean data conforms to business schemas.
- Never bypass byte/count/ratio quotas just because CRC matches.
- Data can still be corrupted, misencoded, or crafted to exploit downstream processing stages.

To ensure trusted content from a publisher, use cryptographic hashes/digital signatures and a proper provenance verification chain rather than relying solely on ZIP CRCs.

## 11. Publishing Data After Extraction and Error Recovery

A request should follow clear states:

~~~text
RECEIVED
   |
   v
VALIDATING_METADATA
   |
   v
EXTRACTING_IN_STAGING
   |
   +---- error/quota/path failure ---> REJECT + CLEANUP
   |
   v
VALIDATING_CONTENT
   |
   +---- schema/hash failure -------> REJECT + CLEANUP
   |
   v
PUBLISHING
   |
   v
READY
~~~

**Important:** if a quota trips midway through writing the third entry, the first two entries may already exist in staging. Never treat staging as a successful extraction; mark it rejected and clean up. The example above deletes the entire temporary tree on exit, including failure paths.

In real applications, uploads may arrive from untrusted users. Clearly separate staging namespaces from published namespaces. Whether moving/renaming an entire directory is atomic depends on the filesystem; if atomic publication is needed, verify platform support and design the protocol accordingly rather than assuming every `Files.move` is atomic.

With retries, avoid publishing partial data or overwriting another request's output. Use per-request IDs/versions, checkpoints/audits, and idempotent cleanup.

## 12. Common Mistakes and Fixes

| Mistake | Why It Is Dangerous | Correct Approach |
| --- | --- | --- |
| Limiting only `.zip` file size | Small ZIPs can expand enormously | Limit total decompressed bytes and per-entry bytes |
| Limiting only total decompressed size | Many empty files still exhaust inodes/metadata | Limit entry count and file-creation resources |
| Limiting only one entry | Many small entries add up past the budget | Maintain a cumulative counter across all entries |
| Trusting `ZipEntry.getSize()` as absolute truth | Metadata may be missing or forged | Check metadata **and** actual streamed bytes |
| Checking size after writing everything | Disk may fill up before the check runs | Check inside each read loop before writing |
| Checking only compression ratio | Low-ratio files can still expand to huge sizes | Combine ratios with absolute byte limits |
| Dividing by `compressedSize=0` | Division-by-zero or miscalculated ratio | Distinguish empty payloads from positive payloads |
| Using `int` to count total bytes | Overflows on large data | Use `long` and overflow-safe comparisons |
| Skipping ZIP path validation | `../...` can write outside the destination | Normalize, reject traversal, and sandbox output |
| Extracting into an active directory | Overwrites files or exposes unvalidated data | Use fresh staging, `CREATE_NEW`, verify, then publish |
| Allowing unintentional duplicate paths | Silent overwrites, unpredictable behavior | Reject duplicates and account for filesystem rules |
| Auto-extracting ZIPs inside ZIPs unboundedly | Per-layer quotas fail to stop tree explosion | Limit depth and enforce a global budget |
| Lacking time/concurrency limits | CPU, I/O, or request queues get overwhelmed | Enforce timeouts, bounded queues, and sandboxes |
| Treating CRC as a security signature | Malicious data can still carry a valid CRC | Verify origin/schema/signatures per threat model |
| Returning success when extraction throws | Target directory may hold partial data | Never publish before verification; clean up failure paths |

## 13. Quota Calculation Scenarios

### Scenario A: Small ZIP, Massive Content

200 KiB archive containing one 50 MiB file after decompression. With `MAX_ENTRY = 1 MiB`, stop immediately when the uncompressed byte counter exceeds 1 MiB, regardless of what input metadata claimed.

The ~250:1 ratio also breaches 100:1; breaching **any one** quota suffices to reject.

### Scenario B: 200 Empty Files

Total decompressed size is 0 bytes, yet 200 entries exceed `MAX_COUNT = 100`. Reject even though ratio and byte sizes are tiny.

### Scenario C: 10 Files, 400 KiB Each

No single file exceeds `MAX_ENTRY = 1 MiB`, yet 4,000 KiB total exceeds `MAX_TOTAL = 2 MiB`. The policy must abort once the running total crosses the threshold.

### Scenario D: 500 KiB Decompressed and 1 KiB Compressed

Ratio = 500:1. With `MAX_RATIO = 100:1`, reject even though output bytes stay under `MAX_ENTRY`.

### Scenario E: Nested ZIPs

Outer ZIP extracts a 1 MiB child ZIP, which expands to 50 MiB. If the application auto-extracts child ZIPs, apply quotas across **the entire chain**; if nested archives are unsupported, treat the child ZIP as an opaque data file without extracting it further.

## 14. Production Deployment Checklist

Before accepting external ZIPs, confirm:

1. **Quantity policies:** cap archive size, entry count, total unpacked bytes, per-entry bytes, and compression ratio; enforce system/tenant-wide quotas.
2. **Streaming enforcement:** check actual bytes per chunk; never use `readAllBytes()` or unbounded `ByteArrayOutputStream` for untrusted payloads.
3. **Path safety:** block Zip Slip, absolute paths, duplicate names, cross-OS separators, symlinks, and excessive depth/name length.
4. **Staging:** create a fresh directory unmodifiable by other users during extraction, forbid overwrites, and never publish before verification.
5. **Format/schema:** allow only required file types with valid encodings/structures; never trust extensions blindly.
6. **Resource isolation:** deadlines, CPU/RAM/disk/inode/open-FD caps, and concurrent request limits.
7. **Error handling:** handle `IOException`, corrupted files, CRC errors, and stalled reads; clean up staging and mark rejected.
8. **Observability:** log request ID and rejection reason, count quota breaches, track time/bytes/entries, and monitor disk usage.
9. **Negative tests:** archives with many empty files, hyper-compressed payloads, invalid metadata, deeply nested entries, traversal, duplicates, ZIP-in-ZIP, and aborted uploads.
10. **Contract documentation:** publish valid limits for senders and return clear errors; never silently truncate extracted data.

## 15. Self-Check Questions

**Question 1.** 5 MiB ZIP, 6 MiB decompressed. `MAX_ZIP = 4 MiB`, `MAX_TOTAL = 10 MiB`. Is it accepted?

**Answer:** No. The input ZIP already exceeds `MAX_ZIP` even though total output is within limits.

**Question 2.** 101 entries, 0 bytes each; `MAX_COUNT = 100`. Is this a concern?

**Answer:** The archive breaches the entry-count policy. Large data is not needed to pressure metadata/inodes. Reject per `MAX_COUNT`.

**Question 3.** Does `getSize() == -1` mean the entry size is -1 bytes?

**Answer:** No. `-1` means the size is unknown. You must have a policy for it; never assume it is safe. When streaming is supported, count actual bytes and apply appropriate ratio checks.

**Question 4.** 10:1 ratio, yet the entry decompresses to 50 GiB with a 1 GiB per-entry limit. Should it pass because the ratio is low?

**Answer:** No. The absolute byte limit has been exceeded.

**Question 5.** While extracting the 20th file, total bytes hit `MAX_TOTAL`. The next `read()` returns 8192 bytes. What should happen?

**Answer:** Reject before writing the new chunk because `8192 > MAX_TOTAL - totalBytes`. Never let bytes beyond the quota hit disk.

**Question 6.** A ZIP contains entry `../../etc/config` with tiny total bytes. Is it safe?

**Answer:** No. A path trying to escape the output directory is a risk independent of size; reject path traversal.

**Question 7.** Extracting with `ZipInputStream` where size is unknown beforehand. Can you decide based solely on metadata?

**Answer:** No. Monitor actual output bytes while reading and use fallback ratio policies if exact `compressedSize` cannot be measured yet.

**Question 8.** Does a matching ZIP CRC prove a file came from a trusted source?

**Answer:** No. CRC is an accidental data-error check, not origin authentication or tamper-resistance like a digital signature.

## 16. Remember

- **Input ZIP size, per-entry decompressed bytes, and total decompressed bytes are three separate quotas.**
- **Entry count** stops archives with excessive files/folders even when total bytes are near 0.
- **Decompression ratio** catches aggressively expanding data, yet **never replaces absolute byte limits**.
- **Never trust ZIP metadata unconditionally**: validate both preflight declarations and actual bytes while extracting.
- **Do not stop at bomb defense:** reject traversal, control symlinks/overwrites, stage cleanly, and limit concurrency.
- **Correctness requires enforcing quotas before every write**, handling errors cleanly, and publishing output only once the entire pipeline succeeds.
