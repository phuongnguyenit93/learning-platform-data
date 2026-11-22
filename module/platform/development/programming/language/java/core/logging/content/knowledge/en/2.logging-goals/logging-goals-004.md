# Operational Measurement with Logging in Java

## 1. What Do Logs Help Measure in Operations?

When an application runs in production, the questions are not just “what error occurred?” but also: how many requests arrive in a given period, how many fail, how long users have to wait, whether background jobs are running slowly or being processed repeatedly, and whether the situation is improving or degrading? **Operational measurement with logging** means writing structured events consistently enough that you can count, group, compute rates, and trace back from an anomaly to a specific execution.

For example, a standalone `Payment completed` line mainly tells you that a transaction finished. If every execution logs a `payment.completed` event with `status`, `duration_ms`, `payment_method`, and `trace_id`, you can calculate transactions per minute, error rate by payment method, latency distribution, and find the execution path of a failing transaction.

Three types of signals commonly work together:

- **Log:** a record of an individual event with context; well suited for root-cause analysis and inspecting specific cases.
- **Metric:** a value aggregated over time, such as requests per second, error rate, or CPU usage; well suited for dashboards and alerting.
- **Trace:** the sequence of steps for a single request across multiple components; well suited for pinpointing slow or failing stages.

Logs can serve as a **source for generating metrics**, but they do not replace all direct measurements. CPU, memory usage, queue depth, and waiting thread counts usually require dedicated metrics or runtime observability tools.

## 2. Turning Operational Questions into Measurements

A common set of information for HTTP applications consists of the following four signals:

| Signal | Question | How to calculate from request-completion events |
| --- | --- | --- |
| Traffic | How many requests is the system receiving? | `request_count / window_seconds`, in requests per second (RPS). |
| Errors | How many executions failed? | `error_count / total_count × 100%`; requires defining what counts as an error. |
| Latency | How long does a request take? | Distribution of `duration_ms`; track p50, p95, p99, and trends. |
| Saturation | Are resources nearing overload? | Combine queue-wait and task-rejection logs with CPU, heap, thread pool, and queue depth metrics. |

Key concepts to distinguish:

- **Count:** the number of events within a time window. Counting `request.completed` tells you how many executions finished; this does not necessarily equal the number of requests *received* if some requests are still hanging or a process terminates abruptly.
- **Rate:** count divided by window length. `300 requests / 60 seconds = 5 RPS`. When comparing a 1-minute window and a 1-hour window, pay attention to how traffic spikes are smoothed out.
- **Error rate:** the ratio of errors under a consistent definition. For HTTP, 5xx responses can be treated as server-side errors; 4xx responses are usually client-side rejections, though some products treat certain 4xx codes as business failures. Reports must clearly state the numerator and denominator.
- **Latency percentile:** p95 is approximately the duration below or equal to which 95% of observations fall. p95/p99 reveal slow tails that an average can hide. Avoid averaging per-host percentiles and treating the result as a system-wide percentile.
- **Success rate / SLI:** the proportion of requests meeting a defined service criterion; an **SLO** is the target for that indicator, for example “99.9% of valid requests succeed over 30 days”. Logs must include sufficient data and classification rules to compute SLIs consistently.

For background jobs, adjust the measurement target accordingly: `job.started`, `job.completed`, `job.failed`, execution duration, queue wait time, and retry count. Distinguish an **attempt** from a **logical job** so you do not accidentally count a job retried three times as three separate jobs.

## 3. Designing a Countable and Correlatable Event

An event should have a stable name, clearly typed fields, and fixed units. Example of a completed request:

```text
ts=2026-01-01T00:00:02Z event=request.completed service=checkout
environment=prod route=/orders/{id} method=GET status=503
duration_ms=85 trace_id=tr-83 request_id=req-204
error_code=UPSTREAM_UNAVAILABLE
```

Each field serves a distinct role:

| Field | Purpose |
| --- | --- |
| `ts` | Event timestamp in UTC/ISO 8601, used for window filtering. |
| `event` | Stable action name to select the right record type, e.g., `request.completed`. |
| `service`, `environment`, `version` | Distinguish the service, environment, and release version. |
| `route`, `method` | Group by normalized route and HTTP method; use `/orders/{id}` instead of raw IDs. |
| `status`, `outcome`, `error_code` | Classify outcomes and aggregate errors; error codes should be stable. |
| `duration_ms` | Processing duration in milliseconds, stored as a number to compute distributions. |
| `trace_id`, `request_id` | Correlate logs from a single execution for detailed investigation. |

A single line containing multiple fields is only a display example; in real log collection systems, **structured JSON** or a format parsed reliably by your collector is much easier to query than arbitrary concatenated strings. Use consistent field names, pick a single unit (`duration_ms` or `duration_ns`), keep numbers as numeric types, and use an explicit value when an optional field is absent.

**Choose the right time to log:** for HTTP, typically emit *one completion event per request* at the layer wrapping the request (filter/interceptor), once both the status and duration are known. For exceptions, still ensure the final outcome is logged in a `finally` block or appropriate completion hook, while avoiding logging the same event multiple times across layers. Do not rely on `request.started` logs to infer how many requests have completed.

**Measure duration properly:** use a monotonic elapsed-time clock such as `System.nanoTime()` and convert to milliseconds; use `Instant.now()` for recording the UTC timestamp, and do not subtract two wall-clock timestamps to measure latency because the system clock can be adjusted. Separate queue wait time and execution time when those are two distinct metrics you need to analyze.

**Security and cost:** do not log passwords, tokens, payment details, payloads containing personal data, or sensitive query strings. Limit unnecessary data; `trace_id` is valuable for search, but do not turn millions of unique IDs into metric labels. Group by normalized `route`, `status`, `service`, or `error_code` with a bounded set of values.

## 4. Java 17 Example: Operational Events and Aggregation

The following example uses `java.util.logging` built into the JDK. The data and timestamps are **fixed so that running the program produces repeatable results**; in a real application, these values come from the request handler and elapsed-time measurement. The example both emits logs for each request and computes aggregated results from the same event set; in production operations, a log collector or query engine typically performs the aggregation from ingested logs.

Save the file `OperationLogDemo.java`:

```java
import java.time.Instant;
import java.util.List;
import java.util.Locale;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public class OperationLogDemo {
    record Request(String traceId, int status, long durationMs) {}

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.operations");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        StreamHandler output = new StreamHandler(System.out, new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + " "
                        + record.getMessage() + System.lineSeparator();
            }
        });
        output.setLevel(Level.INFO);
        logger.addHandler(output);

        List<Request> events = List.of(
                new Request("t1", 200, 12),
                new Request("t2", 200, 20),
                new Request("t3", 503, 85),
                new Request("t4", 404, 16),
                new Request("t5", 200, 34)
        );

        Instant windowStart = Instant.parse("2026-01-01T00:00:00Z");

        for (int i = 0; i < events.size(); i++) {
            Request event = events.get(i);
            String message = String.format(Locale.ROOT,
                    "ts=%s event=request.completed service=checkout"
                            + " route=/checkout status=%d duration_ms=%d trace_id=%s",
                    windowStart.plusSeconds(i),
                    event.status(), event.durationMs(), event.traceId());

            logger.log(event.status() >= 500 ? Level.WARNING : Level.INFO,
                    message);
        }
        output.flush();

        long serverErrors = events.stream()
                .filter(event -> event.status() >= 500).count();
        long[] sorted = events.stream()
                .mapToLong(Request::durationMs).sorted().toArray();

        // Example using the nearest-rank rule on a small dataset.
        int p50Index = (int) Math.ceil(sorted.length * 0.50) - 1;
        int p95Index = (int) Math.ceil(sorted.length * 0.95) - 1;

        System.out.printf(Locale.ROOT,
                "window_s=10 requests=%d rps=%.2f errors_5xx=%d"
                        + " error_5xx_pct=%.1f%% p50_ms=%d p95_ms=%d%n",
                events.size(),
                events.size() / 10.0,
                serverErrors,
                serverErrors * 100.0 / events.size(),
                sorted[p50Index],
                sorted[p95Index]);

        logger.removeHandler(output);
        output.close();
    }
}
```

Run with JDK 17 or later:

```bash
javac OperationLogDemo.java
java OperationLogDemo
```

Expected output (each event is displayed on a single line):

```text
INFO ts=2026-01-01T00:00:00Z event=request.completed service=checkout route=/checkout status=200 duration_ms=12 trace_id=t1
INFO ts=2026-01-01T00:00:01Z event=request.completed service=checkout route=/checkout status=200 duration_ms=20 trace_id=t2
WARNING ts=2026-01-01T00:00:02Z event=request.completed service=checkout route=/checkout status=503 duration_ms=85 trace_id=t3
INFO ts=2026-01-01T00:00:03Z event=request.completed service=checkout route=/checkout status=404 duration_ms=16 trace_id=t4
INFO ts=2026-01-01T00:00:04Z event=request.completed service=checkout route=/checkout status=200 duration_ms=34 trace_id=t5
window_s=10 requests=5 rps=0.50 errors_5xx=1 error_5xx_pct=20.0 p50_ms=20 p95_ms=85
```

Explanation:

1. The window is **defined** as 10 seconds; 5 requests yield `5 / 10 = 0.50 RPS`. The timestamps of the 5 events only span from second 0 to second 4, so you must not take the difference between the first and last timestamp as the denominator and conclude 1.25 RPS.
2. There is one 503 response out of 5 total responses, so the **5xx rate is 20%**. The 404 response is kept in the denominator but not counted as a 5xx error; this rule must be agreed upon with the product team.
3. The sorted durations are `[12, 16, 20, 34, 85]` ms. Using the *nearest-rank* rule, p50 = 20 ms and p95 = 85 ms. With only 5 samples, p95 essentially reflects the maximum value; more samples and an appropriate window are needed before drawing trend conclusions.
4. `trace_id=t3` lets you open the 503 record and trace related events; this ID field itself is not an appropriate dimension for plotting aggregated charts.

`StreamHandler` in the example is configured solely to produce deterministic output and does not represent a production log format. Real projects may use SLF4J with Logback/Log4j2 or another logging framework; the principles around events and measurement are library-independent.

## 5. Turning Logs into Dashboards and Alerts

Typical pipeline:

```text
Request / job
    -> emit structured event
    -> collect, ship, and store logs
    -> parse event + data fields
    -> filter by service, environment, time window
    -> count / rate / error rate / percentile
    -> dashboard + alerts + links to original trace/logs
```

Example operational question: “In the last 5 minutes, has the 5xx rate of `checkout` increased?”. To answer it, select only `event=request.completed` with `service=checkout` and `environment=prod`, take a consistent 5-minute window, count all completed requests as the denominator, count `status >= 500` as the numerator, and compare against the previous period or alert threshold. If it increased, break down further by `route`, `version`, or `error_code`; use `trace_id` to drill down from the chart to individual cases.

Points to specify before putting metrics on a dashboard:

- **Window and time:** clearly state 1 minute / 5 minutes / 30 days, the display time zone, and which timestamp is used (event occurrence time vs. collector ingestion time). Late-arriving events can alter numbers in past windows.
- **Denominator:** all requests, valid requests, completed requests, or unique business requests? Never change this silently when comparing charts.
- **Grouping:** normalize routes; separate `prod` and `staging` environments; avoid mixing background jobs with HTTP traffic or mistakenly counting retries as successful transactions.
- **Percentages and percentiles:** compute only when sample counts are sufficient; document the percentile calculation method. After grouping, aggregate from raw data or an appropriate histogram structure rather than averaging p95 values.
- **Alerting:** typically combines a severity threshold and a sustained duration. For example, “5xx exceeds 2% for 5 minutes with at least 100 requests” reduces false positives when sample counts are low; this is a design example, not a universal threshold for every service.
- **Traceability:** dashboards should link to logs or traces containing `request_id`/`trace_id`, status, error code, and the latest deployment version so on-call engineers can take action.

When logs are sampled, dropped due to backpressure or process crashes, duplicated during retries, or only enabled at `WARN` level, counts derived from logs **no longer reliably represent total traffic**. Metrics used for critical SLA/SLO alerting usually require direct metric instrumentation or an event pipeline with controlled completeness and deduplication. Detailed logs remain invaluable for explaining *why* a metric changed.

## 6. Common Mistakes

1. **Logging only free-text messages:** `"slow!"` or `"something failed"` lacks units, route, and outcome codes, making aggregation difficult. Use stable event names and fields.
2. **Counting error logs as request error rate:** a single request might emit 5 stack traces or none at all; you need a consistent completion event with an accurate denominator.
3. **Using system timestamps to measure duration:** wall clocks can jump; use `System.nanoTime()` for elapsed time and `Instant.now()` for point-in-time timestamps.
4. **Lumping 4xx and 5xx together without definition:** this confuses server incidents with invalid client requests; report them separately or document the success/failure policy.
5. **Grouping by raw IDs or URLs:** creating a new label per request causes metric series cardinality to explode; use normalized routes for aggregation and keep IDs for looking up specific logs.
6. **Relying blindly on incomplete logs:** logs can be sampled, lost, duplicated, or delayed; cross-check against directly collected metrics when measuring reliability targets.
7. **Tracking only averages:** a normal average can still hide many very slow requests; use percentiles alongside sample counts and break down by route.
8. **Logging everything at INFO level:** increases storage costs and risks exposing sensitive data. Select valuable business/operational events, appropriate log levels, and proper retention and masking policies.

## 7. Self-Check Exercise

A service has 200 `request.completed` events in 60 seconds, including 8 5xx responses and 12 4xx responses. Calculate the RPS, the 5xx rate, and determine whether 4xx responses should be treated as server errors.

**Answer:** RPS = `200 / 60 ≈ 3.33`; 5xx rate = `8 / 200 × 100% = 4%`. Under the policy “server error = 5xx”, the 12 4xx responses are not included in the 5xx numerator, though they can still be analyzed separately if they impact user experience. To conclude whether an operational target was violated, you also need the SLI/SLO definitions, data quality checks, and the observation window.

**Check your understanding:** Can you identify which event is being counted, the denominator of each rate, the unit of duration, why `System.nanoTime()` is used, how to trace from a dashboard spike back to a `trace_id`, and at least two situations where metrics derived from logs become inaccurate?