# Verifying Concurrent Loading and Duplicate Class Name Handling in Java ClassLoader

## 1. Goal: Prove Behavior, Not Just Look at Diagrams

In a Java plugin system, application server, test runner, or custom `ClassLoader`, multiple threads may request to load classes at the same time. Some requests use the **same binary name**; others use **two different binary names**. At the same time, two JARs or two plugins may contain **classes with the same fully qualified name**. These situations are related, but they are **not the same problem**.

This hands-on exercise focuses on three questions that can be verified with Java 17+:

1. **What do two concurrent threads receive when calling `loadClass("demo.Alpha")` on the same loader?** With a proper implementation, they receive the **same `Class<?>`**; the loader must not define a duplicate name within the same defining loader.
2. **Can two threads loading `demo.Alpha` and `demo.Beta` on the same loader enter `findClass` at the same time?** Yes, if the loader is registered as **parallel-capable**, is not blocked by another global lock, and dependencies permit.
3. **What happens when two independent loaders both define `demo.Alpha`?** The JVM can have **two distinct runtime classes with the same binary name**, each bound to its own defining loader. Do not assume an object from one loader can be cast to the class defined by the other loader.

After reading this guide, you will build on your own:
- A program to observe **per-name locking** via `getClassLoadingLock`.
- A Java 17+ program with **two threads, CountDownLatch, ClassLoader.findClass, and real bytecode**, verifying both different-name and same-name loading.
- An experiment calling `defineClass` with a duplicate name to observe **`LinkageError`** and compare defining the same name across two loaders.

**Key takeaway:** “concurrent class loading” does not mean “two threads are allowed to create two classes with the same name in the same loader”; on the contrary, **sufficiently narrow per-name synchronization** both protects same-name loading and allows loading different names when appropriate.

## 2. Terms to Distinguish

| Term | Meaning |
|---|---|
| **Binary name** | Name used when `ClassLoader.loadClass` looks up a normal reference type, e.g., `demo.Alpha`; a nested class typically contains `$` in its binary name |
| **Initiating loader** | The loader that initiates the load request and may delegate to another loader |
| **Defining loader** | The loader that actually calls `defineClass` or equivalent to define the runtime class |
| **Runtime class identity** | For a normal class, determined by **binary name + defining ClassLoader** |
| **`findLoadedClass(name)`** | Checks whether the loader/JVM already knows a runtime class for this binary name |
| **`findClass(name)`** | Hook for a custom loader to locate bytecode and call `defineClass` when needed |
| **`defineClass(...)`** | Asks the JVM to turn valid class file bytes into a runtime class |
| **Parallel-capable loader** | A ClassLoader subclass registered to use per-class-name locking in the default loading algorithm |
| **`getClassLoadingLock(name)`** | The lock object used when loading that name |
| **Class initialization** | Runs static initializers according to JVM rules; not the same mechanism as the per-name class-loading lock |

### “Duplicate Name” Has at Least Three Meanings

**A. Two requests with the same name, same loader:**

```text
T1 → Loader-X.loadClass("demo.Alpha")
T2 → Loader-X.loadClass("demo.Alpha")
            └── expected: the same Class<?> result
```

**B. Two class files with the same name appearing across multiple classpath/JAR entries:**

```text
lib-old.jar: demo/Alpha.class
lib-new.jar: demo/Alpha.class
            └── loader/delegation/search order determines which class
```

**C. Two independent defining loaders intentionally using the same name:**

```text
Loader-X.defineClass("demo.Alpha", ...)
Loader-Y.defineClass("demo.Alpha", ...)
            └── can create two different Class<?>
```

The three cases have different diagnostic approaches. Do not lump them all together as a “duplicate class error”.

## 3. Why Is Locking Needed for `loadClass`?

A loader that defines classes itself may perform steps such as:

```text
loadClass(name)
    │
    ▼
findLoadedClass(name)
    │ class already present? ── Yes ──► return existing Class<?>
    │ No
    ▼
delegate to parent
    │ parent found it? ── Yes ──► return parent's Class<?>
    │ No
    ▼
findClass(name)
    └── read class file bytes
        └── defineClass(name, bytes, ...)
                └── new Class<?>
```

If two threads concurrently perform **“check-then-define”** without synchronization:
- Both may see `findLoadedClass(name) == null`.
- Both read the bytes.
- Both call `defineClass` for the same **binary name and defining loader**.
- The JVM must reject the duplicate definition, typically with a **`LinkageError`**.

Therefore, the condition of **checking the not-yet-loaded state and then defining the class** must be coordinated as an appropriate per-name critical section.

### The Default Loading Algorithm Already Does This

`ClassLoader.loadClass(String name, boolean resolve)` has a synchronized implementation roughly equivalent to:

```java
// PSEUDOCODE: describes the structure, not a copy of internal JDK code.
synchronized (getClassLoadingLock(name)) {
    Class<?> result = findLoadedClass(name);

    if (result == null) {
        try {
            result = parentOrBootstrapLoad(name);
        } catch (ClassNotFoundException notFound) {
            result = findClass(name);
        }
    }

    if (resolve) {
        resolveClass(result);
    }
    return result;
}
```

The snippet above only illustrates the sequence and lock; `parentOrBootstrapLoad` is not a real Java API. The safest way to build a simple loader is to **override `findClass`** and keep the standard `loadClass` to take advantage of:
- `findLoadedClass` before `defineClass`;
- parent delegation;
- appropriate per-name or whole-loader locking;
- default `resolve` handling.

**You should not override `loadClass` yourself just to read bytes from a new directory/JAR**. Just override `findClass` when parent-first is appropriate.

## 4. How Do Whole-Loader and Per-Name Locking Differ?

According to the `ClassLoader.getClassLoadingLock(String)` contract:

- If the class loader is **not registered as parallel-capable**, by default it returns **`this`**, meaning the monitor of the entire loader.
- If the class loader **is registered as parallel-capable**, it returns a lock associated with the requested **binary name**.
- For the **same loader and same name**, calls return the appropriate lock for that name.
- For two different names, a parallel-capable loader can use **two different locks**, allowing two `findClass` calls to potentially overlap in time.

### Illustration

```text
Normal loader:
    T1 loadClass("demo.Alpha") ──lock Loader-X──▶ find/define A
    T2 loadClass("demo.Beta")  ──wait for Loader-X────────▶ find B

Parallel-capable loader:
    T1 loadClass("demo.Alpha") ──lock K_Alpha──▶ find/define A
    T2 loadClass("demo.Beta")  ──lock K_Beta ──▶ find/define B

Same name on a parallel-capable loader:
    T1 loadClass("demo.Alpha") ──lock K_Alpha──▶ define A
    T2 loadClass("demo.Alpha") ──wait for K_Alpha──▶ use already loaded A
```

This is a diagram of the **locking mechanism**, not a guarantee that the scheduler will run two threads simultaneously on every machine. If there is a dependency, a shared I/O lock, or whole-loader synchronization in other code, loading can still become serialized.

## 5. Registering as Parallel-Capable Properly

A subclass that wants to use per-name locks under the default implementation needs to register in its static initializer:

```java
public final class MyLoader extends ClassLoader {
    static {
        if (!registerAsParallelCapable()) {
            throw new ExceptionInInitializerError(
                    "ClassLoader parallel registration failed");
        }
    }

    public MyLoader(ClassLoader parent) {
        super(parent);
    }
}
```

This is a valid Java class that can be saved in `MyLoader.java`. It inherits the standard `loadClass` algorithm and does not yet add custom byte-finding logic.

**Important requirements:**
- `registerAsParallelCapable()` is `protected static`; calling it during the initialization of the **loader subclass itself** is the common approach.
- Registration must be performed **before creating the first instance** of that loader class.
- Every superclass in the loader class hierarchy (except `Object`) must be registered according to the API. `ClassLoader` itself is already registered, but a **subclass is not automatically considered registered**.
- Do not ignore the returned `boolean` value; returning `false` means **registration did not succeed**.
- If you define `BaseLoader extends ClassLoader` but **BaseLoader does not register**, `ChildLoader extends BaseLoader` cannot register successfully according to the contract.
- `isRegisteredAsParallelCapable()` on a loader instance confirms the status (Java 9+).

**Important:** registration is **a declaration of capability to support concurrent loading**; it does not automatically make caches, maps, JAR readers, or `findClass` code thread-safe.

## 6. Example 1 — Printing the Lock Difference

### 6.1. Create `LockGranularityDemo.java`

```java
public final class LockGranularityDemo {
    static class Serial extends ClassLoader {
        Object lock(String name) {
            return getClassLoadingLock(name);
        }
    }

    static class Parallel extends ClassLoader {
        static {
            if (!registerAsParallelCapable()) {
                throw new ExceptionInInitializerError(
                        "registration failed");
            }
        }

        Object lock(String name) {
            return getClassLoadingLock(name);
        }
    }

    public static void main(String[] args) {
        Serial serial = new Serial();
        Parallel parallel = new Parallel();

        System.out.println("serial registered: "
                + serial.isRegisteredAsParallelCapable());
        System.out.println("serial A/B same lock: "
                + (serial.lock("demo.Alpha")
                   == serial.lock("demo.Beta")));
        System.out.println("serial lock is loader: "
                + (serial.lock("demo.Alpha") == serial));

        System.out.println("parallel registered: "
                + parallel.isRegisteredAsParallelCapable());
        System.out.println("parallel A/B same lock: "
                + (parallel.lock("demo.Alpha")
                   == parallel.lock("demo.Beta")));
        System.out.println("parallel same name same lock: "
                + (parallel.lock("demo.Alpha")
                   == parallel.lock(new String("demo.Alpha"))));
    }
}
```

Compile/run with JDK 17+:

```bash
javac --release 17 LockGranularityDemo.java
java LockGranularityDemo
```

Verified stdout:

```text
serial registered: false
serial A/B same lock: true
serial lock is loader: true
parallel registered: true
parallel A/B same lock: false
parallel same name same lock: true
```

### 6.2. Explanation

- `Serial` did not call `registerAsParallelCapable`, so the locks for Alpha and Beta are both the `serial` object.
- `Parallel` registered successfully, so the locks for Alpha and Beta are two different objects.
- `new String("demo.Alpha")` creates a **different String object**, yet the name content is still `demo.Alpha`. The same binary name reuses the corresponding lock within the same loader.
- `==` here is used to compare **lock objects**, not to compare names by reference identity.

This is a **lock** test, not yet proof that `findClass` actually runs concurrently. The next example will use valid bytecode, two threads, and latches to verify the actual loading path.

## 7. Designing a Proper Concurrency Verification

To observe a race, many flawed examples simply create two threads, then call `Thread.sleep(100)`, and read the log order. This approach is unreliable because:
- The scheduler might run one task to completion before running the other.
- A CI machine might be slower, timing out unexpectedly.
- Thread sleep does not guarantee that the operations have entered the same code section.
- The order of `System.out.println` is not equivalent to the order of entering `findClass`.
- Both classes might have already been loaded by the parent beforehand, causing the custom `findClass` not to be called.

In this guide, we use:
- `CountDownLatch(2)` to prove that **two different binary names have both entered `findClass` before any operation is released**.
- `CountDownLatch(1)` to hold the task inside `findClass` until the main thread allows it to proceed.
- Two `Future<Class<?>>` instances from `ExecutorService.newFixedThreadPool(2)`.
- `AtomicInteger` to count how many times each class goes through `findClass` in a thread-safe manner.
- A fresh loader for the **same-name** scenario, avoiding caches from the other scenario.
- An independent `RawLoader` class for **intentionally defining a duplicate** (without using `loadClass`) to observe the JVM rejection.

The timeout in the latch is a **safeguard against an indefinitely hanging test**, not a factor that determines stdout. When the machine is unusually congested, the test can fail with a timeout; instead of printing an arbitrary order, it clearly reports a verification failure.

## 8. Example 2 — Loading Two Classes with Different Names and the Same Name Using Real Threads

### 8.1. Source and Output Structure

Create the project:

```text
loader-race/
├── src/
│   └── demo/
│       ├── Alpha.java
│       └── Beta.java
├── LoadRaceDemo.java
├── plugin-classes/
└── host-classes/
```

**Do not put `plugin-classes` on the host application classpath.** If the host parent loader already finds Alpha or Beta, then the custom `findClass` will not be called; the verification loses its value.

### 8.2. File `src/demo/Alpha.java`

```java
package demo;

public final class Alpha {
    public static String id() {
        return "Alpha";
    }
}
```

### 8.3. File `src/demo/Beta.java`

```java
package demo;

public final class Beta {
    public static String id() {
        return "Beta";
    }
}
```

The two classes are independent; they do not directly reference each other, because the goal is to test per-name concurrency without accidentally creating a dependency between Alpha and Beta.

### 8.4. File `LoadRaceDemo.java` — Full Program

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public final class LoadRaceDemo {
    static class ParallelDirectoryLoader extends ClassLoader {
        static {
            if (!registerAsParallelCapable()) {
                throw new ExceptionInInitializerError(
                        "parallel registration failed");
            }
        }

        private final Path root;
        final AtomicInteger alphaFinds = new AtomicInteger();
        final AtomicInteger betaFinds = new AtomicInteger();
        volatile CountDownLatch entered;
        volatile CountDownLatch release;

        ParallelDirectoryLoader(Path root) {
            super(LoadRaceDemo.class.getClassLoader());
            this.root = root;
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            if (!name.equals("demo.Alpha")
                    && !name.equals("demo.Beta")) {
                throw new ClassNotFoundException(name);
            }

            if (name.equals("demo.Alpha")) {
                alphaFinds.incrementAndGet();
            } else {
                betaFinds.incrementAndGet();
            }

            CountDownLatch started = entered;
            CountDownLatch gate = release;
            if (started != null && gate != null) {
                started.countDown();
                try {
                    if (!gate.await(10, TimeUnit.SECONDS)) {
                        throw new ClassNotFoundException(
                                "gate timed out for " + name);
                    }
                } catch (InterruptedException error) {
                    Thread.currentThread().interrupt();
                    throw new ClassNotFoundException(
                            "interrupted: " + name, error);
                }
            }

            try {
                byte[] bytes = Files.readAllBytes(
                        root.resolve(
                                name.replace('.', '/') + ".class"));
                return defineClass(name, bytes, 0, bytes.length);
            } catch (IOException error) {
                throw new ClassNotFoundException(name, error);
            }
        }
    }

    static class RawLoader extends ClassLoader {
        RawLoader() {
            super(null);
        }

        Class<?> define(String name, byte[] data) {
            return defineClass(name, data, 0, data.length);
        }
    }

    public static void main(String[] args) throws Exception {
        Path root = Path.of("plugin-classes");

        // SCENARIO 1: two different binary names.
        ParallelDirectoryLoader different =
                new ParallelDirectoryLoader(root);
        different.entered = new CountDownLatch(2);
        different.release = new CountDownLatch(1);

        ExecutorService two = Executors.newFixedThreadPool(2);
        try {
            Future<Class<?>> alpha = two.submit(
                    () -> different.loadClass("demo.Alpha"));
            Future<Class<?>> beta = two.submit(
                    () -> different.loadClass("demo.Beta"));

            boolean bothEntered =
                    different.entered.await(10, TimeUnit.SECONDS);

            different.release.countDown();
            Class<?> a = alpha.get();
            Class<?> b = beta.get();

            System.out.println("parallel capable: "
                    + different.isRegisteredAsParallelCapable());
            System.out.println("two names entered findClass: "
                    + bothEntered);
            System.out.println("different classes: " + (a != b));
            System.out.println("same defining loader: "
                    + (a.getClassLoader() == b.getClassLoader()));
            System.out.println("find counts: "
                    + different.alphaFinds.get() + ","
                    + different.betaFinds.get());
        } finally {
            different.release.countDown();
            two.shutdownNow();
        }

        // SCENARIO 2: two requests with the same binary name.
        ParallelDirectoryLoader same =
                new ParallelDirectoryLoader(root);
        same.entered = new CountDownLatch(1);
        same.release = new CountDownLatch(1);

        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<Class<?>> first = pool.submit(
                    () -> same.loadClass("demo.Alpha"));

            if (!same.entered.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "first load did not enter findClass");
            }

            CountDownLatch secondStarted = new CountDownLatch(1);
            Future<Class<?>> second = pool.submit(() -> {
                secondStarted.countDown();
                return same.loadClass(new String("demo.Alpha"));
            });

            if (!secondStarted.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "second task did not start");
            }

            same.release.countDown();
            Class<?> c1 = first.get();
            Class<?> c2 = second.get();

            System.out.println("same name same Class: "
                    + (c1 == c2));
            System.out.println("same name findClass calls: "
                    + same.alphaFinds.get());
        } finally {
            same.release.countDown();
            pool.shutdownNow();
        }

        // SCENARIO 3: intentionally defining a duplicate on the same loader.
        byte[] bytecode = Files.readAllBytes(
                root.resolve("demo/Alpha.class"));

        RawLoader raw1 = new RawLoader();
        Class<?> r1 = raw1.define("demo.Alpha", bytecode);

        try {
            raw1.define("demo.Alpha", bytecode);
            System.out.println("duplicate unexpectedly allowed");
        } catch (LinkageError expected) {
            System.out.println("duplicate define rejected: "
                    + expected.getClass().getSimpleName());
        }

        // SCENARIO 4: same binary name, two defining loaders.
        RawLoader raw2 = new RawLoader();
        Class<?> r2 = raw2.define("demo.Alpha", bytecode);

        System.out.println("two loaders same binary name: "
                + r1.getName().equals(r2.getName()));
        System.out.println("two loaders same Class: " + (r1 == r2));
    }
}
```

**Notes on fixture design:**
- `ParallelDirectoryLoader` only allows the exact two names in the fixture, preventing the custom loader from accidentally trying to load JDK/host classes from the directory.
- `entered` and `release` are **test latches**, not mechanisms required in a production loader.
- `volatile` ensures worker threads observe the latch references configured by the main thread before submitting tasks.
- `AtomicInteger` ensures the `findClass` counter does not suffer a data race when different names are loaded concurrently.
- `RawLoader` has a `null` parent (bootstrap delegation); it intentionally exposes a `define` method to verify the duplicate error. **Do not use RawLoader as a general-purpose loader in a real application.**

### 8.5. Compile and Run on Java 17+

Inside the `loader-race` directory, create two output directories:

Bash:

```bash
mkdir -p plugin-classes host-classes
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force plugin-classes,host-classes | Out-Null
```

Compile and run:

```bash
javac --release 17 -d plugin-classes src/demo/Alpha.java src/demo/Beta.java
javac --release 17 -d host-classes LoadRaceDemo.java
java -cp host-classes LoadRaceDemo
```

`--release 17` generates Java 17 target bytecode and restricts Java APIs to that release. Because the source uses basic switch-free syntax, `ExecutorService` and `Path` can all run on Java 17+.

**Critically important condition:** only `host-classes` is included in `-cp`, **not `plugin-classes`**. If you add `plugin-classes` to the host classpath:
- the application parent loader may load Alpha/Beta directly;
- `ParallelDirectoryLoader.findClass` is not called;
- `entered.await(...)` times out because the fixture does not enter the code section being measured;
- that is a **test setup** error, not evidence that the loader does not support concurrency.

### 8.6. Verified Stdout

```text
parallel capable: true
two names entered findClass: true
different classes: true
same defining loader: true
find counts: 1,1
same name same Class: true
same name findClass calls: 1
duplicate define rejected: LinkageError
two loaders same binary name: true
two loaders same Class: false
```

The result was compiled with `javac --release 17` and run on OpenJDK 21. When running on JDK 17+, on a machine with sufficient resources and without exceeding the test timeout, the logic lines produce the results shown above. Do not measure or predict actual speed from these stdout lines.

## 9. Reading Scenario 1 Results — Two Different Names Truly Enter findClass Concurrently

First:

```java
different.entered = new CountDownLatch(2);
different.release = new CountDownLatch(1);
```

Each time `findClass` starts for a valid name:
- increments the counter;
- calls `entered.countDown()`;
- waits on `release.await(...)` before reading bytes and calling `defineClass`.

If the loader **locks the entire instance**, the first thread holds the monitor and waits inside `findClass` for `release`. The second thread is blocked **before it can enter `findClass`**, so the latch counting two arrivals will not reach 0 before release.

With a **parallel-capable loader** that has per-name locks, thread A holds the Alpha lock and thread B holds the Beta lock — different locks. Both reach `entered.countDown()` before the main thread releases `release`. Therefore:

```text
two names entered findClass: true
```

This is stronger evidence than just looking at log order: **both threads were simultaneously present inside the findClass section** (one or both waiting on release, before the main thread allowed either to complete).

The remaining lines:
- `different classes: true` because Alpha and Beta have different binary names/runtime types.
- `same defining loader: true` because both are defined by the **same `different` instance**.
- `find counts: 1,1` because each binary name requires one `findClass` call in a fresh scenario.

### Will Two Different Names Always Enter Concurrently?

No. In production there may be:
- `findClass` code using `synchronized(this)` or another global monitor.
- One thread holding a lock on a shared cache/JAR resource.
- Class A needing to load B and creating dependency-driven blocking.
- The parent loader may find the class before custom `findClass`.
- The scheduler does not let the two tasks run at the exact same instant.
- The application already loaded the classes beforehand, so `findLoadedClass` returns the result directly.
- The container or a custom `loadClass` has its own locking policy.

Therefore, the accurate statement is that **parallel-capable enables the possibility of loading different names in parallel**, not a guarantee that two operations will always overlap or speed up.

## 10. Reading Scenario 2 Results — Same Name Is Defined Only Once

Use a **fresh** `ParallelDirectoryLoader same` so that Alpha is not yet in that loader's memory.

The first thread calls:

```java
same.loadClass("demo.Alpha")
```

It enters `findClass` and then waits for `release`. The second thread starts:

```java
same.loadClass(new String("demo.Alpha"))
```

The new string has a different identity, yet the binary name is the same. The `getClassLoadingLock` algorithm is based on the **class name value**, not requiring the two `String` instances to be the same object.

According to the default algorithm:
1. Thread 1 acquires the per-name lock for Alpha.
2. `findLoadedClass` returns `null`; the parent does not have Alpha.
3. Thread 1 enters `findClass` and waits on the latch.
4. Thread 2 also wants the **Alpha** lock, so it cannot concurrently execute the “check then define” section.
5. After release, thread 1 calls `defineClass` and returns `Class<?>`.
6. Thread 2 acquires the lock, `findLoadedClass("demo.Alpha")` sees the runtime class is already loaded, and returns that class.
7. `findClass` is not called a second time.

Hence stdout:

```text
same name same Class: true
same name findClass calls: 1
```

**Why use reference equality `c1 == c2`?** Because these are two references to `Class<?>`. Comparing `c1.getName().equals(c2.getName())` only confirms the **names match**, not that the two threads received the **same runtime class object**.

**Limitation of this check:** `secondStarted.countDown()` runs before thread 2's `loadClass`, so it proves that the second task has started rather than strictly proving it was already waiting on the monitor at the moment of release. Nevertheless, the fact that both `Future` results return the same `Class<?>` and `alphaFinds=1` verifies the correctness of the outcome. You could add ThreadMXBean/thread dumps if you need to observe the exact blocked state, though the verification does not need to depend on thread scheduling details.

## 11. Reading Scenario 3 Results — Intentionally Calling Duplicate defineClass on One Loader

Unlike standard `loadClass`, the test intentionally calls the exposed method directly:

```java
Class<?> r1 = raw1.define("demo.Alpha", bytecode);
raw1.define("demo.Alpha", bytecode); // second time → LinkageError
```

`RawLoader.define` calls `defineClass` **without** going through `findLoadedClass` or the per-name load lock. The JVM does not allow one defining loader to define two separate runtime classes with the **same binary name**.

Therefore, the second attempt is rejected. On the tested JVM, the error class is simply `LinkageError`:

```text
duplicate define rejected: LinkageError
```

**Do not rely on the exact message** such as “attempted duplicate class definition”, because the stack trace text may differ across JVM versions. The essence is a **duplicate definition for the same loader and binary name**.

Do not “fix” this by swallowing `LinkageError` and returning an arbitrary class yourself. If a custom loader encounters a duplicate during concurrent loading, what needs to be fixed is:
- checking `findLoadedClass` in the right order;
- locking on the right name in `loadClass`;
- not making duplicate `defineClass` calls;
- having no race in the cache mapping name → definition;
- not overriding `loadClass` in a way that loses the default synchronization.

### When Do You Need to Call defineClass Yourself?

A custom loader's `findClass` needs `defineClass` to define bytes from a custom source. However, normally **you should not expose a public `define(name, bytes)`** that any caller can invoke without going through the load policy. RawLoader here intentionally breaks the standard flow **to demonstrate the JVM rejection**.

## 12. Reading Scenario 4 Results — Same Name Across Two Defining Loaders Is Valid

```java
RawLoader raw2 = new RawLoader();
Class<?> r2 = raw2.define("demo.Alpha", bytecode);
```

`raw1` and `raw2` are two separate loader instances. Each defines a runtime class for `demo.Alpha` from the same bytes. Result:

```text
two loaders same binary name: true
two loaders same Class: false
```

This does not contradict the rule that rejects duplicate definitions:

- **One defining loader + one binary name**: cannot define two separate class versions.
- **Two different defining loaders + same binary name**: can have two distinct runtime classes.
- Each runtime class can have its **own static fields** and its own initialization.
- An object defined by `raw1` cannot simply be cast to the `demo.Alpha` class defined by `raw2`.
- If two plugins need to communicate, place the **shared interface/API** in a common parent loader instead of redefining the interface in each child loader.

Note that two child loaders can delegate and receive the same class defined by the parent. **Two different loader objects do not by themselves prove two different class objects** if you only call parent-first `loadClass`. The demo uses separate `defineClass` calls to clearly verify defining-loader identity.

## 13. “Duplicate Class Name on the Classpath” Is a Different Problem from “Duplicate defineClass”

Suppose:

```text
lib-a.jar ── demo/util/Codec.class [version A]
lib-b.jar ── demo/util/Codec.class [version B]
```

If both are on the **application classpath of the same loader**:
- The loader typically locates the class according to its corresponding source/path lookup rules.
- One binary name is defined **once** in that loader; the two files do not automatically become two runtime classes in the same loader.
- Once a class has been loaded, changing the classpath order or overwriting the JAR on disk does not automatically replace the already existing runtime class.
- The outcome may depend on launch configuration, manifest, parent loader, and custom search order.

If the two JARs contain incompatible APIs:
- The compiler uses version A.
- The runtime loads version B.
- When the code resolves a method/field that only exists in A, it may receive `NoSuchMethodError`/`NoSuchFieldError`.
- This is a **binary compatibility/duplicate source conflict**, not a **duplicate `defineClass` within the same loader**.

To inspect:
- Print `Class.getClassLoader()` and the `CodeSource` of the **class actually defined by the JVM**.
- Use `-Xlog:class+load=info` when appropriate.
- Inspect the actual runtime classpath/module path, not just the Maven/Gradle dependency tree.
- Use `ClassLoader.getResources("demo/util/Codec.class")` as a clue for duplicate sources; the result **does not by itself prove which source was defined**.
- Check parent delegation and the classloader graph of the application server/plugin host.

**Maven/Gradle may select one version for the dependency graph**, yet the container or launcher may still supply a different JAR at runtime. Therefore, do not assume that successful dependency resolution guarantees there is no binary name collision in the running system.

## 14. When Does a “Duplicate Binary Name” Cause ClassCastException?

Suppose the service API is packaged twice:

```text
HostLoader
  └── api.Service [Class A]

PluginLoader
  ├── api.Service [Class B, same binary name]
  └── impl.Plugin [implements Class B]
```

The host receives the plugin object and wants to cast it to the host's `api.Service` (Class A). The JVM checks runtime type identity, not just `getName()`. If B and A have different defining loaders, the cast is invalid.

**Common solution:**

```text
Shared ParentLoader
   └── api.Service [a single runtime Class<?>]
          /                          \
    PluginLoader-1             PluginLoader-2
      impl.One                   impl.Two
        implements api.Service via parent
```

- Place the shared contract in the parent loader or shared module.
- Do not redundantly package the service API inside the plugin if the plugin loader redefines it.
- If child-first is needed for the implementation, whitelist `api.*` and platform APIs to use parent-first.
- Only check `serviceType == pluginInstance.getClass().getInterfaces()[i]` when you know the exact interface position; it is better to use `serviceType.isInstance(instance)` to determine assignability.
- With JPMS, also check `Class.getModule()`, readability, and exports/opens.

**Cast errors and duplicate definitions may both be loosely called “duplicate class”, yet their root causes are completely different**.

## 15. When Overriding loadClass: Preserve the Critical Section

A custom loader wanting child-first loading may override `loadClass`. In that case, merely registering `registerAsParallelCapable()` **does not automatically patch** a non-thread-safe implementation.

Guiding pattern:

```java
// PSEUDOCODE IN SUBCLASS: lacks sufficient production validation.
@Override
protected Class<?> loadClass(String name, boolean resolve)
        throws ClassNotFoundException {
    synchronized (getClassLoadingLock(name)) {
        Class<?> loaded = findLoadedClass(name);
        if (loaded == null) {
            if (isPrivatePluginNamespace(name)) {
                try {
                    loaded = findClass(name);
                } catch (ClassNotFoundException absent) {
                    loaded = getParent().loadClass(name);
                }
            } else {
                loaded = super.loadClass(name, false);
            }
        }
        if (resolve) {
            resolveClass(loaded);
        }
        return loaded;
    }
}
```

**Do not copy as production source**: `isPrivatePluginNamespace` is a placeholder, `getParent()` can be `null`, and the policy must handle Java platform classes, package/module constraints, security, and delegation according to your architecture.

Key correctness points to pay attention to:
- The same name must use the same per-name lock.
- Must check `findLoadedClass` before defining.
- Call `defineClass` only once for the same binary name/loader.
- Do not catch `LinkageError` from the parent and arbitrarily try to define another version.
- Do not hold `synchronized(this)` around the entire `loadClass` if you want different names to be able to load concurrently.
- Do not let multiple threads bypass `loadClass` to call `defineClass` directly.

If possible, **only overriding `findClass`** and keeping the default algorithm is the less error-prone choice.

## 16. Signs a Loader Is “Parallel-Capable Yet Still Loads Sequentially”

Successful registration does not guarantee increased throughput. Even if `isRegisteredAsParallelCapable() == true`, there may be:

1. Overriding `public synchronized Class<?> loadClass(String)` or using `synchronized(this)` in other code.
2. A global lock protecting a cache, zip reader, module mapping, or code generation.
3. Both class names being found by the parent, so custom `findClass` does not run.
4. Class A depending on B, waiting on the dependency even though the per-name locks differ.
5. JVM linkage/verification/class initialization creating its own wait points.
6. OS/filesystem I/O or CPU bottlenecks even though the loader logic does not block.
7. Custom `getClassLoadingLock` returning a single shared lock for all names.
8. The loader implementation having multi-layered synchronization or a non-thread-safe library.

### Why Does synchronized(this) Negate the Benefit?

```java
// Illustrative ANTI-PATTERN.
@Override
public synchronized Class<?> loadClass(String name)
        throws ClassNotFoundException {
    return super.loadClass(name);
}
```

If used in a parallel-capable loader, the monitor of the entire instance is still held for the `loadClass` call in this method. Two different names get serialized at the outer method even though `super.loadClass` uses per-name locks.

A better approach is to use narrow locks for specific mutable resources or concurrent collections, rather than placing a global monitor over the entire class lookup/I/O/delegation process.

## 17. Thread Safety in findClass: Do Not Forget Shared State

In the example, each `findClass` call:
- uses a local `String name`;
- computes a local `Path` from `root`;
- reads its own `byte[]`;
- increments counters via `AtomicInteger`;
- synchronizes on the per-name lock in the default `loadClass`.

In a real loader, you must control:
- mutable `HashMap` caches of bytes/classes;
- shared `JarFile`/`ZipInputStream`;
- package definition and certificates/sealing constraints;
- plugin classpath URLs being updated;
- bytecode transformers using mutable buffers;
- module-specific class mapping;
- logs/metrics that are unsafe when multiple threads write to them.

### A Simple Concurrent Cache

```java
// Excerpt inside a custom ClassLoader:
private final java.util.concurrent.ConcurrentMap<String, byte[]>
        bytecodeCache = new java.util.concurrent.ConcurrentHashMap<>();
```

A concurrent map avoids map races, yet **does not replace the correctness of `findLoadedClass` + per-name lock**. Two threads must still not call `defineClass` twice for the same name just because the cache holds the same bytes. Nor do `computeIfAbsent` APIs automatically make all class loading/definition operations deadlock-free; avoid recursive side effects or cross-locks inside the mapping function.

If the loader can be unloaded/reloaded, do not keep caches holding `Class<?>`/ClassLoader/instances indefinitely on a singleton host: they can keep old classloader generations reachable.

## 18. Avoiding Deadlock When Multiple ClassLoaders Cross-Delegate

A scenario:

```text
Thread T1:
   holds Loader-A lock while loading a.One
       └── calls Loader-B to load b.Two

Thread T2:
   holds Loader-B lock while loading b.Three
       └── calls Loader-A to load a.Four
```

With whole-loader locks, this can become:
- T1 holds A, waits for B.
- T2 holds B, waits for A.
- **Deadlock**.

Per-name locks reduce one cause: loading **different names** does not force contention for the entire monitor of loader A/B. However:
- Wait cycles on the **same per-name locks** can still occur.
- Custom locks/delegation cycles can still deadlock.
- Static initialization has its own locking and can cause wait cycles even with parallel-capable loaders.
- Parallel-capable does not replace the parent-first/child-first policy.

**Diagnostic conclusion:** if a thread dump shows a deadlock, you need to find the **actual wait cycle and specific locks**, rather than just turning on registration and considering the issue completely resolved.

## 19. Distinguishing Concurrent Class Loading from Concurrent Initialization

`ClassLoader.loadClass("demo.Alpha")` primarily requests that the class be loaded (and some linking depending on JVM/options); it **does not automatically run `Alpha.<clinit>`**. In contrast:

```java
// Excerpt: loader already exists in the application.
Class<?> type = Class.forName("demo.Alpha", true, loader);
```

The overload above requests **initializing the class** if not yet initialized; the JVM manages initialization synchronization according to its own rules.

If two threads concurrently make first use of a static field/method of a runtime class, the JVM does not let both run static initialization successfully like two independent instances. This **does not mean** the class loader per-name lock is the initialization lock.

When testing:
- Count `findClass` to check class loading.
- Count/observe static initialization separately, if that is what you need to measure.
- Do not infer anything about `findClass` locking from the order of `System.out.println` inside a static block.
- `Class.forName(name, false, loader)` can be used to obtain `Class<?>` without yet requesting initialization, though linking/verification may occur according to the contract.

In the case of circular static initializers, you may also observe incomplete static field values or deadlock caused by multi-threaded code; **do not equate this with `ClassCircularityError`** (a cycle in the superclass/superinterface hierarchy).

## 20. Loading Arrays, Primitives, and Nested Classes: Names Must Be Exact

In Java, `ClassLoader.loadClass` accepts a **binary name** for a normal class/interface. Use:

```text
demo.Alpha
demo.Outer$Nested
java.util.ArrayList
```

Do not pass:
- source-like `demo/Alpha.class` into `loadClass` as a binary name;
- `demo.Alpha.class` (with a `.class` suffix) as a binary name;
- `demo.Outer.Nested` if the actual runtime binary name is `demo.Outer$Nested`;
- the primitive type name `int` expecting the loader to find `int.class`.

With `Class.forName`:
- `Class.forName("int")` **does not return `int.class`** under the regular overload.
- Descriptor-style names like `[Ljava.lang.String;` are used for array classes in the appropriate overload and have their own loader/component rules.
- Arrays are not defined by a custom loader by reading a `[L...;.class` file path like a regular class.
- For named modules, `Class.forName(Module, String)` has different semantics from the loader-based overload and may return `null` when not found in the module; do not mix up the APIs when writing tests.

Those differences explain several “duplicate/not found” logs whose real cause is **an incorrect name format**, not concurrency.

## 21. Which ClassLoader to Use for Testing? Parent and TCCL

A framework may have:
- a loader that defines the framework itself;
- a parent loader providing shared APIs;
- a child loader defining plugin implementations;
- **Thread Context ClassLoader (TCCL)** used for SPI/discovery;
- a dedicated loader for a JPMS ModuleLayer.

`Thread.currentThread().getContextClassLoader()` **is not required to match the defining loader** of a running class.

Specifically:
- `Class.forName(String)` uses the caller's loader, not TCCL automatically.
- `ServiceLoader.load(S.class)` typically uses TCCL to locate providers.
- `ClassLoader.loadClass(name)` uses the receiver loader and its delegation policy.
- `type.getClassLoader()` reveals the actual defining loader of the runtime class.
- `type.getModule()` reveals the runtime module in JPMS.

When testing duplicate names, log both the **receiver loader** and the **defining loader**. Two requests entering two receiver loaders are not enough to prove different classes if both delegate to the parent.

## 22. Real-World Verification in an App Server or Plugin Host

In production you might not write `findClass` yourself, because Tomcat, OSGi-style runtimes, build/test runners, or framework loaders already manage class lookup. A sound diagnostic workflow:

1. **Determine the actual binary name** of the suspected class.
2. **Record process/thread IDs** and timestamps when the load requests occur.
3. **Record loader identity**: the `ClassLoader` object, the loader's class, and the defining loader of the resulting `Class<?>`.
4. Check `isRegisteredAsParallelCapable()` status if the API is available.
5. Inspect whether the loader code overrides `loadClass` or `findClass`, and whether there is global synchronization.
6. Check parent delegation and classpath/module-path/resources.
7. Check if the same name appears in multiple JARs: **which artifact actually supplies the bytes**.
8. If you encounter `LinkageError`, find the `defineClass` call site and the preceding check/lock path.
9. If you encounter `ClassCastException` despite matching names, examine **defining loaders** and shared API placement.
10. If you suspect a deadlock, capture thread dumps at the hang point and analyze the monitor/lock cycle.
11. If you suspect a leak/redeploy issue, check reachable loader generations, TCCL, and registries.
12. Reproduce with a different-name/same-name test in a fresh loader instead of modifying the source JAR of an already-loaded class.

### Minimal Diagnostic Probe

```java
public final class ClassOriginProbe {
    public static void print(Class<?> type) {
        System.out.println("name: " + type.getName());
        System.out.println("loader: " + type.getClassLoader());
        System.out.println("module: " + type.getModule());

        var domain = type.getProtectionDomain();
        var source = domain == null ? null : domain.getCodeSource();
        System.out.println("source: "
                + (source == null ? "<unavailable>"
                                  : source.getLocation()));
    }

    public static void main(String[] args) {
        print(ClassOriginProbe.class);
    }
}
```

Run:

```bash
javac --release 17 ClassOriginProbe.java
java ClassOriginProbe
```

Do not expect a fixed stdout for loader identity/CodeSource, because it depends on the JDK, paths, and environment. **CodeSource can be `null` or an abstract URL**; with dynamic code, transformed class bytes do not necessarily match the current on-disk artifact.

## 23. Instrumentation and JVM Logs When Races Are Hard to Reproduce

### Java 17+ class loading log

On HotSpot:

```bash
java -Xlog:class+load=info -cp host-classes LoadRaceDemo
```

The command builds on the output of the exercise in section 8. The log may show `demo.Alpha`/`demo.Beta` being loaded from a byte array or a loader-specific source. The exact log format depends on the JDK; do not treat the log lines as fixed.

### Thread dump

```bash
jcmd <pid> Thread.print -l
```

`<pid>` is a placeholder; replace it with the actual process ID. In the dump, look for threads that are:
- waiting on `ClassLoader.loadClass` or a custom synchronized block;
- executing `findClass`/`defineClass`;
- holding the loader monitor or per-name lock object;
- waiting on JAR/cache/filesystem I/O;
- inside static initialization or another loader callback.

Note that the JVM has internal synchronizations that are not necessarily reported in full by a deadlock detection tool. Cross-reference multiple thread dumps over time against the code logic instead of inferring from a single snapshot.

### Heap/classloader stats

If multiple runs/redeploys cause the classloader count to grow abnormally:

```bash
jcmd <pid> VM.classloader_stats
```

This is an auxiliary utility, not a correctness test for concurrent loading. Having a class loaded across multiple independent plugin loaders can be completely valid; the lifecycle question is whether those old loaders are still needed after unload.

## 24. Troubleshooting Errors by Symptom

| Symptom | Possible Cause | How to Check |
|---|---|---|
| Two threads with same name, `findClass` called twice | Overridden `loadClass` missing synchronization or not checking loaded state | Per-name lock, `findLoadedClass`, trace |
| `LinkageError: duplicate class definition` | Calling `defineClass` again with the same binary name in the same loader | Find/check/define order, race window |
| Two different names are still serialized | Non-parallel loader, global monitor/cache lock | `isRegisteredAsParallelCapable` and thread dump |
| Latch does not reach 0 in the demo | Parent already loaded class, wrong `-cp`, registration failure, timeout/scheduler | Parent classpath, target directory, console |
| Two loaders load the same name, yet `Class<?>` is still equal | Both delegate to a single parent defining loader | `getClassLoader` of the result |
| `ClassCastException` even though class names match | Two independent defining loaders | Compare `Class<?>` identity, shared API |
| `NoSuchMethodError` when changing classpath/JAR | Compile/runtime binary API mismatch | CodeSource, class loading log, dependency versions |
| `NoClassDefFoundError` on a dependency class | Missing dependency or another initialization failure | Root error, loader hierarchy |
| `ClassCircularityError` | Cycle in superclass/superinterface hierarchy, not just two threads | Inspect class file/type graph |
| Deadlock when loaders cross-delegate | Whole-loader locks or cycle on per-name/global locks | Thread dumps and lock graph |
| Failure only on test runner | Test JVM/loader differs from IDE/main app; different TCCL | TestRuntimeClasspath, process/loader |
| An old class is still used after replacing JAR | Loader already defined and cached the class | New loader generation, process restart |

Do not try to fix all the symptoms above by “registering as parallel-capable”. Only some relate to locking/concurrency; others stem from identity, ABI, module access, or deployment.

## 25. Making Concurrency Tests Reliable

A good verification test has **concrete observable conditions**:

### 25.1. Use a Fresh Loader

Each scenario needs a fresh loader or a new class name to avoid `findLoadedClass` returning a cache hit before the test. Once Alpha has been loaded by a loader, calling it again no longer tests finding bytes or defining the class.

### 25.2. Control Entry Points, Do Not Control the Scheduler with Sleep

`CountDownLatch`/`CyclicBarrier` create synchronization points that can be awaited, yet you need:
- meaningful timeouts and clear failure reporting;
- `finally` always releasing gates;
- not waiting for two arrivals inside a whole-loader monitor when no external thread can release them;
- not trying to measure speed from a single run.

### 25.3. Test Both Different Names and the Same Name

**Different names:** two tasks must be able to enter `findClass` when the names do not depend on each other and the policy has no global lock.

**Same name:** the results of the two futures must be the **same `Class<?>`** and the custom loader must **define only once**.

Do not test only different names: a loader might let all names run in parallel **yet be broken** because it fails to guard against duplicate definition. Do not test only the same name: a completely serial loader also prevents duplicates properly, yet loses concurrency.

### 25.4. Do Not “Prove” Things with Randomly Ordered Logs

Some log lines can interleave arbitrarily. Provide:
- boolean assertions;
- counts;
- identity comparisons;
- latches/queues recording state;
- classloader IDs;
- errors by type, without relying on exact messages.

The demo in section 8 follows this approach: stdout is determined by invariants once the test finishes, not by which thread prints first.

### 25.5. Avoid Turning Tests into Unbounded Stress Runs

If you want stress testing:
- create multiple independent loaders or many different names;
- cap thread/heap/class counts;
- run multiple iterations;
- collect failure logs, do not swallow exceptions;
- clean up executors and loaders/resource handles;
- record JDK/OS/CI config identifiers.

Do not write tests that open thousands of JARs/threads without limits just to “verify a race”; it can cause OutOfMemoryError or file descriptor exhaustion on its own.

## 26. Assertion Suggestions for Automated Tests

If using JUnit, you can verify similarly:

```java
// JUnit EXCERPT — requires the project to have the JUnit Jupiter dependency.
assertSame(classFromT1, classFromT2);
assertEquals(1, loader.alphaFinds.get());
assertSame(loader, classFromT1.getClassLoader());
```

This is an excerpt, not a standalone Java SE file. The order of assertions must be coordinated after the `Future` tasks complete; do not read counters while workers are not yet finished.

For **different names**:
- Prove that `CountDownLatch(2)` counted down to 0 while the gate was not yet released.
- Verify that `Class<?>` is defined by the right loader.
- Verify that the counter for each name equals 1.

For **same name**:
- `assertSame(c1, c2)`;
- `alphaFinds == 1`;
- no duplicate `LinkageError` occurs in the standard loading flow.

For **direct duplicate define**:
- `assertThrows(LinkageError.class, () -> raw.define(...))` after the first define succeeds.

The `assertSame`/`assertThrows` examples are JUnit 5 APIs when properly imported and configured; **the standalone runnable Java files** in sections 6 and 8 do not depend on JUnit.

## 27. Common Misconceptions

| Misconception | Reality |
|---|---|
| “Parallel-capable means two threads can define the same name twice” | No; the same name must still share the lock/loaded class |
| “Just calling `registerAsParallelCapable()` makes all loader code thread-safe” | No; shared caches/resources and overrides must be correct |
| “A subclass automatically inherits ClassLoader's registered status” | No; the subclass needs its own registration and a valid superclass chain |
| “`getClassLoadingLock` always returns the loader itself” | Only by default when non-parallel-capable |
| “Two different String objects mean two different class names” | No; the binary name content is what counts |
| “If two ClassLoaders have the same class name, Class<?> must be equal” | No; defining loader and delegation also matter |
| “Two different loader objects mean Class<?> must be different” | No; both may delegate to a parent |
| “A duplicate class across two JARs always causes a duplicate `LinkageError`” | No; the loader typically picks only one definition for the same name |
| “Calling `defineClass` directly is the same as calling `loadClass`” | No; it skips checks/delegation/locking |
| “`loadClass` always runs the static initializer” | No; initialization has its own rules |
| “Different binary names guarantee double the speed” | No; scheduler, dependencies, I/O, and other locks still apply |
| “A parallel-capable loader cannot deadlock” | No; cycles and custom locks can still cause deadlocks |
| “`findLoadedClass` is an application cache that can be cleared at will” | No; it is tied to runtime loader state |
| “Replacing a .class file on disk makes the JVM automatically reload the old definition” | No; a new loader/process is usually required |
| “Catching every LinkageError and falling back child-first will fix class collisions” | It easily hides real errors and breaks type identity |
| “Using Thread.sleep is enough to prove concurrency” | No; use synchronization primitives and check invariants |
| “A log from one thread is enough to know the actual class source” | You need the defining loader/CodeSource/logs and parent hierarchy |

## 28. Self-Check Questions

1. **How many runtime classes do two threads receive when concurrently calling `loadClass` for the same name through the same standard loader?** One shared class object after loading succeeds.
2. **What is the purpose of `findLoadedClass`?** To return an already loaded class, avoid redefinition, and preserve identity.
3. **When not parallel-capable, what does `getClassLoadingLock` return by default?** The loader instance itself (`this`).
4. **When parallel-capable, can two different names use different locks?** Yes.
5. **Should two `new String("demo.Alpha")` instances with different references but the same content use the same class loading lock?** Yes, same binary name.
6. **Why is `registerAsParallelCapable` needed in a static initializer?** To register the loader class before creating an instance, with a valid superclass chain.
7. **What is the benefit of overriding only `findClass`?** It preserves the default `loadClass` algorithm, loaded check, delegation, and locking.
8. **What is `AtomicInteger` used for in the demo?** Safely counting findClass calls when threads enter concurrently.
9. **What does CountDownLatch(2) prove in the different-name scenario?** Both `findClass` calls reached the gate before release.
10. **What does the result `same name findClass calls: 1` prove?** Two requests with the same name did not cause the loader to define/look up the class twice in the test scenario.
11. **What does calling `defineClass` directly twice with the same binary name and loader cause?** `LinkageError`.
12. **Is it valid for two independent loaders to define the same binary name?** It can be, though it creates different runtime classes.
13. **Can two classes with the same binary name but different defining loaders be cast to each other?** Not by default.
14. **Can two child loaders that both delegate to a parent receive the same Class<?>?** Yes, they can.
15. **Once a parent has loaded Alpha, is child `findClass` always called?** No, under default parent-first delegation.
16. **Why not put plugin-classes on the demo's host classpath?** To avoid having the parent define Alpha/Beta before the custom loader.
17. **How does `ClassLoader.loadClass` differ from `Class.forName(name,true,loader)` regarding initialization?** loadClass does not automatically force init; the forName overload with `true` requests init.
18. **Does loading a class concurrently mean static initialization code runs twice?** No.
19. **To check runtime duplicates, is inspecting only the Maven dependency tree enough?** No; you must inspect the actual loader and class source.
20. **If a worker test times out, should you immediately conclude the loader is broken?** No; check the classpath, parent, scheduler, latches, and resource starvation.

## 29. Official References

- [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, `findLoadedClass`, `findClass`, `defineClass`, `registerAsParallelCapable`, `getClassLoadingLock`.
- [Java SE 17 — Class](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): runtime `Class<?>`, `getClassLoader()`, `forName()`, type identity.
- [Java SE 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): synchronizing start points and waiting for signals without using `Thread.sleep`.
- [Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): submitting tasks and `Future` results.
- [Java SE 17 — LinkageError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/LinkageError.html): incompatible linking/definition errors.
- [Java Virtual Machine Specification 17 — 5 Loading, Linking, and Initializing](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): class creation, defining/initiating loader, constraints, and runtime identity.
- [Oracle — Multithreaded Custom Class Loaders](https://docs.oracle.com/javase/8/docs/technotes/guides/lang/cl-mt.html): principles of parallel-capable and multithreaded custom loaders.

**Conclusion:** A correct ClassLoader must accomplish two things **at the same time**: **guarantee a unique definition per binary name on a defining loader**, and once registered as parallel-capable, **avoid unnecessarily broad locking that prevents different names from loading concurrently**. Verify using **fresh loaders, CountDownLatch, `Class<?>` identity, `findClass` counters, and duplicate `defineClass` errors**. With JARs or plugins sharing class names, always distinguish between **duplicate source bytes**, **duplicate definition within a single loader**, and **two runtime classes with the same name across two loaders** before deciding how to handle them.
