# Pre-initializing Helpers and Preventing Recursive Class Loading, Class Circularity, or Deadlock

In **Java Advance – instrumentation**, under **Concurrency and Performance**, a Java agent can cause an application to encounter `LinkageError`, `ClassCircularityError`, or hang at class-loading time, even though the transformer itself appears to process only a few bytecodes. The cause is usually code invoked inside `ClassFileTransformer.transform(...)` that makes the JVM load additional classes, initialize helpers, or wait on a lock right when the target class **has not yet completed its definition process**.

A typical example: a transformer calls a logger for the first time to report that it has instrumented `OrderService`; the logger initializes a provider, the provider loads another class; the transformer is invoked again and inadvertently needs `OrderService` itself or waits on a class loader lock. The failure sometimes surfaces on a different thread from where the cause originated.

This lesson explains **why helpers must be prepared before registering a transformer**, how to design callbacks to minimize recursive class loading, and how to distinguish **class circularity** from **deadlock** and **static initialization** cycles. There are two complete, standalone Java 17+ examples that can be run by following the instructions.

## 1. Milestones in a Java Agent's Lifecycle

At startup, the agent receives `Instrumentation` via `premain`. When calling `Instrumentation.addTransformer`, the agent registers a callback for the JVM to invoke when a class is loaded, redefined, or retransformed depending on the transformer's capabilities. For first-time class loading, the callback runs **before class definition completes**.

```text
JVM loads agent JAR and calls premain
        |
        v
Initialize helpers + config + state needed for transformer
        |
        v
addTransformer(transformer)
        |
        v
Application class loader begins loading class C
        |
        v
ClassFileTransformer.transform(..., className=".../C", bytes)
        |
        v
JVM continues to verify/link/define C
        |
        v
Application uses C
```

You should not assume the callback is an independent "observation event" where it is safe to call any API. It is a piece of code running **directly in the JVM's class-loading path**. Many custom class loaders hold a lock in `loadClass`, while the classes used by the callback may not yet be loaded or initialized.

**Principle:** do as little as possible in the callback: filter early, use pre-prepared classes/structures, transform the byte array only when truly necessary, and return `null` when making no changes. Network connections, logger initialization, class lookups via reflection, or waiting on work from another thread must happen in a separate phase.

## 2. Class Loading, Linking, and Initialization Are Different Concepts

| Phase | What happens | Why it matters for instrumentation |
| --- | --- | --- |
| **Loading** | The class loader locates bytes, and the JVM defines a class; the transformer may be invoked during this process | The callback may ask the JVM to load another class while the current class is still loading |
| **Linking** | Verify, prepare, and resolve symbolic references when appropriate | Errors in the class hierarchy, class file, or name/method resolution can produce `LinkageError` |
| **Initialization** | Executes static field initializers and `<clinit>` | Helpers may initialize dependencies, invoke application code, or wait on another class being initialized on another thread |

Do not call all of these phenomena "class loading." For example, `ProbeHooks.class` obtains `Class<?>` but **does not necessarily** run the static initializer, whereas `Class.forName("agent.ProbeHooks", true, loader)` requests class initialization.

Symptoms to distinguish:

- **Recursive class loading**: during `transform(C)`, the callback or a dependency asks to load/resolve `C` again or a group of classes leading back to it. Depending on the situation, this may produce `LinkageError`, recursion, or another error; you cannot assume a single fixed exception.
- **`ClassCircularityError`**: according to the Javadoc, the JVM detects a **cycle in the superclass hierarchy** of a class being loaded. A structure like `A extends B`, `B extends A` is invalid; the Java compiler can catch source-level errors, while bytecode generation tools/custom loaders can supply an invalid classfile.
- **Deadlock**: threads mutually hold and wait on resources in a cycle, such as loader lock A → B → A or class initialization locks. In that case, the program may **throw no exception**, and simply hang waiting.
- **Same-thread static initialization cycle**: the Java Language Specification has specific rules for reentrant requests by the thread currently initializing a class. It is not necessarily `ClassCircularityError`; a concrete example is in section 6.

## 3. Why Calling Helpers Inside a Transformer Is Dangerous

Consider the following illustrative code, **which should not be used as-is in a real agent**:

```java
// Anti-pattern snippet, located inside transform(...):
Class<?> target = Class.forName(className.replace('/', '.'));
logger.info("Instrumenting {}", target.getName());
metricsRegistry.counter("transforms").increment();
bytecodeAnalyzer.inspect(target.getDeclaredMethods());
```

There are several different risks:

1. **`Class.forName` on the target itself** forces the loader to find/resolve the class currently being defined by the JVM. For load-time transforms, `classBeingRedefined` is usually `null` because the `Class<?>` of the new class is not yet ready in a safely usable form. The `className`, `loader`, `module`, and `classfileBuffer` are already provided by the callback; there is no need to "re-find" the target through the class loader.
2. **The first use of a logger** may load providers, formatters, service loaders, or configuration. Those newly loaded classes also pass through the transformer if not filtered out.
3. **A metrics registry** may initialize threads, locks, library classes, and I/O on first invocation.
4. **Reflection on the target** can force the JVM to resolve additional types/methods and dependencies while the target is not yet complete.
5. If the callback holds a global `synchronized` lock or calls `Future.join()`/a latch, another thread might be waiting on the very class loader that the callback is holding.

Not every logger call causes an error. The problem is that it is **hard to prove the absence of lazy class loading or lock acquisition** in complex APIs, especially once the JVM has begun defining a class.

## 4. Initializing Helpers Before Registration

The startup order should be:

```text
premain
  -> validate config/allowlist
  -> set up helper loading path on the right class loader
  -> init helpers and dependencies actually needed on the hot path
  -> create transformer, counters, guard
  -> verify ready state
  -> addTransformer(...)
```

Example snippet in `premain`:

```java
// Illustrative snippet in premain, not a standalone program.
ClassLoader agentLoader = AgentEntry.class.getClassLoader();
Class.forName("agent.ProbeHooks", true, agentLoader);
instrumentation.addTransformer(transformer);
```

The three expressions have different meanings:

| Form | Guarantees `<clinit>` initialization? |
| --- | --- |
| `ProbeHooks.class` | No |
| `Class.forName("agent.ProbeHooks", false, loader)` | Does not request initialization |
| `Class.forName("agent.ProbeHooks", true, loader)` | Yes, requests initialization if not yet initialized |

**Do not interpret "pre-initializing helpers" as "loading every class in the JVM."** Only warm up the dependencies truly needed for the transform/hook to operate. Pre-loading thousands of classes increases startup time and can also trigger unwanted side effects.

Notes:

- If a helper's static initializer needs the application to have already started, do not force it to run too early. Design the helper as a simple bridge and initialize the backend in a separate phase when conditions are met.
- Warm up on **the right loader**. A helper initialized by the system loader does not mean a class of the same name defined by a plugin loader has been initialized.
- Warming up direct dependencies may still not touch every lazy-loading branch at runtime. Therefore, you still need class filtering and minimal dependencies in the callback.
- If the helper is injected into bootstrap classes, you must ensure the helper can be resolved by the bootstrap loader; simply placing it in the system loader's agent JAR is not enough.
- If `Class.forName(..., true, ...)` fails, you should report a clear startup error and avoid registering a callback that is missing its helper.

## 5. Complete Java 17+ Example: Warm-up, Early Filtering, Same-Thread Guard

This experiment uses the standard JDK and requires no ASM. The transformer only **observes** the loading of `demo.Target` and returns `null`; the source of `Target.work()` already contains a `ProbeHooks.hit()` call to simulate the `invokestatic` result that a real transformer would insert. **This example does not perform bytecode weaving**; it focuses on initialization order and callback safety.

Structure:

```text
safe-instrumentation/
├── agent.mf
├── src/
│   ├── agent/
│   │   ├── SafeAgent.java
│   │   └── ProbeHooks.java
│   └── demo/
│       ├── Target.java
│       └── Main.java
└── out/                       # created when compiling
```

### 5.1. Helper with a Static Initializer

File `src/agent/ProbeHooks.java`:

```java
package agent;

import java.util.concurrent.atomic.AtomicInteger;

public final class ProbeHooks {
    private static final AtomicInteger HITS = new AtomicInteger();

    static {
        System.out.println("helper: initialized");
    }

    private ProbeHooks() {}

    public static void hit() {
        HITS.incrementAndGet();
    }

    public static int hits() {
        return HITS.get();
    }
}
```

The static initializer is placed here to observe **the exact moment the helper is initialized**. A production hook should keep its call path leaner, typically avoiding `System.out` printing or per-request I/O.

### 5.2. Agent That Only Tracks One Target

File `src/agent/SafeAgent.java`:

```java
package agent;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;
import java.util.concurrent.atomic.AtomicInteger;

public final class SafeAgent {
    private static volatile TargetOnlyTransformer current;

    private SafeAgent() {}

    public static void premain(String options, Instrumentation inst)
            throws ClassNotFoundException {
        System.out.println("agent: preparing");

        // Force helper initialization BEFORE any transformer callback runs.
        Class.forName("agent.ProbeHooks", true,
                SafeAgent.class.getClassLoader());

        TargetOnlyTransformer transformer = new TargetOnlyTransformer();
        transformer.prepare();
        current = transformer;

        inst.addTransformer(transformer);
        System.out.println("agent: transformer registered");
    }

    public static int targetCallbacks() {
        TargetOnlyTransformer transformer = current;
        return transformer == null ? 0 : transformer.callbacks.get();
    }

    private static final class TargetOnlyTransformer
            implements ClassFileTransformer {
        private static final ThreadLocal<Boolean> ACTIVE = new ThreadLocal<>();
        private final AtomicInteger callbacks = new AtomicInteger();

        void prepare() {
            ACTIVE.get();
            callbacks.get();
        }

        @Override
        public byte[] transform(
                Module module,
                ClassLoader loader,
                String className,
                Class<?> classBeingRedefined,
                ProtectionDomain protectionDomain,
                byte[] classfileBuffer) {

            // Do not call helpers, loggers, or guards before filtering.
            if (!"demo/Target".equals(className)) {
                return null;
            }
            // Only prevents reentrancy on the same thread.
            if (Boolean.TRUE.equals(ACTIVE.get())) {
                return null;
            }

            ACTIVE.set(Boolean.TRUE);
            try {
                callbacks.incrementAndGet();
                return null; // Observe class load, do not modify bytes.
            } finally {
                ACTIVE.remove();
            }
        }
    }
}
```

Explanation:

- `Class.forName(..., true, ...)` actually asks the JVM to initialize `ProbeHooks` before `addTransformer` runs.
- `new TargetOnlyTransformer()` and `prepare()` prepare the simple structures used in the callback.
- The `"demo/Target".equals(className)` filter runs **before** the guard/counter; the agent does not touch out-of-scope classes, including the agent's own classes and the JDK.
- `ThreadLocal<Boolean>` is used to prevent same-thread reentrant callbacks in more complex call paths. It **does not** prevent wait cycles across threads.
- `finally` cleans up the state so that an exception does not leave that thread permanently marked as "currently transforming."
- `return null` is the proper way to indicate that the transformer **did not modify bytecode**. The counter only counts callback events for the target; it does not count the number of instrumented bytecodes.

### 5.3. Target and Application

File `src/demo/Target.java`:

```java
package demo;

import agent.ProbeHooks;

public final class Target {
    public int work() {
        // Simulates a call inserted by bytecode weaving.
        ProbeHooks.hit();
        return 7;
    }
}
```

File `src/demo/Main.java`:

```java
package demo;

import agent.ProbeHooks;
import agent.SafeAgent;

public final class Main {
    public static void main(String[] args) {
        System.out.println("application: start");
        Target target = new Target();
        System.out.println("work=" + target.work());
        System.out.println("probe hits=" + ProbeHooks.hits());
        System.out.println("target callbacks=" + SafeAgent.targetCallbacks());
    }
}
```

### 5.4. Manifest, Running, and Output

File `agent.mf` (with a trailing blank line):

```text
Manifest-Version: 1.0
Premain-Class: agent.SafeAgent

```

Create the `out` directory on Linux/macOS:

```bash
mkdir -p out
```

If using Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force out | Out-Null
```

Compile and package the JAR with JDK 17+:

```bash
javac --release 17 -encoding UTF-8 -d out src/agent/ProbeHooks.java src/agent/SafeAgent.java src/demo/Target.java src/demo/Main.java
jar --create --file safe-agent.jar --manifest agent.mf -C out .
java -javaagent:safe-agent.jar -cp safe-agent.jar demo.Main
```

Expected output when running cleanly with only this agent:

```text
agent: preparing
helper: initialized
agent: transformer registered
application: start
work=7
probe hits=1
target callbacks=1
```

`helper: initialized` appears before `agent: transformer registered`: that is proof the helper was initialized before the callback became active. `target callbacks=1` shows that the target passed through the transformer once. `probe hits=1` comes from the direct call in `Target.work()` simulating inserted bytecode. These two counters measure **two different things**.

The example bundles the agent and application into one JAR using the system loader to focus on preparation order. When deploying an agent into a system with plugin class loaders/JPMS/bootstrap, you must verify the helper's own lookup path; warming up on the agent loader does not automatically fix a `NoClassDefFoundError` in the target loader.

## 6. Recursive Static Initialization Is Not Necessarily `ClassCircularityError`

According to JLS §12.4.2, when **the same thread** requests initialization of a class that it is already initializing, the JVM treats this as a reentrant request. Thus, there are cases where a static field read cycle does not produce a linkage error, but instead causes the program to read the default value before the initializer finishes.

Standalone Java 17+ example, file `InitOrderDemo.java`:

```java
public final class InitOrderDemo {
    static final class A {
        static int value = B.value + 1;
    }

    static final class B {
        static int value = A.value + 1;
    }

    public static void main(String[] args) {
        System.out.println("A=" + A.value);
        System.out.println("B=" + B.value);
    }
}
```

Run:

```bash
javac --release 17 InitOrderDemo.java
java InitOrderDemo
```

Output:

```text
A=2
B=1
```

Step-by-step explanation:
1. Accessing `A.value` causes the JVM to begin initializing `A`.
2. The expression for `A.value` needs `B.value` → the JVM initializes `B`.
3. `B.value` reads `A.value` while **the current thread itself** is initializing `A` → it sees the default value `0`.
4. `B.value = 0 + 1 = 1`; then `A.value = 1 + 1 = 2`.

The dependency cycle above **is not** a superclass hierarchy cycle. Therefore, do not conclude it is a `ClassCircularityError`. You should also avoid using this kind of dependency in helpers: the code can run while returning unexpected initialization data.

**`ClassCircularityError`** occurs when the JVM detects a superclass hierarchy cycle while loading a class. Java source with `A extends B` and `B extends A` will be rejected by the compiler; however, a transformer emitting a malformed class file or a buggy custom loader can lead to the corresponding error. Recursive resolution when a transformer tries to look up a class currently being defined again can produce another `LinkageError`, depending on context.

**`ExceptionInInitializerError`** is a different category of problem: if `<clinit>` fails due to an exception, the first use typically throws this error; subsequent uses may throw `NoClassDefFoundError: Could not initialize class ...`. You must read the **root cause** rather than concluding the JAR is missing.

## 7. Deadlock in Class Loading and Class Initialization

`ClassLoader.loadClass(String, boolean)` synchronizes by default on the result of `getClassLoadingLock(className)`. For non-**parallel-capable** loaders, the lock is usually the loader object itself; for loaders supporting parallel class loading, the JVM/loader can use a per-class-name lock to increase concurrency.

Consider a custom loader with cross-delegation:

```text
Thread T1                               Thread T2
---------------------------------       ---------------------------------
Holds loading lock of loader A          Holds loading lock of loader B
loading ClassA                          loading ClassB
-> transformer A needs dependency B     -> initializer B needs dependency A
-> waits for loader B                   -> waits for loader A
                \                        /
                 \---- wait cycle ------/
```

This is a **risk model**, not a guaranteed outcome for every `ClassLoader`. Lock ordering, delegation policy, and the moment the JVM needs to resolve classes determine whether an actual wait cycle forms.

Deadlocks also occur when **two threads initialize two classes**: T1 is initializing helper A and waits for B held by T2; T2 is initializing B and waits for A held by T1. The JLS's **same-thread** reentrancy rule does not eliminate wait cycles across multiple threads.

Appropriate safeguards:
- Do not call `Future.get()`, `CompletableFuture.join()`, latches/blocking I/O, or wait for a worker thread inside `transform`.
- Do not wrap the entire callback in a global monitor inside which additional classes continue to be loaded.
- Do not call `Class.forName(targetName)`/reflection on the target inside a load-time callback.
- Keep lock ordering and class loader delegation consistent if you own a custom loader.
- Consider `ClassLoader.registerAsParallelCapable()` when implementing a non-hierarchical loader and ensure you fully understand its contract; it is **not a cure-all for every deadlock**.

## 8. Preloaded Helpers Must Still Match the Right Class Loader

Suppose an agent loads `agent.ProbeHooks` with the system loader and then injects the instruction:

```text
invokestatic agent/ProbeHooks.hit:()V
```

into a JDK class defined by the **bootstrap loader**. The JVM resolves symbolic references using the **target class's** loader and linkage rules, rather than automatically falling back to the loader that ran the transformer. Thus, a helper initialized by the system loader does not mean a bootstrap target can invoke the helper. The runtime must also check JPMS access if a named module is involved.

Corresponding options:

| Target | Approach |
| --- | --- |
| Target and agent on the same system loader, sufficient delegation | Helper can reside in the agent JAR; warm up on the system loader before registration |
| Target belongs to bootstrap | Minimal helper JAR on the bootstrap search path via `appendToBootstrapClassLoaderSearch` before target use; warm up the bootstrap definition |
| Isolated plugin class loader | Provide the helper in the appropriate loader or a visible bridge; verify class identity and dependencies |
| Target in a named module | Evaluate class visibility, read edges, package exports, and method access separately |

For a bootstrap bridge, do not put the entire bytecode library, logger, HTTP client, and application dependencies onto the bootstrap classpath for "easy lookup." A thin helper using bootstrap-visible APIs that forwards to a prepared dispatcher through a controlled mechanism reduces the risk of creating class-loading cycles.

## 9. Safe Callback Design and Error Policy

A callback in a real system should be designed in the following order:

```text
transform(module, loader, className, bytes)
    |
    +-- className is null or outside allowlist? -> return null
    |
    +-- agent/helper/library class? -> return null
    |
    +-- same-thread reentrancy guard active? -> return null
    |
    +-- process bytecode using only input arguments
    |
    +-- produce valid new byte[], or return null
    |
    +-- clean up guard in finally
```

**Run the allowlist before anything expensive.** If the callback is invoked for thousands of JDK and framework classes, many uninitialized helper/counter/logging classes can also be touched. Early filtering avoids expanding the blast radius.

If you need to use ASM or Byte Buddy, initialize the necessary core classes outside the callback when possible. Avoid calling the target's loader to "check" the current class. If you need to inspect methods, read from `classfileBuffer`; for a class being loaded, those bytes are the exact data the JVM passed to the transformer.

Regarding exceptions, the `ClassFileTransformer` Javadoc states that an uncaught exception escaping `transform` **does not automatically abort** the remaining transformers or the overall load process. It can be treated similarly to `return null` for that transformer. Therefore:
- Report errors via pre-prepared counters/telemetry; avoid initializing a new logger right in the error path.
- Distinguish `callback_seen`, `transform_attempted`, `bytes_returned`, `target_loaded`, and `probe_executed`.
- Have a fail-open/fail-closed policy matching observability requirements, avoiding treating "no exception seen" as success.
- Do not swallow severe errors such as `OutOfMemoryError` and report that the system is still healthy.

`removeTransformer` stops future callbacks; it does not automatically remove bytecode previously injected into classes. If you design a stop capability, you need a valid retransformation mechanism or a hard/soft toggle built in from the start.

## 10. Diagnosing JVM Hangs or Linkage Errors

### 10.1. Facts to Collect

Record the JVM vendor/version, agent manifest, `-javaagent` ordering, target loader/module, name of the class being transformed, helper init timing, config version, callback count, and the first root-cause stack trace.

Do not read only the last exception: a resolution error caused by a callback can resurface later when the application touches the related symbolic reference.

### 10.2. Thread Dumps and Class Loading Logs

If the JVM is still running, inspect threads using the JDK:

```bash
jcmd PID Thread.print -l
```

Or:

```bash
jstack -l PID
```

Replace `PID` with the actual process ID. Look for threads with stacks containing `ClassLoader.loadClass`, `getClassLoadingLock`, `<clinit>`, `ClassFileTransformer.transform`, `Future.get`, waiting monitors, and provider/logger methods. Distinguish `BLOCKED`, `WAITING`, and native stacks. Automatic deadlock detectors may miss some wait patterns in class initialization/native runtime; **a thread dump is evidence for analysis**, not a substitute for reasoning about locks.

During testing, you can enable class loading logs:

```bash
java -Xlog:class+load=info -javaagent:safe-agent.jar -cp safe-agent.jar demo.Main
```

The log can be very verbose and does not directly show all locks, but it helps observe which classes are loaded unexpectedly around the time the transformer is active.

### 10.3. Symptoms and Troubleshooting

| Symptom | What to check |
| --- | --- |
| `ClassCircularityError` | Superclass hierarchy of the new class file, byte structure, loader defining the class |
| Other `LinkageError` inside/outside transformer | Recursive resolution, class identity, constraints, classfile, and root cause |
| `ExceptionInInitializerError` | Static initializer of helper/dependency, underlying cause |
| `NoClassDefFoundError: Could not initialize class` | A previous initialization failed; the class is in an erroneous state |
| `NoClassDefFoundError` for helper | Target loader cannot resolve the helper/dependency |
| Thread stuck at `ClassLoader.loadClass` | Loading lock, cross-delegation, callback requesting a dependency |
| Thread stuck at `<clinit>` | Static initialization lock or cross-thread dependency |
| Spike in callbacks | Broad filter, helper/library also being instrumented, recursive load |
| Probe enabled but no hits | Callback not matching, transform returning `null`, error being masked, or wrong loader/helper |

## 11. Testing and Production Rollout Process

1. **Design the dependency graph:** list the transformer, helper, bytecode engine, logger, metrics, and the loader containing each class. Eliminate reverse dependency paths into the instrumented application.
2. **Prepare safely in `premain`:** config, allowlist, required helper-only JARs, initialize helpers and essential hot paths before registering the transformer.
3. **Observation phase:** register a callback that only reads `className`, returns `null`, and injects no bytes. Check callback counts and thread dumps if any waiting occurs.
4. **Single-target phase:** instrument exactly one class/method with a known loader/module and real code path; verify helper loadability, invocation, bytecode verifier, and latency.
5. **Add guards and error handling:** same-thread reentrancy guard, lightweight counters, `finally` cleanup; do not assume a guard solves cross-thread deadlocks.
6. **Bounded expansion:** grow the allowlist in batches, measuring application p95/p99, transform counts, load times, linkage errors, and warm-up duration.
7. **Concurrent load testing:** multiple threads loading classes simultaneously, plugin loaders, or non-hierarchical delegation; verify no lock waiting or abnormal reentrancy.
8. **Have a kill switch:** configuration allowing new transforms to stop and hooks to be removed via a valid mechanism when the capability exists; do not expect `removeTransformer` to fix already-loaded classes on its own.
9. **Record the environment:** test on the target JDK/vendor/version; specific loader and dependency behaviors can differ across containers/frameworks.

## 12. Self-Check Questions

1. Why should `Class.forName("agent.ProbeHooks", true, agentLoader)` be executed before `addTransformer`?
2. What is the difference between `ProbeHooks.class`, `Class.forName(..., false, ...)`, and `Class.forName(..., true, ...)`?
3. Why should you not call `Class.forName` on **the class currently being transformed**?
4. Why does recursive class loading not always produce `ClassCircularityError`? What structure does this error relate to?
5. Why does the `InitOrderDemo` example produce `A=2`, `B=1` without encountering class circularity?
6. What does a `ThreadLocal<Boolean>` guard help with, and what does it **not** help with when two threads mutually hold loader locks?
7. How can you verify that a helper was initialized before the transformer was registered?
8. Why does `target callbacks=1` in the example not prove that the target's bytecode was modified?
9. If injecting a helper into a class defined by the bootstrap loader, what other issue must be solved besides warm-up?
10. When an application hangs without throwing an exception, how can you use a thread dump to find a wait cycle and distinguish a class loader issue from static initialization?

## 13. References

- [Java SE 21 — `ClassFileTransformer`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): transformer runs before the class is defined, `null`, and exception rules.
- [Java SE 21 — `Instrumentation`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `addTransformer`, `retransformClasses`, `removeTransformer`.
- [Java SE 21 — `java.lang.instrument`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): `premain`, agent JAR, and how the JVM starts an agent.
- [Java SE 21 — `ClassLoader`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): `getClassLoadingLock`, delegation, parallel-capable.
- [Java SE 21 — `ClassCircularityError`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassCircularityError.html): superclass hierarchy cycles.
- [Java SE 21 — `ExceptionInInitializerError`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ExceptionInInitializerError.html): errors in static initializers.
- [Java Language Specification 21 — §12.4.2](https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html#jls-12.4.2): same-thread initialization reentrancy and waiting when a class is being initialized by another thread.
