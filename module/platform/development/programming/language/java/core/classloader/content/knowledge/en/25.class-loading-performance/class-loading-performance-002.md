# Distinguishing Startup Latency from Post-Load Invocation Cost

## 1. Do not equate cold start with steady-state execution

In Java, **the first time a class is needed** and **a method call once the class is ready** are two different workloads. On first use, the JVM may need to locate class bytes, consult the parent classloader, create the runtime `Class<?>`, verify/link the class, execute the static initializer, and load additional dependencies. Afterward, calls to the same method typically do **not** repeat that entire class loading, definition, and initialization process.

Three questions must be distinguished:

1. **Startup latency:** from a defined starting milestone until the JVM/app/plugin meets its readiness condition.
2. **Cold/first-use latency:** when a feature is invoked for the first time, which may entail lazy loading, initialization, resource I/O, and provider discovery.
3. **Post-load cost (warm/steady-state invocation):** once the appropriate classes, objects, and resources are ready, how fast a method/request executes.

All three matter, yet **you should not measure one and label it as another**. A lazy application that starts up very quickly can make the first request slow; an application with a longer eager startup may ensure a more stable post-readiness p99.

**Key takeaway:** if the first call to `loader.loadClass("plugin.Action")` takes longer than `action.execute()` in a hot loop, that does not prove the ClassLoader "slows down every method call." The two measurements include different work.

## 2. Cost map from JVM creation to a hot request

~~~text
OS launches java process
          |
          v
JVM bootstrap + app/bootstrap code
          |
          v
Create classloader/module layer + locate JARs/resources
          |
          v
Loading: delegation, findClass, defineClass
          |
          v
Linking: verify, prepare, resolve when needed
          |
          v
Initialization: static fields/blocks (<clinit>)
          |
          v
SPI/ServiceLoader discovery + constructor + config I/O
          |
          v
FIRST SUCCESSFUL FEATURE RESPONSE
          |
          v
JIT profiling/compilation + caches warming
          |
          v
WARM REQUEST/INVOCATION (steady state)
~~~

This is an **analytical model**, not an absolute sequence for every application. The JVM may resolve symbolic references lazily; code may lazy-load plugins after readiness; the JIT may compile/recompile once the application is already receiving traffic. Measurement points must describe **the exact work being performed**.

| Component | Cold/first-use | Every hot method call? |
|---|---|---|
| JVM bootstrap | Usually occurs at process startup | No |
| Creating `URLClassLoader`/`ModuleLayer` | When creating a generation | No, if reused |
| Reading class bytes from JAR/URL | When the class needs to be defined | No, for a class already loaded in that loader |
| Parent delegation/class definition | When the class needs to be loaded | Does not repeat the full pipeline on every method call |
| Verification/linking | When the class/reference needs processing | Not a fixed cost per invocation |
| `<clinit>` | When the class initializes for the first time | Once successfully per runtime class |
| `ServiceLoader` provider discovery | Typically on first iteration | Not necessarily if cached/provider is reused |
| Reading/parsing config resources | First use/cache miss | Depends on caching strategy |
| JIT compilation/profiling | Warm-up and VM-dependent | Not equivalent to one compilation per call |
| Business logic/allocations/locks | Yes | Yes, depending on workload |
| Method dispatch | Yes | Yes, may be inlined/optimized |

**There is no constant "each class loading takes N ms"** that applies across every JDK, CPU, JAR, and classloader policy.

## 3. Defining the startup milestone precisely

`System.nanoTime()` on the first line of `main()` only shows the interval **after `main` has started**. It omits the preceding JVM launcher/bootstrap phase. Therefore, to measure true startup:

- For CLI: you can measure externally around the process from invoking `java` until output/exit.
- For an HTTP service: measure from process/container start to the **readiness endpoint that truly reflects required work**, and to the first response if required by the SLA.
- For a plugin runtime: measure from the activation request until the plugin is registered, dependencies are initialized, and a contract call succeeds.
- For a modular runtime: if creating a `ModuleLayer` or resolving modules during activation, include that in the workload if production also does so.

A `health=200` milestone returned **before** required plugins are ready should not be used to claim faster startup. You must compare against the same definition of "ready".

### First use does not necessarily coincide with startup

A rarely used feature might only be invoked for the first time after a week, and only then:

- Call `Class.forName` or `ServiceLoader`.
- Parse config.
- Load a JNI library.
- Open a network connection.
- Trigger a cold (unwarmed) JIT code path.

The latency of that request is the **feature cold path**, not JVM process startup. Separate spans should be logged to see the exact cause.

## 4. ClassLoader.loadClass on first call and subsequent calls

In the default implementation, a ClassLoader does roughly the following:

~~~text
loadClass(name)
     |
     v
getClassLoadingLock(name)
     |
     v
findLoadedClass(name)
     |
     +-- Yes -> return existing Class<?>
     |
     +-- No -> parent/bootstrap delegation
                       |
                       +-- found -> return parent's Class
                       |
                       +-- not found -> findClass(name)
                                          |
                                          v
                                    defineClass(bytes)
                                          |
                                          v
                                     Class<?>
~~~

If the class was previously loaded successfully, calling it again with the same name through the same loader can return **the same runtime `Class<?>`**.

~~~java
Class<?> first = loader.loadClass("plugin.Action");
Class<?> second = loader.loadClass("plugin.Action");
System.out.println(first == second);
~~~

This is an **illustrative snippet**, requiring a valid `loader` variable and an existing class; under the class loading contract for that case, the result is `true`.

**Do not infer** that repeated `loadClass` calls cost zero CPU: there are still method calls, checks, and synchronization depending on the implementation. However, it **does not mean re-reading the JAR or defining a new class**. If the plugin object already exists, business code should call it through that shared interface/object instead of using `Class.forName` by string on every request without reason.

### A new loader generation changes the meaning of a benchmark

~~~text
Generation A: ("plugin.Action", LoaderA)
Generation B: ("plugin.Action", LoaderB)
~~~

These are two distinct runtime classes even when the bytecode/binary name is identical. If each benchmark iteration creates a new loader, the measurement includes **class loading/linking/initialization and generation lifecycle**, not just invocation.

## 5. Loading, linking, initialization, and method invocation differ

The calls below **measure different scopes**; giving them the same name "class loading cost" will distort the meaning of the results:

~~~java
Class<?> a = loader.loadClass("plugin.Action");
Class<?> b = Class.forName("plugin.Action", false, loader);
Class<?> c = Class.forName("plugin.Action", true, loader);
~~~

- `loadClass` requests finding/loading the class via delegation, **without actively initializing** the class.
- `Class.forName(..., false, ...)` may load/link, but **does not require running `<clinit>`**.
- `Class.forName(..., true, ...)` requests initialization if the class is not yet initialized; the measurement may include the static initializer and side effects.
- `action.execute()` on a ready instance measures business invocation, which may experience JIT/GC/I/O, but does not redefine that runtime class on every call.

A successful static initializer runs only once per **runtime class**. A different loader generation that defines the same binary name itself has its own class and initialization. Symbolic references may also be resolved when a method uses them, so a successful `loadClass` **does not guarantee that all lazy dependencies are ready**.

For example, if startup has a slow static config reader, place timers to separate `<clinit>` and the first request rather than attributing the entire delay to JAR/verification. If static initialization involves network I/O that is hard to retry, use a controlled startup lifecycle rather than calling `Class.forName` repeatedly as a retry mechanism.

## 6. Runnable Java 17+ example: initialize once, invoke method many times

### File `StartupVsSteadyState.java`

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public final class StartupVsSteadyState {
    private static final AtomicInteger INIT_EVENTS =
            new AtomicInteger();

    public static final class Worker {
        static {
            INIT_EVENTS.incrementAndGet();
        }

        public static long calculate(int value) {
            return 31L * value + 7;
        }
    }

    public static void main(String[] args) throws Exception {
        ClassLoader loader =
                StartupVsSteadyState.class.getClassLoader();

        // A class literal does not require initializing Worker.
        String name = Worker.class.getName();

        long t0 = System.nanoTime();
        Class<?> type = Class.forName(name, false, loader);
        long t1 = System.nanoTime();

        System.out.println("after load(false): "
                + INIT_EVENTS.get());

        long t2 = System.nanoTime();
        Class.forName(name, true, loader);
        long t3 = System.nanoTime();

        System.out.println("after initialize: "
                + INIT_EVENTS.get());

        long checksum = 0;
        int iterations = 100_000;
        long t4 = System.nanoTime();

        for (int i = 0; i < iterations; i++) {
            checksum += Worker.calculate(i);
        }

        long t5 = System.nanoTime();

        System.out.println("after calls: "
                + INIT_EVENTS.get());
        System.out.println("same Class: "
                + (type == Worker.class));
        System.out.println("checksum positive: "
                + (checksum > 0));
        System.out.println("load_ns=" + (t1 - t0));
        System.out.println("init_ns=" + (t3 - t2));
        System.out.println("calls_ns=" + (t5 - t4));
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac StartupVsSteadyState.java
java StartupVsSteadyState
~~~

**The first five lines have deterministic logical output:**

~~~text
after load(false): 0
after initialize: 1
after calls: 1
same Class: true
checksum positive: true
~~~

**The last three lines have the following format, though the numbers are for illustration only:**

~~~text
load_ns=123456
init_ns=45678
calls_ns=789012
~~~

There is no fixed `ns` value across every JDK/CPU/rerun.

### Explanation

1. `Worker.class.getName()` retrieves the binary name without itself requiring Worker to be initialized.
2. `Class.forName(name,false,loader)` does not trigger the initializer; `INIT_EVENTS` remains 0.
3. `Class.forName(name,true,loader)` runs the static block for the first time; counter = 1.
4. After 100,000 calls to `calculate`, the static block does **not** run again; counter remains 1.
5. `type == Worker.class` is `true` due to having the same classloader identity, without creating a new generation.
6. The `load_ns`/`init_ns`/`calls_ns` intervals have **different** measurement scopes and are also affected by noise/JIT effects.

### Why is `calls_ns / 100000` not p99 latency?

- There is only a single aggregate measurement; a percentile requires a distribution of many samples.
- The JVM may compile/inline the method within the loop.
- The loop may be optimized/reduced in cost due to predictable expressions.
- The clock and compiler/scheduler/GC have an impact.
- A tiny arithmetic call is far removed from a request involving I/O, allocations, and concurrency.
- Using `checksum` ensures the result is observed, but does not guarantee eliminating all dead-code elimination/loop transformations.

This program demonstrates the **lifecycle**; it does not replace a professional benchmarking tool.

## 7. Java 17+ example: two loader generations and two runtime classes

A separate test shows why a benchmark that repeatedly creates a new classloader measures a different workload.

### File `src/plugin/demo/PluginAction.java`

~~~java
package demo;

public final class PluginAction {
    static {
        System.out.println("plugin initialized");
    }

    public String call() {
        return "ok";
    }
}
~~~

### File `src/host/LoaderGenerations.java`

~~~java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class LoaderGenerations {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: LoaderGenerations <plugin-dir>");
        }

        URL root = Path.of(args[0]).toAbsolutePath()
                .toUri().toURL();

        try (URLClassLoader loaderA = new URLClassLoader(
                    new URL[]{root},
                    ClassLoader.getPlatformClassLoader());
             URLClassLoader loaderB = new URLClassLoader(
                    new URL[]{root},
                    ClassLoader.getPlatformClassLoader())) {

            String name = "demo.PluginAction";
            Class<?> first = loaderA.loadClass(name);
            Class<?> same = loaderA.loadClass(name);
            Class<?> second = loaderB.loadClass(name);

            System.out.println("repeat in A: " + (first == same));
            System.out.println("same binary name: "
                    + first.getName().equals(second.getName()));
            System.out.println("same runtime type: "
                    + (first == second));

            Object a = first.getConstructor().newInstance();
            Object b = second.getConstructor().newInstance();

            System.out.println("A call: "
                    + first.getMethod("call").invoke(a));
            System.out.println("B call: "
                    + second.getMethod("call").invoke(b));
        }
    }
}
~~~

Bash commands from the project directory:

~~~bash
mkdir -p out/plugin out/host
javac -d out/plugin src/plugin/demo/PluginAction.java
javac -d out/host src/host/LoaderGenerations.java
java -cp out/host LoaderGenerations out/plugin
~~~

**Do not place `out/plugin` on the application classpath.** Stdout when using the fixture above:

~~~text
repeat in A: true
same binary name: true
same runtime type: false
plugin initialized
plugin initialized
A call: ok
B call: ok
~~~

Explanation: `loaderA` defines the class the first time and returns that exact same runtime `Class<?>` on the subsequent call; `loaderB` defines a **different** class with the same binary name. Each class is initialized when its instance is created; therefore, the initializer prints twice. This is the cost of **two loader generations**, not of two method calls on the same instance.

## 8. Designing measurements to match the question

| Question | Measurement point | Result definition |
|---|---|---|
| JVM/app cold start? | Outside the process: launch → readiness | Milliseconds, distribution across multiple fresh processes |
| Plugin activation? | Activation requested → plugin usable | Includes loader, classes, providers, resources, and required init |
| Class loading alone? | Before/after explicit `loadClass` on a cold loader | Only the work of that API; subsequent steps may be lazy |
| Static initialization? | Before/after first `Class.forName(...,true,loader)` | Includes initializer side effects |
| Provider discovery? | Before iterator → provider ready | Includes lazy ServiceLoader work |
| Warm method invocation? | Stable receiver/object, repeated method calls with JMH | ns/op or ops/s, statistical analysis |
| Real request p99? | End-to-end HTTP/RPC | Histogram by concurrency and workload |
| Hot redeploy? | Stop old generation → new generation ready | Teardown, memory pressure, loader activation |

Do not place `new URLClassLoader` inside the measurement loop if the goal is only to call an existing object. Conversely, if the real application must create a loader on every request, **include that cost in the benchmark** and name it accurately.

## 9. Measuring cold startup from outside the JVM

To measure **process startup**, the phase before `main` must be included, so an external harness or appropriate instrumentation is needed:

~~~text
Harness:
  start monotonic timer
  launch java process
  wait for readiness marker / successful endpoint
  record elapsed time
  terminate process safely
  repeat in fresh process
~~~

A shell command like `time java MyMain` measures how long the process runs until completion (suitable for small CLIs); it **is not automatically** the time until a server becomes ready if the server keeps running indefinitely. For an HTTP server, an explicit readiness signal and an external timer are required.

You should hold constant:

- The same JDK/build/VM flags.
- The same artifact and module/classpath/JAR graph.
- The same CPU/quota, memory, OS, and container limits.
- The same required/optional plugins.
- The same network/DNS/DB conditions and secrets.
- Distinguish between a warm and cold OS page cache.
- Multiple fresh processes, rather than using only the noisy first run.
- Report the median, and p95/p99 if the sample count is sufficient; do not pick the fastest run.

If variant A reports ready before a critical provider is initialized, while variant B waits until the provider is usable, the two measurements **do not share the same definition** and should not be compared as equivalent.

## 10. JMH for steady-state method benchmarks

**Java Microbenchmark Harness (JMH)** supports JVM benchmarking with forks, warm-up, measurement iterations, state, result consumption, and statistical reporting.

This JMH snippet **requires the JMH dependency and a separate class**, not plain JDK alone:

~~~java
import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.State;

@State(Scope.Thread)
public class InvokeBenchmark {
    private final BusinessService service = new BusinessService();

    @Benchmark
    public long invoke() {
        return service.compute(42);
    }
}
~~~

`BusinessService` is an illustrative application type; you must supply its implementation and configure the JMH project yourself. The key point is that **the service is prepared outside the benchmark method**, without creating a new loader/plugin object on each invocation.

An appropriate JMH workflow:

1. Run warm-up iterations before collecting numbers.
2. Fork the process when needed to avoid class/JIT state being affected by other benchmarks.
3. Prepare the receiver/provider using `@State` or an appropriate setup lifecycle.
4. Consume the result to reduce the risk of dead-code elimination.
5. Control benchmark parameters/datasets so the compiler does not merely measure a constant-folded expression.
6. Run multiple iterations/samples; record confidence/error bounds.
7. Distinguish between throughput and average time; a microbenchmark does not automatically give production request p99.
8. Do not compare operation A that includes reflection lookup against B that includes only direct invocation and claim "invocation is X slower" when their scopes differ.

**JMH does not replace load testing:** network, thread pools, GC, DB, queues, and real-request p99 still need to be measured with tools suited for production workloads.

## 11. Reflection, MethodHandle, and direct interface calls

Plugin frameworks sometimes look up a method via reflection:

~~~java
java.lang.reflect.Method method =
        type.getMethod("execute");
Object result = method.invoke(instance);
~~~

This is an illustrative snippet when `type`/`instance` already exist. There are two distinct parts:

- **Lookup:** `getMethod(...)`, access validation.
- **Invocation:** `method.invoke(...)`.

If one variant places `getMethod` in every iteration while another variant calls `sharedInterface.execute()` directly, you are measuring lookup plus invoke against invoke alone. For a fair comparison, cache the appropriate `Method`/`MethodHandle` in setup, or measure lookup separately.

An architecture with a shared API in the parent typically allows the host to hold a provider instance:

~~~java
MyService service = factory.create();
service.execute();
~~~

The snippet above only illustrates the pattern; in a real project, `MyService`/`factory` must be declared. The caller then does not need to look up the class again by binary name on every request.

Dynamic dispatch performance depends on the JIT, inline caches, polymorphism, interface implementations, and workload; **there is no constant classloader overhead applied to every call**.

## 12. JIT warm-up differs from static class initialization

**Initialization** runs `<clinit>` once per runtime class if successful. By contrast, **the JIT** operates as the JVM evaluates hot execution paths and may compile/recompile after multiple invocations.

~~~text
Class loaded & initialized
          |
Call 1: cold code/data caches
          |
Call N: profiling, tiered compilation
          |
Call later: optimized/inlined code possible
          |
Deoptimization/recompile possible if profile changes
~~~

The diagram does not claim there must be an exact number N of calls or that every JVM mode always JIT-compiles. Under `-Xint`, the execution model differs from default HotSpot tiered compilation.

**Consequence:** running `Class.forName(name,true,loader)` early may help avoid static initialization on the first request, but it **does not guarantee that the JIT and business data caches are already warm**. If the SLA requires a fast first request, critical request paths need controlled warm-up.

## 13. ServiceLoader and resource I/O are separate cold work

### ServiceLoader lazy discovery

~~~java
ServiceLoader<MyService> services =
        ServiceLoader.load(MyService.class, pluginLoader);
~~~

This is an illustrative snippet, requiring `MyService`/`pluginLoader` to exist.

`ServiceLoader.load` creates a ServiceLoader, while much of the metadata/provider lookup and instantiation happens **when iterating/streaming**. Therefore, measuring `ServiceLoader.load(...)` without traversing providers may **fail to measure full activation**.

Set milestones:

~~~text
create ServiceLoader
   |
iterate descriptors / module provider metadata
   |
load implementation class
   |
check runtime SPI assignability
   |
instantiate provider
   |
invoke provider startup method
~~~

Adding or removing descriptors in `META-INF/services`, changing the TCCL/explicit loader, or altering a named module setup can change the actual work performed. Benchmarks must share the same artifact/provider behavior, not just a matching API call name.

### Resource lookup differs from reading/parsing

~~~java
URL location = pluginLoader.getResource("config/settings.properties");
~~~

`getResource` only locates the URL (or `null`); it is not equivalent to reading all bytes, parsing, and validating. If the code proceeds to call `openStream()` and parse Properties, that is a separate I/O/CPU phase that may be cached or affected by the page cache.

Do not use a resource URL that "looks right" to conclude that the plugin's own data was used; parent-first delegation can shadow a file of the same name in the child.

## 14. Observing class loading with ClassLoadingMXBean

JDK 17 provides `ClassLoadingMXBean`:

~~~java
import java.lang.management.ClassLoadingMXBean;
import java.lang.management.ManagementFactory;

ClassLoadingMXBean bean =
        ManagementFactory.getClassLoadingMXBean();

long total = bean.getTotalLoadedClassCount();
int current = bean.getLoadedClassCount();
long unloaded = bean.getUnloadedClassCount();
~~~

This is an illustrative Java snippet.

- `total` is a **cumulative counter** of the number of classes loaded since the JVM started.
- `current` is a **gauge** of the number of classes currently loaded.
- `unloaded` is a **cumulative counter** of unloaded classes.

They help show whether startup or activation caused the JVM to load additional classes, but they **do not measure per-class latency**. An increase in `total` does not by itself prove a classloader leak or slow method calls; you need to examine the trend, metaspace, loading logs/JFR, and retained classloader references.

When computing deltas, take samples within **the same JVM**; every process restart resets the counters. Also record the JVM process start time and timestamps so a negative delta across two JVMs is not misread as "unloaded".

## 15. JVM logs, JFR, and tracing

On HotSpot JDK 17, enable class load/unload logs:

~~~bash
java -Xlog:class+load=info,class+unload=info \
    StartupVsSteadyState
~~~

This diagnostic command produces extra logs, so stdout is **no longer** as concise as in the demo; tags/formats may vary depending on the JVM. Classloading logs show events/sources, but do not automatically provide p95/p99 business latency.

**Java Flight Recorder (JFR)** can help inspect execution samples, allocations, GC, class loading, and other events depending on the JDK configuration. When analyzing cold start:

- Start the recording early enough to include startup/cold features.
- Record the timeline of plugin loader creation, class definition, first provider readiness, and first request response.
- Compare JIT/GC/I/O/locks alongside classloading activity.
- Do not assume every JFR event is enabled by default, or includes full stack traces/durations.
- Compare multiple runs and ensure the JDK/flags are identical.

Application spans are also useful:

~~~text
process-started
required-services-ready
plugin-loader-created
plugin-class-found
plugin-initialized
provider-ready
first-successful-result
warm-request-completed
~~~

To compute elapsed durations within a process, use a monotonic clock, combined with a wall clock when correlating distributed traces. Do not sum two parallel spans and treat the result as the total.

## 16. Class unloading and metaspace in lifecycle benchmarks

A system performing continuous hot redeploys has:

~~~text
Generation A -> Loader A -> Class A
Generation B -> Loader B -> Class B
Generation C -> Loader C -> Class C
~~~

Each generation has its own runtime class objects; if the host caches `Class<?>`, plugin objects, TCCLs, threads, callbacks, or JNI globals from an old generation, memory usage and class counts may grow.

`URLClassLoader.close()` closes the JAR/file handles of the URL loader; it **does not force the JVM to unload classes immediately**. `System.gc()` also does not guarantee immediate class unloading.

If the actual workload repeatedly creates/retires loaders, you must also measure:

- Load/activation time per generation.
- Total/current/unloaded classes over intervals.
- Metaspace usage, heap, and GC pauses.
- Time to close streams/JAR handles.
- Strong-reference retention and classloader leaks.
- Tail latency of in-flight requests during redeployment.

Do not use a benchmark of a single loader on a fresh JVM to claim that an application redeploying 100 times will not increase memory usage.

## 17. Eager, lazy, and warm-up strategies based on SLA

| Strategy | Benefits | Trade-offs |
|---|---|---|
| Eager loading/init before readiness | Errors surface early, faster first request if sufficiently prepared | Longer startup, larger footprint |
| Lazy init when feature is called | Fast readiness, avoids loading rarely used features | Slow cold request, errors appear late |
| Targeted warm-up | Focuses on critical paths | Must choose the right paths and measure real effect |
| Reuse loader/provider | Reduces repeated activation work | Requires lifecycle/cache consistency |
| New loader per generation | Supports plugin version isolation | Higher load/GC/metaspace cost |
| Separate process for plugin | Stronger isolation | IPC/process startup overhead |

A design can define readiness as:

~~~text
BOOTING -> REQUIRED_PLUGINS_READY ->
WARM_CRITICAL_PATHS -> SERVING
~~~

Optional features may be lazy, but their first-use SLA and fallback policy must be clearly documented. Simply shifting heavy work from startup to the first request without measuring p99 is **insufficient evidence** of overall improvement.

## 18. Common benchmark pitfalls

| Misconception | Why it is wrong | Alternative |
|---|---|---|
| First invocation is slow, so all Java method calls are slow | Conflates loading/init/JIT | Separate cold and warm |
| `Class.forName(..., true)` warms up the JIT | Initialization differs from JIT | Warm up the actual code paths |
| `loadClass` reads the JAR on every call | Usually returns the already-loaded class | Check `findLoadedClass` and timing |
| Creating a new loader every iteration is an invocation benchmark | Measures generation instead | Reuse loader/receiver |
| Mean from a single loop is p99 | Mean differs from distribution percentiles | Histograms, multiple samples |
| A single `nanoTime` measurement is a valid benchmark | Noise/JIT/GC/scheduler | JMH + repeats/forks |
| Timing from `main` is full process startup | Omits JVM bootstrap | External harness |
| `ServiceLoader.load` measures all provider costs | Discovery is lazy | Iterate/instantiate |
| `getResource` has already read the config | Only looks up the URL | Measure open/read/parse |
| Comparing reflection lookup+invoke with direct invoke is fair | Extra work in the reflection case | Separate lookup from invocation |
| Increasing total loaded classes definitely means a leak | A cumulative counter naturally increases | Current/metaspace/retention trend |
| GC not unloading immediately means a leak | Non-deterministic | Observe lifecycle/reference graph |
| "Runs fast" even when the provider fails still meets the SLA | Correctness is not guaranteed | Verify successful feature behavior |

## 19. Checklist before drawing conclusions

- [ ] Clearly define the startup/activation/first-use/steady-state metric.
- [ ] Measure startup **from outside the process** if the goal includes JVM bootstrap.
- [ ] Use the same JDK, flags, hardware, and artifact when comparing.
- [ ] Use the same classpath/module path and loader policy.
- [ ] Use a fresh JVM for cold-start samples.
- [ ] Do not create a ClassLoader on every iteration of a benchmark for an already-loaded method.
- [ ] Distinguish `loadClass` from `Class.forName(..., true)`.
- [ ] Verify that the static initializer runs only per runtime class identity.
- [ ] Measure ServiceLoader provider iteration, not just creating the loader object.
- [ ] Measure resource lookup separately from reading/parsing.
- [ ] Include warm-up and multiple forks when measuring tiny methods with JMH.
- [ ] Consume results to prevent dead-code elimination.
- [ ] Report distribution/tail latency for real requests.
- [ ] Monitor JIT/GC/class count/metaspace when needed.
- [ ] Verify that startup/readiness actually serves the expected functionality.
- [ ] Control TCCL/caches/streams and loader lifecycle during redeployment.
- [ ] Do not generalize a single benchmark configuration to all JVMs.

## 20. Self-check exercises

**Question 1.** Does calling `ClassLoader.loadClass` again with the same name on the same loader always define a new class?

**Answer:** No. A standard ClassLoader returns the already-loaded runtime class; it does not invoke `defineClass` a second time for the same binary name within one loader.

**Question 2.** How does `Class.forName(name, false, loader)` differ from `true`?

**Answer:** `false` does not require initialization, whereas `true` requires initializing an uninitialized class; static initializer cost may appear on the first call.

**Question 3.** Does measuring the time from the start of `main` until readiness capture the full JVM process startup?

**Answer:** No, it omits the JVM launcher/bootstrap time prior to `main`.

**Question 4.** Why can two URLClassLoaders defining the same `plugin.Action` cause the initializer to run twice?

**Answer:** Because they are two distinct runtime classes with different defining loaders; each class has its own initialization lifecycle.

**Question 5.** Does a JMH measurement of 100,000 warmed method invocations reflect HTTP request p99?

**Answer:** No. Real requests also involve networking, queues, concurrency, allocations, I/O, and GC.

**Question 6.** Does `ServiceLoader.load(SPI.class)` completing quickly prove that providers are instantiated?

**Answer:** No, provider discovery/instantiation can be lazy upon iteration.

**Question 7.** If you move config reading from startup to the first request, startup may become faster. Is the overall experience guaranteed to be better?

**Answer:** No; first-use latency may increase. Both the readiness milestone and p99 of first requests need to be measured.

**Question 8.** Why is `getTotalLoadedClassCount()` not the byte size of metaspace?

**Answer:** It is the count of runtime classes ever loaded in the JVM, not memory usage; the footprint per class is not fixed.

**Question 9.** When benchmarking classloader hot redeploy, is it necessary to consider GC/memory?

**Answer:** Yes. Different generations create new runtime types; retention/GC/metaspace can affect latency and throughput.

**Question 10.** If a tiny method runs fast in a loop after warm-up, is dynamic dispatch guaranteed to be equally fast in production?

**Answer:** No. The JIT may inline or constant-fold it, whereas production has multiple implementations, concurrency, and a different workload.

## 21. Decision tree

~~~text
Slow Java/plugin observed
              |
              v
Which milestone?
 /             |              \
Startup     First use      Warm calls
   |            |               |
external    load/init,     JMH / real
harness     providers,     request traces
   |        config I/O          |
   |            |               |
   +------------+---------------+
                |
  Identify the real bottleneck
                |
Eager/lazy/warm-up/reuse loaders
                |
Re-measure same JVM/artifact/workload
                |
   Correctness + tail latency
                |
   Check memory/GC/lifecycle
~~~

**Conclusion:** **Startup**, **first use**, **warm-up**, and **steady-state invocation** are distinct phases. `ClassLoader` creates runtime type identities; it does not rerun the entire load/define/init pipeline every time a loaded method is called. To optimize performance accurately, separate measurement milestones, account for lazy linking/provider/resource work, JIT, and GC, choose the right tools (external startup harness, JMH, JFR, ClassLoadingMXBean, load testing), and verify results on real workloads and artifacts.

### References

- [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html)
- [Java SE 17 — Class.forName](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html)
- [JVMS 17 — Loading, Linking and Initializing](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html)
- [Java SE 17 — ClassLoadingMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ClassLoadingMXBean.html)
- [Java SE 17 — ServiceLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html)
- [OpenJDK — Java Microbenchmark Harness](https://openjdk.org/projects/code-tools/jmh/)
- [Java 17 launcher / Unified JVM Logging](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html)
