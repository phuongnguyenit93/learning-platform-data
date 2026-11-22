# Separating the Agent Entry Point, Transformer, Helper, and Data Collection

> **Objective:** Design and package a Java instrumentation agent so that the **entry point**, **class-file transformer**, **helper invoked by application bytecode**, and **data collection/export component** each have their own responsibilities, dependencies, class loaders, and lifecycles. Understand how to wire these components together using Java 17+, avoid putting exporters or bytecode libraries on the hot path, avoid class-loading errors, and deploy a minimal `agent.jar` + `bridge.jar` pair. Includes a complete lab, `javac`/`jar`/`java` commands, verifiable stdout, and packaging QA steps.

This lesson belongs to the **Packaging and Deployment** group of Java Advanced Instrumentation. “Separating” is not simply moving four classes into four files. You must separate **dependency direction**, **class visibility**, **data contracts**, **which thread executes each task**, **initialization/shutdown**, and **the artifacts delivered to the JVM**.

## 1. Why does a single `Agent` class containing everything often become a problem?

In a first prototype, an agent author might put everything into `premain`:

```text
premain
  ├─ configuration
  ├─ register ClassFileTransformer
  ├─ write ASM/Byte Buddy code
  ├─ create helper
  ├─ send HTTP metrics/traces
  └─ close streams / flush
```

This design is hard to evolve because the four jobs run at different times:

- **Entry point** is invoked by the JVM when the agent starts; its job is to set up the system.
- **Transformer** is invoked by the JVM when defining/redefining/retransforming a class; it produces (or does not produce) classfile **`byte[]`**, and is not the place to send network requests.
- **Helper** sits on the execution path of **instrumented methods**; a business method may call the helper millions of times.
- **Collector/exporter** handles samples, batching, retries, metric snapshots, file/network I/O, and shutdown off the hot path.

If the helper calls a heavy exporter directly, every application request may suffer serialization/network latency. If the transformer keeps a library/exporter as a required dependency for a bootstrap class, a custom class loader may fail to see the type and throw `NoClassDefFoundError`. If the entry point initializes components haphazardly, callbacks may fire before the collector is ready.

**Architectural conclusion:** Separate the **control plane** (setup, policy, lifecycle, transformer) from the **data plane** (very fast callsite helper, data-processing collector) and define a small interface bridging the two sides.

## 2. The four-block model and data flow

```text
               java -javaagent:agent.jar=bridge.jar
                              │
                              ▼
                    [1] AgentEntry.premain
                     │                   │
          append bootstrap JAR      start collector
          configure/filter         configure policy
                     │                   │
                     ▼                   ▼
              [2] Transformer      [4] Collector / Exporter
              (class load time)        (background)
                     │                   ▲
         emit bytecode calling        read counter /
             ProbeBridge.hit()        drain queue
                     │                   ▲
                     ▼                   │
         Loaded application class        │
                     │                   │
            method executes              │
                     ▼                   │
              [3] Minimal helper ────────┘
              (bootstrap-visible,
               no network I/O)
```

There are **two distinct moments** to distinguish:

1. **Class-load time:** The JVM invokes the transformer with `classfileBuffer`. The transformer can return `null` (no modification) or return a valid new class byte array.
2. **Business-execution time:** The JVM executes the loaded application method. If the transformer actually inserted a callsite, `ProbeBridge.hit()` runs when the method is called — **not** every time the transformer callback fires.

Do not name a metric `requests_total` for the number of `transform(...)` callbacks: a single class load can correspond to millions of method invocations, while a redefine can trigger the transformer with no business request at all.

The lab below **simulates the callsite with a helper call already present in the application source**; the transformer is registered and confirms it sees the class, but returns `null`. This is a deliberate choice so it can run standalone with only JDK 17, without conflating “registering a transformer” with “injecting bytecode”.

## 3. Specific responsibilities of each component

| Component | Primary responsibility | What to avoid | Typical loading location |
| --- | --- | --- | --- |
| **Agent entry point** | `premain`/`agentmain`, read config, prepare helper, initialize sink, register transformer, shutdown | Generating bytes or exporting each event directly in the entry method; storing everything in arbitrary static globals | System loader or agent-managing loader |
| **Transformer** | Filter classes, parse input, apply transformation, return bytes or `null` | Making HTTP calls, blocking on queues, sharing a mutable writer, reloading the very class being defined | Agent core loader |
| **Minimal helper/bridge** | Receive probe calls at runtime; record quickly, small schema, thread-safe | Importing SDK/agent core, doing network I/O, holding class loader/request objects indefinitely | Bootstrap or a loader the target is guaranteed to see |
| **Collector/exporter** | Snapshot/drain/batch/sample, flush, retry, send to backend, measure export failures | Running synchronously on every business thread, treating an in-memory queue as a durable log | Agent core loader / dedicated worker |

A clean boundary does not require four threads or four JVMs. These are **four design roles**; a collector can be a background thread in the same process, or a sidecar/remote collector with a clear protocol. The entry point and transformer usually live together in `agent.jar`; the helper may live in a separate JAR due to class loader constraints.

### Data exchanged across each boundary

- `premain` → transformer: immutable filter rules, implementation/config references, and `Instrumentation` when needed.
- Transformer → JVM: `byte[]` classfile output or `null`; **do not** pass business events via the transformer's return value.
- Application bytecode → helper: static/interface calls with a stable owner/name/descriptor; arguments should be small and low-sensitivity.
- Helper → collector: snapshots from counters, a bounded queue, or a bridge interface with clear backpressure rules.
- Collector → backend: batch/stream/metric protocol; must have retries, timeouts, observability, and retention/privacy as required.

## 4. Entry point: the “composition root” of a Java agent

For a startup Java agent, the JAR manifest uses `Premain-Class`:

```text
Manifest-Version: 1.0
Premain-Class: demo.agent.AgentEntry

```

The JVM invokes a valid `premain` form, most commonly:

```java
public static void premain(
        String agentArgs,
        java.lang.instrument.Instrumentation inst) {
    // Wire the agent components together.
}
```

The snippet above is an **illustrative signature**, not a standalone Java program. `-javaagent:/path/to/agent.jar=options` passes the string after `=` into `agentArgs`. You cannot instantiate `new Instrumentation()` yourself; the JVM provides this object.

The entry point should execute in a sensible order:

1. Validate arguments and trusted artifact/config sources.
2. Establish class-loader visibility for the helper **before** target classes need to resolve it.
3. Initialize the helper/collector and verify the required API version/contract.
4. Prepare the transformer and immutable configuration.
5. Register the transformer via `inst.addTransformer(transformer, false)` or `true` when capabilities allow.
6. Register bounded shutdown/flush handling.
7. Log startup status **after** completing the relevant step; if a mandatory resource is unavailable, fail clearly according to policy.

### `premain` vs. `agentmain`

- `Premain-Class` is used when the JVM starts with `-javaagent`.
- `Agent-Class` is used when the runtime supports loading an agent after the JVM has already started; the corresponding entry point is typically `agentmain`.
- With late attach, some classes have already been defined **before** the transformer is registered. Registration **does not replay** past class-load callbacks; handling already-loaded classes requires the `retransformClasses`/`redefineClasses` capability and separate testing.
- Java instrumentation classes are typically loaded by the system class loader, but production environments may have complex loader/module hierarchies. Do not turn a lab assumption into a rule for every runtime.

Do not enable retransform/redefine capabilities just because an agent has a transformer. If the lab only handles **new class loads** and `addTransformer(..., false)`, the manifest **does not need** `Can-Retransform-Classes` or `Can-Redefine-Classes`.

## 5. Transformer: transforming bytes, not a telemetry library

`ClassFileTransformer` has the Java 9+ callback:

```java
@Override
public byte[] transform(
        Module module,
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        java.security.ProtectionDomain domain,
        byte[] classfileBuffer) {
    // ...
}
```

This is an **illustrative method** with an incomplete body. When `transform` returns `null`, the JVM keeps the current bytes at this layer. When it returns new bytes, the JVM passes them to subsequent transformers and then verifies the final classfile. **Do not mutate `classfileBuffer` in place**.

The transformer needs to:

- **Filter early** by class/package/loader/module, excluding the agent/helper and SDK.
- Create a bytecode writer/visitor/buffer **per invocation**; multiple threads can invoke the transformer concurrently.
- Avoid referencing the class currently being defined via `Class.forName`, as this can cause recursion/circularity.
- Keep the class → transform rule mapping tight, with versioning/idempotence to avoid inserting duplicate probes across redefines.
- Never perform HTTP calls, file flushes, or wait on worker threads under the class-loading lock.
- Keep transform logic purely testable: `transform(inputBytes, config) → newBytes|null`.
- Verify output classfiles and compatibility with other transformers in the chain.

If using ASM/Byte Buddy on Java 17, those libraries belong in **agent core**, and should not be “shaded” into the bootstrap helper. On JDK 24+, the standard Class-File API `java.lang.classfile` can replace part of a bytecode library, but this lab targets Java 17+ so it **does not assume** JDK 17 has that API.

### Is `ClassFileTransformer` guaranteed to run exactly once per class?

No. A class can pass through the callback during initial loading and during redefine/retransform operations depending on capabilities. A transformer with `canRetransform=false` still receives a callback on **redefine**; on **retransform**, incapable output is reapplied by the JVM without invoking the incapable callback again. Do not use the callback count as a business event count or conclude that bytes were successfully installed solely from callback logs.

## 6. Helper: the small API actually seen by application bytecode

A transformer can insert a symbolic reference:

```text
invokestatic demo/bridge/ProbeBridge.hit:()V
```

This is an **instruction descriptor**, not a directly runnable Java source line. When the application method executes, the loader/module of the instrumented class itself must resolve `demo.bridge.ProbeBridge`. An agent running on the system loader **does not mean** a custom app loader can see every agent class.

Separating `bridge.jar` has advantages:

- Contains only the classes strictly needed for callsites.
- Allows adding the helper to the bootstrap search **without putting the entire agent core** there.
- Reduces the risk of bootstrap classes accidentally loading the wrong version of a JSON/logging library.
- Allows stabilizing the helper ABI independently of exporter/SDK changes.
- Facilitates `jdeps`, classpath inspection, and package collision QA.

The helper API should consist of a few strongly typed methods: `hit():void`, `record(long):void`, or `record(int,long):void`. Avoid passing webapp request objects, raw `ClassLoader` instances, custom SDK objects, or raw `Throwable` instances into a bootstrap helper that holds static references.

**A bootstrap helper must link only against classes defined by the bootstrap loader.** The JDK explicitly states there is no guarantee that all platform classes are bootstrap-defined. A bridge using only `java.lang.*` and `java.util.concurrent.atomic.LongAdder` from `java.base` is far easier to test than a bridge importing a rich exporter.

### `appendToBootstrapClassLoaderSearch`

The entry point can call:

```java
// Illustrative code in premain given inst and JarFile jar.
inst.appendToBootstrapClassLoaderSearch(jar);
```

The JAR is appended to the bootstrap loader's additional search path. This is an **append**, not an overwrite of already-defined classes or a retroactive fix for a symbolic reference that previously failed to resolve. The Javadoc warns to place only classes/resources intended for bootstrap in that JAR; if an application's package-private class is accidentally defined by bootstrap due to a name collision, `IllegalAccessError` can occur.

Choose a unique bridge package (for example `com.company.instrumentation.bridge.v1`) and **append before the first application class needs it**. When actually using a bootstrap helper, `Class.forName("demo.bridge.ProbeBridge", false, null)` succeeding and `getClassLoader()==null` is useful proof of loader identity.

**Not every helper must be on the bootstrap loader.** If you only instrument a class loader that can see the helper JAR via parent delegation or targeted loader injection, expanding the bootstrap search may be unnecessary. Base the decision on the application's actual topology.

### JPMS

The bootstrap-defined helper in this lab belongs to the **unnamed module of the bootstrap loader**, not the `java.base` module. For **named modules**, Java instrumentation has rules that add read edges for transformed classes' modules to support the helper. Being able to read the helper **does not automatically grant** deep reflection into every package; if the agent needs specific opens/exports, check `Instrumentation.redefineModule` or appropriate configuration.

The lab below uses **classpath/unnamed modules**, so it cannot be used as proof that every module-path/loader combination works without changes.

## 7. Collector: off the hot path with clear semantics

The collector is responsible for turning internal signals into usable data. There are at least three patterns:

| Data needed | What the bridge can hold | What the collector does | Limitations |
| --- | --- | --- | --- |
| Total method calls | `LongAdder` | Periodic snapshot, export cumulative counters | Does not retain individual calls; `sum()` is not atomic under concurrent updates |
| Individual compact events | Bounded queue or bridge interface | Drain batches, retry, send to backend | A successful `offer` does not guarantee the backend persisted it |
| JVM timeline diagnostics | Custom `jdk.jfr.Event` | JFR recording/stream/file analysis | Depends on event enabled/threshold/retention settings |

In the lab, the helper **only increments a `LongAdder`**, while the collector reads the value periodically on a **daemon worker**, then flushes on normal JVM shutdown. That is a minimal, easily verifiable pipeline. **There is no remote exporter**: an in-JVM counter does not automatically appear in Prometheus/OpenTelemetry/a backend until an exporter is actually added.

### Distinguishing “collect” from “deliver”

```text
ProbeBridge.hit()
    → counter increment (in JVM)
    → collector snapshot (in JVM)
    → exporter encode/batch (if implemented)
    → network/file sink (if implemented)
    → backend accepts data (requires separate confirmation)
```

Some projects confuse `counter.increment()` with “metrics sent”. If a queue is full or the backend is down, data may be dropped or stale. You should separately track `attempted`, `accepted`, `dropped`, `exported`, `exportFailed`, and retry counts with exact semantics.

### Threads and shutdown

- Do not spawn **one thread per event**.
- The collector worker should have a managed lifecycle and bounded concurrency.
- If using a daemon worker, the JVM **does not wait** for the worker to finish when only daemon threads remain; you need a flush hook or a designed shutdown mechanism.
- Shutdown hooks do not run when the process is killed with `SIGKILL`, crashes severely, or is forcibly terminated; in-memory telemetry can be lost.
- In a shutdown hook, do not block indefinitely on a network sink; set timeouts/quotas and have a best-effort drop/flush plan.
- Do not hold strong references to plugin `ClassLoader`/`Class<?>` objects in a static helper, as this can cause leaks on app redeploy.

## 8. Complete Java 17+ Lab: entry + transformer + bridge + collector

We will build a sample with **clean class-loader boundaries**, runnable on JDK 17+ with **no external libraries**. It consists of:

1. `AgentEntry`: invoked by the JVM via `premain`, appends `bridge.jar`, starts the collector, registers the transformer.
2. `WatchingTransformer`: only observes `DemoApp` being defined by the JVM, maintaining an atomic flag; **does not modify class bytes**.
3. `ProbeBridge`: bootstrap helper, containing only a `LongAdder` and two public static methods.
4. `CounterCollector`: background sampler on a daemon worker; on shutdown, reads the final counter and prints the result.
5. `DemoApp`: three calls to `ProbeBridge.hit()` in source to **simulate post-instrumentation callsites**.

With this design, the transformer does not generate new bytecode. That is an **intentional limitation** of the example: it demonstrates packaging, loader linkage, and the observation pipeline; to actually insert `invokestatic` requires a valid bytecode transformation (ASM/Byte Buddy or the Class-File API from JDK 24) along with separate integration tests.

### 8.1. Directory structure

```text
four-part-agent-demo/
├── agent.mf
├── bridge-src/
│   └── demo/bridge/ProbeBridge.java
├── agent-src/
│   └── demo/agent/
│       ├── AgentEntry.java
│       ├── WatchingTransformer.java
│       └── CounterCollector.java
└── app-src/
    └── demo/app/DemoApp.java
```

After building, the artifacts are:

```text
out/
├── bridge/           # temporary classes for packaging bridge.jar
├── agent/            # temporary classes for packaging agent.jar
├── app/              # app classes, excluding helper at runtime
├── bridge.jar
└── agent.jar
```

The two JARs have clear responsibilities: `bridge.jar` contains **only** the bootstrap helper class; `agent.jar` contains the entry point, transformer, and collector (and any libraries the agent needs in a real version). The application runs with `-cp out/app`, without adding the bridge or agent JAR to the runtime app classpath.

### 8.2. `bridge-src/demo/bridge/ProbeBridge.java`

```java
package demo.bridge;

import java.util.concurrent.atomic.LongAdder;

public final class ProbeBridge {
    private static final LongAdder HITS = new LongAdder();

    private ProbeBridge() {
    }

    public static void hit() {
        HITS.increment();
    }

    public static long total() {
        return HITS.sum();
    }
}
```

Key points:

- The helper does not import `demo.agent.*`, a JSON library, a metrics SDK, or an HTTP client.
- `LongAdder` belongs to `java.base`, so it can be used on the bootstrap loader.
- `hit()` only increments, has very low overhead, and does not block on network I/O.
- `total()` is a counter snapshot for telemetry; `LongAdder.sum()` does not provide an atomic read across concurrent updates in progress.
- Do not create class loaders, threads, serializers, or network connections during static initialization.

The API consists of `hit:()V` and `total:()J`, making it easy for a real transformer to emit exact callsites. Do not place helpers in `java.*` or common collision-prone packages; `demo.bridge` is for experimentation only, and production should use an organization-specific name.

### 8.3. `agent-src/demo/agent/WatchingTransformer.java`

```java
package demo.agent;

import java.lang.instrument.ClassFileTransformer;
import java.security.ProtectionDomain;
import java.util.concurrent.atomic.AtomicBoolean;

public final class WatchingTransformer
        implements ClassFileTransformer {

    private final AtomicBoolean sawApp = new AtomicBoolean();

    @Override
    public byte[] transform(
            Module module,
            ClassLoader loader,
            String className,
            Class<?> classBeingRedefined,
            ProtectionDomain domain,
            byte[] classfileBuffer) {

        if ("demo/app/DemoApp".equals(className)) {
            sawApp.set(true);
        }

        // Do not modify classfileBuffer; JVM uses existing bytes.
        return null;
    }

    public boolean sawApp() {
        return sawApp.get();
    }
}
```

`AtomicBoolean` ensures the flag is visible from the collector/shutdown thread. The transformer **does not** print logs or send metrics inside the callback. It filters specifically on the internal name `demo/app/DemoApp` instead of scanning the entire JVM. If the JVM invokes the callback with `className==null` in special cases, `"literal".equals(className)` remains safe.

When the transformer is registered before `DemoApp` loads, normal class loading invokes the callback and sets `sawApp=true`. `return null` means no byte modification. **Do not** claim this lab injected bytecode.

### 8.4. `agent-src/demo/agent/CounterCollector.java`

```java
package demo.agent;

import demo.bridge.ProbeBridge;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;

public final class CounterCollector {
    private final WatchingTransformer transformer;
    private final AtomicLong lastSample = new AtomicLong();

    private final ScheduledExecutorService worker =
            Executors.newSingleThreadScheduledExecutor(task -> {
                Thread thread = new Thread(
                        task, "agent-counter-collector");
                thread.setDaemon(true);
                return thread;
            });

    public CounterCollector(WatchingTransformer transformer) {
        this.transformer = transformer;
    }

    public void start() {
        // Periodic work on a dedicated thread, not at business callsites.
        worker.scheduleAtFixedRate(
                () -> lastSample.set(ProbeBridge.total()),
                0, 200, TimeUnit.MILLISECONDS);
    }

    public void stopAndReport() {
        worker.shutdownNow();

        // Final read after application main has completed.
        long finalCount = ProbeBridge.total();
        lastSample.set(finalCount);

        System.out.println(
                "collector: saw-app=" + transformer.sawApp());
        System.out.println(
                "collector: total-hits=" + finalCount);
    }
}
```

Details to understand:

- `CounterCollector` **is a rich agent-side class**; it can depend on the bridge API, but the bridge **must not depend back** on the collector.
- `AtomicLong lastSample` holds the most recent value read by the background worker. In production it could be forwarded to an exporter; the lab only verifies the internal pipeline.
- The worker is a **daemon thread** so it does not keep the JVM alive after the application finishes.
- The 200 ms period is only a lab parameter, **not** a recommended production scrape interval.
- `stopAndReport()` calls `shutdownNow()`, then reads `finalCount` directly from the helper. Thus stdout **does not depend** on whether the background worker had time to run a cycle.
- `shutdownNow()` only requests the task to stop, not a guarantee it has terminated immediately; the lab worker only reads a counter and has no network flush to wait on. A production exporter needs a close/awaitTermination protocol with a timeout and policy-defined flush confirmation.
- Do not report the final count using `lastSample.get()` when the background worker might lag: that value could be stale. Use `finalCount` read after the business calls in the lab.

### 8.5. `agent-src/demo/agent/AgentEntry.java`

```java
package demo.agent;

import java.lang.instrument.Instrumentation;
import java.nio.file.Path;
import java.util.jar.JarFile;

public final class AgentEntry {
    private static JarFile bridgeJar;

    public static void premain(String options, Instrumentation inst)
            throws Exception {

        if (options == null || options.isBlank()) {
            throw new IllegalArgumentException(
                    "Agent option must be a bridge.jar path");
        }

        // 1. Place helper on bootstrap search BEFORE app loads.
        bridgeJar = new JarFile(Path.of(options).toFile());
        inst.appendToBootstrapClassLoaderSearch(bridgeJar);

        // 2. Verify actual loader, not just JAR location.
        Class<?> bridge = Class.forName(
                "demo.bridge.ProbeBridge", false, null);
        if (bridge.getClassLoader() != null) {
            throw new IllegalStateException(
                    "ProbeBridge must be bootstrap-defined");
        }
        System.out.println("agent: bridge-loader=bootstrap");

        // 3. Initialize collector before registering transformer.
        WatchingTransformer transformer = new WatchingTransformer();
        CounterCollector collector = new CounterCollector(transformer);
        collector.start();
        System.out.println("agent: collector=started");

        // 4. Stop collector on normal JVM shutdown.
        Runtime.getRuntime().addShutdownHook(
                new Thread(collector::stopAndReport,
                        "agent-shutdown"));

        // 5. Register transformer for new class-load events.
        inst.addTransformer(transformer, false);
        System.out.println("agent: transformer=registered");
    }
}
```

The code clearly shows that **the entry point is the wiring layer**, needing no bytecode generation, mutable global queues, or exporter code. `JarFile` is held via a static reference in the demo; **do not close it early** before the bootstrap search no longer needs the JAR. In a real system, design appropriate lifecycle and open file handle management.

When `premain` fails due to an invalid path/JAR, JVM agent startup can fail **before** application `main`. This is fail-fast for the lab's mandatory configuration. Do not turn a critical missing-bridge error into a harmless log and continue loading instrumented classes with unresolvable symbolic references.

### 8.6. `app-src/demo/app/DemoApp.java`

```java
package demo.app;

import demo.bridge.ProbeBridge;

public final class DemoApp {
    public static void main(String[] args) {
        System.out.println(
                "app: bridge-loader=" +
                (ProbeBridge.class.getClassLoader() == null
                        ? "bootstrap" : "other"));

        // Simulate 3 callsites that a real transformer could insert.
        ProbeBridge.hit();
        ProbeBridge.hit();
        ProbeBridge.hit();

        System.out.println(
                "app: hits=" + ProbeBridge.total());
    }
}
```

The helper calls here are compiled directly into `DemoApp` by `javac`. They are **not** added by `WatchingTransformer`, because the lab's transformer returns `null`. That does not diminish the value of verifying the boundary: both the application and the rich-side collector see **the same bootstrap-defined helper**.

### 8.7. `agent.mf`

```text
Manifest-Version: 1.0
Premain-Class: demo.agent.AgentEntry

```

Keep the trailing blank line of the manifest main section. Do not declare retransform/redefine capabilities since they are not used. If the agent later needs to process already-loaded classes, evaluate adding `Can-Retransform-Classes`/`Can-Redefine-Classes`, checking `Instrumentation.is*Supported()`, and reviewing schema/JVM limitations.

In the lab, the `bridge.jar` path is passed via **agent options**; we do not set `Boot-Class-Path` in the manifest. This is a transparent setup so learners can see the exact moment `appendToBootstrapClassLoaderSearch` occurs.

### 8.8. Building and running on Bash (Linux/macOS/Git Bash)

From the `four-part-agent-demo` directory:

```bash
mkdir -p out/bridge out/agent out/app

# Compile the helper independently, with only the JDK.
javac -encoding UTF-8 -d out/bridge \
    bridge-src/demo/bridge/ProbeBridge.java
jar --create --file out/bridge.jar -C out/bridge .

# Compile agent core with bridge.jar on the COMPILE classpath.
javac -encoding UTF-8 -cp out/bridge.jar -d out/agent \
    agent-src/demo/agent/WatchingTransformer.java \
    agent-src/demo/agent/CounterCollector.java \
    agent-src/demo/agent/AgentEntry.java

# Package only agent classes; do not copy bridge into agent.jar.
jar --create --file out/agent.jar \
    --manifest agent.mf -C out/agent .

# App sees the bridge API at compile time.
javac -encoding UTF-8 -cp out/bridge.jar -d out/app \
    app-src/demo/app/DemoApp.java

# Runtime app classpath does NOT include bridge.jar or agent.jar.
java -javaagent:out/agent.jar=out/bridge.jar \
    -cp out/app demo.app.DemoApp
```

Compiling both **agent core** and **app** requires the bridge API. However, placing the bridge JAR on the **compile classpath** differs from runtime loading: in the `java` command, the bridge is only introduced via `-javaagent` options and then appended to bootstrap by the entry point. This helps the demo catch packaging/loader bugs instead of accidentally finding the helper on the app classpath.

### 8.9. Building and running on PowerShell (Windows)

```powershell
New-Item -ItemType Directory -Force `
    -Path out/bridge, out/agent, out/app | Out-Null

javac -encoding UTF-8 -d out/bridge `
    bridge-src/demo/bridge/ProbeBridge.java
jar --create --file out/bridge.jar -C out/bridge .

javac -encoding UTF-8 -cp out/bridge.jar -d out/agent `
    agent-src/demo/agent/WatchingTransformer.java `
    agent-src/demo/agent/CounterCollector.java `
    agent-src/demo/agent/AgentEntry.java

jar --create --file out/agent.jar `
    --manifest agent.mf -C out/agent .

javac -encoding UTF-8 -cp out/bridge.jar -d out/app `
    app-src/demo/app/DemoApp.java

java -javaagent:out/agent.jar=out/bridge.jar `
    -cp out/app demo.app.DemoApp
```

PowerShell uses backticks for line continuation. Do not add `out/bridge.jar` to `-cp` at runtime because that would mask the goal of testing the bootstrap bridge. `java`, `javac`, and `jar` must all be from JDK 17+ or a compatible JDK; do not run Java 17 source with JDK 8.

### 8.10. Expected stdout in a normal lab environment

```text
agent: bridge-loader=bootstrap
agent: collector=started
agent: transformer=registered
app: bridge-loader=bootstrap
app: hits=3
collector: saw-app=true
collector: total-hits=3
```

Why is the output deterministic by design?

1. `premain` appends and checks `ProbeBridge` **before application main runs**.
2. The collector starts **before** `addTransformer`, without depending on later callbacks.
3. `DemoApp` is a new class load after `premain`, whose internal name matches `WatchingTransformer`'s filter.
4. `ProbeBridge` has a shared static counter because it is the same bootstrap-defined class.
5. The app calls `hit()` **three times sequentially** and prints 3.
6. The agent installs a shutdown hook; when the JVM stops normally, the hook reads the final counter and transformer flag and prints the two collector lines.
7. The periodic daemon worker **does not print logs**, so stdout order does not depend on the 200 ms period.

If the runtime is forcibly killed, the JAR is wrong, agent startup fails, or other agents print logs, actual stdout may differ. That is not a reason to write a “hard expectation” for an unverified environment. If the app spawns additional threads calling `hit()` concurrently or calls `main` again, the final counter may change.

### 8.11. Inspecting artifacts and the dependency graph

Use the JDK's own tools:

```bash
jar --list --file out/bridge.jar
jar --list --file out/agent.jar
jdeps -verbose:class out/bridge.jar
javap -classpath out/bridge.jar -p demo.bridge.ProbeBridge
javap -classpath out/app -c demo.app.DemoApp
```

Expected invariants:

- `bridge.jar` contains `demo/bridge/ProbeBridge.class` and minimal JAR metadata; it **does not** contain `demo/agent/`, `net/bytebuddy/`, or JSON/HTTP libraries.
- `agent.jar` contains `demo/agent/AgentEntry.class`, `WatchingTransformer.class`, `CounterCollector.class`, and the manifest with `Premain-Class`; it **does not** contain `demo/bridge/ProbeBridge.class`.
- `jdeps` on the bridge reports dependencies only on `java.base` classes, pulling in no rich exporter.
- `javap -c demo.app.DemoApp` shows `invokestatic demo/bridge/ProbeBridge.hit:()V` calls from the app source, **not inserted by the transformer**.
- `Class.getClassLoader()==null` in both the agent and the app confirms the helper is bootstrap-defined at runtime.

`jdeps` only inspects static dependencies in bytecode. It **does not** fully detect dynamic reflection, resource lookups, or dependencies loaded at runtime by plugin frameworks. You must still smoke-test on target class loaders/modules.

## 9. Four components need four separate test suites

### Entry point

- Missing `Premain-Class`, wrong class name, invalid `premain` method.
- Invalid agent options or nonexistent helper JAR.
- Can it open the bootstrap JAR and verify the canonical helper loader?
- Is startup status recorded accurately after components are ready?
- If a mandatory component fails, what fail-open/fail-closed policy do the JVM/app follow?

### Transformer

- Does it accurately filter class name, loader, module, and method descriptor?
- Is it registered before target classes are loaded?
- Does `return null` truly leave bytes unmodified?
- For transformers that emit bytes: is output valid, preserving labels/stack maps, annotations, and method behavior?
- Thread safety under concurrent class loading; no shared mutable bytecode writer?
- Idempotence across multiple redefine/retransform cycles and multiple agents?
- Does it avoid instrumenting the agent/helper/exporter's own packages?

### Helper

- Do bootstrap or target loaders see a single `ProbeBridge` class?
- Do public method descriptors match the symbolic references in bytecode?
- Does it avoid importing rich agent classes/SDKs?
- No blocking, no excessive allocations, and no network calls on the hot path?
- ABI compatibility across upgrades; no static caches retaining plugin class loaders?
- Thread-safe under concurrent method invocations?

### Collector/exporter

- Does it snapshot/drain the right data and units?
- Does the worker avoid keeping the JVM alive unnecessarily; do shutdown hooks/flushes have timeouts?
- On exporter errors, timeouts, backend downtime, or full queues, which data is lost?
- Are there metrics for attempted/dropped/failed/retried?
- Does it avoid sending PII/secrets or retaining data past retention policies?
- Does the collector avoid altering business method exceptions or return values?

**Testing only that the agent starts up is not enough.** Nor is seeing the `transform(...)` callback without testing the helper callsite. You must test **each boundary** as well as the full execution chain.

## 10. Data transfer models between helper and collector

### 10.1. Pull: collector reads counters/histograms in the bridge

```text
Business thread ──> ProbeBridge.hit() ──> LongAdder
                                             ▲
                                        periodic poll
                                             │
                                      CounterCollector
```

Pros: minimal dependencies and allocations; the bootstrap helper can stand alone. Cons: holds only aggregates; `LongAdder.sum()` does not strictly linearize all in-flight updates. For production metrics, cumulative counters are typically exported and the backend computes rates over time windows; restarts/resets must be handled.

### 10.2. Push: helper enqueues compact events

```text
Business thread ──> ProbeBridge.offer(code, elapsed)
                             │
                       bounded queue
                             │
                             ▼
                      worker/exporter
```

If per-event retention is required, a bounded queue can be appropriate. However, do not use `BlockingQueue.put()` on the hot path without analyzing backpressure: when the queue is full, business threads can block. `offer()` does not wait but can return `false`; you need a dropped counter, sampling, or an explicit policy. Enqueuing a record in heap **is not** a guarantee the backend persisted it; power loss or crashes can wipe unsent data.

The bridge can define a small `BridgeSink` interface and the rich agent side can implement an enqueue-only sink. **Caution:** invoking that interface from the helper runs on the business thread; if the implementation performs synchronous HTTP, separating JARs will not solve latency. A `static` sink reference can keep the agent/plugin loader alive; proper `install/uninstall` lifecycle and JMM synchronization are required.

### 10.3. Runtime diagnostics: JFR Event

With JDK 17+, a custom `jdk.jfr.Event` can record duration/fields when a JFR recording is enabled. JFR is well suited for JVM diagnostics and correlation with GC/locks/threads; it is not an HTTP metrics exporter or a durable audit log. Creating/committing events should have enabled/threshold guards and payload controls. If JFR is needed in a bootstrap helper, verify **loader/module visibility of `jdk.jfr`** rather than assuming every platform module is bootstrap-defined. Keeping the bridge minimal reduces risk.

## 11. Source separation and dependency direction in Maven/Gradle

A large project can be organized into:

```text
project/
  agent-bridge/          # bridge.jar, java.base only
  agent-core/            # AgentEntry, Transformer, Collector
  agent-integration/     # JVM tests running -javaagent and custom loaders
  example-app/           # app needing only the bridge API at compile time
```

Dependency rule:

```text
agent-core ──(compile API)──> agent-bridge
example-app ──(compile API)──> agent-bridge

agent-bridge ──X──> agent-core
agent-bridge ──X──> Byte Buddy / JSON / HTTP / telemetry SDK
```

Do not blindly use `implementation`/fat-JAR configurations that cause the build tool to copy `ProbeBridge.class` into **both JARs**. In a Gradle project you might choose `compileOnly` or another dependency scope depending on packaging; Maven has `provided` for certain cases. **There is no single default scope that fits every build tool**: what you must verify is the output artifact and runtime class-loader behavior, not just the scope name.

If agent core uses shading/relocation to avoid ASM/Byte Buddy/JSON library conflicts with the app, apply it to the **rich agent JAR** with proper resource/service-loader rules. **Do not** put the entire shaded fat agent JAR on the bootstrap search. If using a multi-release JAR to support multiple JDKs, check `Multi-Release: true`, class-file versions, and actual class selection on target JDKs; this lab does not use multi-release.

### The manifest is part of the artifact, not just a text file

For an agent JAR, the JVM reads `META-INF/MANIFEST.MF`. A JAR can contain `AgentEntry.class` yet lack `Premain-Class`, causing `-javaagent` to fail. Inspect the manifest **after packaging**, not just `agent.mf` in the source tree.

Similarly, if using `Boot-Class-Path` instead of `appendToBootstrapClassLoaderSearch`, relative paths are resolved according to the specification and must be tested with the **actual deployment locations** of `agent.jar` and `bridge.jar`. Moving a JAR after building without updating paths can cause the agent to start differently than expected.

## 12. Common production deployment pitfalls

### 12.1. ABI-incompatible bridge versions

An inserted call might be:

```text
invokestatic demo/bridge/ProbeBridge.hit:()V
```

If a new version changes this to `hit(int)` and removes the old method, instrumented classes can hit `NoSuchMethodError` when the JVM resolves the callsite. Keep the bridge API stable or version the package/deploy via controlled migration. `appendToBootstrapClassLoaderSearch` does not replace a class of the same name already defined by bootstrap.

### 12.2. Helper only visible to the system loader

If the agent JAR contains `ProbeBridge`, classes in a custom loader whose parent is bootstrap/platform still cannot see it. **Do not assume** `-javaagent` makes all class loaders automatically read agent libraries. If multiple loaders are involved, use a minimal bootstrap helper or a verified injection mechanism into the appropriate loader.

### 12.3. Wrong initialization order

If the transformer has already inserted `ProbeBridge.hit()` callsites but the bridge is not yet on the loader search, the JVM can fail during linking. If the helper calls the collector before the collector is ready, a `NullPointerException` or lost events can occur. Choose a well-defined fallback and append/initialize before registering the transformer.

### 12.4. Duplicate classes across artifacts

The same binary name in two defining loaders can create two static counters or cause `ClassCastException`/loader constraint errors. Keep the bridge JAR canonical and do not copy bridge classes into the rich JAR. Use `jar --list` and `Class.getClassLoader` to prove it rather than just looking at the POM.

### 12.5. Collector breaking business logic

If the helper calls an exporter/network, a backend timeout can slow down or fail business methods. Move heavy processing to a worker. For best-effort telemetry, define fail-open behavior and a dropped counter. For legally or financially mandatory data, best-effort telemetry is insufficient: you need durable transactional records and reliable delivery.

### 12.6. Agent instrumenting itself

A transformer with an overly broad package filter can instrument loggers/serializers/helpers, and then an export callback invokes an instrumented method, creating recursion/`StackOverflowError` or a class-loading deadlock. Exclude agent/bridge/bytecode SDK/sink packages, and check reentrancy and bootstrap load order.

### 12.7. Incorrect shutdown lifecycle

Do not assume every JVM stop invokes shutdown hooks. `kill -9`, hard crashes, or forcibly killed containers can lose data. Do not let shutdown hooks block indefinitely. Removing a transformer also does not automatically strip already-inserted probes from running classes; the helper ABI may need to remain intact until JVM restart.

### 12.8. Separating classes while still sharing mutable global state

Four separate files can still produce a poor design if they all use a non-thread-safe `static HashMap` or share one `ByteArrayOutputStream` across concurrent transformer callbacks. Classfile writers must be per-invocation; counters must use atomic/concurrent structures; configs must use immutable snapshots. `ConcurrentHashMap` prevents map corruption but does not by itself solve unbounded cardinality and memory leaks.

## 13. Common errors and diagnostics

| Symptom | Possible cause | Check |
| --- | --- | --- |
| `Premain-Class` not found | Wrong agent JAR manifest or class package | `jar --list`, inspect `META-INF/MANIFEST.MF` |
| Agent does not start | Wrong `-javaagent` path/options, `premain` throws | Check startup stderr and JAR deployment |
| `ClassNotFoundException` on bootstrap lookup | Wrong `bridge.jar` path or missing class entry | `JarFile`, `jar --list`, internal/binary name |
| `NoClassDefFoundError` at probe | Target's loader cannot see helper or helper's dependencies | `getClassLoader`, `jdeps`, bootstrap append timing |
| `IllegalAccessError` | Runtime package/module/loader differs from expectation | Class access flags, JPMS read/opens/exports |
| `NoSuchMethodError` | Helper ABI differs from callsite | `javap`, owner/name/descriptor, version skew |
| App has counter but collector sees nothing | Two helper copies in two loaders or collector reads wrong registry | Print loader identity, check duplicate JARs |
| `collector: saw-app=false` in lab | Transformer registered late, wrong class name, or agent not run as instructed | Verify registration before app load and filter |
| `collector: total-hits=0` | Callsite missing, app does not call helper, or different helper identity | `javap -c`, `getClassLoader`, call count |
| Metric increments but backend is empty | No exporter or exporter failing | Distinguish in-process counter from remote delivery |
| Slow startup | Class parser/exporter running synchronously in transformer | Profiling/JFR, reduce locks/I/O |
| JVM does not exit | Non-daemon collector still alive, improper shutdown | Worker thread factory, `shutdown`/timeout |
| Events lost on crash | Unflushed in-memory state/queue | Durability/retention/ack policy |
| Duplicate probes after redefine | Non-idempotent transformer | Compare output bytecode/markers and chain order |
| Memory leak after redeploy | Static helper/collector retains `ClassLoader`, `Class<?>`/plugin object | Heap dump, weak/eviction/close |
| Callbacks fire but no probes | Transformer returns `null` or unchanged output | Distinguish callback from bytecode transformation |

One diagnostic principle: **identify which boundary failed before fixing**. If the fault is bootstrap class visibility, increasing exporter retries will not help. If the fault is the network sink, fixing ASM stack maps will not solve it. Separating the four components helps pinpoint where the failure originates.

## 14. QA workflow and release checklist

### Step A — Source/architecture checks

1. Entry point does not unnecessarily import helper implementations before bootstrap setup.
2. Transformer does not reference application runtime classes via the wrong class loader.
3. Helper does not import agent core or non-bootstrap-visible libraries.
4. Collector owns the worker, exporter/serializer, and lifecycle; no I/O in helper `hit`.
5. Public helper API has versioned and reviewed method descriptors.
6. Config/filters are published thread-safely, and transformer writers/contexts are per-invocation.

### Step B — Build artifact checks

1. `bridge.jar` contains only the expected bridge classes/resources.
2. `agent.jar` has the right `Premain-Class` and all required agent classes.
3. No duplicate bridge classes across agent/bridge JARs.
4. Use `jdeps` to inspect static dependencies of the bridge.
5. `javap` app/test classfiles to inspect callsite owner/name/descriptors.
6. Verify class-file major version compatibility with the production JDK.
7. If using shading/relocation, test service resources and package collisions.
8. Sign/verify checksums if deployment requires it; load only trusted agents.

### Step C — Runtime checks

1. App runs **without the bridge on runtime `-cp`**, with the bridge appended early.
2. Print/test the helper's loader identity to confirm the canonical bootstrap class.
3. Transformer sees target classes; the app behaves the same as before instrumentation.
4. Counter/helper from the app and the rich-side collector reflect the same state.
5. Test with custom loaders/named modules if production uses them.
6. For real transformers, verify class bytes, stack maps, and exception paths.
7. Benchmark latency, CPU, allocation, GC, and class-load overhead.
8. Test concurrency, redefine/retransform, multiple agents, and error/failover.

### Step D — Operational checks

1. Endpoint/credential configs do not reside in the bootstrap helper.
2. Collector has timeouts, retry/backpressure/retention, and error monitoring.
3. Dropped/export-failure metrics exist; do not treat `offer(true)` as a delivery ack.
4. Worker threads/shutdown hooks do not hang the JVM indefinitely.
5. Do not send PII, request bodies, or secrets unless explicitly permitted by policy.
6. Have canary/rollback plans and understand the limits of `removeTransformer`.
7. Do not log every JVM class or full byte arrays by default.
8. Document which JDK/agent/bridge version combinations are compatible.

## 15. Misconceptions to eliminate

**Misconception 1: “Splitting one `Agent` class into four classes means the architecture is separated.”**  
False. If the bridge still imports the exporter or instrumented classes still call the rich agent directly, dependency boundaries have not changed.

**Misconception 2: “The class transformer is called every time an application method runs.”**  
False. `transform` handles class definitions/updates; the helper callsite runs on the business execution path.

**Misconception 3: “`-javaagent` makes every custom class loader see all agent classes.”**  
False. You must account for bootstrap/system/custom loader visibility properly.

**Misconception 4: “`appendToBootstrapClassLoaderSearch` should receive the entire fat agent JAR.”**  
False. Javadoc warns to append only classes/resources intended for bootstrap; a fat JAR easily causes package/version/loader errors.

**Misconception 5: “The more capabilities the helper has, the better.”**  
False. A wider helper API brings more dependencies, overhead, security risks, and compatibility issues.

**Misconception 6: “`addTransformer` succeeding means application code has been modified.”**  
False. Callbacks may not fire for already-loaded classes; it can also return `null` and produce no new output.

**Misconception 7: “Counter incrementing means metrics have been sent to the backend.”**  
False. Collector/exporter and remote delivery are separate steps.

**Misconception 8: “A daemon collector is guaranteed to flush when the process exits.”**  
False. Daemon threads do not keep the JVM alive; shutdown hooks are only best-effort during normal shutdown.

**Misconception 9: “`LongAdder.sum()` is an atomic snapshot in all situations.”**  
False. It may exclude concurrent updates in progress; it fits aggregate metrics, not a transaction ledger.

**Misconception 10: “Running the collector directly inside `ProbeBridge.hit()` is simpler and fast enough.”**  
Not by default. Network/serialization can block business threads, causing tail latency and recursion.

**Misconception 11: “Having a bridge JAR eliminates all JPMS issues.”**  
False. Loader visibility, module read edges, and access/opens are separate requirements.

**Misconception 12: “Removing the transformer reverts all instrumented classes.”**  
False. `removeTransformer` does not automatically undo bytes already applied by the JVM.

**Misconception 13: “The lab already performs real bytecode injection because the transformer registers successfully.”**  
False. `WatchingTransformer` returns `null`, and `DemoApp` calls the helper from source. The lab focuses on packaging and 4-way separation.

**Misconception 14: “Replacing `hit():void` with `hit(int):void` does not affect old classes.”**  
False. Bytecode still calling `hit:()V` can fail with `NoSuchMethodError`.

**Misconception 15: “A helper with the same name in two JARs always shares static state.”**  
False. If defined by two different loaders, they can be two independent runtime types and counters.

## 16. Packaging scenarios

### Scenario A — Simple metrics agent needing only total request counts

Use a small bootstrap bridge with `LongAdder` or a minimal histogram; a rich collector reads periodically and exports. No per-event queue is needed. The lab is the foundation of this design. For very high throughput, measure lookup/counter overhead before adding dynamic tags.

### Scenario B — Tracing agent wanting to send individual events

The bridge should have a `record(int code,long elapsedNanos)` with a small payload or an interface/tiny bounded buffer. The rich collector drains and batches. Filtering/sampling/overflow are explicit policies. Do not pass raw `HttpServletRequest`/custom-loader objects into a static bridge cache.

### Scenario C — Instrumenting a framework with multiple class loaders

Separate a bootstrap bridge JAR so target loaders can resolve the same public API; verify parent delegation, JPMS, and helper identity. The bytecode transformer remains in agent core. Do not rely on an exporter library on the system classpath always being visible to targets.

### Scenario D — JFR diagnostics without an immediate remote exporter

If only JVM diagnostics are needed, consider JFR Events with enabled/threshold guards and recording/streaming, minimizing custom data-plane code. However, verify the module/class loader of JFR supporting classes before placing code in the bootstrap helper; do not assume the helper can arbitrarily link to platform modules.

### Scenario E — Agent attaching to an already-running JVM

Ensure `Agent-Class`/`agentmain`, runtime startup support, and proper capabilities. Already-loaded classes do not automatically replay when registering a transformer; you must select target classes and check modifiability/capabilities before transforming. Do not treat a startup-only `premain` sample as proof for attach scenarios.

### Scenario F — Transaction auditing where no data may be lost

Counters, in-memory queues, or JFR are not durable sources of truth. Choose a transaction log/transactional outbox/acknowledged durable sink suited to the requirements. A Java agent can provide auxiliary diagnostic data, but does not replace mandatory persistence policies.

## 17. Self-check questions

**1.** What are the four roles that need to be separated?  
**Answer:** Agent entry point, class-file transformer, helper invoked from instrumented methods, and collector/exporter processing data off the hot path.

**2.** Why must a bootstrap helper not import an HTTP exporter from agent core?  
**Answer:** The bootstrap loader does not see system/agent loader classes by default; that dependency can cause link errors while also increasing business-path overhead.

**3.** When does the JVM invoke `premain`?  
**Answer:** When starting with a valid startup agent, before application `main`.

**4.** Does `ClassFileTransformer.transform` run on every request?  
**Answer:** No. It handles class definitions/updates; probe/helper callsites run when business methods execute.

**5.** Why is `bridge.jar` absent from `-cp` in the lab's runtime command?  
**Answer:** To prove the helper is found by the JVM via the bootstrap search appended by the agent, rather than being masked by the system classpath.

**6.** Does a bootstrap-defined `ProbeBridge` automatically become a `java.base` class?  
**Answer:** No. It belongs to the unnamed module of the bootstrap loader.

**7.** Does `collector: total-hits=3` prove metrics have reached a remote backend?  
**Answer:** Not yet. The lab only snapshots/prints numbers inside the JVM, with no HTTP exporter.

**8.** Why does the collector use a daemon worker and a shutdown hook?  
**Answer:** The daemon does not keep the JVM alive; the hook reads/flushes the final count on normal JVM shutdown. Shutdown hooks do not run in all kill/crash scenarios.

**9.** Why does `WatchingTransformer` have `AtomicBoolean sawApp`?  
**Answer:** The flag is updated by the class-loading callback thread and read by the collector/shutdown thread, so concurrent-safe state is used.

**10.** If `WatchingTransformer` returns `null`, has the class had `ProbeBridge.hit()` injected?  
**Answer:** No. In the lab the callsite is compiled from application source; real injection requires the transformer to return valid new bytes.

**11.** To transform classes already loaded before `premain`/attach, is registering a transformer enough?  
**Answer:** No. Class-load events do not replay automatically; retransform/redefine is needed when supported and permitted.

**12.** Can we bundle all of agent core into `bridge.jar` to deploy fewer files?  
**Answer:** You should not when the bridge is appended to bootstrap; Javadoc warns of misdefining classes and non-bootstrap-visible dependencies.

**13.** If the backend is unavailable, where should it be handled?  
**Answer:** The collector/exporter handles timeout/retry/drop/queue policies; do not block directly on the helper hot path for best-effort telemetry.

**14.** How do you verify the bridge JAR does not pull in external libraries?  
**Answer:** Use `jar --list`, `jdeps`, and runtime loader tests; do not rely solely on build configuration.

**15.** Why is a static map in a bootstrap helper holding a webapp `ClassLoader` dangerous?  
**Answer:** It can prevent old deployments from being garbage-collected after redeploy, causing a class-loader leak.

**16.** When using Gradle/Maven, what matters more than the dependency scope name?  
**Answer:** Actual artifacts and the loader graph: the bridge JAR has only bridge classes, the agent JAR has no duplicates, and runtime resolves the right identity.

**17.** Why can't a single startup lab prove that attach or named modules all work?  
**Answer:** Attach has a different lifecycle/already-loaded classes; named modules have distinct read/opens/exports rules, requiring environment-specific integration tests.

**18.** Is seeing `transformer: registered` in the logs enough to declare “instrumentation complete”?  
**Answer:** No. You must verify callbacks, JVM acceptance of bytes, callsite execution, and data collection/export as required.

## 18. References

- [JDK 17 — `java.lang.instrument` package](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): `Premain-Class`, `Agent-Class`, `Boot-Class-Path`, `premain`/`agentmain`, class loaders, bootstrap supporting classes, and JPMS.
- [JDK 17 — `Instrumentation`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `addTransformer`, `appendToBootstrapClassLoaderSearch`, retransform/redefine capabilities, and loader search limitations.
- [JDK 17 — `ClassFileTransformer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): callbacks, chaining, `return null`, and input buffer preservation requirements.
- [JDK 17 — `ClassLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): delegation and defining/initiating loaders.
- [JDK 17 — `LongAdder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html): counters and snapshot limitations under concurrent updates.
- [JDK 17 — `ScheduledExecutorService`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html): periodic sampling tasks and worker lifecycle.
- [JDK 17 — `Runtime.addShutdownHook`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html#addShutdownHook(java.lang.Thread)): shutdown hooks and operating conditions.
- [JVMS 17 — Loading, Linking and Initialization](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): class identity, loader constraints, and symbolic reference resolution.

**Remember:** **Entry point wires**, **transformer handles classfiles**, **helper does minimal work on the hot path**, and **collector processes data off the hot path**. For multi-loader applications, package a minimal bootstrap **bridge JAR** separate from the rich agent JAR; verify ABI, manifest, loader/module behavior, and startup order with real JVM tests. A registered callback, an incremented counter, and backend-accepted data are **three distinct pieces of evidence** — do not conflate them into a single “instrumentation OK” status.
