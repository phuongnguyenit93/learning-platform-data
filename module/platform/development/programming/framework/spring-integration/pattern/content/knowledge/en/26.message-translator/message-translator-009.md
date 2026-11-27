# Bidirectional Translators and Risk of Data Loss

**Message Translator** is an Enterprise Integration Pattern (EIP) that converts a message from a **representation understood by one system** into a **representation understood by another system**, without forcing both sides to couple directly to each other's data types, serialization formats, or conventions. With Spring Integration, a Translator is typically implemented using a **Transformer**, a chain of Transformers, or an adapter/codec at the integration boundary.

In practice, many teams need **bidirectional** translation: a partner sends `LegacyOrderV1` into an internal system, and the internal system must return orders or emit messages back in the legacy format. Two functions `A → B` and `B → A` may both run cleanly yet **fail to guarantee that the reverse translation recovers all input data**. A field present in A but absent in B will be lost; rounded decimals, stripped timezones, merged enums, or normalized strings can also alter business meaning.

The lesson **Bidirectional Translators and Risk of Data Loss** belongs to the **Message translator** chapter in module **SPRING_INTEGRATION_PATTERN**. The module focuses on implementing Enterprise Integration Patterns with Spring Integration to build loosely coupled, extensible message flows; practicing Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation, accompanied by testing and monitoring processing branches.

**Core message:** *Having two Translators does not mean having an inverse pair of functions*. Define the required level of preservation—**byte equivalence**, **structural equivalence**, **business semantic equivalence**, or merely **task-sufficient information**. When the preservation contract cannot be met, **report data loss, reject, or use an approved extension/provenance mechanism**, instead of silently returning an object that only looks valid.

## 1. Learning objectives

After this lesson, you will be able to:

1. Explain Message Translator and distinguish it from Normalizer, Header Enricher, Router, and serializers.
2. Distinguish forward mapping, reverse mapping, round-trip, and semantic equality.
3. Identify translations that are **lossless**, **lossy**, **unrepresentable**, or **lack a well-defined reverse mapping**.
4. Pinpoint causes of data loss: missing fields, type conversions, precision, enums, timezones, null/absent, and normalization.
5. Design v1/v2 DTOs representing the same order in different representations.
6. Specify major units ↔ minor units conversions using `BigDecimal`, validating scale and overflow.
7. Prevent new enums/statuses from being coerced into similar-looking legacy statuses with different semantics.
8. Write a bidirectional Java Translator returning `TranslationOutcome` along with a loss report.
9. Distinguish a **loss report** from a **validation error**: dropping data differs from being unable to map safely.
10. Build Spring Integration Java DSL flows for both directions, checking lossy outputs before business handlers.
11. Write JUnit 5 unit tests, round-trip/semantic equivalence tests, and channel integration tests.
12. Keep event identity, tenant/correlation, and headers stable across integration boundaries.
13. Design strict/quarantine policies, retries, error channels, DLQs, and Gateway responses per error category.
14. Specify schema/version compatibility, provenance, and strategies to recover lost data.
15. Monitor data loss rates, mapping errors, post-deployment drift, and latency.

## 2. Scenario: one order, two systems

A long-standing partner sends a message:

~~~json
{
  "eventId": "evt-order-1001",
  "tenantId": "tenant-a",
  "orderNo": "ORDER-101",
  "amountMajorText": "25.00",
  "currency": "USD",
  "statusCode": "P",
  "legacyPromotionCode": "SPRING-2026"
}
~~~

The internal system uses the contract:

~~~json
{
  "eventId": "evt-order-1001",
  "tenantId": "tenant-a",
  "orderId": "ORDER-101",
  "totalMinorUnits": 2500,
  "currency": "USD",
  "state": "PAID"
}
~~~

Easy-to-map fields:

- `orderNo` → `orderId`, since both represent the business order identity.
- `"25.00" USD` → `2500` minor units, once unit and precision are confirmed.
- `"P"` → `PAID`, since the partner defines `P` as paid.

However, the internal model **has nowhere to store** `legacyPromotionCode="SPRING-2026"`. When translating back:

~~~json
{
  "eventId": "evt-order-1001",
  "tenantId": "tenant-a",
  "orderNo": "ORDER-101",
  "amountMajorText": "25.00",
  "currency": "USD",
  "statusCode": "P",
  "legacyPromotionCode": null
}
~~~

the reverse translation **does not match the input**. The historical promotion code is gone. If another system needs that code for audits, promotions, or invoice adjustments, silently dropping it causes business errors even though compilation and deserialization both succeeded.

~~~mermaid
flowchart LR
    A["LegacyOrderV1
    has promotionCode"] -->|"Translate A→B"| B["CanonicalOrderV2
    no promotionCode"]
    B -->|"Translate B→A"| A2["LegacyOrderV1'
    promotionCode=null"]
    A2 -->|"Compare"| LOSS["Differs from A: field lost"]
~~~

Another case occurs when B gains a **new status `REFUNDED`** while A only supports `N` (new), `P` (paid), and `C` (cancelled). Never map `REFUNDED → C`: cancelling before payment and refunding after payment have different business semantics.

## 3. What is a Bidirectional Translator?

Notation:

- \(T_{AB}: A \rightarrow B\): translates representation A to B.
- \(T_{BA}: B \rightarrow A\): translates representation B to A.
- \(a \in A\), \(b \in B\): messages belonging to the two contracts.

**Ideal structural round-trip:**

\[
T_{BA}(T_{AB}(a)) = a
\]

and:

\[
T_{AB}(T_{BA}(b)) = b
\]

In real integrations, however, many translations only guarantee:

\[
T_{BA}(T_{AB}(a)) \approx_{\text{business}} a
\]

where \(\approx_{\text{business}}\) denotes **equivalence across published business fields and rules**, not byte-for-byte identity.

### 3.1. Four levels of preservation

| Level | Requirement | Example |
|---|---|---|
| **Byte-for-byte** | Serialized bytes after round-trip are identical | JSON retains whitespace, field order, lexical numbers |
| **Structural** | Identical structural fields/types/values | Jackson DTO deep equality; JSON field order may differ |
| **Semantic** | Equivalent business outcome | `"025.000" USD` and `"25.00" USD` equal the same monetary value |
| **Task-sufficient** | Enough data for a specific task without promising source recovery | Creating a shipment needs `orderId`/address, not legacy promo |

Never use the word **lossless** without specifying **which level** is meant.

### 3.2. An inverse function may not exist

If A has 7 fields while B has only 6 and the seventh is not stored elsewhere, multiple A values collapse into the same B:

~~~text
A1: promotionCode=SPRING-2026
A2: promotionCode=VIP-2026

T_AB(A1) = B
T_AB(A2) = B
~~~

Given only B, it is impossible to tell whether it came from A1 or A2. This is **loss of input distinguishability** and cannot be fixed by writing a cleverer reverse Transformer.

### 3.3. The two directions can have different valid domains

A function A→B may handle all v1 states, while B→A handles only the subset of v2 states legacy understands:

~~~text
A.statusCode: N | P | C
B.state:      NEW | PAID | CANCELLED | REFUNDED

A→B: N/P/C all have mappings
B→A: REFUNDED has no valid mapping
~~~

There is no guarantee that both Translators are **total functions** over all values. Define them as **partial mappings** returning clear errors for out-of-domain inputs.

## 4. How Message Translator differs from related patterns

| Component | Responsibility | Relationship to bidirectional translation |
|---|---|---|
| **Message Translator EIP** | Converts representations between two systems | Overall A↔B pattern |
| **Spring Integration Transformer** | Executes payload/message conversion | Implements one or more Translators |
| **Normalizer EIP** | Multiple input formats converge to canonical form | Usually uses multiple unidirectional Translators |
| **Envelope Wrapper** | Wraps payload with metadata across boundaries | Can wrap before / unwrap after translation |
| **Header Enricher** | Adds metadata in headers | Cannot recover lost payload fields by itself |
| **Content-based Router** | Selects branch by type/version | Routes A→B or to version adapters |
| **Filter** | Accepts/discards messages by condition | Blocks translation outcomes failing policy |
| **Idempotent Receiver** | Prevents duplicate side effects | Uses stable event ID after translation |
| **Aggregator** | Collects parts by group/release rule | Needs immutable correlation/business IDs |
| **Gateway** | Request-reply bridge | Needs a reply path even when translation fails |

A Transformer can convert a Java `LegacyOrderV1` into `CanonicalOrderV2`, yet **it does not by itself verify** that no data was lost or that two transformations are inverses. That responsibility belongs to the **contract, implementation, and tests**.

### 4.1. Translator vs. pure serialization/deserialization

Serialize:

~~~text
CanonicalOrderV2 Java object -> JSON bytes
~~~

Translate:

~~~text
LegacyOrderV1 semantics -> CanonicalOrderV2 semantics
~~~

When wire formats A and B differ, an adapter may both decode and translate; still keep the two concerns separate so you know whether a failure happened in **parsing/encoding** or in **semantic mapping**.

## 5. Seven typical categories of data loss

### 5.1. Dropped fields

A has `legacyPromotionCode`, B does not: the field is lost going A→B. This is not a deserialization failure; schema B is valid yet **lacks the data needed to reconstruct A**.

### 5.2. Collapsing multiple values into one

~~~text
A.status: PAID_BY_CARD | PAID_BY_BANK
B.status: PAID
~~~

Both source statuses map to one target status. Reverse-translating from `PAID` cannot recover the original payment method.

### 5.3. Truncation, rounding, or overflow

~~~text
A.amount = 19.999 USD
B.amountMinorUnits = 2000
~~~

Rounding **discards precision** and can violate financial rules. In this lesson, the Translator **rejects** amounts that cannot be represented exactly in minor units rather than rounding silently.

### 5.4. String normalization and loss of lexical form

~~~text
A = "00025.00"
B = 2500 (cents)
A' = "25.00"
~~~

Same business amount, yet **the original string representation is lost**. If digital signatures or audits require the exact raw original bytes, store the original separately.

### 5.5. Loss of timezone and time precision

~~~text
A = "2026-11-21T09:00:00+07:00"
B = 2026-11-21T02:00:00Z
~~~

Both represent the same `Instant` yet **not the same offset text**. Storing only a local datetime without a timezone can make recovering the original instant impossible during DST overlaps or gaps. The contract must specify whether to preserve the *instant* or the *local wall-clock/timezone identity*.

### 5.6. Null, absent, empty, and default

~~~text
A: field absent
B: field=null
A': field=""

A: discountPercent=0
B: discountPercent=null
~~~

**Not provided**, **explicitly null**, **empty string**, and **numeric zero** can carry distinct meanings. A codec that strips null fields or injects defaults can destroy the original state.

### 5.7. Collections, encodings, and metadata

- Converting an ordered list to a set → loses ordering and duplicates.
- Map key normalization merges distinct keys.
- Unicode normalization can alter byte sequences despite identical visual appearance.
- Decoding binary fields as Strings with the wrong charset → data corruption.
- Dropping unknown JSON fields → breaks round-trips to newer schemas.
- Dropping Spring headers like `correlationId` or `replyChannel` → loses routing context.
- Serialized signatures become invalid after re-encoding even when business data is equivalent.

## 6. Example contract A↔B

We scope this lesson to **two currencies, USD and VND**, so currency units and scale are clear. This is an **illustrative application support matrix**, not a claim that all ISO currencies share identical decimal digit counts.

| Attribute | Legacy A | Canonical B | Result |
|---|---|---|---|
| Event ID | `eventId` | `eventId` | Preserved unchanged |
| Tenant | `tenantId` | `tenantId` | Preserved unchanged; must authenticate at ingress |
| Order ID | `orderNo` | `orderId` | Renamed; preserves business identity |
| Amount | `amountMajorText` | `totalMinorUnits` | Exact parse/conversion |
| Currency | `currency` | `currency` | Preserved |
| Status | `statusCode=N/P/C` | `state=NEW/PAID/CANCELLED/REFUNDED` | B→A cannot map `REFUNDED` |
| Legacy promotion | `legacyPromotionCode` | **Does not exist** | Risk of data loss |

### 6.1. Conditions for accepting a translation

- `eventId`, `tenantId`, and `orderNo`/`orderId` are non-blank strings matching ID grammar.
- `currency` is `USD` or `VND` in this example.
- `amountMajorText` has valid decimal syntax, is positive, and converts **exactly** to `long` minor units.
- `state` and `statusCode` belong to published sets; unknown codes never map to `PAID` or `CANCELLED`.
- When `legacyPromotionCode` is present, A→B must emit a **loss report** or reject per policy.
- B→A must not claim to recover historical promotion codes because B does not hold them.
- Business event ID stays unchanged when forwarding the same logical event.
- Translations may **differ in lexical amount text** as long as the monetary business value is equivalent.

### 6.2. One source event does not imply minting a new event

Boundary Translators usually **convert representation**, not emit new business events. Never call `UUID.randomUUID()` as the `eventId` on every translation. Only when a service genuinely creates a *derived event* (e.g., `ShipmentRequested` from `OrderCreated`) should you allocate a new event ID with proper causation linkage.

## 7. Money: major units → minor units without `double`

In the demo contract, `USD` has two minor-unit digits and `VND` uses whole integers with zero decimal places.

~~~text
USD:
  "25.00" major -> 2500 minor
  "25.001" major -> cannot be represented exactly (reject)

VND:
  "25000" major -> 25000 minor
  "25000.50" major -> cannot be represented exactly (reject)
~~~

Do not write:

~~~java
// Anti-pattern: floating-point can cause rounding errors.
double major = Double.parseDouble("19.99");
long cents = (long) (major * 100);
~~~

Use `BigDecimal` with exact checks:

~~~java
import java.math.BigDecimal;

public final class MoneyConversions {

    private MoneyConversions() {}

    public static long toMinorExact(
            String majorText,
            String currency) {

        if (majorText == null || majorText.isBlank()) {
            throw new TranslationContractException(
                    "AMOUNT_REQUIRED");
        }

        int scale = fractionDigits(currency);

        final BigDecimal major;
        try {
            major = new BigDecimal(majorText);
        }
        catch (NumberFormatException ex) {
            throw new TranslationContractException(
                    "AMOUNT_FORMAT_INVALID", ex);
        }

        if (major.signum() <= 0) {
            throw new TranslationContractException(
                    "AMOUNT_MUST_BE_POSITIVE");
        }

        try {
            return major.movePointRight(scale)
                    .longValueExact();
        }
        catch (ArithmeticException ex) {
            throw new TranslationContractException(
                    "AMOUNT_NOT_EXACT_OR_OVERFLOW", ex);
        }
    }

    public static String toMajorCanonical(
            long minor,
            String currency) {

        if (minor <= 0) {
            throw new TranslationContractException(
                    "AMOUNT_MUST_BE_POSITIVE");
        }

        int scale = fractionDigits(currency);
        return BigDecimal.valueOf(minor, scale)
                .toPlainString();
    }

    private static int fractionDigits(String currency) {
        return switch (currency) {
            case "USD" -> 2;
            case "VND" -> 0;
            default -> throw new TranslationContractException(
                    "CURRENCY_UNSUPPORTED");
        };
    }
}
~~~

This is an **exact converter for the USD/VND demo**, not an FX engine or general ISO 4217 library. Expanding currencies requires defining per-currency rounding/scale and business contracts, plus testing unit changes, overflows, and currency-specific edge cases.

### 7.1. Exact minor units do not mean preserving the lexical string

~~~text
Input A: amountMajorText="0025.000"
B:       totalMinorUnits=2500
Output A': amountMajorText="25.00"
~~~

In monetary semantics, both amounts are equivalent; in **byte/lexical equality**, they differ. If audits require the raw `amountMajorText`, preserve the original via a sidecar/extension or raw store—it cannot be reconstructed from `long`.

### 7.2. Rejected inputs

| Input | Currency | Outcome |
|---|---|---|
| `"25.00"` | USD | 2500 |
| `"25.001"` | USD | `AMOUNT_NOT_EXACT_OR_OVERFLOW` |
| `"25000"` | VND | 25000 |
| `"25000.50"` | VND | `AMOUNT_NOT_EXACT_OR_OVERFLOW` |
| `"-1"` | USD | `AMOUNT_MUST_BE_POSITIVE` |
| `"abc"` | USD | `AMOUNT_FORMAT_INVALID` |
| `"1E1000"` | USD | Reject overflow/range |
| `"10"` | XXX | `CURRENCY_UNSUPPORTED` |

Most errors here are **deterministic contract violations**; retrying the exact same payload unchanged cannot fix them.

## 8. Enums and states that cannot be reverse-translated

Legacy contract:

~~~text
N = NEW
P = PAID
C = CANCELLED
~~~

Canonical adds `REFUNDED`:

~~~java
public enum OrderState {
    NEW,
    PAID,
    CANCELLED,
    REFUNDED
}
~~~

### 8.1. Fail-fast forward mapping

~~~java
public static OrderState toCanonicalState(
        String legacyCode) {

    return switch (legacyCode) {
        case "N" -> OrderState.NEW;
        case "P" -> OrderState.PAID;
        case "C" -> OrderState.CANCELLED;
        default -> throw new TranslationContractException(
                "LEGACY_STATE_UNSUPPORTED");
    };
}
~~~

### 8.2. Reverse mapping is a partial function

~~~java
public static String toLegacyState(
        OrderState state) {

    return switch (state) {
        case NEW -> "N";
        case PAID -> "P";
        case CANCELLED -> "C";
        case REFUNDED -> throw new TranslationContractException(
                "TARGET_STATE_NOT_REPRESENTABLE");
    };
}
~~~

Never map `REFUNDED` to `CANCELLED` because the two business actions differ. If a partner truly wants a "generic terminal" state, obtain **explicit approval and a separate contract**, plus a loss report. Never write `default -> "C"` just to dodge updating mappings.

### 8.3. An unknown code is not automatically `UNKNOWN`

Some systems support a valid `UNKNOWN` state; others treat unknown codes as corrupted data. If you add `UNKNOWN` to canonical, explicitly define how downstream may handle it. Mapping every unrecognized code to `UNKNOWN` and letting fulfillment run can trigger wrong side effects.

## 9. Null, absent, defaults, and data ordering

### 9.1. Optional source fields

`legacyPromotionCode=null` can mean "no promotion" or "not provided" depending on the contract. `legacyPromotionCode="SPRING-2026"` is lost when converting to B because B has no field for it. On reverse translation, you cannot know the original code and must never invent one.

### 9.2. Absent differs from explicit null

JSON examples:

~~~json
{"orderNo": "ORDER-101"}
~~~

and:

~~~json
{"orderNo": "ORDER-101", "legacyPromotionCode": null}
~~~

may map to the **exact same Java record with `legacyPromotionCode=null`** if Jackson does not track field presence. If exact round-trip distinction matters, use `JsonNode`/presence markers, schema unions, or raw original representations.

### 9.3. Collections

If A holds an ordered `List<LineItem>` while B converts it to a `Set<LineItem>`, you can lose ordering and valid duplicate items. Even if a Reverse Translator converts the `Set` back to a `List`, it lacks the information to restore the original sequence.

### 9.4. Timestamps

One system stores `OffsetDateTime`, while the other stores only `Instant` or `LocalDateTime`. Converting to UTC preserves the **point in time**, yet the original offset cannot be recovered automatically. Dropping timezones is even worse when local datetimes fall into repeated or nonexistent DST hours. The contract must state whether to preserve the *instant* or the *local wall-clock/timezone identity*.

## 10. Engineering specification before writing the Translator

Create a **mapping ledger** for review:

| Field / invariant | A→B | B→A | Loss policy |
|---|---|---|---|
| `eventId` | Keep unchanged | Keep unchanged | Loss unacceptable |
| `tenantId` | Keep unchanged, auth | Keep unchanged | Alteration unacceptable |
| `orderNo`/`orderId` | Rename | Reverse rename | Compare value |
| `amountMajorText`/minor | Exact scale conversion | Canonical decimal text | Published lexical form loss |
| `statusCode`/`state` | N/P/C → enum | `REFUNDED` unrepresentable | Reject |
| `legacyPromotionCode` | No target | Cannot recover | Loss report / quarantine |
| `schemaVersion` | Input contract | Output contract | Record provenance |
| `MessageHeaders.ID` | Runtime-generated | Runtime-generated | Never use as business event ID |
| `correlationId` | Preserve per contract | Preserve per contract | Never generate randomly |
| `traceparent` | Propagate per trust policy | Propagate per trust policy | Never mix with business identity |

**Policies must be decided before translating:** does the outbound target permit dropping the promotion code? If not, A→B must **reject/quarantine**, or introduce a canonical extension/sidecar storing it. If yes, add telemetry showing which fields were dropped and why.
## 11. Java 17: DTOs, loss reports, and exceptions

We use records so payload fields remain immutable after creation. Each `public` top-level declaration in the code blocks below belongs in its **own matching Java file** under Java 17+.

### 11.1. Source DTO A (legacy)

~~~java
public record LegacyOrderV1(
        String eventId,
        String tenantId,
        String orderNo,
        String amountMajorText,
        String currency,
        String statusCode,
        String legacyPromotionCode
) {}
~~~

### 11.2. Target DTO B (canonical)

~~~java
public record CanonicalOrderV2(
        String eventId,
        String tenantId,
        String orderId,
        long totalMinorUnits,
        String currency,
        OrderState state
) {}
~~~

`OrderState` from section 8 supports `NEW`, `PAID`, `CANCELLED`, and `REFUNDED`. B supporting a new state does not mean A understands it.

### 11.3. Loss report without sensitive data

~~~java
public record TranslationLoss(
        String fieldName,
        String reasonCode
) {}
~~~

`fieldName` and `reasonCode` come from a finite vocabulary; never embed raw promotion codes, customer names, tokens, or payloads inside reasons. When operators need event specifics, query an access-controlled audit store by event identity.

### 11.4. Outcome holding the original for quarantine handling

~~~java
import java.util.List;
import java.util.Objects;

public record TranslationOutcome<S, T>(
        S original,
        T translated,
        List<TranslationLoss> losses
) {
    public TranslationOutcome {
        Objects.requireNonNull(original, "original");
        Objects.requireNonNull(translated, "translated");
        losses = List.copyOf(losses);
    }

    public boolean lossless() {
        return losses.isEmpty();
    }
}
~~~

Here `TranslationOutcome` retains `original` internally so quarantine/reconciliation can access the original message when genuinely needed. **Never serialize the whole outcome** to partners or business topics expecting only `translated`: leaking `original` exposes legacy contents.

`lossless()` by itself only means **no field flagged as lost by this Translator under its contract**; it does not promise byte-for-byte equality—for example, lexical amounts can still be canonicalized even when the loss list is empty.

### 11.5. Contract exception

~~~java
public final class TranslationContractException
        extends RuntimeException {

    private final String reasonCode;

    public TranslationContractException(
            String reasonCode) {
        super(reasonCode);
        this.reasonCode = reasonCode;
    }

    public TranslationContractException(
            String reasonCode,
            Throwable cause) {
        super(reasonCode, cause);
        this.reasonCode = reasonCode;
    }

    public String reasonCode() {
        return reasonCode;
    }
}
~~~

Outcome comparison table:

| Result | Example | Action |
|---|---|---|
| Translated + no flagged loss | A has no promo code | Eligible for business handler after validation |
| Translated + flagged loss | Has `legacyPromotionCode`, unsupported by B | Quarantine / explicit approval |
| Contract exception | Unknown legacy status `"H"` | Reject; emit no business output |
| Contract exception | B state `REFUNDED` unmappable to A | Unsupported reverse mapping |
| Infrastructure failure | Mapping registry/service temporarily down | Bounded retry; never classify as field loss |

A loss report **is not an exception**: a valid B value may be produced yet **barred from entering the business flow** if policy forbids dropping fields.

## 12. Bidirectional Translator with explicit data-loss decisions

### 12.1. Enum mapper

~~~java
public final class OrderStateMappings {

    private OrderStateMappings() {}

    public static OrderState toCanonicalState(
            String legacyCode) {

        if (legacyCode == null) {
            throw new TranslationContractException(
                    "LEGACY_STATE_REQUIRED");
        }

        return switch (legacyCode) {
            case "N" -> OrderState.NEW;
            case "P" -> OrderState.PAID;
            case "C" -> OrderState.CANCELLED;
            default -> throw new TranslationContractException(
                    "LEGACY_STATE_UNSUPPORTED");
        };
    }

    public static String toLegacyState(
            OrderState state) {

        if (state == null) {
            throw new TranslationContractException(
                    "CANONICAL_STATE_REQUIRED");
        }

        return switch (state) {
            case NEW -> "N";
            case PAID -> "P";
            case CANCELLED -> "C";
            case REFUNDED -> throw new TranslationContractException(
                    "TARGET_STATE_NOT_REPRESENTABLE");
        };
    }
}
~~~

Enum mapping avoids `name()`/`valueOf()` when systems use distinct vocabularies. The new `REFUNDED` state is intentionally rejected instead of pretending to be `CANCELLED`.

### 12.2. `PartnerOrderTranslator`

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.regex.Pattern;

public final class PartnerOrderTranslator {

    private static final Pattern IDENTIFIER =
            Pattern.compile("[A-Za-z0-9._-]+");

    public TranslationOutcome<LegacyOrderV1, CanonicalOrderV2>
    toCanonical(LegacyOrderV1 source) {

        if (source == null) {
            throw new TranslationContractException(
                    "LEGACY_PAYLOAD_REQUIRED");
        }

        requireId(source.eventId(), "EVENT_ID_INVALID");
        requireId(source.tenantId(), "TENANT_ID_INVALID");
        requireId(source.orderNo(), "ORDER_ID_INVALID");

        // Validate exact decimal, currency scale, and overflow.
        long minor = MoneyConversions.toMinorExact(
                source.amountMajorText(),
                source.currency());

        OrderState state =
                OrderStateMappings.toCanonicalState(
                        source.statusCode());

        CanonicalOrderV2 translated = new CanonicalOrderV2(
                source.eventId(),
                source.tenantId(),
                source.orderNo(),
                minor,
                source.currency(),
                state);

        List<TranslationLoss> losses = new ArrayList<>();

        if (source.legacyPromotionCode() != null
                && !source.legacyPromotionCode().isBlank()) {
            losses.add(new TranslationLoss(
                    "legacyPromotionCode",
                    "FIELD_NOT_REPRESENTABLE_IN_CANONICAL"));
        }

        return new TranslationOutcome<>(
                source, translated, losses);
    }

    public TranslationOutcome<CanonicalOrderV2, LegacyOrderV1>
    toLegacy(CanonicalOrderV2 source) {

        if (source == null) {
            throw new TranslationContractException(
                    "CANONICAL_PAYLOAD_REQUIRED");
        }

        requireId(source.eventId(), "EVENT_ID_INVALID");
        requireId(source.tenantId(), "TENANT_ID_INVALID");
        requireId(source.orderId(), "ORDER_ID_INVALID");

        String amountText =
                MoneyConversions.toMajorCanonical(
                        source.totalMinorUnits(),
                        source.currency());

        String legacyStatus =
                OrderStateMappings.toLegacyState(
                        source.state());

        LegacyOrderV1 translated = new LegacyOrderV1(
                source.eventId(),
                source.tenantId(),
                source.orderId(),
                amountText,
                source.currency(),
                legacyStatus,
                null);

        // No legacy promotion field on source B to lose.
        // However, this method does NOT promise to reconstruct historical A.
        return new TranslationOutcome<>(
                source, translated, List.of());
    }

    private static void requireId(
            String id, String error) {

        if (id == null
                || !IDENTIFIER.matcher(id).matches()) {
            throw new TranslationContractException(error);
        }
    }
}
~~~

**Reading the code accurately:**

- `toCanonical` preserves event ID, tenant ID, and business order ID.
- `MoneyConversions.toMinorExact` from section 7 uses `BigDecimal`, never rounding silently.
- `OrderStateMappings` rejects unrecognized statuses.
- Legacy promotion code **cannot be represented in B**: translation returns B with a `TranslationLoss` for policy to decide.
- `toLegacy` produces a valid legacy message from B for **a new outbound operation**, without data to reconstruct a historical A's promotion code. `legacyPromotionCode=null` does not prove the original legacy message lacked a promo.
- `toLegacy` rejects `REFUNDED` rather than emitting a fake `CANCELLED`.

**Note on `lossless()`:** If `toLegacy` receives a B whose promo was lost during A→B, it sees no trace of that loss inside B. Therefore, **looking solely at the B→A outcome is insufficient to prove an A→B→A round-trip was lossless**. Carry the first leg's loss report/provenance across boundaries if round-trip verification is needed.

### 12.3. Quarantine is not "successfully processed"

Because `TranslationOutcome` retains the original input, a loss report can route to quarantine for operators to inspect, add mappings, or ask the partner for clarification. Yet it **must not be ACKed as business success** if the contract guarantees zero lost orders. ACK/NACK policy belongs to the transport adapter and transaction, not to a Java record or sending to a `QueueChannel`.

### 12.4. Never fabricate defaults from uncertain context

If Legacy A lacks a currency and B requires one, never guess from timezone, IP country, or user profile. A default currency is valid only when a **trusted input endpoint's contract** guarantees every amount uses one fixed currency, backed by version/schema rules. Arbitrary defaults cause severe financial errors.

## 13. Unit tests: translations and loss reports

These tests use only JUnit 5 and the Java classes above; no Spring context is needed yet.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class PartnerOrderTranslatorTest {

    private final PartnerOrderTranslator translator =
            new PartnerOrderTranslator();

    private LegacyOrderV1 sample(String promotion) {
        return new LegacyOrderV1(
                "evt-order-1001",
                "tenant-a",
                "ORDER-101",
                "25.00",
                "USD",
                "P",
                promotion);
    }

    @Test
    void nonEmptyLegacyPromotionIsReportedAsLoss() {
        LegacyOrderV1 input = sample("SPRING-2026");

        var outcome = translator.toCanonical(input);

        assertFalse(outcome.lossless());
        assertEquals(
                "FIELD_NOT_REPRESENTABLE_IN_CANONICAL",
                outcome.losses().get(0).reasonCode());
        assertEquals(
                "legacyPromotionCode",
                outcome.losses().get(0).fieldName());

        assertEquals(
                2500L,
                outcome.translated().totalMinorUnits());
        assertEquals(
                OrderState.PAID,
                outcome.translated().state());

        // Original is retained inside internal outcome for quarantine.
        assertEquals(
                "SPRING-2026",
                outcome.original().legacyPromotionCode());
    }

    @Test
    void noLegacyPromotionCanPassLossPolicy() {
        var outcome = translator.toCanonical(sample(null));

        assertTrue(outcome.lossless());
        assertEquals(
                "evt-order-1001",
                outcome.translated().eventId());
        assertEquals(
                "ORDER-101",
                outcome.translated().orderId());
    }

    @Test
    void amountWithExtraFractionalCentIsRejected() {
        LegacyOrderV1 input = new LegacyOrderV1(
                "evt-order-1002", "tenant-a",
                "ORDER-102", "25.001", "USD",
                "P", null);

        TranslationContractException exception =
                assertThrows(
                        TranslationContractException.class,
                        () -> translator.toCanonical(input));

        assertEquals(
                "AMOUNT_NOT_EXACT_OR_OVERFLOW",
                exception.reasonCode());
    }

    @Test
    void unsupportedLegacyStatusCannotBecomePaid() {
        LegacyOrderV1 input = new LegacyOrderV1(
                "evt-order-1003", "tenant-a",
                "ORDER-103", "10.00", "USD",
                "H", null);

        TranslationContractException exception =
                assertThrows(
                        TranslationContractException.class,
                        () -> translator.toCanonical(input));

        assertEquals(
                "LEGACY_STATE_UNSUPPORTED",
                exception.reasonCode());
    }

    @Test
    void refundedIsNotMappedToCancelled() {
        CanonicalOrderV2 source = new CanonicalOrderV2(
                "evt-refund-1001",
                "tenant-a",
                "ORDER-101",
                2500,
                "USD",
                OrderState.REFUNDED);

        TranslationContractException exception =
                assertThrows(
                        TranslationContractException.class,
                        () -> translator.toLegacy(source));

        assertEquals(
                "TARGET_STATE_NOT_REPRESENTABLE",
                exception.reasonCode());
    }

    @Test
    void exactDomainRoundTripPreservesBusinessFields() {
        LegacyOrderV1 source = sample(null);

        var canonical = translator.toCanonical(source);
        var back = translator.toLegacy(
                canonical.translated());

        assertEquals(
                source.eventId(), back.translated().eventId());
        assertEquals(
                source.tenantId(), back.translated().tenantId());
        assertEquals(
                source.orderNo(), back.translated().orderNo());
        assertEquals(
                source.currency(), back.translated().currency());
        assertEquals(
                source.statusCode(), back.translated().statusCode());
        assertEquals(
                source.amountMajorText(),
                back.translated().amountMajorText());

        assertEquals(
                source, back.translated());
    }

    @Test
    void lexicalAmountCanChangeDespiteSemanticEquality() {
        LegacyOrderV1 source = new LegacyOrderV1(
                "evt-order-1004", "tenant-a",
                "ORDER-104", "0025.000", "USD",
                "P", null);

        var canonical = translator.toCanonical(source);
        var back = translator.toLegacy(
                canonical.translated());

        assertEquals(
                2500L, canonical.translated().totalMinorUnits());

        assertEquals(
                "25.00", back.translated().amountMajorText());

        // Different lexical bytes, even though monetary value is both 25.00 USD.
        assertNotEquals(
                source.amountMajorText(),
                back.translated().amountMajorText());
    }
}
~~~

### 13.1. Why doesn't the first test call `assertEquals(A, A')`?

Because `legacyPromotionCode` is not stored in canonical, `A'` will not equal `A`. Forcing an equality test across all inputs and "fixing" the Translator by defaulting a promotion code hides the real loss. Tests must reflect the **preservable domain** and explicitly document when outputs differ per policy.

### 13.2. Test canonical reverse separately

A canonical B created internally may carry `REFUNDED`, which legacy cannot express. Test not only A→B→A, but also B→A→B:

~~~java
@Test
void canonicalReverseRoundTripWorksForSharedStates() {
    CanonicalOrderV2 initial = new CanonicalOrderV2(
            "evt-order-2001", "tenant-a",
            "ORDER-201", 7500L, "USD",
            OrderState.NEW);

    CanonicalOrderV2 result =
            translator.toCanonical(
                    translator.toLegacy(initial).translated())
                    .translated();

    assertEquals(initial, result);
}
~~~

Add this method to the test class above. For `REFUNDED`, the B→A→B round-trip does not exist because reverse mapping rejects it—the exact behavior required by the support matrix.

## 14. Java DSL: two flows enforcing loss policy before business logic

Use Spring Integration Java DSL to wire both paths:

~~~text
partner.orders.in
    -> Translator A→B
    -> TranslationOutcome
    -> lossless?
         yes -> extract translated CanonicalOrderV2 -> orders.canonical.accepted
         no  -> orders.translation.quarantine

orders.canonical.out
    -> Translator B→A
    -> TranslationOutcome
    -> extract translated LegacyOrderV1
    -> partner.orders.out
~~~

**Important:** only `translated` reaches business/outbound channels; `TranslationOutcome` carrying the original payload and loss details remains strictly inside internal validation/quarantine paths.

### 14.1. Spring configuration

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;

@Configuration
@EnableIntegration
public class BidirectionalTranslatorConfiguration {

    @Bean
    public PartnerOrderTranslator partnerOrderTranslator() {
        return new PartnerOrderTranslator();
    }

    @Bean(name = "partner.orders.in")
    public MessageChannel legacyInbound() {
        return new DirectChannel();
    }

    @Bean(name = "orders.canonical.accepted")
    public PollableChannel canonicalAccepted() {
        return new QueueChannel();
    }

    @Bean(name = "orders.translation.quarantine")
    public PollableChannel quarantinedTranslations() {
        return new QueueChannel();
    }

    @Bean(name = "orders.canonical.out")
    public MessageChannel canonicalOutbound() {
        return new DirectChannel();
    }

    @Bean(name = "partner.orders.out")
    public PollableChannel partnerOutbound() {
        return new QueueChannel();
    }

    @Bean
    public IntegrationFlow legacyToCanonicalFlow(
            PartnerOrderTranslator translator) {

        return IntegrationFlow
                .from("partner.orders.in")
                .transform(
                        LegacyOrderV1.class,
                        translator::toCanonical)
                .filter(
                        TranslationOutcome.class,
                        TranslationOutcome::lossless,
                        filter -> filter.discardChannel(
                                "orders.translation.quarantine"))
                .transform(
                        TranslationOutcome.class,
                        TranslationOutcome::translated)
                .channel("orders.canonical.accepted")
                .get();
    }

    @Bean
    public IntegrationFlow canonicalToPartnerFlow(
            PartnerOrderTranslator translator) {

        return IntegrationFlow
                .from("orders.canonical.out")
                .transform(
                        CanonicalOrderV2.class,
                        translator::toLegacy)
                .transform(
                        TranslationOutcome.class,
                        TranslationOutcome::translated)
                .channel("partner.orders.out")
                .get();
    }
}
~~~

**Demo scope:** `DirectChannel` + `QueueChannel` inside one JVM for testing translation. This is not a full broker consumer/HTTP adapter; there are no transactions, persistent quarantine, ACKs, or remote authentication. `orders.translation.quarantine` receives `TranslationOutcome`, **not `ErrorMessage`**. If an exception occurs inside `toCanonical` or `toLegacy`, it follows exception/error-channel handling rather than entering the Filter discard channel automatically.

### 14.2. Why does the `lossless` Filter sit right after the Translator?

Source A may map into a structurally valid B that dropped `legacyPromotionCode`. If the flow sent B straight to a business handler, knowledge of the dropped data would vanish. The Filter inspects the **outcome carrying loss details** before extracting `translated`.

In production, policies can be finer-grained: allowing loss of a business-approved display field while forbidding loss of payment/audit fields. Use **typed loss severities/allowlists** and explicit approvals rather than replacing `lossless` with ad-hoc conditions.

### 14.3. Quarantine needs persistence and retention

`QueueChannel` is a test fixture, not durable across restarts. On real data, quarantine needs a durable store, reason codes, event IDs, source/version, access controls, encryption, and replay policies. If the business cannot tolerate losing a message, routing to an in-memory quarantine and ACKing the broker can still lose work if the process crashes.

### 14.4. The reverse flow does not prove round-trip recovery of original A

The B→A flow outputs `LegacyOrderV1` with `legacyPromotionCode=null` because B lacks that field. That is valid when **emitting a new canonical order to a partner**. If you use B to update a legacy A that originally had a promotion code, fetch the original via a trusted store or extension—never assume `PartnerOrderTranslator` can conjure it back.

## 15. Integration tests across Spring Integration channels

The test below verifies actual routing/transformer wiring and confirms lossy outputs never reach the canonical business channel.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(
        classes = BidirectionalTranslatorConfiguration.class)
class BidirectionalTranslatorFlowTest {

    @Autowired
    @Qualifier("partner.orders.in")
    MessageChannel partnerInbound;

    @Autowired
    @Qualifier("orders.canonical.accepted")
    PollableChannel canonicalAccepted;

    @Autowired
    @Qualifier("orders.translation.quarantine")
    PollableChannel quarantine;

    @Autowired
    @Qualifier("orders.canonical.out")
    MessageChannel canonicalOutbound;

    @Autowired
    @Qualifier("partner.orders.out")
    PollableChannel partnerOutbound;

    private LegacyOrderV1 legacy(String promo) {
        return new LegacyOrderV1(
                "evt-order-3001", "tenant-a",
                "ORDER-301", "19.99", "USD",
                "P", promo);
    }

    @Test
    void reversibleInputReachesCanonicalChannel() {
        assertTrue(partnerInbound.send(
                MessageBuilder.withPayload(legacy(null))
                        .build()));

        Message<?> accepted = canonicalAccepted.receive(1000);
        assertNotNull(accepted);
        assertInstanceOf(
                CanonicalOrderV2.class, accepted.getPayload());

        CanonicalOrderV2 order =
                (CanonicalOrderV2) accepted.getPayload();

        assertEquals(1999L, order.totalMinorUnits());
        assertEquals(OrderState.PAID, order.state());
        assertEquals("evt-order-3001", order.eventId());
        assertNull(quarantine.receive(0));
    }

    @Test
    void lossyInputIsQuarantinedBeforeBusinessOutput() {
        assertTrue(partnerInbound.send(
                MessageBuilder.withPayload(
                        legacy("SPRING-2026"))
                        .build()));

        Message<?> rejected = quarantine.receive(1000);
        assertNotNull(rejected);
        assertInstanceOf(
                TranslationOutcome.class,
                rejected.getPayload());

        TranslationOutcome<?, ?> outcome =
                (TranslationOutcome<?, ?>) rejected.getPayload();

        assertFalse(outcome.lossless());
        assertEquals(
                "legacyPromotionCode",
                outcome.losses().get(0).fieldName());

        assertNull(canonicalAccepted.receive(0));
    }

    @Test
    void canonicalOrderCanBeTranslatedForPartner() {
        CanonicalOrderV2 canonical =
                new CanonicalOrderV2(
                        "evt-order-3002", "tenant-a",
                        "ORDER-302", 2500L, "USD",
                        OrderState.NEW);

        assertTrue(canonicalOutbound.send(
                MessageBuilder.withPayload(canonical)
                        .build()));

        Message<?> translated = partnerOutbound.receive(1000);
        assertNotNull(translated);
        assertInstanceOf(
                LegacyOrderV1.class,
                translated.getPayload());

        LegacyOrderV1 legacy =
                (LegacyOrderV1) translated.getPayload();

        assertEquals("25.00", legacy.amountMajorText());
        assertEquals("N", legacy.statusCode());
        assertEquals(
                "evt-order-3002", legacy.eventId());
        assertNull(legacy.legacyPromotionCode());
    }

    @Test
    void reverseUnsupportedStateDoesNotEmitFakeCancellation() {
        CanonicalOrderV2 refunded =
                new CanonicalOrderV2(
                        "evt-refund-3003", "tenant-a",
                        "ORDER-303", 5000L, "USD",
                        OrderState.REFUNDED);

        assertThrows(RuntimeException.class,
                () -> canonicalOutbound.send(
                        MessageBuilder.withPayload(refunded)
                                .build()));

        assertNull(partnerOutbound.receive(0));
    }
}
~~~

These tests require no real broker. Using `SpringJUnitConfig` and channel beans, they verify each branch by DTO runtime types. If your test suite shares a cached `ApplicationContext` and `QueueChannel`s, drain queues between tests or use unique events to prevent leftover messages, especially under parallel execution.

### 15.1. Integration tests do not replace contract/wire tests

Even when Java methods pass, a serializer might turn `amountMajorText="25.00"` into JSON number `25.0`, strip nulls, or rename fields. Test **serialized JSON/Avro/Protobuf** against real fixtures from both sides rather than comparing only in-JVM Java records.

### 15.2. Invalid inputs do not automatically enter the Filter's quarantine

If `toCanonical` throws `TranslationContractException` on a non-exact amount, the `lossless` Filter never runs. That is a **translation failure**; it follows Spring Integration exception/error-channel routing per topology rather than landing on `orders.translation.quarantine`. If all invalid events require investigation records, configure a dedicated error flow/quarantine adapter or classify **before** the Transformer.

## 16. Headers, metadata, and correlation across both directions

Spring Integration carries orchestration info in `MessageHeaders`, yet never assume those headers are business data or survive every serializer and hop intact.

| Metadata | A→B | B→A | Notes |
|---|---|---|---|
| `eventId` in payload | Preserve | Preserve | Business event identity; never mint new |
| `tenantId` | Preserve + authenticate | Preserve | Never trust unverified payload blindly |
| `orderId` | Map from `orderNo` | Map to `orderNo` | Stable group key for Aggregator |
| `businessCorrelationId` | Preserve per contract | Preserve | Distinct from schema version / trace |
| `traceparent` | Forward via tracing adapter when allowed | Same | Never use as idempotency key |
| Spring `MessageHeaders.ID` | May change on transform | May change | Not a logical event ID |
| `replyChannel`/`errorChannel` | Runtime-local | Runtime-local | Copy only when topology/namespace fits |
| `contentType` | Update after serialization | Update | Avoid stale content types |
| `schemaVersion` | Input version A → output version B | B → A | Never keep old version on new payload |
| `Authorization`/secrets | Never copy casually | Never copy casually | Authenticate per hop |

### 16.1. Spring Transformer and header propagation

When `.transform(PartnerOrderV1.class, ...)` returns a **new payload**, Spring Integration may carry input headers onto the output message via the Transformer endpoint, yet which headers survive depends on implementation, returning `Message<?>` vs. payload, serialization, and adapter mapping.

**Never treat default header propagation as a security policy.** Before emitting onto another transport, enforce an explicit allowlist/mapper for business correlation and permitted tracing context. Never serialize raw `replyChannel`/`errorChannel` objects or bearer tokens onto brokers.

### 16.2. Schema version must describe the current payload

If A is schema v1 and B is schema v2:

~~~text
Inbound:
  payload=LegacyOrderV1
  schemaVersion=1

Outbound:
  payload=CanonicalOrderV2
  schemaVersion=2
  sourceSchemaVersion=1
~~~

Changing only the Java type without updating `schemaVersion` causes downstream to pick the wrong decoder. `sourceSchemaVersion` helps audit and provenance, but never replaces the current schema version.

### 16.3. Correlation must never depend on lexical amount

A business key should use trusted tenant/order IDs, never amounts or statuses: amounts change representation across Translators and statuses evolve over time. If Payment and Inventory events use separate IDs, map to a canonical business identity before the Aggregator.

### 16.4. Preserve source provenance without copying source secrets

You can record `sourceSystem`, `sourceSchemaVersion`, and `translationVersion` in internal metadata under namespace and trust policies. Still, if those fields pose cardinality risks or carry sensitive identifiers, restrict logs, headers, and retention.

## 17. Strict mode, tolerant mode, and loss budgets

**No single loss policy fits every use case.**

### 17.1. Strict translation

Requirements:

- Every required field has an exact mapping.
- Unknown enums/states are rejected.
- Monetary conversions perform no silent rounding.
- Present `legacyPromotionCode` when canonical lacks a field → reject or quarantine.
- Only approved business outputs reach downstream.

Suited for payments, fulfillment, legal/audit data, or events where meaning reduction is unacceptable.

### 17.2. Controlled tolerant translation

May allow:

- Canonicalizing lexical amounts `"0025.000" → "25.00"`.
- Dropping a *legacy-UI-only* field once the business owner approves.
- Mapping a contracted enum alias.
- Keeping optional unknown fields in an extension bag when a newer schema permits.

Yet tolerant does not mean **ignoring arbitrary errors**. Require:

1. Explicit loss type/reason.
2. Owner sign-off for that category of loss.
3. Version scope and policy expiration.
4. Tests and observability.
5. Original preservation when replay or audit requires it.

### 17.3. Loss budgets

An organization might accept zero lost monetary events while tolerating certain optional display fields dropped during a batch migration. Still, "0.1% field loss allowed" rarely fits critical data: define policies **per field and business impact**, not as a flat percentage of messages.

### 17.4. Never silently "fix" bad data

If `amountMajorText="25.005"` cannot convert cleanly into integer cents, never round to `2501` and treat it as a clean translation unless a financial contract explicitly defines the rounding mode and accounting rules. If a status code is unrecognized, never map it to `NEW` just to get it into a handler.

## 18. When are round-trip tests valuable?

Write round-trip tests with explicit **data domains and equality relations**:

### 18.1. A→B→A for the compatible subset of A

~~~text
Source A with promotionCode=null,
statusCode in N/P/C,
amount in canonical lexical form,
supported currency

-> A' can equal A under record equality
~~~

For non-null promotion codes or leading-zero amounts, never expect exact equality.

### 18.2. B→A→B for the legacy-representable subset of B

~~~text
Source B state in NEW/PAID/CANCELLED
-> B' can equal B

Source B state=REFUNDED
-> Reverse Translator rejects; round-trip does not exist
~~~

### 18.3. Property-based testing beyond a few examples

Across broad samples of amounts and statuses, verify:

- `toMinorExact(toMajorCanonical(minor, currency), currency) == minor` for all valid minor units.
- A→B preserves `eventId`, `tenantId`, and `orderId`.
- Unexpected enums never map to another value.
- Loss lists emit reason codes when promotion cannot be represented.
- Retrying the same input yields identical output and loss lists (deterministic).
- Zero side effects inside the Translator.
- Signed/boundary numeric inputs never overflow silently.

You can use jqwik or QuickTheories for property tests if available, while **JUnit 5 parameterized tests** with boundary cases are also highly effective.
## 19. JSON/Avro round-trips differ from Java object round-trips

A `LegacyOrderV1` object may match after A→B→A, yet the raw JSON bytes of the original message still differ because serializers:

- Reorder fields.
- Omit null fields.
- Turn `"25.00"` into numeric `25` if parsed as a number.
- Apply snake_case/camelCase naming strategies.
- Alter charsets or Unicode normalization.
- Strip unknown fields.
- Drop comments and whitespace from source JSON.
- Convert large integers to floats in a JavaScript client.

### 19.1. Contract testing on wire representations

Suppose a legacy producer sends:

~~~json
{
  "eventId": "evt-order-1001",
  "tenantId": "tenant-a",
  "orderNo": "ORDER-101",
  "amountMajorText": "0025.000",
  "currency": "USD",
  "statusCode": "P",
  "legacyPromotionCode": null
}
~~~

If you parse → translate → reverse-translate → serialize via Jackson, the output might be:

~~~json
{
  "eventId": "evt-order-1001",
  "tenantId": "tenant-a",
  "orderNo": "ORDER-101",
  "amountMajorText": "25.00",
  "currency": "USD",
  "statusCode": "P",
  "legacyPromotionCode": null
}
~~~

Business amounts are equal, yet raw bytes differ. If the system verifies **signatures over the original body**, translation breaks byte equality. When audits require exact proof of the received request, store the **original signed bytes** under security/retention rules instead of relying on DTO reserialization.

### 19.2. Deserialization can lose data even before the Translator

An `ObjectMapper` configured to ignore unknown properties can discard `futureAttribute` while reading JSON into `LegacyOrderV1`, **before** `PartnerOrderTranslator` runs. The Translator's loss report never gets a chance to see it.

To detect unknown fields, configure strict decoders/schema validation, or parse into `JsonNode`/extension fields and inspect them before constructing typed DTOs. Never promise lossless end-to-end handling solely by reviewing Translator code if the **inbound codec** already threw data away.

### 19.3. Binary formats and registries

Avro and Protobuf have schema evolution rules, defaults, unknown-field behaviors, and encodings distinct from JSON. A registry version/schema ID picks the right codec and checks structural compatibility; it **does not prove** that business mappings from v1 to canonical v2 are fully invertible.

Tests should include fixtures exported **from real producers** across supported versions, including renamed/deprecated fields and new enum values.

## 20. What to do when recovering source data is mandatory?

When A has data that B cannot express, several strategies exist—none free of complexity, security, or retention trade-offs.

### 20.1. Extend the canonical schema

If `legacyPromotionCode` has durable business meaning, add a contracted field to B:

~~~text
CanonicalOrderV3
  ...
  legacyPromotionCode: optional
  provenance.sourceSchemaVersion: 1
~~~

Pros: data travels with the business record. Cons: downstream consumers may feel schema evolution impacts. Never dump every legacy field into the canonical DTO without reviewing domain ownership and privacy.

### 20.2. Namespaced extension bag

~~~json
{
  "orderId": "ORDER-101",
  "totalMinorUnits": 2500,
  "extensions": {
    "partner-a/v1/legacyPromotionCode": "SPRING-2026"
  }
}
~~~

Pros: keeps system-specific data isolated at the boundary. Cons:

- Key/value schemas are harder to govern.
- Easily abused to carry PII or secrets.
- Downstream may accidentally couple to unstable extensions.
- Requires ownership, versioning, and collision policies.
- Must not serialize extensions to unauthorized recipients.

### 20.3. Sidecar/provenance store

Store data lacking a home in B in dedicated storage:

~~~text
Business key:
  (tenantId, sourceId, eventId)

Canonical record:
  CanonicalOrderV2

Provenance/sidecar:
  originalLegacyPromotionCode
  originalAmountMajorText
  sourceSchemaVersion
  rawPayloadHash
  sourceReceivedAt
~~~

To reconstruct A, query the sidecar by a **trusted immutable key**. This is no longer a pure translation of B alone: it relies on an **auxiliary data store** with retention, consistency, authorization, backup, and recovery requirements.

If the sidecar writes before the business transaction and the business action fails, orphaned provenance remains; if written after and a crash occurs, the business record lacks provenance. When both live in the **same DB**, share a transaction if atomicity is required. Across two systems, design outbox/reconciliation/compensation policies.

### 20.4. Controlled raw original storage

When proving exact bytes/signatures of A is mandatory, keeping the original raw message beats reconstructing it. However, this carries security obligations:

- Encryption at rest and in transit.
- Per-tenant/per-source access controls.
- TTLs and legal retention schedules.
- Integrity checksums/signatures.
- Never log or forward raw credentials.
- Audit viewing, downloading, or restoring originals.
- Regulatory data deletion support.

### 20.5. Reject the translation

When required fields cannot be preserved, **rejecting with a clear reason code** is safer than accepting a distorted record. For instance, `REFUNDED` in B→A cannot map accurately: reject it or upgrade to a new partner contract version supporting refunds.

Never map `REFUNDED → CANCELLED` and claim "round-trip equivalence" without an explicit business contract approving the semantic merge.

## 21. Multiple schema versions: Translator or Normalizer?

A system might receive:

~~~text
LegacyOrder v1 ──┐
LegacyOrder v2 ──┼──> CanonicalOrder v3
PartnerOrder v4 ─┘
~~~

This is a **Normalizer EIP** converging multiple version-specific Translators onto one canonical representation. To reply to each partner in its own format, add reverse paths:

~~~text
CanonicalOrder v3
   ├─> Partner A v1
   ├─> Partner B v4
   └─> Internal API v3
~~~

**Never** assume having an A→B converter means B→A handles every state in B. Newer schema versions introduce fields and states unrepresentable in older targets. Maintain a dedicated support matrix and tests for each **source–target–version pair**.

### 21.1. Schema version and business revision are distinct concepts

- `sourceSchemaVersion`: picks parser/translator.
- `canonicalSchemaVersion`: defines output contract.
- `orderRevision`: tracks order state sequence.
- `eventId`: identifies logical event for deduplication.
- `correlationId`: groups business messages.
- `traceId`: tracks distributed flow execution.

Never use source schema version as a correlation key or business event sequence.

### 21.2. Expand → migrate → contract

Upgrade sequence:

1. Deploy consumers able to read both v1 and v2.
2. Test mappings in both directions.
3. Producers roll out v2 canaries.
4. Monitor lossy, unsupported, and error rates.
5. Stop emitting v1 once new payloads stabilize.
6. Retain the v1 converter for broker backlogs, DLQs, and historical replays.
7. Retire v1 only when retention windows and rollback plans permit.

Deleting the v1 reverse translator too early breaks partners that have not upgraded yet even after internal systems move to canonical v3.

### 21.3. Preventing loops when chaining both directions

Connecting A→B's output into B→A and routing B→A's output back to A creates an **infinite message loop**:

~~~mermaid
flowchart LR
    A["System A"] --> TAB["Translator A→B"]
    TAB --> B["System B"]
    B --> TBA["Translator B→A"]
    TBA --> A
~~~

Distinguish **direction/operation** and handle responses per the request contract. A message reverse-translated as a reply **is not** a fresh command to republish onto the same input topic. Idempotency alone does not replace breaking loops in topology.

## 22. Exceptions, discards, quarantine, and DLQs

A bidirectional system must separate **unrepresentable errors** from **policy-permitted loss**.

| Scenario | Result | Suggested policy |
|---|---|---|
| A maps cleanly into B | Outcome with zero flagged loss | Route to business channel |
| A has promo code unsupported in B | Outcome with loss | Quarantine or approved lossy path |
| Unknown legacy status `"H"` | Deterministic exception | Reject and notify producer |
| B state `REFUNDED` lacks legacy code | Deterministic exception | Never emit fake `CANCELLED` |
| Amount has fractional minor units | Deterministic exception | Reject or apply explicit rounding contract |
| Schema registry temporarily unavailable | Transient exception | Bounded retry/backoff |
| Partner API times out after send | Uncertain remote outcome | Reconcile/idempotency; never blind-retry |
| Oversized input JSON | Ingress security validation | Reject before parsing |
| Same event ID, different business payload | Integrity/idempotency conflict | Audit/quarantine; never skip silently |

### 22.1. Discard channel is not `errorChannel`

In `BidirectionalTranslatorConfiguration`:

- `orders.translation.quarantine` receives **`TranslationOutcome`** from the Filter when `lossless() == false`.
- If `PartnerOrderTranslator` throws an exception, `MessageFilter` never runs; the exception goes to the caller or error infrastructure.
- Spring Integration's `errorChannel` typically receives an `ErrorMessage` wrapping a `Throwable` published by an error handler or adapter.
- A broker DLQ is a separate transport mechanism—it does not appear automatically just because a bean is named "quarantine".

Therefore, quarantine consumers **must not cast** every payload to `ErrorMessage`. If every translation failure needs an investigation record, add a **dedicated error classification flow** turning typed exceptions into `RejectedTranslationRecord`.

### 22.2. `DirectChannel` and async error propagation

With synchronous `DirectChannel`, exceptions inside a Transformer propagate back to `send()` (and may be wrapped by the framework in `MessagingException`). With `ExecutorChannel`, pollers, or broker listeners, errors happen on worker threads; adapters/error handlers publish `ErrorMessage` to configured error channels.

Never assume synchronous exceptions automatically arrive on the global `errorChannel`. Test against your real topology and inbound adapters.

### 22.3. Poison messages must never retry infinitely

If an event arrives with `statusCode="H"` and the consumer does not support it, retrying 1,000 times with the same payload will never create a mapping. Classify it as a non-retryable contract error, route to quarantine/DLQ with a reason code, alert the owner, and reprocess only once an approved adapter/mapping version ships.

### 22.4. Loss is not a `Throwable`

**Report loss** without throwing when a policy filter should decide the route. Conversely, throw exceptions when a valid target cannot be built at all. Never catch all `RuntimeException`s and return `TranslationLoss("UNKNOWN")`—turning DB timeouts or code bugs into "optional field lost".

## 23. Retries, broker ACKs, and bidirectional idempotency

A pure Transformer performs no side effects and produces deterministic outputs for identical inputs, making it retry-friendly. Still, brokers and gateways can deliver the **same business event** downstream multiple times.

~~~text
Partner sends eventId=evt-order-1001
  -> Translate A→B
  -> Business DB commits
  -> Broker ACK lost
  -> Partner/Broker redelivers evt-order-1001
  -> Translate A→B again
  -> Idempotent Receiver must skip duplicate business effect
~~~

### 23.1. Use a stable business event ID

An idempotency key can be `(tenantId, sourceSystem, eventId, operationType)` per namespace. Never use Spring's `MessageHeaders.ID`, broker delivery tags, or retry timestamps: all can change across hops and retranslations.

### 23.2. Translation can change payload fingerprints

If deduplication hashes **raw JSON bytes**, an event in v1 and the same event republished in v2 produce different hashes despite identical business meaning. Compute fingerprints over **canonical business fields**, rules, and versions. If the same event ID carries a materially different amount, treat it as a **conflict**, never skip silently.

### 23.3. ACK only after outcomes are durable

An in-memory discard/quarantine `QueueChannel` does not survive restarts. When the contract forbids losing events, ACK only after the event is durably processed/persisted or durably rejected/quarantined under a trusted source policy. Test adapter-specific ACK/NACK and transactions thoroughly.

### 23.4. Remote side effects after the Translator

If outbound B→A calls a partner API that creates orders, a timeout **does not prove** the partner did not create the order. Retry with a stable idempotency key if supported, or query/reconcile. `TranslationOutcome` does not replace remote idempotency protocols.

## 24. Gateway request-reply and bidirectional translation

A request can enter under contract A and reply under contract A after business logic processes B:

~~~mermaid
flowchart LR
    REQ["Partner Request A"] --> AB["Translate A→B"]
    AB --> HANDLER["Canonical business handler"]
    HANDLER --> BA["Translate B→A response"]
    BA --> RESP["Partner Reply A"]
~~~

**Note:** requests and responses are often **two different message types**; do not reuse `LegacyOrderV1` for every response. Define `LegacyOrderResponseV1` and `CanonicalOrderResultV2` with dedicated mapping and round-trip invariants.

### 24.1. Do not equate reverse translation with replying

B→A may translate an **event** or **response** payload, yet it does not know which `replyChannel` to target. For Spring Integration Gateways, configure reply destinations, timeouts, and error mappings at the endpoint; across brokers/JVMs, never serialize a Java `replyChannel` object expecting the partner to use it.

### 24.2. What should be returned when data loss occurs?

Depending on the API contract, return:

- `422 Unprocessable Content` (or suitable status) if the request cannot be translated faithfully.
- A response listing accepted field losses if the API supports partial acceptance.
- An async `202 Accepted` + tracking ID when manual reconciliation is required.
- An error outcome with a stable reason code so the partner can correct the message.

These are **API design choices**, not rules imposed by Spring's Message Translator. Never silently drop requests and let the Gateway time out when callers need to know why their message was rejected.

### 24.3. Cache replies when idempotent requests are resent

If a partner retries an already-processed request, return the **stored business receipt/result** instead of rerunning the handler. Persist response references/receipts atomically in the idempotency record so B→A response mapping stays consistent.

## 25. Security, trust boundaries, and sensitive data

### 25.1. Mapping a tenant is not authorizing the tenant

`PartnerOrderTranslator` validates only `tenantId` syntax; it **does not authenticate** that the sender has rights to that tenant. HTTP/JMS/Kafka ingress must verify the tenant against authenticated principals/peer identities and ACLs before business handlers trigger side effects.

### 25.2. Loss reports can leak data

`TranslationOutcome.original` holds the entire source record in memory/quarantine. If it contains promotion codes, customer info, tokens, or addresses, serializing the whole outcome to logs or brokers leaks PII. Emit only reason codes to metrics, and store full sources solely in a **restricted, encrypted quarantine store** when truly needed.

### 25.3. Untrusted input strings must never pick arbitrary channel names

Never route directly by `source.legacyPromotionCode` or untrusted payload fields to select `MessageChannel`s or tenant queues. Version/type routing requires allowlists and explicit mappings. Enforce payload size limits, Unicode/numeric parser bounds, schema validation, and rate limits at ingress.

### 25.4. Payload signatures break after translation

A signature over A's JSON bytes no longer proves integrity of B after reserialization. For end-to-end cryptographic integrity:

1. Verify original A bytes/signature at the ingress boundary.
2. Translate per contract and record provenance/audit.
3. Re-sign B using an authorized key/identity if the target requires it.
4. Never copy the old signature as if it validated B's new bytes.

TLS protects transport hops only; it does not authorize client-claimed JSON contents or tenants.

## 26. Observability: knowing what was lost, where, and under which version

A bidirectional translation pipeline needs visibility into **total inputs, outputs, losses, invalids, quarantines, and retries**, not just exception counts.

| Metric | Purpose | Recommended labels |
|---|---|---|
| `translator_input_total` | Messages received | `direction`, `sourceVersion` |
| `translator_success_total` | Successfully translated per policy | `direction`, `targetVersion` |
| `translator_loss_detected_total` | Fields dropped/lost | `fieldName`, `reasonCode` |
| `translator_quarantined_total` | Blocked by loss policy | `direction`, `reason` |
| `translator_contract_error_total` | Deterministic mapping errors | `reasonCode` |
| `translator_infrastructure_error_total` | Registry/service errors | `dependency` |
| `translator_reverse_unsupported_total` | Target A cannot express B | `stateType` |
| `translator_round_trip_mismatch_total` | Broken semantic invariant | `contractVersion` |
| `translator_latency_seconds` | Translation latency | `direction`, `version` |
| `translator_replay_total` | Replayed events | `source`, `eventType` |
| `translator_downstream_duplicate_total` | Duplicate effects blocked | `flow` |
| `translator_source_version_share` | Source format mix | `source`, `version` |

### 26.1. Structured logs

~~~text
service=partner-bridge
flow=legacy-orders
direction=A_TO_B
sourceVersion=1
targetVersion=2
eventType=order.created
eventId=evt-order-1001
outcome=QUARANTINED_LOSSY
lossFields=[legacyPromotionCode]
reasonCode=FIELD_NOT_REPRESENTABLE_IN_CANONICAL
traceId=trace-1001
~~~

Log identifiers per security policy, hashing or redacting where needed; never log raw promotion codes or full payloads. Never use `eventId`, `orderId`, or `traceId` as high-cardinality metric labels. `lossFields` in logs can list **stable field names**, never business values.

### 26.2. Signs of mapping drift

- `AMOUNT_NOT_EXACT_OR_OVERFLOW` spikes after a partner changes units.
- `REFUNDED` reverse rejections surge after the canonical service deploys a new state.
- `legacyPromotionCode` losses jump after a marketing campaign.
- Canonical fingerprints diverge between v1 and v2 for the same event ID.
- Contract tests on JSON fixtures start failing after a serializer upgrade.
- Quarantine rates climb while broker deliveries stay steady.
- Broker ACKs succeed yet business outputs vanish because the loss branch drops messages.
- Gateway replies start timing out because a no-op/discard branch returns no response.

### 26.3. Risk-based alerting

Losing a display-only field during migration may warrant a warning. Losing business amounts, tenant identity, or `eventId` must **fail closed** and page/alert. Do not assign identical severity to every translation loss.

## 27. Translator performance and reliability

### 27.1. Pure mapping is the right default

`PartnerOrderTranslator` is a pure class: no DB, broker, or remote API calls. It is easy to unit test, safe to retry, and scales across instances. If external ID resolution or versioned currency rules are needed, isolate them behind a boundary with explicit caching and timeouts separate from pure mapping where possible.

### 27.2. Avoid duplicating huge payloads indefinitely inside outcomes

`TranslationOutcome<S, T>` retains both source and target. For large messages—especially with binary attachments—this increases heap and GC pressure. Production can store a **source reference / Claim Check** with checksums, ACLs, and retention instead of keeping two large copies in memory, trading off replayability once the reference expires.

### 27.3. Bounded queues and backpressure

If 20% of traffic is blocked by the loss policy and nothing drains the quarantine queue, memory grows unboundedly. Enforce bounded capacities, persistence, retry/backpressure, metrics, and retention. Never ACK and lose flagged messages inside an in-memory `QueueChannel`.

### 27.4. Ordering and correlation across both directions

If one order emits `CREATED → PAID → REFUNDED` across concurrent executor instances, outputs can reorder. `schemaVersion` is not a sequence number; when ordering matters, use business revisions/sequences, tenant/order partition keys, and Resequencers/Aggregators if contracted.

### 27.5. Two-way flows must not bounce infinitely between services

When both integrated systems emit changes, define **source-of-truth**, direction ownership, and loop prevention. A message translated A→B must not be treated by B as a brand-new mutation and echoed back to A without origin/version/idempotency guards.

## 28. Anti-patterns that cause data loss

| Mistake | Consequence | Fix |
|---|---|---|
| Assuming A→B and B→A means lossless round-trip | Cannot recover dropped source fields | Document valid domains; emit loss reports |
| Dropping legacy fields because "target doesn't use them" | Loses audit/promotion history | Explicit approval, extension, or sidecar |
| Fabricating default promo codes to satisfy schema | Invented business data | Null/optional or reject |
| Merging `REFUNDED` into `CANCELLED` | Wrong business state | Mark mapping unsupported |
| Using `double` for money | Precision drift | `BigDecimal`, exact minor units |
| Rounding outside contract rules | Financial discrepancies | Reject or use approved rounding |
| Treating `"25.00"` and `"0025.000"` as byte-identical | Breaks signatures/audits | Separate lexical and semantic checks |
| Dropping unknown JSON fields before Translator | Loss report misses them | Strict decoding or extension bags |
| Equating `null = absent = empty = zero` | Corrupts state meaning | Presence-aware schemas |
| Converting `List` to `Set` | Loses order and duplicates | Pick contract-preserving collections |
| Defaulting enums to `PAID`/`CANCELLED` | Swallows new states | Fail-fast and version routing |
| Changing `eventId` during translation | Replays double-process | Preserve logical event ID |
| Using amount/status as correlation key | Group drift | Stable business keys |
| Publishing full `TranslationOutcome` to broker | Data leaks, contract mismatch | Emit only approved translated DTO |
| Letting lossy B enter business handlers | Business acts on missing data | Explicit loss gate |
| Catching exceptions while ignoring loss results | Silent unlogged data loss | Audit loss outcomes |
| Treating discard as DLQ | No durable recovery | Explicit quarantine/broker DLQ policy |
| ACKing after queuing only in RAM | Crashes lose events | Durable storage + ACK policy |
| Copying all Spring headers to partner | Leaks tokens, stale contentType | Allowlists + transport mappers |
| Testing only Java object equality | Misses wire serializer drift | JSON/Avro fixture tests |
| Wiring two flows into a loop | Infinite messages and side effects | Direction ownership / loop guards |
| Assuming Transformer gives exactly-once | Retries re-run handlers | Idempotent Receiver + transactions |

## 29. Practice exercises, test matrix, and questions

### 29.1. Exercises

**Exercise 1 — Identify preservation levels.** For `"0025.000" USD` → `2500` minor units → `"25.00"`, explain byte, structural, and semantic equality.

**Exercise 2 — Prove non-invertibility.** Construct A1 and A2 differing only in promotion code while yielding identical canonical B; explain why the code cannot be recovered from B.

**Exercise 3 — Money exactness.** Test USD `"25.00"`, `"25.001"`, VND `"25000"`/`"25000.50"`, and `long` overflow.

**Exercise 4 — Enum evolution.** Add `REFUNDED` to B and verify B→A fails with a clear reason code.

**Exercise 5 — Forward translator.** Implement `toCanonical` and verify `eventId`, `tenantId`, `orderId`, and money preservation.

**Exercise 6 — Loss report.** Pass A with `legacyPromotionCode`; assert `TranslationOutcome.losses` is non-empty while `original` stays scoped internally.

**Exercise 7 — Reverse translator.** Build B in state `PAID` and verify amount/status map back to A; discuss why historical promotion codes cannot be recovered.

**Exercise 8 — Domain round-trip.** Verify A→B→A for A without promotion, canonical lexical amount, and status in N/P/C.

**Exercise 9 — Semantic round-trip.** Use `"0025.000"` as source and verify exact strings differ while monetary values remain equal.

**Exercise 10 — Spring Integration DSL.** Wire `BidirectionalTranslatorConfiguration`, routing valid items to accepted and lossy items to quarantine.

**Exercise 11 — Exception route.** Send `statusCode="H"` and amount `"25.001"`; verify typed exceptions are classified separately from loss lists.

**Exercise 12 — Gateway response.** Design replies when requests hit the loss policy, avoiding silent drops that hang callers.

**Exercise 13 — Preserve original.** Design a sidecar store for promotion codes and raw lexical amounts, specifying transactions, TTLs, and ACLs.

**Exercise 14 — JSON fixtures.** Serialize A→B→A with Jackson; compare wire JSON against business fields and test unknown-property behavior.

**Exercise 15 — Idempotency.** Send the same `eventId` across two Spring Message instances after redelivery; downstream performs the business write only once.

**Exercise 16 — Adapter headers.** Verify `Authorization` is stripped while trusted correlation/tracing metadata crosses transport.

**Exercise 17 — Schema migration.** Keep the v1 converter for archived events while producers emit v2; write regression tests.

**Exercise 18 — Collections.** Test `List → Set → List` with duplicates and ordering; design a loss report or preserve sequence metadata.

**Exercise 19 — Timezones.** Translate `OffsetDateTime → Instant → OffsetDateTime`; distinguish same instant from original offset.

**Exercise 20 — Monitoring.** Add metrics for field loss, unrepresentable reverse mappings, invalid money, quarantine, and version drift.

### 29.2. Minimum test matrix

| Input / scenario | Expected |
|---|---|
| A without promotion, standard USD amount | Valid B, empty loss list |
| A with promotion | Loss report; excluded from strict business channel |
| A amount not exact minor units | Contract error |
| A currency outside support matrix | Contract error |
| A unknown status | Contract error |
| B `REFUNDED` | Reverse not representable |
| A lexical amount with leading zeros | Semantic round-trip; bytes not equal |
| A blank `eventId` | Reject |
| A `tenantId` mismatches principal | Reject at auth boundary |
| B→A→B with shared states | Canonical semantic equality |
| A→B→A with non-null promo | Must not claim lossless |
| Input JSON with unknown fields | Handled per schema/decoder policy; never silently dropped |
| Original payload holds secrets | Never serialize full outcome onto broker |
| Broker redelivery | Stable event ID; idempotent side effects |
| Consumer lag / v1 DLQ | v1 converter still has replay plan |
| Quarantine store unavailable | Retry/ACK per durability policy |
| Error in async translator | `ErrorMessage`/error flow obeys policy |
| Lossy result from Filter | Discard payload is `TranslationOutcome`, not `ErrorMessage` |
| Two-way loop | Direction/echo guard present |
| New schema alters status/amount | Contract regression test before deploy |

### 29.3. Self-check questions

1. How does a Message Translator differ from a Serializer?
2. Does having functions A→B and B→A prove they are inverses?
3. How do byte, structural, and semantic equality differ?
4. When is A→B many-to-one?
5. Why can't losing a promotion code be fixed by writing a reverse mapper?
6. Why must `REFUNDED` never map to `CANCELLED`?
7. Why avoid `double` when converting major and minor units?
8. Does numeric equality imply lexical string equality?
9. How do null, absent, and empty differ?
10. At which step can unknown JSON fields get lost before reaching the Translator?
11. Why doesn't `TranslationOutcome.lossless()` prove a byte-level round-trip?
12. Why can't the reverse outcome know whether loss happened during the forward outcome?
13. Why preserve the original payload during quarantine?
14. When should you use an extension bag instead of a canonical field?
15. What dependencies does a sidecar store introduce for reverse translation?
16. Why must business event IDs stay unchanged across translators?
17. How does `schemaVersion` differ from business revision and `traceId`?
18. Why isn't a Spring discard channel automatically an `errorChannel`?
19. When is an exception non-retryable vs. transient?
20. What happens to a Gateway caller if the loss policy silently drops requests?
21. Why can duplicate broker deliveries still happen even when the Translator is deterministic?
22. When is it safe to remove a legacy translator?
23. How do you prevent an infinite A↔B loop when both sides emit events?
24. Which metrics detect data loss after a partner upgrade?
25. When must you test serialized wire bytes instead of just comparing Java records?

## 30. Checklist for designing a Bidirectional Translator

- [ ] Clearly defined domains A/B and source/target schema versions.
- [ ] Maintained a mapping ledger for every field and business invariant.
- [ ] Specified preservation level: byte, structural, semantic, or task-sufficient.
- [ ] Defined which value domains are guaranteed to round-trip.
- [ ] Explicitly identified fields that cannot be recovered.
- [ ] Every loss is reported with a reason code or rejected per contract.
- [ ] Never fabricate defaults for unknown business fields.
- [ ] New/unknown enums are rejected or mapped under approved policy.
- [ ] Money conversion uses `BigDecimal` / exact unit mapping with overflow checks.
- [ ] Null, absent, empty, and zero have clear semantics.
- [ ] Collection ordering and duplicates have explicit preservation contracts.
- [ ] Timestamps preserve the required instant, offset, or timezone.
- [ ] Never change `eventId`, tenant, or business identity when only changing representation.
- [ ] Authenticated tenant/source verified before business side effects.
- [ ] `TranslationOutcome.original` is never exposed publicly or published arbitrarily to brokers.
- [ ] Quarantine defines persistence, ACLs, encryption, TTL, and replay policies.
- [ ] Filter losses are never confused with `errorChannel` `Throwable`s.
- [ ] Deterministic invalid inputs are never retried infinitely.
- [ ] Transient dependency failures use bounded retries and backoff.
- [ ] Broker ACKs occur only after durable outcomes per contract.
- [ ] Downstream enforces an Idempotent Receiver and appropriate transactions.
- [ ] Gateway returns explicit responses/errors for loss policies.
- [ ] Header mapping uses allowlists, never copying tokens or runtime channel objects.
- [ ] Current `schemaVersion` and source provenance are attached accurately.
- [ ] A→B and B→A have separate tests; never assume automatic invertibility.
- [ ] Property/parameterized tests cover numeric boundaries and enum values.
- [ ] Round-trip tests verify explicit **semantic equality**.
- [ ] Serialized JSON/Avro fixtures test every supported version.
- [ ] Schema evolution and legacy retirement account for DLQs, backlogs, and replays.
- [ ] Owners approve field losses, semantic changes, and migration strategies.
- [ ] Metrics separate success, loss, unrepresentable mappings, invalids, and replays.
- [ ] Never use event IDs, order IDs, or trace IDs as high-cardinality metric labels.
- [ ] Two-way flows enforce direction ownership and loop prevention.
- [ ] Never treat payload translation as completed business processing.

## 31. Summary

**Bidirectional Translators and Risk of Data Loss** highlights that implementing **A→B and B→A** provides *interoperability* between two contracts—it **does not automatically create an inverse pair of functions**. When a field in A lacks a home in B, or multiple A states collapse into one B state, source information is lost irreversibly. When amounts convert from decimal strings to minor units, numeric value survives while lexical form disappears; when new enums outgrow legacy capabilities, reverse translation must yield an **unsupported outcome** instead of forcing a wrong mapping.

In Spring Integration, use **Transformer** to execute mappings, **Filter** to gate `TranslationOutcome`s with disallowed losses, Router/Normalizer to pick schema/version adapters, Gateway to uphold request-reply contracts, and error channels/quarantine for failures. A safe Translator demands **typed reasons, explicit loss policies, exact money/enum conversions, stable event identity, header security, and bidirectional testing**. When exact round-trips are mandatory, retain source data in canonical extensions, sidecars, or protected original records with proper access controls and retention—never fabricate lost data.

For **SPRING_INTEGRATION_PATTERN**, the objective is integrating systems that are **loosely coupled and extensible** while staying faithful to message semantics: able to reject rather than accept corrupt data, report losses explicitly instead of silently dropping fields, replay safely without duplicate side effects, and evolve schemas backed by reliable tests, audits, and observability.

### References

- Enterprise Integration Patterns — Message Translator: https://www.enterpriseintegrationpatterns.com/patterns/messaging/MessageTranslator.html
- Enterprise Integration Patterns — Normalizer: https://www.enterpriseintegrationpatterns.com/patterns/messaging/Normalizer.html
- Enterprise Integration Patterns — Envelope Wrapper: https://www.enterpriseintegrationpatterns.com/patterns/messaging/EnvelopeWrapper.html
- Enterprise Integration Patterns — Idempotent Receiver: https://www.enterpriseintegrationpatterns.com/patterns/messaging/IdempotentReceiver.html
- Spring Integration Reference — Transformer: https://docs.spring.io/spring-integration/reference/transformer.html
- Spring Integration Reference — Message Routing: https://docs.spring.io/spring-integration/reference/router.html
- Spring Integration Reference — Filter: https://docs.spring.io/spring-integration/reference/filter.html
- Spring Integration Reference — Java DSL: https://docs.spring.io/spring-integration/reference/dsl.html
- Spring Integration Reference — Message: https://docs.spring.io/spring-integration/reference/message.html
- Spring Integration Reference — Error Handling: https://docs.spring.io/spring-integration/reference/error-handling.html
- Spring Integration Reference — Gateway: https://docs.spring.io/spring-integration/reference/gateway.html
- Spring Integration Reference — Aggregator: https://docs.spring.io/spring-integration/reference/aggregator.html
- Spring Integration Reference — Claim Check: https://docs.spring.io/spring-integration/reference/claim-check.html
- Java SE 17 API — BigDecimal: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html
- Java SE 17 API — Currency: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Currency.html
- JUnit 5 User Guide: https://junit.org/junit5/docs/current/user-guide/
