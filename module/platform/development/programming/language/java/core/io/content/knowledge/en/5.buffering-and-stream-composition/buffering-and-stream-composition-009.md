# How Does `Reader.ready()` Differ from an EOF Check in Java I/O?

## 1. Two Completely Different Questions

When reading data with `java.io.Reader`, two questions are easily confused:

- **Readiness:** If you call `read()` next, will that operation have to **wait for input data**? That is the purpose of `Reader.ready()`.
- **End of stream / EOF:** Has the source **run out of characters** per the reader's contract? That is reported by the **return value of the read operation**, such as `read() == -1` or `readLine() == null`.

**`ready()` is not an EOF check.** A reader might not be ready *at this instant* yet still have data arriving later; conversely, some readers return `true` when already at EOF because the next `read()` call can return `-1` immediately without waiting.

According to the Java SE 17 contract, `Reader.ready()` returns `true` if the next `read()` call **is guaranteed not to block for input**. Returning `false` merely means **there is no such guarantee**; it **does not mean** the next `read()` call is guaranteed to block.

~~~text
                  QUESTION: what happens on the next read?
                         |
             +-----------+-----------+
             |                       |
        reader.ready()           reader.read()
             |                       |
       true / false          char / -1 / IOException
             |                       |
       readiness status         content / EOF / error
       for the next read()
~~~

Practical example: a network connection might not have received further characters yet at the moment you check, so `ready()` is `false`, yet the sender is still active and will send more; **that is not EOF**.

## 2. API Comparison Table

| Criterion | `Reader.ready()` | `Reader.read()` / `Reader.read(char[])` | `BufferedReader.readLine()` |
| --- | --- | --- | --- |
| Purpose | Asks whether the next `read()` must wait for input | Actually reads characters | Actually reads one line |
| Typical return values | `boolean`: `true`/`false` | `int`: char value, character count, or `-1` | `String` or `null` |
| EOF indicator | **None** | **`-1`** | **`null`** |
| Can block? | Not used to read data | Can block waiting for characters, error, or EOF | Can block until a line, error, or EOF arrives |
| Consumes characters? | Does not retrieve characters for the program | Yes | Yes |
| Use as loop condition to read to end of file? | **No** | **Yes**, check `-1` | **Yes**, check `null` |

With `Reader.read()`, the result is an integer from `0` to `65535` representing a UTF-16 unit (`char`), or `-1` when the source is exhausted. **Never cast to `char` before checking `-1`**: casting destroys the EOF sentinel value.

With `Reader.read(char[], off, len)`, the result is the number of characters read, or `-1` if the source is exhausted; if `len == 0`, the method is allowed to return `0` without reading any characters. For a read with `len > 0` on standard-contract readers, having no characters due to EOF is signaled by `-1`, not `0`.

With `BufferedReader.readLine()`, an empty line returns `""` (empty String); **only `null` is EOF**. A final line without a trailing newline is still returned if characters remain.

## 3. Java 17+ Program Proving `ready() == true` Can Still Occur at EOF

`StringReader` reads from a string already residing in memory. For an open `StringReader`, `read()` can resolve immediately even when no characters remain and it will return `-1`. The JDK's `StringReader.ready()` implementation returns `true` in this case.

Create **`ReadyAtEofDemo.java`**:

~~~java
import java.io.IOException;
import java.io.StringReader;

public class ReadyAtEofDemo {
    public static void main(String[] args) throws IOException {
        try (StringReader reader = new StringReader("Hi")) {
            System.out.println("readyBefore=" + reader.ready());
            System.out.println("first=" + (char) reader.read());
            System.out.println("second=" + (char) reader.read());

            int next = reader.read();
            System.out.println("readAtEof=" + next);
            System.out.println("readyAtEof=" + reader.ready());
            System.out.println("readAgain=" + reader.read());
        }
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac -encoding UTF-8 ReadyAtEofDemo.java
java ReadyAtEofDemo
~~~

Stdout:

~~~text
readyBefore=true
first=H
second=i
readAtEof=-1
readyAtEof=true
readAgain=-1
~~~

Explanation:

1. `readyBefore=true`: the two characters in memory can be read immediately.
2. Two `read()` calls consume `H` and `i` in turn.
3. The next read returns **`-1`**: EOF reached.
4. `readyAtEof=true` yet still at EOF. Reason: the next `read()` returns `-1` immediately without waiting for input.
5. Yet another read continues returning `-1`.

**Conclusion from the example:** If you use `while (reader.ready())` to check "is there more data," the program can keep looping at EOF without stopping; if inside the loop you read characters by casting `(char) reader.read()`, it may misinterpret `-1` as normal data.

**Scope of the example:** `readyAtEof=true` above is specific to `StringReader`; do not infer that every `Reader` returns `true` at EOF. What holds true for every `Reader` is **never use `ready()` as an EOF marker**.

## 4. `ready() == false` Also Does Not Prove Data Is Exhausted

Conversely, `false` only says the reader **does not guarantee** the next `read()` will not wait. The read might block, or it might return a character immediately, throw an error immediately, or return EOF immediately depending on the reader.

Typical scenario: a streaming source (such as data arriving over a network or pipe) has no character ready to return at the instant you check. If the sender is only pausing briefly, there is no reason to conclude the source has closed.

~~~text
Time T0: receiver may observe ready() == false
Time T1: sender transmits more bytes
Time T2: read() can return characters
Time T3: sender closes the stream per protocol
Time T4: read() can return -1 (EOF)
~~~

These timestamps are only an illustrative scenario, not a promise that every `Reader` returns `false` at T0 or ends in that exact sequence.

**Common mistake:**

~~~java
// WRONG: ready() == false does not prove EOF.
while (reader.ready()) {
    int ch = reader.read();
    // Process ch...
}
~~~

This snippet can **drop data** if `ready()` temporarily returns `false`; on a specific reader that stays ready at EOF, it also risks an infinite loop if you fail to check `read()`'s return value.

**The right way when the goal is reading all characters until EOF:**

~~~java
// Correct: requires an open Reader reader and IOException handling.
int ch;
while ((ch = reader.read()) != -1) {
    // Use (char) ch only after ruling out -1.
    System.out.print((char) ch);
}
~~~

This is a code fragment for a method that already has a valid reader; it can **block when no data is available yet**. If the stream never closes and there is no other termination rule, the loop can also wait indefinitely. That is a lifecycle issue of the data source, which `ready()` cannot fix.

## 5. `BufferedReader.ready()` and the Meaning of Buffered Data

`BufferedReader` is a wrapper (`decorator`) with a character buffer to reduce reads from the underlying source. Per Java SE 17, `BufferedReader.ready()` can return `true` **when the buffer still contains characters or the underlying reader is ready**.

~~~text
InputStream (bytes)
       |
       v
InputStreamReader (decodes bytes -> chars by charset)
       |
       v
BufferedReader (holds prefetched chars in buffer)
       |
       +--> ready(): buffer has chars / source ready?
       |
       +--> read() / readLine(): actually consumes chars
~~~

Example of buffering effects:

- The underlying reader may be **temporarily not ready** to read new bytes/characters from the source.
- Yet `BufferedReader` already prefetched some characters into its buffer, so **`BufferedReader.ready()` can still be `true`**.
- Once the buffer drains, `ready()` may switch to `false`; that does not mean the source hit EOF.
- When EOF arrives, the reliable signal remains **`read() == -1`** or **`readLine() == null`**, not any particular value of `ready()`.

**A subtle distinction:** `ready()`'s contract speaks about **the next `read()` call** not blocking for input. If the program calls `readLine()`, and only a few characters sit in the buffer with no line terminator yet, `readLine()` may still have to wait. Thus **`ready() == true` is not a guarantee that an entire next line is ready**.

Similarly, a `read(char[])` call requests multiple characters; even after reading some characters, filling the remainder depends on the reader and source conditions. Do not use `ready()` to guarantee message length or whole-payload read speed.

## 6. Reading Line-by-Line to EOF: Distinguishing EOF from Empty Strings

Create **`ReadLinesDemo.java`**:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.StringReader;

public class ReadLinesDemo {
    public static void main(String[] args) throws IOException {
        String input = "first\n\nlast";

        try (BufferedReader reader =
                new BufferedReader(new StringReader(input))) {
            String line;
            while ((line = reader.readLine()) != null) {
                System.out.println("line=[" + line + "]");
            }
            System.out.println("EOF");
        }
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 ReadLinesDemo.java
java ReadLinesDemo
~~~

Stdout:

~~~text
line=[first]
line=[]
line=[last]
EOF
~~~

The example shows:

- `"first"`: the first line ends with LF.
- `""`: the second line is empty, **not EOF**.
- `"last"`: the final line without a newline character is still returned.
- `null`: no more lines remain to read, only then is `EOF` printed.

Never write `while (reader.readLine() != "")` or `while (reader.ready())` instead of comparing against `null`. The `line` variable in the condition must be assigned from **one single read** so you do not accidentally skip lines.

For a real UTF-8 text file, you can use:

~~~java
// Code fragment inside a method with Path path and IOException handling.
try (BufferedReader reader =
        java.nio.file.Files.newBufferedReader(
                path, java.nio.charset.StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        // Process each line.
    }
}
~~~

Choosing an explicit charset ensures byte-to-character conversion matches the file format. Wrapping with a buffer helps performance without changing how EOF is detected.

## 7. Reading in `char` Chunks: Watch the Count Value and `-1`

When reading large data, instead of reading character by character, use a buffer:

~~~java
// Code fragment inside a method with Reader reader and IOException handling.
char[] buffer = new char[4096];
int count;
while ((count = reader.read(buffer, 0, buffer.length)) != -1) {
    // Only the range [0, count) contains newly read characters from this pass.
    process(buffer, 0, count);
}
~~~

Here `process` is a handler provided by the program; this illustrative snippet is not standalone runnable code. The buffer size 4096 is the maximum per request; **`read` does not promise to return all 4096 characters**. If it returns 120, only the first 120 elements are new data. Loop until `-1`, not based on `ready()`.

In the standard `Reader.read(char[], off, len)` contract, for `len > 0`, `-1` means EOF; if `len == 0`, it may return `0` even at EOF. Always use a non-empty array with `buffer.length > 0` for normal read loops.

If the data is binary (images, ZIPs...), use `InputStream.read(byte[])` and `-1` accordingly. **`InputStream.available()` is also not an EOF detector**: it reports an estimate of bytes readable without blocking, not the remaining stream size or end marker.

## 8. Why Shouldn't `ready()` Be Used for Polling or Timeouts?

A pattern like this often looks reasonable yet is unsafe:

~~~java
// WRONG if the goal is to read an entire stream:
while (true) {
    if (reader.ready()) {
        int ch = reader.read();
        if (ch == -1) break;
        handle(ch);
    } else {
        // Assume EOF and exit, or busy-spin waiting.
        break;
    }
}
~~~

If `ready()` returns `false` merely because data has not arrived yet, `break` **drops data that will arrive later**. Replacing `break` with an unbounded loop can cause the program to **busy-spin**, burning CPU. Moreover, even when `ready()` returns `true`, other processing steps can still take time or fail; it is not a deadline/timeout mechanism.

Choose a solution that matches the requirement:

| Requirement | Approach |
| --- | --- |
| Read a finite file/stream to the end | `read() != -1`, `readLine() != null`, or `read(buffer) != -1` |
| Protocol with a known message length | Read the exact specified length; treat short bytes/chars as a protocol error |
| Delimiter-terminated messages | Read until the specified delimiter; do not infer from `ready()` |
| Socket that may wait a long time | Configure timeouts or lifecycle limits at the socket/protocol layer; handle EOF and errors separately |
| Event-driven/non-blocking connections | Use APIs designed for non-blocking I/O like `java.nio.channels.Selector` with an appropriate channel, instead of faking it with `Reader.ready()` |
| Only want to know if the next `read()` is guaranteed not to wait for input | Then consider `ready()`, while still checking the return value of `read()` |

**Socket EOF:** typically appears only when the sender closes its write half of the connection, or the protocol/source ends and the reader drains all buffered data; "temporarily no bytes available" is not EOF. Reading a socket may throw an I/O error rather than EOF depending on the situation.

For line-delimited data, `readLine()` can block while the sender has not sent a newline even if some characters arrived. If immediate character-by-character feedback is needed, design the protocol/reader for that requirement instead of using `ready()` to guess "a full line has arrived."

## 9. Edge Cases to Remember

**Closed reader:** `ready()` and `read()` may throw `IOException`; closing a stream is not a substitute for checking `-1`. In well-written programs, use try-with-resources to guarantee resource release.

**Buffer still holds data after the underlying source ends:** `BufferedReader` can continue returning buffered characters. Only after buffered characters are exhausted does the next read return `-1`.

**Infinite or unknown-end sources:** a single `read()` can block waiting for data; looping "until EOF" has no built-in deadline. The application needs timeouts, closing logic, stop signals, or proper protocol framing.

**One visible Unicode character is not always one `char`:** `Reader.read()` returns a single UTF-16 unit; a code point outside the BMP can require two reads. The EOF condition remains `-1`, regardless of how surrogate pairs are split.

**`readLine() == null` differs from `readLine().isEmpty()`:** an empty string is a valid line; assign the result to a variable and check `null` before processing.

**Multiple threads reading one reader:** calling `ready()` on thread A and then `read()` on thread B, or having another thread consume data in between, creates time-of-check-to-time-of-use changes. Never use `ready()` as a cross-thread synchronization mechanism.

## 10. Quick Bug-Fix Reference

| Buggy Code / Inference | Why It Is Wrong | Fix |
| --- | --- | --- |
| `if (!reader.ready()) EOF` | False does not prove data is exhausted | Call `read()` and check `-1` |
| `while (reader.ready()) { ... }` | May drop data, or fail to stop at EOF | Use the read result as the loop condition |
| `char c = (char) reader.read()` immediately | May cast `-1` into a `char`, losing the EOF sentinel | Keep as `int`, check `-1` first |
| `while ((line = reader.readLine()) != "")` | Confuses blank lines with EOF | `while ((line = reader.readLine()) != null)` |
| `reader.ready() == true` means a full line is present | Readiness of `read()` does not imply a delimiter is present | `readLine()` may still have to wait |
| `InputStream.available() == 0` means EOF | `available` signals readiness, not EOF | Use `InputStream.read() == -1` |
| `read(char[])` always fills the buffer | A `Reader` is allowed to return fewer chars than requested | Process the exact `count` each iteration |
| `ready()` replaces a socket timeout | Makes no timing guarantee and is not a timeout API | Use deadlines/timeouts on the source or protocol |

## 11. Self-Check Questions

**Q1.** `reader.ready()` returns `false`. Can you conclude the stream reached EOF?  
**Answer:** No. The next read is simply not guaranteed to be non-blocking; more data could arrive later, or the read could return immediately.

**Q2.** `reader.ready()` returns `true`. Does that guarantee the next `read()` returns a character?  
**Answer:** No. It only guarantees not blocking for input; the read can still return `-1` at EOF. `StringReader` is an easy example.

**Q3.** When reading a `Reader` character by character, what is the standard stop condition?  
**Answer:** Read into an `int` variable and stop when `read() == -1`.

**Q4.** `BufferedReader.readLine()` returns `""`. Is that EOF?  
**Answer:** No. That is an empty line; EOF is represented by `null`.

**Q5.** Why can `BufferedReader.ready()` be `true` even when the underlying source is not ready?  
**Answer:** Because `BufferedReader`'s buffer already has characters ready to return immediately.

**Q6.** While reading a socket and missing the final byte, does `ready()` tell you how many bytes remain in total?  
**Answer:** No. You must rely on framing/protocol or true EOF, plus timeouts where needed; `ready()` does not provide payload length.

**Q7.** Does `ready()` returning `true` guarantee `readLine()` will not block?  
**Answer:** No. One character may be ready without a line terminator yet, so `readLine()` may still wait.

## 12. Official Documentation for Contract Verification

- [Java SE 17 — Reader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Reader.html): specification of `ready()`, `read()`, `read(char[], off, len)`.
- [Java SE 17 — BufferedReader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedReader.html): specification of buffering, `ready()`, and `readLine()`.
- [Java SE 17 — StringReader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/StringReader.html): in-memory string reader, useful for observing EOF behavior.

**Core takeaway:** **`ready()` answers whether a read can proceed without waiting for input**, whereas **EOF is signaled by the actual return value of `read()` (`-1`) or `readLine()` (`null`)**. In loops processing an entire stream, always base the stopping condition on the read result, never on `ready()`.