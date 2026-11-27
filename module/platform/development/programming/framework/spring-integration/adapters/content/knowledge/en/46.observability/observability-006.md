# Controlled Payload Logging in Spring Integration Adapters

## 1. Why Not Log the Entire Payload?

In Spring Integration, a message can carry file contents, database rows, HTTP bodies, Kafka events, JMS/AMQP messages, documents fetched from SFTP, or transformed Java objects. When a flow fails, the seemingly fastest action is to print the entire `Message<?>`, payload, and headers. That is also the easiest way to accidentally leak **personal data, payment details, passwords, access tokens, session cookies, private keys, customer records, and internal system topology**.

**Controlled payload logging** is a design that captures **enough information to diagnose issues** while restricting **which fields are recorded, at which checkpoints, at what rate, who may read them, and how long they are retained**. Safe metadata should be the default; only include approved subsets of business data after assessing sensitivity and investigative need.

This lesson belongs to the **Observability** chapter of the **SPRING_INTEGRATION_ADAPTERS** module. The module covers integrating external systems via inbound/outbound adapters, gateways, pollers, and MessageChannels across file, SFTP, HTTP, JMS, AMQP, Kafka, and databases, while observing **message contracts, errors, and connection lifecycles**. Therefore, the focus is not merely logger configuration, but **placing observation points correctly without accidentally leaking sensitive data at adapter boundaries**.

### Learning Objectives

After this lesson, you can:

1. Distinguish metadata logs, projected/redacted payload logs, raw payload logs, and business audits.
2. Establish **deny-by-default**, field allowlists, size limits, redaction, and retention policies.
3. Use **WireTap, MessageChannel, service activator, and LoggingHandler/DSL logging** purposefully.
4. Prevent content leaks across File/SFTP/HTTP/JMS/AMQP/Kafka/JDBC adapters, converters, and error flows.
5. Produce safe structured logs and link them with correlation IDs, message history, Micrometer metrics, and distributed tracing.
6. Test against data leaks, operate time-bounded debug logging, and respond when logs actually capture sensitive data.

> **Limitation:** Java examples and configurations illustrate the approach. API/overload names may vary across Spring Integration, Spring Boot, and logging stacks; verify against your project's version. This guide does not grant default permission to write PII or secrets into production logs.

## 2. What Makes a Log Record Sufficient for Diagnostics?

Suppose an adapter receives an order over HTTP and forwards it to Kafka. To know which steps the message passed through, the system typically only needs:

~~~json
{
  "event": "INTEGRATION_CHECKPOINT",
  "flow": "http-order-to-kafka",
  "component": "validateOrder",
  "direction": "inbound",
  "payload_type": "json",
  "size_bucket": "1kb-10kb",
  "schema_version": "v2",
  "outcome": "accepted",
  "correlation_ref": "opaque-correlation-id",
  "trace_ref": "trace-context-reference"
}
~~~

You **do not need** full order JSON, emails, customer addresses, access tokens, or payment fields to see which transformer failed. Deeper details can be looked up via a **controlled reference ID** in the business system if the investigator is authorized.

### 2.1. Four Logging Levels

| Level | Content | Usage |
|---|---|---|
| **L0 — Technical metadata** | Flow, component, message type, outcome, reason code, size bucket, duration | Default for production |
| **L1 — Approved business metadata** | Event type, schema version, document category, opaque business reference | After data classification review and approval |
| **L2 — Sanitized sample** | An allowlisted subset of fields, normalized and tested for redaction | Restricted investigation, sampled and TTL-bounded |
| **L3 — Raw payload** | Full body, file, record, or message | **Disallowed** by default; exceptional cases require an authorized specialized process outside normal app logs |

L2 is not “call `toString` and mask a few strings.” The safer approach is **explicitly extracting only approved fields** and emitting nothing else. L3 carries major risk because log copies spread across collectors, SIEMs, search indexes, alerts, backups, and support accounts.

## 3. Classify Data Before Deciding What to Log

### 3.1. Data Categories to Evaluate

| Data Category | Examples | Recommended Default Policy |
|---|---|---|
| **Secrets/credentials** | Passwords, OAuth tokens, API keys, private keys, cookies, session tokens, recovery codes | **Never log values**, even in debug; log only safe key IDs/fingerprints if needed |
| **Personal data** | Full names, emails, phone numbers, addresses, customer identifiers | Do not log by default; use opaque refs or aggregates |
| **Financial/health/sensitive data** | Payment info, diagnoses, confidential contract data | Never log contents; follow industry controls and policy |
| **Low-sensitivity business payload** | Fixed-catalog event types, schema versions | May be allowlisted after review |
| **Internal information** | Remote paths, hostnames, tenant names, endpoint IDs, queues/topics | Log only to the degree needed; avoid leaking topology externally |
| **Technical metadata** | Direction, bounded error codes, payload kind, retry count | Generally suitable if normalized and free of user-supplied values |
| **Binary/opaque bodies** | PDFs, images, byte[], multipart files, protobuf | Never dump bytes/base64; log type, size bucket, and approved checksums |

**Even seemingly harmless fields can be sensitive**: filenames containing customer names, HTTP paths containing account numbers, Kafka keys containing emails, exception messages containing raw requests, or correlation IDs that are actually contract numbers. Renaming a field to `masked` does not automatically make it safe.

### 3.2. What Data Should Be Used for Investigation?

Prefer information that avoids keeping raw content:

- Application-assigned flow/endpoint IDs from an approved catalog.
- Timestamps, durations, outcomes, and bounded error classifications.
- Message sizes **as buckets** instead of exact byte values when size itself is sensitive.
- Schema versions and event categories from an approved list.
- Record/batch counts and retry attempts.
- Opaque correlation references generated by a trusted system without embedding PII.
- Evidence/ticket references to look up payloads in an authorized store instead of copying payloads into logs.

### 3.3. Logs Are Not Business Data Stores

Logs are routinely replicated to collectors, SIEMs, search indexes, alert notifications, and backups. **Deleting logs on one instance does not erase every copy**. If a payload must be retained for compliance/auditing, build a **dedicated data store or audit store** with explicit access control, encryption, retention, and purpose limitation.

## 4. Common Payload Leak Points in Spring Integration

~~~mermaid
flowchart LR
    EXT[HTTP / SFTP / File / JMS / AMQP / Kafka / DB] --> IN[Inbound Adapter / Gateway]
    IN --> CH[Input MessageChannel]
    CH --> CV[Converter / Transformer]
    CV --> H[Filter / Router / Handler]
    H --> OUT[Outbound Adapter / Gateway]
    OUT --> TARGET[Remote Target]
    CH -. WireTap .-> SAFE[Safe Log Projection]
    CV -. Exception .-> ERR[Error Channel / ErrorMessage]
    H -. Observation .-> MET[Metrics / Tracing]
    SAFE --> COL[Protected Log Collector]
    ERR --> COL
    MET --> OBS[Monitoring]
~~~

Several places emit logs outside business code:

1. **Framework DEBUG/TRACE** can log messages, payloads, or headers in certain loggers/adapters depending on version.
2. **`LoggingHandler`** or DSL `.log(...)` can output more data than intended if default expressions are used or the whole `Message` is printed.
3. **WireTap** creates an observation branch; the handler on that branch might accidentally log raw payloads.
4. **HTTP client/server logging** can capture request/response bodies and `Authorization`.
5. **Kafka/JMS/AMQP converters** can dump records/headers when parsing fails.
6. **SFTP/File adapters** can log paths, filenames, permissions, or contents if custom code prints objects.
7. **JDBC/ORM SQL logging** can print bind parameters and row data.
8. **Exception stack traces** can include URLs with query tokens, partner error bodies, or values interpolated into exception messages.
9. **Tracing baggage/span attributes** can ship message contents to the tracing backend.

**Scope of control** must cover application code, framework log levels, middleware/clients, and telemetry exporters—not just masking a payload in one service activator.

## 5. Logging Policy by Environment and Purpose

| Environment | Default | When Investigation Is Needed |
|---|---|---|
| **Unit test** | Synthetic test data allowed | Test log projection logic and anti-leak rules |
| **Local dev** | Metadata + synthetic data; never production credentials | Increase detail on safe fixtures |
| **Staging** | Normalized metadata and synthetic fixtures | Enable sanitized samples per testing |
| **Production** | L0 and select approved L1; no raw bodies | Activation requires ticket/owner/TTL, sampling, and output controls |

### 5.1. Do Not Rely Solely on Logger Levels

Changing `DEBUG` to `INFO` does not protect data if an `INFO` logger prints the full payload. Conversely, turning on `TRACE` for all Spring Integration packages can enable unreviewed logging across many places.

**Safe default:** every log site uses a **safe projection** regardless of log level; enabling debug only adds more checkpoints or raises sampling frequency, **never unlocking sensitive content**.

### 5.2. Prerequisites for Temporary Verbose Logging

Before enabling elevated logging detail in production, require:

1. An incident/ticket and justification for why extra fields are needed.
2. **Scoped** flow, component, environment, and message subset.
3. Data classification review specifying allowlisted vs. excluded fields.
4. Authorized approval per policy.
5. Sampling rate, expected log volume, and **expiration time**.
6. Target log backend, access controls, retention, and rollback plan.
7. Anti-leak test verifying credentials/PII stay excluded before rollout.
8. Post-incident verification confirming configuration returned to baseline.

**Never** enable bulk payload logging just to track down one message when correlation IDs, error codes, and traces suffice.

## 6. How Body Logging Differs from Header Logging

A Spring Message has a `payload` and `headers`. Many teams mask the body while overlooking:

| Location | Sensitive Data That May Appear |
|---|---|
| Payload | JSON with emails, XML with account numbers, binary documents, DB rows |
| HTTP headers | Authorization, Cookie, Set-Cookie, custom API keys, client certificate metadata |
| JMS/AMQP headers | Application properties with tokens, user/keys, uncontrolled trace baggage |
| Kafka headers/key | Business IDs carrying PII, tokens in custom headers, tenant identifiers |
| Spring Integration headers | `file_name`, remote paths, reply/error channels, original files, internal routing |
| Error messages | Failed payloads, nested exceptions, original messages, URLs, raw responses |
| Message object strings | May stringify payload **and** headers, depending on type/implementation |

### 6.1. Header Allowlists Instead of Blacklists

A **blacklist** only removes known names like `Authorization`, while a custom `x-session-secret` header still slips through. For diagnostic logs, **build a fresh log object containing only permitted fields** (flow ID, endpoint ID, outcome, payload kind) rather than iterating/copying all headers.

### 6.2. Do Not Trust Every Sender-Provided Header

An external HTTP caller or Kafka producer can set `correlationId` or `eventType` to arbitrary values, including newlines for log forging, huge strings, or PII. Validate format, normalize, bound length, and ideally issue an **internal opaque ID** at ingress for untrusted sources.

## 7. WireTap Is an Observation Point, Not Automatic Data Protection

In Spring Integration, `WireTap` (a channel interceptor) forwards messages to a secondary channel for observation while the main flow continues. It helps add checkpoints without modifying every handler.

~~~mermaid
flowchart LR
    SRC[Inbound] --> INPUT[rawInput]
    INPUT --> FLOW[Business Flow]
    INPUT --> TAP[WireTap]
    TAP --> LOGCH[safeLogChannel]
    LOGCH --> PROJ[Allowlist + Classification]
    PROJ --> LOG[Structured Log]
    FLOW --> OUT[Outbound]
~~~

### 7.1. Risks with WireTap

- **No automatic redaction:** messages sent to the tap channel still carry original payloads and headers.
- **Not durable by itself:** a logging branch is neither an audit store nor a message backup.
- **Performance impact:** slow synchronous logging increases latency; async adds queues, memory usage, and drop risk when full.
- **Mutable payloads:** if the payload holds mutable objects, the tap branch and business flow may share the same reference; never assume deep copies happen automatically.
- **Exceptions:** failures in loggers, appenders, or safe projections must follow architectural policy; do not let an optional debug feature break business messages unintentionally.
- **Lifecycle:** if a log queue fills up, define drop/backpressure policies, metrics, and alerts; never silently buffer sensitive data in memory.

### 7.2. Design Rule

**WireTap should send only to a consumer dedicated to building safe log records**, never to a logger calling `message.toString()`. The observation channel needs clear naming, access control, rate bounds, and integration tests alongside the business flow.

## 8. Java DSL Example: Attaching WireTap and a Safe Metadata Logger

The following example shows a flow receiving messages, applying a WireTap on a channel, and running business logic normally while a dedicated handler reads **minimal metadata**. Verify imports and APIs against your deployment version.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHandler;

@Configuration
public class SafeLoggingFlowConfiguration {

    @Bean
    MessageChannel rawInput() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel safeLogChannel() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel businessInput() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow inboundFlow() {
        return IntegrationFlow.from("rawInput")
                .wireTap("safeLogChannel")
                .channel("businessInput")
                .get();
    }

    @Bean
    @ServiceActivator(inputChannel = "safeLogChannel")
    MessageHandler safeLogHandler() {
        return SafeLogProjection::writeLog;
    }

    @Bean
    @ServiceActivator(inputChannel = "businessInput")
    MessageHandler businessHandler() {
        return message -> {
            // Execute business logic; do not log raw payload.
        };
    }
}
~~~

**Important:** this demo only illustrates the wiring. Using `DirectChannel` for the logging branch incurs synchronous cost; for high-throughput systems consider **bounded executors, backpressure, and failure tests**. Mandatory auditing should not rely solely on an auxiliary WireTap.

## 9. Java Example: Creating a Safe Log Projection Instead of Printing Messages

A basic logger class can log only **internal message ID, bounded payload kind, and allowlisted event type**, without reading the whole body.

~~~java
import java.io.File;
import java.util.Set;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.messaging.Message;

public final class SafeLogProjection {
    private static final Logger LOG =
            LoggerFactory.getLogger(SafeLogProjection.class);

    private static final Set<String> APPROVED_EVENTS =
            Set.of("ORDER_RECEIVED", "INVOICE_IMPORTED", "FILE_READY");

    private SafeLogProjection() {}

    public static void writeLog(Message<?> message) {
        Object rawEvent = message.getHeaders().get("eventType");
        String eventType =
                rawEvent instanceof String
                && APPROVED_EVENTS.contains(rawEvent)
                        ? (String) rawEvent
                        : "OTHER";

        String payloadKind = classifyPayload(message.getPayload());

        LOG.info(
                "event=INTEGRATION_CHECKPOINT flow=orders "
                + "outcome=received payload_kind={} event_type={} "
                + "message_ref={}",
                payloadKind, eventType, message.getHeaders().getId()
        );
    }

    private static String classifyPayload(Object payload) {
        if (payload instanceof byte[]) {
            return "binary";
        }
        if (payload instanceof String) {
            return "text";
        }
        if (payload instanceof File) {
            return "file";
        }
        return "object";
    }
}
~~~

### 9.1. Why Does This Example Limit Leaks?

- `payload` **never has `toString()` or serialization called on it**.
- Only three valid `eventType` values are emitted; everything else maps to `OTHER`.
- No arbitrary headers are copied into the log.
- `flow` and `outcome` are fixed constants controlled by code.
- Message ID here is the Spring Message ID used as an application-local reference; **never assume it equals a cross-system business ID**.

### 9.2. Production Decisions Still Needed

1. Whether message IDs are permitted and their retention window under privacy policy.
2. Whether `INFO` frequency should be reduced to avoid high log volume.
3. How to attach validated, PII-free `traceId/correlationRef`.
4. When payload is an `InputStream` or lazy resource, never consume its contents just to build a log.
5. How to guard against logger/appender exceptions, full log queues, and throughput degradation.
6. Guarding log statements so payloads are never evaluated just to construct discarded strings.

## 10. LoggingHandler and DSL `.log(...)`: Control Expressions Carefully

Spring Integration provides `LoggingHandler` and DSL `log(...)` helpers to record message info in a flow. Some default usages can print the payload or entire message object. **Never use `.log()` unchecked on sensitive data paths**.

### 10.1. Choosing an Implementation Approach

| Approach | When Suitable | What Must Be Verified |
|---|---|---|
| Custom handler like section 9 | Need exact control over emitted fields | Uses only safe projection, no raw headers |
| DSL `log(...)` with explicit expression | Want concise checkpoints inside a flow | Expression never returns payload/Message; verify overloads/version |
| `LoggingHandler` with configured level/expression | Java/XML systems configuring explicit handlers | Ensure it does not log raw content by default |
| Framework logger DEBUG/TRACE | Investigating library internals during an incident | Scope, TTL, and whether it logs headers/payloads |
| WireTap + bounded logging channel | Decoupling logging from business handlers | Queue/memory bounds, logger failures, leak tests |

### 10.2. Log Expressions Should Emit Controlled Derived Data

**Desired logical output** for a checkpoint:

~~~text
Output only:
  checkpoint = "validateInvoice"
  flow = "sftp-invoice-import"
  outcome = "accepted"
  correlation_ref = validatedOpaqueRef
  payload_kind = "json"

Never output:
  payload
  message.toString()
  headers.toString()
  full failed message
  raw exception message
~~~

When using SpEL, Kotlin DSL, or Java DSL, expression results must be **safely classified values**, not disguised equivalents of `payload.toString()`. Safety depends on what actually reaches the appender, not which API call was used.

## 11. Do Not Log Payloads by Calling Object `toString()`

Java objects commonly implement `toString()` for debugging, which may expose:

- Every DTO field via Lombok `@Data` or `@ToString`.
- Hibernate/JPA entities with relationships and sensitive fields.
- Collections with thousands of elements.
- Value objects storing tokens/secrets in fields.
- URLs with secret query parameters.
- Spring `Message<?>` containing both payload and headers.

A minor DTO change can cause logs to leak new fields even when logger code stays untouched.

### 11.1. Anti-Pattern Example

~~~java
// Unsafe for unclassified payloads:
log.debug("Received message={}", message);
log.info("Payload={}", message.getPayload());
log.warn("Headers={}", message.getHeaders());
log.error("Failed payload=" + payload, exception);
~~~

### 11.2. Safer Alternative

~~~java
log.warn(
    "event=PAYLOAD_REJECTED flow=invoice-import "
    + "reason_code={} payload_kind={} message_ref={}",
    "INVALID_SCHEMA",
    "json",
    message.getHeaders().getId()
);
~~~

**Note:** `reason_code` is modeled as a bounded enum, not raw exception text or a remote service body. To debug a specific item, use a trusted-system reference ID and look up data in an authorized store.

## 12. Redaction, Masking, Tokenization, and Allowlists

### 12.1. Four Distinct Techniques

| Technique | Example | Limitation |
|---|---|---|
| **Omission** | Exclude the `email` field completely | Safest and simplest when the field is unneeded |
| **Allowlist projection** | Extract only `eventType`, `schemaVersion` | Requires strict control over schema and field values |
| **Masking/redaction** | Replace email with `[REDACTED]` | Can miss nested structures or field aliases |
| **Tokenization/HMAC reference** | Map sensitive IDs to controlled opaque refs | Re-identification risk remains; requires key and access management |

A **plain hash** of low-entropy emails or phone numbers does not make data anonymous; it can be guessed via dictionary attacks. When stable correlation references are required, consider **key-managed HMAC**, purpose separation, and retention controls; outputs remain subject to privacy policies.

### 12.2. Why Regex Blacklists Are Insufficient

For example, a regex looking for `password=...` misses `passwd`, `pwd`, nested JSON fields, URL-encoding, base64, multipart forms, or secrets without familiar delimiters. Regex can serve as a **secondary defense layer**, never a replacement for not logging raw payloads.

### 12.3. Never Fall Back to Raw Logging on Parse Failures

One of the most dangerous anti-patterns:

~~~java
try {
    return parseAndMask(json);
} catch (Exception ex) {
    log.warn("Cannot parse, raw={}", json); // Unsafe
    return json;
}
~~~

Replace with:

~~~java
try {
    return approvedProjection(json);
} catch (Exception ex) {
    return "[UNAVAILABLE_SANITIZED_VIEW]";
}
~~~

Never log `ex.getMessage()` directly if the parser library can embed payload fragments in error messages; emit normalized **exception class/code** values and trace only in vetted, necessary places.

## 13. JSON Payload Example: Extracting Only Approved Fields

Suppose an inbound message carries JSON with `eventType`, `schemaVersion`, `customerEmail`, `paymentToken`, and `items`. Only the event type and schema version are needed to diagnose converter issues.

~~~json
{
  "eventType": "ORDER_RECEIVED",
  "schemaVersion": "v2",
  "customerEmail": "customer@example.invalid",
  "paymentToken": "EXAMPLE_ONLY_NOT_A_REAL_TOKEN",
  "items": [{"sku": "ABC", "quantity": 1}]
}
~~~

**Never** write the JSON above into production logs. The synthetic sample merely shows which fields to drop. You can build an allowlist projection with Jackson:

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Set;

public final class SafeJsonView {
    private static final ObjectMapper MAPPER = new ObjectMapper();
    private static final Set<String> EVENT_TYPES =
            Set.of("ORDER_RECEIVED", "ORDER_CANCELLED");
    private static final Set<String> SCHEMA_VERSIONS =
            Set.of("v1", "v2");

    private SafeJsonView() {}

    public static String eventType(String json) {
        try {
            JsonNode root = MAPPER.readTree(json);
            String value = root.path("eventType").asText("");
            return EVENT_TYPES.contains(value) ? value : "OTHER";
        } catch (Exception ignored) {
            return "UNKNOWN";
        }
    }

    public static String schemaVersion(String json) {
        try {
            JsonNode root = MAPPER.readTree(json);
            String value = root.path("schemaVersion").asText("");
            return SCHEMA_VERSIONS.contains(value) ? value : "OTHER";
        } catch (Exception ignored) {
            return "UNKNOWN";
        }
    }
}
~~~

### 13.1. Improvements Needed in Real Systems

- Parsing twice as shown is **simple but suboptimal**; in production, parse once during existing validation and extract permitted fields there.
- Never parse giant JSON bodies **solely for logging**; enforce input size limits, timeouts, and resource protection at ingress.
- Avoid free-text fields: `eventType` and `schemaVersion` are checked against fixed sets.
- Do not serialize sensitive payloads to JSON just to “mask before logging” if not otherwise needed.
- If an unrecognized schema arrives, log `OTHER` or an error code rather than dumping raw JSON for manual inspection.

## 14. Size Limits, Sampling, and Rate Limiting

Even metadata-only logs can overwhelm high-throughput Kafka or HTTP flows.

### 14.1. Intentional Sampling

| Sampling Approach | Suited For | Risk |
|---|---|---|
| **Flow-level ratio** | General production visibility | Can miss rare errors |
| **Deterministic by opaque ID** | Tracking one message group consistently | Must avoid leaking/hashing PII and skewing distribution |
| **Error-biased sampling** | Raising detail on error codes | Can spike log volume during outages |
| **Time-bounded debug** | Narrow incident/flow investigation | Forgetting to disable causes cost/leak risk |
| **Per-component throttling** | Protecting log collectors during bursts | Drops some events; requires a dropped counter |

Sampling **does not make a sensitive field safe**. Every sampled event must still pass the allowlist/sanitizer. Never use external correlation IDs as sampling seeds without validating/neutralizing them.

### 14.2. Bounding Log Size

Bound:

- Maximum length of every allowed string field.
- Maximum count of emitted attributes or elements.
- Size buckets instead of exact sizes when appropriate.
- Total bytes per event sent to the collector.
- Total volume per flow and capped sampling rates.

When limits are exceeded, emit `TRUNCATED` or `OMITTED`, and **never** continue printing the remainder to another appender.

## 15. File Adapter: Never Log Arbitrary Filenames and Contents

### 15.1. File Inbound

A file can hold invoices, customer lists, HR records, or medical documents. Beyond payloads, file paths often contain **customer names, tenants, projects, or confidential identifiers**.

What to log:

| Field | Handling |
|---|---|
| Flow ID | Fixed value, e.g., `invoice-file-import` |
| Source type | `file` |
| Payload kind | `file`, `bytes`, or `text` |
| Size | Bucket such as `10kb-100kb` |
| Checkpoint | `discovered`, `accepted`, `parsed`, `confirmed` |
| File name/path | Not logged by default; use an opaque file reference |
| File content | Never log raw |
| Parse exception | Error code like `INVALID_CSV_SCHEMA`; never print failing lines with PII |

### 15.2. File Outbound

When writing files, a “file sent” log before rename/flush/atomic handoff (if designed) can mislead. Separate `write_started`, `write_completed`, and `handoff_confirmed` using safe metadata. Never store file contents in logs to verify integrity; use checksums/evidence approved by system owners.

### 15.3. InputStream and Resource Lifecycle

If a payload is an `InputStream` or lazy resource, reading a few KB for logging can **consume the stream**, starving downstream business handlers or adding heavy I/O. Never read payloads to preview them just for debugging; rely on metadata or bounded buffers designed for business logic.

## 16. SFTP: Remote Paths, Sessions, and Credentials

SFTP inbound/outbound adapters handle remote filenames/paths, session metadata, authentication errors, and transfer durations.

**Do not log:**

- Usernames/passwords, private keys, passphrases, credential URIs.
- Full remote paths containing customer names, accounts, or sensitive internal structure.
- Contents of transferred documents, especially in parse error logs.
- Unfiltered SSH stack diagnostics containing secrets/sensitive config.

**Do log:**

| Event | Appropriate Metadata |
|---|---|
| SFTP poll | `source=sftp`, flow, poll outcome, eligible file count |
| Session creation | Fixed dependency alias, `CONNECTED/FAILED`, duration |
| Download | Opaque file ref, size bucket, transfer outcome |
| Upload | Target alias, bytes bucket, confirmation stage |
| Error | `AUTH_FAILURE`, `NETWORK_TIMEOUT`, `REMOTE_PERMISSION` |
| Retry | Attempt count, bounded reason code, backoff category |

### 16.1. Never Put Hostnames/Usernames in Metric Tags or Public Logs

To identify a server, use an approved alias like `partner-sftp-a`; keep alias → host mappings in restricted configuration. Avoid printing full connection strings or secret manager paths unnecessarily.

### 16.2. Distinguish Pre-Message vs. Post-Message Errors

If SFTP fails to connect, no message exists and `MessageHistory` will not explain missing files. Observe via **poll metrics, session events, and error codes**; never enable full-file dumps once connectivity recovers.

## 17. HTTP Gateways: Risky Request/Response Bodies and Headers

### 17.1. HTTP Inbound Gateway

Requests may carry:

- Authorization bearer tokens, Cookies, API keys, session IDs.
- JSON bodies with emails, payment details, addresses.
- URL paths/queries with IDs or secrets.
- Multipart files, form data, or arbitrary client input.

Log **route templates**, HTTP method, status class, latency, request size bucket, and a trusted opaque request ID; never log raw URIs/queries/bodies or arbitrary headers.

### 17.2. HTTP Outbound Gateway

HTTP client errors often include partner response bodies. Error bodies can contain sensitive data, upstream internals, echoed requests, or tokens. Do not write:

~~~java
log.error("HTTP failed, responseBody={}", responseBody);
log.error("Request headers={}", requestHeaders);
log.error("Remote URL={}", fullUrlWithQuery);
~~~

Replace with:

~~~java
log.warn(
    "event=REMOTE_CALL_FAILED target={} status_class={} "
    + "error_class={} correlation_ref={}",
    "billing-api",
    "5xx",
    "REMOTE_SERVER_ERROR",
    safeCorrelationRef
);
~~~

Here `safeCorrelationRef` is logged only after **validation/normalization**, never copied straight from untrusted request input. On 202 or timeout, never treat a “sent” log as proof of remote business commit.

### 17.3. HTTP Wire Logging

HTTP clients/gateways may enable wire logging or interceptors capturing full headers/bodies. Audit HTTP server logging, WebClient/RestClient, proxies/API gateways, and HTTP libraries **simultaneously**. Disabling one application logger does not guarantee bodies are absent in proxies or tracing exporters.

## 18. JMS Adapter: Headers, Redelivery, and DLQ

JMS messages can hold text, bytes, map/object payloads, and application properties; adapters/converters turn them into Spring Messages.

### 18.1. Logging by Transport Semantics

| Event | Useful Safe Metadata |
|---|---|
| Message received | Broker alias, destination alias, correlation reference if safe |
| Processing attempt | Flow, handler, attempt index, result class |
| Redelivery | Redelivered flag/count if provided by system |
| Transaction/ack | Attempted, committed, or rolled back per real outcome |
| DLQ | Reason category, DLQ alias, opaque event reference |

**Never** dump entire `TextMessage`, `BytesMessage`, or JMS properties simply because a consumer failed; properties may hold session/tokens or sensitive identifiers.

### 18.2. Retries and Log Volume

A poison message can redeliver thousands of times, producing thousands of logs with the same payload if logging is unchecked. Use bounded retries, rate limits, DLQ, and terminal-failure counters; log by **event category** instead of printing the body on every failure.

## 19. AMQP/RabbitMQ: Do Not Confuse Broker Metadata with Payloads

AMQP messages include a body and headers/properties, along with routing keys, exchanges, and delivery tags. When logging:

- Use organization-managed fixed **exchange/queue aliases**.
- Log ack/nack/requeue outcomes, retry counts, DLQ events, and connection status.
- Never log raw message bodies on deserialization failure.
- Never treat dynamic delivery tags or routing keys as safe business correlation IDs.
- Clearly distinguish producer confirms, consumer ACKs, and business completion as separate milestones.

### 19.1. Converter Errors

When JSON/Java conversion fails, exceptions can embed data fragments. Instead of printing raw `failedMessage` or bytes, log:

~~~text
event=AMQP_CONVERSION_FAILED
target=orders-queue
content_type=application/json
error_class=INVALID_MESSAGE_SCHEMA
payload_kind=binary
attempt=2
~~~

These values are normalized examples. Never copy raw payloads into DLQ headers or error logs unless explicitly authorized by storage policy; the DLQ itself is a **sensitive data store** requiring ACLs and retention.

## 20. Kafka: Record Keys, Headers, and Serializer Logs

Kafka records have topic, partition, offset, key, value, and headers. In many systems, the **record key itself is a customer ID or email**, so do not log it by default.

| Component | Recommendation |
|---|---|
| Topic | Fixed name or alias if allowed by policy |
| Partition/offset | Operational metadata; govern scope/retention |
| Record key | Do not log raw unless classified safe |
| Record value | Never dump JSON/Avro/Protobuf/binary |
| Headers | Allowlist; strip sensitive tokens/baggage |
| Consumer group | Approved fixed name; never expose config secrets |
| Serialization error | Error code/serializer class, approved schema version |
| Retries/DLQ | Attempts, reason class, event ref, and outcome |

### 20.1. Kafka Deserialization Failures

A schema/serializer error can happen **before a valid Spring Message exists**. At that point there is no parsed payload to log safely; Kafka metadata, normalized exception class, and schema ID are enough for initial triage. Never turn on serializer DEBUG to dump bytes for every record.

### 20.2. Producer and Consumer May Be Separate Processes

Do not stuff full Spring Message headers/history into Kafka records just for debugging; propagate only **approved correlation/trace context** and contract fields. Producer and consumer logs should be joined by safe references rather than raw keys/values.

### 20.3. Exactly-Once Is Not Proven by Logs

A “Kafka send success” log does not prove the consumer committed to the database or that the event was not redelivered. Rely on producer acknowledgments, consumer offset/transaction semantics, idempotency/reconciliation, and dedicated business events when required.

## 21. JDBC/Database Adapter: SQL Parameters and Row Data

Database inbound/outbound adapters and gateways are often debugged via SQL logs, yet statements with bind parameters can expose:

- Emails, account numbers, payment details.
- Profile contents, names, addresses.
- Misplaced tokens/secrets in configuration tables.
- Queries carrying customer keys or sensitive values in WHERE clauses.

### 21.1. Safe Logging Approach

| Question | What to Log |
|---|---|
| Which query ran? | **Fixed query ID** or repository method |
| How long did it take? | Duration, timeout/lock wait |
| What happened? | Rows selected/updated/committed, transaction outcome |
| What failed? | Classified SQL state/error class |
| Which row failed? | Opaque record reference in protected logs |
| SQL parameter values? | **Do not log** by default |
| Entire ResultSet/Entity? | Never log |

### 21.2. Do Not Enable Global SQL Bind Logging for One Bug

ORM/JDBC drivers or proxies may print bind values at certain log levels. Review logger settings outside Spring Integration, especially if SQL TRACE was turned on during an incident. Rely on query IDs, timings, row counts, and error codes; if real row data is needed, inspect it via authorized database access under audit procedures.

### 21.3. Distinguish Transaction Outcomes

A handler log saying “DB update requested” does not prove the transaction committed. Pair it with actual JDBC update/transaction events or target business evidence. Never log raw rows just to prove an update occurred.

## 22. Logging in Error Channels and ErrorMessages

In Spring Integration, some failures route through `errorChannel` as `ErrorMessage`s, depending on endpoint, protocol, async/transaction configuration, and error handlers.

**Special risk:** an error message can contain:

- Exception messages/stack traces with payload fragments or URLs.
- The original failed message and all its headers.
- Failed delivery objects holding references to raw bytes.
- Broker record bodies, HTTP response bodies, or file paths.

### 22.1. Safe Error Logger Checklist

1. Log only **normalized exception class** and `reason_code` from a bounded taxonomy.
2. Log flow, endpoint, transport type, and attempt.
3. If the original message is attached, extract only **opaque IDs and safe metadata**—never stringify it.
4. Never call `Throwable.getMessage()` unless its contents are vetted.
5. Send detailed stack traces only to controlled sinks when policy allows; audit libraries that embed payloads into traces.
6. Separate transient, permanent, and unknown outcomes; never log every retry as a terminal failure.
7. Apply the same data-protection policy to DLQs and error queues as to the source.

### 22.2. Safe Error Event Example

~~~json
{
  "event": "INTEGRATION_PROCESSING_FAILED",
  "flow": "jms-invoice-import",
  "component": "validateInvoiceSchema",
  "error_class": "INVALID_SCHEMA",
  "attempt": 1,
  "terminal": false,
  "payload_kind": "json",
  "message_ref": "opaque-message-reference",
  "exception_type": "MessageConversionException"
}
~~~

This is an application-defined event; **`exception_type` should also be normalized/allowlisted** if exceptions from external dependencies can carry sensitive class names.

## 23. Splitter, Aggregator, Retry: Avoid Multiplying Sensitive Data in Logs

### 23.1. Splitter Fan-Out

A batch of 10,000 records can spawn 10,000 child messages. If full payload logging is enabled on handlers, the same kind of data is written repeatedly, multiplying cost and leak exposure.

**Log instead:** batch size, accepted/rejected counts, bounded error categories, verified correlation references, and overall completion.

### 23.2. Aggregator

An aggregator combines multiple messages; the resulting payload can contain **more sensitive data** than any single item. Never print the entire aggregate result to check group completion. Log group size, completion reason, elapsed duration, and outcome instead.

### 23.3. Retry

Repeated retries can log credentials/bodies on every attempt when logging is uncontrolled. Enforce rate limits, backoff, classified errors, and counters; sample logs **only after sanitization**.

### 23.4. PublishSubscribeChannel and ExecutorChannel

One message can traverse multiple branches or threads. Avoid logging raw payloads on both tap channels and business handlers; track per-branch outcomes via metadata and correlation. When using executors, verify **MDC/tracing context propagation** instead of copying all headers arbitrarily into log context.

## 24. Correlation IDs, Message IDs, and Tracing Context

### 24.1. Each ID Serves a Distinct Purpose

| Reference | Meaning | How to Log |
|---|---|---|
| Spring Message ID | Local message instance; may change when building new messages | Log if permitted by policy; never treat as cross-service ID |
| Correlation ID | Links messages/requests in the same workflow | Log only verified opaque IDs |
| Trace ID / Span ID | Links instrumented operations | Use supported tracing propagation |
| Business ID | Order/contract/customer ID | May be sensitive; map to an opaque reference if needed |
| Broker record identity | Kafka topic/partition/offset, JMSMessageID | Use within operational scope and policy |

### 24.2. Never Put Raw User Input into MDC

MDC and tracing baggage are typically attached automatically to every log in the same thread/context. If a web client sends `X-Correlation-ID` containing sensitive data or special characters, copying it straight into MDC broadcasts it across events. **Validate patterns, cap lengths, replace/issue internal IDs**, and tightly govern baggage allowlists.

### 24.3. Context Across Threads and Brokers

`ExecutorChannel` switches threads; queues and consumers also introduce execution boundaries. MDC is **thread-local logging context**, not equivalent to Spring Message headers. Use version-appropriate context propagation/tracing libraries to carry trace context when needed, and ensure context is **cleared/reset** after processing so correlation never leaks to another task.

## 25. MessageHistory and Payload Logging: Two Different Goals

Spring Integration supports `MessageHistory`, enabled via `@EnableMessageHistory` depending on version. History records metadata about traversed components when enabled and headers are preserved.

**History does not require printing payloads**, nor should history be exported externally over brokers or HTTP responses.

| Question | Preferred Observation Method |
|---|---|
| Which endpoints did the message visit? | Local MessageHistory, endpoint IDs, trace/log checkpoints |
| How long did the handler take? | Micrometer Timer/Observation |
| Was it sent to the broker? | Producer metrics/confirm callbacks |
| Why did the filter drop it? | Structured reason code, discard counter |
| Which file is still pending? | Authorized inventory + opaque file reference |
| Need to inspect specific payload? | Query authorized business store; never dump to logs |

### 25.1. Do Not Treat History as Trusted Input

History headers arriving from external sources can be spoofed or lost in serializers/mappers. Never use them to approve payments, enforce permissions, or decide validation passed. Safety of payload logging and authorization must rely on **policy, verified code, and trusted data sources**.

## 26. Metrics/Observation Replace Most Needs for Body Logging

Many operational questions are solved by metrics:

| Question | Appropriate Metric |
|---|---|
| Does file inbound have data? | Poll count, empty count, eligible files, oldest file age |
| Is SFTP disconnecting? | Session/transfer errors, retries, latency |
| Is HTTP outbound slow? | Request duration p95/p99, status class, timeouts |
| Are JMS/AMQP redeliveries happening? | Attempt/redelivery, requeue, DLQ |
| Is Kafka consumer lagging? | Lag, offset commits, DLQ, handler latency |
| Are JDBC updates slow? | Query/transaction duration, pool waits, lock errors |
| Is QueueChannel backed up? | Depth, oldest age, enqueue/dequeue rates |
| Are filters rejecting many messages? | Accepted/rejected counts by reason class |

Never enable full payload logging when **counters, histograms, queue age, and traces** pinpoint the issue. Protect metrics too: never use emails, filenames, record keys, correlation IDs, or full URIs as tags due to **high cardinality and data-leak risk**.

## 27. Logger and Appender Configuration: An Extra Layer of Defense

Logging config can cap verbosity per package/flow, yet **never replaces allowlist projections**.

Example `application.yml`:

~~~yaml
logging:
  level:
    root: INFO
    org.springframework.integration: INFO
    org.springframework.messaging: INFO
    com.example.integration: INFO
    com.example.integration.debug: OFF
~~~

Package names are illustrative; identify actual loggers and levels in your app. Setting `OFF` on one debug logger only silences that logger and **does not guarantee other frameworks refrain from logging bodies**.

### 27.1. Appenders and Collectors Also Need Controls

1. Restrict read access to stdout, container logs, and log aggregation.
2. Secure transport to collectors and encrypt storage per policy.
3. Separate audit logs from diagnostic logs when purposes/retention differ.
4. Enforce log rotation, size limits, sampling, and retention.
5. Protect debug consoles, remote IDE ports, support bundles, crash dumps, and profiling artifacts.
6. Audit log forwarding to third-party services.
7. Maintain procedures to investigate/purge/quarantine leaked log records per organizational process.

### 27.2. Guard Against Log Injection

Never concatenate untrusted strings directly into logs. Use structured/parameterized logging and **sanitize field values**, stripping or escaping CR/LF, excessive lengths, control characters, and field names. Parameterized loggers avoid unnecessary string formatting, yet **do not automatically mask PII** or block newlines.

## 28. Time-Bounded Debug Logging Controlled by Feature Flags

A sound operational design allows observing a flow briefly **without permitting raw body output**.

Illustrative logical config policy:

~~~yaml
integration:
  diagnostics:
    enabled: false
    flowAllowlist: []
    mode: METADATA_ONLY
    samplingRate: 0.01
    maxEventBytes: 2048
    expiresAt: null
    incidentRef: null
~~~

This is an **application-defined illustrative schema**, not built-in Spring Integration properties. Using it requires implementing configuration evaluation and event projection yourself.

### 28.1. Invariants to Enforce in Code

- `mode` offers no option to emit raw secrets.
- Flows activate only if listed in the allowlist with valid approval.
- `expiresAt` is enforced programmatically; once expired, it turns off automatically even if everyone forgets.
- Sampling/byte limits never exceed policy ceilings.
- Feature flags never alter redaction rules.
- Activation/deactivation logs include actor, timestamp, ticket, and scope.
- Every config change is reviewed and reversible.

### 28.2. Do Not Rely Only on Config Expiration

If a service does not reload config, an expired flag staying active creates risk. Enforce `expiresAt` at log-emission time or via controlled reconciliation, monitor debug event counts post-expiry, and alert on anomalies.

## 29. Automated Anti-Leak Testing

### 29.1. Required Test Fixtures

Construct **synthetic data** covering common leak vectors:

- JSON fields `password`, `accessToken`, nested `credentials.secret`.
- Synthetic email/phone/card-like strings, filenames containing personal info.
- Synthetic HTTP `Authorization` and `Cookie` headers.
- Kafka keys containing fake email strings, custom headers with tokens.
- JMS/AMQP properties with non-standard keys like `x-auth-secret`.
- Error messages embedding fake input fragments or URL queries with fake tokens.
- Binary payloads with recognizable byte markers and an `InputStream`.
- Oversized payloads, Unicode, newlines, and control characters.

**Never use real credentials** or production data to test safe logging.

### 29.2. Test Criteria

1. Safe projection outputs only approved fields.
2. Synthetic secret/PII fixtures **never appear** in log output.
3. Parse failures never fall back to raw logging.
4. Custom headers are not logged automatically.
5. Message `toString()` is never invoked to construct events.
6. Binary/stream payloads are never read for previews.
7. Flows/filters/retries still work when diagnostics are disabled.
8. Enabling/disabling diagnostics respects allowlists, TTL, and sampling.
9. When log sinks fail, behavior matches policy and increments dropped-log metrics.
10. Stress tests verify event size limits, throughput, and queue memory bounds.

### 29.3. Simple JUnit Example

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

class SafeJsonViewTest {
    @Test
    void extractsOnlyApprovedClassification() {
        String input = """
            {
              "eventType":"ORDER_RECEIVED",
              "schemaVersion":"v2",
              "customerEmail":"hidden@example.invalid",
              "paymentToken":"FAKE_SECRET_MARKER"
            }
            """;

        String safeView = SafeJsonView.eventType(input)
                + ":" + SafeJsonView.schemaVersion(input);

        assertTrue(safeView.contains("ORDER_RECEIVED"));
        assertTrue(safeView.contains("v2"));
        assertFalse(safeView.contains("FAKE_SECRET_MARKER"));
        assertFalse(safeView.contains("hidden@example.invalid"));
    }
}
~~~

This tests only the **projection function**, not other appenders or framework loggers. To catch real log leaks, integration tests should capture output from actual loggers, proxies/HTTP clients, error channels, and serializers using synthetic fixtures.

## 30. Testing Integration Flows with WireTap

### 30.1. Verify Both Directions

A WireTap is properly implemented when:

- The business branch still receives and processes messages unchanged.
- The logging branch emits events **containing only valid fields**, without mutating business payloads or headers.
- Logging failures never break business messages contrary to policy.
- Retries or circular channels never trigger infinite log loops.
- Flow/endpoint names and outcomes match the observed checkpoints.
- Log throughput and latency stay within bounds whether diagnostics are on or off.

### 30.2. Test Matrix

| Test Case | Simulation | Expectation |
|---|---|---|
| Happy path | Valid synthetic JSON | Flow succeeds; safe metadata logged |
| Invalid schema | JSON missing fields | Reason code logged, no raw input |
| Nested secret | Multi-level secret fields | Zero secret markers leaked |
| Unknown header | `x-custom-token` | Never logged |
| Stream payload | `InputStream` | Never consumed for preview |
| File payload | Path with fake customer name | Raw path never logged |
| HTTP error | Response body with fake token | Status/error class logged, no body |
| Broker retry | 10 attempts for same event | Rate/sampling respected; body never logged 10 times |
| Async channel | ExecutorChannel | Correlation contexts never mixed |
| Logger failure | Appender throws / queue full | Obeys error policy, dropped-log metric increments |
| Debug TTL | Past `expiresAt` | Elevated logging detail stops |
| Multiple subscribers | PublishSubscribeChannel | Accurate branch metrics, no duplicated raw logs |

## 31. Runbook LOG-01 — Investigating a Failed Message

**Scenario:** a customer reports a message never reached the target system, and operations does not want to turn on raw payload logging.

1. **Identify the flow and business event** via authorized opaque ID/ticket.
2. Check **metrics** for inbound adapter, QueueChannel, handlers, and outbound; pinpoint the last confirmed milestone.
3. Search **structured logs** by correlation/trace, status, error code, and endpoint.
4. If MessageHistory is enabled, inspect the local component path; never trust history as proof of remote commit.
5. At the adapter, inspect protocol-specific outcomes: SFTP transfer result, HTTP status, Kafka producer callback, JMS/AMQP ack/DLQ, JDBC transaction.
6. If still insufficient, request diagnostics with ticket/owner/TTL and **add only allowlisted fields**; never enable “temporary” raw body logging.
7. For timeouts with uncertain outcomes, **read back/reconcile** at the target before retrying to avoid duplicates.
8. Record conclusion, evidence, and preventive actions; turn off diagnostics and verify log volume returns to baseline.

### 31.1. Questions to Answer at Each Checkpoint

| Checkpoint | Question | Suggested Safe Log |
|---|---|---|
| Inbound | Was the message received? | Event type, source alias, accepted/invalid |
| Filter | Why was it discarded? | Bounded reason code |
| Transformer | Which schema/serialization failed? | Schema version, converter ID, error class |
| Router | Which branch was selected? | Fixed destination category |
| Queue | How long has it waited? | Queue age, depth metrics |
| Outbound | What did the target confirm? | Attempt, transport status, outcome type |
| DLQ | Is there data to replay? | Opaque event ref, reason, attempt |

## 32. Runbook LOG-02 — Sensitive Data Detected in Logs

**Trigger:** secret scanner, SOC, support, or owner finds passwords/tokens/PII in application logs, collectors, traces, or support bundles.

1. **Open a security incident**; never copy the sensitive value into tickets or chat. Record only log event ID, storage location, and timestamp.
2. Identify the **data type**, exposure start time, flow, logger, collector, who has read access, and downstream copies.
3. Per authority/risk level, **stop the emission source**, tighten sink access, or disable the leaking diagnostic mode without destroying forensic evidence.
4. For active credentials, **revoke/rotate at the issuer** and audit related sessions/tokens; deleting logs does not invalidate an exposed secret.
5. Preserve original evidence in an ACL-protected investigative store with retention per procedure; do not delete before SOC/Legal review.
6. Trace whether logs propagated to downstream SIEMs, search indexes, alert notifications, backups, external vendors, or support exports.
7. Coordinate with privacy/compliance to assess notification obligations if personal data was exposed.
8. Fix the root cause: safe projection, header allowlist, debug logger scope, appenders, parser error fallbacks, serializers/clients.
9. Verify no further leaks using **synthetic data**, validate deployment, and add regression guardrails.
10. Monitor post-remediation, record owners/evidence, and close the incident per policy.

### 32.1. Do Not Treat “Redacted in UI” as Sufficient

A logging UI may mask a string on screen while retaining raw events in underlying storage or export APIs. Inspect the **entire pipeline and all copies**, not just the display layer.

### 32.2. Do Not Arbitrarily Delete or Rewrite Logs

Logs may serve as forensic evidence or fall under legal hold. Quarantine, redaction, purging, or retention adjustments must follow organizationally authorized procedures to preserve audit integrity.

## 33. Audit Logging and Event Logging Are Not the Same

**Diagnostic logs** assist debugging, may be sampled, and carry short retention. **Audit events** confirm who did what, under what authority, when, on which resource, and with what outcome; they typically require integrity, retention, and independent traceability.

| Criterion | Diagnostic Logging | Audit Logging |
|---|---|---|
| Purpose | Debug/observe performance and errors | Accountability, control, compliance |
| Payload | No raw data by default | Stores only approved business details |
| Sampling | Allowed | Cannot arbitrarily drop mandatory events |
| Retention | Per operational need | Per legal/compliance policy |
| Integrity | Usually mutable | May require tamper-resistance, audit trail |
| Access | SRE/Dev per role | Authorized auditors/Security/owners |

A WireTap logging metadata **does not automatically become a trustworthy audit trail**. When transactions or authorization actions require mandatory auditing, design a contract-driven event store with transactions/idempotency rather than relying on async appenders that can drop logs.

## 34. Anti-Patterns and Improvements

| Anti-Pattern | Consequence | Replacement |
|---|---|---|
| `log.info("{}", message)` | Prints payload and headers depending on type | Safe projection with field allowlist |
| Enabling TRACE on all `org.springframework.*` | Data leak risk, log storm | Narrow scope, TTL, review specific loggers |
| Regex-masking password then logging raw JSON | Misses aliases/nested/encoded secrets | Omit/allowlist strictly by schema |
| Logging raw request when parse fails | Leaks payload precisely on errors | Error code and data-free fallback |
| Logging full SFTP filenames | Leaks paths/usernames/customers | Opaque file ref/alias |
| Logging HTTP headers/bodies | Leaks Authorization/Cookies/PII | Route template, status, duration |
| Logging Kafka keys/values | Leaks domain IDs and data | Topic alias, partition/offset, outcome |
| Logging JDBC bind values | Leaks rows and customer data | Query ID, row count, SQL state |
| Putting raw `correlationId` into MDC | Log injection / PII propagation | Validate/normalize/issue opaque ID |
| Dumping `ErrorMessage`/`originalMessage` | Prints raw failed payloads/headers | Exception class, reason, safe ref |
| Sampling before sanitization | Sampled events still contain raw data | Sanitize every event before emitting |
| Using debug logs as audit | Neither complete nor immutable | Dedicated policy-backed audit store |
| Forgetting to turn off diagnostics | Unnecessary long-term collection | Enforced TTL and monitoring |
| Unbounded logging branch | Heap growth, slows main flow | Queue/capacity/drop policy and metrics |
| Logging raw payload on broker retry | Repeats sensitive data thousands of times | Attempts/terminal outcome counters |

## 35. Practice Scenarios with Guided Resolutions

### Scenario A — HTTP Inbound Logs Full Bearer Tokens

A developer enabled logging for all request headers to debug HTTP 401; the log collector began receiving `Authorization`.

**Resolution:** stop the emission source, contain exposed records, and coordinate token revocation via SOC as needed; replace with status class, route template, and auth failure category. Add tests ensuring `Authorization` never appears in logs or traces.

### Scenario B — SFTP Parse Error Logs Customer Names

A parser failed on a filename like `customer-name_contract.pdf`; logs printed the full path and stack trace.

**Resolution:** use opaque file references, source aliases, size buckets, and `INVALID_DOCUMENT_FORMAT`. Look up the actual file through authorized storage; never log filenames/paths or contents to a shared SIEM.

### Scenario C — Kafka Consumer Encounters Invalid JSON

A deserializer threw an exception embedding a JSON snippet with fake emails and tokens. The logger printed `exception.getMessage()`.

**Resolution:** log normalized exception class/error code, safe schema ID, and policy-compliant topic/partition/offset, dropping raw exception messages. Test with synthetic secret markers and audit framework serializer logging.

### Scenario D — WireTap Slows Down the Payment Flow

A WireTap using `DirectChannel` invoked heavy loggers and formatters. P99 latency spiked when DEBUG was enabled.

**Resolution:** build only a minimal safe projection, measure overhead, consider bounded executors/queues with dropped-log metrics, and apply sampling/TTL; never let a debug branch bottleneck transactions.

### Scenario E — Logger Consumes the Entire InputStream

File inbound delivered a stream; a logging handler read 4 KB to preview it, starving downstream handlers.

**Resolution:** remove previews and use metadata; if business logic requires re-reading stream contents, implement caching/re-readable resources inside the processing flow with memory/disk bounds, never solely for logging.

### Scenario F — Logback DEBUG Is Off Yet Data Still Leaks

A framework `INFO` logger still printed `Message.toString()` in an error handler.

**Resolution:** do not rely only on logger levels; audit every sink across flows and error channels, replace with safe projections, test all paths, and review stack traces/callbacks/client logs.

### Scenario G — Correlation ID Contains Newlines

An HTTP caller sent `X-Correlation-ID` containing CR/LF and a string forged to look like a new log event.

**Resolution:** treat inbound correlation as untrusted input, issue an internal opaque ID or validate pattern/length, sanitize before putting into MDC/logs, and test against log injection.

### Scenario H — JMS Redelivery Causes Log Volume Spike

A PII-bearing message retried 500 times, logging the full body on every attempt.

**Resolution:** stop raw logging, use reason classes, retry/terminal counters, bounded backoff, and ACL-protected DLQs; handle exposed PII log records per incident policy. Never equate handler error count with failed business messages.

### Scenario I — Database SQL Logger Exposes Bind Params

Operations enabled SQL TRACE to debug a JDBC outbound gateway, and the SIEM ingested emails and account numbers.

**Resolution:** disable bind-value logging, log query IDs, SQL state, row counts, timings, and transaction outcomes; contain exposed logs and add configuration guardrails.

### Scenario J — Aggregator Logs the Entire Batch

An aggregator built a list of 10,000 records and printed `payload.toString()`, saturating the logging pipeline.

**Resolution:** log group size, completion reason, duration, rejected count, and safe correlation ref; clear the bulk log backlog and check for leaked data.

### Scenario K — Expired Debug Flag Still Active

Config included `expiresAt`, yet the service checked it only at startup, keeping debug enabled past expiration.

**Resolution:** enforce TTL at emission time or via safe refresh, monitor a `diagnostics_active` metric with overdue alerts, and verify return to baseline post-incident.

### Scenario L — Kafka → HTTP Cannot Link Traces

Producer and consumer emitted safe metadata logs, yet related requests could not be located on the HTTP target.

**Resolution:** propagate trace context/correlation via permitted header mappers, protect baggage, and never forward full payloads or Spring MessageHistory across services. Verify tracing across executors and consumers.

## 36. Implementation and Operations Checklist

### 36.1. Before Adding a Log Statement

- [ ] Defined purpose and checkpoint; checked whether metrics/traces suffice?
- [ ] Classified payload/headers; checked for secrets/PII?
- [ ] Can we log only event code, size bucket, schema version, and opaque ref?
- [ ] Which values are **external** and require validation/normalization?
- [ ] Used an allowlist with no object/`toString()` dumps?
- [ ] Checked risk of raw exception text, URLs, SQL params, or filenames?
- [ ] Confirmed log level and appenders are safe in production?

### 36.2. When Designing WireTap / LoggingHandler

- [ ] Log branch has a dedicated handler creating a safe projection?
- [ ] Business flow preserves original payload and header contracts?
- [ ] Evaluated sync/async, capacity bounds, and logger failure handling?
- [ ] Configured size limits, sampling, and rate limiting?
- [ ] Tested filters/routers/splitters/aggregators/retries and error channels?
- [ ] Prevented exporting raw history, raw headers, or credentials outside adapters?
- [ ] Established approval, TTL, and post-incident reset process for diagnostics?

### 36.3. Per Adapter Type

- [ ] File: no raw contents/paths; never consume streams to log.
- [ ] SFTP: no secrets, usernames/private keys, or sensitive remote paths.
- [ ] HTTP: no request/response bodies, Authorization, Cookies, or full URIs/queries.
- [ ] JMS: no `TextMessage`/raw properties; separate retries/redeliveries.
- [ ] AMQP: no bodies, sensitive headers; DLQ has ACLs and retention.
- [ ] Kafka: no record keys/values; track offsets/acks/outcomes properly.
- [ ] JDBC: no bind parameters/`ResultSet`; log query IDs and transaction status.
- [ ] Error flow: never dump original `Message` or raw exception bodies.

### 36.4. Before Release

- [ ] Ran leak tests with synthetic secret/PII fixtures.
- [ ] Reviewed framework log config, clients, serializers, tracing, and proxies.
- [ ] Verified no raw debug fallback on parse errors.
- [ ] Verified Actuator/log collectors have proper access control and retention.
- [ ] Measured log volume, latency, and dropped diagnostics.
- [ ] Prepared runbooks for secret/PII leaks in logs.
- [ ] Confirmed debug mode returns to baseline after drills/incidents.

## 37. Summary

**Controlled payload logging** does not mean masking a couple of fields and printing the rest. It is an **observability data contract**: deny sensitive contents by default, pick proper checkpoints, build **allowlist-based safe projections**, validate external headers, bound sizes/rates, secure log collectors, and govern temporary debugging operationally.

In **Spring Integration Adapters**, leak risks arise across inbound/outbound adapters, gateways, pollers, MessageChannels, WireTaps, LoggingHandlers, converters, error channels, underlying clients, and framework loggers. Each protocol—File, SFTP, HTTP, JMS, AMQP, Kafka, JDBC—has distinct metadata and confirmation boundaries; a “sent” log cannot replace proof that the target completed. A sustainable approach combines **structured metadata logs, local MessageHistory, correlation/tracing, Micrometer metrics, separate audits, and target verification**, while continuously testing that **no unauthorized secrets, PII, or raw payloads leak into telemetry**.
