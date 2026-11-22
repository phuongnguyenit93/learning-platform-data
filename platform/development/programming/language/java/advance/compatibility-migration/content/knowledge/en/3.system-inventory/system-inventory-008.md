# Recording Functional, Latency, and Resource Metrics as a Baseline

When surveying a system before upgrading Java or changing library versions, the team needs to know how the application behaves prior to the change. A successful build or normal startup does not provide enough information to evaluate the impact of a migration. You need to record a set of metrics reflecting functional results, processing time, and resource consumption under repeatable conditions.

This initial set of measurements is called a **baseline** (reference point). After migration, the team reruns equivalent scenarios, collects the same types of metrics, and compares them against the baseline. This helps answer concrete questions: does the business logic still produce right results, are requests slower, have CPU or memory increased, can the system sustain the same load, and do new errors appear?

A baseline is not a single number, nor is it a guarantee that the system always works correctly. It is a collection of measurements along with execution conditions, clear enough for others to reproduce and understand the magnitude of observed changes.

## 1. Why Is a Baseline Needed Before Migration?

If you only test the system after upgrading, you may spot an issue without knowing whether it already existed before or newly appeared. For example, an order-processing API has a p95 latency of 900 ms after migration. That number alone does not tell whether the migration slowed the system down or the system already had that latency.

When a baseline under the same scenario exists, the team can compare:

- Are business results the same as before migration?
- Have success rate, error rate, and transaction counts changed?
- Have median response time and slow-request percentiles increased?
- Are CPU, heap, garbage collection, threads, and connection pools consuming more?
- Under the same input load, does the system maintain throughput and stability?
- Do new phenomena appear such as timeouts, growing queues, memory leaks, or failures occurring only after extended runs?

A baseline is especially useful when upgrading the JDK, Spring Boot, frameworks, database drivers, HTTP clients, ORMs, or libraries affecting runtime behavior. A change may not fail compilation yet still alter performance, configuration defaults, or request handling.

Record measurements before making changes and retain information on source code version, configuration, data, infrastructure, and load generation. Without those details, post-migration comparisons easily become skewed.

## 2. Three Categories of Metrics to Record

A useful baseline should combine three main metric categories. Each category answers a different question.

| Category | Question | Example metrics |
|---|---|---|
| Functional | Does the system produce correct results and complete business processing? | Successful transactions, business error rate, correct record count, invariant check results |
| Latency and throughput | How fast does the system respond and how much work does it process? | p50, p90, p95, p99 latency, throughput, error rate, queue time |
| Resource utilization | How many resources does the system require to process the same workload? | CPU, heap, allocation, GC pause, threads, connections, network, and disk I/O |

Do not pick just one metric to represent an entire category. For example, lower CPU is not necessarily good if throughput also dropped sharply. Unchanged average latency is not necessarily good if p99 spiked and a subset of users must wait longer. Higher successful request counts do not prove business correctness either if the system creates duplicate transactions or writes wrong data.

Define a small yet representative set of metrics for critical flows, then add deeper metrics when investigating.

## 3. Recording Functional Metrics

Functional metrics describe what work the system performed and whether the outcomes are right. This is the most important layer, because good performance means nothing if the application returns wrong results.

### 3.1. Choosing Representative Business Flows

Start with the main flows the application must preserve after migration. For a sales system, flows may include:

- User login and authentication.
- Searching or viewing product details.
- Creating an order.
- Calculating prices, discounts, and taxes.
- Sending payment requests.
- Recording order status.
- Publishing and receiving events across services.
- Querying history or reports.

For each flow, describe inputs, preconditions, actions, expected outcomes, and side effects. Do not merely record “API returns HTTP 200”, because a protocol-successful response can still carry wrong data or skip a business step.

### 3.2. Defining Correct Outcomes

A scenario needs explicit success criteria. For example:

| Flow | Measurable success condition |
|---|---|
| Create order | Exactly one order exists with the expected ID and total amount |
| Payment | Transaction status matches the result from the payment provider |
| Update inventory | Inventory quantity changes exactly once per business rules |
| Query | Record set, committed order, and field contents are accurate |
| Publish event | Event has valid schema and consumers process it the designed number of times per semantics |

Criteria should check both returned data and persisted state. If an operation can be retried, define how to verify idempotency to detect duplicate transactions. If a flow is asynchronous, define wait time and the final state that must be reached.

### 3.3. Functional Metrics to Collect

- Number of submitted operations and number completed.
- Counts of successes, failures, business-rule rejections, and timeouts.
- Success rate out of total valid operations.
- Counts of created, updated, or deleted records.
- Counts of duplicate, missing, wrong-status, or invariant-violating transactions.
- Counts of messages published, consumed, retried, or sent to dead-letter queues.
- Counts of validation errors and external dependency errors.
- Data reconciliation results across inputs, responses, and database.

Distinguish expected business errors from technical errors. For instance, a payment request rejected due to insufficient balance can be a valid business outcome; a connection error to the payment provider is a technical error. Merging both into one overall error rate makes comparison conclusions inaccurate.

### 3.4. Example of Functional Counters

Suppose an order-creation scenario has 10,000 valid requests. After running, the team checks:

| Outcome | Count |
|---|---:|
| Requests sent | 10,000 |
| Orders created accurately | 9,980 |
| Expected business errors | 10 |
| Technical errors | 8 |
| Duplicate or corrupted orders | 2 |

Do not lump everything together as “9,990 error-free requests”. Two corrupted orders are still a serious functional bug even if the endpoint returned successful responses. Store counts per outcome category and use independent queries or reconciliation to verify final data.

## 4. Recording Latency and Throughput

Latency is the time required to complete an operation according to defined start and end points. Throughput is the amount of work the system processes per unit of time. These two metrics must be read together.

### 4.1. Defining Measurement Points

For APIs, end-to-end latency is typically measured from when the client begins sending a request until the client receives the complete response. This is the experience observed by callers.

In a multi-tier system, time can additionally be measured at each segment:

~~~text
Client sends request
       |
       v
Gateway / Load balancer
       |
       v
HTTP server and filter
       |
       v
Business service
       |
       +----> Database
       |
       +----> Remote service
       |
       v
Serialize response
       |
       v
Client receives response
~~~

Segment measurements help find root causes, yet must not be arbitrarily summed if they overlap or execute in parallel. Clearly document which timer measures the full request and which timer measures only an internal operation.

For background jobs, distinguish message processing time from time spent waiting in the queue. For batch jobs, record both batch completion time and average or percentile processing time per item.

### 4.2. Do Not Look Only at Average Latency

Latency usually has a skewed distribution: most requests are fast while some are very slow. Therefore, the mean value can hide the experience of the slow-request group.

Commonly used percentiles:

| Metric | Interpretation |
|---|---|
| p50 | 50% of requests complete in less than or equal to this value; close to median |
| p90 | 90% of requests complete in less than or equal to this value |
| p95 | 95% of requests complete in less than or equal to this value |
| p99 | 99% of requests complete in less than or equal to this value |
| max | Slowest request observed during the measurement window; sensitive to outliers and sampling duration |

For example, a p50 of 80 ms while p99 is 1,800 ms indicates most requests respond fast whereas a small group is significantly slow. Reporting only a mean of 140 ms can miss the tail-distribution issue.

Do not record p99 while omitting sample count. A measurement with a few dozen requests does not provide a reliable p99 estimate. Ensure enough requests per scenario and duration for percentiles to be meaningful.

### 4.3. Recording Throughput and Error Rate

Throughput can be expressed as requests/second, transactions/second, messages/second, or items/second depending on work type. Specify units clearly and count only completed work under the chosen definition.

A system can reduce latency by processing fewer requests. Therefore, latency comparisons must be made under the same input load and paired with throughput.

Error rate needs a clear definition, for example:

~~~text
error rate = number of technical-error operations / total number of valid operations
~~~

If the system has expected business errors, track them separately so they do not distort the technical error rate. Timeouts, HTTP 5xx, connection errors, and message processing errors should have appropriate classifications.

### 4.4. Measuring Queue Time and Dependency Time

When requests are slow, the cause may lie in wait time for threads, connections, queues, or external services. Also collect:

- Wait time in executors or message queues.
- Time to acquire a connection from the pool.
- Database query execution time.
- Remote API call duration.
- Number of active in-flight requests and waiting requests.
- Timeouts, retries, and retry counts.

These metrics distinguish slow CPU processing from bottlenecks caused by connection exhaustion or slow dependent services.

## 5. Recording Resource Utilization

Resources indicate how much compute capacity the system needs to process a workload. Record both absolute utilization and utilization relative to completed work.

### 5.1. CPU

Figures to observe:

- Process and container/host CPU utilization.
- User and system CPU if provided by the platform.
- Container CPU throttling when hitting quota limits.
- Allocated cores or CPU quota.
- CPU per request or per successful transaction.

70% CPU utilization on an 8-core machine is not equivalent to 70% on a container capped at 1 core. Therefore, record both allocated CPU capacity and actual limits.

If CPU rises after migration, cross-check against throughput. A 10% CPU increase while throughput grows 30% can be an overall efficiency improvement; a 10% CPU increase with flat throughput warrants investigation.

### 5.2. JVM Memory

Do not record just one total memory number. For Java, distinguish:

- Heap used, committed, and maximum.
- Non-heap memory, including Metaspace and off-heap managed areas.
- Direct buffers and native memory when used.
- Process/container RSS or working set.
- Allocation rate and memory trend over time.

Heap used can temporarily rise before a garbage collection. Therefore, record time series or post-GC marks rather than taking a single point-in-time snapshot. RSS can be higher than heap because of thread stacks, metaspace, code cache, direct buffers, and native allocations.

One low memory reading does not prove the absence of a memory leak. Observe after the workload runs long enough and compare trends over equivalent intervals.

### 5.3. Garbage Collection

Useful GC metrics include:

- GC counts by type.
- Total GC time and pause durations.
- Percentage of JVM time spent in GC.
- Allocation rate.
- Heap occupancy before and after GC.
- Full GC count and causes if any.

GC can directly affect p95/p99 latency. If a migration changes the JDK or object-allocating libraries, allocation rate and GC characteristics can change even when business logic stays unchanged.

Save GC configuration, heap size, and JVM flags alongside the baseline. Do not compare two runs with different heap or collector configurations without noting that as a changed variable.

### 5.4. Threads and Connection Pools

Monitor:

- Live thread count and active thread count.
- Waiting, blocked, or long-stalled thread counts.
- Executor size, queue depth, and rejected tasks.
- Active, idle, and waiting connections in the pool.
- Connection acquisition time and pool exhaustion count.
- Socket, file descriptor, or handle counts if exposed by the OS.

Abnormal thread growth can lead to memory pressure or context switching. Connection pool exhaustion can spike latency even when CPU remains low. A continuously growing queue indicates work arrival exceeds processing rate over a period.

### 5.5. Network, Disk, and Dependent Resources

Depending on architecture, also collect:

- Network bytes in/out, connection counts, and connection errors.
- Disk reads/writes, IOPS, and I/O wait time.
- Database query count, query latency, lock wait, and connection utilization.
- Cache hits/misses and evictions.
- Message broker lag, queue depth, and consumer throughput.
- Container CPU/memory limits and container restart counts.

Select metrics tied to the architecture and business flows under survey. You do not need to collect every possible metric if they do not help explain system behavior.

## 6. Locking Down the Workload So Comparisons Are Meaningful

Numbers are only comparable when both runs perform equivalent work. The same application under different loads can show vastly different latency and resource utilization.

Before measuring, describe the workload:

| Component | Information to record |
|---|---|
| Scenario | Endpoint, business flow, or batch under test |
| Data | Dataset size, data distribution, database state |
| Input load | Requests/second or messages published |
| Concurrency | Number of concurrent clients, threads, or requests |
| Flow mix | For example, 60% reads, 30% writes, 10% searches |
| Duration | Warm-up, steady-state measurement window, and total run time |
| Client behavior | Think time, timeouts, retries, and response handling |
| Termination | Stop condition, completed operations, and valid sample count |

Use the same data or a dataset with equivalent properties. If the database in the later run already has warm caches, different row counts, or different indexes, latency can change for reasons outside the migration.

### 6.1. Distinguishing Closed Workloads and Open Workloads

In a closed workload, the number of concurrent clients is kept fixed. When the system responds slowly, the client request-sending rate can also drop. This is useful for observing a fixed group of users yet can mask overload conditions.

In an open workload, the load generator dispatches work at a target rate, relatively independent of response time. This verifies whether the system sustains the arrival rate, yet requires controlling queues and load-generator limits.

Document which model is used. Do not compare results from two different load models and conclude that the migration altered latency.

### 6.2. Warm-Up and Steady State

The JVM has JIT compilation, class loading, caches, and initialization tasks. The first requests can be substantially slower than steady-state execution.

A measurement run typically consists of:

1. Starting the application with the defined configuration.
2. Running warm-up until JIT, caches, and pools reach steady state.
3. Confirming metrics have relatively stabilized.
4. Starting the formal measurement window.
5. Stopping load, waiting for remaining work to finish, and recording results.

Do not mix startup time into normal request-processing latency. If startup time needs evaluation, measure it as a separate scenario using identical startup conditions across both versions.

Warm-up has no fixed duration suited to every application. Choose it based on actual behavior by observing JIT, caches, and metrics. Record the exact duration used so subsequent runs can reproduce it.

## 7. Designing a Repeatable Measurement Run

A good measurement run needs a clear procedure, deterministic input data, and consistent stop conditions.

### Step 1: Select Flows and Goals

Select critical business flows and define measurement goals for each flow. For example: order creation, search, report queries, and background message processing. Set functional criteria alongside performance metrics to observe.

### Step 2: Prepare the Environment

Record JDK, application version, dependencies, JVM flags, OS/container, CPU, memory, database, broker, cache, and network configuration. Ensure no unexpected background tasks disturb the measurement.

### Step 3: Prepare the Data

Create a dataset of the described size and distribution. Document data initialization, schema state, indexes, caches, and reset steps if needed. For write flows, use reconcilable test data and avoid modifying out-of-scope data.

### Step 4: Dry-Run the Scenario

Verify the load generator, endpoints, authentication, timeouts, and result recording. Confirm generated load matches configuration and the load generator does not become a bottleneck.

### Step 5: Warm-Up and Formal Measurement

Run warm-up, then execute the measurement window with the defined workload. Collect functional counters, latency distributions, throughput, errors, and resource metrics on the same timeline.

### Step 6: Repeat

Run multiple independent iterations under equivalent conditions. Record each run's results rather than keeping only the best-looking run. If runs vary widely, find the cause of variance before using them as a baseline.

### Step 7: Reconcile and Store Results

Verify submitted operations, completed operations, output data, errors, and sample counts. Save raw results, dashboards, or reports alongside environment metadata. Record run ID and execution timestamp.

## 8. Tools and Methods for Collecting Metrics in Java Applications

Application-layer metrics can be combined with data from the JVM, operating system, and dependent services. Each source observes a different slice of the system.

### 8.1. Application-Layer Metrics

Spring Boot Actuator paired with Micrometer can export metrics for HTTP requests, JVM, processes, and custom application meters, depending on dependencies and configuration. Functional metrics should be recorded where the application knows the operation truly succeeded.

Illustrative example using Micrometer:

~~~java
@Service
public class OrderService {

    private final Counter completedOrders;
    private final Timer orderProcessingTimer;

    public OrderService(MeterRegistry registry) {
        this.completedOrders = Counter.builder("orders.completed")
                .description("Number of successfully completed orders")
                .register(registry);

        this.orderProcessingTimer = Timer.builder("orders.process")
                .description("Order processing duration")
                .publishPercentileHistogram()
                .register(registry);
    }

    public OrderResult createOrder(CreateOrderCommand command) {
        Timer.Sample sample = Timer.start();

        try {
            OrderResult result = process(command);

            if (result.isSuccessful()) {
                completedOrders.increment();
            }

            return result;
        } finally {
            sample.stop(orderProcessingTimer);
        }
    }

    private OrderResult process(CreateOrderCommand command) {
        // Execute order creation business logic
        return OrderResult.success();
    }
}
~~~

This is an example of where to record counters and timers; data types and success determination must fit the real application. Do not increment the counter as soon as a request arrives if the operation can still fail when writing to the database or calling an external service.

Metric names should be stable, have clear units, and contain no per-user or per-transaction identifying data. Avoid putting order IDs, emails, tokens, or dynamic URL values into labels/tags because doing so creates massive cardinality, increasing monitoring memory and cost.

### 8.2. Prometheus and Dashboards

Prometheus can scrape metric endpoints periodically and store time series. Grafana or an equivalent tool helps display latency, throughput, errors, CPU, memory, and other metrics over the same time window.

When using histograms, configure buckets suited to the latency thresholds being monitored. Percentiles computed from histograms depend in accuracy on bucket layout and query expressions. Do not compare percentiles across two dashboards if calculation methods or bucket configurations differ without noting it.

### 8.3. Java Flight Recorder and JVM Tools

Java Flight Recorder (JFR) helps observe JVM activity such as allocation, GC, threads, lock contention, class loading, and other runtime events.

For example, you can capture a time-bounded recording while running the application:

~~~bash
java -XX:StartFlightRecording=filename=baseline.jfr,duration=2m,settings=profile -jar app.jar
~~~

Or use jcmd to control recordings on a running JVM. JFR is suited for root-cause investigation when aggregate metrics show abnormal CPU, GC, or latency. You do not necessarily need every detailed event enabled for the entire benchmark, because observation itself incurs overhead.

Tools such as jstat, jcmd, and jconsole can help inspect heap, GC, and JVM activity. Record tool versions and collection procedures if results need to be reproduced.

### 8.4. Operating System and Container Metrics

Use OS-appropriate tools to record CPU, memory, disk, network, processes, and container limits. For example, on Linux you can use pidstat, vmstat, iostat, or data from cgroups/container runtime.

Record both allocated resource limits and actual consumption. If a container is limited to 1 CPU and 1 GiB memory, metrics cannot be interpreted as though the application ran on a host with full resources.

### 8.5. Load Generation Tools

You can use k6, Gatling, JMeter, or a tool suited to the system's protocol. The tool must be able to store:

- Scenario and tool version.
- Load rate, concurrency, and run duration.
- Latency distribution, throughput, and errors.
- Input data or data generation method.
- Per-request results or summaries sufficient for reconciliation.

Ensure the load generator machine has sufficient CPU, network, and resources. If the load generator saturates, measured figures will reflect the load generator's limit rather than the application's limit.

## 9. Time Synchronization and Linking Metric Sources

When combining metrics from the application, JVM, database, and load generator, all sources need alignable timestamps. Synchronize system clocks via an appropriate mechanism and record the timezone or timestamp convention.

Each measurement run should have a run ID. Attach the run ID to result filenames, metadata, or test-level tags to locate the matching logs, JFR recordings, dashboard snapshots, and load generator output.

Do not attach a random run ID per request as a metric label if doing so creates high cardinality. Use logs or traces to correlate detailed requests, while keeping aggregate metrics to bounded label values.

A useful timeline might look like:

~~~text
T0        T1             T2                T3
|---------|--------------|-----------------|
Startup   Warm-up        Measurement       Drain / verify
                         |                 |
                         +-- App metrics   |
                         +-- JVM metrics   |
                         +-- OS metrics    |
                         +-- Load results |
                                           +-- Functional reconciliation
~~~

All metric sources must use the same formal measurement window. If CPU is averaged over 10 minutes while latency covers only 2 minutes, placing the two figures side by side can lead to wrong conclusions.

## 10. Saving Metadata So the Baseline Is Reproducible

Numbers without context are hard to use. For each run, store a manifest or report containing:

| Metadata group | Contents |
|---|---|
| Source | Git commit, branch/tag, and working tree status |
| Java | JDK vendor, version, runtime version, and class-file target |
| Build | Gradle/Maven version, build flags, and artifact checksum |
| Dependencies | Framework versions, key libraries, and dependency lock if any |
| JVM | Heap min/max, GC, JVM flags, and relevant system properties |
| Application | Profile, functional config, feature flags, and build version |
| Infrastructure | CPU, memory, OS, container limits, network, and deployment zone |
| Dependent services | Database, schema, broker, cache, and related service versions |
| Dataset | Size, generation method, initial state, and reset method |
| Workload | Scenario, concurrency, arrival rate, mix, and duration |
| Tooling | Load generator, monitoring agent, and tool versions |
| Timing | Start/end timestamps, timezone, and run ID |

Do not store secrets, access tokens, passwords, personal data, or sensitive payloads in manifests. You can record config variable names, configured status, or checksums of secret-redacted configs to detect changes without leaking information.

Abbreviated manifest structure example:

~~~yaml
run:
  id: baseline-java17-order-flow-001
  startedAt: "2026-11-01T09:00:00Z"
  duration: "10m"
source:
  commit: "abc1234"
  artifactSha256: "..."
java:
  vendor: "Example Vendor"
  runtime: "17.x"
  targetRelease: 17
environment:
  cpuLimit: "4 cores"
  memoryLimit: "4 GiB"
  database: "PostgreSQL <version>"
workload:
  scenario: "create-order"
  arrivalRate: "100 requests/second"
  concurrency: 50
  warmup: "5m"
measurement:
  latency: ["p50", "p95", "p99"]
  functional: ["success", "business-error", "technical-error"]
  resources: ["cpu", "heap", "gc", "threads", "connections"]
~~~

Values in the example only illustrate structure. Real manifests must record the exact environment and workload executed, without filling in estimates in place of observed data.

## 11. Comparing Results Before and After Migration

After migration, rerun the same scenario, dataset, load, and measurement method. Build a comparison table by flow or metric group.

For a numeric metric, you can compute absolute difference:

~~~text
absolute change = value_after - value_before
~~~

And percentage change:

~~~text
relative change (%) =
    (value_after - value_before) / value_before * 100
~~~

Interpret the sign according to metric semantics. Increasing latency is usually bad, whereas increasing throughput is usually good. Increasing CPU can be good or bad depending on throughput and resource efficiency goals. When baseline equals 0, do not use the percentage formula above; report absolute difference or an appropriate representation.

Illustrative numerical example:

| Metric | Before migration | After migration | Change |
|---|---:|---:|---:|
| Correct business rate | 100% | 100% | Unchanged |
| Technical error rate | 0.20% | 0.20% | Unchanged |
| Throughput | 500 req/s | 510 req/s | +2.0% |
| p50 latency | 80 ms | 82 ms | +2.5% |
| p95 latency | 240 ms | 270 ms | +12.5% |
| p99 latency | 600 ms | 720 ms | +20.0% |
| Average CPU | 65% | 58% | -7 percentage points |
| Post-GC heap | 900 MiB | 950 MiB | +50 MiB |

This table shows that looking only at throughput or CPU can create a favorable impression while p95 and p99 latencies increased. The team must investigate the cause before concluding the migration meets requirements. Numbers are examples only, not standard thresholds for all applications.

When reporting CPU or percentages, distinguish percentage-point differences from relative percentage changes. Dropping from 65% to 58% is a 7 percentage-point decrease, equivalent to roughly a 10.8% relative reduction from the initial value.

## 12. Assessing Measurement Reliability

A small difference between two runs may come from measurement noise rather than the migration. Common sources of noise include:

- CPU shared with other processes.
- Differences in warm/cold caches.
- Unstabilized JIT compilation or class loading.
- Database checkpoints, vacuuming, backups, or maintenance tasks.
- Network congestion or dependent services under abnormal load.
- Differences in data, request counts, or request distribution.
- Logging, tracing, or profilers enabled in one run yet disabled in another.

Repeat independent measurement runs, inspect distribution across runs, and state variability clearly. Do not cherry-pick only the best run. If runs differ substantially, fix the source of noise or increase run counts before drawing conclusions.

When deeper analysis is needed, use confidence intervals or statistical methods appropriate to the data distribution. For latency, data rarely follows a simple normal distribution; do not mechanically apply mean and standard deviation while ignoring the underlying distribution.

Ensure sample sizes are large enough for the percentiles reported. For example, p99 requires substantially more requests than p50 to have enough tail observations. If samples are too few, explicitly state the limitation rather than presenting p99 as a firm conclusion.

## 13. Common Mistakes When Creating a Baseline

### Measuring Only Once

A single run can be skewed by caches, JIT, or background tasks. Repeat runs and save per-run results.

### Using Only Average Latency

The mean can hide very slow request groups. Track at least p50, p95, and p99 when sample count is sufficient.

### Comparing Different Workloads

Different request counts, concurrency, data, or read/write ratios destroy comparability. Lock down and record the workload.

### Ignoring Business Correctness

Successful responses do not prove final data is right. Check outputs, side effects, and business invariants.

### Recording CPU and Heap at Only One Point in Time

A single snapshot cannot show trends, peaks, GC pauses, or memory leaks. Save time series over the entire measurement window.

### Not Recording Configuration and Infrastructure Limits

The same CPU percentage means different things with different core counts. The same heap used cannot be compared directly when max heap differs.

### Inconsistently Enabling Profilers or Tracing

Observability tools add overhead. Keep configurations equivalent and record which tools were enabled on each run.

### Using Metrics with Uncontrolled Cardinality

Attaching user IDs, order IDs, or dynamic URL values to metric tags can overload monitoring resources and alter the very behavior being measured. Use aggregate metrics with bounded labels; use logs/traces for per-request details.

### Reporting Only Percentage Change

Percentages can mislead when baseline is very small or zero. Always retain raw values, units, absolute deltas, and measurement conditions.

## 14. Defining Acceptance Criteria Before Running Migration

Before comparing, the team should agree on acceptance criteria tailored to product and system requirements. There is no single latency, CPU, or memory threshold that fits all applications.

Example of writing criteria:

| Category | Illustrative criterion |
|---|---|
| Functional | Critical business flows preserve right outcomes; no duplicate transactions or data loss occur |
| Latency | p95 of critical APIs stays within the agreed threshold and does not increase beyond the allowed margin over baseline |
| Throughput | Sustains the target arrival rate without continuous queue growth |
| Errors | No increase in technical error rate or timeouts beyond acceptable limits |
| Resources | CPU, heap, GC pauses, and connection utilization remain within operational bounds |
| Stability | No abnormal upward trends in memory, threads, or queues during extended runs |

If the system already has SLOs or error budgets, use them as a foundation. If not, the team must define thresholds from business requirements, infrastructure capacity, and current baseline. Do not pick thresholds merely because they make migration results look good.

Also distinguish absolute thresholds from relative thresholds. For example, p95 below 300 ms is an absolute threshold; p95 increasing by no more than 10% over baseline is a relative threshold. Both may be needed to keep an already-slow baseline from becoming an acceptable norm.

## 15. Baseline Report Template

A baseline report can be structured as follows:

### Measurement Info

- System name and environment.
- Commit hash, artifact, and Java version.
- Date/time, run ID, and operator.
- Infrastructure, JVM config, and dependent service versions.

### Scenario and Workload

- Business flows tested.
- Dataset and initial data state.
- Load rate, concurrency, and request-type mix.
- Warm-up, measurement duration, and iteration count.

### Functional Results

- Operations sent, succeeded, and failed.
- Breakdown of business errors and technical errors.
- Data reconciliation results.
- Invariants or correctness conditions verified.

### Performance Results

- Throughput and error rate.
- p50, p90, p95, p99 latency.
- Queue time, database latency, and remote call latency if applicable.

### Resource Results

- Process/container CPU and CPU throttling.
- Heap, non-heap, RSS, and allocation rate.
- GC count, pause, and time spent in GC.
- Threads, executor queues, and connection pools.
- Relevant network, disk, and dependent service metrics.

### Conclusions and Limitations

- Key metrics used as the baseline.
- Variation observed across runs.
- Anomalies observed.
- Conditions or limitations that may affect subsequent comparisons.
- Paths to raw data, dashboards, logs, and JFR recordings.

Reports must preserve both raw numbers and interpretation. Do not save only dashboard screenshots, because screenshots usually lack detailed data, queries, and metadata for re-analysis.

## 16. Process for Applying to Java Compatibility Migration

During a migration, a process can be applied around two clear milestones:

**Before migration**

1. Select critical business flows and define correctness criteria.
2. Lock down workload, dataset, and measurement environment.
3. Collect functional counters, latency, throughput, and resource metrics.
4. Repeat measurements, verify stability, and save manifests.
5. Archive artifacts, raw data, and reports as the reference point.

**After migration**

1. Confirm actual Java version, dependencies, JVM flags, and infrastructure.
2. Rerun the exact same dataset, workload, warm-up duration, and measurement window.
3. Collect the same set of metrics using the same definitions.
4. Reconcile functionality and data before interpreting performance.
5. Compare absolute values, percentage changes, percentiles, and variability.
6. Investigate differences exceeding thresholds or showing anomalous signs.
7. Record conclusions alongside test conditions and evidence limitations.

If infrastructure must change at the same time as the JDK or libraries, clearly document the changed variables. When possible, test each change separately or run a test matrix to separate runtime impact from infrastructure impact.

## 17. Principles for Using a Baseline

- **Measure what needs protecting:** Pick metrics tied to business flows and real operational requirements.
- **Keep conditions equivalent:** Workloads, data, runtimes, and infrastructure must be described clearly enough.
- **Measure both outcome and cost:** Functional correctness, latency, throughput, and resource utilization complement each other.
- **Observe distributions:** Use percentiles and sample counts rather than relying solely on averages.
- **Repeat and keep raw data:** Reproducible results are far more valuable than a single number.
- **Interpret in context:** CPU or memory increases/decreases must be placed alongside throughput, latency, and resource limits.
- **Report proportional to evidence:** If only one environment or workload was measured, conclusions must stay scoped to those conditions.

Recording a baseline is the preparatory step for assessing migration impact with data. When the team knows clearly which business operations the system handled accurately, how fast it responded, and how many resources it consumed under a defined workload, post-upgrade results have a concrete basis for comparison. Without a recorded reference point and measurement conditions, remarks like “the application is still fast”, “CPU increased slightly”, or “all features look fine” are hard to verify and too unreliable to make migration decisions.
