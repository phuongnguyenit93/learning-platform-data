# Log Sampling: Controlling Log Volume While Preserving Operational Signals

> **Chapter:** Logging  
> **Lesson:** Log Sampling  
> **Module:** SPRING_BOOT_OBSERVABILITY — Setting up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing. Learn context propagation, tags/cardinality, exporters, sampling, and signal correlation to investigate errors, latency, and application behavior in production environments.

## 1. Why Do You Need Log Sampling?

A Spring Boot application can emit logs for every HTTP request, every dependency call, every retry, and multiple business steps. As traffic grows, log record counts, network transfer volume, and storage costs can climb rapidly. An endpoint handling thousands of requests per second, if emitting multiple `INFO`/`DEBUG` lines per request, can generate massive log volume even with zero errors.

**Log sampling** is the practice of selecting a subset of eligible log records or events to write/export based on an intentional policy. The goal is to reduce log volume and processing costs while retaining the data needed to monitor system health and investigate incidents.

Log sampling should be designed according to log category and purpose:

- Repetitive debug/verbose logs can be sampled more aggressively.
- High-frequency success logs can keep only a fraction or summary.
- Warning logs may need to be retained mostly or fully depending on semantics.
- Error logs must be protected from accidental deletion.
- Security/audit events have dedicated requirements and usually must not be sampled in ways that drop mandatory events.

~~~mermaid
flowchart TD
  A["Application emits log event"] --> B["Classify event"]
  B --> C{"Policy"}
  C -->|"Routine / high volume"| D["Sampling / rate limit"]
  C -->|"Error / security / audit"| E["Protected path"]
  D --> F["Selected log records"]
  D --> G["Dropped / counted records"]
  E --> F
  F --> H["Appender / agent / collector"]
  H --> I["Log backend"]
  G --> J["Drop counters / sampling metrics"]
~~~

**Log sampling does not mean disabling logging for an entire logger.** It is an intentional record-selection policy that can operate in the application, logging backend, agent, or collector.

## 2. Distinguishing Log Sampling, Trace Sampling, and Metrics

The three signals have separate pipelines and semantics. Sampling one signal does not automatically sample the others.

| Mechanism | Target selected | Example |
| --- | --- | --- |
| Log sampling | Log records/events | Keep 1% of success logs for common requests |
| Trace sampling | Traces or spans per sampling decision | Keep 10% of traces at the root sampler |
| Metrics aggregation | Measurements aggregated by meter/labels | Counter increments per request; histogram summarizes distribution |
| Log level filtering | Log events by severity | Do not emit DEBUG in production |
| Rate limiting | Cap events per time window | At most 100 warnings/minute |
| Deduplication | Collapse identical events | One summary warning instead of thousands of duplicate lines |

For example, a request not selected by the trace sampler can still emit application logs if the log pipeline permits it. Conversely, a sampled trace does not guarantee every log record inside that trace is retained.

Do not use sampled log counts to infer total request counts if the policy drops records. Metrics `Counter`/`Timer` are usually the right source for measuring request volume, error rates, and latency.

### 2.1. Log Sampling Does Not Replace Log Levels

Log levels determine the detail/severity emitted by the application. Sampling decides which eligible records are kept or forwarded.

- Reducing production log volume by changing `DEBUG` to `INFO`/`WARN` is a log-level policy.
- Keeping 1 in 100 `INFO` log records of the same kind is a sampling policy.
- Keeping at most 100 warnings per minute is a rate-limiting policy.
- Collapsing 500 identical log records into one summary is deduplication/aggregation.

These techniques can work together, but you must define which policy runs first and which layer drops records.

## 3. Types of Log Sampling

### 3.1. Probabilistic Sampling

Each eligible log event is selected with probability $p$. For instance, $p=0.1$ means expecting to retain roughly 10% of eligible records.

Advantages are simplicity, decentralized execution, and fairly stable volume reduction at scale. Drawbacks are that records belonging to the same request can be kept/dropped independently, and rare critical logs can be dropped accidentally if the policy does not classify them first.

### 3.2. Deterministic Sampling

Selection decisions are computed from a stable key, such as a hash of a correlation key or request group. Records sharing the same key are kept or dropped together.

This helps retain a consistent sequence of logs for a single request/technical session, but care must be taken with sensitive keys or skewed distributions. Never use raw emails, user IDs, or tokens as sampling keys without proper justification and safeguards.

### 3.3. Rate Limiting

A policy caps the maximum number of records over a time interval, such as keeping at most 50 events of the same type per minute. Rate limiting tames bursts yet can drop more records than expected during traffic spikes.

### 3.4. Deduplication or Burst Suppression

When an identical error repeats thousands of times, the system can log one representative record followed by a summary with repeat count, first/last timestamps, and normalized fingerprints.

Deduplication does not mean logging only the first error forever. You need an expiration/window, a count, and a signal indicating events are being suppressed.

| Policy type | Selection basis | Strengths | Key risk |
| --- | --- | --- | --- |
| Probabilistic | Probability | Simple, decentralized | Can drop rare events |
| Deterministic | Hash/stable key | Keeps groups of records consistent | Skewed or unsafe key |
| Rate limiting | Time-window threshold | Controls bursts | Can mask large incidents |
| Deduplication | Fingerprint/error group | Cuts repeated logs | Merging distinct errors by mistake |
| Level filtering | Severity | Tunes verbosity | Loses context if misclassified |

## 4. Calculating Sampling Rate and Expected Record Counts

Suppose there are $N$ eligible log events and the sampler keeps each event with probability $p$. The expected number of retained records is:

\[
E[K] = N \times p
\]

For example, if an application emits 2,000,000 `INFO` log records per day with sampling $p=0.05$:

\[
2{,}000{,}000 \times 0.05 = 100{,}000
\]

The expected number of retained records is 100,000 per day. This is not an exact guarantee; actual counts fluctuate with randomness, traffic volume, and policy.

### 4.1. Statistical Variance

With independent Bernoulli sampling:

\[
Var(K)=Np(1-p)
\]

\[
\sigma=\sqrt{Np(1-p)}
\]

If $N=1{,}000$ and $p=0.1$, the expectation is 100 records with a standard deviation of about 9.49. Observing 90 or 110 records in a small batch does not prove the configuration is broken.

### 4.2. Estimating Storage Volume

Suppose each JSON record averages 800 bytes, $N=2$ million records/day, and $p=0.05$:

\[
100{,}000 \times 800 = 80{,}000{,}000\text{ bytes}
\]

That is roughly 80 MB/day before compression, transport metadata, index overhead, and retention. Actual size must be measured at the backend because records with stack traces are usually much larger than simple success logs.

Do not take the average size of a single `INFO` line to project the entire log pipeline if the system emits many exception stack traces or varied payloads.

## 5. Deciding Which Logs May Be Sampled

Never apply a single probability blindly across every logger and every severity.

A reference classification:

| Group | Examples | Suggested policy |
| --- | --- | --- |
| High-volume success | Request completed, cache hit | Sample or replace with metrics |
| Repetitive diagnostics | Retry attempt, polling status | Sample/rate-limit with summary |
| Debug details | Protocol detail while debugging | Time-bounded log level/config |
| Recoverable warning | Slow dependency with successful fallback | Rate-limit with suppression counter |
| Failed request error | Database unavailable, uncaught exception | Protect log path; do not sample randomly by default |
| Security event | Authentication failure, policy violation | Follow security policy, usually retain all required events |
| Audit event | Permission changes, legally audited transactions | Never apply sampling that drops required records |

This table is a design guide, not an absolute rule. A warning can be a critical signal in a payment system; an error can be an expected business outcome. Classify based on semantics, operational needs, and retention rules.

### 5.1. Never Let Sampling Hide System Failures

If every exception passes through a probabilistic filter, a widespread outage can lose most of its trail. Better practices:

- Prioritize detection via metrics and alerts.
- Protect error records with diagnostic value.
- Trim repetitive logs at retry/polling layers.
- If error bursts must be controlled, use rate limiting/dedup with suppression counters and summaries.
- Maintain a dedicated log path for audit/security per policy.

If a downstream log pipeline samples independently without the application knowing, track drop counts at the collector/agent and define policies per source.

## 6. Sampling in Spring Boot and Logging Backends

Spring Boot provides logging integration and log-level configuration, but there is no universal single property named `log-sampling-probability` applying across all logging backends.

Since Spring Boot defaults to Logback in many applications, you can customize appenders/filters or use an agent/collector with a sampling processor. With Log4j2, filter/appender mechanics differ. Configuration must match your actual backend.

Example logging levels in `application.yml`:

~~~yaml
logging:
  level:
    root: INFO
    org.springframework.web: WARN
    example.orders: INFO
~~~

This is level filtering, not probabilistic sampling. Never describe changing `DEBUG` to `INFO` as log sampling.

### 6.1. Why Not Put One Generic Filter into Every Spring Boot App?

Logback, Log4j2, JUL, and logging pipeline agents have different APIs. A filter written for Logback does not work as-is on Log4j2. Verify the actual logging implementation, version, and where events originate before picking a solution.

If sampling runs in the collector/agent, the application may emit everything while the backend receives a subset. If sampling runs inside the appender, events are dropped before hitting disk/console. The two approaches differ in disk I/O, network bandwidth, cost, and availability of local logs if the collector fails.

## 7. Example Probabilistic Logback Filter

Logback supports filters on appenders. A custom filter can return accept/deny based on logger, level, and a random draw. The example below illustrates the idea; the filter class must be packaged in the application and configured properly for your Logback version.

~~~java
package example.logging;

import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.filter.Filter;
import ch.qos.logback.core.spi.FilterReply;

import java.util.concurrent.ThreadLocalRandom;

public class InfoSamplingFilter extends Filter<ILoggingEvent> {
    private double probability = 0.1;

    public void setProbability(double probability) {
        if (probability < 0.0 || probability > 1.0) {
            throw new IllegalArgumentException(
                    "probability must be between 0 and 1");
        }
        this.probability = probability;
    }

    @Override
    public FilterReply decide(ILoggingEvent event) {
        if (event == null) {
            return FilterReply.NEUTRAL;
        }

        // Sample INFO only; preserve WARN/ERROR and other levels.
        if (!Level.INFO.equals(event.getLevel())) {
            return FilterReply.NEUTRAL;
        }

        return ThreadLocalRandom.current().nextDouble() < probability
                ? FilterReply.ACCEPT
                : FilterReply.DENY;
    }
}
~~~

This filter illustrates a simple policy:

- Applies probability only to `INFO`.
- `WARN`/`ERROR` are not dropped by this filter.
- Unknown events return `NEUTRAL` so downstream filters/appenders continue evaluating.
- `probability` lies in the range `0.0`–`1.0`.

**Important note:** a filter returning `ACCEPT` can short-circuit the filter chain in some configurations; other filters and appender composition must be verified against your Logback version. The example also lacks counters for dropped records, does not classify specific loggers, and does not keep a coherent set of success logs per request. Before production use, add metrics, test the filter chain, check file/console appenders, and verify filter ordering.

Do not attach this filter globally without selectivity. Scope it to specific loggers or an appender dedicated to high-volume success logs.

## 8. Request-Consistent Sampling

Independent per-record probabilistic sampling can keep the first line of a request while dropping the last, or keep an exception context while dropping the preceding step. When investigating multi-step workflows, this yields fragmented clues.

A better option for some use cases is deterministic sampling keyed on an existing trace ID/correlation key. All log records sharing the same key can be selected together by the policy.

~~~text
traceId = 4bf92f...
hash(traceId) -> sampling bucket
bucket < threshold -> keep log group
otherwise -> drop eligible log group
~~~

Advantages:

- Log records from the same trace have a consistent chance of being kept together.
- The backend can retrieve a reasonably complete sample workflow.
- Multiple services can follow the same rule if key and algorithm are standardized.

Limitations:

- Can only use the key if context already exists when the sampling decision runs.
- A trace ID is not a secret, yet remains an identifier; restrict access/log exports.
- If a request lacks trace context, a fallback policy is required.
- Deterministic sampling on a skewed key can yield uneven retention rates.
- Critical logs such as security/audit should not be dropped merely because their trace group was not selected.

Do not write a custom hash sampler with raw string concatenation and ship it to production without evaluating algorithm stability, encoding, salt/versioning, and key distribution.

## 9. Can Trace Sampling and Log Sampling Coordinate?

They can coordinate, provided it is done intentionally.

Example:
- Trace sampler retains 10% of traces.
- Log policy retains most/all `ERROR` logs.
- Success `INFO` logs are sampled by trace ID at 10%.
- Metrics `Counter`/`Timer` still record every eligible request.

~~~mermaid
flowchart TD
  A["Request"] --> B["Trace sampler"]
  A --> C["Application logging"]
  A --> D["Metrics"]
  B --> E["Trace retained or dropped"]
  C --> F{"Log category"}
  F -->|"ERROR / protected"| G["Keep"]
  F -->|"Routine INFO"| H["Log sampler"]
  H --> I["Keep selected logs"]
  H --> J["Drop and count"]
  D --> K["Record metrics normally"]
~~~

If success logs must align with sampled traces, the log pipeline must read the same trace sampling context or apply a unified key/policy. Do not assume Logback automatically knows whether the trace sampler chose a trace.

Never put trace IDs into metric labels to connect signals. Use trace/span correlation in logs and exemplars/links where the metrics backend supports them.

## 10. Sampling at Application, Agent, or Collector?

Log events can be sampled at several layers:

| Location | Strengths | Things to watch |
| --- | --- | --- |
| Application/logger filter | Cuts log creation/write cost early | Requires careful classification and local troubleshooting |
| Logging appender | Caps file/console output per policy | Backend/version-dependent; filter chains easy to misconfigure |
| Agent/forwarder | Decouples policy from app code | App still pays formatting/emitting cost before drop |
| Collector processor | Centralized management across sources | Uses network/ingest before sampling; needs processor state/policy |
| Backend ingestion | Central policy without app changes | May still incur ingest and transport costs beforehand |

If the goal is cutting network/ingest costs, sampling at the agent/collector before sending to the backend can work, though Collector sampling happens after the Collector has already received the data. To reduce appender/disk overhead, enforce the policy earlier in the application.

If local log files serve as a fallback investigation source when the Collector is down, do not accidentally drop all records in the app before the file appender receives them. You can use separate appenders with separate policies.

## 11. Measuring Retained and Dropped Records

Opaque sampling makes operators think the application stopped emitting logs for an event type. Every policy needs measurements:

- Total eligible log events.
- Retained records count.
- Dropped/suppressed records count.
- Actual sampling ratio.
- Filter/collector error count.
- Summary events emitted for collapsed groups.

Conceptual metric examples:

~~~text
application_log_events_total{category="routine_info"}
application_log_events_kept_total{category="routine_info"}
application_log_events_dropped_total{category="routine_info",reason="sampled_out"}
application_log_events_suppressed_total{category="retry_warning"}
~~~

These names are illustrative custom metrics, not built-in Spring Boot meters. Use bounded label values like `category`, `reason`, and logger group; never add trace ID, request ID, or message text as labels.

The keep ratio can be computed as:

\[
keep\_ratio = \frac{kept}{eligible}
\]

If `eligible` equals 0, do not compute the ratio. Compare the observed ratio against the configured probability over a window with enough records. With rate limiting/dedup, the effective ratio depends on bursts and windows rather than a fixed probability.

## 12. Structured Logging and Sampling Decisions

Structured logs let policies classify by event name/category instead of brittle message substrings.

Illustrative record example:

~~~json
{
  "timestamp": "2026-11-22T10:15:21.104Z",
  "level": "INFO",
  "service.name": "order-service",
  "event.name": "orders.request.completed",
  "log.category": "routine_success",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "duration_ms": 42,
  "outcome": "success"
}
~~~

A policy can select events using `log.category` or `event.name`. Do not rely solely on substrings in `message`, as message phrasing can change across versions or languages.

Structured fields also need an allowlist: `duration`, `outcome`, and service metadata can be useful; raw user inputs, request bodies, credentials, and PII should never become sampling keys or default exported fields.

## 13. Rate Limiting and Deduplication for Burst Logs

Probabilistic sampling is not the only answer when an error repeats constantly. For example, an unavailable dependency causes thousands of requests to log the exact same stack trace.

You can use rate limiting/deduplication:

~~~text
Fingerprint: dependency=inventory, exception.type=SocketTimeoutException
Window: 60 seconds

Emit:
  - the first event in the window
  - a summary at window end with suppressed_count
  - a recovery log when state returns to normal (if applicable)
~~~

The summary should include:
- Normalized fingerprint containing no arbitrary message/user input.
- Count of suppressed events.
- First and last observed timestamps.
- Relevant service/dependency/operation.
- One trace exemplar if available and permitted for storage.

Do not merge exceptions with different root causes simply because their message text looks similar. Also track the suppressed count; otherwise on-call teams can underestimate an incident's scale.

## 14. Security, Audit, and Retention

Before sampling logs, classify data and retention obligations:

**Security events:** failed logins, permission changes, access denials, and abuse-detection signals may need complete retention per policy. Never drop them through routine sampling if doing so breaks detection or investigation.

**Audit events:** transactions or configuration changes requiring completeness/integrity must go through a separately controlled audit/event store. Application log sampling should never decide whether an audit event is stored.

**Sensitive data:** never use sampling to hide a data leak. Prevent secrets/PII from entering logs at the source, redact before export if needed, and enforce retention/access per policy.

**Retention:** cutting log volume does not replace designing retention windows, read permissions, encryption, backups, and legal holds. Sampling can alter how representative log history is; operational docs should state the policy and when it applies.

## 15. Common Mistakes When Implementing Log Sampling

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| Lost `ERROR` logs | Filter applied globally by mistake or wrong classification | Test every severity and protected loggers |
| Success logs exist without traces | Log sampling and trace sampling are independent | Check each decision/pipeline |
| Traces exist without success logs | Log policy samples/dedups records | Check sampling counters and event category |
| Actual ratio far from probability | Low volume, other filter chains, multiple sources, or post-sample drop | Measure eligible/kept/dropped at the right layer |
| Warning burst vanishes without a trace | Rate limiter emits no summary/counter | Track suppressed counts and summary events |
| Local file missing logs present in backend | Appender filters differ | Inspect appender topology |
| App still burns CPU though backend receives less | Collector samples after app already formatted/emitted | Consider earlier filtering if app cost is the target |
| Exception stack trace lost | Logger logs text message, encoder/filter strips throwable | Check `Throwable` overload and encoder |
| Inconsistent sampling by trace ID | Key/algorithm or context differs across services | Standardize hashing and propagation |
| Audit records dropped | Sharing sampler with routine logs | Separate audit path and policy |
| High cardinality on log-drop metrics | Using message/ID as metric label | Use bounded `category`/`reason` only |
| Unknown number of dropped records | Missing eligible/drop counters | Instrument policy and suppression dashboard |

### Debugging Workflow

1. Identify which logger and category produced the log record.
2. Identify which sampling/filter layer is active.
3. Check severity/category and whether rules match.
4. Measure eligible, kept, dropped, and suppressed counts.
5. Inspect appender ordering/filter chain.
6. Check agent/collector after the record leaves the process.
7. Check trace sampling separately; do not infer it from log presence.
8. Verify protected event paths and security/audit policies.

## 16. Real-World Scenario: High-Volume Success Requests and Inventory Warning Burst

**Scenario:** `order-service` handles heavy successful traffic. Each request emits `INFO` logs in controller, service, and client. When inventory becomes flaky, a retry loop produces thousands of `WARNING`s within minutes.

### Step 1 — Keep Metrics as the Aggregate Source

Maintain `Counter`s for request count, success, failure, retry, and fallback. Use bounded labels such as `operation`, `outcome`, and `dependency`. Never reduce a `Counter` based on log sampling.

### Step 2 — Trim Routine `INFO`

Select the `orders.request.completed` event category and apply deterministic or probabilistic sampling at a tested rate. Preserve logs with trace context if trace/log consistency policy requires it.

### Step 3 — Control Retry Warnings

Rate-limit repeated warnings by fingerprint `dependency + exception type`. Emit the first event, a summary with `suppressed_count`, and a recovery log. Never drop warnings without counting them.

### Step 4 — Protect Error/Security Paths

Log `ERROR` when a request ultimately fails at the designated boundary. Retain security/audit records under their own policy. Never route these categories through a routine sampler.

### Step 5 — Inspect All Three Signals Together

Metrics show total requests/retries and error rates. Sampled traces reveal execution paths for some requests. Remaining logs carry `traceId`/`spanId` to open the matching trace if stored; if the trace was dropped, logs still carry operation/service/time and safe correlation keys.

**Expected outcome:** lower log volume, zero unintended loss of error/security signals, summarized warning bursts, and metrics still reflecting full traffic.

## 17. Lab Exercises and Self-Check Questions

### Exercise A — Classifying Log Events

Create event categories: `routine_success`, `retry_warning`, `dependency_error`, `security_event`, and `audit_event`. Define whether each category uses probabilistic sampling, rate limiting, deduplication, or protection. State the rationale and policy owner.

### Exercise B — Calculating Volume

An application emits 5 million `INFO` logs/day with $p=0.02$, averaging 600 bytes per record. Compute expected record count, daily payload before compression, and unaccounted assumptions.

### Exercise C — Testing a Logback Filter

Create a filter that samples only `INFO`. Emit 10,000 `INFO`, 100 `WARN`, and 20 `ERROR`. Count eligible/kept/dropped per category; confirm `WARN`/`ERROR` are not dropped by the filter. Verify the appender chain and throwable output.

### Exercise D — Deterministic Sampling by Trace

Use a test trace ID as the sampling key for routine logs. Ensure records sharing a trace receive the same decision across two services. Test requests without trace context and design a fallback. Never use personal IDs or secrets as keys.

### Exercise E — Burst Suppression

Simulate a dependency timeout generating thousands of identical warnings. Cap records within a window, emit a `suppressed_count` summary and a recovery event. Compare against retry/timeout metrics to prove scale is not hidden.

### Exercise F — Separating Signal Policies

Set trace sampling to 10%, success log sampling to 5%, error logs protected, and metrics recorded at 100%. Generate test traffic, verify record counts in each pipeline, and explain why their percentages do not need to match.

### Self-Check Questions

1. How does log sampling differ from trace sampling?
2. Why is changing the logging level not the same as sampling?
3. Does probabilistic sampling guarantee keeping exact $p$ percent in every minute?
4. What advantage does deterministic sampling by trace ID offer?
5. When is rate limiting better than probabilistic sampling?
6. Why should audit events never pass through a routine sampler?
7. How does sampling at the appender differ in cost from sampling at the Collector?
8. Why are eligible/kept/dropped counters needed?
9. How do you ensure `ERROR` logs are not filtered out by mistake?
10. Why must metrics still record 100% when success logs are sampled?
11. How do structured event categories keep sampling policies stable?
12. What summary fields does burst suppression need so incident scale is not hidden?
13. Can logs remain when a trace is dropped by sampling?
14. Can a trace remain when application logs are sampled out?
15. What data must never be used as a sampling key or log attribute?

**Completion criteria:** distinguish log sampling from trace sampling/level filtering; understand probabilistic, deterministic, rate limiting, and dedup; classify protected logs; configure filters/appenders matching the backend; measure eligible/kept/dropped; preserve correlation context; enforce security controls and test bursts.

## 18. Takeaways

- Log sampling selects eligible log records to reduce volume; it is independent of trace sampling and metrics recording.
- Probability $p$ yields an expected record count, not a guarantee over every small time window.
- Log level filtering, probabilistic sampling, deterministic sampling, rate limiting, and deduplication are distinct mechanisms.
- Classify logs by semantics. Never let routine sampling drop audit/security events or essential error signals.
- Appender sampling reduces write costs at the appender; agent/Collector sampling occurs after the application already built and emitted the record.
- Deterministic sampling on a trace/correlation key keeps related logs together, but requires context, a safe key, and a stable algorithm.
- Track eligible, kept, dropped, and suppressed counts. Never drop events without metrics.
- Use structured events/categories for stable policies; avoid matching on free-text messages.
- Metrics continue quantifying requests/errors/latency; traces show selected executions; logs provide events. Never infer total requests from retained log counts.
- Protect secrets/PII, keep log ownership clear, and verify the filter chain against the real logging backend.

## References

- [Spring Boot Reference — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html)
- [Logback Manual — Filters](https://logback.qos.ch/manual/filters.html)
- [Logback Manual — Appenders](https://logback.qos.ch/manual/appenders.html)
- [SLF4J Manual](https://www.slf4j.org/manual.html)
- [OpenTelemetry Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/)
- [OpenTelemetry Collector — Filter Processor](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/processor/filterprocessor)
- [OpenTelemetry — Sampling concepts](https://opentelemetry.io/docs/concepts/sampling/)
- [Micrometer Observation Reference](https://docs.micrometer.io/micrometer/reference/observation.html)
