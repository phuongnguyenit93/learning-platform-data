# Load Testing and Evidence-Based Justification of Reactive Choices in Spring WebFlux

## 1. Goal: Choosing Architecture with Metrics

Spring WebFlux and Reactor provide an asynchronous, non-blocking, and backpressure-aware model. However, merely using `Mono`/`Flux` in an application does not automatically prove that it is faster, handles higher load, or consumes fewer resources than Spring MVC.

Choosing reactive must be tied to a testable hypothesis. For example:

- With high concurrency and mostly I/O wait time, WebFlux can maintain fewer worker threads because no dedicated thread needs to be held while waiting on network/database I/O.
- For CPU-bound workloads, reactive does not reduce computation; CPU limits remain core count, algorithms, and synchronization overhead.
- When downstreams are slow, reactive can propagate demand upstream and bound in-flight work, yet unbounded queues or excessive `flatMap` concurrency can still exhaust memory.
- For low traffic, simple apps, or mostly blocking libraries, MVC can be easier to develop and operate without significant performance penalties.

This practice guides you through load testing and writing evidence-based technical arguments instead of choosing reactive on intuition.

After this lesson, you can:

1. Formulate performance hypotheses for I/O-bound, CPU-bound, and mixed workloads.
2. Design measurements with clear baselines, workloads, environments, and success criteria.
3. Distinguish throughput, latency, concurrency, error rate, and saturation.
4. Use a load generator with an open workload model to send requests at a fixed arrival rate.
5. Read p50/p95/p99, dropped iterations, CPU, heap, GC, and thread counts.
6. Apply Little's Law to verify the relationship between throughput, latency, and in-flight requests.
7. Test a reactive WebFlux example against blocking work offloaded to `boundedElastic`.
8. Understand the limits of synthetic benchmarks and move to benchmarks with real downstreams.
9. Compare WebFlux and Spring MVC under fair conditions.
10. Write an architecture report with metrics, methodology, results, and interpretation limits.

The sample project uses Java 17, Spring Boot 3.3.5, Spring WebFlux, Actuator, Micrometer Prometheus, Reactor Test, and k6. The benchmark numbers in this lesson illustrate methodology; they are not measurements run on a specific machine.

## 2. When Is Reactive Beneficial?

Reactive is generally worth considering when a system performs substantial asynchronous I/O and must serve many concurrent operations.

### 2.1. I/O-Bound Workloads

A single request might accept an HTTP request, call two HTTP services, wait on a database, combine results, and return JSON. If both clients and drivers are non-blocking, the request thread does not sit idle waiting throughout network I/O. Reactor can keep serving other requests while awaiting signals.

This helps when:

- Concurrent connection counts are high.
- I/O wait time is large relative to CPU time.
- Multiple downstream calls can run in parallel.
- Streaming/backpressure is needed.
- The system must bound pending work.

### 2.2. CPU-Bound Workloads

Image encoding, compression, statistical computation, or heavy algorithmic processing still consume CPU even when written with `Flux`. Reactive does not turn a 20 ms computation into 2 ms. If CPU is already saturated, increasing concurrent requests may only raise queue depth and latency.

For CPU-bound workloads, focus on algorithms, core count, allocations/GC, lock contention, data size, and appropriate concurrency.

### 2.3. Blocking Workloads

If a request invokes blocking JDBC, `Thread.sleep`, synchronous SDKs, or blocking file APIs, a thread is held while waiting. You can offload blocking work off the event loop with `Schedulers.boundedElastic()`, yet threads are still needed to execute each blocking task. Bound workers/queues and evaluate reactive clients/drivers if overall gains justify the effort.

### 2.4. No Default Choice for Every Service

| Workload characteristic | Direction to consider |
|---|---|
| High concurrent I/O, non-blocking drivers | WebFlux/reactive has clear potential |
| Large streaming with backpressure needs | Reactive usually fits well |
| Low traffic, simple CRUD, blocking libraries | MVC may be simpler |
| Primarily CPU-bound | Profile algorithms/CPU first |
| Heavy reliance on blocking SDKs | Evaluate offloading cost or replacing SDKs |
| Low load, synchronous APIs | MVC can be a sensible choice |
| Mixed workloads | Measure each endpoint type and the whole system |

Do not use a single synthetic benchmark to decide an entire product's architecture.

## 3. Start with a Falsifiable Hypothesis

For example: for a workload spending mostly 100 ms in I/O wait up to 500 requests/second, non-blocking execution can keep thread usage steadier than blocking execution on a bounded pool while keeping p95 and error rates within target thresholds.

This hypothesis can be falsified if both approaches show similar latency/resource usage, reactive is bottlenecked by schedulers or downstreams, the blocking pool is large enough for the workload, the load generator cannot sustain the requested rate, or the bottleneck lies in CPU/serialization rather than I/O wait.

| Component | Question |
|---|---|
| Workload | I/O-bound, CPU-bound, or mixed? |
| Load | How many requests/second, how many concurrent clients? |
| Payload | Average and p95 request/response size? |
| Downstream | What are wait times and error rates? |
| Baseline | Which implementation are we comparing against? |
| Metrics | Which latency, throughput, CPU, heap, GC, and thread metrics are collected? |
| SLO | What are the maximum p95/p99 and error rates? |
| Stop condition | When is the system considered saturated? |

Do not pre-select the desired outcome. If MVC meets SLOs at lower cost and simpler code, that is also a valid conclusion.

## 4. Quantities to Measure

### 4.1. Throughput

Throughput is the number of requests or operations completed per unit of time, usually requests/second (RPS).

Distinguish:

- **Offered load**: the rate the load generator attempts to send.
- **Accepted/requested rate**: requests that actually reach the server.
- **Completed throughput**: requests that finish.
- **Successful throughput**: successful requests per second.

If offered load is 500 RPS but the generator drops iterations or the server returns errors, never report successful throughput as 500 RPS.

### 4.2. Latency and Percentiles

Latency is the time from sending a request until receiving the complete response.

- **p50**: half of requests have latency no greater than this value.
- **p95**: 95% of requests have latency no greater than this value.
- **p99**: 99% of requests have latency no greater than this value.

Averages can hide tail latency. Two systems with the same 120 ms average—one with p99 at 180 ms and the other with p99 at 2 seconds—deliver very different user experiences.

### 4.3. Error Rate

Measure HTTP 5xx, unexpected HTTP 4xx, timeouts, connection resets/refused, overload rejections, and unstarted load-generator iterations. Do not lump all errors into one number while losing error categories and root causes.

### 4.4. Resource Usage

| Metric | Meaning |
|---|---|
| CPU process/system | Compute capacity utilization |
| Heap used/committed | Java memory |
| GC pause/count | Garbage collection overhead |
| Live/peak thread count | Thread usage |
| Active connections | Open connections |
| In-flight requests | Requests currently in progress |
| Queue depth | Pending work |
| Network bytes | Inbound/outbound traffic |
| Connection pool pending | Tasks waiting for connections |
| Scheduler pending tasks | Tasks waiting on schedulers if instrumented |

A single metric is never enough to conclude. Low CPU with high latency may point to downstreams or queues; higher CPU with higher throughput can also be an acceptable trade-off.

## 5. Closed Workload vs. Open Workload

### 5.1. Closed Workload

A fixed number of virtual users continuously send a new request after the previous one finishes. When the system slows down, each user automatically sends fewer requests. This model fits a fixed set of interactive users, yet it can mask a server failing to keep up with expected arrival rates.

### 5.2. Open Workload

The load generator dispatches requests at a fixed arrival rate, such as 200 requests/second, regardless of how long prior responses take. This model is useful when you want to see how latency and errors behave if the system must absorb 200 requests/second.

In k6, you can use the `constant-arrival-rate` executor.

### 5.3. `dropped_iterations` Must Be Investigated

If k6 lacks enough VUs to launch iterations on schedule, `dropped_iterations` rises. Causes include overly slow application responses, insufficient `preAllocatedVUs`/`maxVUs`, CPU/network exhaustion on the k6 machine, or a saturated load generator.

Do not automatically blame `dropped_iterations` on the server. Inspect CPU and resources on the load generator host, and check whether requests actually reached the server.

## 6. Designing Fair Measurements

To compare reactive and blocking, hold other variables constant:

- Same business logic and response shape.
- Same payload size.
- Same downstream delay or real dataset.
- Same JDK and JVM options.
- Same CPU/memory limits.
- Same HTTP version, TLS, compression, and keep-alive.
- Same logging/metrics/tracing overhead.
- Same connection pool and timeout policies.
- Same load generator and network path.
- Same warm-up duration and measurement window.

Do not run both tests simultaneously on the same machine because they contend for CPU, heap, network, and schedulers. Run each workload independently, repeat multiple runs, and keep identical configurations.

A balanced ordering procedure:

1. Start the application and wait for stability.
2. Run warm-up.
3. Measure reactive.
4. Rest or reset state appropriately.
5. Measure blocking.
6. Swap the order on the next round to reduce thermal/JIT/cache bias.
7. Execute at least 3 runs with the same configuration.
8. Report the median across runs and preserve every raw result file.

If both endpoints live inside one JVM, they still share the HTTP server, event loops, heap, and CPU. That works for a demo lab, but is not equivalent to benchmarking two independent production architectures.

Do not change multiple variables at once. If you raise `flatMap` concurrency, resize heap, alter pool size, and change payload in the same run, you cannot tell which factor drove the outcome.

## 7. Recommended Experiment Procedure

1. **Build**: use the same commit/build; record JDK, Spring Boot, Reactor, and OS versions.
2. **Deploy**: run under identical CPU/memory limits, JVM heap, and environment.
3. **Warm-up**: send low traffic for 30–60 seconds so JIT and connection pools stabilize.
4. **Baseline**: measure very low traffic to establish baseline latency.
5. **Load steps**: test increasing arrival rates, e.g., 50, 100, 200, 400, 600 RPS.
6. **Steady state**: hold each step for 60–180 seconds after warm-up.
7. **Stress**: increase load until SLOs break, queues grow continuously, or error rates exceed thresholds.
8. **Recovery**: reduce load and observe whether queues/latencies return to normal.
9. **Repeat**: repeat at least 3 runs.
10. **Analyze**: aggregate p50/p95/p99, throughput, errors, CPU, memory, GC, threads, and dropped iterations.

These load levels are planning examples only; adjust to machine capacity, processing time, and actual SLOs.

## 8. Little's Law: Throughput, Latency, and Concurrency

Little's Law:

\[
L = \lambda W
\]

Where:

- \(L\): average number of requests in the system (in-flight).
- \(\lambda\): average throughput, requests/second.
- \(W\): average time in the system, in seconds.

For example, throughput of 300 requests/second and average latency of 0.1 seconds:

\[
L = 300 \times 0.1 = 30
\]

The average number of in-flight requests is roughly 30. If throughput stays constant while latency rises to 0.5 seconds, average in-flight requests climb to about 150.

The system must hold more concurrent requests; if each request holds buffers, objects, connections, or state, memory pressure can also rise.

Little's Law describes average relationships in a stable system; do not substitute a percentile latency for average \(W\) and treat it as an exact equality.

## 9. Identifying the Saturation Point

The saturation point is the region where increasing offered load no longer yields proportional increases in successful throughput, while latency, queues, or error rates climb rapidly.

Symptoms:

- Steep p95/p99 climb.
- Successful throughput plateaus.
- Errors/timeouts increase.
- `dropped_iterations` rises.
- CPU nears maximum or one core saturates.
- Queues or pending tasks grow continuously.
- Heap usage/GC pauses rise.
- Connection pools exhaust or pending acquires climb.

### 9.1. Throughput Plateau

The table below illustrates the shape of saturation, not real measurements:

| Offered load | Successful throughput | p95 | Error rate |
|---:|---:|---:|---:|
| 100 RPS | 100 RPS | 115 ms | 0% |
| 200 RPS | 200 RPS | 125 ms | 0% |
| 400 RPS | 390 RPS | 210 ms | 0.2% |
| 600 RPS | 420 RPS | 950 ms | 4% |
| 800 RPS | 425 RPS | 2.4 s | 12% |

At 600–800 RPS, offered load jumps sharply while successful throughput barely moves. The system is overloaded; merely adding VUs or raising timeouts will not fix the bottleneck.

### 9.2. Finding the Root Cause

- High CPU: profile code, serialization, algorithms, locks, or GC.
- Low CPU with high latency: inspect downstreams, connection pools, queues, network, and timeouts.
- Thread count spikes: check blocking calls and schedulers.
- Growing queues: slow producer rate, bound concurrency, or choose an overflow policy.
- High GC: check allocations, payload copies, and object retention.
- One core pegged while total CPU is low: possible event-loop blocking or lock contention.

## 10. Lab Project: WebFlux Reactive Wait vs. Offloaded Blocking Work

The following project creates two endpoints with the same response shape and configurable wait duration:

- `/bench/reactive`: uses `Mono.delay`, simulating an asynchronous wait operation.
- `/bench/blocking`: uses `Thread.sleep` inside `Mono.fromCallable`, offloaded to `Schedulers.boundedElastic()`.

The goal is to observe the difference between holding a thread during a wait and registering a non-blocking timer.

**Important limitation:** this benchmark simulates wait time; it is not a complete benchmark between Spring MVC and WebFlux, nor does it represent every database/HTTP client. `Mono.delay` does not replace real remote network calls. Use the lab to learn the methodology, then replace the simulated wait with real downstreams when making architectural decisions.

### 10.1. Structure

```text
reactive-load-evidence/
├── pom.xml
├── load/
│   └── benchmark.js
└── src/
    ├── main/
    │   ├── java/edu/demo/load/
    │   │   ├── LoadApplication.java
    │   │   ├── WorkService.java
    │   │   ├── WorkController.java
    │   │   └── WorkResponse.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/edu/demo/load/
            ├── WorkServiceTests.java
            └── WorkControllerTests.java
```

### 10.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>edu.demo</groupId>
    <artifactId>reactive-load-evidence</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

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
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

Spring Boot dependency management selects compatible Reactor and Micrometer versions. Do not add arbitrary versions for `reactor-core` or `micrometer-registry-prometheus` when using the Boot BOM.

### 10.3. `LoadApplication.java`

```java
package edu.demo.load;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LoadApplication {

    public static void main(String[] args) {
        SpringApplication.run(LoadApplication.class, args);
    }
}
```

### 10.4. `WorkResponse.java`

```java
package edu.demo.load;

public record WorkResponse(
        String mode,
        long delayMs,
        String status) {
}
```

### 10.5. `WorkService.java`

```java
package edu.demo.load;

import java.time.Duration;

import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@Service
public class WorkService {

    public Mono<WorkResponse> reactive(long delayMs) {
        return Mono.delay(Duration.ofMillis(delayMs))
                .map(ignored ->
                        new WorkResponse("reactive", delayMs, "ok"));
    }

    public Mono<WorkResponse> blockingOffloaded(long delayMs) {
        return Mono.fromCallable(() -> {
                    try {
                        Thread.sleep(delayMs);
                    }
                    catch (InterruptedException error) {
                        Thread.currentThread().interrupt();
                        throw new IllegalStateException(
                                "blocking work interrupted", error);
                    }

                    return new WorkResponse(
                            "blocking-offloaded", delayMs, "ok");
                })
                .subscribeOn(Schedulers.boundedElastic());
    }
}
```

Both methods build the same response type and simulate the same wait duration. `reactive` registers a timer without holding a dedicated thread sleeping. `blockingOffloaded` occupies a bounded elastic worker while `Thread.sleep` blocks.

Do not call `Thread.sleep` directly on the Netty event loop. In a real application, replace sleep with real I/O or an isolated, bounded blocking adapter.

### 10.6. `WorkController.java`

```java
package edu.demo.load;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@RestController
public class WorkController {

    private final WorkService workService;

    public WorkController(WorkService workService) {
        this.workService = workService;
    }

    @GetMapping("/bench/reactive")
    public Mono<WorkResponse> reactive(
            @RequestParam(defaultValue = "100") long delayMs) {

        return validate(delayMs)
                .flatMap(workService::reactive);
    }

    @GetMapping("/bench/blocking")
    public Mono<WorkResponse> blocking(
            @RequestParam(defaultValue = "100") long delayMs) {

        return validate(delayMs)
                .flatMap(workService::blockingOffloaded);
    }

    private Mono<Long> validate(long delayMs) {
        if (delayMs < 0 || delayMs > 1000) {
            return Mono.error(new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "delayMs must be between 0 and 1000"));
        }

        return Mono.just(delayMs);
    }
}
```

Capping the delay prevents clients from turning the lab endpoint into an uncontrolled long sleep task. In production, workload limits must come from configuration and policies managed by the service owner rather than trusting arbitrary values from callers.

### 10.7. `application.properties`

```properties
spring.application.name=reactive-load-evidence
server.port=8080

management.endpoints.web.exposure.include=health,info,metrics,prometheus
management.endpoint.health.show-details=never
management.metrics.distribution.percentiles-histogram.http.server.requests=true
management.metrics.tags.application=${spring.application.name}
```

Actuator provides health and metrics. The Prometheus endpoint exports metrics when the registry is present. In production, restrict network access or secure actuator endpoints; do not expose all management endpoints publicly to the Internet.

### 10.8. `WorkServiceTests.java`

```java
package edu.demo.load;

import java.time.Duration;

import org.junit.jupiter.api.Test;

import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class WorkServiceTests {

    private final WorkService service = new WorkService();

    @Test
    void reactiveDelayCanBeTestedWithVirtualTime() {
        StepVerifier.withVirtualTime(
                        () -> service.reactive(500))
                .thenAwait(Duration.ofMillis(500))
                .assertNext(result -> {
                    assertEquals("reactive", result.mode());
                    assertEquals(500, result.delayMs());
                    assertEquals("ok", result.status());
                })
                .verifyComplete();
    }

    @Test
    void blockingWorkIsOffloadedAndCompletes() {
        StepVerifier.create(service.blockingOffloaded(10))
                .assertNext(result -> {
                    assertEquals("blocking-offloaded", result.mode());
                    assertEquals(10, result.delayMs());
                    assertEquals("ok", result.status());
                })
                .verify(Duration.ofSeconds(3));
    }
}
```

Virtual time applies to Reactor timers created inside the `withVirtualTime` supplier. It does not make `Thread.sleep` run instantaneously; the blocking test uses real time with a finite timeout.

### 10.9. `WorkControllerTests.java`

```java
package edu.demo.load;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class WorkControllerTests {

    @Autowired
    WebTestClient client;

    @Test
    void reactiveEndpointReturnsExpectedPayload() {
        client.get()
                .uri("/bench/reactive?delayMs=5")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.mode").isEqualTo("reactive")
                .jsonPath("$.delayMs").isEqualTo(5)
                .jsonPath("$.status").isEqualTo("ok");
    }

    @Test
    void blockingEndpointReturnsExpectedPayload() {
        client.get()
                .uri("/bench/blocking?delayMs=5")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.mode").isEqualTo("blocking-offloaded")
                .jsonPath("$.delayMs").isEqualTo(5)
                .jsonPath("$.status").isEqualTo("ok");
    }

    @Test
    void delayOutsideAllowedRangeReturnsBadRequest() {
        client.get()
                .uri("/bench/reactive?delayMs=5000")
                .exchange()
                .expectStatus().isBadRequest();
    }
}
```

The Maven test suite consists of two unit tests and three integration tests. They verify endpoint semantics, not throughput. Load testing is run separately with k6.

### 10.10. Running the Application

In the project directory:

```bash
mvn test
mvn spring-boot:run
```

Test reactive:

```bash
curl "http://localhost:8080/bench/reactive?delayMs=100"
```

Sample response:

```json
{"mode":"reactive","delayMs":100,"status":"ok"}
```

Test blocking-offloaded:

```bash
curl "http://localhost:8080/bench/blocking?delayMs=100"
```

Sample response:

```json
{"mode":"blocking-offloaded","delayMs":100,"status":"ok"}
```

The responses above are the expected logical output of the program. It is not claimed that Maven was executed while authoring this lesson.

## 11. Load Testing with k6 at Constant Arrival Rate

k6 is an independent load generator. Use `constant-arrival-rate` to send a fixed number of iterations per second regardless of how long prior requests take.

### 11.1. `load/benchmark.js`

```javascript
import http from 'k6/http';
import { check } from 'k6';

const target = __ENV.TARGET === 'blocking'
    ? 'blocking'
    : 'reactive';

const expectedMode = target === 'blocking'
    ? 'blocking-offloaded'
    : 'reactive';

const rate = Number(__ENV.RATE || 200);
const delayMs = Number(__ENV.DELAY_MS || 100);
const duration = __ENV.DURATION || '90s';
const preAllocatedVUs = Number(__ENV.PREALLOCATED_VUS || 100);
const maxVUs = Number(__ENV.MAX_VUS || 500);

export const options = {
    scenarios: {
        steady: {
            executor: 'constant-arrival-rate',
            rate,
            timeUnit: '1s',
            duration,
            preAllocatedVUs,
            maxVUs,
            gracefulStop: '10s'
        }
    },
    thresholds: {
        http_req_failed: ['rate<0.01']
    }
};

export default function () {
    const url = `http://127.0.0.1:8080/bench/${target}?delayMs=${delayMs}`;
    const response = http.get(url, { timeout: '5s' });

    check(response, {
        'status is 200': result => result.status === 200,
        'response mode matches target': result => {
            try {
                return result.json('mode') === expectedMode;
            }
            catch {
                return false;
            }
        }
    });
}

export function handleSummary(data) {
    const summaryName = `summary-${target}.json`;

    return {
        [summaryName]: JSON.stringify(data, null, 2),
        stdout: JSON.stringify({
            target,
            metrics: data.metrics
        }, null, 2)
    };
}
```

The script uses an open workload. Each iteration sends one HTTP request. The 1% `http_req_failed` threshold is an example; replace it with your real SLO.

### 11.2. Running Both Options Separately

Warm up reactive:

```bash
k6 run -e TARGET=reactive -e RATE=50 -e DURATION=30s load/benchmark.js
```

Measure reactive:

```bash
k6 run -e TARGET=reactive -e RATE=200 -e DELAY_MS=100 -e DURATION=90s load/benchmark.js
```

Warm up blocking:

```bash
k6 run -e TARGET=blocking -e RATE=50 -e DURATION=30s load/benchmark.js
```

Measure blocking:

```bash
k6 run -e TARGET=blocking -e RATE=200 -e DELAY_MS=100 -e DURATION=90s load/benchmark.js
```

Results are saved as `summary-reactive.json` and `summary-blocking.json`. Run inside the project directory so summary files are easy to find.

### 11.3. Stepping Up Load Gradually

After the 200 RPS step, you can try:

```bash
k6 run -e TARGET=reactive -e RATE=400 -e DURATION=90s load/benchmark.js
k6 run -e TARGET=reactive -e RATE=600 -e DURATION=90s load/benchmark.js
```

Repeat similarly for blocking. Step up only when the load generator host still has sufficient resources and shows no significant dropped iterations caused by generator saturation.

Do not treat 200/400/600 RPS as universal targets. Pick levels based on traffic forecasts and real SLOs.

## 12. Reading k6 Results

In the summary, focus on:

| Metric | Meaning |
|---|---|
| `http_reqs` | Total requests sent |
| `http_req_duration` | HTTP request duration distribution |
| `http_req_failed` | Failed request rate |
| `iterations` | Completed iterations |
| `iteration_duration` | Duration of one iteration |
| `vus` | Active virtual users |
| `dropped_iterations` | Iterations not started on schedule |

For `http_req_duration`, read `avg`, `med`, `p(90)`, `p(95)`, `p(99)`, and `max`. Do not screenshot only the RPS line. Record offered rate, completed requests, errors, and dropped iterations.

### 12.1. Result Table to Record

| Run | Target | Offered RPS | Completed RPS | p50 | p95 | p99 | Error % | Dropped iterations |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | reactive | ... | ... | ... | ... | ... | ... | ... |
| 2 | blocking | ... | ... | ... | ... | ... | ... | ... |
| 3 | reactive | ... | ... | ... | ... | ... | ... | ... |
| 4 | blocking | ... | ... | ... | ... | ... | ... | ... |

Fill with actual data from summary files. Never use fabricated numbers or measurements from another machine as results for the current environment.

### 12.2. Checking the Load Generator

If `dropped_iterations` is non-zero:

1. Check CPU and memory on the k6 host.
2. Increase `preAllocatedVUs` if VUs are insufficient while the generator still has resources.
3. Check whether `maxVUs` hit its ceiling.
4. Inspect the network path.
5. Check whether request duration prevents sustaining the arrival rate.
6. If the generator is saturated, run k6 on a dedicated host.

If the generator cannot produce the full load, you cannot conclude the server sustained the offered rate.

## 13. Collecting Metrics from Spring Boot Actuator

Open:

```text
http://localhost:8080/actuator/health
http://localhost:8080/actuator/metrics
http://localhost:8080/actuator/prometheus
```

You can inspect individually:

```bash
curl http://localhost:8080/actuator/metrics/http.server.requests
curl http://localhost:8080/actuator/metrics/jvm.memory.used
curl http://localhost:8080/actuator/metrics/jvm.threads.live
curl http://localhost:8080/actuator/metrics/process.cpu.usage
curl http://localhost:8080/actuator/metrics/jvm.gc.pause
```

Metric names and tags depend on the registry, instrumentation, and versions. Use `/actuator/metrics` to inspect which metrics are actually registered.

### 13.1. Prometheus Scrape

Prometheus can scrape `GET /actuator/prometheus`. Dashboards should track HTTP request rate by URI/status, p50/p95/p99 latency, 5xx rate, heap, GC pauses, live threads, process CPU, connection pool active/pending if client instrumentation is enabled, Reactor Netty metrics if enabled, and queues/concurrency if custom-instrumented.

Never add user IDs, request IDs, or raw URLs with path parameters as high-cardinality labels. Use route templates and bounded-cardinality labels.

### 13.2. `boundedElastic` and Event-Loop Metrics

Scheduler/Netty metrics are not always registered by default under the same names. If you need to observe pending tasks, active workers, or connection pools, enable instrumentation matching your Reactor/Netty version and inspect actual metrics.

Do not assume `boundedElastic` queue depth is present just because Actuator was added. When needed, instrument with Micrometer or use JFR/thread dumps.

## 14. Measuring CPU, Heap, GC, and Threads Beyond HTTP Metrics

Useful JDK commands:

```bash
jcmd <pid> VM.version
jcmd <pid> GC.heap_info
jcmd <pid> Thread.print
jcmd <pid> JFR.start name=load settings=profile duration=120s filename=load.jfr
jfr summary load.jfr
```

Replace `<pid>` with the actual process ID. JFR can reveal blocked threads, CPU hotspots, allocation hotspots, GC pauses, lock contention, and socket events depending on recording configuration.

Never draw conclusions from a single thread dump. Take multiple snapshots under load and compare thread states/stacks.

### 14.1. Thread Count Is Not the Only Goal

A reactive server may use fewer event-loop threads than a blocking system, yet fewer threads do not automatically prove superiority. Evaluate successful throughput, p95/p99, CPU, queues, errors/timeouts, heap/GC, and recovery when load subsides.

If reactive holds fewer threads while p99 spikes due to a slow downstream or congested scheduler, that advantage may not yield good user outcomes.

## 15. Reading Benchmarks Through an Illustrative Example

Suppose multiple runs produce the following table:

| Metric at 400 offered RPS | Reactive | Blocking-offloaded |
|---|---:|---:|
| Completed RPS | 398 | 360 |
| p50 | 108 ms | 110 ms |
| p95 | 145 ms | 380 ms |
| p99 | 220 ms | 900 ms |
| Error rate | 0.1% | 1.5% |
| CPU process | 45% | 68% |
| Live threads | 28 | 75 |

These are **simulated numbers to illustrate reasoning**, not experimental results.

A responsible interpretation:

- At this offered load, both show similar p50.
- Blocking-offloaded has higher p95/p99; there may be queuing on `boundedElastic` or contention.
- CPU and live threads are higher in the blocking-offloaded option in this hypothetical environment.
- Inspect dropped iterations, queues, load generator CPU, and run counts before concluding.
- If the difference repeats consistently, the real workload truly involves substantial I/O wait, and operational cost matters, reactive can be a sensible choice.

Never write "reactive is 3x faster" because one percentile or one run showed a gap. Always state load level, environment, run count, error rate, and measurement limitations.

## 16. Moving from Synthetic Waits to Real Downstreams

`Mono.delay` simulates wait duration, but does not simulate full database or HTTP service behavior.

A production-like benchmark should include a separate downstream:

```text
k6
 |
 v
Gateway / API under test
 |
 +---- Reactive: WebClient (non-blocking)
 |
 +---- Blocking: RestClient/SDK (offloaded)
 |
 v
Downstream service / database
```

Both options must call the same downstream, payload, timeout, dataset, and network path.

### 16.1. Reactive Downstream Call

```java
public Mono<Product> loadReactive(String id) {
    return webClient.get()
            .uri("/products/{id}", id)
            .retrieve()
            .bodyToMono(Product.class);
}
```

`WebClient` is a reactive HTTP client. Using `WebClient` does not automatically keep the whole pipeline non-blocking if a subsequent operator invokes a blocking API.

### 16.2. Offloaded Blocking Downstream Call

```java
public Mono<Product> loadBlocking(String id) {
    return Mono.fromCallable(() ->
                    restClient.get()
                            .uri("/products/{id}", id)
                            .retrieve()
                            .body(Product.class))
            .subscribeOn(Schedulers.boundedElastic());
}
```

This example uses a configured and injected `RestClient`. The blocking call runs on bounded elastic rather than the Netty event loop.

### 16.3. Controlling the Downstream

- Use the same downstream instance/dataset.
- Reset or normalize caches before every run.
- Configure identical timeout and retry policies.
- Cap connection pools sensibly.
- Record downstream latency and error rate.
- Never let the downstream become an unmeasured bottleneck.
- If using a database, keep identical schema/indexes/connection pool and dataset.

If the downstream saturates, results may reflect the database rather than the web framework.

## 17. Comparing WebFlux and Spring MVC Fairly

Do not run both stacks inside a single application context and call it an independent benchmark. When both `spring-boot-starter-web` and `spring-boot-starter-webflux` are present, Spring Boot typically selects MVC when the MVC stack is on the classpath.

A rigorous comparison should deploy two separate applications or deployments:

| Condition | MVC application | WebFlux application |
|---|---|---|
| Java/JVM | Same version/options | Same version/options |
| Business logic | Same logic | Same logic |
| Data source | Same dataset | Same dataset |
| Downstream | Same service | Same service |
| Response | Same JSON/size | Same JSON/size |
| Security | Same policy | Same policy |
| Timeout/retry | Same semantics | Same semantics |
| CPU/memory limit | Same limits | Same limits |
| Load generator | Same machine/config | Same machine/config |

If one app uses JDBC and the other uses R2DBC, you are comparing the entire data-access stack, not only MVC vs. WebFlux. That is still useful, provided you document which variables differ.

### 17.1. Comparison by Workload

- **I/O-bound, high concurrency:** WebFlux can reduce threads waiting on I/O.
- **CPU-bound:** differences may be minor; CPU profiling and algorithms matter more.
- **Blocking dependencies:** WebFlux must offload, adding schedulers and complexity.
- **Streaming/backpressure:** WebFlux offers more natural reactive APIs.
- **Low traffic:** differences may not justify an architectural shift.
- **Team experience/operations:** complexity, debugging, and hiring are costs to weigh too.

## 18. Writing an Evidence-Based Architectural Conclusion

A concise yet review-ready report should contain:

### 18.1. Question and Hypothesis

Example:

> At 400 requests/second, 2 KB payloads, and 100 ms downstream I/O, does WebFlux keep p95 under 250 ms and error rate below 0.5% within CPU/memory budgets?

### 18.2. Methodology

Record commit/build ID, JDK, Spring Boot, Reactor, CPU/RAM/container limits, JVM options, downstream/dataset, k6 version/script, arrival rate/duration/VUs, warm-up and iteration counts, and SLOs/thresholds.

### 18.3. Results

Table containing offered/completed RPS, p50/p95/p99, error/timeout rates, dropped iterations, CPU/heap/GC/threads, queues/connections, medians, and variance across runs.

### 18.4. Explanation

Answer where the bottleneck is, when throughput plateaus, whether p99 rose due to queues/CPU/downstreams, whether data loss or dropped iterations occurred, which resources were saved, and whether results repeated consistently.

### 18.5. Decision and Limitations

Example:

> Choose WebFlux for the I/O-bound gateway because at 400 RPS, all three runs kept p95/p99 within SLO, error rates stayed below threshold, and thread/heap usage was lower. Results apply only to the tested non-blocking downstream workload; CPU-bound tasks and blocking batches are evaluated separately.

If metrics show no meaningful benefit, state so clearly. Keeping MVC to reduce complexity may be the better call.

## 19. Benchmarking Mistakes

| Mistake | Why it is wrong | Fix |
|---|---|---|
| Measuring only average latency | Hides tail latency | Report p50/p95/p99 |
| Running only one iteration | JIT, caches, thermals, and noise skew results | Repeat multiple runs |
| Running both targets simultaneously | Contention for CPU/heap/network | Run separately |
| Skipping warm-up | Measures startup/JIT instead of steady state | Warm up before measuring |
| Using closed model for arrival-rate goals | Slow server shrinks offered load | Use constant-arrival-rate |
| Ignoring dropped iterations | Unknown whether generator produced full load | Inspect generator and VU capacity |
| Assuming fewer threads is always better | Ignores latency, errors, and queues | Measure full SLOs/resources |
| Using Mono.delay to declare WebFlux beats MVC | Simulates wait only, not a production stack | Use real downstreams and two deployments |
| Changing pool sizes between runs | Conditions are no longer equal | Record and hold configuration fixed |
| Running k6 on a CPU-saturated host | Generator becomes the bottleneck | Use a dedicated load generator |
| Not measuring downstreams | Mistakes DB saturation for framework overhead | Collect metrics upstream and downstream |
| Unbounded retries in load tests | Amplifies load | Bound retries/backoff |
| Not keeping response/payload identical | Compares different workloads | Standardize requests/responses |
| Looking only at total CPU | One core/event loop may be saturated | Profile and inspect thread-level metrics |
| Not measuring heap/GC | Misses allocations and queue retention | Collect JVM metrics/JFR |
| Using synthetic results as production claims | Model is not fully representative | State limits and verify with real workloads |
| Not saving raw summaries/configs | Cannot reproduce | Save scripts, summaries, environment, and commit |
| Choosing SLOs after seeing results | Confirmation bias | Define SLOs before benchmarking |

## 20. Pre-Conclusion Checklist

### Workload and Hypothesis

- Is the workload described as I/O-bound, CPU-bound, or mixed?
- Are arrival rate, concurrency, payload, and downstream latency specified?
- Is there a falsifiable hypothesis?
- Are SLOs and saturation criteria defined up front?

### Environment and Fairness

- Identical JDK, JVM options, CPU/RAM limits?
- Identical business logic, data, downstreams, and payloads?
- Identical timeouts, retries, connection pools, and observability?
- Does the load generator have enough capacity?
- Are targets run separately and repeated?

### Metrics

- Offered and completed RPS?
- p50/p95/p99?
- Error/timeout rates?
- Dropped iterations?
- CPU, heap, GC, and thread counts?
- Queues, pending tasks, and connection pools?
- Raw summaries saved for reproducibility?

### Interpretation

- Is the saturation point identified?
- Are server bottlenecks distinguished from generator bottlenecks?
- Is it explained why p99 increased?
- Are synthetic benchmark limitations stated?
- Is claiming reactive is always faster avoided?
- Are complexity and operational costs considered?

## 21. Self-Check Exercises

**Exercise 1.** Why does reactive often fit high-concurrency I/O-bound workloads?

**Answer:** Non-blocking I/O does not hold a dedicated thread for the entire wait duration; threads can serve other work while awaiting I/O completion.

**Exercise 2.** Does reactive automatically increase CPU capacity for CPU-bound workloads?

**Answer:** No. CPU, algorithms, core counts, and contention remain the primary limits.

**Exercise 3.** According to Little's Law, approximately how many in-flight requests are there at 300 RPS throughput and 100 ms average latency?

**Answer:** \(L = 300 \times 0.1 = 30\) requests.

**Exercise 4.** How does p95 differ from average?

**Answer:** p95 is the threshold that 95% of requests complete within; average is the mean and can be heavily skewed by outliers.

**Exercise 5.** How does `constant-arrival-rate` help in load testing?

**Answer:** It maintains the scheduled iteration start rate, suitable for testing a system under a fixed offered load.

**Exercise 6.** Does rising `dropped_iterations` prove the server is saturated?

**Answer:** No. The load generator itself may lack VUs/CPU/network. Both generator and server must be inspected.

**Exercise 7.** Why is warm-up necessary?

**Answer:** To reduce the impact of class loading, JIT compilation, connection pool initialization, and cache warming on the steady-state measurement window.

**Exercise 8.** Why is `Mono.delay` not a complete production benchmark?

**Answer:** It simulates wait duration without simulating protocols, networking, connection pools, databases, serialization, or real downstream failure behaviors.

**Exercise 9.** If offered load increases while successful throughput stalls and p99 and errors climb, what is that a sign of?

**Answer:** The system may have reached its saturation point; find the bottleneck instead of merely adding load.

**Exercise 10.** When comparing MVC and WebFlux, why are two separate deployments needed?

**Answer:** So each application uses its proper stack and configuration independently; when both MVC and WebFlux dependencies are present, Boot may select MVC auto-configuration.

**Exercise 11.** Does a benchmark with lower thread count but high error rate prove reactive is better?

**Answer:** No. Evaluate SLOs, throughput, latency, error rate, and resources together.

**Exercise 12.** What must be recorded so benchmark results are reproducible?

**Answer:** Source/build, JDK/JVM, hardware/limits, dataset/downstream, load script/config, warm-up, measurement window, raw metrics, and run counts.

## 22. Takeaways

- Choosing reactive must rest on workload characteristics and evidence; there is no rule that reactive is always faster than MVC.
- The primary advantage typically appears in I/O-bound workloads with high concurrent waits and non-blocking clients/drivers.
- CPU-bound workloads remain bounded by CPU, algorithms, and contention.
- Measure throughput, p50/p95/p99, error rates, CPU, heap, GC, threads, queues, and connection pools.
- Open workloads with constant arrival rates keep offered load steady.
- `dropped_iterations` can reflect generator capacity limits, not necessarily server failures.
- Little's Law \(L=\lambda W\) helps estimate average in-flight requests.
- Saturation manifests as a throughput plateau alongside rising latency/queues/errors.
- Benchmarks require warm-up, multiple runs, fixed environments, and separate target executions.
- Synthetic waits are isolated labs, not production proof; verify with real workloads.
- MVC/WebFlux comparisons need identical business logic, data, downstreams, payloads, JVM, and resource limits across two independent deployments.
- A sound decision documents methodology, numbers, limitations, and rationale.

**Decision rule:** state workload → state hypothesis → measure fairly → identify bottlenecks/saturation → check against SLOs and resource budgets → explain limitations → only then choose reactive or MVC.

## 23. Official References

- Spring Framework — WebFlux overview and reactive/non-blocking model: https://docs.spring.io/spring-framework/reference/6.1/web/webflux.html
- Spring Boot 3.3 — Actuator metrics: https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html
- Spring Boot 3.3 — Prometheus endpoint: https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.export.prometheus
- Project Reactor — Scheduler and blocking integration: https://projectreactor.io/docs/core/3.6.11/reference/
- Project Reactor — Backpressure: https://projectreactor.io/docs/core/3.6.11/reference/#_on_backpressure
- k6 — Constant arrival rate executor: https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/constant-arrival-rate/
- k6 — Built-in metrics: https://grafana.com/docs/k6/latest/using-k6/metrics/reference/
- k6 — Handle summary and export results: https://grafana.com/docs/k6/latest/results-output/end-of-test/custom-summary/
- OpenJDK — Java Flight Recorder: https://docs.oracle.com/en/java/javase/17/jfapi/flight-recorder-api.html
- Spring Boot 3.3 — Managed dependency versions: https://docs.spring.io/spring-boot/3.3/appendix/dependency-versions/coordinates.html