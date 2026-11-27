# Mapping Errors and Diagnostic Information

## 1. The problem: a conversion error masked by a generic exception

A system receives order events from a partner and translates them into a canonical message for Pricing/Inventory:

~~~json
{
  "schemaVersion": "2",
  "eventId": "EV-701",
  "orderId": "O-701",
  "currency": "USD",
  "totalAmount": "129.99",
  "createdAt": "2026-11-20T09:30:00Z"
}
~~~

The Message Translator converts the payload into `CanonicalOrder`. Occasionally, however, the producer sends:

~~~json
{
  "schemaVersion": "2",
  "eventId": "EV-702",
  "orderId": "O-702",
  "currency": "USD",
  "totalAmount": "one hundred",
  "createdAt": "2026-11-20T09:30:00Z"
}
~~~

If the Transformer merely throws `NumberFormatException`, the dashboard might record:

~~~text
ERROR: Message handling failed
Caused by: NumberFormatException
~~~

That tells you nothing about **which source/schema failed, which field is wrong, whether the error is retryable, which endpoint processed the message, or what data needs fixing**. Conversely, logging the entire payload for diagnostics can leak emails, addresses, payment details, or tokens.

A much more useful error record:

~~~text
outcome=REJECTED_PERMANENT
stage=FIELD_CONVERSION
reasonCode=INVALID_AMOUNT_FORMAT
fieldPath=totalAmount
sourceSystem=PARTNER_A
sourceSchemaVersion=2
eventId=EV-702
endpoint=translator.partner.v2
retryable=false
~~~

**Message Translator** is the component converting a message's representation, typically via a **Transformer** in Spring Integration. It must either translate **according to contract or report a structured error**; never convert invalid data into fake valid values or retry infinitely when an error cannot heal itself.

~~~mermaid
flowchart TD
    SRC["Partner event"] --> DEC{"Decode + validate source contract"}
    DEC -->|"Raw/schema error"| INGRESS["Ingress rejection"]
    DEC -->|"Valid"| TRANS["Message Translator / Transformer"]
    TRANS -->|"Mapping OK"| CAN["CanonicalOrder"]
    TRANS -->|"Mapping error"| CLASS{"Classify"}
    CLASS -->|"Permanent input"| REJECT["Reject / quarantine / typed error"]
    CLASS -->|"Transient dependency"| RETRY["Bounded retry"]
    CLASS -->|"Mapper defect"| ALERT["Error channel + alert"]
    CAN --> DOWN["Business flow"]
~~~

This lesson belongs to the **Message translator** chapter of module **SPRING_INTEGRATION_PATTERN**. The module focuses on implementing Enterprise Integration Patterns with Spring Integration to build loosely coupled, extensible message flows, practicing **Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation**, while testing and observing processing branches.

**Goal:** identify every category of mapping error, build a safe diagnostic contract, implement a Java Transformer and Spring Integration Java DSL flow, understand `MessagingException`/`ErrorMessage` and sync–async boundaries, decide retry/DLQ/Gateway responses, preserve correlation, and test both errors and diagnostics.

## 2. What does a Message Translator convert—and what does it NOT solve?

In Enterprise Integration Patterns, a **Message Translator** converts a message into a format understood by the receiver. Example:

~~~text
PartnerOrderV2
  orderId
  currency
  totalAmount: "129.99"
  createdAt: ISO string

→ Message Translator

CanonicalOrder
  businessId
  money(currency, BigDecimal)
  orderedAt: Instant
~~~

Conversion can include **renaming fields, converting types, normalizing units, restructuring nested objects, mapping enums, parsing timestamps**, and preserving essential metadata.

**Not automatically the Translator's job:**

- Authorizing all business permissions in place of the security layer.
- Fixing bad data by guessing amounts or currencies.
- Retrying external services infinitely.
- Minting a new correlation ID on every attempt.
- Guaranteeing exactly-once execution for downstream side effects.
- Merging multiple messages like an Aggregator.
- Routing across multiple input schemas without a configured Router.

**With multiple source formats**, the **Normalizer** pattern is typically a **Router + multiple Message Translators/Transformers** emitting one canonical contract. Mapping errors must be tagged with the **exact source and version**, not just the Transformer class name.

## 3. An actionable mapping error taxonomy

| Error category | Example | Stage | Retry same message? |
|---|---|---|---|
| **DECODE** | Bad JSON syntax, corrupted bytes/encoding | Before or at inbound adapter | No, if bytes are unchanged |
| **UNSUPPORTED_SCHEMA** | `schemaVersion=9`, only 1/2 supported | Router/contract validation | Do not hot-retry |
| **MISSING_REQUIRED_FIELD** | Missing `orderId` | Field extraction | No |
| **EXPLICIT_NULL_NOT_ALLOWED** | `currency:null` | Source contract validation | No |
| **INVALID_FIELD_TYPE** | `totalAmount: []` | Decode/field extraction | No |
| **INVALID_FIELD_FORMAT** | `"one hundred"` as amount | Conversion | No |
| **OUT_OF_RANGE** | Negative quantity, amount over cap | Conversion/validation | No |
| **UNKNOWN_ENUM_VALUE** | Unaccepted currency/code | Mapping/domain contract | No, unless contract upgrades |
| **AMBIGUOUS_MAPPING** | Both fields present and conflicting | Schema migration | Never guess |
| **ENRICHMENT_UNAVAILABLE** | Lookup service returns 503 | External dependency | Conditionally, with backoff |
| **UNKNOWN_REMOTE_OUTCOME** | Lookup/remote mutation times out after possible commit | External boundary | Reconcile before blind retry |
| **MAPPER_DEFECT** | `NullPointerException` from mapping bug | Code/application | Never misclassify as bad input |
| **RESOURCE_EXHAUSTED** | Oversized message / CPU limit | Ingress/quota/infrastructure | Classify by root cause |

**Permanent** means retrying **the same payload with the same mapper version** cannot fix it automatically; it does not forbid reprocessing after the producer corrects the data or the application updates its schema.

**Transient** means the cause may recover without changing the payload. Yet the outcome of a call with side effects can sometimes be **unknown**—never assume a timeout means it is safe to re-send a risky operation.

## 4. Does the error occur before or inside the Translator?

A raw JSON body might be truncated:

~~~text
{"orderId":"O-701","totalAmount":
~~~

Jackson or the message converter can throw **before Spring Integration ever constructs a `Message<?>`**. In that case, `@Transformer` and an `IntegrationFlow`'s `errorChannel` may **never be invoked**.

Layering:

~~~mermaid
flowchart LR
    BYTES["Raw bytes"] --> CONV["Deserializer / Converter"]
    CONV --> OBJ["Source DTO / JsonNode"]
    OBJ --> MAP["Translator / Transformer"]
    MAP --> CAN["Canonical DTO"]
    CAN --> HANDLER["Business handler"]
    CONV --> ERR1["Adapter/container error handling"]
    MAP --> ERR2["Messaging exception boundary"]
    HANDLER --> ERR3["Business/error boundary"]
~~~

Handle errors at the **exact boundary**:

- HTTP: controller/converter error mapping.
- Kafka/AMQP/JMS: deserializer, listener container, and adapter recoverer.
- Spring Integration `Transformer`: endpoint message-handling exception.
- Business handler: domain or infrastructure failures after mapping.

A unit test passing valid Java objects directly to a mapper **does not prove** how the adapter handles malformed raw bytes.

## 5. Diagnostics must answer six questions

A useful diagnostic identifies:

1. **Where did it fail?** Endpoint, stage, source schema/version.
2. **What failed?** Stable reason code, error category, and field path.
3. **Which input?** Trusted event ID and transport reference, if available.
4. **Which logical work?** Tenant, business correlation ID, group/member ID (once verified).
5. **Can it proceed?** Retryable, permanent, or unknown outcome.
6. **What did the system do?** Rejected, retried, quarantined, failed, ACKed, or sent to reconciliation.

Not every error has every field. Unparsed raw bytes may lack an `eventId`; never set `eventId="UNKNOWN"` and use it as an idempotency or correlation key across thousands of failed messages.

**Reason codes plus sufficient metadata** is the goal. Raw payloads and full stack traces belong in **protected logs/quarantine**, never pushed automatically into public replies or metric tags.

## 6. Reason code catalog instead of relying solely on exception text

Example set of reason codes:

| Error code | Meaning | Stage |
|---|---|---|
| `UNSUPPORTED_SCHEMA_VERSION` | Unsupported version | Contract |
| `MISSING_ORDER_ID` | Missing required order ID | Extraction |
| `NULL_CURRENCY` | Null currency when contract requires it | Extraction |
| `INVALID_AMOUNT_TYPE` | Amount has disallowed JSON type | Extraction |
| `INVALID_AMOUNT_FORMAT` | Amount string cannot be parsed | Conversion |
| `AMOUNT_OUT_OF_RANGE` | Monetary value exceeds range | Validation |
| `INVALID_TIMESTAMP` | Timestamp violates ISO/offset format | Conversion |
| `CURRENCY_NOT_SUPPORTED` | Currency outside business allowlist | Domain mapping |
| `CONFLICTING_FIELDS` | Old and new fields contradict each other | Migration |
| `UNTRUSTED_SOURCE_IDENTITY` | Untrusted source/tenant metadata | Security boundary |
| `MAPPING_DEPENDENCY_TIMEOUT` | Dependent service timed out | Enrichment |
| `MAPPING_INTERNAL_ERROR` | Unexpected code defect | Translator |

**Code naming** should be independent of Java exception class names, Jackson internals, and display languages. User-facing text can be localized while `reasonCode` stays stable for integrations and dashboards.

Catalogs require versioning when external consumers rely on error codes. Never dynamically build codes from raw user-supplied field names without validation (which explodes cardinality or leaks data).

## 7. Example data model: source and canonical

Java 17+:

~~~java
record PartnerOrderV2(
    String schemaVersion,
    String eventId,
    String orderId,
    String currency,
    String totalAmount,
    String createdAt
) {}

record CanonicalMoney(
    Currency currency,
    BigDecimal amountMajor
) {}

record CanonicalOrder(
    String tenantId,
    String eventId,
    String orderId,
    CanonicalMoney total,
    Instant orderedAt,
    String sourceSystem,
    String sourceSchemaVersion
) {}
~~~

These are **application DTOs**, not built-in Spring Integration classes. `totalAmount` is a wire string to make format errors clear; if a producer sends JSON numbers, the deserializer/schema must govern type handling (never coerce arrays/objects into strings).

`tenantId` is not read arbitrarily from a client-declared header. The example uses `verifiedTenantId` authenticated by the inbound adapter/security layer; in multi-tenant systems, identity errors must stay distinct from format mapping errors.

## 8. Diagnostic record without raw payloads

~~~java
enum MappingStage {
    CONTRACT, FIELD_EXTRACTION, FIELD_CONVERSION,
    CANONICAL_VALIDATION, ENRICHMENT, INTERNAL
}

record MappingDiagnostic(
    String reasonCode,
    MappingStage stage,
    String sourceSystem,
    String sourceSchemaVersion,
    String eventId,
    String fieldPath,
    String endpoint,
    boolean retryable
) {}
~~~

One diagnostic instance:

~~~java
new MappingDiagnostic(
    "INVALID_AMOUNT_FORMAT",
    MappingStage.FIELD_CONVERSION,
    "PARTNER_A",
    "2",
    "EV-702",
    "totalAmount",
    "translator.partner.v2",
    false
);
~~~

`fieldPath` is the **contract field name** such as `totalAmount` or `items[2].quantity`, never the field's **value**. Avoid putting `rawEmail`, `cardNumber`, `authorizationHeader`, or full original exceptions into public diagnostic records.

In distributed flows, you can attach `businessCorrelationId`, `quarantineId`, `attemptCount`, or `transportReference` in **protected log context/metadata**, without exposing everything in partner replies.

## 9. Typed exception preserving reason and cause

An application exception:

~~~java
final class MappingFailure extends RuntimeException {
    private final MappingDiagnostic diagnostic;

    MappingFailure(MappingDiagnostic diagnostic) {
        super(diagnostic.reasonCode());
        this.diagnostic = diagnostic;
    }

    MappingFailure(
            MappingDiagnostic diagnostic, Throwable cause) {
        super(diagnostic.reasonCode(), cause);
        this.diagnostic = diagnostic;
    }

    MappingDiagnostic diagnostic() {
        return diagnostic;
    }
}
~~~

Benefits:

- `getMessage()` holds a **controlled error code**, not raw values.
- `getCause()` retains the technical exception for access-controlled investigation logs.
- `diagnostic()` provides stage, field, and retryability to Gateways and error handlers.

Never turn every exception into `MappingFailure("INVALID_INPUT")`. For a `NullPointerException` caused by a bug, do not mask it as a "client input error". For transient dependency failures, never force `retryable=false` just to dump into a DLQ quickly.

## 10. Factory for consistent diagnostic creation

~~~java
final class MappingFailures {
    static MappingFailure permanent(
            String code,
            MappingStage stage,
            PartnerOrderV2 raw,
            String field) {
        return new MappingFailure(
            new MappingDiagnostic(
                code,
                stage,
                "PARTNER_A",
                raw == null ? null : raw.schemaVersion(),
                raw == null ? null : raw.eventId(),
                field,
                "translator.partner.v2",
                false));
    }
}
~~~

This is an **illustrative factory**, not a Spring API. Production can use a typed `ReasonCode` catalog and `SourceContext` rather than loose strings. `eventId` is trusted only after format/source validation; for malicious inputs, omit unvalidated declared IDs from public responses.

A useful rule: **diagnostics must be created where the error is detected**, because outer layers sometimes see only `MessagingException` without knowing `totalAmount` failed.

## 11. Validate fields before conversion—no arbitrary fallbacks

A broken Mapper:

~~~java
BigDecimal amount = new BigDecimal(
    raw.totalAmount() == null
        ? "0" : raw.totalAmount());
~~~

It **turns a missing amount into zero**, making the canonical DTO look valid. For an order whose real amount is unknown, that is silent data corruption.

A clear extractor:

~~~java
String requiredText(
        String value,
        String reasonCode,
        MappingStage stage,
        PartnerOrderV2 raw,
        String fieldPath) {
    if (value == null || value.isBlank()) {
        throw MappingFailures.permanent(
            reasonCode, stage, raw, fieldPath);
    }
    return value;
}
~~~

In JSON:

- **Absent**: property does not exist.
- **Explicit null**: property exists with value `null`.
- **Blank**: value is empty or whitespace-only string.
- **Zero**: numeric value `0`, potentially valid per business contract.

When distinguishing absent vs. explicit null matters, a plain nullable record is insufficient: use `JsonNode.get()` / schema presence tracking or a tri-state type. Never call `asText("")` and silently collapse three states into one.

## 12. Converting money and timestamps: errors must pinpoint the exact field

An amount conversion helper:

~~~java
BigDecimal parseAmount(PartnerOrderV2 raw) {
    String text = requiredText(
        raw.totalAmount(),
        "MISSING_AMOUNT",
        MappingStage.FIELD_EXTRACTION,
        raw,
        "totalAmount");

    if (text.length() > 40) {
        throw MappingFailures.permanent(
            "AMOUNT_OUT_OF_RANGE",
            MappingStage.FIELD_CONVERSION,
            raw,
            "totalAmount");
    }
    try {
        BigDecimal amount = new BigDecimal(text);
        if (amount.signum() < 0) {
            throw MappingFailures.permanent(
                "AMOUNT_OUT_OF_RANGE",
                MappingStage.CANONICAL_VALIDATION,
                raw,
                "totalAmount");
        }
        return amount;
    } catch (NumberFormatException ex) {
        throw new MappingFailure(
            new MappingDiagnostic(
                "INVALID_AMOUNT_FORMAT",
                MappingStage.FIELD_CONVERSION,
                "PARTNER_A",
                raw.schemaVersion(),
                raw.eventId(),
                "totalAmount",
                "translator.partner.v2",
                false),
            ex);
    }
}
~~~

**`BigDecimal`** avoids `double` rounding issues. Production must also enforce **currency scale, max precision/range, rounding policy, and business semantics** (gross/net, refund, etc.), not merely string parsing.

For timestamps, use `Instant.parse(...)` when the contract requires an ISO-8601 UTC timestamp and map `DateTimeParseException` to `INVALID_TIMESTAMP`. Never substitute `Instant.now()` for a missing `createdAt`: that records processing time, not business event time.

## 13. A complete Translator must validate the source before building canonical output

An application mapper combining the helpers above:

~~~java
@Component
class PartnerV2Translator {

    CanonicalOrder translate(
            PartnerOrderV2 raw,
            String verifiedTenantId) {
        if (raw == null) {
            throw MappingFailures.permanent(
                "MISSING_SOURCE_PAYLOAD",
                MappingStage.CONTRACT,
                null,
                "$");
        }
        if (!"2".equals(raw.schemaVersion())) {
            throw MappingFailures.permanent(
                "UNSUPPORTED_SCHEMA_VERSION",
                MappingStage.CONTRACT,
                raw,
                "schemaVersion");
        }

        String eventId = requiredText(
            raw.eventId(),
            "MISSING_EVENT_ID",
            MappingStage.FIELD_EXTRACTION,
            raw,
            "eventId");
        String orderId = requiredText(
            raw.orderId(),
            "MISSING_ORDER_ID",
            MappingStage.FIELD_EXTRACTION,
            raw,
            "orderId");
        String iso = requiredText(
            raw.currency(),
            "MISSING_CURRENCY",
            MappingStage.FIELD_EXTRACTION,
            raw,
            "currency");
        Currency currency;
        try {
            currency = Currency.getInstance(iso);
        } catch (IllegalArgumentException invalid) {
            throw MappingFailures.permanent(
                "INVALID_CURRENCY",
                MappingStage.FIELD_CONVERSION,
                raw,
                "currency");
        }

        BigDecimal total = parseAmount(raw);
        String time = requiredText(
            raw.createdAt(),
            "MISSING_TIMESTAMP",
            MappingStage.FIELD_EXTRACTION,
            raw,
            "createdAt");
        Instant created;
        try {
            created = Instant.parse(time);
        } catch (DateTimeParseException invalid) {
            throw MappingFailures.permanent(
                "INVALID_TIMESTAMP",
                MappingStage.FIELD_CONVERSION,
                raw,
                "createdAt");
        }

        if (verifiedTenantId == null
                || verifiedTenantId.isBlank()) {
            throw MappingFailures.permanent(
                "UNTRUSTED_SOURCE_IDENTITY",
                MappingStage.CONTRACT,
                raw,
                "tenant");
        }

        return new CanonicalOrder(
            verifiedTenantId,
            eventId,
            orderId,
            new CanonicalMoney(currency, total),
            created,
            "PARTNER_A",
            "2");
    }
}
~~~

Place helpers like `requiredText()` and `parseAmount()` in appropriate classes/services when implementing; snippets are separated here to highlight each boundary. `verifiedTenantId` must be supplied by an adapter that performed authentication/authorization—**never** copy a raw producer-declared `tenantId`.

In production, add format validation for `eventId`/`orderId`, currency allowlists, scale/precision checks, canonical versioning, and amount semantics. Successfully constructing `CanonicalOrder` is the **start of validation**, not proof that all business rules pass.

## 14. Using `@Transformer` in Spring Integration

An endpoint producing the canonical payload:

~~~java
@MessageEndpoint
class PartnerOrderTransformer {
    private final PartnerV2Translator translator;

    PartnerOrderTransformer(PartnerV2Translator translator) {
        this.translator = translator;
    }

    @Transformer(
        inputChannel = "translator.partner.v2",
        outputChannel = "translator.canonical")
    public CanonicalOrder translate(
            Message<PartnerOrderV2> request) {
        String verifiedTenantId =
            (String) request.getHeaders()
                .get("verifiedTenantId");
        return translator.translate(
            request.getPayload(), verifiedTenantId);
    }
}
~~~

`verifiedTenantId` in the example must be populated by a **trusted internal adapter** after authentication, and downstream must never trust a header of the same name arriving raw from an external broker or client. Another design puts the verified tenant inside a request envelope instead of a header.

If the mapper throws `MappingFailure`, the endpoint must never return an all-null `CanonicalOrder` or a "success" payload to hide the error. Errors are handled at the synchronous/error-channel boundary and classified intentionally.

Spring Integration may preserve/copy certain request headers when a Transformer builds a reply payload, yet **never assume all headers survive custom `MessageBuilder` calls, external adapters, or brokers**. Test correlation and return addresses against your real topology.

## 15. Java DSL: an alternative configuration

Instead of registering the `@Transformer` endpoint in section 14, you can configure Java DSL:

~~~java
@Configuration
@EnableIntegration
class PartnerTranslationFlow {

    @Bean
    IntegrationFlow partnerV2Flow(
            PartnerV2Translator mapper) {
        return IntegrationFlow.from("translator.partner.v2")
            .transform(
                Message.class,
                request -> mapper.translate(
                    (PartnerOrderV2) request.getPayload(),
                    (String) request.getHeaders()
                        .get("verifiedTenantId")))
            .channel("translator.canonical")
            .get();
    }
}
~~~

These two examples are **alternatives**—never register both consuming from `translator.partner.v2` unless competing consumers are intended. Verify Java DSL overloads/syntax against your Spring Integration version.

The Translator can be unit-tested **independently** of the Spring context. `IntegrationFlow` only wires channels, transforms payloads, preserves desired metadata, and routes errors to the right boundary.

## 16. Mapping errors differ from business errors downstream of the Transformer

Suppose `CanonicalOrder` has valid currency and amount, yet Inventory returns `OUT_OF_STOCK`:

~~~text
PartnerOrderV2
  → Translator: OK
  → CanonicalOrder
  → Inventory: OUT_OF_STOCK
~~~

**`OUT_OF_STOCK` is not `INVALID_AMOUNT_FORMAT` or a Translator error.** It is a business outcome from the receiving system.

Similarly:

- `CARD_DECLINED` after a Gateway calls a payment service is a business rejection.
- `DB_DEADLOCK` while saving an order is an infrastructure failure.
- `UNKNOWN_SKU` can be a business rejection if a catalog lookup returned an authoritative answer.
- `HTTP_503` during SKU lookup is a transient dependency failure—**not proof that the SKU does not exist**.

Routing every downstream exception into `translator.errors` labeled `INVALID_SOURCE_PAYLOAD` destroys metric accuracy and blames the producer for data that was valid.

**Draw crisp boundaries:** Source decode/validation → Translation → Canonical validation → Business. Each layer owns its own reason code catalog and issue ownership.

## 17. Spring exception chains: never inspect only the outermost message

An error thrown by a Transformer can arrive wrapped by Spring Messaging/Integration, e.g., `MessagingException` or `MessageTransformationException`, with `MappingFailure` as an inner cause.

Conceptual stack:

~~~text
MessageTransformationException: failed to transform message
  caused by MappingFailure: INVALID_AMOUNT_FORMAT
    caused by NumberFormatException
~~~

**Never couple business logic to exact exception message strings**, which vary by code, framework, and locale. Walk the cause chain for the **typed exception** and extract its stable diagnostic:

~~~java
MappingFailure findMappingFailure(Throwable problem) {
    Set<Throwable> visited =
        Collections.newSetFromMap(new IdentityHashMap<>());
    Throwable current = problem;

    while (current != null && visited.add(current)) {
        if (current instanceof MappingFailure failure) {
            return failure;
        }
        current = current.getCause();
    }
    return null;
}
~~~

Note that this helper **locates the typed cause** without discarding the original exception. If no `MappingFailure` exists, never assume `INVALID_AMOUNT_FORMAT`; it may be a code bug, network drop, or failure in another endpoint.

## 18. `failedMessage` is helpful, though not always present

When an exception is a `MessagingException`, it may reference the failed message:

~~~java
Message<?> findFailedMessage(Throwable problem) {
    Set<Throwable> visited =
        Collections.newSetFromMap(new IdentityHashMap<>());
    Throwable current = problem;

    while (current != null && visited.add(current)) {
        if (current instanceof MessagingException messaging
                && messaging.getFailedMessage() != null) {
            return messaging.getFailedMessage();
        }
        current = current.getCause();
    }
    return null;
}
~~~

`failedMessage` helps inspect headers like `businessCorrelationId`, source schema, or transport references. Yet there are cases with **no `failedMessage`**:

- JSON parser fails before creating a Spring Message.
- An exception was not wrapped by the framework.
- The adapter only surfaced raw bytes/offsets.
- Failure happened inside an external callback disconnected from the original message.

**Never assume `failedMessage.getPayload()` is always the expected DTO type.** It could be `byte[]`, JSON, another `ErrorMessage`, or an already-transformed message; always check types and restrict payload logging.

## 19. `ErrorMessage` and `errorChannel` in asynchronous flows

When an endpoint runs asynchronously or has configured error handling, failures can become an `ErrorMessage`:

~~~mermaid
sequenceDiagram
    participant I as Inbound
    participant Q as Queue/Executor
    participant T as Transformer
    participant EC as Error channel
    participant EH as Error handler
    I->>Q: PartnerOrderV2
    Q->>T: Message
    T--xEC: MappingException/Transformation failure
    EC->>EH: ErrorMessage(Throwable)
    EH->>EH: Classify + quarantine/retry policy
~~~

In Java, `ErrorMessage` carries a `Throwable` as its payload. Spring Integration provides an error channel mechanism, though **which channel receives an exception depends on the source, poller, gateway, adapter, headers, and configuration**.

**Synchronous `DirectChannel`:** exceptions typically propagate on the caller thread; do not assume all synchronous errors land on global `errorChannel`. **`ExecutorChannel`/poller/listener:** errors occur after upstream `send()` already returned; the error handler at that async boundary owns recovery.

Never treat `send() == true` as proof the Translator succeeded if an executor or broker sits downstream.

## 20. An error handler extracting only controlled diagnostics

Example Service Activator:

~~~java
@MessageEndpoint
class TranslationErrorHandler {
    private final QuarantineService quarantine;

    TranslationErrorHandler(QuarantineService quarantine) {
        this.quarantine = quarantine;
    }

    @ServiceActivator(inputChannel = "translator.errors")
    public void handle(ErrorMessage errorMessage) {
        Throwable problem = errorMessage.getPayload();
        MappingFailure known = findMappingFailure(problem);
        Message<?> failed = findFailedMessage(problem);

        if (known != null && !known.diagnostic().retryable()) {
            quarantine.recordPermanentFailure(
                known.diagnostic(),
                safeTransportReference(failed));
            return;
        }

        // Do not label unclassified errors as invalid input.
        throw new IllegalStateException(
            "UNCLASSIFIED_TRANSLATION_FAILURE", problem);
    }
}
~~~

`QuarantineService` and `safeTransportReference()` are **application-defined abstractions/helpers**. In a real application, they require durable persistence, quotas, and authorization. `findMappingFailure()` and `findFailedMessage()` were introduced in earlier sections.

This is an **error-classification pattern**, not a complete recoverer for every broker. When the handler rethrows, verify the **error channel's own error policy** so it cannot enter an infinite loop. Ideally separate transient retry recovery at the container/retry boundary from terminal quarantine handlers.

**Never ACK/drop before quarantine persistence or recovery ownership is durably recorded.** If quarantine is unavailable, let the transport retain responsibility per policy.

## 21. Synchronous: returning diagnostics to Gateway/HTTP callers

A Gateway can expose a Translator as request–reply:

~~~java
@MessagingGateway(
    defaultRequestChannel = "translator.partner.v2")
interface TranslationGateway {
    CanonicalOrder translate(PartnerOrderV2 event);
}
~~~

In a synchronous flow, exceptions can propagate to the caller and be mapped by the API layer into a structured response:

~~~json
{
  "status": "REJECTED",
  "reasonCode": "INVALID_AMOUNT_FORMAT",
  "fieldPath": "totalAmount",
  "sourceSchemaVersion": "2",
  "retryable": false
}
~~~

Do not assume `MessageTransformationException` is automatically mapped to HTTP 400/422 by the web framework; add an exception mapper, controller advice, or typed result.

**Important Gateway contract:** if a Filter or Translator discards a message without sending a reply, the caller can **time out**, mistaking invalid input for an infrastructure outage. Choose either a fail-fast exception or a typed result like `TranslationAccepted | TranslationRejected`—and implement it end-to-end rather than just declaring the return type.

For async/broker request–reply, the gateway's `replyChannel`/correlation works differently. Never use a temporary reply channel as a durable business ID, and never serialize JVM channel objects into events for remote receivers.

## 22. Error routing by error class, not catch-all

A classifier:

~~~mermaid
flowchart TD
    E["Mapping error"] --> K{"Typed MappingFailure?"}
    K -->|"Yes"| R{"retryable?"}
    R -->|"false"| Q["Permanent reject / quarantine"]
    R -->|"true"| B["Bounded retry + backoff"]
    K -->|"No"| U{"Infrastructure or mapper defect?"}
    U -->|"Verified transient"| B
    U -->|"Unclear"| ALERT["Alert + controlled recovery"]
    B --> DONE{"Succeeded?"}
    DONE -->|"Yes"| OK["Canonical output"]
    DONE -->|"No"| EX["Exhausted retries / DLQ or workflow"]
~~~

Never write:

~~~java
catch (Exception e) {
    throw new MappingFailure(
        permanentDiagnostic("INVALID_INPUT"), e);
}
~~~

This anti-pattern disguises `NullPointerException` bugs, `SQLException`s, and HTTP timeouts as producer input errors. Convert only **known, explicitly semantic exceptions** into permanent reason codes; preserve the cause chain on all others so the proper recovery policy handles them.

## 23. Retry policy: data errors do not heal via retries

| Scenario | Same payload + same mapper | Action |
|---|---|---|
| `INVALID_AMOUNT_FORMAT` | Always fails | Reject/quarantine; producer fixes input |
| `MISSING_ORDER_ID` | Always missing | Reject; do not hot-retry |
| `UNSUPPORTED_SCHEMA_VERSION` | Version unknown | Quarantine/upgrade/migration |
| `ENRICHMENT_UNAVAILABLE` | May recover | Bounded retry + backoff + deadline |
| Mapper logic bug | Hot retry cannot fix | Alert, fix/deploy, reprocess safely |
| Remote timeout after side effect | Uncertain outcome | Reconcile via idempotent remote key |
| Dedupe store inaccessible | Duplicate status unknown | Fail closed/defer unless side effect is inherently idempotent |

With `RequestHandlerRetryAdvice`, remember the advice wraps only **its target handler**. If the Transformer returns immediately and a downstream async consumer throws, retry advice on the Transformer **will not catch** the downstream failure.

**Never stack unbounded retry loops:** handler retry + broker container retry + workflow retry can trigger request storms. Enforce a total attempt budget, deadline, backoff, and terminal state recording.

## 24. A DLQ/quarantine record must carry the right context

For permanent errors:

~~~text
quarantineId = Q-5701
sourceSystem = PARTNER_A
sourceSchemaVersion = 2
eventId = EV-702
reasonCode = INVALID_AMOUNT_FORMAT
fieldPath = totalAmount
stage = FIELD_CONVERSION
endpoint = translator.partner.v2
transportReference = topic:orders/partition:3/offset:1209
mappingPolicyVersion = v2-map-4
replayStatus = PENDING_REVIEW
payloadReference = protected-object://...
~~~

Never dump full raw JSON, secrets, tokens, or PII into general logs or metrics. Store raw payloads only in **protected storage** when genuinely needed, with encryption, retention, access controls, quotas, audits, and non-public references.

**A quarantine record is not a business processed marker.** Rejecting an input does not mean the business operation completed; when the producer sends a corrected version, define policies for event versions, fingerprints, replays, and idempotency.

**Discard channel ≠ DLQ.** A Filter discard channel is an internal Spring Integration channel; a broker DLT/DLQ exists only when an adapter, recoverer, or publisher explicitly emits to it.

## 25. ACK and DLQ when input arrives from a broker

A permanent mapping error in a consumer can create a **poison pill**:

~~~text
Broker → PartnerOrderV2 event EV-702
  → Translator: INVALID_AMOUNT_FORMAT
  → container retries same payload
  → Translator: INVALID_AMOUNT_FORMAT
  → ... never succeeds on its own
~~~

Brokers and containers do not automatically inspect `MappingFailure.retryable=false` unless the adapter's **error classifier/recoverer** is wired to do so. Practical policy:

| Result | Handling before completing source delivery |
|---|---|
| Mapping succeeds, downstream commits cleanly | ACK/commit offset per contract |
| Permanent mapping failure | Persist to DLQ/quarantine safely, then ACK per transport policy |
| Transient failure | Bounded retry/backoff; do not ACK and lose work |
| Quarantine/DLQ unavailable | Retain recovery responsibility; never drop silently |
| Unknown remote side effect | Persist for workflow reconciliation; never assume uncommitted |

**A "publish to DLQ then ACK source" sequence is not inherently atomic** across Kafka, RabbitMQ/AMQP, and JMS. Check your adapter's transaction/ACK semantics, test boundary crashes, and enforce idempotency for duplicate publications.

Never infinitely requeue malformed bytes; conversely, never dump all infrastructure failures into a permanent DLQ merely because they happened inside a Transformer.

## 26. Preserving identity when the Translator cannot produce output

A mapping error can occur **before any canonical ID exists**, e.g., `orderId` is missing. Distinguish:

| ID | Source | Use on failure |
|---|---|---|
| `eventId` | Producer contract | Use if validated/trusted |
| `orderId` | Business payload | May not exist |
| `businessCorrelationId` | Logical processing group | Use only if verified |
| `traceId` | Observability context | Trace requests, never as business group key |
| `MessageHeaders.ID` | Spring message instance | Useful internally, not durable across broker replays |
| `transportReference` | Topic/partition/offset, broker message ID, file offset | Traces back to raw message origin |
| `quarantineId` | New record in error flow | Durable key for error review/replay |

Example raw message missing `eventId`:

~~~text
source=PARTNER_A
transportReference=orders.topic/partition-3/offset-1209
quarantineId=Q-5702
reasonCode=MISSING_EVENT_ID
businessCorrelationId=null
~~~

**Never assign a shared fallback business correlation key like `UNKNOWN` to all errors**: Aggregators or log processors could accidentally lump thousands of unrelated failures into one group. Keep transport/quarantine identities separate from group identities.

Header correlations can be lost when messages change types or cross brokers. If recovery needs those IDs, carry them inside the **wire contract** or store a durable mapping from transport ID to logical ID rather than trusting every Spring header to serialize automatically.

## 27. Splitter: where does the parent group go when one child fails mapping?

Suppose a Splitter emits three line tasks:

~~~text
Order O-701 → Splitter L1, L2, L3
L1 → Translator → LineResult success
L2 → Translator → INVALID_QUANTITY_TYPE
L3 → Translator → LineResult success
                             ↓
                         Aggregator
~~~

If L2's Translator throws an exception without producing a recovery outcome, the Aggregator can **wait forever for L2** because `sequenceSize=3`. `errorChannel` by itself does not generate a `LineResult` carrying the group's correlation and member identity.

~~~mermaid
flowchart TD
    S["Splitter: L1 L2 L3"] --> T["Per-line Translator"]
    T -->|"L1 L3 OK"| OK["LineResult"]
    T -->|"L2 mapping invalid"| ERR["Mapping error"]
    ERR --> DEC{"Policy?"}
    DEC -->|"Fail whole batch"| BATCH["Abort/mark group FAILED"]
    DEC -->|"Allow item outcomes"| FAIL["LineOutcome L2 = FAILED"]
    OK --> AG["Aggregator"]
    FAIL --> AG
    AG --> SUMMARY["OrderSummary PARTIAL/FAILED"]
~~~

Two ways to handle it:

1. **Validate the entire input before the Splitter** if one malformed member invalidates the whole order, avoiding partial fan-out.
2. If the domain allows per-line outcomes, **convert the error into a typed `LineOutcome`** carrying **parent correlation ID, member ID, and `reasonCode`**, and release only when all expected member outcomes arrive.

Never mutate `sequenceSize=3` down to `2` just to force the Aggregator to release, nor count duplicate L1s as three members. Release strategies should check against an **expected member manifest** and each member's terminal state.

## 28. Resequencer and Router do not fix mapping errors by themselves

A Router can pick a Translator based on:

~~~text
source=PARTNER_A, version=2 → translator.partner.v2
source=LEGACY, version=1    → translator.legacy.v1
else                       → unsupported-schema rejection
~~~

**Router** chooses branches. It cannot turn JSON `totalAmount="one hundred"` into a valid number. If routing relies on a spoofed `schemaVersion`, the message may hit the wrong mapper and fail obscurely.

**Resequencer** orders messages. It cannot recreate a child dropped by a Transformer error; missing sequence numbers cause prolonged gaps.

**Filter** can reject before the Translator, yet a boolean-only Filter still needs somewhere to produce `reasonCode` / typed rejections. Conversion errors caught when running `new BigDecimal(text)` are Translator errors, not Filter discards unless validation runs beforehand.

**Aggregator** merges results; if one member lacks a result, define timeouts, failure outcomes, and recovery. Never make the Aggregator responsible for fixing malformed payloads.

## 29. Content Enricher must not mask mapping errors with guessed data

A Translator missing `customerCountry` might call a Customer service to enrich it:

~~~text
Partner event without country
  → Content Enricher lookup(customerId)
  → country=VN
  → CanonicalOrder
~~~

Still, distinguish:

- **Missing because the source schema omits it:** enrichable if the contract allows.
- **Lookup returns authoritative 404:** likely `CUSTOMER_NOT_FOUND`, a business/contract error.
- **Lookup returns HTTP 503:** transient infrastructure failure; never default `country="VN"` just to bypass it.
- **Lookup times out after a remote mutation:** if read-only, retries are safer; if side-effecting, require idempotency/reconciliation.

If a Content Enricher runs multiple parallel lookups, give each lookup its **own request ID** mapped back to the parent message; do not correlate replies solely by `customerId` when one customer has multiple concurrent orders.

In diagnostics, record `stage=ENRICHMENT`, an allowlisted dependency alias, attempt count, and deadline. Never leak access tokens, secret URLs, or verbatim remote responses into public errors.

## 30. Traps in mapping headers and payloads

A Transformer may receive a message with:

~~~text
headers.correlationId=G-701
headers.sequenceNumber=2
headers.sequenceSize=3
headers.replyChannel=<temporary channel object>
payload.eventId=EV-701
~~~

When building a new `Message<?>`, correlation/sequence metadata may need to pass to the next endpoint. Yet **copying all headers indiscriminately** across external transports causes serialization errors, misrouting, or internal leaks.

Principles:

- **In-JVM:** verify how Transformers/`MessageBuilder` propagate headers and allowlist internal headers.
- **Across brokers:** allowlist and convert types properly, placing business correlation inside the wire schema when needed for recovery.
- **With Gateways:** `replyChannel` is a technical return address, not a business correlation key.
- **With Splitters:** `sequenceNumber`/`sequenceSize` have meaning only within their exact correlation group.
- **On failure:** error handlers need parent group context to emit a failure outcome; otherwise quarantine rather than inventing a group.

**A normalized payload does not guarantee all headers stayed intact.** Test at the actual output channel and adapter, not just mapper methods returning DTOs.

## 31. Classify errors by severity so monitoring is not misled

Example:

~~~text
INVALID_AMOUNT_FORMAT       → permanent input issue
UNSUPPORTED_SCHEMA_VERSION  → producer/consumer contract mismatch
MAPPING_INTERNAL_ERROR      → code defect, alert needed
ENRICHMENT_UNAVAILABLE      → transient dependency issue
UNKNOWN_REMOTE_OUTCOME      → reconciliation required
~~~

All can throw exceptions, yet **none should share the exact same alert severity or owner**. A partner changing amount formatting spikes reject rates; a new release throwing `NullPointerException` is a mapper defect; an upstream 503 is a temporary outage.

Permitted metric dimensions:

- `sourceSystem` from an enum/allowlist;
- `schemaVersion` normalized via a finite catalog;
- `reasonCode`, `mappingStage`, `endpoint`, `outcome`;
- `retryable` flag;
- `mappingPolicyVersion`.

Never put `eventId`, `orderId`, emails, or raw exception text into **metric labels** due to high cardinality and sensitive data risks. Specific IDs belong in structured logs and traces with retention and access controls.

## 32. Metrics and tracing for Message Translator

**Suggested** metrics (not Spring Integration defaults):

| Metric | Meaning |
|---|---|
| `translator.input.count` | Traffic by source/schema |
| `translator.success.count` | Canonical messages produced |
| `translator.mapping.failure.count` | Mapping errors by `reasonCode`/stage |
| `translator.decode.failure.count` | Raw byte decode errors at ingress |
| `translator.schema.unsupported.count` | Unsupported input versions |
| `translator.retry.attempts.count` | Retry amplification |
| `translator.retry.exhausted.count` | Exhausted retry budgets |
| `translator.quarantine.pending.count` | Unreviewed permanent errors |
| `translator.quarantine.write.failure.count` | Failures persisting error evidence |
| `translator.mapping.duration` | Mapping latency |
| `translator.enrichment.timeout.count` | Dependency timeouts |
| `translator.canonical.invalid.count` | Outputs failing canonical validation |
| `translator.correlation.missing.count` | Unrecoverable groups |
| `translator.failure.outcome.count` | Failure outcomes for Splitter/Aggregator |

Controlled structured log:

~~~text
eventId=EV-702
sourceSystem=PARTNER_A
sourceSchemaVersion=2
endpoint=translator.partner.v2
mappingPolicyVersion=v2-map-4
stage=FIELD_CONVERSION
reasonCode=INVALID_AMOUNT_FORMAT
fieldPath=totalAmount
retryable=false
outcome=QUARANTINED
transportReference=topic/orders/p3/o1209
~~~

Do not log `totalAmount="one hundred"` if real data in corresponding fields could hold PII or secrets. Field path and reason code usually suffice for triage; open raw references only under authorization when needed.

## 33. Unit test: successful conversion and exact format error

JUnit 5 using the models from sections 7–13:

~~~java
@Test
void partnerV2IsTranslatedWithoutLosingAmount() {
    PartnerV2Translator translator = new PartnerV2Translator();
    PartnerOrderV2 raw = new PartnerOrderV2(
        "2", "EV-701", "O-701", "USD",
        "129.99", "2026-11-20T09:30:00Z");

    CanonicalOrder result =
        translator.translate(raw, "tenant-a");

    assertEquals("O-701", result.orderId());
    assertEquals("EV-701", result.eventId());
    assertEquals(
        Currency.getInstance("USD"),
        result.total().currency());
    assertEquals(
        0,
        new BigDecimal("129.99")
            .compareTo(result.total().amountMajor()));
    assertEquals(
        Instant.parse("2026-11-20T09:30:00Z"),
        result.orderedAt());
}

@Test
void invalidAmountReportsStableCodeAndField() {
    PartnerV2Translator translator = new PartnerV2Translator();
    PartnerOrderV2 raw = new PartnerOrderV2(
        "2", "EV-702", "O-702", "USD",
        "one hundred", "2026-11-20T09:30:00Z");

    MappingFailure failure = assertThrows(
        MappingFailure.class,
        () -> translator.translate(raw, "tenant-a"));

    assertEquals(
        "INVALID_AMOUNT_FORMAT",
        failure.diagnostic().reasonCode());
    assertEquals(
        "totalAmount",
        failure.diagnostic().fieldPath());
    assertEquals(
        MappingStage.FIELD_CONVERSION,
        failure.diagnostic().stage());
    assertFalse(failure.diagnostic().retryable());
}
~~~

Do not assert only that an exception was thrown; assert **`reasonCode`, `stage`, `fieldPath`, `retryable`, and event/source context**. A test asserting only `NumberFormatException` breaks on implementation changes and does not verify the error contract.

## 34. Unit test: missing fields, schema versions, and timestamps

~~~java
@Test
void missingAmountIsNotDefaultedToZero() {
    PartnerV2Translator mapper = new PartnerV2Translator();
    PartnerOrderV2 raw = new PartnerOrderV2(
        "2", "EV-703", "O-703", "USD",
        null, "2026-11-20T09:30:00Z");

    MappingFailure failure = assertThrows(
        MappingFailure.class,
        () -> mapper.translate(raw, "tenant-a"));

    assertEquals(
        "MISSING_AMOUNT",
        failure.diagnostic().reasonCode());
}

@Test
void unknownSchemaVersionIsNotSilentlyAccepted() {
    PartnerV2Translator mapper = new PartnerV2Translator();
    PartnerOrderV2 raw = new PartnerOrderV2(
        "9", "EV-704", "O-704", "USD",
        "10.00", "2026-11-20T09:30:00Z");

    MappingFailure failure = assertThrows(
        MappingFailure.class,
        () -> mapper.translate(raw, "tenant-a"));

    assertEquals(
        "UNSUPPORTED_SCHEMA_VERSION",
        failure.diagnostic().reasonCode());
}

@Test
void invalidTimestampPointsAtCreatedAt() {
    PartnerV2Translator mapper = new PartnerV2Translator();
    PartnerOrderV2 raw = new PartnerOrderV2(
        "2", "EV-705", "O-705", "USD",
        "10.00", "yesterday");

    MappingFailure failure = assertThrows(
        MappingFailure.class,
        () -> mapper.translate(raw, "tenant-a"));

    assertEquals(
        "INVALID_TIMESTAMP",
        failure.diagnostic().reasonCode());
    assertEquals(
        "createdAt",
        failure.diagnostic().fieldPath());
}
~~~

Additional tests should cover explicit nulls, blank IDs, negative amounts, invalid currencies, oversized amount strings, precision/scale, and untrusted tenant metadata. Avoid `@Transactional` on tests if it hides downstream commit/retry behavior.

## 35. Integration test: exception preserves diagnostics through the Transformer

Test context using Java DSL:

~~~java
@Configuration
@EnableIntegration
class TranslatorTestConfig {
    @Bean
    IntegrationFlow testTranslator(PartnerV2Translator mapper) {
        return IntegrationFlow.from("test.partner.in")
            .transform(
                Message.class,
                request -> mapper.translate(
                    (PartnerOrderV2) request.getPayload(),
                    (String) request.getHeaders()
                        .get("verifiedTenantId")))
            .channel("test.partner.out")
            .get();
    }

    @Bean("test.partner.out")
    PollableChannel outputQueue() {
        return new QueueChannel();
    }
}
~~~

In a synchronous test:

~~~java
@Autowired
ApplicationContext context;

@Test
void mapperErrorCanBeRecoveredFromCauseChain() {
    MessageChannel input = context.getBean(
        "test.partner.in", MessageChannel.class);
    PollableChannel output = context.getBean(
        "test.partner.out", PollableChannel.class);

    PartnerOrderV2 malformed = new PartnerOrderV2(
        "2", "EV-702", "O-702", "USD",
        "bad amount", "2026-11-20T09:30:00Z");
    Message<PartnerOrderV2> request =
        MessageBuilder.withPayload(malformed)
            .setHeader("verifiedTenantId", "tenant-a")
            .setHeader("businessCorrelationId", "G-701")
            .build();

    RuntimeException thrown = assertThrows(
        RuntimeException.class,
        () -> input.send(request));

    MappingFailure failure = findMappingFailure(thrown);
    assertNotNull(failure);
    assertEquals(
        "INVALID_AMOUNT_FORMAT",
        failure.diagnostic().reasonCode());
    assertNull(output.receive(0));
}
~~~

The `findMappingFailure()` helper and test bean context were introduced earlier. The test uses a sync boundary, so exceptions propagate to the caller. If switched to `ExecutorChannel`, the test must inspect the error channel/container rather than assuming `send()` throws.

**Do not register both `@Transformer` and Java DSL on the same input channel** in one test unless competing consumers are intended. Run those configurations as independent setups.

## 36. Testing `ErrorMessage` and `failedMessage`: information is not lost

A test can construct the error wrapper an error handler receives:

~~~java
@Test
void errorMessagePreservesMappingDiagnosticAndFailedMessage() {
    PartnerOrderV2 raw = new PartnerOrderV2(
        "2", "EV-702", "O-702", "USD",
        "wrong", "2026-11-20T09:30:00Z");
    Message<PartnerOrderV2> original =
        MessageBuilder.withPayload(raw)
            .setHeader("businessCorrelationId", "G-701")
            .build();

    MappingFailure mapping = MappingFailures.permanent(
        "INVALID_AMOUNT_FORMAT",
        MappingStage.FIELD_CONVERSION,
        raw,
        "totalAmount");

    MessagingException wrapper = new MessagingException(
        original,
        "Transform failed",
        mapping);
    ErrorMessage error = new ErrorMessage(wrapper);

    MappingFailure detected =
        findMappingFailure(error.getPayload());
    Message<?> failed =
        findFailedMessage(error.getPayload());

    assertNotNull(detected);
    assertEquals("INVALID_AMOUNT_FORMAT",
        detected.diagnostic().reasonCode());
    assertNotNull(failed);
    assertEquals("G-701",
        failed.getHeaders().get("businessCorrelationId"));
}
~~~

This test proves the **unwrapping helpers** when `MessagingException.getFailedMessage()` is populated; it **does not prove a real container routes every error to an error channel**. Add an integration test using a real `ExecutorChannel`, poller, or broker adapter, its error channel, and its recovery strategy.

Also test `failedMessage == null`: the error handler must still produce a sanitized error record from transport references if present, or report `UNKNOWN_SOURCE_CONTEXT` instead of throwing a `NullPointerException` that hides the original error.

## 37. Testing raw bytes, schema/version, and unexpected data types

Testing a mapper directly with `PartnerOrderV2` covers only **already-deserialized** objects. Add dedicated adapter/deserializer tests using raw bytes:

~~~text
Case A: { "eventId":"EV-702","totalAmount":
        → JSON syntax error, before Transformer

Case B: { "totalAmount": ["129.99"] }
        → wrong JSON type; must not coerce into a string

Case C: { "schemaVersion":"9", ... }
        → unsupported schema, exact reasonCode

Case D: { "currency":null, ... }
        → missing/null policy

Case E: oversized, deeply nested payload
        → ingress resource limit before building object graph
~~~

Use strict schema/deserializer settings to prevent Jackson from coercing `123` into `"123"`. Test enabled/disabled coercions against the API/producer contract rather than relying on incidental library defaults.

Also test **broker header mapping** when events cross Kafka/AMQP: verify source/version, business IDs, correlation, and trace context actually survive with the right types and cannot be overwritten before the Mapper runs.

**Never log full failed raw bytes** in tests or production when sensitive data may be present; store a controlled hash/reference for auditing and authorized reproduction.

## 38. Testing concurrent errors, retries, and idempotency

Suppose a consumer processes two orders concurrently:

~~~text
EV-702 → INVALID_AMOUNT_FORMAT → quarantine
EV-703 → valid → canonical output → business commit

Broker redelivers EV-702 and EV-703:
  EV-702 → permanent reject, never enters business
  EV-703 → idempotent business handling, zero double commit
~~~

What to prove:

- EV-702's failure **never alters EV-703's correlation or event ID**.
- Permanent mapping errors are not infinitely hot-retried.
- Valid messages are not blocked behind a poison pill once the recoverer handles it.
- Downstream business logic never executes twice on redelivery.
- Quarantine never ingests another tenant's data via spoofed headers.
- If one Mapper branch fails, other branches keep operating per designed routing/flow isolation.

Concurrency tests can use `CountDownLatch` to coordinate ordering instead of flaky `Thread.sleep`. With real brokers, test ACK/NACK, DLT publish failures, and crashes between durable steps.

## 39. Test matrix for mapping and diagnostics

| Scenario | Expected error/outcome | What to verify |
|---|---|---|
| Valid v2 input | `CanonicalOrder` | Accurate amount, currency, timestamp |
| Missing `orderId` | `MISSING_ORDER_ID` | Stage/extraction, `fieldPath` |
| `totalAmount=null` | `MISSING_AMOUNT` | Never defaults to 0 |
| `totalAmount="abc"` | `INVALID_AMOUNT_FORMAT` | Permanent, no valid output |
| `totalAmount=[]` | `INVALID_AMOUNT_TYPE` | Caught at decode/contract boundary |
| Oversized amount | `AMOUNT_OUT_OF_RANGE` | No overflow/truncation |
| Invalid currency | `INVALID_CURRENCY` | No global USD fallback |
| Non-standard timestamp | `INVALID_TIMESTAMP` | Pinpoints `createdAt` |
| Schema v9 | `UNSUPPORTED_SCHEMA_VERSION` | Never misrouted to v2 |
| Bad JSON syntax | Decode failure | Transformer never ran |
| Spoofed tenant/header | Security rejection | Never trusts raw headers |
| Mapper throws NPE | Internal defect | Never labeled as producer error |
| Lookup HTTP 503 | Retryable dependency | Bounded attempts, not premature permanent DLQ |
| Uncertain remote result | Unknown outcome | Reconcile; never blind-retry side effects |
| Filter drops invalid input | Discard / typed error | Gateway does not time out needlessly |
| Async Transformer error | `ErrorMessage` | Accurate diagnostic and correlation |
| Absent failed message | Sanitized fallback | Handler does not crash a second time |
| DLQ unavailable | Durable recovery | Never ACK and lose source |
| Splitter child fails | Failure outcome / batch failure | Aggregator does not wait forever |
| Duplicate event after commit | Idempotent handler | Zero repeated side effects |
| Same `eventId`, different payload | Idempotency key conflict | Never accepted silently |
| Schema upgrade | Different mapping policy version | Controlled replay/migration |
| Oversized payload | Resource rejection | Never exhausts memory/parser |

Test **error codes** and **blast radius** together: verify not only the exception, but also that zero messages enter the business channel, duplicate results are not emitted, groups are not lost, and raw payloads never leak.

## 40. Runbook for "Message transformation failed" alerts

An incident investigation sequence:

1. **Locate endpoint and stage:** did it fail in the deserializer, the Transformer, or a downstream business handler?
2. **Retrieve trusted source/version:** which adapter received the event and which version routed it?
3. **Read `reasonCode`/`fieldPath`:** is it `MISSING_AMOUNT`, `INVALID_AMOUNT_FORMAT`, or `MAPPING_INTERNAL_ERROR`?
4. **Inspect cause chain:** is there a typed `MappingFailure`, or only a `MessagingException` wrapping an infrastructure fault?
5. **Determine retryability:** could retrying the exact same input + policy succeed?
6. **Compare against raw schema when authorized:** did a field name, type, unit, or nullability change?
7. **Check the Router:** was a source/version routed to an incompatible mapper?
8. **Check headers/correlation:** are business IDs, parent groups, and member IDs intact?
9. **Inspect Gateway/error channel:** did the error return to the caller, emit an `ErrorMessage`, or drop into a timeout?
10. **Inspect broker ACK/DLQ:** was a permanent poison pill persisted durably, or is the DLQ down?
11. **Inspect committed effects:** if the failure happened after the Translator inside a business handler, is an idempotent replay needed?
12. **Remediate and regression-test:** fix producer/mapper/schema policy, test raw bytes and canonical results, then replay under audit, retention, and quotas.

**Never "fix" an incident by catching all exceptions and returning a default DTO.** That turns a clear error into silent data corruption. Also never wipe idempotency markers and mass-replay without checking already-committed side effects.

## 41. Pre-deployment diagnostic design checklist

An operable Message Translator should ensure:

- Contracts exist for source schemas, versions, and canonical outputs.
- Decode, extraction, conversion, validation, and dependency failures are distinguished.
- A stable `reasonCode` catalog exists, with `fieldPath` constrained to an allowlist.
- Missing, null, blank, and zero are never treated as identical.
- Required data never gets silent defaults without contract backing.
- Money, date, and enum mappings validate units, precision, ranges, and timezones.
- Diagnostics report `sourceSystem`, `schemaVersion`, `endpoint`, `stage`, and `retryable` when known.
- Business IDs/correlation are verified, never dumping unrelated failures into a shared `UNKNOWN` group.
- Raw PII, secrets, and payloads never enter public errors or metric labels.
- Error classifiers distinguish permanent, transient, and unknown outcomes.
- Gateway paths have typed rejections or exception mappers, never pointless timeouts.
- Async error channels and container handlers are configured and tested.
- Quarantine/DLQ is durable with access controls, quotas, retention, and replay policies.
- Splitters/Aggregators enforce failure outcomes and expected-member policies.
- Retries have deadlines/backoff, and idempotency protects downstream side effects.
- Unit, integration, and transport tests cover error paths.
- Metrics track rejection reasons, schema drift, mapper defects, and quarantine backlogs.

This checklist **does not replace** integration testing with real adapters, endpoints, and error recoverers; it clarifies the guarantees to prove before shipping a Translator to production.

## 42. Practice exercise: a Translator with clear diagnostics and recovery

Build the **PartnerOrderTranslator** mini project:

1. Define `PartnerOrderV2` and `CanonicalOrder` as above.
2. Write `MappingStage`, `MappingDiagnostic`, `MappingFailure`, and a reason-code catalog.
3. Implement the mapper returning a canonical result or typed error, without arbitrary amount/currency defaults.
4. Add a Java DSL Transformer or `@Transformer` (pick one configuration).
5. Write unit tests for valid inputs, bad amounts, missing fields, bad timestamps, and unsupported schemas.
6. Place parser/JSON schema validation before the Transformer and test raw malformed bytes.
7. Test the `MessagingException` cause chain and `failedMessage`.
8. Build a `translator.errors` flow persisting sanitized permanent failures to quarantine.
9. Add a Gateway and HTTP error mapper returning `reasonCode`/`fieldPath` without stack traces.
10. Attach a broker adapter; test bounded retries, ACK/DLT, and an unavailable DLQ.
11. Wire Splitter/Aggregator, trigger a child mapping error, and handle expected members cleanly.
12. Upgrade source schema from v2 to v3; verify the Router picks the right mapper and rejects unsupported versions.
13. Test idempotent replay after commit with zero duplicate business side effects.
14. Build a mapping-failure dashboard by source/version/reason without putting event IDs in metric labels.
15. Write a runbook for `MessageTransformationException` covering every error boundary.

**Completion criteria:** invalid messages report the **right reason, right field, and right source/version**, never enter business flows, never infinitely retry permanent errors, and never lose ownership when the DLQ is down; valid messages continue processing; correlation and idempotency hold across retries and replays.

## 43. Common misconceptions

**"Throwing `NumberFormatException` from the Translator is enough."** No. You need error codes, field paths, source/version, and retryability.

**"Every error from a Transformer means the producer sent bad data."** No. There are mapper defects, dependency outages, and downstream failures.

**"Reading only the outermost exception message suffices."** No. Spring can wrap it in `MessagingException`; inspect the cause chain.

**"Every JSON syntax error reaches `@Transformer`."** No. Deserialization can fail before a Spring Message exists.

**"`failedMessage` always exists and holds the exact source DTO."** No. It can be null, raw bytes, or a transformed payload.

**"All errors automatically go to the global `errorChannel`."** Not automatically; it depends on sync/async boundaries and configuration.

**"A Filter discard channel is a broker DLT."** No. You need a publisher/recoverer bridging from the channel to the broker.

**"Mapping errors should immediately retry multiple times."** Not for permanently malformed input; identical bytes do not fix themselves.

**"If the mapper cannot parse an amount, set it to 0."** Wrong. That is silent data corruption.

**"Any unknown currency can default to USD for all sources."** Not unless the source contract guarantees it.

**"Having `traceId` is enough to aggregate Aggregator results."** No. Traces and business correlation have different semantics.

**"`MessageHeaders.ID` stays identical across all retries and brokers."** Never assume this; messages can be rebuilt.

**"When the Translator fails, the Gateway automatically returns HTTP 400."** No. The API layer must map errors or return a typed rejection.

**"Sending full raw payloads and stack traces to logs/DLQs is safe."** Not when PII, secrets, large payloads, or log injection are involved.

**"Once routed to quarantine, you can ACK regardless of whether storage succeeded."** No. ACKs must obey the durable recovery contract.

**"If one child Translator fails, the Aggregator knows when to finish."** Not without a failure outcome, release strategy, or expiry policy.

**"Having retry advice means you already have idempotency."** No. Retrying and preventing duplicate side effects are separate concerns.

**"A mapped message with the right Java types has the right semantics."** No. Units, precision, currency, timestamps, and business meaning can still be wrong.

## 44. Key takeaways

**Mapping errors and diagnostics** are part of the **Message Translator** contract, not optional logging details. A solid Translator **converts messages faithfully or fails transparently**, specifying **`reasonCode`, `stage`, `fieldPath`, source/version, endpoint, retryability, and trusted identity** whenever possible.

In **Spring Integration**, separate errors **before the Transformer** (decode/adapter), errors **inside the Transformer** that may wrap into `MessagingException`/`MessageTransformationException`, and errors **after the Translator** in business handlers. Use `ErrorMessage`, `failedMessage`, Gateway exception mapping, and error channels according to sync–async boundaries; never assume all errors flow to the same channel automatically.

Classify **permanent input errors**, **transient dependencies**, **unknown outcomes**, and **mapper defects** to choose reject, retry, or reconcile accurately. Preserve correlation and idempotency across Router, Filter, Splitter, Aggregator, Gateway, and brokers; never write raw sensitive data into diagnostics; and test both **error codes** and **zero side effects on bad input**. When data cannot be converted safely, **a clean rejection is far better than fabricating bad values**.

### References

- Enterprise Integration Patterns, **Message Translator**: https://www.enterpriseintegrationpatterns.com/patterns/messaging/MessageTranslator.html
- Enterprise Integration Patterns, **Normalizer**: https://www.enterpriseintegrationpatterns.com/patterns/messaging/Normalizer.html
- Spring Integration Reference, **Transformer**: https://docs.spring.io/spring-integration/reference/transformer.html
- Spring Integration Reference, **Error Handling**: https://docs.spring.io/spring-integration/reference/error-handling.html
- Spring Integration Reference, **Message Filter**: https://docs.spring.io/spring-integration/reference/filter.html
- Spring Integration Reference, **Router**: https://docs.spring.io/spring-integration/reference/router.html
- Spring Integration Reference, **Gateway**: https://docs.spring.io/spring-integration/reference/gateway.html
- Spring Integration Reference, **Aggregator**: https://docs.spring.io/spring-integration/reference/aggregator.html
