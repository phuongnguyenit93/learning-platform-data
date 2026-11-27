# Log Volume Budget for Spring Boot

## 1. Purpose and Context

Logs help investigate errors and understand system behavior, yet every log event has a cost: CPU to create/serialize, I/O to write, network to forward, storage to index, and operator time to search. When traffic climbs or an error repeats thousands of times per second, unbounded logging can drive up costs, congest pipelines, and even slow down the application.

A **log volume budget** is a measurable, manageable budget for the amount of logs generated, forwarded, and stored over a period of time. The budget should align with operational goals: retaining enough important events to investigate incidents while controlling bytes, event rate, retention, and cost.

This lesson belongs to the **Observability Performance** chapter of the **SPRING_BOOT_OBSERVABILITY** module. The module teaches how to set up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing; you will learn context propagation, tags/cardinality, exporters, sampling, and signal correlation to investigate errors, latency, and application behavior in production environments.

After this lesson, you will be able to:
1. Estimate log volume from event rate and average event size.
2. Allocate budgets by service, environment, severity, and event class.
3. Reduce log noise using sampling, aggregation, and deduplication.
4. Retain error, security, and audit events as required.
5. Design structured logging with stable fields and controlled cardinality.
6. Set retention, ingestion, and storage targets.
7. Measure overhead and test logging under load.

**Baseline:** Spring Boot 3.5.x, Java 17+, SLF4J/Logback, and a centralized log collector. Numbers are illustrative; real budgets depend on backend, indexing strategy, compression, and retention requirements.

## 2. What Makes Up Log Volume?

Line count alone does not determine cost. Distinguish:

| Quantity | Meaning | Common unit |
| --- | --- | --- |
| Event rate | Number of log events generated | events/second (EPS) |
| Average event size | Average serialized size per event | bytes/event |
| Ingest volume | Data entering the collector/backend | MB/GB per day |
| Indexed volume | Data after parsing/indexing | GB per day |
| Retained volume | Data currently stored | GB/TB |
| Query volume | Data read during search/alerts | bytes scanned |

JSON logs can be larger than pattern text due to repeated field names and metadata. Compression shrinks transmission/storage size, but does not necessarily reduce indexing or query costs at the same ratio.

## 3. Calculating a Basic Budget

Approximate formula:

```text
raw_bytes_per_day = events_per_second
                    × average_event_bytes
                    × 86,400

ingest_GB_per_day = raw_bytes_per_day / 1,000,000,000
```

For example, a service generates an average of 250 events/second, each 900 bytes:

```text
250 × 900 × 86,400 = 19,440,000,000 bytes/day
                    ≈ 19.44 GB/day (decimal)
```

This is raw volume before compression, replication, and index overhead. If the backend retains 14 days, raw retained volume is roughly 272.16 GB for this service, excluding replicas/indexes.

For capacity planning, also factor in:
- Peak EPS, not just average EPS.
- Burst duration and service replica count.
- JSON field growth across releases.
- Measured compression ratio.
- Replication factor and index overhead.
- Retention by tier/severity.
- Retries/replays during collector or backend disruptions.

### 3.1. Budgets Must Specify Units and Scope

A useful budget states clearly:
- Scope: service, cluster, environment, or tenant tier.
- Window: minute, hour, day, or month.
- Limit: EPS, bytes/day, or bytes/month.
- Alert threshold: warning level before hitting the limit.
- Owner: responsible team.
- Exception policy: which logs must never be dropped.

Sample budget example:

| Scope | Illustrative target | Alert |
| --- | ---: | ---: |
| Single production service | 20 GB/day raw | 80% of budget |
| Error events | No intentional drops | Any drop |
| Production debug logs | Time-bounded enablement only | Exceeding allowlist |
| Security/audit events | Dedicated retention policy | Delivery failure |

Do not apply one number across every service. API gateways, batch processors, and low-traffic admin services have different log profiles.

## 4. Allocating Budgets by Severity and Event Class

Not every log event has equal value. A policy might divide them as:

| Class | Examples | Policy |
| --- | --- | --- |
| ERROR | Failed requests, dependency unavailable | Keep events; deduplicate/rate-limit alerts if needed while preserving evidence |
| WARN | Retries, fallbacks, degraded mode | Keep per event semantics; aggregate repeated warnings |
| INFO | Business lifecycle milestones | Select events with operational value; avoid logging every minor step |
| DEBUG/TRACE | Payload diagnostics, internal state | Off by default in production; enable with scope and expiry |
| SECURITY/AUDIT | Login failures, privilege changes, data access audits | Follow security/audit policy; never drop arbitrarily |

Severity is not the only criterion. An INFO event may be a mandatory audit record; an ERROR repeating millions of times may require aggregation to keep the pipeline unclogged, while preserving counters/summaries and representative events.

## 5. Measuring Actual Volume

Do not rely solely on estimates from source code. Measure at least at two points: the application process and the collector/backend.

Metrics to collect:
- EPS by service, environment, severity, and logger.
- Bytes/second before and after compression.
- Top logger/event names by volume.
- Ratio of duplicate/repeated messages.
- Drop count, queue depth, and exporter retries.
- CPU time and allocations spent on logging.
- Backend ingest/index latency and storage growth.

A structured log schema allows grouping by event name instead of parsing message text. For instance, `event.name=payment.authorization.failed` is far more stable than grouping by a message containing an order ID.

## 6. Structured Logging to Reduce Noise

Log events should have stable fields, concise messages, and useful context:

```json
{
  "timestamp": "2026-11-22T10:15:30Z",
  "level": "WARN",
  "service": "order-service",
  "environment": "production",
  "event.name": "order.retry.scheduled",
  "dependency": "inventory",
  "attempt": 2,
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "message": "Inventory request will be retried"
}
```

This is an illustrative schema. Avoid putting request bodies, credentials, raw SQL parameters, or personal data into events. Use `traceId`/`spanId` to jump to traces when needed rather than repeating full execution details in every log line.

### 6.1. Use Stable Event Codes

Prefer event names/codes with a finite vocabulary:
- `payment.authorization.started`
- `payment.authorization.failed`
- `inventory.lookup.timeout`
- `order.retry.scheduled`

Do not embed IDs into event names or logger names. Messages can describe context, while queries/dashboards should rely on stable fields.

## 7. Sampling, Aggregation, and Deduplication

These three techniques solve different problems:

| Technique | Effect | Risk to control |
| --- | --- | --- |
| Sampling | Keeps only a fraction of eligible events | May miss a rare yet important event |
| Aggregation | Collapses repetitions into a summary/count/window | Loses per-occurrence detail |
| Deduplication | Eliminates duplicates from retries/duplicate delivery | May conflate two distinct legitimate events |

### 7.1. Sampling Routine Logs

Sampling is best suited for high-volume diagnostic events such as successful polling or repetitive debug messages. For example, keep 1% of successes while retaining errors per policy:

```java
if (random.nextDouble() < 0.01) {
    log.debug("Cache refresh completed");
}
```

This is illustrative only. In production, sampling should be deterministic by request/trace key when correlated logs for the same operation must stay together; avoid independent per-line random sampling that leaves fragmented logs for a trace.

Never sample security/audit records or compliance-mandated events. Error logs also need a clear policy: retain representative events, aggregate repeated failures, and emit a metric/counter for total occurrences.

### 7.2. Aggregating Repeated Errors

Instead of logging a full stack trace for every occurrence of the same error, you can:
1. Log an initial event with exception class and dependency.
2. Increment a counter for every occurrence.
3. Aggregate repetitions by time window and a safe error fingerprint.
4. Emit a periodic summary, e.g., `failure_count=1842` in 1 minute.
5. Still keep representative samples and important state transitions.

Fingerprints must not contain raw messages/PII; use normalized exception class, operation code, and error category.

## 8. Do Not Use Log Sampling in Place of Metrics

If the goal is an exact occurrence count, use counters/metrics. Log sampling intentionally drops event-level detail, so remaining logs do not reflect total counts unless sampling rates/weights are recorded.

Example:
- A metrics counter counts all retry attempts.
- Logs retain a sample of successful retries and all abnormal transitions per policy.
- Traces sample according to trace-level policy.

Do not sum sampled log lines and treat them as total errors. If estimation is needed, you must know the sampling probability and accept error bars; for operational counts, metrics are usually far better suited.

## 9. Spring Boot and Logback

Spring Boot defaults to Logback when using the logging starter. Log levels can be configured per package:

```yaml
logging:
  level:
    root: INFO
    com.example.orders: INFO
    com.example.orders.diagnostics: WARN
```

Enable DEBUG/TRACE in production only within a narrow scope and with a time limit. With structured logging, pick a consistent encoder/schema; do not log the same event in the controller, service, and global exception handler.

Example of avoiding duplicate logging:

```java
public Order submit(OrderCommand command) {
    // Business method propagates exception to the HTTP boundary.
    return orderRepository.save(map(command));
}
```

The global boundary can log a single failure event with trace context and exception details per policy. Lower layers should only add logs when they carry unique required context, rather than logging the same stack trace and rethrowing.

### 9.1. Async Logging

An async appender reduces blocking I/O on application threads, but uses a bounded queue. When the queue fills up, the logging framework may block or drop events depending on configuration. You should:
- Monitor queue depth and dropped-event counters.
- Size the queue for bursts and memory budget.
- Define queue-full behavior: block, drop low-priority events, or fall back.
- Never assume async logging guarantees delivery.
- Test shutdown/flush and collector outages.

## 10. Retention and Storage Tiers

Log volume budgets directly tie into retention. Keeping every event for the same duration and at the same index tier is usually unnecessary.

Tiering example:

| Tier | Data | Illustrative retention |
| --- | --- | ---: |
| Hot | Errors, recent operational logs needing fast search | 7 days |
| Warm | Operational logs with reduced indexing/cost | 30 days |
| Cold/archive | Audit/security records per policy | Per organizational requirement |

These are only examples; retention must follow legal, contractual, security policy, and data-processing requirements. Never shorten audit retention just to save cost.

Cost reductions can be achieved by:
- Dropping unindexed or unneeded fields.
- Reducing cardinality and dynamic field counts.
- Compressing before archiving.
- Using index lifecycle/data tiering.
- Applying distinct retention periods by event class.
- Purging expired data across replicas and backups per procedure.

## 11. Estimating Budgets for Peak Traffic

Suppose a service has 6 replicas, each producing an average of 40 EPS, with peak at 3x average, and average event size of 700 bytes.

```text
average EPS = 6 × 40 = 240
peak EPS    = 240 × 3 = 720
raw GB/day  = 240 × 700 × 86,400 / 1,000,000,000
            ≈ 14.52 GB/day
```

Collector capacity must handle peak load near 720 EPS or 504 KB/s raw in this example. If a burst lasts long, queues only delay hitting backend capacity; they do not eliminate volume.

Budgets should include headroom for deployment rollouts, incident bursts, and debug windows. Never size capacity strictly to the average.

## 12. Alerting and Budget Enforcement

Set up alerts when:
- Ingest bytes reach 70–80% of budget.
- EPS exceeds baseline across multiple windows.
- Async queue occupancy or drop count rises.
- Collector exporter retries or backend ingest lag increases.
- Error log rate spikes suddenly.
- Retention/storage forecasts exceed capacity.

Enforcement can throttle noisy DEBUG/INFO events first, but never drop audit/security events or critical error transitions without an approved policy.

During an incident, temporary diagnostics may be enabled per runbook: specify service/endpoint scope, severity, expiry, owner, data classification, and turn-off plan. After the incident, verify log levels return to baseline.

## 13. Testing Logging Under Load

Tests should measure both correctness and overhead:
1. Generate representative traffic with successes, errors, retries, and bursts.
2. Measure baseline EPS and bytes/event.
3. Compare CPU, allocations, GC, and request latency with structured logging enabled.
4. Simulate slow/disconnected collectors to verify queue/drop behavior.
5. Confirm error/audit events are retained per policy.
6. Verify sampling rates and ensure event counts are not misinterpreted.
7. Verify zero PII/secrets appear in logs.
8. Verify shutdown flush and post-outage recovery.

Do not use a benchmark with only short log messages to represent production JSON logs carrying stack traces and MDC fields.

## 14. Troubleshooting

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Ingest spikes suddenly | Retry loop or repeated error generating many stack traces | Aggregate/deduplicate and maintain a total counter |
| Storage grows despite stable EPS | Event size grew, extra fields added, or long stack traces | Analyze bytes/event and schema diffs |
| Request latency rises when logging is enabled | Synchronous I/O, serialization, or appender blocking | Measure logging overhead and configure async with a queue policy |
| Logs lost when backend is slow | Async queue full or exporter dropping | Monitor drop counters, queues, and retry policies |
| Expensive search | Too many indexed fields or high cardinality | Select indexed fields and normalize values |
| Insufficient data for debugging | Overly aggressive sampling or missing representative events | Tune policy and correlate metrics/traces |
| Total error count mismatches log count | Logs are sampled/aggregated | Use a metrics counter as the counting source |
| Single error appears across multiple layers | Multiple layers log and rethrow | Pick one logging boundary |
| Budget exceeded during peak hours | Sized to average only, ignoring peak/replica count | Size capacity for peak and headroom |
| Audit events disappear | Global sampling/drop applied across all severities | Separate audit pipeline and retention policy |
| Debug level left on after incident | No expiry/owner on temporary config | Automate runbook and verify baseline |

## 15. Production Checklist

- [ ] Budget defines scope, unit, time window, owner, and alert threshold.
- [ ] Both average and peak EPS/bytes are estimated.
- [ ] Structured log schema uses stable event names.
- [ ] No secrets, PII, or unnecessary request bodies are logged.
- [ ] Sampling applies only to eligible event classes.
- [ ] Error/security/audit events have dedicated preservation policies.
- [ ] Metrics counters serve as the accurate source for operational totals.
- [ ] Aggregation/deduplication retains summaries and representative evidence.
- [ ] Async queues, drop counts, and exporter retries are monitored.
- [ ] Retention/index/storage tiers match data policy.
- [ ] Temporary DEBUG/TRACE settings have an owner, scope, and expiry.
- [ ] Load tests include bursts and collector outages.

## 16. Practice Questions

1. How does a log volume budget differ from a log line count limit?
2. How do you calculate raw GB/day from EPS and average event size?
3. Why should capacity be sized for peak rather than average?
4. What distinct problems do sampling, aggregation, and deduplication solve?
5. Why shouldn't security/audit events be sampled arbitrarily?
6. Why are metrics counters better than sampled logs for counting total errors?
7. When can an async appender drop logs?
8. How do stable event names reduce query noise?
9. How do retention tiers affect cost and incident investigation?
10. Which indicators should trigger alerts to detect a budget breach?
11. Why must collector outages and shutdown flushes be tested?
12. How do you enable temporary DEBUG logging without forgetting to turn it off in production?

## References

- [Spring Boot — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html)
- [Logback — Appenders](https://logback.qos.ch/manual/appenders.html)
- [Logback — Configuration](https://logback.qos.ch/manual/configuration.html)
- [OpenTelemetry — Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/)
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [Micrometer — Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html)
- [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
