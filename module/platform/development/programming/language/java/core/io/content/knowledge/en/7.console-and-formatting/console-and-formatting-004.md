# Console.reader, writer, readLine, and readPassword in Java

> **Topic:** Java Core I/O → **Console and Formatting**. This lesson explains how to obtain the interactive console device, read/write characters with `reader()` and `writer()`, read lines with `readLine()`, read secret input with `readPassword()`, and distinguish between a real console and standard streams when running in an IDE, CI, or through a pipe. Examples use Java 17+ APIs; `java.io.Console` has been available since Java 6.

## 1. What Is Console, and Is It the Same as System.in and System.out?

`java.io.Console` is the Java SE API for the **character-based console** device attached to the JVM, if one exists. It is suited for applications run interactively from a terminal: showing prompts, reading usernames, selecting actions, and entering passwords without the terminal echoing the typed content.

Obtain a Console with:

~~~java
import java.io.Console;

Console console = System.console();
if (console == null) {
    System.err.println("Không có console tương tác cho tiến trình này.");
    // Choose an alternative workflow or stop the interactive task.
}
~~~

This is a **fragment**, placed inside a method. You cannot instantiate a Console yourself with `new Console()`: the standard way is `System.console()`. The JVM has a Console object attached to the process's console if provided by the environment.

**Important distinctions:**

| Object/API | Purpose | When Running from IDE/CI or Redirected |
| --- | --- | --- |
| `System.in` | Standard input as an `InputStream` (bytes) | Can read from a pipe/file or environment-configured source, even without a console. |
| `System.out` | Standard output as a `PrintStream` | Can write to a terminal, file, or pipe; does not imply a Console always exists. |
| `System.err` | Standard error, typically used for error messages | Can be redirected independently; does not guarantee Console exists. |
| `System.console()` | Returns `Console` if the JVM has a suitable console device, otherwise `null` | Often `null` in many IDEs, background runners, CI environments, or when streams are redirected; must check at runtime. |
| `Console.reader()` / `Console.writer()` | Character-oriented Reader/PrintWriter bound to the console | Call only after confirming `console != null`. |
| `Console.readLine()` / `readPassword()` | Interactive line-level reading, or line-level reading with echo disabled | Does not replace batch reading APIs from files/pipes when there is no console. |

**Do not infer:** claiming "if the program has `System.in`, it must have a Console" is false. Console availability depends on the platform and how the JVM was launched. In a regular terminal, `System.console()` usually returns an object; in test runners, IDE-launched programs, or redirected commands, it is often `null`. Actual behavior can vary by JDK/launcher/terminal, so code must handle the `null` branch.

## 2. Overview of the Four Covered APIs

| API | Return Value | Unit of Operation | Characteristics |
| --- | --- | --- | --- |
| `console.reader()` | Unique `Reader` attached to the console | `char`/UTF-16 code unit | Reads characters directly, suited for custom parsers/scanners. Does not hide typed input. |
| `console.writer()` | Unique `PrintWriter` attached to the console | Encoded text for console output | `print`, `println`, `printf`; flush when prompts must appear immediately. |
| `console.readLine()` or `readLine(fmt,args...)` | `String`, or `null` on EOF | One line of characters | Can display a prompt, reads until line terminator, strips line terminator characters. Input is normally echoed. |
| `console.readPassword()` or `readPassword(fmt,args...)` | `char[]`, or `null` on EOF | One line of sensitive characters | Disables echo during password entry; returns a char array that can be cleared after use. |

The zero-argument variants read a line/secret without displaying a prompt. Variants accepting `String fmt, Object... args` build a prompt using `Formatter` syntax, e.g., `console.readLine("Chào %s, tên bạn? ", role)`. If the prompt contains a literal `%` character inside a **format string**, write `%%` to avoid formatting errors.

**A single Console does not have four independent I/O sources.** `reader()`, `writer()`, and the higher-level read/write methods share the same underlying console device. Interleaving reads from `reader()`, `System.in`, or multiple buffered wrappers on the same source can desynchronize reading logic.

## 3. `Console.reader()` — Reading the Console as a Reader

`reader()` returns the unique `java.io.Reader` object associated with the Console. It is intended for programs needing custom character-parsing logic, such as a parser or `Scanner` processing tokens. `Reader` methods accept/return data in **UTF-16 code units**, not raw bytes.

~~~java
// Fragment: must obtain a valid console before using.
Console console = System.console();
if (console != null) {
    Reader reader = console.reader();
    int codeUnit = reader.read();
    if (codeUnit == -1) {
        console.writer().println("Không còn dữ liệu đầu vào.");
    } else {
        console.writer().printf("Mã char đầu tiên: U+%04X%n", codeUnit);
    }
}
~~~

Because this is a **fragment**, you must import `java.io.Console`, `java.io.Reader`, and declare or catch `IOException` from `Reader.read()`. If the user types an emoji outside the BMP, one `read()` call returns **one code unit**, without guaranteeing the full code point. `reader()` is for reading normal input and provides no guarantee of disabling echo.

### 3.1. Does Line Reading on Reader Differ from readLine?

Yes. `Console.readLine(...)` is for the prompt + single normal line case and returns a `String`. `reader().read(...)` may block waiting for the user to finish a line; the `Console.reader` documentation notes that bulk-read methods will not read past a line boundary in a single invocation even if the buffer still has space. `Reader.read()` returns an `int` with `-1` at EOF, and can read one code unit at a time.

Example wrapping Reader with a parser:

~~~java
// Fragment: use only when console != null.
java.util.Scanner scanner =
        new java.util.Scanner(console.reader());

String command = scanner.nextLine(); // may throw when no line remains.
~~~

`Scanner` also has its own delimiter, locale, and exception rules. Do **not** mix `scanner.nextLine()` and `console.readLine()` simultaneously on the same console assuming buffers will coordinate cleanly. Pick one reading approach suited to the interactive lifecycle. Avoid accidentally closing the scanner mid-way if later code still needs to share the console.

### 3.2. Closing the Reader Returned by Console?

Per the Java 21 API, calling `close()` on the object returned by `console.reader()` or `console.writer()` **does not close the underlying console stream**. Nevertheless, they are shared objects bound to the Console, so avoid creating multiple wrappers and interleaving closes/reads. Resource ownership and wrapper behavior (e.g., `Scanner`, `BufferedReader`) still need separate consideration. For simple CLIs, `readLine()` is usually used directly to avoid manually managing a reading stream.

## 4. `Console.writer()` — Writing with PrintWriter

`writer()` returns the `PrintWriter` object bound to the console. You can:

- `writer().print(value)` to write without a newline.
- `writer().println(value)` to write and append a newline.
- `writer().printf("Đã nhận %d mục%n", count)` to format strings.
- `writer().flush()` or `console.flush()` to push buffered content to the device, useful before waiting for input.

~~~java
// Fragment: console is non-null.
java.io.PrintWriter out = console.writer();
out.println("Công cụ nhập dữ liệu");
out.printf("Phiên làm việc: %s%n", "demo");
out.print("Gõ lệnh: ");
out.flush(); // Display the prompt before waiting.
String command = console.readLine();
~~~

The `Console` API also includes `console.printf(...)` and `console.format(...)` to print directly to the console, along with `console.flush()`. If you want a single-line prompt without a newline, `console.readLine("Tên: ")` is usually clearer than calling `print` followed by `readLine()`.

**PrintWriter behavior:** many `PrintWriter` write methods do not throw checked `IOException` directly; they record errors to be inspected with `checkError()`. If an application requires strict write error checking, check the error state instead of assuming `println()` always succeeds. Meanwhile, `Console.readLine/readPassword` can throw `java.io.IOError` on I/O failures.

### 4.1. Console Charset

Console works with characters and needs a charset matching the console environment. Starting in **Java 17**, `console.charset()` returns the `Charset` used by the Console. This charset can **differ** from `Charset.defaultCharset()`. Therefore, you should not claim every Console uses UTF-8 or that the program's default determines how the terminal renders all characters.

~~~java
// Java 17+ fragment: console != null.
console.writer().printf("Console charset: %s%n", console.charset());
console.flush();
~~~

When Vietnamese output renders incorrectly, examine the terminal/font/locale/charset and stream configuration. Do not try to fix it by blindly casting bytes to `char`; `Console.writer()` already operates at the character layer, while the terminal is responsible for rendering.

## 5. `Console.readLine()` — Reading a Normal Line of Input

Two basic forms:

~~~java
String line = console.readLine();                  // Without printing a prompt.
String name = console.readLine("Tên của bạn: ");  // With a prompt.
~~~

**Important contract:**

1. The method waits for the user to enter a line; normal input is **echoed** by the console as typed.
2. Returns a `String` excluding line terminator characters `\n`, `\r`, or the pair `\r\n`. It does not automatically `trim()` leading/trailing whitespace.
3. At end of input, returns `null`. An empty line where the user presses Enter is **`""`**, completely different from `null`.
4. On I/O error, the method may throw `IOError`; an invalid prompt format may throw `IllegalFormatException`.
5. The prompt `String fmt` uses formatting rules, not SQL or command syntax. Never pass untrusted input as a **format string** when the intent is simply literal display.

Example reading a name and checking EOF:

~~~java
// Fragment: console has already been verified non-null.
String name = console.readLine("Tên hiển thị: ");
if (name == null) {
    console.writer().println("Đã kết thúc đầu vào.");
} else if (name.isEmpty()) {
    console.writer().println("Bạn chưa nhập tên.");
} else {
    console.writer().printf("Xin chào, %s!%n", name);
}
console.flush();
~~~

**An empty line is not EOF.** Distinguish them when building CLI menus. When reading numbers, `readLine()` returns a **String**, not a parsed number; use `Integer.parseInt` with `NumberFormatException` handling and define how whitespace is handled.

### 5.1. Parameterized Prompts and the % Character

~~~java
// Fragment: formatting prompts per java.util.Formatter.
String project = "Java";
String answer = console.readLine("Bạn muốn học %s? [y/n] ", project);

// A literal % in a format string must be written as %%.
String ratio = console.readLine("Nhập mức hoàn thành (0..100%%): ");
~~~

If the `project` variable comes from another source, passing it as a `%s` **argument** is clearer and safer than putting the whole variable in the format string. Do not confuse `String.format`/`printf` with plain string concatenation: `%` has syntactic meaning.

## 6. `Console.readPassword()` — Reading Secret Strings Without Echo

`readPassword()` reads a line in **echo-disabled** mode, meaning characters typed by the user are not printed back to the console as during normal entry. It returns `char[]` instead of `String`.

~~~java
// Fragment: console is available and code is inside a method.
char[] password = console.readPassword("Mật khẩu: ");
if (password == null) {
    console.writer().println("Đã kết thúc đầu vào.");
} else {
    try {
        // Pass char[] to a secret-checking API that supports char[],
        // or process temporarily as required by the application.
        // Do not print the password, do not log the password.
    } finally {
        java.util.Arrays.fill(password, '\0');
    }
}
~~~

Why `char[]`: array elements can be overwritten immediately after use. `String` is immutable, with no reliable API to actively erase its contents in memory. **Clearing the array is not an absolute guarantee that every copy of the secret is erased** from the JVM, libraries, OS, or swap, though it shrinks the lifetime of the copy you control.

**What not to do:**

~~~java
// WRONG example of handling secret data:
String leaked = new String(password);
System.out.println("password=" + leaked);
~~~

Converting the array to `String` and writing it to stdout/logs can create long-lived copies and expose secrets. It is better to use authentication APIs that accept short-lived data (`char[]`/`byte[]` or dedicated credential mechanisms) and clear intermediate buffers whenever possible.

**Disabled echo does not mean the password is completely secure.** It only hides input from the terminal screen; it does not replace secure transport, proper authentication, authorization, secret management, or defense against external input-capturing components. When no terminal is available, do not silently fall back to `Scanner(System.in)` to read passwords in normal echoed mode without warning or proper security design.

### 6.1. Empty Passwords and End of Input

- When the user simply presses Enter, input may be `new char[0]`, i.e., an **empty array** (you must decide whether to allow it).
- At EOF, `readPassword()` returns `null`; do not call `Arrays.fill(null,...)` or `password.length` before checking.
- `readPassword()` may throw `IOError` when the console operation fails, or `IllegalFormatException` if the prompt format is invalid.
- A user canceling the application via an OS signal does not necessarily result in receiving `null`; the environment/terminal may terminate the process before Java handles it.

## 7. Complete Interactive Sample Program: Reading Name and Password

Create file **`ConsoleInputDemo.java`**:

~~~java
import java.io.Console;
import java.io.PrintWriter;
import java.util.Arrays;

public class ConsoleInputDemo {
    public static void main(String[] args) {
        Console console = System.console();
        if (console == null) {
            System.err.println("Không có console tương tác; hãy chạy từ terminal.");
            return;
        }

        PrintWriter out = console.writer();
        out.println("=== Java Console Demo ===");
        out.flush();

        String name = console.readLine("Tên hiển thị: ");
        if (name == null) {
            out.println("Đầu vào đã kết thúc.");
            out.flush();
            return;
        }

        char[] password = console.readPassword("Mật khẩu (không echo): ");
        if (password == null) {
            out.println("Đầu vào đã kết thúc.");
            out.flush();
            return;
        }

        try {
            // Only simulates receiving input; does not authenticate the password yet.
            out.printf("Xin chào, %s. Đã nhận thông tin nhập.%n", name);
            out.flush();
        } finally {
            Arrays.fill(password, '\0');
        }
    }
}
~~~

Compile/run commands in an interactive terminal in the directory containing the file:

~~~bash
javac --release 17 ConsoleInputDemo.java
java ConsoleInputDemo
~~~

**Illustrative input session** (name input typed by the user; characters typed at the password prompt do not appear in the terminal):

~~~text
=== Java Console Demo ===
Tên hiển thị: Mai
Mật khẩu (không echo):
Xin chào, Mai. Đã nhận thông tin nhập.
~~~

This is an **input-dependent transcript**, not a fixed stdout across every environment. If the JVM has no console, the program writes only to stderr:

~~~text
Không có console tương tác; hãy chạy từ terminal.
~~~

The example intentionally does **not** verify the password against a hard-coded value: the goal is how to receive and clear a sensitive array in a CLI. When launching the program from many IDEs or redirected commands, `System.console()` can be `null` and the error branch is the expected proper behavior. Do not "fix" this branch by logging the secret or creating a `String`.

### 7.1. Why Not Use try-with-resources for Console?

`Console` does not implement `AutoCloseable`; do not write `try (Console c = System.console())`. The `Reader` and `PrintWriter` objects returned by the console share the device lifecycle; for simple CLIs, you do not need to close them after every prompt. `Console.flush()` exists to push output as needed. `Arrays.fill(password, '\0')` in `finally` is **sensitive-content cleanup**, different from `close()` on an I/O resource.

## 8. When `reader()` and `writer()` Are Needed Directly

Choose them when you want a custom parser controlling each character/group of characters or have an API accepting a `Reader`/`Writer`. The **standalone** example below demonstrates only reading a single UTF-16 code unit, without handling passwords or combining other input mechanisms.

Create **`ConsoleReaderWriterDemo.java`**:

~~~java
import java.io.Console;
import java.io.IOException;
import java.io.Reader;
import java.io.PrintWriter;

public class ConsoleReaderWriterDemo {
    public static void main(String[] args) throws IOException {
        Console console = System.console();
        if (console == null) {
            System.err.println("Không có console tương tác.");
            return;
        }

        Reader in = console.reader();
        PrintWriter out = console.writer();

        out.print("Nhập một ký tự ASCII rồi Enter: ");
        out.flush();

        int first = in.read();
        if (first == -1) {
            out.println("EOF");
        } else {
            out.printf("Mã UTF-16 đầu tiên: U+%04X%n", first);
        }
        out.flush();
    }
}
~~~

~~~bash
javac --release 17 ConsoleReaderWriterDemo.java
java ConsoleReaderWriterDemo
~~~

If the user enters the letter `A` and presses Enter, the output printed by the program itself after reading will be:

~~~text
Mã UTF-16 đầu tiên: U+0041
~~~

In addition to this output, the terminal may echo the input and prompt, so the complete transcript also depends on the environment. The example reads only **one** `char`, so the Enter character remains in the buffer/input source; do not turn this snippet into a multi-question CLI loop without consuming the rest of the line. For non-BMP characters like emojis, you must read surrogate pairs or use a line-reading approach instead of assuming a single `Reader.read()` call equals one "visible character".

## 9. Interaction Between Reader, Scanner, readLine, and readPassword

**Each reading layer may hold data in its own buffer**. Suppose you create `Scanner(console.reader())`, call `scanner.next()`, and then call `console.readLine()`; the scanner may already have consumed extra characters/newlines that the subsequent `readLine` expected to read. Likewise, wrapping multiple `BufferedReader` instances around the same source can cause unpredictable behavior.

**Design principle:** within an interactive flow, choose **one owner for the reading mechanism**. If you only need prompts/lines/secrets, prefer `Console.readLine` and `Console.readPassword`; if you need complex tokens/grammars, build a parser from one `Reader` and avoid arbitrarily mixing other read calls. In particular, never read partial UTF-8 bytes from `System.in` and expect `Console.reader()` to continue cleanly with the decoder state.

Note that `Console` synchronizes certain operations to ensure atomicity of key console operations, though other threads may **block** while one thread is performing I/O. That does not turn two separate calls—`writer.print` followed by `reader.read`—into an uninterruptible transaction; do not let multiple threads display prompts concurrently without a coordinator.

## 10. Comparison with `Scanner(System.in)`, `BufferedReader`, and Command-Line Arguments

| Input Method | Best Suited For | Limitations Related to This Lesson |
| --- | --- | --- |
| `console.readLine("Tên: ")` | Prompting + reading one line entered by a user in a terminal with a console | Requires `System.console() != null`; returns `null` on EOF. |
| `console.readPassword("Mật khẩu: ")` | Entering secrets with **echo disabled** | Returns `char[]`, requires clearing the array and secret management; unavailable without a console. |
| `console.reader()` + parser/Scanner | Parsing complex character input from the console | Must manage buffers, EOF, exceptions, and avoid mixing read mechanisms. |
| `console.writer()` | Outputting characters/formatted text to the console | May need flushing; `PrintWriter` has its own error-checking mechanism. |
| `new Scanner(System.in)` | Reading stdin as tokens/lines, including pipes/files | Does not disable echo automatically. Does not replace `readPassword()` for secrets. |
| `BufferedReader(new InputStreamReader(System.in, charset))` | Reading regular stdin lines from automation/files | Choose charset per contract, handle exceptions yourself, does not depend on an interactive console. |
| `args[]` / env vars / secret provider | Non-interactive configuration | Do not pass passwords via command-line args due to exposure in process lists/logs; pick an environment-appropriate secret manager. |

### 10.1. Want to Run Batch Mode Without a Console?

For **ordinary (non-sensitive) data**, you can design support for stdin pipes/files as well. Example:

~~~java
// Fragment: do not close System.in if the resource belongs to the JVM lifecycle.
Console console = System.console();
String line;
if (console != null) {
    line = console.readLine("Nhập tên: ");
} else {
    java.io.BufferedReader reader = new java.io.BufferedReader(
        new java.io.InputStreamReader(
            System.in, java.nio.charset.StandardCharsets.UTF_8));
    line = reader.readLine();
}
~~~

The snippet above sits inside a method declaring or catching `IOException`. The no-console branch **does not print a prompt to stdout**, because stdin could be automated data from a pipeline; the UTF-8 charset is an **example protocol assumption**, not an assertion that every stdin uses UTF-8 encoding.

If the input required is a **password**, do not automatically fall back from `readPassword()` to `readLine()` or an echoed scanner and treat them as equivalent. Design an appropriate secret-provisioning path for CI/containers alongside the CLI mechanism for terminals; never expose secrets via stdout, shell history, logs, or command-line arguments.

## 11. Details on EOF, I/O Errors, and Formatting

**EOF:** with `readLine` and `readPassword`, a `null` result means there is no next line because input ended; with `reader().read()`, it is `-1`. A blank line where only Enter was pressed is still valid input (`""` or `char[0]`), not EOF. Terminals may signal EOF via OS-specific key combinations, though key shortcuts are not a stable Java contract.

**I/O exceptions:** `Reader.read()` declares checked `IOException`. Methods like `Console.readLine/readPassword` can throw `IOError` (a subclass of `Error`, not checked `IOException`) when I/O fails; you cannot rely solely on `catch(IOException)` for all errors from Console. Design CLI boundaries to exit/report errors properly without accidentally swallowing errors.

**Format errors:** `readLine(fmt,args...)`, `readPassword(fmt,args...)`, and `printf/format` use Java formatting syntax. Unescaped `%`, missing arguments, or mismatched types can cause `IllegalFormatException`. For example, a percentage prompt must use `"Mức 50%%: "` rather than arbitrarily passing `"Mức 50%: "` as a format string.

**I/O buffering and visibility:** `PrintWriter` has its own buffering/flush behavior. Before waiting for input with a reader, call `out.flush()` or `console.flush()` after using `out.print(...)`. `Console.readLine(fmt,args...)` is already a single prompt + read API, helping reduce coordination bugs across separate calls.

**Threading:** Console synchronizes critical operations; a multi-threaded program reading concurrently from one Console easily creates overlapping prompts. Funnel CLI input through a single handler or queue interactive requests.

## 12. Sensible Testing Strategies

You **should not** treat `System.console() != null` as a mandatory condition in every unit test. Test runners/JUnit/IDEs usually do not provide an interactive console. Instead:

1. Decouple data parsing/validation logic from reading `Console`. For instance, a `parseCommand(String input)` method accepting a plain string can be tested directly in JUnit.
2. Create a boundary accepting input via an interface or injected object if you need to test the Q&A flow. For small demos, simply checking the `System.console() == null` path is sufficient.
3. Verify **no-echo** behavior manually in a real terminal with `readPassword()`; do not expect CI to reproduce terminal interaction.
4. For the batch stdin branch, test separately using UTF-8 files with a defined contract; do not try testing secrets through an echoed pipeline.
5. Never capture/write password contents into snapshots, console logs, test failure messages, or reports. Test only behavior and cleanup without exposing sensitive data.

The interactive examples above do not have fixed stdout when users vary input, and terminal display depends on the environment. Evaluate them against **API contracts and scenarios** rather than transcript matching with real passwords.

## 13. Common Mistakes

1. **Calling `System.console().readLine()` without checking null.** Can throw `NullPointerException` in IDEs/CI/redirection.
2. **Assuming `System.in` is the same as `Console.reader()`.** One is a byte standard stream, the other is the console's reader, with different lifecycle/buffering characteristics.
3. **Using `readLine` to read passwords.** Normal input echoes, and produces a `String` that is hard to clear proactively.
4. **Converting a password `char[]` to `String` just for convenience.** Increases retention time and uncontrolled copies of the secret.
5. **Forgetting to clear `char[]` when finished.** Use `try/finally` and `Arrays.fill(...)` on the exact array received.
6. **Equating `null` with an empty string/array.** EOF and blank lines carry different meanings.
7. **Mixing `Scanner(console.reader())`, `Console.readLine()`, and direct `System.in` reads.** Buffering can lose or consume input unexpectedly.
8. **Forgetting to flush after printing a prompt with `writer().print`.** The prompt may not appear when the user is expected to type.
9. **Ignoring `IllegalFormatException` when a prompt contains `%`.** Format strings must be valid or use `%%`.
10. **Believing `PrintWriter.println` throws checked IOException whenever writing fails.** See `checkError()` and Writer behavior.
11. **Calling `reader().read()` once and calling it a display character.** The unit is a UTF-16 code unit; non-BMP emojis may require two `char`s.
12. **Assuming Console charset always equals the default charset.** `Console.charset()` can differ from `Charset.defaultCharset()`.
13. **Using readPassword as the sole security mechanism.** No-echo reduces on-screen exposure but does not replace protecting secrets in memory and the system.
14. **Assuming Console exists in every Java 17/21 runtime environment.** Availability depends on platform and launch method, not merely JDK version.

## 14. Self-Check Questions

1. Why can `System.in` work while `System.console()` is still `null`?
2. When should you choose `console.reader()` over `console.readLine()`?
3. What type does `console.writer()` return, and why should a prompt written with `print()` be flushed?
4. How do a user entering an empty string and signaling EOF differ in return value?
5. Why does `readPassword()` return `char[]` instead of `String`? What must be done after use?
6. Should you create a fallback `new Scanner(System.in).nextLine()` to read secrets when Console does not exist?
7. If a prompt says `"Hoàn thành 50%?"`, what must you watch out for when passing it to the `readLine(fmt,args...)` format overload?
8. Java 17 added `Console.charset()`; is it necessarily equal to `Charset.defaultCharset()`?
9. Why can mixing Scanner on console.reader with console.readLine make input unpredictable?
10. Why can't code in `catch (IOException e)` handle all I/O errors reported by `Console.readPassword()`?

**Answer hints:** (1) stdin can still be piped while console is unavailable; (2) when a custom character/token parser is needed instead of just a line; (3) `PrintWriter`, needs flushing so the prompt displays; (4) `""`/`char[0]` vs. `null`; (5) arrays can be cleared with `Arrays.fill` in finally; (6) do not do so silently because it may echo secrets; (7) escape `%` as `%%` or pass data as an argument; (8) no; (9) the reading layer may buffer ahead; (10) Console can throw `IOError` which is an `Error`, different from checked `IOException`.

## 15. Official References

- [Oracle Java SE 21 — Console](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/Console.html): contract for `reader`, `writer`, `readLine`, `readPassword`, null/EOF, I/O errors, charset, synchronized I/O, and password array protection.
- [Oracle Java SE 21 — System.console()](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/System.html#console()): conditions under which a console may not exist.
- [Oracle Java SE 21 — Reader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/Reader.html): reading characters, EOF `-1`, and checked `IOException`.
- [Oracle Java SE 21 — PrintWriter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/PrintWriter.html): `print/println/printf`, `flush`, and `checkError`.
- [Oracle Java SE 21 — Arrays.fill](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Arrays.html): clearing contents of a `char[]` when no longer needed.
- [Oracle Java SE 21 — Scanner](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Scanner.html): token parser from Reader and notes on scanner/buffering.

**Takeaway:** obtain Console via `System.console()` and **check for null**; `reader()`/`writer()` are for direct character operations; `readLine()` returns `String` and normally echoes; `readPassword()` returns `char[]` with echo disabled and should be cleared after use. When there is no console, design suitable separate batch/secret handling instead of accepting password input as ordinary plain text.
