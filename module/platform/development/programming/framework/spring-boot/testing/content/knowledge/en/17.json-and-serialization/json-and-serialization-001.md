# `@JsonTest` and Serialization Support Scope in Spring Boot

When building a REST API, an application frequently converts back and forth between **Java objects** and **JSON**. Bugs can occur right in the conversion layer: incorrectly renaming `productId` to `product_id`, omitting fields, outputting `null` outside the contract, turning dates into timestamps, serializing monetary amounts incorrectly, or forgetting to register a custom serializer. These errors can be detected **without starting an HTTP server or database**.

Spring Boot provides **`@JsonTest`**, a **test slice** focused on JSON serialization/deserialization. It loads the JSON mapper and related JSON customization components, while restricting out-of-scope beans. With **Jackson** on Spring Boot 3.5, `JacksonTester<T>` is typically used to test `write` and `parseObject`; when using other libraries, `GsonTester<T>` and `JsonbTester<T>` are available; `BasicJsonTester` supports assertions on JSON strings.

This lesson covers **the mechanism, bean-loading scope, how to test strict JSON contracts, a complete Java 17+ example with `@JsonComponent`, what `@JsonTest` does not prove**, and the differences between Spring Boot 3.x and 4.x.

## 1. What does JSON serialization/deserialization prove?

There are two data directions:

```text
                        serialize / write
Java record / DTO --------------------------------> JSON text
        ^                                              |
        |                                              |
        +----------------------------------------------+
                       deserialize / read
```

**Serialization** is converting a Java value into JSON. **Deserialization** is converting JSON into the expected Java type. An API contract may specify field names, types, numeric precision, date/time formats, field presence conditions, element ordering **in an array**, error policies, and the ability to read data from older versions.

| Risk | Appropriate evidence in `@JsonTest` |
|---|---|
| Field renaming per wire contract | `@JsonProperty`, assert exact JSON key |
| Is `null` omitted or retained? | `@JsonInclude`, assert the field is **absent**, not merely set to null |
| `LocalDate`, `Instant`, zone/offset | `@JsonFormat` and appropriate mapper/module, assert JSON string and round-trip |
| Numeric data `int`, `long`, `BigDecimal` | Assert JSON number/string, precision, and parsed-back value |
| Custom serializer/deserializer | Test that `@JsonComponent` or Jackson `Module` is actually registered in the slice |
| Correctly ordered array | Compare JSON array using the appropriate comparison mode |
| Valid/invalid JSON input syntax | `parseObject` succeeds or throws a parse error |
| Unknown field/required/default semantics | Test actual mapper config and DTO behavior |
| HTTP status, `Content-Type`, routing, security | **Outside the scope of `@JsonTest`**; requires `@WebMvcTest`/`@WebFluxTest` or `@SpringBootTest` |
| Controller → service → repository or DB | **Outside the scope of `@JsonTest`**; requires multi-layer testing |

A "green" `@JsonTest` only confirms **JSON mapping** under the loaded configuration. It does not guarantee that the controller returns the right DTO, that security filters permit the request, or that the API uses the right Jackson mapper when the system has multiple custom-configured mappers.

## 2. How does `@JsonTest` actually create the context?

Imports in **Spring Boot 3.5**:

```java
import org.springframework.boot.test.autoconfigure.json.JsonTest;
import org.springframework.boot.test.json.JacksonTester;

@JsonTest
class ProductJsonTest {
    @Autowired
    JacksonTester<ProductPayload> json;
}
```

This snippet is only a test skeleton; `ProductPayload` and test methods will be fully defined below.

**Mechanism:**

1. The annotation includes Spring Boot's `SpringExtension`/bootstrapper so JUnit Jupiter runs tests in the **Spring TestContext**.
2. `@OverrideAutoConfiguration(enabled = false)` restricts standard auto-configuration; `@ImportAutoConfiguration` and the necessary JSON configurations are selected based on the classpath.
3. With Jackson 2 in Boot 3.5, beans such as **`ObjectMapper`**, `@JsonComponent` classes, and matching Jackson **`Module`** beans are configured/registered.
4. Spring Boot creates JSON tester fields so `@Autowired JacksonTester<ProductPayload>` works, provided the relevant mapper is present.
5. The slice's component scan filter usually **does not load regular `@Service`, `@Repository`, or `@Controller` beans** merely because they are in the same package.

**`@JsonTest` does not start an embedded web server.** Nor does it load a full application graph like `@SpringBootTest`. Therefore, if a serializer depends on a regular service, it may be missing a bean in the slice: evaluate whether that dependency is genuinely needed for JSON mapping, or provide a small, intentional configuration using `@Import`/`@TestConfiguration`. Do not import the entire system just to test a JSON field.

### Support levels depending on the JSON library

| Library | Components used | Tester |
|---|---|---|
| **Jackson 2**, Spring Boot 3.5 | `com.fasterxml.jackson.databind.ObjectMapper`; `@JsonComponent`; Jackson `Module` | `JacksonTester<T>` |
| **Gson** when matching dependency is present | `com.google.gson.Gson` with related configuration | `GsonTester<T>` |
| **JSON-B** when matching provider/dependency is present | `jakarta.json.bind.Jsonb` | `JsonbTester<T>` |
| **Arbitrary JSON string** | Does not require knowing the Java DTO or mapper | `BasicJsonTester` |
| **Jackson 3 / Boot 4.x** | New APIs, mappers, and custom components of the Boot 4 line | Check documentation and exact version dependencies; do not assume Jackson 2 examples transfer verbatim |

The testers are **AssertJ-based** utilities, not identical to Spring MVC `HttpMessageConverter`. Having `JacksonTester` does not mean an HTTP endpoint has been registered.

### Note on `@AutoConfigureJsonTesters`

`@JsonTest` already includes JSON tester configuration. The `@AutoConfigureJsonTesters` annotation allows adjusting this behavior, for example `enabled = false` when you do not want tester fields created. **Disabling testers does not disable the entire JSON mapper**; mapper configuration depends on the loaded auto-configurations. Normally, you do not need to add this annotation if you are only writing basic serialization tests.

## 3. Common JSON testing API

With Jackson in Spring Boot 3.5:

```java
@Autowired
private JacksonTester<ProductPayload> json;

// Object -> JSON content
var actual = json.write(payload);

// JSON string -> Object
ProductPayload restored = json.parseObject(content);
```

This is an illustrative snippet placed inside a `@JsonTest`; `payload` and `content` are declared by the test method. `write`/`parseObject` may throw `IOException` on mapping failures.

Commonly used assertions:

| Check | Example | Meaning |
|---|---|---|
| Entire JSON against contract | `assertThat(json.write(value)).isEqualToJson("expected.json")` | Compares against JSON resource; defaults to **lenient** comparison |
| Disallow extra fields | `isEqualToJson(expected, JSONCompareMode.STRICT)` | Strict mode: disallows extra fields; array order matters |
| JSONPath exists and is a string | `hasJsonPathStringValue("@.product_id")` | Checks type and presence at path |
| Read a specific value | `extractingJsonPathStringValue("@.product_id").isEqualTo("BOOK-1")` | Checks the content of the field |
| Field does not appear | `doesNotHaveJsonPath("@.note")` | Distinguishes **absent** from `"note":null` |
| Parse object | `assertThat(json.parseObject(input)).isEqualTo(expectedDto)` | Checks deserialization by object equality |
| Malformed JSON input | `assertThrows(IOException.class, () -> json.parseObject("{"))` | Parser rejects invalid JSON syntax |

**`JSONCompareMode.STRICT` does not require keys in a JSON object to be in the same character order**, because object key order is not part of the standard contract; however, element order in a JSON array is significant. The default lenient mode in JSONAssert may ignore **extra fields** and may not enforce array order. When testing API contracts that prohibit unexpected fields, intentionally use strict comparison.

When comparing JSON using raw string `assertEquals("{...}", output)`, tests can fail solely due to **object key ordering or whitespace** even though the JSON is validly equivalent. For standard JSON contracts, prefer structural JSON assertions; raw string comparison is only appropriate when **byte-for-byte exactness** is the risk to test (for example, digitally signed payloads or custom canonical JSON).

## 4. Complete Java 17+ example: DTO, dates, null, and custom serializer

We have response DTOs for a product and an invoice:

- `ProductPayload` has Java field `productId`, but the JSON key must be **`product_id`**.
- `availableOn` is a `LocalDate` serialized in **`yyyy-MM-dd`** format.
- `note = null` must **not appear** in JSON due to `@JsonInclude(NON_NULL)`.
- `InvoiceView` contains `Money`; a **`@JsonComponent` serializer** intentionally converts `Money(150000)` into the JSON string **`"150000 VND"`** to illustrate custom mapping.

Formatting money as a string is a technical example, **not a recommended production wire contract**: financial APIs typically require explicit amount and currency unit fields, with defined precision and rounding rules. In real systems, design the contract first before writing the serializer.

### 4.1. Project structure

```text
json-slice-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/json/
    │   ├── JsonLearningApplication.java
    │   ├── ProductPayload.java
    │   ├── Money.java
    │   ├── InvoiceView.java
    │   └── MoneySerializer.java
    └── test/
        ├── java/com/example/json/
        │   ├── ProductPayloadJsonTest.java
        │   └── InvoiceJsonTest.java
        └── resources/com/example/json/
            └── product-expected.json
```

### 4.2. Maven POM with Jackson and JUnit Jupiter

File **`pom.xml`** — pinned to **Spring Boot 3.5.0** so Jackson 2 imports and Spring Boot test APIs are consistent:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>json-slice-demo</artifactId>
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

`spring-boot-starter-json` includes Jackson 2 and the appropriate Java Time module in the Boot 3.5 line. `spring-boot-starter-test` brings JUnit Jupiter, AssertJ, and the necessary JSON testing dependencies into test scope. The Maven parent manages the compatible version set: do **not** pin a standalone Jackson version that diverges from the BOM.

`spring-boot-starter-web`, an HTTP server, or `MockMvc` are not needed: the goal is solely **serialization/deserialization**. The main application file below helps Spring Boot locate the root configuration of the slice.

### 4.3. Root Spring Boot configuration

File **`src/main/java/com/example/json/JsonLearningApplication.java`**:

```java
package com.example.json;

import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JsonLearningApplication {
}
```

A `main` method is not needed to run JUnit tests; `@JsonTest` can discover `@SpringBootApplication` from the test's package. If you want to run it as a real application using `spring-boot:run`, you need to add `main` and a corresponding application entrypoint, but **that is not needed to test JSON**.

### 4.4. DTO with custom keys, dates, and null policy

File **`src/main/java/com/example/json/ProductPayload.java`**:

```java
package com.example.json;

import java.time.LocalDate;

import com.fasterxml.jackson.annotation.JsonFormat;
import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record ProductPayload(
        @JsonProperty("product_id") String productId,
        long priceVnd,
        @JsonFormat(shape = JsonFormat.Shape.STRING, pattern = "yyyy-MM-dd")
        LocalDate availableOn,
        String note) {
}
```

`@JsonProperty("product_id")` changes the **wire key** without changing the Java accessor name `productId()`. `@JsonInclude(NON_NULL)` only omits fields with a **Java null** value during serialization; it does not mean the `note` field can never be deserialized, nor is it a validation rule. `LocalDate` uses a plain date format, without a timezone like `Instant`.

With data `new ProductPayload("BOOK-1", 120_000L, LocalDate.of(2026,11,8), null)`, the JSON contract is:

```json
{
  "product_id": "BOOK-1",
  "priceVnd": 120000,
  "availableOn": "2026-11-08"
}
```

Here `"note"` is **completely absent**, rather than `"note": null`.

### 4.5. JSON fixture stored as a resource file

File **`src/test/resources/com/example/json/product-expected.json`**:

```json
{
  "product_id": "BOOK-1",
  "priceVnd": 120000,
  "availableOn": "2026-11-08"
}
```

With `JacksonTester`, `isEqualToJson("product-expected.json")` looks up the resource relative to the **package of the test class**. Placing the fixture in `src/test/resources/com/example/json/` avoids "resource not found" errors. Use fixture files when JSON is long, has nested structures, or needs contract changes clearly reviewed in Git. For a few simple fields, an inline JSON string can still be easy to read.

### 4.6. Testing serialization, JSONPath, deserialization, and syntax errors

File **`src/test/java/com/example/json/ProductPayloadJsonTest.java`**:

```java
package com.example.json;

import java.io.IOException;
import java.time.LocalDate;

import org.junit.jupiter.api.Test;
import org.skyscreamer.jsonassert.JSONCompareMode;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.json.JsonTest;
import org.springframework.boot.test.json.JacksonTester;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertThrows;

@JsonTest
class ProductPayloadJsonTest {
    @Autowired
    private JacksonTester<ProductPayload> json;

    private ProductPayload fixture() {
        return new ProductPayload(
                "BOOK-1", 120_000L, LocalDate.of(2026, 11, 8), null);
    }

    @Test
    void serializesExactPublicJsonContract() throws IOException {
        assertThat(json.write(fixture()))
                .isEqualToJson("product-expected.json", JSONCompareMode.STRICT);
    }

    @Test
    void serializesNamesTypesAndOmitsNullNote() throws IOException {
        var result = json.write(fixture());

        assertThat(result)
                .hasJsonPathStringValue("@.product_id")
                .doesNotHaveJsonPath("@.note");

        assertThat(result)
                .extractingJsonPathStringValue("@.availableOn")
                .isEqualTo("2026-11-08");

        assertThat(result)
                .hasJsonPathNumberValue("@.priceVnd");
    }

    @Test
    void deserializesJsonToEquivalentJavaRecord() throws IOException {
        String input = """
                {
                  "product_id":"BOOK-1",
                  "priceVnd":120000,
                  "availableOn":"2026-11-08",
                  "note":null
                }
                """;

        assertThat(json.parseObject(input)).isEqualTo(fixture());
    }

    @Test
    void rejectsMalformedJsonSyntax() {
        assertThrows(IOException.class,
                () -> json.parseObject("{\"product_id\":"));
    }
}
```

**Why these tests are meaningful:**

- The **strict** test checks the fixture structurally as JSON, rejecting extra or missing fields; **it does not require object keys to be in the same character order**.
- The JSONPath test checks the renamed key, the type of `priceVnd`, the date format, and that `note` is **absent**.
- The parse test reads realistic JSON and compares **record equality**, proving `@JsonProperty`, the date module, and the nullable field.
- The malformed-syntax test proves the parser reports an error. **It does not by itself prove the API will return HTTP 400** when a client sends that JSON; turning parser exceptions into HTTP status codes is the web layer's responsibility.

Java 17 supports **text blocks** (`"""`) and `record` types used in the example. The `JacksonTester`, `JSONCompareMode`, and `AssertJ` APIs here are chosen from the Spring Boot 3.5 library set.

### 4.7. Custom serializer using `@JsonComponent`

To prove that `@JsonTest` supports **custom mappings discovered by Spring Boot via component scan**, we create two records and a serializer.

File **`src/main/java/com/example/json/Money.java`**:

```java
package com.example.json;

public record Money(long amountVnd) {
}
```

File **`src/main/java/com/example/json/InvoiceView.java`**:

```java
package com.example.json;

public record InvoiceView(String invoiceId, Money total) {
}
```

File **`src/main/java/com/example/json/MoneySerializer.java`**:

```java
package com.example.json;

import java.io.IOException;

import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.databind.JsonSerializer;
import com.fasterxml.jackson.databind.SerializerProvider;

import org.springframework.boot.jackson.JsonComponent;

@JsonComponent
public final class MoneySerializer extends JsonSerializer<Money> {

    @Override
    public void serialize(Money value, JsonGenerator generator,
                          SerializerProvider provider) throws IOException {
        generator.writeString(value.amountVnd() + " VND");
    }
}
```

`@JsonComponent` on `MoneySerializer` makes this serializer a **special JSON component** registered with Jackson by Spring Boot 3.5. A regular `@Service` class is not scanned by default in `@JsonTest`, whereas `@JsonComponent` is permitted by the JSON slice's filters.

**Note:** This example only creates a **one-way** serializer for `Money`, without a corresponding deserializer. Therefore, the test below only asserts **serialization of `InvoiceView`**, without promising to parse `"150000 VND"` back into `Money`. If a real API requires round-trip support, you must create a compatible `JsonDeserializer<Money>` and add a parse test; testing only `write` will miss symmetry bugs.

File **`src/test/java/com/example/json/InvoiceJsonTest.java`**:

```java
package com.example.json;

import java.io.IOException;

import org.junit.jupiter.api.Test;
import org.skyscreamer.jsonassert.JSONCompareMode;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.json.JsonTest;
import org.springframework.boot.test.json.JacksonTester;

import static org.assertj.core.api.Assertions.assertThat;

@JsonTest
class InvoiceJsonTest {
    @Autowired
    private JacksonTester<InvoiceView> json;

    @Test
    void registeredJsonComponentSerializerChangesMoneyWireFormat()
            throws IOException {
        var invoice = new InvoiceView("INV-1", new Money(150_000L));

        assertThat(json.write(invoice))
                .isEqualToJson(
                        "{\"invoiceId\":\"INV-1\",\"total\":\"150000 VND\"}",
                        JSONCompareMode.STRICT);
    }
}
```

If the custom serializer is not loaded, `Money` would normally serialize as an object containing `amountVnd`, causing the test to **FAIL** instead of returning the defined string. Thus, the test accurately proves **custom mapping configuration inside the JSON slice**, not merely Java constructors or getters.

### 4.8. Run commands and expected results

In the directory containing `pom.xml`:

```bash
mvn test
```

If the project has a Maven Wrapper:

```bash
./mvnw test
```

Or run just the two classes:

```bash
mvn -Dtest=ProductPayloadJsonTest,InvoiceJsonTest test
```

On Windows, use `mvnw.cmd` when a wrapper exists, or `mvn` if Maven is installed. With the exact code and fixtures above, there are **5 `@Test` methods**: 4 in `ProductPayloadJsonTest` and 1 in `InvoiceJsonTest`. The expected result is **5 tests pass, 0 failures** on Java 17 and the selected Spring Boot 3.5 stack. These are JUnit tests, **with no fixed business stdout**; Maven Surefire/IDE output varies by version and configuration.

**Do not run `javac` manually and then `java ProductPayloadJsonTest`**: it depends on Spring TestContext, Jackson, AssertJ, and the JUnit test runner on the classpath. Maven commands use the BOM to pull compatible dependencies.

## 5. JSON configuration scope: modules, customizers, mixins, and excluded dependencies

A Spring Boot application can configure JSON at multiple layers:

| Component | Behavior in `@JsonTest` |
|---|---|
| Boot 3.x `@JsonComponent` | Typically scanned and registered for the Jackson 2 mapper |
| Jackson `Module` bean | A bean type allowed by the JSON slice filter, able to contribute serializers/deserializers |
| Annotations on DTOs such as `@JsonProperty`, `@JsonFormat`, `@JsonInclude` | Applied when the mapper processes the type, even when the DTO is not a Spring bean |
| `@JsonMixin` and corresponding configuration (when supported by version) | Must verify it is loaded/registered properly for the Boot line in use |
| `Jackson2ObjectMapperBuilderCustomizer` or mapper customizer in a regular `@Configuration` | **Do not assume it is automatically scanned** into the slice; may need `@Import` or dedicated test config |
| `@Service`, `@Repository`, controllers, and database infrastructure | **Not loaded by default** just because a JSON test is present |
| `HttpMessageConverter`, request/response filters, `@ControllerAdvice` | Not tested by the serialization slice alone; requires the corresponding web/slice test |

Example when JSON mapping depends on a custom-written Jackson Module:

```java
@JsonTest
@Import(MyJacksonConfiguration.class)
class CustomMappingTest {
    @Autowired
    JacksonTester<MyDto> json;
}
```

**This is a structural snippet, not standalone runnable code** because `MyJacksonConfiguration` and `MyDto` are hypothetical. Use `@Import` when the configuration under test is not in the slice's default set; do not assume every `@Configuration` with an `ObjectMapper` bean in production is automatically scanned into the test.

An important risk: **the mapper in `@JsonTest` may differ from the mapper used by a real endpoint**, for instance if the application has multiple `ObjectMapper` instances, MVC/WebFlux has separate converters, or an HTTP profile configures something different. If the requirement is "the `GET /orders` API returns the right JSON", add a **web test** to prove the endpoint actually uses the desired mapping.

### `@JsonTest` and Java records

Records are valid Java types for Jackson when the version is compatible; serialization/deserialization relies on property names/accessors and annotations on record components. However, **records do not enforce Bean Validation on their own**. To test `@NotBlank`, `@Valid`, or API error handling, write a validator unit test or `@WebMvcTest`/`@WebFluxTest` with validation infrastructure.

If there is a business invariant in a record constructor (for example, `priceVnd` must not be negative), JSON parsing can invoke the constructor and throw an exception wrapped by the mapper; however, `@JsonTest` **does not determine** the HTTP status of that error.

## 6. Strict vs lenient, absent vs null, object vs array order

These assertion choices directly affect contract test quality:

### 6.1. Lenient comparison

```java
assertThat(json.write(value)).isEqualToJson(expected);
```

In Spring Boot 3.5's JSON tester API, JSON comparison defaults to **lenient** (JSONAssert tolerance semantics). For example, an actual object with an extra `debug` field can still be accepted if `expected` does not mention it. This is reasonable when the test only cares about a subset of fields; **not appropriate** if the API contract forbids unlisted fields.

### 6.2. Strict comparison

```java
assertThat(json.write(value))
        .isEqualToJson(expected, JSONCompareMode.STRICT);
```

The above is a snippet used inside a class with `JacksonTester` and `import org.skyscreamer.jsonassert.JSONCompareMode`. Strict mode disallows extra fields and checks array order. However, JSON object keys are still compared by **property/name**, not by textual key order; that is the correct behavior for JSON structure.

If the contract requires a specific element order for `items`, assert the JSON array in that exact order. Conversely, if the contract allows elements to be unordered, do not enforce an order merely because the test fixture happens to be sorted in a particular way.

### 6.3. Absent and explicit `null` are not equivalent

These two JSON payloads differ in contract:

```json
{"product_id":"BOOK-1"}
```

```json
{"product_id":"BOOK-1","note":null}
```

`doesNotHaveJsonPath("@.note")` checks that the **key does not exist**. `doesNotHaveJsonPathValue("@.note")` can mean something different depending on how JSONPath treats `null`, so when the real goal is an **absent field**, choosing `doesNotHaveJsonPath` is clearer. Similarly, `hasJsonPath` is not the same as `hasJsonPathValue`: a key present with a `null` value does not mean it has a non-null value.

### 6.4. Number, BigDecimal, and JSON representation

JSON has a **number** type, but different clients/languages have their own numeric limits. Testing that `priceVnd` is a JSON number does not automatically guarantee that very large numbers are accurately represented by a JavaScript client. For money, consider `BigDecimal`, smallest-unit conventions, or strings with precision rules, and assert the exact consumer-facing contract. Do not "fix" monetary issues by unconditionally using `double`.

### 6.5. LocalDate, Instant, and timezone

`LocalDate` represents a **calendar date without a timezone**. `Instant` represents a **point in time in UTC**. With `Instant`, mapper format, precision, offset, and timezone can affect the wire format; do not merely assert `contains("2026")`. Use concrete fixtures, a fixed clock, and an explicit timezone policy. When testing date/time, test **both serialization and deserialization**, not just output.

## 7. JSON mapping does not mean a valid HTTP request body

A common mistake is writing:

```java
@JsonTest
class OrderJsonTest {
    // parseObject("{...}") succeeds
}
```

And then concluding that `POST /orders` will always return 201. That is **unfounded**, because HTTP also goes through:

```text
HTTP request
    |
    +--> router/controller mapping
    +--> security/authentication/authorization
    +--> Content-Type, accept negotiation, body decoding
    +--> JSON deserialization
    +--> Bean Validation (@Valid, constraints)
    +--> business service, transaction, repository
    +--> response serialization + HTTP status
```

`@JsonTest` only focuses on **JSON mapping**. To test whether a controller accepts `@RequestBody`, validates input, or returns 400/415/422 per the contract, use `@WebMvcTest` + MockMvc or `@WebFluxTest` + WebTestClient, with collaborators properly provided. To prove Spring DI wires multiple layers and the database, use `@SpringBootTest` with appropriate test fixtures. If you need to test HTTP sockets/an embedded server, use `@SpringBootTest(webEnvironment = RANDOM_PORT)`.

**Do not use `@SpringBootTest` for every DTO** when `@JsonTest` provides sufficient evidence: creating the entire context is expensive and can cause tests to fail due to unrelated external dependencies. Conversely, having only `@JsonTest` for a sensitive API can leave gaps in HTTP boundary coverage.

## 8. Alternatives using Gson, JSON-B, or without starting Spring

`@JsonTest` supports compatible mappers present on the classpath, not just Jackson. However, **annotations and modules differ across libraries**: `@JsonProperty`, `@JsonComponent`, and Jackson `Module` **do not automatically carry meaning for Gson or JSON-B**.

### GsonTester

Illustrative snippet if the project adds `com.google.code.gson:gson` per BOM/compatibility:

```java
@JsonTest
class GsonMappingTest {
    @Autowired
    GsonTester<MyDto> json;
}
```

`MyDto` is a hypothetical type; the snippet does not include test methods yet. When an app uses Gson, verify that Gson's naming strategy and custom `TypeAdapter` are **actually loaded**; do not copy Jackson annotations and expect Gson to understand them.

### JsonbTester

If using Jakarta JSON-B with a **JSON-B provider**, you can use:

```java
@JsonTest
class JsonbMappingTest {
    @Autowired
    JsonbTester<MyDto> json;
}
```

This is also a snippet and will not run standalone without a provider, DTO, and imports. JSON-B configuration differs from Jackson; tests must reflect the exact mapper the app uses.

### BasicJsonTester

When you only need to check a JSON string, `BasicJsonTester` provides JSON assertions without requiring a specific Java DTO/mapper. It is suited for fixtures or JSON produced by another library; it does not by itself prove **Java object ↔ JSON** conversion via Jackson.

### Testing Jackson directly with a unit test

In plain tests without `@JsonTest`, you can instantiate and configure a dedicated `ObjectMapper` or use `JacksonTester.initFields(...)` with a prepared mapper. The advantage is speed and independence from the Spring context; the disadvantage is that it **does not prove Spring Boot auto-configuration** such as `@JsonComponent` registration in the application. Choose based on the target scope, not annotation preference.

## 9. Differences between Spring Boot 3.5 and 4.x, especially Jackson 3

**The runnable examples in this lesson are pinned to Spring Boot 3.5.0**, using Jackson **2**, `com.fasterxml.jackson.*`, `ObjectMapper`, and `@JsonComponent` from the packages of this line.

In **Spring Boot 4.x**, Jackson **3** is the default mapper in newer releases; libraries and APIs have changed (e.g., `JsonMapper`, new Jackson `@JacksonComponent`/modules), while legacy Jackson 2 support is transitional/deprecated in some versions. **You cannot assume that simply bumping the parent version will preserve the behavior of every `JsonSerializer`, custom module, and Jackson 2 import.** Check the exact Boot 4 patch documentation, migration guide, and BOM, especially if the code uses custom serializers.

Things that must be verified when upgrading:

1. Whether `spring-boot-starter-json` and the actual selected JSON mapper use Jackson 3 or Jackson 2; do not accidentally pin both.
2. Serializer annotations and `JsonMapper`/`ObjectMapper` APIs match the right version line.
3. `@JsonTest` and the corresponding tester type exist in the chosen test module/classpath; do not assume all Boot 3.5 imports are identical in Boot 4.
4. Legacy `@JsonComponent`/Jackson `Module` implementations have been migrated to `@JacksonComponent`/new modules where needed.
5. Compare the **actual JSON contract** before and after upgrading, especially date/time, null, enums, numbers, unknown fields, and custom mappings.
6. Add a web-slice/integration test if you need to confirm the **real HTTP controller** uses the new mapper.

For instance, a `@JsonTest` that only has `JacksonTester<Dto>` without ever checking a custom `@JsonComponent` could still stay green after the serializer was accidentally dropped during a version migration. Keep **output-contract-style tests** like the `InvoiceJsonTest` example.

## 10. Common errors

| Symptom | Common cause | Fix |
|---|---|---|
| `JacksonTester<T>` cannot be injected | Missing matching Jackson/spring-test-json or wrong slice/test bootstrap | Check `spring-boot-starter-json`, `spring-boot-starter-test`, annotations, and version |
| JSON fixture reported not found | Resource placed in wrong package/path | Place in `src/test/resources/<package-path>/expected.json` matching the test's package |
| Mapper produces `productId` instead of `product_id` | Missing proper naming strategy/`@JsonProperty` | Assert strict wire key, use appropriate annotation/config |
| JSON has unexpected `"note": null` | Null inclusion policy differs from expectation | `@JsonInclude(NON_NULL)`, `doesNotHaveJsonPath` |
| Date becomes array/timestamp | Java Time module or different format | Use proper dependency/module/config, check `@JsonFormat` and output |
| Different JSON key order causes test failure | Rigid raw text comparison | Compare JSON structurally, strict when needed |
| Lenient test passes despite leaking sensitive field | Extra fields are ignored | `JSONCompareMode.STRICT`, explicitly test absent fields |
| `@JsonComponent` has no effect | Wrong mapper, serializer not scanned/imported, or different version | Check `@JsonTest` and mapper in context, test concrete output |
| Deserialization fails while serialization passes | Serializer exists without deserializer, missing constructor/property mapping | Test both `write` and `parseObject` directions when contract requires |
| `@Service` bean missing in JSON slice | Slice intentionally excludes regular services | `@Import` small config or switch to appropriate test level |
| JSON slice passes but HTTP returns 415/400 | Content-Type, `@RequestBody`, validation, or exception mapping not tested | `@WebMvcTest`/`@WebFluxTest` or integration test |
| Malformed JSON parse test runs but expected HTTP status does not appear | `@JsonTest` does not create HTTP endpoints | Separate parser tests from web-layer tests |
| Boot 4 does not pick up Boot 3 style custom serializer | Jackson 2/3 APIs and annotations changed | Consult version migration docs, adjust modules and regression contract tests |
| Suite is slow despite only testing DTOs | Using `@SpringBootTest` for every JSON mapping | Use `@JsonTest` or mapper unit tests as needed |
| Fixture has unstable data | Current timestamps, random IDs, locale/default zone | Use fixed values and deterministic configuration |

## 11. Checklist before finishing

- [ ] I know whether the goal is **Java ↔ JSON mapping** or **HTTP response/request behavior**.
- [ ] JSON mapping tests are separated from web/database layers when those layers are not needed.
- [ ] `@JsonTest` loads the mapper of the library actually used by the application.
- [ ] `@JsonComponent`/Jackson `Module` beans or important custom configs are loaded properly.
- [ ] If mapping has an extra service dependency, I considered scoping instead of importing the whole application.
- [ ] Serialization tests verify exact field names, field types, date/time, null policy, and nested values.
- [ ] When the contract requires it, I use **strict JSON comparison**, not just matching a single JSONPath.
- [ ] When a field must be absent, I use `doesNotHaveJsonPath` instead of ambiguous `null` checks.
- [ ] If round-trip is required, I test **both serialization and deserialization**.
- [ ] Malformed input/unknown fields, locale, timezone, and numeric precision are tested per requirements.
- [ ] Fixture files in `src/test/resources` are in the right location and reviewed like an API contract.
- [ ] Tests include representative assertions for `@JsonComponent` to catch dropped custom mappings.
- [ ] I know `@JsonTest` **does not test** controller mapping, HTTP status, security, or repositories.
- [ ] For Spring Boot 4.x, I double-checked **Jackson 3 vs Jackson 2, modules, imports, and testers**.
- [ ] I ran the proper build/test runner or verified the project's exact dependencies/behavior.

**Conclusion:** `@JsonTest` is a **test slice for serialization/deserialization**, not a tool for testing an entire REST API. It is well suited for proving mappers, DTO annotations, JSON contracts, custom serializers, and parse behavior within a lightweight context. When the risk belongs to HTTP or business workflows, supplement with `@WebMvcTest`, `@WebFluxTest`, or `@SpringBootTest` instead of overgeneralizing `@JsonTest` results.

### Official Documentation

- [Spring Boot 3.5 — Auto-configured JSON Tests](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Boot 3.5 — `@JsonTest` Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/json/JsonTest.html)
- [Spring Boot 3.5 — Test slices auto-configuration](https://docs.spring.io/spring-boot/3.5/appendix/test-auto-configuration/slices.html)
- [Spring Boot 3.5 — JSON mapper configuration](https://docs.spring.io/spring-boot/3.5/reference/features/json.html)
- [Spring Boot 4.x — JSON support and Jackson 3](https://docs.spring.io/spring-boot/reference/features/json.html)
- [Spring Boot — `JsonContentAssert` Javadoc](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/test/json/JsonContentAssert.html)
