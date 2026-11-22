# Default Charset and Changes Since JDK 18 in Java

## 1. One Java Program, Two Machines, Two Different Results Reading Vietnamese?

Suppose a text file contains `Tiếng Việt` and is saved in **UTF-8**. A Java program reads the file with:

```java
try (Reader reader = new FileReader("message.txt")) {
    // Read text data...
}
```

If the program runs on JDK 17 or earlier, the result **may** depend on the operating system, user settings, and the JVM's default charset. For example, a machine using UTF-8 reads it properly, whereas a system with code page `windows-1252` or `windows-1258` may decode the UTF-8 bytes into wrong characters, creating the phenomenon commonly called **mojibake** (garbled encoding text).

**Starting in JDK 18**, JEP 400 *UTF-8 by Default* changes the default value of `Charset.defaultCharset()` to **UTF-8** across platforms, unless compatibility mode is requested. Consequently, many I/O constructors/methods that previously relied on the default charset behave more uniformly.

However, concluding that “Java 18+ uses UTF-8 for **all** I/O operations” is **false**. There are still APIs with fixed charsets, explicit charset parameters, console/terminal-specific handling, or custom protocol rules.

This lesson covers:

1. What a charset is, and how it differs from `String` and bytes.
2. How the default charset was determined prior to JDK 18.
3. What JEP 400 changes and its exceptions.
4. Which APIs still require passing `StandardCharsets.UTF_8`.
5. How to inspect `file.encoding`, `native.encoding`, and `COMPAT` mode.
6. Java 17+ examples verifying decoding errors, along with an upgrade checklist.

## 2. What Does a Charset Do?

A Java `String` represents Unicode text. When reading/writing files, sockets, or byte streams, the program must convert **between bytes and characters**:

- **Encoding:** `String`/characters → bytes according to a `Charset`.
- **Decoding:** bytes → characters/`String` according to a `Charset`.

For example, the letter `é` (`U+00E9`) is encoded in UTF-8 as two bytes `C3 A9`, whereas in ISO-8859-1 it is only one byte `E9`. If the UTF-8 bytes `C3 A9` are decoded as ISO-8859-1, you get two code points `U+00C3` and `U+00A9`, typically rendered as `Ã©`.

This is not a `Locale` difference, but an **encoding/decoding mismatch**. `Locale.forLanguageTag("vi-VN")` does not by itself indicate whether a byte stream uses UTF-8 or another charset.

| Component | Purpose | Example |
| --- | --- | --- |
| `String` | Unicode text in Java | `"Tiếng Việt"` |
| `Charset` | Rule converting bytes ↔ characters | `UTF-8`, `ISO-8859-1`, `windows-1258` |
| `Charset.defaultCharset()` | JVM default charset for APIs that use the default | Typically UTF-8 on JDK 18+ |
| `StandardCharsets.UTF_8` | Explicit UTF-8 charset constant, always present in Java SE | `text.getBytes(StandardCharsets.UTF_8)` |
| `Locale` | Language/regional conventions for formatting and linguistic processing | `Locale.US`, `vi-VN` |

A `String` can be correct in memory yet become **corrupted immediately when written to bytes using an unsuitable charset**. Conversely, a UTF-8 file has exact bytes yet can be **misread** if the decoder uses a different charset. Both reader and writer must share the same charset contract, unless an explicit transcoding step is performed.

## 3. Before JDK 18: The Default Charset Depended on the Environment

In JDK 17 and earlier versions, `Charset.defaultCharset()` was determined at JVM startup, typically from the operating system and the machine's language/encoding settings.

| Pre-JDK 18 system/setting | Potential default charset |
| --- | --- |
| Linux/macOS with UTF-8 locale | `UTF-8` |
| Some Western European Windows setups | `windows-1252` or corresponding alias |
| Some Japanese Windows setups | `windows-31j` or related charset |
| Windows with other language settings | Corresponding code page; do not guess from country name alone |
| POSIX/C locale in some environments | May differ from UTF-8 |

These are **examples**, not a fixed lookup table for inferring encoding from the OS. The same OS can have different default charsets depending on user settings and the runtime environment.

How to check in Java:

```java
import java.nio.charset.Charset;

System.out.println(Charset.defaultCharset().name());
```

This is a snippet. If the JVM has a non-UTF-8 default charset, `new InputStreamReader(stream)` may use that charset to decode. When an app moves from a Linux laptop to Windows or from older Windows to a new container image, the same bytes can produce different strings.

**Notable point:** many files encoded on legacy systems contain no metadata indicating their charset. If a historical file was actually saved in `windows-1258`, reading it as UTF-8 will not automatically turn it into valid text. Changing the default charset only changes the **fallback assumption when no charset is specified**, not the encoding of existing files.

## 4. JEP 400: UTF-8 by Default Starting in JDK 18

JEP 400 was introduced in **JDK 18**. The main change is that Java SE APIs **relying on the default charset** now default to UTF-8, making them more independent of OS, locale, and account settings.

```java
Charset current = Charset.defaultCharset();
```

On a JDK 18+ JVM started in normal default mode, `current` is `StandardCharsets.UTF_8`. Passing `-Dfile.encoding=UTF-8` is not required to obtain the new default behavior.

### Comparison Table Across JDK Generations

| Item | JDK 17 and earlier | JDK 18 and later, default |
| --- | --- | --- |
| `Charset.defaultCharset()` | Typically follows environment/system code page | `UTF-8` |
| `new FileReader(file)` without charset | Uses default charset | UTF-8 |
| `new FileWriter(file)` without charset | Uses default charset | UTF-8 |
| `new InputStreamReader(stream)` | Uses default charset | UTF-8 |
| `new OutputStreamWriter(stream)` | Uses default charset | UTF-8 |
| `new String(bytes)` | Uses default charset | UTF-8 |
| `String.getBytes()` | Uses default charset | UTF-8 |
| `Files.newBufferedReader(path)` without charset | Already used UTF-8 | Still uses UTF-8 |
| `Files.readString(path)` without charset (Java 11+) | Already used UTF-8 | Still uses UTF-8 |

These rows describe behavior when **no charset is specified** in the relevant APIs. They do not affect calls that explicitly pass `StandardCharsets.ISO_8859_1` or `Charset.forName("windows-1258")`: an **explicit charset always carries its own specification**.

The JDK 18 change resolves historical inconsistency, yet also introduces **backward-compatibility** risks: legacy code that wrote/read data files in the platform code page without specifying a charset may misread them when running on a newer JDK.

### Changing the “Default” Does Not Automatically Convert Data

Example:

1. On an older machine, `new FileWriter(...)` writes content using a Windows code page.
2. A file `legacy.txt` is created, containing bytes in that code page.
3. Moving the program to JDK 18+, `new FileReader(...)` defaults to decoding the bytes as UTF-8.
4. The old bytes are not necessarily valid UTF-8, leading to replacement characters, decoding errors, or corrupted text depending on the API.

At that point, changing `Locale` settings will not fix the root cause. You must identify the **actual** source charset, read with that charset, and then intentionally rewrite the file as UTF-8 if desired.

## 5. Affected APIs and Unaffected APIs

### 5.1. APIs Using the Default Charset When Parameter Is Omitted

The following calls **depend on the default charset**:

```java
byte[] bytes = text.getBytes();
String decoded = new String(bytes);

Reader reader = new InputStreamReader(input);
Writer writer = new OutputStreamWriter(output);
```

The variables `text`, `input`, and `output` are already-declared data; this is only a **snippet**, not a standalone class. Additionally, `FileReader` and `FileWriter` constructors without a charset parameter, as well as several `Scanner` or `Formatter` constructors, can depend on the default charset.

If you supply an **explicit charset**, behavior becomes clear:

```java
byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
String decoded = new String(bytes, StandardCharsets.UTF_8);

Reader reader =
        new InputStreamReader(input, StandardCharsets.UTF_8);
Writer writer =
        new OutputStreamWriter(output, StandardCharsets.UTF_8);
```

The snippet above requires `import java.nio.charset.StandardCharsets;`, `java.io.Reader;`, `java.io.Writer;`, `java.io.InputStreamReader;`, and `java.io.OutputStreamWriter;`. Even when JDK 18+ defaults to UTF-8, **explicitly specifying the charset** at file/protocol boundaries makes the contract self-documenting and keeps code working on older JDK versions.

### 5.2. Files.readString and Files.newBufferedReader Already Defaulted to UTF-8

Not all text read/write APIs used to depend on the OS. Even before JDK 18:

```java
String text = Files.readString(path);
```

`Files.readString(Path)` (Java 11+) defaults to UTF-8 decoding. `Files.newBufferedReader(Path)` (Java 8+) also defaults to UTF-8. `Files.writeString(Path, text)` (Java 11+) defaults to UTF-8; `Files.newBufferedWriter(Path)` also uses UTF-8 when no charset is passed.

Hence the claim “starting in JDK 18, all `Files` operations first began using UTF-8” is false. JEP 400 primarily addressed APIs tied to the **environment-dependent default charset**. Several `Files` methods had already chosen UTF-8 beforehand.

### 5.3. System.out and System.err Are Special Cases

`System.out` and `System.err` are streams connected to the console/terminal and **do not necessarily** use the same charset as `Charset.defaultCharset()`. Java preserves behavior suited to the stdout/stderr environment, avoiding turning terminal output into mojibake merely because `file.encoding` changed to UTF-8.

In modern JDKs, the console charset can be inspected via `Console.charset()` when a console exists, or through properties like `stdout.encoding`/`stderr.encoding` depending on runtime and platform. Therefore:

```java
System.out.println(Charset.defaultCharset());
```

only reports the **default charset**, and does not prove that the terminal, IDE console, or a downstream process reading stdout decodes as UTF-8.

If an application writes to **a byte stream it owns**, use `OutputStreamWriter(stream, charset)` or `PrintStream(..., charset)` when encoding guarantees are required. When writing to a terminal, identify the terminal/console's actual charset and avoid altering global output streams just to patch a display glitch.

### 5.4. APIs with Fixed or Specialized Charsets

Some APIs do not follow `Charset.defaultCharset()`:

| API/behavior | Rule |
| --- | --- |
| `Properties.load(InputStream)` | Per the traditional `.properties` specification, bytes are read as ISO-8859-1 with `\\uXXXX` escapes |
| `Properties.load(Reader)` | Uses **characters already decoded by the Reader**, does not pick UTF-8 itself |
| `PropertyResourceBundle(InputStream)` | Since Java 9: UTF-8-first with ISO-8859-1 fallback unless configured otherwise |
| `DataInputStream.readUTF()` / `DataOutputStream.writeUTF()` | Uses **modified UTF-8** per Java's contract, not the default charset or standard UTF-8 in all cases |
| `Files.readString(Path)` | UTF-8 by default since the API was introduced |
| `Files.newBufferedReader(Path)` | UTF-8 by default |
| Explicitly passed `StandardCharsets.UTF_8` | Always UTF-8 |
| Third-party APIs or protocols | Per their own contract, do not assume from JEP 400 |

**Do not use `-Dfile.encoding=UTF-8` to fix a `Properties.load(InputStream)` call misreading Vietnamese.** That API has its own ISO-8859-1 rule. If the properties file is actually UTF-8, create an `InputStreamReader(..., StandardCharsets.UTF_8)` and call `Properties.load(Reader)`, or handle it via the appropriate resource bundle standard.

Do not confuse `javac`'s **source file encoding** with **runtime I/O**. Use `javac -encoding UTF-8` when `.java` sources are saved in UTF-8, especially across diverse JDKs/CI environments.

## 6. Java 17+ Verification: UTF-8 Bytes Do Not Self-Declare Their Charset

Create the file **`DefaultCharsetDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.InputStreamReader;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.stream.Collectors;

public class DefaultCharsetDemo {
    private static String codePoints(String value) {
        return value.codePoints()
                .mapToObj(cp -> String.format(
                        Locale.ROOT, "U+%04X", cp))
                .collect(Collectors.joining(" "));
    }

    public static void main(String[] args) throws Exception {
        String source = "Ti\u1EBFng Vi\u1EC7t";
        byte[] data = source.getBytes(StandardCharsets.UTF_8);

        String correct = new String(data, StandardCharsets.UTF_8);
        String wrong = new String(data, StandardCharsets.ISO_8859_1);
        String implicit = new String(data);

        System.out.println("UTF-8 byte count: " + data.length);
        System.out.println("Explicit UTF-8 equals: "
                + source.equals(correct));
        System.out.println("Explicit Latin-1 equals: "
                + source.equals(wrong));
        System.out.println("Latin-1 decoded code points: "
                + codePoints(wrong));

        System.out.println("Default charset: "
                + Charset.defaultCharset().name());
        System.out.println("Default decode equals: "
                + source.equals(implicit));

        try (InputStreamReader reader = new InputStreamReader(
                new ByteArrayInputStream(data),
                StandardCharsets.UTF_8)) {
            char[] chars = new char[32];
            int count = reader.read(chars);
            System.out.println("Explicit reader equals: "
                    + source.equals(new String(chars, 0, count)));
        }
    }
}
```

Commands:

```bash
javac -encoding UTF-8 DefaultCharsetDemo.java
java DefaultCharsetDemo
```

**API-invariant portion of stdout** (the lines listed below are always identical in this example):

```text
UTF-8 byte count: 14
Explicit UTF-8 equals: true
Explicit Latin-1 equals: false
Latin-1 decoded code points: U+0054 U+0069 U+00E1 U+00BA U+00BF U+006E U+0067 U+0020 U+0056 U+0069 U+00E1 U+00BB U+0087 U+0074
Explicit reader equals: true
```

Other lines in the output may vary by JDK/environment. On **JDK 18+ with default startup**, they are typically:

```text
Default charset: UTF-8
Default decode equals: true
```

In actual execution, these two lines appear **before** `Explicit reader equals`; the “invariant” and “environment-dependent” parts are separated here so as not to set false expectations on JDK 17 or when `COMPAT` is enabled.

Distinguish carefully:

- `source.getBytes(UTF_8)` **encodes** accurately as UTF-8.
- `new String(data, UTF_8)` **decodes** accurately with the same charset.
- `new String(data, ISO_8859_1)` creates a **different** string from the same byte array. It does not auto-detect the source charset.
- `new String(data)` uses the default charset, so whether it succeeds or fails depends on JVM configuration.
- `InputStreamReader(..., UTF_8)` gives clear behavior independent of the default.

The output sample prints `U+XXXX` codes to avoid relying on console fonts and charsets when displaying Vietnamese diacritics.

## 7. Demo 2: Default-Dependent APIs vs. Fixed UTF-8 APIs

Create **`FilesCharsetDemo.java`** (Java 17+). This program creates a temporary UTF-8 file and cleans it up:

```java
import java.io.FileReader;
import java.io.Reader;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class FilesCharsetDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile(
                "charset-demo-", ".txt");
        String source = "Ti\u1EBFng Vi\u1EC7t";

        try {
            Files.writeString(file, source, StandardCharsets.UTF_8);

            String nioRead = Files.readString(file);
            System.out.println("Files.readString equals: "
                    + source.equals(nioRead));

            StringBuilder fromDefaultReader = new StringBuilder();
            try (Reader reader = new FileReader(file.toFile())) {
                char[] buffer = new char[64];
                int n;
                while ((n = reader.read(buffer)) != -1) {
                    fromDefaultReader.append(buffer, 0, n);
                }
            }

            System.out.println("Default reader equals: "
                    + source.contentEquals(fromDefaultReader));
            System.out.println("Default is UTF-8: "
                    + StandardCharsets.UTF_8
                            .equals(Charset.defaultCharset()));

            StringBuilder fromExplicitReader = new StringBuilder();
            try (Reader reader = new FileReader(
                    file.toFile(), StandardCharsets.UTF_8)) {
                char[] buffer = new char[64];
                int n;
                while ((n = reader.read(buffer)) != -1) {
                    fromExplicitReader.append(buffer, 0, n);
                }
            }
            System.out.println("Explicit reader equals: "
                    + source.contentEquals(fromExplicitReader));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Commands:

```bash
javac -encoding UTF-8 FilesCharsetDemo.java
java FilesCharsetDemo
```

**Stdout on JDK 18+ with default UTF-8 configuration:**

```text
Files.readString equals: true
Default reader equals: true
Default is UTF-8: true
Explicit reader equals: true
```

If run on JDK 17 with a default charset **other than UTF-8**, `Files.readString` and `Explicit reader` remain `true`, whereas `Default reader equals` **can** be `false`, and `Default is UTF-8` is `false`. Similarly, JDK 18+ with `-Dfile.encoding=COMPAT` can encounter the same situation if the native encoding is not UTF-8.

Lesson: **`Files.readString(Path)` without a charset argument is not historically the same as `new FileReader(File)`** regarding the default charset. When you want clear, cross-environment code, pass an explicit charset to `FileReader` or use `Files` APIs with a UTF-8 contract.

Important note: `Files.createTempFile` only creates a temporary path, and `Files.deleteIfExists` in `finally` cleans it up. The example needs no static file in the repo. If multiple processes run tests, unique temp filenames avoid collisions. In real systems, handle I/O exceptions thoroughly rather than simply declaring `throws Exception` as in a learning example.

## 8. The file.encoding Parameter and COMPAT Mode

In **JDK 18 and later**, `file.encoding` is documented as an implementation option to configure the default charset at JVM startup. Two values are supported per Oracle documentation:

```text
-Dfile.encoding=UTF-8
-Dfile.encoding=COMPAT
```

- **`UTF-8`:** defaults to UTF-8.
- **`COMPAT`:** requests pre-JDK 18 default charset selection behavior, i.e., according to the environment/platform; typically reflecting `native.encoding`.

Other values for `file.encoding` **are not supported under the modern JDK contract**. Do not rely on `-Dfile.encoding=windows-1252` or arbitrary charsets as a long-term design.

Launch examples:

```bash
java -Dfile.encoding=UTF-8 DefaultCharsetDemo
java -Dfile.encoding=COMPAT DefaultCharsetDemo
```

If the machine's native encoding is UTF-8, **both commands may produce the same output**. To truly test a non-UTF-8 case, you need an environment whose legacy/native charset differs from UTF-8, such as a Windows machine with a legacy code page. Do not assume `COMPAT` guarantees different output.

### Properties to Know

| Property / API | Meaning and notes |
| --- | --- |
| `Charset.defaultCharset()` | Primary API to query the current default charset |
| `System.getProperty("file.encoding")` | Info/setting tied to the default charset; check during diagnostics |
| `System.getProperty("native.encoding")` | Platform encoding detected by the JVM (JDK 17+); can differ from JDK 18+'s default UTF-8 |
| `stdout.encoding` / `stderr.encoding` | Can independently control standard output/error charsets on supporting JDKs |
| `java -XshowSettings:properties -version` | Prints startup properties, useful when checking deployments |

**Do not call `System.setProperty("file.encoding", "...")` mid-execution expecting existing readers/writers to switch charsets.** The default charset is established at JVM startup, and already-created I/O objects hold their own charsets. Mutating the runtime property is not a reliable API to change the active default charset.

Nor should `native.encoding` be treated as “the code page to apply to all old files”; an actual file may have been created by an application on another machine. Use the charset of the **source data**, not merely the current machine's charset.

## 9. Distinguishing Console Input/Output Paths

A frequent bug after upgrading Java versions:

- Writing a UTF-8 file works, yet printing to the terminal shows garbled characters.
- `Charset.defaultCharset()` returns `UTF-8`, yet `System.out` uses a different console charset.
- The JVM reads an explicit UTF-8 file accurately, yet a tool capturing stdout or a log shipper decodes with a mismatched charset.

Do not rush to alter the file encoding if the **file content** is already valid. Check every byte boundary:

```text
Java String
  -> Writer/PrintStream encoder
  -> bytes in file/pipe/terminal
  -> receiving program/terminal decoder
  -> displayed characters
```

If a program reads `System.in` via `new InputStreamReader(System.in)`, that decoder uses the default charset, whereas **terminal input** may arrive in a different encoding, creating mismatch risks. When input comes from a console, consult `System.console()` and `Console.charset()` (when a console is attached); when input comes from a file/pipe with a contract, specify the charset explicitly.

`System.console()` can return `null` inside IDEs, CI, pipes, or non-interactive environments. Never assume it is always non-null.

### Do Not Confuse Encoding with Fonts

Even when both bytes and decoder are valid UTF-8, a terminal may lack Unicode glyphs or a suitable font to render characters. That is a **display** issue, distinct from a **decoding** bug. Inspect code points/bytes or write to a UTF-8 file to tell them apart.

## 10. Properties, Resource Bundles, and Default Charset Changes

`.properties` files appear frequently in localized applications. Yet they have a **specialized charset contract**:

```java
Properties properties = new Properties();

try (InputStream input = Files.newInputStream(path)) {
    properties.load(input);
}
```

This is a snippet; `Properties.load(InputStream)` reads bytes as **ISO-8859-1** and processes `\\uXXXX` Unicode escapes. It **does not switch to UTF-8 just because you run on JDK 18+**.

To read a UTF-8 properties file with `Properties`:

```java
Properties properties = new Properties();

try (Reader reader = Files.newBufferedReader(
        path, StandardCharsets.UTF_8)) {
    properties.load(reader);
}
```

This is also a snippet, using `java.util.Properties`, `java.io.Reader`, `java.nio.file.Files`, and `java.nio.charset.StandardCharsets`. The `Reader` has already decoded UTF-8 so `Properties` receives the corresponding Unicode characters.

**`PropertyResourceBundle(InputStream)` is a separate case:** since Java 9, it attempts UTF-8 first and falls back to ISO-8859-1 per specification (governed by `java.util.PropertyResourceBundle.encoding`). Do not conflate `PropertyResourceBundle` behavior with `Properties.load(InputStream)` or JEP 400.

If localization breaks after an upgrade, check which API actually reads the file, which charset the file was saved in, and which rule changed in the Java version. Do not blame everything on the default charset.

## 11. Converting a Legacy File to UTF-8 in a Controlled Way

A safe strategy is:

1. Identify the original encoding **via documentation, trusted metadata, or inspecting the actual data producer**; do not guess from filenames.
2. Read using the confirmed original charset.
3. Verify the decoded content is accurate (check accented keywords, Unicode code points, sample records).
4. Write the new file in `UTF-8`.
5. Re-read with a UTF-8 reader, comparing record counts and content.
6. Replace production data only after taking a backup and preparing a rollback plan.

Illustrative snippet when **the original file is confirmed to be windows-1252**:

```java
Charset legacy = Charset.forName("windows-1252");

String content = Files.readString(oldFile, legacy);
Files.writeString(newFile, content, StandardCharsets.UTF_8);
```

This is not a standalone program; `oldFile` and `newFile` are resolved `Path` instances. If the file is Vietnamese using `windows-1258` or another charset, you must use the exact **confirmed** charset. Do not treat `windows-1252` as a default for all legacy files.

### Watch Out for Decoders That Replace Invalid Characters

Some decoding paths replace invalid bytes with the replacement character `U+FFFD` instead of throwing an error. When data integrity must be verified, use `CharsetDecoder` with `CodingErrorAction.REPORT` and handle `MalformedInputException` or `UnmappableCharacterException` appropriately.

```java
CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);
```

This is a snippet. For large files, pass the decoder to `InputStreamReader` or use streaming reads to avoid loading the whole file into memory. **Do not treat error-free decoding as proof of the right charset**, since many byte sequences are valid in multiple charsets while yielding different text.

## 12. Checklist for Upgrading from JDK 17 or Earlier to JDK 18+

### Inventory

Search the codebase for text I/O **without an explicit charset**:

- `new FileReader(...)`, `new FileWriter(...)`.
- `new InputStreamReader(...)`, `new OutputStreamWriter(...)`.
- `new String(byte[])`, `String.getBytes()`.
- `new Scanner(file/inputStream)` and certain `Formatter` constructors.
- `javac` build steps without a pinned `-encoding`.
- Inter-process communication and stdout/stderr pipelines where encoding is not agreed upon.

At the same time, **categorize** APIs that already specify a charset explicitly, environment-independent UTF-8-default APIs like many `Files` methods, and protocol-specific APIs like `Properties.load(InputStream)`. Do not modify places that already have the right contract just to “make everything UTF-8.”

### Compatibility Testing

1. Pin the JDK version and record `Charset.defaultCharset()` and `native.encoding` in test environments.
2. On **JDK 17** running with a non-UTF-8 charset, test `-Dfile.encoding=UTF-8` at startup to uncover hidden dependencies.
3. On **JDK 18+**, test both normal startup and `-Dfile.encoding=COMPAT` to reproduce legacy behavior when native charsets differ.
4. Test exported/imported files, CSVs, logs, configs, Vietnamese data, emoji, and multi-byte characters.
5. Test execution across IDEs, terminals, CI, containers, and child processes to catch stdout/stdin mismatches.
6. Inspect **actual bytes** of files or protocol responses rather than relying solely on screen output.
7. For legacy files, document the source charset and establish a controlled transcoding plan.

### Sustainable Fixes

If a file/protocol is **defined as UTF-8**, state it explicitly:

```java
String data = Files.readString(path, StandardCharsets.UTF_8);
Files.writeString(path, data, StandardCharsets.UTF_8);
```

If a protocol format mandates a charset **other than UTF-8**, pass that exact charset. For instance, legacy standards, external partners, or archive formats with their own encodings must maintain their contract; changing the JVM default does not replace reading/writing with the right charset.

### Useful Test Suite

| Data category | Example | What to verify |
| --- | --- | --- |
| ASCII | `hello` | Most ASCII-compatible charsets give identical results; insufficient test coverage |
| Accented Vietnamese | `Tiếng Việt` | No mojibake or replacement characters |
| Non-ASCII Latin | `é`, `ñ` | Correct byte codes, accurate reader decoding |
| CJK | Japanese/Chinese/Korean characters | No reliance on legacy code pages |
| Non-BMP emoji | `U+1F600` | 4-byte UTF-8, surrogate pair in String |
| Legacy files | Bytes in confirmed source charset | Not misread as UTF-8 |
| Stdout/stderr | Via IDE, terminal, redirect, CI | Compatible encoder/decoder charsets |
| Transcoding program | Source file → UTF-8 | Accurate readback with zero data loss |

## 13. Common Misconceptions

| Misconception | Why it is wrong | Fix |
| --- | --- | --- |
| “In Java 18+, all I/O is UTF-8” | Only default-dependent APIs changed; many exceptions exist | Check each API's charset contract |
| “Locale vi-VN means UTF-8” | Locale and charset are separate concepts | Pass Charset explicitly |
| “Changing file.encoding at runtime is enough” | Default is set at startup; existing readers/writers keep theirs | Launch with proper config, fix code |
| “-Dfile.encoding=windows-1258 is always supported” | JDK 18+ only specifies UTF-8/COMPAT support | Pass explicit Charset at I/O |
| “COMPAT always returns a non-UTF-8 charset” | Machines with UTF-8 native encoding match the new default | Check `native.encoding` and `defaultCharset()` |
| “Files.readString only became UTF-8 in JDK 18” | This method has used UTF-8 since Java 11 | Distinguish APIs and their history |
| “System.out definitely prints UTF-8” | Console/stdout have their own charsets | Inspect console environment and consumer |
| “Properties.load(InputStream) uses JDK default” | It specifies an ISO-8859-1 contract | Use `load(Reader UTF-8)` for UTF-8 files |
| “UTF-8 bytes are auto-detected by Java” | String/Reader APIs do not auto-detect arbitrary charsets | Know or specify the source charset |
| “Corrupted files just need another UTF-8 encode” | If already misdecoded, you just re-encode mojibake | Go back to source bytes and decode properly |
| “ASCII-only tests suffice to verify transcoding” | ASCII usually shows no difference | Test Vietnamese and non-ASCII characters |
| “file.encoding and native.encoding are identical” | JDK 18+ can default to UTF-8 even if native differs | Read each property for its intended purpose |
| “Charset.defaultCharset decides Vietnamese diacritic rendering” | Font/terminal, Unicode, and formatting algorithms matter too | Separate encoding, decoding, and rendering |

## 14. Review Questions

**Question 1.** Since which version does Java use UTF-8 as the default charset for Java SE APIs that rely on the default charset?

**Answer:** Since **JDK 18** under JEP 400; previously the default could depend on the OS/user settings. `COMPAT` mode reproduces legacy selection behavior on JDK 18+.

**Question 2.** Does `Charset.defaultCharset()` returning UTF-8 prove `System.out` also encodes in UTF-8?

**Answer:** No. Standard streams have their own charset mechanisms tailored to the console and runtime environment.

**Question 3.** Why can `new String(utf8Bytes)` return the wrong string on JDK 17?

**Answer:** The parameterless constructor uses the default charset; if the default is not UTF-8, UTF-8 bytes are misdecoded. Use `new String(utf8Bytes, StandardCharsets.UTF_8)`.

**Question 4.** Which charset does `Files.readString(path)` use if no charset is passed on Java 17?

**Answer:** UTF-8, because that has been the contract of `Files.readString(Path)` since Java 11; it is not a new behavior from JEP 400.

**Question 5.** Why does `Properties.load(InputStream)` still read differently from UTF-8 even on JDK 21?

**Answer:** That API specifies ISO-8859-1 for reading bytes with Unicode escapes, independent of the default charset. Use `Properties.load(Reader)` with an explicitly UTF-8 reader instead.

**Question 6.** If an old file is `windows-1258`, will running on JDK 21 and reading with `FileReader(path)` always work?

**Answer:** No. JDK 21 defaults to UTF-8, while the old file remains in another charset. Read with the confirmed source charset; if appropriate, convert to UTF-8 with testing.

**Question 7.** Is `-Dfile.encoding=COMPAT` a sustainable strategy for all protocols?

**Answer:** No. It aids transition and diagnostics for legacy applications. The long-term solution is defining the data's charset and passing explicit charsets at I/O boundaries.

**Question 8.** Why is calling `System.setProperty("file.encoding","UTF-8")` after app startup insufficient?

**Answer:** The default charset is determined during startup, and already-instantiated readers/writers retain their own configuration. Changing the runtime property is not a reliable way to alter established behavior.

## 15. Summary

- **JDK 17 and earlier:** the default charset typically depends on the machine, locale, and native code page.
- **JDK 18 and later:** JEP 400 makes **UTF-8** the default charset for Java SE APIs that rely on `Charset.defaultCharset()`.
- **Not every API changes under JEP 400:** `System.out`/`System.err`, `Properties.load(InputStream)`, `Files` APIs that already defaulted to UTF-8, protocols, and explicit charsets keep their own contracts.
- **`-Dfile.encoding=UTF-8` or `COMPAT`** are supported at JDK 18+ startup; other values are not part of the supported contract.
- **Always determine the actual charset of source bytes**. For new data or protocols specifying UTF-8, pass `StandardCharsets.UTF_8` explicitly so code is self-documenting and safe across Java versions.
- Upgrading the JVM does not transcode old data automatically. Test files, networks, consoles, logs, and non-ASCII characters before deploying.

**Official References:**

- [OpenJDK JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400)
- [Java SE 21 — Supported Encodings and Default Charset](https://docs.oracle.com/en/java/javase/21/intl/supported-encodings.html)
- [Java SE 21 — InputStreamReader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/InputStreamReader.html)
- [Java SE 21 — Charset](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/Charset.html)
- [Java SE 21 — Files](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html)
- [Java Team — JEP 400 and the Default Charset](https://inside.java/2021/10/04/the-default-charset-jep400/)
