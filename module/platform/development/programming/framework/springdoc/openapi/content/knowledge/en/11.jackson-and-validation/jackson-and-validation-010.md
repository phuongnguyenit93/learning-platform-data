# Custom Serializers or Deserializers and Supplementary Schemas

Jackson determines how Java objects are converted to JSON when returning responses and how JSON is read into Java objects when receiving requests. springdoc-openapi builds specifications from controllers, Java types, annotations, and application metadata. When Jackson is configured with custom serializers or deserializers, the actual JSON structure can differ from the structure springdoc infers from Java types.

Therefore, check both sides of the contract: how Jackson actually writes/reads JSON and how OpenAPI publishes that data. If a serializer turns a Java value object into a JSON string, the schema must describe a string. If a deserializer expects a specific format, the schema should show the exact type, format, pattern, and example so clients send compatible data.

## 1. Where Do Serializers and Deserializers Operate?

Jackson has two primary processing directions:

- **Serialization**: converting Java objects into JSON, typically when a controller returns a response.
- **Deserialization**: reading JSON and creating Java objects, typically when Spring binds a request body into a DTO.

Common Jackson annotations include:

| Annotation | Effect |
|---|---|
| <code>@JsonSerialize</code> | Selects a serializer for a type or property |
| <code>@JsonDeserialize</code> | Selects a deserializer for a type or property |
| <code>@JsonProperty</code> | Sets the JSON property name and controls read/write access |
| <code>@JsonFormat</code> | Adjusts formatting for certain types, such as dates and times |
| <code>@JsonIgnore</code> | Excludes a property during JSON processing per annotation config |
| <code>@JsonCreator</code> | Specifies a constructor or factory method used to instantiate an object from JSON |
| <code>@JsonValue</code> | Selects the value used as the JSON representation of an object or enum |

Serializers/deserializers can be placed at the Java type level or on a specific property. Type-level placement applies wherever that type is used; property-level placement adjusts only a single field or record component.

## 2. Example: Java `Money` Transferred as a JSON String

Suppose an application stores monetary amounts using a <code>Money</code> value object with an <code>amount</code> property. Without customization, Jackson might serialize the object as:

~~~json
{
  "total": {
    "amount": 125000.00
  }
}
~~~

However, the API contract requires representing money as a string with a currency code:

~~~json
{
  "total": "VND 125000.00"
}
~~~

This is a wire-format change. The Java type remains <code>Money</code>, while the external JSON type is <code>string</code>. If OpenAPI continues describing <code>total</code> as an object with an <code>amount</code> property, clients will generate code and send payloads with the wrong structure.

### 2.1. Declaring the Value Object

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

import com.fasterxml.jackson.databind.annotation.JsonDeserialize;
import com.fasterxml.jackson.databind.annotation.JsonSerialize;

@JsonSerialize(using = MoneySerializer.class)
@JsonDeserialize(using = MoneyDeserializer.class)
public record Money(BigDecimal amount) {

    public Money {
        if (amount == null || amount.signum() < 0) {
            throw new IllegalArgumentException(
                "Amount must be a non-negative number"
            );
        }
        amount = amount.setScale(2, RoundingMode.HALF_UP);
    }
}
~~~

Both annotations bind the serializer and deserializer to the <code>Money</code> type. The constructor normalizes amounts to two decimal places and rejects negative or null values.

### 2.2. Writing the Serializer

~~~java
import java.io.IOException;
import java.math.RoundingMode;

import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.databind.JsonSerializer;
import com.fasterxml.jackson.databind.SerializerProvider;

public class MoneySerializer extends JsonSerializer<Money> {

    @Override
    public void serialize(
            Money value,
            JsonGenerator generator,
            SerializerProvider serializers) throws IOException {

        String wireValue = "VND "
            + value.amount()
                .setScale(2, RoundingMode.HALF_UP)
                .toPlainString();

        generator.writeString(wireValue);
    }
}
~~~

The serializer writes a JSON string via <code>writeString</code>. Hence, <code>Money(125000)</code> becomes <code>"VND 125000.00"</code> rather than a JSON object.

### 2.3. Writing the Deserializer

~~~java
import java.io.IOException;
import java.math.BigDecimal;

import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonToken;
import com.fasterxml.jackson.databind.DeserializationContext;
import com.fasterxml.jackson.databind.JsonMappingException;
import com.fasterxml.jackson.databind.JsonDeserializer;

public class MoneyDeserializer extends JsonDeserializer<Money> {

    @Override
    public Money deserialize(
            JsonParser parser,
            DeserializationContext context) throws IOException {

        if (!parser.hasToken(JsonToken.VALUE_STRING)) {
            throw JsonMappingException.from(
                parser,
                "Money must be a string such as VND 125000.00"
            );
        }

        String raw = parser.getText();
        if (!raw.startsWith("VND ")) {
            throw JsonMappingException.from(
                parser,
                "Money must start with VND"
            );
        }

        try {
            return new Money(new BigDecimal(raw.substring(4)));
        } catch (IllegalArgumentException exception) {
            throw JsonMappingException.from(
                parser,
                "Invalid VND amount",
                exception
            );
        }
    }
}
~~~

The deserializer requires the JSON token to be a string prefixed with <code>VND </code>. It then parses the numeric part into <code>BigDecimal</code> and instantiates the value object. JSON sending a raw number or a string with a different currency prefix is rejected.

In production code, clearly specify whether the currency code is fixed or variable, decimal precision, separators, and rounding behavior. This example shows VND with two decimal places solely to illustrate serializers/deserializers.

## 3. Adding an OpenAPI Schema Matching Actual JSON

DTO using <code>Money</code> in Java:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;

public record InvoiceResponse(
    @Schema(
        implementation = String.class,
        type = "string",
        description = "Total amount formatted as VND with two decimal places",
        pattern = "^VND [0-9]+\\.[0-9]{2}$",
        example = "VND 125000.00"
    )
    Money total
) {}
~~~

The attributes <code>implementation = String.class</code> and <code>type = "string"</code> instruct springdoc to describe <code>total</code> as a string, matching the output of <code>MoneySerializer</code>. <code>pattern</code> and <code>example</code> inform consumers of the accepted string format.

The corresponding schema looks roughly like:

~~~yaml
InvoiceResponse:
  type: object
  properties:
    total:
      type: string
      pattern: "^VND [0-9]+\\.[0-9]{2}$"
      description: Total amount formatted as VND with two decimal places
      example: "VND 125000.00"
~~~

For requests, apply the same schema to the property receiving <code>Money</code>:

~~~java
public record CreateInvoiceRequest(
    @Schema(
        implementation = String.class,
        type = "string",
        pattern = "^VND [0-9]+\\.[0-9]{2}$",
        example = "VND 125000.00"
    )
    Money total
) {}
~~~

Through the deserializer, JSON requests containing <code>"VND 125000.00"</code> convert into <code>Money</code> before reaching the controller. Through the serializer, responses containing that value object emit the same string format. The schema documents the shared wire format in both directions.

Note: the <code>@Schema</code> annotation adds OpenAPI metadata and does not alter Jackson. Conversely, <code>@JsonSerialize</code> and <code>@JsonDeserialize</code> alter runtime JSON, yet do not guarantee springdoc automatically infers the custom string schema. Inspect the actual output at <code>/v3/api-docs</code>.

## 4. Property-Level Serializers/Deserializers

You do not always want to change how a Java type is serialized across the whole application. Serializers and deserializers can be attached to a single property:

~~~java
public record PaymentResponse(
    @JsonSerialize(using = MoneySerializer.class)
    @JsonDeserialize(using = MoneyDeserializer.class)
    @Schema(
        implementation = String.class,
        type = "string",
        example = "VND 125000.00"
    )
    Money amount
) {}
~~~

In this example, the annotations affect only the <code>amount</code> property on this DTO. A <code>Money</code> property in another DTO continues using the default setup or its own serializer.

Property-level placement is helpful when the same Java type requires multiple wire formats. For instance, a legacy API accepts a formatted currency string while a newer API accepts an object with <code>amount</code> and <code>currency</code>. Each property needs its own serializer/deserializer and matching schema.

## 5. Registering Serializers/Deserializers with a Jackson Module

Besides annotations, serializers and deserializers can be registered via a <code>SimpleModule</code>. This suits cases where you do not want Jackson annotations on domain models or prefer centralized configuration:

~~~java
import com.fasterxml.jackson.databind.Module;
import com.fasterxml.jackson.databind.module.SimpleModule;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class JacksonConfiguration {

    @Bean
    Module moneyModule() {
        SimpleModule module = new SimpleModule("money-wire-format");
        module.addSerializer(Money.class, new MoneySerializer());
        module.addDeserializer(Money.class, new MoneyDeserializer());
        return module;
    }
}
~~~

Spring Boot automatically registers beans of Jackson's <code>Module</code> type with the framework-managed <code>ObjectMapper</code>. This ensures HTTP message converters and components using the Spring-managed mapper share the configuration.

This is an alternative to the type-level annotations shown earlier. If you choose module registration, remove <code>@JsonSerialize</code> and <code>@JsonDeserialize</code> from <code>Money</code> in that earlier example. Pick one consistent strategy; if both type-level annotations and a module are registered for the same type, verify which serializer Jackson selects at runtime. Avoid registering competing serializers for one type without checking precedence and output.

In Spring Boot, avoid instantiating a standalone <code>new ObjectMapper()</code> inside controllers or services for custom request handling, as that mapper may lack application modules, naming strategies, date/time modules, or configured settings.

## 6. Using @JsonComponent in Spring Boot

Spring Boot supports discovering Jackson components annotated with <code>@JsonComponent</code>. This is useful when you want Spring to manage serializers/deserializers without declaring individual module beans.

Skeleton declaration example:

~~~java
import java.io.IOException;

import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.databind.JsonSerializer;
import com.fasterxml.jackson.databind.SerializerProvider;
import org.springframework.boot.jackson.JsonComponent;

@JsonComponent
public class MoneyJsonComponent {

    public static class Serializer extends JsonSerializer<Money> {
        @Override
        public void serialize(
                Money value,
                JsonGenerator generator,
                SerializerProvider serializers) throws IOException {
            generator.writeString("VND " + value.amount().toPlainString());
        }
    }
}
~~~

You can add a matching nested deserializer in the same component. When using this approach, remove duplicate serializer/deserializer registrations elsewhere or verify how Spring Boot registers them. The skeleton above only illustrates component discovery; maintain the same formatting and error-handling rules as in the serializer/deserializer section above.

<code>@JsonComponent</code> is also an alternative to type-level annotations or module beans from earlier examples. Do not register all three mechanisms for the same type without an explicit reason.

## 7. When to Use @JsonFormat, @JsonValue, or @JsonCreator?

Not every custom format requires writing two serializer and deserializer classes. Jackson provides simpler annotations for straightforward cases:

| Mechanism | Suitable Use Case |
|---|---|
| <code>@JsonFormat</code> | Formatting dates, times, numbers, or enums within type support |
| <code>@JsonValue</code> | An object or enum represented by a single simple value |
| <code>@JsonCreator</code> | Constructor/factory taking a JSON value to instantiate the object |
| <code>@JsonSerialize</code> / <code>@JsonDeserialize</code> | Custom conversion logic or direct JSON token control |
| Jackson <code>Module</code> | Centralized, shared registration of conversion logic |

Example simple value object using <code>@JsonValue</code> to serialize as a string:

~~~java
import com.fasterxml.jackson.annotation.JsonValue;

public record ProductCode(String value) {

    @JsonValue
    public String jsonValue() {
        return value;
    }
}
~~~

To read the string back, use a delegating creator constructor:

~~~java
import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonValue;

public record ProductCode(String value) {

    @JsonCreator(mode = JsonCreator.Mode.DELEGATING)
    public ProductCode {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Product code is required");
        }
    }

    @JsonValue
    public String jsonValue() {
        return value;
    }
}
~~~

For date-time formats, consider <code>@JsonFormat</code> and Java Time module settings before writing a custom serializer. Regardless of mechanism, the OpenAPI schema must describe the final JSON format accurately.

## 8. Customizing Schemas When Annotations Are Not Enough

For complex schemas, you can supplement or adjust schemas using OpenAPI models and customizers. For example, if a serializer produces a string while many DTOs share that Java type and need a consistent schema, the team can define a reusable component schema and reference it on properties.

A component schema for the money format:

~~~yaml
components:
  schemas:
    VndAmount:
      type: string
      description: VND amount with two decimal places
      pattern: "^VND [0-9]+\\.[0-9]{2}$"
      example: "VND 125000.00"
~~~

In the DTO, reference the component:

~~~java
public record InvoiceResponse(
    @Schema(ref = "#/components/schemas/VndAmount")
    Money total
) {}
~~~

If springdoc still emits an inaccurate schema, you can use an <code>OpenApiCustomizer</code> to modify the schema in the output specification. Customizers affect only the OpenAPI spec; they do not change how Jackson writes or reads JSON. Always verify both sides are updated together.

With multiple <code>GroupedOpenApi</code> documentation groups, pick the right customizer scope. If the custom schema must appear in all grouped specs, consider <code>GlobalOpenApiCustomizer</code>; if only one group needs it, register the customizer on that group's configuration.

## 9. Aligning Serialization, Deserialization, and Validation

Three layers must remain consistent:

1. **Jackson** determines the actual JSON tokens, field names, and data formatting.
2. **OpenAPI Schema** documents the type, format, pattern, examples, and bounds clients must follow.
3. **Validation and domain rules** decide what inputs are accepted when requests reach the server.

Example with <code>Money</code>:

| Component | Rule |
|---|---|
| Serializer | Writes object as string such as <code>"VND 125000.00"</code> |
| Deserializer | Accepts only strings prefixed with <code>VND </code> and valid numeric part |
| OpenAPI | <code>type: string</code>, matching pattern and example |
| Validation/domain rule | Rejects negative amounts; applies scale of two decimal places |

If the deserializer rejects strings violating the pattern, the schema should document that exact pattern. If the constructor rejects negative numbers, the schema may specify a non-negative pattern, yet runtime must still validate because patterns and domain validation can differ in detail.

In particular, verify null handling separately. Jackson typically handles JSON null through its null-value mechanism rather than invoking <code>deserialize</code> as with a string token. If a type must disallow null, ensure Bean Validation or constructor/service logic rejects null; the schema must also reflect appropriate requiredness and nullability.

## 10. Testing with ObjectMapper and Real Endpoints

Never inspect annotations alone and assume output is correct. Verify the JSON generated by Spring's mapper.

Example test for serializer/deserializer:

~~~java
import java.math.BigDecimal;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class MoneyJsonTest {

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void writesMoneyAsString() throws Exception {
        String json = objectMapper.writeValueAsString(
            new Money(new BigDecimal("125000.00"))
        );

        assertThat(json).isEqualTo("\"VND 125000.00\"");
    }

    @Test
    void readsMoneyFromString() throws Exception {
        Money money = objectMapper.readValue(
            "\"VND 125000.00\"",
            Money.class
        );

        assertThat(money.amount())
            .isEqualByComparingTo("125000.00");
    }
}
~~~

This example uses AssertJ in a Spring Boot test. For integration testing, call endpoints using MockMvc or WebTestClient to confirm HTTP message converters use the Spring-managed mapper.

Next, download the OpenAPI specification:

~~~bash
curl -s http://localhost:8080/v3/api-docs
~~~

Verify:

- The <code>total</code> property has <code>type: string</code>, not object.
- Pattern and example match the serializer/deserializer.
- Both request and response schemas are accurate.
- No leftover <code>Money</code> component describes an object with <code>amount</code> if the actual wire format is a string.
- Swagger UI displays properly formatted request examples.

Also test invalid inputs such as strings missing the <code>VND </code> prefix, non-string values, negative numbers, and non-numeric strings. Confirm the server returns errors matching API conventions.

## 11. Common Pitfalls

**Serializer turns object into string yet schema remains object.** Add <code>@Schema(implementation = String.class)</code>, <code>type = "string"</code>, or a corresponding component schema; then check the OpenAPI JSON.

**Writing only a serializer and forgetting the deserializer.** Responses may work while requests fail to parse that format. If the API accepts this type from clients, implement a matching deserializer or creator.

**Writing only a deserializer without documenting the format in the schema.** Clients do not know whether to send a string, object, or specific token. Add type, pattern, format, and examples.

**Using a manually created ObjectMapper in services.** A standalone mapper may miss Spring Boot modules and settings. Prefer the Spring-managed mapper or register modules via beans.

**Registering competing serializers.** Type-level annotations, field-level annotations, and modules may all apply at once. Inspect the actual mapper and retain a single clear strategy.

**Relying on @Schema to alter runtime JSON.** OpenAPI annotations describe documentation only; use Jackson or application logic to change serialization.

**Relying on serializers to update OpenAPI automatically.** springdoc does not run serializers over payloads to infer schemas. Add explicit schemas whenever wire formats differ from Java types.

**Skipping tests for null and malformed inputs.** Custom serializers/deserializers must behave predictably for invalid tokens, null, out-of-range values, and parse errors.

## 12. Pre-Publication Review Checklist

- [ ] Defined JSON wire format before and after serializer/deserializer execution.
- [ ] Serializer emits the right JSON type: string, number, object, array, or null.
- [ ] Deserializer reads valid tokens and rejects invalid formats.
- [ ] Selected the right scope: type-level annotation, property annotation, or Jackson Module.
- [ ] Spring Boot uses the intended ObjectMapper and registered modules.
- [ ] OpenAPI schema describes the actual JSON type rather than merely mirroring the Java type.
- [ ] Pattern, format, example, and bounds align with runtime rules.
- [ ] Requests and responses are tested independently.
- [ ] Verified <code>/v3/api-docs</code>, Swagger UI, and real HTTP endpoints.

## References

- [Jackson – Custom Serializers and Deserializers](https://github.com/FasterXML/jackson-databind): serializer/deserializer APIs and data binding.
- [Jackson Annotations – JsonSerialize](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/annotation/JsonSerialize.html): selecting a custom serializer.
- [Jackson Annotations – JsonDeserialize](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/annotation/JsonDeserialize.html): selecting a custom deserializer.
- [Spring Boot – Customize the Jackson ObjectMapper](https://docs.spring.io/spring-boot/reference/features/json.html): Jackson configuration, module beans, and <code>@JsonComponent</code>.
- [Swagger Core – Schema annotation](https://docs.swagger.io/swagger-core/v2.2.0/apidocs/io/swagger/v3/oas/annotations/media/Schema.html): adding type, implementation, pattern, and example to schemas.
- [springdoc-openapi](https://springdoc.org/): generating and customizing OpenAPI from Spring Boot applications.
