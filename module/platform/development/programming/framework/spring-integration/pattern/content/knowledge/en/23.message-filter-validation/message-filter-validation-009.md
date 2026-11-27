# Post-Transformer Validation

> **Chapter:** Message filter and validation  
> **Module:** `SPRING_INTEGRATION_PATTERN` — learning to implement Enterprise Integration Patterns with Spring Integration to build loosely coupled, extensible message flows; practicing Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation, while testing and observing processing branches. This lesson focuses on **validating data after converting it to the canonical model**, before data is allowed into handlers with business side effects.

## 1. Learning Outcomes

After this lesson, you will be able to:

1. Explain why **a successful Transformer does not guarantee a valid message** and when validation is needed both before and after a Transformer.
2. Distinguish **structural validation**, **canonical/domain validation**, **cross-field validation**, **authorization**, and **business-state validation** by responsibility boundary.
3. Design the sequence `Input → Validate transport/schema → Transformer → Validate canonical payload → Filter/Router → Handler` to prevent invalid commands from reaching target systems.
4. Use Spring Integration Java DSL with `.transform(...)`, `.filter(...)`, `.route(...)`, `discardChannel`, and error channels without conflating **business rejections** with **technical exceptions**.
5. Produce **typed** validation outcomes carrying error codes and field paths instead of silently dropping messages when callers need explanations.
6. Integrate Jakarta Bean Validation where appropriate while handling cross-field rules, quantity bounds, and policies backed by authoritative data.
7. Test both accepted and rejected branches, parsing failures inside Transformers, metadata/correlation, duplicates, Splitter/Aggregator interactions, and forbidden side effects.
8. Apply security, idempotency, observability, and error handling so validation never leaks data or stalls workflows.

## 2. Scenario: Partner Sends Orders Using Its Own Schema

A system receives orders from a partner. Source data carries string-typed fields:

~~~json
{
  "tenantId": "shop-a",
  "partnerOrderId": "PO-901",
  "sku": "book-42",
  "quantityText": "003",
  "unitPriceMinorText": "25000",
  "currency": "vnd"
}
~~~

The application must transform this into an internal model:

~~~json
{
  "tenantId": "shop-a",
  "orderId": "PO-901",
  "sku": "BOOK-42",
  "quantity": 3,
  "unitPriceMinor": 25000,
  "currency": "VND"
}
~~~

A Transformer can parse and normalize cleanly yet still emit **rule-violating** data:

~~~json
{
  "tenantId": "shop-a",
  "orderId": "PO-902",
  "sku": "BOOK-42",
  "quantity": -3,
  "unitPriceMinor": 25000,
  "currency": "VND"
}
~~~

`"-3"` is a **parseable** integer, yet a negative quantity **cannot place an order**. Likewise, a syntactically valid `currency` may fall outside the supported currency set; a `long`-valid price may overflow when multiplied by quantity.

Therefore, place **a validation step on the canonical model after the Transformer**:

~~~mermaid
flowchart LR
    IN["Message<ExternalOrder>"] --> PRE["Validate source / schema"]
    PRE --> TR["Transformer: parse + normalize"]
    TR --> VA{"Validate CanonicalOrder"}
    VA -->|"Valid"| OK["Business handlers / Gateway"]
    VA -->|"Invalid"| REJ["RejectionResult / audit"]
    TR -->|"Conversion error"| ERR["Error handling / quarantine"]
~~~

**Invariant to maintain:** No message violating canonical policy ever reaches an endpoint that performs side effects such as reserving stock, issuing invoices, or submitting payment commands.

## 3. Why Pre-Transformer Validation Is Not Enough

The two checkpoints address **different kinds of discrepancies**.

| Checkpoint | Question to answer | Example |
| --- | --- | --- |
| **Before Transformer** | Are the envelope, signature, schema, representation types, size, and source trustworthy? | Malformed JSON, unauthenticated tenant, oversized field |
| **Inside Transformer** | Can the payload be interpreted and normalized into canonical types? | `quantityText="abc"` cannot parse to `int` |
| **After Transformer** | Does the canonical DTO satisfy domain invariants? | Negative quantity, forbidden currency, total exceeds limit |
| **Before commit** | Does current system state permit the operation? | Insufficient stock, closed account |
| **After commit / audit** | Were outcomes recorded/measured accurately? | Operation ID persisted, outbox event exists |

### 3.1. Example of One Field Crossing Multiple Steps

~~~text
Raw quantityText = " 003 "
    |
    |  Structural validation: field is String, length-bounded
    v
Transformer: trim + parse Integer
    |
    v
Canonical quantity = 3
    |
    |  Domain validation: 1 <= quantity <= 500
    v
Business handler: atomically reserve 3 units
~~~

For `"0"`, the Transformer succeeds; **post-Transformer validation** catches the violation. For `"not-a-number"`, the Transformer cannot construct the canonical object; it needs a dedicated **transformation error** rather than forcing `quantity=0` for convenience.

### 3.2. When to Check Both Inside and After the Transformer?

Before transformation, block huge, deeply nested, or dangerous structures from entering parsers. After transformation, recheck invariants altered by normalization, defaulting, enum mapping, or unit conversion.

Examples:

- `currency="usd"` becomes `"USD"`: then check against the supported set.
- `"001"` becomes `1`: then check quantity bounds.
- Source price expressed in minor currency units: verify parsing, currency unit, and total multiplication.
- Mapper fills a default for a missing field: post-transform validation decides whether that default is valid for this operation.
- Router needs a canonical `countryCode`: validation checks country before routing to prevent falling into an inappropriate default branch.

## 4. How Validation, Filter, Router, and Transformer Differ

| EIP component | Responsibility | What not to assume |
| --- | --- | --- |
| **Transformer** | Changes message/payload representation | Anything that converts is automatically valid |
| **Message Filter** | Lets messages proceed or blocks them via a condition | Filter always produces error explanations |
| **Router** | Sends messages to a target branch by key/condition | Router is sufficient validation |
| **Validator** | Checks invariants and produces coded violations | Validation replaces authorization |
| **Service Activator** | Executes business tasks | Handlers should parse every raw schema themselves |
| **Aggregator** | Combines results sharing a group | Filter dropping a child has no effect on release |
| **Error Channel** | Handles exceptions/error messages per topology | Every business rejection is a technical exception |

**A simple Filter** works well when only accept/reject is needed, such as blocking ineligible announcements from a channel. When an API/Gateway must report **why** a request was rejected, produce a typed validation outcome and route to a **rejection flow**.

### 4.1. Business Validation Does Not Mean Authorization

`quantity > 0` is domain validation. Whether tenant A may update tenant B's order is **authorization**. Passing DTO validation does not prove the principal has permission. Never accept a client-sent `validated=true` header in place of server-enforced authorization.

## 5. Pipeline Design Rules

~~~text
Inbound adapter / Gateway
  |
  +-- Authenticate source, validate tenant, request limits
  |
  v
ExternalOrder (parsed against source schema)
  |
  +-- Structural/contract validation
  |
  v
Transformer → CanonicalOrder
  |
  +-- Parse + normalize
  +-- Parse failure → transformation error path
  |
  v
Canonical domain validation
  |
  +-- Valid     → processing branch
  +-- Invalid   → typed rejection + audit + caller response
  |
  v
Idempotent receiver / authorization/state checks
  |
  v
Business handler / external Gateway
  |
  v
Persisted result / outbox / reply
~~~

**Place validation after the Transformer and before side effects.** Do not wait until an Inventory API call fails to discover a negative quantity; by then a domain error has turned into network traffic and unnecessary retries.

### 5.1. A Chain May Have Multiple Transformers

~~~text
JSON document → ExternalOrder → CanonicalOrder → ReserveStockCommand
                  |                |                 |
                schema        domain validation   command invariants
~~~

If a second Transformer **changes data meaning** (converting units, multiplying totals, merging lines, or switching currencies), re-verify the **invariants of the new output model**. A message valid in canonical form does not guarantee every downstream transformation preserves validity.

### 5.2. Every Field Needs a Source of Truth

| Field | Accepted source | Consequence of trusting the wrong source |
| --- | --- | --- |
| `tenantId` | Authenticated identity/principal | Cross-tenant routing and IDOR |
| `orderId` | Mapping under approved partner namespace | ID collisions across two partners |
| `quantity` | Parsed string, range-checked | Negative numbers/overflow |
| `unitPriceMinor` | Normalized schema/currency unit | Unit/currency mismatch, wrong billing |
| `sku` | Normalized + catalog lookup if needed | Router picks wrong branch |
| `operationId` | Business command identity created once | Retries cause duplicate side effects |

## 6. Designing Source and Canonical DTOs (Java 17)

Examples use Java records. Source numeric fields remain `String` to clearly distinguish **parsing errors** from **domain validation failures**.

~~~java
record ExternalOrder(
    String tenantId,
    String partnerOrderId,
    String sku,
    String quantityText,
    String unitPriceMinorText,
    String currency
) {}

record CanonicalOrder(
    String tenantId,
    String orderId,
    String sku,
    int quantity,
    long unitPriceMinor,
    String currency
) {}
~~~

Here, `CanonicalOrder` **is simply a record holding normalized data**, without enforcing every validation in itself. This lets us clearly teach the order: **the transformer may construct a DTO that still fails domain policy; the validator decides next**.

If a project enforces "invalid domain objects cannot be constructed", core invariants can live in domain value-object constructors, treating construction exceptions as validation errors. However, when collecting **multiple errors in one submission**, an intermediate DTO + validation outcome is usually more convenient.

### 6.1. Why Not Parse `quantityText` Directly at the Gateway?

If all partners share the exact same canonical schema, mapping can live early in the adapter. Yet when partner A sends `qty` as a string while partner B sends an integer, separating the **external contract** from the **canonical DTO** makes topologies and tests much clearer.

**Never let the mapper decide authorization.** `tenant` in the sample DTO is illustrative only; production must bind the authenticated tenant from a trusted inbound context and cross-check any payload field.

## 7. Transformer: Parse and Normalize Without Masking Errors

Sample code:

~~~java
import java.util.Locale;

final class ExternalOrderMapper {

    CanonicalOrder toCanonical(ExternalOrder source) {
        if (source == null) {
            throw new InvalidRepresentationException("NULL_SOURCE");
        }

        return new CanonicalOrder(
            text(source.tenantId()),
            text(source.partnerOrderId()),
            text(source.sku()).toUpperCase(Locale.ROOT),
            parseInt(source.quantityText(), "QUANTITY"),
            parseLong(source.unitPriceMinorText(), "PRICE_MINOR"),
            text(source.currency()).toUpperCase(Locale.ROOT)
        );
    }

    private static String text(String value) {
        return value == null ? "" : value.strip();
    }

    private static String requiredText(String value, String name) {
        String result = text(value);
        if (result.isEmpty()) {
            throw new InvalidRepresentationException(name + "_MISSING");
        }
        return result;
    }

    private static int parseInt(String raw, String name) {
        try {
            return Integer.parseInt(requiredText(raw, name));
        } catch (NumberFormatException ex) {
            throw new InvalidRepresentationException(
                name + "_NOT_INTEGER", ex);
        }
    }

    private static long parseLong(String raw, String name) {
        try {
            return Long.parseLong(requiredText(raw, name));
        } catch (NumberFormatException ex) {
            throw new InvalidRepresentationException(
                name + "_NOT_INTEGER", ex);
        }
    }
}

final class InvalidRepresentationException extends RuntimeException {
    InvalidRepresentationException(String code) {
        super(code);
    }

    InvalidRepresentationException(String code, Throwable cause) {
        super(code, cause);
    }
}
~~~

**Key examples:**

| Input | Transformer | Downstream validator |
| --- | --- | --- |
| `quantityText=" 003 "` | Produces `quantity=3` | Accepts if within bounds |
| `quantityText="-3"` | Produces `quantity=-3` | Rejects `QUANTITY_OUT_OF_RANGE` |
| `quantityText="abc"` | Throws `QUANTITY_NOT_INTEGER` | **Does not run** because no canonical DTO exists |
| `currency=" vnd "` | Produces `currency="VND"` | Checks membership in allowed set |
| `currency="xyz"` | Produces `currency="XYZ"` | Rejects `UNSUPPORTED_CURRENCY` |
| `price="999999999999999999999"` | Throws `PRICE_MINOR_NOT_INTEGER` | Does not run |
| `sku=" "` | Produces `sku=""` | Rejects `SKU_REQUIRED` |

Never silently default `quantity=0` on parse failure. If defaults are used, there must be an **approved policy** preserving source provenance; otherwise representation errors get disguised as hard-to-debug domain errors.

### 7.1. No I/O or Side Effects Inside the Mapper

An ideal Transformer for this lesson is **deterministic**: identical verified input yields identical output. Never call stock reservation APIs, send emails, or write to databases inside `toCanonical`. Doing so turns parse retries into business retries and makes tests hard to isolate.

If SKU or exchange-rate lookups are needed, use a dedicated enrichment step with caching/versioned policies and **recheck domain invariants** after enrichment.

### 7.2. Normalization Can Cause Collisions

Two source codes `"book-42"` and `"BOOK-42"` both become `"BOOK-42"`. That may be right if business logic treats SKUs case-insensitively, yet wrong for case-sensitive partners. Normalization rules belong in the **contract**, not just "to look pretty".

## 8. Post-Transformer Validator: Structured Error Codes

To return rejection reasons instead of dropping messages, define DTOs:

~~~java
import java.util.List;
import java.util.Objects;

record ValidationIssue(String field, String code) {
    ValidationIssue {
        Objects.requireNonNull(field, "field");
        Objects.requireNonNull(code, "code");
    }
}

record ValidationOutcome(
    CanonicalOrder order,
    List<ValidationIssue> issues
) {
    ValidationOutcome {
        Objects.requireNonNull(order, "order");
        issues = List.copyOf(issues);
    }

    boolean valid() {
        return issues.isEmpty();
    }
}

record RejectionNotice(
    String orderId,
    List<ValidationIssue> issues
) {
    RejectionNotice {
        issues = List.copyOf(issues);
    }
}
~~~

Never return raw sensitive data inside `ValidationIssue`. Most errors can be expressed as **field name + error code**; public APIs can map codes to locale-specific user messages.

### 8.1. Pure Java Business Validator

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Set;

final class OrderPolicyValidator {

    private static final int MAX_QUANTITY = 500;
    private static final long MAX_UNIT_PRICE_MINOR = 1_000_000_000L;

    private static final Set<String> SUPPORTED_CURRENCIES =
        Set.of("VND", "USD");

    ValidationOutcome inspect(CanonicalOrder order) {
        List<ValidationIssue> issues = new ArrayList<>();

        if (order.tenantId().isBlank()) {
            issues.add(new ValidationIssue(
                "tenantId", "TENANT_REQUIRED"));
        }

        if (order.orderId().isBlank()) {
            issues.add(new ValidationIssue(
                "orderId", "ORDER_ID_REQUIRED"));
        }

        if (!order.sku().matches("[A-Z0-9-]{1,64}")) {
            issues.add(new ValidationIssue(
                "sku", "SKU_FORMAT_INVALID"));
        }

        if (order.quantity() < 1
                || order.quantity() > MAX_QUANTITY) {
            issues.add(new ValidationIssue(
                "quantity", "QUANTITY_OUT_OF_RANGE"));
        }

        if (order.unitPriceMinor() < 0
                || order.unitPriceMinor() > MAX_UNIT_PRICE_MINOR) {
            issues.add(new ValidationIssue(
                "unitPriceMinor", "PRICE_OUT_OF_RANGE"));
        }

        if (!SUPPORTED_CURRENCIES.contains(order.currency())) {
            issues.add(new ValidationIssue(
                "currency", "UNSUPPORTED_CURRENCY"));
        }

        // Cross-field guard: total price must fit in a long.
        if (order.quantity() > 0 && order.unitPriceMinor() >= 0) {
            try {
                Math.multiplyExact(
                    (long) order.quantity(), order.unitPriceMinor());
            } catch (ArithmeticException ex) {
                issues.add(new ValidationIssue(
                    "totalPriceMinor", "TOTAL_OVERFLOW"));
            }
        }

        return new ValidationOutcome(order, issues);
    }
}
~~~

**Intentional point:** the validator does not throw exceptions for expected domain violations like negative quantities or unsupported currencies. It returns a **list of issues** so a rejection flow can inform the sender and write controlled audits.

However, not every condition belongs in a pure validator. **System-state checks** such as current inventory or account status can change immediately after validation. Those conditions must be confirmed at **transaction/commit** time inside the business handler.

### 8.2. Limits Must Be Decided by Business Policy

Sample bounds `MAX_QUANTITY=500` and `MAX_UNIT_PRICE_MINOR=1_000_000_000` are illustrative only. Production must set limits by tenant, item category, currency/scale, and policy version. Never apply a lesson's default limits across all systems.

### 8.3. Why Check for Overflow?

When monetary values are stored in integer `minor units`, multiplying `quantity * unitPriceMinor` can exceed `Long.MAX_VALUE` even though each field parsed cleanly. Use `Math.multiplyExact` (or `BigInteger`/`BigDecimal` with explicit rounding and scale) instead of silently overflowing into negative or wrapped numbers.

## 9. Spring Integration Java DSL: Transformer → ValidationOutcome → Router

The configuration below is **a complete in-JVM flow example**: ingest `ExternalOrder`, normalize into `CanonicalOrder`, evaluate policy, and route to the accepted or rejected branch.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
class PostTransformValidationConfiguration {

    @Bean("orders.raw.in")
    DirectChannel input() {
        return new DirectChannel();
    }

    @Bean("orders.validated")
    DirectChannel validated() {
        return new DirectChannel();
    }

    @Bean("orders.rejected")
    DirectChannel rejected() {
        return new DirectChannel();
    }

    @Bean("orders.business")
    QueueChannel business() {
        return new QueueChannel();
    }

    @Bean("orders.rejections.out")
    QueueChannel rejectedNotices() {
        return new QueueChannel();
    }

    @Bean
    ExternalOrderMapper externalOrderMapper() {
        return new ExternalOrderMapper();
    }

    @Bean
    OrderPolicyValidator orderPolicyValidator() {
        return new OrderPolicyValidator();
    }

    @Bean
    IntegrationFlow transformThenValidate(
            ExternalOrderMapper mapper,
            OrderPolicyValidator validator) {

        return IntegrationFlow.from("orders.raw.in")
            .transform(ExternalOrder.class, mapper::toCanonical)
            .transform(CanonicalOrder.class, validator::inspect)
            .route(
                ValidationOutcome.class,
                outcome -> outcome.valid() ? "VALID" : "INVALID",
                r -> r.channelMapping("VALID", "orders.validated")
                      .channelMapping("INVALID", "orders.rejected"))
            .get();
    }

    @Bean
    IntegrationFlow acceptedOrders() {
        return IntegrationFlow.from("orders.validated")
            .transform(ValidationOutcome.class, ValidationOutcome::order)
            .channel("orders.business")
            .get();
    }

    @Bean
    IntegrationFlow rejectedOrders() {
        return IntegrationFlow.from("orders.rejected")
            .transform(ValidationOutcome.class, outcome ->
                new RejectionNotice(
                    outcome.order().orderId(), outcome.issues()))
            .channel("orders.rejections.out")
            .get();
    }
}
~~~

**Design meaning:**

- `orders.raw.in` accepts only `ExternalOrder` inputs from an already-checked boundary.
- The first Transformer converts to `CanonicalOrder`; parse failures are classified as transformation errors.
- The next Transformer creates a `ValidationOutcome` with issues.
- The Router sends `VALID` to the handler expecting **canonical payloads**, and `INVALID` to the rejection branch.
- The rejection branch emits a `RejectionNotice`, **never sending invalid payloads to business handlers**.
- `QueueChannel` is an observation point for tests, not proof of business completion or durable persistence.

### 9.1. Why Route Instead of Filter in the Main Example?

Because the requirement needs **rejection reasons returned**. A Boolean-based Filter can block messages, yet cannot automatically carry the violation list. Using `ValidationOutcome` and a Router gives both flows **explicit contracts**.

Note that Java DSL overload names can vary across Spring Integration versions. Examples follow modern Java DSL patterns and must be compiled/tested against your project's version during later Content QA; this STEP 4 NEW only authors documentation and has not run a build.

### 9.2. `ValidationOutcome` Is Not a Business Command

After the Router, `acceptedOrders` unwraps `CanonicalOrder`. Avoid sending the raw `ValidationOutcome` to inventory since warehouse consumers do not need validation details. Conversely, never send `RejectionNotice` into the stock-reservation channel, which causes contract confusion or runtime cast errors.

### 9.3. Headers and Correlation Across Transformers

Spring Integration transformers handle messages and headers per implementation/configuration. Verify that **permitted metadata** such as `businessCorrelationId`, `executionId`, and `replyChannel`/`errorChannel` remain valid at each boundary.

Specifically, never assume:

- The envelope's Message ID always equals the original message's ID.
- A `validated=true` header proves the caller is authorized.
- The source payload's `contentType` still describes the post-Transformer payload.
- Headers holding principals/credentials are safe to send to a broker.
- A Transformer automatically preserves every custom header across HTTP/JMS/Kafka adapters.

## 10. Variant: Use a Message Filter When Only Accept/Drop Is Needed

For simple use cases that do not need to report multiple rejection reasons, place `.filter(...)` after `.transform(...)`:

~~~java
@Bean
IntegrationFlow simpleFilterAfterTransform(
        ExternalOrderMapper mapper,
        OrderPolicyValidator validator) {

    return IntegrationFlow.from("orders.simple.in")
        .transform(ExternalOrder.class, mapper::toCanonical)
        .filter(
            CanonicalOrder.class,
            canonical -> validator.inspect(canonical).valid(),
            spec -> spec.discardChannel("orders.invalid.out"))
        .channel("orders.simple.accepted")
        .get();
}
~~~

This is a **code fragment variant** requiring corresponding channels and beans when wired into an application. Meaning:

1. Message transforms into `CanonicalOrder`.
2. Predicate returns `true` when there are no issues.
3. Valid messages proceed.
4. Failing messages go to `discardChannel` per configuration.

**`discardChannel` receives the Filter-blocked message**, not automatically a `RejectionNotice` with an error list. If errors are needed, compute them **before the Filter**, attach trusted headers, or switch to the typed-outcome pattern in section 9.

### 10.1. What Effect Does `throwExceptionOnRejection` Have?

A Message Filter can be configured to **throw an exception on rejection** via its API. This helps when rejections must immediately fail a request–reply call and callers know how to map the exception. However, **avoid** using it for all validation errors in asynchronous flows, because exceptions can trigger repeated retries of **the exact same invalid data**.

Distinction:

| Goal | Recommendation |
| --- | --- |
| Ignore unneeded messages where no reply is expected | Filter drop per contract |
| Route excluded messages to a channel | `discardChannel` |
| Return business error list to caller | Typed `ValidationOutcome` → rejection branch |
| Fail a synchronous request cleanly | Exception mapped to domain error |
| Handle unexpected parse/I/O failures | Error channel/retry/quarantine by failure type |

A Gateway awaiting a response **can time out** if a Filter drops the message without a discard/reply flow. Designing **reply presence** is therefore just as important as the predicate itself.

## 11. Bean Validation After the Transformer

Instead of hand-coding every constraint, you can use **Jakarta Bean Validation** (e.g., Hibernate Validator matching your Spring Boot version). Annotations cover simple field constraints:

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;

record AnnotatedCanonicalOrder(
    @NotBlank String tenantId,
    @NotBlank String orderId,
    @Pattern(regexp = "[A-Z0-9-]{1,64}") String sku,
    @Min(1) @Max(500) int quantity,
    @Min(0) long unitPriceMinor,
    @Pattern(regexp = "VND|USD") String currency
) {}
~~~

After the Transformer produces the annotated DTO, explicitly invoke `Validator.validate(...)`:

~~~java
import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;
import java.util.Set;

final class BeanValidationInspector {
    private final Validator validator;

    BeanValidationInspector(Validator validator) {
        this.validator = validator;
    }

    Set<ConstraintViolation<AnnotatedCanonicalOrder>> inspect(
            AnnotatedCanonicalOrder order) {
        return validator.validate(order);
    }
}
~~~

**Remember:** placing annotations on a record does not mean **any Transformer creating that record automatically runs Bean Validation**. Validation must be triggered explicitly by an integration endpoint, service method validation, or a properly configured interceptor.

### 11.1. Bean Validation Does Not Replace Cross-Field and State Validation

Custom constraints can check `quantity × price`, yet rules depending on inventory or balances at commit time are poorly suited to stale cache reads inside a validator.

A solid pipeline can combine:

~~~text
Bean Validation (shape + field constraints)
   +
Custom Domain Rules (cross-field and policy)
   +
Transactional Business Preconditions (at commit)
~~~

### 11.2. Validation Groups by Version/Use Case

When one canonical model serves multiple contexts, define **validation groups** or separate DTOs for `CreateOrder` vs `AmendOrder`. If creation requires `currency` while partial updates allow omitting it, do not apply a single undifferentiated rule regardless of command type.

Rules need **policy/schema versions** when messages may retry or replay from a DLQ after code upgrades. Identical bytes may be judged differently once rules evolve; contracts must state whether revalidation/reprocessing is allowed.

## 12. Parse Errors, Validation Errors, and Business Errors Need Separate Paths

| Error type | Example | Classification | Handling |
| --- | --- | --- | --- |
| **Representation** | `quantityText="xyz"` | Transformer cannot parse | Invalid input/parse error |
| **Canonical validation** | `quantity=-3` | DTO exists yet violates policy | `RejectionNotice` with code |
| **Authorization** | Another tenant's order | Principal lacks permission | Security error, no blind retry |
| **Transient technical** | DB timeout, HTTP 503 | Downstream may recover | Bounded retry/backoff |
| **Business-state conflict** | Out of stock, finalized order | Commit condition unmet | Terminal business outcome or conditional retry |
| **Integrity/schema drift** | Unsupported newer event version | Incompatible contract | Quarantine + schema handling |

### 12.1. Never Turn Every Error Into `false`

An anti-pattern:

~~~java
// DO NOT: DB outages get treated as "validation failed".
try {
    return remoteService.validate(order);
} catch (Exception ex) {
    return false;
}
~~~

If a remote call times out, you cannot conclude the order is invalid. Emit `UNKNOWN`/`VALIDATION_UNAVAILABLE` or route to an error/retry path. Boolean Filters fit deterministic conditions; they cannot represent **uncertain technical failures**.

### 12.2. Synchronous vs Asynchronous Errors

In flows using `DirectChannel`, exceptions from a Transformer or handler can **propagate to the sending thread**. In flows with `ExecutorChannel`, pollers, or broker adapters, errors may be wrapped as `ErrorMessage`s per endpoint/container mechanics and sent to an error channel if configured.

Do not write docs claiming `.filter(...)` rejections automatically cause Spring Integration to generate an `ErrorMessage`. **Rejection** and **exception** are two separate mechanisms.

### 12.3. Retrying the Exact Same Bad Data Only Amplifies Load

If `quantity=-3` is a terminal error, retrying via RabbitMQ/Kafka or `RequestHandlerRetryAdvice` will not make it valid. Route rejected messages to a dedicated channel for caller correction, or quarantine with TTL/retention and error-code audits. Never let them spin endlessly in DLQs/retry topics.

## 13. Post-Transformer Message Filter and Aggregator

An easy trap: **Splitter → Transformer → Filter → Aggregator**.

~~~text
Batch ORD-901: expected 3 order lines
   |
   v
Splitter: LINE-1, LINE-2, LINE-3
   |
   +--> LINE-1 → valid   → success result
   +--> LINE-2 → invalid → Filter drops silently
   +--> LINE-3 → valid   → success result
   |
   v
Aggregator: has 2/3, may wait forever
~~~

If the Aggregator waits for `sequenceSize=3` or three unique item IDs, silently dropping `LINE-2` ensures **the group never completes**.

### 13.1. Solution: Turn Validation Failures Into Typed Results

~~~text
LINE-1 → ItemOutcome(lineId=1, status=ACCEPTED)
LINE-2 → ItemOutcome(lineId=2, status=REJECTED,
                     codes=[QUANTITY_OUT_OF_RANGE])
LINE-3 → ItemOutcome(lineId=3, status=ACCEPTED)
          |
          v
Aggregator releases 3/3 → BatchOutcome(PARTIAL/REJECTED)
~~~

In this flow, **a rejection result is still an outcome for that item**, not a lost message. The Aggregator can release once all **unique line IDs** report in and produce the contract outcome.

### 13.2. Never Substitute `group.size()` for Unique Business IDs

If `LINE-1` is redelivered twice and `LINE-2` is dropped by the Filter, the Aggregator might receive:

~~~text
LINE-1: ACCEPTED
LINE-1: ACCEPTED (duplicate)
LINE-3: ACCEPTED
~~~

Three raw messages do not prove three distinct business items completed. Deduplicate on `(executionId, lineId)`; group correlation tracks execution, while side-effect idempotency uses separate command/line/operation keys.

### 13.3. Validation Failures Can Be Terminal Item Outcomes

Once `LINE-2` is confirmed **invalid**, the caller rarely wants it retried. Produce `ItemRejected` with codes and line ID, send it down a reply path accepted by the Aggregator; if the business contract mandates **all-or-nothing**, the Aggregator can still return `FAILED` for the whole batch despite having all three outcomes.

**Reply completeness** and **business success** are two independent dimensions.

## 14. Validation Before Router and Gateway

If a Router picks destinations from canonical fields like `currency` or `countryCode`, validate the key before routing. An ill-chosen default channel can send bad data to an endpoint with broader privileges.

~~~mermaid
flowchart LR
    IN["Raw order"] --> T["Transformer"]
    T --> V{"Validate canonical"}
    V -->|"Valid"| R{"Router by currency"}
    R -->|"VND"| VN["Domestic payment"]
    R -->|"USD"| US["International payment"]
    V -->|"Invalid"| E["Rejection"]
~~~

Key rules:

- Never route `currency="XYZ"` to a default payment channel only to discover later it is unsupported.
- Never pull `destinationTenant` from an unverified payload to pick a tenant-privileged channel.
- Restrict which client-supplied headers can influence routing before the Router reads them.
- When a Gateway sends side-effecting commands, preserve the idempotency key across Validator and Transformer.
- Validation should precede side-effect points, yet state-dependent preconditions still require checking inside the handler's transaction.

## 15. Unit Tests: Mapper and Validator

Both components are **pure Java** and fast to test with JUnit 5 without spinning up a Spring context.

### 15.1. Testing Mapping and Normalization

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class ExternalOrderMapperTest {

    private final ExternalOrderMapper mapper = new ExternalOrderMapper();

    @Test
    void normalizesValidPartnerOrder() {
        ExternalOrder raw = new ExternalOrder(
            "shop-a", "PO-901", " book-42 ",
            " 003 ", "25000", " vnd ");

        CanonicalOrder result = mapper.toCanonical(raw);

        assertEquals("BOOK-42", result.sku());
        assertEquals(3, result.quantity());
        assertEquals(25_000L, result.unitPriceMinor());
        assertEquals("VND", result.currency());
    }

    @Test
    void validIntegerRepresentationCanStillBeBadDomainData() {
        CanonicalOrder result = mapper.toCanonical(
            new ExternalOrder(
                "shop-a", "PO-902", "BOOK-42",
                "-3", "25000", "VND"));

        assertEquals(-3, result.quantity());
        assertFalse(new OrderPolicyValidator()
            .inspect(result).valid());
    }

    @Test
    void malformedQuantityFailsAtTransformerBoundary() {
        InvalidRepresentationException ex = assertThrows(
            InvalidRepresentationException.class,
            () -> mapper.toCanonical(new ExternalOrder(
                "shop-a", "PO-903", "BOOK-42",
                "three", "25000", "VND")));

        assertEquals("QUANTITY_NOT_INTEGER", ex.getMessage());
    }

    @Test
    void hugePriceCannotSilentlyOverflowDuringParsing() {
        assertThrows(InvalidRepresentationException.class,
            () -> mapper.toCanonical(new ExternalOrder(
                "shop-a", "PO-904", "BOOK-42",
                "1", "999999999999999999999", "VND")));
    }
}
~~~

### 15.2. Testing Validation and Error Codes

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.Set;
import java.util.stream.Collectors;
import org.junit.jupiter.api.Test;

class OrderPolicyValidatorTest {

    private final OrderPolicyValidator validator =
        new OrderPolicyValidator();

    @Test
    void acceptsCanonicalOrder() {
        CanonicalOrder order = new CanonicalOrder(
            "shop-a", "PO-901", "BOOK-42",
            3, 25_000L, "VND");

        ValidationOutcome result = validator.inspect(order);

        assertTrue(result.valid());
        assertTrue(result.issues().isEmpty());
    }

    @Test
    void collectsMoreThanOneDomainIssue() {
        CanonicalOrder order = new CanonicalOrder(
            "shop-a", "PO-902", "***",
            -3, -100, "XYZ");

        ValidationOutcome result = validator.inspect(order);
        Set<String> codes = result.issues().stream()
            .map(ValidationIssue::code)
            .collect(Collectors.toSet());

        assertFalse(result.valid());
        assertTrue(codes.contains("SKU_FORMAT_INVALID"));
        assertTrue(codes.contains("QUANTITY_OUT_OF_RANGE"));
        assertTrue(codes.contains("PRICE_OUT_OF_RANGE"));
        assertTrue(codes.contains("UNSUPPORTED_CURRENCY"));
    }

    @Test
    void rejectsQuantityAboveBusinessLimit() {
        ValidationOutcome result = validator.inspect(
            new CanonicalOrder(
                "shop-a", "PO-903", "BOOK-42",
                501, 25_000L, "VND"));

        assertTrue(result.issues().stream()
            .anyMatch(issue ->
                issue.code().equals("QUANTITY_OUT_OF_RANGE")));
    }
}
~~~

These tests only check mapping and validation **within the JVM**. They do not prove Spring Integration wiring or that errors route to the expected channels.

## 16. Integration Test: Accepted and Rejected Must Go to the Right Channels

Uses `PostTransformValidationConfiguration` from section 9. With `QueueChannel`, tests observe **one accepted output** and **one rejection notice**, while asserting the opposite branch received nothing.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(PostTransformValidationConfiguration.class)
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class PostTransformValidationFlowTest {

    @Autowired @Qualifier("orders.raw.in")
    MessageChannel input;

    @Autowired @Qualifier("orders.business")
    PollableChannel accepted;

    @Autowired @Qualifier("orders.rejections.out")
    PollableChannel rejected;

    private boolean send(
            String orderId, String quantityText, String currency) {
        ExternalOrder raw = new ExternalOrder(
            "shop-a", orderId, "book-42",
            quantityText, "25000", currency);

        return input.send(MessageBuilder.withPayload(raw)
            .setHeader("businessCorrelationId", orderId)
            .build());
    }

    @Test
    void validCanonicalOrderReachesBusinessBranchOnly() {
        assertTrue(send("PO-901", " 003 ", "vnd"));

        Message<?> approved = accepted.receive(1000);
        assertNotNull(approved);
        assertInstanceOf(CanonicalOrder.class, approved.getPayload());

        CanonicalOrder order = (CanonicalOrder) approved.getPayload();
        assertEquals("BOOK-42", order.sku());
        assertEquals(3, order.quantity());
        assertEquals("VND", order.currency());

        assertNull(rejected.receive(0),
            "Valid input must not reach rejection branch");
        assertNull(accepted.receive(0),
            "Exactly one canonical output expected");
    }

    @Test
    void invalidCanonicalOrderReachesRejectionOnly() {
        assertTrue(send("PO-902", "-3", "vnd"));

        Message<?> denied = rejected.receive(1000);
        assertNotNull(denied);
        assertInstanceOf(RejectionNotice.class, denied.getPayload());

        RejectionNotice notice =
            (RejectionNotice) denied.getPayload();

        assertEquals("PO-902", notice.orderId());
        assertTrue(notice.issues().stream()
            .anyMatch(issue ->
                "QUANTITY_OUT_OF_RANGE".equals(issue.code())));

        assertNull(accepted.receive(0),
            "Invalid order must not reach business branch");
        assertNull(rejected.receive(0),
            "Exactly one rejection notice expected");
    }

    @Test
    void normalizedButUnsupportedCurrencyIsRejected() {
        assertTrue(send("PO-903", "3", "xyz"));
        Message<?> denied = rejected.receive(1000);
        assertNotNull(denied);

        RejectionNotice notice =
            (RejectionNotice) denied.getPayload();

        assertTrue(notice.issues().stream()
            .anyMatch(issue ->
                "UNSUPPORTED_CURRENCY".equals(issue.code())));
        assertNull(accepted.receive(0));
    }
}
~~~

**Scope:** This is an integration test of channels and Transformers/Router **within a Spring context**; it does not test a real DB, broker, JWT, external API, or inventory transaction.

### 16.1. Parse Error Tests Differ from Rejection Tests

If `quantityText="abc"` is sent, the Transformer throws `InvalidRepresentationException` before any `ValidationOutcome` is built. On a `DirectChannel`, the exception can propagate wrapped in a `MessagingException`. Depending on exception wrapping and configuration, tests should assert the **root error code** and **zero output on business/rejection queues** when parse errors use a separate error path.

Do not expect it to turn into a `RejectionNotice` automatically; if an API requires a uniform error response, design **error-to-response mapping** at the boundary.

### 16.2. Assert the Unselected Branch Too

A test asserting only that `RejectionNotice` arrived misses bugs where bad data **simultaneously reached the business branch**. For pre-side-effect validation, negative assertions like `accepted.receive(0) == null` are essential.

When downstream runs asynchronously, test with bounded waits rather than calling `receive(0)` to "prove no message will ever arrive"; negative checks need proper synchronization and deadlines.

## 17. Comprehensive Test Matrix

| Scenario | Input | Expectation |
| --- | --- | --- |
| Valid | `quantityText="003"`, `currency="vnd"` | Canonical quantity=3, currency=VND, enters business |
| Negative number | `quantityText="-3"` | Mapper succeeds, validator rejects |
| Zero | `quantityText="0"` | Rejected per policy |
| Over limit | `quantityText="501"` | `QUANTITY_OUT_OF_RANGE` |
| Non-numeric text | `quantityText="three"` | Transformation error, no canonical created |
| Oversized number | Price string exceeds long | Parse error, no negative overflow |
| Whitespace SKU | `sku=" "` | `SKU_FORMAT_INVALID` |
| Lowercase SKU | `sku="book-42"` | Normalized if contract allows |
| Lowercase currency | `currency="vnd"` | Normalized and accepted |
| Unsupported currency | `currency="ABC"` | `UNSUPPORTED_CURRENCY` |
| Multiple errors on one DTO | Negative quantity, negative price, bad currency | Multiple coded issues |
| Spoofed tenant header | Principal tenant A, payload tenant B | Denied before side effects |
| Oversized message | Input exceeds size limit | Rejected before parse/transform |
| Null field | `tenantId=null` | Domain/structural rejection per contract |
| DB failure in business step | DB timeout | Technical retry/error, not treated as invalid input |
| Silent Filter drop | Gateway waiting for reply | Test catches missing rejection/timeout |
| Splitter 3 children, 1 invalid | One line blocked | Aggregator receives `ItemRejected` or handles group expiry |
| Duplicate child | Same `lineId` redelivered | Does not count as two business results |
| Reordered messages | Two interleaved executions | Correlation never mixes groups |
| Retry after commit | Lost ACK/redelivery | Idempotent handler executes no extra effect |
| Broker adapter | JMS/Kafka header mapper | Trusted metadata preserved per contract |
| Policy version changed | DLQ replay of old data | Handled via explicit versioning strategy |
| Rejection with PII | Sensitive input data | Responses/logs leak no raw values |
| Differing caller privileges | Two tenants using same ID | Authorization and scope block cross-access |

## 18. Versioned Validation and Stale Data in DLQs

Suppose policy at T1 allowed `quantity<=500`; a month later, policy tightens to `quantity<=100`. A message sitting in a DLQ and replayed at T2 has `quantity=300`.

Options:

1. **Revalidate under the new policy:** fits when the command was never accepted and current rules must apply; report reasons clearly.
2. **Pin the execution's policy version:** fits when the workflow was created under historical terms/pricing that must stay reproducible.
3. **Controlled migration:** migrate schema/policy, document meaning changes, and re-verify permissions.

Never silently push an old message through a new Transformer producing different data without auditing. `schemaVersion`, `policyVersion`, `receivedAt`, and trusted origin may be needed to explain why identical inputs yield different results at different times.

### 18.1. How Should Idempotency and Validation Be Ordered?

A duplicate of an already-committed operation may hit a **newer validation policy** that rejects old inputs. Never retry the same command and accidentally run a fresh business effect because idempotency lookup happened too late.

For side-effecting commands, authenticate source/tenant/operation identity first; then consider **checking the already-committed operation state** and returning the persisted outcome per contract while consistently validating requests. No single ordering fits every API, yet **policy changes must never bypass idempotency**.

### 18.2. A `validated` Header Can Go Stale

If a message passed validation at step A and Transformer B later alters currency, quantity, or ownership, step A's `validated=true` header **is no longer proof** that post-B data is valid. In sensitive pipelines, tie validation results to **model/schema/policy versions**, or revalidate at boundaries protecting invariants.

## 19. Observability: Measuring Rejections Without Leaking Data

Useful metrics:

| Measurement point | Metric / signal | Meaning |
| --- | --- | --- |
| Inbound | `inbound_invalid_schema_total` | Initial representation failures |
| Transformer | `transform_failed_total` by error category | Parse/mapping failures |
| Validator | `validation_passed_total` | Valid canonical messages |
| Validator | `validation_rejected_total` by error code | Domain violations |
| Router | `accepted_routed_total` | Valid messages taking right branch |
| Router | `rejection_routed_total` | Rejection path executed, no silent drop |
| Business handler | `side_effect_committed_total` | Actual business commits |
| Error channel | `technical_error_total` | Infrastructure errors distinct from rejections |
| Aggregator | `missing_child_outcome_total` | Dropped/failed children leaving groups short |
| Retry | `retry_attempts_total` | Detects retry storms from misclassified errors |

Labels like `validationCode`, `sourceType`, `schemaVersion`, and `endpoint` usually have bounded value sets. Never attach `orderId`, `tenantId`, email, or arbitrary `correlationId` as high-cardinality metric tags.

### 19.1. Controlled Rejection Logging

~~~json
{
  "event": "post_transform_validation_rejected",
  "businessCorrelationId": "PO-902",
  "schemaVersion": "external-order-v1",
  "policyVersion": "canonical-order-v1",
  "errorCodes": ["QUANTITY_OUT_OF_RANGE"],
  "branch": "orders.rejections.out"
}
~~~

This is an **illustrative application log schema**, not a built-in Spring Integration log. Cap field lengths, mask IDs/PII per policy, and avoid logging raw payloads, access tokens, or exposing stack traces to clients.

### 19.2. Validation Latency

A pure in-JVM validator is typically cheap. Calling multiple external APIs inside it drives up latency and retries. Separate deterministic validation from enrichment/state lookups and measure their latencies separately. Enforce resource limits on regexes, parsing, large arrays, and deep structures to prevent DoS.

## 20. Common Anti-Patterns

| Anti-pattern | Consequence | Better approach |
| --- | --- | --- |
| "Transformer parsed it, so it must be valid" | Negative quantities/bad prices reach handlers | Validate the canonical DTO |
| Validating only raw JSON, skipping canonical | Normalization/defaulting alters invariants | Validate after transform |
| Mapper returns `0` on parse failure | Masks representation errors | Throw typed parse error |
| Filter drops without replying to Gateway | Unexplained caller timeouts | Rejection branch/typed response |
| Throwing exceptions for every domain violation | Broker retries exact bad data | Classify terminal rejections |
| Filter catches all exceptions and returns false | DB outages look like bad data | Dedicated technical error path |
| Trusting client-supplied `validated=true` header | Bypasses checks | Trusted validator and policy version |
| Validation replacing authorization | Cross-tenant side effects | AuthN/AuthZ at trusted boundaries |
| Non-contractual SKU normalization | Collides distinct codes | Versioned canonicalization |
| Assuming old `contentType` still holds post-transform | Mis-serialization/consumer misreads | Update content type metadata |
| Post-Splitter Filter dropping children | Aggregator waits forever on incomplete groups | `ItemRejected` or group expiry |
| Counting raw messages instead of unique item IDs | Duplicates trigger early release | Idempotent child correlation |
| Testing only the positive branch | Bad messages may still hit handlers | Assert negative branch and zero side effects |
| Extrapolating single-JVM tests to end-to-end | Misses adapter/DB/retry issues | Boundary-specific integration/contract tests |
| Missing length/range limits | Overflows, DoS, overload | Input limits + numeric checks |
| Returning raw payloads in rejections | Leaks sensitive data | Error codes, projections, masking |
| Revalidating DLQs ignoring policy versions | Replayed old data changes meaning | Versioned migrations/policy snapshots |
| Checking stock only before calling API | Races until commit time | Atomic business preconditions |

## 21. Implementation Checklist

- [ ] Validate input schema, size, authentication, and tenant **before** the Transformer.
- [ ] Transformer only parses/normalizes per contract; representation errors are never masked by arbitrary defaults.
- [ ] Canonical DTO has clear invariants tested for both field and cross-field rules.
- [ ] Post-Transformer validation sits **before Routers/Gateways/side-effecting handlers**.
- [ ] Criteria cleanly distinguish domain rejections, transient technical errors, and business-state failures.
- [ ] Callers needing feedback receive typed rejections with field/code, never silent drops.
- [ ] If using Filters, discard channel/reply semantics are explicitly tested.
- [ ] If using Bean Validation, `Validator.validate(...)` is actually invoked, not merely annotated on DTOs.
- [ ] Normalization rules and policies are versioned; post-upgrade replays follow contracts.
- [ ] Validation does not replace AuthN/AuthZ or transaction-state checks.
- [ ] Source/tenant/correlation/operation IDs are verified and propagated across required boundaries.
- [ ] Terminal bad data is never retried infinitely through retry topics/DLQs.
- [ ] Splitter/Aggregator use `ItemRejected` or release/expiry policies instead of silently losing messages.
- [ ] Unit tests cover Mapper/Validator and integration tests cover both branches, including the **disallowed branch**.
- [ ] Tests cover parse overflows, numeric bounds, invalid currencies, wrong tenants, and policy migration.
- [ ] Metrics track error categories and accepted/rejected counts without logging PII/raw tokens.
- [ ] Idempotency protects the point where business effects execute; passing a Filter does not guarantee exactly-once.

## 22. Practice Exercise

A system imports invoice batches from three partners. Each partner sends:

~~~json
{
  "partnerId": "partner-a",
  "invoiceNo": "INV-2026-51",
  "amountText": " 125000 ",
  "currencyText": " vnd ",
  "dueDateText": "2026-12-01",
  "customerRef": "CUST-51"
}
~~~

After the Transformer, the system expects `CanonicalInvoice(partnerId, invoiceNo, amountMinor, currency, dueDate, customerRef)`. Per policy:

- `amountMinor` must be greater than 0 and within invoice-type limits.
- `currency` is in the allowed set after normalization.
- `dueDate` must not precede the verified issue date.
- `invoiceNo` must match format and be unique within the partner namespace (enforce uniqueness **at commit** across concurrent instances).
- Tenant/partner identity must come from an authenticated source, not solely from payload fields.
- A batch may hold 100 invoices; callers need to know which invoices were rejected.

**Requirements:**

1. Sketch the flow `Inbound → Parse schema → Transformer → Bean Validation → Domain rules → Router accepted/rejected → Handler`.
2. Write Java records for the external invoice, canonical invoice, and `ValidationOutcome` holding error codes.
3. Classify `amountText="abc"`, `amountText="-1"`, `currencyText="xyz"`, and `dueDateText="not-a-date"`: which fail in the Transformer, and which fail after the Transformer?
4. Design validation for `amount × taxRate` without overflow and with explicit rounding rules.
5. Identify mandatory AuthN/AuthZ placement for partner identity and idempotency keys for `invoiceNo`.
6. Use Spring Integration Java DSL to transform data, evaluate policy, and route to the right branch.
7. Build a rejection DTO excluding `customerRef` and sensitive contents when callers lack permission.
8. Write JUnit tests for valid input, parse errors, negative amounts, unsupported currencies, missing fields, and cross-field rules.
9. Write an integration test proving rejected invoices **cannot reach** the ledger-posting handler.
10. If the flow uses Splitter/Aggregator, send `InvoiceRejected(invoiceNo, codes)` back to the group so a batch with 99/100 valid invoices never hangs.
11. For DLQ replays after 30 days, explain validator versioning and preventing duplicate invoice creation.
12. Design metrics for parse errors, domain rejections, duplicates/conflicts, and business commits without using customer IDs as tags.

**Hint:** Return a `BatchImportOutcome(total, imported, rejected, errorsByInvoice)` to the caller. **An invoice's rejection is still an item outcome**, though if the contract requires all-or-nothing, the batch outcome must reflect that without arbitrarily mutating `expectedCount`.

## 23. Summary

**Post-transformer validation** is the safeguard between **"data that changed representation"** and **"data permitted to execute business logic"**. Transformers normalize source schemas, numeric types, casing, and structures; validators then check quantities, amounts, currencies, cross-field invariants, and canonical policies. Successful parsing **does not prove domain correctness**, and single-point validation **does not replace authorization or atomic state checks at commit**.

In Spring Integration, combine `.transform(...)` with `.filter(...)` for simple conditions or with **`ValidationOutcome` + Router** to build accepted/rejected branches carrying typed error codes. Route representation errors, domain rejections, and technical failures along separate paths; never silently drop children before an Aggregator, never infinitely retry invalid data, and test both positive and negative paths. Combine Router, Splitter/Aggregator, Gateway, retry/error channels, correlation, and idempotency so only **valid, authorized canonical messages representing the right business operation** ever reach side-effecting endpoints.

**References:** Gregor Hohpe & Bobby Woolf, *Enterprise Integration Patterns* (Message Filter, Message Translator, Content-Based Router, Splitter, Aggregator); Spring Integration Reference on Message Filter, Transformers, Router, Java DSL, Message Channels, Error Handling, and Testing; Jakarta Bean Validation specification; Spring Framework validation/transaction management; Java SE on records, `Math.multiplyExact`, and `Locale.ROOT`.
