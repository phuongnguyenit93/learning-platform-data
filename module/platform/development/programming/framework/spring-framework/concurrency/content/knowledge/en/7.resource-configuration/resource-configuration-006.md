# Estimating Capacity and Validating with Load Measurements

## 1. Goal: From Prediction to Measured Limits

In a Spring Framework application using `TaskExecutor`, especially `ThreadPoolTaskExecutor`, configuring thread counts and queues typically starts with an **estimate**: how many tasks per second must the system accept, how long does each task hold a worker, and how much parallel work can dependent services handle? You must then **validate under real load** to learn whether that estimate meets latency, error, and resource targets.

For example, consider a service receiving report-generation requests. If you look only at current CPU and set `maxPoolSize=100`, the pool may never actually reach 100 threads because the queue is still spacious, or 100 threads may contend for 10 database connections. Raising thread counts can drive up backlog, timeouts, and latency. The right approach is to formulate a quantitative hypothesis, pick a test configuration, measure across multiple load levels, and adjust settings based on the **observed bottleneck**.

Decision flow:

```text
Demand (jobs/s) + time per job + SLO
                    |
                    v
           Estimate concurrency
                    |
                    v
     Choose core / max / queue / dependency limits
                    |
                    v
          Generate controlled load
                    |
                    v
 Compare offered rate, throughput, latency, queue, errors
                    |
                    v
      Tune and re-run the same scenario
```

**Scope:** this lesson focuses on task-processing capacity in Spring executors and how to validate it with load tests. Capacity of **one instance** differs from cluster-wide multi-instance capacity; both must be distinguished during planning.

## 2. Aligning Measurement Units Before Calculating

| Quantity | Symbol | Meaning |
| --- | --- | --- |
| Offered load (*offered rate*) | `λ_in` | Tasks/second that callers **attempt** to submit |
| Accepted load | `λ_accepted` | Tasks/second actually accepted by the executor |
| Completion rate (*throughput*) | `λ_done` | Tasks completed/second over the measurement window |
| Processing time inside worker | `S` (seconds) | From when a task **starts running** to when it ends; includes time the task waits on I/O inside the worker |
| Queue wait time | `W_q` (seconds) | From task acceptance until a worker starts running it |
| Total task completion time | `W` (seconds) | Approximately `W_q + S`, excluding steps outside the measured boundary |
| Concurrent workers | `m` | Maximum threads able to process tasks at that time |
| Waiting tasks | `Q` | Length of the executor's internal queue |
| Worker busy ratio | `u` | Roughly average busy workers / available workers |

**Units must stay consistent.** If `λ=100 jobs/s` and `S=80 ms`, convert to `0.080 s` before multiplying. Averages are used for initial capacity estimation; p95/p99 percentiles are used to evaluate user-facing latency and tail latency. Never plug p95 into Little's Law and treat it as an exact formula.

A common point of confusion: an HTTP endpoint may return `202 Accepted` right after enqueueing a task. In that case `http_req_duration` measures **intake time**, not **task completion time**. To measure background processing capacity, track `submit → start → finish` separately.

## 3. Estimating from Arrival Rate and Worker Hold Time

In a sufficiently steady state, if on average `λ` tasks per second arrive and complete, and each task holds a worker for `S` seconds, the average number of busy workers is approximately:

```text
busyWorkers ≈ λ × S
```

This applies work-flow balance logic (related to Little's Law), **provided load is not building an unbounded backlog** and measurements share the same boundary. To leave room for variance, you can pick a target worker utilization `u_target` (e.g., 70%) and estimate:

```text
m_initial = ceil((λ × S) / u_target)
```

The value `u_target` is a **design assumption** for headroom, not a mandatory rule of Java/Spring. Nor is it a **direct formula** for CPU utilization: a worker may spend most of its time waiting on the network or database.

### Hand Calculation Example

Suppose one instance expects 100 tasks/second; initial measurements show each task holds a worker for 80 ms on average (`S=0.08 s`). You want target worker utilization around 70%:

```text
busyWorkers    = 100 × 0.08 = 8
m_initial      = ceil(8 / 0.70) = 12
idealCeiling   = 12 / 0.08 = 150 tasks/s
```

Interpretation:

- At 100 tasks/s, roughly **8 workers** are busy simultaneously on average if `S` stays stable.
- **12 workers** is a starting point for experiments, not a conclusion that production must use exactly 12.
- **150 tasks/s** is an ideal mathematical ceiling if every worker always finishes a task in 80 ms with zero contention and no increase in `S` at higher concurrency. SLO-compliant capacity is typically **lower** than this ceiling.
- If the workload is purely CPU-bound, 100 tasks/s × 80 ms of CPU each demands roughly 8 CPU-seconds/second before overhead; 12 threads cannot substitute for missing CPU capacity. If the 80 ms is mostly I/O wait, fewer CPUs may be needed, while connection/I/O limits become the primary constraint.

### Java 17+ Program to Compute the Starting Point

Save the following as `CapacityEstimate.java`:

```java
import java.util.Locale;

public final class CapacityEstimate {
    public static void main(String[] args) {
        double arrivalRate = 100.0;       // jobs/second
        double workerSeconds = 0.080;     // seconds/job, excluding queue wait
        double targetWorkerUse = 0.70;    // headroom assumption

        double busyWorkers = arrivalRate * workerSeconds;
        int proposedThreads = (int) Math.ceil(busyWorkers / targetWorkerUse);
        double idealCeiling = proposedThreads / workerSeconds;

        System.out.printf(Locale.ROOT,
                "busy workers = %.1f%n", busyWorkers);
        System.out.println("initial threads = " + proposedThreads);
        System.out.printf(Locale.ROOT,
                "ideal ceiling = %.0f jobs/s%n", idealCeiling);
    }
}
```

Run with JDK 17 or later:

```bash
javac CapacityEstimate.java
java CapacityEstimate
```

Deterministic stdout:

```text
busy workers = 8.0
initial threads = 12
ideal ceiling = 150 jobs/s
```

The program **only computes a hypothesis**. It does not measure queues, error rates, external services, or p95 latency. Those values must come from load tests.

## 4. Estimating Queue Depth and Wait Time During Bursts

A bounded pool can absorb a brief arrival spike by queueing. Given a **measured** sustainable completion capacity `μ` (jobs/s), if a burst arrives at `λ_peak > μ` with no other special conditions, the backlog grows by roughly:

```text
backlogAdded ≈ (λ_peak - μ) × durationSeconds
```

**Hypothetical illustrative** example: suppose the system truly sustains 150 jobs/s without slowing down. A 180 jobs/s burst lasting 5 seconds can add roughly `(180-150)×5 = 150 jobs` to the backlog. If load then drops to 100 jobs/s while capacity stays 150 jobs/s, the backlog can drain at a net rate of roughly 50 jobs/s, needing nearly 3 seconds to clear 150 jobs. This is a **simplified model** that omits processing-time distributions, arrival variance, rejections, and capacity degradation under overload.

A 200-slot queue **can hold 150 jobs** in the example above, yet "can hold" does not mean "meets SLO": jobs at the tail of the burst wait much longer. Overly long queues sometimes keep error rates low briefly while producing timeouts or results arriving too late to be useful.

From Little's Law in steady state:

```text
L_system = λ_done × W
```

`L_system` is the average number of tasks in the **entire measured scope** (waiting + running), and `W` is the average time from entering to leaving that scope. For example, if the system completes 100 jobs/s with an average completion time of 0.25 s, roughly 25 tasks coexist in the system on average. **Never use steady-state equations to justify an ever-growing queue under overload**.

## 5. Applying the Hypothesis to ThreadPoolTaskExecutor

Spring's `ThreadPoolTaskExecutor` wraps `java.util.concurrent.ThreadPoolExecutor`. Three parameters govern load intake:

- `corePoolSize`: while workers are below core, the pool usually creates a new worker for incoming tasks.
- `queueCapacity`: once core is reached, the pool usually prefers placing tasks into the queue if space remains.
- `maxPoolSize`: the pool scales beyond core only when **the queue cannot accept more tasks**. Once the queue is also full and max is reached, tasks may be rejected.

Therefore **you cannot choose `maxPoolSize` independently of `queueCapacity`**. The defaults of the `ThreadPoolTaskExecutor` class are core 1, very large max, and very large queue; never treat those as a validated production setup. Spring Boot has its own auto-configuration depending on conditions/versions, so inspect the bean **actually** used by `@Async` or your services.

First example configuration for a fixed 12-worker scenario with a bounded queue in a Spring application:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
public class WorkerCapacityConfig {
    @Bean("reportExecutor")
    public ThreadPoolTaskExecutor reportExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(12);
        pool.setMaxPoolSize(12);
        pool.setQueueCapacity(200);
        pool.setThreadNamePrefix("report-");
        return pool;
    }
}
```

This is a **Spring configuration class**, requiring compatible `spring-context` and registration into an `ApplicationContext`; it does not compile standalone with the JDK alone. The container manages the bean lifecycle. This configuration is a **test hypothesis**, not advice for every system to use 12/12/200.

Setting core=max makes initial measurements easier to interpret: the pool has no "wait for queue to fill before growing to max" phase. Once you have data, you can compare smaller core, larger max, and smaller queue to improve burst absorption. Just keep the **core → queue → max → rejection** order in mind: if the queue is too wide, a large max may never create extra concurrency.

`TaskExecutor.execute(Runnable)` only hands off work; it does not promise task completion. For async tasks needing completion-time statistics, measure **inside the worker**, not just the return duration of `execute`.

## 6. The Real Bottleneck Is Not Necessarily Thread Count

Before enlarging a pool, ask which resource each task waits on:

| Load Type | What May Saturate First | Consequence of Adding Threads |
| --- | --- | --- |
| CPU-bound computation | CPU cores, container CPU quota, GC | Too many threads cause context switching, contention, and higher latency |
| Database queries | Connection pool size, locks/query plans, IOPS | Extra threads just wait together on connections or locks |
| Outbound HTTP calls | Connection pools, timeouts, partner quotas/rate limits | More concurrent calls can trigger throttling and retries |
| File read/write tasks | Disk throughput, latency, file descriptors | Adding threads cannot bypass I/O limits |
| Synchronized systems | Lock contention, critical sections, shared state | Worker count rises while throughput stays nearly flat |

If a pool has 40 threads while the database grants only 10 connections and each task needs one throughout processing, adding threads may simply raise connection wait time. An executor accepting more tasks **does not prove the business layer actually processed more tasks**.

With multiple instances, also calculate total load on dependencies. For example, 4 pods × 12 threads = up to 48 concurrent tasks entering the processing block; if each task holds a connection, the cluster-wide database pool and DB limits must handle it. Scaling replicas can also increase total connections and retry rates.

## 7. Defining Acceptance Criteria Before Load Testing

A measurement is only meaningful when you know what "good enough" looks like. Example **hypothetical targets** for a job-creation endpoint:

- At **100 job-intake requests/second** on the specified infrastructure setup, at least 99.9% of valid jobs are accepted and eventually completed, verified for zero lost or duplicate work per business contract.
- `p95` of **end-to-end completion time** does not exceed **1 second**, not just HTTP `202` return time.
- **Zero task rejections** at target load; if `queueSize` rises during bursts, it must return to baseline afterward.
- CPU, heap, GC, connection pools, and external service quotas retain agreed headroom.

These numbers only illustrate **how to state criteria**, not default Spring SLOs. Substitute real operational requirements and specify the sustained test duration. Passing SLOs at 100 jobs/s does not imply passing at 150 jobs/s.

**Crucially:** separate "request accepted" from "job processed successfully." If HTTP returns 202 while the task hits `TaskRejectedException` and disappears, HTTP graphs can look healthy while business outcomes fail.

## 8. Designing a Reproducible Load Test Plan

A load test plan should include these phases, executed in an environment authorized for load generation:

| Phase | Purpose | Signals to Observe |
| --- | --- | --- |
| Warm-up | Warm JVM/JIT, connections, caches, threads | Latency stabilizes; avoid confusing startup cost with steady state |
| Low baseline | Measure `S` with minimal contention | Worker time, throughput, CPU/GC, DB/API times |
| Step-up load | Find the near-linear scaling region | Accepted/done rates, p95/p99, active threads, queue |
| Sustained target load | Verify steady SLO compliance | Backlog does not climb continuously, low errors, stable GC/CPU/connections |
| Short burst | Evaluate queue limits and recovery | Rejections, peak queue, queue-wait, drain time |
| Controlled overload | Find SLO breaking point and protection behavior | Timeouts, `TaskRejectedException`, downstream errors, retry amplification |
| Recovery / soak | Verify return to normal and check for leaks | Pool/queue return to baseline, memory does not grow unbounded, pending tasks finish |

For fair comparisons between configs, keep task types, payloads, test data, instance counts, CPU/memory quotas, connection pools, cache state, and measurement methods constant. Record the exact config for every run. Changing data, network, and `maxPoolSize` simultaneously makes it hard to tell what caused an improvement or regression.

Load generators also have limits; watch the generator's CPU/network and actual emitted request rate. Use representative payloads: a `"sleep 10ms"` dummy task cannot stand in for a real report running multiple DB queries or file encryption.

## 9. k6 Example: Measuring Incoming Load in Jobs/Second

Tools like **Grafana k6** support the `constant-arrival-rate` scenario: starting iterations at a target rate relatively independently of response times. This helps test "can the server handle 100 requests/second?" A fixed-VU model can **throttle itself** when the server slows down, masking overload points.

Suppose the test app has an **illustrative** API `POST /api/jobs` returning `202` after accepting a job. Create `load.js`:

```javascript
import http from 'k6/http';
import { check } from 'k6';

export const options = {
  scenarios: {
    jobs: {
      executor: 'constant-arrival-rate',
      rate: Number(__ENV.RATE || '50'),
      timeUnit: '1s',
      duration: '4m',
      preAllocatedVUs: 100,
      maxVUs: 250
    }
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<500'],
    dropped_iterations: ['count==0'],
    checks: ['rate>0.99']
  }
};

export default function () {
  const payload = JSON.stringify({
    requestKey: 'perf-' + __VU + '-' + __ITER
  });

  const response = http.post(
    __ENV.BASE_URL + '/api/jobs',
    payload,
    { headers: { 'Content-Type': 'application/json' } }
  );

  check(response, {
    'accepted with 202': (r) => r.status === 202
  });
}
```

This is a **k6 script independent of Java**, yet it **runs accurately only when the test environment exposes `/api/jobs` with the 202 contract and payload shown**. If your real API differs, adjust the path, payload, auth, and success checks before measuring. Do not aim it directly at a live user-facing system without a proper test plan.

On a machine with k6 installed, you can test controlled levels individually:

```bash
k6 run -e BASE_URL=http://localhost:8080 -e RATE=20 load.js
k6 run -e BASE_URL=http://localhost:8080 -e RATE=50 load.js
k6 run -e BASE_URL=http://localhost:8080 -e RATE=100 load.js
k6 run -e BASE_URL=http://localhost:8080 -e RATE=140 load.js
```

These commands illustrate **separate test runs**, not pre-baked output. Run each level only after the environment returns to baseline; never blindly step up load when unsafe signals appear or permitted limits are exceeded.

Here `rate` means **iterations/second**. Each iteration performs one HTTP POST, approximating requests/second as long as sufficient VUs exist and network is unconstrained. Rising `dropped_iterations` may stem from k6 running out of VUs or the server slowing so much that VUs do not free up; do not immediately blame the Spring executor. The template omits `sleep()` at iteration end because `constant-arrival-rate` already paces submissions.

The `p(95)<500` threshold in the script checks only **HTTP admission latency** under 500 ms; it does not verify when jobs finish running. You must collect business metrics or poll job status (if supported by the contract) to verify end-to-end SLOs, completion rates, correctness, and lost work.

## 10. Metrics to Observe Simultaneously

During test runs, plot time series aligned to the **same timestamps**:

| Group | Suggested Metrics | Question Answered |
| --- | --- | --- |
| Incoming load | tasks submitted/s, HTTP RPS, k6 offered rate | How much work is being sent to the system? |
| Admission | tasks accepted/s, rejected/s, HTTP 2xx/4xx/5xx | How much work actually enters the queue/pool? |
| Processing | tasks completed/s, failed/s | What is the real completion capacity? |
| Executor | active threads, current pool size, queue size/capacity | Is the pool busy or is the queue piling up? |
| Timing | queue wait, execution time, end-to-end p50/p95/p99 | Which stage are users waiting in? |
| JVM | CPU, GC pauses, heap, live threads | Is the runtime the bottleneck? |
| Dependencies | active/pending DB connections, query latency, outbound HTTP latency/quotas | Are tasks stalling on DB/external services or the executor? |
| Load client | actual iterations/s, dropped iterations, VUs, generator CPU | Is the load generator emitting the target load? |

In `ThreadPoolTaskExecutor`, APIs like `getActiveCount()`, `getPoolSize()`, `getQueueSize()`, and `getThreadPoolExecutor().getCompletedTaskCount()` provide point-in-time readings (approximate under high concurrency). Micrometer includes binders for properly registered executors; **do not assume every bean automatically exports full metrics** in every plain Spring setup.

To measure **queue wait** more accurately, wrap tasks: record `submittedAt` before calling `execute`, `startedAt` inside `Runnable.run()`, and `finishedAt` in `finally`, then compute `startedAt - submittedAt` and `finishedAt - startedAt` using `System.nanoTime()`. Also record rejected/failed branches so samples do not skew toward successful tasks. When recording metrics, avoid high-cardinality tags like per-`requestId`.

**Watch trends, not just snapshots.** `queueSize=100` at one instant could be a brief burst about to drain; a queue moving 100 → 150 → 200 over minutes at steady load indicates backlog is not draining.

## 11. Interpreting Results and Deciding Adjustments

Analyze using the symptom table:

| Symptom Under Load | Hypothesis to Check | Controlled Trial Action |
| --- | --- | --- |
| Queue grows, active threads near core, below max | Queue is still spacious so pool has not scaled past core | Revisit core and queue; re-measure tail latency |
| Queue full, active threads near max, rejections rising | Load exceeds actual capacity | Reduce offered rate, add admission limits, optimize tasks, consider real capacity scaling |
| CPU near quota, high context switches, adding threads gives no throughput gain | CPU-bound/overthreading | Reduce concurrency or add CPU; measure CPU time/task |
| Low CPU yet busy threads, DB pool waiting for connections | Database/connection pool bottleneck | Optimize queries, shorten connection hold time, adjust limits |
| HTTP returns 202 quickly while job completion time climbs | Downstream queue/workers are congested | Measure end-to-end latency and backlog, not just HTTP p95 |
| Adding threads worsens p99 and increases downstream errors | Increased dependency pressure or contention | Compare under same load with prior config; cap concurrency |
| Queue drains after burst, p95 recovers, zero lost jobs | Burst absorption and recovery look good | Re-verify with longer bursts and different background loads |
| k6 dropped iterations rise | Generator/VU shortage or slow server | Inspect generator limits and latency before concluding capacity |

Distinguish four capacities:

1. **Admission capacity:** the rate at which the system can accept requests/tasks before starting to error.
2. **Processing capacity:** the rate at which tasks actually complete accurately.
3. **SLO capacity:** the highest rate that still meets latency, error, recovery, and resource requirements.
4. **Burst tolerance:** the short-term excess load that queues, deadlines, and rejection policies keep under control.

Operational planning usually relies on **SLO capacity**, which is lower than "how fast tasks can be pushed into a queue" or "how many threads can be spawned."

## 12. When Can You Conclude It Is Validated?

A configuration can be provisionally accepted when test runs representing expected load show:

- **Submission rate, acceptance rate, and completion rate** are all observed; HTTP 202 is not treated as proof of task completion.
- During sustained target load, completion throughput keeps up with valid offered rate, backlog does not grow unbounded, and p95/p99 and errors meet defined SLOs.
- CPU, heap, GC, DB/API connections, retries, pool sizes, and queues are evaluated with realistic data types and expected instance counts.
- Under bursts or controlled overload, the system rejects/throttles per clear policy and recovers cleanly without silently dropping or duplicating jobs outside contract.
- Results are reproducible and saved alongside build version, executor config, dependency pool sizes, load levels, test duration, and charts; re-test whenever parameters change.

**Note:** load tests do not prove every future condition is safe. Changes in data sizes, cold caches, downstream outages, GC, networking, and processing-time distributions can shift capacity. Estimation + measurement is a continuous calibration loop, not a one-shot formula.

## 13. Common Mistakes

1. **Multiplying CPU cores by a fixed constant for every workload's thread pool.** Measure worker hold time, CPU/I/O wait ratio, and dependency limits instead.
2. **Plugging p95 instead of mean time into Little's Law.** The law uses steady-state averages; p95 is a separate latency constraint.
3. **Raising `maxPoolSize` while keeping a huge queue.** The pool may stay near core forever because the queue never fills.
4. **Measuring only HTTP latency for async tasks.** Track actual completion time and job success rate.
5. **Confusing submission rate with throughput.** If 200 jobs/s arrive while only 120 jobs/s finish, backlog/errors will accumulate.
6. **Load testing for only 15 seconds and declaring sustainable capacity.** Systems need warm-up and enough time to expose queue growth, GC, or dependency saturation.
7. **Using fixed VUs without checking arrival rate.** When the server slows, occupied VUs reduce send rate and mask overload.
8. **Huge queues to avoid rejections.** Large backlogs cause timeouts, memory pressure, and work expiring before execution.
9. **Adding threads without watching the database and external APIs.** Executor improvements may simply push the bottleneck to a dependency.
10. **Failing to verify load generator capacity.** Dropped iterations from an underpowered generator distort capacity numbers.
11. **Comparing two configs on different environments.** Pod counts, CPU quotas, data, caches, and networking can invalidate comparisons.
12. **Looking only at peak throughput.** A config might push more for a few seconds while violating p99, error rates, or failing to recover.

## 14. Self-Check Questions

**Q1.** You have 100 jobs/s, each occupying a worker for 80 ms on average, and want worker utilization around 70%. How many workers should you test first?  
**Answer:** `ceil((100×0.08)/0.70)=12` workers; that is only an initial hypothesis.

**Q2.** You set `core=4`, `max=32`, and a very large queue. When 4 workers are busy, will the pool immediately scale to 32?  
**Answer:** Usually no. It prefers queueing while the queue still accepts tasks.

**Q3.** At 120 jobs/s, the app returns HTTP 202 120 times/s yet completes only 70 jobs/s. Can you claim 120 jobs/s capacity?  
**Answer:** No. Admission rate and processing rate differ; backlog may grow or tasks fail/drop.

**Q4.** Why can raising workers from 12 to 40 worsen p99 even when CPU stays low?  
**Answer:** Tasks may contend for DB connections, locks, API quotas, or trigger more timeouts/retries.

**Q5.** In one test the queue grows for a minute then drains back to baseline; in another, the queue keeps growing at the same offered rate. Are these two situations alike?  
**Answer:** No. One may be an absorbed burst; the other indicates completion capacity cannot keep up with incoming load.

**Q6.** Which metrics distinguish real service capacity from load-generator capability?  
**Answer:** Compare offered iterations/s, dropped iterations, accepted/s, completed/s, and errors/latency on both the load generator and server.

### Reference Documentation

- [Spring Framework — ThreadPoolTaskExecutor JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Java SE 17 — ThreadPoolExecutor: core/max, queue, rejection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
- [Micrometer — JVM and Executor metrics](https://docs.micrometer.io/micrometer/reference/1.12/reference/jvm.html)
- [Grafana k6 — Constant arrival rate](https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/constant-arrival-rate/)
- [Grafana k6 — Open and closed load models](https://grafana.com/docs/k6/latest/using-k6/scenarios/concepts/open-vs-closed/)
- [Grafana k6 — Thresholds](https://grafana.com/docs/k6/latest/using-k6/thresholds/)
