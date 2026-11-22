# Reusing a Loader vs. Creating a Loader per Request

## 1. The Problem: What Should a ClassLoader Lifecycle Be Tied To?

In a Java application with plugins, rule engines, an application server, or a system that loads code from JARs, a single class may serve thousands of requests. There are two ways to organize this:

- **Reuse loader:** create one `ClassLoader` for a plugin/version's code environment and reuse it across many requests; each request can still create its own new objects.
- **Loader-per-request:** create a separate `ClassLoader` for each request, load classes through it, handle the request, and then close or discard the loader.

The difference is not just the cost of the `new` operator. It affects **class identity, metaspace memory, verification/linking/initialization, static state, resource/JAR handles, warm-up speed, JIT, reloadability, and cast errors**.

~~~text
REUSE BY PLUGIN VERSION

Plugin v1 --> Loader L1 --> demo.Worker (Class A)
                         |         |         |
                      Request 1  Request 2  Request 3
                      object #1  object #2  object #3


LOADER PER REQUEST

Request 1 --> Loader L1 --> demo.Worker (Class A)
Request 2 --> Loader L2 --> demo.Worker (Class B)
Request 3 --> Loader L3 --> demo.Worker (Class C)

If each child defines Worker itself:
Class A != Class B != Class C
~~~

**Default recommendation:** reuse a class loader **per plugin/version or code-loading environment**, and do not create a new loader for every HTTP/job request if those requests share the same code and classpath. This does not mean you must share a single service instance with mutable state; **loader lifecycle and object lifecycle are two independent decisions**.

Nor should every case use a single loader for the entire JVM. If different versions, tenants, or modules genuinely need different code, loader boundaries should reflect those boundaries.

## 2. A ClassLoader Is Not an Ordinary Object

In the JVM, runtime class identity consists of **binary name + defining class loader**. Therefore, creating a new loader *can* create a new `demo.Worker` class with its own static state, initialization, and metadata, even when the bytes are identical.

~~~text
Loader A defines demo.Worker -> Class A
Loader B defines demo.Worker -> Class B
Class A != Class B
~~~

**Essential condition:** two new loaders do not necessarily create two classes. If parent-first delegation finds `demo.Worker` in the parent, both children can return that same runtime class. When comparing reuse against loader-per-request, you must check `type.getClassLoader()` and `typeA == typeB`, rather than merely counting `new URLClassLoader` calls.

For classes defined by a child loader itself, each generation has its own static fields and initialization; any retained `Class<?>`, reflection metadata, or instance from an older generation can prevent GC/unloading. Thus, the decision to reuse affects CPU, identity, and resource lifecycles alike.

## 3. What Costs Can Reusing a Loader Save?

When loading its own code for the first time, a loader may have to go through delegation/lookup, read class bytes from a directory/JAR, define the class, and perform verification, linking, and initialization at the points required by the JVM. When reusing the same runtime class, it does not have to be redefined on every request.

| Cost category | Reuse loader | Create loader per request |
| --- | --- | --- |
| Loader creation and configuration | Once per code version | Repeated every request |
| Class/JAR entry lookup | Can leverage already-loaded classes/lookup metadata | May have to search again per new loader |
| Define, verify, link | Runtime class already exists | May repeat if each new child defines it itself |
| Static initialization | Once per runtime class | May repeat for each new class copy |
| Metadata/metaspace | Fewer distinct class copies under proper lifecycle | Can create many class copies in a short time |
| JIT profiling/code cache | Opportunity to warm up and reuse methods of the same class | Many separate class/method copies can increase pressure |
| File/JAR handles | Held and closed per plugin lifecycle | Must be opened/closed frequently and by the proper owner |
| Cleanup | Closed when retiring the version | Closed on every request, hard to control when asynchronous |
| Type identity | Stable across requests of the same version | May differ per request |

Do not interpret this table as a guaranteed speedup by some fixed percentage. If a request spends most of its time on network/database I/O, or if the classes are actually all returned by the parent loader, the difference may be small. If each request loads hundreds of implementation classes from a dedicated JAR, the repeated cost can be significant.

An illustrative model, not a measurement:

~~~text
N = number of requests in a plugin version
S = loader initialization + required load/link cost
W = business logic work for one request
L = lookup/cache overhead when reusing the class
R = cleanup cost of one loader

Reuse:           T ≈ S + N × (W + L) + R
Loader/request:  T ≈ N × (S + W + R)
~~~

This is a simplified expression; in reality there are OS/JVM caching, lazy initialization, compilation, and GC. It illustrates that **setup can be amortized** when reusing a loader, rather than making a quantitative claim.

### Reusing a Class Does Not Mean Reusing an Instance

~~~text
Loader L
    |
    +--> Class<demo.Worker>
             |
             +--> instance per request #1
             +--> instance per request #2
             +--> instance per request #3
~~~

You can load the `Class<?>` or create a factory once while still giving each request its own object. This is usually a better choice than creating a new runtime class just to isolate request data.

## 4. Caching and findLoadedClass

The default `ClassLoader.loadClass(String, boolean)` algorithm checks `findLoadedClass(name)` first, then delegates to the parent, and only uses the child's `findClass` when needed.

~~~java
Class<?> first = loader.loadClass("demo.Worker");
Class<?> again = loader.loadClass("demo.Worker");
System.out.println(first == again);
~~~

This is an illustrative snippet inside a method that has a `loader` variable. Under valid class loading, two lookups of the same binary name through the same initiating loader return the same `Class<?>`, without defining a new class on the second call.

**Do not confuse this cache with an application-written Map.** `findLoadedClass` and the JVM manage the identity of runtime classes. A custom `Map<String, Class<?>>` can still hold strong references to the loader after a reload and cause retention. If you cache by class, you need a **lifecycle clear** or an appropriate weak-reference model; do not assume GC will automatically collect a static map on the host.

`ClassLoader.loadClass` also uses a class-loading lock to avoid races when the same name is requested concurrently. Sharing a single loader does not mean one request can arbitrarily define the same class multiple times; the JVM and loader coordinate class loading. For a custom loader, you must follow `getClassLoadingLock(name)` and parallel-capable rules when overriding.

## 5. Java 17+ Example Reproducing the Difference

Example compiling two separate files:

~~~text
example/
├── src/
│   ├── plugin/
│   │   └── demo/Worker.java
│   └── host/
│       └── LoaderReuseDemo.java
└── out/
    ├── plugin/       (plugin bytecode output)
    └── host/         (host bytecode output)
~~~

**Only out/host is placed on the application classpath** at runtime. Out/plugin is loaded by a separate URLClassLoader; if you accidentally add the plugin to the host classpath, the parent can define Worker first and alter the experimental conditions.

### File src/plugin/demo/Worker.java

~~~java
package demo;

public final class Worker {
    private static int constructions;

    public Worker() {
        constructions++;
    }

    public String work() {
        return "ok";
    }

    public static int constructions() {
        return constructions;
    }
}
~~~

The static counter is only to show per-class-loader state. `constructions++` is **not thread-safe**; the example runs on a single thread so the output is deterministic. In concurrent programs, use appropriate synchronization/atomic mechanisms rather than copying this snippet into production code.

### File src/host/LoaderReuseDemo.java

~~~java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public class LoaderReuseDemo {
    public static void main(String[] args) throws Exception {
        URL url = Path.of(args[0]).toAbsolutePath().toUri().toURL();
        ClassLoader parent = LoaderReuseDemo.class.getClassLoader();

        try (URLClassLoader loader = new URLClassLoader(
                new URL[]{url}, parent)) {
            Class<?> type = loader.loadClass("demo.Worker");
            Object first = type.getDeclaredConstructor().newInstance();
            type.getDeclaredConstructor().newInstance();

            System.out.println("reuse same class: "
                    + (type == loader.loadClass("demo.Worker")));
            System.out.println("reuse work: "
                    + type.getMethod("work").invoke(first));
            System.out.println("reuse constructions: "
                    + type.getMethod("constructions").invoke(null));
        }

        Class<?> previous = null;
        boolean distinct = false;
        for (int request = 1; request <= 2; request++) {
            try (URLClassLoader loader = new URLClassLoader(
                    new URL[]{url}, parent)) {
                Class<?> type = loader.loadClass("demo.Worker");
                type.getDeclaredConstructor().newInstance();

                if (previous != null) {
                    distinct = previous != type;
                }
                System.out.println("fresh " + request + " constructions: "
                        + type.getMethod("constructions").invoke(null));
                previous = type;
            }
        }
        System.out.println("fresh types differ: " + distinct);
    }
}
~~~

**Reuse scenario:** a single loader loads Worker. Two instances increment the static count to 2; repeated lookup returns the same `Class<?>`.

**Per-request scenario:** each request creates and closes a loader. Each loader defines its own Worker, so the counter starts over; the two Worker copies have different Class identities.

The `previous` variable intentionally holds a reference to an old Class for comparison. Therefore, the example does **not** prove that class unloading happened immediately when the loader closed.

### Compile and Run on Linux/macOS

From inside the example directory:

~~~bash
mkdir -p out/plugin out/host

javac --release 17 -d out/plugin \
  src/plugin/demo/Worker.java

javac --release 17 -d out/host \
  src/host/LoaderReuseDemo.java

java -cp out/host LoaderReuseDemo out/plugin
~~~

### Compile and Run on Windows PowerShell

~~~powershell
New-Item -ItemType Directory -Force out\plugin, out\host | Out-Null
javac --release 17 -d out\plugin src\plugin\demo\Worker.java
javac --release 17 -d out\host src\host\LoaderReuseDemo.java
java -cp out\host LoaderReuseDemo out\plugin
~~~

### Exact Observed Stdout

~~~text
reuse same class: true
reuse work: ok
reuse constructions: 2
fresh 1 constructions: 1
fresh 2 constructions: 1
fresh types differ: true
~~~

The example compiles with `javac --release 17` and was actually run on a JDK; the output matches the six lines above.

### What the Experiment Proves

1. Creating two Worker objects in the **same loader** does not create two runtime Worker Class copies.
2. The static counter is shared among objects of a single runtime class.
3. A new loader that defines Worker itself creates fresh static state for each class copy.
4. Two `Class<?>` objects from different defining loaders have different identities.
5. `URLClassLoader.close()` is called via try-with-resources when each scope ends.

**Do not conclude** from this example by what percentage per-request is slower, how many bytes of metaspace were allocated, or that classes unload immediately. Measuring performance requires a benchmark with warmup, concurrency, and appropriate JVM memory tracking.

## 6. Why Creating a New Loader per Request Has Consequences Beyond CPU

### Class Identity and Cast Errors

If the host holds a `Class<?>` Worker from loader A and then tries to use a Worker object from loader B as if it were the same concrete type, the JVM may throw `ClassCastException` even though the binary name is the same.

~~~text
Loader A defines demo.Worker -> Worker A
Loader B defines demo.Worker -> Worker B

WorkerA.class != WorkerB.class
~~~

To exchange objects across plugin/request loaders, you need a **shared API interface** defined by a parent loader, such as `api.Task`. Two separate Worker copies can both implement **the same host interface** if they properly delegate that interface to the parent.

If the interface itself is also packaged and defined inside each child, having the same `api.Task` name is not enough—casting to the host's API can still fail. This is why per-request isolation requires careful type-boundary design, not just a performance benchmark.

### Static Initialization and State

When a different loader defines Worker itself, static initialization applies to the **new class**. Resetting a static cache or counter is not resetting a previous instance; it is **a different runtime class copy**.

Creating a new loader solely to prevent state from leaking between requests is usually too heavy-handed. Prefer designing request-scoped data or explicit instance lifecycles. If a service genuinely has static mutable state that must be reset, design cache/session ownership properly; do not use a class loader as an object pool.

### Metaspace and Class Unloading

Each class definition has metadata managed by the JVM. If many loaders each hold hundreds of live classes, peak metaspace and class counts can grow. After closing a loader, class unloading **does not happen instantaneously**: the class/loader must satisfy reachability conditions and the JVM must perform appropriate GC/unloading.

If the host retains a `Class<?>`, Method, Constructor, instance, thread context class loader (TCCL), ThreadLocal, listener, or map reference from an old loader, it can remain reachable. Loader-per-request without reference management increases churn and can even cause memory leaks.

### JIT/Warm-up

The JVM can collect profiling data and compile methods of runtime classes. Continuously creating many separate Worker definitions can make it harder to realize the warm-up benefits of a long-lived class copy, while increasing metadata/code cache pressure. However, the impact **depends on the JVM, workload, and runtime optimizations**; do not quote a speedup number without measuring.

## 7. Fair Benchmarking: What Needs to Be Measured?

To decide based on real data, you should distinguish at least:

| Metric | Meaning |
| --- | --- |
| Cold-start latency | Time from creating the loader to finishing the first request |
| Steady-state p50/p95/p99 | Latency after warmup under comparable load |
| Throughput | Requests per second at a given concurrency |
| Allocations | Object allocations and garbage collection pressure |
| Class counts/metaspace | Runtime class definitions and metadata memory |
| CPU/JIT/code cache | Time the JVM spends on class loading and optimization |
| JAR/file handles | Number of resource handles left open during the lifecycle |
| Reload duration | Time to switch versions and retire the old loader |

### A Sound Test Setup

1. Fix the JDK, JVM options, machine, plugin JAR, business logic, and dependencies.
2. Scenario A: **one loader for the same plugin version**, initialized beforehand and then serving N requests using separate objects.
3. Scenario B: **one loader per request**, with the same number of requests and the same business logic.
4. Measure **cold startup separately**; warm up before measuring steady-state.
5. For latency/throughput, run multiple measurement iterations and multiple JVM forks if appropriate; do not infer from a single run.
6. Keep concurrency, inputs, and classpath identical; ensure server logging or background tasks do not skew results.
7. **Verify the defining loader** to be sure scenario B actually defines its own classes rather than all returning the parent's Class.
8. Measure memory/metaspace alongside time, not just wall-clock latency.
9. Report p95/p99, throughput, allocations, and the exact workload; do not assign a universal overhead constant to all Java applications.

You can use **JMH** for JVM microbenchmarks because it supports warmup, forks, measurement, and safeguards against common measurement pitfalls. Even with JMH, the benchmark must model the full lifecycle (setup + load + instance + work + close), not just measure the URLClassLoader constructor.

### Why a Single System.nanoTime Is Misleading

~~~java
long start = System.nanoTime();
// An operation you want to measure.
long nanos = System.nanoTime() - start;
~~~

This is only an illustrative snippet. Elapsed time can be affected by JIT warmup, class initialization, OS file cache, GC, thread scheduling, or CPU frequency. If the benchmark does not make the computed result observable, the JVM may also optimize away parts of the computation.

**Measure equivalent work:** for per-request, you must include load/link/instance/close. For reuse, you must include setup in cold-start and amortize the cost over an appropriate number of requests when evaluating total cost. Do not compare a cold run of A against steady-state of B and draw a conclusion.

### JVM Diagnostics

On a JDK that supports unified logging, you can run:

~~~bash
java -Xlog:class+load=info -cp out/host LoaderReuseDemo out/plugin
~~~

The log can be many lines long and varies by environment, so it should not be copied as sample stdout. You can also inspect JFR/Java Mission Control, heap dumps, JVM metrics, and class unloading logs when analyzing memory/loader retention. **Do not treat class unloading logs as proof that JAR handles have been closed**: those are two different resources.

## 8. Concurrency: Reusing a Loader Does Not Mean Reusing a Mutable Object

A ClassLoader used by multiple threads to load classes must still obey `loadClass` synchronization/locking. However, the objects and static state it defines are **not automatically thread-safe**.

In the example:

~~~java
private static int constructions;

public Worker() {
    constructions++;
}
~~~

If multiple threads construct Worker concurrently, `++` is not atomic and updates can be lost. One illustrative option:

~~~java
private static final java.util.concurrent.atomic.AtomicInteger
        COUNT = new java.util.concurrent.atomic.AtomicInteger();

public Worker() {
    COUNT.incrementAndGet();
}
~~~

These two snippets are class members, not standalone programs. For a real service, you can use immutable values, request-scoped objects, appropriate pooling, locks, or concurrent collections depending on the problem.

**Do not solve thread safety by opening a URLClassLoader per request** if requests share other resources such as a database, files, or a host registry. It may separate some static fields, but it does not replace a proper concurrency design.

### Do You Need a ClassLoader Pool?

A pool of multiple class loaders for the same plugin/version can multiply runtime class definitions, static copies, and JAR resources; objects from loader A cannot be cast to the concrete Class of loader B. If you do not need namespace isolation, there is usually no reason to maintain a large pool of loaders. Consider pooling **service instances** instead of loader objects when there is an actual bottleneck.

## 9. Reusing at the Right Lifecycle: per Plugin, per Version, Sometimes per Tenant

A common architectural choice:

~~~text
Application Loader
  ├── api.Task       (shared contract)
  └── PluginManager
           |
           +-- Plugin "pricing" v1 --> Loader L1
           |                           Request A/B/C
           |
           +-- Plugin "pricing" v2 --> Loader L2
                                       Request D/E/F
~~~

Advantage: requests for the same version share one code namespace, while v1 and v2 are not forced to share the same concrete Class identity.

For hot reload:

1. Place the new JAR under a version-specific filename to avoid overwriting a file still held by the old loader.
2. Create a new loader L2 and verify plugin/service readiness.
3. Switch new request routing to v2; in-flight requests can finish on v1.
4. Once v1 has quiesced, stop plugin tasks/threads/callbacks and close dedicated InputStreams, JarFiles/ZipFiles.
5. Close URLClassLoader v1 when no concurrent class-loading activity remains.
6. Clear strong references to L1, old Class/Method caches, registry entries, and ThreadLocals/TCCL where appropriate.
7. Clean up the old JAR file once file handles have been released.

`URLClassLoader.close()` has its own contract: it closes files opened by the loader and prevents loading new classes/resources, but it does not destroy already-defined instances/classes. If a thread is actively loading while `close()` is called, the outcome is not guaranteed; therefore, managing in-flight requests and stopping the lifecycle cleanly is necessary.

**Do not reuse one loader forever across all versions.** Once Worker has been defined by loader L1, replacing the JAR on disk does not cause the JVM to redefine Worker v2 in L1. A new loader is a clean version boundary.

### Cases Where More Loaders Are Needed

- Tenants A and B have genuinely different code/classpath/dependencies.
- Different plugin versions need to coexist side by side.
- Batches of dynamic code have independent unload lifecycles.
- Named module configurations/ModuleLayers are resolved differently.
- Testing class loading policies or class identity.

In those cases, create loaders **along the required isolation boundaries**, with explicit limits and retirement timing. A separate loader is not a security sandbox for untrusted code: a class loader by itself does not isolate the process, filesystem, network, or CPU.

## 10. Common Design Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Creating a URLClassLoader unnecessarily for every request | Repeated setup/loading, allocation & cleanup churn | Reuse per plugin/version |
| Sharing a mutable service instance across multiple requests | Race conditions/state leakage | Per-request instances or a thread-safe service |
| Assuming a new loader always returns a new Class | Parent may define the class, skewing benchmarks | Compare Class objects and defining loaders |
| Treating a static field as a JVM-wide shared variable | Class copies have separate static state | Use parent-side API/shared state or an explicit store |
| Closing the loader right after loadClass and returning a long-lived instance | Lazy class/resource loading failures | Keep the loader alive for the serving scope |
| Failing to close loader/streams after retirement | JAR file handles and resource leakage | Try-with-resources/lifecycle shutdown |
| Caching Class/Method in a host singleton without clearing on reload | Old loader cannot be GC'd | Version-scoped cache with clear |
| Putting the plugin JAR on the host application classpath | Parent-first breaks expected isolation/reload | Separate plugin source from host -cp |
| Using a per-request loader as a security sandbox | Does not isolate OS permissions | Appropriate process/container isolation |
| Benchmarking only new URLClassLoader | Excludes class lookup, initialization, and close | Measure the full request lifecycle |
| Benchmarking once on a cold JVM | Mixes startup, GC, and JIT | Warmup, forks, multiple runs |
| Using one loader for v1 and v2 and modifying the JAR file | Already-defined class bytecode does not auto-update | Create a new loader for the new version |
| Using child-first for a shared API | Two runtime API copies, ClassCastException | Parent-first for contract packages |

## 11. Performance Diagnostic Checklist

1. Does each request actually need a **new code namespace**, or only a new instance/state?
2. How many loaders are created per plugin/version? Is there a cap and an owner?
3. **Which loader defined** the plugin class? Are `type.getClassLoader()` and `Class<?>` identity as expected?
4. Did the parent already define the class, or did the child define it itself?
5. How does first-time load/verify/link/initialize time compare to steady-state request handling?
6. Do metaspace/class counts, heap allocations, and JIT/GC increase when many loaders are created?
7. Are TCCL, ThreadLocals, task queues, registries, or static caches retaining old loaders?
8. Are any resource/JAR handles still open, or are files locked on Windows after a reload?
9. Is the loader still in use by requests when `close()` is called?
10. Do shared APIs/interfaces live in the parent and share the same Class identity across plugins?
11. Do load/cast/reload tests cover concurrent requests and multiple versions?
12. Does the benchmark measure the same workload, N requests, concurrency, warm-up, and report p95/p99/throughput?

## 12. Self-Check Questions

**Q1.** A loader loads `demo.Worker` and then calls `loadClass("demo.Worker")` 100 more times. Does the JVM create 100 different Class objects?

**A:** No, under the standard class loading contract. The same binary name and initiating loader yield a consistent Class identity; there may still be lookup overhead, but no new class is defined on each call.

**Q2.** Do two different URLClassLoaders reading the same Worker.class necessarily return two different runtime Classes?

**A:** No. If both delegate to a parent that already defined Worker, they can both return the parent's copy. Only if each child actually defines Worker itself will there be two distinct Class identities.

**Q3.** Does reusing a loader require sharing a single service object across requests?

**A:** No. Many requests can create their own separate instances from the same runtime Class.

**Q4.** Why does the static counter start over in each new loader?

**A:** When a new child defines its own runtime Worker copy, each Class has its own static storage and initialization.

**Q5.** Does closing a loader per request guarantee immediate class unloading?

**A:** No. Unloading depends on reachability and JVM GC; `close()` mainly manages class/resource loading sources and file handles.

**Q6.** When should you create a new loader instead of reusing one?

**A:** When you need an independent classpath/version/tenant/batch code namespace. Typically created per **plugin version** or code-loading boundary, not per request.

**Q7.** Can you conclude that reuse is ten times faster solely from the six-line stdout example?

**A:** No. The example demonstrates runtime class identity and static state, **not performance**. You need a benchmark covering cold/steady-state, throughput, allocations, and memory.

**Q8.** Why can a memory leak still occur even when reusing a loader?

**A:** The loader may live too long, caches/threads/registries may hold old Class references across versions, or resources may not be closed on retirement. Reuse must be paired with an explicit lifecycle.

## Official References

- [Java SE 21 — ClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, `findLoadedClass`, delegation, and getClassLoadingLock.
- [Java SE 21 — URLClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLClassLoader.html): loading classes from URLs and `close()`.
- [JVMS Java SE 21 §5.3 — Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3): runtime class identity and defining loader.
- [JVMS Java SE 21 §5.5 — Initialization](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.5): static initialization.
- [Java SE 21 — Class](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html): Class objects and `getClassLoader`.
