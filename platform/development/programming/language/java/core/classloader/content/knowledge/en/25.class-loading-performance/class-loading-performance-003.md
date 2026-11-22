# Lazy Loading and the Impact of Preloading on Java ClassLoader Performance

## 1. Overview: Pay the Cost at Startup or on First Use?

A Java application typically does not need to execute all of its functionality immediately at startup. Some classes are only used when a specific request arrives, a user enables a feature, or the system discovers a plugin. Therefore, the runtime can **defer loading, linking, or initializing** certain classes until they are actually needed. Architecturally, this approach is commonly referred to as **lazy loading**.

Conversely, **preloading** is a strategy that **proactively performs part of the work early**—for classes, resources, or framework components—to reduce latency when a feature is accessed for the first time.

~~~text
LAZY                                      EAGER / PRELOADING
Process start                             Process start
   |                                          |
   | load/initialize required classes         | proactively load/initialize more classes
   v                                          | build caches, prepare framework...
Server ready                                  v
   |                                      Server ready
   | first request                            |
   | load/link/init more classes?             | first request
   v                                          | less remaining work to do?
Response                                      v
                                          Response
~~~

Common trade-offs:

- **Lazy loading:** can shorten the time until the application is ready and reduce the number of classes that actually need to be processed if a feature is rarely used; however, the first request to that feature may incur extra cost.
- **Preloading:** can shift cost into startup or a warm-up phase, reducing first-use latency; in return, startup takes longer, memory/resident metadata may increase, and it can cause additional I/O/CPU usage or static initialization side effects.

**There is no universal rule that “preloading is always faster.”** Effectiveness depends on the class set, loading mechanism, JIT, class data sharing, storage, concurrency, hot paths, deployment policies, and the metric being optimized (startup, p99 latency, RAM, throughput, or update time).

The most important takeaway of this article: **loading, linking, initialization, and “warming” are distinct operations.** A command that proactively “loads a class” does not automatically execute static initializers, instantiate Spring beans, or force the JIT to compile all methods.

## 2. Three Phases Often Lumped Together as “Class Loading”

To choose the right level of preloading, distinguish the three JVM milestones (JLS/JVMS): **loading** finds the bytes and creates the runtime `Class<?>`; **linking** consists of verification, preparation, and resolution (resolution can occur lazily); **initialization** runs static field expressions and `<clinit>` when required by active use.

| Preload target | May already be completed | May still occur on the first request |
| --- | --- | --- |
| `loadClass(name)` | Class lookup/definition as needed, partial linking | `<clinit>`, lazy resolution, instantiation, I/O/JIT |
| `Class.forName(name, false, loader)` | Loads/links class per API without requesting init | Static initializer, provider/discovery, and business setup |
| `Class.forName(name, true, loader)` | Adds initialization request | Constructors, DI graph, other resource access, first-use/JIT |

### 2.1. “Lazy” Is Not an Absolute Timing Guarantee for Loading

The JVM and frameworks may proactively load or link certain classes ahead of the code path that the application assumes is the first use. **Passing `false` to the API only guarantees that the target class is not proactively initialized**; it does not guarantee the class was never loaded earlier, nor does it force all symbolic references to be resolved. Comparing lazy vs. preload approaches must be based on class-load/init evidence and real workloads, not assumptions about timing.

## 3. Java 17+ APIs and What Actually Happens

| Usage | Loading/linking | Initialization of the target class |
| --- | --- | --- |
| `loader.loadClass("demo.Feature")` | Asks the loader to find/load the class; parent delegation applies | **Does not automatically request** initialization |
| `Class.forName("demo.Feature", false, loader)` | Finds/loads/links per API and VM rules | **Does not request** initialization |
| `Class.forName("demo.Feature", true, loader)` | Finds/loads/links and requests initialization | **Yes**, if needed |
| `Class.forName("demo.Feature")` | Uses the caller's defining loader per the corresponding API; requests initialization | **Yes**, if needed |
| `Feature.class` | Obtains the Class literal, which may trigger necessary class-loading work | **Does not by itself cause** Feature to be initialized |
| `new Feature()` | Requires the class to be prepared | **Yes**, before creating the instance per rules |
| `Feature.runStatic()` | Executes a static method invocation | **Yes**, if not yet initialized |
| `Feature.nonConstantStatic` | Accesses a static field that is not a constant variable | **Yes**, if not yet initialized |
| `Feature.COMPILE_TIME_CONSTANT` | A constant variable is typically inlined into the caller | **May not** cause the declaring class to be initialized |

**Note:** `ClassLoader.loadClass(String, boolean resolve)` is a protected overload; `resolve=true` means requesting **linking via `resolveClass`**, **not initialization**. Do not equate “resolve class” with “run static initializer.”

`Class.forName(name, false, loader)` is suitable when you need a `Class<?>` to inspect metadata, hold a handle, or verify that a class can be loaded, **but it should not be called a full application warm-up**.

## 4. Runnable Example: Three Modes—Lazy, Load, and Preload

The experiment below fixes the order of output messages to illustrate **when static initialization occurs**. It does not attempt to benchmark timing with arbitrary millisecond numbers, since actual timings vary by machine and JDK.

### 4.1. LoadingDemo.java

~~~java
public class LoadingDemo {
    static final class Feature {
        static {
            System.out.println("Feature initialized");
        }

        static void serve() {
            System.out.println("Feature.serve");
        }
    }

    public static void main(String[] args) throws Exception {
        String mode = args.length == 0 ? "lazy" : args[0];
        ClassLoader loader = LoadingDemo.class.getClassLoader();
        String name = "LoadingDemo$Feature";

        switch (mode) {
            case "lazy" -> {
                // Do not proactively load or initialize Feature.
            }
            case "load" -> {
                loader.loadClass(name);
                System.out.println("Class loaded without initialization");
            }
            case "lookup" -> {
                Class.forName(name, false, loader);
                System.out.println("Class resolved without initialization");
            }
            case "preload" -> {
                Class.forName(name, true, loader);
                System.out.println("Preload completed");
            }
            default -> throw new IllegalArgumentException(mode);
        }

        System.out.println("Application ready");
        System.out.println("First request");
        Feature.serve();
        System.out.println("Request completed");
    }
}
~~~

Using **Java 17+**, in a fresh directory containing `LoadingDemo.java`:

~~~bash
javac --release 17 -d out LoadingDemo.java
java -cp out LoadingDemo lazy
java -cp out LoadingDemo load
java -cp out LoadingDemo lookup
java -cp out LoadingDemo preload
~~~

**Run each command in a new JVM process**, because initialization of the same runtime `Class` occurs at most once in its corresponding lifecycle. If invoked a second time in the same JVM, the difference may disappear because the class is already initialized.

### 4.2. Exact Output: lazy

~~~text
Application ready
First request
Feature initialized
Feature.serve
Request completed
~~~

At the point `Application ready` is printed, the code has not attempted to proactively initialize `Feature`. After the `First request` line, the static method call `Feature.serve()` requires the class to be initialized, so the static initializer message appears before the body of `serve` executes.

### 4.3. Exact Output: loadClass

~~~text
Class loaded without initialization
Application ready
First request
Feature initialized
Feature.serve
Request completed
~~~

`loadClass` returned the `Class` before the application was ready, **yet the static initializer still only ran when the method was used**. In this case, part of the loading work may have been shifted to startup, but the `<clinit>` cost was not.

### 4.4. Exact Output: Class.forName with initialize=false

~~~text
Class resolved without initialization
Application ready
First request
Feature initialized
Feature.serve
Request completed
~~~

The program prints `Class resolved without initialization` as **a descriptive label for the demo's lookup operation**; do not infer that every symbol in the bytecode was eagerly resolved. What is certain is that the API did not request initialization, as shown by the stdout order.

### 4.5. Exact Output: preload with initialization=true

~~~text
Feature initialized
Preload completed
Application ready
First request
Feature.serve
Request completed
~~~

This time, `Class.forName(name, true, loader)` forced `Feature` to be initialized before `Application ready`. The first request no longer prints the initialization message because the static initializer runs only once within the loader's namespace.

**What the example proves:** preloading can **shift the timing of initialization**. It **does not prove** that p99 latency in a real system will necessarily drop, that startup will increase by a specific number, or that all framework components have been warmed.

## 5. Defining “Preloading” Precisely by Level

In architecture discussions, the word “preloading” is sometimes used for very different things:

| Level | Action performed | Work that may still hit the first request |
| --- | --- | --- |
| **Name lookup / load** | `loader.loadClass(name)` | Initialization, reflection caches, method first-use |
| **Load without init** | `Class.forName(name, false, loader)` | `<clinit>` and dependent logic |
| **Initialize** | `Class.forName(name, true, loader)` | Constructors, dependency initialization via other paths, request-specific logic |
| **Instantiate** | `Constructor.newInstance` or `new` to create an object | Lazy fields, caches, network connections, business paths |
| **Framework warm-up** | Building DI graph, route mappings, serializers, proxies | Unexecuted paths, other class resolutions, JIT compilation |
| **Application exercise** | Running a representative safe request | Different data, locks/cache misses, workload-dependent logic |
| **JIT warm-up** | Running hot methods enough for JIT profile-guided optimization | Deoptimization, profile shifts, rare paths |
| **CDS/AppCDS** | Sharing archived class metadata on a compatible startup | Static initialization and request-specific caches usually remain |

Do not write in operational documentation that “preloading is complete” when the system merely called `loadClass` and ignored startup errors from static initializers or never exercised the code paths customers are about to hit.

### 5.1. Preloading a Class Does Not Mean Beans Are Created

In Spring or other DI frameworks, having a class loaded by the JVM does not mean **the bean object has been created, the dependency graph is complete, or lifecycle hooks have run**. Class loading and class initialization are not synonymous with application-level initialization of framework components.

If the goal is to avoid first-request slowness for a DI container, you need to measure and warm **the right component paths**, not merely call `Class.forName` on bean classes.

### 5.2. Preloading Does Not Mean JIT Has Compiled the Code

`Class.forName` does not invoke all methods of a class and does not ensure the JVM JIT compiler has optimized them. JIT optimization primarily reacts to actual execution profiles and hotness. A metadata-only “preload” does not replace a warm-up workload.

## 6. Impact on Startup Latency

In CLI applications, serverless functions, short-lived jobs, or desktop launches, **time to first useful action** can be the most important metric.

Startup costs related to class loading may include:

- Reading JAR entries or class files from storage.
- Searching for classes on the classpath/module path via parent delegation, `URLClassLoader`, or custom lookups.
- Verification, preparation, and partial resolution.
- Static initialization of classes used early.
- Framework classpath scanning, reflection index generation, or proxy generation.
- Reading configuration, building the dependency graph, and initializing caches.
- Filesystem/JAR processing I/O and OS page-cache warm-up.

Preloading all plugin classes at startup can delay service readiness, especially if only one plugin is invoked by a small fraction of requests. Conversely, environments that receive health/readiness traffic immediately after start may accept controlled warm-up to avoid first-request latency spikes.

**Measure startup using a concrete definition:**

- **Process-start to bound port?**
- **Process-start to readiness true?**
- **Readiness true to first successful request?**
- **First request p50/p95/p99 latency?**
- **Time for a batch job to finish?**

Shifting cost from before readiness to after readiness can make a “startup metric” look better while worsening the **first user experience**. Shifting it the other way can slow down readiness while making requests immediately after readiness more stable. There is no right choice without defining your SLA/SLO.

## 7. Impact on First-Request Latency and Tail Latency

Lazy loading is especially visible when an endpoint or feature **has never been called** in the current process:

~~~text
Request A arrives when class is not yet initialized:
  routing
  -> discovery / class loading / linking (if needed)
  -> static initialization
  -> create dependency/proxy/cache (if designed to)
  -> execute business logic
  -> response

Request B arrives when class is already initialized:
  routing
  -> execute business logic (may still hit other warm-up)
  -> response
~~~

A single-use cold path can create a spike in **p99** even when most requests are fast. However:

- Not every first request has to load classes; the framework may have loaded them during scanning.
- Loading and initialization may be triggered by another thread before Request A.
- The first request may be slow due to DNS/TLS, connection pools, disk cache, JIT, or external services rather than class loading.
- Preloading can push cost to startup, but it can also cause multiple services preloading simultaneously to contend for CPU and I/O, temporarily reducing throughput.
- Metrics that only track average latency can hide clear spikes on cold requests.

To analyze this, record **timestamps and event details** around class initialization and the request path, then correlate them with traces/JFR instead of measuring only with `System.currentTimeMillis` and guessing the cause.

## 8. Impact on Memory: Loaded Classes Are Not Free

When a class is defined, the JVM typically retains metadata in **Metaspace**, constant pool data, method metadata, and other structures. Reflection, JIT, and initialization operations can also allocate additional objects, code caches, or application-level caches.

Preloading many classes can:

1. Increase the number of **loaded classes** in the process.
2. Increase Metaspace usage and some native memory.
3. Create static caches, singletons, or threads/resources during initialization.
4. Eliminate the chance of **never using** classes belonging to rare features.
5. Increase startup I/O and heap activity, potentially triggering early GC.

However, do not assume a **loaded** class permanently occupies all of its memory for the entire lifetime of the process. **Class unloading** can occur when the defining class loader and its associated classes are no longer reachable under JVM rules; references from static caches, threads, context class loaders, or `ServiceLoader`/proxy caches can keep plugin loaders alive longer than expected.

When using separate class loaders for multiple plugins, preloading all implementation classes across multiple loaders can create **multiple copies of metadata and static state** instead of sharing a single parent loader. When optimizing startup and memory, consider both **type identity and loader lifecycle**.

## 9. Parent Delegation, ClassLoader Locks, and Parallel Preloading

A custom `ClassLoader` typically follows this model:

~~~text
loadClass(binaryName)
    -> findLoadedClass
    -> parent delegation
    -> findClass / defineClass
    -> resolveClass (when requested)
~~~

Repeatedly reading class bytes from disk or the network can incur I/O cost. A loader that properly caches and reuses `Class<?>` avoids duplicate definitions.

When multiple threads attempt to load a class concurrently, the class loader must synchronize appropriately; `ClassLoader.loadClass` uses a class loading lock according to the loader's policy. With **parallel-capable class loaders**, `getClassLoadingLock(name)` can provide per-class-name locks to increase concurrency; custom loaders must register as parallel-capable properly if the design supports it.

### 9.1. Parallel Preloading Is Not Always Faster

- Multiple workers reading from the same storage/JAR can cause I/O contention.
- Verification and initialization can contend for CPU at startup.
- The JVM holds a **class initialization lock**, so multiple threads actively using the same class may block waiting for the thread executing `<clinit>`.
- A custom loader with loader-wide synchronization can serialize requests even when preloading is multi-threaded.
- Circular initialization or `<clinit>` side effects can cause deadlocks or hangs, especially if a static initializer spawns threads and waits for them to complete.

**Prefer a warm-up plan with bounded concurrency, grouped by hot paths, and backed by real measurements**, rather than firing off hundreds of `Class.forName(name, true, loader)` calls simultaneously.

## 10. Static Initialization with Side Effects

Placing heavy network, database, or file I/O inside `static { }` blocks or static field initializers makes both lazy loading and preloading unpredictable.

Illustrative example:

~~~java
final class RemoteConfig {
    static final String VALUE = fetchConfiguration();

    static String fetchConfiguration() {
        // Assume this performs I/O and may throw errors or time out.
        return "configured";
    }
}
~~~

**This is an illustrative snippet** and does not actually make network calls. When the class is initialized, `fetchConfiguration()` runs. Preloading via `Class.forName(..., true, ...)` will execute that logic **before readiness** if the target is not yet initialized.

Consequences:

- **Initialization errors** can block startup instead of only failing a rare feature on first use.
- **Timeouts/external dependencies** can make readiness depend on a service not needed by all features.
- **CPU/memory spikes** can occur when multiple static caches are built at once.
- **Unclear order dependencies:** initializers run early before environment/config is ready.

Therefore, consider keeping `<clinit>` simple and moving heavy I/O to lifecycle-managed initialization with proper timeouts, reporting, and retry capability. Preload static initializers to “warm” an application only when you understand their exact side effects.

## 11. Class Initialization Failures and Retries

If a static initializer fails with an ordinary exception, the first initialization attempt may throw `ExceptionInInitializerError`; subsequent uses of that class may throw `NoClassDefFoundError` indicating the class could not be initialized. This **cannot be resolved by calling `Class.forName` repeatedly on the same class loader**.

Example:

~~~java
public final class Broken {
    static {
        if (System.getProperty("config.ready") == null) {
            throw new IllegalStateException("missing config");
        }
    }

    public static void run() { }
}
~~~

This is an **illustrative snippet**; the Java compiler may require static initializers to complete normally under flow rules, and a runtime conditional `if` branch like the one above allows the class to compile. If code proactively preloads `Broken` before the system is configured, it can **push the failure into startup** and leave the class in an erroneous state in its defining loader.

**Loading early to fail fast** can be a desirable feature if the application strictly requires that class to serve any request. For optional plugins, however, failing the entire process fast can hurt availability: isolate the error and mark only the plugin as unavailable when appropriate.

To load a new version of a class after initialization fails, a plugin architecture may need a **new loader** with a fresh class definition and proper lifecycle management; you cannot arbitrarily “reset” the initialization state of the same `Class`.

## 12. A Second Example: Preloading an API Without Triggering Static Side Effects

In a plugin environment, sometimes you only need to confirm that a binary class name exists **without running its static initializer**.

~~~java
public final class PluginCatalog {
    public static Class<?> find(String name, ClassLoader loader)
            throws ClassNotFoundException {
        return Class.forName(name, false, loader);
    }
}
~~~

This is a **compilable class without a `main` method**. It provides a `Class` lookup without requesting initialization. However:

- Simply finding the `Class` does not prove the plugin has compatible dependencies at every call site.
- The classfile may be linked/resolved under different JVM semantics.
- A static initializer may still fail when the plugin is actually used.
- This cannot be treated as a complete probe to ensure a `ServiceLoader` provider or DI bean is ready.

If you want to inspect the API before readiness, you can use `Class.getDeclaredMethods()` or `isAssignableFrom` as needed, but reflection operations can also trigger loading of referenced types and raise their own errors. Do not assume introspecting all classes is zero-cost or free of module/access interactions.

## 13. ServiceLoader: Provider Discovery Is Also Typically Lazy

`ServiceLoader.load(Service.class, loader)` returns a `ServiceLoader`; finding metadata, loading provider classes, or instantiating them typically happens **lazily during iteration**.

Example:

~~~java
ServiceLoader<MyService> services =
        ServiceLoader.load(MyService.class, pluginLoader);

for (MyService provider : services) {
    provider.run();
}
~~~

This is an **illustrative snippet**, assuming `MyService` and `pluginLoader` already exist. Merely creating a `ServiceLoader` at startup without iterating over its providers does not guarantee that provider classes have been loaded or initialized.

To genuinely warm providers, you must **iterate and instantiate** the intended providers (and possibly invoke appropriate safe paths). However:

- A plugin constructor may perform I/O and register resources.
- If plugin bytecode is incompatible with the runtime service interface, iteration may throw `ServiceConfigurationError`.
- If providers are optional, preloading all of them can expose startup to failures from unused plugins.
- `reload()` refreshes the `ServiceLoader` cache; **it does not replace a `Class` already loaded/initialized by its defining loader**.

Place the service API in a common parent loader if the host and provider need to share the same runtime type, avoiding situations where preloading exposes “provider not a subtype” errors during startup.

## 14. Reflection, Dynamic Proxies, and Framework Startup

Reflection-based frameworks can incur many “first-time” costs:

- Scanning annotations on classes.
- Retrieving `Method`, `Field`, and constructors, and checking access.
- Generating dynamic proxy classes.
- Building the object graph and injection metadata.
- Analyzing route/controller mappings.
- Configuring serializers/deserializers.
- Scanning the classpath/JAR entries.

**Proactively loading classes with `Class.forName(..., false, ...)` does not automatically perform all of this work.**

If a framework provides eager initialization, lazy bean creation, or startup hooks, understand **what unit is being preloaded**. For example, a framework might load a class to read annotations while deferring bean creation; the first request still has to run the constructor and proxy generation.

In systems with multiple `ClassLoader`s or `ModuleLayer`s, generated proxy classes must see **the exact runtime interface `Class`** from the designated loader. Indiscriminately increasing preloading will not fix parent delegation/API duplication or module `opens`/`exports` issues.

## 15. JIT Warm-Up Is Different from Class Preloading

**Class loading and JIT compilation are two separate phenomena.**

A JVM may run a method in the interpreter first, collect execution profiles, and then JIT-compile it when the method becomes hot. Preloading a `Class` without invoking its methods does not generate enough profile data to make any method hot.

Diagram:

~~~text
Class bytes --> loading/linking --> initialization
                       |
                       +--> first method invocation
                                 |
                                 +--> interpreter / tiered compilation
                                 +--> hotness / profile / optimization
                                 +--> potential deoptimization and recompilation
~~~

If your goal is to reduce first-request latency caused by JIT, design a representative **warm-up workload** with production-like data while controlling side effects:

- Hit internal test endpoints while the application is in a warming state before receiving traffic.
- Do not create real transactions or send real emails just to “warm” the system.
- Do not assume the JIT state and profiles from a test request will cover all production distributions.
- Re-measure performance after warm-up; do not rely on a fixed loop count applied across all JDKs and CPUs.
- For serverless or short-lived CLIs, lengthy prewarming may cost more than it saves.

CDS and AppCDS can help reduce part of the loading/memory cost via JVM-supported archives. **They are not a command to “run all static initializers”** and do not eliminate application-level JIT/runtime warm-up.

## 16. Measuring: Distinguishing Cold Start, Warm Start, and Cold Path

A reliable benchmark plan should define:

| Metric | Question | Suggested measurement |
| --- | --- | --- |
| Time to process ready | How soon can the JVM accept valid traffic? | Measure from process start to readiness event |
| Cold first request | How slow is the first request after launch? | Measure end-to-end client-side latency |
| Warm request latency | What is latency after the feature has been used? | Multiple iterations, latency distribution |
| p95/p99 | Are there long-tail spikes during class init? | Request traces + histograms |
| Classes loaded | How many classes are loaded, and from where? | JVM Unified Logging / JFR |
| Metaspace | How much extra metadata does preloading add? | JFR, `MemoryPoolMXBean`, native memory tracking |
| Heap allocations/GC | Do init caches cause allocation pressure? | JFR, GC logging, heap metrics |
| CPU/I/O during startup | How much CPU and disk does preloading consume? | Process/host-level metrics |
| Throughput under load | Does preloading improve overall processing? | Load test after readiness |

### 16.1. Benchmark Each Option in a Fresh JVM Process

If you run lazy and then preload sequentially in **the same JVM with the same defining loader**, the second run may have no class initialization cost left: results become skewed because the class is already initialized. To measure cold effects, spawn a **fresh process** for each trial, or use a genuinely fresh loader namespace when appropriate for the architecture.

Best practices:

1. Use a fixed build artifact, the same JDK/version, and the same hardware/CPU quota and configuration.
2. Run multiple independent trials for **lazy**, **preload-load-only**, and **preload-initialize**.
3. Separate cold OS page-cache and warm OS page-cache runs if it affects results.
4. Record startup/readiness, first-use latency, and p99—not just the average.
5. Measure memory (Metaspace, heap, code cache) and GC alongside the number of loaded classes.
6. Report p50/p95/p99, confidence intervals, or distributions; do not publish a single number as representative of all machines.
7. Run A/B tests under identical traffic/load; note whether preloading consumes CPU cores that compete with workloads.

For microbenchmarks of method execution, prefer JMH and avoid using a simple `nanoTime` loop to draw broad conclusions about JIT optimization. For first-request latency, **end-to-end process-level measurements** are usually more useful.

### 16.2. Observing Class Loading with JVM Unified Logging

On OpenJDK/HotSpot Java 17+:

~~~bash
java -Xlog:class+load=info -cp out LoadingDemo lazy
~~~

This command runs the example from Section 4 if already compiled. It will print **a large amount of JVM log output**, varying by version and classpath; there is no fixed transcript. Compare `class+load` events with the `Feature initialized` log to see that **loaded** does not mean **initialized**.

Unified logging itself has overhead, so only enable it during diagnostics or benchmarks where configuration is consistent across variants.

### 16.3. Using Java Flight Recorder

You can start JFR at launch:

~~~bash
java -XX:StartFlightRecording=filename=loading.jfr,settings=profile \
     -cp out LoadingDemo preload
~~~

This is an illustrative **Unix shell** command. On PowerShell/CMD, write it on a single line:

~~~powershell
java -XX:StartFlightRecording=filename=loading.jfr,settings=profile -cp out LoadingDemo preload
~~~

The captured events depend on the JFR configuration and JVM; if you need **detailed class loading/initialization events**, enable the events available in your runtime. Do not assume default profile settings include every class event or automatically measure all static initialization costs at the method level.

JFR helps observe timelines, allocations, and JVM activity events, **but it does not replace client-side request latency measurements**.

## 17. Ordered, Prioritized Preloading and the “Readiness Budget”

Instead of preloading **every class**, you can categorize them:

**Group A — required before ready:** shared service APIs, modules/beans used by every request, mandatory config where failures should fail fast.

**Group B — critical hot paths:** authentication/authorization, routing/serialization for frequent endpoints. These can be warmed before readiness or during a short canary/warm-up phase after startup.

**Group C — optional/rare paths:** rarely used exporters, report builders, admin-only endpoints, optional plugins. Often suited for lazy initialization if first-use latency still meets SLOs.

**Group D — dynamic/reloadable plugins:** load on demand with managed loader lifecycles, bounded caches, and isolation. Do not automatically eager-init plugins from unapproved sources.

Sample plan:

~~~text
Process start
  |
  +-- initialize mandatory core (fail-fast)
  |
  +-- build routing table / dependency metadata
  |
  +-- optional: warm critical endpoints safely
  |
  +-- readiness ON
  |
  +-- background/low-priority warm optional warmable paths
  |      (only with orchestration, quotas, cancellation)
  |
  +-- normal user traffic
~~~

This is a **design diagram**, not a built-in feature of `ClassLoader`. If production runs multiple replicas, the orchestrator needs to know when an instance is ready to receive traffic; without clear warm-up hooks and budgets, “background preloading” can compete with requests for CPU and worsen tail latency.

## 18. Preloading Is Not Automatically Safe

When proactively running `Class.forName(name, true, loader)` on class names read from a manifest:

- Some classes have static initializers that send requests or read credentials.
- Some plugins are only permitted to run when a specific tenant or feature flag is enabled.
- An initializer may spawn threads, register shutdown hooks, or hold loader references.
- A plugin may be untrusted code even if bytecode verified.
- Eager initialization can surface optional errors before readiness.
- Eager scanning over network storage can cause timeout/retry storms.

Therefore, **class names must belong to a trusted allowlist**, source artifacts must be approved, and preload policies should be based on classes **permitted to initialize**; do not take an arbitrary list of paths from user input and trigger static side effects.

**Security note:** the bytecode verifier and a custom `ClassLoader` are not an I/O permission sandbox for plugin code. When untrusted code must be restricted, use process/container/VM isolation and appropriate OS permissions.

## 19. Common Mistakes When Evaluating Lazy Loading

### Mistake 1: Equating `loadClass` with `initialize`

`loadClass` does not automatically request static initialization. To shift `<clinit>` work earlier, you must choose an API or usage pattern that requests initialization, such as `Class.forName(..., true, loader)`—while accounting for side effects.

### Mistake 2: “`Class.forName(false)` warmed the entire feature”

No. It does not request static initialization, does not create objects through the DI lifecycle, and does not execute hot methods to warm the JIT.

### Mistake 3: Preloading as much as possible is better

False. Many rare classes can increase startup time, metadata/memory usage, and I/O without improving SLOs for actual traffic.

### Mistake 4: Evaluating in an already-warmed JVM

An already-initialized class will not run `<clinit>` again just because `Class.forName` is called. Cold tests require a genuinely fresh process, layer, or loader for the problem at hand, not a warmed-up runtime.

### Mistake 5: Comparing only startup time

A preloading model may slow startup while reducing first-request latency; a lazy model does the opposite. Measure both readiness and first-use/p99.

### Mistake 6: Assuming all first-time delays come from class loading

Class initialization, first connections, JIT, disk cache, TLS, DNS, data caches, and reflection/proxy generation can also cause delays. Use traces and JFR to distinguish them.

### Mistake 7: Forgetting static initializer side effects

Preloading can trigger I/O, throw exceptions, or wait on locks during deployment. Intentional initialization requires proper observability and error handling.

### Mistake 8: Ignoring class loader identity

Two loaders that each define the same binary name create two distinct runtime `Class` objects. Warming a class in loader A does not guarantee plugin loader B is warmed; preloading with the wrong loader can add overhead.

### Mistake 9: Ignoring metadata memory overhead

Loaded classes carry metadata and may retain static state. Preloading every plugin increases pressure on Metaspace/caches, and holding references can prevent unloading.

### Mistake 10: Enabling unbounded multi-threaded preloading

This can cause CPU/I/O contention, initializer lock contention, and increased latency. Bound concurrency, measure rates, and separate critical from non-critical work.

### Mistake 11: Thinking CDS/AppCDS replaces workload warm-up

CDS helps archive metadata/class data at the VM level; it does not ensure static initializers have run or that methods are JIT-optimized for traffic.

### Mistake 12: Calling `ServiceLoader.load` without iterating

`ServiceLoader` uses lazy discovery and instantiation. Merely creating a `ServiceLoader` does not guarantee providers have been created or fully validated.

## 20. Suggestions for Designing a Controlled Warm-Up API

If you need to warm services that share a common interface, prefer **warming at the use-case layer** rather than unbounded reflection:

~~~java
public interface Warmable {
    void warmUp();
}
~~~

Services can implement this contract and warm a **safe, idempotent code path with timeouts/quotas**. An orchestrator invokes it across a list of approved components.

Key considerations:

- `warmUp()` may run multiple times or be retried; ensure it is safe to do so.
- If the system uses DI, invoke it after configuration and dependencies are ready.
- Avoid writing production data, sending external notifications, or creating real transactions just to warm up.
- Expose readiness **after** mandatory warm-up; optional warm-up can run at lower priority with cancellation support.
- Record separate metrics for warm-up time, failures, and CPU/memory cost.
- For plugins, expose the shared `Warmable` interface from a common parent loader rather than letting child-first loaders define their own copy.

This is an **illustrative design**, not a Java SE API named “preload all applications.” Every strategy must integrate into the application's own lifecycle.

## 21. Self-Check Exercises

**1. How does loading differ from initialization?** Loading creates a runtime `Class` from bytes, whereas initialization executes `<clinit>` according to active-use rules.

**2. Does `loader.loadClass(name)` automatically run static initializers?** It does not request initialization. That is a key difference from `Class.forName(name, true, loader)`.

**3. What does `Class.forName(name, false, loader)` do?** It finds/loads a `Class` without requesting initialization; it does not automatically warm DI or JIT.

**4. Why might `Feature.class` not print the static initializer message?** A class literal does not by itself cause the class to be initialized.

**5. What can calling a static method for the first time do?** Active use triggers initialization of the declaring class if needed before executing the method.

**6. Which metrics can preloading improve?** First-use latency and some tail spikes, if it genuinely moves necessary work off the request path.

**7. Which metrics can preloading worsen?** Startup/readiness latency, I/O/CPU contention, and memory footprint.

**8. Why must benchmarks use a fresh JVM process?** If an already-initialized `Class` is reused, cold latency results are no longer valid.

**9. Why is JIT warm-up not equivalent to class loading?** JIT requires execution profiles and hotness; loading a `Class` does not execute all of its methods.

**10. Why can preloading static initializers cause startup to fail?** They can throw exceptions, wait on I/O, spawn threads, or depend on configuration that is not ready yet.

**11. Does `ServiceLoader.load` guarantee provider classes are initialized?** No; provider discovery and instantiation are typically lazy during iteration.

**12. Why can RAM usage increase after preloading?** More `Class` metadata in Metaspace, static caches, and potentially additional heap/code cache usage.

**13. Does a new class loader loading the same binary name reuse the initialization of an old class loader?** Not automatically; they can be two distinct runtime `Class` objects.

**14. Should all optional plugins be preloaded at process start?** Not by default. Categorize by SLO, load selectively, measure startup vs. first-use, and protect code sources.

**15. Can preloading replace readiness/liveness probes?** No. Readiness must reflect whether the system can serve valid traffic; preloading is only one lifecycle strategy.

## 22. References

- **JLS Java 17 `12.2 — Loading of Classes and Interfaces:`** https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.2
- **JLS Java 17 `12.3 — Linking of Classes and Interfaces:`** https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.3
- **JLS Java 17 `12.4 — Initialization of Classes and Interfaces:`** https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4
- **JVMS Java 17 `5 — Loading, Linking and Initializing:`** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html
- **Java SE 17 — ClassLoader:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- **Java SE 17 — Class.forName:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- **Java SE 17 — ServiceLoader:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- **Java SE 17 — JFR APIs:** https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/module-summary.html
- **Java SE 17 — java launcher (Unified Logging, JFR, CDS options):** https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
