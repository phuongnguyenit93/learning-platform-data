# Data Type Conversion

In integration systems, data often arrives from HTTP, CSV files, message brokers, or partner APIs as **strings, bytes, JSON, Maps, or loosely typed DTOs**. Meanwhile, business logic requires explicit types: `BigDecimal` for money, `Instant` for timestamps, `enum` for status sets, and `boolean` for true/false decisions. Spring Integration's **Transformer** lets you place that conversion step in an independent endpoint with an explicit input/output contract that is testable and easy to observe.

This lesson belongs to the **Transformer** chapter of the **SPRING_INTEGRATION_PATTERN** module, focusing on applying Enterprise Integration Patterns with Spring Integration to build loosely coupled, extensible message flows. Alongside Transformer, the module practices Router, Filter, Splitter, Aggregator, Gateway, retry, error channel, and correlation to organize reliable processing branches.

The topic here is **data type conversion**: how to turn raw payloads into **semantically accurate** typed data, prevent precision loss, handle invalid strings, preserve message metadata, and guarantee downstream steps receive only the committed data types.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish **transport data decoding**, **type conversion**, **normalization**, **validation**, and **business processing**.
2. Design a `RawOrder` → `TypedOrder` contract with fields converted to `BigDecimal`, `enum`, `Instant`, and `boolean`.
3. Write a pure Java converter that rejects ambiguous data instead of converting silently.
4. Integrate the converter into Spring Integration using `@Transformer` or Java DSL `IntegrationFlow.transform(...)`.
5. Understand Spring Framework's `ConversionService` and when to use it instead of a manual converter.
6. Explain the difference between a Transformer returning a **payload** versus returning a **complete Message**.
7. Classify parse/type conversion errors and connect them with error flows, retries, and Filter/Router steps.
8. Write unit tests, boundary tests, and integration tests verifying payloads and headers across real channels.
9. Identify risks around locale, timezone, currency, null, precision, mutable data, and contract versions.
10. Turn the conversion step into a reusable, observable, and safely modifiable component.

## 2. Where the Transformer Sits in a Pipeline

An order processing pipeline might look like this:

~~~mermaid
flowchart LR
    A["HTTP / MQ / CSV"] --> D["Decode: raw payload"]
    D --> S["Schema / data limits"]
    S --> T["Transformer: RawOrder → TypedOrder"]
    T --> V{"Validate typed invariants"}
    V -->|Valid| R{"Router"}
    V -->|Invalid| X["Reject/error"]
    R --> B["Priority handler"]
    R --> C["Standard handler"]
    T -->|Parse failure| E["Conversion error flow"]
~~~

Key condition: steps downstream of the Transformer no longer need to parse currency strings or guess timestamp formats. They receive a contract-compliant, strongly typed DTO.

Example input payload:

~~~json
{
  "orderId": " ORDER-1001 ",
  "amount": "1250.50",
  "currency": "usd",
  "occurredAt": "2026-11-21T02:30:00Z",
  "priority": "TRUE"
}
~~~

Expected result:

~~~text
TypedOrder
  orderId: "ORDER-1001"                 String
  amount: 1250.50                       BigDecimal
  currency: USD                         CurrencyCode enum
  occurredAt: 2026-11-21T02:30:00Z     Instant
  priority: true                        boolean
~~~

In the example, the `amount` field **is not allowed** to contain thousand separators, scientific notation, or more than two decimal places. This is an intentional contract choice to eliminate differences across locales and producers.

### 2.1. Frequently Confused Concepts

| Task | Example | Appropriate Component |
|---|---|---|
| Decode bytes/JSON | JSON string → `RawOrder` | Inbound message converter, Jackson/decoder, adapter |
| Convert types | `"1250.50"` → `BigDecimal` | Transformer/`ConversionService` |
| Normalize | `"usd"` → `USD`, trim order ID | Transformer or explicit normalization step |
| Check invariants | `amount > 0`, supported currency code | Boundary validation; can pair with converter per contract |
| Select branch | `priority=true` → priority channel | Router |
| Drop message | Inapplicable event | Filter |
| Write DB or call API | Save order / send payment | Service Activator, outbound adapter |

A Transformer can perform both type conversion and basic format verification to avoid producing invalid objects; however, business rules that depend on the DB or current state belong in **handlers or services with proper transactions**.

## 3. Why Must Data Type Conversion Be Tightly Designed?

If you only call `String.valueOf`, `Boolean.parseBoolean`, `Double.parseDouble`, and `LocalDateTime.parse` without defining a contract, the system can create data that **looks valid but carries the wrong meaning**.

For example:

- `Boolean.parseBoolean("yes")` returns `false` without throwing an error. A producer sending `"yes"` could be interpreted as non-priority.
- `Double.parseDouble("0.1")` yields a binary floating-point value that cannot represent 0.1 exactly. Converting it carelessly to `BigDecimal` creates monetary calculation risks.
- `"1,234.50"` can mean something different from `"1.234,50"` depending on locale.
- `"2026-11-21 09:30"` contains no offset/timezone; converting directly to `Instant` requires **supplying an explicit timezone rule**.
- Parsing an enum with `valueOf` fails on lowercase unless normalized, while overly permissive normalization can mask bad data.
- A DTO with `amount=null` may be silently masked if conversion defaults it to 0.

**Principle:** conversions must be explicit about accepted representations and behavior when conversion fails. Never invent defaults with business impact unless the producer committed to them.

## 4. Defining Input and Output Types

The example uses Java 17+ `record`s to keep payloads immutable by API design.

### 4.1. Input DTO

~~~java
public record RawOrder(
        String orderId,
        String amountText,
        String currencyText,
        String occurredAtText,
        String priorityText
) {}
~~~

An inbound adapter can construct `RawOrder` from JSON, CSV, or other decoded sources. This class holds fields as `String`s as received externally; it **does not guarantee** the values have been parsed or validated.

### 4.2. Typed DTO

~~~java
import java.math.BigDecimal;
import java.time.Instant;

public enum CurrencyCode {
    USD,
    EUR
}

public record TypedOrder(
        String orderId,
        BigDecimal amount,
        CurrencyCode currency,
        Instant occurredAt,
        boolean priority
) {}
~~~

In a real project, declare `public enum CurrencyCode` and `public record TypedOrder` in separate source files or arrange valid Java visibility/packages. `BigDecimal`, `Instant`, `String`, and enums are all immutable values; records generate no setters.

**Significance of types:** when a handler receives `TypedOrder`, it can call `order.amount().compareTo(...)` or `order.occurredAt().isBefore(...)` without re-parsing. That reduces duplication and bugs across branches.

### 4.3. Conversion Contract

| Input `RawOrder` | Output `TypedOrder` | Rule |
|---|---|---|
| `orderId` | `String` | Required; trim leading/trailing whitespace |
| `amountText` | `BigDecimal` | Digits only with optional decimal part, up to 2 digits; must be greater than 0 |
| `currencyText` | `CurrencyCode` | Trim, uppercase with `Locale.ROOT`; only `USD` or `EUR` |
| `occurredAtText` | `Instant` | ISO-8601 timestamp string with unambiguous instant; e.g. `...Z` |
| `priorityText` | `boolean` | Trim, case-insensitive; only `true` or `false` |

These are illustrative rules, not a mandate that every system uses two decimal places or only USD/EUR. When an application supports VND, JPY, or units with other scales, design per-currency rules instead of blindly copying this decimal-place example.

## 5. Conversion Errors Need Explicit Error Codes

An error like "failed to convert" is rarely enough to debug or return an API response. Define an exception with a stable error code, without needing to expose sensitive raw values.

~~~java
public final class OrderConversionException
        extends RuntimeException {

    private final String code;

    public OrderConversionException(String code) {
        super(code);
        this.code = code;
    }

    public OrderConversionException(
            String code, Throwable cause) {
        super(code, cause);
        this.code = code;
    }

    public String code() {
        return code;
    }
}
~~~

Suggested error codes:

| Code | Field | Meaning |
|---|---|---|
| `ORDER_ID_REQUIRED` | `orderId` | Missing/blank |
| `AMOUNT_REQUIRED` | `amountText` | Missing/blank |
| `INVALID_AMOUNT_FORMAT` | `amountText` | Violates specified grammar |
| `AMOUNT_MUST_BE_POSITIVE` | `amountText` | Value is 0 or negative |
| `CURRENCY_REQUIRED` | `currencyText` | Missing/blank |
| `UNSUPPORTED_CURRENCY` | `currencyText` | Not USD/EUR |
| `OCCURRED_AT_REQUIRED` | `occurredAtText` | Missing/blank |
| `INVALID_OCCURRED_AT` | `occurredAtText` | Cannot parse into `Instant` |
| `PRIORITY_REQUIRED` | `priorityText` | Missing/blank |
| `INVALID_PRIORITY` | `priorityText` | Not true/false |

Exceptions report a conversion contract violation, whereas a **Filter rejection** is a normal choice for a valid message that does not belong on that branch. The two cases should not be conflated in metrics or retries.

## 6. Pure Java Converter: String → BigDecimal/enum/Instant/boolean

Start with a Spring-free function: take `RawOrder`, return `TypedOrder` or throw a conversion error with a specific code.

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Instant;
import java.time.format.DateTimeParseException;
import java.util.Locale;
import java.util.Objects;
import java.util.regex.Pattern;

public final class OrderTypeConverter {

    // Accepts only 1, 12, 12.3, 12.34; rejects 1,000 or 1e3.
    private static final Pattern AMOUNT =
            Pattern.compile("[0-9]+(\\.[0-9]{1,2})?");

    public TypedOrder convert(RawOrder raw) {
        Objects.requireNonNull(raw, "raw");

        String orderId =
                required(raw.orderId(), "ORDER_ID_REQUIRED");
        BigDecimal amount = parseAmount(raw.amountText());
        CurrencyCode currency =
                parseCurrency(raw.currencyText());
        Instant occurredAt =
                parseInstant(raw.occurredAtText());
        boolean priority =
                parsePriority(raw.priorityText());

        return new TypedOrder(
                orderId, amount, currency, occurredAt, priority);
    }

    private String required(String value, String code) {
        if (value == null || value.isBlank()) {
            throw new OrderConversionException(code);
        }
        return value.strip();
    }

    private BigDecimal parseAmount(String rawAmount) {
        String text = required(rawAmount, "AMOUNT_REQUIRED");

        if (!AMOUNT.matcher(text).matches()) {
            throw new OrderConversionException(
                    "INVALID_AMOUNT_FORMAT");
        }

        BigDecimal amount = new BigDecimal(text);

        if (amount.signum() <= 0) {
            throw new OrderConversionException(
                    "AMOUNT_MUST_BE_POSITIVE");
        }

        // Illustrative contract allows at most 2 decimal places.
        // Do not round numbers carrying data beyond that precision.
        return amount.setScale(2, RoundingMode.UNNECESSARY);
    }

    private CurrencyCode parseCurrency(String rawCurrency) {
        String text = required(
                rawCurrency, "CURRENCY_REQUIRED")
                .toUpperCase(Locale.ROOT);

        return switch (text) {
            case "USD" -> CurrencyCode.USD;
            case "EUR" -> CurrencyCode.EUR;
            default -> throw new OrderConversionException(
                    "UNSUPPORTED_CURRENCY");
        };
    }

    private Instant parseInstant(String rawTimestamp) {
        String text = required(
                rawTimestamp, "OCCURRED_AT_REQUIRED");

        try {
            return Instant.parse(text);
        } catch (DateTimeParseException exception) {
            throw new OrderConversionException(
                    "INVALID_OCCURRED_AT", exception);
        }
    }

    private boolean parsePriority(String rawPriority) {
        String text = required(
                rawPriority, "PRIORITY_REQUIRED")
                .toLowerCase(Locale.ROOT);

        return switch (text) {
            case "true" -> true;
            case "false" -> false;
            default -> throw new OrderConversionException(
                    "INVALID_PRIORITY");
        };
    }
}
~~~

### 6.1. Why Put Parsing Logic in a Separate Class?

- Unit tests run directly without an `ApplicationContext`.
- Code contains no channel names or `BeanFactory`.
- Same input yields the same result, provided dependencies remain immutable.
- One central place publishes the grammar and error codes.
- Multiple flows can reuse the converter without duplicating logic.
- Easy to separate data errors from infrastructure errors and retry decisions.

In a production service, you may use standardized organizational validators and type converters. The example above intentionally spells out the rules so learners see **exactly which inputs are permitted to convert**.

### 6.2. Why Use a Regular Expression?

`Pattern.compile("[0-9]+(\\.[0-9]{1,2})?")` specifies:

- One or more digits `0–9`.
- Optionally a dot followed by one or two decimal digits.
- Rejects plus/minus signs, commas, scientific notation, or unexpected characters.

For instance:

| Input String | Result |
|---|---|
| `"1250.50"` | `1250.50` |
| `" 1250.5 "` | `1250.50` after trim/scale |
| `"100"` | `100.00` |
| `"0"` | Error `AMOUNT_MUST_BE_POSITIVE` |
| `"-1"` | Error `INVALID_AMOUNT_FORMAT` |
| `"1,250.50"` | Error `INVALID_AMOUNT_FORMAT` |
| `"1250,50"` | Error `INVALID_AMOUNT_FORMAT` |
| `"1e3"` | Error `INVALID_AMOUNT_FORMAT` |
| `"100.999"` | Error `INVALID_AMOUNT_FORMAT` |

This keeps the contract transparent. If you need negative signs for refunds or other notations, **update the contract intentionally** rather than simply dropping the regex and hoping `BigDecimal` guesses every format properly.

### 6.3. Why Avoid `Double` for Money?

~~~java
// Avoid for monetary values under this contract:
double value = Double.parseDouble("0.1");
BigDecimal risky = new BigDecimal(value);

// Prefer:
BigDecimal precise = new BigDecimal("0.1");
~~~

`double` uses binary floating point and cannot represent most decimal fractions exactly. `new BigDecimal(double)` exposes the binary approximation. When the source is a decimal string, constructing `BigDecimal` **directly from the string** preserves the intended value.

### 6.4. Why Does `parsePriority` Not Use `Boolean.parseBoolean`?

~~~java
Boolean.parseBoolean("true");  // true
Boolean.parseBoolean("false"); // false
Boolean.parseBoolean("yes");   // false
Boolean.parseBoolean("1");     // false
Boolean.parseBoolean("oops");  // false
~~~

If a producer sends `"oops"`, silently returning `false` could send a priority order down the standard branch. For required fields, switch over the accepted vocabulary and raise an error on anything else.

### 6.5. Time: `Instant` Differs from `LocalDateTime`

`Instant` represents a point on the timeline and does not retain a display timezone. `Instant.parse("2026-11-21T02:30:00Z")` yields a globally unambiguous point in time. By contrast, `"2026-11-21 09:30:00"` gives no timezone position and cannot yield a single instant.

If the contract permits local date-times, an explicit `ZoneId` or offset must be declared:

~~~java
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;

LocalDateTime local =
        LocalDateTime.parse("2026-11-21T09:30:00");

Instant instant = local
        .atZone(ZoneId.of("Asia/Ho_Chi_Minh"))
        .toInstant();
~~~

This is a rule that **supplies a business timezone**. Never rely on the server's default timezone to convert customer data, because deploying to another environment can shift timestamps. For regions with daylight saving time, also define policies for ambiguous or nonexistent local times.

## 7. Wiring the Converter into `@Transformer`

Spring Integration provides `org.springframework.integration.annotation.Transformer`. The method can accept a **typed payload** and return a **new typed payload**.

~~~java
import org.springframework.integration.annotation.Transformer;

public final class OrderTransformer {

    private final OrderTypeConverter converter;

    public OrderTransformer(OrderTypeConverter converter) {
        this.converter = converter;
    }

    @Transformer(
            inputChannel = "orders.raw",
            outputChannel = "orders.typed")
    public TypedOrder toTypedOrder(RawOrder raw) {
        return converter.convert(raw);
    }
}
~~~

When a `Message<RawOrder>` is sent to `orders.raw`:

1. Spring Integration receives the message at the transformer endpoint.
2. It extracts the `RawOrder` payload and passes it to the method.
3. The method invokes the pure Java converter.
4. On success, the method returns `TypedOrder`.
5. The framework builds the output message and sends it to `orders.typed` per configuration.
6. If the converter throws an exception, **no valid result payload** is forwarded to the output channel for that attempt.

### 7.1. Registering Beans and Channels

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;

@Configuration
@EnableIntegration
public class OrderTransformerConfiguration {

    @Bean(name = "orders.raw")
    public MessageChannel rawOrders() {
        return new DirectChannel();
    }

    @Bean(name = "orders.typed")
    public PollableChannel typedOrders() {
        return new QueueChannel();
    }

    @Bean
    public OrderTypeConverter orderTypeConverter() {
        return new OrderTypeConverter();
    }

    @Bean
    public OrderTransformer orderTransformer(
            OrderTypeConverter converter) {
        return new OrderTransformer(converter);
    }
}
~~~

The output `QueueChannel` in the example is for testing; in real systems, the output typically connects to a validator, router, or service activator. The default in-memory `QueueChannel` **does not** guarantee durability across application restarts.

The `@Transformer` annotation only takes effect when the object is Spring-managed and Integration annotation infrastructure is enabled. Calling `new OrderTransformer(...)` outside Spring does not create a messaging endpoint.

### 7.2. Example Sending a Message

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

void send(MessageChannel rawChannel) {
    RawOrder raw = new RawOrder(
            " ORDER-1001 ",
            "1250.50",
            "usd",
            "2026-11-21T02:30:00Z",
            "TRUE");

    Message<RawOrder> message =
            MessageBuilder.withPayload(raw)
                    .setHeader("traceId", "trace-1001")
                    .setHeader(
                            "businessCorrelationId", "ORDER-1001")
                    .build();

    rawChannel.send(message);
}
~~~

Once the transformer completes, the output holds `TypedOrder`. `traceId` and `businessCorrelationId` can be preserved on the output message via payload-returning Transformer header propagation. The testing section below **verifies this behavior directly**, rather than merely assuming it.

### 7.3. Do Not Combine Payload Conversion with Side Effects in One Transformer

~~~java
// Illustrative anti-pattern:
@Transformer(inputChannel = "orders.raw")
public TypedOrder convertAndSave(RawOrder raw) {
    TypedOrder order = converter.convert(raw);
    repository.save(order);
    notificationService.send(order.orderId());
    return order;
}
~~~

If sending the reply fails and the message is retried, the code can write to the DB or send notifications a second time. Separate pure conversion into a Transformer, and put DB writes and notifications into dedicated handlers with proper transactions and idempotency.

## 8. Using Java DSL `transform(...)`

Java DSL makes the topology readable in a single configuration while reusing the pure converter:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
public class TypedOrderDslConfiguration {

    @Bean
    public IntegrationFlow typedOrderFlow(
            OrderTypeConverter converter) {

        return IntegrationFlow.from("orders.dsl.raw")
                .transform(RawOrder.class, converter::convert)
                .channel("orders.dsl.typed")
                .get();
    }
}
~~~

This flow only accepts `RawOrder` payloads per contract; if the input is a JSON string or arbitrary `Map`, decode/convert it in an earlier step. For named channels, declare explicit channel beans to avoid ambiguity during testing and deployment.

**This is an alternative** to `@Transformer` in section 7—do not register both on the same `DirectChannel` if the goal is a single pipeline. When multiple consumers subscribe to a `DirectChannel`, messages are normally not broadcast to every consumer.

### 8.1. Simple Lambda Conversion

~~~java
@Bean
IntegrationFlow simpleQuantityFlow() {
    return IntegrationFlow.from("quantity.raw")
            .transform(String.class, Integer::valueOf)
            .channel("quantity.number")
            .get();
}
~~~

This snippet illustrates concise syntax. For bad input such as `"not-a-number"`, `Integer.valueOf` throws an exception. If input comes from external sources, add length limits, error classification, and a result contract; never assume every string parses cleanly.

### 8.2. Separating Meaningful Transformations

~~~mermaid
flowchart LR
    A["raw.order.json"] --> J["JSON decoder"]
    J --> B["RawOrder"]
    B --> C["Type Transformer"]
    C --> D["TypedOrder"]
    D --> V["Validation"]
    V --> R{"Router"}
    R --> P["Priority"]
    R --> N["Normal"]
~~~

Each step can have its own tests. Avoid creating dozens of Transformers just to chain `trim` calls, yet also avoid cramming decoding, validation, DB writes, and notifications into one method when failure modes and retry policies differ.

## 9. Spring Framework's `ConversionService`

Spring Framework provides `org.springframework.core.convert.ConversionService` to convert types through registered converters. For simple types, it helps avoid repeating conversion logic.

~~~java
import org.springframework.core.convert.ConversionService;
import org.springframework.core.convert.support.DefaultConversionService;

ConversionService conversionService =
        new DefaultConversionService();

Integer quantity =
        conversionService.convert("42", Integer.class);

Boolean flag =
        conversionService.convert("true", Boolean.class);
~~~

This is direct Spring Framework usage, **not automatically a Spring Integration Transformer endpoint**. You can call `ConversionService` inside a Transformer or register it as a bean serving other type-conversion points.

### 9.1. When to Use Built-in Converters?

| Need | Approach |
|---|---|
| `"42"` → `Integer` with no extra rules | Built-in `ConversionService` or `Integer.valueOf` |
| String → enum using standard framework rules | Built-in converter, followed by policy checks |
| `"TRUE"`/`"FALSE"` with narrow contract vocabulary | Custom converter like `OrderTypeConverter` |
| `"1250.50"` → `BigDecimal` with strict grammar/scale | Custom converter or explicitly registered converter |
| `LocalDateTime` → `Instant` needing business `ZoneId` | Context/timezone-explicit conversion |
| JSON → DTO | Boundary message converter/decoder such as Jackson |
| `RawOrder` → `TypedOrder` with multiple fields and error codes | Domain-specific Transformer/converter |

**Key point:** default converters may accept representations outside your application's policy. Using `ConversionService` does not automatically guarantee currencies, timezones, and business rules are enforced.

### 9.2. Creating a Custom Converter for `ConversionService`

Spring Framework provides the `Converter<S,T>` interface:

~~~java
import org.springframework.core.convert.converter.Converter;

public final class RawOrderToTypedOrderConverter
        implements Converter<RawOrder, TypedOrder> {

    private final OrderTypeConverter delegate;

    public RawOrderToTypedOrderConverter(
            OrderTypeConverter delegate) {
        this.delegate = delegate;
    }

    @Override
    public TypedOrder convert(RawOrder source) {
        return delegate.convert(source);
    }
}
~~~

When registered into the appropriate `FormattingConversionService` / `ConversionService`, components using that service can reuse it. Control the **registration scope**: a global converter affects everywhere the framework shares that service, not just one flow. For conversions with business consequences, an explicit Transformer is usually easier to see and reason about.

### 9.3. Do Not Confuse Implicit Conversion with Explicit Transformation

A `@Transformer` method expecting `TypedOrder` while a producer sends `String` does not guarantee Spring Integration knows how to convert an arbitrary JSON string into `TypedOrder`. Argument resolution and message conversion depend on configured converters. For critical flows, model the **decoder/converter upfront**, have the Transformer accept the known type, and test directly from the inbound adapter's real payload.

## 10. JSON, CSV, and Map: Understanding Decoding Boundaries

### 10.1. JSON → `RawOrder` Before Type Conversion

For an API/broker sending JSON:

~~~json
{
  "orderId": " ORDER-1001 ",
  "amountText": "1250.50",
  "currencyText": "USD",
  "occurredAtText": "2026-11-21T02:30:00Z",
  "priorityText": "true"
}
~~~

A JSON decoder like Jackson can bind fields into `RawOrder`. Then `OrderTypeConverter` converts to `TypedOrder`. If a field is missing, it may bind as `null` depending on binding settings, and the converter emits the corresponding error code.

Do not conflate **syntactically invalid JSON** errors with **`amountText` grammar violations**. The former occurs in the decoder; the latter occurs in type conversion.

### 10.2. CSV and Delimiter Parsing

Example:

~~~text
ORDER-1001,1250.50,USD,2026-11-21T02:30:00Z,true
~~~

A CSV parser must handle commas inside quoted values, escaping, encoding, BOM, and header rows before constructing `RawOrder`. Never use `line.split(",")` as a general-purpose production CSV parser. Once the DTO exists, the converter does not need to know whether data came from CSV or JSON.

### 10.3. Dynamic Maps

When an inbound adapter yields `Map<String,Object>`, do not cast fields like `(String) map.get("amount")` when the runtime value might be `Integer`, `Double`, or `BigDecimal`. Define the schema/value types upfront and use a tested adapter to normalize into `RawOrder` or another DTO.

Expressions like `String.valueOf(map.get("amount"))` can turn `null` into the string `"null"`, or lose the distinction between numeric and string inputs. If an amount can arrive as a JSON number, verify deserializer configuration so decimal precision is preserved.

## 11. Payload Transformer vs. Message Transformer

This is an important distinction in Spring Integration.

### 11.1. Returning a New Payload

~~~java
@Transformer(
        inputChannel = "orders.raw",
        outputChannel = "orders.typed")
public TypedOrder convert(RawOrder input) {
    return converter.convert(input);
}
~~~

The framework constructs the output message for `TypedOrder`. Under Spring Integration's header propagation rules, appropriate inbound headers can be preserved automatically.

### 11.2. Returning a Complete `Message`

~~~java
import org.springframework.integration.annotation.Transformer;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

@Transformer(
        inputChannel = "orders.raw",
        outputChannel = "orders.typed")
public Message<TypedOrder> convertMessage(
        Message<RawOrder> input) {

    TypedOrder typed = converter.convert(input.getPayload());

    return MessageBuilder.withPayload(typed)
            .copyHeaders(input.getHeaders())
            .build();
}
~~~

This is an **alternative approach**—do not declare it simultaneously on an input channel already served by the Transformer in section 11.1.

When returning a new `Message<?>`, your code owns the contents of that message; never assume every request header will appear automatically. `copyHeaders(...)` illustrates explicitly carrying metadata, though at trust boundaries an **allowlist** is required to avoid forwarding sensitive headers or non-serializable objects to external systems.

### 11.3. Which Headers Should Be Tested?

| Header | Purpose | Note |
|---|---|---|
| `traceId` | Cross-stage tracing | Preserve per observability contract |
| `businessCorrelationId` | Links messages in the same business flow | Do not use Message ID as durable correlation |
| `replyChannel` | Gateway/request–reply | Must preserve when the flow still needs a reply |
| `errorChannel` | Error path in supporting topologies | Do not copy across unsupported boundaries |
| `tenantId` | Data scoping | Use only once verified |
| `schemaVersion` | Payload version interpretation | May need updating when contract changes |
| `MessageHeaders.ID` | Message instance ID | May be regenerated by framework; do not assert equality |

**Do not change `traceId` or `businessCorrelationId` just because the payload changed from String to BigDecimal.** Likewise, if you produce a new DTO yet blindly keep `contentType=application/json` from the raw bytes, downstream may misinterpret the message; verify each real adapter's mapping and metadata.

## 12. May a Transformer Return `null`?

Do not use `return null` to represent "conversion failed" or "drop message."

~~~java
// Anti-pattern:
@Transformer(inputChannel = "orders.raw")
public TypedOrder unsafeConvert(RawOrder input) {
    if (input.amountText() == null) {
        return null;
    }
    return converter.convert(input);
}
~~~

In Spring Integration, a Transformer is expected to produce a result; returning `null` can trigger a `MessageTransformationException` or equivalent failure. Depending on your intent:

- **Reject a valid out-of-scope message:** use a Filter with `discardChannel` if needed.
- **Unparseable data:** throw a meaningful conversion exception or return an explicit result type.
- **Branch by state:** use a Router.
- **Turn one message into a collection/multiple parts:** evaluate Transformer or Splitter per contract.

### 12.1. Explicit Result Type Instead of Exceptions

If errors must be handled as **data** rather than thrown:

~~~java
public sealed interface ConversionOutcome
        permits ConversionAccepted, ConversionRejected {}

public record ConversionAccepted(TypedOrder value)
        implements ConversionOutcome {}

public record ConversionRejected(
        String errorCode,
        String fieldName)
        implements ConversionOutcome {}
~~~

A Transformer can return `ConversionOutcome`, and a Router directs `ConversionAccepted` to the success branch and `ConversionRejected` to the reject branch. This pattern works well when every input must emit a recorded outcome, especially when async consumers have no caller waiting for an exception.

In return, downstream must handle the sealed hierarchy, or a follow-up Transformer extracts `ConversionAccepted.value()` into `TypedOrder`. Do not mix the result-type model with Filter's `throwExceptionOnRejection` and accidentally report errors twice.

## 13. Conversion Errors in Sync and Async Flows

When the converter throws `OrderConversionException`, Spring Integration may wrap it in a messaging/transformer exception. How the error reaches the caller depends on topology:

| Topology | Typical Error Path | Caveat |
|---|---|---|
| Synchronous `DirectChannel` | Exception surfaces to `send()` caller or Gateway | Caller can inspect cause chain |
| `ExecutorChannel` | Error occurs on worker thread | Needs proper error handling; sender may not see it |
| Message-driven inbound adapter | Listener/container handles exception | Ack/retry/dead-letter depends on adapter |
| Request–reply Gateway | Error or timeout per configuration | Must ensure a contract-compliant response |
| Downstream Router | Never invoked when conversion fails | Test that typed channel stays empty on error |

### 13.1. Do Not Retry Deterministic Bad Data

`amountText="abc"` or `priorityText="oops"` will not become valid by retrying the exact same payload. Such errors should be returned to the producer, routed to reject/quarantine, or recorded as failed per policy; never retry infinitely.

Conversely, a Transformer that also enriches from an external API may suffer transient timeouts. It is better to **separate enrichment** into its own endpoint so it can have a different retry policy from pure type conversion.

### 13.2. Conversion Exceptions May Be Wrapped

Do not demand that the outermost exception always be `OrderConversionException`. The framework handler may throw a `MessagingException` whose cause is the conversion exception. When building error flows, traverse the cause chain in a controlled way and map to stable error codes; never return raw stack traces or sensitive raw values to callers.

### 13.3. Do Not Treat `errorChannel` as Automatic in Every Flow

In synchronous flows, exceptions can propagate straight back to the caller. In async flows, infrastructure can publish an `ErrorMessage` to a configured channel. **Do not assume that merely adding an `errorChannel` header automatically sends every error from every endpoint there.** Test the real topology, especially when `MessageTransformer` sits behind a Gateway or broker consumer.

## 14. Unit Testing the Pure Java Converter

Unit tests should start with cases that require no Spring. JUnit 5 can verify both success cases and error codes.

### 14.1. Successful Conversion Cases

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.time.Instant;

import org.junit.jupiter.api.Test;

class OrderTypeConverterTest {

    private final OrderTypeConverter converter =
            new OrderTypeConverter();

    @Test
    void convertsRawStringsToTypedValues() {
        RawOrder input = new RawOrder(
                " ORDER-1001 ",
                "1250.50",
                "usd",
                "2026-11-21T02:30:00Z",
                "TRUE");

        TypedOrder result = converter.convert(input);

        assertEquals("ORDER-1001", result.orderId());
        assertEquals(new BigDecimal("1250.50"), result.amount());
        assertEquals(CurrencyCode.USD, result.currency());
        assertEquals(
                Instant.parse("2026-11-21T02:30:00Z"),
                result.occurredAt());
        assertTrue(result.priority());
    }

    @Test
    void trimsAndUsesTwoDecimalPlacesWithoutRounding() {
        RawOrder input = new RawOrder(
                "ORDER-1002",
                " 100.5 ",
                "EUR",
                "2026-11-21T00:00:00Z",
                "false");

        TypedOrder result = converter.convert(input);

        assertEquals(new BigDecimal("100.50"), result.amount());
        assertFalse(result.priority());
    }
}
~~~

These tests check **actual types and values**, not just that a DTO was constructed. For `BigDecimal`, in this example scale 2 is part of the contract, so `assertEquals(new BigDecimal("100.50"), ...)` is intentional.

### 14.2. Table-Driven Error Code Testing

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.stream.Stream;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;

class OrderTypeConverterInvalidInputTest {

    private final OrderTypeConverter converter =
            new OrderTypeConverter();

    static Stream<Arguments> invalidInputs() {
        return Stream.of(
                Arguments.of(
                        new RawOrder(" ", "1.00", "USD",
                                "2026-11-21T00:00:00Z", "true"),
                        "ORDER_ID_REQUIRED"),
                Arguments.of(
                        new RawOrder("A", null, "USD",
                                "2026-11-21T00:00:00Z", "true"),
                        "AMOUNT_REQUIRED"),
                Arguments.of(
                        new RawOrder("A", "1,000", "USD",
                                "2026-11-21T00:00:00Z", "true"),
                        "INVALID_AMOUNT_FORMAT"),
                Arguments.of(
                        new RawOrder("A", "0", "USD",
                                "2026-11-21T00:00:00Z", "true"),
                        "AMOUNT_MUST_BE_POSITIVE"),
                Arguments.of(
                        new RawOrder("A", "1.00", "JPY",
                                "2026-11-21T00:00:00Z", "true"),
                        "UNSUPPORTED_CURRENCY"),
                Arguments.of(
                        new RawOrder("A", "1.00", "USD",
                                "2026-11-21 09:30:00", "true"),
                        "INVALID_OCCURRED_AT"),
                Arguments.of(
                        new RawOrder("A", "1.00", "USD",
                                "2026-11-21T00:00:00Z", "yes"),
                        "INVALID_PRIORITY"));
    }

    @ParameterizedTest
    @MethodSource("invalidInputs")
    void rejectsInvalidConversions(
            RawOrder input, String expectedCode) {

        OrderConversionException exception =
                assertThrows(
                        OrderConversionException.class,
                        () -> converter.convert(input));

        assertEquals(expectedCode, exception.code());
    }
}
~~~

This tests **type conversion errors**, not Filter rejections. Beyond the cases above, add timestamps with valid fractional seconds/offsets per contract, very large numbers, Unicode whitespace, missing fields, and adapter-truncated values.

### 14.3. Determinism Verification

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class ConverterDeterminismTest {

    @Test
    void sameInputProducesSameTypedValue() {
        OrderTypeConverter converter =
                new OrderTypeConverter();

        RawOrder raw = new RawOrder(
                "A", "10.00", "USD",
                "2026-11-21T00:00:00Z", "true");

        TypedOrder first = converter.convert(raw);

        for (int i = 0; i < 100; i++) {
            assertEquals(first, converter.convert(raw));
        }
    }
}
~~~

This test verifies a desirable property but **does not strictly prove** the code has no side effects. Code review is still needed to ensure the Converter does not call clocks, DBs, or APIs or mutate inputs.

## 15. Integration Testing Through `MessageChannel`

Unit tests do not confirm Spring wired the endpoint and propagated metadata. An integration test sends `Message<RawOrder>` to `orders.raw` and receives `Message<TypedOrder>` from `orders.typed`.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.time.Instant;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = OrderTransformerConfiguration.class)
class OrderTransformerFlowTest {

    @Autowired
    @Qualifier("orders.raw")
    MessageChannel raw;

    @Autowired
    @Qualifier("orders.typed")
    PollableChannel typed;

    @Test
    void transformsPayloadAndPreservesTracingHeaders() {
        RawOrder input = new RawOrder(
                " ORDER-1001 ",
                "1250.50",
                "USD",
                "2026-11-21T02:30:00Z",
                "true");

        Message<RawOrder> message =
                MessageBuilder.withPayload(input)
                        .setHeader("traceId", "trace-1001")
                        .setHeader(
                                "businessCorrelationId", "ORDER-1001")
                        .build();

        assertTrue(raw.send(message));

        Message<?> output = typed.receive(1000);
        assertNotNull(output);
        assertInstanceOf(TypedOrder.class, output.getPayload());

        TypedOrder result = (TypedOrder) output.getPayload();

        assertEquals("ORDER-1001", result.orderId());
        assertEquals(new BigDecimal("1250.50"), result.amount());
        assertEquals(CurrencyCode.USD, result.currency());
        assertEquals(
                Instant.parse("2026-11-21T02:30:00Z"),
                result.occurredAt());
        assertTrue(result.priority());

        assertEquals(
                "trace-1001", output.getHeaders().get("traceId"));
        assertEquals(
                "ORDER-1001",
                output.getHeaders().get("businessCorrelationId"));
    }

    @Test
    void malformedAmountDoesNotReachTypedOutput() {
        RawOrder invalid = new RawOrder(
                "ORDER-1002",
                "not-a-number",
                "USD",
                "2026-11-21T02:30:00Z",
                "true");

        RuntimeException failure = assertThrows(
                RuntimeException.class,
                () -> raw.send(
                        MessageBuilder.withPayload(invalid).build()));

        Throwable cause = failure;
        while (cause != null
                && !(cause instanceof OrderConversionException)) {
            cause = cause.getCause();
        }

        assertInstanceOf(OrderConversionException.class, cause);
        assertEquals(
                "INVALID_AMOUNT_FORMAT",
                ((OrderConversionException) cause).code());

        assertNull(typed.receive(0));
    }
}
~~~

**Important note:** the example uses a synchronous `DirectChannel`. Catching the exception directly from `raw.send(...)` makes sense in this topology; when switching to an executor or broker, errors occur on another thread and tests must observe the appropriate error flow, ack, or dead-letter behavior.

### 15.1. How Does Flow Testing Differ from Converter Testing?

| Converter Unit Test | Spring Integration Test |
|---|---|
| Verifies parsing rules and error codes | Verifies annotations, beans, and channel wiring |
| Requires no Spring context | Requires Spring context |
| Fast, covers many edge cases | Verifies payload/header propagation |
| Cannot detect wrong `outputChannel` | Detects missing or miswired target channels |
| Does not reveal framework exception wrapping | Observes the real cause chain |

When scaling the test suite, keep channel fixtures isolated so multiple tests do not accidentally read/write the same queue in a shared context. Results received from a `QueueChannel` only prove the endpoint moved the message in memory, not that downstream databases or brokers finished processing.

## 16. Designing a Realistic End-to-End Pipeline

An application receives orders over HTTP and Kafka. Both adapters have different protocol characteristics, yet after decoding, both can pass a common `RawOrder` to the converter.

~~~mermaid
flowchart TB
    HTTP["HTTP inbound adapter"] --> HDEC["HTTP JSON decode / limits"]
    KAFKA["Kafka inbound adapter"] --> KDEC["Kafka deserialize / schema"]
    HDEC --> RAW["orders.raw: RawOrder"]
    KDEC --> RAW
    RAW --> TRANS["Type Transformer"]
    TRANS --> TYPED["orders.typed: TypedOrder"]
    TYPED --> VAL{"Typed validation"}
    VAL -->|Pass| ROUTE{"Router: priority"}
    VAL -->|Fail| REJECT["Business reject"]
    TRANS -->|Parse failure| ERROR["Conversion error flow"]
    ROUTE --> PRI["Priority service"]
    ROUTE --> STD["Standard service"]
~~~

Separation of responsibilities:

- **HTTP adapter:** authenticates callers, enforces body limits, decodes JSON, and maps HTTP responses/errors.
- **Kafka adapter:** handles deserialization, schema/versioning, consumer acknowledgment, and retry/quarantine.
- **Transformer:** performs pure contract-driven type conversion without knowing whether data came from HTTP or Kafka.
- **Validator:** validates typed DTO invariants and applicable business rules.
- **Router:** selects priority/standard branches based on verified data.
- **Handler:** executes DB operations and API calls, owning transactions and idempotency.
- **Error flow:** separates parse failures, validation failures, and transient infrastructure failures.

### 16.1. Error Handling Differs Between HTTP and Kafka

An `OrderConversionException("INVALID_AMOUNT_FORMAT")` in HTTP can map to a 400/422 response per the API contract. With Kafka, there is no waiting HTTP caller; the consumer must decide offset/ack, retry, dead-letter topic, or quarantine. **Do not assume a Spring Integration exception automatically produces an HTTP status code or DLQ entry.**

When the same Transformer serves two sources, error handling **at the source boundary** can differ while the converter and error codes remain shared.

### 16.2. When Should You Parse First and Validate Afterward?

After the converter produces `TypedOrder`, you can use Bean Validation or a custom validator to check cross-field relationships, domain bounds, and contextual policies—for instance, priority orders requiring a higher minimum value, currencies restricted by region, or `occurredAt` not drifting too far from receipt time.

For rules depending on **current time**, do not read the system clock inside the converter if the goal is deterministic type conversion. Pass `receivedAt` into a controlled context and evaluate the rule during business validation.

## 17. Performance and Large-Data Considerations

A pure converter can run fast, yet still needs resource management:

1. **Bound input size before parsing.** A numeric string millions of digits long must not reach a `BigDecimal` converter without adapter/schema size limits.
2. **Reuse `Pattern` and formatters safely.** `Pattern` is immutable/thread-safe when creating new matchers; `DateTimeFormatter` is immutable and safe to reuse.
3. **Never make HTTP/DB calls inside a converter.** Type conversion should stay CPU-local and testable.
4. **Use immutable DTOs.** For mutable collections or nested objects, consider defensive copies.
5. **Avoid repeated parsing.** Once `TypedOrder` exists, downstream should never do `new BigDecimal(order.amount().toString())`.
6. **Be cautious with default timezones.** Relying on host timezone can shift behavior across containers or regions.
7. **Avoid unbounded queues.** A Transformer provides no backpressure on its own. Under async processing, monitor queue depth, timeouts, and memory.
8. **Do not auto-retry deterministic parse failures.** Free resources and route invalid data to the appropriate failure path.

For very large or streaming payloads, design explicit batch/stream processing and memory limits. A Transformer returning a single object does not by itself eliminate parsing or serialization overhead.

## 18. Observability: Tracking Conversion Outcomes

When an upstream source changes format, type conversion failure rates spike suddenly. Measure **successes**, **failures**, and downstream impact.

| Metric | Meaning | Recommendation |
|---|---|---|
| `conversion_success_total{flow}` | Count of successfully converted messages | Keep `flow` label low cardinality |
| `conversion_failure_total{code}` | Failure count by stable error code | Never put raw values into labels |
| `conversion_duration_seconds{flow}` | Converter latency | Compare before/after deployments |
| `typed_validation_rejected_total{rule}` | Business rule rejections post-conversion | Keep separate from parse errors |
| `source_schema_version` | Producer version | Useful for diagnosing contract drift |
| `traceId` / `eventId` | Trace a specific message | Put in traces/logs per security policy |

### 18.1. Never Log Full Payloads

Raw payloads may hold personal, financial, or token data. When conversion fails, log `errorCode`, field name, source/schema version, and correlation ID—never the full rejected value. Some format errors stem from injection or exfiltration probes; sanitize values sent to logs, dashboards, and clients.

### 18.2. Do Not Turn Observability into a Pure Converter Side Effect

To keep the converter pure, emit metrics/logs in the Transformer endpoint adapter, advice, or error handler rather than calling networks/DBs inside `parseAmount`. If the metrics backend fails, conversion behavior must remain intact per system SLOs.

## 19. Common Pitfalls

### Pitfall 1 — Parsing `double` and Converting to `BigDecimal`

**Symptom:** monetary values acquire unexpected extra decimal digits and threshold comparisons fail.

**Fix:** construct `BigDecimal` directly from the source string and enforce grammar, scale, and rounding policy.

### Pitfall 2 — `Boolean.parseBoolean` Silently Coerces Invalid Inputs to `false`

**Symptom:** producer sends `"yes"` or `"1"`, and the message is treated as non-priority.

**Fix:** define an explicit vocabulary of valid strings, convert strictly, or document the expanded token set explicitly.

### Pitfall 3 — Parsing Timezone-Less Timestamps with Server Timezone

**Symptom:** identical inputs yield different instants between local and cloud environments.

**Fix:** require offsets/UTC or pass a trusted contract-defined `ZoneId`, and test across timezones.

### Pitfall 4 — Using a Transformer to Swallow Bad Input with `null`

**Symptom:** `MessageTransformationException` or messages vanish before reaching expected branches.

**Fix:** throw a coded conversion error; if errors should flow as data, use `ConversionOutcome` with a Router; reserve Filters for valid messages that do not match criteria.

### Pitfall 5 — Building a New Message Drops Trace or Correlation Headers

**Symptom:** payload converts cleanly, yet Gateways time out or logs lose correlation.

**Fix:** understand the difference between payload-returning and Message-returning Transformers; deliberately retain required headers and test `replyChannel` with real Gateways.

### Pitfall 6 — Manually Converting Raw JSON Strings Without Schema Management

**Symptom:** missing or renamed fields produce confusing nulls or type mismatches.

**Fix:** use a contract-driven decoder/schema first, then run the type Transformer; version payloads as producers evolve.

### Pitfall 7 — Retrying Deterministic Errors Infinitely

**Symptom:** `amountText="abc"` is reprocessed over and over, saturating queues and CPU.

**Fix:** classify non-retryable conversion failures, reject/quarantine them, and retry only recoverable transient errors.

### Pitfall 8 — Mixing Conversion with DB/API Calls

**Symptom:** unit tests depend on network calls, retries trigger duplicate side effects, and conversion bugs look like timeouts.

**Fix:** separate pure converters, enrichment services, and business handlers into endpoints with distinct error policies.

### Pitfall 9 — Silently Defaulting Invalid Data

**Symptom:** blank currency becomes USD, blank timestamp becomes now, or blank amount becomes zero without policy approval.

**Fix:** apply defaults only when explicitly stated in the contract with source/version awareness; never fabricate business values.

### Pitfall 10 — Skipping Post-Conversion Validation

**Symptom:** parsing succeeds, yet business handlers receive disallowed states.

**Fix:** keep domain validation, authorization checks, and state-dependent invariants at the right transactional boundary after type conversion.

### Pitfall 11 — Wrong Channel Names or Two Endpoints Competing on One `DirectChannel`

**Symptom:** converter tests pass, yet messages never reach the expected branch at runtime.

**Fix:** write integration wiring tests, pick either `@Transformer` or Java DSL for a given input, and remember `DirectChannel` does not broadcast.

### Pitfall 12 — Decoding JSON Numbers as `Double` Before the Transformer

**Symptom:** `RawOrder` already holds a float-derived numeric representation, and the converter cannot recover exact digits.

**Fix:** configure the JSON decoder properly, preferring strings or `BigDecimal` in the contract when exact monetary precision matters.

## 20. Practice Exercises

**Context:** a system receives orders over HTTP and Kafka; both sources decode into `RawOrder`. Before routing, payloads must be normalized into `TypedOrder`.

### Exercise 1 — Basic Conversion

Create `RawOrder`, `TypedOrder`, `CurrencyCode`, `OrderConversionException`, and `OrderTypeConverter`. Write tests for:

~~~text
" ORDER-1001 ", "1250.50", "usd",
"2026-11-21T02:30:00Z", "TRUE"
~~~

Verify `orderId` is trimmed, `amount` is `BigDecimal("1250.50")`, `currency` is `USD`, timestamp matches `Instant`, and `priority` is `true`.

### Exercise 2 — Coded Invalid-Data Rejections

Test: zero amount, negative amount, comma-formatted amount, more than two decimal places, unsupported currency, timestamp without timezone, and priority `"yes"`. Assert stable error codes.

### Exercise 3 — Annotation Transformer

Wire `orders.raw` → `OrderTransformer` → `orders.typed`. Send a `Message<RawOrder>` carrying `traceId` and `businessCorrelationId`. Assert the output payload type and that headers remain present.

### Exercise 4 — Java DSL

Rewrite the pipeline with `.transform(RawOrder.class, converter::convert)` without registering two consumers on the same `DirectChannel`. Compare integration test results with the annotation configuration.

### Exercise 5 — Error Flow

Send `amountText="bad"`; with `DirectChannel`, inspect the exception and cause chain. Switch to `ExecutorChannel` or an inbound broker adapter and design `ErrorMessage`/rejection handling. Explain why deterministic errors should not be retried.

### Exercise 6 — Timezone Conversion

Allow local date-time strings from a dedicated producer along with a timezone field. Write explicit `ZoneId` conversion and test invalid timezones as well as DST gaps/overlaps.

### Exercise 7 — Custom `ConversionService`

Implement `Converter<RawOrder, TypedOrder>` backed by `OrderTypeConverter` and register it in an appropriately scoped service. Check whether other consumers of the service can convert it, and discuss the impact of global converter registration.

### Exercise 8 — Combining Router and Filter

After `TypedOrder`, use a Router to separate `priority=true` from the standard branch and a Filter to drop events outside a promotional campaign. Assert downstream endpoints never re-parse strings.

### Exercise 9 — Header Propagation

Build one Transformer returning a `TypedOrder` payload and another returning `Message<TypedOrder>`. Compare headers—especially `traceId`, `replyChannel`, and `businessCorrelationId`. Add a request-reply Gateway to test real behavior.

### Exercise 10 — Versioned Schema Evolution

Producer v2 adds a new currency or changes priority representation to `"1"/"0"`. Design converter versioning or pre-conversion routing so v1 data is never silently misinterpreted.

### Self-Check Questions

1. How does a Transformer differ from a JSON decoder and a Filter?
2. Why construct `BigDecimal` directly from a string rather than parsing `double`?
3. What does `Boolean.parseBoolean("yes")` return, and why can that be dangerous?
4. When a timestamp lacks a timezone, what information is missing to construct an `Instant`?
5. Why can a globally registered Converter affect multiple flows?
6. If a `@Transformer` method returns `null`, is that treated as a Filter rejection?
7. How does a payload-returning Transformer differ from a `Message<?>`-returning Transformer regarding header propagation?
8. Should an `INVALID_AMOUNT_FORMAT` error be retried multiple times?
9. Why do converter unit tests not prove the target channel exists?
10. When a message passes through a Transformer, which metadata enables tracing and preserves request–reply?
11. Why should you not default a missing currency to `"USD"` unless the contract specifies it?
12. If data already lost precision because a JSON decoder parsed to `Double`, can the Transformer restore exact precision?
13. How do you measure conversion failures without exposing full raw payloads?
14. When using Splitter/Aggregator, can payload transformation affect correlation/sequence metadata?

## 21. Design Checklist

- [ ] Defined input contract and strongly typed output DTO.
- [ ] Minimal decoding/validation performed upfront at the trust boundary before the Transformer.
- [ ] Amounts use `BigDecimal` with explicit grammar, scale, and rounding policy.
- [ ] Booleans and enums accept only published tokens.
- [ ] Timestamps carry explicit offsets/timezones or follow an explicit `ZoneId` rule.
- [ ] No silent coercion from bad data to business defaults.
- [ ] Converter is pure, free of DB/API/clock/side effects.
- [ ] Conversion exceptions carry stable error codes without leaking sensitive raw input.
- [ ] Chosen either `@Transformer` or Java DSL consistently with clear channel wiring.
- [ ] Never uses `return null` to filter messages.
- [ ] Understands payload returns vs. full `Message` returns and header propagation rules.
- [ ] Tested required `traceId`/`correlation`/`replyChannel` headers.
- [ ] Deterministic data errors are not retried infinitely; infrastructure failures use bounded retries.
- [ ] Covered by unit tests, parameterized tests, and integration tests.
- [ ] Downstream consumers receive `TypedOrder` and never re-parse strings.
- [ ] Monitoring tracks successes, conversion failures, latency, and schema changes.
- [ ] Serialization and trust-boundary limits evaluated when crossing brokers/stores.
- [ ] Versioning strategy prepared for producer format changes.

## 22. Summary

**Data type conversion** is a natural responsibility of a **Transformer** in Spring Integration. A raw payload may hold strings representing money, timestamps, and boolean flags; the Transformer converts them into `BigDecimal`, `Instant`, enums, and booleans under an **explicit contract**, so downstream Filters, Routers, and Service Activators never repeat parsing or accept ambiguous data.

A practical approach is: **decode at the protocol boundary → pure Java converter → `@Transformer` or Java DSL → business validation → routing/processing**. Distinguish conversion errors from normal rejections, preserve appropriate metadata, enforce idempotency in side-effecting handlers, and test through real channels. This allows the **SPRING_INTEGRATION_PATTERN** module to combine Transformers with Gateways, Routers, Filters, Splitters/Aggregators, retries, and error channels in controllable, extensible, and observable flows.

### References

- Spring Integration Reference — Transformer: https://docs.spring.io/spring-integration/reference/transformer.html
- Spring Integration Reference — Java DSL: https://docs.spring.io/spring-integration/reference/dsl.html
- Spring Integration API — `@Transformer`: https://docs.spring.io/spring-integration/api/org/springframework/integration/annotation/Transformer.html
- Spring Framework Reference — Spring Type Conversion: https://docs.spring.io/spring-framework/reference/core/validation/convert.html
- Spring Framework API — ConversionService: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/convert/ConversionService.html
- Spring Framework API — Converter: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/convert/converter/Converter.html
- Java SE API — BigDecimal: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html
- Java SE API — Instant: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html
- JUnit 5 User Guide — Parameterized Tests: https://junit.org/junit5/docs/current/user-guide/#writing-tests-parameterized-tests
