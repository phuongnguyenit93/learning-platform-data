# GC Reclaiming Memory Is Different from Closing Files, Sockets, and External Resources

## 1. Main Thesis: A Dead Object Does Not Mean the External Resource Is Closed

In Java, the **garbage collector (GC)** manages the reusability of **memory of Java objects** that the program no longer needs according to reachability rules. However, a Java object may only be a **wrapper** for a resource outside the Java heap, such as:

- A file descriptor or OS handle of a file.
- Sockets and TCP connections.
- Database connections or cursors/statements/result sets.
- Direct/native buffers, native allocations, or file mappings.
- Processes, executors, thread pools, and objects tied to a task's lifecycle.
- Locks, listener registrations, timers, and native library resources.

**GC is not a deterministic resource-closing API.** A Java object may have exited its lexical scope, lost all references, or become eligible for collection, while the file is still open, the TCP connection still exists, the native allocation has not been reclaimed, or the transaction has not been rolled back/committed.

Example:

```java
void readFile(Path file) throws IOException {
    InputStream stream = Files.newInputStream(file);
    int firstByte = stream.read();
    // Do not call close() and do not use try-with-resources.
}
```

This is **illustrative code** and must be placed inside a class with the appropriate imports declared. The local variable `stream` is no longer used after the method, but **Java does not guarantee that the file descriptor will be closed immediately when the method returns**. Some implementations/libraries have a Cleaner mechanism or fallback release; that is not a reason to rely on GC instead of `close()`.

How it should be written:

```java
void readFile(Path file) throws IOException {
    try (InputStream stream = Files.newInputStream(file)) {
        int firstByte = stream.read();
        // Process the result.
    }
}
```

`try-with-resources` establishes an **ordered closing path following Java's control flow**, whether the block completes normally or via an exception.

**Distinguish three questions:**

1. **Is the object still strongly reachable?** → related to GC and reachability.
2. **Is the external resource still open/allocated?** → depends on the API/OS and the resource's state.
3. **Who is responsible for calling close/release/rollback/shutdown?** → this is the **ownership contract** of the application and library.

Questions 2 or 3 cannot be answered from question 1 alone.

## 2. Map of Heap Memory and External Resources

```text
               Java heap                     OS / native
        +---------------------+             +-------------------------+
        | FileInputStream     | --handle--> | File descriptor/handle  |
        | or FileChannel      |             | open file               |
        +---------------------+             +-------------------------+

        +---------------------+             +-------------------------+
        | Socket Java object  | --handle--> | TCP socket kernel state |
        +---------------------+             +-------------------------+

        +---------------------+             +-------------------------+
        | Connection wrapper  | --owns?---> | DB session / pool slot  |
        +---------------------+             +-------------------------+

        +---------------------+             +-------------------------+
        | Native buffer owner | --owns?---> | Native bytes / mapping  |
        +---------------------+             +-------------------------+
```

The diagram shows **responsibility relationships**, not asserting that every resource always has a single wrapper or a separate OS handle: libraries can share descriptors, manage connection pools, reuse channels, or use multiple native structures.

### 2.1. The Java Heap Is Managed by GC

According to **JVMS §2.5.3**, the heap is used to allocate class instances and arrays. The VM uses automatic storage management to reclaim heap storage of objects that are no longer needed. The garbage collector can run according to its own policy; `System.gc()` does not provide a portable deadline for all unused objects to be reclaimed.

What GC **cannot infer on its own from an arbitrary object type** is "resolve a transaction", "flush business data", "send a protocol close frame", "return a connection pool slot by the deadline", or "close a file handle at the requested time".

### 2.2. External Resources Have Their Own Limits

For example, the operating system may limit the number of file descriptors for a process. An application holding thousands of unclosed sockets can encounter errors like **too many open files** or resource exhaustion even when the Java heap still has plenty of space.

A connection pool can run out of connections even though the heap still has free space. A native allocation can cause the process RSS to grow beyond the Java heap memory. **Increasing `-Xmx` does not automatically fix an external resource leak** and sometimes makes the container's native memory budget even scarcer.

### 2.3. Each Type of "Release" Has Different Effects

| Action | Direct impact | Does not automatically guarantee |
| --- | --- | --- |
| Dropping a local reference | Removes one reference edge in the Java graph | Immediate object GC; automatic closing of socket/file |
| `System.gc()` | Suggests the runtime perform GC | Any given resource will be closed before a deadline |
| `close()` | Executes the closing contract of the corresponding resource | Immediate freeing of the Java heap object |
| `shutdown()` of an executor | Starts the shutdown process per the API | All tasks have finished immediately |
| `commit()` / `rollback()` | Controls the transaction per JDBC/database | Immediate GC of the connection wrapper |
| `Files.delete(...)` | Requests deletion of the directory entry/file per the OS | All related open handles close automatically or have the same semantics across all OSes |

**What needs to be designed is state/lifecycle**, not just the number of bytes used.

## 3. Scope, Reachability, and Resource Lifetime Are Three Independent Axes

Consider:

```java
InputStream in = Files.newInputStream(path);
try {
    consume(in);
} finally {
    in.close();
}
```

This is **illustrative code**, requiring `path`, `consume`, imports, and application-specific exception handling. In this snippet:

- The local variable `in` has its own **scope**.
- The stream object has its own **reachability**; it could still be held in another method or by a field if the code shares the reference.
- The file descriptor has an **open/closed state** per the API/OS; calling `close()` actively transitions the lifecycle through the closing step.

You can proactively **close a resource while the Java wrapper object is still strongly reachable**, for example `in.close(); System.out.println(in != null);`. The variable `in` still holds a reference value; this does not mean the file is still open.

Conversely, you can drop all local references to a wrapper without any guarantee that the external resource has been closed by a deadline.

### 3.1. Object Still Alive While Resource Is Closed

```java
InputStream stream = Files.newInputStream(path);
stream.close();
boolean wrapperStillReferenced = stream != null;
```

`wrapperStillReferenced` is true when the code completes normally. However, the stream resource has already been requested to close. **Object memory lifetime ≠ resource open state**.

Some APIs allow calling `close` repeatedly; some APIs/implementations have their own behavior. Do not equate "wrapper is still alive" with "resource can continue to be validly used".

### 3.2. Object Out of Scope While Resource May Still Be Open

```java
static void openAndForget(Path path) throws IOException {
    InputStream stream = Files.newInputStream(path);
    stream.read();
    // No close.
}
```

This is an **anti-pattern**. After returning, one should not assume the OS handle has been released. Some libraries provide fallback cleanup via reference processing, but the timing of GC/cleaner is non-deterministic; resource ownership must not be designed around that chance.

### 3.3. Reference Still Alive While Resource Is No Longer Usable

A closed socket/stream/DB connection can still be a normal Java object. However, calling read/write/query after closing can throw an exception or behave according to the corresponding API.

**Do not use `object != null` as the sole check that a resource is still open.** State and errors must be obtained from the resource's contract.

## 4. Why Cannot Finalization Be a Reliable Strategy for Closing Files/Sockets?

Finalization previously allowed a class to override `finalize()` to execute code when the runtime detected a special condition related to object reachability. This mechanism has many problems:

- There is no deadline for when GC detects that an object needs processing.
- Finalizers can be slow and may not run before the process exits.
- There are risks of delayed memory reclamation, deadlocks, security/concurrency issues, and object resurrection.
- Newer runtimes may disable or remove the feature.
- Finalizers do not have a reliable business transaction mechanism to ensure data has been flushed/committed.

**JEP 421** deprecates finalization for removal starting in JDK 18. New code should not write `finalize` to close file descriptors, network sessions, or database connections. Use `try-with-resources`/`AutoCloseable` or an explicit lifecycle instead.

### 4.1. Running a Finalizer Does Not Mean Resource Logic Is Complete

Closing a file can fail with `IOException`; a transaction may need rollback/commit according to rules; network close may depend on protocol and peer state. These situations require an **error-handling flow controlled by the caller**.

If relying only on finalization, the caller has no clear point to receive and handle close errors before returning a business result.

## 5. `AutoCloseable` and `Closeable` — The Language of Ownership

**`AutoCloseable`** provides the `close()` method:

```java
public interface AutoCloseable {
    void close() throws Exception;
}
```

`java.io.Closeable` extends `AutoCloseable` with a `close()` contract suitable for I/O (typically declaring `IOException`). Not every AutoCloseable is a Closeable; not every `close` has the same idempotency semantics or exception type.

### 5.1. What Does `try-with-resources` Do?

With:

```java
try (Resource resource = open()) {
    use(resource);
}
```

The Java compiler ensures `close()` is called upon exiting the body if the resource was created successfully, **even if the body throws an exception**. When there are multiple resources, they are closed **in reverse order of initialization**.

This snippet is only a **structural pattern**; `Resource`, `open`, and `use` must be declared accordingly. The standalone hands-on example in the next section uses a real file to verify this.

### 5.2. Do Not Understand `AutoCloseable` as a Java Destructor

- `close()` only does what the API/implementation specifies.
- The Java object can still exist after `close()`.
- `close()` may flush/rollback/return a pool resource/release a native handle depending on each API.
- An `AutoCloseable` may not own any native resource; it can still manage logical lifecycle.
- `try-with-resources` does not force GC to run.

### 5.3. Ownership Must Be Defined

When a method receives an `InputStream` from a caller, distinguish:

- **Callee owns:** the method is responsible for closing it after use.
- **Caller owns:** the method only borrows the stream and does not close it, unless the API contract states otherwise.

Example:

```java
static byte[] readWithoutClosing(InputStream borrowed)
        throws IOException {
    return borrowed.readAllBytes();
}
```

This is an **illustrative method**. The caller is responsible for closing the stream if it owns the resource. Having the callee close it on its own can break the caller's subsequent operations. Naming/documentation must clearly state ownership; not every method that sees an `InputStream` should call `close`.

## 6. Complete Java 17+ Example: Real File, Reverse-Order Close, Suppressed Exception

Create the file **`ResourceLifecycleDemo.java`**:

```java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class ResourceLifecycleDemo {
    static final class Tracked implements AutoCloseable {
        private final String name;
        private boolean closed;

        Tracked(String name) {
            this.name = name;
        }

        void use() {
            System.out.println("using " + name);
        }

        @Override
        public void close() {
            if (!closed) {
                closed = true;
                System.out.println("closed " + name);
            }
        }
    }

    static final class FailingClose implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close failed");
        }
    }

    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("resource-lifecycle-", ".txt");

        try {
            try (BufferedWriter writer =
                         Files.newBufferedWriter(file, StandardCharsets.UTF_8)) {
                writer.write("Hello JVM");
            }

            try (BufferedReader reader =
                         Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
                System.out.println("file content: " + reader.readLine());
            }
        } finally {
            Files.deleteIfExists(file);
        }

        try (Tracked first = new Tracked("first");
             Tracked second = new Tracked("second")) {
            first.use();
            second.use();
        }

        try (FailingClose failing = new FailingClose()) {
            throw new IllegalStateException("body failed");
        } catch (IllegalStateException error) {
            System.out.println("primary: " + error.getMessage());
            System.out.println("suppressed count: "
                    + error.getSuppressed().length);
            System.out.println("suppressed type: "
                    + error.getSuppressed()[0]
                            .getClass().getSimpleName());
        }

        System.out.println("done");
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac --release 17 ResourceLifecycleDemo.java
java ResourceLifecycleDemo
```

**Exact stdout in a normal run**, when having permission to create/read/delete temporary files in the system temp directory:

```text
file content: Hello JVM
using first
using second
closed second
closed first
primary: body failed
suppressed count: 1
suppressed type: IOException
done
```

The example was checked with `javac --release 17` and run on OpenJDK 21, and stdout matches. The program uses a real temporary file via `Files.createTempFile` and does not print random paths, so that output is stable across runs with a valid I/O environment.

### 6.1. The File I/O Part Resolves the Resource Lifecycle

`Files.newBufferedWriter` opens a writer, writes `Hello JVM`, and try-with-resources closes the writer when the block ends; closing the writer also ensures appropriate flush/close operations per the API contract. Afterward, the reader is opened separately, reads the line, and closes.

`Files.deleteIfExists(file)` in `finally` deletes the temporary file whether the I/O operations succeed or throw an exception (subject to file system error limits). No line has to call `System.gc()` to complete the file's lifecycle.

**Note:** `deleteIfExists` does not always succeed; for example, `IOException` can occur due to access permissions/file system. The "exact stdout" condition above applies **when temporary file operations succeed normally**, and does not assert that every sandbox environment permits I/O.

### 6.2. `close()` Occurs in Reverse Order

Two resources:

```java
try (Tracked first = new Tracked("first");
     Tracked second = new Tracked("second")) {
    first.use();
    second.use();
}
```

are created in the order `first` then `second`. Upon exiting the block, the compiler closes `second` before `first`:

```text
using first
using second
closed second
closed first
```

Reverse order is especially useful when the second resource depends on the first resource; for example, a buffering wrapper wrapping an underlying stream. However, if two wrappers **point to the same underlying resource**, the ownership contract must be understood separately to avoid duplicate closing or premature closing.

### 6.3. `close()` Can Throw an Exception When the Body Has Already Failed

In the example:

```java
try (FailingClose failing = new FailingClose()) {
    throw new IllegalStateException("body failed");
}
```

When exiting the body, Java still calls `FailingClose.close()`. `close` throws `IOException("close failed")`, but because **the body already has a primary exception** `IllegalStateException("body failed")`, the exception from close is attached to the **suppressed exceptions** array of the primary exception.

Therefore, the output shows:

```text
primary: body failed
suppressed count: 1
suppressed type: IOException
```

**Do not lose suppressed exceptions when debugging.** They can contain information that a file/socket/channel did not close cleanly even though the primary error originated from content processing.

### 6.4. When Both the Body and `close` Succeed

`close` is still called, but without an exception. The program does not need and should not use `System.gc()` just to "trigger" closing the file.

## 7. Exceptions, Closing Order, and Partial Acquisition

`try-with-resources` solves tricky corners of cleanup:

### 7.1. Second Resource Fails to Open

```java
try (InputStream first = openFirst();
     InputStream second = openSecond()) {
    use(first, second);
}
```

This is illustrative code, not standalone. If `openFirst()` succeeds but `openSecond()` throws an exception, Java will **close `first` which was already successfully initialized**. This is an advantage over code that opens multiple resources and only calls `close` at the end of the body.

### 7.2. Multiple `close` Calls Throw Errors

Resources are closed in reverse order; if the body already threw an error, errors in close are **suppressed** appropriately. If the body completes normally but a close throws an error, the error from close can become the primary exception. With multiple close errors, subsequent errors can be suppressed onto the primary error according to Java rules.

Therefore, one cannot infer that all `close` failure cases are swallowed; one must inspect the exception chain and `getSuppressed()`.

### 7.3. Do Not Replace `try-with-resources` with an Incorrect `finally`

An example that easily loses information:

```java
Resource r = open();
try {
    doWork(r);
} finally {
    r.close(); // If this also throws, it risks masking the original error.
}
```

This is non-standalone illustrative code. When possible, `try-with-resources` helps Java preserve the primary/suppressed exception relationship better than a hand-written finally block that has not accounted for all error scenarios.

### 7.4. Do Not Catch All Errors and Continue as If Closing Succeeded

An `IOException` from `close` can signal a failed flush, lost connection, disk corruption, or another I/O failure. The right handling depends on business logic: propagate, bounded retry, mark transaction failed, report error, or log with context.

Do not do:

```java
try {
    resource.close();
} catch (Exception ignored) {
    // Always treat as success: anti-pattern.
}
```

The code above is an **illustrative anti-pattern**, not a recommended rule.

## 8. Files, Streams, and Channels: Closing the Right Owning Object

### 8.1. `InputStream`, `OutputStream`, `Reader`, `Writer`

Streams/writers typically represent reading/writing capabilities. Closing:

- Ends usage of the resource per the API contract.
- May flush appropriate buffers before release.
- May transition the OS handle to a closed state.
- May throw an exception; must be handled.

If using `BufferedInputStream` wrapping another stream, it is necessary to determine whether the wrapper owns the underlying stream. In typical APIs, closing the wrapper also closes the underlying stream; if the underlying stream is still used elsewhere, closing the wrapper can break the caller.

### 8.2. `FileChannel` and `SeekableByteChannel`

`FileChannel` is a `Channel` and has `close()` per the API. Use try-with-resources:

```java
try (java.nio.channels.FileChannel channel =
         java.nio.channels.FileChannel.open(path,
                 java.nio.file.StandardOpenOption.READ)) {
    long size = channel.size();
    // Process size.
}
```

This is **illustrative code**, with `path` declared in context. Closing a channel is a lifecycle operation independent of the GC heap object.

### 8.3. `MappedByteBuffer` and Mapped Memory

Memory-mapped files are more complex because mappings and OS pages have their own lifecycle. Using `FileChannel.map` can create a mapped buffer; **closing the FileChannel does not mean all mappings are unmapped immediately** in every situation.

Do not promise "try-with-resources for a channel will immediately unmap all still-reachable buffers". The lifecycle of a mapping also depends on the buffer, JVM/OS, and supporting APIs. If deterministic unmapping is needed, design via the appropriate API of the target JDK rather than using non-portable private `Unsafe` tricks.

### 8.4. Flush Is Not Close, and Close Is Not Universal fsync

- `flush()` typically requests pushing buffered data to the underlying layer, per the API.
- `close()` ends resource usage, sometimes flushing before release.
- Ensuring data is truly **durable** on the storage device is a different issue, which may require APIs such as `FileChannel.force` and consideration of OS/file system contracts.

Do not confuse "file descriptor finished closing" with "every byte is guaranteed permanently written regardless of power loss".

## 9. Sockets: Java Wrapper Lifetime Differs from TCP Connection

A `java.net.Socket` typically represents a TCP endpoint. When a socket is connected, the OS holds network state, buffers, and descriptors outside the Java heap.

### 9.1. Proactively Closing Sockets

Illustrative Java source example:

```java
import java.net.Socket;

try (Socket socket = new Socket("example.com", 443)) {
    socket.setSoTimeout(5000);
    // Communicate according to the corresponding protocol.
}
```

**Not a standalone program**: requires appropriate method/exception handling, network access, and a valid protocol. Do not treat the example as a complete HTTP/TLS client because a TCP connection to port 443 does not automatically perform a TLS handshake or HTTP request.

When the try block ends, `Socket.close()` is called per contract. GC is not an agent used to ensure sockets close on time.

### 9.2. Closing a Socket Is Not Confirmation That Data Reached the Peer

TCP is a stateful protocol. `close()` initiates/completes local-side closing operations per the API/OS, but **does not automatically become a business-level ACK** that the server has processed the transaction or written data to the database.

To confirm successful processing, the application needs a protocol response, timeout, and an appropriate retry/idempotency strategy.

### 9.3. `shutdownInput`, `shutdownOutput` Differ from `close`

`shutdownOutput()` and `shutdownInput()` have a socket **half-close** contract in supported cases; they should not arbitrarily be treated as equivalent to `Socket.close()`.

A streaming application sometimes needs to signal that it has finished sending data using half-close while still reading the response. If close is called too early, it can break the protocol flow.

### 9.4. Socket Timeout Does Not Replace Resource Cleanup

`setSoTimeout` adjusts the read wait time per the API, helping avoid certain indefinite blocking reads. However, a timeout does not automatically close the socket, nor does it clean up listeners or close connection pools when a request ends. Cleanup and timeout are **two complementary layers of protection**.

### 9.5. `ServerSocket` Also Needs Close

`ServerSocket` can hold a bound port and an OS descriptor. A server socket variable going out of scope does not promise the port is released immediately. Use try-with-resources and explicit shutdown/cancellation for the accept loop when appropriate.

## 10. JDBC: `Connection.close()` May Return to the Pool, Not Close the Real TCP Connection

In production applications, database connections typically go through a **connection pool**. A call:

```java
try (java.sql.Connection connection =
         dataSource.getConnection()) {
    // Use connection.
}
```

is an **illustrative code snippet**, where `dataSource` must be configured. With a connection wrapper from a pool, `close()` usually means **returning the logical connection to the pool** after handling appropriate state, not necessarily destroying the underlying physical socket.

This is a classic example that:

> **The closing contract of a resource must not be inferred from the Java type name, but must be read from the provider's documentation and ownership model.**

### 10.1. Close `ResultSet` and `Statement` as Well When Owned

```java
try (Connection c = dataSource.getConnection();
     PreparedStatement p =
             c.prepareStatement("SELECT name FROM users WHERE id = ?")) {
    p.setLong(1, userId);
    try (ResultSet rs = p.executeQuery()) {
        if (rs.next()) {
            String name = rs.getString(1);
            // Process name.
        }
    }
}
```

This is illustrative code, requiring `dataSource`, `userId`, and appropriate imports/drivers. Scope-based closing helps avoid holding cursors, statements, or connection pool slots unnecessarily.

### 10.2. Transaction Lifecycle Differs from GC

A transaction needs clear logic:

- `commit()` when business logic succeeds and conditions are met.
- `rollback()` when encountering an error or validation failure.
- `close()`/return connection per the provider contract.

**Do not assume "GC has reclaimed the Connection object" means the transaction has committed.** Closing a connection may roll back the transaction depending on driver/pool/DB behavior, but it does not replace an explicit transaction decision.

### 10.3. Connection Pool Exhaustion

An endpoint forgetting to call close can exhaust the pool's available connections. At that point, the system can hang waiting or time out even though **the Java heap still has plenty of memory**.

Pool metrics must be monitored: active, idle, pending acquisition, timeout, connection age, and release behavior. GC logs are not enough to prove the pool lifecycle is correct.

## 11. Executors, Threads, and Processes: "Closing" Is Not a Single Common Operation

Not every resource has an exact method named `close` or the same contract:

| Resource | Commonly used lifecycle API | Notes |
| --- | --- | --- |
| `InputStream` / `Reader` | `close()` | May throw `IOException` |
| `FileChannel` | `close()` | File/channel ownership |
| `Socket` / `ServerSocket` | `close()` | OS socket and protocol semantics |
| JDBC `Connection` | `close()` | May return connection to pool |
| JDBC `Statement`, `ResultSet` | `close()` | Often needs nested try-with-resources |
| `ExecutorService` | `shutdown()`, `shutdownNow()`, `awaitTermination()` | Stops accepting tasks and waits for tasks to finish per API |
| `Process` | `destroy()`, `destroyForcibly()`, `waitFor()` | Controls child process, not GC |
| Application listener/registration | `removeListener`, `unregister` | Must cut off callback source at end of lifecycle |
| `ThreadLocal` | `remove()` | Avoids retaining request state across pool tasks |
| Lock/semaphore | `unlock()` / `release()` | Balances acquire/release, not heap free |

**Version note:** JDK 17 `ExecutorService` primarily uses `shutdown`/`awaitTermination`; do not blindly apply utilities or try-with-resources usages added to the interface in newer JDKs to `--release 17` code.

### 11.1. Proper Executor Shutdown

```java
ExecutorService pool = Executors.newFixedThreadPool(2);
try {
    // Submit work and process results per contract.
} finally {
    pool.shutdown();
    if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
        pool.shutdownNow();
    }
}
```

This is illustrative code, requiring imports and `InterruptedException` handling. `shutdown()` is a request to stop accepting new work and give existing tasks a chance to complete; it **does not immediately guarantee all threads have died**. `awaitTermination` helps the caller wait with a bound. `shutdownNow` attempts to interrupt via the corresponding mechanism, without guaranteeing to kill every task regardless of whether it responds to interruption.

### 11.2. ThreadLocal Retention

A worker thread in a pool can live across thousands of requests. Even though the request's local variables have gone out of scope, `ThreadLocal` values can still be retained via the thread-local map.

```java
try {
    CONTEXT.set(requestContext);
    handleRequest();
} finally {
    CONTEXT.remove();
}
```

The code above is an **illustrative pattern**, requiring definitions for `CONTEXT`, `requestContext`, and `handleRequest`. `remove()` is cleanup of the **logical request scope**, not a command requesting GC.

## 12. `Cleaner`: Fallback Cleanup When an Object Becomes Phantom Reachable

Java 9+ has `java.lang.ref.Cleaner` to register a cleaning action corresponding to an object. Cleaner relies on **`PhantomReference` and `ReferenceQueue`** to detect reachability changes.

Three points must be understood:

1. The cleaning action is run when GC/reference processing reports the object has become **phantom reachable**, or when code **explicitly calls `Cleanable.clean()`**.
2. **There is no guaranteed deadline** when the action is triggered by GC; before the process exits, it may not have run yet.
3. **The action must not hold a strong reference to the registered object**, otherwise the object may not become phantom reachable and the automatic cleaner will not be triggered.

Therefore, **Cleaner is a safety net**, not a replacement for `try-with-resources` or explicit close for files/sockets/DBs that need timely release.

### 12.1. Safe Pattern Example

```java
import java.lang.ref.Cleaner;

final class NativeHandle implements AutoCloseable {
    private static final Cleaner CLEANER = Cleaner.create();

    private static final class State implements Runnable {
        private boolean cleaned;

        @Override
        public synchronized void run() {
            if (cleaned) return;
            cleaned = true;
            // Release native handle owned by State.
        }
    }

    private final State state = new State();
    private final Cleaner.Cleanable cleanable =
            CLEANER.register(this, state);

    @Override
    public void close() {
        cleanable.clean();
    }
}
```

This is an **illustrative class**, not actually allocating a native handle. `State` is declared `static` so it does not capture `NativeHandle.this`. In real code, `State` must hold enough data to release the resource, but **must not accidentally hold the wrapper referent itself**.

**Do not register `this::cleanup` or a lambda using fields of `this` as a cleaning action** if it holds a strong reference to the referent, because this can prevent GC-based cleanup.

## 13. Complete Java 17+ Example: Calling Cleaner Proactively Without Waiting for GC

Create the file **`CleanerSafetyDemo.java`**:

```java
import java.lang.ref.Cleaner;
import java.util.concurrent.atomic.AtomicBoolean;

public final class CleanerSafetyDemo implements AutoCloseable {
    private static final Cleaner CLEANER = Cleaner.create();

    private static final class State implements Runnable {
        private final AtomicBoolean cleaned = new AtomicBoolean();

        @Override
        public void run() {
            if (cleaned.compareAndSet(false, true)) {
                System.out.println("cleaned once");
            }
        }
    }

    private final Cleaner.Cleanable cleanable =
            CLEANER.register(this, new State());

    void use() {
        System.out.println("using wrapper");
    }

    @Override
    public void close() {
        cleanable.clean();
    }

    public static void main(String[] args) {
        try (CleanerSafetyDemo resource = new CleanerSafetyDemo()) {
            resource.use();
        }
        System.out.println("explicit close finished");
    }
}
```

Run:

```bash
javac --release 17 CleanerSafetyDemo.java
java CleanerSafetyDemo
```

**Exact stdout:**

```text
using wrapper
cleaned once
explicit close finished
```

The example was compiled with `--release 17` and run successfully on OpenJDK 21.

Explanation:

- `Cleaner.register(this, new State())` registers the wrapper as the referent and a `State` **that does not reference the wrapper**.
- `try-with-resources` proactively calls `close()`.
- `close()` calls `cleanable.clean()`, so the action runs via the **explicit** path and prints `cleaned once` before the block finishes.
- The code **does not call GC** and does not wait for phantom reachability; therefore, stdout does not depend on GC scheduling.
- `AtomicBoolean` makes the action behavior idempotent in the demo; per the Cleaner contract, a cleanable action is executed at most once via the appropriate mechanism.
- The demo **does not manage a real OS handle**, only demonstrating the relationship between close and Cleaner. Real resources need accurate release logic and separate error handling.

### 13.1. Why Should Cleaner Not Be Used for Critical Transactions?

If the program forgets `close()`, an action depending on GC may only run late or fail to run before the process exits. Transactions cannot rely on "commit/rollback when the object becomes phantom reachable" to achieve consistency by a deadline.

## 14. `Reference.reachabilityFence` and Native Resource Wrappers

A subtle case arises when a Java wrapper owns a native handle, but the native operation only takes a numeric value such as an address/handle:

```java
static void perform(NativeWrapper owner) {
    long handle = owner.handle();
    nativeCall(handle);
    java.lang.ref.Reference.reachabilityFence(owner);
}
```

This is **illustrative code**; `NativeWrapper` and `nativeCall` are not declared. The compiler/JIT may notice that `owner` itself is no longer used via a Java reference in the native operation after obtaining `handle`, while the cleaning mechanism could release the native handle if the wrapper becomes phantom reachable too early.

`Reference.reachabilityFence(owner)` ensures **the object remains strongly reachable at least until after this invocation**, helping prevent some cases of premature cleanup while the native operation is still using the handle.

However, it:

- Does not call `close()`.
- Does not call `System.gc()`.
- Does not pin the object at an immutable heap address.
- Does not solve the problem of another thread proactively calling `close()` concurrently.
- Does not replace an ownership protocol with appropriate synchronization.

For ordinary Java file streams, **try-with-resources** is usually the better abstraction; `reachabilityFence` is particularly suitable in carefully designed native-resource wrapper layers.

## 15. Native/Off-Heap Buffers Have Their Own Lifecycle

Some APIs allocate memory **outside the Java heap**, such as direct buffers or native allocations. The Java heap bytes visible in a profiler can be smaller than the process's total RSS.

### 15.1. `ByteBuffer.allocateDirect`

```java
java.nio.ByteBuffer direct =
        java.nio.ByteBuffer.allocateDirect(1024 * 1024);
```

This is illustrative code. A direct buffer holds a memory region that the VM tries to support for efficient I/O/native access, rather than a regular Java heap `byte[]` array.

The ability to reclaim native memory of a direct buffer depends on the VM and buffer/reference processing mechanisms. **There is no standard `close()` on every `ByteBuffer`** for an application to call like `InputStream`.

For resources demanding a deterministic lifecycle, choose APIs that support **explicit ownership/release** in the target JDK, such as Foreign Function & Memory API constructs if using a JDK with stable support. Do not use private `Unsafe.invokeCleaner` as a portable Java SE promise.

### 15.2. `FileChannel.map` / Mapped Buffers

Mapped memory can persist after the channel closes. Although closing the channel releases resources per the API, memory mapping has its own semantics/lifetime. Do not treat GC of the Java wrapper or closing the channel as proof that the mapping was unmapped at the exact right time.

### 15.3. High RSS Does Not Mean a Heap Leak

When a container is killed for exceeding its memory limit, also check:

- Heap used/committed and GC.
- Metaspace/class metadata.
- Native allocations, direct/mapped buffers.
- Thread stacks.
- Code cache, VM/GC native structures.
- File/socket handles and other resource consequences.

This is an extension to explain **off-heap**, and does not mean every FD leak automatically increases RSS at the same rate; FD count and heap/RSS are independent metrics.

## 16. Idempotency, Thread Safety, and Closing Multiple Times

Do not assume all `close()` methods of every `AutoCloseable` have the same semantics. Some resources are designed with **idempotent close**; some have their own state or exception behavior.

In application code you write yourself, you can prefer an idempotent `close` if it fits the contract:

```java
final class Gate implements AutoCloseable {
    private boolean closed;

    @Override
    public void close() {
        if (closed) return;
        closed = true;
        releaseOwnedResource();
    }
}
```

This is **illustrative code**, with `releaseOwnedResource` undefined. With multiple threads, a `closed` variable without proper synchronization **is not enough to guarantee thread-safe close**. One must plan a state machine, atomic/synchronized operations, and avoid use-after-close and double-free.

### 16.1. Concurrent Close with Read/Write

If one thread is using a socket/channel and another thread calls close, the result depends on the API (it may throw an exception/cancel blocking I/O). Do not treat GC or a simple `volatile boolean closed` as a solution for concurrency correctness.

In low-level native APIs, use-after-free can even cause severe errors. Ownership rules must define who is borrowing the handle and when there is permission to release it.

### 16.2. Nested Resources and Shared Underlying Handles

If two wrappers are created that share ownership of an underlying stream, closing one wrapper can make the other wrapper unusable. Do not assume "closing each wrapper once" is always right when there is **shared ownership**.

When you actually want the stream to remain open for the caller, use an API with a clear borrowing/lending contract or a purpose-built non-closing wrapper, instead of silently omitting close and hoping GC cleans it up.

## 17. Distinguishing Resource Leaks and Memory Leaks

| Phenomenon | Common symptoms | What to inspect |
| --- | --- | --- |
| **Java heap retention/leak** | Live heap or retained object graph grows | GC roots, static collections, caches, ThreadLocal |
| **File descriptor leak** | OS FD count grows, unable to open new files/sockets | Unclosed open paths, resource ownership |
| **Socket/connection leak** | TCP connections/active pool grows, timeouts when acquiring connections | `Socket.close()`, pool metrics, protocol/lifecycle |
| **Native memory leak** | RSS/native allocation grows outside heap | Direct buffers, JNI/native allocations, NMT |
| **Thread leak** | Threads live unnecessarily long, stack memory grows | Executor shutdown, task cancellation |
| **Database cursor leak** | Cursor/statement resource exhaustion | `ResultSet`, `Statement`, driver/pool semantics |
| **Mapped memory retention** | Memory mappings/handles persist | Mapped buffers and unmap/lifecycle APIs |
| **Class loader retention** | Metaspace/class counts grow after redeploy | Loader references, reflection caches, listeners |

A resource leak can lead to memory pressure, but **does not necessarily manifest first as `OutOfMemoryError: Java heap space`**. A heap leak is also not necessarily related to FD count.

**Do not use "GC logs look normal" to rule out a resource leak.** GC logs observe memory-management behavior, not count every held external resource.

## 18. Diagnostics on the JVM and Operating System

### 18.1. Counting File Descriptors

On Linux, you can view the OS-level FD count with tools like `lsof` or `/proc/<pid>/fd` (depending on permissions/container):

```bash
lsof -p <pid>
ls /proc/<pid>/fd
```

`<pid>` is a placeholder; replace it with the actual PID of the Java process. These are observation commands for diagnostics; they are not behavior to be run inside a Java program.

**Not every platform has `/proc` or `lsof`.** Windows has its own handles/process monitoring tools; do not transfer Linux commands to Windows and expect them to work.

### 18.2. Monitoring Pools and Sockets

- Database connection pool: active/idle/pending/timeouts.
- HTTP client connection pool: leased/idle/available connections.
- Server sockets: accepted connections, close timing, number of concurrent connections.
- OS socket states: established, close-wait, time-wait… must be interpreted according to TCP semantics and the OS, not treating every `TIME_WAIT` as a leak.

For example, many prolonged `CLOSE_WAIT` states may suggest the local side has not closed the socket after the peer closed, but this must be cross-checked against application behavior and the operating system.

### 18.3. JVM Tools

On HotSpot JDK, you can use:

```bash
jcmd -l
jcmd <pid> GC.class_histogram
jcmd <pid> Thread.print
```

To view native memory via NMT if enabled from startup:

```bash
jcmd <pid> VM.native_memory summary
```

**NMT is not an FD/socket counter.** It tracks many categories of VM native allocations, not necessarily including all external native libraries or the lifecycle of every connection.

`GC.class_histogram` shows the number of Java instances by type, but does not prove how many file handles remain unclosed. A `FileInputStream` object may still be in the heap while already closed; a provider may have its own pooling wrappers/handles.

### 18.4. Resource Telemetry Is More Important Than a Single Heap Dump

Monitor over time:

- FD/handle count.
- Socket count by state.
- Pool active/idle/waiting.
- Open-file/channel counts if the library exposes metrics.
- Heap allocated/live/committed and GC.
- Native/RSS memory.
- Rate of successful/failed closes.
- Latency and timeout of resource acquisition.

Use the same workload to compare before/after a fix. Do not conclude "leak fixed" just because a single snapshot has a low number.

### 18.5. Observing Whether Close Occurs in Every Control Path

A testing technique is to wrap the resource with a counting class:

```java
final class CloseCounter implements AutoCloseable {
    int closes;
    @Override
    public void close() { closes++; }
}
```

This is an illustrative snippet. It can be used in unit tests to verify cleanup even if the body throws an exception or returns early. With concurrency, use thread-safe counters if multiple threads operate on the same object.

## 19. An Easily Overlooked Case: HTTP Responses and Returned Streams

For example, an HTTP library allows accessing the **response body as a stream**. Even though the client object/response wrapper has a short scope, the body stream or response object may have to be closed per the documentation to:

- Return the connection to the pool.
- Avoid leaking the underlying socket.
- Allow connection reuse.
- Ensure chunked/body data is handled according to a valid policy.

With Java 11+ `java.net.http.HttpClient`, different body handlers have different lifecycles. In particular, if receiving the body as an `InputStream`, the caller needs to manage closing the stream per the API; do not infer solely from whether the `HttpClient` object has been GC'd.

An application can make thousands of HTTP requests yet hold response streams longer than needed, exhausting the connection pool before the Java heap runs out.

## 20. Designing Ownership by Layer

A clear architectural approach:

```text
Application startup
     |
     +--> create long-lived pools/clients
     |         |
     |         +--> shut down once on application stop
     |
     +--> each request / task
               |
               +--> borrow connection/stream
               |
               +--> try-with-resources
               |       |
               |       +--> process
               |       +--> commit/rollback per business logic
               |       +--> close / return pool slot
               |
               +--> return response
```

It is not mandatory to create/close a heavyweight client for every request. Some clients/pools are **designed to be reused** and must be closed at application shutdown, while sessions/connections/response streams have shorter scopes.

### 20.1. Checklist of Questions to Document in the API Contract

| Question | Example of required answer |
| --- | --- |
| Who creates the resource? | Factory or pool |
| Who owns it? | Caller, callee, application singleton |
| Who has permission to close it? | Owner or responsible wrapper |
| How is it closed? | `close`, `shutdown`, `rollback`, `cancel` |
| When is it closed? | End of request, end of transaction, application shutdown |
| What if close fails? | Propagate/log/retry/mark failure appropriately |
| Is concurrent use safe? | Per thread-safety documentation |
| Can it be reused after close? | Per each API's contract |
| Is there a Cleaner fallback? | Secondary protection only, do not rely on deadline |

### 20.2. Wrapping Resources in a Lifecycle-Aware Abstraction

If business code manipulates complex files/native handles, create a class that **implements `AutoCloseable`**, with a clear state machine and ownership documentation. Then callers use try-with-resources to close resources **predictably**, not as a collection event.

## 21. Common Misconceptions

### Misconception 1: "Java has GC so `close()` is unnecessary"
GC cleans the Java heap based on reachability, and does not guarantee closing every external resource on time.

### Misconception 2: "A variable leaving `{ }` means the OS file descriptor is released"
Lexical scope is not the deadline of an OS resource. Cleanup must be based on lifecycle/ownership.

### Misconception 3: "Setting stream = null closes the file"
Setting null only changes a reference edge. It does not force the library to call close or the OS to release the handle immediately.

### Misconception 4: "`System.gc()` is the standard way to clean up sockets"
No. GC scheduling is not a network resource release API.

### Misconception 5: "Once a resource is closed, the Java object must disappear"
The Java wrapper can still be reachable; close and reclaim are two different states.

### Misconception 6: "If the heap has plenty of capacity, we cannot run out of FDs"
FD pools/OS handles have independent limits.

### Misconception 7: "`close()` of a pooled JDBC connection definitely closes the physical TCP socket"
No. In a pool, close may mean returning the logical connection to the pool.

### Misconception 8: "try-with-resources only closes when the body succeeds"
False. Java calls close even when the body throws an exception or returns early; read primary/suppressed exception rules.

### Misconception 9: "A close exception always replaces the original exception"
No. try-with-resources has suppressed exceptions to preserve close failure information when the body already has a primary exception.

### Misconception 10: "Every `AutoCloseable.close` is idempotent and thread-safe"
No. Read the specific contract; write thread-safe `close` yourself when there is multi-thread ownership.

### Misconception 11: "Closing `FileChannel` always unmaps mapped buffers immediately"
There is no such portable guarantee.

### Misconception 12: "`Socket.close` confirms the remote server has committed"
No. TCP close does not replace application-level acknowledgement.

### Misconception 13: "Cleaner can replace transaction rollback/commit"
No. GC-triggered Cleaner has no deadline or transaction semantics.

### Misconception 14: "Making a Cleaner action call `this.close()` is safe"
It can hold a strong reference to the referent, causing the action to never run via the GC path. Separate State from the wrapper.

### Misconception 15: "Finalizers are guaranteed to run before shutdown"
No. Finalization is deprecated for removal and provides no progress guarantee.

### Misconception 16: "If the GC heap is stable, there is no native leak"
False. Native allocations, FD counts, and sockets are independent.

### Misconception 17: "`ThreadLocal` automatically clears when an HTTP request ends"
False. A worker thread can live across many requests; request-scope cleanup requires explicit remove.

### Misconception 18: "Close/cleanup errors can be ignored because GC will handle it again"
There is no guarantee GC will fix a failing resource state or run the cleanup logic properly an extra time.

## 22. Self-Check Exercises and Answers

**Question 1.** Why does `new FileInputStream(path)` creating a Java object not mean the file will close when the local variable goes out of scope?

**Answer:** Because the wrapper object and the OS file descriptor have different lifecycles. GC does not guarantee calling close automatically on time; use try-with-resources.

**Question 2.** When `InputStream.close()` runs successfully, is the Java wrapper GC'd immediately?

**Answer:** Not necessarily. The wrapper may still be reachable; close manages the resource rather than freeing the Java heap object.

**Question 3.** Two `AutoCloseable` resources are declared in the order `a` then `b` in try-with-resources. What is the close order?

**Answer:** `b.close()` before `a.close()`.

**Question 4.** The body throws `IllegalStateException`, and close throws `IOException`. With try-with-resources, which is the primary exception?

**Answer:** Normally `IllegalStateException` from the body is primary; `IOException` from close is stored in the primary's suppressed exceptions per the rules.

**Question 5.** Does `Connection.close()` in a JDBC pool necessarily close the physical socket?

**Answer:** No. The provider may return the logical connection to the pool; read the pool/driver documentation.

**Question 6.** The heap still has 300 MiB free, but the process fails to open new files due to the FD limit. Is increasing `-Xmx` the root solution?

**Answer:** No. Look for unclosed open file/socket handles, OS limits, and their lifecycle.

**Question 7.** Is `System.gc()` a reliable way to release sockets?

**Answer:** No. Use explicit `Socket.close()` or try-with-resources.

**Question 8.** What risk does a Cleaner action capturing the registered wrapper itself cause?

**Answer:** A strong reference from the action to the referent can prevent the object from becoming phantom reachable, blocking automatic cleaning.

**Question 9.** Why should `Cleanable.clean()` still be called from `close()` when using Cleaner?

**Answer:** For cleanup on a caller-controlled schedule; without depending on when GC reports phantom reachability.

**Question 10.** Does `Reference.reachabilityFence(owner)` automatically close a file?

**Answer:** No. It ensures owner is strongly reachable past the call site, and does not perform resource close.

**Question 11.** Does `Socket.close()` prove the server has processed and successfully saved a transaction?

**Answer:** No. An appropriate application-level response/acknowledgement is required.

**Question 12.** Why is closing `FileChannel` not enough to assert that a mapped buffer has been unmapped immediately?

**Answer:** Mappings have their own lifecycle/semantics; channel close does not enforce an immediate unmap guarantee across all JDKs.

**Question 13.** A ThreadLocal value still holds an object graph after a request; the caller's local variable has gone out of scope. How is the object still alive?

**Answer:** The worker thread holds the thread-local map entry/value. Use `remove()` when the request ends if the state only belongs to the request.

**Question 14.** By what mechanism does `CleanerSafetyDemo` print `cleaned once` on its own?

**Answer:** `try-with-resources` calls `close()`, and close calls `cleanable.clean()` explicitly; no GC is needed.

**Question 15.** Should an HTTP client using a connection pool be created and closed for every request?

**Answer:** Not necessarily. The client/pool can be reused long-term; response body streams or borrowed connections are closed in a shorter scope per the API.

**Question 16.** Is looking only at `GC.class_histogram` enough to conclude file handles are closed properly?

**Answer:** No. One must observe FD counts, close behavior, and resource ownership; the histogram only gives the number of Java objects by type.

**Question 17.** Why should suppressed exceptions be inspected?

**Answer:** Because a resource's close can fail when the body already has a primary error; suppressed exceptions store the cause of the close failure, which has diagnostic value.

**Question 18.** Can `ByteBuffer.allocateDirect` increase native memory without heap usage increasing correspondingly?

**Answer:** Yes. Direct buffers involve native/off-heap memory; accounting and reclamation depend on the VM.

## 23. Project Application Checklist

1. For each resource, clearly document **owner, borrow semantics, how to close, and closing point**.
2. Prefer **try-with-resources** for `AutoCloseable` with a finite scope.
3. Close resources in the appropriate order, avoiding double-close of shared handles.
4. Preserve suppressed exceptions when both the body and close fail.
5. In JDBC, distinguish transaction lifecycle, statement/result set, and connection pool semantics.
6. In network code, distinguish local close, half-close, timeout, and business acknowledgement.
7. Use explicit shutdown/cancellation for executors, tasks, and streams/listeners per the API.
8. For `ThreadLocal` request data, use `finally` to `remove()` when appropriate.
9. Use Cleaner only as a **fallback**, ensuring the action does not capture the referent.
10. Do not rely on `finalize`, `System.gc()`, or `Thread.sleep` as a way to close resources.
11. For native wrappers, consider `reachabilityFence` and ownership synchronization when there is contention between use/close.
12. Separate heap/GC metrics from FD counts, socket states, pool metrics, and native RSS.
13. Test success, exception, timeout, cancellation, partial acquisition, and shutdown paths.
14. Measure resource usage across multiple requests/redeploy cycles rather than a single snapshot.
15. If OS handle count keeps growing, fix **resource lifecycle** before just raising OS limits.
16. When using mapped memory or native FFM, read the API contract for the target JDK, avoiding private implementation shortcuts.
17. Ensure close error logs have context without leaking secrets/PII.
18. Do not claim **GC "never" helps release resources**: some libraries have fallback cleanup; the accurate statement is that **GC is not a deterministic release mechanism with a deadline**.

### Final Summary

```text
                Java object wrapper
                       |
        +--------------+---------------+
        |                              |
        v                              v
  Heap reachability            External resource state
        |                              |
        v                              v
  GC may reclaim               explicit close / release
  object memory                (owner-controlled)
        |                              |
        +--------------+---------------+
                       |
         does NOT mean at the same time

try-with-resources:
  allocate -> use -> guaranteed close per Java control flow
  (when execution reaches the corresponding points; close can still fail)

Cleaner:
  fallback cleanup based on phantom reachability;
  no deadline, so explicit clean/close is the primary path
```

**Key takeaway:** **GC manages Java object memory; the application must manage external resources according to explicit ownership and closing contracts.** File descriptors, sockets, connections, native allocations, and worker threads must not be allowed to depend on when a variable goes out of scope or when the collector happens to run.

### Authoritative References

- [JVMS §2.5.3 — Heap (Java SE 17)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.5.3): heap objects and automatic storage management.
- [JLS §14.20.3 — try-with-resources (Java SE 17)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3): initialization/reverse-order closing rules, exceptions, and suppressed exceptions.
- [AutoCloseable API (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): close contract and try-with-resources recommendation.
- [Closeable API (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Closeable.html): close for I/O resources.
- [Cleaner API (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Cleaner.html): phantom reachability, explicit `clean`, and preventing actions from capturing the referent.
- [Reference.reachabilityFence API (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Reference.html#reachabilityFence(java.lang.Object)): keeping a wrapper strongly reachable until the last point of use.
- [Socket API (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html): close, half-close, and timeout.
- [Files.newBufferedWriter (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#newBufferedWriter(java.nio.file.Path,java.nio.charset.Charset,java.nio.file.OpenOption...)): opening a writer on the filesystem.
- [Connection API (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Connection.html): transactions and close per JDBC.
- [OpenJDK JEP 421 — Deprecate Finalization for Removal](https://openjdk.org/jeps/421): limitations and roadmap for removing finalization.
