# Managing Diagnostic Data Without Making Callbacks Depend on the Class Being Loaded

When building a Java instrumentation agent, the `ClassFileTransformer.transform(...)` method executes right at the moment the JVM is processing the **definition, redefinition, or retransformation of a class**. This is a highly sensitive spot: a single logging call, serializer creation, reflection call, or accidental reference to an application class can trigger the loading of another class before the current class finishes being defined. The consequences can include transformer invocation loops, class linkage errors, deadlocks during class loading, severely increased startup latency, or lost diagnostic signals right when they are needed most.

The goal of this article is to design a **safe diagnostic data recording path inside the transformer callback**, avoid turning observation into a dependency on **the very class being loaded**, decouple collection from data analysis/export, and understand the limits of each buffer type. The Java 17+ example below is a runnable startup agent that only counts callbacks and retains a sample of class names in bounded memory; it does not modify bytecode.

You will be able to explain: why `Class.forName`, loggers, formatters, service discovery, class loaders, and serializers are risky inside the callback; what data is available in the `transform` parameters; how to place counters and buffers safely; and why logging outside the callback still needs to account for backpressure, loops, and when the agent is initialized.

## 1. Context: Transformers Run During Class Loading

An agent registers a callback via `Instrumentation.addTransformer(...)`. For a new class, the JVM invokes the transformer before the class's bytes are used to complete its definition; if there are multiple transformers, the result of a previous transformer can be passed to the next one.

~~~text
JVM prepares to define class demo/app/Target
       |
       v
read class bytes -> transformer A -> transformer B -> verify/link/define
                       |
                       +-- [DANGEROUS] wants to log
                              -> logger backend needs to load a class
                              -> class loader / transformer runs again
                              -> may trigger reentrancy / locks / errors
                       |
                       +-- [SAFER] check name, increment counter,
                              record tiny metadata into bounded buffer,
                              return null or valid byte[] immediately
       |
       v
another part of the agent reads data later, logs/exports outside the callback
~~~

"The transformer runs while the class is being loaded" **does not mean** every `transform` call only comes from a new load: it can also come from `redefineClasses` and, for a transformer registered as retransformation-capable, from `retransformClasses`. Therefore, recorded data must clearly state whether it counts **callback invocations**, **class definitions**, or **retransformation passes**. Do not infer that one callback equals one new class successfully initialized.

This hot path has special constraints:

- The callback can be invoked very frequently, during application startup or lazy class loading on demand.
- Multiple threads can concurrently pass through the callback for different classes; do not assume a global callback runs on only a single thread.
- The JVM may be holding or having to interact with locks related to class loading. Adding a lock from a logger or cache inside the callback can create a wait cycle.
- Agent code may itself need to load helper classes at runtime. If those dependencies are not ready yet, the callback creates the very class-loading activity it is observing.
- Errors and stack traces from the callback do not necessarily reach application logs in the familiar way; the Javadoc states that an unhandled exception from a transformer has the same effect on the transformation as returning `null`, and subsequent transformers may still be called.

Therefore, the design principle here is: **do minimal work inside `transform`, and push work that can cause class loading, locking, I/O, or large allocations elsewhere.**

## 2. Parameters You Can Use Without Reloading the Target Class

Java 17 supports two `transform` overloads. Example signature receiving module information (introduced in Java 9):

~~~java
public byte[] transform(
        Module module,
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        ProtectionDomain protectionDomain,
        byte[] classfileBuffer);
~~~

This is an **illustrative signature**, not a standalone Java source file. You can override the five-parameter version (without `Module`); the six-parameter default method delegates to the five-parameter version if the six-parameter version is not overridden.

| Parameter | Useful to know | Risks to avoid |
| --- | --- | --- |
| `className` | Binary name in **internal form** such as `demo/app/Target`, usable for filtering | Do not call `Class.forName` to "verify" the name; check for `null` first |
| `loader` | Defining class loader, may be `null` for the bootstrap loader | Do not call `loadClass`, `getResource`, `toString`, or hold an unbounded strong reference |
| `classBeingRedefined` | `null` when defining a new class; non-null on redefine/retransform | Do not rely on it to obtain `Class<?>` on initial load or trigger reflection |
| `module` | Module containing the class being transformed (with the six-parameter overload) | Do not run complex reflection/module scanning logic in the hook |
| `protectionDomain` | Protection domain associated with the class being defined | Do not immediately open code source URLs/JARs, access policies/permissions, or retain the object long-term |
| `classfileBuffer` | Input bytecode at the point the transformer is called | Do not mutate the buffer in place; do not hold a long-lived reference; may contain sensitive data |

When no bytecode change is needed, **`return null` is the right answer**, meaning this transformer performs no transformation. Do not return `classfileBuffer` itself just to signal "unchanged"; do not mutate the input `byte[]` in place. When an actual change is needed, return **a new valid `byte[]`** and uphold the redefine/retransform contract if those capabilities are used.

`className` uses `/`, not `.`. In special definition cases, the name can be `null`, so filters must always tolerate `null`. `loader == null` does not mean "unknown", but usually indicates the bootstrap loader; nor should you infer that the agent has access to every module from the name information alone.

## 3. How Circular Dependencies Are Created Inside the Callback

### 3.1. Using Reflection to Look Up the "Class Being Loaded"

The snippet below illustrates **what not to do** while the JVM is defining a new class:

~~~java
// Dangerous example: do not put this snippet into a real transformer.
String binaryName = className.replace('/', '.');
Class<?> target = Class.forName(binaryName, true, loader);
target.getDeclaredMethods();
~~~

While the class is being defined, calling `Class.forName` can ask the class loader to participate in defining/initializing a class of the same name or load classes required by reflection. In specific situations this can cause recursive loading, `ClassCircularityError`, `LinkageError`, deadlocks, or load-time-dependent behavior. Changing `true` to `false` only avoids requesting initialization; **it can still trigger loading and linking**. Do not use that approach to obtain metadata of a class currently in the middle of being defined.

If you need to inspect class structure to decide how to transform, read **the bytes passed to the callback by the JVM** using a pre-prepared bytecode tool, and do only what is necessary. Reading bytes does not require defining the class into a `Class<?>`; however, a **parser** also has dependencies, allocations, and can itself trigger class loading. Therefore, the parser must be packaged, preinitialized, and controlled.

### 3.2. Referencing an Application Class Directly from Agent Code

An example that should not be placed inside `transform`:

~~~java
// Dangerous illustration, not a standalone program.
if (demo.app.Target.class.getName().equals(className)) {
    DiagnosticRegistry.record(demo.app.Target.class);
}
~~~

In the Java source above, a class literal can force resolution or cause callback code to link against a type managed by the application loader. Once an agent has a static dependency on application code, class loading order and loader visibility become part of correctness. Agent code in a different class loader can even hit `NoClassDefFoundError` even though the application can load that class itself.

Instead of depending on a target `Class` object, compare the **internal name literal**:

~~~java
if ("demo/app/Target".equals(className)) {
    // Only collect small primitive/String data that is already available.
}
~~~

String comparison does not require the JVM to define `demo.app.Target`. That is why callbacks typically filter early on `className` before doing expensive operations.

### 3.3. Logging with a Framework Inside the Hook

A seemingly harmless statement:

~~~java
// Failure mode illustration only.
logger.debug("Transforming {}", className);
~~~

can pull in loading of the logging backend, message formatter, provider, MDC, stack walker, service loader, configuration, appender, and I/O. When the log engine has not been initialized yet, its supporting classes may themselves pass through the callback. If the logger uses locks while the callback runs under sensitive class-loading state, lock cycles become even harder to predict. Many logging libraries also create reflection/object data or store context information unsuitable to retain on this path.

Not every logger will necessarily fail; the issue is **uncontrolled dependencies**, initialization timing, and overhead. With a callback intercepting every class, one log statement per class can cause a log explosion right at startup.

### 3.4. Pulling "Complete" Data from Loader, Domain, or Bytes

- `loader.getClass().getName()`, `loader.toString()`, `loader.getResource(...)`, or `loader.loadClass(...)` can perform additional class loading, synchronization, or I/O.
- `protectionDomain.getCodeSource()` and steps that fetch URLs/JARs can introduce new dependencies; an arbitrary object's `toString` can invoke uncontrolled code.
- Using a JSON serializer to serialize `ClassLoader`, `Module`, or `ProtectionDomain` can trigger reflection, cycles, huge object graphs, and information leaks.
- Keeping `classfileBuffer` in a long-lived queue pins many large byte arrays, increasing heap usage, GC pressure, and the risk of exposing class bytes.
- Caching `Class<?>` or `ClassLoader` in an agent `static Map` can keep class loaders alive after application undeploy/hot reload.

For typical diagnostic purposes, **class name + event type + a few counters** are usually enough to narrow things down. Only retain live class loader objects if there is a clearly designed and verified lifecycle/weak-reference mechanism.

## 4. Collection Architecture: Small Hot Path, Diagnostics Processed Elsewhere

A pragmatic architecture:

~~~text
                  Agent bootstrap (premain/agentmain)
                    | create DiagnosticState
                    | preload required helpers
                    | configure filters / limits / writer
                    v
       register ClassFileTransformer (once)
                    |
              each transform callback
                    |
              name == null? -> return null
                    |
              prefix mismatch? -> return null
                    |
              record small primitive/counter/metadata
                    |
              bounded buffer / overwrite or drop
                    |
                 return null
                    |
       +------------+------------------------------+
       |                                           |
JVM continues defining class                Agent reporter
                                            reads snapshot
                                            redaction / formatting
                                            logs / JFR / exports
                                            outside the callback
~~~

Split into three responsibilities:

1. **Bootstrap:** prepare helpers, initialize counters/buffers and the reporter **before** registering the transformer. Avoid having the first callback lazily initialize an entire library graph.
2. **In-callback collector:** filter early, write into pre-allocated structures, tolerate concurrency, have bounded latency and memory, and never block waiting for the reporter.
3. **Out-of-callback reporter:** periodically take snapshots or drain queues, aggregate, format, log/export over the network, and manage timeouts/batching, retention, and pipeline health.

This path does not eliminate 100% of class-loading side effects (the JVM, compiler/JIT, libraries, and scheduling can vary), but it significantly reduces uncontrolled dependencies. Do not run the reporter inside `transform` just because you "want to log immediately".

### 4.1. What to Do Before Registering the Transformer

- Initialize the **transformer class**, helper classes, counters, filters, and data structures used on the hot path.
- If using a bytecode parser, prepare and exercise the parser on safe data before the hook starts; consider preloading/relocating helper packages.
- Configure **self-exclusion** for packages belonging to the agent, logger, exporter, serializer, or internal packages that do not need observation.
- Define buffer sizes, payload limits, events/second, and behavior when full.
- Choose a reporter thread/lifecycle outside the callback. Use a daemon worker if appropriate, and interrupt/flush within a budget on shutdown.
- Do not call `Instrumentation.addTransformer` multiple times unintentionally; duplicate registrations can cause repeated callback invocations and make the source hard to trace.

"Preloaded" is not a guarantee that every dependency is strictly free of later class loading (e.g., lazy providers, lambdas, charsets, locales, logging backends). You still need to test on the target JVM version and keep the callback path simple.

### 4.2. Level of Data to Store

| Data | Recommendation | Reason |
| --- | --- | --- |
| Total callbacks matching filter | Atomic counter | Fast counting, does not pin target classes |
| `className` in internal form | At most a bounded number of slots or a sample | Can guide investigation without loading the class |
| `loader == null` | Boolean/flag when useful | Does not hold a reference to the loader |
| New load vs redefine/retransform | `classBeingRedefined == null` or already-determined metadata | Does not force reflection onto `Class<?>` |
| `Module`, `ClassLoader`, `ProtectionDomain` | Avoid retaining directly in long-lived buffers | Can keep class/JVM graphs alive |
| `classfileBuffer` | Use only inside the callback when actual transformation needs it | Byte arrays can be large and contain secrets |
| Full stack trace | Collect selectively in out-of-callback processing only | High cost and expands dependencies |
| Sensitive tokens/configs/URLs | Redact or do not store | Telemetry must not become a data leak path |

Not all data can be reconstructed **after** the callback: if you want to record the class name, event type, or labels observable right at transform time, store a **minimal snapshot of the available information**; the reporter does not need to call back into the class loader to reconstruct metadata.

## 5. Java 17+ Example: Bounded Diagnostic Buffer, Callback Does Not Load `Target`

This example creates a startup agent and a simple application. The agent only records callbacks for `demo/app/Target` using an `AtomicLong` and an eight-slot `AtomicReferenceArray<String>`. The callback **does not call `Class.forName`**, does not log, does not serialize, and does not reference `demo.app.Target.class`. The reporter prints metrics upon normal JVM termination via a shutdown hook, i.e., outside `transform`.

The four required files are `SafeDiagnosticAgent.java`, `Main.java`, `MANIFEST.MF`, and the JAR built from them. The two Java files can be placed in the same source directory; `javac -d` creates the class directory tree matching the packages.

### 5.1. File `SafeDiagnosticAgent.java`

~~~java
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicReferenceArray;

public final class SafeDiagnosticAgent {
    private static final int CAPACITY = 8;
    private static final AtomicLong SEEN = new AtomicLong();
    private static final AtomicReferenceArray<String> RECENT =
            new AtomicReferenceArray<>(CAPACITY);

    public static void premain(String agentArgs, Instrumentation inst) {
        // Initialize helpers/essential operations before registration.
        Observer observer = new Observer();
        SEEN.getAndIncrement();
        SEEN.set(0);
        RECENT.set(0, null);

        Runtime.getRuntime().addShutdownHook(
                new Thread(SafeDiagnosticAgent::report, "agent-report"));

        inst.addTransformer(observer, false);
        System.out.println("AGENT_READY");
    }

    private static void report() {
        System.out.println("TARGET_CALLBACKS=" + SEEN.get());
        System.out.println("RECENT_TARGET=" + RECENT.get(0));
    }

    private static final class Observer implements ClassFileTransformer {
        @Override
        public byte[] transform(
                ClassLoader loader,
                String className,
                Class<?> classBeingRedefined,
                ProtectionDomain protectionDomain,
                byte[] classfileBuffer) {

            // Compare internal name; do not resolve/load target class.
            if (!"demo/app/Target".equals(className)) {
                return null;
            }

            long sequence = SEEN.getAndIncrement();
            int slot = (int) (sequence & (CAPACITY - 1));
            RECENT.set(slot, className);
            return null;
        }
    }
}
~~~

**Breakdown of each decision:**

- `Observer` is created before `inst.addTransformer(...)`. Objects/structures used in the callback are already allocated; "warming up" the counter and slot only helps readiness and does not guarantee every JDK path has been preloaded.
- The five-parameter method is overridden. On Java 17, the default overload with `Module` delegates to this version if we do not override the six-parameter overload.
- The filter compares `"demo/app/Target".equals(className)`, avoiding `NullPointerException` when the name is null and **not** forcing the Target class to be loaded for comparison.
- `SEEN.getAndIncrement()` assigns a sequence number to the event, using `AtomicLong` to tolerate concurrent callbacks. This is the **number of callbacks matching the filter**, not the number of times the JVM successfully defined the class.
- `AtomicReferenceArray` has exactly eight slots: the formula `sequence & 7` maps each event to a slot. With many events, older slots are overwritten; memory holding class names is bounded. The class name string is provided via the callback parameter; no `Class<?>`, `ClassLoader`, or `byte[]` is retained.
- `return null` means **no bytecode modification**. Counting and recording metadata are purely observational.
- `report()` runs in a shutdown hook, not inside the callback. Thus `System.out`, string formatting, and I/O stay in the output phase. A shutdown hook is a convenient demo mechanism, **not a reliable telemetry protocol for production**.
- There are no third-party dependencies. Placing `SafeDiagnosticAgent` in the default package is only to minimize compilation steps, not a recommended structure for large agents.

**Concurrency limitation of the ring:** the atomic counter records the number of callbacks, but two threads executing `SEEN.getAndIncrement()` and then `RECENT.set(...)` can be interleaved by the scheduler. The array only provides a best-effort recent snapshot; it does not guarantee "the eight most recent events" in chronological order or an exactly-once consumer queue. If ordering/losslessness is required, you must choose a different data structure and backpressure mechanism, accepting the explicit costs and assumptions.

### 5.2. File `Main.java`

~~~java
package demo.app;

public final class Main {
    public static void main(String[] args) {
        System.out.println("APP_RESULT=" + Target.answer());
    }
}

final class Target {
    static int answer() {
        return 42;
    }
}
~~~

`Main` and `Target` compile into two class files in package `demo.app`. When the application executes `Target.answer()`, the JVM must have the definition of `demo/app/Target`; the agent has already been registered from `premain` before `main` runs.

### 5.3. File `MANIFEST.MF`

~~~text
Manifest-Version: 1.0
Premain-Class: SafeDiagnosticAgent

~~~

The manifest here is for a **startup agent**: `Premain-Class` points to `SafeDiagnosticAgent`, which contains `public static void premain(...)`. Ensure there is a trailing newline and an empty line at the end of the main section. `Agent-Class` is not needed because this exercise does not dynamically load via the Attach API.

### 5.4. Compile, Package, and Run

In the directory containing the three source files created above, using JDK 17 or later:

~~~bash
javac --release 17 -d agent-out SafeDiagnosticAgent.java
javac --release 17 -d app-out Main.java
jar --create --file safe-agent.jar --manifest MANIFEST.MF -C agent-out .
java -javaagent:safe-agent.jar -cp app-out demo.app.Main
~~~

The two `javac -d` commands create the output directories and required subdirectories on JDK 17+. `jar --create` packages the agent class along with its nested class `SafeDiagnosticAgent$Observer.class` into `safe-agent.jar`; the application runs independently via `-cp app-out`. Use a fresh run without attaching other agents or actively redefining/retransforming `Target` when comparing against the expected output.

**Standard output produced by the example on a typical JVM:**

~~~text
AGENT_READY
APP_RESULT=42
TARGET_CALLBACKS=1
RECENT_TARGET=demo/app/Target
~~~

Explanation: `AGENT_READY` appears during `premain`. The application then prints `42`; the callback for the Target class is counted once; when the JVM shuts down normally, the reporter prints the recorded statistics. In environments with other agents, custom class loaders, multiple redefinitions, or extra JVM diagnostics, output may include additional lines or a different callback count. Do not treat `1` as an invariant constant across all workloads.

**What is actually proven:** the Target class behaves as before in the demo, the class-name filter works, small data is stored without the callback calling into the Target class, and printing the report is decoupled from the callback. It does **not** prove bytecode modification, retransformation, logging backends, or that an agent is completely immune to internal class loading.

## 6. When Many Events Must Be Collected: Choosing Storage and Loss Policies

A proper buffer must have a clear **capacity** and **failure policy**. Some options:

| Mechanism | Advantages | Risks and conditions |
| --- | --- | --- |
| `AtomicLong`/`LongAdder` counters | Minimal data, relatively low contention; good for totals | Does not retain event names/strings; count does not equal successful class load |
| Overwriting `AtomicReferenceArray` ring | Bounded allocation, fast writes, does not retain loaders | Overwrites old entries; snapshot may be out of order under multithreading |
| Bounded queue + `offer` | Decouples producer and consumer, reports when full | Some implementations use locks; `offer` does not wait for capacity but **may contend on locks** |
| Unbounded concurrent queue | Simple API, never blocks on capacity | If consumer is slow, data/memory allocation grows without bound |
| Thread-local buffers | Reduces contention between producers | Must manage thread lifecycle and total memory; thread pools extend data lifetime |
| Direct export inside callback | Data leaves immediately | Should be avoided: I/O, serialization, retries, and locks slow down/disrupt loading threads |

An **overwriting ring** is a **best-effort snapshot** policy: keeps recent items, accepts losing history. **Drop-on-full** for a queue is another policy: rejects new events when full, with a `droppedCounter` to track what was lost. Both require a separate metric for overwritten/dropped events and an explicit statement that the data is incomplete.

If the requirement is "zero event loss", you must weigh data reliability against JVM safety. Blocking indefinitely inside a transformer to "wait for space" is usually a dangerous choice, because the callback is inside the class-loading lifecycle. For business requirements needing exact recording, use a separate durable business audit channel; best-effort diagnostics cannot replace transactional auditing.

### 6.1. Bounding Counts and Sizes

A few calculations help avoid accidental designs:

- 100,000 callbacks where each event retains a class bytes array averaging 20 KiB will hold about **2 GiB** of raw data, excluding overhead. Do not store `byte[]` to "analyze later" without a hard limit.
- A 256-slot ring holds at most 256 object references at a time; the referenced strings/records still consume memory, so record sizes must be bounded.
- If logging every class in a system with tens of thousands of class definitions, log volume at startup can exceed exporter throughput; filter before creating events.
- Under overload, you can tighten filter specificity, lower the sampling rate, collect only aggregate counters, or drop events. Always reflect sample loss in reports.

The numbers in these calculations are illustrative. Actual capacity must be measured against class sizes, class-loading rates, GC, and agent configuration. Counting transformer callbacks is not equivalent to the number of classes live on the heap.

### 6.2. Class Loader Independence and Reference Management

In applications with plugins, app servers, or hot reload, class loaders can be created and discarded many times. A `Map<ClassLoader, Diagnostics>` placed in an agent global will hold strong references to loaders; it can prevent the entire class graph/metadata from being collected. Even caching `Class<?>` can transitively retain a loader.

Solutions depend on the goal:

- Do not retain the loader if you only need callback counts per package.
- If loader identity is needed, generate a separate lifecycle-managed identifier; do not call `toString` on arbitrary loaders inside the callback.
- Use weak references/weak-key maps **if you genuinely need to track loaders**, but understand equality, cleanup, concurrency, and how a value can inadvertently retain the key.
- Discard or shrink data when an agent/module no longer needs observation. `removeTransformer` prevents future callbacks, but the Javadoc notes that callbacks already in flight may continue after removal; code must tolerate that state.

## 7. Preloading and Class Loader Isolation: Necessary but Not Sufficient

One precaution is to package dedicated helpers for the agent and try to initialize them before registering the transformer. You can bundle helpers into the agent JAR or use shaded/relocated dependencies to avoid name collisions with the application, depending on how the agent is deployed. Helpers should not be resolved by the target class's own class loader inside the callback.

However, there are several traps:

1. **Lazy loading:** a library is instantiated, but the first method call loads a formatter, codec, lambda, or provider.
2. **Bootstrap/library instrumentation:** if the transformer applies to `java/*` or `jdk/*`, even the JDK helpers used to record data can trigger callbacks. Filter early and instrument only the groups genuinely needed.
3. **No `Class<?>` on new load:** `classBeingRedefined == null` is the normal contract; do not run `Class.forName` to compensate.
4. **Cross-loader visibility:** an agent loaded by one loader does not necessarily have access to application classes. Having the right package name does not mean `loader.loadClass` will be safe.
5. **Instrumentation of helpers:** if you instrument the agent/helpers/exporters themselves, you can create recursion in the measurement path. Define exclusion scope before enabling.
6. **Module boundaries:** a `Module` from the API is not an automatic license to read/open all modules or reflect into any package. Valid module access must be handled during setup if genuinely needed.

The `Instrumentation.addTransformer` Javadoc notes that classes the transformer depends on may be excluded from the callback stream. That is **not** a blanket guarantee that "every dependency is automatically safe". Do not rely on an internal JVM exclusion mechanism to skip designing against reentrancy and class-loader dependencies.

## 8. Reentrancy Guards: Uses and Limits

Some agents use a `ThreadLocal` as a reentrancy guard. The goal is to prevent **the same thread** from processing nested diagnostic events generated by its own measurement path. Conceptual code:

~~~java
// Pseudocode: illustrates the guard, not a standalone runnable class.
if (Boolean.TRUE.equals(IN_DIAGNOSTICS.get())) {
    return null;
}
IN_DIAGNOSTICS.set(Boolean.TRUE);
try {
    captureMinimalMetadata(className);
    return null;
} finally {
    IN_DIAGNOSTICS.remove();
}
~~~

`IN_DIAGNOSTICS` must be declared/initialized in the agent before the transformer is registered; `captureMinimalMetadata` must be a prepared, safe processing path. This is not a magic "add ThreadLocal and every callback becomes safe" trick:

- The guard only prevents reentrancy **within the same thread**; it does not resolve deadlocks between two threads or class-loading dependencies on another thread.
- `ThreadLocal` can add overhead or allocate new state on other threads; use `remove` to avoid leaking context in thread pools.
- If the guard sits *after* a logger/parser call capable of triggering loading, it arrives too late.
- Holding a guard does not automatically propagate across asynchronous tasks on other threads.
- When a callback throws, `finally` must restore state; a stuck guard can silently drop all subsequent diagnostics on that thread.

**Prefer not creating dependencies in the first place.** A guard is an extra layer of defense when nested logic cannot be completely avoided, and it must be tested against real application JDKs, loaders, class loading, and concurrency.

## 9. Errors in Callbacks and Preserving Diagnostic Signals

The `ClassFileTransformer` contract has a detail that is easy to misunderstand: **if a transformer throws an unhandled exception, the JVM still tries subsequent transformers and still attempts the load/redefine/retransform**; for the failing transformer's transformation, the effect is the same as returning `null`. Thus, you may not see a normal exception surface where the application calls the class, yet you have lost the transformation or lost diagnostics.

How to structure this:

- For expected errors in diagnostic storage, maintain a **minimal failure counter**, and `return null` when there is no bytecode transformation.
- Do not try to build large exception messages, full stack traces, or call complex loggers inside the callback; that can create a new error loop.
- If errors truly must be reported, capture small error codes/counts in the callback and hand them to the reporter to format, decide on retries, or alert.
- For invalid classfile errors in transformation logic, the API allows `IllegalClassFormatException` when the input is not a well-formed class file. That is not a command to "force the JVM to halt": this exception also has the same effect as returning `null` in the transformer chain. Dedicated tests are needed to confirm the transformer does not produce malformed bytes.
- The Javadoc mentions catching `Throwable` to guard against unchecked exceptions. In production designs, do not silently swallow severe JVM errors like `OutOfMemoryError` and pretend everything is stable. Choose an explicit error policy, measurement, and consequence.

Illustrative example of **a helper method, not a standalone source file**:

~~~java
private byte[] safeObserve(String className) {
    try {
        if (className != null && className.startsWith("demo/app/")) {
            observed.incrementAndGet();
        }
    } catch (RuntimeException diagnosticFailure) {
        failures.incrementAndGet();
    }
    return null;
}
~~~

Here, `observed` and `failures` are **pre-created counters**. This is only a pattern for expected errors; if `failures.incrementAndGet()` itself or an unprepared helper class causes a new error, the callback still needs better defensive design. Never let diagnostic errors alter the returned bytecode or the business class's contract.

## 10. Out-of-Callback Reporter: Formatting, Exporting, and Shutdown

Moving I/O to a worker or another lifecycle point keeps the callback from being blocked by network/formatters; however, the reporter still runs **in the same JVM**, sharing CPU, heap, GC, and potentially triggering class loading. Therefore:

- Initialize the reporter on the agent startup path/thread before or independently of the callback; prepare dependencies and have a filter excluding the exporter's packages.
- Consume only snapshotted data; do not call back into `Class.forName` for loading classes to fill in missing details.
- With bounded queues, use budgeted flush/batching, timeouts, and drop metrics; avoid infinite retries when the collector fails.
- Do not send events containing secrets, class bytes, full class loader objects, or paths with sensitive information.
- If the reporter fails, the callback must not wait for the reporter to recover; keep diagnostics fail-open if the application contract requires it, and alert on signal loss.
- Keep shutdown hook work bounded; `Runtime.halt`, `kill -9`, JVM crashes, or abrupt environment termination can prevent shutdown hooks from running. Therefore, the shutdown-printing example is not a durability guarantee.
- Avoid non-daemon workers that live forever and prevent the application from exiting; close resources and stop workers according to the proper lifecycle.

Where data must survive crashes, consider another recording mechanism with appropriate durability, but do not turn `transform` into a synchronous file writer for every class just to guarantee zero loss.

## 11. Data Quality: Callback Does Not Equal Successful Class Loading

A counter like `TARGET_CALLBACKS=1` proves that the transformer was called once by the JVM for a name matching the filter in the demo. It does **not** prove:

- That the class successfully passed verify/link/initialize steps after the callback returned.
- That the class name is unique across the entire JVM: the same name can appear across multiple defining class loaders.
- That every class definition passed through the agent: a late-registered agent does not automatically see previously loaded classes; some dependency class definitions are excluded by contract.
- That one callback corresponds to one business event or one method execution.
- That data was successfully delivered to the backend when it is only sitting in the ring.
- That ring write order reflects absolute chronological order across multiple threads.

If you need to count **successfully loaded classes** or build an accurate map of loaded classes, you must redefine the signal, add independent diagnostic sources, and handle the supported JVM conditions. Callback count metrics should be named accurately and paired with sample-loss/coverage caveats.

To diagnose missing data, distinguish:

| Observation | Possible interpretation | Next check |
| --- | --- | --- |
| Counter increases, ring no longer has old names | Slots were overwritten | Total events and capacity; check retention/snapshot |
| Counter does not increase for expected class | Wrong filter, class loaded before registration, different loader/load path, callback has not run | Check internal name, registration timing, JDK/agent setup |
| App fails to load class but counter increased | Callback ran before verify/define completed | Check `ClassFormatError`/`LinkageError` and JVM logs |
| Exporter misses events even though counter increased | Queue drops/flush failures, backend error/lag | Monitor drop/failure/ingest delay |
| Agent starts up slowly | Heavy hook or helper init, logger/encoder loaded early | Separate `premain` and callback timing; narrow instrumented packages |
| Heap grows on hot redeploy | Agent holds strong references to loader/class or bytes | Inspect caches, weak refs, and retention |

## 12. QA Before Deploying to a Real Service

Do not just test that "the agent printed the right thing". Use a compact matrix that targets failure modes directly:

| Test group | How to trigger | Acceptance criteria |
| --- | --- | --- |
| New load | Main invokes a new class after `premain` | Callback receives correct internal name; app returns baseline result |
| Null name / bootstrap | Callback encounters null name or null loader | No NPE; does not force class load to learn the name |
| Multi-thread contention | Multiple threads load different classes | No deadlock, data race, or unbounded queue growth |
| Reentrancy | Logger/parser/helper lazy-loaded at test time | No infinite recursive hook; filter/guard takes effect |
| Reporter down | Simulate unreachable collector, full queue | Class loading does not hang; drop/overwrite is signaled |
| Redeploy / custom loader | Load then discard plugin class loader | Agent holds no unintended strong references |
| Bytecode error | Intentionally supply malformed transform output in isolated test | Clear failure path; does not corrupt unrelated classes |
| Retransform / redefine | If supported by agent, test on modifiable class | Accurate callback semantics/counting; no schema changes violating JVM limits |
| Shutdown / abrupt stop | Normal shutdown and forced kill in test environment | Understand which signals can be lost; do not rely solely on shutdown hook |

**Overhead measurement procedure:** run a baseline without the agent, the agent enabled with a filter skipping all classes, and the agent with the real filter and reporter enabled. Keep load, JDK flags, and workload equivalent; compare startup time, CPU, heap, allocation, GC, thread contention, class-loading rate, p95/p99 latency, and recorded/overwritten/dropped event counts. Do not assign a single fixed overhead number to all agents.

### Short Design Checklist

1. Filter by `className` and primitives; avoid resolving `Class<?>` for the class being loaded.
2. Pre-initialize helpers, required parsers, and buffers before `addTransformer`.
3. Do not log/serialize/read resources/wait on I/O inside `transform`.
4. Do not retain `classfileBuffer`, loaders, `Class<?>`, or domains in unbounded global collections.
5. Define capacity, overwrite/drop policy, and data-loss metrics.
6. Export data outside the callback, with timeouts and self-exclusion for the agent/exporter.
7. QA across multiple threads, custom loaders, class loading, and reporter failures.
8. Explicitly state that counted events are **callbacks**, not successful class definitions or completed business operations.

## 13. Common Mistakes

- **"Calling `Class.forName(name, false, loader)` cannot trigger loading."** False: `false` skips class initialization but can still trigger loading/linking.
- **"Logging only reads data so it has no side effects."** False: the backend, formatter, locks, I/O, and supporting classes can run right while the class is being defined.
- **"`Class<?>` is available in every transform callback."** False: `classBeingRedefined` is normally null on initial load.
- **"Returning `classfileBuffer` is how you signal no change."** The contract reserves `return null` for no-op; do not mutate input bytes in place.
- **"Calling `getResource` on the loader to learn the class source is safe."** Not guaranteed; the loader may perform I/O, locking, and additional class loading.
- **"A queue with `offer` never blocks threads."** Not guaranteed for lock-based implementations; `offer` only differs from `put` regarding waiting for capacity.
- **"A ThreadLocal guard solves all dependency cycles."** It only limits same-thread reentrancy; it does not handle deadlocks across threads.
- **"A ring buffer holds the exact eight most recent events in chronological order."** Not guaranteed when callbacks run concurrently and slots are overwritten.
- **"`removeTransformer` stops all callbacks immediately."** In-flight callbacks may continue.
- **"A callback running proves class definition succeeded."** The callback is invoked before class bytes are verified/applied.
- **"Once the agent is preloaded, the exporter will no longer load classes."** Lazy initialization can still occur; verify it.

## 14. Self-Check Questions

1. Why can calling `Class.forName(className.replace('/', '.'), false, loader)` still be wrong inside `transform`?
2. How does `classBeingRedefined` differ between a new definition and a redefine/retransform?
3. What does `return null` mean in `ClassFileTransformer`? Do you need to return the input `byte[]` when making no changes?
4. Why should a callback only record `loader == null` instead of storing loader objects in a static map?
5. What enables a logger or JSON encoder to cause recursion or deadlock even when only "recording diagnostics"?
6. Distinguish callback counters, overwriting rings, and dropping queues; what conclusions do they allow about data quality?
7. In the example, why must `SafeDiagnosticAgent` call `new Observer()` and prepare the buffer before `addTransformer`?
8. If the Target class loads successfully but the reporter is killed, what can you still know for sure from the internal count, and what is lost in exported data?
9. When multiple threads write to an eight-slot ring, is the snapshot always the eight newest events by timestamp?
10. If using Byte Buddy/ASM to actually transform bytes, how would you prepare helpers and decouple error logging so you do not depend on the target class being defined?

## 15. Conclusion and Further Reading

Treat `transform` as **code executing inside a class-definition transaction**. Do not resolve `Class<?>` of the class being loaded, do not call into class loaders or libraries with hard-to-control dependency graphs, and do not export data synchronously on this path. Keep the callback limited to filtering available metadata and updating small, bounded structures; move expensive processing elsewhere; and clearly document coverage, overwrite/drop behavior, concurrency, and data incompleteness.

When a transformer actually modifies bytecode, the byte modification **must happen and return synchronously inside the callback** so the JVM uses the new class definition. Offloading only applies to **formatting, recording, aggregating, and exporting diagnostics**; you cannot defer a required bytecode transformation until after the class has been defined and treat it as the same mechanism.

**Official references:**

- [Oracle JDK 21 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): callback timing, parameters, `null` for no-op, chaining, exceptions, and redefine/retransform.
- [Oracle JDK 21 — Instrumentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `addTransformer`, relationships between transformers, `removeTransformer`, and retransformation limits.
- [Oracle JDK 21 — java.lang.instrument package](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): startup/dynamic agent lifecycle, manifest, and `Instrumentation`.
- [Oracle JDK 21 — javac](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html): `--release` and `-d`, how package classes are placed into the output directory.
