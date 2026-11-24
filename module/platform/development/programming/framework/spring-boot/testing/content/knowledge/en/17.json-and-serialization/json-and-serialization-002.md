# Testing JSON with JacksonTester, JsonbTester, GsonTester, and BasicJsonTester

> **Module:** Spring Boot – testing  
> **Group:** JSON and serialization  
> **Topic:** JacksonTester, JsonbTester, GsonTester, or BasicJsonTester by library  
> **Goal:** Choose the right JSON tester for the mapper in use, verify serialization/deserialization and JSON contracts with meaningful assertions, distinguish `@JsonTest` from unit tests that manually initialize testers, and understand the limits and differences among Jackson, Gson, Jakarta JSON-B, and raw JSON strings.

## 1. The actual problem to test

In a Spring Boot application, converting a Java object to JSON is not just calling `toString()`. Data crossing an API or message broker boundary must adhere to a contract, for example:

```json
{
  "order_id": 502,
  "recipient": "buyer@example.test",
  "quantity": 3,
  "shipOn": "2026-06-17"
}
```

A DTO can be serialized incorrectly in many ways:

- `order_id` turns into `orderId` because an annotation was omitted or a different mapper was used.
- `shipOn` becomes a timestamp/array instead of a `yyyy-MM-dd` date string.
- The `recipient` field is null or mixed up with another address.
- `quantity` is serialized as the string `"3"` instead of the number `3`.
- An internal field, password, or token accidentally leaks into JSON.
- A required field is omitted during deserialization, falling back to an unintended default value.
- JSON is syntactically valid but semantically wrong: currency, units, precision, timezone, enum naming.
- Tests only compare the Java object against itself, without checking the actual JSON output.

A quality test should verify **both directions** when the system requires it:

1. **Serialization:** Does Java object → JSON have the right field names, data types, values, structure, and excluded fields?
2. **Deserialization:** Does JSON from a client/provider → Java object properly read required/optional fields, enums, dates/times, and numeric types?
3. **Negative contract:** Under what policy is malformed JSON, missing required fields, or invalid values handled?
4. **Mapper configuration:** Does it use the same `ObjectMapper`/`Gson`/`Jsonb` and modules/naming rules as the real application?

Spring Boot provides four main helpers under the `org.springframework.boot.test.json` package for writing assertions closer to the JSON contract than manual string comparison.

## 2. Choose the tester by library, not by arbitrary preference

| Tester | Engine used to serialize/parse objects | Suitable input | Typical usage |
| --- | --- | --- | --- |
| **`JacksonTester<T>`** | Jackson `ObjectMapper` | Java DTO/record using Jackson, `@JsonProperty`, `@JsonFormat`, Jackson modules | `@JsonTest` + `@Autowired JacksonTester<Dto>` |
| **`GsonTester<T>`** | Google `Gson` | DTO serialized by Gson, `@SerializedName`, `TypeAdapter` | `@JsonTest` when Gson is present or unit test with `GsonTester.initFields` |
| **`JsonbTester<T>`** | Jakarta JSON Binding `Jsonb` | DTO using `@JsonbProperty`, JSON-B adapters/visibility | `@JsonTest` when a provider is present or unit test with `JsonbTester.initFields` |
| **`BasicJsonTester`** | Does not convert Java objects through a mapper; accepts JSON bytes/text/file | JSON already produced by any source, raw HTTP response, message text | `new BasicJsonTester(getClass())` + `json.from(payload)` |

They share a common set of JSON assertion features because Spring Boot integrates AssertJ, JSONAssert, and JsonPath. However, **a tester does not change the JSON engine that production uses**. If the real API runs on Jackson while tests use `GsonTester`, you may miss Jackson-specific configurations of the API itself.

### 2.1. Decision questions

- Standard Spring MVC/WebFlux application with Jackson on the classpath and DTOs using `com.fasterxml.jackson.annotation.*`? Usually choose **JacksonTester**.
- Real system intentionally uses Gson (`com.google.gson.Gson`)? Choose **GsonTester**, providing the right `Gson` instance or corresponding Boot auto-configuration.
- System based on Jakarta JSON-B (`jakarta.json.bind.Jsonb`)? Choose **JsonbTester**, with both the JSON-B API **and an implementation** such as Eclipse Yasson.
- You only have a JSON payload from a webhook, fixture file, response, or producer without needing to build an object? Choose **BasicJsonTester**.
- Want to test real HTTP request/response through a controller? A JSON tester is only **one part**; add `MockMvc`, `WebTestClient`, or an HTTP client integration test depending on the boundary.

**There is no "strongest tester for every situation."** The right choice depends on the contract and engine. For example, Java records are well serialized by Jackson in Spring Boot 3.5; if using a Gson version or JSON-B provider that does not support the same record/annotation semantics, verify that engine's capabilities rather than assuming equivalence.

## 3. What does `@JsonTest` actually auto-configure?

`@JsonTest` is a **test slice** in `spring-boot-test-autoconfigure`. It sets up the JSON configuration under test without loading the entire business application.

When the corresponding libraries are present and auto-configuration conditions are met, it can load:

- Jackson `ObjectMapper`, matching Jackson `Module` beans, and `@JsonComponent` beans.
- Gson `Gson` and customizations when supported by the classpath/config.
- JSON-B `Jsonb` with a compatible provider when appropriate dependencies are present.
- JSON testers eligible for field injection.
- JSON/JSONPath assertion mechanisms from test dependencies.

It does **not** start an HTTP listener, run all controllers/services/repositories, make network calls, or boot a full Spring Boot application context like `@SpringBootTest`.

Example:

```java
@JsonTest
class ShippingNoticeJsonTest {
    @Autowired
    JacksonTester<ShippingNotice> json;
}
```

This is a **condensed configuration snippet**; the runnable project in section 5 has full imports and test methods. `@JsonTest` together with Spring Boot's tester support automatically initializes the `JacksonTester<ShippingNotice>` field with the proper generic type, so you do not need to write `new JacksonTester(...)` yourself.

### 3.1. Role of `@AutoConfigureJsonTesters`

`@AutoConfigureJsonTesters` lets you customize JSON tester registration; its `enabled` attribute defaults to `true`. When `@JsonTest` works normally, you usually **do not need to add** this annotation.

```java
@JsonTest
@AutoConfigureJsonTesters(enabled = true)
class ExampleJsonTest {
    // Tester fields are initialized when an appropriate mapper is available.
}
```

This is only an annotation template, not a standalone test. Do not confuse `@AutoConfigureJsonTesters` with adding an engine dependency: if the project lacks Gson or a JSON-B provider, the annotation will not download libraries from Maven.

### 3.2. Does `@JsonTest` use the real mapper configuration or a fresh mapper?

The strength of `@JsonTest` is that it typically uses the **Spring Boot-configured mapper bean** in the JSON slice: `spring.jackson.*` properties, `@JsonComponent`, and Modules/Customizers suited to the test context. This differs from:

```java
ObjectMapper mapper = new ObjectMapper();
```

A manually created `ObjectMapper` may lack `JavaTimeModule`, naming strategies, serializers, visibility rules, mix-ins, or null policies used by the app. Tests with a default mapper might pass while the app's HTTP JSON differs, or vice versa.

However, the slice does not necessarily scan/import **every custom `@Configuration`** in the application. If a Jackson Module is declared in a configuration excluded from the slice, `@Import` that small module/config specifically, or use a full-context/integration test to verify bean wiring. Do not rush to turn every JSON test into `@SpringBootTest` just because a module was missing.

### 3.3. What if multiple JSON engines are on the classpath?

`@JsonTest` can support multiple engines if they are present, but the JSON engine used by the application's HTTP converters is chosen by dependencies, auto-configuration, and custom settings. A passing `GsonTester` test does not prove MVC uses Gson; similarly, a `JsonbTester` test does not prove the real message producer uses JSON-B.

To test **actual serialization at the HTTP boundary**, test the MVC/WebFlux converter and response body in an appropriate HTTP test. To avoid unnecessary complexity in this lesson, the runnable project below uses Jackson + Basic, while Gson/JSON-B are presented as **two opt-in extensions** with explicit dependencies.

## 4. Meaningful JSON assertions

Suppose a tester returns `JsonContent<T>`:

```java
assertThat(json.write(dto))
        .isEqualToJson("expected-shipping-notice.json");
```

`isEqualToJson` performs **structural JSON comparison**, not character-by-character string comparison via `String#equals`. This approach typically avoids locking tests to whitespace or object field order. The `.json` filename is a fixture resource (see layout in section 5).

```java
assertThat(json.write(dto))
        .extractingJsonPathStringValue("@.recipient")
        .isEqualTo("buyer@example.test");
```

This directly checks a field the consumer relies on. The `@.recipient` syntax refers to the JSON root in this API (you may see JSONPath examples using `$` elsewhere; follow the convention supported by Spring Boot's test API).

Some useful assertion patterns:

| What to prove | Assertion choice |
| --- | --- |
| JSON matches fixture | `assertThat(json.write(dto)).isEqualToJson("expected.json")` |
| String field exists with right value | `extractingJsonPathStringValue("@.field").isEqualTo(...)` |
| Number exists with right value | `extractingJsonPathNumberValue("@.quantity")` + `Number` assertion |
| Java object round-trip | `assertThat(json.parseObject(payload)).isEqualTo(expected)` |
| No secret fields leaked | Parse into JSON tree/map and assert field does not exist |
| Array in exact order when order is contracted | Compare JSONPath list/array or JSON tree in order |
| Syntactically invalid JSON | Check mapper/tester exception; do not accept silent parsing |
| HTTP request/response status/headers | `MockMvc`/`WebTestClient` alongside the tester |

**Do not merely check "valid JSON."** Valid JSON can still contain wrong fields or omit required fields.

### 4.1. JSON numbers: avoid confusing `Integer`, `Long`, `Double`, and `BigDecimal`

JSON has a `number` type without separate `int`/`long`/`double` types. After JsonPath extraction, a value may be a specific `Number` object depending on the parser and number magnitude. Thus, a rigid comparison:

```java
assertThat(json.write(dto))
        .extractingJsonPathNumberValue("@.quantity")
        .isEqualTo(3L);
```

can be brittle if the value is returned as `Integer(3)` rather than `Long(3)`. When the contract only requires an integer value:

```java
assertThat(json.write(dto))
        .extractingJsonPathNumberValue("@.quantity")
        .satisfies(number ->
                assertThat(number.intValue()).isEqualTo(3));
```

Both snippets are **assertion templates embedded in a test**; they require `assertThat` static import and `json`/`dto` variables. For monetary amounts, do **not** convert to `intValue()` since decimals would be lost. Use `BigDecimal`/decimal semantics in the domain, checking scale/precision per contract and JSON tree when needed. Checking that the JSON value is `3` rather than string `"3"` is also a separate assertion when type is part of the contract.

### 4.2. Missing differs from null, and null differs from empty string

The following three JSON payloads are **three distinct contracts**:

```json
{"order_id":502}
```

```json
{"order_id":502,"note":null}
```

```json
{"order_id":502,"note":""}
```

If clients distinguish "do not update" from "clear data," missing vs explicit null can have major impact. Do not just write `contains("note")` on strings; parse JSON and check `node.has("note")`, `node.hasNonNull("note")`, or specific properties. With Gson/JSON-B, use the corresponding JSON tree/parser or AssertJ JSONPath; do not rely on Jackson if the app deliberately avoids it.

### 4.3. JSON object field order vs array order

`{"a":1,"b":2}` and `{"b":2,"a":1}` are normally equivalent in JSON object semantics. However, arrays `[1,2]` and `[2,1]` have different orders.

If a test must protect item order, do not use an order-insensitive collection comparison. You can parse JSON into a tree and assert `assertThat(node.get("items").get(0)...).isEqualTo(...)`, or use ordered JSONPath array/list assertions. If the receiver requires canonical JSON bytes for signatures, order/whitespace/encoding truly are part of the contract and must be tested on **serialized bytes** per that spec.

### 4.4. Checks based solely on `toString()` are usually meaningless

This snippet does not test Jackson:

```java
ShippingNotice notice = ...;
assertThat(notice.toString()).contains("buyer@example.test");
```

It tests `record.toString()`, completely independent of `ObjectMapper`. Good tests must go through `json.write(notice)` or the real mapper to observe the JSON output. Similarly, `assertThat(json.parseObject(json.write(dto).getJson())).isEqualTo(dto)` is **only** a round-trip: both directions sharing the same mapping bug can still pass. Combine with an expected fixture or **independent** field-level contract checks.

## 5. Runnable Spring Boot/Java 17 project: JacksonTester + BasicJsonTester

The main project uses **Java 17, Spring Boot 3.5.16, Maven, Jackson, and AssertJ**. The JSON tests do not start an HTTP server or connect to a database/Internet, except that Maven may need to download dependencies on the first run.

### 5.1. File structure

```text
json-tester-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/jsonlab/
    │   │   ├── JsonTesterLabApplication.java
    │   │   └── ShippingNotice.java
    │   └── resources/
    │       └── application.yml
    └── test/
        ├── java/com/example/jsonlab/
        │   ├── ShippingNoticeJsonTest.java
        │   ├── RawJsonContractTest.java
        │   └── ManualJacksonTesterTest.java
        └── resources/com/example/jsonlab/
            └── expected-shipping-notice.json
```

Every public Java type matches its filename; all classes share package `com.example.jsonlab`. The fixture file is placed in `src/test/resources/com/example/jsonlab/` so it can be resolved relative to the test class's package. The project needs no controller/repository because the focus is the **JSON contract**, not HTTP mapping.

### 5.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>json-tester-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-json</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

- `spring-boot-starter-json` includes Jackson 2.x and common modules such as Java Time (managed by Boot's dependency management).
- `spring-boot-starter-test` includes JUnit Jupiter, AssertJ, JSONAssert, JsonPath, and Spring Boot test support.
- `spring-boot-starter-web` is **not needed** to test serialization: no controller/server is used.
- When moving the example to a real web app, `spring-boot-starter-web` typically already brings in Jackson. Avoid adding redundant duplicate dependencies.

### 5.3. Application root and DTO

```java
// src/main/java/com/example/jsonlab/JsonTesterLabApplication.java
package com.example.jsonlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JsonTesterLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(JsonTesterLabApplication.class, args);
    }
}
```

```java
// src/main/java/com/example/jsonlab/ShippingNotice.java
package com.example.jsonlab;

import java.time.LocalDate;

import com.fasterxml.jackson.annotation.JsonFormat;
import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;

public record ShippingNotice(
        @JsonProperty("order_id") long orderId,
        String recipient,
        int quantity,
        @JsonFormat(pattern = "yyyy-MM-dd") LocalDate shipOn,
        @JsonInclude(JsonInclude.Include.NON_NULL) String note) {
}
```

**JSON contract of `ShippingNotice`:**

| Java component | JSON field | Semantics |
| --- | --- | --- |
| `orderId` | `order_id` | Jackson annotation renames the field |
| `recipient` | `recipient` | Synthetic email string |
| `quantity` | `quantity` | JSON number, not a string |
| `shipOn` | `shipOn` | ISO-like date string matching the specified pattern |
| `note` null | Field `note` **omitted** | `@JsonInclude(NON_NULL)` on the component |

`@JsonProperty`, `@JsonFormat`, and `@JsonInclude` are all **Jackson annotations**. They are not guaranteed to be understood the same way by Gson/JSON-B. Sections 9/10 will use a neutral POJO without assuming any engine interprets Jackson annotations.

### 5.4. `application.yml`

```yaml
# src/main/resources/application.yml
spring:
  application:
    name: json-tester-lab
```

No `server.port`, database, or production secret is needed. `@JsonTest` only loads the JSON slice; the main application can also start as a non-web application if `main` is executed, though that is not required for tests.

### 5.5. Independent JSON fixture

File `src/test/resources/com/example/jsonlab/expected-shipping-notice.json`:

```json
{
  "order_id": 502,
  "recipient": "buyer@example.test",
  "quantity": 3,
  "shipOn": "2026-06-17"
}
```

The fixture is authored by the test writer from the contract, **not** generated by calling `json.write(actual)` itself and saving it without review. If a serializer bug changes `order_id` to `orderId`, the test must fail.

### 5.6. `ShippingNoticeJsonTest.java` — `@JsonTest` using real Jackson

```java
// src/test/java/com/example/jsonlab/ShippingNoticeJsonTest.java
package com.example.jsonlab;

import java.time.LocalDate;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.json.JsonTest;
import org.springframework.boot.test.json.JacksonTester;

import static org.assertj.core.api.Assertions.assertThat;

@JsonTest
class ShippingNoticeJsonTest {

    @Autowired
    private JacksonTester<ShippingNotice> json;

    @Autowired
    private ObjectMapper mapper;

    private ShippingNotice sample() {
        return new ShippingNotice(
                502L,
                "buyer@example.test",
                3,
                LocalDate.of(2026, 6, 17),
                null);
    }

    @Test
    void writesJsonContractFromRealJacksonConfiguration()
            throws Exception {
        assertThat(json.write(sample()))
                .isEqualToJson("expected-shipping-notice.json");

        assertThat(json.write(sample()))
                .extractingJsonPathStringValue("@.recipient")
                .isEqualTo("buyer@example.test");
    }

    @Test
    void keepsNumbersNumericAndDoesNotLeakNullNote()
            throws Exception {
        JsonNode actual = mapper.readTree(
                json.write(sample()).getJson());

        assertThat(actual.path("order_id").asLong())
                .isEqualTo(502L);
        assertThat(actual.path("quantity").isIntegralNumber())
                .isTrue();
        assertThat(actual.path("quantity").asInt())
                .isEqualTo(3);
        assertThat(actual.has("note")).isFalse();
        assertThat(actual.has("orderId")).isFalse();
    }

    @Test
    void deserializesKnownJsonIntoIndependentExpectedRecord()
            throws Exception {
        String payload = """
                {
                  "order_id": 502,
                  "recipient": "buyer@example.test",
                  "quantity": 3,
                  "shipOn": "2026-06-17"
                }
                """;

        ShippingNotice actual = json.parseObject(payload);

        assertThat(actual).isEqualTo(sample());
    }

    @Test
    void preservesUnicodeAndEscaping() throws Exception {
        ShippingNotice notice = new ShippingNotice(
                503L,
                "người.dùng@example.test",
                1,
                LocalDate.of(2026, 6, 18),
                "Chào \"bạn\"!");

        String jsonText = json.write(notice).getJson();
        ShippingNotice roundTrip = json.parseObject(jsonText);

        assertThat(roundTrip).isEqualTo(notice);
        assertThat(mapper.readTree(jsonText)
                .path("note").asText())
                .isEqualTo("Chào \"bạn\"!");
    }
}
```

**Explanation of each assertion:**

1. Fixture compares the entire JSON structure against an independent expected value.
2. JSONPath directly checks `recipient` as read by consumers.
3. `mapper.readTree` verifies `quantity` is numeric, the null `note` field is not serialized, and `orderId` is not leaked under its Java name.
4. `parseObject` checks JSON → record against the exact expected value, including `LocalDate`.
5. The Unicode/escaping round-trip is a **supplementary** test, not a replacement for an independent fixture, because both directions could share a bug and still produce the original object.

**Note on the Java code snippet:** In actual Java source, the literal `"Chào \"bạn\"!"` represents a string containing double quotes in its content. In Markdown files, the backslashes inside the code fence must be preserved as shown above when pasting into `.java`.

### 5.7. `RawJsonContractTest.java` — `BasicJsonTester` without a mapper

```java
// src/test/java/com/example/jsonlab/RawJsonContractTest.java
package com.example.jsonlab;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.json.BasicJsonTester;

import static org.assertj.core.api.Assertions.assertThat;

class RawJsonContractTest {

    private final BasicJsonTester json =
            new BasicJsonTester(getClass());

    @Test
    void validatesRawPayloadWithoutDeserializingJavaDto() {
        String raw = """
                {
                  "status": "ACCEPTED",
                  "count": 2,
                  "items": [
                    {"sku":"SKU-1"},
                    {"sku":"SKU-2"}
                  ]
                }
                """;

        assertThat(json.from(raw))
                .extractingJsonPathStringValue("@.status")
                .isEqualTo("ACCEPTED");

        assertThat(json.from(raw))
                .extractingJsonPathNumberValue("@.count")
                .satisfies(number ->
                        assertThat(number.intValue()).isEqualTo(2));

        assertThat(json.from(raw))
                .extractingJsonPathStringValue("@.items[1].sku")
                .isEqualTo("SKU-2");
    }

    @Test
    void comparesSemanticJsonRatherThanWhitespace() {
        String raw = """
                {"status":"ACCEPTED","count":2}
                """;

        assertThat(json.from(raw))
                .isEqualToJson("""
                        {
                          "count": 2,
                          "status": "ACCEPTED"
                        }
                        """);
    }
}
```

`BasicJsonTester#from(CharSequence)` accepts **already-existing JSON**. It can read JSON from a `String`, byte array, file, stream, or resource, but it does not have `write(SomeDto)` or `parseObject(...)` like typed marshal testers. Thus it is ideal for testing webhook JSON/raw payloads. At the same time, it **does not prove that a Jackson/Gson/JSON-B mapper built the JSON correctly**, unless the input JSON was actually generated by that mapper in the code under test.

### 5.8. `ManualJacksonTesterTest.java` — usage without `@JsonTest`

```java
// src/test/java/com/example/jsonlab/ManualJacksonTesterTest.java
package com.example.jsonlab;

import java.time.LocalDate;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.json.JacksonTester;

import static org.assertj.core.api.Assertions.assertThat;

class ManualJacksonTesterTest {

    private JacksonTester<ShippingNotice> json;

    @BeforeEach
    void setup() {
        ObjectMapper mapper = new ObjectMapper()
                .findAndRegisterModules();
        JacksonTester.initFields(this, mapper);
    }

    @Test
    void serializesWithExplicitMapperOutsideSpringContext()
            throws Exception {
        ShippingNotice notice = new ShippingNotice(
                502L, "buyer@example.test", 3,
                LocalDate.of(2026, 6, 17), null);

        assertThat(json.write(notice))
                .isEqualToJson("expected-shipping-notice.json");
    }
}
```

`JacksonTester.initFields(this, mapper)` scans the typed tester fields on the test instance and initializes them using the provided mapper. `findAndRegisterModules()` lets the mapper discover Jackson modules on the classpath (including the JavaTime module when present) in this example.

**Important difference:** a manual mapper does not automatically guarantee using **all** Spring Boot customizations of the production `ObjectMapper`. If the contract depends on property naming/visibility/modules configured by the context, use `@JsonTest` or inject the **real mapper bean**; the manual example is useful for isolated tests without Spring.

### 5.9. Run commands and test count of the main project

From the `json-tester-lab` directory (where `pom.xml` resides):

```bash
java -version
mvn -version

mvn test
mvn -Dtest=ShippingNoticeJsonTest test
mvn -Dtest=RawJsonContractTest test
mvn -Dtest=ManualJacksonTesterTest test
```

The main project has **7 JUnit `@Test` methods**: `ShippingNoticeJsonTest` has **4**, `RawJsonContractTest` has **2**, and `ManualJacksonTesterTest` has **1**: **4 + 2 + 1 = 7**.

Expected result: assertions pass when files and dependencies are declared properly. Maven/Surefire/Spring Boot may print different test ordering, runtimes, or logs; there is no fixed stdout to hard-code. `curl` is not needed because there is no HTTP endpoint in the example.

## 6. `JacksonTester`: mapper-aware contract, with JSON view support

### 6.1. When should you choose it?

Choose `JacksonTester<T>` when production uses Jackson and the DTO has any of the following:

- `@JsonProperty` to rename fields.
- `@JsonIgnore`/`@JsonInclude` controlling which fields appear.
- `@JsonFormat`, `JavaTimeModule`, enum format, or timezone.
- Custom `JsonSerializer`/`JsonDeserializer`, mix-ins, or Jackson `Module` beans.
- `@JsonView` when the API exposes public/internal views.
- Configuration from `spring.jackson.*` or `Jackson2ObjectMapperBuilderCustomizer` in a Boot 3.x app.

With Jackson, engine and annotations must match. A test using Gson on the same DTO might **ignore** `@JsonProperty("order_id")` and emit `orderId`, which is not "GsonTester broken" but a real difference between mappers.

### 6.2. `JacksonTester#forView`

If the application uses `@JsonView`, `JacksonTester` provides `forView(ViewClass.class)` to test a specific view. **Illustrative** example, not part of the runnable project since it requires additional DTO and view annotations:

```java
class Views {
    interface Public {}
    interface Internal extends Public {}
}

record Profile(
        @JsonView(Views.Public.class) String displayName,
        @JsonView(Views.Internal.class) String internalNote) {
}

// In a test with JacksonTester<Profile> json:
assertThat(json.forView(Views.Public.class)
        .write(new Profile("Lan", "review-only")))
        .isEqualToJson("""
                {"displayName":"Lan"}
                """);
```

The snippet requires `com.fasterxml.jackson.annotation.JsonView` and AssertJ `assertThat` imports. Whether fields without a view annotation are included also depends on `DEFAULT_VIEW_INCLUSION`. For sensitive data, verify the output schema against the exact security contract, and do not rely on a simplified view example as an authorization mechanism.

### 6.3. Typed marshal tester and resources

`JacksonTester<T>` extends `AbstractJsonMarshalTester<T>`, providing `write(T)`, `parse(String)`, `parseObject(String)`, `read(String)`, and overloads. Distinguish:

- `write(dto)`: serializes a Java DTO, returning `JsonContent<T>` for AssertJ JSON checks.
- `parse(jsonString)`: deserializes and returns `ObjectContent<T>` for object assertions.
- `parseObject(jsonString)`: deserializes and returns `T` directly.
- `read("resource.json")` / resource-reading overloads: useful when large JSON input resides in a fixture.
- `JsonContent#getJson()`: retrieves raw serialized text when byte/text syntax checks or JSON tree parsing are needed.

Fixture filenames normally resolve relative to the test class/package; place resources in the matching package, especially when moving test packages or creating new modules.

## 7. `BasicJsonTester`: right for JSON from any source

`BasicJsonTester` fits when there is no Java DTO to serialize, such as:

- A callback/webhook sending a raw JSON string.
- An API client returning a `String` or `byte[]` response.
- A producer writing JSON via a custom library or template engine.
- A snapshot/fixture file read by another system.
- Checking JSONPath/JSONAssert without choosing Jackson/Gson/JSON-B.

Direct usage:

```java
BasicJsonTester json = new BasicJsonTester(getClass());

assertThat(json.from("""
        {"event":"order.created","orderId":502}
        """))
        .extractingJsonPathStringValue("@.event")
        .isEqualTo("order.created");
```

This is a pattern embedded in a test method and requires the `assertThat` static import. If data already exists as bytes, `json.from(byte[])` can be used. When passing a `String` **ending in `.json`**, the API may treat it as a resource name rather than raw JSON; to avoid ambiguity, use clear JSON content `{...}`/`[...]` or an explicit resource overload.

### 7.1. Do not turn BasicJsonTester into a "Java object parser"

Fundamental difference:

```text
JacksonTester<ShippingNotice> / GsonTester<T> / JsonbTester<T>
              Java object ↔ JSON text

BasicJsonTester
              JSON text/bytes/file → JsonContent<Object> → assertions
```

`BasicJsonTester` carries no generic DTO type, knows nothing about DTO serialization annotations, and does not construct entities from JSON. If a test requires deserializing JSON into a domain object, pick the typed tester matching the engine or use the real mapper.

### 7.2. Choosing JSONPath or structural equality?

- JSONPath is great when only certain fields are part of the contract, or JSON contains dynamic metadata.
- Structural equality is great when the entire payload/schema is a stable contract and fixtures are reviewed.
- For JSON with dynamic timestamps/UUIDs, assert format, presence, correlation, and relationships instead of a fixed snapshot.
- For JSON with secret fields, assert **absence** via parser/tree rather than only checking one public field.
- For arrays, determine whether order belongs to the contract.

## 8. GsonTester: when the application truly uses Gson

Gson is provided by Google, using `com.google.gson.Gson` and annotations like `@SerializedName`. `GsonTester<T>` uses `Gson` to marshal/unmarshal Java objects, while JSON assertions behave similarly to other typed testers.

**Do not add Gson to a Jackson project if production does not use it.** To run the extension below on the same Maven project from section 5, add the dependency in **test scope**:

```xml
<dependency>
    <groupId>com.google.code.gson</groupId>
    <artifactId>gson</artifactId>
    <scope>test</scope>
</dependency>
```

The version is normally managed by the Spring Boot BOM. Gson in test scope suffices for the unit test example; in a real production application using Gson, declare the dependency in the appropriate scope and configure the HTTP converter/mapper accordingly.

### 8.1. Neutral POJO as a shared fixture for Gson and JSON-B

Create file `src/test/java/com/example/jsonlab/GatewayReceipt.java`:

```java
// GatewayReceipt.java
package com.example.jsonlab;

public class GatewayReceipt {
    private String code;
    private int attempts;

    public GatewayReceipt() {
    }

    public GatewayReceipt(String code, int attempts) {
        this.code = code;
        this.attempts = attempts;
    }

    public String getCode() {
        return code;
    }

    public void setCode(String code) {
        this.code = code;
    }

    public int getAttempts() {
        return attempts;
    }

    public void setAttempts(int attempts) {
        this.attempts = attempts;
    }
}
```

The POJO has a no-arg constructor, getters/setters, and simple fields so both Gson and JSON-B handle it easily. Do not use the Jackson record `ShippingNotice` as "proof" that every engine has identical record/annotation support.

### 8.2. `GsonTesterTest.java` — manual initFields, without Spring

```java
// src/test/java/com/example/jsonlab/GsonTesterTest.java
package com.example.jsonlab;

import com.google.gson.Gson;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.json.GsonTester;

import static org.assertj.core.api.Assertions.assertThat;

class GsonTesterTest {

    private GsonTester<GatewayReceipt> json;

    @BeforeEach
    void setup() {
        Gson gson = new Gson();
        GsonTester.initFields(this, gson);
    }

    @Test
    void serializesUsingGson() throws Exception {
        GatewayReceipt receipt =
                new GatewayReceipt("OK", 2);

        assertThat(json.write(receipt))
                .isEqualToJson("""
                        {"code":"OK","attempts":2}
                        """);
    }

    @Test
    void deserializesUsingGson() throws Exception {
        GatewayReceipt actual = json.parseObject("""
                {"code":"DONE","attempts":3}
                """);

        assertThat(actual.getCode()).isEqualTo("DONE");
        assertThat(actual.getAttempts()).isEqualTo(3);
    }
}
```

Because this is a pure JUnit test, `GsonTester.initFields(this, gson)` explicitly supplies the engine to the tester without `@JsonTest`. The test verifies JSON against Gson defaults in the example, but **does not** automatically test `GsonBuilderCustomizer`/`spring.gson.*` in the real application.

### 8.3. When using `@JsonTest` for Gson

In an application genuinely using Gson, once Gson dependencies and auto-configuration are ready, you can write:

```java
@JsonTest
class GsonContractSliceTest {
    @Autowired
    GsonTester<GatewayReceipt> json;

    // @Test methods verifying json.write and json.parseObject...
}
```

This is an annotation template, not a runnable file in the main project. A `@JsonTest` is helpful when you need to verify the Boot-configured mapper. Do not assume adding a Gson dependency **forces** MVC/WebFlux to switch to Gson; HTTP converters have separate selection/configuration rules.

### 8.4. How does Gson differ from Jackson?

- Field-renaming annotation: Gson uses `@SerializedName("order_id")`; Jackson uses `@JsonProperty("order_id")`.
- Naming/exclusion/field visibility may differ.
- Java Time, polymorphic mapping, null inclusion, and adapter behavior may differ.
- Gson serializes fields by default, whereas Jackson typically relies on properties/annotations.
- A DTO passing `GsonTester` does not prove compatibility with `ObjectMapper`.

**Annotation difference example (illustrative only):**

```java
class Example {
    @SerializedName("order_id")
    long orderId;
}
```

This snippet requires `import com.google.gson.annotations.SerializedName`; do not add it to main source if Gson is not used. It represents a Gson-specific contract. For JSON-B, the corresponding annotation belongs to the `jakarta.json.bind.annotation` namespace.

## 9. JsonbTester: with Jakarta JSON Binding (JSON-B)

JSON-B is an API for Java object ↔ JSON conversion. Spring Boot includes auto-configuration support when the **JSON-B API and a compatible implementation** are on the classpath. A common implementation is Eclipse Yasson.

To run this extension in the project, add to `pom.xml`:

```xml
<dependency>
    <groupId>jakarta.json.bind</groupId>
    <artifactId>jakarta.json.bind-api</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.eclipse</groupId>
    <artifactId>yasson</artifactId>
    <scope>test</scope>
</dependency>
```

`Yasson` requires a compatible Jakarta JSON-P provider at runtime (usually pulled via the provider's dependency graph). If you encounter a "provider not found" error, inspect the dependency tree/versions and add the appropriate JSON-P provider per Yasson's documentation; do not confuse the JSON-B API with its implementation.

### 9.1. `JsonbTesterTest.java` — explicit creation and closing of Jsonb

```java
// src/test/java/com/example/jsonlab/JsonbTesterTest.java
package com.example.jsonlab;

import jakarta.json.bind.Jsonb;
import jakarta.json.bind.JsonbBuilder;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.json.JsonbTester;

import static org.assertj.core.api.Assertions.assertThat;

class JsonbTesterTest {

    private Jsonb jsonb;
    private JsonbTester<GatewayReceipt> json;

    @BeforeEach
    void setup() {
        jsonb = JsonbBuilder.create();
        JsonbTester.initFields(this, jsonb);
    }

    @AfterEach
    void cleanup() throws Exception {
        if (jsonb != null) {
            jsonb.close();
        }
    }

    @Test
    void serializesUsingJsonb() throws Exception {
        GatewayReceipt receipt =
                new GatewayReceipt("OK", 2);

        assertThat(json.write(receipt))
                .isEqualToJson("""
                        {"code":"OK","attempts":2}
                        """);
    }

    @Test
    void deserializesUsingJsonb() throws Exception {
        GatewayReceipt actual = json.parseObject("""
                {"code":"DONE","attempts":3}
                """);

        assertThat(actual.getCode()).isEqualTo("DONE");
        assertThat(actual.getAttempts()).isEqualTo(3);
    }
}
```

`JsonbTester.initFields(this, jsonb)` initializes the tester using the exact `Jsonb` instance created. Unlike code using Spring injection, the unit test is responsible for creating and closing JSON-B resources.

**Note:** `JsonbTester` uses the Jakarta namespace `jakarta.json.bind.*` with Spring Boot 3.x. Do not copy `javax.json.bind.*` imports from a legacy Java EE project without checking versions.

### 9.2. JSON-B annotations are not automatically equivalent to Jackson annotations

```java
class Example {
    @JsonbProperty("order_id")
    public long orderId;
}
```

This is an illustrative snippet requiring `jakarta.json.bind.annotation.JsonbProperty`, not part of the main runnable code. `@JsonbProperty` is understood by JSON-B; Jackson's `@JsonProperty` and Gson's `@SerializedName` are three distinct annotation systems.

If a service truly uses JSON-B, check the exact `JsonbConfig`, visibility, adapters, date/time formatting, and runtime provider. Do not use another mapper's tester to "pass" a schema on paper only.

### 9.3. When using `@JsonTest` for JSON-B

When the provider/API is on the classpath and Spring Boot auto-configures `Jsonb`, you can inject:

```java
@JsonTest
class JsonbContractSliceTest {
    @Autowired
    JsonbTester<GatewayReceipt> json;
}
```

This is an annotation template, not a complete test class. The project in section 5 does not include Gson/Jsonb in the base POM; they only become runnable after adding the extension dependencies. For projects needing multiple engines, separate test classes and explicitly pick the mapper under test rather than assuming HTTP converters automatically switch.

## 10. Running all examples, separating base and extensions

### 10.1. Base project

Using only the POM in section 5 and the three base test classes:

- `ShippingNoticeJsonTest`: 4 tests.
- `RawJsonContractTest`: 2 tests.
- `ManualJacksonTesterTest`: 1 test.

Result: **7 tests** with only these classes. There are no Gson or JSON-B dependencies in the base POM, so do not copy the two extension classes into source without adding the dependencies.

### 10.2. When practicing all three engines

Add the three test-scope dependencies from sections 8–9 (Gson, JSON-B API, Yasson), add `GatewayReceipt.java` and the two test classes `GsonTesterTest` and `JsonbTesterTest` into the proper package.

```bash
# Ensure Maven downloads all dependencies and compiles test sources:
mvn -B test

# Run each engine separately:
mvn -Dtest=ShippingNoticeJsonTest test
mvn -Dtest=GsonTesterTest test
mvn -Dtest=JsonbTesterTest test
mvn -Dtest=RawJsonContractTest test
```

When adding the two extension test classes, the total number of `@Test` methods is **11**: 7 base + 2 Gson + 2 JSON-B. However, passing depends on compatible dependencies/JSON-B provider setup; if Maven reports a provider or module error, fix the dependency graph instead of swapping `JsonbTester` for `JacksonTester` to "bypass" the test.

### 10.3. What the tests do and do not prove

| Test | What is verified | What is not verified |
| --- | --- | --- |
| `ShippingNoticeJsonTest` | Spring JSON slice with Jackson mapper and DTO contract | HTTP route/status, network serialization in other contexts |
| `RawJsonContractTest` | Raw JSON payload and JSONPath | How the payload was generated from a Java object |
| `ManualJacksonTesterTest` | Jackson serialization with a manually created mapper | All Boot-specific mapper customizers |
| `GsonTesterTest` | JSON per test's default Gson | Whether the production app uses a Gson converter |
| `JsonbTesterTest` | JSON per test's Jsonb/Yasson | Production runtime provider/config if different |
| Separate MVC/WebFlux integration test | Endpoint returning JSON via real converter in web context | External gateway/proxy/consumer if not set up |

**Be transparent about scope:** `@JsonTest` is a slice for JSON mappers; testing the entire HTTP boundary is an additional layer. A passing JSON fixture does not by itself confirm endpoint routing, validation, exception handling, or content negotiation work properly.

## 11. Defining expected values so tests are not "false green"

### 11.1. Expected must be independent of actual

An anti-pattern:

```java
String actualJson = json.write(dto).getJson();
assertThat(json.write(dto)).isEqualToJson(actualJson);
```

This merely compares the output with the output just generated, establishing no correctness standard. If the mapper accidentally changes `order_id` to `orderId`, it can still pass.

Better:

```java
assertThat(json.write(dto))
        .isEqualToJson("""
                {
                  "order_id": 502,
                  "recipient": "buyer@example.test",
                  "quantity": 3,
                  "shipOn": "2026-06-17"
                }
                """);
```

This is a snippet used inside a test with `json` and `dto` prepared; the expected value is specified independently by the author from the contract.

### 11.2. Do not force output to match every whitespace

If the receiver simply reads a JSON object, the representations:

```json
{"a":1,"b":2}
```

and

```json
{
  "b": 2,
  "a": 1
}
```

are normally structurally equivalent. Use `isEqualToJson` or a JSON tree instead of `assertThat(raw).isEqualTo(...)` when whitespace/key order are not part of the contract.

**Exception:** when signing a message with HMAC over serialized bytes, content hashing/canonicalization, or a protocol requiring exact ordering, compare bytes and encoding explicitly. `isEqualToJson` is not sufficient to prove byte-for-byte signatures.

### 11.3. Do not assert only round-trip

`json.parseObject(json.write(dto).getJson()).equals(dto)` can pass even if both serializer and deserializer rename a field in the same wrong way. You must have a **golden fixture** or field-level assertions based on the public schema.

### 11.4. Do not check internal fields only via `contains`

JSON with `"password":"***"` and JSON with `"password":"secret"` both contain the string `password`. To guarantee no leak, assert the field is **absent or masked** per the exact policy, and inspect nested objects if allowed by the schema.

For example, in a Jackson JSON parser:

```java
JsonNode root = mapper.readTree(json.write(dto).getJson());
assertThat(root.has("password")).isFalse();
```

This is a pattern embedded in a test; it requires an actual DTO with a password field if you truly want to guard that use case. With JSON-B/Gson, use the corresponding parser or `BasicJsonTester`/JSONPath to inspect the payload. Never use real secrets in fixtures.

## 12. Tricky corners of JSON serialization

### 12.1. Date/time and timezone

In `ShippingNotice`, `shipOn` is a `LocalDate`, carrying no timezone. It has an explicit `yyyy-MM-dd` format.

For `Instant`, `OffsetDateTime`, or `ZonedDateTime`, you must decide the contract:

- UTC ISO-8601?
- Epoch milliseconds or seconds?
- Fractional seconds included?
- Preserve original offset or normalize?
- Convert timezone per user locale?

Tests need **fixed timestamps** and exact expected fixtures; do not use `Instant.now()` and expect serialization and assertions to match down to the nanosecond. A manually created mapper without Java Time support can throw `InvalidDefinitionException`; use a Boot-configured mapper or the appropriate module.

### 12.2. Enum naming

An API has an enum `PENDING_APPROVAL` while consumers expect `"pendingApproval"`. Jackson `@JsonValue`, Gson adapters, and JSON-B adapters each have their own mechanisms. Write both serialize **and** deserialize tests with the exact string sample; do not treat default `enum.name()` as the final contract.

### 12.3. Null/missing/default values

- A missing object property and an explicit null are different.
- Primitive Java `int` cannot represent null like `Integer`.
- A Java record with strict constructor validation can throw when Jackson deserializes.
- Gson/JSON-B have their own default/unknown-field strategies.
- JSON schema validation and Bean Validation do not automatically run just by calling `json.parseObject`; `@Valid` in a controller is a separate layer.

To test a missing required field, you can test `assertThatThrownBy(() -> json.parseObject(payload))` **if the mapper/DTO is configured to reject it**. Do not write tests expecting Jackson to always fail on every missing field; by default many field types can receive null/zero.

### 12.4. Numeric precision

JSON numbers `12.50` and `12.5` can have the same mathematical value but different scales in Java `BigDecimal`. When unit-testing money, clarify: does the contract require numeric equivalence, fixed two-decimal formatting, or a string amount? If a JSON signature or downstream schema requires 2 decimal places, test the raw representation/`JsonNode` decimal node in a way that preserves scale. Do not convert currency amounts to `double` and assert approximately if money has exact decimal rules.

### 12.5. Collections and order

If JSON output contains a chronologically ordered list, assert elements in order. If object field order is not part of the contract, do not enforce order. If a `Map` is serialized and consumers only look up keys, test based on structural equality rather than an accidental iteration order.

### 12.6. Polymorphism and type information

Jackson `@JsonTypeInfo`, custom subtypes, Gson `TypeAdapter`, and JSON-B adapters control how an interface/abstract field is encoded/decoded. Testing a simple DTO does not protect polymorphic cases. When an object graph has subtypes, use fixtures containing the type discriminator, verify valid type allowlists, and avoid enabling unsafe default typing just to make tests pass.

### 12.7. Generics such as `List<Dto>`

`JacksonTester<List<MyDto>>` can be initialized with full generic type information from the field via the test infrastructure. If creating a mapper manually, `TypeReference<List<MyDto>>`/`ResolvableType` must be handled properly. Do not deserialize `List<Dto>` by casting through a raw `List` and claim element types were verified after deserialization.

### 12.8. Escaping and Unicode

JSON strings must validly encode quotes, backslashes, and control characters. The Java record test in section 5 puts Vietnamese text and quotes into `note`, verifying round-trip. If a system consumes JSON in a specific charset or signs raw bytes, test the actual encoding at the HTTP/message boundary.

### 12.9. Unknown fields, backward compatibility

A new provider may add fields. Mappers may ignore unknown fields or fail, depending on configuration. Choose an explicit policy:

- Should a public API be forward-compatible with extra fields? Test decoding input with extra fields.
- Does a sensitive command input need strict validation? Test unknown/missing/duplicate fields per policy.
- Does a versioned event use schema evolution? Test v1/v2 fixtures and consumer defaults.

Do not assume every JSON tester always ignores unknown fields: Jackson/Gson/JSON-B have different defaults and custom settings.

## 13. JSON fixtures and snapshots: managing them reliably

### 13.1. When to save `expected.json`?

Fixtures are helpful for large payloads, nested arrays, required fields, and stable schemas. They are easier to review in pull requests than long escaped strings.

Rules:

1. Place in `src/test/resources` matching the package if using resource-relative lookup.
2. Use synthetic values, containing no real customer data or tokens.
3. Keep fixtures **independent** of the actual serializer; if updating a snapshot, review why it changed.
4. Name files to reflect the contract: `order-created-v1.json`, `payment-captured-v2.json`.
5. For schema evolution, keep some fixtures of older versions when backward compatibility is required.
6. Do not make updating fixtures an automatic action whenever tests turn red; that could be a regression.

### 13.2. `isEqualToJson` does not replace JSON Schema

Comparing against one fixture proves **one example**. It does not prove all possible values, all required/optional fields, or valid ranges. If the contract requires JSON Schema/OpenAPI, add schema validation or contract testing at the appropriate layer; testers remain useful for typical/boundary cases.

### 13.3. How to review diffs

When a test fails, classify it:

- **Wrong field name:** mapper annotation/naming strategy changed.
- **Wrong value:** domain mapping/rounding/timezone error.
- **Extra/missing field:** include/exclude/visibility/optional semantics changed.
- **Different array order:** collection sorting/contract order changed.
- **Wrong type:** number vs string, object vs array, null vs omitted.
- **Wrong or outdated fixture:** requirements changed, needing a versioning/compatibility decision.

Only update expected values when the contract genuinely changes; do not auto-accept new output just to make the test green.

## 14. How do `@JsonTest`, `@WebMvcTest`, and `@SpringBootTest` differ?

| Purpose | Annotation/tool | What is tested | What is not tested |
| --- | --- | --- | --- |
| Test DTO serializer/mapper | `@JsonTest` + `JacksonTester`/Gson/Jsonb | Mapper, modules, JSON fields | HTTP routing, status/headers |
| Test external raw JSON | `BasicJsonTester` | JSONPath/structural JSON contract | Which mapper produced the payload |
| Controller returning status/body with mocked service | `@WebMvcTest` + `MockMvc` | MVC mapping, HTTP response serialization in slice | Real service logic when mocked |
| Real service + controller with mocked HTTP | `@SpringBootTest(MOCK) + @AutoConfigureMockMvc` | Integration bean graph/mapping/response | Embedded HTTP listener/network |
| Real HTTP server | `@SpringBootTest(RANDOM_PORT)` + HTTP client | Servlet/reactive server and JSON response over socket | External production ingress/CDN if absent |
| External provider schema/contract | HTTP stubs, Pact/OpenAPI/schema tests | Consumer/provider compatibility | Full E2E production flow |

Common point of confusion: `@JsonTest` uses the real `ObjectMapper` but **does not automatically guarantee** the HTTP controller configuration shares the same converters/visibility/profile as the full running app. Some customizations are picked up by the slice; some app-specific `@Configuration` classes need importing. When serialization is an important public contract, include **some** HTTP boundary tests to protect real wiring.

## 15. Troubleshooting: common issues when using JSON testers

### Issue A. `@Autowired JacksonTester<Dto>` is not created

**Likely cause:** missing `@JsonTest`/test auto-configuration, missing Jackson dependency, generic field not initialized, or test not running with Spring TestContext.

**Fix:** check `spring-boot-starter-test`, `@JsonTest`, and `spring-boot-starter-json`; if avoiding a Spring context, call `JacksonTester.initFields(this, mapper)` in `@BeforeEach`.

### Issue B. `ObjectMapper` cannot handle `LocalDate`

**Likely cause:** you used `new ObjectMapper()` without registering the JavaTime module.

**Fix:** use `@JsonTest`'s mapper, or `new ObjectMapper().findAndRegisterModules()` when the module is on the classpath; do not arbitrarily stringify dates just to make tests pass.

### Issue C. Added `@JsonProperty` but Gson output still uses the old name

**Cause:** `@JsonProperty` belongs to Jackson; Gson uses `@SerializedName`/Gson configuration.

**Fix:** choose the right tester for the engine or use the appropriate mapping annotation. If the app is supposed to use Jackson, the bug is **engine selection/config**, not "wrong test data."

### Issue D. JSON-B reports "provider not found"

**Cause:** JSON-B API is present without a compatible implementation/JSON-P provider.

**Fix:** add Eclipse Yasson and the required Jakarta JSON-P provider dependency, align versions with the BOM, and inspect the dependency tree. Do not use legacy `javax.json.bind` in Boot 3.x.

### Issue E. `isEqualToJson("fixture.json")` cannot find the file

**Cause:** fixture is not on the classpath/package relative to the test, filename/path is wrong, or resources were not copied by the build.

**Fix:** place under `src/test/resources/com/example/jsonlab/` matching the package with the exact filename; if needed, use an explicit resource path overload.

### Issue F. Numeric JSONPath assertion fails even though `3 == 3` numerically

**Cause:** `Number` is returned as `Integer`/`Long`/`BigDecimal`, differing in type from expected.

**Fix:** use `satisfies(n -> assertThat(n.intValue()).isEqualTo(3))` for integer semantics, or check decimals per policy. Do not force numbers into strings to dodge types.

### Issue G. Test passes solely because of round-trip

**Cause:** expected was taken from actual, or both serialize and deserialize share the same mapping bug.

**Fix:** add an independent expected fixture/schema, key field-level assertions, and negative cases.

### Issue H. Jackson test passes but HTTP response differs

**Cause:** MVC converter uses a different mapper/config, custom configuration is missing from `@JsonTest`, or content negotiation alters format.

**Fix:** verify mapper beans and custom modules in the corresponding context; add `@WebMvcTest`/`MockMvc` or an HTTP integration test for the endpoint.

### Issue I. Same DTO produces different JSON across Gson, JSON-B, and Jackson

**Cause:** engines have different naming/visibility/annotation support.

**Fix:** define the contract per real engine and test each engine separately if warranted; do not apply one expected payload when schemas intentionally differ.

### Issue J. Null field appears unexpectedly

**Cause:** default inclusion policy or annotation/configuration not applied to the mapper in use.

**Fix:** write concrete missing-vs-null tests, checking `JsonInclude`, Gson `serializeNulls`, or JSON-B config per engine.

### Issue K. Test loads the entire application and requires a database

**Cause:** using `@SpringBootTest` instead of `@JsonTest` when only the mapper is needed.

**Fix:** pick the JSON slice and import only the necessary custom module instead of the entire application. If the goal requires mapper wiring in the full context, use a test database/fake outbound ports, never production credentials.

### Issue L. JSON payload contains secrets in failure logs

**Cause:** assertion prints the entire payload containing real tokens/passwords/PII.

**Fix:** use synthetic fixtures, redact sensitive fields, and limit test artifacts; never put production data into tests for debugging.

## 16. Code review checklist for JSON tests

- [ ] Real engine identified: Jackson, Gson, JSON-B, or raw JSON text.
- [ ] Correct `JacksonTester`/`GsonTester`/`JsonbTester`/`BasicJsonTester` chosen.
- [ ] With `@JsonTest`, verified necessary mapper modules/customizations are actually in the slice.
- [ ] With manual testers, called `initFields` using a compatible mapper.
- [ ] Includes **Java → JSON** assertions on field names, data types, values, and omitted fields.
- [ ] Includes **JSON → Java** assertions when the app receives JSON input.
- [ ] Expected values are independent fixtures/contracts, not comparing output against itself.
- [ ] Structural JSON equality is used when whitespace/object key order is not part of the contract.
- [ ] Array order is checked when order is important.
- [ ] Missing, null, empty string, and unknown fields have matching policies/tests.
- [ ] Date/time/timezone, enums, `BigDecimal`, and Unicode/escaping have cases where relevant.
- [ ] Sensitive data is **excluded** and does not leak into logs/fixtures.
- [ ] Tests do not confuse a passing mapper with a passing HTTP endpoint.
- [ ] Does not start a real DB/broker/network when only testing JSON conversion.
- [ ] If production uses a different converter, an HTTP boundary test confirms the real engine.
- [ ] Fixtures are versioned/reviewed alongside the public contract.

## 17. Practice exercises

### Exercise 1: Catch wrong field renaming

Temporarily change `@JsonProperty("order_id")` to `@JsonProperty("orderId")` on a scratch branch. Run `ShippingNoticeJsonTest`. Which tests do you expect to fail?

**Answer hint:** `isEqualToJson("expected-shipping-notice.json")` fails schema matching, and the assertion checking the JSON tree has no `orderId` also fails.

### Exercise 2: Missing differs from null

Try removing `@JsonInclude(NON_NULL)` from `note`, then check whether the generated JSON contains the `note` field. Write an assertion confirming the "omit field if null" contract using `mapper.readTree`/`has("note")`. If the mapper has a global `NON_NULL` policy, understand that config before concluding the annotation alone controls it.

### Exercise 3: Gson annotation

Create a separate DTO with `@SerializedName("order_id")` and write a `GsonTester` test verifying key `order_id` and no `orderId` key. Do **not** use `@JsonProperty` and expect Gson to rename it.

### Exercise 4: JSON-B field naming

Create a JSON-B POJO with `@JsonbProperty("order_id")` and write a `JsonbTester` test asserting output. Check the differences if you replace the DTO with a Java record, especially on the real JSON-B provider/version in use.

### Exercise 5: Webhook JSON payload

Given a JSON string with `eventType`, `aggregateId`, and `items[]`, use `BasicJsonTester#from(payload)` to assert types/strings and an item via JSONPath. Add a payload case missing `aggregateId`; decide whether this is an invalid-schema test or just a field-absence assertion.

### Exercise 6: JSON API response

Add a controller returning `ShippingNotice`. Use `@WebMvcTest` + `MockMvc` to assert the JSON response has `order_id`, `shipOn`, and no `note`. This proves the JSON engine/wiring in the MVC slice produces the right HTTP response, not just `JacksonTester`.

## 18. Self-check questions

**1.** When should you choose `BasicJsonTester` instead of `JacksonTester`?

**Answer:** When the data under test is JSON text/bytes/file already produced by any source, without needing to serialize/deserialize a Java DTO with Jackson.

**2.** Does `@JsonTest` automatically download the Gson dependency from Maven?

**Answer:** No. It auto-configures support for JSON libraries already present based on classpath/conditions. Dependencies are declared by the project.

**3.** Does using `GsonTester` to test a DTO containing `@JsonProperty("order_id")` guarantee `order_id` output?

**Answer:** No. `@JsonProperty` belongs to Jackson; Gson has its own annotation/configuration such as `@SerializedName`.

**4.** Why can `JacksonTester.initFields(this, new ObjectMapper())` differ from `@JsonTest`?

**Answer:** A manually created mapper lacks Boot customizations, Java Time modules, naming/visibility rules, or serializers registered by the Spring context. If app config is needed, use the mapper bean or the auto-configured JSON slice.

**5.** Should you write `assertThat(json.write(dto).getJson()).isEqualTo(expectedRawString)`?

**Answer:** Only when whitespace/key order/raw bytes are genuinely part of the contract. Otherwise, compare JSON structure or JSONPath.

**6.** What does `JsonbTester` require besides `jakarta.json.bind-api`?

**Answer:** It requires a compatible JSON-B implementation/provider such as Eclipse Yasson along with the corresponding JSON-P dependency. The API alone is just interfaces.

**7.** Does a passing `@JsonTest` prove `GET /api/orders` returns status 200?

**Answer:** Not yet. It protects the mapper; HTTP routing/status must be tested using MVC/WebFlux/server integration tests.

**8.** Is a passing `parseObject(write(dto))` round-trip enough?

**Answer:** Not enough: both serialization and deserialization can share the same field-naming bug. An independent expected schema/fixture is required.

**9.** JSONPath returns `Number`; should you cast to `Long` in every case?

**Answer:** No. Choose comparisons matching the required numeric semantics or check the exact type per contract, avoiding brittle matchers caused solely by numeric wrappers.

**10.** Should you test that `password` is not leaked by asserting JSON contains `"password":null`?

**Answer:** Only if the contract genuinely allows that field to appear as null. Usually secret data must not appear even as null; verify field absence using a JSON tree/schema.

## 19. Official Documentation

- [Spring Boot 3.5 – Auto-configured JSON Tests](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html#testing.spring-boot-applications.autoconfigured-json-tests): `@JsonTest`, Jackson/Gson/Jsonb/Basic testers, `initFields`, and JSONPath.
- [Spring Boot 3.5 – Test JSON package](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/json/package-summary.html): `JacksonTester`, `GsonTester`, `JsonbTester`, `BasicJsonTester`.
- [Spring Boot 3.5 – JacksonTester Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/json/JacksonTester.html): `write`, `parseObject`, `initFields`, `forView`.
- [Spring Boot 3.5 – JsonbTester Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/json/JsonbTester.html): `JsonbTester.initFields` and JSON-B support.
- [Spring Boot 3.5 – AutoConfigureJsonTesters Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/json/AutoConfigureJsonTesters.html): controlling registration.
- [Spring Boot 3.5 – Test Auto-configuration Slices](https://docs.spring.io/spring-boot/3.5/appendix/test-auto-configuration/slices.html): beans/auto-configurations of the JSON slice.
- [Jackson Annotations](https://github.com/FasterXML/jackson-annotations): `@JsonProperty`, `@JsonFormat`, `@JsonInclude`.
- [Gson User Guide](https://github.com/google/gson/blob/main/UserGuide.md): Gson engine and annotations/adapters.
- [Jakarta JSON Binding Specification](https://jakarta.ee/specifications/jsonb/): `Jsonb` API, naming/serialization, and providers.

**Conclusion:** To test JSON effectively, **choose the tester matching the right engine and boundary**. `JacksonTester`, `GsonTester`, and `JsonbTester` protect Java object ↔ JSON conversion for a mapper; `BasicJsonTester` protects existing JSON as a string/bytes. `@JsonTest` tests the JSON mapper inside a Spring slice, while HTTP tests verify the application's converters and responses. Always use independent expected values, check field names/types/values/absent fields, and never mistake a passing round-trip for a passing contract.
