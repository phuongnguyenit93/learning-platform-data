# Console.charset and Actual Console Encoding

## 1. Why Can the Console Display Accented Text Incorrectly?

A Java program may hold valid Unicode text in memory, yet the terminal displays garbled characters, question marks, or strings like `Tiáº¿ng Viá»‡t`. The cause usually lies in **character encoding (charset) mismatches between components**, not necessarily in a corrupted Java string.

A simplified path for output data:

~~~text
Java String
    |
    | encode using a Charset
    v
Byte sequence
    |
    | System.out / Console.writer / pipe
    v
Terminal or receiving program
    |
    | decode using the charset it uses
    v
Displayed characters
~~~

If Java encodes using UTF-8 while the terminal decodes using a different code page, the same byte sequence will be misinterpreted. Input has the analogous problem: the terminal sends bytes in charset A while the program reads and decodes them using charset B.

In Java 17, the key API for the console is **`Console.charset()`**. This method was added in Java 17 to report the charset used by a `Console` instance. It helps distinguish the console's charset from the JVM's default charset.

Concepts to keep separate:

- **`String`:** text data in Java, represented as UTF-16 code units.
- **`Charset`:** rule for converting between characters and bytes, such as UTF-8.
- **`Console.charset()`:** the charset used by a `Console` object if the JVM has a console.
- **`Charset.defaultCharset()`:** the JVM's default charset for APIs that rely on the default charset.
- **Terminal/IDE/pipe/file:** the destination or source of bytes; each can have its own encoding configuration.

No single charset automatically represents every input/output path of a Java process.

## 2. A Java String Is Not a UTF-8 Byte Sequence

### 2.1. String Stores Character Content, Not Terminal Encoding

A Java `String` is a sequence of characters in Java's Unicode model. At the API level, methods like `length()` and `charAt()` operate on UTF-16 code units:

~~~java
String text = "Tiếng Việt";
System.out.println(text.length());
System.out.println(text.charAt(0));
~~~

A `String` does not remember whether it originated from UTF-8, a Windows code page, or another charset. A charset is only needed when converting text to bytes or bytes to text.

For example, the same string can be encoded into different byte sequences:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

String text = "Tiếng Việt";

byte[] utf8 = text.getBytes(StandardCharsets.UTF_8);
byte[] utf16 = text.getBytes(StandardCharsets.UTF_16);

System.out.println(Arrays.toString(utf8));
System.out.println(Arrays.toString(utf16));
~~~

The two byte arrays differ, yet both can be decoded back to the same content when the matching charset is used.

### 2.2. Charsets Must Match at Both Ends

~~~java
String original = "Xin chào";
byte[] bytes = original.getBytes(StandardCharsets.UTF_8);

String decodedCorrectly =
        new String(bytes, StandardCharsets.UTF_8);
String decodedWrongly =
        new String(bytes, StandardCharsets.ISO_8859_1);
~~~

`decodedCorrectly` preserves the original content. `decodedWrongly` produces a different character string because UTF-8 bytes are decoded under ISO-8859-1 rules.

This is the fundamental principle behind mojibake: **bytes encoded under one charset are read under another**.

### 2.3. Unicode Code Points and UTF-16 Code Units

For ordinary Vietnamese letters, one character typically corresponds to one UTF-16 code unit. However, Unicode also includes characters outside the Basic Multilingual Plane—such as certain emoji—that require a surrogate pair:

~~~java
String emoji = "😀";

System.out.println(emoji.length()); // 2 UTF-16 code units
System.out.println(emoji.codePointCount(0, emoji.length())); // 1 code point
~~~

This is not a charset bug. It is how Java represents supplementary code points in UTF-16. When handling general Unicode, distinguish code unit counts, code point counts, and post-encoding byte counts.

## 3. Charset.defaultCharset() and Console.charset() Are Different

### 3.1. The JVM Default Charset

`Charset.defaultCharset()` returns the default charset used by the JVM for APIs that do not specify a charset explicitly:

~~~java
import java.nio.charset.Charset;

System.out.println(Charset.defaultCharset());
~~~

On Java 17, **do not assume the default charset is always UTF-8 across all operating systems and configurations**. JEP 400 standardized UTF-8 as the default charset starting in JDK 18. Java 17 predates that change; the default charset can depend on the environment and launch configuration.

When writing code that must run on Java 17 and newer JDKs, specify charsets explicitly for files, protocols, and exchanged data. Do not rely on the default charset when a data format requires UTF-8.

### 3.2. The Console's Charset

Java 17 introduced `Console.charset()`:

~~~java
import java.io.Console;
import java.nio.charset.Charset;

Console console = System.console();
if (console != null) {
    Charset consoleCharset = console.charset();
    console.printf("Console charset: %s%n", consoleCharset.name());
} else {
    System.out.println("No interactive console available");
}
~~~

`Console.charset()` returns the charset used by the **`Console` instance**. That charset can differ from `Charset.defaultCharset()`. Therefore:

- Do not use `Charset.defaultCharset()` to conclude with certainty which charset the terminal uses to decode bytes.
- Do not use `Console.charset()` to conclude that every file or pipe in the application uses that charset.
- When a `Console` is available, prefer `Console.reader()`, `Console.writer()`, `readLine()`, and `printf()` for console interaction because these APIs are tied to the `Console` instance.
- When no `Console` is available, determine standard stream encoding based on the runtime environment's contract.

### 3.3. Why Doesn't Console.charset() Replace defaultCharset()?

The two APIs answer two different questions:

| API | Question Answered |
|---|---|
| `Charset.defaultCharset()` | What is the JVM's default charset for APIs relying on the default charset? |
| `console.charset()` | Which charset does the current `Console` instance use? |

For example, an application might run in an environment where the interactive console uses a terminal-supplied charset while log files are written explicitly in UTF-8. There is no reason to force both destinations to use the same encoding.

## 4. System.console() Can Return null

### 4.1. Not Every Java Process Has a Console

`System.console()` returns the `Console` object attached to the JVM if the environment provides a suitable console. It can return `null`, for example when:

- The program runs inside certain IDEs where standard input/output is redirected.
- The program runs as a service or background process.
- Standard input/output is connected to a pipe or file rather than an interactive terminal.
- The execution environment does not attach a console to the process.

Therefore, the following is unsafe:

~~~java
// May throw NullPointerException if no Console is available.
// Charset charset = System.console().charset();
~~~

Always check for `null`:

~~~java
Console console = System.console();

if (console == null) {
    // No interactive console available.
} else {
    System.out.println(console.charset());
}
~~~

Do not write application logic assuming `System.console()` is always non-null just because it works on a developer workstation. When running in CI, an IDE, a container, or as a service, the result can differ.

### 4.2. Console and Standard Streams Are Related but Not Identical

Java has three standard streams:

- `System.in`: input byte stream.
- `System.out`: standard output byte stream, of type `PrintStream`.
- `System.err`: error output byte stream, of type `PrintStream`.

`Console` provides an API geared toward console interaction, including a reader, writer, line reading, password reading, and formatting. If standard streams are redirected, the JVM still has `System.in/out/err`, yet may have no `Console`.

Do not equate them:

~~~text
System.out != Console.writer()
System.in  != Console.reader()
~~~

They may target the same device during a run, but they are distinct APIs and data paths. The `Console`'s charset is not proof of the charset of every stream.

## 5. Using Console.charset() Properly on Java 17

### 5.1. Reading and Writing via the Console API

~~~java
import java.io.Console;
import java.nio.charset.Charset;

public class ConsoleCharsetDemo {
    public static void main(String[] args) {
        Console console = System.console();

        if (console == null) {
            System.err.println(
                    "No interactive console; please run in a suitable terminal."
            );
            return;
        }

        Charset charset = console.charset();
        console.printf("Console charset: %s%n", charset.name());

        String name = console.readLine("Enter name: ");
        console.printf("Hello, %s!%n", name);
        console.flush();
    }
}
~~~

Here:

1. Check that `Console` exists before using it.
2. Retrieve the console's actual charset with `charset()`.
3. Use `readLine` and `printf` to interact via `Console`.
4. Call `flush()` when you need to ensure output is pushed out before continuing.

If `Console` does not exist, this example cannot use `console.charset()`; switch to a standard-streams policy or report that the application requires interactive mode.

### 5.2. Using Console.reader() and Console.writer()

`Console` provides:

- `reader()`: a `Reader` for reading text from the console.
- `writer()`: a `PrintWriter` for writing text to the console.
- `charset()`: the charset used by the `Console`.

~~~java
import java.io.Console;
import java.io.Reader;
import java.io.PrintWriter;

Console console = System.console();
if (console != null) {
    Reader reader = console.reader();
    PrintWriter writer = console.writer();

    writer.println("Enter data using the Console charset:");
    writer.flush();

    // In real applications, you can wrap reader in BufferedReader
    // to call readLine() when needed.
}
~~~

There is no need to manually create an `InputStreamReader(System.in, console.charset())` just to replace the Console API when the console reader is already available. Using Console's own APIs reduces the risk of accidentally reading the same stream through multiple wrappers or mixing buffering mechanisms.

### 5.3. Reading Passwords

`Console` also provides `readPassword()` to read a password without echoing characters to the screen:

~~~java
Console console = System.console();
if (console == null) {
    throw new IllegalStateException("Interactive console required");
}

char[] password = console.readPassword("Password: ");
if (password != null) {
    try {
        // Authenticate password here.
    } finally {
        java.util.Arrays.fill(password, '\0');
    }
}
~~~

`readPassword()` returns a `char[]` so the caller can clear its contents after use. This is preferable to reading a password as a `String` if you want to reduce how long secret data lingers in memory. It does not replace secure authentication or password-storage practices.

## 6. Standard Input/Output When No Console Is Available

### 6.1. Choosing a Charset According to the Stream Contract

If a program runs through a pipe, file redirection, or in a headless/non-console environment, identify the charset agreed upon by the calling and receiving programs. For protocols controlled by your application, UTF-8 is usually a good choice:

~~~java
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

BufferedReader reader = new BufferedReader(
        new InputStreamReader(System.in, StandardCharsets.UTF_8)
);

String line = reader.readLine();
~~~

This snippet declares that bytes from `System.in` must be decoded as UTF-8. That works when the input producer also sends UTF-8. If the terminal or piped process sends bytes in another charset, specifying UTF-8 on the receiving side will not fix the sender.

### 6.2. Writing Explicit UTF-8 to Standard Output

~~~java
import java.io.BufferedWriter;
import java.io.OutputStreamWriter;
import java.io.Writer;
import java.nio.charset.StandardCharsets;

Writer utf8Output = new BufferedWriter(
        new OutputStreamWriter(System.out, StandardCharsets.UTF_8)
);

utf8Output.write("Hello, Vietnam!");
utf8Output.newLine();
utf8Output.flush();
~~~

Here the application actively encodes to UTF-8 before writing bytes to `System.out`. The reading side (terminal, pipe, or another program) must also decode as UTF-8.

When using an explicit wrapper like this, stick to one output path for that content and flush at appropriate times. Do not arbitrarily mix `System.out.println()` with a `Writer` that has its own charset/buffer, as output may interleave or appear out of order.

Do not close `System.out` or `System.in` when merely wrapping them in an application; closing the wrapper usually closes the underlying stream as well. Normally you should only flush and let the process manage standard stream lifecycles.

### 6.3. No Single Charset Automatically Suits Every Terminal

If the program writes UTF-8 while the terminal decodes in a different encoding, output will still be wrong. If the program writes in the console charset while output is redirected to a file/pipe where the receiver expects UTF-8, data can also break.

Distinguish these scenarios:

| Scenario | How to Choose Charset |
|---|---|
| Interacting with a real Console | Use `Console.reader()/writer()`; query `Console.charset()` when needed |
| Communicating with a pipe/file via an application-defined protocol | Specify the protocol's charset, usually UTF-8 |
| Reading a file whose charset is defined in a specification | Use the file's exact charset; do not infer it from the console |
| Running in an IDE or CI without a Console | Use standard streams with an explicitly configured or agreed-upon encoding |

## 7. Charset.defaultCharset() on Java 17 and Newer JDKs

### 7.1. Java 17 Should Not Be Assumed to Default to UTF-8

JEP 400 standardized UTF-8 as the default charset starting in **JDK 18**. Because this lesson targets Java 17, keep the version boundary clear:

- On Java 17, the default charset usually depends on the OS/JVM environment and can vary across machines.
- Starting in JDK 18, UTF-8 becomes the default charset under the new policy, while console cases still follow dedicated console rules.
- `Console.charset()` remains the API to call when asking for the `Console` instance's charset, rather than the general default charset.

Do not rely on Java 17's default behavior when designing a file or protocol whose specification requires UTF-8. Specify the charset explicitly.

### 7.2. Avoiding Default-Charset Dependencies When Reading/Writing Files

Avoid:

~~~java
// May lead to assumptions about runtime default charset:
// Files.readString(path);
// Files.writeString(path, text);
~~~

Prefer:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

String content = Files.readString(path, StandardCharsets.UTF_8);
Files.writeString(path, content, StandardCharsets.UTF_8);
~~~

Overloads that name the charset explicitly keep file I/O consistent across machines and JDK versions.

### 7.3. Avoid Changing the Default Charset Just to Fix One Console

Altering the entire JVM's default charset configuration to work around one terminal can affect other files, libraries, or protocols. If the issue is confined to the console, use the Console API; if the issue is in a file or pipe, configure the proper charset at that boundary.

Do not treat a global setting as a substitute for clear encoding contracts on individual data streams.

## 8. Separating Console, File, and Network Encodings

### 8.1. Console

The console is the interactive interface with the person running the program. When `System.console()` exists:

~~~java
Console console = System.console();
if (console != null) {
    console.printf("Charset: %s%n", console.charset());
    String input = console.readLine("Input: ");
}
~~~

Use the Console API for interactive prompts, input lines, passwords, and formatted output.

### 8.2. Files

Text files require an encoding defined by a contract:

~~~java
Files.writeString(
        Path.of("message.txt"),
        "Xin chào",
        StandardCharsets.UTF_8
);
~~~

A file's charset should not depend on where the program was executed. A file created from a terminal, an IDE, or a service must still be readable under the same format.

### 8.3. Network and Protocols

A protocol must define how text maps to bytes. For example, HTTP often uses UTF-8 for modern formats, yet you must follow the charset declared in the media type or specific spec. Never use `Console.charset()` to encode network payloads.

~~~java
byte[] payload = jsonText.getBytes(StandardCharsets.UTF_8);
~~~

If an API requires another charset, use that charset per contract. Encoding belongs to the protocol, not the user's machine settings.

### 8.4. Processes and Pipes

When a Java program launches another program or consumes process output, encoding must be agreed upon between both processes. `Process.getInputStream()` and `getOutputStream()` are byte streams; wrap them with `InputStreamReader`/`OutputStreamWriter` using a known charset.

~~~java
Process process = new ProcessBuilder("some-command").start();

BufferedReader childOutput = new BufferedReader(
        new InputStreamReader(
                process.getInputStream(),
                StandardCharsets.UTF_8
        )
);
~~~

This example assumes the child process emits UTF-8. If the command specifies a different encoding, use that command's exact charset rather than guessing from the Java console's charset.

## 9. Detecting and Handling Encoding Errors

### 9.1. Recognizing Symptoms of Charset Mismatches

Common signs:

- Accented text turns into garbled sequences like `Tiáº¿ng Viá»‡t`.
- Certain characters become `?` or replacement characters `�`.
- Emoji or non-ASCII characters fail to display.
- The Java program prints properly in one terminal but breaks in an IDE or when redirected to a file.
- A file reads fine on the machine that created it but breaks on another machine.

Do not try to fix this by replacing broken characters after misdecoding. Once bytes are interpreted with the wrong charset, original information may already be lost; fix the charset at the encode/decode boundary and re-read from the original byte source.

### 9.2. Default Decoders May Replace Malformed Data

Many text-reading APIs replace invalid byte sequences with a replacement character depending on their decoder. If the application must **reject invalid bytes**, configure a decoder with `CodingErrorAction.REPORT`:

~~~java
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

var decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

BufferedReader reader = new BufferedReader(
        new InputStreamReader(System.in, decoder)
);
~~~

When input bytes are invalid UTF-8, reading can throw `MalformedInputException` (a subclass of `CharacterCodingException`) instead of silently substituting characters. This is useful for protocols, strict input validation, or file verification.

### 9.3. CharsetEncoder Can Also Report Encoding Errors

If a target charset cannot represent a character, an encoder can replace it or report an error depending on configuration. For formats requiring lossless encoding, configure:

~~~java
var encoder = StandardCharsets.UTF_8.newEncoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);
~~~

UTF-8 can encode every valid Unicode scalar value, though a Java `String` may contain unpaired surrogates. If strict data protection is needed, configure the encoder to catch those cases.

### 9.4. Do Not Confuse Charset with Font

Even when bytes are decoded accurately into Unicode characters, the terminal still needs a font containing the corresponding glyphs. If the font lacks support for a character, the terminal may display empty boxes or fallback symbols.

Distinguish:

- **Encoding/decoding:** converting bytes to code points/characters.
- **Font/rendering:** drawing characters visually on screen.

If Java produced the right content and the terminal decoded it properly yet characters still do not render, inspect the terminal's font or rendering capabilities. Changing the charset cannot supply missing glyphs.

## 10. Complete Example: Interactive Console and Pipe Fallback

Save the file as **ConsoleEncodingDemo.java**:

~~~java
import java.io.BufferedReader;
import java.io.Console;
import java.io.InputStreamReader;
import java.io.PrintWriter;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;

public class ConsoleEncodingDemo {

    public static void main(String[] args) throws Exception {
        Console console = System.console();

        if (console != null) {
            // Console has its own charset; use Console APIs.
            Charset charset = console.charset();
            console.printf("Console charset: %s%n", charset.name());

            String name = console.readLine("Enter name: ");
            console.printf("Hello, %s!%n", name);
            console.flush();
            return;
        }

        // No console: e.g. running via pipe/IDE/CI.
        // This example's contract specifies UTF-8 for stdin/stdout.
        BufferedReader reader = new BufferedReader(
                new InputStreamReader(
                        System.in,
                        StandardCharsets.UTF_8
                )
        );
        PrintWriter writer = new PrintWriter(
                new java.io.OutputStreamWriter(
                        System.out,
                        StandardCharsets.UTF_8
                )
        );

        writer.println("No Console available; falling back to UTF-8 per contract.");
        writer.flush();

        String name = reader.readLine();
        if (name == null) {
            writer.println("No input provided.");
        } else {
            writer.println("Hello, " + name + "!");
        }
        writer.flush();
    }
}
~~~

Compile on JDK 17:

~~~shell
javac --release 17 ConsoleEncodingDemo.java
java ConsoleEncodingDemo
~~~

To test the non-console branch, run the program in an environment where standard streams are redirected, such as via a pipe or an IDE/CI runner. The fallback branch in the example **assumes a UTF-8 contract**; if the input producer or output consumer does not use UTF-8, adjust the configuration to match the actual contract.

This example demonstrates choosing APIs based on environment type. It cannot automatically detect every encoding used by terminals or piped processes.

## 11. Diagnosing Incorrect Console Display

When encountering display issues, isolate exactly which boundary corrupts the bytes:

**Step 1 — Verify the String content.**  
Print basic diagnostics or inspect code points in the program to verify whether the data was already corrupted before encoding.

**Step 2 — Check whether a Console exists.**  
Call `System.console()`. If null, you cannot use `Console.charset()`; determine whether the program is running in an IDE, service, pipe, or file redirect.

**Step 3 — If a Console exists, read the charset from the Console itself.**  
Call `console.charset()`, and use `console.reader()` and `console.writer()` for interaction.

**Step 4 — Check the default charset separately.**  
Call `Charset.defaultCharset()` to inspect the JVM default. Do not conclude that it must equal the console charset.

**Step 5 — Check the receiving side.**  
The terminal, IDE, file viewer, or receiving process must decode bytes using the same charset Java used.

**Step 6 — Check font and rendering.**  
If characters decoded properly but lack glyphs, changing the charset will not solve it.

**Step 7 — Define a contract for each stream.**  
Interactive consoles can use the Console API; files and networks should use explicit charsets; pipes must agree on an encoding between both processes.

## 12. Common Misconceptions

| Misconception | Accurate Understanding |
|---|---|
| "Java Strings are stored in UTF-8." | Strings store text in Java's Unicode/UTF-16 model; UTF-8 is an encoding used when converting to bytes. |
| "Charset.defaultCharset() is always the terminal's charset." | The JVM default charset and the Console charset are two separate concepts. |
| "Java 17 always defaults to UTF-8." | JEP 400 standardized UTF-8 as default starting in JDK 18; Java 17 still depends on environment/configuration. |
| "System.console() is never null." | It can be null in IDEs, services, pipes, redirects, or environments without an interactive console. |
| "You can call System.console().charset() directly." | You must check whether `Console` is null first. |
| "Console.charset() is the encoding for all files and network I/O." | It only reports the `Console` instance's charset. Files and protocols need charsets per their own contracts. |
| "System.out and Console.writer() are guaranteed to be the same object." | They are different APIs/output paths; do not equate their charsets or buffering. |
| "Changing the default charset fixes every console issue." | The problem may lie in the terminal, pipe, file, or font; fix the exact boundary. |
| "Encoding corruption can be fixed by string replacement after decoding." | Once decoded incorrectly, information may be lost; re-read the original bytes with the correct charset. |
| "Box characters always mean a charset error." | The font or terminal may simply lack the glyph even though decoding succeeded. |
| "Explicit UTF-8 guarantees the terminal displays text properly." | The receiving side must also decode UTF-8 and be able to render the characters. |
| "All console data must use UTF-8." | The console has its own charset; use the Console API or follow the actual environment contract. |

## 13. Practice Exercises

### Exercise 1 — Observing Charsets

Write a program that prints:

~~~java
System.out.println(Charset.defaultCharset());
System.out.println(System.console() == null);
~~~

If `Console` exists, also print `System.console().charset()`. Run it in different terminals and IDE/runners, and record the results. Explain why you cannot assume all three environments share the same configuration.

### Exercise 2 — Comparing Console and Standard Output

When `Console` is available, write:

~~~java
console.writer().println("Tiếng Việt: ă â ê ô ơ ư đ");
console.flush();
~~~

Then compare this with writing via `OutputStreamWriter(System.out, StandardCharsets.UTF_8)`. State what charset contract each output path has and how the terminal must be configured to display both properly.

### Exercise 3 — Inspecting UTF-8 Bytes

Encode `"Xin chào Việt Nam"` with UTF-8, print the byte array in hex, and decode it back with UTF-8. Then decode the same bytes with a different charset and explain mojibake.

### Exercise 4 — Handling a Null Console

Write a program that:

- Uses `Console.reader()`/`Console.writer()` if `Console` is available.
- Otherwise reads/writes standard streams using UTF-8 per contract.
- Does not close standard streams.
- Flushes output at the right moments.

Run it in an interactive terminal and through a pipeline/IDE runner, noting which branch executes.

### Exercise 5 — Rejecting Invalid UTF-8 Bytes

Create a `CharsetDecoder` with `CodingErrorAction.REPORT`, then decode a valid byte sequence and an invalid byte sequence. Observe the exception and explain the difference between `REPORT` and replacement behavior.

### Exercise 6 — Distinguishing Font from Charset

Pick a character unsupported by your current terminal font. Verify its code point in Java, write UTF-8 bytes, and decode them back. If the text remains intact inside Java while the terminal shows a box glyph, explain why this is a font/rendering issue.

## 14. Self-Check Questions

1. In which Java version was `Console.charset()` introduced?
2. What question does this method answer?
3. Why can't `Console.charset()` replace `Charset.defaultCharset()` in all situations?
4. When can `System.console()` return null?
5. What is the difference between `System.in/out/err` and `Console.reader()/writer()`?
6. Does a Java `String` store the charset used to create it?
7. Why does decoding UTF-8 bytes with another charset produce mojibake?
8. In which JDK did JEP 400 change the default charset?
9. Why should files and network protocols specify charsets explicitly?
10. When no `Console` is available, how do you choose the encoding for standard streams?
11. Why shouldn't you close `System.in` or `System.out` when merely wrapping them?
12. When should you use `CodingErrorAction.REPORT`?
13. Why can a box glyph indicate a font issue rather than an encoding error?
14. Does `Console.charset()` report the encoding of a pipe or file redirect?

## 15. References

- [Java SE 17 API — Console](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Console.html): `charset()`, `reader()`, `writer()`, `readLine()`, `readPassword()`.
- [Java SE 17 API — System.console()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#console()): conditions under which the JVM provides a Console.
- [Java SE 17 API — Charset](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/Charset.html): default charset and charset mechanisms.
- [Java SE 17 API — StandardCharsets](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html): standard charsets, including UTF-8.
- [Java SE 17 API — InputStreamReader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStreamReader.html): decoding bytes into characters with a specified charset or decoder.
- [Java SE 17 API — OutputStreamWriter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStreamWriter.html): encoding characters into bytes.
- [OpenJDK JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): default charset change standardized in JDK 18 and its relationship with console environments.
- [Java SE 17 API — CodingErrorAction](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CodingErrorAction.html): handling invalid input during encoding and decoding.

When handling consoles on Java 17, query `Console.charset()` if the JVM provides a `Console` and use the Console's own reader/writer APIs for interaction. When working with files, networks, or pipes, specify the charset according to the data contract. Keeping the JVM charset, Console charset, and receiving-device encoding clearly separated makes it easy to diagnose display issues rather than altering global application configuration blindly.
