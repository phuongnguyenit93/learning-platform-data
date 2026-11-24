# Distinguishing Observability, Monitoring, and Troubleshooting

A Spring Boot application is still running, `/actuator/health` returns `UP`, yet users wait a long time to complete checkout. In that situation, you need to answer three different groups of questions: is the service meeting expectations; is there enough data to understand what is happening; and what evidence explains the delay?

This lesson helps you distinguish **observability**, **monitoring**, and **troubleshooting (diagnosis)**, and place Spring Boot Actuator in its proper role. Follow this order: understand the three concepts → recognize the signals → walk through a scenario → practice reading signals.

## 1. Three Concepts Looking at the Same System

### 1.1. Observability: What Can Be Understood from External Outputs?

Observability is the ability to infer a system’s internal state and behavior from the data it emits. Its practical value lies in being able to ask new questions when problems arise, including questions not already built into a dashboard.

For example: “Why are only checkout requests through partner A on the new version slow, while partner B remains normal?” To answer that, the data must carry enough context to distinguish operation, version, partner, and request path. This concept is explained in the [OpenTelemetry Observability primer](https://opentelemetry.io/docs/concepts/observability-primer/).

Observability is a **capability of the system together with how its data is used**. Installing a library or collecting large volumes of data does not by itself prove that capability. If related events cannot be linked or the error window cannot be queried, operators still struggle to answer questions.

### 1.2. Monitoring: Tracking a Service Against Goals and Rules

Monitoring is the activity of collecting, tracking, and evaluating data to know how a system is operating. Dashboards, periodic checks, and alerts are common implementations.

An illustrative rule: “Alert when the failed checkout request rate exceeds 2% over 5 minutes, with at least 100 requests.” This is an illustrative rule; real thresholds depend on service objectives and traffic.

Monitoring can use metrics, logs, traces, or external probes. It also supports trend analysis and planning, not only alerting. [Google SRE describes monitoring](https://sre.google/sre-book/monitoring-distributed-systems/) as collecting, processing, aggregating, and displaying data, while distinguishing user-facing symptoms from internal causes.

### 1.3. Troubleshooting: Explaining Problems with Hypotheses and Evidence

Troubleshooting (diagnosis) is the process of identifying a problem, narrowing scope, forming hypotheses, and testing them to reach a grounded explanation. This process can begin from an automated alert, a user report, or an anomaly observed during load testing.

For example: “Is waiting to acquire a database connection making checkout slow?” You must seek data that confirms or refutes that hypothesis. Two charts rising at the same time are not enough to conclude causality.

Diagnosis is an **activity of reasoning and investigation**. Good data makes it more effective, but tools do not guarantee the right conclusion on their own. The hypothesis-and-verification approach is presented in [Google SRE — Effective Troubleshooting](https://sre.google/sre-book/effective-troubleshooting/).

### 1.4. Comparison Table

| Perspective | Observability | Monitoring | Troubleshooting |
| --- | --- | --- | --- |
| Nature | Capability to understand a system via data | Activity of tracking and evaluating operations | Process of investigating and explaining problems |
| Typical question | Can we trace what happened and in what context? | What is abnormal compared to our targets? | Which hypothesis is supported by evidence? |
| Example in this lesson | Correlating version, partner, and request path | Detecting an error rate exceeding a threshold | Verifying that waiting for connections causes slowness |
| Useful outcome | Richly contextualized, queryable data | Trends, status, alerts | Scope of impact, explanation, action, and re-verification |

The three concepts complement one another. A system may alert well yet lack data for investigation. Conversely, data may be plentiful while timely detection rules are missing. Diagnosis still requires a person or analytical mechanism using the data methodically.

## 2. Which Data Helps Answer Which Question?

Operational data is often referred to collectively as **telemetry**. In this lesson, we focus on metrics, logs, and traces.

### 2.1. Metrics: Seeing Scale and Trends

**Metrics** represent quantities such as request counts, processing duration, or memory usage. They must be read together with units, time intervals, and classification dimensions.

Illustrative questions:

- How many checkout requests arrive per second?
- What is the failure rate over the last 5 minutes?
- How did p95 latency per operation change after deployment?

p95 is the 95th percentile of the latency distribution: roughly 95% of observations fall at or below that value, depending on the estimation method. It is not the mean. Sample size and time window are needed to interpret it. Read more at [OpenTelemetry — Metrics](https://opentelemetry.io/docs/concepts/signals/metrics/).

**Sample calculation created for this lesson:** in a window with 200 eligible requests, 10 failed:

```text
Failure rate = 10 / 200 × 100% = 5%
```

This number describes the defined set of requests. It does not yet tell you which requests failed, what the cause was, or whether all users were affected equally.

### 2.2. Logs: Seeing a Specific Event

**Logs** record events with timestamps and context. Structured log records allow searching by field rather than relying entirely on plain-text matching.

The following record is **hypothetical data** with application-chosen field names:

```json
{
  "timestamp": "2026-01-10T09:02:15Z",
  "level": "WARN",
  "service": "checkout",
  "version": "v2",
  "event": "payment_timeout",
  "provider": "A",
  "traceId": "0123456789abcdef0123456789abcdef",
  "spanId": "0123456789abcdef",
  "timeoutMs": 2000
}
```

It tells you the application recorded a timeout event with partner A in that context. It does not prove partner A’s server failed: time may have been spent in several places along the path.

Logs can be correlated with traces via identifiers. However, not every log record carries request context; collection and correlation must be configured. See [OpenTelemetry — Logs](https://opentelemetry.io/docs/concepts/signals/logs/).

### 2.3. Traces: Seeing the Path of a Request

A **distributed trace** describes the path of a request across instrumented operations. Each **span** represents a unit of work with timing and relationships to other spans.

For example, you might follow a checkout request through cart validation and then the partner call. You need to read both nested and parallel relationships; do not arbitrarily add every span duration to infer total time. See [OpenTelemetry — Traces](https://opentelemetry.io/docs/concepts/signals/traces/).

If a step is not instrumented, the trace may not show detail for that step. Seeing a long client call only identifies an area for further investigation; to know what happened inside the target system, you need corresponding evidence on that side.

### 2.4. Combining Signals by Question

| Question in the checkout scenario | Suitable starting signal | Needed to go deeper |
| --- | --- | --- |
| How many requests are slow? | Metrics by operation and time window | Distribution, traffic volume, version |
| What happened to a single request? | Contextualized logs | Trace ID, processing step details |
| Which step took the time? | Stored trace for the request | Details of the suspected step |
| Where are JVM threads waiting? | Thread state dump | Multiple timestamps and load context |
| Did the fix improve the service? | Before-and-after indicator comparison | Comparable traffic and conditions |

A per-request unique identifier is very useful when searching logs or traces, but is usually unsuitable as a metric tag because it has too many distinct values. In Spring Boot’s Observation model, low-cardinality attributes go into metrics and traces, while high-cardinality attributes go only into traces. See [Spring Boot 3.3 — Observability](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html).

Beyond queryability, consider whether data is retained long enough and remains complete. Sampling mechanisms may keep only a subset of traces. Thus, not finding a trace for a request does not mean the request never occurred. See [OpenTelemetry — Sampling](https://opentelemetry.io/docs/concepts/sampling/).

## 3. Where Does Actuator Stand?

In Spring Boot, Actuator provides management access points and supports data collection integrations. For metrics, Spring Boot integrates Micrometer; external systems handle scraping, storage, and querying per the chosen configuration. See [Spring Boot 3.3 — Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).

One way to visualize the data flow:

```text
Running Spring Boot application
  ├─ Status and Actuator access points
  ├─ Metrics via Micrometer
  ├─ Application logs
  └─ Traces when corresponding integration is configured
                ↓
       Collection / data export
                ↓
       Storage and querying
                ↓
       Monitoring / investigation
```

Branches may travel through different collection pipelines. For example, logs can be collected from process output, while metrics are scraped periodically by a monitoring system.

### 3.1. Role of Selected Access Points

| Default access point | Main value |
| --- | --- |
| `/actuator/health` | Read health status from configured health indicators |
| `/actuator/metrics` | Discover and inspect metrics registered in the application |
| `/actuator/prometheus` | Provide metrics formatted for Prometheus scraping; requires the matching registry library |
| `/actuator/threaddump` | Capture thread states to assist investigation |
| `/actuator/loggers` | Read and change logging level configuration |

In Spring Boot 3.3, only `health` is exposed over HTTP by default. Whether an endpoint exists, is enabled, is exposed, and is permitted to be accessed must each be verified separately. See [Spring Boot 3.3 — Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html). Path and port also depend on application configuration, as described in [Monitoring and Management over HTTP](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html).

### 3.2. Reading the Limits of Each Tool Properly

**Health returns `UP`:** this result reflects the configured health checks at the moment of the check. It does not directly measure whether users complete checkout accurately, quickly, or slowly. In the opening example, a simple connectivity check can succeed while a business query remains slow. You can inspect the response structure in [Health REST API 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/health.html).

**Metrics contain data:** you can inspect what the application has registered and current values. The `metrics` API is meant for inspecting meters, not designed as an operational monitoring datastore. Retaining history and long-term querying require a suitable external system. See [Actuator Metrics REST API 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/metrics.html).

**Having Actuator:** does not mean every request has exported and stored traces. You must configure a tracer, export pipeline, and receiving backend. Spring Boot provides Micrometer Tracing integration for this purpose. See [Spring Boot 3.3 — Tracing](https://docs.spring.io/spring-boot/3.3/reference/actuator/tracing.html).

Thus, Actuator helps produce and expose evidence on the application side. Assessing service health and finding root causes still depend on collected data, correlation, and the investigation process.

## 4. Walking Through a Complete Scenario

**All service names, timestamps, figures, and evidence in this section are hypothetical to teach reasoning.**

### 4.1. Detection Step: Recognizing User Impact

The `checkout` service just deployed version `v2`. The operations team sees data for the same 5-minute window:

| Hypothetical observation | Before deployment | After deployment |
| --- | --- | --- |
| Eligible requests | 200 | 200 |
| Failed requests | 0 | 10 |
| Failure rate | 0% | 5% |
| p95 latency | 300 ms | 2,000 ms |
| Health of running instances | `UP` | `UP` |

The error-rate rule stated in section 1 triggers on the post-deployment data. This is an example of **monitoring detecting a symptom**.

You must not conclude that `v2` is the root cause merely because two events happened close together. External systems, traffic load, and other concurrent changes must be examined.

### 4.2. Querying Step: Using Observability to Slice Groups

Assuming the data includes `version`, `provider`, and operation name, we slice the 200 post-deployment requests:

| Hypothetical group | Total requests | Failures | Failure rate |
| --- | --- | --- | --- |
| `v2`, partner A | 50 | 10 | 20% |
| `v2`, partner B | 150 | 0 | 0% |

The new breakdown narrows the impact to the group using A. That is the value of **observability**: not only seeing an aggregate figure, but being able to ask follow-up questions using existing context.

If the data only said “system-wide 5% errors”, the operations team could not deduce this breakdown. An unanswerable question is a signal to improve instrumentation for next time.

### 4.3. Diagnosis Step: Avoiding Jumping from Symptom to Cause

The investigation team proposes three hypotheses:

| Hypothesis | Evidence to look for |
| --- | --- |
| Partner A is processing slowly | Client-side timing and partner’s corresponding data |
| Application is waiting to acquire an HTTP connection to A | Connection wait time, active/waiting connection counts, and thread states |
| Internal stage before calling A is slow | Stage durations or additional measurements in that stage |

Suppose a retained trace shows time concentrated in the call to A. Logs record `payment_timeout`. Those two facts do not distinguish “A is slow” from “the application is waiting on resources before sending”.

Continuing the investigation, the team finds **additional hypothetical evidence**:

1. Client-specific measurements show most time is spent waiting to acquire a connection.
2. Active connections hit the pool limit while many requests queue up.
3. `v2` configuration lowered the connection limit dedicated to A.
4. In a controlled test holding load comparable, restoring the old configuration reduces wait time.

At this point, the connection-limit hypothesis is much better supported. Conclusions must state the scope of evidence and remaining unknowns; do not turn one test into an absolute claim for every situation.

### 4.4. Remediation and Re-Verification Step

A mitigation action could be rolling back to the previously stable configuration following the team’s deployment procedure. Afterward, verify:

- Do success rate and latency for partner A’s group return to expected levels?
- Are there new errors or side effects on partner B’s group?
- Are traffic conditions comparable enough for a fair comparison?
- What alerts or signals should be added for earlier detection and investigation?

**Mitigating impact** and **confirming root cause** are two separate outcomes that must be recorded clearly. Restarting to temporarily stabilize a system can be useful, yet that outcome alone does not explain why the problem occurred.

## 5. Hands-On: Reading Actuator on an Existing Application

This section uses an existing Spring Boot 3.3 web application with `spring-boot-starter-actuator`, running on a study machine with a suitable JDK. No extra business API is needed to learn the three concepts.

### 5.1. Prepare the Test Scope

Assume the application runs at `localhost:8080`, uses the default management path, and you have permission to read the endpoints. If Spring Security is used, follow the application’s authentication mechanism.

In configuration dedicated to a study machine, you can expose the two needed endpoints:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,metrics"
```

This configuration is for observation and does not bypass the security layer. When merging into existing config, maintain one valid `management` tree rather than creating duplicate keys. In shared or public environments, restrict authorized callers; do not expose every endpoint just for an exercise.

### 5.2. Ask Questions Before Running Commands

The commands below use PowerShell with `curl.exe`; in other environments use the corresponding `curl` program.

Read health status:

```powershell
curl.exe -i "http://localhost:8080/actuator/health"
```

**Question answered:** what health status does the application report at the moment of the call? Record the actual HTTP status code and body. Do not assume the result is always `UP`, nor treat a single successful call as proof that all business operations work correctly.

Discover metric names:

```powershell
curl.exe -i "http://localhost:8080/actuator/metrics"
```

Then read only a name that actually appears in the list. For example, if `jvm.memory.used` is present:

```powershell
curl.exe -i "http://localhost:8080/actuator/metrics/jvm.memory.used"
```

**Question answered:** what values and classification dimensions does that metric currently have? Read `measurements`, `availableTags`, and the unit if provided. Memory values change with the process; the lesson does not prescribe a fixed JSON output.

If `http.server.requests` is already in the list, you can inspect it:

```powershell
curl.exe -i "http://localhost:8080/actuator/metrics/http.server.requests"
```

Spring Boot uses this name by default for Spring MVC/WebFlux server request metrics, though it can be customized. Metrics also depend on operations that have occurred. Do not conclude a business API has no traffic solely from not seeing the name in a single read. Refer to [Spring Boot 3.3 — HTTP server metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.supported.spring-mvc).

### 5.3. From a Single Read to Monitoring and Diagnosis

Calling `health` once is a point-in-time check. Long-term tracking requires collecting over time and defining evaluation criteria. Investigating a slow request requires data from that specific time and context.

Try keeping a small observation log:

| Field to record | Question |
| --- | --- |
| Timestamp and time zone | What time does this read correspond to? |
| Version and specific running instance | Which process does the data belong to? |
| Metric name, unit, and filters | Are we comparing the exact same quantity? |
| Operations performed | What could cause the value to change? |
| Conclusion and limits | What does this observation prove, and what does it not prove? |

Do not extrapolate an exact service-wide p95 from a few manual calls. This exercise helps recognize signals; evaluating latency distributions requires an appropriate sample set and aggregation method.

If you encounter access errors, record data-retrieval issues separately: `401/403` typically points to checking authentication/authorization; `404` points to checking path, exposure config, or whether the endpoint or metric exists. These are investigation leads, not a strict mapping for every system with proxies and custom security rules.

## 6. Misconceptions That Easily Cause Wrong Conclusions

### “Having a CPU chart means full observability”

A CPU chart answers one class of questions. In the checkout scenario, normal CPU can coincide with long wait times. Start from the question to answer and check whether corresponding data exists.

### “No ERROR logs means no incident”

An application can compute wrong business results or become too slow without throwing exceptions. Check the user journey and expected outcomes instead of only counting log levels.

### “An alert already pinpoints the root cause”

An alert usually only confirms its condition was met. “High error rate” is a symptom. Even an alert saying “active connections hit limit” still requires finding why resources are held so long or why the limit is unsuitable.

### “Raising log levels will always fix missing data”

Increasing log verbosity can add context for future occurrences, but cannot recover data that was never saved. Weigh volume, sensitive information, and operational impact; collect only what the investigation question needs.

### “No alerts means the system is healthy”

Rules might not cover the right behavior, data might not be collected, or the alerting pipeline might be broken. Distinguish “no problem detected” from “measured and verified that service requirements are met”.

### “A successful rollback proves the entire root cause”

It is useful evidence of a related change. To explain the mechanism, identify the specific change and check other factors that changed at the same time.

## 7. Self-Check with Scenarios

### Scenario A

Every minute, a system checks checkout completion using a synthetic transaction and alerts on consecutive failures.

**Answer:** this is monitoring from an external perspective. The result helps detect a failing user journey; knowing where the failure lies requires additional diagnostic data.

### Scenario B

The operations team can pick a slow request, link logs with its trace, and identify the version and processing step involved.

**Answer:** this scenario demonstrates useful observability capability. When the team uses that data to test hypotheses, they are performing troubleshooting.

### Scenario C

Health reports `UP`, no alerts fire, yet user reports show checkout totals are calculated incorrectly.

**Answer:** the service cannot be considered healthy based on `health` alone. Scope the incorrect behavior, gather evidence from affected transactions, and add appropriate business-outcome checks.

### Applied Exercise

For an existing operation in your application:

1. Write one sentence describing the outcome users expect.
2. Choose one observable signal to detect when that outcome is not met.
3. State one investigative question that signal cannot answer by itself.
4. Specify what additional data is needed and how to correlate it to the exact operation.
5. Write one hypothesis, one verification check, and one result that could refute that hypothesis.

You understand the three concepts accurately when you can explain separately: **what is being monitored, what more can be learned from the data, and what must be verified to conclude**.
