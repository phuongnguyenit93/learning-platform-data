# `finalize()` Is Deprecated and Should Not Be Used for Resource Management — Java 17

## 1. Objectives and Key Takeaways

In Java, the **garbage collector (GC)** handles reclaiming the memory of objects that are no longer used by the program according to reachability rules. However, Java objects can also manage **off-heap resources**: file descriptors, network connections, sockets, JDBC connections, native memory, data streams, or business locks. An object becoming unreachable does **not** guarantee that those resources will be released **at the right time**.

Java used to provide a method inherited from `Object`:

```java
protected void finalize() throws Throwable
```

A class can override it to run “cleanup” code after the GC determines that the object is eligible for finalization. However, this mechanism has serious issues: **no invocation deadline**, **no invocation ordering**, difficult error control, high cost, risk of deadlock, object resurrection, and security issues. Therefore, **do not use `finalize()` to close files, sockets, database connections, or any resource that needs to be released reliably**.

Primary alternatives in Java 17:

- **`try-with-resources`** to ensure `close()` is executed at the end of the usage scope, including when an exception occurs.
- **`AutoCloseable` / `Closeable`** to declare and execute resource release explicitly, with clear ownership responsibility.
- **`try/finally`** if you must manage a cleanup operation that cannot yet be expressed with try-with-resources.
- **`Cleaner`** or **`PhantomReference`** in certain low-level situations as a **safety net**, not replacing a proactive `close()` call.
- Application **lifecycle management** to close/cancel/unregister at the appropriate time.

**Key takeaway:** *The GC manages memory reclaimability; the program manages when resources are closed.*

This lesson follows **Java 17** and explains in detail: deprecation history, the finalizer mechanism, limitations, alternatives, exception suppression, hierarchical resources, ownership, Cleaner, ReferenceQueue, testing, migrating away from `finalize()`, multiple standalone runnable programs, and exercises.

## 2. Distinguishing `finalize`, `final`, and `finally`

These three words look similar in spelling, yet are completely different in role:

| Concept | Role | Used to close resources? |
| --- | --- | --- |
| `finalize()` | Hook inherited from `Object`, which may be called by the finalization mechanism when processing an object | **Do not use** as a reliable cleanup approach |
| `final` | Modifier for a class, method, field, or local variable; restricts inheritance/overriding/reassignment | Does not perform cleanup itself |
| `finally` | Block executed according to the control flow of `try` (with limitations such as abrupt JVM termination) | Can perform cleanup, but `try-with-resources` is generally preferred |
| `close()` | Method declared in `AutoCloseable`, typically representing explicit release | **Yes**, if the implementation satisfies the contract |
| `try-with-resources` | Syntax `try (Resource r = ...) { ... }` that calls `close()` automatically upon exiting scope | **Preferred approach** |

### Comparison Example

```java
final class ConnectionOwner implements AutoCloseable {
    @Override
    public void close() {
        System.out.println("closed");
    }
}

try (ConnectionOwner owner = new ConnectionOwner()) {
    // Use the resource within the defined scope.
}
```

The snippet above illustrates valid source code inside an appropriate method/context; it **has no `finalize()`**. The class's `final` modifier does not cause `close()` to run. It is `try-with-resources` that guarantees `close()` is called when exiting via normal control flow or via an exception.

## 3. Deprecation History: Java 9, Java 17, and JDK 18

It is important to state the release milestones accurately:

1. **Java 9:** `Object.finalize()` was marked **deprecated** due to design issues.
2. **Java 17:** `Object.finalize()` still exists in the Java SE API and is annotated with `@Deprecated(since="9")`; the API docs advise against using it.
3. **JDK 18:** **JEP 421** marks the finalization mechanism and related APIs as **deprecated for removal**; this is an important milestone distinct from “deprecated” in Java 17.
4. Later JDKs may change policies for enabling, disabling, or removing finalization. When writing software, you must consider the **actual JDK being deployed**, rather than guessing future behavior from version numbers alone.

**Do not misstate:** “Java 17 removed `finalize()`” or “Java 17 first introduced deprecated-for-removal.” Neither is accurate. Java 17 still has the API, though its use is discouraged; the for-removal milestone is JDK 18.

### Why Still Learn About an Outdated API?

When maintaining applications, you may encounter:
- Legacy code overriding `finalize()` to close files/sockets.
- Older libraries that use finalizers.
- `javac -Xlint:deprecation` warnings.
- Heap/performance issues caused by finalizable objects.
- A requirement to migrate to a newer JDK.
- Vulnerabilities because a finalizer can observe a partially constructed object.

Understanding the legacy mechanism helps you **remove dependencies properly**, rather than learning it to create new finalizers.

## 4. What Does `Object.finalize()` Look Like?

In Java 17, the signature from `java.lang.Object`:

```java
@Deprecated(since = "9")
protected void finalize() throws Throwable
```

At the source level, a subclass can override it:

```java
class LegacyResource {
    @Override
    protected void finalize() throws Throwable {
        try {
            // Legacy example: delayed and unreliable cleanup.
        } finally {
            super.finalize();
        }
    }
}
```

**This is only an example for reading legacy code, not recommended code to use.** Do not put real resources that need to be closed into a new finalizer.

Characteristics:
- It is not a destructor as in some languages with manual memory management.
- It is not automatically called when a local variable goes out of scope.
- It does not run immediately when a reference is assigned `null`.
- It is not guaranteed to run before process exit.
- It can be delayed indefinitely.
- Exceptions from a finalizer do not behave like exceptions from an explicit `close()` call made by a caller.

### Do Not Call `finalize()` Manually Instead of `close()`

Calling `someObject.finalize()` directly from application code (even if accessibility permits it) is just an ordinary method call; it **does not make the object unreachable, does not replace GC, and does not guarantee idempotency**. If proactive cleanup is needed, declare **`close()`** with a clear contract.

## 5. Lifecycle: Object, Reference, Finalization, Resource

Let's model an object holding a native handle:

```text
[Client / GC root] ──strong ref──▶ [ResourceWrapper]
                                       │
                                       └──native handle──▶ [OS resource]
```

When the client no longer has a strong reference path to the wrapper:
- The JVM can detect that the wrapper is no longer strongly reachable.
- The GC can process the wrapper's memory/lifecycle when appropriate.
- A finalizer (if present and processed by the runtime) **is not guaranteed to run on time**, or may not run at all.
- File descriptors/sockets/native handles need to be released **early and deterministically**, without relying on the wrapper eventually being garbage-collected.
- When the application calls `close()`, the wrapper may still be reachable while the OS resource is already closed. This is the **desired outcome**.

### Two Different Lifecycles

**Java object lifecycle**: allocation → remains reachable → may become unreachable → GC may reclaim.

**Resource lifecycle**: acquire → use → **release/close** according to the application contract.

Do not force a resource to wait for the object to die. Conversely, an object can continue to exist after the resource has closed, for example to provide metadata, `isClosed()` state, or logging.

## 6. Why Is Finalizer Execution Timing Unpredictable?

There is no API deadline such as:
- “GC must run within 100 ms after `obj = null`.”
- “The finalizer must run before the caller method returns.”
- “`System.gc()` must finish all finalizers.”
- “Normal process termination will run all finalizers.”

None of these four statements is a **Java 17 guarantee**.

The JVM can defer GC based on memory pressure and collector policies. A small process that exits quickly often has no reason to run a full GC. Furthermore, source scope and liveness do not coincide; a local variable no longer being used is not a finalizer event.

With scarce resources (file descriptors, DB connections), you can run out of resources **before** heap pressure causes GC to care.

### Practical Risk

An application may have spare heap while opening very many sockets/file descriptors. It can hit “too many open files” or pool starvation because it relies on GC to call finalizers. Increasing the heap sometimes delays finalization even longer, without solving the root cause.

## 7. Runnable: A Resource with Deterministic `close()`

Save **`ExplicitCloseDemo.java`**:

```java
final class DemoResource implements AutoCloseable {
    private boolean closed;

    void use() {
        if (closed) {
            throw new IllegalStateException("resource closed");
        }
        System.out.println("using");
    }

    boolean isClosed() {
        return closed;
    }

    @Override
    public void close() {
        if (!closed) {
            closed = true;
            System.out.println("closed");
        }
    }
}

public class ExplicitCloseDemo {
    public static void main(String[] args) {
        DemoResource resource = new DemoResource();

        resource.use();
        resource.close();

        System.out.println(resource.isClosed());
    }
}
```

Compile and run:

```bash
javac --release 17 -encoding UTF-8 ExplicitCloseDemo.java
java ExplicitCloseDemo
```

**Exact** stdout:

```text
using
closed
true
```

The example implements an idempotent `close()`: calling it multiple times does not release twice. `AutoCloseable` in general **does not require every implementation to be idempotent**, so if an API allows closing multiple times, document/implement that behavior clearly.

## 8. Prefer `try-with-resources`

`try-with-resources` has been supported in Java since Java 7. When a resource implements `AutoCloseable`, the construct:

```java
try (DemoResource resource = new DemoResource()) {
    resource.use();
}
```

automatically calls `resource.close()` upon exiting the try statement according to language rules.

Benefits:
- Makes the resource's **ownership scope** visible.
- Prevents forgetting to close on `return` branches or ordinary exceptions.
- Multiple resources are closed in reverse order of declaration.
- Exceptions from `close` are handled via **suppressed exceptions** if the try body already has a primary exception.
- Code is typically shorter and more consistent than manual `try/finally`.

### Does Not Mean Closing Every Object in the Block

Only the resource variables listed in `try (...)` have their `close()` auto-invoked. A `StringBuilder` created inside the block does not automatically have `close()`; it is just an ordinary Java object.

## 9. Runnable: try-with-resources Always Calls `close()`

Save **`TryWithResourcesDemo.java`**:

```java
final class AuditResource implements AutoCloseable {
    AuditResource() {
        System.out.println("open");
    }

    void use() {
        System.out.println("use");
    }

    @Override
    public void close() {
        System.out.println("close");
    }
}

public class TryWithResourcesDemo {
    public static void main(String[] args) {
        try (AuditResource resource = new AuditResource()) {
            resource.use();
        }

        System.out.println("after");
    }
}
```

```bash
javac --release 17 -encoding UTF-8 TryWithResourcesDemo.java
java TryWithResourcesDemo
```

Stdout:

```text
open
use
close
after
```

`close` happens **before** the after statement. There is no need to predict GC, no need for `System.gc()`, or a legacy finalizer.

## 10. What If Code in try Throws an Exception?

`try-with-resources` still closes the resource if resource creation succeeded. The exception from the try body is propagated after Java performs cleanup according to the rules.

```java
try (AuditResource resource = new AuditResource()) {
    throw new IllegalStateException("problem");
}
```

This is a snippet and must not be mistaken for a full program. Note that Java has special rules if resource acquisition or close also throws an error; suppression will be explained separately.

**Do not rely on `finally`/`close` when the process is killed abruptly, the JVM halts, or hardware fails.** Determinism under Java control flow does not mean a guarantee against external system failures.

## 11. Runnable: Cleanup Even When an Exception Occurs

Save **`ExceptionCloseDemo.java`**:

```java
final class Resource implements AutoCloseable {
    @Override
    public void close() {
        System.out.println("close");
    }
}

public class ExceptionCloseDemo {
    public static void main(String[] args) {
        try (Resource resource = new Resource()) {
            System.out.println("work");
            throw new IllegalStateException("failed");
        } catch (IllegalStateException error) {
            System.out.println("caught:" + error.getMessage());
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ExceptionCloseDemo.java
java ExceptionCloseDemo
```

Stdout:

```text
work
close
caught:failed
```

There is no “finalize ran” line. Cleanup runs due to a **language construct**, not the collector.

## 12. Multiple Resources Are Closed in Reverse Order

When declaring:

```java
try (Resource a = new Resource("A");
     Resource b = new Resource("B")) {
    // ...
}
```

Java closes **B before A**. This matches dependency stacks: the object created last should generally be released before the original object.

### What to Distinguish

**The close order in try-with-resources** has clear language rules.

**The order of finalizers across multiple objects** is unspecified. Therefore, if a Child resource needs to use a Parent resource during cleanup, finalizers do not provide a reliable dependency-order mechanism.

## 13. Runnable: Reverse-Order Close

Save **`CloseOrderDemo.java`**:

```java
final class NamedResource implements AutoCloseable {
    private final String name;

    NamedResource(String name) {
        this.name = name;
        System.out.println("open:" + name);
    }

    @Override
    public void close() {
        System.out.println("close:" + name);
    }
}

public class CloseOrderDemo {
    public static void main(String[] args) {
        try (NamedResource a = new NamedResource("A");
             NamedResource b = new NamedResource("B")) {
            System.out.println("work");
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 CloseOrderDemo.java
java CloseOrderDemo
```

Stdout:

```text
open:A
open:B
work
close:B
close:A
```

If cleanup order matters, the architecture should express it through explicit scopes/dependency management as in the example, not by relying on the order in which the GC chooses to process objects.

## 14. Suppressed Exceptions: Preserving the Original Error

If code in the try body throws an exception **and** `close()` also throws an exception:
- The exception from the try body is typically the **primary exception**.
- The exception from `close()` is typically a **suppressed exception**, accessed via `getSuppressed()`.
- As a result, the “work execution failed” error is not silently overwritten by the second error during cleanup.

This is a helpful difference between `try-with-resources` and certain careless ways of writing a manual `finally`.

### The `AutoCloseable.close()` Method

The `AutoCloseable` API declares `void close() throws Exception`. Implementations may choose to throw a narrower checked exception type, or throw no checked exception at all. `java.io.Closeable.close()` declares `IOException` and has a specific contract for I/O resources.

## 15. Runnable: Observing a Suppressed Exception

Save **`SuppressedExceptionDemo.java`**:

```java
import java.io.IOException;

final class FailingResource implements AutoCloseable {
    @Override
    public void close() throws IOException {
        throw new IOException("close-failed");
    }
}

public class SuppressedExceptionDemo {
    public static void main(String[] args) {
        try (FailingResource resource = new FailingResource()) {
            throw new IOException("work-failed");
        } catch (IOException error) {
            System.out.println(error.getMessage());
            System.out.println(error.getSuppressed().length);
            System.out.println(error.getSuppressed()[0].getMessage());
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 SuppressedExceptionDemo.java
java SuppressedExceptionDemo
```

Stdout:

```text
work-failed
1
close-failed
```

The original error message is still preserved. If you use a manual `finally` and throw a new exception without managing it explicitly, you can accidentally mask the initial exception.

## 16. When Resource Acquisition in a Constructor Fails

An easily overlooked point: **a constructor can also throw an exception** midway. If acquisition occurs in multiple steps:

```java
ResourceA a = acquireA();
ResourceB b = acquireB(); // May fail.
```

when B fails, A needs to be released. `try-with-resources` allows Java to close the resources **that were previously created successfully** in the resource specification.

```java
try (ResourceA a = acquireA();
     ResourceB b = acquireB()) {
    use(a, b);
}
```

This is a design snippet, assuming `ResourceA` and `ResourceB` implement `AutoCloseable`.

**If a resource's constructor acquires partial resources and then throws an exception before the object is successfully registered in try-with-resources**, the constructor/factory itself must clean up the resources acquired during the failed attempt. Try-with-resources **cannot close a resource variable that did not finish initializing successfully**.

## 17. Runnable: Second Resource Fails During Initialization

Save **`ResourceAcquisitionFailureDemo.java`**:

```java
final class AResource implements AutoCloseable {
    AResource() {
        System.out.println("A-open");
    }

    @Override
    public void close() {
        System.out.println("A-close");
    }
}

final class BResource implements AutoCloseable {
    BResource() {
        System.out.println("B-start");
        throw new IllegalStateException("B-failed");
    }

    @Override
    public void close() {
        System.out.println("B-close");
    }
}

public class ResourceAcquisitionFailureDemo {
    public static void main(String[] args) {
        try (AResource a = new AResource();
             BResource b = new BResource()) {
            System.out.println("body");
        } catch (IllegalStateException error) {
            System.out.println(error.getMessage());
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ResourceAcquisitionFailureDemo.java
java ResourceAcquisitionFailureDemo
```

Stdout:

```text
A-open
B-start
A-close
B-failed
```

A was created successfully, so it is auto-closed. B's constructor throws an exception, so `B-close` is **not** called by try-with-resources; if B opened OS resources before throwing, B's constructor/factory must clean up what it opened.

## 18. Resource Ownership: Who Is Responsible for `close()`?

To use `AutoCloseable` properly, you must identify the **owner**:
- Which code calls acquire/open?
- Who is allowed to use the resource?
- When does the scope end?
- Who is responsible for closing?
- Are there borrowers that only borrow the resource and must not close it?
- If the resource is returned from a factory, how is ownership transferred?

Example of a method returning an `InputStream` that the caller must close:

```java
InputStream openData() throws IOException {
    return Files.newInputStream(path);
}
```

**Snippet:** `path` must exist in an appropriate context. If a factory returns an open stream, document “caller owns and must close”.

A method that merely **receives a resource to use** should not arbitrarily close a caller-owned resource unless the contract specifies ownership transfer.

### Ownership Prevents Two Categories of Bugs

1. **Resource leak**: nobody closes it.
2. **Use-after-close/double-close**: multiple parties think they are the owner, leading to premature or duplicate closing.

Choose one clear owner and one proper cleanup point.

## 19. `Closeable` and `AutoCloseable`

`AutoCloseable`:
- General-purpose, has the method `close() throws Exception`.
- Used in try-with-resources.
- Suitable for many kinds of resources: database connections, custom handles, subscriptions.

`Closeable`:
- Belongs to `java.io`, extends `AutoCloseable`.
- `close() throws IOException`.
- Has a specific contract for closeable I/O objects and requires closing multiple times to have no effect once already closed according to the API.

Not every Java object needs to implement `AutoCloseable`. An immutable value object such as `record Point(int x,int y)` that holds no off-heap resources does not need `close()`.

### Avoid `AutoCloseable` Just to Get `try` Syntax

If an object does not genuinely have a resource lifetime, adding `AutoCloseable` with an empty `close()` makes the API confusing and creates false expectations about ownership.

## 20. Runnable: Writing a Stateful `Closeable`

Save **`CustomCloseableDemo.java`**:

```java
import java.io.Closeable;
import java.io.IOException;

final class TextHandle implements Closeable {
    private boolean closed;

    String read() {
        if (closed) {
            throw new IllegalStateException("closed");
        }
        return "data";
    }

    @Override
    public void close() throws IOException {
        if (!closed) {
            closed = true;
            System.out.println("release");
        }
    }
}

public class CustomCloseableDemo {
    public static void main(String[] args) throws IOException {
        TextHandle handle = new TextHandle();

        try (handle) {
            System.out.println(handle.read());
        }

        System.out.println("done");
    }
}
```

```bash
javac --release 17 -encoding UTF-8 CustomCloseableDemo.java
java CustomCloseableDemo
```

Stdout:

```text
data
release
done
```

Java 9 and later support **final or effectively final** resource variables declared before `try` inside `try (handle)`. In Java 17 this is stable syntax. There is no need to call `finalize()`.

## 21. Using `finally` When try-with-resources Is Not Possible

If an API does not yet implement `AutoCloseable`, you may need:

```java
Resource resource = acquire();
try {
    use(resource);
} finally {
    release(resource);
}
```

This is an API-dependent **snippet**, not a standalone runnable example. If you control the interface, consider wrapping the resource in an adapter implementing `AutoCloseable` so you can call:

```java
try (ResourceAdapter adapter = new ResourceAdapter(...)) {
    adapter.use();
}
```

### Be Careful with Exception Ordering in finally

If the body already threw and `finally` also throws, the second exception can mask the first. With `AutoCloseable`, try-with-resources manages suppressed exceptions, preserving better diagnostic information.

### Do Not Write Cleanup When There Are No Resources to Clean Up

`finally` is also used to restore state/unlock in some APIs. However, not every method needs a `finally`; use it when there is a side effect/acquisition that requires a guaranteed balancing action.

## 22. Runnable: `finally` Cleanup via Control Flow

Save **`ManualFinallyDemo.java`**:

```java
public class ManualFinallyDemo {
    static void process() {
        boolean acquired = false;

        try {
            acquired = true;
            System.out.println("work");
            throw new IllegalStateException("failure");
        } finally {
            if (acquired) {
                System.out.println("cleanup");
            }
        }
    }

    public static void main(String[] args) {
        try {
            process();
        } catch (IllegalStateException error) {
            System.out.println(error.getMessage());
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ManualFinallyDemo.java
java ManualFinallyDemo
```

Stdout:

```text
work
cleanup
failure
```

The driving mechanism is exception unwinding, not GC. For real `AutoCloseable` resources, prefer try-with-resources because it expresses ownership more clearly.

## 23. Files and Streams: Replacing Finalizers with Explicit Scopes

A legacy class using `finalize()` to close a file stream is usually hiding **who owns the stream**. When refactoring, clarify the owner, return the resource to a responsible caller, or wrap the entire I/O operation in `try-with-resources`. For example, `Files.lines(path)` returns a stream that can hold a file handle so the caller must close it per contract, whereas an in-memory stream like `Stream.of(...)` has no equivalent file handle.

If an API returns an `InputStream` from a factory, clearly document that the caller is responsible for closing it. If a method only borrows a stream, do not close the caller's resource unless the contract allows ownership transfer. This is the principle for fixing finalizer bugs; detailed examples of `BufferedReader`, `Files.lines`, and close errors belong in the AutoCloseable/TWR lesson.

## 24. JDBC: Closing Logical Resources, Not Waiting for Finalization

`Connection`, `Statement`/`PreparedStatement`, and `ResultSet` have deterministic lifecycles in JDBC. Do not put `finalize()` on a DAO/entity hoping that the connection will be returned to the pool when the JVM collects the object. Instead, place an explicit `close()` according to scope; in a connection pool, `Connection.close()` typically returns the **logical connection** to the pool, not necessarily closing the physical socket.

A migration review must determine: who acquires the connection, who commits/rolls back the transaction, who owns the statements and result sets, whether a connection is held in a singleton, and whether code paths close properly when exceptions occur. `try-with-resources` helps close resources but **does not automatically commit or roll back with proper business semantics** in place of transaction management. Examples with multiple JDBC resources and close order are covered in the dedicated AutoCloseable/TWR lesson.

## 25. Sockets and Network Resources: Separating Connection Lifecycle from GC

A socket has its own OS/protocol resources and implements `Closeable`. When an operation owns a `Socket`, close it promptly with `close()` (usually inside `try-with-resources`), rather than writing a finalizer or calling `System.gc()` to “rescue” exhausted file descriptors. If a helper only borrows an input/output stream from a socket, understand the API ownership: closing a stream may affect the shared socket.

When migrating away from finalizers, what needs checking is **the connection lifecycle and who is responsible for closing**, including when handshake, I/O, timeout, or exceptions occur. Java's mechanism for closing multiple resources and handling suppressed errors is explained in the AutoCloseable/TWR lesson; the focus here is why finalization cannot replace that contract.

## 26. Why `System.gc()` Does Not Solve Resource Leaks

A lot of legacy code tries:

```java
resource = null;
System.gc();
System.runFinalization();
```

This is an **anti-pattern**, not a solution.

- `resource = null` only clears one reference; the object may still have other references.
- `System.gc()` is a GC request, not a reclamation deadline.
- `System.runFinalization()` does not make the cleanup model deterministic; it is also a legacy API tied to finalization.
- Waiting for a finalizer cannot guarantee release before the pool/file descriptors are exhausted.
- Relying on explicit GC often puts pressure on performance and does not fix the ownership bug.

**Proper fix:** close the resource when done and reduce/release references holding it, rather than asking the collector to fix lifecycle bugs for you.

## 27. Why Finalizers Cause Performance Problems

An object requiring finalization typically goes through extra GC/runtime processing paths compared to an ordinary object. This can lead to:
- Overhead for tracking and processing finalizable objects.
- Objects/resources surviving longer than expected.
- A backlog of finalizers waiting to be processed.
- Increased pressure on memory or off-heap resources.
- Unpredictable latency.

Do not assume a **fixed** cost or number of GC cycles across all JVMs/collectors/versions. Actual measurements may vary, yet the JDK docs consistently warn of performance issues.

### When Resource Cleanup Is Slow

A finalizer waiting on I/O/locks or executing a blocking operation can delay other finalization tasks depending on the runtime implementation. As the backlog grows, resource leaks look as if “the GC refuses to collect,” when the root cause is attaching cleanup to a flow with no timing guarantee.

## 28. Why Finalizers Can Deadlock or Hang

A finalizer runs outside the thread or ordering explicitly arranged by the application. If it:
- Waits on a lock currently held by another thread;
- Waits for an event from a thread that depends on the resource needing release;
- Performs unbounded blocking I/O;
- Waits on a monitor during application shutdown;

it can create a deadlock/hang or a backlog.

**Do not build designs assuming “finalizer A must run before finalizer B”**: there is no guaranteed ordering of finalizers. A resource graph with dependencies all the more requires an explicit `close()` with a clear owner and reverse-order scopes.

### Analysis Example, Non-Runnable

```java
@Override
protected void finalize() throws Throwable {
    waitForOtherComponent(); // May wait forever.
}
```

This is a **legacy anti-pattern snippet**, not a runnable program. A finalizer is not a safe place to synchronize with or wait on another service.

## 29. Exceptions in `finalize()` Are Not Like Exceptions from `close()`

In the finalization API:
- Exceptions thrown by a finalizer are not reported as exceptions from a `close()` call in the corresponding application method.
- They may be ignored by the finalization mechanism; the application has no try/catch at the actual call site to handle them according to business semantics.
- Errors closing OS resources can be hidden, causing the issue to appear later as resource starvation.

With an explicit `close()`:
- The caller has a point to catch `IOException` or appropriate checked exceptions.
- Context can be logged, retries attempted if valid, business errors reported, or recovery performed.
- Try-with-resources has the suppressed exceptions mechanism to preserve the primary error.

**If resource release errors matter**, do not place them in a hook where the caller has no opportunity to handle them at the right time.

## 30. A Finalizer May Be Skipped Completely

In situations such as:
- The process exits before GC/finalization processes the object;
- The JVM is terminated/halted;
- GC does not need to run during the program's lifetime;
- Runtime policy disabling finalization on JDKs that support it;
- Implementation-specific conditions;

the application must not expect every object with a finalizer to be processed by that finalizer.

The takeaway is neither “finalizers rarely run” nor “they always run,” but that **the API does not provide the necessary guarantees** to serve as a proper resource manager.

### Do Not Write Unit Tests Waiting for a Finalizer

A test that calls `Thread.sleep(1000)` and asserts that a finalizer counter increased is unreliable. It depends on the scheduler/GC/timing and can be flaky. Test `close()` instead of waiting on a mechanism outside the test's control flow.

## 31. Object Resurrection: Finalizers Can Revive an Object

A finalizer can accidentally or intentionally publish `this` to a long-lived reference, such as a static field or registry. When that happens, the object can return to a reachable state after finalization has begun.

Diagram:

```text
Before:
no strong roots ──X──▶ LegacyObject

In finalizer:
static Registry.saved = this;

After:
GC root → Registry.saved → LegacyObject
```

This is called **object resurrection**.

### Risks

- It cannot be assumed that “finalization ran” means the object can never be accessed again.
- The object's state may no longer satisfy expected invariants.
- Running the finalizer once does not handle cleanup on subsequent times the object loses reachability after resurrection.
- It is difficult to ensure the resource is in a valid open/closed state.

Under the traditional finalization model, an instance's finalizer **is not automatically invoked a second time by the JVM** just because the instance was resurrected and then became unreachable again. Do not use resurrection to manage lifecycle.

## 32. Reading Legacy Resurrection — Do Not Practice as Cleanup

```java
class DangerousLegacy {
    static DangerousLegacy saved;

    @Override
    protected void finalize() throws Throwable {
        try {
            saved = this;
        } finally {
            super.finalize();
        }
    }
}
```

**This is a legacy anti-pattern snippet; there is no run command or stdout.** This override may cause `saved` to be assigned under circumstances where the finalizer runs, yet it is impossible to predict when GC/finalization occurs. Do not instruct developers to call `System.gc()` to “test resurrection” and then rely on timing.

### Design Implications

Do not place critical cleanup logic in a method that can itself make the object reachable again. Design an idempotent `close()`, control state, and avoid leaking references to partially destroyed resources.

## 33. Finalizer Attack and Failed Object Construction

A well-known security issue with finalization is the **finalizer attack**: if a superclass constructor performs permission checks/validation and throws an exception, an untrusted subclass can inherit/write a finalizer in a way that gives an unsuccessfully initialized object a chance to leak a reference externally.

This falls under the class of problems involving **partially initialized objects**, inheritance, and the ability of a finalizer to run independently of whether application construction succeeded.

Key lessons:
- Do not assume “the constructor threw an exception” automatically prevents all code of the object/subclass from running afterward under the legacy finalization mechanism.
- Do not allow an object that has not passed validation to enter a global registry.
- For a security-sensitive class, consider making the class final, tightening constructor visibility, using factory APIs, enforcing invariants, and eliminating finalization from the hierarchy.
- When auditing legacy code, look for `finalize()` overrides in both subclasses and external libraries.

**Do not use exploit examples** for resource management; the goal is to recognize why an API with hard-to-control security implications has been deprecated.

## 34. What Is `Cleaner`?

Java provides `java.lang.ref.Cleaner`, which uses phantom reachability/ReferenceQueue mechanisms to manage registered cleaning actions.

A pattern:

```java
private static final Cleaner CLEANER = Cleaner.create();

private final Cleaner.Cleanable cleanable;

// When explicit release is needed:
cleanable.clean();
```

Essential points:
- When `cleanable.clean()` is called explicitly, the action can run **proactively**, without waiting for GC.
- If the application forgets to close, Cleaner **may** run the action after the referent becomes phantom reachable according to runtime rules.
- **There is no guarantee that Cleaner runs automatically before process exit**, nor is there any deadline.
- The cleaning action should be fast, non-blocking, safe for concurrent execution, and independent of object state that has already become inaccessible.
- The cleaning action **must not hold a strong reference to the registered object**. If the action captures the referent itself, it can prevent the object from becoming phantom reachable and prevent Cleaner from automatically invoking it.

**Conclusion:** Cleaner is a **safety net**, while proactive `close()` remains the primary path.

## 35. Runnable: Cleaner with Explicit Close and Deterministic Output

Save **`CleanerBackstopDemo.java`**:

```java
import java.lang.ref.Cleaner;
import java.util.concurrent.atomic.AtomicBoolean;

final class NativeLikeHandle implements AutoCloseable {
    private static final Cleaner CLEANER = Cleaner.create();

    private static final class State implements Runnable {
        private final int id;
        private final AtomicBoolean released = new AtomicBoolean();

        State(int id) {
            this.id = id;
        }

        @Override
        public void run() {
            if (released.compareAndSet(false, true)) {
                System.out.println("release:" + id);
            }
        }

        boolean isReleased() {
            return released.get();
        }
    }

    private final State state;
    private final Cleaner.Cleanable cleanable;

    NativeLikeHandle(int id) {
        this.state = new State(id);
        this.cleanable = CLEANER.register(this, state);
    }

    boolean isReleased() {
        return state.isReleased();
    }

    @Override
    public void close() {
        cleanable.clean();
    }
}

public class CleanerBackstopDemo {
    public static void main(String[] args) {
        NativeLikeHandle handle = new NativeLikeHandle(42);

        handle.close();
        handle.close();

        System.out.println(handle.isReleased());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 CleanerBackstopDemo.java
java CleanerBackstopDemo
```

Stdout:

```text
release:42
true
```

- `State` is a **static nested class** and does not capture `NativeLikeHandle`.
- `CLEANER.register(this, state)` tracks the handle as the referent and State as the action.
- `close()` calls `cleanable.clean()`; the action is executed **at most once** per the Cleaner contract.
- `AtomicBoolean` explicitly reinforces idempotency at the resource state layer.
- The output is deterministic because the application **calls close directly**, without waiting for GC.
- This snippet simulates a native handle ID and release log; production code must invoke the real release API and handle concurrent close/use and errors appropriately.

### Do Not Copy This Pattern for Every Object

`Cleaner` has overhead and complexity. If an object holds no special resource, regular GC suffices for heap memory. If an object holds a resource, the default solution is `AutoCloseable`/try-with-resources; Cleaner is only an intentional supplementary defense layer.

## 36. Anti-Pattern: Cleaning Action Capturing the Referent Itself

Wrong:

```java
final class BrokenHandle {
    private static final java.lang.ref.Cleaner CLEANER =
            java.lang.ref.Cleaner.create();

    private final java.lang.ref.Cleaner.Cleanable cleanable;

    BrokenHandle() {
        cleanable = CLEANER.register(
                this,
                () -> System.out.println(this.toString()));
    }
}
```

This snippet **can compile**, yet has a lifecycle bug: the lambda holds a reference to `this`, keeping the referent strongly reachable through the action. Because the referent does not reach phantom reachability as intended, **the automatic cleaner action may never be called**.

Fix:
- Separate the state needing cleanup into an independent **static nested State**.
- Register `CLEANER.register(this, state)`.
- State holds only the native handle/metadata to be released and does **not** point back to the referent.
- Ensure the action is idempotent and does not block for long.
- Always provide an explicit `close()`.

### Do Not Use a Non-Static Inner Class as State

A non-static inner class typically carries an enclosing-instance association, which can retain the resource owner itself. The JDK Cleaner API recommends static state to avoid accidentally holding a back-reference to the object.

## 37. `Cleaner` Still Does Not Solve Every Situation

Cleaner does **not** guarantee:
- Closing the resource within a deterministic time after the last reference.
- Running when the process is killed or the application calls halt.
- Running in a specific order across different objects.
- Running before an external system timeout.
- Completing all queued cleaning actions on exit.
- Supporting business retries or propagating release errors to the right caller like an explicit `close()`.

A Cleaner action should avoid throwing exceptions (exceptions in an asynchronous cleaner action are generally ignored per API behavior), avoid holding locks for long, and avoid depending on other resources that might already be closed.

### When Should You Consider Cleaner?

- A native/off-heap resource wrapper that uses explicit close as its primary path.
- You need a safety net for programmer errors where close is forgotten.
- You have small cleanup state that can be separated from the referent.
- Fallback cleanup with no deadline is acceptable.
- You have metrics and tests proving that explicit close runs properly.

Do not use Cleaner to perform transaction commit/rollback, send network business events, or release resources with time-bound SLAs.

## 38. `PhantomReference` and `ReferenceQueue`

A lower-level option than Cleaner is combining:
- `PhantomReference<T>`;
- `ReferenceQueue<T>`;
- A tracker for references/states;
- A cleanup worker/logic that processes references when enqueued.

`PhantomReference.get()` **always returns null**, preventing access to the referent through the phantom reference. It is used for post-mortem reachability tracking and cleanup coordination, not as a “weak reference where get() still works”.

Compared to Cleaner:
- Requires code to manage the queue, strong retention of reference objects, and cleanup bookkeeping.
- Requires handling thread lifecycle/errors/race conditions.
- Very easy to introduce leaks if the cleanup state retains the referent.
- Has no timing guarantee.
- Typically suitable only for library/platform code.

**At the typical application level, use `AutoCloseable` first.**

## 39. Runnable: Phantom Reference Does Not Return the Object

Save **`PhantomReferenceDemo.java`**:

```java
import java.lang.ref.PhantomReference;
import java.lang.ref.Reference;
import java.lang.ref.ReferenceQueue;

public class PhantomReferenceDemo {
    public static void main(String[] args) {
        Object object = new Object();
        ReferenceQueue<Object> queue = new ReferenceQueue<>();

        PhantomReference<Object> phantom =
                new PhantomReference<>(object, queue);

        System.out.println(phantom.get() == null);

        Reference.reachabilityFence(object);
        System.out.println("no-gc-assumption");
    }
}
```

```bash
javac --release 17 -encoding UTF-8 PhantomReferenceDemo.java
java PhantomReferenceDemo
```

Stdout:

```text
true
no-gc-assumption
```

Do not assert that the queue already contains an element. Enqueue timing depends on GC. `Reference.reachabilityFence(object)` keeps the object reachable up to the point where the fence is called in the program; it does **not** cause the object to be collected afterward.

## 40. What Is `Reference.reachabilityFence` Used For?

Some native-resource wrappers encounter liveness optimization situations where the Java wrapper is no longer needed for Java statements while native work is still in progress.

The marker:

```java
Reference.reachabilityFence(wrapper);
```

helps ensure the wrapper is treated as **strongly reachable up to the fence point** per the API. It is **not**:
- A GC command;
- A replacement for `close()`;
- A guarantee that cleanup happens after the fence;
- A way to keep an object alive forever.

If resource code already uses try-with-resources/close properly, reachabilityFence is usually unnecessary. It is a specialized tool for library/native-integration authors who thoroughly understand the object/native-handle relationship.

## 41. How to Handle Proactive Cleanup Errors

When `close()` throws an `IOException` or domain exception:
- Preserve the original exception and suppressed exceptions.
- Do not swallow errors that lose critical transaction state.
- Attach appropriate context to logs and avoid exposing secrets.
- Only retry release if the API permits it and the operation is idempotent/safe.
- Set resource state to `CLOSING`/`CLOSED` if thread safety is needed.
- Do not hold broad locks during blocking cleanup.
- Do not push all errors into an asynchronous finalizer where the caller cannot handle them.

### A Note on Idempotency

Many `close()` operations should be idempotent, though `AutoCloseable` does not strictly require it. If your resource can be closed along multiple code paths, **design and clearly document** repeat-close behavior rather than assuming all libraries behave the same way.

## 42. Runnable: Idempotent Close Testable Without GC

Save **`IdempotentCloseDemo.java`**:

```java
final class SafeHandle implements AutoCloseable {
    private int releaseCount;
    private boolean closed;

    void use() {
        if (closed) {
            throw new IllegalStateException("closed");
        }
    }

    int releaseCount() {
        return releaseCount;
    }

    @Override
    public void close() {
        if (!closed) {
            closed = true;
            releaseCount++;
        }
    }
}

public class IdempotentCloseDemo {
    public static void main(String[] args) {
        SafeHandle handle = new SafeHandle();

        handle.use();
        handle.close();
        handle.close();

        System.out.println(handle.releaseCount());

        try {
            handle.use();
        } catch (IllegalStateException error) {
            System.out.println(error.getMessage());
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 IdempotentCloseDemo.java
java IdempotentCloseDemo
```

Stdout:

```text
1
closed
```

The test verifies the contract **proactively enforced by the code**: release once and reject use-after-close. There is no `System.gc()` or sleeping while waiting for a finalizer.

## 43. A Resource Wrapper with Clear State and Ownership

A good wrapper:
- Knows whether it is open or closed.
- Exposes `close()` as a clear public API.
- Separates ownership from borrowed references.
- Prevents operations after close if invalid.
- Closes child resources in an order compatible with dependencies.
- Has a strategy when acquisition fails midway.
- May add a Cleaner safety net for a native handle if needed.
- Does not use a finalizer.

A bad wrapper:
- Makes it impossible to tell when the resource is released.
- Has a `finalize()` that logs without a `close()`.
- Relies on the caller setting references to null.
- Ignores exceptions during cleanup.
- Retains references in a global registry without unregistering.

## 44. Runnable: Manager Managing Two Child Resources

Save **`CompositeCloseDemo.java`**:

```java
final class Child implements AutoCloseable {
    private final String name;

    Child(String name) {
        this.name = name;
        System.out.println("open:" + name);
    }

    @Override
    public void close() {
        System.out.println("close:" + name);
    }
}

final class Composite implements AutoCloseable {
    private final Child first;
    private final Child second;

    Composite() {
        first = new Child("first");
        second = new Child("second");
    }

    @Override
    public void close() {
        second.close();
        first.close();
    }
}

public class CompositeCloseDemo {
    public static void main(String[] args) {
        try (Composite composite = new Composite()) {
            System.out.println("using-composite");
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 CompositeCloseDemo.java
java CompositeCloseDemo
```

Stdout:

```text
open:first
open:second
using-composite
close:second
close:first
```

The example introduces the idea of reverse-order cleanup. In production, if second.close() throws an exception, the code must ensure first.close() is still attempted and error details are preserved, for instance by using nested try/finally or an appropriate abstraction. This is a crucial point when writing composite resources.

## 45. Resource Acquisition Should Use the Shortest Possible Scope

If a DB connection is only needed for a single query, do not hold it in a singleton field and wait for GC to clean it up at process end. The longer the scope:
- The easier it is to hold scarce resources unnecessarily.
- The harder it is to identify the owner.
- The more code paths can lead to forgetting to close.
- The higher the risk of contention/pool exhaustion.

**Good design:**

```java
try (Connection connection = dataSource.getConnection()) {
    // A short unit of work.
}
```

The snippet requires a real JDBC context. If a multi-step transaction must share a connection, the longer ownership scope is **intentional**, rather than always closing after a single statement regardless of transaction boundaries.

## 46. Does `ShutdownHook` Replace Finalizers?

Java provides `Runtime.addShutdownHook(Thread)` for certain process-wide cleanup scenarios. However, a shutdown hook is **not** a per-resource/per-request solution:
- It runs during the process shutdown lifecycle, not when a request finishes.
- It is not guaranteed to run if the JVM is halted or the process is killed ungracefully.
- Shutdown sequencing/timeouts/threads can introduce complexity.
- It does not replace `close()` for thousands of connections/sessions while the process is running.

Use a shutdown hook for **process-wide** resources when appropriate; per-operation resources should still use scopes and proactive close.

### Be Careful with `System.exit`

Do not write a finalizer demo that calls `System.exit()` and tries to print before/after: there will be many implementation-specific behaviors. The runnable programs in this README only illustrate cleanup driven by Java control flow.

## 47. Why Finalization Is Unsuitable for Business Logic

Do not place in `finalize()`:
- Committing or rolling back a transaction.
- Sending confirmation emails.
- Changing order status.
- Emitting business events that must be delivered.
- Writing audit records that must not be lost.
- Releasing a distributed lock with a deadline.
- Executing a payment reversal.
- Calling a remote service to clean up a workflow.

These actions require **ordering, ownership, retries, idempotency, observability, and SLAs**; finalization does not provide those guarantees.

If business requirements demand cleanup even when a process dies, you must design proper **durable jobs/outboxes/leases/timeouts and recovery**; you cannot rely solely on a Java object finalizer.

## 48. Distinguishing a Heap Memory Leak from a Resource Leak

A **heap retention leak**: references still retain unnecessary objects, such as a static map/listener holding a large graph.

A **resource leak**: a file/socket/native handle/connection is not closed, even though the Java object may soon become unreachable.

These two bugs can occur together or independently:
- Not retaining a reference but forgetting to close: the OS resource may leak until runtime/OS cleanup, with no safe timing.
- Retaining a static reference while the resource is closed: heap retention can still be large even though the OS handle was released.
- Closing properly and dropping references properly: resolves both lifecycles.

**The GC only knows about object reachability**; it does not infer business deadlines for releasing a file descriptor.

## 49. Investigating a Legacy Application That Still Has `finalize()`

A controlled process:

1. Search for `finalize()` overrides in your code and dependencies.
2. Document the resource that each finalizer intends to release.
3. Inspect where it is acquired, where the reference is returned/passed, the owner, and exit paths.
4. Determine whether `close()/dispose()/release()` already exists.
5. Evaluate exception behavior and cleanup dependency ordering.
6. Design an explicit lifecycle using `AutoCloseable`/try-with-resources or `finally`.
7. Write regression tests verifying proper closing on both success and failure paths.
8. If a low-level resource needs a safety net, evaluate Cleaner with state separated from the referent.
9. Remove the `finalize()` override and update docs/call sites.
10. Test under the target JDK and compare resource metrics/performance.

### Do Not Simply Delete the Finalizer

If the finalizer was previously the **only cleanup path**, deleting it without adding new close/ownership logic can make leaks worse. Migration must move resource-closing responsibility to verifiable code paths.

## 50. Compiler Warnings and Deprecation Annotations

In Java 17, when a class overrides a deprecated method, depending on compiler flags and usage, you may receive deprecation diagnostics. You can enable them with:

```bash
javac --release 17 -Xlint:deprecation Example.java
```

No fixed diagnostic “stdout” line is provided because the warning format and line numbers depend on the compiler and source.

### Do Not Treat Suppression as Remediation

`@SuppressWarnings("deprecation")` only **hides the warning** within its effective scope; it does not change:
- Finalizer timing;
- GC behavior;
- Exception handling;
- Security issues;
- The likelihood of the API being removed in the future.

Fix the resource lifecycle. Only suppress warnings when there is a special reason in migration code and it undergoes a scoped code review.

## 51. Code Review: Detecting Finalizers with grep

In source code, the term may appear in forms such as:

```java
@Override
protected void finalize() throws Throwable {
    // ...
}
```

or:

```java
protected void finalize() {
    // ...
}
```

Be sure to review:
- Actual `finalize()` method overrides.
- Calls to `System.runFinalization()`/`Runtime.runFinalization()`.
- Comments stating “the GC closes the resource automatically”.
- Resources acquired without being closed.
- Cleaners capturing the referent.
- Inheritance chains that have finalization logic in a superclass or subclass.

Some code has a method named `finalize` with a different signature (`finalize(int)`), which does not override `Object.finalize()`; do not draw conclusions from text search alone without checking the signature.

## 52. Proper Unit Testing: Counting `close()`

A reliable test can use a fake resource with a counter:

- When the try body completes → close count = 1.
- When an exception occurs in the body → close count = 1.
- When there are two resources → close order is reversed.
- If close also throws → primary/suppressed exceptions are correct.
- When the second constructor throws → the first resource still closes.
- When a client borrows a resource → it does not close it arbitrarily unless specified by contract.
- If the API is idempotent → repeated close does not release repeatedly.

**Do not** assert “finalize runs within 100 ms,” “System.gc causes the reference to be cleared,” or “after the test, the heap shrinks by exactly N bytes.” These are not contracts to be enforced.

## 53. Runnable: Measuring Cleanup Along an Exception Path

Save **`CloseContractTestDemo.java`**:

```java
final class CountingHandle implements AutoCloseable {
    private int closes;

    int closes() {
        return closes;
    }

    @Override
    public void close() {
        closes++;
    }
}

public class CloseContractTestDemo {
    public static void main(String[] args) {
        CountingHandle handle = new CountingHandle();

        try (handle) {
            throw new IllegalArgumentException("error");
        } catch (IllegalArgumentException ignored) {
            // The try-with-resources cleanup path still runs.
        }

        if (handle.closes() != 1) {
            throw new AssertionError("close count");
        }

        System.out.println("CLOSE_CONTRACT_PASS");
    }
}
```

```bash
javac --release 17 -encoding UTF-8 CloseContractTestDemo.java
java CloseContractTestDemo
```

Stdout:

```text
CLOSE_CONTRACT_PASS
```

This Java 17 example uses `try (handle)`, which is valid because the `handle` variable is effectively final. `close` runs before the catch block and the test assertion.

## 54. Why Cleaner Is Inferior to Explicit `try-with-resources`

| Criterion | `try-with-resources` + `close()` | `Cleaner` Without Close |
| --- | --- | --- |
| Cleanup timing | Tied to program structure, when the scope ends | Depends on reachability/GC/background processing |
| Does caller know cleanup happened? | Yes, clear control flow | Cannot predict a deadline |
| Order of multiple resources | Reverse declaration order per language rules | Cannot guarantee order of GC callbacks |
| Cleanup errors | Can be caught/suppressed | Asynchronous errors are hard to propagate to caller |
| Runs before shutdown? | When the program passes through scope normally | Not guaranteed |
| Used for transactions | Can be used to release after an explicit commit/rollback flow | Unsuitable |
| Acts as fallback if close is forgotten? | Not a GC fallback | Can help in some wrappers |
| Complexity | Usually low | Higher, requires state not capturing the referent |

**Cleaner is not forbidden**, yet good usage typically makes **`AutoCloseable` the primary mechanism and Cleaner a defensive aid**.

## 55. How to Keep Cleanup State Independent of the Object

When using Cleaner, distinguish clearly:

```text
Cleaner ──▶ Cleanable registration ──▶ State ──▶ Native handle
                   │
                   └──phantom tracking──▶ Resource owner
```

State must not:
- Hold a reference to the Resource owner itself.
- Be a non-static inner class that implicitly captures the owner.
- Be a lambda accessing `this`/instance methods of the owner.
- Hold a child object with a back-reference to the owner forming a hidden strong cycle.

State **is allowed** to hold enough information to release the resource: ID/descriptor/native pointer and synchronization state. The owner object typically holds the `Cleanable` so it can call `clean()` in its explicit `close()`.

### Separating Metadata and Ownership

If State contains a singleton `Logger` or another utility object, check whether the graph leads back to the owner. When in doubt, use heap graph analysis rather than trusting that a “short-looking” lambda does not capture this.

## 56. Concurrent Close and Cleaner Actions

A resource wrapper may be used by multiple threads while one thread calls `close()` and a Cleaner background task prepares to release. The design must consider:
- The release state transitions **only once** (`AtomicBoolean`, CAS, or appropriate locking).
- Never use the native handle after release.
- Races between close and in-flight operations.
- Memory visibility and thread safety.
- Are release errors reported/recorded on the explicit close path?
- Can the cleanup action block?
- Is `reachabilityFence` needed to keep the wrapper alive through the end of the native operation?

You cannot rely solely on a `final` field or `volatile boolean` as a complete solution for concurrent resource safety. Operations must follow specific invariants and API contracts.

## 57. Finalization and the Object Graph

Do not predict cleanup order based on the structure:

```text
Parent ──field──▶ Child
```

Parent holding Child does not establish a rule that “Child.finalize runs before Parent.finalize” or vice versa. A finalizer might access other objects that are in an unpredictable lifecycle state.

This is why:
- With explicit ownership, Parent.close can call Child.close.
- Use try-with-resources with reverse-order close for direct resources.
- No custom graph finalization traversal is needed.
- Avoid relying on finalizers to close resources that have a dependency order.

## 58. Distinguishing `Cleaner` from `WeakReference`

`WeakReference<T>` primarily avoids keeping a referent strongly reachable solely because that cache/reference exists. `weak.get()` can return null once the referent is processed by the collector.

`Cleaner` manages registered cleanup actions when reachability changes. To release a native handle, the cleanup action must have independent state and clear release semantics.

Do not use `WeakReference` as an automatic “resource-closing callback”: a plain weak reference carries no release logic. If you build your own mechanism with `ReferenceQueue`, you must manage the queue/references/cleanup lifecycle and still have no deadline.

**Not every application needs weak/phantom refs.** Explicit ownership/close is the easier-to-understand and safer choice for most resource use cases.

## 59. Mistake: Believing Java “Has GC So You Don't Need to Close”

The GC automatically manages the **heap memory** of unreachable objects. It has no business knowledge:
- “When the request ends, return the DB connection to the pool.”
- “Once the upload finishes, close the file immediately.”
- “On timeout, release the distributed lock.”
- “When the transaction fails, roll back.”
- “When switching users, unregister the old listener.”

Those events are known by the application code. If you leave cleanup responsibility to the GC, resources can be held unnecessarily long and cause failures even when the heap is not full at all.

### Questions to Ask

Instead of “when will this object be GC'd?”, ask:
1. Where is the resource acquired?
2. Which unit of work owns it?
3. When does that unit of work end?
4. At which point must `close/release` run?
5. Do error/return/cancel branches share the same cleanup contract?

## 60. Anti-Pattern: Finalizer That Merely Logs “closed”

A flawed demo typically creates an object with `finalize() { println("closed"); }`, calls `System.gc()`, and then concludes:
- The finalizer always runs;
- That is a sign the resource has been released;
- It can be used for actual closing;
- It is definitely called upon JVM exit.

All of those conclusions are unreliable.

If you want to teach resource lifecycles, use a **program with a deterministic `close()`**, printing `open/use/close` via try-with-resources. Do not present finalizer timing output as “exact stdout”.

## 61. Warnings When Migrating JDKs

When migrating from Java 17 to another JDK:
- Review JEP 421 and the release notes of the target JDK.
- Search for usages in your own code and older libraries.
- Ensure no business logic depends on finalization.
- Run static analysis/lint checks for deprecated APIs.
- Use memory/file descriptor/connection metrics to verify the migration.
- If the JDK supports disabling finalization, test it in test/staging to find dependencies (following **version-accurate** guidance; do not copy JDK 18 options into Java 17 run instructions when the option is unsupported).
- Document resource ownership in published APIs.

**Very important:** the command-line flag `--finalization=disabled` was introduced alongside changes in JDK 18; **do not claim it is a Java 17-compatible flag**.

## 62. Exercise 1 — Accurate Deprecation Milestones

Question: Has Java 17 removed `Object.finalize()`?

**Answer:** No. In Java 17, this API has been deprecated since Java 9. Deprecation **for removal** of finalization was introduced in JDK 18 under JEP 421.

## 63. Exercise 2 — Assigning `null`

Question: Does `resource = null;` close the resource immediately?

**Answer:** No. That is merely reassigning a single reference; aliases/GC timing still apply, and no close call happens.

## 64. Exercise 3 — End of Block

Question: Does an object variable going out of lexical scope guarantee `finalize()` runs immediately?

**Answer:** No. Scope differs from liveness/reachability, and the GC has no such deadline.

## 65. Exercise 4 — `System.gc()`

Question: After `System.gc()`, can you assert that the finalizer definitely printed a line?

**Answer:** No. GC/finalization scheduling has no timing guarantee or certainty of executing as expected by the test.

## 66. Exercise 5 — File Descriptor

A method opens a file to read a few lines and then returns. Should you use `finalize()` or try-with-resources?

**Answer:** Try-with-resources with a BufferedReader/InputStream/Stream that has a close contract. Close it when the reading work finishes.

## 67. Exercise 6 — DB Connection Pool

Question: Should a pooled JDBC Connection wait for the JVM GC to be returned to the pool?

**Answer:** No. Use connection.close per the pool/library contract and try-with-resources aligned with the unit-of-work.

## 68. Exercise 7 — Exception in the Body

If the body throws an exception, does try-with-resources close a resource that was acquired successfully?

**Answer:** Yes, according to Java control-flow rules. Exceptions from close may be suppressed if the body had a primary exception.

## 69. Exercise 8 — Order of Two Closes

`try (A a = ...; B b = ...) { ... }`. Which resource is closed first?

**Answer:** B before A according to reverse declaration order.

## 70. Exercise 9 — Close Error

The body throws `IOException("work")` and close throws `IOException("close")`. Which error does the caller receive as primary?

**Answer:** Typically the “work” error is primary; the “close” error is in `getSuppressed()`, per try-with-resources rules.

## 71. Exercise 10 — Constructor Acquisition Failure

A is created successfully, B's constructor throws, and the body does not run. Is A closed?

**Answer:** Yes, if A is in the try-with-resources resource spec. Separately, B's constructor is responsible for cleaning up its internal acquisition when construction fails.

## 72. Exercise 11 — `AutoCloseable`

Question: Is every `AutoCloseable.close()` automatically idempotent by default?

**Answer:** It is not a universal mandatory contract. Check the API/implementation design; many real resources support repeated close, though it must not be assumed automatically.

## 73. Exercise 12 — `Closeable`

Question: How does `Closeable` relate to `AutoCloseable`?

**Answer:** Closeable extends AutoCloseable, specifically for I/O, and uses the API's IOException/close behavior. Both work in try-with-resources.

## 74. Exercise 13 — Legacy Code

A class has a `finalize()` override that calls `socket.close()`. Should you simply delete the override?

**Answer:** No. First add explicit ownership/close paths; only then remove the finalizer. Deleting it without replacement can make leaks worse.

## 75. Exercise 14 — `Cleaner`

Does Cleaner create an automatic cleanup deadline when an object is no longer reachable?

**Answer:** No. Automatic cleaning depends on GC/reachability; treat it as a safety net.

## 76. Exercise 15 — Explicit Cleaner

`Cleanable.clean()` is called inside `close()`. Does it have to wait for GC?

**Answer:** No, the explicit call can run the action proactively, per the Cleaner contract; the action is not run repeatedly for the same registration.

## 77. Exercise 16 — Capturing this

A Cleaner action is written as `() -> release(this.handle)`. What is the risk?

**Answer:** The lambda captures the owner `this`, keeping the referent reachable and preventing automatic cleaning. Extract a static State holding the handle independently.

## 78. Exercise 17 — Non-Static Inner State

Should you use a non-static inner class as Cleaner State if it implicitly holds the outer instance?

**Answer:** No. That risks retaining the referent and preventing the cleaner from running automatically. Use a static nested State.

## 79. Exercise 18 — PhantomReference.get()

Question: Can `phantom.get()` return the original object after GC?

**Answer:** No, it returns null per the API; do not use it as a getter for cleanup.

## 80. Exercise 19 — `reachabilityFence`

Does `Reference.reachabilityFence` invoke GC or close?

**Answer:** No. It keeps the referent strongly reachable up to the fence point; it is not resource release.

## 81. Exercise 20 — Object Resurrection

A finalizer stores `this` into a static field. What can happen?

**Answer:** The object can become reachable again if the finalizer runs, complicating lifecycle and security. Do not use this to manage resources.

## 82. Exercise 21 — Finalizer Exceptions

Can an error in a finalizer be reliably handled at the caller like `close()` throws IOException?

**Answer:** No. Finalization occurs outside the caller's control flow; errors may be ignored per API semantics.

## 83. Exercise 22 — `final` Class

Question: Does `final class Resource` close automatically when the local variable goes out of scope?

**Answer:** No. `final` restricts subclassing and is unrelated to automatic resource release.

## 84. Exercise 23 — `finally`

If AutoCloseable cannot be used immediately, can `finally` perform cleanup?

**Answer:** Yes, within an appropriate control-flow scope; be careful if cleanup itself throws, and preserve the original exception.

## 85. Exercise 24 — Resource Ownership

A callee receives an InputStream owned by the caller and only uses it for parsing. Should the callee close it on its own?

**Answer:** Only if the contract transfers ownership or specifies it explicitly. If it merely borrows the stream, the callee generally does not close the caller's resource.

## 86. Exercise 25 — Cleaner at Shutdown

Does Cleaner guarantee running all actions before process exit?

**Answer:** No. The API states behavior on `System.exit` is implementation-specific and does not guarantee every action runs.

## 87. Exercise 26 — Performance

What problems can an indefinitely blocking finalizer cause?

**Answer:** It can slow down the backlog, cause a hang/deadlock, or retain resources. Do not put blocking business work in finalizers/cleaning actions.

## 88. Exercise 27 — Heap Leak and Resource Leak

An object closed its socket but remains in a static cache—have all issues been eliminated?

**Answer:** The socket resource may be released, but the heap graph is still retained in the cache, which can be a separate heap retention leak.

## 89. Exercise 28 — Resource Still Open, Object Unreachable

If the application loses references to a file handle without closing it, is the file guaranteed to be closed immediately?

**Answer:** No. Losing a strong reference path does not replace an explicit close contract; GC/finalization has no deadline.

## 90. Exercise 29 — Exception Test

A unit test wants to verify cleanup on failure. Should it observe finalizer count or close count?

**Answer:** Close count/state via deterministic control flow, including suppression and ordering if needed. Do not test GC timing.

## 91. Exercise 30 — Complete Migration

You find `finalize()` in a native handle wrapper—what should you do?

**Answer:** Design explicit AutoCloseable/ownership; ensure failed constructors perform cleanup, idempotency/thread safety, and tests; consider an independent Cleaner State as a backup if needed; remove the finalizer override and verify runtime metrics.

## 92. Comprehensive True/False Quiz

1. Java 17 removed `Object.finalize()`.
2. `Object.finalize()` has been deprecated since Java 9.
3. JDK 18 marks finalization as deprecated for removal.
4. When a local variable goes out of scope, `finalize()` always runs immediately.
5. `System.gc()` guarantees closing all resource wrappers.
6. `try-with-resources` calls `close()` upon exiting scope per Java control flow.
7. `AutoCloseable` can be used with custom classes.
8. If two resources are in a single try, they close in reverse order of declaration.
9. A Cleaner action may capture the referent without consequences.
10. Cleaner has an automatic deadline for releasing file descriptors.
11. `PhantomReference.get()` returns the referent object.
12. Finalizers carry the risk of object resurrection.
13. A `final` reference and `finalize()` are the same mechanism.
14. `Closeable` extends `AutoCloseable`.
15. Proactive resource closing can occur while the Java wrapper object is still reachable.

**Answer:** 1 false; 2 true; 3 true; 4 false; 5 false; 6 true; 7 true; 8 true; 9 false; 10 false; 11 false; 12 true; 13 false; 14 true; 15 true.

## 93. Common Mistakes Table

| Mistake/Misconception | Why It Is Wrong | How to Fix |
| --- | --- | --- |
| “GC automatically manages all resources” | GC primarily reclaims memory and does not know OS resource deadlines | Explicit `close()` based on ownership |
| “`finalize()` runs immediately when set to null” | There is no GC/finalization deadline | Try-with-resources |
| “`System.gc()` is a cleanup API” | It is only a request/hint, not a guarantee | Close resources proactively |
| “Java 17 removed finalize” | Java 17 still contains the deprecated API | Distinguish Java 9/17 and JDK18 JEP421 |
| “`final` is equivalent to finalizer” | The modifier does not invoke cleanup | Use AutoCloseable |
| “`finally` is a GC callback” | Finally belongs to control flow | Understand exception unwinding |
| “Remembering to call finalize manually is enough” | It is not a release contract and risks double cleanup | The `close()` API |
| “Closing eventually at the end is fine” | File descriptors/DB slots have their own deadlines/limits | Short resource scopes with clear ownership |
| “Cleaner replaces try-with-resources” | Automatic Cleaner is nondeterministic | Cleaner only as backup if needed |
| “Cleaner lambda capturing this is safe” | It can keep the referent strongly reachable | Independent static State |
| “A cleanup error doesn't matter” | It can hide resource leaks/transaction state | Catch/report, suppressed exceptions |
| “Two resources close in declaration order” | Java closes them in reverse order | Design dependencies properly |
| “AutoCloseable is always idempotent” | Not universally required | Document and implement appropriately |
| “If a new resource fails, already-opened resources aren't cleaned up” | Try-with-resources closes initialized resources | Wrap acquisitions in the resource list |
| “If a constructor fails, try-with-resources automatically closes the uncreated object” | No resource variable finished initializing | Clean up partial acquisitions inside constructor/factory |
| “Process exit invokes all cleaners” | There is no guarantee | Do not delegate business logic to GC |
| “No need to test close, the JVM will handle it” | GC is nondeterministic | Test explicit close count/state |
| “Deleting the finalizer fixes the leak” | It may remove the only cleanup path | Move cleanup to an explicit path first |
| “Shutdown hook replaces per-request close” | Runs too late and is not guaranteed for all shutdown types | Each owner closes by scope |

## 94. Checklist for Replacing `finalize()` with a Safe Design

- [ ] Located all `finalize()` overrides in relevant code/libraries.
- [ ] Aware that JDK 17 has it deprecated since 9; JDK 18 JEP421 is for removal.
- [ ] No new functionality built depending on finalizers.
- [ ] Identified off-heap resources held by the object.
- [ ] Distinguished resource lifetime from Java object reachability.
- [ ] Is the owner clear for each resource?
- [ ] Can the resource implement `AutoCloseable`/`Closeable`?
- [ ] If yes, prefer `try-with-resources` in an appropriately small scope?
- [ ] If not, is there an explicit `try/finally` or release adapter?
- [ ] Tested cleanup on the success path?
- [ ] Tested cleanup on the exception path?
- [ ] Tested reverse-order close for multiple resources?
- [ ] Verified suppressed exception behavior?
- [ ] Handled partial acquisition failure?
- [ ] Prevented invalid double close/use-after-close?
- [ ] Clear idempotency and thread-safety contract where needed?
- [ ] Do all borrowers/owners know who has permission to close?
- [ ] Avoided calling `System.gc()`/`runFinalization()` to fix leaks?
- [ ] Avoided using `@SuppressWarnings("deprecation")` as the primary solution?
- [ ] If using Cleaner, is it strictly a backstop?
- [ ] Is Cleaner State static/independent and not capturing the referent?
- [ ] Is the cleaning action fast, minimally blocking, and order-independent?
- [ ] Not assuming Cleaner will run before JVM exit?
- [ ] If using `PhantomReference`, are the queue and bookkeeping managed properly?
- [ ] If using `reachabilityFence`, is it understood not to be a cleanup call?
- [ ] No business-critical events/transactions placed in a finalizer?
- [ ] Metrics exist for file handles/connections/native allocations?
- [ ] Considered resource leaks separately from heap retention leaks?
- [ ] Tests exist that do not depend on GC timing?
- [ ] Evaluated the actual JDK's behavior when upgrading versions?
- [ ] Removed the `finalize()` path after the explicit lifecycle is working?
- [ ] Documentation exists on ownership/cleanup lifecycle for callers?
- [ ] Reviewed security/constructor failure/resurrection in legacy classes?

## 95. Summary

In **Java 17**, `Object.finalize()` still appears in the API, yet it has been **deprecated since Java 9**. **JDK 18 / JEP 421** further marks finalization as **deprecated for removal**. The finalizer mechanism does not provide the guarantees a resource manager needs: no deterministic invocation timing, no ordering, poor error visibility, potential overhead increase, and risks of deadlock, object resurrection, or security flaws.

To manage resources:
1. Clearly identify **who owns the resource**.
2. **Close proactively** using `AutoCloseable.close()`.
3. Prefer `try-with-resources` to ensure cleanup even when an exception occurs.
4. Handle exception suppression, constructor failure, and repeated close according to the contract.
5. For rare native/off-heap wrappers, **Cleaner** can act as a safety net with a State that does not capture the referent — **never replacing explicit close**.
6. Test close count/state and resource metrics, **not** relying on `System.gc()` or finalizer timing.

**Rule of thumb:** *Do not wait for the garbage collector to know your work is done. The code that owns the resource must close it when it is no longer needed.*

## 96. Official Documentation

- **Java SE 17 `Object.finalize()`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#finalize()
- **Java SE 17 `AutoCloseable`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html
- **Java SE 17 `Closeable`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Closeable.html
- **Java SE 17 `Cleaner`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Cleaner.html
- **Java SE 17 `PhantomReference`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/PhantomReference.html
- **Java SE 17 `Reference.reachabilityFence()`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Reference.html#reachabilityFence(java.lang.Object)
- **JLS §14.20.3 — try-with-resources**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3
- **JLS §12.6 — Finalization of Class Instances**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.6
- **JEP 421 — Deprecate Finalization for Removal (JDK 18)**: https://openjdk.org/jeps/421
