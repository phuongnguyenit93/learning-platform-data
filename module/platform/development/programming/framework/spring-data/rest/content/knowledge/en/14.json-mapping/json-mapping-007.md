# Registering Custom Jackson Modules, Serializers, and Deserializers in Spring Data REST

## Objectives

After this lesson, you will be able to:

- Explain what a Jackson Module is used for and when to create a dedicated module.
- Write a serializer to convert a Java type into JSON according to an API contract.
- Write a deserializer to convert a JSON request into the corresponding Java type.
- Register both on the ObjectMapper used by Spring Data REST.
- Verify results on repository endpoints while avoiding losing built-in Jackson and HAL configurations.

## 1. How Does Jackson Participate in Spring Data REST?

Spring Data REST publishes repositories as HTTP resources. When clients send requests or receive responses, the framework needs to convert between Java objects and JSON:

- **Serialization:** Java object → JSON response. Jackson invokes a serializer to write values as JSON.
- **Deserialization:** JSON request → Java object. Jackson invokes a deserializer to read data and construct Java values.

For example, an entity has a property of type Money. A default contract might represent Money as an object containing amount and currency. If the API needs a specific format, such as always writing amount as a number and currency as a currency code, we can define a serializer/deserializer for Money.

A Jackson Module is a unit for registering Jackson extension components, such as serializers, deserializers, key serializers, mix-in annotations, or type configurations. SimpleModule is a convenient choice when you need to register a few serializers and deserializers by Java type.

General processing flow:

1. The client sends JSON to a Spring Data REST endpoint.
2. Spring Data REST uses the ObjectMapper configured for REST to deserialize the request body.
3. Jackson looks up the deserializer matching the property type and converts JSON to a Java value.
4. The repository processes the entity per business logic.
5. When building the response, Jackson looks up the matching serializer and writes the Java value to JSON.
6. Spring Data REST adds resource structure and HAL links according to application configuration.

Custom serializers/deserializers only determine how the types they are registered for are represented. They do not replace repositories, persist entities on their own, or alter Spring Data REST HTTP rules.

## 2. Choosing the Right Customization Scope

There are two common ways to attach serializers/deserializers:

| Approach | Scope | When to Use |
|---|---|---|
| Jackson Module registered by Java type | Every property of the registered type in that ObjectMapper | A data type needs the same JSON contract across multiple entities or endpoints |
| @JsonSerialize and @JsonDeserialize | A specific annotated class or property | Only one property needs a special representation |

For instance, if every Money property in the REST API needs the same format, registering via a module centralizes configuration. If only one field needs a different format, property-level annotations express intent more clearly.

Pay attention to ObjectMapper scope. A module registered on Spring Data REST's mapper affects endpoints using that mapper. If the application has multiple ObjectMappers for different purposes, do not assume the module automatically appears in all mappers.

## 3. Building an Example Data Type

Suppose the API manages Person and the entity has a salary property of type Money. We want Money's JSON to look like:

    {
      "amount": 1250.50,
      "currency": "USD"
    }

Illustrative Java type:

    import java.math.BigDecimal;

    public class Money {
        private final BigDecimal amount;
        private final String currency;

        public Money(BigDecimal amount, String currency) {
            if (amount == null) {
                throw new IllegalArgumentException("amount is required");
            }
            if (currency == null || currency.isBlank()) {
                throw new IllegalArgumentException("currency is required");
            }
            this.amount = amount;
            this.currency = currency;
        }

        public BigDecimal getAmount() {
            return amount;
        }

        public String getCurrency() {
            return currency;
        }
    }

This example keeps amount as BigDecimal to avoid binary floating-point errors common when using double for monetary values. In a real application, currency can be replaced with java.util.Currency or an enum validated by business rules.

## 4. Writing a Serializer

A serializer extends StdSerializer and implements the serialize method. The method receives the Java value, JsonGenerator, and SerializerProvider.

    import java.io.IOException;

    import com.fasterxml.jackson.core.JsonGenerator;
    import com.fasterxml.jackson.databind.SerializerProvider;
    import com.fasterxml.jackson.databind.ser.std.StdSerializer;

    public final class MoneySerializer extends StdSerializer<Money> {

        public MoneySerializer() {
            super(Money.class);
        }

        @Override
        public void serialize(
                Money value,
                JsonGenerator generator,
                SerializerProvider provider) throws IOException {

            generator.writeStartObject();
            generator.writeNumberField("amount", value.getAmount());
            generator.writeStringField("currency", value.getCurrency());
            generator.writeEndObject();
        }
    }

Key calls:

- writeStartObject() begins a JSON object.
- writeNumberField() writes a numeric field.
- writeStringField() writes a string field.
- writeEndObject() ends the object.

For Money with amount 1250.50 and currency USD, the serializer generates a JSON object with those two fields. Field ordering in JSON should not be relied upon as a business condition by clients; the contract lies in field names and data types.

Serializers must handle null values appropriately according to the contract. Jackson normally has its own null serializer mechanism; avoid manually writing the string `"null"` if the API expects a true JSON null.

## 5. Writing a Deserializer

A deserializer extends StdDeserializer and implements the deserialize method. The method reads JSON tokens, validates structure, and constructs the Java object.

    import java.io.IOException;

    import com.fasterxml.jackson.core.JsonParser;
    import com.fasterxml.jackson.databind.DeserializationContext;
    import com.fasterxml.jackson.databind.JsonMappingException;
    import com.fasterxml.jackson.databind.JsonNode;
    import com.fasterxml.jackson.databind.deser.std.StdDeserializer;

    public final class MoneyDeserializer extends StdDeserializer<Money> {

        public MoneyDeserializer() {
            super(Money.class);
        }

        @Override
        public Money deserialize(
                JsonParser parser,
                DeserializationContext context) throws IOException {

            JsonNode node = parser.getCodec().readTree(parser);

            if (node == null || !node.isObject()) {
                throw JsonMappingException.from(
                    parser, "Money must be a JSON object");
            }

            JsonNode amount = node.get("amount");
            JsonNode currency = node.get("currency");

            if (amount == null || !amount.isNumber()
                    || currency == null || !currency.isTextual()) {
                throw JsonMappingException.from(
                    parser,
                    "Money requires numeric amount and string currency");
            }

            try {
                return new Money(
                    amount.decimalValue(),
                    currency.asText());
            } catch (IllegalArgumentException ex) {
                throw JsonMappingException.from(
                    parser, "Invalid Money value", ex);
            }
        }
    }

The logic above follows these steps:

1. Use parser.getCodec().readTree(parser) to read JSON into a JsonNode tree.
2. Verify the node is an object.
3. Extract amount and currency by field name.
4. Check that amount is numeric and currency is a string.
5. Construct Money from BigDecimal and currency.
6. Report a mapping error if the JSON violates the contract or has invalid values.

Do not silently replace invalid input with amount 0 or a default currency. That turns an invalid request into seemingly valid data and can cause hard-to-trace business bugs. Return a clear deserialization error so clients can fix the request.

If the contract needs to allow optional fields, explicitly define behavior for absent fields, null values, and wrong-type values. Do not treat these three cases as identical.

## 6. Packaging Serializer and Deserializer in a SimpleModule

SimpleModule lets you register both components for the same Java type:

    import com.fasterxml.jackson.databind.module.SimpleModule;

    public final class MoneyModule extends SimpleModule {

        public MoneyModule() {
            super("money-module");
            addSerializer(Money.class, new MoneySerializer());
            addDeserializer(Money.class, new MoneyDeserializer());
        }
    }

After creating the module, we need to register it on the ObjectMapper used by Spring Data REST.

## 7. Registering the Module with Spring Data REST

A clear way to customize Spring Data REST's ObjectMapper is to implement RepositoryRestConfigurer and override configureJacksonObjectMapper.

    import com.fasterxml.jackson.databind.ObjectMapper;
    import org.springframework.context.annotation.Configuration;
    import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;

    @Configuration
    public class RepositoryRestJacksonConfiguration
            implements RepositoryRestConfigurer {

        @Override
        public void configureJacksonObjectMapper(
                ObjectMapper objectMapper) {

            objectMapper.registerModule(new MoneyModule());
        }
    }

Spring Data REST invokes this callback when configuring the mapper serving REST resources. We register the module on the passed-in mapper, allowing the custom serializer/deserializer to participate in Spring Data REST request and response conversion.

Principles to follow:

- Register the module on the framework-provided ObjectMapper.
- Do not create a new ObjectMapper with new ObjectMapper() and expect Spring Data REST to automatically use it.
- Do not replace the existing mapper when you only need to add a data type.
- Do not remove Jackson modules or settings already registered by Spring Boot and Spring Data REST.
- Place the configuration in a Spring-managed configuration class so the callback is discovered.
- If there are multiple RepositoryRestConfigurers, organize configurations clearly and check ordering when one configuration depends on another.

Using a dedicated SimpleModule groups related serializers/deserializers, making code easy to read and test. When you have multiple data types, you can add multiple addSerializer/addDeserializer pairs to one module or split modules by business domain.

## 8. When to Use Annotations Instead of a Module?

If only a single property needs special formatting, you can attach annotations directly:

    import com.fasterxml.jackson.databind.annotation.JsonDeserialize;
    import com.fasterxml.jackson.databind.annotation.JsonSerialize;

    public class Person {

        @JsonSerialize(using = MoneySerializer.class)
        @JsonDeserialize(using = MoneyDeserializer.class)
        private Money salary;

        public Money getSalary() {
            return salary;
        }

        public void setSalary(Money salary) {
            this.salary = salary;
        }
    }

This explicitly shows which serializer/deserializer is used for the salary property. Choose one registration approach matching your contract to avoid confusing redundant configuration. If both a module and property annotations are registered for the same property, verify the effective mapper and test output rather than assuming which configuration takes effect.

## 9. Testing Serializers and Deserializers

Test the two layers separately first, then run integration tests against Spring Data REST endpoints.

### Testing Serialization

Create a Money with amount 1250.50 and currency USD, serialize it, and verify the JSON has:
- amount as a JSON number.
- currency as a JSON string.
- Field names matching the contract.
- No unexposed internal fields.

### Testing Deserialization

Feed a JSON object with amount and currency into the mapper, then confirm:
- The result is a Money instance.
- BigDecimal retains the exact value and required scale.
- Currency retains the right code.
- JSON missing fields or having wrong types is rejected.
- Invalid values produce a clear mapping error.

### Testing Spring Data REST Endpoints

Use integration tests or MockMvc to verify actual repository endpoints:

- GET an item or collection containing a Money property: the response uses the custom serializer.
- POST an item with Money: the request body is processed by the custom deserializer.
- PUT/PATCH an item: verify the deserializer on submitted fields.
- Verify _links and HAL metadata still appear normally.
- Verify status codes and response bodies match the endpoint contract.

Example item creation request:

    POST /people
    Content-Type: application/json
    Accept: application/hal+json

    {
      "firstName": "An",
      "salary": {
        "amount": 1250.50,
        "currency": "USD"
      }
    }

An illustrative response may contain:

    {
      "firstName": "An",
      "salary": {
        "amount": 1250.50,
        "currency": "USD"
      },
      "_links": {
        "self": {
          "href": "http://localhost:8080/people/42"
        }
      }
    }

This structure is illustrative; actual collection names, properties, IDs, and links depend on the application's repositories and configuration.

## 10. Common Errors

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Serializer is not invoked | Module is not registered on the mapper the endpoint uses; Java type mismatch | Check the RepositoryRestConfigurer callback and actual property type |
| Deserializer is not invoked | Request lacks that property, endpoint uses a different type, or another annotation/configuration applies | Inspect request body, entity mapping, and mapper |
| GET works, but POST fails | Serializer works, but deserializer does not properly handle input JSON | Test both conversion directions separately |
| Wrongly typed JSON is still accepted | Deserializer lacks node validation or falls back to default values | Validate object, fields, types, and domain rules |
| Other APIs change format | Module was registered on an ObjectMapper shared across multiple APIs | Identify the mapper and registration scope; limit custom types |
| HAL links or metadata disappear | Replaced the mapper or overwrote existing REST configuration | Add the module to the passed-in mapper; do not replace the mapper entirely |
| A property produces unexpected output compared to the module | Property has custom annotations or different Jackson settings | Inspect annotations and effective mapper via integration tests |

## 11. Completion Checklist

- [ ] Identified the exact Java type to customize.
- [ ] Defined the JSON contract with clear field names and data types.
- [ ] Serializer writes the right JSON types without unintentionally turning numbers into strings.
- [ ] Deserializer validates structure and field types before creating the object.
- [ ] Invalid data errors are reported clearly without substituting default values.
- [ ] Registered SimpleModule on Spring Data REST's ObjectMapper via RepositoryRestConfigurer.
- [ ] Did not create a new mapper or remove built-in HAL modules.
- [ ] Tested serialization, deserialization, and real endpoints.
- [ ] Confirmed HAL links and other properties still work.
- [ ] Checked existing clients if the JSON contract changed.

## Conclusion

A Jackson Module packages Jackson extensions into a registerable unit. A serializer defines how a Java value is written as JSON; a deserializer defines how JSON is converted into a Java value. With Spring Data REST, register modules on the ObjectMapper passed into RepositoryRestConfigurer's configureJacksonObjectMapper callback. This preserves existing REST mappers and configurations while giving you control over the JSON contract for custom data types.

## References

- Spring Data REST — Customizing Spring Data REST: https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html
- Spring Data REST — Repository configuration: https://docs.spring.io/spring-data/rest/reference/
- Jackson Databind — SimpleModule API: https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/module/SimpleModule.html
- Jackson Databind — StdSerializer API: https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/ser/std/StdSerializer.html
- Jackson Databind — StdDeserializer API: https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/deser/std/StdDeserializer.html
