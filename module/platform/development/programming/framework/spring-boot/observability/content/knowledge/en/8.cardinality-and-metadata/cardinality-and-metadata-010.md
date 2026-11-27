# Metadata size limits in Spring Boot Observability

In the **Cardinality and metadata** chapter of the **SPRING_BOOT_OBSERVABILITY** module, setting up observability does not stop at collecting **metrics, logs, and distributed tracing** with Micrometer Observation. In production environments, you must also control **the amount of metadata attached to each signal**: tag names/values, span attributes, trace events, log fields, and information propagated across services.

Metadata helps answer questions such as “which payment provider is slow?”, “at which stage did the error occur?”, or “which trace is this request linked to?”. However, an error field tens of kilobytes long, hundreds of attributes on a single span, or baggage propagated on every HTTP request can inflate costs, get truncated by the backend, slow down the application, and accidentally leak sensitive information.

**Goal:** design limits on **field count, individual field length, total size, distinct value count, and propagation scope**; enforce them close to the origin; and verify limits across the SDK, collector, and backend.

## 1. Distinguishing metadata size from cardinality

These two concepts are related yet solve different problems.

**Metadata size** describes the storage footprint/complexity of data attached to *a single* signal. It can be measured by:

- **Field count:** how many attributes/events a span has; how many keys a log has; how many labels a metric has.
- **Length of a key/value:** how many characters or **UTF-8 bytes** a string takes.
- **Total record size:** the total serialized size of a log event, span, or HTTP header.
- **Depth/structure:** nested objects, large arrays, stack traces, and linked lists.

**Cardinality** measures the number of **distinct values or label combinations** that can occur, which matters most for time-series metrics.

| Case | Main issue | How to handle |
| --- | --- | --- |
| `order.id` is a 10-character code with millions of values | Extremely high cardinality despite short value | Do not use ID as a metric label; keep in traces/logs only if genuinely needed and permitted |
| An `error.message` tag 30 KB long | Both huge and high cardinality; may leak data | Never use verbatim as a tag; map to a finite error code |
| A span with 600 attributes, 8 bytes each | Large attribute count even though each value is short | Cap attribute count and keep only fields useful for investigation |
| A log containing a 2 MB request body | Huge event size and potential PII | Do not log bodies by default; store needed data in an appropriate place |
| `provider=bank_a/bank_b` and `outcome=ok/error` | Low cardinality, small size | Suitable for metric breakdown |

A **256-byte/value limit does not make `userId` a low-cardinality tag**. Conversely, a four-value enum can still be wasteful if each value name gets concatenated with a giant description.

### Bytes, characters, and string length

In Java, `String.length()` counts **UTF-16 code units**, not the number of bytes when data is transmitted as UTF-8. Vietnamese characters and emojis can consume more bytes than ASCII characters. For example, the string `"đỏ"` has two visible characters yet requires five UTF-8 bytes (`đ` takes two bytes and `ỏ` takes three bytes).

When a limit imposed by an HTTP proxy, collector, or backend is measured in **bytes**, measure the bytes of the actual wire representation. Slicing with `substring(0, 256)` only guarantees a count of UTF-16 code units; it may still exceed a 256 UTF-8 byte budget. Nor should you arbitrarily slice a byte array in the middle of a multi-byte character and decode it back, as that can produce replacement characters.

## 2. Where does metadata live?

In a Spring Boot application using Micrometer Observation, metadata can pass through multiple layers:

```text
Spring Boot service / HTTP / job / message consumer
                |
                v
     Observation.Context + KeyValues
                |
                +--> metric handler --> MeterRegistry --> exporter/scraper
                |                                       --> time series backend
                |
                +--> tracing handler --> span attributes/events/links
                |                       --> tracing SDK/exporter/collector
                |                       --> tracing backend
                |
                +--> logs (explicitly written by app) --> encoder/shipper/backend
                |
                +--> propagation context --> HTTP/message headers --> other services
```

Not all data in `Observation.Context` is exported as metadata. Conventions, filters, and handlers decide which key-values are processed. Likewise, creating a span does not mean the exporter retains all attributes: the SDK, collector, or backend may cap, truncate, or drop data.

| Signal | Typical metadata | Limits to manage |
| --- | --- | --- |
| Metrics | Metric name, label keys/values, resource tags | Label count, length, **value combinations**, series count |
| Traces | Span attributes, events, links, status, error details | Attribute count, attribute length, event/link count, export payload |
| Logs | Message, structured fields, MDC, stack trace | Event size, field lengths, field count, sensitive data |
| Propagation | `traceparent`, `tracestate`, baggage, or custom headers | Total HTTP/message header size, entry count, and hop spread |

Each layer has its own policy. **There is no single Spring Boot configuration property** that guarantees bounds across all four places.

## 3. Metrics: keep labels short, finite, and meaningful

For metrics, prioritize **cardinality** before counting label length. Time series count usually grows with the product of choices per label. If a metric has labels:

- `provider` with 3 values;
- `outcome` with 4 values;
- `region` with 5 values;
- `order_id` with 100,000 values;

then the theoretical combination count is **3 × 4 × 5 × 100,000 = 6,000,000** (before other infrastructure labels). Capping `order_id` length at 24 bytes **does not reduce the number of combinations**.

Design rules:

1. **Do not put** order IDs, user IDs, emails, tokens, raw URLs/query strings, or exception messages into low-cardinality metric tags.
2. Pick values from an **enum/allowlist**, e.g., `provider=bank_a/bank_b/other`, `outcome=success/declined/error`.
3. Keep label names short and stable; never generate dynamic keys from product names or input data.
4. Budget **label count and distinct value count**, and define a policy for unexpected values.
5. Check series counts in the metrics backend after deployment; evaluate changes across versions, instance counts, and environments.

### Example: mapping external errors into controlled categories

Do not turn `providerException.getMessage()` directly into a tag. Substitute an internal error code:

```java
import java.util.Locale;
import java.util.Set;

public final class PaymentTelemetry {
    private static final Set<String> KNOWN_ERROR_KINDS =
            Set.of("timeout", "rate_limited", "unavailable", "invalid_response");

    private PaymentTelemetry() {}

    public static String errorKind(String providerCode) {
        if (providerCode == null) {
            return "unknown";
        }
        String normalized = providerCode.trim().toLowerCase(Locale.ROOT);
        return KNOWN_ERROR_KINDS.contains(normalized)
                ? normalized
                : "other";
    }
}
```

With an Observation:

```java
observation.lowCardinalityKeyValue(
        "payment.error_kind", PaymentTelemetry.errorKind(providerErrorCode));
```

Unexpected values roll into `other` instead of creating unbounded series. Still, **do not ignore an unusual spike in `other`**: have a way to detect/inspect errors outside high-cardinality metric labels, such as controlled diagnostic logs.

### MeterFilter is the last line of defense, not a substitute for label design

Micrometer provides `MeterFilter` to govern metric names/tags and cap how many tag values a registry accepts. For example:

```java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.config.MeterFilter;
import org.springframework.boot.actuate.autoconfigure.metrics.MeterRegistryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class MetricsProtectionConfiguration {

    @Bean
    MeterRegistryCustomizer<MeterRegistry> limitProviderValues() {
        return registry -> registry.config().meterFilter(
                MeterFilter.maximumAllowableTags(
                        "payment.authorize", "payment.provider", 12,
                        MeterFilter.deny()));
    }
}
```

This example caps **12 distinct values of the `payment.provider` tag** on meters whose names start with `payment.authorize`. When exceeded, the `MeterFilter.deny()` fallback can cause **new meters to be rejected**, resulting in lost data for those series. This is a safety net against misconfiguration; normalize values at the source first and monitor meter-denial events. This filter **is not a mechanism for capping byte length of tag strings**.

## 4. Traces: limiting attributes, events, and error details

A custom observation can emit spans through a tracing bridge/handler. Micrometer's `lowCardinalityKeyValue(...)` entries are usually used by handlers for both metric tags and trace attributes; `highCardinalityKeyValue(...)` entries are normally used only for trace context in standard handlers. Exact handling depends on the handler, bridge, and version.

Data groups that need dedicated budgets:

| Trace component | Risk when oversized | Control approach |
| --- | --- | --- |
| Span attributes | Heavy spans; SDK may drop attributes past count limits | Keep only diagnostic fields; limit count and value length |
| Span events | One request emits thousands of events | Record only key business milestones; cap event count |
| Span links | Fan-out or batch generates huge link counts | Keep essential links; cap link count |
| Exception details | Very long stack traces, cause chains, or exception messages | Use short error kinds for classification; keep error details controlled |
| Span name | Embedding IDs or raw URLs hinders aggregation | Stable operation names like `payment.authorize` |

The OpenTelemetry SDK has limits such as **max attributes per span, max attribute-value length, max events, max links**. Depending on how the SDK is initialized, these can be configured via SDK builders or autoconfigure mechanisms. For instance, in a system **actually using OpenTelemetry SDK autoconfigure**, you might consider variables such as:

```text
OTEL_SPAN_ATTRIBUTE_COUNT_LIMIT=32
OTEL_SPAN_ATTRIBUTE_VALUE_LENGTH_LIMIT=256
OTEL_SPAN_EVENT_COUNT_LIMIT=16
OTEL_SPAN_LINK_COUNT_LIMIT=16
```

These are **illustrative policy values**, not mandatory defaults of OpenTelemetry or Spring Boot. They take effect only when the specific SDK/autoconfigure supports and reads them; a Spring Boot app using the **Brave bridge**, or a custom-built SDK, does not automatically receive the same policy. SDK limits also **do not directly govern tags in `MeterRegistry`, structured logs, or baggage**.

If an attribute is truncated or dropped, check how the SDK handles it, whether dropped attributes/events are counted, and whether the backend enforces a secondary limit. Collector configurations can strip additional data after it leaves the JVM.

## 5. Logs: avoid turning business payloads into giant records

Structured logs help explain **why** a step failed, but a record containing request/response bodies, lists of thousands of items, or repeated stack traces can exceed log shipper and storage thresholds. Those components may truncate strings, split records, or reject ingestion depending on configuration.

A good log for a payment error typically only needs fields like:

```json
{
  "event": "payment.authorization_failed",
  "provider": "bank_a",
  "error_kind": "timeout",
  "retryable": true,
  "duration_ms": 812
}
```

If tracing and MDC correlation are configured, `traceId`/`spanId` can be added by the logging pipeline to cross-reference the trace; there is no need to dump the entire trace context or raw headers into every log.

Best practices:

- Use short error classification codes; log exceptions intentionally and avoid repeating stack traces at every layer.
- Cap free-form field lengths **before encoder serialization**; consider capping total log event size.
- Never log passwords, tokens, cookies, card numbers, or full request bodies simply because you are debugging.
- When data must be truncated, include a controlled marker such as `truncated=true` or the initial byte count within a sensible range so investigators know the record is incomplete.
- Route large audit-grade records to dedicated storage with appropriate authorization/reference schemes rather than stuffing them into telemetry.

Not every failure needs a massive event. Quantitative signals like error rate belong in metrics; step relationships belong in traces; technical/domain decision details belong in logs.

## 6. Context propagation and baggage: limits must include the wire path

Distributed tracing links requests across services via propagation mechanisms such as **W3C Trace Context** with `traceparent`/`tracestate` when supported by the stack. **Baggage** is a separate mechanism to carry selected key-values with the distributed context; it is not a store for full business payloads.

A baggage value can be sent repeatedly across many HTTP calls or messages. If 1 KB of baggage traverses many hops and fan-out calls, bandwidth and processing overhead multiply with each transmission. Worse, baggage crossing trust boundaries can expose data in headers.

Practical rules:

1. **Do not propagate** user profiles, session tokens, emails, order contents, or raw exceptions via baggage.
2. Pick only fields genuinely required downstream, with an attribute allowlist and length caps; prefer short classification metadata.
3. Distinguish **trace IDs** generated by tracing from business IDs: propagate standard trace context, never hand-craft trace headers.
4. Check **total header size** permitted by reverse proxies, gateways, brokers, or HTTP clients. Exceeding limits can cause requests to be rejected before reaching the application.
5. When suspecting metadata size broke propagation, check downstream parent/child spans and log correlation rather than only checking for HTTP 200.

Mid-flight baggage truncation can corrupt semantics; keeping it small and explicit at the source is better. Key names, encoding, and standard/SDK limits must be verified against the actual propagator deployed.

## 7. Setting metadata budgets by signal type

No single number fits every application. The following table illustrates **internal starting targets for evaluation**, **not default limits** or mandatory Micrometer rules:

| Target | Example budget | How to verify and react |
| --- | --- | --- |
| Team-added low-cardinality metric labels | Max 6 keys; every value from enum/allowlist | Check value sets and series count; unknown values roll into `other` |
| Custom-instrumentation span attributes | Max 16 fields; strings max 128 UTF-8 bytes | Drop minor fields, keep error codes; SDK may apply additional overall limits |
| Business span events | Max 8 events per operation | Emit events only on state transitions valuable for investigation |
| Typical application log event | Target max 4 KiB serialized | Trim fields, omit bodies; exceptions follow a dedicated policy |
| Application-defined baggage | None by default; at most a few short keys if truly required | Allowlist, verify encoding and total headers |

With these illustrative figures, clarify:

- 128 **UTF-8 bytes per value** does not mean a 128-byte max span; there are also key names, multiple attributes, events, and protocol metadata.
- 4 KiB **per log event** does not guarantee 4 KiB on the wire after encoding/compression or shipper-added metadata.
- Limiting **field count** differs from limiting **distinct value count** across records. Metrics need both.
- Environments may have different policies, but those must be verified against the real backend and governed like a telemetry contract.

Prefer establishing budgets by **observing record size distributions**, vendor limits, and acceptable operational capacity. When trimming, decide whether to *reject*, *normalize*, *truncate*, or *drop* so the most critical data survives.

## 8. Java example: safely truncating strings by UTF-8 bytes

When a field is **approved for export** yet has variable length, you can truncate it by UTF-8 byte count by iterating over Unicode code points. This avoids slicing inside a multi-byte character:

```java
import java.nio.charset.StandardCharsets;

public final class TelemetryText {
    private TelemetryText() {}

    public static String limitUtf8Bytes(String value, int maxBytes) {
        if (value == null || maxBytes <= 0) {
            return "";
        }
        StringBuilder result = new StringBuilder();
        int usedBytes = 0;
        for (int offset = 0; offset < value.length();) {
            int codePoint = value.codePointAt(offset);
            String piece = new String(Character.toChars(codePoint));
            int nextBytes = piece.getBytes(StandardCharsets.UTF_8).length;
            if (usedBytes + nextBytes > maxBytes) {
                break;
            }
            result.append(piece);
            usedBytes += nextBytes;
            offset += Character.charCount(codePoint);
        }
        return result.toString();
    }
}
```

Example when capping an **application-generated diagnostic hint approved for export**:

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

public void recordPaymentFailure(
        ObservationRegistry registry,
        String approvedDiagnosticHint,
        Runnable action) {

    String hint = TelemetryText.limitUtf8Bytes(approvedDiagnosticHint, 128);

    Observation.createNotStarted("payment.failure.review", registry)
            .lowCardinalityKeyValue("failure.category", "provider")
            .highCardinalityKeyValue("diagnostic.hint", hint)
            .observe(action);
}
```

**Important:** truncation **does not make data safe**. If `approvedDiagnosticHint` contains a password, token, PII, order ID, or an error message containing a sensitive body, truncating to 128 bytes can still expose it. Use this helper only after **classifying, authorizing, and sanitizing data at the source**. Furthermore, high-cardinality attributes must not be turned into metric tags by custom conventions/handlers.

This illustrative function only addresses **the length of a single string**. It does not cap **attribute count**, **total span size**, **log field count**, or **total baggage headers**. Nor does it replace configuring SDK/backend limits.

### When should you not truncate?

Do not truncate an **identifier requiring exact matching** and use the result as a join key: two distinct IDs can share the same prefix after truncation. It is better not to export the ID if unnecessary; when cross-referencing is truly required, use a policy-approved field with controlled format/length stored in the appropriate channel. Hashing an ID does not solve cardinality or re-identification risks either.

## 9. How do limits at source, SDK, collector, and backend differ?

Multiple coordinated control layers are usually needed:

| Layer | Responsibility | Limits to remember |
| --- | --- | --- |
| **Code and ObservationConvention** | Export only needed metadata, normalize enums, keep sensitive data out of key-values | This layer understands business semantics best |
| **ObservationFilter/MeterFilter** | Adjust context/tags or protect meter registry | A filter cannot make arbitrary log/trace payloads safe with a single rule |
| **Tracing SDK** | Cap attributes/events/links and span field sizes | Does not automatically cap metric labels, baggage, or log messages |
| **Exporter/collector** | Control ingestion, processors, sampling, redaction, transforms | Data has already consumed app/network resources before arriving here |
| **Backend** | Cap ingestion/time series/event size and retention | Backend dropping or truncation can lose investigative detail |
| **Gateway/proxy/broker** | Cap header/message size | Oversized propagation metadata can break the transaction itself rather than just losing telemetry |

For example, if a span carries 400 custom attributes, the collector might drop 350 attributes on ingest. Yet the application already built the context, serialized/exported the initial payload, and paid the overhead. Enforcing limits **right in code** still matters even when the backend enforces quotas.

For logs, log shippers behave differently from tracing SDKs: some pipelines **truncate or drop an entire event** when oversized. Monitor dropped-log counts and ingestion-error alerts. Never treat an unfound log as proof that code didn't execute.

## 10. Applying to error, latency, and linked-trace investigations

Suppose an order flow runs:

```text
POST /checkout
   |
   +-- inventory.reserve        [business span]
   |      +-- database call     [infrastructure span if instrumented]
   |
   +-- payment.authorize        [business span]
          +-- provider HTTP     [client span if instrumented]
```

A useful, compact metadata set:

| Signal | Metadata to keep | Avoid |
| --- | --- | --- |
| HTTP metrics | `uri` as route template, `status`, `method` | Full URL with order ID/query |
| `inventory.reserve` | `warehouse.tier=primary/secondary`, `outcome=reserved/out_of_stock/error` | Cart dump or item list |
| `payment.authorize` | `provider=bank_a/bank_b`, `outcome=approved/declined/error` | Payment token, raw card info |
| Business trace | Step boundaries and durations, normalized error info | Unfiltered verbatim exception messages |
| Error log | `event`, `error.kind`, `retryable`, `traceId`/`spanId` when correlated | Sensitive request body and headers |
| Propagation | Standard trace context, minimal baggage only when truly needed | Entire user profile |

When `payment.authorize` fails, metrics detect error rates by provider; traces pinpoint the slow outbound call; logs confirm the technical error kind. If metadata is improperly truncated, investigations can still fail even when all three systems are collecting data.

Distinguish **sampling** from size limits: a sampler may skip a trace, while a retained trace may still lose attributes due to quota truncation. Broken context propagation can also detach child spans from parent spans. Check each cause individually instead of blaming “the backend lost data.”

## 11. Workflow to verify and monitor the metadata budget

Before shipping a metadata policy to production, run at least these steps:

1. **Inventory exported fields:** across HTTP, custom observations, logs, tracing attributes/events, and baggage. Identify origin, purpose, and owner.
2. **Classify sensitivity:** accounts, credentials, personal data, business IDs, free-form payloads; remove or sanitize before applying length limits.
3. **Measure real samples:** attribute/log-field counts, UTF-8 byte distribution, series count per label, header sizes, and dropped/truncated record rates.
4. **Set explicit budgets:** counts, bytes/value, total event size, distinct values, retention; clearly distinguish illustrative targets from backend-enforced hard limits.
5. **Normalize at the source:** enums/allowlists, stable key names, route templates, finite error codes, and no default body logging.
6. **Configure defensive layers:** meter filters, tracing SDK, collector, log pipeline, and gateway matching your stack.
7. **Verify signal correlation:** from a latency/error alert, locate the span, log, and downstream service; test async/queue paths and sampling too.
8. **Monitor post-release:** time series, dropped spans/attributes/logs, ingest failures, telemetry latency, CPU/memory, and cost.

### Minimum test matrix

| Scenario | Expected behavior |
| --- | --- |
| Short ASCII value in allowlist | Preserved and exported accurately |
| Vietnamese/emoji value near byte limit | Does not exceed UTF-8 budget; emits no corrupted characters |
| Provider returns unknown error code | Low-cardinality tag maps to `other`; no unbounded values created |
| Long exception message containing sensitive data | Never emitted verbatim to metric/trace/log; uses safe classification code |
| Span with too many attributes/events | Essential fields preserved; SDK/backend drop/truncation observable if supported |
| Oversized log event | Pipeline truncates/drops per verified policy; does not lose all vital error info |
| Oversized baggage/header | Prevented at source; does not cause HTTP/message rejection due to headers |
| Trace dropped by sampling | Metrics still exist when metric handler is active; not mistaken for attribute loss |
| Task runs on another thread/service | Parent-child trace and log correlation work when context propagation is configured |

A crucial check is comparing **data attached in code** against **data actually visible in the backend**. If code attaches 15 attributes but the backend shows only 10, trace SDK → exporter → collector → backend to locate the limit causing truncation or dropping. If metric series jump suddenly, find the label receiving many new values rather than merely shortening string lengths.

## 12. Hands-on exercise

A Spring Boot service processing 10,000 orders/day currently has these telemetry fields:

```text
Metric: checkout.duration
  tags: outcome, provider, orderId, errorMessage

Trace span: checkout
  attributes: provider, fullRequestBody, paymentToken,
              retryCount, failurePhase, errorMessage

Log: "checkout failed: " + fullExceptionStack

Propagation baggage:
  userProfileJson, orderId
```

Propose how to cut size and cardinality while preserving the ability to investigate errors, latency, and cross-service links. One reference solution:

1. **Metric:** keep `outcome` and normalized `provider`; remove `orderId` and `errorMessage`; if error classification is needed, add `error.kind` from an allowlist.
2. **Span:** keep `provider`, `retry.count`, and `failure.phase`; drop `fullRequestBody` and `paymentToken`; use only approved error codes/diagnostic hints with byte and attribute-count caps.
3. **Log:** write a structured event with error kind, retryability, and trace correlation. Log exception details selectively, avoiding duplication and keeping secrets out.
4. **Baggage:** drop `userProfileJson`; do not propagate `orderId` by default. Use standard trace context propagation; add baggage only where downstream need is proven.
5. **Infrastructure:** check the SDK, collector, exporter, log pipeline, gateway, and metrics backend to confirm policies are genuinely enforced.

**Conclusion:** Metadata size limits are an integral part of observability design, not merely a quota setting. With Micrometer Observation in Spring Boot, emit **minimal metadata with clear semantics**: finite metric labels, right-sized trace attributes/events, structured and safe logs, and minimal baggage. Combining source normalization, SDK/backend caps, and end-to-end verification across metrics–logs–traces keeps the system rich enough for investigations without being overwhelmed by metadata.
