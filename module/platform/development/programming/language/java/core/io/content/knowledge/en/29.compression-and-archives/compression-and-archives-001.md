# Distinguishing GZIP Compression from ZIP Archives in Java I/O

## 1. Similar Names That Solve Two Different Problems

**GZIP** and **ZIP** both appear in Java via the `java.util.zip` package and can both use the **DEFLATE** compression algorithm, yet they are **not the same format** and **do not share the same data structure**.

- **GZIP (`.gz`):** a format for **compressing a single byte stream**. `GZIPOutputStream` accepts bytes and produces a GZIP stream; `GZIPInputStream` reads a GZIP stream and returns the uncompressed bytes. It does not build a list of files/directories by entry.
- **ZIP (`.zip`):** an **archive/container** format that can hold multiple **entries** — file names, relative paths, metadata, and data — inside a single ZIP file. `ZipOutputStream` creates entries; `ZipInputStream` traverses entries sequentially; `ZipFile` looks up and reads entries from an archive file.

In short: **GZIP compresses the contents of a stream; ZIP packages multiple named items and can compress each item individually.**

Usage example:

~~~text
report.txt
   |
   +-- GZIP --> report.txt.gz
                 (a single stream containing compressed report.txt data)

docs/a.txt ----+
docs/b.txt ----+-- ZIP --> docs.zip
images/x.png --+             |
                             +-- docs/a.txt
                             +-- docs/b.txt
                             +-- images/x.png
~~~

The name `report.txt.gz` is an external naming convention; the `GZIPOutputStream` API itself **does not create a `report.txt` file entry that can be traversed like a ZIP**. A GZIP stream does not inherently store a directory tree that an extractor uses to recreate multiple files.

## 2. Overview Comparison Table

| Criterion | GZIP | ZIP |
|---|---|---|
| Purpose | Compressing a **data stream** | **Packaging files/directories** into an archive, usually combined with compression |
| Multiple individually named files? | Not in the `GZIPInputStream` model | Yes, each item is a `ZipEntry` |
| Preserving directory structure | Not directly | Yes, through entry names/paths and corresponding metadata |
| Java types | `GZIPInputStream`, `GZIPOutputStream` | `ZipInputStream`, `ZipOutputStream`, `ZipFile`, `ZipEntry` |
| Compression | Usually uses DEFLATE inside a GZIP wrapper | Entries can be `DEFLATED` or `STORED`; the ZIP format has other methods |
| Sequential reading | Naturally reads a single stream | `ZipInputStream` reads each entry sequentially |
| Lookup entry by name | No entry/file index | `ZipFile.getEntry(name)` |
| Per-file metadata | No `ZipEntry` | Name, size, CRC-32, timestamp, comment, extra fields per entry |
| Ending structure | CRC-32 trailer and content size (modulo 2³²) | Archive central directory / end-of-central-directory |
| Common extensions | `.gz`, `.tgz`, `.tar.gz` | `.zip`, `.jar` |
| Best suited for | Compressing logs, response bodies, a single large stream | Packaging multiple documents, backups/archives, downloadable folders |
| Data security | Not encrypted/authenticated by default | Not encrypted/authenticated by default |

**Note:** some applications may concatenate multiple consecutive **GZIP members** into a single valid GZIP stream. That **does not turn GZIP into a ZIP archive**: there is still no entry directory, and no API to look up files by name like `ZipFile`.

## 3. Format Structure: GZIP Wrapper and ZIP Archive

### 3.1. GZIP

A typical GZIP member is structured as:

~~~text
+--------------------+
| GZIP header        |  magic bytes 1F 8B, flags, method, ...
+--------------------+
| Compressed payload |  DEFLATE-compressed bytes
+--------------------+
| GZIP trailer       |  CRC-32 + ISIZE (size mod 2^32)
+--------------------+
~~~

The header/trailer forms a **GZIP wrapper** around the compressed content, helping the reader recognize the format and verify the checksum. GZIP does not have a list of files named `docs/a.txt`, `docs/b.txt` like a ZIP central directory. The GZIP format can include some optional header fields, but they should not be equated with ZIP's entry system.

**CRC-32 is an accidental error-detection mechanism, not cryptographic authentication**. If a file is intentionally modified, the checksum provides no tamper-resistance guarantee.

### 3.2. ZIP

A ZIP archive typically contains multiple entry records and a **central directory** near the end of the archive:

~~~text
+------------------------------+
| Local header: docs/a.txt     |
| Compressed data: a.txt       |
+------------------------------+
| Local header: docs/b.txt     |
| Compressed data: b.txt       |
+------------------------------+
| ...                          |
+------------------------------+
| Central directory            |
|   - entry names and metadata |
|   - offsets to local records |
+------------------------------+
| End-of-central-directory     |
+------------------------------+
~~~

Each entry can be **DEFLATED** or **STORED** (uncompressed), depending on configuration. A `ZipOutputStream` that has not been properly `finish()`ed/`close()`d may not have finished writing the directory, making the archive unusable even though some entry data has already been output.

### 3.3. Magic Bytes for Preliminary Identification

- GZIP typically starts with `1F 8B` (hex).
- A ZIP local file header typically starts with `50 4B 03 04`, representing `PK` and the rest of the signature. An empty ZIP file may start with a different end-of-central-directory signature.

**Do not use magic bytes as complete validation.** They are only a preliminary format check; the content may still be corrupted, incomplete, forged, or incompatible.

## 4. Corresponding Java APIs: Same Package, Different Semantics

The `java.util.zip` package contains the following classes:

| API | Role |
|---|---|
| `GZIPOutputStream` | Compresses written bytes into a GZIP stream |
| `GZIPInputStream` | Decompresses a GZIP input stream into bytes |
| `ZipOutputStream` | Writes a ZIP archive with one or more `ZipEntry` instances |
| `ZipInputStream` | Reads `ZipEntry` items sequentially from a ZIP stream |
| `ZipFile` | Opens a ZIP file to list/find entries and open streams to read them |
| `ZipEntry` | Represents a named entry with metadata in a ZIP archive |
| `Deflater`/`Inflater` | Compresses/decompresses at a lower algorithmic layer |
| `CRC32` | Computes CRC-32 checksums |

Do not use `GZIPInputStream` to directly decompress `.zip` files, and do not use `ZipInputStream` to directly read `.gz` files. Although both use DEFLATE in many cases, **the wrapper/container formats are different**.

### ZIP Entries May Be Uncompressed

As of Java 17, `ZipEntry` defines `DEFLATED` and `STORED`:

~~~java
ZipEntry entry = new ZipEntry("image.png");
entry.setMethod(ZipEntry.STORED);
~~~

This is **illustrative code, not standalone**. With `STORED`, `ZipOutputStream` requires setting the exact size, compressed size, and CRC before calling `putNextEntry`; merely calling `setMethod(STORED)` as shown above and writing without metadata will cause an error. `DEFLATED` is the default method of `ZipOutputStream` and normally computes the required metadata automatically after writing the entry.

Therefore, **ZIP does not mean every entry is compressed**; an archive can contain entries stored as raw bytes, which makes sense for already-compressed images or videos.

## 5. GZIP in Java: Compressing and Decompressing a Single Content Stream

A typical sequence of operations:

~~~java
// Create .gz from a byte stream:
try (InputStream in = Files.newInputStream(source);
     OutputStream out = new GZIPOutputStream(
             Files.newOutputStream(gzipPath))) {
    in.transferTo(out);
}

// Decompress .gz back to a byte stream:
try (InputStream in = new GZIPInputStream(
             Files.newInputStream(gzipPath));
     OutputStream out = Files.newOutputStream(restoredPath)) {
    in.transferTo(out);
}
~~~

This is **illustrative code inside a method**, assuming `Path source`, `Path gzipPath`, `Path restoredPath` already exist along with appropriate imports. It processes **the contents of a single file**, without traversing a directory tree or automatically creating child files by name from the compressed stream.

**Why is `try-with-resources` needed?** `GZIPOutputStream` must write all compressed data and the trailer upon `finish()`/`close()`; closing the stream also releases resources of the underlying stream. Reading `gzipPath` before the writer finishes/closes can result in an incomplete stream.

### `finish()` vs. `flush()`

`GZIPOutputStream.finish()` completes the GZIP stream without **closing the underlying OutputStream**. `close()` closes both the filter stream and the underlying stream. `flush()` does not replace `finish()`: depending on the `syncFlush` setting, flushing may only push the output buffer or trigger `SYNC_FLUSH`, without necessarily writing the member-terminating trailer.

In a normal pipeline, **closing `GZIPOutputStream`** at the end of the scope is the simplest choice; only call `finish()` manually when you want to finalize the GZIP stream while keeping the underlying stream open for other tasks.

### Why Can a `.tar.gz` File Contain Multiple Files?

**TAR is an archive; GZIP is compression.** The typical processing flow is:

~~~text
docs/a.txt + docs/b.txt + dirs
        |
        v
TAR: packages multiple files/metadata into one byte stream
        |
        v
GZIP: compresses the TAR byte stream
        |
        v
backup.tar.gz
~~~

When extracting `.tar.gz`, you must **GZIP-decompress first**, then use a **TAR reader** to extract each file. The Java standard library (`java.util.zip`) provides GZIP and ZIP, but **does not provide a dedicated TAR parser/writer**. An external library or appropriate TAR tool is required to read TAR entries. Naming a file `.tar.gz` does not turn `GZIPInputStream` into a TAR parser.

## 6. ZIP in Java: Creating Multiple Entries

To create a ZIP using `ZipOutputStream`, each file must be placed into a `ZipEntry`:

~~~java
try (ZipOutputStream zip = new ZipOutputStream(
        Files.newOutputStream(zipPath), StandardCharsets.UTF_8)) {

    zip.putNextEntry(new ZipEntry("docs/a.txt"));
    Files.copy(pathA, zip);
    zip.closeEntry();

    zip.putNextEntry(new ZipEntry("docs/b.txt"));
    Files.copy(pathB, zip);
    zip.closeEntry();
}
~~~

This is an **illustrative snippet** with valid `Path zipPath`, `pathA`, `pathB` and corresponding imports. The names `docs/a.txt`/`docs/b.txt` inside the ZIP are **entry paths**, and do not require the source files to reside in a directory tree of the same names.

The order of steps:

1. `putNextEntry(entry)` opens a new entry.
2. `write(...)` or `Files.copy(path, zip)` writes the bytes of that entry.
3. `closeEntry()` finishes the current entry and prepares for the next entry.
4. `close()`/`finish()` finalizes the archive, including the directory metadata.

For directory entries, the common convention is to append a trailing `/` to the name, e.g. `docs/`, and write no data as you would for a regular file. Entry names should use `/` separators and **relative** paths for portability.

### Entry Metadata

`ZipEntry` supports `getName()`, `isDirectory()`, `getSize()`, `getCompressedSize()`, `getCrc()`, `getTime()`, `getComment()`, and their corresponding setters. Some values may be **-1** or `null` if unknown. When reading sequentially with `ZipInputStream`, do not assume all metadata is available from the local header at the time of `getNextEntry()`.

Do not infer that a file's contents or path are safe solely from `ZipEntry.getName()`. The entry name is **data supplied by the archive** and must be validated before being used as a file path.

## 7. ZIP: `ZipInputStream` vs. `ZipFile`

Both are used to read ZIP archives, but they have different capabilities:

### 7.1. ZipInputStream — Sequential Reading

~~~java
try (ZipInputStream in = new ZipInputStream(
        Files.newInputStream(zipPath), StandardCharsets.UTF_8)) {

    ZipEntry entry;
    while ((entry = in.getNextEntry()) != null) {
        System.out.println("entry=" + entry.getName());

        // Read bytes from the current entry until entry EOF.
        byte[] bytes = in.readAllBytes();
        // Only use readAllBytes for small, trusted entries.
        in.closeEntry();
    }
}
~~~

This illustrative snippet assumes `Path zipPath` and appropriate imports. `getNextEntry()` advances to the next entry and returns `null` when none remain. `read(...) == -1` indicates **end of data for the entry currently being read**, not necessarily the end of the entire archive. Do not use `available()` to determine the remaining size: with `ZipInputStream`, it usually returns 1 before entry EOF and 0 after EOF, **not the number of unread bytes**.

It is suitable when the input is an **InputStream**, such as a ZIP uploaded over a network, or when you want to iterate through every entry in order. It is not a random-access API for looking up an entry by name from the archive's central directory.

### 7.2. ZipFile — Lookup and Opening Streams for Entries

~~~java
try (ZipFile zip = new ZipFile(zipPath.toFile(),
                              StandardCharsets.UTF_8)) {
    ZipEntry entry = zip.getEntry("docs/a.txt");
    if (entry != null) {
        try (InputStream in = zip.getInputStream(entry)) {
            // Read only the contents of docs/a.txt.
        }
    }
}
~~~

This illustrative snippet assumes `Path zipPath`. `ZipFile` reads archive metadata to locate entries, supports `getEntry(name)`, `entries()`, or `stream()`, and opens an `InputStream` for each selected entry. It is typically appropriate when you need to **pick files by name** or inspect the list of entries in an archive on disk.

Closing `ZipFile` also closes all `InputStream` instances obtained via `getInputStream(entry)`. Do not retain those streams for reading after `ZipFile` has been closed. In practice, `ZipInputStream` walks local entry headers whereas `ZipFile` uses the central directory: the two approaches can expose **different metadata on malformed/crafted archives**, which requires care when inspecting untrusted archives.

### Which API to Choose?

| Input and Requirement | Choice |
|---|---|
| A single GZIP byte stream | `GZIPInputStream` |
| Writing a GZIP stream | `GZIPOutputStream` |
| Receiving a ZIP from a stream/upload and iterating entries sequentially | `ZipInputStream` |
| Creating a multi-file ZIP | `ZipOutputStream` |
| Reading a ZIP file on disk and looking up entries by name | `ZipFile` |
| Viewing a ZIP as a file system to traverse `Path` | ZIP file system provider if `jdk.zipfs` is available in the environment |

Do not use `ZipFile` directly on a plain `InputStream`; it takes a file name/`File` (and related overloads), so network inputs usually require streaming parsing or buffering to a temporary file depending on requirements.

## 8. Complete Java 17+ Demo: Both Formats Side by Side

To make it easy to run on any machine with Java 17, the example works **in memory**, without creating files or directories on disk. It creates and decompresses a GZIP stream from a payload, then creates a ZIP containing two named file entries and reads them back.

**File name: `GzipZipDemo.java`**

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.zip.GZIPInputStream;
import java.util.zip.GZIPOutputStream;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;
import java.util.zip.ZipOutputStream;

public class GzipZipDemo {
    public static void main(String[] args) throws Exception {
        byte[] payload =
                "Xin chao NIO".getBytes(StandardCharsets.UTF_8);

        ByteArrayOutputStream gzipData = new ByteArrayOutputStream();
        try (GZIPOutputStream gzip = new GZIPOutputStream(gzipData)) {
            gzip.write(payload);
        }

        try (GZIPInputStream gzip = new GZIPInputStream(
                new ByteArrayInputStream(gzipData.toByteArray()))) {
            System.out.println("gzip=" +
                    new String(gzip.readAllBytes(), StandardCharsets.UTF_8));
        }

        System.out.printf("gzip magic=%02X %02X%n",
                gzipData.toByteArray()[0] & 0xFF,
                gzipData.toByteArray()[1] & 0xFF);

        ByteArrayOutputStream zipData = new ByteArrayOutputStream();
        try (ZipOutputStream zip =
                new ZipOutputStream(zipData, StandardCharsets.UTF_8)) {

            zip.putNextEntry(new ZipEntry("docs/a.txt"));
            zip.write("Alpha".getBytes(StandardCharsets.UTF_8));
            zip.closeEntry();

            zip.putNextEntry(new ZipEntry("docs/b.txt"));
            zip.write("Beta".getBytes(StandardCharsets.UTF_8));
            zip.closeEntry();
        }

        try (ZipInputStream zip = new ZipInputStream(
                new ByteArrayInputStream(zipData.toByteArray()),
                StandardCharsets.UTF_8)) {
            ZipEntry entry;
            while ((entry = zip.getNextEntry()) != null) {
                String content = new String(zip.readAllBytes(),
                        StandardCharsets.UTF_8);
                System.out.println(entry.getName() + "=" + content);
                zip.closeEntry();
            }
        }

        byte[] zipBytes = zipData.toByteArray();
        System.out.printf("zip magic=%02X %02X %02X %02X%n",
                zipBytes[0] & 0xFF, zipBytes[1] & 0xFF,
                zipBytes[2] & 0xFF, zipBytes[3] & 0xFF);
    }
}
~~~

Compile and run:

~~~bash
javac GzipZipDemo.java
java GzipZipDemo
~~~

**Stdout verified with the JDK:**

~~~text
gzip=Xin chao NIO
gzip magic=1F 8B
docs/a.txt=Alpha
docs/b.txt=Beta
zip magic=50 4B 03 04
~~~

Explanation:

1. `GZIPOutputStream` only accepts `payload` — a single content stream; `GZIPInputStream` returns the bytes of `Xin chao NIO`. There is no `ZipEntry` or file name inside the GZIP example data.
2. `ZipOutputStream` uses `putNextEntry` to create **two separately named files** in the archive; each entry has its own data and boundaries.
3. `ZipInputStream.getNextEntry()` returns `docs/a.txt` and `docs/b.txt` in sequence. `readAllBytes()` is safe here for the demo because **we created very small data ourselves**; do not apply this directly to untrusted uploads.
4. `closeEntry()` completes reading/writing the entry at the current position. `try-with-resources` finalizes the GZIP/ZIP stream and closes resources.
5. Different magic bytes (`1F 8B` vs `50 4B 03 04`) show that the two cannot be treated as the same format merely because both use DEFLATE.

## 9. Which Format Compresses Better?

There is no absolute answer. Both GZIP and ZIP commonly use DEFLATE, but their **compression units and metadata** differ:

- GZIP compresses **one continuous stream**; if multiple files are combined using TAR and then GZIPped, the compressor can exploit data repetition across adjacent parts of the stream (within the algorithm's window limit).
- ZIP typically compresses **each entry separately**, making it easy to browse or extract individual entries, but it cannot automatically reuse data history from one entry for another entry.
- ZIP must store local headers, file names, and a central directory, so an archive with very many small files can incur noticeable overhead.
- GZIP also has a header/trailer; for very small or already-compressed data (PNG, JPEG, MP4…), the compressed size may equal or **exceed** the original size.
- Results depend on the compression level, data type, size, number of files, and per-file compressibility. Comparisons are only meaningful across **the same dataset and the same functional requirements**.

Do not compare a `data.gz` compressing one file against a multi-file `bundle.zip` and conclude which algorithm is better based solely on size.

### Choosing a Format by Use Case

**Choose GZIP** if the input is already **a single stream**: log streams, a single text file, HTTP response content coding `gzip`, or a pre-packaged TAR backup. With HTTP `Content-Encoding: gzip`, the response body is compressed as a single HTTP data stream; the encoding header does not mean the body becomes a ZIP archive containing files.

**Choose ZIP** if users need to download **multiple files**, preserve names/paths and extract individual files, or if an API needs to look up an entry by name. `.jar` files are also based on the ZIP format, adding the `META-INF` structure and Java archive semantics.

When you need **streaming processing** of multiple entries directly from the network, `ZipInputStream` can be convenient; when you need **random lookup** on a stored file, `ZipFile` is usually better suited.

## 10. Charset and Entry Names

`ZipEntry` names are **a separate concern** from file content bytes:

- `new ZipOutputStream(out, StandardCharsets.UTF_8)` encodes entry names as UTF-8 when appropriate.
- `new ZipInputStream(in, StandardCharsets.UTF_8)`/`new ZipFile(file, StandardCharsets.UTF_8)` decodes entry names using the chosen charset, though if the ZIP **language encoding flag** indicates UTF-8, the Javadoc specifies using UTF-8 regardless of the provided charset.
- The contents of `docs/a.txt` may be UTF-8, UTF-16, or binary data, **not determined** by the charset passed to `ZipInputStream`.

For example, the entry name `"tiếng-việt.txt"` can be encoded in UTF-8, while the content bytes must be decoded according to that file's own charset.

Do not assume `ZipEntry.getName()` is a safe path string simply because it decoded cleanly as Unicode. You must still validate the path before extracting to the filesystem.

## 11. Safety When Extracting ZIP/GZIP from Untrusted Sources

### 11.1. Zip Slip — Path Traversal

An archive may intentionally contain an entry like `../../outside.txt` or an absolute name like `/tmp/target`. Directly calling `outputRoot.resolve(entry.getName())` without validation allows the program to write **outside the intended directory**.

Basic check:

~~~java
Path root = outputDir.toAbsolutePath().normalize();
Path target = root.resolve(entry.getName()).normalize();

if (!target.startsWith(root) || target.equals(root)) {
    throw new IOException("Unsafe ZIP entry: " + entry.getName());
}
~~~

This is an **illustrative snippet**; `outputDir` and `ZipEntry entry` must exist. This check is a **basic layer of defense**, not a complete Zip Slip solution across every OS. You should disallow absolute entry paths/drive prefixes by policy, check symlinks/hardlinks/path components in the target directory, avoid file creation race conditions, and use safe filesystem mechanisms. For untrusted archives, extract into a dedicated directory controlled by the application with anti-symlink policies and write limits.

### 11.2. Zip Bombs / GZIP Bombs

A small compressed stream can expand into massive amounts of data. A ZIP archive can also contain **very many entries**, exhausting CPU, RAM, or storage.

You should limit:

1. **Total decompressed bytes** for the entire archive.
2. **Maximum decompressed bytes per entry**.
3. **Number of entries**, name/path length, and directory depth.
4. **Processing time/deadline**, disk quota, and memory.
5. Where appropriate, **anomalous compression ratios**, though do not rely solely on ratios or declared metadata.
6. The **actual byte count read during streaming**, because `ZipEntry.getSize()` may be `-1` or untrustworthy declared metadata.

Calling `readAllBytes()` on an unbounded compressed upload can exhaust the heap. Instead, read in fixed chunks with `read(byte[])`, count bytes, and then write to output. This principle holds for both `GZIPInputStream` and `ZipInputStream`.

### 11.3. CRC-32 Does Not Authenticate the Source

CRC-32 in GZIP/ZIP detects transmission/storage data corruption; it **does not prevent intentional tampering**. When you need assurance that a file comes from a trusted source and has not been intentionally altered, use digital signatures/MACs or a cryptographic checksum verified through another trusted channel. ZIP encryption does not mean `java.util.zip` provides built-in password APIs to decrypt every password-protected ZIP; the JDK 17 standard ZIP API is not a general-purpose ZIP encryption library.

### 11.4. Proper Resource Reading/Writing

- Use `try-with-resources` to close streams and `ZipFile`.
- If creating a ZIP/GZIP and reading the output immediately, complete `close()`/`finish()` first.
- Avoid writing an archive to the same path as a source file you are currently reading; this can corrupt data.
- With ZIP streaming, close entries with `closeEntry()` at the proper time.
- For ZIP entries with missing metadata, **do not blindly trust** the size to allocate large arrays.

## 12. Common Mistakes

1. **Assuming ZIP = GZIP differing only by extension.** Wrong: the formats and structures are different.
2. **Using `GZIPInputStream` to read `.zip`.** Wrong: a GZIP wrapper is not a ZIP archive.
3. **Using `ZipInputStream` to read `.gz`.** Wrong: a GZIP stream does not have ZIP local entries.
4. **Assuming every ZIP entry is compressed.** Wrong: `STORED` saves uncompressed contents.
5. **Assuming GZIP natively preserves multiple files and directory names.** Wrong: GZIP compresses a stream; handling multiple files usually uses TAR first.
6. **Confusing `.tar.gz` with ZIP.** Wrong: TAR packages files, and GZIP compresses the TAR stream.
7. **Forgetting `putNextEntry()` before writing bytes to a ZIP.** Wrong entry structure ordering.
8. **Forgetting to finish/close ZIP output and trying to read it immediately.** The archive may lack its central directory.
9. **Assuming `ZipInputStream.read() == -1` means end of the entire archive.** Wrong: it usually indicates EOF of the current entry.
10. **Using `available()` on `ZipInputStream` to count remaining bytes.** Wrong: it is not a remaining byte count.
11. **Assuming the entry name charset is the file content charset.** Wrong: name metadata and payload are separate concerns.
12. **Extracting `entry.getName()` without validation.** Prone to Zip Slip/path traversal.
13. **Using `readAllBytes()` on untrusted archives.** Prone to OOM/zip bombs.
14. **Treating CRC-32 as security or a digital signature.** Wrong: a checksum does not guarantee authenticity.
15. **Assuming `ZipFile` accepts an arbitrary `InputStream`.** Wrong: `ZipFile` reads a ZIP file; use `ZipInputStream` for an `InputStream`.
16. **Assuming already-compressed files will always get smaller when gzipped/zipped.** Wrong: headers and overhead can increase size.

## 13. Self-Check Knowledge Questions

**Question 1.** You need to compress a single log file for HTTP transmission without keeping multiple files. What should you choose?

**Answer:** GZIP is the natural choice for a stream; use `GZIPOutputStream` or HTTP `Content-Encoding: gzip` according to the appropriate protocol.

**Question 2.** You need to send a user a folder containing 30 files, preserving names and structure upon extraction. What should you choose?

**Answer:** A ZIP archive with `ZipOutputStream` creating a `ZipEntry` for each file/directory (or TAR then GZIP if appropriate for the ecosystem); do not use GZIP directly to write 30 individually named files.

**Question 3.** Why does `.tar.gz` contain multiple files even though GZIP compresses a single stream?

**Answer:** TAR packages multiple files into a single stream; GZIP compresses that TAR stream.

**Question 4.** Given a ZIP file on disk, you want to read only the `config/settings.json` entry. What should you use?

**Answer:** `ZipFile.getEntry("config/settings.json")`, followed by `getInputStream(entry)`. For streaming ZIP data, use `ZipInputStream` to iterate through entries.

**Question 5.** Can a ZIP containing an entry `../../secret.txt` be written directly into the target directory?

**Answer:** No. You must validate paths, protect against traversal/symlinks, and enforce resource limits before extracting.

**Question 6.** A ZIP is being created with `ZipOutputStream`; all entries have been written, but it has not been closed/finished yet. Should the ZIP file be considered complete?

**Answer:** No. The central directory and archive-ending metadata may not have been written completely.

### Official Java 17 Documentation

- [java.util.zip package](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/package-summary.html)
- [GZIPInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/GZIPInputStream.html)
- [GZIPOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/GZIPOutputStream.html)
- [ZipInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipInputStream.html)
- [ZipOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipOutputStream.html)
- [ZipFile](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipFile.html)
- [ZipEntry](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipEntry.html)
