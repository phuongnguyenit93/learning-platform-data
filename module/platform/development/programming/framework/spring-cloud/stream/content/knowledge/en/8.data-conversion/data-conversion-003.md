# Converting JSON to POJO or Java Record

In a message stream, brokers typically store or transmit payloads as bytes. Java applications, however, prefer working with structured data types such as `OrderCreated`, `Customer`, or `OrderLine`. Spring Cloud Stream combines the binder, function type information, and message converters to turn JSON payloads into Java objects before invoking handler functions. In the reverse direction, Java objects are converted into JSON when sending messages out to the broker.

This process frees business code from manually reading raw bytes or calling `ObjectMapper` in every consumer. For conversion to work properly, producers and consumers must agree on the JSON contract, target data types, and `content-type`. In the `SPRING_CLOUD_STREAM` module, this applies to the `Supplier`/`Function`/`Consumer` functional model and to Kafka, RabbitMQ, or Pulsar binders.

This lesson belongs to the **Data Conversion** chapter. We will cover JSON structures to POJOs and Java records, binding configuration, nested fields, schema control, and diagnosing conversion errors.

## 1. From JSON on the Broker to Java Objects

Suppose a producer sends an order event as JSON:

```json
{
  "orderId": "ORD-2026-0042",
  "total": 1250000.50,
  "createdAt": "2026-11-24T08:30:00Z",
  "customer": {
    "customerId": "CUS-018",
    "name": "Nguyen An"
  },
  "items": [
    {
      "sku": "COFFEE-01",
      "quantity": 2,
      "unitPrice": 250000.25
    },
    {
      "sku": "TEA-03",
      "quantity": 3,
      "unitPrice": 250000.00
    }
  ]
}
```

The payload above contains primitive/simple fields (`orderId`, `total`), a timestamp field (`createdAt`), a nested object (`customer`), and an array of objects (`items`). In the application, we want to access data via strongly typed Java methods, such as `event.customer().name()` or `event.items().get(0).sku()`.

Overall conversion flow:

```text
Producer
  Java object
      |
      v
  Message converter (JSON)
      |
      v
  JSON bytes ----------------------> Broker
                                       |
                                       v
                                Binder receives message
                                       |
                                       v
                                Content type + target type
                                       |
                                       v
                                JSON message converter
                                       |
                                       v
                                POJO / Java record
                                       |
                                       v
                                Function / Consumer
```

Key steps on the receiving side:

1. The binder receives a message from a topic, queue, or subscription and turns it into a Spring `Message`.
2. The framework determines the content type, typically via the `contentType` header or the binding's `content-type` configuration.
3. The function's input type provides information about the Java type the application expects.
4. A matching message converter reads the JSON and creates the Java object.
5. Spring Cloud Stream invokes the function with the converted payload.

On the sending side, the converter performs the reverse process: taking the Java payload, serializing it into JSON according to the content type, and passing the message to the binder to send to the broker. Converter details and configuration may vary by framework version, but the principle is that content type describes the payload format while the function's parameter type describes the data type the application wants to receive.

## 2. `content-type` Indicates the Payload Is JSON

Spring Cloud Stream uses content type to choose how to convert messages. For JSON, the common value is `application/json`. It can be declared per binding:

```yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: order-processing
          content-type: application/json
```

The `processOrder-in-0` input binding reads messages from the `orders.created` destination and declares that the payload is JSON-formatted. If the function accepts `OrderCreated`, the converter attempts to construct an object of that type from the JSON.

For functions with an output, content type can be declared on the output binding:

```yaml
spring:
  cloud:
    function:
      definition: enrichOrder
    stream:
      bindings:
        enrichOrder-in-0:
          destination: orders.created
          group: order-enrichment
          content-type: application/json
        enrichOrder-out-0:
          destination: orders.enriched
          content-type: application/json
```

`content-type` can be written in kebab-case in YAML configuration; Spring Boot maps it to the corresponding Java property. In some flows, messages may also carry a `contentType` header. Ensure that outbound metadata and binding configuration do not conflict, especially when the same destination serves multiple message types.

Do not assume every payload is JSON just because the config file ends in `.yml` or because the producer is written in Java. Brokers typically store only bytes and metadata; producers and consumers must agree on the actual format.

## 3. Mapping JSON to a POJO

A POJO (Plain Old Java Object) is a standard Java class used to represent data. A DTO can have a default constructor, getters/setters, and fields corresponding to JSON properties.

```java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

public class OrderCreated {

    private String orderId;
    private BigDecimal total;
    private Instant createdAt;
    private Customer customer;
    private List<OrderLine> items;

    public OrderCreated() {
    }

    public String getOrderId() {
        return orderId;
    }

    public void setOrderId(String orderId) {
        this.orderId = orderId;
    }

    public BigDecimal getTotal() {
        return total;
    }

    public void setTotal(BigDecimal total) {
        this.total = total;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(Instant createdAt) {
        this.createdAt = createdAt;
    }

    public Customer getCustomer() {
        return customer;
    }

    public void setCustomer(Customer customer) {
        this.customer = customer;
    }

    public List<OrderLine> getItems() {
        return items;
    }

    public void setItems(List<OrderLine> items) {
        this.items = items;
    }
}
```

Nested types also need matching structures:

```java
import java.math.BigDecimal;

class Customer {
    private String customerId;
    private String name;

    public Customer() {}

    public String getCustomerId() { return customerId; }
    public void setCustomerId(String customerId) {
        this.customerId = customerId;
    }

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }
}

class OrderLine {
    private String sku;
    private int quantity;
    private BigDecimal unitPrice;

    public OrderLine() {}

    public String getSku() { return sku; }
    public void setSku(String sku) { this.sku = sku; }

    public int getQuantity() { return quantity; }
    public void setQuantity(int quantity) { this.quantity = quantity; }

    public BigDecimal getUnitPrice() { return unitPrice; }
    public void setUnitPrice(BigDecimal unitPrice) {
        this.unitPrice = unitPrice;
    }
}
```

Jackson is commonly used to serialize and deserialize JSON in Spring applications. With POJOs, the converter relies on constructors and Java properties recognized by Jackson. Getters/setters, constructors, and property names must be compatible with how the mapper is configured. There is no need to instantiate an `ObjectMapper` inside each consumer when the framework converter already processes the payload.

## 4. Mapping JSON to a Java Record

Java records are a concise choice for immutable DTOs. A record declares its data components right in its header; the compiler generates the canonical constructor, accessors, and `equals`, `hashCode`, and `toString` methods.

```java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

public record OrderCreated(
    String orderId,
    BigDecimal total,
    Instant createdAt,
    Customer customer,
    List<OrderLine> items
) {}

public record Customer(
    String customerId,
    String name
) {}

public record OrderLine(
    String sku,
    int quantity,
    BigDecimal unitPrice
) {}
```

With Jackson compatibly configured by Spring Boot, JSON can be mapped into records by component name. For instance, the JSON field `orderId` is passed to the `orderId` component; the `customer` object is converted into a `Customer` record; each element in `items` becomes an `OrderLine`.

Records suit message DTOs well because data is normally created once during deserialization and does not need setters to mutate individual fields. If transformation is needed, a new record can be created with updated values. Records also clarify the function's input contract and enable compile-time type checking by the compiler.

Key points to note:

- JSON field names must match record component names or have corresponding mapping annotations.
- Required fields, nullability, and default values must be clearly specified in the contract.
- Primitive types such as `int` cannot represent `null`; if a field may be absent, consider wrapper types like `Integer` and perform business checks.
- Records do not validate data automatically. After deserialization, the application still needs validation for order IDs, quantities, monetary amounts, and business rules.
- Records require Java 16 or later as a standard feature; check the application's Java version before using them.

## 5. Using POJOs or Records in Spring Cloud Stream Functions

When the input type is explicitly declared, the framework can convert the payload to that type before calling the function. Example of a consumer accepting a record:

```java
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderConsumers {

    @Bean
    Consumer<OrderCreated> processOrder() {
        return event -> {
            System.out.println("Order: " + event.orderId());
            System.out.println("Customer: " + event.customer().name());
            System.out.println("Item count: " + event.items().size());
        };
    }
}
```

The default input binding for this function is `processOrder-in-0`. Configuration:

```yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: order-processing
          content-type: application/json
```

The consumer receives `OrderCreated`, not a JSON string. Deserialization happens at the message boundary before the business function executes. If the JSON cannot be mapped to the record, a conversion error occurs before the code inside the lambda runs.

If you want to read both payload and headers, use `Message<T>`:

```java
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.messaging.Message;

@Bean
Consumer<Message<OrderCreated>> processOrderMessage() {
    return message -> {
        OrderCreated order = message.getPayload();
        String correlationId = message.getHeaders()
            .get("correlationId", String.class);

        System.out.printf("Order %s, correlation %s%n",
            order.orderId(), correlationId);
    };
}
```

`Message<T>` maintains a clear boundary: `getPayload()` returns the converted business object, while `getHeaders()` contains transport or tracing metadata. Do not stuff correlation IDs, trace IDs, or routing information into the payload if they are purely message metadata.

## 6. Serializing Java Objects to JSON on Output

On the sending side, a `Function` can accept a DTO and produce another DTO. Spring Cloud Stream serializes the result according to the output binding's content type:

```java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;

record OrderAccepted(String orderId, String status) {}

@Bean
Function<OrderCreated, OrderAccepted> acceptOrder() {
    return order -> new OrderAccepted(order.orderId(), "ACCEPTED");
}
```

```yaml
spring:
  cloud:
    function:
      definition: acceptOrder
    stream:
      bindings:
        acceptOrder-in-0:
          destination: orders.created
          group: order-acceptance
          content-type: application/json
        acceptOrder-out-0:
          destination: orders.accepted
          content-type: application/json
```

The function returns `OrderAccepted`; the converter serializes the record into JSON and the binder sends it to the `orders.accepted` destination. Downstream consumers can declare `OrderAccepted` as their input type to deserialize it. As a result, business functions work with Java types instead of manually concatenating JSON strings.

## 7. Mapping Field Names and JSON Structures

In practice, JSON field names do not always match Java names. For example, an external API sends `customer_id` while Java uses `customerId`. Jackson annotations can be used to declare the mapping:

```java
import com.fasterxml.jackson.annotation.JsonProperty;

public record Customer(
    @JsonProperty("customer_id") String customerId,
    String name
) {}
```

When the JSON contains:

```json
{
  "customer_id": "CUS-018",
  "name": "Nguyen An"
}
```

Jackson maps `customer_id` into the `customerId` component. Annotations can also be used with POJOs. If the entire system follows snake_case conventions, you can configure a centralized naming strategy on `ObjectMapper`; keep configuration consistent across producers and consumers, avoiding conflicting annotations and global strategies.

Nested objects and arrays require corresponding Java types. For example, `List<OrderLine>` tells the converter that each element of the `items` array should be instantiated as an `OrderLine`. If raw types like unparameterized `List` or `Map` are declared, the application can lose element type information and have to cast at usage sites.

## 8. Numeric Types, Dates/Times, and Enums

Choose Java types suited to the meaning of the data:

| JSON | Common Java type | Notes |
|---|---|---|
| Identifier string | `String` or `UUID` | UUIDs must be valid format; codes with leading zeros should remain strings |
| Monetary amount | `BigDecimal` | Avoid `double` for monetary calculations requiring decimal precision |
| Quantity | `int` or `Integer` | Use wrapper if you need to distinguish a missing field from value 0 |
| Point in time | `Instant` | JSON should use ISO-8601 strings with offset or `Z` |
| Business date | `LocalDate` | Use only when data represents a date, not a point in time |
| Fixed status | `enum` | Define how to handle new or unrecognized enum values |

Example payload:

```json
{
  "orderId": "ORD-42",
  "total": 1250000.50,
  "createdAt": "2026-11-24T08:30:00Z",
  "deliveryDate": "2026-11-27",
  "status": "PENDING"
}
```

Corresponding record:

```java
import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;

public record OrderSnapshot(
    String orderId,
    BigDecimal total,
    Instant createdAt,
    LocalDate deliveryDate,
    OrderStatus status
) {}

enum OrderStatus {
    PENDING,
    ACCEPTED,
    CANCELLED
}
```

Spring Boot typically autoconfigures Jackson support for Java date/time types when the corresponding dependency is present. Even so, date/time formats must still be agreed upon. If a producer sends epoch numeric timestamps while the consumer expects ISO-8601 strings, conversion may fail or produce unexpected values. Specify the format explicitly in the contract and test with real payloads.

## 9. Missing Fields, Extra Fields, and Schema Evolution

Producers and consumers may be deployed at different times. A newer producer version may add JSON fields that an older consumer does not yet know about. Conversely, a newer consumer may expect a field that an older producer does not yet send.

Cases to consider:

| JSON change | Risk | Design approach |
|---|---|---|
| Adding an optional field | Older consumers may reject unknown fields, depending on mapper config | Define unknown property policy; consider `@JsonIgnoreProperties(ignoreUnknown = true)` when appropriate |
| Adding a required field | Newer consumers do not receive a value from older producers | Use valid defaults, controlled nullability, or a new schema version |
| Renaming a field | Older consumers cannot find the old name | Maintain aliases/compatibility during transition periods |
| Changing data type | Deserialization may fail or lose information | Avoid changing types in place; introduce a new field or a new contract version |
| Removing a field | Older consumers may still depend on it | Deprecate first, monitor consumers, then remove |

To ignore unknown JSON fields in a specific DTO, you can use:

```java
import java.math.BigDecimal;
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public record OrderCreated(
    String orderId,
    BigDecimal total
) {}
```

This policy is useful when a consumer only needs a subset of the contract and can safely ignore new fields. However, do not blindly enable ignoring all fields. If a new field carries business-critical data, ignoring it can cause the system to process incorrectly without raising an error.

Missing fields may become `null`, primitive default values, or cause errors depending on constructors, Java types, and Jackson configuration. Therefore, validate required fields after deserialization. You can use Jakarta Bean Validation with `@NotBlank`, `@NotNull`, `@Positive` and invoke a validator at the application layer, placing business validation where it fits the processing flow.

## 10. Message DTOs Should Be Separated from Storage Entities

Do not use JPA entities as message payloads by default. Entities may contain lazy relationships, internal fields, persistence annotations, or sensitive data that should not be sent across a broker. A dedicated DTO keeps the JSON contract under control:

```java
public record OrderCreated(
    String orderId,
    BigDecimal total,
    Instant createdAt
) {}
```

In your service, map entities to DTOs before returning to an output binding. This reduces coupling between database schema and message schema, avoids serializing proxies/lazy relationships, and limits exposure of internal data. DTOs also make it possible to preserve compatibility when entity structures change.

## 11. Common Conversion Errors

Deserialization errors typically occur before the business function is invoked. Some common scenarios:

| Symptom | Possible cause | Resolution |
|---|---|---|
| Cannot convert JSON to record | Field name mismatch, wrong data type, or constructor missing required value | Check JSON, record components, and annotations |
| `Cannot deserialize value` | JSON sends a string while Java expects a number, object, or enum | Fix the contract or define an appropriate converter |
| Date/time errors | Incorrect timestamp format or missing Java time support | Standardize on ISO-8601 and verify Jackson Java Time support |
| Errors caused by new fields | Consumer rejects unknown properties | Align on schema evolution and unknown-field policies |
| Values are `null` | Producer omitted field, field name differs, or field was excluded on serialization | Inspect actual payload and run post-conversion validation |
| Consumer receives `String` instead of DTO | Function declared `String`, or content type/converter mismatch | Check function signature, content type, and headers |
| Output is not JSON as expected | Output binding lacks proper content type or payload was already a JSON string | Check payload type and converter to avoid double serialization |

When diagnosing, inspect the raw message, content type, function target type, and converter exception. Do not only check logs inside the lambda, because failures can happen before the lambda is called.

## 12. Avoid Manual JSON Parsing When Converters Already Handle It

A common pitfall is declaring a consumer accepting `String`, then calling `ObjectMapper.readValue` inside every function:

```java
// Only use when the application truly needs to receive a raw JSON string.
Consumer<String> processRawJson = json -> {
    // Manually parse JSON here
};
```

If the payload is already JSON and the function knows the target type, declare `Consumer<OrderCreated>` or `Function<OrderCreated, Result>` directly. The framework can convert payloads at the binding boundary, making code shorter and types clearer.

Manual parsing still has its place: when an application needs to inspect the raw payload before choosing a schema, handle multiple different JSON structures on the same destination, or apply a specialized converter. In those cases, explicitly manage parse errors, encoding, schema versions, and data security.

Avoid double-serializing JSON. If you already have a JSON string and send that string as a JSON payload, the converter may produce a JSON string containing escaped JSON instead of the intended JSON object. Decide whether the payload is a Java object or a raw JSON string and configure content type accordingly.

## 13. Testing JSON Conversion

Test at least three layers:

1. **DTO tests:** verify sample JSON maps into POJOs/records with accurate values, numeric types, dates/times, nested objects, and lists.
2. **Function tests:** verify the business function receives the right Java type and produces the right output.
3. **Binding integration tests:** verify the binder, content type, destination, and message converter work together properly with a real broker or test binder.

Example Jackson test for a record:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.math.BigDecimal;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

class OrderCreatedJsonTest {

    private final ObjectMapper objectMapper = new ObjectMapper()
        .findAndRegisterModules();

    @Test
    void readsOrderJsonIntoRecord() throws Exception {
        String json = """
            {
              "orderId": "ORD-42",
              "total": 1250.50,
              "createdAt": "2026-11-24T08:30:00Z",
              "customer": {
                "customerId": "CUS-018",
                "name": "Nguyen An"
              },
              "items": []
            }
            """;

        OrderCreated order = objectMapper.readValue(json, OrderCreated.class);

        assertEquals("ORD-42", order.orderId());
        assertEquals("CUS-018", order.customer().customerId());
        assertEquals(new BigDecimal("1250.50"), order.total());
    }
}
```

The example above tests Jackson directly and does not replace Spring Cloud Stream integration tests. Integration tests should send a message with `content-type: application/json` into the binding and confirm the function receives the right DTO. You should also test malformed payloads, missing required fields, extra fields, unknown enum values, and invalid timestamps.

## 14. Process for Implementing a JSON Contract

When establishing a JSON stream between services:

1. Design the message schema with clear field names, data types, required fields, and date/time formats.
2. Create a POJO or Java record representing the payload; use dedicated DTOs for messaging contracts.
3. Declare concrete input/output types in `Supplier`, `Function`, or `Consumer`.
4. Configure `content-type: application/json` for the relevant bindings.
5. Verify that producers serialize properly and consumers deserialize using sample payloads.
6. Define how missing fields, extra fields, null values, and schema versions are handled.
7. Validate data after conversion before executing business logic.
8. Test bindings with a real binder or broker, including malformed payloads.
9. Monitor conversion errors, DLQs, and schema changes during deployment.

## 15. Self-Check

- [ ] Can explain the role of `content-type` in selecting a message converter.
- [ ] Can describe how JSON is converted into a POJO or Java record before invoking the function.
- [ ] Can write a record containing nested objects and a `List` of elements.
- [ ] Can distinguish converted Java payloads from raw JSON strings and message headers.
- [ ] Can choose appropriate `BigDecimal`, `Instant`, `LocalDate`, and wrapper types.
- [ ] Know how to use Jackson annotations to map JSON field names.
- [ ] Can analyze the impact of missing fields, extra fields, and schema changes.
- [ ] Can design DTO, function, and binding integration tests.

## Conclusion

Spring Cloud Stream uses content type, function input/output types, and message converters to turn JSON into POJOs or Java records before executing business logic. POJOs suit mutable structures, while records suit immutable DTOs and explicit type contracts. For a reliable message stream, producers and consumers must agree on field names, data types, date/time formats, and schema evolution policies. Test real payloads at both the Jackson and binding levels, and explicitly handle missing, extra, or invalid data.
