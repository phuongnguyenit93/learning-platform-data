# ZipInputStream, ZipOutputStream, and ZipEntry in Java Core I/O

## 1. What Is ZIP and Why Are These Three Classes Needed?

ZIP is an **archive** format: a file containing multiple entries (files, directories, and metadata), which may use compression per entry. Java provides the standard `java.util.zip` library to read and create ZIP archives without needing a third-party library.

Three essential classes:

- **`ZipInputStream`**: sequentially reads each entry from an `InputStream` containing ZIP data. It is suitable when the source is a stream and random access is not needed.
- **`ZipOutputStream`**: creates a ZIP archive and writes each entry sequentially to an `OutputStream`. It automatically writes the required ZIP structures when finalizing the archive.
- **`ZipEntry`**: describes **one item** in the archive: name, compression method, size (if known), CRC-32, timestamp, comment/extra field, etc. It is metadata, **not a stream of content bytes**.

Visualization:

```text
Writing ZIP                             Reading ZIP
-----------                             -----------
OutputStream (file/network/memory)      InputStream (file/network/memory)
       ^                                       |
       |                                       v
ZipOutputStream                         ZipInputStream
       ^                                       |
 putNextEntry(ZipEntry)                  getNextEntry() -> ZipEntry
 write(payload bytes)                    read(payload bytes)
 closeEntry()                            closeEntry()
       |                                       |
   [a.txt][b.bin][folder/]              process each entry in sequence
```

A ZIP can contain multiple entries. **The boundary between entries is defined by the ZIP format structure**, not a custom text delimiter. Entries can use either the `DEFLATED` (compressed) or `STORED` (uncompressed) method.

## 2. Differences Between a ZIP File, an Entry, and a Stream

Suppose `backup.zip` contains:

```text
backup.zip
├── docs/
│   ├── hello.txt
│   └── guide.md
└── image.bin
```

- `backup.zip` is the **outer ZIP file**, opened via `Files.newInputStream` or `Files.newOutputStream`.
- `docs/`, `docs/hello.txt`, `docs/guide.md`, and `image.bin` are **entries**, identified by `ZipEntry.getName()`.
- `ZipInputStream.read()` reads **the contents of the current entry**, rather than returning an independent `InputStream` for each entry.
- `ZipOutputStream.write()` writes **bytes for the current entry** after `putNextEntry()`.
- `ZipEntry` holds the name and attributes; to get the content bytes you must use the appropriate stream.

The standard convention is for entry names to use `/` even on Windows. Directory entries typically have names ending with `/`, such as `docs/`, and `ZipEntry.isDirectory()` recognizes them by this convention. A ZIP may contain no separate directory entry while still containing a file named `docs/hello.txt`; when extracting, parent directories must still be created explicitly.

## 3. Writing Flow with `ZipOutputStream`

Basic workflow:

```java
try (ZipOutputStream zout = new ZipOutputStream(
        Files.newOutputStream(zipPath), StandardCharsets.UTF_8)) {

    ZipEntry entry = new ZipEntry("docs/hello.txt");
    zout.putNextEntry(entry); // Open a new entry in the archive
    zout.write(contentBytes); // Write data belonging to the current entry
    zout.closeEntry();        // Close the entry
} // close() finalizes the archive and closes the underlying stream
```

This is an **illustrative snippet inside a method**: `zipPath` and `contentBytes` must be declared beforehand, and `java.nio.file.*`, `java.nio.charset.StandardCharsets`, and `java.util.zip.*` must be imported.

Important contract:

1. **`putNextEntry(entry)`** opens a new entry, writes its corresponding header, and prepares the write state. If a previous entry has not been closed yet, `putNextEntry` may close the previous entry per the implementation contract; nevertheless, you should call `closeEntry()` explicitly for clarity.
2. **`write(byte[])` or `write(byte[],off,len)`** writes bytes of the currently open entry. If no entry is open, you must not arbitrarily write payload data.
3. **`closeEntry()`** finalizes the current entry: flushes/writes required metadata such as size and CRC, and ends the compressed data section. It **does not close the entire archive**.
4. **`finish()`** writes the ZIP ending structures without closing the underlying stream. Useful if you want to complete the ZIP while keeping the underlying `OutputStream` open. After `finish()`, no further entries can be written.
5. **`close()`** closes `ZipOutputStream`, finishes the ZIP if needed, and closes the underlying stream. Using `try-with-resources` is the default choice.

**If you only call `flush()` on the output stream and send the file**, the ZIP may lack its central directory and fail to read properly. Finalize the ZIP with `finish()` or `close()`.

### 3.1. Writing a Directory

```java
zout.putNextEntry(new ZipEntry("docs/"));
zout.closeEntry();
```

This is a snippet within scope of a `ZipOutputStream zout`. A name with a trailing `/` indicates a directory entry and normally contains no payload. ZIP does not require every directory to have its own entry; you can write only the files under `docs/`.

### 3.2. Writing Two Consecutive File Entries

```java
zout.putNextEntry(new ZipEntry("first.txt"));
zout.write("One".getBytes(StandardCharsets.UTF_8));
zout.closeEntry();

zout.putNextEntry(new ZipEntry("second.txt"));
zout.write("Two".getBytes(StandardCharsets.UTF_8));
zout.closeEntry();
```

Do not write bytes for the second file before opening `second.txt`, otherwise those bytes will be appended to the currently open entry.

## 4. Reading Flow with `ZipInputStream`

Sequential entry-reading workflow:

```java
try (ZipInputStream zin = new ZipInputStream(
        Files.newInputStream(zipPath), StandardCharsets.UTF_8)) {

    ZipEntry entry;
    byte[] buffer = new byte[8192];

    while ((entry = zin.getNextEntry()) != null) {
        System.out.println("entry=" + entry.getName());

        int n;
        while ((n = zin.read(buffer)) != -1) {
            // Only buffer[0..n) contains newly read bytes of this entry.
            processBytes(buffer, 0, n); // application-defined callback
        }

        zin.closeEntry();
    }
}
```

This is an **illustrative algorithmic pattern**, not standalone, since `zipPath` and `processBytes` are supplied by the application.

Usage rules:

- **`getNextEntry()`** advances to the next entry and returns its metadata, or `null` when no entries remain.
- **`read(byte[])`** reads decompressed bytes of the current entry; returns a **positive byte count** (or potentially 0 per the overload contract if a 0-length read is requested), and **`-1` when the end of that entry's content is reached**.
- `-1` from `read()` means **end of the current entry**. It **does not prove the archive has no more entries**. Only `getNextEntry() == null` signals the end of the entry list in this stream.
- **`closeEntry()`** finishes processing the current entry; if it has not been fully read, skipping/draining the remainder may perform I/O and detect ZIP errors.
- **`close()`** closes the ZIP input stream and the underlying stream.

A single `read(buffer)` call is not guaranteed to fill the buffer or read the entire entry. Always loop until `-1`; do not use `available()` as "the number of bytes remaining in the ZIP". `ZipInputStream.available()` is not a reliable measure of remaining data size.

## 5. Complete Java 17+ Example: Creating and Reading Back a ZIP

This example creates a real ZIP in a temporary directory containing a directory entry, a UTF-8 text file, and a binary file. After `ZipOutputStream` cleanly closes the archive, `ZipInputStream` reads each entry and prints the results. The displayed output has a deterministic order.

Create file `ZipStreamsDemo.java`:

```java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;
import java.util.zip.ZipOutputStream;

public class ZipStreamsDemo {
    public static void main(String[] args) throws IOException {
        Path archive = Files.createTempFile("zip-streams-", ".zip");

        try {
            try (OutputStream raw = Files.newOutputStream(archive);
                 ZipOutputStream zout = new ZipOutputStream(
                         raw, StandardCharsets.UTF_8)) {

                zout.putNextEntry(new ZipEntry("docs/"));
                zout.closeEntry();

                zout.putNextEntry(new ZipEntry("docs/hello.txt"));
                zout.write("Xin chào ZIP".getBytes(StandardCharsets.UTF_8));
                zout.closeEntry();

                zout.putNextEntry(new ZipEntry("data.bin"));
                zout.write(new byte[] {0, 1, 2, (byte) 255});
                zout.closeEntry();
            }

            try (InputStream raw = Files.newInputStream(archive);
                 ZipInputStream zin = new ZipInputStream(
                         raw, StandardCharsets.UTF_8)) {

                ZipEntry entry;
                byte[] buffer = new byte[1024];

                while ((entry = zin.getNextEntry()) != null) {
                    ByteArrayOutputStream content = new ByteArrayOutputStream();
                    int n;

                    while ((n = zin.read(buffer)) != -1) {
                        content.write(buffer, 0, n);
                    }

                    if (entry.isDirectory()) {
                        System.out.println("directory: " + entry.getName());
                    } else if (entry.getName().endsWith(".txt")) {
                        String text = new String(
                                content.toByteArray(), StandardCharsets.UTF_8);
                        System.out.println(
                                entry.getName() + " = " + text);
                    } else {
                        System.out.println(
                                entry.getName() + " = "
                                + Arrays.toString(content.toByteArray()));
                    }

                    zin.closeEntry();
                }
            }
        } finally {
            Files.deleteIfExists(archive);
        }
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac ZipStreamsDemo.java
java ZipStreamsDemo
```

Expected stdout:

```text
directory: docs/
docs/hello.txt = Xin chào ZIP
data.bin = [0, 1, 2, -1]
```

**Step-by-step explanation:**

1. Create a ZIP with `Files.createTempFile`, then write through `ZipOutputStream`.
2. Write the directory entry `docs/` with an empty payload.
3. Write `docs/hello.txt`, encoding the string to UTF-8 bytes **before compression**. Entry name and content are two separate kinds of data.
4. Write `data.bin` containing bytes 0, 1, 2, `0xFF`. Java `byte` is signed, so `Arrays.toString` prints `0xFF` as `-1`; this is **not an EOF indicator** from `ZipInputStream.read()`.
5. Once the output ZIP is closed, the archive has all complete ZIP structures ready to be opened by ZIP input.
6. `getNextEntry()` returns the three entries in order. The `zin.read(buffer)` loop retrieves **the exact decompressed bytes of one entry** until `-1`.
7. The example uses `ByteArrayOutputStream` to simplify printing. For large entries or untrusted ZIPs, **do not buffer the entire content in RAM**; process as a stream and enforce byte limits (see the security section).

Using `try-with-resources` closes both the ZIP wrapper and underlying streams normally or on error. The `finally` block deletes the temporary file when permitted by the operating system.

## 6. `ZipEntry`: Reading and Setting Metadata Properly

`ZipEntry` represents metadata about a ZIP component. Useful APIs:

| API | Meaning | Note |
| --- | --- | --- |
| `getName()` | Entry name inside the ZIP | **Must not be trusted** when used as an OS path |
| `isDirectory()` | Whether the name ends with `/` | Implicit parent directories can exist without separate directory entries |
| `getSize()` | **Decompressed** data size | May return `-1` if unknown in the local header |
| `getCompressedSize()` | Compressed data size | May return `-1` if unknown |
| `getCrc()` | 32-bit CRC-32 of uncompressed content | May return `-1` if unknown |
| `getMethod()` | `STORED` or `DEFLATED` | Depends on the entry and ZIP format |
| `getTime()`, `getLastModifiedTime()` | Entry timestamp if present | Precision and preservation may vary |
| `getComment()`, `getExtra()` | Comment/extra fields if provided | Stream readers do not always receive full central-directory metadata |
| `setMethod()`, `setSize()`, `setCrc()` | Entry metadata when writing | Must be valid, especially for `STORED` |

A `ZipEntry` can be read from `zin.getNextEntry()` or constructed with `new ZipEntry("path/in/archive")`. It does not own the `ZipInputStream` or `ZipOutputStream`.

### 6.1. Why Can `getSize()` Be `-1`?

When writing a ZIP with `DEFLATED`, the writer may not know the uncompressed length, compressed length, and CRC of the entry in advance. Those values can be placed in a **data descriptor** after the payload or in the central directory at the end of the archive.

`ZipInputStream` is a **sequential** reader that typically reads metadata from the local file header. Therefore, `entry.getSize()` or `entry.getCrc()` may be `-1` when first starting to read an entry, even though the entry is completely valid.

Do not write code like `new byte[(int) entry.getSize()]` when `getSize()` is unknown. Count **actual decompressed bytes** both for processing data and for preventing ZIP bombs.

### 6.2. An Entry Name Is Not Necessarily a Safe Path

Names such as `../secret.txt`, `/etc/config`, or other special strings may appear in ZIP archives received from external sources. When using them to write to disk, enforce root boundary checks (see the security section). Never take `ZipEntry.getName()`, call `destination.resolve(name)` directly, and write the file without validation.

## 7. `DEFLATED` and `STORED`: Two Common Modes

`ZipEntry.DEFLATED` is the DEFLATE compression method, usually used by `ZipOutputStream` by default. `ZipEntry.STORED` stores uncompressed bytes.

| Property | `DEFLATED` | `STORED` |
| --- | --- | --- |
| Compresses content | Yes | No |
| CPU during write/read | Incurs compression/decompression cost | No DEFLATE needed |
| Archive size | Can be smaller, or slightly larger for hard-to-compress data | Close to original size plus ZIP metadata |
| Must know size/CRC **before** `putNextEntry()` | Usually not required | **Yes**; requires size, compressed size, and CRC |
| When suitable | Text, JSON, repetitive data | Already-compressed data, avoiding recompression, or format requirement |

DEFLATED example:

```java
ZipEntry entry = new ZipEntry("notes.txt");
entry.setMethod(ZipEntry.DEFLATED);
zout.putNextEntry(entry);
zout.write(data);
zout.closeEntry();
```

This is a snippet with existing `ZipOutputStream zout` and `byte[] data`. When size/CRC are not set beforehand, the writer can compute them after finishing the entry.

### 7.1. Writing STORED Requires Computing CRC and Size Ahead of Time

```java
import java.util.zip.CRC32;
import java.util.zip.ZipEntry;

// Inside a method with ZipOutputStream zout and byte[] data:
CRC32 crc = new CRC32();
crc.update(data);

ZipEntry entry = new ZipEntry("already-compressed.bin");
entry.setMethod(ZipEntry.STORED);
entry.setSize(data.length);
entry.setCompressedSize(data.length);
entry.setCrc(crc.getValue());

zout.putNextEntry(entry);
zout.write(data);
zout.closeEntry();
```

`STORED` requires **size equal to compressed size** and a known CRC-32 **before writing the entry**. Missing metadata can cause `putNextEntry()` to throw `ZipException`. If the actual bytes written do not match the declared size/CRC, writing or closing the entry may also fail.

For very large data whose CRC is not yet known, you may have to read it once to compute CRC and read it a second time, or switch to `DEFLATED` so the writer computes metadata afterward. Avoid loading an entire large file into a `byte[]` just to compute CRC.

### 7.2. Compression Level

`ZipOutputStream.setLevel(int level)` sets the DEFLATED compression level for subsequent entries, typically from `Deflater.NO_COMPRESSION` (0) to `Deflater.BEST_COMPRESSION` (9), or `Deflater.DEFAULT_COMPRESSION` (-1). Higher levels can consume significantly more CPU without shrinking the file noticeably; benchmark on real data. The level is not a security flag or a measure of ZIP "standard compliance".

## 8. ZIP Entry Names and Character Encoding

Entry names are metadata that can contain Unicode; Java supports constructors taking a `Charset`:

```java
ZipOutputStream zout = new ZipOutputStream(
        Files.newOutputStream(zipPath), StandardCharsets.UTF_8);

ZipInputStream zin = new ZipInputStream(
        Files.newInputStream(zipPath), StandardCharsets.UTF_8);
```

These are **two separate stream-creation snippets**; do not open a writer and reader simultaneously on the same ZIP file being created as a normal workflow. Finish/close the writer before opening the reader.

Distinction:

- The `Charset` on `ZipInputStream`/`ZipOutputStream` controls **encoding of entry names and related ZIP metadata** according to format rules.
- An entry's content is an **arbitrary byte array**. If it is text, code must choose the charset explicitly when calling `String.getBytes` or `new String(bytes, charset)`.
- ZIPs from older tools sometimes use code pages other than UTF-8; if ZIP metadata/flags mismatch, entry names may decode incorrectly or throw errors. Choose the charset based on the archive's specification/source rather than guessing blindly.
- When a ZIP marks entry names as UTF-8 per the standard, that flag governs how the reader decodes; the constructor `Charset` does not "force every entry regardless of the flag".

Entry names should use `/` per the ZIP convention. Do not rely on the OS `File.separator` when constructing internal names inside an archive.

## 9. `ZipInputStream` or `ZipFile`?

Both read ZIP archives, but serve different needs:

| Criterion | `ZipInputStream` | `ZipFile` |
| --- | --- | --- |
| Data source | An `InputStream` | A ZIP file accessible via path or `File` |
| Entry access | Sequential via `getNextEntry()` | List and retrieve specific entries via `getEntry()`/`entries()` |
| Reading data | `read()` on the stream pointing to the current entry | `getInputStream(entry)` returns an entry content stream |
| Metadata | Primarily from local file headers | Can rely on the central directory; more complete |
| Best suited for | Uploads/network streams, sequential extraction | Picking arbitrary files in an archive, repeated access |
| Lifecycle | A single stream; process entries in order | Properly close `ZipFile` and its entry streams |

`ZipInputStream` is not a good fit if you need to immediately open `report.csv` at the end of an archive without walking through preceding entries. When the ZIP file is already on disk and random access by name is needed, `ZipFile` is usually more suitable.

There is also the **Zip File System** option (`FileSystems.newFileSystem` with the `jar` provider) to manipulate `Path` objects inside an archive; that is a different model from the sequential stream reading/writing covered here.

## 10. Safe Extraction: Preventing Zip Slip

When accepting ZIP files from users, an entry might be named `../../outside.txt`. If an application joins that name to the target directory without checking, it can write **outside the permitted directory**. This is the **Zip Slip** vulnerability.

Always resolve a valid root, normalize the path, and reject paths escaping the root:

```java
Path root = destination.toAbsolutePath().normalize();
Path target = root.resolve(entry.getName()).normalize();

if (!target.startsWith(root)) {
    throw new IOException("ZIP entry escapes destination");
}
```

This is an **illustrative snippet**; `destination` and `entry` are existing variables. Additional requirements apply:

1. Reject absolute paths or invalid entry names.
2. Reject `..` components that cause the target to escape the root.
3. Reject special names/path formats invalid on the target operating system.
4. Create parent directories before opening the target file.
5. Choose a duplicate-name policy: `CREATE_NEW` so existing files are not silently overwritten; check for duplicate entry names in the ZIP.
6. **Important:** checking `normalize()/startsWith()` only protects lexically at the path level. If the extraction directory already contains **symlinks** or a malicious process concurrently modifies the directory tree, traversing a symlink/TOCTOU can still cause writes outside the root. It is safer to extract into a **new, private directory without symlinks that no other actor can modify concurrently**; for high threat models, use platform-level directory-handle relative path opening / symlink-safe APIs.

Do not treat `ZipEntry.isDirectory()` as proof that an entry is safe: `ZipEntry` only holds metadata, whereas actual writes depend on the resolved path.

## 11. Preventing ZIP Bombs: Count Actual Bytes, Never Trust Metadata

A ZIP bomb is an archive that is very small compressed but decompresses into massive amounts of data, or contains millions of entries. `getSize()` may be unknown beforehand or untrustworthy for unverified inputs.

Minimum limits for an extraction service:

- **Maximum number of entries**, e.g. 1,000.
- **Decompressed size per entry**, e.g. 20 MiB.
- **Total decompressed size across all entries**, e.g. 100 MiB.
- **Path depth / total path length** and directory count.
- **CPU time / timeout**, access counts, disk space, and concurrent processing quota.
- You may add a decompression-ratio threshold with a clear measurement definition, but do not rely solely on ratio: a legitimate archive that compresses extremely well can still have a high ratio.

Example byte-processing loop with actual quotas:

```java
long currentSize = 0;
int n;

while ((n = zin.read(buffer)) != -1) {
    if (n > MAX_ENTRY_BYTES - currentSize
            || n > MAX_TOTAL_BYTES - totalSize) {
        throw new IOException("ZIP extraction size limit exceeded");
    }

    currentSize += n;
    totalSize += n;
    output.write(buffer, 0, n);
}
```

This is an **illustrative snippet inside the processing loop of one entry**, with `ZipInputStream zin`, `OutputStream output`, `byte[] buffer`, `long totalSize`, and defined quota constants. Checking `n > quota - used` avoids overflow when adding, provided the `used` variables start non-negative and do not exceed the quota.

`Files.copy(zin, target)` or `zin.transferTo(output)` are convenient, but do not automatically enforce decompressed byte limits per your business policy. For untrusted archives, read in blocks and check quotas before every write.

### 11.1. Extraction Pattern with Quotas and Path Validation

The method below is **illustrative within its design scope**, not a guarantee against all concurrent filesystem attack vectors:

```java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

static void extractIntoPrivateDirectory(
        InputStream zipData, Path privateRoot) throws IOException {

    final long MAX_ENTRY_BYTES = 20L * 1024 * 1024;
    final long MAX_TOTAL_BYTES = 100L * 1024 * 1024;
    final int MAX_ENTRIES = 1000;

    // privateRoot must be a new directory, without symlinks and
    // not concurrently modified by another actor.
    Path root = privateRoot.toAbsolutePath().normalize();
    long total = 0;
    int count = 0;
    byte[] buffer = new byte[8192];

    try (ZipInputStream zin = new ZipInputStream(zipData)) {
        ZipEntry entry;
        while ((entry = zin.getNextEntry()) != null) {
            if (++count > MAX_ENTRIES) {
                throw new IOException("Too many ZIP entries");
            }

            Path relative = Path.of(entry.getName());
            Path target = root.resolve(relative).normalize();
            if (relative.isAbsolute() || !target.startsWith(root)
                    || target.equals(root)) {
                throw new IOException("Unsafe ZIP entry path");
            }

            if (entry.isDirectory()) {
                Files.createDirectories(target);
            } else {
                Files.createDirectories(target.getParent());
                long entryBytes = 0;

                try (OutputStream out = Files.newOutputStream(
                        target, StandardOpenOption.CREATE_NEW,
                        StandardOpenOption.WRITE)) {
                    int n;
                    while ((n = zin.read(buffer)) != -1) {
                        if (n > MAX_ENTRY_BYTES - entryBytes
                                || n > MAX_TOTAL_BYTES - total) {
                            throw new IOException("ZIP content too large");
                        }
                        out.write(buffer, 0, n);
                        entryBytes += n;
                        total += n;
                    }
                }
            }
            zin.closeEntry();
        }
    }
}
```

**Conditions for using this pattern:**

- The caller must **pre-create an empty, private directory** and pass it as `privateRoot`. This method does not create the root itself and does not offer absolute protection if another actor can create symlinks inside the tree between operations. For untrusted sources under a strong threat model, use sandboxing or OS-appropriate symlink-safe path traversal mechanisms.
- `Path.of(entry.getName())` may throw `InvalidPathException` on invalid names; catch and translate this into an invalid-archive error at the API boundary.
- `CREATE_NEW` refuses to overwrite existing files, even if another entry in the ZIP shares the same name. That is a policy choice; for partially extracted temporary files on error, the application must clean them up according to its own transaction workflow.
- Do not use `closeEntry()` as a substitute for quotas: if an oversized entry is encountered, throw an exception to abort extraction instead of attempting to drain the entire archive.
- ZIP files can contain path names with OS-specific semantics; on Windows, watch out for device names, `:` characters, trailing dots/spaces, case sensitivity, and path limits. Always test in the target environment.

This method is presented to teach the primary layers of defense, not as a complete production extractor. Real applications also need time quotas, directory counts, file permissions, disk space checks, progress reporting, cancellation, antivirus scanning where appropriate, and concurrency/symlink testing.

## 12. CRC-32 and Data Integrity

CRC-32 in ZIP detects accidental transmission/storage corruption. When an entry is read completely through `ZipInputStream`, the implementation can verify the CRC and declared size upon reaching the end of the entry, throwing `ZipException` on mismatch.

However:

- CRC-32 is **not** a digital signature, MAC, or authentication code; an attacker can alter content and recompute the CRC.
- Never use CRC-32 to decide that a ZIP is safe or came from a trusted source.
- Never assume `getCrc()` is already available at the start of an entry.
- Reading/closing a ZIP can throw `ZipException`, `EOFException`, or `IOException` if data is truncated or corrupted. Handle the error path and never silently publish partially extracted files as complete.

If authenticity guarantees are required, use an application-layer signature/MAC mechanism or an authenticated container format with proper verification procedures.

## 13. ZIP Is Not Encrypted or a Secure Backup by Default

Standard Java `ZipOutputStream` **does not provide password-protected/encrypted ZIP creation**. It compresses and packages data, without protecting content from readers. Likewise, JDK's `ZipInputStream` is not a general-purpose solution for ZIPs encrypted using common password/encryption variants.

Do not treat a `.zip` file as secure merely because it is unreadable in a text editor. If security is required, apply appropriate encryption/authentication at another layer or use a vetted ZIP library supporting the format, verifying provenance and proper configuration.

Furthermore, ZIP is not a format that stores all operating system metadata uniformly. POSIX permissions, symlinks, owner/group, and extended attributes may reside in extra fields or tool-specific conventions; simply using JDK `ZipEntry` does not mean all permissions/symlinks will be accurately restored upon extraction.

## 14. Stream I/O, Buffers, and Memory Usage

The strength of `ZipInputStream`/`ZipOutputStream` is **sequential stream processing**. For large files, you can use an 8 KiB or 64 KiB buffer instead of reading everything into a `byte[]`.

Example of streaming a file into a ZIP (in-method pattern):

```java
try (InputStream fileIn = Files.newInputStream(sourceFile)) {
    zout.putNextEntry(new ZipEntry(entryName));
    byte[] buffer = new byte[8192];
    int n;
    while ((n = fileIn.read(buffer)) != -1) {
        zout.write(buffer, 0, n);
    }
    zout.closeEntry();
}
```

Assume `zout` is an open `ZipOutputStream`, and `sourceFile` and `entryName` have been validated. Do not add a file to a ZIP under an absolute OS path. Entry names should be relative paths using `/` and contain no sensitive information.

When extracting, similarly use a fixed buffer and write `output.write(buffer,0,n)`. This bounds the **intermediate buffer** size, though you must still add actual target quotas and concurrency limits.

If creating very many ZIPs concurrently, total memory calculations must account for `ZipOutputStream`/`ZipInputStream` instances, buffers owned by `Deflater`/`Inflater`, file handles, queued bytes, and executor threads. Close streams promptly when finished to release resources.

## 15. Common Mistakes

| Mistake | Consequence | Correct Approach |
| --- | --- | --- |
| Not calling `putNextEntry()` before `write()` | No valid entry to receive the payload | Per entry: open → write → close |
| Only calling `flush()` and using an unfinished archive | ZIP lacks its central directory | Call `finish()` or `close()` |
| Assuming `read() == -1` means end of the entire ZIP | Stops after the first entry | Call `getNextEntry()` until `null` |
| Assuming `getSize()` is always positive | Metadata may be unknown | Count actual bytes |
| Allocating `byte[(int)getSize()]` unchecked | Negative size, overflow, or OOM | Streaming + quotas |
| Using `STORED` without setting size/CRC | `ZipException` when writing | Precompute metadata |
| Setting `compressedSize` equal to `size` for DEFLATED | Can fail since compressed length differs | Let the writer compute or supply accurate metadata |
| Writing entry names with `File.separator` | Non-portable ZIP | Use `/` |
| Treating `ZipEntry.getName()` as a safe path | Zip Slip, writing outside directory | Normalize + root check + anti-symlink |
| Extracting without limits | ZIP bomb and disk exhaustion | Per-entry/total quotas and timeouts |
| Using `available()` to tell if an entry ended | Wrong semantics | Loop `read` until `-1` |
| Reading text with the default charset | Corrupted Unicode characters | Explicit charset, e.g. UTF-8 |
| Treating CRC as authentication | Does not prevent intentional tampering | Signatures/MAC when needed |
| Thinking ZIP encrypts by default | Contents can be read openly | Separate encryption or authenticated solution |
| Ignoring errors while reading/closing entries | May accept corrupted files | Propagate errors, clean up partial files |
| Keeping a `ByteArrayOutputStream` for every large entry | Heap bloats | Process in blocks/streams |
| Duplicate names in the archive | Extraction overwrites or fails inconsistently | Define a duplicate policy upfront |

## 16. Exercises and Answers

**Exercise 1.** A ZIP has two entries. After `zin.read()` returns `-1`, is the entire ZIP finished?

**Answer:** No; that is only the end of the **current entry's** content. You must call `zin.getNextEntry()` to advance to the next entry; `null` signals the end of all entries.

**Exercise 2.** `ZipEntry.getSize()` returns `-1`. Is the archive definitely corrupted?

**Answer:** No. A sequential reader may not know the size from the local file header; count decompressed bytes while reading to the end of the entry.

**Exercise 3.** Why must `ZipOutputStream` with `STORED` know the CRC-32 before writing?

**Answer:** Per the Java ZIP writer contract, a `STORED` entry must have size, compressed size, and CRC determined before `putNextEntry()`.

**Exercise 4.** Should you take `entry.getName()` and write straight to `outputDir.resolve(name)`?

**Answer:** No. The name could contain `..`, an absolute path, or exploit symlinks; extract into a safe root, normalize/validate, and combine with symlink protections.

**Exercise 5.** A ZIP has an entry that decompresses to 5 GiB even though the archive is only a few MiB. Does using an 8 KiB buffer by itself solve the risk?

**Answer:** No. A small intermediate buffer only limits transient RAM; it can still fill the disk or consume CPU. You need quotas on total bytes, bytes per entry, time, and entry count.

**Exercise 6.** Does `ZipEntry` itself hold the file's contents?

**Answer:** No. It only describes metadata; contents are read/written via the ZIP streams while the entry is active.

**Exercise 7.** Why must you close `ZipOutputStream` or call `finish()` after writing entries?

**Answer:** To finalize the ZIP format structures, especially the central directory at the end of the archive, allowing readers to locate all entries.

**Exercise 8.** A ZIP contains `docs/hello.txt` without a `docs/` entry. Is the ZIP necessarily invalid?

**Answer:** No. A file entry can imply parent directories; when extracting, create parent directories explicitly.

**Exercise 9.** If an entry's data is Vietnamese text, does the `ZipInputStream(..., UTF_8)` constructor automatically decode the content into a `String`?

**Answer:** No. The ZIP stream's charset applies to entry names per metadata rules. The payload remains raw bytes and must be decoded using the agreed charset.

**Exercise 10.** Can CRC-32 be used to verify that a ZIP came from a trusted sender?

**Answer:** No. CRC detects accidental errors, not an authentication mechanism against an attacker.

## 17. Checklist When an Application Creates or Receives ZIPs

1. Choose `ZipOutputStream` for sequential ZIP writing, `ZipInputStream` for sequential reading, and `ZipFile` for random access to an archive on disk.
2. For each entry, follow the exact order `putNextEntry` → `write` → `closeEntry`; finalize the archive with `close` or `finish`.
3. Read using `getNextEntry()` until `null`, and `read()` until `-1` within **each entry**.
4. Choose explicit charsets for entry names and for text content.
5. When using `STORED`, set size, compressed size, and CRC before writing; `DEFLATED` is suitable when metadata is unknown beforehand.
6. Never assume `getSize/getCrc` are always known during stream reading.
7. For untrusted ZIPs, block Zip Slip, absolute paths, duplicate entries, symlinks/TOCTOU, and OS-specific file names.
8. Limit entry count, bytes per entry, total decompressed bytes, path length, processing time, and concurrent archives.
9. Handle `ZipException`, `IOException`, and CRC errors, and clean up incomplete extracted files; never publish results before all policy checks succeed.
10. Do not treat compression as encryption, do not treat CRC as authentication, and do not assume filesystem metadata is fully restored.

## Official Java Documentation

- Java SE 17 — `ZipInputStream`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipInputStream.html
- Java SE 17 — `ZipOutputStream`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipOutputStream.html
- Java SE 17 — `ZipEntry`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipEntry.html
- Java SE 17 — `ZipFile`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipFile.html
- Java SE 17 — `CRC32`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/CRC32.html
- Java SE 17 — `Files`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html
