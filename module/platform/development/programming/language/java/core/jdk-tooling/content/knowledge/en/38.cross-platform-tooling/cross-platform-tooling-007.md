# Terminal Encoding in Java

**Terminal encoding** is the rule for converting between characters and bytes when a program reads data from a terminal or writes data to a terminal. For Java applications, encoding errors often appear when the program, shell, operating system, terminal emulator, or log receiver do not agree on a charset.

For example, Java creates the string `Xin chào` in memory. When writing to `System.out`, the string is encoded into bytes. The terminal emulator receives the bytes and decodes them to render characters on the screen. If Java encodes as UTF-8 but the terminal decodes using a different code page, the user might see `Xin chÃ o` or replacement characters. Conversely, if the terminal sends bytes in one encoding but Java reads them with another charset, input data is also corrupted.

To handle this properly, you need to separate four concerns:

1. **Data encoding:** which charset does the file, network protocol, pipe, or terminal use?
2. **Java stream encoding:** which charset are `System.in`, `System.out`, and `System.err` using to read/write?
3. **Environment encoding:** how are the shell, locale, Windows console code page, SSH, or container configured?
4. **Display capability:** does the terminal font have the appropriate glyphs and rendering support?

Not every garbled text issue is caused by Java. The charset may be correct while the font is missing glyphs; or the bytes may be correct while the shell transforms data during a pipe/redirect.

## 1. Characters, Unicode, charsets, and bytes

The following concepts are related but not synonymous:

| Concept | Meaning | Example |
|---|---|---|
| Character | Unit of text in the application's context | Letter `A`, letter `ế` |
| Unicode code point | Numeric code representing a character in Unicode | `U+0041`, `U+1F600` |
| UTF-16 code unit | 16-bit unit used in Java's `String` representation | One `char` is one code unit |
| Charset | Rule for mapping characters/code points to bytes and vice versa | UTF-8, UTF-16LE, windows-1258 |
| Byte | Actual unit of data transmitted over a stream or stored in a file | `C3 A0` |
| Terminal code page | Encoding that a console/terminal uses for input or output data | Windows code page 65001 |

Java `String` represents text using UTF-16 code units. This does not mean every Java string is stored as UTF-8 or that every character occupies one `char`.

For example:

- The letter `A` has code point `U+0041`, occupying one UTF-16 code unit.
- The letter `ế` can be represented by a single precomposed code point or by a sequence of code points consisting of the letter `e` and combining marks.
- The emoji `😀` has code point `U+1F600`, represented by two UTF-16 code units (a surrogate pair).

Therefore, `String.length()` returns the number of UTF-16 code units, not the number of code points or visible glyphs. If you need to count code points:

```java
String value = "A😀";

System.out.println("utf16.units=" + value.length());
System.out.println("code.points=" +
        value.codePointCount(0, value.length()));
```

Stdout:

```text
utf16.units=3
code.points=2
```

A single character visible to the user can also consist of multiple code points, such as a letter with combining diacritics or an emoji with a modifier. If you handle cursor positioning, terminal width, or string truncation by visible character, you need the concept of a grapheme cluster; `codePointCount()` still does not accurately count visible characters.

## 2. Data flow between Java and the terminal

A CLI program has two main data flows:

**Input**

Keyboard or pipe source produces bytes → terminal/OS or shell forwards bytes → `System.in` receives bytes → Java decoder converts bytes into `String`.

**Output**

Java creates `String` → `System.out` or `System.err` encoder converts to bytes → OS/shell/pipe forwards bytes → terminal emulator or log collector decodes bytes → font renders glyphs.

Each step can use a different configuration. For example:

- The Java source file is saved as UTF-8.
- The Java compiler reads the source as UTF-8.
- The Java `String` holds Unicode content.
- `System.out` encodes according to `stdout.encoding`.
- The terminal emulator displays using UTF-8.
- The terminal font supports Vietnamese.

If any link does not match, the output can be corrupted even when the source code and `String` are correct.

A pipeline can also change behavior when switching from an interactive terminal to redirection:

```sh
java TerminalEncodingDemo
java TerminalEncodingDemo > output.txt
java TerminalEncodingDemo | another-command
```

The first command usually runs with an interactive terminal. The next two redirect stdout to a file or pipe; the runtime may choose a different encoding and `System.console()` may return `null`. Therefore, test both interactive execution and CI/redirected execution.

## 3. Distinguishing the default charset from the terminal charset in Java

A common misconception is thinking `Charset.defaultCharset()` is always the terminal's encoding. This is incorrect.

Java has different default charsets for different purposes:

| API/stream | Charset used |
|---|---|
| `Charset.defaultCharset()` | Default charset of the Java runtime |
| `System.in` | `stdin.encoding` on JDKs that expose this property |
| `System.out` | `stdout.encoding` |
| `System.err` | `stderr.encoding` |
| `Console` output | `Console.charset()` |
| File I/O without specifying a charset | Usually uses the default charset of the corresponding API |
| File I/O with an explicit charset | The charset passed to the API |

Since JDK 18, per JEP 400, the default charset of Java SE APIs is UTF-8 across operating systems. Before JDK 18, the default charset usually depended on the locale and environment. On Windows, for example, it could be a code page such as `windows-1258`, `windows-1252`, or a charset matching the installed language.

However, `System.in`, `System.out`, and `System.err` have their own encodings. In JDK 25, the `stdin.encoding`, `stdout.encoding`, and `stderr.encoding` properties describe the encoding of the standard streams; their default values depend on the platform and user environment. They can differ from `file.encoding` and `native.encoding`.

`Console.charset()` was added in Java 17 and returns the charset used for `Console` write operations. This charset can differ from `Charset.defaultCharset()`.

**Practical rule:** do not use `Charset.defaultCharset()` to guess the terminal encoding. Check the specific stream or explicitly specify the encoding of the input/output protocol.

## 4. Differences between JDK 17 and JDK 18+

JDK 18 introduced JEP 400 — UTF-8 by Default:

- JDK 17 and earlier: the default charset is determined by the host environment and locale.
- JDK 18 and later: the default charset of Java SE APIs is UTF-8, unless the runtime is started with a supported compatibility mode.
- `native.encoding` was introduced in JDK 17 to indicate the encoding from the host environment.
- `System.in`, `System.out`, and `System.err` still have their own charsets; do not assume they are derived from `file.encoding`.

On JDK 18+, `file.encoding=COMPAT` can request the default charset behavior of earlier JDK releases. This is a compatibility option during migration and should not be used as a general encoding fix for new applications.

You should not call `System.setProperty("file.encoding", "UTF-8")` after the JVM has started to change the charset. The default charset is determined during runtime initialization; changing the property at runtime is not a reliable mechanism for changing the encoding of already-created streams.

If you need to test a legacy application, you can try running it on an older JDK with `-Dfile.encoding=UTF-8` to detect places that rely on the default charset. However, this does not automatically configure the terminal or shell.

## 5. Checking the actual charset of the JVM and terminal

Before modifying code, gather runtime information.

Java inspection commands:

```sh
java --version
java -XshowSettings:properties -version
```

In the output, pay attention to these properties:

- `file.encoding`
- `native.encoding`
- `stdin.encoding`
- `stdout.encoding`
- `stderr.encoding`
- `user.language`
- `user.country`
- `user.timezone`

Some properties may not be exposed on every JDK version. Do not assume a missing property means UTF-8.

Inspecting a Linux/macOS environment:

```sh
locale
locale charmap
printf '%s\n' "$LANG" "$LC_ALL" "$LC_CTYPE"
```

`LC_ALL` takes precedence over other locale variables. `LC_CTYPE` affects character classification and handling. `LANG` is the default locale when more specific variables are not set.

Inspecting Windows:

```powershell
chcp
[Console]::InputEncoding
[Console]::OutputEncoding
$PSVersionTable.PSVersion
```

`chcp` displays the active console code page. The Windows console has code pages for input and output; both directions can be configured separately via APIs. PowerShell also has its own encodings for cmdlets, files, and communication with native executables.

Check from within Java code using the program in the next section to see what the runtime actually observes.

## 6. Java 17+ example: terminal encoding diagnostic program

Create the file `TerminalEncodingDemo.java`:

```java
import java.io.Console;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

public class TerminalEncodingDemo {
    private static void printProperty(String name) {
        System.out.println(name + "="
                + System.getProperty(name, "<not exposed>"));
    }

    public static void main(String[] args) {
        System.out.println("java.version="
                + System.getProperty("java.version"));
        System.out.println("default.charset="
                + Charset.defaultCharset().name());

        printProperty("file.encoding");
        printProperty("native.encoding");
        printProperty("stdin.encoding");
        printProperty("stdout.encoding");
        printProperty("stderr.encoding");

        Console console = System.console();
        System.out.println("console.present=" + (console != null));
        if (console != null) {
            System.out.println("console.charset="
                    + console.charset().name());
        }

        String message = "Xin chào, Java!";
        System.out.println("message=" + message);
        System.out.println("message.utf8.hex="
                + HexFormat.of().formatHex(
                        message.getBytes(StandardCharsets.UTF_8)));
        System.out.println("message.utf16.units=" + message.length());
        System.out.println("message.codePoints="
                + message.codePointCount(0, message.length()));

        String supplementary = "A😀";
        System.out.println("emoji.utf16.units="
                + supplementary.length());
        System.out.println("emoji.codePoints="
                + supplementary.codePointCount(
                        0, supplementary.length()));
    }
}
```

Compile and run:

```sh
javac TerminalEncodingDemo.java
java TerminalEncodingDemo
```

Example output when running on JDK 25 in a UTF-8 Linux terminal:

```text
java.version=25.0.x
default.charset=UTF-8
file.encoding=UTF-8
native.encoding=UTF-8
stdin.encoding=UTF-8
stdout.encoding=UTF-8
stderr.encoding=UTF-8
console.present=true
console.charset=UTF-8
message=Xin chào, Java!
message.utf8.hex=58696e206368c3a06f2c204a61766121
message.utf16.units=15
message.codePoints=15
emoji.utf16.units=3
emoji.codePoints=2
```

The exact version and encoding properties depend on the JDK/OS/terminal. When run from an IDE, CI, or with redirection, `console.present` is usually `false`; in that case there is no `console.charset` to read. The sample output only illustrates a UTF-8 environment, not a guaranteed result on every machine.

The hex string of the message helps distinguish encoding errors from display errors. If the UTF-8 bytes are correct but the screen still displays incorrectly, check how the terminal decodes and its font.

## 7. Reading interactive input and piped input

When the application needs to read from the keyboard, prefer `Console` if available:

```java
Console console = System.console();

if (console != null) {
    String line = console.readLine("Nhập tên: ");
    System.out.println("received=" + line);
} else {
    System.err.println("Không có interactive console.");
}
```

`System.console()` returns `null` when the JVM has no attached console, such as in an IDE, CI, or when standard input/output is redirected. Do not use `System.console()` as the sole way to read data if the application needs to support pipes.

For a pipe with a UTF-8 contract, specify the charset explicitly:

```java
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

public class Utf8PipeInput {
    public static void main(String[] args) throws Exception {
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(
                        System.in, StandardCharsets.UTF_8))) {
            String line = reader.readLine();
            System.out.println("received=" + line);
        }
    }
}
```

Run with UTF-8 input:

```sh
printf 'Xin chào\n' | java Utf8PipeInput
```

Stdout when the pipe sends UTF-8 and the output is read as UTF-8:

```text
received=Xin chào
```

This example defines the pipe protocol as UTF-8. If the program receives input from a source using a different encoding, configure the charset according to that source's contract. Do not swap the decoder's charset by "trial and error until it looks right", because data can be decoded incorrectly without throwing an exception.

With JDK 25, the `System` documentation recommends using `stdin.encoding` to convert `System.in` bytes to characters when following the platform encoding. For pipes controlled by the application, specifying UTF-8 directly is usually clearer and easier to test.

## 8. Writing output for terminal, pipe, and file

For interactive output, `System.out` is already configured by the JVM according to `stdout.encoding`. If you are only printing CLI messages, you can use:

```java
System.out.println("Xin chào");
System.err.println("Có lỗi xảy ra");
```

For file or protocol data, specify the encoding at the point of writing:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path path = Path.of("message.txt");
Files.writeString(path, "Xin chào", StandardCharsets.UTF_8);

String content = Files.readString(path, StandardCharsets.UTF_8);
System.out.println(content);
```

Do not rely on the default charset to read/write files whose format specifies UTF-8. The same application might run on JDK 17 and JDK 25; specifying the charset explicitly keeps behavior consistent.

If the application outputs data for another program to read, treat stdout as a protocol stream. Choose an explicit encoding, delimiter, line ending, and error handling. Avoid mixing diagnostic messages into stdout if stdout carries JSON, CSV, or machine-readable data; send diagnostic messages to stderr.

Do not close `System.in`, `System.out`, or `System.err` while the application still needs them. When wrapping a stream, only flush when needed; closing the wrapper can close the underlying standard stream as well.

## 9. Using Console and standard stream charsets

`Console` is suited for interactive CLI applications:

- `System.console()` retrieves the console attached to the JVM if present.
- `Console.readLine()` reads a line from the console.
- `Console.readPassword()` reads a password without echoing characters.
- `Console.writer()` writes text through the console.
- `Console.charset()` returns the charset used for console write operations, available since Java 17.

`Console.charset()` is not the charset of every file or every pipe. When `System.console()` is `null`, there is no `Console` object to query.

In JDK 25, the following properties describe the standard streams:

| Property | Stream |
|---|---|
| `stdin.encoding` | `System.in` |
| `stdout.encoding` | `System.out` and console output |
| `stderr.encoding` | `System.err` |

These properties default to the platform/user environment. JDK 25 documentation allows starting the JVM with `UTF-8` for the corresponding properties. Do not set an arbitrary value unsupported by the runtime; ensure the terminal/pipe at the other end also uses UTF-8.

Example on a JDK that supports these properties:

```sh
java -Dstdin.encoding=UTF-8 -Dstdout.encoding=UTF-8 -Dstderr.encoding=UTF-8 TerminalEncodingDemo
```

This command is only appropriate when both the input source and output destination send/receive UTF-8. If the terminal is using a different code page, forcing Java to output UTF-8 can make the display worse.

`file.encoding` controls the default charset of APIs that depend on the default charset. It is not a master switch to change terminal input/output. Do not confuse `file.encoding`, `native.encoding`, `stdin.encoding`, and `stdout.encoding`.

## 10. Windows Command Prompt and console code pages

Windows has multiple encoding layers: Unicode inside applications, console input code page, console output code page, ANSI code page, OEM code page, and shell encoding.

`chcp` displays or changes the active console code page:

```cmd
chcp
chcp 65001
chcp
```

Code page `65001` is UTF-8. Run the Java application after changing the code page so the new process picks up the new setting. The Windows console has separate code pages for input and output; Windows APIs allow querying or setting the two values independently.

Several points to note:

- Modern terminal emulators can use Unicode, but child processes are still affected by how the host provides standard streams.
- `chcp 65001` does not automatically change the charset of every file created by PowerShell.
- The terminal font must contain the glyphs to be displayed.
- `cmd.exe`, Windows Terminal, PowerShell, and IDE terminals can behave differently.
- If Java output is redirected to a file, inspect the file's bytes rather than just looking at the screen.

If you encounter garbled Vietnamese text in Command Prompt, check the code page, `stdout.encoding`, `stderr.encoding`, font, and JDK version. Do not rush to change the source file encoding if the compiler is already reading the source correctly.

## 11. Windows PowerShell 5.1 and PowerShell 7+

PowerShell has its own encodings for files, cmdlets, pipelines, and native commands. This is why a Java command can print correctly on screen while a redirected file contains unexpected bytes.

### Windows PowerShell 5.1

Windows PowerShell 5.1 has inconsistent default encodings across cmdlets. `-Encoding UTF8` usually creates UTF-8 with a BOM; `Default` uses the active ANSI code page; `Oem` uses the OEM code page. A UTF-8 script file without a BOM containing non-ASCII characters may be interpreted using the legacy code page.

When saving UTF-8 output, specify the encoding explicitly:

```powershell
java TerminalEncodingDemo | Out-File -FilePath output.txt -Encoding utf8
Get-Content output.txt -Encoding utf8
```

### PowerShell 7+

PowerShell 6 and later default to UTF-8 without BOM for many text output operations. PowerShell 7.1+ provides values such as `utf8`, `utf8NoBOM`, and `utf8BOM`; `utf8` defaults to no BOM.

Example:

```powershell
java TerminalEncodingDemo | Out-File -FilePath output.txt -Encoding utf8NoBOM
Get-Content output.txt -Encoding utf8
```

`$OutputEncoding` controls the encoding PowerShell uses when sending text through a pipeline to an external/native program. It does not control the encoding that `Out-File` or file cmdlets use when writing files.

Do not assume `>` behaves the same way between Windows PowerShell 5.1 and PowerShell 7. Specify `-Encoding` when saving text that needs to be exchanged across tools. For binary data, avoid passing it through a text pipeline; use a file/byte stream appropriate for your PowerShell version.

## 12. Linux and macOS: locale and UTF-8

On Linux/macOS, the locale usually determines the default encoding of many command-line tools. Check with:

```sh
locale
locale charmap
locale -a
```

Common variables:

- `LANG`: default locale.
- `LC_CTYPE`: character classification and charset rules.
- `LC_ALL`: overrides all other locale settings.

A UTF-8 environment can use:

```sh
export LANG=en_US.UTF-8
export LC_CTYPE=en_US.UTF-8
```

Or use a UTF-8 locale already available on the system, such as `C.UTF-8` if the distribution supports it:

```sh
export LANG=C.UTF-8
export LC_ALL=C.UTF-8
```

Not every image/container comes with `en_US.UTF-8` or `C.UTF-8` preinstalled. Check `locale -a` before configuring. If the locale has not been generated/installed, merely setting environment variables can cause tools to report an invalid locale or fall back.

Avoid setting `LC_ALL=C` when the application needs to read/write UTF-8 text. The traditional C locale typically uses an ASCII/POSIX environment; this can cause text-processing utilities to behave unexpectedly.

macOS typically uses UTF-8 in its default terminal. Even so, applications should still specify encodings explicitly for files and protocols rather than relying on the developer machine's locale.

## 13. SSH, WSL, containers, and CI logs

Encoding can change when an application runs across multiple environment layers.

### SSH

The local terminal and remote shell must agree on how characters are exchanged. SSH can forward locale variables such as `LANG` and `LC_*` if the client/server allow it. Check `locale` on the remote machine, not only on the local machine.

If the remote machine does not receive the locale, check `SendEnv` on the client and `AcceptEnv` on the server. Do not forward environment variables that contain secrets.

### WSL

WSL connects a Windows terminal to a Linux environment. Check the locale inside WSL using `locale` and verify that the host terminal supports the required font/glyphs. Do not assume the Windows Command Prompt code page determines the Linux locale inside WSL.

### Docker/containers

Containers need appropriate locale and terminal configuration. For example:

```sh
docker run --rm -it \
  -e LANG=C.UTF-8 \
  -e LC_ALL=C.UTF-8 \
  -e TZ=UTC \
  your-java-image
```

Minimal images may not have locale data installed. Verify the charset with `locale charmap` inside the container. When running a container without a TTY, `System.console()` usually returns `null`; the application must support pipes or redirected standard input.

### CI logs

CI runners usually capture stdout/stderr rather than displaying an interactive terminal. You should:

- Identify the encoding expected by the log collector.
- Use UTF-8 for text logs if the runner supports it.
- Print the JDK version and encoding properties in a diagnostic step.
- Never assume `System.console()` exists.
- Never mix binary output or archive files into text logs.
- Check both downloaded logs and logs rendered in the web UI.

## 14. BOM and file encoding

UTF-8 can have or omit a Byte Order Mark (BOM). A BOM is a byte sequence at the beginning of a file that helps some tools identify the encoding.

For UTF-8 files exchanged across multiple operating systems, UTF-8 without BOM is generally more compatible with Unix tools and modern utilities. However, some legacy tools have specific requirements.

Java does not automatically detect every charset solely from file contents. When reading a file, pass the correct charset:

```java
String text = Files.readString(
        Path.of("input.txt"),
        StandardCharsets.UTF_8);
```

If a file has a BOM and the reading API returns the BOM as the first character, handle it according to the file format. Do not blindly strip the first character because legitimate data might actually start with that character.

Avoid saving a UTF-8 file sometimes with a BOM and sometimes without, depending on the machine or shell. Choose one convention and verify with a byte-level tool.

## 15. Charset conversion and data loss errors

When converting from one charset to another, not every character can be represented in the target charset.

For example, UTF-8 can represent all of Unicode. A legacy code page might not be able to represent certain Vietnamese letters, emojis, or mathematical symbols.

Many decoder/encoder APIs default to replacing invalid or unmappable characters with a replacement character. This can silently lose data while the program keeps running.

When data integrity matters, use `CodingErrorAction.REPORT` to detect errors:

```java
import java.nio.CharBuffer;
import java.nio.charset.Charset;
import java.nio.charset.CharsetEncoder;
import java.nio.charset.CodingErrorAction;

public class StrictEncodingDemo {
    public static void main(String[] args) throws Exception {
        Charset charset = Charset.forName("windows-1252");

        CharsetEncoder encoder = charset.newEncoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);

        encoder.encode(CharBuffer.wrap("Xin chào"));
        System.out.println("ENCODABLE");
    }
}
```

On a JDK that has the `windows-1252` charset, this example throws `UnmappableCharacterException` because the letter `à` is not in that charset's repertoire. Since the exception occurs before `println`, the `ENCODABLE` line is not printed.

For Vietnamese data, UTF-8 is usually the right choice for files, database protocols, HTTP payloads, and application-controlled pipes. If you must exchange data with a legacy system using a specific code page, determine the charset from the integration contract and test boundary characters.

## 16. Unicode normalization when comparing strings

Some characters can have multiple visually equivalent Unicode representations. For example, an accented letter can be encoded as a single precomposed code point or as a base letter plus a combining mark.

Two strings may look identical yet not be equal when compared by bytes or `String.equals()`.

If business logic requires comparing in normalized form, you can use Unicode normalization:

```java
import java.text.Normalizer;

String first = "é";
String second = "e\u0301";

String normalizedFirst =
        Normalizer.normalize(first, Normalizer.Form.NFC);
String normalizedSecond =
        Normalizer.normalize(second, Normalizer.Form.NFC);

System.out.println(normalizedFirst.equals(normalizedSecond));
```

Stdout:

```text
true
```

Only normalize when the data contract requires it. Do not arbitrarily normalize binary content, digital signatures, or data where byte identity is significant.

## 17. Configuring encoding in Gradle and Maven

Terminal encoding is one part of runtime I/O; source/resource encoding is another part of the build. Both must be configured.

### Gradle Kotlin DSL

```kotlin
plugins {
    java
}

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
}

tasks.withType<ProcessResources>().configureEach {
    filteringCharset = "UTF-8"
}
```

`options.encoding` specifies the charset for the Java source compiler. `filteringCharset` is used when the process resources task performs filtering. If you do not filter resources, still specify the encoding explicitly for tools or tasks that actually read text.

### Maven

```xml
<properties>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <project.reporting.outputEncoding>UTF-8</project.reporting.outputEncoding>
    <maven.compiler.encoding>UTF-8</maven.compiler.encoding>
</properties>
```

Setting encoding in the build helps the compiler and plugins process sources/resources consistently. It does not automatically configure the code page of the terminal running Maven.

If Vietnamese build logs are garbled while the source/resource artifacts are correct, check the Maven/Gradle process output encoding and the log collector separately. Do not change the source encoding just to fix a terminal log.

## 18. Logging and command-line output

Logging frameworks have separate encoders for console appenders and file appenders. Check the configuration of each appender:

- Console appender: the charset must match `stdout.encoding`/the terminal.
- File appender: choose UTF-8 or the encoding expected by the log ingestion system.
- JSON logs: use UTF-8 per the ingestion system's contract.
- Error output: check `stderr.encoding` separately.
- Log aggregation: verify the collector does not decode bytes using a different code page.

Do not apply a console charset configuration to a file appender if the two destinations have different encoding contracts.

For CLIs, keep stdout for results that other programs can parse and stderr for warnings/errors. If a command is piped to another program, the output should have a stable format and encoding, independent of terminal font or locale.

## 19. Diagnosing by bytes instead of only looking at the screen

When text displays incorrectly, inspect the raw bytes.

Linux/macOS:

```sh
printf 'Xin chào\n' > sample.txt
xxd -g 1 sample.txt
file -bi sample.txt
```

If `xxd` shows the UTF-8 bytes for `à` as `c3 a0`, the file data is already UTF-8 encoded. If the terminal displays it incorrectly, the issue likely lies in the decode/render step.

Windows PowerShell:

```powershell
[System.IO.File]::WriteAllText(
    "sample.txt",
    "Xin chào",
    [System.Text.UTF8Encoding]::new($false)
)
Format-Hex -Path sample.txt
```

`Format-Hex` displays the bytes of the file; it helps distinguish file-saving errors from text-display errors.

For Java output, redirect it to a file and inspect the bytes. Keep in mind, however, that the shell may perform conversions during redirection. If you need to inspect raw bytes, use a redirection mechanism appropriate for your shell/version and check the bytes with `xxd`, `od`, or `Format-Hex`.

## 20. Common errors and how to fix them

| Symptom | Possible cause | How to fix |
|---|---|---|
| Vietnamese displays as `Ã` or strange characters | UTF-8 decoded with another code page | Compare the Java output charset with the terminal code page |
| Characters appear as question marks `?` | Target charset cannot represent the characters | Use UTF-8 or the contract charset; enable a strict encoder when needed |
| Characters appear as boxes | Font is missing glyphs or terminal cannot render them | Check font/glyphs after confirming the bytes are correct |
| `System.out` is wrong even though `defaultCharset()` is UTF-8 | `stdout.encoding` differs from the default charset | Check stream encoding and console charset |
| `Scanner` reads Vietnamese incorrectly | `Scanner` uses a different charset from the input source | Pass an explicit charset to `Scanner` or use `Console` |
| `System.console() == null` when running in an IDE | IDE does not attach a direct terminal to the JVM | Support stdin pipes or run in a real terminal |
| CI behaves differently from local | CI redirects streams and uses a different environment | Check stdin/stdout encoding, locale, and log collector |
| Fails on Java 17 but works on Java 25 | Default charset changed in JDK 18 | Specify charsets explicitly; test JDK 17 compatibility |
| UTF-8 file has a strange first character | BOM treated as content | Check for BOM and handle according to the file format |
| PowerShell redirection produces a different encoding | PowerShell 5.1/7 have different defaults | Specify `Out-File -Encoding` or a .NET API with explicit encoding |
| Input through a PowerShell pipe is wrong | `$OutputEncoding` does not match the native program | Configure pipeline encoding per contract |
| Linux reports an invalid locale | Locale is not installed/generated in the image | Check `locale -a` and install the appropriate locale |
| Garbled text over SSH remote | Locale not forwarded or remote locale differs | Check `LANG`, `LC_*`, and SSH `SendEnv`/`AcceptEnv` |
| Accented characters compare as unequal | Different Unicode normalization forms | Normalize to NFC/NFD when required by business logic |
| Silent data loss without an exception | Decoder/encoder replaces bad characters with replacement | Use `CodingErrorAction.REPORT` and verify the charset |

## 21. Workflow for troubleshooting terminal encoding

When a user reports garbled Vietnamese text in a CLI:

1. Confirm whether the error occurs in input, output, file, pipe, or logs.
2. Run `java --version` and print the charset properties.
3. Check whether `System.console()` exists.
4. If a console exists, inspect `Console.charset()`.
5. On Windows, check `chcp`, PowerShell version, and console input/output encodings.
6. On Linux/macOS, check `locale`, `locale charmap`, `LANG`, `LC_CTYPE`, and `LC_ALL`.
7. Write a fixed test string and compare its UTF-8 bytes using a hex tool.
8. If the bytes are correct, inspect the terminal decoder and font.
9. If the bytes are wrong, inspect the Java stream encoder/decoder or shell pipeline.
10. Specify UTF-8 explicitly for files and protocols.
11. Test interactive terminal, file redirection, and pipe execution.
12. Re-run on both JDK 17 and JDK 18+ if the application must support both.

Change one layer at a time to pinpoint where the wrong conversion happens. Do not change `file.encoding`, code page, locale, and PowerShell preferences all at once, as that makes it hard to identify the root cause.

## 22. Checklist

- [ ] Distinguished Unicode code point, UTF-16 code unit, charset, and byte.
- [ ] Understood the input/output flow between Java, shell, and terminal.
- [ ] Distinguished `Charset.defaultCharset()` from the terminal charset.
- [ ] Understood that JDK 18+ uses UTF-8 as the default charset for Java SE APIs.
- [ ] Checked `stdin.encoding`, `stdout.encoding`, and `stderr.encoding` separately.
- [ ] Understood that `Console.charset()` exists since Java 17 and can differ from the default charset.
- [ ] Handled the case where `System.console()` returns `null`.
- [ ] Specified charsets explicitly for files and pipe protocols.
- [ ] Checked the Windows code page with `chcp`.
- [ ] Distinguished PowerShell 5.1 and PowerShell 7 encoding defaults.
- [ ] Checked Linux/macOS locale and locale availability.
- [ ] Checked SSH, WSL, containers, and CI log collectors.
- [ ] Handled BOM according to the file format.
- [ ] Used strict encoding when data loss is unacceptable.
- [ ] Checked Unicode normalization when text comparison is required.
- [ ] Verified bytes with a hex tool rather than relying solely on screen display.
- [ ] Configured source/resource encoding in Gradle or Maven.

## 23. References

- Oracle Java SE 25 API — System and standard streams: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/System.html
- Oracle Java SE 25 API — Console.charset(): https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/Console.html
- Oracle Java SE 25 Internationalization Guide — Default Charset and standard stream charsets: https://docs.oracle.com/en/java/javase/25/intl/internationalization-guide.pdf
- Oracle JDK 18 Release Notes — JEP 400, UTF-8 by Default: https://www.oracle.com/java/technologies/javase/18-relnote-issues.html
- Microsoft Learn — Console Code Pages: https://learn.microsoft.com/en-us/windows/console/console-code-pages
- Microsoft Learn — chcp command: https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/chcp
- Microsoft Learn — PowerShell Character Encoding: https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_character_encoding
- Java SE API — Charset, CharsetEncoder and CodingErrorAction: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/package-summary.html

Terminal encoding is the coordination between Java stream charsets, the shell, the operating system, the terminal emulator, and the data consumer. JDK 18+ standardizes the default charset of many Java APIs on UTF-8, but standard streams still have their own encodings. By explicitly specifying charsets for files/protocols, checking the terminal encoding properly, and verifying actual bytes, Java applications can handle Vietnamese and Unicode reliably across Windows, Linux, macOS, SSH, containers, and CI.