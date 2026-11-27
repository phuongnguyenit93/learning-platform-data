# Normalizer: Converting Multiple Formats into a Common Representation

## 1. The Problem: Three Partners Sending the Same Information in Three Different Ways

In the **Normalizer** chapter of the **SPRING_INTEGRATION_PATTERN** module, we learn to implement Enterprise Integration Patterns with **Spring Integration** to build loosely coupled, extensible message flows. When connecting Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation, an important question arises right from the start: **if sources send data with the same meaning but different structures, must all downstream processing understand every single one of those structures?**

Suppose the system receives paid order information from three sources:

- The **ERP** system sends legacy JSON using fields `orderNo`, `grossAmountVnd`, `submittedAtIso`, and status `PAID`.
- **Marketplace** sends newer JSON using `purchaseRef`, `amountMinor`, `currencyCode`, epoch milliseconds timestamp, and status `SETTLED`.
- A partner sends **CSV** with columns `order_key`, `amount_decimal`, `currency`, `occurred_at`, and status `PAYMENT_COMPLETE`.

The three payloads carry the same business message: “order X paid amount Y at time Z”. Yet if the Handler, Aggregator, and reporting all need to know all three schemas, adding a new partner requires modifying dozens of places.

~~~mermaid
flowchart LR
    A["ERP JSON v1"] --> R["Message Router"]
    B["Marketplace JSON v2"] --> R
    C["CSV upload"] --> R
    R --> T1["ERP Translator"]
    R --> T2["Marketplace Translator"]
    R --> T3["CSV Translator"]
    T1 --> N["CanonicalOrder"]
    T2 --> N
    T3 --> N
    N --> V["Validate common contract"]
    V --> F["Router / Aggregator / business flow"]
~~~

**Normalizer** is a pattern that routes all sources through dedicated transformations and converges them into **a unified internal structure**. It does more than rename fields: the interpretation of currency, timezones, statuses, identifiers, and data trustworthiness must follow a common contract.

### Learning Objectives

After this lesson, you will be able to:

1. Explain Normalizer according to EIP and distinguish it from a single Transformer.
2. Distinguish **parse/decode**, **normalize to a common schema**, **validate**, and **enrich**.
3. Define a **canonical model** with clear types, units, and semantics.
4. Use a Router to select a Transformer by source or payload type instead of spreading an `if/else` block across the system.
5. Build a Java 17 + Spring Integration Java DSL example for ERP, marketplace, and CSV.
6. Protect tenant/source identity, business correlation, eventId, and trace metadata as messages pass through the normalizer.
7. Handle malformed data, unknown schemas, duplicates, retries, DLQ, and quarantine without losing events.
8. Write unit tests and integration tests to prove three formats produce a common output contract.

## 2. Normalizer Definition in Enterprise Integration Patterns

According to [Enterprise Integration Patterns — Normalizer](https://www.enterpriseintegrationpatterns.com/patterns/messaging/Normalizer.html), if multiple sources send messages that are **semantically equivalent** but have **different formats**, we can:

1. Use a **Message Router** to identify the message type.
2. Route each type to the appropriate **Message Translator**.
3. Require every Translator to produce **the same common format**.
4. Send the normalized messages into a single unified processing flow.

~~~text
Source A format ──> Translator A ──┐
Source B format ──> Translator B ──┤──> Canonical format
Source C format ──> Translator C ──┘
             ↑
      Message Router selects branch
~~~

Spring Integration provides **Router**, **Transformer**, **Channel**, **Service Activator**, **Filter**, and the DSL to implement this pattern. **Do not assume there is a dedicated endpoint named `Normalizer`** where the framework automatically converts all formats. This is **a pattern composition**, not a promise that the framework automatically understands partner data semantics.

### 2.1. How Does Normalizer Differ from Transformer?

| Component | Role | Example |
| --- | --- | --- |
| **Parser / MessageConverter** | Turns bytes or JSON/XML/CSV into a readable structure | `byte[]` → `ErpOrderV1` |
| **Router** | Selects the right processing branch for the type | `VerifiedErpOrder` → `erpOrders` |
| **Transformer** | Converts one input type to one output type | `ErpOrderV1` → `CanonicalOrder` |
| **Normalizer** | Coordinates a router and multiple translators for one contract | ERP, marketplace, CSV → `CanonicalOrder` |
| **Filter** | Blocks/drops messages based on criteria | Rejects unauthorized or invalid events |
| **Aggregator** | Combines multiple related messages into one result | Three `CanonicalOrder` outcomes → one report |
| **Enricher** | Adds information from another source | Maps external customer ID → trusted internal ID |

A Transformer may be the entire solution if there is only one input format. When multiple equivalent formats must enter the **same downstream contract**, the Normalizer layout becomes useful.

### 2.2. Normalization Does Not Turn Every Source into the Same Values

Three sources can produce the same `CanonicalOrder` **type** with different data: tenant, sourceEventId, externalOrderId, currency, and event time still retain the true values of each source. **Same representation** means unified fields, types, units, semantics, and validation; not forcing every order into one order code or one currency.

For example:

| Source | Amount Input | Canonical Output |
| --- | --- | --- |
| ERP | `"150000"` VND | `Money(150000, VND)` |
| Marketplace | `1235` minor units USD | `Money(12.35, USD)` |
| CSV | `"89.90"` USD | `Money(89.90, USD)` |

If there are two orders in USD and VND, the Normalizer must not blindly add raw amounts as if they shared the same unit. Currency conversion (FX) is an independent business rule requiring explicit rate, rate source, timestamp, and rounding rules.

## 3. Processing Chain from Wire Bytes to Canonical Event

Different adapters may carry HTTP JSON, JMS byte payloads, AMQP messages, CSV files, or XML. A pipeline should separate boundaries:

~~~mermaid
flowchart TD
    W["Wire bytes / payload"] --> P["Parse + schema selection"]
    P --> S["Authenticate & verify source"]
    S --> R["Route by verified source/type"]
    R --> T["Format-specific Transformer"]
    T --> C["CanonicalOrder"]
    C --> V["Common validation"]
    V --> D["Business downstream"]
    P -.-> E["Malformed → quarantine"]
    S -.-> E
    R -.-> E
    T -.-> E
    V -.-> E
~~~

**Responsibility layers:**

- **Adapter/Parser:** decodes protocol, charset, JSON/XML/CSV schema, and size limits. Does not decide business status such as whether payment succeeded.
- **Trust boundary:** verifies source/tenant, event emission permissions, and the schemas that the source is allowed to emit.
- **Router:** selects the right translator; avoids guessing from untrusted fields when verified identity is available.
- **Translator:** performs field mapping, type conversion, timezone normalization, money units, and enum/status mapping.
- **Canonical validator:** enforces invariants that apply to **all sources**, not only ERP.
- **Downstream:** processes a unified CanonicalOrder type without `if (source == ERP) ...` unless it is an intentional business rule.

### 3.1. Why Parse Before Routing?

When inputs are already typed Java DTOs, **PayloadTypeRouter** easily selects a branch. But if every adapter puts a JSON `String` onto a shared channel, routing by `payload.getClass()` only sees `String` and cannot tell ERP from marketplace.

There are three safe options:

1. **Dedicated adapters** decode each schema into a typed DTO and then route by payload class.
2. **An envelope with `sourceSystem/schemaVersion`** verified at ingress, then route by trusted metadata.
3. **Content-based routing** after a safe schema-identification step with versioned contracts and strict validation.

Do not merely search for a substring like `"orderNo"` in raw JSON to guess the schema. The field could appear in a nested object, be escaped, or be intentionally injected by another producer. Use a parser/schema registry and an authenticated source.

### 3.2. Why Not Parse CSV with `split(",")`?

CSV allows quoted fields, commas inside values, embedded newlines, and escaping. `String.split(",")` is an unsafe anti-pattern for general CSV.

In real systems, use a parser library that supports CSV dialects, encoding, BOM, and size limits, then map each row into a DTO. The examples in this lesson use **DTOs already produced by a parser**, rather than pretending Java `split` is a valid parser for all CSVs.

## 4. Designing the Canonical Model Before Writing Translators

The canonical model is the **contract between the integration layer and the business layer**. It must be clear enough for all downstream consumers to understand once.

| Attribute | Meaning | Invariant |
| --- | --- | --- |
| `tenantId` | Verified tenant | Non-empty, not from an arbitrary HTTP header |
| `sourceSystem` | Verified event-emitting system | Allowlisted value |
| `sourceEventId` | Logical event ID for deduplication | Stable across redeliveries |
| `externalOrderId` | Order ID per source contract | Namespaced by source/tenant if needed |
| `status` | Common typed status | Valid mappings only; never default unknown to “success” |
| `Money` | Amount and currency | Non-negative, precision matches currency |
| `occurredAt` | Event timestamp | UTC `Instant` parsed with proper zone |
| `schemaVersion` | Canonical contract version | Enables controlled schema evolution |

Several design choices:

- Use **immutable records** and `BigDecimal` for money; never `double`.
- Use **`Instant`** for absolute points in time; if a source sends local time, a **specific `ZoneId`** is required.
- Preserve **sourceEventId** and **sourceSystem** for tracing and deduplication.
- Do not discard raw events before storing/quarantining them according to retention and privacy requirements.
- Do not stuff the entire raw JSON/XML into the canonical record just to avoid writing a mapper; raw payloads belong in controlled storage if actually needed.
- Only bump schemaVersion when the contract clearly changes; avoid tying schema version to application build numbers.

### 4.1. Common Schema and Compatibility

A new field such as `taxIncluded` or `pricingBasis` may be **optional** for historical data yet required for new business logic. Rules are needed:

- Which fields are required, which are nullable/optional, and which have valid defaults?
- If a source lacks data, return an explicit **UNKNOWN** or reject?
- When changing units, are both stored events and consumers migrated?
- When an enum gets a new value, does the mapper fail closed or pick a fallback?

A “canonical schema” is only useful if all producers/translators and downstream consumers **agree on semantics**, not just field names.

## 5. Input Examples from Three Sources

In this chapter, adapters have already parsed JSON/CSV and verified the source, producing **typed input records**. So the lesson can be tested without an external broker, we simulate the exact point **right after the inbound parser and trust validation**.

### 5.1. ERP JSON v1

~~~json
{
  "eventId": "evt-erp-101",
  "orderNo": "ERP-101",
  "grossAmountVnd": "150000",
  "submittedAtIso": "2026-11-01T08:30:00Z",
  "paymentState": "PAID"
}
~~~

### 5.2. Marketplace JSON v2

~~~json
{
  "evt": "evt-market-202",
  "purchaseRef": "MK-202",
  "amountMinor": 1235,
  "currencyCode": "USD",
  "eventTimeEpochMillis": 1793521800000,
  "state": "SETTLED"
}
~~~

`amountMinor=1235` with USD (two decimal places) is **12.35 USD**, not 1.235 USD or 1235 USD. For VND, the number of decimal digits according to `Currency` is 0. Do not hard-code every currency to two decimal places.

### 5.3. CSV

~~~csv
event_id,order_key,amount_decimal,currency,occurred_at,state
evt-csv-303,CSV-303,89.90,USD,2026-11-01T08:30:00Z,PAYMENT_COMPLETE
~~~

This is a CSV dialect where `occurred_at` is in ISO-8601 UTC format and `amount_decimal` uses a dot. If real files use `1.234,50` or `dd/MM/yyyy HH:mm`, a **separate** parser/locale/timezone configuration is required; never apply one blanket comma-replacement across all partners.

## 6. Java 17: Three Verified Input Types and One Common Output

Instead of letting the Translator trust self-reported sourceId/tenantId fields inside JSON, the ingress layer creates a **TrustedSource** from a verified principal, certificate, broker ACL, or adapter configuration.

### 6.1. Trusted Source and Raw DTOs

~~~java
enum SourceSystem {
    ERP,
    MARKETPLACE,
    CSV_UPLOAD
}

record TrustedSource(
        String tenantId,
        String partnerId,
        SourceSystem system) {

    TrustedSource {
        if (tenantId == null
                || !tenantId.matches("[a-z0-9_-]{1,48}")
                || partnerId == null
                || !partnerId.matches("[A-Za-z0-9_-]{1,64}")
                || system == null) {
            throw new IllegalArgumentException("INVALID_TRUSTED_SOURCE");
        }
    }
}

record ErpOrderV1(
        String eventId,
        String orderNo,
        String grossAmountVnd,
        String submittedAtIso,
        String paymentState) {
}

record MarketplaceOrderV2(
        String evt,
        String purchaseRef,
        long amountMinor,
        String currencyCode,
        long eventTimeEpochMillis,
        String state) {
}

record CsvOrderRow(
        String eventId,
        String orderKey,
        String amountDecimal,
        String currencyCode,
        String occurredAtIso,
        String state) {
}
~~~

**The name `TrustedSource` does not create trust on its own.** Only code at the trust boundary is permitted to construct that record after authentication/authorization and partner mapping succeed. The unit test examples construct the record directly to isolate the normalizer, **not to verify the security of an HTTP/JMS adapter**.

Do not use a “universal raw order” record with 20 nullable fields and force downstream code to guess which fields are meaningful. **Each source schema has its own type** so version/mapping errors surface at the corresponding translator.

### 6.2. Verified Wrappers So the Router Sees Payload Type

~~~java
sealed interface VerifiedIncomingOrder
        permits VerifiedErpOrder,
                VerifiedMarketplaceOrder,
                VerifiedCsvOrder {
    TrustedSource source();
}

record VerifiedErpOrder(
        TrustedSource source,
        ErpOrderV1 body) implements VerifiedIncomingOrder {
}

record VerifiedMarketplaceOrder(
        TrustedSource source,
        MarketplaceOrderV2 body) implements VerifiedIncomingOrder {
}

record VerifiedCsvOrder(
        TrustedSource source,
        CsvOrderRow body) implements VerifiedIncomingOrder {
}
~~~

For example, `VerifiedErpOrder` is constructed only after the adapter verifies that the message originated from the ERP system; input JSON **cannot choose** `source.system()` without passing the trust boundary.

### 6.3. Canonical Types

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Instant;
import java.util.Currency;
import java.util.Objects;

enum CanonicalOrderStatus {
    PAID,
    CANCELLED,
    PENDING
}

record Money(BigDecimal amount, Currency currency) {
    Money {
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(currency, "currency");

        int digits = currency.getDefaultFractionDigits();
        if (digits < 0) {
            throw new IllegalArgumentException(
                    "UNSUPPORTED_CURRENCY_FRACTION_DIGITS");
        }

        // Do not silently round data with the wrong precision.
        amount = amount.setScale(digits, RoundingMode.UNNECESSARY);
        if (amount.signum() < 0) {
            throw new IllegalArgumentException("NEGATIVE_ORDER_AMOUNT");
        }
    }
}

record CanonicalOrder(
        int canonicalSchemaVersion,
        String tenantId,
        String partnerId,
        SourceSystem sourceSystem,
        String sourceEventId,
        String externalOrderId,
        CanonicalOrderStatus status,
        Money total,
        Instant occurredAt) {

    CanonicalOrder {
        if (canonicalSchemaVersion != 1
                || tenantId == null
                || partnerId == null
                || sourceSystem == null
                || sourceEventId == null
                || sourceEventId.isBlank()
                || externalOrderId == null
                || externalOrderId.isBlank()
                || status == null
                || total == null
                || occurredAt == null) {
            throw new IllegalArgumentException(
                    "INVALID_CANONICAL_ORDER");
        }
    }
}
~~~

**What `Money` solves:** there is only one representation of monetary amounts in the system; decimal places are enforced according to `Currency`. For example, `new Money(new BigDecimal("89.999"), USD)` is rejected rather than rounded to 90.00. If the domain needs precision beyond standard currency units (such as exchange rates or weight-based unit prices), define a separate **Rate/UnitPrice** type instead of loosely relaxing Money.

**What `CanonicalOrder` solves:** downstream sees an enum `status`, a `Money`, an `Instant`, and clear identity fields. It does not need to know whether ERP stores amounts as strings, marketplace sends minor units, or CSV uses ISO timestamps.

## 7. Source-Schema Translators: One Responsibility per Branch

The following functions accept verified typed input and return a **non-null** `CanonicalOrder`. In Spring Integration, a Transformer is not a Filter: a transformation cannot simply return null to mean “skip event”.

### 7.1. Shared Validation Helpers for Translators

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.Currency;

final class PurchaseOrderNormalizer {

    private static String requiredId(
            String value,
            String field) {
        if (value == null
                || !value.matches("[A-Za-z0-9_-]{1,96}")) {
            throw new IllegalArgumentException(
                    "INVALID_" + field);
        }
        return value;
    }

    private static Currency supportedCurrency(String code) {
        if (code == null || !java.util.Set.of(
                "VND", "USD").contains(code)) {
            throw new IllegalArgumentException(
                    "UNSUPPORTED_CURRENCY");
        }
        return Currency.getInstance(code);
    }

    private static BigDecimal decimal(String text) {
        if (text == null || text.isBlank()) {
            throw new IllegalArgumentException("MISSING_AMOUNT");
        }
        try {
            return new BigDecimal(text);
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException(
                    "INVALID_AMOUNT_FORMAT", ex);
        }
    }

    private static Instant isoInstant(String text) {
        if (text == null || text.isBlank()) {
            throw new IllegalArgumentException("MISSING_EVENT_TIME");
        }
        try {
            return Instant.parse(text);
        } catch (java.time.format.DateTimeParseException ex) {
            throw new IllegalArgumentException(
                    "INVALID_EVENT_TIME", ex);
        }
    }

    private static void requireSource(
            TrustedSource source,
            SourceSystem expected) {
        if (source == null || source.system() != expected) {
            throw new SecurityException("SOURCE_SCHEMA_MISMATCH");
        }
    }

    private static CanonicalOrder canonical(
            TrustedSource source,
            String eventId,
            String orderId,
            Money total,
            Instant occurredAt,
            CanonicalOrderStatus status) {

        return new CanonicalOrder(
                1,
                source.tenantId(),
                source.partnerId(),
                source.system(),
                requiredId(eventId, "EVENT_ID"),
                requiredId(orderId, "ORDER_ID"),
                status,
                total,
                occurredAt);
    }

    // Three format-specific methods are added below.
}
~~~

**Note:** the code snippets in this lesson are split across multiple blocks for explanation. The next three methods belong to the **same `PurchaseOrderNormalizer` class** above; when placing them in a real source file, put them inside the class body before the closing `}`, without declaring duplicate classes.

### 7.2. ERP: Parsing VND Amounts and ISO Timestamps

~~~java
// Method inside PurchaseOrderNormalizer.
CanonicalOrder fromErp(VerifiedErpOrder input) {
    requireSource(input.source(), SourceSystem.ERP);
    ErpOrderV1 raw = java.util.Objects.requireNonNull(
            input.body(), "erp body");

    CanonicalOrderStatus status = switch (raw.paymentState()) {
        case "PAID"      -> CanonicalOrderStatus.PAID;
        case "CANCELLED" -> CanonicalOrderStatus.CANCELLED;
        case "PENDING"   -> CanonicalOrderStatus.PENDING;
        default -> throw new IllegalArgumentException(
                "UNKNOWN_ERP_PAYMENT_STATE");
    };

    return canonical(
            input.source(),
            raw.eventId(),
            raw.orderNo(),
            new Money(
                    decimal(raw.grossAmountVnd()),
                    supportedCurrency("VND")),
            isoInstant(raw.submittedAtIso()),
            status);
}
~~~

Values like `"150000"` can be parsed directly; `"150,000"` must be rejected if **the ERP contract specifies a decimal string without separators**. Never strip commas without knowing whether the comma is a thousands separator or a decimal point.

### 7.3. Marketplace: Converting Minor Units to Decimal

~~~java
// Method inside PurchaseOrderNormalizer.
CanonicalOrder fromMarketplace(VerifiedMarketplaceOrder input) {
    requireSource(input.source(), SourceSystem.MARKETPLACE);
    MarketplaceOrderV2 raw = java.util.Objects.requireNonNull(
            input.body(), "marketplace body");

    Currency currency = supportedCurrency(raw.currencyCode());
    int digits = currency.getDefaultFractionDigits();

    CanonicalOrderStatus status = switch (raw.state()) {
        case "SETTLED"  -> CanonicalOrderStatus.PAID;
        case "CANCELED" -> CanonicalOrderStatus.CANCELLED;
        case "PENDING"  -> CanonicalOrderStatus.PENDING;
        default -> throw new IllegalArgumentException(
                "UNKNOWN_MARKETPLACE_STATE");
    };

    return canonical(
            input.source(),
            raw.evt(),
            raw.purchaseRef(),
            new Money(
                    BigDecimal.valueOf(raw.amountMinor(), digits),
                    currency),
            Instant.ofEpochMilli(raw.eventTimeEpochMillis()),
            status);
}
~~~

For USD, `BigDecimal.valueOf(1235L, 2)` creates 12.35. For VND, `BigDecimal.valueOf(150000L, 0)` creates 150000. This is an exact unit conversion because `minorUnits` by contract is an **integer**; it is not an exchange rate and needs no `double`.

### 7.4. CSV: Parsing Decimal According to the Declared Dialect

~~~java
// Method inside PurchaseOrderNormalizer.
CanonicalOrder fromCsv(VerifiedCsvOrder input) {
    requireSource(input.source(), SourceSystem.CSV_UPLOAD);
    CsvOrderRow raw = java.util.Objects.requireNonNull(
            input.body(), "csv row");

    CanonicalOrderStatus status = switch (raw.state()) {
        case "PAYMENT_COMPLETE" -> CanonicalOrderStatus.PAID;
        case "ORDER_CANCELLED"  -> CanonicalOrderStatus.CANCELLED;
        case "AWAITING_PAYMENT" -> CanonicalOrderStatus.PENDING;
        default -> throw new IllegalArgumentException(
                "UNKNOWN_CSV_STATE");
    };

    return canonical(
            input.source(),
            raw.eventId(),
            raw.orderKey(),
            new Money(
                    decimal(raw.amountDecimal()),
                    supportedCurrency(raw.currencyCode())),
            isoInstant(raw.occurredAtIso()),
            status);
}
~~~

If CSV `amount_decimal` contains an empty string or `"NaN"`, parsing must reject it. Never convert an invalid amount into 0, because that turns a **data error** into a **zero-value transaction**.

### 7.5. Unifying Without Erasing Source Provenance

The outputs of all three translators have type `CanonicalOrder` yet still contain:

~~~text
tenantId
partnerId
sourceSystem
sourceEventId
externalOrderId
status
total
occurredAt
canonicalSchemaVersion
~~~

This information is essential for deduplication, reconciliation, and business routing after the normalizer. **Do not strip source identity** just because “downstream doesn’t need to care about formats”; not caring about **source structure** is different from losing **data provenance**.

## 8. Java DSL: Payload-Type Router, Three Translators, One Canonical Channel

Spring Integration provides **PayloadTypeRouter** or Java DSL routing by payload class. Once adapters have verified and wrapped payloads with `VerifiedErpOrder`, `VerifiedMarketplaceOrder`, or `VerifiedCsvOrder`, the Router can choose the branch without parsing raw JSON a second time.

~~~mermaid
flowchart TD
    I["verifiedIncomingOrders"] --> R{"Payload type Router"}
    R -->|"VerifiedErpOrder"| E["erpOrders"]
    R -->|"VerifiedMarketplaceOrder"| M["marketplaceOrders"]
    R -->|"VerifiedCsvOrder"| C["csvOrders"]
    R -->|"Unknown type"| Q["unknownFormatOrders"]
    E --> TE["fromErp"]
    M --> TM["fromMarketplace"]
    C --> TC["fromCsv"]
    TE --> N["canonicalOrders"]
    TM --> N
    TC --> N
    N --> V["CommonOrderPolicy"]
    V --> O["canonicalOutput"]
~~~

### 8.1. Common Policy After Normalization

~~~java
final class CommonOrderPolicy {

    CanonicalOrder requireValid(CanonicalOrder order) {
        if (order == null || order.canonicalSchemaVersion() != 1) {
            throw new IllegalArgumentException(
                    "INVALID_CANONICAL_SCHEMA");
        }

        // This is an example-specific policy:
        // PAID requires a positive amount.
        if (order.status() == CanonicalOrderStatus.PAID
                && order.total().amount().signum() <= 0) {
            throw new IllegalArgumentException(
                    "PAID_ORDER_REQUIRES_POSITIVE_AMOUNT");
        }

        return order;
    }
}
~~~

**Business note:** some systems allow free orders with a price of 0. The policy above only illustrates placing a **shared invariant** in one place. If free orders are valid, model/classify them explicitly rather than assuming every paid event with amount=0 is an error.

### 8.2. Configuring Channels and Router

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
class NormalizerFlowConfig {

    @Bean
    PurchaseOrderNormalizer purchaseOrderNormalizer() {
        return new PurchaseOrderNormalizer();
    }

    @Bean
    CommonOrderPolicy commonOrderPolicy() {
        return new CommonOrderPolicy();
    }

    @Bean
    MessageChannel verifiedIncomingOrders() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel erpOrders() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel marketplaceOrders() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel csvOrders() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel canonicalOrders() {
        return new DirectChannel();
    }

    @Bean
    QueueChannel canonicalOutput() {
        return new QueueChannel();
    }

    @Bean
    QueueChannel unknownFormatOrders() {
        return new QueueChannel();
    }

    @Bean
    IntegrationFlow verifiedOrdersRouter() {
        return IntegrationFlow.from("verifiedIncomingOrders")
                .<Object, Class<?>>route(Object::getClass, router -> router
                        .channelMapping(
                                VerifiedErpOrder.class, "erpOrders")
                        .channelMapping(
                                VerifiedMarketplaceOrder.class,
                                "marketplaceOrders")
                        .channelMapping(
                                VerifiedCsvOrder.class, "csvOrders")
                        .defaultOutputChannel("unknownFormatOrders"))
                .get();
    }

    @Bean
    IntegrationFlow erpNormalization(
            PurchaseOrderNormalizer normalizer) {
        return IntegrationFlow.from("erpOrders")
                .transform(
                        VerifiedErpOrder.class,
                        normalizer::fromErp)
                .channel("canonicalOrders")
                .get();
    }

    @Bean
    IntegrationFlow marketplaceNormalization(
            PurchaseOrderNormalizer normalizer) {
        return IntegrationFlow.from("marketplaceOrders")
                .transform(
                        VerifiedMarketplaceOrder.class,
                        normalizer::fromMarketplace)
                .channel("canonicalOrders")
                .get();
    }

    @Bean
    IntegrationFlow csvNormalization(
            PurchaseOrderNormalizer normalizer) {
        return IntegrationFlow.from("csvOrders")
                .transform(
                        VerifiedCsvOrder.class,
                        normalizer::fromCsv)
                .channel("canonicalOrders")
                .get();
    }

    @Bean
    IntegrationFlow commonCanonicalValidation(
            CommonOrderPolicy policy) {
        return IntegrationFlow.from("canonicalOrders")
                .transform(
                        CanonicalOrder.class,
                        policy::requireValid)
                .channel("canonicalOutput")
                .get();
    }
}
~~~

This Java DSL configuration targets modern Spring Integration versions (6.x/7.x). The DTOs and Translator from earlier sections must be placed in an importable module/package. **No real Kafka/HTTP adapter is included here**: `verifiedIncomingOrders` represents the boundary **after** source verification and schema parsing.

### 8.3. Why Multiple IntegrationFlows Instead of One Long Flow?

The Router splits messages into three dedicated channels. Each sub-flow owns exactly one Translator. Once `CanonicalOrder` is produced, the branches converge on `canonicalOrders` and run **the same `CommonOrderPolicy`**.

As a result:

- Changing the ERP structure does not require editing the Marketplace translator.
- Adding a new XML source primarily adds **parser + verified DTO + route mapping + translator**.
- Downstream business code does not need `switch(sourceSystem)` to interpret basic fields.
- Latency and error rates can be measured per translator.
- A misbehaving source can be isolated without forcing other sources to change schemas.

### 8.4. When to Choose a Single Transformer?

If there are only two very simple structures, a single Transformer with a `switch` over a sealed input type may suffice. The Normalizer pattern emphasizes **separation of concerns**, not mandating a separate JVM class or channel for every input type in every situation.

Choose the multi-sub-flow layout when each source has its own parsing/validation/rate-limit/error policy, or when a large number of partners makes an all-in-one Transformer hard to maintain.

## 9. Unsupported Type vs. Malformed Known Type

Two failure modes look similar if you only observe “no canonical output appeared”, yet they must be distinguished:

| Category | Example | Where Detected | Policy |
| --- | --- | --- | --- |
| **Unknown type** | A `String` or new DTO with no route | Router defaultOutputChannel | Quarantine/unsupported-format metric |
| **Wrong source wrapper** | ERP payload with TrustedSource=MARKETPLACE | Translator source check | Block and report trust violation |
| **Malformed value** | ERP `grossAmountVnd="abc"` | ERP translator | Reject/quarantine, do not fabricate amounts |
| **Unknown enum** | State="REFUNDED" with no mapping | Translator mapping | Fail closed, update contract |
| **Invalid canonical invariant** | PAID amount=0 under example policy | CommonOrderPolicy | Reject per common policy |
| **Transient infrastructure failure** | Database lookup fails during enrichment | Adapter/enricher | Bounded retry, do not classify as schema error |

`unknownFormatOrders` only receives **messages that match no routing mapping**. A `NumberFormatException` or `IllegalArgumentException` thrown by a Transformer **does not automatically go to the Router's `defaultOutputChannel`**. Error handling must be configured at the endpoint/adapter if failed messages should be routed to quarantine.

### 9.1. Do Not Return Null to “Filter”

~~~java
// Do not do this inside a Transformer:
CanonicalOrder fromErp(VerifiedErpOrder input) {
    if (invalid(input)) {
        return null;
    }
    return convert(input);
}
~~~

According to Spring Integration Transformer documentation, a transformation method **must not return null** as a way to silently drop a message; the framework will raise an error. If filtering is needed, use a **Filter with a discardChannel**, or produce a typed **RejectedEvent outcome** for auditing.

### 9.2. Do Not Use the Default Branch to Silently Accept Data

A Router can be configured by default to drop unroutable messages, but in payment flows unknown types must be observable. Routing to `defaultOutputChannel` into quarantine is a testable learning pattern. In production, the queue needs a consumer, durability, bounds, and retention; never retain untrusted payloads indefinitely in an in-memory `QueueChannel`.

## 10. Metadata and Correlation Through the Normalizer

Multiple sources may send **the same business event** over different transports or experience broker redelivery. The Normalizer must preserve enough metadata for downstream steps to reconcile and group correctly.

### 10.1. Which Identities Must Be Preserved?

| Identity | Source | Why Preserve It? |
| --- | --- | --- |
| **trustedTenantId** | Ingress security context | Tenant isolation |
| **partnerId/sourceSystem** | Authenticated source registry | Provenance tracking, ID namespacing |
| **sourceEventId** | Verified event contract | Deduplication/redelivery |
| **externalOrderId** | Valid business payload | Link order by source |
| **businessCorrelationKey** | Workflow registry/trusted ingress | Group messages belonging to one workflow |
| **traceId** | Observability instrumentation | Trace across hops |
| **schemaVersion** | Parser/registry contract | Know which version to use to interpret payload |

A Spring Message transformed into a new payload may get a different **`MessageHeaders.ID`** from the ingress message. What matters is that **business identity** remains stable and verified.

### 10.2. Transformer Header Propagation

Spring Integration normally **propagates inbound headers when a Transformer returns a payload**. If a Transformer returns **a complete `Message`**, user code is responsible for the entire outbound Message and which headers are kept.

Example of a Transformer returning only a payload:

~~~java
.transform(VerifiedErpOrder.class, normalizer::fromErp)
~~~

In this example, framework headers and internally attached headers can propagate according to framework rules. Do not rely on that as a guarantee that **every header** crosses HTTP/JMS/TCP, since adapters use different HeaderMapper mechanisms.

### 10.3. When Building a New Message, Select Headers via an Allowlist

~~~java
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

final class CanonicalMessageFactory {
    private CanonicalMessageFactory() {}

    static Message<CanonicalOrder> fromVerifiedInput(
            CanonicalOrder order,
            String businessGroupKey) {
        if (businessGroupKey == null
                || businessGroupKey.isBlank()) {
            throw new IllegalArgumentException("MISSING_GROUP_KEY");
        }

        return MessageBuilder.withPayload(order)
                .setHeader("trustedTenantId", order.tenantId())
                .setHeader("sourceSystem", order.sourceSystem().name())
                .setHeader("businessEventId", order.sourceEventId())
                .setHeader(
                        "businessCorrelationKey", businessGroupKey)
                .setHeader(
                        IntegrationMessageHeaderAccessor.CORRELATION_ID,
                        businessGroupKey)
                .build();
    }
}
~~~

`businessGroupKey` here **must be generated or looked up by a trusted internal source**, never copied verbatim from a client HTTP header. Never copy `replyChannel`, `errorChannel`, or `routingSlip` from untrusted payloads when constructing a canonical Message.

### 10.4. Business Key vs. eventId

If three events—PAYMENT, INVENTORY, and SHIPPING—for one order need an Aggregator, they have **three distinct eventIds** but one **business correlation key**. A redelivered PAYMENT event must keep the same eventId and the same business key, rather than creating a new group from `MessageHeaders.ID`.

The Normalizer only produces a `CanonicalOrder` per input; **it is not an Aggregator**. If you want to combine `CanonicalOrder`s, you must explicitly define the key, expected member set, release strategy, timeout, and duplicate handling.

## 11. Unit Tests for Each Translator

Before wiring the flow into a Spring context, test pure mappings with **JUnit 5**. Tests should assert **values**, not merely that the method returns a `CanonicalOrder`.

### 11.1. ERP: VND Decimal and Status

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.Currency;
import org.junit.jupiter.api.Test;

class PurchaseOrderNormalizerTest {

    private final PurchaseOrderNormalizer normalizer =
            new PurchaseOrderNormalizer();

    @Test
    void erpPaidOrderBecomesCanonicalOrder() {
        var incoming = new VerifiedErpOrder(
                new TrustedSource(
                        "tenant-a", "PARTNER-ERP", SourceSystem.ERP),
                new ErpOrderV1(
                        "evt-erp-101",
                        "ERP-101",
                        "150000",
                        "2026-11-01T08:30:00Z",
                        "PAID"));

        CanonicalOrder order = normalizer.fromErp(incoming);

        assertEquals(1, order.canonicalSchemaVersion());
        assertEquals("tenant-a", order.tenantId());
        assertEquals("PARTNER-ERP", order.partnerId());
        assertEquals(SourceSystem.ERP, order.sourceSystem());
        assertEquals("evt-erp-101", order.sourceEventId());
        assertEquals("ERP-101", order.externalOrderId());
        assertEquals(CanonicalOrderStatus.PAID, order.status());
        assertEquals(new BigDecimal("150000"), order.total().amount());
        assertEquals(Currency.getInstance("VND"),
                order.total().currency());
        assertEquals(Instant.parse("2026-11-01T08:30:00Z"),
                order.occurredAt());
    }

    @Test
    void unknownErpStatusIsRejected() {
        var incoming = new VerifiedErpOrder(
                new TrustedSource(
                        "tenant-a", "PARTNER-ERP", SourceSystem.ERP),
                new ErpOrderV1(
                        "evt-erp-102",
                        "ERP-102",
                        "150000",
                        "2026-11-01T08:30:00Z",
                        "SETTLED_BUT_NOT_CONFIRMED"));

        assertThrows(IllegalArgumentException.class,
                () -> normalizer.fromErp(incoming));
    }

    @Test
    void wrongTrustedSourceCannotUseErpTranslator() {
        var incoming = new VerifiedErpOrder(
                new TrustedSource(
                        "tenant-a", "PARTNER-MARKET",
                        SourceSystem.MARKETPLACE),
                new ErpOrderV1(
                        "evt-erp-103", "ERP-103", "100",
                        "2026-11-01T08:30:00Z", "PAID"));

        assertThrows(SecurityException.class,
                () -> normalizer.fromErp(incoming));
    }
}
~~~

In the example, `SourceSystem` is guarded by `requireSource`, yet this test **does not replace** real-world authentication of connections and partners. `TrustedSource` must be constructed at ingress from trusted sources.

### 11.2. Marketplace: Minor-Unit Conversion

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.Currency;
import org.junit.jupiter.api.Test;

class MarketplaceNormalizationTest {

    @Test
    void convertsUsdMinorUnitsWithoutFloatingPoint() {
        var input = new VerifiedMarketplaceOrder(
                new TrustedSource(
                        "tenant-a", "MARKET-01",
                        SourceSystem.MARKETPLACE),
                new MarketplaceOrderV2(
                        "evt-m-1", "MK-202", 1235L, "USD",
                        1793521800000L, "SETTLED"));

        CanonicalOrder result =
                new PurchaseOrderNormalizer().fromMarketplace(input);

        assertEquals(CanonicalOrderStatus.PAID, result.status());
        assertEquals(new BigDecimal("12.35"),
                result.total().amount());
        assertEquals(Currency.getInstance("USD"),
                result.total().currency());
        assertEquals(Instant.ofEpochMilli(1793521800000L),
                result.occurredAt());
    }

    @Test
    void negativeMinorUnitsDoNotBecomeValidMoney() {
        var input = new VerifiedMarketplaceOrder(
                new TrustedSource(
                        "tenant-a", "MARKET-01",
                        SourceSystem.MARKETPLACE),
                new MarketplaceOrderV2(
                        "evt-m-2", "MK-203", -10, "USD",
                        1793521800000L, "SETTLED"));

        assertThrows(IllegalArgumentException.class,
                () -> new PurchaseOrderNormalizer()
                        .fromMarketplace(input));
    }

    @Test
    void unsupportedCurrencyIsRejectedExplicitly() {
        var input = new VerifiedMarketplaceOrder(
                new TrustedSource(
                        "tenant-a", "MARKET-01",
                        SourceSystem.MARKETPLACE),
                new MarketplaceOrderV2(
                        "evt-m-3", "MK-204", 1000, "XYZ",
                        1793521800000L, "SETTLED"));

        assertThrows(IllegalArgumentException.class,
                () -> new PurchaseOrderNormalizer()
                        .fromMarketplace(input));
    }
}
~~~

The `supportedCurrency` policy in the example only accepts VND and USD to avoid accidentally accepting a new currency without tests. When adding currencies, update the contract, fractional-digit tests, and currency/unit-price policies.

### 11.3. CSV: Decimal Scale and Invalid Formats

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class CsvNormalizationTest {

    private final TrustedSource source = new TrustedSource(
            "tenant-a", "PARTNER-CSV", SourceSystem.CSV_UPLOAD);

    @Test
    void csvDecimalAndStateBecomeCanonical() {
        var input = new VerifiedCsvOrder(source,
                new CsvOrderRow(
                        "evt-csv-303",
                        "CSV-303",
                        "89.90",
                        "USD",
                        "2026-11-01T08:30:00Z",
                        "PAYMENT_COMPLETE"));

        CanonicalOrder order =
                new PurchaseOrderNormalizer().fromCsv(input);

        assertEquals(CanonicalOrderStatus.PAID, order.status());
        assertEquals(new BigDecimal("89.90"),
                order.total().amount());
    }

    @Test
    void csvAmountWithWrongPrecisionIsRejected() {
        var input = new VerifiedCsvOrder(source,
                new CsvOrderRow(
                        "evt-csv-304",
                        "CSV-304",
                        "89.999",
                        "USD",
                        "2026-11-01T08:30:00Z",
                        "PAYMENT_COMPLETE"));

        assertThrows(ArithmeticException.class,
                () -> new PurchaseOrderNormalizer().fromCsv(input));
    }

    @Test
    void csvDateMustHaveAnUnambiguousInstant() {
        var input = new VerifiedCsvOrder(source,
                new CsvOrderRow(
                        "evt-csv-305",
                        "CSV-305",
                        "89.90",
                        "USD",
                        "01/11/2026 08:30",
                        "PAYMENT_COMPLETE"));

        assertThrows(IllegalArgumentException.class,
                () -> new PurchaseOrderNormalizer().fromCsv(input));
    }
}
~~~

**Note on the exception:** `Money` calls `BigDecimal.setScale(..., RoundingMode.UNNECESSARY)`, so a value with fractional digits that cannot be represented at the currency's scale throws `ArithmeticException`. Production code can wrap it into a domain error code such as `INVALID_CURRENCY_PRECISION`; tests should match the final exception contract published by the application.

### 11.4. Property Tests and Metamorphic Tests

As translators grow in number, beyond fixed examples you should test properties:

- **Deterministic:** identical input and verified context produce the same `CanonicalOrder`.
- **No lost provenance:** tenantId, partnerId, and sourceEventId remain intact.
- **No silent rounding:** amounts with wrong precision are always rejected.
- **Semantic equivalence:** e.g., USD `"12.35"` in CSV and `1235` minor units in marketplace produce the same `Money`.
- **Tenant isolation:** two tenants with the same `externalOrderId` must not be treated as the same order identity if downstream requires isolation.
- **Never turn unknown statuses into PAID:** an unmapped new enum must produce an explicit error.
- **Input bounds:** far-off dates, oversized numbers, overly long strings, and unsupported schemaVersions must be handled according to policy.

Asserting `result != null` alone is not enough to prove the Normalizer preserves semantics.

## 12. Integration Test: Three Formats Flowing Through a Shared IntegrationFlow

The following test uses **JUnit 5 + spring-test** and needs no Kafka/HTTP broker because parsing and authentication are assumed to run before the `verifiedIncomingOrders` channel.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(NormalizerFlowConfig.class)
class NormalizerFlowTest {

    @Autowired
    @Qualifier("verifiedIncomingOrders")
    MessageChannel input;

    @Autowired
    @Qualifier("canonicalOutput")
    QueueChannel output;

    @Autowired
    @Qualifier("unknownFormatOrders")
    QueueChannel unknown;

    @BeforeEach
    void clearQueues() {
        while (output.receive(0) != null) {
            // Clear the test context queue.
        }
        while (unknown.receive(0) != null) {
            // Clear the test context queue.
        }
    }

    private CanonicalOrder nextOrder() {
        Message<?> message = output.receive(0);
        assertNotNull(message);
        assertInstanceOf(CanonicalOrder.class, message.getPayload());
        return (CanonicalOrder) message.getPayload();
    }

    @Test
    void threeFormatsConvergeIntoTheSameCanonicalType() {
        var erp = new VerifiedErpOrder(
                new TrustedSource(
                        "tenant-a", "PARTNER-ERP", SourceSystem.ERP),
                new ErpOrderV1(
                        "evt-e-1", "ERP-101", "150000",
                        "2026-11-01T08:30:00Z", "PAID"));

        var market = new VerifiedMarketplaceOrder(
                new TrustedSource(
                        "tenant-a", "MARKET-01",
                        SourceSystem.MARKETPLACE),
                new MarketplaceOrderV2(
                        "evt-m-1", "MK-202", 1235,
                        "USD", 1793521800000L, "SETTLED"));

        var csv = new VerifiedCsvOrder(
                new TrustedSource(
                        "tenant-a", "PARTNER-CSV",
                        SourceSystem.CSV_UPLOAD),
                new CsvOrderRow(
                        "evt-c-1", "CSV-303", "89.90", "USD",
                        "2026-11-01T08:30:00Z",
                        "PAYMENT_COMPLETE"));

        assertTrue(input.send(
                MessageBuilder.withPayload(erp).build()));
        assertTrue(input.send(
                MessageBuilder.withPayload(market).build()));
        assertTrue(input.send(
                MessageBuilder.withPayload(csv).build()));

        List<CanonicalOrder> results = List.of(
                nextOrder(), nextOrder(), nextOrder());

        assertEquals(3, results.size());
        assertEquals(Set.of(
                        SourceSystem.ERP,
                        SourceSystem.MARKETPLACE,
                        SourceSystem.CSV_UPLOAD),
                results.stream()
                        .map(CanonicalOrder::sourceSystem)
                        .collect(Collectors.toSet()));

        assertTrue(results.stream().allMatch(
                order -> order.canonicalSchemaVersion() == 1));
        assertTrue(results.stream().allMatch(
                order -> order.status()
                        == CanonicalOrderStatus.PAID));
        assertEquals(new BigDecimal("150000"),
                results.get(0).total().amount());
        assertEquals(new BigDecimal("12.35"),
                results.get(1).total().amount());
        assertEquals(new BigDecimal("89.90"),
                results.get(2).total().amount());
        assertNull(output.receive(0));
    }

    @Test
    void unknownPayloadTypeGoesToQuarantineChannel() {
        assertTrue(input.send(
                MessageBuilder.withPayload(
                        "unrecognized-data").build()));

        Message<?> quarantine = unknown.receive(0);
        assertNotNull(quarantine);
        assertEquals("unrecognized-data",
                quarantine.getPayload());
        assertNull(output.receive(0));
    }
}
~~~

**Takeaway:** even though the three payloads have different field names and primitive types, the `canonicalOutput` channel emits only `CanonicalOrder`. The `unknownPayloadType` test only verifies the Router default branch; it **does not** prove that parser errors in a translator go into the same queue.

### 12.1. Note on Assertion Ordering

The demo flow uses **DirectChannel**, so each `send` executes synchronously through router/transformer/policy into the output `QueueChannel`, making positional assertions after three sequential sends valid. If switched to **ExecutorChannel**, results can arrive in any order; tests must match by `sourceEventId` before asserting contents rather than assuming `results.get(0)` is ERP.

### 12.2. Testing Errors in a Known Format

~~~java
// Method snippet to add to NormalizerFlowTest.
@Test
void malformedKnownFormatDoesNotProduceCanonicalOrder() {
    var invalid = new VerifiedErpOrder(
            new TrustedSource(
                    "tenant-a", "PARTNER-ERP", SourceSystem.ERP),
            new ErpOrderV1(
                    "evt-e-invalid", "ERP-999", "not-a-number",
                    "2026-11-01T08:30:00Z", "PAID"));

    // The exception may be wrapped by Spring Integration into
    // MessagingException/MessageTransformationException.
    assertThrows(RuntimeException.class,
            () -> input.send(
                    MessageBuilder.withPayload(invalid).build()));

    assertNull(output.receive(0));
    // The unknown-format channel is not the Transformer's errorChannel.
    assertNull(unknown.receive(0));
}
~~~

If you want this error routed to quarantine, add **proper error handling at ingress/transformer** matching sync/async semantics, or handle it in the adapter with appropriate ack/retry/DLQ. Never tweak assertions to pretend the Router sent parse errors to `defaultOutputChannel`.

### 12.3. Testing Preservation of the Business Correlation Header

~~~java
// Method snippet to add to NormalizerFlowTest.
@Test
void propagatesTrustedBusinessCorrelation() {
    var erp = new VerifiedErpOrder(
            new TrustedSource(
                    "tenant-a", "PARTNER-ERP", SourceSystem.ERP),
            new ErpOrderV1(
                    "evt-e-correlation", "ERP-777", "500",
                    "2026-11-01T08:30:00Z", "PAID"));

    String businessKey = "ord:v1:tenant-a:ERP-777:2";
    assertTrue(input.send(
            MessageBuilder.withPayload(erp)
                    .setHeader("businessCorrelationKey", businessKey)
                    .build()));

    Message<?> transformed = output.receive(0);
    assertNotNull(transformed);
    assertEquals(businessKey,
            transformed.getHeaders().get(
                    "businessCorrelationKey"));
}
~~~

In the test, the header is attached by internal code and treated as verified. Production needs an authentication/lookup layer to generate the key; never allow a client-supplied `businessCorrelationKey` to pass straight into `verifiedIncomingOrders`.

## 13. Semantic Normalization Matters More Than Field Renaming

Renaming `orderNo` to `externalOrderId` is mechanical mapping. Yet two fields with similar names **do not necessarily share the same meaning**.

### 13.1. Gross, Net, and Tax

Suppose:

~~~text
ERP:
  grossAmountVnd = 150000
  includesTax = true

Marketplace:
  amountMinor = 150000
  currencyCode = VND
  excludesFees = true
~~~

If ERP is tax-inclusive total and Marketplace excludes shipping/fees, these two fields cannot be assumed to mean the same `total`. If the canonical contract truly requires **gross payable amount**, the Marketplace translator must have sufficient data and rules to compute it; otherwise, **reject or add an `amountBasis`/missing-data representation**.

Never turn incomplete data into a plausible-looking value just to finish the Normalizer.

### 13.2. Does “PAID” Really Equal “SETTLED”?

With one partner, `SETTLED` may mean funds have arrived in the account, while `PAID` only means payment was authorized. With another partner, both correspond to the customer having completed payment.

Every status mapping table must be **approved by business owners**. The example's table:

| ERP | Marketplace | CSV | Canonical |
| --- | --- | --- | --- |
| PAID | SETTLED | PAYMENT_COMPLETE | PAID |
| CANCELLED | CANCELED | ORDER_CANCELLED | CANCELLED |
| PENDING | PENDING | AWAITING_PAYMENT | PENDING |

is valid only if those source names **have the same meaning under the specific integration contract**. A new value like `PARTIALLY_REFUNDED` must not be mapped automatically to PAID or CANCELLED before its semantics are defined.

### 13.3. Absolute Time, Local Time, and Daylight Saving

`Instant.parse("2026-11-01T08:30:00Z")` is an absolute instant. But `"2026-11-01 08:30"` **does not specify a timezone**.

If ERP sends local time and the contract specifies `Asia/Ho_Chi_Minh`, you can parse with `LocalDateTime` and apply the agreed `ZoneId`. If data comes from a region with daylight saving time, a local timestamp may **not exist or may occur twice**. There must be an explicit resolution rule or rejection; never default to the container host's system timezone.

~~~java
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;

static Instant parsePartnerLocalTime(String text) {
    LocalDateTime local = LocalDateTime.parse(
            text,
            DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm"));
    return local.atZone(
            ZoneId.of("Asia/Ho_Chi_Minh")).toInstant();
}
~~~

**This is an example for a specific timezone contract**, not a generic converter for all sources. For zones with DST and strict accuracy requirements, handle gaps/overlaps intentionally rather than assuming Java's default `atZone()` resolves them in line with business rules.

### 13.4. Units of Measure Also Need Canonicalization

Normalizer is not only for money. A logistics system might receive:

~~~text
Source A: weight=2.5 kg
Source B: weight=2500 g
Source C: weight=5.511556 lb
~~~

If canonical `weightGrams` is a decimal or integer at a chosen precision, every translator must convert using explicit rounding rules, bounds, and units. Multiplying with `double` and casting to `int` can lose precision; use `BigDecimal` with an explicitly chosen precision.

### 13.5. Partner IDs vs. Internal IDs

Two sources can both send `externalOrderId="1001"` for two completely different orders. **The Normalizer must not treat that as a shared internal order ID** without looking up a registry keyed by tenant + partner + externalId.

If downstream needs `internalOrderId`, add an **Enricher** authorized to query the mapping, or separate out a `ResolveIdentity` step after normalization. Do not conflate having a canonical schema with all external business IDs being unified.

## 14. XML Format and Schema Versions: How to Add a New Source?

The Normalizer must remain extensible when a fourth source sends XML:

~~~xml
<purchaseEvent schemaVersion="3">
    <eventId>evt-xml-404</eventId>
    <externalOrder>XML-404</externalOrder>
    <money currency="USD">19.99</money>
    <occurredAt>2026-11-01T08:30:00Z</occurredAt>
    <state>PAYMENT_CAPTURED</state>
</purchaseEvent>
~~~

The proper integration process:

1. The inbound adapter receives raw XML over an authenticated channel with size limits.
2. The XML parser is configured **against XXE/external entity resolution**, with schema/namespace validation.
3. Decode into a typed `XmlPurchaseV3`, and only then create `VerifiedXmlOrder`.
4. Add a route for the new type or verified source+version.
5. Write a `fromXmlV3` translator returning **CanonicalOrder version 1**.
6. Add contract tests and tests for invalid fields, unknown status, currency precision, and tenant isolation.
7. Keep downstream on CanonicalOrder version 1 if semantics have not changed.

**Do not force canonical version to jump from 1 to 3 just because the XML source uses schema v3.** There are two independent lifecycles:

- **Source schema version**: changes at a partner's input boundary.
- **Canonical schema version**: changes in the shared internal contract.

### 14.1. When One Source Has Multiple Versions

Suppose Marketplace emits both `MarketplaceOrderV1` and `MarketplaceOrderV2` during a migration period. Maintain two typed DTOs or a versioned parser with explicit validation:

~~~text
JSON version 1 -> VerifiedMarketplaceV1 -> Translator V1 --+
                                                          +-> CanonicalOrder v1
JSON version 2 -> VerifiedMarketplaceV2 -> Translator V2 --+
~~~

Do not use `if (fieldX != null)` to guess the version when two schemas share overlapping fields. Rely on a trusted schemaVersion or contract/endpoint-specific parser, rejecting unsupported versions.

### 14.2. Changing the Canonical Contract Also Has Costs

If downstream needs to add `taxIncluded` or `lineItems`, upgrading from CanonicalOrder v1 to v2 may require:

- Backward/forward compatibility policies.
- v1 → v2 mapping or dual-version support.
- Schema registry and producer/consumer contracts.
- Migration of persisted events, replay, and DLQ.
- Cross-service compatibility tests.
- A rollout plan that avoids upgrading every translator in a single non-rollbackable deployment.

**Normalizer reduces coupling to source schemas**; it does not eliminate the versioning cost of the **canonical schema**.

## 15. A Multi-Row CSV File Is Not a Single Normalized Message

In the main example, each `VerifiedCsvOrder` represents **one parsed row**. For a 10,000-row file, a different flow sits upstream:

~~~mermaid
flowchart LR
    F["CSV file"] --> P["CSV parser"]
    P --> S["Splitter: per row"]
    S --> N["Normalizer: row -> CanonicalOrder"]
    N --> V["Validate common contract"]
    V --> H["Idempotent business handler"]
    N -.->|"Row validation failed"| Q["Row quarantine"]
~~~

Row splitting may happen in the parser, poller, or Splitter depending on size and streaming requirements. Do not load a multi-GB file into a `List` just to feed a Splitter when a bounded iterator/stream works.

### 15.1. Row-by-Row Error Policy

| Error Kind | Example | Possible Decision |
| --- | --- | --- |
| **File-level** | Invalid signature, unauthorized tenant | Reject the entire file |
| **Schema-level** | Header missing required column, wrong charset | Reject file or quarantine |
| **Row-level** | Row 305 has amount="abc" | Reject that row; let other rows proceed if policy allows |
| **Infrastructure** | DB down while writing row 400 | Retry/park; do not classify as an invalid row |
| **Duplicate row** | Same eventId within file or on redelivery | Deduplicate by logical event |
| **Unknown outcome** | External command sent but no reply received | Reconcile before retrying side effects |

If the business requires **all-or-nothing** (all rows valid or reject the entire file), do not let the Normalizer allow unintended partial success. Conversely, if per-row import is accepted, produce an **ImportReport** with expected, accepted, rejected, and pending counts plus per-row error codes.

### 15.2. Do Not Let a Filter Drop an Item Before an Aggregator

If a Splitter attaches `sequenceSize=100` and one row is dropped by a Filter without producing a terminal outcome, an Aggregator waiting for 100 outcomes may never release. For imports requiring a complete report:

- Every row needs **one terminal result** (SUCCESS or REJECTED) if that is the policy.
- Infrastructure exceptions need retry, state/timeout, not silent conversion into REJECTED.
- An Aggregator keyed by correlationId/sequence or manifest **releases only when all logical rows complete**, not by counting attempts.

This is how Normalizer works alongside **Splitter, Filter, Aggregator, and retry** without losing valid data.

### 15.3. CSV Row Identity

When a file is replayed after a crash, row 300 may appear again. One possible key is:

~~~text
logicalEventKey =
    trustedTenantId
    + ":" + partnerId
    + ":" + fileImportId
    + ":" + rowIdentity
~~~

`rowIdentity` must remain stable across replays (an immutable manifest lineNumber or a trusted source eventId). If the parser strips blank lines and renumbers rows, line numbers can stop being stable. Use an existing eventId or a content digest with a conflict policy; never pick one arbitrarily per run.

## 16. Retry, Replay, and Idempotency After the Normalizer

A Transformer may be deterministic, yet if the broker redelivers the same raw event, the Normalizer can produce **two identical `CanonicalOrder` instances**. From a transformation standpoint, that is correct; from a database write or external service call standpoint, it can cause **two side effects**.

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant N as Normalizer
    participant H as Business Handler
    participant D as Database
    B->>N: Raw event E, attempt 1
    N->>H: CanonicalOrder E
    H->>D: Apply business effect
    D-->>H: Commit
    Note over B: Ack/connection lost
    B->>N: Raw event E, attempt 2
    N->>H: CanonicalOrder E
    H->>D: Detect E already processed
    D-->>H: Skip duplicate effect
~~~

**Normalizer does not provide exactly-once processing** merely by converting all formats into one type. Idempotency must protect the **logical business event or operation** where effects occur.

### 16.1. Scoping Event Identity Properly

If `sourceEventId` is unique only within a partner, an appropriate deduplication key is:

~~~text
dedupKey = trustedTenantId + ":" + partnerId + ":" + sourceEventId
~~~

Do not use `externalOrderId` alone: a single order can have multiple valid events (PAYMENT, REFUND, CANCEL). Do not use `MessageHeaders.ID`: that is a technical identity that can change across builds/replays. Do not use `occurredAt` as an idempotency key because multiple events can share the same timestamp.

### 16.2. A Durable Inbox/Ledger

PostgreSQL example:

~~~sql
CREATE TABLE canonical_event_inbox (
    tenant_id VARCHAR(48) NOT NULL,
    partner_id VARCHAR(64) NOT NULL,
    source_event_id VARCHAR(96) NOT NULL,
    raw_digest VARCHAR(128) NOT NULL,
    source_schema_version INTEGER NOT NULL,
    canonical_schema_version INTEGER NOT NULL,
    processing_status VARCHAR(32) NOT NULL,
    accepted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, partner_id, source_event_id)
);

CREATE INDEX canonical_event_inbox_status_idx
    ON canonical_event_inbox (processing_status);
~~~

When receiving an event:

1. Take `tenantId`/`partnerId` from the trust boundary and `sourceEventId` from the validated payload.
2. Compute a digest over the **wire payload canonicalized per schema/format version**, or store a raw digest using a defined calculation.
3. Look up/claim the event using the unique constraint.
4. If already processed with an equal digest, it is a redelivery and must not trigger a new effect.
5. If the same identity arrives with a different digest, raise **ID_CONFLICT** and quarantine; never overwrite silently.
6. If status is still RECEIVED/DISPATCH_PENDING, recover processing rather than dropping it.
7. Mark COMPLETED only when the business effect satisfies the commit condition under the contract.

### 16.3. Crash Window Between Inbox and Downstream

Anti-pattern:

~~~text
1. INSERT inbox E, status=SEEN
2. COMMIT
3. Crash before sending E to business handler
4. Broker redelivers E
5. Code sees E is already SEEN and drops it
=> Business effect never occurs
~~~

Fixes to choose from:

- **Transactional outbox:** write the inbox record and dispatchable event in the same transaction; a worker continues publishing/consuming after a crash.
- **Inbox state machine:** RECEIVED → DISPATCH_PENDING → PROCESSED, with a recovery scanner and ownership.
- **Transactional consumer:** commit offsets/acks aligned with the database transaction per adapter capabilities; still test gaps between resource boundaries.

Not every application needs all three, but it must have **one concrete model** protecting the crash window.

### 16.4. Replaying When Mapping Versions Change

Suppose `MarketplaceOrderV2` previously mapped `SETTLED → PAID`, but a contract update requires distinguishing `SETTLED` from a new `RECONCILED` state.

When replaying raw events to rebuild projections, you must know:

- The original source schema version.
- The semantic translation/mapping version.
- The canonical schema version.
- Whether to rebuild a **read model** or re-execute **side effects**.
- Migration and backward-compatibility rules.

Replaying to rebuild reports **must not automatically resend charges/emails/bookings**. Separate **projection rebuilding** from effectful handlers and use an idempotency/operation ledger.

### 16.5. Why Not Generate a Random eventId Inside the Transformer?

~~~java
// Anti-pattern for redelivery:
String newId = java.util.UUID.randomUUID().toString();
~~~

If every Transformer invocation generates a fresh eventId, a redelivered raw event looks like a new event and bypasses deduplication. `sourceEventId` must be stable by contract; if the source omits one, ingress must define a **deterministic identity from the manifest/operation** or persist a mapping. Never call `UUID.randomUUID()` per attempt without storing it.

## 17. Error Handling: Never Turn Corrupted Data into Seemingly Valid Data

### 17.1. Error Classification

| Error Class | Example | Recommended Handling |
| --- | --- | --- |
| **Parsing/schema** | Invalid JSON, CSV missing required column | Reject/quarantine at adapter |
| **Authorization** | Producer unauthorized to emit ERP event for another tenant | Reject, audit/security alert |
| **Semantic mapping** | Unsupported new source status | Quarantine, update mapping contract |
| **Canonical validation** | PAID total=0 under illustrative policy | Reject via domain validation |
| **Transient infrastructure** | Registry lookup timeout, DB unavailable | Bounded retry, preserve eventId |
| **Unexpected application bug** | NullPointerException/IllegalStateException from code defect | Alert, quarantine/retry after fix |
| **External side effect unknown** | HTTP timeout after sending charge command | Reconcile; do not treat as data error |

Never catch `Exception` and return a `CanonicalOrder` with `status=PENDING` and amount=0, as downstream systems will treat a failed event as a valid one.

### 17.2. DirectChannel vs. Async Channels

The lesson's DSL example uses **DirectChannel**. When a Translator throws an exception:

- The exception normally propagates back to the sender (possibly wrapped by Spring Integration in a `MessagingException`).
- A failed `input.send()` does not automatically send the message to the `unknownFormatOrders` `QueueChannel`.
- The inbound adapter (HTTP/JMS/Kafka) must decide ack/retry/response according to the real contract.

If replaced with an **ExecutorChannel**, poller, or async endpoints, error handling can send an **ErrorMessage** to `errorChannel`. However, an `ErrorMessage` wraps a `Throwable`, not a valid `CanonicalOrder`, and `errorChannel` **is not automatically a durable DLQ**.

### 17.3. Quarantine Record

A useful quarantine record:

~~~json
{
  "sourceSystem": "CSV_UPLOAD",
  "schemaVersion": 1,
  "eventRef": "evt-csv-304",
  "errorStage": "NORMALIZATION",
  "errorCode": "INVALID_CURRENCY_PRECISION",
  "retryable": false,
  "status": "REQUIRES_SOURCE_CORRECTION"
}
~~~

This is an **example model**, not an `ErrorMessage` generated automatically by Spring Integration. Quarantine can store raw payloads in protected object storage while keeping only references/digests in metadata; minimize PII and enforce clear retention and authorization.

### 17.4. Remediation and Replay Path

For data errors:

1. Record the source, schema version, event ID, error code, and enough reconciliation context.
2. Ask the partner to fix the payload or issue a valid correction event.
3. Do not mutate the payload yourself and replay with the same eventId if versioning policy forbids it.
4. Once corrected, use the contractual `eventId`/revision identity and check the existing ledger and side effects.
5. Re-run through the **exact applicable translator/version** without bypassing validation.

For infrastructure errors, perform bounded retries with backoff; if still unresolved, mark status as pending/unknown with a recovery job rather than silently treating the message as normalized.

## 18. Data Volume, Backpressure, and Ordering

Payload transformation can be CPU-bound (JSON/XML parsing) or I/O-bound (catalog/rate lookups). A pipeline that works at 10 events/second may fail at 10,000 events/second.

### 18.1. Bounded Resources

- Limit bytes per HTTP/JMS/AMQP message and CSV row size.
- Limit digit count in `amountDecimal` before instantiating `BigDecimal`; huge numeric strings can exhaust CPU/memory.
- Limit XML node counts/depth and disable external entity resolution to prevent XXE.
- Do not create unbounded `QueueChannel`s in production just because the demo test used them.
- Use bounded executors, queue capacities, timeouts, and per-source rate limits.
- If one partner frequently sends invalid schemas, quarantine needs quotas so it does not fill storage for all other partners.

### 18.2. No Parallelism Just from Having Three Router Branches

The Router selects a branch by type. With `DirectChannel`, execution runs on the sender's thread; sending three sequential messages in a test does not prove they run in parallel.

To achieve parallelism, place `ExecutorChannel`/async adapters at appropriate points and isolate per source with bulkheads. However:

- A large thread pool does not replace database connection pool capacity.
- Async transformations can **reorder completions**.
- If downstream requires ordering by logical event, use sequence/version numbers and a Resequencer or dedicated coordinator.
- Do not sort blindly by `occurredAt` when producer clocks have skew.

### 18.3. Source Independence

One partner sending bursts of invalid or slow events should not degrade processing for all other tenants/product lines. You can apply:

- Per-source rate limits/quotas.
- Bounded queues and error isolation.
- Circuit breakers around external enrichment/lookups, not around pure transformations.
- Per-adapter/per-translator latency and error metrics.
- Per-source ingestion pause/resume or isolated DLQ replay.

**Do not isolate by source and then forget to enforce unified output validation**: all three translators must obey one canonical contract so downstream can rely on it.

## 19. Observability for the Normalizer

A generic `TRANSFORM_FAILED` error report is insufficient to diagnose why a partner started sending a new status or wrong amount scale.

| Metric | Meaning |
| --- | --- |
| **normalizer_input_total{source,schema}** | Messages received per source/schema |
| **normalizer_output_total{source,status}** | CanonicalOrder instances emitted |
| **normalizer_unsupported_type_total{source}** | Router found no matching translator |
| **normalizer_parse_failed_total{source,code}** | Unparseable input data |
| **normalizer_semantic_reject_total{source,code}** | Mapping/validation rejections |
| **normalizer_processing_duration_seconds{source}** | Parse/translate/validate latency |
| **normalizer_quarantine_total{reason}** | Events stored for later handling |
| **normalizer_retry_total{source,reason}** | Retries due to transient failures |
| **normalizer_duplicate_skipped_total{source}** | Events detected as redeliveries |
| **normalizer_inbox_pending** | Inbox items not yet dispatched or completed |
| **normalizer_backpressure_total{source}** | Queue full/task rejections |
| **normalizer_canonical_version_total{version}** | Distribution of canonical schema versions |

Keep `source`, `schema`, `status`, and `reason` within a **bounded set of values**. Never put arbitrary `eventId`, `orderId`, `tenantId`, or payload text in metric labels; that creates extreme cardinality and risks leaking data.

### 19.1. Sample Success Log

~~~json
{
  "stage": "NORMALIZE",
  "sourceSystem": "MARKETPLACE",
  "sourceSchemaVersion": 2,
  "canonicalSchemaVersion": 1,
  "eventRef": "evt-market-202",
  "outcome": "SUCCESS",
  "normalizedStatus": "PAID"
}
~~~

### 19.2. Sample Failure Log

~~~json
{
  "stage": "NORMALIZE",
  "sourceSystem": "CSV_UPLOAD",
  "sourceSchemaVersion": 1,
  "eventRef": "evt-csv-304",
  "outcome": "REJECTED",
  "errorCode": "INVALID_CURRENCY_PRECISION",
  "retryable": false
}
~~~

**Never log** raw payment details, tokens, customer PII, sensitive file paths, or unfiltered payloads. If raw events must be inspected later, store them in an access-controlled location with proper retention, logging only a reference.

### 19.3. Useful Alerts

1. One source suddenly spikes in `UNKNOWN_STATUS` errors after a partner API upgrade.
2. Unsupported-type message counts rise with no planned translator addition.
3. An adapter succeeds at ingestion while normalizer output drops sharply.
4. Currency precision errors spike on marketplace after a rollout.
5. Quarantine fills up or lacks an assigned consumer/operator.
6. Inbox has items stuck in `RECEIVED`/`DISPATCH_PENDING` past SLA.
7. A new canonical schema version appears before consumers support it.
8. One source emits tenant IDs outside its verified permissions.
9. Downstream reports false joins due to `externalOrderId` missing a partner namespace.
10. Replayed messages trigger business effects a second time.

## 20. Runbook: Partner Sends Data but CanonicalOrder Never Appears

**Scenario:** the system logs successful inbound event receipt, yet downstream sees no corresponding `CanonicalOrder`.

### Step 1 — Verify the Event Actually Entered the Right Adapter

Collect trusted source/partner, schema version, event ID, receipt timestamp, and trace. Check whether the adapter received bytes successfully or hit a rate limit/quota or parse failure. Never use HTTP 200 or a broker ACK as proof that the business handler committed.

### Step 2 — Check Authentication and Wrapper Type

Did the raw event pass authentication/authorization? Was the correct `VerifiedErpOrder`/`VerifiedMarketplaceOrder`/`VerifiedCsvOrder` constructed? If an ERP event was wrapped as marketplace, the Router will take the wrong branch.

### Step 3 — Check Route Selection

A new DTO after a rollout may lack a `channelMapping`. Inspect `unknownFormatOrders`/quarantine and unsupported-type metrics. Never silently route unknown DTOs to the ERP translator just because it is the default route.

### Step 4 — Check Converters and Status Mapping

Example:

~~~text
Input source=MARKETPLACE, schemaVersion=2
currencyCode=USD
amountMinor=1235
state=PARTIALLY_REFUNDED

Normalizer:
  source recognized
  amount valid
  state not mapped
  outcome: UNKNOWN_MARKETPLACE_STATE
~~~

Do not change the mapping to PAID before knowing what `PARTIALLY_REFUNDED` means. Verify with the partner contract and domain owner.

### Step 5 — Check Common Validation

A message may pass the Translator and fail in `CommonOrderPolicy`, such as PAID with amount=0 under the example policy. Distinguish **format-specific errors** from **canonical invariant violations**.

### Step 6 — Locate ErrorMessage/Quarantine

With `DirectChannel`, exceptions may propagate back to the adapter caller. With async channels, inspect `errorChannel`/error handler, DLQ, or recovery jobs. Quarantine records must contain source, schema, event identity, and error code sufficient for reprocessing.

### Step 7 — Check Inbox/Dedup State

If `eventId` already exists:

- **COMPLETED + same digest:** already processed; skipping the redelivery is correct.
- **RECEIVED/DISPATCH_PENDING:** check for a stalled worker/recovery scanner.
- **Same ID with different digest:** investigate `ID_CONFLICT`.
- **Not present:** look for ingestion/routing failures prior to the inbox.

### Step 8 — Controlled Recovery

Replay only after confirming a fixed data issue, a retryable infrastructure failure, or a valid correction. Preserve proper identity/versioning and avoid re-triggering non-idempotent side effects.

### Step 9 — Post-Remediation Verification

Verify canonical output has accurate `Money`/`Instant`/status/source identity, business handlers execute exactly once, and metrics/error rates return to baseline. With multi-source data, verify schema contracts rather than only counting processed events.

## 21. Hands-On Exercise: Normalizer for Three Payment Sources

Implement a Spring Integration module accepting three types of payment notifications:

~~~text
ERP             -> JSON v1 -> ErpPaidEvent
Marketplace     -> JSON v2 -> MarketplacePaidEvent
Batch Partner   -> CSV     -> CsvPaidRow

All types:
   -> validated trusted context
   -> Normalizer (route + translator)
   -> PaymentCanonicalEvent
   -> common validation
   -> idempotent persistence
~~~

### 21.1. Minimal Canonical Contract

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.Currency;

record PaymentCanonicalEvent(
        int schemaVersion,
        String tenantId,
        String sourceSystem,
        String sourceEventId,
        String externalPaymentId,
        String internalOrderId,
        BigDecimal amount,
        Currency currency,
        Instant paidAt,
        String paymentStatus) {
}
~~~

**Requirement:** `internalOrderId` must come from a **trusted mapping** keyed by tenant/source/externalPaymentId or externalOrderId; never assume partner payment IDs share a single namespace.

### 21.2. Test Dataset

| Row | Source | Source Values | Expected Output |
| --- | --- | --- | --- |
| 1 | ERP | `"150000"` VND, `PAID` | 150000 VND, PAID |
| 2 | Marketplace | `1235` minor USD, `SETTLED` | 12.35 USD, PAID |
| 3 | CSV | `"89.90"` USD, `PAYMENT_COMPLETE` | 89.90 USD, PAID |
| 4 | ERP | `"abc"` VND | Reject INVALID_AMOUNT_FORMAT |
| 5 | Marketplace | `-1` minor USD | Reject negative amount |
| 6 | CSV | `"89.999"` USD | Reject invalid precision |
| 7 | Marketplace | `PARTIALLY_REFUNDED` | Reject unknown status until defined |
| 8 | Unknown schema | JSON version 9 | Unsupported version/quarantine |
| 9 | Duplicate | Event ID from row 2 resent | Do not record effect a second time |
| 10 | Multi-tenant | Same externalPaymentId in different tenant | Do not merge identities mistakenly |

### 21.3. Implementation Steps

1. Determine source/tenant from adapter identity rather than self-reported payload fields.
2. Define a canonical schema with explicit types, units, and validation.
3. Define separate DTOs for ERP, Marketplace, and CSV.
4. Write a parser/MessageConverter per schema; test invalid JSON, CSV quoting, charset, and input size.
5. Write a Router selecting by typed payload or trusted source+version.
6. Write three pure Translators; avoid external I/O unless required.
7. Merge the branches into one canonical channel.
8. Add `CommonCanonicalValidation` protecting shared invariants.
9. Add a default route for unknown types and an error path for invalid known types.
10. Write unit tests for fields, status, currency, timestamp, and source identity.
11. Write an integration test proving all three formats yield `PaymentCanonicalEvent`.
12. Preserve `sourceEventId`, `partnerId`, and `businessCorrelationKey` across the Normalizer.
13. Use an inbox/ledger or appropriate idempotent receiver to prevent duplicate effects across redeliveries.
14. For CSV batch processing, design row-level outcomes and a final import report.
15. Write a contract test for a new XML source without modifying the business handler.
16. Simulate a mapping version change and perform a controlled replay of historical inputs.
17. Measure parse/translate latency, quarantine rate, pending inbox, and backpressure.
18. Write a runbook explaining how to replay a failed event without re-sending committed side effects.

### 21.4. Acceptance Criteria

| Criterion | How to Verify |
| --- | --- |
| Single output contract | Downstream receives only PaymentCanonicalEvent |
| Per-source mapping | Each input schema has its own translator and tests |
| Accurate currency | USD minor units and VND have no scale errors |
| Accurate timestamp | Instant has explicit timezone/UTC |
| Semantic status | Unknown never defaults to PAID |
| Tenant/source isolation | Mismatched verified context is blocked |
| Router fallback | Unknown input goes to quarantine instead of vanishing |
| Error handling | Invalid known format never silently becomes canonical |
| Header propagation | Business correlation and event ID are not altered arbitrarily |
| Replay | Same eventId produces no duplicate effect |
| CSV batch | One bad row does not unintentionally drop other rows |
| Observability | Metrics and logs suffice to investigate rejection reasons |

### 21.5. Try Swapping One Source Without Touching Downstream

A useful architectural litmus test:

> When a partner switches from CSV v1 to XML v3 while the data meaning stays the same, the integration team must be able to replace the parser, typed DTO, and Translator **without changing reporting/order-recording logic** that consumes only the canonical schema.

If source-specific field names still leak downstream as `if (source == CSV)`, the Normalizer has not yet created a loosely coupled boundary.

## 22. Self-Check Questions

1. Is Normalizer a single Transformer or a pattern coordinating a Router with multiple Translators?
2. Why do three JSON/CSV payloads with the same meaning but different fields/units represent a Normalizer problem?
3. Why is a `MessageConverter` turning bytes into a Java record alone not sufficient for normalization?
4. Does a canonical schema require all sources to produce identical field values?
5. Can `grossAmountVnd` and `amountMinor` always map directly to the same `total`?
6. Why should `double` never be used for monetary amounts?
7. Is `SETTLED` always synonymous with `PAID`?
8. If Marketplace introduces an unsupported new state, should you default it to PENDING or fail closed?
9. When is routing by payload type appropriate, and when should you route by trusted `schemaVersion`?
10. Why shouldn't raw JSON `String`s be routed solely on `payload.getClass()`?
11. Is returning null from a `Transformer` a valid way to implement a Filter?
12. Does a Router's `defaultOutputChannel` automatically receive exceptions thrown by a Translator?
13. What is the difference between a source schema version and a canonical schema version?
14. Why must `sourceEventId` remain stable across retries?
15. How does a business correlationId differ from a source eventId?
16. If a Translator constructs a brand-new Message, what must be done with trusted headers?
17. Why is `Instant` important when two sources use different timezones?
18. If one row of a CSV fails, should the entire file always be rejected?
19. Why can a unique index on an inbox table still lose events if a crash occurs before dispatch?
20. Does Normalizer guarantee exactly-once side effects?
21. When a partner changes schemas, what should be verified before enabling the new production route?
22. Which metrics distinguish unknown input types from invalid known values?
23. When is an Enricher needed after the Normalizer to map `externalOrderId` to `internalOrderId`?
24. Why shouldn't an unbounded `QueueChannel` be used to collect all failed messages?

## 23. Design and Operations Checklist

- Documented all input schemas, versions, charsets, currencies/timezones, and owners for each source.
- Every source passes authentication/authorization and schema validation before trusted routing.
- Canonical contract clearly defines field types, units, nullable semantics, and enum values.
- Source-specific parsing is separated from semantic translation; no generic CSV split or unsafe XML parser.
- Router selects the right translator based on typed payload or trusted source+version.
- No default route silently turns unknown payloads into seemingly valid data.
- Each Translator returns a non-null `CanonicalOrder` or emits a classified error.
- Status mappings are confirmed by domain owners as semantically equivalent.
- Money uses `BigDecimal`/`Currency` with explicit rounding/precision policies.
- Timestamps have explicit timezone/UTC rather than relying on the system default zone.
- `sourceEventId`, tenant, partner, schema version, and business correlation remain properly scoped.
- If a Transformer builds a new Message, only allowlisted internal headers are copied/attached.
- A common validator runs after every Translator; no source bypasses policy.
- Source schema migrations have contract tests and rollback plans.
- Canonical schema versioning has clear backward/forward compatibility.
- Unknown formats and malformed known formats have separate error/quarantine paths.
- Error channel, DLQ, and quarantine have consumers, durability, retention, and auditing.
- Retries distinguish data errors from transient infrastructure failures.
- Inbox/outbox/recovery handles crash windows and event ID conflicts.
- Side effects have idempotency independent of whether the Transformer is deterministic.
- CSV/file batches have an explicit all-or-nothing or partial-success policy.
- Splitter/Aggregator does not lose items when a row is filtered/rejected.
- `DirectChannel`/`ExecutorChannel` is chosen based on latency, ordering, and backpressure.
- Input size, queues, pools, parser resources, and per-source event rates are bounded.
- Logs exclude sensitive raw payloads; metrics exclude high-cardinality IDs.
- Tests cover happy paths, invalid amounts, wrong statuses, wrong sources, unknown schemas, duplicates, replays, tenant isolation, and schema upgrades.
- A runbook exists to trace issues from adapter through canonical output to downstream effects.

**Conclusion:** Normalizer brings multiple sources with **the same semantics but different formats** into a common representation. In Spring Integration, the pattern is cleanly realized as **Router → per-source Translator → canonical channel → common validation**. The greatest value lies not in renaming fields, but in **normalizing the semantics of currency, time, status, and identity**, and then protecting that contract with schema versioning, testing, error handling, idempotency, and monitoring. When designed properly, adding a new format does not force every downstream consumer to learn a new data language.

## References

- [Enterprise Integration Patterns — Normalizer](https://www.enterpriseintegrationpatterns.com/patterns/messaging/Normalizer.html): Router + Message Translators producing a unified format for semantically equivalent messages.
- [Enterprise Integration Patterns — Message Translator](https://www.enterpriseintegrationpatterns.com/patterns/messaging/MessageTranslator.html): transforming a message's structure and semantics into another structure.
- [Enterprise Integration Patterns — Content-Based Router](https://www.enterpriseintegrationpatterns.com/patterns/messaging/ContentBasedRouter.html): selecting a route based on message characteristics.
- [Spring Integration Reference — Routers](https://docs.spring.io/spring-integration/reference/router.html): routers, Java DSL, and default output channel.
- [Spring Integration Reference — Router Implementations](https://docs.spring.io/spring-integration/reference/router/implementations.html): PayloadTypeRouter and routing by Java class.
- [Spring Integration Reference — Transformer](https://docs.spring.io/spring-integration/reference/transformer.html): POJO/DSL transformers, null return restrictions, header propagation, and header filtering.
- [Spring Integration Reference — Message](https://docs.spring.io/spring-integration/reference/message.html): immutable Message, MessageHeaders, and MessageBuilder.
- [Spring Integration Reference — Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html): building IntegrationFlows and connecting Router/Transformer/Channel.
- [Spring Integration Reference — Splitter](https://docs.spring.io/spring-integration/reference/splitter.html): child messages, correlation, and sequence metadata.
- [Spring Integration Reference — Aggregator](https://docs.spring.io/spring-integration/reference/aggregator.html): group correlation, release, timeout, and partial results.
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): synchronous/asynchronous errors, errorChannel, and ErrorMessage.
- [Spring Integration Reference — Idempotent Receiver](https://docs.spring.io/spring-integration/reference/handler-advice/idempotent-receiver.html): deduplication support and limitations to note before side effects.
- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): DirectChannel, ExecutorChannel, and QueueChannel.
