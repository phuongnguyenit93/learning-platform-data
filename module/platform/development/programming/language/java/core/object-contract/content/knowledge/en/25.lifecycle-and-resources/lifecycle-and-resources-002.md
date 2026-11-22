# No Guarantee on When or Whether a Finalizer Will Run

## 1. Core Problem

In Java, a **finalizer** is the `finalize()` method that a class can override to request an action when an object is about to be processed by the Garbage Collector (GC). This is a legacy cleanup mechanism and is **unreliable for resource management**.

There is no guarantee that:
- An object will be processed by the GC immediately when it is no longer used by the program.
- `finalize()` will be called within a deterministic time window, even when the object is no longer referenced.
- `finalize()` for all objects will run before the application terminates.
- A finalizer will execute successfully or release resources in time when the application runs out of memory, is stopped, or the JVM exits.

**Consequence:** do not use finalizers to close files, sockets, database connections, release locks, complete transactions, write critical data, or perform any action that requires guaranteed timing.

In the context of *lifecycle and resources*, two kinds of work must be clearly separated:
- **Reclaiming heap memory managed by the JVM:** the GC handles this; the program does not need to and cannot force the collection time of individual objects.
- **Releasing resources with business lifecycles or off-heap resources:** the application must manage these explicitly, usually via `AutoCloseable` and `try-with-resources`.

## 2. How Does Finalization Work and Why Is It Unpredictable?

A simplified model:

~~~text
Object created
      |
      v
Currently reachable
      |
      v
No longer reachable under JVM rules
      |
      v
Eligible for GC consideration
      |
      +---- GC has not run / not processed object ----> waits indefinitely
      |
      v
May be queued for finalization processing (legacy mechanism)
      |
      +---- finalizer may be delayed, not complete
      |
      v
GC may reclaim memory when conditions are suitable
~~~

This diagram only illustrates important relationships; it is not a schedule that the JVM commits to executing step-by-step at a fixed time.

### 2.1. Losing References Does Not Mean Immediate GC

When the program no longer uses an object, its memory **may** be collected. The JVM decides when to collect based on allocation activity, heap state, collector algorithms, and other conditions. The JVM may not run GC before the program completes. Therefore, "the object is no longer used" is not an event for predicting when `finalize()` runs.

### 2.2. GC Does Not Mean the Finalizer Will Complete

Even in environments that still support finalization, an object becoming eligible for processing is not a guarantee that its finalizer will run before a specific deadline. Finalizers are executed by the runtime mechanism, not called by the business thread where the resource's usage ends. A slow, hung, or lock-waiting finalizer can impede cleanup.

Modern Java versions have marked finalization as a mechanism to be removed. `Object.finalize()` was marked deprecated in Java 9; Java 18 further marked it **deprecated for removal** under JEP 421. Therefore, new code should not be designed around this method.

### 2.3. A GC Hint Is Not a Promise

~~~java
System.gc(); // Only a GC request/hint; does not guarantee the finalizer is called
~~~

The call above is a single illustrative line of Java, not a standalone program. It does not guarantee that GC runs, does not guarantee a specific object is processed, and **does not guarantee the timing or execution of `finalize()`**. Placing `System.gc()` after dropping references does not turn a finalizer into a safe resource-closing mechanism.

### 2.4. An Application Can Terminate Before Cleanup

When a short-lived program ends, the JVM has no obligation to run all pending finalizers. Abnormal termination scenarios make relying on finalizers even riskier. A resource such as a file descriptor or socket may therefore fail to be released **on time** by merely waiting for GC.

The operating system usually reclaims many resources when a process exits, but that does not replace the application closing resources according to their lifecycle, flushing necessary contents, or completing transactions.

## 3. Placing Finalizers in the Proper Lifecycle Model

`finalize()` belongs to the GC reachability-processing mechanism; `finally` is a control-flow construct that runs when leaving `try` according to Java rules; and `final` prevents certain assignments, overrides, or inheritance. Thus, a `final` variable or a `finally` block does not make a finalizer capable of running on time. The later lesson distinguishing these three keywords clarifies the syntax and `return`/`throw` cases.

## 4. Practical Comparison: Close Immediately or Wait for GC?

For resources owned by the code itself, place usage inside `try-with-resources`:

~~~java
try (java.io.InputStream in = java.nio.file.Files.newInputStream(path)) {
    System.out.println(in.read());
}
~~~

This snippet assumes `path` is of type `Path` and the calling code handles or declares `IOException`. Upon exiting the block, the JVM executes the `close()` path according to the Java language; when merely dropping references to wait for `finalize()`, the program cannot deduce when the resource will be released. `close()` can still throw an exception, so callers must handle errors rather than assuming cleanup always succeeds. Details on closing order and suppressed exceptions are covered in the lesson on `AutoCloseable`.

## 5. Why Is Using a Finalizer to Close Resources Wrong?

Consider the following flawed idea (illustrative only, **should not be applied**):

~~~java
// Illustrative code inside a class holding a resource, not a complete program.
@Override
protected void finalize() throws Throwable {
    try {
        releaseNativeResource(); // Hoping the GC will call this at an appropriate time
    } finally {
        super.finalize();
    }
}
~~~

`releaseNativeResource()` is a hypothetical method name to illustrate the idea, not a built-in API or standalone snippet. Even if the cleanup method is correct, the program can still hold onto file descriptors/sockets/native memory until an unpredictable time, or never call the finalizer before stopping.

Finalization also creates additional problems:

- **Resource backlog:** available heap memory does not fully reflect pressure on file descriptors, network connections, or native memory; the JVM may see no reason to run GC immediately.
- **Performance:** objects with finalizers can require more complex GC processing; a slow finalizer can delay cleanup of other objects.
- **No guaranteed order:** you cannot assume the finalizer of resource A runs before B even if A depends on B.
- **Exceptions and failures:** uncaught exceptions in a finalizer do not provide a reliable business-error reporting mechanism to the thread that used the resource.
- **Object resurrection:** a finalizer can make the object reachable again by storing `this` elsewhere. This makes the lifecycle hard to reason about; the finalizer of the same object is not called repeatedly forever by the JVM just because it becomes unreachable again.
- **Safety and maintainability:** finalizers execute outside normal business control flow, making ordering, state, and interaction with synchronization mechanisms hard to determine.

If a resource must be released immediately after an operation finishes, releasing it must be part of the execution flow or an explicitly managed component lifecycle.

## 6. Cleaner Does Not Create a Cleanup Deadline

`Cleaner` can perform fallback cleanup after a referent becomes phantom-reachable, but there is no guarantee the GC will identify it and the action will complete before a deadline. When deterministic closing is needed, have the owner call `close()`; a native library may add `Cleaner` as a fallback line of defense. If `close()` calls `Cleanable.clean()`, the proactive path executes the action immediately during the call; this differs from waiting for Cleaner to run automatically. The action must not hold a strong reference to the referent.

## 7. Common Reasoning Mistakes

| Claim | Accurate Assessment |
| --- | --- |
| “Leaving scope means the finalizer runs immediately.” | False. Scope and reachability do not establish a finalization schedule. |
| “Putting `System.gc()` before exiting is enough.” | False. It is not a GC/finalization guarantee. |
| “Finalizers will close all files before the JVM exits.” | False. Not guaranteed. |
| “`finally` is the same as `finalize()`.” | False. `finally` is tied to control flow; `finalize()` is tied to the legacy GC mechanism. |
| “`final` helps an object automatically release resources.” | False. `final` does not manage resource lifecycles. |
| “Cleaner always runs when an object is no longer used.” | False. Automatic cleaning has no deadline or guarantee before shutdown. |
| “GC already manages memory, so sockets/streams don't need closing.” | False. OS resources and flush/close contracts require separate handling. |
| “`try-with-resources` calls `close()` immediately upon leaving the block.” | True in normal Java execution flow, including when the body throws an exception. |

## 8. How to Design Resource Lifecycles

When writing or reviewing a Java class that owns resources, identify each step in order:

1. **Which resources need closing?** For example: file streams, sockets, JDBC resources, native handles, executors, or a client with a `close()`/`shutdown()` API.
2. **Who owns the resource?** Ownership determines who is responsible for closing it and when. If a method opens a short-lived resource itself, it usually closes it right inside the method.
3. **Where is the lifecycle boundary?** Wrap the resource in `try-with-resources` if appropriate; for long-lived components, arrange a lifecycle hook or explicit `close()` call from the owning component.
4. **What if an operation throws an exception?** Use `try-with-resources` or `finally` properly; decide how to log/handle closing exceptions and suppressed exceptions.
5. **What if the caller forgets to close?** You may consider Cleaner as a last-resort fallback for certain native resources, while still treating forgetting to close as a contract bug.
6. **How to test it?** Test that `close()` is called the right number of times and at the right time, even when operations fail. Do not write tests relying on `System.gc()` or fixed sleeps hoping `finalize()` appears.

Example knowledge-check question: “An object opens a file and is no longer referenced. Is the file guaranteed to be closed within one second?” **No.** Being eligible for collection creates no guarantee on GC or finalizer timing. If the program needs to close the file after reading, use `try (InputStream in = ...) { ... }` and let `close()` occur at the end of the block.

## 9. Key Takeaways

- **Finalization is a legacy, unpredictable mechanism that has been deprecated for removal.**
- **You cannot infer execution timing or guarantee finalizer execution from losing references, GC, or `System.gc()`.**
- **Clean up resources according to clear ownership and lifecycle:** `AutoCloseable`, `try-with-resources`, or `close()`/`shutdown()` when a component finishes.
- **Cleaner is only a fallback layer for certain cases**, not a replacement for explicit cleanup.
