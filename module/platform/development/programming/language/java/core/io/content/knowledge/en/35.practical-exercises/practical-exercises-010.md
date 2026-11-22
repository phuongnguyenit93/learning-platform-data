# Java 17 Practical Exercise: Compressing, Extracting ZIPs with Limits, and Entry Path Validation

## 1. Objectives and Practical Outcomes

This exercise builds a **ZIP packer/extractor** using Java Core I/O with no external libraries. The program compresses a directory tree into a `.zip`, extracts it to a new destination directory, and proactively rejects inputs that violate policy.

Once completed, you will be able to:

1. Use `Files.walkFileTree` to traverse a file tree **without following symbolic links** by default.
2. Use `ZipOutputStream` to create an archive containing both files and **empty directories**.
3. Use `ZipInputStream` to process one `ZipEntry` at a time without loading every file into RAM.
4. Enforce limits on **entry count, depth, name length, per-file bytes, and total uncompressed bytes**.
5. Detect **Zip Slip** via entries like `../escape.txt`, absolute names, or unsafe separators.
6. Use `Path.resolve`, `normalize`, `Path.startsWith(Path)`, `NOFOLLOW_LINKS`, and `CREATE_NEW` within their proper scope.
7. Create parent directories for nested files even when the ZIP lacks explicit directory entries.
8. Distinguish write success, path validation, **archive integrity**, and resistance against filesystem race conditions.
9. Run a **round-trip** test and then test two problematic archives: traversal and decompression limit overflow.

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

**Note:** This is a foundational design and defense-in-depth exercise. It **does not claim to be a complete sandbox against an adversary with permission to modify the filesystem concurrently**. The final sections explain how to upgrade it to a production solution with staging, permission controls, and TOCTOU mitigation.

## 2. Concrete Problem

Suppose the input is:

~~~text
source/
  docs/
    a.txt       (Alpha)
    b.txt       (Beta)
  empty/
~~~

The program creates:

~~~text
bundle.zip
  docs/
  docs/a.txt
  docs/b.txt
  empty/
~~~

Then extracting into a **new output directory**, we expect:

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
C:/Windows/Temp/a.txt      -> Windows drive-style ':' in name
docs\..\escape.txt         -> backslash traversal
docs/./a.txt               -> non-canonical name per policy
docs/../a.txt              -> '..' component
docs/a.txt (duplicate)     -> duplicate/overwrite
large.txt (past quota)     -> zip bomb / disk exhaustion
~~~

A ZIP is a **multi-entry named archive**, not a single GZIP-compressed byte stream. `ZipOutputStream` and `ZipInputStream` operate entry by entry via `ZipEntry`. The ZIP format can store each entry as `DEFLATED` or `STORED`; ZIP **does not mean every entry is compressed**.

## 3. Designing Policy Before Writing Code

Do not write `extract(zip, target)` first and try to patch dangerous names afterward. Define the policy clearly upfront:

| Constraint | Value in Example | Meaning |
|---|---:|---|
| `maxEntries` | 20 | Maximum total file and directory entries |
| `maxDepth` | 8 | Maximum number of entry name segments |
| `maxName` | 100 | Maximum entry name string length |
| `maxFileBytes` | 128 | Maximum **uncompressed** bytes per file |
| `maxTotalBytes` | 256 | Maximum total **uncompressed** bytes |
| Output dir | Must not exist | Never merge/overwrite existing data |
| Input symlink | Reject | Do not pack contents outside the allowed tree |
| Output symlink | Do not follow on parents | Reduce risk of writing off-target |
| Duplicate file path | Reject | Prevent replacing existing data |
| Abnormal entry name | Reject | Prevent traversal/platform-specific paths |
| Read/write memory | 8192-byte buffer | Never call `readAllBytes()` on untrusted files |

The `128`/`256`-byte thresholds are tiny to make the **practice exercise** easy to test; they **are not production quota recommendations**. In real systems, choose quotas based on business needs, memory/disk budgets, concurrent users, timeouts, and system limits.

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

This is an **excerpt from the main class in section 6**, not a standalone runnable file. In production code, validate that all values received by the record are positive/valid in a constructor or factory; this example initializes with controlled constants.

## 4. Step 1 — Traversing the Source to Pack Without Escaping the Tree

`Files.walkFileTree(root, visitor)` by default **does not follow symbolic links** when `FOLLOW_LINKS` is not passed. With `SimpleFileVisitor`:

- `preVisitDirectory`: upon entering a directory, can emit a directory entry ending with `/`.
- `visitFile`: upon visiting a regular file, writes a file entry and streams chunk by chunk.
- If a symlink or unsupported file type is encountered, the example **rejects** it instead of silently following/copying.
- If source files change during packing, handle that via your testing/threat model; `walkFileTree` does not create an immutable snapshot of the whole tree.

### Producing Machine-Independent Entry Names

`Path` on Windows can represent separators differently from Linux. Names inside a ZIP should be normalized to **relative names using `/`**:

~~~java
static String relativeName(Path root, Path path) {
    return root.relativize(path).toString().replace('\\', '/');
}
~~~

This is an illustrative method. Never store absolute source paths inside a ZIP: extractors only want relative names beneath a destination directory of their choosing.

**Do not create the ZIP inside the source tree being walked.** If the output archive sits inside the source directory, traversal can visit the growing ZIP file itself and make the input unstable. The example rejects `archivePath.startsWith(sourceRoot)` after canonicalizing root.

### Preserving Empty Directories

If you only emit entries for files, an `empty/` directory with no children can vanish. Therefore for directories (excluding root), emit `ZipEntry("relative/path/")`. Directory entries **carry no regular file content** in the demo.

## 5. Step 2 — Defining Allowed Entry Names and Destination Paths

### 5.1. Why Is `entry.getName()` Untrusted Data?

ZIP entry names are chosen by whoever created the archive. Java's `ZipInputStream.getNextEntry()` returns a `ZipEntry`, yet **does not automatically verify that the filename is safe to write inside an output directory**.

Counter-example:

~~~java
Path target = outputRoot.resolve(entry.getName());
Files.copy(zipInputStream, target); // MUST NOT do this with an unvalidated name.
~~~

This is a **counter-example snippet**, not standalone runnable code. With the name `../escape.txt`, `resolve` can land outside `outputRoot`. That is **Zip Slip / path traversal**.

### 5.2. Validating Each Name Component

Demo policy:

- Reject empty names or names exceeding `maxName` characters.
- Reject names starting with `/`.
- Reject `\` (avoids Windows traversal/UNC paths and separator ambiguity).
- Reject NUL characters.
- Strip a trailing `/` **only when checking a directory entry**.
- Split on `/` and reject empty components, `.`, `..`, or components containing `:`.
- Bound component count by `maxDepth`.
- Only then call `root.resolve(name).normalize()` and verify `target.startsWith(root)` by **Path components**.

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

`validateName` and `Limits` are implemented in the full code below. **Do not use `target.toString().startsWith(root.toString())`** because the string `/safe/output-other` looks like a prefix match for `/safe/output` even though `Path` disagrees.

### 5.3. Distinguishing `normalize` from Real Paths

- `normalize()` performs **path syntax** cleanup, eliminating `.`/`..` components; it does not inspect actual symbolic links on disk.
- `toRealPath()` resolves the physical path and requires the resource to exist; it can resolve symlinks according to requested options.
- `Path.startsWith(Path)` compares path components under the provider, not raw string prefixes.
- `Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS)` helps reject a symlink when checking whether a component is a real directory.

A symlink in a parent directory can still redirect I/O outside root if you only check `normalize()+startsWith`. The demo creates a **new output directory** under an application-controlled parent and checks components while creating directories. However, if an attacker can alter parents or subdirectories concurrently, **TOCTOU** risk remains, as explained in section 10.

## 6. Complete Java 17+ Program: Pack, Unpack, and Two Blocked Cases

**Filename: `ArchivePracticeDemo.java`**

The program below creates its own temporary directory and test data, so you do not need to prepare external files. The code uses the **Java 17 standard library**; no Maven, Gradle, or JUnit is needed to run the lab.

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

    // Forbid dangerous relative paths and non-portable path forms.
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

    // Traverse source files, emit ZIP entries, and bound bytes read.
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
            // Do not leave a partially packed ZIP behind.
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

    // Create parent directories step by step, rejecting symbolic links as directories.
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

    // Extract ZIP into a NEW directory, blocking path traversal and byte bombs.
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
                    // If the current file is partially extracted, delete it.
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

        // Earlier entry files remain if unpack fails on a later entry.
        return total;
    }

    // For testing only: create a ZIP containing one custom entry.
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

            // Happy path: source -> ZIP -> new output.
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

            // Negative test 1: ZIP with entry name escaping root.
            Path escape = work.resolve("escape.zip");
            makeSingleZip(
                    escape, "../escape.txt", new byte[]{1});

            try {
                unpack(escape, work.resolve("reject-escape"), NORMAL);
            } catch (IOException ex) {
                System.out.println(
                        "zipSlip=" + ex.getMessage());
            }

            // Negative test 2: entry small on disk but expands past limit.
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

Run inside the directory containing `ArchivePracticeDemo.java`:

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

### Explaining the Output

- `packedBytes=9`: the two files contain `Alpha` (5 UTF-8 bytes) and `Beta` (4 UTF-8 bytes). This is the **raw data byte count put into the ZIP**, not `Files.size(bundle.zip)`. ZIPs add headers and a central directory so the archive size differs.
- `unpackedBytes=9`: total bytes actually extracted to files, independent of potentially untrusted size metadata.
- `sameA=true`: comparing with `Arrays.equals(byte[], byte[])` confirms source and extracted files have identical bytes.
- `emptyDirectory=true`: directory entry `empty/` was packed and recreated with the exact name.
- `zipSlip=Unsafe entry name`: `../escape.txt` was rejected before being used as a write path.
- `limit=Uncompressed byte limit`: the entry of 200 zero bytes was rejected under limits of 32 bytes per file and 64 bytes total.
- `outsideCreated=false`: no `escape.txt` file was created in the parent of the destination directory.

The program uses `Files.createTempDirectory` and deletes only the **temporary tree it created itself**, even if tests throw. If run in an environment disallowing file creation or lacking filesystem permissions, operations can throw `IOException`; that is an environment restriction rather than the happy-path output.

## 7. Step 3 — Inspecting What Is Actually Inside a ZIP

When packing, `ZipOutputStream.putNextEntry` writes the entry name and starts the entry data stream. `closeEntry` finishes the current entry, while `ZipOutputStream.close` finalizes the ZIP archive and closes output. **Do not open the output ZIP for reading before the stream is closed/finished**: the central directory may not be completely written yet.

Two ways to read ZIPs serve different purposes:

| API | When to Use? |
|---|---|
| `ZipInputStream` | Iterates entries sequentially when input is a stream, such as an upload, validating names **right before writing** |
| `ZipFile` | Opens a ZIP file on disk, lists/looks up entries by name, and opens an entry input stream |
| `ZipOutputStream` | Creates an archive by adding multiple `ZipEntry` records |
| `ZipEntry` | Metadata/name of an individual archive item |

Note that `ZipInputStream` operates primarily on **local entry records**, whereas `ZipFile` can use the **central directory**. An archive crafted inconsistently between local headers and the central directory may parse differently across tools. For untrusted inputs, **validate the actual entries the extractor will write**, rather than scanning a name list with one parser and assuming another parser extracts identically.

### Why Read Data in Chunks?

Code:

~~~java
byte[] buffer = new byte[8192];
for (int n; (n = zip.read(buffer)) != -1; ) {
    // Check quota against n, then write n bytes.
}
~~~

This snippet illustrates the structure, not a standalone loop. `ZipInputStream.read` returns **decompressed data for the current entry**. A `-1` return value means end of the current entry, not end of the archive. After finishing an entry, call `closeEntry()` and then `getNextEntry()` to advance.

**Do not use `zip.readAllBytes()` on untrusted archives**, because a tiny entry on disk can decompress into massive data and exhaust the heap.

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
create parent directories safely
     |
     +-- directory entry --> create directory, closeEntry
     |
     +-- file entry -------> CREATE_NEW, copy with byte quota, closeEntry
~~~

### Why Not Just `Path.isAbsolute`?

On Linux, `C:\Windows\file.txt` can be parsed as a relative filename containing backslashes, whereas on Windows it means a very different path. This exercise enforces a **portable naming policy**: forbidding backslashes and colons before resolving, instead of relying solely on the current OS's path parsing.

Similarly, `\\server\share\...` can represent a Windows UNC path. Blocking backslashes removes an entire class of ambiguity.

### Why Forbid `..` Even When `normalize` Stays Inside Root?

For example, `docs/../a.txt` normalizes to `a.txt`, staying inside root. However, allowing traversal segments makes policies harder to audit, especially alongside symlinks or different extraction logic. This exercise chooses to **reject every `..` and `.`** for a uniform rule.

### Why Compare `Path` Objects Instead of Strings?

If root is `/var/data/out`, the path `/var/data/outside.txt` also begins with the string `"/var/data/out"`. Yet `Path.startsWith(root)` inspects path components and does not treat `outside.txt` as a child of `out`. Even so, path comparison is only a **syntactic check layer**, not a complete anti-symlink solution by itself.

## 9. Step 5 — Bounding by Uncompressed Bytes, Not Metadata Alone

### Do Not Trust `ZipEntry.getSize()`

Some entries have unknown size or untrusted metadata, so `ZipEntry.getSize()` can be `-1` or misrepresent actual decompressed bytes. If you trust metadata to allocate an array and read all at once, the program is vulnerable to a **zip bomb**.

Check inside the loop:

~~~java
if (n > limits.maxFileBytes() - size
        || n > limits.maxTotalBytes() - total) {
    throw new IOException("Uncompressed byte limit");
}

out.write(buffer, 0, n);
size += n;
total += n;
~~~

This snippet is extracted from the full program. `size` and `total` advance only after validating and writing the chunk. Comparing `n > limit - used` avoids integer overflow from adding large numbers first, provided limits are positive and `used` has not exceeded the limit.

**Quotas are not just bytes:**

- `maxEntries` blocks archives with millions of empty file/directory entries.
- `maxName` limits excessively long names.
- `maxDepth` bounds directory nesting depth.
- `maxFileBytes` blocks one entry from expanding too large.
- `maxTotalBytes` blocks many small entries whose combined size is huge.
- Production also needs **deadlines, CPU quotas, inode/file count limits, disk quotas, directory counts, and total compressed input byte limits**.

Do not rely on compression ratio (uncompressed/compressed) as the sole safeguard: compressed-size metadata may be untrusted or awkward to compute while streaming. Always meter actual bytes.

### What If Quota Is Exceeded After a File Was Already Created?

In the demo, a new file opened via `Files.newOutputStream(..., CREATE_NEW, WRITE)` may have already received partial bytes before a chunk exceeds quota. The `catch` block attempts to **delete the current file**.

However, if earlier entries already succeeded, they **may remain inside the output directory**. The whole `unpack` is **not an atomic transaction**. In production, use an application-owned staging directory and publish only after every entry is processed and validated.

## 10. Destination Directories and Symbolic Links: Practical Safety Scope

### 10.1. Why Require Creating a New Destination Directory?

`Files.createDirectory(newOutput)` requires the path not to exist yet, unlike `Files.createDirectories` which accepts an existing tree.

In this exercise:

~~~java
Path root = Files.createDirectory(newOutput).toRealPath();
~~~

Benefits:

- Does not accidentally mix archive files into existing data.
- Does not overwrite existing filenames.
- No pre-planted subdirectories or symlinks exist inside the **new output**, assuming a trusted parent and no concurrent writer modifying the output tree.
- Makes ownership and cleanup straightforward if extraction fails.

Prerequisite: **the parent of `newOutput` must be trusted**, and untrusted actors must lack permission to modify the output tree during extraction. The demo creates its parent with `Files.createTempDirectory` for a controlled practice environment.

### 10.2. Checking Symlinks on Parent Components

When creating `root/docs/a.txt`, `directories` inspects each component:

~~~java
if (Files.exists(at, LinkOption.NOFOLLOW_LINKS)) {
    if (!Files.isDirectory(at, LinkOption.NOFOLLOW_LINKS)) {
        throw new IOException("Non-directory or symlink parent");
    }
} else {
    Files.createDirectory(at);
}
~~~

An existing symlink generally fails `isDirectory(..., NOFOLLOW_LINKS)` and is rejected instead of silently following the link outside root. `CREATE_NEW` on the final file prevents overwriting an existing file or symlink.

### 10.3. TOCTOU Is Not Fully Solved

**TOCTOU (Time Of Check To Time Of Use)** is the window between checking a path and opening/creating the file. If an attacker can swap a directory for a symlink in that window, earlier Java checks may no longer hold.

Therefore **`normalize()`, `NOFOLLOW_LINKS`, and `CREATE_NEW` do not automatically create an atomic filesystem sandbox**.

When the threat model permits other processes to modify the output tree, consider:

- Staging under a private parent with restricted OS permissions/ACLs.
- Using descriptor-relative operations such as `SecureDirectoryStream` where supported by the filesystem provider to mitigate specific races.
- Using OS-level isolation/sandboxes, containers, and least-privilege process accounts.
- Watching out for Windows junctions/reparse points and provider-specific path semantics.
- Never restoring symlinks or hardlinks from archive metadata without strict, explicit target validation.

**Do not describe the demo as immune to every Zip Slip/TOCTOU attack.** It is a foundation for path/name validation and write controls in a trusted new destination environment.

## 11. Portability: Windows, Unicode, and Colliding Names

`validateName` intentionally enforces a **basic** portable policy, yet does not handle every filesystem-specific edge case.

Cases to address when hardening:

1. **Case-insensitive collisions:** `docs/A.txt` and `docs/a.txt` can map to the same destination on some filesystems.
2. **Unicode normalization:** two visually identical names may normalize to the same path.
3. **Windows reserved names:** `CON`, `PRN`, `AUX`, `NUL`, `COM1`, etc., carry special rules, even with extensions.
4. **Trailing dots/spaces:** names like `a.txt.` or `a.txt ` can be normalized or collide on some OSes.
5. **Colons / NTFS ADS:** `a.txt:stream` is rejected by the example's colon check.
6. **Slashes/backslashes:** ZIP names typically use `/`; policy forbids `\` to avoid cross-OS differences.
7. **Symlinks/junctions:** must be checked even when names are syntactically valid.
8. **Overly long names in bytes:** `String.length()` in the demo counts UTF-16 code units; OSes may cap names/paths in **bytes** or native representations.

`CREATE_NEW` offers a practical defense against final-path collisions, yet systems with strict cross-platform requirements should include a **dedicated filesystem name validator** tested across target OSes.

## 12. Extended Practice: Adding Negative Tests

The lab already includes two negative tests: traversal and a byte bomb. For complete practice, extend `makeSingleZip` or build a multi-entry ZIP helper and test these additional cases:

| Test Case | Expected Result |
|---|---|
| `/tmp/outside.txt` | Reject absolute entry |
| `C:/temp/out.txt` | Reject colon/drive prefix |
| `docs\..\outside.txt` | Reject backslash |
| `docs/../outside.txt` | Reject `..` |
| `docs//a.txt` | Reject empty component |
| Two `same.txt` entries | Reject duplicate |
| `docs/a.txt` then `docs/a.txt/b.txt` | Reject because parent is a file, not a directory |
| Hundreds of empty entries | Blocked by `maxEntries` |
| Excessively nested entry | Blocked by `maxDepth` |
| One entry expanding too large | Blocked by `maxFileBytes` |
| Multiple entries expanding too large combined | Blocked by `maxTotalBytes` |
| Names differing only by case | Filesystem-dependent; must never overwrite |
| Symlink in source tree | Packer rejects unsupported source type |
| Missing permissions on ZIP/destination | Throws `IOException`; closes streams and cleans up properly |
| Truncated archive or bad CRC | Must report error, never publish partial output |

Important assertions go beyond "throws an exception":

- **No file is created outside root**.
- No existing file is overwritten.
- A half-written file from the failing entry is deleted.
- Earlier extracted entries may still remain: tests must **understand rollback boundaries**.
- After errors, resources opened via TWR are still closed.
- Quotas are counted from **decompressed** bytes.
- On mid-pack cancellation tests, the newly created ZIP file must be cleaned up.

### Using Unit Test Assertions Instead of Relying on Logs

A JUnit 5 test can be structured as:

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

This is **JUnit 5 pseudocode** and does not compile standalone: `createArchiveWithEntry`, `newTemporaryDestination`, and `TEST_LIMITS` are project-defined test fixtures. `root` must **not exist yet** when passed to `unpack`. The complete program in section 6 needs no JUnit and implements an equivalent test case.

## 13. When Should `ZipFile` Replace `ZipInputStream`?

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

This is illustrative code requiring `Path archivePath` and imports. `ZipFile` uses the central directory, whereas `ZipInputStream` suits uploads/streams. **Never switch to `ZipFile` and drop path, quota, or ownership checks.**

If an archive uses **ZIP encryption/passwords**, Java's `java.util.zip` does not provide a general API to decrypt arbitrary password-protected ZIP variants. For ZIP features beyond JDK scope, use a vetted library. Never treat an "unsupported method" exception as a reason to disable path validation.

## 14. Production Architecture: Stage First, Then Publish

Use two phases:

~~~text
archive.zip
    |
    v
Private staging directory (new)
    |
    +-- per entry: validate path, quota, no-follow, CREATE_NEW
    |
    +-- check whole archive / format / checksum / malware policy if needed
    |
    v
Publish to final destination per policy
    |
    v
Clean up staging on failure
~~~

In production, ideally ensure:

1. Place staging on the same filesystem as destination if atomic rename is desired where supported.
2. Prevent other users from writing into staging or swapping directories/symlinks.
3. Bound compressed input bytes, uncompressed bytes, entry count, depth, CPU time, and inode count.
4. Reject sensitive executable/script entries if the product does not need them.
5. Check OS-specific reserved names and case collisions.
6. Clarify merge/overwrite policies; the demo supports **new destinations only**.
7. When publishing, verify support for `StandardCopyOption.ATOMIC_MOVE` if desired; `AtomicMoveNotSupportedException` can occur and renames are not cross-filesystem transactions.
8. Clean up staging on mid-way failure and clean up orphan staging directories after crashes.
9. For sensitive data, ZIP CRC32 detects accidental corruption only and **is not a tamper-proof digital signature**.
10. Log errors clearly distinguishing "invalid path", "quota exceeded", "archive corrupted", "permission denied", and "I/O interrupted" without leaking unintended host paths.

**Do not report success just because `unpack` wrote a few files.** Success must mean every entry was read, validated, extracted, streams closed cleanly, and output published per contract.

## 15. Common Mistakes

1. **Writing `entry.getName()` straight into output without validation.** Leads to Zip Slip.
2. **Using `String.startsWith` alone for containment checks.** Can misclassify paths sharing a string prefix.
3. **Believing `Path.normalize()` solves symlinks.** False: normalize is purely syntactic.
4. **Believing `NOFOLLOW_LINKS` eliminates all races.** False if an attacker can mutate the tree concurrently.
5. **Using `CREATE`/`TRUNCATE_EXISTING` on untrusted entries.** Can overwrite existing files; use `CREATE_NEW` when disallowing overwrites.
6. **Extracting into a populated directory without a merge policy.** Causes collisions/overwrites.
7. **Skipping directory entries.** Loses empty directories.
8. **Assuming every ZIP emits `docs/` before `docs/a.txt`.** Not guaranteed; create parents safely after validation.
9. **Not capping entry counts.** An archive with millions of empty files breaks systems despite tiny byte counts.
10. **Trusting `entry.getSize()` to allocate arrays.** Can be `-1` or falsified.
11. **Calling `zip.readAllBytes()` on untrusted uploads.** Exhausts heap on zip bombs.
12. **Bounding only compressed ZIP size.** A few KiB compressed can expand massively.
13. **Forgetting `ZipOutputStream.close()`.** Central directory may remain incomplete.
14. **Thinking `ZipInputStream.read() == -1` means end of archive.** It means end of the current entry.
15. **Putting the output ZIP inside the walked source tree.** Causes self-referential/unstable input.
16. **Following source symlinks unchecked.** Can pack files outside the intended directory.
17. **Allowing backslashes arbitrarily in entry names.** Behavior diverges across OSes.
18. **Skipping duplicate/case-collision checks.** Can silently lose or overwrite files.
19. **Assuming `IOException` rolls back previously extracted files.** False: explicit staging/cleanup is required.
20. **Assuming CRC32 proves an archive is trustworthy.** False: checksums provide no cryptographic authentication.

## 16. Self-Check Questions

**Question 1.** Why must the packer write directory entries like `empty/`?

**Answer:** To preserve empty directories. If a ZIP only contains file entries, directories without files can disappear upon extraction.

**Question 2.** Why is checking `zipEntry.getSize() <= maxBytes` alone insufficient against zip bombs?

**Answer:** Metadata can be missing or untrusted, and many entries combined can still be huge. You must count actual decompressed bytes inside each `read` iteration before writing.

**Question 3.** If a ZIP contains `docs/a.txt` with no `docs/` entry, can the extractor still create it?

**Answer:** Yes. After the name is validated inside root, safely create parent directories and then create the new file.

**Question 4.** Why is `Path.startsWith(root)` better than `String.startsWith(root.toString())`?

**Answer:** It compares path components, avoiding mistaking `/safe/output2` for a child of `/safe/output`.

**Question 5.** What problem does `Files.newOutputStream(..., CREATE_NEW)` solve?

**Answer:** Prevents overwriting/truncating an existing file or symlink at the final path; it does not by itself stop an attacker swapping parent directories in a race.

**Question 6.** Why must testing `../escape.txt` verify both the exception and the filesystem?

**Answer:** Throwing an exception does not prove an outside file was never created first. Assertions must verify no offending file exists after the failed operation.

**Question 7.** If the tenth entry exceeds quota after nine valid entries were extracted, do the earlier files vanish automatically?

**Answer:** No. The demo only cleans up the entry currently being extracted; separate staging + cleanup/publish logic is needed for all-or-nothing behavior.

**Question 8.** Why should Java `ZipInputStream` not be used on a single `.gz` GZIP stream?

**Answer:** A ZIP archive has `ZipEntry` records and ZIP container structure, whereas GZIP is a different stream format; even though both can use DEFLATE, their headers and containers differ.

**Question 9.** The program runs on Linux yet an archive has an entry named `C:/tmp/a.txt`. Why does the exercise policy still reject it?

**Answer:** To preserve portability and prevent names from being interpreted as drive paths if extracted on Windows or by other tools.

### Java 17 Official References

- [ZipOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipOutputStream.html)
- [ZipInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipInputStream.html)
- [ZipEntry](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipEntry.html)
- [ZipFile](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipFile.html)
- [Files.walkFileTree and Files.newOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [Path.resolve, normalize, startsWith](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html)
- [LinkOption.NOFOLLOW_LINKS](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/LinkOption.html)
- [StandardOpenOption.CREATE_NEW](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardOpenOption.html)
- [SecureDirectoryStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/SecureDirectoryStream.html)