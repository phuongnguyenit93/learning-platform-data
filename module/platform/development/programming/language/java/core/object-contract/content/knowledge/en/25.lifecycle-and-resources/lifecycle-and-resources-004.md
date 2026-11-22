# Do Not Use Finalizers as a Mandatory Mechanism to Release Resources

## Objectives

After this lesson, you will be able to distinguish between reclaiming **heap memory** and releasing **off-heap resources**; explain why `finalize()` does not guarantee resource closing; and design resource lifecycles using `AutoCloseable`, `try-with-resources`, and clear ownership rules.

## 1. The Garbage Collector Does Not Replace Closing Resources

The garbage collector (GC) manages object reachability and reclaims Java memory when appropriate. However, file descriptors, sockets, database connections, native handles, I/O streams, and many operating system resources have their own lifecycles and quotas. A wrapper object no longer being used **does not mean** the resource it represents has been released in time.

For example, a program that opens many files without closing them can exhaust file descriptors even when the heap still has plenty of memory. The goal of resource management is to determine *who owns a resource and when its use ends*, rather than waiting for the GC to guess when to clean up.

## 2. How Does `finalize()` Work and Why Should You Not Rely on It?

In the legacy finalization model, a class can override `protected void finalize() throws Throwable`. When an object becomes eligible for collection, the JVM *may* process its finalizer. This is not a promise that the method will run immediately, run before any deadline, or run before the process exits.

`Object.finalize()` was marked deprecated in Java 9; **JEP 421 (JDK 18)** marked finalization for removal in a future release. Software needs to work correctly even when finalization is disabled or never called.

Key issues:

- **Nondeterministic timing:** when an object becomes unreachable and when the GC/finalizer processes it do not follow the business timing required to close a file or connection. `System.gc()` is only a request and does not turn finalizers into a reliable mechanism.
- **No execution guarantee:** GC may not run, finalizers may be delayed indefinitely, the environment may disable finalization, or the JVM may exit before cleanup occurs.
- **Hard-to-control order and interactions:** related resources may already be in a different state; execution on a dedicated finalization thread makes synchronization and errors hard to predict.
- **Overhead and risks:** finalizers can slow down memory reclamation, prolong object lifetimes, and create bug/security surfaces. A finalizer can also resurrect an object (object resurrection), making lifecycle reasoning complex.
- **Hard-to-observe failures:** uncaught exceptions in a finalizer do not provide a cleanup error-reporting mechanism like a direct `close()` call at the resource owner.

**Rule:** do not write `finalize()` to perform mandatory work such as flushing data, committing/rolling back, closing sockets, returning connections to a pool, or releasing native handles. Work that must complete must reside in a controlled execution flow.

## 3. Primary Approach: Require the Owner to End the Lifecycle

Replacing a finalizer with `close()` is only right when **the owner actually calls** that method. For short-scoped resources, `AutoCloseable` with `try-with-resources` lets Java attempt to close whether the body succeeds or throws an error:

```java
try (var writer = java.nio.file.Files.newBufferedWriter(path)) {
    writer.write("Hello");
}
```

This illustrative snippet assumes `path` is a `Path` and `IOException` exceptions are declared or handled. `close()` must release the real resource, and closing errors must be observed; `try-with-resources` preserves the primary error from the `try` body and attaches `close()` errors as suppressed exceptions via `getSuppressed()`. Resources declared in order A then B are closed B before A.

The next lesson on `AutoCloseable` provides runnable programs, file reading/writing and JDBC examples, verifying closing order and dual-error paths. Here the focus is on **redesigning ownership and closing points** when removing finalizers, rather than merely renaming a callback.

## 4. Designing a Self-Managed Resource Class

When wrapping a native handle, socket, or closeable object yourself, implement `AutoCloseable` (or `Closeable` if appropriate for an I/O contract):

1. Identify which object **owns** the resource and who must call `close()`. If a library/framework/pool owns the resource, do not arbitrarily close a borrowed object.
2. Clarify **open / closed** state; after `close()`, reject invalid operations. Depending on the resource type, design `close()` to be safe when called repeatedly.
3. Release the actual resource inside `close()`, reporting errors appropriately. When cleanup can fail, attempt to release the remaining parts and manage exceptions deliberately.
4. Transfer ownership transparently if returning a resource out of the current scope. Do not close a resource still used by another component.
5. If using the resource across multiple threads, specify thread safety clearly and synchronize `close()`/usage state; a plain `boolean` flag does not guarantee thread safety by itself.

Example that only **simulates the lifecycle** without opening a real native handle:

```java
// OwnershipDemo.java
public class OwnershipDemo {
    static final class ManagedResource implements AutoCloseable {
        private boolean closed;

        void use() {
            if (closed) {
                throw new IllegalStateException("Resource closed");
            }
            System.out.println("Using");
        }

        @Override
        public void close() {
            if (!closed) {
                closed = true;
                System.out.println("Closed");
            }
        }
    }

    public static void main(String[] args) {
        try (ManagedResource resource = new ManagedResource()) {
            resource.use();
        }
    }
}
```

```bash
javac OwnershipDemo.java
java OwnershipDemo
```

```text
Using
Closed
```

In real implementations, place the code that releases the file/socket/native handle inside `close()`; do not confuse the example's `System.out.println("Closed")` statement with an actual release operation. For resources requiring thread safety, synchronize or use an appropriate atomic state mechanism.

## 5. Cleaner Does Not Turn Fallback Cleanup into Mandatory Cleanup

You may register a `Cleaner` for a native handle wrapper if you need to mitigate the consequences of users forgetting `close()`, but the action only runs automatically when reachability conditions and scheduling allow. Business flow must still close proactively; the action must be decoupled from the tracked object and guard against double-freeing. Do not put flushes, commits/rollbacks, or mandatory notifications in a Cleaner callback. The final lesson in this chapter walks through the `Cleanable` pattern and testing this limitation.

## 6. Migrating from Finalizer-Based Code to Explicit Resource Management

Suppose legacy code relies on `finalize()` to close a handle. The proper migration path:

1. Locate `finalize()` overrides, the resources released inside them, and where those objects are instantiated. Check relevant dependencies as well.
2. Add `close()` / `AutoCloseable`, extract cleanup logic into an explicit operation with double-close protection; remove business reliance on the finalizer.
3. Update the object's **owner** to use `try-with-resources` when scoped, or call `close()` at the service/component's shutdown point for longer lifecycles.
4. Test normal paths, exceptions during use, exceptions during closing, repeated close calls, and use after close. Verify the actual resource is released **without calling `System.gc()`**.
5. Consider Cleaner only to mitigate leaks from callers forgetting to close for suitable resources; do not treat it as the primary cleanup path.

Illustrative snippet of the idea to avoid:

```java
// Legacy code, should not be used: intentionally an illustrative fragment only.
@Override
protected void finalize() throws Throwable {
    releaseNativeHandle();
}
```

Recommended design: the object owning the handle implements `AutoCloseable`, calls `releaseNativeHandle()` from `close()`, and requires the creator/owner of the object to end usage via `try-with-resources` or explicit `close()`. The `releaseNativeHandle()` method in the fragment above is a hypothetical illustrative name, not a Java API.

## 7. Common Mistakes

| Concept or Practice | Problem | Alternative |
| --- | --- | --- |
| “GC will automatically close files/connections” | Reclaiming memory and closing OS resources are two different responsibilities | Close on time via `try-with-resources` |
| Calling `System.gc()` after using a resource | Does not guarantee GC or finalizers run on time | Call `close()` at the ownership boundary |
| Using `finalize()` to flush, commit, or rollback | These operations need control over order, errors, and timing | Execute proactively in business flow |
| Installing only `Cleaner`, without `close()` | Automatic Cleaner still has no guaranteed deadline | `close()` is primary; Cleaner is only fallback |
| Relying on shutdown hooks to close individual objects | Hooks belong to process lifecycle, may not run on all exit types, and do not manage per-resource lifecycles | Close immediately when no longer used |
| Closing resources owned by a framework/pool | Can break objects that are shared or reused | Follow the API's ownership contract |

## 8. Self-Check

- When a `Socket` is no longer referenced, can we immediately conclude the socket has been closed? **No.** Losing references does not guarantee OS cleanup has occurred in time.
- When both the `try-with-resources` body and `close()` throw exceptions, where do you find the closing error? **`Throwable.getSuppressed()`** on the primary exception.
- Can Cleaner be used to ensure data is flushed before returning an HTTP response? **No.** Flush/close explicitly in a controlled processing flow.
- Does a class holding no files/sockets/native handles need a finalizer for GC to free heap memory? **No.** GC automatically manages memory for ordinary objects.

**Key takeaway:** resource lifecycles must be designed around **ownership + explicit closing operations**. Finalizers and GC-dependent callbacks do not satisfy guarantees for releasing resources at mandatory times.

## References

- [JEP 421 — Deprecate Finalization for Removal](https://openjdk.org/jeps/421)
- [Java SE 17 — AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html)
- [Java SE 17 — Cleaner](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Cleaner.html)
