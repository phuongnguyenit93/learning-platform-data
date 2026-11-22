# Limiting Allocation, Bytecode Parsing, and Logging in the `ClassFileTransformer` Callback

## 1. Why Is the Callback a Performance-Sensitive Location?

When a Java agent registers a `ClassFileTransformer`, the JVM may invoke `transform(...)` for **a large number of class definitions** during startup or dynamic class loading. The transformer can also participate in `redefineClasses` or `retransformClasses` depending on capabilities. The JVM must process the callback's result before completing the corresponding class definition/update path: synchronous work inside the callback can therefore add directly to class loading latency, startup time, hot deploy, or class updates.

A callback that only adds a few cheap checks is usually negligible. However, if **every class** has to:

- Instantiate a `ClassReader`/`ClassWriter`, parse the constant pool and all method instructions;
- Clone the `classfileBuffer` array even when nothing is actually changed;
- Concatenate log strings, capture stack traces, and write to `System.out`/file/network;
- Invoke reflection or `Class.forName` to retrieve metadata;
- Wait on a synchronized logger, global lock, cache, or full queue;
- Retain `Class<?>`, `ClassLoader`, or full byte arrays in an unbounded cache;

then the overhead can accumulate across **thousands or tens of thousands of callback invocations**, driving up allocation, GC, and contention. Worse, the transformer can trigger recursive class loading or deadlock right on the JVM's class loading path.

**Learning objective:** build the callback along the pipeline **cheap filter → parse only on match → create output only when changed → return `null` on no-op → emit logs outside the callback**. At the same time, handle concurrent invocations, reentrancy, error policy, object lifetime, and accurate measurement.

This lesson belongs to **Concurrency and Performance**, applying Java Instrumentation on **JDK 17+**. The end-of-lesson example compiles and runs on JDK 17 with no external libraries required.

## 2. The API Contract Before Optimizing

### 2.1. Two Overloads of `ClassFileTransformer`

In Java 17, the callback has a legacy 5-parameter form:

```java
default byte[] transform(
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        ProtectionDomain protectionDomain,
        byte[] classfileBuffer);
```

and a Java 9+ form with an additional `Module`:

```java
default byte[] transform(
        Module module,
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        ProtectionDomain protectionDomain,
        byte[] classfileBuffer);
```

These are illustrative signatures requiring `import java.security.ProtectionDomain`. Because both overloads have default implementations, `ClassFileTransformer` is not a functional interface; use a class or an anonymous class overriding the method, **do not use a lambda** for this interface on JDK 17.

Key inputs:

- `className`: JVM internal name, e.g. `com/example/Service`; in some special callbacks it can be `null`.
- `module`: the module of the class being transformed, not the agent's module.
- `loader`: the **defining class loader**; `null` for the bootstrap loader.
- `classBeingRedefined`: `null` on new class load; non-`null` for redefine **and** retransform.
- `classfileBuffer`: current bytes in the transformer chain; **do not modify this array directly**.

The condition `classBeingRedefined != null` does **not** by itself distinguish redefine from retransform. On retransform, a transformer with `canRetransform=false` may have its previous output reapplied by the JVM without invoking the callback again; when counting phases, you must understand registration lifecycle.

### 2.2. `return null` Is the Standard No-Op

A proper fast-path pattern:

```java
@Override
public byte[] transform(
        Module module,
        ClassLoader loader,
        String className,
        Class<?> redef,
        ProtectionDomain domain,
        byte[] bytes) {

    if (!"demo/Target".equals(className)) {
        return null;
    }

    return rewriteSelectedClass(bytes);
}
```

This is an **illustrative snippet**, as `rewriteSelectedClass` is not defined; the full Java 17 example section below provides all runnable files.

According to the API contract:

- Return `null` if **no transformation is performed**. The JVM will use the current input as the effective output.
- If modifying, return a **new `byte[]` array containing a valid class file**.
- Do not mutate `classfileBuffer` in place.
- Do not return an empty array `new byte[0]` to signal a no-op.
- If a transformer throws an exception, other transformers are still invoked per the contract; an exception does not guarantee that class loading is blocked.
- Output during redefine/retransform must comply with JVMTI limits on modifying an already-loaded class.

**Performance implication:** for unrelated classes or when no changes are needed, returning `null` avoids copying the classfile as well as unnecessary writer/serialization work.

## 3. Breaking Down Cost by Stage

```text
JVM -> transform(...)
        |
        v
 [1] check name/module/loader + policy
        |
        +---- no match --------------> return null
        |
        v
 [2] reentrancy guard if needed
        |
        v
 [3] parse required bytes/metadata
        |
        +---- no change needed ------> return null
        |
        v
 [4] allocate new byte[] / writer
        |
        v
 [5] valid rewrite; update lightweight metric
        |
        v
 return new byte[]
        |
        v
 Export metrics/logs via ANOTHER path outside callback
```

Different cost sources behave differently:

| Category | Source of overhead | Strategy |
| --- | --- | --- |
| Allocation | Cloning `byte[]`, parser/visitor, strings, logger events | Conditional instantiation, `null` no-op, lifecycle-bounded cache |
| CPU | Walking constant pool/method instructions, computing frames | Early filtering, parse only as deep as needed, benchmark |
| Latency | File/network/console I/O, locks, full queues | Non-blocking callback, bounded export |
| Class loading | Reflection, logger initialization, helper class dependencies | Warm up helpers, no `Class.forName` in callback |
| Concurrency | Shared mutable parser, global `synchronized` | Per-call local state, immutable config, thread-safe counters |
| Retention | Unbounded `Class<?>`/`ClassLoader`/`byte[]` cache | Bounded cache, eviction, appropriate weak-key policy |
| Correctness | Corrupted bytes, invalid frames, duplicate hook insertion | Verify, immutable input, test idempotence |

**There is no default time/allocation limit in the Java SE Javadoc.** Each product must set its own budget based on startup SLO, class count, classfile size distribution, agent ownership, JVM, and acceptable overhead.

### 3.1. Why Does the Fast Path Matter?

Suppose only 1 out of 1,000 classes matches a rule. If you create a reader for all 1,000 classes before filtering, 999 useless parsers still run. If you check `"demo/Target".equals(className)` first, most callbacks finish without inspecting a single byte.

The 1/1,000 ratio is only an **illustrative example**, not a metric from any specific JVM. Yet the principle holds: **optimize the common path before optimizing the rare path**.

If a policy requires filtering by annotation, metadata must be read, but you can still pre-filter by package/module/class loader first and then visit only the required attributes. There is no need to walk method instructions or recompute stack maps just to check an annotation.

## 4. Limiting Allocations in the Callback

### 4.1. Avoidable Allocations

Anti-patterns:

```java
// Wrong when changing nothing: clones the entire byte array on every callback.
return classfileBuffer.clone();

// Wrong: builds strings even when debug logging is unnecessary.
String message = "Inspecting " + className
        + " loader=" + loader;
logDebug(message);

// Wrong if called every time: parses all bytecode before filtering.
Reader reader = new Reader(classfileBuffer);
if (!wanted(className)) {
    return null;
}
```

This is **pseudo-code**; the symbols `logDebug`, `Reader`, and `wanted` are undefined. It only illustrates unnecessary overhead patterns.

A better version in terms of decision flow:

```java
if (!wanted(className)) {
    return null;
}

if (!requiresChange(classfileBuffer)) {
    return null;
}

// Allocate output only on the modifying branch.
byte[] output = classfileBuffer.clone();
applyChange(output);
return output;
```

This is also **pseudo-code** without a concrete parser/writer. In real bytecode, changing lengths, the constant pool, instruction offsets, or frames requires a library that understands JVM structure; **do not patch raw offsets arbitrarily**.

### 4.2. Choosing What Data to Cache

You can reuse **immutable configuration**, compiled matchers, sets of method names, rule versions, descriptors, and per-class-independent metadata. Still, be careful:

- Do not retain `classfileBuffer` from every callback just to "possibly debug later."
- Do not share a single mutable `ClassReader`/`ClassWriter` instance across multiple threads if the implementation is not thread-safe.
- Do not store `ClassLoader` or `Class<?>` as strong keys in an unbounded static cache, as that can cause a classloader leak.
- Do not use `className` alone to identify a class when multiple loaders can define the same binary name.
- Do not cache incomplete or stale results across redefinition/retransformation.

If per-class metadata must be kept, consider `ClassValue`, weak keys, or a cache tied to plugin/module lifecycle, while verifying that **values do not hold back-references to the loader**, thread safety, and invalidation policy.

### 4.3. Counters Do Not Necessarily Produce Zero Allocations

`LongAdder` generally performs well under multi-threaded updates, but as contention rises it can allocate internal `Cell` structures. `ThreadLocal` can also allocate entries when first used on a thread.

The right goal is to **avoid unnecessary allocations on the common path**, not to promise "zero allocation" when the JVM, JIT, counters, and libraries can still allocate based on state.

## 5. Limiting Bytecode Parsing

### 5.1. How Deep Do You Need to Parse?

| Requirement | What needs to be read? | Full instruction walk? |
| --- | --- | --- |
| Filter by class name | Callback `className` | No |
| Filter by module/defining loader | Callback `module`/`loader` | No |
| Filter by class-file version | Class file header | No |
| Inspect list of method signatures | Class/method metadata | Not necessarily |
| Check annotations | Attributes/metadata | Not necessarily |
| Insert method-entry advice | Code attributes, instructions | Yes |
| Cover exceptional exits | Control flow + exception table | Yes |
| Generate/recompute stack maps | Control flow and hierarchy | May require deep analysis |

In Java 17, use a bytecode library such as ASM or Byte Buddy for complex rewriting. The Java Class-File API `java.lang.classfile` was standardized in **JDK 24** and is not available in JDK 17.

### 5.2. Avoiding Unintended Class Loading

A classic mistake:

```java
// Anti-pattern inside transform for a class not yet defined:
Class<?> target = Class.forName(
        className.replace('/', '.'),
        false,
        loader);
```

This code can trigger loading/linking (even with `initialize=false`), load the wrong class via another loader, or cause recursion while the target itself is being defined. Instead, use the callback's module/name/loader and classfile metadata; if a hierarchy is needed to compute frames, use a controlled classfile/resolver source.

**Do not use reflection just to check if a class has an annotation** when a classfile parser can read annotation attributes without defining the class into the JVM.

### 5.3. Parsing Limits and Time Budgets

If input is untrusted or has unusual classfiles, the parser must validate length/magic, constant-pool tags, offsets, and memory limits before large allocations. Do not treat the simplified parser example in this lesson as a tool for reading arbitrary classfiles.

A soft time budget can help an agent observe slow parsers, but the JVM **has no mechanism to safely abort a callback mid-execution upon a deadline**. When deciding to skip, stop in a state where you can still return `null` or a **complete** output; never return a partially rewritten byte array.

## 6. Limiting Logging in the Callback

### 6.1. Why Can `System.out.println` Cause Slowdowns and Recursion?

```java
System.out.println(
        "Transforming " + className + ", loader=" + loader);
```

In a callback invoked for many classes, this line can:

- Allocate strings/string builders and call a custom `loader.toString()`.
- Write synchronously to a `PrintStream`; the terminal/file can block or experience backpressure.
- Load additional logger formatters, appenders, and helper classes during class loading.
- Cause lock inversion with a class loader lock currently held.
- Cause a log storm, consuming disk/network and increasing the agent's footprint.

A logger set to level OFF **does not eliminate the cost** if the message is already formatted before `isDebugEnabled()`.

### 6.2. Recommended Logging Model

**Inside the callback:** keep only counters or minimal selected events, without constructing long messages.

**Outside the callback:** an agent management thread or scheduled exporter aggregates counters, applies rate-limiting, and prints logs.

Example:

```java
private static final java.util.concurrent.atomic.LongAdder CHANGED =
        new java.util.concurrent.atomic.LongAdder();

// Inside the callback, after actually modifying bytes:
CHANGED.increment();

// Outside the callback, at report export time:
String summary = "changed=" + CHANGED.sum();
```

These are **illustrative snippets**, not a standalone class. `LongAdder.sum()` is suitable for metrics, though it is not a linearizable atomic snapshot while threads are still updating it.

If specific errors must be logged, use a **bounded queue**, sampling, or rate limiting. When the queue is full, apply a **drop/coalesce** policy—never `BlockingQueue.put`, which can block indefinitely from inside the callback. Also account for the cost of allocating event objects and enqueuing them.

### 6.3. Preventing Logging Recursion

A logger initialized for the first time inside `transform` can load many helper classes; each helper class in turn triggers the transformer. Ways to reduce the risk:

1. Initialize required helpers and the logging backend outside the callback, during `premain` if appropriate.
2. Do not instrument the agent's or logger's own packages unless explicitly intended.
3. Filter by class before any logging.
4. Attach a reentrancy guard **after the filter** when truly needed.
5. Do not log unbounded stack traces inside `catch`; count errors and handle them according to the fail policy.

Do not promise that preloading all helpers will completely eliminate recursion: class loader/module/dependency graphs and other agents can still interact.

## 7. Concurrency and Shared State

### 7.1. Callbacks Must Not Assume Single-Threaded Execution

Class loading can occur across multiple threads. One transformer instance can process multiple classes concurrently; shared mutable state must be designed safely:

- Avoid `synchronized transform(...)`, because it serializes the class loading path and can increase deadlock risk.
- Do not store `byte[] currentBuffer` or a mutable parser in a shared static field.
- Use local variables for each invocation's bytecode visitor, buffer, and output.
- Swap configuration via an **immutable snapshot** and `volatile` or `AtomicReference` if the agent has dynamic policies.
- Use only thread-safe counters or bounded queues.
- If caching per class, clearly scope by loader/module namespace and version.

The `Instrumentation.removeTransformer` Javadoc also notes: a transformer **may still receive callbacks after being removed** due to concurrent class loading. Therefore, callbacks must not access closed resources without lifecycle protection.

### 7.2. Scoped `ThreadLocal` Guard

A basic guard:

```java
private static final ThreadLocal<Boolean> ACTIVE =
        new ThreadLocal<>();

static boolean enter() {
    if (Boolean.TRUE.equals(ACTIVE.get())) {
        return false;
    }
    ACTIVE.set(Boolean.TRUE);
    return true;
}

static void leave() {
    ACTIVE.remove();
}
```

Illustrative snippet, not a standalone Java class. Once `enter()` succeeds, call `leave()` in `finally`. The guard prevents **same-thread** reentry; it does not resolve dependency cycles across multiple threads or global locks.

`ThreadLocal` carries per-thread overhead and can retain values too long if `remove()` is forgotten. Do not store plugin objects or classloaders in a `ThreadLocal` attached to long-lived executor threads.

## 8. Java 17 Demo: Early Filtering, Conditional Cloning, Out-of-Callback Logging

The demo uses exactly **one Java agent** and **one target class**. The agent only patches a 6-byte UTF8 constant-pool literal:

```text
"ORIGIN" -> "PATCH!"
```

Both strings consist of 6 ASCII bytes, so the example can replace bytes inside `CONSTANT_Utf8` **without changing entry length or offsets**. This is an exercise illustrating allocation strategy, not a general-purpose bytecode patcher. To insert method-entry advice, use ASM/Byte Buddy with a verifier/frames.

### 8.1. Structure

```text
fast-callback/
├── PerfAgent.java
├── FastTransformer.java
├── TargetService.java
├── DemoApp.java
└── agent.mf
```

All Java sources live in the default package for ease of execution; the target is loaded from the app JAR after `premain` registers the transformer.

### 8.2. `PerfAgent.java`

```java
import java.lang.instrument.Instrumentation;

public final class PerfAgent {
    private PerfAgent() {
    }

    public static void premain(String args, Instrumentation inst) {
        // Initialize classes, counters, and guard before the target loads.
        inst.addTransformer(new FastTransformer(), false);
    }

    public static String metrics() {
        // Do not build strings inside the callback.
        return FastTransformer.metrics();
    }
}
```

### 8.3. `FastTransformer.java`

```java
import java.lang.instrument.ClassFileTransformer;
import java.nio.charset.StandardCharsets;
import java.security.ProtectionDomain;
import java.util.concurrent.atomic.LongAdder;

public final class FastTransformer implements ClassFileTransformer {
    private static final byte[] OLD =
            "ORIGIN".getBytes(StandardCharsets.US_ASCII);
    private static final byte[] NEW =
            "PATCH!".getBytes(StandardCharsets.US_ASCII);

    private static final LongAdder MATCHED = new LongAdder();
    private static final LongAdder CHANGED = new LongAdder();
    private static final LongAdder NO_OP = new LongAdder();
    private static final LongAdder FAILED = new LongAdder();
    private static final LongAdder TOTAL_NANOS = new LongAdder();

    // Only used on the branch where the class matches the filter.
    private static final ThreadLocal<Boolean> ACTIVE =
            new ThreadLocal<>();

    @Override
    public byte[] transform(
            Module module,
            ClassLoader loader,
            String className,
            Class<?> classBeingRedefined,
            ProtectionDomain domain,
            byte[] classfileBuffer) {

        // Fast path: do not touch bytes, timer, logger, or ThreadLocal.
        if (!"TargetService".equals(className)
                || classBeingRedefined != null) {
            return null;
        }

        MATCHED.increment();

        if (Boolean.TRUE.equals(ACTIVE.get())) {
            NO_OP.increment();
            return null;
        }

        ACTIVE.set(Boolean.TRUE);
        long start = System.nanoTime();

        try {
            byte[] changed = patch(classfileBuffer);
            if (changed == null) {
                NO_OP.increment();
                return null;
            }

            CHANGED.increment();
            return changed;
        } catch (RuntimeException error) {
            // Fail-open for demo; production requires a clear policy.
            FAILED.increment();
            return null;
        } finally {
            TOTAL_NANOS.add(System.nanoTime() - start);
            ACTIVE.remove();
        }
    }

    private static byte[] patch(byte[] input) {
        if (input.length < 10
                || (input[0] & 255) != 0xCA
                || (input[1] & 255) != 0xFE
                || (input[2] & 255) != 0xBA
                || (input[3] & 255) != 0xBE) {
            throw new IllegalArgumentException("Invalid class file");
        }

        int constantPoolCount = u2(input, 8);
        int p = 10;
        byte[] result = null;

        for (int i = 1; i < constantPoolCount; i++) {
            int tag = input[p++] & 255;

            switch (tag) {
                case 1 -> { // CONSTANT_Utf8
                    int n = u2(input, p);
                    p += 2;

                    if (n == OLD.length && equalsAt(input, p, OLD)) {
                        // A new array is allocated only when an actual edit occurs.
                        if (result == null) {
                            result = input.clone();
                        }
                        System.arraycopy(NEW, 0, result, p, NEW.length);
                    }
                    p += n;
                }
                case 3, 4, 9, 10, 11, 12, 17, 18 -> p += 4;
                case 5, 6 -> { // Long/Double occupy 2 indices.
                    p += 8;
                    i++;
                }
                case 7, 8, 16, 19, 20 -> p += 2;
                case 15 -> p += 3;
                default -> throw new IllegalArgumentException(
                        "Unsupported constant pool tag: " + tag);
            }
        }
        return result; // null = no changes.
    }

    private static int u2(byte[] bytes, int at) {
        return ((bytes[at] & 255) << 8)
                | (bytes[at + 1] & 255);
    }

    private static boolean equalsAt(
            byte[] bytes, int at, byte[] pattern) {
        for (int i = 0; i < pattern.length; i++) {
            if (bytes[at + i] != pattern[i]) {
                return false;
            }
        }
        return true;
    }

    static String metrics() {
        return "[agent] matched=" + MATCHED.sum()
                + " changed=" + CHANGED.sum()
                + " noOp=" + NO_OP.sum()
                + " failed=" + FAILED.sum();
    }

    static long totalTransformNanos() {
        return TOTAL_NANOS.sum();
    }
}
```

**What is right about the code's performance and API usage:**

1. Non-target classes go straight to `return null`: no cloning, parsing, logging, timing, or touching `ThreadLocal`.
2. Counters, constant arrays, and the guard are initialized when `FastTransformer` is initialized during `premain`, not recreated per target.
3. Only the target branch walks the constant pool. When a literal to patch is found, one `input.clone()` is created and the original input is not mutated.
4. If the target already contains `PATCH!` and no longer has `ORIGIN`, `patch` returns `null`; the effect is a no-op.
5. `TOTAL_NANOS` records only the duration from after the filter/guard to `finally`. It does **not** measure total JVM class load/verification or the overhead of non-target fast paths.
6. `ThreadLocal` always calls `remove()` in `finally`, avoiding long-lived entries on the thread; the guard protects only the same thread.
7. `metrics()` builds the string **after the callback**, not directly on the transform path.
8. `FAILED` records parser errors via `RuntimeException` and the demo returns `null`; other errors or security-critical policies require dedicated handling.

**Important limitation:** the parser is only sufficient for valid `javac --release 17` class files in the demo; it does not check all bounds/constant-pool semantics and must not be used for arbitrary data. Production code must use a standard bytecode library, verify outputs, and check JVM/classfile versions.

### 8.4. `TargetService.java`

```java
public final class TargetService {
    private TargetService() {
    }

    public static String value() {
        return "ORIGIN";
    }
}
```

This literal appears in the constant pool, and the agent replaces the exact 6 ASCII bytes with `PATCH!`.

### 8.5. `DemoApp.java`

```java
public final class DemoApp {
    private DemoApp() {
    }

    public static void main(String[] args) {
        // Load target after premain has registered the transformer.
        System.out.println("[app] value=" + TargetService.value());

        // Only here do we build and print the log/metrics string.
        System.out.println(PerfAgent.metrics());
    }
}
```

### 8.6. `agent.mf`

```text
Manifest-Version: 1.0
Premain-Class: PerfAgent

```

This is the agent JAR manifest. A trailing blank line is required to terminate the main section; the demo does not use retransform/redefine, so `Can-Retransform-Classes` or `Can-Redefine-Classes` is not needed.

### 8.7. Running on Linux/macOS/WSL (POSIX)

Open a terminal in the `fast-callback/` directory:

```bash
mkdir -p out

javac --release 17 -d out \
  PerfAgent.java FastTransformer.java TargetService.java DemoApp.java

jar --create --file perf-agent.jar --manifest agent.mf \
  -C out PerfAgent.class -C out FastTransformer.class

jar --create --file app.jar \
  -C out DemoApp.class -C out TargetService.class

java -javaagent:perf-agent.jar \
  -cp "perf-agent.jar:app.jar" DemoApp
```

**Expected stdout**:

```text
[app] value=PATCH!
[agent] matched=1 changed=1 noOp=0 failed=0
```

These are the stable demo values when a normal JVM defines `TargetService` once and no other agent interferes. `TOTAL_NANOS` is not printed because nanosecond values depend on the JVM/JIT/host. In environments with multiple agents or custom loaders, counters may differ depending on actual callback counts.

If you omit `-javaagent:perf-agent.jar` while keeping the agent JAR on the classpath, `TargetService.value()` returns `ORIGIN`; counters from `FastTransformer` can be read, but since no transformations occurred, all of them are 0.

### 8.8. Windows PowerShell

```powershell
New-Item -ItemType Directory -Force out | Out-Null

javac --release 17 -d out PerfAgent.java FastTransformer.java TargetService.java DemoApp.java
jar --create --file perf-agent.jar --manifest agent.mf -C out PerfAgent.class -C out FastTransformer.class
jar --create --file app.jar -C out DemoApp.class -C out TargetService.class

java -javaagent:perf-agent.jar -cp "perf-agent.jar;app.jar" DemoApp
```

Windows uses `;` in the classpath, while POSIX uses `:`.

### 8.9. Verifying Demo Properties

- **Right target:** only `className = "TargetService"` and initial class load are processed.
- **Immutable input:** `input` is not modified; non-`null` output is created via clone.
- **No clone on no-op:** `patch(input)` returns `null` if `ORIGIN` is not found.
- **Deterministic:** given the same input bytes in the demo and the same rule, patching yields the same output.
- **Repeat-safe:** passing the patched output through `patch` again finds no old literal, so the effective output remains unchanged.
- **Error reporting:** on parser `RuntimeException`, it increments the counter and returns `null`, without printing stack traces inside the callback.
- **No hot-path logging:** the `[agent] ...` string is built after the target method completes.
- **Does not solve everything:** does not demonstrate ASM advice/frame recomputation, nor does it prove zero allocations across all JVM class loading.

## 9. Measuring Overhead Properly

### 9.1. Separating Measurement Layers

Distinguish between:

1. **Callback exposure**: number of times the JVM invokes the transformer, including no-ops.
2. **Rule match**: number of callbacks matching the filter.
3. **Parse/transform time**: CPU and allocation only for classes matching the rule.
4. **JVM define/verify**: VM cost after receiving output bytes.
5. **Runtime probe overhead**: cost of injected hooks when the method is called repeatedly by the application.
6. **Logging/export**: sink cost outside the callback.

A timer inside the callback does **not** measure total startup time and does **not** measure runtime method advice overhead. If you call `System.nanoTime()` in every callback for every class, the timer itself adds overhead. Measure only when needed, via sampling, or only on matched classes.

### 9.2. Minimum Benchmark Matrix

| Variant | What to measure | What to keep constant |
| --- | --- | --- |
| JVM without agent | Baseline startup and class loading | JDK, app, options |
| Fast no-op agent | Registration/filter cost | Same set of classes |
| Parse-only agent | Bytecode reader cost | Same classfile fixtures |
| Rewrite agent | Added allocation/writer/frame cost | Same rule/target output |
| Per-class logging agent | Diagnostic cost (control anti-pattern) | Same log sink and volume |
| Aggregate logging agent | Counters/export cost | Same telemetry cadence |
| Concurrent plugin/class loading | Contention, throughput, p99 latency | Loaders, threads, hardware |

Single measurements can be skewed by JIT warm-up, disk cache, GC, class loader topology, logging sinks, and background workloads. Run multiple iterations, analyze distributions, and observe **allocations, GC pauses, CPU, startup latency, and tail latency**, not just nanoseconds of a single callback.

### 9.3. Observation Tools

- **JFR:** class loading, allocation, CPU, and GC events per recording configuration.
- **JVM unified logging:** class loading/GC logs when investigating; enable selectively because logging also introduces overhead.
- **Async-profiler or equivalent profiler:** CPU/allocation hotspots under real runtime workloads.
- **JMH:** benchmark standalone parse/transform algorithms after warm-up, though integration benchmarks are still needed for real class loading impact.
- **Heap dump/classloader diagnostics:** locate caches retaining `Class<?>`, `ClassLoader`, or output `byte[]` long-term.

Do not measure `Instrumentation.getObjectSize(classfileBuffer)` and call it the total cost of instrumentation: that method only estimates an object's shallow size, not CPU, GC, or Metaspace.

## 10. Errors and Fail-Open/Fail-Closed Policies

In a typical observability agent, a failing parser may choose `return null` to avoid breaking the application. The example uses `catch (RuntimeException)` and only increments `FAILED`. However, for a security-enforcement agent, skipping instrumentation may be unacceptable: you need an explicit policy, failure-mode tests, and alerting managed outside the callback.

Do not use `throw new IllegalClassFormatException(...)` as a "guaranteed switch to reject a class": the Javadoc states that transformer exceptions are handled along the chain and do not guarantee load/redefine cancellation. Do not abuse `catch (Throwable)` to swallow `OutOfMemoryError`, `ThreadDeath`, or other critical VM errors.

If full error diagnostics are needed, capture a short bounded event inside the callback (if resources permit), then process/format the log later. Do not call `error.printStackTrace()` directly on the class loading path.

## 11. Verifying Correctness Under Repeated Callbacks

A fast transformer that keeps adding another hook on every pass can still degrade the application over time.

- **Deterministic:** same classfile bytes + same policy snapshot → same effective output.
- **Idempotent if required:** re-processing the output does not add unintended hooks, fields, methods, or wrappers.
- **Repeat-safe:** counters/caches/lifecycle do not cause incorrect double-counting or unbounded resource retention.
- **Composable:** multiple transformers run in order; the previous output becomes the next input. Two individually idempotent transformers do not guarantee an idempotent pipeline.
- **Class loader aware:** the same binary name from two loaders is not necessarily the same class identity.

`retransformClasses` does not necessarily pass a transformer's own previous output as input to a new callback; the JVM uses base bytes and reuse rules for `canRetransform=false` transformers. Therefore, to test `T(T(B)) = T(B)`, write a unit test **calling the pure algorithm on its own output**, and supplement with JVM integration tests for retransform/redefine.

Scenarios to test:

- Non-matching class: always returns `null`, zero `byte[]` allocations from the rule itself.
- Matching class already instrumented: no-op, does not add a second hook.
- Matching class with corrupted bytes: clear fail-open/closed policy and no log storm.
- Multiple loaders with the same name: proper scoping/filtering.
- Two threads transforming concurrently: no shared mutable visitor.
- Unregistration: in-flight callbacks do not use closed resources.
- Helper class loading inside callback: no recursion/deadlock.

## 12. Lifecycle and Memory Anti-Patterns

### Retaining All Input Bytes After Every Callback

```java
static final java.util.List<byte[]> HISTORY =
        new java.util.ArrayList<>();

static void keep(byte[] input) {
    HISTORY.add(input);
}
```

This is an **illustrative anti-pattern**, not a standalone Java file. When many classes load, an unbounded list keeps every buffer alive indefinitely; if the goal is just recording metrics, this is unnecessary.

### Per-Class-Loader Map Without Eviction

```java
static final java.util.Map<ClassLoader, byte[]> CACHE =
        new java.util.concurrent.ConcurrentHashMap<>();
```

Strong keys can keep plugin loaders and class metadata reachable after the application unloads the plugin. If caching is required, enforce lifecycle/TTL/size budgets, verify cached values do not hold back-references to the loader, and distinguish module/class identity. Weak-key caches do not prevent all leaks if values hold strong references to the key.

### Uncleaned `ThreadLocal`

If a `ThreadLocal` holds plugin-owned objects on a long-lived thread pool, the plugin loader can remain retained through that value. For a reentrancy guard, store only a minimal flag/value and call `remove()` in `finally`.

### Unbounded Queue for Events/Logs

If callbacks outpace the consumer, the queue grows with the class loading rate or memory pressure. Enforce bounded capacity and a drop/coalesce policy—never wait on blocking I/O from the callback.

## 13. Troubleshooting Table

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Slow startup despite few target classes | Parsing all classes before filtering | Check name/module/loader before touching bytes |
| Rising GC allocations | Cloning and creating writers even when unchanged | `return null` on no-op, clone only when needed |
| Class loading deadlock | Logging lock, reflection, synchronized callback, or classloading recursion | Reduce dependencies, avoid I/O/locks, bounded guard |
| Thousands of log lines during startup | Logging every class, formatting strings before level check | Counters, sampling, rate limit, external exporter |
| Races under concurrent class loading | Sharing mutable parser/writer | Local variables, immutable policy, thread-safe counters |
| Stack map errors / `VerifyError` | Rewriting control flow without preserving frames | Use an appropriate library, verify target JVM classfiles |
| `Class.forName` triggers class loading loop | Trying to inspect metadata of class currently being defined | Use callback metadata, bytecode parser, and proper resolver |
| Multi-loader app gets mis-patched | Filter/cache keyed only by class name | Add loader/module namespace to policy |
| Loader remains reachable after plugin unload | Cache holds strong `ClassLoader` or `Class<?>` references | Bounded cache, lifecycle cleanup, heap-dump paths |
| Counter changes while reading | `LongAdder.sum()` is not an atomic snapshot across updates | Treat as approximate metric; synchronize separately if consistent snapshot needed |
| Transformer throws exception but class still loads | Misunderstanding transformer exception contract | Do not rely on exceptions as a strict class-blocking mechanism |
| Few callbacks yet startup stays slow | Measuring only matched classes, missing VM/other callbacks | Measure baseline and end-to-end class loading |
| Old hooks still run after removing transformer | `removeTransformer` does not roll back already-instrumented classes | Use redefine/retransform with capability if rollback is needed |
| Java 17 does not recognize `java.lang.classfile` | This API became standard in JDK 24 | Use ASM/Byte Buddy or upgrade JDK |

## 14. Pre-Production Checklist

1. Filter by `className`/`module`/`loader` and policy snapshot **before the parser**.
2. Do not instantiate `ClassReader`/`ClassWriter` when the class does not match.
3. Return `null` on no-op; do not clone or mutate input.
4. Parse only as much metadata/code as the rule requires; do not compute frames unnecessarily.
5. Do not use `Class.forName`/reflection that causes unintended classloading in the callback.
6. Do not log per-class unconditionally; format messages outside the callback.
7. Use bounded queues, sampling/rate limiting, and avoid potentially blocking I/O.
8. Use immutable config and local visitors/buffers; thread-safe counters.
9. Do not `synchronized` the entire callback on a global monitor.
10. If using a `ThreadLocal` guard, place it after the fast filter and clean up in `finally`.
11. Do not hold unbounded strong references to class loaders, `Class` objects, or byte arrays.
12. Define fail-open/fail-closed behavior per requirements; do not blindly swallow VM fatal errors.
13. Verify classfiles and test constructors, exception paths, class versions, and frames.
14. Test repeated redefinition/retransformation alongside other transformers.
15. Measure baseline/no-op/parse/rewrite/logging/end-to-end startup on realistic workloads.
16. Set alerts for performance budgets, failure rates, memory retention, and callback latency.
17. Test on the target JVM, classloaders/modules, and build/deploy pipeline.

## 15. Self-Check Questions

**Question 1:** Why is `return null` better than `return bytes.clone()` when a class is not modified?

**Answer:** `null` is the API-defined no-op and avoids byte allocation/copying while leaving the input unmodified.

**Question 2:** Should you instantiate a parser for every class and then check `className`?

**Answer:** No, if the rule can filter by name/module/loader. Filtering first keeps the common path cheap.

**Question 3:** Is a logger set to level OFF completely allocation-free?

**Answer:** No, if the message is formatted before checking the level. Guard message construction, and prefer not logging on the fast path.

**Question 4:** Does a `ThreadLocal` guard prevent recursion across all threads?

**Answer:** No. It only prevents same-thread reentry and does not replace managing classloader dependencies/locks.

**Question 5:** Does `changed.increment()` prove the JVM has successfully installed the bytes?

**Answer:** Not yet. The counter increments before the JVM verifies/links/defines the class. Execution results must be tested.

**Question 6:** Can a transformer removed via `removeTransformer` still receive callbacks?

**Answer:** Yes, due to concurrent class loading already in progress. Teardown code must tolerate in-flight callbacks.

**Question 7:** Why should callback exceptions not be treated as a guaranteed way to block class loading?

**Answer:** The contract still allows subsequent transformers to run and class loading/redefinition to proceed; another mechanism is needed if blocking is a policy requirement.

**Question 8:** Is optimizing allocation inside `transform` enough to optimize an agent?

**Answer:** No. There is still parsing CPU, JVM verification, classloader concurrency, and the runtime overhead of probes injected into methods.

## 16. Authoritative References

- [Oracle Java SE 17 — `ClassFileTransformer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): callbacks, `null`, not mutating `classfileBuffer`, errors, and redefine limits.
- [Oracle Java SE 17 — `Instrumentation`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): adding/removing transformers and concurrent class loading semantics.
- [Oracle Java SE 17 — `java.lang.instrument` package](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): `premain`, agent manifest, and lifecycle.
- [Oracle Java SE 17 — `LongAdder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html): concurrent counters.
- [Oracle Java SE 17 — `ThreadLocal`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html): per-thread guard and `remove()`.
- [JVMS Java SE 17 — Chapter 4](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html): classfile, constant pool, method Code, and StackMapTable.

**Takeaway:** A fast callback does not mean skipping checks. Use **cheap fast filters, `null` no-ops, conditional parser/writer usage, out-of-callback logging, and concurrency-safe state**, then measure actual costs on the target JVM. Performance optimization must go hand in hand with bytecode correctness and class loader lifecycle management.
