# Enums and Actual Serialized Values

Enums in Java help restrict a property to a known set of values—for example, an order status can only be pending payment, paid, or cancelled. However, constant names in source code are not necessarily the values the API sends over JSON. Jackson can serialize enums into constant names, custom strings, numbers, or objects. **springdoc-openapi** must accurately describe the values transmitted over HTTP so clients understand and send valid data.

When designing enum schemas, distinguish three layers:

1. **Internal value in Java:** the constant name or an attribute of the enum.
2. **Actual JSON value:** the output written to responses by the Jackson serializer and the values accepted in requests by the deserializer.
3. **OpenAPI value:** the elements in the schema **enum** property, along with their data type and format.

If these three layers do not match, Swagger UI may suggest wrong values, documentation may misdescribe responses, and clients generated from OpenAPI may send requests rejected by the server.

## 1. Default Enums in Java and JSON

Without special configuration, Jackson typically serializes an enum as its constant name:

~~~java
public enum OrderStatus {
    PENDING,
    PAID,
    CANCELLED
}
~~~

A DTO using the enum:

~~~java
public record OrderView(
    String id,
    OrderStatus status
) {}
~~~

The default JSON response looks like:

~~~json
{
  "id": "ORD-1001",
  "status": "PENDING"
}
~~~

The corresponding OpenAPI schema must describe the status property as a string and list the exact allowed values:

~~~yaml
OrderStatus:
  type: string
  enum:
    - PENDING
    - PAID
    - CANCELLED
~~~

Enum values are case-sensitive. For example, PENDING and pending are two different values in the contract. Do not use UI display labels like Awaiting payment if the API actually transmits PENDING.

## 2. Distinguishing Constant Names and Wire Values

In real systems, APIs often need stable, readable values or compatibility with other systems. Constant names may use Java conventions like PENDING_PAYMENT, while JSON uses the string pending-payment.

~~~java
public enum OrderStatus {
    PENDING_PAYMENT,
    PAID,
    CANCELLED
}
~~~

If Jackson still uses its default configuration, responses will contain PENDING_PAYMENT. To change the value sent over HTTP, configure serialization with annotations or a serializer. Do not only change the OpenAPI description to pending-payment while Jackson continues writing PENDING_PAYMENT.

An enum should have one clear definition of its wire value. Example:

~~~java
public enum OrderStatus {
    PENDING_PAYMENT("pending-payment"),
    PAID("paid"),
    CANCELLED("cancelled");

    private final String wireValue;

    OrderStatus(String wireValue) {
        this.wireValue = wireValue;
    }

    public String getWireValue() {
        return wireValue;
    }
}
~~~

Simply having the wireValue field does not make Jackson use it automatically. You must mark how to serialize it as shown in the next section.

## 3. Using @JsonValue to Serialize Custom Values

The **@JsonValue** annotation marks the method or field Jackson uses as the JSON value for an enum. Example:

~~~java
import com.fasterxml.jackson.annotation.JsonValue;

public enum OrderStatus {
    PENDING_PAYMENT("pending-payment"),
    PAID("paid"),
    CANCELLED("cancelled");

    private final String wireValue;

    OrderStatus(String wireValue) {
        this.wireValue = wireValue;
    }

    @JsonValue
    public String getWireValue() {
        return wireValue;
    }
}
~~~

When serialized, the resulting value is the custom string:

~~~json
{
  "status": "pending-payment"
}
~~~

When using an enum with @JsonValue, verify both directions:

- Serialization: constant PENDING_PAYMENT is written as the string pending-payment.
- Deserialization: a request containing pending-payment is converted back to constant PENDING_PAYMENT.

Jackson supports using the enum's @JsonValue during deserialization in compatible versions. However, if you need explicit control over aliases, input errors, or conversion rules, declare a factory with @JsonCreator.

## 4. Using @JsonCreator to Read JSON Values

@JsonCreator allows specifying how an enum is constructed from an input value. It can be combined with @JsonValue to define a canonical wire value:

~~~java
import java.util.Arrays;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonValue;

public enum OrderStatus {
    PENDING_PAYMENT("pending-payment"),
    PAID("paid"),
    CANCELLED("cancelled");

    private final String wireValue;

    OrderStatus(String wireValue) {
        this.wireValue = wireValue;
    }

    @JsonValue
    public String getWireValue() {
        return wireValue;
    }

    @JsonCreator
    public static OrderStatus fromWireValue(String value) {
        return Arrays.stream(values())
            .filter(status -> status.wireValue.equals(value))
            .findFirst()
            .orElseThrow(() ->
                new IllegalArgumentException("Unknown order status: " + value)
            );
    }
}
~~~

With the definition above:

| JSON Value | Result |
| --- | --- |
| pending-payment | PENDING_PAYMENT |
| paid | PAID |
| cancelled | CANCELLED |
| PENDING_PAYMENT | Not accepted unless the factory defines this alias |
| unknown | Rejected |

The factory should have clear rules for invalid values. When an exception is thrown during request binding, Spring/Jackson typically turns the error into an input error response, usually 400 depending on exception handler configuration.

If the API must accept legacy values while only emitting one canonical value, aliases can be handled in @JsonCreator:

~~~java
@JsonCreator
public static OrderStatus fromWireValue(String value) {
    return switch (value) {
        case "pending-payment", "PENDING_PAYMENT", "pending" ->
            PENDING_PAYMENT;
        case "paid", "PAID" -> PAID;
        case "cancelled", "CANCELLED" -> CANCELLED;
        default -> throw new IllegalArgumentException(
            "Unknown order status: " + value
        );
    };
}
~~~

In this case, requests can send multiple aliases, while responses still only emit the canonical value returned by @JsonValue. This is an important point when describing schemas: the set of values accepted in requests may be broader than the set of values emitted in responses.

## 5. Using @JsonProperty on Individual Enum Constants

If you only need to map constant names to specific strings, you can place @JsonProperty directly on each constant:

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;

public enum PaymentStatus {
    @JsonProperty("awaiting-payment")
    PENDING,

    @JsonProperty("settled")
    PAID,

    @JsonProperty("reversed")
    REFUNDED
}
~~~

Jackson uses the declared strings to serialize and deserialize the enum according to its configuration:

~~~json
{
  "paymentStatus": "awaiting-payment"
}
~~~

This approach fits when each constant has a simple JSON value. If aliases, input normalization, or complex conversion logic are needed, @JsonCreator expresses the rules more clearly.

Choose one consistent strategy for an enum. Avoid mixing multiple mapping mechanisms such as @JsonProperty, @JsonValue, @JsonCreator, and custom serializers without verifying precedence and actual `ObjectMapper` behavior.

## 6. When Jackson Configures Enums as Numbers or Objects

Enums are not always serialized as strings. `ObjectMapper` configuration or annotations can change the JSON type.

### Serializing enums as numbers

Jackson can be configured to write enums as ordinals or numeric codes. For example, if the application uses business codes:

~~~java
public enum PaymentStatus {
    PENDING(10),
    PAID(20),
    REFUNDED(30);

    private final int code;

    PaymentStatus(int code) {
        this.code = code;
    }

    @JsonValue
    public int getCode() {
        return code;
    }
}
~~~

The JSON response will contain a number:

~~~json
{
  "paymentStatus": 10
}
~~~

The OpenAPI schema must now describe an integer type, not a string:

~~~yaml
type: integer
format: int32
enum:
  - 10
  - 20
  - 30
~~~

Do not use ordinal as a stable API code. Ordinal depends on constant declaration order; adding or reordering enum constants can change published values. Use explicit business codes if the API requires numbers.

### Serializing enums as objects

With **@JsonFormat(shape = JsonFormat.Shape.OBJECT)** or a custom serializer, an enum can be written as an object instead of a scalar. Example:

~~~json
{
  "paymentStatus": {
    "code": "awaiting-payment",
    "label": "Awaiting payment"
  }
}
~~~

In this case, the schema is no longer a simple string enum. You must describe an object with code and label properties, along with their proper data types and constraints. Inspect the actual JSON before deciding on the schema.

### Global configuration affecting wire values

Jackson settings such as **WRITE_ENUMS_USING_TO_STRING**, **WRITE_ENUMS_USING_INDEX**, **READ_ENUMS_USING_TO_STRING**, or **ACCEPT_CASE_INSENSITIVE_ENUMS** can alter how enums are read and written. The exact impact depends on the Jackson version and how `ObjectMapper` is configured in Spring Boot.

If an enum overrides toString() or the application enables WRITE_ENUMS_USING_TO_STRING, emitted values may differ from constant names. If WRITE_ENUMS_USING_INDEX is enabled, JSON may contain ordinal numbers. Never assume the schema based solely on Java enum code; verify against the `ObjectMapper` used by Spring.

## 7. Describing Enums in OpenAPI with @Schema

Springdoc typically infers enum schemas from Java types and Jackson integration. For default enums, it can generate a schema with type string and an enum list. When custom wire values or serialization settings change the data type, inspect the output and add metadata if needed.

### Declaring allowableValues

Allowed values can be described with **@Schema(allowableValues = ...)**:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;

public record OrderView(
    String id,

    @Schema(
        description = "Order status in the API",
        type = "string",
        allowableValues = {
            "pending-payment",
            "paid",
            "cancelled"
        },
        example = "pending-payment"
    )
    OrderStatus status
) {}
~~~

In the example, the schema describes the string values emitted by the API. Ensure the allowableValues list matches the values serialized by Jackson. Modifying only the annotation without updating `ObjectMapper` can make documentation inaccurate.

For numeric codes, declare the appropriate type:

~~~java
@Schema(
    type = "integer",
    format = "int32",
    allowableValues = {"10", "20", "30"},
    example = "10"
)
PaymentStatus paymentStatus
~~~

Check the generated OpenAPI output to ensure the enum is represented as numbers rather than numeric strings. The annotation's allowableValues attribute accepts strings, while the schema's type determines how values are represented in the specification.

### Using enumAsRef to reuse schemas

When an enum appears in multiple requests and responses, you can generate a shared schema in components using **@Schema(enumAsRef = true)**:

The example below assumes the enum uses default serialization, meaning JSON contains constant names. If the enum uses **@JsonValue** or **@JsonProperty**, the list in the component must reflect the corresponding wire values.

~~~java
@Schema(
    name = "OrderStatus",
    description = "Order statuses supported by the API",
    enumAsRef = true
)
public enum OrderStatus {
    PENDING_PAYMENT,
    PAID,
    CANCELLED
}
~~~

Properties using the enum can reference the schema:

~~~yaml
components:
  schemas:
    OrderStatus:
      type: string
      description: Order statuses supported by the API
      enum:
        - PENDING_PAYMENT
        - PAID
        - CANCELLED
~~~

In requests or responses, the schema can use:

~~~yaml
status:
  $ref: '#/components/schemas/OrderStatus'
~~~

Using enumAsRef avoids repeating the enum list in many places and provides a single point of management when enum values change. However, only use a shared schema when operations genuinely share the same value set and wire value type.

## 8. Requests and Responses May Have Different Enum Sets

An API sometimes accepts legacy aliases in requests while only emitting canonical values in responses. For example:

- Requests accept pending-payment, pending, or PENDING_PAYMENT.
- Responses only return pending-payment.

A single shared enum schema cannot accurately express two different value sets without supplemental per-direction descriptions. In such cases, you can:

1. Create separate enum types or DTOs for requests and responses.
2. Declare distinct schemas for request and response properties using appropriate annotations.
3. Use `OpenApiCustomizer` to adjust schemas per operation when annotations are insufficient.
4. Simplify the contract by accepting only one canonical wire value if aliases are unnecessary.

Example of separating types:

~~~java
public enum OrderStatusInput {
    PENDING_PAYMENT,
    PENDING,
    PAID,
    CANCELLED
}

public enum OrderStatusOutput {
    PENDING_PAYMENT,
    PAID,
    CANCELLED
}
~~~

This is a modeling option. If you need to keep the same internal domain enum, you can use boundary DTOs or converters to map from the input contract to the business type and from the business type to the output contract.

Do not include every alias the server happens to accept in the response schema. The response schema must reflect values the server actually emits; the request schema must reflect values clients are allowed to send.

## 9. Enums in Query Parameters, Path Parameters, and Headers

Enums can appear in many places outside JSON bodies. Example:

~~~java
@GetMapping("/api/orders")
List<OrderView> findOrders(
    @RequestParam OrderStatus status
) {
    return orderService.findByStatus(status);
}
~~~

OpenAPI describes a query parameter with an enum schema:

~~~yaml
parameters:
  - name: status
    in: query
    required: true
    schema:
      type: string
      enum:
        - pending-payment
        - paid
        - cancelled
~~~

If Spring binds enums using default constant names while Jackson responses use a custom @JsonValue, verify query parameter conversion rules separately. Spring MVC's conversion service does not necessarily use the same mechanism as Jackson JSON deserialization.

This means:

- @JsonValue may control JSON bodies without automatically ensuring query parameters parse that wire value.
- Jackson's @JsonCreator is also not automatically used for @RequestParam or @PathVariable.
- If the API uses custom wire values in query/path parameters, provide a Spring converter such as **Converter<String, OrderStatus>** and verify both request binding and the OpenAPI parameter enum.

Converter example:

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.stereotype.Component;

@Component
public class OrderStatusConverter implements Converter<String, OrderStatus> {

    @Override
    public OrderStatus convert(String source) {
        return OrderStatus.fromWireValue(source);
    }
}
~~~

This converter lets Spring MVC convert query or path values into enums following application rules. The OpenAPI schema still needs to accurately describe the set of wire values accepted by the converter.

## 10. Verifying Actual Values with ObjectMapper

Before checking OpenAPI, confirm how the application's `ObjectMapper` reads and writes enums.

Test example:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class OrderStatusJsonTest {

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void writesCanonicalWireValue() throws Exception {
        String json = objectMapper.writeValueAsString(
            OrderStatus.PENDING_PAYMENT
        );

        assertThat(json).isEqualTo("\"pending-payment\"");
    }

    @Test
    void readsWireValue() throws Exception {
        OrderStatus status = objectMapper.readValue(
            "\"pending-payment\"",
            OrderStatus.class
        );

        assertThat(status).isEqualTo(OrderStatus.PENDING_PAYMENT);
    }
}
~~~

This is a Jackson-level test. It confirms serialization/deserialization independently of Springdoc. If the application has multiple `ObjectMapper` instances or custom converter configurations, verify the exact mapper used for HTTP message conversion.

## 11. Inspecting Enums in Generated OpenAPI

After starting the application, fetch the document:

~~~bash
curl -sS http://localhost:8080/v3/api-docs -o openapi.json
~~~

Inspect the enum schema:

~~~bash
jq '.components.schemas.OrderStatus' openapi.json
~~~

Inspect an operation whose request or response uses the enum:

~~~bash
jq '.paths["/api/orders"].get' openapi.json
~~~

Verify these points:

1. Schema type is string, integer, or object matching the actual JSON.
2. The enum list has the exact wire values and exact casing.
3. The example value belongs to the enum set.
4. Request and response schemas reflect any difference if the server accepts aliases.
5. Query/path/header parameters follow the same conversion rules enforced by Spring MVC.
6. If using enumAsRef, properties reference the right component with no duplicate schema names.

You can add assertions in integration tests to read /v3/api-docs and verify enum lists. If a schema uses $ref, resolve the reference to components.schemas before comparing values.

## 12. Common Pitfalls

**Swagger UI displays constant names instead of wire values.** Check whether `ObjectMapper` uses @JsonValue or @JsonProperty. Then inspect the generated schema. If the schema still uses constant names, add @Schema(allowableValues) or adjust the schema with a customizer and re-test.

**Response returns strings but OpenAPI describes integer.** Check @JsonValue, WRITE_ENUMS_USING_INDEX, or custom serializers. The OpenAPI type must match actual JSON.

**Request JSON accepts a value but query parameter fails.** JSON deserialization and Spring MVC conversion are two separate paths. Create a Converter<String, Enum> if custom wire values are needed in query or path parameters.

**Added aliases but schema does not reflect them properly.** Decide whether aliases are only for requests or also emitted in responses. If the two directions differ, use separate schemas instead of one misleading shared enum.

**Reordering constants changes the API.** Check whether the application serializes ordinal/index. Use explicit, stable wire codes instead of depending on constant declaration order.

**Enum becomes an object while schema remains string.** Check @JsonFormat(shape = OBJECT) or custom serializers and declare the corresponding object schema.

## 13. API Enum Design Checklist

- [ ] Identify the actual enum values emitted by JSON responses.
- [ ] Identify the set of values accepted by JSON requests.
- [ ] Define binding rules separately for query, path, and header parameters.
- [ ] Choose one clear Jackson strategy: default, @JsonValue, @JsonProperty, or custom serializer.
- [ ] Use @JsonCreator if parsing control or alias support is needed.
- [ ] Do not use ordinals as stable API values.
- [ ] Describe type and enum accurately in OpenAPI.
- [ ] Use @Schema(enumAsRef = true) when the schema is genuinely shared.
- [ ] Verify `ObjectMapper` and runtime JSON.
- [ ] Inspect /v3/api-docs and Swagger UI after changing enums.

## 14. Summary

Java enums are only an internal representation of a set of states. API values depend on how Jackson serializes and deserializes them, how Spring MVC binds parameters, and what schema springdoc generates. Define wire values first, configure Jackson consistently, describe the accurate type and enum list in OpenAPI, and test both actual requests and responses. When requests support aliases or bind differently from responses, use separate contracts per direction so clients never have to guess valid values.

## 15. References

- [Jackson Annotations — JsonValue](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonValue.html): marks the value used when serializing an enum or property.
- [Jackson Annotations — JsonCreator](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonCreator.html): defines the constructor or factory used to create values from JSON.
- [Swagger Core — Schema annotation](https://javadoc.io/doc/io.swagger.core.v3/swagger-annotations/latest/io/swagger/v3/oas/annotations/media/Schema.html): allowableValues and enumAsRef attributes of the schema annotation.
- [Springdoc OpenAPI documentation](https://springdoc.org/): how springdoc generates and customizes OpenAPI schemas from Spring applications.
