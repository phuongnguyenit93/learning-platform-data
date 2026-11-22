# Default Charset and the Impact of Environment and JDK Version

## 1. Why Does the Default Charset Matter?

In Java, `String` holds Unicode characters; files, sockets, messages, and many I/O APIs exchange **bytes**. **Encoding** turns characters into bytes; **decoding** turns bytes into characters. A byte sequence can only be decoded accurately when the reader uses the same charset that the writer used.

The **default charset** of a JVM is obtained via `Charset.defaultCharset()`. Certain APIs automatically use this charset when the developer omits a `Charset` argument or encoding name. Consequently, the exact same source code can write different bytes, or read the same file with different results, when moving across machines or JDK versions.

For example, the letter `é` in UTF-8 has two hex bytes `C3 A9`; in ISO-8859-1 it has only one byte `E9`. Reading the two UTF-8 bytes `C3 A9` as ISO-8859-1 produces two characters `Ã©` instead of one character `é` — a form of **mojibake** (garbled text due to encoding mismatch). If a charset cannot represent a character during writing, depending on the API or encoder configuration, the character may be replaced or the operation may fail; never assume every conversion preserves data.

Distinguish three things:

- `String.length()` counts *UTF-16 code units*, not UTF-8 bytes and not necessarily the number of user-perceived characters.
- `s.getBytes(charset).length` is the actual byte count after encoding with the specified charset.
- The default charset only matters for APIs that **actually use** it. An API that specifies UTF-8 or takes an explicit charset does not depend on the default charset.

## 2. Rules by JDK Version

| Version | Typical Default Charset | Consequence |
| --- | --- | --- |
| JDK 17 and earlier | Depends on OS, locale, and environment configuration at JVM startup; many Linux/macOS machines use UTF-8, while some Windows environments use code pages like `windows-1252` | Applications omitting the charset argument can behave differently across machines. |
| JDK 18 and later (JEP 400) | **UTF-8** is the default for Java SE APIs that use the default charset, unless a supported compatibility configuration is set | Higher consistency across operating systems; however, legacy data in other charsets may be misread. |

JEP 400 (**UTF-8 by Default**) took effect in **JDK 18**. This change affects the **JVM's default charset**; it does not mean every file on disk automatically converts to UTF-8, every third-party library defaults to UTF-8, or arbitrary bytes are valid UTF-8.

On JDK 18+, supported options when launching the JVM include:

- `-Dfile.encoding=UTF-8`: use UTF-8 as the default charset.
- `-Dfile.encoding=COMPAT`: select the default charset in a way compatible with JDK 17 and earlier, typically picking up the host environment's encoding.

`COMPAT` was introduced to ease migration to JDK 18+; **do not assume it behaves identically on JDK 17**. `file.encoding` values other than `UTF-8` and `COMPAT` are unsupported under the newer JDK specification; avoid relying on behavior specific to one JDK build.

JDK 17 introduced the `native.encoding` property to observe the host environment's encoding. On JDK 18+, `Charset.defaultCharset()` can be UTF-8 even when `native.encoding` reports a different charset. `file.encoding` is a startup configuration property; **do not call `System.setProperty("file.encoding", "...")` mid-execution and expect readers, writers, and the default charset to switch consistently**.

## 3. Which APIs Are Affected and Which Are Not?

| Written with Default Charset (JDK/Environment Dependent) | Explicit, Stable Version |
| --- | --- |
| `text.getBytes()` | `text.getBytes(StandardCharsets.UTF_8)` |
| `new String(bytes)` | `new String(bytes, StandardCharsets.UTF_8)` |
| `new InputStreamReader(inputStream)` | `new InputStreamReader(inputStream, StandardCharsets.UTF_8)` |
| `new OutputStreamWriter(outputStream)` | `new OutputStreamWriter(outputStream, StandardCharsets.UTF_8)` |
| `new FileReader(file)` | `new FileReader(file, StandardCharsets.UTF_8)` |
| `new FileWriter(file)` | `new FileWriter(file, StandardCharsets.UTF_8)` |

`StandardCharsets.UTF_8` is a constant in `java.nio.charset` and always represents UTF-8. When a document or protocol requires a different charset (such as legacy files in `windows-1252`), specify **that exact charset** on both sides instead of forcing everything to UTF-8.

Several `java.nio.file.Files` methods already chose UTF-8 **even before JDK 18** when no charset was passed, such as:

- `Files.readString(path)`, `Files.writeString(path, text)`;
- `Files.newBufferedReader(path)`, `Files.newBufferedWriter(path)`;
- `Files.readAllLines(path)`.

Therefore, do not assume every overload lacking a charset parameter uses `Charset.defaultCharset()`. Read the contract of the **exact overload being called**. For binary data, `Files.readAllBytes(path)` simply returns bytes without decoding or using a charset.

**Important exception:** `System.out` and `System.err` may use an encoding tied to the console/standard streams, differing from `Charset.defaultCharset()`. On newer JDKs, `Console.charset()` and properties related to stdout/stderr help inspect this setup. Garbled text in a terminal alone does not prove the bytes in a file are wrong; inspect file, stream, and terminal encodings separately.

## 4. Java 17+ Example: Fixed Bytes vs. JVM-Dependent Default Charset

Create **`DefaultCharsetDemo.java`** (save the source file as UTF-8):

```java
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.HexFormat;

public class DefaultCharsetDemo {
    public static void main(String[] args) {
        String text = "Aé";

        byte[] utf8 = text.getBytes(StandardCharsets.UTF_8);
        String decodedCorrectly = new String(utf8, StandardCharsets.UTF_8);
        String decodedIncorrectly = new String(utf8, StandardCharsets.ISO_8859_1);

        System.out.println("String.length(): " + text.length());
        System.out.println("UTF-8 byte count: " + utf8.length);
        System.out.println("UTF-8 hex: " + HexFormat.of().withUpperCase().formatHex(utf8));
        System.out.println("UTF-8 round trip correct: " + text.equals(decodedCorrectly));
        System.out.println("ISO-8859-1 decode same text: " + text.equals(decodedIncorrectly));

        Charset actualDefault = Charset.defaultCharset();
        byte[] implicit = text.getBytes();
        System.out.println("Default charset: " + actualDefault.name());
        System.out.println("Default bytes match UTF-8: " + Arrays.equals(implicit, utf8));
        System.out.println("file.encoding: " + System.getProperty("file.encoding"));
        System.out.println("native.encoding: " + System.getProperty("native.encoding"));
    }
}
```

Compile and run from the terminal in the directory containing the file:

```bash
javac -encoding UTF-8 DefaultCharsetDemo.java
java DefaultCharsetDemo
```

**The first five lines have deterministic output** on Java 17+:

```text
String.length(): 2
UTF-8 byte count: 3
UTF-8 hex: 41C3A9
UTF-8 round trip correct: true
ISO-8859-1 decode same text: false
```

The remaining lines **depend on the JDK version, environment, and startup flags**. For example, on JDK 18+ with default settings, `Default charset: UTF-8` and `Default bytes match UTF-8: true`; `native.encoding` may match or differ from UTF-8 depending on the machine. There is no single exact stdout for `file.encoding` and `native.encoding` across all operating systems.

With JDK 18+, you can also run:

```bash
java -Dfile.encoding=UTF-8 DefaultCharsetDemo
java -Dfile.encoding=COMPAT DefaultCharsetDemo
```

On a machine whose native encoding is not UTF-8, the `COMPAT` run reveals the difference. If the native encoding is already UTF-8, both runs may produce `Default bytes match UTF-8: true`. On JDK 17, you can test `java -Dfile.encoding=UTF-8 DefaultCharsetDemo` to evaluate an application before upgrading, but only use `COMPAT` on JDK 18+.

**Explanation:** `"Aé"` has two UTF-16 code units yet becomes three UTF-8 bytes (`41 C3 A9`). Decoding the same UTF-8 bytes as ISO-8859-1 produces a different string; writing and reading must agree on the charset. `text.getBytes()` at the end of the example intentionally uses the default overload to highlight the risk; in application code, prefer the overload taking an explicit charset.

## 5. Writing and Reading Files with a Specified Charset

The snippet below is **illustrative code placed inside a method declaring `throws IOException`**, with imports `java.nio.file.Files`, `java.nio.file.Path`, and `java.nio.charset.StandardCharsets`:

```java
Path path = Path.of("message.txt");
String message = "Hello, Java";

Files.writeString(path, message, StandardCharsets.UTF_8);
String restored = Files.readString(path, StandardCharsets.UTF_8);
System.out.println(message.equals(restored)); // true
```

`Files.writeString` writes characters as UTF-8 bytes, and `Files.readString` reads them as UTF-8, independent of the JVM's default charset. If the charset argument is omitted in **these two specific methods**, their default is still UTF-8. When a file comes from an external system, first determine the actual source charset: choose UTF-8 for UTF-8 data, or another charset if the source specification dictates it. Do not automatically treat a legacy file as UTF-8 merely by changing JVM flags.

A byte stream can also declare its encoding explicitly:

```java
// Two standalone conceptual lines; valid in/out streams are required.
var reader = new java.io.InputStreamReader(in, StandardCharsets.UTF_8);
var writer = new java.io.OutputStreamWriter(out, StandardCharsets.UTF_8);
```

In real applications, `in` and `out` are managed `InputStream`/`OutputStream` instances (typically using `try-with-resources`); the charset must match the protocol and source data.

## 6. When Upgrading JDK or Changing Environments, Which Bugs Surface Easily?

**Scenario 1 — legacy files using a Windows charset.** An application running on JDK 17 writes files with `new FileWriter(file)` when the default charset is `windows-1252`. After moving to JDK 21, `new FileReader(file)` typically decodes with UTF-8. If the file contains bytes that are not valid UTF-8, depending on the API, replacement characters or read errors may occur; if the bytes happen to be valid UTF-8 with a different meaning, wrong text appears. The right fix is to identify the file's original encoding, read it with that charset, and if needed, **perform a checked conversion** to UTF-8.

**Scenario 2 — byte exchange between services.** Service A uses `getBytes()` to send a message, and Service B uses `new String(bytes)` to receive it. If their default charsets differ, messages can be corrupted or lose data. Define the charset in the communication contract (usually UTF-8) and pass it explicitly on both sender and receiver.

**Scenario 3 — tests pass on a developer machine but fail in CI/containers.** Different OS images, locales, or JDK versions change the default charset (especially on JDK 17 and earlier). ASCII-only tests can stay green because many charsets encode ASCII identically. Add data with Vietnamese diacritics and non-ASCII characters, and verify both **output bytes** and decoded results.

**Scenario 4 — Java source files and terminal.** `.java` files saved in a legacy encoding may be misdecoded by `javac` if the compiler encoding changes. Pass `javac -encoding UTF-8` when source files are UTF-8; check IDE/build tool encoding settings. A terminal can display characters incorrectly even when bytes are properly encoded, so never use console appearance as the sole test.

## 7. Diagnosis and Safe Migration

You can inspect the JVM configuration with:

```bash
java -XshowSettings:properties -version
```

In the output, pay attention to `file.encoding` and (when available) `native.encoding`. Inside the application, print `Charset.defaultCharset().name()` as shown above to see the **actual** default charset. On JDK 18+, compare a default run against `-Dfile.encoding=COMPAT` to uncover dependencies on legacy code pages. On JDK 17, test with `-Dfile.encoding=UTF-8` to prepare for upgrading.

Steps to investigate and fix a mojibake bug:

1. Capture the **original** bytes at the source (inspect hex or log raw bytes); preserve the original before making changes.
2. Identify the charset mandated by the format, protocol, headers, or producing system. If no contract exists, investigate rather than trusting the JVM default to "guess" correctly.
3. Decode using the source charset **once**, checking characteristic characters and invalid-data cases.
4. When standardization is needed, re-encode to UTF-8, update metadata/protocols, and test the read–write flow across environments.
5. Replace uses of `getBytes()`, `new String(bytes)`, `InputStreamReader`, `OutputStreamWriter`, `FileReader`, and `FileWriter` that omit a charset with overloads matching the data contract; audit third-party libraries and build options as well.

**Do not** "fix" garbled text by repeatedly converting between charsets or changing `file.encoding` globally without understanding the source bytes. Changing configuration can mask a bug in one stream while breaking another. If data already suffered lossy replacement during an earlier decode, changing the charset downstream cannot recover the original bytes.

## 8. Checklist for Writing Resilient Java

- Have an explicit encoding contract for files, HTTP bodies, CSVs, logs, or exchanged data; prefer UTF-8 when designing new formats.
- Use `StandardCharsets.UTF_8` or the format-specified charset when converting `String` ⇄ `byte[]` and when constructing readers/writers.
- Do not equate the default charset with `native.encoding`, `.java` source encoding, console charset, locale, or the actual encoding of an existing file.
- Test non-ASCII characters on the target JDK/deployment environment; validate both bytes and decoded strings.
- Treat `-Dfile.encoding=COMPAT` as a testing/transition tool on JDK 18+, while passing explicit charsets is the long-term solution.

## Official Documentation

- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400).
- [Oracle JDK 18 Release Notes — JEP 400](https://www.oracle.com/java/technologies/javase/18-relnote-issues.html).
- [Oracle Java SE 21 Internationalization Guide — Supported Encodings](https://docs.oracle.com/en/java/javase/21/intl/supported-encodings.html).
- [Java 17 API — `FileReader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/FileReader.html).
