# `Object.finalize()` Has Been Marked `deprecated for removal`

## 1. Concept and API Status

`java.lang.Object` is the root class of the Java class hierarchy. It used to provide the method:

```java
@Deprecated(since = "9", forRemoval = true)
protected void finalize() throws Throwable
```

- `finalize()` is a **finalizer**: a legacy mechanism allowing a class to define an operation when the JVM processes an object that is no longer accessed by the program, before reclaiming that object's memory.
- The default `Object.finalize()` implementation **does nothing**. Previously, some classes overrode the method to release off-heap resources such as file descriptors, sockets, or native handles.
- The API was marked deprecated in **Java 9**; **JEP 421 (JDK 18)** marked the finalization mechanism as *deprecated for removal*. As of Java SE 26, `Object.finalize()` is still in the API but is explicitly documented as subject to removal in a later release.
- `@Deprecated(forRemoval = true)` is a signal to migrate away from the API; it **does not mean the method has already been removed** or that existing code is guaranteed not to compile.

Key takeaway: **Do not use `finalize()` to manage resources in new Java code; close resources explicitly.**

## 2. How Finalization Works and Why It Is Unreliable

General progression when finalization is enabled by the JVM:

1. An object with a finalizer is no longer referenced in a way that keeps the program using it.
2. The garbage collector (GC) may identify the object as eligible for finalization, and the JVM may schedule execution of the finalizer.
3. The finalizer, if invoked, runs on a thread not directly chosen by the application. Afterward, the GC still needs to recheck the object's reachability before reclaiming memory.

**There is no guarantee that a finalizer runs immediately, runs before the JVM terminates, or runs before a specific deadline.** An object might never undergo finalization during the entire lifetime of the program. Calling `System.gc()` or `System.runFinalization()` does not turn cleanup into a guaranteed contract.

Core issues:

| Issue | Consequence |
| --- | --- |
| Nondeterministic timing | File descriptors, sockets, or native memory may be held for a long time even though the Java object is no longer used. |
| GC overhead and object retention | Objects requiring finalization may have to go through additional processing before memory is reclaimed. |
| Security risks | A finalizer can access partially initialized object state or bring the object "back to life" (*object resurrection*). |
| Difficult error and concurrency control | Finalizers run on an unspecified thread; uncaught exceptions in a finalizer are ignored. |
| Difficult testing | Results depend on GC, execution timing, and JVM state; tests may pass intermittently or flake. |

For a given object, the JVM will not automatically call the finalizer more than once; that still **does not guarantee even a single invocation** before the program stops. The GC manages **heap memory**, and does not automatically know when business logic has finished using all operating system resources.

## 3. Similar-Looking Names with Different Natures

- `finalize()`: legacy cleanup callback tied to object lifecycle and GC; deprecated for removal.
- `finally`: block of `try/catch/finally`, executed when control flow leaves `try` under normal rules; can be used to call `close()`.
- `final`: keyword prohibiting variable reassignment, method overriding, or class inheritance depending on context; unrelated to finalizers.
- `close()` and `AutoCloseable`: interface for intentional caller-driven resource lifecycle management, typically combined with `try-with-resources`.

## 4. Solution When Code Needs to Close Resources

When a class owns a file, socket, connection, or handle that must be closed on time, have the class implement `AutoCloseable` and arrange for the consumer to call `close()` at the ownership boundary; the most common approach is `try-with-resources`. Java calls `close()` when leaving the block in normal execution flow, including when the block body throws an exception. This is a control-flow contract, not a GC side effect.

```java
try (var reader = java.nio.file.Files.newBufferedReader(path)) {
    System.out.println(reader.readLine());
}
```

This is an illustrative snippet inside a method that has a `path` variable of type `Path`, with `IOException` handled or declared appropriately. The in-depth lesson on `AutoCloseable` analyzes closing order, ownership, and suppressed exceptions.

## 5. Cleaner Only Plays a Fallback Role

`java.lang.ref.Cleaner` (Java 9+) allows registering an independent cleaning action and calling `Cleanable.clean()` proactively. When relying solely on GC triggers, this action **has no deadline** and may not run before the JVM exits. Do not use Cleaner to replace `close()` or to commit or flush mandatory data. If used for a native handle, the action must not hold a strong reference to the tracked object itself. The Cleaner lesson at the end of the chapter explains independent state design and reference traps.

## 6. Auditing Legacy Code and Checking Compatibility

When maintaining a codebase with finalizers:

1. Find classes overriding `finalize()`, both in source code and dependent libraries. Inspect which resources are actually owned, who is responsible for closing them, and the exception-handling path.
2. Move primary cleanup operations to `close()` or an equivalent closing API; update call sites with `try-with-resources` or `finally` when appropriate.
3. If a fallback layer is needed for native resources, consider `Cleaner` with state that does not reference the registered object itself.
4. Test normal paths, exception paths, repeated `close()` calls, and closing a resource that was never used.
5. Try running with finalization disabled to detect remaining dependencies:

```bash
# Option available since JDK 18; replace App with the actual main class.
java --finalization=disabled App
```

You can use `jdeprscan --for-removal your-app.jar` to find references to standard APIs marked for removal in a JAR file. However, bytecode scanning **does not replace searching for `finalize()` methods declared by the project itself**; you need to inspect source code, libraries, and resource behavior. Do not use `System.runFinalization()` as a workaround: this API is also deprecated for removal and does not provide the required cleanup guarantee.

## 7. Common Mistakes and How to Remember

- **Wrong:** “When the GC reclaims an object, all its files/sockets are closed on time.” **Right:** The GC primarily reclaims Java memory; off-heap resources need their own closing lifecycle.
- **Wrong:** “Using `finally` and `finalize()` is the same.” **Right:** `finally` belongs to code execution flow; `finalize()` depends on the finalization mechanism.
- **Wrong:** “`deprecated for removal` means `finalize()` has already been removed.” **Right:** It warns of planned removal in the future; check the target API/JDK.
- **Wrong:** “Registering a Cleaner lets you omit `close()`.” **Right:** Cleaner is only suitable as a fallback safeguard with no timing guarantee.
- **Wrong:** “Waiting on `System.gc()` until the finalizer runs is a stable test.” **Right:** Test explicit closing operations and observable resource state instead.

**Design principle:** whichever object owns a resource must provide a clear way to close it; consuming code must determine the closing time. `Object.finalize()` is a historical mechanism that should be excluded from new designs.

## 8. Official Documentation

- [JEP 421 — Deprecate Finalization for Removal](https://openjdk.org/jeps/421)
- [Java SE 26 — `java.lang.Object.finalize()` API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Object.html#finalize())
- [Java SE 26 — JLS §12.6, Finalization of Class Instances](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-12.html#jls-12.6)
- [Java SE 26 — `Cleaner` API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ref/Cleaner.html)
- [Java SE 26 — `AutoCloseable` API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/AutoCloseable.html)
