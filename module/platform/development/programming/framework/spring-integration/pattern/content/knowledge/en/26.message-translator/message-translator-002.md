# Mapping Payload and Metadata

> **Chapter:** Message translator  
> **Module:** `SPRING_INTEGRATION_PATTERN` — learn how to implement Enterprise Integration Patterns with Spring Integration to build loosely coupled and extensible message flows. Practice Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation, while testing and monitoring processing branches. This lesson dives deep into **transforming both the payload and metadata of a message without violating the contract, losing correlation, or forwarding sensitive information unintentionally**.

## 1. Learning objectives

After this lesson, you will be able to:

1. Explain **Message Translator** in Enterprise Integration Patterns (EIP) as a format isolation boundary between two systems with different contracts.
2. Distinguish between **payload**, **message headers**, **transport metadata**, and **business metadata**; understand why all four cannot be copied indiscriminately.
3. Design a mapping contract for fields, data types, currency units, timestamps, schema versions, correlation headers, idempotency, and reply/error routing.
4. Write a Java 17 Message Translator that converts `Message<PartnerOrder>` into `Message<WarehouseCommand>` with explicitly created and validated headers.
5. Use Spring Integration Java DSL to integrate a Translator with `Service Activator`, `DirectChannel`, and `QueueChannel`, and understand the `.transform(...)` variant.
6. Analyze which metadata must be **preserved**, **renamed**, **derived**, **dropped**, or **recomputed** when crossing HTTP, Kafka, AMQP, JMS, and internal channels.
7. Distinguish mapping/validation errors from technical errors; preserve proper behavior for Gateway, Router, Splitter/Aggregator, retry, redelivery, and idempotent consumers.
8. Write unit/integration/contract tests verifying not only the payload, but also headers, authorization, source provenance, and error paths.

## 2. The problem: valid source message, unusable target message

A partner sends an order command in JSON:

~~~json
{
  "partnerOrderNo": "PO-901",
  "sku": " book-42 ",
  "quantityText": "003",
  "unitPriceMajor": "12.50",
  "currency": "usd",
  "requestedAt": "2026-11-21T15:00:00+07:00",
  "deliveryNote": "Deliver during business hours"
}
~~~

The source adapter has authenticated the sender and created an internal message with the following metadata:

~~~text
Payload: PartnerOrder(...)
Headers verified/issued by the system:
  trustedTenant        = shop-a
  trustedPartner       = partner-a
  sourceSchemaVersion  = partner-order-v1
  businessCorrelationId= ORD-901
  operationId          = CMD-901
  originalMediaType    = application/vnd.partner.order+json

Transport/internal-only headers:
  id, timestamp, replyChannel, errorChannel, ...
External headers not trusted by default:
  authorization, cookie, arbitrary trace IDs, ...
~~~

The warehouse service expects a canonical command:

~~~json
{
  "tenantId": "shop-a",
  "partnerId": "partner-a",
  "partnerOrderNo": "PO-901",
  "operationId": "CMD-901",
  "sku": "BOOK-42",
  "quantity": 3,
  "unitPriceMinor": 1250,
  "currency": "USD",
  "requestedAt": "2026-11-21T08:00:00Z",
  "deliveryNote": "Deliver during business hours"
}
~~~

It also needs **business correlation** to link the result back to the original order and a **stable operation ID** to prevent retries from duplicating business actions. However, the warehouse **must not** receive the HTTP client's Authorization header, a Java `replyChannel` object, or an original payload containing sensitive information in a header.

If a Transformer only converts `quantityText` into `quantity` while forgetting `operationId` and `businessCorrelationId`, the command might run successfully **yet fail to correlate the reply properly** or get processed twice on redelivery.

**A proper Message Translator must preserve the contract for both the payload and critical metadata.**

~~~mermaid
flowchart LR
    IN["Message<PartnerOrder>"] --> P["Payload mapper"]
    IN --> H["Header/metadata policy"]
    P --> V{"Validate target command"}
    H --> V
    V -->|"Valid"| OUT["Message<WarehouseCommand>"]
    V -->|"Invalid"| REJ["Typed mapping rejection"]
    OUT --> AD["Outbound adapter/header mapper"]
    AD --> W["Warehouse service"]
~~~

## 3. Message Translator in EIP

**Message Translator** is a form of **Message Transformation**: converting a message from a format system A understands into a format system B understands. It serves as an anti-corruption/decoupling layer when each system defines different fields, headers, serialization, and semantics.

In Spring Integration, this can be implemented with:

- `.transform(...)` / Message Transformer when the primary goal is transforming the payload or message representation.
- `.handle(...)` with a service returning `Message<?>` when you want to explicitly construct both the payload and headers.
- Header Enricher / Header Filter for dedicated metadata policies.
- Gateway/Adapter and header mappers to translate metadata at HTTP, AMQP/JMS/Kafka boundaries.
- Router to pick the right Translator when multiple source message types exist.

### 3.1. Comparison with easily confused patterns

| Component | Goal | Example |
| --- | --- | --- |
| **Message Translator** | Convert message contract A → B | Partner order + headers → warehouse command + headers |
| **Transformer** | Mechanism/endpoint changing data representation | JSON `String` → Java record |
| **Normalizer** | Multiple source formats → one common format | A/B/C translators → `CanonicalOrder` |
| **Header Enricher** | Add/enrich required headers | Add `businessCorrelationId` |
| **Header Filter** | Remove disallowed metadata | Strip `authorization` before broker |
| **Content Enricher** | Enrich info from an external source | Look up customer code by account ID |
| **Content-Based Router** | Choose branch based on metadata/payload | Currency USD → international channel |
| **Claim Check** | Replace large payload with a reference | 50 MiB file → object key |
| **Idempotent Receiver** | Block duplicate side effects of the same operation | Redelivery of `CMD-901` does not reserve stock twice |

**Do not equate a Message Translator with a JSON serializer.** A serializer converts bytes to a DTO; a Translator must also understand **field semantics and the metadata the target expects**, such as money in minor units, source identity, reply correlation, and tenant boundaries.

## 4. Four layers of information in a message

~~~text
┌────────────────────────────────────────────┐
│ Message                                   │
│  Payload: business content                │
│     order, item, amount, timestamp         │
│                                            │
│  Business metadata / headers              │
│     correlationId, operationId, tenant     │
│                                            │
│  Integration control headers              │
│     replyChannel, errorChannel, sequence   │
│                                            │
│  Transport-specific metadata              │
│     HTTP headers, JMS delivery headers,    │
│     Kafka topic/partition/offset, AMQP...  │
└────────────────────────────────────────────┘
~~~

### 4.1. Payload

Contains the business data needed by the target handler: order ID, SKU, quantity, amount, timestamps. The Translator may rename fields and convert types, structures, units, and enums **according to an explicit contract**.

### 4.2. Business metadata

Governance info for the business interaction, such as `operationId`, `businessCorrelationId`, source partner, or schema version. It may reside in the payload, headers, or both per the contract. **Never assume metadata is trustworthy merely because it is in a header.**

### 4.3. Integration-control headers

Headers such as `replyChannel`, `errorChannel`, and `sequenceNumber` have meaning within a specific Spring Integration flow. Some are **objects that exist only in the JVM** or are only useful to an Aggregator/Resequencer. When crossing to another system, they must be mapped into an **appropriate transport format**, never blindly serializing a `MessageChannel`.

### 4.4. Transport metadata

Metadata such as Kafka offset, AMQP delivery tag, JMS delivery count, or HTTP Authorization are not stable business identities. They are usually owned by the adapter/broker, can change during retries/redeliveries, and have provider-specific mapping limits.

## 5. Mapping contract: deciding for every field and header

Before writing the Translator, draft a **source → target** table along with validation and failure policies.

### 5.1. Payload mapping

| Source | Target | Rule | On failure |
| --- | --- | --- | --- |
| `partnerOrderNo` | `partnerOrderNo` | Preserve case-sensitive ID | Reject if blank |
| `sku` | `sku` | Trim + uppercase **if SKU contract is case-insensitive** | Reject if invalid characters |
| `quantityText` | `quantity` | Parse exact int, 1..500 | Reject; do not default to 1 |
| `unitPriceMajor` | `unitPriceMinor` | `BigDecimal` USD × 100 exact | Reject if rounding/overflow occurs |
| `currency` | `currency` | Normalize `USD`, check allowlist | Reject unsupported |
| `requestedAt` | `requestedAt` | Offset timestamp → `Instant` | Reject if offset is missing |
| `deliveryNote` | `deliveryNote` | Keep content within limits/policy | Reject if too long or sanitize for context |
| Trusted `tenantId` | `tenantId` | Take from authenticated principal/context | Security reject |
| Trusted `partnerId` | `partnerId` | Take from adapter/server registry | Security reject |
| Trusted `operationId` | `operationId` | Preserve across retry/redelivery | Reject if missing |

### 5.2. Metadata/header mapping

| Header/source | Output policy | Explanation |
| --- | --- | --- |
| `businessCorrelationId` | **Preserve** after validation | Reply/audit tied to business request |
| `operationId` | **Preserve** and verify against target payload | Stable idempotency key |
| `trustedTenant` | **Derive** into command's `tenantId` | Do not accept client-declared namespace |
| `trustedPartner` | **Derive** into `partnerId` | Authenticated partner scope |
| `sourceSchemaVersion` | **Preserve** for audit | Identifies which decoder/mapping was used |
| `targetSchemaVersion` | **Generate** | Output contract, e.g., `warehouse-command-v1` |
| `originalMediaType` | **Preserve under new name** if needed | Prevents old content-type from misdescribing new payload |
| `contentType` | **Recompute** during outbound serialization | Java record in JVM is not automatically JSON bytes |
| `replyChannel` / `errorChannel` | **Conditionally preserve** within the same JVM trusted flow | Do not send Java channel objects over a broker |
| `sequenceNumber` / `sequenceSize` | **Conditionally preserve** if downstream needs group semantics | Do not apply one group to a new execution |
| `traceparent` | **Validate/delegate to tracer** | Do not copy client-declared strings as authority |
| `authorization`, `cookie`, raw JWT | **Drop** at external boundary | Secrets of one trust boundary do not belong at the target |
| `rawPayload`, `debugDump` | **Drop/Claim Check** | Avoid leaking sensitive data or oversized payloads |
| `MessageHeaders.ID`, timestamp | **Recreate or framework-managed** | A new envelope ID is not an operation ID |
| Kafka offset, AMQP deliveryTag | **Do not treat as business identity** | Per-delivery metadata only |

### 5.3. Five core actions

- **Preserve:** keep metadata that retains the same meaning in the new message.
- **Rename:** keep the value but rename the key to match the target contract.
- **Derive:** compute the target value from trusted sources or business rules.
- **Drop:** remove data that is unauthorized, unnecessary, or should not cross the boundary.
- **Recompute:** regenerate content type, envelope ID, timestamp, or headers whose meaning changes after transformation.

**Rule:** A header omitted from the contract is **not automatically** permitted to travel to another consumer just because `MessageBuilder.copyHeaders(...)` makes it convenient.

## 6. Metadata is not proof of authentication

An HTTP client could send:

~~~http
X-Tenant-Id: shop-b
X-Operation-Id: CMD-901
X-Business-Correlation-Id: ORD-901
Authorization: Bearer ...
~~~

If the adapter turns those fields directly into `trustedTenant` and lets the Translator use it **without authentication**, a client can submit commands into another tenant's namespace.

**Valid boundary:**

~~~text
Untrusted transport headers
    |
    v
HTTP/JMS/Kafka adapter
  -> Authenticate producer/principal
  -> Authorize tenant, partner, schema version
  -> Validate operation/correlation IDs
  -> Strip/disallow untrusted control headers
  -> Create TrustedSourceContext / trusted headers
    |
    v
Message Translator
~~~

The header name `trustedTenant` in the example merely **denotes an internal contract**; the name itself does not make a string trustworthy. The adapter, security filter, or ingress gateway must guarantee provenance and prevent clients from spoofing it.

### 6.1. Correlation and idempotency are two distinct responsibilities

Example:

~~~text
businessCorrelationId = ORD-901
operationId           = CMD-901
sourceSchemaVersion   = partner-order-v1
executionId           = RUN-901-A
MessageHeaders.ID     = random message envelope ID
~~~

- **Business correlation** links messages belonging to the same order or request.
- **Operation ID** identifies a command with side effects; must stay constant across all retries of that command.
- **Execution ID** groups one workflow/Scatter-Gather run; may change upon reprocessing.
- **Message ID** of the envelope may change whenever a message is reconstructed.
- **Transport delivery metadata** belongs to a single attempt, not a deduplication key.

Do not use a broad `correlationId` to block all commands on the same order; nor use `MessageHeaders.ID` as an idempotency key when the broker can redeliver under a new envelope.

## 7. Payload mapping: changing representation without arbitrarily changing meaning

For example, the price `"12.50" USD` must become `1250` minor units if the target contract uses cents. Conditions to verify:

1. Currency must exist in the contract with a defined scale.
2. Major unit price must be parsed accurately (`BigDecimal`), never via `double`.
3. Conversion to minor units must be **exact**, never silently truncated.
4. Ranges, quantities, and totals must not overflow.
5. Timestamps must include an offset or follow an explicit timezone policy.
6. Enums and SKUs must be normalized **per the field's contract**, not by habitually uppercasing every string.

### 7.1. Difference between representation and domain validation

| Input | Translator | Validator/domain |
| --- | --- | --- |
| `quantityText="003"` | Parses 3 | Valid if 1..500 |
| `quantityText="abc"` | Parse failure | No canonical DTO created |
| `quantityText="-2"` | Parses integer | Reject negative number |
| `unitPriceMajor="12.345"` | Has fractional cent | Reject without a rounding policy |
| `currency="usd"` | Normalize to USD | Valid |
| `currency="xyz"` | Unknown scale/contract | Reject unsupported |
| Timestamp without offset | Cannot safely derive instant | Reject or use versioned policy |

Do not turn parser errors into `0` or a default enum just to keep moving forward. If the target requires a valid order quantity, **do not let bad data reach the Inventory Gateway** just because the Translator managed to construct a DTO.

## 8. Java 17: source DTO and target command

The following examples use **Java 17**, Spring Messaging, and Spring Integration. Each record/class can be placed in its corresponding file within the same package.

~~~java
import java.time.Instant;

record PartnerOrder(
    String partnerOrderNo,
    String sku,
    String quantityText,
    String unitPriceMajor,
    String currency,
    String requestedAt,
    String deliveryNote
) {}

record WarehouseCommand(
    String tenantId,
    String partnerId,
    String partnerOrderNo,
    String operationId,
    String sku,
    int quantity,
    long unitPriceMinor,
    String currency,
    Instant requestedAt,
    String deliveryNote
) {}
~~~

To stay simple and focused on mapping, `WarehouseCommand` contains the data needed by the warehouse; `operationId` and namespace live in the payload **because the target system needs to check idempotency**. Headers are still needed for correlation/routing inside the integration flow.

### 8.1. Coded mapping failure

~~~java
final class TranslationFailure extends RuntimeException {
    private final String code;

    TranslationFailure(String code) {
        super(code);
        this.code = code;
    }

    TranslationFailure(String code, Throwable cause) {
        super(code, cause);
        this.code = code;
    }

    String code() {
        return code;
    }
}
~~~

This exception represents **data that cannot be converted under the contract**. It must not be used to mask `IOException`, `DataAccessException`, or random infrastructure failures.

### 8.2. Do not catch every exception as "invalid input"

~~~java
// WRONG: downstream timeout is treated as an invalid payload.
try {
    return remoteService.translateAndSave(order);
} catch (Exception ex) {
    throw new TranslationFailure("INVALID_ORDER");
}
~~~

Mapping should be as computationally pure as possible; side effects belong after the Translator, ensuring parse retries never accidentally re-invoke payment or warehouse APIs.

## 9. Writing a Translator for both payload and metadata

The `PartnerOrderTranslator` example receives the full `Message<PartnerOrder>`, not just the payload, to enforce the **header contract** alongside business mapping.

**Precondition:** Ingress has already authenticated and set `trustedTenant`, `trustedPartner`, `sourceSchemaVersion`, `businessCorrelationId`, and `operationId`. External clients have no authority to set or overwrite these headers.

~~~java
import java.math.BigDecimal;
import java.time.DateTimeException;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.util.Locale;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;

final class PartnerOrderTranslator {

    public Message<WarehouseCommand> translate(
            Message<PartnerOrder> inbound) {
        PartnerOrder raw = inbound.getPayload();
        MessageHeaders headers = inbound.getHeaders();

        // Required contract headers provided by the trusted adapter.
        String tenant = required(
            headers.get("trustedTenant", String.class),
            "TENANT_CONTEXT_MISSING");
        String partner = required(
            headers.get("trustedPartner", String.class),
            "PARTNER_CONTEXT_MISSING");
        String sourceVersion = required(
            headers.get("sourceSchemaVersion", String.class),
            "SOURCE_VERSION_MISSING");
        String operationId = required(
            headers.get("operationId", String.class),
            "OPERATION_ID_MISSING");
        String correlationId = required(
            headers.get("businessCorrelationId", String.class),
            "CORRELATION_ID_MISSING");

        if (!"partner-order-v1".equals(sourceVersion)) {
            throw new TranslationFailure(
                "UNSUPPORTED_SOURCE_SCHEMA");
        }
        if (!"partner-a".equals(partner)) {
            throw new TranslationFailure(
                "UNEXPECTED_SOURCE_PARTNER");
        }

        // Payload mapping, do not regenerate commandId on each attempt.
        String currency = canonicalCurrency(raw.currency());
        int quantity = parseQuantity(raw.quantityText());
        long unitPriceMinor = parseMinorPrice(
            raw.unitPriceMajor(), currency);

        String note = raw.deliveryNote();
        if (note != null && note.length() > 500) {
            throw new TranslationFailure(
                "DELIVERY_NOTE_TOO_LONG");
        }

        WarehouseCommand command = new WarehouseCommand(
            tenant,
            partner,
            required(raw.partnerOrderNo(), "ORDER_ID_MISSING"),
            operationId,
            canonicalSku(raw.sku()),
            quantity,
            unitPriceMinor,
            currency,
            parseRequestedAt(raw.requestedAt()),
            note
        );

        // Do not copyHeaders(...) from untrusted input.
        MessageBuilder<WarehouseCommand> result =
            MessageBuilder.withPayload(command)
                .setHeader(
                    "businessCorrelationId", correlationId)
                .setHeader("operationId", operationId)
                .setHeader("tenantId", tenant)
                .setHeader("sourceSystem", partner)
                .setHeader(
                    "sourceSchemaVersion", sourceVersion)
                .setHeader(
                    "targetSchemaVersion",
                    "warehouse-command-v1");

        // When the contract needs original MIME provenance, use a separate header name.
        String originalMediaType = headers.get(
            "originalMediaType", String.class);
        if (originalMediaType != null) {
            result.setHeader(
                "originalMediaType", originalMediaType);
        }

        // Only supports internal routing within the same JVM.
        // Do not serialize channel objects over an external broker.
        Object reply = headers.getReplyChannel();
        if (reply instanceof MessageChannel localReplyChannel) {
            result.setReplyChannel(localReplyChannel);
        }
        Object error = headers.getErrorChannel();
        if (error instanceof MessageChannel localErrorChannel) {
            result.setErrorChannel(localErrorChannel);
        }

        return result.build();
    }

    private static String required(String value, String code) {
        if (value == null || value.isBlank()) {
            throw new TranslationFailure(code);
        }
        return value;
    }

    private static String canonicalSku(String value) {
        String sku = required(
            value, "SKU_MISSING")
            .strip().toUpperCase(Locale.ROOT);

        if (!sku.matches("[A-Z0-9-]{1,64}")) {
            throw new TranslationFailure("SKU_INVALID");
        }
        return sku;
    }

    private static String canonicalCurrency(String raw) {
        String currency = required(
            raw, "CURRENCY_MISSING")
            .strip().toUpperCase(Locale.ROOT);

        if (!"USD".equals(currency)) {
            // Demo only supports USD with 2 minor units.
            throw new TranslationFailure(
                "UNSUPPORTED_CURRENCY");
        }
        return currency;
    }

    private static int parseQuantity(String raw) {
        try {
            int quantity = Integer.parseInt(
                required(raw, "QUANTITY_MISSING").strip());
            if (quantity < 1 || quantity > 500) {
                throw new TranslationFailure(
                    "QUANTITY_OUT_OF_RANGE");
            }
            return quantity;
        } catch (NumberFormatException ex) {
            throw new TranslationFailure(
                "QUANTITY_NOT_INTEGER", ex);
        }
    }

    private static long parseMinorPrice(
            String raw, String currency) {
        if (!"USD".equals(currency)) {
            throw new TranslationFailure(
                "UNSUPPORTED_CURRENCY");
        }
        try {
            long minor = new BigDecimal(
                required(raw, "PRICE_MISSING").strip())
                .movePointRight(2)
                .longValueExact();

            if (minor < 0 || minor > 1_000_000_000L) {
                throw new TranslationFailure(
                    "PRICE_OUT_OF_RANGE");
            }
            return minor;
        } catch (NumberFormatException | ArithmeticException ex) {
            throw new TranslationFailure(
                "NON_EXACT_PRICE", ex);
        }
    }

    private static Instant parseRequestedAt(String raw) {
        try {
            return OffsetDateTime.parse(
                required(raw, "REQUESTED_AT_MISSING").strip())
                .toInstant();
        } catch (DateTimeException ex) {
            throw new TranslationFailure(
                "INVALID_REQUESTED_AT", ex);
        }
    }
}
~~~

### 9.1. What did the Translator do?

1. Read the payload and the headers **provided by a trusted adapter**.
2. Rejected unsupported schemas/partners.
3. Converted quantity, money, and timestamp using exact types.
4. Created `WarehouseCommand` containing a stable business operation ID.
5. Built a new message with **allowlisted metadata**: correlation, operation, source, versions, tenant.
6. Preserved `replyChannel`/`errorChannel` only if they are valid internal `MessageChannel` objects.
7. Excluded `authorization`, `cookie`, raw JSON, and delivery counters from the new message.

**Example limitations:** `required(...)` checks for non-blank strings without enforcing length limits on every ID; production ingress/schema validators must enforce length, charset, and authorization per the contract. Uppercasing `canonicalSku` is only valid if **source SKUs are case-insensitive**. The 1 billion `unitPriceMinor` cap and USD-only rule are illustrative choices.

### 9.2. Do not regenerate `operationId` inside the Translator

If `translate(...)` calls `UUID.randomUUID()` to generate a new command ID, every broker redelivery creates a **new business operation** and bypasses downstream idempotency.

~~~text
Delivery #1:
  operationId=CMD-901 -> ReserveStock once

Redelivery:
  operationId=CMD-901 -> return existing outcome

Forbidden:
  redelivery -> operationId=random-new -> ReserveStock again
~~~

The ID must be issued **once** by the producer/business source, or by trusted ingress and durably persisted before retries can occur. `MessageHeaders.ID` is not a stable substitute.

### 9.3. Should `replyChannel` and `errorChannel` be kept?

Within the **same JVM**, a Gateway waiting for a reply may need `replyChannel` and error routing to remain intact. The sample code preserves them only when they are internal `MessageChannel` objects provided by the application.

At an **outbound broker/HTTP boundary**, `MessageChannel` objects must not be serialized. Convert them into a **reply destination/correlation per the transport contract**, or use an outbound header mapper to strip those headers. If clients can declare channel names or routing headers themselves, never preserve them without allowlist and authorization checks.

### 9.4. Why not call `copyHeaders(...)` for all inputs?

If you do:

~~~java
// DO NOT do this at a trust boundary:
Message<WarehouseCommand> unsafe = MessageBuilder
    .withPayload(command)
    .copyHeaders(inbound.getHeaders())
    .build();
~~~

You can inadvertently forward `Authorization`, `Cookie`, `rawPayload`, an outdated original MIME type, a spoofed tenant header, or delivery metadata that does not belong to the target consumer.

**Operational note:** Beyond Translator code, some endpoints/adapters can automatically propagate headers via framework defaults. Therefore, **header policies on outbound adapters/mappers and contract tests on real messages** remain essential. Constructing a Message with an allowlist **is not sole proof** that every boundary stripped forbidden headers.

## 10. Spring Integration Java DSL for the Translator

There are two common ways to use Spring Integration:

- `.transform(...)` when conversion logic mainly targets the **payload**.
- `.handle(service, "method")` with a method accepting/returning `Message<?>` to explicitly express the contract for both payload and headers, as in this lesson.

### 10.1. Unidirectional flow example

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
class MessageTranslatorFlowConfiguration {

    @Bean("translator.partner.in")
    DirectChannel inbound() {
        return new DirectChannel();
    }

    @Bean("translator.warehouse.out")
    QueueChannel outbound() {
        // Observation point for integration tests,
        // production can replace this with a broker adapter.
        return new QueueChannel();
    }

    @Bean
    PartnerOrderTranslator partnerOrderTranslator() {
        return new PartnerOrderTranslator();
    }

    @Bean
    IntegrationFlow mapPartnerOrder(
            PartnerOrderTranslator translator) {
        return IntegrationFlow
            .from("translator.partner.in")
            .handle(translator, "translate")
            // Add a filter layer for forbidden headers at the
            // flow boundary; external adapters still need an allowlist.
            .headerFilter(
                "authorization", "cookie", "rawPayload")
            .channel("translator.warehouse.out")
            .get();
    }
}
~~~

In this example, `DirectChannel` dispatches synchronously and `QueueChannel` is an **in-memory** queue for testing. It provides no durability, ACKs, or transactions across a real broker. When moving to Kafka/JMS/AMQP, verify the adapter's serialization, header mapper, offset/ACK, and retry policies accordingly.

### 10.2. Variant when only transforming the payload

If both payload and headers of the input belong to the **same trusted domain**, you can transform only the payload using a Transformer:

~~~java
IntegrationFlow payloadOnly(
        java.util.function.Function<PartnerOrder, WarehouseCommand> mapper) {
    return IntegrationFlow.from("partner.payload.in")
        .transform(PartnerOrder.class, mapper::apply)
        .channel("warehouse.commands.out")
        .get();
}
~~~

This is an abbreviated snippet; mappers and channels must be supplied when integrating. **Do not assume** a payload-only Transformer automatically enforces header drop/rename policies across a trust boundary. If schema and metadata change together, include explicit header handling steps and verification tests.

### 10.3. Note on content type

If `PartnerOrder` was deserialized from JSON, the input may have `contentType=application/json`. After the Translator, the payload inside the JVM is a Java `WarehouseCommand`, **not necessarily JSON bytes**. The outbound serializer determines the media type/encoding of the emitted message.

Keep them separate:

~~~text
originalMediaType = application/vnd.partner.order+json
targetSchemaVersion = warehouse-command-v1

Transport serialization:
  WarehouseCommand -> JSON bytes
  outbound Content-Type = application/json
  encoding = UTF-8 (contract)
~~~

Do not keep the original MIME type by default once the output has changed representation. Do not leave `contentType=application/pdf` on a `Message<ClaimReference>` when the payload is now a metadata DTO.

## 11. Correlation and reply with a Gateway

In request–reply flows, messages passing through a Gateway must retain the ability to reach the right reply recipient.

~~~mermaid
sequenceDiagram
    participant P as Partner Gateway
    participant T as Translator
    participant W as Warehouse endpoint
    P->>T: PartnerOrder + trusted correlation + reply route
    T->>W: WarehouseCommand + same business operation
    W-->>T: WarehouseReceipt + operationId
    T-->>P: PartnerOrderReply + correlation
~~~

A response returning to the source typically needs a **reverse Translator**:

| Warehouse response | Partner reply | Rule |
| --- | --- | --- |
| `operationId` | `requestId` | Map according to verified contract |
| `reservationStatus` | `status` | Explicit enum mapping, never unknown→SUCCESS |
| `warehouseOrderId` | `fulfillmentReference` | Preserve identity |
| `businessCorrelationId` | `businessCorrelationId` | Link request/reply |
| `internalErrorDetails` | Do not send externally | Redact/map to public error code |

Having only a request translator **does not automatically** translate the response back into the partner's contract. If the Gateway uses an external broker, you need a reply queue/topic, a stable correlation key, timeouts, and handling for late replies.

### 11.1. Internal `replyChannel` vs. reply address

- Within the same JVM, `replyChannel` can be a `MessageChannel` object or equivalent Spring configuration.
- Over a broker, a reply address is typically a **queue/topic or transport identifier** with its own access control rules.
- A partner must not specify arbitrary reply destinations that cause internal data to be sent to unauthorized endpoints.
- If the Translator drops `replyChannel` when the Gateway expects a reply, the caller may time out even though the business handler succeeded.

### 11.2. A success response cannot be inferred from translation alone

Succeeding in translation only means the **target message was constructed**. It does not prove the warehouse received, committed, or replied to it. For asynchronously processed requests, return `ACCEPTED/PROCESSING/COMPLETED` per the contract, never "order completed" immediately after creating `WarehouseCommand`.

## 12. Metadata across Splitter, Aggregator, and Scatter-Gather

Suppose an order has three lines:

~~~text
executionId = RUN-901-A
businessCorrelationId = ORD-901

LINE-1 -> warehouse command -> reply
LINE-2 -> warehouse command -> reply
LINE-3 -> warehouse command -> reply
~~~

The Translator for each child needs to preserve sufficient context:

- `executionId` to group by **processing run**.
- `lineId` to identify a **unique child**.
- `operationId` or `(commandId,lineId,operationType)` to guard side effects.
- `sequenceNumber/sequenceSize` if the flow relies on them for group semantics.
- `businessCorrelationId` to trace back to the original order.

**Do not** replace every `correlationId` with a plain `orderId` if one order can have two concurrent executions. Nor treat a transport sequence number as a business ID.

### 12.1. Do not drop a child and hang the Aggregator

If a child with `quantity=-3` is rejected by the Translator and silently dropped by a Filter, an Aggregator waiting for three replies will only receive two. Produce a **typed child outcome** `REJECTED` that feeds into the batch result, or define clear release/timeout/partial policies.

### 12.2. Duplicates must not count as new children

Redelivery may produce two `WarehouseReceipt` messages for LINE-2. Group release must rely on **unique child IDs/expected set**, not simply `group.size()`. If the group is already complete and a duplicate reply arrives later, use closed-execution state/tombstones so a new group is not spawned and a second final result emitted.

### 12.3. Correlation does not replace idempotency

Two messages sharing a correlation ID only indicate relatedness. The backend must still enforce a durable operation ID and transactions/idempotency when reserving stock, charging payments, or issuing invoices. A Transformer that preserves correlation while regenerating the operation ID on each retry can still cause double charges.

## 13. Unit tests: correct payload and intact, safe metadata

A Translator must be tested in two directions:

1. Which fields/headers **must exist** in the output.
2. Which fields/headers **must not exist** in the output.

Asserting only `quantity=3` will miss a lost `operationId` or a leaked `authorization` header when emitting messages.

### 13.1. Fixture containing both valid metadata and data to strip

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

final class TranslationFixture {
    private TranslationFixture() {}

    static Message<PartnerOrder> validMessage() {
        PartnerOrder body = new PartnerOrder(
            "PO-901",
            " book-42 ",
            "003",
            "12.50",
            "usd",
            "2026-11-21T15:00:00+07:00",
            "Deliver during business hours");

        return MessageBuilder.withPayload(body)
            .setHeader("trustedTenant", "shop-a")
            .setHeader("trustedPartner", "partner-a")
            .setHeader(
                "sourceSchemaVersion", "partner-order-v1")
            .setHeader("businessCorrelationId", "ORD-901")
            .setHeader("operationId", "CMD-901")
            .setHeader(
                "originalMediaType",
                "application/vnd.partner.order+json")
            // Simulate a header that must not be forwarded externally.
            .setHeader("authorization", "Bearer demo-secret")
            .setHeader("rawPayload", "private-demo-data")
            .build();
    }
}
~~~

The fixture sets `trustedTenant` directly **only for unit tests**; this does not replace authentication in a real inbound adapter.

### 13.2. JUnit 5: verifying business payload and critical headers

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class PartnerOrderTranslatorTest {

    private final PartnerOrderTranslator translator =
        new PartnerOrderTranslator();

    @Test
    void mapsPayloadAndMandatoryMetadata() {
        Message<WarehouseCommand> out =
            translator.translate(
                TranslationFixture.validMessage());

        WarehouseCommand command = out.getPayload();

        assertEquals("shop-a", command.tenantId());
        assertEquals("partner-a", command.partnerId());
        assertEquals("PO-901", command.partnerOrderNo());
        assertEquals("CMD-901", command.operationId());
        assertEquals("BOOK-42", command.sku());
        assertEquals(3, command.quantity());
        assertEquals(1250L, command.unitPriceMinor());
        assertEquals("USD", command.currency());
        assertEquals(
            Instant.parse("2026-11-21T08:00:00Z"),
            command.requestedAt());

        assertEquals("ORD-901",
            out.getHeaders().get("businessCorrelationId"));
        assertEquals("CMD-901",
            out.getHeaders().get("operationId"));
        assertEquals("warehouse-command-v1",
            out.getHeaders().get("targetSchemaVersion"));
        assertEquals("partner-order-v1",
            out.getHeaders().get("sourceSchemaVersion"));
    }

    @Test
    void doesNotCopySensitiveOrUnmappedHeaders() {
        Message<WarehouseCommand> out =
            translator.translate(
                TranslationFixture.validMessage());

        assertNull(out.getHeaders().get("authorization"));
        assertNull(out.getHeaders().get("cookie"));
        assertNull(out.getHeaders().get("rawPayload"));
        assertNull(out.getHeaders().get("trustedTenant"));
        assertEquals("shop-a", out.getPayload().tenantId());
    }

    @Test
    void refusesMissingOperationIdInsteadOfRegenerating() {
        Message<PartnerOrder> missing = MessageBuilder
            .fromMessage(TranslationFixture.validMessage())
            .removeHeader("operationId")
            .build();

        TranslationFailure error = assertThrows(
            TranslationFailure.class,
            () -> translator.translate(missing));

        assertEquals("OPERATION_ID_MISSING", error.code());
    }

    @Test
    void refusesFractionalCentWithoutRoundingPolicy() {
        PartnerOrder old =
            TranslationFixture.validMessage().getPayload();

        PartnerOrder bad = new PartnerOrder(
            old.partnerOrderNo(), old.sku(),
            old.quantityText(), "12.345",
            old.currency(), old.requestedAt(),
            old.deliveryNote());

        Message<PartnerOrder> input = MessageBuilder
            .fromMessage(TranslationFixture.validMessage())
            .setPayload(bad)
            .build();

        TranslationFailure error = assertThrows(
            TranslationFailure.class,
            () -> translator.translate(input));

        assertEquals("NON_EXACT_PRICE", error.code());
    }

    @Test
    void refusesUnsupportedSchemaVersion() {
        Message<PartnerOrder> input = MessageBuilder
            .fromMessage(TranslationFixture.validMessage())
            .setHeader(
                "sourceSchemaVersion", "partner-order-v99")
            .build();

        TranslationFailure error = assertThrows(
            TranslationFailure.class,
            () -> translator.translate(input));

        assertEquals("UNSUPPORTED_SOURCE_SCHEMA", error.code());
    }

    @Test
    void refusesTimestampWithoutOffset() {
        PartnerOrder old =
            TranslationFixture.validMessage().getPayload();

        PartnerOrder bad = new PartnerOrder(
            old.partnerOrderNo(), old.sku(),
            old.quantityText(), old.unitPriceMajor(),
            old.currency(),
            "2026-11-21T15:00:00",
            old.deliveryNote());

        Message<PartnerOrder> input = MessageBuilder
            .fromMessage(TranslationFixture.validMessage())
            .setPayload(bad)
            .build();

        TranslationFailure error = assertThrows(
            TranslationFailure.class,
            () -> translator.translate(input));

        assertEquals("INVALID_REQUESTED_AT", error.code());
    }
}
~~~

### 13.3. Header and payload must not contradict each other

If a source contract carries an operation ID in **both** the payload and a header:

~~~text
payload.operationId = CMD-901
header.operationId  = CMD-902
~~~

Do not silently pick one side. The rule is to designate **one authenticated source of truth** at ingress, compare duplicates per contract, and reject with `OPERATION_ID_CONFLICT` if they differ. Never generate a new ID during retry to "fix" it.

The lesson's `PartnerOrder` example does not carry an operation ID; the trusted adapter issues or recovers `operationId` from a command registry, and the Translator populates it into `WarehouseCommand`.

## 14. Integration test: channels and header policy together

Using `MessageTranslatorFlowConfiguration` from section 10, the test observes the Translator handler, Header Filter, and output channel.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(MessageTranslatorFlowConfiguration.class)
@DirtiesContext(
    classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class MessageTranslatorFlowTest {

    @Autowired @Qualifier("translator.partner.in")
    MessageChannel input;

    @Autowired @Qualifier("translator.warehouse.out")
    PollableChannel output;

    @Test
    void emitsTargetCommandWithValidAndSafeHeaders() {
        assertTrue(input.send(
            TranslationFixture.validMessage()));

        Message<?> translated = output.receive(1000);
        assertNotNull(translated);
        assertInstanceOf(
            WarehouseCommand.class,
            translated.getPayload());

        WarehouseCommand command =
            (WarehouseCommand) translated.getPayload();

        assertEquals(3, command.quantity());
        assertEquals(1250L, command.unitPriceMinor());
        assertEquals("CMD-901", command.operationId());
        assertEquals("ORD-901",
            translated.getHeaders().get(
                "businessCorrelationId"));

        assertNull(
            translated.getHeaders().get("authorization"));
        assertNull(
            translated.getHeaders().get("rawPayload"));
        assertNull(output.receive(0),
            "One input must yield one target message");
    }
}
~~~

**Limitation:** this is an **in-JVM** integration test with no HTTP authentication, external warehouse, JMS/Kafka/AMQP provider, or outbox. With an async executor/broker, `receive(0)` is insufficient to prove "never emitted"; use a bounded await and verify business side effects.

### 14.1. Contract tests to add

- Gateway request–reply preserves local reply routes and timeout semantics.
- HTTP ingress strips spoofed tenant/source/correlation headers before the Translator.
- Broker adapter emits only **allowed headers** after serialization.
- Kafka/JMS/AMQP round-trip preserves exact types for `operationId` and `businessCorrelationId`.
- Redelivery creates a new envelope while keeping the operation ID and business action unchanged.
- Missing required metadata does not generate a bogus `WarehouseCommand`.
- Unknown schemas or unsupported currencies route clearly to error/quarantine.
- Tracing does not create high-cardinality metric labels.
- Two tenants with the same `partnerOrderNo` are never merged into one operation.
- Sensitive source fields/PII are not reflected into outbound headers.

## 15. Mapping metadata across HTTP, AMQP, JMS, and Kafka

There is no single header frame used verbatim across all transports. Each adapter has different size limits, encodings, provider-managed fields, and interaction rules.

| Boundary | Risk | Must verify |
| --- | --- | --- |
| HTTP inbound | Client spoofs tenant/operation via custom header | Principal, signature, allowlist |
| HTTP outbound | Accidentally forwarding token/cookie | Only contract headers emitted |
| AMQP | Reply-to, correlation, retry/DLX headers have specific semantics | Header mapper and redelivery |
| JMS | `JMSCorrelationID`, `JMSReplyTo`, provider headers | Request–reply, type serialization |
| Kafka | Record key, partition/offset, and typed headers | Correlation across retry topics/rebalances |
| Internal channel | `replyChannel` is a Java object/bean name | Never serialize objects externally |
| CloudEvents | `id/source/type/subject` form an event envelope | Do not confuse event ID with business command |

### 15.1. Kafka key differs from business operation ID

~~~text
Kafka record key:       tenantId + orderId (partitioning)
Business operation ID:  CMD-901 (idempotency)
Business correlation:   ORD-901
Kafka offset:           record/delivery position
~~~

A record can be republished to a new offset/topic; if deduplicating by offset, the same business command will be treated as a brand-new command. Kafka transactions have their own scope and **do not roll back an external Warehouse HTTP API**.

### 15.2. `JMSCorrelationID` differs from `MessageHeaders.ID`

JMS `JMSCorrelationID` supports correlation at the JMS protocol level. Spring `MessageHeaders.ID` is the envelope ID. A business operation ID can be mapped onto JMS correlation per the contract **if the domain chooses so**, but they are not naturally identical.

### 15.3. Do not convert arbitrary Java objects into HTTP headers

HTTP headers are typically text; a Spring message header can be a `MessageChannel`, `UUID`, or application object. The outbound mapper must select a fixed representation, enforce length limits, handle encoding, and never emit internal objects or security state unintentionally.

### 15.4. Allowlist policy at the outbound adapter

~~~text
Allowed:
  operationId
  businessCorrelationId
  targetSchemaVersion
  sourceSystem (if needed)

Denied:
  authorization
  cookie
  rawPayload
  replyChannel (Java object)
  errorChannel (Java object)
  internalPrincipal
  debugException
  arbitrary headers not in contract
~~~

**Inspect data on the wire** in contract tests, not just `PartnerOrderTranslator.translate(...)`. Some endpoints may propagate headers through framework defaults.

## 16. Header propagation has no single default rule for all endpoints

Spring Integration provides Transformers, Service Activators, Header Enrichers, Header Filters, and outbound adapters, each with different message-creation and header-propagation behaviors.

Never assume that:

- Every Transformer always preserves every header.
- A Service Activator returning `Message<?>` suffices to remove all input headers.
- `MessageHeaders.ID` will stay constant.
- The original content type still describes the payload after transformation.
- `replyChannel`/`errorChannel` can be serialized over Kafka/JMS.
- A header named `trustedTenant` is guaranteed to be authenticated.

### 16.1. Defense across boundaries

~~~mermaid
flowchart LR
    U["Untrusted input"] --> I["Ingress auth + strip/validate"]
    I --> T["Translator: payload + known metadata"]
    T --> A["Outbound adapter allowlist"]
    A --> B["Broker/remote service"]
    B --> R["Receiver: verify source + schema + auth"]
~~~

This is not wasted duplicate effort: an intermediate endpoint added later might introduce headers, so the final adapter must still act as a strict enforcement gate.

## 17. Retry/redelivery: Translator must keep business identity stable

Typical failure window:

~~~text
PartnerOrder (operationId=CMD-901)
    -> Translator -> WarehouseCommand
    -> Warehouse commits reservation
    -> Network ACK lost
    -> Local retry or broker redelivery
    -> Translator runs again
    -> WarehouseCommand must still have operationId=CMD-901
~~~

The Translator must not generate `UUID.randomUUID()`, assign `Instant.now()` as event time, recalculate prices with an unpinned exchange rate, or create a new correlation group on each attempt.

### 17.1. Correlation is not inherently idempotency

`businessCorrelationId=ORD-901` only links steps of an order. If the same order has CREATE, CANCEL, and AMEND commands, they cannot share a single correlation ID for deduplication. `operationId` must represent **one meaningful mutation**.

Even when the Translator preserves the operation ID, the **Warehouse** must still enforce an idempotent receiver / unique DB key or API idempotency token at the commit boundary, because brokers can redeliver.

### 17.2. Distinguishing terminal errors from technical errors

| Error | Retry with same input? | Handling |
| --- | --- | --- |
| Quantity unparseable | No | Typed translation rejection |
| Price requires disallowed rounding | No | Domain/representation rejection |
| Unsupported source schema | Not until decoder is upgraded | Quarantine |
| Missing trusted tenant/operation ID | Do not bypass | Security/contract error |
| Outbound broker timeout | Conditionally | Bounded retry + stable IDs |
| Warehouse HTTP 503 | Conditionally | Backoff/idempotent backend |
| Warehouse committed then response lost | Reconcile/retry same operation key | Do not emit a new command |
| Authorization denied | No | Reject per security policy |

Do not catch all exceptions and convert them into `TranslationFailure("INVALID_ORDER")`. Technical errors need an error channel or retry; terminal invalid inputs should not be retried infinitely by the broker.

## 18. Schema evolution and reproducing mapping during DLQ replay

Example:

~~~text
Partner schema v1: unitPriceMajor="12.50"
Partner schema v2: priceMinor=1250
Warehouse v1:      unitPriceMinor=1250
~~~

If a v2 message is read as v1, the price can increase 100-fold. Both `sourceSchemaVersion` (to select the decoder/translator) and `targetSchemaVersion` (to define the output contract) are needed.

A message sent to a DLQ 15 days ago might be replayed after new rules roll out. Choose explicitly:

1. Pin the old mapping policy version if historical results must be reproduced.
2. Re-translate under the new policy if permitted, with audit/migration tracking.
3. Reconcile if the old business mutation already committed.
4. Keep the **same operation ID** for the same business command.
5. Do not treat transport metadata changes as changes in business intent.

### 18.1. When lossy conversion is permitted

Byte-perfect equality is not always required. However, dropping fields, reducing timestamp precision, rounding numbers, or redacting data requires an explicit **loss policy**. You may emit a warning, reject, upgrade the schema, or securely retain the raw/provenance data (Claim Check). If an original signature was computed over raw bytes, reserialized canonical JSON cannot substitute for those raw bytes.

## 19. Observability for payload and metadata contracts

| Signal/metric | Purpose |
| --- | --- |
| `translator_received_total` by source/schema | Traffic and version skew |
| `translator_success_total` by target version | Track mapping throughput |
| `translation_rejected_total` by code | Schema drift/invalid values |
| `header_contract_missing_total` | Lost operation/correlation metadata |
| `header_contract_conflict_total` | Conflicting header and payload |
| `outbound_header_filtered_total` | Detect attempts to emit forbidden metadata |
| `translation_latency` | Transformation cost |
| `reply_timeout_total` | Detect reply route failures |
| `downstream_retry_total` | Technical retries |
| `idempotency_hit_total` | Duplicate business commands |
| `quarantine_oldest_age` | Errors needing review |

Do not use `orderId`, `operationId`, `tenantId`, or `businessCorrelationId` as unbounded metric tags (high cardinality). They belong only in access-controlled logs/traces with masking and retention policies.

### 19.1. Log metadata without logging secrets

~~~json
{
  "event": "message_translated",
  "source": "partner-a",
  "sourceSchemaVersion": "partner-order-v1",
  "targetSchemaVersion": "warehouse-command-v1",
  "headerContract": "PASS",
  "payloadMapping": "PASS",
  "result": "ACCEPTED"
}
~~~

This is an **illustrative log schema**, not built-in Spring Integration logging. Do not log raw JSON, access tokens, cookies, pre-signed URLs, or unnecessary personal data.

## 20. Common anti-patterns

| Anti-pattern | Consequence | Better approach |
| --- | --- | --- |
| Map only payload, ignore business headers | Lost correlation and idempotency | Pair metadata contract with payload contract |
| Copy all headers to be "safe" | Leaks tokens, PII, Java internal routing | Allowlist/strip at ingress and outbound |
| Use `MessageHeaders.ID` as operation ID | Retries create new business effects | Stable business operation identity |
| Use `businessCorrelationId` for all idempotency | New actions on same order get blocked | Separate correlation, group, and operation IDs |
| Generate new `operationId` on every translation | Redeliveries become new commands | Recover durable command ID |
| Read `trustedTenant` header from HTTP client | Cross-tenant routing/IDOR | Authenticate at trust boundary and issue context |
| Keep `application/json` from raw before serialization | Consumer misinterprets representation | Recompute media type at adapter |
| Serialize `replyChannel` over Kafka/JMS | Type errors or internal topology leaks | Transport reply address + correlation |
| Map `JMSMessageID`/Kafka offset to business key | Replay yields different key | Contract-defined operation ID |
| Default unknown currency to USD | Wrong units and monetary amount | Reject unknown/unsupported |
| Use `double` to convert major→minor | Uncontrolled precision/rounding | Exact `BigDecimal` + scale policy |
| Replace `requestedAt` with `Instant.now()` | Replay alters business timestamp | Parse source time with offset |
| Uppercase every ID | Collides case-sensitive identifiers | Normalize per field contract |
| Process conflicting header and payload anyway | Enables spoofing or wrong writes | Validate consistency and reject |
| Catch parse errors as technical retry | Retry storm with bad data | Typed terminal rejection |
| Treat HTTP timeout as uncommitted | Can trigger duplicate side effects | Target idempotency/reconciliation |
| Skip testing disallowed emission paths | Bad messages leak into handlers | Negative tests / zero side effects |
| Filter drops child before Aggregator | Group never receives enough replies | Typed rejected child outcome |
| Test in one JVM and assume broker contract | Header mapper/codecs may differ | Round-trip tests across real transport |
| Log raw source metadata | Leaks secrets and inflates cardinality | Structured safe logs + masking |
| Replay with new mapping policy unversioned | Same command yields different output | Pin/migration/reconciliation |

## 21. Pre-production checklist for Message Translator

- [ ] Maintain a mapping table for **payload fields** and a separate one for **metadata/headers**.
- [ ] Every field defines source, target, type, unit, validation, and error policy.
- [ ] Distinguish business metadata, integration-control headers, and transport metadata.
- [ ] Ingress authenticates tenant/partner and strips spoofed headers.
- [ ] Translator never generates a new operation ID when retrying the same command.
- [ ] Business correlation ID, operation ID, and execution ID have clear scopes.
- [ ] Target command never uses `MessageHeaders.ID`/Kafka offset as a business key.
- [ ] Numeric conversion is exact per currency/scale, avoiding arbitrary `double`.
- [ ] Timestamps specify offset/epoch units; origin event time is never replaced by processing time.
- [ ] Unknown enums/source versions have transparent rejection or migration policies.
- [ ] Required, optional, null, and conflicting fields follow contract handling rules.
- [ ] Outbound adapter enforces header allowlists and proper content-type/serializers.
- [ ] Sensitive headers, raw payloads, and Java channel objects never leak across external boundaries.
- [ ] Gateway reply/error routing works both after translation and after transport mapping.
- [ ] Splitter/Aggregator preserve execution/child identity without counting duplicates as new items.
- [ ] Mapping errors are not retried as technical failures; technical errors are not treated as invalid input.
- [ ] Downstream side effects are protected by an idempotent receiver/appropriate transaction.
- [ ] Unit tests assert both required headers **and** forbidden headers.
- [ ] Integration/contract tests on real broker/HTTP verify schema/header round-trips.
- [ ] DLQ replay defines clear source/target schema versions and mapping policies.
- [ ] Observability covers header conflicts, missing metadata, mapping failures, and reply timeouts.
- [ ] Logs, metrics, and tracing never leak tokens/PII or create high-cardinality metric labels.

## 22. Practice exercise

A customer service system receives shipping requests through two channels:

**Partner A** sends a message:

~~~json
{
  "shipmentNo": "SHP-901",
  "weightKg": "2.500",
  "declaredValue": "120.50",
  "currency": "USD",
  "createdAt": "2026-11-21T15:00:00+07:00",
  "serviceCode": "EXPRESS"
}
~~~

Metadata authenticated at ingress:

~~~text
trustedTenant         = tenant-a
trustedPartner        = carrier-a
businessCorrelationId = CASE-901
operationId           = SHIP-CREATE-901
sourceSchemaVersion   = carrier-shipment-v1
~~~

The **Warehouse/shipping system** expects:

~~~json
{
  "tenantId": "tenant-a",
  "carrierId": "carrier-a",
  "shipmentNo": "SHP-901",
  "weightGrams": 2500,
  "declaredValueMinor": 12050,
  "currency": "USD",
  "createdAt": "2026-11-21T08:00:00Z",
  "serviceTier": "EXPRESS",
  "operationId": "SHIP-CREATE-901"
}
~~~

The system also requires a `ShipmentCreated` reply back to the Gateway using `CASE-901`. Partner A also sends `Authorization`, `X-Caller-IP`, and `X-Debug-Payload` headers that the shipping system **must not receive**.

**Tasks:**

1. Write a payload mapping matrix converting kg to grams, major currency to minor units, and ISO offset to Instant.
2. Write a metadata mapping contract specifying which fields to preserve, rename, derive, drop, and recompute.
3. Explain why `businessCorrelationId` and `operationId` must not be used interchangeably.
4. Define `CarrierShipmentV1`, `ShippingCommandV1`, and `TranslationFailure` as Java records/classes.
5. Write a Translator taking `Message<CarrierShipmentV1>` and returning `Message<ShippingCommandV1>` with an explicit header allowlist.
6. Add a Spring Integration flow with inbound, Translator, Header Filter, and outbound channel; describe how to use `.transform(...)` if only transforming the payload.
7. Design a reply Translator from `ShipmentCreated` back to the partner response, preserving correlation without leaking internals.
8. When the Gateway uses request–reply over JMS, distinguish `JMSCorrelationID/JMSReplyTo` from an in-JVM `replyChannel` object.
9. Test `weightKg="2.501"` expecting exact grams, `declaredValue="120.505"`, and an unsupported currency without silent rounding.
10. Test missing `operationId`, invalid `sourceSchemaVersion`, and tenant conflict between payload and identity.
11. Write a JUnit test asserting the output **no longer** contains Authorization, raw debug payload, or internal Java channel names.
12. Write a Kafka/AMQP/JMS integration test (pick one) verifying content-type, schema version, operation ID, and correlation across serialization.
13. Simulate the shipping API committing successfully while the ACK is lost; redelivery must retain the operation ID so the backend does not create a second shipment.
14. For a multi-parcel batch, handle one rejected child so the Aggregator returns a clear result instead of hanging.
15. Propose metrics for missing headers, contract conflicts, translation failures, retries, and reply timeouts.

**Hint:** A Translator does more than return a DTO that looks right. It must return a **message whose overall contract is right**: valid payload, intact essential headers, blocked dangerous metadata, and a durable operation identity safe for retries.

## 23. Summary

**Mapping payload and metadata** is the core of a Message Translator when connecting systems with distinct schemas and semantics. Converting fields, units, dates, or enums is only part of the job; messages also carry **business identity, correlation, version, reply/error routing, security context, and transport metadata**. Dropping an essential header can lose a reply or break retries; keeping an extra sensitive header can leak data and breach trust boundaries.

In Spring Integration, design an **explicit mapping contract**, construct a new message with selected and validated metadata, use an appropriate Transformer or Service Activator, and apply a **header filter/allowlist at the outbound adapter**. Distinguish successful message translation from committed business handlers, test both payload **and** metadata across transports, keep operation IDs stable across retries/redeliveries, and properly handle Splitter/Aggregator, Gateway, error channels, schema evolution, and authorization. The goal is a target message that is **semantically accurate, safe, traceable, and protects side effects**.

**References:** Gregor Hohpe & Bobby Woolf, *Enterprise Integration Patterns* (Message Translator, Message Router, Correlation Identifier, Request-Reply, Idempotent Receiver); Spring Integration Reference on Message Transformation, Header Enricher/Header Filter, Java DSL, Service Activators, Gateways, Routers, Message Channels, Error Handling, and Testing; Spring Messaging API on `Message`, `MessageHeaders`, and `MessageBuilder`; Java SE on `BigDecimal`, `OffsetDateTime`, `Instant`, and `Locale.ROOT`.
