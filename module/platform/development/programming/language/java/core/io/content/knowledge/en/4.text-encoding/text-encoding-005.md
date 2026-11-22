# Default Charset, UTF-8 Since JDK 18, and API-Specific Exceptions

When a Java program converts between **bytes** and **text**, it must choose a `Charset`: the rule for encoding characters into bytes or decoding bytes into characters. When no charset is specified, *some* APIs use the **JVM's default charset**. Starting in **JDK 18**, Java applies **UTF-8 as the default charset** per JEP 400, giving many APIs more consistent behavior across Windows, Linux, and macOS. However, not every API lacking a charset parameter uses `Charset.defaultCharset()`: many APIs already mandate UTF-8, ISO-8859-1, the terminal device charset, or a format-defined charset.

What matters in practice is **identifying the exact rule of the API in use** and **specifying the charset explicitly at data boundaries** whenever data must remain compatible across environments or Java versions.

## 1. What Is a Charset and What Is the Default Charset Used For?

`String` objects in Java represent Unicode character sequences at the API level; when reading/writing files, sending data over the network, or exchanging data with external systems, strings must be represented as bytes. A character can occupy different numbers of bytes depending on the charset.

Example with the character `é`:

| Charset | Bytes in hexadecimal |
|---|---|
| UTF-8 | `C3 A9` |
| ISO-8859-1 | `E9` |
| US-ASCII | Cannot be represented directly; replacement or error behavior depends on the API/encoder |

If written as UTF-8 yet read as ISO-8859-1, the two bytes `C3 A9` can be decoded into `Ã©`: this is **mojibake** (text garbled due to mismatched encoding). This is not a bug with Vietnamese accents in `String`; it is an error caused by the two sides interpreting bytes under different rules.

`java.nio.charset.Charset.defaultCharset()` returns the JVM's default charset object. APIs *defined to use the default charset* will use this charset when no charset argument is passed. Therefore, distinguish among:

- **Default charset**: JVM-wide default, read via `Charset.defaultCharset()`.
- **Explicitly passed charset**: e.g., `StandardCharsets.UTF_8`; independent of the default charset.
- **Fixed charset per API contract**: e.g., `Files.readString(path)` defaults to UTF-8 regardless of the default charset.
- **Interactive environment charset**: e.g., console input/output, which may differ from `Charset.defaultCharset()`.
- **Format- or protocol-defined charset**: e.g., loading `Properties` from an `InputStream` using ISO-8859-1.

Do not infer solely from the fact that an API **has no charset parameter** that it necessarily uses the default charset.

## 2. Before and After JDK 18: What Changed?

JEP 400, effective from **JDK 18**, makes UTF-8 the standard default charset for Java SE APIs that depend on the default charset, unless the JVM is configured to change behavior via a supported mechanism.

| Version | Typical Default Charset | Impact |
|---|---|---|
| JDK 17 and earlier | Depends on OS, locale, and environment configuration at JVM startup | The same code without a charset may produce/read different bytes across machines |
| JDK 18 and later | **UTF-8 by default** across all platforms | APIs using the default charset behave more consistently |
| JDK 18+ with `-Dfile.encoding=COMPAT` | Falls back to JDK 17-style environment-derived charset determination | Used for testing and compatibility handling during upgrades |
| JDK 18+ with `-Dfile.encoding=UTF-8` | UTF-8 | Makes configuration intent explicit via startup flag |

For example, on a Windows machine using a legacy code page, JDK 17 might use `windows-1252` or `windows-31j` as the default charset, whereas JDK 18+ uses UTF-8 by default. However, **JDK 17 does not mean it always avoids UTF-8**: many Linux and macOS environments already defaulted to UTF-8 beforehand. The actual result must be checked on the running JVM.

The impact of the change lies in **encoding/decoding operations that depend on the default charset**. JEP 400 does not automatically re-encode previously written files, does not auto-detect legacy file charsets, and does not alter encoding contracts specifically defined by individual APIs.

### Two properties to distinguish

- `file.encoding` relates to the JVM's default charset selection. For JDK 18+, the specification-supported values to select this mechanism are `UTF-8` and `COMPAT` when passed at startup.
- `native.encoding` describes the charset originating from the environment/OS configuration, useful for identifying compatibility mode. It **can differ** from `file.encoding` when the default charset is UTF-8.

With JDK 18+, when running `-Dfile.encoding=COMPAT`, the default charset is derived from `native.encoding` under the compatibility mechanism; it may still be UTF-8 if the environment uses UTF-8. Do not expect `COMPAT` to always return a charset other than UTF-8.

**Do not treat `System.setProperty("file.encoding", "...")` after the program has started as a safe way to switch charsets.** The JVM and related components may have already initialized/cached the charset. If JVM-level adjustment is needed, pass the option at startup; if stable encoding at the data level is needed, pass `Charset` directly into the API.

## 3. Identifying the Charset on a Running JVM

Create file **`CharsetProbe.java`** saved in UTF-8:

~~~java
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public class CharsetProbe {
    public static void main(String[] args) {
        System.out.println("default = " + Charset.defaultCharset().name());
        System.out.println("file.encoding = " + System.getProperty("file.encoding"));
        System.out.println("native.encoding = " + System.getProperty("native.encoding"));

        String text = "\u00E9"; // Character é
        System.out.println("implicit = " + Arrays.toString(text.getBytes()));
        System.out.println("explicit UTF-8 = "
                + Arrays.toString(text.getBytes(StandardCharsets.UTF_8)));
    }
}
~~~

Compile with JDK 17+; the `-encoding UTF-8` flag ensures the compiler interprets the UTF-8 source file as intended:

~~~bash
javac -encoding UTF-8 CharsetProbe.java
java CharsetProbe
~~~

The first three lines and the `implicit` line **depend on the JVM/environment or startup flags**, so there is no single stdout identical across every machine. What remains invariant is:

~~~text
explicit UTF-8 = [-61, -87]
~~~

This line prints `byte[]` using Java's signed `byte` type, so the bytes `C3 A9` are displayed as `-61, -87`. These are still valid UTF-8 bytes for `é`.

On JDK 18+, test these two modes independently:

~~~bash
java -Dfile.encoding=UTF-8 CharsetProbe
java -Dfile.encoding=COMPAT CharsetProbe
~~~

When `UTF-8` is used as the default charset, the `implicit` line is also `[-61, -87]`. When `COMPAT` selects a different charset, this line **may change**—for instance, a character encoded as a single byte in ISO-8859-1 or another compatible encoding. Do not hard-code `native.encoding` or Windows charset results in tests running across multiple operating systems.

You can view additional startup properties with `java -XshowSettings:properties -version`. The most reliable way to know what default charset Java is actually using in code remains `Charset.defaultCharset()`.

## 4. APIs That Truly Depend on the Default Charset

In the following calls, if **no charset is passed**, character ↔ byte conversion relies on the JVM's default charset per the API contract:

| API / Example | Affected Area |
|---|---|
| `"text".getBytes()` | Encodes `String` to bytes |
| `new String(byteArray)` | Decodes bytes to `String` |
| `new InputStreamReader(inputStream)` | Decodes bytes from an input stream into characters |
| `new OutputStreamWriter(outputStream)` | Encodes characters when writing to an output stream |
| `new FileReader(file)`, `new FileWriter(file)` (constructors without a charset) | Reads/writes characters on files |
| `Scanner` or `Formatter` constructors that use the default charset with byte sources/targets | Converts characters at the I/O layer per the overload |

Example of an environment-dependent pair of calls:

~~~java
// Illustrative snippet: uses the default charset, which may differ between JDK 17 and 18+.
byte[] bytes = "Tiếng Việt".getBytes();
String decoded = new String(bytes);
~~~

If both operations happen inside the **same JVM** with no byte alteration, they usually return the original string for a charset supporting that text; however, **the generated bytes may differ across machines**. Writing a file on machine A and reading it on machine B is the boundary where encoding bugs readily surface, especially with charsets unable to represent all characters.

To control behavior, choose the overload taking a `Charset`:

~~~java
import java.nio.charset.StandardCharsets;

byte[] bytes = "Tiếng Việt".getBytes(StandardCharsets.UTF_8);
String decoded = new String(bytes, StandardCharsets.UTF_8);
~~~

This snippet is an **illustrative snippet** because it has no `main`; it shows how to specify UTF-8 independently of the default charset. `StandardCharsets.UTF_8` is a standard charset constant available on every Java SE implementation.

For streams, also pass it to the constructor:

~~~java
Reader reader = new InputStreamReader(input, StandardCharsets.UTF_8);
Writer writer = new OutputStreamWriter(output, StandardCharsets.UTF_8);
~~~

This is an illustrative snippet; `input` and `output` are already-opened streams that must be closed properly. For files, you can choose `FileReader`/`FileWriter` constructors accepting `Charset` on modern JDKs, or use `Files.newBufferedReader`/`Files.newBufferedWriter` accepting `Charset`.

## 5. Notable Exceptions: APIs Not Using the Default Charset

The change in JDK 18 **does not mean every Java API switched to UTF-8**. Some APIs already fixed UTF-8 earlier, some fix a different encoding, and some depend on the terminal/format.

| API or Scenario | Actual Rule |
|---|---|
| `Files.readString(path)`, `Files.writeString(path, text)` | Defaults to **UTF-8** per API contract (since these APIs appeared in JDK 11) |
| `Files.newBufferedReader(path)`, `Files.newBufferedWriter(path)` | Defaults to **UTF-8** even on JDK 17 |
| `Files.readAllLines(path)`, `Files.lines(path)` when no charset is specified | Defaults to **UTF-8** |
| `Properties.load(InputStream)`, `Properties.store(OutputStream, ...)` | Byte-based properties format uses **ISO-8859-1**, with Unicode escapes following specific rules |
| `Properties.load(Reader)`, `Properties.store(Writer, ...)` | Characters are already/being handled by `Reader`/`Writer`; charset is determined by whoever created the reader/writer |
| `PropertyResourceBundle` loading `.properties` files | Since JDK 9, tries UTF-8 by default with an ISO-8859-1 fallback when bytes are not valid UTF-8 per ResourceBundle rules; **not identical to `Properties.load(InputStream)`** |
| `System.out`, `System.err`, and console reading/writing | Console/stream charset may follow the terminal environment and need not equal `Charset.defaultCharset()`; governed by separate system rules |
| `FileInputStream`, `FileOutputStream`, `Files.readAllBytes` | Operate on **raw bytes**, performing no automatic text encoding/decoding |
| `InputStreamReader(input, someCharset)`, `new String(bytes, someCharset)` | Uses the **explicitly passed charset**, not the default |

Thus, moving from Java 17 → 18 may cause `new FileReader("old.txt")` to interpret bytes differently than before, whereas `Files.readString(path)` has always used UTF-8 and therefore **does not change charsets merely because of JEP 400**.

### 5.1. `Files` methods fixed to UTF-8

The convenience character-based file APIs of `java.nio.file.Files` generally default to UTF-8. This was already true prior to JDK 18:

~~~java
String content = Files.readString(path); // UTF-8
Files.writeString(path, content);         // UTF-8

try (BufferedReader reader = Files.newBufferedReader(path)) {
    String line = reader.readLine();      // UTF-8
}
~~~

This is an **illustrative snippet** requiring imports for `Files`, `Path`, `BufferedReader`, and `IOException`, as well as a declared `path`. These methods also provide overloads accepting a `Charset` to handle data in other encodings. Do not use `Charset.defaultCharset()` to guess the encoding of the overloads above.

### 5.2. `Properties.load(InputStream)` is the easiest case to mistake

The properties format read directly from bytes via `Properties.load(InputStream)` **did not switch to UTF-8 in JDK 18**. This API assumes **ISO-8859-1** for input bytes and supports Unicode escapes for other characters. By contrast, `Properties.load(Reader)` accepts characters already decoded by the reader using the charset chosen by the application.

For example, a UTF-8 byte file containing `name=Café`: using `load(InputStream)`, `é` may turn into `Ã©`; to load UTF-8 properly, wrap with `InputStreamReader` using `StandardCharsets.UTF_8` and then call `load(Reader)`.

In particular, do not mistakenly apply this rule to `ResourceBundle.getBundle(...)` loading `PropertyResourceBundle`, because properties-based resource bundle loading changed per JEP 226 starting in **JDK 9**. These are two APIs with different rules despite sharing the `.properties` file extension.

### 5.3. Console and `System.in/out/err` have their own rules

In terminal-launched applications, input and output bytes must match the encoding used by the terminal or host environment. JEP 400 intentionally does not force `System.out` and `System.err` to always use UTF-8 like `Charset.defaultCharset()`; unilaterally altering console output can garble characters in some environments.

- `System.out`/`System.err` are `PrintStream` instances whose encoding configuration ties to the terminal environment or related properties (such as `stdout.encoding` and `stderr.encoding`). Do not infer them from the default charset.
- `System.in` is a **byte stream**. When wrapped with `new InputStreamReader(System.in)` or `new Scanner(System.in)` without specifying a charset, the default wrapper itself may use the **default charset**, which does not necessarily match the terminal's encoding.
- For interactive input applications, consider `System.console()`/`Console` when a proper console is available; `System.console()` may return `null` when running inside an IDE, pipeline, or when I/O is redirected.
- On JDKs exposing `stdin.encoding`, `stdout.encoding`, and `stderr.encoding`, you may consult them per your deployment version's documentation to pick the matching charset. They are **not proof** that `file.encoding` always matches the console encoding.

When communicating over a protocol specifying UTF-8 or writing to a file, state UTF-8 explicitly where characters convert to bytes. For direct terminal interaction, account for the terminal device's characteristics.

## 6. Java 17+ Example: Verifying Fixed UTF-8 and ISO-8859-1 APIs

Create file **`CharsetApiRulesDemo.java`**, saved in UTF-8:

~~~java
import java.io.ByteArrayInputStream;
import java.io.InputStreamReader;
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.Properties;

public class CharsetApiRulesDemo {
    public static void main(String[] args) throws Exception {
        String text = "Caf\u00E9";
        byte[] utf8 = text.getBytes(StandardCharsets.UTF_8);

        System.out.println("UTF-8 bytes: " + Arrays.toString(utf8));
        System.out.println("Explicit decode: "
                + text.equals(new String(utf8, StandardCharsets.UTF_8)));

        Path file = Files.createTempFile("charset-rule-", ".txt");
        try {
            Files.write(file, utf8);
            System.out.println("Files.readString: "
                    + text.equals(Files.readString(file)));
        } finally {
            Files.deleteIfExists(file);
        }

        byte[] propertiesUtf8 = ("name=" + text + "\n")
                .getBytes(StandardCharsets.UTF_8);

        Properties byteProperties = new Properties();
        byteProperties.load(new ByteArrayInputStream(propertiesUtf8));
        System.out.println("Properties.load(InputStream): "
                + text.equals(byteProperties.getProperty("name")));

        Properties readerProperties = new Properties();
        try (Reader reader = new InputStreamReader(
                new ByteArrayInputStream(propertiesUtf8), StandardCharsets.UTF_8)) {
            readerProperties.load(reader);
        }
        System.out.println("Properties.load(Reader UTF-8): "
                + text.equals(readerProperties.getProperty("name")));
    }
}
~~~

Compile and run on JDK 17+:

~~~bash
javac -encoding UTF-8 CharsetApiRulesDemo.java
java CharsetApiRulesDemo
~~~

Consistent stdout on JDK 17+ (even when the default charset is not UTF-8):

~~~text
UTF-8 bytes: [67, 97, 102, -61, -87]
Explicit decode: true
Files.readString: true
Properties.load(InputStream): false
Properties.load(Reader UTF-8): true
~~~

Why does this output happen?

1. `text.getBytes(StandardCharsets.UTF_8)` produces environment-independent UTF-8 bytes. The character `é` encodes to `C3 A9`.
2. `new String(utf8, UTF_8)` decodes properly with the same charset; string comparison returns `true`.
3. `Files.readString(file)` without a charset still defaults to UTF-8 per its own contract; it returns the exact string, even on JDK 17.
4. `Properties.load(InputStream)` uses ISO-8859-1 and interprets the two UTF-8 bytes of `é` as two characters, so the string differs from the original value.
5. `Properties.load(Reader)` receives characters already decoded with UTF-8, so it reads the content accurately.

The program uses a temporary file and deletes it in `finally` so it does not overwrite any existing file. The example verifies **differences between API contracts**, without needing to change `file.encoding` to produce this difference.

## 7. Small Example of a Bug When Switching JDK Versions

Suppose a system previously ran on JDK 17 on a machine using an older charset, with code like:

~~~java
// Illustrative snippet: missing explicit charset at the data boundary.
try (FileWriter writer = new FileWriter("report.txt")) {
    writer.write("Café");
}
~~~

If the previous default charset was ISO-8859-1, `é` might have been written as byte `E9`. When upgrading to JDK 18+, the same code lacking a charset may write UTF-8, where `é` becomes `C3 A9`. An older application still expecting ISO-8859-1 will misread the new file; conversely, the upgraded application may also misread legacy data.

The durable solution is to **know the actual charset of the data and choose explicitly**. For example, when the system specifies that the file must be UTF-8:

~~~java
// Illustrative snippet: requires appropriate imports and IOException handling.
try (Writer writer = new OutputStreamWriter(
        new FileOutputStream("report.txt"), StandardCharsets.UTF_8)) {
    writer.write("Café");
}
~~~

Or in modern Java:

~~~java
Files.writeString(Path.of("report.txt"), "Café", StandardCharsets.UTF_8);
~~~

The snippets above only illustrate charset selection; for real files, consider creation/overwrite policies, permissions, and I/O errors. If **existing legacy data truly uses a legacy encoding**, read it with the **exact** legacy charset to transcode it to UTF-8; merely flipping a JVM flag or labeling old bytes “UTF-8” does not transform those bytes into UTF-8.

During data migration, decoding error handling is crucial: some default decoders may replace invalid bytes with a replacement character, masking data loss. Critical data should be verified using the right charset and an appropriately configured decoder to catch replacement errors or unmappable characters.

## 8. Testing JDK 17 → 18+ Migration

A useful testing workflow:

1. **Inventory locations relying on the default charset**: `new String(bytes)`, `String.getBytes()`, `FileReader/FileWriter`, `InputStreamReader/OutputStreamWriter`, and matching overloads of `Scanner` or `Formatter`. Cross-check each overload's contract.
2. **Identify byte origins**: legacy files, new files, configuration resources, terminal, network payloads, and partner data may use different charsets.
3. **Test with explicit UTF-8 on the legacy environment**: on JDK implementations supporting it, try `java -Dfile.encoding=UTF-8 ...` to detect upgrade impacts. For `javac`, use `-encoding UTF-8` when source files are saved in UTF-8.
4. **Test compatibility mode on JDK 18+**: `java -Dfile.encoding=COMPAT ...` for comparison during diagnosis; do not treat this as a long-term substitute for specifying encoding explicitly at data boundaries.
5. **Verify output by bytes and decoded content**: use a test suite containing ASCII, Vietnamese diacritics, non-Latin-1 characters, and existing data. An ASCII-only test rarely distinguishes UTF-8 from many legacy charsets.
6. **Keep APIs with specialized contracts intact**: `Properties.load(InputStream)` and `Files.readString` do not change meaning just because of JEP 400. If changing APIs, proactively evaluate format conversion.
7. **Test stdout/console separately**: a valid UTF-8 file does not prove the terminal is also interpreting stdout as UTF-8; distinguish terminal display from actual bytes in a file.

In projects, document the charset in file format or protocol specifications and test the write → read lifecycle on target environments. Do not rely on a developer's machine charset as a data contract.

## 9. Common Conceptual Pitfalls

| Misconception | Reality |
|---|---|
| “Java 17 always defaults to ANSI; Java 18 always uses UTF-8 across every API” | JDK 17 could already use UTF-8; JDK 18+ defaults to UTF-8 **for APIs using the default charset**, with exceptions remaining |
| “Omitting the charset always uses `Charset.defaultCharset()`” | Text-based `Files` APIs, `Properties.load(InputStream)`, and the console follow different rules |
| “`COMPAT` always means ISO-8859-1” | `COMPAT` uses an environment-compatible charset; it may be UTF-8 or another charset |
| “Calling `System.setProperty("file.encoding", "UTF-8")` switches all streams immediately” | Runtime configuration is unreliable for changing charsets already in use |
| “Upgrading to JDK 18 automatically converts all old files to UTF-8” | Stored bytes do not change; you must read with the source charset and encode to the target charset |
| “`System.out.println(...)` definitely outputs UTF-8 starting in JDK 18” | Console/stdout charset has its own rules; the terminal must also decode the bytes properly |
| “`.properties` is always ISO-8859-1” | `Properties.load(InputStream)` uses ISO-8859-1; `PropertyResourceBundle` since JDK 9 normally reads UTF-8 with fallback |
| “Testing with ASCII is enough” | For plain ASCII characters, many charsets produce identical bytes; non-ASCII characters are required to expose differences |

## 10. Key Takeaways

- **JDK 17 and earlier**: default charset depends on platform configuration; **JDK 18 and later**: defaults to UTF-8 per **JEP 400**.
- **`Charset.defaultCharset()`** reports the actual JVM default charset; on JDK 18+, you can test `-Dfile.encoding=UTF-8` or `-Dfile.encoding=COMPAT` at startup.
- Only APIs **that actually rely on the default charset** are affected accordingly; fixed-encoding APIs and raw byte streams do not change semantics automatically.
- **`Files.readString/newBufferedReader` default to UTF-8**, whereas **`Properties.load(InputStream)` uses ISO-8859-1**; these are the two clearest examples to contrast.
- **Console/stdin/stdout/stderr** have their own encoding rules; do not equate them with the default charset without checking.
- Whenever data must persist long-term or be exchanged across machines, **always state the charset explicitly**, typically `StandardCharsets.UTF_8`, and test both encoding and decoding.

### Official References

- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400)
- [Java SE — Charset.defaultCharset()](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/Charset.html#defaultCharset())
- [Java SE — Files](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html)
- [Java SE — Properties](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Properties.html)
- [Oracle — Supported Encodings](https://docs.oracle.com/en/java/javase/25/intl/supported-encodings.html)