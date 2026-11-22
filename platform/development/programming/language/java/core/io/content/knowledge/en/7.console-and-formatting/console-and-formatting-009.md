# checkError() and I/O Errors Not Thrown Directly in Java

In Java I/O, most write streams report failures by throwing `IOException`. However, the two classes specialized for printing and formatting output—**`java.io.PrintStream`** and **`java.io.PrintWriter`**—report errors differently: ordinary write operations **do not throw `IOException` directly** to the caller, and instead record errors in an internal state. The **`checkError()`** method allows checking that state.

This is especially important when logging, exporting reports, generating formatted text, or printing to the console. Having `print()`, `println()`, or `printf()` finish without throwing an `IOException` **does not mean the data was written successfully**.

This lesson is part of the **Console and Formatting** topic in Java Core I/O; its focus is how to recognize, explain, and handle errors for APIs that "store errors in a status flag".

## 1. Learning Objectives

After this lesson, you can:

- Distinguish how `PrintStream` and `PrintWriter` report errors compared to ordinary `OutputStream` and `Writer`.
- State the `checkError()` contract accurately, including that checking can **flush** the output.
- Understand why `print()`, `println()`, and `printf()` running without throwing `IOException` can still lose data.
- Use `checkError()` at the appropriate points and recognize that this boolean **does not reveal the detailed cause**.
- Distinguish `autoFlush` on `PrintStream` from `PrintWriter`, and identify **non-I/O** exceptions that can still be thrown.
- Write deterministic Java 17+ programs that reproduce write errors without relying on physical disks, networks, or terminals.
- Choose lower-level APIs declaring `throws IOException` when business logic requires managing errors and specific causes.

## 2. Why Do the Two Formatting Print Classes Handle Errors Specially?

### `PrintStream`

`java.io.PrintStream` extends `FilterOutputStream` and is used to print textual representations of many value types:

~~~java
stream.print("name=");
stream.println("Java");
stream.printf("count=%d%n", 3);
~~~

`System.out` and `System.err` are normally two `PrintStream` instances provided by the JVM. `PrintStream` also provides byte-writing operations, though `print`/`println`/`printf` focus on writing encoded characters down to a byte output.

Per the Java 17 `PrintStream` contract, **write operations do not propagate normal `IOException` to the caller**; when the underlying stream reports an I/O error, the print class records the error in a flag for `checkError()` to inspect. A notable exception is `InterruptedIOException` from the underlying stream: `PrintStream` handles it by setting the thread's interrupt status instead of simply recording it as a normal I/O error.

### `PrintWriter`

`java.io.PrintWriter` extends `Writer`, providing text-printing operations similar to `PrintStream`:

~~~java
writer.print("name=");
writer.println("Java");
writer.printf("count=%d%n", 3);
~~~

`PrintWriter` works with **characters**; it has no raw byte-writing methods like `OutputStream`. `PrintWriter` methods do not propagate `IOException` from write/flush/close outward the way an ordinary `Writer` can; to detect error conditions you must check `checkError()`.

**Important distinction:** constructing a `PrintStream`/`PrintWriter` with a file-opening constructor can still **throw `IOException`** (or a specific checked exception) when the file cannot be opened/created. "Does not throw IOException" here refers mainly to error reporting **once you have a print object and perform I/O operations**, not immunity to all errors at every stage.

## 3. Comparison Table of Writing APIs

| Type | Unit of Work | I/O Errors on Write/Flush/Close | How Callers Detect |
| --- | --- | --- | --- |
| `OutputStream`, e.g. `FileOutputStream` | Bytes | Methods typically declare `throws IOException` | Catch/propagate exception |
| `Writer`, e.g. `BufferedWriter` | Characters | Methods typically declare `throws IOException` | Catch/propagate exception |
| `PrintStream` | Formatted printing, writing bytes | Does not propagate normal I/O `IOException` from print/write calls | `checkError()`; watch out for interrupt status separately |
| `PrintWriter` | Formatted printing, writing characters | Does not propagate normal I/O `IOException` from print/write calls | `checkError()` |
| `Formatter` | Pattern-based formatting | I/O errors with `Appendable` can be recorded instead of thrown directly | `ioException()` |

Not everything named "print" shares the same contract. When choosing an error-handling strategy, look at the **exact API type** and the caller's responsibilities.

## 4. How Does `checkError()` Work?

Both classes have:

~~~java
boolean failed = output.checkError();
~~~

On `PrintStream`, `checkError()` **flushes the output if still open**, then checks the error state. On `PrintWriter`, `checkError()` likewise **flushes if the writer is not closed** and then checks the error state. Thus this call is **not merely reading a boolean field**; it can trigger a deferred I/O operation.

| Result | What Can Be Concluded | What Must Not Be Concluded |
| --- | --- | --- |
| `true` | The print class recorded an error condition per its mechanism | You do not know the exact root cause, how many bytes/characters reached the target, or whether continuing is safe |
| `false` | At check time no error had been recorded in the state observable by the API | Does not prove data is durably on disk, reached a peer, or will not fail later |

**Common scenario:** `print("abc")` only places data in a buffer; `checkError()` can trigger a flush, and the flush itself causes the lower layer to throw `IOException`. Then `checkError()` returns `true`. If never checked, the program might assume the print operation succeeded.

### The Error Flag Usually "Sticks" Once Set

Both classes provide `protected setError()` and `protected clearError()`. Once the flag becomes `true`, subsequent `checkError()` calls continue returning `true` until cleared by appropriate internal/subclass mechanisms, even if a later operation encounters no new error.

**There is no public API to reliably retrieve or reset all errors** on an ordinary `PrintStream`/`PrintWriter` object. `clearError()` is `protected`, not advice for callers to "ignore errors and continue". If an output target is broken, you typically must investigate, replace the resource, or report failure at the business layer.

In particular, `checkError()` does not return the underlying `IOException`, stack trace, or failing file path. If you need to preserve the root cause, use an appropriate `Writer`/`OutputStream` or build a custom monitoring wrapper when designing your API.

## 5. Runnable Java 17+ Example: `PrintStream` Swallows I/O Write Errors

We can build a mock `OutputStream`: every write throws `IOException`. Using it as a `PrintStream` destination yields deterministic results without corrupting real files.

Create **`PrintStreamErrorDemo.java`**:

~~~java
import java.io.IOException;
import java.io.OutputStream;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;

public class PrintStreamErrorDemo {
    static final class BrokenOutputStream extends OutputStream {
        @Override
        public void write(int value) throws IOException {
            throw new IOException("simulated disk failure");
        }
    }

    public static void main(String[] args) {
        try (PrintStream out = new PrintStream(
                new BrokenOutputStream(), true, StandardCharsets.UTF_8)) {

            out.println("record-1");

            System.out.println("afterPrintln=continued");
            System.out.println("checkError=" + out.checkError());
        }
    }
}
~~~

Compile/run:

~~~bash
javac PrintStreamErrorDemo.java
java PrintStreamErrorDemo
~~~

**Exact stdout:**

~~~text
afterPrintln=continued
checkError=true
~~~

Why?

1. `BrokenOutputStream.write(int)` throws `IOException` on every actual write operation.
2. `PrintStream.println` attempts to write to the underlying stream; upon encountering a normal I/O error, `PrintStream` records the error instead of propagating a checked exception up to `main`.
3. The line `afterPrintln=continued` proves **control flow kept going**.
4. `checkError()` returns `true` because the error flag was set.
5. `try-with-resources` still closes the print resource, yet `PrintStream.close()` itself also does not propagate normal I/O `IOException` outward.

This example demonstrates that **writing data can fail while the program keeps running**. It does not prove writing to the console or files always fails; mocking a broken sink makes the failure reproducible.

## 6. Runnable Java 17+ Example: `PrintWriter` Also Needs `checkError()`

`PrintWriter` wraps an underlying `Writer`. A writer may throw `IOException` when asked to write, yet `PrintWriter` does not propagate that error like an ordinary `BufferedWriter`.

Create **`PrintWriterErrorDemo.java`**:

~~~java
import java.io.IOException;
import java.io.PrintWriter;
import java.io.Writer;

public class PrintWriterErrorDemo {
    static final class BrokenWriter extends Writer {
        @Override
        public void write(char[] chars, int offset, int length)
                throws IOException {
            throw new IOException("simulated writer failure");
        }

        @Override
        public void flush() {
            // No underlying buffer.
        }

        @Override
        public void close() {
            // No real resource to close.
        }
    }

    public static void main(String[] args) {
        try (PrintWriter out = new PrintWriter(new BrokenWriter(), true)) {
            out.println("record-2");

            System.out.println("afterPrintln=continued");
            System.out.println("checkError=" + out.checkError());
        }
    }
}
~~~

Compile/run:

~~~bash
javac PrintWriterErrorDemo.java
java PrintWriterErrorDemo
~~~

**Exact stdout:**

~~~text
afterPrintln=continued
checkError=true
~~~

`BrokenWriter` intentionally fails on writing a character array. `PrintWriter` catches the error from the underlying writer and sets its internal error flag. `println()` returns as if normal; only `checkError()` reveals that a problem occurred.

**Easy mistake:** if you call `BrokenWriter.write(...)` directly, the caller must handle `IOException`. When calling through `PrintWriter`, the I/O error gets turned into a flag instead of being thrown.

## 7. Comparison with `BufferedWriter` When You Need the Root Error

In tasks needing strict failure handling—such as writing mandatory complete reports, writing config files, or exporting data where write failures must fail the business operation—`BufferedWriter` or `OutputStream` can be a better fit because they do not hide the I/O cause.

~~~java
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.Writer;

public final class StrictWrite {
    private StrictWrite() {}

    public static void writeRequiredRecord(
            Writer destination, String record) throws IOException {
        BufferedWriter buffered = new BufferedWriter(destination);
        buffered.write(record);
        buffered.newLine();
        buffered.flush();
    }
}
~~~

This class compiles, with no `main`. It does not close `destination` because ownership stays with the caller; however, you must ensure the method finishes `flush()` and the caller handles closing policy. `BufferedWriter` throws or propagates `IOException` if the lower layer fails, giving the caller a concrete cause to handle/log and fail cleanly.

In practice, if you are the one **opening the file**, wrap opening the writer in `try-with-resources`:

~~~java
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class ReportWriter {
    private ReportWriter() {}

    public static void save(Path target, String report) throws IOException {
        try (BufferedWriter writer =
                     Files.newBufferedWriter(target, StandardCharsets.UTF_8)) {
            writer.write(report);
            writer.newLine();
        }
    }
}
~~~

This is a class without `main`. `Files.newBufferedWriter` can create a new file or truncate the target file by default; the caller must pick a safe path/update strategy. If writing or closing hits an I/O error, the operation throws `IOException` outward rather than only setting a flag. For atomic-write requirements, design a temporary file and replace the target file after verification.

**Note:** `flush()` or `close()` completing without error still does not guarantee data is durably synced to storage. `checkError() == false` is an even weaker signal; it reflects only the error state known to the print class.

## 8. `autoFlush` and Why the Two Classes Differ

Both `PrintStream` and `PrintWriter` have constructors taking an `autoFlush` flag, though the events that trigger flushing differ.

### `PrintStream` with `autoFlush=true`

Per the Java 17 documentation, automatic flushing can occur when:

- Writing a **byte array**.
- Calling a `println(...)` method.
- Writing a newline character or byte `'\n'`.

`PrintStream` operates on bytes below an encoding layer, so this auto-flush contract **differs** from `PrintWriter`'s behavior.

### `PrintWriter` with `autoFlush=true`

Automatic flushing occurs when calling:

- `println(...)`
- `printf(...)`
- `format(...)`

**There is no autoFlush guarantee merely because you write `'\n'` with `write('\n')`** or call `print(...)` without a newline. Even when `autoFlush=false`, `checkError()` can still flush if the writer remains open.

| Action | `PrintStream(autoFlush=true)` | `PrintWriter(autoFlush=true)` |
| --- | --- | --- |
| `println("x")` | Auto-flushes | Auto-flushes |
| `write('\n')` | Auto-flushes per `PrintStream` contract | No autoFlush from this event alone |
| `print("x")` without newline | Do not assume it always flushes | Do not assume it always flushes |
| `checkError()` while not closed | Flushes to check error | Flushes to check error |

### Standalone Demo: Difference at `write('\n')`

Create file **`AutoFlushDifferenceDemo.java`**:

~~~java
import java.io.IOException;
import java.io.OutputStream;
import java.io.PrintStream;
import java.io.PrintWriter;
import java.io.StringWriter;
import java.nio.charset.StandardCharsets;

public class AutoFlushDifferenceDemo {
    static final class CountingOutputStream extends OutputStream {
        int flushes;

        @Override
        public void write(int value) {
            // Intentionally discard data just to count flushes.
        }

        @Override
        public void flush() {
            flushes++;
        }
    }

    static final class CountingWriter extends StringWriter {
        int flushes;

        @Override
        public void flush() {
            flushes++;
        }
    }

    public static void main(String[] args) throws IOException {
        CountingOutputStream byteTarget = new CountingOutputStream();
        try (PrintStream out = new PrintStream(
                byteTarget, true, StandardCharsets.UTF_8)) {
            out.write('\n');
            System.out.println("streamFlushed=" + (byteTarget.flushes > 0));
        }

        CountingWriter charTarget = new CountingWriter();
        try (PrintWriter out = new PrintWriter(charTarget, true)) {
            out.write('\n');
            System.out.println("writerFlushedAfterWrite="
                    + (charTarget.flushes > 0));

            out.println("done");
            System.out.println("writerFlushedAfterPrintln="
                    + (charTarget.flushes > 0));
        }
    }
}
~~~

Run on Java 17+:

~~~bash
javac AutoFlushDifferenceDemo.java
java AutoFlushDifferenceDemo
~~~

Stdout:

~~~text
streamFlushed=true
writerFlushedAfterWrite=false
writerFlushedAfterPrintln=true
~~~

Counters are read **before closing the streams**, so results are unaffected by `close()`. Do not assert an exact flush count for `PrintStream`, since a single call may flush more than once depending on implementation; the example checks only whether at least one flush occurred.

**Performance:** `autoFlush=true` pushes data to lower layers more frequently—useful for interactive responsiveness, yet costly when writing many small items. `autoFlush=false` usually fits batching writes until the end of a chunk and flushing explicitly. Either way, when correctness matters, check the write result instead of relying solely on the method returning.

## 9. Error-Handling Pattern at Task Boundaries

Suppose you must use `PrintWriter` because you rely on formatted printing methods. A minimal strategy is:

~~~java
import java.io.IOException;
import java.io.PrintWriter;
import java.io.Writer;

public final class CheckedPrintTask {
    private CheckedPrintTask() {}

    public static void writeRecord(
            Writer sink, String name, int quantity) throws IOException {
        PrintWriter printer = new PrintWriter(sink, false);

        printer.printf("item=%s, quantity=%d%n", name, quantity);

        if (printer.checkError()) {
            throw new IOException("Formatted output failed");
        }
    }
}
~~~

This class compiles; the caller provides `Writer` and manages when to close it. `checkError()` requests a flush before returning status, so lower-layer errors at flush time have a chance to surface.

However, this pattern has limitations:

1. **Does not preserve the original `IOException`:** you only have a boolean to build a generic descriptive exception.
2. **Does not distinguish partial writes:** part of the data may already have been written before failing.
3. **Does not replace checking errors when closing the real sink:** if the caller closes `sink` later and an error occurs then, you need `sink`'s error reporting and clear resource ownership.
4. **No certainty the error occurred on the exact record just written:** an error flag from an earlier operation might still be set.
5. If `sink` itself is another `PrintWriter`, stacked wrapper layers can hide original details further; avoid unnecessary nesting of print classes.

When you control both the API and resource lifecycle, it is usually **better to use `Writer`/`BufferedWriter` directly** with `throws IOException` rather than routing through `PrintWriter` and synthesizing a cause-less exception.

### Reading Status After `close()`

If the final close/flush operation **can produce a new error**, checking `checkError()` **after closing** is valuable to catch errors recorded by `PrintWriter.close()`. Example:

~~~java
import java.io.IOException;
import java.io.PrintWriter;
import java.io.Writer;

public final class CloseErrorCheck {
    private CloseErrorCheck() {}

    public static void writeAndCheck(Writer sink, String text)
            throws IOException {
        PrintWriter out = new PrintWriter(sink);
        try {
            out.print(text);
        } finally {
            out.close();
        }
        if (out.checkError()) {
            throw new IOException("Output or close failed");
        }
    }
}
~~~

This class has no `main` and **intentionally transfers responsibility for closing `sink` to the helper**; use it only when the method's contract permits closing the caller-supplied sink. Calling `checkError()` on a `PrintWriter` after closing does not flush the already-closed writer, yet still reflects errors recorded by the class.

If a runtime exception occurs inside the `try` block, Java continues propagating that exception after `finally` and never reaches the `if`; thus the example primarily inspects normal I/O and resource-closing states. When you need to preserve all root causes and close errors, work with the underlying `Writer` and `try-with-resources` so Java records suppressed exceptions too.

## 10. Exceptions That Can Still Be Thrown Normally

Do not interpret "`PrintStream`/`PrintWriter` do not throw `IOException` when writing" as "no `print` call ever throws an exception". Errors outside the internal I/O error-flag mechanism can still arise:

- `IllegalFormatException` (and its subclasses) when a format string is malformed or argument types mismatch in `printf`/`format`.
- `NullPointerException` for parameters that must not be `null`, depending on the overload/API.
- `IndexOutOfBoundsException` for invalid array/string slice indices.
- `RuntimeException` thrown by user code running inside `Object.toString()` or `Formattable.formatTo(...)`.
- Errors when **opening a file** in a constructor can throw `IOException` or specific checked exceptions; security/permission errors may have their own representation.
- JVM-level `Error`s are not turned into booleans by this mechanism.

Bad format example:

~~~java
System.out.printf("%d%n", "not a number");
~~~

This snippet throws `IllegalFormatConversionException` (a subclass of `IllegalFormatException`); `checkError()` is **not** the mechanism for detecting such formatting errors. It is not an `IOException` from an I/O device.

### The `InterruptedIOException` Case in `PrintStream`

The Java 17 `PrintStream` documentation distinguishes `InterruptedIOException` from other `IOException`s: when the underlying stream throws this exception, the class may **set the thread's interrupt flag** to signal interruption rather than setting the normal error flag. Therefore, **`checkError() == false` is not proof that every abnormal condition has been ruled out**. When an application uses cancellation/thread interruption, handle the interrupt flag according to your design.

Do not casually clear the interrupt state with `Thread.interrupted()` just to make an example look "clean", because that method **both reads and clears** the interrupt flag. If you need to inspect without clearing, use `Thread.currentThread().isInterrupted()`.

## 11. What to Watch Out For with `System.out` / `System.err`?

`System.out.println(...)` and `System.err.println(...)` are often used assuming "printing means succeeding". On an interactive console, failures are uncommon, yet you can still encounter a **closed target**, a pipe closed early by the consumer, redirected output environments, log file failures, or special I/O destinations.

~~~java
System.out.println("export complete");
if (System.out.checkError()) {
    // Detected PrintStream error state.
    // Decide handling at the business layer or via another error channel.
}
~~~

If `System.out` has already failed, trying to report that error via `System.out` itself will likely fail as well. Depending on the application, use another observation channel, return an exit status, throw an application-level exception, or write to a dedicated logging system.

**Never arbitrarily `close()` `System.out` or `System.err`** in a library or a program that still needs to print. These are process-wide shared resources. `System.console()` can return `null` when running in IDEs, CI, or environments without an interactive console; do not assume a console always exists.

`checkError()` on `System.out` can also flush. It **does not confirm** that a user saw the text on the terminal, that a redirected file was fsynced, or that a monitoring system ingested the log.

## 12. `Formatter.ioException()`: A Similar Mechanism on a Different API

`java.util.Formatter` accepts an `Appendable` target and provides `format(...)`. When an `IOException` occurs while writing through the target, `Formatter` can record the exception rather than throwing it from `format`; inspect it via **`formatter.ioException()`**.

~~~java
import java.io.IOException;
import java.io.Writer;
import java.util.Formatter;
import java.util.Locale;

public class FormatterErrorDemo {
    static final class FailingWriter extends Writer {
        @Override
        public void write(char[] chars, int offset, int length)
                throws IOException {
            throw new IOException("formatter output failed");
        }

        @Override
        public void flush() { }

        @Override
        public void close() { }
    }

    public static void main(String[] args) {
        try (Formatter formatter =
                     new Formatter(new FailingWriter(), Locale.ROOT)) {
            formatter.format("item=%d", 42);

            IOException cause = formatter.ioException();
            System.out.println("formatterError=" + (cause != null));
            System.out.println("message="
                    + (cause == null ? "none" : cause.getMessage()));
        }
    }
}
~~~

Compile/run:

~~~bash
javac FormatterErrorDemo.java
java FormatterErrorDemo
~~~

**Expected stdout:**

~~~text
formatterError=true
message=formatter output failed
~~~

Difference from `PrintWriter.checkError()`: `Formatter.ioException()` returns the **recorded `IOException`**, rather than just a boolean. However, `Formatter` and `PrintWriter` are not the same class; do not call `checkError()` on `Formatter` or `ioException()` on `PrintStream`.

Formatting syntax errors like `IllegalFormatException` still follow their own contract and throw directly. When wrapping other objects in `Formatter`, clarify who owns the destination and whether `Formatter.close()` closes the destination if it implements `Closeable`.

## 13. Errors During Flush/Close: The Commonly Missed Moment

Some systems buffer across multiple layers:

~~~text
print / println / printf
          |
          v
PrintWriter / PrintStream [error state]
          |
          v
BufferedWriter / encoder / OutputStream
          |
          v
File / pipe / socket / device
~~~

A print statement may only place data into a buffer. Errors emerge only when:

- Enough data accumulates that the buffer must push downward.
- `autoFlush` triggers a flush.
- `checkError()` invokes flush.
- `flush()` or `close()` is called directly.
- The lower layer attempts to transfer data and discovers the target is no longer usable.

Thus there may be **no error recorded when `print()` returns**, yet after a flush/checkError it becomes `true`. When multiple buffering layers exist, identify where the task's **completion boundary** lies.

If a workflow requires verifying that data is durably persisted or received by another system, use stronger mechanisms (e.g., receiver acknowledgment, transactions, checksum/ack, `FileChannel.force` when file sync is required). `checkError()` itself only inspects the error state observed by the print API.

## 14. API Selection Guide

### Just Printing for Users or Debugging

`System.out.print/println/printf` fits well. When a CLI tool requires strictly accurate output, consider checking `System.out.checkError()` upon completion and reflecting errors via exit code or another channel.

### Needing Formatted Printing to an Existing `Writer`

`PrintWriter` is convenient for `printf/println`. If write errors matter to business logic, **check `checkError()` after write/flush batches**, while recognizing that losing the root cause makes error reporting less detailed.

### Needing Accuracy and Retry/Audit Capability

Prefer `Writer`/`BufferedWriter` or `OutputStream`/`BufferedOutputStream` with `throws IOException`. When errors occur, preserve the root cause and explicitly decide policies for partial writes, retries, temp files, timeouts, and closing resources.

### Needing Formatting to an Arbitrary `Appendable`

`Formatter` can fit; check `ioException()` for destination I/O errors while still handling format/runtime errors separately.

### Multiple Wrapper Layers

Avoid stacking unnecessary `PrintWriter`/`PrintStream` wrappers and assuming the outer layer faithfully reflects every failure. The contract can convert errors into internal state at the very first layer; using an explicit error-throwing API at business boundaries is much easier to manage.

## 15. Common Misconceptions

**1. "No exception means the write succeeded."**  
False for `PrintStream`/`PrintWriter`: normal I/O errors may just set a flag. Use `checkError()` if write success must be verified.

**2. "`checkError()` only reads a flag and performs no I/O."**  
False: while still open, the method can invoke flush, and flushing can trigger new errors or I/O latency.

**3. "`checkError() == false` means bytes reached the final target durably."**  
False: it does not guarantee fsync, socket receipt, or success of external storage steps. The flag reflects errors seen by the print class, not a delivery receipt.

**4. "If printing fails, `checkError()` will tell you which exact IOException occurred."**  
False: the return value is just a boolean. Use an API that throws errors directly or a dedicated monitoring wrapper if you need the cause.

**5. "`PrintStream` and `PrintWriter` autoFlush work identically."**  
False: `PrintWriter` triggers autoFlush on `println/printf/format`; `PrintStream` additionally triggers on byte-array writes and newlines.

**6. "All exceptions are caught by print classes."**  
False: `IllegalFormatException` formatting errors, index errors, and runtime exceptions can still propagate. `InterruptedIOException` in `PrintStream` also has special handling.

**7. "Calling `close()` guarantees all errors are reported via exceptions."**  
False for `PrintStream`/`PrintWriter`: I/O errors during flush/close can also be recorded in internal state instead of thrown. For critical tasks, establish end-of-life error checks and clear ownership.

**8. "A `true` error flag means the most recent write failed completely."**  
False: state can accumulate from an earlier error, and a write operation may have succeeded partially before failing. Never use the error flag as a byte counter or detailed error classifier.

## 16. Production Code Review Checklist

- [ ] Do you know whether the output variable is `PrintStream`, `PrintWriter`, `Formatter`, or `Writer/OutputStream`?
- [ ] If using a print class, is `checkError()` called at points where business logic must know I/O status?
- [ ] If using `Formatter`, is `ioException()` checked when output correctness requires zero errors?
- [ ] Are flagged I/O errors distinguished from runtime/format exceptions that can throw directly?
- [ ] Is it understood that `checkError()` can flush while the object remains open?
- [ ] Are you avoiding treating `false` as a guarantee of durable commit, network ACK, or successful delivery?
- [ ] If using `autoFlush`, are the differences between `PrintStream` and `PrintWriter` accurately accounted for?
- [ ] Is resource closing ownership clear: who owns the `Writer`/`OutputStream`, who closes it, and who checks final errors?
- [ ] When `IOException` causes and strict retry policies are needed, did you consider direct APIs declaring `throws IOException`?
- [ ] Are libraries avoiding closing `System.out`/`System.err` that they do not own?
- [ ] Do tests simulate write errors with mock `OutputStream`/`Writer` implementations rather than relying on flaky disk/random failures?

### Self-Check Questions

**Question 1.** `PrintWriter.println("A")` completes with no exception. Is writing guaranteed to have succeeded?  
**Answer:** No. Check `checkError()` at sensible boundaries and understand the limits of this signal.

**Question 2.** Can `checkError()` perform an I/O operation itself?  
**Answer:** Yes. If the stream is still open, it flushes before checking the error state.

**Question 3.** Does `PrintWriter(autoFlush=true).write('\n')` always auto-flush?  
**Answer:** No. `PrintWriter`'s autoFlush is tied to `println/printf/format`, unlike `PrintStream`.

**Question 4.** If you want to preserve the exact `IOException` cause when writing a config file, what should you use?  
**Answer:** Use `Writer`/`BufferedWriter` or `OutputStream` with `throws IOException` and `try-with-resources`; these APIs propagate the original error cause up to the caller.

**Question 5.** Does `System.out.checkError() == false` prove logs were read by the monitoring system?  
**Answer:** No. It is not an acknowledgment from the log-receiving system.

**Question 6.** If `printf("%d", "text")` is called and Java throws `IllegalFormatConversionException`, is `checkError` the handling mechanism?  
**Answer:** No. That is a runtime formatting error handled per the formatting contract, distinct from I/O errors held in the status flag.

**Takeaway:** `PrintStream` and `PrintWriter` prioritize convenience for printing/formatting text and therefore **can turn I/O errors into internal state**. `checkError()` helps detect errors known to the print class, yet **carries no detailed cause and does not guarantee data reached the final destination**. When correctness demands precise error handling, choose abstractions that let `IOException` reach the caller and manage the full resource lifecycle.

## Official API References (Java 17)

- [PrintStream — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/PrintStream.html)
- [PrintWriter — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/PrintWriter.html)
- [Formatter — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Formatter.html)
