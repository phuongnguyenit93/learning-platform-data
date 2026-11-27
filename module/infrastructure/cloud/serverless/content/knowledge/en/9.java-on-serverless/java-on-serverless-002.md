# Mapping Events to DTOs and Controlling Serialization

In the **Java on Serverless** chapter, functions often receive data from multiple sources such as HTTP APIs, queues, event buses, object storage, or schedulers. Each source may have its own request structure, but Java business logic needs to work with stable, testable data types. Converting an event into a DTO (Data Transfer Object) establishes the boundary that decouples platform formats from the application model.

Serialization is the process of converting a Java object into a transmissible or storable format, such as JSON. Deserialization is the process of reading that format and reconstructing a Java object. Without controlling both directions, a minor change in a field name, date-time format, enum, or null value can cause a function to fail on incoming messages, or emit payloads that downstream consumers cannot parse.

This lesson belongs to the **CLOUD_SERVERLESS** module, focusing on developing and deploying serverless applications, particularly Java functions triggered by HTTP, messages, or events. When deploying FaaS, you must design DTOs and serialization to be compatible with triggers, handle invalid data, support contract versioning, and avoid leaking sensitive data in logs. These decisions directly affect retries, idempotency, cold starts, and scalability.

The Java examples in this lesson use records, text blocks, and switch expressions, assuming a Java 17 or later runtime. Jackson requires a version supporting records (2.12 or later); date-time handling is provided by the jackson-datatype-jsr310 package. If a project runs on an older runtime, adjust the DTOs and syntax accordingly and verify the library compatibility matrix.

## 1. Why map events to DTOs?

Platform events typically contain both transport metadata and business data. For example, an HTTP request includes method, headers, path, query parameters, and body. A queue message includes message ID, receipt handle, receive timestamp, delivery count, and body. An object storage event includes bucket, object key, size, and metadata.

Business logic usually needs only a subset of that data. If a domain service accepts provider-specific event types directly, it becomes coupled to transport structures and difficult to test outside the FaaS runtime.

DTOs create an explicit contract at the application boundary:

- The adapter receives the event from the trigger.
- The deserializer converts JSON or the payload into an appropriate DTO type.
- The validator checks structural and input data rules.
- The mapper converts the DTO into a command or internal model.
- The use case executes the business logic.
- The response mapper or serializer builds the return value or outgoing event.

~~~mermaid
flowchart LR
    T["HTTP / Queue / Event"] --> A["Trigger adapter"]
    A --> E["Envelope / raw payload"]
    E --> D["Deserializer"]
    D --> V["DTO validation"]
    V --> M["Mapper"]
    M --> C["Command / use case"]
    C --> R["Business result"]
    R --> S["Serializer"]
    S --> O["HTTP response / outgoing event"]
~~~

Separating these stages clarifies where an error occurs. Malformed JSON is a parse error; a missing required field is a contract error; a type-valid value violating a rule such as a negative quantity is a business validation error; a storage failure is a processing error. Each error category has a distinct retry and response policy.

## 2. Distinguishing event envelope, payload, and DTO

You should not treat an entire event as a single business DTO. An event can have three layers:

| Layer | Contents | Examples |
|---|---|---|
| Transport wrapper | Metadata provided by HTTP, queue, or platform | headers, messageId, receiptHandle |
| Event envelope | Shared event context | id, source, type, time |
| Business payload | Event-specific data | orderId, customerId, lines |

DTOs can represent an envelope, a payload, or a specific request/response. Name them by role to avoid ambiguity, such as **CloudEventEnvelope<OrderPlacedData>**, **OrderPlacedData**, **PlaceOrderRequest**, and **PlaceOrderCommand**.

Example JSON event:

~~~json
{
  "specversion": "1.0",
  "id": "evt-1001",
  "source": "urn:example:orders",
  "type": "com.example.orders.order-placed",
  "time": "2026-11-17T10:15:30Z",
  "data": {
    "orderId": "ORD-1001",
    "customerId": "CUS-2001",
    "totalAmount": 1250000,
    "currency": "VND"
  }
}
~~~

The envelope describes the event and its origin. The data object is the business payload. Java can represent both parts with two separate DTOs:

~~~java
import java.time.Instant;

public record EventEnvelope<T>(
        String specversion,
        String id,
        String source,
        String type,
        Instant time,
        T data) {
}

public record DetailedOrderPlacedData(
        String orderId,
        String customerId,
        long totalAmount,
        String currency) {
}
~~~

The generic **EventEnvelope<T>** type allows reusing the envelope structure across multiple payloads. When deserializing, supply the full generic type to Jackson; passing only **EventEnvelope.class** can cause the data field to deserialize into a **Map** instead of **DetailedOrderPlacedData**.

In systems using CloudEvents, adhere strictly to CloudEvents attributes and protocol bindings. The DTO above is only a simplified internal envelope example, not a full implementation of the specification.

## 3. DTOs should reflect the contract, not the database schema

DTOs exchange data at boundaries. They do not need to mirror database entities or domain models.

Example incoming API payload:

~~~json
{
  "customerId": "CUS-2001",
  "items": [
    {
      "sku": "SKU-01",
      "quantity": 2
    }
  ],
  "requestedDeliveryDate": "2026-11-20"
}
~~~

Java DTOs:

~~~java
import java.time.LocalDate;
import java.util.List;

public record PlaceOrderRequest(
        String customerId,
        List<OrderItemRequest> items,
        LocalDate requestedDeliveryDate) {
}

public record OrderItemRequest(
        String sku,
        int quantity) {
}
~~~

The domain model may use different types:

~~~java
public record PlaceOrderCommand(
        CustomerId customerId,
        List<OrderLine> lines,
        DeliveryDate requestedDeliveryDate) {
}
~~~

The mapper converts the DTO into a command after validation:

~~~java
public final class PlaceOrderMapper {
    public PlaceOrderCommand toCommand(PlaceOrderRequest request) {
        return new PlaceOrderCommand(
                new CustomerId(request.customerId()),
                request.items().stream()
                        .map(item -> new OrderLine(
                                new ProductSku(item.sku()),
                                item.quantity()))
                        .toList(),
                new DeliveryDate(request.requestedDeliveryDate()));
    }
}
~~~

The types **CustomerId**, **OrderLine**, **ProductSku**, and **DeliveryDate** in this example are illustrative domain types. The core point is that DTOs represent the transport contract, while the domain model enforces business rules.

Do not pass JPA entities or objects with lazy-loading associations directly into events. Doing so can inadvertently serialize internal fields, circular references, ORM proxies, or sensitive data. Create explicit DTOs containing only fields permitted for publication.

## 4. Choosing appropriate Java data types

DTO field types determine how JSON is read and written. Choosing overly broad or mismatched types can cause precision loss, time zone errors, or ambiguity around missing values.

| Data | Java types to consider | Notes |
|---|---|---|
| String identifiers | **String** or value object | Validate format and length |
| Integer quantities | **int**, **long**, or wrapper | Pick appropriate bounds; wrappers distinguish null |
| Money and exact decimals | **BigDecimal** | Avoid **double** for monetary values |
| Date without time | **LocalDate** | JSON typically uses yyyy-MM-dd |
| Absolute point in time | **Instant** | Represent in UTC |
| Date-time with offset | **OffsetDateTime** | Preserve offset if required by contract |
| Lists | **List<T>** | Check for null, empty, and size limits |
| Possibly absent values | Wrapper, **Optional<T>**, or custom convention | Distinguish missing from null |
| Finite states | **enum** or controlled string | Define a policy when new values appear |

### 4.1. Currency and decimal numbers

Do not use **double** or **float** to represent monetary amounts requiring decimal precision. Binary floating-point types cannot represent all decimal numbers accurately.

Use **BigDecimal**:

~~~java
import java.math.BigDecimal;

public record PaymentData(
        String paymentId,
        BigDecimal amount,
        String currency) {
}
~~~

In JSON, amount may be represented as a number:

~~~json
{
  "paymentId": "PAY-01",
  "amount": 1250000.50,
  "currency": "VND"
}
~~~

The contract must specify currency, scale, rounding mode, and unit. Some systems send amount as a decimal string to prevent clients on other platforms from converting it into a floating-point type. When using strings, the schema must document the format and consumers must parse with validation.

### 4.2. Dates and times

**LocalDate** fits calendar dates such as a delivery date. **Instant** fits the moment an event occurred. Do not use **LocalDateTime** for a global timestamp if the payload has no time zone or offset, as consumers cannot unambiguously determine the exact instant.

Example:

~~~java
import java.time.Instant;
import java.time.LocalDate;

public record ShipmentEvent(
        String shipmentId,
        LocalDate deliveryDate,
        Instant createdAt) {
}
~~~

Corresponding JSON:

~~~json
{
  "shipmentId": "SHP-1001",
  "deliveryDate": "2026-11-20",
  "createdAt": "2026-11-17T10:15:30Z"
}
~~~

When using Jackson, register **JavaTimeModule** to serialize/deserialize **java.time** types. Standardize on ISO-8601 and UTC for timestamps across systems.

### 4.3. Primitives and wrappers

**int** cannot hold null. If JSON omits the quantity field, Jackson may assign the default value 0 to the primitive depending on configuration. That erases the distinction between "the sender omitted the field" and "the sender sent 0".

If a field is required, verify presence or use the **Integer** wrapper combined with validation. If 0 is valid and the field must always be present, configure deserialization/validation to detect omitted fields.

Note: **FAIL_ON_NULL_FOR_PRIMITIVES** only makes Jackson reject an explicit null value for a primitive; it does not automatically detect a primitive property omitted from JSON. An omitted field can still receive Java's default value, such as 0. If you must distinguish missing from 0, use wrappers with validation or track presence using a custom deserializer or dedicated DTO.

## 5. Configuring Jackson for Java serverless

Jackson is the standard library for JSON handling in Java. **ObjectMapper** performs serialization and deserialization. In serverless applications, configure the mapper once during environment initialization and reuse it across invocations.

Example configuration:

~~~java
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

public final class Json {
    private static final ObjectMapper MAPPER = createMapper();

    private Json() {
    }

    private static ObjectMapper createMapper() {
        ObjectMapper mapper = new ObjectMapper();

        mapper.registerModule(new JavaTimeModule());
        mapper.disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);

        mapper.enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
        mapper.enable(DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES);

        return mapper;
    }

    public static ObjectMapper mapper() {
        return MAPPER;
    }
}
~~~

The configuration above illustrates a strict contract policy. In systems that must remain compatible with producers that add new fields, you can allow ignoring unknown properties on specific DTOs. Apply that decision intentionally rather than toggling it ad hoc inside individual handlers.

**ObjectMapper** should be fully configured before concurrent use. Once in use, do not mutate global configuration across invocations. If different policies are required, create separate mappers or **ObjectReader**/**ObjectWriter** instances up front.

### 5.1. Deserializing JSON into a DTO

~~~java
String json = """
        {
          "customerId": "CUS-2001",
          "items": [
            {"sku": "SKU-01", "quantity": 2}
          ],
          "requestedDeliveryDate": "2026-11-20"
        }
        """;

PlaceOrderRequest request =
        Json.mapper().readValue(json, PlaceOrderRequest.class);
~~~

If JSON is malformed or types are incompatible, Jackson throws an exception such as **JsonProcessingException** or a subtype. The adapter must classify this as a payload error, log safely, and return a response or route the message to the error flow according to the trigger.

### 5.2. Serializing a DTO into JSON

~~~java
PlaceOrderRequest request = new PlaceOrderRequest(
        "CUS-2001",
        List.of(new OrderItemRequest("SKU-01", 2)),
        LocalDate.of(2026, 11, 20));

String json = Json.mapper().writeValueAsString(request);
~~~

In production, avoid logging the entire JSON if the payload contains personal data, tokens, or payment information. When logging is necessary, record only metadata or redacted fields.

### 5.3. Supporting generic types

When deserializing an envelope with a generic payload, use **TypeReference** to preserve type information:

~~~java
import com.fasterxml.jackson.core.type.TypeReference;

TypeReference<EventEnvelope<OrderPlacedData>> eventType =
        new TypeReference<>() {};

EventEnvelope<OrderPlacedData> event =
        Json.mapper().readValue(json, eventType);
~~~

If you only pass **EventEnvelope.class**, generic type arguments are erased at runtime. Jackson may construct a **LinkedHashMap** for data. This forces manual casting and forfeits compile-time type safety.

## 6. Controlling JSON field names

JSON field names may differ from Java property names. For instance, a producer uses **order_id**, while Java uses **orderId**.

### 6.1. Using JsonProperty

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;

public record OrderPlacedDto(
        @JsonProperty("order_id") String orderId,
        @JsonProperty("customer_id") String customerId) {
}
~~~

**JsonProperty** specifies the property name during both JSON reading and writing. This is the clearest option when a contract uses fixed names or differs from Java conventions.

### 6.2. Using a naming strategy

If the entire payload uses snake_case, you can configure a naming strategy:

~~~java
import com.fasterxml.jackson.databind.PropertyNamingStrategies;

ObjectMapper mapper = new ObjectMapper();
mapper.setPropertyNamingStrategy(
        PropertyNamingStrategies.SNAKE_CASE);
~~~

With this setting, **customerId** maps to **customer_id**. A naming strategy reduces repetitive annotations, but avoid applying it globally if the same function consumes multiple contracts with differing naming conventions.

### 6.3. Accepting legacy names with JsonAlias

When a producer is migrating field names, the consumer can accept both old and new names:

~~~java
import com.fasterxml.jackson.annotation.JsonAlias;
import com.fasterxml.jackson.annotation.JsonProperty;

public record CustomerDto(
        @JsonProperty("customerId")
        @JsonAlias({"customer_id", "clientId"})
        String customerId) {
}
~~~

**JsonProperty** defines the name used when serializing; **JsonAlias** allows accepting additional names when deserializing. Aliases are useful during transitions, but should not be kept indefinitely once producers have upgraded.

## 7. Missing, null, empty, and default

A frequent source of bugs is treating the following states as equivalent:

- The field is absent from the JSON.
- The field is present with a null value.
- The field is present with an empty string "".
- The field is present with an empty list [].
- The field is present with a default value such as 0 or false.

These states can carry different meanings. For example, in a profile-update API, an omitted field may mean "keep existing value", whereas null may mean "clear value". If a deserializer silently supplies defaults, the application may overwrite data unintentionally.

You can model these explicitly with wrappers or custom types. For simple DTOs, use **Integer** instead of **int** to distinguish null from 0. If you also need to distinguish missing from null, use presence tracking, a custom deserializer, or a wrapper type with states such as **Absent**, **Present(null)**, and **Present(value)**.

Example validating required fields:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Positive;
import jakarta.validation.Valid;
import java.util.List;

public record CreateOrderDto(
        @NotBlank String customerId,
        @NotEmpty List<@Valid OrderLineDto> lines) {
}

public record OrderLineDto(
        @NotBlank String sku,
        @Positive int quantity) {
}
~~~

Bean Validation can enforce **@NotBlank**, **@NotEmpty**, **@Positive**, and similar constraints. The application must invoke the validator explicitly after deserialization. Jackson only constructs the object; it does not enforce full application validation rules automatically.

## 8. Enums and new values from producers

Enums let the Java model express a finite set of states:

~~~java
public enum OrderStatus {
    PENDING,
    CONFIRMED,
    CANCELLED
}

public record OrderStatusDto(
        String orderId,
        OrderStatus status) {
}
~~~

However, a producer might introduce a new status before the consumer is deployed. If Jackson does not recognize the enum value, deserialization fails and the message may be retried continuously.

There are several ways to handle this:

1. **Strict enum:** Reject unknown values. Suitable when a new value changes critical logic and the consumer must be updated first.
2. **Default enum value:** Use **@JsonEnumDefaultValue** with **READ_UNKNOWN_ENUM_VALUES_USING_DEFAULT_VALUE**. Safe only when an UNKNOWN state exists and logic handles it explicitly.
3. **Keep the value as a String:** Convert to an enum or domain value after validation. Useful when the consumer needs to store or forward unknown values.

Example with a default value:

~~~java
import com.fasterxml.jackson.annotation.JsonEnumDefaultValue;

public enum OrderStatus {
    PENDING,
    CONFIRMED,
    CANCELLED,

    @JsonEnumDefaultValue
    UNKNOWN
}
~~~

Configuration:

~~~java
mapper.enable(
        DeserializationFeature.READ_UNKNOWN_ENUM_VALUES_USING_DEFAULT_VALUE);
~~~

Never silently collapse unknown states into PENDING or CONFIRMED. The default value must explicitly indicate "the consumer does not recognize this state" and prevent erroneous business decisions.

## 9. Nested DTOs, collections, and generic payloads

Events often contain lists or nested objects. Declare concrete types so the compiler and validator can verify them.

~~~java
import java.math.BigDecimal;
import java.util.List;

public record OrderPlacedData(
        String orderId,
        String customerId,
        List<OrderLineData> lines,
        BigDecimal totalAmount,
        String currency) {
}

public record OrderLineData(
        String productId,
        int quantity,
        BigDecimal unitPrice) {
}
~~~

When deserializing:

~~~java
OrderPlacedData data =
        Json.mapper().readValue(json, OrderPlacedData.class);
~~~

If the payload is a top-level list, use **TypeReference<List<OrderPlacedData>>**:

~~~java
List<OrderPlacedData> orders = Json.mapper().readValue(
        json,
        new TypeReference<List<OrderPlacedData>>() {});
~~~

Avoid using **List<Object>** or **Map<String, Object>** as the primary model for known contracts. Dynamic types fit flexible metadata, while business payloads should use concrete DTOs to enforce schema and type safety.

## 10. Custom serializers and deserializers

Sometimes an external contract uses a format different from the desired Java type. For example, a producer sends a numeric currency code while the application wants a **CurrencyCode** enum, or a timestamp uses a custom format.

You can use a custom deserializer to convert it:

~~~java
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.databind.DeserializationContext;
import com.fasterxml.jackson.databind.JsonDeserializer;
import java.io.IOException;

public final class CurrencyCodeDeserializer
        extends JsonDeserializer<CurrencyCode> {

    @Override
    public CurrencyCode deserialize(
            JsonParser parser,
            DeserializationContext context) throws IOException {

        String value = parser.getValueAsString();

        try {
            return CurrencyCode.valueOf(value);
        } catch (IllegalArgumentException failure) {
            return (CurrencyCode) context.handleWeirdStringValue(
                    CurrencyCode.class,
                    value,
                    "Unsupported currency code");
        }
    }
}
~~~

Attach the deserializer to the DTO:

~~~java
import com.fasterxml.jackson.databind.annotation.JsonDeserialize;

public record PaymentDto(
        String paymentId,
        @JsonDeserialize(using = CurrencyCodeDeserializer.class)
        CurrencyCode currency) {
}
~~~

Custom serializers can also format values when emitting events. However, do not write custom serializers if Jackson already supports the type out of the box. Conversion logic must be tested, handle errors cleanly, and avoid depending on global mutable state.

## 11. Polymorphic events and dispatching handlers by type

A subscription may receive multiple event types. For example, OrderPlaced, OrderCancelled, and PaymentSucceeded have different payloads. You can use the envelope's **type** to select the DTO and handler.

A clear approach is dispatching via a registry:

~~~java
public final class EventDispatcher {
    private final OrderPlacedHandler orderPlacedHandler;
    private final OrderCancelledHandler orderCancelledHandler;

    public EventDispatcher(
            OrderPlacedHandler orderPlacedHandler,
            OrderCancelledHandler orderCancelledHandler) {
        this.orderPlacedHandler = orderPlacedHandler;
        this.orderCancelledHandler = orderCancelledHandler;
    }

    public void dispatch(String type, JsonNode data) throws Exception {
        switch (type) {
            case "com.example.orders.order-placed" -> {
                OrderPlacedData dto = Json.mapper().treeToValue(
                        data, OrderPlacedData.class);
                orderPlacedHandler.handle(dto);
            }
            case "com.example.orders.order-cancelled" -> {
                OrderCancelledData dto = Json.mapper().treeToValue(
                        data, OrderCancelledData.class);
                orderCancelledHandler.handle(dto);
            }
            default -> throw new UnsupportedOperationException(
                    "Unsupported event type: " + type);
        }
    }
}
~~~

The example above assumes **JsonNode** is imported from Jackson and the envelope has already been validated. A registry can also be implemented as a map from type to handler for easier extensibility.

Do not enable Jackson default typing on untrusted payloads or allow JSON to specify Java class names directly for instantiation. Deserializing arbitrary classes introduces security risks. If polymorphic deserialization is used, enforce an explicit type allowlist and verify the data source. For event buses, dispatching by registered event type is usually easier to control.

## 12. Mapping events by trigger type

The same business payload may arrive from different triggers, but the outer wrapper typically varies.

### 12.1. HTTP trigger

An HTTP adapter may receive the request body and headers:

~~~java
public record HttpEvent(
        String method,
        Map<String, String> headers,
        String body,
        String requestId) {
}
~~~

The handler parses the body into a DTO:

~~~java
public final class PlaceOrderHttpHandler {
    private final PlaceOrderUseCase useCase;

    public PlaceOrderHttpHandler(PlaceOrderUseCase useCase) {
        this.useCase = useCase;
    }

    public HttpResponse handle(HttpEvent event) throws Exception {
        PlaceOrderRequest request = Json.mapper().readValue(
                event.body(), PlaceOrderRequest.class);

        // Validation and mapping are performed before calling the use case.
        PlaceOrderCommand command = mapAndValidate(request);
        PlaceOrderResult result = useCase.execute(command);

        return new HttpResponse(
                201,
                Json.mapper().writeValueAsString(result));
    }
}
~~~

The types **HttpResponse**, **PlaceOrderUseCase**, **PlaceOrderCommand**, and **PlaceOrderResult** are illustrative. On a concrete platform, the adapter must use the provider's request/response classes and HTTP status conventions. Validate empty bodies, Content-Type, payload size, encoding, and identity authentication before invoking business logic.

### 12.2. Queue trigger

Messages from a queue typically have a wrapper containing transport metadata and a body:

~~~java
public record QueueRecord(
        String messageId,
        String body,
        int receiveCount,
        String sentTimestamp) {
}
~~~

The body is parsed into a dedicated DTO:

~~~java
public void handle(QueueRecord record) throws Exception {
    OrderPlacedData eventData = Json.mapper().readValue(
            record.body(), OrderPlacedData.class);

    orderPlacedUseCase.processOnce(
            record.messageId(),
            eventData);
}
~~~

In practice, if the body contains a CloudEvent, parse the envelope first and then parse **data**. Never assume every queue places the payload directly inside the body. Some platforms wrap messages inside another event object or Base64-encode the body.

### 12.3. Event bus or stream

With an event bus, a function may receive a batch of records. Each record may have **source**, **detail-type**, **detail**, or an equivalent structure depending on the platform.

The adapter must translate the provider-specific structure into an internal model:

~~~java
public record NormalizedEvent(
        String eventId,
        String source,
        String type,
        Instant time,
        JsonNode payload) {
}
~~~

The dispatcher then maps **type** and payload to the concrete DTO. This keeps the use case independent of field names defined by a provider's event wrapper.

## 13. Controlling unknown properties and schema evolution

When a producer adds a new field, older consumers may receive payloads containing unknown properties. The **FAIL_ON_UNKNOWN_PROPERTIES** policy determines whether Jackson rejects or ignores those fields.

There are two common choices:

| Policy | Behavior | Best suited when |
|---|---|---|
| Strict | Rejects unknown properties | Closed contracts where unexpected changes must be detected immediately |
| Tolerant | Ignores unknown properties | Contracts allowing backward-compatible field additions |

Tolerant does not mean ignoring every change. If a producer alters the type of a known field or changes its business semantics, the consumer can still fail or misbehave.

You can allow unknown properties on a specific DTO:

~~~java
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public record CustomerUpdatedEvent(
        String customerId,
        String displayName) {
}
~~~

Avoid enabling tolerant mode globally without testing. Critical fields such as amount, currency, tenantId, or authorization context must be verified explicitly. An unexpected field may indicate a producer sent the wrong event type or an incompatible payload version.

### 13.1. Schema evolution rules

Adding new optional fields is usually safe if existing consumers can ignore them. Changes such as removing required fields, changing data types, changing units, or altering semantics generally break compatibility.

Versioning strategies include:

- Versioning in **dataschema**.
- Introducing a new event type for a breaking contract.
- Including a **schemaVersion** field in the payload per internal convention.
- Supporting multiple versions in the consumer during migration windows.

Never change the meaning of an event while keeping the same type. If **OrderPlaced** previously meant an order was recorded, do not reuse that type to mean the order has been paid.

## 14. Validation: successful parsing does not mean valid data

Deserialization only proves that JSON can be mapped into a Java type. It does not guarantee the data satisfies business rules.

Validation can be divided into three layers:

1. **Structural:** JSON is syntactically valid, fields have compatible types, and the envelope contains required attributes.
2. **Data:** strings are non-empty, numbers fall within bounds, collections have reasonable sizes, and dates are valid.
3. **Business:** the customer exists, the order can be placed, the state transition is permitted, and inventory is available.

Bean Validation example:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Positive;
import java.util.List;

public record CreateOrderDto(
        @NotBlank String customerId,
        @NotEmpty List<@Valid CreateOrderLineDto> lines) {
}

public record CreateOrderLineDto(
        @NotBlank String sku,
        @Positive int quantity) {
}
~~~

Validator:

~~~java
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;

public final class DtoValidator {
    private static final ValidatorFactory FACTORY =
            Validation.buildDefaultValidatorFactory();

    private static final Validator VALIDATOR =
            FACTORY.getValidator();

    private DtoValidator() {
    }

    public static <T> void validate(T dto) {
        var violations = VALIDATOR.validate(dto);

        if (!violations.isEmpty()) {
            throw new IllegalArgumentException(
                    "Payload validation failed: " + violations);
        }
    }
}
~~~

This example illustrates invoking Jakarta Bean Validation. In production, do not dump full violation objects or sensitive payloads into logs. Produce structured error codes and sanitized diagnostic details instead.

## 15. Handling serialization errors in serverless

Parse and validation errors must be distinguished from transient errors in downstream dependencies.

| Error type | Examples | Handling approach |
|---|---|---|
| Invalid JSON | Missing brace, bad encoding | Reject payload; generally do not retry indefinitely |
| Type mismatch | String sent for numeric field | Route to error flow or DLQ per policy |
| Missing required field | Absent orderId | Contract error; investigate producer |
| Data rule violation | Negative quantity | Reject or quarantine |
| Unsupported event type | Consumer lacks handler | Route to DLQ, alert, or ignore per contract |
| Transient processing error | Database timeout | Bounded retry with backoff |
| Output serialization error | Unsupported type or failing custom serializer | Log internal error; do not emit partial payload |

With queues, a permanent payload error can cause endless redeliveries if the handler simply throws an exception. Define which errors are retryable and which must go to a DLQ. For HTTP, return an appropriate status code such as 400 for invalid requests without exposing stack traces or internal details.

Never return success or ACK a message before all required steps finish. If a function succeeds but the response is lost, the message may be redelivered; the use case must remain idempotent.

## 16. Outbound serialization and event contracts

When publishing events, the serializer generates JSON from a DTO. Control which fields are exposed, their names, null handling, timestamp formatting, and schema version.

Outbound DTO example:

~~~java
import com.fasterxml.jackson.annotation.JsonInclude;
import java.time.Instant;
import java.util.List;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record OrderConfirmedEvent(
        String orderId,
        String customerId,
        Instant confirmedAt,
        List<String> productIds) {
}
~~~

**@JsonInclude(NON_NULL)** omits properties with null values during serialization. However, omitting a null field may have a different meaning from sending "field": null. Agree on the contract with consumers.

Never directly serialize domain entities or objects containing:

- Passwords, tokens, or secrets.
- Internal fields meant solely for persistence.
- Lazy proxies or circular relationships.
- Personal data unnecessary for consumers.
- Debug fields or runtime metadata.

It is best to create dedicated outbound DTOs containing only fields approved for publication.

## 17. Payload size, encoding, and binary data

Events may relate to files or binary data, but large files should not be embedded in JSON by default. Base64 encoding increases data size by roughly one-third and raises memory overhead during serialization/deserialization.

With object storage, typically send only a reference:

~~~json
{
  "fileId": "FILE-1001",
  "bucket": "documents",
  "objectKey": "invoices/2026/INV-1001.pdf",
  "contentType": "application/pdf",
  "sizeBytes": 245760
}
~~~

Consumers use appropriate permissions to read the object. Do not send long-lived signed URLs or credentials inside events. If using pre-signed URLs, keep expiration short, restrict permissions, and consider that events might be stored or replayed after the URL expires.

Enforce body size limits before parsing, especially for public HTTP triggers. Serializers/deserializers can also consume large amounts of memory if payloads are deeply nested or contain massive arrays. Set limits on request size, nesting depth, and element counts according to platform capabilities.

## 18. Security when deserializing untrusted data

JSON from HTTP, queues, or event buses must be treated as untrusted input requiring validation. Fundamental safeguards include:

- Accept only supported Content-Types and encodings.
- Limit payload size and structural nesting depth.
- Verify event type, source, and schema before invoking business logic.
- Do not enable polymorphic default typing for untrusted data.
- Never deserialize arbitrary classes based on class names in JSON.
- Validate numeric ranges, string lengths, list sizes, and URIs against contract bounds.
- Never log full raw payloads or credentials.
- Authenticate producers and enforce publish/subscribe permissions at the transport layer.

If using custom deserializers, handle errors in a controlled manner. Never let input values trigger file access, arbitrary URL fetching, expression evaluation, or instantiation of non-allowlisted classes.

## 19. Testing DTOs and serialization

Serialization is a contract across multiple components, so tests should target actual JSON rather than merely checking getters/setters.

Useful test categories:

- **Round-trip:** Serializing a DTO and deserializing it back preserves key values.
- **Golden JSON:** Comparing emitted JSON against published contract samples.
- **Compatibility:** New consumers can read older event versions; existing consumers handle compatible changes properly.
- **Invalid payload:** Malformed JSON, missing fields, type mismatches, or out-of-bounds values produce expected errors.
- **Unknown field/enum:** Verifying strict or tolerant behavior.
- **Date/time and decimal:** Verifying UTC, offsets, scale, and precision.
- **Security:** Ensuring secrets and internal fields never appear in serialized output.

JUnit example:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.math.BigDecimal;
import java.util.List;
import org.junit.jupiter.api.Test;

class OrderPlacedSerializationTest {
    @Test
    void roundTripPreservesOrderData() throws Exception {
        OrderPlacedData original = new OrderPlacedData(
                "ORD-1001",
                "CUS-2001",
                List.of(new OrderLineData(
                        "SKU-01", 2, new BigDecimal("500000.00"))),
                new BigDecimal("1250000.00"),
                "VND");

        String json = Json.mapper().writeValueAsString(original);

        OrderPlacedData restored = Json.mapper().readValue(
                json, OrderPlacedData.class);

        assertEquals(original, restored);
    }
}
~~~

Java records automatically generate value-based equals, allowing this test to compare two DTOs directly. For mutable DTOs or custom types, assert key fields and verify exact JSON formatting.

## 20. Optimizing serialization in FaaS environments

Serialization affects cold starts, CPU, memory, and latency. Optimization techniques include:

- Reuse a configured **ObjectMapper** rather than creating a new one per invocation.
- Use lean DTOs; avoid serializing entities or large object graphs.
- Avoid parsing the same JSON multiple times across layers.
- Register only required Jackson modules; omit unused libraries.
- Use streaming APIs for large payloads when incremental processing is needed.
- Bound batch sizes to avoid retaining too many objects on the heap.
- Measure parse, validation, mapping, and serialization durations separately when optimizing.

Do not optimize by skipping validation or loosening contracts before measuring a real bottleneck. A shared mapper must finish configuration before concurrent invocations occur; never mutate global settings while handling requests.

## 21. Workflow for mapping events to DTOs

A consistent workflow applicable to every trigger:

1. **Receive raw event:** Identify whether the source is HTTP, queue, stream, or event bus and determine the platform wrapper type.
2. **Validate transport:** Check source identity, Content-Type, encoding, request size, and access permissions.
3. **Separate envelope and payload:** Read message metadata or event context, identifying event type and schema version.
4. **Deserialize:** Select the appropriate DTO for the event type and schema version.
5. **Validate:** Check structure, data types, required fields, and domain rules.
6. **Map to command:** Convert the DTO into internal types so the use case stays transport-independent.
7. **Handle idempotency:** Use event ID, message ID, or idempotency key to prevent duplicate side effects.
8. **Handle errors:** Distinguish permanent payload errors from transient infrastructure errors; choose response, retry, or DLQ.
9. **Serialize output:** Use outbound DTOs and the published schema.
10. **Observe:** Record event ID, type, correlation ID, and outcome without logging sensitive data.

## 22. Common pitfalls

**Using the event wrapper as the domain model:** Couples business logic to provider structures and complicates testing. Introduce internal DTOs and boundary mappers.

**Using Map<String, Object> for every payload:** Sacrifices type checking and requires manual casting. Use concrete DTOs for known events; reserve maps for genuinely dynamic metadata.

**Losing generic type information during deserialization:** Causes payloads to become maps instead of DTOs. Use TypeReference or JavaType.

**Using double for money:** Introduces decimal precision errors. Use BigDecimal or smallest integer currency units per contract.

**Using LocalDateTime for global timestamps:** Lacks time zone context, making exact instants ambiguous. Use Instant or OffsetDateTime.

**Ignoring unknown fields globally:** Can mask producers sending the wrong contract. Choose strict or tolerant per event type and test compatibility.

**Enums unable to tolerate new values:** Causes consumers to fail continuously when producers add states. Choose strict, UNKNOWN, or controlled strings based on business needs.

**Calling the use case immediately after deserializing:** Successful parsing does not guarantee valid data. Validate before invoking business logic.

**Serializing database entities:** Can expose internal fields, lazy proxies, or sensitive data. Use dedicated outbound DTOs.

**Creating an ObjectMapper on every invocation:** Increases allocations and initialization overhead. Reuse an immutable mapper after configuration.

**Enabling default typing on untrusted data:** Opens risks of arbitrary class deserialization. Use allowlists and dispatch by event type.

**Retrying serialization errors indefinitely:** Invalid payloads will continue failing. Classify errors and route them to a DLQ or quarantine flow.

## 23. Pre-deployment checklist

- [ ] Transport wrapper, event envelope, and business payload are clearly separated.
- [ ] DTOs are decoupled from database entities and domain models.
- [ ] Each event type maps to the right DTO and handler.
- [ ] Generic payloads are deserialized with full type information.
- [ ] JSON field names, aliases, and naming strategies are standardized.
- [ ] Types for money, date-time, enums, and null/missing handling are chosen intentionally.
- [ ] ObjectMapper is configured once and reused safely.
- [ ] Java Time module and required modules are registered.
- [ ] Unknown property and new enum value policies are defined.
- [ ] Payloads are validated for structure, data constraints, and business rules.
- [ ] Payload size and nesting depth limits are enforced.
- [ ] Arbitrary classes are never deserialized from untrusted input.
- [ ] Outbound DTOs contain only fields approved for publication.
- [ ] Round-trip, golden JSON, and schema compatibility tests exist.
- [ ] Parse/validation errors are distinguished from transient errors for proper retry handling.
- [ ] Event ID/correlation ID and safe logging are in place for tracing.

## Conclusion

Mapping events to DTOs establishes a clear boundary between trigger formats and Java business logic. The envelope carries transport or event context; the payload is deserialized into a concrete DTO; the validator checks the data; the mapper converts the DTO into a command; and the use case executes the business operation. In the reverse direction, outbound DTOs and serializers produce payloads compliant with the consumer contract.

In serverless environments, reuse a configured ObjectMapper, pick accurate data types, control null and unknown fields, manage schema versions, enforce payload limits, and classify serialization errors. When contracts are tested and consumers tolerate duplicate messages, Java functions can reliably receive and emit events across HTTP, queues, and event buses without tight coupling to platform-specific structures.
