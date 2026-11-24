# Class Loading Locks, Parallel-Capable Loaders, and Deadlock Risks

In a Java application with runtime extensibility, multiple threads can request loading classes from the same plugin or from different plugins concurrently. The JVM must guarantee a class loader never defines the same class twice, yet overly broad synchronization can serialize independent class loads. When two class loaders cross-depend on each other, holding a lock while calling into another loader can even cause a **deadlock**: each thread holds a lock the other thread is waiting for.

This lesson focuses on three directly related issues:

1. **What is a class loading lock?** `ClassLoader` locks the sequence of checking already-loaded classes, delegating, finding/defining, and linking when needed to preserve consistency.
2. **What does a parallel-capable loader change?** Requests for different class names can use different locks, while requests for the same name still coordinate safely.
3. **How do deadlocks form and how are they handled?** Especially when customizing class loaders, using mutual delegation between plugins, or mixing loader locks with application locks.

The practical goal is to thoroughly understand the contract of **ClassLoader.loadClass**, **getClassLoadingLock**, and **registerAsParallelCapable** in Java 17+, design safer plugin loaders, and diagnose incidents instead of blindly adding `synchronized`.

## 1. Why Does Class Loading Need Locking?

In the JVM, a class is identified not only by its binary name such as `app.plugins.Parser` but also by **the class loader that defined it**. Two loaders can define two classes with the same name and produce two different `Class` objects. However, a single loader must never accidentally define the same name twice because two threads raced.

Imagine two threads simultaneously requesting `demo.plugin.Task` through one loader:

~~~text
Thread T1                  Loader L                    Thread T2
    |                         |                            |
    |--- loadClass(Task) ---->|<---- loadClass(Task) -------|
    |                         |                            |
    |                Check findLoadedClass                 |
    |                Locate and define class (if needed)   |
    |                Record loaded Class, resolve if asked |
    |                         |                            |
    |<-------- same valid Class, no duplicate define ------|
~~~

If both T1 and T2 see the class as unloaded and both call `defineClass` for the same name in the same loader, a race occurs and can throw `LinkageError` for duplicate definition, alongside other inconsistencies. Locking wraps the **check–then–load/define** sequence so only one thread executes the class-creation path for that name.

Synchronization also interacts with delegating to the parent loader or looking up classes in the loader itself. A `ClassLoader` cannot simply lock around `defineClass` alone while leaving prior state checks and branching unprotected; a custom loader must preserve consistency across the entire sequence.

### Where Is the Lock in the Default Implementation?

Under Java's standard delegation mechanism, the general flow of `ClassLoader.loadClass(String, boolean)` looks conceptually like:

~~~java
// ILLUSTRATIVE CODE OF THE MECHANISM; NOT A VERBATIM JDK REPRODUCTION
protected Class<?> loadClass(String name, boolean resolve)
        throws ClassNotFoundException {
    synchronized (getClassLoadingLock(name)) {
        Class<?> c = findLoadedClass(name);
        if (c == null) {
            try {
                c = getParent() != null
                        ? getParent().loadClass(name)
                        : findBootstrapClassOrNullIllustration(name);
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

The snippet above **only illustrates the idea** and cannot compile directly because `findBootstrapClassOrNullIllustration` is a placeholder name representing the bootstrap lookup step. Do not copy this snippet as a production override. The actual `ClassLoader` path includes JDK-specific bootstrap handling and exception details; the essential points are **`synchronized(getClassLoadingLock(name))`**, **`findLoadedClass`**, delegating to the parent, and then **`findClass`** when appropriate.

A custom loader normally only needs to **override `findClass(String)`** to read bytecode from its own source. Inheriting the default `loadClass` preserves parent-first rules and JDK-managed locking. Override `loadClass` only when you genuinely need a different delegation policy and have carefully verified concurrency interactions.

## 2. Locks of Normal Loaders vs. Parallel-Capable Loaders

The protected method **getClassLoadingLock(String className)** is where `ClassLoader` selects the lock object used for loading a class name.

- **Non-parallel-capable loader:** every class name returns **the loader instance itself** (`this`). That means T1 loading A blocks T2 loading B through that loader, even when A and B are independent.
- **Parallel-capable loader:** the loader maintains a distinct lock object for **each class name**. T1 loading A and T2 loading B can proceed concurrently; if both load A, they still share A's lock.
- Different class names do not mean all work runs in parallel: both threads may still wait on the parent, read from a shared JAR store, hit cache locks, hit application locks, or depend on one another.

The table below distinguishes the mechanisms:

| Condition | Non-parallel-capable loader | Parallel-capable loader |
| --- | --- | --- |
| Two threads load **the same name A** on the same loader | Same `this` lock | Same lock dedicated to A |
| Two threads load **A and B** on the same loader | Still the same `this` lock | Two different per-name locks |
| Loading A via loader L1, B via loader L2 | Each loader has its own lock object | Locks are scoped per loader and name |
| Delegation cycle L1 → L2 → L1 | Risk of deadlock | **Still at risk**, depending on names/locks and ordering |
| Safety of custom caches/URLs/JARs | Must be ensured by author | **Still must be ensured by author** |
| Static class initialization | Separate JVM mechanism | Separate JVM mechanism |

With an ordinary loader, a `synchronized` method like `loadClass` synchronizes on `this`, creating a loader-wide lock. With parallel-capable, the vital contract is **holding the lock from `getClassLoadingLock(name)`**, without accidentally wrapping the operation in a shared outer lock.

### Why Not Remove Locking Entirely?

Parallel-capable **does not** mean multiple threads are free to define the same name at will. Per-name locks still coordinate `findLoadedClass`, delegation, and `findClass`. If a custom `loadClass` drops locking or calls `defineClass` competitively, registering as parallel-capable will not automatically fix races or `LinkageError`.

In other words, parallel-capable is **a change in synchronization granularity**: from one lock per loader to multiple per-name locks. It does not waive synchronization responsibilities, replace the class-loading contract, or magically resolve plugin dependency structures.

## 3. Registering as Parallel-Capable Properly

`ClassLoader` provides the protected static method **registerAsParallelCapable()**. A custom loader class that wants parallel support must invoke this method inside **its own static initializer**. Registration must happen before the class is used to construct instances in its normal lifecycle.

~~~java
public final class PluginClassLoader extends ClassLoader {
    static {
        if (!registerAsParallelCapable()) {
            throw new ExceptionInInitializerError(
                    "Failed to register parallel-capable class loader");
        }
    }

    public PluginClassLoader(ClassLoader parent) {
        super(parent);
    }

    // Override findClass when using a custom bytecode source.
    // Here we inherit default loadClass to preserve parent-first and JDK locking.
}
~~~

**This is a loader structure example** that compiles if saved as `PluginClassLoader.java`; it does not yet add custom bytecode lookup. Registration applies to **the specific `ClassLoader` class**, not as a JVM-wide flag for all instances or all subclasses.

A crucial requirement is that **the entire relevant superclass chain must already be registered as parallel-capable**. If an intermediate loader superclass you wrote did not register, a subclass cannot simply call `registerAsParallelCapable()` to bypass that limitation. In multi-layer plugin loader hierarchies, check intermediate base classes rather than looking only at the leaf subclass.

### Cases to Avoid

~~~java
// CODE ILLUSTRATING A DESIGN MISTAKE, DO NOT USE IN PRODUCTION
public final class SlowPluginClassLoader extends ClassLoader {
    static {
        registerAsParallelCapable();
    }

    @Override
    protected synchronized Class<?> loadClass(String name, boolean resolve)
            throws ClassNotFoundException {
        return super.loadClass(name, resolve);
    }
}
~~~

Even though the class attempted to register, the **`synchronized` keyword on the overridden method locks all of `this`**. Two requests to load A and B will still enter the method one at a time. Calling `super.loadClass` inside does not remove the outer lock. Other common mistakes include wrapping `loadClass` in `synchronized(this)` or sharing a single static/global lock across all plugins.

Another mistake is adding `registerAsParallelCapable()` yet writing a custom `loadClass` that omits `synchronized(getClassLoadingLock(name))`. Registration does not automatically make custom code safe; the class loader must apply the proper locking in its own loading path.

**Practical priority:** if your sole goal is loading bytecode from a different source, override `findClass` and inherit `loadClass`. Only replace delegation when there is a clear requirement for plugin isolation or namespaces.

## 4. Runnable Java 17 Example: Checking Per-Class-Name Locks

This example runs standalone without loading malicious code or trying to cause a deadlock. It uses **getClassLoadingLock** to directly observe the difference in **lock object identity** returned by the JVM; because it compares references only, there is no thread-scheduling nondeterminism.

Create file **ClassLoadingLockDemo.java**:

~~~java
public class ClassLoadingLockDemo {
    public static void main(String[] args) {
        inspect("Serial", new SerialLoader());
        inspect("Parallel", new ParallelLoader());
    }

    private static void inspect(String label, LockProbe probe) {
        Object a1 = probe.lock("demo.A");
        Object a2 = probe.lock("demo.A");
        Object b = probe.lock("demo.B");

        System.out.println(label
                + ": same-name=" + (a1 == a2)
                + ", different-names-share-lock=" + (a1 == b));
    }

    private interface LockProbe {
        Object lock(String name);
    }

    private static final class SerialLoader extends ClassLoader
            implements LockProbe {
        SerialLoader() {
            super(ClassLoadingLockDemo.class.getClassLoader());
        }

        @Override
        public Object lock(String name) {
            return getClassLoadingLock(name);
        }
    }

    private static final class ParallelLoader extends ClassLoader
            implements LockProbe {
        static {
            if (!registerAsParallelCapable()) {
                throw new ExceptionInInitializerError(
                        "Parallel registration failed");
            }
        }

        ParallelLoader() {
            super(ClassLoadingLockDemo.class.getClassLoader());
        }

        @Override
        public Object lock(String name) {
            return getClassLoadingLock(name);
        }
    }
}
~~~

Save with UTF-8 encoding, open a terminal in the file's directory, and run with **JDK 17 or newer**:

~~~bash
javac -encoding UTF-8 ClassLoadingLockDemo.java
java ClassLoadingLockDemo
~~~

Deterministic output:

~~~text
Serial: same-name=true, different-names-share-lock=true
Parallel: same-name=true, different-names-share-lock=false
~~~

**Explanation of each result:**

1. For `SerialLoader` (unregistered), `getClassLoadingLock("demo.A")` and `getClassLoadingLock("demo.B")` both return `this`, so both same-name and different-name comparisons are `true`.
2. For `ParallelLoader`, registration occurred in the static initializer. The name `demo.A` maps consistently to one lock; two queries for A return the same reference, whereas `demo.B` gets a different lock.
3. These two classes are direct subclasses of `ClassLoader`, so `SerialLoader` does **not** inherit parallel-capable status from its parent class; each subclass must register itself. The JDK's base `ClassLoader` already supports the parallel-capable contract.
4. The example measures **lock identity**, not speed. It does not prove I/O or parent loaders can actually load two classes twice as fast. Those aspects must be benchmarked or concurrency-tested separately.

In a real loader class, the observed locks are the exact monitors the standard `loadClass` implementation uses to synchronize request handling.

## 5. How Does a Deadlock Between Two Class Loaders Happen?

A classic deadlock involves two separate loaders **L_A** and **L_B**, both using loader-wide locks. Suppose `L_A` needs to ask `L_B` for class B, while `L_B` needs to ask `L_A` for class A. Two threads run concurrently:

~~~text
Thread T1                                  Thread T2
---------                                  ---------
Holds lock(L_A) loading A                  Holds lock(L_B) loading B
    |                                            |
    |  Calls L_B.loadClass(B)                    |  Calls L_A.loadClass(A)
    v                                            v
Waits for lock(L_B) <----------------------> Waits for lock(L_A)
    |                                            |
Cannot release lock(L_A)                   Cannot release lock(L_B)
                     DEADLOCK
~~~

Both threads wait on a lock held by the other. Neither thread can finish its current load call to release its own lock. This is a **circular wait**; increasing thread counts, tweaking HTTP request timeouts, or adding more `synchronized` blocks usually fails to address the root cause.

In a plugin system, causes can include:

- Plugin A uses class loader A to load a class and falls back to plugin B's loader.
- Plugin B likewise falls back to loader A to resolve a dependency.
- Two load calls run concurrently while the loaders hold their locks across delegation.
- Or custom plugin code holds its own monitor around loading, then invokes another loader, forming a similar wait cycle.

**Scope note:** the diagram above shows a loader-wide locking model. With parallel-capable, `L_A` and `L_B` can hold **per-class-name** locks; this specific deadlock scenario can shrink or disappear if the two threads do not request colliding names and no extra locks are held. However, a wait cycle can still occur if both sides need the same per-name locks, wait on dependent loads, hold plugin monitors, or run class initialization. You cannot conclude "registered parallel-capable, therefore deadlocks are impossible."

### Why Does Cross-Delegation Easily Create Cycles?

Default delegation normally flows from child loader to parent loader along a directed relationship without cycles. When designing custom plugin loaders, implementers sometimes add logic like:

~~~text
Plugin A loader
   -> if class not found, ask Plugin B loader
   -> Plugin B loader asks Plugin A loader back
~~~

Even with a single thread, a delegation loop lacking termination conditions can lead to infinite recursion/`StackOverflowError` or class-loading failures depending on the situation. With multiple threads and loaders holding different locks, it can turn into a deadlock. Both symptoms share one architectural root cause: **a class resolution path without a consistent dependency direction**.

The sustainable solution is not trying every loader until something succeeds; clearly define which loader owns each namespace, which API groups the parent manages, and which plugin dependencies are permitted.

## 6. What Parallel-Capable Helps With, and What Can Still Block?

Suppose loader L concurrently handles requests to load two independent classes `demo.plugin.JsonCodec` and `demo.plugin.XmlCodec`.

**Non-parallel-capable loader:**

~~~text
T1: acquire lock(L) ---- load JsonCodec ---- release
T2:                      wait lock(L)        ---- load XmlCodec ----
~~~

**Parallel-capable loader:**

~~~text
T1: acquire lock(L, JsonCodec) ---- load JsonCodec ---- release
T2: acquire lock(L, XmlCodec)  ---- load XmlCodec  ---- release
~~~

This diagram shows **concurrency potential**, not a speed promise or exact JVM timeline. When both class names need the parent loader, read a shared JAR, or touch a locked cache, shared wait points still exist.

For two calls with **the same name**, even in a parallel-capable loader, both use the same lock for that name. This protects `findLoadedClass`/`defineClass`. A loader cannot sacrifice the "define once" invariant merely to increase concurrency.

### Other Locks Do Not Disappear

| Source of waiting | Why doesn't parallel-capable solve it automatically? |
| --- | --- |
| Non-parallel-capable parent loader | The parent still locks its entire instance while resolving classes through it |
| Custom caches or bytecode stores | If the cache uses `synchronized`/a global lock, calls still serialize |
| Locks on plugin objects or registries | Monitors outside `getClassLoadingLock` are unchanged |
| Cyclic cross-delegation protocols | A dependency cycle can still cause mutual waiting |
| Static class initialization | The JVM manages class-initialization synchronization via a separate mechanism |
| Slow I/O or network tasks | Can lengthen lock hold times regardless of lock granularity |
| Loading the same class name | Intentionally still coordinates using the same lock |

This matters especially with per-tenant loaders, per-plugin loaders, or reload mechanisms. Avoid wrapping all plugins in one global lock "to be safe," as it negates concurrency benefits and widens potential wait cycles across plugins.

## 7. Distinguishing Loading, Linking, and Initialization

A hang during plugin startup may come from **a class loader lock**, yet it can also come from **static class initialization**; pinpoint which one it is.

- **Loading:** finding bytecode and creating the `Class` object bound to a defining loader; `ClassLoader.loadClass` is the familiar entry point.
- **Linking:** verifying, preparing, and resolving references as needed. `resolveClass` can request linking an already-loaded class, not initializing it.
- **Initialization:** running static field initializers and static initialization blocks when triggered—e.g. by `new`, calling a non-constant static method per JVM semantics, or `Class.forName(name, true, loader)`.

`ClassLoader.loadClass("demo.Plugin")` normally **does not automatically run `demo.Plugin`'s static initializer**. In contrast, `Class.forName("demo.Plugin", true, loader)` requests initialization. If class A and class B have cross-dependent static initializers, two threads can wait on each other at the JVM's internal initialization lock, even if all loaders are parallel-capable.

~~~text
T1: initializing class A -> inside <clinit> needs class B
T2: initializing class B -> inside <clinit> needs class A
T1 waits for B to initialize; T2 waits for A to initialize -> possible deadlock
~~~

Do not see `ClassLoader` in a stack trace and automatically assume the bug is in `getClassLoadingLock`. Inspect whether the thread is **BLOCKED waiting on a loader monitor**, waiting on class initialization, or simply reading a JAR/waiting on I/O.

Another common mistake is doing heavy work or activating plugins inside a loader class's static initializer: it is both hard to diagnose and risks re-entering class loading while components are not yet ready. A custom loader's static initializer should perform only minimal, reliable registration/setup.

## 8. Safer Ways to Implement a Custom Class Loader

### 8.1. Keep the Default Path When Possible

If the host only needs to load bytecode from a plugin directory, JAR, or private store, prefer **overriding `findClass`** or using an existing built-in loader. Do not rewrite all of `loadClass` merely to read from an extra class source: the default path already handles caching, delegation, and synchronization.

Illustrative API skeleton (not a standalone program, because `ClassBytesRepository` must be implemented by the application):

~~~java
final class RepositoryClassLoader extends ClassLoader {
    static {
        if (!registerAsParallelCapable()) {
            throw new ExceptionInInitializerError("Registration failed");
        }
    }

    private final ClassBytesRepository repository;

    RepositoryClassLoader(ClassLoader parent, ClassBytesRepository repository) {
        super(parent);
        this.repository = repository;
    }

    @Override
    protected Class<?> findClass(String name) throws ClassNotFoundException {
        byte[] bytes = repository.find(name);
        if (bytes == null) {
            throw new ClassNotFoundException(name);
        }
        return defineClass(name, bytes, 0, bytes.length);
    }
}
~~~

The skeleton does not define `ClassBytesRepository`, does not check code source/signing/package sealing, and does not cover bytecode trust; it **only shows the override point**. In production, the repository must behave thread-safely when `findClass` runs concurrently for different names, validate bytecode, and package properly per loader rules.

### 8.2. If You Must Override loadClass, Use Per-Name Locks and Explicit Rules

A child-first loader for plugin-private namespaces may need to override `loadClass`. In that case:

1. Wrap `findLoadedClass`/delegation/`findClass` and optional resolution in **`synchronized(getClassLoadingLock(name))`**.
2. Check **`findLoadedClass(name)`** before attempting to define the class.
3. Explicitly specify which namespaces are **parent-first** (`java.*`, `javax.*`, `jakarta.*`, host APIs, shared SPI interfaces) and which belong to the plugin; never attempt to define `java.*` classes yourself.
4. Provide a controlled fallback and throw **ClassNotFoundException** when absent, rather than searching in circles across all loaders.
5. Call **resolveClass** only per contract; do not force static initialization of every class while holding locks.
6. Avoid holding an extra `synchronized(this)`, static/global monitor, or registry lock across calls to another loader.
7. With multiple plugins, enforce an **acyclic** dependency graph or share APIs through a parent loader; treat dependency relationships as inputs validated when enabling plugins.

Calling `getClassLoadingLock(name)` inside a custom loader **does not automatically make it parallel-capable**: if registration failed or was omitted, it still returns `this`. Therefore combine **proper class registration, valid superclass chain, and lock-compliant loading code**.

### 8.3. Do Not Hold Application Locks While Calling a Custom Loader

Dangerous example:

~~~java
// CODE ILLUSTRATING RISK: pluginRegistry is an object managed by the host.
synchronized (pluginRegistry) {
    // The loader might call back into application code or another loader.
    pluginLoader.loadClass(pluginName);
}
~~~

If another thread holds a class loader lock and needs to access `pluginRegistry`, the pair of operations can form a wait cycle. Take the needed configuration/snapshot first, release the registry lock, and then invoke the loader under the system's safety policy. If you need to record results afterward, re-check state/version when re-entering the registry.

Similarly, avoid invoking plugin callbacks, dependency resolvers that may execute user code, or uncontrolled I/O inside a broad critical section. Long lock hold times increase concurrency failure odds and make plugin shutdown unpredictable.

## 9. Diagnosing Deadlocks and Class-Loading Bottlenecks

A JVM that appears hung while enabling a plugin can be in one of three states:

1. **True deadlock:** a lock wait cycle among two or more threads that cannot make progress.
2. **Lock contention:** threads waiting on a loader processing classes slowly, which can eventually finish.
3. **I/O wait or class initialization wait:** stacks sit inside loading/initialization paths yet the cause is not a class loader monitor.

You need thread dump evidence taken **at the time of the incident**; do not conclude from wait duration or low CPU alone.

### Step 1 — Capture Thread Dumps

Find the process PID and run a command suited to the JDK and permissions. With JDK diagnostic tools:

~~~bash
jcmd <pid> Thread.print -l
~~~

Or:

~~~bash
jstack -l <pid>
~~~

In real commands, **replace `<pid>` with the numeric PID**, such as `12345`; the two lines above are templates, not literal commands. In container environments, run in the appropriate namespace/process with attach permissions. Capturing several dumps a short interval apart helps distinguish progressing work from a stuck wait cycle.

### Step 2 — Read Lock Ownership and Wait Relationships

Look for:

- Threads **BLOCKED (on object monitor)** or `waiting-to-lock`/`locked` entries on the same loader monitor or per-name lock object.
- Stack frames involving `ClassLoader.loadClass`, `getClassLoadingLock`, `findClass`, `defineClass`, `URLClassLoader`, framework loaders, or custom plugin loaders.
- T1's **waiting to lock** pointing to a monitor held by T2 while T2 waits on a monitor held by T1: that is evidence of a circular wait.
- For parallel-capable loaders, a per-name lock monitor may show up simply as a **`java.lang.Object`**, without directly displaying the class name; correlate with stack frames and resolver logs to map it.
- For class initialization, watch for static initialization frames and threads waiting on a class; do not jump to blaming `getClassLoadingLock`.

Illustrative example from an investigation perspective (not literal stdout of a specific JDK):

~~~text
T1: holds monitor lock L_A, waits for monitor lock L_B
T2: holds monitor lock L_B, waits for monitor lock L_A
=> circular wait: class-loader deadlock

T3: waits for monitor lock L_C
T4: holds monitor lock L_C and is slowly reading a JAR
=> contention/I-O: insufficient evidence of deadlock
~~~

The JVM can detect and print certain Java-level deadlocks automatically. Even so, some waits involving class initialization or native/I/O may not appear in automatic deadlock reports; you still need to inspect the actual stacks and states.

### Step 3 — Add Controlled Observability

- Log **loader identity** (name, kind, parent, plugin/tenant ID) and **binary class name** at start/lookup/fallback/finish, especially before calling another loader.
- Log parallel-capable registration status at startup and verify override code uses `getClassLoadingLock(name)`. Do not infer it from the loader's class name.
- Check class-resolution paths for cycles: A → B → A, fallback across all loaders, or registry locks held during cross-delegation.
- Use appropriate JVM/JFR tools to measure lock contention and class-load counts/latency, while understanding the limits of event data provided by each JDK and configuration.
- Correlate with plugin release timestamps, classpath changes, hot reloads, and loader policies. An upgrade can introduce a dependency that makes two formerly independent plugins cross-dependent.

Java provides **ThreadMXBean.findDeadlockedThreads()** to assist in detecting monitor and ownable-synchronizer deadlocks supported by the JVM; it is not sole proof and does not catch every form of resource wait. Inspect the actual thread dump before choosing a fix.

## 10. Preventive Design by Root Cause

| Root cause | Preferred fix | Notes |
| --- | --- | --- |
| All class names serialized on one custom loader | Register parallel-capable properly, use `getClassLoadingLock(name)` | Shared caches/bytecode sources must still be thread-safe |
| Overridden `synchronized loadClass` locking `this` | Remove outer lock and follow per-name locking | Do not remove check–load–define synchronization |
| Two plugin loaders calling each other without ordering | Design a directed dependency graph, eliminate cycles | Parallel-capable cannot fix circular architecture |
| Child loader loading its own copy of host service API | Use parent-first for shared APIs | Avoids two `Class` identities for the same interface |
| Holding plugin registry lock while calling `loadClass` | Separate config snapshot from class loading | Re-verify version/state when updating back |
| Static initializers triggering cyclic dependencies | Minimize side effects, move init to controlled lifecycle | This can be a separate initialization deadlock |
| Reading JARs/remote sources under long-held locks | Cache or stage data carefully, avoid unnecessary blocking | Preserve trust/permission checks and define-once |
| Hard-to-reproduce bug | Build concurrent load tests + timeouts, capture thread dumps | Never treat one passing test run as proof of no deadlock |

### For Plugin Systems Needing Hot Reload

A new plugin version typically receives a new class loader. Threads/instances from the old version can keep references to the old loader, causing waits or leaks if lifecycle cleanup is sloppy. On stop/reload, manage explicitly:

- States **ACTIVE → STOPPING → CLOSED**, rejecting new work while stopping.
- Finish or cancel running tasks per policy; do not hold the plugin manager's monitor while joining a thread that needs that same monitor.
- Close `URLClassLoader` or resource handles once unused, dropping strong references so classes have a chance to unload.
- Do not use a single coarse-grained global registry lock to load, stop, and activate plugins simultaneously; separate state transitions from operations that can block or call outward.

Calling **URLClassLoader.close()** releases resources owned by the loader per contract, yet does not by itself unload defined classes; unloading still depends on references to classes, instances, and the loader. Likewise, `registerAsParallelCapable()` is neither an unloading mechanism nor a lifecycle coordinator.

## 11. Meaningful Concurrency Testing

The per-name lock test in section 4 verifies what the API provides, yet a real plugin system needs tests along its actual class-loading paths.

Scenarios to test:

1. **Same name on the same loader, multiple threads:** every thread receives the exact same `Class` or a valid loading error with the same cause; no duplicate definitions or races causing `LinkageError`.
2. **Two independent names on the same loader:** not serialized by a loader-wide lock when registered parallel-capable; use instrumentation/observation rather than asserting from a single timing measurement.
3. **Parent loader and child loader:** shared API must keep the same `Class` identity; provider classes can live in child, API in parent.
4. **Two plugins with directed dependency:** shared code resolves strictly along the allowed graph without circular fallback.
5. **Two threads activating a plugin concurrently:** registry/lifecycle states do not introduce extra lock cycles or double-register a resource.
6. **Stopping a plugin mid-load:** host handles errors and cleans up validly, not closing backing data while another thread is still using it if forbidden by contract.
7. **Bytecode/URL/JAR source errors:** threads waiting on locks are released via exceptions; cache state stays consistent, leaving no threads hung indefinitely.
8. **Cross-class initialization:** test `<clinit>` separately if plugins have complex static initializers; distinguish those errors from class loader locks.

When writing tests that simulate deadlocks, use timeouts and thread/process cleanup; if deliberately triggering a true deadlock, run it in a **child JVM** so the test can terminate instead of hanging the entire test runner. Use `CountDownLatch`/`CyclicBarrier` to coordinate execution order, yet never equate a short-timeout test pass with proof that no concurrency bug exists.

Each test should prove a clear invariant: define-once per name/loader, no circular waits, loader configuration not bypassed, shared API `Class` identity, and proper unload/lifecycle conditions.

## 12. Common Mistakes

1. **Assuming `synchronized` on all of `loadClass` is always safer:** it prevents same-name races yet blocks all other names and invites deadlocks under cross-delegation.
2. **Calling `registerAsParallelCapable()` while forgetting superclasses:** registration can silently fail if a superclass is not parallel-capable; check the return value and class initialization order.
3. **Setting parallel-capable while dropping locks in an override:** two threads can still race into duplicate `defineClass`; per-name locking is core to the contract.
4. **Putting `synchronized` on an overridden `loadClass`:** continues serializing on `this` despite parallel-capable registration.
5. **Confusing per-name locks with per-package/JAR locks:** two names can run in parallel yet still contend on shared resources; caches and I/O must be thread-safe.
6. **Allowing circular fallback among plugin loaders:** causes infinite recursion or cross-thread deadlocks; enforce a single dependency direction.
7. **Holding registry/manager locks while calling plugin loaders or callbacks:** wait cycles can form between application monitors and loader monitors.
8. **Blaming every hang on `ClassLoader`:** class initialization, I/O, and loader caches have separate waiting mechanisms; inspect thread dumps before fixing.
9. **Believing timeouts break `synchronized` deadlocks:** a caller timeout does not release a monitor held by a thread blocked on a lock; fix the lock graph and delegation path.
10. **Treating parallel-capable as guaranteed speedup:** class loading can still be bottlenecked by the parent loader, disk, ZIP/JAR handling, verification, or caches; measure under realistic workloads.

## 13. Pre-Release Checklist for Extension Class Loaders

- **Loader class and superclasses:** if parallel-capable is needed, all required superclasses support it; register in the right class's static initializer and check the return value.
- **Locking mechanism:** use `getClassLoadingLock(name)` when writing `loadClass`, synchronizing `findLoadedClass` → delegation/lookup → resolution; avoid outer monitors on `this`.
- **Class identity:** service APIs and host APIs use parent-first/shared `Class` identity; do not allow incompatible API copies into child-first paths.
- **Dependency graph:** no delegation cycles among loaders; if code must be shared, define the owning loader and explicit resolution order.
- **Resources and caches:** all data accessed in `findClass` behaves safely when multiple names load concurrently; define clear rules for closing/swapping bytecode sources.
- **Lifecycle:** never hold class loader or plugin registry locks while waiting on external stop/join/callbacks; include cleanup/rollback flows.
- **Diagnostics:** log class name, loader identity, parent/fallback path, and thread; provide a way to capture thread dumps on failure.
- **Testing:** same name, different names, multiple loaders, plugin reload, I/O errors, and static initializers all have dedicated scenarios.

**Technical conclusion:** `ClassLoader` must protect loading a single class name within a single loader. Parallel capability lets **different names** use **different class-loading locks**; it reduces unnecessary serialization yet cannot break circular loader dependencies, registry locks, or class initialization cycles on its own. Preventing deadlocks in runtime extensibility requires **the right lock granularity**, **acyclic delegation paths**, and **controlled plugin lifecycle management**.

**API reference:** [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html), especially `loadClass`, `getClassLoadingLock`, and `registerAsParallelCapable`.
