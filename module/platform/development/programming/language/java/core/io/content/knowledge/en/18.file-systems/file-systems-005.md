# ZIP File System in Java: Manipulating Archives with Path and Files

A `.zip` file is often treated as an archive that must be extracted before processing. Java NIO.2 also provides the **ZIP file system (ZipFS)**: mounting ZIP contents into a `FileSystem`, from which you can read, create, copy, rename, and delete entries using `Path` and `Files` themselves. This approach fits well when you need to manipulate many files inside a ZIP without manually managing each `ZipEntry`.

## 1. Goals and mental model

After this lesson, you will be able to:

- Create a new ZIP archive, open an existing ZIP, and close resources properly.
- Distinguish operating system paths from paths **inside the ZIP**.
- Use `Files.createDirectories`, `writeString`, `readString`, `copy`, `move`, `delete`, and `walk` on a ZIP.
- Understand provider boundaries, limitations, common errors, and risks when receiving untrusted ZIPs.
- Choose ZipFS or stream/entry-based APIs depending on the task.

Diagram:

```text
Operating system                ZIP file system
/tmp/work/lesson.zip  ─open─>   /
                                └── docs/
                                    ├── readme.md
                                    └── source.txt
Path of ZIP on machine          Path of entry inside ZIP
```

`Files` is a class that operates on `Path`; by default it is not limited to working only with disk files. Each `Path` belongs to a `FileSystem` and a `FileSystemProvider`. When a `Path` points to a ZipFS entry, `Files` operations are forwarded to the JDK's ZIP provider. The contents in the archive do not become regular files in an external directory.

Key types:

| Component | Role |
| --- | --- |
| `java.nio.file.Path` | Identifies the ZIP on disk, or an entry **inside** ZipFS; the two Path types have different providers. |
| `java.nio.file.FileSystem` | Context for accessing the ZIP's entries; must be closed via `close()`. |
| `java.nio.file.FileSystems` | Opens/creates ZipFS via `newFileSystem(...)`. |
| `java.nio.file.Files` | Reads/writes/lists/manipulates entries just like with a filesystem. |
| `jdk.zipfs` | ZIP filesystem provider bundled with common JDK builds; minimal runtime applications must include this module. |

## 2. Complete program: creating, traversing, reading, and modifying a ZIP

The following example is standalone and runs on Java 17+. It creates a dedicated temporary directory so it does not delete or overwrite your existing ZIPs. After the first pass, `try-with-resources` closes ZipFS to write the changes to the archive; the next pass reopens that ZIP file and modifies entries.

Save with the exact name **`ZipFsDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.FileSystem;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Map;
import java.util.stream.Stream;

public class ZipFsDemo {
    public static void main(String[] args) throws Exception {
        Path workDir = Files.createTempDirectory("zipfs-demo-");
        Path source = workDir.resolve("source.txt");
        Path archive = workDir.resolve("lesson.zip");
        Files.writeString(source, "Tệp nguồn\n", StandardCharsets.UTF_8);

        // Create a nonexistent ZIP. Inside the ZIP, use a Path from zipFs.
        try (FileSystem zipFs = FileSystems.newFileSystem(
                archive, Map.of("create", "true"))) {
            Path docs = zipFs.getPath("/docs");
            Files.createDirectories(docs);
            Files.copy(source, docs.resolve("source.txt"));
            Files.writeString(docs.resolve("readme.md"), "# ZIP FS\n",
                    StandardCharsets.UTF_8, StandardOpenOption.CREATE_NEW);

            try (Stream<Path> entries = Files.walk(zipFs.getPath("/"))) {
                entries.filter(path -> Files.isRegularFile(path))
                        .map(Path::toString)
                        .sorted()
                        .forEach(System.out::println);
            }
        }

        // Existing ZIP: open without create, read, rename, delete entry.
        try (FileSystem zipFs = FileSystems.newFileSystem(archive, Map.of())) {
            Path docs = zipFs.getPath("/docs");
            Path readme = docs.resolve("readme.md");
            System.out.print(Files.readString(readme, StandardCharsets.UTF_8));
            Path guide = docs.resolve("guide.md");
            Files.move(readme, guide);
            Files.delete(docs.resolve("source.txt"));
            System.out.println("guide exists: " + Files.exists(guide));
        }
    }
}
```

Compile and run in the directory containing the file:

```bash
javac ZipFsDemo.java
java ZipFsDemo
```

Stdout result:

```text
/docs/readme.md
/docs/source.txt
# ZIP FS
guide exists: true
```

The actual path of `lesson.zip` varies by machine, but it is not printed, so the stdout above is deterministic. When the program ends, the archive retains `/docs/guide.md`; `/docs/source.txt` has been deleted.

**Step-by-step walkthrough:**

1. `Files.createTempDirectory` creates a physical directory; `archive` is a `Path` belonging to the default filesystem. `Files.writeString(source, ...)` writes the source file *outside the ZIP*.
2. `FileSystems.newFileSystem(archive, Map.of("create", "true"))` opens a filesystem for the ZIP; the `create` option allows creating the archive if it does not exist yet. If the file is not a valid ZIP, opening may throw `ZipException`/`IOException`.
3. `zipFs.getPath("/docs")` creates a path *inside the archive*. `Files.createDirectories` creates a directory entry; `Files.copy` copies from a real file into the ZIP; `Files.writeString` writes another entry.
4. `Files.walk` returns a `Stream<Path>`, which must be closed with `try-with-resources`. Filtering regular files avoids printing `/` and `/docs`; sorting keeps output deterministic.
5. Closing `zipFs` is a required step to release resources and finalize writing; then the ZIP is reopened in existing mode. `Files.move` renames an entry, and `Files.delete` removes an entry. Changes are written upon closing.

## 3. Two Path spaces: the easiest point to confuse

```java
Path zipOnDisk = Path.of("backup.zip");       // Path on OS
// Inside an open block: FileSystem zipFs = ...
Path fileInZip = zipFs.getPath("/docs/a.txt"); // Path belonging to ZipFS
```

These two lines merely illustrate the difference; `zipFs` must be initialized in real code. `zipOnDisk.resolve("docs/a.txt")` does **not** point into the archive: it represents a filesystem path outside the ZIP. Conversely, `zipFs.getPath("/docs/a.txt")` points to the right entry while ZipFS is open.

You can use `zipFs.getPath("/docs").resolve("a.txt")` to build child paths. The `/` in the examples is ZIP path syntax; you should not build entry paths by concatenating the OS separator string. Only use `Files` on `Path` objects that are still valid and belong to the right provider.

The following operations all have clear meaning once both `Path` objects are declared:

| Need | API call | Meaning |
| --- | --- | --- |
| Outside ZIP → inside ZIP | `Files.copy(hostFile, zipEntry)` | Puts a file into the archive. |
| Inside ZIP → outside ZIP | `Files.copy(zipEntry, hostFile)` | Extracts **one** entry to an external directory. |
| Inside ZIP → inside ZIP | `Files.copy(entryA, entryB)` | Duplicates an entry within the appropriate filesystem. |
| Rename inside ZIP | `Files.move(oldEntry, newEntry)` | Moves/renames an entry. |
| Delete entry | `Files.delete(entry)` | Deletes an entry; directory must be empty if deleting a directory. |

If the target already exists, `Files.copy` normally throws `FileAlreadyExistsException`, unless `StandardCopyOption.REPLACE_EXISTING` is supplied and accepted by the provider. Avoid using `Files.move` across two providers with the assumption of an atomic operation; moving a file between filesystems may involve copying and deleting, which can fail partway through.

## 4. Opening a ZIP properly and managing its lifecycle

**Creating a new archive:**

```java
try (FileSystem fs = FileSystems.newFileSystem(
        archivePath, Map.of("create", "true"))) {
    Files.createDirectories(fs.getPath("/logs"));
    Files.writeString(fs.getPath("/logs/result.txt"), "OK\n");
}
```

This is an illustrative snippet using an already declared `archivePath` variable representing a `Path` on disk. In the JDK's ZipFS API, the `create` option takes the string `"true"`; if the ZIP already exists, the call opens that existing ZIP as well. If you require **creating only a brand-new file**, check/coordinate naming externally beforehand and handle concurrency conflicts; a standalone `Files.exists` check is not a lock.

**Opening an existing archive:**

```java
try (FileSystem fs = FileSystems.newFileSystem(archivePath, Map.of())) {
    Path entry = fs.getPath("/logs/result.txt");
    if (Files.isRegularFile(entry)) {
        String content = Files.readString(entry, StandardCharsets.UTF_8);
        System.out.println(content);
    }
}
```

These two snippets use `archivePath` from surrounding context and are not standalone programs. A read-only ZIP can be opened with `Map.of("readonly", "true")` if the provider and JDK version support that option; do not assume filesystem permissions outside the ZIP or all environment keys are portable across providers. If you simply need read-only behavior, avoid calling any write APIs and ensure the outer ZIP file is protected by OS permissions.

Some alternative APIs:

- `FileSystems.newFileSystem(Path, Map<String, ?>)`: uses the archive file's `Path`, convenient for everyday tasks.
- `FileSystems.newFileSystem(URI, Map<String, ?>)`: commonly uses a URI with the `jar:` scheme, such as `URI.create("jar:" + archivePath.toUri())`. Distinguish the archive's URI from an entry `Path` and from another filesystem's URI.
- `FileSystems.getFileSystem(URI)`: looks up an already registered filesystem by URI, without creating a new one. With `newFileSystem(URI, ...)`, opening a duplicate of an existing open filesystem may throw `FileSystemAlreadyExistsException`.

**Resource rule:** keep all entry operations inside `try (FileSystem fs = ...)`. After `fs.close()`, using a `Path` bound to that fs may throw `ClosedFileSystemException`. Do not open/close repeatedly for individual entries; process a batch of tasks in one ZipFS session and close when done.

## 5. Listing, finding, reading, and writing entries

Once you have an open `FileSystem fs`:

```java
Path root = fs.getPath("/");
try (Stream<Path> stream = Files.walk(root)) {
    stream.filter(Files::isRegularFile)
          .map(root::relativize)
          .forEach(System.out::println);
}
```

`Files.walk` traverses recursively and can be resource-intensive on large ZIPs; use `Files.list(fs.getPath("/docs"))` when you only need one level. Both return a stream that must be closed. Traversal order is not guaranteed, so call `sorted()` if tests require deterministic output. `root.relativize(path)` converts `/docs/a.txt` to `docs/a.txt` within the same filesystem; do not mix `Path` objects from two providers in `relativize`/`resolve` calls that require the same context.

For small text files, `Files.readString(entry, StandardCharsets.UTF_8)` and `Files.writeString(...)` are convenient. Use `Files.newBufferedReader`, `newBufferedWriter`, or streams for large data so the entire entry is not held in RAM. Ensure the parent directory exists before writing: `Files.createDirectories(entry.getParent())`. Common write options:

- `CREATE_NEW`: create only if the entry does not yet exist; useful to avoid accidentally overwriting a file.
- `CREATE`: create if absent, though it can open an existing file.
- `TRUNCATE_EXISTING`: erase old content when opening for write if the entry exists.
- `APPEND`: use only when permitted by the provider and file semantics; ZIP is not optimized for frequent log appending.

When handling non-text bytes, prefer `Files.newInputStream`/`newOutputStream`, `Files.copy`, or `Files.readAllBytes` for small payloads; avoid `readString` for images, classes, PDFs, or binary data.

## 6. Write behavior and limitations to understand

An archive is a container file. Modifying an entry is **not equivalent** to writing bytes directly into an OS directory: the provider may reorganize and rewrite the archive data upon closing, so bulk writes, large sizes, or repeated open/close cycles can be expensive. Do not assume renaming, copying, or writing entries has the same cost and atomicity as a physical filesystem.

For real projects:

1. Open ZipFS once for a batch, operate on `Path` objects of that filesystem, and close once; avoid processing files one by one with separate ZIP open/close cycles.
2. Always decide explicitly how name collisions are handled (preserve existing, reject, or `REPLACE_EXISTING`) and handle `IOException` errors.
3. Do not assume `StandardCopyOption.ATOMIC_MOVE` works with ZIPs. Do not treat archive updates as transactions: if the process stops mid-modification, the file may not be in the expected state.
4. For critical data, work on a temporary ZIP copy on the **same OS target filesystem**, verify the result, and then replace the target archive using an appropriate strategy; keep backups and prepare error handling. File replacement on the OS can be requested as atomic, though that depends on the provider/file store.
5. Avoid multiple writers modifying the same ZIP concurrently. Synchronize at the application level or use a single-writer workflow; filesystem locks and ZipFS caches do not replace a coordination strategy.

ZipFS is not a complete POSIX file system. Permissions, symbolic links, file attributes, renames, and advanced options may differ, be absent, or be unsupported. `Files.setPosixFilePermissions` and `WatchService`, for instance, should not be assumed to work. Nor is ZipFS an API for automatically encrypting or opening password-protected ZIPs.

**Performance:** well suited for a moderate number of entries and random access across many entries; for large files, stream data to bound RAM usage. Evaluate total size, entry count, write frequency, and filesystem close time. Do not read an entire archive into a byte array unless you are certain of its size limits.

## 7. Reading untrusted ZIPs and safe extraction

This lesson mainly operates *inside* ZipFS, yet when copying entries out to an OS directory you must pay special attention:

- **ZIP Slip / path traversal:** an externally supplied entry name can contain `../` or an absolute path. Normalize the target path and ensure the destination remains within the permitted extraction directory. Never append the raw entry name directly to the host path and write immediately.
- **ZIP bomb:** a small archive can decompress into a huge amount of data, contain vast numbers of entries, or have deeply nested paths. Bound the entry count, decompressed size, time, and storage; overall limits must be checked while streaming, not just by trusting metadata.
- **Anomalous entries:** normalize names, handle separators, duplicate names, encoded names, empty directories, unsupported file/attribute types, and all `IOException`s.
- **Untrusted sources:** do not execute programs or scripts or load classes extracted from a ZIP; treat them strictly as data.

Sketch of checking the destination path when extracting an entry (this snippet uses `entry` as a ZipFS Path, and `destinationRoot` as a normalized OS directory):

```java
Path root = destinationRoot.toAbsolutePath().normalize();
Path relative = entry.isAbsolute()
        ? entry.getRoot().relativize(entry)
        : entry;
Path dest = root.resolve(relative.toString()).normalize();
if (!dest.startsWith(root) || dest.equals(root)) {
    throw new SecurityException("Entry path ngoài thư mục đích");
}
```

This is only **one layer of path-syntax checking**, not a complete safe extractor. With malicious data, you need clear policies for existing symbolic links in the target directory, check/write race conditions, quotas, and special files; consider `SecureDirectoryStream` where supported and an isolated extraction environment. Do not rely solely on `normalize()` to protect against links or concurrent filesystem changes.

## 8. Common errors and how to handle them

| Symptom | Common cause | How to handle |
| --- | --- | --- |
| `NoSuchFileException` | The ZIP does not exist yet or an entry/parent is missing. | Verify the archive; create a new one with `create=true` when intended; create parent directories inside the ZIP first. |
| `FileAlreadyExistsException` | Creating/copying into an entry that already exists. | Choose `CREATE_NEW` or `REPLACE_EXISTING` according to policy. |
| `ProviderNotFoundException` | Runtime is missing the ZIP provider, e.g., a custom `jlink` image without `jdk.zipfs`. | Check the runtime image/modules and include `jdk.zipfs` when packaging. |
| `FileSystemAlreadyExistsException` | Reopening the same `jar:` URI while that FileSystem is still registered. | Reuse the existing filesystem or manage its lifecycle; do not open duplicate URIs arbitrarily. |
| `ClosedFileSystemException` | Reading/writing entries after closing the `FileSystem`. | Keep all entry processing inside a `try-with-resources` block. |
| `ProviderMismatchException` | Mixing Paths from different providers in an operation requiring the same system. | Clearly distinguish OS Paths from ZipFS Paths; use cross-provider copy operations when supported. |
| `ZipException`/`IOException` | Corrupted archive, non-ZIP data, permissions, or I/O failure. | Validate inputs, report contextual errors, close resources, and do not continue with a corrupted archive. |
| Changes not immediately visible in the outer file | The FileSystem has not been closed yet or the application still holds write streams. | Close streams and `FileSystem` before another workflow uses the archive. |

Errors and when they are thrown depend on the operation, provider, and operating system; the table above shows typical scenarios, not a mandatory 1-to-1 mapping.

## 9. When to use ZipFS, ZipFile, or ZipInputStream?

| Tool | Main advantage | Choose when |
| --- | --- | --- |
| **ZipFS + `Path`/`Files`** | Unified API to read/write/copy/rename/delete multiple entries. | You need to treat a ZIP as a directory tree and update the archive. |
| `java.util.zip.ZipFile` | Look up and read individual entries in an existing ZIP. | Mostly reading, wanting to iterate entries and obtain `InputStream`. |
| `ZipInputStream` | Sequentially iterate entries from a data stream. | Reading a ZIP stream without needing a filesystem or random access. |
| `ZipOutputStream` | Write a ZIP sequentially with `ZipEntry`. | Streaming archive creation where entry order/metadata control is needed. |

There is no single best API for all cases. ZipFS is most useful when performing varied operations through the same NIO interface. If you are only extracting entries sequentially from a network stream, the `java.util.zip` classes are often simpler. Standard ZIPs compress per entry; ZIP does not provide full filesystem semantics like a database or transactions.

## 10. Usage checklist and practice exercises

Before implementing: confirm where the archive lives, which provider entries belong to, whether the ZIP is newly created or already exists, overwrite policy, text encoding, size limits, path security, `close()` management, and error-handling strategy.

**Exercise 1 — Add a file to a ZIP.** Based on the sample program, create `/images/info.txt` using `Files.createDirectories` and `Files.writeString`, then use `Files.walk` to prove the entry appeared. Try deliberately writing with `CREATE_NEW` a second time to observe the duplicate-name error.

**Exercise 2 — Copy outward.** Open an existing ZIP, select `/docs/guide.md`, and use `Files.copy` to write it to a new file under `workDir`. Verify the content outside the ZIP with `Files.readString`. Make sure the path outside the ZIP is constructed from `workDir` rather than `zipFs.getPath`.

**Exercise 3 — Verify lifecycle and integrity.** Open a ZIP, update two entries, close ZipFS, and reopen it to compare contents. Then try accessing an old `Path` after `close()` and explain why a `Path` must be recreated from the new filesystem.

**Remember:** `archivePath` points to the *ZIP container on the OS*; `zipFs.getPath("/...")` points to an *entry inside the container*. Use `Files` on the right `Path`, group operations into one `FileSystem` lifecycle, close resources, and treat external ZIP data as untrusted input.
