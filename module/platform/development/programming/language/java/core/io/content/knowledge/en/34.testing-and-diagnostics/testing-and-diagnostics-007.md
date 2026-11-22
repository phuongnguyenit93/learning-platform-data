# Verifying Resources Are Closed on Failure in Java I/O

## 1. Why Can a Program That Produces Correct Results Still Leak Resources?

Java I/O programs commonly open **file streams, readers/writers, channels, sockets, ZIP archives, directory streams**, or other resources holding OS file descriptors/handles. If an exception occurs mid-operation and a resource is not released, the consequences can include:

- File descriptors or socket handles are never returned; the system fails with errors like "Too many open files."
- Files remain open, preventing renaming or deletion on certain operating systems.
- Output buffers are not flushed or finalized; ZIP/GZIP data lacks trailers or metadata.
- Network connections stay open, tying up client and server resources.
- Directory streams or file input streams continue holding handles even after business logic stops using them.
- In high-throughput request systems, rare errors accumulate into severe leaks.

**Verifying resources are closed on failure** means writing tests that force code down error paths, then observing **who is responsible for closing, how many times `close` is called, in what order, and which exceptions are preserved**.

This is not just "add a `finally` block." Modern Java favors **`try-with-resources`** for `AutoCloseable` objects, yet we still must test ownership contracts and handle subtle edge cases.

Goals after this lesson:

1. Master `try-with-resources` semantics on normal exit, exceptions, `return`, `break`, and acquisition failures.
2. Verify resources are closed even when `read`/`write` throws `IOException`.
3. Understand primary exceptions and **suppressed exceptions** raised by `close()`.
4. Build test doubles and fault injection to measure close calls and ordering without relying on random I/O failures.
5. Recognize the limits of test doubles: calling `close()` does not by itself prove an OS handle was actually released.
6. Apply these checks to stream wrappers, `FileChannel`, `ZipFile`, `DirectoryStream`, and `Files.lines()`/`walk()`/`list()`.

## 2. Distinguishing `close`, `flush`, and Actual Resource Release

Three concepts are often conflated:

| Concept | Core Contract | How to Observe / Test |
|---|---|---|
| `flush()` | Pushes buffered data to the next layer per the stream/writer contract | Fake output records `flush`; verify data reached the underlying stream |
| `close()` | Ends the resource lifecycle; depending on API, may flush/finalize before releasing | Spy/tracker records `close`; integration test checks resource state |
| Data durability | Bytes are guaranteed persisted per the application contract | Use appropriate APIs like `FileChannel.force(...)`, filesystem policy, and dedicated tests |

`OutputStream.close()`/`Writer.close()` usually finishes flushing that layer's buffer before closing the underlying stream. However, **closing does not guarantee all data is durable on the storage device**, nor does it mean a network peer confirmed processing.

For close testing, define the exact invariant:

> If a method **owns** a successfully opened resource, then on every exit path from that method—including when an error is thrown—that resource must be closed per contract.

"Requested to close" is the unit-test level using a spy. "Handle no longer held open" may require OS/API-level integration tests. "Durably persisted data" is a separate requirement altogether.

## 3. \`AutoCloseable\`, \`Closeable\`, and Resource Ownership

`AutoCloseable` declares:

~~~java
public interface AutoCloseable {
    void close() throws Exception;
}
~~~

`java.io.Closeable` extends `AutoCloseable`, declares `close() throws IOException`, and by the `Closeable` contract, calling `close` on an already-closed object has no further effect. However, **plain `AutoCloseable` does not mandate idempotent `close()`**; Javadoc recommends implementers make it idempotent if possible.

Common resources:

| API | Resource | Who Should Close? |
|---|---|---|
| `FileInputStream`, `FileOutputStream` | File stream | The code that created or took ownership per contract |
| `BufferedInputStream`, `BufferedReader` | Wrapper and underlying source | Usually close the outer wrapper, which closes the underlying source |
| `InputStreamReader`, `OutputStreamWriter` | Byte ↔ char bridge and underlying stream | Usually the owner of the outer bridge |
| `FileChannel`, `SocketChannel`, `ServerSocketChannel` | File/socket channel | The component owning the channel |
| `ZipFile`, `ZipInputStream` | ZIP container/stream | The component opening the ZIP |
| `DirectoryStream<Path>` | Directory handle | The component calling `Files.newDirectoryStream` |
| `Stream<String>` from `Files.lines` | Open file stream | The code calling `Files.lines` |
| `Stream<Path>` from `Files.list`/`Files.walk` | Directory handles | The code creating the file-backed stream |

**Ownership must be explicit.** When a method receives an `InputStream` from a caller, there are two valid but non-equivalent designs:

- **Callee owns:** the method assumes responsibility for closing the stream even on failure; this must be stated in the API contract.
- **Caller owns:** the method only reads/writes and does not close the stream; the caller closes it in an outer scope.

There is no universal rule that "if you have an `InputStream`, just close it." For example, many APIs must never close `System.in` or a shared stream.

## 4. \`try-with-resources\`: The Foundation for Exception-Safe Cleanup

Java 17 syntax:

~~~java
try (InputStream in = Files.newInputStream(source);
     OutputStream out = Files.newOutputStream(target)) {
    in.transferTo(out);
}
~~~

This is illustrative code requiring `java.io.*`, `java.nio.file.*`, and defined `Path source, target`. For any resource successfully initialized in the header, Java automatically calls `close()` upon exiting the `try` block, whether:

- The block completes normally.
- A `return` executes inside the block.
- A `break` or `continue` leaves the scope.
- The block throws `IOException`, `RuntimeException`, or `Error`.
- Trailing `catch`/`finally` blocks execute afterward.

### 4.1. Creation and Closing Order

Resources in the header are **initialized left to right** and **closed right to left**.

~~~java
try (Tracked first = open("first");
     Tracked second = open("second")) {
    runBusinessLogic();
}
~~~

This is illustrative structural code with custom `Tracked` and factory methods. Execution flow:

~~~text
open first
open second
body
close second
close first
~~~

If `runBusinessLogic()` fails, both `close` calls still run in reverse order. If `close second` also throws an error, Java **still attempts to close `first`**.

### 4.2. What If Opening the Second Resource Fails?

Suppose opening `first` succeeds, while initializing `second` throws an exception:

~~~text
open first   -> succeeds
open second  -> throws IOException
close first  -> executed automatically
body         -> NOT executed
~~~

This is a mandatory branch to test. `try-with-resources` guarantees that resources **already initialized earlier in the header** are closed. However, if **a resource's constructor or factory itself allocates a native handle and throws before returning the object**, the `try` header never received that resource; the constructor/factory must clean up its own partially opened state.

### 4.3. Null Resources

A resource expression may evaluate to `null`. Java does not call `close()` on a `null` resource; however, using `null` to signify an absent resource often makes contracts harder to reason about and must be tested explicitly when permitted by an API.

### 4.4. Existing Variables in `try-with-resources`

Since Java 9, a `final` or **effectively final** local variable or field can be placed in the header:

~~~java
InputStream opened = Files.newInputStream(source);
try (opened) {
    consume(opened);
}
~~~

This is illustrative and requires defining `consume`. It works when initialization must happen one step earlier while still handing ownership of the variable to `try-with-resources`. Never use the resource after the closing scope ends.

## 5. Exception in the Body vs. Exception in `close`: Which Is Thrown?

This is the single most important detail when testing error paths.

Suppose:

1. `read()` throws `IOException("read-failed")`.
2. During cleanup, `close()` also throws `IOException("close-failed")`.

With `try-with-resources`:

- The exception from the body (`read-failed`) remains the **primary exception** thrown to the caller.
- The exception from `close` (`close-failed`) is attached to the primary exception as a **suppressed exception**.
- The caller can inspect it via `Throwable.getSuppressed()`.

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

This is an **illustrative code snippet** requiring definitions for `openFailingStream()` and `consume(...)`. Never equate `Throwable.getCause()` with `getSuppressed()`:

| API | Represents |
|---|---|
| `getCause()` | The underlying cause of a wrapped/chained exception |
| `getSuppressed()` | Additional exceptions captured while cleaning up after a primary exception |
| `addSuppressed(...)` | Allows manual cleanup-exception attachment, though `try-with-resources` does this automatically |

### What If the Body Succeeds and `close` Fails?

When no body exception occurs, the `close` exception is thrown as the primary error. If **multiple resources fail to close**, the exception from the resource closed first (the rightmost one in the header) becomes primary, and subsequent close failures become suppressed exceptions.

### What If Both Acquisition and `close` Fail?

If resource `B` fails to initialize while `A` is already open, the initialization exception from `B` is kept as primary; any error closing `A` is attached as suppressed. This preserves **the root reason the operation failed** instead of letting cleanup mask it.

### Why Hand-Written `finally` Blocks Easily Go Wrong

A pattern that loses the original error:

~~~java
InputStream in = open();
try {
    doWork(in);         // throws IOException A
} finally {
    in.close();         // throws IOException B
}
~~~

This is an anti-pattern without explicit suppressed-exception handling: the caller receives only `B`, while `A` is masked. `try-with-resources` implements exact language-specified exception priority; use it instead of reimplementing this logic by hand.

## 6. Testing Strategy: Proactively Inject Faults at Every Step

To guarantee `close` works on failure, do not wait for the filesystem or network to glitch randomly. Build **test doubles** or fault-injection fixtures that simulate failures at each stage.

A minimum test matrix:

| Scenario | What to Verify |
|---|---|
| Successful execution | Opened resource is closed exactly once per ownership |
| `read` throws an error | `close` is called; caller receives the read error |
| `write` throws an error | `close` is called; caller receives the write error |
| Early `return` | `close` executes before the return completes |
| `break`/`continue` exits scope | `close` executes when leaving scope |
| Opening second resource fails | First resource is still closed |
| Two active resources | Closed in reverse initialization order |
| `close` itself throws an error | Error propagates properly; remaining resources still attempt to close |
| Both body and `close` fail | Body error is primary, close error is in `suppressed` |
| Wrapper fails while reading | Closing wrapper closes underlying source per ownership |
| Resource closed twice | Never rely on luck; verify contract and exact call count |
| Async I/O cancel/timeout | Verify cancellation policy and release once all operations resolve |

Distinguish three kinds of tests:

1. **Unit-level contract tests:** fake/spy resources verify `close()` is called and exceptions behave properly.
2. **Integration tests:** open real files, sockets, or ZIPs, run fault scenarios, and verify closure via API/OS checks.
3. **Diagnostic/soak tests:** repeat failure loops many times to monitor file descriptors, memory, and thread/socket counts over time.

Do not rely on an OS-specific "cannot delete an open file" failure as **the sole proof**. Linux commonly allows unlinking a file name even while a handle remains open; Windows has different sharing/locking rules. Portable tests should use spies and verify state through proper APIs.

## 7. Complete Java 17+ Program Testing Four Failure Branches

The example below contains all its own fixtures and requires no JUnit or real disk files. It demonstrates:

- Simultaneous body and `close` failures.
- Two resources closed in **reverse** open order.
- Failure while acquiring the second resource.
- `BufferedInputStream` throwing mid-read while still closing its underlying stream.
- Early `return` from a method still closing the resource.

**File name: `CloseOnFailureDemo.java`**

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

**Verified stdout from JDK:**

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

### Why Each Line Matters

**`primary=work-failed`:** the body threw `IOException` first; this is the primary error. The failing `close()` does not replace it.

**`suppressed=close-second`:** resource `second` threw `IOException` during `close`; Java kept the body error and recorded the cleanup error separately.

**`close-order=...`:** resources opened as `first` then `second`, yet closed as `second` then `first`. Both close calls ran even though `second` threw.

**`acquisition=acquire-failed`:** `failAcquire` threw in the header stage; the body never ran, and the second acquisition error was preserved.

**`acquisition-trace=...close:held`:** even though the second resource could not be created, the already-initialized `held` resource was still closed.

**`read-failure=read-failed`:** the fake stream threw from `read`. This is fault injection, avoiding any need to break real files.

**`wrapped-close-calls=1`:** `try-with-resources` closed `BufferedInputStream`, and the wrapper closed `FailingInput` once. In the example, only the outer wrapper is declared as the owned resource so the underlying source is not closed twice.

**`early-return-closed=true`:** even though `earlyReturn` returns a string, `Tracked.close` still runs before the return finishes.

### Limitations of Test Doubles

In the demo, `Tracked.close()` sets `closed=true` *before* throwing its simulated `IOException`. This only models a fixture-defined contract. For real resources, a throwing `close()` can leave post-close state dependent on the API or provider. Never conclude **all native handles were freed** solely because a spy recorded `close()`.

Likewise, `wrapped-close-calls=1` verifies wrapper behavior in this example. If production code accidentally holds another reference to the same resource and closes it elsewhere, a unit test scoped to one method cannot automatically detect every external owner. Tests must mirror the application's actual ownership structure.

## 8. Designing Unit Tests with Spies and Fault Injection

### 8.1. A Spy Recording Close Count and Order

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

This is an illustrative class requiring `java.io.IOException`. If real code receives resources from a caller, inject `CloseSpy` via an interface or factory instead of touching real OS resources. **Do not just assert `closeCalls >= 1` when the contract demands a single owner**; assert the exact count and check against accidental double-close.

### 8.2. Methods with Explicit Ownership Contracts

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

This illustrates **callee owns**. A test can pass a fake `InputStream` whose `read(byte[],off,len)` throws after `n` bytes and assert `close` was still called.

If the interface specifies **caller owns**, the method differs:

~~~java
static void processBorrowed(InputStream in) throws IOException {
    byte[] buffer = new byte[4096];
    while (in.read(buffer) != -1) {
        // Use only, DO NOT close.
    }
}
~~~

For borrowed resources, unit tests should verify the callee **did not close** the stream, while the caller closes it in the owning outer scope. Never mix the two contracts.

### 8.3. Injecting Faults After Partial Processing

To catch leaks that occur once processing has begun but before it finishes, a fake can:

- Allow `read()` to succeed `N` times and throw `IOException` on call `N+1`.
- Allow `write(...)` to accept some data and then throw an error.
- Trigger a parse error after the stream is opened.
- Throw inside a record/file-entry callback.
- Fail during ZIP/GZIP finalization or `flush`/`close`.

Tests should assert **preservation of the original exception, close counts, and cleanup of all initialized resources**, not merely that the method threw `IOException`.

### 8.4. JUnit 5 — `assertThrows` Example

If the project uses JUnit Jupiter, a test can be written as:

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

This is a **JUnit 5 illustrative snippet and does not compile standalone**: `FailingInputStream`, `service`, and its method are project-supplied fixtures, requiring Jupiter dependencies and imports. Mark tests clearly to avoid confusing them with standalone Java SE 17 examples. Do not assert hardcoded assumptions if a fake or wrapper buffers reads and changes actual `read` call counts.

## 9. Stream Wrappers and Closing the Underlying Source

Wrappers typically forward `close()` to the underlying stream. Example:

~~~java
InputStream raw = Files.newInputStream(path);
try (BufferedInputStream buffered = new BufferedInputStream(raw)) {
    consume(buffered);
}
~~~

This is an illustrative snippet with defined `Path path` and `consume(...)`. The owner of the outer wrapper is responsible for closing; when `BufferedInputStream.close()` runs, it closes the underlying input.

A style many developers write:

~~~java
try (InputStream raw = Files.newInputStream(path);
     BufferedInputStream buffered = new BufferedInputStream(raw)) {
    consume(buffered);
}
~~~

This can cause **two attempts to close `raw`**: first via `buffered.close()`, then TWR calls `raw.close()` in reverse order. Standard `Closeable` implementations make `close()` idempotent, yet **never assume every custom wrapper or resource tolerates double-close safely**. When ownership is clear, place only the outermost wrapper in the resource header, or design explicit ownership transfer.

### `Reader`/`Writer` and Charset Bridges

~~~java
try (BufferedReader reader = Files.newBufferedReader(
        path, StandardCharsets.UTF_8)) {
    return reader.readLine();
}
~~~

This is an illustrative snippet inside a method returning `String` with `Path path`. `readLine` can return `null` or throw `IOException`; both paths close the reader.

`BufferedWriter` and `OutputStreamWriter` can raise errors during `flush`/`close` because of encoding and byte-writing steps. Testing both **write-time failures** and **close-time failures** is therefore essential, especially for formats with trailers or finalization.

### When a Wrapper Does Not Own the Underlying Stream

Not every wrapper in a framework is allowed to close the stream beneath it. Some APIs provide a "close shield" wrapper to block `close` from reaching a shared stream. When a stream is **borrowed** from a caller, wrappers and factories must make clear **whether `close` propagates downward**. Test ownership at this boundary to avoid both leaks and prematurely closing a resource the caller still needs.

## 10. Testing Resource Closure Across Java NIO APIs

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

This snippet illustrates resource management rather than data parsing; if a buffer has `remaining == 0`, `read` can return `0`, and the example ensures the buffer is cleared. In production, handle zero-progress reads properly for each channel type rather than busy-looping.

Tests should ensure `channel.close()` is called if reading or parsing throws `IOException`. `Channel.isOpen()` lets integration tests check API state after closing. However, confirming "no OS handle remains" may require separate observation when debugging native resource leaks.

### 10.2. `SocketChannel` / `ServerSocketChannel`

Sockets can fail on `connect`, `accept`, `read`, `write`, or `close`. Tests must define who owns accepted sockets and listeners:

- Closing a listener **must not be assumed** to close every already-accepted socket automatically.
- Once `accept` succeeds, each accepted socket needs its own cleanup path.
- On an error handling one client, do not accidentally close the entire listener if the server should keep running.
- Use loopback + port `0` for integration tests; enforce deadlines so tests cannot hang forever.

Measuring `close` with spy channels often requires an abstraction because channel classes have strict contracts; avoid building fakes by arbitrarily overriding final or native methods in ways that misrepresent the real implementation.

### 10.3. `ZipFile` and `ZipInputStream`

ZIP is an important case because streams can fail **mid-decompression** or during CRC verification:

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

This is an illustrative snippet with `Path zipPath`. When an exception occurs, TWR closes the entry stream and `ZipFile` in scope order. With `ZipInputStream`, place it in TWR and track closing of the underlying stream if the wrapper owns it. With `ZipOutputStream` or `GZIPOutputStream`, `close` finalizes the compressed trailer; remember to test failures during metadata finalization.

### 10.4. `DirectoryStream`, `Files.list`, `Files.walk`, and `Files.lines`

Not every `Stream<T>` holds an OS resource, but **streams returned by these `Files` APIs can hold file or directory handles**. Close them explicitly:

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

These are illustrative snippets requiring `java.nio.file.*`, `java.nio.charset.*`, `java.util.stream.Stream`, and `directory`/`logFile` variables. They are not standalone methods, and `count` values are usage examples without printed output.

**Note:** `Stream.count()`/`findFirst()`/`forEach()` are terminal operations, yet **they do not replace `close()`** on a file-backed stream. If the pipeline throws `UncheckedIOException` during iteration, TWR still closes the stream.

### 10.5. `Files.copy` and APIs That Manage Their Own Sources

If an API accepts an `InputStream` from a caller, do not assume it closes the stream. For example, `Files.copy(InputStream, Path, ...)` does not take over the input stream's ownership scope; the caller must place the input in TWR when the caller is the owner.

Never infer ownership just because a method reads to EOF; **EOF does not mean closed**.

## 11. Testing Initialization Failures: Where Leaks Hide

A resource factory can involve multiple steps:

~~~java
Resource openResource(Path path) throws IOException {
    InputStream in = Files.newInputStream(path);
    // Another initialization step may throw an error here.
    return new Resource(in);
}
~~~

This is pseudocode where `Resource` is application-defined. If the step between the two lines fails before returning the object, the caller never receives a `Resource` to close. Design the factory to clean up partially opened state:

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

This is **illustrative code** and does not compile standalone because `Resource` and `initializeOwnedResource(...)` are application-defined. It demonstrates ownership transfer, though if both initialization and cleanup fail, the `finally` block above can **mask the initialization error**; production code should use nested `try-with-resources` or collect suppressed exceptions to preserve the root cause. Even better, minimize manual transfer steps and put opened resources into a TWR scope as early as possible.

Cleaner example using TWR when possible:

~~~java
try (InputStream in = Files.newInputStream(path)) {
    // Preparation steps completely consume in within this scope.
    return parseData(in);
}
~~~

This illustrates the case where `parseData` returns a result **without retaining the stream**. If `parseData` must return an object owning `in` itself, you cannot close `in` before returning and must design explicit ownership transfer.

### Testing Partial Initialization

- Failure before opening: nothing to close.
- Open A succeeds, open B fails: A must close.
- Factory opens file, then header parsing fails: file must close.
- Wrapper constructor fails after receiving a source: factory/caller must agree on who owns and cleans up the source.
- Resource returned successfully yet rejected by caller: caller must close per contract.

Do not test exceptions at only one point; **the exact point of failure** determines which resources already exist.

## 12. Test Doubles Are Not Enough to Verify Real Handles

Java call spies are very useful, but have limitations:

- `closeCalls==1` confirms `close` was called on the fake, not that the kernel released the file descriptor.
- Spies do not test kernel buffers, delayed writes, flushes, or corruption.
- A third-party library wrapper may hold extra resources outside the fake's scope.
- Concurrency bugs (another thread reading during `close`) can produce states and exceptions unseen in sequential unit tests.

### Where Integration Tests Add Value

With real files:

1. Use `Files.createTempFile` or `Files.createTempDirectory` for an isolated test area.
2. Open real resources through production code.
3. Inject parsing/processing failures rather than relying on random hardware errors.
4. After the method exits with an exception, check `isOpen()` (if supported), reopen/read/write the file via a fresh handle, and clean up temporary files.
5. When needed, use OS-level tools to inspect descriptor counts before and after repeated test runs.

**Never use file deletability as a universal cross-platform proof.** Some operating systems allow unlinking an open file, so a successful `Files.deleteIfExists` **does not prove** the handle was closed.

### Stress / Soak Tests

Small leaks are hard to spot in a single run. Execute 1,000–10,000 cycles of "open → read error → cleanup" in an appropriately bounded environment and monitor:

- File handle and socket counts.
- Threads or tasks still holding resources.
- Execution duration and memory over time.
- Error counts and suppressed exception counts.
- Open directory streams and ZIP readers.

Draw conclusions from stability trends in a controlled environment, not hardcoded counts from another OS or JDK. Every test must clean up its own artifacts even when assertions fail.

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
         wait for/resolve pending I/O per contract
                |
             close channel
                |
             CLOSED
~~~

Some APIs allow closing a channel while operations are pending, causing those operations to terminate abnormally with `AsynchronousCloseException`. A unit test checking only "close was called immediately when the method threw" is **insufficient** when a background component owns closure; check shutdown state after all tasks and handlers have resolved.

### Avoiding Flaky Tests with `Thread.sleep`

Do not write:

~~~java
startAsyncOperation();
Thread.sleep(200); // guess operation finished
assertTrue(isClosed());
~~~

This is a non-runnable **anti-pattern**. Use `CountDownLatch`, `CompletableFuture`, `Future.get(timeout, unit)`, or explicit synchronization with a **deadline** to wait for the close event. The timeout bounds the test—it is not proof an operation finished simply because time elapsed.

### When a Thread Is Interrupted

Java `try-with-resources` still runs cleanup when exiting scope due to an interrupt-induced exception, though individual `close` APIs have their own contracts and exceptions. For custom `AutoCloseable` types, Javadoc recommends against throwing `InterruptedException` from `close`, as suppression can produce unpredictable behavior. When handling `InterruptedException`, decide explicitly whether to restore the interrupt flag and stop per application policy.

## 14. Designing APIs That Are Easy to Test for Closure

Testable I/O components share common traits:

- **Injectable resources** or resource factories via constructors/parameters, enabling read/write/close fault simulation.
- **Clear ownership contracts**: who creates, who uses, who closes, and who transfers ownership.
- **No global singletons for mutable streams** unless sharing is genuinely required.
- **Tight scopes**: open resources right before use and close them as early as possible.
- **Never swallow `IOException`**: body and cleanup errors propagate or log per policy.
- **Never rely on GC, finalizers, or `Cleaner` as the primary release mechanism**: they give no deterministic close timing.
- **Test beyond the happy path**: cover initialization errors, partial reads/writes, parser errors, close errors, and early returns.

A typical separation:

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

This is **illustrative code**, where `Result` and `decode` are application-defined. This design lets unit tests test `parse` with fake inputs while testing `parseFile`'s filesystem resource lifecycle separately, without needing to mock static `Files.newInputStream` for every test.

### Testing Methods with Explicit Close Responsibilities

If an API takes `InputStream stream` with **caller owns** semantics, tests should assert the stream **remains open after the method finishes** (even on error). Conversely, the `parseFile` boundary must assert the file stream is closed on any error. Two opposite assertions can both be right because ownership differs.

## 15. Why Close Testing Must Also Account for `finally` Failures

When manual `finally` is unavoidable due to non-`AutoCloseable` APIs or complex ownership:

1. Preserve the original exception.
2. Do not skip cleaning up remaining resources if one `close` fails.
3. Never close resources the method does not own.
4. Do not skip partially initialized state.
5. Do not hide suppressed exceptions from logging and monitoring.
6. Avoid double-closing resources with non-idempotent close semantics.

With multiple resources, writing every case accurately by hand is error-prone; **prefer `try-with-resources`** whenever possible. If you must aggregate exceptions manually, attach cleanup errors to the primary exception with `addSuppressed`, taking care never to suppress an exception onto itself or pass `null`.

### When to `catch` and When Not To

**Simple and usually sufficient:**

~~~java
try (InputStream in = Files.newInputStream(path)) {
    return parse(in);
}
~~~

If the caller understands `IOException`, do not catch merely to log and rethrow. If the application needs extra context, preserve the cause:

~~~java
try (InputStream in = Files.newInputStream(path)) {
    return parse(in);
} catch (IOException ex) {
    throw new IOException("Cannot parse: " + path, ex);
}
~~~

Both snippets are **illustrative code inside a method returning a parser result** where `parse` must be defined. When wrapped, any suppressed close exceptions remain attached to the cause `ex`; logging tools should traverse both causes and suppressed exceptions so close failures are never lost.

**Avoid:**

~~~java
catch (IOException ex) {
    return null; // swallows error, caller thinks read succeeded
}
~~~

This is an anti-pattern. Swallowing `IOException` may still close the resource, yet leaves output data and control flow untrustworthy. If a product defines a valid fallback, express it through an explicit return type rather than turning failure into ambiguous success.

## 16. Final Checklist for Tests and Code Reviews

Before considering an I/O path properly cleaned up, verify:

- [ ] Identify the **resource owner** for every stream, channel, and wrapper.
- [ ] All successfully opened resources sit inside `try-with-resources` or equivalent cleanup.
- [ ] When opening a second resource fails, the first resource still closes.
- [ ] When `read`, `write`, parsing, or callbacks fail, cleanup still runs.
- [ ] On `return`, `break`, or early exit, cleanup runs properly.
- [ ] Multiple resources close in **reverse order**, and one `close` failure does not prevent closing the others.
- [ ] Body exceptions remain primary and `close` exceptions appear in `getSuppressed()`.
- [ ] Wrappers close underlying sources per ownership; non-idempotent resources are never double-closed.
- [ ] File-backed streams from `Files.lines`/`list`/`walk` close even if a terminal operation throws.
- [ ] Fakes/spies confirm **`close` was called**; integration tests verify real behavior where needed.
- [ ] OS handle release is never inferred solely from file deletability.
- [ ] Async tasks use deadlines and synchronization to verify completion/closure instead of fixed sleeps.
- [ ] Primary and suppressed exceptions are logged/propagated adequately for diagnosis.
- [ ] Test fixtures release resources themselves even when assertions fail.

## 17. Common Mistakes

1. **"Reaching EOF closes the stream automatically."** False: `read() == -1` does not replace `close()`.
2. **"GC will reclaim file handles in time."** No deterministic timing exists; always close explicitly.
3. **"Only close on the happy path."** False: error paths leak much more easily.
4. **"Resources in TWR close in opening order."** False: they close in **reverse** order.
5. **"If opening the second resource fails, the first isn't closed."** False for a first resource already initialized in the header.
6. **"If the second `close` throws, Java skips closing the first."** False: remaining opened resources are still closed.
7. **"A `close` error always overwrites a `read` error."** False in TWR; the `close` error becomes suppressed when a primary exists.
8. **"`getCause` and `getSuppressed` are the same."** False: cause chains and suppressed cleanup errors are distinct.
9. **"`Spy.closeCalls==1` guarantees zero OS descriptors remain."** False: use real/instrumented tests where required.
10. **"Calling `close` twice is safe on every `AutoCloseable`."** False: `AutoCloseable` does not mandate idempotence.
11. **"Closing `BufferedInputStream` doesn't affect the underlying stream."** Wrappers normally close their source; know ownership.
12. **"A terminal operation on `Files.lines` closes the stream automatically."** False: file-backed streams still require `close()`.
13. **"A constructor/factory throwing before returning is always cleaned up by TWR."** False: partially opened resources not yet handed to TWR must be cleaned up by the factory.
14. **"Being able to delete the file proves the stream was closed."** False on OSes with unlink semantics for open files.
15. **"`Thread.sleep(100)` is enough to test async close."** Non-deterministic; use synchronization and deadlines.
16. **"`close()` cannot throw `IOException`."** False: output flushing and finalization especially can fail.
17. **"Catching and returning `null` is a safe way to handle I/O errors."** Usually loses context and fakes success.
18. **"Closing a listener automatically closes all accepted channels."** Never assume this; every channel needs explicit ownership.

## 18. Self-Check Questions

**Q1.** In TWR with two resources `A` and `B`, the body throws `IOException("read")` and `B.close()` throws `IOException("close")`. What exception does the caller see?

**Answer:** `"read"` is primary; `"close"` is inside `getSuppressed()`. Java still attempts to close `A`.

**Q2.** Resource `A` opens successfully, but initializing `B` throws `IOException`. Does `A` close?

**Answer:** Yes, if `A` was already initialized in the TWR header. The body does not run, and `B`'s initialization exception is primary.

**Q3.** If a method executes `return` inside TWR, does `close` run before or after the method finishes returning?

**Answer:** `close` runs upon exiting scope before the method finishes returning. If `close` throws an exception, the method can complete abruptly with that exception instead of returning normally.

**Q4.** Why do unit tests using `CloseSpy` still need some integration tests?

**Answer:** A spy checks `close` calls against the fake's contract; it does not verify native handles, output finalization, or internal resources of real implementations.

**Q5.** Why is `Files.lines(path).count()` not enough to ensure the file is closed?

**Answer:** Terminal operations process elements without guaranteeing closure of the file-backed stream. Wrap the returned stream in TWR.

**Q6.** A service wraps `System.in` in `BufferedInputStream`. Should the service close the wrapper by default when done?

**Answer:** You cannot decide without knowing ownership. Closing the wrapper typically closes the underlying source; for shared `System.in`, design borrowed ownership or an explicit close shield.

**Q7.** An object's close handler can throw `IOException`. What should unit tests check besides `closeCalls`?

**Answer:** Check primary vs. suppressed exceptions, close ordering of other resources, and whether the method propagates errors per contract.

**Q8.** When an async I/O callback is pending and code requests shutdown, when can you conclude cleanup is complete?

**Answer:** Only after cancellation/completion policies and channel/resource closure are confirmed via synchronization signals with a deadline—never merely because the shutdown-request method returned.

### Official Java 17 Documentation

- [JLS `14.20.3 — try-with-resources](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3)
- [AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html)
- [Closeable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Closeable.html)
- [Throwable.getSuppressed](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html#getSuppressed())
- [Files — lines, list, walk](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [BufferedInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedInputStream.html)
- [FileChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html)
- [ZipFile](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipFile.html)
