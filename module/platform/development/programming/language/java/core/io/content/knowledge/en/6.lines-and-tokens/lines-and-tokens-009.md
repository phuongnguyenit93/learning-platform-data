# Scanner.ioException and Closing Data Sources in Java

`java.util.Scanner` helps read text data into **tokens**, numbers, strings, or lines. However, a real-world data-reading program must also distinguish **valid end of data (EOF)** from **I/O errors**, and must know **who is responsible for closing the source** when reading finishes. Both points are easily overlooked because `Scanner` absorbs certain `IOException`s from the data source on the caller's behalf.

This lesson focuses on `Scanner.ioException()`, `Scanner.close()`, the lifecycle of `Readable`/`Closeable` sources, and appropriate error-handling patterns for files, input streams, readers, and keyboard input. Examples use Java 17+.

## 1. Where Does Scanner Sit in the Reading Pipeline?

A typical pipeline looks like this:

```text
File / socket / System.in / byte source
               |
               v
       InputStream / Reader
               |
               | reads data, may raise IOException
               v
             Scanner
        splits tokens, parses numbers,
        handles delimiters
               |
               v
      hasNext(), next(), nextInt(),
      hasNextLine(), nextLine(), ...
```

`Scanner` can be constructed directly from a `Readable` (such as a `Reader`), `InputStream`, `File`, `Path`, `String`, and other source types. Which option fits depends on the source and character encoding requirements. When the source is bytes, choose an **explicit charset**, such as `StandardCharsets.UTF_8`, so text content is decoded consistently.

Different error situations:

| Situation | Typical Symptom |
| --- | --- |
| Data ends naturally | `hasNext()` / `hasNextLine()` becomes `false` |
| Source `Readable.read(...)` throws `IOException` | Scanner treats it as end of input; cause can be inspected via `ioException()` |
| Token exists but has invalid numeric type | `nextInt()` may throw `InputMismatchException` |
| Calling `next()` when no tokens remain | `NoSuchElementException` |
| Calling search/read operations on a closed Scanner | `IllegalStateException` |
| Opening a file fails in the constructor | Constructor may throw `IOException` / `FileNotFoundException` before a Scanner exists to inspect |
| Closing a `Closeable` source fails | `Scanner.close()` handles the error and may store the `IOException` for querying via `ioException()` |

Do not lump these scenarios into "Scanner returning false means success" or "any exception is a file error."

## 2. What Exactly Does Scanner.ioException() Do?

Signature:

```java
public IOException ioException()
```

This is a **query** method, not a data-reading command:

- Returns the **most recent `IOException`** recorded by Scanner from the underlying `Readable` source.
- Returns `null` if no such I/O exception has been recorded yet.
- Does not rethrow the exception automatically. You must inspect the return value and decide whether to report an error, log, retry, or halt.
- Can be called after reading finishes and also **after `close()`** to check for source-closing errors.
- It does **not** represent all parsing errors, malformed data formats, or failures in source-opening constructors.

According to the Java 17 API contract, if `read()` on the underlying `Readable` throws an `IOException`, Scanner **assumes it has reached the end of input**. Consequently, a `while (scanner.hasNext())` loop can terminate normally even though an I/O error just occurred underneath. You must query `ioException()` to tell them apart in this case.

### Mental Model: Reading Two Tokens Then Failing

```text
Actual source: "10 20" + [IOException while fetching further data]
                            |
                            v
Scanner may supply "10", "20" first, then hasNext() == false.
                                  |
                                  +--- ioException() != null
                                       -> source failed; do not treat data as complete.
```

How many tokens are returned before failure depends on read-ahead buffering, delimiter rules, and when the source throws the exception; **do not** predict that every source will yield exactly two tokens from a diagram. The takeaway is **never conclude success merely because the token loop finished**.

`ioException() == null` only means Scanner **has not recorded an `IOException` from the source**. It does not prove the data is business-valid, has the right field count, matches a checksum, uses the right charset, or that the whole expected file arrived.

## 3. Why Might IOException Not Surface Directly in hasNext()/next()?

`Scanner` is built for text and token parsing. It manages reading from a `Readable` and makes a design choice: **translate `IOException` read failures into an EOF-like signal at the token layer**, while keeping the underlying cause available for later inspection.

Example of usage that is **not safe enough**:

```java
try (Scanner scanner = new Scanner(source)) {
    while (scanner.hasNext()) {
        process(scanner.next());
    }
    // Without checking scanner.ioException():
    // a read IOException may have just caused the loop to terminate.
}
```

This is a snippet: `source` is a valid `Readable` source and `process` is a business function. When processing critical data, check for I/O errors **after reading**, and if you need to detect source-close errors, check **after closing** as well.

To avoid confusion:

- `hasNext() == false` may mean no tokens remain; check `ioException()` before declaring a stream completely read.
- `hasNextInt() == false` may mean the next token is not an integer per current locale/radix, or no tokens remain, or an underlying read error occurred. Check context; `ioException()` itself only answers about I/O.
- `nextInt()` may throw `InputMismatchException` on a wrongly typed token. That exception is **not** automatically mapped to `ioException()`.
- `next()`/`nextLine()` may throw `NoSuchElementException` when no matching content remains. Do not catch that exception alone and assume the source ended normally.

## 4. Runnable Java 17+ Example: Read Failure, Close Failure, and Lifecycle

The file `ScannerIoLifecycleDemo.java` below uses two simulated sources that produce controlled errors. The example needs no files on disk, so results are easily reproducible.

```java
import java.io.Closeable;
import java.io.IOException;
import java.nio.CharBuffer;
import java.util.Scanner;

public class ScannerIoLifecycleDemo {
    private static final class FaultyReadSource
            implements Readable, Closeable {
        int closeCalls;

        @Override
        public int read(CharBuffer target) throws IOException {
            throw new IOException("read failed");
        }

        @Override
        public void close() {
            closeCalls++;
        }
    }

    private static final class FaultyCloseSource
            implements Readable, Closeable {
        int closeCalls;

        @Override
        public int read(CharBuffer target) {
            return -1; // natural EOF
        }

        @Override
        public void close() throws IOException {
            closeCalls++;
            throw new IOException("close failed");
        }
    }

    public static void main(String[] args) {
        // 1. Error-free source; Scanner reads both numbers completely.
        Scanner normal = new Scanner("7 11");
        int sum = 0;
        while (normal.hasNextInt()) {
            sum += normal.nextInt();
        }
        System.out.println("normal sum: " + sum);
        System.out.println("normal ioException: " + normal.ioException());
        normal.close();

        // 2. Source throws IOException on the very first read.
        FaultyReadSource reader = new FaultyReadSource();
        Scanner readScanner = new Scanner(reader);
        System.out.println("read hasNext: " + readScanner.hasNext());
        System.out.println("read ioException: "
                + readScanner.ioException().getMessage());
        readScanner.close();
        System.out.println("read close calls: " + reader.closeCalls);

        // 3. Source ends naturally, yet closing the source throws IOException.
        FaultyCloseSource closer = new FaultyCloseSource();
        Scanner closeScanner = new Scanner(closer);
        System.out.println("close error before close: "
                + closeScanner.ioException());
        closeScanner.close();
        System.out.println("close error after close: "
                + closeScanner.ioException().getMessage());
        System.out.println("close attempts: " + closer.closeCalls);

        try {
            closeScanner.hasNext();
        } catch (IllegalStateException e) {
            System.out.println("closed scanner: "
                    + e.getClass().getSimpleName());
        }
    }
}
```

Compile and run with Java 17+:

```bash
javac ScannerIoLifecycleDemo.java
java ScannerIoLifecycleDemo
```

Stdout verified with JDK:

```text
normal sum: 18
normal ioException: null
read hasNext: false
read ioException: read failed
read close calls: 1
close error before close: null
close error after close: close failed
close attempts: 1
closed scanner: IllegalStateException
```

Key points to take away:

1. A plain string source has no `IOException`, so `normal.ioException()` returns `null`.
2. `readScanner.hasNext()` becomes `false` even though the cause is **`IOException("read failed")`**, not true EOF. The error is stored in `ioException()`.
3. When `readScanner.close()` is invoked, Scanner calls `close()` on `FaultyReadSource` exactly once because it implements `Closeable`.
4. `FaultyCloseSource.read()` returns `-1` (true EOF). Before closing, `ioException()` is `null`; after closing fails, `ioException()` holds `"close failed"`.
5. `Scanner.close()` does not declare `throws IOException`; source-closing errors are handled internally and may have to be retrieved via `ioException()`.
6. After `close()`, token-searching operations like `hasNext()` throw `IllegalStateException`. Keep the reference to Scanner solely to check post-close errors, not to continue reading.

This is an **intentional simulation** rather than an example of a real OS error. Real-world scenarios include disk errors, network disconnects, sources failing mid-read, or errors occurring while releasing resources.

## 5. Closing Scanner: Also Closes the Source When It Is Closeable

`Scanner` implements `Closeable` and `AutoCloseable`; it can be used in `try-with-resources`.

Contract of `Scanner.close()`:

- While Scanner is still open, it **calls `close()` on the reading source if that source implements `java.io.Closeable`**.
- If the source only implements `Readable` without `Closeable`, Scanner has no generic `close()` method to close that source.
- Calling `Scanner.close()` a second time does not close the source again per contract.
- Reading/searching tokens after close throws `IllegalStateException`.
- An IOException when closing the source may be recorded in `ioException()`; do not assume that because `scanner.close()` returned normally every underlying I/O close succeeded.

Ownership diagram:

```text
try-with-resources closes Scanner
             |
             v
         Scanner.close()
             |
             +-- source implements Closeable?
                    |
                YES | NO
                    | 
                    v
              source.close()        (no generic source-close operation)
                    |
             wrapped source may
             close underlying streams
```

Example:

```java
InputStream fileBytes = Files.newInputStream(path);
Scanner scanner = new Scanner(fileBytes, StandardCharsets.UTF_8);
scanner.close();
```

This is a snippet where `path` is a valid `Path`, requiring imports `java.io.*`, `java.nio.file.*`, `java.nio.charset.*`, `java.util.Scanner`, and handling `IOException` when opening the file. In the example, Scanner uses an internal Reader to decode from the InputStream; when Scanner closes, the wrapper chain typically closes both the Reader and the underlying InputStream. **Therefore, closing Scanner can render the original InputStream unusable.**

### Ownership Rules

- **Opening a file within the current method:** the method typically owns the resource and must close it when done. `try-with-resources` is the natural choice.
- **Receiving an `InputStream` / `Reader` from another object:** verify the ownership contract; avoid arbitrarily closing Scanner when the caller still needs the source.
- **Shared sources like `System.in`:** generally should not be closed automatically just because one user prompt completed, as doing so cuts off stdin for subsequent parts of the program.
- **In-memory `String` sources:** closing Scanner remains a consistent lifecycle practice, even though no OS file/network handle is held by the program.

Do not create multiple Scanners over the same `InputStream` or `Reader` without controlling read-ahead/buffering: one Scanner can consume bytes/chars ahead, leaving the other Scanner without expected data.

## 6. Try-with-resources and Checking ioException After Closing

Basic pattern for reading a file with an explicit charset:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.Scanner;

public class ReadFileLines {
    public static void main(String[] args) throws IOException {
        Path path = Path.of("input.txt");

        // Java 9+: an effectively final variable can be used in try(...).
        Scanner scanner = new Scanner(path, StandardCharsets.UTF_8);

        try (scanner) {
            while (scanner.hasNextLine()) {
                String line = scanner.nextLine();
                System.out.println(line);
            }
        }

        // Runs after close: detects both read errors and source-close errors.
        IOException failure = scanner.ioException();
        if (failure != null) {
            throw new IOException("Failed to read/close " + path, failure);
        }
    }
}
```

Run with JDK 17+:

```bash
javac ReadFileLines.java
java ReadFileLines
```

When running, `input.txt` must exist in the **current working directory**. The program prints each line read. Because content depends on the file, no fixed stdout is claimed here. If opening the file fails, the constructor throws `IOException` **before** the `try` block starts; in that case no Scanner exists to call `ioException()`.

Why `Scanner scanner` is deliberately declared outside `try`: you need to retain the **reference** to check `ioException()` after `try-with-resources` has called `close()`. Even though Scanner is closed, `ioException()` still reports the stored I/O exception; just do not call `hasNextLine()` afterward.

**Important limitation of this pattern:** if processing **inside** the loop throws an independent exception (such as invalid business data), the statement after the `try` block will not execute. The application needs its own error-reporting mechanism, or must check `ioException()` inside `finally` if recording I/O errors even when parsing fails is mandatory. Avoid blindly throwing a new exception inside `finally` that masks the original exception unless you have designed explicit exception precedence rules.

### Does try-with-resources Automatically Surface IOException on Close?

No. For `Scanner`, `close()` has return type `void` and **does not declare `throws IOException`**. It can store an `IOException` from the source inside `ioException()` rather than throwing it outward. Therefore:

```java
try (Scanner scanner = new Scanner(source)) {
    consume(scanner);
}
// The try block not throwing IOException does not prove source.close() succeeded.
```

This is an illustrative snippet: `source` is a closeable source and `consume` is a processing function. If the application must reliably detect close failures, retain the reference to query `ioException()` after close, or manage the source/Reader directly with an API whose close contract propagates close errors.

## 7. Distinguishing Read Errors, Parse Errors, and EOF

| Symptom | Possibilities | How to Verify |
| --- | --- | --- |
| `hasNext() == false` | EOF, no matching tokens left, or IOException while reading | Check `ioException()`; also understand input structure |
| `hasNextLine() == false` | End of lines or read error | Check `ioException()` |
| `next()` throws `NoSuchElementException` | No tokens remain | Check parser state and `ioException()` |
| `nextInt()` throws `InputMismatchException` | Token invalid for type/radix/locale | Handle type mismatch; `ioException()` may still be `null` |
| `nextInt()` throws `NoSuchElementException` | No token left to consume | Do not treat this exception itself as proof of IOException |
| `hasNextInt() == false` | Current token is not a number or no matching data remains | Can use `hasNext()` to separate wrong-type token from missing token |
| `ioException() != null` | Scanner's source reported an IOException during read/close | Handle the I/O cause in context |

Example when reading numbers:

```java
if (scanner.hasNextInt()) {
    int number = scanner.nextInt();
    // Process number.
} else if (scanner.hasNext()) {
    String invalidToken = scanner.next();
    // A token exists, yet this token cannot be parsed as an int.
} else {
    IOException failure = scanner.ioException();
    if (failure != null) {
        // Reading encountered an IOException.
    } else {
        // Currently no tokens remain; typically a valid EOF.
    }
}
```

This is a snippet: `scanner` was created beforehand, and the program imports `java.util.Scanner` / `java.io.IOException`. If the source can block, each `hasNext...` call may wait for data. `Scanner` buffers input and defaults to whitespace delimiters; configure `useDelimiter`/`useLocale`/`useRadix` to match the real format if the parser depends on them.

## 8. Handling System.in: When Should You Not Close It?

Common scenario:

```java
Scanner input = new Scanner(System.in, StandardCharsets.UTF_8);
System.out.print("Tên: ");
String name = input.nextLine();
System.out.println("Xin chào " + name);
// Do not call input.close() if multiple parts of the application still use System.in.
```

This is a snippet requiring `java.util.Scanner` and `java.nio.charset.StandardCharsets`. Omitting `close()` in this illustration is intentional: `System.in` is a **shared resource**, normally governed by the program's lifecycle. Calling `input.close()` can cascade and close `System.in`; subsequent input in another component will fail to work.

Nevertheless, there is no absolute rule saying "a Scanner on System.in must never be closed." In a standalone CLI program, when the application truly terminates and owns input, closing the resource can make sense. Base the decision on **ownership and lifecycle**, not simply on whether `try-with-resources` compiles.

Practical guidelines:

- Have only one component own the `System.in` Scanner and pass data or an input helper to other components.
- Do not create and close a new Scanner for every individual keyboard prompt when more prompts follow.
- If a Scanner lives throughout a CLI session, check `ioException()` at shutdown or when input fails.
- Do not overlook methods that can **block**, such as `hasNext()` or `nextLine()`, when designing timeouts and cancellation at the application layer.

## 9. Scenario: Scanner Created from a Reader with a Strict Decoder

A text-reading `Scanner` can receive data from an `InputStreamReader`. If the application requires UTF-8 bytes to be strictly valid, pass a decoder configured with `REPORT`:

```java
CharsetDecoder strict = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

Reader reader = new InputStreamReader(inputStream, strict);
Scanner scanner = new Scanner(reader);
try (scanner) {
    while (scanner.hasNextLine()) {
        String line = scanner.nextLine();
        // Process line.
    }
}
IOException readOrCloseFailure = scanner.ioException();
if (readOrCloseFailure != null) {
    throw readOrCloseFailure;
}
```

This is an **illustrative snippet**, requiring imports `java.io.*`, `java.util.Scanner`, and `java.nio.charset.*`; `inputStream` is a valid byte source and the method must handle `IOException`.

If `InputStreamReader` encounters malformed UTF-8 bytes under `REPORT`, it throws `MalformedInputException` (an `IOException`). Scanner treats that read error as end of input and saves it for `ioException()` to return. Hence **relying solely on `hasNextLine() == false` is insufficient** to prove valid UTF-8 text.

If you use a `Scanner` constructor with a charset without passing a configured decoder, do not assume its character-error policy matches the strict configuration above; consult the corresponding API contract. Furthermore, `Scanner` does not validate CSV/JSON structure, field counts, signatures, or checksums: those belong to business parser/validator layers.

## 10. What If Both a Read Error and a Close Error Occur?

`ioException()` only provides the **most recent I/O exception** Scanner recorded; it is not a full history of all failures. If a source throws an `IOException` while reading and then throws another `IOException` during closing, the value returned afterward may be the close error. Do not treat `ioException()` as a complete error log; if you need to diagnose both, capture the result right after the read loop and before closing.

Skeleton example (illustrates the idea, not a standalone program):

```java
Scanner scanner = new Scanner(source);
IOException readFailure;

try {
    while (scanner.hasNextLine()) {
        handle(scanner.nextLine());
    }
    readFailure = scanner.ioException(); // Before close.
} finally {
    scanner.close();                     // May update the stored exception.
}

IOException lastFailure = scanner.ioException(); // After close.
```

In this snippet, `source` is a `Readable` with known ownership, `handle` is a business method, and imports `java.util.Scanner`/`java.io.IOException` are needed. If `handle` throws an exception, `readFailure` may remain unassigned and the statement after `finally` will not run; therefore **do not use this skeleton verbatim as complete production code**. In real implementations, initialize `readFailure = null` and design `catch/finally` with clear exception precedence rules. The core message: errors can happen **before** or **during** close, and `ioException()` remembers only **the latest one**.

If you want detailed logging and error reporting for a strict protocol, wrap the underlying `Reader`/`InputStream` to observe exceptions directly, or implement lower-level reading logic so EOF and failures are distinguished right where they occur.

## 11. When to Use Scanner, and When to Switch to Another API?

`Scanner` is handy for regex token splitting, number parsing, and interactive input; it is **not the only choice** when large data streams or precise I/O error management are needed.

| Need | Usually Appropriate Choice |
| --- | --- |
| Small CLI reading numbers/tokens and user answers | `Scanner`, with an owned `System.in` lifecycle |
| Reading a few file lines and parsing tokens | `Scanner` + try-with-resources + `ioException()` |
| Processing very large text files line by line | `BufferedReader` / `Files.newBufferedReader` or `Files.lines` with proper resource closing |
| Need to catch `IOException` immediately at each read | `BufferedReader.readLine()` or `Reader.read(...)` directly |
| Binary protocols with record lengths | `InputStream`/`DataInputStream`/appropriate channels |
| Validating CSV, JSON, or specialized formats | Format-specific parser managing the stream per parser contract |

`BufferedReader` example:

```java
try (BufferedReader reader =
        Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        process(line);
    }
}
```

This is a snippet with `path` and `process` already defined and `IOException` handled. The difference: when `readLine()` encounters an I/O error, it **throws `IOException` directly**, making inline error catching more natural. That does not mean `BufferedReader` parses numbers and tokens automatically like Scanner; the two APIs serve different jobs.

## 12. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Checking only `hasNext() == false` and assuming the file finished cleanly | I/O error disguised as EOF | Check `ioException()` |
| Thinking `ioException()` rethrows the error automatically | Errors get ignored | Check for non-`null`, report/throw when needed |
| Assuming `InputMismatchException` is an IOException | Misclassifies data errors | Catch/check parse errors separately |
| Closing Scanner on `System.in` while more input is needed | Closes shared stdin source | Manage ownership and reuse one Scanner |
| Closing Scanner and then calling `nextLine()` | `IllegalStateException` | Do not read after close |
| Assuming close succeeded because `Scanner.close()` doesn't throw | Ignores IOException during source close | Call `ioException()` after close if needed |
| Checking `ioException()` only before close | Misses close errors | Consider checking again after close |
| Failing to open source/file in constructor yet trying to call `scanner.ioException()` | Scanner does not exist yet | Catch exceptions at the source-opening constructor |
| Creating multiple Scanners sharing one InputStream | Read-ahead contention, lost/reordered tokens | Single owner or explicit data distribution design |
| Assuming `ioException() == null` means the file is valid | Misses missing fields, bad format, charset issues | Validate data independently of I/O errors |
| Ending a numeric loop on `hasNextInt() == false` without inspecting bad tokens | Non-numeric tokens get left behind | Check `hasNext()` and input data policy |
| Using `Scanner` across threads without synchronization | Unsafe parser state | One source per consumer, or explicit synchronization |

## 13. Self-Check Quiz

1. **Is `hasNext()` returning `false` enough to guarantee normal EOF?** No; Scanner may have received an `IOException` from the source and treated it as end of input.
2. **What does `ioException()` return?** The most recent `IOException` recorded from Scanner's source, or `null` if none occurred.
3. **Does `ioException()` throw the stored exception?** No; it merely returns an exception object for the application to inspect.
4. **After `Scanner.close()`, can you still call `ioException()`?** Yes; that is how you detect stored close errors. However, you cannot continue scanning tokens.
5. **Does closing Scanner always close the source?** Scanner calls `close()` if the underlying source implements `Closeable`; with wrapped sources, closing may propagate down the streams.
6. **Why is try-with-resources alone insufficient if you need to detect source-close errors?** `Scanner.close()` can retain the IOException internally; check `ioException()` afterward.
7. **Does `nextInt()` throwing `InputMismatchException` mean a file I/O error?** No; it typically means the current token cannot be parsed as an int.
8. **If opening a file fails in the constructor, how do you check `ioException()`?** You cannot, because Scanner was never created; catch the exception directly from the open operation.
9. **Why shouldn't you arbitrarily close `Scanner(System.in)`?** Because closing the scanner can close the shared console input stream needed by other components.
10. **When should you prefer `BufferedReader`?** When you need line-by-line reading and direct `IOException` throwing rather than Scanner-style token parsing.

## Java 17 References

- [`Scanner` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Scanner.html).
- [`Readable` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Readable.html).
- [`Closeable` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Closeable.html).
- [`BufferedReader` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedReader.html).
- [`InputStreamReader` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStreamReader.html).

**Key takeaway:** `Scanner` can turn a source `IOException` into the end of token scanning, so **`ioException()` is an essential check before concluding a read succeeded**. `close()` also closes the source if the source is `Closeable`; manage source ownership carefully and check close errors when data reliability demands it.
