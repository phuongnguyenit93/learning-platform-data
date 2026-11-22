# `putNextEntry`, `closeEntry`, and Finalizing a ZIP Archive in Java

## 1. The Problem: A Valid ZIP Requires More Than Writing Bytes

In Java Core, the `java.util.zip` package supports creating and reading ZIP files. When packaging multiple files into an archive, an application cannot simply concatenate the bytes of each file and rename the extension to `.zip`. The ZIP format contains **entries**, metadata, integrity check information, and a **central directory** that tells readers what the archive contains.

`ZipOutputStream` is the class used to **sequentially write a ZIP archive** to an `OutputStream`. Three core operations:

- **`putNextEntry(ZipEntry entry)`**: begins writing a new entry, positioning the stream at that entry's data section.
- **`closeEntry()`**: ends the current entry, finalizing the required entry metadata and preparing the state to write the next entry.
- **`finish()`**: finalizes the **entire ZIP archive** (including the central directory) **without closing the underlying output stream**.
- In addition, **`close()`** on `ZipOutputStream` finalizes the archive (if not already finalized) **and closes the underlying stream**.

**Key point:** `closeEntry()` closes **one component** of the ZIP; `finish()` and `close()` complete **the entire archive structure**. A ZIP file may have had every entry closed with `closeEntry()` and still not be a complete ZIP archive if the ending structures/central directory have not been written yet.

Standard usage example:

```java
try (ZipOutputStream zip =
         new ZipOutputStream(Files.newOutputStream(zipPath))) {

    zip.putNextEntry(new ZipEntry("a.txt"));
    zip.write("A".getBytes(StandardCharsets.UTF_8));
    zip.closeEntry();

    zip.putNextEntry(new ZipEntry("b.txt"));
    zip.write("B".getBytes(StandardCharsets.UTF_8));
    zip.closeEntry();

} // close() automatically finalizes the archive and closes the underlying stream.
```

This is an **illustrative snippet**, not a standalone program: `zipPath` must be declared and the APIs imported. Complete runnable examples appear in later sections.

## 2. `ZipOutputStream`, `ZipEntry`, and the Archive Lifecycle

Diagram of common operational states:

```text
Open ZipOutputStream
       |
       v
putNextEntry("a.txt")
       |
       v
write(bytes of a.txt)
       |
       v
closeEntry()
       |
       +------------------------------+
       |                              |
       v                              |
putNextEntry("b.txt")                 |
       |                              |
       v                              |
write(bytes of b.txt)                 |
       |                              |
       v                              |
closeEntry()                          |
       |                              |
       +--> ... next entry ... -------+
       |
       v
finish() or close()
       |
       v
Central directory + ending info
       |
       v
Complete ZIP archive
```

**`ZipEntry`** describes one component inside the archive. It carries the entry name (e.g., `docs/readme.txt`), modification time, compression method, size, and CRC-32 when available. **`ZipOutputStream`** manages how entry data and metadata are written into the ZIP stream.

A multi-file ZIP is not multiple `ZipOutputStream` instances concatenated together: it is **one `ZipOutputStream`**, with **multiple `putNextEntry`/`closeEntry` cycles**, followed by **one archive finalization**.

| Scope | Object / Operation | Ending Event |
| --- | --- | --- |
| A single file/directory in the ZIP | `ZipEntry` | `closeEntry()` |
| Entire ZIP file with multiple entries | `ZipOutputStream` | `finish()` or `close()` |
| Physical byte destination | Underlying `OutputStream` | `close()` if owned by the ZIP stream; or closed by its owner |

**Order matters**: calling `write` right before `putNextEntry` does not mean "writing a ZIP file". To write entry data, you must open an entry first.

## 3. What Parts Are Inside a ZIP?

Conceptually, a ZIP archive typically contains:

```text
+----------------------------+
| Local file header: a.txt   |
+----------------------------+
| Compressed data: a.txt     |
+----------------------------+
| (optional data descriptor) |
+----------------------------+
| Local file header: b.txt   |
+----------------------------+
| Compressed data: b.txt     |
+----------------------------+
| (optional data descriptor) |
+----------------------------+
| Central directory records  |
| a.txt, b.txt, offsets ...  |
+----------------------------+
| End of central directory   |
+----------------------------+
```

This is a simplified diagram and does not cover every variant of the ZIP specification (such as ZIP64, extra fields, or comments). Yet it illustrates why **closing the last entry does not mean the archive is finished**.

- **Local file header** sits right before each entry's data.
- **Data descriptor** may appear when size/CRC are unknown beforehand and is written after the data.
- **Central directory** contains the consolidated metadata table, offsets, and entry count.
- **End of central directory** terminates the ZIP structure.

`ZipFile` typically relies on the central directory for random entry access. Thus, if you attempt to open the archive via `ZipFile` before calling `finish()` or `close()`, there is no guarantee the archive is valid. Conversely, `ZipInputStream` may be able to read **some local entry data** from an incomplete stream, but such partial reading **does not prove the entire archive is structurally sound**.

**Do not use `flush()` as a substitute for `finish()`.** `flush` only pushes already-buffered bytes through stream layers per the flush contract; it does not mean the central directory has been written.

## 4. `putNextEntry(ZipEntry)`: Starting a New Entry

Syntax:

```java
ZipEntry entry = new ZipEntry("docs/readme.txt");
zip.putNextEntry(entry);
zip.write(content);
zip.closeEntry();
```

This is an illustrative snippet with `zip` and `content` declared elsewhere.

When calling `putNextEntry`:

1. `ZipOutputStream` starts an entry with the specified name.
2. Writes the necessary header information to identify the entry in the ZIP.
3. Configures the stream so subsequent `write(...)` calls belong to **the new entry**.
4. If a previous entry is still active, `putNextEntry` will **close the previous entry** before starting the new one per the Java API contract.

Step 4 allows the code to advance to a new entry automatically, but **it is no reason to omit `closeEntry()` in clean code**. Calling `closeEntry` explicitly makes lifecycle management, error-handling points, and metadata inspection clearer.

### Entry Names Are Logical Paths Inside the ZIP

`new ZipEntry("docs/readme.txt")` has the name `docs/readme.txt`. The forward slash `/` is the standard directory separator in ZIP and **is independent of the operating system's path separator**.

| Entry Name | Common Meaning |
| --- | --- |
| `report.txt` | File at the root of the ZIP |
| `docs/readme.txt` | File inside the logical folder `docs/` |
| `docs/` | Entry representing a directory |
| `images/a.png` | File inside the logical folder `images/` |

`ZipEntry` **does not create real directories on disk**; it only records the name and metadata in the archive. During extraction, the ZIP reader decides how to create the corresponding directory structure.

To represent an **empty directory** in a ZIP, you need an entry whose name ends with `/`, such as `new ZipEntry("empty/")`, typically with no data bytes written. If the archive only contains `docs/readme.txt` without `docs/`, many extraction tools still create parent directories as needed. However, an **empty directory** will not be represented unless it has its own directory entry.

### Duplicate Names and Metadata

Within a single `ZipOutputStream`, duplicate entry names are not allowed; you may encounter `ZipException: duplicate entry: ...`. Packaging applications must define a policy for duplicate names: reject, rename, or select a single source before writing. **You cannot "reopen the same entry to append more data" after closing it** simply by calling `putNextEntry` again with the same name.

If no modification time is set on a `ZipEntry`, the implementation may use the current time. Therefore, **output ZIP bytes are not guaranteed to be identical across runs** even when the file contents are identical. To produce reproducible ZIP byte outputs in a build pipeline, you must control entry ordering, timestamps, names, metadata, charset, compression algorithm/level, and environment compatibility.

## 5. `write` Only Writes Data for the Current Entry

Between `putNextEntry` and `closeEntry`, `ZipOutputStream.write(...)` writes the content **of the currently open entry**.

```java
zip.putNextEntry(new ZipEntry("hello.txt"));
zip.write("Hello".getBytes(StandardCharsets.UTF_8));
zip.write(" World".getBytes(StandardCharsets.UTF_8));
zip.closeEntry();
```

Two consecutive `write` calls produce the decompressed content `Hello World` **inside the same entry**, not two separate files.

For large files, transfer bytes in chunks from an `InputStream`:

```java
try (InputStream input = Files.newInputStream(source)) {
    zip.putNextEntry(new ZipEntry("payload.bin"));

    byte[] buffer = new byte[8192];
    int count;
    while ((count = input.read(buffer)) != -1) {
        zip.write(buffer, 0, count);
    }

    zip.closeEntry();
}
```

This is an illustrative snippet: `zip` and `source` must be declared, along with imports and exception handling. Using a loop avoids `Files.readAllBytes` for large files. `closeEntry` must be called **after copying all data**; do not close the entry on every read iteration.

### Do Not Arbitrarily Wrap a ZIP Stream in a Writer

`ZipOutputStream` is a **byte** stream, not a character stream. If the content is text, specify the charset explicitly:

```java
byte[] utf8 = "Xin chào".getBytes(StandardCharsets.UTF_8);
zip.write(utf8);
```

Do not rely on the machine's default charset. If wrapping `OutputStreamWriter` or `BufferedWriter` around `ZipOutputStream`, understand that **a buffered writer can hold unflushed bytes** and `writer.close()` will close the entire ZIP stream before subsequent entries are written. For many small entries, using `getBytes(StandardCharsets.UTF_8)` or a carefully lifecycle-managed adapter layer is usually simpler.

## 6. `closeEntry()`: Ends the File, Not the Archive

Signature:

```java
void closeEntry() throws IOException;
```

`closeEntry()` finalizes the current entry and puts `ZipOutputStream` into a state ready to start the next entry. For entries using `DEFLATED`, closing the entry finishes that entry's compressed stream and writes the information needed to decompress and verify the data. For `STORED`, closing may verify size/CRC against the declared metadata.

**What `closeEntry()` does NOT do:**

- Does not create the next entry.
- Does not close the underlying `OutputStream`.
- Does not finalize the archive's central directory.
- Does not destroy or reopen `ZipOutputStream`.
- Does not guarantee the target file is durably flushed to disk.

You can call `putNextEntry`, `write`, and `closeEntry` repeatedly on **the same** stream for distinct entry names.

Clear naming separates the two levels:

```text
putNextEntry("a.txt")  -> open entry a
write(bytes)           -> write data for a
closeEntry()           -> close a

putNextEntry("b.txt")  -> open entry b
write(bytes)           -> write data for b
closeEntry()           -> close b

finish() / close()     -> finalize the ZIP containing a and b
```

If no entry is currently active, calling `closeEntry()` does not produce a new archive. Never use it in place of `finish()`.

## 7. `finish()` Compared with `close()` and `flush()`

These three end-of-stream operations are often confused:

| Call | Finalizes ZIP? | Closes `ZipOutputStream`? | Closes Underlying Stream? | When to Use |
| --- | --- | --- | --- | --- |
| `closeEntry()` | **No** | No | No | After each entry |
| `flush()` | **No** | No | No | Pushes bytes through the stream per flush contract; does not finalize the archive |
| `finish()` | **Yes** | Does not close underlying stream | **No** | Need to finalize the ZIP while preserving sink ownership |
| `close()` | **Yes** | **Yes** | **Yes** | ZIP stream owns the sink; fits try-with-resources |

Read the `finish()` row carefully: it **ends the ZIP data section** without closing the wrapped stream. The `ZipOutputStream` object should not be reused to start additional entries after `finish()`, because the ZIP structure has already ended. `finish()` **is not a "checkpoint" from which you can append more entries**.

`close()` both finalizes the ZIP and closes itself along with the destination stream. If writing to a file via `Files.newOutputStream(zipPath)`, **`try-with-resources` is the default choice**: whether exiting the scope normally or via exception, the resource is closed; if an I/O error occurs during finalization/closing, `IOException` can still be thrown, in which case the archive may be invalid.

**Do not routinely call `finish()` before every `close()`.** `close()` is responsible for finalizing the archive, so the standard idiom is simply closing the ZIP stream properly. Calling `finish()` explicitly is useful when you need to mark the exact end of the archive **without yet closing the destination**.

### When Is `finish()` Actually Used in Practice?

If a library accepts a caller-owned `OutputStream` and must write a complete ZIP **without closing the caller's stream**, it can:

1. Create a `ZipOutputStream` wrapping the provided output.
2. Write all entries.
3. Call `finish()`.
4. **Do not** call `close()` on `ZipOutputStream` if doing so would close the caller's output.
5. Let the caller manage flushing/closing the output per the API contract.

Ownership and cleanup on exception during archive writing must be designed explicitly. If compression resources must also be released while keeping the destination open, the safe approach depends on wrapper/adapter structure and desired lifecycle; **never assume `close()` leaves the underlying stream open**.

## 8. Standalone Java 17+ Example: Creating a Multi-Entry ZIP and Verifying the Central Directory

This first example writes a ZIP to a **temporary file**, containing one directory entry and two text files. It calls `closeEntry()` explicitly after each entry. Once `try-with-resources` closes `ZipOutputStream`, `ZipFile` reads back the finalized ZIP.

The program verifies:

- The ZIP has exactly three entries.
- Both text entries yield the expected contents.
- The directory entry is recognized via `isDirectory()`.

**File `ZipLifecycleDemo.java`:**

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;
import java.util.zip.ZipOutputStream;

public class ZipLifecycleDemo {
    public static void main(String[] args) throws IOException {
        Path zipPath = Files.createTempFile("zip-lifecycle-", ".zip");

        try {
            try (ZipOutputStream zip = new ZipOutputStream(
                    Files.newOutputStream(zipPath),
                    StandardCharsets.UTF_8)) {

                zip.putNextEntry(new ZipEntry("docs/"));
                zip.closeEntry();

                zip.putNextEntry(new ZipEntry("docs/a.txt"));
                zip.write("Xin chao".getBytes(StandardCharsets.UTF_8));
                zip.closeEntry();

                zip.putNextEntry(new ZipEntry("docs/b.txt"));
                zip.write("Java 17".getBytes(StandardCharsets.UTF_8));
                zip.closeEntry();
            } // close(): finalizes the central directory and closes the file.

            try (ZipFile archive = new ZipFile(
                    zipPath.toFile(), StandardCharsets.UTF_8)) {

                System.out.println(
                        "So entry: " + archive.size());

                ZipEntry directory = archive.getEntry("docs/");
                System.out.println(
                        "Entry thu muc: " + directory.isDirectory());

                ZipEntry a = archive.getEntry("docs/a.txt");
                try (var input = archive.getInputStream(a)) {
                    System.out.println("a.txt: "
                            + new String(input.readAllBytes(),
                                    StandardCharsets.UTF_8));
                }

                ZipEntry b = archive.getEntry("docs/b.txt");
                try (var input = archive.getInputStream(b)) {
                    System.out.println("b.txt: "
                            + new String(input.readAllBytes(),
                                    StandardCharsets.UTF_8));
                }
            }
        } finally {
            Files.deleteIfExists(zipPath);
        }
    }
}
```

Run with **JDK 17+**:

```bash
javac ZipLifecycleDemo.java
java ZipLifecycleDemo
```

**Stdout when creating/reading the ZIP succeeds:**

```text
So entry: 3
Entry thu muc: true
a.txt: Xin chao
b.txt: Java 17
```

Step-by-step explanation:

1. `Files.createTempFile` creates a location to store the test ZIP.
2. `ZipOutputStream` wraps the file output stream and uses `UTF-8` for **entry names**.
3. `docs/` ends with `/` and contains no payload; `closeEntry` finishes the directory entry.
4. `docs/a.txt` and `docs/b.txt` are opened in turn via `putNextEntry`, written with UTF-8 bytes, and closed via `closeEntry`.
5. Exiting `try` invokes `zip.close()` automatically, finalizing the archive.
6. `ZipFile` reads a valid ZIP with a central directory; `getEntry` fetches entries by exact name and `getInputStream` returns the decompressed content.
7. `finally` deletes the temp file after `ZipFile` has been closed. Deletion behavior may be affected if another process interferes with the file, though the program does not depend on the random temp filename.

Because the example looks up entries by name rather than printing the order listed by `ZipFile.entries()`, the output does not depend on file creation time or actual compressed ZIP size.

## 9. Java 17+ Example: Proving `finish()` Does Not Close the Sink

To observe the difference between `finish()` and `close()`, we wrap the underlying stream with a `closed` flag. After `finish()`, the flag remains unchanged. Only when `close()` is called on the ZIP stream is the sink closed.

**File `ZipFinishDemo.java`:**

```java
import java.io.ByteArrayOutputStream;
import java.io.FilterOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;
import java.util.zip.ZipOutputStream;
import java.io.ByteArrayInputStream;

public class ZipFinishDemo {
    private static class TrackedOutputStream extends FilterOutputStream {
        boolean closed = false;

        TrackedOutputStream(OutputStream destination) {
            super(destination);
        }

        @Override
        public void close() throws IOException {
            closed = true;
            super.close();
        }
    }

    public static void main(String[] args) throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        TrackedOutputStream destination = new TrackedOutputStream(bytes);
        ZipOutputStream zip = new ZipOutputStream(
                destination, StandardCharsets.UTF_8);

        try {
            zip.putNextEntry(new ZipEntry("one.txt"));
            zip.write("OK".getBytes(StandardCharsets.UTF_8));
            zip.closeEntry();

            zip.finish();
            System.out.println("Sink closed after finish: "
                    + destination.closed);

            try (ZipInputStream input = new ZipInputStream(
                    new ByteArrayInputStream(bytes.toByteArray()),
                    StandardCharsets.UTF_8)) {
                ZipEntry entry = input.getNextEntry();
                System.out.println("First entry: " + entry.getName());
                System.out.println("Body: " + new String(
                        input.readAllBytes(), StandardCharsets.UTF_8));
                input.closeEntry();
            }
        } finally {
            zip.close();
        }

        System.out.println("Sink closed after close: "
                + destination.closed);
    }
}
```

Compile/run:

```bash
javac ZipFinishDemo.java
java ZipFinishDemo
```

**Stdout on success:**

```text
Sink closed after finish: false
First entry: one.txt
Body: OK
Sink closed after close: true
```

**Analysis:**

- `zip.finish()` writes the ZIP ending structures; `TrackedOutputStream.closed` remains `false`.
- `ZipInputStream` reads from a copy of `byte[]` once the ZIP has been finalized.
- `zip.close()` is called in `finally`, closing the ZIP stream and the underlying stream; the `closed` flag becomes `true`.
- `ByteArrayOutputStream.close()` in the standard JDK does not make previously written data inaccessible; here we use a tracking wrapper to observe that `close` is actually propagated down to the sink.

**This example demonstrates ownership, not a recommendation to always call both `finish()` and `close()`.** If the goal is to keep the underlying stream open for the caller, production code must clearly define who owns and is allowed to close the stream, rather than using `finally { zip.close(); }` when the caller forbids closing the sink.

## 10. `DEFLATED` and `STORED`: Different Metadata Requirements

Two common methods supported by `ZipEntry`:

| Method | Characteristics | Must Provide Metadata Upfront? |
| --- | --- | --- |
| `ZipEntry.DEFLATED` | DEFLATE compression, default for `ZipOutputStream` | Usually the stream can compute size/CRC automatically while writing |
| `ZipEntry.STORED` | Stores raw bytes, uncompressed | **Size, compressed size, and CRC-32 must be determined beforehand** |

With `DEFLATED`, if size, compressed size, or CRC are not set, `ZipOutputStream` can compute and write the appropriate values after processing the data. You must still call `closeEntry()` to finish the entry; you cannot assume the input array length is the compressed size.

With **`STORED`**, ZIP does not compress the bytes, so compressed size equals size. You must declare accurate size and CRC-32 before writing; if missing or if written data does not match, `ZipException` may occur.

Example metadata setup for a STORED entry:

```java
byte[] payload = new byte[] {10, 20, 30};
CRC32 checksum = new CRC32();
checksum.update(payload);

ZipEntry raw = new ZipEntry("raw.bin");
raw.setMethod(ZipEntry.STORED);
raw.setSize(payload.length);
raw.setCompressedSize(payload.length);
raw.setCrc(checksum.getValue());

zip.putNextEntry(raw);
zip.write(payload);
zip.closeEntry();
```

This is an illustrative snippet, assuming `java.util.zip` is imported and `zip` is open. Compute the CRC from **the exact actual input bytes**. `CRC32` is an accidental error-detection code, **not** a cryptographic signature or anti-tampering tool.

### Why Does `STORED` Need CRC Beforehand?

With certain ways of writing uncompressed ZIP content, the header must contain the exact size/CRC before writing the data. `ZipOutputStream` validates these values per the STORED method contract.

If the size is unknown or you must stream a non-rereadable source, you can use `DEFLATED` so ZIP computes the information while writing (even if the data barely compresses), or consider spooling the data to a temporary area before creating the STORED entry.

## 11. Java 17+ Example: Creating a STORED Entry with Exact Size/CRC

The following program creates an in-memory ZIP, stores `raw.bin` **uncompressed**, then reads it back, checking the method and data bytes.

**File `StoredEntryDemo.java`:**

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.zip.CRC32;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;
import java.util.zip.ZipOutputStream;

public class StoredEntryDemo {
    public static void main(String[] args) throws IOException {
        byte[] payload = new byte[] {10, 20, 30, 40};
        CRC32 crc = new CRC32();
        crc.update(payload);

        ZipEntry raw = new ZipEntry("raw.bin");
        raw.setMethod(ZipEntry.STORED);
        raw.setSize(payload.length);
        raw.setCompressedSize(payload.length);
        raw.setCrc(crc.getValue());

        ByteArrayOutputStream sink = new ByteArrayOutputStream();
        try (ZipOutputStream zip = new ZipOutputStream(
                sink, StandardCharsets.UTF_8)) {
            zip.putNextEntry(raw);
            zip.write(payload);
            zip.closeEntry();
        }

        try (ZipInputStream input = new ZipInputStream(
                new ByteArrayInputStream(sink.toByteArray()),
                StandardCharsets.UTF_8)) {
            ZipEntry read = input.getNextEntry();
            byte[] actual = input.readAllBytes();

            System.out.println("Method STORED: "
                    + (read.getMethod() == ZipEntry.STORED));
            System.out.println("Uncompressed size: " + read.getSize());
            System.out.println("Bytes match: "
                    + Arrays.equals(payload, actual));
            input.closeEntry();
        }
    }
}
```

Commands:

```bash
javac StoredEntryDemo.java
java StoredEntryDemo
```

**Stdout on success:**

```text
Method STORED: true
Uncompressed size: 4
Bytes match: true
```

The example demonstrates all steps required for a STORED entry:

1. Compute CRC32 over the payload before creating the entry.
2. Set `method=STORED`, size, compressed size, and CRC.
3. Call `putNextEntry` and write the exact declared byte count.
4. `closeEntry` finalizes the entry and verifies metadata.
5. Close the ZIP stream to finalize the archive.
6. Decompress back to bytes and compare contents.

If the data comes from an external source, **never compute CRC over a different copy of the data** and write a modified payload. A mismatched CRC or size can trigger `ZipException` when closing the entry.

## 12. Proper API Call Order in Real-World Scenarios

### 12.1. Multiple Files in One ZIP

```text
ZipOutputStream.open
  putNextEntry(file 1)
    write...
  closeEntry()
  putNextEntry(file 2)
    write...
  closeEntry()
  ...
ZipOutputStream.close()  => complete archive + closed sink
```

The most common case: use a `ZipOutputStream` inside `try-with-resources`, close entries explicitly, and let `close()` finalize the ZIP.

### 12.2. Caller Owns the OutputStream

```text
Caller creates OutputStream
  library creates ZipOutputStream(output)
    putNextEntry / write / closeEntry ...
    finish()
  return sink control to caller
Caller decides when to flush/close sink
```

Note that there must be a very clear convention regarding **closing ownership**. `ZipOutputStream.close()` is unsuitable if the caller requires the sink to stay open. Sometimes a non-closing wrapper can be used, but you must manage the deflater lifecycle and all I/O errors; never apply workarounds merely to avoid designing clear ownership.

### 12.3. Calling closeEntry Before Writing All Data

```text
putNextEntry("large.bin")
write(chunk 1)
closeEntry()
write(chunk 2)  <-- DOES NOT belong to large.bin; this is a workflow bug
```

After `closeEntry()`, the entry's content has ended. The program must read/write the **entire** payload before closing the entry. There is no standard API to resume appending to the same entry after closing it.

### 12.4. Input File Encounters IOException While Packaging

If reading a source file or writing the ZIP encounters an error before an entry is complete, **never silently ignore the error and publish the archive as valid**. The entry may be incomplete, or even if the central directory is written, that component's data will not represent the intended content.

Production rules should be:

1. Write the ZIP to a **temporary file**.
2. Use `try-with-resources` to guarantee closing the stream.
3. Once writing succeeds completely, **verify the archive if needed**.
4. Only on success, publish/rename the temporary file to the official name.
5. On error, discard the incomplete artifact per policy; never proceed using it as a successful archive.

When using `Files.move` with `ATOMIC_MOVE`, availability depends on the provider/filesystem; have a fallback plan when unsupported. Atomic publishing does not replace `fsync` or durability mechanisms when power-loss protection is required.

## 13. Is `closeEntry` Mandatory Before the Next `putNextEntry`?

Per the Java SE 17 API, `putNextEntry` **closes the current entry if it is still active**. Similarly, `finish()` is responsible for finishing the ZIP archive and can finalize an open entry.

Conceptual example:

```java
zip.putNextEntry(new ZipEntry("a.txt"));
zip.write(new byte[] {65});

// putNextEntry will close a.txt before opening b.txt.
zip.putNextEntry(new ZipEntry("b.txt"));
zip.write(new byte[] {66});

zip.finish();
```

This is an illustrative snippet using an existing `zip` variable. **Using this automatic behavior to hide state in code is discouraged.** Developers should close entries explicitly where data completes, and use `try-with-resources` to guarantee archive finalization.

Benefits of being explicit:
- Logging and written byte counts can be placed right alongside each entry.
- Entry CRC/size errors are easily attributed to the entry being processed.
- Clear separation between source read errors, ZIP write errors, and finalization errors.
- Easy to refactor into an `addEntry(zip, source)` helper with a clear contract.

`closeEntry()` and `close()` do not have the same scope of effect; confusing the two names breaks multi-file processing flows.

## 14. Writing Directory Entries and Safe Relative Paths

When creating an archive from a source directory, construct entry names **relative to the root directory**:

```java
Path root = Path.of("/source-folder").toAbsolutePath().normalize();
Path file = root.resolve("images/logo.png");
String entryName = root.relativize(file).toString().replace('\\', '/');
```

This is illustrative and will not run standalone on every OS since the example path must exist. The rule of converting `\\` to `/` helps maintain consistent ZIP entry naming.

However, **normalizing separators is not enough for security**. Never accept untrusted entry names and store them in a ZIP without validation:

- Avoid absolute names, `../` traversal, empty paths, and conflicting entries.
- Avoid embedding file names containing sensitive information or absolute server paths.
- Define a policy for symbolic links (skip, archive target contents, or represent the link specially).
- Never assume ZIP entries automatically carry compatible permission/mode metadata across all tools.

**When extracting ZIPs from others** (beyond the core ZIP-creation focus of this article), prevent **Zip Slip**: resolve the entry name under the target directory, normalize, verify it does not escape the permitted directory, and address symbolic links/TOCTOU according to your threat model. Also limit total decompressed size, entry count, and compression ratio to prevent zip bombs.

The goal in the ZIP-creation side is to assign clean entry names and avoid generating archives that are dangerous or hard to extract.

## 15. Charset, Compression Level, and Metadata

### 15.1. Charset for **Entry Names**

`ZipOutputStream(OutputStream out, Charset charset)` lets you choose how **entry names and comments** are encoded. For example:

```java
ZipOutputStream zip = new ZipOutputStream(
        output, StandardCharsets.UTF_8);
```

This is an illustrative snippet; `output` must be an open `OutputStream`.

**The charset in the constructor does not automatically encode file contents.** If you want to store UTF-8 text, encode the payload separately:

```java
zip.write("Tiếng Việt".getBytes(StandardCharsets.UTF_8));
```

When extracting text, the reading side must also use the exact charset of the **content**. Never equate the entry-name charset with each file's content charset.

### 15.2. `setLevel(int)` Only Controls Compression Level

`zip.setLevel(Deflater.BEST_COMPRESSION)` changes the compression level used for **subsequent DEFLATED** entries. It does not alter the decompressed content, does not turn ZIP into another format, and cannot make an archive "complete" before `finish/close`.

`ZipEntry.STORED` preserves raw data without compression; thus, the DEFLATE compression level has no effect on STORED entries.

### 15.3. Comments and Timestamps

`ZipEntry.setTime(long)` sets the modification timestamp. `ZipOutputStream.setComment(String)` sets the archive comment. Such metadata can affect ZIP bytes and build reproducibility.

In pipelines requiring **reproducible builds**, you must sort entry order and normalize metadata; never assume two ZIPs share identical bytes simply because their logical payloads match.

## 16. Notes for JAR and GZIP

- **JAR** is also based on ZIP. `JarOutputStream` extends `ZipOutputStream` and supports `putNextEntry`/`closeEntry` and `finish/close`. JAR has additional conventions such as `META-INF/MANIFEST.MF`, digital signatures, and metadata, so an arbitrary ZIP should not be treated as a compliant deployable JAR.
- **GZIP** is a different format, typically representing a single compressed stream rather than a multi-entry ZIP archive. `GZIPOutputStream` has `finish()`/`close()` but **does not have `putNextEntry(ZipEntry)`** like ZIP.

Do not confuse them:
- `ZipOutputStream`: multiple named entries, metadata, and a central directory.
- `GZIPOutputStream`: a GZIP compressed data stream without ZIP-style entry lists.
- `JarOutputStream`: ZIP with additional JAR conventions.

This distinction is important when choosing the right API: use ZIP/JAR to package multiple files into one archive; use GZIP or `DeflaterOutputStream` to compress a single raw data stream depending on the required format.

## 17. Common Mistakes and Fixes

| Mistake | Consequence or Cause | Fix |
| --- | --- | --- |
| Calling `write` before `putNextEntry` | No active entry to hold the data | Open an entry first |
| Calling `closeEntry` and assuming the ZIP is finished | Archive lacks its central directory | Call `finish()` or `close()` |
| Only calling `flush()` then publishing the ZIP | Stream may not have written ending structures | Finalize the ZIP before publishing |
| Calling `close()` then trying to add entries | Stream is already closed | Create a new archive or redesign the flow |
| Calling `finish()` then calling `putNextEntry` | Archive is already finalized | Only finish after the last entry |
| Closing zip inside a utility method when caller owns the sink | Sink closed unexpectedly | Clear ownership contract; use finish if sink must stay open |
| Forgetting `closeEntry` during consecutive writes | May auto-close on putNextEntry, but blurs lifecycle | Close entries explicitly after writing all data |
| Setting `STORED` without declaring size/CRC | `ZipException` | Compute and set before putNextEntry |
| Declaring wrong size or CRC | Error when closing/writing entry | Compute from actual bytes; ensure data stays unchanged |
| Reusing an entry name | Duplicate entry | Check name collisions before writing |
| Treating `folder/file.txt` as a full OS path | Non-standard, risks leaking host paths | Use relative paths with `/` |
| Assuming constructor charset encodes text payloads | Extracted text file has garbled encoding | Encode content explicitly with UTF-8 |
| Printing ZIP size and expecting it to be constant | Compression and metadata can vary | Verify entry counts/contents instead of byte length |
| Writing ZIP directly to the final artifact before success | Can leave a corrupted ZIP after errors | Write a temp file, verify, then publish |
| Reading one entry with ZipInputStream and concluding the ZIP is complete | Local entries can be read without a central directory | Finalize with finish/close and inspect with ZipFile when needed |

## 18. Self-Check Exercises

### Question 1. Two entries have called `closeEntry()`, but `finish()`/`close()` has not been called yet

Is `ZipFile` guaranteed to read the archive?

**No.** `closeEntry()` ends individual entries, while a ZIP archive normally requires the central directory and ending structures. `ZipFile` relies on consolidated metadata; the ZIP must be properly finalized.

### Question 2. `zip.finish()` was called when the sink is owned by the caller

Does the sink close automatically, and should `putNextEntry` be called afterward?

**No.** `finish()` does not close the underlying stream. However, the ZIP is already finalized, so no further entries should be written; the caller manages the sink per its contract.

### Question 3. Using `ZipEntry.STORED` with a known payload

Which metadata fields must be present?

Exact **size**, **compressed size** (equal to size), and **CRC-32** of the payload. If missing or mismatched with the data, `ZipException` may occur. CRC-32 does not replace cryptographic authentication.

### Question 4. Saving `src/docs/readme.txt` as entry `docs/readme.txt`

Is it mandatory to create a `docs/` entry beforehand?

Not mandatory for **all extraction tools** if you just want to extract the file into a logical directory; many tools create parent directories from file names. However, to represent an **empty directory** or control directory structure explicitly, adding an entry ending with `/` is standard practice.

### Question 5. Using `zip.close()` in try-with-resources: is calling `zip.finish()` beforehand required?

**Not required.** `close()` finalizes the ZIP and then closes the underlying stream. `finish()` is used when you want to finalize the archive while keeping the sink open, or need an explicit archive-end boundary.

### Question 6. Called `putNextEntry("x.txt")` and wrote multiple byte chunks

Should `closeEntry()` be called after each chunk?

**No.** All chunks of `x.txt` belong to the same open entry. Call `closeEntry()` **once after all data has been written**; closing early ends the entry's data.

### Question 7. ZipInputStream read `one.txt` from an unfinished ZIP byte stream

Can you conclude the ZIP is completely valid?

**No.** Reading a local entry does not prove the central directory and end-of-central-directory are valid. You must `finish` or `close` and verify the integrity of the whole archive according to application requirements.

## 19. Safe Packaging Checklist

Before starting:

- Determine **who owns the `OutputStream`** and who is responsible for calling `close`.
- Define **relative**, unique entry names compatible with the target extraction platform.
- Choose default `DEFLATED`, or `STORED` with accurately precomputed metadata.
- Determine the charset for entry names/comments and how text payloads are encoded.

When writing each entry:

- Call `putNextEntry(entry)`.
- Write the **complete** entry content before closing.
- Call `closeEntry()`, handling `IOException` and `ZipException`.
- Never conclude an archive is valid if an error occurred mid-stream.

When finalizing:

- Use `close()` / `try-with-resources` if the ZIP stream owns the sink.
- Use `finish()` if you must finalize the archive **while keeping the caller's sink open**.
- Never publish an incomplete ZIP file; for critical files, write to a temp file, verify, and then publish.
- When you need to inspect the complete entry list and consolidated structure, open with `ZipFile` after the ZIP has been finalized.
- When extracting untrusted data, enforce policies validating paths, sizes, entry counts, and resources.

## 20. Summary

**Three operations to remember by their exact scope:**

```text
putNextEntry(entry) -> start an entry
write(bytes)        -> write that entry's content
closeEntry()        -> end that entry

repeat for other entries

finish()            -> end the ENTIRE ZIP,
                       while keeping the underlying OutputStream open

or

close()             -> end the ENTIRE ZIP
                       and also close the underlying OutputStream
```

`putNextEntry` and `closeEntry` establish boundaries for individual files/directories inside a ZIP. `finish` establishes the end boundary of **the archive**, while `close` also manages the lifecycle of the underlying resource. Never conflate these three layers of responsibility. With a clear grasp of entry-level versus archive-level operations, you can write code that packages multiple files, cleans up resources properly, and avoids producing corrupted ZIPs or incomplete data.

**Official Reference Documentation for Java SE 17:**

- [ZipOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipOutputStream.html) — `putNextEntry`, `closeEntry`, `finish`, `close`.
- [ZipEntry](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipEntry.html) — name, method, size, CRC-32.
- [ZipFile](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipFile.html) — reading complete ZIPs with entry indexing.
- [ZipInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipInputStream.html) — reading entries sequentially.
- [JarOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/JarOutputStream.html) — ZIP-based JARs.
