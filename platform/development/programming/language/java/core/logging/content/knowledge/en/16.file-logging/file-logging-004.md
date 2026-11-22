# File Encoding in Java Logging

## 1. What Is File Encoding?

**File encoding** is the way characters in a log message are converted into bytes stored on disk. In Java, text data is typically handled as a **String**; when a Logger emits an event, a Handler or Appender chooses a text format and then writes it out as bytes using a **Charset** such as UTF-8.

Example message:

~~~text
INFO | Đăng nhập thành công ở Đà Nẵng 🌿
~~~

The message can be written accurately to a UTF-8 file, but if a reader opens it with an incompatible character encoding, Vietnamese diacritics may turn into garbled characters. This phenomenon is commonly called **mojibake**.

Encoding errors do more than make logs hard to read. They can also:
- Cause search engines to fail to match keywords or names.
- Cause CSV parsers, JSON lines parsers, or log collection systems to misinterpret data.
- Create discrepancies between Windows, Linux, container, and CI environments.
- Make snapshot comparisons, exception analysis, or cross-service correlation unreliable.
- Lead to character loss if a decoding or encoding step silently replaces invalid data.

**Goal:** Choose an explicit encoding at the **writer**, ensure the **reader** uses the same encoding, and verify both the **actual bytes** and the **decoded text**. For modern text log files, UTF-8 is usually the right choice.

## 2. Charset, Formatter, Encoder, and FileHandler

It is important to distinguish the layers in the pipeline:

~~~text
Java String / Throwable / metadata
              |
              v
Logger emits event
              |
              v
LogRecord (JUL) or logging event (other backend)
              |
              v
Formatter / Layout -> produces formatted string
              |
              v
Charset Encoder -> converts characters to bytes
              |
              v
FileHandler / FileAppender -> writes bytes to file
              |
              v
File on disk -> collector / decoder / parser -> readable content
~~~

In practice, the internal call order varies by backend, but **the two decisions remain separate**: formatting the message and encoding it into bytes.

| Concept | Role |
| --- | --- |
| **String / Unicode** | Character data inside the program |
| **Charset** | Mapping rules between characters and bytes, e.g., UTF-8 |
| **Encoder** | Converts text into bytes |
| **Decoder** | Converts bytes back into text |
| **Formatter (JUL)** | Produces the display string from a LogRecord |
| **Layout / Encoder (Logback, Log4j 2)** | Defines event structure and can configure the output Charset |
| **Handler / Appender** | Responsible for writing events to a destination, such as a file or console |

**Encoding is not encryption.** UTF-8 ensures characters are represented correctly; it does not hide or securely encrypt data. Log files containing tokens or payment information still require redaction, access control, and storage protection.

## 3. Why Is UTF-8 Commonly Used?

**UTF-8** is a Unicode encoding that uses a variable number of bytes per character. It offers several benefits for log files:

- Supports Vietnamese characters, characters from other languages, and emojis.
- Common ASCII characters have byte representations identical to ASCII.
- Works well with JSON, many parsers, container log collectors, and operational tools.
- Reduces dependence on operating system locale or code pages.
- Simplifies standardizing pipelines across multiple services.

However, **one character does not necessarily equal one byte**. For example:
- An ASCII character is usually one UTF-8 byte.
- Vietnamese characters with diacritics may require multiple bytes.
- An emoji such as **🌿** is stored using four UTF-8 bytes, while in a Java String it may require two UTF-16 code units.

Therefore, **String.length() is not the file size**. When calculating storage capacity or file rotation limits, you must measure actual bytes.

### Other Charsets

| Charset | Characteristics | Risks for Logs |
| --- | --- | --- |
| **UTF-8** | Unicode, standard for text/JSON | Requires the reader to decode using UTF-8 as well |
| **UTF-16LE / UTF-16BE** | Based on two bytes for most code units | Many line-based text tools assume UTF-8 or ASCII |
| **UTF-16** | Has byte-order rules, may use a BOM | Must understand endianness and reader support |
| **ISO-8859-1** | Single-byte encoding with a limited character set | Cannot fully represent Vietnamese characters or emojis |
| **windows-1252** | Legacy encoding | Not UTF-8 and does not cover all of Unicode |
| **Charset.defaultCharset()** | Default charset at runtime | Not a portable contract across all Java versions and environments |

When working with a legacy file in an older charset, you must identify its **actual charset** before converting. Simply "opening as UTF-8 and saving again" cannot recover data that was already decoded incorrectly.

## 4. File Logging in Java Util Logging (JUL)

JUL is built into the JDK and uses **java.util.logging.Logger**, **LogRecord**, and **FileHandler**. FileHandler receives records, uses a Formatter to produce text, and writes to a file.

Basic configuration example:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.logging.FileHandler;
import java.util.logging.SimpleFormatter;

// Illustration placed inside a method that handles IOException.
FileHandler file = new FileHandler("logs/application.log", true);
file.setEncoding(StandardCharsets.UTF_8.name());
file.setFormatter(new SimpleFormatter());
file.setLevel(java.util.logging.Level.INFO);
logger.addHandler(file);
~~~

The snippet above is **not a standalone program**. It assumes the **logger** variable already exists, the **logs** directory exists, and the method handles IOException. In a real application, you must detach the Handler and call **close()** on shutdown following the proper lifecycle.

Meaning:
- **FileHandler(pattern, append):** Opens a file by the chosen name or pattern.
- **setEncoding("UTF-8"):** Configures the encoding for output data.
- **setFormatter(...):** Selects how records are formatted, independent of the Charset.
- **setLevel(...):** Limits the event level accepted by the Handler.
- **Logger.addHandler(...):** Connects the log source to the file destination.
- **Handler.close():** Finishes writing, flushes, and releases associated resources.

If no Formatter is specified, **FileHandler defaults to XMLFormatter**. This explains why beginners may see an XML file instead of the desired single-line log format. Setting UTF-8 does not turn XML into single-line text; you must choose an appropriate Formatter.

**Do not change the charset mid-way while appending to the same file.** If the first half of a file uses encoding A and the second half uses encoding B, readers typically cannot tell how to decode each part. When changing encodings, switch to a new file or follow a rotation/migration plan.

## 5. Standalone Java 17 Example: Writing a UTF-8 File and Verifying Bytes

This example uses only JDK 17 standard libraries, with no Maven or external dependencies. The code:

1. Creates a temporary directory.
2. Creates a FileHandler that writes UTF-8 to a file in that directory.
3. Logs a string containing Vietnamese characters and an emoji.
4. Closes the Handler and reads back the stored bytes.
5. Compares the bytes against the expected UTF-8 bytes.
6. Decodes using **CharsetDecoder** in strict error-reporting mode.
7. Verifies that the start of the file has no UTF-8 BOM.
8. Prints easily verifiable results, then cleans up the temporary files.

Create **Utf8FileLoggingDemo.java**:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.logging.FileHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class Utf8FileLoggingDemo {
    private static final Logger LOG =
            Logger.getLogger("demo.file.Utf8FileLoggingDemo");

    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("utf8-file-log-");
        Path path = dir.resolve("application.log");

        String message = "event=ORDER_CREATED text=Chào Đà Nẵng 🌿";
        String expected = "INFO | " + message + "\n";

        FileHandler file = new FileHandler(path.toString(), false);
        file.setEncoding(StandardCharsets.UTF_8.name());
        file.setLevel(Level.INFO);
        file.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName()
                        + " | " + formatMessage(record) + "\n";
            }
        });

        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);
        LOG.addHandler(file);

        try {
            LOG.info(message);
        } finally {
            LOG.removeHandler(file);
            file.close();
        }

        byte[] actualBytes = Files.readAllBytes(path);
        byte[] expectedBytes =
                expected.getBytes(StandardCharsets.UTF_8);

        String decoded = StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(actualBytes))
                .toString();

        boolean bom = actualBytes.length >= 3
                && (actualBytes[0] & 0xff) == 0xef
                && (actualBytes[1] & 0xff) == 0xbb
                && (actualBytes[2] & 0xff) == 0xbf;

        System.out.println(
                "UTF8_BYTES_MATCH="
                + Arrays.equals(actualBytes, expectedBytes));
        System.out.println(
                "DECODED_TEXT_MATCH=" + expected.equals(decoded));
        System.out.println("UTF8_BOM_PRESENT=" + bom);

        Files.deleteIfExists(path);
        Files.deleteIfExists(dir);
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac -encoding UTF-8 Utf8FileLoggingDemo.java
java Utf8FileLoggingDemo
~~~

**Expected stdout:**

~~~text
UTF8_BYTES_MATCH=true
DECODED_TEXT_MATCH=true
UTF8_BOM_PRESENT=false
~~~

### Why Are the Results Consistent?

- The source file is read accurately with **javac -encoding UTF-8** for Vietnamese characters and emojis.
- FileHandler is explicitly configured with **UTF-8**, independent of the default charset.
- The custom Formatter outputs only **INFO | message** and an **LF** character, without adding a variable timestamp.
- The Logger is at INFO and does not forward to parent handlers, so no default logs leak to stdout.
- FileHandler writes only to the file; the three stdout lines are the program's verification output.
- Closing the Handler before reading the file prevents buffered content from being missed.
- Byte-by-byte comparison detects encoding errors even when an editor auto-corrects display rendering.
- The Decoder in **REPORT** mode does not silently replace invalid UTF-8 bytes with the **�** character.
- UTF-8 in this configuration does not emit a BOM, so the result is **false**.
- Using a temporary directory avoids hardcoded paths and prevents colliding with other applications' log files.

**Note:** This example intentionally writes a single line. In production, a Formatter typically includes a timestamp, logger name, thread, exception, and request/trace ID; the encoding and byte verification principles apply the same way.

## 6. UTF-8 via JUL's logging.properties

When configuring JUL via a **logging.properties** file, you can set the FileHandler encoding without calling setEncoding in every class:

~~~properties
handlers = java.util.logging.FileHandler
.level = INFO

java.util.logging.FileHandler.pattern = logs/application-%u.%g.log
java.util.logging.FileHandler.limit = 10485760
java.util.logging.FileHandler.count = 3
java.util.logging.FileHandler.append = true
java.util.logging.FileHandler.level = INFO

java.util.logging.FileHandler.encoding = UTF-8
java.util.logging.FileHandler.formatter = java.util.logging.SimpleFormatter
java.util.logging.SimpleFormatter.format = %1$tFT%1$tT%1$tz | %4$s | %3$s | %5$s%6$s%n
~~~

These properties are **java.util.logging configuration** and do not apply to Logback or Log4j 2.

Explanation:
- **FileHandler.encoding:** Charset used when writing the file.
- **FileHandler.formatter:** Formatter class that produces the LogRecord content.
- **FileHandler.pattern:** File location and naming pattern.
- **limit/count:** Size limit in bytes and number of rotating files.
- **append:** Enables appending to an existing file, so the existing file must share the same format/charset.
- **SimpleFormatter.format:** Content pattern; it does not determine encoding.

Ensure the **logs** path is writable or replace it with a path suitable for your deployment environment. For a compiled application with class **com.example.Main**:

~~~bash
java -Djava.util.logging.config.file=logging.properties -cp out com.example.Main
~~~

This is a **sample command**, not the command to run Utf8FileLoggingDemo, which creates its FileHandler in code.

### Why Distinguish Formatter from Encoding?

A file using SimpleFormatter can be UTF-8 encoded. A file using XMLFormatter can also be UTF-8 encoded. The two files have **different formats** but the same **charset**. Therefore, when encountering garbled Vietnamese diacritics, check the encoding before replacing the entire Formatter.

Conversely, switching from XML to plain text in the same appended file can leave the content without a single consistent structure. Use a new file or trigger a rollover when changing formats.

## 7. File Encoding in SLF4J + Logback

**SLF4J is an API** and does not decide file bytes itself. With the **Logback** backend, encoding is typically configured on the **Encoder** of FileAppender or RollingFileAppender.

Example **logback.xml**:

~~~xml
<configuration>
    <appender name="FILE"
              class="ch.qos.logback.core.FileAppender">
        <file>logs/application.log</file>
        <append>true</append>
        <encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
            <charset>UTF-8</charset>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS,UTC} %-5level %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="FILE"/>
    </root>
</configuration>
~~~

- **FileAppender** opens the target file.
- **PatternLayoutEncoder** produces text output according to the pattern.
- **charset=UTF-8** determines how text is converted into bytes.
- **root INFO** allows matching events to reach the appender.
- **%msg** holds the message and **%n** emits a newline.

The XML file must be on the runtime classpath, and the project must include a compatible Logback provider. This configuration does not apply to plain JUL.

### RollingFileAppender and Charset

When using **RollingFileAppender**, the encoder still determines the charset. Renaming a file or compressing it as **.gz** does not turn UTF-8 into a different charset. Compressed archives must be decompressed before reading the text bytes.

~~~xml
<appender name="FILE"
          class="ch.qos.logback.core.rolling.RollingFileAppender">
    <file>logs/application.log</file>
    <rollingPolicy
        class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
        <fileNamePattern>logs/archive/application.%d{yyyy-MM-dd}.%i.log.gz</fileNamePattern>
        <maxFileSize>10MB</maxFileSize>
        <maxHistory>7</maxHistory>
        <totalSizeCap>1GB</totalSizeCap>
    </rollingPolicy>
    <encoder>
        <charset>UTF-8</charset>
        <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level %logger - %msg%n</pattern>
    </encoder>
</appender>
~~~

This is a **partial** configuration; you must attach an appender-ref to the appropriate root or logger. The numbers shown are illustrative. Size limits use file bytes, not String.length(). Before changing the encoding of an appender that appends to an existing file, deploy across a new file/rollover boundary to avoid mixing charsets.

## 8. File Encoding in Log4j 2

Log4j 2 typically uses a **Layout** to format and encode data. Example **log4j2.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration>
    <Appenders>
        <File name="FILE"
              fileName="logs/application.log"
              append="true">
            <PatternLayout
                charset="UTF-8"
                pattern="%d{ISO8601} %-5p %c - %m%n"/>
        </File>
    </Appenders>

    <Loggers>
        <Root level="info">
            <AppenderRef ref="FILE"/>
        </Root>
    </Loggers>
</Configuration>
~~~

There are **two encoding concepts**:

1. **XML declaration encoding="UTF-8":** The charset of the XML configuration file itself.
2. **PatternLayout charset="UTF-8":** The charset of the log content sent by the Layout to the file.

**Merely saving log4j2.xml as UTF-8 does not guarantee the output log file is UTF-8.** You must verify the actual Layout/Appender configuration and the written bytes.

With a JSON layout, the serializer may output certain characters as Unicode escapes or as raw UTF-8 characters. Both are valid JSON representations; do not confuse JSON escaping with the encoding of the entire file.

## 9. Byte Order Mark (BOM) and UTF-8

A **BOM** is an optional byte marker at the beginning of some Unicode files. The UTF-8 BOM has the byte sequence:

~~~text
EF BB BF
~~~

UTF-8 does not need a BOM to determine byte order because UTF-8 itself has no endianness modes like UTF-16LE/BE. Some editors may add a BOM, but line-based log pipelines usually do not need it.

For **JSON lines** files, a collector may expect the first line to start immediately with the byte for **{**. If a BOM precedes this character, the parser may reject it or see an unexpected U+FEFF character.

**Practical recommendation:** Choose **UTF-8 without BOM** for text/JSON lines logs, unless the receiving system documents a different requirement. In particular, **never prepend a BOM on every append** or every restart: a BOM in the middle of a file is no longer a valid header signature.

When using PowerShell or editors on Windows to convert files, check the tool's encoding settings. Different PowerShell versions handle UTF-8 BOMs differently; do not assume a file is byte-identical just because the text looks the same.

## 10. Source Encoding, Log File Encoding, and Terminal Encoding

There are at least three destinations that are easy to confuse:

~~~text
Source .java
   |
   | javac reads using source charset
   v
Java String in memory
   |
   +--> FileHandler/Encoder --> log file bytes
   |
   +--> ConsoleAppender/System.out --> terminal
   |
   +--> Collector --> parser/index/storage
~~~

### Source Code

If Java source files contain Vietnamese characters, use **javac -encoding UTF-8** or configure the Maven/Gradle compiler encoding. This ensures the compiler reads String literals accurately.

### Log File

Use **FileHandler.setEncoding("UTF-8")**, **Logback encoder charset**, or **Log4j 2 Layout charset**. This is the byte contract of the file.

### Terminal

The terminal's charset and font, as well as stdout/stderr properties, can make text display incorrectly even when the log file is completely valid UTF-8. **JUL's ConsoleHandler typically writes to stderr**, whereas FileHandler does not write to the console.

### Collector

A collector may read files using a different parser, encoding, or configuration than the writer program. Therefore, inspecting the file directly is not enough if the system ingests logs into a dashboard; you must test the entire pipeline.

### Java 17 and Newer Versions

In **Java 17**, the default charset can depend on the environment. Starting in **Java 18**, JEP 400 standardizes UTF-8 as the default charset for many APIs under standard conditions. However, do not rely on those defaults to skip configuring file logging: applications using other backends, out-of-JVM collectors, and deployment environments may make their own choices.

**Do not simply add the JVM file.encoding option and assume all encoding bugs are solved.** Configuring the file writer and verifying the bytes remains the more reliable approach.

## 11. Reading Back UTF-8 Files with Java 17

Reading an entire text file:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path path = Path.of("logs/application.log");
String text = Files.readString(path, StandardCharsets.UTF_8);
~~~

This is a short snippet placed inside a method that handles IOException, not a standalone program.

For large files, read line by line to avoid loading the entire contents into RAM:

~~~java
try (var lines = Files.lines(path, StandardCharsets.UTF_8)) {
    lines.forEach(System.out::println);
}
~~~

When byte-level QA is needed, you can use **Files.readAllBytes(path)** if the test file is small enough, then compare against the expected UTF-8 bytes.

### Why Is a Strict Decoder Useful?

~~~java
String decoded = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT)
        .decode(ByteBuffer.wrap(bytes))
        .toString();
~~~

This snippet assumes **bytes** and the necessary imports are already present; it can throw **CharacterCodingException** on invalid bytes. This approach is suited for tests, legacy migrations, and pipelines that must reject corrupted data.

Conversely, when using **new String(bytes, StandardCharsets.UTF_8)**, invalid byte sequences may be replaced with a **replacement character**. If you only check that "a String can be read," the program may miss silent character loss.

### Avoiding the Default Charset

~~~java
// Unclear about charset:
String unclear = new String(bytes);

// Explicit and reproducible:
String explicit = new String(bytes, StandardCharsets.UTF_8);
~~~

A common bug occurs when code reads a file on host A and writes it on host B using different default charsets. If the file is UTF-8, specify UTF-8 at both the read and write sites.

## 12. Newlines, Record Boundaries, and Log Injection

Even within UTF-8 files, newlines can differ:

~~~text
LF   = 0A
CRLF = 0D 0A
~~~

**System.lineSeparator()** uses the environment's newline. In the Java 17 example above, the Formatter fixes **\n** so byte output stays identical across operating systems.

Collectors typically read logs line by line. If a message contains newlines, tabs, or control characters from untrusted input, a single event can be split across multiple lines. This is a **record boundary/log injection** issue, not an encoding error.

Example input:

~~~text
Username: Minh
ERROR fake-event injected by input
~~~

If the application writes the input directly into the message, the second line can look like a separate ERROR event. Use proper structured logging/JSON, escape or sanitize control characters, and never build JSON by arbitrary string concatenation.

**Correct UTF-8 does not prevent log injection.** Encoding only defines bytes; it does not evaluate the meaning or trustworthiness of the content.

## 13. Mojibake: Why Can a Valid File Still Have Wrong Content?

A UTF-8 byte stream can be valid yet still contain data that was corrupted **before the Logger received the String**. For example, an HTTP client reads a response with the wrong charset, turning Vietnamese characters into garbled symbols, and then the logger writes that corrupted String as UTF-8.

This produces two distinct classes of errors:

| Situation | Check |
| --- | --- |
| File bytes are not valid UTF-8 | Strict UTF-8 decoder will report an error |
| File bytes are valid UTF-8, but content is wrong | Compare Unicode text against the expected data at the source |

Therefore, good QA requires both:
- **Valid UTF-8 bytes** matching the original input string.
- **Decoded text matching** the message the Logger intended to write.

If data has already been converted into replacement characters, re-saving it as UTF-8 cannot automatically recover the lost bytes.

### Diagnostic Procedure

1. Identify the exact **writer**: JUL/Logback/Log4j 2 backend, appender, and Charset.
2. Take a copy of the file as **raw bytes** before opening and saving it in an editor.
3. Inspect the leading bytes, any BOM if present, and decode as UTF-8 in REPORT mode.
4. If the file is valid, inspect the String **just before** the logger is called.
5. If the String is already wrong, check the database driver, HTTP layer, message queue, or file input.
6. Verify whether the collector and dashboard decode using the right Charset.
7. Fix at the exact failing step; add a regression test with Vietnamese text and emojis.
8. Do not rewrite the original file if the logs are serving as forensic/audit evidence.

You cannot always guess the source charset from a few garbled characters. If a legacy file may contain mixed encodings, investigate and perform a controlled migration.

## 14. Unicode Normalization and Search

Two strings that look identical do not necessarily share the same code points. A Vietnamese character with a diacritic can be a precomposed character or a base letter plus a combining mark. Both can be validly written in UTF-8, yet produce different bytes.

Java provides **java.text.Normalizer**:

~~~java
String nfc = java.text.Normalizer.normalize(
        input,
        java.text.Normalizer.Form.NFC);
~~~

This is an illustrative snippet and requires the input variable to be declared.

**Normalization is different from encoding.** UTF-8 does not mandate a specific Unicode normalization form. If you need consistent search for accented strings, you can normalize at the indexing/query layer. However, for audit logs or data that must preserve exact evidence, do not blindly alter the original payload: keep the raw event if investigations require it.

## 15. JSON Lines and UTF-8

Many production logging pipelines store one JSON object per line:

~~~json
{"timestamp":"2026-11-09T12:34:56.789Z","level":"INFO","event_code":"ORDER_CREATED","message":"Đã tạo đơn ở Đà Nẵng"}
~~~

A solid JSON lines pipeline requires:
- File output is UTF-8 by contract.
- Each event is serialized into valid JSON.
- Newlines inside messages are properly escaped rather than creating new records.
- Quotes, backslashes, and control characters are handled by the serializer.
- No unexpected BOM.
- Timestamp, level, service, logger, trace ID, and exception follow a clear schema.
- The reader/collector uses the right charset and parses all fields.
- Rotation/archiving does not drop or mix bytes of a record.

**JSON escaping and UTF-8 are two separate layers.** A character may appear directly as UTF-8 or be represented by the serializer as a Unicode escape; both must satisfy the JSON parser and the charset contract.

## 16. Rotation, Compression, and File Size

Encoding affects byte counts and therefore affects file size limits.

Suppose an application emits **1,000 events/second** with an average size of **400 bytes/event** after encoding:

~~~text
1,000 × 400 = 400,000 bytes/second
400,000 × 86,400 ≈ 34.56 GB/day raw data
~~~

This estimate excludes storage metadata, indexing, replication, or compression. For logs heavy in Vietnamese text or emojis, byte counts can differ significantly from estimates based on String.length().

When using FileHandler, RollingFileAppender, or RollingFile:
- Design quotas and rotation based on bytes, retention, and business needs.
- When changing encodings, do not append new data to a file with an old charset.
- **.gz** archive files must be decompressed before decoding bytes into text.
- Test the collector when the active file is renamed/truncated while an event is being written.
- Maintain proper file permissions, directories, locks, and lifecycle.
- Do not treat choosing UTF-8 as a guarantee against log loss during crashes or disk-full conditions.

## 17. Migrating Legacy Log Files to UTF-8

Procedure:

1. Identify the old charset from documentation, writer code, or technical evidence.
2. Preserve the source file byte-for-byte.
3. Decode using the source charset with an explicit error-handling policy.
4. Re-encode to UTF-8.
5. Verify Vietnamese characters, punctuation, special characters, and newlines.
6. Test parsers/collectors and search reports.
7. Switch the writer to UTF-8 when starting a new file or after a rollover.
8. Document the migration method, data source, and QA results.

Example **only for files whose source is confirmed to be windows-1252**:

~~~java
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path source = Path.of("legacy.log");
Path target = Path.of("converted-utf8.log");

String text = Files.readString(
        source,
        Charset.forName("windows-1252"));
Files.writeString(target, text, StandardCharsets.UTF_8);
~~~

This snippet is not a standalone program and needs IOException handling. **Do not assume windows-1252 for all legacy data**, especially when text contains Vietnamese. Large files should be converted by streaming rather than loading everything into memory; avoid splitting a multi-byte sequence across two chunks when decoding.

## 18. Testing File Encoding Before Production

### A. Unit Tests

- Feed ASCII, Vietnamese, CJK characters, and emojis into the Formatter/Encoder.
- Compare the resulting UTF-8 byte array against the expected bytes.
- Verify line endings and control character handling.
- Ensure no BOM is added if the contract forbids it.

### B. Integration Tests

- Start the real backend with UTF-8 charset configuration.
- Write to a temporary file.
- Flush/close the Handler/Appender following the proper lifecycle.
- Read the bytes, strict-decode, and compare content.
- Verify that an Exception is formatted/written properly using the same Charset.
- Test after rollover or restart in a production-like environment.

### C. End-to-End Tests with the Collector

- Have the agent read the newly written UTF-8 file.
- Verify message, logger name, level, timestamp, request ID, and exception.
- Ensure search can match Vietnamese strings and emojis.
- Check the JSON parser, byte offsets, newlines, and multi-line split data.
- Verify retention, read permissions, and that sensitive fields are not leaked.

Do not just screenshot a terminal and conclude file encoding PASSED: the terminal may render using a different charset or mask byte errors with replacement characters.

## 19. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using the default charset because "every machine is UTF-8" | Depends on JDK/host/tools | Specify UTF-8 on the Handler/Encoder/Layout |
| Confusing Formatter with encoding | Changing the pattern does not fix diacritic corruption | Configure both layout and Charset |
| Changing the XML config encoding and assuming the log file changes too | Output still follows the appender's charset | Check the Layout/Encoder Charset |
| Reader uses a code page other than UTF-8 | Mojibake | Decode explicitly as UTF-8 |
| Using only String.length() to measure size | Inaccurate byte/quota estimates | Measure bytes after encoding |
| Testing only ASCII | Misses Vietnamese/emoji bugs | Include multilingual test data |
| Using a decoder that silently replaces invalid bytes | Undetected data loss | Use REPORT mode in QA |
| Appending after changing the charset | One file contains multiple charsets | Rollover or create a new file |
| Leaving a BOM in unsupported JSON lines | Parser fails at start of file | Use UTF-8 without BOM per contract |
| Treating file and console encoding as identical | Fixing the wrong component | Verify bytes separately from the terminal |
| Writing raw newlines from input | Log injection, split events | Use structured logging and escaping |
| Thinking UTF-8 is encryption | Data leakage | Apply redaction and access control |
| Reading large files with readAllBytes | Memory pressure | Stream/collect line by line |
| Rewriting the charset of original audit files in place | Loss of evidence | Preserve source bytes before migration |
| Ignoring collector encoding | Dashboard displays garbled text | Run end-to-end tests |

## 20. File Encoding Implementation Checklist

1. Identify the exact backend: **JUL**, **Logback**, **Log4j 2**, or another backend.
2. Choose a charset contract, typically **UTF-8 without BOM** for text/JSON lines.
3. Set **FileHandler.encoding=UTF-8** in JUL, or the Encoder/Layout UTF-8 charset in your backend.
4. Distinguish the encodings of **source .java files**, **XML config files**, **log files**, **terminal**, and **collector**.
5. Test Vietnamese text, emojis, quotes, backslashes, newlines, and non-ASCII characters.
6. Read bytes back with a strict decoder and compare against expected Unicode content.
7. Do not mix different charsets or formats when appending to the same file.
8. Verify rotation, archive files, write permissions, quotas, and retention.
9. Use structured logging where appropriate to reduce log injection and parsing errors.
10. Apply redaction, access control, and data protection policies; encoding does not replace security.
11. Test on both Windows and Linux, on the actual JDK in use, in CI, and through the collector pipeline.
12. Verify the dashboard can search and display Vietnamese characters accurately after deployment.

## 21. Self-Check Questions

**1. Why doesn't changing the Formatter necessarily fix Vietnamese character corruption?**

Because the Formatter controls layout, while the Charset Encoder controls bytes. If the reader uses the wrong charset, the content will still be corrupted.

**2. What needs to be configured for JUL's FileHandler to write UTF-8?**

Use **setEncoding("UTF-8")** or the property **java.util.logging.FileHandler.encoding = UTF-8**.

**3. In Logback, where is the charset configured?**

Inside the **encoder** of FileAppender/RollingFileAppender, for example a **charset** element set to UTF-8.

**4. In Log4j 2, is the XML header encoding the log file encoding?**

No. The XML header describes the configuration file; you must set the charset on the Layout/Appender.

**5. Why do valid UTF-8 bytes not prove that a string was logged accurately?**

Because the String may have already been corrupted before the Logger received it. You must compare the Unicode content before and after writing.

**6. Why should you not prepend a BOM when appending logs?**

A BOM is only meaningful as a marker at the start of a stream; inserting it mid-file can cause parsers to see unexpected characters.

**7. Why can an emoji make String.length() differ from the UTF-8 byte count?**

Java Strings use UTF-16 code units, while UTF-8 uses a variable number of bytes. One emoji can consist of two UTF-16 code units and four UTF-8 bytes.

**8. Why must you test the file and the collector separately?**

Because the writer may emit valid UTF-8 while the collector decodes or parses it incorrectly, leaving the dashboard with corrupted content.

**Remember:** File encoding is a **character → byte → character** contract between your application and the entire observability pipeline. Choose **explicit UTF-8**, configure it at the right Handler/Encoder/Layout, verify actual bytes and text, avoid BOMs or mixed charsets, and test file rotation and collectors so Vietnamese logs preserve their meaning across every environment.
