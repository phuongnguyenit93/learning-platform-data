# Trade-offs Between Loader Count, Isolation Level, and Metaspace Size

> **Java Core → ClassLoader → Performance.** In a plugin architecture, multiple `ClassLoader`s can help modules use different dependency versions, load/unload individual generations independently, and protect type identity across plugins. However, if each loader **redefines thousands of runtime classes on its own**, the JVM must retain additional metadata for those class definitions. This lesson analyzes the trade-off between **loader count**, **isolation granularity**, **used/committed/reserved Metaspace**, **class unloading**, heap/JIT/I/O overhead, and how to benchmark properly on Java 17+ (HotSpot). The goal is to choose loader boundaries based on actual requirements, rather than assuming “one loader is always better” or “more loaders are always better.”

## 1. Three Variables to Balance

A plugin system typically needs to satisfy three goals:

1. **Isolation:** avoid binary name and version conflicts between plugins, and enable replacing a plugin without restarting the entire JVM.
2. **Memory:** limit duplicated classes/metadata, heap caches, JIT-compiled code, class-loading infrastructure, and JAR handles.
3. **Operations:** start up fast enough, support clean shutdown/unloading, preserve correct shared API identities, and remain diagnosable when leaks occur.

Conceptual diagram:

~~~text
       FEWER LOADERS                         MORE LOADERS
             |                                     |
  +--------------------+               +------------------------+
  | Shared loader      |               | Loader P1  | Loader P2 |
  | plugin A + B + C   |               | lib 1.0    | lib 2.0   |
  +--------------------+               +------------+-----------+
             |                                     |
  + Fewer duplicate definitions         + Isolate versions/ABI
  + Less loader/JAR overhead            + Retire P1 independently
  - Hard to unload A alone              - Class metadata may duplicate
  - Prone to version conflicts          - More loaders, caches, locks,
                                          lifecycle/resource owners
~~~

**You cannot deduce exact memory usage from `loaderCount` alone.** You need to know how many classes each loader defines, how large those classes are, how many dependencies are shared vs. private, whether module layers or generated classes are involved, and how many old generations remain reachable.

## 2. Root Mechanism: Runtime Type Identity

According to the JVM Specification, a runtime class or interface is uniquely identified by its **binary name and defining class loader**.

~~~java
Class<?> a = loaderA.loadClass("plugins.Widget");
Class<?> b = loaderB.loadClass("plugins.Widget");
boolean sameType = a == b;
~~~

This is an illustrative snippet; `sameType` **can be true** if both A and B delegate to a parent that already defined `plugins.Widget`. It is **false** if each loader calls `defineClass` for `plugins.Widget` itself. Therefore, the number of **loader objects** does not equal the number of **class definitions**.

### 2.1. Two Cases to Distinguish

**Parent sharing case:**

~~~text
               SharedParentLoader
                 define api.Service
                 define common.JsonCodec
                   /        \
          PluginLoaderA   PluginLoaderB
          define AImpl    define BImpl
                   \        /
                   shared API classes
~~~

With parent-first delegation, child loaders can return the same `api.Service.class` and `common.JsonCodec.class`, so there is no need to duplicate metadata for **runtime classes defined by the parent**.

**Duplicate private definitions case:**

~~~text
         PluginLoaderA                 PluginLoaderB
       define vendor.Parser          define vendor.Parser
       define vendor.Model           define vendor.Model
       define vendor.Util            define vendor.Util

         vendor.Parser@A != vendor.Parser@B
~~~

Each loader has its own class definition, its own static fields, and a different identity. The VM may reuse or share some data at other levels depending on the implementation, but it **does not treat the two runtime classes as a single type**, and must manage metadata for each definition.

**Important:** A runtime `Class<?>` loaded via child delegation still has `getClassLoader()` pointing to the **defining parent**, not necessarily the child that initiated `loadClass` (the initiating loader). When measuring duplication, count **definitions per defining loader**, not just how many times `loadClass` is called.

## 3. What Does Metaspace Hold, and How Does It Differ from the Java Heap?

On modern HotSpot, Metaspace uses native memory to manage various kinds of **class metadata** (for example, representations of classes, methods, and constant-pool metadata). The Java heap and Metaspace are separate domains in performance analysis.

| Component | Conceptual area / lifecycle | Consequence when duplicating plugins |
| --- | --- | --- |
| Runtime class metadata | HotSpot Metaspace; tied to class loader data/lifetime | Defining the same bytecode across multiple loaders can increase metadata |
| Compressed class pointers/class metadata | May reside in compressed class space on HotSpot with corresponding configuration | May have large reserved virtual space but small committed memory |
| `Class<?>` mirrors, instances, arrays, static object graphs | Heap and runtime VM references | Static caches/instances can also grow with each generation |
| Dynamic proxies/lambda-generated classes | Runtime class definitions + heap instances | Can increase metadata, JIT/code cache, and object counts |
| Compiled methods | Code cache / JIT-managed native memory | Hot methods of each runtime class may require separate compilation |
| Loader objects / URLs / cache structures | Java heap | Depends on loader implementation and number of resources |
| `JarFile`/open streams/file handles | VM/OS resources | Depends on lifecycle and `URLClassLoader.close()` |
| Threads/executors | Heap + native stacks/OS resources | Per-loader plugin thread pools can be very costly outside Metaspace |

### 3.1. Three Different Numbers: Used, Committed, Reserved

HotSpot/JMX statistics typically distinguish:

- **Used:** the amount of metadata currently in use by the allocator according to the corresponding metric.
- **Committed:** the amount of physical/virtual-memory backing committed for the pool; this can exceed used because the allocator keeps free space/manages chunks.
- **Reserved:** the **virtual address space** range reserved for potential future commits; this does not mean the process is actually consuming that much RAM.

For example, a line showing `reserved = 1 GiB` for compressed class space **does not mean the JVM is using 1 GiB of RAM for class metadata**. You must compare used/committed, and under memory pressure also inspect process RSS/cgroup, GC/JIT/thread/native allocations.

**Do not blindly sum** JMX Metaspace pools and all Native Memory Tracking (NMT) buckets as two independent totals: the tools may be describing the **same** allocations at different levels of categorization or granularity.

### 3.2. Metaspace Is Not PermGen

Java 8 removed PermGen and introduced Metaspace in HotSpot (JEP 122). On Java 17/21/25, you should not configure `-XX:MaxPermSize` or refer to modern metadata as PermGen. However, “Metaspace” is a **HotSpot JVM implementation** detail, not a JLS requirement that every JVM have a pool with this exact name and layout.

Memory growth in a plugin system is not always in Metaspace: a large `static byte[]` grows the **heap**, thread stacks grow **native memory**, and JIT-compiled code grows the **code cache**.

## 4. Estimation Model: There Is No Fixed MB per Loader

A mental model (not an official HotSpot formula):

\[
M_{\mathrm{metadata}} \approx M_{\mathrm{shared}} +
  \sum_{i=1}^{N} M_{\mathrm{classes\ defined\ by\ loader}\ i}
  + M_{\mathrm{allocator\ overhead}}
\]

Each `M_classes` depends on class count, methods/fields/constant pool, invokedynamic/generated classes, and live state. A loader may create **0** class definitions (pure delegation); another loader may define tens of thousands of types.

Examples **for reasoning, not benchmarks**:

- 10 loaders, each defining only 3 private classes and using 1,000 classes from the parent: low duplication.
- 10 loaders, each independently defining 1,000 similar classes: there can be roughly 10,000 plugin-side runtime definitions instead of 1,000.
- 100 loaders, each holding its own JAR scan caches, URL streams, and threads: increases total footprint across many areas outside Metaspace.

**Never multiply “loader count × 1 MB” and present it as a measured result.** A few very large classes can cost more than many small ones; meanwhile, allocator fragmentation, GC events, and JVM flags cause used/committed values to vary.

### 4.1. What Sharing Is Still Viable?

ClassLoader delegation allows **runtime class identity** to be shared at the parent. If plugins need to use `api.Plugin` and boundary DTOs, sharing them via the parent not only saves metadata but also prevents `ClassCastException` errors such as “X cannot be cast to X”.

However, sharing **does not mean** the parent should hold every library. When two plugins require binary-incompatible versions of a library, placing that library in a parent-first shared loader can cause `NoSuchMethodError`, `ClassNotFoundException`, `IllegalAccessError`, or incorrect behavior in the host. When a real dependency version conflict exists, **isolation is worth the cost**.

## 5. Design Options and Trade-offs

| Configuration | Isolation | Expected memory cost | Lifecycle / reload |
| --- | --- | --- | --- |
| Single loader for host + all plugins | Low | Few duplicated definitions | Hard to unload a plugin independently; usually requires restart |
| Shared parent API + one loader per plugin | Good between implementations | Separate metadata for private classes, shared API not duplicated | Replacing/retiring each plugin is relatively clear |
| One loader per tenant with the same bytecode | Very high between tenants | Can duplicate many definitions/caches | Isolates short-lived tenants, but easy to OOM |
| One loader per plugin generation | Isolates V1/V2 | **Peak overlap** while V1 and V2 coexist | Fits rolling updates; must drain V1 |
| Group loader for trusted plugins with compatible dependencies | Medium | Reduces duplication within the group | Unloading a single plugin is harder; higher coupling |
| New loader per request | Very high, usually unnecessary | Heavy startup/link/JIT/metadata churn | Almost never justified for normal service requests |
| Plugin in a separate process/JVM | Stronger boundary than classloaders | Higher total JVM baseline footprint | Independent management; OS-level RAM/CPU limits possible |

No single option wins every column. The choice depends on requirements for **security, ABI, tenant isolation, release cadence, Metaspace budget, latency SLOs, and cleanup reliability**.

### 5.1. When Should You Use One Loader per Plugin?

Appropriate when:

- Plugins have their own dependencies (including conflicting versions).
- You need to hot-swap plugin V1/V2 without restarting the application.
- You want clear resource ownership/routing boundaries.
- The number of plugins and class definitions fits within the memory budget.
- Shared API types live in a long-lived, versioned loader.

This is a good default for many plugin managers, **but you must measure it** with real workloads and plugin counts rather than treating it as “free.”

### 5.2. When Should You Group Loaders?

You can group modules when they use the **same dependency versions** and are always deployed/retired together. The benefit is fewer duplicate classes and less JAR scan metadata. Drawbacks:

- A group loader is a single namespace; it cannot load two versions of the same binary name.
- Static singletons and mutable state within the group may be shared unexpectedly.
- Reloading one module may force replacing the entire group.
- Class initialization failures in one type can affect multiple modules in the group.

Choose grouping **based on compatibility and lifecycle coupling**, not merely to save a few megabytes.

### 5.3. One Loader per Tenant: Beware the Multiplier

Suppose a SaaS system has 500 tenants running the same plugin bytecode. If each tenant has its own loader and redefines the entire framework/dependencies, class metadata and caches can scale with the number of tenants even though the business logic is identical.

If **runtime type identity isolation** is not required, it is usually better to:

- Share application/plugin classes across tenants.
- Isolate mutable tenant state in **objects and request contexts**, without creating new ClassLoaders.
- Enforce permissions at the API/business boundary (authorization/capabilities), rather than treating ClassLoader as a security sandbox.
- If tenant-level security/process limits are truly required, consider process/container isolation and measure baseline costs.

**ClassLoader is not a complete security boundary.** As of JDK 24, the Java Security Manager is permanently disabled (JEP 486); a custom loader alone does not prevent a plugin from accessing files or the network within the same process.

## 6. Peak Metaspace During Rolling Updates and Hot Reloads

A system has V1 active and is preparing V2:

~~~text
Time ----->
      V1 active metadata
      |===========================|
                        V2 prepare/live metadata
                        |===========================|
                        ^ cutover         ^ V1 can be GC'd/unloaded after drain

OVERLAP window:
  V1 metadata + V2 metadata + associated heap/resources
~~~

At cutover time, V1 code may still be serving **in-flight requests**. If V2 is prewarmed with many classes, peak Metaspace can exceed steady-state usage. If V1 fails to unload because a cache, TCCL, listener, or stack frame still retains its loader, generations accumulate and memory usage grows across reloads.

### 6.1. Capacity Planning Without Fabricated Numbers

Suppose you measure in practice:

- `M_live`: committed metadata when one generation is stably active.
- `Delta_prepare`: additional committed metadata when loading/prewarming V2.
- `Delta_overlap_other`: extra heap/code cache/thread/JAR native memory during overlap.
- `Headroom`: memory margin for GC/JIT/traffic bursts.

After establishing a baseline and taking repeated measurements, budget at least enough for **steady state + peak overlap + margin**, without exceeding process/cgroup/host limits. If these values have not been measured, **do not** assign arbitrary MB numbers to them.

### 6.2. Why `active = newGeneration` Alone Does Not Free V1

References can still remain from:

- A request currently executing a V1 method.
- `Thread.currentThread().getContextClassLoader()` (TCCL) on a pool worker.
- `ThreadLocal` values, static maps in the host, and reflection `Class/Method/MethodHandle` caches.
- `ServiceLoader` provider caches and DI/framework registries.
- Executor tasks, event listeners, logging/JDBC registrations, and JNI references.
- A `ModuleLayer` or `ClassLoader` still held by a registry.

You must **quiesce → drain → unregister/close → clear caches/restore TCCL → close loader → release strong references**. `URLClassLoader.close()` releases JAR/file handles managed by the loader; it does not directly destroy already-loaded `Class<?>` objects and does not force JVM class unloading.

## 7. Elastic Metaspace and What Not to Promise

JEP 387 **Elastic Metaspace** (integrated since JDK 16) improves how HotSpot manages and **uncommits unneeded memory** after class unloading. It gives workloads that create and destroy many loader generations a more flexible way to return part of committed memory to the operating system.

However:

- JEP 387 **does not mean** every byte of class metadata from an old loader vanishes immediately after `close()`.
- First, the loader must become **eligible for GC**; as long as strong roots remain, its metadata must stay alive.
- The JVM/GC may not have run an unload cycle yet; the allocator may also retain chunks for reuse or keep partially used chunks committed.
- **Reserved virtual space** can remain large and steady even as committed/used memory drops; do not mistake this for a native RAM leak.
- Collector configuration, JVM version, flags like `-XX:MetaspaceReclaimStrategy`, compressed class space, and the OS all affect reclamation and metrics; do not treat a single flag as a cure for a classloader leak.

**Fix the root cause** (sensible loader reuse, sharing, cleanup) before raising memory limits. If a retention path exists from the host, increasing `-XX:MaxMetaspaceSize` only delays the failure without removing the root.

## 8. Lab 1 (Java 17+): Same Bytecode, Two Defining Loaders

This lab compares a single reused loader against two loaders that actually define the same binary name. Run on Java 17+; do **not** put the plugin JAR on the application classpath.

### 8.1. Directory Tree

~~~text
loader-tradeoff-lab/
├─ plugin-src/demo/plugin/Action.java
├─ host-src/LoaderIdentityDemo.java
└─ build/
   ├─ plugin/      (created during build)
   ├─ host/
   └─ action.jar
~~~

**`plugin-src/demo/plugin/Action.java`**

~~~java
package demo.plugin;

public final class Action {
    public String name() {
        return "action";
    }
}
~~~

**`host-src/LoaderIdentityDemo.java`**

~~~java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class LoaderIdentityDemo {
    public static void main(String[] args) throws Exception {
        URL jar = Path.of("build", "action.jar")
                .toAbsolutePath().toUri().toURL();

        ClassLoader parent = ClassLoader.getPlatformClassLoader();

        try (URLClassLoader shared =
                     new URLClassLoader(new URL[] {jar}, parent);
             URLClassLoader isolatedA =
                     new URLClassLoader(new URL[] {jar}, parent);
             URLClassLoader isolatedB =
                     new URLClassLoader(new URL[] {jar}, parent)) {

            Class<?> shared1 = shared.loadClass("demo.plugin.Action");
            Class<?> shared2 = shared.loadClass("demo.plugin.Action");
            Class<?> separateA = isolatedA.loadClass("demo.plugin.Action");
            Class<?> separateB = isolatedB.loadClass("demo.plugin.Action");

            System.out.println("one loader, same class="
                    + (shared1 == shared2));
            System.out.println("different loaders, same class="
                    + (separateA == separateB));
            System.out.println("same binary name="
                    + separateA.getName().equals(separateB.getName()));
            System.out.println("different defining loaders="
                    + (separateA.getClassLoader()
                        != separateB.getClassLoader()));
        }
    }
}
~~~

### 8.2. Compile and Run (POSIX shell)

~~~bash
mkdir -p build/plugin build/host

javac --release 17 -d build/plugin \
    plugin-src/demo/plugin/Action.java

jar --create --file build/action.jar -C build/plugin .

javac --release 17 -d build/host \
    host-src/LoaderIdentityDemo.java

java -cp build/host LoaderIdentityDemo
~~~

**Expected stdout:**

~~~text
one loader, same class=true
different loaders, same class=false
same binary name=true
different defining loaders=true
~~~

What the lab **proves**: the same binary name can have just one runtime type in a shared loader, but **two runtime types** when each isolated loader defines the JAR bytes itself. What the lab **does not measure**: exact Metaspace bytes added, class loading time, throughput, or GC class unloading.

`try-with-resources` closes loader-owned JAR handles. The `Class<?>` local variables remain in scope, and loader classes can stay alive after close if other references remain; do not claim that “closing immediately frees all Metaspace.”

### 8.3. Shared API in Real-World Design

When the host and plugins need to cast objects to a common interface, **the parent must define the shared API**. A plugin class with a different defining loader can have the same interface name yet **not be assignable** to the host's interface if the child redefines it. Therefore, sharing `api.PluginService` both saves metadata and preserves type identity, while plugin-specific implementations should still be defined by the child.

## 9. Lab 2 (Java 17+): Observing ClassLoadingMXBean and Metaspace MXBean

Use the Java Management API to read **loaded class count**, the number of unloaded classes, and available memory pools. Values are runtime observations; **there is no fixed numeric stdout across JDKs/OSes/GCs**.

**`host-src/LoaderMetrics.java`**

~~~java
import java.lang.management.ClassLoadingMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryPoolMXBean;
import java.lang.management.MemoryUsage;
import java.lang.management.MemoryType;

public final class LoaderMetrics {
    public static void main(String[] args) {
        ClassLoadingMXBean classes =
                ManagementFactory.getClassLoadingMXBean();

        System.out.println("loaded-now=" +
                classes.getLoadedClassCount());
        System.out.println("loaded-total=" +
                classes.getTotalLoadedClassCount());
        System.out.println("unloaded-total=" +
                classes.getUnloadedClassCount());

        for (MemoryPoolMXBean pool :
                ManagementFactory.getMemoryPoolMXBeans()) {
            if (pool.getType() != MemoryType.NON_HEAP) {
                continue;
            }
            MemoryUsage usage = pool.getUsage();
            if (usage == null) {
                continue;
            }
            System.out.printf("%s: used=%d committed=%d max=%d%n",
                    pool.getName(), usage.getUsed(),
                    usage.getCommitted(), usage.getMax());
        }
    }
}
~~~

~~~bash
javac --release 17 -d build/host host-src/LoaderMetrics.java
java -cp build/host LoaderMetrics
~~~

**No expected numerical stdout**: pool names, counts, and values vary by JVM/startup; `getMax()` returns the pool's estimated limit or `-1` if undefined. **The `max` label is the pool limit returned by `MemoryUsage.getMax()` (or `-1` if undefined), not reserved address space.** `MemoryUsage` returns `init, used, committed, max`, with **no reserved field**.

### 9.1. Turning Metrics into a Valid Comparison

Good practice:

1. Run workload A with a single shared loader in a separate JVM; warm up until stable.
2. Run workload B with K isolated loaders in another JVM, with the same JDK/heap/GC flags and the same set of classes used.
3. Repeat multiple times, capturing JMX/class count/Metaspace metrics at **equivalent milestones**.
4. Also measure `System.nanoTime` for each load/initialization phase, latency/throughput, CPU, allocations, and file handles if those are bottlenecks.
5. In a multi-loader benchmark, each class should genuinely be defined by the loader under test rather than accidentally delegating the implementation to the host.
6. Subtract/compare against baseline and report jitter; do not compare two consecutive readings and assume all variance comes solely from loader count.

**Note:** `ClassLoadingMXBean.getTotalLoadedClassCount()` is cumulative since VM startup, **not the number currently alive**; `getLoadedClassCount()` is the number currently loaded. When evaluating leaks, track the trend of **currently loaded classes/loaders** and class unloading across multiple cycles, not just the cumulative count which naturally only increases.

## 10. Measuring with jcmd, Native Memory Tracking, and Logging on HotSpot

The following tools are documented in JDK 25; **support and flags depend on the JVM/distribution**:

~~~bash
# With the PID identified from jcmd -l:
jcmd <pid> help

# Class loader statistics:
jcmd <pid> VM.classloader_stats
jcmd <pid> VM.classloaders

# Metaspace summary and per-loader breakdown (if supported):
jcmd <pid> VM.metaspace basic
jcmd <pid> VM.metaspace show-loaders

# Native Memory Tracking summary (if enabled at startup):
jcmd <pid> VM.native_memory summary

# Trace class loading/unloading in a single run:
java -Xlog:class+load=info,class+unload=info \
    -cp build/host LoaderIdentityDemo
~~~

These are **diagnostic command templates**; replace `<pid>` with the actual PID and ensure the lab's class files are available. If a command is rejected, run `jcmd PID help` / `jcmd PID help VM.metaspace` to inspect the options supported by your actual runtime.

### 10.1. NMT Must Be Enabled Before Measuring

Launch the application with:

~~~bash
java -XX:NativeMemoryTracking=summary \
    -cp build/host LoaderIdentityDemo
~~~

In a long-running process, you can use:

~~~bash
jcmd <pid> VM.native_memory baseline
jcmd <pid> VM.native_memory summary.diff
~~~

**Do not chain two short-lived process commands assuming the PID will still exist.** The lab above exits quickly; `jcmd`/NMT commands must target a JVM that stays alive long enough, or be applied to a real service / a harness that keeps the JVM waiting.

NMT tracks **JVM native memory**, not all allocations made by arbitrary third-party native libraries. NMT also has runtime overhead; do not enable `detail` everywhere in production without measuring and having a clear need. NMT categories such as Class, Thread, Code, and GC reflect different parts of the footprint.

### 10.2. What Should a Capacity Dashboard Include?

If the system has a dashboard, track at least:

- Active plugin/tenant/generation count and the number of live defining loaders.
- Currently loaded classes, and classes loaded/unloaded over time.
- Metaspace used/committed (and compressed class space if applicable).
- Native memory categories Class/Code/Thread, process RSS, and cgroup memory.
- Heap used/GC pause times, number of JAR file handles, thread count, and JIT/code cache.
- Hot reload latency: generation preparation, cutover, drain, and resource close.
- 95th/99th percentile request latency during load/unload/rollout.
- Rate of `OutOfMemoryError: Metaspace`, class-loader retention, and leaked generations.

Mark **deployment/reload events** to explain spikes; do not treat every peak during a rollout as a leak.

## 11. How to Verify a ClassLoader Leak Instead of Guessing

If Metaspace grows with every plugin reload:

~~~text
ClassLoadingMXBean current count increases
       |
       v
Have old generations really STOPPED?
       |
       +-- No --> still have in-flight tasks/callbacks: valid or lifecycle bug
       |
       +-- Yes --> is ClassLoader V1 present in heap dump?
                     |
                     +-- Host static Map -> Class/Method/instance
                     +-- Worker -> TCCL or ThreadLocal value
                     +-- EventBus -> listener/captured lambda
                     +-- ServiceLoader/DI/serializer cache -> provider/type
                     +-- ModuleLayer/driver/JMX registry -> classes/handles
~~~

Steps:

1. Log the generation id and defining loader identity on load/retire.
2. Quiesce requests, stop executors/timers, and unregister listeners.
3. Clear host caches/`ThreadLocal`s, restore TCCL, and close owned streams/JARs.
4. Drop host references to old `Class<?>`, `Method`, `MethodHandle`, instances, layers, and loaders.
5. Observe across **multiple GC/class unload cycles**, rather than expecting an instant deadline.
6. If generations remain reachable, use a heap dump / dominator tree to find the **path to GC root**.
7. Re-measure with the same workload; a single `System.gc()` proves neither the presence nor the absence of a leak.

JLS `12.7` allows class unloading when the defining loader can be reclaimed; it does not require the JVM to unload immediately. `URLClassLoader.close()` is not `ClassLoader.unloadClass`. On some JDKs, Metaspace used may drop while committed/RSS does not drop immediately due to allocator/OS pages and GC policies.

## 12. Optimize Architecture Before Tuning Flags

A sensible order of priority:

1. **Remove unnecessary duplication**: use a shared parent loader for APIs/dependencies that all plugins genuinely share with the same version and lifecycle.
2. **Isolate private packages properly**: use separate loaders where version conflicts or hot reloads are required.
3. **Reduce concurrent generations**: bound V2 prewarming, and drain V1 early without failing requests.
4. **Cap the number of plugins/tenants per JVM** based on real memory profiling, not a guessed constant.
5. **Reduce eager loading and reflection scanning** if a plugin only uses a subset of its classes; measure latency before lazy-loading everything.
6. **Clean up cache/resource roots**: `ServiceLoader`, DI metadata, `Method`/`MethodHandle` caches, TCCL, `ThreadLocal`, threads, and JAR handles.
7. **Benchmark pool/group strategies** at realistic plugin counts, rather than assuming a microbenchmark predicts production SLOs.
8. **Last**, consider `-XX:MaxMetaspaceSize`, container limits, and reclaim flags on the specific JVM; test against service-level metrics.

**MaxMetaspaceSize** is a limit that can help fail fast or enforce a budget on HotSpot, but setting it too small causes `OutOfMemoryError: Metaspace`, while setting it too large can mask retention. Do not raise it indefinitely when a classloader leak is known.

### 12.1. When Class Sharing Can Break Compatibility

If `Plugin A` requires `lib.JsonParser` version 1, `Plugin B` requires version 2, and the two are not binary-compatible, forcing both to share a single parent `lib.JsonParser` class can cause one plugin to misbehave. Conversely, loading the library separately in A and B uses extra metadata but **guarantees separate type identity policies**, provided the public host boundary does not expose private library types.

The right split is:
- `api.*` and DTO/shared contracts: **shared parent**.
- `plugin.impl.*` and private versioned dependencies: **child**.
- Do not pass API-dependent classes across loaders by casting by name; use a shared interface or an explicit serialization/schema boundary.
- If using custom child-first delegation, scope it to specific packages and protect `java.*` and shared contracts; writing a custom `loadClass` requires accurate locking and parent delegation.

## 13. Comparing Isolation by Actual Goal

| Requirement | Separate ClassLoader needed? | Alternative / consideration |
| --- | --- | --- |
| Two versions of the same binary name in one JVM | Usually **yes** | Separate process or relocation if appropriate |
| Independent hot reload per plugin | Usually **yes**, new generation loader | Restart JVM when replacing the whole application |
| Per-tenant configuration data | **Not necessarily** | Separate instances/config context/authorization |
| Isolating filesystem/network permissions for untrusted code | **Not sufficient** | Process/container/OS boundary |
| Unloading part of an application | Lifecycle-scoped loader enables this | Hold no references, ensure GC eligibility |
| Minimizing class metadata for common libraries | Shared loader helps if versions are compatible | CDS/archiving depending on JDK, must measure; does not change class identity |
| Shortening plugin startup | Can reduce eager scanning/prewarming | Measure class loading costs and use appropriate lazy init |
| Isolating native code crashes | ClassLoader is not enough | Process isolation |
| Optimizing throughput across many plugins | Workload-dependent | Locking, pool usage, JIT, GC, bytecode generation |

**Design takeaway:** “Deeper isolation” should be justified by a clear requirement. Isolate **state** with objects when multiple tenants simply run one code version; isolate **code/versions** with loaders when multiple runtime definitions are truly needed; isolate **trust/resource failures** with process/OS boundaries when security and fault containment are required.

## 14. Self-Check Exercises

1. Will two `URLClassLoader`s with the same URL and the same parent **always** produce two runtime classes when calling `loadClass("X")`? **No**; if the parent defines X, both can delegate to the same class.
2. Are two loaders that each define the same binary name a single runtime type? **No**, identity includes the defining loader.
3. Does the number of loader objects equal the number of class definitions? **No**, a loader can define many, few, or zero classes.
4. Can multiple loaders defining the same library increase Metaspace? **Yes**, because metadata for separate runtime definitions is not the same as a single shared `Class`.
5. Does adding a loader always cost a fixed number of MB? **No**; footprint depends on definitions, allocator, and dependencies.
6. Does `reserved=1GiB` mean the JVM is holding 1 GiB of actual RAM in Metaspace? **No**; check used/committed.
7. Can using multiple loaders help unload a plugin without restarting the JVM? **Yes**, when isolation and lifecycle/root cleanup are done properly.
8. Does `URLClassLoader.close()` immediately unload classes? **No**.
9. Does `System.gc()` guarantee class unloading? **No**.
10. Can V1 and V2 coexisting during a rollout increase peak Metaspace? **Yes**, while both generations are live.
11. Can a `Method` in a host static cache keep plugin loader V1 alive? **Yes**.
12. Does a plugin's static field that only self-references within an unreachable cycle necessarily pin the loader? **No**.
13. What is NMT `summary` used to observe? **JVM native memory categories**, not all native allocations from external libraries.
14. Is `ClassLoadingMXBean.getTotalLoadedClassCount()` the number currently loaded? **No**, it is cumulative since JVM startup.
15. What is the difference between `getLoadedClassCount()` and `getUnloadedClassCount()`? **Currently live vs. cumulative unloaded**.
16. Is one loader per tenant always better than shared classes when all tenants run the same code? **No**, it can unnecessarily multiply metadata and caches.
17. What can happen when using one loader for plugins A and B with different dependency versions? **Binary compatibility/class name conflicts**.
18. Why shouldn't `MaxMetaspaceSize` be increased before looking for a leak? **It only delays memory pressure if the retention path remains intact**.
19. Does JEP 387 allow a pinned loader to unload itself? **No**, strong roots must be released first.
20. Is ClassLoader sufficient to isolate untrusted plugins at the OS permission level? **No**.

## 15. Production Readiness Review Checklist

- [ ] Know the **count of defining class loaders and class definitions**, not just `ClassLoader` object counts.
- [ ] Categorize shared API, versioned dependency, and private implementation packages.
- [ ] Enforce a maximum limit on active plugins/tenants/generations based on capacity testing.
- [ ] Measure Metaspace **used/committed** and do not confuse reserved with RSS.
- [ ] Measure heap, thread stacks, code cache, and JAR handles alongside metadata.
- [ ] Load tests cover steady state, burst plugin startup, and V1/V2 overlap.
- [ ] Have a shutdown protocol for loader generations: quiesce, drain, unregister, close, release.
- [ ] Have a class identity test: `SharedApi.class == pluginVisibleSharedApiClass`.
- [ ] No TCCL/ThreadLocal/reflection caches retain V1 after retirement.
- [ ] Have a dashboard for classloader stats and class unload events per generation.
- [ ] Check JVM vendor/version/GC and the impact of NMT/diagnostic flags.
- [ ] On Metaspace OOM, check for loader retention before raising the memory limit.
- [ ] Do not use ClassLoader as a security sandbox for untrusted code.
- [ ] Document the trade-off of group loader vs. per-plugin loader vs. process isolation in architecture decisions.

## 16. References

1. [JVMS `5.3 — Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html#jvms-5.3): runtime class identity by binary name and defining loader.
2. [JLS `12.7 — Unloading of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html#jls-12.7): GC eligibility conditions prior to class unloading.
3. [ClassLoader — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ClassLoader.html): parent delegation, `loadClass`, `defineClass`, `findLoadedClass`.
4. [URLClassLoader — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/URLClassLoader.html): close and loader/resource lifecycle limits.
5. [JEP 387 — Elastic Metaspace](https://openjdk.org/jeps/387): improved chunk allocation and uncommitting memory when class metadata is freed.
6. [JEP 122 — Remove the Permanent Generation](https://openjdk.org/jeps/122): PermGen → Metaspace.
7. [ClassLoadingMXBean — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/ClassLoadingMXBean.html): currently loaded, total loaded, and total unloaded counts.
8. [MemoryPoolMXBean — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/MemoryPoolMXBean.html): measuring pool used/committed/max.
9. [The jcmd Command — JDK 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html): `VM.classloader_stats`, `VM.classloaders`, `VM.metaspace`, `VM.native_memory`.
10. [Native Memory Tracking — JDK 25 Troubleshooting](https://docs.oracle.com/en/java/javase/25/troubleshoot/diagnostic-tools.html): NMT categories, baseline/diff, and overhead.
11. [JEP 486 — Permanently Disable the Security Manager](https://openjdk.org/jeps/486): why ClassLoader does not replace a sandbox.
12. [ManagementFactory — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/ManagementFactory.html): querying class-loading and memory-pool MXBeans.

**Key takeaway:** Increasing the loader count does **not automatically** scale Metaspace by a fixed factor; the cost comes from **actual live runtime class definitions, allocator/metadata overhead, and retained resources**. Share compatible types through the parent to reduce duplication, use separate loaders only where version isolation or hot reload is genuinely needed, and measure **peak overlap, used/committed, classes loaded/unloaded, and strong roots** instead of guessing from loader count or reserved virtual memory.
