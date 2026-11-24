# Detecting Thread Blocking and Evaluating Real Load Capacity

> **Context:** Spring Boot web-runtime, focusing on Spring WebFlux running on Reactor Netty and the consequences when blocking or CPU-bound code lands on the event loop. This lesson lays out a workflow for root-cause analysis, reproducing behavior with a Java 17+ application, designing repeatable load tests, reading metrics, and determining load thresholds against realistic targets.

## 1. Target Outcomes

After this lesson, you will be able to:

1. Explain why a long synchronous call on an **event-loop thread** can slow down many HTTP requests, even while an individual request still returns `200 OK`.
2. Distinguish **blocking I/O**, **non-blocking I/O**, **CPU-bound work**, **lock contention**, **connection pool queues**, and **stop-the-world GC** when diagnosing latency.
3. Correlate external signals (RPS, p95/p99, errors, timeouts) with internal evidence (thread dumps, JFR, CPU profilers, metrics) to diagnose accurately.
4. Apply `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` when interacting with blocking APIs, while understanding why that is strictly an isolation measure.
5. Design load tests with explicit inputs, durations, step ramps, acceptance thresholds, and stop conditions; interpret saturation points correctly instead of mistaking "highest peak RPS ever seen" for sustainable capacity.
6. Write a reproducible report detailing app version, environment config, load scenario, parameters, metrics, root causes, and conclusion limits.

## 2. Execution Model: Why Is Blocking One Thread Dangerous?

A WebFlux + Reactor Netty server defaults to a relatively small pool of event-loop threads to serve very many connections. The event loop receives socket events, performs non-blocking reads/writes, invokes callbacks/advances reactive pipelines, and returns to handle new events. It does **not** hold a worker thread idle per request while waiting on network I/O.

```text
       HTTP A        HTTP B        HTTP C        ...
          \            |            /
           +---- Netty event loops ----+
                      |
                short callback
                /           \
     non-blocking WebClient   light CPU / operators
                \           /
              return thread to loop
                      |
            result event arrives later
                      |
                emit next signal
```

If a callback executes `Thread.sleep(500)`, synchronous `RestTemplate`, synchronous JDBC, blocking file reads, or a large computation loop on the event loop, that thread is pinned until the operation finishes. Other connections needing that same thread must wait. Under load, the visible symptom is **execution-layer head-of-line blocking**: tail latency spikes, event-loop lag climbs, and timeouts appear even while overall CPU remains fairly low.

Conversely, a `WebClient` remote HTTP call taking 500 ms wall-clock time **does not inherently block** the event-loop thread for 500 ms: the network runtime registers a callback and moves on to other work. When data returns, the pipeline resumes.

Remember: `Mono`/`Flux` describe processing flows; they do not automatically move synchronous code to another thread. `map(x -> blockingCall(x))` still blocks the signal-emitting thread. `flatMap` cannot save you either if its lambda invokes a blocking API **before** returning a publisher. And `Thread.sleep()` does not throw an exception on its own merely for running on a Reactor Netty event loop.

### I/O-Bound, CPU-Bound, and Blocking Are Three Separate Axes

| Work type | Examples | What resource is consumed? | Easily misread signs |
|---|---|---|---|
| Non-blocking I/O | `WebClient` with Reactor Netty, compatible R2DBC | Connections, sockets, callbacks, buffers; no thread sitting idle across network latency | Requests still slow down due to upstream, yet thread dumps won't show threads waiting per request |
| Blocking I/O | Synchronous JDBC, `InputStream.read()`, sync SDKs | A thread is pinned waiting for I/O; plus pool/connection limits | Low CPU yet high p99 and elevated thread/queue counts |
| CPU-bound | Compression, signing, large serialization, heavy algorithms | CPU cores, caches, memory bandwidth | High CPU, hot runnable stacks even with zero blocking APIs |
| Lock contention | `synchronized` around shared state, synchronous locks | Threads contending for locks; latency tracks contention | `BLOCKED`/monitor enter states; CPU need not be high |
| Scheduler/connection queue | All boundedElastic workers busy, DB/HTTP pools exhausted | Resource queues/waiting | Latency rises before business logic even starts |
| GC pauses, resource throttling | Heap pressure, CPU quotas, container limits | JVM/runtime/OS | Even trivial endpoints stall simultaneously |

**Never conclude "event-loop blocking" solely from low CPU, high latency, or threads in `WAITING`.** Idle event-loop threads wait for I/O events normally. You need proof matching **exact thread + exact stack + duration + correlation with load**.

## 3. Typical Symptoms of a Blocked Event Loop

You may encounter scenarios like:

- A normally sub-millisecond `/fast` endpoint suddenly suffers elevated p95/p99 when another endpoint runs slow data queries.
- Most requests still return `200 OK`, yet timeouts appear as RPS rises while CPU cores remain underutilized.
- Certain requests stall despite healthy upstreams: they wait in line for callbacks on a busy event loop.
- Repeated thread dumps catch `reactor-http-nio-...` (or corresponding Netty threads) inside `Thread.sleep`, `java.io`, JDBC clients, or the same heavy CPU routine.
- After offloading blocking calls from the event loop, lightweight endpoints recover noticeably, though overall throughput may then hit DB pools, boundedElastic worker caps, or downstream limits.

These symptoms are **not exclusive** to blocking. Proxy buffering, load balancers, DNS, TCP backlogs, socket/connection pools, GC, OS throttling, or an underpowered load generator can look similar. Sound diagnosis follows **observation → hypothesis → evidence → controlled change → re-measurement**.

## 4. Layering Evidence to Detect Blocking

### 4.1. HTTP Layer: Detecting Symptoms Externally

Record at least:

- **Offered load:** intended request/iteration **initiation rate per second** configured in the load tool.
- **Achieved throughput:** completed responses/requests per second (RPS) measured at client and, if available, server.
- **Latency:** median (p50), p95, p99, and max; for streaming, separate time-to-first-byte and total completion time.
- **Errors:** timeouts, resets, `5xx`, `429`, `503`, wrong business outcomes, cancelled requests; never check only `500` rates.
- **Concurrency:** in-flight requests, queue depths, open/pending connections.
- **Resource saturation:** CPU, GC, heap, event-loop lag, worker utilization, connection pools, OS limits.

A clean average latency can hide 1% of requests stalling for seconds. For latency-sensitive APIs, p99 matters far more than the mean. With tiny sample sizes, p99 is noisy; collect sufficient samples per stage and repeat runs.

### 4.2. Thread Layer: Capturing Stacks Under Load

With JDK 17+ and access to the Java process, run:

```bash
jps -l
jcmd <PID> Thread.print -l
```

Replace `<PID>` with the actual process ID. Capture multiple snapshots **while the load test is running**, such as during steady load and right as degradation begins. Locate Netty request-handling threads (names vary by runtime) and inspect their **stack frames**:

```text
Example pattern to investigate (illustrative, not a real thread dump):
reactor-http-nio-3
  -> ... handler/reactive operator ...
  -> ... legacy JDBC / Thread.sleep / InputStream.read ...
```

Seeing the same blocking call stack on event-loop threads across multiple snapshots is far stronger evidence than a single stray sample. Correlate timestamps with latency spikes and load-generating endpoints. Java thread states `RUNNABLE`, `WAITING`, `TIMED_WAITING`, `BLOCKED` **do not self-explain root causes**: `RUNNABLE` can include native I/O, `WAITING` can simply be an idle worker, and `BLOCKED` usually reflects monitor contention.

In Docker/Kubernetes, run tools in an environment with JDK/attach permissions or use an approved diagnostic mechanism. Never assume a JRE-only container image includes `jcmd`.

### 4.3. Java Flight Recorder (JFR) and Profilers

JFR is a JVM tool that records CPU, allocations, GC, and blocking/parking/locking/I/O events when configured appropriately. Example for a test application:

```bash
jcmd <PID> JFR.start name=webload settings=profile duration=60s filename=webload.jfr
```

Apply load during the recording window, then open `webload.jfr` in JDK Mission Control or a compatible JFR reader. You can also inspect events via CLI:

```bash
jfr print --events jdk.ExecutionSample,jdk.ThreadPark,jdk.SocketRead,jdk.JavaMonitorEnter webload.jfr
```

Event lists can appear empty if the profile/settings omit them or none occurred. Stack depth and sampling frequency have limits; **absence of an event never proves zero blocking occurred**.

How to read it:

- **CPU profile**: find which stacks burn CPU; heavy CPU on the event loop requires offloading CPU work rather than labeling it I/O blocking.
- **ThreadPark/JavaMonitorEnter**: identify threads waiting on locks/parks, durations, and call sites.
- **SocketRead/file-related events**: identify synchronous I/O pinning threads; seeing them on boundedElastic reflects intentional isolation.
- **GC/JVM/OS**: check whether pauses, allocation rates, CPU throttling, or memory pressure align with p99 spikes.

Run JFR/profilers with acceptable overhead and environment-appropriate configuration. In production, follow operational controls and protect sensitive stack/metadata data.

### 4.4. BlockHound: Catching Blocking Calls on Non-Blocking Threads

[BlockHound](https://github.com/reactor/BlockHound) can instrument known blocking calls (such as `Thread.sleep`) when executed on threads marked non-blocking. In compatible setups, it catches mistakes early during tests or diagnostics.

Example bug that a tool like BlockHound targets:

```java
// Dangerous if this pipeline is subscribed on an event-loop thread.
Mono<String> bad = Mono.fromCallable(() -> {
    Thread.sleep(200);
    return "ok";
});
```

**Do not hold false assumptions:**

1. `Mono.block()` on certain Reactor `NonBlocking` threads may be rejected immediately with `IllegalStateException`; that **does not** mean every blocking API fails automatically.
2. BlockHound does not detect every custom blocking library, does not catch long CPU-bound loops via the same mechanism, and may require explicit integrations/allowlists.
3. Instrumentation support depends on JDK, Byte Buddy, Reactor, and BlockHound versions; project docs note JVM flags required on JDK 13+. Never assume a `BlockHound.install()` snippet works across every build/runtime unchanged.
4. Never rely solely on BlockHound to certify capacity: it helps **detect a class of bugs**, whereas load tests and observability measure real impact.

### 4.5. Spring Boot Actuator, Micrometer, and Reactor Netty

With `spring-boot-starter-actuator`, Micrometer exposes HTTP/JVM/system metrics. For Reactor Netty, meters such as `reactor.netty.eventloop.pending.tasks` or `reactor.netty.connection.provider.pending.connections` help **when Netty instrumentation is enabled and exported by your metrics setup**. Exact meter names/tags vary by version, configuration, and backend.

In a lab setup, add dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

And test configuration in `src/main/resources/application.properties`:

```properties
management.endpoints.web.exposure.include=health,metrics
```

After startup, list registered meters via:

```bash
curl http://localhost:8080/actuator/metrics
```

A meter may not appear until its code path runs; never assume every `reactor.netty.*` meter is enabled by default. For Prometheus, add the registry and configure endpoints separately; expose management endpoints only within appropriate networks and access controls.

**Read metrics causally:** rising HTTP latency paired with event-loop pending tasks and blocking stacks points to event-loop blocking; rising latency paired with DB pending connections points to pools/upstreams; high CPU paired with GC pauses or CPU hotspots points elsewhere.

## 5. WebFlux Lab: Three Execution Paths and One Control Endpoint

Experiment goal: observe the difference between **deliberately blocking the event loop**, **offloading blocking calls to a suitable worker**, and **non-blocking timer delays**. For a clean comparison, use a Spring Boot app containing **only** `spring-boot-starter-webflux` running embedded Reactor Netty. Having `spring-boot-starter-web` on the classpath as well may make Spring Boot select Spring MVC, invalidating server assumptions.

Create a Java 17+ Spring Boot project with `org.springframework.boot:spring-boot-starter-webflux`. In Gradle (Groovy DSL), the minimal dependency snippet is:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
```

This adds to a **project with Spring Boot plugins and repositories already configured**, not a complete `build.gradle`. Create a single application class at `src/main/java/example/load/BlockingLoadLabApplication.java`:

```java
package example.load;

import java.time.Duration;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@SpringBootApplication
public class BlockingLoadLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(BlockingLoadLabApplication.class, args);
    }

    @RestController
    public static class LabController {

        @GetMapping("/lab/fast")
        public Mono<String> fast() {
            return Mono.just("fast-ok");
        }

        @GetMapping("/lab/blocked")
        public Mono<String> blocked() {
            // INTENTIONALLY WRONG: a blocking Callable subscribed
            // on the current thread, typically the Netty event loop.
            // For local experimentation only.
            return Mono.fromCallable(LabController::legacyWait);
        }

        @GetMapping("/lab/offloaded")
        public Mono<String> offloaded() {
            // Same blocking work, but executed on a Scheduler
            // suitable for blocking I/O.
            return Mono.fromCallable(LabController::legacyWait)
                    .subscribeOn(Schedulers.boundedElastic());
        }

        @GetMapping("/lab/nonblocking")
        public Mono<String> nonblocking() {
            // Timer-based delay; does not hold a sleeping thread for 200 ms.
            return Mono.delay(Duration.ofMillis(200))
                    .thenReturn("timer-ok");
        }

        @GetMapping("/lab/cpu")
        public Mono<Long> cpu() {
            return Mono.fromCallable(() -> {
                        long sum = 0L;
                        for (long i = 0; i < 2_000_000L; i++) {
                            sum += i;
                        }
                        return sum;
                    })
                    .subscribeOn(Schedulers.parallel());
        }

        private static String legacyWait()
                throws InterruptedException {
            Thread.sleep(200);
            return "legacy-ok";
        }
    }
}
```

**Why is this example trustworthy?**

- `Mono.fromCallable` defers `legacyWait` until subscription. In `/lab/blocked`, no scheduler switch occurs, so under standard WebFlux/Netty it runs on the event-loop thread. This route is **intentionally broken** to demonstrate the problem—never ship it to production.
- `/lab/offloaded` attaches `subscribeOn(Schedulers.boundedElastic())` directly to the blocking source, moving `Thread.sleep` onto a worker to keep event loops unpinned. It **does not make `legacyWait` non-blocking**.
- `/lab/nonblocking` uses `Mono.delay` without putting any thread to sleep for 200 ms. It simulates logical delay, **not real HTTP I/O**.
- `/lab/fast` serves as a simple probe to detect spillover latency onto endpoints doing no slow work.
- `/lab/cpu` demonstrates offloading computation onto `Schedulers.parallel()`. This small loop is merely to observe the operator; JIT/compilers may optimize it, so never use it as a CPU benchmark.
- `Thread.sleep` strictly **simulates blocking**; real I/O libraries have distinct behaviors and wait characteristics. `Mono.delay` uses a timer scheduler and still needs a thread briefly to emit callbacks when the timer fires; the key point is **not holding a thread idle** for the entire 200 ms.

Run the project:

```bash
./gradlew bootRun
```

On Windows, use `gradlew.bat bootRun`. In another terminal, verify each endpoint (in Windows PowerShell, prefer `curl.exe` if `curl` is aliased):

```bash
curl -s http://localhost:8080/lab/fast
curl -s http://localhost:8080/lab/blocked
curl -s http://localhost:8080/lab/offloaded
curl -s http://localhost:8080/lab/nonblocking
curl -s http://localhost:8080/lab/cpu
```

Expected response bodies in order:

```text
fast-ok
legacy-ok
legacy-ok
timer-ok
1999999000000
```

`1_999_999_000_000` is the sum of integers from 0 to 1,999,999. Actual response times **are not fixed**: the legacy and timer endpoints introduce ~200 ms logical delay, plus scheduling, network, load, JIT, and test-machine variance.

To observe clearly, apply load **separately** to `/lab/blocked`, then repeat on `/lab/offloaded` and `/lab/nonblocking`. While a client drives load, intermittently probe `/lab/fast` and record its latency; this probe reveals how one slow endpoint degrades unrelated requests sharing an event loop. Base conclusions on multi-sample distributions, never a single `curl` invocation.

### Expected Impact Profiles

| Path | Where does the 200 ms work sit? | What to observe | Limitation |
|---|---|---|---|
| `/lab/blocked` | Blocks subscribing thread, typically event loop in test config | Heavy load stalls `/lab/fast` too | Depends on event-loop count, runtime config, and connection distribution |
| `/lab/offloaded` | Blocks boundedElastic worker | Event loop stays much more responsive | Workers and queues are bounded; does not scale throughput infinitely |
| `/lab/nonblocking` | Timer holds no sleeping worker | Logical delay does not pin the event loop | Does not represent real DB/downstream calls |
| `/lab/cpu` | Computes on Reactor parallel worker | Separates CPU from event loop | CPU cores are finite; parallel is unsuitable for blocking I/O |
| `/lab/fast` | Minimal work | Control endpoint for baseline latency | Still shares sockets, runtime, proxies, and system CPU |

**Test warning:** `/lab/blocked` is strictly for controlled dev/benchmark labs. Never deploy intentional bottleneck endpoints to real systems or run load tests outside authorized environments.

## 6. Designing Load Tests: Ask the Right Question Before Measuring

A good load test never starts with "blast as many requests as possible". You must specify **which capacity** is being measured: the end-to-end system for a structured workload, on a defined hardware configuration, against explicit SLA/SLO targets.

### Three Test Types to Distinguish

| Type | Objective | Load level and duration |
|---|---|---|
| Smoke/baseline | Verify endpoint correctness, load tool operation, and metric collection | Low requests, short run; never draw capacity conclusions from it |
| Load/step test | Characterize behavior at target load and find where degradation starts | Stepped ramps held long enough at each step to observe steady state |
| Stress/soak test | Stress: observe degradation and recovery beyond capacity. Soak: catch leaks/resource accumulation over prolonged runs | Stress ramps deliberately above target; soak holds representative load for long durations |

Add **spike tests** if evaluating sudden traffic bursts. A 30-second run cannot prove stability over hours, nor expose memory leaks, connection leaks, or degradation across GC cycles.

### Document Context for Fair Comparisons

Before starting, record variables that shift outcomes:

1. Source commit/version, Java version, Spring Boot/Reactor versions, and JVM flags.
2. CPU cores/vCPU, container CPU quotas, RAM, heap, replica count, event-loop/scheduler/pool settings.
3. Load generator host, network topology, TLS, proxies/ingress, keep-alive, HTTP version, connection limits.
4. Database version/config, pools, caches, upstreams, input datasets, and cache warm/cold state.
5. Endpoint mix in workload, request/response sizes, read/write ratio, user behavior, authentication.
6. Acceptance criteria: where p95/p99 is measured, error rate, target throughput, resource ceilings, timeout bounds.
7. Safety guards and abort conditions: avoid exhausting shared DBs, disrupting shared environments, or hitting third-party services outside test scope.

Upgrading a server from 2 vCPU to 8 vCPU without noting it renders RPS comparisons meaningless. Warm caches, keep-alive, loopback networking, and skipped auth also yield numbers far rosier than production.

## 7. Open Workloads, Closed Workloads, and Coordinated Omission

Two common client simulation models:

- **Closed workload:** N virtual users; each user sends the next request only after the previous finishes (optionally after think time). When the server slows down, the sending rate **automatically drops**. Useful for some interactive user flows, yet hides failure to sustain an offered arrival rate.
- **Open workload:** the tool attempts to launch requests at a fixed arrival rate independent of server response time, e.g., 20 → 50 → 100 req/s. Useful for asking "does the server still meet SLOs when traffic arrives at rate X?". When VUs/connections run short, the tool drops scheduled iterations, so inspect `dropped_iterations`.

**Coordinated omission** occurs when measurement tooling fails to record requests that should have arrived while the system was stalled, making tail latency look artificially clean. Match the load model and measurement method to reality; never claim fixed VUs and fixed arrival rates measure the same thing.

### Little's Law as a Sanity Check

In a stable steady-state system, the approximate relationship is:

```text
L = λ × W

L: average concurrent requests inside the system
λ: average arrival/completion rate (requests/second) at steady state
W: average time spent in the system (seconds)
```

If a system steadily serves 50 req/s averaging 0.2 s/request, expect roughly 10 concurrent requests inside the system. If average latency climbs to 1 s at 50 req/s, in-flight requests average around 50. This links **mean values**—never plug p95 into W and call the product "average concurrency".

When offered load exceeds real capacity, queues grow, latency climbs, and the system leaves steady state. In that regime, do not blindly apply `L = λW` to project capacity. Little's Law is a sanity check, **not proof for choosing a scheduler**.

## 8. A Runnable k6 Script for Stepped Load Ramps

Use [Grafana k6](https://grafana.com/docs/k6/latest/) installed on the load-generator machine. Create `load-test.js` **on the load-generator machine** (not in deployable app source):

```javascript
import http from 'k6/http';
import { check } from 'k6';

const baseUrl = __ENV.BASE_URL || 'http://localhost:8080';
const testPath = __ENV.TEST_PATH || '/lab/offloaded';

export const options = {
    scenarios: {
        stepped_load: {
            executor: 'ramping-arrival-rate',
            startRate: 5,
            timeUnit: '1s',
            preAllocatedVUs: 40,
            maxVUs: 100,
            stages: [
                { target: 5, duration: '20s' },
                { target: 20, duration: '30s' },
                { target: 20, duration: '1m' },
                { target: 50, duration: '30s' },
                { target: 50, duration: '1m' },
                { target: 5, duration: '20s' },
            ],
        },
    },
    thresholds: {
        http_req_failed: ['rate<0.01'],
        http_req_duration: ['p(95)<500', 'p(99)<1000'],
        checks: ['rate>0.99'],
    },
};

export default function () {
    const response = http.get(baseUrl + testPath, {
        timeout: '3s',
    });

    check(response, {
        'HTTP 200': (r) => r.status === 200,
    });
}
```

Run per endpoint:

```bash
k6 run -e TEST_PATH=/lab/blocked load-test.js
k6 run -e TEST_PATH=/lab/offloaded load-test.js
k6 run -e TEST_PATH=/lab/nonblocking load-test.js
```

When targeting another host, specify `BASE_URL` with an authorized server hostname/IP:

```bash
k6 run -e BASE_URL=http://localhost:8080 -e TEST_PATH=/lab/offloaded load-test.js
```

In remote environments, replace `localhost` with the test-environment service address. Never leave `localhost` when the load generator runs on a separate host, as it would hit the generator itself.

**Script accuracy notes:** `ramping-arrival-rate` attempts to start iterations per second; each iteration here executes one HTTP GET, so offered iterations/s approximates offered requests/s absent drops or retries. `preAllocatedVUs` and `maxVUs` cap k6-side concurrency. If `dropped_iterations > 0`, the tool could not launch all scheduled iterations; never claim the server sustained the `target` rate alone.

The `p95 < 500 ms`, `p99 < 1,000 ms`, and `<1%` error thresholds are **lab examples**, not production SLOs. Set criteria from product requirements. `checks` assert HTTP 200; `thresholds` determine k6's pass/fail exit code. If an endpoint legitimately returns `404` or `429` by policy, adjust checks and expected-response predicates accordingly.

**Never put `sleep()` at the end of an iteration** under `ramping-arrival-rate`: this executor already schedules arrival rates. A load generator at 100% CPU, out of sockets/file descriptors, burdened by heavy TLS, or short on VUs can become the bottleneck itself; monitor the generator alongside the server.

### Measuring Spillover Impact on the Fast Endpoint

The script above drives a single path for clean comparison. To verify event-loop interference, while load runs against `/lab/blocked`, measure `/lab/fast` latency from a **second lightweight client**. Repeat while loading `/lab/offloaded` and `/lab/nonblocking`. Isolating probe traffic from main load separates "an endpoint designed with 200 ms latency" from "**an unrelated endpoint being stalled**".

To report probe p95 rigorously, use a dedicated k6 scenario/metric or a statistical client rather than eyeballing a few `curl` timings.

## 9. Analyzing Metrics: Which Metric Answers Which Question?

| Metric | Meaning | Question to ask |
|---|---|---|
| Offered rate vs achieved RPS | Planned launch rate vs actual completions | Did we reach target traffic? Did drops, timeouts, or retries distort the run? |
| p50 / p95 / p99 latency | Client-observed latency distribution | Does the tail degrade well before the average shifts? |
| `http_req_failed` / status breakdown | Failed requests as classified by the tool | At what load do errors begin; are they `503`, `5xx`, timeouts, or wrong results? |
| `checks` | k6 assertion logic | Is the server returning **correct content/status**, not just failing fast? |
| `dropped_iterations` | Scheduled iterations k6 failed to start | Too few VUs, weak generator, or extreme latency? Was offered load actually achieved? |
| p95/p99 of `/lab/fast` under slow-endpoint load | Control endpoint latency | Is blocking spilling onto shared event loops? |
| CPU/GC/heap | Compute, memory, and GC pressure | CPU saturation, GC pauses, or allocation pressure? |
| Netty event-loop pending tasks/lag | Event queue / dispatch delay | Are callbacks being delayed under load? Is the meter actually enabled? |
| boundedElastic workers/queue | Blocking-call execution capacity | Did offloading free the event loop while forming a new queue? |
| DB/HTTP client connection pools | Active/pending connections | Does downstream cap out below the HTTP server? |
| Thread dumps/JFR | Execution stacks, locks, I/O, CPU | Which code causes the delay, on which thread type, and when? |

In k6, `http_req_duration` measures sending, waiting, and receiving—not full iteration time or connection/DNS setup. For network breakdown, inspect `http_req_blocked`, `http_req_connecting`, `http_req_tls_handshaking`, `http_req_waiting`, and `http_req_receiving`. For streaming endpoints, response duration and time-to-first-byte answer different questions.

**Separate verified facts from hypotheses.** Example: "p99 climbed past 50 RPS, and Netty event loops appeared in `Thread.sleep` stacks" is verifiable evidence. "JDBC occupied the event loop" is only valid when stack traces confirm synchronous JDBC on event-loop threads; a latency chart alone proves nothing.

## 10. Determining Sustainable Load Capacity

A pragmatic definition:

> **The sustainable capacity of a system for workload X, under configuration Y, is the highest offered rate verified continuously over a representative window that still meets latency, error-rate, and resource SLOs without unbounded queue growth or degrading resource accumulation.**

Always record **X** and **Y**. There is no universal "this web-runtime handles 1,000 RPS" number valid across all endpoints and environments.

### Stepped Measurement Procedure

1. **Baseline:** run idle/minimal load; verify APIs, datasets, and monitoring; record baseline CPU, heap, GC, and latency.
2. **Warm-up:** let JVM/JIT, connection pools, and caches warm up; exclude warm-up samples from capacity calculations.
3. **Steady state at target loads:** step through planned rates, holding long enough to sample p95/p99 and inspect queues. Log offered vs achieved RPS, errors, and resources.
4. **Find the knee point:** note where p95/p99 climbs steeply, achieved throughput plateaus, queues swell, or errors appear.
5. **Confirm sustainability:** re-test just below the knee for a longer duration. A 30-second burst never proves leak-free stability.
6. **Verify recovery:** drop load and check whether queues, latency, CPU, and GC return to baseline. Unrecovered resources signal leaks or wedged tasks.
7. **A/B comparison:** change one major variable at a time (e.g., `blocked` → `offloaded`) holding everything else fixed; repeat runs and avoid comparing days with differing host/proxy/DB background load.

### Good vs. Bad Conclusion Examples

Avoid writing: "The test ramped to 500 RPS, so the server handles 500 RPS." 500 might merely be `target`, with 150 dropped iterations, breached p99 SLOs, or a growing pool queue after one minute.

Write instead: "Under the **documented scenario** and **configuration**, offered load of 120 req/s held for 20 minutes achieved 119.6 req/s, kept p95 within SLO, stayed below error thresholds, and showed flat queues; 150 req/s failed as p99 breached SLO and timeouts rose. This is the observed threshold in this test setup and must be validated further against production-like mixes."

Figures above **illustrate phrasing only**, not measured outputs of this lab app.

### Little's Law and Bottleneck Intuition

Suppose four event-loop threads each get blocked for 200 ms per callback (a vastly simplified idealization ignoring overhead). One thread completes roughly 5 blocking callbacks/sec; four threads roughly 20/sec. This is an **intuitive bottleneck estimate**, not guaranteed Netty throughput or a real benchmark: real results depend on scheduling, workers, settings, pools, sockets, request mix, and clients. Offloading frees the event loop, yet capacity remains capped by boundedElastic, connection pools, and the blocking library itself.

When CPU is the bottleneck, adding threads may only increase context switching. When a database has 10 connections and queries take 200 ms, ideal DB throughput caps near 50 queries/sec regardless of how many HTTP workers you add. Use estimates to **point measurements toward the right bottleneck**, never as a substitute for empirical numbers.

## 11. Classifying Issues via a Causal Decision Tree

```text
           p95/p99 climbs as offered RPS rises
                         |
           +-------------+--------------+
           |                            |
   Is achieved RPS               Are there drops/
   close to offered?             timeouts?
           |                            |
   Inspect CPU/GC/queues         Inspect generator,
           |                     network, pools, server
   +-------+---------+
   |                 |
 High CPU       Low/moderate CPU
   |                 |
 Profile CPU    Thread dump/JFR:
 ser/logic      is event loop blocked?
   |                 |
 Size CPU       +----+-----------+
 pool           |                |
          Evidence found     Unclear
                |                |
          Isolate blocking   Inspect connection pools,
          source, re-test    proxies, locks, queues,
          at same load       upstreams, GC, timeouts
```

This is a **diagnostic guide**, not a deterministic algorithm. Bottlenecks often coexist; blocking JDBC can simultaneously stall the event loop and exhaust the DB pool. Fixing one p99 bottleneck often shifts pressure onto the next resource.

## 12. Fix the Root Cause, Not Just Symptoms

### 12.1. Blocking API Accidentally Running on the Event Loop

Buggy example:

```java
// Inside a WebFlux service; legacyRepository is a blocking API.
Mono<Report> wrong(long id) {
    return Mono.just(legacyRepository.load(id));
}
```

`legacyRepository.load(id)` runs synchronously **when creating** `Mono.just`, potentially blocking the caller thread. Switch to a lazy source and offload scheduler:

```java
// Proper isolation for a blocking API; Report/legacyRepository defined by app.
Mono<Report> better(long id) {
    return Mono.fromCallable(() -> legacyRepository.load(id))
            .subscribeOn(Schedulers.boundedElastic());
}
```

This is an **illustrative snippet** of a service holding a `legacyRepository` field and `Report` type; not a standalone compilable program. `boundedElastic` has thread and queue caps; also manage timeouts, DB pools, concurrency/bulkheads, and cancellation. When genuine non-blocking APIs exist (WebClient, compatible reactive DB drivers), keep the I/O path non-blocking rather than offloading pointlessly.

### 12.2. Heavy CPU Work Inside `map` on the Event Loop

```java
// Assumes transformCpuHeavy is defined.
Mono<Result> transformed =
        sourceMono.publishOn(Schedulers.parallel())
                  .map(this::transformCpuHeavy);
```

`publishOn(parallel())` shifts downstream execution to CPU workers, yet **never splits** one monolithic computation across cores. Utilizing multiple cores across independent items requires partitioning and bounded concurrency, e.g., `Flux.parallel().runOn(...)` or a dedicated CPU executor. Remember `parallel` is finite and can saturate under long-running computations.

### 12.3. Downstream/DB Pool Saturation

When the event loop is healthy yet requests queue on DB connections, tuning the event loop will not lift throughput. Measure `active/idle/pending` connections, acquisition times, query latency, and timeouts. Optimize queries, indexes, downstream capacity, appropriate caching, and cap concurrency within capacity; **increasing pool size is not always right**, as it can overload the database further.

### 12.4. Task Queues and Backpressure

Reactor `Schedulers.boundedElastic()` is bounded; submitting excessive blocking callables inflates queues and tail latency. With `flatMap`, cap concurrent inner subscriptions:

```java
// Illustrative code: blockingLoad(id) defined by application.
Flux.range(1, 100)
    .flatMap(id -> Mono.fromCallable(() -> blockingLoad(id))
                        .subscribeOn(Schedulers.boundedElastic()), 8);
```

`8` caps concurrent inner subscriptions **within this pipeline**, not global traffic across all HTTP requests. Production workloads need global rate limits/admission control, bulkheads, pool alignment, timeouts, and clean overload responses (such as `429` or `503` per API contract) instead of unbounded queues.

### 12.5. ThreadLocals, Context, and Tracing

When hopping schedulers, never assume `ThreadLocal` values move automatically to new threads. In Reactor, use `Context`/supported context propagation and proper observability/security integrations. When reading thread dumps, correlate request/span IDs if tracing is active; never mix up requests.

### 12.6. Timeouts, Retries, and Cancellation

Place timeouts at the right layers (HTTP client, DB, reactive pipeline, gateway) reflecting business limits. Unchecked retries **amplify load** right when downstream is struggling. Retry only appropriate failures, with backoff, attempt caps, and idempotency where needed. Client cancellation does not guarantee synchronous blocking APIs abort immediately; handle cleanup and resource limits per SDK/driver capabilities.

## 13. Load Testing Traps That Lead to False Conclusions

| Trap | Consequence | Mitigation |
|---|---|---|
| Sending a single `curl` request | Hides contention, queuing, and p99 | Test concurrently with sufficient sample distributions |
| Looking only at average latency | Masks tail latency and timeouts | Track p95/p99, max, and error rates |
| Watching `target` RPS while ignoring `dropped_iterations` | Assumes load was sent when k6 failed to launch it | Record offered, achieved, drops, and generator resources |
| Loopback test on a single host | Generator and server compete for CPU/network; differs from production network | Separate generator host when needed; document topology |
| Hot cache / unrealistically tiny responses | Inflates speed beyond real workloads | Use representative payloads and data sizes |
| Measuring right after restart without warm-up | JIT, class loading, and pool init skew p95 | Run explicit warm-up; analyze steady state |
| Raising VUs and calling it fixed req/s | Closed workloads throttle arrival rate when servers slow down | Use open arrival models to enforce offered rates |
| Skipping DB/pool/upstream metrics | Misattributes bottlenecks to event loops or CPU | Measure end-to-end and every dependency |
| Leaving verbose debug logging on during benchmarks | Logging causes blocking I/O and skews results | Control profiling/logging; note measurement overhead |
| Inflating thread pools whenever latency climbs | Adds oversubscription, queue/memory bloat, and context switching | Find the real bottleneck and set bounded limits |
| Seeing event loop `WAITING` and blaming blocking | Idle event loops also wait for events normally | Check stacks, duration, event-loop lag, and correlation |
| Stopping after short tests showing `200 OK` | Misses leaks, GC pressure, timeouts, and slow backlog buildup | Run longer stress/soak tests with errors and cleanup |
| Testing directly on uncontrolled production | Risks real outages and noisy metrics from live traffic | Use authorized test environments/windows and load caps |

## 14. Actionable Result Report Template

A solid engineering report should include:

```text
Objectives/SLOs:
  workload, target offered RPS, p95/p99, error-rate, test duration

Environment:
  commit, Java/Spring/Reactor, vCPU/RAM, CPU quotas, heap, replicas,
  proxy/TLS, DB, clients, load-generator host

Scenario:
  endpoint mix, payloads, auth, open/closed model,
  warm-up, stages, duration, generator version

Per-step observations:
  offered vs achieved RPS, dropped iterations,
  p50/p95/p99, timeouts/error statuses,
  CPU, GC, memory, event-loop lag,
  scheduler queues, HTTP/DB connection pools

Diagnostic evidence:
  timestamps, thread dumps/JFR/profilers,
  event-loop or downstream queue stacks,
  correlation with p99 spikes

Conclusions:
  load threshold meeting/failing SLO in the stated environment,
  hypotheses and evidence, current bottleneck,
  confidence level, open risks

Changes and re-verification:
  code/config changed, repeat test under identical conditions,
  impact on p95/p99/errors/throughput/resources,
  next investigation step if evidence remains incomplete
```

Example interpretation (**not actual measured data**): "Ramping from 40 to 80 req/s caused p99 on the lightweight endpoint to spike while CPU stayed below saturation. Thread dumps during latency peaks showed an event-loop thread executing `Thread.sleep` from the slow endpoint handler. After moving the callable to boundedElastic, lightweight p99 dropped in an identical test; higher throughput then hit the blocking backend's pool limit." That chain reasons from **metrics + stacks + controlled A/B tests**, never guesswork from a single chart.

## 15. Self-Check

**Q1.** If WebFlux returns `Mono<String>`, is it guaranteed to have zero blocking?  
**Answer:** No. Code inside `Mono.fromCallable`, `map`, `flatMap`, or executed prior to assembling the `Mono` can still invoke blocking APIs. Verify actual execution threads and underlying APIs.

**Q2.** Does `Thread.sleep(200)` in a handler automatically cause Reactor to throw `IllegalStateException`?  
**Answer:** Never assume so. Reactor guards specific methods like `block()` on non-blocking threads; catching `Thread.sleep` and other blocking APIs often requires BlockHound/JFR/thread dumps, within their respective compatibility and coverage limits.

**Q3.** Does moving blocking JDBC onto boundedElastic make the database client non-blocking?  
**Answer:** No. BoundedElastic threads still wait on JDBC and face worker, queue, and connection-pool limits; isolation simply keeps the event loop unblocked.

**Q4.** Why measure p95/p99 of `/lab/fast` while another endpoint is under load?  
**Answer:** To detect spillover interference across shared event loops, CPU, or shared resources. It separates "this endpoint has 200 ms business latency" from "unrelated endpoints are being stalled".

**Q5.** k6 sets `target: 100` iterations/s and reports `dropped_iterations > 0`. Can you conclude the server handles 100 RPS?  
**Answer:** No. Some scheduled requests were never initiated; check achieved RPS and load-generator/VU capacity before concluding.

**Q6.** At 50 req/s and 200 ms average system time, roughly how many requests are in-flight at steady state?  
**Answer:** By Little's Law, roughly `50 × 0.2 = 10` requests. Never substitute p99 for mean time.

**Q7.** If CPU is low and p99 is high, is the event loop definitely blocked?  
**Answer:** No. It could be waiting on downstream, connection pools, locks, or proxies/networks. Gather stacks/metrics and compare controlled runs.

**Q8.** If a load tool hits a 500 RPS peak for a few seconds, is "sustainable capacity = 500 RPS"?  
**Answer:** No. Capacity must be sustained for the target workload and environment over an adequate duration, meeting latency/error SLOs, with stable queues/resources and clean recovery.

**Q9.** When `/lab/offloaded` outperforms `/lab/blocked`, does that mean boundedElastic is the final answer for all blocking I/O?  
**Answer:** No. It proves blocking must be isolated off the event loop; you still need pool sizing, timeouts, rate limits, and evaluation of true non-blocking APIs.

## References

- [Spring Framework — WebFlux concurrency model](https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html): non-blocking assumptions, thread model, and differences from Servlet.
- [Project Reactor — FAQ: wrapping a synchronous blocking call](https://projectreactor.io/docs/core/release/reference/faq.html#faq.wrap-blocking): `fromCallable` and `subscribeOn(Schedulers.boundedElastic())`.
- [Project Reactor — Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html): `publishOn`, `subscribeOn`, `parallel`, and `boundedElastic`.
- [BlockHound — README](https://github.com/reactor/BlockHound): blocking-call instrumentation and JVM/version requirements.
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): HTTP, JVM, and system observability.
- [Reactor Netty — Reference Guide](https://projectreactor.io/docs/netty/release/reference/): event loops, connection providers, metrics.
- [Grafana k6 — Ramping arrival rate](https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/ramping-arrival-rate/): stepped open arrival scenarios.
- [Grafana k6 — Thresholds](https://grafana.com/docs/k6/latest/using-k6/thresholds/): pass/fail criteria, latency, and error rates.
- [Grafana k6 — Arrival-rate VU allocation](https://grafana.com/docs/k6/latest/using-k6/scenarios/concepts/arrival-rate-vu-allocation/): VU sizing and `dropped_iterations`.