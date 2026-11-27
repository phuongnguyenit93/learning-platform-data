# Custom Serializers, Deserializers, and Jackson Modules

## 1. When Do You Need Custom JSON Handling?

In the **SPRING_BOOT_NATIVE_IMAGE** module, Spring Boot is processed with **Spring AOT** and compiled into a GraalVM Native Image to evaluate startup time, memory usage, and compatibility. JSON is a critical application boundary: requests from clients are converted into Java objects, and responses are converted back into JSON.

By default, Jackson handles most JavaBeans, records, collections, and common data types well. However, external JSON formats sometimes differ from internal Java structures. For example:

- An API expects currency as an object with two fields `amount` and `currency`, while the code uses a `Money` value object.
- A legacy API sends dates and times as custom strings rather than ISO-8601.
- A field accepts multiple JSON shapes, yet the application wants to normalize them into a single Java type.
- A domain type needs a stable JSON contract independent of internal field names.

In those cases, you can write a **custom serializer** to control how a Java object becomes JSON, a **custom deserializer** to validate and convert JSON into a Java object, and bundle both components into a **Jackson module** for reuse.

With Native Image, you also need to check Jackson's dynamic access requirements. Custom code invoking constructors/getters directly may not need reflection for those direct calls, but DTOs introspected by Jackson still require metadata so GraalVM retains constructors, fields, accessors, or nested types.

## 2. Serialization and Deserialization Flows

The two flows run in opposite directions:

~~~mermaid
flowchart LR
    A["Java object"] --> S["JsonSerializer"]
    S --> G["JsonGenerator"]
    G --> J["JSON output"]
    I["JSON input"] --> P["JsonParser"]
    P --> D["JsonDeserializer"]
    D --> O["Java object"]
~~~

| Component | Role |
| --- | --- |
| `JsonSerializer<T>` | Converts an object of type `T` into JSON tokens |
| `JsonDeserializer<T>` | Reads JSON tokens and constructs an object of type `T` |
| `JsonGenerator` | Writes objects, arrays, strings, numbers, booleans, and null |
| `JsonParser` | Reads tokens from JSON input |
| `SerializerProvider` | Supplies serializers and context for writing |
| `DeserializationContext` | Supplies context, configuration, and utilities for reading |
| `Module` | Groups Jackson serializers, deserializers, mix-ins, and extensions |

Serializers and deserializers should focus on **a type's JSON contract**. Business logic such as database calls, authorization checks, HTTP calls, or transaction creation does not belong in these classes.

## 3. Domain Example: Money

Suppose a billing system uses a value object:

~~~java
package com.example.billing;

import java.math.BigDecimal;
import java.util.Objects;

public record Money(BigDecimal amount, String currency) {
    public Money {
        Objects.requireNonNull(amount, "amount is required");
        Objects.requireNonNull(currency, "currency is required");
        if (!currency.matches("[A-Z]{3}")) {
            throw new IllegalArgumentException(
                "currency must be a three-letter uppercase code"
            );
        }
    }
}
~~~

JSON format published by the API:

~~~json
{
  "amount": 125000.50,
  "currency": "VND"
}
~~~

The application wants to write `amount` as a JSON number, write `currency` as a string, preserve `BigDecimal` precision, and reject missing or mistyped data. The example uses a record for illustration; a JavaBean can preserve the exact same JSON contract and substitute appropriate constructor/setter instantiation.

## 4. Writing a Custom Serializer

Jackson provides `JsonSerializer<T>`. For typical serializers, you can extend `StdSerializer<T>`:

~~~java
package com.example.billing.json;

import java.io.IOException;
import com.example.billing.Money;
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
        generator.writeNumberField("amount", value.amount());
        generator.writeStringField("currency", value.currency());
        generator.writeEndObject();
    }
}
~~~

`writeStartObject()` opens the JSON object; `writeNumberField()` writes the number; `writeStringField()` writes the currency code; `writeEndObject()` closes the object. Use `JsonGenerator` instead of manual JSON string concatenation so Jackson handles escaping, encoding, and JSON structure accurately.

Custom serializers are useful when the JSON contract differs from an object's field layout, formats need normalization, a value object maps to a scalar/object/array, or only publicly allowed fields should be emitted. If you only need to rename fields, omit fields, or format dates using standard settings, consider annotations or built-in modules before writing a new serializer.

## 5. Writing a Custom Deserializer

A deserializer extends `StdDeserializer<T>`. It reads JSON input, validates structure and data types, and constructs the object:

~~~java
package com.example.billing.json;

import java.io.IOException;
import com.example.billing.Money;
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
        if (!node.isObject()) {
            throw JsonMappingException.from(
                parser, "Money must be represented as a JSON object"
            );
        }

        JsonNode amountNode = node.get("amount");
        JsonNode currencyNode = node.get("currency");
        if (amountNode == null || !amountNode.isNumber()) {
            throw JsonMappingException.from(
                parser, "Money.amount must be a JSON number"
            );
        }
        if (currencyNode == null || !currencyNode.isTextual()) {
            throw JsonMappingException.from(
                parser, "Money.currency must be a JSON string"
            );
        }

        try {
            return new Money(
                amountNode.decimalValue(),
                currencyNode.textValue()
            );
        }
        catch (IllegalArgumentException ex) {
            throw JsonMappingException.from(
                parser, "Money contains an invalid value"
            );
        }
    }
}
~~~

The deserializer verifies that the root is an object, `amount` is a JSON number, and `currency` is a JSON string, then lets the domain constructor enforce invariants. Do not return an invalid object and let errors surface later in services or the database. Also avoid putting sensitive payloads into exception messages.

### 5.1. Nulls, Missing Fields, and Invalid Fields

Jackson handles JSON `null` through a dedicated null-value mechanism; `deserialize()` is not always invoked for a `null` token. If the API contract needs special null handling, consider overriding `getNullValue(DeserializationContext)` and configuring null handling accordingly.

| Input | Meaning | Recommended Handling |
| --- | --- | --- |
| `{"amount":10,"currency":"USD"}` | Valid data | Instantiate `Money` |
| `{"amount":10}` | Missing required field | Throw mapping error |
| `{"amount":"10","currency":"USD"}` | Wrong JSON type per contract | Throw error or accept strings if explicitly defined by the API |
| `null` | JSON null | Handle per API null policy |
| `{}` | Empty object | Report missing required data |

If the API must accept multiple formats, document precedence and conversion rules clearly. Avoid silently coercing every value between strings and numbers, as that can mask invalid client payloads.

## 6. Bundling Serializers and Deserializers into a Jackson Module

A module groups handlers for a set of data types. With Jackson 2, you can use `SimpleModule`:

~~~java
package com.example.billing.json;

import com.example.billing.Money;
import com.fasterxml.jackson.databind.module.SimpleModule;

public final class MoneyJacksonModule extends SimpleModule {
    public MoneyJacksonModule() {
        super("money-module");
        addSerializer(Money.class, new MoneySerializer());
        addDeserializer(Money.class, new MoneyDeserializer());
    }
}
~~~

Give the module an explicit name so it is easy to identify in configuration and logs. You can register handlers for multiple value objects when they belong to the same JSON contract.

### 6.1. Registering the Module with Spring Boot

In Spring Boot 3 using Jackson 2, a common approach is declaring the module as a Spring bean:

~~~java
package com.example.billing.config;

import com.example.billing.json.MoneyJacksonModule;
import com.fasterxml.jackson.databind.Module;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class JacksonConfiguration {
    @Bean
    Module moneyJacksonModule() {
        return new MoneyJacksonModule();
    }
}
~~~

Spring Boot automatically registers `Module` beans with the auto-configured `ObjectMapper`. Controllers using HTTP JSON, `@RequestBody`, `@ResponseBody`, and components using the Spring-managed mapper can use this module.

**Do not create a new `ObjectMapper` solely to register a module.** Declaring a custom mapper manually can accidentally discard Spring Boot's default settings, Java Time module, naming strategy, date format, or other customizers. If a project has a custom mapper, check where it is constructed and whether the module is registered on the exact mapper used by HTTP converters.

### 6.2. Other Registration Approaches

| Approach | Scope | When to Use |
| --- | --- | --- |
| Spring bean of type `Module` | Mapper managed by Spring Boot | Shared module for a domain type family |
| `@JsonComponent` | Serializer/deserializer discovered by Spring Boot | Small handlers tied to component scanning |
| `@JsonSerialize` / `@JsonDeserialize` | Annotated type or property | Only one type or property needs a handler |
| `Jackson2ObjectMapperBuilderCustomizer` | Jackson 2 builder | Need to customize the builder or module installation |
| Custom `ObjectMapper` | A separate mapper | Only when an independent mapper is genuinely needed |

Do not register the same serializer multiple times across a module bean, `@JsonComponent`, and annotations unintentionally. Multiple handlers applying to the same type can make behavior depend on registration order or complicate debugging.

### 6.3. Using `@JsonComponent`

Spring Boot supports `@JsonComponent` for automatic discovery of serializers/deserializers. Compact example:

~~~java
@JsonComponent
public class MoneyJsonComponent {

    public static class Serializer extends JsonSerializer<Money> {
        @Override
        public void serialize(
                Money value,
                JsonGenerator generator,
                SerializerProvider provider) throws IOException {
            generator.writeStartObject();
            generator.writeNumberField("amount", value.amount());
            generator.writeStringField("currency", value.currency());
            generator.writeEndObject();
        }
    }

    public static class Deserializer extends JsonDeserializer<Money> {
        @Override
        public Money deserialize(
                JsonParser parser,
                DeserializationContext context) throws IOException {
            // Read and validate JSON according to the same Money contract.
            // Logic from MoneyDeserializer can be reused.
            JsonNode node = parser.getCodec().readTree(parser);
            if (!node.isObject()
                    || node.get("amount") == null
                    || !node.get("amount").isNumber()
                    || node.get("currency") == null
                    || !node.get("currency").isTextual()) {
                throw JsonMappingException.from(parser, "Invalid Money JSON");
            }
            return new Money(
                node.get("amount").decimalValue(),
                node.get("currency").textValue()
            );
        }
    }
}
~~~

This is an alternative to `SimpleModule` in a Spring Boot application. Do not keep both the module bean example and `@JsonComponent` for the same `Money` type simultaneously; pick one registration mechanism.

### 6.4. Annotations on Types or Properties

If a serializer applies only to one property, you can annotate it:

~~~java
public record InvoiceResponse(
    @JsonSerialize(using = MoneySerializer.class)
    @JsonDeserialize(using = MoneyDeserializer.class)
    Money total
) {
}
~~~

This makes the property's contract explicit, though Jackson must be able to instantiate and access the serializer class properly. If the same `Money` type always shares one JSON representation across the application, a module bean is usually easier to manage.

## 7. Modules and Jackson in Spring Boot Native Image

### 7.1. Why Does Jackson Need Metadata?

Jackson often introspects Java types to find constructors/factory methods, record components, getters/setters/fields, annotations, nested types, generic types, and polymorphic subtypes. On the JVM, reflection can inspect much of this information at runtime. Native Image needs to know ahead of time which members and types must be retained. If a DTO is discovered by Jackson solely via reflection without metadata, requests or responses can fail in the native executable even when the JAR works.

### 7.2. Spring AOT and Binding Types

Spring Framework provides `@RegisterReflectionForBinding` to register types requiring reflection for data binding. For example:

~~~java
package com.example.billing.config;

import com.example.billing.api.CreateInvoiceRequest;
import com.example.billing.api.InvoiceResponse;
import org.springframework.aot.hint.annotation.RegisterReflectionForBinding;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@RegisterReflectionForBinding({
    CreateInvoiceRequest.class,
    InvoiceResponse.class
})
class JsonNativeHints {
}
~~~

Register DTOs actually bound by Jackson in requests and responses. If they contain nested types requiring introspection, inspect generated metadata and add necessary types based on real native errors. Do not register every model in the application just to avoid errors.

### 7.3. Do Custom Handlers Need Reflection Hints?

That depends on how the handler is instantiated and what it does:

- If Spring constructs `MoneyJacksonModule` via a bean method and the module calls `new MoneySerializer()`/`new MoneyDeserializer()`, those constructor calls are direct calls in bytecode.
- If the serializer calls `value.amount()` directly and the deserializer calls `new Money(...)`, those invocations are also statically represented in code.
- If Jackson must introspect `CreateInvoiceRequest`, `InvoiceResponse`, or other DTOs, those binding types may still need reflection hints.
- If a handler is instantiated via annotations, classpath scanning, or `ServiceLoader`, verify discovery and matching metadata in the native executable.

Therefore, **do not automatically add reflection hints for every serializer class**. Identify whether the failure lies in handler instantiation or DTO introspection, then register the exact missing types or members.

### 7.4. Explicit Module Registration

In a Spring Boot application, declaring the module as a bean makes registration explicit:

~~~java
@Bean
Module moneyJacksonModule() {
    return new MoneyJacksonModule();
}
~~~

If using `ObjectMapper.findAndRegisterModules()`, Jackson may rely on `ServiceLoader` to locate modules. For native images, verify metadata and provider resources so service discovery works. Avoid auto-discovery mechanisms if a Spring bean or explicit configuration already meets your needs.

## 8. Jackson 2 and Jackson 3: Do Not Mix APIs

The `SimpleModule`, `JsonSerializer`, and `JsonDeserializer` examples in this lesson use **Jackson 2** with `com.fasterxml.jackson.*` packages, common in Spring Boot 3 applications.

Spring Boot 4 moves to the **Jackson 3** ecosystem as the default choice. Jackson 3 changes packages/APIs to the `tools.jackson.*` namespace along with corresponding Spring Boot integration. Therefore:

- Do not include both Jackson 2 and Jackson 3 dependencies simultaneously just to copy snippets from two different guides.
- Choose the Jackson major version matching your Spring Boot version.
- Use serializer, deserializer, and module APIs from the same major version as `ObjectMapper` and HTTP message converters.
- Verify package imports, module registration, and tests when upgrading Spring Boot.

The design concepts remain identical: serializers emit JSON tokens, deserializers read and validate JSON, modules group handlers, and Spring Boot registers modules on the managed mapper. **Exact package names and APIs must match the version.**

## 9. Testing Serializers and Deserializers

Custom JSON handlers need tests for both writing and reading. Test example with Jackson 2:

~~~java
class MoneyJacksonModuleTests {

    private final ObjectMapper mapper = JsonMapper.builder()
        .addModule(new MoneyJacksonModule())
        .build();

    @Test
    void serializesMoneyAsAmountAndCurrency() throws Exception {
        Money money = new Money(
            new BigDecimal("125000.50"),
            "VND"
        );
        String json = mapper.writeValueAsString(money);
        assertThat(json)
            .isEqualTo("{\"amount\":125000.50,\"currency\":\"VND\"}");
    }

    @Test
    void deserializesMoney() throws Exception {
        Money money = mapper.readValue(
            "{\"amount\":125000.50,\"currency\":\"VND\"}",
            Money.class
        );
        assertThat(money.amount()).isEqualByComparingTo("125000.50");
        assertThat(money.currency()).isEqualTo("VND");
    }
}
~~~

Tests should also cover negative/positive amounts, integers/decimals, missing/blank/malformed currencies, non-object JSON roots, `amount` as string/null/object, unknown fields, JSON `null`, and `BigDecimal` precision.

### 9.1. Verifying the Module Is Registered by Spring Boot

Beyond unit tests creating a mapper manually, write integration tests using the Spring-managed mapper:

~~~java
@SpringBootTest
class MoneyJacksonIntegrationTests {

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void springManagedMapperUsesMoneyModule() throws Exception {
        Money value = new Money(new BigDecimal("10.25"), "USD");
        String json = objectMapper.writeValueAsString(value);
        assertThat(json)
            .isEqualTo("{\"amount\":10.25,\"currency\":\"USD\"}");
    }
}
~~~

This test verifies that the module bean is actually wired into the mapper managed by Spring Boot. If unit tests pass yet the integration test fails, check component scanning, bean registration, custom mappers, and HTTP converter configuration.

### 9.2. Testing HTTP Endpoints

If the custom module is used for a REST API, test both requests and responses:

~~~java
mockMvc.perform(post("/invoices")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
            {
              "total": {
                "amount": 125000.50,
                "currency": "VND"
              }
            }
            """))
    .andExpect(status().isCreated());
~~~

Also verify that the response returns the expected JSON contract, not merely the status code. An isolated mapper test does not prove that the message converter uses the same mapper in the application.

## 10. Testing on Native Image

A custom module working on the JVM is not guaranteed to work in the native executable. Native Image may lack metadata for DTOs or discovery paths used by Jackson.

Recommended sequence:

1. Run serializer/deserializer unit tests on the JVM.
2. Run integration tests with the Spring Boot-managed mapper.
3. Build the native executable with Maven/Gradle using Spring AOT.
4. Run native tests or the executable and send real JSON requests.
5. Test both valid and invalid JSON, especially nested types.

With Gradle and Native Build Tools, a project may configure a `nativeTest` task; with Maven, it may configure a corresponding native test execution. Exact task/goal names and plugin versions depend on the build system, so inspect your project's actual configuration.

### 10.1. Common Native Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| JVM serializes, native cannot find serializer | Module not registered on native mapper or discovery failed | Use a module bean/explicit registration; inspect the real mapper |
| Deserialization reports it cannot instantiate DTO | Missing constructor/field/accessor metadata for DTO | Register binding type via `@RegisterReflectionForBinding` or exact hints |
| Custom handler is never called | Module missed the active mapper, type registration mismatched, or another mapper was used | Check `Module` bean, HTTP converters, and mapper instance |
| Record/constructor binding fails on native | Native Image lacks constructor/introspection metadata | Check hints for records/DTOs and nested types |
| Fails only on endpoint, unit test passes | HTTP converter uses a different mapper or endpoint DTO is unregistered | Test request/response through Spring context and native executable |
| Wrong JSON type gets accepted | Deserializer coerces values too loosely | Check token types, validate input, and test boundary data |
| Module registered twice | Combined multiple mechanisms like bean, `@JsonComponent`, and annotations | Pick one primary mechanism per type/mapper |

## 11. Design Considerations

### 11.1. Keep the JSON Contract Stable

Do not serialize an entire internal object directly if the API only needs a subset of fields. A custom serializer should explicitly publish which fields appear and their JSON types. Renaming a field or changing a number to a string must be treated as an API contract change.

### 11.2. Do Not Lose Numeric Precision

For money and decimals, use `BigDecimal` and `JsonGenerator.writeNumber(...)`. Do not convert through `double` or `float` for convenience. Rounding rules belong in the business domain or service layer, not hidden inside a serializer.

### 11.3. Handling Untrusted Input

A deserializer is a boundary receiving client input. Validate token types and value bounds; avoid allocating huge objects from unbounded arrays or strings; never enable broad polymorphic default typing for untrusted input; use a subtype allowlist if JSON represents multiple subtypes; and avoid logging full payloads when they may contain personal data or secrets.

### 11.4. Do Not Put Business Logic in Serializers

Serializers and deserializers should perform pure data conversion. Do not access databases, make HTTP calls, read secret stores, or depend on request-scoped state. Doing so makes mapping hard to test, hard to reuse, and prone to unexpected failures when Jackson serializes objects for logs, caches, or message brokers.

### 11.5. Generic Types and Contextual Handlers

If a handler depends on generic types such as `Envelope<T>` or per-property annotations, the serializer/deserializer may need to implement `ContextualSerializer`/`ContextualDeserializer` to receive type and property metadata. Do not assume one shared handler works for every generic parameter if behavior depends on `T`.

For simple cases like `Money`, class-based serializers/deserializers are usually sufficient. Implement contextual handlers only when specifically required.

## 12. Practical Workflow from Module to Native Executable

Suppose a billing service receives an invoice-creation request with `Money` and returns JSON with the same structure.

**Step 1 — Define the JSON contract**

- Write examples of valid and invalid JSON.
- Finalize data types for `amount`, `currency`, and the policy for nulls/missing fields.
- Decide whether the serializer applies to the whole type or a single property.

**Step 2 — Implement handlers**

- Write `MoneySerializer` and `MoneyDeserializer`.
- Keep conversion pure, with no service or database calls.
- Test `BigDecimal`, currency codes, and mapping errors.

**Step 3 — Register the module**

- For Spring Boot 3 / Jackson 2, create a `Module` bean returning `MoneyJacksonModule`.
- Choose `@JsonComponent` or property-level annotations if a narrower scope fits better.
- Avoid registering the same handler via multiple mechanisms.

**Step 4 — Test on the JVM**

- Test direct serialization/deserialization.
- Test the Spring-managed mapper.
- Test HTTP requests and responses.

**Step 5 — Prepare native metadata**

- Identify DTOs introspected by Jackson.
- Inspect metadata generated by Spring AOT and native support.
- Use `@RegisterReflectionForBinding` or exact hints if native runtime reports missing types or members.
- Verify the module is explicitly registered on the mapper.

**Step 6 — Build and run native**

Build with Maven or Gradle per project configuration. Call the real endpoints, verify well-formed JSON and invalid input errors. After changing a serializer, module, or hints, rebuild the native executable to test the new output.

**Step 7 — Record results**

- Save the JSON contract and test cases.
- Record Spring Boot, Jackson, and GraalVM versions.
- Record JVM and native test statuses.
- Measure build time, startup time, and RSS if performance comparison is needed.

## 13. Pre-Completion Checklist

- [ ] The data type's JSON contract is clearly documented.
- [ ] Serializer uses `JsonGenerator`, not manual JSON string concatenation.
- [ ] Deserializer validates root, token types, required fields, and domain values.
- [ ] Policies for null, missing fields, and unknown fields are defined.
- [ ] The module is registered on the mapper actually used by Spring Boot.
- [ ] The same handler is not unintentionally registered via multiple mechanisms.
- [ ] Jackson major version matches Spring Boot and dependencies.
- [ ] DTOs introspected by Jackson have appropriate metadata for native.
- [ ] Unit, Spring integration, HTTP request/response, and native runtime tests have passed.
- [ ] `BigDecimal` precision is preserved and sensitive payloads are not logged.

**Remember:** a custom serializer defines how a Java object is written as JSON; a custom deserializer validates JSON and constructs an object; a Jackson module bundles handlers for consistent registration. In Spring Boot Native Image, verify both mapper registration and reflection metadata for DTOs introspected by Jackson. JVM testing is the first step, while the native executable must be verified with real requests and responses.

## References

- [Jackson Databind — Custom Serializers and Deserializers](https://github.com/FasterXML/jackson-databind): `JsonSerializer`, `JsonDeserializer`, `SimpleModule`, and databinding APIs.
- [Spring Boot Reference — Jackson](https://docs.spring.io/spring-boot/reference/features/json.html): JSON configuration, module beans, and Jackson integration with Spring Boot.
- [Spring Framework — Runtime Hints](https://docs.spring.io/spring-framework/reference/core/aot.html): Spring AOT, runtime hints, and reflection registration for native apps.
- [GraalVM Native Image — Reachability Metadata](https://www.graalvm.org/latest/reference-manual/native-image/metadata/): metadata required for reflection, resources, proxies, and serialization.
