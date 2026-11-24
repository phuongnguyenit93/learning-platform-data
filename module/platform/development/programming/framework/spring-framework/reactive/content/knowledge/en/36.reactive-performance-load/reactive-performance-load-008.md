# Comparing Reactive with MVC or Virtual Threads Under Identical Real Load

## 1. Goal and Questions to Answer

Spring MVC, Spring MVC running with virtual threads, and Spring WebFlux can all serve HTTP APIs in Java. Each model organizes I/O waiting, thread usage, task scheduling, and data flow differently. There is no universal conclusion that reactive is always faster than MVC, that virtual threads always replace WebFlux, or that one framework achieves the highest throughput across every workload.

This lesson builds a repeatable, explainable comparison approach:
- Compare all three options under the same workload and the same resource limits.
- Distinguish I/O-bound, CPU-bound, and mixed workloads.
- Hold dependencies, data, payloads, timeouts, connection pools, and incoming load constant.
- Measure throughput, p50/p95/p99 latency, error rate, CPU, heap/direct memory, GC, threads, connections, and queues.
- Use a load generator driven by offered arrival rate rather than a loop dependent on response time.
- Analyze results at the saturation point and identify the real bottleneck.
- Build a sample Spring Boot project with three separate apps: MVC with platform threads, MVC with virtual threads, and WebFlux.
- Know when to choose each model, when additional benchmarking is needed, and when numbers are insufficient to decide.

**The three models compared:**

| Model | Request Handling | While Waiting on I/O |
| --- | --- | --- |
| Spring MVC + platform threads | Servlet requests run on server platform threads | Request thread is usually held while waiting on blocking I/O |
| Spring MVC + virtual threads | MVC/Servlet programming model, using virtual threads per config/runtime support | Virtual thread can unmount on supported blocking I/O, freeing its carrier |
| Spring WebFlux + Reactor Netty | Non-blocking handlers and Reactive Streams | Event-loop is not blocked; pipeline resumes when I/O signals arrive |

Virtual threads are a threading model, not a standalone web framework. WebFlux is a reactive web stack. The two options solve different problems and can coexist in the same system across appropriate boundaries.

## 2. Understanding the Three Models Accurately

### 2.1. Spring MVC with Platform Threads

Spring MVC is built on the Servlet API. In the traditional request-per-thread model, a request typically occupies a server worker thread while the controller performs work. If the controller calls synchronous JDBC, reads files, or makes blocking HTTP calls, that thread waits for I/O to complete.

Advantages:
- Sequential programming, easy to read and debug with stack traces.
- Rich ecosystem of Servlets, filters, security, transactions, JDBC, and synchronous libraries.
- Easy integration with existing blocking dependencies.
- Under moderate or CPU-bound load, this model can deliver strong performance with simplicity.

Limitations:
- Platform threads have higher stack/native resource costs than virtual threads.
- Thread pools are bounded; when requests wait long on I/O, workers stay held and new requests can queue up.
- Raising thread counts unboundedly is not a solution because the OS, memory, and scheduler have limits.
- One slow dependency can hold threads far longer than actual CPU time needed.

### 2.2. Spring MVC with Virtual Threads

A virtual thread is a JVM-managed Thread scheduled onto a smaller pool of platform carrier threads. When a virtual thread executes supported JDK blocking I/O operations, it can unmount from its carrier while waiting; the carrier can then run another virtual thread.

This model keeps synchronous code:

```java
String result = restClient.get()
        .uri("/remote")
        .retrieve()
        .body(String.class);
```

Request threads can wait on I/O without holding a platform thread in many situations. This helps thread-per-request applications with high concurrency spent largely waiting on I/O.

What virtual threads do not do:
- They do not make CPU computations run faster.
- They do not add CPU cores.
- They do not add capacity to databases, downstream APIs, or connection pools.
- They do not automatically cap concurrent requests to dependencies.
- They do not eliminate the need for timeouts, bulkheads, rate limits, backpressure, or queue bounds.
- They do not turn a blocking API into non-blocking I/O; code retains synchronous semantics.

Virtual threads require Java 21+; Spring Boot 3.5 enables support via:

```properties
spring.threads.virtual.enabled=true
```

Spring Boot 3.5 recommends Java 24+ for a better experience, while Java 21+ is the minimum requirement. Use the exact same JDK, update version, and JVM configuration across all three apps in a benchmark.

Virtual threads are daemon threads. For apps needing to keep the JVM alive when only virtual threads remain, Spring Boot recommends:

```properties
spring.main.keep-alive=true
```

With supported embedded Tomcat or Jetty, Spring Boot can configure virtual threads for request handling. Verify the actual server implementation and runtime threads; do not infer solely from properties. This property does not turn WebFlux's Reactor Netty event-loop into virtual threads.

### 2.3. Spring WebFlux with Reactor

WebFlux supports non-blocking I/O and Reactive Streams backpressure. On Reactor Netty, a small set of event-loop threads serves many connections; when I/O is not yet ready, the event loop can process other work instead of holding a dedicated thread per waiting request.

Controllers compose results asynchronously:

```java
@GetMapping("/work")
public Mono<String> work() {
    return webClient.get()
            .uri("/remote")
            .retrieve()
            .bodyToMono(String.class);
}
```

Conditions for this model to pay off:
- Most of the request path must be non-blocking.
- Use reactive HTTP clients, R2DBC, or appropriate reactive drivers.
- Never block the event-loop with JDBC, Thread.sleep, blocking I/O, or long CPU tasks.
- Manage demand, prefetch, concurrency, and buffers.
- Handle cancellation, timeouts, errors, and resource cleanup per lifecycle.

Calling `block()` or running JDBC directly on the event-loop can hold a thread and impact many unrelated requests. For legacy blocking APIs, you can isolate them on `Schedulers.boundedElastic()` or a bounded executor, though that is a blocking integration workaround rather than a fully non-blocking path.

### 2.4. WebFlux Does Not Require Netty

WebFlux can run on Reactor Netty as well as certain Servlet containers. Spring MVC and WebFlux can coexist, though Spring Boot picks MVC if both `spring-boot-starter-web` and `spring-boot-starter-webflux` are on the classpath under standard auto-detection.

Therefore, a benchmark comparing MVC/Tomcat and WebFlux/Netty is really comparing two complete deployment stacks, including framework, server connector, and runtime config. To isolate the programming model's effect alone, intentionally control or swap server connectors, and document the setup explicitly.

## 3. Workloads Determine Outcomes

Never run one benchmark and declare one model superior for every application. At minimum, distinguish three workloads.

### 3.1. I/O-Bound: Waiting on Downstream

Example request:
1. Receive HTTP request.
2. Call a downstream API with 50–200 ms latency.
3. Wait for response.
4. Serialize small payload and return result.

Here, platform threads can be tied up while waiting; virtual threads can increase concurrent waiting tasks; WebFlux can use fewer event-loop threads if the whole chain is non-blocking.

This workload suits comparing scalability when many requests wait on I/O.

### 3.2. CPU-Bound: Computation

Examples:
- Hashing/encoding.
- Data calculations.
- Image compression.
- Pure CPU algorithms.
- Large object transformations.

CPU-bound workloads are constrained primarily by CPU cores, algorithms, allocations, and memory bandwidth. Virtual threads do not create extra CPU. Reactive operators do not make CPU math faster on their own either.

When measuring CPU-bound work, use the exact same computation function, inputs, iteration counts, and core counts. In WebFlux, avoid running long calculations directly on the event-loop; use an appropriate CPU scheduler while documenting scheduler overhead and worker counts.

### 3.3. Mixed Workloads

Real-world apps typically wait on DB/HTTP while also serializing, validating, authorizing, and computing. This is the most important workload for production decisions.

Measure separately:
- Dependency wait time.
- Application CPU time.
- Connection pool wait.
- Queue wait.
- Serialization/deserialization.
- Time spent consuming response bodies.

Measuring only total latency can mistake a database bottleneck for a thread model issue.

## 4. Principles of Fair Comparison

### 4.1. Fix Input Variables

| Variable | Must Keep Identical |
| --- | --- |
| Hardware | Same CPU model/cores, RAM, NUMA/host if possible |
| Container | Same CPU quota, memory limit, and container runtime |
| JDK | Same vendor, major/minor/update, and JVM flags |
| Framework | Same Spring Boot/Spring Framework version |
| Payload | Same request size, response size, schema, and compression |
| Workload | Same endpoint semantics, business logic, and input distribution |
| Dependency | Same downstream/database, data, and latency |
| Connection | Record max connections, pools, keep-alive, and protocol |
| Security | Same authentication/authorization, or intentionally disabled for all |
| Logging | Same log level; avoid debug/trace in a single variant |
| Metrics | Same instrumentation and cardinality |
| Timeouts | Same connect/read/overall deadlines |
| Load generator | Same host, script, arrival rate, and duration |

Do not benchmark three servers on the same machine simultaneously if they compete for CPU/memory. Run each variant separately in the same environment and repeat across multiple runs.

### 4.2. Separate Two Benchmark Questions

**Question A — Comparing end-to-end stacks:** MVC/Tomcat/platform, MVC/Tomcat/virtual, WebFlux/Netty. This is the practical question when choosing a deployment stack. Results include connector and framework differences.

**Question B — Comparing programming models:** try keeping server, protocol, dependency, and workload identical while changing only request/thread handling. This is harder and may require server customization. Do not conflate results from A and B into one conclusion.

### 4.3. Same Dependency, Not Just Equal Simulated Delays

If the goal is I/O-bound testing, prefer a shared downstream service:
- Same endpoint.
- Same payload.
- Same latency distribution.
- Same connection reuse.
- Same HTTP version.
- Same timeouts.
- Same connection counts, or explicitly document client connector differences.

A `Thread.sleep(100)` in MVC and `Mono.delay(100ms)` in WebFlux only simulate wait time; they do not exercise networking, connection pools, HTTP clients, DNS, TLS, or databases. Use synthetic waits for isolated scheduling tests, not as substitutes for end-to-end benchmarks.

## 5. Designing an I/O-Bound Benchmark with a Shared Downstream

The template below uses three separate applications. All three expose `GET /work`; each request calls a WebFlux stub on port 9090, which returns the same payload after a delay. The two MVC apps call the same WebClient and block on the request thread; the WebFlux app returns a Mono without blocking.

This design keeps the outbound client library/connector identical while varying how inbound requests are handled. It measures end-to-end request handling across the three variants under an I/O-bound workload, rather than a microbenchmark measuring only the event loop.

### 5.1. Project Structure

```text
web-stack-benchmark/
  settings.gradle
  build.gradle
  stub/
    build.gradle
    src/main/java/demo/stub/StubApplication.java
    src/main/java/demo/stub/DelayController.java
  mvc-platform/
    build.gradle
    src/main/resources/application.properties
    src/main/java/demo/mvcplatform/MvcPlatformApplication.java
    src/main/java/demo/mvcplatform/WorkController.java
  mvc-virtual/
    build.gradle
    src/main/resources/application.properties
    src/main/java/demo/mvcvirtual/MvcVirtualApplication.java
    src/main/java/demo/mvcvirtual/WorkController.java
  webflux/
    build.gradle
    src/main/resources/application.properties
    src/main/java/demo/webflux/WebFluxApplication.java
    src/main/java/demo/webflux/WorkController.java
  load/
    k6-work.js
```

### 5.2. settings.gradle

```groovy
rootProject.name = 'web-stack-benchmark'

include 'stub'
include 'mvc-platform'
include 'mvc-virtual'
include 'webflux'
```

### 5.3. Root build.gradle

```groovy
plugins {
    id 'org.springframework.boot' version '3.5.6' apply false
    id 'io.spring.dependency-management' version '1.1.7' apply false
}

allprojects {
    group = 'demo'
    version = '1.0.0'

    repositories {
        mavenCentral()
    }
}

subprojects {
    apply plugin: 'java'
    apply plugin: 'org.springframework.boot'
    apply plugin: 'io.spring.dependency-management'

    java {
        toolchain {
            languageVersion = JavaLanguageVersion.of(21)
        }
    }

    dependencies {
        testImplementation 'org.springframework.boot:spring-boot-starter-test'
    }

    tasks.withType(Test).configureEach {
        useJUnitPlatform()
    }
}
```

Each module adds its own dependencies in its `build.gradle`:

| Module | Additional Dependencies |
| --- | --- |
| stub | spring-boot-starter-webflux, spring-boot-starter-actuator |
| mvc-platform | spring-boot-starter-web, spring-boot-starter-webflux, spring-boot-starter-actuator |
| mvc-virtual | spring-boot-starter-web, spring-boot-starter-webflux, spring-boot-starter-actuator |
| webflux | spring-boot-starter-webflux, spring-boot-starter-actuator |

In the two MVC modules, `starter-webflux` provides only `WebClient`; because `starter-web` is present, Spring Boot selects the MVC application type under standard auto-detection. Do not expect a profile on the same classpath to automatically switch to a Netty/WebFlux server.

Example `build.gradle` for the `stub` module:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

For `mvc-platform` and `mvc-virtual`:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

For `webflux`:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

### 5.4. Shared Stub

File `stub/src/main/resources/application.properties`:

```properties
server.port=9090
spring.application.name=benchmark-stub
management.endpoints.web.exposure.include=health,metrics
```

File `DelayController.java`:

```java
package demo.stub;

import java.time.Duration;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class DelayController {

    @GetMapping("/delay")
    public Mono<String> delay(
            @RequestParam(defaultValue = "100") long ms) {
        if (ms < 0 || ms > 2000) {
            return Mono.error(
                    new IllegalArgumentException("ms out of range"));
        }
        return Mono.delay(Duration.ofMillis(ms))
                .thenReturn("OK");
    }
}
```

`StubApplication.java`:

```java
package demo.stub;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StubApplication {

    public static void main(String[] args) {
        SpringApplication.run(StubApplication.class, args);
    }
}
```

The shared stub returns body `OK` after 100 ms by default. It is a simulated dependency with real inter-process networking, not a database or production downstream system. Measure the stub's CPU, connections, and latency to verify the stub itself does not become the bottleneck.

### 5.5. MVC with Platform Threads

File `mvc-platform/src/main/resources/application.properties`:

```properties
spring.application.name=mvc-platform
server.port=8080
spring.threads.virtual.enabled=false
benchmark.stub.base-url=http://127.0.0.1:9090
management.endpoints.web.exposure.include=health,metrics
```

`MvcPlatformApplication.java`:

```java
package demo.mvcplatform;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcPlatformApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                MvcPlatformApplication.class, args);
    }
}
```

`WorkController.java`:

```java
package demo.mvcplatform;

import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
class ClientConfiguration {

    @Bean
    WebClient benchmarkClient() {
        return WebClient.builder()
                .baseUrl("http://127.0.0.1:9090")
                .build();
    }
}

@RestController
class WorkController {

    private final WebClient client;

    WorkController(WebClient client) {
        this.client = client;
    }

    @GetMapping("/work")
    String work() {
        return client.get()
                .uri("/delay?ms=100")
                .retrieve()
                .bodyToMono(String.class)
                .block(Duration.ofSeconds(2));
    }
}
```

The controller uses the MVC request thread and blocks up to two seconds to retrieve the response from the same WebClient. This intentionally creates a blocking workload on the request thread to measure platform-thread behavior.

### 5.6. MVC with Virtual Threads

File `mvc-virtual/src/main/resources/application.properties`:

```properties
spring.application.name=mvc-virtual
server.port=8080
spring.threads.virtual.enabled=true
spring.main.keep-alive=true
benchmark.stub.base-url=http://127.0.0.1:9090
management.endpoints.web.exposure.include=health,metrics
```

`MvcVirtualApplication.java`:

```java
package demo.mvcvirtual;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcVirtualApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                MvcVirtualApplication.class, args);
    }
}
```

`WorkController.java` has the same logic as the `mvc-platform` module, changing the package to `demo.mvcvirtual`:

```java
package demo.mvcvirtual;

import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
class ClientConfiguration {

    @Bean
    WebClient benchmarkClient() {
        return WebClient.builder()
                .baseUrl("http://127.0.0.1:9090")
                .build();
    }
}

@RestController
class WorkController {

    private final WebClient client;

    WorkController(WebClient client) {
        this.client = client;
    }

    @GetMapping("/work")
    String work() {
        return client.get()
                .uri("/delay?ms=100")
                .retrieve()
                .bodyToMono(String.class)
                .block(Duration.ofSeconds(2));
    }
}
```

What differs in this module is that the runtime/server executor is configured to use virtual threads via Spring Boot. The controller remains synchronous MVC; the outbound WebClient remains the same client/connector, and the request thread waits via `block`.

**Pre-benchmark check:** confirm the server is actually using virtual threads in the running environment; do not rely solely on the property file. Record JDK, Spring Boot, embedded server version, and thread names/JFR. If the server/connector or custom executor does not support virtual thread integration as expected, the result is not a valid MVC virtual threads benchmark.

### 5.7. WebFlux

File `webflux/src/main/resources/application.properties`:

```properties
spring.application.name=webflux
server.port=8080
benchmark.stub.base-url=http://127.0.0.1:9090
management.endpoints.web.exposure.include=health,metrics
```

`WebFluxApplication.java`:

```java
package demo.webflux;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebFluxApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                WebFluxApplication.class, args);
    }
}
```

`WorkController.java`:

```java
package demo.webflux;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@Configuration
class ClientConfiguration {

    @Bean
    WebClient benchmarkClient() {
        return WebClient.builder()
                .baseUrl("http://127.0.0.1:9090")
                .build();
    }
}

@RestController
class WorkController {

    private final WebClient client;

    WorkController(WebClient client) {
        this.client = client;
    }

    @GetMapping("/work")
    Mono<String> work() {
        return client.get()
                .uri("/delay?ms=100")
                .retrieve()
                .bodyToMono(String.class)
                .timeout(java.time.Duration.ofSeconds(2));
    }
}
```

WebFlux returns `Mono<String>` without blocking the event-loop. The two-second deadline is set on the publisher. The two MVC modules use `block(Duration.ofSeconds(2))`; all three share the same application-level time budget, though exception mapping between blocking timeout and reactive timeout may differ. Ensure consistent error/status mapping in your benchmark.

### 5.8. Running Each Variant

Start the stub once:

```bash
./gradlew :stub:bootRun
```

In a separate terminal, run only one benchmark app at a time:

```bash
./gradlew :mvc-platform:bootRun
```

Or:

```bash
./gradlew :mvc-virtual:bootRun
```

Or:

```bash
./gradlew :webflux:bootRun
```

The apps share port 8080, so stop the previous variant before starting the next. The stub keeps listening on 9090.

Verify readiness before load:

```bash
curl -i http://127.0.0.1:8080/actuator/health
curl -i http://127.0.0.1:8080/work
```

Expected response body for `/work`:

```text
OK
```

Do not start k6 before both the app and stub are ready. Do not include startup/JIT warmup time in steady-state measurements.

## 6. Load Generator by Offered Arrival Rate

### 6.1. Why Use constant-arrival-rate?

A closed-loop test that sends the next request only after the previous response finishes automatically lowers offered load when the server slows down. When saturated, the generator sends fewer requests and can make latency appear lower than the load real users would actually generate.

A fixed arrival-rate scenario sets how many requests start per second. Monitor `dropped_iterations`: if the load generator cannot issue enough iterations, the test fails to reach its intended offered rate and results cannot be compared as planned.

### 6.2. k6 Script

File `load/k6-work.js`:

```javascript
import http from 'k6/http';
import { check } from 'k6';

export const options = {
  scenarios: {
    steady_load: {
      executor: 'constant-arrival-rate',
      rate: 200,
      timeUnit: '1s',
      duration: '5m',
      preAllocatedVUs: 200,
      maxVUs: 1000
    }
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<500']
  }
};

export default function () {
  const response = http.get(__ENV.BASE_URL + '/work');

  check(response, {
    'HTTP 200': r => r.status === 200,
    'body is OK': r => r.body === 'OK'
  });
}
```

The 200 requests/second rate and 500 ms p95 threshold are illustrative starting values, not universal results or SLOs. Tune the rate to expected capacity, dependency latency, and load generator capability.

Run:

```bash
k6 run -e BASE_URL=http://127.0.0.1:8080 load/k6-work.js
```

To find saturation, step up arrival rates across separate stages—for instance 50, 100, 200, 400, 800 requests/second. Give each stage enough stabilization and measurement time. Stop when error rate/latency breaches thresholds or resources hit safety limits.

### 6.3. The Load Generator Must Have Enough Headroom

- Run the load generator on a separate machine/container from the server if possible.
- Monitor CPU, memory, and network on the k6 host.
- Monitor `dropped_iterations` and actual VU count.
- Do not raise `maxVUs` indefinitely to mask an underpowered generator.
- Pin k6 version, script, seed/inputs, and test duration.
- Never run all three benchmark servers concurrently on the same host unless your goal is measuring resource contention.

## 7. Metrics to Record

### 7.1. Service Quality

| Metric | Question Answered |
| --- | --- |
| Throughput (completed req/s) | How many requests per second does the system complete? |
| Offered arrival rate | How many requests per second does the generator try to send? |
| p50 latency | How long does a typical request take? |
| p95/p99 latency | Does tail latency degrade under heavy load? |
| Error rate | How many requests fail/time out? |
| Dropped iterations | Did the generator issue the requested load? |
| Active requests | How many requests are currently in flight? |

Do not look only at throughput. A server pushing high requests/second with spiking p99 and high error rates may fail its SLA.

### 7.2. CPU and Memory

- CPU utilization per process/container.
- Heap used/committed and allocation rate.
- Direct/native memory, especially with Netty.
- GC count, pause time, allocation pressure, and promotion.
- RSS/container memory.
- Context switches and runnable threads.
- JFR allocation/lock/I/O profiles.

WebFlux may use fewer request threads yet still maintains heap/direct buffers, event loops, and queues. Virtual threads reduce platform thread costs while waiting on I/O, yet each virtual thread still has a stack/state and can consume memory at very high concurrency.

### 7.3. Threads and Queues

For MVC platform:
- Tomcat busy/current/max threads.
- Request queue/accept count.
- Executor queue and rejected tasks.

For MVC virtual:
- Number of live virtual threads.
- Carrier/platform thread utilization.
- JFR pinned virtual threads.
- DB/HTTP connection wait queues.
- Semaphore/resource waits.

For WebFlux:
- Reactor Netty active connections/event loops.
- Event-loop pending tasks.
- Scheduler workers/queues.
- Pending connection pool acquisitions.
- Operator prefetch/buffers and cancellations.

Never compare raw thread counts while ignoring thread roles. 1,000 virtual threads waiting on I/O are not equivalent to 1,000 held platform threads.

### 7.4. Dependencies

If the workload calls a database or HTTP service, record:
- Active/idle connection counts.
- Pending acquire count and acquire latency.
- Downstream request rate and latency.
- Database CPU, lock waits, query plans, and connection count.
- Stub/downstream error rate.
- Timeout/retry counts.

If the DB connection pool hits its cap, adding virtual threads or event loops will not make the database faster.

## 8. Analysis by Workload

### 8.1. I/O-Bound with Steady Latency

When most requests wait on a dependency, platform-thread MVC may hit worker thread or queue limits. MVC virtual can hold more waiting requests without needing the same number of platform threads. WebFlux can serve many connections with fewer event-loop threads if the entire chain is non-blocking.

Outcomes depend on:
- Downstream connection pools.
- Allowed connection counts.
- HTTP client connectors.
- Timeouts.
- Payload encode/decode.
- CPU and memory.
- Server configuration.

If all variants are constrained by the same 50-connection database pool, raising concurrency may only increase queue wait rather than throughput.

### 8.2. CPU-Bound

For CPU-bound work, all three models are bounded by core count and algorithm efficiency. Virtual threads do not add cores; WebFlux does not accelerate CPU math on its own. Differences may stem from:
- Scheduler/executor overhead.
- Context switching.
- Allocation and GC.
- Serialization.
- JIT compilation.
- Lock contention.

Do not use `Thread.sleep()` to represent CPU-bound work. Use the exact same CPU function with fixed inputs and iterations; measure CPU time, throughput, and tail latency.

Deterministic function example:

```java
public final class CpuWork {

    private CpuWork() {
    }

    public static long calculate(int iterations) {
        long value = 0x1234ABCDL;

        for (int i = 0; i < iterations; i++) {
            value ^= (value << 7);
            value ^= (value >>> 9);
            value *= 0x9E3779B97F4A7C15L;
        }

        return value;
    }
}
```

MVC can call this function directly. WebFlux can run a long CPU task on an appropriate scheduler:

```java
@GetMapping("/cpu")
Mono<Long> cpu(@RequestParam(defaultValue = "1000000")
               int iterations) {
    return Mono.fromSupplier(
            () -> CpuWork.calculate(iterations))
            .subscribeOn(Schedulers.parallel());
}
```

This snippet requires importing Reactor `Mono` and `Schedulers`. `Schedulers.parallel()` worker count depends on config/CPU; record it and do not arbitrarily raise workers past core count. If the task is tiny, scheduler handoff may cost more than the computation itself; benchmark both inline and offloaded paths against clear targets.

### 8.3. Mixed Workloads

A request might wait 80 ms on HTTP, compute for 3 ms, and serialize for 1 ms. In this case:
- The threading model affects waiting behavior.
- CPU work affects event loops/carriers/workers.
- Pool sizes cap concurrent requests to dependencies.
- Queues and buffers affect tail latency.

Change one variable per run. For example, raising pool concurrency and arrival rate simultaneously makes it hard to tell what caused throughput to change.

## 9. Virtual Threads: Specific Conditions and Pitfalls

### 9.1. Do Not Pool Virtual Threads Like Platform Threads

Virtual threads are designed for one thread per task. Do not create fixed thread pools to reuse virtual threads. If you need to cap concurrent requests to a dependency, use an appropriate concurrency limiter such as a Semaphore, bulkhead, or connection pool.

Example:

```java
Semaphore permits = new Semaphore(20);

String callDependency() throws InterruptedException {
    permits.acquire();
    try {
        return blockingClientCall();
    } finally {
        permits.release();
    }
}
```

This snippet illustrates capping concurrent calls at 20. In production, handle interruption, permit wait timeouts, and guaranteed permit release. If using a database connection pool, the pool already acts as a resource cap; do not add a redundant semaphore without reason.

### 9.2. Pinning

On certain JDK versions, a virtual thread can become pinned to its carrier when performing blocking operations inside `synchronized` blocks or native/foreign calls. Prolonged or frequent pinning can reduce scalability.

Check via:
- JFR event `jdk.VirtualThreadPinned`.
- Thread dumps/JFR.
- Profiling on the exact production JDK.

Pinning behavior varies across JDK versions; do not extrapolate a Java 21 result to Java 24+ without re-measuring.

### 9.3. ThreadLocal

Virtual threads support `ThreadLocal`, yet virtual thread counts can grow very large. Avoid caching heavy objects in `ThreadLocal` as often done with a small platform-thread pool. Per-virtual-thread `ThreadLocal` contexts can raise allocations/memory usage.

### 9.4. Blocking Must Still Be Bounded

Virtual threads make blocking easier to scale, not dependencies infinite. You still need:
- Per-downstream call timeouts.
- Overall request deadlines.
- Bounded connection pools.
- Bulkheads/concurrency limits.
- Per-tenant/service rate limits.
- Conditional retries and idempotency.
- Cancellation and cleanup.

## 10. WebFlux: Specific Conditions and Pitfalls

### 10.1. Do Not Block the Event-Loop

Never call synchronous JDBC/JPA, `Thread.sleep`, `block()`, or blocking file/network I/O directly on the event-loop. One blocking operation can stall the event-loop from serving many other connections.

If you must call legacy blocking code:

```java
Mono<Result> result = Mono.fromCallable(
        () -> legacyBlockingService.load(id))
        .subscribeOn(Schedulers.boundedElastic());
```

This isolates blocking work; it does not turn a blocking library reactive. `boundedElastic` has worker/queue limits; size and configure it per dependency rather than treating it as an infinite queue.

### 10.2. Backpressure Is Not an Automatic Memory Cap

Reactive Streams demand regulates items between Publisher and Subscriber, yet operator prefetch, `flatMap` concurrency, buffers, codecs, connection pools, and the network stack still have queues. Identify every buffer and its bound.

### 10.3. Do Not Benchmark with `Flux.just` and Draw Conclusions About I/O

An endpoint returning only `Flux.range` or `Mono.just` does not measure scaling while waiting on databases/networks. It primarily measures routing, serialization, schedulers, and framework overhead.

### 10.4. Do Not Rewrite an Entire App to WebFlux If Dependencies Remain Blocking

If most workloads rely on blocking JDBC/JPA and synchronous libraries, WebFlux may have to offload continuously onto `boundedElastic`. MVC + virtual threads may offer a simpler code model. Compare on real workloads rather than picking based on the word "reactive" in return types.

## 11. Database Benchmarks: JDBC, Virtual Threads, and R2DBC

This is a separate problem from an outbound HTTP stub.

A DB benchmark must hold constant:
- Same database engine/version.
- Same schema, indexes, data, and query plans.
- Same transaction isolation.
- Same read/write ratio.
- Same pool max connections and timeouts.
- Same cache warm/cold state.
- Same number of database nodes and CPU/memory.

Typical variants:
- MVC + JDBC on platform threads.
- MVC + JDBC on virtual threads.
- WebFlux + R2DBC.

**Limitation:** JDBC and R2DBC are different drivers/APIs. Even with identical queries and databases, serialization, protocol handling, pooling, and driver implementations differ. Results compare two end-to-end data access stacks, not an isolated measurement of thread models alone.

Never run blocking JDBC directly on the WebFlux event-loop. To benchmark legacy JDBC inside WebFlux, offload onto `boundedElastic` and clearly report it as a blocking-adapter variant.

The database connection pool is a real resource cap. If the pool has 40 connections, 4,000 virtual threads or 4,000 reactive subscribers do not turn that into 4,000 concurrent queries.

## 12. Reliable Benchmarking Methodology

### 12.1. Warm-Up

The JVM needs time for:
- Class loading.
- JIT compilation.
- Connection pool initialization.
- DNS/TLS/session setup.
- Cache population.
- Spring initialization.

Warm-up must be excluded from steady-state measurements. Use the exact same warm-up duration across every variant—for example, 3–5 minutes or until throughput/CPU/latency stabilize.

### 12.2. Measurement and Repetition

A practical protocol:
1. Deploy one variant in a clean environment.
2. Wait for health/readiness.
3. Warm up at a fixed load.
4. Run a low arrival-rate stage.
5. Step up stages until saturation or SLO failure.
6. Collect metrics/logs/JFR.
7. Stop the app and restart cleanly.
8. Repeat at least three times.
9. Alternate variant order to reduce bias from caches, host thermals, or background load.
10. Aggregate median and variance across runs.

Never make architectural conclusions from a single run.

### 12.3. Measure at Steady State

Exclude the first few seconds of startup or load ramps from steady-state numbers. For each stage, record:
- Offered rate.
- Achieved throughput.
- Latency distribution.
- Errors/timeouts.
- CPU/memory.
- Connections/queues.
- Dropped iterations.

If the generator cannot sustain the offered rate, that stage is invalid for comparison.

### 12.4. Coordinated Omission

A closed-loop generator sending the next request only after the previous response omits time during which real users would keep submitting requests. When the server slows down, the generator throttles itself and can make tail latency look artificially low.

An arrival-rate model makes offered load explicit. Still monitor whether the generator runs short on VUs or drops iterations.

## 13. Reading Results and Finding Saturation

Illustrative example table (synthetic numbers to show how to read results, **not real benchmark data**):

| Variant | Offered req/s | Completed req/s | p95 | Error rate | CPU |
| --- | ---: | ---: | ---: | ---: | ---: |
| MVC platform | 500 | 470 | 420 ms | 1.0% | 75% |
| MVC virtual | 500 | 498 | 210 ms | 0.1% | 73% |
| WebFlux | 500 | 500 | 180 ms | 0.0% | 71% |

Do not read this table as claiming WebFlux is always best. In this illustration, WebFlux shows lower p95 at one specific load; you must inspect multiple stages, p99, memory, error rates, downstream pools, and repeated runs before concluding.

### 13.1. Spotting Bottleneck Signals

- CPU at 100%, flat throughput: CPU-bound or allocation/serialization; adding concurrency may worsen latency.
- Low CPU, high latency, many pending connection acquires: dependency pool or slow downstream.
- MVC platform busy threads at max and growing queue: request thread capacity or blocking waits.
- MVC virtual with many virtual threads yet flat throughput: dependency/database cap, CPU, or semaphore/connection pool.
- WebFlux event-loop pending tasks rising: likely event-loop blocking or overly long CPU work.
- Heap/direct memory climbing continuously: buffers/queues/retained objects or leaks; reactive is not automatically memory-bounded.
- Errors/timeouts rising with arrival rate: system exceeded capacity or misconfigured deadlines.
- Dropped iterations rising: load generator failed to sustain offered load; stage results need investigation.

### 13.2. Comparing Throughput Within the Same SLO

A sound method is finding the maximum throughput that still satisfies the SLO:
- Error rate below threshold.
- p95/p99 below threshold.
- Memory not growing unboundedly.
- Dependencies remaining within allowed capacity.
- No runaway queues.

This is far more operationally meaningful than "highest RPS before the process crashes."

## 14. Observability Tools

### 14.1. Spring Boot Actuator and Micrometer

Expose required endpoints on internal/test networks:

```properties
management.endpoints.web.exposure.include=health,metrics,prometheus
```

If using Prometheus, add the corresponding registry dependency and secure metrics endpoints. Never expose `/actuator/prometheus` openly to the public internet.

Metrics should keep tag cardinality bounded; never put user IDs, order IDs, or URLs with dynamic IDs into tags.

### 14.2. Java Flight Recorder

JFR is useful for inspecting:
- CPU hot methods.
- Allocations and GC.
- Thread park/block/monitor contention.
- Socket reads/writes.
- Virtual thread pinning.
- Class loading and runtime events.

Start a recording:

```bash
java -XX:StartFlightRecording=filename=benchmark.jfr,duration=10m -jar app.jar
```

Analyze the file with JDK Mission Control or a suitable JFR tool. Apply the exact same recording policy across all variants because profiling has overhead.

### 14.3. Thread Dumps

For virtual threads, `jcmd` can produce JSON thread dumps on supported JDKs:

```bash
jcmd <pid> Thread.dump_to_file -format=json threads.json
```

This is an illustrative command; replace `<pid>` with the actual process ID. Compare thread dumps to see where tasks wait, rather than just counting threads to judge performance.

## 15. Common Benchmark Mistakes

| Mistake | Why Results Are Skewed | How to Fix |
| --- | --- | --- |
| Benchmarking only `Flux.just` | No real I/O or concurrency | Use production-like workloads |
| Using `Thread.sleep` on WebFlux event-loop | Blocks the event-loop, invalidating benchmark | Use real dependencies or `Mono.delay` for synthetic tests |
| Comparing MVC JDBC against WebFlux JDBC on event-loop | One variant violates WebFlux's model | Use R2DBC or explicit blocking offload |
| Running all three variants concurrently on one host | CPU/memory/cache contention | Run sequentially in identical environments |
| Using different JDKs | Different JIT/GC/virtual thread implementations | Pin the same JDK |
| Measuring only RPS | Ignores tail latency and errors | Measure p50/p95/p99, errors, and SLOs |
| Closed-loop load generator | Load drops when server slows | Use an arrival-rate model |
| Ignoring dropped iterations | Unknown whether generator sustained load | Record offered and achieved rates |
| Underpowered downstream stub | Benchmark measures stub instead of app | Monitor stub, scale capacity, or control load |
| Different connection pools | One variant gets more connections | Fix or explicitly report pools |
| Uneven warm-up | JIT/cache bias | Warm up with the same protocol |
| Running only once | Results skewed by noise | Repeat and swap run order |
| Not measuring GC/direct memory | Misses memory bottlenecks | Collect JFR, GC, and RSS/direct metrics |
| Enabling virtual threads without verifying | Variant may still run platform threads | Check threads/JFR/runtime |
| Raising virtual threads beyond DB pool | Queue waits climb while DB remains the cap | Bound concurrency per dependency |
| Testing only CPU-bound to pick a framework | Does not represent I/O-bound workloads | Separate workload types |
| Testing only localhost and concluding for production | Ignores proxies/TLS/networking | Test staging with real infrastructure |

## 16. Architecture Decision Matrix

| System Characteristic | First Option to Evaluate | Reason |
| --- | --- | --- |
| Existing MVC/JDBC app with many I/O-waiting requests | MVC + virtual threads | Can increase concurrency while keeping blocking code |
| Greenfield reactive API with WebClient/R2DBC and streaming | WebFlux | End-to-end non-blocking and backpressure |
| Predominantly CPU-bound | Measure all three; pick by simplicity/overhead | Threading models do not add CPU |
| Mostly blocking libraries | MVC platform or MVC virtual | Avoid constant blocking offload in WebFlux |
| Heavy streaming requests/responses | WebFlux | Reactive Streams and non-blocking streaming |
| Very small downstream connection pool | Either model, with bounded concurrency | Dependency is the bottleneck |
| Needs Servlet filters/container integration and ecosystem | Spring MVC | Servlet stack compatibility |
| Many I/O waits with readable synchronous code | MVC + virtual threads | Thread-per-request remains straightforward |
| Team experienced with Reactor and all-reactive dependencies | WebFlux | Leverages non-blocking, cancellation, and backpressure |
| Mixed workloads and legacy systems | Benchmark per service boundary | Different stacks can be chosen per service |

An organization does not have to standardize on one model everywhere. You can keep MVC for CRUD/JDBC, use WebFlux for gateways/streaming services, and enable virtual threads on suitable MVC apps.

## 17. Technical Findings to Include in a Benchmark Report

A reproducible report should contain:

1. Goal: throughput at a given SLO, latency, memory, or concurrency.
2. Models: MVC platform, MVC virtual, WebFlux; server connector and client connector.
3. Versions: JDK, Spring Boot, Spring Framework, Reactor, server, OS/container.
4. Hardware/resources: CPU, RAM, cgroup quotas, heap, GC.
5. Workload: I/O/CPU/mixed, payloads, dependency latency, data distribution.
6. Pools: HTTP, DB, executors, connections, concurrency limits.
7. Load: generator version, arrival-rate stages, duration, VUs, and dropped iterations.
8. Warm-up/measurement: protocol, repetition count, run order.
9. Results: offered/achieved RPS, p50/p95/p99, errors, CPU, memory, GC, queues.
10. Bottleneck: CPU, event loop, worker threads, pools, database, or network.
11. Trade-offs: code complexity, observability, operational cost, and migration.
12. Limitations: what was not benchmarked and what assumptions remain unverified.

Never write "WebFlux is 30% faster" from testing one localhost endpoint. Specify the exact benchmark, load, environment, and run-to-run variance.

## 18. Pre-Selection Checklist for MVC, Virtual Threads, or WebFlux

- [ ] Classified workload as I/O-bound, CPU-bound, or mixed.
- [ ] Identified which dependencies dominate latency.
- [ ] Used the same JDK and framework versions.
- [ ] Held payloads, business logic, and security identical.
- [ ] Fixed or explicitly documented connection pools/executors.
- [ ] Verified the MVC virtual variant actually uses virtual threads.
- [ ] Verified WebFlux does not block the event-loop.
- [ ] Ran the load generator outside the server host with sufficient capacity.
- [ ] Used arrival-rate tests and monitored dropped iterations.
- [ ] Warmed up before measuring.
- [ ] Ran multiple load stages and multiple repetitions.
- [ ] Measured p50/p95/p99, errors, CPU, memory, and GC.
- [ ] Monitored queues, active connections, and downstream pools.
- [ ] Determined maximum throughput within the same SLO.
- [ ] Documented benchmark limitations without generalizing beyond the data.

## 19. Official References

- [Spring Boot 3.5 – Virtual Threads](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html): Java 21+, spring.threads.virtual.enabled, daemon threads and pinning notes.
- [Spring Boot 3.5 – Task Execution and Scheduling](https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html): auto-configured AsyncTaskExecutor and virtual-thread integration.
- [Spring Framework – Spring WebFlux](https://docs.spring.io/spring/reference/web/webflux.html): reactive stack, non-blocking I/O, Reactive Streams backpressure, coexistence with MVC.
- [Oracle Java 21 – Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html): virtual thread scheduling, I/O-bound use cases, CPU-bound limits, and pinning.
- [Oracle Java – JEP 444](https://openjdk.org/jeps/444): goals and semantics of virtual threads.
- [Spring Boot – Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Micrometer and runtime observability.
- [Spring Framework – WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): reactive HTTP client.
- [k6 – Constant Arrival Rate Executor](https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/constant-arrival-rate/): offered arrival rate model and VU configuration.
- [JDK Flight Recorder](https://docs.oracle.com/en/java/javase/21/jfapi/flight-recorder.html): recording and analyzing JVM events.

## 20. Key Takeaways

**No single model wins every workload.** MVC with platform threads is easy to integrate and fits moderate loads; MVC with virtual threads scales well for synchronous I/O-waiting code on Java 21+; WebFlux fits non-blocking chains, streaming, and backpressure when dependencies are also reactive.

A fair comparison keeps workload, dependencies, payloads, JDK, resources, timeouts, and offered load identical. Measure throughput alongside p95/p99, error rate, CPU, memory, GC, connection pools, and queues; run multiple repetitions after warm-up. Specifically, virtual threads scale I/O-waiting tasks rather than speeding up CPU execution, while WebFlux delivers its benefits only when the event-loop stays unblocked. Choose a stack based on saturation points under the same SLO, operational complexity, and real dependency capabilities.
