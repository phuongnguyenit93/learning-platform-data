# Custom Serializer, Deserializer, Module, and @JsonComponent

## 1. Lesson goal

In Spring Boot, Jackson usually converts Java objects to JSON and JSON to Java objects automatically. However, real-world applications have **value objects** that require custom wire formats: money needs exact representation, order codes must be JSON strings, third-party types cannot be annotated directly, and malformed input must be rejected deliberately.

This lesson belongs to the **JSON and serialization** group and dives into four core tools:

- **`JsonSerializer<T>`:** controls how Jackson writes JSON from a Java type.
- **`JsonDeserializer<T>`:** reads JSON and builds that Java type, validating token types, required fields, and values.
- **`SimpleModule`/`Module`:** registers serializers/deserializers with an `ObjectMapper`.
- **`@JsonComponent`:** Spring Boot's mechanism to auto-discover and register custom JSON components in the application.

We will also test with `@JsonTest`, `JacksonTester`, `ObjectMapper`, and `MockMvc`, while distinguishing a **plain Jackson mapper** from a **Spring Boot auto-configured mapper**.

Scope: **Spring Boot 3.3.5**, Java 17+, and Jackson 2 managed by the Spring Boot BOM. This is a specific stack for learning and reproduction; with other Boot/Jackson versions, check package/API migration guides instead of blindly swapping imports. The goal is complete code following a Gradle structure, independent tests, and well-scoped expected outcomes.

## 2. Why isn't default JSON always the right contract?

Consider a Java value object:

```java
public record Money(BigDecimal amount, String currency) {}
```

Without a custom serializer, Jackson typically serializes this record as an object with a numeric field, e.g. `{"amount":12.50,"currency":"USD"}`. However, our API specifies that `amount` must be a **JSON string**:

```json
{"amount":"12.50","currency":"USD"}
```

Reason: `BigDecimal("12.50")` expresses decimal value and scale; we do not want clients accidentally routing money through IEEE-754 doubles and altering representation. Some APIs choose integer minor units or JSON numbers for amounts, yet each choice must be established by contract and tested.

Second value object:

```java
public record OrderCode(String value) {}
```

The API only accepts a string like `"ORD-0007"`, not an object `{"value":"ORD-0007"}`. This problem fits a custom serializer and deserializer for `OrderCode`.

**Tests must protect both directions:**

```text
Java -> JsonSerializer -> JSON
Money(12.50, USD) -> {"amount":"12.50","currency":"USD"}
OrderCode(ORD-0007) -> "ORD-0007"

JSON -> JsonDeserializer -> Java
{"amount":"12.50","currency":"USD"} -> Money
"ORD-0007" -> OrderCode

Wrong type/shape/pattern -> explicit error, no invalid object created
```

Round-trip testing is necessary but **insufficient**: if the serializer and deserializer share the same mistake, a round-trip can still return the original object. Therefore, include literal JSON fixtures representing the client-server contract.

## 3. Serialization, deserialization, and registration are three separate responsibilities

| Component | What it does | Common pitfalls |
| --- | --- | --- |
| `JsonSerializer<T>` | Writes JSON tokens using `JsonGenerator` | Manually concatenating strings, losing escaping, writing wrong number/string type |
| `JsonDeserializer<T>` | Reads tokens using `JsonParser`; constructs `T` | Accepting wrong JSON shapes, skipping field type validation |
| `JsonMappingException` | Describes mapping errors | Throwing exceptions without context, making client diagnostics hard |
| `SimpleModule` | Registers multiple handlers with a mapper | Creating a module without registering it |
| `@JsonComponent` | Plugs handlers into Spring Boot's auto-registration | Component outside scan scope or wrong `ObjectMapper` used |
| `ObjectMapper` | Executes read/write at runtime | Testing `new ObjectMapper()` while HTTP converters use another mapper |
| `@JsonTest` | JSON slice test with Boot-configured mapping | Assuming it loads all controllers/DB/application |
| `MockMvc` | Tests JSON across Spring MVC's HTTP boundary | Calling Java methods directly and bypassing converters |

Two questions must not be conflated:

1. **Is the serializer written correctly?** Test the conversion logic itself, both positive and negative cases.
2. **Is the application actually using that serializer?** Test registration and the HTTP JSON boundary.

A serializer with correct logic that is not registered on the Jackson mapper is effectively "nonexistent" for endpoints.

## 4. When to use Module, @JsonComponent, or Jackson annotations?

| Need | Suitable approach |
| --- | --- |
| A value type and Spring Boot should auto-discover its handlers | `@JsonComponent` |
| A library needing multiple serializers/deserializers, usable outside Spring too | `SimpleModule` |
| Third-party type whose source cannot be edited | Module or Jackson mix-in |
| Only one property needs custom formatting | `@JsonSerialize(using=...)` / `@JsonDeserialize(using=...)` |
| Global naming, inclusion, format configuration | Boot `spring.jackson.*` or builder customizer |
| Verify registration without starting a server | `@JsonTest` |
| Verify client POST JSON and server response JSON | `@SpringBootTest` + `@AutoConfigureMockMvc` or real HTTP |

Do not register multiple competing serializers for the same Java type unless there is a clear reason and precedence is verified by tests. The example uses `@JsonComponent` and `Module` for **two distinct types** to show both mechanisms without conflict.

## 5. Sample Java 17+ project with Gradle

Complete structure:

```text
json-customization-demo/
├── settings.gradle
├── build.gradle
├── src/main/java/com/example/jsonlab/
│   ├── JsonLabApplication.java
│   ├── Money.java
│   ├── MoneyJson.java
│   ├── OrderCode.java
│   ├── OrderCodeModule.java
│   ├── Receipt.java
│   └── ReceiptController.java
└── src/test/java/com/example/jsonlab/
    ├── ReceiptJsonTest.java
    ├── OrderCodeModuleStandaloneTest.java
    └── ReceiptMvcTest.java
```

### settings.gradle

```groovy
rootProject.name = 'json-customization-demo'
```

### build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
```

`spring-boot-starter-web` brings Jackson via the Spring Boot JSON starter. `spring-boot-starter-test` provides JUnit Jupiter, AssertJ, `@JsonTest`, `JacksonTester`, Spring MVC test infrastructure, and Mockito. Jackson versions are managed by Boot's BOM.

Use the Gradle Wrapper (`./gradlew`/`gradlew.bat`) if the project includes one; otherwise, use a compatible installed `gradle`. The demo does not call any database, payment gateway, or external system.

### Application class

Create `src/main/java/com/example/jsonlab/JsonLabApplication.java`:

```java
package com.example.jsonlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JsonLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(JsonLabApplication.class, args);
    }
}
```

All classes belong to package `com.example.jsonlab`, so the root `@SpringBootApplication` class can component-scan them, including `@JsonComponent` and Jackson Module beans.

## 6. Declaring domain value objects

### 6.1. Money — BigDecimal and currency code

`src/main/java/com/example/jsonlab/Money.java`:

```java
package com.example.jsonlab;

import java.math.BigDecimal;
import java.util.Objects;

public record Money(BigDecimal amount, String currency) {

    public Money {
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(currency, "currency");

        if (!currency.matches("[A-Z]{3}")) {
            throw new IllegalArgumentException(
                    "currency must have three uppercase letters");
        }
    }
}
```

`Money` rejects nulls and malformed currency patterns even when Java code calls the constructor directly, **not** only when instantiated via JSON. This is a local invariant for the example, not full validation against the ISO 4217 list: three uppercase letters do not prove the currency is supported in production.

Do not use `new BigDecimal(12.50)` in monetary tests. `double` values can carry binary approximations; use `new BigDecimal("12.50")` to specify the exact decimal amount.

### 6.2. OrderCode — structured identifier

`src/main/java/com/example/jsonlab/OrderCode.java`:

```java
package com.example.jsonlab;

public record OrderCode(String value) {

    public OrderCode {
        if (value == null || !value.matches("ORD-[0-9]{4}")) {
            throw new IllegalArgumentException(
                    "order code must look like ORD-0007");
        }
    }
}
```

`ORD-0007` is valid; `ORD-7` or `ord-0007` is invalid per the sample contract. Using `[0-9]` instead of a regex string needing extra escaping keeps the Java example readable.

### 6.3. Receipt — composite object using both mappings

`src/main/java/com/example/jsonlab/Receipt.java`:

```java
package com.example.jsonlab;

import java.util.Objects;
import com.fasterxml.jackson.annotation.JsonPropertyOrder;

@JsonPropertyOrder({"id", "total", "code"})
public record Receipt(long id, Money total, OrderCode code) {

    public Receipt {
        if (id <= 0) {
            throw new IllegalArgumentException(
                    "receipt id must be positive");
        }
        Objects.requireNonNull(total, "total");
        Objects.requireNonNull(code, "code");
    }
}
```

We will convert a `Receipt` instance to JSON:

```json
{
  "id": 7,
  "total": {
    "amount": "12.50",
    "currency": "USD"
  },
  "code": "ORD-0007"
}
```

`@JsonPropertyOrder` makes serialized property ordering predictable when needed, though key tests should still compare **structure and values**, because JSON object property order is not normally protocol-significant.

`Receipt`'s constructor forbids null `total` or `code`; this is essential because a custom deserializer is not necessarily invoked when a JSON property is absent or null. Those invariants belong outside the serialization layer.

## 7. @JsonComponent: a serializer and deserializer pair for Money

Create `src/main/java/com/example/jsonlab/MoneyJson.java`:

```java
package com.example.jsonlab;

import java.io.IOException;
import java.math.BigDecimal;

import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.databind.DeserializationContext;
import com.fasterxml.jackson.databind.JsonDeserializer;
import com.fasterxml.jackson.databind.JsonMappingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.JsonSerializer;
import com.fasterxml.jackson.databind.SerializerProvider;

import org.springframework.boot.jackson.JsonComponent;

@JsonComponent
public class MoneyJson {

    public static class Serializer extends JsonSerializer<Money> {

        @Override
        public void serialize(
                Money value,
                JsonGenerator generator,
                SerializerProvider provider) throws IOException {

            generator.writeStartObject();
            generator.writeStringField(
                    "amount", value.amount().toPlainString());
            generator.writeStringField(
                    "currency", value.currency());
            generator.writeEndObject();
        }
    }

    public static class Deserializer extends JsonDeserializer<Money> {

        @Override
        public Money deserialize(
                JsonParser parser,
                DeserializationContext context) throws IOException {

            JsonNode node = parser.getCodec().readTree(parser);

            if (node == null || !node.isObject()) {
                throw JsonMappingException.from(
                        parser, "Money must be a JSON object");
            }

            JsonNode amountNode = node.get("amount");
            JsonNode currencyNode = node.get("currency");

            if (amountNode == null || !amountNode.isTextual()
                    || currencyNode == null
                    || !currencyNode.isTextual()) {
                throw JsonMappingException.from(
                        parser,
                        "Money amount and currency must be strings");
            }

            try {
                return new Money(
                        new BigDecimal(amountNode.textValue()),
                        currencyNode.textValue());
            } catch (IllegalArgumentException exception) {
                throw JsonMappingException.from(
                        parser,
                        "Invalid Money: " + exception.getMessage(),
                        exception);
            }
        }
    }
}
```

### Why put `@JsonComponent` on an enclosing class?

Spring Boot supports `@JsonComponent` directly on `JsonSerializer`, `JsonDeserializer`, and `KeyDeserializer` classes, **or** on an enclosing class containing **static nested** serializers/deserializers. The second style groups both directions of a wire contract in one place. `MoneyJson.Serializer` and `MoneyJson.Deserializer` are registered through Boot's `JsonComponentModule` when the component is in the Spring context.

`@JsonComponent` is a Spring Boot mechanism, **not** a built-in feature of `new ObjectMapper()`. When running plain Jackson, a module or equivalent registration is required.

### Why serialize using `JsonGenerator`?

`generator.writeStartObject()`, `writeStringField(...)`, and `writeEndObject()` produce valid JSON and handle escaping properly. Never hand-build JSON via `"{\"amount\":\"" + ...`, because arbitrary values may contain characters needing escaping.

`BigDecimal.toPlainString()` avoids exponent notation in wire output. For `new BigDecimal("12.50")`, it writes `"12.50"`; for `BigDecimal` values in scientific notation, other formatting choices may apply, so define the contract upfront.

### Why deserialize by reading `JsonNode`?

`parser.getCodec().readTree(parser)` reads the entire `Money` JSON value into a `JsonNode`; we verify the root is an object, both required fields are **textual**, and then construct `Money`. This is easy to follow for small objects. For very large documents or streaming, tree-based deserialization incurs memory allocation; a streaming parser reduces allocations, though token order and unknown fields must be handled carefully.

Crucially: the serializer writes `amount` as a string, and the deserializer **rejects** numeric `amount`. Thus the contract stays consistent rather than silently accepting undocumented wire forms.

When the constructor or `BigDecimal(String)` throws `IllegalArgumentException`, the code wraps it in `JsonMappingException`. The HTTP layer can map JSON reading errors to `400 Bad Request`. A deserializer should not dictate HTTP status codes directly because it may be used in message queues, files, caches, or non-HTTP unit tests.

### Null, missing fields, and unknown fields

- For JSON literal `null`, Jackson normally applies its own null handling rather than invoking `Money`'s `deserialize(...)` method.
- When the `Money` property is absent in `Receipt`, the value can become null and `Receipt`'s constructor will reject it.
- This deserializer reads `amount` and `currency` and ignores unknown fields. Rejecting unknown properties requires explicit checks or schema validation; do not assume `FAIL_ON_UNKNOWN_PROPERTIES` checks keys automatically once a custom deserializer reads the tree itself.

Never use serializers/deserializers to perform database I/O or log sensitive data; keep them focused on conversion, deterministic, and easy to test.

## 8. SimpleModule for the OrderCode value object

Instead of `@JsonComponent`, `OrderCode` will be handled via a Jackson Module. Create `src/main/java/com/example/jsonlab/OrderCodeModule.java`:

```java
package com.example.jsonlab;

import java.io.IOException;

import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonToken;
import com.fasterxml.jackson.databind.DeserializationContext;
import com.fasterxml.jackson.databind.JsonDeserializer;
import com.fasterxml.jackson.databind.JsonMappingException;
import com.fasterxml.jackson.databind.JsonSerializer;
import com.fasterxml.jackson.databind.SerializerProvider;
import com.fasterxml.jackson.databind.module.SimpleModule;

import org.springframework.stereotype.Component;

@Component
public class OrderCodeModule extends SimpleModule {

    public OrderCodeModule() {
        super("OrderCodeModule");

        addSerializer(OrderCode.class, new JsonSerializer<OrderCode>() {

            @Override
            public void serialize(
                    OrderCode value,
                    JsonGenerator generator,
                    SerializerProvider provider) throws IOException {
                generator.writeString(value.value());
            }
        });

        addDeserializer(OrderCode.class, new JsonDeserializer<OrderCode>() {

            @Override
            public OrderCode deserialize(
                    JsonParser parser,
                    DeserializationContext context) throws IOException {

                if (!parser.hasToken(JsonToken.VALUE_STRING)) {
                    throw JsonMappingException.from(
                            parser, "OrderCode must be a JSON string");
                }

                try {
                    return new OrderCode(parser.getText());
                } catch (IllegalArgumentException exception) {
                    throw JsonMappingException.from(
                            parser,
                            "Invalid OrderCode: " + exception.getMessage(),
                            exception);
                }
            }
        });
    }
}
```

`SimpleModule.addSerializer` registers the `OrderCode` → JSON string converter, and `addDeserializer` registers the reverse. `parser.hasToken(JsonToken.VALUE_STRING)` verifies the input token type without coercing JSON objects/numbers into strings. `OrderCode`'s constructor then validates the pattern.

### How does Spring Boot register a Module?

In Spring Boot 3.3, a Jackson `Module` bean in the `ApplicationContext` is auto-registered with Boot's configured `ObjectMapper`. `OrderCodeModule` is annotated with `@Component` under the application root package, so it becomes a module bean.

An alternative configuration style when keeping Jackson Modules free of Spring component annotations is:

```java
@Configuration(proxyBeanMethods = false)
class ModulesConfiguration {
    @Bean
    Module orderCodeModule() {
        SimpleModule module = new SimpleModule("order-code");
        module.addSerializer(
                OrderCode.class, new OrderCodeSerializer());
        module.addDeserializer(
                OrderCode.class, new OrderCodeDeserializer());
        return module;
    }
}
```

**This is only an architectural snippet, not part of the runnable project.** `OrderCodeSerializer` and `OrderCodeDeserializer` are assumed to be defined separately. In the sample project, `OrderCodeModule` is already a bean, so do **not** add this second config to avoid duplicate registration.

### Using Jackson outside Spring

```java
ObjectMapper mapper = new ObjectMapper();
mapper.registerModule(new OrderCodeModule());
```

Here the module affects **only this mapper**. Any controller using Boot's configured mapper does not automatically change from calling `registerModule` on a standalone object. That is why plain Jackson tests and Spring Boot mapper tests must be distinguished.

### Choosing Module vs @JsonComponent

`@JsonComponent` is concise for a few Spring-managed handlers. `SimpleModule` is useful when building a library/group of handlers, needing registration on standalone mappers, or handling key serializers/deserializers. The two options do not compete when targeting different types as in this example. Never register two serializers for the same type and rely on arbitrary module ordering.

## 9. REST controller to test JSON at the HTTP boundary

`src/main/java/com/example/jsonlab/ReceiptController.java`:

```java
package com.example.jsonlab;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/receipts")
public class ReceiptController {

    @PostMapping(
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Receipt> echo(
            @RequestBody Receipt receipt) {
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(receipt);
    }
}
```

The endpoint simply echoes input; it writes to no DB and creates no payment orders. Its sole purpose is testing:

1. Spring MVC POST routing and requiring `Content-Type: application/json`.
2. Jackson deserializing `Money` and `OrderCode` per configuration.
3. The controller returning `Receipt`.
4. Jackson serializing the right JSON output with HTTP status `201 Created`.

A test calling `controller.echo(receipt)` directly bypasses Spring MVC's JSON reader/writer. Use `MockMvc` or a real HTTP client when proving the mapper is wired into HTTP conversion.

## 10. `@JsonTest` checks mapping without starting a server

Create `src/test/java/com/example/jsonlab/ReceiptJsonTest.java`:

```java
package com.example.jsonlab;

import java.math.BigDecimal;

import com.fasterxml.jackson.databind.JsonMappingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.json.JsonTest;
import org.springframework.boot.test.json.JacksonTester;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertThrows;

@JsonTest
class ReceiptJsonTest {

    @Autowired
    ObjectMapper mapper;

    @Autowired
    JacksonTester<Receipt> json;

    private Receipt sample() {
        return new Receipt(
                7L,
                new Money(new BigDecimal("12.50"), "USD"),
                new OrderCode("ORD-0007"));
    }

    @Test
    void serializesReceiptUsingBothCustomizations()
            throws Exception {
        assertThat(json.write(sample())).isEqualToJson("""
            {
              "id": 7,
              "total": {
                "amount": "12.50",
                "currency": "USD"
              },
              "code": "ORD-0007"
            }
            """);
    }

    @Test
    void deserializesReceiptUsingBothCustomizations()
            throws Exception {
        Receipt parsed = json.parseObject("""
            {
              "id": 7,
              "total": {
                "amount": "12.50",
                "currency": "USD"
              },
              "code": "ORD-0007"
            }
            """);

        assertThat(parsed).isEqualTo(sample());
    }

    @Test
    void preservesAmountScaleAcrossRoundTrip()
            throws Exception {
        String wire = mapper.writeValueAsString(sample());
        Receipt parsed = mapper.readValue(
                wire, Receipt.class);

        assertThat(parsed.total().amount())
                .isEqualTo(new BigDecimal("12.50"));
        assertThat(parsed.total().amount().scale())
                .isEqualTo(2);
    }

    @Test
    void standaloneMoneyHasCustomObjectShape()
            throws Exception {
        String wire = mapper.writeValueAsString(
                new Money(new BigDecimal("4.00"), "EUR"));

        assertThat(wire).isEqualTo(
                "{\"amount\":\"4.00\",\"currency\":\"EUR\"}");
    }

    @Test
    void rejectsNumericMoneyAmount() {
        assertThrows(JsonMappingException.class,
                () -> mapper.readValue("""
                    {"amount":12.50,"currency":"USD"}
                    """, Money.class));
    }

    @Test
    void rejectsUnparseableMoneyAmount() {
        assertThrows(JsonMappingException.class,
                () -> mapper.readValue("""
                    {"amount":"twelve","currency":"USD"}
                    """, Money.class));
    }

    @Test
    void rejectsInvalidCurrency() {
        assertThrows(JsonMappingException.class,
                () -> mapper.readValue("""
                    {"amount":"12.50","currency":"usd"}
                    """, Money.class));
    }

    @Test
    void rejectsInvalidOrderCode() {
        assertThrows(JsonMappingException.class,
                () -> mapper.readValue(
                    "\"ORD-7\"", OrderCode.class));
    }

    @Test
    void nullMoneyUsesJacksonNullHandling()
            throws Exception {
        assertThat(mapper.writeValueAsString((Money) null))
                .isEqualTo("null");

        assertThat(mapper.readValue("null", Money.class))
                .isNull();
    }
}
```

**There are 9 test methods.** `@JsonTest` in Boot 3.3 auto-configures `ObjectMapper`, `@JsonComponent` beans, and Jackson `Module` beans matching the JSON test slice. `JacksonTester<Receipt>` provides clear semantic JSON assertions.

### Why use both JacksonTester and ObjectMapper?

`JacksonTester.write(...)` with `isEqualToJson(...)` compares JSON structure without depending on whitespace or key order when unnecessary. `ObjectMapper` lets you directly check round-trips, `BigDecimal` scale, and exception types on invalid input.

Tests using literal JSON input are valuable because they simulate the client contract. If you only serialize and deserialize the same object, both serializer and deserializer could be broken simultaneously while the test still PASSES.

### Why check scale?

`new BigDecimal("12.50")` has scale 2. `BigDecimal("12.5")` has the same numerical value under `compareTo`, yet a different scale; `BigDecimal.equals` distinguishes them. Because this example's contract writes `amount` as a decimal string, the test protects `scale() == 2`. If your API does not require preserving scale, define a rounding/normalization policy and adjust expectations deliberately.

### What do the invalid-input tests protect?

- `rejectsNumericMoneyAmount`: `amount` is a JSON number, rejected even though the numeric value looks valid.
- `rejectsUnparseableMoneyAmount`: string cannot construct a `BigDecimal`.
- `rejectsInvalidCurrency`: currency violates `Money`'s constructor.
- `rejectsInvalidOrderCode`: code does not match the pattern.
- `nullMoneyUsesJacksonNullHandling`: JSON literal null is handled separately by Jackson, without necessarily invoking the custom deserializer.

Do not rely on exact Jackson error message wording across all versions; asserting `JsonMappingException` suffices at the mapping unit level. The HTTP layer tests status 400.

## 11. Unit testing a Module without a Spring context

Create `src/test/java/com/example/jsonlab/OrderCodeModuleStandaloneTest.java`:

```java
package com.example.jsonlab;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class OrderCodeModuleStandaloneTest {

    @Test
    void moduleCanBeRegisteredWithPlainJacksonMapper()
            throws Exception {
        ObjectMapper mapper = new ObjectMapper();
        mapper.registerModule(new OrderCodeModule());

        OrderCode code = new OrderCode("ORD-0042");

        assertThat(mapper.writeValueAsString(code))
                .isEqualTo("\"ORD-0042\"");

        assertThat(mapper.readValue(
                "\"ORD-0042\"", OrderCode.class))
                .isEqualTo(code);
    }
}
```

**There is 1 test method.** It proves standalone registration of `SimpleModule`. However, it **does not prove** that the Boot application registered the `Module` bean or `MoneyJson`; since the mapper is freshly instantiated, it lacks other Boot auto-registered customizations.

If someone in a project creates `new ObjectMapper()` inside a controller, `@JsonTest` can PASS while HTTP behavior differs. It is better to inject Boot's mapper or explicitly configure one shared mapper.

## 12. Integration test: JSON passing through Spring MVC

Create `src/test/java/com/example/jsonlab/ReceiptMvcTest.java`:

```java
package com.example.jsonlab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ReceiptMvcTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void validPayloadUsesCustomReadersAndWriters()
            throws Exception {
        mockMvc.perform(post("/api/receipts")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "id": 7,
                      "total": {
                        "amount": "12.50",
                        "currency": "USD"
                      },
                      "code": "ORD-0007"
                    }
                    """))
                .andExpect(status().isCreated())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.id").value(7))
                .andExpect(jsonPath("$.total.amount").value("12.50"))
                .andExpect(jsonPath("$.total.currency").value("USD"))
                .andExpect(jsonPath("$.code").value("ORD-0007"));
    }

    @Test
    void invalidMoneyAmountIsBadRequest()
            throws Exception {
        mockMvc.perform(post("/api/receipts")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "id": 7,
                      "total": {
                        "amount": 12.50,
                        "currency": "USD"
                      },
                      "code": "ORD-0007"
                    }
                    """))
                .andExpect(status().isBadRequest());
    }

    @Test
    void nonJsonContentTypeIsUnsupported()
            throws Exception {
        mockMvc.perform(post("/api/receipts")
                .contentType(MediaType.TEXT_PLAIN)
                .content("not json"))
                .andExpect(status().isUnsupportedMediaType());
    }
}
```

**There are 3 test methods.** This is an HTTP contract test via **MockMvc**, not a TCP request to embedded Tomcat: `@SpringBootTest` builds the application context, and `@AutoConfigureMockMvc` sets up mock servlet infrastructure. It suffices to check JSON bodies, content types, converters, controller mappings, and status codes. If the product needs real network/TLS/server port verification, add `@SpringBootTest(webEnvironment=RANDOM_PORT)` with an HTTP client in a dedicated suite.

The assertions verify the JSON path end to end:

```text
POST JSON body
  -> Spring MVC HttpMessageConverter
  -> Boot ObjectMapper
  -> MoneyJson.Deserializer + OrderCodeModule deserializer
  -> ReceiptController.echo(...)
  -> MoneyJson.Serializer + OrderCodeModule serializer
  -> JSON response, HTTP 201
```

When `amount` is a JSON number, the custom `Money` deserializer throws a mapping exception; MVC normally wraps it in `HttpMessageNotReadableException` and returns 400 by default. With `Content-Type: text/plain` on an endpoint with `consumes=application/json`, the request is rejected with 415. If the application has a custom `@ControllerAdvice`, assert status/error schema against the actual policy.

## 13. Run commands and expected results to verify

| Class | Number of `@Test` | Scope |
| --- | ---: | --- |
| `ReceiptJsonTest` | 9 | `@JsonTest`, Boot mapper, `@JsonComponent`, and Module |
| `OrderCodeModuleStandaloneTest` | 1 | Module with plain `ObjectMapper` |
| `ReceiptMvcTest` | 3 | Full context + MockMvc HTTP JSON mapping |

Total of **13 test methods** in the example code.

Run commands if the project includes a Gradle Wrapper:

```bash
./gradlew test --tests 'com.example.jsonlab.ReceiptJsonTest'
./gradlew test --tests 'com.example.jsonlab.OrderCodeModuleStandaloneTest'
./gradlew test --tests 'com.example.jsonlab.ReceiptMvcTest'
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

If no Wrapper is present, run `gradle test` with a compatible installed Gradle. There is no fixed business stdout; Gradle writes HTML reports to `build/reports/tests/test/index.html` and XML data to `build/test-results/test/`.

**These are expectations based on the source, not an already-executed CI report.** In practice, inspect the actual report, including passed/failed test counts, dependency versions, and exception causes if any.

## 14. Very important boundaries

### 14.1. Null does not always pass through a custom deserializer

If JSON contains `"total":null`, Jackson can bypass `MoneyJson.Deserializer.deserialize(...)` and produce Java null. `Receipt` in the example rejects null via its constructor. If an endpoint wants Bean Validation instead of constructor invariants, configure `@NotNull`/`@Valid` with the proper validation dependency.

If a test merely calls `mapper.readValue("null", Money.class)`, default null handling may return Java null. Do not conclude the custom deserializer "allowed empty money"—it may never have been invoked.

### 14.2. Unknown fields and duplicate keys

`Money`'s deserializer reads into a `JsonNode` and extracts two fixed fields. An extra JSON field like `"unknown":"x"` is not actively checked by this handler. For duplicate keys, tree-based processing may keep one version of the value depending on parser/features.

If the contract requires strictness, add checks for the allowed field set and a duplicate-detection policy. Never assume `FAIL_ON_UNKNOWN_PROPERTIES` automatically covers an object when a custom deserializer **manually reads the tree**.

### 14.3. Numeric precision and scale

Do not convert `BigDecimal` through `double` to "simplify" JSON. With JSON numbers, JavaScript clients can lose precision; with decimal strings, the server must validate parseability and scale/rounding rules. `toPlainString()` writes without exponents, yet it does not enforce a "two decimal places for every currency" policy by itself.

For instance, `new BigDecimal("1E+3").toPlainString()` returns `"1000"`. If the wire contract forbids exponents on **input**, add regex validation or custom parser rules; `BigDecimal(String)` accepts scientific notation.

### 14.4. Jackson DTO mapping does not replace business logic

Serializers exist to represent objects, not to query the DB to check active currency codes, deduct inventory, or emit events. Business validation should run at the appropriate domain/service boundary. If a custom deserializer performs network calls, it slows down request decoding, complicates retries, and risks side effects before the controller even sees the request.

### 14.5. Map key serializers differ from value serializers

If an API uses `Map<OrderCode, String>`, JSON object property names are **map keys**. Handlers added via `addSerializer(OrderCode.class, ...)` for values are not automatically used for keys. When custom map keys are needed, use `KeySerializer`/`KeyDeserializer` or the corresponding Module registrations, and test JSON object keys separately.

### 14.6. Polymorphic deserialization and security

Never enable unrestricted default typing allowing clients to specify arbitrary Java classes to instantiate. If an API requires subtypes, use an explicit discriminator, a subtype allowlist, and test that unknown types are rejected. A JSON field holding a client-supplied class name is **never trustworthy input for reflection**.

### 14.7. Date/time: prefer standard modules whenever possible

For `Instant`, `OffsetDateTime`, and `LocalDateTime`, check the Java Time module and Spring Boot/Jackson configuration before writing custom serializers. `LocalDateTime` carries no timezone; never silently assume it is UTC. If the contract demands epoch milliseconds or RFC 3339, specify timezone/offset and test both directions.

## 15. @JsonComponent, @JsonSerialize, and module precedence

When only **one field** of a DTO needs a different format, you can annotate it:

```java
public record ReportRow(
        @JsonSerialize(using = SpecialMoneySerializer.class)
        Money displayAmount
) {}
```

This is a non-standalone illustrative snippet: `SpecialMoneySerializer` and its imports must be declared in the application using it. It illustrates a property-level serializer, whereas `SimpleModule.addSerializer(Money.class, ...)` typically has type-level scope on the mapper.

When combining property annotations and modules for the same type, Jackson follows its own resolution rules; do not guess precedence by reading source order. Keep only the rules you need and guard the output with JSON contract tests.

Spring Boot 3.3 also provides `Jackson2ObjectMapperBuilderCustomizer` for global settings such as naming strategies, inclusion, or indentation. Never create a separate `new ObjectMapper()` inside each controller just to tweak one property; use the proper configuration/Module/annotation and inject the shared mapper.

## 16. Layered testing: why not use just one test type?

| Test level | What it concludes | What it leaves unproven |
| --- | --- | --- |
| Pure Java JUnit + `registerModule` | `SimpleModule` logic works on that specific mapper | Whether Boot auto-registers the `Module` bean |
| `@JsonTest` + `JacksonTester` | Boot JSON slice uses the custom component/module | Whether HTTP controllers are wired correctly |
| `@SpringBootTest` + MockMvc | Spring MVC HTTP reader/writer uses the mapper and returns right statuses | Real TCP server/TLS/proxies |
| `RANDOM_PORT` HTTP integration | Real embedded server receives HTTP and returns wire JSON | External systems, DB consistency if absent |
| Consumer/provider contract tests | JSON contract between real service and clients | All business effects under failure/concurrency |

**A real-world bug:** `@JsonTest` PASSES, yet a controller has a custom `MappingJackson2HttpMessageConverter` holding a different mapper. MVC tests will show wrong response JSON formats. In that case, never "edit" expected JSON to match the bug; inspect which mapper the HTTP converter actually uses.

## 17. How to investigate when custom mapping fails to work

1. Determine whether the failure is on **write** or **read**.
2. Inspect the actual JSON: string or number, object or primitive, missing field or malformed JSON?
3. Check whether the application uses the **Spring Boot-managed `ObjectMapper`** or a manually instantiated mapper.
4. Confirm `@JsonComponent` lies inside component scan for the proper package.
5. Check whether the `Module` bean is created and registered with the right mapper.
6. If `@JsonTest` does not load a module from a separate `@Configuration`, consider `@Import`ing that config into the slice or right-sized test context.
7. Check model invariants, custom constructors, and exception wrapping.
8. Check `Content-Type`, `Accept`, and `consumes/produces` when failures happen over HTTP.
9. Isolate a plain module unit test outside Spring to narrow down the cause.
10. After fixing, re-run both the JSON slice and MVC tests; never look only at one happy-path test.

## 18. Symptom and cause table

| Symptom | Possible cause | How to verify |
| --- | --- | --- |
| `Money` writes `amount` as a number | `@JsonComponent` not scanned/registered or wrong mapper used | `@JsonTest` and MVC test |
| `OrderCode` becomes an object with `value` | `SimpleModule` not registered | Test Boot mapper and plain mapper |
| Plain mapper PASSES, Boot mapper FAILS | `Module` bean missing from context | Package scan, `@Component`/`@Bean` |
| `@JsonTest` PASSES, HTTP FAILS | Converter uses a separate mapper | MockMvc and converter configuration |
| Numeric JSON `amount` returns 400 | Deserializer intentionally accepts strings only | Check payload against contract |
| JSON `null` not rejected by custom deserializer | Separate null handling | Constructor invariant / validation |
| Unknown field silently ignored | Custom tree handler does not check extra keys | Strict schema test |
| Map key ignores custom format | Key serializer differs from value serializer | `addKeySerializer`/`addKeyDeserializer` |
| `BigDecimal` turns into `double` style | Passed through floating point at some step | Literal JSON, scale, and precision tests |
| Exception message changes after upgrade | Relied on internal Jackson wording | Assert type/status/code rather than full stack traces |
| JSON timestamps shifted by timezone | Wrong `Instant`/`LocalDateTime`/config | Test timezones/offsets |
| HTTP returns 415 | `Content-Type` does not match `consumes` | MockMvc media-type assertion |
| HTTP returns 400 | Invalid JSON syntax/type/constructor validation | Inspect root cause |
| Flaky test suite | Mapper mutated after startup or shared mutable state | Configure before use; isolate test data |

## 19. QA checklist for custom JSON

1. Is the wire format specified before writing code?
2. Does the serializer write the right JSON tokens and escaping?
3. Does the deserializer validate root shape, field types, and values?
4. Are both literal JSON and round-trips tested?
5. Are missing, null, malformed, wrong-type, and domain-invalid inputs distinguished?
6. Do decimal amounts preserve precision and scale per contract?
7. Is `@JsonComponent` present in the Spring application context?
8. Is the `Module` bean registered on Boot's `ObjectMapper`?
9. Is there a module unit test using `new ObjectMapper().registerModule(...)`?
10. Is there a `@JsonTest` covering serialization and deserialization in Spring?
11. Is there an MVC/HTTP test verifying request/response and 400/415 status codes?
12. Have competing serializers for the same Java type been avoided?
13. Are serializers/deserializers free of mutable per-request state?
14. Is mutating `ObjectMapper` config while handling concurrent requests avoided?
15. Is unrestricted auto-typing/unsafe subtype resolution avoided?
16. Have other libraries (Kafka/Redis/WebClient) been checked for using the right mapper if required by contract?
17. Are secret logging and side effects avoided during deserialization?
18. Do tests run on the project's exact Java/Boot/Jackson versions?
19. Does the actual test report match the test count rather than guessing from source?
20. Are wire contract changes versioned/communicated to consumers when needed?

## 20. Deliberate practice exercises

1. Run `ReceiptJsonTest` and observe `amount` serialized as a JSON string.
2. Remove `@JsonComponent` from `MoneyJson` and re-run; distinguish a registration error from a serializer logic bug.
3. Remove `@Component` from `OrderCodeModule` without registering it elsewhere; observe how the JSON shape of `code` changes.
4. Use a plain mapper + `registerModule` to see Jackson supports modules independently of Spring.
5. Try sending `"amount":12.50`; explain the token type error compared to `"amount":"12.50"`.
6. Try `"amount":"abc"`, `"currency":"usd"`, and `"code":"ORD-7"`; distinguish parse failures from domain invariants.
7. Add tests with `total=null` and a missing `total` field to test `Receipt`'s constructor.
8. Try adding an unknown field inside `Money`; decide on an ignore-or-reject policy and write a test for that choice.
9. Verify `BigDecimal("12.50")` preserves scale 2 across round-trip; then test scientific notation.
10. Create another DTO using `@JsonSerialize` on a single field and compare its scope with a module.
11. Extend the Module for `Map<OrderCode,String>` using dedicated key serializer/deserializer.
12. Write a contract upgrade test across two JSON versions to protect backward compatibility with consumers.
13. Try a MockMvc POST with `Content-Type: text/plain` to distinguish media type errors from JSON parsing.
14. When needed, add a `RANDOM_PORT` HTTP test to verify behavior over a real port.
15. Run `./gradlew test`, open the HTML report, confirm **13 test methods**, and inspect failure stack traces if any.

## 21. Official Documentation

- [Spring Boot 3.3 — JSON / Jackson](https://docs.spring.io/spring-boot/3.3/reference/features/json.html): `@JsonComponent`, custom serializers/deserializers, Jackson auto-configuration.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@JsonTest`, `JacksonTester`, Module auto-config, and Spring MVC testing.
- [Jackson Databind 2.17 — JsonSerializer](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/2.17.2/com/fasterxml/jackson/databind/JsonSerializer.html): serializer contract.
- [Jackson Databind 2.17 — JsonDeserializer](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/2.17.2/com/fasterxml/jackson/databind/JsonDeserializer.html): deserializer contract.
- [Jackson Databind 2.17 — SimpleModule](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/2.17.2/com/fasterxml/jackson/databind/module/SimpleModule.html): registering handlers, key serializers/deserializers.
- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html): testing JSON readers/writers through Servlet MVC without real TCP.

## 22. Summary

A **custom serializer** defines how a Java object is written as JSON; a **custom deserializer** defines which JSON creates a Java object and which inputs must be rejected; a **Module** registers those rules onto an `ObjectMapper`; and **`@JsonComponent`** is the Spring Boot 3.x mechanism for discovering and registering JSON components via component scan.

A trustworthy test suite must protect **wire contracts**, **domain invariants**, **registration on the real mapper**, and **HTTP behavior** together. Use plain JUnit module tests to isolate conversion logic, `@JsonTest` to verify Boot configuration, and `MockMvc` to confirm Spring MVC applies the same mapping to requests and responses. Always account for nulls, missing/unknown fields, `BigDecimal` precision, and the difference between a `new`-created mapper and the application's real mapper.
