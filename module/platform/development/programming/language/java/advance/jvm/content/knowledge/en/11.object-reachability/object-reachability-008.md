# Finalization, Deprecation, and Choosing `try-with-resources` or `Cleaner` in Java

**Finalization** is a long-standing mechanism in Java: an object can define a `finalize()` method, and the JVM may invoke it after determining that the object is no longer reachable according to certain GC conditions. It was previously used to close files, sockets, database connections, or release native handles when developers forgot to clean up.

However, **finalization does not provide reliable execution timing, risks resurrecting objects, introduces concurrency bugs, deadlocks, resource leaks, and impacts performance**. Java currently recommends **not writing new finalizers**. For resources that must be released in a timely manner, use **`AutoCloseable` + `try-with-resources`**; when a fallback cleanup path is genuinely needed when an object is no longer reachable, use **`java.lang.ref.Cleaner`**, while still prioritizing explicit `close()`.

This lesson belongs to the **Object Reachability** section in the JVM, focusing on reachability, object lifecycle, and choosing the appropriate API. The main examples run on **Java 17+**, only illustrating stdout results when timing can be controlled, and **do not assume the JVM will definitely run GC/finalizer/Cleaner before a deadline**.

## 1. Distinguishing GC, Finalization, and Resource Cleanup

There are three tasks that are often conflated:

1. **GC memory reclamation:** The JVM recognizes that an object on the Java heap is no longer needed according to reachability rules and can reclaim the object's heap memory.
2. **Finalization:** A legacy mechanism that may invoke an overridden `Object.finalize()` on an eligible object before the object's memory is reclaimed according to the finalization-supported sequence.
3. **Resource cleanup:** Closing sockets, file descriptors, transactions, native pointers, or locks/connections. Many of these resources are **not automatically released on time just because the Java wrapper object becomes unreachable**.

```text
Java object on the heap
       │
       ├─ still strongly reachable
       │     └─ the application is holding and using the object
       │
       └─ no longer strongly reachable
             │
             ├─ GC may analyze reachability and process references
             ├─ legacy finalization may run (if the object has a finalizer,
             │   the runtime still has it enabled, and conditions apply)
             ├─ Cleaner may receive phantom reachability notification
             │   and run the registered cleaning action
             └─ heap storage may be reused when GC permits

Do not confuse:
  "object is eligible for collection"
       ≠ "finalize has definitely run"
       ≠ "native/socket resource was closed on time".
```

GC is responsible for the **Java heap**, whereas connection pools, file descriptors, native allocations, and OS handles have their own ownership/closing policies. A design relying solely on finalization can cause an application to exhaust file descriptors even while the heap still has plenty of capacity and the collector has no reason to run.

### 1.1. Why Strong-Weak-Phantom Matters

The `java.lang.ref` package describes **strong, soft, weak, and phantom reachability**. Historically, finalization is related to reachability stages and object processing; `Cleaner` uses **phantom references** together with a reference queue to receive notifications when a registered object is no longer normally reachable.

The core difference: **Cleaner does not invoke a method on the referent by retrieving the object via `PhantomReference.get()`**. The cleaning action must hold the **independent state** needed for cleanup, because phantom `get()` always returns `null`.

## 2. Deprecation Status Across JDK Releases

It is important to distinguish between an API being **marked deprecated**, **deprecated for removal**, **disabled by default**, and **removed**. Those are four different states.

| Version / Milestone | Notable Status |
| --- | --- |
| **Java 9** | `Object.finalize()` was marked **`@Deprecated(since="9")`**; `Cleaner` was introduced |
| **JDK 17** | `Object.finalize()` still exists but is **deprecated**; finalization is a legacy mechanism and should not be used in new code |
| **JDK 18 – JEP 421** | Finalization was **deprecated for removal**; several related APIs were marked accordingly; added the `--finalization=disabled` option to test for dependencies |
| **JDK 26 (2026 migration guide)** | Oracle still describes finalization as **deprecated for removal**; one must not claim it has been completely removed solely because of JEP 421 |
| **A future release** | The mechanism is expected to be disabled by default and then removed as part of the platform's transition process; the exact release must be verified against the corresponding release notes |

**Key takeaway:** "`Object.finalize()` is deprecated" does not mean the Java 17 compiler no longer recognizes the method. On the contrary, the compiler accepts compatible code but emits a **warning**, and the API is marked as discouraged. The **deprecated for removal milestone in JDK 18** is a stronger compatibility signal, not a guarantee that code will break in the very next JDK release.

### 2.1. Testing with Finalization Disabled in JDK 18+

JEP 421 provides a testing switch when supported by the runtime:

```bash
# JDK 18+ supports this option per JEP 421:
java --finalization=disabled -cp out MyApplication
```

It helps detect code or dependencies that **implicitly rely on finalization**. Do not treat this command as an example required to run on Java 17: **JDK 17 does not have `--finalization=disabled`, which was introduced in JDK 18**.

Note:

- Disabled finalization must not be understood as disabled GC.
- Disabling finalization does not automatically call `close()` for you.
- If an application has resources that are only closed via `finalize()`, disabling it may expose resource leaks or change behavior; that is an issue to fix in code/lifecycle.
- JVM options should not be used to avoid migrating away from finalizers in the codebase.
- Newer JVM documentation may change flags/statuses across releases; when deploying, always verify `java -version` and the exact vendor release notes.

### 2.2. Why "Removed" Differs from "Deprecated"

**Deprecated:** The API call may still exist and work, but there are warnings/documentation advising against its use.

**Deprecated for removal:** The API/mechanism is planned for removal; dependent code should be migrated early and tested for compatibility.

**Disabled:** The runtime may keep code/API compatible but **not execute the finalization work**; logic relying on side effects of `finalize()` will fail.

**Removed:** The API/mechanism is no longer provided in a specific release scope; source, binary compatibility, or runtime behavior may have to change.

Do not infer status solely from the name `finalize` in a stack trace or old library code: you must identify the actual release and loaded class.

## 3. How Did `Object.finalize()` Work?

In Java 17, `Object.finalize()` has the signature:

```java
@Deprecated(since = "9")
protected void finalize() throws Throwable
```

A legacy class could override it:

```java
// HISTORICAL CODE FOR READING/MIGRATION ONLY, NOT RECOMMENDED FOR NEW CODE:
class LegacyResource {
    @Override
    protected void finalize() throws Throwable {
        try {
            // cleanupLegacyHandle();  // Assume legacy code holds a native handle.
        } finally {
            super.finalize();
        }
    }
}
```

This is an **illustrative snippet**, not a file with `main`; it intentionally performs no actual cleanup. Calling `super.finalize()` in an overridden `finalize()` is not automatically inserted by Java the way constructor chaining works.

### 3.1. No Guarantees About Timing

Even when finalization is enabled:

- The JVM does not promise to call `finalize()` immediately when a local variable goes out of scope.
- It can be delayed for a very long time or **never run before the process exits**.
- There is no invocation order for finalizers across different objects.
- Do not build business rules assuming a finalizer executes on the current thread.
- An unhandled exception thrown from `finalize()` is ignored according to the `Object.finalize()` contract; it is not propagated back to business code callers to catch.

**Do not use `System.gc()` or `System.runFinalization()` as a "clock" to force finalizers to run.** Those calls provide no SLA for cleanup. `System.runFinalization()` is also among the related APIs to avoid and was deprecated for removal in JDK 18.

### 3.2. Finalizers Can Resurrect Objects (Resurrection)

A legacy finalizer can store `this` into a static field/list and make the object strongly reachable again:

```java
// HISTORICAL ANTI-PATTERN ONLY — DO NOT RUN EXPECTING FIXED GC TIMING:
static Object resurrected;

@Override
protected void finalize() throws Throwable {
    resurrected = this; // Makes the object have a strong path again.
}
```

Here, the object was once eligible for finalization and then **resurrected**. By contract, a finalizer is **not automatically invoked multiple times** for the same finalizable object. Therefore, "cleaning up the object again when it dies a second time" cannot be considered reliable.

Do not attempt resurrection in production code: it complicates the lifecycle, makes native resource release timing unpredictable, and is a reason the finalization mechanism is discouraged.

### 3.3. Finalizer Thread, Locks, and Concurrency

Finalizers do not run on the Java caller thread at a time of your choosing. If a finalizer tries to wait for a lock/thread while another thread holds that lock and waits for GC-related work or a resource, the application can deadlock or hang. Finalization also puts pressure on GC/reference processing and forces objects to live longer to pass through the finalization cycle.

A finalizer performing long blocking I/O can delay the processing of other finalizers. This is a design flaw: **the lifecycle should not depend on a non-deterministic cleanup thread** when a resource needs to be closed immediately after use.

## 4. Why Is Finalization Unsuitable for Resource Management?

### 4.1. Java Heap Does Not Reflect File Descriptor Counts

For example, a program opens thousands of file streams and drops the references:

```java
// ANTI-PATTERN example, do not use:
for (int i = 0; i < 100_000; i++) {
    java.io.FileInputStream stream =
            new java.io.FileInputStream("data.txt");
    stream.read();
    // No close(), just dropping the reference.
}
```

This is a **non-standalone snippet**, assuming the file exists. The process can run out of OS file descriptors **before** GC decides to reclaim the wrappers; furthermore, an exception in `read()` causes the code to skip any cleanup path.

The right solution is to **close the resource at the point where you know you are done using it**, rather than waiting for heap pressure. Even the Java 17 Javadoc for `FileInputStream` recommends closing directly or using try-with-resources.

### 4.2. Native Pointers and Use-After-Free

A Java wrapper may hold a `long handle` pointing to a native resource. If finalizer cleanup runs after the optimizer sees that the wrapper is no longer live, while native code is still processing the handle, **use-after-free** can occur.

`Reference.reachabilityFence(wrapper)` can keep the wrapper strongly reachable up to a specified point in Java code, but it is a supplementary tool for lifetime correctness, **not a substitute for controlled ownership and closing**.

### 4.3. Security and Exploitation of Partially Initialized Objects

Some classes whose constructors throw exceptions before full initialization can still face finalization-related risks in legacy designs. Mechanisms capable of resurrecting objects or executing code when state is incomplete can open vulnerabilities and make security reasoning difficult. This is one of the reasons cited in JEP 421 when deprecating finalization.

**Do not use a finalizer to perform authorization, mandatory flushing, transaction commits, or saving critical state**: you have no guarantee that such code will run at the right time, in the right order, or complete at all.

## 5. First Choice: `AutoCloseable` + `try-with-resources`

A resource can be explicitly closed via `close()`. The `AutoCloseable` interface defines:

```java
public interface AutoCloseable {
    void close() throws Exception;
}
```

Many Java APIs such as `InputStream`, `OutputStream`, `Reader`, JDBC `Connection`, `Statement`, `ResultSet`, and `java.nio` resources support scope-based closing (check each API's specific contract).

`try-with-resources` in Java causes the compiler to invoke `close()` when control leaves the `try` block, including:

- Normal completion.
- `return` from the `try` body.
- An exception inside the `try` body.
- Other valid control flows leaving the statement according to Java semantics.

This is **deterministic cleanup tied to control flow**, independent of GC detecting that the object is unreachable.

### 5.1. Closing Order with Multiple Resources

Resources are **initialized from left to right** and **closed in reverse order** (LIFO-like).

Create file **`TryWithResourcesOrderDemo.java`**:

```java
public class TryWithResourcesOrderDemo {
    static final class Tracer implements AutoCloseable {
        private final String name;

        Tracer(String name) {
            this.name = name;
            System.out.println("open " + name);
        }

        @Override
        public void close() {
            System.out.println("close " + name);
        }
    }

    public static void main(String[] args) {
        try (Tracer first = new Tracer("A");
             Tracer second = new Tracer("B")) {
            System.out.println("body");
        }
        System.out.println("after");
    }
}
```

Compile/run on Java 17+:

```bash
javac --release 17 TryWithResourcesOrderDemo.java
java TryWithResourcesOrderDemo
```

**Exact stdout:**

```text
open A
open B
body
close B
close A
after
```

**Explanation:** The code creates `A` then `B`, enters the `try` body, and then closes `B` before `A`. This is the `try-with-resources` mechanism in the Java language, not the JVM waiting for GC before calling `close()`.

### 5.2. What If the Second Resource's Constructor Throws an Exception?

If `new Tracer("B")` throws an exception during resource acquisition, Java still **closes any previously initialized resources**, which in this example is `A`. Thus, try-with-resources also protects cases where execution never enters the body.

That is one reason to create resources directly inside the `try` header rather than opening multiple resources with `new` beforehand and relying on a hand-written `finally` block.

### 5.3. Reusing Effectively Final Resources (Java 9+)

Java 9 allows using a `final` or **effectively final** resource variable that was already initialized:

```java
var stream = java.nio.file.Files.newInputStream(path);
try (stream) {
    // Read data...
}
```

This is a **snippet**; it requires a `path` variable of type `java.nio.file.Path` and handling `IOException`. It illustrates the `try (stream)` syntax supported in Java 9+, while the standalone examples in this lesson use Java 17.

**Note:** The resource must implement `AutoCloseable`; you cannot just have a method named `close` unrelated to the interface and expect the compiler to handle it automatically.

## 6. `try-with-resources` and Suppressed Exceptions

There is an important scenario: **the try body throws an exception, and then `close()` also throws an exception**. Java does not simply replace the original error with the closing error (in the standard case):

- The exception from the try body is the **primary exception**.
- The exception from `close()` is **suppressed** onto the primary exception via `Throwable.addSuppressed`.
- The caller catches the primary exception and can inspect the secondary errors via `Throwable.getSuppressed()`.

### 6.1. Complete Java 17 Example and Deterministic Stdout

Create file **`SuppressedCloseDemo.java`**:

```java
public class SuppressedCloseDemo {
    static final class FailingResource implements AutoCloseable {
        @Override
        public void close() throws Exception {
            throw new Exception("close failed");
        }
    }

    public static void main(String[] args) {
        try (FailingResource ignored = new FailingResource()) {
            throw new IllegalStateException("body failed");
        } catch (Exception ex) {
            System.out.println("primary=" + ex.getMessage());
            System.out.println("suppressedCount=" +
                    ex.getSuppressed().length);
            System.out.println("suppressedMessage=" +
                    ex.getSuppressed()[0].getMessage());
        }
    }
}
```

Run:

```bash
javac --release 17 SuppressedCloseDemo.java
java SuppressedCloseDemo
```

Stdout:

```text
primary=body failed
suppressedCount=1
suppressedMessage=close failed
```

`IllegalStateException` from the body remains the primary error. The exception from `close` is preserved as suppressed, not swallowed. In production code, do not assume `getSuppressed()[0]` always exists; this demo program knows for certain that the resource is designed to throw from `close`.

### 6.2. `getCause()` Is Not `getSuppressed()`

- **Cause chain:** Usually indicates the underlying cause that produced a wrapper exception (for example, `new IOException("failed", cause)`).
- **Suppressed exceptions:** Errors that occurred during cleanup, preserved alongside the primary exception.

When diagnosing failures across multiple resources, read the **primary exception**, **cause**, and **suppressed exceptions**. A log that only prints `ex.getMessage()` may miss critical closing errors.

### 6.3. Contrast with a Hand-Written `finally`

A hand-written `finally`:

```java
try {
    throw new IllegalStateException("body failed");
} finally {
    throw new IllegalStateException("cleanup failed");
}
```

This is an **anti-pattern snippet**; the `cleanup failed` error replaces the previous normal/abrupt completion and can mask the `body failed` error unless preserved manually. Try-with-resources is designed to avoid losing the primary exception during resource closing.

## 7. Second Choice: `Cleaner` When Fallback Cleanup Is Truly Needed

`java.lang.ref.Cleaner`, introduced in Java 9, manages **phantom references and reference queues** to associate an object with a **`Runnable` cleaning action**. When the registered object becomes phantom-reachable according to the rules, Cleaner can execute the action on an appropriate thread. The API also provides `Cleanable.clean()` to invoke the action **proactively**.

Cleaner is **better than finalization** in separating cleanup state from the referent and avoiding direct method calls on a dying object, but **automatic Cleaner cleanup still has no reliable deadline**.

### 7.1. Key API

```java
Cleaner cleaner = Cleaner.create();
Cleaner.Cleanable cleanable = cleaner.register(owner, cleanupAction);
cleanable.clean();
```

- `owner` is the object monitored for phantom reachability.
- `cleanupAction` is the `Runnable` that releases the separate state.
- `cleanable.clean()` requests executing cleanup **once if it has not already been performed**.
- The action is invoked by Cleaner **at most once** for the corresponding registration; if not explicitly cleaned and the object does not become phantom-reachable while the JVM is running, the action may **never run**.
- During automatic processing, the action may run on a dedicated thread managed by Cleaner and concurrently with running code; behavior on `System.exit` provides no guarantee that all actions will be executed.
- Exceptions from the cleaning action are ignored by Cleaner per API specification; logging/monitoring should be designed if cleanup can fail.

### 7.2. Diagram: Avoid Keeping `owner` Alive Incorrectly

```text
CORRECT:
   Cleaner/registration ──strong──► State (handle/resource data)
            │
            └──phantom──► Owner
   State has no strong path back to Owner.

INCORRECT:
   Cleaner/registration ──strong──► cleanup lambda
                                      │
                                      └──strong capture this──► Owner
   Owner remains strongly reachable → automatic Cleaner cannot trigger.
```

**Key point:** Do not let `cleanupAction` hold a strong reference to `owner` — even indirectly via an inner class, a lambda `() -> this.close()`, or a field in `State` pointing back to owner. If it does, owner never becomes phantom-reachable and cleanup will not run automatically.

Using a **`static` nested class holding the state to be closed** is a clear, safe pattern.

## 8. Complete Java 17 `Cleaner` + `try-with-resources` Program

Create file **`CleanerResourceDemo.java`**:

```java
import java.lang.ref.Cleaner;
import java.util.concurrent.atomic.AtomicBoolean;

public class CleanerResourceDemo {
    private static final Cleaner CLEANER = Cleaner.create();

    private static final class State implements Runnable {
        private final AtomicBoolean released = new AtomicBoolean();

        @Override
        public void run() {
            if (released.compareAndSet(false, true)) {
                System.out.println("release");
            }
        }
    }

    static final class Resource implements AutoCloseable {
        private final State state = new State();
        private final Cleaner.Cleanable cleanable =
                CLEANER.register(this, state);

        void use() {
            if (state.released.get()) {
                throw new IllegalStateException("closed");
            }
            System.out.println("using");
        }

        @Override
        public void close() {
            cleanable.clean();
        }
    }

    public static void main(String[] args) {
        try (Resource resource = new Resource()) {
            resource.use();
        }
        System.out.println("after");
    }
}
```

Java 17 commands:

```bash
javac --release 17 CleanerResourceDemo.java
java CleanerResourceDemo
```

**Deterministic stdout:**

```text
using
release
after
```

Explanation:

1. `CLEANER` lives long enough thanks to the static reference.
2. Each `Resource` creates a `State` **that holds no reference back to Resource**.
3. Cleaner registers to track `Resource` with `state`.
4. `try-with-resources` guarantees `close()` runs when leaving the body.
5. `close()` calls `cleanable.clean()`, so the action runs at a clear, deterministic point when this method is called.
6. `AtomicBoolean` demonstrates a guard for repeated/concurrent cleanup; the action does not print/release twice. Even though `clean()` is already at-most-once per Cleanable, the guard helps illustrate that cleanup state should be idempotent.
7. Neither `System.gc()` nor a finalizer is needed to produce the expected stdout.

**This is a demo managing a simulated resource.** `State.run()` only prints a message and does not actually free native memory or a file descriptor. A real application needs appropriate `free(handle)`/`close(fd)`/connection-release logic, error handling, thread safety, and guarantees that code does not use the resource after close.

### 8.1. Why Not Declare `State` as a Non-Static Inner Class?

A `class State implements Runnable` declared **inside `Resource` without `static`** can have an implicit strong reference to the outer `Resource`. Cleaner holds `State` → `State` holds owner → owner is never phantom-reachable.

In the example, `State` is a **static nested class** of `CleanerResourceDemo`, so it has no implicit outer instance reference. It also holds no explicit field of type `Resource`.

### 8.2. Why Doesn't Cleaner Replace `close()`?

Cleaner can only run automatically when the owner becomes eligible for phantom reachability processing and the runtime processes the notification. GC is typically triggered by **heap memory pressure**, not by the OS running low on file handles. A resource may stop being used by the application yet still hold a file descriptor for a long time if waiting for GC.

Therefore, the proper design is usually:

```text
Application lifecycle:
  acquire resource
       │
       ▼
  use resource in try-with-resources
       │
       ▼
  close() → Cleanable.clean() → timely release

Fallback:
  application forgets close()
       │
       ▼
  owner may become phantom-reachable later
       │
       ▼
  Cleaner may run action at an unguaranteed time
```

A fallback can help mitigate some leaks, but **must never be the sole path for critical resources**.

## 9. Finalization vs. Cleaner: Don't Confuse Their Responsibilities

| Property | Legacy `finalize()` | `Cleaner` | `AutoCloseable` / try-with-resources |
| --- | --- | --- | --- |
| API / status | Deprecated; finalization deprecated for removal since JDK 18 | Java 9+, recommended API for fallback cleanup | Standard for explicit lifecycle |
| Typical trigger | GC/finalization processing after reachability conditions | Phantom reachability & reference processing | Scope exit / explicit `close()` |
| Deterministic timing? | **No** | **No** for automatic cleanup | **Yes**, following Java control flow |
| Guaranteed to run before JVM exit? | **No** | **No** (automatic) | Yes when control actually passes through `close`/`try`, not if the process is killed |
| Method on finalizing object? | `finalize()` is called on the object itself | Action separated from owner; does **not** hold owner | `close()` called while the object is still managed by code |
| Object resurrection? | Possible in legacy finalizers | Cannot access referent again via phantom `get()` | No finalizer resurrection pattern |
| Exception semantics | Uncaught finalizer exceptions are ignored | Exceptions from cleaning action are ignored per API | `close()` can throw and caller handles it; suppressed exceptions |
| Proactive cleanup callable? | Do not use `finalize()` as a close API | `Cleanable.clean()` | `close()` or try-with-resources |
| When appropriate? | **Do not write new ones; only handle/migrate legacy** | Fallback for native/off-heap state when callers cannot always be controlled | File/socket/JDBC/native handle with clear ownership and scope |

**Practice:** If a library already supports `Closeable`/`AutoCloseable`, use it. Do not wrap the library in a finalizer. Cleaner is only necessary when designing **a wrapper with specialized off-heap state** where you want an extra safety net if consumers forget to close.

## 10. Upgrade Risks: Legacy Libraries Depending on Finalization

Some older code placed cleanup inside `finalize()` without a public `close()`. When migrating:

1. **Search for `finalize()` overrides** in the codebase and dependency bytecode where possible, not just `System.gc()` calls.
2. Identify the type of resource held: OS file descriptor, native memory, executor, socket, registry entries, or plain Java data structures.
3. Clarify **who owns the resource** and when usage ends.
4. Add **`AutoCloseable`/`close()`** and update callers to use try-with-resources or `finally`.
5. If you cannot control all clients or have native resources needing a fallback, design a Cleaner with **independent state** that does not retain the owner.
6. Verify idempotency and concurrency between explicit close, automatic cleanup, and code actively using the resource.
7. Remove the legacy finalizer after ensuring other cleanup paths cover the need.
8. Test on a JDK supporting `--finalization=disabled` (JDK 18+) to uncover remaining assumptions.
9. Monitor file handle/native memory metrics and integration tests in realistic environments, not just object counts on the heap.

### 10.1. Before–After Migration Pattern

**Before (illustrating legacy pattern only):**

```java
class LegacyHandle {
    private long nativeHandle;

    @Override
    protected void finalize() throws Throwable {
        try {
            releaseNative(nativeHandle);
        } finally {
            super.finalize();
        }
    }

    private static native void releaseNative(long handle);
}
```

This is not a standalone program and intentionally illustrates a design to retire. It lacks a close API and relies on GC timing.

**After — appropriate design skeleton:**

```java
final class HandleOwner implements AutoCloseable {
    private final Cleaner.Cleanable cleanable;

    HandleOwner(long handle) {
        // State is a static nested class, holds handle independently,
        // uses an atomic guard to release at most once.
        State state = new State(handle);
        this.cleanable = CLEANER.register(this, state);
    }

    @Override
    public void close() {
        cleanable.clean();
    }
}
```

This is **illustrative pseudocode**, not a standalone Java file: you need to define `CLEANER`, `State`, `handle` ownership, and native release logic. The `CleanerResourceDemo.java` program in section 8 is the complete compilable/runnable version to observe the pattern and output.

### 10.2. Ownership Must Be Clear to Prevent Double-Free

For native handles, functions like `releaseNative(handle)` may be unsafe if executed twice. The design needs synchronization and a single **OPEN → CLOSED** state transition, must not lend out the raw handle after close, and must be fail-safe on exception paths.

Simply adding a plain `boolean closed` is insufficient when multiple threads can run concurrently. Use `AtomicBoolean`/CAS or synchronization matching the API contract; if the native resource is used concurrently, a one-time cleanup guard is also **not enough** to prevent use-after-close — you also need an ownership/lifetime design or locking for concurrent operations.

## 11. Tricky Case: Resource Must Stay Alive Beyond a Native Operation

GC/JIT can treat a Java wrapper as no longer used **before the end of its lexical scope**, if the thread is only using a primitive `long handle` extracted from the wrapper. Cleaner could run before a native operation using the handle finishes if lifetime is not protected.

Java provides `Reference.reachabilityFence(Object)`:

```java
// Illustrative snippet, assuming owner and nativeUse are declared:
long handle = owner.getHandle();
try {
    nativeUse(handle);
} finally {
    java.lang.ref.Reference.reachabilityFence(owner);
}
```

The fence method keeps `owner` strongly reachable at least until the fence location. It **does not trigger GC, does not close the resource**, and does not replace locking/synchronization when `close()` can run from another thread.

Placing the fence in `finally` ensures it is called even if the native operation throws a Java exception. Apply it when the lifecycle requires it; do not add it mechanically everywhere and treat it as a complete solution for resource safety.

## 12. Why Not Call `finalize()` Manually for Cleanup?

A method named `finalize()` can still be invoked directly in Java under appropriate access conditions, but doing so **does not turn it into a proper resource-closing API with a standard contract**:

- Its visibility is typically `protected`, not intended for external consumers.
- If the JVM still has finalization enabled, calling it manually does not mean the GC mechanism will never invoke the finalizer later.
- Overridden code may rely on state not prepared for multiple invocations.
- A cleanup method should have a clear name/API like `close()`, invoked according to ownership with appropriate idempotent state.

**Do not use** `object.finalize()`, `System.runFinalization()`, or `System.gc()` to handle a resource you already know you are done using.

## 13. How to Check Legacy Code and Compiler Warnings

### 13.1. Java 17 Deprecation Warnings

Example of reading an old class overriding `finalize()` (not recommended to run):

```java
class DeprecatedFinalizerDemo {
    @Override
    protected void finalize() throws Throwable {
        System.out.println("legacy cleanup");
        super.finalize();
    }
}
```

If saved as `DeprecatedFinalizerDemo.java`, you can compile it to **observe the warning**:

```bash
javac --release 17 -Xlint:deprecation DeprecatedFinalizerDemo.java
```

The program above has no `main` and **must not be used to measure finalizer count/timing**. `javac` warning output varies by compiler/version/locale, so no "exact canonical" stderr is provided.

On JDK 18+, `finalize()`/finalization is marked deprecated for removal per JEP 421, and the compiler may display a more specific warning. Do not rely on fixed warning text to determine application correctness.

### 13.2. Finding Overrides/Bytecode

You can scan owned code using repository tools:

```bash
# Find method declarations/overrides in source (for guidance only):
grep -R "finalize(" src

# Inspect methods in a compiled class:
javap -p YourClass
javap -c -p YourClass
```

Text search is only a first step: a transitive library may contain a finalizer whose source is not in the repository. When using `javap`, the name `finalize` in bytecode does not by itself prove it actually manages resources or that finalization is always enabled.

Several JDK resource-management APIs have already migrated away from finalization or use other cleanup mechanisms; read the Javadoc of the **specific API/JDK release** before concluding that every `InputStream` "still has a finalizer".

### 13.3. Testing with Finalization Disabled

A valuable test is: on JDK 18+ supporting `--finalization=disabled`, run an integration suite simulating resource creation/usage/closing and assert **no unbounded growth in file descriptors/native memory**. The test should focus on explicit cleanup and quotas, **without** needing to wait for GC to succeed.

If a test only checks that objects are reclaimed when calling `System.gc()` without checking actual resources, it may miss leaks in file descriptors, sockets, or native allocations.

## 14. Common Misconceptions

1. **"Finalization was removed from Java 17."** False. `Object.finalize()` is still present in Java 17, though deprecated.
2. **"JEP 421 was introduced in Java 9."** False. Java 9 marked `Object.finalize()` deprecated; **JEP 421 belongs to JDK 18** and deprecates finalization for removal.
3. **"Deprecated for removal means the very next JDK will definitely remove it."** False. There is no fixed removal date implied by this status.
4. **"Finalization and garbage collection are the same operation."** False. GC can reclaim heap; a finalizer is a legacy callback with its own processing policy.
5. **"As soon as an object loses its strong reference, `finalize()` runs immediately."** False. Finalizer timing is not guaranteed.
6. **"`System.gc()` is a command to synchronously run all finalizers."** False. There is no such SLA.
7. **"A finalizer can safely handle committing transactions."** False. You cannot rely on timing or completion guarantees.
8. **"An exception from a finalizer will appear in the caller's `catch` block."** False. Uncaught finalizer exceptions are normally ignored by contract.
9. **"A finalizer cannot keep an object alive."** False. Legacy finalization is capable of resurrection.
10. **"If there is no heap leak, there cannot be a resource leak."** False. File descriptors/native handles exist outside the heap.
11. **"Every resource should attach a `Cleaner` instead of having `close()`."** False. Explicit close is the primary path.
12. **"A Cleaner action can freely call `owner.close()`."** False. Capturing the owner can prevent automatic cleanup from ever triggering.
13. **"Cleaner runs right when the scope ends."** False. Automatic cleaning depends on phantom reachability/GC; only explicit clean has deterministic timing.
14. **"Cleaner is guaranteed to run before `System.exit()`."** False. The Javadoc makes no such guarantee.
15. **"A cleaning action can be executed any number of times."** Not recommended. `Cleanable` has at-most-once semantics per registration; state cleanup should be idempotent to protect the resource.
16. **"try-with-resources only calls close when there is no exception."** False. It closes on exceptional paths as well according to the rules.
17. **"The first declared resource is closed first."** False. Resources are closed in reverse order.
18. **"An exception from close always erases the original exception from try."** False. Try-with-resources uses suppressed exceptions for the appropriate cases.
19. **"`AutoCloseable` and `Closeable` are completely unrelated interfaces."** False. `java.io.Closeable` extends `AutoCloseable`, refining the contract.
20. **"`reachabilityFence` runs GC and frees the resource."** False. It maintains strong reachability up to the call site.
21. **"Just using AtomicBoolean eliminates races between use and close."** False. A one-time release guard does not by itself solve concurrent use-after-close.
22. **"Having a Cleaner exempts the application from handling suppressed exceptions."** False. Exceptions on explicit close, Cleaner actions, and business code have different contracts.
23. **"Seeing `finalize()` in bytecode proves a finalizer thread is always running."** False. The runtime can disable finalization depending on JDK/flags; the code may never execute.
24. **"JDK 17 can run `--finalization=disabled` just like JDK 18."** False. The flag was introduced in JDK 18.

## 15. Self-Check and Answers

**Question 1.** Why shouldn't files/sockets be closed in `finalize()`?

**Answer:** The JVM does not guarantee timing or that the finalizer will run before process exit; OS handles can be exhausted even while the Java heap is healthy.

**Question 2.** At which milestone was `Object.finalize()` deprecated, and what does JEP 421 do?

**Answer:** The method was marked deprecated in Java 9; JEP 421 in JDK 18 marks finalization **deprecated for removal** and adds a testing option to disable the mechanism.

**Question 3.** Three resources `A`, `B`, `C` are successfully initialized in the same `try` header. In what order are they closed?

**Answer:** **C → B → A**.

**Question 4.** The `try` body throws error `E1`, and `close()` throws `E2`. With try-with-resources, which error is primary?

**Answer:** `E1` is normally primary; `E2` is suppressed onto `E1`, accessible via `getSuppressed()`.

**Question 5.** Why is a Cleaner action like `() -> this.release()` a trap?

**Answer:** The lambda captures `this`, Cleaner retains the action and thereby keeps the owner strongly reachable; the owner may never reach phantom reachability for the automatic action to run.

**Question 6.** Does `CleanerResourceDemo` print `release` because GC ran on time or because of explicit close?

**Answer:** Because `try-with-resources` calls `close()` and `close()` calls `Cleanable.clean()`, so stdout does not depend on GC timing.

**Question 7.** Does `Cleaner` guarantee all actions will run on `System.exit()`?

**Answer:** No. The Java 17 Javadoc states that behavior on exit is implementation-specific; automatic cleanup has no deadline.

**Question 8.** A legacy library needs to be tested without finalizers, but the application uses JDK 17. Can `--finalization=disabled` be used directly?

**Answer:** No. That flag was introduced in JDK 18. Run tests on a JDK that supports the flag or migrate the resource lifecycle to explicit close.

**Question 9.** What scenario does `Reference.reachabilityFence(wrapper)` help handle?

**Answer:** Ensuring the Java wrapper remains strongly reachable up to the fence location, useful when a native operation still needs the resource associated with the wrapper even though the optimizer sees no other Java-level uses.

**Question 10.** Why is an atomic guard in State not enough to make a native resource thread-safe?

**Answer:** It prevents releasing twice, but if another thread is still using the handle during close, there is still a risk of use-after-close; an ownership/synchronization policy is needed.

**Question 11.** What happens when `finalize()` code throws an uncaught exception?

**Answer:** Per the `Object.finalize()` API contract, the unhandled exception is ignored and finalization of that object terminates; it is not returned to business code callers.

**Question 12.** When should Cleaner be used instead of only try-with-resources?

**Answer:** When designing a wrapper managing off-heap/native state that needs **fallback cleanup** if API users forget to close, while still providing explicit `close()` as the primary mechanism. If a resource already has good close/lifecycle handling, Cleaner is usually unnecessary to add.

## 16. Summary via Architectural Decision

```text
What resource are you managing?
       │
       ├─ Plain Java object, no resource to close?
       │       └─ Hold references as needed, let GC manage the heap.
       │
       └─ File/socket/JDBC/native handle/OS resource needing closing?
               │
               ▼
       Can the owner and end-of-use point be determined?
               │
           Yes ├──► Implement AutoCloseable
               │     + try-with-resources / explicit close
               │     + test exceptional paths / suppressed exceptions
               │
           No / hard to control all clients?
               └──► Still provide explicit close
                     + consider Cleaner fallback
                     + independent State without capturing owner
                     + synchronized and idempotent release
                     + accept that automatic cleanup has no deadline

Legacy finalize():
    ONLY to identify, evaluate, and migrate;
    do not choose as a new design solution.
```

**Key takeaway:** Garbage collection reclaims **Java heap memory**, but does not promise that OS resources will be closed promptly. `Object.finalize()` is a deprecated mechanism and finalization has been **deprecated for removal since JDK 18** due to non-deterministic behavior, resurrection, security/reliability risks, and overhead. In modern Java, **`try-with-resources`/`AutoCloseable` is the primary choice** for clear lifecycles; **`Cleaner` only supplements fallback cleanup** via phantom reachability, with an action that does not retain the owner and has no timing guarantee. Proper design must pay attention to ownership, exception preservation, races between use and close, and testing with finalization disabled.

### Official References

- [Java SE 17 — `Object.finalize()` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#finalize()): deprecation, timing/ordering/exception limitations, and recommended alternatives.
- [JEP 421 — Deprecate Finalization for Removal](https://openjdk.org/jeps/421): JDK 18 milestone, rationale, and `--finalization=disabled`.
- [Oracle JDK 26 Migration Guide — Finalization Deprecated for Removal](https://docs.oracle.com/en/java/javase/26/migrate/migrating-from-jdk-8-later-jdk-releases.html): migration status described in 2026 documentation.
- [Java SE 17 — `Cleaner`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Cleaner.html): phantom reachability, no-reference-to-owner, and at-most-once actions.
- [Java SE 17 — `AutoCloseable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html).
- [JLS Java SE 17 — `try-with-resources` (§14.20.3)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3): close order and suppressed exceptions.
- [Java SE 17 — `Throwable.getSuppressed()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html#getSuppressed()).
- [Java SE 17 — `Reference.reachabilityFence`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Reference.html#reachabilityFence(java.lang.Object)).
- [Java SE 17 — `FileInputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/FileInputStream.html): resource release guidance.
- [Oracle JDK 18 Release Notes — JEP 421](https://www.oracle.com/java/technologies/javase/18-relnote-issues.html).
