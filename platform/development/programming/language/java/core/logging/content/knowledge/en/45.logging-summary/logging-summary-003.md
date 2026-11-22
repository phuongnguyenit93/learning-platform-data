# Log Content Checklist in Java: From Code Review to Production Acceptance

## 1. Purpose and How to Use the Checklist

A system may already have SLF4J, Logback, or Log4j2 enabled, yet its logs can still be **unhelpful**: log lines fail to state the event clearly, lack a request ID, mark `SUCCESS` before a transaction commits, log at the wrong ERROR level, or accidentally contain tokens, passwords, and personal data. A **log content checklist** is a set of verification questions for **each log event and its data contract** before code is merged or deployed.

This document serves as a summary for **Java Core Logging**, independent of any specific logging backend. For every logger call or structured event, the reviewer needs to confirm:

1. **Should this event be logged?** What is its operational, security, or audit purpose?
2. **At what point is it logged?** Attempted, accepted, denied, committed, completed, or failed?
3. **At what level is it logged?** Does DEBUG, INFO, WARN, or ERROR accurately reflect the severity?
4. **Is there sufficient context?** Service, event type, operation/request/trace ID, route, outcome.
5. **Do fields have the right types and trusted sources?** Numeric status, duration with units, authenticated actor.
6. **Is there any secret or unnecessary data?** Authorization, Cookie, PII, payload, URLs containing tokens.
7. **Can it be read, queried, and correlated?** Valid JSONL, stable field schema, searchable event ID.
8. **Can it be measured and tested?** Positive/negative cases, escaping, async, redaction, actual encoder output.

**The goal is not to log as much as possible.** A compliant log contains **the right information, in the right place, at the right time**, enough for diagnosis without becoming a leak source or a system bottleneck.

## 2. Quick Checklist for Every Log Line Before Merging

Use this table as a **PR review gate**:

| Question | PASS when | FAIL signs |
| --- | --- | --- |
| **Purpose** | Clear search/alert/audit scenario | `logger.info("Here")` answers nothing |
| **Event identity** | Has `event.name`/fixed code | Relies on parsing free-form English sentences |
| **Timing** | Outcome is confirmed at the right milestone | Logging "success" before commit |
| **Severity** | Level matches actual impact | Every 4xx is logged as ERROR |
| **Context** | Service, request/operation/trace ID when available | Cannot distinguish between two requests |
| **Schema** | Consistent field names/types/units | `duration_ms` contains nanoseconds |
| **Source trust** | Actor, tenant, and route come from trusted sources | Taking identity from `X-User-ID` |
| **Safety** | No passwords, tokens, card data, raw body | Logging the entire request object |
| **Bounded size** | Message/stack trace have appropriate limits | Multi-MB logs inside a loop |
| **Actionable** | Has an appropriate error code or safe reason code | "Something went wrong" |
| **No duplication** | Each layer has a clear responsibility | One exception logged as ERROR 4 times |
| **Testability** | Tests exist for fields/types/secrets and output | Only asserting that a mock logger was called |

If a requirement does not apply, explicitly note **N/A and why**. For example, a startup event does not have an HTTP request ID; that is not automatically a bug.

## 3. Decision Checklist: "Should This Event Be Logged?"

Before writing `logger.info(...)`, ask:

- [ ] Does the event serve a clear troubleshooting, operational, security analysis, or audit purpose?
- [ ] Is there already a better metric/trace to represent high-frequency signals?
- [ ] Without logging this event, would the on-call team still have enough data to find the root cause?
- [ ] Is an equivalent log already recorded at another boundary?
- [ ] Does the event help distinguish **causes** or **outcomes**, rather than narrating every obvious step?
- [ ] Is the event needed on every request, or only on state transitions/failures?
- [ ] If frequency increases 100x, will the log remain useful and cost-safe?
- [ ] If auditing is required, does this event need durable storage different from regular application logs?

**Avoid logging every iteration** or every getter call, unless there is a specific diagnostic need and the DEBUG level is controlled. **Do not stay silent** on permission changes, credential compromises, security denials, or business commits with audit obligations just because they increase volume.

### Distinguishing Events and Metrics

An application handling 1,000 requests/s does not necessarily need 1,000 INFO "request started" logs from every helper method. Instead:

- Use a minimal access event at the HTTP boundary.
- Log business events at the actual outcome point.
- Use metric counters/histograms for throughput and latency.
- Use traces for paths across multiple services.
- Log WARN/ERROR when an issue requires attention.

**Log sampling** can reduce diagnostic costs, but it alters representativeness. Do not arbitrarily sample audit/security events that must be preserved.

## 4. Event Name Checklist: "What Happened?"

A log should have a **stable, indexable event name**, for example:

| Scenario | Good event code | Do not just log |
| --- | --- | --- |
| Order completed | `checkout.completed` | `"All good"` |
| Order rejected | `checkout.rejected` | `"Cannot do that"` |
| Dependency failed | `dependency.call_failed` | `"Exception!"` |
| Login rejected | `authentication.failed` | `"Wrong password for..."` |
| Permission denied | `authorization.denied` | `"Bad user"` |
| Token issued | `token.issued` | Actual JWT/token |
| Job accepted | `job.accepted` | `"Job done"` |
| Worker completed | `job.completed` | `"202 returned"` |
| Configuration changed | `configuration.changed` | Dumping new config with secrets |

**Checklist:**

- [ ] Event name is chosen from an owned catalog/enum, not a client-supplied string.
- [ ] Name describes **an event that has occurred**, not an unknown predicted outcome.
- [ ] Semantics distinguish between `started`, `accepted`, `failed`, `completed`, and `committed`.
- [ ] Event codes are versioned/reviewed when changed to avoid breaking dashboards/alerts.
- [ ] Event origin is clear: auth handler, controller boundary, business transaction, or worker.
- [ ] Do not embed dynamic IDs in the name, such as `checkout.completed.123456`, which causes high cardinality.
- [ ] Do not reuse one event name for two business actions with different semantics.

For example, `event.name=payment.completed` is only valid after proof of payment completion; an HTTP `202 Accepted` or sending a request to a gateway is not sufficient.

## 5. Log Emission Timing and Outcome Accuracy Checklist

**Log timing determines truthfulness.** Milestones are not equivalent:

```text
Request received
    │
    ▼
Authentication / authorization
    │
    ▼
Business validation
    │
    ▼
Transaction begin
    │
    ▼
Business state changed
    │
    ▼
Transaction committed
    │
    ▼
Downstream delivery or asynchronous completion
```

Examples:

- `checkout.started`: workflow started, does not indicate success.
- `checkout.rejected`: rejected by a business rule.
- `checkout.accepted`: request accepted for async processing.
- `checkout.completed`: business logic actually met completion criteria.
- `checkout.failed`: failure confirmed according to the corresponding logic.
- `audit.role.granted`: role change committed per contract, not merely calling `save()`.

**Checklist:**

- [ ] Event is emitted at the milestone where the code truly knows the state.
- [ ] Outcomes `SUCCESS`/`FAILED`/`DENIED`/`ACCEPTED` have distinct definitions.
- [ ] HTTP status is recorded according to the measurement boundary; not inferred as a business commit.
- [ ] Retries and duplicates use an operation ID/attempt ID to distinguish them.
- [ ] If a transaction rolls back, no false "committed" event remains.
- [ ] If an event must be durable alongside the transaction, an outbox/audit store has been evaluated.
- [ ] Asynchronous jobs use two milestones—accepted/completed—when needed.
- [ ] Pre-authentication failures do not attribute an authenticated user from a self-declared username.

**An important testing rule:** on transaction rollback, verify no false `COMMITTED` event is emitted; on a 202 job, verify an `ACCEPTED` event and a separate completion event emitted by the worker.

## 6. Log Level Checklist: DEBUG, INFO, WARN, ERROR

| Level | Use when | Do not use when |
| --- | --- | --- |
| TRACE | Very deep detail, time-boxed, from safe data sources | Dumping secrets or enabling across production long-term |
| DEBUG | Diagnostic data within package/service scope | Logging full objects regardless of privacy |
| INFO | Meaningful system and business state changes | Logging every loop iteration with no value |
| WARN | Recoverable anomalies or conditions needing attention | Every business validation rejection is WARN |
| ERROR | Failures needing investigation / impacting processing capability | Every 400/401/404 is ERROR |
| FATAL/SEVERE | Backend-specific, highest severity level | Assuming every facade shares the same enum |

SLF4J typically uses `WARN`; JUL uses `WARNING`; Log4j2 has its own levels. **Do not assume one backend's enum name is the exact output of another backend.**

- [ ] Level is based on **impact and response need**, not just HTTP status.
- [ ] WARN/ERROR are sparse and high-quality enough for alerting.
- [ ] Do not log ERROR with the same exception at every layer if no new context is added.
- [ ] Do not use a lower level to intentionally hide mandatory audit/security events.
- [ ] Disabled DEBUG does not perform unnecessary expensive formatting/`toString()` computations.
- [ ] Temporary level increases have an owner, scope, rollback time, and privacy check.
- [ ] Test both the effective logger level **and appender/handler filter** when expecting an event to appear.

**SLF4J snippet** example, not standalone Java:

```java
if (logger.isDebugEnabled()) {
    logger.debug("diagnostic_summary={}", buildSafeDebugSummary());
}
```

Using parameterized messages does not make an expensive argument-building method lazy: Java still evaluates `buildSafeDebugSummary()` before calling `debug` without an appropriate guard/supplier.

## 7. Core Fields Checklist in Every Structured Event

A minimal schema template might include:

| Field | Suggested Type | Required? | Owner |
| --- | --- | --- | --- |
| `@timestamp` | ISO-8601 UTC string | Usually | Encoder/event source |
| `level` | enum string | Yes | Logging backend |
| `service.name` | string | Yes | Trusted deployment config |
| `environment` | string | Usually | Trusted deployment config |
| `schema.version` | integer | Yes if contracted | Event schema owner |
| `event.name` | stable string | Yes for business/security events | Event producer |
| `message` | concise string | Optional | Business/event producer |
| `request_id` | validated string | HTTP events when present | Edge/application boundary |
| `trace_id` | 32 lower-hex string | When valid trace exists | Tracing instrumentation |
| `span_id` | 16 lower-hex string | When active span exists | Tracing instrumentation |
| `http.route` | trusted route template | HTTP routed events | Framework/router |
| `http.method` | controlled string | HTTP events | HTTP instrumentation |
| `http.status_code` | integer | Completed HTTP events | HTTP boundary |
| `duration_ms` | integer/long | Timed event | Monotonic timer |
| `outcome` | controlled enum | Event-dependent | Business/security layer |
| `error.code` | controlled string | For coded errors | Error classification |
| `operation_id` | safe string | Jobs/transactions needing correlation | Workflow owner |
| `actor.id` | potentially sensitive string | Policy-driven audit | Verified security context |

**There is no single required schema for every log line**: startup, GC, HTTP access, background jobs, and audit logs have different fields. Schemas should be defined **per event class or event.name**, with clear required and optional fields.

### Per-Field Checklist

- [ ] Naming is consistent across services and versions.
- [ ] JSON numbers remain numbers, booleans remain booleans; do not stringify everything.
- [ ] Duration includes its unit in the name and has clear start/end boundaries.
- [ ] Timestamps include a timezone and do not depend on machine locale.
- [ ] Null, missing, and empty string values have distinct semantics and are tested.
- [ ] Fields have maximum lengths or enums where appropriate.
- [ ] No duplicate JSON keys or collisions with encoder-generated fields.
- [ ] No arbitrary fields injected from request JSON or untrusted metadata.
- [ ] Schema versioning/migration exists when renaming fields or changing data types.

## 8. Log Message Checklist: Short, Meaningful, Free of Live Data

A good structured log can still include a `message` for quick operator reading, but the message **should not be a dumping ground for all data**.

**Do:**

```text
event.name=checkout.rejected
message="Checkout rejected by inventory policy"
error.code="OUT_OF_STOCK"
http.status_code=409
```

**Don't:**

```text
"Checkout rejected for username=user@example.com, token=eyJ..., body={...}"
```

Checklist:

- [ ] Message answers "what happened" without being overly verbose.
- [ ] Prefer event codes and structured fields for filtering; message is only supplementary.
- [ ] Do not concatenate raw client input directly into strings.
- [ ] If user-submitted data is included, fields/values are validated, escaped, and length-limited.
- [ ] No passwords/tokens/cookies/session IDs/card data.
- [ ] Do not generate semantically misleading messages on exceptions or rollbacks.
- [ ] Do not repeatedly log the same error across multiple layers without new context.
- [ ] Messages remain safe even when switching level from INFO to DEBUG.
- [ ] Messages with Unicode/CRLF/quotes are safely encoded for JSONL.

**Messages like "Error: null"** or "Failure!" are insufficient when a safe reason code and processing step can be added; however, do not replace them with a full request dump.

## 9. Time Checklist: Timestamp, Duration, and Clock

The two most error-prone fields are **timestamp** and **duration**.

| Field | Recommended Approach | Common Mistake |
| --- | --- | --- |
| `@timestamp` | Clear UTC/offset, from event source | `LocalDateTime.toString()` missing timezone |
| `ingested_at` | Added by collector/backend on receipt | Mistaking it for when the event occurred |
| `duration_ms` | Delta computed from a monotonic clock | Using `currentTimeMillis` which can jump |
| `timeout_ms` | Configured deadline for dependency call | Confusing with actual elapsed time |
| `retry_delay_ms` | Delay between retry attempts | Accidentally recording nanoseconds |
| `event.sequence` | Sequence if the system actually manages it | Inferring absolute ordering from timestamps |

Example of elapsed time in Java:

```java
// JDK 17 snippet; measurement only, not a standalone program.
long start = System.nanoTime();
try {
    performBusinessOperation();
} finally {
    long elapsedMs =
            java.util.concurrent.TimeUnit.NANOSECONDS.toMillis(
                    System.nanoTime() - start);
    recordDurationMetric(elapsedMs);
}
```

**Units and boundaries must match:** in async execution, the `finally` block of an HTTP method may run before the worker completes. Do not attach `duration_ms` to a `completed` event when only submitting the job.

- [ ] Timestamp is parseable and has an explicit UTC offset.
- [ ] Duration is non-negative; percentages/ratios have appropriate names and units.
- [ ] Do not measure duration using two wall-clock timestamps susceptible to clock adjustments.
- [ ] Tests cover time boundaries, timeouts, and slow dependencies.
- [ ] With async loggers, recognize that event time differs from ingestion time and do not treat lag as business latency.
- [ ] Do not use wall-clock timestamps to infer exactly-once ordering in distributed systems.

## 10. Correlation and Trace Context Checklist

Each long-running request/job may need multiple IDs, but they are **not equivalent**:

| Field | Meaning | Trusted Source |
| --- | --- | --- |
| `request_id` | HTTP request correlation | Generated or validated by server/gateway |
| `trace_id` | Distributed trace correlation | Tracing instrumentation |
| `span_id` | Current span | Tracing instrumentation |
| `operation_id` | Workflow across retries/queues | Business orchestration |
| `event.id` | Distinguishes event/replay/duplicate | Event producer with ID mechanism |
| `job_id` | Job identifier | Job scheduler/queue |
| `tenant.id` | Tenant scope | Authenticated tenant context |
| `actor.id` | Principal performing the action | Verified security context |

Checklist:

- [ ] IDs are validated for format/length before logging; do not use arbitrary strings directly from headers.
- [ ] Trace ID is not treated as user identity authentication.
- [ ] Multiple events emitted by one request have consistent request/trace IDs.
- [ ] Two different requests do not mix context after thread reuse.
- [ ] Async workers have context propagated explicitly, not expecting `ThreadLocal` to cross threads automatically.
- [ ] Non-HTTP events (scheduler/startup) have a policy for absent fields.
- [ ] Do not put baggage containing PII/tokens into every log via MDC.
- [ ] If actor/tenant must be stored, retrieve from verified principal; apply corresponding access control/retention.
- [ ] Do not use request/user/trace IDs as metric labels with unbounded cardinality.

## 11. Exception Logging Checklist: Diagnostic Enough Without Leaking

When an exception occurs, you need to know:

- **Error type** and safe error code.
- **Processing step/dependency class** that failed.
- **Outcome**: retry, fallback, failed, partial success.
- **Request/operation ID** for investigation.
- **Whether the error impacts users**, per the HTTP/business boundary.
- **Stack trace** only when reviewed and the sink has appropriate permissions/retention.

### Good and Bad Patterns

```java
// SLF4J snippet, does not compile standalone.
logger.error("Checkout dependency failed: code={} operation_id={}",
        "INVENTORY_UNAVAILABLE", safeOperationId);

// RISK: exception may contain raw URL/query/token from the HTTP client.
logger.error("HTTP client failed: {}", httpException.getMessage());

// RISK: DTO.toString() may print email/token/card data.
logger.error("Checkout request failed: {}", requestDto);
```

A stack trace can be useful, but `Throwable` messages and nested causes sometimes contain URLs, response bodies, or payloads. **Do not assume `logger.error("...", exception)` is completely safe** just because the parameter is a `Throwable`.

- [ ] Has a safe code and appropriate boundary to classify the error.
- [ ] Does not log raw request/response bodies or secrets inside exceptions.
- [ ] No repeated stack traces across every retry/layer.
- [ ] If retried, the event includes `attempt`/`max_attempts` or equivalent when needed.
- [ ] Errors handled successfully via fallback are not reported as outage-level ERRORs unless policy requires it.
- [ ] When full traces are needed, write only to an authorized sink with tested redaction mechanisms.
- [ ] Test cases where exception messages contain a fake canary.

## 12. Security Checklist: Data That Must Never Enter Default Logs

**Data categories to exclude at the source:**

1. Passwords, OTPs, MFA seeds, recovery codes, password reset tokens.
2. `Authorization`/Bearer tokens/JWTs/access tokens/refresh tokens.
3. Cookies, Set-Cookie, session identifiers, CSRF secrets, private/API keys.
4. PAN, CVV, payment credentials, and unnecessary payment data.
5. Raw request/response bodies of sensitive endpoints.
6. Queries/paths containing tokens, emails, medical records, or private IDs.
7. Webhook signatures, webhook secrets, or full URLs with signed queries.
8. Unapproved PII fields such as email, phone, address, personal profiles.
9. Secrets from configuration/environment exceptions, SQL bind parameters.
10. Uncontrolled headers like `Referer`, `User-Agent`, or forwarded headers that may carry unintended data.

**Mandatory security checklist:**

- [ ] **Field allowlist** is preferred over regex blacklists for raw objects.
- [ ] No raw body/headers/query/URI on auth/token/payment/reset routes.
- [ ] Unknown endpoints use `UNMATCHED`/safe route class, not raw URL fallback.
- [ ] Error handlers/HTTP clients/framework DEBUG logs do not emit secrets.
- [ ] Tokens already written to logs are not "safe" merely because of dashboard masking.
- [ ] If pseudonymization is needed, re-identification risk and processing purpose are evaluated.
- [ ] Security/audit events take actor/outcome from verified sources.
- [ ] Canary tests run across app file/stdout/collector/index/export within permitted scope.
- [ ] An incident response exists for leaked tokens: revoke/rotate and preserve evidence per policy.

**Do not equate "haven't seen a secret" with "tested all sources".** Tomcat access logs, gateways, Java HTTP clients, APMs, and collectors may log differently from the SLF4J application logger.

## 13. Client Input Control and Log Forging Checklist

An attacker may try to inject newlines or control characters into headers, queries, or messages to forge fake lines:

```text
X-Request-ID: req-123\n2026-11-10 ERROR admin granted
```

If a text formatter does not neutralize this data, readers may misinterpret it as two independent records. Standard JSON encoders escape CR/LF inside strings, but log forging can still occur when events are exported to CSV/HTML/terminals.

- [ ] Do not use input strings as field names, logger names, or file paths.
- [ ] IDs/headers are validated, with character and length restrictions.
- [ ] Strings entering JSON properly escape `"`, `\`, CR/LF, tabs, and control chars.
- [ ] In JSONL, one event occupies one physical line, even if the message contains logical newlines.
- [ ] Do not let raw multi-line stack traces break the one-event-per-line contract if the parser requires JSONL.
- [ ] Exported CSV/HTML logs have context-aware protection to prevent formula/HTML injection.
- [ ] Do not print untrusted strings raw to terminals/tickets during investigations.
- [ ] Test malicious and unusually long strings on both success and error paths.

**Structured logging is an enabler, not automatic data safety.** Every field value needs a policy.

## 14. Granularity Checklist: "Enough" Not "Everything"

Example of a **sufficiently useful** checkout event:

```json
{
  "event.name": "checkout.rejected",
  "service.name": "checkout-api",
  "http.route": "/orders/{id}/checkout",
  "http.status_code": 409,
  "duration_ms": 4,
  "error.code": "OUT_OF_STOCK",
  "outcome": "DENIED",
  "request_id": "req_102"
}
```

It is unnecessary to log the full request body, Product/Customer objects, response contents, all HTTP headers, SQL queries with bind values, or stack trace frames for business rejections.

Ask:

- [ ] If a field is removed, can investigations still answer operational questions?
- [ ] If a field is added, does it increase cardinality, volume, or privacy risk?
- [ ] Can the field be obtained from metrics/traces/business queries when needed, instead of copying everything into logs?
- [ ] For lists/arrays, are item counts and nesting depth bounded?
- [ ] For large payloads, can **size/type** be logged instead of contents?
- [ ] For retries, can a summary/aggregation be logged instead of a stack trace every time?
- [ ] Is there a risk of multiple services redundantly logging the same request across hops?

**A "very detailed" record that causes disk-full or leaks secrets is a low-quality record.**

## 15. Structured JSON Checklist: Schema, Parser, Data Types

An example contract:

```json
{"@timestamp":"2026-11-10T03:15:00Z","schema.version":1,"level":"INFO","service.name":"checkout-api","event.name":"checkout.completed","http.status_code":200,"duration_ms":12,"outcome":"SUCCESS","request_id":"req_101"}
```

Some bugs hard to spot by eye:

| Bug | Why is it wrong? | Required assertion |
| --- | --- | --- |
| `"http.status_code":"200"` | Numeric aggregation fails | JSON parser: integer |
| `"duration_ms":"12"` | String type, unit might be wrong | Numeric + range |
| `"success":"true"` | Boolean stringified | Boolean true/false |
| `"trace_id":null` | Unclear if missing or no trace | Nullable/optional contract |
| `"event.name"` renamed | Old alerts/filters stop matching | Contract name/type test |
| Duplicate field | Parsers may pick first/last key differently | Strict duplicate detection when needed |
| One event spans multiple physical lines | JSONL ingestion may reject | 1 JSON object/line |
| Nested/flat shape changed | `http.status_code` differs from nested `http.status_code` | JSON path/shape assertion |

- [ ] Event includes `schema.version` when required by contract.
- [ ] Required fields are present and have the right types, not just `contains("status")`.
- [ ] Optional fields have consistent absent/null semantics.
- [ ] Actual encoder output from Logback/Log4j2/JUL is tested, not just a mock logger.
- [ ] No collisions between MDC, fluent key-value fields, and encoder-generated fields.
- [ ] Encoder/collector updates have consumer contract tests with dashboards/indexes.
- [ ] JSONL UTF-8 and exception serialization have escaping tests.
- [ ] Do not change level/event enums while ignoring schema versioning/migration.

## 16. HTTP Access Log Specific Checklist

HTTP access events should answer where a request went and how it was handled **without leaking raw URLs**.

| Content | Suggestion |
| --- | --- |
| Method | `GET`/`POST` from HTTP instrumentation, validated/normalized |
| Route | Framework matched template `/orders/{id}` or category |
| Status | Integer 100–599 at the appropriate completion point |
| Latency | Milliseconds/seconds with field name indicating unit |
| Request ID | Validated; correlation, not user identity |
| Trace ID | When instrumentation actually has context |
| Source/hop | Clear gateway/server/app boundary to avoid double counting |
| Request/response size | Byte count when purposeful, not body |

- [ ] Do not dump `Authorization`, `Cookie`, `Set-Cookie`.
- [ ] Do not log raw `getRequestURI()` or query strings for endpoints containing tokens/PII.
- [ ] Use route template/class for unmatched endpoints.
- [ ] Distinguish response status at a filter's `finally` block from the final status of async/SSE requests.
- [ ] Container access logs (Tomcat), gateways, and app filters have separate owners.
- [ ] An HTTP 401 event must not be automatically translated to "wrong password" if the auth system has not concluded that.
- [ ] HTTP metrics do not use request ID, token, or raw URL as metric labels.

## 17. Security/Audit Events Checklist

**Security events** typically answer whether authentication/authorization succeeded; **audit events** answer who performed what action on which resource with what outcome. They have different requirements from application DEBUG logs.

An audit event might look like:

```json
{
  "event.name": "role.granted",
  "actor.type": "USER",
  "actor.id": "user_42",
  "target.type": "USER",
  "target.id": "user_91",
  "outcome": "COMMITTED",
  "operation_id": "op_19"
}
```

Checklist:

- [ ] Actor is the **authenticated principal**, not a client-declared username/email.
- [ ] Separate `actor`, `executor/service`, `initiated_by`, and `target` when delegation/jobs are involved.
- [ ] Action/target/outcome come from trusted business state.
- [ ] Matches the transaction commit milestone; `202 Accepted` is not marked completed.
- [ ] Includes event ID/operation ID to reconcile retries/duplicates when needed.
- [ ] Access, retention, legal hold, integrity, and export permissions are defined.
- [ ] Do not log tokens/OTPs/secrets just to "have enough evidence".
- [ ] Mandatory audits do not exist solely in an async debug queue that can discard events.
- [ ] If using an outbox, events may be resent; consumers have an idempotency/dedup policy.
- [ ] When the audit sink fails, business behavior is governed by a clear policy, not silently losing events.
- [ ] Test anonymous, service account, impersonation, and async job cases.
- [ ] Do not fabricate actor/outcome when reconstructing past events.

**A pretty JSON event does not replace audit integrity.** An event can be schema-valid yet have the wrong actor/outcome or vanish before storage.

## 18. Background Jobs, Retries, and Async Checklist

For schedulers, queue workers, or `CompletableFuture`:

- [ ] Log enough `job_id`/`operation_id`/`attempt` to trace workflows across multiple attempts.
- [ ] Distinguish `queued`/`started`/`retry_scheduled`/`completed`/`failed`.
- [ ] Outcome is not marked "completed" immediately upon calling `submit`.
- [ ] Retried requests are not counted as new transactions if business logic uses an idempotency key.
- [ ] Executor identity is the service account; human initiator only when the link is verified.
- [ ] Correlation metadata is passed via safe message headers/DTOs, not carrying tokens to be logged.
- [ ] MDC is snapshotted/restored per worker scope, not leaking across thread pools.
- [ ] Timeout/poison message errors and DLQ have safe event reason codes.
- [ ] Retry counts/lag should have metrics, avoiding error spam on every loop.
- [ ] If the async logger sink is slow, events may wait/drop; the policy must be known.

A `job.accepted` event and a `job.completed` event have **two different timestamps and potentially two different trace contexts**; use `operation_id` for long-lived correlation rather than assuming a single thread-local suffices.

## 19. Event Cardinality, Size, and Performance Checklist

**The "usefulness" of an event also depends on its operational cost.**

- [ ] Event rate/s at INFO/WARN/ERROR is estimated under normal load and bursts.
- [ ] Do not log deep object graphs, binary files, or very large JSON payloads.
- [ ] Do not serialize expensive DTOs when the logger level is disabled.
- [ ] Do not call the logger in tight loops with duplicate content unless truly necessary.
- [ ] Use rate limiting/sampling with statistical impact evaluation, separate from mandatory audits.
- [ ] Fields used for metrics are kept low-cardinality.
- [ ] Message/stacktrace lengths are capped and tested against oversized inputs.
- [ ] Know whether a full `AsyncAppender` queue blocks or discards and how it affects p99.
- [ ] Have metrics for dropped events, sink errors, backlog, and ingest lag.
- [ ] When enabling DEBUG temporarily, have a rollback owner and timebox; privacy rules still apply.

**Do not conclude "async logger is faster so it's always better."** A full queue can block requests or drop logs. Local appender/collector success also does not prove the backend has indexed all data.

## 20. Standalone Java 17: Self-Checking "Checklist-Compliant Log Content"

The following example uses **plain JDK 17** and **java.util.logging (JUL)**, requiring no Maven, SLF4J, or Spring. The goal is not to write a new production JSON encoder, but to build **a rule set for validating event content**:

- Two events `checkout.completed` and `checkout.rejected` are created with a schema allowlist.
- Includes `event.name`, `level`, timestamp, service, trusted route, numeric status/duration, outcome, request ID, and trace ID.
- A fake canary string is present in the request input but **is not included in the event**.
- Success and rejected events have appropriate level/outcome/error code.
- `validate` rejects missing required fields, wrong types, and forbidden fields outside the allowlist.
- `json` is a minimal serializer for String/Integer/Long/Boolean; messages with newlines are escaped.
- Uses a JUL Logger + custom Handler to verify that **the logger actually emitted the events**; stdout only reports fixed PASS lines.

**Note:** This code does not create an HTTP server, write files, send to a collector, or guarantee audit delivery or semantics beyond the mock model. The serializer is for educational purposes only and does not handle all Unicode surrogates/nested JSON; real applications should use a dedicated JSON encoder and test parsing with a library like Jackson.

Create the file **`LogContentChecklistDemo.java`**:

```java
import java.time.Instant;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class LogContentChecklistDemo {
    private static final Set<String> REQUIRED = Set.of(
            "@timestamp", "schema.version", "level", "service.name",
            "event.name", "http.route", "http.status_code",
            "duration_ms", "outcome", "request_id", "trace_id",
            "message");

    private static final Pattern REQUEST_ID =
            Pattern.compile("[A-Za-z0-9_-]{1,64}");
    private static final Pattern TRACE_ID =
            Pattern.compile("[0-9a-f]{32}");

    record Input(
            String requestId,
            String traceId,
            String authorization,
            String requestBody) {}

    private static Map<String, Object> create(
            Input input,
            String eventName,
            int status,
            long elapsedMs,
            String message) {

        boolean completed = "checkout.completed".equals(eventName);
        boolean rejected = "checkout.rejected".equals(eventName);
        if (!completed && !rejected) {
            throw new IllegalArgumentException("Unknown event");
        }

        Map<String, Object> fields = new LinkedHashMap<>();
        fields.put("@timestamp", "2026-11-10T03:15:00Z");
        fields.put("schema.version", 1);
        fields.put("level", completed ? "INFO" : "WARNING");
        fields.put("service.name", "checkout-api");
        fields.put("event.name", eventName);
        fields.put("http.route", "/orders/{id}/checkout");
        fields.put("http.status_code", status);
        fields.put("duration_ms", elapsedMs);
        fields.put("outcome", completed ? "SUCCESS" : "DENIED");
        fields.put("request_id", input.requestId());
        fields.put("trace_id", input.traceId());
        fields.put("message", message);
        if (rejected) {
            fields.put("error.code", "OUT_OF_STOCK");
        }

        // Do not read input.authorization() or input.requestBody().
        validate(fields);
        return fields;
    }

    private static String text(Map<String, Object> fields, String key) {
        Object value = fields.get(key);
        if (!(value instanceof String s) || s.isBlank()) {
            throw new IllegalArgumentException("Bad string field: " + key);
        }
        return s;
    }

    private static void validate(Map<String, Object> fields) {
        Set<String> allowed = new HashSet<>(REQUIRED);
        if (fields.containsKey("error.code")) {
            allowed.add("error.code");
        }
        if (!fields.keySet().equals(allowed)) {
            throw new IllegalArgumentException("Bad set of fields");
        }

        Instant.parse(text(fields, "@timestamp"));
        if (!(fields.get("schema.version") instanceof Integer version)
                || version != 1) {
            throw new IllegalArgumentException("Bad schema version");
        }
        if (!"checkout-api".equals(text(fields, "service.name"))) {
            throw new IllegalArgumentException("Bad service");
        }
        if (!"/orders/{id}/checkout".equals(
                text(fields, "http.route"))) {
            throw new IllegalArgumentException("Bad route");
        }
        if (!REQUEST_ID.matcher(
                text(fields, "request_id")).matches()) {
            throw new IllegalArgumentException("Bad request ID");
        }
        if (!TRACE_ID.matcher(
                text(fields, "trace_id")).matches()) {
            throw new IllegalArgumentException("Bad trace ID");
        }
        if (!(fields.get("http.status_code") instanceof Integer status)
                || !(fields.get("duration_ms") instanceof Long duration)
                || duration < 0L) {
            throw new IllegalArgumentException("Bad numeric fields");
        }
        if (text(fields, "message").length() > 120) {
            throw new IllegalArgumentException("Message too long");
        }

        String event = text(fields, "event.name");
        String level = text(fields, "level");
        String outcome = text(fields, "outcome");
        if ("checkout.completed".equals(event)) {
            if (status != 200 || !"INFO".equals(level)
                    || !"SUCCESS".equals(outcome)
                    || fields.containsKey("error.code")) {
                throw new IllegalArgumentException("Bad completion");
            }
        } else if ("checkout.rejected".equals(event)) {
            if (status != 409 || !"WARNING".equals(level)
                    || !"DENIED".equals(outcome)
                    || !"OUT_OF_STOCK".equals(
                            text(fields, "error.code"))) {
                throw new IllegalArgumentException("Bad rejection");
            }
        } else {
            throw new IllegalArgumentException("Unknown event");
        }
    }

    private static String quote(String value) {
        StringBuilder out = new StringBuilder("\"");
        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);
            switch (c) {
                case '"' -> out.append("\\\"");
                case '\\' -> out.append("\\\\");
                case '\n' -> out.append("\\n");
                case '\r' -> out.append("\\r");
                case '\t' -> out.append("\\t");
                default -> {
                    if (c < 0x20) {
                        String hex = Integer.toHexString(c);
                        out.append("\\u")
                                .append("0".repeat(4 - hex.length()))
                                .append(hex);
                    } else {
                        out.append(c);
                    }
                }
            }
        }
        return out.append('"').toString();
    }

    private static String json(Map<String, Object> fields) {
        validate(fields);
        StringBuilder out = new StringBuilder("{");
        boolean first = true;
        for (Map.Entry<String, Object> field : fields.entrySet()) {
            if (!first) {
                out.append(',');
            }
            first = false;
            out.append(quote(field.getKey())).append(':');
            Object v = field.getValue();
            if (v instanceof String s) {
                out.append(quote(s));
            } else if (v instanceof Integer || v instanceof Long
                    || v instanceof Boolean) {
                out.append(v);
            } else {
                throw new IllegalArgumentException("Unsupported type");
            }
        }
        return out.append('}').toString();
    }

    private static void check(boolean condition, String label) {
        if (!condition) {
            throw new AssertionError(label);
        }
    }

    private static void expectInvalid(Map<String, Object> event) {
        try {
            validate(event);
            throw new AssertionError("Invalid event accepted");
        } catch (IllegalArgumentException expected) {
            // Invalid conditions must be rejected.
        }
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.content.checklist");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        List<String> captured = new ArrayList<>();
        Handler handler = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (isLoggable(record)) {
                    captured.add(record.getMessage());
                }
            }
            @Override public void flush() {}
            @Override public void close() {}
        };
        handler.setLevel(Level.ALL);
        logger.addHandler(handler);

        String canary = "FAKE_SECRET_CANARY_508";
        Input first = new Input(
                "req_101", "4bf92f3577b34da6a3ce929d0e0e4736",
                "Bearer " + canary, "password=" + canary);
        Input second = new Input(
                "req_102", "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "Bearer " + canary, "card=" + canary);

        try {
            Map<String, Object> good = create(
                    first, "checkout.completed", 200, 12L,
                    "Checkout\ncompleted");
            Map<String, Object> rejected = create(
                    second, "checkout.rejected", 409, 4L,
                    "Inventory rejected checkout");

            logger.log(Level.INFO, json(good));
            logger.log(Level.WARNING, json(rejected));

            check(captured.size() == 2, "Wrong event count");
            check(good.get("http.status_code") instanceof Integer,
                    "Status must be integer");
            check(good.get("duration_ms") instanceof Long,
                    "Duration must be long");
            check(good.get("outcome").equals("SUCCESS"),
                    "Incorrect outcome");
            System.out.println("PASS 1: event schema and meaning");

            String line = captured.get(0);
            check(line.contains("\"http.status_code\":200"),
                    "Numeric JSON missing");
            check(line.contains("\"message\":\"Checkout\\ncompleted\""),
                    "Newline escape missing");
            check(line.indexOf('\n') < 0 && line.indexOf('\r') < 0,
                    "JSONL physical newline found");
            System.out.println("PASS 2: JSONL values and escaping");

            Map<String, Object> missing = new LinkedHashMap<>(good);
            missing.remove("request_id");
            expectInvalid(missing);

            Map<String, Object> wrongType = new LinkedHashMap<>(good);
            wrongType.put("http.status_code", "200");
            expectInvalid(wrongType);

            Map<String, Object> extra = new LinkedHashMap<>(good);
            extra.put("authorization", first.authorization());
            expectInvalid(extra);
            System.out.println("PASS 3: missing, type and extra fields");

            check(!captured.get(0).contains(canary)
                    && !captured.get(1).contains(canary),
                    "Secret canary leaked");
            check(captured.get(0).contains("\"request_id\":\"req_101\"")
                    && !captured.get(0).contains("req_102"),
                    "First ID wrong");
            check(captured.get(1).contains("\"request_id\":\"req_102\"")
                    && !captured.get(1).contains("req_101"),
                    "Second ID wrong");
            System.out.println("PASS 4: privacy and correlation");
            System.out.println("ALL CONTENT CHECKS PASSED");
        } finally {
            logger.removeHandler(handler);
            handler.close();
        }
    }
}
```

Compile and run:

```bash
javac --release 17 LogContentChecklistDemo.java
java LogContentChecklistDemo
```

**Exact stdout if all assertions succeed:**

```text
PASS 1: event schema and meaning
PASS 2: JSONL values and escaping
PASS 3: missing, type and extra fields
PASS 4: privacy and correlation
ALL CONTENT CHECKS PASSED
```

**Explanation of results:**

- The first event carries status `200`, INFO, `SUCCESS`, and `Long` duration; the second carries status `409`, JUL `WARNING`, `DENIED`, and `OUT_OF_STOCK`.
- A real `Logger` has a capture handler, so the example verifies that two events passed level filtering in JUL; it does not prove a centralized backend received them.
- Inputs contain a token and body with `FAKE_SECRET_CANARY_508`, but the builder does not read them to write the event.
- Missing required fields, wrong types, and fields outside the allowlist are tested as cases that **must fail validation**.
- Newlines in `message` are escaped to `\n` in JSON, without creating extra physical lines in JSONL.
- The two request IDs are distinct and logs do not mix IDs. **This does not replace concurrent MDC/ThreadLocal isolation tests** during web/async integration.
- The serializer handles only a finite set of types and **is not a general-purpose production JSON serializer**; integration tests must use the actual encoder and a JSON parser like Jackson.
- The timestamp is fixed for deterministic test results, not how timestamps are generated in a real runtime environment.
- The `rejected` event represents a **business rejection**, not a security authorization denial.

## 21. SLF4J, Logback, Log4j2, and JUL Integration Checklist

The Java 17 example above simulates log content using JUL; when moving to production libraries, you must test **effective output**:

| Layer | Verification Questions |
| --- | --- |
| SLF4J facade | Are logger name, level, and key-value pairs correct? |
| Logback | Does appender/encoder serialize MDC/fields? Any duplicated keys? |
| Log4j2 | Do JSON Template Layout and configuration produce the desired shape? |
| JUL | Do both Logger level and Handler level/filter allow the event? |
| Spring Boot | Is structured format compatible with the version; does custom config override it? |
| HTTP server | Do Tomcat/Jetty access logs have an independent source? |
| Collector | Does the parser preserve numeric/boolean types and route to the right index? |
| Backend | Do queries by event/trace ID work accurately; are retention and access control valid? |

SLF4J 2.x has a **fluent logging API**:

```java
// Integration snippet: requires SLF4J 2.x and a compatible logger/backend.
logger.atInfo()
      .addKeyValue("event.name", "checkout.completed")
      .addKeyValue("http.status_code", 200)
      .addKeyValue("duration_ms", 12L)
      .addKeyValue("outcome", "SUCCESS")
      .log("Checkout completed");
```

**Do not assume** `addKeyValue` automatically turns into top-level JSON fields like in the demo: the backend/layout might only print `key=value` text, nest them under another object, or fail to preserve types. For acceptance, capture the **actual emitted line**, parse it with Jackson, and verify the contract.

When using Logback's `ListAppender`, it helps inspect events before the encoder. To verify JSON fields, you must capture after the **actual encoder**. For async loggers, wait for draining via an appropriate synchronization/lifecycle mechanism before asserting, rather than sleeping for a fixed duration and hoping.

## 22. Spring MVC / WebFlux Application Checklist

For HTTP services:

- [ ] There is a defined boundary where access events are emitted after request processing.
- [ ] If using a Servlet filter, know when `HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE` is available.
- [ ] Requests rejected by the security layer before MVC may lack a matched route; use a safe generic fallback.
- [ ] Do not confuse `OncePerRequestFilter` with WebFlux's `WebFilter`.
- [ ] Async dispatch/SSE/streaming need completion callbacks when final status/duration are required.
- [ ] Do not log bodies via `CommonsRequestLoggingFilter`/default framework debug on login/token/payment routes.
- [ ] Proxies/gateways/Tomcat access logs may output raw paths/queries even if the app logger filters them.
- [ ] MDC/trace propagation across `@Async`, thread pools, and HTTP clients is configured and tested.
- [ ] Do not assign actor from an unverified `X-User-ID` header.
- [ ] Correct request ID/trace ID is present in events at necessary search points.
- [ ] Alerting relies on stable event codes/levels/outcomes, not regexes on free-form message text.

**Do not drop important access/security events just to block payloads.** Safe metadata can be logged without reading the raw request.

## 23. Content Unit Tests Checklist

| Test | PASS when |
| --- | --- |
| Event name | Name belongs to catalog, not dynamic |
| Required fields | All fields for the event class are present |
| Wrong type | `"200"` is rejected when an integer is expected |
| Invalid duration | Negative values or wrong units are caught |
| Timestamp | Parseable ISO-8601 UTC/offset |
| Missing context | Policy for absence exists, no fake trace fabricated |
| Wrong actor/tenant | Unauthenticated IDs are not accepted |
| Unexpected field | Entire DTO is not auto-serialized |
| Sensitive canary | Does not appear in any field/message |
| Outcome timing | Uncommitted does not log COMMITTED |
| Retry | Attempt and operation ID do not collide |
| Exception | Safe code, no secrets logged from Throwable |
| Oversized input | Bounded/not dumped |
| Control chars | JSONL properly escaped, no log forging |
| Disabled DEBUG | Expensive formatter not invoked unnecessarily |

**Testing note:** a single `assertFalse(log.contains(secret))` on **one** line is not enough to prove other sources are safe; however, it is a useful and fast unit/regression test. Combine it with schema/field selection checks and end-to-end pipeline verification.

## 24. Integration Tests Checklist for Actual Output

- [ ] Capture output from the actual encoder/layout in use, not just a mocked logger API.
- [ ] Parse each JSON line with an independent parser like Jackson; verify object shape.
- [ ] Check `isIntegralNumber()` before `asInt()`/`intValue()` to prevent type coercion from masking bugs.
- [ ] Verify required/optional fields and numeric/boolean/enum/unit values.
- [ ] Verify escaping of quotes/backslashes/CRLF/Unicode and one event per line.
- [ ] Verify events have no duplicate keys or collisions with default fields.
- [ ] Verify INFO/WARN/ERROR are filtered or routed to the right appender per real configuration.
- [ ] Verify MDC from request A/B does not leak when thread pools reuse threads.
- [ ] Verify output when exception/stack trace messages contain a canary.
- [ ] Verify async queue drains properly before asserting event counts and drop policies.
- [ ] If files roll, test rollover/retention in a test directory, not production.
- [ ] If the backend parses nested fields, assertions use the exact JSON path/schema.
- [ ] Re-run contract tests when upgrading encoders/frameworks.

**JUnit 5 + Jackson snippet** example to verify an actual JSON line from a test fixture:

```java
// line must come from a fixture produced by the actual encoder, not reconstructed with a mock.
com.fasterxml.jackson.databind.JsonNode root =
        new com.fasterxml.jackson.databind.ObjectMapper().readTree(line);

org.junit.jupiter.api.Assertions.assertTrue(root.isObject());
org.junit.jupiter.api.Assertions.assertEquals(
        "checkout.completed", root.path("event.name").asText());
org.junit.jupiter.api.Assertions.assertTrue(
        root.path("http.status_code").isIntegralNumber());
org.junit.jupiter.api.Assertions.assertEquals(
        200, root.path("http.status_code").intValue());
org.junit.jupiter.api.Assertions.assertTrue(
        root.path("duration_ms").isIntegralNumber());
org.junit.jupiter.api.Assertions.assertFalse(
        line.contains("FAKE_SECRET_CANARY_508"));
```

This snippet **does not compile standalone** because it depends on `line`, JUnit 5, and Jackson. It illustrates the difference between a **schema test** and simple string searching.

## 25. E2E Checklist: Logs Reach the Right Place and Remain Searchable

From a system perspective:

1. [ ] Log is present at source stdout/file with a test event ID **containing no secrets**.
2. [ ] Collector receives all test events per measurable semantics; queues/retries have metrics.
3. [ ] Parser preserves types, field names, JSON shape, and timestamps.
4. [ ] Backend indexes environment/service/tenant accurately.
5. [ ] Queries by event name/ID/trace ID return accurate data within SLO.
6. [ ] Duplicate/replay/drop behavior during collector retries is evaluated.
7. [ ] Dashboards and alerts do not depend on volatile message text.
8. [ ] Retention across file/node/backend/archive tiers is clearly documented.
9. [ ] Exports/snapshots/backups have appropriate permissions and data lifecycle policies.
10. [ ] Alerts exist for rising log ingestion lag or sink errors.
11. [ ] Security/audit events have dedicated durability requirements.
12. [ ] A runbook exists if dashboards are empty while the source is still writing.

**Do not use an empty query result as proof that an event was lost.** Check timezone, time window, permissions, index alias, ingestion lag, and parser before classifying it as lost.

## 26. Common Log Content Mistakes and Fixes

| Anti-pattern | Consequence | Fix |
| --- | --- | --- |
| `logger.info("Done")` | Unclear what finished | `event.name` + status/outcome |
| Logging SUCCESS before commit | False audit trail | Emit after outcome confirmation point |
| All HTTP 4xx as ERROR | Alert fatigue | Level by impact and event class |
| Full request/body in message | Leaks tokens/PII, high volume | Allowlisted fields |
| Raw URL with reset token | Secret in path/query | Trusted route template/class |
| `duration_ms` storing nanoseconds | Measurement off by a millionx | Unit conversion and tests |
| `http.status_code` as string | Histograms/aggregations break | JSON number contract |
| Missing request ID | Cannot locate related requests | Valid ID at edge and propagation |
| Using trace ID as user ID | Wrong security attribution | Verified principal |
| `MDC.put` without restore | Tenant/request leaks across threads | Scope + finally |
| Throwables with raw HTTP response | PII leaked via stack trace | Safe codes and exception policy |
| Logging same exception at 4 layers | Wastes storage, duplicate alerts | Clear boundary ownership |
| Async queue silently drops INFO | Loss of diagnostic capability | Metrics/policy and proper sink |
| Testing only with mock logger | Misses JSON type drift | Test actual encoder/collector |
| Changing event codes arbitrarily | Breaks dashboards/filters | Catalog + schema version |
| Eager DEBUG formatting | Wastes CPU/alloc when level off | Appropriate guard/supplier |
| Using dynamic event names | High cardinality | Event enum + ID in separate field |
| Frequent business errors at WARN | On-call noise | Proper severity policy |
| Unbounded log sizes | Disk full, collector lag | Bounded data, rolling/retention |
| Dumping everything on log loss | Worsens outage and leaks secrets | Triage per pipeline stage |

## 27. Quality Scorecard Applicable to Code Review

A **suggested scorecard** can be used for each event:

| Criterion | Suggested Points |
| --- | ---: |
| Event is necessary and purposeful | 10 |
| Correct event code + timing/outcome | 20 |
| Appropriate severity | 10 |
| Schema field names/types/units | 15 |
| Context and trusted identity | 15 |
| Privacy/security policy | 20 |
| Testability and operations | 10 |
| **Total** | **100** |

**Do not use a total score to overlook dangerous flaws.** If a log contains a password/token, wrong actor, or a COMMITTED event before transaction commit, it is a **mandatory FAIL**, even if all other items are good.

A simpler approach for reviews:

- **Blocker:** secret leak, wrong actor/outcome, log forging, mandatory audit could be lost without policy.
- **Major:** missing correlation, wrong event/schema/type/units, ERROR spam, missing error classification.
- **Minor:** unclear message, missing optional field when other investigation paths exist, inconsistent style.

Score thresholds and classifications are only **team process templates**, not mandatory legal or technical standards.

## 28. Pull Request Checklist Template

You can copy the template below for a PR changing logging. Reviewers should attach **test evidence** for each item rather than just ticking boxes.

```markdown
### Logging content review

- [ ] This event has a clear troubleshooting/security/audit purpose.
- [ ] Event name belongs to the catalog and matches the business milestone.
- [ ] Level reflects impact without creating ERROR/WARN spam.
- [ ] Outcome, HTTP status, error code, and commit timing are accurate.
- [ ] Required structured fields are complete, with correct types and units.
- [ ] Request/trace/operation IDs are trusted, with no context mixing.
- [ ] Actor/tenant come from verified security context if applicable.
- [ ] No tokens, passwords, OTPs, cookies, cards, or raw body/query logged.
- [ ] Messages/exceptions are sanitized and length-bounded.
- [ ] JSONL escaping is correct and free of log forging.
- [ ] Actual encoder output is tested (type/shape/escape).
- [ ] Fake canary and at least one negative case are tested.
- [ ] Async queue/sink/collector/retention have an owner and policy.
- [ ] Dashboard/alert consumers remain compatible after schema changes.

Evidence:
- Test commands and results:
- Log event sample (sanitized):
- Schema version:
- Event owner:
- Known limitations / operational follow-up:
```

The `Evidence` fields in the PR template are **a template for learners to fill in during real reviews**, not TODO markers in this lesson or tested system data.

## 29. Pre-Release Checklist

- [ ] Service event catalog exists, with owners and schema versions.
- [ ] INFO/WARN/ERROR events have clear purposes without excessive duplication.
- [ ] UTC timestamps, numeric statuses, durations with units, and outcomes are consistent.
- [ ] Structured JSONL is parsed from the real encoder/backend, not just strings built in unit tests.
- [ ] Correlation IDs are validated/propagated without leaking across requests or tenants.
- [ ] Async job events do not claim completed before completion.
- [ ] Security/audit events use trusted actor/outcome and are preserved per policy.
- [ ] No raw secrets, bodies, headers, queries, or URLs containing tokens.
- [ ] Exceptions and HTTP client logs have passed privacy tests.
- [ ] Tests cover canaries/CRLF/Unicode/oversized payloads and failure paths.
- [ ] No field name/type drift breaking dashboards or alerts.
- [ ] Event/log volume fits capacity, and AsyncAppender overflow policy is known.
- [ ] File/stdout/collector/backend have owner-defined rotation/retention/queue health.
- [ ] Temporary DEBUG in production has scope/expiry/rollback.
- [ ] On-call engineers can look up logs by event name + request/trace/operation ID.
- [ ] Runbook distinguishes filtered, delayed, dropped, and unindexed logs.
- [ ] Test PASS/FAIL reports and unverified limitations are documented honestly.

**Remember:** a good checklist does not ask "did we call `logger.info`?"—it asks **"is this event necessary, at the right time, at the right severity, with the right fields and data types, with enough correlation, free of secrets, and verifiable end-to-end?"** A log line is only valuable when operators can **trust its meaning** without paying the price of security risks or production instability.

### References

- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [MITRE — CWE-117: Improper Output Neutralization for Logs](https://cwe.mitre.org/data/definitions/117.html)
- [SLF4J — User Manual and Fluent Logging API](https://www.slf4j.org/manual.html)
- [Logback — Manual: Appenders](https://logback.qos.ch/manual/appenders.html)
- [Logback — Manual: Mapped Diagnostic Context](https://logback.qos.ch/manual/mdc.html)
- [Apache Log4j — JSON Template Layout](https://logging.apache.org/log4j/2.x/manual/json-template-layout.html)
- [OpenTelemetry — Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/)
- [Java 17 — java.util.logging.Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html)
- [JUnit 5 — User Guide](https://junit.org/junit5/docs/current/user-guide/)
