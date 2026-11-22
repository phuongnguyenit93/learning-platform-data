# getClassLoadingLock and Class-Name-Based Locking in Java ClassLoader

## 1. The Problem: Multiple Threads Concurrently Requesting Class Loading

A Java application may have multiple threads concurrently calling:

~~~java
Class<?> a = loader.loadClass("demo.plugin.Alpha");
~~~

For a custom `ClassLoader`, finding and defining a class is not merely reading a `.class` file. The JVM must maintain **type identity**, **loading constraints**, the relationship with the **parent loader**, and whether a class has already been loaded. If two threads both see “there is no `demo.plugin.Alpha` yet” and then both call `defineClass`, one thread may succeed, while the other encounters a `LinkageError` because it attempts to define a duplicate name in the same loader.

However, if one thread is loading `demo.plugin.Alpha`, why must another thread wanting to load `demo.plugin.Beta` also wait? Java supports two locking approaches:

- **ClassLoader not registered as parallel-capable:** the default `loadClass` operation synchronizes on **the ClassLoader object itself**, meaning one shared lock for all class names in that loader.
- **ClassLoader registered as parallel-capable:** `getClassLoadingLock(name)` by default returns **a lock object dedicated to that class name**. Two threads requesting the **same name** obtain the same lock; **different** names have different locks.

Both mechanisms serve to protect consistency during class loading. Finer-grained locking by class name means different names **can** be processed in parallel, not that faster loading is guaranteed in every program.

**Quick takeaway:**

~~~text
Non-parallel-capable loader L:
  getClassLoadingLock("a.A") == L
  getClassLoadingLock("b.B") == L
  => class names contend for a single monitor

Parallel-capable loader L:
  getClassLoadingLock("a.A") == lock_A
  getClassLoadingLock("a.A") == lock_A
  getClassLoadingLock("b.B") == lock_B
  lock_A != lock_B
  => same name remains serialized, different names can proceed concurrently
~~~

There is no “single JVM-wide lock per class name”. Locks belong to **each ClassLoader instance**. Two different loaders can define two classes with the same binary name, yet they become two different runtime types.

## 2. What is `ClassLoader.getClassLoadingLock(String className)`?

The API was added in **Java 7**:

~~~java
protected Object getClassLoadingLock(String className)
~~~

This is a **protected instance method** of `java.lang.ClassLoader`. Its purpose is to return an object to serve as the **monitor lock** for loading the class with the binary name `className`.

According to [Java SE 21 — ClassLoader#getClassLoadingLock](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html#getClassLoadingLock(java.lang.String)):

1. If the **ClassLoader instance is registered as parallel-capable**, the method returns a dedicated object associated with the specified class name.
2. If **not parallel-capable**, the method returns **`this`**, i.e., the ClassLoader instance itself.
3. If the loader is parallel-capable and `className == null`, the method throws `NullPointerException` by contract.
4. Because this is a protected method, external code cannot arbitrarily call it on an arbitrary `ClassLoader`. A subclass can call `getClassLoadingLock` to support its own class loading logic.

The API returns a lock object; it **does not perform class loading** and **does not automatically lock the thread upon being called**. Only `synchronized(lock)` or an equivalent construct using that monitor creates a synchronized region.

### 2.1. When is per-name locking used?

The default implementation `ClassLoader.loadClass(String, boolean)` synchronizes on:

~~~java
synchronized (getClassLoadingLock(name)) {
    // check if class is already loaded;
    // delegate to parent;
    // call findClass if needed;
    // resolve if requested;
}
~~~

This is **illustrative code explaining the lock scope**, not the complete executable source code of the JDK.

Because multiple threads may ask the JVM to load the same name, the operation of **checking `findLoadedClass` + deciding `findClass`/`defineClass`** must be consistently protected. Separating the check and the define step under two unrelated locks will cause a race condition.

### 2.2. Why not just use `synchronized(this)`?

`synchronized(this)` locks the entire ClassLoader instance. It is appropriate for a **non-parallel-capable** loader, but can cause **unnecessary contention** if a loader needs to load many independent class names.

For example:

~~~text
Thread-1 wants plugin.First:
   holds monitor of Loader L
   slow file/classpath read while holding L

Thread-2 wants plugin.Second:
   must wait for monitor L, even though the class name differs

If L is parallel-capable and uses dedicated locks:
   Thread-1 holds lock_First
   Thread-2 holds lock_Second
   => can proceed concurrently with their respective find/load steps
~~~

The benefit is strictly **the ability to proceed concurrently**. They may still have to wait for each other when depending on a non-parallel-capable parent loader, sharing a common cache/JAR/resource lock, encountering loading constraints, or executing other synchronized logic.

## 3. Which loaders can use dedicated locks?
A `ClassLoader` subclass only becomes **parallel-capable** when it successfully registers via `protected static registerAsParallelCapable()`, typically called in the static initializer of the subclass itself before any instance is created. Every loader superclass in the chain (except `Object`) must also be registered. The base `ClassLoader` itself is already registered, but this status is **not automatically inherited by subclasses**.
```java
static {
    if (!registerAsParallelCapable()) {
        throw new ExceptionInInitializerError("Registration failed");
    }
}
```
Place this block inside the custom `ClassLoader`; verify at runtime using `loader.isRegisteredAsParallelCapable()`. If a custom-written superclass has not registered, the call in the child returns `false`. The next article on `registerAsParallelCapable` dives deeper into these conditions; the focus here is **which lock `getClassLoadingLock` returns** and how it coordinates for the same name.

## 4. Why must `findLoadedClass` be checked under the right lock?

The standard `loadClass` algorithm can be visualized as:

~~~text
loadClass(name, resolve)
  synchronized (getClassLoadingLock(name)):
      c = findLoadedClass(name)

      if c == null:
          try parent.loadClass(name)

      if still null:
          c = findClass(name)

      if resolve:
          resolveClass(c)

      return c
~~~

`findLoadedClass(name)` returns `Class<?>` if a class with the same binary name has already been recorded by the JVM for **this loader as an initiating loader**, not necessarily only classes directly defined by this loader via `defineClass`. When the loader has already found the class via its parent, it must also avoid attempting to define that name again.

### 4.1. When two threads request the same class

~~~text
Thread A: loadClass("pkg.Service")
  lock_Service acquired
  findLoadedClass == null
  not found in parent
  findClass -> defineClass -> Class C
  release lock_Service

Thread B: loadClass("pkg.Service")
  waits for lock_Service
  then findLoadedClass returns Class C
  does not call defineClass again
  returns the same Class C
~~~

The correct result is that **both threads receive the same `Class<?>`** from the same loader; the number of times `findClass` is actually called to define that class is typically **once** in a properly configured experiment.

### 4.2. If two threads request two different names

~~~text
Thread A: lock_Alpha => load Alpha
Thread B: lock_Beta  => load Beta
~~~

With a parallel-capable loader, **different names, different locks** allows the operations to take place concurrently. If both need the parent, read a shared cache, or have circular dependencies, waiting can still occur. There is no claim that any timing test will always yield a 2× speedup.

### 4.3. `getClassLoadingLock` does not replace cache checking

If a custom loader writes:

~~~java
synchronized (getClassLoadingLock(name)) {
    byte[] bytes = readClassBytes(name);
    return defineClass(name, bytes, 0, bytes.length);
}
~~~

then the snippet above is **incorrect**: once the second call enters the lock, it will still always call `defineClass` again if it does not check whether the class is already loaded. The snippet above is **intentionally flawed code**, and `readClassBytes` is merely a placeholder helper name, not a built-in API.

The right approach is to use the default `loadClass` — or, when overriding is truly necessary, ensure the rule of **checking `findLoadedClass` inside the same lock region**, handling delegation, calling `findClass` only when needed, and resolving appropriately.

## 5. Java 17+ Hands-On: Verifying Shared Locks and Per-Name Locks

The following experiment uses no external libraries and only requires JDK 17+. We create:

1. `SerialLoader` **not registered as parallel-capable** to show that every class name uses the loader object itself as the lock.
2. `ParallelLoader` **registered as parallel-capable** to observe a stable lock per class name.
3. Eight tasks concurrently calling `ParallelLoader.loadClass("demo.plugin.Alpha")`, proving they receive the **same `Class<?>`** and the custom `findClass` is called once.

The verification does not rely on thread scheduling order; it only compares object identity and counts `findClass` calls with an `AtomicInteger`.

### 5.1. Directory tree

~~~text
demo/
├── src/
│   ├── app/
│   │   └── LockDemo.java
│   └── plugin/
│       └── demo/
│           └── plugin/
│               └── Alpha.java
└── build/
    ├── app/
    └── plugin/
~~~

**Mandatory:** when running, `-cp` must contain only `build/app`, without `build/plugin`. If you accidentally add `build/plugin` to the system classpath, the parent may find `Alpha` first, preventing `ParallelLoader.findClass` from being called and rendering the measurement meaningless.

### 5.2. File `src/plugin/demo/plugin/Alpha.java`

~~~java
package demo.plugin;

public class Alpha {
    public String name() {
        return "alpha";
    }
}
~~~

This is the class that `ParallelLoader` will load by reading file bytes from `build/plugin`.

### 5.3. File `src/app/LockDemo.java`

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class LockDemo {
    static final String NAME = "demo.plugin.Alpha";

    static final class SerialLoader extends ClassLoader {
        Object lock(String name) {
            return getClassLoadingLock(name);
        }
    }

    static final class ParallelLoader extends ClassLoader {
        static final boolean REGISTERED = registerAsParallelCapable();
        final Path root;
        final AtomicInteger findCalls = new AtomicInteger();

        ParallelLoader(Path root) {
            super(LockDemo.class.getClassLoader());
            this.root = root;
        }

        Object lock(String name) {
            return getClassLoadingLock(name);
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            if (!NAME.equals(name)) {
                throw new ClassNotFoundException(name);
            }
            findCalls.incrementAndGet();
            try {
                byte[] bytes = Files.readAllBytes(
                        root.resolve(name.replace('.', '/') + ".class"));
                return defineClass(name, bytes, 0, bytes.length);
            } catch (IOException ex) {
                throw new ClassNotFoundException(name, ex);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        SerialLoader serial = new SerialLoader();
        ParallelLoader parallel = new ParallelLoader(Path.of("build/plugin"));

        System.out.println("serialSameLock="
                + (serial.lock(NAME) == serial.lock("demo.plugin.Beta")));
        System.out.println("serialLockIsLoader="
                + (serial.lock(NAME) == serial));
        System.out.println("parallelRegistered="
                + (ParallelLoader.REGISTERED
                        && parallel.isRegisteredAsParallelCapable()));
        System.out.println("parallelSameNameSameLock="
                + (parallel.lock(NAME) == parallel.lock(NAME)));
        System.out.println("parallelDifferentNamesDifferentLock="
                + (parallel.lock(NAME) != parallel.lock("demo.plugin.Beta")));
        System.out.println("parallelLockNotLoader="
                + (parallel.lock(NAME) != parallel));

        ExecutorService executor = Executors.newFixedThreadPool(8);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<Class<?>>> futures = new ArrayList<>();

        try {
            for (int i = 0; i < 8; i++) {
                futures.add(executor.submit(() -> {
                    start.await();
                    return parallel.loadClass(NAME);
                }));
            }
            start.countDown();

            Class<?> first = futures.get(0).get();
            boolean allSame = true;
            for (Future<Class<?>> f : futures) {
                allSame &= (f.get() == first);
            }
            System.out.println("allThreadsSameClass=" + allSame);
            System.out.println("findClassCalls=" + parallel.findCalls.get());
            System.out.println("loaderOwnsClass="
                    + (first.getClassLoader() == parallel));
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(10, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
~~~

Explanation of key parts:

- `SerialLoader` does not register parallel capability, so `getClassLoadingLock` returns **`this`** for every name, even when the class has not yet been loaded.
- `ParallelLoader.REGISTERED` is evaluated when the class is initialized, **before the instance constructor is invoked**. Because the superclass `ClassLoader` is already parallel-capable, registration succeeds.
- `lock(...)` is simply a package-private method providing read access to the protected method for the test; it **does not load a class itself**.
- `ParallelLoader.findClass` only handles `NAME`, while `loadClass` still uses the default JDK implementation with `findLoadedClass`, delegation, and per-name locking.
- `AtomicInteger` counts how many times the custom `findClass` is called for `Alpha`; not how many times the `loadClass` API is called.
- `CountDownLatch start` lets all eight tasks begin looking up the class together after being submitted to the thread pool. Because the JDK guards the `loadClass` path, only one task needs to define class `Alpha` itself; the remaining tasks receive the existing `Class<?>`.
- `Future.get()` waits for results and surfaces exceptions instead of printing out of order. `finally` ensures the executor is shut down.

### 5.4. Compile/run commands

Inside the `demo` directory on Linux/macOS:

~~~sh
mkdir -p build/plugin build/app
javac --release 17 -d build/plugin src/plugin/demo/plugin/Alpha.java
javac --release 17 -d build/app src/app/LockDemo.java
java -cp build/app LockDemo
~~~

On Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force build/plugin, build/app | Out-Null
javac --release 17 -d build/plugin src/plugin/demo/plugin/Alpha.java
javac --release 17 -d build/app src/app/LockDemo.java
java -cp build/app LockDemo
~~~

**Exact stdout verified with the JDK and Java 17 compatibility level:**

~~~text
serialSameLock=true
serialLockIsLoader=true
parallelRegistered=true
parallelSameNameSameLock=true
parallelDifferentNamesDifferentLock=true
parallelLockNotLoader=true
allThreadsSameClass=true
findClassCalls=1
loaderOwnsClass=true
~~~

### 5.5. Why does each line matter?

| Line | Evidence |
|---|---|
| `serialSameLock=true` | Unregistered loader uses **one shared lock** for two different binary names |
| `serialLockIsLoader=true` | That shared lock is the **loader object itself** |
| `parallelRegistered=true` | The `ParallelLoader` subclass type registered as parallel-capable successfully |
| `parallelSameNameSameLock=true` | Within the **same loader instance**, querying the same name twice returns the same lock object |
| `parallelDifferentNamesDifferentLock=true` | The two names `Alpha` and `Beta` have two different locks |
| `parallelLockNotLoader=true` | The per-name lock is not the entire loader instance |
| `allThreadsSameClass=true` | All eight tasks receive the same runtime definition of `Alpha` |
| `findClassCalls=1` | Only one task reaches the step of reading bytes/`defineClass` via custom `findClass` |
| `loaderOwnsClass=true` | The class was defined by `ParallelLoader`, not the parent/system loader |

**Technical significance:** the same name is protected so no duplicate class is created, while obtaining locks for different names does not force all threads to contend for one monitor. The example does not attempt to measure speed, so the result does not depend on whether the machine has many or few cores.

### 5.6. Extended experiments

**Try 1 — Without registration:** remove `REGISTERED = registerAsParallelCapable()`, then rerun on a fresh JVM. `parallel.isRegisteredAsParallelCapable()` will be `false`; the per-name lock lines are expected to change: multiple names use the same loader object. Without changing any other code, having `parallelRegistered` print `false` is correct.

**Try 2 — Two different parallel loaders:** create `ParallelLoader second = new ParallelLoader(root)`, and compare `parallel.lock(NAME)` with `second.lock(NAME)`. These are two instances, so the per-name locks **are not the same JVM-wide shared monitor**.

**Try 3 — Also loading class Beta:** create and compile `demo.plugin.Beta`, and adjust `findClass` to support both Alpha/Beta. Have two tasks load the two different names; they can proceed through separate locks concurrently; **do not use log print order or execution time to conclusively prove parallelism**.

**Try 4 — Overriding incorrectly:** override `loadClass` yourself while omitting `findLoadedClass` or omitting the lock, then fire multiple requests for the same name. You may encounter a `LinkageError` or intermittent failures. This is an experiment that should stay in a sandbox and not be done on a production loader.

## 6. Overriding `loadClass`: When Is It Needed and What Must Be Preserved?

Normally, **override only `findClass(String)`** to provide a custom byte-reading strategy. Doing so lets you leverage the default `loadClass` implementation: locking, JVM caching, parent delegation, and `resolveClass`.

If you truly need a custom strategy such as **child-first for a plugin namespace**, you may have to override `loadClass(String, boolean)`. In that case, you are responsible for ensuring:

1. Synchronizing using a lock for the **same class name**, for example `synchronized(getClassLoadingLock(name))`.
2. Calling `findLoadedClass(name)` **inside** the lock region before attempting to define the class.
3. Applying the application's delegation policy properly (parent-first, or child-first with exceptions).
4. Calling `findClass`/`defineClass` only when no matching class already exists.
5. If `resolve` is true, calling `resolveClass` in the proper place.
6. Avoiding calling `loadClass` back along paths where two names have a circular dependency and locks are held in opposite orders.
7. Complying with runtime package/security constraints and loading constraints across loaders.

Pseudocode illustrating the **parent-first** idea (not a complete runnable custom loader):

~~~java
@Override
protected Class<?> loadClass(String name, boolean resolve)
        throws ClassNotFoundException {
    synchronized (getClassLoadingLock(name)) {
        Class<?> c = findLoadedClass(name);

        if (c == null) {
            try {
                c = getParent().loadClass(name);
            } catch (ClassNotFoundException ex) {
                c = findClass(name);
            }
        }

        if (resolve) {
            resolveClass(c);
        }
        return c;
    }
}
~~~

**Important warning:** the snippet above omits handling of the `null` parent contract (bootstrap fallback) and other requirements of a real loader, so it is strictly **structural pseudocode** — **do not copy it into production**. The best practice when there is no special requirement is **not to override `loadClass`**.

### 6.1. Same name, different loaders: do they share the same lock?

No. `getClassLoadingLock("pkg.A")` on `loader1` and `loader2` are two results bound to **two different instances**. Therefore, per-name locking **does not** solve all interaction problems between class loaders:

~~~text
Loader A -> class pkg.ServiceA
Loader B -> class pkg.ServiceB

If A holds the lock for ServiceA and waits for B to load ServiceB,
and B holds the lock for ServiceB and waits for A to load ServiceA,
a circular wait/deadlock may occur depending on the delegation/call graph.
~~~

Parallel-capable registration **reduces deadlocks caused by loader-wide synchronization**, especially in non-hierarchical delegation models, but **does not guarantee that all types of deadlock disappear**.

## 7. Loader-Wide Locking vs. Per-Name Locking: Trade-Offs

| Property | Non-parallel-capable loader | Parallel-capable loader |
|---|---|---|
| `getClassLoadingLock("A")` | Returns **`this`** | Returns object bound to name `A` |
| `getClassLoadingLock("B")` | Also **`this`** | Returns object bound to name `B` |
| Two threads both loading **A** | Serialized when going through default `loadClass` | Serialized on the same `lock_A` |
| Two threads loading **A** and **B** | Contend for the loader's shared monitor | Can be processed concurrently |
| Registration requirement | No | `registerAsParallelCapable` from the subclass before creating an instance |
| Deadlock-free guarantee | **No** | **Also no** |
| Safe if overriding `loadClass` arbitrarily | **No** | **No** |
| General recommendation | Use default, override `findClass` if needed | Register properly and still prefer overriding `findClass` |

A framework can use parallel-capable loading to support multi-threaded plugin/resource loading. However, granular locking does not turn class loading into an arbitrary operation: type identity based on binary name + defining loader must still be maintained.

## 8. Common Mistakes and Misconceptions

### 8.1. “`getClassLoadingLock(name)` automatically locks the thread”

False. The method **returns an Object** to use as a monitor. The default `loadClass` uses `synchronized(getClassLoadingLock(name))`; your own code must explicitly synchronize on the lock when handling loading itself.

### 8.2. “Without parallel-capable, Java does not support multithreading”

False. Multiple threads can still **call** `loadClass` on the same loader. They will synchronize on a single shared monitor in the default implementation. Parallel-capable relates to **lock granularity**, not prohibiting other threads.

### 8.3. “Registering parallel-capable for an instance via constructor”

False. Registration applies to the **subclass calling the method**, not an object constructor. It is valid only when called before any instance of the subclass exists and when every superclass is registered.

### 8.4. “`ClassLoader` is already parallel-capable, so every subclass is automatically parallel-capable”

False. The JDK `ClassLoader` is already registered, yet custom subclasses still must call `registerAsParallelCapable` themselves. Do not infer from the superclass and skip the subclass's status.

### 8.5. “Parallel-capable allows defining the same name twice”

False. The same name must use the same lock and `findLoadedClass` to avoid repeated `defineClass` calls; otherwise the JVM may throw `LinkageError`. Creating a new runtime class for the same name may require a **different ClassLoader instance**, subject to the JVM's identity/loading constraints.

### 8.6. “With per-name locking, `loadClass` can be overridden however you want”

False. Locking is only one part: you must still check the cache, delegation, linking/resolution, package constraints, and coordination across multiple loaders.

### 8.7. “Two different class names will always load in parallel and run faster”

False. Whether threads actually run in parallel depends on the scheduler, CPU, I/O, parent loader, dependencies, and other locks. The API only enables finer-grained locking; it does not guarantee throughput or ordering.

### 8.8. “Locks are shared between two ClassLoaders if the name string is the same”

False. `getClassLoadingLock` is an instance method, and the lock map belongs to the loader. Two class loaders do not become a JVM-wide lock registry.

### 8.9. “`findLoadedClass` only finds classes directly defined by the loader”

Incomplete. It checks the JVM's record for the **initiating loader**; the class may have been defined by the parent and received by the child via delegation.

### 8.10. “If concurrent loading fails, just catch `LinkageError`”

False. Catching the error does not fix the race condition. Check that `findLoadedClass` is inside the proper critical section, along with registration, the `defineClass` call path, delegation, and how `getClassLoadingLock` is used.

## 9. Debugging Deadlocks or Duplicate Definitions

### 9.1. Signs of a duplicate definition

The log may contain:

~~~text
java.lang.LinkageError: loader ... attempted duplicate class definition for ...
~~~

This is an **example of the message shape**, not standard stdout. When investigating, record the **binary class name**, the defining/initiating loaders involved, the full stack trace, the `defineClass` path, and the threads loading the same name.

Checklist:

1. Which loader processed this name first?
2. Is `loadClass` overridden, and does it hold `getClassLoadingLock(name)`?
3. Is `findLoadedClass(name)` called **before** `findClass/defineClass` and **inside** the same lock?
4. Has the subclass actually registered as parallel-capable?
5. Are both threads going through the **same loader instance**?
6. Did the parent already load this class, or is child-first code trying to define it again?
7. Is the error caused by **loading constraints between two loaders** rather than a duplicate definition in the same loader?

### 9.2. Deadlock when multiple threads load different names

Especially with loaders whose delegation does not follow a simple parent-child tree, while holding a shared loader lock, one thread can wait on another loader that is already occupied; the other thread waits on the first loader, forming a cycle. The Java API note recommends that loaders with **non-hierarchical delegation** register as parallel-capable to reduce the risk of deadlocks caused by holding the loader lock throughout loading.

To diagnose:

- Capture a **thread dump** using an appropriate tool, such as `jcmd <pid> Thread.print` or `jstack <pid>` in supported environments.
- Look for threads in the `BLOCKED` state and monitors associated with loaders.
- Inspect the call stack for `ClassLoader.loadClass`, `findClass`, and custom delegation.
- Check for deadlocks caused by **inverted lock ordering across loaders or class names**.
- Do not just enable parallel-capable without fixing a cyclic dependency graph; registration does not eliminate all deadlocks.

Commands with `<pid>` are **syntax templates** — replace it with the PID of the actual process when using them; tools and output vary by JDK.

### 9.3. When performance degrades due to contention

Do not immediately override `loadClass` to manually use per-name locking. First:

1. Profile/sample to see whether contention is actually occurring on the loader monitor.
2. Check whether the loader is registered as parallel-capable according to `isRegisteredAsParallelCapable()`.
3. Remove I/O and expensive operations from the hot path where appropriate.
4. Check whether parent delegation and libraries in use are holding other locks.
5. Use standard `findClass` and proper registration before considering complex strategies.

## 10. Self-Check

1. What does `getClassLoadingLock(String)` return for a loader **not registered as parallel-capable**?
2. For a parallel-capable loader, do two calls with the same binary name return the same lock object? What about two different binary names?
3. Why are `getClassLoadingLock("X")` and `getClassLoadingLock("Y")` both `this` on a non-parallel-capable loader?
4. Is the per-class-name lock global across the JVM or bound to a ClassLoader instance?
5. Does `getClassLoadingLock` synchronize automatically when called, or does it only return an object?
6. In the default `loadClass`, which lock region encloses `findLoadedClass`, delegation, and `findClass`?
7. Why must `findLoadedClass` be checked when the thread already holds the lock?
8. Why should parallel-capable registration reside in a static initializer rather than after instance creation?
9. What happens if an intermediate custom superclass is not yet parallel-capable?
10. What is `isRegisteredAsParallelCapable()` used to verify?
11. If eight threads simultaneously request `Alpha`, why does the demo only call custom `findClass` once?
12. Why **can** two different class names be loaded concurrently without guaranteeing a speedup?
13. Why can merely using `synchronized(getClassLoadingLock(name))` while forgetting `findLoadedClass` still result in duplicate definition?
14. When should you override `findClass` instead of `loadClass`?
15. What can cause custom delegation between loaders to deadlock even when per-name locking is used?
16. Does `registerAsParallelCapable` allow a class with the same name to be defined twice in the same loader?
17. If `Thread A` holds the lock for name `Alpha` and `Thread B` holds the lock for name `Beta`, what dependency scenarios still force the two threads to wait for each other?
18. In a `LinkageError` stack trace, how should you distinguish a duplicate definition from a loading-constraint violation?

**Completion criteria:** run the Java 17+ program, accurately explain the nine lines of stdout, distinguish loader lock from per-name lock, properly use `registerAsParallelCapable`/`getClassLoadingLock`, keep `findLoadedClass` inside the critical section when customizing a loader, and diagnose contention/race/deadlock.

## 11. Official Documentation

- [Java SE 21 — ClassLoader#getClassLoadingLock](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html#getClassLoadingLock(java.lang.String)): non-parallel contract returns `this`, parallel returns a lock per class name.
- [Java SE 21 — ClassLoader#registerAsParallelCapable](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html#registerAsParallelCapable()): subclass registration conditions, irreversible status.
- [Java SE 21 — ClassLoader#isRegisteredAsParallelCapable](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html#isRegisteredAsParallelCapable()): checking runtime status.
- [Java SE 21 — ClassLoader#loadClass](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html#loadClass(java.lang.String,boolean)): standard algorithm, parent delegation, `findLoadedClass`, and `findClass`.
- [JVMS Java SE 21 — Chapter 5](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html): foundations of class loading, linking, identity, and JVM constraints.

This article uses APIs available since Java 7+; the Java 17 example runs standalone without Maven/Gradle or external libraries. Observe via the **object identity** of the lock and class, rather than execution timing or JDK-dependent `toString()` strings.
