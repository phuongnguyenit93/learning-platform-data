# Designing Input/Output Contracts and Handling Invalid Data

In **SPRING_CLOUD_FUNCTION**, a business function can be invoked over HTTP, events, or serverless environments without rewriting its logic. The prerequisite for safe reuse is that **the data contract** must be sufficiently explicit: what types the function accepts, which fields are required, what values are valid, what results it returns, and how it responds when data fails to meet requirements.

This lesson belongs to the **Function Model** chapter, focusing on designing input/output contracts for **Supplier<T>**, **Function<T, R>**, and **Consumer<T>**, distinguishing data conversion errors from business errors, building validation policies, handling exceptions/rejection results, and testing both the core and adapters. **FunctionCatalog** and **composition** connect functions by data types, while adapters are responsible for mapping inputs, outputs, and errors to concrete protocols.

## 1. What Does a Function Contract Include?

The signature **Function<T, R>** states that calling **apply(T input)** returns **R**, yet generic types alone do not describe the full contract.

A complete contract needs to specify:

1. **Input shape:** field names, types, units of measurement, required/optional fields, and formats.
2. **Validity rules:** value ranges, cross-field relationships, and permitted business states.
3. **Success behavior:** return value, meaning of each field, and guaranteed invariants.
4. **Rejection behavior:** stable error codes, offending fields, caller-facing messages, and handling policies.
5. **Side effects:** whether the function writes data or emits messages; idempotency conditions if applicable.
6. **Versioning and compatibility:** whether older systems can handle newer data.
7. **Protocol boundaries:** where HTTP statuses, message headers, retries, or serverless error envelopes are defined.

Example:

~~~text
QuoteRequest(requestId, sku, quantity)
          │
          ▼
 Function<QuoteRequest, Quote>
          │
          ├── Success: Quote(requestId, sku, quantity, unitPrice, subtotal)
          │
          └── Rejection: predefined error code and reason
~~~

**A business contract is not synonymous with an HTTP contract.** A **Function<QuoteRequest, Quote>** does not need to know URLs or HTTP status codes. An HTTP adapter can convert requests into **QuoteRequest** and errors into responses; an event binder can handle errors via retries/dead-letter; a serverless adapter has its own error reporting mechanism.

## 2. Choosing Contracts Suited to Supplier, Function, and Consumer

| Model | Signature | Input Contract | Output Contract | On Invalid Data |
| --- | --- | --- | --- | --- |
| **Supplier<R>** | () → R | Accepts no business arguments | Value R generated/provided | Configuration/data-source errors may cause **get()** to fail |
| **Function<T, R>** | T → R | T has schema and validation rules | R has schema and output guarantees | Can throw exceptions or return an explicitly designed rejection result type |
| **Consumer<T>** | T → void | T must be validated before side effects | No business output | Can throw exceptions for the adapter to catch, or use a contract-defined rejection mechanism |

**Function<T, R>** fits data transformation logic. When input consists of multiple pieces of information, wrap them in a **record/DTO** instead of using a Map without a clear schema.

Example:

~~~java
public record QuoteRequest(
    String requestId,
    String sku,
    Integer quantity
) {}

public record Quote(
    String requestId,
    String sku,
    int quantity,
    java.math.BigDecimal unitPrice,
    java.math.BigDecimal subtotal
) {}
~~~

Using two types clearly separates **input** from **output**. Using **Integer** instead of **int** for input quantity lets you detect a missing field as **null**, rather than accidentally conflating a missing field with 0 after conversion.

**Records only make field references immutable**; they do not automatically validate business rules. A record can be instantiated with blank strings, negative quantities, or null quantities. If a record holds a mutable List/Map, the collection's contents do not become immutable either.

## 3. Separating Three Layers of Data Checks

When a request or event enters the application, separate different kinds of failures:

~~~mermaid
flowchart TD
    A["HTTP JSON / Message bytes / Serverless event"] --> B{"Readable and convertible?"}
    B -- "No" --> C["Format or conversion error"]
    B -- "Yes" --> D["DTO / record T"]
    D --> E{"Valid per contract?"}
    E -- "No" --> F["Validation error"]
    E -- "Yes" --> G{"Allowed by business rules?"}
    G -- "No" --> H["Business rejection"]
    G -- "Yes" --> I["Execute Function"]
    I --> J["Output R"]
~~~

### 3.1. Structural and Conversion Errors

For example, a request is not valid JSON or the **quantity** field is an object instead of a number. The adapter/converter cannot construct **QuoteRequest**; in that case **apply(...)** is not even called.

~~~json
{
  "requestId": "REQ-101",
  "sku": "BOOK",
  "quantity": {"value": 3}
}
~~~

Exact behavior also depends on the JSON converter, coercion settings, and Java types. Do not assume every converter rejects or coerces identically.

### 3.2. Contract Validation Errors

A payload may deserialize into a record yet still be invalid:

~~~json
{
  "requestId": "REQ-101",
  "sku": "BOOK",
  "quantity": 0
}
~~~

The value **quantity = 0** has the valid type **Integer**, but violates the condition "quantity must be between 1 and 1000." This is input/business validation, not a JSON parse error.

### 3.3. Rejection Based on Business State

A request is structurally valid, yet the SKU is unsupported, discontinued, or out of stock. This error differs from a mistyped **quantity** and differs from a disconnected database.

In this lesson's example: **sku = "UNKNOWN"** is syntactically valid but absent from the sample price catalog. The function signals rejection with the code **UNKNOWN_SKU**. In real deployments, explicitly decide whether this case is represented as an API error or a business result such as "unable to quote."

## 4. Defining the Schema: Field Names, Types, Units, and Limits

Before writing code, build a contract table for the quote example.

| Field | Type | Required | Constraints and Meaning |
| --- | --- | --- | --- |
| **requestId** | String | Yes | Non-blank business correlation ID; max 64 characters |
| **sku** | String | Yes | Product code; trimmed and uppercased; letters, digits, hyphens only; max 24 characters |
| **quantity** | Integer | Yes | Integer quantity from **1** to **1000** |
| **unitPrice** (output) | BigDecimal | Yes on success | Price from internal source; currency unit and decimal scale per app policy |
| **subtotal** (output) | BigDecimal | Yes on success | **quantity × unitPrice**, excluding taxes/other fees |

**Units of measurement are part of the schema.** A **weight** field must specify grams or kilograms; an **amount** field must state currency and rounding rules. In the example, the sample price table uses integers in an assumed system currency to stay focused on the Function contract. A real payment product requires a stricter currency model and rounding policy.

String normalization rules must also be explicit: if trimming or uppercasing is applied, apply it consistently; if requestId is a case-sensitive identifier, do not uppercase it just because sku is normalized.

## 5. Java 17+ Example: A Function with Explicit Validation

The following application illustrates **Function<QuoteRequest, Quote>**, a pricing service using internal data and two explicitly coded error types.

File **QuoteContractApplication.java**:

~~~java
package example.function;

import java.math.BigDecimal;
import java.util.Locale;
import java.util.Map;
import java.util.function.Function;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class QuoteContractApplication {

    public static void main(String[] args) {
        SpringApplication.run(QuoteContractApplication.class, args);
    }

    public record QuoteRequest(
        String requestId,
        String sku,
        Integer quantity
    ) {}

    public record Quote(
        String requestId,
        String sku,
        int quantity,
        BigDecimal unitPrice,
        BigDecimal subtotal
    ) {}

    // Input violates the Function contract.
    public static final class InvalidQuoteRequestException
            extends IllegalArgumentException {

        private final String code;
        private final String field;

        public InvalidQuoteRequestException(
                String code, String field, String message) {
            super(message);
            this.code = code;
            this.field = field;
        }

        public String code() {
            return code;
        }

        public String field() {
            return field;
        }
    }

    // Input is structurally valid but rejected by business rules.
    public static final class QuoteRejectedException
            extends RuntimeException {

        private final String code;

        public QuoteRejectedException(String code, String message) {
            super(message);
            this.code = code;
        }

        public String code() {
            return code;
        }
    }

    public static final class PriceCatalog {
        private final Map<String, BigDecimal> prices;

        public PriceCatalog(Map<String, BigDecimal> prices) {
            this.prices = Map.copyOf(prices);
        }

        public BigDecimal findPrice(String sku) {
            return prices.get(sku);
        }
    }

    public static final class QuoteService {
        private final PriceCatalog catalog;

        public QuoteService(PriceCatalog catalog) {
            this.catalog = catalog;
        }

        public Quote calculate(QuoteRequest request) {
            if (request == null) {
                throw invalid("REQUEST_REQUIRED", "request",
                    "Quote request must not be null");
            }

            String requestId = requiredText(
                request.requestId(), "requestId", 64);

            String sku = requiredText(request.sku(), "sku", 24)
                .toUpperCase(Locale.ROOT);

            if (!sku.matches("[A-Z0-9-]{1,24}")) {
                throw invalid("INVALID_SKU", "sku",
                    "SKU contains unsupported characters");
            }

            Integer quantity = request.quantity();
            if (quantity == null
                    || quantity < 1
                    || quantity > 1000) {
                throw invalid("INVALID_QUANTITY", "quantity",
                    "Quantity must be between 1 and 1000");
            }

            BigDecimal unitPrice = catalog.findPrice(sku);
            if (unitPrice == null) {
                throw new QuoteRejectedException(
                    "UNKNOWN_SKU", "Product is not available for quoting");
            }

            BigDecimal subtotal = unitPrice.multiply(
                BigDecimal.valueOf(quantity));

            return new Quote(
                requestId, sku, quantity, unitPrice, subtotal);
        }

        private static String requiredText(
                String value, String field, int maxLength) {

            if (value == null || value.isBlank()) {
                throw invalid("REQUIRED_FIELD", field,
                    "Field must not be blank");
            }

            String normalized = value.trim();
            if (normalized.length() > maxLength) {
                throw invalid("FIELD_TOO_LONG", field,
                    "Field exceeds maximum length");
            }

            return normalized;
        }

        private static InvalidQuoteRequestException invalid(
                String code, String field, String message) {
            return new InvalidQuoteRequestException(
                code, field, message);
        }
    }

    @Bean
    PriceCatalog priceCatalog() {
        return new PriceCatalog(Map.of(
            "BOOK", new BigDecimal("85000"),
            "PEN", new BigDecimal("12000")
        ));
    }

    @Bean
    QuoteService quoteService(PriceCatalog catalog) {
        return new QuoteService(catalog);
    }

    @Bean("calculateQuote")
    Function<QuoteRequest, Quote> calculateQuote(
            QuoteService service) {
        return service::calculate;
    }
}
~~~

**Key decisions:**

- Input uses **Integer quantity** to separate missing fields from 0.
- **requiredText(...)** validates non-blank strings, trims whitespace, and enforces max length.
- **sku** is normalized with **Locale.ROOT** to avoid host-locale-dependent outcomes.
- **QuoteService** makes no direct references to HTTP requests, Kafka messages, or serverless handlers.
- **PriceCatalog** holds an immutable price table; unitPrice is not client-supplied data.
- **InvalidQuoteRequestException** carries **code** and **field** so adapters can build structured responses.
- **QuoteRejectedException** represents structurally valid requests that fail business rules.
- **calculateQuote** is the **Function<QuoteRequest, Quote>** bean recognized by Spring Cloud Function via FunctionCatalog.

The exception classes are declared inline to keep the example easy to read. In large systems, separate contract types, exceptions, and services into appropriate packages.

### 5.1. Valid Input Example

~~~json
{
  "requestId": "REQ-101",
  "sku": " book ",
  "quantity": 2
}
~~~

Expected result:

~~~json
{
  "requestId": "REQ-101",
  "sku": "BOOK",
  "quantity": 2,
  "unitPrice": 85000,
  "subtotal": 170000
}
~~~

**QuoteService** trims **sku**, uppercases it, looks up BOOK's price, and calculates **2 × 85000 = 170000**. The output carries no HTTP or broker details.

### 5.2. Missing or Invalid Input

| Input | Error Condition | Error Code Emitted by Example |
| --- | --- | --- |
| **request = null** | Missing object | **REQUEST_REQUIRED** |
| **requestId = ""** | Blank required field | **REQUIRED_FIELD** |
| **sku = "A B"** | Disallowed characters | **INVALID_SKU** |
| **quantity = null** | Missing required field | **INVALID_QUANTITY** |
| **quantity = 0** | Below lower bound | **INVALID_QUANTITY** |
| **quantity = 1001** | Above upper bound | **INVALID_QUANTITY** |
| **sku = "UNKNOWN"** | Absent from price table | **UNKNOWN_SKU** |

These are **application-defined example error codes**, not built-in Spring Cloud Function error codes. For payloads rejected by the converter before constructing a QuoteRequest, the failure occurs in the adapter and may not match these codes; applications should define a separate error contract for parse/conversion errors.

## 6. Separating Validation from Serialization and Framework

Valid JSON does not guarantee a valid business request. Likewise, deserializing into **QuoteRequest** does not automatically run validation unless the adapter or application is configured to do so.

Some applications use **Jakarta Bean Validation**:

~~~java
public record QuoteRequestWithConstraints(
    @jakarta.validation.constraints.NotBlank
    String requestId,

    @jakarta.validation.constraints.NotBlank
    String sku,

    @jakarta.validation.constraints.NotNull
    @jakarta.validation.constraints.Min(1)
    @jakarta.validation.constraints.Max(1000)
    Integer quantity
) {}
~~~

Annotations express part of the field-level rules, yet **merely adding annotations does not guarantee every Function bean invoked through every adapter will auto-validate before apply()**. You need a mechanism invoking the validator at the right boundary (such as an HTTP controller with **@Valid** and validation infrastructure, or a validator injected in the adapter layer).

Moreover, annotation-based validation cannot express every rule:

- Whether the SKU exists in the active data source.
- Whether the quantity can be fulfilled given current inventory state.
- Whether two fields are mutually consistent.
- Whether the request is permitted in the order's current state.

You can combine **adapter-level validation** for shape constraints with **business-core validation** for mandatory invariants. However, critical rules must not live solely in an HTTP controller if the same Function is also invoked via brokers or serverless.

## 7. Two Error-Reporting Strategies: Exceptions and Explicit Results

A Function has at least two ways to represent failure to produce a successful output.

### 7.1. Throwing Exceptions

As in **QuoteService.calculate(...)**:

~~~java
throw new InvalidQuoteRequestException(
    "INVALID_QUANTITY", "quantity",
    "Quantity must be between 1 and 1000"
);
~~~

Pros: keeps the **Function<QuoteRequest, Quote>** signature clean and halts processing immediately when the contract is violated. Cons: adapters must map exceptions appropriately; an exception carries no HTTP status or retry policy on its own.

Use explicit exception types and error codes for expected failures, avoiding forcing clients to parse **getMessage()** as a stable identifier.

### 7.2. Returning Success/Rejection Within One Contract

When rejection is a normal business branch, you can design a two-state result type:

~~~java
public sealed interface QuoteDecision
        permits QuoteAccepted, QuoteDeclined {}

public record QuoteAccepted(
    QuoteContractApplication.Quote quote
) implements QuoteDecision {}

public record QuoteDeclined(
    String code,
    String field,
    String message
) implements QuoteDecision {}
~~~

And a Function converting the outcome:

~~~java
Function<
    QuoteContractApplication.QuoteRequest,
    QuoteDecision> decide = request -> {
    try {
        return new QuoteAccepted(service.calculate(request));
    } catch (QuoteContractApplication.InvalidQuoteRequestException ex) {
        return new QuoteDeclined(
            ex.code(), ex.field(), ex.getMessage());
    } catch (QuoteContractApplication.QuoteRejectedException ex) {
        return new QuoteDeclined(
            ex.code(), null, ex.getMessage());
    }
};
~~~

The snippet assumes **QuoteDecision**, **QuoteAccepted**, and **QuoteDeclined** reside in the same package or are imported properly, and **service** is provided. With polymorphic result types, define a clear schema/serializer; do not assume all Spring Cloud Function converters serialize/deserialize **sealed interfaces** identically.

| Strategy | Best Suited For | Things to Consider |
| --- | --- | --- |
| **Exception** | Bad input, uncontinuable errors, infrastructure failures | Classification, adapter mapping, selective retries |
| **Explicit Result/Decision** | Rejection is an expected business outcome | Output schema expressing branches, versioning, consumer handling |
| **Returning null** | Rarely a good default choice | Ambiguous with empty/error and inconsistent across adapters |

**Do not use null as a substitute for errors.** A null output can mean different things over HTTP, streams, or composition, and easily causes **NullPointerException** in downstream functions. If "not found" is an expected outcome, name and model that state explicitly with an appropriate type or contract.

## 8. HTTP Adapter Determines Status and Error Responses

With the Spring Cloud Function Web starter:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-function-web</artifactId>
</dependency>
~~~

and bean selection config:

~~~yaml
spring:
  cloud:
    function:
      definition: calculateQuote
~~~

when the application runs on the default port 8080, you can call:

~~~bash
curl -i -X POST http://localhost:8080/calculateQuote \
  -H "Content-Type: application/json" \
  -d '{"requestId":"REQ-101","sku":"BOOK","quantity":2}'
~~~

The adapter converts JSON into **QuoteRequest**, invokes **FunctionCatalog**, and serializes **Quote**. However, **IllegalArgumentException** or **QuoteRejectedException** does not automatically guarantee HTTP 400, 422, or a specific error JSON format. Test the behavior of the running adapter version and add an HTTP mapping layer when the API contract requires a stable error structure.

Example application-defined API error contract:

~~~json
{
  "code": "INVALID_QUANTITY",
  "field": "quantity",
  "message": "Quantity must be between 1 and 1000"
}
~~~

A possible HTTP policy:

| Scenario Category | Commonly Considered HTTP Codes | Interpretation |
| --- | --- | --- |
| Malformed JSON / fails deserialization | **400 Bad Request** | Request cannot be parsed |
| Missing field or invalid value | **400 Bad Request** or **422 Unprocessable Content** | Choose consistently with the API contract |
| Valid SKU format but cannot be quoted | **404** or **422** per API contract | Depends on whether SKU is treated as a queried resource or a business rejection |
| Transient database/service error | **5xx** | Do not expose internal infrastructure exception details |
| Success | **2xx** | Return **Quote** payload |

The table describes **a design policy**, not a claim that Spring Cloud Function Web returns these status codes by default.

### 8.1. Example of an HTTP Adapter Explicitly Mapping Errors

If explicit control over status codes and error bodies is needed, create an application controller at **/api/quotes** calling **QuoteService**. This example uses Spring MVC and does not replace Spring Cloud Function Web's auto-generated **/calculateQuote** endpoint.

~~~java
package example.function;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/quotes")
public class QuoteHttpAdapter {

    private final QuoteContractApplication.QuoteService service;

    public QuoteHttpAdapter(
            QuoteContractApplication.QuoteService service) {
        this.service = service;
    }

    public record ApiError(
        String code,
        String field,
        String message
    ) {}

    @PostMapping
    public QuoteContractApplication.Quote calculate(
            @RequestBody QuoteContractApplication.QuoteRequest request) {
        return service.calculate(request);
    }

    @ExceptionHandler(
        QuoteContractApplication.InvalidQuoteRequestException.class)
    public ResponseEntity<ApiError> invalid(
            QuoteContractApplication.InvalidQuoteRequestException ex) {
        return ResponseEntity.badRequest().body(
            new ApiError(ex.code(), ex.field(), ex.getMessage()));
    }

    @ExceptionHandler(
        QuoteContractApplication.QuoteRejectedException.class)
    public ResponseEntity<ApiError> rejected(
            QuoteContractApplication.QuoteRejectedException ex) {
        return ResponseEntity.unprocessableEntity().body(
            new ApiError(ex.code(), null, ex.getMessage()));
    }
}
~~~

Here, the controller **translates business errors to HTTP**, while **QuoteService** still accepts and returns Java DTOs. The example does not separately handle JSON parse errors occurring **before** the controller calls the service; production systems often use a shared **@RestControllerAdvice** to standardize those errors.

Do not place HTTP status mapping logic inside **Function.apply(...)** if you still intend to deploy the same function via brokers or serverless.

## 9. Events: Invalid Data Directly Affects Retries

With Spring Cloud Stream and a suitable binder, the same **Function<QuoteRequest, Quote>** can consume input messages and emit output messages:

~~~yaml
spring:
  cloud:
    function:
      definition: calculateQuote
    stream:
      bindings:
        calculateQuote-in-0:
          destination: quote-requests
        calculateQuote-out-0:
          destination: quote-results
~~~

This configuration requires Spring Cloud Stream, a concrete binder, a broker, and connection properties. For each message, the framework converts to **QuoteRequest**, invokes the Function, and sends **Quote** upon success.

A specific challenge is that **a failing event may be redelivered**. Permanent missing-field errors will not vanish after retries, whereas transient database failures can recover.

~~~mermaid
flowchart TD
    A["Message from broker"] --> B{"Convert and validate"}
    B -- "Permanently invalid input" --> C["Reject / dead-letter / error event"]
    B -- "Valid" --> D["Function.apply"]
    D --> E{"Outcome"}
    E -- "Success" --> F["Publish Quote"]
    E -- "Transient error" --> G["Bounded retry + backoff"]
    E -- "Business rejection" --> H["Rejection channel or error per contract"]
~~~

| Error Category | Does Automatic Retry Help? | Common Handling Approach |
| --- | --- | --- |
| JSON fails deserialization | Usually no if payload is unchanged | Dead-letter/quarantine, monitor and fix producer |
| Invalid quantity | Usually no | Emit coded error, reject, or dead-letter |
| UNKNOWN_SKU | Depends on whether reference data updates | Business rejection or data enrichment workflow |
| Database timeout | Potentially yes | Bounded retries, backoff, circuit breaker/timeout where appropriate |
| Broker disconnected on publish | Potentially yes | Rely on binder policy while ensuring side effects are not duplicated |

**There is no single universal retry/dead-letter rule across all binders.** Kafka, RabbitMQ, and other adapters have different acknowledgment, retry, error-channel, and dead-letter mechanisms. Test the exact binder and configuration version in use.

If you want every message processed into a **business outcome** including rejections, you can switch the output to **QuoteDecision** or a status-bearing result DTO. Then the message can be treated as successfully delivered at the transport level even when business logic returns "declined"; downstream consumers must understand that branch. This is a **contract decision**, not an exception-handling trick.

## 10. Serverless: Errors Also Need a Contract

In a serverless environment, the adapter converts the event into **QuoteRequest**, invokes **calculateQuote**, and transforms the output into the format expected by the runtime.

~~~text
Cloud event
  -> Serverless adapter / conversion
  -> QuoteRequest
  -> calculateQuote.apply(...)
  -> Quote or exception
  -> Runtime result / error mapping
~~~

A validation failure reported via exception may cause the runtime or trigger service to retry, depending on synchronous vs. asynchronous invocation models. Therefore clearly distinguish:

- **Permanent errors:** invalid data that cannot fix itself through retries.
- **Transient errors:** interrupted dependencies that may recover.
- **Business rejections:** is rejection a normal outcome or a failure the orchestrator must be notified about?

**Handlers, event envelopes, statuses, and retries vary by platform**; the Function itself does not dictate them. Keep shared validation logic inside the service, and design a serverless wrapper that recognizes error codes to map them to the trigger contract properly.

## 11. Message<T> and Headers: Metadata Does Not Replace Payload Contracts

A **Message<T>** carries **payload** and **headers**. With Spring Cloud Function, you can declare **Function<Message<QuoteRequest>, Message<Quote>>** when adapter logic needs to read metadata.

~~~java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

// Placed inside an application configuration class with Spring-injected QuoteService.
@Bean("calculateQuoteMessage")
Function<
    Message<QuoteContractApplication.QuoteRequest>,
    Message<QuoteContractApplication.Quote>>
        calculateQuoteMessage(
            QuoteContractApplication.QuoteService service) {

    return incoming -> {
        QuoteContractApplication.Quote quote =
            service.calculate(incoming.getPayload());

        var output = MessageBuilder.withPayload(quote);

        Object correlation =
            incoming.getHeaders().get("correlationId");
        if (correlation != null) {
            output.setHeader("correlationId", correlation);
        }

        return output.build();
    };
}
~~~

This example is a **@Bean method** placed in an appropriate Spring configuration class (not a standalone top-level Java file). **QuoteService** still handles the payload; the wrapper reads headers and forwards only necessary metadata.

Points to remember:

- The **correlationId** header aids log correlation and tracing; **it does not replace** required payload fields **requestId**, **sku**, and **quantity**.
- Do not extract authorization claims from client-supplied headers unless verified by a security layer.
- Do not assume HTTP headers, Kafka headers, and serverless metadata map identically.
- Do not mutate **MessageHeaders** directly because the incoming map may be read-only; build a new Message.
- Do not copy all headers indiscriminately. Internal headers or sensitive data may not be permitted to propagate.

Beyond **Message<T>**, Spring Cloud Function also supports BiFunction/BiConsumer receiving **payload** and a **headers Map** in suitable cases. The headers Map is protocol metadata, not a second business payload.

## 12. Composition Must Align Both Data Types and Errors

Spring Cloud Function supports composing functions by name via **FunctionCatalog**. Suppose we add a bean:

~~~java
@Bean("formatQuote")
Function<QuoteContractApplication.Quote, String> formatQuote() {
    return quote -> quote.requestId() + ":"
        + quote.subtotal().toPlainString();
}
~~~

**formatQuote** accepts the exact **Quote** returned by **calculateQuote**. You can select:

~~~yaml
spring:
  cloud:
    function:
      definition: calculateQuote|formatQuote
~~~

Data flow:

~~~mermaid
flowchart LR
    A["QuoteRequest"] --> B["calculateQuote"]
    B --> C["Quote"]
    C --> D["formatQuote"]
    D --> E["String"]
~~~

If **calculateQuote** throws an exception, **formatQuote** will not receive a **Quote** to process in the normal invocation path. If switching to the **QuoteDecision** strategy, the next function must accept **QuoteDecision** or a structured result type—you cannot keep **Function<Quote, String>** and expect the framework to handle the business-error branch automatically.

A sound composition contract specifies:

1. Is the output **R** of the preceding step compatible with the input **T** of the next step?
2. Are null or empty results permitted?
3. Where are exceptions from each step handled?
4. Are required headers preserved across every step?
5. Does the final pipeline output fit the adapter exposing/binding it?

**Do not mix business errors with type conversion.** When data violates the contract, report the proper error/rejection branch instead of hoping a message converter will coerce a broken object into the input type expected by the next function.

## 13. Contracts with Reactive Streams

With Project Reactor, a Function can process publishers:

~~~java
import java.util.function.Function;
import reactor.core.publisher.Flux;

Function<Flux<QuoteContractApplication.QuoteRequest>,
         Flux<QuoteContractApplication.Quote>> reactiveQuotes =
    requests -> requests.map(service::calculate);
~~~

In this example, **service** is a **QuoteService** supplied via dependency injection. Validation runs per element when the Flux is subscribed to.

**Point for caution:** if **service.calculate(...)** throws an exception inside **map(...)**, the publisher typically emits **onError** and terminates the stream unless the pipeline is designed with appropriate error handling. This differs from expecting "one bad message is skipped and all subsequent messages continue."

If per-element error handling is required, switch to an explicit result type:

~~~java
Function<Flux<QuoteContractApplication.QuoteRequest>,
         Flux<QuoteDecision>> decisions =
    requests -> requests.map(request -> {
        try {
            return (QuoteDecision) new QuoteAccepted(
                service.calculate(request));
        } catch (QuoteContractApplication.InvalidQuoteRequestException ex) {
            return new QuoteDeclined(
                ex.code(), ex.field(), ex.getMessage());
        } catch (QuoteContractApplication.QuoteRejectedException ex) {
            return new QuoteDeclined(
                ex.code(), null, ex.getMessage());
        }
    });
~~~

**QuoteDecision** is the business type defined in Section 7; the snippet does not implement retries or infrastructure error handling itself. Choosing which errors to catch and represent as results must follow the contract—avoid catching every **Exception** and turning a system outage into a misleading "processed" event.

Furthermore, not all adapters support **Flux** in the same way. Subscriptions, backpressure, converters, and error mapping for HTTP streaming or stream binders must be verified against the actual integration version.

## 14. Upholding Contracts Under Side Effects or Retries

Even though **calculateQuote** only performs computation, many real-world Functions or Consumers both validate and write to a database or emit events.

An important rule: **validate data before side effects, yet still have a recovery strategy when side effects only partially complete.**

~~~text
Receive OrderPaidEvent
  -> Convert and validate
  -> Check idempotency key
  -> Persist state/transaction
  -> Emit message or send notification
~~~

Requirements to define in the contract:

- **Event ID** is a stable identifier of the business event, independent of how many times the broker redelivers it.
- **Idempotency:** will reprocessing the same event ID cause duplicate writes or double charges?
- **Transactions:** which write operations must be atomic; are unique constraints required?
- **External side effects:** if the database write succeeds but sending a notification fails, how is it handled?
- **Retries:** which errors are retryable, max attempts, and backoff.
- **Caller feedback:** Consumers return no business output; processing status is reflected via storage or adapter error mechanisms.

Never use an **in-memory Map inside a singleton** as a durable idempotency mechanism across multiple replicas. In distributed systems, you typically need unique constraints, business keys, transactions, or the outbox pattern depending on requirements.

## 15. Designing Contracts That Can Evolve

When a Function is invoked across multiple protocols, changing a DTO changes the **contract**. Assess compatibility before deployment.

| Change | Risk | Prudent Practice |
| --- | --- | --- |
| Add optional output field | Older clients may reject unknown fields | Verify serializers and consumer contracts |
| Add required input field | Older clients do not send it | Version the contract or adopt conversion/backward-compatibility policy |
| Change **quantity** from number to string | Old messages may fail to deserialize | Create a new version or explicit migration |
| Change unit from grams to kilograms | Data still parses but semantics break | Rename field/schema or version; never change units silently |
| Rename error codes | Clients matching old codes misbehave | Treat error codes as part of the API contract |
| Change output type to **QuoteDecision** | Clients expecting Quote cannot read the branch | Align schema/consumers and run compatibility tests |
| Rename Function bean | Endpoints/bindings/definitions may point to old name | Update deployment config and integration tests |

A data contract can be documented via JSON Schema, OpenAPI, or an event system schema. However, **Java types and wire schemas are not identical**: nullability, decimal numbers, timestamps, and default fields must be verified with the actual serializer in use.

If a broker uses a schema registry, establish compatibility policies across producer and consumer versions. For HTTP, version endpoints or media types on breaking changes. For serverless, verify the event envelope supplied by the runtime/trigger.

## 16. Unit Testing: Every Input Case and Error Code

A correct Function must handle **valid cases** and **rejected cases** according to its contract. Service unit tests are independent of web servers and brokers.

JUnit 5 example:

~~~java
package example.function;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;
import java.util.Map;

import org.junit.jupiter.api.Test;

class QuoteContractApplicationTest {

    private final QuoteContractApplication.QuoteService service =
        new QuoteContractApplication.QuoteService(
            new QuoteContractApplication.PriceCatalog(
                Map.of("BOOK", new BigDecimal("85000"))
            )
        );

    @Test
    void validInputReturnsNormalizedQuote() {
        var input = new QuoteContractApplication.QuoteRequest(
            "REQ-101", " book ", 2);

        var result = service.calculate(input);

        assertEquals("BOOK", result.sku());
        assertEquals(2, result.quantity());
        assertEquals(new BigDecimal("170000"), result.subtotal());
    }

    @Test
    void missingQuantityIsRejectedWithStableCode() {
        var input = new QuoteContractApplication.QuoteRequest(
            "REQ-102", "BOOK", null);

        var error = assertThrows(
            QuoteContractApplication.InvalidQuoteRequestException.class,
            () -> service.calculate(input)
        );

        assertEquals("INVALID_QUANTITY", error.code());
        assertEquals("quantity", error.field());
    }

    @Test
    void zeroQuantityIsRejected() {
        var input = new QuoteContractApplication.QuoteRequest(
            "REQ-103", "BOOK", 0);

        var error = assertThrows(
            QuoteContractApplication.InvalidQuoteRequestException.class,
            () -> service.calculate(input)
        );

        assertEquals("INVALID_QUANTITY", error.code());
    }

    @Test
    void unknownSkuIsBusinessRejection() {
        var input = new QuoteContractApplication.QuoteRequest(
            "REQ-104", "UNKNOWN", 1);

        var error = assertThrows(
            QuoteContractApplication.QuoteRejectedException.class,
            () -> service.calculate(input)
        );

        assertEquals("UNKNOWN_SKU", error.code());
    }

    @Test
    void nullRequestIsRejectedBeforeAnyProcessing() {
        var error = assertThrows(
            QuoteContractApplication.InvalidQuoteRequestException.class,
            () -> service.calculate(null)
        );

        assertEquals("REQUEST_REQUIRED", error.code());
    }
}
~~~

This suite verifies logic, error codes, and field names of the contract. It does not by itself prove that JSON converters, HTTP statuses, or binder retries behave as desired.

### 16.1. Adding Boundary Cases

Also test:

- Quantity **1**, **1000**, and **1001** to cover boundaries.
- Whitespace-only **requestId**; SKU with unsupported characters or over 24 characters.
- SKU case normalization and leading/trailing whitespace.
- Product prices with fractional digits per currency policy.
- Whether identical inputs yield identical outputs when logic is expected to be pure.
- Whether root-level and field-level null inputs are handled consistently.
- Whether error codes remain stable across display-message wording changes.

Avoid writing tests that merely mirror the implementation without verifying invariants. For example, **quantity = 0** must be rejected because the contract defines a lower bound of 1, not simply because the code happens to contain **quantity <= 0**.

## 17. Integration Testing via FunctionCatalog and Adapters

To verify the **calculateQuote** bean name and that Spring Cloud Function locates the function, test with a real application context:

~~~java
package example.function;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.math.BigDecimal;
import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

@SpringBootTest
class QuoteContractCatalogTest {

    @Autowired
    FunctionCatalog catalog;

    @Test
    void catalogInvokesTypedFunction() {
        Function<
            QuoteContractApplication.QuoteRequest,
            QuoteContractApplication.Quote> fn =
                catalog.lookup("calculateQuote");

        assertNotNull(fn);

        var result = fn.apply(
            new QuoteContractApplication.QuoteRequest(
                "REQ-101", "BOOK", 2)
        );

        assertEquals(new BigDecimal("170000"), result.subtotal());
    }
}
~~~

Integration tests require compatible Spring Boot, Spring Cloud Function, and Spring Boot Test versions. When a real system uses adapters, verify each separately:

| Boundary to Test | Verification Examples |
| --- | --- |
| **HTTP** | Valid/invalid JSON types, missing fields, status codes, and error JSON |
| **Custom HTTP controller** | Error mapping of **InvalidQuoteRequestException** and **QuoteRejectedException** |
| **Stream** | Payload deserialization, input/output bindings, retries, and dead-lettering for invalid messages |
| **Serverless** | Event envelope, input conversion, output, and handler errors |
| **Composition** | **calculateQuote|formatQuote** passes matching types and halts at the right step on errors |
| **Message headers** | Only required correlationId is retained; sensitive headers are not leaked |
| **Schema versioning** | Older consumers handle newer payloads per committed compatibility policy |

Only test adapters actually used in the product. You do not need to spin up a broker or serverless runtime just to run unit tests for **QuoteService**.

## 18. Common Design Pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Request parses yet breaks business logic | Checked JSON syntax only, skipped invariant checks | Run contract validation after conversion |
| Missing field treated as 0 | Used primitive type when null needed to be distinguished | Use nullable types/DTOs and validate |
| Output is sometimes null, sometimes an object | Did not define a "no result" branch | Use a result type/exception with a clear contract |
| HTTP returns unexpected status code | Assumed exceptions map themselves | Design an HTTP adapter and test error mappings |
| Stream retries a bad payload infinitely | Failed to separate permanent errors from transient errors | Configure retry policy, DLQ, or explicit rejection outcomes |
| Composition fails types at downstream step | Output mismatches input or switched to result type | Specify and test contracts at every step |
| Clients break after version upgrade | Breaking changes to fields, units, or error codes | Manage schemas/versions and contract tests |
| Logs leak user data | Put entire raw payloads/internal exceptions into messages | Expose only safe messages and log responsibly |
| Same event creates duplicate side effects | Retries/redelivery and missing idempotency | Use event keys, unique constraints/transactions |
| API lets callers dictate unit prices | Failed to verify critical data from internal sources | Look up prices in a trusted service or data port |
| DTO depends on HttpServletRequest/Kafka record | Mixed business contract with protocol types | Use plain Java DTOs and conversion adapters |
| Validation exists only in HTTP controller | Stream/serverless invocations bypass checks | Keep business invariants in core or a shared validator |

## 19. Practice Exercises

**Exercise 1 — Contract table.** Design **Function<ShippingRequest, ShippingQuote>** accepting request ID, weight, and delivery zone. Specify whether weight is in grams or kilograms, min/max bounds, required fields, and rejection conditions.

**Exercise 2 — Classifying errors.** Given malformed JSON, negative quantity, nonexistent SKU, database timeout, and broker redelivery, classify them into conversion, validation, business rejection, transient infrastructure, and retry/redelivery; propose appropriate HTTP/Stream behavior.

**Exercise 3 — Error contract.** Define **ApiError(code, field, message)** and map QuoteService exceptions to HTTP statuses in a dedicated controller. Add tests for requests with quantity 0 and SKU UNKNOWN.

**Exercise 4 — Explicit results.** Convert the quote problem to **Function<QuoteRequest, QuoteDecision>**. Design a JSON schema so consumers distinguish **accepted** from **declined**, then explain what changes if results are published via a broker.

**Exercise 5 — Composition.** Add **Function<Quote, String> formatQuote** and configure **calculateQuote|formatQuote**. Predict which steps run when quantity is invalid and write a unit test confirming formatQuote does not run.

**Exercise 6 — Schema evolution.** Suppose input needs a new **currency** field, whereas earlier clients sent only requestId/sku/quantity. Design a backward-compatibility or versioning strategy; contrast adding an optional field against silently changing currency units.

**Exercise 7 — Stream data errors.** For the **calculateQuote-in-0** input binding, describe how to handle a permanently invalid event versus an event temporarily unable to query the price catalog. Identify observability details to log alongside the correlation ID and explain why infinite retries should be avoided.

**Exercise 8 — Boundary testing.** Build a test suite for quantity = null, 0, 1, 1000, 1001; blank SKU, invalid-character SKU, nonexistent SKU; requestId over 64 characters. Distinguish service unit tests from adapter integration tests.

### Key Takeaways

- **Input/output contracts** encompass not only the **T → R** generics, but also schemas, constraints, data semantics, error codes, and failure behavior.
- **Conversion, validation, and business rejection** are three distinct categories; design and test each boundary separately.
- **Function<T, R>** can use exceptions or explicit result types. Never treat **null** as a safe default error signal.
- **HTTP, Stream, and serverless** invoke the same business logic, while error mapping, retries, and response formatting belong to adapters; verify against the actual runtime environment.
- **FunctionCatalog and composition** connect functions by name and type, so changing error contracts or output types can affect the entire pipeline.
- Proper error design, schema versioning, and boundary testing enable safe reuse of one function across multiple protocols.
