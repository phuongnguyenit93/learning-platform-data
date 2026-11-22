# Extracting to the Right Target Directory and Handling Entry Paths in Java

## 1. Goal: Extract to the Right Place Without Writing Outside Permitted Boundaries

In Java I/O, a ZIP archive can contain multiple `ZipEntry` items. Each entry has a **name** (e.g., `docs/manual.txt`), compressed data, and metadata. When extracting to disk, a program must convert an **untrusted entry name** into a `Path` on the target machine, create parent directories, and write data into an allowed file.

A common mistake is joining the entry name onto the destination directory without checking:

~~~java
Path target = outputDir.resolve(entry.getName());
Files.copy(zip, target); // dangerous if entry.getName() is unchecked
~~~

This is an **anti-pattern snippet**, not standalone runnable code. If an entry is named `../../outside.txt`, the write can escape `outputDir`. This vulnerability is known as **Zip Slip** (path traversal during extraction).

A proper extractor must ensure:

1. Every file and directory stays **inside a target root directory** specified by the application.
2. Entries contain no absolute paths, `..`, dangerous separators, or policy-incompatible names.
3. No traversal through **symbolic links** or path components controlled by someone else.
4. Existing files are not overwritten unless permitted by the user/policy.
5. Limits are enforced on **entry count, name length, decompressed bytes, and total resources**.
6. Streams/channels are released properly, archive errors are caught, and a failed copy is never treated as success.
7. A cleanup plan exists for partially created files on failure; multi-entry extraction **is not automatically an atomic transaction**.

This article focuses on extracting ZIPs with `java.util.zip` and `java.nio.file` on **Java 17+**. For `.tar.gz`, GZIP only decompresses the outer stream, while TAR needs an appropriate parser; the entry-name handling principles below remain useful, though TAR APIs are not in `java.util.zip`.

## 2. Understanding `ZipEntry` Names and the Target Directory

Example inside a ZIP:

~~~text
Archive backup.zip
  docs/
  docs/readme.txt
  docs/config/app.properties
  images/logo.png
~~~

Suppose the application wants to extract into:

~~~text
/opt/myapp/imports/job-001/
~~~

After safe processing, the expected result is:

~~~text
/opt/myapp/imports/job-001/
  docs/
    readme.txt
    config/
      app.properties
  images/
    logo.png
~~~

On Windows, the root directory might be `C:\data\imports\job-001` instead of a Linux path. **ZIP entry names normally use `/` as the separator**; never treat `\` as a valid subpath separator when importing untrusted archives.

### 2.1. `ZipEntry` Is Not `java.nio.file.Path`

`ZipEntry.getName()` returns a **String taken from the archive**, not a path normalized by the operating system or verified for access permissions. For example:

~~~java
ZipEntry entry = zip.getNextEntry();
String name = entry.getName(); // data coming from the archive
~~~

`name` may represent a regular file, a directory (by convention ending with `/`), or an unsafe name. Java does not automatically confine that name inside your destination for you.

**Never pass `entry.getName()` directly as an output path** to `new File(...)`, `Files.copy(...)`, `Files.newOutputStream(...)`, or `Files.createDirectories(...)` without validation.

### 2.2. Relative Paths Must Stay Under the Root Directory

Given a target directory `root`, code commonly builds:

~~~java
Path target = root.resolve(entry.getName()).normalize();
if (!target.startsWith(root)) {
    throw new IOException("Entry outside output directory");
}
~~~

This is a **required baseline check, but incomplete**. It must be paired with:

- `root` being a **safely determined absolute path**, never comparing a relative root with an absolute target.
- Validating the entry name **before use**, especially for absolute paths, `..`, backslashes, Windows drive/UNC prefixes, and null bytes.
- Checking symbolic links along parent directory components and preventing path swapping via race conditions when other actors can modify the filesystem.
- Overwrite policies and resource limits.

When `root` is absolute and normalized, `target.startsWith(root)` is a `Path`-component comparison, **not** a string prefix check like `String.startsWith(...)`. For instance, `/safe/outside.txt` starts with the string `"/safe/out"`, yet **is not under** the path `/safe/out` by path components.

## 3. Untrusted Entry Name Patterns

The following table shows cases to block or handle under explicit policies:

| Entry Name | Risk | Typical Safe Handling |
|---|---|---|
| `docs/readme.txt` | Normal relative path | Acceptable if other checks pass |
| `docs/config/app.yml` | Needs parent directory creation | Validate then create directories safely |
| `../outside.txt` | Escapes one level up | **Reject** |
| `../../secret.txt` | Escapes multiple levels | **Reject** |
| `/etc/passwd` | Unix absolute path | **Reject** |
| `C:/Windows/temp.txt` | Windows drive-absolute | **Reject** |
| `C:relative.txt` | Windows drive-relative / name with colon | **Reject** under portable policy |
| `\\server\share\file.txt` | Windows UNC or foreign separator | **Reject** backslashes/UNC |
| `docs\..\outside.txt` | Backslash traversal on Windows | **Reject** |
| `docs/./a.txt` | Unnecessary `.` component | Should reject under strict policy |
| `docs//a.txt` | Empty segment / anomalous path | Should reject |
| `docs/../a.txt` | Contains `..` even if normalized stays inside | Should reject the name upfront |
| `docs/a.txt:stream` | Alternate Data Stream (Windows) | Reject colons |
| Repeated `docs/a.txt` | Overwrite/collision | Reject duplicates or apply explicit policy |
| Very long / deeply nested name | Exhaustion, filesystem errors | Limit length and depth |

Examples like `C:`, `\`, and ADS are Windows-specific. To write a cross-platform extractor and avoid parsing differences across filesystem providers, **do not allow these forms merely because they look harmless on Linux**.

### Checking Even When Normalization Stays Inside

`docs/../file.txt` becomes `file.txt` after `normalize()`, remaining inside the root. Yet allowing `..` adds complexity, makes name checks inconsistent, and invites OS discrepancies. For a strict extractor policy, **reject every `..` and `.` path component**, then resolve/normalize as an extra fallback layer.

### Directory Entries

`ZipEntry.isDirectory()` usually recognizes names ending with `/`. An entry `docs/` is a directory; code must create a directory rather than opening an output stream to write file contents. However, a valid ZIP may **omit a separate `docs/` entry** and contain only `docs/readme.txt`, so the extractor must create parent directories as needed after validating the path.

Do not rely solely on trailing `/` to identify **every type of filesystem object in third-party ZIPs**; some archives store Unix file modes or symlink metadata beyond the simple surface `ZipInputStream` exposes.

## 4. Zip Slip: normalize, startsWith, and Defense Boundaries

A flawed extractor might do:

~~~java
Path target = root.resolve(entry.getName()); // Not normalized / not validated.
Files.createDirectories(target.getParent());
Files.copy(zip, target);
~~~

When the entry is `../attack.txt`, `resolve` produces a path escaping `root`. `Files.createDirectories` and `Files.copy` can then write to unintended locations or affect resources outside the extraction scope.

A better validation approach:

~~~java
Path root = outputDir.toRealPath();
String name = entry.getName();

// Block untrusted forms before calling Path APIs.
if (name.isEmpty() || name.startsWith("/")
        || name.indexOf('\\') >= 0
        || name.indexOf('\0') >= 0) {
    throw new IOException("Unsafe entry name");
}

Path target = root.resolve(name).normalize();
if (target.equals(root) || !target.startsWith(root)) {
    throw new IOException("ZIP entry escaped target directory");
}
~~~

This is **illustrative code**, omitting component splitting to reject `..`, `.`, colons, empty segments, symlinks, and quotas. The complete runnable example in Section 8 implements those checks.

### Why Not Compare Raw Strings?

Code like:

~~~java
if (!target.toString().startsWith(root.toString())) {
    throw new IOException("Unsafe target");
}
~~~

is an **anti-pattern**. If `root` is `/srv/out`, then `/srv/outside/a.txt` starts with the same string prefix. `Path.startsWith(Path)` compares path components, avoiding this bug.

### Why Do `toAbsolutePath + normalize` Not Stop Symlinks?

`normalize()` handles syntactic `.` and `..` segments; it **does not walk the filesystem to detect symbolic links**. Suppose `docs` under `root` is already a symlink pointing to `/tmp/other`. The path `root/docs/file.txt` can still escape `root` **in physical filesystem reality** even though name, `normalize`, and `startsWith` checks all pass.

Therefore, you must account for **filesystem state**, not just Strings and Paths.

## 5. Symlinks, Hardlinks, and TOCTOU

### 5.1. Directory Symlinks in the Target Directory

If the target directory allows untrusted components, code like:

~~~java
Files.createDirectories(target.getParent());
Files.newOutputStream(target);
~~~

can traverse an existing symlink on disk and write elsewhere. Basic defenses:

- Extract into a **fresh, empty, private directory** beneath an application-controlled parent.
- When walking directory components, use `Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS)` so **symlinks are never treated as directories**.
- When creating files, use `StandardOpenOption.CREATE_NEW` to avoid overwriting an existing file or symlink at the final path.
- Never automatically create symlinks/hardlinks from entry metadata without a strict security policy.

### 5.2. Limits of Check-Then-Use

Checking `NOFOLLOW_LINKS` and then calling `Files.newOutputStream(...)` **does not form an atomic security transaction** across steps. An attacker able to modify the target directory can swap a directory for a symlink **between the check and opening the file**. This is a **TOCTOU — time of check to time of use** flaw.

If your threat model includes another process **concurrently modifying the target directory directly**, stronger mechanisms are needed: private directory isolation/permissions, OS sandboxing, or descriptor-relative operations such as `SecureDirectoryStream` where supported by the provider. Never claim that `normalize()`, `NOFOLLOW_LINKS`, or `CREATE_NEW` alone makes code immune to all race conditions.

### 5.3. Example Code Using a Fresh Directory

The example in Section 8 intentionally requires `Files.createDirectory(destination)` **to create a new directory**. If the directory already exists, the program rejects instead of mixing entries into old data. That prevents overwrites and reduces the risk of pre-existing symlinks left in the tree. Still, **the parent of `destination` must remain trusted**, and untrusted actors must not modify it during extraction.

### 5.4. Duplicate Names and Filesystem Collisions

Repeated `a.txt` entries can cause later files to overwrite earlier ones. Additionally, a filesystem may treat `A.txt` and `a.txt` as the same file, or normalize Unicode/special names according to OS rules. Therefore, besides maintaining a `Set<Path>` to catch normalized duplicates, still use **`CREATE_NEW`** so existing files cannot be overwritten. An extractor targeting environments with special filenames also needs rules for reserved device names, trailing dots/spaces, and Unicode normalization.

## 6. Extracting Entry by Entry with `ZipInputStream`

`java.util.zip.ZipInputStream` reads a ZIP input stream, advancing through entries with `getNextEntry()`:

~~~java
try (ZipInputStream zip = new ZipInputStream(
        Files.newInputStream(zipPath), StandardCharsets.UTF_8)) {
    ZipEntry entry;
    while ((entry = zip.getNextEntry()) != null) {
        // 1. Validate entry name and root-bounded path.
        // 2. If directory: create directory safely.
        // 3. If file: create new file, copy in chunks, and count bytes.
        // 4. closeEntry() after finishing the entry.
        zip.closeEntry();
    }
}
~~~

This is an **illustrative skeleton, not a standalone extractor**; real code must actually decompress entry data rather than calling `closeEntry()` alone and treating files as extracted.

API points:

- `getNextEntry()` advances to the next entry and returns `null` at the end.
- `zip.read(buffer)` inside an entry returns **decompressed bytes**; `-1` means end of that entry's data, **not** end of the archive.
- `closeEntry()` finishes reading the current entry and prepares to move to the next one.
- `ZipInputStream` does not support random lookup by name like `ZipFile.getEntry(name)`.
- Each entry maps to its own target file, though parent directory entries are not guaranteed to appear in the ZIP.
- For untrusted uploads/ZIPs, never call `zip.readAllBytes()` and write: decompressed output can be huge.

### ZIP Bombs and Quotas

An archive can be compact yet expand into gigabytes. **Do not trust `ZipEntry.getSize()`** because metadata may be missing or untrustworthy. Count **the actual bytes returned by `zip.read(...)`** during decompression.

Quotas to define explicitly:

| Quota | Why? |
|---|---|
| Max entry count | Prevents millions of empty files |
| Decompressed bytes per entry | Prevents a single huge inflated file |
| Total decompressed bytes | Caps overall archive size |
| Entry name length | Blocks overly long names/path abuse |
| Directory depth | Reduces deeply nested path tree risks |
| Time/deadline and CPU | Prevents runaway CPU/infinite processing |
| Actual file/directory count | Prevents inode exhaustion |
| Disk quota space | Prevents filling the partition |

Limits in the demo are **illustrative values**, not universal security thresholds for all applications.

## 7. Safe Extractor Strategy: Data, Validation, Writing, Finalization

An implementable workflow consists of:

1. Identify the input ZIP path (source) and choose a **trusted parent** for output.
2. Create a **fresh output directory**; if it already exists, reject or follow an explicit staging/merge policy.
3. Read `ZipEntry.getName()`, check length and every segment, rejecting disallowed separators/`..`/absolute paths/drive prefixes.
4. Resolve the path against the canonicalized root, normalize, and verify `target.startsWith(root)` and `target` is not equal to `root`.
5. Use a set to detect duplicate entry paths after normalization.
6. For directories: create each directory component without following symlinks.
7. For regular files: create the new file using `CREATE_NEW` and stream-decompress in chunks.
8. Add every read chunk to per-entry and total budgets; abort **before writing past any quota**.
9. Call `closeEntry()` and handle CRC/corrupt-ZIP exceptions per policy; on file error, clean up partial files.
10. After the whole archive: finalize the stream; publish output to the final location only once the entire archive and structure are verified.

**Note:** if the tenth entry fails, the first nine entries may already have been created. Production systems therefore typically use a **staging directory**, publishing/moving to the final destination only when full extraction succeeds; verify atomicity/overwrite semantics of the move operation on the actual filesystem. Multi-file operations do not automatically form a transaction.

## 8. Complete Java 17+ Program: Baseline Safe Extraction

The following example creates a valid two-file ZIP, a malicious ZIP containing `../escape.txt`, and attempts to extract both. The program requires a **fresh, empty target directory**, blocks path traversal and anomalous names, refuses to follow existing directory symlinks, prevents file overwrites, caps decompressed size, and cleans up temporary files.

This is a **simple, runnable design example**, not a sandbox against adversaries with concurrent race permissions on the same filesystem; see Section 5 on TOCTOU.

**File: `SafeZipExtractDemo.java`**

~~~java
import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Comparator;
import java.util.HashSet;
import java.util.Set;
import java.util.stream.Stream;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;
import java.util.zip.ZipOutputStream;

public class SafeZipExtractDemo {
    private static final int MAX_ENTRIES = 100;
    private static final int MAX_NAME_LENGTH = 240;
    private static final int MAX_DEPTH = 16;
    private static final long MAX_ENTRY_BYTES = 1_000_000L;
    private static final long MAX_TOTAL_BYTES = 3_000_000L;

    // Validate ZIP name under a portable policy, then build path under root.
    private static Path safeTarget(Path root, String name)
            throws IOException {
        if (name.isEmpty() || name.length() > MAX_NAME_LENGTH
                || name.startsWith("/") || name.indexOf('\\') >= 0
                || name.indexOf('\0') >= 0) {
            throw new IOException("Unsafe ZIP entry path");
        }

        String body = name.endsWith("/")
                ? name.substring(0, name.length() - 1)
                : name;
        String[] parts = body.split("/", -1);
        if (parts.length > MAX_DEPTH) {
            throw new IOException("Unsafe ZIP entry path");
        }

        for (String part : parts) {
            if (part.isEmpty() || part.equals(".")
                    || part.equals("..") || part.indexOf(':') >= 0) {
                throw new IOException("Unsafe ZIP entry path");
            }
        }

        Path target = root.resolve(name).normalize();
        if (target.equals(root) || !target.startsWith(root)) {
            throw new IOException("Unsafe ZIP entry path");
        }
        return target;
    }

    // Walk each directory component and reject symlinks.
    private static void ensureDirs(Path root, Path dir)
            throws IOException {
        Path current = root;
        for (Path component : root.relativize(dir)) {
            current = current.resolve(component);
            if (Files.exists(current, LinkOption.NOFOLLOW_LINKS)) {
                if (!Files.isDirectory(
                        current, LinkOption.NOFOLLOW_LINKS)) {
                    throw new IOException("Unsafe directory component");
                }
            } else {
                Files.createDirectory(current);
            }
        }
    }

    static long extract(Path archive, Path newDestination)
            throws IOException {
        // Requires non-existent directory. Parent must be trusted.
        Path root = Files.createDirectory(newDestination).toRealPath();
        Set<Path> seen = new HashSet<>();
        int entries = 0;
        long total = 0;

        try (ZipInputStream zip = new ZipInputStream(
                Files.newInputStream(archive), StandardCharsets.UTF_8)) {
            ZipEntry entry;

            while ((entry = zip.getNextEntry()) != null) {
                if (++entries > MAX_ENTRIES) {
                    throw new IOException("Too many entries");
                }

                Path target = safeTarget(root, entry.getName());
                if (!seen.add(target)) {
                    throw new IOException("Duplicate ZIP path");
                }

                if (entry.isDirectory()) {
                    ensureDirs(root, target);
                    zip.closeEntry();
                    continue;
                }

                ensureDirs(root, target.getParent());
                boolean created = false;
                try {
                    try (OutputStream out = Files.newOutputStream(
                            target, StandardOpenOption.CREATE_NEW,
                            StandardOpenOption.WRITE)) {
                        created = true;
                        byte[] buffer = new byte[8192];
                        long count = 0;

                        for (int n; (n = zip.read(buffer)) != -1; ) {
                            if (n == 0) {
                                throw new IOException(
                                        "No decompression progress");
                            }
                            if (n > MAX_ENTRY_BYTES - count
                                    || n > MAX_TOTAL_BYTES - total) {
                                throw new IOException(
                                        "Decompressed data limit");
                            }

                            out.write(buffer, 0, n);
                            count += n;
                            total += n;
                        }
                    }
                    zip.closeEntry();
                } catch (IOException | RuntimeException ex) {
                    if (created) {
                        try {
                            Files.deleteIfExists(target);
                        } catch (IOException cleanup) {
                            ex.addSuppressed(cleanup);
                        }
                    }
                    throw ex;
                }
            }
        }
        return total;
    }

    // Demo helper only: creates two small archives for testing.
    private static void createZip(
            Path archive, String[] names, String[] bodies)
            throws IOException {
        try (ZipOutputStream zip = new ZipOutputStream(
                Files.newOutputStream(archive),
                StandardCharsets.UTF_8)) {
            for (int i = 0; i < names.length; i++) {
                zip.putNextEntry(new ZipEntry(names[i]));
                zip.write(bodies[i].getBytes(StandardCharsets.UTF_8));
                zip.closeEntry();
            }
        }
    }

    public static void main(String[] args) throws IOException {
        Path work = Files.createTempDirectory("zip-safe-example-");
        try {
            Path good = work.resolve("good.zip");
            Path evil = work.resolve("evil.zip");

            createZip(
                    good,
                    new String[]{"docs/a.txt", "docs/b.txt"},
                    new String[]{"Hello ZIP", "Java 17"});
            createZip(
                    evil,
                    new String[]{"../escape.txt"},
                    new String[]{"not allowed"});

            Path goodOut = work.resolve("good-out");
            long copied = extract(good, goodOut);
            System.out.println("bytes=" + copied);
            System.out.println(
                    "a=" + Files.readString(
                            goodOut.resolve("docs/a.txt")));
            System.out.println(
                    "b=" + Files.readString(
                            goodOut.resolve("docs/b.txt")));

            try {
                extract(evil, work.resolve("bad-out"));
                System.out.println("blocked=false");
            } catch (IOException rejected) {
                System.out.println(
                        "blocked=" + rejected.getMessage());
            }

            System.out.println(
                    "escaped=" + Files.exists(
                            work.resolve("escape.txt")));
        } finally {
            // work is a fresh temporary directory owned by the demo.
            try (Stream<Path> paths = Files.walk(work)) {
                for (Path p : paths
                        .sorted(Comparator.reverseOrder())
                        .toList()) {
                    Files.deleteIfExists(p);
                }
            }
        }
    }
}
~~~

**Compile/run with JDK 17+:**

~~~bash
javac SafeZipExtractDemo.java
java SafeZipExtractDemo
~~~

**Stdout verified on the JDK:**

~~~text
bytes=16
a=Hello ZIP
b=Java 17
blocked=Unsafe ZIP entry path
escaped=false
~~~

### Step-by-Step Result Explanation

- `docs/a.txt` holds the UTF-8 string `Hello ZIP` (9 bytes); `docs/b.txt` holds `Java 17` (7 bytes), totaling `16` extracted bytes.
- Even though the archive lacks a separate `docs/` entry, `ensureDirs` safely creates the needed directory before writing files.
- `Files.newOutputStream(..., CREATE_NEW, WRITE)` requires the target file path not to exist yet; if a file or symlink already sits there, creation fails without overwriting.
- `../escape.txt` is rejected **before any file is created** thanks to component-level path checks; output shows `blocked=Unsafe ZIP entry path`.
- `escaped=false` confirms the program did not create `escape.txt` outside `bad-out` in this demo.
- `Files.createTempDirectory` gives the demo a dedicated temporary parent, and `finally` deletes the files created by the demo.

### Security Limitations of the Demo

1. **No guarantee against concurrent race conditions** from another process permitted to modify parent/output simultaneously; that is the `TOCTOU` problem. On servers, extract only into a private service-owned directory with strict permissions, or use race-resistant primitives.
2. **Not atomic across the whole archive:** if a later entry fails, earlier entries may remain in `newDestination`. In production, extract into staging, validate everything, and publish per policy. Clean up staging on failure.
3. **Does not recreate symlink/hardlink/permission/ownership metadata** from the ZIP. This is an intentional attack-surface reduction in the example: entries are handled strictly as directories or regular files, never creating links from metadata. If symlink preservation is required, validate entry types, link targets, permissions, and root confinement per a dedicated threat model.
4. **Quotas are illustrative thresholds**: max 100 entries, 240 name characters, 16 levels, 1,000,000 bytes/entry, and 3,000,000 bytes total. Real servers also need deadlines, CPU quotas, actual created-directory caps, disk quotas, and request rate limits.
5. **Temp cleanup in `finally`** can fail on unusual filesystems or if another actor holds a file lock. Production needs logging and proper retry/retention policies, never deleting directories it does not own.
6. **Source data in the demo is self-created** using UTF-8. For third-party ZIPs, entry-name charsets and payload charsets may differ; apply realistic encoding policies.

## 9. Production Improvements

### 9.1. Staging Before Publishing

Instead of writing straight into a user-visible directory:

1. Create a fresh staging directory inside a service-controlled area.
2. Extract into staging after validating entries.
3. Check file counts, sizes, formats, checksums, or signatures as needed.
4. Only when the entire archive succeeds, move/rename staging to the final destination.
5. Implement rollback/deletion of staging on failure and cleanup after service crashes.

**Never assume `Files.move(..., ATOMIC_MOVE)` is always supported** or implies transactional semantics across every file store. It may throw `AtomicMoveNotSupportedException`; if the target exists, overwrite semantics vary by policy. On many filesystems, directory renames are atomic only under narrow conditions and still do not replace integrity checks.

### 9.2. Using an Already-Existing Target Directory

If a product must extract into an existing directory, the policy must be explicit:

- Are same-named files allowed to be overwritten?
- Are duplicate entry names within the same archive allowed?
- What if the target contains symlinks, junctions/reparse points (Windows), or hardlinks?
- Must pre-existing non-archive files in the directory remain untouched?
- Must file permissions, ownership, or timestamps be reconciled?
- Can another process create/delete/rename paths while extraction is running?

The demo pattern **by design does not support merging into an existing directory**; add explicit logic rather than swapping `createDirectory` for `createDirectories` and assuming everything remains safe.

### 9.3. Checking Unicode, Case Folding, and OS Filenames

Across different filesystems, distinct entry names can collide on the same file or be rejected:

- `a.txt` and `A.txt` collide on case-insensitive systems.
- Unicode strings can have multiple normalization forms.
- On Windows, reserved device names like `CON`, `PRN`, `AUX`, or `NUL` have special restrictions, even with extensions added.
- Names with trailing dots/spaces may be stripped or treated specially depending on the provider.
- `:` can represent an Alternate Data Stream on NTFS, which is why the demo's portable policy bans it.

`CREATE_NEW` blocks overwriting an actually existing file, yet production systems should validate invalid names upfront and report clear errors.

### 9.4. Preventing Zip Bombs and Disk Exhaustion

Even with byte quotas, an archive can declare or generate countless empty entries. Combine **count quota + byte quota + depth/path quota + CPU/deadline + disk quota**. Counting actually decompressed bytes is critical because ZIP metadata sizes may be unknown (`ZipEntry.getSize() == -1`) or untrustworthy.

Never use `ZipInputStream.readAllBytes()` on untrusted entries. In the demo, a fixed 8,192-byte buffer checks limits on each chunk **before writing**. The comparison `n > MAX_TOTAL_BYTES - total` also prevents integer overflow with positive quotas.

### 9.5. Integrity and Signatures

ZIPs typically include **CRC-32** to detect transmission/storage corruption. CRC-32 **is not a mechanism against intentional tampering**. If an archive is used as a deployment/software/configuration package, use digital signatures/MACs or hashes verified from a trusted source. A file with a valid CRC can still carry a malicious payload or dangerous paths if left unvalidated.

`ZipInputStream` reads local entry headers; `ZipFile` uses the central directory for named entry access. For untrusted archives with inconsistent metadata between local headers and the central directory, choosing between parsers/APIs can affect enforcement policies. Never assume scanning a name list once guarantees every byte/entry the extractor processes matches. **Validate each actual entry at the moment it is processed**.

## 10. Common Mistakes

1. **Joining `entry.getName()` directly onto output and writing immediately.** Prone to Zip Slip.
2. **Comparing only `target.toString().startsWith(root.toString())`.** Can confuse `/root/outside` with `/root/out`.
3. **Using only `normalize()` and believing symlinks are handled.** `normalize()` does not inspect the filesystem.
4. **Allowing `..` because after normalization it stays inside root.** Makes policy inconsistent and raises bypass risk.
5. **Filtering only `/` while forgetting backslashes on Windows.** Can let traversal slip through.
6. **Assuming `Path.isAbsolute()` on Linux blocks `C:\...` on Windows.** Validate portable name rules upfront.
7. **Calling `Files.createDirectories` on any parent inside an existing directory tree.** May follow symlinks.
8. **Using default `Files.newOutputStream(target)`.** Can truncate existing files; use `CREATE_NEW` when forbidding overwrites.
9. **Allowing multiple entries with the same name to overwrite each other.** Can swap a valid payload for a malicious one.
10. **Using `readAllBytes()` or unbounded `Files.copy` on untrusted ZIPs.** Can exhaust RAM/disk via a Zip bomb.
11. **Assuming `ZipEntry.getSize()` is always accurate.** May be `-1` or spoofed metadata.
12. **Treating `zip.read() == -1` as end of the entire archive.** That is entry EOF; continue calling `getNextEntry()`.
13. **Not closing `ZipInputStream`/output streams.** Causes leaks or truncated files.
14. **Treating a `docs/` entry as a regular file.** Create a directory; do not write payload as a file.
15. **Assuming a failed extraction automatically rolled back all files.** Previously written entries may still remain on disk.
16. **Using `NOFOLLOW_LINKS` + check and claiming TOCTOU is eliminated.** If another actor can modify the filesystem, isolation and stronger primitives are still required.
17. **Trusting CRC-32 as a publisher's digital signature.** CRC does not prevent tampering.
18. **Extracting uploaded ZIP archives into a shared publicly writable folder.** Increases the risk of paths being swapped mid-run.

## 11. Self-Check

**Question 1.** Why is `root.resolve(entry.getName()).normalize().startsWith(root)` necessary but not sufficient?

**Answer:** It verifies containment by `Path` components, yet does not block platform-specific names, filesystem symlinks, TOCTOU races, overwrites, duplicates, or resource exhaustion.

**Question 2.** An entry named `../../escape.txt` is extracted under `/data/uploads/job1`. Should the file be created?

**Answer:** No. Names containing `..` must be rejected. Used directly, it could escape `job1` and write into another directory.

**Question 3.** A ZIP contains only `docs/a.txt` with no `docs/` entry. Can it still be extracted properly?

**Answer:** Yes. After validating the name, the extractor safely creates the parent directory `docs` and then creates `a.txt`.

**Question 4.** Why is `CREATE_NEW` safer than opening an output stream with default options?

**Answer:** Because it requires creating a brand-new file and fails if the target path already exists (including symlinks), avoiding default open-mode overwrite/truncation.

**Question 5.** Why are Zip bomb defenses still needed even after path validation is secure?

**Answer:** Path validation only restricts where writes go; a tiny archive can still generate excessive files or massive decompressed data, exhausting CPU/RAM/disk.

**Question 6.** The output root is owned by the application, yet another process is allowed to rename subdirectories concurrently. Is checking `NOFOLLOW_LINKS` safe enough?

**Answer:** No. Check-then-open can be raced; isolation, private directory permissions, or appropriate TOCTOU-resistant APIs are needed.

**Question 7.** Extraction fails after writing 5 of 10 entries. Do the earlier files disappear automatically?

**Answer:** No. Transactional-like behavior requires staging, cleanup policies, and publishing only after full validation succeeds.

### Official Java 17 Documentation

- [ZipInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipInputStream.html)
- [ZipEntry](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipEntry.html)
- [ZipOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipOutputStream.html)
- [ZipFile](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipFile.html)
- [Path: resolve, normalize, startsWith](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html)
- [Files: createDirectory, newOutputStream, exists, isDirectory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [StandardOpenOption.CREATE_NEW](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardOpenOption.html#CREATE_NEW)
- [SecureDirectoryStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/SecureDirectoryStream.html)
