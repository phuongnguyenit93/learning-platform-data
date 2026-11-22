# Verifying Strings Across File, Resource, and Output Boundaries in Java

## 1. Why Can the Same String Have Corrupted Diacritics?

In Java, `String` stores Unicode character data (under the UTF-16 model). However, when saving files, reading resources, sending HTTP payloads, or printing to a terminal, text crosses the **boundary between characters and bytes**:

~~~text
String (Unicode)
      |
      | encode with a Charset
      v
bytes in file / resource / network / stdout
      |
      | decode with receiver's Charset
      v
String or characters rendered on screen
~~~

If the writer uses UTF-8 while the reader assumes ISO-8859-1, the string `café` can become `cafÃ©`. If a character cannot be represented in the target charset, the system may substitute `?` or throw an error. If the terminal receives the right bytes yet interprets them with another code page, the program can still be right in memory while **visible output appears corrupted**.

This lesson focuses on **verifying strings across three boundaries**:

1. **Files (file I/O)**: data flowing from `String` to bytes and back.
2. **Resources (resource files)**: `.properties`, `ResourceBundle`, configuration, translations.
3. **Output (output)**: console, logs, streams, and data exchanged with external systems.

We use Java 17+ and the APIs `StandardCharsets`, `Files`, `InputStreamReader`, `OutputStreamWriter`, `Properties`, `ResourceBundle`, `CharsetDecoder`, and `CharsetEncoder` to pinpoint **the exact boundary causing the bug**, rather than assuming Java “does not support Vietnamese.”

**Rule:** formatting by `Locale` and encoding by `Charset` are **two different operations**. `Locale.forLanguageTag("vi-VN")` does not turn bytes into UTF-8; `StandardCharsets.UTF_8` does not translate messages into Vietnamese.

## 2. Distinguishing Unicode, Charset, Locale, and Encoding

| Concept | Responsibility | Example |
| --- | --- | --- |
| Unicode code point | Abstract character identity | `é` is `U+00E9`, `🌍` is `U+1F30D` |
| Java `String` | Stores sequences via UTF-16 code units | `String.equals`, `length`, `codePoints` |
| Charset | Mapping between characters and bytes | UTF-8, UTF-16, ISO-8859-1 |
| Encoder | Converts `char`/string to bytes | `String.getBytes(UTF_8)` |
| Decoder | Converts bytes back to characters | `new String(bytes, UTF_8)` |
| Locale | Language/regional rules for formatting and bundle selection | `Locale.US`, `vi-VN` |
| ResourceBundle | Selects resources by locale and fallback rules | `Messages_vi_VN.properties` |
| Terminal/font | Receives bytes and selects glyphs to draw | Windows console, Linux terminal, CI log |

UTF-8 is an **encoding**, not a language. The same string `"Xin chào"` can be displayed to users across multiple locales while still stored as UTF-8 in the system.

### Do Not Treat `String.length()` as Byte Count

`String.length()` counts **UTF-16 code units**; non-BMP characters like `🌍` typically occupy 2 code units, yet occupy 4 bytes in UTF-8. An accented character can be precomposed or base letter + combining mark, causing code point and code unit counts to differ despite looking identical.

Example:

~~~java
String text = "🌍";
System.out.println(text.length());                       // 2
System.out.println(text.codePointCount(0, text.length())); // 1
System.out.println(text.getBytes(StandardCharsets.UTF_8).length); // 4
~~~

This is a **method-body snippet**, requiring `import java.nio.charset.StandardCharsets`. Do not infer file byte count, network transfer limits, or column widths from `String.length()`.

## 3. Boundary Inspection Diagram: Check Both Writer and Reader

When seeing garbled diacritics, gather evidence at each point:

~~~text
[1] Original String
    - what are the code points?
    - are diacritics intact before encoding?
        |
        v
[2] Bytes after encoding
    - which Charset was chosen?
    - are hex bytes right?
        |
        v
[3] Bytes when read back
    - are bytes intact?
    - is there a BOM or intermediate conversion step?
        |
        v
[4] String after decoding
    - which charset was used?
    - do U+FFFD or mojibake appear?
        |
        v
[5] Rendered output
    - were stdout/logs encoded properly?
    - do terminal/browser have matching decode/font?
~~~

If the `String` read from a file is already wrong, the cause lies in a step **before rendering**. If the code points inside `String` are right yet the screen looks wrong, inspect **output encoding, terminal environment, and fonts**.

### Three Key Failure Modes

- **Mojibake**: valid bytes decoded with a mismatched charset. For example, UTF-8 of `é` is `C3 A9`; reading those two bytes as ISO-8859-1 yields `Ã©`.
- **Replacement character**: the decoder cannot interpret a byte sequence and substitutes `U+FFFD`, typically displayed as `�`.
- **Unmappable character**: the encoder cannot represent a character in the target charset; depending on policy, it writes `?` or throws an exception.

Do not “fix diacritics” via repeated `new String(old.getBytes(...), ...)` calls without knowing **the original bytes and encode/decode history**. A string that underwent lossy character replacement may be unrecoverable.

## 4. Choosing StandardCharsets.UTF_8 Explicitly

Java provides the `StandardCharsets.UTF_8` constant in `java.nio.charset`. This is the standard unified choice for text files, resources, and modern protocols when no other standard is mandated.

~~~java
byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
String decoded = new String(bytes, StandardCharsets.UTF_8);
~~~

This is a **method-body snippet**, requiring `import java.nio.charset.StandardCharsets` and an existing `text` variable.

**Round-trip rule:** If input text is valid and encoded/decoded with the same charset capable of representing all its characters, `text.equals(decoded)` should normally be `true`. When converting to ISO-8859-1, UTF-16BE, or another charset without a clear contract, round-trip preservation may not hold.

### Java 17 vs. Java 18+ Differ on the Default Charset

- In **JDK 17 and earlier**, the default charset of many APIs depends on the operating system, locale/machine configuration, and how the JVM was launched.
- Starting in **JDK 18**, JEP 400 switches the default charset of most Java SE APIs to UTF-8 by default, with exceptions around console I/O and compatibility mechanisms.
- Even so, **do not rely on the default charset** when a file/protocol format is a contract that must be reproducible across different JDKs, servers, and CI.
- APIs such as `Files.readString(Path)` and `Files.writeString(Path, ...)` already specify UTF-8 in their own documentation, independent of legacy `FileReader`'s default-charset behavior.

To inspect the environment:

~~~java
System.out.println(Charset.defaultCharset());
System.out.println(System.getProperty("file.encoding"));
~~~

This is a **method-body snippet**, requiring `import java.nio.charset.Charset`. This is diagnostic data, **not** a way to configure per-file encoding. Avoid relying on calling `System.setProperty("file.encoding", ...)` at runtime to alter all active I/O.

## 5. Complete Example: Lossless UTF-8 Write and Read

Create `Utf8RoundTripDemo.java`:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.HexFormat;

public class Utf8RoundTripDemo {
    public static void main(String[] args) throws Exception {
        String source = "Xin chào, 世界 🌍";
        Path file = Files.createTempFile("utf8-roundtrip-", ".txt");

        try {
            byte[] expectedBytes =
                    source.getBytes(StandardCharsets.UTF_8);

            Files.writeString(file, source, StandardCharsets.UTF_8);
            byte[] actualBytes = Files.readAllBytes(file);
            String decoded =
                    Files.readString(file, StandardCharsets.UTF_8);

            System.out.println("Same bytes: "
                    + Arrays.equals(expectedBytes, actualBytes));
            System.out.println("Same text: "
                    + source.equals(decoded));
            System.out.println("UTF-8 for é: "
                    + HexFormat.of().formatHex(
                            "é".getBytes(StandardCharsets.UTF_8)));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Run on Java 17+:

~~~bash
javac -encoding UTF-8 Utf8RoundTripDemo.java
java Utf8RoundTripDemo
~~~

Output:

~~~text
Same bytes: true
Same text: true
UTF-8 for é: c3a9
~~~

This test verifies two **distinct yet related** facts:

1. `Same bytes`: the file actually contains the exact UTF-8 bytes generated from the source.
2. `Same text`: the decoder reconstructs the exact input `String`.

If you merely print text to the console and eyeball it, it is hard to tell whether a bug occurred in the file, decoder, or terminal. Programmatic byte/string comparison isolates the problem **independently of the console's Unicode rendering capabilities**.

`HexFormat` arrived in Java 17; on older Java versions, format hex using a loop or appropriate utility.

## 6. Files.readString/writeString and Legacy APIs

### Choose APIs Where You Know the Exact Charset

| Usage | Charset chosen | Assessment |
| --- | --- | --- |
| `Files.readString(path, UTF_8)` | Explicit UTF-8 | Clear, recommended for text files |
| `Files.writeString(path, text, UTF_8)` | Explicit UTF-8 | Easy to verify exact bytes |
| `Files.readString(path)` | UTF-8 per API | Fine when contract is UTF-8 |
| `Files.newBufferedReader(path, UTF_8)` | UTF-8 | Suitable for streaming line reads |
| `Files.newBufferedWriter(path, UTF_8)` | UTF-8 | Suitable for streaming line writes |
| `new InputStreamReader(in, UTF_8)` | UTF-8 | Suitable when working with byte streams |
| `new OutputStreamWriter(out, UTF_8)` | UTF-8 | Suitable when writing to byte streams |
| `new InputStreamReader(in)` | Default charset | Prone to contract drift on Java 17 |
| `new FileReader(file)` on Java 17 | Default charset | Needs review during code migration |
| `new String(bytes)` | Default charset | Avoid when bytes have a defined encoding |
| `text.getBytes()` | Default charset | Avoid for stable protocols |

### Streaming Reads

~~~java
try (BufferedReader reader = Files.newBufferedReader(
        path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        // Process a UTF-8 decoded line.
    }
}
~~~

This is a **method-body snippet**, requiring imports for `java.io.BufferedReader`, `java.nio.file.Files`, `java.nio.file.Path`, and `java.nio.charset.StandardCharsets`; `path` is already defined.

Choose streaming reads when files are large or require line-by-line processing. `Files.readString` loads the entire content into memory, so never use it unconditionally on huge or untrusted files.

### Closing Streams and Flushing

When writing with `BufferedWriter`/`OutputStreamWriter`, `flush`/`close` properly to ensure bytes reach the destination. Use `try-with-resources` to close and propagate I/O errors. However, **closing a writer does not fix a wrong charset**; specify the right encoding when creating the writer.

## 7. When Bytes Are Invalid: Strict Decoders and Replacement Policies

Some convenience APIs replace invalid bytes with a replacement character, causing the program to **throw no error** while silently losing information. When processing critical input files, explicitly choose `CodingErrorAction.REPORT`.

### Complete Java 17+ Program

Create `StrictDecodeDemo.java`:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.Locale;

public class StrictDecodeDemo {
    public static void main(String[] args) {
        // C3 must be followed by a UTF-8 continuation byte,
        // yet 28 is '(' (invalid in that position).
        byte[] invalidUtf8 = {(byte) 0xC3, (byte) 0x28};

        try {
            StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(invalidUtf8));

            System.out.println("Unexpected success");
        } catch (CharacterCodingException ex) {
            System.out.println("Strict decode failed: "
                    + ex.getClass().getSimpleName());
        }

        String replaced = new String(
                invalidUtf8, StandardCharsets.UTF_8);

        System.out.printf(Locale.ROOT,
                "First code point after replacement: U+%04X%n",
                replaced.codePointAt(0));
        System.out.println("Replaced length: " + replaced.length());
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 StrictDecodeDemo.java
java StrictDecodeDemo
~~~

Output:

~~~text
Strict decode failed: MalformedInputException
First code point after replacement: U+FFFD
Replaced length: 2
~~~

**Why does this matter?**

- `CharsetDecoder` with `REPORT` signals invalid bytes.
- `new String(invalidUtf8, UTF_8)` in this example applies replacement for invalid bytes, putting `U+FFFD` into the result.
- Once original bytes are replaced with `U+FFFD` or `?`, the original information may be lost; do not assume you can reliably reverse-repair it.
- In pipelines requiring strict validation, use decoders/encoders with explicit policies and record errors at the **byte boundary**.

### Encoders Also Need Error Policies

If the target is ISO-8859-1, characters such as Japanese cannot be represented. Use `CharsetEncoder` with `CodingErrorAction.REPORT` if you want to fail clearly instead of substituting characters:

~~~java
CharsetEncoder encoder =
        StandardCharsets.ISO_8859_1.newEncoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);
ByteBuffer bytes = encoder.encode(CharBuffer.wrap("日本語"));
~~~

This is an **illustrative snippet** inside a method, requiring imports for `java.nio.charset.CharsetEncoder`, `CodingErrorAction`, `StandardCharsets`, `java.nio.CharBuffer`, `java.nio.ByteBuffer`, and declaring `throws CharacterCodingException` or handling the exception. This example will throw an unmappable error: a Latin-1 file cannot directly hold those characters.

Only use historical charsets like ISO-8859-1 or Windows code pages when input/output is **confirmed** to use that charset. For new protocols, UTF-8 is generally the clearer choice.

## 8. Properties.load(InputStream) Differs from Properties.load(Reader)

This is one of the most frequent sources of diacritic bugs in Java applications.

**`java.util.Properties.load(InputStream)`** specifies that each byte is interpreted as ISO-8859-1, with `\uXXXX` Unicode escapes for characters outside that set. This **does not change** merely because JDK 18+ picks UTF-8 as the default charset.

Meanwhile, **`Properties.load(Reader)`** reads **characters** from an already-decoded Reader; if the Reader uses UTF-8, UTF-8 properties content enters as proper Unicode.

### Complete Java 17+ Example Without Creating Files

Create `PropertiesEncodingDemo.java`:

~~~java
import java.io.ByteArrayInputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.Properties;

public class PropertiesEncodingDemo {
    public static void main(String[] args) throws Exception {
        String source = "label=café\n";
        byte[] utf8 = source.getBytes(StandardCharsets.UTF_8);

        Properties legacyBytes = new Properties();
        legacyBytes.load(new ByteArrayInputStream(utf8));

        Properties utf8Reader = new Properties();
        try (InputStreamReader reader = new InputStreamReader(
                new ByteArrayInputStream(utf8),
                StandardCharsets.UTF_8)) {
            utf8Reader.load(reader);
        }

        System.out.println("InputStream value: "
                + legacyBytes.getProperty("label"));
        System.out.println("Reader value: "
                + utf8Reader.getProperty("label"));
        System.out.println("Reader correct: "
                + "café".equals(utf8Reader.getProperty("label")));
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 PropertiesEncodingDemo.java
java PropertiesEncodingDemo
~~~

Output when the console renders Unicode properly:

~~~text
InputStream value: cafÃ©
Reader value: café
Reader correct: true
~~~

Explanation:

- UTF-8 for `é` consists of two bytes `C3 A9`.
- `Properties.load(InputStream)` reads those two bytes as two ISO-8859-1 characters, producing `Ã©`.
- `Properties.load(Reader)` receives `é` already decoded as UTF-8, thus preserving `café`.
- If the terminal uses the wrong charset, lines containing Unicode characters may still **look different**. The `Reader correct: true` line is an in-memory check, more reliable than inspecting glyphs.

### Things to Remember About Properties

- `Properties.load(Reader)` does not skip `.properties` syntax rules: escapes, `=`:`:` delimiters, line continuations, and `\uXXXX` are still processed per properties syntax.
- `Properties.store(OutputStream, ...)` uses traditional byte-stream rules, emitting Unicode escapes for characters outside ISO-8859-1.
- `Properties.store(Writer, ...)` writes characters through the Writer and its chosen charset; it does not always produce the same bytes as the `OutputStream` overload.
- When obtaining an `InputStream` from `ClassLoader.getResourceAsStream(...)`, `getResourceAsStream` itself only supplies **bytes**; you still must pick the right decoding layer afterward.

**Do not confuse `Properties` with `PropertyResourceBundle`**: they have different encoding rules in Java 9+.

## 9. ResourceBundle .properties in Java 9+ Has Its Own Rules

`ResourceBundle.getBundle(...)` is used to load translations by locale. For resources loaded via `PropertyResourceBundle(InputStream)` on Java 9+, the default encoding rule is:

1. Try reading `.properties` as **UTF-8**.
2. If an invalid UTF-8 byte error of the documented kind occurs, fall back to reading as **ISO-8859-1**.
3. If you want a single strict encoding, set the system property `java.util.PropertyResourceBundle.encoding` to `UTF-8` or `ISO-8859-1` **at JVM startup, before the class is initialized**.

The runtime evaluates this property **once when initializing the `PropertyResourceBundle` class**. Calling `System.setProperty(...)` too late or calling `ResourceBundle.clearCache()` does not turn it into a per-read encoding toggle.

Notably, `PropertyResourceBundle`'s default UTF-8 behavior **does not** switch `Properties.load(InputStream)` to UTF-8.

### UTF-8 Resource File Example

Create two files in the same directory:

~~~text
demo/
  ResourceBundleUtf8Demo.java
  Messages_vi_VN.properties
~~~

Contents of `Messages_vi_VN.properties` (saved as **UTF-8**):

~~~properties
welcome=Xin chào, thế giới!
currency=Đồng Việt Nam
~~~

Create `ResourceBundleUtf8Demo.java`:

~~~java
import java.util.Locale;
import java.util.ResourceBundle;

public class ResourceBundleUtf8Demo {
    public static void main(String[] args) {
        Locale locale = Locale.forLanguageTag("vi-VN");
        ResourceBundle bundle =
                ResourceBundle.getBundle("Messages", locale);

        String message = bundle.getString("welcome");
        System.out.println("Correct value: "
                + "Xin chào, thế giới!".equals(message));
        System.out.println("Message: " + message);
    }
}
~~~

Compile/run inside `demo` using Java 17+:

~~~bash
javac -encoding UTF-8 ResourceBundleUtf8Demo.java
java -cp . ResourceBundleUtf8Demo
~~~

Output when the terminal renders Unicode properly:

~~~text
Correct value: true
Message: Xin chào, thế giới!
~~~

`Correct value: true` proves the `String` value was read accurately. If the `Message` line shows garbled diacritics in the terminal, inspect **the output**, rather than immediately editing the bundle content.

### Strict UTF-8 Mode

When you want to detect resource files containing invalid bytes instead of falling back to Latin-1, run:

~~~bash
java -Djava.util.PropertyResourceBundle.encoding=UTF-8 -cp . ResourceBundleUtf8Demo
~~~

Notes:

- Put `-D...` **before the main class name**.
- Supported values are `UTF-8` or `ISO-8859-1` per Javadoc.
- To apply in real applications, configure it **at startup**, not by calling `System.setProperty` after resources have been used.
- Tests must verify the base name, package, classpath, locale fallback, and the actual packaged content.

### Resources with Unicode Escapes

In legacy systems, content may be written as:

~~~properties
welcome=Xin ch\u00E0o
~~~

Escape syntax represents Unicode inside ASCII/Latin-1 properties files. However, if a Java 17+ project standardizes on UTF-8, keeping literal Unicode content can be easier to read and review. Pick one consistent encoding policy and avoid mixing manual escape conversion with decoding in a different charset, which makes bugs harder to trace.

## 10. Compiler Charset Differs from Runtime File Charset

Java source code is also a **file of bytes**. Before a `String` exists in the JVM, `javac` must read the source file with the right encoding.

For example, `Hello.java` contains the literal `"Tiếng Việt"`. If the file is saved as UTF-8 yet the compiler reads it with another charset, the literal is already corrupted **inside the class file**; no downstream `Files`/`ResourceBundle` call can fix it automatically.

Compile with an explicit charset:

~~~bash
javac -encoding UTF-8 Hello.java
~~~

This is an illustrative command assuming `Hello.java` exists. In real projects, configure encoding in the build tool:

- Maven: source/resource encoding must be configured and verified for the plugin versions and build toolchain used.
- Gradle: configure encoding for compile tasks and `processResources` if filtering/transforming content.
- IDE: verify file encodings and matching compiler settings.
- CI: rebuild from source in a clean environment without relying on a developer machine's encoding.

**Note:** `javac -encoding UTF-8` applies only to **source files read by javac**; it does not set the encoding of `.properties` files, runtime data, terminals, or HTTP responses.

### Watch Out for Resources Altered by Build Tools

A `Messages_vi_VN.properties` file may sit in the resources folder and then pass through variable filtering, copying, minifying, merging, or JAR packaging. If the UTF-8 source file is right yet the packaged classpath resource has wrong bytes, the bug is in the **build pipeline**.

To debug, inspect the **actually packaged file** and its bytes, not only the source file in the IDE. When loading a resource from a JAR, `getResourceAsStream` returns the packaged bytes, not necessarily the original file on a developer's disk.

## 11. Byte Order Mark (BOM) and the U+FEFF Character

Some UTF-8 files begin with three bytes `EF BB BF`, known as a **UTF-8 BOM**. In certain text-reading APIs, those three bytes can be decoded into a leading `U+FEFF` character in the `String`.

This creates subtle bugs:

- A file looks like it starts with `"name="`, yet the first key is actually `"\uFEFFname"`.
- `text.startsWith("name")` returns false.
- A parser for another protocol may actively detect/strip a BOM, yet **never assume all APIs do so**.

### Standalone Java 17+ Example

Create `Utf8BomDemo.java`:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;

public class Utf8BomDemo {
    public static void main(String[] args) throws Exception {
        Path path = Files.createTempFile("bom-test-", ".txt");

        try {
            byte[] withBom = {
                    (byte) 0xEF, (byte) 0xBB, (byte) 0xBF,
                    (byte) 'H', (byte) 'e',
                    (byte) 'l', (byte) 'l', (byte) 'o'
            };
            Files.write(path, withBom);

            String content =
                    Files.readString(path, StandardCharsets.UTF_8);

            System.out.printf(Locale.ROOT,
                    "First character: U+%04X%n",
                    (int) content.charAt(0));
            System.out.println("Equals Hello: "
                    + content.equals("Hello"));
            System.out.println("Without initial BOM: "
                    + (content.startsWith("\uFEFF")
                        ? content.substring(1) : content));
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
~~~

Run commands:

~~~bash
javac -encoding UTF-8 Utf8BomDemo.java
java Utf8BomDemo
~~~

Output:

~~~text
First character: U+FEFF
Equals Hello: false
Without initial BOM: Hello
~~~

This is a **policy of stripping a leading BOM when the file contract permits**, not a license to delete every `U+FEFF` anywhere in text. For XML, CSV, JSON, source files, or specialized formats, follow the BOM rules of **the respective protocol**. Do not call `strip()` assuming it guarantees removing `U+FEFF`.

## 12. Writing Output: Console and Logs Are Another Byte Boundary

Console output is not simply `System.out.println(text)` and “Unicode works automatically.” Multiple layers may sit in between:

~~~text
Valid Java String
     |
     v
PrintStream / logger encodes to bytes
     |
     v
stdout / terminal / CI / redirect / log collector
     |
     v
viewer's decoder + font
~~~

If printing `"Tiếng Việt"` shows garbled text to the user, verify the **in-memory string** via tests and inspect the **emitted bytes**. Never alter Unicode in business data just to appease a misconfigured terminal.

### Java 18+ Does Not Mean System.out Is Always UTF-8

JEP 400 switched the default charset for most Java SE APIs to UTF-8, yet `System.out`/`System.err` have separate considerations for the console/host charset. Therefore never conclude “`Charset.defaultCharset()` is UTF-8, so every terminal definitely reads UTF-8.”

In practice, check:

- The actual charset of the console/terminal and how the JVM initializes output streams.
- The charset of log appenders/file writers.
- The charset of log collectors/CI systems.
- Whether the font has glyphs for the printed language.
- Cases where stdout is redirected to a file rather than an interactive console.

In Java 17+, `System.console()` can be `null` when running under an IDE/CI/redirection; if non-null, `System.console().charset()` helps diagnose the console charset. Never rely on `System.console()` always being non-null.

### Java 17+ Example Checking Output Bytes in Memory

Instead of depending on a terminal, create an output stream with an explicit charset.

Save `OutputEncodingDemo.java`:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

public class OutputEncodingDemo {
    public static void main(String[] args) throws Exception {
        ByteArrayOutputStream output = new ByteArrayOutputStream();

        try (OutputStreamWriter writer = new OutputStreamWriter(
                output, StandardCharsets.UTF_8)) {
            writer.write("café");
        }

        byte[] bytes = output.toByteArray();
        String decoded = new String(bytes, StandardCharsets.UTF_8);

        System.out.println("Hex: "
                + HexFormat.of().formatHex(bytes));
        System.out.println("Same text: " + "café".equals(decoded));
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 OutputEncodingDemo.java
java OutputEncodingDemo
~~~

Output:

~~~text
Hex: 636166c3a9
Same text: true
~~~

When output is produced via `OutputStreamWriter(..., UTF_8)`, bytes can be verified independently of the terminal. `OutputStreamWriter` must be flushed/closed; the example uses try-with-resources.

If you want a `PrintStream` for a specific destination, Java 17 provides `new PrintStream(output, true, StandardCharsets.UTF_8)`. However, wrapping `System.out` in a new `PrintStream` does not guarantee the destination console decodes UTF-8 properly; you must examine the entire pipeline.

## 13. Running Programs with Output Redirection and Hex Inspection

When suspecting the terminal, a useful QA workflow is:

1. Run the program writing an **explicit-charset UTF-8 file** or redirect stdout to a file in a known environment.
2. Inspect output hex bytes as close to the application as possible.
3. Read back using `Files.readString(path, StandardCharsets.UTF_8)`.
4. Compare the read `String` with expected text in a unit test.
5. If bytes are right yet the file viewer displays errors, check the encoding selected by **the file viewer**.

Example reading an existing `output.txt` confirmed to be UTF-8:

~~~java
Path path = Path.of("output.txt");
String content = Files.readString(path, StandardCharsets.UTF_8);
System.out.println(content.contains("Tiếng Việt"));
~~~

This is a **method-body snippet**, requiring imports for `java.nio.file.Path`, `java.nio.file.Files`, and `java.nio.charset.StandardCharsets`; the file must have been created beforehand in UTF-8. The boolean result tells whether the content read properly, though you still must inspect each boundary if a pipeline dropped bytes.

### Locale Does Not Fix Charset Bugs

For example, `NumberFormat.getNumberInstance(Locale.GERMANY)` produces decimal commas and grouping dots per German locale. Yet when writing the result to a file, **you still must choose a charset**. Likewise, `StandardCharsets.UTF_8` does not produce German decimal commas on its own.

Responsibility diagram:

~~~text
Numeric/date value
   -> Locale: produces String with proper punctuation, month names, and formatting
   -> Charset: converts that String to bytes
   -> Destination: receives bytes / stores
   -> Reader's Charset: restores String
   -> Font/renderer: displays glyphs
~~~

Never try to fix a bug in one layer by modifying a completely unrelated layer.

## 14. HTTP, JSON, and Network Data: Another Party Decides Encoding

When sending strings over a network, both client and server must share a byte contract.

- **JSON** is standardly used with UTF-8; follow the specification/version of the JSON standard in use.
- **HTTP Content-Type** and charset can affect how clients interpret bodies for relevant media types; set headers properly via your API/framework.
- HTTP libraries, servlets, and JSON mappers may encode/decode on your behalf; inspect actual configuration and avoid double-encoding.
- Never use parameterless `String.getBytes()` for a protocol needing consistent bytes across different servers.
- URL encoding/percent-encoding is a URI structure concern, **not identical** to UTF-8 text file encoding even though they connect at the byte level.

For example, an API returns JSON containing `"Xin chào"`: verify the response bytes are right, `Content-Type` matches, and the receiving JSON parser interprets them properly. Never assume content is corrupted merely because DevTools or a terminal renders an unusual font.

When passing data through a database, inspect **connection charset, column types, and driver behavior**. With databases, if a string in the JVM is right before insert yet wrong after select, compare data/bytes at the driver/database boundary to isolate the root cause.

## 15. Distinguishing “Encoding Bugs” from “Unicode Normalization Bugs”

Two accented strings can look identical yet have different code points:

~~~text
café       -> ... U+00E9
cafe\u0301 -> ... U+0065 U+0301
~~~

This is a **Unicode canonical equivalence** concern, not necessarily a byte-reading bug. Java's `Normalizer.Form.NFC` can bring them to a canonically equivalent form while **preserving diacritics**.

Conversely:

- `cafÃ©` typically indicates mojibake from UTF-8 being interpreted under another charset.
- `caf�` indicates invalid bytes were likely substituted with a replacement character.
- `caf?` may result from an encoder unable to represent a character substituting a fallback.
- `cafe` instead of `café` may come from unaccented source data or an **intentional** accent-stripping transform, not necessarily a charset bug.

Never apply `NFD + replaceAll("\\p{M}+", "")` to “fix encoding.” That is **lossy diacritic stripping**, which can collapse `má`, `mã`, and `mạ` into the same `ma`, altering meaning.

### Printing Code Points for Diagnostics

~~~java
text.codePoints().forEach(cp ->
        System.out.printf("U+%04X ", cp)
);
~~~

This is a **method-body snippet** using `text`. Combining code-point printing with byte hex distinguishes cases where **characters are already wrong in the JVM** from cases where **characters are right yet the renderer displays them incorrectly**.

When working with emoji or non-BMP characters, `codePoints()` is better than iterating `char` by `char` to inspect true Unicode values.

## 16. What Should an End-to-End Test Suite Include?

A unit test checking only in-memory `String.equals` is insufficient when an application spans multiple boundaries. Include file, resource, and output tests along the **real execution path**.

### Recommended Test Matrix

| Boundary | Test data | Evidence to verify |
| --- | --- | --- |
| Source → class | `Tiếng Việt`, `café`, `日本語` | `javac -encoding UTF-8`, in-JVM literals match |
| String → file | Vietnamese, emoji, combining marks | UTF-8 bytes match expected |
| File → String | Valid UTF-8, invalid UTF-8 | Round-trip; strict decode must catch errors |
| Properties InputStream | `label=café` containing UTF-8 bytes | Detects Latin-1 mojibake |
| Properties Reader | Same UTF-8 file | Unicode value restored accurately |
| PropertyResourceBundle | `Messages_vi_VN.properties` | Translations loaded properly; explicit UTF-8 policy |
| BOM | File starting with `EF BB BF` | `U+FEFF` present/stripped per target rule |
| OutputWriter | `café` | Bytes `63 61 66 C3 A9` |
| Console/log | Multilingual, CI, and redirection | Separate stream encoding from viewer decoder |
| Network/database | UTF-8, localized names | Both sides preserve strings and protocol contract |
| Unicode normalization | `é` vs. `e + ◌́` | Never confuse NFC with diacritic stripping |
| Unsupported charset | Japanese text through Latin-1 | Encoder `REPORT` instead of silent data loss |

### Sample Data Should Be Diverse

Do not test only ASCII `"Hello"` since many legacy charsets share the same bytes for ASCII. Valuable test data includes:

- Vietnamese: `"Tiếng Việt, Đặng, Trường"`.
- Accented Latin: `"café, naïve"`.
- Japanese: `"日本語"`.
- Arabic: `"مرحبا"`.
- Emoji: `"🌍"`.
- Decomposed Unicode: `"cafe\u0301"`.
- Invalid UTF-8 input: bytes `C3 28`.
- Files with and without a BOM.

Test **the actually packaged/deployed artifact**, not only files in the source repository. Certain bugs appear only after resource filtering or when moving between Windows and Linux.

## 17. Symptom-Based Troubleshooting Checklist

| Symptom | Possible cause | First check |
| --- | --- | --- |
| `cafÃ©` | UTF-8 decoded as ISO-8859-1/Windows code page | Source byte hex and reader's charset |
| `caf�` | Invalid bytes or replacing decoder | Is `U+FFFD` in the `String`? Strict decoder |
| `caf?` | Encoder could not represent character | Output charset, encoder error policy |
| Console broken but String tests pass | Output/terminal charset or font | Output hex/terminal settings, UTF-8 log file |
| Source file right, runtime bundle wrong | Resource filtering/copy/JAR or bundle encoding | Inspect packaged resource bytes |
| `Properties.load(InputStream)` mangles accents | API's ISO-8859-1 semantics | Switch to UTF-8 `Reader` if contract permits |
| `ResourceBundle` wrong in Java 17 | File bytes, fallback, encoding config, or wrong resource | Check base name, locale, classpath, startup property |
| Properties key starts with strange char | UTF-8 BOM retained as U+FEFF | Check first three bytes and BOM rule |
| Same-looking Unicode fails `equals` | Different NFC/NFD forms | Print code points, consider NFC |
| Java 17 works, another Java fails or vice versa | Different default charset/JDK/provider | Pass `StandardCharsets.UTF_8` explicitly |
| Log written right but viewer shows wrong accents | Viewer uses mismatched charset | Check bytes and viewer's UTF-8 mode |
| Text breaks after DB round-trip | Connection, column, driver conversion | Compare String before insert vs. after select |

**Do not randomly try charsets to pick whichever “looks okay” and overwrite original data.** Identify the byte source and encoding contract, reproduce the bug reliably, and preserve the original copy for investigation.

## 18. Control Process in Real-World Applications

A sound policy for multilingual Java projects:

1. **UTF-8 sources and resources:** set consistent encoding in IDE/build/CI, inspect final JAR contents.
2. **Explicit charsets for files and networks:** use overloads taking an explicit `Charset`; for byte streams, wrap with matching-encoding Reader/Writer.
3. **Separate Locale and Charset:** format linguistic output first, encode when leaving the JVM.
4. **Strict reads when needed:** use `CharsetDecoder/Encoder` with `REPORT` for critical data.
5. **Never strip diacritics to hide bugs:** never apply transliteration or mark stripping when the issue is I/O encoding.
6. **Monitor conversion points:** log charset, byte length, and error codes; avoid putting raw sensitive info in logs.
7. **Test in CI:** test multiple languages, surrogate pairs, invalid bytes, BOMs, packaged JAR files, and redirected output.
8. **Standardize translation ownership:** `ResourceBundle` selects strings by `Locale`, while resource bytes have an independent encoding policy.
9. **Never store formatted output as source data:** store clean Unicode and typed data; render per recipient context.
10. **Test JDK upgrades thoroughly:** pay special attention to Java 17 vs. 18+ default charsets; keep contracts explicit to minimize behavior changes.

### Practice Exercises

1. Explain why `String.length()`, Unicode code point count, and UTF-8 byte length of `"🌍"` are three different numbers.
2. Write `"Tiếng Việt 🌍"` to a UTF-8 file, read it back, and verify both bytes and `String.equals`.
3. Parse bytes `C3 28` using `CharsetDecoder.REPORT` and using `new String(bytes, UTF_8)`. Observe the difference.
4. Create properties containing `label=café` in UTF-8; compare results of `Properties.load(InputStream)` and `load(Reader UTF8)`.
5. Read `Messages_vi_VN.properties` with `ResourceBundle.getBundle`. Why can the result differ from `Properties.load(InputStream)`?
6. Run `ResourceBundleUtf8Demo` with `-Djava.util.PropertyResourceBundle.encoding=UTF-8` at startup. Why does changing the property after class initialization have no effect?
7. Create a UTF-8 file with a BOM and inspect the first character via `Files.readString`. When is stripping `U+FEFF` allowed?
8. Write an `OutputStreamWriter` to a `ByteArrayOutputStream` and inspect the hex bytes of `"café"`. Why is a byte test stronger than looking at the console?
9. A system has the right `String` before calling `println`, yet the terminal prints garbled text. List the boundaries to inspect before modifying translation-handling code.
10. Test `"caf\u00E9"` and `"cafe\u0301"`; distinguish normalization from charset when checking equality.
11. Run Unicode tests across Java 17 and Java 21 builds in different environments; verify that passing explicit charsets stabilizes results.
12. If an API takes `Locale.US` yet reads a file as Latin-1, what happens? Why is `Locale` not a fix for byte errors?

**Remember:** verifying strings properly requires checking **across byte boundaries**. Data can be right in `String` yet break when writing files, loading properties, or printing to a terminal. Use `StandardCharsets.UTF_8` explicitly, inspect **byte hex and Unicode code points**, round-trip files/resources/output, distinguish `Properties.load(InputStream)` (ISO-8859-1) from Java 9+ `PropertyResourceBundle` (UTF-8 by default with documented fallback), and handle invalid bytes with strict decoders/encoders when needed. **Never strip diacritics, batch-replace characters, or change Locale to mask Charset bugs.**

### References

- [Java SE 17 — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html) — `readString`, `writeString`, and reader/writer.
- [Java SE 17 — StandardCharsets](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html) — standard charsets.
- [Java SE 17 — CharsetDecoder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetDecoder.html) — malformed/unmappable and `CodingErrorAction`.
- [Java SE 17 — Properties](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Properties.html) — `load(InputStream)` vs. `load(Reader)`.
- [Java SE 17 — PropertyResourceBundle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PropertyResourceBundle.html) — default UTF-8 and controlling encoding.
- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400) — default charset change starting in Java 18 and exceptions.
- [Java SE 17 — PrintStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/PrintStream.html) — byte output and charset.
- [Unicode Standard Annex #15](https://www.unicode.org/reports/tr15/) — distinguishing Unicode normalization from encoding changes.
