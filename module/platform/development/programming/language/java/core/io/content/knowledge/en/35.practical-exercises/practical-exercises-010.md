# Java 17 Practice: Bounded ZIP Packing, Unpacking, and Entry Path Validation

## 1. Practice Objectives and Expected Outcomes

This exercise builds a **ZIP packer/extractor** using Java Core I/O with zero external dependencies. The program packs a directory tree into a `.zip` file, unpacks it into a fresh destination directory, and proactively rejects inputs that violate policy.

Once finished, you will be able to:

1. Use `Files.walkFileTree` to traverse a file tree **without following symbolic links** by default.
2. Use `ZipOutputStream` to create archives containing both files and **empty directories**.
3. Use `ZipInputStream` to process one `ZipEntry` at a time without loading all files into RAM.
4. Enforce bounds on **entry count, depth, name length, per-file bytes, and total uncompressed bytes**.
5. Detect **Zip Slip** via entries named `../escape.txt`, absolute names, or unsafe separators.
6. Apply `Path.resolve`, `normalize`, `Path.startsWith(Path)`, `NOFOLLOW_LINKS`, and `CREATE_NEW` within their proper scope.
7. Create parent directories for child files even when the ZIP omits standalone directory entries.
8. Distinguish successful data writes, path checks, **archive integrity**, and resistance to filesystem races.
9. Run a **round-trip** test and then test two problematic archives: traversal and uncompressed byte limit exceeded.

Expected output:

~~~text
packedBytes=9
unpackedBytes=9
sameA=true
emptyDirectory=true
zipSlip=Unsafe entry name
limit=Uncompressed byte limit
outsideCreated=false
~~~

**Note:** This is a foundational design and defense-in-depth exercise. It **does not claim to be a complete sandbox against an adversary able to modify the filesystem concurrently**. The final section explains how to elevate this to a production solution with staging, permission controls, and TOCTOU mitigation.

## 2. Specific Problem Statement

Suppose the input is:

~~~text
source/
  docs/
    a.txt       (Alpha)
    b.txt       (Beta)
  empty/
~~~

The program produces:

~~~text
bundle.zip
  docs/
  docs/a.txt
  docs/b.txt
  empty/
~~~

Then, unpacking into a **new output directory**, we expect:

~~~text
output/
  docs/
    a.txt       (Alpha)
    b.txt       (Beta)
  empty/
~~~

At the same time, the extractor must reject:

~~~text
../escape.txt              -> writes outside output
/srv/app/config.txt        -> absolute path
C:/Windows/Temp/a.txt      -> name with ':' like a Windows drive
docs\..\escape.txt         -> backslash traversal
docs/./a.txt               -> non-canonical name per policy
docs/../a.txt              -> '..' segment
docs/a.txt (repeated)      -> duplicate/overwrite
large.txt (expands past quota) -> zip bomb / disk exhaustion
~~~

ZIP is an **archive of multiple named entries**, not a single GZIP-compressed byte stream. `ZipOutputStream` and `ZipInputStream` work sequentially with `ZipEntry` objects. The ZIP format can store each entry as `DEFLATED` or `STORED`; ZIP **does not mean every entry is compressed**.

## 3. Designing Policy Before Writing Code

Do not write `extract(zip, target)` first and try to patch dangerous names afterward. Define the policy clearly upfront:

| Constraint | Value in Example | Meaning |
|---|---:|---|
| `maxEntries` | 20 | Caps total file and directory entries |
| `maxDepth` | 8 | Caps number of entry name segments |
| `maxName` | 100 | Caps entry name string length |
| `maxFileBytes` | 128 | Caps **uncompressed** bytes per file |
| `maxTotalBytes` | 256 | Caps total **uncompressed** bytes |
| Output dir | Must not exist yet | Avoids merging/overwriting old data |
| Input symlink | Rejected | Prevents packing content outside allowed tree |
| Output symlink | Not followed when traversing parents | Reduces risk of writing off-target |
| Duplicate file path | Rejected | Prevents replacing data |
| Abnormal entry name | Rejected | Prevents traversal/platform-specific paths |
| Read/write memory | 8192-byte buffer | Never call `readAllBytes()` on untrusted files |

The tiny `128`/`256`-byte thresholds make **this practice exercise** easy to test; they are **not production quota recommendations**. In real systems, choose quotas based on business requirements, memory/disk budgets, concurrent users, timeouts, and system limits.

We use a Java `record` to hold the policy:

~~~java
record Limits(
        int maxEntries,
        int maxDepth,
        int maxName,
        long maxFileBytes,
        long maxTotalBytes) {
}
~~~

This is an **excerpt from the main class in section 6**, not a standalone runnable file. In production code, validate that all values passed into the record are positive/valid in a constructor or factory; this example initializes with controlled constants.

## 4. Step 1 — Traversing the Source to Pack Without Leaving the Tree

`Files.walkFileTree(root, visitor)` by default **does not follow symbolic links** unless `FOLLOW_LINKS` is passed. With `SimpleFileVisitor`:

- `preVisitDirectory`: on visiting a directory, writes a directory entry ending with `/`.
- `visitFile`: on visiting a regular file, writes a file entry and streams chunks.
- On encountering a symlink or unsupported file type, the example **rejects** it rather than silently following or copying.
- If source files change during packing, handle that via dedicated testing/threat modeling; `walkFileTree` does not capture an immutable snapshot of the whole tree.

### Producing Machine-Independent Entry Names

`Path` on Windows may render separators differently from Linux. Names inside a ZIP should be normalized to **relative names using `/`**:

~~~java
static String relativeName(Path root, Path path) {
    return root.relativize(path).toString().replace('\\', '/');
}
~~~

This is an illustrative method. Never store absolute source file paths inside a ZIP: extractors only want relative names under their chosen destination directory.

**Never create the ZIP inside the source tree being traversed.** If the output archive sits inside the source directory, traversal can encounter the growing ZIP file itself and make the input unstable. The example rejects `archivePath.startsWith(sourceRoot)` after canonicalizing root.

### Preserving Empty Directories

If you only emit entries for files, an `empty/` directory with no children would vanish. Therefore, for directories (excluding root), emit `ZipEntry("relative/path/")`. Directory entries **carry no regular file payload** in the demo.

## 5. Step 2 — Defining Allowed Entry Names and Target Paths

### 5.1. Why Is `entry.getName()` Untrusted Data?

ZIP entry names are chosen by whoever built the archive. Java's `ZipInputStream.getNextEntry()` returns a `ZipEntry` yet **does not automatically verify that the filename is safe to write into an output directory**.

Counter-example:

~~~java
Path target = outputRoot.resolve(entry.getName());
Files.copy(zipInputStream, target); // NEVER do this with unchecked names.
~~~

This is a **counter-example snippet**, not standalone runnable code. With the name `../escape.txt`, resolving can place the file outside `outputRoot`. That is **Zip Slip / path traversal**.

### 5.2. Validating Every Name Segment

Demo policy:

- Reject empty names or names exceeding `maxName` characters.
- Reject names starting with `/`.
- Reject `\` (avoids Windows traversal/UNC paths and separator ambiguity).
- Reject NUL characters.
- Strip a trailing `/` **only when checking a directory entry**.
- Split on `/` and reject empty segments, `.`, `..`, or segments containing `:`.
- Cap segment count with `maxDepth`.
- Only then call `root.resolve(name).normalize()` and assert `target.startsWith(root)` by **Path components**.

~~~java
static Path targetFor(Path root, String name, Limits limits)
        throws IOException {
    validateName(name, limits);
    Path target = root.resolve(name).normalize();
    if (target.equals(root) || !target.startsWith(root)) {
        throw new IOException("Unsafe entry name");
    }
    return target;
}
~~~

`validateName` and `Limits` are implemented in the full listing below. **Never use `target.toString().startsWith(root.toString())`** because the string `/safe/output-other` looks like a prefix match for `/safe/output` even though `Path` treats them as siblings.

### 5.3. Distinguishing `normalize` from Real Paths

- `normalize()` performs **path syntax** cleanup, eliminating `.`/`..` segments; it does not inspect actual symbolic links on disk.
- `toRealPath()` determines the actual path and requires the target to exist; it can resolve symlinks per requested behavior.
- `Path.startsWith(Path)` compares path components on the underlying provider, not mere string prefixes.
- `Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS)` rejects a symlink when checking whether a component is a true directory.

A symlink in a parent directory can still redirect I/O outside the root if you rely only on `normalize()+startsWith`. The demo creates a **brand-new output directory** under an application-controlled parent and checks components as directories are created. Still, if an attacker can modify parents/subdirectories concurrently, **TOCTOU** risk remains, as explained in section 10.

## 6. Complete Java 17+ Program: Pack, Unpack, and Two Blocked Cases

**Filename: `ArchivePracticeDemo.java`**

The program below creates its own temporary directory and test fixtures, so you do not need external files. The code uses the **Java 17 standard library**; no Maven, Gradle, or JUnit is needed to run this lab.

~~~java
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.*;
import java.util.zip.*;

public class ArchivePracticeDemo {
    record Limits(int maxEntries, int maxDepth, int maxName,
                  long maxFileBytes, long maxTotalBytes) {
    }

    static final Limits NORMAL = new Limits(20, 8, 100, 128, 256);

    // Forbid dangerous relative paths and non-portable path syntax.
    static void validateName(String name, Limits limits)
            throws IOException {
        if (name.isEmpty() || name.length() > limits.maxName()
                || name.charAt(0) == '/' || name.indexOf('\\') >= 0
                || name.indexOf('\0') >= 0) {
            throw new IOException("Unsafe entry name");
        }

        String value = name.endsWith("/")
                ? name.substring(0, name.length() - 1)
                : name;

        String[] pieces = value.split("/", -1);
        if (pieces.length > limits.maxDepth()) {
            throw new IOException("Unsafe entry name");
        }

        for (String part : pieces) {
            if (part.isEmpty() || part.equals(".")
                    || part.equals("..") || part.indexOf(':') >= 0) {
                throw new IOException("Unsafe entry name");
            }
        }
    }

    static String relativeName(Path root, Path path) {
        return root.relativize(path).toString().replace('\\', '/');
    }

    // Walk source files, write ZIP entries, and enforce byte read limits.
    static long pack(Path sourceDir, Path archive, Limits limits)
            throws IOException {
        if (Files.isSymbolicLink(sourceDir)) {
            throw new IOException("Symlink source");
        }

        Path root = sourceDir.toRealPath();
        if (!Files.isDirectory(root, LinkOption.NOFOLLOW_LINKS)
                || archive.toAbsolutePath().normalize().startsWith(root)) {
            throw new IOException("Archive path invalid");
        }

        final long[] total = {0};
        final int[] entries = {0};

        try (ZipOutputStream out = new ZipOutputStream(
                Files.newOutputStream(
                        archive,
                        StandardOpenOption.CREATE_NEW,
                        StandardOpenOption.WRITE),
                StandardCharsets.UTF_8)) {

            Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
                void begin(String name) throws IOException {
                    validateName(name, limits);
                    if (++entries[0] > limits.maxEntries()) {
                        throw new IOException("Entry limit");
                    }
                    out.putNextEntry(new ZipEntry(name));
                }

                @Override
                public FileVisitResult preVisitDirectory(
                        Path dir, BasicFileAttributes attrs)
                        throws IOException {

                    if (!dir.equals(root)) {
                        begin(relativeName(root, dir) + "/");
                        out.closeEntry();
                    }
                    return FileVisitResult.CONTINUE;
                }

                @Override
                public FileVisitResult visitFile(
                        Path file, BasicFileAttributes attrs)
                        throws IOException {

                    if (!attrs.isRegularFile()) {
                        throw new IOException(
                                "Unsupported source type");
                    }

                    begin(relativeName(root, file));
                    long size = 0;

                    try (InputStream in = Files.newInputStream(
                            file, LinkOption.NOFOLLOW_LINKS)) {
                        byte[] buffer = new byte[8192];

                        for (int n; (n = in.read(buffer)) != -1; ) {
                            if (n == 0) {
                                throw new IOException(
                                        "No input progress");
                            }

                            if (n > limits.maxFileBytes() - size
                                    || n > limits.maxTotalBytes()
                                           - total[0]) {
                                throw new IOException(
                                        "Uncompressed byte limit");
                            }

                            out.write(buffer, 0, n);
                            size += n;
                            total[0] += n;
                        }
                    }

                    out.closeEntry();
                    return FileVisitResult.CONTINUE;
                }
            });

        } catch (IOException | RuntimeException ex) {
            // Do not leave behind a partially packed ZIP.
            try {
                Files.deleteIfExists(archive);
            } catch (IOException cleanup) {
                ex.addSuppressed(cleanup);
            }
            throw ex;
        }

        return total[0];
    }

    static Path targetFor(Path root, String name, Limits limits)
            throws IOException {
        validateName(name, limits);

        Path target = root.resolve(name).normalize();
        if (target.equals(root) || !target.startsWith(root)) {
            throw new IOException("Unsafe entry name");
        }
        return target;
    }

    // Create each parent directory, rejecting symbolic links as directories.
    static void directories(Path root, Path destDir) throws IOException {
        Path at = root;

        for (Path part : root.relativize(destDir)) {
            at = at.resolve(part);

            if (Files.exists(at, LinkOption.NOFOLLOW_LINKS)) {
                if (!Files.isDirectory(
                        at, LinkOption.NOFOLLOW_LINKS)) {
                    throw new IOException(
                            "Non-directory or symlink parent");
                }
            } else {
                Files.createDirectory(at);
            }
        }
    }

    // Unpack ZIP into a NEW directory, blocking path traversal and byte bombs.
    static long unpack(Path archive, Path newOutput, Limits limits)
            throws IOException {
        Path root = Files.createDirectory(newOutput).toRealPath();
        Set<Path> names = new HashSet<>();
        int entries = 0;
        long total = 0;

        try (ZipInputStream in = new ZipInputStream(
                Files.newInputStream(archive),
                StandardCharsets.UTF_8)) {

            ZipEntry entry;
            while ((entry = in.getNextEntry()) != null) {
                if (++entries > limits.maxEntries()) {
                    throw new IOException("Entry limit");
                }

                Path target = targetFor(
                        root, entry.getName(), limits);

                if (!names.add(target)) {
                    throw new IOException("Duplicate entry");
                }

                if (entry.isDirectory()) {
                    directories(root, target);
                    in.closeEntry();
                    continue;
                }

                directories(root, target.getParent());
                boolean created = false;

                try {
                    long size = 0;

                    try (OutputStream out = Files.newOutputStream(
                            target,
                            StandardOpenOption.CREATE_NEW,
                            StandardOpenOption.WRITE)) {
                        created = true;
                        byte[] buffer = new byte[8192];

                        for (int n; (n = in.read(buffer)) != -1; ) {
                            if (n == 0) {
                                throw new IOException(
                                        "No output progress");
                            }

                            if (n > limits.maxFileBytes() - size
                                    || n > limits.maxTotalBytes()
                                           - total) {
                                throw new IOException(
                                        "Uncompressed byte limit");
                            }

                            out.write(buffer, 0, n);
                            size += n;
                            total += n;
                        }
                    }

                    in.closeEntry();

                } catch (IOException | RuntimeException ex) {
                    // If the current file was partially unpacked, delete it.
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

        // Earlier entries remain if unpacking fails on a later entry.
        return total;
    }

    // Test-only helper: build a ZIP containing a single arbitrary entry.
    static void makeSingleZip(
            Path archive, String name, byte[] content)
            throws IOException {
        try (ZipOutputStream out = new ZipOutputStream(
                Files.newOutputStream(
                        archive,
                        StandardOpenOption.CREATE_NEW,
                        StandardOpenOption.WRITE),
                StandardCharsets.UTF_8)) {

            out.putNextEntry(new ZipEntry(name));
            out.write(content);
            out.closeEntry();
        }
    }

    // Delete only the temporary directory created and owned by the demo.
    static void clean(Path work) throws IOException {
        if (!Files.exists(work)) {
            return;
        }

        try (var paths = Files.walk(work)) {
            for (Path p : paths
                    .sorted(Comparator.reverseOrder())
                    .toList()) {
                Files.deleteIfExists(p);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Path work = Files.createTempDirectory(
                "archive-practice-");

        try {
            Path source = Files.createDirectory(
                    work.resolve("source"));
            Path docs = Files.createDirectory(
                    source.resolve("docs"));

            Files.writeString(
                    docs.resolve("a.txt"), "Alpha",
                    StandardCharsets.UTF_8);
            Files.writeString(
                    docs.resolve("b.txt"), "Beta",
                    StandardCharsets.UTF_8);
            Files.createDirectory(source.resolve("empty"));

            // Happy path: source -> ZIP -> fresh output.
            Path zip = work.resolve("bundle.zip");
            System.out.println(
                    "packedBytes=" + pack(source, zip, NORMAL));

            Path output = work.resolve("output");
            System.out.println(
                    "unpackedBytes=" + unpack(zip, output, NORMAL));

            System.out.println("sameA=" + Arrays.equals(
                    Files.readAllBytes(docs.resolve("a.txt")),
                    Files.readAllBytes(
                            output.resolve("docs/a.txt"))));
            System.out.println("emptyDirectory=" +
                    Files.isDirectory(
                            output.resolve("empty")));

            // Negative test 1: ZIP with an entry escaping outside root.
            Path escape = work.resolve("escape.zip");
            makeSingleZip(
                    escape, "../escape.txt", new byte[]{1});

            try {
                unpack(escape, work.resolve("reject-escape"), NORMAL);
            } catch (IOException ex) {
                System.out.println(
                        "zipSlip=" + ex.getMessage());
            }

            // Negative test 2: small compressed entry expanding past limit.
            Path huge = work.resolve("huge.zip");
            makeSingleZip(
                    huge, "large.txt", new byte[200]);

            try {
                unpack(
                        huge,
                        work.resolve("reject-large"),
                        new Limits(20, 8, 100, 32, 64));
            } catch (IOException ex) {
                System.out.println(
                        "limit=" + ex.getMessage());
            }

            System.out.println("outsideCreated=" +
                    Files.exists(
                            work.resolve("escape.txt")));

        } finally {
            clean(work);
        }
    }
}
~~~

Run in the directory containing `ArchivePracticeDemo.java`:

~~~bash
javac ArchivePracticeDemo.java
java ArchivePracticeDemo
~~~

**Stdout verified with Java:**

~~~text
packedBytes=9
unpackedBytes=9
sameA=true
emptyDirectory=true
zipSlip=Unsafe entry name
limit=Uncompressed byte limit
outsideCreated=false
~~~

### Explaining the Results

- `packedBytes=9`: the two files contain `Alpha` (5 UTF-8 bytes) and `Beta` (4 UTF-8 bytes). That is the **raw payload byte count placed into the ZIP**, not `Files.size(bundle.zip)`. A ZIP has headers and a central directory, so archive size differs.
- `unpackedBytes=9`: total bytes actually extracted to files, independent of potentially untrustworthy metadata sizes.
- `sameA=true`: comparing with `Arrays.equals(byte[], byte[])` confirms source and restored files have identical bytes.
- `emptyDirectory=true`: directory entry `empty/` was packed and recreated with its exact name.
- `zipSlip=Unsafe entry name`: `../escape.txt` was rejected before being used as a write path.
- `limit=Uncompressed byte limit`: the entry containing 200 `0` bytes was rejected when per-file cap was 32 bytes and total cap was 64 bytes.
- `outsideCreated=false`: no `escape.txt` file was created in the parent of the target directory.

The program uses `Files.createTempDirectory` and deletes only **the temporary tree it created**, even when tests throw. In an environment disallowing file creation or lacking filesystem permissions, operations may throw `IOException`; that is an environment constraint rather than the happy-path output.

## 7. Step 3 — Inspecting What Is Actually Inside a ZIP

When packing, `ZipOutputStream.putNextEntry` writes the entry name and starts the entry's data stream. `closeEntry` finishes the current entry, while `ZipOutputStream.close` finalizes the entire ZIP archive and closes the output stream. **Never open the output ZIP to read before the stream is closed/finished**: the central directory may not have been written yet.

Two ways of reading ZIPs serve different purposes:

| API | When to Use? |
|---|---|
| `ZipInputStream` | Streaming entries sequentially when input arrives as a stream (e.g., upload) and checking names **right before writing** |
| `ZipFile` | Opening a ZIP file on disk, listing/looking up entries by name, and opening entry input streams |
| `ZipOutputStream` | Building an archive by appending multiple `ZipEntry` items |
| `ZipEntry` | Metadata/name of each archive item |

Note that `ZipInputStream` reads primarily from **local entry records**, whereas `ZipFile` uses the **central directory**. A malformed archive with mismatched local headers and central directory can behave differently across parsers. For untrusted inputs, **validate the exact entry the extractor is about to write**, rather than scanning a name list with one parser and blindly trusting another parser to extract identically.

### Why Read Data in Chunks?

Code:

~~~java
byte[] buffer = new byte[8192];
for (int n; (n = zip.read(buffer)) != -1; ) {
    // Check quota using n, then write n bytes.
}
~~~

This snippet illustrates structure, not a standalone loop. `ZipInputStream.read` returns **decompressed data of the current entry**. Here `-1` means end of the current entry, not end of the archive. After finishing, call `closeEntry()` and then `getNextEntry()` for the next entry.

**Never call `zip.readAllBytes()` on untrusted archives**, because a tiny compressed entry on disk can inflate into huge data and exhaust heap memory.

## 8. Step 4 — Preventing Zip Slip: Validating Names Before Creating Files

Inside `unpack`, every entry goes through:

~~~text
getNextEntry()
     |
     v
++entryCount, check maxEntries
     |
     v
validateName: length / absolute / slash / backslash / . / .. / colon
     |
     v
root.resolve(name).normalize()
     |
     v
target.startsWith(root) and target != root
     |
     v
Set<Path>.add(target): reject duplicates
     |
     v
safely create parent directories
     |
     +-- directory entry --> create directory, closeEntry
     |
     +-- file entry -------> CREATE_NEW, copy with byte quota, closeEntry
~~~

### Why Isn't `Path.isAbsolute` Enough?

On Linux, `C:\Windows\file.txt` can be parsed as a relative filename containing backslashes, whereas on Windows it carries a different path meaning. This exercise enforces a **portable name policy**: forbidding backslashes and colons before resolving, instead of relying purely on the host OS's path parser.

Likewise, `\\server\share\...` can be a UNC path on Windows. Blocking backslashes removes an entire class of ambiguity.

### Why Forbid `..` Even When `normalize` Stays Inside Root?

For instance, `docs/../a.txt` normalizes to `a.txt`, staying inside root. Still, allowing traversal segments makes policies harder to audit, especially alongside symlinks or alternative extraction logic. This exercise **rejects all `..` and `.` segments** for a clean, consistent rule.

### Why Compare `Path` Instead of Strings?

If root is `/var/data/out`, the path `/var/data/outside.txt` also begins with the string `"/var/data/out"`. Yet `Path.startsWith(root)` inspects path components and does not treat `outside.txt` as a child of `out`. Even so, `Path` comparison is a **syntactic validation layer**, not a complete defense against symlinks on its own.

## 9. Step 5 — Enforcing Limits on Uncompressed Bytes, Not Just Metadata

### Never Trust `ZipEntry.getSize()`

Some entries have unknown size or untrustworthy metadata, so `ZipEntry.getSize()` can be `-1` or misstate the actual decompressed byte count. Using this metadata to allocate an array and read at once leaves the program vulnerable to **zip bombs**.

Example check inside the loop:

~~~java
if (n > limits.maxFileBytes() - size
        || n > limits.maxTotalBytes() - total) {
    throw new IOException("Uncompressed byte limit");
}

out.write(buffer, 0, n);
size += n;
total += n;
~~~

This excerpt comes from the full program. `size` and `total` increment only after checking and writing the chunk. Comparing `n > limit - used` avoids integer overflow from adding large values before checking, assuming positive limits and `used` not already exceeding the limit.

**Quotas are not just byte counts:**

- `maxEntries` stops archives containing millions of empty directory/file entries.
- `maxName` curbs excessively long filenames.
- `maxDepth` caps directory nesting depth.
- `maxFileBytes` stops a single entry from inflating too large.
- `maxTotalBytes` stops many small entries from summing to huge totals.
- Production also requires **deadlines, CPU quotas, inode/file count caps, disk quotas, directory counts, and total compressed input byte caps**.

Never rely on compression ratio (uncompressed/compressed) as your sole barrier: compressed-size metadata can be forged or awkward to track while streaming. Always count actual decompressed bytes.

### What If Quota Exceeds After a File Was Already Created?

In the demo, a file created via `Files.newOutputStream(..., CREATE_NEW, WRITE)` may have received partial writes before a chunk breaches quota. The `catch` block attempts to **delete the current file**.

However, if earlier entries already unpacked cleanly, they **may remain in the output directory**. `unpack` as a whole **is not an atomic transaction**. In production, use an application-owned staging directory and publish only once every entry has been processed and validated.

## 10. Target Directory and Symbolic Links: Practical Safety Scope

### 10.1. Why Require Creating a Brand-New Target Directory?

`Files.createDirectory(newOutput)` requires the path not to exist yet, unlike `Files.createDirectories` which accepts an existing tree.

In the exercise:

~~~java
Path root = Files.createDirectory(newOutput).toRealPath();
~~~

Benefits:

- Never accidentally mixes archive files into old data.
- Never overwrites existing filenames.
- No pre-planted subdirectories or symlinks inside the **new output**, assuming the parent is trusted and nobody else writes into the output tree.
- Clear ownership and cleanup if extraction fails.

Prerequisite: **the parent of `newOutput` must be trusted**, and untrusted actors must lack write access to the output tree during extraction. The demo creates its parent with `Files.createTempDirectory` for a safe practice environment.

### 10.2. Checking Symlinks Along Parent Components

When building `root/docs/a.txt`, `directories` checks each component:

~~~java
if (Files.exists(at, LinkOption.NOFOLLOW_LINKS)) {
    if (!Files.isDirectory(at, LinkOption.NOFOLLOW_LINKS)) {
        throw new IOException("Non-directory or symlink parent");
    }
} else {
    Files.createDirectory(at);
}
~~~

An existing symlink normally fails `isDirectory(..., NOFOLLOW_LINKS)`, so it is rejected rather than silently followed to write outside root. `CREATE_NEW` on the final file prevents overwriting an existing file or symlink.

### 10.3. TOCTOU Is Not Completely Eliminated

**TOCTOU (Time Of Check To Time Of Use)** is the window between checking a path and opening/creating the file. If an attacker has permission to swap a directory for a symlink in that window, earlier Java checks may no longer hold.

Therefore **`normalize()`, `NOFOLLOW_LINKS`, and `CREATE_NEW` do not by themselves form an atomic filesystem sandbox**.

When the threat model allows other processes to mutate the output tree, you may need:

- Creating/staging under a private parent with restricted OS permissions/ACLs.
- Descriptor-relative operations such as `SecureDirectoryStream` when supported by the filesystem provider to mitigate specific races.
- OS-level isolation/sandboxes, containers, and least-privilege process accounts.
- Care with Windows junctions/reparse points and provider-specific path structures.
- Never restoring symlinks/hardlinks from archive metadata without validating targets under a strict policy.

**Do not describe this demo as an absolute defense against all Zip Slip/TOCTOU attacks.** It is a foundation for name/path validation and write controls in a trusted fresh destination environment.

## 11. Portability: Windows, Unicode, and Colliding Names

`validateName` intentionally enforces a **basic** portable policy, yet does not handle every special filesystem filename.

Cases to address when hardening:

1. **Case-insensitive collisions:** `docs/A.txt` and `docs/a.txt` may map to the same file on some filesystems.
2. **Unicode normalization:** two visually identical names may normalize to the same path.
3. **Windows reserved names:** `CON`, `PRN`, `AUX`, `NUL`, `COM1`... have special rules, even with extensions.
4. **Trailing dots/spaces:** names like `a.txt.` or `a.txt ` may be normalized/collide on certain OSes.
5. **Colons / NTFS ADS:** `a.txt:stream` is rejected by the example's `:` ban.
6. **Slashes/backslashes:** ZIP names normally use `/`; the policy forbids `\` to prevent cross-OS divergence.
7. **Symlinks/junctions:** must be caught even when names are syntactically valid.
8. **Byte-length limits:** `String.length()` in the demo counts UTF-16 code units; OSes can also cap filename/path lengths by **bytes** or native representations.

`CREATE_NEW` provides a practical defense against final-path collisions, though systems with strict cross-platform requirements should add a **dedicated filesystem name validator** tested on target OSes.

## 12. Extension Practice: Adding Negative Tests

The lab already includes two negative tests: traversal and byte bomb. For thorough practice, extend `makeSingleZip` or build a multi-entry ZIP helper and test these cases:

| Test Case | Expected Result |
|---|---|
| `/tmp/outside.txt` | Rejects absolute entry |
| `C:/temp/out.txt` | Rejects colon/drive prefix |
| `docs\..\outside.txt` | Rejects backslash |
| `docs/../outside.txt` | Rejects `..` |
| `docs//a.txt` | Rejects empty segment |
| Two `same.txt` entries | Rejects duplicate |
| `docs/a.txt` then `docs/a.txt/b.txt` | Rejects because parent is a file, not a directory |
| Hundreds of empty entries | Blocked by `maxEntries` |
| Deeply nested entry | Blocked by `maxDepth` |
| Single entry inflating huge | Blocked by `maxFileBytes` |
| Many entries summing huge | Blocked by `maxTotalBytes` |
| Names differing only by case | Filesystem-dependent; must never overwrite |
| Symlink inside source tree | Packer rejects unsupported source type |
| Insufficient permissions on ZIP/target | Throws `IOException`; closes streams and cleans up properly |
| Truncated archive / bad CRC | Must fail and not publish partial output |

Important assertions go beyond "throws an exception":

- **Zero files created outside root**.
- Existing files are never overwritten.
- A partially written file from the failing entry is deleted.
- Earlier entries may still remain: tests must **explicitly reflect rollback boundaries**.
- After an error, streams opened via try-with-resources are still closed.
- Quotas count **decompressed** bytes.
- When packing is interrupted mid-way, the newly created ZIP file must be cleaned up.

### Using Unit Test Assertions Instead of Relying on Logs

A JUnit 5 test might follow this pattern:

~~~java
@Test
void rejectsZipSlip() throws Exception {
    Path archive = createArchiveWithEntry(
            "../escape.txt", new byte[]{1});
    Path root = newTemporaryDestination();

    assertThrows(
            IOException.class,
            () -> ArchivePracticeDemo.unpack(
                    archive, root, TEST_LIMITS));

    assertFalse(Files.exists(
            root.getParent().resolve("escape.txt")));
}
~~~

This is **JUnit 5 pseudocode**, not standalone compilable code: `createArchiveWithEntry`, `newTemporaryDestination`, and `TEST_LIMITS` are project-defined fixtures. `root` must **not exist yet** when passed to `unpack`. The full program in section 6 requires no JUnit and already runs the equivalent test case.

## 13. When to Use `ZipFile` Instead of `ZipInputStream`?

For a ZIP file already on disk, `ZipFile` can look up entries by name:

~~~java
try (ZipFile zip = new ZipFile(
        archivePath.toFile(), StandardCharsets.UTF_8)) {

    ZipEntry entry = zip.getEntry("docs/a.txt");
    if (entry != null) {
        try (InputStream in = zip.getInputStream(entry)) {
            // Read this entry's content and enforce byte limits as in unpack.
        }
    }
}
~~~

This is illustrative code requiring `archivePath` and imports. `ZipFile` can leverage the central directory, whereas `ZipInputStream` fits streaming uploads. **Never switch to `ZipFile` and drop path, quota, and ownership checks.**

If an archive uses **ZIP encryption/passwords**, Java's `java.util.zip` offers no general API to decrypt all password-protected ZIP variants. For ZIP features outside JDK scope, use a vetted library. Never treat an "unsupported method" exception as a reason to disable path validation.

## 14. Production Architecture: Stage First, Then Publish

Use a two-stage flow:

~~~text
archive.zip
    |
    v
Private staging directory (new)
    |
    +-- per entry: validate path, quota, no-follow, CREATE_NEW
    |
    +-- inspect whole archive / format / checksum / malware policy if needed
    |
    v
Publish to final destination per policy
    |
    v
Clean up staging on failure
~~~

In production, ideally ensure:

1. Place staging on the same filesystem as destination if atomic rename is desired where supported.
2. Deny other users write access to staging or ability to swap directories/symlinks.
3. Cap compressed input bytes, uncompressed bytes, entry count, depth, CPU time, and inode count.
4. Refuse or isolate sensitive executable/script entries unless the product requires them.
5. Check reserved/colliding filesystem names on actual target OSes.
6. Clarify merge/overwrite policies; the demo supports **new destinations only**.
7. On publish, check support for `StandardCopyOption.ATOMIC_MOVE` if atomic move is wanted; handle `AtomicMoveNotSupportedException` and remember rename is not a cross-filesystem transaction.
8. Clean up staging on mid-run failure and sweep orphan staging directories after crashes.
9. For sensitive content, ZIP CRC32 detects accidental corruption only—**not forged tampering**.
10. Log clear categories ("invalid path", "quota exceeded", "archive corrupted", "permission denied", "I/O interrupted") without leaking unintended system paths.

**Never return success just because `unpack` created a few files.** Success must mean every entry was read, validated, extracted, streams closed cleanly, and output published per contract.

## 15. Common Pitfalls

1. **Writing `entry.getName()` directly into output without checks.** Leads to Zip Slip.
2. **Using `String.startsWith` alone for containment checks.** Can confuse sibling paths sharing a string prefix.
3. **Believing `Path.normalize()` resolves symlinks.** Wrong: `normalize` only cleans syntax.
4. **Believing `NOFOLLOW_LINKS` eliminates all races.** Wrong if an attacker can mutate the tree concurrently.
5. **Using `CREATE`/`TRUNCATE_EXISTING` on untrusted entries.** Can overwrite old files; use `CREATE_NEW` when overwrites are forbidden.
6. **Extracting into a non-empty directory without a merge policy.** Causes collisions and silent overwrites.
7. **Ignoring directory entries.** Loses empty directories.
8. **Assuming every ZIP contains a `docs/` directory entry before `docs/a.txt`.** Not guaranteed; create parents safely after validation.
9. **Not capping entry count.** An archive with millions of empty files still breaks systems even with tiny total bytes.
10. **Trusting `entry.getSize()` to allocate arrays.** Can be `-1` or forged.
11. **Calling `zip.readAllBytes()` on untrusted uploads.** Easily exhausts heap via zip bombs.
12. **Capping only compressed ZIP size.** A few KiB compressed can expand massively.
13. **Forgetting `ZipOutputStream.close()`.** Central directory may be incomplete.
14. **Treating `ZipInputStream.read() == -1` as end of archive.** It only marks end of the current entry.
15. **Placing the output ZIP inside the source tree being walked.** Causes unstable/self-including ZIP input.
16. **Uncontrolled following of source symlinks.** Can pack sensitive files outside the target directory.
17. **Allowing arbitrary backslashes in entry names.** Behavior diverges across OSes.
18. **Skipping duplicate and case-collision checks.** Can silently lose or overwrite files.
19. **Assuming `IOException` automatically rolls back earlier extracted files.** Wrong: staging and cleanup are required.
20. **Assuming CRC32 proves archive authenticity.** Wrong: checksums provide no cryptographic authentication.

## 16. Self-Check Questions

**Question 1.** Why must the packer write directory entries such as `empty/`?

**Answer:** To preserve empty directories. If a ZIP contains only file entries, directories with no child files vanish upon extraction.

**Question 2.** Why is checking `zipEntry.getSize() <= maxBytes` alone insufficient against zip bombs?

**Answer:** Metadata can be missing or forged, and many entries together can still sum huge. You must count actual decompressed bytes in every `read` iteration before writing.

**Question 3.** If a ZIP contains `docs/a.txt` with no `docs/` entry, can the extractor still create it?

**Answer:** Yes. Once the name is validated and verified inside root, safely create parent directories and then create the new file.

**Question 4.** Why is `Path.startsWith(root)` better than `String.startsWith(root.toString())`?

**Answer:** It compares Path components, preventing `/safe/output2` from matching `/safe/output`.

**Question 5.** What problem does `Files.newOutputStream(..., CREATE_NEW)` solve?

**Answer:** Prevents overwriting/truncating an existing file or symlink at the final path; it does not by itself stop an attacker from swapping parent directories in a race.

**Question 6.** Why must testing `../escape.txt` assert both the exception and the filesystem?

**Answer:** Catching an exception does not prove no file escaped root beforehand. Assertions must verify no offending file exists after failure.

**Question 7.** If the tenth entry exceeds quota after nine valid entries already extracted, do the earlier files vanish automatically?

**Answer:** No. The demo cleans up only the current failing entry's file; separate staging + cleanup/publish are needed for all-or-nothing workflows.

**Question 8.** Why shouldn't Java's `ZipInputStream` be used on a plain `.gz` GZIP stream?

**Answer:** ZIP archives have `ZipEntry` records and ZIP container structure, whereas GZIP is a different stream compression format; even though both can use DEFLATE, headers and containers differ.

**Question 9.** The program runs on Linux, yet an archive contains `C:/tmp/a.txt`. Why does this lesson's policy still reject it?

**Answer:** To maintain portability and prevent names from being interpreted as drive paths if extracted on Windows or by other tools.

### Official Java 17 Documentation

- [ZipOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipOutputStream.html)
- [ZipInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipInputStream.html)
- [ZipEntry](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipEntry.html)
- [ZipFile](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipFile.html)
- [Files.walkFileTree and Files.newOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [Path.resolve, normalize, startsWith](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html)
- [LinkOption.NOFOLLOW_LINKS](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/LinkOption.html)
- [StandardOpenOption.CREATE_NEW](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardOpenOption.html)
- [SecureDirectoryStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/SecureDirectoryStream.html)
