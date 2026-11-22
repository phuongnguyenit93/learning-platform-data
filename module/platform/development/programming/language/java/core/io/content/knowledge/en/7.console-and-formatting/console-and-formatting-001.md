# System.in, System.out, and System.err in Java

## 1. What Are the Three Standard I/O Streams For?

A command-line program typically has three communication channels with the outside environment:

- **`System.in`** is **standard input (stdin)**: the input byte stream. It usually receives keyboard input when the program runs in a terminal, though it can also receive data from a file, pipe, or another program.
- **`System.out`** is **standard output (stdout)**: the normal output stream, intended for results that the user or calling program needs to receive.
- **`System.err`** is **standard error (stderr)**: a separate output stream, intended for errors, warnings, and diagnostic information.

In Java, all three belong to the `java.lang.System` class and can be accessed anywhere as `System.in`, `System.out`, and `System.err` without importing `System`.

```text
                            ┌───────────────────────────┐
keyboard / file / pipe ────>│ System.in  : InputStream   │
                            │                           │
                            │     Java Application      │
                            │                           │
terminal / file / pipe <────│ System.out : PrintStream   │
terminal / file / pipe <────│ System.err : PrintStream   │
                            └───────────────────────────┘
```

These three channels are **process streams**: when starting a program, the shell/OS usually attaches them to the terminal; the caller can redirect the streams **without modifying Java code**. Although stdout and stderr often appear on the same screen, they are **two separate logical channels**. Distinguishing channels properly allows the shell to capture program results, save errors to a file, and connect programs via pipes reliably.

**Simple communication rule:** primary data or results go through `System.out`; errors/warnings go through `System.err`; the program receives requests/data from `System.in`. This is a common design convention, not a mandatory constraint enforced by Java.

## 2. Actual Data Types of the Three Variables

| Variable | Java Type | Direction | Common Operations |
| --- | --- | --- | --- |
| `System.in` | `java.io.InputStream` | Input | `read()`, `read(byte[])` |
| `System.out` | `java.io.PrintStream` | Output | `print()`, `println()`, `printf()`, `write()`, `flush()` |
| `System.err` | `java.io.PrintStream` | Output | `print()`, `println()`, `printf()`, `write()`, `flush()` |

`InputStream` receives **bytes**; `PrintStream` can also write bytes, while adding convenient methods to **print formatted text**. `PrintStream` extends `OutputStream`, so `System.out.write(65)` writes a single byte with value 65, whereas `System.out.print(65)` writes the text representation of the number `65` (usually two characters). This is an important distinction when designing programs that output data.

The following two examples are **illustrative** calls, not standalone programs:

```java
System.out.write(65);    // One byte with value 65 (ASCII letter A).
System.out.print(65);    // Two digit characters: 6 and 5.
System.err.println("Không thể mở tệp.");
```

`PrintStream` has methods that write strings using a configured encoding. Therefore, you should not assume that `System.out` uses the same charset as `Charset.defaultCharset()` across every JDK, console, and configuration. If the output must be data exchanged in an exact byte format, specify the charset and data framing in the communication contract.

## 3. System.in: Reading stdin as Bytes

Because `System.in` is an `InputStream`, byte-reading rules apply:

- `int read()` returns **0 to 255** when a byte is read, or **-1** at end of stream (EOF).
- `int read(byte[] buffer)` returns the number of bytes read; it does not guarantee always filling the array. Only elements from `0` to `count - 1` are new data.
- A read call may wait when no data is available yet (blocking). The user not pressing Enter yet or the upstream side of a pipe not sending data yet are reasons a program may appear to "hang".
- EOF is not a newline character: Enter usually completes a line; EOF means the source has no more bytes.

When reading **text**, reading byte by byte and casting directly to `char` is wrong for multi-byte data such as UTF-8. Choose an explicit charset and use `InputStreamReader` to decode, optionally wrapping with `BufferedReader` to read line by line.

### When to Use BufferedReader?

`BufferedReader` is convenient when you want to read a line of text. It returns a `String` without the newline characters, and returns `null` at EOF. It accepts LF, CR, or CRLF as line terminators.

```java
// Illustrative snippet; requires importing java.io.* and StandardCharsets.
BufferedReader reader = new BufferedReader(
        new InputStreamReader(System.in, StandardCharsets.UTF_8));

String line = reader.readLine();
if (line == null) {
    System.err.println("Không có dữ liệu đầu vào (EOF).");
} else {
    System.out.println("Đã nhập: " + line);
}
```

The snippet above **does not close** `reader` because closing the wrapper also closes `System.in`, which can affect other parts of the application that continue reading stdin. For a short, standalone CLI application, closing stdin when the entire process finishes may be acceptable; however, in libraries, reusable components, or multi-step programs, **the stream owner should decide when to close it**.

### Runnable Java 17 Example: Read a Line and Respond

**File `ReadStdin.java`:**

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

public class ReadStdin {
    public static void main(String[] args) throws IOException {
        BufferedReader reader = new BufferedReader(
                new InputStreamReader(System.in, StandardCharsets.UTF_8));

        System.out.print("Name? ");
        System.out.flush(); // Ensure the prompt is requested to be flushed out.

        String name = reader.readLine();
        if (name == null) {
            System.err.println("Input is empty (EOF)");
            return;
        }

        String normalized = name.strip();
        if (normalized.isEmpty()) {
            System.err.println("Input name is blank");
            return;
        }

        System.out.println("Hello, " + normalized);
    }
}
```

Compile with JDK 17+:

```bash
javac ReadStdin.java
java ReadStdin
```

If you type `Lan` and press Enter, the terminal usually displays:

```text
Name? Lan
Hello, Lan
```

The line `Name? Lan` includes the prompt printed by the program and the characters typed by the user via **terminal echo**. Echoing depends on how the terminal is configured, not a Java `println`.

With stdin containing exactly one line `Lan`, **the stdout data produced by the program** is:

```text
Name? Hello, Lan
```

In this case, data comes from the input source rather than interactive typing; the program does not reprint the input string it read. **Stderr is empty** when valid. If stdin hits EOF immediately at the start, stdout only contains `Name? ` (with no newline), while stderr contains `Input is empty (EOF)` followed by a newline.

Command to run in a shell that supports input redirection (Bash or Command Prompt) after creating a text file `name.txt` containing `Lan`:

```bash
java ReadStdin < name.txt
```

On **Windows PowerShell 5.1**, the `<` input redirection syntax is not supported the same way as `cmd.exe`; you can use `cmd /c "java ReadStdin < name.txt"` when you need to preserve `cmd`'s byte redirection mechanism. If using a PowerShell pipeline such as `Get-Content name.txt | java ReadStdin`, passing data through the pipeline may affect encoding compared to reading directly from a file; for Unicode data, choose an appropriate approach and encoding.

### Why Flush the Prompt?

`print("Name? ")` has no newline. Some environments use buffering so the prompt might not appear before the program waits on `readLine()`. Calling `System.out.flush()` is a sensible practice at interactive boundaries. Do not rely on `println` automatically flushing in some configurations as a universal guarantee for all output wrappers.

## 4. System.out: Normal Output and Formatting

`System.out` is a `PrintStream`. Familiar methods:

| Method | Purpose |
| --- | --- |
| `print(value)` | Prints the text representation of the value, **without automatically adding a newline** |
| `println(value)` | Prints the value and then appends the **environment's line terminator** |
| `println()` | Appends only a new line |
| `printf(format, args)` | Prints using a format string |
| `printf(locale, format, args)` | Prints using an explicit locale |
| `format(...)` | Similar to `printf` |
| `append(...)` | Appends a character sequence to the `PrintStream` |
| `write(int)`/`write(byte[])` | Writes raw bytes through the output layer |
| `flush()` | Pushes buffered data to the underlying layer as supported by the stream |
| `checkError()` | Checks the write error state of the `PrintStream` |

The `println` method adds a new line, though it does not guarantee identical newline bytes across operating systems: typically LF on Unix and CRLF on Windows. To standardize a file/protocol that requires LF, write the character `"\n"` per the specification rather than depending on the system separator.

`printf` uses `java.util.Formatter` rules:

- `%s`: string or `String.valueOf(...)` representation.
- `%d`: integer.
- `%f` and `%.2f`: floating-point number, with display precision.
- `%n`: platform-specific newline, better than `"\n"` when formatting output for the host platform.
- `%%`: literal percent sign.

Pay attention to **locale**. Some locales use a comma as the decimal separator instead of a dot. For output that another machine needs to parse, pass `Locale.ROOT` or an explicit formatting locale.

### Java 17 Example: Distinguishing print, println, and printf

**File `StandardOutputFormat.java`:**

```java
import java.util.Locale;

public class StandardOutputFormat {
    public static void main(String[] args) {
        System.out.print("Items: ");
        System.out.println(3);
        System.out.printf(Locale.ROOT, "Price: %.2f%n", 12.5);
        System.out.println("Done");
    }
}
```

Run:

```bash
javac StandardOutputFormat.java
java StandardOutputFormat
```

**Stdout output** (each line ends according to the OS):

```text
Items: 3
Price: 12.50
Done
```

If you omit `Locale.ROOT`, the formatted floating-point result may vary depending on the default locale. When exporting CSV or machine-readable data, specifying only the locale is still not enough to build a safe format: you also need to define escaping/quoting, charset, and line endings.

### PrintStream and Write Errors: An Easy Detail to Miss

Unlike `OutputStream.write(...)` which can throw `IOException`, `PrintStream.print`/`println`/`write` methods are designed **not to throw checked `IOException` in normal calls**. They record I/O errors in an internal state; the application can check with `checkError()`:

```java
// Illustrative snippet:
System.out.println("result");
System.out.flush();
if (System.out.checkError()) {
    System.err.println("Could not write standard output");
}
```

`checkError()` flushes the stream automatically if it is not closed; the error state typically persists once a write error has occurred. **Do not treat a completed `println` call as confirmation that the receiver has read/consumed the data**. In programs outputting critical data or running in pipelines, consider broken pipe detection policies and appropriate exit statuses. With non-`PrintStream` APIs, such as regular `OutputStream` or `Writer`, I/O errors can be reported via `IOException`.

## 5. System.err: An Independent Warning/Error Channel

`System.err` is also a `PrintStream`, sharing the same `print`, `println`, and `printf` API. The difference lies in **purpose and process channel**: stderr is for diagnostics, while stdout holds normal results.

A command-line tool can output results on stdout so the caller can pass them into another program, while errors/warnings still need to be visible without corrupting the data. For example, if stdout is a plain list of IDs, printing `"Warning: ..."` to stdout could cause the receiving program to mistake it for an ID. Sending warnings to stderr keeps stdout data easy to parse.

```java
System.out.println("ID-001"); // Result intended for the pipeline.
System.err.println("Warning: using cached data"); // Diagnostics.
```

In a terminal, both lines may appear together, making it hard for users to notice the separate channels. When redirecting stdout and stderr to **two different files**, the difference becomes clear.

### Runnable Java 17 Example: Two Output Channels

**File `OutputChannels.java`:**

```java
public class OutputChannels {
    public static void main(String[] args) {
        System.out.println("record-1");
        System.err.println("warning: fallback");
        System.out.println("record-2");
    }
}
```

Compile:

```bash
javac OutputChannels.java
```

Example run in a shell supporting redirection:

```bash
java OutputChannels > result.txt 2> diagnostics.txt
```

**Contents of `result.txt`:**

```text
record-1
record-2
```

**Contents of `diagnostics.txt`:**

```text
warning: fallback
```

This is an easy example to verify that stdout and stderr are two distinct channels. If you just run `java OutputChannels` and watch a single shared terminal, **do not rely on the interleaving order** between the two channels to deduce event order, because buffering, scheduling, and display mechanisms may cause lines to appear in a different order than the calls.

## 6. Redirection, Pipes, and the Meaning of 0, 1, 2

The symbols stdin, stdout, and stderr correspond by Unix/POSIX OS convention to file descriptors **0, 1, 2**. Different shells have similar redirection syntax, though not completely identical. For Bash and Command Prompt, common examples:

| Syntax | Meaning |
| --- | --- |
| `java App < input.txt` | Reads stdin from `input.txt` |
| `java App > output.txt` | Writes stdout to a file, usually **overwriting** |
| `java App >> output.txt` | Appends stdout to a file |
| `java App 2> error.txt` | Writes stderr to a separate file |
| `java App > output.txt 2> error.txt` | Separates the two outputs |
| `java App 2>&1` | Directs stderr to wherever stdout currently points |
| `java Producer \| java Consumer` | Connects Producer's stdout to Consumer's stdin |

When using a pipe `Producer | Consumer`, Producer's stderr **usually does not automatically enter Consumer's stdin**; stderr still follows its own route unless redirected otherwise. This is why you should keep stdout clean, containing only the data the consumer expects.

**Redirection order can matter.** For instance, in Bash, `java App > output.txt 2>&1` sends both channels to the destination where stdout was directed. In contrast, `java App 2>&1 > output.txt` has a different meaning because stderr was attached to stdout's original destination beforehand. When merging both to one destination, the order of bytes/chunks from the two streams must not be treated as a reliable total order solely because of redirection syntax.

**PowerShell has its own stream and redirection model**, especially when calling native executables through a pipeline, and encoding handling also differs between Windows PowerShell 5.1 and newer PowerShell versions. Test commands in the exact shell you use; do not assume all pipe/redirection syntaxes are completely equivalent in bytes, encoding, and exit status.

## 7. How Do Stdin and Stdout Relate to Bytes and Charsets?

`System.in` reads bytes, while `BufferedReader(InputStreamReader(...))` reads text after decoding. Choose the charset at the data boundary:

```java
// Illustrative code; each library may choose a charset per its own contract.
BufferedReader reader = new BufferedReader(
        new InputStreamReader(System.in, StandardCharsets.UTF_8));
String text = reader.readLine();
```

The example assumes data fed into stdin is **UTF-8**. When data actually comes from a terminal with a different encoding, explicit UTF-8 may be incompatible. You need to identify whether the source is a file, pipe, terminal, or another system, then select the appropriate charset. Seeing Vietnamese text correctly on screen does not prove the exchanged bytes are UTF-8.

### Console Encoding and Default Charset Are Two Different Concepts

`Charset.defaultCharset()` is the default charset for many Java APIs; JDK 17 prior to JEP 400 may depend on the platform, while JDK 18+ typically defaults to UTF-8 (with exceptions/compatibility modes). However, the charset of **console/standard streams** may follow its own JVM and environment mechanism. You should not simply infer that `System.out` is always UTF-8 just because the JVM has a UTF-8 default charset.

If a tool must output **exact UTF-8 bytes** for consumption from a pipe or file, you can construct a `Writer` on the output stream with an explicit charset, though you must manage flushing and not arbitrarily close the standard stream:

```java
// Illustrative snippet, not a standalone program.
Writer utf8 = new OutputStreamWriter(System.out, StandardCharsets.UTF_8);
utf8.write("Xin chào");
utf8.flush();
```

You need to import `java.io.Writer`, `java.io.OutputStreamWriter`, `java.nio.charset.StandardCharsets`, and handle `IOException`. Do not call `utf8.close()` midway through the application's lifecycle if the program still uses stdout, because closing the wrapper closes the underlying stream. Avoid mixing direct `System.out.print` calls with writes through a buffered wrapper to the same output stream without explicitly managing flush order.

If the data must be **binary**, use a byte-oriented API on the output channel or `System.out.write(byte[])`, and separate logging completely to `System.err` so as not to corrupt the payload.

## 8. System.console() and Differences from System.in

`System.console()` returns a `java.io.Console` when the JVM has an interactive console attached to the running process; it can return **`null`**, which commonly happens when running in an IDE, via certain launchers, or when input/output is redirected.

Key differences:

- `System.in` is always the process's stdin channel per the JVM API, capable of reading bytes from a pipe/file.
- `Console` provides line reading, prompt printing, and `readPassword()` better suited for certain terminal interfaces.
- When `System.console() == null`, you must not call `console.readLine()` directly; you need a fallback using stdin or a change in how the program is run.
- `Console.readPassword()` reads a password without echoing as supported by the console; the result is a `char[]`, which can be cleared after processing. It is **not** a suitable way to read a password when the program receives automated input from a pipe.

### Java 17 Example: Input via Console or Stdin

**File `ConsoleFallback.java`:**

```java
import java.io.BufferedReader;
import java.io.Console;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

public class ConsoleFallback {
    public static void main(String[] args) throws IOException {
        Console console = System.console();
        String name;

        if (console != null) {
            name = console.readLine("Name? ");
        } else {
            BufferedReader reader = new BufferedReader(
                    new InputStreamReader(System.in, StandardCharsets.UTF_8));
            System.out.print("Name? ");
            System.out.flush();
            name = reader.readLine();
        }

        if (name == null) {
            System.err.println("No name (EOF)");
            return;
        }

        System.out.println("Hello, " + name);
    }
}
```

Compile:

```bash
javac ConsoleFallback.java
java ConsoleFallback
```

With input `Minh`, the program prints the greeting `Hello, Minh` after receiving a line of input; how the prompt is displayed/echoed depends on the console branch and environment. If stdin is at EOF, stderr prints `No name (EOF)`. This example uses UTF-8 in the **fallback branch**; for environments with a different stdin charset, adjust the encoding to match the actual data.

Do not use `System.console() != null` as a security verification that the user entering input is a real human, as the program remains subject to terminal configuration and external processes.

## 9. Scanner for Structured Input

`java.util.Scanner` is a higher-level utility for parsing tokens, numbers, and text data types. It can be attached to stdin:

```java
// Illustrative snippet:
Scanner scanner = new Scanner(System.in, StandardCharsets.UTF_8);
String word = scanner.next();
```

You need to import `java.util.Scanner` and `java.nio.charset.StandardCharsets`. When using `nextInt()` followed by `nextLine()`, remember that `nextInt()` only reads the numeric token; the line terminator may still remain in the input, causing `nextLine()` to return an empty string. For line-based protocols, it is often easier to control by using `BufferedReader.readLine()` and then `Integer.parseInt(line.strip())` with error handling.

`Scanner` also has a `Locale` mechanism: parsing commas/dots in numbers can differ between locales. When input structure has a fixed format, choose `scanner.useLocale(Locale.ROOT)` or the locale matching the specification.

**Closing `Scanner` also closes the underlying `System.in`**, so do not automatically wrap a scanner in `try-with-resources` around stdin if the stream is shared across multiple parts of the program. If the scanner is created on a file stream that your code owns, `try-with-resources` remains the right choice.

## 10. Lifecycle Management and Avoiding Accidental Closure of the Three Standard Streams

`System.in`, `System.out`, and `System.err` are usually initialized by the JVM/launcher, with a lifecycle tied to the entire process. Closing them directly can prevent other parts from reading input or writing output.

Example requiring caution:

```java
// Inappropriate if the program still uses stdout after this block.
try (PrintWriter writer = new PrintWriter(System.out)) {
    writer.println("First phase");
}
// PrintWriter.close() closes the underlying System.out stream.
```

When creating a wrapper only for use inside a method, you can let the standard streams be managed at the application level and call `flush()` when needed instead of closing the wrapper mid-program. For standalone files that you open yourself, still prefer `try-with-resources`. Distinguishing between a **wrapper** and **resource ownership** is essential.

`System.out.close()` can cause subsequent `println` calls not to output as expected; `PrintStream` usually records the error rather than throwing a checked `IOException`, so the program may "silently" fail without an exception appearing.

### When to Flush?

- **Input prompts:** flush before waiting on stdin if the prompt is printed without a newline.
- **Streaming data that the receiver must process immediately:** flush at necessary application boundaries, balancing performance.
- **When finishing writing:** flushing is generally sensible; for an output stream that is properly closed, closing handles the buffer depending on the implementation.

`flush()` does not guarantee the receiving side has read the data, nor does it prove it has been durably written to disk.

## 11. Changing System Streams with setIn, setOut, setErr

Java provides:

```java
System.setIn(InputStream newInput);
System.setOut(PrintStream newOutput);
System.setErr(PrintStream newError);
```

These are **illustrative** calls with stream variables already created. They **change the JVM's global reference** to the standard streams, commonly used in tests, frameworks, or special bootstraps. When replacing `System.out` with a `PrintStream` writing to memory, subsequent code calling `System.out.println` is routed to the new destination; this does not necessarily change the file descriptors of all native libraries or child processes.

Because the change has JVM-wide scope, you must **restore the old stream** in `finally`. If tests run in parallel, one test replacing `System.out` may accidentally capture another test's output. It is better to design critical logic to accept a `PrintStream`/`Writer` via a parameter when possible.

### Runnable Java 17 Example: Temporarily Capturing Stdout

**File `CaptureStdout.java`:**

```java
import java.io.ByteArrayOutputStream;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;

public class CaptureStdout {
    public static void main(String[] args) {
        PrintStream original = System.out;
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();

        try (PrintStream capture =
                     new PrintStream(bytes, true, StandardCharsets.UTF_8)) {
            System.setOut(capture);
            System.out.print("captured");
        } finally {
            System.setOut(original);
        }

        System.out.println("Captured: "
                + bytes.toString(StandardCharsets.UTF_8));
    }
}
```

Run:

```bash
javac CaptureStdout.java
java CaptureStdout
```

**Exact stdout:**

```text
Captured: captured
```

Because `System.out` was temporarily swapped, the `print("captured")` call did not go directly to the terminal. After the `finally` block, the original stdout is restored to print the result. `capture.close()` closes only the temporary stream, not the original stdout. In multithreaded applications, this pattern needs to run in a controlled test context; mutating global streams is not a safe default technique for capturing per-request logs.

## 12. stdout/stderr and Exit Codes: Two Separate Mechanisms

Printing errors to `System.err` **does not automatically make a program fail**. Conversely, a program can exit with an error code without printing anything. Shells and automation tools typically inspect the **exit code**, alongside stdout and stderr.

Example:

```java
// Illustrative snippet, call only when you want to terminate the JVM.
System.err.println("Invalid command-line arguments");
System.exit(2);
```

`System.exit(2)` requests terminating the JVM with status 2 per application convention; shells typically treat non-zero statuses as failures. Avoid using `System.exit` in libraries or unit tests because it terminates the entire running process. In a dedicated `main` method, another option is throwing an uncaught exception or explicitly managing control flow; the exact exit status depends on how the launcher handles it.

A good CLI usually defines three conventions together: **what stdout contains**, **what stderr contains**, and **what exit codes mean**. For tools that only produce data output, success or progress messages should not be mixed into stdout if the caller needs to parse clean data.

## 13. Buffering, Mixing Two Streams, and Concurrency

Even if code sequentially calls:

```java
System.out.println("A");
System.err.println("B");
System.out.println("C");
```

that does not guarantee the terminal, IDE, or target file displays `A`, `B`, `C` in order if the two streams pass through **two different buffering or consumption mechanisms**. Flushing can make output appear more promptly, but does not turn the two streams into a single totally ordered protocol.

In multithreaded programs, multiple threads printing concurrently to streams can produce interleaved content; even if individual calls are synchronized to some degree by the implementation, **do not rely on atomicity for an entire application message** if constructed from multiple calls. A better approach is formatting the complete message before writing, or delegating ordered logging to a dedicated logging component.

Even if both stdout and stderr are redirected to the same file, this still does not establish a reliable clock or event ordering. For multithreaded diagnostics, you should usually include timestamps, thread identifiers, and a proper logging mechanism instead of scattering `System.out.println` calls.

## 14. Practical Example: A CLI with Clean Stdout and Clear Stderr

The `NormalizeLines` program reads **UTF-8 lines** from stdin, strips leading/trailing whitespace, and outputs non-empty lines to stdout. A count of omitted lines is sent to stderr so stdout can be piped into another program without mixing diagnostic messages.

**File `NormalizeLines.java`:**

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.io.Writer;
import java.nio.charset.StandardCharsets;

public class NormalizeLines {
    public static void main(String[] args) throws IOException {
        BufferedReader reader = new BufferedReader(
                new InputStreamReader(System.in, StandardCharsets.UTF_8));
        Writer writer = new OutputStreamWriter(
                System.out, StandardCharsets.UTF_8);

        int omitted = 0;
        String line;

        while ((line = reader.readLine()) != null) {
            String value = line.strip();
            if (value.isEmpty()) {
                omitted++;
                continue;
            }

            writer.write(value);
            writer.write('\n'); // Output format specifies LF.
        }

        writer.flush(); // Do not close System.out as the application still owns it.
        System.err.println("Omitted blank lines: " + omitted);
    }
}
```

Compile:

```bash
javac NormalizeLines.java
```

Suppose `lines.txt` is a **UTF-8** file with the following contents (with a whitespace-only line in the middle):

```text
  Lan

 Minh
```

Run in Bash/cmd:

```bash
java NormalizeLines < lines.txt > clean.txt 2> stats.txt
```

**Contents of `clean.txt` per program logic:**

```text
Lan
Minh
```

**Contents of `stats.txt`:**

```text
Omitted blank lines: 1
```

`String.strip()` removes whitespace according to Java's definition of Unicode whitespace, differing in some cases from `trim()`. The program does not preserve original newlines: it outputs fixed LF, which is **intentional for the output format**. Blank lines may be truly empty lines or contain only whitespace. Malformed charset input must be handled explicitly if invalid UTF-8 must be rejected; default decoder configurations may replace malformed bytes depending on the API.

This is the right way to wire the three channels: stdin is the data source, stdout outputs only processed records, and stderr carries statistics/diagnostics. If more complex logging/tracing is desired, diagnostics can be moved to a logging framework with an appropriate appender configured.

## 15. Common Misconceptions

| Misconception | Why It Is Dangerous | How to Understand/Fix |
| --- | --- | --- |
| `System.in` is always the keyboard | Stdin can be a file, pipe, or other source | Design to read both interactive and redirected input |
| `read()` returns a text character | It returns a **byte**, which may be part of a UTF-8 sequence | Use `InputStreamReader` and the right charset for text |
| `-1` is the byte `0xFF` | `read()` returns `int` to distinguish EOF from 255 | Check `int value == -1` |
| `System.out` and `System.err` are always equivalent | Shells can redirect them separately | Send results to stdout; warnings/errors to stderr |
| `print(65)` is equivalent to `write(65)` | One writes text digits, the other writes a byte | Use the right text or byte API |
| `println` always produces a single `'\n'` character | Separator is platform-dependent | Choose `%n` for system lines, `"\n"` for fixed LF |
| No exception means `PrintStream` wrote successfully | `PrintStream` tracks an internal error flag | Check `checkError()` when needed |
| Closing `Scanner(System.in)` only frees Scanner | It closes the underlying stdin too | Only close when owning/deciding to end stdin |
| `System.console()` is always non-`null` | IDEs, pipelines, launchers may not provide a Console | Check `null`, provide a fallback branch |
| Every terminal uses UTF-8 | Encoding may depend on configuration | Agree on the actual charset on both sides |
| stderr is automatically piped along with stdout | Pipes usually connect only stdout | Redirect stderr deliberately when needed |
| Mixing stdout and stderr preserves statement order | Both streams have separate buffering/consumers | Do not rely on display order |
| `System.setOut` affects only one method | The reference changes JVM-wide | Restore in `finally`, avoid parallel tests |
| Printing to stderr automatically returns an error exit code | Output channels and exit status are independent | Set exit status according to the CLI contract |

## 16. Which Tool to Choose for Each Need?

- **Reading a line of text:** `BufferedReader(new InputStreamReader(System.in, charset))`.
- **Reading tokenized/numeric data:** `Scanner` if suitable, watching out for locale, leftover tokens, and stdin ownership.
- **Interactive input with prompts/passwords:** consider `System.console()` and always handle `null`.
- **Printing user-friendly output:** `System.out.println` or `printf` with an explicit locale if needed.
- **Printing errors/warnings:** `System.err`, keeping stdout output data clean.
- **Outputting a byte stream or text in a contracted encoding:** use byte output or a `Writer` with an explicit charset and format.
- **Testing output:** prefer passing `PrintStream`/an interface via dependency injection; use `System.setOut` only in isolated tests and always restore the original stream.
- **Applications with complex logging and diagnostics:** use a logging framework instead of ad-hoc printing from multiple classes.

## 17. Self-Check Exercises

1. Run `OutputChannels` three times: normally, with `> result.txt`, and with `> result.txt 2> diagnostics.txt`. Explain which messages belong to stdout/stderr.
2. Run `ReadStdin` with the keyboard and with an input file. Observe the difference between **terminal echo** and the bytes Java actually prints.
3. Replace `System.out.print("Name? ")` with `println`, explain the change in how the prompt appears, and why `flush` still matters on some buffered channels.
4. Create a UTF-8 file containing Vietnamese text, read it via `InputStreamReader(System.in, UTF_8)`, and compare it against running in a terminal with a different encoding. Record the charset on each end.
5. Use `System.err.println` to report an error when there is no input, then run the program with stdin at EOF. Inspect stdout and stderr independently.
6. Extend `NormalizeLines` so that if the entire input is empty, it returns exit status 2. Keep the error on stderr and explain why a message on stderr alone is not enough to signal failure to a script.
7. Write a test for a method accepting `PrintStream output` and calling `output.println("ok")`. Use `ByteArrayOutputStream` to compare the result without modifying JVM-wide `System.out`.
8. Find and fix the bug with `Scanner.nextInt()` right before `nextLine()`; compare with reading a whole line and parsing explicitly.
9. Explain why stdout is the data channel, stderr is the diagnostic channel, and **exit status** is the process's result signal; these three are related but do not replace one another.

## 18. Takeaways

`System.in` is an **`InputStream` input**, while `System.out` and `System.err` are **two `PrintStream` outputs**. They are the standard channels of a Java process and can be redirected via files or pipes. To write clear command-line tools, read stdin using the right data type and charset, output primary results to stdout, send errors/warnings through stderr, control flushing/closing based on ownership, and use exit codes to signal success/failure to callers.

### References

- Java SE 17 API: [`System`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html), [`InputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html), [`PrintStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/PrintStream.html).
- Java SE 17 API: [`Console`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Console.html), [`InputStreamReader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStreamReader.html), [`Scanner`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Scanner.html).
- [JEP 400: UTF-8 by Default](https://openjdk.org/jeps/400) to distinguish the JVM default charset from specific charset requirements on console/standard streams.
