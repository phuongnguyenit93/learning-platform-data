# Verifying Resources Are Closed on Failure in Java I/O

## 1. Why Can a Program With Correct Output Still Leak Resources?

Java I/O programs commonly open **file streams, readers/writers, channels, sockets, ZIP archives, directory streams**, or resources holding OS file descriptors/handles. If an exception occurs mid-operation and a resource is not released, the consequences can include:

- File descriptors/socket handles are never returned; the system fails with errors like "Too many open files".
- Files remain locked open, preventing renaming or deletion on some operating systems.
- Output buffers are not flushed/finalized; ZIP/GZIP data lacks trailers or metadata.
- Network connections stay open, tying up client and server resources.
- Directory streams or file-reading streams keep holding handles even after business logic stops using them.
- In high-throughput systems, rare errors accumulate into severe leaks.

**Verifying resources are closed on failure** means writing tests that force the program down error branches and then observing **who is responsible for closing, how many times `close` is called, in what order, and which exception is preserved**.

This is not merely "adding `finally`". Modern Java favors **`try-with-resources`** for `AutoCloseable` objects, yet we still must test ownership contracts and handle subtle edge cases.

Lesson objectives:

1. Understand `try-with-resources` semantics on normal exit, exceptions, `return`, `break`, and acquisition failures.
2. Verify resources are closed even when `read`/`write` throws `IOException`.
3. Understand primary exceptions and **suppressed exceptions** raised by `close()`.
4. Build test doubles/fault injection to measure close calls and order without relying on random I/O errors.
5. Recognize the limits of test doubles: calling `close()` does not by itself prove an OS handle was genuinely released.
6. Apply these techniques to stream wrappers, `FileChannel`, `ZipFile`, `DirectoryStream`, and `Files.lines()`/`walk()`/`list()`.

## 2. Distinguishing `close`, `flush`, and Actual Release

Three concepts are often conflated:

| Concept | Core Contract | How to Observe/Test |
|---|---|---|
| `flush()` | Pushes buffered data to the next layer per the stream/writer contract | Fake output records `flush`; verify data reached the underlying stream |
| `close()` | Ends the resource's lifecycle; depending on the API, may flush/finalize before releasing | Spy/tracker records `close`; integration test checks resource state |
| Durability | Bytes are guaranteed stably stored per application contract | Use appropriate APIs like `FileChannel.force(...)`, filesystem policy, and dedicated tests |

`OutputStream.close()`/`Writer.close()` typically finishes processing that layer's buffer before closing the underlying stream. However, **closing does not mean all data is guaranteed durable on the device**, nor does it mean a network peer confirmed processing.

For close testing, define the exact invariant:

> If a method **owns** a successfully opened resource, then on every exit path of that method — including when an error occurs — that resource must be requested to close per contract.

"Requested to close" is the unit-test level with a spy. "Handle no longer held open" may require an OS/API-specific integration test. "Data stored durably" is yet another requirement.

## 3. \`AutoCloseable\`, \`Closeable\`, and Resource Ownership

`AutoCloseable` declares:

~~~java
public interface AutoCloseable {
    void close() throws Exception;
}
~~~

`java.io.Closeable` extends `AutoCloseable`, declares `close() throws IOException`, and by `Closeable`'s contract, calling `close` on an already closed object has no further effect. By contrast, **plain `AutoCloseable` does not require `close` to be idempotent**; its Javadoc encourages implementers to make it so if possible.

Common resources:

| API | Resource | Who Should Close? |
|---|---|---|
| `FileInputStream`, `FileOutputStream` | File stream | Code that creates/borrows it per ownership contract |
| `BufferedInputStream`, `BufferedReader` | Wrapper and underlying source | Typically close the outer wrapper, which closes the underlying source |
| `InputStreamReader`, `OutputStreamWriter` | Byte ↔ char bridge and underlying stream | Typically the owner of the outer bridge |
| `FileChannel`, `SocketChannel`, `ServerSocketChannel` | File/socket channel | The component owning the channel |
| `ZipFile`, `ZipInputStream` | ZIP container/stream | The component opening the ZIP |
| `DirectoryStream<Path>` | Directory handle | The component calling `Files.newDirectoryStream` |
| `Stream<String>` from `Files.lines` | Open file stream | Code calling `Files.lines` |
| `Stream<Path>` from `Files.list`/`Files.walk` | Directory handles | Code creating the file-backed stream |

**Ownership must be explicit.** If a method accepts an `InputStream` passed by a caller, there are two valid but non-equivalent designs:

- **Callee owns:** the method takes responsibility for closing the stream even on error; this must be stated in the API contract.
- **Caller owns:** the method only reads/writes and does not close the stream; the caller closes it in an outer scope.

There is no universal rule of "whenever you see an `InputStream`, close it". For instance, many APIs should never close `System.in` or a shared stream.

## 4. \`try-with-resources\`: The Foundation for Exception-Safe Cleanup

Java 17 syntax:

~~~java
try (InputStream in = Files.newInputStream(source);
     OutputStream out = Files.newOutputStream(target)) {
    in.transferTo(out);
}
~~~

This is illustrative code requiring `java.io.*`, `java.nio.file.*`, and defined `Path source, target`. For any resource successfully initialized in the header, Java automatically calls `close()` upon exiting the `try`, whether:

- The block completes normally to the end.
- A `return` executes inside the block.
- A `break`/`continue` exits the scope.
- The block throws an `IOException`, `RuntimeException`, or `Error`.
- Trailing `catch`/`finally` blocks handle the outcome.

### 4.1. Creation and Closing Order

Resources in the header are **initialized left-to-right** and **closed right-to-left**.

~~~java
try (Tracked first = open("first");
     Tracked second = open("second")) {
    runBusinessLogic();
}
~~~

This is model code with custom `Tracked` and factory methods. Execution flow:

~~~text
open first
open second
body
close second
close first
~~~

If `runBusinessLogic()` fails, both `close` calls still run in reverse order. If `close second` also throws an error, Java **still attempts to close `first`**.

### 4.2. What If the Second Resource Fails to Open?

Suppose opening `first` succeeds, but the initializer expression for `second` throws an exception:

~~~text
open first   -> succeeds
open second  -> throws IOException
close first  -> runs automatically
body         -> DOES NOT run
~~~

This is a mandatory test branch. `try-with-resources` guarantees that resources **already fully initialized earlier** are closed. However, if **a resource's constructor/factory itself allocates a native handle and then throws before returning the object**, the header never receives that resource; the constructor/factory must clean up its own partially opened resource.

### 4.3. Null Resources

A resource expression may evaluate to `null`. Java does not call `close()` on a `null` resource; however, using `null` to imply "no resource" often obscures contracts and needs explicit testing when permitted by an API.

### 4.4. Pre-existing Variables in `try-with-resources`

Since Java 9, a `final` or **effectively final** local variable/field can be placed in the header:

~~~java
InputStream opened = Files.newInputStream(source);
try (opened) {
    consume(opened);
}
~~~

This is illustrative code requiring `consume` to be defined. It fits cases where a step must initialize the resource beforehand while still handing ownership to `try-with-resources`. Never use the resource after the closing scope.

## 5. Exception in Body and Exception in `close`: Which Is Thrown?

This is the most critical point when testing error branches.

Suppose:

1. `read()` throws `IOException("read-failed")`.
2. During cleanup, `close()` also throws `IOException("close-failed")`.

With `try-with-resources`:

- The exception from the processing block (`read-failed`) remains the **primary exception** thrown to the caller.
- The exception from `close` (`close-failed`) is attached to the primary as a **suppressed exception**.
- Callers can inspect them via `Throwable.getSuppressed()`.

~~~java
try (InputStream in = openFailingStream()) {
    consume(in); // may throw IOException("read-failed")
} catch (IOException ex) {
    System.err.println("Primary: " + ex);
    for (Throwable suppressed : ex.getSuppressed()) {
        System.err.println("During close: " + suppressed);
    }
}
~~~

This is an **illustrative code snippet** requiring definitions for `openFailingStream()` and `consume(...)`. Do not confuse `Throwable.getCause()` with `getSuppressed()`:

| API | Represents |
|---|---|
| `getCause()` | The underlying cause of a wrapped/chained exception |
| `getSuppressed()` | Additional exceptions preserved while handling/cleaning up the primary exception |
| `addSuppressed(...)` | Allows code to attach cleanup exceptions manually, though `try-with-resources` does this automatically |

### What if the block finishes normally, and `close` fails?

When there is no body error, the exception from `close` is thrown directly. If **multiple resource closes fail**, the exception from the resource closed first (the rightmost one in the header) becomes primary, and subsequent close failures become suppressed exceptions.

### What if both `open` and `close` fail?

If resource B fails to initialize after A has already opened, the exception from initializing B is kept as primary; the error from closing A is attached as suppressed. This preserves information about the **original reason the workflow failed**, instead of letting cleanup mask the root cause.

### Why is hand-written `finally` error-prone?

An easy way to lose the original error:

~~~java
InputStream in = open();
try {
    doWork(in);         // throws IOException A
} finally {
    in.close();         // throws IOException B
}
~~~

This is an anti-pattern when lacking suppressed-exception handling: the caller may receive only B, while A is swallowed. `try-with-resources` enforces language-spec exception precedence; use it rather than reimplementing this logic from scratch.

## 6. Testing Strategy: Actively Inject Faults at Every Step

To verify `close` works under failure, do not wait for the filesystem or network to glitch by chance. Build **test doubles** or fault-injection fixtures simulating failures at every point.

A minimum test matrix:

| Scenario | What to Verify |
|---|---|
| Successful execution | Opened resource is closed under exactly one ownership pass |
| `read` throws | `close` is called; caller receives the read error |
| `write` throws | `close` is called; caller receives the write error |
| Early `return` | `close` runs before the return completes |
| `break`/`continue` leaving scope | `close` runs upon exiting scope |
| Opening second resource fails | First resource is still closed |
| Two resources active together | Closed in reverse order of opening |
| `close` itself throws | Error propagates properly; remaining resources are still attempted |
| Body + `close` both fail | Body error is primary; close error is in `suppressed` |
| Wrapper fails while reading | Closing wrapper closes underlying source per ownership |
| Resource closed twice | Do not rely on luck; define contract and verify call count |
| Async I/O cancel/timeout | Verify cancellation policy and release once all ops settle |

Distinguish three levels of testing:

1. **Unit-level contract tests:** fake/spy resources verify `close()` is called and exceptions are preserved.
2. **Integration tests:** open real files/sockets/ZIPs, run fault scenarios, and check closure via API/OS.
3. **Diagnostic/soak tests:** repeat failure paths many times to monitor file descriptors, memory, and thread/socket counts over time.

Do not rely on an OS-specific "open file cannot be deleted" error as **sole proof**. Linux generally allows unlinking an open file name while handles remain open; Windows has different sharing/locking rules. Portable tests should use spies and verify state via appropriate APIs.

## 7. Complete Java 17+ Program Testing Four Failure Branches

The example below is self-contained with all fixtures, requiring neither JUnit nor real disk files. It simulates:

- Simultaneous body failure and `close` failure.
- Two resources closed in **reverse** opening order.
- Failure while acquiring the second resource.
- `BufferedInputStream` throwing during read and still closing the underlying stream.
- Early `return` from a method where the resource is still closed.

**Filename: `CloseOnFailureDemo.java`**

~~~java
import java.io.BufferedInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.List;

public class CloseOnFailureDemo {

    static final class Tracked implements AutoCloseable {
        final String name;
        final List<String> events;
        final boolean failClose;
        boolean closed;

        Tracked(String name, List<String> events, boolean failClose) {
            this.name = name;
            this.events = events;
            this.failClose = failClose;
            events.add("open:" + name);
        }

        @Override
        public void close() throws IOException {
            events.add("close:" + name);
            closed = true;

            if (failClose) {
                throw new IOException("close-" + name);
            }
        }
    }

    static Tracked failAcquire(List<String> events)
            throws IOException {
        events.add("acquire:failed");
        throw new IOException("acquire-failed");
    }

    static final class FailingInput extends InputStream {
        int closeCalls;

        @Override
        public int read() throws IOException {
            throw new IOException("read-failed");
        }

        @Override
        public void close() {
            closeCalls++;
        }
    }

    static String earlyReturn(List<String> events)
            throws IOException {
        try (Tracked r = new Tracked(
                "early", events, false)) {
            return "done";
        }
    }

    public static void main(String[] args) throws Exception {
        List<String> events = new ArrayList<>();

        try (Tracked first =
                     new Tracked("first", events, false);
             Tracked second =
                     new Tracked("second", events, true)) {

            events.add("body");
            throw new IOException("work-failed");

        } catch (IOException ex) {
            if (!"work-failed".equals(ex.getMessage())
                    || ex.getSuppressed().length != 1
                    || !"close-second".equals(
                            ex.getSuppressed()[0].getMessage())) {
                throw new AssertionError(
                        "Exception hierarchy incorrect");
            }

            System.out.println("primary=" + ex.getMessage());
            System.out.println("suppressed=" +
                    ex.getSuppressed()[0].getMessage());
        }

        System.out.println("close-order=" + events);

        List<String> acquisitionEvents = new ArrayList<>();
        try (Tracked held =
                     new Tracked("held", acquisitionEvents, false);
             Tracked unused = failAcquire(acquisitionEvents)) {

            throw new AssertionError("Not reached");

        } catch (IOException ex) {
            System.out.println(
                    "acquisition=" + ex.getMessage());
        }

        System.out.println(
                "acquisition-trace=" + acquisitionEvents);

        FailingInput raw = new FailingInput();

        try (BufferedInputStream wrapped =
                     new BufferedInputStream(raw)) {
            wrapped.read();

        } catch (IOException ex) {
            System.out.println(
                    "read-failure=" + ex.getMessage());
        }

        System.out.println(
                "wrapped-close-calls=" + raw.closeCalls);

        List<String> early = new ArrayList<>();
        System.out.println(
                "early-return=" + earlyReturn(early));
        System.out.println(
                "early-return-closed=" +
                        early.contains("close:early"));
    }
}
~~~

Compile and run:

~~~bash
javac CloseOnFailureDemo.java
java CloseOnFailureDemo
~~~

**Verified stdout from JDK run:**

~~~text
primary=work-failed
suppressed=close-second
close-order=[open:first, open:second, body, close:second, close:first]
acquisition=acquire-failed
acquisition-trace=[open:held, acquire:failed, close:held]
read-failure=read-failed
wrapped-close-calls=1
early-return=done
early-return-closed=true
~~~

### Why does each line matter?

**`primary=work-failed`:** the body threw `IOException` first; this is the primary error. Failing `close()` does not overwrite it.

**`suppressed=close-second`:** resource `second` threw `IOException` during `close`; Java preserved the body error and recorded the cleanup error separately.

**`close-order=...`:** resources opened as `first` then `second`, but closed as `second` then `first`. Both closes were attempted even though `second` threw.

**`acquisition=acquire-failed`:** `failAcquire` threw in the header; the body never ran, and the second initialization error is preserved.

**`acquisition-trace=...close:held`:** even though the second resource could not be created, the previously initialized `held` resource was still closed.

**`read-failure=read-failed`:** the fake stream threw from `read`. This is fault injection, without having to trigger a real disk error.

**`wrapped-close-calls=1`:** `try-with-resources` closed `BufferedInputStream`, and the wrapper closed `FailingInput` exactly once. In the example, only the outer wrapper is declared in the resource header so the source isn't closed twice.

**`early-return-closed=true`:** even though `earlyReturn` returns a string, `Tracked.close` is still invoked before the return completes.

### Limits of test doubles

In the demo, `Tracked.close()` sets `closed=true` *before* deliberately throwing `IOException`. This merely models a fixture-defined contract. With real resources, a `close()` failure can leave post-close state dependent on the API/provider. Never conclude **every native handle was freed** solely because a spy received `close()`.

Similarly, `wrapped-close-calls=1` verifies this example's wrapper behavior. If production code accidentally holds another reference to the same resource and calls `close` again, a unit test scoped only here cannot detect external owners. Tests must model the application's actual ownership structure.

## 8. Designing Unit Tests with Spies and Fault Injection

### 8.1. A spy recording close count and order

A simple fake resource:

~~~java
final class CloseSpy implements AutoCloseable {
    int closeCalls;
    boolean failOnClose;

    @Override
    public void close() throws IOException {
        closeCalls++;
        if (failOnClose) {
            throw new IOException("close failed");
        }
    }
}
~~~

This is an illustrative class importing `java.io.IOException`. If a real class receives resources from callers, inject `CloseSpy` via an interface/factory rather than real OS resources. **Do not merely assert `closeCalls >= 1` when the contract requires one owner**; assert the exact count and check against accidental double-close.

### 8.2. A method with a clear ownership contract

~~~java
static void processOwned(InputStream in) throws IOException {
    try (in) {
        byte[] buffer = new byte[4096];
        while (in.read(buffer) != -1) {
            // Process bytes read.
        }
    }
}
~~~

This illustrates **callee owns**. Tests can pass a fake `InputStream` whose `read(byte[], off, len)` deliberately throws after `n` bytes, then assert `close` was still called.

If the interface specifies **caller owns**, the method must differ:

~~~java
static void processBorrowed(InputStream in) throws IOException {
    byte[] buffer = new byte[4096];
    while (in.read(buffer) != -1) {
        // Use only; DO NOT close here.
    }
}
~~~

In the borrowed case, unit tests should verify the callee **did not close**, while the caller closes in the outer owning scope. Never mix the two contracts.

### 8.3. Injecting faults after partial processing

To catch leaks occurring once processing starts but fails mid-way, a fake can:

- Allow `read()` to succeed `N` times and throw `IOException` on call `N+1`.
- Allow `write(...)` to accept part of the data then throw.
- Fail parsing after the stream has been opened.
- Throw inside a record/file-entry callback.
- Fail during ZIP/GZIP finalization or flush/close.

Tests should assert **preservation of the original exception, close count, and cleanup of all initialized resources**, not merely that the method throws `IOException`.

### 8.4. JUnit 5 — `assertThrows` example

If the project uses JUnit Jupiter, a test can look like:

~~~java
@Test
void closesOwnedInputAfterReadFailure() {
    FailingInputStream fake = new FailingInputStream();

    IOException thrown = assertThrows(
            IOException.class,
            () -> service.processOwned(fake));

    assertEquals("read-failed", thrown.getMessage());
    assertEquals(1, fake.closeCalls());
}
~~~

This is **illustrative JUnit 5 code and does not compile standalone**: `FailingInputStream`, `service`, and its method are project-provided fixtures; Jupiter imports/dependencies are required. Clearly label tests to avoid confusing them with standalone Java SE 17 programs. Avoid rigid call-count assertions if a fake caches or alters actual `read` counts.

## 9. Stream Wrappers and Closing the Underlying Source

Wrappers normally forward `close()` to the underlying stream. For example:

~~~java
InputStream raw = Files.newInputStream(path);
try (BufferedInputStream buffered = new BufferedInputStream(raw)) {
    consume(buffered);
}
~~~

This is illustrative code with defined `Path path` and `consume(...)`. The outer wrapper's owner is responsible for closing; when `BufferedInputStream.close()` runs, it closes the underlying input.

Many developers write:

~~~java
try (InputStream raw = Files.newInputStream(path);
     BufferedInputStream buffered = new BufferedInputStream(raw)) {
    consume(buffered);
}
~~~

This can cause **two attempts to close `raw`**: first by `buffered.close()`, then by TWR calling `raw.close()` in reverse order. Standard `Closeable` implementations are usually idempotent, but **never assume every custom wrapper/resource tolerates double-close safely**. In clear ownership designs, typically only the outermost wrapper belongs in the resource header, or use a controlled ownership-transfer pattern.

### Readers/Writers and charset bridges

~~~java
try (BufferedReader reader = Files.newBufferedReader(
        path, StandardCharsets.UTF_8)) {
    return reader.readLine();
}
~~~

This is illustrative code inside a method returning `String`, with `Path path`. `readLine` can return `null` or throw `IOException`; both paths close the reader.

`BufferedWriter` and `OutputStreamWriter` can raise errors during `flush`/`close` due to encoding and writing bytes. Thus testing both **write-time failures** and **close-time failures** matters, especially for formats with trailers/finalization.

### When a wrapper does not own the underlying stream

Not every wrapper in a framework is automatically allowed to close the underlying stream. Some APIs provide "close shield" wrappers to block `close` from reaching a shared stream. When a stream is **borrowed** from a caller, the wrapper or factory must explicitly state **whether `close` propagates downward**. Test ownership at this boundary to avoid both leaks and prematurely closing a caller's active resource.

## 10. Testing Closure Across Different Java NIO Resource APIs

### 10.1. `FileChannel` / `SeekableByteChannel`

`FileChannel` is `AutoCloseable`; when `read`/`write` throws `IOException`, code must close the channel:

~~~java
try (FileChannel channel = FileChannel.open(
        path, StandardOpenOption.READ)) {
    ByteBuffer buffer = ByteBuffer.allocate(8192);
    while (channel.read(buffer) != -1) {
        buffer.clear();
    }
}
~~~

This illustrates resource management rather than data parsing; if a buffer has `remaining == 0`, `read` may return `0` and the example's logic must ensure the buffer is `clear()`ed. In production, handle no-progress per channel type rather than busy-looping indefinitely.

Tests should ensure `channel.close()` runs if reading/parsing throws `IOException`. `Channel.isOpen()` checks API-level state after closing in integration tests. Confirming "no OS handle remains", however, may require independent observation when diagnosing native resource leaks.

### 10.2. `SocketChannel` / `ServerSocketChannel`

Sockets can fail on `connect`, `accept`, `read`, `write`, or `close`. Tests must define who owns accepted sockets and the listener:

- Closing the listener **must not be assumed** to close all already accepted sockets automatically.
- Once `accept` succeeds, every accepted socket needs its own cleanup path.
- On an error handling one client, do not accidentally close the entire listener if the server should keep serving.
- Use loopback + port `0` for integration tests; set deadlines so tests never hang forever.

Measuring `close` with spy channels often requires an abstraction because channel classes carry specific contracts; avoid faking them by arbitrarily overriding non-final methods if that diverges from real implementations.

### 10.3. `ZipFile` and `ZipInputStream`

ZIP is an important example because streams can fail **during decompression** or CRC checks:

~~~java
try (ZipFile zip = new ZipFile(zipPath.toFile())) {
    ZipEntry entry = zip.getEntry("data.txt");
    if (entry == null) {
        throw new IOException("Missing entry");
    }

    try (InputStream content = zip.getInputStream(entry)) {
        // Read / parse / validate content; exceptions may occur.
    }
}
~~~

This is illustrative code with `Path zipPath`. When an exception occurs, TWR closes the entry stream and `ZipFile` per scope. With `ZipInputStream`, place it in TWR and verify the underlying stream closes if the wrapper owns it. With `ZipOutputStream` or `GZIPOutputStream`, `close` finalizes the compressed structure; remember to test error paths during metadata finalization.

### 10.4. `DirectoryStream`, `Files.list`, `Files.walk`, and `Files.lines`

Not every `Stream<T>` holds OS resources, but **Streams returned by these `Files` APIs can hold file/directory handles**. Close them explicitly:

~~~java
try (Stream<Path> paths = Files.list(directory)) {
    paths.forEach(System.out::println);
}
~~~

~~~java
try (Stream<Path> paths = Files.walk(directory)) {
    long count = paths.filter(Files::isRegularFile).count();
}
~~~

~~~java
try (Stream<String> lines = Files.lines(
        logFile, StandardCharsets.UTF_8)) {
    long count = lines.filter(line -> line.contains("ERROR"))
                      .count();
}
~~~

These are illustrative snippets requiring `java.nio.file.*`, `java.nio.charset.*`, `java.util.stream.Stream`, and `directory`/`logFile` variables. They are not standalone methods, and the `count` values are usage examples producing no output.

**Note:** `Stream.count()`/`findFirst()`/`forEach()` are terminal operations, **not substitutes for `close()`** on a file-backed stream. If the pipeline throws `UncheckedIOException` during iteration, TWR still closes the stream.

### 10.5. `Files.copy` and APIs That Do Not Own Caller Streams

If an API accepts an `InputStream` from a caller, do not assume it closes the stream. For example, `Files.copy(InputStream, Path, ...)` does not replace the input stream's owning scope; the caller must place the input in TWR when it owns it.

Never infer ownership just because a method reads to EOF; **EOF does not mean closed**.

## 11. Testing Initialization Failures: Where Leaks Hide

A resource factory may involve multiple steps:

~~~java
Resource openResource(Path path) throws IOException {
    InputStream in = Files.newInputStream(path);
    // Another initialization step may throw here.
    return new Resource(in);
}
~~~

This is pseudocode with an application-defined `Resource` type. If the step between those two lines fails before returning the object, the caller never receives `Resource` to close. The factory must clean up what it already opened:

~~~java
Resource openResource(Path path) throws IOException {
    InputStream in = Files.newInputStream(path);
    boolean transferred = false;
    try {
        Resource resource = initializeOwnedResource(in);
        transferred = true; // Ownership transfers to returned resource.
        return resource;
    } finally {
        if (!transferred) {
            in.close();
        }
    }
}
~~~

This is **illustrative code** and does not compile standalone because `Resource` and `initializeOwnedResource(...)` are application-defined. It demonstrates ownership transfer, though if both initialization and cleanup fail, the `finally` block above can **mask the initialization error**; production code should use nested try-with-resources or collect suppressed exceptions to preserve the root cause. An even better approach is minimizing manual transfer steps and placing opened resources into a TWR scope as early as possible.

Cleaner TWR-based pattern:

~~~java
try (InputStream in = Files.newInputStream(path)) {
    // Preparation steps consume `in` completely within this scope.
    return parseData(in);
}
~~~

This illustrates the case where `parseData` returns a result **without retaining the stream**. If `parseData` must return an object owning `in` itself, you cannot close `in` before returning: design an explicit ownership transfer instead.

### Testing partial initialization

- Error before opening: nothing to close.
- Open A succeeds, open B fails: A must close.
- Factory opens file then fails header parsing: file must close.
- Wrapper constructor fails after receiving source: factory/caller must agree who owns and cleans up the source.
- Resource returned successfully but caller rejects it: caller must close per contract.

Do not test exceptions at only one site; the **exact failure point** determines which resources already exist.

## 12. Test Doubles Alone Cannot Verify Real OS Handles

Spies measuring Java calls are valuable, yet have limits:

- `closeCalls == 1` confirms `close` was invoked on a fake, not that the kernel released a file descriptor.
- Spies do not exercise kernel buffers, delayed writes, flushes, or corruption.
- A third-party library wrapper may hold additional resources outside the fake's visibility.
- Concurrency bugs (another thread reading during `close`) can produce states and exceptions absent from sequential unit tests.

### Where integration tests add value

With real files:

1. Use `Files.createTempFile` or `Files.createTempDirectory` for an isolated test area.
2. Open real resources through production code.
3. Inject parsing/processing faults instead of relying on random hardware errors.
4. After the method exits with an exception, check `isOpen()` (if supported), reopen/read/write the file via a fresh handle, and clean up temporary files.
5. Where needed, use OS-level tools to compare descriptor counts before and after repeated runs.

**Never use file deletability as a universal cross-platform criterion**. Some operating systems allow unlinking an open file, so `Files.deleteIfExists` succeeding **does not prove** the handle was closed.

### Stress/soak tests

Small leaks rarely show up in a single run. Run 1,000–10,000 cycles of "open → read error → cleanup" in an environment with suitable quotas and observe:

- File handle/socket counts.
- Threads/tasks still holding resources.
- Latency and memory over time.
- Failed request counts and suppressed exceptions.
- Remaining open directory streams or ZIP readers.

Base conclusions on steady-state trends in a controlled environment rather than hardcoded numbers from another OS/JDK. Every test must clean up even if an assertion fails.

## 13. Close Failures in Asynchronous and Multi-Threaded Systems

With `AsynchronousFileChannel`, `AsynchronousSocketChannel`, and I/O executors, returning from a method does not necessarily finish all pending operations.

Define the lifecycle explicitly:

~~~text
OPEN
  |
  +--> SUBMITTED OPERATIONS
  |          |
  |          +--> COMPLETED / FAILED / CANCELLED
  |
  +--> SHUTDOWN REQUEST
                |
         stop new submissions
                |
         wait/settle pending I/O per contract
                |
             close channel
                |
             CLOSED
~~~

Some APIs allow closing a channel while operations are pending; in-flight operations may terminate abnormally with `AsynchronousCloseException`. A unit test checking only "`close` was called immediately when the method threw" is **insufficient** when closing belongs to a background component; verify shutdown state after tasks/handlers have settled.

### Avoid flaky tests using `Thread.sleep`

Do not write:

~~~java
startAsyncOperation();
Thread.sleep(200); // guessing the operation finished
assertTrue(isClosed());
~~~

This is a non-runnable **anti-pattern**. Use `CountDownLatch`, `CompletableFuture`, `Future.get(timeout, unit)`, or explicit synchronization with a **deadline** to wait for the close event. A timeout bounds the test; it is not proof that the operation finished when time expires.

### Interrupted threads

Java `try-with-resources` still cleans up when exiting via an interrupt-related exception, though the `close` API itself has its own contract and exceptions. For custom `AutoCloseable` types, Javadoc recommends avoiding `InterruptedException` from `close` because suppression can cause unpredictable behavior. When handling `InterruptedException`, decide whether to restore the interrupt flag and stop per application policy.

## 14. Designing APIs That Are Easy to Close-Test

Testable I/O components typically share these traits:

- **Injectable resources or resource factories** via constructor/factory, enabling read/write/close fault simulation.
- **Explicit ownership contracts**: who creates, who uses, who closes, who transfers ownership.
- **No global singletons for mutable streams** unless sharing is truly required.
- **Minimal scope**: open resources close to where they are used and close promptly when done.
- **No swallowed `IOException`**: body errors and cleanup errors propagate/log per policy.
- **No reliance on GC/finalizers/`Cleaner` as the primary release mechanism**: their timing is non-deterministic.
- **Testing beyond the happy path**: test acquisition failures, partial reads/writes, parser errors, close errors, and early returns.

A classic split:

~~~java
// Core logic operating on a caller-borrowed stream:
static Result parse(InputStream borrowed) throws IOException {
    // Parse; do not close borrowed.
    return decode(borrowed);
}

// Boundary taking ownership of the file stream:
static Result parseFile(Path path) throws IOException {
    try (InputStream owned = Files.newInputStream(path)) {
        return parse(owned);
    }
}
~~~

This is **illustrative code**, with `Result` and `decode` application-defined. This design lets unit tests exercise `parse` using fake inputs while verifying `parseFile` manages filesystem resource lifecycles—without mocking static `Files.newInputStream` for every test.

### Testing methods with clear closing responsibilities

If an API takes an `InputStream stream` under **caller owns**, tests should assert the stream **remains open after the method finishes** (even on error). Conversely, the `parseFile` boundary must assert the file stream is closed on any error. Both opposite assertions can be right because ownership differs.

## 15. Why Close Testing Must Also Account for `finally` Errors

When manual `finally` is unavoidable because no suitable `AutoCloseable` exists or ownership is complex:

1. Preserve the original exception.
2. Do not skip remaining resources needing cleanup if one `close` fails.
3. Never close resources the method does not own.
4. Handle incomplete initialization cleanly.
5. Do not hide suppressed exceptions in logging/monitoring.
6. Avoid double-closing resources with non-idempotent semantics.

With multiple resources, hand-coding all these cases is error-prone; **prefer `try-with-resources`** wherever possible. If you must aggregate exceptions manually, attach cleanup errors to the primary via `addSuppressed`, taking care not to self-suppress or pass `null`.

### When to catch and when not to catch

**Simple and usually sufficient:**

~~~java
try (InputStream in = Files.newInputStream(path)) {
    return parse(in);
}
~~~

If the caller understands `IOException`, do not catch just to log and rethrow. If the app needs extra context, preserve the cause:

~~~java
try (InputStream in = Files.newInputStream(path)) {
    return parse(in);
} catch (IOException ex) {
    throw new IOException("Cannot parse: " + path, ex);
}
~~~

Both snippets are **illustrative code inside a parser method** where `parse` is defined. On a wrapped exception, suppressed errors remain attached to the cause `ex`; logging tools should traverse both cause chains and suppressed exceptions so close failures are never lost.

**Avoid:**

~~~java
catch (IOException ex) {
    return null; // swallows error, caller thinks read succeeded
}
~~~

This is an anti-pattern. Swallowing `IOException` may still close the resource, yet leaves output data and control flow untrustworthy. If a product supports a valid fallback, express it via an explicit return type rather than turning errors into ambiguous success.

## 16. Final Checklist for Tests and Code Reviews

Before considering an I/O path properly cleaned up, verify:

- [ ] **Resource owner** is identified for every stream/channel/wrapper.
- [ ] All successfully opened resources sit inside `try-with-resources` or equivalent cleanup.
- [ ] When opening a second resource fails, the first resource still closes.
- [ ] On `read`, `write`, parse, or callback failure, cleanup still runs.
- [ ] On `return`/`break` or early exit, cleanup runs properly.
- [ ] Multiple resources close in **reverse order**, and one failing `close` does not block closing others.
- [ ] Body exceptions remain primary and `close` errors appear in `getSuppressed()`.
- [ ] Wrappers close underlying sources per ownership; no double-closing non-idempotent resources.
- [ ] File-backed streams from `Files.lines/list/walk` close even if the terminal operation throws.
- [ ] Fakes/spies confirm **`close` was called**; integration tests verify real-world behavior as needed.
- [ ] OS handle release is never inferred solely from file deletability.
- [ ] Async tasks use deadlines and synchronization to verify completion/closure—never fixed sleeps.
- [ ] Primary and suppressed exceptions are logged/propagated adequately for diagnostics.
- [ ] Test fixtures release their own resources even when assertions fail.

## 17. Common Mistakes

1. **"Reaching EOF closes the stream automatically."** False: `read() == -1` does not replace `close()`.
2. **"GC will reclaim file handles promptly."** Timing is non-deterministic; always close explicitly.
3. **"Only close on the happy path."** False: error paths leak far more often.
4. **"Resources in TWR close in the order they were opened."** False: they close in **reverse** order.
5. **"If opening the second resource fails, the first isn't closed."** False if the first initialized successfully in the header.
6. **"If the second `close` throws, Java skips closing the first."** False: all opened resources are still attempted.
7. **"A `close` error always overrides a `read` error."** False in TWR; `close` errors are suppressed when a primary exists.
8. **"`getCause` and `getSuppressed` are the same."** False: cause chains and suppressed cleanup errors are distinct.
9. **"`Spy.closeCalls == 1` guarantees no OS descriptor remains."** False: verify with real tests/instrumentation as needed.
10. **"Calling `close` twice on any `AutoCloseable` is safe."** False: `AutoCloseable` does not mandate idempotency.
11. **"Closing `BufferedInputStream` leaves the underlying stream open."** Wrappers normally close their source; know ownership.
12. **"A terminal operation on `Files.lines` closes the stream automatically."** False: file-backed streams must be closed.
13. **"If a constructor/factory throws before returning, TWR automatically cleans up inside it."** False: partially opened resources not yet handed to TWR must be cleaned up by the factory.
14. **"Being able to delete the file proves the stream was closed."** False on OSes with open-file unlink semantics.
15. **"`Thread.sleep(100)` is enough to test async close."** Non-deterministic; use synchronization and deadlines.
16. **"`close()` can never throw `IOException`."** False: output flushing/finalization in particular can fail.
17. **"`catch` and `return null` is a safe way to handle I/O errors."** Usually loses context and produces false success.
18. **"Closing a listener automatically closes all accepted channels."** Never assume this; every channel needs its own ownership.

## 18. Self-Check Questions

**Question 1.** In TWR with two resources A and B, the body throws `IOException("read")` and `B.close()` throws `IOException("close")`. What exception does the caller see?

**Answer:** `"read"` is primary; `"close"` is inside `getSuppressed()`. Java still attempts to close A.

**Question 2.** Resource A opens successfully, but initializing B throws `IOException`. Does A close?

**Answer:** Yes, if A initialized successfully in the TWR header. The body does not run, and B's initialization exception is primary.

**Question 3.** If a method executes `return` inside TWR, does `close` run before or after the method finishes returning?

**Answer:** `close` runs when exiting the scope before the method finishes returning its value. If `close` throws an exception, the method completes abnormally with that exception instead of returning normally.

**Question 4.** Why do unit tests using `CloseSpy` still need some integration tests?

**Answer:** Spies verify `close` calls against a fake's contract; they do not thoroughly test native handles, output finalization, or internal resources of real implementations.

**Question 5.** Why isn't `Files.lines(path).count()` enough to ensure the file is closed?

**Answer:** Terminal operations consume elements without promising to close the file-backed stream. Wrap the returned stream in TWR.

**Question 6.** A service wraps `System.in` in a `BufferedInputStream`. Should the service close the wrapper by default when done?

**Answer:** Cannot decide without knowing ownership. Closing the wrapper normally closes the underlying stream; for shared `System.in`, design explicit borrowed ownership or a close-shield.

**Question 7.** An object's close handler can throw `IOException`. What should unit tests verify besides `closeCalls`?

**Answer:** Verify primary/suppressed exceptions, close order of other resources, and that the method propagates errors per contract.

**Question 8.** If an async I/O callback is pending and code requests shutdown, when can you conclude cleanup is complete?

**Answer:** Only after cancellation/completion policies and channel/resource closure are confirmed via signals/synchronization with a deadline; you cannot infer it merely because the shutdown-request method returned.

### Official Java 17 Documentation

- [JLS `14.20.3 — try-with-resources](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3)
- [AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html)
- [Closeable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Closeable.html)
- [Throwable.getSuppressed](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html#getSuppressed())
- [Files — lines, list, walk](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [BufferedInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedInputStream.html)
- [FileChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html)
- [ZipFile](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipFile.html)
