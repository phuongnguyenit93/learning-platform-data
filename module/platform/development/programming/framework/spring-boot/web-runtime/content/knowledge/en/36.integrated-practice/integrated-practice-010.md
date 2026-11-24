# Load Testing, Resource Limit Tuning, and Verifying Overload Behavior in Spring Boot

## 1. Practice Objectives

A Spring Boot application may return HTTP 200 in 20 ms for a single user, yet collapse when hundreds of clients hit it concurrently: queues grow, p99 spikes, Tomcat worker threads block waiting on the DB, heap climbs, CPU throttles, the reverse proxy returns 502/504, or the Pod is OOMKilled. Therefore, **load testing** is not just chasing the highest RPS number—it must prove:

1. The application meets its **SLOs** for a specific workload and traffic profile.
2. Which resource becomes the **bottleneck** as load rises: CPU, heap/GC, threads, sockets, DB pool, queues, network, proxy, or the load generator itself.
3. Limits are **measured and tuned with evidence**, rather than arbitrarily raising every property.
4. Above capacity, the app exhibits **controlled overload behavior**: bounding concurrent work, returning clear HTTP 429/503 responses, or shedding early without unbounded queues.
5. Once load subsides, health, latency, connections/pools, and memory **recover** without backlog, leaks, or restart storms.
6. Evidence is collected from **both client and server**, without hiding rejected requests.

This lesson is an integrated practice for **Spring Boot web-runtime** using Java 17, Spring Boot 3.3.x, Spring MVC/embedded Tomcat, Actuator/Micrometer, k6, Docker, and Kubernetes. All timeouts, thread counts, quotas, and RPS targets are **lab values** chosen for observability—never assume they are safe or optimal for production.

**Safety scope:** run load generators only against localhost or authorized staging environments with strict bounds on duration, RPS, VUs, connections, and resources. Never aim stress tests at production or third-party systems without explicit approval, a maintenance window, and a kill switch.

## 2. Defining Metrics Before Generating Load

| Term | Accurate Meaning | Common Confusion |
| --- | --- | --- |
| Offered arrival rate | Requests/s the load generator **attempts to start** | Not the requests/s actually reaching Spring |
| Achieved request rate | Requests/s actually sent or completed, per tool | Not guaranteed to match target rate |
| Successful throughput | Operations/s **fulfilling the business contract** | HTTP 503/429 does not count as successful |
| Concurrency / in-flight | Requests holding resources at an instant | Different from RPS |
| Latency | Request duration at the measured boundary | Averages hide p99 spikes |
| p50/p95/p99 | Latency percentiles; p99 is the level ~99% stay under | Unstable with tiny sample sizes |
| Error rate | Failure ratio per contract: status, timeout, reset, business error | Intentional 503s still count as client-facing errors |
| Rejection / load shedding | Refusing new work before overload crashes the system | Not successful throughput |
| Saturation | Resource near full capacity or queues/pending growing | Low CPU does not mean DB/threads are free |
| Recovery | Returning to baseline latency, success, pools/heap/queues | Not just seeing the process still `Running` |

Example **lab contract** (not a production SLO):

- **Baseline:** 10 GET requests/s to an endpoint with simulated 200ms delay; HTTP success ≥99%, p95 `<`450ms, p99 `<`700ms, zero dropped iterations.
- **Stress:** ramp to 100–120 attempted GET requests/s; once all 8 logical slots are busy, the app returns **503 + Retry-After** while accepted latency stays bounded.
- **Safety:** zero OOMKills, zero unexpected restarts, health/ping remains serviceable, no unbounded queues.
- **Recovery:** drop back to 10 req/s; 503 drops near 0, accepted latency returns to baseline, active work settles normally.
- **Correctness:** if adapted to POST/DB, verify durable side effects and idempotency; HTTP 200 alone does not prove zero lost or duplicated writes.

### Little's Law and Approximate Capacity

For a steady-state system with consistent measurement boundaries:

\[
L = \lambda W
\]

`L` is average concurrent requests in the system, `λ` is completed requests/second, and `W` is average request duration (seconds). With 8 concurrent slots each held for 0.2 seconds, ideal capacity is roughly:

\[
\mu \approx 8 / 0{,}2 = 40 \text{ requests/s}
\]

This is only a **lab approximation** assuming every request takes ~200ms with no other bottleneck. In reality, serialization, thread scheduling, I/O, GC, retries, and payload sizes introduce variance. When offered load is 120/s against ~40/s capacity, the excess must enter a **bounded queue**, be rejected, or be throttled rather than accumulating without bound.

A classic danger signal: successful throughput stops climbing while p99, queue depth, and timeouts keep rising with offered load. That inflection is the **knee point** of the capacity curve.

## 3. Load Test Types and Scenario Selection

| Test | Question Answered | When to Run |
| --- | --- | --- |
| Smoke | Do endpoint, script, tokens, and metrics work? | Before every benchmark |
| Warm-up | Have JIT, classloading, and pools/caches stabilized? | Before baseline |
| Baseline | Are SLOs met at low traffic? | Reference benchmark |
| Load test | Does expected normal peak traffic meet SLOs? | Capacity verification |
| Stress | Pushing past target, which limit breaks first? | Inspect overload behavior |
| Spike | Does a sudden burst trigger meltdown? | Test queues and retries |
| Soak | Over long runs, do memory/FD/threads leak? | Stability check |
| Recovery | After load drops, does the system bounce back? | After stress/spike |
| Scalability | Does adding CPU/replicas raise successful throughput? | Tuning/architecture |
| Failover | How do Pod restarts/drains/DB stalls hit tail latency? | Resilience testing |

### Closed Model vs Open Model

**Closed model (constant VUs)**: each virtual user starts its next iteration only after the previous one completes. When the server slows down, request rate naturally slows too, causing the generator to **mask server degradation**—known as *coordinated omission*.

~~~javascript
export const options = {
  scenarios: {
    closed: {
      executor: 'constant-vus',
      vus: 20,
      duration: '30s',
    },
  },
};
~~~

**Open model (arrival rate)**: the tool attempts to launch requests at a fixed schedule regardless of response time, provided VUs are available.

~~~javascript
export const options = {
  scenarios: {
    open: {
      executor: 'constant-arrival-rate',
      rate: 20,
      timeUnit: '1s',
      duration: '30s',
      preAllocatedVUs: 30,
      maxVUs: 60,
    },
  },
};
~~~

With arrival-rate executors, **do not add `sleep(1)` at the end of the iteration** to pace traffic; the executor paces automatically. If `dropped_iterations > 0`, scheduled iterations **could not start** because the generator ran out of free VUs—due to low `preAllocatedVUs/maxVUs`, a slow SUT holding VUs too long, or both. Never misreport dropped iterations as app-returned HTTP 503s: track HTTP responses and attempts separately.

## 4. Finite Resources in Spring Boot

~~~text
Clients -> CDN / Ingress / LB
              |
              v
Tomcat TCP accept / keep-alive connections
              |
              v
Servlet request worker threads
              |
              v
Application concurrency gate
              |
          +---+----+
          |        |
          v        v
       JDBC       HTTP downstream
       pool       client pool
          |        |
          +---+----+
              |
              v
        CPU / heap / direct memory
              |
              v
        Database / broker / disk
~~~

| Resource | Signs of Saturation | What to Tune |
| --- | --- | --- |
| Servlet worker threads | Busy near max, queueing, health slows down | Reduce blocking/timeouts, size workers sensibly |
| TCP connections / FD | Refused/timeouts, high open sockets | Connection caps, keep-alive, idle/slow-client policies |
| Executor queue | Rising wait time and queued memory | Bounded queues, admission/rejection |
| JDBC pool | Hikari active=max, pending threads rising | Pool sizing, queries/indexes/transaction duration |
| CPU | High utilization/quota throttling, rising p99 | Optimize CPU work, CPU requests/limits, scale out |
| JVM heap/GC | Long GC pauses, climbing post-GC heap | Allocation profiling, heap/cache sizing |
| Native/direct memory | High RSS despite low Java heap | Netty buffers, thread stacks, cgroup memory |
| Reverse proxy | 502/504, upstream connect/read timeouts | LB upstream pools, limits, route/path configs |
| Load generator | VUs maxed, `dropped_iterations`, high CPU | Add injector capacity, lower test target |
| Downstream DB/broker | Latency, locks, queue lag | Capacity, multi-Pod budgets, backpressure |

**There is no universal flag to "boost performance."** At 30% CPU, the app can still be bottlenecked on a DB pool. Raising Tomcat workers from 16 to 200 may simply create 184 more threads waiting on the DB. Expanding the accept queue can lengthen request waits and lower success rates as clients time out.

## 5. Runnable Project: Spring Boot 3.3 / Java 17

The demo app exposes:

- `GET /api/ping` returning fast health-like JSON for HTTP responsiveness checks.
- `GET /api/work?durationMs=200` simulating work with `Thread.sleep` and bounded duration.
- A **Semaphore** capping concurrent work to 8 requests per JVM. When exhausted, it returns **503 Service Unavailable** with `Retry-After: 1` instead of queueing indefinitely.
- `GET /api/state` reporting active and available slots.
- Micrometer counters/gauges and Spring Actuator Prometheus.
- JUnit integration tests for 200, 400, 503, and recovery.
- k6 scripts for baseline and stress tests.

**Clear limitation:** `Thread.sleep` occupies a Servlet worker while consuming negligible CPU; RPS measured here **cannot be used to size CPU-bound workloads** like compression, encryption, or heavy JSON, nor does it represent a production database.

### 5.1. Directory Structure

~~~text
load-lab/
├── settings.gradle
├── build.gradle
├── Dockerfile
├── baseline.js
├── stress.js
└── src/
    ├── main/
    │   ├── java/demo/loadlab/LoadLabApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/demo/loadlab/LoadLabHttpTest.java
~~~

### 5.2. settings.gradle

~~~groovy
rootProject.name = 'load-lab'
~~~

### 5.3. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}

tasks.named('bootJar') {
    archiveFileName = 'load-lab.jar'
}
~~~

`spring-boot-starter-web` provides embedded Tomcat. The Micrometer Prometheus registry lets `/actuator/prometheus` serve scrape output; a real Prometheus server to store time series is a **separate** component not started by the dependency.

### 5.4. application.properties

~~~properties
spring.application.name=load-lab
server.port=8080

# Protect Actuator while testing on localhost only.
server.address=127.0.0.1

# Intentionally small Tomcat connector limits for the lab.
server.tomcat.threads.max=16
server.tomcat.threads.min-spare=4
server.tomcat.max-connections=100
server.tomcat.accept-count=20
server.tomcat.connection-timeout=10s
server.tomcat.keep-alive-timeout=10s
server.tomcat.mbeanregistry.enabled=true

# Logical work admission budget, separate from Tomcat thread count.
lab.max-concurrent=8

management.endpoints.web.exposure.include=health,info,metrics,prometheus
management.endpoint.health.probes.enabled=true
management.metrics.distribution.percentiles-histogram.http.server.requests=true

server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

**Explanation:**
- `server.tomcat.threads.max=16` bounds platform request workers, **not** RPS or TCP connections. With Java 21 virtual threads, several Tomcat thread settings lose this effect, though this lab targets Java 17.
- `server.tomcat.max-connections=100` bounds total connections including idle keep-alive sockets, not 100 concurrent handlers.
- `server.tomcat.accept-count=20` sets the TCP backlog when full; the OS may timeout/refuse without returning HTTP 503.
- `server.tomcat.connection-timeout` primarily waits for the request line after accept, not a total handler deadline.
- `server.tomcat.keep-alive-timeout` waits for the **next** request on a persistent connection.
- `server.tomcat.mbeanregistry.enabled=true` enables Tomcat MBean metrics in Boot 3.3.
- `management.metrics.distribution.percentiles-histogram.http.server.requests=true` enables HTTP timer histograms; assess memory/cardinality before enabling in production.
- `lab.max-concurrent=8` guards only the controller's work section; the server can still exhaust CPU, threads, or sockets before reaching the controller.

**Never expose `/actuator/prometheus`, `/actuator/metrics`, or `/api/state` publicly without protection.** In Docker/Kubernetes, when binding `0.0.0.0`, protect diagnostics via firewalls, NetworkPolicy, and edge auth.

### 5.5. Complete Java Source

`src/main/java/demo/loadlab/LoadLabApplication.java`:

~~~java
package demo.loadlab;

import java.util.Map;
import java.util.concurrent.Semaphore;
import java.util.concurrent.atomic.AtomicInteger;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class LoadLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(LoadLabApplication.class, args);
    }
}

@RestController
class WorkController {
    private final Semaphore permits;
    private final AtomicInteger active = new AtomicInteger();
    private final Counter rejected;
    private final Counter completed;
    private final int limit;

    WorkController(
            @Value("${lab.max-concurrent:8}") int maxConcurrent,
            MeterRegistry registry) {

        if (maxConcurrent < 1) {
            throw new IllegalArgumentException(
                    "lab.max-concurrent must be >= 1");
        }

        this.limit = maxConcurrent;
        this.permits = new Semaphore(maxConcurrent, true);

        Gauge.builder("lab.work.active", active, AtomicInteger::get)
                .description("Current active work requests")
                .register(registry);

        Gauge.builder("lab.work.available", permits,
                        Semaphore::availablePermits)
                .description("Available admission permits")
                .register(registry);

        rejected = Counter.builder("lab.work.rejections")
                .description("Work requests rejected at app gate")
                .register(registry);

        completed = Counter.builder("lab.work.completions")
                .description("Accepted work requests completed")
                .register(registry);
    }

    @GetMapping("/api/ping")
    Map<String, String> ping() {
        return Map.of("status", "ok");
    }

    @GetMapping("/api/state")
    Map<String, Integer> state() {
        return Map.of(
                "active", active.get(),
                "available", permits.availablePermits(),
                "limit", limit);
    }

    @GetMapping("/api/work")
    ResponseEntity<?> work(
            @RequestParam(defaultValue = "200") int durationMs) {

        if (durationMs < 0 || durationMs > 2500) {
            return ResponseEntity.badRequest().body(Map.of(
                    "error", "durationMs must be 0..2500"));
        }

        if (!permits.tryAcquire()) {
            rejected.increment();
            return ResponseEntity
                    .status(HttpStatus.SERVICE_UNAVAILABLE)
                    .header(HttpHeaders.RETRY_AFTER, "1")
                    .body(Map.of(
                            "result", "rejected",
                            "reason", "capacity"));
        }

        active.incrementAndGet();
        try {
            // Strictly to simulate blocking wait in the lab.
            Thread.sleep(durationMs);
            completed.increment();
            return ResponseEntity.ok(Map.of(
                    "result", "ok",
                    "durationMs", durationMs));
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            return ResponseEntity
                    .status(HttpStatus.SERVICE_UNAVAILABLE)
                    .body(Map.of("result", "interrupted"));
        } finally {
            active.decrementAndGet();
            permits.release();
        }
    }
}
~~~

### Why This Code Cleanly Verifies Overload Behavior

- `Semaphore(maxConcurrent,true)` enforces a finite permit count **per JVM**. `tryAcquire()` fails fast without parking request threads in an unbounded permit wait queue.
- When slots are exhausted, the controller **explicitly returns HTTP 503** with `Retry-After: 1`—**application-layer rejection**, distinct from TCP refusal or NGINX 502.
- `try/finally` always releases permits even on exceptions or interrupts, preventing permanent capacity leaks.
- `active` gauges running work, `available` tracks remaining permits, `rejected` counts gate 503s, and `completed` counts finished work.
- `/api/ping` needs no permit, yet still traverses Tomcat threads/connections. If the whole HTTP stack saturates, ping can still time out—it is never guaranteed 200 under total collapse.
- One Pod with 8 permits means 4 Pods admit up to **32 concurrent work requests** if balanced evenly, though a shared DB may tolerate less. This is not a distributed/global quota.

### 5.6. Running Locally

Linux/macOS:

~~~bash
./gradlew clean test bootJar
java -jar build/libs/load-lab.jar
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat clean test bootJar
java -jar .\build\libs\load-lab.jar
~~~

If the project lacks a Gradle wrapper, generate one using a compatible Gradle install or run `gradle clean test bootJar`.

In another terminal:

~~~bash
curl -i http://127.0.0.1:8080/api/ping
curl -i 'http://127.0.0.1:8080/api/work?durationMs=200'
curl -i http://127.0.0.1:8080/api/state
curl -i http://127.0.0.1:8080/actuator/health
~~~

Expected idle responses:

~~~text
GET /api/ping                 -> HTTP 200 {"status":"ok"}
GET /api/work?durationMs=200  -> HTTP 200 {"result":"ok","durationMs":200}
GET /api/state                -> HTTP 200 {"active":0,"available":8,"limit":8}
GET /actuator/health          -> HTTP 200 {"status":"UP"}
~~~

JSON key/header ordering, actual elapsed time, and instantaneous `active` counts can vary. `durationMs=5000` returns HTTP 400 (validation), not overload 503.

## 6. JUnit Testing: Proving 503 Fires When Permits Exhaust

`src/test/java/demo/loadlab/LoadLabHttpTest.java`:

~~~java
package demo.loadlab;

import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = "lab.max-concurrent=1")
class LoadLabHttpTest {

    @Autowired
    TestRestTemplate http;

    @Test
    void normalEndpointsWork() {
        ResponseEntity<String> ping = http.getForEntity(
                "/api/ping", String.class);
        assertThat(ping.getStatusCode()).isEqualTo(HttpStatus.OK);

        ResponseEntity<String> ok = http.getForEntity(
                "/api/work?durationMs=10", String.class);
        assertThat(ok.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(ok.getBody()).contains("\"result\":\"ok\"");
    }

    @Test
    void invalidDurationReturns400() {
        ResponseEntity<String> r = http.getForEntity(
                "/api/work?durationMs=9000", String.class);
        assertThat(r.getStatusCode())
                .isEqualTo(HttpStatus.BAD_REQUEST);
    }

    @Test
    void overloadedRequestReturns503AndThenRecovers()
            throws Exception {

        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            Future<ResponseEntity<String>> first =
                    executor.submit(() -> http.getForEntity(
                            "/api/work?durationMs=2000",
                            String.class));

            // Wait until the first request holds the permit,
            // rather than relying on an arbitrary Thread.sleep(100).
            boolean entered = false;
            for (int i = 0; i < 150; i++) {
                Map<?, ?> s = http.getForObject("/api/state", Map.class);
                if (s != null
                        && ((Number) s.get("active")).intValue() == 1) {
                    entered = true;
                    break;
                }
                Thread.sleep(10);
            }

            assertThat(entered).isTrue();

            ResponseEntity<String> denied = http.getForEntity(
                    "/api/work?durationMs=10", String.class);
            assertThat(denied.getStatusCode())
                    .isEqualTo(HttpStatus.SERVICE_UNAVAILABLE);
            assertThat(denied.getHeaders().getFirst("Retry-After"))
                    .isEqualTo("1");

            assertThat(first.get(5, TimeUnit.SECONDS)
                    .getStatusCode()).isEqualTo(HttpStatus.OK);

            ResponseEntity<String> recovered = http.getForEntity(
                    "/api/work?durationMs=10", String.class);
            assertThat(recovered.getStatusCode())
                    .isEqualTo(HttpStatus.OK);
        } finally {
            executor.shutdownNow();
        }
    }
}
~~~

Run:

~~~bash
./gradlew test --tests demo.loadlab.LoadLabHttpTest
~~~

With test cap = 1, the method holds the first request for 2 seconds, **verifies `active==1`**, asserts the second request gets 503, and verifies a request after completion returns 200. This prevents mistaking sequential calls for concurrent load. The test proves single-JVM HTTP behavior, not multi-pod cluster/Ingress capacity or production RPS.

**Stability note:** on very slow or heavily contended CI runners, polling windows/timeouts may need adjustment; the test must genuinely fail if the first request never entered the controller rather than faking a pass.

## 7. k6 baseline.js: Latency-Independent Offered Rate

Create `baseline.js` in the project root. Requires installing the **k6 CLI** per official docs; Gradle does not bundle `k6`.

~~~javascript
import http from 'k6/http';
import { check } from 'k6';

const BASE = __ENV.BASE_URL || 'http://127.0.0.1:8080';

export const options = {
  scenarios: {
    baseline: {
      executor: 'constant-arrival-rate',
      rate: 10,
      timeUnit: '1s',
      duration: '30s',
      preAllocatedVUs: 20,
      maxVUs: 50,
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    'http_req_duration{route:work}': [
      'p(95)<450',
      'p(99)<700',
    ],
    dropped_iterations: ['count==0'],
  },
};

export default function () {
  const res = http.get(BASE + '/api/work?durationMs=200', {
    timeout: '3s',
    tags: { route: 'work' },
  });

  check(res, {
    'baseline receives HTTP 200': (r) => r.status === 200,
    'baseline returns expected body': (r) =>
      r.status === 200 && r.json('result') === 'ok',
  });
}
~~~

Run while the Spring app is up:

~~~bash
k6 run -e BASE_URL=http://127.0.0.1:8080 baseline.js
~~~

On Windows PowerShell, run `k6 run -e ... .\baseline.js`. Target is **~10 iterations/s**; since each iteration makes one HTTP GET, attempted request rate tracks ~10/s when `dropped_iterations=0` and no script errors occur.

### Interpreting Thresholds

- `http_req_failed < 1%`: k6 marks HTTP 4xx/5xx as failed by default; the baseline expects zero 503s.
- `http_req_duration{route:work} p95 < 450ms`, `p99 < 700ms`: route-tagged response duration without mixing in health URLs.
- `dropped_iterations == 0`: the generator had enough VUs to start every scheduled iteration.
- If k6 exits non-zero, inspect which threshold failed. Never blindly raise VUs or timeouts to force green without finding the cause.
- The 450/700ms limits are **lab criteria**; set production thresholds from your real SLOs.

**Before baseline**, run a small warm-up to stabilize JIT, connection pools, and caches. Measure cold-start behavior in a **separate** experiment rather than folding it into steady state.

## 8. k6 stress.js: Controlled Ramp and Separating 503s

Create `stress.js` in the project root:

~~~javascript
import http from 'k6/http';
import { check } from 'k6';
import { Counter, Rate, Trend } from 'k6/metrics';

const BASE = __ENV.BASE_URL || 'http://127.0.0.1:8080';

const rejected = new Counter('lab_rejected_503');
const unexpected = new Rate('unexpected_response');
const acceptedLatency = new Trend('accepted_latency_ms', true);

export const options = {
  scenarios: {
    stress: {
      executor: 'ramping-arrival-rate',
      startRate: 10,
      timeUnit: '1s',
      preAllocatedVUs: 60,
      maxVUs: 120,
      stages: [
        { target: 20, duration: '15s' },
        { target: 80, duration: '25s' },
        { target: 120, duration: '25s' },
        { target: 10, duration: '20s' },
      ],
    },
  },
  thresholds: {
    unexpected_response: ['rate<0.01'],
    dropped_iterations: ['count==0'],
    accepted_latency_ms: ['p(95)<600'],
  },
};

export default function () {
  const res = http.get(BASE + '/api/work?durationMs=200', {
    timeout: '3s',
    tags: { route: 'work' },
  });

  const ok = res.status === 200;
  const shed = res.status === 503;

  if (ok) {
    acceptedLatency.add(res.timings.duration);
  }
  if (shed) {
    rejected.add(1);
  }

  unexpected.add(!(ok || shed));
  check(res, {
    'response is HTTP 200 or controlled 503': (r) =>
      r.status === 200 || r.status === 503,
  });
}
~~~

Run:

~~~bash
k6 run -e BASE_URL=http://127.0.0.1:8080 stress.js
~~~

**How to read the results:**

- At 10–20 req/s, the app usually has spare permits out of 8.
- With 8 slots and ~200ms handlers, crossing ~40/s offered load triggers **fast 503s** from the app gate.
- `lab_rejected_503` counts k6-observed 503s; `lab.work.rejections` counts server-side gate hits. Differences point to proxies, network drops, multiple instances, or timing windows.
- `accepted_latency_ms` tracks only status 200 responses, while overall `http_req_duration` mixes in fast 503s.
- k6's `http_req_failed` **still climbs** on intentional 503s; never hide that metric in reports.
- `unexpected_response` captures statuses outside 200/503 (and status 0 network errors), signaling failures outside the load-shedding contract.
- Check `dropped_iterations` separately: if k6 starves for VUs, fewer requests actually reach the app than planned.
- `accepted_latency_ms p95<600ms` is a lab criterion; failing it suggests accepted requests are queueing ahead of the permit gate.
- No single run guarantees a specific 503 count: OS/client scheduling, real latencies, replica counts, and config all shift results. **Measure**—never fabricate outputs.

### Why Overall Latency Can Look "Better" Under Overload

Suppose 40 HTTP 200s take 250ms and 80 fast 503s take 5ms. The combined average across 120 requests is ~87ms—lower than the 250ms baseline—yet only **one-third of requests succeeded**. Always report together:

~~~text
target offered rate
started/completed attempts
dropped_iterations
HTTP 200/s (successful throughput)
HTTP 503/s (intentional shed)
unexpected errors and connection failures
accepted p95/p99
all-response p95/p99
JVM, Tomcat, DB and OS saturation
recovery after reducing load
~~~

Never filter out 503s from error rates and claim zero errors, nor confuse intentional 503 load shedding with a Spring crash.

## 9. Manual Verification of the Concurrency Gate

Single request:

~~~bash
curl -i 'http://127.0.0.1:8080/api/work?durationMs=200'
~~~

Expected HTTP 200 JSON:

~~~json
{"result":"ok","durationMs":200}
~~~

When 8 requests occupy the handler, a 9th concurrent request returns:

~~~http
HTTP/1.1 503 Service Unavailable
Retry-After: 1
Content-Type: application/json

{"result":"rejected","reason":"capacity"}
~~~

Header order/formatting varies by runtime. To send a **localhost** burst on Linux/macOS:

~~~bash
seq 1 20 | xargs -P 20 -I {} \
  curl -s -o /dev/null -w '%{http_code}\n' \
  'http://127.0.0.1:8080/api/work?durationMs=1000'
~~~

Output typically mixes 200 and 503 when requests overlap; exact counts vary with scheduling. Afterward:

~~~bash
curl -i 'http://127.0.0.1:8080/api/work?durationMs=10'
curl -i http://127.0.0.1:8080/api/state
~~~

expect HTTP 200 and `active:0`, `available:8` once idle. Never send 9 **sequential** cURLs and call it a concurrency test.

## 10. Metrics: Client, HTTP, Tomcat, JVM, OS, and Downstream

### 10.1. Actuator/Micrometer Endpoints

In the lab:

~~~bash
curl -i http://127.0.0.1:8080/actuator/health
curl -i http://127.0.0.1:8080/actuator/metrics
curl -i http://127.0.0.1:8080/actuator/metrics/http.server.requests
curl -i http://127.0.0.1:8080/actuator/metrics/lab.work.active
curl -i http://127.0.0.1:8080/actuator/metrics/lab.work.rejections
curl -i http://127.0.0.1:8080/actuator/prometheus
~~~

**Some meters appear only after the first request**; route-tagged `http.server.requests` requires prior traffic. Registries also transform names: dotted `lab.work.rejections` becomes snake_case in Prometheus, e.g., `lab_work_rejections_total`, and gauges look like `lab_work_active`. **These names are illustrative**—inspect real scrape output before building dashboards.

In Spring Boot 3.3:
- Spring MVC auto-instruments `http.server.requests`.
- JVM metrics live under `jvm.*` (heap, GC, threads...); system/process metrics under `system.*` and `process.*`.
- Tomcat metrics may require `server.tomcat.mbeanregistry.enabled=true`.
- Prometheus output requires both the registry dependency **and** management endpoint exposure.

### 10.2. PromQL Queries with a Real Prometheus Server

When HTTP histograms are enabled and labels match this example, successful rate:

~~~promql
sum(rate(http_server_requests_seconds_count{
  uri="/api/work",status="200"
}[1m]))
~~~

App-level 503 rate:

~~~promql
sum(rate(http_server_requests_seconds_count{
  uri="/api/work",status="503"
}[1m]))
~~~

p95 latency of HTTP 200 requests:

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_server_requests_seconds_bucket{
      uri="/api/work",status="200"
    }[5m])
  )
)
~~~

**Verify in practice:** Micrometer/Prometheus versions, histogram settings, and labels can differ. Without `_bucket` series, `histogram_quantile` cannot run; enable timer histograms thoughtfully and measure time-series cardinality cost. Never attach raw `userId`, `requestId`, or query strings as metric tags.

### 10.3. Layers to Monitor Together

| Layer | Signals |
| --- | --- |
| k6 | `http_reqs`, `iterations`, `dropped_iterations`, `http_req_failed`, p50/p95/p99 |
| HTTP | `http.server.requests` by uri/status/method, 429/503/502/504 |
| App | `lab.work.active`, `available`, `rejections`, `completions` |
| Tomcat | busy/current threads, connections, accept/backlog saturation |
| JVM | used/after-GC heap, GC pauses, live threads, direct buffers |
| OS / container | CPU usage, CPU throttling, RSS, memory limit/OOM, FDs |
| DB | Hikari active/idle/pending, acquisition timeouts, slow queries |
| Upstream | downstream latency/errors, HTTP client pool pending |
| Proxy | upstream response/connect times, 502/504, resets |
| K8s | restarts, OOMKilled, CPU/memory requests/limits, Ready endpoints |

**Low cluster-wide average CPU can hide one hot Pod.** Inspect per-node/pod/revision aligned to identical timestamps. Never compare localhost k6 against public-ingress k6 and blame a single Tomcat property for the gap.

## 11. Tuning Tomcat and App Budgets Meaningfully

Lab levers:

~~~properties
server.tomcat.threads.max=16
server.tomcat.max-connections=100
server.tomcat.accept-count=20
lab.max-concurrent=8
~~~

**Four independent limits:**

- `threads.max`: platform worker thread cap. Java 21 virtual threads change semantics for some settings; this Java 17 lab uses platform threads.
- `max-connections`: total accepted connections including idle keep-alive sockets; not concurrent request workers.
- `accept-count`: TCP backlog when connections/threads fill; the OS can refuse/time out without any HTTP response.
- `lab.max-concurrent`: logical concurrent work permits inside the controller. When exhausted, requests dispatched by Tomcat receive 503.

### Experiment Matrix — Change One Variable at a Time

| Run | Change | Possible Observation |
| --- | --- | --- |
| A | 16 threads, 100 conns, 8 slots | Reference baseline |
| B | `lab.max-concurrent=2` | ~10/s theoretical, earlier 503s |
| C | `lab.max-concurrent=12` | Accepted rate may rise if Tomcat/downstream have headroom |
| D | `server.tomcat.threads.max=4` | Tomcat dispatch bottlenecks before the app gate |
| E | `server.tomcat.max-connections=20` | Connections/keep-alive may bottleneck |
| F | `server.tomcat.accept-count=500` | Longer backlog without raising service rate |
| G | Lower Docker CPU limit | On CPU-bound work, throttling and p99 climb |
| H | More replicas | Total permits grow, though LB/DB may cap throughput |

Restart with CLI overrides to run experiments cleanly and inspect startup config:

~~~bash
java -jar build/libs/load-lab.jar \
  --lab.max-concurrent=2
~~~

Or:

~~~bash
java -jar build/libs/load-lab.jar \
  --server.tomcat.threads.max=4
~~~

Change one setting per run, re-warm, and run the exact same k6 script, host, network, payload, and duration. Measure successful throughput **plus** accepted p95/p99, 503s, dropped iterations, and threads/CPU/heap/DB.

### Never Expand Queues Unboundedly

If 8 slots are tied up behind a 5-second downstream stall, a 10,000-request queue only piles up doomed waits. `Semaphore.acquire()` blocking endlessly on Servlet threads is also a hidden queue. `tryAcquire()` fail-fast—or a deadline-bounded queue—protects p99 far better. Rejected requests need clear client contracts: 503 for node/server overload, 429 for client/tenant quotas, plus `Retry-After` and bounded retries with backoff and jitter.

## 12. HikariCP, DB, and Downstream: Bottlenecks Often Live Outside Tomcat

This project **has no database**, so there is no live Hikari pool. In a real Spring JDBC/JPA app, typical settings look like:

~~~properties
# Only for applications using Spring DataSource/HikariCP.
spring.datasource.hikari.maximum-pool-size=10
spring.datasource.hikari.minimum-idle=2
spring.datasource.hikari.connection-timeout=1000
~~~

Hikari's `connection-timeout=1000` is in **milliseconds** (1 second)—verify per version/DB driver. Across 3 Pods each with Hikari max 10, total connections can reach ~30 plus other workers; never expand pools before checking DB `max_connections`, lock contention, and query plans.

Watch:
- Hikari active / idle / pending counts and connection acquisition timeouts.
- DB query p95/p99 duration, locks, CPU, and IOPS.
- Outbound HTTP client connect/read/pool-acquire deadlines.
- Whether retries amplify traffic while error budgets are exhausted.
- Whether DB transactions/connections stay open across response streaming.

**Adding Tomcat threads never fixes a saturated DB pool.** Real fixes shorten query/transaction times, tune SQL/indexes, cache appropriately, bound downstream concurrency, and add circuit breakers.

## 13. Docker: CPU, Memory, Bind Address, and Benchmark Boundaries

`Dockerfile` for the built JAR:

~~~dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY build/libs/load-lab.jar /app/load-lab.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/load-lab.jar"]
~~~

Build and run **binding only to host localhost**:

~~~bash
./gradlew clean bootJar
docker build -t load-lab:1.0 .

docker run --rm --name load-lab \
  --cpus=1 --memory=512m \
  -e SERVER_ADDRESS=0.0.0.0 \
  -e JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=65" \
  -p 127.0.0.1:18080:8080 \
  load-lab:1.0
~~~

Test:

~~~bash
curl -i http://127.0.0.1:18080/api/ping
k6 run -e BASE_URL=http://127.0.0.1:18080 baseline.js
~~~

**Explanation:**
- `server.address=127.0.0.1` from local properties must be overridden to `0.0.0.0` **inside Docker** so host port publishing reaches the container IP instead of container loopback.
- `EXPOSE 8080` is metadata only; `-p 127.0.0.1:18080:8080` publishes the port.
- `--cpus=1` enforces a CPU quota, causing throttling on truly CPU-heavy work.
- `--memory=512m` caps total container memory; heap is only part of it—thread stacks, metaspace, direct buffers, and JIT code cache also consume memory.
- `-XX:MaxRAMPercentage=65` is a lab guard keeping heap from eating the whole cgroup; size from actual RSS/off-heap profiles and JVM flags.
- `docker stats` tracks usage; `docker inspect` may print env vars/secrets, so never share raw output.

**Do not expect doubling CPU from 1 to 2 cores to double throughput on a `Thread.sleep` endpoint.** The workload only sleeps 200ms with 8 permits and does not represent hashing, JSON serialization, or SQL CPU work. Size CPU using realistic production payloads, traffic mixes, and DB interactions.

## 14. Kubernetes: Requests, Limits, Probes, HPA, and Backpressure

**Lab** manifest `k8s-load-lab.yaml` (image must be available on cluster nodes/registry):

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: load-lab
spec:
  replicas: 1
  selector:
    matchLabels:
      app: load-lab
  template:
    metadata:
      labels:
        app: load-lab
    spec:
      containers:
        - name: app
          image: load-lab:1.0
          imagePullPolicy: IfNotPresent
          ports:
            - name: http
              containerPort: 8080
          env:
            - name: SERVER_ADDRESS
              value: "0.0.0.0"
            - name: LAB_MAX_CONCURRENT
              value: "8"
          resources:
            requests:
              cpu: "250m"
              memory: "256Mi"
            limits:
              cpu: "1"
              memory: "512Mi"
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 2
            failureThreshold: 30
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
---
apiVersion: v1
kind: Service
metadata:
  name: load-lab
spec:
  selector:
    app: load-lab
  ports:
    - name: http
      port: 80
      targetPort: http
  type: ClusterIP
~~~

**Key mechanics:**
- `requests` guide scheduler placement and utilization calculations for many HPA policies.
- `limits.cpu` enforces cgroup CPU quotas/throttling; a container need not sit at 100% CPU to suffer tail-latency spikes from throttling.
- `limits.memory` triggers **OOMKill** if cgroup memory exceeds the cap; spare Java heap does not guarantee native memory hasn't run out.
- Liveness probes must not fail during brief overload and trigger a restart storm across replicas.
- Readiness controls traffic routing; **an app gate hitting 8/8 momentarily should not automatically flip the Pod NotReady**, as that causes endpoint flapping and traffic shifts.
- HPA does not replace admission control: autoscaling lags behind spikes, shared DB capacity may not scale, and excess load still requires backpressure/load shedding.
- `imagePullPolicy=IfNotPresent` fits local kind/minikube; production should use immutable digests from trusted registries.

Once the image is loaded/published:

~~~bash
kubectl apply -f k8s-load-lab.yaml
kubectl get pods -l app=load-lab -o wide
kubectl get svc load-lab
kubectl get endpointslice \
  -l kubernetes.io/service-name=load-lab
kubectl logs deployment/load-lab --tail=100
kubectl top pods
~~~

`kubectl top` requires `metrics-server`. For local `kind`, run `kind load docker-image load-lab:1.0`. To load-test the in-cluster Service accurately, run k6/cURL from an in-cluster Pod in the same namespace or via staging Ingress; **`kubectl port-forward`** is for debugging, not measuring production LB/Ingress performance.

## 15. Diagnosing Why a Stress Test Fails

### A. Application Admission Gate Working as Designed

Signs:
- `lab.work.active≈8`, `lab.work.available≈0`.
- `lab.work.rejections` climbs alongside k6 HTTP 503s.
- Accepted p95 stays bounded; CPU, heap, and threads avoid runaway growth.
- When load drops, 503s vanish and permits recover.

**Conclusion:** overload was shed **before consuming expensive downstream resources**. Only raise permits if downstream, CPU, and memory have proven headroom.

### B. Tomcat Threads or Connection Layer Saturating Before the App

Signs:
- Tomcat busy workers pinned near max 16.
- TCP timeouts/refusals or gateway 502/504s.
- App rejection counter stays low because requests never reached the controller.
- `/api/ping` slows down despite needing no work permits.

**Conclusion:** fix connectors, worker counts, blocking, keep-alive, or TCP backlog rather than blindly raising app permits.

### C. DB Pool Exhaustion

Signs:
- Hikari `active=max`, pending threads growing, workers stuck waiting for connections.
- p99 climbs alongside slow DB queries/locks and pool acquisition timeouts.

**Conclusion:** optimize SQL/transactions and downstream budgets; adding Tomcat threads will not raise DB throughput when the DB/pool is the bottleneck.

### D. CPU Throttling, Heap/GC, or Native Memory

Signs:
- Cgroup CPU throttled time spikes and p99 rises under tight CPU limits.
- Long GC pauses, rising post-GC heap, or memory hitting cgroup limits.
- OOMKilled despite seemingly free heap (native/direct/stack allocations).

**Conclusion:** inspect CPU quotas, RSS, GC logs, and profiles rather than looking only at average CPU or `-Xmx`.

### E. Ingress/Proxy Failing Before the App

Signs:
- k6 receives 502/504 while app `http.server.requests` and rejections do not rise correspondingly.
- Ingress logs show connection refused, upstream timeouts, or no ready endpoints.

**Conclusion:** troubleshoot networking, proxies, Service routing, or rollouts—do not blame the controller.

### F. Load Generator Saturation

Signs:
- `dropped_iterations > 0`; k6 VUs, CPU, or sockets maxed out.
- Server looks idle while achieved RPS falls short of target.

**Conclusion:** measurements are invalid for proving server capacity; scale up injector resources, separate the load-generator machine, or tune VUs cleanly.

## 16. 429 vs 503, Retry-After, and Retry Storms

- **429 Too Many Requests:** best for per-user, per-tenant, or per-API-key rate/quota limits.
- **503 Service Unavailable:** best when global or node capacity is temporarily exhausted (used here for the `Semaphore` gate).
- **502/504:** gateway/upstream failures, distinct from app-level 503s.
- **`Retry-After: 1`:** server hint asking clients to back off for 1 second, though clients aren't forced to obey.

Safe client retries need **exponential backoff + jitter**, bounded max attempts, overall deadlines, and protection against synchronized reconnect storms. For side-effecting POSTs (creating orders, charging payments), require **`Idempotency-Key`**, durable deduplication, and reconciliation—a 504/timeout never proves a transaction didn't commit.

**Concurrency limits** differ from **rate limits**: a single 1-hour SSE stream stays well below rate limits while holding a connection open, whereas 1,000 tiny bursts may trip rate limits despite low concurrency. Enforce quotas, buffers, and timeouts appropriate to each route type.

## 17. Soak, Spike, and Recovery: Verifying After Load Drops

A thorough stress test never stops the moment HTTP 503s appear; include a **recovery window**:

1. Warm up; record baseline CPU, post-GC heap, threads, FDs, and active slots.
2. Run steady load at 10/s and confirm baseline SLOs.
3. Ramp through 20→80→120/s within authorized bounds.
4. Capture full status breakdown, accepted latency, unexpected failures, and queue depths.
5. Drop back to 10/s or 0; monitor active slots, DB pending, Tomcat threads, and heap.
6. After stabilization, verify 200 responses resume, 503s drop near 0, and zero restarts, OOMs, or queue creep occurred.
7. Over long soak runs, confirm post-GC heap, native RSS, Netty/Servlet connections, FDs, and metric series do not climb endlessly.

Rising RSS over a few minutes **does not prove a memory leak**: the JVM reserves heap/code cache, loads classes, and fills caches. Inspect post-GC retained memory, GC/JFR logs, and heap dumps (only in secured staging, as dumps can contain PII) before diagnosing leaks.

When JDK diagnostics and permissions are available:

~~~bash
jcmd
jcmd 12345 VM.flags
jcmd 12345 GC.heap_info
jcmd 12345 Thread.print
jcmd 12345 JFR.start name=load-lab settings=profile duration=60s
~~~

`12345` is an example PID; substitute the real PID. These commands require JDK tools and matching privileges; JFR profiling adds overhead and captures sensitive data, so never run or export dumps recklessly in production.

## 18. Comparing Spring MVC/Tomcat Against WebFlux/Reactor Netty

This lab uses synchronous Spring MVC with `Thread.sleep`:
- each accepted request ties up one platform worker thread during the wait;
- Tomcat worker saturation is a primary signal.

WebFlux/Reactor Netty uses non-blocking I/O:
- never run `Thread.sleep` or `.block()` on event-loop threads;
- enforce bounded demand/queues, slow-subscriber policies, timeouts, and cancellation;
- `server.tomcat.threads.max` has zero effect on Netty;
- an unbounded `onBackpressureBuffer` on a hot publisher can trigger OOM.

Illustrative snippet (**not a standalone WebFlux project**):

~~~java
// Inside a reactive WebFilter with exchange and chain.
return Mono.defer(() -> {
    if (!semaphore.tryAcquire()) {
        exchange.getResponse().setStatusCode(
                HttpStatus.SERVICE_UNAVAILABLE);
        return exchange.getResponse().setComplete();
    }

    return chain.filter(exchange)
            .doFinally(signal -> semaphore.release());
});
~~~

Because Reactor publishers are lazy, acquiring and releasing permits must bind to subscription and completion lifecycle—never wrap **publisher assembly** in `try/finally` and release the permit before the response finishes.

**Never compare** Spring MVC `Thread.sleep` directly against a WebFlux timer endpoint and declare one framework faster. Benchmarks must compare identical business logic, DB, payloads, SLOs, network paths, and resources.

## 19. A Scientific Tuning Loop

~~~text
Business workload + SLO
          |
          v
Warm-up + reproducible baseline
          |
          v
Increase offered load in stages
          |
          v
Measure successful throughput,
accepted p95/p99, rejects, saturation
          |
          v
Find actual bottleneck
  | CPU/GC        -> optimize/scale CPU/memory
  | SQL/DB pool   -> query/pool/transaction budget
  | Tomcat worker -> reduce blocking/bounded concurrency
  | Socket/FD     -> connection cap/keep-alive/timeouts
  | Queue         -> bound/reject/priority
  | k6 injector   -> VUs/CPU/network on load-generator
          |
          v
Change ONE parameter
          |
          v
Repeat same workload/environment
          |
          v
Compare SLO, successful RPS,
rejection/error rates, recovery
~~~

**Anti-pattern:** changing Tomcat 16→200 threads, DB pool 10→100, CPU 1→4, and heap 256MB→2GB all at once and declaring "more threads made the app faster." You have no control isolating which change helped.

Run multiple trials and record variance, revision, JVM flags, Pod count, k6 targets, warm-up, test duration, time of day, ingress route, dataset, and cache state. Only identical conditions support valid before/after comparisons.

## 20. Sample Results Report (Purely Hypothetical Numbers)

| Config | Offered RPS | Achieved req/s | 200/s | 503/s | Unexpected/s | Accepted p95 | Assessment |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 8 slots baseline | 10 | 10 | 10 | 0 | 0 | 225ms | Lab SLO met |
| 8 slots ramp | 30 | 30 | 29 | 1 | 0 | 245ms | Near threshold |
| 8 slots stress | 120 | 120 | 39 | 81 | 0 | 280ms | Controlled load shedding |
| 2 slots stress | 120 | 120 | 10 | 110 | 0 | 240ms | Gate sheds earlier |
| 8 slots recovery | 10 | 10 | 10 | 0 | 0 | 220ms | Recovered after load |

**Every number in this table illustrates reporting format only** and is not an actual measured run. It assumes zero `dropped_iterations`, one HTTP request per iteration, zero automatic retries, and a single JVM app. Real numbers vary with scheduling, CPU, network, JIT, payload, OS, and proxy layers.

### Responsible Sample Conclusion

> Under the recorded version, configuration, and workload, the system met p95 SLOs at low load; under high stress arrival rates, the app shed excess load via 503 once permits saturated, produced zero unexpected HTTP/network errors, kept accepted p95 within SLO, and recovered after load dropped. This demonstrates **controlled overload** for the lab workload—not that production achieves 120 business transactions/s.

### Misleading Conclusion

> The load generator reported 120 RPS and an overall average latency of 60ms, so the server successfully handled 120 RPS.

If 81/s were fast HTTP 503 rejections, successful throughput was only 39/s. Fast 503s pull down overall average latency, hiding the experience of accepted requests.

## 21. Common Mistakes Table

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Looking only at total RPS | Treats 503s as completed work | Report successful throughput, 503s, and retries |
| Looking only at average latency | Hides p95/p99 and tail timeouts | Measure percentiles per route and status |
| Skipping warm-up | Cold JIT/caches skew baseline | Warm up first; benchmark cold start separately |
| Using `constant-vus` for fixed arrival rate | Slow server reduces client RPS | Use k6 arrival-rate executors |
| Adding `sleep` inside arrival-rate | Holds k6 VUs longer, spikes drops | Let the executor pace iterations |
| Ignoring `dropped_iterations` | Load never reached offered rate | Check injector VUs/CPU and app slowness |
| Requiring stress tests to have `http_req_failed == 0` | Intentional 503s fail the test | Define a separate overload threshold contract |
| Hiding 503s from reports | Masks real client impact | Report full status mix and errors transparently |
| Running k6 and app on the same low-CPU node | Injector steals CPU from the app | Separate load generator and monitor both |
| Raising threads when Hikari pool is full | Creates more blocked waiting threads | Optimize SQL/DB and concurrency bounds |
| Raising `accept-count` instead of capacity | Lengthens queues and timeouts | Use bounded admission and measure latency |
| Waiting forever on `Semaphore.acquire()` | Ties up Servlet workers | Use `tryAcquire()` to reject fast |
| Forgetting `finally` to release permits | Permanently leaks slots | Always release on errors/interrupts |
| Confusing ingress 502 with app 503 | Tunes the wrong layer | Compare edge vs app counters and upstream logs |
| Monitoring heap only | Misses native/direct/stack memory | Track RSS, cgroup memory, and FDs |
| Watching only average CPU | Misses CPU throttling and DB waits | Track CPU quota throttling and downstream metrics |
| Letting liveness fail under brief load | Triggers restart storms | Tie liveness to process health, readiness separately |
| Treating HPA as load shedding | Autoscaling lags behind spikes | Keep bounded admission controls |
| Using `port-forward` to benchmark ingress | Bypasses real production path | Test via real staging Service/Ingress |
| Exposing Actuator to the Internet | Leaks operational metrics/topology | Restrict to private networks with auth |
| Blindly retrying POSTs on 503/504 | Duplicates side effects | Use idempotency keys and durable reconciliation |

## 22. Acceptance Checklist

- [ ] Load generated only against authorized targets with bounded duration, rate, VUs, and a stop switch.
- [ ] Success/error SLOs and overload contract explicitly defined.
- [ ] Java/Boot/JVM flags, code revision, Pod count, and CPU/memory/DB configs recorded.
- [ ] Endpoints, payloads, datasets, and network paths represent real workloads.
- [ ] Warm-up, baseline, and identical configuration kept across runs.
- [ ] k6 `dropped_iterations` verified; never claim capacity if target load wasn't delivered.
- [ ] Reported offered vs achieved vs successful throughput, plus 200/429/503/502/504/status0.
- [ ] Measured accepted p95/p99 separately from overall p95/p99.
- [ ] Measured Tomcat workers/connections, app slots, JVM/GC, cgroup CPU/memory, and DB pool.
- [ ] Verified app-level 503 returns fast when permits exhaust.
- [ ] Confirmed zero unbounded queues, OOMs/restarts, or FD/heap leaks.
- [ ] Reduced load and verified active slots, queues, latency, and health recover.
- [ ] Changed only one parameter per tuning run while repeating the exact workload.
- [ ] With multi-Pod/Ingress, reconciled edge vs app and per-Pod metrics.
- [ ] For POST business workloads, verified idempotency and durable invariants.
- [ ] No diagnostic/Actuator endpoints, tokens, or PII exposed in public logs or metrics.
- [ ] Conclusions scoped to the tested workload and environment without wild extrapolation.

## 23. Self-Check Questions

**1.** With 8 permits and 200ms per work request, roughly what is the theoretical capacity?

**Answer:** `8 / 0.2 = 40 requests/s` under ideal conditions—not a measured throughput guarantee.

**2.** A server receives 120 req/s and returns 503 for 80/s of them. Can we claim it successfully handled 120 req/s?

**Answer:** No. Successful throughput is ~40/s assuming the rest succeeded; 503s are deliberate rejections that still impact clients.

**3.** Why can overall average/p95 latency drop during overload?

**Answer:** Fast 503 rejections can dominate the sample count, pulling overall duration down while success rate collapses. Measure accepted latency separately.

**4.** Does k6 `dropped_iterations` mean Tomcat returned HTTP 503?

**Answer:** No. Those are scheduled iterations that never started because no VU was available—caused by under-provisioned load generators or slow server responses holding VUs.

**5.** Are `server.tomcat.threads.max=16` and `lab.max-concurrent=8` the same thing?

**Answer:** No. Tomcat threads serve all HTTP traffic including other routes, whereas the app gate caps logical work on one route. Connections and accept backlog are separate too.

**6.** Does setting `server.tomcat.accept-count=1000` make the DB process queries faster?

**Answer:** No. It only expands the connector's TCP backlog, adding zero CPU or DB capacity.

**7.** Is setting `-Xmx` equal to the container memory limit safe?

**Answer:** No. The JVM needs non-heap/direct/native memory and thread stacks, and the OS/cgroup also uses memory—risking OOMKill.

**8.** Why can't a `Thread.sleep` test prove CPU scalability?

**Answer:** Sleeping blocks workers without stressing CPU; CPU-bound workloads must be benchmarked directly.

**9.** When should you return 429 vs 503?

**Answer:** 429 suits per-client/tenant rate or quota limits; 503 suits temporary server/node capacity exhaustion.

**10.** Why can adding Tomcat threads worsen latency if Hikari max is 10?

**Answer:** More workers pile up waiting on the 10 DB connections, increasing queueing and p99 without relieving the DB/pool bottleneck.

**11.** When ramping back down from 120/s to 10/s, what must be verified?

**Answer:** 503s drop, 200s recover, accepted p95/p99 return to baseline, active slots/queues/FDs/heap do not leak, and Pods did not restart.

**12.** Is `kubectl port-forward` to a Service valid for benchmarking public Ingress?

**Answer:** No. Port-forwarding follows a different network path and overhead; test the actual Service/Ingress/LB where authorized.

**13.** Does an HTTP 504 on a POST guarantee the DB did not commit?

**Answer:** No. A gateway timeout does not prove the backend aborted before committing; retries require idempotency and durable reconciliation.

**14.** Can WebFlux/Netty use `server.tomcat.threads.max` to scale processing?

**Answer:** No. Netty uses event loops, reactive backpressure, and distinct properties—never block the event loop.

**15.** What three metric groups are the minimum needed to sign off on overload behavior?

**Answer:** Client outcomes (offered/started/200/503/errors/p95), server admission/saturation (active slots, workers/CPU/DB), and recovery/stability (health, restarts/OOMs, queues/memory).

## 24. Official References

- [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): Tomcat max threads/connections/accept count, keep-alive, MBean Registry.
- [Spring Boot 3.3 — Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html): Micrometer, `http.server.requests`, JVM/system/Tomcat metrics, Prometheus registry.
- [Spring Boot 3.3 — Actuator Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html): health/metrics security and exposure.
- [Spring Boot 3.3 — Graceful Shutdown](https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html): in-flight requests on shutdown.
- [Tomcat 10.1 — HTTP Connector](https://tomcat.apache.org/tomcat-10.1-doc/config/http.html): threads/connections/backlog/timeouts.
- [Grafana k6 — Open vs Closed Models](https://grafana.com/docs/k6/latest/using-k6/scenarios/concepts/open-vs-closed/): arrival-rate and coordinated omission.
- [Grafana k6 — Constant Arrival Rate](https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/constant-arrival-rate/): rate, `preAllocatedVUs`/`maxVUs`.
- [Grafana k6 — Ramping Arrival Rate](https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/ramping-arrival-rate/): stress stages.
- [Grafana k6 — Dropped Iterations](https://grafana.com/docs/k6/latest/using-k6/scenarios/concepts/dropped-iterations/): unscheduled iterations and causes.
- [Grafana k6 — Thresholds](https://grafana.com/docs/k6/latest/using-k6/thresholds/): pass/fail, tagged submetrics.
- [Grafana k6 — Built-in Metrics](https://grafana.com/docs/k6/latest/using-k6/metrics/reference/): `http_req_failed`, request duration, iterations, VUs.
- [Micrometer — Reference](https://docs.micrometer.io/micrometer/reference/concepts.html): Counters, Gauges, Timers, tag cardinality.
- [Docker — Resource Constraints](https://docs.docker.com/engine/containers/resource_constraints/): CPU/memory limits.
- [Docker — Port Publishing](https://docs.docker.com/engine/network/port-publishing/): container/host port distinction.
- [Kubernetes — Resource Management](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/): CPU requests/limits, memory, scheduler.
- [Kubernetes — Probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/): readiness/liveness/startup.
- [Kubernetes — Horizontal Pod Autoscaling](https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale/): HPA behavior/metrics.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): 429/503 and Retry-After.

**Remember:** a good load-test report states more than raw RPS. It details **test conditions, offered/achieved/successful throughput, p95/p99, 429/503/5xx counts, CPU/heap/thread/DB saturation, which bottleneck hit first, and recovery behavior**. Above capacity, controlled fail-fast load shedding beats infinite queueing—just report **client impact** transparently with hard numbers and never hide failures.