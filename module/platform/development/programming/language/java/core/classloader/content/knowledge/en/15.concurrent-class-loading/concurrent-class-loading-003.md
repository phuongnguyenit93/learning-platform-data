# What Is a Parallel-Capable ClassLoader? Concurrent Class Loading and Per-Class-Name Locking in Java

## 1. Concept

A **parallel-capable class loader** is a `ClassLoader` that is **registered as capable of supporting concurrent loading of classes with different names**. When using the default `ClassLoader.loadClass(String, boolean)` implementation, its locking mechanism is narrowed from **the entire loader object** down to **each binary name being loaded**.

In short:

- **Standard loader (not parallel-capable):** two threads requesting *two different classes* through the **same loader** may have to wait for each other because they share the lock on the **ClassLoader object**.
- **Parallel-capable loader:** two threads requesting *two different class names* through the **same loader** can enter the loading path concurrently thanks to **separate per-name locks**. If it is the same class name, they are still coordinated to avoid duplicate definition.
- **Registration does not automatically make all logic thread-safe:** the loader author must still protect mutable state, caches, streams, package definitions, classpath handling, and any `loadClass` override.
- **Not “loading a single class with multiple threads”:** parallel-capable is primarily meant to allow **multiple different classes** to be loaded in parallel, while still protecting requests to load the same binary name.

This mechanism was introduced in **Java 7** to reduce deadlock situations in systems with multiple class loaders and to support safer concurrent loading.

### Lesson in the ClassLoader Module

This section belongs to the **Concurrent Loading** group. What needs to be understood is not only how to call `registerAsParallelCapable()`, but also **where the lock actually resides**, **why loader design affects deadlock**, **how to register validly**, and **when registration is still not enough**.

## 2. Why Does ClassLoader Need Locking When Loading Classes?

Suppose two threads concurrently call:

```java
// Snippet: loader is a ClassLoader managed by the application.
Class<?> first = loader.loadClass("plugin.Service");
Class<?> second = loader.loadClass("plugin.Service");
```

Without coordination, both could observe that the class is not loaded yet, read the same `plugin/Service.class` file, and both call `defineClass("plugin.Service", ...)` on a single defining loader. This can cause a **`LinkageError` due to duplicate definition**.

The default `ClassLoader.loadClass(name, resolve)` implementation uses the order:

1. `findLoadedClass(name)`: has the class already been recorded?
2. `parent.loadClass(name)` (or bootstrap if parent is `null`): query the parent loader.
3. `findClass(name)`: the current loader finds and defines it itself when the parent does not find it.
4. `resolveClass(c)` if the `resolve` parameter is `true`.

The entire default sequence is synchronized on **`getClassLoadingLock(name)`**. This is the key point of parallel-capable: **the lock object returned by this method depends on the loader's registration state**.

Do not equate `loadClass` with initialization (`<clinit>`). A loader can load or link a class without requiring the static initializer to run yet. The locks used by the JVM for class initialization are not simply the same lock returned by `getClassLoadingLock`.

## 3. How Do Non-Parallel-Capable and Parallel-Capable Differ in Their Locks?

According to the `ClassLoader.getClassLoadingLock(String)` contract:

- If **the loader is not registered as parallel-capable**, the method **returns `this`** — the current loader object.
- If **the loader is registered as parallel-capable**, the method returns **a separate lock object associated with the requested binary name**.
- On the same loader, **the same name** receives the same appropriate lock; different names can have different locks.
- When a loader is parallel-capable, passing `null` to `getClassLoadingLock` will result in a `NullPointerException` per the API contract. For valid class names, always pass a non-null binary name.

### Visualizing the Difference

```text
Not parallel-capable: a single lock L for the whole loader
----------------------------------------------------------
Thread T1: loadClass("plugin.A")
             └── holds lock L ───────────────┐
Thread T2: loadClass("plugin.B")             │
             └── needs same lock L → waits ◀─┘


Parallel-capable: per-binary-name locking
-----------------------------------------
Thread T1: loadClass("plugin.A")
             └── holds lock K_A ───▶ loads A
Thread T2: loadClass("plugin.B")
             └── holds lock K_B ───▶ loads B
             (K_A and K_B are different; can run concurrently)

Thread T3: loadClass("plugin.A")
             └── needs K_A → waits for T1 then uses loaded result
```

**Benefit:** reduces overly broad locking when multiple requests load independent classes. When a loader searches for classes in a JAR or directory, the I/O/lookup work for differently named classes has the opportunity to proceed concurrently.

**Limitation:** classes A and B may depend on each other, or the loader may have shared internal resources; part of the work may still have to be serialized. Registration does not guarantee a speedup in all cases and **does not guarantee deadlock will never occur**.

## 4. Related APIs

| API | Role | Things to Remember |
|---|---|---|
| `ClassLoader.registerAsParallelCapable()` | Registers the **loader's class** as parallel-capable | `protected static`; called from the subclass's initializer |
| `loader.isRegisteredAsParallelCapable()` | Queries whether the loader instance is registered | `public final`, since Java 9 |
| `getClassLoadingLock(String name)` | Obtains the lock used when loading the binary name | `protected`; by default returns `this` or a per-name lock |
| `loadClass(String name)` | Public entry point when requesting a class | By default calls protected `loadClass(name, false)` |
| `loadClass(String name, boolean resolve)` | Lookup algorithm: loaded → parent → findClass → resolve | By default synchronizes on the lock returned by `getClassLoadingLock` |
| `findLoadedClass(String name)` | Checks whether the name has been recorded by the JVM for the initiating loader | Avoids redefining an existing class |
| `findClass(String name)` | Hook for a custom loader to locate and define a class itself | Should override this method whenever possible |
| `defineClass(...)` | Hands bytes to the JVM to define a runtime class | Must not be called multiple times for the same name/defining loader |

`getClassLoadingLock` is a method that can be overridden by a subclass if a special locking policy is needed. However, for a simple loader, it is best to **leave the standard mechanism intact** and only override `findClass`. Overriding the lock arbitrarily can break built-in guarantees and makes correctness hard to prove across multiple threads.

## 5. Registering as Parallel-Capable
A subclass that wants parallel loading must call `registerAsParallelCapable()` from **its own** static initializer, while no instance exists yet and all loader superclasses are already registered. A return value of `false` indicates ineligibility; if the application depends on parallel loading, fail early. Registration is per **loader class**, not a per-object setting, and cannot be undone once it succeeds.
```java
static {
    if (!registerAsParallelCapable()) {
        throw new ExceptionInInitializerError("Parallel registration failed");
    }
}
```
The following `ParallelLockDemo` and `ParallelDirectoryDemo` examples use this exact rule. For multi-level hierarchies, callers, and late registration conditions, see the lesson **registerAsParallelCapable and Registration Conditions**; here, the goal is to understand the benefits and limitations of **concurrently loading multiple class names**.

## 6. Java 17+ Example 1: Inspecting the Exact Per-Name Lock

Create the file `ParallelLockDemo.java`:

```java
public final class ParallelLockDemo {
    static class PlainLoader extends ClassLoader {
        PlainLoader() {
            super(ParallelLockDemo.class.getClassLoader());
        }

        Object lockFor(String name) {
            return getClassLoadingLock(name);
        }
    }

    static class ParallelLoader extends ClassLoader {
        static {
            if (!registerAsParallelCapable()) {
                throw new ExceptionInInitializerError(
                        "Could not register ParallelLoader"
                );
            }
        }

        ParallelLoader() {
            super(ParallelLockDemo.class.getClassLoader());
        }

        Object lockFor(String name) {
            return getClassLoadingLock(name);
        }
    }

    public static void main(String[] args) {
        PlainLoader plain = new PlainLoader();
        ParallelLoader parallel = new ParallelLoader();

        System.out.println("plain registered: "
                + plain.isRegisteredAsParallelCapable());
        System.out.println("parallel registered: "
                + parallel.isRegisteredAsParallelCapable());

        System.out.println("plain A lock == B lock: "
                + (plain.lockFor("demo.A") == plain.lockFor("demo.B")));
        System.out.println("plain A lock == loader: "
                + (plain.lockFor("demo.A") == plain));

        System.out.println("parallel A lock == B lock: "
                + (parallel.lockFor("demo.A")
                   == parallel.lockFor("demo.B")));
        System.out.println("parallel A lock == A lock: "
                + (parallel.lockFor("demo.A")
                   == parallel.lockFor("demo.A")));
        System.out.println("parallel A lock == loader: "
                + (parallel.lockFor("demo.A") == parallel));
    }
}
```

Compile and run with **JDK 17+**:

```bash
javac ParallelLockDemo.java
java ParallelLockDemo
```

Stdout:

```text
plain registered: false
parallel registered: true
plain A lock == B lock: true
plain A lock == loader: true
parallel A lock == B lock: false
parallel A lock == A lock: true
parallel A lock == loader: false
```

**Explanation of each result:**

- `PlainLoader` does not call `registerAsParallelCapable`. Even though its superclass `ClassLoader` is registered, **PlainLoader itself is not registered**, so `getClassLoadingLock` returns the `plain` object for both `demo.A` and `demo.B`.
- `ParallelLoader` registers successfully in its static initializer. Each binary name gets its own lock, so the lock for `demo.A` differs from `demo.B`.
- Querying the **same name** `demo.A` twice returns the corresponding same lock, ensuring threads requesting the same class do not define it twice.
- The lock for `demo.A` in a parallel-capable loader is not the loader object, so a thread doing `synchronized(parallel)` is not using the per-name locking mechanism employed by the default implementation.

This is a **locking-contract verification example**, not a speed benchmark. It intentionally creates no threads, because it wants to demonstrate **what makes parallel loading possible** in a scheduler-independent way.

## 7. Java 17+ Example 2: Loading Two Classes Through a Parallel-Capable Loader

In the previous example, we only observed the locks. This example loads actual bytecode from a directory across two threads, preserving the default parent-first delegation and keeping `findClass` simple.

### 7.1. Prepare the Plugin Classes

In an empty working directory, create `A.java`:

```java
package plugin;

public final class A {
    public static String id() {
        return "A";
    }
}
```

Create `B.java`:

```java
package plugin;

public final class B {
    public static String id() {
        return "B";
    }
}
```

### 7.2. Create ParallelDirectoryDemo.java

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;

public final class ParallelDirectoryDemo {
    static final class DirectoryLoader extends ClassLoader {
        static {
            if (!registerAsParallelCapable()) {
                throw new ExceptionInInitializerError(
                        "DirectoryLoader registration failed"
                );
            }
        }

        private final Path root;
        private final AtomicInteger definitions = new AtomicInteger();

        DirectoryLoader(Path root, ClassLoader parent) {
            super(parent);
            this.root = root;
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            Path file = root.resolve(
                    name.replace('.', '/') + ".class"
            );

            byte[] bytes;
            try {
                bytes = Files.readAllBytes(file);
            } catch (IOException cause) {
                throw new ClassNotFoundException(name, cause);
            }

            Class<?> defined =
                    defineClass(name, bytes, 0, bytes.length);
            definitions.incrementAndGet();
            return defined;
        }

        int definitions() {
            return definitions.get();
        }
    }

    public static void main(String[] args) throws Exception {
        DirectoryLoader loader = new DirectoryLoader(
                Path.of("plugin-classes"),
                ParallelDirectoryDemo.class.getClassLoader()
        );

        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<Class<?>> left =
                    pool.submit(() -> loader.loadClass("plugin.A"));
            Future<Class<?>> right =
                    pool.submit(() -> loader.loadClass("plugin.B"));

            Class<?> a = left.get();
            Class<?> b = right.get();

            System.out.println("parallel capable: "
                    + loader.isRegisteredAsParallelCapable());
            System.out.println("A from child: "
                    + (a.getClassLoader() == loader));
            System.out.println("B from child: "
                    + (b.getClassLoader() == loader));
            System.out.println("definitions: "
                    + loader.definitions());
            System.out.println("A reused: "
                    + (loader.loadClass("plugin.A") == a));
        } finally {
            pool.shutdown();
        }
    }
}
```

### 7.3. Compile and Run

Create the output directory. On Bash:

```bash
mkdir -p plugin-classes
```

On Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force plugin-classes | Out-Null
```

Then:

```bash
javac --release 17 -d plugin-classes A.java B.java
javac --release 17 ParallelDirectoryDemo.java
java -cp . ParallelDirectoryDemo
```

Output structure:

```text
working-directory/
├── A.java
├── B.java
├── ParallelDirectoryDemo.java
├── ParallelDirectoryDemo.class
├── ParallelDirectoryDemo$DirectoryLoader.class
└── plugin-classes/
    └── plugin/
        ├── A.class
        └── B.class
```

**Do not add `plugin-classes` to `-cp`** of the host program. If the parent (application loader) can also see `plugin.A` or `plugin.B`, it may load that class first; the custom loader's `findClass` will not be called for that name, causing `definitions` not to reflect the intended example.

Stdout with the exact structure above:

```text
parallel capable: true
A from child: true
B from child: true
definitions: 2
A reused: true
```

### 7.4. Meaning and Limitations of the Example

The two `Future` tasks request **two different binary names** on the **same DirectoryLoader instance**. The loader is registered as parallel-capable and inherits the default `ClassLoader.loadClass`, so the loading path uses per-name locking.

- Each class is defined exactly once in the example.
- `AtomicInteger` makes the `definitions` counter safe when two threads may increment it concurrently.
- `findClass` only uses the immutable `root` data and a local byte array variable per call, rather than a shared, unlocked `InputStream`.
- Calling `loadClass("plugin.A")` again afterward uses the already-loaded state, returning the same `Class<?>` object.
- The actual order in which T1/T2 execute I/O may vary depending on the scheduler. **Stdout does not measure or prove that the two `Files.readAllBytes` operations actually overlapped in time.** It confirms that the loader is registered, loading succeeded, and type identity was preserved.

This example **does not run the static initializers of A/B** solely from using `loadClass`. They have no observable static initializer; if you add `static { ... }`, remember that initialization is a separate phase.

## 8. Why Must the Same Binary Name Still Be Protected?

Suppose both threads call:

```java
loader.loadClass("plugin.A");
```

With the default parallel-capable loader, both will need **the same lock dedicated to `plugin.A`**. One thread enters, checks `findLoadedClass`, and finds/defines A if needed; the other thread waits, then checks again and retrieves the already-recorded class. This prevents two paths from calling `defineClass` together for **the same loader + the same binary name**.

Diagram:

```text
Thread T1                            Thread T2
---------                            ---------
loadClass("plugin.A")                loadClass("plugin.A")
lock K_A                             waits for lock K_A
findLoadedClass → null               ...
parent not found                     ...
findClass → defineClass A            ...
unlock K_A                           acquires lock K_A
                                     findLoadedClass → A
                                     return A
```

**Parallel-capable does not remove synchronization**; it only **changes the granularity of synchronization**. This mechanism still requires a proper locking policy per class name.

If you override `loadClass` yourself and omit `findLoadedClass` and `getClassLoadingLock`, a custom loader may attempt to define the same name multiple times and hit a `LinkageError`. Registering as parallel-capable does not fix a broken `loadClass`.

## 9. Why Is ClassLoader Parallel-Capable While a Subclass Might Not Be?

A common mistake is thinking:

> “`ClassLoader` is already parallel-capable; every class with `extends ClassLoader` must also be parallel-capable.”

This is **false**. Each class in the subclass chain must be registered if that capability is desired.

Example inheritance tree:

```text
ClassLoader                          [registered]
   │
   ▼
MyBaseLoader                         [registered]
   ├── MyChildA                      [not registered]
   │       └── MyGrandchildA         [cannot register successfully
   │                                  when superclass is not registered]
   └── MyChildB                      [registered]
           └── MyGrandchildB         [must register itself if desired]
```

### Java 17+ Example: Checking Registration Failure

Create the file `RegistrationChainDemo.java`:

```java
public final class RegistrationChainDemo {
    static class LegacyBase extends ClassLoader {
        // No registerAsParallelCapable().
    }

    static class CannotRegisterChild extends LegacyBase {
        static final boolean REGISTERED =
                registerAsParallelCapable();
    }

    static class GoodBase extends ClassLoader {
        static {
            if (!registerAsParallelCapable()) {
                throw new ExceptionInInitializerError(
                        "GoodBase registration failed"
                );
            }
        }
    }

    static class GoodChild extends GoodBase {
        static {
            if (!registerAsParallelCapable()) {
                throw new ExceptionInInitializerError(
                        "GoodChild registration failed"
                );
            }
        }
    }

    public static void main(String[] args) {
        LegacyBase legacy = new LegacyBase();
        CannotRegisterChild rejected = new CannotRegisterChild();
        GoodChild accepted = new GoodChild();

        System.out.println("legacy: "
                + legacy.isRegisteredAsParallelCapable());
        System.out.println("registration attempt: "
                + CannotRegisterChild.REGISTERED);
        System.out.println("rejected child: "
                + rejected.isRegisteredAsParallelCapable());
        System.out.println("accepted child: "
                + accepted.isRegisteredAsParallelCapable());
    }
}
```

Run:

```bash
javac RegistrationChainDemo.java
java RegistrationChainDemo
```

Stdout:

```text
legacy: false
registration attempt: false
rejected child: false
accepted child: true
```

`CannotRegisterChild` fails to register because its superclass `LegacyBase` is not registered; there is no “automatic inheritance” of registration status from the grandparent `ClassLoader`. In contrast, both `GoodBase` and `GoodChild` register themselves in their own initializers, so the chain is valid.

The `if (!registerAsParallelCapable()) throw ...` check in production loaders helps detect wrong assumptions about the hierarchy early; you should not ignore a `false` return value and claim the loader supports parallel loading.

## 10. Deadlock When the Delegation Path Is Not a Tree
If two loaders can call into each other while holding loading locks, two threads can form an A → B → A wait cycle. Per-name locking reduces contention caused by **different names on the same loader**, but wait cycles between specific per-name locks can still happen. Therefore, a parallel-capable loader needs a delegation graph with terminating routes and proper lock ordering. The lesson **Deadlock When Multiple Loaders Cross-Delegate** contains a runnable experiment and the procedure for taking thread dumps; do not treat `registerAsParallelCapable` as a fix for dependency cycles.

## 11. Distinguishing Loading Deadlock from Initialization Deadlock

These are two different classes of problems:

| Scope | Lock/Synchronization | Symptoms |
|---|---|---|
| Class loading | `getClassLoadingLock(name)` and custom loader locks if any | Threads wait while calling `loadClass`/`findClass` |
| Class initialization | Initialization synchronization managed by the JVM for each runtime class/interface | Threads wait inside/through `<clinit>` or related code |
| Application locks | `synchronized`, `ReentrantLock`, `Future.get`, `Thread.join`... | Threads wait on each other due to application logic |

If thread T1 is initializing A and needs B, while thread T2 is initializing B and needs A, a deadlock can occur **even when the ClassLoader is parallel-capable**. You cannot “fix” a static initialization cycle simply by adding `registerAsParallelCapable`.

On the other hand, a same-thread initialization request cycle A → B → A can read unassigned static fields without necessarily deadlocking. To distinguish them, examine stack traces, the `<clinit>` frames, and the `loadClass` call paths of each thread.

**Do not use `ThreadMXBean.findDeadlockedThreads()` as the sole test**: that API does not guarantee detecting every internal wait cycle when the JVM coordinates class loading/initialization. Specific thread dumps and class loader information are needed.

## 12. When Overriding loadClass: Do Not Drop Locking

When only overriding `findClass`, you benefit from the default implementation's per-name locking. However, some loaders want **child-first** delegation for certain packages and therefore must override `loadClass`.

The template here is **illustrative pseudocode**, not a standalone Java class and **not** the only way to implement a custom loader:

```java
// PSEUDOCODE — needs handling for parent==null, package policies,
// loader/module constraints, and clear exceptions.
@Override
protected Class<?> loadClass(String name, boolean resolve)
        throws ClassNotFoundException {
    synchronized (getClassLoadingLock(name)) {
        Class<?> loaded = findLoadedClass(name);
        if (loaded == null) {
            if (isChildFirstNamespace(name)) {
                try {
                    loaded = findClass(name);
                } catch (ClassNotFoundException ignored) {
                    loaded = getParent().loadClass(name);
                }
            } else {
                try {
                    loaded = getParent().loadClass(name);
                } catch (ClassNotFoundException ignored) {
                    loaded = findClass(name);
                }
            }
        }
        if (resolve) {
            resolveClass(loaded);
        }
        return loaded;
    }
}
```

**Mandatory warning:** this snippet uses `getParent().loadClass`, so it does not handle a `null` parent; it lacks full namespace whitelist/blacklist or module/package checks. **Do not copy it as a production implementation**. Use it to see that overriding `loadClass` must preserve **`synchronized(getClassLoadingLock(name))` + `findLoadedClass` + single class definition** per name.

When designing child-first:
- Do not attempt child-first for `java.*` or platform classes.
- Identify which packages are shared APIs that must be defined by the parent to avoid two runtime types with the same name.
- Do not catch every `LinkageError` from the parent and pretend it was “not found” to fall back to the child.
- Check for delegation loops in systems with multiple loaders.
- Ensure two requests for the same name do not concurrently call `defineClass`.
- Do not put `synchronized(this)` around the entire `loadClass` if the goal is parallel-capable; this lock serializes all names again.

### Why Can synchronized(this) Nullify the Benefit?

```java
// ANTI-PATTERN — for illustration only:
@Override
public synchronized Class<?> loadClass(String name)
        throws ClassNotFoundException {
    return super.loadClass(name);
}
```

Even a loader registered as parallel-capable must still acquire the **monitor of the entire instance** when entering the method above; requests for different names are serialized right at the door. Do not put `synchronized` on the entire loader out of “fear of races” and then expect parallel loading to be effective.

If shared data structures must be protected, use a dedicated lock for that data or concurrent collections; avoid holding a global lock during I/O operations or delegation that may call another loader.

## 13. Thread-Safety of findClass: Registration Is Only a Promise

Successful registration means that **calls loading different classes can enter loader code concurrently**. Therefore, `findClass` must be ready for concurrency.

### Parts Prone to Race Conditions

- A mutable `HashMap<String, byte[]>` read/written from multiple threads without synchronization.
- Using **a shared InputStream or ZipInputStream** and letting threads read class entries concurrently.
- Using instance fields like `String currentClassName` or `byte[] scratchBuffer` as shared scratch storage across all loading requests.
- Two threads concurrently trying to define the same package or updating a package/certificate registry improperly.
- Updating the classpath/URL list during loading without a clear synchronization policy.
- Holding a monitor and then calling another loader, opening up a lock cycle.
- Failing to manage the closing lifecycle of a JAR/URLClassLoader while multiple threads are still loading classes from that source.

The `DirectoryLoader` example in section 7 uses an immutable `Path root`, local `byte[]`, and `AtomicInteger`. That design is small and safer than sharing a byte array without locking to save allocations.

### A Suitable Cache

```java
// Snippet inside a custom loader:
private final java.util.concurrent.ConcurrentMap<String, byte[]>
        bytesCache = new java.util.concurrent.ConcurrentHashMap<>();
```

`ConcurrentHashMap` can protect the map from races, but it **does not replace locking around class definition**. If a loader overrides `loadClass` incorrectly and two threads still call `defineClass` for the same binary name together, a thread-safe bytecode cache will not save it.

You also need to design the cache lifecycle: a cache that retains a class loader, `Class<?>`, or plugin objects longer than necessary can prevent class unloading during redeployment.

## 14. Same Name, Multiple Defining Loaders: Distinguishing from Parallelism

Two threads loading the same binary name through **two different loaders** do not necessarily produce the same runtime class:

```text
Thread T1 → Loader-A.loadClass("plugin.Service")
Thread T2 → Loader-B.loadClass("plugin.Service")

If Loader-A and Loader-B define it themselves:
  ("plugin.Service", Loader-A) ≠ ("plugin.Service", Loader-B)
```

This is a **type identity** issue, not the nature of parallel-capable loading. Per-name locks typically **belong to each loader instance**, not a single global lock shared across the entire JVM for all loaders loading the same binary name.

Conversely, a child loader may delegate to its parent and receive back the class defined by the parent; in that case, the defining loader differs from the initiating loader. When checking:

```java
Class<?> result = loader.loadClass("plugin.Service");
System.out.println(result.getClassLoader());
```

This is a **snippet**; the result of `getClassLoader()` indicates the defining loader of the runtime class (for bootstrap, usually represented as `null`). Do not infer from which loader a thread called that this loader necessarily defined the class.

## 15. Does Parallel-Capable Automatically Improve Performance?

There is no guarantee. It **opens up the possibility** rather than promising a speedup for every workload.

Effectiveness depends on:

1. **The number of different class names being requested concurrently.**
2. **The actual cost of finding and defining classes**: reading JARs over the file system/network, verifying/linking, caching.
3. **The degree of dependency between classes**: one class may require another class, leading to waiting.
4. **Thread-safety of the storage/resource loader**: locks may still exist in the Zip/JAR reader, data store, or network client.
5. **Parent delegation and module graph**: a class returned immediately by the parent may not enter the child's `findClass`.
6. **Additional lock granularity** imposed by the application; `synchronized(this)` and long-held cache locks can nullify the benefit.
7. **JVM/OS scheduling and I/O contention**: multiple threads are not necessarily faster than a single thread in an I/O-bound environment.

Do not benchmark simply by comparing two `System.currentTimeMillis()` calls in a single run. You should use multiple iterations, warm-up, valid distinct class names, and observe throughput/latency and thread dumps. A loader that has already loaded all classes beforehand often causes the benchmark to mainly measure `findLoadedClass` cache hits rather than concurrent class definition.

## 16. How to Debug Deadlocks/Races in Class Loading

### Step 1: Identify the Loader and Its Registration State

```java
// Snippet when you already have a ClassLoader loader:
System.out.println(loader.getClass().getName());
System.out.println(loader.isRegisteredAsParallelCapable());
System.out.println(loader.getParent());
```

`isRegisteredAsParallelCapable()` has existed since Java 9; the examples in this lesson target Java 17+.

### Step 2: Identify Competing Class Names

Log the binary name, thread name, and loader ID immediately **before/after** these points:

- `loadClass(name)`
- `findClass(name)`
- `defineClass(name, bytes, ...)`
- Delegation calls between loaders
- Custom locks and I/O sources

Do not log URLs with query strings containing credentials or sensitive paths in production systems.

### Step 3: Inspect Thread Dumps

On HotSpot/JDK, the corresponding tool is available:

```bash
jcmd <pid> Thread.print -l
```

`<pid>` is a **placeholder for the actual process ID**, not a literal string to enter. Look for threads waiting inside `ClassLoader.loadClass`, `getClassLoadingLock`, `findClass`, a static initializer, or plugin code. Cross-check whether two threads are holding locks on the same loader instance or on per-name locks.

### Step 4: Inspect Override Paths

If the class loader is registered as parallel-capable yet performance remains sequential:

- Is `loadClass` overridden with `synchronized` on the entire instance?
- Is `synchronized(this)`/a global lock used inside `findClass`?
- Are all threads waiting on a single `ZipFile`/cache lock?
- Is a lock acquired before calling another loader, causing a delegation cycle deadlock?
- Is class initialization/`<clinit>` waiting on another thread, making it look like a class-loading bug?

### Step 5: Reproduce and Fix the Root Cause

- Use multi-threaded tests with two groups: **multiple different names** and **the same name**.
- Verify that every name is defined **at most once per defining loader**.
- Use `CountDownLatch` or `CyclicBarrier` in tests to control start timing rather than relying on arbitrary `Thread.sleep()`.
- If there is a race due to caches/shared resources, fix the synchronization or data rather than just enabling registration.
- If there is a wait cycle caused by cross-delegating loaders, simplify the dependency graph; per-name locking only reduces one class of risk.

## 17. A Concurrency Experiment Exercise (Without Enforcing Fixed Stdout)

You can extend `DirectoryLoader` from section 7 with a counter tracking entry into `findClass` for two different names:

```java
// Snippet of a test idea, not a standalone runnable file:
CountDownLatch firstTwoEntered = new CountDownLatch(2);

@Override
protected Class<?> findClass(String name)
        throws ClassNotFoundException {
    firstTwoEntered.countDown();
    // Then the test allows both threads to proceed via another latch
    // before reading bytes and calling defineClass.
    ...
}
```

To verify concurrency:
1. Use **a single loader instance** and two threads calling `loadClass` for **two different binary names**.
2. Block both at the beginning of `findClass` on another latch; the main thread checks that both have entered.
3. Repeat with an **unregistered** loader. With the default `loadClass` path, one thread may be unable to enter `findClass` before the first thread releases the whole-loader lock.
4. Use timeouts and release latches in `finally` so the test never hangs indefinitely.
5. Do not hardcode stdout or fixed absolute wait times; schedulers and machine loads vary.

This section describes a testing methodology. Snippets with `...` are **pseudocode** only, not directly compilable Java source. The two runnable demos in sections 6 and 7 and the hierarchy example in section 9 already provide complete code, compile commands, and deterministic stdout.

## 18. Common Misconceptions

| Misconception | Reality |
|---|---|
| Extending `ClassLoader` makes it automatically parallel-capable | No; the subclass must register itself |
| Registering by calling the method in the constructor | Wrong timing; must happen before creating an instance, usually in a static initializer |
| Registering only the child class is enough | No; the entire relevant superclass chain must also be registered |
| Parallel-capable means loading a single class across multiple threads concurrently | Per-name locking still prevents duplicate definition of the same name |
| Parallel-capable removes all synchronization | No; it replaces the whole-loader lock with a per-class-name lock |
| Registration makes `findClass` automatically thread-safe | No; caches, I/O, and shared state still need protection |
| `synchronized(this)` around `loadClass` still runs in parallel | It serializes all names, reducing the benefit |
| Being parallel-capable alone prevents deadlock | Same-name cycles, initialization, and custom locks can still deadlock |
| Parallel class loading runs `<clinit>` concurrently in an uncontrolled way | Loading and initialization have separate rules |
| Two loaders loading the same name always produce the same class | No; the defining loader is part of runtime identity |
| Having an `AtomicInteger` to count classes is safe enough | No; duplicate `defineClass` calls and other state still need proper locking |
| Once a loader has loaded a class, modifying the file and calling it again returns the new version | No; `findLoadedClass` may return the old class |
| Registration automatically turns a ClassLoader into child-first | No; delegation order does not change |

## 19. Custom Loader Design Checklist for Real-World Applications

**Before implementation:**

- Determine whether you need to **load multiple different classes concurrently** or only sequentially.
- Verify that all loader superclasses support parallel-capable loading.
- Decide whether you can only override `findClass` or truly must override `loadClass`.
- Clarify the parent/shared API, plugin-specific namespaces, and loader lifecycle.

**During implementation:**

- Register in a static initializer and confirm the return value is `true`.
- Keep the default `loadClass` when possible; it already coordinates locking and caching.
- Call `defineClass` exactly once for a binary name within the same defining loader.
- Use local variables and concurrent collections for mutable shared state.
- Do not hold a whole-loader lock across I/O or delegation unless necessary.
- Preserve proper `ClassNotFoundException` semantics versus `LinkageError` when bytes are corrupted.
- Do not change parent-first implicitly; clearly document which parts are child-first, if any.

**During testing:**

- Verify `isRegisteredAsParallelCapable()`.
- Verify same name → one runtime class; different names → two properly defined classes.
- Test for races in package definition, resources, caching, and close/reload.
- Test cross-dependencies and class initialization.
- Use thread dumps/structured logs to distinguish loading locks from JVM initialization locks.

**In operations:**

- Do not close a `URLClassLoader` while other threads are still loading from it; coordinate quiescence before closing.
- Stop tasks, unregister callbacks, and restore the Thread Context ClassLoader when shutting down a plugin.
- Check whether the classloader remains reachable after redeployment; do not assume closing leads to unloading.
- Monitor performance with real workloads rather than only looking at the registered status.

## 20. Self-Check Questions

1. **What does parallel-capable ClassLoader mean?** A loader registered so that it can load different binary names concurrently through the standard implementation's per-name locking.
2. **What lock does a non-parallel loader use in the default `loadClass`?** The loader object itself (`this`).
3. **What lock does a parallel loader use?** A dedicated lock associated with the requested binary name.
4. **Can two threads requesting `plugin.A` simultaneously call `defineClass`?** Not in a proper implementation; the same name shares locking/caching to prevent duplicate definition.
5. **Which API is used to register?** `protected static ClassLoader.registerAsParallelCapable()` in the subclass's static initializer.
6. **Must superclasses also be registered?** Yes, except `Object` per the contract.
7. **Does a registered `ClassLoader` automatically register `extends ClassLoader`?** No.
8. **Which API queries whether a loader instance is registered?** `isRegisteredAsParallelCapable()` (Java 9+).
9. **Why should you override `findClass` instead of `loadClass` when you only need a new bytecode source?** It preserves the default delegation algorithm, `findLoadedClass`, locking, and `resolveClass`.
10. **What effect does `synchronized(this)` around the entire loadClass have?** It blocks different class names from running concurrently on the loader's monitor, losing the benefit of per-name locks.
11. **Does registration automatically protect a `HashMap` or shared `InputStream` in `findClass`?** No.
12. **Does parallel-capable prevent `<clinit>` deadlock?** No; class initialization is a separate synchronization mechanism.
13. **Do two different defining loaders creating classes with the same binary name produce the same runtime type?** No.
14. **What is the main reason deadlock is avoided during cross-delegation?** It reduces wait cycles caused by locking the entire loader; sensible dependency and locking design is still needed.
15. **Is benchmarking needed after registration?** Yes, if performance is the goal; registration only opens the possibility rather than guaranteeing faster execution.

## Authoritative References

- [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `registerAsParallelCapable`, `isRegisteredAsParallelCapable`, `getClassLoadingLock`, and `loadClass`; applies to all Java 17 examples in this lesson.
- [Java SE 25 — ClassLoader](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ClassLoader.html): updated contract for registration, locking, default synchronization, and loader hierarchy.
- [Oracle — Multithreaded Custom Class Loaders in Java](https://docs.oracle.com/javase/8/docs/technotes/guides/lang/cl-mt.html): guide to designing multithreaded custom class loaders, parallel-capable registration, and caveats when overriding `loadClass`.
- [Java Virtual Machine Specification — §5.3 Creation of Classes and Interfaces](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html#jvms-5.3): defining/initiating loaders and runtime class identity.
- [Java Language Specification — §§12.2 Loading, 12.3 Linking, 12.4 Initialization](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html): relationship between loading, linking, and initialization.

**Conclusion:** **Parallel-capable** is a registered capability allowing a `ClassLoader` to use **per-class-name locking** instead of locking the entire loader during default `loadClass` calls. It maintains safety for **the same binary name** while allowing **different names** to be loaded concurrently. Properly registering the superclass chain is a necessary condition; thread-safe `findClass` code, cycle-free delegation, and proper resource lifecycles are what truly make the system safe.
