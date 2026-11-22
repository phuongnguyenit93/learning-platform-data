# Distinguishing Logs and Metrics in Java

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain what events a **log** records, and what quantitative characteristics of a system a **metric** describes.
- Choose the right type of data when you need to investigate a specific error, track trends, measure performance, or set up alerts.
- Recognize common metric types: counter, gauge, histogram, and summary.
- Know how to combine logs and metrics without increasing storage costs, exposing sensitive data, or creating too many metric labels.
- Observe the difference through a standalone Java 17 program.

## 2. What Is a Log? What Is a Metric?

A **log** is a record of a *specific event* that occurred in the application. It typically includes a timestamp, severity level, source, message, and context to answer the question: **“What happened, where, and why?”**

Illustrative log example:

~~~text
2026-11-09T10:00:12Z ERROR checkout requestId=req-42 orderId=ORD-7 Payment timeout after 3000 ms
~~~

From this log, an operator can look up a request, see that the checkout operation timed out, and continue tracing the exception or related events. Logs are useful because they preserve **details of each individual occurrence**, but a single log line does not tell you whether the system is failing system-wide or if it is just an isolated case.

A **metric** is a measurement represented by a **numeric value**, associated with a timestamp, and optionally accompanied by classification labels (*labels/tags*) to form a time series of numbers. Metrics answer the question: **“How many, how fast or slow, how is it changing, and is it exceeding a threshold?”**

Example metric following Prometheus naming conventions (hypothetical values):

~~~text
http_requests_total{service="checkout",status="500"} 42
http_requests_in_flight{service="checkout"} 3
~~~

The first line represents the cumulative count of requests with status code 500 for a group of labels; the second line is the number of requests currently being processed at the time of sampling. Neither value **contains a requestId, stack trace, or the cause of each individual error**.

The key point: **logs store the context of individual events; metrics store measurements that can be aggregated and compared over time**. The two complement each other and do not completely replace one another.

## 3. Comparison Table: Logs vs. Metrics

| Criterion | Log | Metric |
| --- | --- | --- |
| Unit of information | A single event/record, usually with a message | A numeric observation or a time series of numeric values |
| Primary question | “What happened to this request?” | “How many failed requests occurred in the last 5 minutes?” |
| Typical contents | Timestamp, level, message, logger, correlation ID, exception/stack trace | Measurement name, value, timestamp, unit, labels/tags |
| Level of detail | Can drill down to specific operations and root causes | Represents aggregates, rates, states, or distributions |
| Searchability | Search by string/field, filter events | Query numeric data by time range and labels |
| Dashboards, alerting | Can be built from log searches/counts, depending on the collection system | Well-suited for plotting trends and setting threshold rules |
| Storage size | Depends on event volume, message size, and stack traces | Depends on the number of time series (label combinations), scrape/collection frequency, and retention |
| Sensitive data | High risk if logging request bodies, tokens, or personal information | Risk if sensitive information is placed in label names or values |
| Common Java tools | java.util.logging (JUL), SLF4J with Logback/Log4j 2 | Micrometer, OpenTelemetry Metrics; collection systems such as Prometheus |
| Limitation when used alone | Hard to see the big picture if only reading line by line | Hard to determine the specific cause from a single number alone |

You should not assume that logs are always plain text or that metrics are always pre-aggregated data. A **structured log** can contain numeric fields, logs can be counted into *log-based metrics*, and a counter metric can be updated every time an event occurs. The important difference lies in the **data model and intended use**.

## 4. Metric Types to Recognize

### 4.1. Counter — Cumulative Count

A counter typically increases when an event occurs, such as the number of HTTP requests processed, errors, or retries. A counter does not decrease on its own during the lifetime of the same process/measurement series; **when the process restarts, the value may reset to 0**, so rate-querying systems must handle resets.

Example:

~~~text
10:00  requests_total = 120
10:01  requests_total = 180
~~~

Over 60 seconds, assuming no reset and complete measurement data, the number of requests increased by 60, which corresponds to an average of **1 request/second**. A cumulative counter is not the throughput at a point in time; throughput must be calculated from **the rate of increase over a time interval**.

### 4.2. Gauge — A Value That Can Go Up or Down

A gauge describes a state measured at the time of sampling: the number of open connections, tasks currently being processed, queue depth, or amount of memory currently in use.

~~~text
active_connections = 12
queue_depth = 4
~~~

A gauge can increase, decrease, or stay the same. Do not use a counter for values that need to decrease when resources are released.

### 4.3. Histogram — Distribution of Observations

A histogram typically categorizes observations such as response times into **buckets**, while also tracking the total count and total sum of values (depending on the specific metric system). Using this distribution, you can estimate **p95/p99 latency** and detect slow requests that an average value would hide.

For example, suppose there are 100 requests: 95 requests take 20 ms, while 5 requests take 2000 ms. Looking only at the average may not adequately reveal how slow the tail group is. A histogram with well-chosen buckets lets you ask: “What percentage of requests completed under 500 ms?”

**Units matter:** many libraries measure duration in **seconds**, even though an application might display it in **milliseconds**. Naming, configuration, and queries must use consistent units.

### 4.4. Summary — Statistical Summary of Observations

Some systems provide a summary to track count, sum, and sometimes compute quantiles directly at the recording site. Merging precomputed quantiles from multiple instances usually **does not produce a valid system-wide quantile**; a histogram is better suited when you need to aggregate distributions across multiple instances and compute quantiles at query time. Not every metric library provides the same set of metric types or the same export rules.

## 5. When to Use Logs vs. Metrics

| Need | Preferred Choice | Reason |
| --- | --- | --- |
| See why a specific request failed | **Log** with request ID and exception | Need the message, stack trace, and context |
| Know if the error rate increased in the last 5 minutes | **Metric**: errors / total requests | Need statistics over a time window |
| Alert when p95 latency exceeds a threshold | **Metric** of type histogram | Need the processing time distribution |
| Investigate a rare error encountered by a single user | **Log** with correlation ID, with sensitive data redacted | Need to trace the sequence of events |
| Know how many requests are currently running | **Metric** of type gauge | Instantaneous state that can increase or decrease |
| Know who changed access permissions | Appropriate **audit log** | Need an auditable event history; retention and integrity requirements may be higher than application logs |
| Find which service is slowing down a request in a distributed system | **Tracing**, combined with metrics and logs | Traces/spans describe the path; metrics show trends, and logs provide error details |

Example during a checkout incident:

1. **Metrics** show that the failed request rate jumped from 1% to 8% over 10 minutes and p95 latency spiked. This is the “something is wrong” signal that prompts an investigation.
2. Operators filter the **logs** of the checkout service during that time window, looking up `requestId` and exceptions to see how the failures actually happened.
3. If the call spans multiple services, the **trace ID** links the request across spans; logs sharing the same ID clarify the error details in each service.
4. After deploying a fix, continue watching **metrics** to verify that error rate and latency return to expected levels, while checking logs to confirm that the specific error does not recur.

You cannot infer a root cause such as “the database ran out of connections” **solely** from a metric showing an increased error count. You need evidence from logs, traces, system state, or other observability sources.

## 6. Java 17+ Example: Recording Logs and Metrics Differently for the Same Operation

The following example uses **java.util.logging** built into the JDK to log an error event, while using **LongAdder** to count requests, count errors, and sum durations. This is a learning model to make the difference easy to see, **not a standard metric-publishing system**: in a real application, instrument with Micrometer or OpenTelemetry Metrics and let a monitoring system collect the data.

Create the file **LogMetricDemo.java**:

~~~java
import java.util.Locale;
import java.util.concurrent.atomic.LongAdder;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public class LogMetricDemo {
    private static final Logger LOG =
            Logger.getLogger(LogMetricDemo.class.getName());

    private static final LongAdder REQUESTS = new LongAdder();
    private static final LongAdder ERRORS = new LongAdder();
    private static final LongAdder DURATION_MS_SUM = new LongAdder();

    private static void recordRequest(
            String requestId, int durationMs, boolean success) {
        // Three numeric measurements are updated for each request.
        REQUESTS.increment();
        DURATION_MS_SUM.add(durationMs);

        if (!success) {
            ERRORS.increment();

            // Log with the context of the exact request that encountered the issue.
            LOG.warning("requestId=" + requestId
                    + " outcome=error durationMs=" + durationMs);
        }
    }

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        Handler output = new StreamHandler(System.out, new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + " | "
                        + formatMessage(record) + System.lineSeparator();
            }
        });
        output.setLevel(Level.INFO);
        LOG.addHandler(output);

        // Mocked and fixed data for deterministic output.
        recordRequest("req-101", 12, true);
        recordRequest("req-102", 18, false);
        recordRequest("req-103", 30, true);

        // StreamHandler is buffered: flush before printing the summary.
        output.flush();

        long requests = REQUESTS.sum();
        long errors = ERRORS.sum();
        long durationSum = DURATION_MS_SUM.sum();

        System.out.println("requests_total " + requests);
        System.out.println("request_errors_total " + errors);
        System.out.println("request_duration_ms_sum " + durationSum);
        System.out.printf(Locale.ROOT,
                "request_duration_ms_avg %.1f%n",
                (double) durationSum / requests);
    }
}
~~~

Compile and run with JDK 17+ in a UTF-8–capable terminal:

~~~bash
javac -encoding UTF-8 LogMetricDemo.java
java LogMetricDemo
~~~

**Exact stdout** of the program in a normal run:

~~~text
WARNING | requestId=req-102 outcome=error durationMs=18
requests_total 3
request_errors_total 1
request_duration_ms_sum 60
request_duration_ms_avg 20.0
~~~

Line-by-line analysis:

- The **WARNING** line is a **log**: it tells you *which request* failed and provides a specific message. With a real exception, you can use **LOG.log(Level.SEVERE, "Failed to process request " + requestId, exception)** to capture the stack trace instead of logging only the message.
- **requests_total = 3** and **request_errors_total = 1** are **illustrative counters** for total requests and total errors; they do not carry `requestId`.
- **request_duration_ms_sum = 60** divided by 3 gives an average of **20.0 ms**. Having only sum and count **cannot determine p95**; measuring p95 requires collecting a distribution (such as a histogram).
- **LongAdder** is suitable when multiple threads update a counter; however, **sum() is not an atomic snapshot of all concurrent updates**. In this sequential example, the results are deterministic.
- **StreamHandler** is configured explicitly to write to stdout and print only the level and message. Real-world logging should include a timestamp, service name, logger, and correlation ID; default handlers or different configurations may produce different output.
- The lines ending in **_total** above are simply **summary values printed to the console for learning**. They do not automatically become Prometheus-scraped metrics, do not expose an HTTP endpoint, and do not have a time-series storage backend.

In a real system, a metrics library handles registering measurements, exporting data, managing labels, and interacting with the backend. Application code should only update meaningful measurements rather than building a custom metrics infrastructure just to count requests.

## 7. How Can Logs and Metrics Work Together?

Suppose an API has the path **/orders/{id}**. A sensible strategy is:

**Metric** (labels with a bounded set of values):

~~~text
http_requests_total{route="/orders/{id}",method="GET",status="500"} 17
~~~

**Log** for the individual error event:

~~~text
ERROR service=order-api requestId=req-781 route=/orders/{id} orderId=ORD-781 cause="database timeout"
~~~

The metric tells you which route is seeing an increase in 500 responses; the log helps you find each corresponding request and its cause. **Do not attach requestId or orderId as metric labels**: nearly every request would create a distinct label combination, causing the number of time series to explode (*high cardinality*), increasing memory usage and collection cost.

Use labels such as **service**, **method**, **status**, and **route template** (for example `/orders/{id}`), keeping the number of distinct values under control. Individual IDs, full exception messages, and stack traces belong in log or trace context when legitimately needed.

In systems that support it, an **exemplar/trace ID** can help jump from a metric data point to a related trace. This links observability sources without turning unique IDs into labels on every time series.

## 8. Understanding Timing and Cost Aspects

**Logs** typically carry per-event timestamps; emitting, buffering, shipping, and indexing can cause records to appear with a delay in search tools. Do not assume that the order of lines collected from multiple threads or multiple instances reflects absolute execution order.

**Metrics** are typically scraped or received periodically by a backend. A data point may reflect the measurement timestamp, a cumulative value, or an aggregated result over an interval; do not infer that a single sample point represents a single request. Resolution, ingestion latency, and query time ranges all affect the result.

Regarding cost:

- Logging too verbosely at INFO for every minor step can generate huge data volumes, especially inside loops or high-traffic APIs; choose appropriate levels, retention, and sampling.
- Although metrics are compact for tracking trends, they can become very expensive when label combinations grow unchecked. Each unique set of label values typically creates a separate time series.
- A system can also **derive metrics from logs** by counting or summing fields. This is useful when suitable logs already exist, but you must consider ingestion cost, latency, and accuracy; do not assume it is equivalent to directly instrumented metrics.
- Manage retention periods, access controls, and data deletion as required. **Do not log passwords, tokens, API keys, or sensitive request payloads**; likewise, do not use personal information as metric labels.

## 9. Common Misconceptions

| Misconception | Correct Understanding |
| --- | --- |
| “Having INFO logs means we already have metrics” | Logs describe events; metrics require numeric measurements and a collection/querying pipeline |
| “A counter currently at 300 means 300 requests/second” | A counter is cumulative; you must measure its increase over time to compute a rate |
| “Total duration / request count is p95” | That is the **average (mean)**, not a percentile; p95 requires a distribution of observations |
| “The more labels a metric has, the more detailed and better it is” | Labels with nearly unique values cause high cardinality |
| “Add requestId to every metric for easier debugging” | Keep IDs in logs/traces; use bounded categorical labels for metrics |
| “Seeing the error rate rise tells you which code bug happened” | Metrics detect changes; you need logs/traces and related evidence to identify the root cause |
| “Reading log lines one by one is enough to measure overall system health” | You need metrics to monitor overviews, rates, distributions, and threshold-based alerts |
| “Metrics always increase and never reset” | Counters can reset on restart; gauges can go up or down |
| “If you write a log, it is guaranteed to be saved” | Buffers, transport errors, receiver limits, or retention policies can cause logs to be lost |

## 10. Self-Check Questions

**Question 1.** You want to know what percentage of HTTP requests returned 5xx in the last 5 minutes. What should you choose?

**Answer:** A metric — count 5xx requests and total requests over the same time window, then compute the ratio; the result is only meaningful when request definitions and labels are consistent.

**Question 2.** An individual request throws a `NumberFormatException`; you need to inspect the input parameter and the failure location. What should you choose?

**Answer:** A log with sufficient context, a request ID, and the throwable/stack trace. Mask or omit sensitive input values.

**Question 3.** You want to see under how many milliseconds 95% of requests respond. What should you choose?

**Answer:** A distribution-based metric, typically a histogram with appropriate buckets/resolution. A total counter or an average calculation is not enough to determine p95.

**Question 4.** Two requests both return status 500. Should you put both `requestId` values into the labels of `http_requests_total`?

**Answer:** No. Labels should keep the number of combinations bounded; request IDs belong in logs or traces.

**Question 5.** The system triggers an alert for a rising error rate, but you do not know why. What is the next step?

**Answer:** Narrow down the service, route, and time window using metrics; query error logs for the same time window and correlate request/trace IDs to find evidence of the root cause.

**Key Takeaway:** **Logs answer “what happened to a specific event?”, while metrics answer “how is the system performing at scale and over time?”.** Use metrics to detect and quantify, logs to investigate details, and combine them with tracing when requests span multiple components.
