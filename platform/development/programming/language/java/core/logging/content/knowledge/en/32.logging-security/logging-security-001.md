# Threat Model for Logging in Java

## 1. What is a logging threat model?

A logging **threat model** is a model that identifies **assets to protect**, **log data and flow**, **trust boundaries**, **adversaries**, **attack scenarios**, **defensive controls**, and **testing methods**. Logging is both a security incident detection tool and an attack surface: it can leak tokens, store forged information, be deleted or altered to cover tracks, or become a cause of application unavailability.

Two questions must be answered in parallel:

1. **How does logging aid defense?** Are failed login attempts, authorization violations, administrative privilege changes, sensitive data access, anomalies, and configuration changes recorded sufficiently for investigation?
2. **How can the logging system itself be attacked?** Can a client forge log lines via input, can an appender write secrets, do viewers have overly broad permissions, can a collector misidentify the source, or can the queue be congested?

For example: an API writes a client-controlled `User-Agent` header directly into a text file. An attacker injects a newline character followed by a string resembling an `ERROR` record, misleading investigators about the timeline. In another scenario, HTTP error logs record the raw `Authorization` header, exposing a valid token in an observability store readable by dozens of people.

**Do not equate "having logs" with "having trustworthy evidence."** Investigative value also depends on the data source, identity verification, timestamps, completeness, integrity, and access control over the data after it is written.

## 2. Assets and security objectives

| Asset | Security Property | Impact When Compromised |
| --- | --- | --- |
| Data in logs | **Confidentiality** | Exposure of PII, tokens, passwords, payment data, internal paths |
| Individual log events | **Integrity** | Forged log lines, altered outcome or actor |
| Security/audit events | **Completeness / Accountability** | Missing critical events, inability to determine whether an action occurred |
| Timeline | Clear timestamp and source | Wrong conclusions about incident order and root cause |
| Logging pipeline | **Availability** | Dropped logs; full disk; blocked requests |
| Logging configuration | Modifiable only by authorized principals | Disabling security logs or redirecting data to unauthorized destinations |
| Log store and exports | Access control, retention | Bulk reading/downloading of data, history deletion, or distribution of copies |

**Distinguish three types of logs:**

- **Application/diagnostic logs:** operational/debugging, often tolerating some loss of detail under overload according to policy.
- **Security event logs:** record authentication, authorization, sensitive operations, errors, and suspicious behavior for monitoring.
- **Audit trail:** if required as evidence or for reconciliation, may require durable storage, separation of duties, integrity guarantees, and stricter retention.

Naming a file `audit.log` does **not** automatically make it a tamper-resistant audit store. If legal or business requirements apply, dedicated recording and storage policies must be designed.

## 3. Threat actors and control capabilities

Before assessing risk, describe what an attacker *actually has the ability to do*:

| Actor | Can Control | Must Not Be Trusted by Default |
| --- | --- | --- |
| Unauthenticated client | URL/path, query, body, headers, request rate | Client-declared `X-User-ID`, `X-Forwarded-For`, `traceparent` |
| Malicious authenticated user | Business content, repeated actions, some display names/labels | `toString()`, filenames, user-supplied error strings |
| Compromised dependent service | Response/error messages, metadata, emitted events | HTTP errors or exceptions containing external strings |
| Compromised service account | Sending data under the service's identity within its permission scope | Tenant, index, and source name inside the payload |
| Over-privileged operator | Changing level, sink, retention, exporting, or deleting logs | Independence of the audit trail without separation of duties |
| Faulty collector or plugin | Parser, enrichment, transport, indexing, and rendering | Data after it leaves the application process |

You must also threat-model **unintentional failures**: misconfiguration, clock drift, crashes, network partitions, full queues, exhausted disk, buggy log-cleanup scripts, or accidental export of sensitive records. The confidentiality, integrity, and availability impact can be identical to an active attack.

## 4. Log flow diagram and trust boundaries

```text
    [Internet / Client]           [Dependency / SDK]
         │  untrusted data               │
         ▼                               ▼
   [HTTP Server/Gateway] ──────► [Java Application]
         │                              │
         │ access event                 │ application/security event
         │                              ▼
         │                      [Logger + MDC/trace]
         │                              │
         │                      [Filter + Encoder]
         │                              │
         └────────────┐                 ▼
                      └────────► [Async Queue/Appender]
                                            │
                                            ▼
                                     [stdout/File/Socket]
                                            │
                                            ▼
                                   [Collector / Agent]
                                            │
                                  TLS/Auth/Validation
                                            ▼
                                    [Central Log Store]
                                            │
                               ┌────────────┴────────────┐
                               ▼                         ▼
                         [Search/Dashboard]       [Export/Backup]
                               │                         │
                            Operators             Other systems
```

Examine each boundary carefully:

1. **Internet → Server:** request ID, IP, URL, user-agent, and headers may be untrusted; trusted proxies must also be explicitly configured.
2. **Application data → Log event:** body, exceptions, MDC, object `toString()`, and messages from dependencies may contain secrets, PII, or format-breaking strings.
3. **Logger → Queue/Appender:** levels/filters can drop events; in-memory queues, backpressure, retries, and shutdown affect data preservation.
4. **Process → Collector:** file/stdout read permissions, network transport, sender identity, handoff, and buffering belong to a different trust zone.
5. **Collector → Store:** parsers, enrichment, relabeling, multi-tenant routing, and indexing can modify, drop, or duplicate events.
6. **Store → Dashboard/Export:** search APIs, viewers, CSVs, notebooks, and backups expand the exposure surface.
7. **Control plane → Logging config:** any permission to change levels, filters, masking, destinations, and retention is also permission to alter evidence.

For each boundary, document: **who controls the data**, protocol and format, authentication mechanism, where data is buffered, read/write permissions, and how failures are detected.

## 5. STRIDE for logging systems

STRIDE is a threat classification framework; it is not a built-in configuration checklist for Logback or Log4j2.

| Category | Logging Scenario | Impact | Controls and Verification |
| --- | --- | --- | --- |
| **Spoofing** | Client sets `X-User-ID: admin` or spoofs IP, and the app logs it as the authenticated actor | Misattributed actions | Extract actor from verified security principal; trust only configured proxies; test with spoofed headers |
| **Tampering** | CRLF injects fake lines, operator edits files, collector alters fields | Distorted evidence | Structured encoding, sanitization, RBAC, append-only/tamper detection |
| **Repudiation** | Role changes are not logged or audit logs are easily deleted | Actions cannot be reconciled | Event schema, reconciliation, separation of duties, retention, and durable storage |
| **Information Disclosure** | Logging request headers, JWTs, PII, stack traces, then exporting broadly | Account takeover, privacy breach | Field allowlist, never log secrets at the source, encryption, and least privilege |
| **Denial of Service** | Error spamming fills queue/disk, expensive exception formatting | Slow requests, lost logs, service outage | Bounded queue, rate/size limits, quotas, metrics, and overload policy |
| **Elevation of Privilege** | Vulnerable viewer/parser, overly broad logging admin permissions | Compromise or disabling of controls | Patch dependencies, isolate parsers, separate config/read/delete permissions |

**Note:** a single scenario can span multiple categories. For example, log forging both undermines integrity and enables repudiation. Do not assign the highest severity to every case; prioritize based on data scope, attacker capabilities, exploitability, and real-world impact.

## 6. Log injection and log forging (CWE-117)

### Scenario

Unsafe code in an application with backend logging:

```java
// UNSAFE ILLUSTRATION: do not use this pattern for untrusted data.
logger.warn("Login failed: user=" + username);
```

Suppose the client supplies a `username` value containing:

```text
guest
ERROR user=admin event=login_success
```

If the application writes the raw value into a line-oriented text log, one real event can look like two events. The second line was planted by the attacker, not verified by the application. This is an example of **Improper Output Neutralization for Logs (CWE-117)**.

Variants also include delimiters in `key=value`, hand-concatenated unescaped JSON, terminal control characters, Unicode line separators, or oversized payloads that overwhelm parsers/collectors.

### Defenses in order of priority

1. **Define a fixed schema:** `event.name`, `actor.id`, `outcome`, `http.route` are meaningful fields; event names and route templates are determined by the server.
2. **Validate type/length/value:** request IDs match an expected format, actions and reasons belong to valid code sets; never use raw input as a logger name, level, filename, or index.
3. **Use structured logging** through a proper encoder: for example, JSON with per-value escaping, never manual JSON string concatenation.
4. **Neutralize CR/LF and control characters** for text logs; handle additional special characters appropriate to the target format and enforce an event-size limit.
5. **Use static message templates and parameterized logging**, such as `logger.warn("Login failed for {}", safeUser)`. However, **placeholders do not automatically prevent CRLF** if the layout still prints the raw string.
6. **Protect downstream pipelines:** parsers, HTML dashboards, CSV exports, and queries must also escape according to their own context.

A valid JSON event does not guarantee safety if a dashboard renders values into unescaped HTML. Conversely, merely replacing `\n` with the two-character backslash-n sequence does not solve secrets, delimiters, or oversized data.

## 7. Avoiding exposure of tokens, PII, and secrets

**Common sources of risk:**

- `Authorization`, `Cookie`, `Set-Cookie`, session IDs, access tokens, refresh tokens, API keys.
- Query parameters containing `code`, `token`, `password`, or sensitive identifiers.
- Request/response bodies for login, payments, healthcare, or personal profiles.
- `toString()` of DTOs, records, or exceptions containing secret fields.
- Database connection strings, URLs with credentials, environment variables, secret manager contents.
- Stack traces and errors from SDKs/HTTP clients containing headers, payloads, or internal paths.
- MDC, tracing baggage, or context automatically attached to every event.

Example of what not to do:

```java
// UNSAFE ILLUSTRATION.
logger.error("Request headers={} body={}", requestHeaders, requestBody);
```

Instead, emit a **security event using an allowlist** of fields needed for investigation, for example:

```text
event=authentication_failed
route=/login
request_id=req_42
outcome=DENY
reason=BAD_CREDENTIALS
duration_ms=23
```

You do not need a full name, password, or token to know that a login request failed. If an actor ID or IP must be stored, ensure a valid processing purpose, access control, retention, and avoid inferring the actor from client headers.

**Place defenses early:** stripping sensitive fields before creating the event is better than scrubbing after the event has passed through stdout/files. Collector scrubbers and dashboard masking are only supplementary layers. Regex-based token masking can miss new formats, nested JSON, or split values. Hashing IDs does not automatically eliminate re-identification risk, especially if the value space is small and easy to reverse-lookup.

## 8. Java 17 example: allowlist logging and newline neutralization

The following standalone example uses **`java.util.logging` (JUL)** built into the JDK. Its goal is to demonstrate three controls:

- Meaningful event types, routes, and reason codes are decided by the **application**.
- Request IDs are accepted only if they match a format allowlist.
- An untrusted input must be escaped and bounded if it genuinely needs to be displayed in a single text line.

**This is an educational example**, not a production security logging library. The escape function only handles control characters for a **text line**; it does not replace JSON/CSV/HTML escaping, does not detect tokens/PII, and does not guarantee durability.

Save as **`LoggingThreatModelDemo.java`**:

```java
import java.util.Set;
import java.util.regex.Pattern;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class LoggingThreatModelDemo {
    private static final Pattern SAFE_ID =
            Pattern.compile("[A-Za-z0-9_-]{1,64}");
    private static final Set<String> REASONS =
            Set.of("BAD_CREDENTIALS", "ACCOUNT_LOCKED");
    private static final Logger LOG =
            Logger.getLogger("security.events");

    private static final class StdoutHandler extends Handler {
        StdoutHandler() {
            setLevel(Level.ALL);
        }

        @Override
        public void publish(LogRecord event) {
            if (isLoggable(event)) {
                System.out.println(event.getLevel().getName()
                        + " " + event.getMessage());
            }
        }

        @Override
        public void flush() {
            System.out.flush();
        }

        @Override
        public void close() {
            flush();
        }
    }

    private static String checkedId(String raw) {
        return raw != null && SAFE_ID.matcher(raw).matches()
                ? raw : "invalid";
    }

    private static String checkedReason(String raw) {
        return raw != null && REASONS.contains(raw)
                ? raw : "UNTRUSTED";
    }

    private static String escapeLine(String raw, int maxChars) {
        if (raw == null) {
            return "-";
        }
        StringBuilder out = new StringBuilder();
        for (int i = 0; i < raw.length();) {
            int cp = raw.codePointAt(i);
            i += Character.charCount(cp);

            String safe;
            if (cp == '\r') {
                safe = "\\r";
            } else if (cp == '\n') {
                safe = "\\n";
            } else if (cp == '\t') {
                safe = "\\t";
            } else if (Character.isISOControl(cp)
                    || cp == 0x2028 || cp == 0x2029
                    || (cp >= 0xD800 && cp <= 0xDFFF)) {
                safe = "?";
            } else {
                safe = new String(Character.toChars(cp));
            }

            if (out.length() + safe.length() > maxChars) {
                break;
            }
            out.append(safe);
        }
        return out.toString();
    }

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);
        StdoutHandler handler = new StdoutHandler();
        LOG.addHandler(handler);

        try {
            String requestId = checkedId("req_42");
            String reason = checkedReason("BAD_CREDENTIALS");

            LOG.warning("event=authentication_failed"
                    + " route=/login"
                    + " request_id=" + requestId
                    + " reason=" + reason);

            LOG.info("event=http_response"
                    + " route=/login status=401"
                    + " request_id=" + requestId);

            String untrusted = "guest\nERROR event=login_success";
            System.out.println("escaped_input="
                    + escapeLine(untrusted, 80));
            System.out.println("invalid_request_id="
                    + checkedId("bad\nid"));
        } finally {
            LOG.removeHandler(handler);
            handler.close();
        }
    }
}
```

Compile and run with JDK 17+:

```bash
javac --release 17 LoggingThreatModelDemo.java
java LoggingThreatModelDemo
```

**Exact stdout:**

```text
WARNING event=authentication_failed route=/login request_id=req_42 reason=BAD_CREDENTIALS
INFO event=http_response route=/login status=401 request_id=req_42
escaped_input=guest\nERROR event=login_success
invalid_request_id=invalid
```

Explanation:

- Two real events are created via `LOG.warning` and `LOG.info`, with the event type, route, and reason fields controlled by the application.
- `checkedId` rejects request IDs containing newline characters, avoiding passing an unvalidated header string directly as a correlation ID.
- `escapeLine` iterates by Unicode code point, replaces CR/LF with safe representations, handles control characters, and enforces a length limit. In stdout, `\n` in `escaped_input` is **two literal characters** (backslash and `n`), not an actual newline.
- The handler runs synchronously and disables parent handlers, so no timestamp lines or duplicate records are emitted by JUL's default handler.
- `escapeLine` only illustrates neutralization; for `key=value` strings you must also consider delimiters such as spaces/`=` and parser-specific encoding. It is best to use a structured JSON encoder rather than building entire records via string concatenation.
- When input contains secrets or PII, **do not log it**, even if CR/LF has been escaped. Escaped data can still be sensitive data.
- Do not use this program in place of production frameworks: it does not handle queues, file rotation, durable storage, TLS, multi-tenant access control, or guaranteed audit events.

## 9. Integrity, provenance, and audit trail

Integrity has different levels:

1. **Accurate event content:** outcomes come from verified logic; actors come from the security principal, not a user ID in the request.
2. **No forged lines at write time:** schemas, encoding, and neutralization prevent a single input from creating fake lines.
3. **No modification/deletion after write:** filesystem/index permissions, administrative separation, append-only storage, or tamper-detection mechanisms.
4. **No modification in transit:** channel protection and source authentication, especially for multi-tenant collectors.
5. **Detecting missing events:** event IDs/sequences, ingestion metrics, heartbeats, and reconciliation mechanisms.

Options when audit trails require high assurance:

- Store a copy in a system with a **different privilege domain** so an application operator cannot alter all evidence.
- Use **immutable/WORM retention** or append-only storage where appropriate and configure separate administrative permissions.
- Use hash chains/MACs/signatures on events or batches with canonical serialization and independent key management. A standalone checksum can be recomputed by anyone with write access, so it is insufficient against tampering.
- Number events per source/partition and monitor for gaps, duplicates, and clock drift. Multi-service systems do not have a global ordering based on timestamps alone.
- For critical business events, consider a **transactional outbox/event store** to tie transaction data and audit trails together, rather than relying on in-memory logging queues.

**Important limitation:** TLS or signatures on events cannot prove the true actor if the application took the actor from a spoofed header. A signature only attests to the data that was signed. Accountability requires a chain of trust: authentication, business logic, log source, transport, storage, and read/delete permissions.

## 10. Ensuring availability: logging must not become a DoS vector

An attacker can send a flood of requests to trigger WARN/ERROR logs, long stack traces, or events with large payloads. The logging system itself can make the service unavailable:

- **CPU** busy building messages, serializing JSON, formatting exceptions.
- **Heap** holding large queues, events, and MDC snapshots; increased GC pressure.
- **Disk** filled by log files and insufficient rotation limits.
- **Request threads** blocked by synchronous appenders or full async queues.
- **Collector/backend** overloaded, retrying endlessly, or incurring high ingest costs.
- **Dashboards** slowed down by excessive field cardinality.

Simple model: `λ` is the log event generation rate (events/sec) and `μ` is the consumer processing rate. If `λ > μ` persists, the backlog grows until it hits a limit. **Increasing queue size only delays the queue filling up; it does not make the sink faster.**

| Control | What It Controls | Trade-off |
| --- | --- | --- |
| Bounded queue | Limits heap usage | When full, must block/drop/fallback according to policy |
| Event size limit | Prevents oversized payloads | May truncate data; requires a truncated marker |
| Rate limiting or aggregation | Reduces repetitive logs | Must not suppress critical security events |
| Controlled sampling | Reduces operational log volume | Unsuitable if it randomly drops mandatory audit events |
| Disk quota/separate volume | Isolates app from log disk full | Must monitor and define behavior when full |
| Async appender | Offloads part of I/O from requests | Does not guarantee event preservation on crash by default |
| Collector buffering | Absorbs network hiccups | Finite buffer with risk of loss/duplication |

**Fail-open vs fail-closed:** if a sink fails, logging should generally not bring down the entire system just because DEBUG logs are lost. However, for mandatory audits, proceeding with a transaction without recording an audit trail may violate requirements. This is a **business policy decision** requiring durable mechanisms and reconciliation; do not apply one default to all log types.

## 11. Transport, collector, and storage pipelines also need a threat model

### In transit

- When transmitting over untrusted networks, use TLS and consider mTLS/service identity as needed.
- Source service/tenant identity must be bound to the **authenticated identity of the channel**, not just a `service.name` value in the payload.
- Collectors should validate schema, size, field count, timeouts, and authorization to write to a specific index/tenant.
- Monitor `retry`, `drop`, `ingest errors`, and `lag`; an HTTP 200 from a collector may only mean "accepted," not that the data is already searchable.
- Never allow client data to determine sink URLs, filenames, or server storage paths.

### At the store and read permissions

- Separate **ingest**, **read/search**, **export**, **config**, and **delete/retention** permissions. A dashboard-only viewer account should not also have permission to delete an index.
- Encryption at rest/in transit is necessary when required, but **does not replace IAM/RBAC**.
- Log export/download operations and sensitive queries; consider requiring approval for bulk exports.
- Audit buckets, indices, snapshots, backups, attachments, and test-environment copies—not just the production store.
- Ensure retention applies to appropriate copies and complies with legal and personal-data obligations.
- Never place log directories under a public web root or use signed links without an expiration time.

### Viewer/export attack surface

A JSON event may be safe when written, yet dangerous if a dashboard renders fields as unescaped HTML. CSV exports can contain strings starting with `=`, `+`, `-`, or `@` that spreadsheet tools interpret as formulas if not safely handled. Log content must be treated as **untrusted data** at every display or transformation step.

## 12. Logging configuration is also an asset to protect

Someone with permission to modify loggers/appenders can:

- Lower the level or disable loggers that record security events.
- Enable DEBUG/TRACE to cause logs to capture more PII/secrets.
- Redirect appenders to files/sockets or endpoints they control.
- Delete/shorten retention and disable collectors/agents.
- Disable masking or alter schemas/filters, causing loss of evidence.

Recommended controls:

1. **Least privilege:** separate configuration-change permissions from read and delete permissions where risk warrants it.
2. **Change management and auditing:** who changed it, when, before/after, and purpose; alert on anomalous changes.
3. **Do not rely solely on the root logger level** for mandatory security events.
4. **Time-bound DEBUG enabling**, scoped to specific packages, with an automatic revert mechanism.
5. **Protect management endpoints** such as `/actuator/loggers` if used; require authentication/authorization and never expose them to the Internet.
6. **Test multi-instance reloads:** changing configuration on one pod does not necessarily apply to all pods; verify config version/effective level.

Secure configuration must distinguish "logging less to reduce overhead" from "blinding incident detection." Never drop authorization or privilege-change logs just to reduce INFO line counts.

## 13. Schema for more trustworthy security events

Illustrative JSON event example, with field names agreed upon by the operations team:

```json
{
  "timestamp": "2026-11-10T02:30:00.100Z",
  "service.name": "identity-api",
  "event.name": "authorization_denied",
  "event.id": "evt_501",
  "actor.id": "acct_17",
  "actor.authenticated": true,
  "action": "READ_PROFILE",
  "resource.type": "user_profile",
  "outcome": "DENY",
  "reason.code": "INSUFFICIENT_SCOPE",
  "http.route": "/profiles/{id}",
  "http.response.status_code": 403,
  "request_id": "req_42",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "schema.version": 1
}
```

Rules must be defined for each field:

- `timestamp` is the event time at the source in UTC; an ingestion time may be added to detect delays.
- `event.name` and `reason.code` belong to an allowlist and must never be taken verbatim from the request.
- `actor.id` comes from the authenticated security context; if anonymous, record that explicitly rather than guessing from headers.
- `http.route` should be the server-known route template, not the raw URL with query/tokens.
- `request_id` and `trace_id` must be validated and propagated properly; **they are not proof of an authenticated actor**.
- `outcome` reflects the actual business result, not inferred merely from whether an exception occurred or from the HTTP status alone.
- `event.id` helps reconcile duplicates/gaps, but a self-generated ID does not inherently provide tamper/deletion resistance.
- `schema.version` lets collectors know how to parse the event type correctly.

Specify retention and who may view `actor.id`; sometimes a pseudonymized ID is sufficient. An audit event intended for accountability must be backed by authentication and trustworthy storage, not just well-formed JSON fields.

## 14. MDC, trace context, and asynchronous logging

### Context spoofing

If a request carries `X-Request-ID: req_admin` and the application copies it straight into MDC, an attacker can create duplicate IDs or disrupt investigations. Define a **canonical request ID source**, validate length/characters, and define a policy for invalid headers. For W3C trace context, use validated parsers/instrumentation and do not blindly trust all client metadata.

### Context leakage across requests

Java thread pools reuse threads. If `MDC.put("tenant_id", ...)` lacks scoped cleanup, a subsequent request may inherit the previous request's tenant ID. This both corrupts evidence and risks cross-tenant data leakage.

```java
// Illustrative snippet using SLF4J MDC, not a standalone program.
// When context is set by an outer layer, save and restore it within the proper scope.
org.slf4j.MDC.put("request_id", validatedRequestId);
try {
    processRequest();
} finally {
    org.slf4j.MDC.remove("request_id");
}
```

The snippet above requires the SLF4J dependency, the `processRequest` method, and the application's `validatedRequestId` variable. It only illustrates cleanup; if an older MDC value exists from a parent scope, removing it directly can lose valid context—restore it using the appropriate mechanism instead.

### Async queues and snapshots

Consumers run on a different thread from producers. Events must capture the necessary context (trace ID, span ID, timestamp, appropriate actor context) before being enqueued. Never let a consumer read the worker thread's current MDC and apply it to an older event; it may be empty or wrong.

Avoid putting secrets/PII into tracing baggage where it automatically appears in every log. Do not use `trace_id` or `request_id` as low-cardinality metric labels; high-cardinality values can overload the observability system.

## 15. Dependencies, formatters, and dynamic processing

Logging frameworks and plugins are software that must be updated like any other dependency:

- Inventory the actual runtime logging backend (Logback, Log4j2, JUL bridge) and transitive dependencies.
- Check advisories/vulnerabilities against the exact deployed versions; do not assume using SLF4J alone avoids backend vulnerabilities.
- Avoid unnecessary lookup/evaluation features on untrusted strings and dynamic appender configuration driven by input.
- Restrict custom formatters/parsers that accept unbounded events or perform repeated decoding.
- Verify that appender I/O paths cannot be steered to client-chosen endpoints or file paths.
- Test log viewers/search/exports for injection and permission boundaries.

**Log4Shell (CVE-2021-44228)** is a historical example of the consequences of processing untrusted data inside a logging component with a vulnerable version/configuration. This does **not** mean every Log4j2 version or every placeholder call has that vulnerability. Always evaluate based on actual versions and patches.

## 16. Risk ranking and mitigation plan

For each threat, document **source → attack path → trust boundary → impact → control → test → residual risk**. Example:

| ID | Scenario | Primary Control | Expected Evidence |
| --- | --- | --- | --- |
| T1 | CRLF header injects fake lines | JSON schema + neutralization + max length | One request produces one valid event, no fake lines |
| T2 | JWT logged when SDK throws exception | Field allowlist + canary scan | Dummy token does not appear in files, indices, or exports |
| T3 | Admin deletes audit logs | Separation of duties and immutable copy | Delete attempt denied or tampering detected |
| T4 | Brute force fills log disk | Quota, bounded queue, rate bound | Burst test does not exhaust application disk |
| T5 | Tenant A MDC leaks into request B | Cleanup/restore and snapshot | Concurrent runs do not mix actors/tenants |
| T6 | Collector loses connectivity | Delivery lag/drop metrics, alerts, bounded buffer | Alert fires and chosen policy is enforced |
| T7 | Runtime logger disabled | Admin RBAC, audited configuration | 401/403 for unauthorized users; valid changes have an audit trail |
| T8 | CSV export triggers formula execution | Context-aware safe export | Client-supplied strings do not become formulas |

T2 can be critical if the token remains valid and logs are widely readable; T4 is severe if log files and the database share a disk. Rank risks by **exploitability × impact**, rather than defaulting everything to critical.

## 17. Logging security testing

### Content and injection

1. Send CR/LF, tabs, control characters, Unicode separators, text with `=`, quotes, and oversized inputs to externally facing fields.
2. Verify the parser receives **exactly one structured event**, no forged events, and subsequent events are not corrupted.
3. Test HTML dashboards, CSV exports, and query interfaces with the same neutralized payloads.
4. Ensure malformed events raise errors or are sanitized in a controlled way without misassigning actors or event types.

### Secrets, permissions, and data

1. Use **dummy/canary secrets**, never real tokens, in tests; search for the canary across stdout/files/collector/index/dashboard/exports.
2. Trigger exceptions in HTTP clients, JDBC, SDKs, and authentication providers; verify raw request bodies/headers are not exposed.
3. Use read-only, export, admin, and audit roles to verify RBAC separation.
4. Check retention, snapshots, backups, staging files, and unintended access paths.
5. Enable DEBUG in a test environment and confirm no secrets appear inadvertently.

### Integrity and source authentication

1. Spoof `X-User-ID`, `X-Forwarded-For`, `X-Request-ID`; actor/source address must follow the defined trust model.
2. Trigger authorization denials, role changes, and privileged actions; verify events, outcomes, and context come from real logic.
3. Attempt to modify/delete audit data with test accounts and confirm it is blocked/detected per policy.
4. Check for gaps/duplicates, event time vs ingestion time, and clock drift.
5. Send data from service A while claiming `service.name=B`; the collector must not elevate payload claims to source identity.

### Availability and pipeline failures

1. Generate log bursts from error requests to observe queue depth, CPU, GC, disk, and p99 latency.
2. Slow down the sink or drop the network; count attempted/enqueued/written/dropped events and verify alerts.
3. Simulate disk full, appender permission denied, and collector timeout; verify the approved fail-open/fail-closed policy.
4. Kill the process while the queue still has a backlog to assess event-loss risk, distinct from a normal drain on shutdown.
5. Test multi-tenant and multi-pod setups to ensure one tenant's logs/traces cannot be read by another tenant.

**PASS criteria must be specific:** include test event IDs, expected fields/values, checked source scope, access permissions, dropped event counts, and alert evidence. Seeing a single WARN line on the console is not enough to prove the pipeline is safe.

## 18. Pipeline observability and incident response

The following metrics are **instrumentation suggestions**, not built-in metric names in every framework:

| Signal | Meaning |
| --- | --- |
| `logging_events_attempted` | Unusual volume, brute force |
| `logging_events_dropped` | Events lost due to queue/collector/policy |
| `logging_queue_depth` | Bottleneck or slow consumer |
| `event_to_ingest_lag` | Delay before data is searchable |
| `collector_ingest_errors` | Parser, TLS, auth, or network errors |
| `audit_sequence_gaps` | Sign of missing/altered records when a trusted sequence exists |
| `log_config_changes` | Who changed level/filter/sink/retention |
| `log_export_bytes` | Unusually large data exports |
| `tamper_detection_alerts` | Sign of modification/deletion or failed integrity check |
| `secret_scan_hits` | Sensitive data that may have leaked into logs |

When a **token is found exposed in logs**:

1. Stop emitting the token at the source (fix schema/encoder/logging call) and restrict access.
2. Revoke/rotate the secret based on impact; deleting a log line does not invalidate a token.
3. Trace propagation paths: files, stdout, collectors, indices, dashboards, exports, and backups.
4. Audit who viewed/downloaded the data and notify/respond per organizational policy.
5. Handle stored copies according to retention/legal requirements and add regression tests to prevent recurrence.

When **log tampering/deletion is suspected**, do not overwrite existing evidence. Preserve copies under independent access control, cross-check against transaction stores and gateway/collector logs, and investigate which configuration or deletion permissions were used.

## 19. Threat modeling checklist for design reviews

- [ ] Mapped the flow: client → Java logger → appender/queue → collector → store → viewer/export.
- [ ] Identified assets, threat actors, control capabilities, and trust boundaries.
- [ ] Classified application, access, security, and audit events; avoided conflating retention.
- [ ] Identified which identities come from security principals and which metadata is merely client-provided.
- [ ] Defined a field allowlist and avoided logging raw credentials or sensitive bodies/headers by default.
- [ ] Tested log injection/forging and output encoding for text/JSON/HTML/CSV.
- [ ] Bounded event size, queues, and disk; defined policy when sinks fail.
- [ ] Enforced RBAC for ingest/read/export/config/delete and tenant isolation.
- [ ] Protected transport and log-source provenance.
- [ ] Verified log context does not leak across threads/requests/tenants.
- [ ] Determined whether audit trails need durable storage, tamper evidence, and business reconciliation.
- [ ] Monitored dropped events, lag, collector errors, and configuration changes.
- [ ] Tested secret canaries, spoofed headers, parsers, dashboards, and exports.
- [ ] Assigned incident responders for when logging stops, is tampered with, or leaks data.
- [ ] Documented residual risks and risk owners.

**Remember:** a complete logging threat model protects **data confidentiality**, **the accuracy and integrity of trails**, and **the operability of both the service and pipeline**. Logs only help security when events are generated from trustworthy sources, do not expose protected information, can detect loss or tampering, and are accessed by the right people at the right time.

### References

- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [MITRE CWE-117 — Improper Output Neutralization for Logs](https://cwe.mitre.org/data/definitions/117.html)
- [OWASP — Log Injection](https://owasp.org/www-community/attacks/Log_Injection)
- [NIST SP 800-92 — Guide to Computer Security Log Management](https://csrc.nist.gov/pubs/sp/800/92/final)
- [Java 17 API — java.util.logging.Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html)
