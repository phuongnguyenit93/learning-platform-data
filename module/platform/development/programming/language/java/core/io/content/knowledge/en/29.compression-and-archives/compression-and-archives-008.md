# `JarFile`, `JarInputStream`, and `Manifest` at the Java I/O Level

## 1. Goal: Reading a JAR File as a ZIP Archive with Metadata

A JAR (*Java ARchive*) is a ZIP-based archive format: it contains multiple entries with names such as `com/example/App.class`, `config/settings.properties`, and `docs/readme.txt`, and may contain the metadata file `META-INF/MANIFEST.MF`. When working at the **I/O level**, a program does not necessarily need to load classes or execute the JAR; it may simply need to list entries, fetch resources, read the manifest, inspect entry metadata, and close streams properly.

Three common classes:

- **`java.util.jar.JarFile`**: opens an **existing JAR file on the filesystem**, looks up entries by name, iterates entries, and opens an `InputStream` per entry; extends `java.util.zip.ZipFile`.
- **`java.util.jar.JarInputStream`**: reads a JAR **sequentially from an `InputStream`**; extends `java.util.zip.ZipInputStream`. Suitable when the source is streamed data without a randomly accessible file.
- **`java.util.jar.Manifest`**: data model for `META-INF/MANIFEST.MF`, consisting of **main attributes** and **per-entry attributes**. This is metadata about the archive and specific entries, not the contents of every file inside the JAR.

This article focuses on Java SE 17+ APIs at the I/O layer: proper reading, manifest placement, entry/stream lifecycles, performance comparisons, and security boundaries. Concepts around class loading, launchers, and JAR signatures are covered only insofar as needed to avoid incorrect inferences from I/O data.

## 2. What Does a JAR Look Like?

An archive may contain:

```text
sample.jar
├── META-INF/
│   └── MANIFEST.MF
├── com/example/Main.class
├── docs/
│   └── readme.txt
└── config/
    └── app.properties
```

"Directories" inside a JAR are usually entries whose names end with `/` (e.g., `docs/`). Not every parent path is required to have its own directory entry; `docs/readme.txt` can exist without a `docs/` entry.

Example manifest contents:

```text
Manifest-Version: 1.0
Main-Class: com.example.Main
Created-By: Example

Name: docs/readme.txt
X-Role: documentation

```

Meaning:

- `Manifest-Version`: manifest format version attribute.
- `Main-Class`: main class name used when the JAR is executed by a supporting launcher; the value is a Java class name syntax, not a `.class` entry path inside the ZIP.
- `Created-By`: example metadata attribute supplied by the JAR creation tool.
- `Name: docs/readme.txt` starts **a per-entry section**; the `X-Role` attribute beneath it belongs to that file's section, not to main attributes.

Blank lines separate sections. The manifest format has specific rules for line endings, encoding, and line-wrapping continuation for long values; to produce valid manifests, use the `Manifest` class rather than concatenating raw strings arbitrarily. Entry names in the manifest associate metadata with matching entries; **the presence of a section does not prove the archive contains that entry**, and an ordinary entry may have no dedicated metadata section.

## 3. Comparing `JarFile` and `JarInputStream`

| Criterion | `JarFile` | `JarInputStream` |
| --- | --- | --- |
| API base | extends `ZipFile` | extends `ZipInputStream` |
| Input | File/JAR openable as a file | Any suitable `InputStream` |
| Traversal style | Lookup entries by name, enumerate entries | Sequential reading via `getNextJarEntry()` |
| Reading manifest | `getManifest()`, can locate manifest anywhere in archive | `getManifest()` **provided manifest is at the start of the stream** |
| Reading entry content | `jar.getInputStream(entry)` | Read `jarInput.read(...)` on the current entry |
| Moving to another entry | Look up new entry independently | `getNextJarEntry()` advances to the next entry |
| Unsaved network/pipe source | Requires a suitable file copy of the JAR first | Can consume the stream directly |
| Resource management | Close `JarFile` and entry streams | Close `JarInputStream` wrapping the source |
| Can access second entry before first? | Yes, via `getJarEntry(name)` | No; data is read sequentially |

**Do not confuse "random access" with arbitrary byte modification.** `JarFile` supports *looking up and opening streams by entry name* without sequentially reading all preceding entries, yet it remains an **archive-reading** API, not a `RandomAccessFile` for arbitrarily mutating ZIP bytes. To create a JAR or modify contents, use `JarOutputStream`/packaging tools and rebuild the archive appropriately.

A JAR may contain entries compressed with `DEFLATED` or uncompressed with `STORED`. When reading entries, the API returns **decompressed content bytes**, not the compressed byte sequence inside the archive.

## 4. `JarFile`: Looking Up and Reading Entries by Name

Common API usage:

```java
try (JarFile jar = new JarFile(jarPath.toFile())) {
    Manifest manifest = jar.getManifest(); // may be null
    JarEntry entry = jar.getJarEntry("docs/readme.txt");

    if (entry != null && !entry.isDirectory()) {
        try (InputStream in = jar.getInputStream(entry)) {
            byte[] bytes = in.readAllBytes();
            // Only use readAllBytes() if data size is already bounded!
        }
    }
}
```

This is a snippet, **not a standalone program**; it requires a valid `Path jarPath`, imports for `JarFile`, `JarEntry`, `Manifest`, and `InputStream`, and `IOException` handling.

### How Do `getJarEntry(name)` and `getEntry(name)` Differ?

- `JarFile.getJarEntry(String name)` returns a `JarEntry` or `null` if not found.
- `JarFile.getEntry(String name)` returns a `ZipEntry` or `null`; `JarEntry` is an extended entry subtype of `ZipEntry`.
- `jar.entries()` returns `Enumeration<JarEntry>` to iterate entries. You can also use `jar.stream()` to get an entry stream as supported by `ZipFile`.
- `jar.getInputStream(entry)` opens a stream to **read the contents of the identified entry**.

Avoid confusing `JarFile.getInputStream(entry)` with reading from a `JarInputStream` positioned at its current entry. With `JarFile`, you can select `docs/readme.txt` first and `config/app.properties` second, independent of the physical ZIP layout. With `JarInputStream`, reaching an entry near the end requires walking through all earlier entries in stream order.

### Reading in Chunks Instead of Unbounded RAM Loading

`InputStream.readAllBytes()` in the snippet is suitable for small files with application-controlled limits. For JARs from untrusted sources or resources that could be very large:

```java
byte[] block = new byte[8192];
long total = 0;
int n;
while ((n = in.read(block)) != -1) {
    total += n;
    if (total > MAX_ALLOWED_BYTES) {
        throw new IOException("Entry too large");
    }
    // Send block[0..n) to a streaming processor.
}
```

This snippet requires `in`, `MAX_ALLOWED_BYTES`, and a program-defined handler. In real code, also bound throughput, entry count, total decompressed bytes, and processing time; avoid arithmetic overflow by checking remaining headroom before adding when necessary.

## 5. `JarInputStream`: Sequential Traversal and Reading the Current Entry

Created from an input stream:

```java
try (JarInputStream jis =
        new JarInputStream(Files.newInputStream(jarPath))) {

    Manifest manifest = jis.getManifest();

    JarEntry entry;
    while ((entry = jis.getNextJarEntry()) != null) {
        System.out.println("entry=" + entry.getName());

        if (!entry.isDirectory()) {
            byte[] bytes = jis.readAllBytes();
            // Only use this when the file has a small/strictly bounded size.
        }

        jis.closeEntry();
    }
}
```

This snippet requires imports and `IOException` handling. `getNextJarEntry()` advances to the start of the next entry and returns `null` at the end of the archive. While positioned at an entry, `jis.read(...)` reads **that entry's decompressed bytes**. At the end of an entry, `read` returns `-1` for the current entry; that does not mean the entire JAR has ended — call `getNextJarEntry()` to get the next entry.

**Never** wrap a `new JarInputStream` per entry around the same input stream expecting to rewind to the start of the JAR; the stream has already advanced forward. If re-reading is needed, the source must be recreatable (or saved to a file and opened with `JarFile`).

### What Does `closeEntry()` Do?

`closeEntry()` finishes reading the current entry, skips any unconsumed content bytes of that entry if present, and prepares to transition. `getNextJarEntry()` also handles advancing to the next entry per the ZIP stream contract. In flows performing signature or integrity verification, **reading the entire entry** gives verification/integrity checks a chance to complete; never assume reading only headers suffices to validate all content.

### `JarInputStream` Does Not Create Separate `InputStream`s per Entry

`JarInputStream` **itself is** the stream reading the current entry. You do not call `jis.getInputStream(entry)` as with `JarFile`. To separate each entry's content, copy the entry's bytes to a sink or process them right while positioned at that entry.

## 6. `Manifest`: Main Attributes and Per-Entry Attributes

Key APIs to remember:

| API | Return Value / Meaning |
| --- | --- |
| `jar.getManifest()` | `Manifest`, or `null` if the archive has no manifest |
| `jis.getManifest()` | `Manifest` when found at a valid start position, or `null` |
| `manifest.getMainAttributes()` | `Attributes` of the main section |
| `manifest.getEntries()` | `Map<String, Attributes>` containing sections keyed by entry name |
| `manifest.getAttributes("docs/readme.txt")` | `Attributes` of the specified section, or `null` |
| `attrs.getValue(Attributes.Name.MAIN_CLASS)` | Attribute value keyed by `Attributes.Name`, or `null` |
| `attrs.getValue("X-Role")` | Attribute value by string name, or `null` |

Example:

```java
Manifest manifest = jar.getManifest();
if (manifest != null) {
    Attributes main = manifest.getMainAttributes();

    String version = main.getValue(Attributes.Name.MANIFEST_VERSION);
    String mainClass = main.getValue(Attributes.Name.MAIN_CLASS);

    Attributes docs = manifest.getAttributes("docs/readme.txt");
    String role = docs == null ? null : docs.getValue("X-Role");
}
```

This snippet assumes `jar` is a valid `JarFile`. **`Manifest.getEntries()` does not list every file in the JAR**: it only lists sections that have metadata entries in the manifest. To list archive entries, use `JarFile.entries()` or `JarInputStream.getNextJarEntry()`.

Similarly, **`Main-Class` is metadata**, not proof that the named class actually exists, declares a proper `public static void main(String[])`, or that the JAR will run with `java -jar`. To verify, inspect the archive and launch behavior as required.

Section name keys normally use ZIP entry paths with `/`, not host absolute paths. Never pass entry names straight into an external `Path` without validating the destination.

## 7. Crucial Distinction: Manifest Placement for `JarInputStream`

Not every file named `META-INF/MANIFEST.MF` anywhere in an archive is automatically recognized by `JarInputStream.getManifest()`.

Per the Java 17 API contract:

- `JarInputStream.getManifest()` returns the manifest if `META-INF/MANIFEST.MF` is the **first entry** in the ZIP/JAR stream.
- Or if the first entry is the `META-INF/` directory and the **second entry** is `META-INF/MANIFEST.MF`.
- If the manifest sits elsewhere, `getManifest()` **is not guaranteed to locate/read it** as the leading stream manifest. Nor should you rely on whether later positions are skipped or returned as regular entries.

When the manifest is properly at the start, `getNextJarEntry()` / `getNextEntry()` **skips the manifest entry** already consumed by the constructor; if the first entry is `META-INF/` followed by the manifest, both are skipped during normal entry iteration.

Diagram:

```text
JAR A:
  META-INF/
  META-INF/MANIFEST.MF
  docs/readme.txt
             ^
  getManifest() reads metadata;
  getNextJarEntry() starts at docs/readme.txt

JAR B:
  docs/readme.txt
  META-INF/MANIFEST.MF
             ^
  Never assume getManifest() will read a manifest appearing later!
```

By contrast, `JarFile` reads the archive structure like a ZIP file and can access the manifest entry by name; `getManifest()` does not depend on entries appearing at the front of the stream as `JarInputStream` does.

**How to create a JAR in the right order:** use `new JarOutputStream(output, manifest)`. This constructor writes the manifest entry early per the API contract, enabling `JarInputStream` to obtain `Manifest` in learning examples. When creating JARs with external tools, check packaging order if stream-based consumers require the manifest at the front.

## 8. Complete Java 17+ Example: Creating and Reading a JAR with Both APIs

The following program creates a temporary JAR from Java with a manifest and two small content files. It then reads the same archive two ways to show **entry lookup by name** with `JarFile` and **sequential traversal** with `JarInputStream`.

Save as **`JarFileVsInputStreamDemo.java`**:

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.jar.Attributes;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;
import java.util.jar.JarInputStream;
import java.util.jar.JarOutputStream;
import java.util.jar.Manifest;

public class JarFileVsInputStreamDemo {
    private static void addFile(
            JarOutputStream out, String name, String content)
            throws IOException {
        JarEntry entry = new JarEntry(name);
        out.putNextEntry(entry);
        out.write(content.getBytes(StandardCharsets.UTF_8));
        out.closeEntry();
    }

    public static void main(String[] args) throws Exception {
        Path path = Files.createTempFile("jar-io-demo-", ".jar");

        try {
            Manifest manifest = new Manifest();
            Attributes main = manifest.getMainAttributes();
            main.put(Attributes.Name.MANIFEST_VERSION, "1.0");
            main.put(Attributes.Name.MAIN_CLASS, "example.Main");

            Attributes document = new Attributes();
            document.putValue("X-Role", "documentation");
            manifest.getEntries().put("docs/readme.txt", document);

            try (JarOutputStream out = new JarOutputStream(
                    Files.newOutputStream(path), manifest)) {
                addFile(out, "docs/readme.txt", "HELLO");
                addFile(out, "config/app.properties", "mode=demo\n");
            }

            // APPROACH A: JarFile supports looking up entries by name.
            try (JarFile jar = new JarFile(path.toFile())) {
                Manifest meta = jar.getManifest();
                System.out.println("jarfile-main="
                        + meta.getMainAttributes().getValue(
                                Attributes.Name.MAIN_CLASS));

                JarEntry readme = jar.getJarEntry("docs/readme.txt");
                try (InputStream in = jar.getInputStream(readme)) {
                    System.out.println("jarfile-readme="
                            + new String(in.readAllBytes(),
                                    StandardCharsets.UTF_8));
                }

                Attributes perEntry =
                        meta.getAttributes("docs/readme.txt");
                System.out.println("jarfile-role="
                        + perEntry.getValue("X-Role"));

                System.out.println("jarfile-config="
                        + (jar.getJarEntry("config/app.properties") != null));
            }

            // APPROACH B: JarInputStream only reads entries sequentially.
            try (JarInputStream stream = new JarInputStream(
                    Files.newInputStream(path))) {
                Manifest meta = stream.getManifest();
                System.out.println("stream-main="
                        + meta.getMainAttributes().getValue(
                                Attributes.Name.MAIN_CLASS));

                List<String> names = new ArrayList<>();
                JarEntry entry;
                while ((entry = stream.getNextJarEntry()) != null) {
                    if (!entry.isDirectory()) {
                        names.add(entry.getName());
                        // Only because the example has two very small files.
                        byte[] content = stream.readAllBytes();
                        if (entry.getName().equals("docs/readme.txt")) {
                            System.out.println("stream-readme="
                                    + new String(content,
                                            StandardCharsets.UTF_8));
                        }
                    }
                    stream.closeEntry();
                }

                Collections.sort(names); // do not rely on ZIP order
                System.out.println("stream-files=" + names);
            }
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
```

Compile and run commands:

```bash
javac JarFileVsInputStreamDemo.java
java JarFileVsInputStreamDemo
```

**Stdout when file creation/reading succeeds (Java 17+):**

```text
jarfile-main=example.Main
jarfile-readme=HELLO
jarfile-role=documentation
jarfile-config=true
stream-main=example.Main
stream-readme=HELLO
stream-files=[config/app.properties, docs/readme.txt]
```

What happens in sequence?

1. `Manifest` is built with the official API; `Manifest-Version` is `1.0` and `Main-Class` is `example.Main`.
2. `manifest.getEntries()` contains a dedicated section for `docs/readme.txt` with metadata `X-Role=documentation`.
3. `JarOutputStream` receives the manifest upon construction and writes the required entries; the program then adds two small content files.
4. `JarFile` retrieves the manifest without scanning entries sequentially, then looks up `docs/readme.txt` and reads its UTF-8 bytes. It also checks whether another entry exists.
5. `JarInputStream` reads the leading manifest, then `getNextJarEntry()` sequentially reads the file entries; it does not need or offer instant lookup by name. The list is sorted **before printing** to avoid depending on archive metadata/entry order.
6. `JarInputStream.readAllBytes()` inside the loop reads **the current entry's content**, not swallowing all remaining entries. Because the example contains only a few bytes, `readAllBytes()` is acceptable; for untrusted JARs, read in blocks and enforce limits.
7. Both readers and entry streams are closed properly before deleting the temporary file.

Having `Main-Class: example.Main` in this JAR **does not** make it a runnable Java application: the sample JAR does not contain `example/Main.class`. The example tests **reading metadata at the I/O layer**, not `java -jar`.

## 9. When the Source Is a Network or Single-Pass Stream

For example, suppose you receive JAR data from an HTTP response body `InputStream`, or a file unwrapped from another layer:

```java
try (JarInputStream jar = new JarInputStream(responseBody)) {
    JarEntry entry;
    while ((entry = jar.getNextJarEntry()) != null) {
        if (!entry.isDirectory()) {
            // Process bytes of the current entry's content here.
        }
        jar.closeEntry();
    }
}
```

This snippet is **not standalone**: `responseBody` is an application-provided `InputStream`, and `IOException` handling is required. Important points:

- `JarInputStream` reads sequentially, fitting cases where you cannot seek backward or do not want to persist the full archive to disk first.
- Closing `JarInputStream` closes the underlying source stream. If the HTTP client still needs the stream for another purpose, establish clear ownership.
- Just because bytes arrive from the network does not mean the full JAR was received. If the connection drops midway, code must handle `IOException`, unexpected EOF, and integrity checks as required.
- If you need fast repeated lookups of an entry near the end of the archive, consider **writing to a size-bounded temporary file** and using `JarFile`; never copy an unbounded input stream into RAM just to reopen it.
- The manifest **can be `null`** even if the archive is a valid ZIP, especially when no manifest sits at the proper leading position.

When spooling a stream to a temp file, avoid trusting a sender-supplied filename to build paths outside allowed directories, and cap total bytes received.

## 10. `JarEntry` Metadata: What Can Be Read and What Might Be Missing?

`JarEntry` extends `ZipEntry`, so it provides:

| API | Meaning / Note |
| --- | --- |
| `getName()` | Logical path of the entry inside the archive |
| `isDirectory()` | True for directory entries (usually name ends with `/`) |
| `getSize()` | Decompressed size if known; may be `-1` |
| `getCompressedSize()` | Compressed data size if known; may be `-1` |
| `getCrc()` | CRC-32 if known; may be `-1` |
| `getMethod()` | ZIP compression method (usually `STORED` or `DEFLATED`) |
| `getTime()` | Modification time if present; details depend on archive metadata |
| `getComment()` | Entry comment if present |
| `getAttributes()` | Main? **No**: this is an API of `Manifest`, not `JarEntry` |
| `getCertificates()` / `getCodeSigners()` | Signature metadata after reading and verifying full content; may be `null` |

Special note: there is no `JarEntry.getAttributes()` method to return a manifest section. To get per-entry metadata, use `Manifest.getAttributes(entry.getName())`; meanwhile, `getCertificates()/getCodeSigners()` relate to signatures if the JAR is signed and entry verification has occurred.

Entry `size` or `compressedSize` values are archive metadata, **not an absolute safety bound**. When streaming an untrusted archive, sizes may be unknown before reading finishes, or headers may be insufficient to protect against decompressing massive payloads. Always count **actual decompressed bytes** and enforce limits while reading.

## 11. Verifying JAR Signatures Does Not Mean Trusting the Publisher

Java supports signed JARs and signature-related metadata. Some `JarFile` constructors take a `verify` flag; `JarInputStream` also has overloads taking `boolean verify`.

Key points:

1. `verify=true` requests signature verification when content is read under supported conditions; it **does not** mean the entire archive has already been verified the moment the constructor returns.
2. For a signed entry, `getCertificates()/getCodeSigners()` metadata is typically populated only after **reading the entire entry content and completing verification**.
3. An unsigned JAR may have `getCertificates() == null` or `getCodeSigners() == null`, even though reading succeeds.
4. **Signature verification / digest checks do not automatically confirm a trusted publisher**. Applications must enforce certificate trust policies, certificate chains, expiration, and signer identity rather than merely checking "signers present".
5. With `JarInputStream`, signed JAR processing also depends on the manifest being in the right leading position and signature entries appearing in proper order. Do not extrapolate signed-JAR verification as a guarantee for out-of-order packaged JARs.
6. `JarFile` supports signature processing when using the API properly; however, read errors, corrupted entries, or signature verification failures must be treated as errors and never silently ignored.

Snippet verifying an entry has been read completely:

```java
try (JarFile jar = new JarFile(file, true)) {
    JarEntry entry = jar.getJarEntry("docs/readme.txt");
    if (entry == null) {
        throw new IOException("Entry not found");
    }

    try (InputStream in = jar.getInputStream(entry)) {
        in.transferTo(OutputStream.nullOutputStream());
    }

    // If the jar is properly signed, only after reading the entire entry
    // is signer/certificate metadata available to inspect.
    var signers = entry.getCodeSigners();
    // signers == null does not prove the JAR is malicious;
    // signers != null does not yet prove the publisher is trusted.
}
```

This snippet is **not standalone**: `file` is a `File`, requiring imports for `JarFile`/`JarEntry`/`InputStream`/`OutputStream`/`IOException` and security-policy handling. The snippet makes no trust decision and does not verify signatures of all entries when reading only one entry.

When handling plug-ins or artifacts downloaded from untrusted sources, establish a dedicated trust policy workflow (checksum/digest over a trusted channel, signatures and chain validation, repository signing, sandboxing, permissions). `JarFile`/`JarInputStream` are only I/O and API-contract verification tools, not a complete trust-management system.

## 12. `Manifest` and Multi-Release JARs

Java 9+ supports **multi-release JARs**, which can hold versioned classes/resources:

```text
META-INF/MANIFEST.MF
com/example/Lib.class
META-INF/versions/9/com/example/Lib.class
META-INF/versions/17/com/example/Lib.class
```

The manifest's main attributes may contain:

```text
Multi-Release: true
```

This allows supporting runtime mechanisms to select versioned entries where supported by the API. `JarFile` provides constructors/methods for selecting a multi-release archive version (e.g., overloads taking `Runtime.Version`), and views of physical vs. logical entries may differ by configuration.

**Never** equate `JarInputStream` with a runtime class loader: it walks **physical stream entries**, without promising to pick entries for your target Java version. When a program simply wants to inspect archive bytes, decide whether the goal is to inspect **physically stored entries** or a **versioned view**. Use documented `JarFile` overloads when multi-release semantics are explicitly needed.

In the earlier example, the manifest has no `Multi-Release` attribute, so version selection does not arise. Do not add multi-release complexity to a simple task reading `docs/readme.txt` when unnecessary.

## 13. Other Enumeration Approaches

### Iterating with `JarFile.entries()`

```java
try (JarFile jar = new JarFile(path.toFile())) {
    var entries = jar.entries();
    while (entries.hasMoreElements()) {
        JarEntry entry = entries.nextElement();
        if (!entry.isDirectory()) {
            System.out.println(entry.getName());
        }
    }
}
```

This snippet requires `Path path` and imports; iteration order **is not guaranteed to be sorted by name**. If deterministic output is required, collect entry names and call `Collections.sort(...)` before printing.

### Iterating with `JarInputStream` and Byte Limits

```java
JarEntry entry;
while ((entry = jis.getNextJarEntry()) != null) {
    if (entry.isDirectory()) {
        jis.closeEntry();
        continue;
    }

    long bytesForThisEntry = 0;
    int count;
    byte[] chunk = new byte[8192];
    while ((count = jis.read(chunk)) != -1) {
        bytesForThisEntry += count;
        if (bytesForThisEntry > limitPerEntry) {
            throw new IOException("Entry too large");
        }
        // Process chunk[0..count) within bounded limits.
    }

    jis.closeEntry();
}
```

This snippet assumes `jis` and `limitPerEntry` are declared. For malicious archives, also limit **total decompressed size, entry count, and processing time**. Never rely solely on `getSize()`.

## 14. Reading Metadata Without "Extracting" to the Filesystem

Not every task needs to extract a JAR into real files on disk:

- Reading `config/app.properties`: look up the `JarEntry` or scan the stream, open the content `InputStream`, and pass it to `Properties.load` if formatted accordingly.
- Reading `docs/readme.txt`: read bytes and decode text using an explicit charset.
- Checking build version: read a main or per-entry attribute from `Manifest` if present.
- Listing resources: iterate entry names without creating unnecessary temporary files.
- Checking whether an entry exists: `JarFile.getJarEntry("...") != null`.

If the goal is merely looking up a known resource in an archive on disk, `JarFile` is usually simpler than extracting everything. If the archive arrives from a single-pass stream, `JarInputStream` avoids writing to disk but requires sequential traversal.

### Reading `Properties` from an Entry

```java
try (JarFile jar = new JarFile(jarPath.toFile())) {
    JarEntry entry = jar.getJarEntry("config/app.properties");
    if (entry == null) {
        throw new IOException("Missing config entry");
    }

    Properties props = new Properties();
    try (InputStream in = jar.getInputStream(entry)) {
        props.load(in);
    }

    String mode = props.getProperty("mode");
}
```

This snippet requires `jarPath` and imports. `Properties.load(InputStream)` follows properties-file encoding rules; it is not automatically equivalent to a UTF-8 parser for all raw characters in the file. If data is defined as UTF-8, wrap in a `Reader` with `StandardCharsets.UTF_8` and call `Properties.load(Reader)`.

In the `JarFileVsInputStreamDemo` example, `config/app.properties` contains only ASCII `mode=demo`, so no encoding discrepancy arises.

## 15. Never Use Untrusted Entry Names for Unchecked Extraction

A JAR can contain unsafe entry names, such as:

```text
../outside.txt
../../etc/config
/absolute/path.txt
dir/../../escape.txt
```

If a program converts `entry.getName()` directly into a `Path` beneath the destination directory and writes files, it risks **Zip Slip / path traversal**: files may be written outside the intended directory.

Initial validation check:

```java
Path root = extractionDir.toAbsolutePath().normalize();
Path target = root.resolve(entry.getName()).normalize();

if (!target.startsWith(root)) {
    throw new IOException("Entry escapes extraction directory");
}
```

This is a snippet, not a complete secure extraction routine: `extractionDir` and `entry` must be declared. Additionally check:

- Absolute entry paths, directory traversal, and OS-invalid filenames.
- **Symbolic links** already existing in the target directory can cause the real path to diverge from the lexical path. `normalize()` and `startsWith(root)` do not fully protect against symlinks/race conditions; extract into a fresh directory with proper permissions, safe path-opening checks, and a policy forbidding symlinks where necessary.
- Limits on total decompressed bytes, path depth, entry count, time, and quotas.
- Entries with identical names or names colliding after normalization; never silently overwrite user files.
- CRC errors, malformed ZIP structures, and entries capable of excessive resource consumption.
- Never launch code inside a newly received JAR merely because manifest metadata lists a `Main-Class`.

If you only need to read metadata/entries in memory, skipping disk extraction avoids part of the path-traversal risk, yet resource limits during decompression remain essential.

## 16. Resource Lifecycles and I/O Errors

### With `JarFile`

`JarFile` holds resources associated with the opened ZIP file. Use `try-with-resources` to close `JarFile`. Entry `InputStream`s should also be closed after use. Never save an entry stream, close `JarFile` first, and expect that stream to keep reading normally.

### With `JarInputStream`

`JarInputStream` wraps an underlying `InputStream`. Closing `JarInputStream` closes the underlying stream via `FilterInputStream` semantics, so only grant ownership if closing the source is genuinely intended.

Never share a single `JarInputStream` across multiple concurrent reader threads without coordination: entry position and decompression state are strictly sequential. If two entries must be read independently, `JarFile` with separate entry streams is usually more appropriate, though you must still manage `JarFile` lifetime and application-level thread safety.

### Common Errors

- `IOException`: filesystem read failure, unexpected EOF, corrupted archive, or provider refusal.
- `ZipException` (subclass of `IOException`): invalid ZIP structure, CRC mismatch, or decompression error.
- `SecurityException` in certain signed-JAR verification, permission, or security-policy scenarios.
- `NullPointerException` can happen if you call `jar.getInputStream(jar.getJarEntry(name))` when the entry does not exist; check for `null` first.
- `jar.getManifest() == null` is **normal** for a JAR without a manifest; never assume one always exists.
- `entry.isDirectory() == true` means the entry describes a directory; never try to decode it as a text resource.
- `jarInput.getNextJarEntry() == null` is the condition indicating no more entries remain, distinct from `read() == -1` for **the current entry**.

When reading archives from external sources, never treat an exception as an "empty file" and ignore it; handle errors appropriately according to data safety requirements.

## 17. Another Small Example: Reading a `Manifest` from an In-Memory JAR

If you only have a `byte[]` representing a JAR (for instance, just generated in memory by an API), `JarInputStream` works directly with `ByteArrayInputStream`.

Save **`InMemoryJarDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.jar.Attributes;
import java.util.jar.JarEntry;
import java.util.jar.JarInputStream;
import java.util.jar.JarOutputStream;
import java.util.jar.Manifest;

public class InMemoryJarDemo {
    public static void main(String[] args) throws Exception {
        Manifest m = new Manifest();
        m.getMainAttributes().put(
                Attributes.Name.MANIFEST_VERSION, "1.0");
        m.getMainAttributes().putValue("X-Label", "memory-demo");

        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (JarOutputStream out = new JarOutputStream(bytes, m)) {
            out.putNextEntry(new JarEntry("hello.txt"));
            out.write("OK".getBytes(StandardCharsets.US_ASCII));
            out.closeEntry();
        }

        try (JarInputStream input = new JarInputStream(
                new ByteArrayInputStream(bytes.toByteArray()))) {
            Manifest manifest = input.getManifest();
            System.out.println("label="
                    + manifest.getMainAttributes().getValue("X-Label"));

            JarEntry entry = input.getNextJarEntry();
            System.out.println("entry=" + entry.getName());
            System.out.println("content="
                    + new String(input.readAllBytes(),
                            StandardCharsets.US_ASCII));
            input.closeEntry();

            System.out.println("next=" + input.getNextJarEntry());
        }
    }
}
```

Run:

```bash
javac InMemoryJarDemo.java
java InMemoryJarDemo
```

Stdout on success:

```text
label=memory-demo
entry=hello.txt
content=OK
next=null
```

This example **needs no temporary file**. `JarOutputStream(bytes, manifest)` wrote the manifest in the leading position expected by `JarInputStream`, followed by a single content entry added by the application. `getNextJarEntry()` after reading `hello.txt` returns `null` when no entries remain. `ByteArrayOutputStream` does not lose bytes upon `close()`; however, for large JARs, materializing a `byte[]` for the entire archive consumes heavy RAM, so prefer streaming or files as needed.

## 18. Selection and Practice Checklist

When implementing JAR-reading logic, ask yourself in order:

1. **Where is the source?** If a file, `JarFile` suits lookup; if a single-pass stream, `JarInputStream` suits sequential reading.
2. **Do you need only metadata or content bytes?** Read `Manifest` if only attributes are needed; use entry `InputStream`/`JarInputStream.read` if payloads are needed.
3. **Is the manifest guaranteed to be at the start of the stream?** With `JarInputStream`, this determines whether `getManifest()` succeeds.
4. **Do you need to iterate all entries?** With `JarFile` you can look up directly by name; a sequential stream must walk in order.
5. **Are you handling untrusted files?** Limit entry count, decompressed bytes, temp disk usage, and processing time; validate paths when extracting.
6. **Are signatures required?** Read entries completely to finalize verification and enforce an independent trust policy rather than checking only `Main-Class`/`signers`.
7. **Is it a multi-release JAR?** Decide whether you want physical entries or a versioned view and choose the appropriate API/overload.
8. **Who closes resources?** `try-with-resources` for `JarFile`, each entry stream, and `JarInputStream`. Never close the archive while code is still reading entries.
9. **What is the charset?** Bytes inside an entry do not default to UTF-8 or text; only decode with a charset when specified by the format.
10. **What should be tested?** JARs with and without manifests, early/late manifests, missing entries, directory entries, UTF-8 text, corrupted archives, large compressed entries, null metadata, and signed JARs if signatures are used.

## 19. Self-Check Exercises

1. Why can `JarFile` open `config/app.properties` without reading all of `docs/readme.txt` first?
2. When using `JarInputStream`, which API advances to the next entry? Which API reads bytes of the current entry?
3. When `JarInputStream.read()` returns `-1` for an entry, can you conclude the entire archive has ended?
4. Why can `JarInputStream.getManifest()` return `null` even if the archive contains `META-INF/MANIFEST.MF` at a later position?
5. Does `Manifest.getEntries()` list all `.class` files and resources in the JAR? Which API should you use?
6. Is `Main-Class` enough to prove a JAR will run with `java -jar`?
7. How does `Manifest.getAttributes("docs/readme.txt")` differ from `Manifest.getMainAttributes()`?
8. Why must `JarFile` be closed after closing its entry `InputStream`s?
9. When receiving a 2 GB JAR over the network, why are `Files.readAllBytes` or unbounded `JarInputStream.readAllBytes` on entries risky?
10. What does `entry.getSize() == -1` mean? Should you blindly trust sizes provided by ZIP headers for untrusted data?
11. When can `JarEntry.getCodeSigners()` contain signature data, and why does `signers != null` still not prove a trusted source?
12. Does `JarInputStream` automatically select `META-INF/versions/17` entries like a class loader for multi-release JARs?
13. If a ZIP entry is named `../secrets.txt` and a program extracts to disk, what risk must be prevented? Is `Path.normalize()` alone enough against symlinks?
14. Run the two practice programs, compare stdout, and modify `JarFileVsInputStreamDemo` to add an `images/icon.bin` entry. Why shouldn't an image file be force-decoded as text?
15. If an application checks only for the existence of `META-INF/MANIFEST.MF` without checking `Manifest-Version` or manifest formatting, what assumptions can fail?

## 20. Java SE 17 Documentation

- [`JarFile` — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/JarFile.html): entry access, manifests, multi-release, and signatures.
- [`JarInputStream` — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/JarInputStream.html): sequential reading, `getManifest()`, `getNextJarEntry()`.
- [`JarEntry` — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/JarEntry.html): entry metadata, certificates, and code signers.
- [`Manifest` — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/Manifest.html): main/per-entry attributes.
- [`JarOutputStream` — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/JarOutputStream.html): creating archives and adding manifests.
- [`ZipFile` and `ZipInputStream` — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/package-summary.html): ZIP format foundation and entry semantics.

## 21. Remember

**`JarFile`** opens a JAR on the filesystem, looks up entries by name, and issues streams to read individual entries; **`JarInputStream`** reads an archive sequentially from an `InputStream`. **`Manifest`** is metadata at `META-INF/MANIFEST.MF` comprising main attributes and per-entry attributes, not a list of every file.

When using `JarInputStream`, placing the manifest **at the start of the archive** is critical for `getManifest()` to work per contract; a manifest recognized at the front will not appear again as a regular entry via `getNextJarEntry()`. Always check for `null`, distinguish entry EOF from archive EOF, bound decompressed bytes, close resources in proper order, and never equate reading a manifest or signature with executing or trusting JAR contents.
