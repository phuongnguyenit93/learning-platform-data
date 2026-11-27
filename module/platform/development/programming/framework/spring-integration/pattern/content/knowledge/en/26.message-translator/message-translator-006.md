# Handling Unmapped Fields

## 1. The problem: the translator encounters a field with nowhere to go

An order system receives orders from a partner. The partner sends:

~~~json
{
  "eventId": "PARTNER-EVT-901",
  "partnerOrderRef": "EXT-ORD-901",
  "totalVnd": "850000",
  "deliveryCode": "EXP",
  "legacyCampaignHint": "old-q4",
  "newRiskIndicator": "high"
}
~~~

Internally, the business only expects a canonical structure:

~~~json
{
  "sourceEventId": "PARTNER-EVT-901",
  "orderId": "EXT-ORD-901",
  "amountVnd": 850000,
  "shippingTier": "EXPRESS"
}
~~~

The fields `eventId`, `partnerOrderRef`, `totalVnd`, and `deliveryCode` have clear mapping rules. However, `legacyCampaignHint` and `newRiskIndicator` **have no target fields**. If the translator drops both without recording anything, the supplier might have added a critical attribute and data is silently lost. If the translator throws an exception for every unknown field, a minor non-critical extension update could halt all ingestion.

**Handling unmapped fields** means designing an **explicit policy** for data that lacks a conversion rule from source to target structure. The policy may be to **reject, quarantine, ignore intentionally, store in a controlled extension area, or enrich from an authoritative source**. The choice must reflect the data contract, business criticality, access rights, and replay capability; never let a mapper library make business decisions unconsciously.

~~~mermaid
flowchart LR
    S["Partner order message"] --> T["Message Translator"]
    T --> M["Mapped canonical fields"]
    T --> U["Unmapped-field diagnostics"]
    U --> P{"Policy"}
    P -->|Known safe to ignore| I["Accept + audit warning"]
    P -->|Unknown / critical| Q["Reject or quarantine"]
    P -->|Approved extension| X["Protected extension bag"]
    M --> V["Validate canonical result"]
    I --> V
    X --> V
    V --> B["Business flow if accepted"]
~~~

This lesson belongs to the **Message translator** chapter in the `SPRING_INTEGRATION_PATTERN` module. The learning objective is to implement Enterprise Integration Patterns with Spring Integration to build loosely coupled, extensible message flows; practice Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation; and test/observe processing branches.

### Learning objectives

After this lesson, you will be able to:

1. Distinguish **source fields without targets**, **target fields without sources**, **named fields with unconvertible values**, **null/missing fields**, and **unrecognized fields from a new schema**.
2. Decide when to **ignore with audit**, when to **reject/quarantine**, and when to use an **extension bag or enrichment**.
3. Implement a Java translator returning `MappingResult`, `MappingIssue`, error severity, and policy version instead of reporting "success" while silently dropping fields.
4. Build a Spring Integration Java DSL flow that routes valid payloads to business flows and invalid mapping results to quarantine.
5. Test monetary values, enums, unknown fields, missing/null values, schema evolution, retries, and redeliveries.
6. Design observability, security, duplicate prevention, replay, and error handling along proper boundaries.

## 2. What does a Message Translator do—and not do?

**Message Translator** is an Enterprise Integration Pattern used to convert a message from **one data format/contract** into a format/contract understood by the consumer.

Example:

~~~text
PartnerOrderV1
   partnerOrderRef = EXT-ORD-901
   totalVnd        = "850000"
   deliveryCode    = EXP
      |
      v
Message Translator
      |
      v
NormalizedOrder
   orderId         = EXT-ORD-901
   amountVnd       = 850000
   shippingTier    = EXPRESS
~~~

In Spring Integration, a **Transformer endpoint** is commonly where a Message Translator is implemented. However:

- **Transformer** is the framework mechanism converting a payload/message; **Message Translator** emphasizes semantics and contracts between two systems.
- **Filter** decides which messages proceed; **Translator** decides how data is interpreted and transformed.
- **Router** selects channels or branches; a Translator does not itself route to the right destination.
- **Content Enricher** pulls supplemental data from another source; it is not a rule to leave gaps or fabricate missing fields.
- **Envelope Wrapper** wraps metadata around a payload; a Translator may alter the payload while still preserving required metadata.
- **Normalizer/Canonical Data Model** brings multiple sources into one internal structure; the translator is where source data enters that structure.

### 2.1. Unmapped fields are not just different names

| Source data | Target data | Situation | Action |
|---|---|---|---|
| `partnerOrderRef` | `orderId` | Rename rule exists. | Translate normally. |
| String `totalVnd` | Numeric `amountVnd` | Parse/validate rule exists. | Parse exactly; reject errors. |
| `deliveryCode=EXP` | `shippingTier=EXPRESS` | Enum mapping exists. | Map via allowlist. |
| `legacyCampaignHint` | No matching field. | **Source-only field**, approved to ignore. | Warn/audit per policy. |
| `newRiskIndicator` | No matching field. | **Unknown source field**, impact unknown. | Strict reject/quarantine or versioned policy. |
| Missing `riskDecision` | Target requires `riskDecision` | **Target-only required field**. | Enrich from authoritative source or reject; never default PASS. |
| `deliveryCode=OVERNIGHT` | Enum lacks OVERNIGHT | **Known field, unknown value**. | Mapping error; never fall back to STANDARD. |
| `totalVnd="abc"` | `amountVnd` | **Conversion error**. | Mapping error and quarantine. |
| `totalVnd=null` | `amountVnd` | **Missing/null required field**. | Validation error; never default to 0. |

Key takeaway: **No mapping** (no rule exists) differs from **valid mapping with invalid data**. Conflating the two corrupts error metrics, replays, and issue ownership.

### 2.2. Distinguish data allowed to be dropped from data that must not be lost

A field like `legacyCampaignHint` can be dropped once the business owner confirms it is unused. By contrast, a new `exportControlFlag`, `riskIndicator`, or `discountAmount` field can change how a transaction should be handled. If the parser silently drops it, transactions may be processed wrongly with no way to recover.

Therefore, maintain a **mapping contract** specifying:

- Which source fields **must be recognized**.
- Which source fields **are mapped**.
- Which fields **are permitted to be ignored** and why.
- Which fields **must be rejected/quarantined if present** or unreviewed.
- Which target fields **must have values**.
- Clear type, unit, enum, and default conversions.
- Contract version and scope per partner/source/tenant.

## 3. Five easily confused "unmapped" cases

### 3.1. Source-only: source has a field the target does not need

~~~json
{"legacyCampaignHint":"old-q4"}
~~~

Can be **intentionally ignored** if approved and unneeded downstream. Avoid logging raw values just to prove a field was ignored; usually **field name, policy version, count, and source** suffice. If PII is involved, enforce retention and access controls.

### 3.2. Target-only: target requires a field the source omits

~~~text
Target requires:
  fraudApproved: Boolean

Source provides:
  orderId, amount, deliveryCode
  (no fraudApproved)
~~~

**Never default `fraudApproved=true`.** Options:

1. Make the target field optional if the business domain genuinely permits it.
2. Apply a **contract-documented default**, e.g., a legacy partner's default shipping tier.
3. Enrich from an authoritative fraud service, with timeouts/retries and decision versioning.
4. Reject/quarantine if a required value cannot be safely established.

Missing source data may stem from **version incompatibility**, not an intentional business omission.

### 3.3. Known field, unknown value

~~~text
source.deliveryCode = OVERNIGHT
target.shippingTier = STANDARD | EXPRESS
~~~

At the field-name level, a mapping exists. Yet `OVERNIGHT` is undefined in the enum table. Defaulting to `STANDARD` would delay expedited shipments and mask the error. Policy should normally **reject/quarantine `UNKNOWN_ENUM_VALUE`** so the contract gets updated. Fall back only with business owner approval.

### 3.4. Missing, null, empty, and blank are distinct states

| State | Example | Possible meaning |
|---|---|---|
| Missing | JSON lacks `totalVnd` key. | Producer omitted it / older version. |
| Explicit null | `"totalVnd": null`. | Producer explicitly states "no value", or a bug. |
| Empty string | `"totalVnd": ""`. | Empty data, not zero. |
| Blank | `"totalVnd": "  "`. | Empty after normalization. |
| Zero | `"totalVnd": "0"`. | An actual numeric value needing business validation. |
| Malformed | `"totalVnd": "8.5.00"`. | Conversion error. |

A Java record with a nullable field **may already lose the distinction between missing and explicit null** if the JSON deserializer maps both to `null`. When the contract requires distinguishing them, inspect the raw structure/JSON node or use a presence-aware representation at ingress.

### 3.5. Unknown field from a new schema or raw parser

If a producer deploys V2 adding `newRiskIndicator` while the consumer still expects V1, many mappers either ignore unknown properties by default or throw. Never rely on mapper defaults to decide policy: **explicitly choose** forward compatibility vs. strict schema enforcement.

For sensitive schemas like payments or security, strict/quarantine catches critical new fields. For extensible analytics events, ignoring extra fields can be acceptable **with bounds and telemetry**.

## 4. Policies when no mapping is found

### 4.1. Selection matrix

| Policy | When suitable | Risks / conditions |
|---|---|---|
| **REJECT** | Mapping missing for a critical field; producer needs immediate error. | Needs structured error response; do not lose the record. |
| **QUARANTINE** | Message already entered broker; hold for analysis/schema upgrade/replay. | Store/ACK, authorization, retention, and replay must be clear. |
| **IGNORE_WITH_AUDIT** | Field is approved as non-impacting. | Emit warnings/metrics and policy version; never ignore unknown fields by default. |
| **PRESERVE_EXTENSION** | Target has a designed extension model and consumers truly need forwarding. | Allowlists, type/size bounds, security, versioning; never allow arbitrary keys. |
| **ENRICH** | Target field requires data from an authoritative source. | Dependency timeouts, stale data, authorization, determinism, and retries. |
| **DEFAULT_EXPLICIT** | Business contract defines an explicit default, e.g., absent shipping code -> STANDARD. | Never default unknown enums, amounts, or security flags. |
| **VERSIONED_MIGRATION** | V1/V2 renames or restructures fields while preserving meaning. | Upcaster must verify equivalence; never guess missing values. |

### 4.2. Defaults are a business decision

**Allowed** (when contracted):

~~~text
Partner V1:
  deliveryCode absent means STANDARD

Mapping:
  absent -> ShippingTier.STANDARD
~~~

**Never invent arbitrarily**:

~~~text
Partner:
  totalVnd missing

Mapping:
  missing -> BigDecimal.ZERO
  then send to payment
~~~

Even a `STANDARD` default is valid only when the **field is absent** as specified in the contract. If a producer sends an unsupported `deliveryCode="SAME_DAY"`, that is an **unknown value** to handle separately, not a missing field.

### 4.3. Per-partner and per-version policies

~~~text
Partner A, contract v1:
  allowedIgnored = [legacyCampaignHint]
  unknownSourceFields = QUARANTINE
  deliveryCode missing = STANDARD

Partner B, contract v2:
  allowedIgnored = [marketingTrace]
  unknownSourceFields = IGNORE_WITH_AUDIT
  deliveryCode missing = ERROR
~~~

Do not apply the loosest policy to every tenant/partner. Policy changes can alter whether old inputs are accepted or rejected, so track **`policyVersion`**, deployment audits, and migration strategies.

### 4.4. Do not lose data before identifying unknown fields

~~~text
Raw JSON
  -> Generic deserializer silently ignores unknown fields
  -> Typed PartnerOrderInput (newRiskIndicator already dropped)
  -> Translator cannot report unmapped newRiskIndicator
~~~

To detect unmapped source fields, **ingress parsing must preserve or report field names**. Use:

- Schema validation with **unknown-properties reporting**.
- Jackson `JsonNode`/tree parsing before binding typed DTOs.
- `@JsonAnySetter` or a bounded extension map, where appropriate.
- Contract registries or generated schemas with strict decoding.

**Do not** slurp unbounded raw JSON into a map "just to be safe": enforce field count, length, nesting depth, and payload size limits, and block dangerous data.

## 5. Java design: source, target, and trusted context

Examples target **Java 17+, Spring Boot 3.x, and Spring Integration 6.x**. Records/classes in the lesson belong in the same package and should be split into their respective Java files in a real project. They are educational examples, not compiled here, and not a production order schema.

### 5.1. Source DTO with known fields and extension fields

~~~java
import java.util.Map;

record PartnerOrderInput(
        String eventId,
        String partnerOrderRef,
        String totalVnd,
        String deliveryCode,
        Map<String, String> extraFields) {

    PartnerOrderInput {
        extraFields = extraFields == null
                ? Map.of()
                : Map.copyOf(extraFields);
    }
}
~~~

`extraFields` **illustrates decoded fields lacking a mapping**. If a JSON parser already dropped unknown fields before instantiating the record, the translator cannot recover lost field names. The map assumes non-null values because `Map.copyOf` rejects null keys/values; if the wire format distinguishes explicit nulls, use a richer ingress structure and parser validation.

### 5.2. Trusted ingress must never come directly from self-declared JSON

~~~java
record TrustedPartnerIngress(
        String authenticatedPartner,
        String authenticatedTenant,
        PartnerOrderInput payload) {

    TrustedPartnerIngress {
        if (authenticatedPartner == null
                || authenticatedPartner.isBlank()
                || authenticatedTenant == null
                || authenticatedTenant.isBlank()
                || payload == null) {
            throw new IllegalArgumentException(
                    "INVALID_TRUSTED_INGRESS");
        }
    }
}
~~~

In the demo, tests construct `TrustedPartnerIngress` directly to focus on mapping. In production, partner and tenant must be **authenticated/authorized at the adapter boundary**, never trusting a remote caller setting a header named `authenticatedPartner`.

### 5.3. Target canonical DTO

~~~java
import java.math.BigDecimal;

enum ShippingTier {
    STANDARD, EXPRESS
}

record NormalizedOrder(
        String sourceEventId,
        String orderId,
        BigDecimal amountVnd,
        ShippingTier shippingTier,
        String sourcePartner,
        String tenantId) {}
~~~

Neither `legacyCampaignHint` nor `newRiskIndicator` appears in `NormalizedOrder`: that is **by canonical contract design**. If consumers need a new field, evolve the business/data contract intentionally rather than smuggling it into other metadata to dodge mapping errors.

### 5.4. Mapping result with severity, reason, and version

~~~java
import java.util.List;
import java.util.Objects;

enum MappingSeverity {
    WARNING, ERROR
}

record MappingIssue(
        String code,
        String field,
        MappingSeverity severity) {
    MappingIssue {
        if (code == null || code.isBlank()
                || severity == null) {
            throw new IllegalArgumentException(
                    "INVALID_MAPPING_ISSUE");
        }
    }
}

record MappingResult(
        TrustedPartnerIngress original,
        NormalizedOrder normalized,
        List<MappingIssue> issues,
        String mappingVersion) {

    MappingResult {
        Objects.requireNonNull(original, "original");
        issues = List.copyOf(issues);
        if (mappingVersion == null || mappingVersion.isBlank()) {
            throw new IllegalArgumentException(
                    "INVALID_MAPPING_VERSION");
        }
    }

    boolean accepted() {
        return normalized != null
                && issues.stream().noneMatch(
                        issue -> issue.severity()
                                == MappingSeverity.ERROR);
    }
}
~~~

**Why return `MappingResult` instead of just `NormalizedOrder`?** Because:

- Consumers see clear mapping success/warning/failure outcomes.
- Intentionally ignored fields can still produce a **warning** without breaking output.
- Unapproved unknown fields can produce an **error** and route to quarantine.
- Mapping version explains why the same payload behaves differently before/after a deploy.
- Error handlers receive structured issues instead of parsing exception text.

Not all errors come from "unknown fields"; `MISSING_REQUIRED_FIELD`, `INVALID_DECIMAL`, and `UNSUPPORTED_ENUM_VALUE` still need distinct reason codes.

## 6. Translator with an explicit unmapped-field policy

### 6.1. Choosing strict vs. forward-compatible per contract

~~~java
enum UnknownFieldMode {
    STRICT_QUARANTINE,
    WARN_AND_IGNORE
}
~~~

`STRICT_QUARANTINE` means the translator **marks the result not accepted** so a Spring Filter routes it to quarantine; the enum/translator itself does not write to broker queues. `WARN_AND_IGNORE` should be used only for partners/schemas whose business owner approved accepting new extension keys, with rate monitoring.

### 6.2. Concrete mapping rules

| Source | Target | Rule |
|---|---|---|
| `eventId` | `sourceEventId` | Required, stable across redeliveries. |
| `partnerOrderRef` | `orderId` | Required; do not blindly trim/alter IDs if whitespace is significant. |
| `totalVnd` | `amountVnd` | Positive whole-digit string, bounded, exact `BigDecimal` parse. |
| `deliveryCode=STD` | `shippingTier=STANDARD` | Approved enum mapping. |
| `deliveryCode=EXP` | `shippingTier=EXPRESS` | Approved enum mapping. |
| `deliveryCode` absent | `shippingTier=STANDARD` | Default **only** because the example assumes partner contract allows it. |
| `deliveryCode` other value | No valid output produced | `UNSUPPORTED_DELIVERY_CODE`. |
| `extraFields.legacyCampaignHint` | No target | Ignore with warning because it is allowlisted. |
| Remaining `extraFields` | No target | Strict reject/quarantine, or warning if policy is lenient. |
| Authenticated partner/tenant | `sourcePartner/tenantId` | Only from trusted context, never inferred from payload. |

### 6.3. Pure Java Translator with no external service calls

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;

final class PartnerOrderTranslator {
    static final String MAPPING_VERSION = "partner-order-v1";
    private static final BigDecimal MAX_VND =
            new BigDecimal("1000000000000");
    private static final Set<String> ALLOWED_IGNORED_FIELDS =
            Set.of("legacyCampaignHint");

    private final UnknownFieldMode unknownFieldMode;

    PartnerOrderTranslator(UnknownFieldMode unknownFieldMode) {
        this.unknownFieldMode = unknownFieldMode;
    }

    MappingResult translate(TrustedPartnerIngress ingress) {
        PartnerOrderInput input = ingress.payload();
        List<MappingIssue> issues = new ArrayList<>();

        String eventId = input.eventId();
        if (missing(eventId)) {
            issues.add(error(
                    "MISSING_EVENT_ID", "eventId"));
        }

        String orderId = input.partnerOrderRef();
        if (missing(orderId)) {
            issues.add(error(
                    "MISSING_ORDER_ID", "partnerOrderRef"));
        }

        BigDecimal amount = parseAmount(
                input.totalVnd(), issues);

        ShippingTier tier = mapShipping(
                input.deliveryCode(), issues);

        for (Map.Entry<String, String> extra
                : input.extraFields().entrySet()) {
            if (ALLOWED_IGNORED_FIELDS.contains(extra.getKey())) {
                issues.add(warning(
                        "IGNORED_LEGACY_FIELD", extra.getKey()));
            } else if (unknownFieldMode
                    == UnknownFieldMode.STRICT_QUARANTINE) {
                issues.add(error(
                        "UNMAPPED_SOURCE_FIELD", extra.getKey()));
            } else {
                issues.add(warning(
                        "UNMAPPED_SOURCE_FIELD_IGNORED",
                        extra.getKey()));
            }
        }

        boolean hasErrors = issues.stream().anyMatch(
                issue -> issue.severity()
                        == MappingSeverity.ERROR);

        NormalizedOrder normalized = hasErrors
                ? null
                : new NormalizedOrder(
                        eventId,
                        orderId,
                        amount,
                        tier,
                        ingress.authenticatedPartner(),
                        ingress.authenticatedTenant());

        return new MappingResult(
                ingress, normalized, issues, MAPPING_VERSION);
    }

    private static BigDecimal parseAmount(
            String raw, List<MappingIssue> issues) {
        if (missing(raw)) {
            issues.add(error(
                    "MISSING_AMOUNT", "totalVnd"));
            return null;
        }
        // Illustrative contract: integer VND, no commas or decimal points.
        // Reject overly long strings before creating BigDecimal.
        if (raw.length() > 20 || !raw.matches("[0-9]+")) {
            issues.add(error(
                    "INVALID_AMOUNT_FORMAT", "totalVnd"));
            return null;
        }
        BigDecimal value = new BigDecimal(raw);
        if (value.signum() <= 0 || value.compareTo(MAX_VND) > 0) {
            issues.add(error(
                    "AMOUNT_OUT_OF_RANGE", "totalVnd"));
            return null;
        }
        return value;
    }

    private static ShippingTier mapShipping(
            String code, List<MappingIssue> issues) {
        if (missing(code)) {
            // Valid only because the assumed partner V1 contract permits it.
            issues.add(warning(
                    "SHIPPING_DEFAULT_APPLIED", "deliveryCode"));
            return ShippingTier.STANDARD;
        }
        return switch (code) {
            case "STD" -> ShippingTier.STANDARD;
            case "EXP" -> ShippingTier.EXPRESS;
            default -> {
                issues.add(error(
                        "UNSUPPORTED_DELIVERY_CODE", "deliveryCode"));
                yield null;
            }
        };
    }

    private static boolean missing(String value) {
        return value == null || value.isBlank();
    }

    private static MappingIssue error(String code, String field) {
        return new MappingIssue(
                code, field, MappingSeverity.ERROR);
    }

    private static MappingIssue warning(String code, String field) {
        return new MappingIssue(
                code, field, MappingSeverity.WARNING);
    }
}
~~~

### 6.4. Rationale behind key details in the code

1. **Uses `BigDecimal`**, avoiding binary floating-point rounding errors from `double`.
2. **Caps string length before parsing**, preventing huge numeric strings from wasting CPU/memory.
3. **Defaults missing shipping only per contract**, never falling back for unsupported values.
4. **Issues store codes and field names**, never raw emails, risk scores, or tokens.
5. **Takes partner/tenant from trusted ingress**, preventing source fields from overriding them.
6. **Returns null `NormalizedOrder` on errors**, preventing partial mappings from entering business flows.
7. **Emits warnings when ignoring fields**, making schema drift visible without conflating it with failures.
8. **Pins `MAPPING_VERSION` to the rules**, updated whenever allowlists, defaults, or semantics change.

In the demo, `extraFields` stays inside `MappingResult.original` and could contain sensitive data. Production needs an encrypted, retention-controlled store/reference—never log or publish full `MappingResult` objects to shared subscribers.

### 6.5. Do not turn `WARN_AND_IGNORE` into permission to ignore everything

A lenient policy may suit low-risk event tracking, provided you enforce:

- Allowed partner and schema versions.
- Max extra fields/bytes/nesting at ingress.
- `UNMAPPED_SOURCE_FIELD_IGNORED` alerts keyed by **sanitized field name**.
- Rate/threshold alerts to spot new producer rollouts.
- A list of **critical fields** that must never be ignored.
- Review SLAs to promote unknown fields to mapped, allowlisted, or blocked.

Never let senders specify `unknownFieldMode=WARN_AND_IGNORE` in the payload. The mode must come from the consumer's trusted policy.

## 7. Source-only vs. target-only fields: different solutions

### 7.1. Source-only is not automatically an error

A partner might include `marketingTrace` solely for its own dashboard. If canonical `NormalizedOrder` does not need it and the contract confirms this, **ignore with audit** is appropriate—provided it does not alter the meaning of mapped fields and no downstream policy depends on it.

### 7.2. Target-only required fields must be resolved before the business handler

Target requires `riskApproval`, which the source does not provide:

~~~mermaid
flowchart LR
    S["Partner order"] --> T["Translator"]
    T --> M{"Target riskApproval required?"}
    M -->|No| B["Create canonical order"]
    M -->|Yes| E["Trusted risk enrichment / validation"]
    E -->|Approved result| B
    E -->|Unavailable or unknown| Q["Retry technical / quarantine by reason"]
~~~

Never default `riskApproval=APPROVED`. If enrichment calls an external service, it may time out or return different results across retries; define contracts for **snapshots, versions, correlation**, retries, and authorization. A pure deterministic translator is easier to test; isolating external lookups in a Content Enricher endpoint clarifies boundaries.

### 7.3. Null is not a free "default"

Suppose `target.discountPercent` has no value:

- If the domain explicitly means "no discount applies", an optional/zero representation **per contract** can work.
- If missing discount data changes the amount to charge, never default to 0 and run payment without knowing whether source pricing completed.
- If the target field means "unknown", use an intentional **UNKNOWN/Optional** representation rather than equating it with `false`.

**Principle:** safe defaults must follow **verified semantics**, not the fact that a Java constructor or serializer demands a value.

## 8. Spring Integration: translator + filter + quarantine

### 8.1. Flow design

A clean, testable layout:

~~~mermaid
flowchart LR
    INPUT["partner.order.input"] --> TRANSFORM["PartnerOrderTranslator"]
    TRANSFORM --> OUT["MappingResult"]
    OUT --> CHECK{"accepted()"}
    CHECK -->|True| NORM["NormalizedOrder"]
    NORM --> BUS["orders.normalized -> business handler"]
    CHECK -->|False| Q["partner.mapping.quarantine"]
    Q --> STORE["Quarantine writer + audit"]
~~~

We **do not throw exceptions** for unknown fields as unexpected Java failures when that is an expected validation outcome. The Translator returns `MappingResult`; the Filter separates accepted and rejected items. If the translator hits an actual bug or the quarantine store fails, that is a **technical exception** requiring separate recovery/error policies.

### 8.2. Two test-only probes

~~~java
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

final class AcceptedOrderProbe {
    private final List<NormalizedOrder> values =
            new CopyOnWriteArrayList<>();

    void accept(NormalizedOrder order) {
        values.add(order);
    }

    List<NormalizedOrder> snapshot() {
        return List.copyOf(values);
    }
}

final class MappingQuarantineProbe {
    private final List<MappingResult> rejected =
            new CopyOnWriteArrayList<>();

    void record(MappingResult result) {
        if (result.accepted()) {
            throw new IllegalArgumentException(
                    "CANNOT_QUARANTINE_ACCEPTED_RESULT");
        }
        rejected.add(result);
    }

    List<MappingResult> snapshot() {
        return List.copyOf(rejected);
    }
}
~~~

**Warning:** Probes keep data in memory only. If the application must **never lose messages** on crashes, replace them with a durable quarantine DB/queue and design ACKs, idempotency, retention, and authorization. Never log full `MappingResult.original` payloads into structured logs, as they may contain private data.

### 8.3. Illustrative Java DSL flow

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
class MessageTranslatorConfiguration {

    @Bean(name = "partner.order.input")
    MessageChannel partnerInput() {
        return new DirectChannel();
    }

    @Bean(name = "orders.normalized")
    MessageChannel normalizedOutput() {
        return new DirectChannel();
    }

    @Bean(name = "partner.mapping.quarantine")
    MessageChannel mappingQuarantine() {
        return new DirectChannel();
    }

    @Bean
    PartnerOrderTranslator partnerOrderTranslator() {
        return new PartnerOrderTranslator(
                UnknownFieldMode.STRICT_QUARANTINE);
    }

    @Bean
    AcceptedOrderProbe acceptedOrderProbe() {
        return new AcceptedOrderProbe();
    }

    @Bean
    MappingQuarantineProbe mappingQuarantineProbe() {
        return new MappingQuarantineProbe();
    }

    @Bean
    IntegrationFlow translatePartnerOrders(
            PartnerOrderTranslator translator) {
        return IntegrationFlow.from("partner.order.input")
                .transform(
                        TrustedPartnerIngress.class,
                        translator::translate)
                .filter(
                        MappingResult.class,
                        MappingResult::accepted,
                        spec -> spec.discardChannel(
                                "partner.mapping.quarantine"))
                .transform(
                        MappingResult.class,
                        MappingResult::normalized)
                .channel("orders.normalized")
                .get();
    }

    @Bean
    IntegrationFlow businessOrders(AcceptedOrderProbe probe) {
        return IntegrationFlow.from("orders.normalized")
                .handle(
                        NormalizedOrder.class,
                        (order, headers) -> {
                            probe.accept(order);
                            return null; // Terminal demo handler.
                        })
                .get();
    }

    @Bean
    IntegrationFlow quarantineMappingFailures(
            MappingQuarantineProbe probe) {
        return IntegrationFlow.from(
                        "partner.mapping.quarantine")
                .handle(
                        MappingResult.class,
                        (result, headers) -> {
                            probe.record(result);
                            return null; // Terminal demo handler.
                        })
                .get();
    }
}
~~~

### 8.4. Step-by-step walkthrough

1. Inbound adapter created a `TrustedPartnerIngress` from payload and security context.
2. `transform(...)` runs the **pure Java translator**, returning `MappingResult` with issues.
3. `filter(...)` allows messages onward only when `accepted()` is true.
4. When accepted, `transform(MappingResult::normalized)` extracts the `NormalizedOrder` payload.
5. The message flows through `orders.normalized` to the business handler.
6. When rejected, the Filter routes the **`MappingResult` with all issues intact** to `partner.mapping.quarantine`.
7. The demo quarantine handler records into a probe; production replaces it with a durable writer.

This Java DSL example follows Spring Integration 6.x design patterns. Verify exact overloads and header semantics against your project dependencies in a dedicated QA/build step; this STEP 4 did not run Gradle/Python or specialized Content QA.

### 8.5. Avoid Filter configurations that drop quarantine items

Unsafe snippet:

~~~java
// Illustrating anti-pattern only:
.filter(MappingResult.class, MappingResult::accepted)
~~~

Without a `discardChannel`, rejected messages are dropped from the business path **without being recorded**. Enabling `throwExceptionOnRejection(true)` switches semantics to exception handling per configuration instead of normal quarantine routing. Choose one **explicit, observable, tested** path.

### 8.6. When to use a Router instead of a Filter?

If there are three outcome classes:

~~~text
MappingResult.status:
  ACCEPTED_WITH_WARNING
  INVALID_BUSINESS_MAPPING
  UNSUPPORTED_SCHEMA
~~~

A Router can dispatch to three channels. For this two-branch accepted/rejected exercise, **Filter + discard** illustrates the pattern most cleanly; production can use a typed outcome plus Router to separate technical, schema, and business errors without conflating reasons.

### 8.7. Never let MessageTranslator bypass source verification

`TrustedPartnerIngress.authenticatedTenant` comes from an authorized adapter. If `NormalizedOrder.tenantId` were copied directly from a caller-supplied JSON field, the translator would become **data laundering**—stamping untrusted input as trusted. Security must be authenticated before mapping and re-verified on replay.

## 9. Unit tests: known fields and unknown fields

### 9.1. Simple fixture without a Spring context

~~~java
import java.util.Map;

final class PartnerOrderFixtures {
    static TrustedPartnerIngress ingress(
            Map<String, String> extras) {
        return new TrustedPartnerIngress(
                "PARTNER-A",
                "TENANT-A",
                new PartnerOrderInput(
                        "EVT-901",
                        "EXT-ORD-901",
                        "850000",
                        "EXP",
                        extras));
    }
}
~~~

### 9.2. All known fields map accurately

~~~java
import java.math.BigDecimal;
import java.util.Map;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class PartnerOrderTranslatorHappyPathTest {
    @Test
    void knownFieldsTranslateToCanonicalValues() {
        PartnerOrderTranslator translator =
                new PartnerOrderTranslator(
                        UnknownFieldMode.STRICT_QUARANTINE);

        MappingResult result = translator.translate(
                PartnerOrderFixtures.ingress(Map.of()));

        assertTrue(result.accepted());
        assertEquals("EXT-ORD-901",
                result.normalized().orderId());
        assertEquals(new BigDecimal("850000"),
                result.normalized().amountVnd());
        assertEquals(ShippingTier.EXPRESS,
                result.normalized().shippingTier());
        assertEquals("TENANT-A",
                result.normalized().tenantId());
        assertEquals("partner-order-v1",
                result.mappingVersion());
    }
}
~~~

### 9.3. Allowlisted ignored field emits a warning

~~~java
import java.util.Map;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class AllowlistedUnmappedFieldTest {
    @Test
    void legacyFieldIsIgnoredWithDiagnostic() {
        PartnerOrderTranslator translator =
                new PartnerOrderTranslator(
                        UnknownFieldMode.STRICT_QUARANTINE);
        MappingResult result = translator.translate(
                PartnerOrderFixtures.ingress(
                        Map.of("legacyCampaignHint", "old-q4")));

        assertTrue(result.accepted());
        assertEquals("IGNORED_LEGACY_FIELD",
                result.issues().get(0).code());
        assertEquals(MappingSeverity.WARNING,
                result.issues().get(0).severity());
    }
}
~~~

### 9.4. Unknown field in strict mode must block business processing

~~~java
import java.util.Map;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertEquals;

class StrictUnmappedFieldTest {
    @Test
    void unknownFieldCannotSilentlyReachBusiness() {
        PartnerOrderTranslator translator =
                new PartnerOrderTranslator(
                        UnknownFieldMode.STRICT_QUARANTINE);
        MappingResult result = translator.translate(
                PartnerOrderFixtures.ingress(
                        Map.of("newRiskIndicator", "high")));

        assertFalse(result.accepted());
        assertNull(result.normalized());
        assertEquals("UNMAPPED_SOURCE_FIELD",
                result.issues().get(0).code());
        assertEquals(MappingSeverity.ERROR,
                result.issues().get(0).severity());
    }
}
~~~

Here "blocking business processing" means `MappingResult.accepted() == false`. Actual routing to quarantine is verified by the **Spring Flow integration test**, not solely by translator unit tests.

### 9.5. Lenient mode passes only when policy permits

~~~java
import java.util.Map;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.assertEquals;

class LenientUnmappedFieldTest {
    @Test
    void ignoredUnknownFieldStillProducesWarning() {
        PartnerOrderTranslator translator =
                new PartnerOrderTranslator(
                        UnknownFieldMode.WARN_AND_IGNORE);

        MappingResult result = translator.translate(
                PartnerOrderFixtures.ingress(
                        Map.of("newRiskIndicator", "high")));

        assertTrue(result.accepted());
        assertEquals("UNMAPPED_SOURCE_FIELD_IGNORED",
                result.issues().get(0).code());
    }
}
~~~

**Do not use this lenient test as justification to enable lenient mode on payment/risk flows.** It merely demonstrates the semantics of a mode that requires explicit business contract approval.

### 9.6. New enum value vs. missing field

~~~java
import java.util.Map;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ShippingMappingTest {
    private final PartnerOrderTranslator translator =
            new PartnerOrderTranslator(
                    UnknownFieldMode.STRICT_QUARANTINE);

    @Test
    void unsupportedNewEnumIsErrorNotDefault() {
        TrustedPartnerIngress input = new TrustedPartnerIngress(
                "PARTNER-A", "TENANT-A",
                new PartnerOrderInput(
                        "EVT-1", "ORD-1", "100000",
                        "OVERNIGHT", Map.of()));

        MappingResult result = translator.translate(input);
        assertFalse(result.accepted());
        assertEquals("UNSUPPORTED_DELIVERY_CODE",
                result.issues().get(0).code());
    }

    @Test
    void absentShippingGetsContractualDefaultAndWarning() {
        TrustedPartnerIngress input = new TrustedPartnerIngress(
                "PARTNER-A", "TENANT-A",
                new PartnerOrderInput(
                        "EVT-2", "ORD-2", "100000",
                        null, Map.of()));

        MappingResult result = translator.translate(input);
        assertTrue(result.accepted());
        assertEquals(ShippingTier.STANDARD,
                result.normalized().shippingTier());
        assertEquals("SHIPPING_DEFAULT_APPLIED",
                result.issues().get(0).code());
    }
}
~~~

### 9.7. Monetary amounts must never be parsed by guessing

~~~java
import java.util.Map;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertEquals;

class AmountMappingTest {

    @Test
    void invalidAmountCannotProduceCanonicalOrder() {
        PartnerOrderTranslator translator =
                new PartnerOrderTranslator(
                        UnknownFieldMode.STRICT_QUARANTINE);
        TrustedPartnerIngress input = new TrustedPartnerIngress(
                "PARTNER-A", "TENANT-A",
                new PartnerOrderInput(
                        "EVT-3", "ORD-3", "8,500.00",
                        "STD", Map.of()));

        MappingResult result = translator.translate(input);
        assertFalse(result.accepted());
        assertEquals("INVALID_AMOUNT_FORMAT",
                result.issues().get(0).code());
    }
}
~~~

In this demo, `totalVnd` is contracted as an **integer string without thousands separators**, so `"8,500.00"` is not guessed as `8500` or `8.5`. If a partner supports another locale or currency, write a dedicated, tested, versioned converter with explicit units.

## 10. Integration tests: rejected messages actually go to quarantine

### 10.1. Accepted orders reach only the business handler

~~~java
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringJUnitConfig(MessageTranslatorConfiguration.class)
@DirtiesContext(classMode =
        DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class MessageTranslatorAcceptedIntegrationTest {

    @Autowired
    @Qualifier("partner.order.input")
    MessageChannel input;

    @Autowired
    AcceptedOrderProbe business;

    @Autowired
    MappingQuarantineProbe quarantine;

    @Test
    void knownFieldsBecomeOneNormalizedOrder() {
        assertTrue(input.send(
                MessageBuilder.withPayload(
                        PartnerOrderFixtures.ingress(Map.of()))
                        .build()));

        assertEquals(1, business.snapshot().size());
        assertEquals(0, quarantine.snapshot().size());
        assertEquals("EXT-ORD-901",
                business.snapshot().get(0).orderId());
    }
}
~~~

### 10.2. Unknown field in strict mode reaches only quarantine

~~~java
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringJUnitConfig(MessageTranslatorConfiguration.class)
@DirtiesContext(classMode =
        DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class MessageTranslatorQuarantineIntegrationTest {

    @Autowired
    @Qualifier("partner.order.input")
    MessageChannel input;

    @Autowired
    AcceptedOrderProbe business;

    @Autowired
    MappingQuarantineProbe quarantine;

    @Test
    void strictUnknownFieldDoesNotLeakIntoBusiness() {
        assertTrue(input.send(
                MessageBuilder.withPayload(
                        PartnerOrderFixtures.ingress(
                                Map.of("newRiskIndicator", "high")))
                        .build()));

        assertEquals(0, business.snapshot().size());
        assertEquals(1, quarantine.snapshot().size());
        MappingResult rejected =
                quarantine.snapshot().get(0);
        assertFalse(rejected.accepted());
        assertEquals("UNMAPPED_SOURCE_FIELD",
                rejected.issues().get(0).code());
        assertEquals("partner-order-v1",
                rejected.mappingVersion());
    }
}
~~~

**Significance:** using the demo's synchronous `DirectChannel` and probes, the integration test traverses `Transformer → Filter → discard channel → quarantine handler`, rather than merely calling a plain Java method.

**Limitations:** a channel named "quarantine" and an in-memory list do not prove durability. There is no broker, DB, retry, ACK, security principal, or real JSON decoder in this test.

### 10.3. Known ignored field reaches business while preserving warning

~~~java
import java.util.Map;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.assertEquals;

class MappingWarningOnlyTest {
    @Test
    void allowlistedLegacyFieldDoesNotBlockMapping() {
        PartnerOrderTranslator translator =
                new PartnerOrderTranslator(
                        UnknownFieldMode.STRICT_QUARANTINE);
        MappingResult result = translator.translate(
                PartnerOrderFixtures.ingress(
                        Map.of("legacyCampaignHint", "retired")));

        assertTrue(result.accepted());
        assertEquals(1, result.issues().size());
        assertEquals(MappingSeverity.WARNING,
                result.issues().get(0).severity());
        assertEquals("EXT-ORD-901",
                result.normalized().orderId());
    }
}
~~~

The accepted branch should emit **sanitized warning metrics/logs** rather than forwarding the entire source object with unused extra values to the business handler. In the sample flow, the business handler receives `NormalizedOrder` after the second transform, not `MappingResult.original`.

### 10.4. Verifying Header and Event ID at the boundary

An inbound adapter may construct a new Spring `Message<TrustedPartnerIngress>` with a fresh `MessageHeaders.ID` on each redelivery. Logical `sourceEventId` must come from the source event/operation identity, not `MessageHeaders.ID`.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;

class SourceEventIdentityTest {
    @Test
    void twoSpringMessagesCanCarrySameLogicalEvent() {
        TrustedPartnerIngress same =
                PartnerOrderFixtures.ingress(java.util.Map.of());
        Message<TrustedPartnerIngress> first =
                MessageBuilder.withPayload(same).build();
        Message<TrustedPartnerIngress> retry =
                MessageBuilder.withPayload(same).build();

        assertNotEquals(
                first.getHeaders().getId(),
                retry.getHeaders().getId());

        PartnerOrderTranslator translator =
                new PartnerOrderTranslator(
                        UnknownFieldMode.STRICT_QUARANTINE);

        assertEquals(
                translator.translate(first.getPayload())
                        .normalized().sourceEventId(),
                translator.translate(retry.getPayload())
                        .normalized().sourceEventId());
    }
}
~~~

This only proves JVM Message IDs can differ when **creating two message objects**, not that every transport preserves or changes IDs identically. Test concrete adapters to verify wire metadata mapping.

## 11. "Unseen" fields may have been lost before the Translator

### 11.1. JSON binding defaults can mask schema drift

Suppose the client adds:

~~~json
{
  "partnerOrderRef": "EXT-ORD-901",
  "totalVnd": "850000",
  "deliveryCode": "EXP",
  "newRiskIndicator": "high"
}
~~~

If Jackson/JSON mapper is configured to **ignore unknown properties** silently, `newRiskIndicator` vanishes during DTO binding. The Translator sees only bound fields and reports **accepted**, even though the raw source carried unhandled data.

Conversely, a strict deserializer may throw **`UnrecognizedPropertyException`** before the translator runs; that case must go through **adapter/parser error handling**, not the typed mapping result's `discardChannel`.

### 11.2. Parse as a tree or with a schema-aware decoder

Recommended pseudo-flow:

~~~text
Raw JSON bytes (bounded by size/depth)
  -> Authenticate producer / tenant
  -> Detect schema version, event type
  -> Enumerate declared source property names
  -> Compare against known schema + approved extensions
  -> Decode typed PartnerOrderInput with extraFields
  -> PartnerOrderTranslator
  -> MappingResult
~~~

With Jackson, `JsonNode`/tree models help inspect names before binding. However, that does **not** mean retaining every unknown value in memory; many systems need only a **sanitized list of field names** plus a protected raw reference for investigation.

### 11.3. Parse errors differ from mapping errors

| Scenario | Where error occurs | Handling channel |
|---|---|---|
| Truncated JSON | Parser/deserializer | Adapter technical/error/DLQ or raw quarantine. |
| Valid JSON object with new key | Schema-aware parser/translator | Unknown-property policy: reject/warn/quarantine. |
| `totalVnd` is a JSON array instead of string | Deserializer/contract validation | Raw schema violation, before typed translator. |
| `totalVnd="abc"` string | Translator | `INVALID_AMOUNT_FORMAT`. |
| Enum `OVERNIGHT` string | Translator | `UNSUPPORTED_DELIVERY_CODE`. |
| Quarantine DB unreachable | Quarantine writer | Technical retry/backpressure; never mark source invalid. |

Do not catch every `RuntimeException` at ingress and label it `UNMAPPED_FIELD`. Proper error classification determines retries and ownership (producer, mapping team, platform).

### 11.4. Duplicate JSON property keys

~~~json
{
  "totalVnd": "850000",
  "totalVnd": "0"
}
~~~

A parser may pick one value on duplicate keys, silently altering monetary meaning. For critical data, enforce **duplicate-key detection / strict parsing** per policy—never expect an already-bound Java `Map` to recover both historical values.

### 11.5. Case-insensitive mapping and aliases need limits

Names like:

~~~text
totalVnd
TotalVnd
total_vnd
total-vnd
~~~

do not automatically mean the same field across all schemas. Aliases may be supported per version and producer, yet if a single message carries both `totalVnd` and `total_vnd` with conflicting values, report **`AMBIGUOUS_FIELD_ALIAS`** instead of picking the last one. Never enable case-insensitive matching to hide contract drift without auditing.

## 12. When should unmapped fields live in an extension bag?

### 12.1. An extension bag is a contract, not a trash can

Some domains design explicit extensibility:

~~~json
{
  "orderId": "ORD-901",
  "amountVnd": 850000,
  "extensions": {
    "partnerA.campaignHint": "winter"
  }
}
~~~

Here extensions have **namespaces, allowlists, types, size limits, and authorization**. Consumers that understand an extension use it; others ignore it safely. Even then, never allow a self-declared `"riskApproved": true` inside extensions to bypass real risk checks.

### 12.2. Risks to avoid

- **Mass assignment:** client sends a field named like an internal property to overwrite status, tenant, or permissions.
- **PII leakage:** extension carries email, tokens, or addresses and gets forwarded to many recipients.
- **Schema shadowing:** both canonical `amountVnd` and `extensions.amountVnd` appear with conflicting values.
- **Payload inflation:** thousands of keys or huge values exhausting memory/network.
- **Executable/type hints:** fields interpreted as class names, SpEL expressions, or URLs executed automatically.
- **Replay ambiguity:** an extension ignored on the first attempt gets read on a later attempt after a code upgrade, changing the outcome for the same event.

If an application genuinely needs partner-specific metadata, place it in a **distinct, versioned extension area**, never randomly inside core `NormalizedOrder` or untrusted Spring Message headers.

### 12.3. Field-sensitive policies

A production contract should express:

~~~text
partnerA.schemaV1:
  ignored fields:
    legacyCampaignHint -> WARNING

  mapped extensions:
    partnerA.promoReference -> approved string, maxLength=64

  forbidden fields:
    rawPassword
    bearerToken
    privilegedRole

  unknown fields:
    STRICT_QUARANTINE
~~~

This list is a **policy template**, not default Spring Integration config. Implementation must ensure the parser detects fields before ignoring them and never logs raw sensitive values inside reason codes.

## 13. Mapping contracts and schema evolution

### 13.1. An additive field change can still alter meaning

Producer V1:

~~~json
{
  "partnerOrderRef": "ORD-901",
  "totalVnd": "850000",
  "deliveryCode": "STD"
}
~~~

Producer V2:

~~~json
{
  "partnerOrderRef": "ORD-901",
  "totalVnd": "850000",
  "deliveryCode": "STD",
  "taxIncluded": false
}
~~~

The new field `taxIncluded=false` can **change the meaning of the amount**. If V1 assumed tax was already included, ignoring `taxIncluded` corrupts the canonical amount even though `totalVnd` parses cleanly.

**An unknown field is not always independent of known fields.** Whenever a producer changes its schema, review business semantics rather than just counting unmapped fields.

### 13.2. Schema version must be identified at ingress

A wire envelope should state:

~~~text
eventType=partner.order.submitted
schemaVersion=2
authenticatedPartner=PARTNER-A
payload={...}
~~~

For unsupported versions, choose:

- **Reject/quarantine** with `UNSUPPORTED_SCHEMA_VERSION`.
- **Upcast/downcast** using a designed, tested data mapping.
- **Dual-read migration** (consumer supporting V1 and V2) during transition.

Never feed schema V2 into a V1 translator with default unknown-ignoring enabled—especially in domains involving money, risk, fulfillment, or access control.

### 13.3. Backward/forward compatibility goes beyond compilation

| Producer change | V1 consumer | Decision |
|---|---|---|
| Add optional field with no business impact | Acceptable. | Allowlisted ignore + warning or extension. |
| Add field affecting price calculation | Unsafe to ignore. | New mapping/version; quarantine old. |
| Rename `totalVnd` → `grossVnd` | V1 misses required field. | Versioned alias/migration. |
| Change unit VND → USD | Number parses, semantics wrong. | Currency-aware conversion; never guess. |
| Add `deliveryCode` enum value | V1 does not recognize value. | Explicit mapping or unsupported enum. |
| Remove optional source field | Acceptable per contract. | Default or optional target. |
| Remove required source field | V1 cannot build valid canonical order. | Reject or authoritative enrichment. |
| Change null semantics | Risk of wrong default. | Presence-aware migration/testing. |
| Add nested object | Parser/mapper may drop whole subtree. | Schema validation and nested mapping diagnostics. |

### 13.4. Version mapping rules alongside code

A mapping registry/ruleset might record:

~~~text
mappingPolicyId = partnerA-order
mappingVersion  = 2026-11
sourceSchema    = partner.order.v2
targetSchema    = normalized.order.v3
acceptedSources = [PARTNER-A]
unknownFields   = QUARANTINE
approvedIgnored = [legacyCampaignHint]
defaults        = [deliveryCode absent -> STANDARD]
~~~

Values are illustrative. For quarantined records, you must be able to see **which policy applied on initial receipt** and which new policy ran during replay. Never overwrite old records and erase the original rejection reasons.

### 13.5. Do not confuse schema version with business version

`sourceSchemaVersion=2` is the message representation version, not `orderVersion=2` of a business order. A Resequencer ordering order mutations must use a clearly defined business sequence/aggregate version, never the schema version.

## 14. Mapper libraries: convenient, not a replacement for business contracts

### 14.1. Manual mapping, MapStruct, and serializers compared

| Tool/approach | Best suited for | What must still be added |
|---|---|---|
| Plain Java like `PartnerOrderTranslator` | Conditional rules, diagnostics, value validation. | Maintenance as fields grow; unit/contract tests. |
| MapStruct | Mapping typed Java beans/records and catching unmapped target/source fields at compile time. | Business policy, raw unknown JSON, security, recovery. |
| Jackson/ObjectMapper | JSON ↔ Java objects, schema binding, configurable unknown-property behavior. | Semantic mapping, currency/enum/defaults, audit. |
| JSON Schema/Avro/Protobuf | Defining/validating wire schemas and compatibility. | Canonical domain translation, authorization, idempotency. |
| Custom dynamic mapping config | Many partners/schemas and runtime rules. | Versioning, validation/sandboxing, performance, provenance. |

### 14.2. Compile-time unmapped targets differ from runtime unknown sources

With MapStruct, `unmappedTargetPolicy` catches unmapped **target fields** at build time. `unmappedSourcePolicy` can warn on unused source fields in the **typed source model**, depending on mapper version and settings.

~~~java
// Policy annotation illustration when the project has a MapStruct dependency.
// Not compiled in STEP 4; does not replace contract tests.
import org.mapstruct.Mapper;
import org.mapstruct.ReportingPolicy;

@Mapper(
    unmappedTargetPolicy = ReportingPolicy.ERROR,
    unmappedSourcePolicy = ReportingPolicy.WARN
)
interface MappingPolicyExample {
    // Generated mapper methods are declared here.
}
~~~

**Important:**

- Compile-time warnings see only fields in the **Java source type**, unaware of unknown JSON fields dropped by the parser.
- A `Map<String, Object> extensions` holds unbounded runtime keys that the compiler cannot enumerate.
- Auto-mapping by field name in MapStruct does not guarantee matching semantics or units.
- Annotations do not replace quarantine policies, business validation, source authorization, or replay.

Never equate "zero compiler warnings" with "every critical field is mapped accurately".

### 14.3. A target field can have a mapping and still yield wrong output

Suppose the source provides `amountCents=850000` and the target expects `amountVnd`: a mapper can copy the number straight across since types match. Yet if the source is **USD cents** and the target is **VND**, the unit mapping is wrong—not a success.

For monetary values, specify:

- Source currency and minor/major units.
- Approved rounding mode and scale.
- Exchange rate and rate timestamp if converting currencies.
- Which value feeds the idempotency fingerprint.
- Negative signs, nulls, zero, and value bounds.

Never use `double` or `toString()` casually for money. If conversion requires an external FX service, treat it as enrichment with dedicated failure/recovery semantics.

### 14.4. Unknown enums must not map to a value with another business meaning

Anti-pattern:

~~~java
// Wrong if the default is not approved by the business.
ShippingTier map(String code) {
    return switch (code) {
        case "EXP" -> ShippingTier.EXPRESS;
        default -> ShippingTier.STANDARD;
    };
}
~~~

When `code="SAME_DAY"` arrives, it silently becomes `STANDARD`. Explicitly handle **`case "STD"`** and **`case "EXP"`**, and have default report `UNSUPPORTED_DELIVERY_CODE`. Only map unknown values to `STANDARD` when the contract explicitly mandates it (very rare for critical fields), and monitor its rate.

### 14.5. Field aliases: easy source of conflicting data

Suppose V1 uses `totalVnd` and V2 uses `grandTotalVnd`. During a migration window, a payload might carry **both**:

~~~json
{
  "totalVnd": "850000",
  "grandTotalVnd": "900000"
}
~~~

A mapper must not arbitrarily pick the last one or prefer the "newest" without a contract. Instead:

- Reject with `CONFLICTING_FIELD_ALIASES`.
- Accept only one name per declared schema version.
- If the contract allows both, verify they match and then take the defined canonical field.

**Never clean up contradictions by silently dropping one field.**

## 15. Idempotency and replay after fixing a mapping

### 15.1. Same event, different mapping policy

~~~text
First delivery:
  eventId=EVT-901
  mappingVersion=partner-order-v1
  newRiskIndicator unknown -> QUARANTINED

After policy change:
  eventId=EVT-901
  mappingVersion=partner-order-v2
  newRiskIndicator mapped -> ACCEPTED
~~~

This is **revalidation/retranslation of the same logical event**, not automatically a brand-new order. Keep stable source event/operation identity, replay attempt IDs, and policy version audits. Never mint a new `operationId` on every code fix and let downstream create duplicate payments.

### 15.2. Quarantine records may hold sensitive payloads requiring protection

A minimal quarantine case might carry:

~~~text
quarantineId: Q-901
trustedPartner: PARTNER-A
tenantScope: TENANT-A
sourceEventId: EVT-901
mappingVersion: partner-order-v1
sourceSchemaVersion: v2
reasonCodes: [UNMAPPED_SOURCE_FIELD]
fieldNames: [newRiskIndicator]
payloadReference: protected-object-ref
state: NEW
~~~

If the source lacks a stable `eventId`, define a **trusted ingress envelope identity** or transport coordinate + producer contract for deduplication. Never generate a new UUID on every redelivery and pretend deduplication works.

### 15.3. Quarantine differs from business failure

A translation failure before calling the business handler **usually has no business side effects yet**, though never assume that holds universally:

- The translator might sit after another endpoint with side effects.
- An enrichment lookup or audit entry might already have run.
- The broker might redeliver the same event on a different pipeline.
- A prior attempt might have reached payment, failed downstream, and been replayed.

Therefore, when reprocessing, check the **durable operation ledger/receipt** rather than assuming a prior quarantine case means nothing committed.

### 15.4. Conditions for safe replay

1. **Authorize:** operator/service is authorized to replay for that tenant, partner, and case.
2. **Fix source/schema or mapping policy:** know what changed to resolve the previously unmapped field.
3. **Preserve original:** never overwrite the raw event or initial policy outcome.
4. **Revalidate:** run the typed decoder and translator under the target policy.
5. **Check idempotency:** has the event/business operation already completed?
6. **Publish/dispatch with lineage:** keep the source event ID and attach `replayAttemptId`/`replayOf`.
7. **Audit outcome:** `ACCEPTED`, `STILL_INVALID`, `CONFLICT`, `PROCESSING_PENDING`, `COMPLETED`.

If a field still lacks a mapping, replaying 100 times only repeats the same deterministic error. Fix the data or update the policy, and keep **bounded retries** solely for technical failures.

### 15.5. Never overwrite an existing receipt after fixing a mapping

An order paid `850000` VND; after deploying a new mapping, retranslating the same source event ID produces `900000`. Do not reprocess it into a new charge or overwrite the receipt to `900000`. That is a **semantic conflict** requiring authoritative business reconciliation or a correction event, not an ignorable duplicate.

### 15.6. Source-only warnings can signal a rollout

Every ignored field in lenient mode should be observed by source, schema, and policy—not dismissed as "permanently unimportant". If `newRiskIndicator` jumps from 0% to 100%, a new producer release likely needs a mapping agreement; ignoring it indefinitely risks business errors.

## 16. Quarantine writer, acknowledgment, and technical errors

### 16.1. Mapping rejection does not mean the case is durably saved

In the demo:

~~~text
Partner input -> Translator -> MappingResult(ERROR)
   -> Filter discardChannel -> MappingQuarantineProbe
~~~

`MappingQuarantineProbe` stores items in RAM. If the JVM dies, the list disappears. Production requires a durable quarantine store or queue with clear policies for:

- Stable case identity and duplicate detection.
- Encrypted raw/typed payload references; avoid storing unnecessary secrets.
- Reason codes, field names, `mappingVersion`, `sourceSchemaVersion`, and trusted partner.
- Quotas, retention, permissions, audit trails, and cleanup.
- Replays, corrections, and versioned attempts.
- Broker ACK **only after durable handoff is confirmed** per contract.

### 16.2. Crash windows between broker and quarantine store

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant C as Consumer
    participant T as Translator / Filter
    participant Q as Durable Quarantine
    B->>C: Event EVT-901
    C->>T: Translate
    T-->>C: ERROR: UNMAPPED_SOURCE_FIELD
    C->>Q: Persist case key=(tenant,partner,eventId)
    Q-->>C: Commit success
    Note over C,B: Crash before ACK
    B->>C: Redelivery EVT-901
    C->>Q: Same case identity
    Q-->>C: Existing case / idempotent update
    C-->>B: Ack per transport policy
~~~

**This is a logical flow**, not a promise of an atomic distributed transaction between broker and database. If the DB commits while the broker ACK is lost, the message arrives again. Quarantine insert/upsert must be idempotent; verify atomicity semantics for your real backend (MongoDB/JDBC/Kafka/Redis).

### 16.3. An unavailable quarantine store does not make invalid data "valid"

~~~text
MappingResult = ERROR
Quarantine database = TIMEOUT
~~~

This is a **result-persistence failure**, never a reason to send invalid messages into business flows. Safe options:

- Bounded retry with backoff for transient store errors.
- Backpressure or pause ingestion when no safe storage is available.
- Fallback durable queue on approved infrastructure.
- Alert operations and record `QUARANTINE_WRITE_FAILED`.
- Never ACK/commit offsets blindly before securing a durable outcome when the contract requires zero loss.

### 16.4. Error channel does not replace discard channel

Spring Integration provides `errorChannel`/`ErrorMessage` for processing exceptions depending on execution model and configuration. However:

- Translator **normally returns `MappingResult(ERROR)`** → Filter routes to discard channel with no exception.
- JSON parse failure **before translator** → handled separately by the adapter/deserializer handler.
- Quarantine DB throws → technical exception, propagated or error-handled depending on direct vs. async adapters.
- Business payment throws **after translator accepted** → never relabel it `UNMAPPED_SOURCE_FIELD`.

Avoid a catch-all error flow that dumps every `Throwable` into "unknown source field quarantine". Classify accurately so retries and ownership stay clear.

### 16.5. Choosing retry behavior by error type

| Error | Immediate retry with same payload? | Policy |
|---|---|---|
| `UNMAPPED_SOURCE_FIELD` under strict v1 | Usually no. | Wait for mapping/schema update or producer fix. |
| `UNSUPPORTED_DELIVERY_CODE` | No if value is unchanged. | Update allowed mapping after review. |
| `MISSING_AMOUNT` | No if raw event is immutable. | Source correction or authorized replay. |
| `INVALID_AMOUNT_FORMAT` | No. | Investigate source encoding/contract. |
| JSON parser unavailable / misconfigured | After infra fix. | Technical error policy. |
| Quarantine database temporarily down | Bounded. | Backoff, deduplicate, no silent ACK. |
| Business API timeout | Per operation idempotency. | Reconcile `UNKNOWN` outcome. |
| Security tenant mismatch | No. | Deny/audit; never "fix" via retries. |
| Same `eventId`, different raw content | Do not treat as safe duplicate. | Conflict/quarantine/investigation. |

### 16.6. Do not wrap the entire flow in retry advice without knowing side-effect boundaries

Example:

~~~text
Inbound -> Translator -> Filter -> BusinessHandler -> Ack
~~~

If `BusinessHandler` commits and the reply/ACK is lost, retrying the whole chain re-translates the same event and may invoke business logic again. A pure deterministic Translator can be safely rerun; **business side effects still require idempotency**. Handling unmapped fields does not by itself protect against duplicate deliveries.

## 17. Metadata, Envelope Wrapper, and `MessageHeaders`

### 17.1. Changing the payload must not lose essential IDs

Suppose a `Spring Message<PartnerOrderInput>` carries headers:

~~~text
businessEventId = EVT-901
correlationId   = CHECKOUT-88
traceparent     = ...
trustedTenant   = TENANT-A (from authenticated ingress)
~~~

The Translator creates `NormalizedOrder`. The message payload changes, yet metadata needed for **tracing, correlation, and idempotency** must cross the boundary per contract. Still:

- Spring `MessageHeaders.ID` is a runtime message ID that can change when building a new message.
- Business event IDs must be preserved explicitly; never rely on framework IDs for deduplication.
- In-JVM `replyChannel`/`errorChannel` may be internal objects unsuitable for serializing to Kafka/HTTP.
- `traceparent` never grants authorization.

### 17.2. Source-only fields should not be "hidden" inside arbitrary headers

Anti-pattern:

~~~text
newRiskIndicator unmapped in payload
  -> .setHeader("newRiskIndicator", rawValue)
  -> every downstream consumer receives it
~~~

This does not solve missing mappings—it merely **relocates the data**. If the field holds risk or PII data, it leaks information. Place metadata in selected headers only when it has an **explicit purpose, schema, type, access control, and lifetime**.

### 17.3. Correlation does not replace event identity

~~~text
Checkout CHECKOUT-88
  -> Event EVT-901: OrderSubmitted
  -> Event EVT-902: PaymentAuthorized
  -> Event EVT-903: InventoryReserved
~~~

Three events can share one correlation ID while having three distinct logical identities. Using correlation as a global idempotency key would wrongly drop the second event. In the Translator, preserve each ID according to its layer's responsibility, and never mint a new ID when merely changing the schema representation of the **same event**.

### 17.4. `mappingVersion` differs from `schemaVersion`

~~~text
sourceSchemaVersion = partner.order.v2
mappingVersion      = partner-to-canonical.2026-11
targetSchemaVersion = normalized.order.v3
~~~

The source schema may stay unchanged while mapping rules evolve (e.g., an approved shipping default). Conversely, a new schema may reuse the same mapping semantics. Tracking these versions **separately** makes replays and investigations accurate.

### 17.5. Never reuse stale envelope security context for unauthorized replays

A quarantine record storing `tenant=TENANT-A` from an earlier receipt does not prove today's replay operator is authorized for that tenant. Replay must check the current principal/actor, revocation/retention state, and active permissions. Never accept a self-declared external `trustedTenant` header while bypassing authorization.

## 18. Message Translator coordinating with Enterprise Integration Patterns

### 18.1. Filter: compute outcome first, filter afterward

~~~text
PartnerOrderInput
   -> Translator computes MappingResult
   -> Filter:
        accepted -> normalized business flow
        rejected -> quarantine
~~~

This preserves the **reason codes** for unmapped fields. If a Filter returns only a boolean by invoking the mapper once in the predicate and then invoking the mapper again in a quarantine handler, policies or reference data might change between calls. **Compute the outcome once** and route that exact outcome.

### 18.2. Router: pick translator by authoritative schema

~~~mermaid
flowchart LR
    INPUT["Incoming envelope"] --> VERIFY["Authenticate + validate source/type/version"]
    VERIFY --> R{"Schema Router"}
    R -->|Partner A V1| TA["Translator A V1"]
    R -->|Partner A V2| TB["Translator A V2"]
    R -->|Partner B V1| TC["Translator B V1"]
    R -->|Unsupported| Q["Schema quarantine"]
    TA --> N["Canonical model"]
    TB --> N
    TC --> N
~~~

Never route solely on a self-declared `source=trusted-service` inside the payload. If the Router has no matching mapping version, **do not** default to an older translator and ignore new fields just "to keep things running".

### 18.3. Content Enricher: separate lookups from mapping

Suppose target `taxRegion` requires the customer's address from CRM:

~~~text
Partner source fields -> Pure Translator -> Partial validated model
   -> Content Enricher (trusted CRM lookup)
   -> Canonical model validation
   -> Business handler
~~~

A lookup can fail due to a network timeout, unlike an "unmapped source field". Define separate policies for stale lookups, consistency, deadlines, authorization, and retries. If enrichment runs before translation, track which defaults came from the source, which came from the lookup, and which version each value belonged to.

### 18.4. Splitter: a batch containing unmappable children

~~~text
Batch B-9
  -> Item 1: mapped OK
  -> Item 2: unsupported deliveryCode
  -> Item 3: mapped OK
~~~

If a Splitter produces three child messages and a Filter routes item 2 to quarantine, a downstream Aggregator may miss one part. Ensure:

- Stable `batchId + itemId` along with correlation/sequence.
- An explicit failure outcome for rejected children if the batch contract expects one result per child.
- Timeout/release strategies for partial failures.
- Deduplication of duplicate child replies so a repeated item never substitutes for a missing one.

**Never treat a translator-rejected child as a success** just to fill out the sequence.

### 18.5. Aggregator: never combine canonical data with ambiguous raw data

An Aggregator receives results from three partners, one of which failed to map `currency`. Never sum `amount` values with unknown units. Aggregate only **validated typed canonical values**, or emit `AggregationOutcome(PARTIAL_FAILURE)` with reasons—never silently drop a branch whose amount is unclear.

### 18.6. Scatter–Gather: branch replies with distinct schemas

A request fans out to Inventory, Pricing, and Fraud. Branches may return:

~~~text
InventoryReplyV2 -> InventoryTranslator -> InventoryOutcome
PricingReplyV1   -> PricingTranslator   -> PricingOutcome
FraudReplyV3     -> FraudTranslator     -> FraudOutcome
~~~

The Gatherer must distinguish **missing branch**, **invalid mapping**, **timeout**, and **success**. If the Fraud reply has an unmapped field governing risk decisions, never mark the order `APPROVED` just because the other two branches succeeded.

### 18.7. Resequencer: schema mapping must not corrupt order

`schemaVersion` is a representation version, not the `sequenceNumber` of business events. The Translator can convert V1/V2 to a canonical DTO while preserving **business sequence** and `correlationId` for the Resequencer.

If `seq=2` fails mapping and goes to quarantine, a Resequencer waiting for 1, 2, 3 can stall. Define a **failure placeholder/gap policy**, or quarantine the entire group per contract—never renumber `seq=3` to `2`.

### 18.8. Idempotent Receiver: fixed mappings must not cause duplicate effects

~~~text
Original event EVT-901 -> translator V1 rejects
Replay EVT-901 -> translator V2 accepts
~~~

On replay, downstream deduplicates by **stable business event/operation ID**, not by `mappingVersion` or a new Spring `MessageHeaders.ID`. If a side effect or receipt already exists from another path, return the previous outcome or signal a conflict rather than starting a new operation.

### 18.9. Claim Check: token survives while raw data expires

A quarantine case might store only a claim token pointing to the raw partner payload. If the Claim Check store's TTL is shorter than the review/replay horizon, **the original is gone when the mapper gets fixed**. Ensure appropriate protected replay storage/retention, or clearly record unrecoverability. Never fabricate missing fields from earlier warning messages.

### 18.10. Gateway: respond cleanly on rejected mappings

A synchronous `MessagingGateway` waiting for a reply may time out if a Filter discards the message to a one-way quarantine. If the API contract requires a response, return:

~~~json
{
  "status": "REJECTED_MAPPING",
  "eventId": "EVT-901",
  "mappingVersion": "partner-order-v1",
  "issueCodes": ["UNMAPPED_SOURCE_FIELD"],
  "quarantineRef": "Q-901"
}
~~~

Include only **error codes and fields safe to expose to the caller**, never raw sensitive data. Asynchronous flows may need only an ACK after durable quarantine; synchronous Gateways require a tested reply path.

### 18.11. Error channel: classify by failure point

~~~text
Decoder error -> raw/schema error handling
MappingResult(ERROR) -> quarantine/rejection routing
Translator implementation exception -> technical error handling
Quarantine write exception -> persistence retry/backpressure
Business handler exception -> downstream retry/reconciliation
~~~

Do not apply the exact same `RetryAdvice` everywhere without knowing **side-effect boundaries** and **exception scope**. Deterministic mapping errors are not fixed by retrying continuously; infrastructure errors warrant bounded retries.

## 19. Operations: metrics and audits to catch silently dropped fields

### 19.1. Meaningful milestones

~~~text
event=SOURCE_MESSAGE_RECEIVED
  partner=PARTNER-A
  sourceSchemaVersion=v2
  eventRef=EVT-901

event=MAPPING_STARTED
  mappingVersion=partner-order-v1
  sourceType=PartnerOrderInput

event=MAPPING_COMPLETED
  status=REJECTED
  issueCodes=[UNMAPPED_SOURCE_FIELD]
  issueFields=[newRiskIndicator]

event=QUARANTINE_PERSISTED
  caseRef=Q-901
  mappingVersion=partner-order-v1

event=REPLAY_AUTHORIZED
  caseRef=Q-901
  targetMappingVersion=partner-order-v2

event=RETRANSLATION_COMPLETED
  caseRef=Q-901
  status=ACCEPTED
~~~

This is an **application-proposed structured log schema**, not Spring Integration's default logging. If source or field names could carry sensitive data, sanitize, truncate, allowlist, and control access. Specifically, **never log raw `extraFields` values in standard logs**.

### 19.2. Suggested metrics

| Metric | What it measures |
|---|---|
| `translator_messages_received_total` | Deliveries entering the translator. |
| `translator_accepted_total{source,policy}` | Accepted outcomes. |
| `translator_rejected_total{reason}` | Rejected outcomes. |
| `translator_unmapped_fields_total{fieldClass}` | Unknown fields grouped into bounded classes. |
| `translator_ignored_fields_total{policy}` | Legitimately ignored fields. |
| `translator_default_applied_total{field}` | Contractual defaults applied. |
| `translator_invalid_format_total{field}` | Unparseable values. |
| `translator_unsupported_enum_total{field}` | New/unsupported enum values. |
| `translator_schema_mismatch_total{sourceType}` | Incompatible schemas. |
| `mapping_quarantine_persisted_total` | Durably saved mapping cases. |
| `mapping_quarantine_write_failed_total` | Quarantine persistence failures. |
| `mapping_replay_total{outcome}` | Replay/retranslation outcomes. |
| `translator_latency_seconds` | Mapping latency. |
| `mapping_policy_version_active` | Active policy version by bounded config. |

Metric names are illustrative. Never use `eventId`, `orderId`, `customerId`, `quarantineId`, or free-form unknown field values as labels, as they explode cardinality and leak data. Aggregate varied unknown field names into `known_ignored/critical_unknown/other_unknown`, and use access-controlled logs for specific investigations.

### 19.3. "Translated successfully" still does not mean a business result exists

| Milestone | What can be claimed | What cannot be claimed |
|---|---|---|
| Raw received | Adapter received bytes/record. | Typed decoding succeeded. |
| JSON decoded | Syntax/types parsed per decoder. | Mapping preserved business semantics. |
| Mapping accepted | Translator built canonical outcome per rules. | Business handler committed. |
| Warning ignored field | Field ignored under current policy. | Field will stay unimportant in future versions. |
| Filter discarded | Did not proceed down the Filter's accepted path. | Quarantine record was durably saved. |
| Quarantine persisted | Case recorded per store contract. | Replay completed the business operation. |
| Business receipt COMPLETED | Operation reached an authoritative outcome. | Remote side effects rolled back atomically across external systems. |
| Broker ACK | Transport recorded acknowledgment per its semantics. | No duplicate republish will happen later. |

### 19.4. Message History does not reveal which fields were dropped

Spring Integration Message History (when enabled) shows which Transformer/Filter a message passed through. It cannot reveal whether:

- `newRiskIndicator` was stripped by the parser before entering the flow.
- A mapping policy ignored a field under valid business approval.
- `totalVnd` suffered a silent unit conversion error without throwing.
- A required target field received a fabricated default outside the contract.
- A quarantine case was committed or replayed under which version.

Supplement it with **mapping diagnostics, contract tests, policy/version audits, and business idempotency receipts**.

### 19.5. Runbook when unmapped fields spike

1. Identify affected **source, tenant, and schema version**.
2. Inspect **sanitized field names**, severity levels, and active `mappingVersion`.
3. Check whether a producer recently deployed or toggled a schema/feature flag.
4. Evaluate **new field semantics** with business/domain owners, especially money, tax, permissions, or risk.
5. Check `STRICT_QUARANTINE` vs. `WARN_AND_IGNORE` mode and review messages accepted while the field was ignored.
6. If business data corruption is suspected, throttle ingestion/processing per risk policy rather than blindly expanding the ignore list.
7. Update/version the contract or translator mapping and add regression tests.
8. Verify **replay eligibility**, original references, tenant permissions, stable `eventId`, and operation receipts.
9. Revalidate/retranslate under the new policy with auditing and bounded attempts.
10. Reconcile accepted, rejected, quarantined, and persisted counts without conflating milestones.

## 20. Testing matrix for unmapped fields

| ID | Scenario | Expected outcome | Must never happen |
|---|---|---|---|
| MT-01 | All source fields known, valid data | Produces accurate `NormalizedOrder`. | Alters `orderId`/`amount`. |
| MT-02 | `partnerOrderRef` differs in name from `orderId` | Renamed per mapping. | Sets blank target `orderId`. |
| MT-03 | `totalVnd="850000"` | `BigDecimal("850000")`. | Uses `double` with precision loss. |
| MT-04 | `totalVnd="0"` | `AMOUNT_OUT_OF_RANGE`. | Executes zero-amount payment via bad default. |
| MT-05 | `totalVnd="-1"` | `INVALID_AMOUNT_FORMAT` per demo. | Sends negative amount to business. |
| MT-06 | `totalVnd="8,500"` | `INVALID_AMOUNT_FORMAT`. | Guesses locale/units. |
| MT-07 | `totalVnd="8500.50"` | `INVALID_AMOUNT_FORMAT` for integer contract. | Silent rounding. |
| MT-08 | `totalVnd=null` | `MISSING_AMOUNT`. | Defaults to 0. |
| MT-09 | `totalVnd=""` or blank | `MISSING_AMOUNT`. | Parses as 0. |
| MT-10 | Oversized numeric string | `INVALID_AMOUNT_FORMAT`, bounded resources. | Unbounded CPU/memory consumption. |
| MT-11 | Value exceeds demo max | `AMOUNT_OUT_OF_RANGE`. | Exceeds cap unreported. |
| MT-12 | `deliveryCode=STD` | `ShippingTier.STANDARD`. | Inverted mapping. |
| MT-13 | `deliveryCode=EXP` | `ShippingTier.EXPRESS`. | Inverted mapping. |
| MT-14 | `deliveryCode` absent | Defaults to STANDARD + warning per V1 contract. | Uses default without audit. |
| MT-15 | `deliveryCode=OVERNIGHT` | `UNSUPPORTED_DELIVERY_CODE`. | Auto-falls back to STANDARD. |
| MT-16 | `eventId` missing | `MISSING_EVENT_ID`, not accepted. | Generates UUID per consumer attempt. |
| MT-17 | `partnerOrderRef` missing | `MISSING_ORDER_ID`. | Creates blank order. |
| MT-18 | `legacyCampaignHint` in `extraFields` | Ignored + `IGNORED_LEGACY_FIELD` warning. | Adds raw value into canonical DTO. |
| MT-19 | `newRiskIndicator` in strict mode | `UNMAPPED_SOURCE_FIELD` ERROR. | Silently ignored. |
| MT-20 | `newRiskIndicator` in lenient mode | Warning, accepted per approved policy. | Zero telemetry. |
| MT-21 | Two unknown fields in one message | Records all field names/reasons (no raw secrets). | Reports false clean success. |
| MT-22 | Same field name, schema V2 changes semantics | Version-specific mapping/quarantine. | Applies V1 rule and corrupts money/tax. |
| MT-23 | JSON has new key, parser defaults to ignore unknown | Ingress test detects/reports it. | Translator thinks no unknown fields exist. |
| MT-24 | Malformed JSON before typed input | Adapter raw error route. | Claims Filter handles typed outcome. |
| MT-25 | JSON duplicate keys | Caught by parser/schema validation. | Picks an ambiguous value. |
| MT-26 | Conflicting `totalVnd` and alias `grandTotalVnd` | `CONFLICTING_FIELD_ALIASES` or schema reject. | Picks one randomly. |
| MT-27 | Approved ignored source-only field | Warning/audit per `mappingVersion`. | Pushed into all downstream headers. |
| MT-28 | Required target `riskApproval` has no source | Authoritative enrichment or reject. | Defaults to APPROVED. |
| MT-29 | Optional target missing, contractual default | Default + diagnostic/contract version. | Applies default to unknown values. |
| MT-30 | Source money uses different unit | Currency-aware mapping or reject. | Adds two incompatible currency units. |
| MT-31 | Source enum adds valid value in V2 | V2 translator mapping and tests. | V1 silently accepts without review. |
| MT-32 | Unknown field contains bearer token | Never log/forward raw; deny per policy. | Leaks token into quarantine logs/metrics. |
| MT-33 | Untrusted tenant in payload | Bound from authenticated tenant. | Switches to another tenant. |
| MT-34 | Same event, new Spring Message ID | Stable `sourceEventId`. | Repeated business effect due to runtime UUID. |
| MT-35 | Same source `eventId`, conflicting raw payload | Identity conflict/review. | Blind deduplication. |
| MT-36 | Accepted branch | Business probe receives one `NormalizedOrder`. | Incorrectly quarantined. |
| MT-37 | Strict rejected branch | Quarantine probe receives `MappingResult` with issues. | Business handler invoked. |
| MT-38 | Filter missing discard channel | Test catches unpersisted records. | Silent drop treated as success. |
| MT-39 | `throwExceptionOnRejection` enabled | Error semantics tested as configured. | Assumes discard still runs. |
| MT-40 | Quarantine store down | Bounded technical retry/backpressure. | ACKs and loses original. |
| MT-41 | Broker ACK lost after quarantine commit | Idempotent case deduplication. | Creates infinite duplicate cases. |
| MT-42 | Quarantine raw payload expires before replay | Reports unreplayable or uses other valid source. | Fabricates missing data. |
| MT-43 | Policy V1 rejected, policy V2 accepted | Versioned retranslation + audit. | Erases original/old reason. |
| MT-44 | Replay same event that already has business receipt | Idempotent previous outcome. | Triggers new payment/operation. |
| MT-45 | Splitter with one child mapping error | Failure outcome/correlation/gap policy. | Aggregator waits forever. |
| MT-46 | Aggregator receives amount with unknown currency | Reject/partial failure per contract. | Sums mismatched units. |
| MT-47 | Scatter–Gather Fraud reply has unmapped critical field | Does not APPROVED full request. | Ignores Fraud. |
| MT-48 | Resequencer has gap from rejected mapping | Gap/placeholder/timeout policy. | Reorders or fakes success. |
| MT-49 | Gateway mapping rejected | Returns rejected response/error contract. | Caller hangs indefinitely. |
| MT-50 | Producer adds many unknown fields in bulk | Alerts by source/policy; reviews schema drift. | Ignores indefinitely without monitoring. |
| MT-51 | MapStruct compiles cleanly yet new raw key arrives | Caught by runtime decoder/schema test. | Equates compiler checks with wire safety. |
| MT-52 | Oversized extension bag | Size/count/type bounds and backpressure. | OOM or log injection. |
| MT-53 | Unknown field name has control characters | Sanitize field path/log output. | Log forging/injection. |
| MT-54 | Retry after source is revoked | Reauthorize against current principal. | Uses stale metadata to bypass auth. |
| MT-55 | Success count differs from durable persisted count | Dashboard separates milestones. | Reports all rejects are durably quarantined. |

### 20.1. Testing pyramid to apply

| Layer | Verifies | Does not prove |
|---|---|---|
| **Unit translator** | Field mapping, null/enum/amount, severity/policy. | Spring flow routing or broker behavior. |
| **JSON/schema contract** | Raw unknown keys, duplicate keys, aliases, size/type/version. | Durable quarantine commit. |
| **Spring Integration flow** | Transformer → Filter → discard/business handlers. | Multi-node persistence if using fakes. |
| **Adapter test** | Deserialization, header mapping, error channel/DLQ, ACK. | External payment business idempotency. |
| **Database test** | Quarantine unique keys, transactions, concurrent writes, retention. | Broker ACK when no broker is used. |
| **System/recovery** | Crash windows, replay, source version migration, multi-node. | Real-world failures not yet simulated. |
| **Security test** | AuthN/AuthZ, tenant isolation, PII masking, protected replay. | Unreviewed trust boundaries. |

### 20.2. Golden mapping fixtures

To catch regressions after deployments, maintain at least versioned fixtures:

~~~text
Fixture A / partnerA-v1-accepted:
  eventId=EVT-A1, orderRef=ORD-A1
  totalVnd=850000, deliveryCode=EXP
  expected.amountVnd=850000, shippingTier=EXPRESS

Fixture B / partnerA-v1-ignored:
  legacyCampaignHint=retired
  expected.accepted=true
  expected.warning=IGNORED_LEGACY_FIELD

Fixture C / partnerA-v2-new-field:
  newRiskIndicator=high
  expected.strictV1.error=UNMAPPED_SOURCE_FIELD
  expected.v2.mapping=explicitly approved outcome

Fixture D / partnerA-v1-unknown-enum:
  deliveryCode=OVERNIGHT
  expected.error=UNSUPPORTED_DELIVERY_CODE
~~~

These fixtures should test **raw serialization → typed input → mapping result → flow routing**; constructing already-typed Java objects skips parser-dropped unknown JSON fields.

## 21. Anti-patterns to avoid

| Pitfall | Consequence | Solution |
|---|---|---|
| "Any unmapped field gets dropped by default." | Loss of meaningful data. | Strict policy or audited allowlist ignore. |
| "Every unknown field is a fatal error." | Even optional extensions halt ingestion. | Classify critical vs. approved ignored vs. extension. |
| "No MapStruct warnings means raw JSON has no unknown fields." | Runtime fields may be stripped earlier by decoder. | Schema-aware ingress diagnostics. |
| "Missing required target field? Just default it to satisfy the constructor." | Produces wrong, potentially dangerous business values. | Enrich, make optional, or reject per contract. |
| "Map any new enum to STANDARD." | Silently alters delivery terms. | Explicit enum mapping and unsupported error. |
| "If amount parses, the money is right." | Wrong currency, scale, or units. | Semantic conversion with versioning/validation. |
| "Ignore fields without emitting warnings." | Cannot detect schema drift. | Warning metrics and `mappingVersion`. |
| "Preserve raw fields by stuffing them into Spring headers." | Data leakage and route injection. | Metadata allowlist and protected extension bag. |
| "Treat missing and unknown with the same default." | Masks new values. | Missing-only defaults backed by contract. |
| "Any null means zero or false." | Conflates UNKNOWN with negation. | Presence-aware validation and optional semantics. |
| "A mapping retry creates a new `eventId`." | Breaks idempotency. | Stable event/operation identity. |
| "Appending quarantine items to a list is durable enough." | Crashes lose cases. | Durable DB/queue and proper ACK ordering. |
| "Throw exceptions for every mapping issue." | Hard to separate invalid business inputs from technical failures. | Typed `MappingResult` + dedicated error path. |
| "Filter `false` automatically saves the message." | Silent discard. | Discard channel / quarantine handler. |
| "Gateway replies automatically on duplicate/rejected items." | Caller timeouts. | Explicit reply/error contract. |
| "If target lacks a field, consider translation done anyway." | Partial object leaks into business logic. | Validate canonical invariants before handlers. |
| "Retranslating the same raw event yields the same business outcome regardless of policy." | New mapping can change semantics and side effects. | Versioned replay + reconciliation/receipt conflict handling. |
| "Upgrading to schema V2 means V1 can be deleted immediately." | Historical events/DLQ cannot be replayed. | Backward compatibility aligned with retention. |
| "Unit tests proving mapping works make production safe." | Headers, decoders, stores, or ACKs can still fail. | Contract, adapter, and system tests. |

## 22. Practice exercises

1. **Basic mapping:** use `PartnerOrderTranslator` to map `partnerOrderRef`, `totalVnd`, and `deliveryCode` into `NormalizedOrder` and assert each field.
2. **Source-only allowlist:** send `legacyCampaignHint`, keep mapping accepted while emitting a warning; verify the raw value does not enter `NormalizedOrder`.
3. **Strict unknown:** add `newRiskIndicator` to `extraFields`; assert `UNMAPPED_SOURCE_FIELD` and `normalized == null`.
4. **Lenient unknown:** enable `WARN_AND_IGNORE` in a unit test, compare accepted/status with strict mode, and explain the risks without approval.
5. **Multiple fields:** send two unknown fields; verify both reasons are recorded without logging raw values.
6. **Missing required:** omit `eventId`, `partnerOrderRef`, or `totalVnd`; verify each produces its own reason code.
7. **Missing vs. null:** use a raw JSON parser to distinguish absent keys from explicit nulls before DTO binding; verify the chosen policy.
8. **Contractual default:** omit `deliveryCode`, expect `STANDARD` + `SHIPPING_DEFAULT_APPLIED`.
9. **Unknown enum:** send `deliveryCode=OVERNIGHT`, assert error instead of fallback.
10. **Amount locale:** test `850000`, `850000.0`, `850,000`, `1E6`; verify only the contracted format passes.
11. **Input bounds:** supply an overly long `totalVnd`; assert controlled rejection without parsing a massive number.
12. **Target-only risk field:** add required `riskApproval` to the canonical model, design authoritative enrichment or rejection, never defaulting `APPROVED`.
13. **Extension bag:** define namespace, allowlist, type, and length for one partner metadata field; test shadowing against core fields.
14. **Jackson unknown properties:** introduce a new JSON key silently ignored by default; update ingress parsing to detect it before the translator runs.
15. **Duplicate JSON keys:** craft raw JSON with two `totalVnd` keys; configure parser/validation to flag the conflict.
16. **Field aliases:** allow V1 `totalVnd` and V2 `grandTotalVnd`; test when both appear with differing values.
17. **Schema V2:** promote `newRiskIndicator` to an official field after review, bump `mappingVersion`, and add golden fixtures.
18. **Partner scope:** same source key from Partner A and Partner B with independent policies; never apply A's allowlist to B.
19. **Tenant authorization:** craft input whose self-declared tenant differs from `authenticatedTenant`; verify it never maps to a higher-privilege tenant.
20. **Spring DSL accepted:** send a message to `partner.order.input`; assert the business probe holds one `NormalizedOrder` and quarantine is empty.
21. **Spring DSL rejected:** send an unknown field in strict mode; assert quarantine holds `MappingResult` and business probe is empty.
22. **Filter error semantics:** test removing `discardChannel` or enabling `throwExceptionOnRejection`; explain each outcome and how to prevent silent drops.
23. **Header preservation:** pass `businessEventId` and `correlationId` through Transformer/adapters; verify neither is lost or confused with `MessageHeaders.ID`.
24. **Broker redelivery:** send the same event in two Spring Messages with different runtime IDs; verify the downstream Idempotent Receiver applies only one business operation.
25. **Durable quarantine:** replace the probe with a JDBC repository enforcing unique `(tenant, partner, eventId, caseType)`; test two workers writing concurrently.
26. **Crash/ACK:** simulate committing quarantine while losing the broker ACK; redelivery creates one idempotent case, not two.
27. **Store failure:** make the quarantine DB unavailable; verify rejected messages never leak into business processing and bounded retry/backpressure runs.
28. **Authorized replay:** upgrade `mappingVersion` from V1 to V2, retranslate a quarantined event with authorization and audit; keep raw original intact.
29. **Replay conflict:** same `eventId` with a changed amount; check the completion ledger and refuse automatic re-charging.
30. **Splitter/Aggregator:** one child has an unknown enum; emit a failure outcome with correlation/sequence so the Aggregator never waits infinitely.
31. **Scatter–Gather:** Pricing and Inventory succeed while Fraud mapping fails; Gatherer must not return overall `APPROVED`.
32. **Resequencer:** message `seq=2` is quarantined; implement a gap policy or failure placeholder while keeping business sequence intact.
33. **Gateway response:** caller submits malformed/unsupported mapping and receives `REJECTED_MAPPING` with issue codes and a reference instead of timing out.
34. **Metrics:** build dashboards for accepted, rejected, quarantine persisted, and unknown warnings without using event IDs or raw unknown values as metric labels.
35. **Runbook:** write a checklist for investigating a spike in `UNMAPPED_SOURCE_FIELD` by source/schema, from producer deploy through mapping policy upgrade and controlled replay.

### 22.1. Completion criteria

An implementation is considered solid when:

- Every critical source field has an explicit **mapping rule or policy decision**.
- Source-only ignored fields have approval, warnings, and a policy version.
- Target-only required fields never receive fabricated defaults contradicting semantics.
- Missing, null, blank, unknown enum, and unknown field cases are classified separately.
- Monetary values and units convert strictly per contract without `double`.
- Translator returns structured reason codes and emits no canonical object while errors exist.
- Spring flows route accepted and rejected outcomes to the **right handlers** with zero silent drops.
- Pre-translator parse errors and post-translator store errors have dedicated error paths.
- Stable `eventId`, tenant/source trust boundaries, and replay permissions are enforced.
- Tests cover raw → typed → mapping → channel → business/quarantine, not just a single mapping method.

## 23. Self-check questions

**Question 1: When a Message Translator encounters a source field with no matching target, must it always delete it?**

No. You need a policy: reject/quarantine, ignore with approval, preserve in a bounded extension, or extend the canonical model. The choice depends on business semantics and the data contract.

**Question 2: How do source-only and target-only differ?**

Source-only is a field the source sends that the target does not require; target-only is a field the target requires that the source omits. A required target-only field may need enrichment or rejection—it cannot be solved merely by ignoring.

**Question 3: If `legacyCampaignHint` is approved to be ignored, is a warning still needed?**

Policy-driven diagnostics/telemetry are helpful to confirm intentional ignoring and detect drift, though logging raw values is unnecessary.

**Question 4: Should `deliveryCode=null` and `deliveryCode=OVERNIGHT` both map to `STANDARD`?**

No. In the demo, missing/null defaults to `STANDARD` **under the V1 contract**; `OVERNIGHT` is an unsupported new enum value and must raise an error.

**Question 5: Why is successfully parsing `totalVnd="850000"` insufficient to prove a mapping is correct?**

You must also know the unit, currency, scale, pre- vs. post-tax semantics, bounds, and business rules. A type-valid mapping can still be semantically wrong.

**Question 6: Why use `MappingResult` instead of returning `NormalizedOrder` directly?**

To retain issues, severities, `mappingVersion`, source context, and the accepted/rejected decision for controlled investigation and replay.

**Question 7: If Jackson dropped an unknown JSON field before creating the DTO, can the translator detect it again?**

Not from the stripped DTO. You need a schema-aware parser, tree model, strict failure mode, or extension collector at ingress.

**Question 8: If MapStruct reports zero unmapped targets at compile time, does that prove raw JSON contains no unknown fields?**

No. The compiler cannot see runtime keys dropped by the decoder or stored inside maps. Contract and runtime tests remain necessary.

**Question 9: Why not forward all unmapped fields in Spring headers?**

It leaks data, breaks domain/transport boundaries, bloats payloads, risks header injection, and exposes unauthorized fields to consumers.

**Question 10: Can a new `taxIncluded` field be ignored just because `totalVnd` is already mapped?**

Never assume so. `taxIncluded` can change the meaning of the total; review schema semantics and mapping rules.

**Question 11: Does Filter rejection mean the message is durably stored in quarantine?**

Not yet. `discardChannel` only defines the route; you still need a durable writer/ACK flow, persistence, and recovery tests.

**Question 12: Is setting `throwExceptionOnRejection(true)` the same as normal discard routing?**

No. It changes Filter rejection semantics to throwing exceptions; verify configuration and error routing under your execution model.

**Question 13: If a business handler times out after mapping was accepted, should it be tagged `UNMAPPED_SOURCE_FIELD`?**

No. That is a downstream/technical failure or uncertain outcome requiring retry/reconciliation per business operation.

**Question 14: Why track `mappingVersion` and `sourceSchemaVersion` separately?**

Because rules/defaults can change across deploys for the same schema, or a new schema can share the same mapping semantics. Separate versions enable accurate audits and replays.

**Question 15: Is replaying a previously rejected event with a V2 mapper a brand-new business event?**

Not by default. When retranslating the same logical event, keep `eventId`, check downstream idempotency, and attach replay attempt lineage.

**Question 16: How do you deduplicate a quarantined raw message that lacks an `eventId`?**

Use a trusted ingress envelope identity or semantically defined transport record identity—never mint a fresh UUID on every receipt and call it a stable key.

**Question 17: If a translator runs after a Splitter and one child fails mapping, what happens to the Aggregator?**

It can end up missing a child. Provide error outcomes/placeholders, correlation, timeouts, or partial-release policies per contract—never fake a failed child as `SUCCESS`.

**Question 18: Should a field holding security-sensitive info be written into `UNMAPPED_SOURCE_FIELD` logs?**

Never log raw values. Log only reason codes, sanitized/masked field names, and a protected payload reference if needed, under proper access and retention controls.

**Question 19: Why shouldn't `MessageHeaders.ID` be used as the deduplication identity during retranslation?**

Spring's runtime message can be recreated with a new ID; logical `eventId` / business `operationId` must stay stable across retries and replays.

**Question 20: If the caller is a synchronous Gateway and rejected mappings go to a one-way quarantine, what does the caller receive?**

Likely a timeout. Define an explicit response/error contract—such as `REJECTED_MAPPING` with issue codes and a quarantine reference—rather than assuming a discard channel sends a reply.

**Question 21: When is `WARN_AND_IGNORE` appropriate?**

When business/data owners approve it for a specific partner/schema/field scope, with safety bounds, warning metrics, and no impact on critical invariants.

**Question 22: Can you hardcode `riskApproval=true` to satisfy a required target field?**

No. That value must come from an authoritative source; if unavailable, run controlled enrichment/retries or reject.

**Question 23: Should deterministic mapping errors be retried automatically in a loop?**

No. Unchanged data and policy produce the exact same error; fix the input or upgrade the mapping. Only infrastructure failures warrant bounded retries.

**Question 24: Why aren't passing mapper unit tests sufficient for production readiness?**

Because parsers can drop unknown fields, header mappers can lose event IDs, quarantine stores/ACKs can fail, and broker redeliveries can duplicate side effects. You need contract, Spring Integration, adapter, persistence, and recovery tests.

## 24. Conclusion

**Handling unmapped fields** in a Message Translator is a **data contract and business safety decision**, not just a mapper configuration toggle. Source fields without targets, target fields missing sources, new enums, unparseable values, and missing/null fields are **not one single error category**. Each requires an explicit policy and reason code: **reject/quarantine, ignore with audit, approved defaults, authoritative enrichment, or bounded extension schemas**.

In Spring Integration, a cleanly testable design is **Translator returns `MappingResult` → Filter checks `accepted` → business flow or `discardChannel` to quarantine**. Preserve source event identity, correlation, trusted tenant context, and mapping versions; separate pre-translator parse errors from post-mapping downstream errors; and never ACK, deduplicate, or replay without understanding durable outcomes and business side effects.

Within `SPRING_INTEGRATION_PATTERN`, whenever combining Message Translator with Router, Filter, Transformer, Splitter, Aggregator, Scatter–Gather, Resequencer, Gateway, Claim Check, Idempotent Receiver, retries, and error channels, always be able to answer: **"Which fields translated with accurate meaning?", "Which fields were dropped or missing and under what policy?", "Where are rejected messages stored, and who is authorized to fix and replay them?", and "How do we guarantee retries never duplicate business impact?"** Those answers keep systems loosely coupled from producers, safe for schema evolution, observable, and recoverable from failures.
