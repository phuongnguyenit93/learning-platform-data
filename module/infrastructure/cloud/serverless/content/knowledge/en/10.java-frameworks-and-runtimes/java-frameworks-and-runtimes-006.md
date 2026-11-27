# Comparing JVM and Native Executables for Real-World Workloads

Serverless Java applications can be run in two common ways. The first packages the application as a JAR and runs it on the JVM. The second compiles the application ahead of time into a native executable, usually with GraalVM Native Image, and runs the binary directly on the target operating system.

Both approaches can execute the same Java logic, but they have different characteristics in startup time, memory usage, steady-state throughput, packaging, and library compatibility. Neither choice is universally faster or cheaper. The right decision depends on the workload: whether functions are short- or long-lived, whether cold starts happen frequently, whether traffic is steady or bursty, and which Java features the application uses.

## 1. The Two Execution Models

### 1.1. Running a JAR on the JVM

In the JVM model, the application is compiled to Java bytecode. When deployed, a Java runtime starts a process, loads classes, initializes the framework, and executes bytecode.

The JVM can use an interpreter to start running quickly, after which the JIT compiler compiles frequently invoked code into machine code. The JVM profiles the live workload to optimize hot paths, inline methods, and apply optimizations based on observed behavior. When an application runs long enough, these optimizations can significantly improve throughput.

An important advantage of this model is broad compatibility with the Java ecosystem: reflection, dynamic class loading, proxies, JNI, instrumentation, libraries, and monitoring tools generally behave as traditional Java applications expect.

In return, a new process must initialize the JVM, load classes, and initialize the framework. JIT also needs time to gather profiles and optimize code. For functions that run for a few hundred milliseconds and finish, many JIT optimizations may never have a chance to take effect.

### 1.2. Native Executables with AOT Compilation

Native Image compiles the Java application ahead of time (AOT) before deployment into an executable targeting a specific OS and architecture. At runtime, the binary does not need a standalone JVM to load bytecode and perform traditional JIT compilation.

A native executable still includes a runtime for the Java features it supports, such as object management, garbage collection, exceptions, and threads. Therefore, a native executable should not be mistaken for bare machine code with no runtime. The difference is that most reachability analysis and compilation happen at build time.

Native Image typically performs reachability analysis starting from known entry points to determine which classes, methods, and resources must be included in the binary. This model is commonly called a closed-world assumption: elements discovered only dynamically at runtime may not automatically be included in the executable. Reflection, JNI, resource loading, proxies, and service loading may require metadata or additional configuration.

The result typically has fast startup times and avoids traditional JIT warm-up phases. However, native builds can take longer, consume more CI resources, and require explicit handling of dynamic application features.

## 2. High-Level Comparison

| Criterion | JAR running on JVM | Native executable |
|---|---|---|
| Process startup | Usually requires initializing JVM, loading classes, and framework | Usually faster due to ahead-of-time compilation and an app-tailored runtime |
| JIT warm-up | Yes; hot code is optimized at runtime | No traditional JIT profiling in standard Native Image |
| Post-warm-up throughput | Usually strong for long, steady workloads thanks to JIT | May be lower or comparable; depends on code, workload, and config |
| Memory | Includes heap, metaspace, thread stacks, JIT, and native memory | Includes heap and native runtime; often cuts some overhead but does not guarantee less RAM |
| Deployment size | JAR plus Java runtime or runtime layer | Binary can be large; no separate JVM install needed when runtime is bundled appropriately |
| Build | Usually fast and simple | Can be slow, CPU/RAM-heavy, and requires a native toolchain |
| Reflection and dynamic class loading | Broadly supported | Requires metadata and config for dynamic access paths |
| Debugging and profiling | Rich, familiar JVM tooling ecosystem | Tooling and observability depend on native runtime, build, and platform |
| Portability | Bytecode runs across compatible JVMs | Binary is tied to the OS, CPU architecture, and ABI of the build environment |
| Notable fit | Long workloads, high throughput, rich Java libraries | Short functions, critical cold starts, bursty or scale-to-zero workloads |

The observations in the table reflect common trends, not performance guarantees. A native executable can be slower than the JVM on a given workload, and the JVM can start fast enough for real-world requirements once frameworks, runtimes, and deployment setups are optimized.

## 3. Startup and Cold Starts

Cold starts occur when the platform must create a new execution environment before handling an invocation. For Java, total cold-start time can include:

- Container or sandbox initialization.
- Process and runtime startup.
- Class and library loading.
- Framework, dependency injection, and configuration initialization.
- Client, connection pool, or cache creation.
- Executing the first invocation's logic.

Native executables typically shorten runtime initialization and class loading. This can be beneficial when functions scale from zero to many instances, or when each instance handles only a few requests before being reclaimed.

However, native compilation does not eliminate every part of a cold start. Container startup, file mounts, secret reads, DNS, TLS handshakes, database connections, and application initialization logic still take time. A native application that boots very fast yet spends several hundred milliseconds connecting to external services still exhibits a noticeable cold start.

Measure the time until the function is truly ready to serve requests (ready-to-serve), not merely the time from process start until the first log line is printed.

### 3.1. The JVM Also Has Ways to Reduce Cold Starts

Before switching to native, review platform-appropriate JVM optimizations:

- Reduce the number of libraries and classes loaded at startup.
- Avoid initializing unnecessary clients or caches in static initializers.
- Use lazy initialization for components needed only on certain routes.
- Optimize framework startup and dependency injection configuration.
- Use Class Data Sharing (CDS) or suitable class archiving mechanisms if supported by the runtime.
- Use platform snapshot/restore or CRaC mechanisms when supported and when state can be checkpointed safely.
- Keep execution environments warm if cost and traffic patterns permit.

Snapshot or restore mechanisms carry their own caveats: open sockets, credentials, system clocks, and external state may need refreshing after restore. Do not assume every application is safe to process-snapshot.

### 3.2. Latency Must Be Measured by Percentiles

Some functions experience rare but very slow cold starts. Looking only at averages can hide the issue. Measure:

- p50: typical experience.
- p95: latency of the slower tail of requests.
- p99: extreme tail of the distribution, critical for strict SLAs.
- Cold-start duration separately.
- Ready-to-serve duration.
- Duration of the first invocation vs. warm invocations.

If p95 or p99 is dominated by database connections, DNS, or external dependencies, switching to native may not address the actual bottleneck.

## 4. Throughput and Post-Warm-Up Performance

JVM JIT excels when a process runs for a long time and executes the same code paths repeatedly. After profiling, the JVM can optimize hot methods, object allocations, and branch predictions based on observed runtime behavior.

Native Image performs optimizations primarily at build time. It can use profile-guided optimization (PGO) to leverage profiles collected from a representative workload during the build, but that is not the same as the JVM continuously profiling and JIT-optimizing inside each live execution environment.

For sustained CPU-bound workloads, a warmed-up JVM is often a strong choice. For short-lived functions, waiting for JIT warm-up may not pay off because invocations finish before optimizations take effect. Native may hold an advantage in that case.

Some workloads are not bound by the Java runtime:

- Calling external APIs and waiting on the network.
- Reading/writing object storage.
- Waiting on databases or message brokers.
- Waiting on users or callbacks.

For I/O-bound workloads, the difference between JVM and native can be small compared to dependency wait times. Measure total processing time and dependency latency before deciding.

## 5. Memory and Scaling

RAM usage affects how many instances can run concurrently, CPU allocation on some platforms, and function cost. Native executables often cut overhead related to JVM internals and class metadata, but total RSS still depends on heap, native allocations, threads, TLS, buffers, and libraries.

Distinguish among:

- **Java heap:** objects allocated by the application.
- **Metaspace/class metadata:** class metadata inside the JVM.
- **JIT code cache:** machine code generated by JIT in the JVM.
- **Thread stacks:** stack space for each thread.
- **Native memory:** direct buffers, TLS, native libraries, and runtime structures.
- **RSS:** physical memory of the process reported by the operating system.

Native Image does not have a traditional JVM metaspace or JIT code cache, but it still uses heap, stacks, and native memory. A native executable can still exhibit high RSS if the application retains many objects or uses large native libraries.

Do not compare only max heap settings. Measure peak RSS and memory usage under large payloads, high concurrency, and realistic workloads. Also track GC pause times, allocation rates, and out-of-memory invocation terminations.

### 5.1. Scale-Out and Concurrency

When the platform scales out instances, each instance consumes a slice of RAM and opens some number of database connections. A native executable using less RAM in certain workloads may allow higher instance density, but that does not automatically mean the database can handle more connections.

Cap connection pools and system-wide concurrency. If each function instance opens 10 connections and the platform scales to 100 instances, the database can receive up to 1,000 connections. Switching to native does not solve that limit.

## 6. Java and Framework Compatibility

This is one of the most consequential differences when choosing native executables.

The JVM broadly supports features built on classpath and runtime discovery. Native Image needs to know in advance which elements can be used. Scenarios needing attention:

- Reflection to instantiate objects or invoke methods by name.
- Reflection-based JSON/XML serialization.
- Classpath scanning and plugin discovery.
- Dynamic proxies and framework-generated proxies.
- Reading resources from the classpath.
- JNI and native libraries.
- `ServiceLoader` and dynamically discovered providers.
- Instrumentation, agents, and bytecode enhancement tools.
- Class loading from modules or JARs loaded after the process starts.

Several frameworks provide build-time augmentation, AOT processing, and metadata to support Native Image. Quarkus and Micronaut are designed with many build-time optimizations; Spring Boot also supports AOT and native images via compatible versions and plugins. Exact support depends on framework versions, extensions, and libraries in use.

Do not conclude that "the framework supports native" means every library in your application is compatible. An extension may work on the JVM while lacking metadata or native-mode support for a specific feature.

### 6.1. Reflection and Reachability Metadata

For example, an application instantiates an object by class name:

~~~java
Class<?> type = Class.forName(configuredClassName);
Object handler = type.getDeclaredConstructor().newInstance();
~~~

On the JVM, the class can be found on the classpath if a JAR contains it. With Native Image, the class and constructor invoked via reflection must be identified during build analysis or declared via appropriate metadata. Otherwise, the runtime may report the class or member unavailable even though the code compiled cleanly.

How to handle this:

1. Prefer APIs and framework integrations with built-in native support.
2. Use build-time registration or annotations provided by the framework.
3. Declare reflection/resource/JNI metadata in the format supported by Native Image.
4. Use the tracing agent under test workloads to capture part of the dynamic access config.
5. Test the native executable against realistic business flows, including rare branches.

The tracing agent only records code paths executed during collection. It cannot infer every branch that could occur in production. Metadata generated from tests must be reviewed and verified further.

### 6.2. Build-Time Initialization vs. Runtime Initialization

Native Image can initialize certain classes at build time to reduce runtime work. This helps with immutable data, but is dangerous if static initializers read the current time, environment variables, secrets, random seeds, environment-specific config files, or open connections.

Values computed at build time can get baked into the binary and reused across every environment. For example, never bake production credentials into an image or compute a deployment-environment-dependent value during the build.

Clearly identify which classes can be initialized safely at build time and which must wait until runtime. Do not force every class to build-time initialization solely to improve startup.

## 7. Packaging, Deployment, and Operations

JARs generally offer higher portability: the same bytecode can run across multiple operating systems and architectures with a compatible JVM. A native executable is built for a specific target, typically tied to:

- Operating system and system library versions.
- CPU architecture such as x86_64 or ARM64.
- ABI and libc implementation (for example, glibc or musl).
- Linked native libraries.
- Toolchain and Native Image builder versions.

A binary compiled on a developer machine may fail to run in the platform's Linux runtime if architecture or ABI mismatches. Build in an environment compatible with the deployment target, use an appropriate container/build image, and test the binary in a production-like environment.

Native builds can consume significantly more CPU, RAM, and time. CI should cache dependencies and toolchains when safe, while rebuilding the binary whenever source code, metadata, frameworks, JDK, or native configurations change. Preserve build provenance and compiler versions for reproducibility.

### 7.1. Execution Examples

In the JVM model, an application might be started as:

~~~bash
java -jar target/application.jar
~~~

In the native model, the build tool or framework plugin generates an executable, and you run the corresponding binary:

~~~bash
./target/application
~~~

File names, directories, and build commands depend on the Maven/Gradle plugin, framework, and operating system. Do not treat a single generic native command as valid for every project. Use the official build configuration for your framework and target runtime.

With FaaS, you may need a custom runtime or adapter for the platform to invoke a native executable. Check the runtime contract: how events are received, inputs are read, responses are returned, signals are handled, logs are emitted, and architecture is declared. A native binary that runs fine in a container cannot automatically be dropped into every Java managed runtime.

## 8. Serverless Cost: Measure Total Cost Instead of Startup Alone

Cost depends on the provider's billing model. Platforms may bill by request count, invocation duration, configured memory, CPU, provisioned concurrency, networking, or supporting services.

Native executables can reduce duration or allow lower memory configurations in some cases. Yet they can also require higher memory in other cases, make build pipelines costlier, or increase development effort due to compatibility work.

Account for all of:

- Compute cost per invocation.
- Request costs and retries.
- Provisioned concurrency or warm-instance costs.
- Database, queue, object storage, and network costs.
- Native build and CI time costs.
- Effort to maintain metadata, native-specific configs, and tests.
- Incident costs if a library fails only in native mode.

A native function that runs 20% faster will not reduce total cost by 20% if most of its duration is spent waiting on a database or external API. Conversely, for frequently invoked workloads where cold starts dominate, reducing startup can yield substantial savings.

## 9. Choosing Based on Workload Characteristics

| Workload | JVM is usually suitable when | Native is usually suitable when |
|---|---|---|
| Steady-traffic HTTP API | Instances stay alive long enough for JIT warm-up to pay off | Startup remains a bottleneck and frameworks/libraries support native well |
| Scale-to-zero HTTP API | Cold starts are acceptable or startup-mitigation features exist | p95/p99 cold start is a strict requirement |
| Queue consumer for short messages | Consumers run continuously and long-term throughput matters | Workers scale on bursts and each instance handles few messages |
| Long CPU-bound processing | High post-warm-up throughput is needed | Workloads are short, too brief for JIT to pay off, and native is benchmarked |
| I/O-bound tasks | Compatibility and development velocity are priorities | Startup or footprint is a measured bottleneck |
| Heavy reflection/plugin applications | Dynamic runtime ecosystem is required | Can be replaced with build-time registration or well-tested metadata |
| Very small, low-dependency functions | Both can fit; decide via benchmarks | Achieves good startup and footprint if builds stay simple |

### 9.1. Example 1: Short-Lived Webhook Handler

A webhook receives an event, verifies a signature, writes one record, and publishes a message. The function runs for a few hundred milliseconds, can scale from zero, and experiences uneven traffic.

In this case, cold starts and footprint can impact p95/p99 and cost. A native executable is worth testing, especially if the framework and JSON, HTTP, and crypto libraries all support native well. If the JVM already meets SLAs after startup tuning or if the platform provides effective snapshot/restore, native may not offer enough benefit to offset build and maintenance costs.

### 9.2. Example 2: Continuously Running Consumer

A consumer continuously reads messages; each process runs for hours and handles thousands of messages. The JVM has time to warm up, allowing JIT to optimize repeated code paths. Here, steady-state throughput, GC behavior, and observability may matter more than startup. The JVM is usually the first choice to benchmark.

Native can still fit if the process needs a tiny footprint or rapid scale-out, but you must measure sustained throughput and CPU/RAM usage under realistic load.

### 9.3. Example 3: Heavy Framework and Reflection Function

An application loads plugins via configuration, uses dynamic type-discovering serializers, and relies on libraries with deep reflection. The JVM generally reduces compatibility risk and lets the team ship faster.

To adopt native, you must inventory all dynamic features, define metadata, test every plugin, and exercise rare paths. If migration cost outweighs cold-start benefits, staying on the JVM is a sound decision.

## 10. Fair Benchmarking Process

Do not choose native based on a single startup number on a developer laptop. Benchmark cold paths, warm paths, and scale-out behavior.

### 10.1. Keep Test Conditions Equivalent

- Same source code and dependency versions.
- Same business logic, payloads, and input data.
- Same region, CPU architecture, and network limits.
- Same memory/CPU settings if the platform allows direct comparison.
- Same concurrency limits and retry policies.
- Same downstream dependencies, or measure dependency time separately.
- Build in release/production mode for both options.

If native uses a different framework or library version than the JVM build, results no longer isolate runtime differences. Document any differences in the report.

### 10.2. Measure Multiple Workload Shapes

Run at least these scenarios:

1. Isolated cold start with no prior requests.
2. Continuous warm invocations on the same execution environment.
3. Rapid burst scaling from low to high invocation rates.
4. High concurrency to measure scale-out and connection pressure.
5. Small payloads and large payloads.
6. Both CPU-bound and I/O-bound workloads if the app handles both.
7. Slow dependencies or transient errors to observe timeouts/retries.

Do not measure just once. Collect enough samples for meaningful percentiles, and separate initialization time from business processing time.

### 10.3. Metrics to Compare

| Category | Metrics |
|---|---|
| Startup | Time to ready, cold-start duration, init duration |
| Latency | Invocation p50, p95, p99 |
| Throughput | Requests/messages per second and sustained processing time |
| Memory | Peak RSS, heap, native memory, allocation rate |
| CPU | CPU time, utilization, and GC time |
| Reliability | Error rate, timeouts, crashes, retries, and throttling |
| Scale | Instance ramp-up time, achieved concurrency, connection counts |
| Cost | Compute, request, dependency, and build pipeline costs |

Measure both sides the same way. For instance, if JVM metrics report only heap while native metrics report RSS, the comparison is unfair. Collect identical OS-process-level metrics and supplement them with runtime metrics to explain differences.

## 11. Common Pitfalls When Moving to Native

- **Application builds cleanly yet fails with reflection errors at runtime:** add metadata or use version-matched framework integrations.
- **Resources missing from package:** declare needed resources and verify files inside the binary.
- **ServiceLoader fails to find providers:** verify service metadata and reachability configuration.
- **Incompatible JNI or native libraries:** verify target architecture, ABI, and linked libraries.
- **Environment-dependent static values frozen at build time:** move initialization to runtime.
- **Overly heavy CI builds:** choose suitable build images, allocate adequate resources, and optimize caching.
- **Binary fails to run on the target environment:** build for the exact OS/architecture/libc and test inside the deployment image.
- **Lower warm performance than JVM:** benchmark PGO, GC settings, and workload structure; consider returning to the JVM if throughput matters more than startup.
- **Misleading memory metrics:** compare RSS to RSS and inspect both heap and native allocations.

Do not run a smoke test against just one endpoint. A native app may boot fine yet fail on a route triggered only by a specific event type or when the serializer encounters a rare subtype. Tests must cover realistic business paths.

## 12. Decision Checklist

Before choosing a runtime for a Java function, answer:

1. Does the function experience frequent cold starts or scale-to-zero behavior?
2. Does the SLA impose strict requirements on p95/p99 startup?
3. How long does each execution environment live and how many requests/messages does it handle?
4. Is the workload CPU-bound or mostly waiting on I/O?
5. Does post-warm-up throughput matter more than startup?
6. Does the application use reflection, dynamic proxies, JNI, or plugins?
7. Do the framework and all extensions support native in the versions used?
8. Is the native binary compatible with the platform's OS, architecture, and ABI?
9. Does CI have sufficient resources and time to build and test native executables?
10. Do latency/RAM reductions produce measurable cost savings?
11. Can the team maintain native-specific metadata and tests?
12. Can the JVM meet targets through startup tuning, snapshots, or platform configuration?

A practical strategy often starts with the JVM due to simpler deployment and broad compatibility. Then, benchmark native specifically on functions where cold start or memory is a bottleneck. If native improves key metrics without introducing excessive compatibility or operational risk, adopt native for that function. You do not have to force the entire system onto a single runtime; each function can use the option that best fits its workload.

## 13. Self-Check Questions

- What information does JVM JIT use to optimize code at runtime?
- At which lifecycle stage does Native Image differ from running a JAR on the JVM?
- Why does a native executable still need a runtime and garbage collector?
- How does the closed-world assumption affect reflection and resource loading?
- When is JVM warm-up an advantage rather than an overhead?
- Why is native not guaranteed to deliver higher throughput than the JVM?
- Why must you measure peak RSS instead of comparing only Java heap?
- Which OS, architecture, and ABI differences affect native binaries?
- Why must reflection and plugin branches be tested in native mode?
- Which metrics help decide whether native actually reduces serverless costs?

The JVM and native executables are two Java deployment models with distinct trade-offs. Choose based on function lifetime, cold-start rate, throughput, memory, compatibility, and operational cost. Benchmarking on real workloads is what reveals which option better satisfies your SLAs and budget.
