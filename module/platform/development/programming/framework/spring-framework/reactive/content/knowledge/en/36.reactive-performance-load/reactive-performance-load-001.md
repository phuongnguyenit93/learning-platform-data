# Measuring Latency, Throughput, Threads, and Memory in Spring WebFlux

**Module:** Spring Framework - reactive  
**Parent Topic:** Performance and Load  
**Lesson:** Measuring Latency, Throughput, Threads, and Memory

## Learning Objectives

After this lesson, you will be able to:

1. Design repeatable benchmarks and distinguish warm-up, ramp-up, steady state, and soak tests.
2. Read average, median, p90, p95, p99, and maximum latency; understand why percentiles matter more than a standalone average.
3. Measure throughput and concurrency, and distinguish offered load from actually completed requests.
4. Use Little's Law to relate throughput, latency, and in-flight requests.
5. Choose an open-loop or closed-loop load model based on the testing goal.
6. Measure Java threads, thread states, heap, non-heap, direct memory, process RSS, CPU, and GC.
7. Use Micrometer/Actuator, Prometheus, k6, JFR, jcmd, jstat, and JMH.
8. Understand the WebFlux event-loop and identify blocking calls that stall workers.
9. Build a Spring Boot 3.3.5 application with fast, delay, and CPU-bound endpoints.
10. Read k6 p95/p99, request rate, VUs, and dropped iterations; avoid false conclusions caused by the load generator or environment.

## 1. Performance Is Multidimensional

An endpoint may respond fast with a single request yet become slow under hundreds of concurrent requests. One system may achieve high throughput with poor tail latency; another may have a low p50 yet low completed requests per second.

Four groups must be measured simultaneously:

- **Latency:** the duration of an operation from the caller's perspective.
- **Throughput:** the number of operations completed per unit of time.
- **Concurrency and threads:** the number of in-flight operations, thread count, and thread states.
- **Memory and GC:** heap, direct memory, RSS, allocation rate, and garbage collection.

As concurrency increases, throughput typically rises up to a point. Beyond the saturation point, queues grow longer, p95/p99 rise, and timeouts increase while throughput may plateau. CPU is not the only bottleneck: connection pools, the event-loop, databases, locks, or upstream services can also become congested.

Before measuring, define clearly: which component is measured; whether timing runs from sending the request to headers or the end of the body; which workload and payload are used; and what the success criteria are. Without defined measurement boundaries, two latency numbers may not be comparable.

## 2. Latency: Look at the Distribution, Not Just the Average

| Metric | How to Read | Meaning |
| --- | --- | --- |
| **p50 / median** | 50% of requests complete at or before this value | Typical experience. |
| **p90** | 90% of requests are no slower than this value | Slow request tier. |
| **p95** | 95% of requests are no slower than this value | Tail latency commonly used for SLAs. |
| **p99** | 99% of requests are no slower than this value | Slowest 1% of requests. |
| **max** | The slowest request | Sensitive to outliers and sample size. |
| **average** | Total latency divided by request count | Useful, but can hide the tail. |

Illustrative example, not a benchmark result: p50 = 20 ms, p95 = 120 ms, p99 = 900 ms. The median looks good, yet the slowest 1% of requests take nearly a second. In a chain of sequential service calls, the tail latency of one dependency can stretch the entire request.

When reporting, record sample request count, measurement duration, p50/p90/p95/p99, error rate, timeout count, and whether latency is measured up to headers or the full response body.

### 2.1. HTTP Metrics in k6

- `http_req_duration`: time spent sending the request, waiting for the response, and receiving the response body; excludes blocked, connecting, and TLS handshake time.
- `http_req_waiting`: time spent waiting for the response (time to first byte).
- `http_req_sending` and `http_req_receiving`: time spent sending and receiving data.
- `http_req_blocked`: time spent waiting before starting to send, which may include waiting for a connection slot.
- `http_req_connecting`: TCP connection establishment time.
- `http_req_tls_handshaking`: TLS handshake time.

If `http_req_duration` increases, inspect waiting, receiving, and connecting to pinpoint the slow phase. Status 200 alone does not prove the body was fully read if the connection is dropped mid-stream.

## 3. Throughput, Concurrency, and Little's Law

Throughput is the number of operations completed per unit of time:

\[
\text{throughput} =
\frac{\text{completed operations}}{\text{measurement duration}}
\]

For example, 60,000 completed requests in 60 seconds equals 1,000 req/s. This is only an illustrative calculation; a real benchmark must use the number of requests actually completed and report errors/drops.

Distinguish between:

- **Offered load:** the rate at which the generator attempts to send requests.
- **Started requests:** requests that have been initiated.
- **Completed throughput:** completed requests per second.
- **Successful throughput:** successfully completed requests per second.
- **Error rate:** proportion of failed requests.

If the generator targets 1,000 req/s but only 600 req/s complete, you cannot report that the system achieved 1,000 req/s.

### 3.1. Little's Law

In a stable system:

\[
L = \lambda W
\]

`L` is the average number of in-flight operations; `λ` is the average throughput (operations/second); `W` is the average time an operation spends in the system (seconds).

Example:

\[
L = 200 \times 0.1 = 20
\]

With a throughput of 200 req/s and an average duration of 0.1 seconds, there are approximately 20 in-flight requests on average. If duration increases to 0.5 seconds while throughput stays constant, average concurrency rises to around 100.

Little's Law applies only when the system is stable and all quantities are measured across the same boundary.

## 4. Open-Loop and Closed-Loop Load

**Closed-loop:** a VU sends a request, waits for the response, and only then sends the next one. If the server slows down, the load generation rate drops automatically. This model suits simulating interactive users, but can mask queueing when the system is overloaded.

**Open-loop:** the generator issues requests according to a predetermined arrival rate, independent of response time. This model suits testing processing capacity at a fixed request arrival rate. If there are not enough VUs to keep up with the schedule, the dropped iterations metric increases.

In k6, `constant-arrival-rate` is an open-model executor. Common test types:

- Ramp-up: gradually increase load.
- Steady-state: hold stable load for measurement.
- Spike: abruptly increase the arrival rate.
- Stress: push load past expected levels to find the breaking point.
- Soak: sustain load for a long duration to detect leaks, memory drift, and degradation.

State the load model explicitly. Do not compare open-loop and closed-loop throughput as if under identical conditions.

## 5. Threads and Event-Loop in WebFlux

WebFlux with Reactor Netty uses non-blocking I/O. A request waiting on I/O does not need to hold a dedicated Java thread as in the thread-per-request model. Many requests can share event-loop worker threads.

This does not mean WebFlux cannot stall:

- Synchronous JDBC/file I/O, `Thread.sleep`, or `block()` blocks the event-loop.
- Long-running CPU-bound work on the event-loop slows down other requests.
- `Schedulers.parallel()` and `Schedulers.boundedElastic()` have their own pools.
- Drivers, logging, and native libraries can create additional threads.

Metrics to observe:

| Metric | Meaning |
| --- | --- |
| `jvm.threads.live` | Number of live Java threads. |
| `jvm.threads.peak` | Peak live Java thread count. |
| `jvm.threads.states` | Thread count by state. |
| Thread dump | Stack traces and states at capture time. |
| OS process threads | Number of native threads of the process. |

Thread count alone does not indicate good or bad performance. Compare under the same workload: does thread count grow continuously, are many threads BLOCKED, and do stack traces repeat at a lock or blocking call?

### 5.1. Do Not Block the Event-Loop

Example to avoid:

```java
@GetMapping("/bad")
public Mono<String> bad() {
    return Mono.just(blockingDatabaseCall());
}
```

`blockingDatabaseCall()` runs immediately when the method is called, before the Mono is returned, so it can block the event-loop.

If you must call a legacy blocking API:

```java
@GetMapping("/legacy")
public Mono<String> legacy() {
    return Mono.fromCallable(this::blockingDatabaseCall)
            .subscribeOn(Schedulers.boundedElastic());
}
```

This isolates the blocking workload; it does not turn JDBC into reactive I/O and does not create a shared transaction with R2DBC. You should bound concurrency and monitor the scheduler's queue/threads. For CPU-bound work, use a suitable CPU pool such as `Schedulers.parallel()`.

## 6. Memory: Heap, Direct Buffer, and RSS

| Area | Contents | Metric/Tool |
| --- | --- | --- |
| Heap | Java objects, collections, DTOs, caches | `jvm.memory.used`, `jvm.memory.max` |
| Non-heap | Metaspace, code cache, and other JVM regions | `jvm.memory.used` by area |
| Direct buffer | Off-heap buffers used for I/O | `jvm.buffer.memory.used`, `jvm.buffer.count` |
| Native memory | Thread stacks, native libraries, JVM internals | NMT, OS tools |
| Process RSS/working set | Resident memory pages of the process | OS process monitor |
| Container memory | Memory accounted by cgroup/runtime | Container metrics |

Heap used is not total process RAM. RSS also includes direct buffers, thread stacks, metaspace, native libraries, and memory mappings. Heap committed can exceed heap used because the JVM retains allocated regions for reuse.

Track heap before/after GC, GC count/pause, allocation rate, old-generation growth, direct buffers, and RSS. A single snapshot is insufficient to conclude a memory leak; observe trends across multiple workload cycles.

### 6.1. JDK Tools

Find the application's PID, then run:

```bash
jcmd <PID> Thread.print
jcmd <PID> GC.heap_info
jstat -gcutil <PID> 1000 10
```

`Thread.print` outputs stack traces; `GC.heap_info` displays heap details; `jstat -gcutil` samples GC regions every 1,000 ms, 10 times.

Record Java Flight Recorder during load:

```bash
jcmd <PID> JFR.start name=webflux-load settings=profile duration=60s filename=webflux-load.jfr
```

Open the file with Java Mission Control to inspect CPU, allocation, GC, lock contention, thread, and I/O events.

To inspect native memory, Native Memory Tracking must be enabled at startup:

```bash
java -XX:NativeMemoryTracking=summary -jar app.jar
jcmd <PID> VM.native_memory summary
```

NMT has overhead and cannot be enabled retroactively on a running process. On Windows PowerShell:

```powershell
Get-Process -Id <PID> |
    Select-Object Id, CPU, WorkingSet64, PrivateMemorySize64, Threads
```

`WorkingSet64` is the resident working set; `PrivateMemorySize64` is private memory. They do not map directly to heap used.

## 7. Micrometer and Spring Boot Actuator

Actuator provides health/metrics endpoints; Micrometer collects JVM, process, and HTTP server metrics. Add the Prometheus registry for scraping.

Useful metrics include `http.server.requests`, `jvm.threads.live`, `jvm.threads.peak`, `jvm.threads.states`, `jvm.memory.used`, `jvm.memory.max`, `jvm.buffer.memory.used`, `jvm.gc.pause`, `process.cpu.usage`, and `system.cpu.usage`. Do not assume every driver/pool exports the same metric names; inspect the actual endpoint.

### 7.1. application.properties

```properties
spring.application.name=webflux-performance-lab
server.port=8080

management.endpoints.web.exposure.include=health,info,metrics,prometheus
management.endpoint.health.show-details=never
management.metrics.tags.application=webflux-performance-lab
management.metrics.distribution.percentiles-histogram.http.server.requests=true
```

Expose metrics/prometheus only on an internal management network or protect them with an appropriate security policy.

### 7.2. Reading Metrics

```bash
curl http://localhost:8080/actuator/health
curl http://localhost:8080/actuator/metrics/jvm.threads.live
curl http://localhost:8080/actuator/metrics/jvm.memory.used
curl http://localhost:8080/actuator/metrics/jvm.buffer.memory.used
curl http://localhost:8080/actuator/prometheus
```

The `metrics/{name}` endpoint returns measurements and tags. Prometheus names are normalized, such as `jvm_threads_live_threads` or `jvm_memory_used_bytes`. Inspect the live endpoint before building dashboards.

## 8. Repeatable Benchmark Process

1. **Fix the environment:** record commit, JDK, Spring Boot/Reactor, CPU/RAM, OS, container limits, JVM flags, GC, dependencies, pools, and the load generator machine.
2. **Define the workload:** route mix, payload/response size, warm/cold cache, arrival rate/VUs, error budget, latency SLO, and memory ceiling.
3. **Warm-up:** wait for class loading, JIT, connection pools, and caches to stabilize; measure cold start separately if needed.
4. **Ramp-up:** increase load in steps and observe CPU, latency, throughput, and queues.
5. **Steady-state:** hold a fixed load long enough to obtain a representative sample.
6. **Soak:** run for an extended period (e.g., 30–60 minutes or per target) to uncover memory drift, thread growth, pending acquires, and GC pauses.
7. **Repeat:** run multiple iterations under identical conditions and report variance; do not cherry-pick the best run.
8. **Change one factor at a time:** pool size, scheduler, payload, or serialization. Changing multiple factors at once makes it impossible to know which one caused the difference.

Do not run for a few seconds and draw conclusions about p99. For long tests, verify that the load generator does not become the bottleneck.

## 9. k6: Measuring HTTP Latency and Throughput

Create `load.js`:

```javascript
import http from "k6/http";
import { check } from "k6";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8080";
const PATH = __ENV.SCENARIO_PATH || "/bench/delay?ms=20";

export const options = {
  scenarios: {
    steady_arrival: {
      executor: "constant-arrival-rate",
      rate: 100,
      timeUnit: "1s",
      duration: "60s",
      preAllocatedVUs: 50,
      maxVUs: 200
    }
  },
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<250", "p(99)<500"],
    dropped_iterations: ["count==0"],
    checks: ["rate>0.99"]
  }
};

export default function () {
  const response = http.get(BASE_URL + PATH);
  check(response, {
    "HTTP status is 200": (r) => r.status === 200
  });
}
```

The generator attempts to start 100 iterations/second for 60 seconds; it allocates 50 initial VUs and can scale up to 200. `dropped_iterations` must be monitored; if it increases, the generator is not issuing enough workload on schedule. The p95/p99 and error rate thresholds here are examples and must be replaced with your real SLOs.

Start the app first, then run:

```bash
k6 run -e BASE_URL=http://localhost:8080 load.js
k6 run -e BASE_URL=http://localhost:8080 -e SCENARIO_PATH=/bench/fast load.js
k6 run -e BASE_URL=http://localhost:8080 -e SCENARIO_PATH=/bench/cpu?iterations=100000 load.js
k6 run --summary-export=summary.json load.js
```

k6 reports `http_reqs`, `http_req_duration`, `http_req_failed`, `vus`, `vus_max`, `iterations`, `dropped_iterations`, and data transfer. Read the actual request rate and percentiles from the summary; do not copy the target rate as actual throughput.

If generator CPU hits 100%, VUs climb sharply, or dropped iterations rise while the server still has headroom, run the generator on another machine, add resources, or distribute the load. Monitor CPU, memory, and network on both the generator and the server.

## 10. Spring Boot 3.3.5 Project for Measuring WebFlux

The demo provides three workloads:

- `/bench/fast`: small response, no intentional delay.
- `/bench/delay?ms=20`: asynchronous wait using `Mono.delay`; this is a logical delay, not network latency.
- `/bench/cpu?iterations=100000`: bounded CPU computation on `Schedulers.parallel()` to avoid running long loops on the Netty event-loop.

### 10.1. Structure

```text
webflux-performance-lab/
├── pom.xml
└── src/main/
    ├── java/demo/
    │   ├── PerformanceLabApplication.java
    │   ├── BenchResult.java
    │   └── BenchController.java
    └── resources/application.properties
load.js
```

### 10.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>webflux-performance-lab</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-registry-prometheus</artifactId>
            <scope>runtime</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

The Spring Boot parent manages compatible versions of Spring Framework, Reactor, and Micrometer.

### 10.3. PerformanceLabApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PerformanceLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(PerformanceLabApplication.class, args);
    }
}
```

### 10.4. BenchResult.java

```java
package demo;

public record BenchResult(
        String scenario,
        long value,
        long elapsedNanos,
        String executingThread) {
}
```

`elapsedNanos` only measures the illustrative operation inside the handler, not end-to-end HTTP latency; caller latency is measured by k6.

### 10.5. BenchController.java

```java
package demo;

import java.time.Duration;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@RestController
@RequestMapping("/bench")
public class BenchController {

    @GetMapping("/fast")
    public Mono<BenchResult> fast() {
        long started = System.nanoTime();
        return Mono.fromSupplier(() -> new BenchResult(
                "fast", 1L, System.nanoTime() - started,
                Thread.currentThread().getName()));
    }

    @GetMapping("/delay")
    public Mono<BenchResult> delay(
            @RequestParam(defaultValue = "20") long ms) {
        if (ms < 0 || ms > 5000) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "ms must be from 0 to 5000");
        }
        long started = System.nanoTime();
        return Mono.delay(Duration.ofMillis(ms))
                .map(ignored -> new BenchResult(
                        "delay", ms, System.nanoTime() - started,
                        Thread.currentThread().getName()));
    }

    @GetMapping("/cpu")
    public Mono<BenchResult> cpu(
            @RequestParam(defaultValue = "100000") int iterations) {
        if (iterations < 1 || iterations > 2_000_000) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "iterations must be from 1 to 2000000");
        }
        return Mono.fromCallable(() -> {
                    long started = System.nanoTime();
                    long value = 0x9E3779B97F4A7C15L;
                    for (int i = 0; i < iterations; i++) {
                        value = Long.rotateLeft(value ^ i, 13)
                                * 0xC2B2AE3D27D4EB4FL;
                    }
                    return new BenchResult(
                            "cpu", value, System.nanoTime() - started,
                            Thread.currentThread().getName());
                })
                .subscribeOn(Schedulers.parallel());
    }
}
```

`Mono.fromSupplier` runs upon subscription. `Mono.delay` does not block threads while waiting. `/cpu` uses the parallel scheduler for a synthetic CPU workload; it does not represent a specific business algorithm. Parameters are bounded to prevent a single request from asking for too many iterations. The thread name in the response is purely diagnostic, not a process thread count.

### 10.6. application.properties

```properties
spring.application.name=webflux-performance-lab
server.port=8080
management.endpoints.web.exposure.include=health,info,metrics,prometheus
management.endpoint.health.show-details=never
management.metrics.tags.application=webflux-performance-lab
management.metrics.distribution.percentiles-histogram.http.server.requests=true
```

### 10.7. Build, Run, and Smoke Test

```bash
mvn clean package
mvn spring-boot:run
```

In another terminal:

```bash
curl -i http://localhost:8080/bench/fast
curl -i "http://localhost:8080/bench/delay?ms=20"
curl -i "http://localhost:8080/bench/cpu?iterations=100000"
curl http://localhost:8080/actuator/metrics/jvm.threads.live
curl http://localhost:8080/actuator/metrics/jvm.memory.used
```

A response has the following structure (values are illustrative only, not baseline measurements):

```json
{
  "scenario": "delay",
  "value": 20,
  "elapsedNanos": 21000000,
  "executingThread": "parallel-1"
}
```

Do not use illustrative elapsedNanos values or thread names as a baseline. Real results depend on the scheduler, JIT, CPU, and load.

## 11. JMH: Microbenchmarks Differ from Load Tests

k6 measures end-to-end HTTP; JMH is suited for comparing pure Java transformations. JMH handles warm-up, forking, and measurement iterations better than a hand-written `System.nanoTime` loop.

Standalone benchmark example (requires JMH dependency and annotation processor in a benchmark module; not part of the WebFlux project in section 10):

```java
import java.util.Arrays;
import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.*;

@State(Scope.Thread)
@BenchmarkMode(Mode.Throughput)
@OutputTimeUnit(TimeUnit.SECONDS)
@Warmup(iterations = 5, time = 1)
@Measurement(iterations = 8, time = 1)
@Fork(2)
public class MappingBenchmark {
    @Param({"100", "1000"})
    int size;
    private int[] values;

    @Setup(Level.Trial)
    public void setup() {
        values = new int[size];
        for (int i = 0; i < size; i++) values[i] = i;
    }

    @Benchmark
    public long imperativeSum() {
        long sum = 0;
        for (int value : values) sum += value;
        return sum;
    }

    @Benchmark
    public long streamSum() {
        return Arrays.stream(values).asLongStream().sum();
    }
}
```

Read throughput and error margin across each fork/iteration; do not pick the single best iteration. Do not benchmark WebFlux by creating a Mono and calling `block()` in a loop and calling that reactive server throughput. For end-to-end HTTP use k6; for isolated CPU functions use JMH.

## 12. Interpreting Results and Finding Bottlenecks

- **Latency increases while throughput still increases:** the system may be approaching saturation; check in-flight count, queues, CPU, event-loop, and downstream services.
- **Latency increases while throughput plateaus:** CPU, connection pool, database, locks, or GC may have reached their limit.
- **Low CPU yet high latency:** requests may be waiting on I/O, pool acquire, locks, scheduler queues, or remote services; inspect thread dumps and tracing.
- **Thread count grows over time:** look for per-request Executor/scheduler creation, thread-per-task, uncanceled timers/subscriptions, or clients that are not reused.
- **Stable heap yet rising RSS:** check direct buffers, native memory, thread stacks, memory mappings, NMT, and process metrics.
- **Poor p99 with stable p50:** check GC pauses, allocation bursts, slow downstream services, retry storms, large payloads, TLS/connection creation, and lock contention.

Do not increase thread or pool sizes before having evidence of the bottleneck; raising limits may merely shift pressure onto the database or CPU.

## 13. Benchmark Report Template

| Attribute | Recorded Value |
| --- | --- |
| Commit / build | SHA or version |
| JDK / Spring Boot | Actual version |
| CPU / RAM / container limit | Specs of machine running the app |
| Workload | Routes, payload, request mix |
| Load model | Open-loop or closed-loop |
| Target arrival rate | req/s |
| Completed requests | Actual total |
| Successful throughput | successful req/s |
| p50 / p95 / p99 | ms |
| Error / timeout rate | % and count |
| Dropped iterations | Number of dropped iterations |
| VUs / in-flight | Values during measurement window |
| JVM live / peak threads | Thread count |
| Heap / direct buffer / RSS | MB |
| CPU / GC pause | % and ms |
| Warm-up / steady / soak | Duration |
| Bottleneck | Evidence and hypothesis |

Leave unmeasured numbers blank. A p95 figure without workload, sample count, environment, and error rate is nearly impossible to compare reliably.

## 14. Common Pitfalls

| Pitfall | Why It Is Wrong | How to Handle |
| --- | --- | --- |
| Reporting only average latency | Hides very slow requests | Report p50/p95/p99 and sample count. |
| Using target arrival rate as throughput | Requests may drop/timeout | Read completed request and error metrics. |
| Too-short tests | Insufficient warm-up, misses leaks/GC | Separate warm-up, steady-state, and soak. |
| Comparing machines with different specs | Noise from CPU/RAM/JDK/limits | Fix and record the environment. |
| Not tracking dropped_iterations | Generator is not issuing full load | Increase resources/VUs or distribute the generator. |
| Calling block/sleep on the event-loop | Blocks I/O workers | Use non-blocking APIs or the proper scheduler. |
| Immediately adding threads when latency rises | May increase contention/context switches | Check thread dumps and metrics first. |
| Looking only at heap | Ignores native/direct memory and RSS | Track buffers, NMT, and process memory. |
| Using Mono.delay to conclude TCP is slow | Delay occurs after the request reaches the handler | Use a network fault proxy for transport testing. |
| Using a single System.nanoTime call | JIT/GC/scheduler noise skews results | Use JMH or repeated load tests. |
| Running app and generator on a weak machine | Both processes contend for CPU/network | Separate machines or verify generator headroom. |
| Enabling wiretap/body logging during benchmarks | Logging alters workload and can leak data | Disable debug logs or measure overhead separately. |
| Changing multiple parameters at once | Cannot tell which factor improved performance | Change one factor at a time. |

## 15. Self-Check Questions

**Question 1.** What does p95 = 200 ms mean?  
**Answer:** Roughly 95% of sampled requests had latency no greater than 200 ms; the remaining 5% were slower.

**Question 2.** Does 500 req/s throughput mean the generator sent 500 req/s?  
**Answer:** No. Throughput is the completion rate; offered arrival rate is the intended sending rate.

**Question 3.** What does Little's Law express?  
**Answer:** In a stable system, average concurrency L equals throughput λ multiplied by average duration W: L = λW.

**Question 4.** How does open-loop differ from closed-loop?  
**Answer:** Open-loop maintains an arrival schedule independent of response latency; closed-loop typically waits for a response to finish before sending the next request.

**Question 5.** Why does WebFlux not create a thread per request?  
**Answer:** It uses non-blocking I/O and an event-loop; many requests can share workers while waiting on I/O.

**Question 6.** Why is calling blocking JDBC on the event-loop dangerous?  
**Answer:** It occupies the thread handling I/O and delays other requests on that event-loop.

**Question 7.** How does heap used differ from RSS?  
**Answer:** Heap used covers objects in the Java heap; RSS also includes direct buffers, native memory, thread stacks, and other process regions.

**Question 8.** Which metrics help observe thread counts?  
**Answer:** `jvm.threads.live` and `jvm.threads.peak`; thread dumps help find stack traces and states.

**Question 9.** Which tool measures HTTP throughput and p95/p99?  
**Answer:** k6 or an equivalent load-testing tool; read the completed request rate and latency distribution.

**Question 10.** Should you use JMH or k6 to measure a Java collection transformation function?  
**Answer:** JMH for function microbenchmarks; k6 for end-to-end HTTP.

**Question 11.** Why is a soak test needed?  
**Answer:** To detect leaks, thread growth, memory drift, GC, and pool degradation that only appear after extended duration.

**Question 12.** What can cause low CPU yet high p99?  
**Answer:** Waiting on I/O, pool acquire, locks, scheduler queues, remote dependencies, or GC.

## 16. Key Takeaways

- Measure **latency distribution, actual throughput, concurrency, threads, CPU, and memory** simultaneously.
- p95/p99 expose tail latency that averages or p50 can conceal.
- Little's Law connects concurrency, throughput, and latency in steady state.
- Open-loop maintains an arrival rate; closed-loop simulates users waiting for responses.
- WebFlux relies on the event-loop and non-blocking I/O; do not block the event-loop with JDBC, Thread.sleep, or block().
- Heap is not all of process memory; measure direct buffers, native memory, and RSS as well.
- Actuator/Micrometer observes JVM/HTTP; k6 generates load; JFR/jcmd/jstat analyze the runtime; JMH runs microbenchmarks.
- Warm-up, steady-state, soak, fixed workloads, and a sufficiently capable load generator are required for fair comparisons.
- Do not turn illustrative thresholds or a single run into an SLA.

## References

1. [Spring Boot 3.3 – Actuator Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html): Micrometer, JVM metrics, tags, and Prometheus.
2. [Spring Framework – WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html): non-blocking model and event-loop.
3. [Reactor Core – Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html): parallel, boundedElastic, and scheduler switching.
4. [k6 – Constant Arrival Rate Executor](https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/constant-arrival-rate/): open-model, VUs, and dropped iterations.
5. [k6 – Built-in Metrics](https://grafana.com/docs/k6/latest/using-k6/metrics/reference/): http_req_duration, waiting, sending, receiving, VUs, and request rate.
6. [k6 – Thresholds](https://grafana.com/docs/k6/latest/using-k6/thresholds/): pass/fail thresholds by percentile and error rate.
7. [Micrometer – JVM Metrics](https://docs.micrometer.io/micrometer/reference/reference/jvm.html): thread, memory, GC, and buffer metrics.
8. [OpenJDK JMH](https://github.com/openjdk/jmh): microbenchmarks, warmup, forks, and measurement.
9. [JDK 17 – jcmd](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): thread dumps, heap, JFR, and NMT.
10. [JDK 17 – jstat](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jstat.html): JVM/GC statistics.
11. [Java Flight Recorder](https://docs.oracle.com/en/java/javase/17/jfapi/): recording and analyzing runtime events.
