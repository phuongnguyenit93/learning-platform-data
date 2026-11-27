# Validating Data at the Boundary Before Running Business Logic

## 1. Lesson Objectives

Spring Cloud Function lets you encapsulate logic inside `Supplier`, `Function`, and `Consumer` beans, register them with `FunctionCatalog`, and compose them into pipelines invoked over Java, HTTP, event-driven systems, or serverless environments. However, that reusability creates a challenge: **the same function can receive input from multiple sources with varying levels of trust**.

An HTTP client may send JSON missing a field, a message may contain a payload with the wrong version, or a serverless trigger may be re-invoked with stale data. If business logic calculates prices, writes to a database, or publishes events before validating inputs, failures can cause unwanted and hard-to-recover side effects.

In the **Reliability** chapter, this lesson focuses on **validating data at the input boundary before running business logic**. After this lesson, you will be able to:

- Distinguish data validation, deserialization/type conversion, and authorization.
- Design a `normalize → validate → business → side effect` pipeline with clear Java types.
- Use Jakarta Bean Validation **explicitly** inside a Function bean.
- Understand why you cannot simply add `@Valid` to a DTO and assume `FunctionCatalog` will validate automatically.
- Classify input errors, business-rule errors, and infrastructure errors, and choose appropriate retry handling.
- Protect a side-effecting Consumer from bad data, redelivered data, and race conditions.
- Test validation in isolation, the full pipeline in `FunctionCatalog`, and HTTP/message/serverless adapters.

> Examples use Java 17, Spring Boot 3+, and the `jakarta.validation` namespace. For projects on other Spring Boot / Spring Cloud Function versions, choose compatible dependencies, namespaces, and adapter mechanisms. The validation examples in this lesson are **invoked explicitly** from a Function, rather than relying on unverified implicit validation behavior.

## 2. Where Does the "Boundary" Sit?

The boundary is not just an HTTP controller. With Spring Cloud Function, input can arrive from many paths:

~~~text
HTTP JSON ─────────┐
                   |
Kafka/Rabbit event ├──> Adapter / converter
                   |            |
Serverless event ──┤            v
                   |       Input DTO / Message<T>
Java caller ───────┘            |
                                v
                        normalizeInput
                                |
                                v
                        validateInput
                                |
                                v
                         businessLogic
                                |
                                v
                   Consumer / persist / publish
~~~

We typically have at least three layers of checks:

1. **Transport/conversion layer:** can the request or message be read? Is the JSON valid? Are number/string types right? Does the payload exceed size limits?
2. **DTO/validation layer:** are required fields present? Do values match the expected pattern? Are lengths/quantities within bounds?
3. **Business layer:** is the user authorized to perform the action? Is the SKU still active for sale? Does the quantity fit current limits or inventory? Has the order already been processed?

Do not lump these groups into a vague "validate" block. **Authorization** and identity verification belong in the proper security layer; Bean Validation cannot replace permission checks.

### 2.1. Error Classification Examples

| Input or Situation | Primary Detection Layer | Example Handling Direction |
|---|---|---|
| Unparseable JSON | Converter/HTTP adapter | Reject before entering the Function |
| Missing `quantity` field | DTO validation | Missing-field error |
| `quantity = -3` | DTO validation | Value-range error |
| `sku = "??"` | DTO validation | Format error |
| Well-formed SKU but discontinued | Business logic | Reject under current rules |
| Valid request but user lacks permission | Security/authorization | Deny access |
| Database timeout while writing | Infrastructure | Retryable per policy |
| Same order ID with different content | Consistency/idempotency | Conflict, do not overwrite silently |

Input errors **cannot fix themselves through retries** if the payload stays unchanged. Distinguish them from transient I/O errors.

## 3. Why Validate Before Business Logic?

Suppose a pipeline does not validate data first:

~~~text
Input → calculatePrice → saveQuote → validateOrder
~~~

If `quantity = 0`, `saveQuote` may already have written an invalid value before `validateOrder` throws an exception. If the messaging system retries after the error, the side effect can repeat.

A safer design:

~~~text
Input → normalize → validate → calculatePrice → saveQuote
                         |                          |
                         | error: stop before write | side effect
                         v                          v
                      Reject                  Idempotent storage
~~~

In synchronous Java, when the validation Function throws an exception, downstream steps do not run normally. This does not replace transactions or idempotency, but it **reduces the scope of side effects when input is invalid**.

### 3.1. "Validate Early" Does Not Mean Validating Everything Twice

A client may have UI validation for quick feedback, yet **the server must validate again** because clients and payloads are untrusted.

On the other hand, syntactic checks on the same object should not be needlessly duplicated across layers. Assign clear responsibilities: the converter confirms structure; Function validation confirms the DTO contract; business logic checks conditions requiring current state.

## 4. Designing the Input Contract

Suppose a quote service receives JSON matching:

~~~json
{
  "orderId": "  ord-42 ",
  "sku": " sku-7 ",
  "quantity": 2
}
~~~

Requirements:

- After normalization, `orderId` has the form `ORD-<1 to 10 digits>`.
- After normalization, `sku` has the form `SKU-<1 to 10 digits>`.
- `quantity` is an integer between 1 and 100.
- Do not use unvalidated data to calculate prices or write records.

We use three domain types:

~~~text
OrderRequest (data received by adapter)
       |
       v
ValidatedOrder (passed validation)
       |
       v
Quote (business result)
~~~

Using an intermediate type avoids confusing `Function<OrderRequest,Quote>` with a function that must only accept validated input.

## 5. Declaring the DTO with Jakarta Bean Validation

Example using records in Java 17:

~~~java
package example.functions;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;

public final class OrderModels {

    private OrderModels() {}

    public record OrderRequest(
            @NotBlank
            @Pattern(regexp = "ORD-[0-9]{1,10}")
            String orderId,

            @NotBlank
            @Pattern(regexp = "SKU-[0-9]{1,10}")
            String sku,

            @NotNull
            @Min(1)
            @Max(100)
            Integer quantity) {}

    public record ValidatedOrder(
            String orderId,
            String sku,
            int quantity) {}

    public record Quote(
            String orderId,
            String sku,
            int quantity,
            long totalVnd) {}
}
~~~

Each annotation serves a distinct role:

| Annotation | Constraint | Example Fields |
|---|---|---|
| `@NotBlank` | Non-null string, not solely whitespace | `orderId`, `sku` |
| `@Pattern` | String matches regex; null is ignored by this constraint | `orderId`, `sku` |
| `@NotNull` | Value must be present | `quantity` |
| `@Min(1)` | At least 1 | `quantity` |
| `@Max(100)` | At most 100 | `quantity` |

`quantity` uses `Integer` rather than `int` so it can represent a **missing** field after deserialization (null). With primitive `int`, some binding mechanisms supply a default value of 0, making it harder to tell "missing field" apart from "sender entered 0".

The regexes in the example are intentionally simple and bounded. On large payloads or complex regexes, limit payload size before validation and avoid patterns prone to excessive CPU consumption.

### 5.1. Annotations Do Not Run Just Because an Object Exists

Constructing:

~~~java
OrderModels.OrderRequest request =
        new OrderModels.OrderRequest("BAD", "SKU-7", 2);
~~~

**does not automatically throw an error** just because the record has `@Pattern`. Constraints are evaluated only when a validation mechanism actually calls `Validator.validate(...)`, or when the framework is configured to invoke validation at the appropriate boundary.

Likewise, do not assume `FunctionCatalog.lookup(...).apply(request)` automatically inspects annotations and rejects inputs. In this lesson, we **register a dedicated validation Function and call Validator explicitly**.

## 6. Adding the Right Validation Dependency Version

With Spring Boot 3+ (Java 17 or newer), you typically use the starter:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

The starter provides the Jakarta Bean Validation API and an implementation matching the Boot version managed by the BOM. The application still needs a compatible Spring Cloud Function context/starter to provide `FunctionCatalog`.

If an older project uses `javax.validation`, do not switch blindly to `jakarta.validation` without checking Spring Boot / Spring Framework compatibility. Use a consistent set of versions.

Note: some applications include only `spring-cloud-function-context` without Spring Web. They can still use `Validator` directly; validation does not require an HTTP controller.

## 7. Splitting Normalization and Validation into Two Functions

Raw input can contain whitespace or lowercase letters. We want **intentional normalization first**, followed by validation against the canonical format.

~~~text
OrderRequest("  ord-42 ", " sku-7 ", 2)
                     |
                     v
normalizeOrderRequest
                     |
                     v
OrderRequest("ORD-42", "SKU-7", 2)
                     |
                     v
validateOrderRequest
                     |
                     v
ValidatedOrder("ORD-42", "SKU-7", 2)
~~~

Normalization must not silently hide important errors. For instance, do not truncate overly long strings or rewrite an invalid SKU into another code to "pass validation." Apply only normalizations permitted by the business contract.

### 7.1. Explicit Validation Error Type

~~~java
package example.functions;

import java.util.List;

public class InvalidOrderException extends RuntimeException {

    private final List<String> violations;

    public InvalidOrderException(List<String> violations) {
        super("Invalid order request");
        this.violations = List.copyOf(violations);
    }

    public List<String> violations() {
        return violations;
    }
}
~~~

This error represents invalid input according to the DTO contract. Do not use it to mask database timeouts or security errors. When returning error details externally, expose only appropriate information and avoid leaking raw payloads, tokens, or sensitive content in responses or logs.

### 7.2. Configuring the Function Beans

~~~java
package example.functions;

import java.util.List;
import java.util.Locale;
import java.util.function.Function;

import jakarta.validation.Validator;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import example.functions.OrderModels.OrderRequest;
import example.functions.OrderModels.ValidatedOrder;
import example.functions.OrderModels.Quote;

@Configuration
public class OrderFunctions {

    private static String canonical(String input) {
        return input == null
                ? null
                : input.trim().toUpperCase(Locale.ROOT);
    }

    @Bean
    public Function<OrderRequest, OrderRequest> normalizeOrderRequest() {
        return input -> {
            if (input == null) {
                throw new InvalidOrderException(
                        List.of("body: required"));
            }

            return new OrderRequest(
                    canonical(input.orderId()),
                    canonical(input.sku()),
                    input.quantity());
        };
    }

    @Bean
    public Function<OrderRequest, ValidatedOrder> validateOrderRequest(
            Validator validator) {

        return input -> {
            if (input == null) {
                throw new InvalidOrderException(
                        List.of("body: required"));
            }

            List<String> errors = validator.validate(input)
                    .stream()
                    .map(v -> v.getPropertyPath()
                            + ": " + v.getMessage())
                    .sorted()
                    .toList();

            if (!errors.isEmpty()) {
                throw new InvalidOrderException(errors);
            }

            return new ValidatedOrder(
                    input.orderId(),
                    input.sku(),
                    input.quantity());
        };
    }

    @Bean
    public Function<ValidatedOrder, Quote> calculateQuote() {
        return order -> new Quote(
                order.orderId(),
                order.sku(),
                order.quantity(),
                Math.multiplyExact(
                        order.quantity(), 125_000L));
    }
}
~~~

Assume `Validator` is registered in the Spring context by compatible validation configuration. The line `validator.validate(input)` is where **validation actually executes**—not merely the annotations on the DTO.

After validation succeeds, the pipeline receives `ValidatedOrder`. Java unboxes `Integer` to `int` when constructing the object; because `@NotNull` was checked beforehand, the value is non-null on the success path.

### 7.3. The Order Cannot Be Changed Arbitrarily

If `validateOrderRequest` is placed before `normalizeOrderRequest`, input `" ord-42 "` will fail the canonical regex even though surrounding whitespace is allowed by the business rules. If `calculateQuote` is placed before validation, it lacks a contract accepting `OrderRequest` and could run on invalid data.

The intended order is:

~~~text
normalizeOrderRequest
        |
        v
validateOrderRequest
        |
        v
calculateQuote
~~~

Each step's output must match the next step's input; `String`, `OrderRequest`, `ValidatedOrder`, and `Quote` cannot be swapped simply because they have similar fields.

## 8. Dynamic Business Rules Must Still Be Checked

Bean Validation is useful for the DTO contract, but cannot replace all business logic.

For example, SKU `SKU-7` matches the regex yet is currently discontinued; `quantity=20` is within 1..100 yet inventory only has 4 left. These facts depend on the system's current state.

One way to separate concerns:

~~~text
Adapter / deserialize
         |
normalizeOrderRequest
         |
validateOrderRequest          (DTO constraints)
         |
loadCatalogOrInventory         (read external data)
         |
decideOrder                   (business rules from snapshot)
         |
persist / publish             (side effect)
~~~

If validation depends on external data, do not claim it is a pure Function just because it has the signature `Function<T,R>`. When possible, pass a data snapshot in an explicit input type and keep the decision step deterministic.

### 8.1. Authorization Is Not Bean Validation

A request with a valid `orderId` and `sku` can still be sent by a user lacking permission to act. Security must verify identity/authorization at the appropriate trust boundary.

Do not put an access token into a DTO regex and treat that as an authorization check. Nor should you rely solely on a client-supplied `userId` to determine ownership; trusted identity must be established by authentication/authorization mechanisms.

## 9. Composing Functions with FunctionCatalog

Spring Cloud Function registers Function beans by name. With the beans from section 7, the quote-calculation pipeline can be looked up:

~~~java
package example.functions;

import java.util.function.Function;

import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.stereotype.Service;

import example.functions.OrderModels.OrderRequest;
import example.functions.OrderModels.Quote;

@Service
public class QuoteService {

    private final FunctionCatalog catalog;

    public QuoteService(FunctionCatalog catalog) {
        this.catalog = catalog;
    }

    public Quote quote(OrderRequest request) {
        Function<OrderRequest, Quote> pipeline = catalog.lookup(
                "normalizeOrderRequest|validateOrderRequest|calculateQuote");

        if (pipeline == null) {
            throw new IllegalStateException(
                    "Quote pipeline not found");
        }

        return pipeline.apply(request);
    }
}
~~~

Execution flows from left to right:

~~~text
OrderRequest
    |
    v
normalizeOrderRequest    Function<OrderRequest,OrderRequest>
    |
    v
validateOrderRequest     Function<OrderRequest,ValidatedOrder>
    |
    v
calculateQuote           Function<ValidatedOrder,Quote>
    |
    v
Quote
~~~

The result for `new OrderRequest(" ord-42 "," sku-7 ",2)` is a `Quote` with `orderId="ORD-42"`, `sku="SKU-7"`, `quantity=2`, and `totalVnd=250000`.

Note: the bean names in the `lookup` expression are a string literal, so the compiler cannot check that the names exist or that generic types align across every step. Integration tests must verify the chain against the exact Spring context used by the application.

## 10. Placing a Side-Effecting Consumer After Validation

Suppose the system needs to save quotes. Separate a port for the side effect:

~~~java
package example.functions;

import example.functions.OrderModels.Quote;

public interface QuoteSink {
    void save(Quote quote);
}
~~~

Register the Consumer:

~~~java
package example.functions;

import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import example.functions.OrderModels.Quote;

@Configuration
public class QuoteSinkFunctions {

    @Bean
    public Consumer<Quote> saveQuote(QuoteSink sink) {
        return sink::save;
    }
}
~~~

Then the write pipeline is:

~~~text
normalizeOrderRequest|validateOrderRequest|calculateQuote|saveQuote
        ⇒ Consumer<OrderRequest>
~~~

`saveQuote` runs **after** validation and calculation succeed. It does not return a `Quote`, so you cannot append another Function afterward and expect the Consumer to forward output.

### 10.1. A Simple Implementation for Testing

~~~java
package example.functions;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.stereotype.Component;

import example.functions.OrderModels.Quote;

@Component
public class InMemoryQuoteSink implements QuoteSink {

    private final ConcurrentHashMap<String, Quote> records =
            new ConcurrentHashMap<>();

    @Override
    public void save(Quote quote) {
        Quote old = records.putIfAbsent(
                quote.orderId(), quote);

        if (old != null && !old.equals(quote)) {
            throw new IllegalStateException(
                    "Same orderId with different quotes");
        }
    }

    public Quote find(String orderId) {
        return records.get(orderId);
    }

    public int size() {
        return records.size();
    }

    public Map<String, Quote> snapshot() {
        return Map.copyOf(records);
    }

    public void clear() {
        records.clear();
    }
}
~~~

`putIfAbsent` prevents creating two records for the same `orderId` within one JVM instance, and detects conflicts when the same key arrives with a different payload. This is only an in-memory example; **it provides no persistence, multi-replica unique constraints, or broker transactions**.

### 10.2. Calling the Consumer Pipeline

~~~java
import java.util.function.Consumer;

import example.functions.OrderModels.OrderRequest;

Consumer<OrderRequest> pipeline = catalog.lookup(
        "normalizeOrderRequest|validateOrderRequest"
        + "|calculateQuote|saveQuote");

if (pipeline == null) {
    throw new IllegalStateException("Missing consumer pipeline");
}

pipeline.accept(new OrderRequest(" ord-42 ", " sku-7 ", 2));
~~~

Data is validated before writing. If called with `quantity=0`, `validateOrderRequest` throws `InvalidOrderException` and `saveQuote` is not invoked in the synchronous flow.

## 11. What Counts as "Enough Validation"?

A common mistake is assuming a few annotations solve every data issue.

### 11.1. Aspects Typically Requiring Checks

| Aspect | Example | Appropriate Layer |
|---|---|---|
| Payload structure | Valid JSON, matching types | Converter/adapter |
| Required values | `orderId`, `quantity` not missing | DTO validation |
| Size limits | Body size, abnormally long strings | Gateway/adapter + DTO |
| Format | `ORD-42`, `SKU-7` | DTO validation |
| Value ranges | `1 <= quantity <= 100` | DTO validation |
| Cross-field constraints | End date not before start date | Custom validator or business logic |
| Dynamic rules | Item still on sale, sufficient stock | Business service |
| Access control | Is this customer allowed to place orders? | Authentication/authorization |
| Duplicate prevention | Same `orderId` / idempotency key | Storage/transaction |

Minimum checks must apply on **every entry path** that can bring untrusted data to business logic. Do not validate only in an HTTP controller if the same Function can also be invoked from Kafka or serverless triggers.

### 11.2. Null, Missing Fields, and Type Mismatches Differ

If JSON contains `"quantity": "abc"`, the converter may fail before `OrderRequest` is built. If the `quantity` field is absent, the DTO may be built with `quantity=null` and `@NotNull` catches it.

If JSON contains `"quantity": 0`, the DTO is built and `@Min(1)` catches it. These three cases occur at different layers and may require distinct error codes and observability.

### 11.3. Nested Fields

If a request has child objects, `@Valid` on a nested field instructs the validator to cascade validation when `Validator.validate(...)` is called on the parent object.

However, `@Valid` is a **cascade directive**, not proof that Spring Cloud Function triggers validation automatically. Verify explicitly where `Validator` is invoked, including when nested objects are deserialized from JSON.

## 12. Errors Should Have a Clear Contract

In the example, `InvalidOrderException` holds a list of violations. It is important to **classify errors before applying retries**:

| Error | Example | Retry the Same Payload? |
|---|---|---|
| Unreadable payload | Malformed JSON | Usually no |
| Invalid DTO | Missing `quantity`, malformed SKU | Usually no |
| Business rule rejection | Discontinued SKU | Depends on policy; no infinite retry |
| Unauthorized | User lacks permission | Never use retries to bypass security |
| Transient error | Database timeout | Yes, if the operation is idempotent |
| Idempotency conflict | Same `orderId` with different payload | Usually report conflict |
| Uncertain commit outcome | Lost ack/response | Check state or perform idempotent retry |

If a Consumer catches every exception and ignores it, the adapter may treat processing as successful and acknowledge the message even though data was never saved. Let errors propagate or map them explicitly per policy instead of swallowing them silently.

## 13. HTTP: Distinguishing Function Validation from Controller Validation

With a REST controller that calls `QuoteService` directly, the input pipeline can be controlled explicitly:

~~~java
package example.functions;

import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import example.functions.OrderModels.OrderRequest;
import example.functions.OrderModels.Quote;

@RestController
@RequestMapping("/quotes")
public class QuoteController {

    private final QuoteService service;

    public QuoteController(QuoteService service) {
        this.service = service;
    }

    @PostMapping
    public Quote quote(@RequestBody OrderRequest request) {
        return service.quote(request);
    }
}
~~~

Here **it is `validateOrderRequest` inside the pipeline** that calls `Validator`. The controller does not need `@Valid` on the parameter to run the same validation. If you choose to validate at the controller via `@Valid @RequestBody`, verify whether messaging or serverless entry paths enforce the same constraints.

One way to map `InvalidOrderException` to HTTP 400:

~~~java
package example.functions;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class OrderErrorHandler {

    @ExceptionHandler(InvalidOrderException.class)
    public ResponseEntity<Map<String, Object>> invalidOrder(
            InvalidOrderException ex) {

        return ResponseEntity
                .status(HttpStatus.BAD_REQUEST)
                .body(Map.of(
                        "code", "INVALID_ORDER",
                        "violations", ex.violations()));
    }
}
~~~

Illustrative response:

~~~json
{
  "code": "INVALID_ORDER",
  "violations": ["quantity: must be greater than or equal to 1"]
}
~~~

Actual validation messages depend on the provider and locale, so clients **should not rely on exact wording**. Production APIs should return stable error codes, limit exposed details, and handle JSON parse failures separately (such as `HttpMessageNotReadableException` before the Function runs).

### 13.1. The HTTP Adapter Can Differ from a Custom Controller

Spring Cloud Function has its own web adapter when an application uses the corresponding starter. Endpoint exposure, request/response conversion, and exception mapping can differ from a hand-written `@RestController`.

Do not assume the example's `@RestControllerAdvice` governs every adapter or automatically applies to serverless handlers. Test the actual invocation path being deployed.

## 14. Events: Handling Poison Messages Before Side Effects

In Spring Cloud Stream, input can arrive as a message from a broker. A JSON payload may fail deserialization, or deserialize into a DTO that violates constraints.

~~~text
Broker Message
      |
      v
Binder / message converter
      |
      v
OrderRequest
      |
      v
normalizeOrderRequest
      |
      v
validateOrderRequest
      |
      +--- invalid → error policy / DLQ / observability
      |
      v
calculateQuote → saveQuote
      |
      v
Ack per binder policy
~~~

A **poison message** is a message that repeatedly causes processing to fail—for instance due to an invalid schema or unrecoverable data. If infinite retries are configured, it can cause an error loop or block valid messages.

Classify invalid-payload errors separately from transient errors, then decide whether to discard, route to a dead-letter queue, or respond otherwise per requirements. DLQ support, retries, ack configuration, and bindings depend on the broker, binder, and version; never infer them from `FunctionCatalog`.

### 14.1. Message Headers and schemaVersion

If an adapter uses `Message<OrderRequest>`, headers may carry `eventId`, `schemaVersion`, correlation ID, or transport metadata. When inspecting them:

- Trust only headers actually protected or guaranteed by the system.
- Check the schema version before interpreting data under a new contract.
- Preserve correlation IDs needed for observability without leaking sensitive data.
- Enforce idempotency by event identifier or business key to handle redeliveries.

`OrderRequest` and `Message<OrderRequest>` have different generic types. If a Function needs headers, declare the appropriate contract or add an adapter step that extracts the payload explicitly; do not assume all headers pass through every kind of composition automatically.

## 15. Serverless: Validation Must Run on Every Invocation

A serverless handler can receive events from HTTP, a queue, a scheduler, or an event bus. Execution conditions, conversion, and retries may differ, yet the general rule remains:

~~~text
Event → Deserialize → Validate → Business → Side effect
~~~

Do not assume that an event invoked by another cloud service always matches the schema. An event may be an older version, altered, missing fields, or redelivered after an error.

If the handler invokes the same Function beans, use **one shared validation step** to avoid rule drift between HTTP and serverless. How errors are reported back to the platform depends on the adapter, trigger, and provider retry configuration.

### 15.1. Do Not Use Retries to Fix Validation Errors

If a message has `quantity=-1`, retrying the exact same payload will keep failing. Retries make sense for transient connectivity failures, and side effects must still be protected by idempotency.

## 16. When Cross-Field Validation Is Needed

Field-level annotations handle many basic constraints. Yet conditions like "`endAt` must be after `startAt`" or "if `type=EXPRESS`, maximum quantity is 10" involve multiple fields.

You can write a dedicated domain Function:

~~~java
import java.util.function.Function;

record ShippingRequest(
        String type,
        int packageCount) {}

Function<ShippingRequest, ShippingRequest> checkShippingRule =
        request -> {
            if ("EXPRESS".equals(request.type())
                    && request.packageCount() > 10) {
                throw new IllegalArgumentException(
                        "EXPRESS supports at most 10 packages");
            }
            return request;
        };
~~~

The function returns the validated input so downstream pipeline steps still receive the data. If a rule must query inventory or permissions, it is no longer pure validation; design appropriate dependencies, transactions, or snapshots.

### 16.1. Do Not Turn Every Validation into a Boolean

If `validateOrder` returns `Boolean`, the next Function expecting `ValidatedOrder` has no input data. Return the validated object instead, or a structured result type with a Function that resolves error states before running business logic.

## 17. Reactive: Validate Before Creating Side Effects

In a reactive application, per-item Functions can be lifted into a `Flux` pipeline:

~~~java
import java.util.function.Function;

import reactor.core.publisher.Flux;

import example.functions.OrderModels.OrderRequest;
import example.functions.OrderModels.ValidatedOrder;
import example.functions.OrderModels.Quote;

Function<OrderRequest, OrderRequest> normalize =
        orderFunctions.normalizeOrderRequest();

Function<OrderRequest, ValidatedOrder> validate =
        orderFunctions.validateOrderRequest(validator);

Function<ValidatedOrder, Quote> calculate =
        orderFunctions.calculateQuote();

Function<Flux<OrderRequest>, Flux<Quote>> pipeline =
        flux -> flux
                .map(normalize)
                .map(validate)
                .map(calculate);
~~~

`orderFunctions` is the configured instance along with `Validator` present as a dependency in the Spring context. Each element flows in order: normalize → validate → calculate.

With Reactor, mappers typically run when a subscriber requests items. If validation throws `InvalidOrderException`, it generally becomes an `onError` signal; the stream terminates by default on an unhandled error.

### 17.1. One Bad Element Can Stop the Entire Flux

~~~java
Flux<OrderRequest> inputs = Flux.just(
        new OrderRequest("ORD-42", "SKU-7", 2),
        new OrderRequest("BAD", "SKU-7", 2),
        new OrderRequest("ORD-43", "SKU-8", 2));
~~~

Without a per-item error policy, `"BAD"` can terminate the stream before `ORD-43` is processed. Skipping, isolating, or continuing per message is a business and adapter decision—it does not happen automatically with `map`.

### 17.2. Side Effects in Reactive Flows Need Extra Protection

If a repository is called inside `doOnNext` or a mapper that gets retried or resubscribed, writes can repeat. Even with validation ahead of it, **valid duplicates** can still create duplicate side effects.

Avoid blocking I/O directly on event-loop threads; for reactive I/O, use appropriate clients and operators while controlling concurrency, backpressure, and error signals. Validation does not replace idempotency or transactions.

## 18. Testing Validation with Java/JUnit

Test constraints before adding brokers or controllers. With the Jakarta Validation starter, you can create a `Validator` in a unit test:

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.function.Function;

import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;

import org.junit.jupiter.api.Test;

import example.functions.OrderModels.OrderRequest;
import example.functions.OrderModels.ValidatedOrder;

class OrderValidationTest {

    @Test
    void normalizesBeforeCheckingConstraints() {
        try (ValidatorFactory factory =
                    Validation.buildDefaultValidatorFactory()) {

            Validator validator = factory.getValidator();
            OrderFunctions functions = new OrderFunctions();

            Function<OrderRequest, OrderRequest> normalize =
                    functions.normalizeOrderRequest();

            Function<OrderRequest, ValidatedOrder> validate =
                    functions.validateOrderRequest(validator);

            ValidatedOrder result = validate.apply(
                    normalize.apply(new OrderRequest(
                            " ord-42 ", " sku-7 ", 2)));

            assertEquals(
                    new ValidatedOrder("ORD-42", "SKU-7", 2),
                    result);
        }
    }

    @Test
    void rejectsMissingOrInvalidQuantity() {
        try (ValidatorFactory factory =
                    Validation.buildDefaultValidatorFactory()) {

            Function<OrderRequest, ValidatedOrder> validate =
                    new OrderFunctions()
                            .validateOrderRequest(
                                    factory.getValidator());

            assertThrows(InvalidOrderException.class,
                    () -> validate.apply(new OrderRequest(
                            "ORD-42", "SKU-7", null)));

            assertThrows(InvalidOrderException.class,
                    () -> validate.apply(new OrderRequest(
                            "ORD-42", "SKU-7", 0)));

            assertThrows(InvalidOrderException.class,
                    () -> validate.apply(new OrderRequest(
                            "ORD-42", "SKU-7", 101)));
        }
    }
}
~~~

This suite uses the Jakarta Validation provider on the classpath. These tests verify that `Validator` actually runs; no Spring Boot context is needed to test DTO rules.

### 18.1. Check the Error List Without Relying on Provider Ordering

Constraint violations may be returned in an unspecified order. In the example, the Function called `sorted()` for more stable output, though provider messages can still vary by locale.

A good test checks fields or structured error codes rather than comparing exact message prose verbatim. For public APIs, define stable error codes.

## 19. Integration Testing FunctionCatalog and Blocking Side Effects

Create the Spring Boot application class in package `example.functions`:

~~~java
package example.functions;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

With `OrderFunctions`, `QuoteSinkFunctions`, `InMemoryQuoteSink`, and Spring Cloud Function context on the classpath, test the name-composed pipelines:

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertNull;

import java.util.function.Consumer;
import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

import example.functions.OrderModels.OrderRequest;
import example.functions.OrderModels.Quote;

@SpringBootTest(classes = OrderApplication.class)
class OrderCatalogValidationTest {

    @Autowired
    FunctionCatalog catalog;

    @Autowired
    InMemoryQuoteSink sink;

    @Test
    void validPayloadIsNormalizedAndPriced() {
        Function<OrderRequest, Quote> pipeline = catalog.lookup(
                "normalizeOrderRequest|validateOrderRequest|calculateQuote");

        assertNotNull(pipeline);

        Quote quote = pipeline.apply(
                new OrderRequest(" ord-42 ", " sku-7 ", 2));

        assertEquals(
                new Quote("ORD-42", "SKU-7", 2, 250_000L),
                quote);
    }

    @Test
    void invalidRequestDoesNotReachSaveQuote() {
        Consumer<OrderRequest> pipeline = catalog.lookup(
                "normalizeOrderRequest|validateOrderRequest"
                + "|calculateQuote|saveQuote");

        assertNotNull(pipeline);

        assertThrows(InvalidOrderException.class,
                () -> pipeline.accept(
                    new OrderRequest("ORD-91", "SKU-7", 0)));

        assertNull(sink.find("ORD-91"));
    }

    @Test
    void repeatedValidRequestDoesNotDuplicateQuote() {
        Consumer<OrderRequest> pipeline = catalog.lookup(
                "normalizeOrderRequest|validateOrderRequest"
                + "|calculateQuote|saveQuote");

        assertNotNull(pipeline);

        OrderRequest request =
                new OrderRequest("ORD-92", "SKU-7", 2);

        pipeline.accept(request);
        pipeline.accept(request);

        assertEquals(
                new Quote("ORD-92", "SKU-7", 2, 250_000L),
                sink.find("ORD-92"));
    }
}
~~~

Distinct test keys keep the example readable, but do not replace an isolation strategy when multiple tests or contexts run in parallel. An in-memory store only verifies behavior inside one JVM; for production confidence, test unique constraints and transactions against a real database.

### 19.1. Negative Tests Must Also Verify No Side Effect Occurred

If a test checks only `InvalidOrderException`, you still do not know whether a write step ran before the exception was thrown. That is why the assertion `sink.find("ORD-91") == null` matters: it confirms the validation boundary genuinely blocks invalid writes.

## 20. Testing at the Adapter Boundary

Function unit tests and catalog integration tests **do not replace** adapter testing.

| Boundary | Test Scenario | What to Verify |
|---|---|---|
| HTTP | Malformed JSON | Rejected before business logic, proper error status |
| HTTP | `quantity=null` or `0` | Validation error returned, nothing written |
| HTTP | Valid input with whitespace | Normalized and returns expected Quote |
| Messaging | Un-deserializable payload | Binder handles per policy, no infinite poison loop |
| Messaging | Schema-valid DTO failing rules | Nothing written, error classified |
| Messaging | Redelivered message | Idempotency, ack/retry, and DLQ |
| Serverless | Missing fields, stale events | Validation runs consistently |
| Reactive | One invalid item mid-Flux | Error signal or continuation matches policy |
| Multi-instance | Same `orderId` from two workers | Storage enforces uniqueness |

When a valid request is resent after a timeout, validation will continue to pass—and that is **expected**. Preventing duplicate processing at that point belongs to idempotency/transactions, not Bean Validation.

## 21. Checklist When Designing a Validation Boundary

Before taking the pipeline to production, check:

1. Does every untrusted input source pass through a shared validation step or equivalent mechanism?
2. Are deserialization errors, DTO errors, business errors, and authorization errors distinguished?
3. Do constraints cover missing/null fields, regexes, lengths, and value bounds?
4. Are payload size and complexity bounded before parsing or regex evaluation?
5. Is normalization permitted by the contract, and does it run before validation as intended?
6. Is `Validator.validate(...)` actually invoked on the `FunctionCatalog` execution path?
7. Does business logic consume `ValidatedOrder` rather than unvalidated raw data?
8. Is the side-effecting Consumer placed after validation and protected against duplicates?
9. Do invalid inputs have a policy avoiding infinite retries, with appropriate observability/DLQ routing?
10. For HTTP, are error codes and exposed details stable without leaking sensitive data?
11. For messaging, are `schemaVersion`, `content-type`, and headers verified on the actual adapter?
12. Are unit tests, catalog integration tests, and adapter integration tests all in place?

Early validation makes pipelines predictable and reduces erroneous side effects, yet it does not replace security, transactions, or recovery mechanisms when infrastructure fails.

## 22. Common Pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| DTO has annotations but invalid data still passes | Nothing invokes Validator | Add explicit validation step or verify adapter `@Valid` support |
| Lowercase input gets rejected | Validation runs before normalization | Define canonical format and run steps in the right order |
| Missing quantity field is hard to distinguish | Using primitive `int` | Use `Integer` with `@NotNull` when distinction is needed |
| `quantity="abc"` does not produce `InvalidOrderException` | Converter fails before Function runs | Handle deserialization errors at the adapter |
| `saveQuote` runs on invalid data | Validation not on every entry path | Place validation before Consumer and test negative cases |
| Broker keeps retrying a bad message forever | Unclassified poison message | Bounded retry policy / DLQ / quarantine |
| Written twice even though validation passed | Validation does not handle duplicates | Idempotency key and storage uniqueness |
| Same key with different payload is ignored | Recorder fails to detect conflict | Compare payload/version and report conflict |
| Client receives internal details in errors | Exposing raw exceptions or payloads | Stable error codes, minimal details, safe logging |
| Reactive errors appear late | Mapper executes upon subscription | Test with `StepVerifier` and error signals |

## 23. Self-Practice Exercises

**Exercise 1 — Identifying the Boundary.** For HTTP JSON containing `quantity="abc"`, should the error be caught at the converter or Bean Validation? What about when `quantity` is `0`?

**Exercise 2 — No Automatic `@Valid`.** Why is declaring `@NotNull` and `@Pattern` on `OrderRequest` alone insufficient to guarantee `FunctionCatalog.lookup(...).apply(...)` always rejects invalid data?

**Exercise 3 — Designing a Pipeline.** Order `calculateQuote`, `normalizeOrderRequest`, and `validateOrderRequest` properly. State the input/output contract of the full chain.

**Exercise 4 — Consumer and Side Effects.** Append `saveQuote: Consumer<Quote>` to the pipeline. How does the overall contract change? Which method invokes it, and why can you not chain a Function after a Consumer?

**Exercise 5 — DTO and Null.** Why is `Integer quantity` more useful than `int quantity` when a client may omit the quantity field? Which constraint catches a missing value?

**Exercise 6 — Dynamic Rules.** A SKU matches the regex yet is out of stock. Is Bean Validation enough? Propose where to check inventory and how to prevent race conditions when multiple orders arrive concurrently.

**Exercise 7 — HTTP vs. Messaging.** A controller uses `@Valid`, whereas a Kafka consumer has no validation. What is the risk? Propose how to share validation.

**Exercise 8 — Retries and Poison Messages.** If JSON from a broker has `orderId="BAD"` permanently, do continuous retries help? Describe a quarantine/observability approach.

**Exercise 9 — Testing.** Write an assertion ensuring an input with `quantity=0` is rejected and does not create record `ORD-91` in the sink.

**Exercise 10 — Reactive.** A `Flux<OrderRequest>` contains three elements, with an invalid middle element. What normally happens with a default `map(validate)`? Contrast per-message handling with an error terminating the entire Flux.

### Suggested Answers

- **Exercise 1:** Type mismatch `"abc"` normally fails in the converter; `0` has the right type but violates `@Min(1)`.
- **Exercise 2:** Annotations are metadata; a mechanism must invoke `Validator.validate(...)` or explicitly configured validation integration.
- **Exercise 3:** `normalizeOrderRequest|validateOrderRequest|calculateQuote`, contract `Function<OrderRequest,Quote>`.
- **Exercise 4:** Appending `|saveQuote` produces `Consumer<OrderRequest>` invoked via `accept(...)`; a Consumer returns `void`.
- **Exercise 5:** `Integer` represents null; `@NotNull` detects a missing quantity.
- **Exercise 6:** Check inventory at the business/storage layer with an appropriate reservation/transaction mechanism.
- **Exercise 7:** Input via Kafka can bypass validation; place a shared validation Function ahead of business logic on all entry paths.
- **Exercise 8:** Infinite retries cannot fix invalid data; classify the error, route to quarantine/DLQ, and alert operations.
- **Exercise 9:** `assertThrows(InvalidOrderException.class, () -> pipeline.accept(invalid)); assertNull(sink.find("ORD-91"));`.
- **Exercise 10:** A failing mapper typically emits `onError` and terminates the Flux; continuing per message requires designing an appropriate error-handling boundary.

## 24. Key Takeaways

- **Validating input before business logic and side effects** limits writing or publishing bad data.
- Deserialization, Bean Validation, authorization, and business-rule checks are **distinct boundaries** that must be handled with the right responsibilities.
- Annotations such as `@NotNull`, `@Pattern`, and `@Min` do not run automatically; in Spring Cloud Function, ensure a validation mechanism is explicitly invoked.
- The `normalize → validate → calculate → consume` pipeline clarifies data states and keeps the side-effecting Consumer at the end.
- `FunctionCatalog` and `spring.cloud.function.definition` compose/select functions; they do not automatically provide security, retries, DLQs, transactions, or idempotency.
- Permanently invalid data should usually not be retried indefinitely. Valid redelivered data requires storage-level duplicate prevention.
- For HTTP, events, serverless, and reactive flows, verify input/conversion, errors, headers, retries, and side-effect safety in the **actual adapter**.