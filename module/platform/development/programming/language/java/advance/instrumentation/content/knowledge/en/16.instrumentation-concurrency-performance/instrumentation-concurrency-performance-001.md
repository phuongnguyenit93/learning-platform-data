# A Transformer Can Receive Concurrent Calls from Multiple Class-Loading Threads

> **Goal:** Understand why a Java `ClassFileTransformer` object may have to handle **multiple `transform(...)` calls running concurrently**, even when the application simply has multiple threads loading different classes. Know how to design a **thread-safe** transformer without locking the entire class-loading process; distinguish local variables from shared state, use `ConcurrentHashMap`, `LongAdder`, and `AtomicInteger` in the right places, and prevent race conditions, deadlocks, class-loader recursion, and memory leaks. Includes a **runnable Java 17+ lab** to observe two threads requesting class loads, aggregate results safely, and avoid assuming a fixed thread schedule.

This lesson belongs to the **Concurrency and Performance** group of Java Advanced Instrumentation. The topic is **concurrency at the class transformation callback**. It is distinct from thread safety of application code after a class has been defined, and distinct from a single class being used by multiple threads. One transformer can process multiple **class files** across multiple threads; if it shares memory unsafely, output or observed metrics can be corrupted right during the JVM's class-loading phase.

## 1. Visualizing Two Threads Loading Classes Concurrently

A JVM can have multiple class-loading activities:

- Thread A initializes an endpoint, asking the loader to define `com/example/OrderService`.
- Thread B starts another task, asking the loader to define `com/example/InvoiceService`.
- A framework loads proxies, lambda/hidden classes, or plugins.
- Another tool requests redefine/retransform while the JVM is running.

If the agent called:

```java
instrumentation.addTransformer(transformer, false);
```

then when the JVM processes matching class definitions, **the same `transformer` object** is used to invoke `transform`. There is no general contract that the JVM will serialize **all callbacks** on that object under **a single global lock**.

```text
Thread "loader-A"                         Thread "loader-B"
       │                                         │
       ▼                                         ▼
defineClass(OrderService)                defineClass(InvoiceService)
       │                                         │
       ▼                                         ▼
┌───────────────────────┐             ┌───────────────────────┐
│ transformer.transform │             │ transformer.transform │
│ input bytes for A     │             │ input bytes for B     │
└──────────┬────────────┘             └────────────┬──────────┘
           │                                       │
           └───────── same Java object ────────────┘
                           │
                 Agent's shared state?
```

Two callbacks **can overlap** in time, depending on the JVM, class loader, scheduling timing, and class names. Not every JVM or every test is guaranteed to run two callbacks concurrently. The right design rule is: **do not rely on them always running sequentially**.

The **`Instrumentation.removeTransformer` Javadoc** also emphasizes that class loading is multi-threaded: an in-progress or already-scheduled callback may occur **after a transformer has been unregistered**. Therefore, concurrency affects both callback handling and agent lifecycle.

## 2. When Is the `transform` Callback Called?

In `java.lang.instrument.ClassFileTransformer`, Java 9+ provides the overload:

```java
byte[] transform(
        Module module,
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        java.security.ProtectionDomain protectionDomain,
        byte[] classfileBuffer);
```

This is a **reference signature**, not a complete method to compile standalone. When using Java 17+, override it in an implementation or anonymous class as shown in the Section 8 example.

Applicable scenarios:

| Operation Type | Java Callback `canRetransform=false` | Java Callback `canRetransform=true` |
| --- | --- | --- |
| Loading/defining a new class | May be called | May be called |
| `Instrumentation.redefineClasses` | May be called | May be called |
| `Instrumentation.retransformClasses` | **Not called again**, JVM reuses previous output | May be called |

"May be called" means the transformer is registered at the time of processing and the class definition applies to it. This is an **event classification**, not an assertion that every callback has actual transformation work to do.

When multiple transformers participate, the JVM applies the chain in the order of four groups: **Java incapable → JVMTI native incapable → Java capable → JVMTI native capable**. Within a Java group, registration order determines the processing order for **a single class definition**. That **does not turn different classes into a JVM-wide sequential callback queue**.

If `transform(...)` returns `null`, it means "do not modify the bytes at the current layer". If it returns a new `byte[]`, subsequent callbacks will receive the new bytes. **Do not modify `classfileBuffer` directly**: the Javadoc requires that the input array not be mutated.

## 3. Do Not Confuse Class Loader Locks with Transformer Locks

JDK `ClassLoader` has synchronization mechanisms when finding/defining classes. `loadClass(name, resolve)` typically uses `getClassLoadingLock(name)`:

- A class loader that is **not registered as parallel capable** typically uses the loader object itself as the lock. In that case, a single loader may serialize multiple class-loading requests.
- A **parallel-capable** class loader can return a separate lock per class name. Different class names have the opportunity to be loaded concurrently.
- Multiple separate **loader instances** have their own locks, even if each loader serializes its own calls.
- Actual scheduling also depends on the JVM, dependency loading, initialization, and other locks.

Since Java 7, custom loaders can use `registerAsParallelCapable()` following the rules (before creating instances and with appropriate superclasses already parallel capable) if parallel loading support is desired. **Do not call it just to "fix" a race in a transformer**: transformer thread safety must be handled independently.

```text
Loader L1 lock A  ──> class C1 ──> transformer.transform(...)
Loader L2 lock B  ──> class C2 ──> transformer.transform(...)
```

Even if L1 and L2 have their own controls, they do not guarantee that two `transform` calls through **the same transformer object** are mutually exclusive. A common mistake is thinking "the JVM already has a class-loading lock, so all agent fields are safe".

### Must the Same Class Necessarily Be Loaded Concurrently Multiple Times?

Do not interpret this as "two threads in the same defining loader can successfully define the same binary name twice". The JVM has constraints on class identity and loading/definition. Multiple requests for the same name may wait on each other, see the already-defined class, or fail according to loader mechanics. **The focus of this lesson is two or more different classes**, possibly belonging to different loaders, passing through the transformer concurrently.

The same class name from two different **defining class loaders** represents two different runtime types. If an agent caches solely by `className`, it may accidentally mix results from two loaders.

## 4. The Simplest Race Condition Pattern: A Shared Field

Suppose a transformer holds a transformation buffer as a field:

```java
// WRONG example, not a standalone transformer.
private final java.io.ByteArrayOutputStream scratch =
        new java.io.ByteArrayOutputStream();

public byte[] transform(...) {
    scratch.reset();
    scratch.writeBytes(classfileBuffer);
    // ... rebuild class bytes ...
    return scratch.toByteArray();
}
```

The snippet above **does not compile verbatim** because `...` represents undeclared parameters/logic. It is used to point out **shared mutable state**.

When two threads run at the same time:

```text
A: scratch.reset()
A: scratch.writeBytes(bytesA)
B: scratch.reset()
B: scratch.writeBytes(bytesB)
A: return scratch.toByteArray()  // risks returning bytesB
```

With `ByteArrayOutputStream`, mutable operations are not designed to serve as an unlocked shared buffer between two callbacks. Even if each call always produces valid bytes on a single thread, multithreading can cause **corrupt bytecode**, verifier errors, or failures that only appear rarely in production.

**The right approach for temporary data:** Create objects at the invocation scope:

```java
// Illustration inside transform(...).
java.io.ByteArrayOutputStream local =
        new java.io.ByteArrayOutputStream(classfileBuffer.length);
local.writeBytes(classfileBuffer);
byte[] candidate = local.toByteArray();

// This is not a real transformation yet: it only makes a copy.
// If bytecode is not modified, return null.
return null;
```

Each callback has **its own `local`**, without overwriting another thread's data. In a real agent, ASM `ClassReader`, `ClassWriter`, visitor chains, method analysis structures, and offsets should also be created separately **for each transform**, unless the library documentation guarantees a specific object is thread-safe.

### Especially Dangerous Fields

- `byte[] workingBytes` reused across callbacks.
- Mutable `ClassReader`/`ClassWriter` held in a field.
- `HashMap<String, BytecodeModel>` updated concurrently.
- `SimpleDateFormat`, digests, or serializers with shared mutable state and no thread-safety contract.
- Shared `StringBuilder` used to construct method descriptors.
- `long calls++` on a plain field without atomics/synchronization.
- `ArrayList` used as a shared log buffer and appended to by multiple threads.

Bugs may manifest as `ConcurrentModificationException`, wrong output, missing call counts, unusual exceptions, or class-loading hangs; **not every bug can be reproduced with a short test**.

## 5. Safe Data Models: Immutable, Local, Concurrent

### 5.1. Per-Callback Local Variables

The best default:

```java
@Override
public byte[] transform(
        Module module,
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        java.security.ProtectionDomain domain,
        byte[] classfileBuffer) {

    if (className == null
            || !className.startsWith("com/example/business/")) {
        return null;
    }

    // Temporary data lives only within the current callback.
    byte[] original = classfileBuffer;
    int inputLength = original.length;

    // myBytecodeLibraryTransform is an illustrative helper written by the agent.
    // Must create a separate writer/visitor each time.
    byte[] output = myBytecodeLibraryTransform(original);

    return output;
}
```

**This code snippet is illustrative only and does not run standalone** because `myBytecodeLibraryTransform` is not a JDK API. More importantly: `original` is only a **reference** to the input array; do not modify that array in place. `output` must be a **new** array representing a valid class file, and builder states must be isolated from other callbacks.

### 5.2. Safely Published Immutable Configuration

An agent may need to change filter policies while the JVM is running. Do not mutate `enabled`, `threshold`, or `prefixes` fields inside a mutable object while callbacks read them. You can use an immutable record and `AtomicReference`:

```java
// Illustration in a Java 17+ agent class.
record Config(boolean enabled, String prefix) { }

private final java.util.concurrent.atomic.AtomicReference<Config> config =
        new java.util.concurrent.atomic.AtomicReference<>(
                new Config(true, "com/example/business/"));

public byte[] transform(...) {
    Config snapshot = config.get();
    if (!snapshot.enabled()) {
        return null;
    }
    // Use the same snapshot for one transform invocation.
}
```

This is a **fragment**, not a method with full parameters. The meaning: each callback reads a safely published `Config` that then **does not change mid-way** during a single processing pass. The management agent replaces the entire record:

```java
config.set(new Config(false, "com/example/business/"));
```

`AtomicReference.set` has the appropriate visibility semantics. If `Config` itself contains a mutable `HashMap`, making the reference itself atomic **does not automatically make the map contents thread-safe**. Ensure the configuration object is **truly immutable** or properly protected.

### 5.3. Counters Using `LongAdder`

```java
private final java.util.concurrent.atomic.LongAdder calls =
        new java.util.concurrent.atomic.LongAdder();

// Inside transform:
calls.increment();
```

`LongAdder` is efficient for high update frequency across multiple threads. However, `calls.sum()` **is not an atomic snapshot** if threads are actively incrementing, so use it only with aggregate telemetry semantics. Once workers have completely finished (e.g., after `Future.get()` completes in the lab), with no more concurrent updates, the sum will reflect all completed increments.

If you need non-duplicate sequential IDs per call, use `AtomicLong.getAndIncrement()` instead of `LongAdder`. `LongAdder` does not assign sequence numbers to individual events.

### 5.4. Per-Class Tables Using `ConcurrentHashMap`

```java
private final java.util.concurrent.ConcurrentHashMap<String,
        java.util.concurrent.atomic.LongAdder> counts =
        new java.util.concurrent.ConcurrentHashMap<>();

// In the callback, after filtering:
counts.computeIfAbsent(
        className, ignored ->
                new java.util.concurrent.atomic.LongAdder()
).increment();
```

This is illustrative code inside an agent class that has a `className` variable. `computeIfAbsent` is a useful concurrent API when updating histograms/frequencies. However:

- Do not perform heavy work, I/O, or complex class loading inside the mapping function.
- Avoid recursively updating the same map inside the mapping function.
- Use keys with controlled cardinality; do not record every hidden/generated class name unboundedly.
- If class names can collide across loaders, keying by name alone **is not enough** to describe runtime identity.
- Do not retain class loader/object/class references in a static map indefinitely, as this causes a **class-loader leak** after redeploy.

In the lab, we only track **two known internal class names**, so the maximum number of keys is 2, avoiding any unbounded cardinality issue.

## 6. Does `synchronized` Solve It?

One way to protect a shared buffer is to lock the entire `transform`:

```java
// Pattern to be cautious of, not a default recommendation:
public synchronized byte[] transform(...) {
    // Parse, transform, log, generate bytes...
}
```

Data safety may improve, but the performance penalty and deadlock risk are significant:

- **Different** class-loading requests must wait on each other for a single global transformer lock.
- A callback might need to resolve a helper class while holding the monitor; another thread might hold the class-loading lock and wait for the monitor, creating an **AB–BA** cycle.
- If instrumentation of logging, class parsers, or exporters also triggers class loading, deadlocks can become hard to diagnose.
- One slow callback due to I/O causes a backlog of class loads, increasing startup time and latency.

Do not treat `synchronized` on the entire callback as the only way to achieve thread safety. **Prefer a per-call local transform context**, immutable configuration, concurrent counters/maps, and extremely narrow locks **only when truly necessary**.

### A Conceptual Deadlock Cycle

```text
Thread A: holds transformer lock
    └── inside transform, needs to load Helper X
            └── waits for loader L's class-loading lock

Thread B: holds loader L's class-loading lock
    └── loads another class, needs transformer lock
            └── waits for Thread A
```

**This is a risk diagram**, not a claim that every loader/JVM will produce that exact cycle. If the design requires acquiring multiple locks in a callback, you must establish a lock ordering; do not hold an agent monitor when entering operations that can trigger unpredictable class loading, callbacks, or I/O.

## 7. Special Rule: The Transformer Is on the Class-Loading Path

Inside a callback, a seemingly harmless Java call can force the loader to load additional classes. For example:

```java
// Warning: placing this in transform(...) can trigger loading.
Class.forName("com.example.MissingHelper");
logger.debug("Transform " + className);
bytecodeLibrary.initializeAllPlugins();
```

The lines above illustrate risks (the `logger` variable is undeclared), not recommended code. `Class.forName` can also initialize a class depending on the overload; formatters/logging frameworks can also cause the JVM to load their own classes.

The `ClassFileTransformer` Javadoc specifically warns about transforming **core JDK classes** when the transformation process itself depends on those classes. If transforming class `C` causes loading/resolving class `C` itself, the JVM may throw `LinkageError` or a subtype. A failed resolution can leave a remembered failure in another class's symbolic reference, causing an error to surface later at a location far from the callback.

Precautions:

1. **Pre-initialize** agent components that are definitely needed (when safe) in `premain`/`agentmain`, avoiding first-time lazy loading inside the callback.
2. **Exclude agent and helper packages** from the transformation scope.
3. **Do not** call `Class.forName(className)` to "get the current class" while the JVM is defining it.
4. Bytecode libraries should parse from the provided byte array rather than automatically traversing the application's class loader to resolve every type unnecessarily.
5. If a hierarchy resolver is needed, understand the class-loader/module context and avoid recursion.
6. Keep logging minimal; avoid synchronous network calls directly inside the callback.
7. Do not spawn a thread or block waiting for another thread to load a class when the callback itself holds a lock needed for that load.

### Is `ThreadLocal` Safe?

`ThreadLocal` can provide a per-thread context, but it does not solve everything:

- Threads are reused to load many classes; stale state can remain if not reset.
- A callback can be **called nested** on the same thread (reentrancy), causing a shared context via `ThreadLocal` to be overwritten.
- If `ThreadLocal` holds objects from a custom class loader, it can cause leaks via long-lived threads.
- Proper `try/finally` and `remove()` are required if using temporary state.

For most transformers, **per-invocation local variables** are simpler than `ThreadLocal` and easier to prove safe. Use `ThreadLocal` only when profiling shows a benefit and reentrancy/lifecycle have been verified.

## 8. Java 17+ Lab: Two Threads Loading Two Classes, One Transformer Safely Collecting Stats

We will create **a Java agent** and **an application** using two separate `ClassLoader` instances. Two threads are launched via `ExecutorService`, wait together on a `CountDownLatch`, and then respectively request loading `TargetA` and `TargetB`.

A single transformer filters specifically for these two classes, increments a `LongAdder`, records names into `ConcurrentHashMap.newKeySet()`, and uses an `AtomicInteger` to track the number of active callbacks. **The transformer returns `null`**, so no bytecode is modified.

**Purpose:** Drive multiple class-loading requests into a single transformer object, verify that shared statistics do not lose data, and allow observing concurrency when the JVM actually overlaps them. The lab **does not claim** that the two callbacks must overlap on every runtime/thread schedule.

### 8.1. Directory Structure

```text
concurrent-transformer-demo/
├── agent.mf
├── agent-src/
│   └── demo/agent/ConcurrentAgent.java
├── app-src/
│   └── demo/app/Main.java
└── targets-src/
    └── demo/targets/
        ├── TargetA.java
        └── TargetB.java
```

After building:

```text
out/
├── agent/                      # Java agent classes
├── app/                        # application classes
├── targets/                    # .class files read by custom loader
└── concurrent-agent.jar
```

**Do not put `out/targets` on the runtime `-cp`**: if the target classes appear on the application classpath, parent delegation may load them via a different path than what the lab intends to test.

### 8.2. `targets-src/demo/targets/TargetA.java`

```java
package demo.targets;

public final class TargetA {
    public static String id() {
        return "A";
    }
}
```

### 8.3. `targets-src/demo/targets/TargetB.java`

```java
package demo.targets;

public final class TargetB {
    public static String id() {
        return "B";
    }
}
```

Each target depends only on `java.base`. This is important because the lab's custom loader uses the **platform loader as its parent**; no external application or library classes need to be resolved by the target classes.

### 8.4. `agent-src/demo/agent/ConcurrentAgent.java`

```java
package demo.agent;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.LongAdder;

public final class ConcurrentAgent {

    private static final LongAdder CALLBACKS = new LongAdder();

    // Concurrent set bounded in content since the callback only stores A/B.
    private static final Set<String> NAMES =
            ConcurrentHashMap.newKeySet();

    private static final AtomicInteger ACTIVE = new AtomicInteger();
    private static final AtomicInteger PEAK = new AtomicInteger();

    public static void premain(String args, Instrumentation inst) {
        inst.addTransformer(new ClassFileTransformer() {
            @Override
            public byte[] transform(
                    Module module,
                    ClassLoader loader,
                    String className,
                    Class<?> classBeingRedefined,
                    ProtectionDomain domain,
                    byte[] classfileBuffer) {

                if (!"demo/targets/TargetA".equals(className)
                        && !"demo/targets/TargetB".equals(className)) {
                    return null;
                }

                int now = ACTIVE.incrementAndGet();
                PEAK.accumulateAndGet(now, Math::max);
                try {
                    CALLBACKS.increment();
                    NAMES.add(className);
                    // Do not share mutable buffers or writers.
                    // No need to modify bytes in this experiment.
                    return null;
                } finally {
                    ACTIVE.decrementAndGet();
                }
            }
        }, false);

        System.out.println("agent: transformer registered");
    }

    public static long callbackCount() {
        return CALLBACKS.sum();
    }

    public static int distinctTargetCount() {
        return NAMES.size();
    }

    public static int activeCallbackCount() {
        return ACTIVE.get();
    }

    public static int maximumActiveCallbacks() {
        return PEAK.get();
    }
}
```

**Why is this thread-safe?**

- `CALLBACKS` is a `LongAdder`, suitable for concurrent increments.
- `NAMES` is a set from `ConcurrentHashMap.newKeySet()`; multiple threads can call `add` without corrupting the structure.
- `ACTIVE.incrementAndGet()` and `decrementAndGet()` manage the concurrent callback count using atomic operations.
- `PEAK.accumulateAndGet(now, Math::max)` records the highest number of in-flight callbacks **observed by this probe**, without relying on a racy `if (now > old) old = now` check.
- `finally` guarantees the decrement runs even if code inside `try` throws an exception.
- There is no shared `byte[] working`. Each callback receives its own `classfileBuffer` and **does not modify** that array.
- No heavy helpers or I/O are called inside the callback, reducing the risk of recursion and deadlock.
- Filtering the two internal names up front ensures all other JDK/helper classes are skipped immediately.

**What the lab does not do:** It does not assert `PEAK>=2` as a mandatory pass condition. Even when two tasks start close together, the JVM **may serialize** class-loading phases or the OS may not schedule the callbacks to overlap. Seeing `maximumActiveCallbacks()==1` in one run does not prove a transformer is always single-threaded.

If you want to observe this, you can temporarily print:

```java
// Illustrative line placed in Main after both Futures have completed:
System.out.println(
        "agent: max-active=" + ConcurrentAgent.maximumActiveCallbacks());
```

The output may be `1` or `2`, depending on the environment and scheduling. **Do not use this difference to conclude whether a race exists or does not exist in transformer code**; in production, you must always design for thread safety.

### 8.5. `app-src/demo/app/Main.java`

```java
package demo.app;

import demo.agent.ConcurrentAgent;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public final class Main {

    private static final class TargetLoader extends ClassLoader {
        private final Path root;

        TargetLoader(Path root) {
            // Parent does not have the lab's application/target classes.
            super(ClassLoader.getPlatformClassLoader());
            this.root = root;
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {

            // Do not read arbitrary classes from disk.
            if (!"demo.targets.TargetA".equals(name)
                    && !"demo.targets.TargetB".equals(name)) {
                throw new ClassNotFoundException(name);
            }

            Path file = root.resolve(
                    name.replace('.', '/') + ".class");
            try {
                byte[] bytes = Files.readAllBytes(file);
                return defineClass(name, bytes, 0, bytes.length);
            } catch (IOException e) {
                throw new ClassNotFoundException(name, e);
            }
        }
    }

    private static String loadAndCall(
            String binaryName, Path root, CountDownLatch start)
            throws Exception {

        // Both workers start loading only when main releases the latch.
        start.await();
        ClassLoader loader = new TargetLoader(root);
        Class<?> type = Class.forName(binaryName, true, loader);
        return (String) type.getMethod("id").invoke(null);
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: Main <targets-class-root>");
        }

        Path root = Path.of(args[0]);
        CountDownLatch start = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(2);

        try {
            Callable<String> jobA = () -> loadAndCall(
                    "demo.targets.TargetA", root, start);
            Callable<String> jobB = () -> loadAndCall(
                    "demo.targets.TargetB", root, start);

            Future<String> a = pool.submit(jobA);
            Future<String> b = pool.submit(jobB);

            // Give class-load requests an opportunity to run in parallel.
            start.countDown();

            String resultA = a.get(10, TimeUnit.SECONDS);
            String resultB = b.get(10, TimeUnit.SECONDS);

            System.out.println(
                    "app: values=" + resultA + "," + resultB);
            System.out.println(
                    "agent: callbacks=" + ConcurrentAgent.callbackCount());
            System.out.println(
                    "agent: distinct-targets=" +
                    ConcurrentAgent.distinctTargetCount());
            System.out.println(
                    "agent: active-after=" +
                    ConcurrentAgent.activeCallbackCount());
            System.out.println(
                    "agent: peak-positive=" +
                    (ConcurrentAgent.maximumActiveCallbacks() >= 1));
        } finally {
            pool.shutdownNow();
        }
    }
}
```

**Concurrency design review:**

1. The app uses a two-worker pool instead of spawning new threads inside the transformer.
2. `CountDownLatch` helps the two tasks start close together, but **does not promise** parallel execution into the callback on every JVM.
3. The two `TargetLoader` instances **are two different objects**; the callback code still runs through **one** transformer registered with the JVM.
4. `TargetLoader` only locates the exact two classes from `out/targets`; JDK classes are handled by the parent `ClassLoader.getPlatformClassLoader()`.
5. `Class.forName(binaryName, true, loader)` defines/initializes the target class; each class's `id()` has no side effects other than returning a string.
6. After `Future.get(...)` for **both** tasks, all callbacks required to load and invoke those targets have completed. Reading the counters/active count at that point is valid.
7. `a.get(10, TimeUnit.SECONDS)` and `b.get(...)` make the test fail clearly if loading stalls; this **does not** guarantee that a JVM deadlock disappears. `shutdownNow()` asks workers to stop when possible, and cannot safely kill a thread stuck in class loading.
8. Do not print messages from inside the callback, to avoid turning log interleaving order into a "correct answer" about scheduling.

### 8.6. `agent.mf`

```text
Manifest-Version: 1.0
Premain-Class: demo.agent.ConcurrentAgent

```

The lab only uses `ClassFileTransformer` registered with `canRetransform=false` and new class definitions. `Can-Retransform-Classes` or `Can-Redefine-Classes` **are not needed**. If you add those two capabilities for another experiment, clearly separate that as a new scope and verify JVM support rather than treating them as prerequisites for this lab.

### 8.7. Compile and Run: Bash

From the `concurrent-transformer-demo` directory:

```bash
mkdir -p out/agent out/app out/targets

# Compile agent first.
javac -encoding UTF-8 -d out/agent \
    agent-src/demo/agent/ConcurrentAgent.java

# Package only agent classes, not target classes.
jar --create --file out/concurrent-agent.jar \
    --manifest agent.mf -C out/agent .

# Application needs agent API at compile time because it calls agent statistics.
javac -encoding UTF-8 -cp out/agent -d out/app \
    app-src/demo/app/Main.java

# Two independent targets outside the runtime classpath.
javac -encoding UTF-8 -d out/targets \
    targets-src/demo/targets/TargetA.java \
    targets-src/demo/targets/TargetB.java

java -javaagent:out/concurrent-agent.jar \
    -cp out/agent:out/app \
    demo.app.Main out/targets
```

Do not put `out/targets` in `-cp`; if accidentally added, parent delegation may load the targets via the system loader instead of `TargetLoader`, changing the meaning of the example. Unix-like classpaths use `:` when there are multiple entries.

### 8.8. Compile and Run: Windows PowerShell

```powershell
New-Item -ItemType Directory -Force `
    -Path out/agent, out/app, out/targets | Out-Null

javac -encoding UTF-8 -d out/agent `
    agent-src/demo/agent/ConcurrentAgent.java

jar --create --file out/concurrent-agent.jar `
    --manifest agent.mf -C out/agent .

javac -encoding UTF-8 -cp out/agent -d out/app `
    app-src/demo/app/Main.java

javac -encoding UTF-8 -d out/targets `
    targets-src/demo/targets/TargetA.java `
    targets-src/demo/targets/TargetB.java

java -javaagent:out/concurrent-agent.jar `
    -cp "out/agent;out/app" `
    demo.app.Main out/targets
```

PowerShell uses a **backtick** for line continuation, unlike `\` in Bash. Windows classpaths use `;`. You need JDK 17+ with matching `java`, `javac`, and `jar`. The agent JAR must have a valid `Premain-Class` and the required agent classes; do not put `TargetA/B` into the agent JAR.

### 8.9. Expected Stdout When the Lab Runs Normally

```text
agent: transformer registered
app: values=A,B
agent: callbacks=2
agent: distinct-targets=2
agent: active-after=0
agent: peak-positive=true
```

**Why can these lines be expected to be stable?**

- Each target class is requested to be defined **once** in its own custom loader and matches the filter.
- `CALLBACKS` increments once per selected callback.
- `NAMES` only holds two names and is added to concurrently in a thread-safe manner.
- Both `Future.get` calls complete before printing statistics.
- The transformer's `finally` block decrements `ACTIVE` back to 0 at the end of every target callback.
- `PEAK>=1` is true if at least one matching callback ran; it does not need to imply `PEAK==2`.

If you see extra logs from the JVM or another agent, that is data outside the lab; the lab assumes no other tools are writing to stdout. If a class file is missing or the path is wrong, `Future.get()` throws `ExecutionException` containing the cause instead of pretending the statistics lines succeeded. If the JVM does not support Java agent startup, the program cannot run as instructed.

**Testing real concurrency:** Add a line displaying `maximumActiveCallbacks()`; if you see `2`, you have evidence that **two target callbacks overlapped at the time of measurement**. If you see `1`, you **cannot** conclude that callbacks are always sequential across JVMs; you only know **this run** did not record an overlap. You can increase the number of classes/loaders/tasks and repeat the test, but do not put `Thread.sleep` or forced barriers directly into a production transformer.

## 9. Why Does the Example Not Use `HashMap`/`int++`?

If you use:

```java
// Unsafe if multiple callbacks update concurrently:
private final java.util.Map<String, Integer> count = new java.util.HashMap<>();
private int total;
```

and in the callback:

```java
total++;
count.put(name, count.getOrDefault(name, 0) + 1);
```

then:

- `total++` consists of read, add, write; multiple threads can suffer **lost updates**.
- `HashMap` does not provide safety under concurrent writes; both the map structure and results can become inconsistent.
- `count.getOrDefault` followed by `put` is not an atomic operation; two threads can read the same old value and overwrite each other's results.
- `volatile int total` **does not** turn `total++` into an atomic addition; `volatile` ensures appropriate visibility/ordering, but does not combine read-modify-write into one atomic operation.

Replace with:

```java
private final java.util.concurrent.atomic.AtomicInteger total =
        new java.util.concurrent.atomic.AtomicInteger();

total.incrementAndGet();
```

or `LongAdder` when only total frequency is needed. For a histogram map, use `ConcurrentHashMap<K,LongAdder>` and `computeIfAbsent(...).increment()` as in Section 5.

### When Is `AtomicInteger` Better Suited Than `LongAdder`?

- Use `AtomicInteger` if you need to receive the value **immediately after the increment** (`incrementAndGet`) or perform compare-and-set.
- Use `LongAdder` for high-update-frequency counters when `sum()` does not need to be an atomic snapshot while updates are occurring.
- Do not use `LongAdder.sumThenReset()` as an **atomic rollover** while multiple transformers are still incrementing, because updates concurrent with the reset can prevent metrics from being cleanly partitioned into time windows.
- For exported counter metrics, record process restarts/resets if the monitoring system computes rates from cumulative numbers.

## 10. Do Not Cache Transform Output Solely by `className`

An easy-to-get-wrong optimization is:

```java
// Architectural example that is not yet safe:
ConcurrentHashMap<String, byte[]> cache = new ConcurrentHashMap<>();
```

Why is keying by name insufficient?

1. **Class loader:** `com/example/Widget` in plugin A and plugin B may be two different types with different source bytes.
2. **Module layer:** One binary name can exist in multiple module/loader contexts.
3. **Class-file version:** Two versions with the same name may differ in major version or dependencies.
4. **Transformer configuration:** Enabled/disabled rules, probe version, or sampling mode may change.
5. **Input bytes:** A redefine can supply new bytes for the same class; an old name-based key could return stale output.
6. **Reentrancy:** A cache miss might invoke a byte-generation function that loads a class and hits the cache again; the mapping function must not recurse arbitrarily.

If a cache is truly needed, the key must fully describe both the input **and** context, bound its size, and avoid strongly retaining application class loaders. For instrumentation that already runs before the JVM defines a class, **do not use a global cache** without profiling proof that it is needed and tests covering redeploy, redefine, and multi-loader scenarios.

### Do Not Mutate `classfileBuffer` and Return the Same Array

The Javadoc requires that the input byte array not be modified. A transformer should:

```java
// Illustration inside callback:
if (!shouldTransform(className)) {
    return null;
}
byte[] generated = generateNewClassFile(classfileBuffer);
return generated;
```

`shouldTransform` and `generateNewClassFile` are **agent-provided functions**, not JDK APIs. If nothing is modified, `return null`; if modified, the output must be a **valid class file** with proper stack maps, metadata, method descriptors, and control flow. The trick of "using the input array as scratch space to reduce allocation" can break chaining of other transformers, even if the agent only has one thread.

## 11. Lock Ordering, Recursion, and Class Initialization

The callback runs during class definition, before the JVM verifies/applies the class. At that point:

- Some classes or helpers that the transformer wants to use **have not been loaded yet**.
- A class initializer might run if the tool accidentally references a static field/method of a new class.
- A loader lock may currently be held.
- Logging/exporters may need to load other classes and create a dependency chain.
- `ClassFileTransformer` may be called again on another loading thread, or another callback of the same agent may occur concurrently.

Therefore, do not do this:

```text
transform(A):
    holds agent monitor
    calls a synchronous network exporter
    waits for a worker to load class B
    worker must acquire agent monitor to transform(B)
```

This is a **deadlock pattern** example, not a runnable program. Good principles:

- **Do not block** inside the callback on HTTP timeouts, full queues, or latches from external code.
- Do not hold a monitor around class loader calls or heavy reflection.
- Initialize parsers/formatters/helpers before multiple application threads load classes, when safe to do so.
- Filter agent/helper packages to avoid self-instrumentation.
- Do not log full class bytes, user data, or high-cardinality class names.
- Verify bytecode output separately; do not rely on the transformer callback completing to claim the JVM has defined the class.

### Reentrant Callbacks and Guards

A `ThreadLocal<Boolean>` is sometimes used to mark "currently transforming" on the same thread:

```java
// Illustrates the idea, not a complete transformer:
private static final ThreadLocal<Boolean> IN_TRANSFORM =
        ThreadLocal.withInitial(() -> false);

if (IN_TRANSFORM.get()) {
    return null;
}
IN_TRANSFORM.set(true);
try {
    // Transformation does not itself load the classes it is processing.
} finally {
    IN_TRANSFORM.remove();
}
```

Such a guard **does not** make shared data across threads safe, nor does it prevent parallel callbacks on **two different threads**. If nested callbacks can genuinely happen, a per-thread guard design must account for `remove()` and outer-scope state so it does not accidentally clear the outer callback's state. A simple boolean may not suffice for complex nesting cases. **Prefer filtering and safely pre-initializing dependencies**.

## 12. `removeTransformer` and Configuration Changes While Callbacks Are Running

A false assumption:

```text
removeTransformer(t) returns true
⇒ all running transforms have stopped
⇒ safe to immediately delete all state/helpers of t
```

The Javadoc makes no such guarantee. Due to the multi-threaded nature of class loading, a transformer **may still receive callbacks** after being removed. A request already deep in the pipeline may be using the object. Therefore:

- `removeTransformer` is an **unregister operation for future events**, not a barrier waiting for all callbacks to finish.
- Do not immediately close/release every resource an old callback might use while expecting callbacks to never happen again.
- If you need to disable functionality, use a **safely published `enabled` flag**, and have the callback read a snapshot so it can return `null` quickly.
- If a clean shutdown is needed, use a dedicated protocol to track **in-flight callbacks**, wait with a timeout outside the callback when safe, and manage resources according to the agent's lifecycle.
- `AtomicInteger ACTIVE` in the lab is a **measurement** tool, not a stop-synchronization mechanism; checking `ACTIVE==0` once does not guarantee no new callback can arrive afterward.
- Exclude bridges/helpers from transformation and keep their ABI stable if already-instrumented classes continue calling helpers after the transformer is removed.

In particular, **removing a transformer does not revert bytecode** already applied by the JVM. An already-instrumented class can continue calling helpers even when the transformer is no longer registered.

## 13. When `retransformClasses` Runs Concurrently with Class Loading

With `Instrumentation.retransformClasses`, the JVM takes already-loaded `Class<?>` objects and passes them through the corresponding chain:

- Java transformers registered with `canRetransform=false` **are not called again** during retransform; their previous output is reused.
- Java transformers registered with `canRetransform=true` receive new callbacks for applicable retransformed classes.
- With `redefineClasses`, both capable and incapable transformers receive applicable callbacks.
- These callbacks may occur close in time to other threads loading new classes or another agent handling a different event type. Do not use a single global mutable writer across class load/redefine/retransform.

States like `classBeingRedefined != null` only indicate that the class already exists; they **do not by themselves distinguish** retransform from redefine. If the agent wants to log the event type, obtain the context from the API-calling layer itself rather than guessing from callback parameters.

**Distinguishing shareable data:**

| Data | Policy |
| --- | --- |
| Current callback's byte array | Local/read-only |
| Class model, bytecode writer/visitor | Local to each transform |
| Immutable config | Share via final/atomic publication |
| Counters | `LongAdder`/`AtomicLong`, not `long++` |
| In-flight callbacks | `AtomicInteger` and a dedicated lifecycle protocol |
| Per-class stats | `ConcurrentHashMap` with bounded keys |
| Class loader/class references | Avoid long-term strong retention; use cleanup/weak strategy |
| Telemetry queue | Bounded/nonblocking if on the hot path |
| HTTP exporter and heavy serializer | Independent worker, never synchronous inside transform |

## 14. Testing Race Conditions Instead of Only Testing the Happy Path

A single run showing `callbacks=2` does not prove that all transformations using shared state are safe. Intentional tests are needed:

1. **Multiple different classes:** Load many classes across different threads/loaders.
2. **Same name in multiple loaders:** Ensure outputs/counters are not mixed when identities differ.
3. **Registration before/after:** Install the transformer before loading targets; do not count class loads that occurred prior to registration.
4. **Loading during config changes:** Use immutable snapshots, test toggling enabled/filters.
5. **Removing during loading:** Do not assume callbacks stop immediately; have a shutdown policy.
6. **Transformer throws:** All shared-state counters/active counts must be cleaned up in `finally`.
7. **Slow exporter:** Never let the callback block or try to log while a class loader lock is held.
8. **Independent bytecode buffers:** Compare hashes/outputs for the same input across multiple parallel runs.
9. **Reentrancy:** Use a helper capable of loading classes to test guards/exclusions in staging.
10. **Different JVMs/JDKs:** Lack of overlap in one run does not prove sequential behavior on another JVM.

### Appropriate Measurement Tools

- Thread dumps/JFR to inspect blocking, lock contention, class-loading events, and stack traces.
- JMH when benchmarking hot-path operations of transformer helpers (isolated from full class loading).
- Stress tests with many classes/loaders and repeated JVM restarts, not just a single run.
- Bounded metrics: callback count, class transform latency, errors, queue drops, active/peak callbacks.
- Classfile verifier and runtime tests if the transformer actually returns new bytes.

Do not arbitrarily add `Thread.sleep()` in a production transformer to "make overlap easier to see"; it slows down startup and can push the JVM into timeouts. The lab does not require overlap because it tests **safe coding practices**, not a thread-scheduling guarantee.

### A Special Test Scenario

If you want to reproduce a shared-buffer bug, use a separate test that launches **multiple threads calling a pure transform helper** on two different byte arrays and compares output hashes. That test proves thread safety of the helper/bytecode generation **under artificial invocation**, but it is not proof that the JVM called `ClassFileTransformer` concurrently. Clearly distinguish *unit stress* from *integration stress*.

## 15. Thread-Safe Transformer Design Checklist

1. **Filter classes early:** Only process classes/packages actually in scope.
2. **Immutable input:** Do not modify `classfileBuffer` in place.
3. **Per-invocation builders:** Do not share mutable ClassWriter/ClassReader/visitor/scratch buffers.
4. **Immutable config snapshot:** One transform uses one stable policy version.
5. **Proper concurrent counters:** `LongAdder` for aggregates; `AtomicInteger/AtomicLong` for values needing atomicity.
6. **Controlled concurrent maps:** Keep `computeIfAbsent` small, no recursion, no I/O.
7. **No global mutable `HashMap` or `ArrayList`** if concurrent writers exist without proper synchronization.
8. **Limit locking:** Do not `synchronized` the entire callback unless serialization is genuinely acceptable and lock ordering has been analyzed.
9. **Avoid class-loading recursion:** Exclude agent/helpers, check dependencies loaded by the transformer itself.
10. **Do not block on network:** Use workers and bounded event queues if telemetry must be recorded.
11. **Do not retain class loaders indefinitely:** Be careful with static maps/caches in long-lived bootstrap agents.
12. **Manage removal/shutdown:** Callbacks may arrive after `removeTransformer`; state/resources must have a proper lifecycle.
13. **Distinguish load/redefine/retransform:** `canRetransform=false` does not get callbacks on retransform but still gets callbacks on redefine.
14. **Observe actual results:** A callback being invoked does not prove the bytes were accepted by the JVM.
15. **Test concurrency thoroughly:** Multi-loader, multi-thread, config changes, exceptions, reentrancy, and JVM versions.
16. **Do not confuse diagnostics with business invariants:** `LongAdder.sum()` is a metric, not a transaction ledger.
17. **Measure overhead:** Allocation, CPU, startup, class-loading latency, safepoint/GC, and lock contention.
18. **Preserve Java semantics:** If generating real bytecode, verify method returns/throws, stack maps, access/module flags, and proper class identity.
19. **Keep sufficient diagnostics on failure:** Log class name/loader/category in a bounded way; do not dump sensitive data.
20. **Have a rollback plan:** An instrumentation bug should not force debugging in an environment lacking original artifacts; prepare a verified restart/redefine plan.

## 16. Common Pitfalls

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Sometimes runs fast, sometimes `VerifyError` | Shared writer/buffer mixes output class bytes | Create writer and buffer per invocation, verify output |
| `callbacks` smaller than actual class count | Lost increments from `int++`, or classes filtered/registered late | Use atomic/LongAdder; verify exact scope |
| `ConcurrentModificationException` in map | `HashMap`/`ArrayList` updated concurrently | Use concurrent collections or immutable snapshot design |
| Slow startup when many classes load | `synchronized transform`, heavy I/O or logging | Shrink critical path, local context, decouple exporter |
| JVM hangs when loading a class | Loader lock + transformer monitor cycle or recursive load | Thread dump/JFR, eliminate lock nesting |
| `NoClassDefFoundError` during transform | Agent tries to resolve unavailable helper/class, loader mismatch | Pre-load dependencies, exclude agent packages |
| `ClassCircularityError` | Recursive class loading through transformer/helper | Avoid referencing the class currently being defined |
| Heap grows after hot redeploy | Static map retains old `Class<?>` or `ClassLoader` | Weak references/eviction and lifecycle cleanup |
| Lost events despite accurate callback counter | Bounded queue drops or exporter errors | Track accepted/dropped/exported separately |
| Callbacks still seen after `removeTransformer` | Multi-threaded JVM class loading | Allowed per Javadoc; shut down defensively |
| No overlap seen in one test run | Scheduling or loader lock serializes workload | Do not conclude always single-threaded; test multiple setups |
| Duplicate probes after redefine | Non-idempotent transformer, stale version cache | Check bytes/schema and marker/probe placement |
| Wrong class after cache hit | Cache keyed only by binary name, ignoring loader/config/input | Design complete key or remove cache |
| `ThreadLocal` retains old state | Thread reuse, missing `finally/remove` | Scope cleanup, prefer local variables |
| Valid bytecode but wrong business logic | Altered control flow, exception paths, or helper semantics | Runtime integration tests and controlled rollout |

## 17. Self-Check Questions

**1.** Why can the same `ClassFileTransformer` be called by multiple threads?  
**Answer:** The JVM can load multiple classes across multiple threads/loaders; registration does not create a global lock guaranteeing all callbacks are serialized.

**2.** Does a non-parallel-capable class loader guarantee the transformer is single-threaded JVM-wide?  
**Answer:** No. **Different** loaders can still proceed with loading independently; another loader may also be parallel capable.

**3.** Is `long calls++` safe under two concurrent callbacks?  
**Answer:** No. It is a non-atomic read-modify-write; use `AtomicLong` or `LongAdder` depending on the goal.

**4.** Does `volatile long calls` fix lost updates on `calls++`?  
**Answer:** No. `volatile` improves visibility, but `++` is still not an atomic operation.

**5.** Why should you not keep an ASM `ClassWriter` in a transformer field?  
**Answer:** It is a mutable per-class context; two callbacks can write to it concurrently and corrupt contents/labels/constant pool.

**6.** How does `ConcurrentHashMap.newKeySet()` differ from `HashSet` in the example?  
**Answer:** It supports safe concurrent `add` operations for the set of class names; a plain mutable `HashSet` is unsafe under multiple concurrent writers.

**7.** Is `LongAdder.sum()` an atomic snapshot while callbacks are still incrementing?  
**Answer:** No. Once callbacks have completed (such as after `Future.get`), the total statistic is stable.

**8.** Does `maximumActiveCallbacks()==1` in one run prove the JVM always serializes transformers?  
**Answer:** No. It only means that specific test run did not observe overlap; schedulers/loaders/JVMs can behave differently.

**9.** Why can `synchronized transform` slow down startup?  
**Answer:** It forces all callbacks on the same object to contend on a single monitor, even when processing different classes.

**10.** Is `removeTransformer` a barrier guaranteeing no further callbacks will occur?  
**Answer:** No. The Javadoc warns that callbacks may arrive after removal due to multi-threaded class loading.

**11.** Is a `ClassFileTransformer` always called again during retransform if registered with `canRetransform=false`?  
**Answer:** No. The incapable transformer's output is reused and the callback does not run; however, during redefine, applicable callbacks still run.

**12.** Why is `className` insufficient to identify a class in a cache?  
**Answer:** The same name can exist across multiple defining loaders, module contexts, and byte versions.

**13.** Should you call `Class.forName(className)` right inside `transform` to inspect the class being loaded?  
**Answer:** No. It can trigger repeated loading/initialization, recursion, or linkage errors.

**14.** Does using `ThreadLocal` replace all synchronization for shared fields?  
**Answer:** No. It only isolates state per thread; reentrancy, lifecycle, and shared fields still need to be addressed separately.

**15.** If a transformer throws an exception, should you skip decrementing the active count?  
**Answer:** No. Put the decrement in `finally` so counters/lifecycle do not drift.

**16.** Does the lab returning `null` mean the JVM instrumented the `id()` method?  
**Answer:** No. The callback only observes and records stats; it does not alter class bytes.

**17.** If agent code generates new bytes across multiple threads, what is the most important rule?  
**Answer:** Each invocation must have its own bytecode builder and temporary state; do not mutate the input buffer, output must be valid, and do not depend on unprotected shared mutable state.

**18.** When a telemetry queue is full, should you call `put` and block inside the callback?  
**Answer:** Usually no. It holds up the class-loading path and can cause latency/deadlocks; use bounded nonblocking `offer` and a drop policy if telemetry is best-effort.

**19.** When output caching is unnecessary, should you use a global map to "improve performance"?  
**Answer:** No. Caching adds complexity, memory retention, stale state, and loader identity bugs; only do so after measurement and testing.

**20.** Does a callback logging success mean the class has been verified/installed by the JVM?  
**Answer:** No. The JVM verifies/installs bytes after the transformer chain; you must observe the operation's outcome and runtime behavior.

## 18. Official References

- [JDK 17 — `ClassFileTransformer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): `transform` contract, callback before JVM defines class, chaining, `null`, `IllegalClassFormatException`, notes on class circularity.
- [JDK 17 — `Instrumentation`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `addTransformer`, `removeTransformer` and warning that callbacks may still occur after removal due to multi-threaded class loading; redefine/retransform.
- [JDK 17 — `ClassLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): parent delegation, `getClassLoadingLock`, and `registerAsParallelCapable`.
- [JDK 17 — `ConcurrentHashMap`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): `newKeySet`, `computeIfAbsent`, and concurrent operations.
- [JDK 17 — `LongAdder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html): contended counters and limitations of `sum`.
- [JDK 17 — `AtomicInteger`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html): atomic increment/decrement/accumulate.
- [JDK 17 — `CountDownLatch`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): coordinating when workers start.
- [JDK 17 — `Future`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): `get` and memory visibility guarantees when a worker finishes.
- [JLS 17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): Java memory model, visibility, happens-before, and races.
- [JVMS 17 — Loading, Linking and Initialization](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): class loading/definition, identity, and loader constraints.

**Key takeaway:** A transformer can handle class-loading requests **from multiple threads** within the same timeframe. A single class loader's lock does not guarantee that callbacks **JVM-wide** are serialized. Keep bytecode builders and scratch state **per invocation**, use **immutable snapshot** configuration, **concurrent** counters/collections when sharing, avoid I/O and long-held locks inside callbacks, and test with multiple classes/loaders/threads. The lab verifies correct state without **assuming** every run observes `PEAK==2`.