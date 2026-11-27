# What Native Image Is and the Startup and Memory Challenges It Addresses

## 1. Why Care About Startup Time and Memory?

A Spring Boot application running on the JVM has many advantages: the same JAR file can run on compatible operating systems, a rich library ecosystem, and the JVM can optimize running code using JIT (*Just-in-Time compilation*). However, in some deployment models, initializing both the JVM and the application becomes a significant portion of the cost.

Consider an order management REST service. When starting up in the traditional way, the process must initialize the JVM, load the required classes, build the `ApplicationContext`, create beans, apply auto-configuration, initialize the web server, and perform whatever tasks the application requires before it is ready to receive requests. When the number of processes increases or processes are frequently recreated, this cost can occur repeatedly.

The two main problems are:

- **Startup time:** the time from when the process starts until the application is actually ready to serve. This time affects scale-out, rolling deployments, recovery from failures, short-lived jobs, and cold starts of on-demand workloads.
- **Memory footprint:** the amount of memory a process needs when idle and under load. Besides the Java heap, there is memory for the runtime, metadata, stacks, compiled code, and other native regions. In container environments with RAM limits, a high footprint can reduce the number of instances that can be deployed or increase the risk of exceeding memory limits.

**GraalVM Native Image** is an option aimed at optimizing these two characteristics. Combined with **Spring AOT**, a Spring Boot application can be compiled ahead of time into machine code and packaged into a native executable for a specific operating system and CPU architecture.

> The goal of Native Image is not to guarantee that every application runs faster on every metric. Its primary value usually lies in startup time, memory consumption, and the ability to run immediately in environments with short process lifecycles.

## 2. What Is GraalVM Native Image?

**Native Image** is an *ahead-of-time* (AOT) compilation technology in the GraalVM ecosystem. Instead of only distributing `.class`/`.jar` bytecode for the JVM to compile and execute at runtime, the build process analyzes the application code that can be used, compiles it ahead of time into machine code, and then links it into an executable for the target platform.

Example of how it is run:

```bash
# Traditional approach: requires a compatible Java runtime on the host machine
java -jar target/order-service.jar

# Native approach: runs the executable built for this platform directly
./target/order-service
```

The commands and artifact names are illustrative; the actual output path depends on the project configuration and operating system. On Windows, native executables typically have a `.exe` extension.

### 2.1. Comparing the Path from Source Code to Runtime

| Aspect | Spring Boot Application on JVM | Spring Boot Native Image Application |
|---|---|---|
| Main artifact | JAR containing bytecode and resources | Machine code executable for the target OS/CPU |
| At build time | Compiles Java/Kotlin to bytecode, packages JAR | Adds Spring AOT, analyzes reachable code, compiles and links natively |
| At runtime | JVM loads classes, manages runtime, and can use JIT | Runs ahead-of-time compiled machine code with a leaner runtime bundled into the executable |
| Flexibility | Class loading and certain dynamic behaviors are directly supported by the JVM | Dynamic parts that the analyzer cannot detect must be declared ahead of time |
| Startup | Includes JVM work and application initialization | Usually faster because many steps are already handled at build time |
| Memory | Includes JVM and application memory regions | Often has a lower footprint in many workloads, though heap, stacks, and GC still exist |
| Long-running optimization | JIT can adapt to actual code and load | Does not benefit from JVM JIT at runtime; throughput must be measured separately |
| Artifact portability | JAR can run on compatible JVMs | Requires an artifact matching the OS, CPU, and related system libraries |

Native Image **is not** simply compressing a JAR into a single file, nor does it convert a Java application into another programming language. The executable still carries the necessary runtime components, such as object allocation, memory management, garbage collection, and thread support. Therefore, "not needing a separate JVM installed to run" does not mean "having no runtime" or "having no garbage collector".

### 2.2. Three Easily Confused AOT Concepts

**AOT (Ahead-of-Time)** is a general term for processing or compiling before a program executes. In a Spring Boot native project, it is important to distinguish:

1. **Spring AOT:** analyzes Spring configuration at build time and generates code/metadata to support creating the `ApplicationContext`, registering beans, proxies, reflection, or required resources. It helps move early-determinable decisions to the build phase and describes dynamic behaviors to the compiler.
2. **GraalVM Native Image:** performs code *reachability analysis*, compiles the necessary parts into machine code, and produces a native executable.
3. **JVM JIT:** optimizes and compiles code while the program is running based on what the runtime observes. This is a different strategy that can provide advantages for long-running applications handling heavy loads.

Spring AOT and GraalVM Native Image complement each other: Spring AOT handles many framework-specific aspects, while GraalVM builds the native program.

```mermaid
flowchart LR
    A["Spring Boot source code and configuration"] --> B["Compile bytecode"]
    B --> C["Spring AOT: generate code and metadata"]
    C --> D["GraalVM Native Image: analyze and compile"]
    D --> E["Native executable for target OS/CPU"]
    E --> F["Start up and serve requests"]
```

Simplified diagram of the steps; actual build plugins orchestrate multiple code generation tasks, dependency processing, and library linking.

## 3. How Does Native Image Improve Startup?

### 3.1. Startup Costs on the JVM

When running a Spring Boot JAR, the JVM and framework typically perform several tasks:

1. Initialize the runtime, class loaders, and structures required to execute Java.
2. Load, link, and initialize classes as needed.
3. Parse Spring configuration, identify beans, and build the `ApplicationContext`.
4. Initialize essential components such as the web server, connection pools, or external connection clients.
5. Bring the application to a state ready to serve requests; the JIT may subsequently continue optimizing frequently called code paths.

Not all of these steps occur sequentially or strictly during startup. However, they show that startup consists of both JVM work **and** the application's own work.

### 3.2. Work Shifted to Build Time

With Native Image, GraalVM compiles most determinable code ahead of time and packages the necessary runtime data. Spring AOT helps pre-generate many structures that would normally have to be discovered at runtime. Consequently, when the native process starts, it can skip part of the dynamic class loading, analysis, and compilation overhead of the traditional execution model.

However, **Native Image does not eliminate all startup work**. Connecting to a database, reading runtime configuration, warming up caches, running migrations, creating connection pools, or calling external services still takes time. An application that is slow due to DNS or an unready database will not automatically stop being slow because of AOT.

### 3.3. Defining "Startup Complete" Properly

When comparing two builds, you must choose the same measurement milestone:

| Milestone | Interpretation | Notes |
|---|---|---|
| Process start | The OS begins creating the process | This is the start of the measurement, not an indication that the app is ready |
| Spring context started | The framework has passed several initialization phases | The `Started ... in ... seconds` log is useful but does not fully replace readiness |
| Application ready | `ApplicationReadyEvent` is emitted | Reflects Spring's lifecycle; depends on tasks the application performs |
| Readiness achieved | Health/readiness endpoint returns the expected result | Suitable for measuring time until receiving traffic, if the endpoint is properly configured |
| First successful request | The first business request completes successfully | Includes the impact of connections and lazy initialization triggered on the first request |

In Kubernetes or autoscaling environments, **the time from process start to readiness** is usually closest to the operational question: "how long until a new instance can receive traffic?". For batch jobs, you also need to measure total job execution time, because fast startup with slower processing may not be the better choice.

## 4. Which Parts of Memory Does Native Image Aim to Reduce?

### 4.1. A Java Application's Memory Is Not Just Heap

A Spring Boot process on the JVM can use:

- **Java heap:** where most Java objects created by the application reside.
- **Metaspace / metadata and runtime regions:** class information, JVM structures, and data for runtime management.
- **Code cache:** where JIT-compiled machine code resides (if present).
- **Thread stacks:** stack memory for threads.
- **Native allocations / system libraries:** buffers and memory regions used by native libraries, networking, TLS, compression, and other components.

Native Image typically reduces some runtime overhead associated with class loading and JIT, while avoiding bundling a full JVM as when running a JAR. However, **heap, thread stacks, native allocations, and garbage collection still exist**. Actual savings depend on the framework, libraries, thread count, caches, workload, and GC configuration.

### 4.2. Distinguishing Common Metrics

| Metric | What Is It Measuring? | Where Is It Commonly Misunderstood? |
|---|---|---|
| Heap used | Size of objects currently in use in the Java heap | Not the entire RAM of the process |
| Heap committed / max | Committed / maximum allowed capacity for the heap | Not synonymous with RSS or actual physical RAM in use |
| RSS (*Resident Set Size*) | Physical memory pages currently in RAM associated with the process | May include shared pages; cannot be used to deduce heap alone |
| Peak RSS | Highest RSS recorded during the measurement window | Does not reflect the full curve over time, but is useful for setting memory limits |
| Container memory usage | Memory accounted for by the container/cgroup environment | May include page cache and other memory types depending on metrics/tools |

For example, if the native build reports a lower heap, that alone is not enough to conclude the container will drop by that exact amount of RAM. You must check **RSS, peak memory, and container-level metrics** under the same conditions.

### 4.3. When a Low Footprint Creates Economic Benefits

Suppose a node has a fixed memory limit and needs to run many service instances. If each instance uses less RAM when idle and at target load, the operations team can pack more instances or set lower resource requests/limits after verifying safety. This benefit is especially worth considering for many small microservices, low-traffic APIs that must remain always ready, or workloads that frequently scale up and down.

You should not jump directly from "lower RAM" to "cloud costs definitely drop": CPU, pricing models, minimum replica counts, quotas, and load capacity also determine actual cost.

## 5. Suitable Use Cases and Trade-offs

Native Image is well-suited when **time to instance readiness** or **RAM per instance** is a critical constraint. Typical scenarios include:

| Scenario | Reason to Try Native Image | What Else to Verify |
|---|---|---|
| Functions / event-driven tasks | Processes are frequently created fresh; cold start affects latency | Total event processing time and platform limits |
| Continuously scaling-out microservices | Earlier instance readiness helps handle traffic spikes | Actual readiness time and load-handling capacity |
| Short-lived batch jobs | Startup accounts for a large share of total runtime | Total job duration, CPU, and library compatibility |
| Many small services on a single node | Lower footprint can increase deployment density | Peak RSS, RAM limits, and safety margin under load spikes |
| Long-running, CPU-intensive APIs | May still offer memory or startup advantages | Compare throughput, p95/p99 latency, and CPU usage against warmed-up JVM JIT |

Common trade-offs:

**Heavier and slower builds.** The native compiler needs to analyze dependencies, optimize code, and link the executable, often consuming significant CPU/RAM in the pipeline. Development teams need to factor in CI build time and build machine resources.

**Less flexibility with dynamic behavior.** Native Image relies on a *closed-world* assumption: the compiler must know which code and structures may be used. Reflection, dynamic proxies, resources loaded by path name, serialization, JNI, or dynamic class loading may require metadata/hints. If missing, the application might build successfully yet fail on a rarely invoked business flow.

**Dependence on build platform and runtime environment.** A native executable is tied to an operating system, CPU architecture, and sometimes system libraries or linking methods. A Linux build does not immediately produce a Windows executable, and a Linux binary must be compatible with the target runtime/container.

**Runtime performance does not improve uniformly.** The JVM JIT can use runtime profiling information to optimize hot code paths. A native application starts fast but may have lower throughput or higher CPU usage for some long-running workloads; other applications may yield different results. You must measure on real workloads.

**Artifact size and container image size have no one-way rule.** A native executable may be larger than a JAR, yet does not require distributing a separate JRE/JDK in the runtime image. Total container size depends on the base image, system libraries, debug symbols, and packaging approach.

**Observability and debugging require verification.** Profiling methods, collecting heap/thread diagnostics, handling stack traces, integrating agents, and APM libraries can differ from the JVM. Confirm that your operational tools support the native variant and corresponding versions.

## 6. What Role Does Spring Boot Play in Native Compilation?

Spring Boot uses many convenient mechanisms such as component scanning, dependency injection, configuration properties, and auto-configuration. On the JVM, the framework can discover or generate certain structures at runtime. With native, key information must be determined or declared early.

**Spring AOT** performs build-time processing to generate initialization code, bean configurations, and necessary *runtime hints*. This helps GraalVM see the data types, methods, resources, or proxies that the application logic uses indirectly.

### 6.1. Example of a Case Requiring Runtime Hints

Suppose an application uses a library that discovers and instantiates objects via reflection, or reads templates not directly referenced from Java code. Reachability analysis might not automatically detect all involved components. Spring provides a mechanism to register hints:

```java
import org.springframework.aot.hint.MemberCategory;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ImportRuntimeHints;

@Configuration
@ImportRuntimeHints(OrderRuntimeHints.class)
class NativeConfig {
}

class OrderRuntimeHints implements RuntimeHintsRegistrar {
    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        // Example: a library uses reflection to invoke OrderDto's constructor.
        hints.reflection().registerType(
            OrderDto.class,
            MemberCategory.INVOKE_DECLARED_CONSTRUCTORS
        );

        // Example: the application reads template files from the classpath at runtime.
        hints.resources().registerPattern("templates/order/*.html");
    }
}
```

Here, `OrderDto` is a project-defined DTO class. The snippet illustrates **how** to register reflection and resources; specific hint needs depend on the library and code access paths. You should not register entire classes or enable overly broad reflection out of habit. Many Spring Boot features already have AOT support, so not every DTO needs manual hints.

### 6.2. Cases Requiring Compatibility Review

- Libraries that look up classes by class name strings, use `Class.forName(...)`, or load new plugins after the application has been built.
- Frameworks that generate proxies/bytecode dynamically or use reflection to inspect constructors, fields, and methods.
- Loading JSON, XML, templates, certificates, or configuration files from the classpath using paths only known at runtime.
- Serialization/deserialization of dynamically discovered types, JNI bindings, or native libraries.
- Application configurations that alter bean structures based on conditions only known at runtime.

A compatibility issue does not necessarily mean a project cannot use Native Image. You need to pinpoint the dynamic component, leverage the library's AOT support, add hints where appropriate, and retest on the **actual native executable**.

## 7. Trying Native Image on a Spring Boot Project

To picture the workflow, consider a Spring Boot project on a version supporting GraalVM Native Image, using a compatible JDK/GraalVM and build plugin. The following examples assume the project has configured `native-maven-plugin` or the Gradle plugin `org.graalvm.buildtools.native`, and has the required native-image tooling installed.

### 7.1. With Maven

```bash
# Traditional JAR build as a baseline
./mvnw -DskipTests package

# Build native executable (when the 'native' profile is configured)
./mvnw -Pnative native:compile
```

In projects using the Spring Boot parent and corresponding native configuration, the `native` profile typically orchestrates Spring AOT processing and GraalVM Native Build Tools. For customized projects, inspect the plugins and lifecycle configuration before running. Native compilation requires significantly more build resources than regular JAR packaging.

### 7.2. With Gradle

```bash
# Traditional JAR build
./gradlew bootJar

# Build native executable when GraalVM Native Build Tools is enabled
./gradlew nativeCompile
```

Spring Boot also supports building container images via buildpacks for appropriately configured projects. Ensure the image uses the right native executable and test on the same target architecture, OS, and container resources.

### 7.3. Verifying the Result

Do not stop at the `BUILD SUCCESS` message. Run the native build in an appropriate environment and test at least the critical flows: startup with realistic configuration, API calls, reading templates/resources, data serialization, database connections, TLS checks, health/readiness, and flows using reflection.

If the application depends on external services, distinguish configuration/connection errors from native metadata errors. Integration testing on the native executable is essential to catch issues that unit tests on the JVM might miss.

## 8. Measuring Startup and Memory Fairly

Suppose you need to answer: **"Does the native build help Order Service start faster and use less RAM?"** The approach is to build **two variants from the same commit**, providing the same functionality and running under comparable conditions.

### 8.1. Experiment Setup

1. Lock down the same application version, configuration, Spring profiles, input data, and load level. Record the JDK, GraalVM, Spring Boot, build plugin versions, OS, CPU, and machine architecture.
2. Build the JVM JAR and native release variants. Run under equivalent conditions regarding CPU, memory limits, environment variables, database, and network. Do not run both processes competing for resources while collecting metrics.
3. Repeat cold start measurements multiple times; choose process creation as the start milestone and successful readiness as the end milestone. Record the median, p95, and variance range; avoid drawing conclusions from a single run.
4. Measure RSS/container memory when the application is idle and after stabilizing under a fixed load. Also track peak RSS during startup and load processing.
5. Run load tests with the same scenario and concurrency level to compare requests/second, p95/p99 latency, CPU, and error rate. For the JVM, clearly document the warm-up phase before measuring steady-state performance.
6. Compare total build time and resources; note library compatibility, observability, and operational friction.

For example, on Linux you can take a **point-in-time snapshot** of RSS (in KB) using:

```bash
ps -o pid,rss,cmd -p <PID>
```

Or monitor container metrics with your existing monitoring tools. The `ps` command only returns a value at the moment it runs; **it does not measure peak RSS**. You also should not measure startup by the total duration of a single `curl` command after the server is already up: that measurement primarily reflects the HTTP latency of the request.

With Spring Boot Actuator's readiness endpoint (when enabled and configured), the measurement procedure can be described as:

```text
start = monotonic clock at process creation
launch the JVM or native build
poll GET /actuator/health/readiness until ready status is reached
startup_ready = current monotonic clock - start
record RSS/peak memory and CPU metrics per phase
```

If external dependencies are unstable, startup numbers may reflect waiting on the database or network rather than the compilation technology itself. In that case, measure them separately and clearly document the assumptions.

### 8.2. Results Table Template

Fill in **actual measurements** in the table below; there is no universal improvement rate that applies to every application.

| Metric | JVM JAR | Native Image | Interpretation |
|---|---|---|---|
| Startup to readiness, median | _(measure)_ | _(measure)_ | Lower means ready to accept traffic sooner |
| Startup to readiness, p95 | _(measure)_ | _(measure)_ | Shows variance across cold starts |
| Idle RSS | _(measure)_ | _(measure)_ | Compares footprint at low load |
| Peak RSS under load | _(measure)_ | _(measure)_ | Directly relates to memory limits |
| Throughput at target load | _(measure)_ | _(measure)_ | Must evaluate alongside CPU and error rate |
| Steady-state p95 latency | _(measure)_ | _(measure)_ | Reflects real request latency |
| Build time | _(measure)_ | _(measure)_ | Trade-off for CI/CD and development loop |
| Runtime container size | _(measure)_ | _(measure)_ | Depends on base image and system libraries |

**How to read the results:** if native wins clearly on startup and RAM but loses throughput, the decision still depends on deployment goals. A batch job running for a few seconds may be evaluated differently from an API continuously handling heavy CPU load. The ultimate yardstick is efficiency *per workload*, not the label "native" or "JVM".

## 9. Common Misconceptions

**"Native Image is always faster than the JVM."** Inaccurate. Native usually has an advantage in startup; throughput, post-warm-up latency, and CPU can be better or worse depending on workload, configuration, and tool versions.

**"Native Image does not use a heap and does not need GC."** Inaccurate. The native binary still needs object allocation and memory lifecycle management, including garbage collection.

**"If the native build succeeds, every feature will work."** Inaccurate. Reflection, resources, or rarely hit code paths may only fail at runtime. Testing the actual native build and real integrations is mandatory before deployment.

**"The smaller the JAR, the less RAM the application uses."** There is no direct correlation. Artifact size on disk is different from process memory while running.

**"Native Image replaces all Spring Boot optimization techniques."** Inaccurate. Minimizing dependencies, reducing unnecessary beans, sizing pools appropriately, optimizing queries, caching, and tuning readiness still directly affect startup and RAM.

## 10. Conclusion and Further Learning

GraalVM Native Image enables compiling Java applications ahead of time into native executables, while Spring AOT prepares code and metadata so a Spring Boot application—which inherently relies on many dynamic components—can operate within that model. The two benefits to verify are **shortening the time until the application is ready** and **reducing memory per instance**. The cost can be more complex builds, restrictions on dynamic features, and long-term processing performance that differs from the JVM JIT.

As you continue practicing, use the same Spring Boot project to: configure Maven or Gradle native builds, catch reflection/resource errors and register hints when needed, run compatibility tests, package containers, and then compare cold start, readiness, RSS, and performance under load before deciding to operate the native build.

### Official References

- [Spring Boot Reference — GraalVM Native Images](https://docs.spring.io/spring-boot/reference/packaging/native-image/)
- [Spring Framework Reference — Ahead-of-Time Optimizations](https://docs.spring.io/spring-framework/reference/core/aot.html)
- [GraalVM — Native Image](https://www.graalvm.org/latest/reference-manual/native-image/)
