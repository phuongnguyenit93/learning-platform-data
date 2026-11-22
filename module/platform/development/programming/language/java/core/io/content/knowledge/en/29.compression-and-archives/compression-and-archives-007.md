# ZIP Archive: Entry Name Charsets and Metadata in Java

In Java Core I/O, `java.util.zip.ZipFile`, `ZipInputStream`, `ZipOutputStream`, and `ZipEntry` let you read, write, and inspect ZIP files. An archive does not just hold **content bytes**: each entry also carries **path names, comments, timestamps, sizes, compression methods, CRC, and extra fields**. Designing the entry name charset poorly or interpreting metadata carelessly can cause a ZIP file to display garbled Vietnamese names, lose timestamps, or introduce extraction errors and security risks.

**Key takeaway:** The charset used to encode **entry names/comments** and the charset of the **file content inside an entry** are two independent concerns. For new archives, consistently choose **UTF-8**. For legacy ZIPs, determine the actual encoding and check the UTF-8 flag bit inside the ZIP before reading with another charset. Metadata is **conditional information**, not proof that content is safe, intact, or authenticated.

## 1. Archive, Entry, and Content Are Three Separate Layers

A ZIP consists of multiple entries and structures such as local file headers, compressed data, the central directory, and archive-ending records. Each entry represents a file or a directory path. For example:

```text
documents.zip
├── tài-liệu/                     # May be a directory entry, if written
│   └── đề-cương.txt               # ZIP entry name: "tài-liệu/đề-cương.txt"
├── images/
│   └── logo.png
└── README.md

Each file entry involves these concepts:
  name                internal archive name/path
  comment             optional entry note
  compressed data     file bytes after compression
  CRC-32              checksum of original bytes
  size                uncompressed size
  compressedSize      compressed data size
  method              e.g., STORED or DEFLATED
  timestamps/extra    metadata and extended fields
```

Entry names follow the ZIP convention using `/` as the path separator. Never equate them with a `Path` of the current OS: on Windows, ZIP entries normally still use `/`; an archive may also contain strange or malicious names that cannot map directly to valid files.

A directory entry typically has a name **ending with `/`**, such as `"documents/"`, and `ZipEntry.isDirectory()` checks this convention. A ZIP might contain only a file entry `"documents/report.txt"` without a **separate `"documents/"` directory entry**. During extraction, the application may need to create parent directories.

## 2. Entry Name Charset Is Not the Payload Charset

Clearly distinguish four concepts:

| Component | How Is It Encoded or Interpreted? | Typical Java API |
| --- | --- | --- |
| Entry name | A character string converted into bytes in the ZIP header/central directory. | `new ZipOutputStream(out, charset)`; `new ZipFile(file, charset)` |
| Entry comment | String metadata; encoding must match the reader. | `ZipEntry.setComment()` / `getComment()` |
| Archive-wide comment | Note stored in the end-of-central-directory record. | `ZipOutputStream.setComment()`; `ZipFile.getComment()` |
| File content | Byte sequence depending on data type; ZIP does not force UTF-8 text. | `out.write(bytes)`; `ZipFile.getInputStream(entry)` |

For example, a ZIP may store the name `"tài-liệu/đề-cương.txt"` in UTF-8. Inside could be a JPEG image, a PDF file, or a `.txt` whose content uses UTF-8, UTF-16, or a legacy charset. The `Charset` parameter of `ZipOutputStream` only governs encoding **names and comments in the ZIP structure**; it does not automatically convert content bytes to UTF-8.

Correct pattern for a UTF-8 text file:

```java
byte[] payload = "Xin chào".getBytes(StandardCharsets.UTF_8);
out.putNextEntry(new ZipEntry("tài-liệu/chào.txt"));
out.write(payload);
out.closeEntry();
```

This snippet assumes `out` is a `ZipOutputStream` opened with UTF-8, with imports for `StandardCharsets` and `ZipEntry`. When reading, decode the **payload** with `new String(bytes, StandardCharsets.UTF_8)` or use `InputStreamReader(in, UTF_8)` when you know the file is genuinely UTF-8 text.

## 3. The UTF-8 Flag (Bit 11) and Legacy Charsets in ZIP

In the ZIP format, **general purpose bit flag bit 11** is also called the *language encoding flag* or *EFS flag*. When set, the corresponding entry name and comment are interpreted as **UTF-8**. Compliant readers must honor this bit rather than forcing UTF-8 names into CP437 or another charset.

When this bit is **not set**, names/comments may be encoded in a legacy charset. Classic ZIP is commonly associated with **IBM437 (CP437)**; in practice, names written by older tools using Windows code pages or local encodings also appear. Therefore:

- For ZIPs created by **new** applications, prefer `StandardCharsets.UTF_8` and a consistent packaging tool.
- For **legacy** ZIPs, you need to know the charset the ZIP producer actually used; seeing garbled accents alone is not enough to identify the exact charset.
- If a ZIP has the **UTF-8 flag**, a legacy charset passed to name-reading constructors must not be used to reinterpret names marked as UTF-8. Follow the ZIP bit flag.
- If a ZIP lacks the flag and names were written in another code page, supply the matching `Charset` to decode entry names.
- Some ZIP extensions include the Unicode Path Extra Field (`0x7075`) and Unicode Comment Extra Field (`0x6375`), usually paired with a CRC tying them to the original name/comment. **Do not assume** every ZIP library handles these extra fields identically.

**Important interoperability note:** The `java.util.zip` API does not promise automatic heuristic detection of every legacy charset. If you need to support ZIP files from multiple sources, define a configurable charset selection policy, prioritize the bit flag and source contract, test against real fixtures, and handle decoding errors rather than silently corrupting filenames.

## 4. Choosing the Right Charset in Java

Java 17+ provides helpful constructors:

```java
// Modern default: UTF-8 for ZIP names.
ZipOutputStream out1 = new ZipOutputStream(outputStream);
ZipInputStream in1 = new ZipInputStream(inputStream);
ZipFile zip1 = new ZipFile(file);

// Explicitly specify UTF-8 (suitable for new archives).
ZipOutputStream out2 = new ZipOutputStream(
        outputStream2, StandardCharsets.UTF_8);
ZipFile zip2 = new ZipFile(file2, StandardCharsets.UTF_8);

// Read/write legacy ZIP with a compatible charset.
Charset cp437 = Charset.forName("IBM437");
ZipInputStream legacyStream = new ZipInputStream(inputStream3, cp437);
ZipFile legacyZip = new ZipFile(legacyFile, cp437);
```

**These are separate snippets**, not one standalone runnable block: stream/file variables must already be initialized, and each object must follow proper lifecycle closing via `try-with-resources`. When picking a charset other than UTF-8, make sure it can encode all intended names and comments. For instance, `IBM437` can encode `"café.txt"`, but cannot encode a full modern Vietnamese filename.

API notes:

| Class | Function | Points to Note |
| --- | --- | --- |
| `ZipOutputStream(OutputStream, Charset)` | Creates a ZIP, encoding names/comments per spec and chosen charset. | Good for controlling new archives; unencodable characters or invalid settings can cause exceptions. |
| `ZipInputStream(InputStream, Charset)` | Reads entries sequentially, using the appropriate charset for names. | Sequential access via local file headers; does not provide full central-directory metadata/lookup like ZipFile. |
| `ZipFile(File, Charset)` | Opens the central directory to look up entries, comments, and metadata. | Decodes names with the right charset; must be closed to release resources. |
| `ZipEntry(String)` | Sets the logical name of an entry. | Does not take a `Charset`; name encoding happens in ZipOutputStream. |

In Java 17, overloads of the standard Java library that omit a charset use UTF-8 per the JDK contract. Avoid assuming an archive extracted by **another** tool will always default to UTF-8 if a legacy file lacks the flag.

## 5. Common Metadata on ZipEntry

`ZipEntry` exposes several fields:

| API | Meaning | Note |
| --- | --- | --- |
| `getName()` | Decoded entry name. | May be a relative path, absolute path, or traversal string supplied by an untrusted archive. |
| `getComment()` / `setComment()` | Optional entry note. | May be null; do not treat as authenticated data. |
| `getMethod()` / `setMethod()` | ZIP method; JDK commonly supports `STORED` and `DEFLATED`. | Not all compression methods from external tools are supported by the JDK. |
| `getSize()` / `setSize()` | Uncompressed size, bytes. | May return `-1` if unknown. |
| `getCompressedSize()` / `setCompressedSize()` | Compressed byte count. | May return `-1` if unknown; depends on method and write/read stage. |
| `getCrc()` / `setCrc()` | CRC-32 of uncompressed content. | May return `-1` if unknown; CRC checks accidental errors, **not** cryptographic signatures. |
| `getTime()` / `setTime(long)` | Modification time as a millisecond timestamp. | Value may be missing; range/precision depends on ZIP metadata. |
| `getLastModifiedTime()` | `FileTime` of modification if present. | May be null; precision and representation depend on extra fields. |
| `getLastAccessTime()` / `getCreationTime()` | Access/creation time if provided by the archive. | May be null; do not interpret missing as `now()`. |
| `getExtra()` / `setExtra(byte[])` | Extra fields in binary ZIP format. | May be null; parse by ID/length with strict bounds checking. |
| `isDirectory()` | Checks whether the name ends with `/`. | Does not guarantee an external file outside the archive is actually a safe directory. |

Metadata fields may not be populated completely in every ZIP. In ZIPs created by external tools, an entry might lack comments, omit creation time, or store timestamps at a different precision than expected. When copying/repacking ZIPs, avoid accidentally resetting every timestamp to the current time if your application must preserve source timestamps.

### Archive-Wide Metadata

`ZipOutputStream.setComment(String)` sets the **archive comment**, whereas `ZipEntry.setComment(String)` sets an **entry comment**. `ZipFile.getComment()` reads the archive comment. These two are separate structures and must not be confused with the payload of a `README.txt` file.

ZIP comment limits are typically measured **in encoded bytes**, up to 65,535 bytes for the respective comment field. A Java `String` of 30,000 Unicode characters is not guaranteed to fit within that byte limit when UTF-8 encoded. For externally supplied archives, comments may be null or contain characters outside the charset.

## 6. Timestamps and Precision

Classic ZIP uses MS-DOS date/time fields with known limitations: second resolution can be **2 seconds**, the date range is limited, and timezone information is not always complete. Extra fields are commonly used to store timestamps with higher precision and clearer semantics; however, different ZIP tools may write or read them differently.

Java allows setting:

```java
ZipEntry entry = new ZipEntry("notes.txt");
entry.setLastModifiedTime(
        FileTime.from(Instant.parse("2024-01-02T03:04:06Z")));
entry.setLastAccessTime(
        FileTime.from(Instant.parse("2024-01-02T03:04:06Z")));
entry.setCreationTime(
        FileTime.from(Instant.parse("2024-01-02T03:04:06Z")));
```

This snippet uses imports `java.util.zip.ZipEntry`, `java.nio.file.attribute.FileTime`, and `java.time.Instant`; the values shown are sample timestamps.

**Distinctions:**

- `setTime(long)` and `setLastModifiedTime(FileTime)` both affect modification time, though serialized representation depends on the API/extra fields and format capabilities.
- Pick a single clear source of truth to avoid accidentally setting two conflicting modification timestamps.
- Creation/access times are not required in every archive; `getCreationTime()`/`getLastAccessTime()` can return null.
- When comparing archives across multiple OSes or timezones, compare via `Instant` and allow for format precision. **Not every ZIP file** is required to preserve nanosecond precision.
- Timestamps inside an archive are not security evidence: a ZIP creator can set them to arbitrary values.

If preserving metadata carries legal or business significance, define a separate manifest schema with source verification and signatures; do not rely solely on ZIP timestamps.

## 7. Complete Java 17+ Example: UTF-8 ZIP and IBM437 ZIP

The example creates **two independent archives**:

1. A UTF-8 ZIP with entry `"tài-liệu/đề-cương.txt"`, comment `"Bản mẫu"`, and a fixed timestamp.
2. A legacy ZIP using `IBM437` with entry `"café.txt"` and an ASCII comment.
3. The payload contents of **both** are UTF-8 encoded, regardless of the entry name charset.
4. Reopen both with `ZipFile(..., charset)` matching how each archive was created; inspect metadata, recompute CRC-32, and print the payload.

Save as **`ZipEntryMetadataDemo.java`**:

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.FileTime;
import java.time.Instant;
import java.util.zip.CRC32;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;
import java.util.zip.ZipOutputStream;

public class ZipEntryMetadataDemo {
    private static final Instant FIXED_TIME =
            Instant.parse("2024-01-02T03:04:06Z");
    private static final byte[] PAYLOAD =
            "Xin chào".getBytes(StandardCharsets.UTF_8);

    private static void writeArchive(
            Path path, Charset nameCharset, String name, String entryComment)
            throws IOException {
        try (ZipOutputStream out = new ZipOutputStream(
                Files.newOutputStream(path), nameCharset)) {
            out.setComment("Archive note");
            ZipEntry entry = new ZipEntry(name);
            entry.setLastModifiedTime(FileTime.from(FIXED_TIME));
            entry.setComment(entryComment);
            out.putNextEntry(entry);
            out.write(PAYLOAD);
            out.closeEntry();
        }
    }

    private static void inspect(Path path, Charset nameCharset, String name)
            throws IOException {
        try (ZipFile zip = new ZipFile(path.toFile(), nameCharset)) {
            ZipEntry entry = zip.getEntry(name);
            if (entry == null) {
                throw new IOException("Missing entry: " + name);
            }
            byte[] bytes;
            try (InputStream in = zip.getInputStream(entry)) {
                bytes = in.readAllBytes();
            }
            CRC32 check = new CRC32();
            check.update(bytes);
            System.out.println("name=" + entry.getName());
            System.out.println("entry-comment=" + entry.getComment());
            System.out.println("archive-comment=" + zip.getComment());
            System.out.println("mtime=" + entry.getLastModifiedTime().toInstant());
            System.out.println("crc-valid=" + (check.getValue() == entry.getCrc()));
            System.out.println("payload=" +
                    new String(bytes, StandardCharsets.UTF_8));
        }
    }

    public static void main(String[] args) throws IOException {
        Path modern = Files.createTempFile("utf8-zip-", ".zip");
        Path legacy = Files.createTempFile("legacy-zip-", ".zip");
        try {
            writeArchive(modern, StandardCharsets.UTF_8,
                    "tài-liệu/đề-cương.txt", "Bản mẫu");
            writeArchive(legacy, Charset.forName("IBM437"),
                    "café.txt", "Example");
            System.out.println("[UTF-8]");
            inspect(modern, StandardCharsets.UTF_8,
                    "tài-liệu/đề-cương.txt");
            System.out.println("[IBM437]");
            inspect(legacy, Charset.forName("IBM437"), "café.txt");
        } finally {
            Files.deleteIfExists(modern);
            Files.deleteIfExists(legacy);
        }
    }
}
```

Compile and run (JDK 17 or later, with IBM437 charset available):

```bash
javac -encoding UTF-8 ZipEntryMetadataDemo.java
java ZipEntryMetadataDemo
```

Stdout compiled and verified by running:

```text
[UTF-8]
name=tài-liệu/đề-cương.txt
entry-comment=Bản mẫu
archive-comment=Archive note
mtime=2024-01-02T03:04:06Z
crc-valid=true
payload=Xin chào
[IBM437]
name=café.txt
entry-comment=Example
archive-comment=Archive note
mtime=2024-01-02T03:04:06Z
crc-valid=true
payload=Xin chào
```

Explanation:

- `ZipOutputStream(..., StandardCharsets.UTF_8)` writes UTF-8 names and comments. For Vietnamese names, byte length usually differs from `String.length()`; the reader must understand the correct encoding.
- `Charset.forName("IBM437")` is chosen for the second archive, where `é` is representable in that code page; the entry name is still returned by the Java API as a proper Unicode `String` when using the matching charset.
- `PAYLOAD` is always constructed via `getBytes(UTF_8)`. The ZIP header charset has no effect on it because `ZipOutputStream.write(byte[])` operates on raw bytes.
- `ZipEntry.setLastModifiedTime(FileTime)` sets a fixed modification timestamp. The tested JDK returns the exact `Instant` in this example, though archives from other tools might omit extra fields or use a different resolution.
- `ZipEntry.setComment()` and `ZipOutputStream.setComment()` are distinct metadata; inspecting via `ZipFile` reveals both comment levels.
- `CRC32` is computed over the **decompressed bytes** and compared against `entry.getCrc()`. A `true` result confirms the checksum matches; it does not prove the archive was not intentionally modified.
- The example only creates two single-entry archives, so it omits duplicate-name handling, quotas, zip bombs, or filesystem extraction; subsequent sections cover requirements for untrusted inputs.

**Demo limitation:** `ZipFile` opens a complete central directory and the example uses `readAllBytes()` because the payload is tiny and self-generated. For large ZIPs, never call `readAllBytes()` on arbitrary entries without bounding the actual size. Read in chunks with quotas.

## 8. ZipFile vs. ZipInputStream: Metadata Is Not Identical at Every Point

Two reading models:

**`ZipFile`** accesses the ZIP's central directory. It is generally suitable when you need to list many entries, read comments, sizes, CRCs, compressed sizes, or look up an entry by name:

```java
try (ZipFile zip = new ZipFile(archive.toFile(),
        StandardCharsets.UTF_8)) {
    ZipEntry found = zip.getEntry("README.md");
    if (found != null) {
        System.out.println("size=" + found.getSize());
        try (InputStream input = zip.getInputStream(found)) {
            // Process input in chunks with quota.
        }
    }
}
```

This is a snippet; `archive` must be a valid `Path`. `ZipFile.close()` releases resources tied to the compressed file; closing each entry stream when done keeps the code clean.

**`ZipInputStream`** reads sequentially, entry by entry:

```java
try (ZipInputStream in = new ZipInputStream(
        Files.newInputStream(archive), StandardCharsets.UTF_8)) {
    ZipEntry entry;
    while ((entry = in.getNextEntry()) != null) {
        System.out.println(entry.getName());
        byte[] buf = new byte[8192];
        long expanded = 0;
        for (int n; (n = in.read(buf)) != -1; ) {
            expanded += n;
            if (expanded > MAX_UNCOMPRESSED_BYTES) {
                throw new IOException("Entry quá lớn");
            }
            // Process buf[0..n) with the required sink.
        }
        in.closeEntry();
    }
}
```

This is a **snippet**, requiring `MAX_UNCOMPRESSED_BYTES` defined per quota and appropriate imports. `ZipInputStream` reads local file headers; some metadata (especially fields present only in the central directory) may be unknown until the entry finishes or may not be populated like in `ZipFile`. Therefore, never assume `getComment()` or `getSize()` is always available on every entry while streaming.

If archive comments and complete central-directory metadata are needed, usually choose `ZipFile`. For files received from a non-seekable stream, `ZipInputStream` may fit, yet the application must still design validation, quotas, error handling, and EOF policies.

## 9. DEFLATED vs. STORED and Required Declarations

`ZipEntry` has two common methods supported by the standard Java API:

- **`ZipEntry.DEFLATED`**: data is DEFLATE-compressed. With `ZipOutputStream`, the JDK can compute CRC/size when closing the entry if not specified beforehand; the writer does not usually need all info upfront.
- **`ZipEntry.STORED`**: content is stored uncompressed. When using `ZipOutputStream` with STORED, before `putNextEntry` you must set `size`, `compressedSize`, and `CRC-32` per the API contract; both sizes must be equal.

STORED example for an existing byte array:

```java
byte[] data = "Hello".getBytes(StandardCharsets.UTF_8);
CRC32 checksum = new CRC32();
checksum.update(data);

ZipEntry entry = new ZipEntry("hello.txt");
entry.setMethod(ZipEntry.STORED);
entry.setSize(data.length);
entry.setCompressedSize(data.length);
entry.setCrc(checksum.getValue());

out.putNextEntry(entry);
out.write(data);
out.closeEntry();
```

This is a **snippet**: `out` must be an open `ZipOutputStream` with imports for `ZipEntry`, `CRC32`, and `StandardCharsets`. With STORED, supplying an inaccurate size/CRC or writing a different byte count can cause the library to throw `ZipException`. With DEFLATED, size/compressed size depend on compression level and content; never infer compressed size from character count.

Never blindly assume every entry read from external sources uses DEFLATED/STORED and skip checking `getMethod()`. ZIP has many extensions and other methods; Java's `java.util.zip` does not support every ZIP variant (such as many encryption formats or extended compression methods).

## 10. Extra Fields: When Are They Needed and Why Must Parsing Be Careful?

ZIP extra fields are extensible byte regions in headers and the central directory. Each item typically has a header ID, data size, and payload. Common examples:

| Illustrative ID | Common Meaning | Note |
| --- | --- | --- |
| `0x5455` | Extended timestamp (often called UT). | May contain modification/access/creation times depending on length and flags. |
| `0x000A` | NTFS extra field. | May contain timestamps in Windows FILETIME format. |
| `0x0001` | ZIP64 extended information. | Used to represent sizes/offsets exceeding classic header limits. |
| `0x7075` | Unicode Path Extra Field. | Adds a Unicode name, with version and CRC verifying the original name. |
| `0x6375` | Unicode Comment Extra Field. | Adds a Unicode comment; not all readers use it automatically. |

Example accessing raw extras:

```java
byte[] extra = entry.getExtra();
if (extra != null) {
    System.out.println("extra bytes=" + extra.length);
}
```

This is a snippet; `entry` is a `ZipEntry`. **Never assume** an extra field always has an expected length. When parsing manually:

1. Bound the total extra byte length per the ZIP structure.
2. For each field, verify at least 4 header bytes remain (ID and data length).
3. Read header integers in ZIP's **little-endian** byte order.
4. Before reading the payload, verify the data length does not exceed the remaining slice.
5. Handle unknown fields by skipping them with bounds checking; never cast or allocate memory unchecked.
6. For Unicode extras, check version, CRC, and alignment with the original name before trusting the data.
7. Never assume `ZipEntry.getExtra()` preserves the exact original raw bytes intact after the JVM has parsed special timestamps/fields.

`setExtra(byte[])` is for specifically structured binary metadata; it does not magically turn arbitrary bytes into attributes understood properly by ZIP and all tools. If full preservation of ZIP-specific external attributes/permissions/ownership is required, specialized tools/libraries and compatibility testing beyond `java.util.zip` may be necessary.

## 11. Comments and Encoding: Common Bugs

Typical mistakes:

- Writing UTF-8 names while a legacy reader tries to decode using another code page ⇒ accented letters turn into mojibake or errors.
- Writing entry names containing characters unrepresentable in a legacy charset ⇒ the writer may throw or produce an unexpected archive.
- Confusing `ZipEntry.comment` with `ZipOutputStream.setComment` ⇒ reading only the archive comment misses individual entry notes.
- Assuming `ZipInputStream.getNextEntry()` supplies full central-directory comment metadata ⇒ may return `null`.
- Writing a comment exceeding 65,535 **encoded bytes** ⇒ rejected by the writer or produces an invalid archive.
- Storing Vietnamese names while forgetting that some older archive tools lack proper encoding detection.
- Creating a ZIP with one library and reading it with another; inconsistent Unicode extras, bit flags, timestamps, and external attributes ⇒ unexpected results.

For strong interoperability, test **both directions**: Java creates ZIP → target tool reads; target tool creates ZIP → Java reads. Your test fixture suite should include ASCII names, accented Vietnamese names, supplementary characters (emoji if supported), long names, accented comments, timestamps, empty directories, and entries without explicit parent directory entries.

## 12. Safe Extraction: Entry Names Are Untrusted Paths

An externally supplied archive can contain names like:

```text
../outside.txt
/absolute/path.txt
C:/Windows/target.txt
safe/../../escape.txt
folder\..\escape.txt
```

**Never** join an entry name directly onto a root directory and write the file without validation. Mapping ZIP names to real paths depends on the OS and directory policies.

A foundational strategy:

1. Define a fixed, controlled destination directory, such as `targetRoot.toAbsolutePath().normalize()`.
2. Only accept relative entry names using `/`; reject absolute paths, drive prefixes, `\` separators unless explicitly justified, and `..` components.
3. Use `Path.resolve(name).normalize()` and verify the resulting path stays under the root **using `startsWith(Path)` on normalized `Path` objects**, not string prefix comparison.
4. Before writing, protect against symlinks already present in the target path; `normalize()` is a **syntactic** check and does not eliminate symlink/TOCTOU races.
5. Use an isolated extraction directory, appropriate permissions, and an explicit overwrite policy; for untrusted sources, enforce resource limits and consider safer APIs (such as controlled relative resolution / `SecureDirectoryStream` when supported by the provider).
6. Reject duplicate names or names that collide after normalization/case-folding on the target filesystem to prevent unwanted overwrites.

Illustrative example:

```java
// Snippet: trustedRoot is an application-controlled Path.
Path root = trustedRoot.toAbsolutePath().normalize();
String rawName = entry.getName();

if (rawName.startsWith("/") || rawName.contains("\\") ||
        rawName.contains("..") || rawName.indexOf('\0') >= 0) {
    throw new IOException("Tên entry không được phép");
}

Path destination = root.resolve(rawName).normalize();
if (!destination.startsWith(root) || destination.equals(root)) {
    throw new IOException("Entry nằm ngoài thư mục đích");
}
```

This is a **basic defensive snippet** and intentionally broad in its rejections (for example, a normal filename containing `..` in its name would also be rejected). It does not by itself stop all symlink/TOCTOU attacks if the filesystem is modified concurrently; before production use, apply platform/provider-appropriate policies and an application-owned destination directory. Do not treat this snippet as a complete extractor.

## 13. ZIP Bombs, CRC, and Untrusted Metadata

Even when an entry has no path traversal, an archive can have a **tiny compressed size but huge uncompressed size**. A file of a few KB can expand into many GB when decompressed. Other risks include archives with huge entry counts, nested archives, very long names, and malformed structures.

Limits to define:

| Risk | Mitigation |
| --- | --- |
| Single uncompressed entry too large | Enforce a decompressed byte quota **while streaming**. |
| Total ZIP bytes exceed limit | Accumulate total bytes across all entries and abort when exceeding the quota. |
| Too many entries | Limit entry count and directory depth. |
| Abnormal compression ratio | Set compression-ratio thresholds/risk checks, though **never rely on ratio alone**. |
| Extraction takes too long | Enforce CPU deadlines/timeouts and bounded processing so services are not blocked. |
| Corrupted entry or CRC mismatch | Validate, discard all uncommitted output data, and log appropriately. |
| Unusual extra fields/metadata | Validate lengths and ignore unsupported fields per policy. |
| Duplicate filenames or overwrites | Track normalized names and use safe file-creation modes. |

**CRC-32 is not an origin authentication mechanism.** It detects common accidental data errors, yet an archive creator can alter the payload and recompute the CRC. When you need to trust content, use digital signatures or cryptographic hashes bound to a manifest verified by a trusted source, or your system's dedicated protection mechanisms. Nor does ZIP guarantee that timestamps, comments, or filenames are trustworthy for security decisions.

If `entry.getSize()` is `-1` or spoofed, never allocate buffers based on that size or assume everything is safe; quotas must count the **actual bytes** passing through the stream.

## 14. Preserving Metadata When Copying or Repacking a ZIP

When reading an input archive and writing a new archive, an application may want to preserve:

- Properly decoded entry names.
- Directory relationships and trailing `/` on directory entries.
- Individual entry comments and the archive comment.
- Modification/access/creation times when available.
- Compression method, size, CRC, and extra fields when compatible.
- Permissions/owner/external attributes if business logic requires them, which usually demands specialized libraries since the standard API does not cover all fields.

However, **do not blindly copy all metadata by calling every setter unconditionally**:

1. If a name was decoded with the wrong charset, writing it back in UTF-8 permanently "freezes" the corrupted name.
2. Never force `STORED` without compatible size/CRC values.
3. A `ZipEntry` from a compressed archive may have size/compressed size/CRC that are no longer valid if the payload was modified or the compression level changed.
4. Extra fields may carry data tied to old layouts, offsets, filenames, or timestamps; blindly copying raw bytes can create inconsistent metadata.
5. Invalid metadata must be rejected or sanitized under a clear policy. Preserving unintended external symlinks/permissions can create risks on extraction.

When converting an archive to UTF-8, **decode legacy names accurately first, normalize internal conventions, and then write a new UTF-8 ZIP**. When bit-identical archive preservation is required, high-level unpack/repack APIs are unsuitable; copy raw archive bytes or use structure-preserving tools.

## 15. Choosing APIs and Conventions in System Design

**Creating new cross-platform ZIPs:**

- Prefer `StandardCharsets.UTF_8` and `ZipOutputStream`.
- Name entries with `/`, never OS absolute paths.
- Include only necessary metadata while clearly documenting receiver expectations.
- Close each entry with `closeEntry()` and close `ZipOutputStream` via `try-with-resources` so the central directory is written completely.
- Bound input/entry counts/sizes; normalize duplicate detection and reject unsafe paths.

**Reading legacy ZIPs:**

- Use `ZipFile(file, charset)` when complete central directory access and lookup by name are needed.
- Honor the UTF-8 bit flag and pick the right legacy charset from the source contract when the flag is unset.
- Test names, charsets, comments, timestamps, and methods using real fixtures.
- Treat metadata as optional/untrusted; never pass raw entry names directly to the filesystem.

**Reading streaming ZIPs:**

- Use `ZipInputStream(input, charset)` when sequential processing is needed.
- Never rely on `getSize()`/comments always being ready at `getNextEntry()`; track actual decompressed bytes.
- Ensure entries are fully read/closed and errors/EOF are handled properly.
- Enforce entry count, total ZIP quota, and timeouts; never allocate an array sized from untrusted metadata.

**Archives requiring richer metadata than baseline ZIP:** consider libraries supporting external attributes, symlinks, encryption, and ZIP64/Unicode extras per specific requirements. Never try to force `java.util.zip` to provide capabilities the API does not guarantee.

## 16. Common Errors and Resolutions

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Vietnamese entry names turn into strange characters | Wrong charset decoding on a legacy ZIP without the UTF-8 flag. | Determine the source charset and pass it explicitly to `ZipFile/ZipInputStream`. |
| Reader still uses UTF-8 even though IBM437 was passed | Entry has the UTF-8/EFS flag set. | Honor the flag; do not force legacy decoding when the flag specifies UTF-8. |
| Cannot create a ZIP with Unicode names | Chosen charset cannot represent those names/comments. | Use UTF-8 for new ZIPs. |
| Text payload reads incorrectly even though the name is right | Using the entry name charset to decode content. | Separate header charset from payload charset; identify the inner file's encoding. |
| `getComment()` returns null | No comment present or reading from a source lacking central-directory metadata. | Treat comments as optional; use `ZipFile` when needed. |
| `getSize()` returns -1 | Metadata unknown in a streaming context. | Count actual bytes and enforce quotas. |
| CRC mismatch / `ZipException` | Corrupted compressed data, truncated bytes, or metadata mismatch. | Reject the data and do not commit incomplete output. |
| Timestamp discrepancies | Different DOS time, timezone, resolution, or extra fields. | Standardize time policy, use Instant/FileTime, test round-trip. |
| Unrecognized extra fields | Metadata extensions from another ZIP tool. | Parse by ID/length with bounds checks or use an appropriate library. |
| Extraction escapes target directory | Entry name has `..`/absolute path/symlink. | Validate paths, enforce root boundaries, and protect against TOCTOU. |
| Disk full while extracting | Zip bomb or missing quotas. | Limit actual decompressed bytes and total disk usage. |
| Empty folders missing | ZIP only recorded files or omitted directory entries. | Write explicit directory entries when empty folders must be preserved. |
| ZIP opens in Java but fails in another tool | Different support for methods, charsets, extras, or ZIP64. | Verify compatibility on target tools/platforms. |

## 17. Practice Exercises

**Exercise 1 — Name and payload charsets.** Change the UTF-8 entry name to `"ảnh/đồ-thị.txt"` and the payload to `"Đồ thị mẫu"`. Verify that changing the payload charset **does not** alter how the entry name is decoded; identify where each charset is configured.

**Exercise 2 — IBM437 ZIP.** With entry `"café.txt"`, read using `IBM437` and compare against using the UTF-8 constructor. Predict how misdecoding can throw errors or corrupt the name. Do not attempt to write Vietnamese accented characters unsupported in IBM437 to a legacy ZIP without handling exceptions.

**Exercise 3 — STORED metadata.** Use `CRC32` and `ZipEntry.STORED` to add entry `"raw.bin"` containing 10 bytes. Set accurate size, compressed size, and CRC before `putNextEntry`; try declaring a wrong CRC to observe the failure and explain why CRC is not a digital signature.

**Exercise 4 — Timestamps/extra.** Create an entry with a fixed modification timestamp, read it back with `ZipFile`, and inspect `getTime()`/`getLastModifiedTime()`/`getExtra()`. Compare across two different ZIP tools to spot differences in precision and extra fields.

**Exercise 5 — Directory entries.** Create a ZIP containing only `"empty/"` and `"docs/info.txt"`. Inspect `isDirectory()`, contents, and how extraction preserves empty folders. Why does `"docs/info.txt"` not require the archive to have a separate `"docs/"` entry?

**Exercise 6 — Safe extraction.** Build a `safeExtract` function checking absolute paths, `..` components, symlinks, duplicate names, and a 100 MiB total uncompressed limit. Test with an archive containing `"../escape.txt"` to verify rejection without writing any file outside the root.

**Exercise 7 — ZIP bomb.** Simulate a small compressed entry that expands to many repeated bytes on decompression. Count actual bytes in the read loop and halt at the quota even if `entry.getSize()` is missing or forged. Test only in a size-bounded temporary directory, never against production data.

**Exercise 8 — Converting legacy encoding to UTF-8.** Take a ZIP with IBM437 names, decode them accurately, and create a new UTF-8 ZIP with Unicode names and proper comments. Measure readability on target tools and verify metadata is preserved/converted according to policy.

### Self-Check Questions

1. Which charset governs entry names and which governs data inside an entry?
2. What does EFS/UTF-8 bit 11 tell the reader?
3. Why should passing `IBM437` not override a name flagged as UTF-8?
4. How does a ZIP entry comment differ from an archive comment?
5. When `ZipInputStream.getNextEntry()` returns an entry, are all sizes/CRCs/comments guaranteed to be ready?
6. When must size/compressed size/CRC be set beforehand for `STORED`?
7. Do `FileTime` and extra fields preserve nanosecond timestamps across all OSes?
8. Does CRC-32 stop an attacker from modifying an archive and recomputing the CRC?
9. Why is `Path.normalize()` not enough to prevent all symlink races during extraction?
10. Should you use `ZipFile` or `ZipInputStream` when you need the archive comment and fast entry lookup?

## 18. References

- [Java SE 21 — ZipEntry](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/zip/ZipEntry.html): name, comment, time, method, size, CRC, and extra.
- [Java SE 21 — ZipFile](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/zip/ZipFile.html): opening ZIPs with charset, looking up entries, and archive comments.
- [Java SE 21 — ZipInputStream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/zip/ZipInputStream.html): reading entries sequentially from an `InputStream`.
- [Java SE 21 — ZipOutputStream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/zip/ZipOutputStream.html): writing entries, charsets, comments, and finalizing the central directory.
- [Java SE 21 — Charset](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/Charset.html): selecting and handling character encodings.
- [PKWARE APPNOTE — ZIP format specification](https://pkware.cachefly.net/webdocs/casestudies/APPNOTE.TXT): ZIP bit flags, metadata, and extra field conventions.

**Remember:** Entry names/comments are ZIP metadata with their own charset and flags; payloads are independent bytes. Choose UTF-8 for new archives, read legacy archives with a verified charset, understand that timestamps/extra fields/sizes may be missing or differ across tools, and always validate paths, quotas, and trust before extracting.
