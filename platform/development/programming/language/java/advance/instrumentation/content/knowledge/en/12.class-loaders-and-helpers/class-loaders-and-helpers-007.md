# Separating the Minimal Helper from the Dependency-Heavy Agent

> **Goal:** Design Java instrumentation so that code injected into the application only needs to call a **small and stable helper**, while `premain`, bytecode transformers, logging, exporters, serialization, and complex libraries remain in the **agent runtime**. Understand class loader boundaries, transitive dependencies, `appendToBootstrapClassLoaderSearch`, JPMS, bootstrap helper limitations, and how to verify this with a Java 17+ experiment that builds two separate JARs.

This lesson belongs to the **Class loaders and helpers** group. It focuses on **helper call linkage** after the JVM has instrumented a class, without assuming all classes are loaded by the system class loader. A transformer can produce a valid class file, yet the application still fails at runtime because the class loader of the **transformed class** cannot find the helper that the transformer placed into the bytecode.

## 1. Why Separate Them?

A real-world Java agent typically contains:

- `Agent.premain(...)` or `agentmain(...)` to initialize the agent.
- `ClassFileTransformer`, ASM/Byte Buddy libraries, or the Class-File API to transform bytes.
- Class/method filters, policies, configuration, and feature flags.
- HTTP/gRPC exporters, batching, metrics/tracing SDKs, JSON serializers.
- Worker threads, loggers, caches, retries, and shutdown hooks.
- A **helper** that instrumented methods call very frequently.

Suppose the transformer inserts an instruction equivalent to:

```text
invokestatic example/agent/HeavyTracer.onEnter:()V
```

This is a **symbolic method reference notation**, not Java source or standalone assembler. When the application class runs, the JVM must resolve `example.agent.HeavyTracer` and the `onEnter()V` method through that class's class loader/module system. Even if the agent sees `HeavyTracer` on its own classpath, the application might not see it. If `HeavyTracer` in turn requires `com.vendor.HttpExporter`, `org.slf4j.*`, or a bytecode library, the helper's loader must also resolve that entire dependency graph.

A more reliable design:

```text
    Rich Java Agent Runtime              Minimal Bridge/Helper
  ┌──────────────────────────┐         ┌────────────────────────────┐
  │ premain / transformer    │         │ tiny public static API     │
  │ config, Byte Buddy/ASM   │         │ bootstrap-visible deps    │
  │ exporter / SDK / logging │         │ low overhead / no network  │
  │ batching / error policy  │         │ stable method descriptors  │
  └───────────┬──────────────┘         └──────────────▲─────────────┘
              │ setup/consume                     │
              └───────────────────────────────────┘
                                                  │ invokestatic
                                 ┌────────────────┴──────────────┐
                                 │ Instrumented application     │
                                 │ methods, custom class loader │
                                 └───────────────────────────────┘
```

The core idea is **dependency inversion**: the rich agent can know about the helper, but the helper **must not import** the rich agent. If data needs to be transferred, use counters, a bounded buffer, or a very small interface defined on the bridge side; do not pull exporters/networking directly into the application's execution path.

## 2. Comparing the Two Parts

| Criterion | Minimal Helper | Dependency-Heavy Agent Part |
| --- | --- | --- |
| Caller | Instrumented application methods | JVM calls `premain`, agent self-orchestrates |
| Role | Fast recording, keeping API for callsites | Bytecode generation, orchestration, data export |
| Loader | Where the target can reliably resolve it; sometimes bootstrap | System/agent-specific loader |
| Dependencies | Prefer `java.base`, no agent dependencies | Bytecode SDK, JSON, HTTP, metrics, logging |
| Frequency | Potentially millions of times/second | Per config/batch/transform pass |
| API | Small, clearly versioned, stable descriptors | Can change internally |
| Resources | Minimal allocation, non-blocking, no network | Threads, queues, file/network as needed |
| State | Counters or minimal state | Config, exporters, caches, retry policy |
| Risks | Loader mismatch, ABI, initialization | Dependency conflicts, lifecycle |
| Primary test | Does the JVM resolve the helper correctly? | Do the transformer and exporter work correctly? |

**A JAR with few bytes does not automatically mean the helper is truly minimal.** A class whose static initializer opens an HTTP connection is still a heavy helper. A helper consisting of a few methods and a `LongAdder` from `java.base` is easier to verify.

## 3. Runtime Class Identity: Same Name Does Not Mean Same Class

In the JVM, class identity depends on the **binary name and defining class loader**. Two different loaders can define the same name `example.bridge.ProbeBridge` yet create two independent runtime types:

```text
Loader L1: example.bridge.ProbeBridge → static counter A
Loader L2: example.bridge.ProbeBridge → static counter B
```

In that case, counter A does not share state with counter B. An interface in the agent loader and an interface with the same name from a plugin loader may be incompatible; casting between objects can throw `ClassCastException` even when the class names are identical. Loader constraints can also produce linkage errors.

### Common Loaders

- **Bootstrap class loader:** defines core classes and classes the agent intentionally adds to the bootstrap search. With `Class.getClassLoader()`, `null` represents the bootstrap loader.
- **Platform class loader:** handles a portion of platform modules; it is not a child of the system loader.
- **System/application class loader:** usually loads the application classpath and the main Java agent class.
- **Custom loaders:** plugin/app-server/servlet/OSGi/framework; may be parent-first, child-first, or have custom rules.

A custom loader whose parent is **bootstrap** or **platform** might not see classes that only reside in the agent's system loader. Likewise, a class defined by bootstrap does not automatically "look down" into the system loader to resolve an agent library.

This is why `javac` being able to compile the transformer and helper with a large classpath **does not prove** that the instrumented application class will be able to link the helper at runtime.

## 4. Why Must a Bootstrap Helper Only Depend on Bootstrap-Visible Classes?

The `java.lang.instrument` Javadoc specifies that supporting classes arranged by the agent to be defined by the **bootstrap loader** via `appendToBootstrapClassLoaderSearch` or `Boot-Class-Path` must only **link** to classes that are also defined by bootstrap. There is no guarantee that all platform classes can be defined by bootstrap.

Incorrect dependency boundary example:

```java
// ILLUSTRATIVE CODE — DO NOT USE.
package example.bridge;

import example.agent.runtime.RichExporter;
import com.vendor.json.JsonWriter;

public final class ProbeBridge {
    public static void hit() {
        RichExporter.send(JsonWriter.encode("hit"));
    }
}
```

Even if it compiles thanks to libraries on the classpath, the bootstrap loader may not see `RichExporter` and `JsonWriter` when the method is linked/executed. A common error is `NoClassDefFoundError`, though the exact cause and the moment the JVM detects it depend on bytecode/loader behavior. Do not solve this by appending the entire `agent-fat.jar` to bootstrap.

Better example:

```java
package example.bridge;

import java.util.concurrent.atomic.LongAdder;

public final class ProbeBridge {
    private static final LongAdder HITS = new LongAdder();

    private ProbeBridge() {}

    public static void hit() {
        HITS.increment();
    }

    public static long total() {
        return HITS.sum();
    }
}
```

`LongAdder` belongs to `java.base`, making it suitable for providing a minimal internal counter. `sum()` is **not an atomic snapshot** while other threads are still writing; that is normal for aggregate telemetry, not for a transaction ledger.

**Distinguish loader and module:** A `ProbeBridge` class defined by the bootstrap loader belongs to the **unnamed module of the bootstrap loader**; it does **not** automatically become a class in `java.base`. Do not place helpers in `java.*` packages or use names that easily collide with application/library packages.

## 5. What Should and Should Not Be in the Helper

A good bridge API typically has these properties:

1. A `public` class and `public static` methods with stable names/descriptors if bytecode calls them directly via `invokestatic`.
2. Simple parameters (`int`, `long`, `boolean`, occasionally normalized `String`), avoiding objects from plugin/tenant loaders.
3. No imports of `demo.agent.*`, observability SDKs, bytecode libraries, JSON serializers, or logging frameworks.
4. No creating network connections, writing files, or waiting on locks that could block inside methods injected into the hot path.
5. No `Thread.sleep`, `BlockingQueue.put`, or per-invocation request serialization.
6. No holding raw `ClassLoader`, `Class<?>`, `Throwable`, or request objects in unbounded static maps.
7. Minimal object allocation; if a queue is needed, make it bounded with a drop/backpressure policy.
8. Do not instrument the helper package or agent libraries to avoid recursion.
9. Do not perform classpath scanning or dependency injection in the bridge's `<clinit>`.
10. Deterministic behavior when the agent exporter is not ready: no-op, count, or drop with statistics.
11. A versioning strategy for methods already referenced by older bytecode.
12. Ensure normal telemetry failures do not alter business exceptions/return values according to operational policy.

Example descriptors for callsites:

```text
ProbeBridge.hit()           → ()V
ProbeBridge.record(long)    → (J)V
ProbeBridge.record(int,long)→ (IJ)V
```

This is a **signature table**, not runnable source. When a transformer inserts a call, the JVM needs the exact owner internal name, method name, and method descriptor. Changing `hit:()V` to `hit:(I)V` without updating existing classes will cause `NoSuchMethodError` even if the helper JAR is loaded successfully.

## 6. How to Choose Where to Place the Helper

| Deployment Approach | When to Use | Limitations to Test |
| --- | --- | --- |
| `appendToBootstrapClassLoaderSearch(JarFile)` | Helper must be visible to many loaders, including bootstrap | Only depend on bootstrap classes; append early; dedicated package |
| `Boot-Class-Path` in agent manifest | Startup agent knows the helper JAR path | Correct URI/path relative to agent JAR; same bootstrap restrictions |
| `appendToSystemClassLoaderSearch(JarFile)` | Target classes actually see the system loader | Custom loaders that do not delegate to system may not see it |
| Inject helper into target loader | Framework/plugin has its own loader and you want to limit scope | Class identity, duplicate definitions, loader lifecycle |
| Bundle helper into the application | Application actively integrates the API | Compatibility/versioning managed jointly by app and agent |

**There is no universally best choice.** Bootstrap is suitable when the helper is truly small and instrumented classes run in multiple loaders; it also expands the class-loading surface of the entire JVM. For applications using only a single fixed loader, packaging the helper where that loader can see it may be simpler.

### `Boot-Class-Path` vs. `Class-Path`

An agent manifest can configure:

```text
Manifest-Version: 1.0
Premain-Class: demo.agent.SplitAgent
Boot-Class-Path: bridge.jar

```

This is an **alternative configuration**, not used in the main lab below. Relative paths in `Boot-Class-Path` are resolved against the location of the agent JAR per the specification. When an agent is loaded late, non-JAR paths have special rules; this lesson uses a startup agent to reduce complexity.

## 7. Understanding `appendToBootstrapClassLoaderSearch`

`Instrumentation.appendToBootstrapClassLoaderSearch(JarFile)` adds a JAR to the **search path used when the bootstrap loader cannot find a class via default mechanisms**. If called multiple times, new JARs are searched in the order they were appended. It does **not**:

- Replace a class that has already been defined with the same name.
- Force existing class-loader searches to automatically reload previously failed references.
- Make a bootstrap helper automatically see classes that only exist in system/custom loaders.
- Verify whether the helper JAR contains trustworthy classes.
- Provide an API to remove/rollback appended JARs.
- Allow safely putting an entire fat agent JAR with all its libraries into bootstrap.

The Javadoc warns very specifically: an appended JAR that accidentally contains a private/package-access application class can cause bootstrap to define that class during parent delegation, resulting in a hard-to-diagnose `IllegalAccessError`. **Use a unique helper package** and include only resources/classes truly intended for bootstrap.

Another warning is **negative resolution caching** per the JVM specification: after a symbolic reference fails to resolve once, some references may continue failing with the same error even if a JAR is appended later. Therefore, `premain` should append the helper **before the application uses it or the JVM resolves new callsites**. Do not wait until `NoClassDefFoundError` occurs and hope that appending the JAR will fix all already-loaded class state.

Active verification pattern:

```java
// Inside an agent that has Instrumentation inst and JarFile helperJar:
inst.appendToBootstrapClassLoaderSearch(helperJar);

Class<?> bridge = Class.forName(
        "demo.bootstrap.ProbeBridge", false, null);

if (bridge.getClassLoader() != null) {
    throw new IllegalStateException(
            "Bridge was not defined by bootstrap loader");
}
```

`null` as the third argument to `Class.forName` requests the **bootstrap loader**. The `false` argument means do not intentionally initialize the class at this check step. If the class still cannot be found, `ClassNotFoundException` should be handled at startup rather than silently letting the application run into hard-to-diagnose errors.

## 8. Java 17+ Lab: Building `bridge.jar` and `agent.jar` Separately

The goal is to **demonstrate runtime class loading**, not to introduce bytecode-manipulation libraries. The lab uses an app that calls `ProbeBridge.hit()` directly from source: that call has semantics equivalent to an `invokestatic` callsite that a transformer would insert. The `ClassFileTransformer` in the agent is registered but **returns `null`**, because we do not want to depend on ASM/Byte Buddy to verify helper visibility.

### 8.1. Layout

```text
split-helper-demo/
├── agent.mf
├── bridge-src/
│   └── demo/bootstrap/ProbeBridge.java
├── agent-src/
│   └── demo/agent/
│       ├── SplitAgent.java
│       └── runtime/RichReporter.java
└── app-src/
    └── demo/app/DemoApp.java
```

Build outputs will be placed in `out/bridge.jar`, `out/agent.jar`, and `out/app`. Do not put `ProbeBridge.class` inside `agent.jar`.

### 8.2. File `bridge-src/demo/bootstrap/ProbeBridge.java`

```java
package demo.bootstrap;

import java.util.concurrent.atomic.LongAdder;

// This class only has bootstrap-visible dependencies from java.base.
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

In the lab, only one thread increments the counter three times; therefore `total()` produces a deterministic result. In a real application, `LongAdder.sum()` may not be an atomic snapshot while producers are still updating, so use it as an aggregate metric rather than a ledger.

### 8.3. File `agent-src/demo/agent/runtime/RichReporter.java`

```java
package demo.agent.runtime;

// Represents the dependency-heavy agent part; the lab needs no network or external SDK.
public final class RichReporter {
    private RichReporter() {
    }

    public static String ready() {
        return "agent: rich-side=ready";
    }
}
```

In production, this package may contain exporters, SDKs, configuration, and retries. **Never** let `ProbeBridge` import `RichReporter`: a bootstrap class cannot assume it can link a class in the system loader. The example intentionally avoids external libraries so learners only need JDK 17+.

### 8.4. File `agent-src/demo/agent/SplitAgent.java`

```java
package demo.agent;

import demo.agent.runtime.RichReporter;
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.nio.file.Path;
import java.security.ProtectionDomain;
import java.util.jar.JarFile;

public final class SplitAgent {
    // Keep the JarFile alive for the lifetime of the demo.
    private static JarFile bootstrapJar;

    public static void premain(String options, Instrumentation inst)
            throws Exception {
        if (options == null || options.isBlank()) {
            throw new IllegalArgumentException(
                    "Expected bootstrap helper JAR path");
        }

        bootstrapJar = new JarFile(Path.of(options).toFile());
        inst.appendToBootstrapClassLoaderSearch(bootstrapJar);

        // Immediately verify whether the bootstrap loader can find the helper.
        Class<?> bridge = Class.forName(
                "demo.bootstrap.ProbeBridge", false, null);
        if (bridge.getClassLoader() != null) {
            throw new IllegalStateException(
                    "Helper was not defined by bootstrap loader");
        }
        System.out.println("agent: helper-loader=bootstrap");

        // The rich side is not in the helper JAR.
        System.out.println(RichReporter.ready());

        inst.addTransformer(new ClassFileTransformer() {
            @Override
            public byte[] transform(
                    Module module,
                    ClassLoader loader,
                    String className,
                    Class<?> classBeingRedefined,
                    ProtectionDomain domain,
                    byte[] classfileBuffer) {
                // The lab only registers the hook; it does not modify bytecode.
                // In a real agent: filter classes, then insert a call to
                // demo/bootstrap/ProbeBridge.hit:()V.
                return null;
            }
        }, false);
        System.out.println("agent: transformer=registered");
    }
}
```

**Analysis:**

- `premain` runs before the application's `main` when using `-javaagent`.
- `bootstrapJar` is held by a static reference and is not closed early in the demo.
- The helper path from `agentArgs` is used to open a `JarFile` and append it to the bootstrap search.
- `Class.forName(..., false, null)` checks only the bootstrap search; it does not ask the system loader.
- `RichReporter` belongs only to `agent.jar` and is not referenced by the helper.
- The Java 17 transformer overrides `transform(Module,...)`; returning `null` leaves the bytes unchanged. The lab does not claim new probe bytecode was inserted.
- Manifest capabilities `Can-Retransform-Classes`/`Can-Redefine-Classes` are not needed because the lab does not call those two APIs.
- In production, **do not accept untrusted JAR paths** to append. Verify checksums/signatures, packages, and deployment permissions because a Java agent has deep access into the JVM.

### 8.5. File `app-src/demo/app/DemoApp.java`

```java
package demo.app;

import demo.bootstrap.ProbeBridge;

public final class DemoApp {
    public static void main(String[] args) {
        ClassLoader loader = ProbeBridge.class.getClassLoader();
        System.out.println("app: helper-loader=" +
                (loader == null ? "bootstrap" : "other"));

        ProbeBridge.hit();
        ProbeBridge.hit();
        ProbeBridge.hit();

        System.out.println("app: hits=" + ProbeBridge.total());
    }
}
```

This is an **app that already contains the callsites**. For real transformer output, the bytecode would contain a symbolic methodref to `demo/bootstrap/ProbeBridge.hit:()V` when inserting the equivalent instruction. The app only needs the bridge class file **at compile time**, while **at runtime** it must resolve the helper through the bootstrap search configured by the agent.

### 8.6. File `agent.mf`

```text
Manifest-Version: 1.0
Premain-Class: demo.agent.SplitAgent

```

Keep a trailing newline and blank line at the end of the manifest. Do not configure `Boot-Class-Path` in this lab, because `premain` calls append itself using the path from options.

### 8.7. Bash Commands

In the `split-helper-demo` directory:

```bash
mkdir -p out/bridge out/agent out/app

javac -encoding UTF-8 -d out/bridge \
    bridge-src/demo/bootstrap/ProbeBridge.java
jar --create --file out/bridge.jar -C out/bridge .

javac -encoding UTF-8 -d out/agent \
    agent-src/demo/agent/runtime/RichReporter.java \
    agent-src/demo/agent/SplitAgent.java
jar --create --file out/agent.jar \
    --manifest agent.mf -C out/agent .

javac -encoding UTF-8 -cp out/bridge.jar -d out/app \
    app-src/demo/app/DemoApp.java

java -javaagent:out/agent.jar=out/bridge.jar \
    -cp out/app demo.app.DemoApp
```

Key point: the app compile command uses `-cp out/bridge.jar`, whereas runtime only uses `-cp out/app`. `out/bridge.jar` enters the **bootstrap search** via `-javaagent:out/agent.jar=out/bridge.jar`; the part after `=` is the options string passed to `premain`, not a classpath. `agent.jar` is located by the JVM via the `-javaagent` mechanism and does not need to be placed on the app's runtime `-cp`.

### 8.8. PowerShell Commands

```powershell
New-Item -ItemType Directory -Force `
    -Path out/bridge, out/agent, out/app | Out-Null

javac -encoding UTF-8 -d out/bridge `
    bridge-src/demo/bootstrap/ProbeBridge.java
jar --create --file out/bridge.jar -C out/bridge .

javac -encoding UTF-8 -d out/agent `
    agent-src/demo/agent/runtime/RichReporter.java `
    agent-src/demo/agent/SplitAgent.java
jar --create --file out/agent.jar `
    --manifest agent.mf -C out/agent .

javac -encoding UTF-8 -cp out/bridge.jar -d out/app `
    app-src/demo/app/DemoApp.java

java -javaagent:out/agent.jar=out/bridge.jar `
    -cp out/app demo.app.DemoApp
```

Use JDK 17+ (`java`, `javac`, `jar` from the same JDK). PowerShell uses a backtick for line continuation; Bash uses a backslash. In this lesson's compile command there is only one JAR on the compile classpath, so there is no need to join multiple entries with `:` or `;`.

### 8.9. Expected Stdout

In a typical HotSpot/OpenJDK environment, when the JARs are correct and no other agent prints extra logs:

```text
agent: helper-loader=bootstrap
agent: rich-side=ready
agent: transformer=registered
app: helper-loader=bootstrap
app: hits=3
```

The order is significant: the agent adds the bootstrap search and checks the loader **before** the app starts. The app sees the **same helper defined by bootstrap**. Three consecutive `hit` calls on the same thread produce a counter of 3.

The `agent: transformer=registered` output only confirms that `addTransformer` was called; it does **not** prove the transformer produced new bytes because `transform` returns `null`. The example uses source callsites to test the loader boundary in isolation.

### 8.10. Inspecting JAR Contents and Dependencies

```bash
jar --list --file out/bridge.jar
jar --list --file out/agent.jar
jdeps -verbose:class out/bridge.jar
javap -classpath out/bridge.jar -p demo.bootstrap.ProbeBridge
```

`bridge.jar` must contain `demo/bootstrap/ProbeBridge.class` and standard JAR metadata, and **must not** contain `demo/agent/SplitAgent.class`, `net/bytebuddy/...`, `org/objectweb/asm/...`, or exporters. `agent.jar` should contain `demo/agent/SplitAgent.class`, the transformer's anonymous class, `RichReporter.class`, and the manifest, **without `ProbeBridge.class`**.

`jdeps` helps detect **static dependencies** in bytecode, but does not prove every reflection or dynamic class lookup is safe. Combine JAR inspection, runtime `getClassLoader`, and smoke tests.

## 9. Control Experiments

### A. Not Appending the Helper to Bootstrap

If you omit the `appendToBootstrapClassLoaderSearch` call while keeping `Class.forName(binaryName, false, null)`, the agent will not find the helper via bootstrap search and startup will fail early. If you also omit that check and run the app without the helper on the runtime classpath, a common error is `NoClassDefFoundError` when resolving the callsite.

Takeaway: **compile-time classpath is not runtime loader visibility**.

### B. Accidentally Packaging the Helper into Both `agent.jar` and `bridge.jar`

If a build plugin copies `ProbeBridge.class` into `agent.jar`, the JVM may encounter duplicate classes across multiple search paths. Parent delegation and definition timing determine the runtime instance; some classes may already be loaded from elsewhere before the bootstrap append. Do not rely on "it still works in the lab" to treat this as correct packaging.

Solution: produce **two artifacts with non-overlapping contents** and test with `jar --list`. A version mismatch between the helper JAR and instrumented classes can also cause `NoSuchMethodError`.

### C. Helper Imports an Exporter That Only Exists in the Agent

If `ProbeBridge.hit()` calls `RichReporter.ready()` or a non-bootstrap-visible SDK, the helper no longer satisfies the constraint. In a JVM, the error may only surface when that method is first linked or executed. Do not try to fix it by putting the entire dependency tree into bootstrap; invert the dependency and keep the exporter on the rich agent side.

### D. Custom Class Loader Only Delegates to Bootstrap

A plugin loader may see the bootstrap bridge without seeing a class placed only on the system loader. Test on a real runtime/container, because some frameworks use child-first loaders or module layers. Do not extrapolate from `Class.forName(name)` succeeding under the system loader.

### E. Appending After a Symbolic Reference Has Already Failed to Resolve

The Javadoc warns that previous resolution failures may be retained per the JVM specification. Do not use late appending as an automatic recovery mechanism after `NoClassDefFoundError`. Prefer startup `premain`, or have an attach/class-loading sequence that is designed and tested separately.

## 10. If the Helper Needs to Send Events to the Heavy Agent Part

One solution is to define an interface in the bridge JAR and place the implementation in the rich agent:

```java
// ILLUSTRATIVE CODE: bridge-src/demo/bootstrap/BridgeSink.java
package demo.bootstrap;

public interface BridgeSink {
    void record(int code, long elapsedNanos);
}
```

```java
// ILLUSTRATIVE CODE: agent runtime, not a standalone program.
package demo.agent.runtime;

import demo.bootstrap.BridgeSink;

public final class QueueSink implements BridgeSink {
    @Override
    public void record(int code, long elapsedNanos) {
        // Only a nonblocking offer into a bounded queue here.
        // HTTP export and serialization happen on a separate worker.
    }
}
```

This is a **design pattern**, without code for installing the sink, queue, shutdown, or delivery guarantees. It shows the right direction: **bootstrap defines the interface**, the agent loader defines the implementation. Do not let the bootstrap helper import `QueueSink`. If you install the implementation via a `static volatile BridgeSink sink`, you must handle the JMM properly, fall back when `sink==null`, guard against recursion, and watch classloader retention. A direct callback still runs **on the business thread**; if the implementation performs synchronous HTTP, splitting the JARs does not reduce latency.

If you only need aggregate counts, updating a `LongAdder` as in the lab is **less complex** than a callback interface. If you need individual events, a bounded queue with `offer`, a drop counter, and a separate worker/exporter may be appropriate. **An in-RAM queue is not a durable audit log**: a successful `offer` does not guarantee the backend received it, a crash can lose events, and retries can create duplicates.

### The Helper Is a Bridge, Not an Unbounded State Store

Do not store `ClassLoader`, `Class<?>`, `Thread`, request objects, or plugin objects in a static map inside the helper without cleanup. Because a bootstrap helper is long-lived, it can retain the class loader of a redeployed webapp/plugin, causing a memory leak. If per-loader configuration is needed, use tested weak references/eviction/lifecycle handling instead of an unboundedly growing static map.

## 11. Relationship with JPMS When the Target Is a Named Module

Since Java 9, the **module graph** and the **class-loader graph** are two separate conditions. A bootstrap-defined `ProbeBridge` belongs to the **unnamed module of the bootstrap loader**. In JDK 17, `java.lang.instrument` states that the JVM arranges supporting read edges from **the module of the transformed class** to the unnamed modules of the bootstrap loader and the loader containing the main agent class, to support instrumentation.

This does not mean any arbitrary named module always has access to every class in a bootstrap helper. You need to check:

- Was the calling class actually processed by the transformer?
- Can the target's module read the module containing the helper under the actual configuration?
- Are the helper type and methods `public`?
- Is deep reflection into non-public members of another package needed? If so, that is an **opens** issue, not just class-loader visibility.
- Any `redefineModule` adding reads/opens/exports (if truly needed) must target the right direction, package, and minimal scope of permissions.

The lab intentionally uses a **classpath unnamed module** for the app to isolate the loader problem. For named modules, write integration tests on the same module graph and class loaders as production.

## 12. Versioning and Lifecycle of the Bootstrap Helper

An instrumented method may contain a fixed callsite:

```text
invokestatic demo/bootstrap/ProbeBridge.hit:()V
```

If a new helper version removes `hit()` and only keeps `record(int)`, already-instrumented classes can encounter `NoSuchMethodError` when resolving the callsite at runtime. Because a bootstrap JAR is appended to the search path, it is not a **hot-swap mechanism** to replace already-defined classes. Multiple JARs with the same binary name do not trigger automatic class replacement.

Design practices:

1. Keep the bridge ABI stable for as long as instrumented classes may exist.
2. Prefer adding new backward-compatible APIs rather than changing descriptors already in use.
3. If breaking compatibility is necessary, version the package/helper and control the migration.
4. Do not package two helper versions with the same binary name and expect the JVM to pick the new one.
5. If a class was instrumented by agent version A, test it against the corresponding bridge version when agent B is deployed.
6. Do not assume `removeTransformer` or deleting the JAR on disk will restore already-instrumented classes.
7. Design a way to disable probes and restart the JVM when you need to clean up the loader search or update bootstrap definitions.

### Be Careful with Static Initializers

A bootstrap helper should have very small initialization, such as creating a `LongAdder`, without loading SDKs, calling exporters, reading large configurations, or spawning workers. An `ExceptionInInitializerError` from the helper while application classes are running can cause cascading failures; subsequent references to a class with an initialization failure may report `NoClassDefFoundError`.

## 13. Troubleshooting Table

| Symptom | Possible Cause | What to Check |
| --- | --- | --- |
| `ClassNotFoundException` on `Class.forName(..., null)` | Bootstrap cannot see the bridge JAR | Correct `agentArgs`, JAR entries, append before lookup |
| `NoClassDefFoundError` at callsite | Helper missing at runtime or symbolic reference resolution failed | Target's loader, package name, append timing |
| `NoClassDefFoundError` for agent's exporter | Bridge links back to a dependency only in the system loader | `jdeps bridge.jar`, remove heavy imports/fields/calls |
| `IllegalAccessError` | Incompatible package/module/loader access | Print `Class.getModule` and `getClassLoader` |
| `NoSuchMethodError` | Callsite method descriptor differs from current bridge version | `javap -p`, check ABI |
| `ClassCastException` between same-named types | Two loaders defined different classes | Compare `Class<?>` identity and defining loader |
| `ExceptionInInitializerError` | Bridge `<clinit>` depends on config/I/O/other error | Keep initialization minimal |
| `StackOverflowError` when agent is enabled | Instrumenting helper/exporter, reentrant recursion | Exclude agent/bridge packages, add guard |
| Inconsistent metric counts | Multiple helper identities or multiple callsites | Check bootstrap loader and probe count |
| `OutOfMemoryError` after redeploy | Bridge static field retains old plugin objects/class loader | Heap dump and cleanup/weak references |
| App runs locally but fails in server | Custom loader/module differs from lab classpath | Reproduce exact loader tree, JPMS, parent delegation |
| Agent startup abort | `premain` throws exception due to bad path/JAR | Check manifest, path, and file permissions |

**Distinguish four steps:** (1) the loader **finds the class**, (2) the JVM **permits access/linking** per module/visibility rules, (3) static initialization **succeeds**, (4) the helper code **behaves correctly** and does not slow down the application. One step succeeding does not prove the remaining steps succeed.

## 14. Implementation Checklist

1. Identify the actual class loader/module of the instrumented target.
2. Choose an appropriate helper placement; do not default to bootstrap in every project.
3. Have a **separate bridge JAR** containing only the necessary classes/resources.
4. Use a dedicated package, avoiding collisions with third-party/JDK/application classes.
5. Use `jdeps`, `jar --list`, and code review to verify the dependency graph.
6. Keep the helper API public, small, with stable descriptors, and easy to version.
7. Eliminate all static references from the helper to the agent runtime or external libraries.
8. Append the bootstrap search **early**, before the target references the helper.
9. Verify `Class.forName(name,false,null)` and loader identity when choosing bootstrap.
10. Check JPMS reads/opens if the target belongs to a named module.
11. Filter the transformer so it does not process the bridge/agent/exporter.
12. Return valid new bytes when actually transforming, and `return null` if unchanged.
13. Do not block on network/disk from the helper on the hot path.
14. Control bounded queues/drops if detailed events are needed.
15. Do not hold class loaders/plugin objects in unbounded helper static state.
16. Have a startup-failure policy if the helper JAR is wrong/missing, rather than silently running with missing functionality.
17. Test both classpath and realistic custom-loader/module-path scenarios.
18. Test helper ABI compatibility with older instrumented bytecode.
19. Measure latency, CPU, allocation, GC, and probe counts with/without the agent.
20. Have a plan for shutdown, disabling probes, and restarting when updating the bootstrap JAR.

## 15. Self-Check Exercises

**Q1.** Can an agent class import `RichExporter`, so any instrumented application class can import it too?  
**A:** No. The target class loader may not see the system/agent loader or its dependency graph.

**Q2.** Why should `bridge.jar` contain only `ProbeBridge.class` and minimal bootstrap dependencies?  
**A:** To avoid bootstrap accidentally defining libraries not meant for it, reducing linkage errors and package/version conflicts.

**Q3.** What does `ProbeBridge.class.getClassLoader()==null` mean?  
**A:** The class was defined by the bootstrap loader. It does not mean the class belongs to the `java.base` module.

**Q4.** When compiling an app with `-cp bridge.jar` and then running with only `-cp out/app`, when does it still run?  
**A:** When the agent properly appends the bridge JAR to the bootstrap search before the app resolves the helper, as in the lab.

**Q5.** Can a bootstrap helper directly call a class defined only by the system loader?  
**A:** This cannot be assumed. The JDK's bootstrap supporting classes rule requires them to link only to bootstrap-defined classes.

**Q6.** If appending is omitted, what is the error at `Class.forName(..., false, null)`?  
**A:** When the bootstrap search does not find the helper, `ClassNotFoundException`; callsites in the app may encounter `NoClassDefFoundError`.

**Q7.** Do two classes with the same name in two defining loaders share a static counter?  
**A:** Not necessarily: they can be two independent runtime classes with separate static state.

**Q8.** Does `appendToSystemClassLoaderSearch` make the helper visible to every plugin loader?  
**A:** No. A plugin loader might not delegate to the system loader.

**Q9.** Are using `Boot-Class-Path` in the manifest and `appendToBootstrapClassLoaderSearch` the same mechanism?  
**A:** No. They are two mechanisms for providing a bootstrap search path, with different packaging/timing characteristics.

**Q10.** Why can a `hit:()V` callsite fail after upgrading the helper?  
**A:** If the method was removed or its descriptor changed, the old symbolic reference can cause `NoSuchMethodError`.

**Q11.** Why does the lab's app call the helper directly instead of having the transformer insert instructions?  
**A:** To verify JAR splitting, the bootstrap loader, and runtime linkage without needing a bytecode generation library. The transformer in the lab returns `null` and inserts no code.

**Q12.** Should a webapp's `ClassLoader` be kept in a static bridge map for convenient lookup?  
**A:** Not without lifecycle/eviction; it can keep the old loader alive indefinitely after a redeploy.

**Q13.** With named modules, does simply bootstrap-loading the helper guarantee all access/opens are valid?  
**A:** No. The module graph and visibility must be checked separately; the JDK helps with read edges for the module of the transformed class, not for any arbitrary module.

**Q14.** Does calling `removeTransformer` remove helper calls already inserted into classes?  
**A:** No. It does not automatically roll back already-defined class bytes.

**Q15.** Why should a bootstrap helper not use `java.util.logging.Logger` by default?  
**A:** There is no guarantee all platform classes are defined by bootstrap; keep the helper depending only on bootstrap-visible classes, preferring `java.base`.

## 16. Official References

- [JDK 17 — `Instrumentation.appendToBootstrapClassLoaderSearch`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): bootstrap search, JAR contents warning, package collision, negative resolution, and system loader search.
- [JDK 17 — `java.lang.instrument` package](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): `premain`, loading agent JAR, bootstrap supporting classes, `Boot-Class-Path`, JPMS read edges.
- [JDK 17 — `ClassFileTransformer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): lifecycle callback and requirements for returning bytes/`null`.
- [JDK 17 — `ClassLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): bootstrap/parent delegation, class visibility.
- [JDK 17 — `LongAdder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html): counter and snapshot limitations under concurrency.
- [JVMS 17 — Loading, Linking, and Initializing](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): class identity, loader constraints, and symbolic references.

**Remember:** The helper is a **minimal API** for instrumented bytecode; the rich agent carries the bytecode SDK, exporters, and complex dependencies. When using bootstrap search, append only a **small helper JAR**, before the target needs to resolve it, and verify the actual loader. Separating dependencies in the right direction helps avoid linkage errors, reduces overhead, and preserves long-term deployability and diagnosability.