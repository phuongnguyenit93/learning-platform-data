# Finalization and resource management with explicit closing

During Java application upgrades and migrations, one subtle risk is tying resource release to garbage collection (GC). Legacy code sometimes places file closing, native memory freeing, or connection returning inside the `finalize()` method and expects the JVM to call it automatically when the object is no longer referenced. This expectation is insufficient to guarantee that resources are released on time, in the right order, or even released at all.

Modern Java encourages managing resource lifecycles through **explicit closing**: the class owning the resource implements `AutoCloseable` or `Closeable`; the lifecycle owner calls `close()`, typically via `try-with-resources`. For native resources, `Cleaner` or reference-processing can serve as a fallback, but does not replace controlled closing.

This lesson focuses on identifying dependencies on finalization, selecting appropriate resource management approaches, migrating legacy code to explicit closing, and organizing tests during a Java Advance Compatibility Migration.

## 1. Distinguishing Java memory from off-heap resources

Java's GC primarily manages the heap memory containing Java objects. When an object becomes unreachable, the JVM can reclaim its heap memory at an appropriate time. **That does not mean all resources associated with the object have been released.**

Examples of resources requiring lifecycle management:

| Resource | Why does it need releasing? | Common mechanism |
|---|---|---|
| File descriptor, input/output stream | The OS limits handle counts; files may remain locked | `close()`, `try-with-resources` |
| Socket and network connection | Holds connections, descriptors, and protocol state | `Socket.close()` or equivalent API |
| JDBC connection, statement, result set | Holds connection pools, cursors, and server-side resources | `AutoCloseable` / `try-with-resources` |
| Direct/native memory | Off-heap memory with a lifecycle different from Java objects | API with a clear owner; `Arena.close()` when appropriate |
| JNI native handle | OS or C/C++ library objects requiring explicit release calls | `AutoCloseable` wrapper calling the native release function |
| Zip/JAR filesystem, directory stream | Can hold descriptors, mappings, or open state | Close the owning object |
| Thread pool and task executor | Retains threads or running tasks | Coordinated shutdown/close |
| Lock or transaction | Must end according to business logic and deterministic order | `unlock()` / commit / rollback in `finally` |

Not every Java object needs to be closed. `String`, collections, most POJOs, and ordinary arrays are managed by GC. Building artificial `close()` mechanisms for every object adds unnecessary complexity. Focus on objects that actually **own** resources needing release.

### 1.1. An example bug caused by relying on GC

Suppose an application processes thousands of files without closing streams:

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;

static byte[] readFile(Path path) throws IOException {
    InputStream input = Files.newInputStream(path);
    return input.readAllBytes(); // Stream is not closed
}
```

The application may run fine in small tests, because streams eventually lose references and some implementations have internal cleanup mechanisms. However, after many iterations, the number of open file descriptors can grow faster than GC can reclaim or clean them up. The system can fail to open files or hit handle limits.

Fix using `try-with-resources`:

```java
static byte[] readFile(Path path) throws IOException {
    try (InputStream input = Files.newInputStream(path)) {
        return input.readAllBytes();
    }
}
```

Now the stream is closed when the `try` block exits, even if `readAllBytes()` throws an exception.

## 2. What is finalization and why should dependencies on it be removed?

### 2.1. The traditional `finalize()` mechanism

In legacy Java, a class could override `Object.finalize()` to ask the JVM to run cleanup code before reclaiming the object. Legacy-style example:

```java
class LegacyNativeResource {
    private long nativeHandle;

    @Override
    @SuppressWarnings("deprecation")
    protected void finalize() throws Throwable {
        try {
            if (nativeHandle != 0L) {
                releaseNative(nativeHandle);
                nativeHandle = 0L;
            }
        } finally {
            super.finalize();
        }
    }

    private static native void releaseNative(long handle);
}
```

This is a **pattern that needs migration**, not a pattern to adopt in new code. The `finalize()` method is not invoked immediately when a variable leaves scope; GC decides when an object may be processed. In some situations, the JVM may terminate before the finalizer ever runs.

Main issues:

- **Non-deterministic timing:** too many files or native handles may be held for a long time even though the Java object is no longer used.
- **No execution guarantee:** the JVM does not promise that finalizers will always run before the process exits.
- **GC overhead and latency:** objects with finalizers require special handling, making reclamation more complex.
- **Unspecified ordering:** finalizers of two related objects do not necessarily run in the order required by release logic.
- **Difficult error handling:** exceptions in a finalizer provide no reliable error-propagation path back to where the resource was used.
- **Safety and correctness risks:** object resurrection and running code on objects that are not yet or no longer in a valid state can produce hard-to-control behavior.

Do not use `System.gc()`, `System.runFinalization()`, or allocate many objects to "force" finalizers to run. Those calls do not establish a reliable resource-release contract.

### 2.2. Finalization lifecycle across Java releases

Finalization has long been warned against; `Object.finalize()` was marked deprecated starting in Java 9. JEP 421 further deprecated finalization **for removal** in the JDK 18 timeframe, emphasizing migration to controlled release. JDK releases may provide options to disable finalization to help detect dependencies; option availability and syntax should be checked against the running JDK.

When migrating JDKs, do not infer that because code still compiles, finalization remains a long-term supported contract. An older dependency might still override `finalize()` without the application's knowledge.

### 2.3. Distinguishing finalization from `final` and `finally`

Three easily confused concepts:

- **`finalize()`:** legacy GC-related cleanup hook; should not be used for new resource management.
- **`final`:** modifier that restricts variable reassignment, method overriding, or class inheritance depending on placement; has no effect on closing resources.
- **`finally`:** code block executed upon exiting `try` under normal exception rules; can be used to close resources manually, though `try-with-resources` is usually cleaner.

Traditional `finally` example:

```java
InputStream input = Files.newInputStream(path);
try {
    consume(input);
} finally {
    input.close();
}
```

This pattern offers more deterministic release timing than `finalize()`, but risks having an exception from `close()` mask the original exception. `try-with-resources` handles that issue more cleanly.

## 3. `AutoCloseable`, `Closeable`, and `try-with-resources`

### 3.1. The `AutoCloseable` contract

`AutoCloseable` was introduced in Java 7 and declares the `close()` method. An object implementing this interface can be declared in the resource header of `try-with-resources`:

```java
public interface AutoCloseable {
    void close() throws Exception;
}
```

`java.io.Closeable` extends `AutoCloseable` and specifies `close()` throwing `IOException`, suited for I/O classes. Both interfaces enable `try-with-resources` to handle automatic closing.

Choose the interface based on the resource kind:

| Scenario | Suggested interface |
|---|---|
| Streams and I/O resources with I/O-related errors | `Closeable` |
| Transactions, native sessions, scopes, or general resources | `AutoCloseable` |
| APIs with existing types extending either interface | Keep the existing contract; avoid creating unnecessary new closing interfaces |

A class's `close()` method can narrow checked exceptions by declaring a more specific exception or declaring no checked exceptions at all. API design should specify consistent semantics: whether closing can fail, whether closing multiple times is allowed, and which methods remain valid after closing.

### 3.2. `try-with-resources` closes immediately upon leaving scope

Example using two resources:

```java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

static void copyText(Path source, Path target) throws IOException {
    try (BufferedReader reader =
                 Files.newBufferedReader(source, StandardCharsets.UTF_8);
         BufferedWriter writer =
                 Files.newBufferedWriter(target, StandardCharsets.UTF_8)) {

        String line;
        while ((line = reader.readLine()) != null) {
            writer.write(line);
            writer.newLine();
        }
    }
}
```

When the block finishes, Java closes the resources in **reverse order of declaration**: `writer` first, then `reader`. If initializing the second resource fails, the first resource that was already successfully created is still closed.

The resource's scope must correspond to the code region that owns it. Do not use the object after the scope has closed.

### 3.3. Java 9 allows using previously declared resource variables

Starting in Java 9, `try-with-resources` allows declaring a resource outside and referencing it in the resource header if the variable is `final` or effectively final:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

static String firstLine(Path path) throws IOException {
    BufferedReader reader = Files.newBufferedReader(path);

    try (reader) {
        return reader.readLine();
    }
}
```

This mechanism is useful when migrating code with separate initialization steps, provided scope and ownership remain clear. After the `try` block, do not continue using `reader` because it has been closed.

### 3.4. Exceptions and suppressed exceptions

Suppose reading fails while `close()` also throws an exception. With `try-with-resources`, the exception from the body is preserved as the primary exception; errors during closing are attached to `getSuppressed()`.

```java
try (AutoCloseable resource = acquireResource()) {
    performOperation(resource);
} catch (Exception error) {
    System.err.println("Primary error: " + error);

    for (Throwable suppressed : error.getSuppressed()) {
        System.err.println("Close error: " + suppressed);
    }

    throw error;
}
```

In production logging, log both the primary exception and suppressed exceptions so cleanup errors are not missed. Avoid overwriting the primary exception with a new exception containing only a generic message. With multiple resources, closing happens in reverse order and multiple close errors may be attached.

### 3.5. Building a custom closeable class

A simple wrapper can manage an I/O resource:

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Objects;

public final class FileReaderSession implements AutoCloseable {
    private final InputStream input;
    private boolean closed;

    public FileReaderSession(Path path) throws IOException {
        this.input = Files.newInputStream(
            Objects.requireNonNull(path, "path")
        );
    }

    public int read() throws IOException {
        if (closed) {
            throw new IllegalStateException("Session is closed");
        }
        return input.read();
    }

    @Override
    public void close() throws IOException {
        if (!closed) {
            closed = true;
            input.close();
        }
    }
}
```

Usage:

```java
try (FileReaderSession session = new FileReaderSession(path)) {
    System.out.println(session.read());
}
```

This simple example assumes the resource is not used concurrently by multiple threads. If `read()` and `close()` can run concurrently, a boolean flag is not enough to ensure safety; specify thread confinement or design appropriate synchronization.

## 4. Resource ownership: who is responsible for closing?

One of the common mistakes after moving away from finalization is multiple places each assuming somewhere else will call `close()`.

### 4.1. Ownership must follow the lifecycle

Three roles can be distinguished:

- **Owner:** creates or receives transferred ownership, responsible for closing exactly once per the contract.
- **Borrower:** permitted to use the resource within a defined scope, but must not close it unless given ownership.
- **Factory/provider:** creates the resource and explicitly states whether the consumer must close it.

Example of a factory returning a stream:

```java
static InputStream openConfig(Path path) throws IOException {
    return Files.newInputStream(path);
}
```

The caller receives a new resource and must close it:

```java
try (InputStream input = openConfig(path)) {
    loadConfiguration(input);
}
```

Conversely, a method that only borrows a stream should not close it unless the contract allows doing so:

```java
static int countBytes(InputStream borrowed) throws IOException {
    int count = 0;
    while (borrowed.read() != -1) {
        count++;
    }
    return count;
}
```

In the latter example, the caller still owns the stream and decides when to close it. Unexpectedly "helping" by closing it can break downstream processing.

### 4.2. Do not return closed resources

This is a common mistake:

```java
static InputStream incorrect(Path path) throws IOException {
    try (InputStream input = Files.newInputStream(path)) {
        return input; // Returns a closed handle!
    }
}
```

If the caller should read the stream, return it directly and document closing responsibility. If the method should fully own reading, return the data already read before the scope ends.

### 4.3. Shared resources and application lifecycle

It is not possible to apply `try-with-resources` to every shared resource at every call site. For example, a connection pool or shared client typically lives for the duration of the service. There must be an application-level owner (lifecycle manager, dependency-injection container, or service coordinator) that closes it during controlled service shutdown.

Crucially, **closing authority is coordinated from a single place**, even when multiple components borrow the resource. If one request accidentally closes a shared HTTP client, other requests can fail.

### 4.4. Asynchronous resources

With asynchronous processing, a task's scope may outlive the method scope that created the resource. Do not close immediately after submitting if the task still uses the resource:

```java
// Wrong: the task may use the stream after the try block ends.
try (InputStream input = Files.newInputStream(path)) {
    executor.submit(() -> process(input));
}
```

There are two safe approaches:

1. The worker task opens and closes the resource within its own scope.
2. The coordinating owner ensures the resource is closed only after all related tasks finish, with explicit cancellation and shutdown mechanisms.

When using callbacks or reactive streams, clearly document who owns the subscription, connection, and cancel token. Passing a resource across multiple threads does not make GC a reliable cleanup mechanism.

## 5. Migrating from `finalize()` to explicit closing

### 5.1. Code example before migration

Suppose a legacy class holds a native handle:

```java
public class LegacySession {
    private long handle;

    public LegacySession() {
        handle = NativeApi.open();
    }

    public void send(byte[] payload) {
        NativeApi.send(handle, payload);
    }

    @Override
    @SuppressWarnings("deprecation")
    protected void finalize() throws Throwable {
        try {
            NativeApi.release(handle);
        } finally {
            super.finalize();
        }
    }
}
```

Here `NativeApi` is a hypothetical class representing a JNI binding. This pattern can hold onto the native handle for a long time and offers no business-level way to close it.

### 5.2. Migrating to `AutoCloseable`

The new version manages the handle explicitly:

```java
import java.util.concurrent.atomic.AtomicLong;

public final class NativeSession implements AutoCloseable {
    private final AtomicLong handle;

    public NativeSession() {
        long acquired = NativeApi.open();
        if (acquired == 0L) {
            throw new IllegalStateException(
                "Native session could not be opened"
            );
        }
        this.handle = new AtomicLong(acquired);
    }

    public void send(byte[] payload) {
        long current = handle.get();
        if (current == 0L) {
            throw new IllegalStateException("Session is closed");
        }
        NativeApi.send(current, payload);
    }

    @Override
    public void close() {
        long previous = handle.getAndSet(0L);
        if (previous != 0L) {
            NativeApi.release(previous);
        }
    }
}
```

Usage:

```java
try (NativeSession session = new NativeSession()) {
    session.send(payload);
}
```

`AtomicLong.getAndSet(0L)` ensures one `close()` call claims the right to release the handle and subsequent close calls do not release the same handle again. This is an example of **idempotence**.

However, `send()` and `close()` can race if called from different threads. One thread might read the handle right before another thread releases it. For real native handles, design synchronized lifetimes: confine each session to a single thread, use locks, controlled reference counting, or an in-flight operation counter. Do not treat `AtomicLong` alone as enough to prevent every use-after-free.

Additionally, `NativeApi.release` might throw an exception. The `close()` contract should specify whether that error is propagated, logged, or translated into another exception; avoid leaving the handle in a reusable state after a release attempt.

### 5.3. Partial initialization failure

A complex native wrapper may allocate multiple handles in a constructor. If the second step fails, the object is not completely constructed, so the caller cannot call `close()` on it. The constructor must clean up already allocated resources before throwing the error.

Illustrative principle example:

```java
static NativeBundle openBundle() {
    long primary = NativeApi.openPrimary();

    try {
        long secondary = NativeApi.openSecondary(primary);
        return new NativeBundle(primary, secondary);
    } catch (RuntimeException | Error failure) {
        NativeApi.releasePrimary(primary);
        throw failure;
    }
}
```

If cleanup can also throw an error, preserve the original exception and attach the cleanup error as a suppressed exception where appropriate. The code above illustrates the ownership pattern; the class and native methods are hypothetical example components, not built-in JDK APIs.

### 5.4. Evolving the API so callers have time to transition

When the legacy class is a public API, requiring callers to call `close()` is a behavioral contract change. It can be rolled out in phases:

1. Add `AutoCloseable` or a factory returning a closeable resource, keeping the old constructor during transition if required.
2. Document clearly in Javadoc that the caller owns the resource and must close it.
3. Update all internal callers to `try-with-resources`.
4. Add controlled logging/metrics to detect resource leaks.
5. Advise external consumers to upgrade versions and update their code.
6. Run integration tests with real consuming applications.
7. Remove finalization dependencies once all callers are updated.

Do not remove a finalizer before providing a new release path in the public API. Conversely, do not keep a finalizer indefinitely to compensate for callers failing to call `close()`; establish a removal roadmap or a fallback not reliant on finalization.

## 6. `Cleaner`: fallback mechanism for native resources

### 6.1. What can Cleaner do?

`java.lang.ref.Cleaner` (Java 9+) allows registering a cleaning action that runs after the registered object becomes phantom reachable, or when the application invokes `Cleanable.clean()`. Cleaner provides an alternative to finalization for fallback cleanup of off-heap resources.

However, Cleaner **does not guarantee timing** and does not guarantee the action will run before the JVM shuts down. Therefore, for files, sockets, connections, or native handles requiring timely release, continue using `close()` and `try-with-resources` as the primary path. Cleaner works well as a "safety net" when a caller forgets to close, not as a business lifecycle management mechanism.

### 6.2. Pattern combining Cleaner with `AutoCloseable`

The following pattern keeps the cleaning state separate from the owner object so the action does not accidentally retain a strong reference to the owner itself:

```java
import java.lang.ref.Cleaner;
import java.util.concurrent.atomic.AtomicLong;

public final class NativeBuffer implements AutoCloseable {
    private static final Cleaner CLEANER = Cleaner.create();

    private static final class State implements Runnable {
        private final AtomicLong address;

        State(long address) {
            this.address = new AtomicLong(address);
        }

        @Override
        public void run() {
            long previous = address.getAndSet(0L);
            if (previous != 0L) {
                NativeApi.freeMemory(previous);
            }
        }
    }

    private final State state;
    private final Cleaner.Cleanable cleanable;

    public NativeBuffer(long bytes) {
        long address = NativeApi.allocateMemory(bytes);
        if (address == 0L) {
            throw new IllegalStateException("Allocation failed");
        }

        this.state = new State(address);
        this.cleanable = CLEANER.register(this, state);
    }

    public long address() {
        long current = state.address.get();
        if (current == 0L) {
            throw new IllegalStateException("Buffer is closed");
        }
        return current;
    }

    @Override
    public void close() {
        cleanable.clean();
    }
}
```

`NativeApi` is a hypothetical class representing a native allocator; the example is not a complete memory manager and does not address one thread using the address while another thread calls `close()`.

Key design points:

- `State` is a separate object holding no strong reference to `NativeBuffer`.
- `Cleaner.register(this, state)` registers the cleaning action with the owner.
- `close()` calls `cleanable.clean()` to release **immediately on the explicit close path**.
- `AtomicLong.getAndSet(0L)` avoids freeing twice once the action has run.
- If the caller forgets to close and the owner becomes phantom reachable, Cleaner *may* run the action later.

### 6.3. Limitations of Cleaner

Do not use Cleaner to:

- Commit or roll back a transaction based on business outcome.
- Guarantee a socket or file is closed immediately when a request finishes.
- Meet SLAs on connection pool release timing.
- Perform operations requiring ordered closing of multiple related resources.
- Run complex logic depending on other services that may already have shut down.
- Propagate cleanup exceptions back to the caller for consistent handling.

The cleaning action runs on Cleaner's management thread and should not depend on UI, request context, or thread-local state. If the action holds the owner so the referent remains reachable, the action may never trigger automatically. If the action throws an exception, error observability is typically worse than calling `close()` directly.

For critical resources, the better approach is controlling ownership and measuring leaks rather than relying on Cleaner to mask design flaws.

## 7. `ReferenceQueue`, phantom references, and special cases

Java provides reference types such as weak, soft, and phantom references alongside `ReferenceQueue`. They serve reachability management and GC-related mechanisms.

`PhantomReference` can be used to detect when an object has reached phantom reachability and coordinate cleanup for an external resource. However, building a correct reference manager requires:

- Keeping the `PhantomReference` reachable until it is processed.
- Having a queue consumer and shutdown mechanism.
- Separating cleanup metadata from the referent object.
- Handling concurrency, deregistration, and idempotence.
- Accepting that the process may exit before the queue is processed.

Most applications should use `Cleaner` if a fallback is needed instead of building a custom reference queue. In particular, do not use weak references to replace resource closing: weak references only affect reachability and provide no resource-lifecycle contract.

## 8. Java APIs where `close()` is easily overlooked

### 8.1. `Files.lines`, `Files.list`, `Files.walk`

Several methods on `java.nio.file.Files` return a `Stream` backed by an OS resource. Terminal operations such as `count()` or `forEach()` **do not automatically close the stream**. Wrap the stream in `try-with-resources`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

static long countNonEmptyLines(Path path) throws IOException {
    try (Stream<String> lines =
             Files.lines(path, StandardCharsets.UTF_8)) {
        return lines.filter(line -> !line.isBlank()).count();
    }
}
```

For directory traversal:

```java
static long countJavaFiles(Path root) throws IOException {
    try (Stream<Path> paths = Files.walk(root)) {
        return paths
            .filter(Files::isRegularFile)
            .filter(path -> path.toString().endsWith(".java"))
            .count();
    }
}
```

If returning the stream outward, the caller must be the owner and bear closing responsibility. Do not close the stream inside the method and return an invalidated stream to the caller.

### 8.2. JDBC resources

A safe pattern with JDBC:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

static int countActiveUsers(DataSource dataSource)
        throws SQLException {

    String sql = "SELECT COUNT(*) FROM users WHERE active = ?";

    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement =
             connection.prepareStatement(sql)) {

        statement.setBoolean(1, true);

        try (ResultSet rows = statement.executeQuery()) {
            rows.next();
            return rows.getInt(1);
        }
    }
}
```

With a connection pool, `Connection.close()` typically returns the connection to the pool rather than immediately closing the physical TCP connection; details depend on the implementation. The caller must still invoke `close()` when done to avoid exhausting the pool.

For transactions, distinguish closing a connection from committing or rolling back. Coordinate transactions with explicit code or a transaction manager, ensuring rollback when operations fail. Do not expect `close()` to always implicitly commit or roll back the way business logic requires.

### 8.3. `ExecutorService` and thread pools

In modern Java, `ExecutorService` supports `close()` and can be used with `try-with-resources` in applicable releases. However, closing an executor is not like closing a file: it governs task lifecycles and may wait for tasks to finish.

For an executor that lives for the application's lifetime, the service-level owner must manage shutdown, cancellation, timeouts, and handling unfinished tasks. Do not close an executor right after submitting if tasks are designed to run asynchronously beyond the current scope.

### 8.4. Resources from third-party libraries

SDK clients, HTTP clients, database sessions, file-system providers, compression libraries, and native bindings may have their own closing APIs. Do not assume every resource implements `AutoCloseable`.

When upgrading a library version, check release notes regarding lifecycles:

- A factory that previously returned a shared resource may now return a caller-owned resource.
- A `close()` method may change from a no-op to releasing sockets or worker threads.
- A client may require calling `shutdown()`, `dispose()`, or `release()` instead of `close()`.
- An API returning a lazy stream may require the caller to close it after the terminal operation.
- A DI framework may automatically close beans when the application context stops; callers should not manually close them mid-request.

Read the ownership contract of the exact dependency version rather than inferring it from class names.

## 9. Foreign Function & Memory API and resource scopes

Java 21 provided the Foreign Function & Memory API in preview; in Java 22 the API became final. Upgrades across these releases need API change checks when the application uses FFM.

In the final API, `Arena` manages the lifecycle of memory regions:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class ArenaExample {
    public static void main(String[] args) {
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment segment = arena.allocate(
                ValueLayout.JAVA_LONG
            );

            segment.set(ValueLayout.JAVA_LONG, 0, 123L);

            long value = segment.get(ValueLayout.JAVA_LONG, 0);
            System.out.println(value);
        }
    }
}
```

When the arena closes, segments allocated within that scope are no longer valid to access per the API contract. This clearly expresses resource lifetimes and reduces manual management of native addresses via integers.

Different arena kinds have different lifetimes: for example, a shared arena allows multi-threaded access while still requiring controlled closing; an automatic arena has a lifetime governed by reachability/GC. When timely resource release is required, prefer an explicitly closeable arena over automatic cleanup.

Do not share a `MemorySegment` beyond its arena's lifetime. If an async task needs the segment, the owner must keep the arena valid until the task completes and coordinate closing.

## 10. Designing `close()` properly in production systems

### 10.1. Idempotence and closed state

Normally, calling `close()` multiple times should not free the same native pointer twice. `Closeable` specifies that repeated closes have no effect; for `AutoCloseable` in general, idempotence is an important recommendation, though not guaranteed by every implementation.

A state-managing class should define:

- `OPEN`: the resource is ready for use.
- `CLOSING`: release has started; new usage calls are not permitted.
- `CLOSED`: release is complete or the handle is no longer valid.

In concurrent code, select an appropriate locking mechanism or state machine. Merely setting `closed = true` does not by itself resolve race conditions with in-flight I/O operations.

### 10.2. Closing order for dependent resources

If resource B uses resource A, usually close B before A. Because `try-with-resources` closes in reverse order, declare the underlying resource first and the wrapper afterward:

```java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement =
         connection.prepareStatement(sql);
     ResultSet results = statement.executeQuery()) {

    while (results.next()) {
        consume(results);
    }
}
```

In this order, ResultSet is closed first, followed by statement and connection. This is a significant advantage over relying on finalizers with unspecified ordering.

### 10.3. Behavior when closing fails

`close()` can throw checked or unchecked exceptions. Decide:

- Should a closing failure cause the business operation to be marked failed?
- Can the resource be retried for closing?
- If partially released, what is the object's state?
- Are logs, metrics, or alerts needed to detect leaks?
- When multiple resources fail together, which exception is kept as primary?

With file output, a flush/close error may mean data was not completely written. Do not silently ignore it. With a connection pool, an error returning a connection may need metrics but does not necessarily revert an already committed transaction. The policy depends on each resource's contract.

### 10.4. Closing does not mean commit, unlock, or cancel

Some resources are not `AutoCloseable` even though they still require ordered release. A `Lock` needs `unlock()` in `finally`, a transaction needs commit/rollback based on outcome, a subscription needs canceling, and a job needs coordinated termination.

Example using a lock:

```java
lock.lock();
try {
    updateSharedState();
} finally {
    lock.unlock();
}
```

Do not force every cleanup operation into `AutoCloseable` if that abstraction obscures the semantics of commit, rollback, or ownership. Explicit closing is the principle; the specific interface must fit the resource.

## 11. Reviewing the codebase during migration

### 11.1. Signals to look for

Across source code and dependencies, prioritize identifying:

- Overrides of `finalize()` or calls to `super.finalize()`.
- `System.runFinalization()` and code expecting GC to release resources.
- `System.gc()` invoked as a "resource-closing measure".
- Custom `Cleaner` or `ReferenceQueue` implementations.
- File/socket/JDBC resources created without a `close()` path.
- `Files.lines`, `Files.list`, `Files.walk` used without try-with-resources.
- Native wrappers holding a `long handle`, `ByteBuffer`, pointer, or file descriptor.
- Factories returning resources with unclear ownership.
- Async tasks using resources whose lifetime is shorter than the task.
- Global resources closed from a local request or transaction.

Text search can be used as a starting step:

```shell
rg -n "finalize\\s*\\(|runFinalization\\s*\\(" src
rg -n "System\\.gc\\s*\\(" src
rg -n "Files\\.(lines|list|walk|find)\\s*\\(" src
rg -n "newInputStream|newOutputStream|getConnection" src
rg -n "Cleaner|PhantomReference|ReferenceQueue" src
```

String searching does not replace data-flow analysis. A resource might be closed in a framework lifecycle, inside a wrapper, or via another method; it can also be opened indirectly by an SDK. Establish ownership before making edits.

### 11.2. Building an inventory table

| Location | Resource | Current owner | Cleanup mechanism | Risk | Migration approach |
|---|---|---|---|---|---|
| ImportService | InputStream | Calling method | Not closed | File descriptor exhaustion | Try-with-resources |
| LegacyNativeBridge | Native handle | Object with finalizer | finalize | Leaks and indeterminate shutdown | AutoCloseable + Cleaner fallback |
| DataRepository | JDBC Connection | Request | Closed on some branches | Connection pool exhaustion | Try-with-resources/transaction manager |
| ReportExporter | Files.lines Stream | Unclear caller | Terminal operation | Descriptors held open | Transfer ownership or return data |
| SharedClientFactory | Shared HTTP client | Application | Request closes by mistake | Cross-request failures | Application-level lifecycle owner |

The table above illustrates how to document findings; class names do not represent a specific repository. The goal is to clarify where resources are created, last used, and closed.

## 12. Controlled migration roadmap

### Phase 1: Measure the baseline

Before modifying code, collect:

- Actual JDK version and vendor.
- Open file descriptor/handle counts.
- Connection pool utilization and connection wait timeouts.
- Native memory and direct buffer usage.
- Thread counts, executor queues, and shutdown behavior.
- I/O errors, connection leak warnings, and GC pressure.
- Existing tests for startup, shutdown, cancellation, and exception paths.

The baseline shows whether the migration actually reduces resource retention and detects unintended new behaviors.

### Phase 2: Define owners and contracts

For each resource, pick a single owner and specify:

1. Who creates or receives the resource?
2. Who may use it and for how long?
3. Who is responsible for closing it?
4. Can it be shared across threads or requests?
5. If the constructor or operation fails, where is the resource closed?
6. Is a fallback mechanism needed when callers forget to close?

Do not write cleanup wrappers before answering these questions.

### Phase 3: Replace finalizers with closing APIs

- For local resources, move to `try-with-resources`.
- For wrappers owning native handles, add `AutoCloseable` and an explicit `close()` method.
- For shared clients, close in the application lifecycle.
- For async resources, keep the owner alive until tasks finish.
- For native memory, consider an FFM Arena with an explicit closing scope.
- For legacy finalizers, remove GC-dependent code once closing paths cover all callers; consider a Cleaner fallback only if appropriately justified.

### Phase 4: Update consumers and API documentation

Update callers, for example from:

```java
LegacySession session = new LegacySession();
session.send(payload);
// No close operation
```

to:

```java
try (NativeSession session = new NativeSession()) {
    session.send(payload);
}
```

In Javadoc, state clearly that the type implements `AutoCloseable`, which party owns closing, and whether the object remains usable after `close()`.

For public libraries, add migration notes so consumers do not forget to update call sites. If a transition period is needed, use deprecation and release notes to describe when the contract changes.

### Phase 5: Test in the target environment

Re-run unit and integration tests on the target JDK, focusing on:

- Success paths.
- Exceptions in the body.
- Exceptions in `close()`.
- Partial initialization failures.
- Repeated closing.
- Access after closing.
- Concurrent use and closing.
- Cancellation/timeouts.
- Shutdown with running tasks.
- Data written to files flushes/closes successfully.

If the organization needs to verify no finalization dependency remains, consider running in a JVM configuration with finalization disabled **if supported by the runtime**, verifying the option against the specific JDK/vendor. Test results must rely on explicit closing capabilities rather than merely whether a flag is accepted.

### Phase 6: Rollout and observation

Deploy incrementally. Monitor file descriptors, connection pools, native memory, CPU/GC, latency, and shutdown errors. If leaks increase, identify the resource owner and exception path instead of adding `System.gc()` calls.

Maintain rollback capability when upgrading the JDK and replacing native libraries together, while ensuring data or protocol changes do not block rollback. For public APIs, communicate the `close()` contract clearly to consumers before removing old behavior.

## 13. Example resource lifecycle test

You can write a fake resource to test that `try-with-resources` closes even when code throws an exception:

```java
import java.util.concurrent.atomic.AtomicInteger;

final class TrackedResource implements AutoCloseable {
    private final AtomicInteger closeCount;

    TrackedResource(AtomicInteger closeCount) {
        this.closeCount = closeCount;
    }

    void work() {
        throw new IllegalStateException("Operation failed");
    }

    @Override
    public void close() {
        closeCount.incrementAndGet();
    }
}
```

Usage snippet:

```java
AtomicInteger closes = new AtomicInteger();

try (TrackedResource resource = new TrackedResource(closes)) {
    resource.work();
} catch (IllegalStateException expected) {
    // Handle the operation error.
}

if (closes.get() != 1) {
    throw new AssertionError("Resource was not closed exactly once");
}
```

This test verifies the lifecycle property without calling GC. For real resources, add integration tests measuring file descriptors, checking native memory, confirming connections return to the pool, or using mocks/spies to verify release calls.

Do not write tests relying on `System.gc()` and waiting for finalizers to run; such tests are flaky and verify the wrong contract. For Cleaner fallbacks, you can test behavior when calling `Cleanable.clean()` explicitly, without relying on GC timing to confirm business correctness.

## 14. Common mistakes

**Only replacing `finalize()` with `Cleaner`.** Cleaner also does not guarantee execution timing. Add `close()` and move callers to explicit ownership; use Cleaner if a fallback is needed.

**Thinking `try-with-resources` is only for files.** JDBC, native Arena, resource scopes, and many other objects can also implement `AutoCloseable`.

**Closing a resource in a called method that does not own it.** A borrower closing on its own can break the caller and other components. Document the owner clearly.

**Returning a resource after closing it.** Leads to access errors and subtle bugs. If returning a resource, transfer closing responsibility.

**Using a terminal operation and forgetting to close file-backed streams.** `Stream.count()` or `forEach()` does not mean `Files.lines` or `Files.walk` is closed.

**Relying on `final` to prevent leaks.** `final` only restricts reassigning the reference; it does not release resources automatically.

**Ignoring `close()` exceptions.** Can hide unflushed file output or connections failing to return to the pool.

**Assuming repeated closing is always safe.** Read the specific type's `AutoCloseable` contract and implement idempotence in native wrappers if needed.

**Handling only single-threaded cases and ignoring races between use and close.** Thread confinement or lifecycle synchronization is needed.

**Using GC as a timer.** GC cannot replace application timeouts, cancellation, or shutdown logic.

## 15. Checklist before completing migration

### Source code and APIs

- [ ] Inventoried `finalize()` overrides and finalization-related calls.
- [ ] Identified which resources require explicit closing.
- [ ] Documented owners, borrowers, and when ownership is transferred.
- [ ] Added `AutoCloseable`/`Closeable` on the appropriate resource-owning classes.
- [ ] Migrated local resources to `try-with-resources`.
- [ ] No returning closed objects or mistakenly closing shared resources.

### Native resources and fallbacks

- [ ] Native handles are released by intentional `close()` calls.
- [ ] Safeguards exist against double-free on repeated closes.
- [ ] Resolved races between operations and closing where concurrency exists.
- [ ] Handled cleanup when constructors partially fail.
- [ ] `Cleaner` is only a fallback and holds no strong reference to the owner.
- [ ] No reliance on GC to commit, roll back, or close on time.

### Testing and operations

- [ ] Tested success, exception, cancellation, and shutdown paths.
- [ ] Tested errors in `close()` and checked suppressed exceptions where applicable.
- [ ] Verified file-backed streams, JDBC connections, and SDK clients are closed.
- [ ] Collected metrics on file descriptors, connection pools, and native memory.
- [ ] Reviewed finalization behavior for the target JDK/vendor.
- [ ] Prepared release notes and consumer guidance if public APIs changed.

## Conclusion

Finalization is not a reliable contract for releasing resources. Java memory is managed by GC, whereas file descriptors, sockets, JDBC connections, native handles, and off-heap resources require clear lifecycles. The modern approach is assigning closing responsibility to the owner, implementing `AutoCloseable` or `Closeable`, and using `try-with-resources` or a lifecycle manager to call `close()` at deterministic times.

In Java Advance Compatibility Migration, locate `finalize()` dependencies, fix ownership before changing cleanup mechanisms, handle errors and concurrency properly, and test the application on the target JDK. `Cleaner` can guard against some forgotten closes, but reliability and correctness must come from the explicit closing path and be verified through resource-lifecycle testing.
