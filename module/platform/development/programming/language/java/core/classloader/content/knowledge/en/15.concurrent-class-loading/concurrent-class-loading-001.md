# Class Loading Locks in the Default ClassLoader Implementation

> **Scope:** Java Core → ClassLoader → Concurrent Class Loading. This lesson explains why the JVM needs synchronization when multiple threads concurrently request the same class, the default locking path of `ClassLoader.loadClass(String, boolean)`, the role of `getClassLoadingLock(String)`, the difference between regular loaders and *parallel-capable loaders*, along with deadlock, race condition, and `LinkageError` scenarios when writing your own loader. Examples compile with Java 17+.

## 1. The Problem: Two Threads Loading the Same Class Name

Suppose a program has a custom loader `L`, and two threads almost simultaneously call:

```java
// Two calls on the same ClassLoader instance L:
L.loadClass("demo.Widget");
L.loadClass("demo.Widget");
```

If the loading path is not properly synchronized, both threads might:

1. Both check that `demo.Widget` is not present yet.
2. Both read `demo/Widget.class` from disk/JAR.
3. Both prepare to call `defineClass("demo.Widget", ...)` using the **same defining loader**.
4. One thread defines it first; the other thread tries to redefine the same binary name and may cause **`LinkageError`: duplicate class definition**.

The JVM identifies an ordinary class/interface by the pair **(binary name, defining loader)**. Two distinct definitions with the same binary name cannot be registered under the **same defining loader**, even if the bytecode from the two reads is identical.

At the same time, the JVM must allow multiple threads to access a loaded class and receive the **same `Class<?>` object**. That is why the standard `loadClass` path includes checking for an already recorded class, parent delegation, finding bytes, and synchronizing via the **class-loading lock**.

**Key takeaway:** Not everything related to the JVM is globally locked; the lock used by Java `ClassLoader` depends on whether the loader is registered as *parallel-capable*.

## 2. Standard Path of ClassLoader.loadClass

Two APIs:

```java
public Class<?> loadClass(String name) throws ClassNotFoundException;

protected Class<?> loadClass(String name, boolean resolve)
        throws ClassNotFoundException;
```

The public overload invokes logic equivalent to `loadClass(name, false)`. In the **default implementation** of the protected overload, the Javadoc describes the execution flow as follows:

```text
loadClass("demo.Widget", resolve)
           |
           v
synchronized (getClassLoadingLock("demo.Widget"))
           |
           +--> findLoadedClass("demo.Widget")
           |        |
           |        '--> already exists -> reuse the corresponding Class<?>
           |
           +--> if not present, try parent.loadClass("demo.Widget")
           |        |
           |        '--> parent finds it -> use Class<?> returned by parent
           |
           +--> if parent cannot find it, call findClass("demo.Widget")
           |        |
           |        '--> subclass finds bytes and calls defineClass(...)
           |
           +--> if resolve == true: resolveClass(result)
           |
           '--> return Class<?>
        (release class-loading lock)
```

This is the general sequence according to Java SE 21 `ClassLoader.loadClass(String, boolean)`. The most important point is that the lock covers **the entire class-lookup cycle in the default implementation**, not just the `defineClass` statement.

### Meaning of Each Step

- `getClassLoadingLock(name)`: returns the object used to synchronize loading the class named `name`.
- `findLoadedClass(name)`: checks whether the class has been recorded by the JVM as loaded by the loader per the API semantics; if so, it does not define it again.
- **Parent delegation:** queries the parent first to keep platform and shared classes with consistent identity under the default policy.
- `findClass(name)`: the recommended extension point for subclasses; reads class bytes from the custom loader's source and calls `defineClass`.
- `resolveClass(clazz)`: if requested, triggers linking per the method contract. **Does not mean automatically running the static initializer.**

The Javadoc emphasizes: **unless overridden**, `loadClass(String, boolean)` synchronizes on the result of `getClassLoadingLock` throughout the loading process. If a subclass overrides `loadClass` completely, it is responsible for maintaining proper class-lookup logic, synchronization, deadlock safety, and Java type identity.

## 3. The Class-Loading Lock Is Not Always the ClassLoader Itself

Method:

```java
protected Object getClassLoadingLock(String className);
```

According to Java SE 21:

| Type of ClassLoader Instance | Value of `getClassLoadingLock(name)` |
| --- | --- |
| **Not registered as parallel-capable** | **The loader object itself (`this`)**, shared across all names. |
| **Registered as parallel-capable** | **A lock associated with the specific class name** for that loader. |

Diagram:

```text
Non-parallel loader L:
    getClassLoadingLock("demo.A") --> L
    getClassLoadingLock("demo.B") --> L
    getClassLoadingLock("demo.C") --> L
                                    same monitor

Parallel-capable loader P:
    getClassLoadingLock("demo.A") --> lock[A]
    getClassLoadingLock("demo.B") --> lock[B]
    getClassLoadingLock("demo.A") --> lock[A]
                                    different names, different locks,
                                    same name, same lock
```

With a non-parallel loader, multiple threads loading **two differently named classes** on the same loader still have to wait on the same monitor if the default `loadClass` implementation is used. Simple, but it can limit throughput.

With a parallel-capable loader, requests for **different names** can pass through the loading section of the same loader concurrently. However, threads needing to load the **same name** still synchronize on the same lock so as not to double-define.

**Understand the limitation properly:** parallel-capable is *the capability to allow* concurrency at the class-name lock level, not a guarantee that all loading work will actually run in parallel at full speed. Disk I/O, parent loaders, package metadata, filesystem, network, JVM linking, and other locks can still cause contention.

### Observing getClassLoadingLock from a Subclass

Because `getClassLoadingLock` is `protected`, you can create a diagnostic wrapper method inside a subclass:

```java
class DiagnosticLoader extends ClassLoader {
    Object lockFor(String className) {
        return getClassLoadingLock(className);
    }
}
```

This is a **compilable class**, though it lacks `main`. Do not expose the lock object publicly in a production API for callers to lock arbitrarily for long durations; it can stall other class-loading requests or create deadlocks.

## 4. How Does Parallel-Capable Affect the Default Lock?
An **unregistered** `ClassLoader` subclass uses the shared lock `this`; a **parallel-capable** one uses a per-binary-name lock and can load different names concurrently. Registration is performed via `registerAsParallelCapable()` in the static initializer **of each subclass**, before any instance exists, and requires all superclass loaders to also be registered. Check `isRegisteredAsParallelCapable()` to avoid wrong assumptions.
The `ParallelLoader` example right below demonstrates this completely: the same name keeps a stable lock, eight threads return the same `Class<?>`, and `findClass` only needs to define it once. Registration **does not automatically make** a `HashMap`, I/O streams, package metadata, or your overridden `loadClass` code thread-safe. A separate lesson on `registerAsParallelCapable` analyzes the superclass, caller, and timing rules in depth.

## 5. Runnable Example on Java 17+: Observing Locks and 8 Threads Loading the Same Class

The experiment creates a `SerialLoader` that is not registered as parallel-capable and a `ParallelLoader` that is registered. Both extend `ClassLoader` directly, so they are not affected by the application loader's implementation.

`ParallelLoader` overrides **`findClass`**, not `loadClass`. As a result, the standard Java SE lock still covers the already-loaded check, parent delegation, and new definition.

### Source Structure

```text
src/
  demo/
    Widget.java
  app/
    LoadingLockDemo.java
plugin-classes/    (created by javac)
app-classes/       (created by javac)
```

**File `src/demo/Widget.java`:**

```java
package demo;

public class Widget {
    public int answer() {
        return 42;
    }
}
```

**File `src/app/LoadingLockDemo.java`:**

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;

public class LoadingLockDemo {
    static class SerialLoader extends ClassLoader {
        SerialLoader() {
            super(ClassLoader.getPlatformClassLoader());
        }

        Object lockFor(String name) {
            return getClassLoadingLock(name);
        }
    }

    static final class ParallelLoader extends ClassLoader {
        static {
            if (!registerAsParallelCapable()) {
                throw new ExceptionInInitializerError(
                        "Registration failed");
            }
        }

        private final Path root;
        final AtomicInteger findCalls = new AtomicInteger();

        ParallelLoader(Path root) {
            super(ClassLoader.getPlatformClassLoader());
            this.root = root;
        }

        Object lockFor(String name) {
            return getClassLoadingLock(name);
        }

        @Override
        protected Class<?> findClass(String binaryName)
                throws ClassNotFoundException {
            findCalls.incrementAndGet();

            try {
                byte[] bytes = Files.readAllBytes(
                        root.resolve(
                                binaryName.replace('.', '/') + ".class"));
                return defineClass(
                        binaryName, bytes, 0, bytes.length);
            } catch (IOException e) {
                throw new ClassNotFoundException(binaryName, e);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        SerialLoader serial = new SerialLoader();
        ParallelLoader parallel =
                new ParallelLoader(Path.of("plugin-classes"));

        System.out.println("serial registered: "
                + serial.isRegisteredAsParallelCapable());
        System.out.println("serial same lock for A/B: "
                + (serial.lockFor("demo.A")
                        == serial.lockFor("demo.B")));
        System.out.println("parallel registered: "
                + parallel.isRegisteredAsParallelCapable());
        System.out.println("parallel same lock for A/B: "
                + (parallel.lockFor("demo.A")
                        == parallel.lockFor("demo.B")));
        System.out.println("parallel same lock for A: "
                + (parallel.lockFor("demo.A")
                        == parallel.lockFor("demo.A")));

        int requests = 8;
        CountDownLatch start = new CountDownLatch(1);
        var pool = Executors.newFixedThreadPool(requests);
        try {
            List<Future<Class<?>>> tasks = new ArrayList<>();
            for (int i = 0; i < requests; i++) {
                tasks.add(pool.submit(() -> {
                    start.await();
                    return parallel.loadClass("demo.Widget");
                }));
            }

            start.countDown();
            Class<?> first = tasks.get(0).get();

            boolean same = true;
            for (Future<Class<?>> task : tasks) {
                same &= task.get() == first;
            }

            System.out.println("requests: " + requests);
            System.out.println("one Class object: " + same);
            System.out.println("findClass calls: "
                    + parallel.findCalls.get());
            System.out.println("defining loader matches: "
                    + (first.getClassLoader() == parallel));
        } finally {
            pool.shutdownNow();
        }
    }
}
```

### Compile and Run

From the root directory containing `src`, run:

```bash
javac --release 17 -d plugin-classes src/demo/Widget.java
javac --release 17 -d app-classes src/app/LoadingLockDemo.java
java -cp app-classes LoadingLockDemo
```

**Stdout compiled with `--release 17` and verified on OpenJDK 24:**

```text
serial registered: false
serial same lock for A/B: true
parallel registered: true
parallel same lock for A/B: false
parallel same lock for A: true
requests: 8
one Class object: true
findClass calls: 1
defining loader matches: true
```

### Line-by-Line Explanation

1. `SerialLoader` does not call `registerAsParallelCapable`: status is `false`. The two names `demo.A` and `demo.B` share the `serial` instance's monitor, so the `==` comparison is `true`.
2. `ParallelLoader` calls registration in its static initializer before being instantiated: status is `true`. Two different names use two different locks; calling again with the same name returns the same lock.
3. `plugin-classes` **is not in `-cp app-classes`**; the parent platform loader does not define `demo.Widget` from there. Therefore, `ParallelLoader.findClass` actually reads the bytes and creates the class.
4. `CountDownLatch` gets eight tasks ready and then allows them to call `parallel.loadClass("demo.Widget")` simultaneously. The scheduler may run them at different times; we **do not rely on timing** to assert the degree of parallelism.
5. Because it is the same loader + same binary name, the per-name lock, `findLoadedClass`, and `defineClass` coordinate so that every task results in **the exact same `Class<?>`**, while `findClass` is called only **once in this configuration**.
6. `first.getClassLoader() == parallel` proves that the custom loader is the **defining loader** in the example. If the parent already contained `demo.Widget`, the result would need to be interpreted differently.

**Important:** this test demonstrates the lock behavior and safe loading of a single name. It does **not** measure speed or prove that `findClass` for two different names always runs in parallel; measuring that requires a controlled benchmark.

## 6. Why Don't Two Threads Loading the Same Name Create Two Class<?> Objects?

Inside the default `loadClass`, `synchronized (getClassLoadingLock(name))` protects the *check–delegate–find–define* sequence.

An illustrative timeline:

```text
Thread A                              Thread B
--------                              --------
lock("demo.Widget") acquired          waits for same lock
findLoadedClass -> null
parent lookup -> missing
findClass -> defineClass -> C
return C; release lock
                                      acquire same lock
                                      findLoadedClass -> C
                                      return C; release lock
```

The key is **re-checking under the lock**. Checking `findLoadedClass` only outside the lock and then calling `defineClass` unsynchronized is a time-of-check/time-of-use pattern prone to race conditions.

With a parallel-capable loader, the per-name lock protects each class individually. Two names `demo.Widget` and `demo.Helper` have different locks; that does not exempt the need to synchronize **shared state** elsewhere:

- The same archive/JAR reader with mutable state.
- Caches mapping resources, package metadata, or verification results.
- `definePackage` for two differently named classes in the **same package**.
- Global bytecode transform pipeline, generator cache, and class signers.
- Cross-references between plugin loaders forming a delegation graph.

You should distinguish the **class-loading lock** of the base class from other mutexes you design yourself. A loader that is already parallel-capable whose `findClass` is not thread-safe can still fail.

## 7. Override findClass; Do Not Rush to Override loadClass

Javadoc recommendation: subclasses that conform to the delegation model should generally override `findClass` to provide a new bytecode source.

Minimal pattern:

```java
@Override
protected Class<?> findClass(String binaryName)
        throws ClassNotFoundException {
    byte[] bytes = obtainVerifiedClassBytes(binaryName);
    if (bytes == null) {
        throw new ClassNotFoundException(binaryName);
    }
    return defineClass(binaryName, bytes, 0, bytes.length);
}
```

This is a **snippet** placed inside a `ClassLoader` subclass, where `obtainVerifiedClassBytes` is a helper that depends on the application's repository/JAR reader. It does not compile standalone.

Advantages:

- The default `loadClass` handles `getClassLoadingLock` and `findLoadedClass`.
- Parent delegation is already included following the standard Java model.
- `resolveClass` is called properly when the protected overload is used with `resolve=true`.
- The subclass only focuses on reading bytes for the right name and calling `defineClass`.

If you override `loadClass` to switch to child-first, you must check `findLoadedClass` yourself and synchronize properly before defining. A pseudocode example of a safe structure:

```java
@Override
protected Class<?> loadClass(String name, boolean resolve)
        throws ClassNotFoundException {
    synchronized (getClassLoadingLock(name)) {
        Class<?> c = findLoadedClass(name);
        if (c == null) {
            // Implement a valid delegation/fallback policy here:
            // ensure no duplicate name is defined and protect namespaces.
            c = super.loadClass(name, false);
        }
        if (resolve) {
            resolveClass(c);
        }
        return c;
    }
}
```

This is an **illustrative snippet**, not a complete child-first template. In practice, with `super.loadClass`, parent-first still applies; achieving child-first requires fully designing your own source order, handling protected namespaces, and addressing linkage errors. Do not copy this and assume you have changed the strategy.

Another risk: if a subclass **deliberately overrides `loadClass` without synchronization**, the superclass's default locking contract **does not automatically guarantee** safety for that overridden code.

## 8. When Cross-Delegation Can Cause Deadlocks
If thread T1 holds loader A's monitor and waits for loader B, while T2 holds B and waits for A, a circular wait and deadlock occur. Per-class-name locking in parallel-capable loaders **reduces circular waits caused by loader-wide locks**, but does not prevent every dependency cycle. The lesson **Deadlocks When Multiple Loaders Cross-Delegate** provides a two-loader example, thread dumps, and ways to eliminate circular waits; here, remember not to hold `synchronized(this)` yourself around calls to another loader.

## 9. The Class-Loading Lock Is Not the Class Initialization Lock

Phases to distinguish:

| Phase | What Happens | Which Lock Is Involved? |
| --- | --- | --- |
| **Loading** | Finding/defining `Class<?>` from binary name/bytes. | The default `ClassLoader.loadClass` uses `getClassLoadingLock`. |
| **Linking** | Verification, preparation, and resolution per JVM rules. | The JVM has its own mechanism; `resolveClass` does not invoke the static initializer. |
| **Initialization** | Running `<clinit>`, including static field initializers/static blocks. | The JVM uses a per-class **initialization lock/protocol** per JVMS §5.5. |

Do not infer that when two threads call `Class.forName("demo.Widget")`, the static initializer runs only once **solely because of** `getClassLoadingLock`. The JVM has a **separate** class initialization synchronization mechanism. In particular, `Class.forName(name, false, loader)` requests loading/linking per the API, but **does not request initialization**; regular `Class.forName(name)` can trigger initialization.

Therefore:

- A class can be loaded without yet being initialized.
- A class may currently be initializing in another thread; the JVM must coordinate according to `<clinit>` rules.
- Deadlocks involving static initializers are not cured merely by registering a parallel-capable loader.
- The per-class-name monitor is not the monitor used for all `static synchronized` methods of the class.

This is why, when debugging a hang, you need to know whether threads are stuck at **loader delegation/defineClass** or **class initialization**.

## 10. Race Conditions in Custom Loaders: Mistakes to Avoid

| Flawed Design | What Can Happen | Correct Approach |
| --- | --- | --- |
| Omitting `synchronized(getClassLoadingLock(name))` when overriding `loadClass` | Two threads call `defineClass` on the same name → `LinkageError`. | Use the default implementation or lock accurately by name. |
| Checking `findLoadedClass` only outside the lock | Race between check and define. | Check and define under the same lock for that name. |
| Subclass registered as parallel-capable but sharing an unsynchronized mutable `HashMap` | Cache race/corruption bugs. | Use concurrent collections and an appropriate visibility policy. |
| Two different class names calling `definePackage` simultaneously | The package may be defined twice → `IllegalArgumentException`. | Synchronize state per package; verify metadata/sealing. |
| Using a single `InputStream`/`JarFile` with mutable operations from multiple threads without a thread-safe contract | Misread/truncated bytes or resource errors. | Separate streams, synchronize per source, or use APIs that manage concurrency. |
| Calling into another loader while holding multiple unordered locks | Circular wait/deadlock. | Design a delegation DAG or an explicit lock acquisition order. |
| `registerAsParallelCapable` in a subclass while the superclass is not registered | Registration returns false. | Register properly across every class in the hierarchy. |
| Calling `registerAsParallelCapable` too late | Registration fails because an instance has already been created. | Perform it during class initialization before the constructor. |
| Locking on a fresh `new Object()` on each load call | No coordination among threads at all. | Use a stable lock per loader/name. |
| Using resource path `demo/Widget.class` instead of binary name `demo.Widget` | Wrong lookup/definition. | Distinguish between binary names and archive paths. |

### Do Not Automatically Attribute Every LinkageError to Double-Define

`LinkageError` has many causes: loading constraint violations, incompatibility between library versions, `NoSuchMethodError`, `ClassFormatError` (a subclass of `LinkageError`), duplicate class definition, etc. Read the exception message/stack trace before concluding it is due to a race.

Running multiple threads **without seeing an exception** also does not prove a loader is thread-safe; concurrency bugs can depend on timing, I/O sources, and scheduler ordering.

## 11. Standard Patterns for Loaders with Multiple Bytecode Sources

A custom loader serving a large plugin system typically needs the following rules:

**A. Clear ownership.** A loader instance is a class and resource namespace. Do not share mutable state across multiple loader instances without reason.

**B. Override only the necessary extension point.** When the policy remains parent-first, prefer `findClass`. Avoid overriding `loadClass` just to read from a database/directory.

**C. Register as parallel-capable intentionally.** If throughput or the delegation model requires loading different names concurrently, use `registerAsParallelCapable` **along with a full thread-safety review**. For simple loaders, non-parallel may be easier to reason about and fast enough.

**D. Locks beyond the class lock are separate.** Package metadata, caches, JAR handles, and class generators must be synchronized properly according to data sharing. Do not rely on a loader-wide lock once parallel-capable is enabled.

**E. Control parent/plugin ordering.** A class with a matching name in the parent may be returned by the parent; the returned `Class<?>` has the parent as its defining loader, not the loader on which `loadClass` was called.

**F. Errors must be categorized.** `ClassNotFoundException` when the class does not exist; `IOException` when reading bytes wrapped with its cause; `LinkageError` for duplicates/incompatibility; `VerifyError` from the verifier; `ExceptionInInitializerError` at initialization is a different phase.

**G. Test both same-name and different-name loading.** Test the same name to prove there is no double-definition, test different names to observe lock contention/caches, and test parent delegation and multiple loaders with cross-reference dependencies.

**H. Do not disable safety for premature optimization.** The goal is correctness first; only afterward measure contention using thread dumps/JFR/profiling before optimizing.

## 12. Debugging Hangs During Concurrent ClassLoader Loading

When an application freezes during startup or when activating a plugin:

1. **Capture a thread dump** using an appropriate JDK tool, such as `jcmd <pid> Thread.dump_to_file -format=text dump.txt` (syntax/capabilities may vary by version), or `jstack <pid>` on supported JVMs.
2. Look at threads in `BLOCKED`/`WAITING` inside `ClassLoader.loadClass`, `getClassLoadingLock`, `findClass`, I/O, and `<clinit>`. Do not only search for the string `ClassNotFoundException`.
3. If thread A holds loader A's lock and waits for loader B, while B waits for A, draw the delegation graph and monitor owners/waiters.
4. Check `loader.isRegisteredAsParallelCapable()` and the actual hierarchy; do not assume a loader is “parallel” from its class name.
5. If two threads load the same class name, check whether `loadClass` was overridden without locking; if there is a double-definition, look for the stack at `defineClass` and the `findLoadedClass` path.
6. If different names share the same package, check for races in `definePackage`, sealing, and shared caches.
7. If a static initializer is waiting, distinguish the **JVM initialization protocol** from the loader's monitor; avoid trying to fix it incorrectly with `registerAsParallelCapable`.
8. Reproduce with a minimal test program, using `CountDownLatch`/`CyclicBarrier` to trigger calls close together, comparing `Class<?>` with `==`, and counting `findClass` calls.
9. Keep the lock graph simple and eliminate cycles; never force `Thread.stop()` to “resolve” a deadlock in production.

Results from `ThreadMXBean.findDeadlockedThreads` can help diagnose some monitor/synchronizer deadlocks, but they do not replace I/O and dependency graph analysis; a thread that does not complete might be waiting on network/disk rather than deadlocked.

## 13. Self-Check Questions

1. **For a non-parallel-capable loader, what is `getClassLoadingLock("A") == getClassLoadingLock("B")`?**  
   `true`: the method returns the loader instance itself.
2. **For a parallel-capable loader, do two different names share the same lock?**  
   No, per the implementation requirements; the lock is associated with the class name. The same name on the same loader receives the same lock.
3. **The root `ClassLoader` is parallel-capable, so is a direct subclass automatically parallel-capable?**  
   No. The subclass must register if it wants to support it.
4. **When should parallel-capable registration happen?**  
   During class initialization of the loader subclass, before any instance exists, and all ClassLoader superclasses must already be registered.
5. **If eight threads call `loader.loadClass("demo.Widget")` concurrently, is it valid to create eight `Class<?>` objects under the same defining loader?**  
   No; class identity must be reused. In the demo, all eight return a single object and `findClass` runs only once.
6. **Does a parallel-capable loader automatically make every shared `HashMap` thread-safe?**  
   No; application state must be synchronized separately.
7. **Should you override `loadClass` or `findClass` when you only want to source class bytes from a custom directory?**  
   Usually `findClass`; preserves the locking logic and parent delegation of the default `loadClass`.
8. **Does `synchronized(getClassLoadingLock(name))` guarantee that the static initializer runs only once?**  
   Not directly; the JVM has a separate initialization lock/protocol for the class.
9. **Why is non-hierarchical delegation prone to deadlocks with non-parallel loaders?**  
   Each thread can hold a loader-wide monitor and then wait for another loader's monitor in a cycle.
10. **Does registering as parallel-capable eliminate all deadlocks?**  
    No; locks for different names can still form a circular wait.
11. **Does `resolveClass` execute constructors or static blocks?**  
    No, not in the sense of initialization; it serves linking.
12. **Why shouldn't you lock on `synchronized(this)` yourself inside any parallel-capable loader?**  
    It can reintroduce a coarse lock, defeating the benefit of loading different names concurrently and increasing deadlock risk.

## 14. Authoritative References

- [Java SE 21 — ClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, `getClassLoadingLock`, `findLoadedClass`, `findClass`, `registerAsParallelCapable`, and `isRegisteredAsParallelCapable`.
- [Java SE 21 — Concurrent programming / java.util.concurrent](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/package-summary.html): `CountDownLatch`, `ExecutorService`, `Future`, synchronization.
- [JVMS §5.3 — Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3): defining vs. initiating loader and runtime type identity.
- [JVMS §5.5 — Initialization](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.5): separate class initialization synchronization/protocol.
- [JLS Chapter 12 — Execution](https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html): loading, linking, and initialization.
- [Java SE 21 — ThreadMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html): API supporting monitor deadlock diagnostics.
