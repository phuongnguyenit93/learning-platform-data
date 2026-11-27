# Avoiding Data Loss During Normalization

> **Chapter:** Normalizer  
> **Module:** `SPRING_INTEGRATION_PATTERN` — learning to implement Enterprise Integration Patterns with Spring Integration to build loosely coupled, extensible message flows; practicing Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation, while testing and monitoring processing branches. This lesson focuses on **preserving meaning, accuracy, and reconcilability when normalizing multiple formats into one common contract**.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Describe the EIP **Normalizer** as a coordination of **Message Router + Message Translator/Transformer** so multiple message types become one canonical representation.
2. Distinguish **format conversion** from **semantic change**, identifying where data can be silently lost without throwing an exception.
3. Build a **mapping contract** specifying required fields, unmappable fields, differences between `absent`/`null`/empty values, and extension fields.
4. Handle money, units, integers, timestamps, timezones, enums, and identifiers without arbitrary truncation, rounding, defaulting, or namespace changes.
5. Design a canonical DTO with **provenance**, versioning, and controlled raw references; understand the limits of retaining raw inputs.
6. Write a Java 17 normalizer with typed accepted/rejected/warning outcomes, then connect two sources via Spring Integration Java DSL.
7. Test golden mappings, invalid inputs, semantically equivalent data, partial/unknown fields, idempotency, and multi-branch errors.
8. Handle security, retries, DLQ replays, Splitter/Aggregator, and observability so bad data never reaches side-effecting handlers.

## 2. Scenario: Two Partners Describing the Same Order with Two Schemas

**Partner A** sends an order with string quantity, unit price in USD major units, and ISO-8601 timestamp:

~~~json
{
  "order_id": "PO-901",
  "qty": "003",
  "unit_price": "12.50",
  "currency": "usd",
  "created_at": "2026-11-21T08:00:00Z",
  "channel": "retail",
  "note": null
}
~~~

**Partner B** uses minor units (cents), epoch milliseconds, and a numeric channel code:

~~~json
{
  "orderNumber": "PO-901",
  "quantity": 3,
  "priceMinor": 1250,
  "currencyCode": "USD",
  "eventEpochMs": 1795248000000,
  "channelCode": 1,
  "legacyCampaignCode": "CAMPAIGN-7"
}
~~~

Both can produce equivalent canonical business fields:

~~~json
{
  "externalOrderId": "PO-901",
  "quantity": 3,
  "unitPriceMinor": 1250,
  "currency": "USD",
  "occurredAt": "2026-11-21T08:00:00Z",
  "channel": "RETAIL"
}
~~~

Yet if you **only** keep the final JSON, you miss critical differences:

- A sends `note: null`, whereas B **omits** the note field. Their meanings can differ in PATCH/merge flows.
- B sends `legacyCampaignCode`. If it controls discounts, ignoring it causes wrong pricing; if it only tracks attribution, a policy-approved warning may suffice.
- Both A and B might use `PO-901` yet represent **two distinct orders** under different partner namespaces.
- Major/minor units, timezones, and channel mappings require a versioned contract; never “guess” from data types.

**Goal definition:** a Normalizer must **preserve essential business information**, be transparent about unrepresentable data, and never emit bad commands merely because a Mapper returned successfully.

~~~mermaid
flowchart LR
    A["Partner A"] --> R["Trusted source routing"]
    B["Partner B"] --> R
    R --> TA["Translator A"]
    R --> TB["Translator B"]
    TA --> V{"Mapping + validation"}
    TB --> V
    V -->|"Valid"| C["CanonicalOrder + provenance"]
    V -->|"Invalid"| E["Rejection / quarantine"]
    A -.-> RAW[("Protected raw store")]
    B -.-> RAW
    C --> D["Router / Gateway / Business handler"]
~~~

## 3. Normalizer in Enterprise Integration Patterns

Normalizer solves the problem of **accepting multiple message types and presenting one common format** downstream. Logically it comprises:

1. **Router:** identifies message type/source schema using trusted metadata.
2. **Matching Translator/Transformer:** converts the source schema into the canonical model.
3. **Unified output contract:** consumers downstream of the Normalizer need not understand schemas A/B/C.
4. **Unmappable path:** reject, quarantine, or warn when policy allows.

~~~text
ExternalOrderA --\
ExternalOrderB ----> select translator ---> CanonicalOrder ---> downstream
LegacyOrderC   --/       |                 ^
                          +-- unsupported ---+--> rejection flow
~~~

In Spring Integration, this pattern can be built with `.route(...)` branching by type/schema or separate per-partner input channels `.transform(...)`-ing onto a shared channel. There is **no requirement** for a single Java endpoint named `Normalizer`; the pattern is the combined behavior of Router and Transformer.

| Pattern | Responsibility | Do Not Confuse With |
| --- | --- | --- |
| **Normalizer** | Multiple input schemas → one canonical schema | Assuming renaming fields alone is safe |
| **Transformer** | Converts one representation into another | Checking all permissions or DB state itself |
| **Router** | Chooses a branch by source/type/content | Verifying schema validity itself |
| **Filter** | Blocks messages failing a condition | Returning full rejection reasons itself |
| **Content Enricher** | Adds data from another source | Recovering intentionally discarded raw fields |
| **Claim Check** | Stores large/raw payload in a store, passes a reference | Guaranteeing access permissions or retention itself |
| **Aggregator** | Combines child replies sharing correlation | Treating a duplicate as a new child |

## 4. Subtle Ways Data Is Silently Lost

Data loss can happen **even when deserialization, transformation, and sending all report success**.

| Kind of Data Loss | Scenario | Consequence |
| --- | --- | --- |
| Dropped field | `campaignCode` missing from output DTO | Lost attribution or discount rules |
| Wrong default | Missing `qty` → defaulted to `1` | Unconfirmed quantity invented |
| Absent/null collapsed | Missing field and explicit null both become Java `null` | Accidental deletion or skipped deletion |
| Numeric truncation | `12.345` USD → `1234` cents | Monetary error |
| Double precision | Parsing money via `double` | Floating-point/rounding errors |
| Overflow | Price × quantity overflows `long` | Negative or wrong total |
| Wrong unit | `1250` minor units read as `1250 USD` | Price off by 100x |
| Wrong epoch unit | Epoch seconds read as milliseconds | Timestamp off by decades |
| Host default timezone | Offset-less local time forced to UTC | Wrong deadline handling |
| Unknown enum fallback | `channelCode=3` → RETAIL | Routed to wrong workflow |
| Lossy text normalization | Uppercasing case-sensitive IDs | Distinct IDs collide into one |
| Lost ordering | `List` → `Set` | Business sequence lost |
| Lost namespace | Keeping only `orderId`, dropping tenant/partner | Wrong deduplication/authorization |
| Stripped metadata | Dropping execution/correlation/operation ID | Misgrouped replies or duplicate side effects |
| Schema drift | Using v1 parser on v2 message | Fields misread |
| Catching all errors into default DTO | DB/network/bugs turned into “invalid input” | Fails to retry or reconcile |

### 4.1. Intentional vs. Accidental Lossiness

Not every partner field may be kept or forwarded. Sensitive fields, redundant data, or secrets **must sometimes be dropped** for data minimization. Every drop decision requires:

- A mapping contract specifying which fields are dropped, why, and who approved it.
- Impact classification: **required**, optional, untrusted, sensitive, or extension.
- Policy: **ERROR**, **WARNING**, redaction, extension, or raw retention.
- Enough evidence for auditing without logging PII or tokens indefinitely.
- Retention/deletion windows aligned with compliance and replay windows.

**Avoiding data loss does not mean storing every piece of data forever.** Security, privacy, and retention are part of correctness.

## 5. Write the Mapping Contract Before Coding

Example mapping matrix for the two partners:

| Source Field | Canonical Field | Mapping | When Unparseable/Unknown |
| --- | --- | --- | --- |
| A `order_id` | `externalOrderId` | Keep ID intact with namespace | Reject |
| A `qty` | `quantity` | Exact integer parse, range 1..500 | Reject |
| A `unit_price` | `unitPriceMinor` | `BigDecimal` major→minor per currency | Reject if unexpected rounding needed |
| A `created_at` | `occurredAt` | ISO instant with offset | Reject if zone missing |
| A `channel` | `channel` | retail/wholesale → enum | Reject unknown |
| A `note` | `note` | Preserve absent/null/value | Reject if parser lost presence |
| B `priceMinor` | `unitPriceMinor` | Range check, **never multiply by 100** | Reject |
| B `eventEpochMs` | `occurredAt` | `Instant.ofEpochMilli` | Reject out of window |
| B `channelCode` | `channel` | 1=RETAIL, 2=WHOLESALE | Reject unknown |
| B `legacyCampaignCode` | Not in canonical v1 | Warning + raw ref if non-functional | Reject if field controls discounts |
| Trusted `tenantId` | `source.tenantId` | From authenticated adapter | Security reject |
| Schema version | `source.sourceSchemaVersion` | Select verified decoder/policy | Reject unsupported |

**Three rules never to break:**

1. Required fields **must never** receive fabricated valid defaults just to pass a Filter.
2. Unknown enums or units **must never** map to a “closest” business value.
3. Unmapped fields require an **explicit decision**, never silent disappearance.

### 5.1. Every Field Needs a Source of Truth

Do not trust `tenantId` or `partnerId` from a JSON body as authorization. The HTTP/broker boundary must authenticate the principal/source, verify tenant and schema version, and supply a **trusted context** to the Normalizer.

If a client sets header `partnerId=A` to hit Translator A, a router relying solely on that header risks type confusion and cross-tenant data leaks.

## 6. Canonical Format and Provenance

A good canonical DTO need not be a “superset of every field from every partner”. The goal is retaining **truly needed shared concepts**.

~~~text
CanonicalOrder
  source:
    tenantId
    partnerId
    sourceSchemaVersion
    rawReference (internal-only)
  externalOrderId
  quantity
  unitPriceMinor
  currency
  occurredAt
  channel
  note: ABSENT | EXPLICIT_NULL | VALUE
  canonicalSchemaVersion
~~~

- **Core fields**: meaningful and broadly shared, governed by contract/version.
- **SourceContext/provenance**: traces partner, schema, and authorized raw copy.
- **Controlled extension**: consider for single-source fields; bound size, types, and access.
- **Raw reference**: points to securely stored raw payload for audit/reprocessing when needed.
- **MappingIssue**: warning/error codes when output cannot preserve full input meaning.

A `rawReference` is **internal-only** data, not a public URL or bearer token to broadcast to all consumers. If raw data contains PII, enforce encryption, IAM, auditing, and retention.

### 6.1. Business Identity Namespace

Two partners can both have `orderId=PO-901`. Identity keys should consider:

~~~text
(tenantId, partnerId, externalOrderId)
~~~

If one order receives multiple commands (`CREATE`/`CANCEL`/`AMEND`), idempotency also needs a stable `commandId` or `operationType`. **Execution correlation groups** and **business side-effect idempotency keys** serve two different purposes.

### 6.2. Absent, Explicit Null, Empty String

| Source Data | Meaning When Updating a Field | What to Do |
| --- | --- | --- |
| Key omitted | No change requested | Preserve `ABSENT` |
| Key has `null` | May request clearing the value | Preserve `EXPLICIT_NULL` |
| Key has `""` | Empty string sent | Preserve `VALUE("")` or reject per policy |
| Key has string | Set concrete value | `VALUE(text)` after validation |

Java `Optional<String>` usually cannot represent **the difference between missing and explicit null**; for PATCH/merge, use an explicit state type.

~~~java
enum FieldState {
    ABSENT,
    EXPLICIT_NULL,
    VALUE
}

record FieldText(FieldState state, String value) {
    FieldText {
        if (state == null) {
            throw new IllegalArgumentException("FIELD_STATE_MISSING");
        }
        if ((state == FieldState.VALUE) != (value != null)) {
            throw new IllegalArgumentException("INVALID_FIELD_STATE");
        }
    }

    static FieldText absent() {
        return new FieldText(FieldState.ABSENT, null);
    }

    static FieldText explicitNull() {
        return new FieldText(FieldState.EXPLICIT_NULL, null);
    }

    static FieldText of(String text) {
        return new FieldText(
            FieldState.VALUE,
            java.util.Objects.requireNonNull(text));
    }
}
~~~

**Note at the parser boundary:** deserializers binding both missing JSON properties and explicit JSON `null` to Java `null` erase presence *before the Transformer runs*. When the contract distinguishes them, capture field presence right during JSON parsing (or use a presence-aware structure) to build `FieldText`.

## 7. Preserving Money and Numeric Precision

Two sources can be equivalent:

~~~text
Partner A: "12.50" USD (major units)
Partner B: 1250 USD minor units
Canonical: unitPriceMinor=1250, currency=USD
~~~

Yet not every decimal string converts to minor units **without rounding**. `12.345 USD` has fractional cents; without a rounding policy, reject rather than truncating.

### 7.1. Java `BigDecimal` and `longValueExact`

~~~java
import java.math.BigDecimal;
import java.util.Locale;

final class MoneyNormalization {
    private MoneyNormalization() {}

    static String currency(String raw) {
        if (raw == null) {
            throw new MappingFailure(
                "currency", "CURRENCY_REQUIRED");
        }
        String normalized = raw.strip().toUpperCase(Locale.ROOT);
        if (!normalized.equals("USD")
                && !normalized.equals("VND")) {
            throw new MappingFailure(
                "currency", "UNSUPPORTED_CURRENCY");
        }
        return normalized;
    }

    static int scale(String currency) {
        return switch (currency) {
            case "USD" -> 2;
            case "VND" -> 0;
            default -> throw new MappingFailure(
                "currency", "UNSUPPORTED_CURRENCY");
        };
    }

    static long fromMajor(String raw, String currency) {
        if (raw == null || raw.isBlank()) {
            throw new MappingFailure(
                "unitPrice", "PRICE_REQUIRED");
        }
        try {
            BigDecimal major = new BigDecimal(raw.strip());
            long minor = major.movePointRight(
                scale(currency)).longValueExact();
            return fromMinor(minor);
        } catch (NumberFormatException | ArithmeticException ex) {
            throw new MappingFailure(
                "unitPrice", "PRICE_NOT_EXACT_MINOR_UNITS", ex);
        }
    }

    static long fromMinor(long minor) {
        if (minor < 0 || minor > 1_000_000_000L) {
            throw new MappingFailure(
                "unitPrice", "PRICE_OUT_OF_RANGE");
        }
        return minor;
    }
}
~~~

The 1-billion minor-unit cap, `USD/VND` set, and scales here are **illustrative policies only**. Production must verify decimal digits per currency/source contract, versioned, including currencies with special conventions.

### 7.2. Never Convert Exchange Rates Automatically

`12.50 USD` and `12500 VND` are **not** automatically equal values. The Normalizer should unify **representation**, not apply today's exchange rate to rewrite historical meaning. When FX conversion is needed, record rate source, timestamp, rounding policy, and original amounts for audit.

### 7.3. Checking Total Price Overflow

~~~java
long totalMinor;
try {
    totalMinor = Math.multiplyExact(
        (long) quantity, unitPriceMinor);
} catch (ArithmeticException ex) {
    throw new MappingFailure(
        "totalPriceMinor", "TOTAL_OVERFLOW", ex);
}
~~~

If the domain needs numbers larger than `long`, use `BigInteger`/`BigDecimal` with explicit schema and serialization rules. Never cast through `double`.

## 8. Time, Timezones, and Resolution

| Source | Can Determine Exact Instant? | Handling |
| --- | --- | --- |
| `2026-11-21T08:00:00Z` | Yes | Parse to `Instant` |
| `2026-11-21T15:00:00+07:00` | Yes | Same instant in UTC |
| `2026-11-21 15:00` without offset | Not reliably | Reject or apply contracted zone |
| Epoch milliseconds | Yes once unit is known | `Instant.ofEpochMilli` |
| Epoch seconds | Yes once unit is known | `Instant.ofEpochSecond` |
| Date-only `LocalDate` | Not an instant | Keep date-only; do not guess UTC midnight |

**Never use `ZoneId.systemDefault()`** for partner data that requires explicit timezone semantics. Different host timezones produce different outputs, shifting deadlines.

If a source provides nanosecond precision while canonical/brokers retain milliseconds, that is an **intentional precision loss** that should be documented. When contracts require signatures over raw bytes, reserialized canonical output cannot replace the original bytes.

## 9. Unknown Enums, String Normalization, and Schema Drift

Suppose Partner B adds channel code `3=MARKETPLACE` in a new schema release. If the v2 mapper defaults unknown codes to `RETAIL`, every marketplace order will **take the wrong downstream Router branch**.

~~~java
enum OrderChannel {
    RETAIL,
    WHOLESALE
}

static OrderChannel channelByCode(int value) {
    return switch (value) {
        case 1 -> OrderChannel.RETAIL;
        case 2 -> OrderChannel.WHOLESALE;
        default -> throw new MappingFailure(
            "channelCode", "UNKNOWN_CHANNEL_CODE");
    };
}
~~~

An `UNKNOWN` enum value is acceptable **only when** downstream understands it and refrains from side effects for unclear channels. Unknown is never “close enough to retail”.

### 9.1. Do Not Uppercase Every Business ID

`orderId="Ab-12"` and `orderId="AB-12"` can be two distinct IDs if a partner is case-sensitive. A Transformer calling `toUpperCase` on every string causes **collisions** and false deduplication. Normalize based on **each field's contract**, not formatting habits.

### 9.2. Independent Versions

~~~text
source schema A       a-order-v1
source schema B       b-order-v2
canonical schema      canonical-order-v1
normalizer policy     normalizer-policy-v6
~~~

Source version does not equal canonical model version. When policy changes, DLQ replays can produce different results; pin versions, migrate, or explicitly re-normalize under governance.

## 10. Raw Reference, Provenance, and Deciding Whether to Keep Source Fields

A canonical DTO **need not** be a lossless replica of every source schema. For instance, B's `legacyCampaignCode` has no shared canonical field. There are four deliberate choices:

| Policy | Action | When Appropriate |
| --- | --- | --- |
| **Reject** | Do not emit canonical success | Field affects pricing, permissions, compliance, or routing |
| **Warn + raw reference** | Accepted with coded warning | Field does not affect current processing; source remains reconcilable |
| **Controlled extension** | Store in schema-bound allowlisted extension | Specific consumers are authorized to read source-specific fields |
| **Evolve canonical** | Add new version/field and migrate | Field has become a necessary shared concept |

A canonical payload can carry provenance:

~~~text
SourceContext
  tenantId              = shop-a
  partnerId             = partner-b
  sourceSchemaVersion   = b-order-v2
  rawReference          = raw/b-901 (internal-only)

CanonicalOrder
  externalOrderId       = PO-901
  quantity              = 3
  unitPriceMinor        = 1250
  currency              = USD
  occurredAt            = 2026-11-21T08:00:00Z
  channel               = RETAIL
  note                  = ABSENT
  canonicalSchemaVersion= canonical-order-v1

MappingWarning
  LEGACY_CAMPAIGN_NOT_MAPPED
~~~

**Never claim** the canonical DTO alone is completely lossless when `legacyCampaignCode` was dropped. The warning proves the mapping policy acknowledged the loss; the raw reference helps only while the object exists, matches the tenant, stays within retention, and consumers hold read permissions.

Raw storage needs checksums, IAM, encryption, access auditing, and cleanup. Never copy a raw reference into a public pre-signed URL. Do not retain raw PII forever for debugging convenience; data minimization and erasure rights still apply.

## 11. Java 17: Source Models, Canonical Model, and Typed Mapping Results

The lesson uses `record` for immutable data. `SourceContext` is metadata provided by the **authenticated adapter**, never copied from a client-supplied header.

~~~java
import java.time.Instant;
import java.util.List;
import java.util.Objects;

record SourceContext(
    String tenantId,
    String partnerId,
    String sourceSchemaVersion,
    String rawReference
) {
    SourceContext {
        if (tenantId == null || tenantId.isBlank()
            || partnerId == null || partnerId.isBlank()
            || sourceSchemaVersion == null
            || sourceSchemaVersion.isBlank()
            || rawReference == null || rawReference.isBlank()) {
            throw new IllegalArgumentException(
                "INVALID_SOURCE_CONTEXT");
        }
    }
}

record PartnerAOrder(
    String orderId,
    String quantityText,
    String unitPriceDecimal,
    String currency,
    String occurredAtIso,
    String channel,
    FieldText note
) {}

record PartnerBOrder(
    String orderNumber,
    long quantity,
    long priceMinor,
    String currencyCode,
    long eventEpochMs,
    int channelCode,
    FieldText note,
    String legacyCampaignCode
) {}

record AEnvelope(SourceContext source, PartnerAOrder body) {}
record BEnvelope(SourceContext source, PartnerBOrder body) {}

record CanonicalOrder(
    SourceContext source,
    String externalOrderId,
    int quantity,
    long unitPriceMinor,
    String currency,
    Instant occurredAt,
    OrderChannel channel,
    FieldText note,
    String canonicalSchemaVersion
) {
    CanonicalOrder {
        Objects.requireNonNull(source);
        Objects.requireNonNull(occurredAt);
        Objects.requireNonNull(channel);
        Objects.requireNonNull(note);
    }
}

enum IssueSeverity { WARNING, ERROR }

record MappingIssue(
    String field,
    String code,
    IssueSeverity severity
) {}

record NormalizationResult(
    SourceContext source,
    CanonicalOrder value,
    List<MappingIssue> issues
) {
    NormalizationResult {
        Objects.requireNonNull(source);
        issues = List.copyOf(issues);
    }

    boolean accepted() {
        return value != null && issues.stream().noneMatch(
            i -> i.severity() == IssueSeverity.ERROR);
    }
}

record NormalizationRejection(
    String partnerId,
    String rawReference,
    List<MappingIssue> issues
) {
    NormalizationRejection {
        issues = List.copyOf(issues);
    }
}
~~~

`NormalizationResult` can be accepted **with warnings**. On mandatory errors, `value=null` and the result is rejected; never fabricate a meaningless default DTO just to avoid null. `NormalizationRejection` is for **internal quarantine**; public APIs need a projection stripping raw keys and sensitive metadata.

### 11.1. Mapping Errors and Technical Failures Are Two Different Classes

~~~java
final class MappingFailure extends RuntimeException {
    private final String field;
    private final String code;

    MappingFailure(String field, String code) {
        super(code);
        this.field = field;
        this.code = code;
    }

    MappingFailure(String field, String code, Throwable cause) {
        super(code, cause);
        this.field = field;
        this.code = code;
    }

    String field() { return field; }
    String code() { return code; }
}
~~~

This represents **source data unmappable under the contract**, such as unsupported enums, invalid quantities, or unpermitted rounding. Never catch arbitrary `Exception`s and turn DB/object-store outages, code bugs, or unavailable services into data rejections; those require dedicated error channels, retry/backoff, or alarms.

## 12. NormalizerService: Controlled Mapping of Partners A and B

The code below uses `FieldText`, `MoneyNormalization`, `MappingFailure`, `OrderChannel`, and the records defined above. `NormalizerService` performs pure computation without side effects.

~~~java
import java.time.DateTimeException;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Objects;

final class NormalizerService {

    public NormalizationResult fromA(AEnvelope env) {
        Objects.requireNonNull(env);
        SourceContext source = Objects.requireNonNull(env.source());
        PartnerAOrder raw = Objects.requireNonNull(env.body());

        try {
            requireSource(source, "partner-a", "a-order-v1");
            String currency = MoneyNormalization.currency(raw.currency());

            CanonicalOrder output = new CanonicalOrder(
                source,
                requiredOrderId(raw.orderId()),
                parseQuantity(raw.quantityText()),
                MoneyNormalization.fromMajor(
                    raw.unitPriceDecimal(), currency),
                currency,
                parseIsoTime(raw.occurredAtIso()),
                fromChannelName(raw.channel()),
                requirePresence(raw.note()),
                "canonical-order-v1");

            validateTotal(output);
            return new NormalizationResult(
                source, output, List.of());
        } catch (MappingFailure failure) {
            return rejection(source, failure);
        }
    }

    public NormalizationResult fromB(BEnvelope env) {
        Objects.requireNonNull(env);
        SourceContext source = Objects.requireNonNull(env.source());
        PartnerBOrder raw = Objects.requireNonNull(env.body());

        try {
            requireSource(source, "partner-b", "b-order-v2");
            String currency = MoneyNormalization.currency(raw.currencyCode());

            CanonicalOrder output = new CanonicalOrder(
                source,
                requiredOrderId(raw.orderNumber()),
                positiveQuantity(raw.quantity()),
                MoneyNormalization.fromMinor(raw.priceMinor()),
                currency,
                parseEpochMillis(raw.eventEpochMs()),
                fromChannelCode(raw.channelCode()),
                requirePresence(raw.note()),
                "canonical-order-v1");

            validateTotal(output);
            List<MappingIssue> issues = new ArrayList<>();

            if (raw.legacyCampaignCode() != null
                && !raw.legacyCampaignCode().isBlank()) {
                // Example policy: this field is for attribution only.
                issues.add(new MappingIssue(
                    "legacyCampaignCode",
                    "LEGACY_CAMPAIGN_NOT_MAPPED",
                    IssueSeverity.WARNING));
            }
            return new NormalizationResult(
                source, output, issues);
        } catch (MappingFailure failure) {
            return rejection(source, failure);
        }
    }

    private static void requireSource(
            SourceContext source, String partner, String version) {
        if (!partner.equals(source.partnerId())
            || !version.equals(source.sourceSchemaVersion())) {
            throw new MappingFailure(
                "source", "SOURCE_SCHEMA_MISMATCH");
        }
    }

    private static NormalizationResult rejection(
            SourceContext source, MappingFailure failure) {
        return new NormalizationResult(
            source, null,
            List.of(new MappingIssue(
                failure.field(), failure.code(), IssueSeverity.ERROR)));
    }

    private static String requiredOrderId(String id) {
        if (id == null || id.isBlank()) {
            throw new MappingFailure(
                "orderId", "ORDER_ID_REQUIRED");
        }
        // Do not uppercase IDs if the partner is case-sensitive.
        return id;
    }

    private static int parseQuantity(String text) {
        if (text == null || text.isBlank()) {
            throw new MappingFailure(
                "quantity", "QUANTITY_REQUIRED");
        }
        try {
            return positiveQuantity(Long.parseLong(text.strip()));
        } catch (NumberFormatException failure) {
            throw new MappingFailure(
                "quantity", "QUANTITY_NOT_INTEGER", failure);
        }
    }

    private static int positiveQuantity(long value) {
        if (value < 1 || value > 500) {
            throw new MappingFailure(
                "quantity", "QUANTITY_OUT_OF_RANGE");
        }
        return (int) value;
    }

    private static Instant parseIsoTime(String value) {
        if (value == null || value.isBlank()) {
            throw new MappingFailure(
                "occurredAt", "TIME_REQUIRED");
        }
        try {
            return validateTime(Instant.parse(value.strip()));
        } catch (DateTimeException failure) {
            throw new MappingFailure(
                "occurredAt", "INVALID_ISO_TIME", failure);
        }
    }

    private static Instant parseEpochMillis(long value) {
        try {
            return validateTime(Instant.ofEpochMilli(value));
        } catch (DateTimeException failure) {
            throw new MappingFailure(
                "eventEpochMs", "INVALID_EPOCH_MILLIS", failure);
        }
    }

    private static Instant validateTime(Instant time) {
        Instant from = Instant.parse("2000-01-01T00:00:00Z");
        Instant until = Instant.parse("2100-01-01T00:00:00Z");
        if (time.isBefore(from) || !time.isBefore(until)) {
            throw new MappingFailure(
                "occurredAt", "TIME_OUT_OF_RANGE");
        }
        return time;
    }

    private static OrderChannel fromChannelName(String value) {
        if (value == null) {
            throw new MappingFailure(
                "channel", "CHANNEL_REQUIRED");
        }
        return switch (value.strip().toUpperCase(Locale.ROOT)) {
            case "RETAIL" -> OrderChannel.RETAIL;
            case "WHOLESALE" -> OrderChannel.WHOLESALE;
            default -> throw new MappingFailure(
                "channel", "UNKNOWN_CHANNEL");
        };
    }

    private static OrderChannel fromChannelCode(int code) {
        return switch (code) {
            case 1 -> OrderChannel.RETAIL;
            case 2 -> OrderChannel.WHOLESALE;
            default -> throw new MappingFailure(
                "channelCode", "UNKNOWN_CHANNEL_CODE");
        };
    }

    private static FieldText requirePresence(FieldText note) {
        if (note == null) {
            throw new MappingFailure(
                "note", "NOTE_PRESENCE_NOT_CAPTURED");
        }
        return note;
    }

    private static void validateTotal(CanonicalOrder order) {
        try {
            Math.multiplyExact(
                (long) order.quantity(), order.unitPriceMinor());
        } catch (ArithmeticException failure) {
            throw new MappingFailure(
                "totalPriceMinor", "TOTAL_OVERFLOW", failure);
        }
    }
}
~~~

**What is protected:**

- A and B must match verified **source + schema version**.
- A's price converts units accurately and rejects when exact precision cannot be preserved; B is never multiplied by 100.
- Unknown channels never default to `RETAIL`.
- `ABSENT` and `EXPLICIT_NULL` remain distinct via `FieldText`.
- No random operation ID is generated across retries.
- Campaign fields are dropped only under an approved warning policy.

The code focuses on mapping. Quantity limits 1..500, price cap of 1 billion minor units, and timestamps 2000–2100 are **illustrative**, not universal policies for all applications.

## 13. Java DSL: Converging Two Schemas onto One Canonical Channel

The two input channels belong to separately authenticated adapters. Each branch runs a schema-specific Transformer, sends `NormalizationResult` into a shared Router, and splits accepted vs. quarantine.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
class LossAwareNormalizerConfiguration {

    @Bean("normalizer.a.in")
    DirectChannel inputA() { return new DirectChannel(); }

    @Bean("normalizer.b.in")
    DirectChannel inputB() { return new DirectChannel(); }

    @Bean("normalizer.results")
    DirectChannel results() { return new DirectChannel(); }

    @Bean("normalizer.accepted")
    DirectChannel accepted() { return new DirectChannel(); }

    @Bean("normalizer.rejected")
    DirectChannel rejected() { return new DirectChannel(); }

    @Bean("orders.canonical.out")
    QueueChannel canonicalOutput() { return new QueueChannel(); }

    @Bean("orders.quarantine.out")
    QueueChannel quarantineOutput() { return new QueueChannel(); }

    @Bean
    NormalizerService normalizer() { return new NormalizerService(); }

    @Bean
    IntegrationFlow partnerA(NormalizerService normalizer) {
        return IntegrationFlow.from("normalizer.a.in")
            .transform(AEnvelope.class, normalizer::fromA)
            .channel("normalizer.results")
            .get();
    }

    @Bean
    IntegrationFlow partnerB(NormalizerService normalizer) {
        return IntegrationFlow.from("normalizer.b.in")
            .transform(BEnvelope.class, normalizer::fromB)
            .channel("normalizer.results")
            .get();
    }

    @Bean
    IntegrationFlow decision() {
        return IntegrationFlow.from("normalizer.results")
            .route(
                NormalizationResult.class,
                result -> result.accepted() ? "OK" : "REJECT",
                r -> r.channelMapping("OK", "normalizer.accepted")
                      .channelMapping("REJECT", "normalizer.rejected"))
            .get();
    }

    @Bean
    IntegrationFlow deliver() {
        return IntegrationFlow.from("normalizer.accepted")
            .transform(
                NormalizationResult.class,
                NormalizationResult::value)
            .channel("orders.canonical.out")
            .get();
    }

    @Bean
    IntegrationFlow quarantine() {
        return IntegrationFlow.from("normalizer.rejected")
            .transform(
                NormalizationResult.class,
                result -> new NormalizationRejection(
                    result.source().partnerId(),
                    result.source().rawReference(),
                    result.issues()))
            .channel("orders.quarantine.out")
            .get();
    }
}
~~~

### 13.1. Must a Router Always Sit Ahead of Transformers?

No. In the example, **sources are already verified at input adapters** and two dedicated channels select the right translator. When one channel receives multiple schemas, a Router can inspect **trusted source/schema/type** to select the Translator; unknown types/versions must route to rejection rather than falling back to an arbitrary default Mapper.

This Java DSL targets modern Spring Integration releases. Verify overload signatures and endpoint configs against actual project dependencies during Content QA; **STEP 4 NEW did not run a build**.

### 13.2. Never Route Mapping Errors to Business Handlers

The `normalizer.accepted` branch unwraps `CanonicalOrder`; the `normalizer.rejected` branch emits `NormalizationRejection` carrying error codes. A rejected message must never reach Inventory/Payment Gateways simply because a Transformer returned a non-null result object.

The demo's `QueueChannel` merely provides a test receiver; it does not prove downstream commit or act as a durable broker.

## 14. Post-Transformer Validation and Error Handling

After normalization, canonical domain validation and business-state validation at commit time are still needed.

~~~text
Adapter: authentication + schema + size
    |
    v
Normalizer: source-specific mapping
    |
    +--> ERROR mapping -> reject/quarantine
    |
    v
Canonical business validation
    |
    +--> domain invalid -> typed rejection
    |
    v
Authorization / idempotent receiver
    |
    v
Business transaction (inventory/payment/DB)
    |
    v
Outbox / reply / audit
~~~

| Error | Belongs To | Should Retry? |
| --- | --- | --- |
| `qty="three"` | Parse/mapping | No, not with identical bytes |
| `channelCode=99` | Unsupported mapping | No, until policy updates |
| `unit_price="12.345"` USD | Precision mismatch | Needs data/rule fix |
| Unauthorized source tenant | AuthN/AuthZ | Never bypass permissions |
| DB/network timeout | Technical | Bounded retry/backoff |
| Out of stock at commit | Business-state outcome | Per business contract |

**Never catch every exception into a `MappingIssue(ERROR)`.** Infrastructure errors belong on an error channel or exception path; terminal data errors must not be retried forever by a broker.

### 14.1. Header Propagation

Transformers, MessageChannels, and adapters can rebuild messages and headers. Verify preservation of `businessCorrelationId`, `executionId`, `commandId`, and mapping policy/schema versions across HTTP, JMS, AMQP, or Kafka.

- `MessageHeaders.ID` can change; never use it as a business idempotency key.
- Raw JSON `contentType` does not necessarily fit a newly created canonical Java payload.
- `replyChannel` is an in-JVM object, not serializable over brokers by default.
- Never copy JWTs, secrets, or large raw payloads into uncontrolled headers or logs.

### 14.2. Normalization Does Not Replace Authorization

A syntactically valid `tenantId` inside a canonical record does not prove the principal is authorized. Avoid trusting namespaces from external payloads; validate source and tenant at ingress and again at business handlers when needed.

## 15. Unit Tests: Semantically Equivalent Sources Retain Distinct Provenance

Use JUnit 5 to test `NormalizerService` and value types. Two orders with the same quantity, price, and instant produce equivalent business fields, **while** source context and note presence remain distinct.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.time.Instant;
import org.junit.jupiter.api.Test;

class NormalizerServiceTest {
    private final NormalizerService service = new NormalizerService();

    private static SourceContext aSource() {
        return new SourceContext(
            "shop-a", "partner-a", "a-order-v1", "raw/a-901");
    }

    private static SourceContext bSource() {
        return new SourceContext(
            "shop-a", "partner-b", "b-order-v2", "raw/b-901");
    }

    private static PartnerAOrder aOrder() {
        return new PartnerAOrder(
            "PO-901", "003", "12.50", "usd",
            "2026-11-21T08:00:00Z",
            "retail", FieldText.explicitNull());
    }

    private static PartnerBOrder bOrder() {
        return new PartnerBOrder(
            "PO-901", 3, 1250, "USD",
            Instant.parse("2026-11-21T08:00:00Z")
                .toEpochMilli(),
            1, FieldText.absent(), "CAMPAIGN-7");
    }

    @Test
    void sameBusinessMeaningPreservesDifferentSourceMetadata() {
        NormalizationResult a = service.fromA(
            new AEnvelope(aSource(), aOrder()));
        NormalizationResult b = service.fromB(
            new BEnvelope(bSource(), bOrder()));

        assertTrue(a.accepted());
        assertTrue(b.accepted());

        CanonicalOrder first = a.value();
        CanonicalOrder second = b.value();

        assertEquals(first.externalOrderId(),
                     second.externalOrderId());
        assertEquals(first.quantity(), second.quantity());
        assertEquals(first.unitPriceMinor(),
                     second.unitPriceMinor());
        assertEquals(first.currency(), second.currency());
        assertEquals(first.occurredAt(), second.occurredAt());
        assertEquals(first.channel(), second.channel());

        // Do not strip provenance just to make the full DTOs equal.
        assertNotEquals(first.source(), second.source());
        assertEquals(FieldState.EXPLICIT_NULL,
            first.note().state());
        assertEquals(FieldState.ABSENT,
            second.note().state());
    }

    @Test
    void unknownLegacyFieldProducesExplicitWarning() {
        NormalizationResult result = service.fromB(
            new BEnvelope(bSource(), bOrder()));

        assertTrue(result.accepted());
        assertTrue(result.issues().stream()
            .anyMatch(i ->
                i.code().equals("LEGACY_CAMPAIGN_NOT_MAPPED")
                && i.severity() == IssueSeverity.WARNING));
        assertEquals("raw/b-901", result.source().rawReference());
    }

    @Test
    void doesNotSilentlyRoundFractionalCents() {
        PartnerAOrder bad = new PartnerAOrder(
            "PO-902", "1", "12.345", "USD",
            "2026-11-21T08:00:00Z", "retail",
            FieldText.absent());

        NormalizationResult result = service.fromA(
            new AEnvelope(aSource(), bad));

        assertFalse(result.accepted());
        assertNull(result.value());
        assertEquals("PRICE_NOT_EXACT_MINOR_UNITS",
            result.issues().get(0).code());
    }

    @Test
    void rejectsUnknownChannelInsteadOfDefaulting() {
        PartnerBOrder bad = new PartnerBOrder(
            "PO-903", 3, 1250, "USD",
            Instant.parse("2026-11-21T08:00:00Z")
                .toEpochMilli(),
            99, FieldText.absent(), null);

        NormalizationResult result = service.fromB(
            new BEnvelope(bSource(), bad));

        assertFalse(result.accepted());
        assertEquals("UNKNOWN_CHANNEL_CODE",
            result.issues().get(0).code());
    }

    @Test
    void refusesLostNotePresenceInformation() {
        PartnerAOrder bad = new PartnerAOrder(
            "PO-904", "2", "5.00", "USD",
            "2026-11-21T08:00:00Z", "retail", null);

        NormalizationResult result = service.fromA(
            new AEnvelope(aSource(), bad));

        assertFalse(result.accepted());
        assertEquals("NOTE_PRESENCE_NOT_CAPTURED",
            result.issues().get(0).code());
    }

    @Test
    void rejectsMismatchedSourceSchema() {
        SourceContext wrong = new SourceContext(
            "shop-a", "partner-b", "a-order-v1", "raw/wrong");

        NormalizationResult result = service.fromB(
            new BEnvelope(wrong, bOrder()));

        assertFalse(result.accepted());
        assertEquals("SOURCE_SCHEMA_MISMATCH",
            result.issues().get(0).code());
    }
}
~~~

### 15.1. What Matters in the First Test

If you wrote `assertEquals(first, second)` and altered the code to drop `source` and `note` just to pass, the test itself would **encourage data loss**. The right question is:

> Which business fields must match, and which provenance/optional-value differences **must be preserved**?

In reality, a Partner A order and a Partner B order with similar-looking IDs are not necessarily **the same order**; compare only within contracted business fields.

### 15.2. Essential Additional Tests

- `2026-11-21T15:00:00+07:00` and `2026-11-21T08:00:00Z` yield the same instant.
- Timestamps missing timezone/offset reject under the sample policy.
- Epoch seconds mistaken for milliseconds are not silently accepted as valid dates.
- `qty="0"`, `qty="-1"`, `qty="999999999999999999999"` never produce a valid quantity.
- Negative, out-of-range, or non-exact decimal prices reject.
- Wrong source schema version, unknown currency, and unknown enum produce error codes.
- `"note":null` differs from omitted note; parsers may need a JSON tree to preserve it.
- Two tenants using the same order ID never collide in deduplication.
- Raw copies preserve checksums and can only be read by authorized principals.

## 16. Spring Integration Test: Accepted and Rejected Take Separate Paths

With `LossAwareNormalizerConfiguration`, verify canonical DTO vs. coded rejection outputs; specifically assert that **rejected messages never reach the business branch**.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(LossAwareNormalizerConfiguration.class)
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class LossAwareNormalizerFlowTest {

    @Autowired @Qualifier("normalizer.a.in")
    MessageChannel inA;

    @Autowired @Qualifier("normalizer.b.in")
    MessageChannel inB;

    @Autowired @Qualifier("orders.canonical.out")
    PollableChannel accepted;

    @Autowired @Qualifier("orders.quarantine.out")
    PollableChannel rejected;

    @Test
    void validPartnerAEntersCanonicalOutput() {
        SourceContext source = new SourceContext(
            "shop-a", "partner-a", "a-order-v1", "raw/a-901");

        PartnerAOrder order = new PartnerAOrder(
            "PO-901", "003", "12.50", "USD",
            "2026-11-21T08:00:00Z", "retail",
            FieldText.explicitNull());

        assertTrue(inA.send(MessageBuilder.withPayload(
            new AEnvelope(source, order)).build()));

        Message<?> out = accepted.receive(1000);
        assertNotNull(out);
        assertInstanceOf(CanonicalOrder.class, out.getPayload());

        CanonicalOrder canonical = (CanonicalOrder) out.getPayload();
        assertEquals(1250L, canonical.unitPriceMinor());
        assertEquals("partner-a", canonical.source().partnerId());
        assertEquals(FieldState.EXPLICIT_NULL,
            canonical.note().state());

        assertNull(rejected.receive(0));
    }

    @Test
    void badChannelIsRejectedWithNoCanonicalMessage() {
        SourceContext source = new SourceContext(
            "shop-a", "partner-b", "b-order-v2", "raw/b-bad");

        PartnerBOrder bad = new PartnerBOrder(
            "PO-902", 3, 1250, "USD",
            Instant.parse("2026-11-21T08:00:00Z")
                .toEpochMilli(),
            99, FieldText.absent(), null);

        assertTrue(inB.send(MessageBuilder.withPayload(
            new BEnvelope(source, bad)).build()));

        Message<?> denied = rejected.receive(1000);
        assertNotNull(denied);
        assertInstanceOf(
            NormalizationRejection.class,
            denied.getPayload());

        NormalizationRejection notice =
            (NormalizationRejection) denied.getPayload();

        assertEquals("raw/b-bad", notice.rawReference());
        assertTrue(notice.issues().stream()
            .anyMatch(issue ->
                "UNKNOWN_CHANNEL_CODE".equals(issue.code())));

        assertNull(accepted.receive(0),
            "Unmappable source must not reach business output");
    }
}
~~~

**Integration test scope:** this tests inside a single Spring context, without real brokers (Kafka/JMS), raw object stores, real authentication, or business transactions. Synchronous `QueueChannel` and `DirectChannel` let tests assert emptiness on the unselected branch. With async `ExecutorChannel`/brokers, use bounded awaits and synchronization to prove **no side effects**, not just `receive(0)`.

### 16.1. Do Not Assert Only That a Rejection Was Emitted

A buggy flow could emit a rejection *and* still forward a bad canonical message to the handler. Tests must verify **negative paths**, ideally using a mock business handler or DB check proving **zero mutations** when normalization fails.

## 17. Golden Mapping Vectors and Property-Based Tests

A few passing fixtures are not enough to catch schema drift. Maintain **golden vectors** per source/schema/mapping policy:

~~~text
A v1:
  qty="003", price="12.50", USD
  -> quantity=3, minor=1250, USD, ACCEPTED

A v1:
  qty="2", price="12.345", USD
  -> REJECT PRICE_NOT_EXACT_MINOR_UNITS

B v2:
  channelCode=99
  -> REJECT UNKNOWN_CHANNEL_CODE

B v2:
  legacyCampaignCode="CAMPAIGN-7"
  -> ACCEPTED + WARNING LEGACY_CAMPAIGN_NOT_MAPPED

A v1:
  note present=null
  -> note EXPLICIT_NULL

B v2:
  note missing
  -> note ABSENT
~~~

Use property-based testing (e.g., a JUnit-compatible generator) to check invariants:

- Every quantity 1..500 in source A parses to the exact `int`.
- Major-unit prices within allowed scale convert to minor units without losing precision.
- Prices with fractional minor units never round silently.
- ISO timestamps with different offsets for the same instant yield equal outputs.
- Source IDs never change case when the contract forbids it.
- Unknown enums and schema versions are never accepted.
- Normalization never mints a new `commandId`/`operationId` on retries.
- Raw source hashes/round-trips are checked within defined scope.

### 17.1. Round-Trip Holds Only Under Defined Semantics

For example:

~~~text
A source price "012.500" USD
   -> canonical unitPriceMinor=1250
   -> serialized source price "12.50"
~~~

This preserves **business value**, not the **original byte sequence**. When signatures, legal compliance, forensics, or replays require exact raw bytes, store raw copies under access control and retention. Never treat reserialized canonical JSON as proof of the original raw JSON.

## 18. DLQ Replay, Mapping Policy Versions, and Idempotency

A message may be replayed days later when code or policies have changed:

~~~text
Initial run:
  source schema = a-order-v1
  normalizer-policy-v1
  canonical-order-v1

DLQ replay:
  source schema = a-order-v1
  code currently deployed = normalizer-policy-v3
  canonical-order-v2
~~~

The same raw payload can yield different values if v3 altered rounding, enum mapping, timezone, or defaults. Choose one clear strategy:

1. **Pin policy version** per execution when reproducing historical decisions.
2. **Re-normalize with new rules** when business approves fixing a mapping bug, with auditing/migration.
3. **Migrate canonical v1 → v2** explicitly rather than mixing silently.
4. **Reconcile / manual review** if downstream already committed side effects under old results.

### 18.1. Preserve Business Operation Identity

A retry/redelivery of the same command must never mint a fresh `commandId` inside the normalizer. Otherwise, the downstream Idempotent Receiver sees a new operation and deducts stock or charges twice.

- **Business operation key**: prevents duplicate side effects.
- **Execution ID/correlation**: groups one workflow run accurately.
- **Message ID/attempt**: transport/diagnostic metadata; may change.
- **Raw reference**: reconciles with source; not an idempotency key itself.

### 18.2. Retention Must Match Replay Windows

If the broker/DLQ allows replays after 15 days while the raw store retains only 2 days, never promise full re-normalization after 15 days. Likewise, purging the idempotency ledger before DLQ replays can cause duplicate business processing. Align retention across **raw data, metadata, idempotency state, and brokers**.

## 19. Normalizer Inside a Splitter–Aggregator Flow

A batch containing multiple orders/lines may traverse:

~~~mermaid
flowchart TD
    B["Batch from mixed sources"] --> S["Splitter"]
    S --> N["Normalizer A/B"]
    N --> D{"Mapping acceptable?"}
    D -->|"Yes"| A["ItemOutcome NORMALIZED"]
    D -->|"No"| R["ItemOutcome REJECTED + issue codes"]
    A --> G["Aggregator by executionId"]
    R --> G
    G --> O["BatchOutcome: accepted/rejected counts"]
~~~

**Never silently Filter-drop an unnormalizable child** if the Aggregator expects a full `sequenceSize` or child ID set. If LINE-2 vanishes, the Aggregator can hold the group forever or fail with an unexplained timeout.

### 19.1. Distinguish “All Replies Received” from “All Items Accepted”

~~~text
Expected children: [LINE-1, LINE-2, LINE-3]
LINE-1 -> NORMALIZED
LINE-2 -> REJECTED (UNKNOWN_CHANNEL_CODE)
LINE-3 -> NORMALIZED

Aggregator received 3/3 child outcomes
Business result: 2 accepted, 1 rejected
~~~

Receiving three out of three outcomes **does not** mean all three are business-valid. If the contract is all-or-nothing, the batch must report `FAILED` even though all replies arrived.

### 19.2. Duplicates and Correlation

A child may be redelivered twice by a broker. Never treat two deliveries of `LINE-1` as two distinct children. Deduplicate by `(executionId, childId)` or an appropriate business key. Idempotency for downstream side effects remains a separate layer from group correlation.

## 20. Observability: Detecting Dropped or Altered Information

A log entry `normalized=true` cannot explain lost data.

| Metric/Signal | Question Answered |
| --- | --- |
| Inbound count by partner/version | Who is sending which schemas? |
| Unknown source/schema count | Did a partner change formats unannounced? |
| Mapping accepted/rejected rate | What is the acceptance rate? |
| Issue codes (warnings/errors) | Which fields are being dropped or losing meaning? |
| Precision-loss rejected count | Are inputs requiring disallowed rounding? |
| Unknown enum/currency count | Is schema drift occurring? |
| Raw-store available/missing | Can we still reconcile and reprocess? |
| Quarantine oldest age/backlog | Are failures forgotten and piling up? |
| DLQ re-normalization version changes | Could replays change outputs? |
| Business commit vs. normalized count | Did accepted mappings actually succeed downstream? |

**Metric labels** should use bounded-cardinality fields like `partnerType`, `sourceSchemaVersion`, `issueCode`, and endpoint. Never use `orderId`, `rawReference`, `tenantId`, or `executionId` as high-cardinality time-series tags; keep debugging details in access-controlled logs/traces.

### 20.1. Controlled Logging

~~~json
{
  "event": "normalization_rejected",
  "partner": "partner-b",
  "sourceSchemaVersion": "b-order-v2",
  "canonicalSchemaVersion": "canonical-order-v1",
  "issueCodes": ["UNKNOWN_CHANNEL_CODE"],
  "decision": "QUARANTINE"
}
~~~

This is an illustrative log schema, **not** built-in Spring Integration logging. Never log raw JSON, secrets, pre-signed URLs, or personal data just to inspect bad input.

## 21. Anti-Patterns and How to Avoid Them

| Anti-Pattern | Consequence | Fix |
| --- | --- | --- |
| Mapping known fields and silently dropping unknown ones | New schemas lose data | Mapping contract + warning/error |
| Turning `qty="abc"` into 0 | Hides source errors | Reject with typed error code |
| Parsing money with `double` | Precision loss | `BigDecimal` + exact minor units |
| Mixing major/minor units | Prices off by 100x | Explicit unit contract per source |
| Forcing offset-less timestamps to UTC | Wrong deadlines/times | Reject or versioned zone policy |
| Reading epoch seconds as milliseconds | Wrong years | Validate units and ranges |
| Collapsing missing and null to Java `null` | Loses PATCH semantics | Capture presence before mapper |
| Unknown enum → `RETAIL` | Wrong routing | Reject or controlled `UNKNOWN` |
| Uppercasing all order IDs | Collisions | Normalize only per field contract |
| Exposing raw references publicly | Data leaks | Authorization/projections |
| Storing raw payloads in message headers | Bloated messages and leak risk | Claim Check / protected store |
| Retaining raw payloads forever | Violates retention policies | Data minimization and expiry |
| Self-reported source/tenant headers | Source spoofing | Trusted adapter context |
| Turning every exception into mapping error | Technical failures never retry | Dedicated error channel |
| Minting new operation UUID per attempt | Duplicate side effects on redelivery | Stable business key |
| Filter dropping invalid children | Aggregator waits for missing parts | Typed child rejection outcomes |
| Testing only happy paths | Misses loss/overflow/schema drift | Golden/property-based/negative tests |
| Treating canonical JSON as original raw | Invalid byte/signature proof | Store original bytes when required |

## 22. Production Readiness Checklist for Normalizer

- [ ] Mapping matrix exists per source schema version, including unknown fields.
- [ ] Fields classified as required, optional, restricted, extension, or reject-on-unknown.
- [ ] Numeric/monetary normalization defines units, precision, rounding, and overflow policies.
- [ ] Timestamps specify timezone, epoch unit, and precision per contract.
- [ ] Missing, explicit null, and empty string are never collapsed unintentionally.
- [ ] Unknown enums are never mapped to fake business values.
- [ ] Business IDs never alter case or namespaces arbitrarily.
- [ ] Trusted source context comes from auth/adapters, never client bodies.
- [ ] `canonicalSchemaVersion`, `sourceSchemaVersion`, and normalizer policy version recorded.
- [ ] Raw/provenance storage enforces retention and access controls when replay is needed.
- [ ] Unmappable critical fields always trigger rejection.
- [ ] Warnings never trick downstream into treating lossy output as lossless.
- [ ] Mapping errors stay separate from technical and domain/business-state errors.
- [ ] Rejected messages never reach side-effecting handlers.
- [ ] Correlation and idempotency keys survive Transformers and transport mappers.
- [ ] Splitter/Aggregator handle typed child rejection outcomes.
- [ ] Unit, integration, schema-contract, and negative tests exist.
- [ ] Unknown fields, price precision errors, and schema drift are monitored.
- [ ] Raw PII/tokens are kept out of logs and high-cardinality IDs out of metric tags.
- [ ] Runbooks cover quarantine handling, mapping migrations, and DLQ replays.

## 23. Applied Exercise

A logistics system receives parcel details from three carriers.

**Carrier A:** weight in decimal kilograms; dimensions in centimeters; ISO time with offset; `fragile:null`:

~~~json
{
  "shipment_id": "SHP-18",
  "weight_kg": "1.250",
  "length_cm": "30.0",
  "width_cm": "20.0",
  "height_cm": "10.0",
  "event_at": "2026-11-21T15:00:00+07:00",
  "fragile": null
}
~~~

**Carrier B:** weight in grams, dimensions in millimeters, epoch milliseconds; omits `fragile`:

~~~json
{
  "shipmentId": "SHP-18",
  "weightGrams": 1250,
  "lengthMm": 300,
  "widthMm": 200,
  "heightMm": 100,
  "eventEpochMs": 1795248000000
}
~~~

**Carrier C:** adds `temperatureControlClass`, which the current canonical schema does not yet represent. Certain products require this classification to select cold storage.

**Requirements:**

1. Create a mapping matrix for A/B/C specifying retained and unmappable fields.
2. Design canonical `Shipment` with standardized weight, length, and time units.
3. Convert `kg → grams` and `cm → millimeters` using `BigDecimal`/exact conversion; when must you reject rather than round?
4. Distinguish A's explicit null from B's absence for `fragile`.
5. Choose a policy for `temperatureControlClass`: warning, reject, extension, or schema upgrade? Why must it reject before routing if it governs cold-chain storage?
6. Separate `tenantId`, `carrierId`, `sourceSchemaVersion`, and raw reference into a trusted context.
7. Write `NormalizerService` and `NormalizationResult` with error/warning codes.
8. Build a Java DSL flow with Router, Transformers for A/B/C, and typed accepted/rejected channels.
9. Write golden tests proving two carriers yield matching mass/dimensions/instant with distinct provenance.
10. Test overflow, epoch-unit mistakes, unknown enums, and null/absent handling.
11. If one child fails normalization in a 100-parcel batch, emit `ShipmentRejected` so the Aggregator does not hang.
12. Design retention, ACLs, and checksums for the raw store if replay is required.
13. Explain why you must not mint a new `commandId` each time a DLQ message is re-normalized.
14. Propose metrics/alerts for schema drift, precision loss, quarantine backlog, and raw-reference failures.

**Hint:** the goal is not merely making JSON look alike, but preserving **the same meaning**; anything unrepresentable requires an explicit business decision, evidence, and handling path.

## 24. Summary

**Avoiding data loss during normalization** is a core duty when building a multi-source Normalizer. A Router selects a Translator by trusted source/schema while Transformers convert representations into a canonical model. Yet code running without exceptions **does not prove meaning was preserved**: missing vs. null, monetary rounding, timezones, enums, ID namespaces, raw fields, and metadata can all vanish or distort silently.

A resilient design requires **a mapping contract, schema/policy versioning, typed warnings/errors, exact numeric/time conversions, trusted source contexts, and explicit accepted/rejected routes**. When auditing or replay is required, raw references or Claim Check support reconciliation within valid access and retention bounds; they never replace authorization or security controls. Combine Spring Integration Java DSL, Router, Transformer, Filter, Gateway, Splitter/Aggregator, retry/error channels, correlation, and idempotency with unit, integration, and contract tests so messages normalize **accurately, explainably, and without erroneous side effects**.

**References:** Gregor Hohpe & Bobby Woolf, *Enterprise Integration Patterns* (Normalizer, Message Translator, Content-Based Router, Claim Check, Correlation Identifier); Spring Integration Reference on Transformers, Routers, Java DSL, Message Channels, Claim Check, Error Handling, and Testing; Java SE documentation on `BigDecimal`, `Instant`, `Locale.ROOT`, `Math.multiplyExact`, and records; data contracts and schema evolution literature.
