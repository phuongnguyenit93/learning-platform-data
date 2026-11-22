# `Closeable`, `AutoCloseable`, and `try-with-resources`

## Lesson Objectives

When a Java program opens a file, socket, stream, reader, channel, or database connection, the resource behind the object can be a **file descriptor, buffer, connection, lock, or system state**. The garbage collector manages the memory of Java objects, yet **it is not a mechanism for closing resources promptly** as required by the application.

Java provides `AutoCloseable`, the specialized `Closeable` interface, and the `try-with-resources` (TWR) syntax to manage the lifecycle of closeable resources. The key questions are: **who owns the resource, when is it closed, in what order, and what happens if both the `try` body and `close()` throw errors**.

After this lesson, you will be able to:

- Distinguish `java.lang.AutoCloseable` and `java.io.Closeable` via the `close()` signature, applicability, and repeated-close behavior.
- Use `try-with-resources` with one or more resources, understanding **left-to-right** initialization order and **right-to-left** closing order.
- Write programs that accurately handle exceptions thrown inside the `try` body, during initialization, and during closing; know how to inspect `Throwable.getSuppressed()`.
- Apply Java 9+ syntax for pre-declared resource variables and the *effectively final* rule.
- Choose the right resource ownership strategy when wrapping streams/readers, using `System.in/out`, receiving resources from libraries, or managing transactions.
- Test resource lifecycles using standalone Java 17 examples with verifiable output.

## 1. Why Must Resources Be Closed?

Consider this code:

```java
InputStream in = Files.newInputStream(path);
byte[] data = in.readAllBytes();
```

This is an **illustrative snippet**: `path` is a valid `Path`; it assumes imports for `java.io.InputStream`, `java.nio.file.Files`, `java.nio.file.Path`, and `IOException` handling. This snippet does not close `in`. If a long-running program repeatedly opens many files without closing them, it can exhaust file descriptors or hold system resources longer than desired. If `readAllBytes()` throws an exception, no path in this snippet ensures the stream is closed.

**Do not rely on the garbage collector**: GC may not run when you need to release resources; some resources do not correspond directly to a heap region. Calling `System.gc()` also does not become a promise that resources will close in time. Always **bind usage scope to closing scope**.

TWR lets us rewrite it as:

```java
try (InputStream in = Files.newInputStream(path)) {
    byte[] data = in.readAllBytes();
    // Process data while in is still open.
}
```

This is an **illustrative snippet**; `path` and the same imports/checked exceptions apply. When leaving the `try` block, Java automatically calls `in.close()` — even if the body throws an exception or executes `return`. For regular I/O, this should be your default approach.

### Common Lifecycle

```text
Create/open resource -> Use -> Close (even if usage fails)
        |                |
        +-- open error?  +-- close error?
                \       /
        Handle exception with context
```

**Closing a resource does not mean data has been durably persisted to disk.** For instance, `BufferedWriter.close()` typically flushes its buffer and closes the underlying writer, which is not equivalent to ensuring the filesystem synced data via `fsync`/`FileChannel.force()`. This lesson focuses on **lifecycle and errors**, without turning `close()` into a durability guarantee.

## 2. `AutoCloseable`: General Resource-Closing Contract

`java.lang.AutoCloseable` is an interface with a single method:

```java
public interface AutoCloseable {
    void close() throws Exception;
}
```

This is a **condensed illustrative signature**, not code you need to declare yourself to replace the JDK class. Any object type implementing `AutoCloseable` can appear in the resource declaration header of `try-with-resources`.

The object may represent a file, database connection, lock scope, session, or non-filesystem resource. An object that owns no OS resource can still implement `AutoCloseable` if it wishes to provide a structured end-of-lifecycle operation.

Examples of related types:

| Type / API | Relationship | Commonly Managed Resource |
|---|---|---|
| `AutoCloseable` | Root interface | Any resource with a closing lifecycle |
| `Closeable` | Extends `AutoCloseable` | I/O typically throwing `IOException` |
| `InputStream`, `OutputStream`, `Reader`, `Writer` | Implement `Closeable` | Files, byte/character streams, or wrappers |
| `java.nio.channels.Channel` | Extends `Closeable` | I/O channels |
| `java.sql.Connection` | Implements `AutoCloseable` | Database connections |
| `java.sql.Statement`, `ResultSet` | Implement `AutoCloseable` | Statements and query results |
| `Stream<String>` returned by `Files.lines(path)` | `Stream` is `AutoCloseable` | Stream tied to an open reader/file |

`AutoCloseable.close()` declares `throws Exception`, meaning an implementation may throw a checked exception. However, **a concrete implementation is allowed to narrow or omit the checked exception** in its `close()` signature. Thus, the exception type you must declare/catch depends on the **static type of the variable** and the statements inside the `try` body.

Example:

```java
class TaskScope implements AutoCloseable {
    @Override
    public void close() {
        System.out.println("release");
    }
}
```

This is an **illustrative class definition**, usable in an appropriate Java file. Even though the base `AutoCloseable` declares `throws Exception`, `TaskScope.close()` here throws no checked exception, so caller code typed as `TaskScope` is not forced to catch `Exception` solely because of closing.

**Note on repeated closing:** `AutoCloseable` does not require `close()` to be idempotent (where calling it multiple times has the same effect as calling it once). A resource may throw an error or mutate state if closed again. Do not manually call `close()` inside a TWR body and assume Java's second close will always be harmless.

## 3. `Closeable`: Specialized Interface for I/O

`java.io.Closeable` **extends** `AutoCloseable` and narrows the checked exception:

```java
public interface Closeable extends AutoCloseable {
    @Override
    void close() throws IOException;
}
```

This is also a **condensed signature**, with `IOException` from `java.io`.

| Criterion | `AutoCloseable` | `Closeable` |
|---|---|---|
| Package | `java.lang` | `java.io` |
| Relationship | Parent interface | `extends AutoCloseable` |
| Checked exception from `close()` | Declares `Exception` | Declares `IOException` |
| Scope | General resource closing | I/O resources, especially streams/readers/channels |
| Repeated close | Not required to be idempotent | `Closeable` contract: closing an already closed object has no effect |
| Usable in TWR? | Yes | Yes |

`Closeable` states the rule: if the stream is already closed, invoking `close()` again has no effect. However, that does **not** mean every other `AutoCloseable` type shares that guarantee; nor does it guarantee that the **first** close will definitely succeed.

When designing your own API:

- If the abstraction is purely I/O, `Closeable` and `IOException` help callers handle domain-appropriate errors.
- If the resource scope is broader than I/O (such as a session/transaction context), `AutoCloseable` is a better fit. You can define `close()` with a narrower checked exception, or no checked exception when appropriate.
- For complex cleanup, avoid arbitrarily throwing broad `Exception` when you can provide a stable, meaningful exception type.

## 4. `try-with-resources`: Syntax and Execution Order

Basic syntax since Java 7:

```java
try (ResourceType first = openFirst();
     ResourceType second = openSecond()) {
    use(first, second);
} catch (SomeException ex) {
    handle(ex);
} finally {
    afterClosing();
}
```

This is **Java pseudocode**, not a standalone program: `ResourceType` must implement `AutoCloseable`, while `openFirst`, `openSecond`, `use`, `handle`, `afterClosing`, and `SomeException` are descriptive placeholders. `catch` and `finally` are optional; you can write TWR without either.

Main sequence:

1. Evaluate and **initialize resources from left to right**.
2. Once all initializations succeed, execute the `try` body.
3. Before running the TWR statement's `catch` or `finally`, **close resources from right to left**.
4. If errors occur, apply the **primary exception** and **suppressed exceptions** rules (below).
5. `catch` catches any remaining exception after TWR closes the resources; `finally` runs according to try/finally statement rules.

TWR also closes resources when exiting the block via `break`, `continue`, `return`, or an exception under normal Java execution mechanics. Do not interpret this as an absolute guarantee if the process is forcibly killed, `Runtime.halt()` is called, power is lost, or the JVM crashes: in those cases, cleanup may not run.

### Example 1 — Order of Opening, Using, and Closing Resources

Save **`ResourceOrderDemo.java`**:

```java
public class ResourceOrderDemo {
    static final class Trace implements AutoCloseable {
        private final String name;

        Trace(String name) {
            this.name = name;
            System.out.println("open " + name);
        }

        @Override
        public void close() {
            System.out.println("close " + name);
        }
    }

    public static void main(String[] args) {
        try (Trace first = new Trace("first");
             Trace second = new Trace("second")) {
            System.out.println("work");
        }
        System.out.println("after");
    }
}
```

Compile/run on Java 17+:

```bash
javac ResourceOrderDemo.java
java ResourceOrderDemo
```

Exact stdout:

```text
open first
open second
work
close second
close first
after
```

Explanation: `first`'s constructor runs before `second`'s. When leaving the body, Java invokes `second.close()` first and then `first.close()`, reversing initialization order. Thus an outer layer can continue existing until inner layers have closed — which typically matches wrappers depending on underlying streams.

If `second` fails to initialize, TWR still closes the already initialized `first`; it does not attempt to close a variable that never received a valid resource.

### Resource Declarations and `final`

Variables declared in the TWR header are **implicitly final**: you cannot reassign them to another object inside the `try` body.

Since Java 9, you can use **previously declared variables** if they are `final` or *effectively final*:

```java
InputStream input = Files.newInputStream(path);
try (input) {
    System.out.println(input.read());
}
```

This is an **illustrative snippet**, assuming `path` is a `Path`, with `InputStream`/`Files` imports and `IOException` handling. `input` is never reassigned, so it is effectively final and valid in Java 9+. After the block, the variable remains in the outer scope, yet **the stream is closed**; do not reuse it for further reads.

**Invalid** example because the resource variable is reassigned:

```java
InputStream input = Files.newInputStream(firstPath);
input = Files.newInputStream(secondPath);
try (input) {
    // Compiler error: input is not final or effectively final.
}
```

This is a **counterexample**, with `firstPath` and `secondPath` declared as `Path`. The code does not compile under Java 9+ resource-variable syntax. The proper design is a single variable owning a single resource, or declaring resources directly in the TWR header. Never use this counterexample in real projects, because overwriting the reference also risks leaking the first stream.

Since Java 10, you can use `var` for resources declared directly in the header:

```java
try (var reader = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    System.out.println(reader.readLine());
}
```

This illustrative snippet requires `path`, `Files`/`StandardCharsets` imports, and `IOException` handling. Using `var` does not change closing rules; the static type is inferred from the initializer.

## 5. Both `try` Body and `close()` Fail: Suppressed Exceptions

This is a critical reason to use TWR instead of careless manual cleanup.

Suppose:

1. The body throws `IllegalStateException("work failed")`.
2. When closing the second resource, `close()` throws `Exception("close second")`.
3. When closing the first resource, `close()` throws `Exception("close first")`.

If cleanup in `finally` is written carelessly, a `close` error can mask the exception from the body — losing the root cause. TWR follows these rules:

- When the **`try` body throws**, the body's exception is the **primary exception**.
- `close()` exceptions occurring during cleanup are attached to the primary via `Throwable.addSuppressed()`.
- If the **body does not throw** yet multiple `close()` calls throw, the exception from the **first** resource closed in reverse order becomes primary; subsequent close exceptions are suppressed.
- `getSuppressed()` returns an array of attached exceptions; **it is not `getCause()`**. Cause usually describes a causal chain; suppressed describes concurrent errors occurring during cleanup.

### Example 2 — Observing Primary and Suppressed Exceptions

Save **`SuppressedExceptionsDemo.java`**:

```java
public class SuppressedExceptionsDemo {
    static final class FailingResource implements AutoCloseable {
        private final String name;

        FailingResource(String name) {
            this.name = name;
            System.out.println("open " + name);
        }

        @Override
        public void close() throws Exception {
            System.out.println("close " + name);
            throw new Exception("close " + name + " failed");
        }
    }

    public static void main(String[] args) {
        try (FailingResource first = new FailingResource("first");
             FailingResource second = new FailingResource("second")) {
            throw new IllegalStateException("work failed");
        } catch (Exception ex) {
            System.out.println("primary: " + ex.getMessage());
            for (Throwable suppressed : ex.getSuppressed()) {
                System.out.println(
                    "suppressed: " + suppressed.getMessage()
                );
            }
        }
    }
}
```

Compile/run:

```bash
javac SuppressedExceptionsDemo.java
java SuppressedExceptionsDemo
```

Exact stdout:

```text
open first
open second
close second
close first
primary: work failed
suppressed: close second failed
suppressed: close first failed
```

Key takeaway: TWR **still attempts to close `first`** even after `second.close()` threw an error. The primary exception is `IllegalStateException("work failed")`, so both `close` errors are recorded in `getSuppressed()` in the order they occurred.

If you remove `throw new IllegalStateException("work failed")` and let the body finish normally, then **`second`'s close error** becomes primary and `first`'s close error becomes suppressed.

Do not log only `ex.getMessage()` and ignore suppressed exceptions. When analyzing I/O failures, you may need `ex.getSuppressed()`; many logging frameworks display them when logging the full exception stack trace, though detail levels depend on configuration.

### What If Opening the Second Resource Fails?

Another scenario:

```java
try (InputStream first = openFirst();
     InputStream second = openSecond()) {
    // ...
}
```

This is a **descriptive snippet**: `openFirst()` and `openSecond()` are illustrative functions returning `InputStream`. If `openFirst()` succeeds but `openSecond()` throws an exception, Java will **close `first`**. The exception from initializing `second` is primary; if `first.close()` also throws, `first`'s close error is suppressed. The `try` body **does not execute**, because not all resources were initialized.

For resources created **outside** the header before entering TWR, the caller must ensure they are brought into a closing scope or have a cleanup plan if initializing other objects fails. TWR does not automatically manage resources whose ownership it was not given.

## 6. Why Is TWR Better Than Manual `finally` Closing?

This simple manual approach looks correct at first glance:

```java
Resource resource = open();
try {
    doWork(resource);
} finally {
    resource.close();
}
```

This is **pseudocode**, with `Resource`, `open`, and `doWork` as illustrative names. The problem: if both `doWork` and `close` **throw exceptions**, the exception from `finally` can replace the primary exception, making debugging harder. Writing manual cleanup properly for multiple resources and suppressed exceptions requires complex try/catch logic where ordering mistakes are easy.

TWR corresponds to a compiler-generated `try/finally` mechanism that handles exceptions and cleanup systematically. For resources implementing `AutoCloseable`, prefer TWR to clarify ownership and reduce boilerplate.

Note: **TWR does not replace proper `catch` handling**. It handles closing automatically; read/write or close errors still need to be handled, declared, or translated into domain exceptions at the right boundary.

## 7. Managing Files with TWR in Java 17

With `Files`, `Path`, and common streams:

- `Files.newInputStream(path)` returns an `InputStream` that must be closed.
- `Files.newOutputStream(path, ...)` returns an `OutputStream` that must be closed.
- `Files.newBufferedReader(path, charset)` and `Files.newBufferedWriter(...)` return closeable readers/writers.
- `FileChannel.open(path, ...)` returns a closeable `FileChannel`.
- `Files.lines(path, charset)` returns a `Stream<String>` tied to the file; **the stream must be closed**.
- `Files.list(path)`, `Files.walk(path)`, and `Files.find(...)()` are also filesystem traversal streams that must be closed after use. For `Files.find`, use the exact API syntax when coding: `Files.find(path, maxDepth, matcher)`; do not invoke `Files.find(...)()` literally as printed in this shorthand.

A read/write workflow often has **two resources**: input and output. TWR closes output before input when input is declared before output.

### Example 3 — Copying Content Across Two Streams

Save **`CopyWithResourcesDemo.java`**:

```java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class CopyWithResourcesDemo {
    public static void main(String[] args) throws IOException {
        Path source = Files.createTempFile("twr-src-", ".txt");
        Path target = Files.createTempFile("twr-dst-", ".txt");

        try {
            Files.writeString(
                source, "Xin chào", StandardCharsets.UTF_8
            );

            try (InputStream in = Files.newInputStream(source);
                 OutputStream out = Files.newOutputStream(
                     target,
                     StandardOpenOption.WRITE,
                     StandardOpenOption.TRUNCATE_EXISTING
                 )) {
                in.transferTo(out);
            }

            System.out.println(
                "copied: " +
                Files.readString(target, StandardCharsets.UTF_8)
            );
        } finally {
            Files.deleteIfExists(target);
            Files.deleteIfExists(source);
        }
    }
}
```

Compile/run:

```bash
javac CopyWithResourcesDemo.java
java CopyWithResourcesDemo
```

Stdout when filesystem operations succeed:

```text
copied: Xin chào
```

The program creates two temporary files, writes UTF-8 text to the source, and then uses `InputStream.transferTo(OutputStream)` (Java 9+) to copy bytes to the target. If copying fails, TWR still attempts to close both `out` and `in`. Once TWR finishes, reading the target opens the file fresh. The `finally` block cleans up the temporary files.

**Example limitation:** cleanup in `finally` is an independent system operation that can throw `IOException` and mask an earlier error unless an appropriate handling policy is designed. The example prioritizes demonstrating TWR on two streams; in production, temp-cleanup/error-logging utilities need mechanisms that preserve the primary exception. Furthermore, the second `Files.createTempFile` call could fail after creating the first file but before entering `try/finally`, so this demo does not cover every failure scenario during **temporary file preparation**. Production designs must wrap resource creation within appropriate cleanup scopes.

`transferTo()` does not call `close()` for you; therefore, TWR is ideal for guaranteeing streams are closed even if reading, writing, or copying fails.

### Closing `Files.lines` and Filesystem Streams

Correct syntax:

```java
try (Stream<String> lines =
         Files.lines(path, StandardCharsets.UTF_8)) {
    long count = lines.filter(s -> !s.isBlank()).count();
    System.out.println(count);
}
```

This is an **illustrative snippet**. `path` is a `Path`; you need `import java.util.stream.Stream;`, `java.nio.file.Files`, `java.nio.charset.StandardCharsets`, and `IOException` handling. The stream is closed when exiting TWR.

Do not equate `stream.count()` or another terminal operation with `stream.close()`. Regular Java Streams do not necessarily require closing, but streams backed by files or directories must be closed per the API contract. With `Files.walk`, closing the stream also releases associated directory handles.

## 8. Wrapping Streams: Who Is Responsible for Closing?

Types like `BufferedInputStream`, `BufferedOutputStream`, `InputStreamReader`, `OutputStreamWriter`, `BufferedReader`, and `BufferedWriter` are typically **wrappers/decorators** around an underlying resource:

```text
FileInputStream ──► InputStreamReader(UTF-8) ──► BufferedReader
                                                      ▲
                                                 caller uses
                                                      │
                                                caller close()
                                                      ↓
                                              closes lower layers
```

With the standard I/O wrapper classes above, `close()` on the **outermost wrapper** normally closes the underlying stream/reader too. Therefore:

```java
try (BufferedReader reader = Files.newBufferedReader(
        path, StandardCharsets.UTF_8)) {
    String line = reader.readLine();
}
```

This is an **illustrative snippet**, with `path` as a `Path`, appropriate imports, and `IOException` handling. The caller owns `reader` and only needs to close `reader`. Since `Files.newBufferedReader` creates the underlying file layer itself, closing `reader` manages the lifecycle per that contract.

Do not arbitrarily manage the same resource under **multiple independent owners**. For example, a library receiving a caller-provided `OutputStream` may only be responsible for writing data and should not close it. APIs must explicitly define ownership:

- **Caller owns**: the library does not close the received stream; the caller closes it once all consumers are done.
- **Callee owns**: upon receiving the stream, the library manages and closes it; the caller must not continue using it.
- **Borrowed resource**: an object only borrows the resource for the duration of processing and has no authority to close the shared source.

Do not assume all third-party wrapper classes share the same closing behavior; read the specific class contract.

### `System.in`, `System.out`, `System.err`

The standard streams are process-wide global resources. Example:

```java
try (BufferedReader reader = new BufferedReader(
        new InputStreamReader(System.in, StandardCharsets.UTF_8))) {
    System.out.println(reader.readLine());
}
```

This is an **illustrative snippet**, but **requires careful consideration**: when TWR closes `reader`, it also closes `System.in`. If the program still needs stdin elsewhere, subsequent reads may fail. In a CLI that reads once and exits, this might be acceptable; in a library, REPL, or multi-part input program, never close a **borrowed** standard stream whose lifecycle you do not own.

Similarly, closing a custom `PrintWriter` or `BufferedWriter` wrapped around `System.out` can close stdout itself, causing subsequent prints to fail. For caller-supplied streams, the API should state whether it closes or only flushes.

### `close()` vs. `flush()`

`flush()` on a buffered writer/stream pushes buffered data **down to the underlying layer**, allowing continued use. `close()` ends the lifecycle and normally flushes pending data during closing. **Do not use `flush()` as a substitute for `close()`** when descriptors must be released; and **do not treat `close()` as `FileChannel.force()`** to claim data is durable on the device.

If a protocol requires sending a message immediately while the stream stays open, you may need to flush at the right business boundary before closing time.

## 9. TWR and JDBC: Closing Resources Is Not Committing a Transaction

JDBC resources such as `Connection`, `Statement`, `PreparedStatement`, and `ResultSet` can be used with TWR because they implement `AutoCloseable`. Typical declaration order is **Connection -> Statement -> ResultSet**, so closing occurs in **ResultSet -> Statement -> Connection** order.

Formal example:

```java
try (Connection conn = dataSource.getConnection();
     PreparedStatement stmt =
         conn.prepareStatement("SELECT id FROM items");
     ResultSet result = stmt.executeQuery()) {
    while (result.next()) {
        System.out.println(result.getLong("id"));
    }
}
```

This is an **illustrative snippet**, not a standalone program: `dataSource`, table `items`, a JDBC driver, `import java.sql.*`, and `SQLException` handling must exist in the application. This example cannot run without a properly configured database connection.

Crucially: **closing a Connection does not guarantee a transaction was committed**. With `autoCommit=false`, the application must follow an explicit commit/rollback policy. Behavior when closing a connection with an unresolved transaction can vary by driver, pool, and DBMS; never build financial workflows relying on "close will auto-commit".

Typical transaction management pattern:

```text
Open connection -> begin transaction
    -> execute operations
    ├─ success -> commit
    └─ failure -> rollback (if still possible)
Finally -> close / return connection to pool
```

TWR helps release resources; transaction logic still belongs to the business/database layer.

With a connection pool, `Connection.close()` may return a logical connection to the pool rather than closing the physical connection. That is a **pool/driver contract detail**, further showing that `close()` is an abstraction-lifecycle operation, not always "close physical socket immediately".

## 10. Handling Exceptions When Closing

### Checked Exceptions in Header and Body

If a variable in the header is typed as `AutoCloseable`, the compiler knows `close()` **can throw `Exception`**. Thus, the enclosing method must declare or catch an appropriate exception, even if the `try` body appears not to throw:

```java
static void use(AutoCloseable resource) throws Exception {
    try (resource) {
        System.out.println("using");
    }
}
```

This is an **illustrative method** (Java 9+) inside a valid Java class. `resource` is an effectively final parameter, and `throws Exception` satisfies the general close signature. In application APIs, prefer specific resource types whose `close()` declares a narrower exception instead of forcing every caller to catch broad `Exception`.

Conversely, `Closeable` narrows it to `IOException`, so programs can declare `throws IOException` when using streams with matching operations.

### When Do TWR's `catch` and `finally` Run?

```java
try (SomeResource r = create()) {
    work(r);
} catch (Exception ex) {
    report(ex);
} finally {
    markFinished();
}
```

This is **pseudocode** illustrating order: resource `r` has already finished closing or attempted to close **before** control transfers to the statement's `catch` and `finally`. If TWR closing throws when the body did not, `catch` can catch that close error. If the body threw, `catch` receives the primary exception with corresponding suppressed exceptions.

Do not add an unnecessary `r.close()` call inside `finally`: it may close the resource again, cause errors, or obscure ownership. Use `finally` for actions outside the resource's lifecycle when truly needed, and **avoid throwing new errors that mask the primary exception**.

### Limitations of Cleanup

TWR makes guarantees about **Java language control flow during normal execution**. It does not guarantee:

- That the machine cannot lose power or the process cannot be killed before `close()` finishes.
- That `close()` will always succeed. Filesystem or network errors can still occur.
- That a third-party `close()` method will not block indefinitely or have side effects.
- That once a resource is closed, a transaction is committed, data is synced to disk, or a remote service acknowledged it.
- That a resource can be reused after closing. Many readers/streams/channels throw errors if used afterward.

Therefore, if system requirements demand crash recovery, durable commits, or cross-file atomicity, you still need to design against the contracts of the filesystem, database, or protocol involved.

## 11. Common Mistakes and Fixes

| Mistake | Why It Is Wrong | Fix |
|---|---|---|
| Opening a stream and not closing it on error | Can leak file descriptors/handles | Declare resource in TWR |
| Assuming GC closes resources promptly | GC has no deterministic resource-cleanup schedule | Proactively close at scope end |
| Closing only the first resource when using several | Remaining resources may leak | Declare all scope-owned resources in TWR |
| Forgetting closing order | Outer layer depending on inner layer may need to close first | TWR closes in reverse declaration order |
| Manually calling `close()` inside TWR | Risks double closing; `AutoCloseable` is not required to be idempotent | Let TWR close once unless contract requires otherwise |
| Ignoring `getSuppressed()` | May miss cleanup failures | Log full exception details for diagnostics |
| Catching and swallowing all errors | May continue after read/write/cleanup failed | Decide retry, rollback, propagate, or report error |
| Throwing a new error in `finally` | Can mask the original error | Use TWR; avoid uncontrolled exceptions in cleanup |
| Wrapping `System.in` in TWR inside a library | Can close the caller's global stdin | Manage resource ownership properly |
| Assuming closing a connection commits | False for manual transactions | Commit/rollback explicitly |
| Forgetting to close `Files.lines`/`Files.walk` | File/directory handles may remain open | `try (Stream<?> s = Files...)` |
| Using `flush()` instead of `close()` | Flush does not release system resources | Use TWR and flush only when early push is needed |
| Relying on `close()` for crash durability | Close does not replace sync/fsync | Design durability explicitly |
| Returning a resource closed by TWR | Caller receives an unusable object | Do not wrap a returned resource in TWR |
| Catching overly broad `Exception` unnecessarily | Easy to hide bugs and makes APIs awkward | Choose specific resource types and checked exceptions |
| Giving a resource multiple owners | One closing causes errors for others | Define ownership and transfer rules clearly |

### Subtle Bug: Returning an Object Out of TWR

```java
static InputStream broken(Path path) throws IOException {
    try (InputStream in = Files.newInputStream(path)) {
        return in;
    }
}
```

This is a **design counterexample**. The method compiles, yet Java **closes `in` before completing the return**. The caller receives an already closed stream and typically cannot read from it. There are two proper designs depending on intent:

1. **Caller will read**: return the newly opened stream, documenting that the caller owns it and must close it with TWR.
2. **Method reads itself**: place `InputStream` in TWR, read the necessary data or construct a result object **independent** of the resource before returning.

Similarly, never return a JDBC `ResultSet` from a scope that has already closed its `Statement` or `Connection`.

## 12. Resource Scope Design Strategy

Classify resources by ownership:

```text
Current function creates the resource itself
    └── Function is responsible for closing; use TWR.

Function receives a resource owned by the caller
    └── Usually only borrows it for use; does not close it
        (unless the API explicitly transfers ownership).

Function creates a resource for the caller to use later
    └── Return the open resource + document that the caller must close it.

Wrapper owns the underlying resource
    └── Close the outermost wrapper per the wrapper's contract.
```

A common pattern is **keeping a resource alive for as short a time as possible while covering every operation that needs it**. Do not open a connection at the start of a request and hold it across unrelated wait steps; conversely, do not close too early while a lazy iterator, reader, or parser is still consuming it.

In code with callbacks or asynchronous tasks, TWR can **close too early** if the body only *schedules* a task and exits while the background task still needs the resource. In such cases, lifetime management must be tied to completion of the asynchronous task; never assume a callback will finish before the TWR block ends.

Some libraries provide closeable resources whose `close()` is not idempotent, has side effects, or can block or throw exceptions; check the contract and place timeouts/monitoring at the appropriate layer if resource hang is a risk.

## 13. Self-Check Questions

**Question 1.** What is the core difference between `Closeable` and `AutoCloseable`?

**Answer:** `Closeable extends AutoCloseable`, and `close()` declares `IOException` instead of `Exception`, fitting many I/O types. `Closeable` specifies that repeated closing has no effect; `AutoCloseable` does not require idempotency.

**Question 2.** In what order does `try (A a = ...; B b = ...)` open and close?

**Answer:** Initializes **a then b**, closes **b then a**. If initializing b fails, the already initialized a is still closed.

**Question 3.** Both the `try` body and `close()` throw errors; which exception is primary?

**Answer:** The body's error is primary; close errors are added to `getSuppressed()`. If the body succeeds but multiple closes fail, the error from the first resource closed is primary.

**Question 4.** Is `Throwable.getCause()` the same as `getSuppressed()`?

**Answer:** No. Cause represents the underlying cause of an exception; suppressed holds attached exceptions, such as errors thrown while closing resources in TWR.

**Question 5.** Can a variable declared outside TWR be used in `try (resource)` in Java 17?

**Answer:** Yes, if the variable is `final` or effectively final (a Java 9+ feature). After TWR, the variable remains in scope, but the resource is closed.

**Question 6.** Why shouldn't a library close `System.in`?

**Answer:** It is typically a global resource owned by the application/caller; a library closing a wrapper over `System.in` can close standard input, preventing other parts from reading further.

**Question 7.** Should `Files.lines(path)` be placed inside TWR even when using a terminal operation like `count()`?

**Answer:** Yes. A file-backed stream holds an open resource that must be closed; a terminal operation does not replace closing the stream's lifecycle.

**Question 8.** Does a `Connection` closed by TWR guarantee database writes were committed?

**Answer:** No. Transactions must follow an explicit commit/rollback policy; closing only ends the logical/physical connection lifecycle per the driver and pool.

**Question 9.** When should you NOT wrap a newly created resource in TWR?

**Answer:** When the goal is to **return an open resource** for the caller to use afterward; in that case, the caller takes ownership and responsibility for closing. Never return a stream that TWR has already closed.

**Question 10.** Can TWR be used as proof that a file is durably saved across power loss?

**Answer:** No. Closing a stream/writer is a lifecycle concern; durability requires evaluating filesystem and device sync mechanisms alongside business requirements.

**Key Takeaway:** `AutoCloseable` defines resource closeability; `Closeable` specializes it for I/O; `try-with-resources` builds closing into language structure in **reverse initialization order** and preserves primary exceptions via **suppressed exceptions**. To use them correctly, clarify **who owns the resource, usage scope, error-handling policy, and closing timing** — never relying on the garbage collector or equating close with commit/durability.
