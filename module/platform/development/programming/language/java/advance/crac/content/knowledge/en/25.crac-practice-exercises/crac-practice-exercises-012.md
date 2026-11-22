# Building a Performance Report and Acceptance Criteria for a Sample Application

An application using CRaC only has operational value when checkpoint and restore improve the time to bring the service into a serving state while maintaining the required behavior and performance. To prove this, measurements must be taken on the same application, with the same workload and a controlled environment; then the results must be presented in a repeatable report with clear conditions for deployment acceptance.

This practice exercise guides you through building a performance report for a sample Java application with HTTP endpoints. We compare the normal JVM startup path with the restore path from a CRaC checkpoint, while also measuring checkpoint creation cost, image size, post-ready performance, and recovery capability when dependencies change.

A good report must answer the following questions:

- How much faster does restore bring the application to a ready state compared to a cold start?
- Is the time from process creation to readiness opening measured consistently?
- Is the first request after restore abnormally slow?
- Do throughput, latency, and error rate during steady-state operation change?
- How much CPU, memory, disk, and time do checkpoint/restore consume?
- Are the results repeatable across multiple runs and multiple instances?
- Which functional, compatibility, and operational conditions must be met before acceptance?

The numbers in the example results of this article are illustrative data for practicing how to calculate and present results. They are not benchmarks run on a specific JDK, CRIU, or hardware. When deploying, replace them with data measured from your environment.

## 1. Define measurement goals and scope

Before running benchmarks, clearly state the goal. If the goal is to reduce scale-out time, the primary measurement is the time from instance creation to when the instance receives traffic. If the goal is to reduce startup time after deployment, measure from when the process starts until both readiness and dependencies are ready. If the goal is to reduce recovery time after node failure, also measure failure detection time, provisioning a new instance, downloading the image, restoring, and opening traffic.

Do not lump everything into a single “startup time” number. Each phase can have a different bottleneck.

### Distinguish milestones

| Milestone | Definition | What it reflects |
|---|---|---|
| Process start | The time the OS creates the JVM process | Process creation and runtime loading cost |
| JVM ready | The JVM completes the required runtime initialization | JVM initialization cost |
| Application ready | The application completes initializing beans, routes, and local resources | Application initialization cost |
| Dependency ready | Database, broker, secret provider, and required dependencies are connected | Integration recovery cost |
| Readiness open | The instance is allowed to receive traffic | Time serving begins |
| First successful response | The first request completes successfully | Cold path/first request cost |
| Steady state | The system has passed the warm-up phase and load is stable | Long-term serving performance |

For scale-out goals, use `process start → readiness open` as the primary milestone and report `readiness open → first successful response` separately. For end users, first response may matter more than the readiness timestamp if the probe only checks a very lightweight endpoint.

### Metric groups

Divide metrics into four groups:

1. **Startup and recovery:** cold-start-to-ready, restore-to-ready, first-request latency, and dependency recovery time.
2. **Serving performance:** throughput, latency percentiles, error rate, and resource utilization.
3. **Checkpoint cost:** checkpoint duration, image size, CPU, memory, I/O, and storage capacity.
4. **Reliability:** checkpoint/restore success rate, business correctness, multi-instance restore capability, and behavior when dependencies are unavailable.

Do not use a single isolated metric to make a decision. Fast restore-to-ready with failing requests or severely degraded throughput means the application has not passed.

## 2. Describe the sample application

To make results comparable, use a Java application with deterministic behavior and a stable workload. For example, the application provides:

- `GET /health/live`: confirms the process and event loop are still active.
- `GET /health/ready`: returns success only when required resources are ready.
- `GET /api/catalog/{id}`: returns catalog data of a fixed size.
- `POST /api/compute`: performs a CPU computation of controlled duration.
- `GET /metrics`: exports runtime and application metrics.

If the sample application uses Spring Boot, Quarkus, Micronaut, or another framework, record the version and configuration. Do not change frameworks between baseline and CRaC because startup and runtime costs can differ significantly.

### Characteristics to keep fixed

| Component | Sample configuration |
|---|---|
| Java runtime | Same JDK distribution, version, and build |
| Application | Same artifact SHA-256 |
| Framework | Same version and profile |
| HTTP server | Same implementation and port configuration |
| Dependencies | Same database/broker or same test double |
| Dataset | Same data, response size, and cache state |
| CPU/memory | Same host class and container limits |
| JVM flags | Identical, except for options required for CRaC |
| Logging | Same log level and appender |
| Workload | Same request mix, concurrency, and duration |

If the checkpoint is created after the application has warmed up caches or JIT, the baseline must be clearly described. A checkpoint can be created after an intentional warm-up phase, but do not compare it against an unwarmed cold start and conclude the entire difference is due to CRaC. Report the benefit of retained warmed-up state separately.

### Dependencies in the practice exercise

You can choose one of two types:

**Local test double:** suitable for measuring the JVM/framework and request path in isolation. Data is served from memory or a stable mock service. Results do not fully represent a production environment with a database/broker.

**Real dependencies in a test environment:** suitable for measuring realistic readiness and reconnection. Database, broker, secret manager, and network must keep the same configuration across runs. Specify whether dependencies are restored together with the application or remain independent services.

Do not mix both types in the same result table without distinguishing them. Each dependency configuration is a separate benchmark scenario.

## 3. Define the baseline and execution paths

At least two execution paths are needed:

**Baseline cold start:** launch a new JVM with a production-like command, wait for readiness to open, and measure the first response.

**CRaC restore:** create a checkpoint from an initialized application following a defined procedure, then restore the image and measure from restore start time to readiness and first response.

To fully understand costs, add:

- Time to start a new JVM and create the initial checkpoint.
- Time to package, transfer, and extract the image if the deployment pipeline includes these steps.
- Restore time on the same host and on a compatible target host.
- Post-restore warm-up time if JIT/cache are not in an equivalent state.

### Intervals to report separately

| Metric | Start point | End point |
|---|---|---|
| Cold start to ready | New JVM process starts | Readiness opens |
| Restore to ready | Restore command starts | Readiness opens |
| First request latency | First request sent after readiness | Complete response received |
| Checkpoint duration | Checkpoint request starts | Runtime confirms checkpoint complete |
| Artifact preparation | Packaging/transfer/verification starts | Image is ready for restore |
| Restore total deployment time | Instance provisioning/image download starts | Instance receives traffic |
| Warm-up duration | Readiness opens or warm-up starts | Steady-state criteria reached |

If you only measure the time the `java` command returns, you may miss the time when the application is not yet ready. If you measure from deployment start without separating image download time, it is hard to tell whether CRaC's benefit is offset by artifact transfer cost.

### Measurement workflow diagram

~~~mermaid
flowchart TD
    A[Prepare the same artifact and environment] --> B[Run cold-start baseline]
    B --> C[Measure readiness and first response]
    C --> D[Warm up according to scenario]
    D --> E[Create checkpoint]
    E --> F[Measure checkpoint time and image size]
    F --> G[Restore from image]
    G --> H[Measure restore-to-ready and first response]
    H --> I[Run steady-state workload]
    I --> J[Collect latency throughput errors CPU memory]
    J --> K[Repeat measurements]
    K --> L[Compile report and apply criteria]
~~~

## 4. Design a repeatable workload

The workload must reflect the types of requests the application actually serves. An endpoint that only returns `200 OK` may measure the HTTP server but does not reflect database, serialization, cache, or CPU work.

### Define the request mix

Example workload:

| Request | Weight | Purpose |
|---|---:|---|
| `GET /api/catalog/{id}` | 70% | Data reading and serialization |
| `POST /api/compute` | 20% | Measure CPU path |
| `GET /health/ready` | 10% | Check serving status |

This is only a sample mix. Replace the ratios with your application's request mix. If endpoints have different payloads, record request/response sizes and input data.

### Define concurrency and duration

A benchmark configuration might include:

- 1 client to measure single-request latency.
- 10, 50, and 100 concurrent clients to observe scalability.
- 5 minutes warm-up.
- 10 minutes steady-state measurement.
- At least 5 independent runs per scenario; for noise-sensitive benchmarks, increase the number of runs.

Do not treat these sample numbers as mandatory standards. Choose concurrency and duration based on expected load, environment limits, and enough time for metrics to stabilize.

### Separate first request from steady state

The first request after restore may incur lazy initialization, class loading, JIT compilation, DNS lookup, or connection creation costs. Record separately:

- First request after readiness.
- Requests in the first 30–60 seconds.
- Steady-state after warm-up.

If you only take the average over the entire long test, high latency of the first few requests may be hidden.

### Avoid unintended load on dependencies

If every request creates a heavy query or a new message, the benchmark may measure the database/broker instead of the application. Keep data, indexes, caches, and dependency state stable. Monitor dependencies as well to know where the bottleneck lies.

## 5. Collect startup and readiness times

Readiness must reflect the actual conditions required to serve traffic. The readiness endpoint should not return `200` just because the HTTP server opened a port if the database pool, secret provider, or required consumer is not ready.

### Log timestamps from the application

Record milestones using structured logs:

~~~text
event=process_started
event=application_context_ready
event=crac_after_restore_started
event=dependencies_ready
event=readiness_open
event=first_request_completed
~~~

Each event should include a UTC timestamp, checkpoint ID, restore attempt ID, incarnation ID, and application build. Do not log secrets or sensitive request data.

Within the same process, use `System.nanoTime()` to measure elapsed duration. Use `Instant.now()` or log timestamps to correlate across hosts. Do not subtract wall-clock timestamps between two machines without handling clock skew.

Example:

~~~java
long startedAt = System.nanoTime();
initializeDependencies();
long elapsedNanos = System.nanoTime() - startedAt;

logger.info("event=dependencies_ready elapsed_ms={}",
        elapsedNanos / 1_000_000);
~~~

For the time from process start to readiness, you can log a timestamp in the entrypoint/orchestrator and the readiness event in the application. Ensure both use synchronized clocks; even better, use an external measurement based on the same clock.

### Measure externally

A script can poll readiness and record start/end timestamps:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

READY_URL="http://127.0.0.1:8080/health/ready"
START_NS=$(date +%s%N)

until curl --silent --fail "$READY_URL" >/dev/null; do
  sleep 0.05
done

END_NS=$(date +%s%N)
ELAPSED_MS=$(( (END_NS - START_NS) / 1000000 ))
printf 'readiness_elapsed_ms=%s\n' "$ELAPSED_MS"
~~~

This is an example for Linux with GNU `date` supporting `%N`. On other operating systems, use an appropriate monotonic timer. A polling script has finite resolution; record the poll interval and do not interpret results as more precise than that resolution.

Place the start point immediately before the cold start or restore command, not after the process has already appeared. If measuring end-to-end deployment time, start from the instance creation/image download operation.

### Measure first response

After readiness opens, send a representative request and record the time:

~~~bash
curl --silent --show-error --output /dev/null \
  --write-out 'http_code=%{http_code} total_seconds=%{time_total}\n' \
  http://127.0.0.1:8080/api/catalog/42
~~~

Run the same request, payload, client location, and connection policy for baseline and restore. If connection reuse is enabled on one side and not the other, first-request results are no longer comparable.

## 6. Measure throughput, latency, and error rate

Startup improvement is only part of the benefit. You must confirm the application serves stably after restore.

### Latency percentiles

Report at least:

- p50: latency of a typical request.
- p90 or p95: latency of the majority of requests.
- p99: tail latency.
- Maximum: use only together with request count and context to understand outliers.

Do not report only the average. A few very slow requests can be masked by the mean.

### Throughput

Throughput is the number of requests completed per unit of time, usually requests/second. Record concurrency, duration, request mix, and completed request count. When the client saturates CPU or network, measured throughput may reflect the limit of the load generator.

### Error rate

Categorize errors:

- HTTP 5xx.
- Unexpected HTTP 4xx.
- Timeout or connection reset.
- Requests rejected due to readiness.
- Business errors or incorrect response data.

Do not count all HTTP 4xx as system errors if some codes are valid outcomes of the workload. Define errors before running.

### Example using hey

`hey` is an HTTP load generation tool. Example:

~~~bash
hey -z 10m -c 50 -m GET \
  http://127.0.0.1:8080/api/catalog/42
~~~

This command runs for 10 minutes with 50 concurrent workers against a GET endpoint. Record the `hey` version, load generator host, CPU/network of the load generator, and raw output. For complex request mixes, use k6, Gatling, or a tool suitable for payloads and authentication.

### k6 example

~~~javascript
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  vus: 50,
  duration: '10m',
  thresholds: {
    http_req_failed: ['rate<0.001'],
    http_req_duration: ['p(95)<200', 'p(99)<500'],
  },
};

export default function () {
  const response = http.get('http://127.0.0.1:8080/api/catalog/42');
  check(response, {
    'status is 200': (r) => r.status === 200,
  });
  sleep(0.1);
}
~~~

The thresholds in the example are placeholders to illustrate syntax. Replace them with your application's SLO/criteria and specify the time unit used by the tool version.

Do not run the load generator on the same host running the JVM if doing so causes CPU or memory contention. Prefer a dedicated load generator machine or explicitly document shared resources.

## 7. Measure resources and checkpoint cost

Beyond latency, CRaC can change resource usage. Checkpoint images consume storage; checkpoint/restore can create CPU and I/O bursts; retained warm-up state can make heap or RSS larger.

### Resource metrics

| Metric | Interpretation |
|---|---|
| CPU usage | CPU consumed during startup, checkpoint, restore, and steady-state |
| RSS | Resident memory of the process |
| Heap used/committed | Heap memory in use and heap committed by the JVM |
| Native memory | Thread stacks, direct buffers, native libraries, and runtime allocations |
| Peak memory | Highest level during a phase |
| Disk read/write | I/O for reading/writing checkpoint images |
| Checkpoint image size | Size of the stored image |
| Restore read volume | Volume read to restore the image |
| File descriptors/threads | Count after restore compared to baseline |

RSS, heap used, and heap committed are different quantities. Do not infer RSS solely from heap usage. Use OS/container metrics alongside JVM metrics.

### Reference Linux commands

~~~bash
/usr/bin/time -v java -jar app.jar
~~~

`time -v` reports wall time, CPU time, maximum resident set size, and several process details. To measure restore, apply it to the corresponding restore command for your JDK distribution.

If the process is already running:

~~~bash
ps -o pid,etime,%cpu,%mem,rss,vsz,nlwp,cmd -p <pid>
cat /proc/<pid>/status
~~~

In containers, also read cgroup metrics to know actual limits and usage. On Kubernetes, record CPU/memory requests and limits, node type, and throttling status.

### Checkpoint size

Record:

- Image directory size after checkpoint.
- Archive size if packaged.
- Compressed size.
- Packaging and extraction time.
- Network transfer time.
- Number of retained images and retention policy.

Compression can reduce storage/network but increases CPU and latency. Measure compression/decompression time as well if it is part of the deployment pipeline.

### Checkpoint overhead

Measure the time from checkpoint request to completion. Also record the time the application does not receive traffic, the number of queued/rejected requests, and the impact on dependencies. A very fast checkpoint that drops requests or causes transaction timeouts cannot be considered free.

If the checkpoint is created after draining traffic from the application, measure drain duration and checkpoint engine duration separately to know the total interruption time.

## 8. Design the test matrix

A clear matrix helps detect cases where CRaC works in one environment but fails in another.

| Scenario | How to run | Purpose |
|---|---|---|
| S1 — Cold start | New JVM, no checkpoint | Baseline |
| S2 — Restore same host | Restore image on the compatible host where it was created | Measure basic benefit |
| S3 — Restore target host | Transfer image to a supported target host | Measure distribution cost and portability within supported scope |
| S4 — First request | Measure the first request after readiness | Detect lazy initialization |
| S5 — Steady state | Fixed workload after warm-up | Compare serving performance |
| S6 — Concurrent restore | Restore multiple instances simultaneously | Measure CPU, disk, network, and coordination burst |
| S7 — Dependency unavailable | Secret manager/database/broker temporarily fails | Verify readiness and retry |
| S8 — Repeated restore | Restore multiple times from the same image per scenario | Detect stale state or resource leaks |
| S9 — Fresh checkpoint | Create a new image after build/config changes | Verify image creation workflow |

Not every combination is supported. For example, restoring to a different host must follow compatibility constraints of JDK, CRIU, kernel, architecture, and application resources. Clearly state which scenarios are within the supported scope.

### Number of runs and aggregation

A practical workflow:

1. Run at least one pilot run to catch configuration errors.
2. Warm up under the same policy.
3. Run at least 5 independent runs for each critical scenario.
4. If results vary widely, increase the number of runs and investigate noise sources.
5. Report median, p95 across runs, or an appropriate sample distribution.
6. Keep raw results so calculations can be recomputed.

For startup time, each run is one independent sample. For request latency, thousands of requests in a single run are not equivalent to thousands of independent startups. Do not mix these two sample types in the same statistic.

### Control test order

Do not always run cold start first and CRaC second if the host warms up over time. Interleave or randomize scenario order to reduce bias from thermal state, filesystem cache, CPU frequency, and background load.

If benchmarking on a shared host, record background load and avoid running updates, backups, or other tasks during measurement.

## 9. Calculate and present results

Choose a consistent unit, such as milliseconds for startup/latency and requests/second for throughput.

### Time improvement

With:

- \(T_c\): cold-start-to-ready.
- \(T_r\): restore-to-ready.

Time reduction percentage:

\[
\text{Time reduction} =
\frac{T_c - T_r}{T_c} \times 100\%
\]

Speedup:

\[
\text{Speedup} = \frac{T_c}{T_r}
\]

Illustrative example: cold start 8.4 seconds, restore 1.2 seconds:

\[
\text{Time reduction} = \frac{8.4 - 1.2}{8.4} \times 100\%
= 85.7\%
\]

\[
\text{Speedup} = \frac{8.4}{1.2} = 7.0\times
\]

State clearly that both times are measured to the same readiness milestone. If cold start is measured to first response while restore is measured to readiness, the comparison is invalid.

### Throughput regression

With:

- \(Q_b\): baseline throughput.
- \(Q_r\): post-restore throughput.

Throughput change:

\[
\text{Throughput change} =
\frac{Q_r - Q_b}{Q_b} \times 100\%
\]

A negative value indicates throughput degradation. Use the same request mix, concurrency, and duration.

### Illustrative result table example

<text color="secondary" size="sm">Simulated data to illustrate reporting format, not actual measured results.</text>

| Metric | Cold start | CRaC restore |
|---|---:|---:|
| Process-to-ready median | 8,400 ms | 1,200 ms |
| Process-to-ready p95 | 9,100 ms | 1,450 ms |
| First request p95 | 145 ms | 160 ms |
| Steady-state throughput | 4,800 req/s | 4,760 req/s |
| Steady-state latency p95 | 42 ms | 43 ms |
| Error rate | 0.02% | 0.03% |
| RSS after warm-up | 620 MiB | 650 MiB |
| Checkpoint duration | — | 780 ms |
| Checkpoint image | — | 185 MiB |

In the example, restore-to-ready is significantly faster. However, first request p95 increases slightly and post-warm-up RSS is higher; throughput/steady-state latency are nearly equivalent. A real report must determine whether these differences fall within acceptable limits.

### Charts to include

Depending on the goal, present:

- Bar chart of cold-start-to-ready and restore-to-ready by median/p95.
- Line chart of latency over time to show first-request spikes and warm-up.
- Throughput by concurrency.
- RSS/heap/CPU by phase.
- Checkpoint image size and transfer duration.
- Restore success rate across runs.

Do not just show charts. Clearly state units, number of runs, request count, workload, versions, and environment directly beneath each chart.

## 10. Define acceptance criteria

Acceptance criteria must be written before viewing the final results. If thresholds are only set after seeing the numbers, teams can easily adjust criteria unconsciously to justify the results.

Divide conditions into four gates:

1. **Functional correctness:** the application and business logic work properly after restore.
2. **Performance:** startup/restore meets targets and steady-state does not degrade beyond allowed limits.
3. **Reliability/operability:** repeatable restore, dependency recovery, scaling, and observability work.
4. **Security/compatibility:** images and secrets are protected; the environment is within the support matrix.

### Example acceptance criteria

The thresholds below are only examples to illustrate how to write them. The project team must replace them with the application's SLOs, actual load, and resource budget.

| Item | Example criterion | Type |
|---|---|---|
| Restore-to-ready | p95 ≤ 2 seconds within the same host profile | Performance gate |
| Startup improvement | Median restore-to-ready reduced by at least 60% vs. cold start | Performance gate |
| First request | p95 ≤ 200 ms and no spike exceeding SLO threshold | Performance gate |
| Throughput | No more than 5% decrease vs. baseline | Performance gate |
| Steady-state latency | p95 increases by no more than 5% | Performance gate |
| Error rate | Does not exceed SLO; no new business errors | Reliability gate |
| Checkpoint success | 20/20 successes in the selected test matrix | Reliability gate |
| Restore success | 20/20 successes in the supported environment | Reliability gate |
| Functional validation | All smoke tests and data-integrity tests pass | Hard gate |
| Dependency recovery | Do not open readiness before required dependencies are ready | Hard gate |
| Multi-instance behavior | No duplicate leader/policy-violating side effects | Hard gate |
| Resource budget | RSS, CPU, and image size within defined budget | Resource gate |
| Security | Artifact access, encryption, and secret handling meet policy | Hard gate |
| Compatibility | JDK/CRIU/kernel/architecture within support matrix | Hard gate |

### Hard gate and soft target

**Hard gate** is a condition that must never be violated, such as data correctness, no duplicate payments, no two leaders for the same role, no secret exposure, and no opening readiness when required dependencies are not ready.

**Soft target** is a performance goal that can be traded off within an approved range, such as image size, startup improvement percentage, or RSS increase. If a soft target is not met, document the trade-off and the accountable approver.

Never allow a very fast startup result to compensate for functional bugs or data safety violations.

### Set thresholds based on SLO

If the application has latency or availability SLOs, acceptance criteria must align with that budget. For example:

- If an instance must serve traffic within 5 seconds, restore-to-ready p95 needs to be below this threshold with headroom for orchestration.
- If an API has a 100 ms p95 latency budget, a 500 ms first-request spike may need to be addressed with warm-up or readiness gating.
- If a pod has a 1 GiB memory limit, checkpoint restore must not create a peak RSS exceeding the limit or cause OOM.

Do not set thresholds based solely on a nice-looking number. Account for deployment overhead, image transfer, readiness probe interval, retries, network, and dependency startup.

## 11. Fillable report template

Each report should have enough information for someone else to repeat the benchmark without having to ask about configuration.

### Test run information

| Field | Value |
|---|---|
| Report ID | [fill in] |
| Measurement date/time | [UTC and timezone] |
| Operator | [fill in] |
| Application build | [version + SHA-256] |
| Framework/version | [fill in] |
| JDK vendor/version/build | [fill in] |
| CRIU version | [fill in] |
| Kernel/OS | [fill in] |
| Container runtime/orchestrator | [fill in] |
| CPU architecture and host class | [fill in] |
| CPU/memory limits | [fill in] |
| Dependency profile | [test double or real service] |
| JVM flags | [fill in] |
| Checkpoint ID | [fill in] |
| Workload profile | [request mix, concurrency, duration] |
| Measurement tool and version | [fill in] |

### Key results

| Metric | Baseline | CRaC | Threshold | Result |
|---|---:|---:|---:|---|
| Cold/restore to ready median | [ ] | [ ] | [ ] | [PASS/FAIL] |
| Cold/restore to ready p95 | [ ] | [ ] | [ ] | [PASS/FAIL] |
| First request p95 | [ ] | [ ] | [ ] | [PASS/FAIL] |
| Throughput | [ ] | [ ] | [ ] | [PASS/FAIL] |
| Steady-state latency p95 | [ ] | [ ] | [ ] | [PASS/FAIL] |
| Error rate | [ ] | [ ] | [ ] | [PASS/FAIL] |
| RSS peak | [ ] | [ ] | [ ] | [PASS/FAIL] |
| Checkpoint duration | N/A | [ ] | [ ] | [PASS/FAIL] |
| Image size | N/A | [ ] | [ ] | [PASS/FAIL] |
| Restore success rate | N/A | [ ] | [ ] | [PASS/FAIL] |

### Result summary

Write concisely:

- Restore-to-ready median/p95 and improvement vs. baseline.
- First request latency and warm-up duration.
- Throughput, p95/p99 latency, and error rate.
- CPU, RSS, image size, checkpoint duration, and transfer cost.
- Number of runs, success/failure counts, and variance.
- Failed scenarios and confirmed root causes.

### Analysis and decision

| Question | Record |
|---|---|
| Was the primary performance goal met? | [evidence] |
| Is there any steady-state regression? | [evidence] |
| Are there any functional or data integrity errors? | [evidence] |
| Is multi-instance restore safe? | [evidence] |
| Do dependencies recover in the right order? | [evidence] |
| Is the resource budget met? | [evidence] |
| Are there any open compatibility or security risks? | [evidence] |
| Decision | [ACCEPT / ACCEPT WITH CONDITIONS / REJECT] |
| Remaining conditions and owner | [fill in] |

Attach raw output, redacted logs, workload config, checkpoint manifest, checksums, and measurement scripts. Do not attach checkpoint images or secrets to a general report.

## 12. Complete report example with illustrative data

This section shows how to turn numbers into conclusions. All numbers below are simulated.

### Context

A Java catalog application serves HTTP GET and CPU endpoints. The same build and JDK are run in a container with 2 vCPUs and a 1 GiB memory limit. Dependencies are simulated using a stable test service. The baseline is cold start; the CRaC image is created after the application context and sample cache have warmed up. Each scenario runs 10 independent times; the steady-state workload runs for 10 minutes with 50 concurrent clients.

### Illustrative results

| Metric | Baseline cold start | CRaC restore | Example threshold |
|---|---:|---:|---:|
| To-ready median | 8.4 s | 1.2 s | Restore p95 ≤ 2.0 s |
| To-ready p95 | 9.1 s | 1.45 s | ≤ 2.0 s |
| First request p95 | 145 ms | 160 ms | ≤ 200 ms |
| Throughput | 4,800 req/s | 4,760 req/s | Regression ≤ 5% |
| Steady p95 | 42 ms | 43 ms | Regression ≤ 5% |
| Error rate | 0.02% | 0.03% | Per SLO |
| RSS peak | 620 MiB | 650 MiB | ≤ 800 MiB |
| Checkpoint duration | — | 0.78 s | ≤ 1.5 s |
| Image size | — | 185 MiB | ≤ 250 MiB |
| Restore success | — | 10/10 | 10/10 |

From the two to-ready medians:

- Speedup = 8.4 / 1.2 = 7.0x.
- Time reduction = 85.7%.
- Throughput change = (4,760 − 4,800) / 4,800 = −0.83%.
- Steady p95 change = (43 − 42) / 42 = +2.38%.

According to the example thresholds, restore-to-ready p95, first request p95, throughput, steady p95, RSS, checkpoint duration, image size, and restore success all pass. Error rate needs to be checked against the defined SLO; you cannot conclude from the numbers alone without knowing the error budget.

### Illustrative conclusion

In this test configuration, CRaC reduces median time-to-ready by approximately 85.7% compared to cold start and achieves restore p95 under 2 seconds. Throughput and steady-state p95 change by less than 5%, while RSS peak and image size are within the assumed budget. The results support continuing CRaC trials for this workload.

The deployment decision still requires results from real dependencies, restore on target nodes, multiple concurrent instances, credential rotation, failover, and data testing. A simulated dataset is not sufficient for production approval.

## 13. Factors that skew benchmarks

| Bias | Impact | How to control |
|---|---|---|
| Different JDK builds | Startup and CRaC implementation differ | Fix vendor/version/build |
| Different JVM flags | Heap, GC, JIT, and container behavior differ | Save all flags |
| Unwarmed baseline, warmed image | Benefits may be misattributed to restore | Document checkpoint state and also compare against a warm baseline if needed |
| Different dependencies | Measures network/database instead of CRaC | Fix dependency profile |
| Host under background load | Startup and latency fluctuate | Isolate or record background load |
| Saturated load generator | Throughput is limited by client | Monitor generator CPU/network |
| Single run only | Does not reflect variance | Repeat multiple times and report distribution |
| Reporting average only | Hides tail latency | Report p50/p95/p99 |
| Not separating first request | Lazy initialization is hidden | Measure first request separately |
| Overly lightweight readiness probe | Reports ready before dependencies | Readiness reflects actual serving conditions |
| Measuring restore command instead of end-to-end deployment | Skips image download/extraction | Report both restore engine time and total deployment time |
| Warm filesystem cache on later runs | Restore may be faster due to OS cache | Interleave order and record cache state |
| Changing concurrency between runs | Throughput/latency cannot be compared | Fix workload |
| Different log verbosity | CPU/I/O and timing differ | Fix logging level |
| Restoring multiple instances but measuring only one | Ignores contention | Test concurrent restore and rollout |

### Warm-up and JIT

A checkpoint can retain loaded class state, caches, and part of runtime/JIT state depending on the JDK and how the image is created. Therefore, you must describe how long after startup the checkpoint was created, with how many requests, and which paths were intentionally warmed up.

Do not create a checkpoint after a very heavy workload and compare it with a cold start baseline without reporting that condition. An additional comparison could be:

- Cold start without warm-up.
- Cold start with equivalent warm-up before measuring steady state.
- CRaC restore from an image created after the same warm-up policy.

These three execution paths help separate startup benefits, retained initialized-state benefits, and steady-state performance.

## 14. Evaluate overall cost, not just restore time

CRaC can make restore faster, but requires creating, storing, distributing, and managing checkpoint images. Evaluate the overall cost across a deployment lifecycle:

~~~text
Build application
    -> Start JVM and warm up
    -> Create checkpoint
    -> Package and store image
    -> Transfer image to target
    -> Verify and prepare image
    -> Restore JVM
    -> Reconnect dependencies
    -> Open readiness
~~~

If a new image must be created on every deployment, checkpoint creation cost belongs to the deployment pipeline. If an image is reused across many instances, this cost can be amortized, but storage/transfer and restore concurrency increase.

### Cost calculations

**Total time to bring an instance into service:**

\[
T_{\text{total}} =
T_{\text{provision}} +
T_{\text{image transfer}} +
T_{\text{prepare}} +
T_{\text{restore}} +
T_{\text{dependency recovery}}
\]

**Storage to retain:**

\[
S_{\text{total}} =
S_{\text{image}} \times N_{\text{versions}} \times N_{\text{copies}}
\]

This is a simple estimation model; storage deduplication, compression, replication, and retention can change the result.

**Number of concurrently restored instances:**

Do not measure only a single restore. When multiple instances read the same image simultaneously, storage and network can become bottlenecks. Record artifact read throughput, p95 restore time, peak CPU, and readiness time for the entire group.

### Benefit comparison by scenario

| Scenario | Economic/technical question |
|---|---|
| Frequent scale-out | Does restore time saved outweigh image creation/storage/transfer costs? |
| Infrequent deployments | Is the operational cost of checkpoints worth it compared to cold start? |
| Many replicas | Can the artifact store and nodes handle restore bursts? |
| Large images | Do transfer and storage erase startup benefits? |
| Workloads with slow dependencies | Does restore reduce dependency recovery time, or only JVM startup? |
| Nodes with different kernel/architecture | Are they within the supported compatibility matrix? |

## 15. Acceptance criteria by deployment stage

It is not necessary to enable CRaC for all traffic immediately after a successful benchmark. You can use stages:

### Lab stage

- Verify basic checkpoint/restore.
- Measure cold start and restore-to-ready.
- Check functionality and first request.
- Document JDK/CRIU/kernel compatibility.

### Staging stage

- Run a near-production workload.
- Restore on target node and container profiles.
- Verify real dependencies, secret rotation, and consumer rejoin.
- Test restoring multiple instances simultaneously.
- Confirm rollback to cold start when the image is unusable.

### Canary stage

- Apply only to a small percentage of instances.
- Monitor startup p95, error rate, CPU/RSS, consumer lag, and readiness.
- Compare against cold-start replicas during the same time window.
- Have rollout stop conditions if a hard gate is violated.

### Production stage

- Expand only after canary passes over a sufficiently long observation window.
- Maintain cold-start fallback.
- Manage image versions and retention.
- Monitor drift in JDK, kernel, CRIU, dependencies, and container policy.
- Re-run benchmarks when impactful components change.

### Rollout stop rules

For example, stop the rollout if:

- Restore success rate falls below threshold.
- Data corruption or duplicate side effects occur.
- Multiple leaders exist for the same role.
- Readiness opens before dependencies are ready.
- Error rate or p99 latency exceeds SLO.
- Peak RSS causes OOM or prolonged CPU throttling.
- Artifact checksum/signature verification fails.

Hard gates should be automated whenever possible. Do not wait for an end-of-day report if metrics already show data safety or correctness failures.

## 16. Pre-sign-off checklist

### Benchmark design

- [ ] Measurement goals and scope are clearly written.
- [ ] Cold start and CRaC restore use the same artifact and equivalent configuration.
- [ ] Definitions of process start, readiness, and first response are consistent.
- [ ] Workload, request mix, concurrency, and duration are fixed.
- [ ] Dependency profile and warm-up policy are documented.
- [ ] Sufficient independent runs and raw results exist.

### Data collection

- [ ] Median and p95 exist for startup/restore-to-ready.
- [ ] First-request latency and steady-state percentiles exist.
- [ ] Throughput and error rate exist.
- [ ] CPU, RSS/heap/native memory, and peak usage exist.
- [ ] Checkpoint duration and image size exist.
- [ ] Transfer/prepare duration exists if part of the deployment path.
- [ ] Restore success rate and functional test results exist.

### Criteria and decision

- [ ] Acceptance criteria were defined before viewing results.
- [ ] Hard gates and soft targets are distinguished.
- [ ] Thresholds are based on SLOs and resource budgets.
- [ ] Results are calculated from raw samples, not just averages.
- [ ] Regressions and trade-offs are clearly documented.
- [ ] Unrun or unsupported scenarios are clearly stated.
- [ ] ACCEPT/CONDITIONAL/REJECT decision has an owner and conditions.

### Reproducibility and security

- [ ] JDK, CRIU, kernel, OS, architecture, and container runtime are recorded.
- [ ] Scripts, commands, configs, and tool versions are saved.
- [ ] Logs have had secrets redacted.
- [ ] Checkpoint images are not publicly attached.
- [ ] Manifest/checksums and artifact references are recorded.
- [ ] Cold-start fallback and rollback plan exist.

A CRaC performance report is valuable when measurements are reproducible, milestones are defined consistently, and acceptance criteria are set in advance. Measure startup, restore, first request, steady state, and artifact cost separately; verify functionality and behavior when restoring multiple instances; then compare against SLOs and resource budgets. Approve deployment only when time benefits come with correctness, reliability, operability, and security.
