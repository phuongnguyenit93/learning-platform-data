# Default character set and controlled data migration to UTF-8

During a Java upgrade, an application may compile successfully and still start normally yet begin misreading Vietnamese diacritics, producing garbled CSV characters, or exchanging data incompatibly with other systems. The cause often does not lie in string-processing algorithms, but in the **default character set** (*default charset*) used by the program when converting between bytes and characters.

Older Java versions typically obtained the default charset from the operating environment. Moving to a newer JDK can change the behavior of calls that do not declare a charset. Specifically, starting in Java 18, **JEP 400** directs UTF-8 to become the default charset for relevant Java SE APIs, whereas old applications may have been relying on an encoding such as Windows-1252, Windows-1258, or an encoding determined by OS settings. A seemingly small default change can affect files, messages, logs, HTTP, batch jobs, and long-lived stored data.

This lesson sits in the **Default behavior** chapter of the **Java Advance Compatibility Migration** module. The focus is not merely adding `StandardCharsets.UTF_8` to source code, but building a migration approach **with inventorying, source encoding identification, error control, comparative evidence, and a rollback plan**.

## 1. Learning objectives

After this lesson, learners can:

- Distinguish *bytes*, Unicode characters, `String`, and charsets when reading/writing data.
- Explain the impact of `Charset.defaultCharset()` and the default change starting in Java 18.
- Identify APIs implicitly using the default charset.
- Determine the source encoding of data and distinguish **reading legacy bytes correctly** from **writing new UTF-8**.
- Design a migration process with backups, decoding error checks, and recovery capability.
- Handle areas easily overlooked: `.properties`, console, CSV, logs, HTTP protocol, databases, and native integration.
- Write tests protecting Vietnamese data, special characters, BOMs, malformed data, and bidirectional flows.

## 2. Core of the issue: bytes and characters are not the same

### 2.1. `String` stores characters, files store bytes

In a Java program, a `String` object represents a sequence of Unicode characters according to Java's model. When writing a string to a file or transmitting over a network, the program must encode the string into bytes. When reading data back, the program must decode bytes into characters.

```text
Unicode characters in String
          |
          | encode using a specific charset
          v
        Byte[]
          |
          | write file / network transfer / store blob
          v
       Stored data

        Byte[]
          |
          | decode using a specific charset
          v
Unicode characters in String
```

A charset is the mapping rule between characters and bytes. If encoding and decoding use two incompatible charsets, data can become distorted even when the bytes themselves are still readable.

For example:

```java
String value = "Cà phê Việt Nam";

byte[] utf8 = value.getBytes(StandardCharsets.UTF_8);

String restored =
        new String(utf8, StandardCharsets.UTF_8);

System.out.println(restored);
```

When both sides agree on UTF-8, the string is restored accurately. If the same string is decoded using another encoding, the result may contain unintended characters.

### 2.2. Why do simple ASCII strings easily hide bugs?

Many common charsets use the same bytes for ASCII characters from `0x00` to `0x7F`. Therefore, tests containing only `Hello123` can pass even though the program uses the wrong charset.

Conversely, characters such as:

```text
Vietnamese:    Trường đại học, Nguyễn, dữ liệu
European:      café, naïve, résumé
Symbols:       €, ©, →, ✓
Supplementary: emoji or characters outside the Basic Multilingual Plane
```

help expose differences faster. Encoding migration test suites must contain the character groups that the system actually has to process, not only English data.

### 2.3. Encoding differs from Unicode normalization

UTF-8 is an *encoding*; NFC/NFD are **Unicode normalization** forms. Two strings can display identically yet have different code points or byte sequences.

For example, an accented character is sometimes represented by a precomposed code point or by a base character plus a combining mark. Converting bytes to UTF-8 does not automatically normalize to NFC.

In migration, distinguish:

- **Wrong charset:** bytes are decoded with an incorrect code page.
- **Mojibake:** strings display as wrong characters such as `Ã`, `Â`, or question marks due to one or more inconsistent encode/decode passes.
- **Wrong normalization:** different code points despite similar visual appearance.
- **Data loss:** characters were already replaced with `?` or `�` before migration.

Each type requires its own handling approach. Not every case can be fixed by “re-converting to UTF-8”.

## 3. How does the default charset change across Java versions?

### 3.1. Before Java 18: typically environment-dependent

In JDKs prior to Java 18, the default charset of many Java SE APIs could be chosen based on the operating system, locale, environment configuration, or how the JVM was launched.

For example, a program using:

```java
byte[] data = text.getBytes();
String decoded = new String(data);
```

implicitly used `Charset.defaultCharset()` for conversion. It might run correctly on a development machine yet break when running on another machine or container with a different default charset.

You should not assert that running on Windows always means charset X or Linux always means UTF-8. Actual results must be verified on the specific environment and JDK.

### 3.2. Java 18+: JEP 400 and UTF-8 by default

**JEP 400 (UTF-8 by Default)** was introduced starting in Java 18. For Java SE APIs within the scope of this change, the default charset is standardized to UTF-8, making behavior more consistent across platforms.

This has two sides:

- **Benefit:** new code depends less on the OS locale; UTF-8 data is handled more consistently.
- **Compatibility risk:** old code may implicitly assume the default charset is another encoding. When changing JDKs, the same `new String(bytes)` or `FileReader` may decode differently than before.

Not **every** text operation in Java switches to UTF-8 automatically. APIs with their own charset rules, communication protocols, `.properties` files, and console streams have specific characteristics and need separate verification.

### 3.3. Checking the default charset in use

You can log it in a test environment:

```java
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;

public final class CharsetDiagnostics {
    public static void main(String[] args) {
        System.out.println("Default charset: "
                + Charset.defaultCharset());
        System.out.println("file.encoding: "
                + System.getProperty("file.encoding"));
        System.out.println("native.encoding: "
                + System.getProperty("native.encoding"));
        System.out.println("UTF-8 available: "
                + Charset.isSupported(StandardCharsets.UTF_8.name()));
    }
}
```

Read the output together with JDK vendor/version and JVM arguments. `native.encoding` provides information about the platform encoding on JDKs that support this property; it does not mean every API uses that encoding.

If you need to observe operational behavior, measure with the actual program reading/writing representative files, rather than concluding completely from a single system property.

### 3.4. `file.encoding` should not be a long-term data control API

Some applications attempt to control the default charset with:

```bash
java -Dfile.encoding=UTF-8 -jar application.jar
```

Across JDKs before and after JEP 400, the rules and supported values of this property differ; Java 18+ has compatibility mechanisms such as `-Dfile.encoding=COMPAT` for the purpose of falling back to environment-based encoding selection in supported cases.

**Do not change `file.encoding` via `System.setProperty` while the application is running expecting every API to switch charsets immediately.** Initialization/caching behavior, the timing of charset selection, and per-JDK behavior may not meet that expectation.

Using a property like this, if unavoidable, should only be a **tested transitional solution**. The long-term solution is choosing the charset explicitly at data read/write boundaries.

### 3.5. Risk table by migration phase

| Phase | Behavior to watch | Risks |
| --- | --- | --- |
| Java 8–17 | Default charset of many APIs can depend on the environment. | Data is only right on one machine/locale; different containers misread it. |
| Java 18+ | UTF-8 becomes the default charset for JEP 400 APIs. | Old non-UTF-8 files are misread even though source did not change. |
| Changing JVM vendor/container | Locale, timezone, OS image, fonts, and external tool encodings may differ. | Logs, batch files, import/export, or terminals are inconsistent. |
| Switching to explicit encoding | Each flow uses the charset defined in the contract. | Source encoding must be accurately identified; do not assume all old data is UTF-8. |

## 4. APIs that easily use the default charset unintentionally

### 4.1. Converting between `String` and `byte[]`

**Implicit:**

```java
byte[] bytes = text.getBytes();
String value = new String(bytes);
```

**Explicit UTF-8:**

```java
byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
String value = new String(bytes, StandardCharsets.UTF_8);
```

If the input bytes are legacy data in another charset, replacing `new String(bytes)` with UTF-8 without checking the source will not make the data correct. The **read** charset must match the source data; the **write** charset must match the target contract.

### 4.2. Readers, Writers, and streams

Constructors that do not specify a charset, such as `new FileReader(file)`, `new FileWriter(file)`, `new InputStreamReader(in)`, and `new OutputStreamWriter(out)`, typically use the default charset.

Example of a stable read path:

```java
import java.io.BufferedReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path path = Path.of("data/input.txt");

try (BufferedReader reader =
        Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        System.out.println(line);
    }
}
```

Writing a file:

```java
try (var writer =
        Files.newBufferedWriter(path, StandardCharsets.UTF_8)) {
    writer.write("Dữ liệu UTF-8");
}
```

The helpers above clearly express the UTF-8 contract at the read/write site. If Java 8 must be supported, use `Paths.get(...)` and explicit variable type declarations instead of `Path.of` and `var`.

### 4.3. Some APIs **already** default to UTF-8

Not every API that omits a charset parameter uses `Charset.defaultCharset()`. For example:

- `Files.readString(Path)` / `Files.writeString(Path, ...)` (Java 11+) default to UTF-8.
- `Files.newBufferedReader(Path)` and `Files.newBufferedWriter(Path)` default to UTF-8.
- `Files.readAllLines(Path)` defaults to UTF-8.
- `Files.lines(Path)` defaults to UTF-8.

Therefore, you must read **each API's** contract. Do not apply a mechanical rule “omitting charset means using the default charset”.

For code needing explicit intent, the overload taking `StandardCharsets.UTF_8` is usually easier to audit.

### 4.4. `Scanner`, `PrintWriter`, `PrintStream`, and high-level I/O utilities

Some overloads of `Scanner`, `PrintWriter`, or `PrintStream` may choose the default charset according to the contract of the JDK in use. Other overloads allow declaring an explicit charset.

When auditing, do not search only for `new String`; inspect constructors, factories, wrappers, and third-party libraries that may perform reading/writing on behalf of the application.

## 5. Finding implicit charset usages in the repository

Source code search can be used as a first step:

```bash
rg -n 'new String\(|\.getBytes\(\)|new FileReader\(|new FileWriter\(|new InputStreamReader\(|new OutputStreamWriter\(' src
```

Find other read/write flows:

```bash
rg -n 'Scanner\(|PrintWriter\(|PrintStream\(|readAllBytes\(|Files\.readString\(|Files\.writeString\(|getProperty\("file.encoding"|Charset\.defaultCharset' .
```

Results are only **investigation points**, not certain bugs. Some calls require the default charset per system contract; some `new String` calls already pass a charset in another parameter; some libraries use explicit encodings not visible in application source.

For each point, record:

| Field | Must be determined |
| --- | --- |
| Byte source | File, network, database BLOB, clipboard, process output, queue, or plugin. |
| Source charset | Published value, configured value, or verified from original data. |
| Decode API | Method/constructor converting bytes to `String`. |
| Encode API | Method/constructor converting `String` to bytes. |
| Target charset | UTF-8, legacy charset, protocol-mandated charset, or binary (no conversion). |
| Data owner | Service, partner, batch system, or deployment team. |
| Environment | JDK/OS/container/locale where the flow runs. |
| Evidence | Byte samples, metadata, tests, protocol specifications, and logs. |

The goal is identifying **conversion boundaries** rather than replacing all calls with UTF-8 en masse.

## 6. Classifying data before converting to UTF-8

### 6.1. Plain text data

For example `.txt`, exported documents, or text logs. Can be read with the source charset and written as UTF-8 after verifying actual lines.

Attributes to record:

- Line ending style: LF, CRLF, or CR.
- Presence or absence of a BOM.
- Special characters or control characters.
- Original encoding and verification source.
- Filename conventions, timestamps, and access permissions.

### 6.2. Structured-format data

CSV, XML, HTML, JSON, YAML, and configuration files are all text yet have different **format contracts**.

For example, converting CSV bytes to UTF-8 must still preserve delimiters, quote escaping, column order, and newline representation. XML must stay consistent between actual bytes and the `encoding` in the XML declaration. HTML may specify the charset in HTTP headers or `meta` tags.

Do not treat structured formats as a byte string for arbitrary character find-and-replace. Use an appropriate parser/serializer if content transformation is needed.

### 6.3. Binary or mixed data

Images, PDFs, ZIPs, protobuf, encrypted payloads, compressed files, and database BLOBs are not arbitrary text. Do not “convert to UTF-8” these bytes.

Some formats contain both binary parts and text fields. You must use the format's parser to identify **the exact fields needing encoding conversion**, avoiding corrupting signatures, length fields, checksums, or binary structures.

### 6.4. Data with unknown encoding

Encoding cannot always be detected reliably from bytes alone. An ASCII byte sequence is also valid UTF-8 and may be valid in many other charsets.

Even when bytes are syntactically valid UTF-8, that **is not enough to prove** the author used UTF-8. Authoritative metadata must take priority: specifications, HTTP `Content-Type`, partner contracts, legacy system configuration, or confirmation from the data producer.

If there is not enough evidence, mark the status as *undetermined*, collect more samples, and do not overwrite original data.

## 7. Controlled conversion: decode source → encode target

### 7.1. Mistake: changing the output charset without knowing the input

Unsafe example:

```java
byte[] oldBytes = Files.readAllBytes(source);
String text = new String(oldBytes, StandardCharsets.UTF_8);
Files.write(target, text.getBytes(StandardCharsets.UTF_8));
```

If `oldBytes` was originally encoded in Windows-1258, using UTF-8 to decode can produce replacement characters or distorted data; writing UTF-8 afterward will **permanently save the corruption**.

Correct process:

```text
Source bytes (identified legacy charset)
             |
             | Decode using source charset
             v
   Correct Unicode characters
             |
             | Verify content, errors, special characters
             v
       Encode using UTF-8
             |
             v
   Target UTF-8 bytes and updated metadata
```

### 7.2. Simple example for legacy data with known encoding

If the source specification confirms ISO-8859-1:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path source = Path.of("legacy.txt");
Path target = Path.of("converted.txt");

byte[] originalBytes = Files.readAllBytes(source);
String content =
        new String(originalBytes, StandardCharsets.ISO_8859_1);

Files.write(target, content.getBytes(StandardCharsets.UTF_8));
```

This is an example of **conversion direction**, not how to auto-detect charsets. ISO-8859-1 is not suitable for fully encoding Vietnamese; it is only used when the source genuinely confirms that charset.

In legacy Vietnamese data systems, you may encounter Windows-1258, TCVN3/ABC, or VNI. **TCVN3 and VNI may require dedicated transcoders**; one cannot assume Java's `Charset.forName` directly supports every legacy convention. For Windows-1258, verify whether the specific JDK supports the charset and confirm sample data before using.

### 7.3. Why is strict decoding necessary?

Some convenience APIs like `new String(bytes, charset)` may replace invalid byte sequences with a replacement character instead of throwing an error. When converting data in bulk, this behavior is very dangerous: the tool may “succeed” while losing the ability to recover original characters.

When lossless conversion is required, use `CharsetDecoder` with:

- `CodingErrorAction.REPORT` for malformed input.
- `CodingErrorAction.REPORT` for unmappable characters during decoding.
- Separate error handling, without silently using `REPLACE` or `IGNORE`.

Example:

```java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.Charset;
import java.nio.charset.CharsetDecoder;
import java.nio.charset.CodingErrorAction;

static String decodeStrict(byte[] bytes, Charset source)
        throws java.nio.charset.CharacterCodingException {
    CharsetDecoder decoder = source.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT);

    CharBuffer chars = decoder.decode(ByteBuffer.wrap(bytes));
    return chars.toString();
}
```

If the decoder reports an error, keep the source file intact, log error positions/counts according to the tool's capabilities, and route that case to a separate handling flow. Do not fix malformed bytes automatically without an approved rule.

### 7.4. Example of file conversion with backup and temporary file writing

A simple process using Java 11+ can include:

```java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.Charset;
import java.nio.charset.CharsetDecoder;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

public final class SafeTextConverter {
    public static void convert(Path source, Path target, Charset sourceCharset)
            throws Exception {
        // Read source only, do not overwrite original file.
        byte[] raw = Files.readAllBytes(source);

        CharsetDecoder decoder = sourceCharset.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);

        CharBuffer chars = decoder.decode(ByteBuffer.wrap(raw));
        ByteBuffer utf8 = StandardCharsets.UTF_8.newEncoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .encode(chars);

        byte[] converted = new byte[utf8.remaining()];
        utf8.get(converted);

        Path absoluteTarget = target.toAbsolutePath();
        Path directory = absoluteTarget.getParent();
        Path temp = Files.createTempFile(directory, "utf8-", ".tmp");

        try {
            Files.write(temp, converted);
            // Do not replace an existing target file if not approved.
            Files.move(temp, absoluteTarget);
        } finally {
            Files.deleteIfExists(temp);
        }
    }
}
```

The code above is an **illustrative example** for the decode-then-encode and staging flow, not yet a complete migration utility. `Files.move(temp, target)` does not guarantee an atomic move on every filesystem; if atomicity and durability are required, you must check filesystem capabilities, concurrent write policies, fsync, file permissions, and recovery procedures. It also assumes enough RAM to hold the entire file; for large files, stream conversion with stateful decoders/encoders is needed, properly handling multibyte sequences across buffer boundaries.

In real migration, back up original data to an immutable or versioned location before running a batch. Do not use this code to automatically overwrite unapproved data in bulk.

### 7.5. Do not re-convert files that are already UTF-8

Before running a batch, each file/record needs a status:

| Status | Action |
| --- | --- |
| Source encoding confirmed as legacy | Decode source, validate, encode UTF-8. |
| Already valid UTF-8 | Keep unchanged or normalize metadata if needed; do not transform unnecessarily. |
| Encoding undetermined | Do not convert automatically; require verification. |
| Data already has mojibake | Investigate encode/decode history; do not apply the regular legacy-to-UTF-8 pipeline. |
| Data already lost characters | Restore from backup or source system if available; re-encoding cannot recover lost information. |
| Binary | Do not convert charset. |

Batches must be designed to be **idempotent**: re-running must not corrupt data a second time. A common approach is storing a manifest containing source, version, charset, checksum, status, and conversion result.

## 8. BOM, newlines, and Unicode normalization

### 8.1. BOM in UTF-8

UTF-8 can appear with a byte order mark `EF BB BF` at the beginning of a file. UTF-8 does not need a BOM to determine byte order, yet some old tools or systems use a BOM as an identification marker.

Some parsers can accept a BOM, while other applications treat it as a `U+FEFF` character at the start of the string and misparse headers, column names, or identifiers.

Before converting:

- Determine whether consumers require a BOM.
- Determine whether the source has a UTF-8, UTF-16LE, or UTF-16BE BOM.
- Do not simply strip three bytes `EF BB BF` if the file has not actually been confirmed as UTF-8.
- Do not automatically remove `U+FEFF` characters in the middle of content when they may carry data meaning.

### 8.2. Newlines and delimiters

Changing encoding does not necessarily mean changing newlines. If a job is outputting CRLF for an external system to read, switching to LF can change the contract even though every character displays properly.

For CSV, keep quote and delimiter rules intact; for TSV, check tab characters in data. Separate **charset** issues from other file structure changes for easier comparison and rollback.

### 8.3. Normalization

If the system needs to match Vietnamese strings with one another, it may be necessary to standardize Unicode normalization, such as NFC. However, **do not automatically normalize all data** in the same transcoding batch unless specifications require it, because that can alter code point sequences, checksums, or input data meaning.

Changing charsets and Unicode normalization are two independent decisions; each change needs separate testing.

## 9. System boundaries easily affected

### 9.1. CSV/Excel files

A batch system may export CSV for users to open with spreadsheet software. Consumers may rely on locale, BOM, or import configuration to interpret the encoding.

When switching to UTF-8:

- Agree on the encoding with the receiving party.
- Use explicit UTF-8 when generating files.
- Test opening/importing on the exact tool and version customers use.
- Determine whether a UTF-8 BOM is needed, instead of adding it automatically in every case.
- Test Vietnamese diacritics, delimiters, and line breaks inside cells.

A file being valid UTF-8 does not guarantee the receiving software selects UTF-8 automatically.

### 9.2. HTTP and APIs

For data transmitted over HTTP, charset is part of the **content contract** along with media type and headers. For example, `Content-Type: text/plain; charset=UTF-8` helps consumers determine how to decode.

Do not only change `getBytes()` code and ignore headers. Servers, clients, reverse proxies, and frameworks may apply different defaults per media type.

When sending JSON, use encoding rules of the protocol and supported JSON library; when sending forms or plain text, explicitly determine encoding per standards and partner contracts. Do not apply a single assumption across all protocols.

### 9.3. Databases

Databases have their own encoding, collation, and driver configuration. Java `String` is converted into wire/database data according to the driver and connection contract.

Points to review:

- Encoding of the database/schema/column.
- Charset and JDBC connection configuration.
- Whether data is genuinely stored as proper Unicode or only looks “right” because it was previously mis-decoded yet read back the same way.
- Whether CSV import/export or SQL dumps have an explicit charset.
- Whether collation, normalization, and string comparison change unexpectedly.

Changing `Charset.defaultCharset()` is not an operation that converts the encoding of an entire database. For BLOB data containing legacy text, you must know the charset of the BLOB content before converting.

### 9.4. Message queues and exchange files

If payloads are transmitted as `byte[]`, both producer and consumer need to agree on encoding. If the framework automatically serializes objects or JSON, check the serializer configuration.

A producer upgrading its JDK may start writing UTF-8 while an old consumer still reads with the old encoding. Therefore, deploy contracts/versioning before enabling changes, or support parallel handling via an agreed mechanism.

### 9.5. Console, stdout, stderr, and logs

The encoding of terminals, consoles, or output streams can differ from `Charset.defaultCharset()` depending on JDK, OS, and how the JVM is launched. Do not infer that every `System.out.println` line will automatically match container log files.

Check separately:

- Developer interactive console.
- Output redirected to files.
- Output of a Java process read by another program via `ProcessBuilder`.
- Log files created by the logging framework.
- Logs collected and displayed by the container/logging platform.

If the application writes text log files, configure the logging framework's encoder/file appender with an explicit charset. If reading stdout of another process, determine the encoding that process actually outputs.

### 9.6. Native integration

JNI/JNA or external programs may use string/byte types per platform conventions. Do not apply UTF-8 to a native API whose contract specifies another encoding.

With `ProcessBuilder`, Java launches external commands yet does not automatically convert stdout/stderr content into valid UTF-8 for every program. When reading streams, determine the process's charset in the actual environment.

## 10. Important exceptions: Properties and ResourceBundle

### 10.1. `Properties.load(InputStream)` does not use the default charset in the usual way

`java.util.Properties.load(InputStream)` has its own rule: bytes in the stream are read as ISO-8859-1, with characters outside that range representable by Unicode escapes in the corresponding properties format.

For example:

```java
Properties config = new Properties();

try (InputStream in = Files.newInputStream(Path.of("legacy.properties"))) {
    config.load(in);
}
```

Do not think that simply because the JVM default charset is UTF-8, the code above automatically reads `.properties` as UTF-8. The rule of the `InputStream` overload remains independent of `Charset.defaultCharset()`.

If the file specification confirms UTF-8, the `Reader` overload can be used:

```java
Properties config = new Properties();

try (Reader reader = Files.newBufferedReader(
        Path.of("utf8.properties"), StandardCharsets.UTF_8)) {
    config.load(reader);
}
```

Consider both the creation and consumption processes of properties; an old file with escape sequences is not identical to a raw UTF-8 text file in every situation.

### 10.2. ResourceBundle property files

How `ResourceBundle` handles property resources has its own rules per JDK and changed starting in Java 9. When upgrading from Java 8, check resource bundles packaged in JARs, especially files containing Vietnamese or non-ASCII characters.

Do not infer from `Charset.defaultCharset()`. Check the contract of the target Java version and any encoding control properties if present; run tests with the actual resources, locale, and class loader.

### 10.3. Source file encoding and runtime charset are two different issues

The compiler reads `.java` files based on its configuration, whereas the program at runtime reads/writes business files according to runtime APIs.

A project may compile UTF-8 source successfully yet misprocess input data because `FileReader` uses an unintended default charset.

With Maven/Gradle, configure source and resource encoding appropriately; with plain `javac`, `-encoding UTF-8` can be used for source code. This does not automatically change the encoding of business files the app reads after deployment.

## 11. Testing migration across an environment matrix

### 11.1. Designing tests with distinguishing characters

A sample dataset should contain:

```text
ASCII:          Hello 123
Vietnamese:     Hà Nội, Đà Nẵng, Cần Thơ, Nguyễn
Accented:       tiếng Việt, dữ liệu, kiểm thử
Symbols:        €, £, ©, →, ✓
Outside BMP:    an emoji character matching the contract
Special edges:  blank line, newline, tab, double quote
```

If the system does not support a character group, document the contract limitation explicitly instead of silently losing characters.

### 11.2. Checking both bytes and content

Do not only compare strings displayed on a terminal. You need to verify:

1. Input bytes and checksum before conversion.
2. Source charset identified by evidence.
3. Whether strict decoding produced any errors.
4. Whether Unicode content matches the expected sample.
5. Whether target bytes are valid UTF-8 and match the contract.
6. Whether data preserves its meaning after an actual consumer reads it.

You can inspect file bytes with hex viewer tools. Do not use a terminal decoding in the wrong encoding to assert the original file is corrupt.

### 11.3. Testing with different default charsets

Build a test matrix across supported environments:

| Test case | JDK/environment | Input | Expected result |
| --- | --- | --- | --- |
| Baseline | Old JDK, current locale | Real legacy file | Record current output and bytes. |
| New JDK | Target JDK with default configuration | Same legacy file | Result decoded using explicit source charset. |
| Standard UTF-8 | Target JDK | Valid UTF-8 file | No character changes. |
| Malformed data | Target JDK | Bytes invalid for declared charset | Report error and keep source intact. |
| Already converted | Target JDK | UTF-8 file with manifest | Not re-converted in a way that causes distortion. |
| Integration | New producer, current consumer | Message/file/API | Consumer receives exact characters and metadata. |

If the application must run on multiple JDKs or operating systems, test on those environments within the supported scope. **Explicit charset configuration** is an important way to reduce dependence on the environment matrix.

### 11.4. Example unit test for UTF-8

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;

class Utf8RoundTripTest {
    @Test
    void preservesVietnameseCharacters() {
        String original = "Đà Nẵng – dữ liệu UTF-8";
        byte[] encoded = original.getBytes(StandardCharsets.UTF_8);
        String decoded =
                new String(encoded, StandardCharsets.UTF_8);

        assertEquals(original, decoded);
    }
}
```

The test above protects a basic round-trip flow. **It is not enough** to confirm legacy data conversion logic: if the source decoder is wrong yet subsequent encode/decode both err in the same way, the new round trip can still pass. Migration tests should use pre-known legacy byte fixtures and expected Unicode confirmed by the data source.

## 12. Controlled roadmap for migrating data to UTF-8

### Step 1: Capture the baseline

Record JDK vendor/version, actual default charset, source encoding configuration, OS/locale, container image, JVM arguments, and the list of data read/write boundaries.

Save real byte samples, checksums, and current results of critical flows. Create backups before making changes.

### Step 2: Inventory sources and owners

Find APIs using implicit charsets, legacy file storage systems, batch jobs, and external data exchange flows. Associate each source with an owner and published contract.

Do not equate “text in the source repository” with “every business file”.

### Step 3: Identify source charsets

Prioritize source documentation and metadata. If byte analysis is needed, combine multiple samples and owner input. Do not let heuristic tools decide automatically for the entire dataset.

Undetermined files must go into a pending queue and must not be converted silently.

### Step 4: Standardize UTF-8 contracts at system boundaries

Before modifying batch converters, agree on which consumers receive UTF-8, whether formats need a BOM, which headers must change, and how parallel transition is supported.

For APIs and message queues, prepare both producer and consumer; do not upgrade only one side and expect all sides to auto-detect the new charset.

### Step 5: Change I/O code to explicit charsets

Replace places relying implicitly on the default charset with reading in the **source charset** and writing in the **target charset**. For new data flows with a UTF-8 contract, use `StandardCharsets.UTF_8`.

Clearly separate APIs with their own rules such as `Properties.load(InputStream)`, `ResourceBundle`, and console output.

### Step 6: Test conversion on a copy

Run batches on staging with copied data. Decode strictly, save error reports, check output bytes, compare business content, and test feeding into real consumers.

Avoid running directly on production data on the first attempt.

### Step 7: Create a manifest and rollback mechanism

A manifest can contain:

| Attribute | Example meaning |
| --- | --- |
| Dataset / file ID | Stable identifier of source data. |
| Source encoding | Verified value. |
| Target encoding | `UTF-8`. |
| Source checksum | Detects whether the source changed between runs. |
| Backup location | Restore location, with access permissions. |
| Conversion version | Version of the tool/algorithm used. |
| Converted checksum | Verifies output matches the version. |
| Status | Pending, converted, validated, quarantined. |
| Validation evidence | Tests, samples, confirming person. |

Rollback capability must rely on backups or immutable originals, not on always being able to reverse-convert data whose characters have already been replaced.

### Step 8: Partial rollout and monitoring

Prioritize a canary or small dataset. Measure decode errors, number of quarantined files, number of errored records, consumer read success rate, and character display incidents.

Once results stabilize, expand in limited batches, avoiding modifying all data at once in a way that is hard to recover.

### Step 9: Finalize contracts and remove workarounds

After conversion, update API/file format documentation, source encoding in builds, import/export examples, and operations runbooks. If `-Dfile.encoding=COMPAT` was used as a transitional step, plan its removal once implicit-dependency flows are resolved.

## 13. Common errors and diagnostics

| Symptom | Possible cause | Investigation step |
| --- | --- | --- |
| Vietnamese characters become `Ã...` or strange strings | UTF-8 was decoded with another charset, or repeatedly mis-decoded/encoded. | Inspect raw bytes, conversion history, source/target encodings. |
| Characters become `?` | Encoder could not represent the character and used replacement. | Check the code page on the first write; find the original backup. |
| Character `�` appears | Decoder used replacement for invalid bytes. | Find the original byte source and enable strict decoding. |
| File reads right on dev machine yet wrong on server | Default charset differs between environments. | Log `Charset.defaultCharset()` and audit APIs without charsets. |
| CSV shows garbled diacritics when opened in Excel | Consumer picks another encoding or expects BOM/import options. | Test with the exact target tool, agree on UTF-8/BOM. |
| `.properties` file has wrong Vietnamese | Used wrong overload or misunderstood charset rules. | Check `load(InputStream)` vs `load(Reader)`. |
| XML/HTML reports wrong encoding | Declaration/header mismatches bytes. | Check metadata and actual bytes. |
| Container logs are wrong yet output file is right | Console/collector charset differs from file encoder. | Check stdout, appender, collector, terminal. |
| Data remains wrong after writing UTF-8 | In-memory string was already mis-decoded previously. | Check the very first decode step; not only the encode step. |
| Second conversion batch corrupts files | Status not tracked, not idempotent. | Add manifest, checksums, and block repeated conversion. |

An important principle: **do not fix characters displaying incorrectly before identifying the raw bytes at the boundary causing the error**. If the error is at the terminal rather than the file, converting the file will create further problems.

## 14. Performance and large data

Examples like `Files.readAllBytes` fit small files or practice exercises, yet reading GBs of data into RAM can cause memory pressure or `OutOfMemoryError`.

For large data, use:

- `InputStream` combined with `InputStreamReader` having a strictly configured `CharsetDecoder`.
- `OutputStream` combined with `OutputStreamWriter` using UTF-8.
- Appropriate buffers and proper handling of multibyte byte sequences across buffer boundaries.
- Temporary file writing, checkpoints, checksums, and idempotent retries.
- Partitioning batches by file or record to isolate errors.

If converting via `Reader`/`Writer`, check BOM policies, newlines, and how invalid input is handled. Measure throughput with representative data yet do not sacrifice error checking for speed.

## 15. Checklist for completing charset migration

- [ ] Distinguished byte-level encoding from Unicode text and normalization.
- [ ] Recorded default charsets of the old JDK and target JDK in real environments.
- [ ] Identified the impact of JEP 400 if migrating to Java 18+.
- [ ] Reviewed `new String(byte[])`, `getBytes()`, Reader/Writer calls, and I/O libraries.
- [ ] Confirmed APIs with their own charset rules instead of assuming default charset.
- [ ] Inventoried files, APIs, queues, logs, database import/export, and native integration.
- [ ] Determined source charsets using metadata or reliable evidence.
- [ ] Classified data into already-UTF-8, legacy, undetermined, mojibake, and binary.
- [ ] Have backups, checksums, manifest, dry run, and a rollback plan.
- [ ] Used strict decoders or an approved error policy, without silent character replacement.
- [ ] Confirmed BOM, newlines, delimiters, and file/protocol metadata.
- [ ] Tested Vietnamese data, special characters, malformed data, and converted files.
- [ ] Verified real consumers read UTF-8 accurately, not just encode/decode unit tests.
- [ ] Standardized contracts and removed default charset workarounds when safe.

## 16. Conclusion

Default charset is an **environmental behavior**, not a reliable data contract for systems that must run across different Java versions and platforms. With Java 18+, UTF-8 becomes the default for APIs within JEP 400's scope, yet data created from older JDKs can still use other charsets and cannot be fixed merely by changing the default charset.

The sustainable migration path is explicitly defining charsets at every byte–text boundary, **decoding with a verified source charset, encoding target output as UTF-8, controlling errors, and preserving originals**, and then testing on actual consumers. When encoding information becomes part of the contract and operational workflow, the application depends less on JDK default changes and Java upgrades become more predictable.
