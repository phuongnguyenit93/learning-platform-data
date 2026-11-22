# Auto-Flush and Which Operations Actually Trigger Flush in Java I/O

When writing to a console, file, or socket, a program usually does not deliver every character or byte immediately to the destination. Several Java I/O classes use a **buffer** to batch data; calling **`flush()`** requests pushing buffered data down to underlying write layers. **Auto-flush** is a mode causing certain operations to trigger flushing automatically.

Key point: **there is no single auto-flush rule shared across all Java I/O classes**. `PrintWriter` and `PrintStream` have different trigger conditions; `BufferedWriter.newLine()` does not flush by itself. Therefore, "containing a newline character" and "having been flushed" are not always equivalent.

## 1. How Do `write`, `flush`, and `close` Differ?

- **`write`/`print`:** feeds data into the stream. If buffering is present, the data may not yet have moved to the next receiving layer.
- **`flush()`:** requests forwarding buffered data to lower layers; wrappers typically forward `flush` to the wrapped stream. This **does not guarantee** bytes are durably on disk or that an application on the other end of a network has processed them.
- **`close()`:** closes the stream, generally finalizing any remaining buffered data and releasing resources. For shared streams like `System.out`, do not close them arbitrarily.

**Auto-flush** does not mean "every `write` flushes", "every `\n` flushes", or "no need to think about buffering". You must identify the **object type**, **constructor**, and **exact method being called**.

```text
Application
    |
    | print/write/println/printf/format
    v
PrintWriter or PrintStream
    |
    | may call flush if autoFlush condition is met
    v
BufferedWriter / OutputStreamWriter / BufferedOutputStream
    |
    | flush to lower layer
    v
OS buffer -> file / socket / terminal / device
```

When data appears on a console or reaches another application also depends on multiple layers. `flush()` is a request on the write API, not an ACK from the receiving system.

## 2. `PrintWriter`: Which Methods Actually Trigger Auto-Flush

`PrintWriter` writes **text** through a `Writer` or `OutputStream`. To enable auto-flush:

```java
PrintWriter out = new PrintWriter(destination, true);
```

This is an illustrative code snippet: `destination` is an existing `Writer` or `OutputStream`, with `import java.io.PrintWriter`. Passing `true` enables auto-flush, and `false` disables it. Normal constructors without an `autoFlush` argument **disable** this mode by default.

By the `PrintWriter` contract, when the auto-flush flag is `true`, the method groups that **trigger a flush** are:

1. `println(...)`, including zero-argument `println()`;
2. `printf(...)`, even when the format string has **no** newline;
3. `format(...)`, even when the format string has **no** newline.

Conversely, calling only `print(...)`, `write(...)`, or `append(...)` **does not trigger auto-flush under `PrintWriter` rules**, even if the data contains `'\n'`.

| Operation on `PrintWriter` with autoFlush=true | Triggers Auto-Flush per Contract? |
| --- | --- |
| `out.print("Hello")` | No |
| `out.print("Hello\n")` | No |
| `out.write("Hello\n")` | No |
| `out.write('\n')` | No |
| `out.append('\n')` | No |
| `out.println("Hello")` | **Yes** |
| `out.println()` | **Yes** |
| `out.printf("n=%d", 7)` | **Yes**, even without `%n` |
| `out.format("n=%d", 7)` | **Yes**, even without `%n` |
| `out.flush()` | Explicit flush, regardless of autoFlush |
| `out.close()` | Finalizes and closes the stream |

**Important trap:** `out.println("x")` both writes the platform's line terminator and auto-flushes; `out.print("x\n")` only writes a string with LF, **without auto-flushing** under the `PrintWriter` contract. Both may look identical on Linux, yet differ in when data is pushed to lower layers.

When `autoFlush=false`, `println`/`printf`/`format` **do not auto-flush due to that flag**. Data can still be forwarded when the buffer fills, through lower-layer mechanisms, or when you call `flush()` or close the stream. Disabling auto-flush does not mean data sits completely untouched until closing.

## 3. Runnable Java 17+ Example: Counting `flush()` Calls on the Target Stream

Instead of guessing from when text appears in the terminal, let us create a mock `Writer` to count how many times `flush()` is invoked. The program uses `PrintWriter` with `autoFlush=true` and `BufferedWriter` without auto-flush.

Save the file as **`AutoFlushDemo.java`**:

```java
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.PrintWriter;
import java.io.Writer;

public class AutoFlushDemo {

    public static void main(String[] args) throws IOException {
        SpyWriter printTarget = new SpyWriter();

        try (PrintWriter out = new PrintWriter(printTarget, true)) {
            out.print("A");
            System.out.println("PrintWriter after print: "
                    + printTarget.flushCount);

            out.write("\n");
            System.out.println("PrintWriter after write LF: "
                    + printTarget.flushCount);

            out.println("B");
            System.out.println("PrintWriter after println: "
                    + printTarget.flushCount);

            out.printf("n=%d", 7);
            System.out.println("PrintWriter after printf: "
                    + printTarget.flushCount);

            out.format(" m=%d", 8);
            System.out.println("PrintWriter after format: "
                    + printTarget.flushCount);

            out.flush();
            System.out.println("PrintWriter after explicit flush: "
                    + printTarget.flushCount);
        }

        SpyWriter bufferedTarget = new SpyWriter();
        try (BufferedWriter out = new BufferedWriter(bufferedTarget)) {
            out.write("C");
            out.newLine();
            System.out.println("BufferedWriter after newLine: "
                    + bufferedTarget.flushCount);

            out.flush();
            System.out.println("BufferedWriter after explicit flush: "
                    + bufferedTarget.flushCount);
        }
    }

    static final class SpyWriter extends Writer {
        private final StringBuilder characters = new StringBuilder();
        int flushCount;

        @Override
        public void write(char[] chars, int offset, int length) {
            characters.append(chars, offset, length);
        }

        @Override
        public void flush() {
            flushCount++;
        }

        @Override
        public void close() {
            // Mock target used only to observe flush calls.
        }
    }
}
```

Compile and run with JDK 17+:

```bash
javac -encoding UTF-8 AutoFlushDemo.java
java AutoFlushDemo
```

**Verified stdout:**

```text
PrintWriter after print: 0
PrintWriter after write LF: 0
PrintWriter after println: 1
PrintWriter after printf: 2
PrintWriter after format: 3
PrintWriter after explicit flush: 4
BufferedWriter after newLine: 0
BufferedWriter after explicit flush: 1
```

Explanation:

- `print("A")` and `write("\n")` do not auto-flush, so the counter stays at 0.
- `println("B")` auto-flushes, raising the counter to 1.
- `printf("n=%d", 7)` and `format(" m=%d", 8)` each flush once more despite having no newline.
- Explicit `flush()` brings the counter to 4.
- `BufferedWriter.newLine()` only writes the line terminator; an explicit `flush()` is needed for `SpyWriter` to receive a flush call.

`SpyWriter` measures only `flush()` calls to the **target writer**, not physical file durability or network delivery latency. The example prints counts **before the wrapper closes** so closing is not mixed into the measurement.

## 4. `PrintStream`: Different Rules from `PrintWriter`

`PrintStream` is a byte-output class with text-printing methods; `System.out` and `System.err` have type `PrintStream`. It can be created with explicit auto-flush:

```java
import java.io.OutputStream;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;

// Assuming OutputStream destination already exists:
PrintStream out = new PrintStream(
        destination, true, StandardCharsets.UTF_8
);
```

Per the API documentation, when `PrintStream`'s auto-flush flag is enabled, events that can trigger a flush to the underlying byte stream are:

- **Writing a byte array**, such as `write(byte[])`, `write(byte[], off, len)`, or `writeBytes(byte[])`;
- **Calling `println(...)`**;
- **Writing a newline character or byte `'\n'`**.

Thus, `PrintStream.write('\n')` **triggers auto-flush**, whereas `PrintWriter.write("\n")` **does not trigger auto-flush under `PrintWriter`'s own contract**.

| Operation on `PrintStream` with autoFlush=true | Conclusion |
| --- | --- |
| `out.write('X')` | No newline byte trigger |
| `out.write('\n')` | **Triggers** on newline byte |
| `out.write(new byte[] {65, 66})` | **Triggers** on byte-array write |
| `out.writeBytes(new byte[] {65, 66})` | **Triggers** on byte-array write |
| `out.println("X")` | **Triggers** on `println` |
| `out.print("X\n")` | Contains newline character in the data |
| `out.print("X")` | Do not rely on this call alone as an interactive flush guarantee |
| `out.printf("n=%d", 7)` | Do not treat `printf` by name as its own trigger; depends on actual bytes/newlines written |
| `out.flush()` | Explicit flush regardless of configuration |

`PrintStream` may encode characters to bytes through internal steps. Therefore, do not assert an *exact flush count* for arbitrary `print(...)` or `printf(...)` calls from the API table alone; focus on the documented trigger events and call `flush()` explicitly when timing is a design requirement.

Example:

```java
byte[] payload = {65, 66};
out.write(payload);   // PrintStream autoFlush=true: writes byte array.
out.write('\n');      // PrintStream autoFlush=true: newline byte.
```

Here `out` is an open `PrintStream`. `write` writes **raw bytes**; it does not automatically convert a payload into charset-encoded text. If `out` is a `BufferedOutputStream` or another `OutputStream`, `PrintStream`'s auto-flush rules do not apply to it.

## 5. `BufferedWriter.newLine()` and `BufferedOutputStream`

`BufferedWriter` optimizes character writing; `BufferedOutputStream` optimizes byte writing. Both have `flush()` and `close()`, yet **do not have an `autoFlush=true` flag like `PrintWriter`/`PrintStream`**.

```java
writer.write("Dòng 1");
writer.newLine();
writer.write("Dòng 2");
writer.flush();
```

This illustrative snippet assumes `writer` is an open `BufferedWriter`. `newLine()` only writes the platform's line separator: LF on many Unix systems, and usually CRLF on Windows. It **does not auto-flush**.

For byte streams:

```java
output.write(bytes);
output.flush();
```

`output` is an open `BufferedOutputStream` and `bytes` is a byte array. The buffer may forward data when full or via internal thresholds, yet writing `'\n'` into a buffered stream **does not carry `PrintStream`'s auto-flush behavior**.

Easy confusion: `BufferedWriter.newLine()` and `PrintWriter.println()` may produce the same line terminator. However, `PrintWriter.println()` auto-flushes if the flag is enabled; `BufferedWriter.newLine()` does not.

## 6. Console: Showing a Prompt Before Reading Input

Suppose a program must print a prompt without ending the line, then wait for the user:

```java
import java.util.Scanner;

System.out.print("Nhập tên: ");
System.out.flush();  // Push the prompt before waiting for the user.

Scanner scanner = new Scanner(System.in);
String name = scanner.nextLine();
System.out.println("Xin chào, " + name);
```

This is an illustrative snippet meant for `main` with `Scanner` imported. Calling `flush()` lets your code **actively** control when the prompt is pushed out. Do not rely solely on assuming "the console displays it immediately", because the application might run in an IDE, pipe, terminal, test harness, or with `stdout` redirected.

`System.out` is a `PrintStream`, yet you should not depend on an unverified auto-flush configuration to decide when prompts appear; the program or a framework could even replace `System.out` via `System.setOut(...)`. When an explicit flush is needed, call `System.out.flush()`.

Do not close `System.in`/`System.out` mid-application just to flush a prompt: they are shared resources. Depending on ownership, also think carefully before closing a `Scanner` wrapping `System.in`.

## 7. `printf`, `format`, and `%n`

With `PrintWriter` autoFlush=true, **`printf`/`format` auto-flush even when the format string has no newline**:

```java
writer.printf("Tiến độ: %d%%", 75);
writer.format(" | Tổng: %d", 100);
```

Here `writer` is a `PrintWriter` with auto-flush enabled. Inside the format string, `%%` is a literal percent sign.

Three mechanisms to distinguish:

- **`"\n"`:** fixed LF character, not necessarily the platform line separator.
- **`"%n"`:** format specifier producing the platform-appropriate newline.
- **`println(...)`:** method that prints a line and ends it; on `PrintWriter` with auto-flush enabled, it also triggers a flush.

Example:

```java
writer.print("OK\n");     // No auto-flush per PrintWriter rules.
writer.printf("OK");      // Auto-flushes, even without a newline.
writer.printf("OK%n");    // Both ends the line and auto-flushes.
```

These snippets do not have identical meaning across every kind of `Writer` or `PrintStream`. Always check which API is actually being invoked.

## 8. Does `flush()` Mean "Write Succeeded"?

`flush()` can push bytes out of Java-level buffers, yet it is **not equivalent to**:

- "The file is durably saved on storage": the OS and hardware may still buffer writes. If file synchronization is required, choose an appropriate API and understand its limits, such as `FileChannel.force(...)`.
- "It reached the application across the network": sockets/networks and the receiving application have independent state. To know the receiver **processed** it, you need protocol-level acknowledgment.
- "No I/O error occurred": write calls can fail, and error reporting varies by class.

### `close()` Ends the Lifecycle

Typically use `try-with-resources`:

```java
try (BufferedWriter writer = Files.newBufferedWriter(
        path, StandardCharsets.UTF_8)) {
    writer.write("Nội dung");
    writer.newLine();
}
```

This is an illustrative method/block requiring a `path` variable and imports for `BufferedWriter`, `Files`, and `StandardCharsets`. `close()` normally drains remaining buffered content and closes the resource. If you need to **keep writing**, call `flush()` when needed—do not `close()`.

### Errors and `checkError()`

`PrintWriter` and `PrintStream` do not report `IOException` directly from normal print methods; they record errors internally. You can check:

```java
writer.println("Đã ghi");
if (writer.checkError()) {
    throw new IllegalStateException("Không thể ghi đầu ra");
}
```

Here `writer` is a `PrintWriter`. **`checkError()` may invoke flush automatically before checking the error state**. Therefore, when measuring "which method triggered a flush", do not insert `checkError()` between measurements without accounting for this side effect.

Unlike the two Print classes, `BufferedWriter.write()` and `BufferedWriter.flush()` can throw `IOException`, letting the application handle exceptions under standard contracts.

## 9. Auto-Flush and Performance

Auto-flush fits interactive flows where the receiver needs to see data early, though flushing too frequently can negate the benefits of buffering.

Example:

```java
for (int i = 0; i < 10_000; i++) {
    writer.println(i);
}
```

If `writer` is a `PrintWriter` with auto-flush enabled, **every `println` triggers a flush**. With files or networks, this can cause excessive I/O round-trips.

When writing large amounts of data where per-line immediacy is unnecessary, consider `BufferedWriter` or `PrintWriter` with auto-flush disabled, combined with batched flushes and proper closing. Conversely, for prompts or two-way protocols waiting on input, delaying a flush can stall both sides.

**There is no single "always fastest" configuration.** Choose flush points based on communication requirements and benchmark with your actual application.

## 10. Quick Comparison Table

| Class / Stream Type | When Does It Flush? | What Not to Infer |
| --- | --- | --- |
| `BufferedWriter` | `flush()`, close, or buffer eviction | `newLine()` does not auto-flush |
| `BufferedOutputStream` | `flush()`, close, or buffer flush | Writing a newline adds no special trigger |
| `PrintWriter` autoFlush=false | Explicit flush/close or lower-layer handling | `println` does not auto-flush when flag is off |
| `PrintWriter` autoFlush=true | **`println`, `printf`, `format`**, explicit flush/close | `print("\n")` and `write("\n")` do not auto-flush |
| `PrintStream` autoFlush=true | **Byte-array writes, `println`, newline**, explicit flush/close | Do not apply `PrintWriter`'s table verbatim |
| `System.out` | Depends on actual `PrintStream` and usage; has `flush()` | Do not assume every `print` flushes immediately |

Underlying streams may push data early when buffers fill; this table lists **contractual trigger points**, not physical display or transmission times.

## 11. Common Mistakes

| Mistake | Consequence / Explanation | Correct Practice |
| --- | --- | --- |
| "`print("\n")` is just like `println()` for auto-flush" | False for `PrintWriter` | Call `println` or `flush()` |
| "`BufferedWriter.newLine()` auto-flushes" | Only writes the line separator | Call `flush()` at synchronization points |
| "`printf` needs `%n` to flush" | `PrintWriter` triggers on the `printf` call itself | Separate formatting from auto-flush rules |
| "`PrintStream` and `PrintWriter` behave identically" | `PrintStream` triggers include byte arrays/newlines | Check the exact class API |
| "Flush means the file is safe against power loss" | OS/devices maintain their own state | Use file-sync techniques when required |
| "Flush means the server processed it" | Not an application-level ACK | Design a confirmation protocol |
| "Not seeing a prompt means data was lost" | Could be buffering or redirected stdout | Flush explicitly and check the environment |
| "Using close to display a prompt" | Close ends the stream so writing cannot continue | Use `flush()` |
| "`checkError` only reads a flag" | It may call flush | Account for the side effect |
| "Auto-flush always improves performance" | Constant flushing adds overhead | Pick an appropriate flush frequency |

## 12. Self-Check

1. After `new PrintWriter(target, true)`, does `print("A\n")` auto-flush? **No**.
2. On the same writer, does `printf("x=%d", 3)` without a newline auto-flush? **Yes**.
3. Does `BufferedWriter.newLine()` auto-flush? **No**.
4. On `PrintStream` with autoFlush=true, does `write('\n')` trigger? **Yes**, due to the newline byte.
5. On `PrintStream` with autoFlush=true, does `write(new byte[]{1, 2})` trigger? **Yes**, due to writing a byte array.
6. Why call `System.out.flush()` after `print("Nhập: ")` before `Scanner.nextLine()`? **To actively push the prompt out** before waiting for input.
7. Does `flush()` prove bytes are durably written to disk or processed by a server? **No**.
8. Can `PrintWriter.checkError()` affect the flush count? **Yes**, because the method may flush while checking.
9. For a million lines that do not need immediate visibility, what can per-line auto-flush cause? **Increased I/O overhead**.

**Takeaway:** `PrintWriter` auto-flushes on **`println`, `printf`, `format`** (when enabled); `PrintStream` auto-flushes on **`println`, byte-array writes, and newlines** (when enabled); `BufferedWriter` needs an **explicit `flush()`** where data must be pushed out. Whenever timing matters, call `flush()` explicitly and do not confuse it with durable storage or receiver processing guarantees.
