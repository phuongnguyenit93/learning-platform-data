# Handling Missing Fields Across Schemas

## 1. The Problem: Three Sources Sending the Same Order with Different Structures

A system receives orders from a legacy application, a partner API, and a newer mobile app. All three describe an **order**, yet disagree on field names, currency units, time representation, or customer data:

~~~json
{
  "source": "legacy-v1",
  "order_no": "O-501",
  "amount_cents": 12500,
  "created_utc": "2026-01-10T07:15:00Z"
}
~~~

~~~json
{
  "schemaVersion": "2",
  "orderId": "O-502",
  "totalAmount": "125.00",
  "currency": "USD",
  "buyer": {"email": null}
}
~~~

~~~json
{
  "schemaVersion": "3",
  "id": "O-503",
  "money": {"value": "125.00", "isoCurrency": "USD"},
  "contactEmail": "buyer@example.org",
  "placedAt": "2026-01-10T07:15:00Z"
}
~~~

**The problem:** schema v1 lacks `currency` and `email`; v2 has `email=null` and no timestamp; v3 renames fields. Downstream code should not maintain three business processing branches for all three shapes.

**Normalizer** in Enterprise Integration Patterns is the approach of **bringing heterogeneous input formats to a common canonical format** by coordinating a **Message Router** and **Message Translators/Transformers**. In Spring Integration, this pattern is usually built with a Router classifying source/schema and Transformers converting into a **canonical message**; calling `.transform()` once does not magically resolve missing data on its own.

~~~mermaid
flowchart LR
    A["Legacy schema v1"] --> ROUTER["Router: source + schema"]
    B["Partner schema v2"] --> ROUTER
    C["Mobile schema v3"] --> ROUTER
    ROUTER --> T1["Transformer v1"]
    ROUTER --> T2["Transformer v2"]
    ROUTER --> T3["Transformer v3"]
    T1 --> CAN["CanonicalOrder"]
    T2 --> CAN
    T3 --> CAN
    CAN --> VALID["Canonical validation"]
    VALID --> BUS["Business flow"]
~~~

This lesson belongs to the **Normalizer** chapter in the **SPRING_INTEGRATION_PATTERN** module, focused on implementing Enterprise Integration Patterns with Spring Integration to build loosely coupled, extensible message flows. Examples connect **Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation**, along with testing and monitoring processing branches.

**After this lesson**, you will be able to distinguish missing/null/blank/zero; decide which fields may be defaulted vs. rejected or enriched; implement Java/Jackson mappings and Java DSL; preserve identity and semantic correctness across schema evolution; and test multiple sources as well as conversion errors.

## 2. What Problem Does Normalizer Solve?

Without a Normalizer, every business service must understand every schema:

~~~text
InventoryHandler:
  if legacy → read order_no
  else if partner → read orderId
  else if mobile → read id

PricingHandler: repeats the same logic...
ShippingHandler: repeats the same logic...
~~~

The result is **source schema sprawl** across modules. A single field rename at a partner forces edits across multiple handlers, raising the risk of inconsistent conversions.

With a Normalizer:

~~~text
Source A/B/C
  → classify format
  → map + validate + missing-field policy
  → CanonicalOrder
  → Inventory/Pricing/Shipping use one contract
~~~

**Benefits:** reduced coupling, centralized schema evolution management, uniform validation/defaulting policies, and testing once at the integration boundary.

**Limitation:** a Normalizer cannot recover information that the producer **never supplied**. When critical data is absent and no trusted source can derive it, the output must explicitly represent **unknown** or be rejected; never invent values just to satisfy a constructor.

## 3. Four Commonly Confused States When Reading a Field

| State | Illustrative JSON | Possible Meaning |
|---|---|---|
| **Missing / absent** | No `email` key | Producer does not support it yet, does not know it, or omitted it |
| **Explicit null** | `"email": null` | Producer explicitly signals absent, unknown, or deletion request — depends on contract |
| **Blank / empty** | `"email": ""` or `"email": "  "` | Value was sent but empty; usually requires validation |
| **Concrete value** | `"email": "a@b.example"` | Value present; still requires format/source validation |

For numbers and booleans there is also:

~~~json
{"quantity": 0, "enabled": false}
~~~

**Zero and false are real values**, not missing. Logic like `if (!value) useDefault()` in truthy/falsy languages or code treating `0` as null can turn `quantity=0` into `quantity=1`, or `enabled=false` into `true`.

Specifically in **update/patch semantics**:

- An absent field may mean **leave unchanged**.
- A null field may mean **clear existing value**.
- A blank field may mean **reject**.
- A concrete value may mean **overwrite**.

For **create events**, rules may differ. Inspecting JSON shape alone without reading the source contract **is not enough** to determine meaning.

## 4. Missing-Field Decision Table: Reject, Preserve Unknown, Default, or Enrich?

| Situation | Choice | Safety Condition |
|---|---|---|
| Field required for business invariant | **Reject** | No trusted data available to recover it |
| Optional field omitted | **Preserve missing/unknown** | Downstream contract permits it |
| Default explicitly published by source schema | **Conditional default** | Scoped to source/version; auditable |
| Value lookable from an authoritative source | **Enrich** | Trusted key, explicit timeout/retry |
| Field renamed in a newer schema | **Map/rename** | Equivalent semantics and units |
| Explicit null meaning deletion in a patch | **Preserve null-intent** | Do not overwrite with a default |
| Field contains invalid empty string | **Reject/normalize per contract** | Never silently convert into fake valid data |
| Number, date, or money format error | **Reject conversion** | No loose parsing causing silent truncation |
| Unauthenticated source | **Reject/quarantine** | Never rely on a self-declared source label |

A sound decision order:

~~~mermaid
flowchart TD
    IN["Input field"] --> REQUIRED{"Required in canonical contract?"}
    REQUIRED -->|"No"| PRES{"Source schema distinguishes missing vs. null?"}
    PRES -->|"Yes"| KEEP["Preserve presence semantics"]
    PRES -->|"No"| UNKNOWN["Keep unknown or document limitation"]
    REQUIRED -->|"Yes"| EXISTS{"Valid value present?"}
    EXISTS -->|"Yes"| MAP["Map/convert + validate"]
    EXISTS -->|"No"| GUARANTEE{"Guaranteed default exists?"}
    GUARANTEE -->|"Yes"| DEF["Default by source/version + provenance"]
    GUARANTEE -->|"No"| ENRICH{"Authoritative lookup exists?"}
    ENRICH -->|"Yes"| E["Enrich with deadline/retry"]
    ENRICH -->|"No"| REJ["Reject/quarantine"]
~~~

Never choose “default every null to zero or empty string”, because that loses information and produces wrong financial numbers.

## 5. Build a Source Contract Table Before Writing Transformers

Example **assumed policy of the sample system**, to be replaced with real contracts in production:

| Canonical Field | Legacy v1 | Partner v2 | Mobile v3 | Policy |
|---|---|---|---|---|
| `orderId` | `order_no` | `orderId` | `id` | Required; reject if missing |
| `amount` | `amount_cents` | `totalAmount` | `money.value` | Convert with validation |
| `currency` | Absent | `currency` | `money.isoCurrency` | Legacy v1 **contractually guaranteed USD**; others required |
| `email` | Absent | `buyer.email` nullable | `contactEmail` | Optional; preserve presence |
| `orderedAt` | `created_utc` | Absent | `placedAt` | Optional; never default to `now()` |
| `sourceVersion` | v1 identified by adapter | v2 | v3 | Required for tracing/migration |
| `tenantId` | From trusted transport | From auth/partner mapping | From principal | Never use raw tenant headers to self-grant access |

A rule **valid only in this example**: Legacy v1 sends amounts in **USD cents** without a currency field because the producer contract guarantees the entire v1 feed uses USD. Thus `amount_cents=12500` can convert to `USD 125.00`.

**If the legacy feed mixes VND and USD or changed units without versioning**, a USD fallback is **data corruption**, not normalization. In that case, reject, add schema/versioning, or look up an authoritative source.

## 6. Canonical Contract Should Not Mirror One Arbitrary Source Schema

The canonical model is a **common format with documented semantics**, not simply “a copy of the latest source's DTO”.

A workable contract:

~~~text
CanonicalOrder
  tenantId: nonblank, trusted
  orderId: nonblank
  money:
    currency: ISO currency code, required
    amountMajor: decimal, required, nonnegative
  email: field-presence + optional string
  orderedAt: field-presence + timestamp in UTC
  provenance:
    sourceSystem: enum
    sourceSchemaVersion: string
    defaultedFields: limited list
  eventId/correlation: stable identifiers
~~~

Downstream consumers do not need to know `order_no` differs from `orderId` or `money.isoCurrency`, yet they must know **absent email differs from cleared email**, or which source rule applied a default value.

The canonical contract should have a **version** independent of producer schemas. When the canonical version changes breaking semantics, apply migration/routing and compatibility tests; do not push every source version into one DTO and hope field mapping never misfires.

## 7. Java 17+: Representing Presence Explicitly

A simple model:

~~~java
enum FieldPresence {
    ABSENT,
    EXPLICIT_NULL,
    PRESENT
}

record FieldValue<T>(FieldPresence presence, T value) {
    FieldValue {
        Objects.requireNonNull(presence, "presence");
        if (presence == FieldPresence.PRESENT && value == null) {
            throw new IllegalArgumentException(
                "PRESENT requires non-null value");
        }
        if (presence != FieldPresence.PRESENT && value != null) {
            throw new IllegalArgumentException(
                "ABSENT/EXPLICIT_NULL require null value");
        }
    }

    static <T> FieldValue<T> absent() {
        return new FieldValue<>(FieldPresence.ABSENT, null);
    }

    static <T> FieldValue<T> explicitNull() {
        return new FieldValue<>(FieldPresence.EXPLICIT_NULL, null);
    }

    static <T> FieldValue<T> present(T value) {
        return new FieldValue<>(FieldPresence.PRESENT, value);
    }
}
~~~

This is an **application-defined type**, not a class provided by Spring Integration. It lets consumers query directly:

~~~java
FieldValue<String> email = FieldValue.absent();
FieldValue<String> unset = FieldValue.explicitNull();
FieldValue<String> actual =
    FieldValue.present("buyer@example.org");
~~~

`Optional<String>` only distinguishes **has value vs. no value**; it cannot distinguish missing from explicit null. For create-only schemas where both mean “unknown”, `Optional` may suffice; for patch semantics, use a tri-state or equivalent representation.

**Never place `FieldValue.present("")` into the canonical model when the contract forbids blank strings.** Valid presence must still pass value validation.

## 8. Canonical Java Model with Provenance

~~~java
enum SourceSystem {
    LEGACY,
    PARTNER,
    MOBILE
}

record SourceInfo(
    SourceSystem system,
    String schemaVersion,
    Set<String> defaultedFields
) {}

record CanonicalMoney(
    Currency currency,
    BigDecimal amountMajor
) {}

record CanonicalOrder(
    String tenantId,
    String orderId,
    String eventId,
    CanonicalMoney money,
    FieldValue<String> email,
    FieldValue<Instant> orderedAt,
    SourceInfo provenance
) {}
~~~

In the example:

- `Currency` is `java.util.Currency`; ISO codes must be validated.
- `amountMajor` uses `BigDecimal`, never `double` for money.
- `email` and `orderedAt` preserve presence.
- `SourceInfo` records source/version and which fields were defaulted.
- `tenantId` must come from an authenticated boundary.
- `eventId` is a contracted logical event ID; do not substitute `MessageHeaders.ID` across brokers.

**Provenance should be right-sized**: do not stuff entire raw payloads and PII into canonical objects if consumers do not need them. When raw input audit/replay is required, store a safe reference with separate retention and access controls.

## 9. V1 Input: Schema Without `currency` and `email`

DTO for the legacy feed:

~~~java
record LegacyOrderV1(
    String order_no,
    Long amount_cents,
    String created_utc,
    String event_id
) {}
~~~

Since v1 omits currency, apply a default **only when** the v1 source is contractually guaranteed to be USD cents:

~~~java
CanonicalOrder normalizeLegacyV1(
        LegacyOrderV1 raw,
        String verifiedTenantId) {
    requireNonBlank(raw.order_no(), "MISSING_ORDER_ID");
    requireNonBlank(raw.event_id(), "MISSING_EVENT_ID");
    if (raw.amount_cents() == null) {
        throw new InvalidInputException("MISSING_AMOUNT");
    }
    if (raw.amount_cents() < 0) {
        throw new InvalidInputException("NEGATIVE_AMOUNT");
    }

    CanonicalMoney money = new CanonicalMoney(
        Currency.getInstance("USD"),
        BigDecimal.valueOf(raw.amount_cents(), 2));

    FieldValue<Instant> orderedAt =
        raw.created_utc() == null
            ? FieldValue.absent()
            : FieldValue.present(
                parseUtcOrReject(raw.created_utc()));

    return new CanonicalOrder(
        verifiedTenantId,
        raw.order_no(),
        raw.event_id(),
        money,
        FieldValue.absent(), // v1 has no email at all.
        orderedAt,
        new SourceInfo(
            SourceSystem.LEGACY,
            "1",
            Set.of("money.currency")));
}
~~~

`requireNonBlank`, `parseUtcOrReject`, and `InvalidInputException` are **application-defined helpers/exceptions** shown in later sections. `Set.of("money.currency")` lets audits see that currency **was derived from the source contract**, not supplied by the producer.

Never assign `""` or `"unknown@domain"` for email, because fabricated data can leak into shipping/notification services.

## 10. V2: Distinguishing Missing `buyer.email` from Explicit Null with Jackson

A `record PartnerOrderV2(String email)` cannot tell whether the `email` key **is absent** or present with `null`, because most Jackson configurations map both to Java `null`.

Use `JsonNode` at the boundary:

~~~java
FieldValue<String> readBuyerEmail(JsonNode root) {
    JsonNode buyer = root.get("buyer");

    if (buyer == null) {
        return FieldValue.absent();
    }
    if (!buyer.isObject()) {
        throw new InvalidInputException("INVALID_BUYER_OBJECT");
    }

    JsonNode email = buyer.get("email");
    if (email == null) {
        return FieldValue.absent();
    }
    if (email.isNull()) {
        return FieldValue.explicitNull();
    }
    if (!email.isTextual()) {
        throw new InvalidInputException("INVALID_EMAIL_TYPE");
    }

    String text = email.textValue();
    if (text.isBlank()) {
        throw new InvalidInputException("BLANK_EMAIL");
    }
    return FieldValue.present(text);
}
~~~

Jackson distinguishes:

- `get("email")==null`: **property absent**.
- `get("email").isNull()`: property present with **JSON null value**.
- `isTextual()`: string-typed value.
- `textValue()`: extracts string **after type checking**.

Do not call `path("email").asText("")` and treat missing/null/blank as identical: convenience methods can erase presence state. For nested fields, validate the parent object first.

## 11. Parsing Numbers, Currencies, and Timestamps Strictly

Different sources express money in minor units or decimal strings:

~~~text
Legacy: amount_cents=12500  → USD 125.00
Partner: totalAmount="125.00", currency="USD"
Mobile: money.value="125.00", money.isoCurrency="USD"
~~~

Conversions to avoid:

- `Double.parseDouble` followed by `new BigDecimal(double)`, causing precision errors.
- Silently truncating `"12.5"` to integer `12`.
- Assuming `currency=USD` for all sources just because one legacy source did.
- Accepting `NaN`/`Infinity` or locale separators outside the contract.
- Using `Instant.now()` for a missing `createdAt`, fabricating business event times.

Example:

~~~java
BigDecimal parseMoneyOrReject(
        JsonNode node, String fieldName) {
    if (node == null || node.isNull()) {
        throw new InvalidInputException(
            "MISSING_" + fieldName);
    }
    if (!node.isTextual() && !node.isNumber()) {
        throw new InvalidInputException(
            "INVALID_" + fieldName + "_TYPE");
    }
    try {
        BigDecimal value = new BigDecimal(
            node.isTextual() ? node.textValue() : node.asText());
        if (value.signum() < 0) {
            throw new InvalidInputException("NEGATIVE_AMOUNT");
        }
        return value;
    } catch (NumberFormatException ex) {
        throw new InvalidInputException("INVALID_AMOUNT");
    }
}
~~~

In production, add **currency scale policies** (JPY, USD, etc.), maximum precision/range, rounding rules, operation type (whether refunds allow negatives), and resource guards against huge numeric strings. For timestamps, use ISO-8601 with explicit offsets and normalize to `Instant`; a local datetime without timezone **is insufficient** to pinpoint an instant.

## 12. Validation Helpers Preserving Stable Error Codes

~~~java
final class InvalidInputException extends RuntimeException {
    private final String reasonCode;

    InvalidInputException(String reasonCode) {
        super(reasonCode);
        this.reasonCode = reasonCode;
    }

    String reasonCode() {
        return reasonCode;
    }
}

void requireNonBlank(String value, String reasonCode) {
    if (value == null || value.isBlank()) {
        throw new InvalidInputException(reasonCode);
    }
}

Instant parseUtcOrReject(String value) {
    try {
        return Instant.parse(value);
    } catch (DateTimeParseException ex) {
        throw new InvalidInputException("INVALID_TIMESTAMP");
    }
}
~~~

These are **illustrative helpers** that can be extracted into a dedicated validator/service. `InvalidInputException` represents a **contract violation**, distinct from `TransientDataAccessException` or HTTP 503.

**Never expose raw parser exception messages in public responses.** Return a standardized `reasonCode`, plus field path and source/version if appropriate; keep raw payloads protected inside a separate quarantine/reference store.

## 13. Mapping V2: Required and Optional Fields Do Not Share One Policy

V2 makes `orderId`, `totalAmount`, and `currency` required while `buyer.email` is optional:

~~~java
String requiredText(JsonNode root, String field) {
    JsonNode node = root.get(field);
    if (node == null || node.isNull()) {
        throw new InvalidInputException("MISSING_" + field);
    }
    if (!node.isTextual() || node.textValue().isBlank()) {
        throw new InvalidInputException("INVALID_" + field);
    }
    return node.textValue();
}

CanonicalOrder normalizePartnerV2(
        JsonNode root, String verifiedTenantId) {
    String orderId = requiredText(root, "orderId");
    String eventId = requiredText(root, "eventId");
    String code = requiredText(root, "currency");
    Currency currency;
    try {
        currency = Currency.getInstance(code);
    } catch (IllegalArgumentException ex) {
        throw new InvalidInputException("INVALID_CURRENCY");
    }

    BigDecimal amount =
        parseMoneyOrReject(root.get("totalAmount"), "AMOUNT");
    FieldValue<String> email = readBuyerEmail(root);
    return new CanonicalOrder(
        verifiedTenantId,
        orderId,
        eventId,
        new CanonicalMoney(currency, amount),
        email,
        FieldValue.absent(), // v2 does not publish orderedAt.
        new SourceInfo(
            SourceSystem.PARTNER, "2", Set.of()));
}
~~~

`requiredText()` in the example rejects missing, explicit null, and blank for **required fields**. Conversely, `readBuyerEmail()` in section 10 **preserves** the distinction between absent, null, and present per the email contract.

**Not every field must follow the same policy.** A schema can specify `orderId` required, `currency` required, `email` nullable, `orderedAt` optional. Adopting a canonical schema does not mean every source must populate every field.

## 14. Mapping V3: Renaming Fields Does Not Mean Changing Semantics

V3 renames:

~~~text
id                    → orderId
money.value           → money.amountMajor
money.isoCurrency     → money.currency
contactEmail          → email
placedAt              → orderedAt
~~~

Before mapping, verify:

1. Does `money.value` share the **same unit and rounding** as v2's `totalAmount`?
2. Is `placedAt` when the order was created, paid, or submitted?
3. Does `contactEmail=null` mean unknown or an email deletion request?
4. Is `id` unique per tenant, region, source, or globally?
5. Does `schemaVersion="3"` come from a trusted contract or a client-spoofable field?

A safe Java helper for reading nested objects:

~~~java
JsonNode requiredObject(JsonNode parent, String field) {
    JsonNode child = parent.get(field);
    if (child == null || !child.isObject()) {
        throw new InvalidInputException("INVALID_" + field);
    }
    return child;
}

CanonicalMoney readMobileMoney(JsonNode root) {
    JsonNode money = requiredObject(root, "money");
    String isoCode = requiredText(money, "isoCurrency");
    Currency currency;
    try {
        currency = Currency.getInstance(isoCode);
    } catch (IllegalArgumentException ex) {
        throw new InvalidInputException("INVALID_CURRENCY");
    }
    BigDecimal value =
        parseMoneyOrReject(money.get("value"), "AMOUNT");
    return new CanonicalMoney(currency, value);
}
~~~

**Never treat identical field names as proof of identical meaning.** If v3 changes `amount` from merchandise subtotal to shipping-inclusive total, the mapping must update the business contract or adjust accordingly, rather than silently placing it into canonical `totalAmount`.

## 15. Normalization Must Be Deterministic When Using Only Known Data

Given an input and a specific mapping policy version, the Normalizer should return the same canonical result:

\[
\operatorname{normalize}(source, version, payload, policy)
= canonical\ result
\]

Therefore separate:

- **Pure mapping:** renaming fields, converting units, validating shapes, resolving absent/null, applying defaults **guaranteed by contract**.
- **I/O enrichment:** calling other services to supplement missing info.
- **Business handler:** updating inventory, pricing, creating transactions.

Never assign defaults like `orderedAt=Instant.now()` inside pure mapping: two replays will produce two different outputs. If the system genuinely needs `ingestedAt`, that is **ingestion metadata** distinct from `orderedAt`; put it in a dedicated field without overwriting semantic timestamps.

When replaying messages from a DLQ, record `mappingPolicyVersion` so you know which rules ran previously. If a default or rounding rule changes, normalization outputs can differ even for identical raw payloads; that is a business-impacting change requiring governance.

## 16. A Shared Envelope So the Router Picks the Right Source Transformer

If raw bytes were already parsed into a `JsonNode` by the adapter, standardize metadata at ingress:

~~~java
record NormalizationEnvelope(
    SourceSystem source,
    String schemaVersion,
    String verifiedTenantId,
    JsonNode payload
) {}
~~~

**`verifiedTenantId`** must be established by trusted authentication/adapters—never take a self-reported `tenantId` field and trust it blindly. `source` and `schemaVersion` must also be verified via transport contracts, topic/route, or schema registry. A client-sent `sourceSystem` header can be untrusted.

A Java DSL router:

~~~java
@Configuration
@EnableIntegration
class NormalizationRouter {

    @Bean
    IntegrationFlow dispatchSchema() {
        return IntegrationFlow.from("normalizer.input")
            .route(
                NormalizationEnvelope.class,
                envelope -> envelope.source().name(),
                mapping -> mapping
                    .channelMapping("LEGACY", "normalizer.legacy")
                    .channelMapping("PARTNER", "normalizer.partner")
                    .channelMapping("MOBILE", "normalizer.mobile")
                    .defaultOutputChannel("normalizer.unsupported"))
            .get();
    }
}
~~~

This illustrates Java DSL; verify imports, bean/channel names, and overload signatures against your Spring Integration version. The Router's job is **choosing the conversion path**, not filling missing fields. The `normalizer.unsupported` path must have a consumer handling errors/quarantine properly rather than letting bad messages vanish silently.

**Source routing and schema version routing are two distinct steps.** One source may send v1 and v2 concurrently; validate/route by **(source, version)** pairs, or let each source adapter dispatch to a version-aware mapper. Avoid routing v9 to a v2 handler merely because the provider matches.

## 17. One Transformer per Format, One Shared Output Type

Transformers accept `NormalizationEnvelope`, validate the version, and return `CanonicalOrder`:

~~~java
@Configuration
@EnableIntegration
class NormalizationTransformers {

    @Bean
    IntegrationFlow legacyFlow(OrderNormalizers normalizers) {
        return IntegrationFlow.from("normalizer.legacy")
            .transform(
                NormalizationEnvelope.class,
                normalizers::fromLegacy)
            .channel("normalizer.canonical")
            .get();
    }

    @Bean
    IntegrationFlow partnerFlow(OrderNormalizers normalizers) {
        return IntegrationFlow.from("normalizer.partner")
            .transform(
                NormalizationEnvelope.class,
                normalizers::fromPartner)
            .channel("normalizer.canonical")
            .get();
    }

    @Bean
    IntegrationFlow mobileFlow(OrderNormalizers normalizers) {
        return IntegrationFlow.from("normalizer.mobile")
            .transform(
                NormalizationEnvelope.class,
                normalizers::fromMobile)
            .channel("normalizer.canonical")
            .get();
    }
}
~~~

`OrderNormalizers` is an **application-written service**, where `fromLegacy()` reads v1 and calls `normalizeLegacyV1()`, `fromPartner()` calls `normalizePartnerV2()`, and `fromMobile()` uses v3 helpers. Each method must:

1. Verify the envelope's `source` and `schemaVersion`.
2. Validate required fields **before** fallible conversions.
3. Normalize missing fields per that version's contract.
4. Attach source provenance and `defaultApplied` flags.
5. Produce a complete `CanonicalOrder` or **throw a classified error**, never a half-baked object.

If all three flows send into `normalizer.canonical`, configure **one downstream business consumer** (or an explicit fan-out). Never subscribe multiple independent consumers to one `DirectChannel` expecting every subscriber to receive every message; `DirectChannel` with multiple subscribers has round-robin/load-balancing dispatch semantics.

## 18. Canonical Validation After the Transformer Is Another Safeguard

Source-specific validation protects the input contract. Once all mappings emit `CanonicalOrder`, validate **canonical invariants**:

~~~java
@Service
class CanonicalOrderValidator {
    boolean isValid(CanonicalOrder order) {
        return order != null
            && order.tenantId() != null
            && !order.tenantId().isBlank()
            && order.orderId() != null
            && !order.orderId().isBlank()
            && order.eventId() != null
            && !order.eventId().isBlank()
            && order.money() != null
            && order.money().currency() != null
            && order.money().amountMajor() != null
            && order.money().amountMajor().signum() >= 0
            && order.email() != null
            && order.orderedAt() != null
            && order.provenance() != null;
    }
}
~~~

This example validates basic fields; production adds max precision/range, tenant authorization, ID format/uniqueness, email format, date validity, schema version, and domain-specific policies.

A canonical validation integration flow:

~~~java
@Bean
IntegrationFlow canonicalValidation(
        CanonicalOrderValidator validator) {
    return IntegrationFlow.from("normalizer.canonical")
        .filter(
            CanonicalOrder.class,
            validator::isValid,
            spec -> spec.throwExceptionOnRejection(true))
        .channel("orders.business")
        .get();
}
~~~

**Do not conflate two failure types:** malformed source input should report codes like `MISSING_ORDER_ID`; a mapper bug producing an invalid `CanonicalOrder` from valid source data is a **normalization defect** requiring an alert, not blaming the producer.

## 19. Filter Only Decides Accept/Reject; It Does Not Invent Missing Fields

~~~text
Raw parsed source
  → Filter(check required source fields)
  → Transformer(normalize)
  → Filter(check canonical invariants)
  → Business handler
~~~

A Filter returning `false` may drop the message, route to `discardChannel`, or throw an exception depending on configuration. Actual ***normalization*** happens in the Transformer or mapping service, not by having a Filter fill in fields.

Place a Filter **before the Transformer** for cheap, pure-data checks that are dangerous when missing (JSON shape, mandatory IDs, array bounds, schema version). Check canonical invariants after the Transformer.

If the Transformer throws `InvalidInputException` before the second Filter runs, that is a **mapping rejection path**, not a Filter discard event. Handle this class of error at the corresponding Gateway or broker error boundary.

## 20. Content Enricher When a Required Field Is Absent from the Source

Suppose shipping requires `deliveryAddress`, while the legacy feed provides only `customerId`. You can:

~~~mermaid
flowchart LR
    LEG["Legacy order, no address"] --> MAP["Normalize known fields"]
    MAP --> LOOK{"Content Enricher: customer lookup"}
    LOOK -->|"Found + authorized"| ADD["Canonical order + address"]
    LOOK -->|"Definitive not found"| REJ["Permanent rejection / business outcome"]
    LOOK -->|"Timeout/503"| RET["Retryable failure"]
    ADD --> SHIP["Shipping handler"]
~~~

**Enrichment** is valid only with an **authoritative source** and a verified key. Missing address never justifies setting `address="N/A"` and letting Shipping run.

Spring Integration **Content Enricher** coordinates request/reply enrichment, yet you must:

- Preserve original correlation across lookup and reply.
- Enforce timeout and retry budgets on lookups.
- Distinguish **“address not found”** from **“lookup service unavailable”**.
- Never attach values from another customer due to matching names or concurrent requests.
- Account for cache TTL, stale data, and authorization before using results.

**Never turn an HTTP 503 into `FieldValue.absent()` and let business proceed** when the address is required. That is an unresolved infrastructure failure, not an intentionally omitted source field.

## 21. Preserving Correlation, Trace, and Identity Across Schema Changes

A message may carry:

~~~text
sourceSystem=PARTNER
sourceSchemaVersion=2
eventId=EV-501
tenantId=tenant-a
businessCorrelationId=tenant-a|O-501|revision-2
springMessageId=<framework message ID>
traceId=<distributed tracing ID>
~~~

These IDs **are not interchangeable**:

- `springMessageId` identifies a Spring message object and may change when a Transformer returns a reply.
- `eventId` identifies the event per producer contract.
- `businessCorrelationId` groups results belonging to one logical unit of work.
- `traceId` supports observability, not automatically business grouping.
- `sequenceNumber/sequenceSize` serve Splitter/Resequencer, not source schema versioning.

The Normalizer must **preserve required business identifiers** in canonical payloads/headers. Never take `order_no` from source A and `MessageHeaders.ID` from source B for the same `orderId` field; that is a semantic bug, not a mere type difference.

When creating a new message with `MessageBuilder`, specify which headers cross and which are unsafe across trust boundaries (`replyChannel`, auth headers, raw internal routing). Over brokers, test header mappers and include essential business identifiers in the **wire contract**.

## 22. Placing Normalizer Ahead of Splitter and Aggregator

A helpful rule: **normalize an order before splitting it into line tasks** if a missing field could affect the whole batch.

~~~text
Legacy v1 / Partner v2 / Mobile v3
  → Normalizer → CanonicalOrder
  → Validate common invariants
  → Splitter: CanonicalLineWork #1..#N
  → Worker branches
  → Aggregator: CanonicalOrderResult
~~~

If a source omits `currency` and normalizes wrongly to a different default, **all Pricing child tasks** will miscalculate even though the Aggregator receives all N results. Missing-field policy must be resolved **before** fan-out.

**Correlation:** Splitter usually attaches `correlationId/sequenceNumber/sequenceSize` per child group. Normalizers must never arbitrarily overwrite those headers or merge results from two sources sharing an order ID across different tenants, operations, or revisions.

If a line has malformed data after the Splitter:

- **Reject the whole batch** when the business forbids partial results.
- Or emit a **failure outcome with the same member ID/group key** for that line so the Aggregator concludes `PARTIAL`/`FAILED` intentionally.

Never decrement expected group size when a Filter drops a member; doing so hides source errors and can produce false success.

## 23. Gateway Can Return Canonical Output or Rejection

A Gateway:

~~~java
@MessagingGateway(defaultRequestChannel = "normalizer.input")
interface OrderNormalizationGateway {
    CanonicalOrder normalize(NormalizationEnvelope input);
}
~~~

Conditions for the Gateway to return reliably:

1. All source flows must eventually produce an appropriate **canonical reply**.
2. `replyChannel` headers must survive endpoints, or reply routing must be configured explicitly.
3. Invalid sources must produce a **typed error response** or mapped exception, never be silently dropped.
4. Async broker calls or Content Enrichers can time out; do not label all timeouts as `INVALID_SCHEMA`.
5. Distinguish source `schemaVersion` from output `canonicalVersion`.

If a Filter receives an invalid message and **discards with no reply**, the Gateway will simply time out instead of reporting `MISSING_ORDER_ID`. For request–reply, use a **fail-fast validation exception carrying `reasonCode`** or a typed `NormalizationRejected` result in the return contract.

**Normalizing an object does not require a Gateway** if receivers already live inside an `IntegrationFlow`. A Gateway is useful when a boundary wants request–reply or a typed API.

## 24. Error Channel: Malformed Input vs. Dependency Failure

| Situation | Error Class | Expected Outcome |
|---|---|---|
| JSON parse error | Decode/adapter boundary | Reject/quarantine; no endless retries |
| Unsupported source version | Contract | `UNSUPPORTED_SCHEMA_VERSION` |
| Missing required `orderId` | Contract | `MISSING_ORDER_ID` |
| Unparseable amount | Mapping/contract | `INVALID_AMOUNT` |
| Missing currency with no valid fallback | Contract | `MISSING_CURRENCY` |
| Content Enricher HTTP 503 | Transient dependency | Bounded retry/backoff |
| Customer lookup returns genuine 404 | Business/contract depending on case | Reject or terminal outcome |
| Mapper throws NPE due to bug | Application defect | Alert + error path; do not blame source |
| Broker/`MessageGroupStore` error | Infrastructure | Retry/recovery per transaction semantics |

An `InvalidInputException` can map to HTTP 400/422 or permanent DLQ/quarantine; infrastructure exceptions can be retried. With synchronous `DirectChannel`, errors propagate to the caller; with `ExecutorChannel`/pollers/brokers, errors happen at a different **async error boundary**.

**Never assume every exception lands on `errorChannel`**: a deserializer failure before Spring Integration constructs a `Message` may only hit the adapter/container error handler. And a Filter's `discardChannel` is not automatically a broker DLQ.

## 25. Retry and Idempotency of Normalization

A message is redelivered after successful normalization:

~~~text
Raw eventId=EV-501, schemaVersion=1
  → normalize → CanonicalOrder
  → downstream commit
  → crash before broker ACK
  → redelivery EV-501
~~~

If the Normalizer is deterministic and side-effect-free, re-normalizing the same data is safe. **Downstream business handlers**, however, still require idempotency to avoid double charging or double publishing.

What to preserve across retries:

- Stable `eventId`/logical work ID; never generate a new UUID on every normalization.
- Deterministic `source/version/mappingPolicyVersion`.
- Consistent defaulting policy; never retroactively apply new defaults to old replays.
- Canonical output carrying business group/member identity for Splitter/Aggregator.
- Clear fingerprinting/canonicalization when identical keys arrive with different payloads.

If mapping relies on an external lookup whose data changes between attempts, the Normalizer is no longer purely deterministic. You may need **snapshot/lookup versions**, persisted normalized outputs, or idempotent workflow state depending on business rules.

**Never retry malformed input indefinitely**: the same schema-invalid raw bytes cannot fix themselves. If a producer fixes the schema, run a **controlled reprocess/migration workflow**, not hot retries.

## 26. Schema Evolution and Compatibility Conditions

A new or optional producer field may look backward-compatible, yet consumers still need checking:

| Change | Usually Compatible? | What to Check |
|---|---|---|
| Added optional `email` | Usually yes | Are unknown fields rejected? |
| Added required field with no default | Usually breaking for old inputs | Need new version/migration? |
| Renamed `order_no` to `orderId` | Breaking if old parser requires old name | Mapper per source version |
| Changed `amount_cents` to major decimals | Breaking semantics | Convert scale/currency accurately |
| Allowed `null` on previously non-null field | Potentially breaking | Does downstream accept unknown? |
| Treated zero as “missing” | Breaking semantics | Never conflate falsey values |
| Changed meaning of `createdAt` | Breaking despite same type | Contract and data lineage |
| Changed `orderId` scope from global to per-tenant | Breaking correlation/keys | Idempotency/correlation migration |

With Avro/Protobuf/JSON Schema, schema registries and compatibility modes catch **certain structural changes**, yet **never verify meaning**—such as gross vs. net amounts, currency scales, or timezones.

During transitions, run **v1 and v2 Transformers** in parallel for version-routed messages. Do not build one function with dozens of `if (fieldExists)` checks and no policy, as behavior can flip unexpectedly if an input happens to carry both old and new names.

## 27. Contract-First: Align on Field Meanings Before Deploying

Each source schema should have a versioned field contract table. For example:

| Field | Wire Type | Presence Rule | Null Rule | Canonical Mapping | Owner |
|---|---|---|---|---|---|
| v1 `order_no` | string | Required | Reject | `orderId` | Legacy team |
| v1 `amount_cents` | integer | Required | Reject | USD cents → decimal | Legacy team |
| v1 `email` | Absent | Absence expected | N/A | `ABSENT` | Legacy team |
| v2 `buyer.email` | string/null | Optional | `EXPLICIT_NULL` | `email` | Partner team |
| v2 `currency` | ISO string | Required | Reject | Currency | Partner team |
| v3 `placedAt` | ISO timestamp | Optional/required per contract | Reject or unknown | `orderedAt` | Mobile team |

**Never invent mapping policy from consumer guesswork.** Source owners must confirm:

- What does an absent field mean?
- Is explicit null allowed?
- For **which versions** and until when is a default guaranteed?
- What are the monetary units, precision, timezone, and case sensitivity?
- Over what scope is an ID unique?
- Will producer changes arrive via migration or event versioning?
- Who owns handling when unknown/null reaches downstream?

A contract change does not end with editing a Transformer. You need **contract tests, release sequencing, and observability** to detect traffic from unexpected producer versions.

## 28. Per-Source Defaulting Policies Must Have Scope and Provenance

An example policy set:

~~~text
Policy legacy-v1:
  if currency ABSENT:
     currency = USD
     reason = LEGACY_V1_USD_CENTS_CONTRACT
  if email ABSENT:
     preserve ABSENT

Policy partner-v2:
  if currency ABSENT:
     REJECT MISSING_CURRENCY
  if buyer.email ABSENT:
     preserve ABSENT
  if buyer.email EXPLICIT_NULL:
     preserve EXPLICIT_NULL

Policy mobile-v3:
  if money.isoCurrency ABSENT:
     REJECT MISSING_CURRENCY
  if placedAt ABSENT:
     preserve ABSENT only if optional
~~~

Never use a global rule:

~~~java
String currency = payload.get("currency") == null
    ? "USD"
    : payload.get("currency").asText();
~~~

That rule assigns USD to every payload missing top-level `currency`, including v3 where currency lives inside `money.isoCurrency`, or a partner actually sending another currency.

**Record provenance:** track which fields were defaulted, rule/policy version, and source/version. Provenance need not appear on every public API, yet internal pipelines and audits need a way to trace where a value came from.

## 29. When Missing Fields Appear in Patch/Update Events

Consider an `UpdateCustomerContact` example:

~~~json
{
  "customerId": "C-501",
  "email": null
}
~~~

If the patch contract specifies:

- Missing `email` key → keep existing email.
- `email=null` → delete existing email.
- `email="new@example.org"` → update email.
- `email=""` → invalid.

then transforming into `Optional<String>` erases the distinction between absent and null, risking **unintended deletion** or failing to clear when requested.

A canonical change instruction can look like:

~~~java
record EmailPatch(
    FieldValue<String> email
) {}

void applyEmailPatch(EmailPatch change) {
    switch (change.email().presence()) {
        case ABSENT -> {
            // Leave unchanged.
        }
        case EXPLICIT_NULL -> {
            // Delete email per contract and authorization.
        }
        case PRESENT -> {
            // Validate and persist the new email value.
        }
    }
}
~~~

This illustrates **missing-field semantics**, not a complete REST PATCH framework. Applying deletes/updates still requires authorization, optimistic locking, and idempotency/operation versioning.

**Do not apply patch semantics by default to create events** when a source schema defines explicit null as “unknown”. Semantics are governed by the **message type's contract**.

## 30. Unknown and Nullable Must Be Interpreted Consistently Downstream

A canonical field may be optional, yet each consumer must decide what to do:

| Consumer | `email ABSENT` | `email EXPLICIT_NULL` | `email PRESENT` |
|---|---|---|---|
| Email notification | Do not send; log missing data | Do not send; respect cleared/null state | Validate and send if permitted |
| Customer CRM sync | Leave unchanged under patch semantics | Clear if contract permits | Update |
| Analytics | Count in “missing” bucket | Count in “explicit null” bucket | Use permitted value |
| Shipping | Not needed if shipment uses no email | Not needed if optional | May use for notifications |

**Never turn missing into a fake email address** that a service might actually email. If downstream cannot handle `FieldValue`, a dedicated adapter can translate into the consumer's contract using explicit unknown/null rules.

Canonical models **are not required** to use tri-state for every field. Use it only when the domain truly needs the distinction; otherwise keep the schema simple and document how missing/null merge.

## 31. Test: Legacy V1 Lacks Currency, Yet Default Has Contractual Proof

JUnit 5 for the mapper:

~~~java
@Test
void legacyV1UsesContractualCurrencyDefault() {
    LegacyOrderV1 source = new LegacyOrderV1(
        "O-501", 12500L,
        "2026-01-10T07:15:00Z",
        "EV-501");

    CanonicalOrder result =
        normalizeLegacyV1(source, "tenant-a");

    assertEquals("O-501", result.orderId());
    assertEquals(
        Currency.getInstance("USD"),
        result.money().currency());
    assertEquals(
        0,
        result.money().amountMajor()
            .compareTo(new BigDecimal("125.00")));
    assertEquals(
        FieldPresence.ABSENT,
        result.email().presence());
    assertTrue(result.provenance().defaultedFields()
        .contains("money.currency"));
    assertEquals(
        Instant.parse("2026-01-10T07:15:00Z"),
        result.orderedAt().value());
}
~~~

The test verifies that **the USD default applies only to legacy v1 per the example contract**. Add an opposing test for v2/v3 missing currency: **it must reject**, never silently sharing a global fallback.

Method snippets in earlier sections belong inside their corresponding classes/services/test fixtures; imports and wiring are omitted to focus on the Normalizer.

## 32. Test: Missing, Explicit Null, Blank, and Present

Jackson `ObjectMapper` on raw JSON:

~~~java
@Test
void distinguishesEmailPresenceStates() throws Exception {
    ObjectMapper mapper = new ObjectMapper();

    JsonNode missing = mapper.readTree(
        "{\"buyer\":{}}");
    JsonNode explicitNull = mapper.readTree(
        "{\"buyer\":{\"email\":null}}");
    JsonNode present = mapper.readTree(
        "{\"buyer\":{\"email\":\"buyer@example.org\"}}");
    JsonNode blank = mapper.readTree(
        "{\"buyer\":{\"email\":\"   \"}}");

    assertEquals(FieldPresence.ABSENT,
        readBuyerEmail(missing).presence());
    assertEquals(FieldPresence.EXPLICIT_NULL,
        readBuyerEmail(explicitNull).presence());
    assertEquals(FieldPresence.PRESENT,
        readBuyerEmail(present).presence());
    assertEquals(
        "buyer@example.org",
        readBuyerEmail(present).value());
    assertThrows(InvalidInputException.class,
        () -> readBuyerEmail(blank));
}
~~~

This tests **presence differences**; `@Valid` on a Java DTO after deserialization cannot replace it if missing and null already collapsed into Java `null`, losing the original state.

Add tests for `buyer=null`, `buyer=[]`, `buyer.email=123`, and overly long nested strings. For patch APIs, explicitly test “missing preserves” and “explicit null deletes” to prevent silent data loss.

## 33. Test: Missing Amount Must Not Default to Zero

After making legacy DTO `amount_cents` nullable `Long`, test:

~~~java
@Test
void legacyMissingAmountIsNotAssumedZero() {
    LegacyOrderV1 source = new LegacyOrderV1(
        "O-501", null, null, "EV-501");

    InvalidInputException error =
        assertThrows(
            InvalidInputException.class,
            () -> normalizeLegacyV1(source, "tenant-a"));

    assertEquals("MISSING_AMOUNT", error.reasonCode());
}
~~~

**Why use `Long` instead of `long`?** When JSON omits a field, many deserializer configurations set primitive `long` to `0`, making **missing amount** indistinguishable from **actual zero amount**. When the API must tell them apart, use boxed types or `JsonNode`/schema validation before constructing DTOs.

**Zero can be valid** for a 100%-discounted order depending on contract. Never arbitrarily reject amount 0 just to catch missing fields; validators must reflect business rules.

## 34. Test: Missing Currency in V2 Must Reject, Not Borrow V1's Default

~~~java
@Test
void partnerV2MissingCurrencyIsRejected() throws Exception {
    JsonNode source = new ObjectMapper().readTree(
        "{"
        + "\"orderId\":\"O-502\","
        + "\"eventId\":\"EV-502\","
        + "\"totalAmount\":\"125.00\""
        + "}");

    InvalidInputException error =
        assertThrows(
            InvalidInputException.class,
            () -> normalizePartnerV2(source, "tenant-a"));

    assertEquals(
        "MISSING_currency",
        error.reasonCode());
}
~~~

In the helper from section 13, `requiredText(root, "currency")` concatenates the error code with the field name, yielding `MISSING_currency`. In production, standardize codes to an **uppercase enum/catalog** such as `MISSING_CURRENCY`, rather than letting JSON key casing dictate error codes.

More important than capitalization: **partner v2 must not inherit legacy v1's USD default**. A test returning `currency=USD` when v2 omits the field is a **bug**, even if the resulting data looks superficially valid.

## 35. Integration Test: Router → Transformer → Canonical Validation

Set up a test Spring context with the dispatcher and three transformers from sections 16–18. Send a message:

~~~java
Message<NormalizationEnvelope> request =
    MessageBuilder.withPayload(
        new NormalizationEnvelope(
            SourceSystem.LEGACY,
            "1",
            "tenant-a",
            legacyJsonNode))
    .setHeader("businessCorrelationId",
        "tenant-a|O-501|revision-1")
    .build();
~~~

A test can attach a `QueueChannel` at `orders.business` to assert:

~~~java
@Test
void legacyMessageBecomesCanonicalWithoutLosingIdentity() {
    MessageChannel input =
        context.getBean("normalizer.input", MessageChannel.class);
    PollableChannel output =
        context.getBean("orders.business", PollableChannel.class);

    assertTrue(input.send(request));
    Message<?> received = output.receive(1_000);
    assertNotNull(received);
    assertInstanceOf(
        CanonicalOrder.class,
        received.getPayload());

    CanonicalOrder canonical =
        (CanonicalOrder) received.getPayload();
    assertEquals("O-501", canonical.orderId());
    assertEquals("EV-501", canonical.eventId());
    assertEquals(
        SourceSystem.LEGACY,
        canonical.provenance().system());
}
~~~

`context`, `legacyJsonNode`, and `request` are **test fixtures**, not global Spring Integration variables. Run tests with **production consumers disabled** so competing subscribers do not steal output messages. To verify header propagation, assert `businessCorrelationId` and `replyChannel` wherever required; never assume every header survives every external adapter.

Test each source/version separately and assert **identical canonical semantics** for equivalent inputs. Assert more than instance type: verify money, email presence, timestamp, and provenance.

## 36. Schema and Failure-Path Test Matrix

| Test Case | Input | Expected Outcome |
|---|---|---|
| Valid v1 contract | Missing currency/email | Audited USD default, email `ABSENT` |
| Valid v2 contract | Currency + null email | No currency default; email `EXPLICIT_NULL` |
| Valid v3 contract | Nested money + `contactEmail` | Mapped to right names/units |
| V1 missing amount | `amount_cents` absent | `MISSING_AMOUNT` |
| V2 missing currency | `currency` absent | Permanent reject |
| V3 missing `money` | Nested object absent | `INVALID_money` or catalog equivalent |
| Missing order ID | Empty/null `orderId` | Reject before business |
| Wrong amount type | Array/object | Reject `INVALID_AMOUNT_TYPE` |
| Zero amount | `0` | Processed per contract; not treated as missing |
| Email absent | No email key | `ABSENT` |
| Email explicit null | `"email":null` | `EXPLICIT_NULL` |
| Email blank | `"email":"  "` | `BLANK_EMAIL` |
| Invalid timestamp | Invalid offset | `INVALID_TIMESTAMP` |
| Unsupported version | Producer sends v9 | Reject/quarantine |
| Source mismatch | Header LEGACY, transport PARTNER | Reject/trust-boundary validation |
| Tenant mismatch | Payload `tenant-b`, principal `tenant-a` | Security reject |
| Lookup 503 | Required field needs enrichment | Retryable, no fake `UNKNOWN` |
| Duplicate raw event | Redelivery with same `eventId` | No duplicate business side effect |
| Two groups | Same `orderId`, different tenant/revision | Separate correlations |
| Splitter child failure | One invalid line after split | Failure outcome or whole-batch reject |
| Mapper bug | Null pointer inside mapping code | Application defect alert; do not blame source |
| Broker retry | Spring Message ID changes | Business identity stays stable |
| DLQ replay | Schema supported after migration | Reprocessed with policy/version/audit |

**Note:** error codes in the examples may still reflect field name/casing; production should use a `ReasonCode` enum or catalog independent of payload naming so `MISSING_currency` does not become a permanent API contract.

## 37. Property-Based and Metamorphic Tests to Catch Normalization Bugs

Beyond fixed examples, assert invariants:

1. **Same source+version+payload+policy → same canonical result.**
2. **No fabricated values:** absent email in v1 never becomes a fake string.
3. **No lost zeros:** amount 0 and boolean false stay intact per contract.
4. **No tenant mixing:** two payloads with the same `orderId` and different tenants remain distinct identities.
5. **Exact money conversion:** 12500 USD cents must equal `BigDecimal("125.00")`.
6. **Reject invalid types:** arrays/objects in scalar fields never cast silently.
7. **Version routing:** v2 never borrows v1 defaults.
8. **Field presence:** absent/null/present always preserve semantics.
9. **Mapping provenance:** record only fields that were actually defaulted.
10. **No side effects before validation:** malformed inputs never execute handlers.

Property-based testing (e.g., jqwik) can generate empty strings, Unicode, huge numbers, decimal scales, and nested objects to expose silent truncation or unclassified exceptions.

**You do not need a full property-based framework to start**; a data-driven JUnit table covering schema versions and presence states already delivers huge value.

## 38. Serialization of Canonical Field Presence

A Java type `FieldValue<String>` **does not automatically guarantee** wire formats express absent/null/present as intended. If the system publishes canonical messages over Kafka or HTTP, define an explicit schema for tri-state.

An explicit JSON representation:

~~~json
{
  "canonicalVersion": "1",
  "orderId": "O-502",
  "email": {
    "presence": "EXPLICIT_NULL",
    "value": null
  }
}
~~~

With a real value:

~~~json
{
  "email": {
    "presence": "PRESENT",
    "value": "buyer@example.org"
  }
}
~~~

When `presence=ABSENT`, the contract can choose either:

- Keep the wrapper `{"presence":"ABSENT","value":null}` to **preserve tri-state explicitly**; or
- Omit the `email` property on serialization and use a parser capable of detecting absence.

Pick **one strategy** and test end-to-end; never let a `NON_NULL` serializer strip `value` so consumers misread absence, or let a deserializer collapse null and missing.

With Avro/Protobuf, optional/union/presence semantics differ from JSON; design schemas per technology. **Never assume Java `null` equals JSON null or absent fields across every transport.**

## 39. Scalability: Separate Mappers per Source, Yet Bound Resources

Because a Normalizer sits **ahead of every business branch**, it can become a bottleneck:

~~~text
N inbound producers
  → Router/Normalizer CPU
  → Canonical validation
  → Downstream workers
~~~

Design bounds:

| Resource | Risk | Mitigation |
|---|---|---|
| JSON parse | Huge/deeply nested payloads | Max bytes, nesting depth, token count |
| String numeric parse | Multi-million-digit decimals | Max length/precision |
| Regex/validation | Catastrophic backtracking | Safe regexes, timeout/size limits |
| Transformer CPU | Many complex input schemas | Profiling, bounded concurrency |
| Content Enricher I/O | Fan-out lookups cause overload | Bounded executors, quotas, proper caching |
| Error/quarantine store | Broken producer sends millions of bad messages | Rate limits, retention, storage quotas |
| Output message volume | Normalized order splits into N lines | Cap N before Splitter |

**Normalize as early as possible without absorbing all business logic.** A Transformer should execute deterministically against an input contract, rather than calling three external services to “try to fill every field” when a source omits most data.

When flows run asynchronously, know which thread executes mapping errors and which error channel/container handler receives them; an upstream `send()` returning `true` does not prove mapping and business logic finished.

## 40. Data Security: Source, Tenant, and Optional PII

A source could send:

~~~text
headers.sourceSystem=LEGACY
headers.tenantId=tenant-b
payload.order_no=O-501
payload.buyer.email=somebody@example.org
~~~

If untrusted, it might **claim to be LEGACY** to exploit v1 defaulting rules or swap tenants to inject into another group.

Necessary controls:

1. Determine source from **authenticated adapters, permissioned topics/queues, or partner credentials**.
2. Determine tenant from trusted context and validate payload tenant if present.
3. Enforce allowed source/version combinations; a v2 producer must not claim v1 to skip required fields.
4. Restrict raw headers/properties copied onto new messages.
5. Handle email/address and PII according to consent and business purpose; keep them out of unnecessary logs.
6. Apply encryption, access control, retention, and auditing on quarantined raw payloads.
7. Never use correlation IDs as authorization tokens.

**A value defaulted in line with the technical contract does not grant business permission to use it everywhere.** A real email address might still lack marketing consent; presence and consent are separate concerns.

## 41. Observability: Tracking Defaults, Missing Fields, and Mapping Errors

These metrics are **suggestions**, not guaranteed built-ins in Spring Integration:

| Metric | Detects |
|---|---|
| `normalizer.received.count` | Traffic by source/version |
| `normalizer.completed.count` | Total canonical outputs |
| `normalizer.rejected.count` | Permanently rejected inputs |
| `normalizer.failed.count` | Mapper/infra errors |
| `normalizer.default.applied.count` | Fields defaulted per policy |
| `normalizer.missing.field.count` | Absent fields |
| `normalizer.explicit.null.count` | Explicit nulls |
| `normalizer.unsupported.schema.count` | Out-of-contract source/versions |
| `normalizer.currency.invalid.count` | Money mapping errors |
| `normalizer.conversion.duration` | Latency by mapper/source |
| `normalizer.enrichment.retry.count` | Lookup retries |
| `normalizer.enrichment.timeout.count` | Dependency timeouts |
| `normalizer.quarantine.pending.count` | Backlog of bad inputs |
| `normalizer.canonical.validation.failed.count` | Mapper emitted out-of-contract output |

Keep tags low-cardinality: `sourceSystem`, bounded `schemaVersion`, `reasonCode`, allowlisted `fieldName`, `policyVersion`. **Never use `orderId`, `eventId`, `customerEmail`, or raw payloads as metric tags.**

Protected structured logs/traces can show:

~~~text
eventId=EV-501
sourceSystem=LEGACY
sourceSchemaVersion=1
mappingPolicyVersion=legacy-map-1
canonicalVersion=1
defaultedFields=["money.currency"]
missingFields=["email"]
normalizationOutcome=ACCEPTED
orderId=O-501
~~~

Never log untrusted raw emails/addresses, secrets, or large payloads for debugging. When raw inspection is needed, use a protected quarantine reference with access control.

## 42. Runbook When Downstream Reports Missing or Wrong Fields

1. **Identify the wrong output:** was the field genuinely absent, explicit null, blank, or defaulted?
2. **Check canonical schema version:** does downstream understand the presence contract?
3. **Check source/version:** did the message enter the right Transformer?
4. **Check trust boundary:** were `sourceSystem`/tenant read from credentials or raw headers?
5. **Inspect raw schema (with authorization):** did the source include the field with the right type?
6. **Inspect mapping rules:** were field renames, units, or defaults applied for the right source/version?
7. **Inspect provenance:** which fields were defaulted under which `policyVersion`?
8. **Inspect serializer:** did a presence wrapper or JSON null get stripped?
9. **Inspect Content Enricher:** was the lookup a definitive miss or a 503 timeout?
10. **Inspect Router/Filter:** are unsupported schemas rejected or falling into an old branch?
11. **Inspect correlation/idempotency:** did retries mint new event/group IDs or mix groups?
12. **Inspect Splitter/Aggregator:** did bad data enter children and skew partial results?
13. **Controlled recovery:** fix mapping/schema, run contract tests, then reprocess with audit/idempotency—never blindly replay messages that already caused side effects.

A classic warning sign: `default.applied` spikes suddenly after a source upgrades versions. That often signals the source **dropped an important field** or the Router misrouted it—not “an improvement because the normalizer rejects fewer messages”.

## 43. Common Misconceptions

**“Normalizer is just renaming fields.”** Only partly true. It also governs types, units, presence, validation, defaulting policies, and schema/version routing.

**“Spring Integration has an `@Normalizer` that handles every schema automatically.”** Do not assume a magic endpoint exists; EIP Normalizer is typically a composition of Router and Transformers.

**“An omitted field and a null field are identical.”** Not in patch/update contracts and many event schemas.

**“`Optional<T>` is always enough to represent missing fields.”** Not when distinguishing missing from explicit null.

**“Zero, false, and empty all mean missing.”** Wrong. Zero and false can be valid values; empty depends on the contract.

**“If a required field is missing, pick any default so the code runs.”** Wrong. Defaults are valid only when the source/version **guarantees the semantics**.

**“Legacy v1 uses USD, so any source missing currency is USD.”** Wrong. Fallbacks are scoped to source/version, never global.

**“`Instant.now()` fixes a missing timestamp.”** Wrong when the field represents original business event time; `ingestedAt` is a separate field.

**“Jackson mapping to a DTO without error is sufficient validation.”** No. Requiredness, blankness, money scale, `schemaVersion`, and authorization still need checking.

**“JSON numbers and Java `double` work for all monetary math.”** No. Use `BigDecimal`/minor units and currency policies.

**“If Content Enricher times out, treat the field as unknown and continue.”** Not if the field is required; a timeout is a dependency failure.

**“After normalization, provenance no longer matters.”** With multiple sources/versions and defaulting rules, dropping provenance breaks auditing and schema migrations.

**“If a new version parses with the old mapper, it is definitely compatible.”** Not if semantics, units, or requiredness changed.

**“One canonical schema makes every consumer understand null automatically.”** No; you need explicit contracts, documentation, and tests.

**“Correlation metadata survives every broker adapter automatically.”** Not guaranteed; verify wire contracts and header mapping tests.

**“An invalid field after a Splitter can be dropped and Aggregator will still finish cleanly.”** Not if the group lacks members; define explicit failure outcomes or policies.

## 44. Checklist for Designing an Operable Normalizer

Before onboarding a new source, verify:

- Inventoried all **source+schema versions** and their owners.
- Defined a **canonical contract version** independent of individual sources.
- Documented required, optional, nullable, and patch semantics per field.
- Tested policies for **absent/null/blank/zero/false**.
- Allowed defaults only where guaranteed by source contract, scoped by **source/version**.
- Converted money/timezones/precision with explicit checks.
- Sourced identity and tenant scope from trusted boundaries.
- Kept mapping/validation free of side effects before data is verified.
- Routed unknown/unsupported schemas to explicit rejection paths, never silent fallbacks.
- Separated permanent input errors from transient dependency failures in error mapping.
- Recorded **provenance** for critical defaults/mapping policies.
- Preserved correlation and idempotency across Router/Transformer/broker boundaries.
- Provided rejection replies on Gateways instead of silent drops causing pointless timeouts.
- Defined manifest/member outcome policies for Splitter/Aggregator.
- Built contract tests, unit tests, transport integration tests, metrics, and runbooks.

**A fully checked checklist without end-to-end tests still does not prove correctness.** Verify at least raw input decoding, source/version routing, mapping, and the canonical consumer together.

## 45. Hands-On Exercise: Adding a Fourth Schema Without Touching Business Handlers

Build a mini project **OrderMessageNormalizer** with the three introduced sources, then add **Partner v3**:

1. Define `CanonicalOrder`, `CanonicalMoney`, `FieldValue<T>`, and `SourceInfo`.
2. Write the schema contract table for Legacy v1, Partner v2, and Mobile v3.
3. Implement `normalizeLegacyV1` with the USD fallback scoped strictly to the legacy contract.
4. Implement `normalizePartnerV2` using Jackson `JsonNode` for `buyer.email` absent/null/present.
5. Implement `normalizeMobileV3` from `money.value`, `money.isoCurrency`, `contactEmail`, and `placedAt`.
6. Use a Java DSL Router to pick the transformer by trusted source/version.
7. Build a canonical validator and rejection flow carrying `reasonCode`.
8. Attach a Gateway accepting inputs and returning canonical results or typed rejections.
9. Wire a broker adapter simulating stripped custom headers; verify business IDs remain in the canonical contract.
10. Add a Content Enricher for a required field, simulating 404 vs. HTTP 503 differently.
11. Split a normalized order into line jobs; verify Aggregator never mixes groups or falsely succeeds when a child is invalid.
12. Run tests for money conversion, missing/null/zero, unsupported versions, tenant mismatches, mapping replays, and DLQs.
13. Build a dashboard for rejection rate, applied defaults, latency, and enrichment timeouts.
14. **Add Partner v3 with renamed fields**; replace/add adapter/mapper/router while **leaving Inventory/Pricing business handlers untouched** if the canonical contract stays unchanged.
15. Write a migration plan for when the canonical contract must change breaking semantics.

**Completion criteria:** three different sources with identical semantic inputs yield equivalent canonical results; missing fields are never filled arbitrarily; v1 defaults are audited while v2/v3 missing currency reject; email absent vs. null remains distinct; logical correlation stays stable across retries; adding a new source does not couple business handlers to source schemas.

## 46. Key Takeaways

**Handling missing fields across schemas** lies at the heart of a trustworthy **Message Normalizer**. A Normalizer brings multiple data shapes into a **canonical contract**—often combining **Router + Transformer**—yet **must never fabricate values that the source omitted or the contract does not guarantee**.

Distinguish **absent, explicit null, blank, zero, and concrete values**; classify fields as **required, optional, nullable, or defaulted by source/version**; enrich only from authoritative sources; route parse/schema errors to proper rejection paths while handling dependency outages with controlled retries. For money and time, keep **units, currency, scale, and timezone** exact. For events crossing Gateway, Filter, Splitter, Aggregator, and brokers, keep **business identity, correlation, and idempotency** stable.

A strong Normalizer lets business handlers understand just one shared contract while missing or invalid data is **preserved accurately or rejected transparently**. Measure default and rejection rates, store provenance where needed, test both raw bytes and canonical outputs, and version mapping rules so schema evolution never silently alters business outcomes.

### References

- Enterprise Integration Patterns, **Normalizer**: https://www.enterpriseintegrationpatterns.com/patterns/messaging/Normalizer.html
- Enterprise Integration Patterns, **Message Translator**: https://www.enterpriseintegrationpatterns.com/patterns/messaging/MessageTranslator.html
- Enterprise Integration Patterns, **Content-Based Router**: https://www.enterpriseintegrationpatterns.com/patterns/messaging/ContentBasedRouter.html
- Spring Integration Reference, **Router**: https://docs.spring.io/spring-integration/reference/router.html
- Spring Integration Reference, **Transformer**: https://docs.spring.io/spring-integration/reference/transformer.html
- Spring Integration Reference, **Content Enricher**: https://docs.spring.io/spring-integration/reference/content-enrichment.html
- Spring Integration Reference, **Message Filter**: https://docs.spring.io/spring-integration/reference/filter.html
- Spring Integration Reference, **Error Handling**: https://docs.spring.io/spring-integration/reference/error-handling.html
- Spring Integration Reference, **Aggregator**: https://docs.spring.io/spring-integration/reference/aggregator.html
