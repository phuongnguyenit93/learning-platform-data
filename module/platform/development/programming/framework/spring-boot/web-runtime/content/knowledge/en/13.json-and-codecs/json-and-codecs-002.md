# Customizing spring.jackson.* and Jackson2ObjectMapperBuilderCustomizer in Spring Boot

Spring Boot uses Jackson to convert **Java objects ↔ JSON** when an application receives HTTP requests or returns HTTP responses, and Jackson can also be used in services, message converters, codecs, or anywhere an ObjectMapper is needed. Two common customization approaches are:

1. **spring.jackson.*** in application.yml/application.properties: the configuration surface provided by Spring Boot for common Jackson features.
2. **Jackson2ObjectMapperBuilderCustomizer**: a callback bean allowing the application to add configuration to the Spring Boot-managed Jackson2ObjectMapperBuilder. Used when properties cannot express custom serializers, deserializers, modules, or special rules.

The main focus is **Jackson 2 in Spring Boot 3.5.x / Spring Framework 6.2.x**, with packages `com.fasterxml.jackson.*` and `org.springframework.boot.autoconfigure.jackson.Jackson2ObjectMapperBuilderCustomizer`. Spring Boot 4.x prefers Jackson 3 with a different API and customizer group; **do not copy Jackson 2 code verbatim into Boot 4 without checking the migration guide**.

Guiding principle: **properties first, field/type annotations when needed, builder customizer for shared extensions, and replacing ObjectMapper only when truly necessary**. Replacing the entire mapper too early easily drops Spring Boot defaults, Java Time modules, and configurations set up by starters.

## 1. JSON Processing Flow in Spring Boot

An HTTP request can follow this flow:

~~~text
Client
  |
  | POST /api/products
  | Content-Type: application/json
  | {"product_name":"Keyboard"}
  v
Spring MVC DispatcherServlet
  |
  v
HandlerMethod + @RequestBody
  |
  v
MappingJackson2HttpMessageConverter
  |
  | uses Boot-configured ObjectMapper
  v
CreateProductRequest Java record
  |
  v
ProductController / Service
  |
  v
ProductResponse Java record
  |
  v
Jackson serializer
  |
  | Content-Type: application/json
  v
JSON response
~~~

In a WebFlux application, body reading/writing is performed via **HttpMessageReader/HttpMessageWriter and JSON encoders/decoders** instead of Servlet MVC HttpMessageConverter. Both can use Jackson, but you need to confirm which mapper and codecs are registered in the actual application.

Commonly encountered classes:

- **com.fasterxml.jackson.databind.ObjectMapper**: the core Jackson 2 object for serialization/deserialization.
- **Jackson2ObjectMapperBuilder** from Spring Framework: helps build and configure ObjectMapper; can auto-detect several well-known modules.
- **Jackson2ObjectMapperBuilderCustomizer** from Spring Boot: callback that modifies the Boot-managed builder.
- **JacksonAutoConfiguration**: auto-configuration that creates the builder/mapper and applies customizers under appropriate conditions.
- **MappingJackson2HttpMessageConverter**: JSON converter commonly used in MVC.
- **Jackson2JsonEncoder/Jackson2JsonDecoder**: JSON codecs commonly used in WebFlux.
- **@JsonProperty, @JsonFormat, @JsonInclude**: Jackson annotations controlling how a specific type or property is mapped.

Do not immediately assume an unexpected JSON response is a controller bug. Check in order: Java object → annotations → ObjectMapper/codec → content negotiation → response body.

## 2. How Does Spring Boot Configure Jackson by Default?

With `spring-boot-starter-web` or `spring-boot-starter-webflux` on Boot 3.5, the JSON starter normally provides the required Jackson dependencies. If auto-configuration conditions are satisfied, Boot creates an **ObjectMapper** and **Jackson2ObjectMapperBuilder**, then applies web-friendly defaults.

Common defaults in Boot 3.x:

- `DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES` is typically **disabled** on the Boot-configured mapper: JSON containing unknown fields does not automatically fail the request solely because of those fields.
- `SerializationFeature.WRITE_DATES_AS_TIMESTAMPS` is typically **disabled**: date/time types supported by the module typically serialize to an appropriate text/ISO representation, though this still depends on the Java type and annotations.
- `MapperFeature.DEFAULT_VIEW_INCLUSION` is disabled per the builder/framework configuration.
- Modules for Java 8 date/time, Optional, and several common types are registered when appropriate dependencies are present.
- `Jackson2ObjectMapperBuilder` can be reused by multiple components to create mappers with aligned configuration.

These are **defaults of the Boot-managed mapper**, not mandatory settings for every ObjectMapper in the JVM. Calling `new ObjectMapper()` in application code creates an independent instance that does not automatically receive `spring.jackson.*` properties or builder customizers.

Do not rely on defaults not explicitly documented in your project's API contract. For requirements such as unknown fields, date formats, enums, or null fields, configure properties explicitly and write tests to protect the behavior.

## 3. Important spring.jackson.* Property Groups

Spring Boot 3.5.x provides several property groups. Not every Jackson enum or option has an independent key listed by full name in metadata; groups with `*` allow binding supported features by enum name.

| Property Group | Meaning | Example |
|---|---|---|
| spring.jackson.property-naming-strategy | JSON property naming rule | SNAKE_CASE |
| spring.jackson.default-property-inclusion | Include or omit fields based on value | NON_NULL, NON_EMPTY |
| spring.jackson.serialization.* | Enable/disable SerializationFeature | indent-output, write-dates-as-timestamps |
| spring.jackson.deserialization.* | Enable/disable DeserializationFeature | fail-on-unknown-properties |
| spring.jackson.mapper.* | Enable/disable MapperFeature | accept-case-insensitive-properties |
| spring.jackson.parser.* | Enable/disable JsonParser.Feature | allow-comments (requires security consideration) |
| spring.jackson.generator.* | Enable/disable JsonGenerator.Feature | escape-non-ascii when supported |
| spring.jackson.time-zone | Timezone used when Jackson formats compatible types | Asia/Ho_Chi_Minh |
| spring.jackson.date-format | Pattern for compatible date formats, typically legacy java.util.Date | yyyy-MM-dd HH:mm:ss |
| spring.jackson.locale | Locale for locale-dependent formatting | vi_VN |
| spring.jackson.visibility.* | Auto-detection threshold for getters, fields, etc. | field: any |

**Note:** the "allow-comments" example for the JSON parser is mentioned to distinguish configuration groups, not as a recommendation to enable it. JSON comments are not part of standard JSON syntax and can cause handling discrepancies between systems.

### 3.1. application.yml Example

~~~yaml
spring:
  jackson:
    property-naming-strategy: SNAKE_CASE
    default-property-inclusion: non_null
    serialization:
      indent-output: false
      write-dates-as-timestamps: false
    deserialization:
      fail-on-unknown-properties: false
~~~

Meaning:

1. Java's `productName` is named `product_name` when using the snake_case strategy and no overriding annotation.
2. Fields with null values are omitted from JSON responses at the mapper default level.
3. `indent-output: false` disables pretty printing.
4. `write-dates-as-timestamps: false` favors non-timestamp date/time representations for supported types.
5. `fail-on-unknown-properties: false` allows extra fields beyond the DTO during deserialization according to active Jackson rules.

Boot relaxed binding accepts various casing, hyphens, and corresponding feature names; however, use the keys listed in your version's documentation for readability and clarity.

### 3.2. Equivalent application.properties

~~~properties
spring.jackson.property-naming-strategy=SNAKE_CASE
spring.jackson.default-property-inclusion=non_null
spring.jackson.serialization.indent-output=false
spring.jackson.serialization.write-dates-as-timestamps=false
spring.jackson.deserialization.fail-on-unknown-properties=false
~~~

Do not declare both YAML and properties in the same project. If multiple PropertySources contain the same key, the Spring Environment determines the effective value according to Boot's precedence rules. Environment variables or CLI arguments can override config files per their priority order.

## 4. Naming Strategy: camelCase in Java, snake_case in External JSON

When declaring:

~~~java
public record ProductResponse(
        long id,
        String productName,
        String optionalNote) {
}
~~~

and configuring SNAKE_CASE, Jackson can serialize it to:

~~~json
{
  "id": 1,
  "product_name": "Keyboard",
  "optional_note": "Demo"
}
~~~

During deserialization, incoming JSON with the key `product_name` can map to the record parameter `productName`. This is especially useful when the API contract uses snake_case while Java code follows camelCase.

Do not confuse a **naming strategy** with automatically renaming every string in JSON. It applies to property names mapped by Jackson, not String values or business keys across arbitrary data types.

### 4.1. Overriding on a Single Field

If one field must keep an external name differing from the global rule, use @JsonProperty:

~~~java
public record ProductView(
        @JsonProperty("external_id") long id,
        String productName) {
}
~~~

With global SNAKE_CASE, the JSON can be:

~~~json
{"external_id":1,"product_name":"Keyboard"}
~~~

@JsonProperty declares an explicit name for this property, suitable when a partner schema has an exception. Do not change the global naming strategy just because one field has an unusual name.

### 4.2. Risk of Changing Naming Strategy After API Release

Changing property-naming-strategy from the default to SNAKE_CASE can be a **breaking change**:

- Response field names can change from `productName` to `product_name`.
- Clients previously sending `productName` may no longer bind as expected.
- JSON snapshots, OpenAPI schemas, frontend models, and integration tests may stop matching.
- Message producers/consumers sharing the ObjectMapper can also be affected if they use the same mapper.

For stable public APIs, consider versioning/migration, separate DTOs, or local annotations instead of turning on a global change hastily.

## 5. Null Fields: NON_NULL vs. NON_EMPTY and NON_DEFAULT

`spring.jackson.default-property-inclusion` uses values from `JsonInclude.Include`.

| Value | Practical Meaning | Warning |
|---|---|---|
| ALWAYS | Normally serializes properties even when null | May expose unnecessary data structure |
| NON_NULL | Omits null properties | Does not omit "", 0, false, or empty lists |
| NON_EMPTY | Omits null and certain empty values per serializer/type | Definition of empty depends on Jackson and the type |
| NON_DEFAULT | Omits values considered defaults in the given context | Needs explicit testing, especially with primitives/records/POJOs |

Record example:

~~~java
new ProductResponse(1L, "Keyboard", null)
~~~

with NON_NULL can produce:

~~~json
{"id":1,"product_name":"Keyboard"}
~~~

Do not treat an **absent field** as identical to a **null-valued field** in every API. Some clients distinguish the two, especially for PATCH, JSON Merge Patch, or partial updates.

If a specific field must be serialized even when null, you can use `@JsonInclude(JsonInclude.Include.ALWAYS)` at the field/type level and test the result. Model annotations are typically used for contract exceptions, while global properties define the application default.

## 6. Serialization and Deserialization Are Not the Same Operation

**Serialization**: Java object → JSON. For example, returning `@ResponseBody` or a REST response.

**Deserialization**: JSON → Java object. For example, receiving `@RequestBody`.

Common misconceptions:

- `serialization.indent-output` only controls indentation of output JSON; it does not determine whether input JSON is valid.
- `deserialization.fail-on-unknown-properties` only controls how unmapped properties are handled. It does **not** ignore malformed JSON, oversized bodies, wrong types, or validation rules.
- `default-property-inclusion` primarily affects **output**; it does not mean an input field with null will be automatically rejected.
- `property-naming-strategy` can affect both input and output.
- Time zone/DateFormat affects certain date/time types; it does not turn arbitrary Strings into dates or change the JVM default timezone.
- Jackson annotations such as `@JsonFormat` and `@JsonIgnoreProperties` can alter local behavior relative to defaults.

A POST with `Content-Type: application/json` but malformed JSON typically triggers an HTTP 400 error at the body-reading layer. A POST with `Content-Type: text/plain` sent to a handler that only consumes JSON can return HTTP 415 before Jackson is invoked. Do not investigate `spring.jackson.*` when the real issue is consumes/Content-Type.

## 7. When to Use Jackson2ObjectMapperBuilderCustomizer?

In Boot 3.5.x, Spring Boot recognizes beans of type:

~~~java
org.springframework.boot.autoconfigure.jackson
        .Jackson2ObjectMapperBuilderCustomizer
~~~

The interface has one method:

~~~java
void customize(Jackson2ObjectMapperBuilder builder);
~~~

This is an **abbreviated API definition**, not a standalone Java file. The customizer bean receives the Boot-managed builder and adds options before the mapper is constructed.

Appropriate use cases:

- Adding a serializer or deserializer for a business data type.
- Adding a specialized date/time formatter for a type when annotations are unsuitable.
- Adding a Jackson module or mix-in through a proper extension point.
- Tuning features not exposed directly as properties.
- Standardizing configuration across mappers built from the Boot-managed builder.

Structural example:

~~~java
@Bean
Jackson2ObjectMapperBuilderCustomizer jsonCustomizer() {
    return builder -> {
        // Additional configuration on the Boot-managed builder.
    };
}
~~~

**Do not confuse** this with calling `new ObjectMapper()`. A builder customizer only affects mappers created through a builder that applies the customizer; it does not automatically alter every ObjectMapper instantiated by other libraries in the process.

## 8. Customizer Ordering and Relationship with spring.jackson.*

Spring Boot allows multiple `Jackson2ObjectMapperBuilderCustomizer` beans. They can be ordered with `@Order`/`Ordered`. In the mechanism documented for Boot 3.5, Boot's property-configuring customizer has order **0**; therefore you can add customizers that run before or after it.

Example:

~~~java
@Bean
@Order(1)
Jackson2ObjectMapperBuilderCustomizer amountCustomizer() {
    return builder -> builder.serializerByType(
            MoneyAmount.class, new MoneyAmountSerializer());
}
~~~

In this example, `@Order(1)` requests the customizer to run after Boot's order-0 customizer. However, `serializerByType` for a specific business type does not conflict with naming strategies or `NON_NULL`, so ordering is shown here to clarify the extension principle.

If multiple customizers call setters for the same feature, the result can depend on application order. Do not configure one value via a property and a conflicting value via a customizer while assuming one always wins.

Recommended practices:

1. Use properties for common settings.
2. Use customizers for new behavior that **does not overlap** with properties.
3. If an override is unavoidable, specify order explicitly and test the resulting mapper.
4. Place customizers in a package covered by component scanning or imported into the ApplicationContext.
5. Do not mutate ObjectMapper configuration once the application starts serving requests; a shared mapper across threads is expected to remain stable.

## 9. Runnable Java 17+ Sample Project

Scenario: a JSON API needs `snake_case`, omitted null fields, leniency for unknown input fields, and formatting for a specialized `MoneyAmount` type as a string ending in " VND". We use:

- **application.yml**: configures general features that already have properties.
- **Jackson2ObjectMapperBuilderCustomizer**: registers a serializer for `MoneyAmount`.
- **@RestController**: GET and POST to observe bidirectional data flow.
- **MockMvc**: verifies JSON output and input against the contract.
- **ObjectMapper bean**: verifies the serializer is registered in the Boot-managed mapper.

To avoid database dependencies, the example uses a fixed response with `id=1`. This is a JSON demo, **not a product persistence system**.

Structure:

~~~text
jackson-customization-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/jsondemo/
    │   │   ├── JsonDemoApplication.java
    │   │   ├── MoneyAmount.java
    │   │   ├── MoneyAmountSerializer.java
    │   │   ├── JsonConfiguration.java
    │   │   ├── CreateProductRequest.java
    │   │   ├── ProductResponse.java
    │   │   └── ProductController.java
    │   └── resources/
    │       └── application.yml
    └── test/
        └── java/com/example/jsondemo/
            └── ProductJsonTest.java
~~~

### 9.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <artifactId>jackson-customization-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>jackson-customization-demo</name>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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
~~~

This is a complete Maven `pom.xml`. `spring-boot-starter-web` brings in the Jackson 2 artifacts needed for JSON in Boot 3.5.x, and the Spring Boot parent manages dependency versions.

### 9.2. application.yml

~~~yaml
spring:
  jackson:
    property-naming-strategy: SNAKE_CASE
    default-property-inclusion: NON_NULL
    serialization:
      indent-output: false
      write-dates-as-timestamps: false
    deserialization:
      fail-on-unknown-properties: false
~~~

The example chooses explicit properties and needs no passwords or secrets in the file. Do not use `@EnableWebMvc`; Spring Boot auto-configures MVC and JSON converters as usual.

### 9.3. JsonDemoApplication.java

~~~java
package com.example.jsondemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JsonDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(JsonDemoApplication.class, args);
    }
}
~~~

`@SpringBootApplication` enables auto-configuration and component scanning for classes in the `com.example.jsondemo` package.

### 9.4. MoneyAmount.java

~~~java
package com.example.jsondemo;

import java.math.BigDecimal;

public record MoneyAmount(BigDecimal value) {
}
~~~

`MoneyAmount` is a simple business type. The default JSON for this record would be an object with a `value` property; in this demo we want to write a string with a unit.

**Design note:** in real financial systems, exchange monetary amounts and currencies using an explicit schema (such as `amount` + `currency`), rather than only sending a string containing `" VND"`. The string format here is an easy-to-observe custom serializer example, not a payment API standard.

### 9.5. MoneyAmountSerializer.java

~~~java
package com.example.jsondemo;

import java.io.IOException;

import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.databind.JsonSerializer;
import com.fasterxml.jackson.databind.SerializerProvider;

public class MoneyAmountSerializer extends JsonSerializer<MoneyAmount> {

    @Override
    public void serialize(
            MoneyAmount amount,
            JsonGenerator generator,
            SerializerProvider serializers) throws IOException {

        generator.writeString(
                amount.value().toPlainString() + " VND");
    }
}
~~~

This is a Jackson **2** serializer. It writes `MoneyAmount` as a JSON string. `writeString` handles necessary escaping for string values; do not manually wrap quotes and call `writeRawValue` when you just need to serialize a String.

### 9.6. JsonConfiguration.java

~~~java
package com.example.jsondemo;

import org.springframework.boot.autoconfigure.jackson
        .Jackson2ObjectMapperBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;

@Configuration(proxyBeanMethods = false)
public class JsonConfiguration {

    @Bean
    @Order(1)
    Jackson2ObjectMapperBuilderCustomizer moneyAmountCustomizer() {
        return builder -> builder.serializerByType(
                MoneyAmount.class, new MoneyAmountSerializer());
    }
}
~~~

**Important note about Java imports:** Does Java disallow line breaks between package names and dots in imports? Java actually permits whitespace between dot tokens and identifiers, but to keep code easy to copy and avoid confusion, write the import on **one line** as follows:

~~~java
import org.springframework.boot.autoconfigure.jackson.Jackson2ObjectMapperBuilderCustomizer;
~~~

The rest of the file stays the same. The bean has `@Order(1)` to run after Spring Boot's order-0 customizer. It does not call `new ObjectMapper()`, does not replace the entire builder, and does not erase active properties.

### 9.7. CreateProductRequest.java

~~~java
package com.example.jsondemo;

public record CreateProductRequest(
        String productName,
        String optionalNote) {
}
~~~

Jackson is configured with SNAKE_CASE, so the input uses `product_name`, `optional_note`. If the request contains an extra field, `fail-on-unknown-properties: false` lets the mapper ignore fields absent from the DTO.

### 9.8. ProductResponse.java

~~~java
package com.example.jsondemo;

public record ProductResponse(
        long id,
        String productName,
        String optionalNote,
        MoneyAmount totalPrice) {
}
~~~

This is a Java record using both String properties and the custom `MoneyAmount` type. With `NON_NULL`, `optionalNote=null` is omitted from output; `totalPrice` is converted into a String by the custom serializer.

### 9.9. ProductController.java

~~~java
package com.example.jsondemo;

import java.math.BigDecimal;
import java.net.URI;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/products")
public class ProductController {

    @GetMapping(
            path = "/{id}",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<ProductResponse> get(
            @PathVariable("id") long id) {

        if (id != 1L) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.ok(sample("Keyboard", null));
    }

    @PostMapping(
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<ProductResponse> create(
            @RequestBody CreateProductRequest body) {

        if (body.productName() == null
                || body.productName().isBlank()) {
            return ResponseEntity.badRequest().build();
        }

        ProductResponse response =
                sample(body.productName(), body.optionalNote());

        return ResponseEntity
                .created(URI.create("/api/products/1"))
                .body(response);
    }

    private ProductResponse sample(
            String productName,
            String optionalNote) {

        return new ProductResponse(
                1L,
                productName,
                optionalNote,
                new MoneyAmount(new BigDecimal("125000")));
    }
}
~~~

The controller returns responses via Spring MVC; the JSON converter uses the Boot-configured Jackson mapper. Returning `id=1` on POST is a demo convention and does not imply data persistence.

**Distinguishing the boundaries:** `SNAKE_CASE` and `NON_NULL` are controlled by properties; the `" VND"` suffix on `totalPrice` comes from the customizer registering `MoneyAmountSerializer`.

## 10. Testing All Behavior with MockMvc

**src/test/java/com/example/jsondemo/ProductJsonTest.java**

~~~java
package com.example.jsondemo;

import java.math.BigDecimal;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ProductJsonTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void getUsesSnakeCaseNullExclusionAndSerializer() throws Exception {
        mvc.perform(get("/api/products/1")
                    .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.product_name")
                        .value("Keyboard"))
                .andExpect(jsonPath("$.total_price")
                        .value("125000 VND"))
                .andExpect(jsonPath("$.optional_note")
                        .doesNotExist());
    }

    @Test
    void postDeserializesSnakeCaseAndIgnoresUnknownField()
            throws Exception {

        mvc.perform(post("/api/products")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_JSON)
                    .content("""
                            {
                              "product_name": "Mouse",
                              "optional_note": null,
                              "unknown_field": 123
                            }
                            """))
                .andExpect(status().isCreated())
                .andExpect(header().string(
                        "Location", "/api/products/1"))
                .andExpect(jsonPath("$.product_name").value("Mouse"))
                .andExpect(jsonPath("$.total_price")
                        .value("125000 VND"))
                .andExpect(jsonPath("$.optional_note").doesNotExist());
    }

    @Test
    void missingProductNameIsRejected() throws Exception {
        mvc.perform(post("/api/products")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"optional_note\":\"none\"}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void bootManagedObjectMapperHasCustomizer() throws Exception {
        ProductResponse response = new ProductResponse(
                1L, "Keyboard", null,
                new MoneyAmount(new BigDecimal("125000")));

        JsonNode tree = objectMapper.readTree(
                objectMapper.writeValueAsString(response));

        assertThat(tree.path("product_name").asText())
                .isEqualTo("Keyboard");
        assertThat(tree.path("total_price").asText())
                .isEqualTo("125000 VND");
        assertThat(tree.has("optional_note")).isFalse();
    }
}
~~~

Strengths of the tests:

- GET verifies field **serialization** with global naming + NON_NULL + custom serializer.
- POST verifies snake_case **deserialization** and unknown field handling per property.
- Missing `product_name` verifies the controller rejects invalid business data.
- The `ObjectMapper` test confirms the Boot-managed bean has the customizer's serializer, not just an isolated HTTP converter.

**Do not use JSON string equality to assert key order**: JSON objects do not require preserving property order as shown in examples. Use `jsonPath` or `JsonNode` to check structure and values.

Because the test code uses Java text blocks (`"""` in `.content`), Java 15+ is required, which the project's Java 17 satisfies.

Run from the root directory:

~~~bash
mvn test
mvn spring-boot:run
~~~

Maven returns exit code 0 when tests/builds succeed. If dependencies are not yet cached, Maven needs to download them from configured repositories; log line counts and test execution order are not deterministic and must not be used as proof of correctness.

## 11. Trying the API with curl and Reading Real JSON

When the application runs on the default port 8080:

~~~bash
curl -i \
  -H 'Accept: application/json' \
  http://localhost:8080/api/products/1
~~~

Logical response body:

~~~json
{"id":1,"product_name":"Keyboard","total_price":"125000 VND"}
~~~

Do not assert that field order always matches the string above; tests only check the required values.

POST:

~~~bash
curl -i -X POST \
  http://localhost:8080/api/products \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  --data '{"product_name":"Mouse","optional_note":null,"unknown_field":123}'
~~~

Expected result: HTTP 201 Created, Location: `/api/products/1`; JSON contains `product_name="Mouse"`, `total_price="125000 VND"`, and omits `optional_note` because it is null. `unknown_field` is ignored under `fail-on-unknown-properties=false`.

If you change the property to `true`, the POST request above can be rejected by Jackson due to `unknown_field`, producing HTTP 400 (via Spring MVC's `@RequestBody` reading mechanism). Toggling this flag is an API contract decision and should not be changed after release without testing client integrations.

With Windows PowerShell, you can use `curl.exe` to avoid alias differences in PowerShell versions.

## 12. When to Add a Jackson Module or @JsonComponent?

If custom serializers/deserializers need to be reused or package a group of types, a Jackson **Module** can be cleaner than calling `builder.serializerByType` for each class.

Example of a module bean for the **same MoneyAmountSerializer**:

~~~java
@Bean
Module moneyModule() {
    SimpleModule module = new SimpleModule("money-module");
    module.addSerializer(
            MoneyAmount.class, new MoneyAmountSerializer());
    return module;
}
~~~

Required imports:

~~~java
import com.fasterxml.jackson.databind.Module;
import com.fasterxml.jackson.databind.module.SimpleModule;
~~~

In Boot 3.5.x, Jackson `Module` beans are discovered and applied to the Boot-created builder/mapper via auto-configuration. This is an **alternative** to the customizer registering `MoneyAmountSerializer`; **do not register both for the same type just to experiment**, as it can create duplicate configuration or confusing precedence.

Another option is **@JsonComponent** for serializers/deserializers under Spring Boot 3.x when you want the serializer class to be auto-detected via component scanning. Check the API of the Boot version in use and test that the serializer appears in the mapper actually used by the HTTP converter.

Selection rules:

- One or two changes on the mapper: `Jackson2ObjectMapperBuilderCustomizer` is usually simple.
- Packaging reusable serializers/deserializers: Jackson `Module`.
- Scoping changes to a single DTO: `@JsonProperty`, `@JsonFormat`, `@JsonInclude`, or other Jackson annotations.
- Only common features/naming/locale needed: `spring.jackson.*`.

## 13. Dates, Timezones, and Java Time: Error-Prone Corners

There are three common date/time groups:

1. **java.util.Date / Calendar**: legacy types, typically affected by the mapper's `date-format`/`time-zone`.
2. **java.time.Instant / OffsetDateTime / ZonedDateTime**: carry instant or offset/zone information; formatting depends on the Java Time module and Jackson configuration.
3. **java.time.LocalDate / LocalDateTime**: represent a calendar date or date-time **without an attached timezone**; changing global `time-zone` does not turn a `LocalDateTime` into a zoned instant.

Example:

~~~java
public record EventResponse(
        Instant createdAt,
        LocalDate eventDate) {
}
~~~

With the Java Time module present and `WRITE_DATES_AS_TIMESTAMPS=false`, these types usually serialize to appropriate text representations. However, if the API requires a specific ISO format, write tests for each field and type rather than assuming all types are handled identically.

### 13.1. @JsonFormat for Local Exceptions

~~~java
public record EventView(
        @JsonFormat(pattern = "yyyy-MM-dd")
        LocalDate eventDate) {
}
~~~

When a requirement applies to just one field, `@JsonFormat` is usually clearer than setting `spring.jackson.date-format` globally. In particular, a `java.util.Date` pattern should not be assumed to apply identically to every `java.time` type.

Records or code using `@JsonFormat` need to import `com.fasterxml.jackson.annotation.JsonFormat` and `java.time.LocalDate`.

### 13.2. Do Not Rely on Timezone to Fix the Domain Model

If the system needs to store absolute instants, `Instant`/`OffsetDateTime` usually express that more clearly than a zoneless `LocalDateTime`. The timezone used for **displaying** to users is a separate decision from the timestamp stored/exchanged. Do not mask flawed domain semantics simply by changing `spring.jackson.time-zone`.

### 13.3. Do Not Accidentally Drop the Java Time Module

Manually creating `new ObjectMapper()` and calling `writeValueAsString` with `LocalDate` may lack `JavaTimeModule`, depending on dependencies and mapper initialization. A Boot-managed builder typically handles present modules through Spring's integration mechanism. If replacing the mapper, register all required modules, configure formatting, and re-test.

## 14. When Multiple ObjectMappers Coexist

An application may have:

- The Boot auto-configured `ObjectMapper` bean for web JSON.
- A dedicated `ObjectMapper` for Kafka, file export, cache, or an external API.
- A dedicated `XmlMapper` for XML.
- A mapper instantiated directly by a third-party library.
- A mapper built from the Boot-configured `Jackson2ObjectMapperBuilder`.

**A customizer does not guarantee that every mapper in the JVM shares the same configuration.** Only mappers created through a builder that applies the customizers receive those customizations accordingly.

Example of creating a separate mapper while still using the Boot-injected builder:

~~~java
@Bean("exportObjectMapper")
ObjectMapper exportObjectMapper(
        Jackson2ObjectMapperBuilder builder) {

    return builder.build();
}
~~~

This is an extension example **not added to the sample project in section 9**, because multiple `ObjectMapper` beans can cause injection ambiguity by type and alter auto-configuration conditions. When an application legitimately has multiple mappers, assign clear names/`@Qualifier`s and verify which mapper each converter/codec uses.

**Not recommended**:

~~~java
ObjectMapper mapper = new ObjectMapper();
~~~

if the goal is to inherit all `spring.jackson.*` settings and Boot customizers. A manual mapper may work, but it often lacks integrations that the project expects.

### 14.1. Declaring Your Own ObjectMapper Bean Can Make Boot Back Off

If an application defines its own mapper (especially `@Primary`), auto-configuration conditions can change: Boot's default mapper may no longer be created, or converters may pick a different mapper. Declaring your own `Jackson2ObjectMapperBuilder` bean can also alter builder preparation logic.

Treat replacing the mapper as an **infrastructure-level** change requiring tests for HTTP JSON, modules, custom serializers, naming, null inclusion, date/time, and mapper injection sites. Do not use that approach merely to enable pretty printing or swap one serializer.

## 15. Jackson and Spring MVC: Avoiding Confusion with HttpMessageConverter

Spring MVC chooses a converter based on Java type, request `Content-Type`, client `Accept`, and the media types supported by the converter.

Cases:

- **400 Bad Request**: JSON body has syntax errors, cannot bind to the DTO, or fails validation.
- **415 Unsupported Media Type**: Input `Content-Type` is not supported by `consumes` mapping/converters.
- **406 Not Acceptable**: `Accept` requests a response media type that the mapping/converter cannot provide.
- **500 or response error**: an unhandled serialization exception occurred while writing the response.

`spring.jackson.deserialization.fail-on-unknown-properties=false` does not mean any invalid JSON is accepted. It only ignores **unknown properties** under Jackson's rules; syntactically invalid bodies or incompatible types can still be rejected.

**You do not need @EnableWebMvc** to customize `ObjectMapper` in Spring Boot. `WebMvcConfigurer` has dedicated extension points for message converters; replacing or clearing the converter list can strip the application of default behaviors. If your goal is only to adjust JSON, start with `spring.jackson.*` and customizers.

### 15.1. JSON Responses Are Not Decided by the Controller Alone

When a `@RestController` returns `ProductResponse`, Spring MVC still needs a JSON converter and an appropriate `ObjectMapper`. If changed to `ResponseEntity<String>` containing pre-built JSON, it may go through the String converter and bypass `ObjectMapper` serialization. That explains why "I set `spring.jackson.*` and nothing changed" can happen when an endpoint returns `String` instead of a DTO.

Do not concatenate JSON strings manually to bypass the converter unless a special protocol requires it and escaping/content type are guaranteed valid.

## 16. Jackson and Spring WebFlux: Different Codec Attachment Points

The Spring WebFlux reactive stack uses `Jackson2JsonEncoder`/`Decoder` for JSON when Jackson is chosen and codecs are properly configured. They serve a role analogous to MVC's JSON converter, though they are not the same bean types.

Example WebFlux controller:

~~~java
@RestController
@RequestMapping("/api/products")
public class ReactiveProductController {

    @GetMapping("/{id}")
    public Mono<ProductResponse> find(
            @PathVariable long id) {
        return service.findById(id);
    }
}
~~~

This is an **illustrative snippet**, lacking a `service` field and imports, and is not part of the runnable MVC project in section 9. It highlights that `Mono` does not itself dictate the JSON format; codecs and mappers still must be configured.

When a WebFlux JSON response does not reflect a customizer:

1. Confirm the application is actually running a Spring WebFlux server, not an MVC app using WebClient.
2. Check `CodecConfigurer`, `CodecCustomizer`, and any custom encoders/decoders.
3. Verify whether the Jackson mapper is Boot-managed or replaced by the application.
4. Check if entity/DTO annotations override global settings.
5. Test with `WebTestClient` using actual JSON bodies, not just the `ObjectMapper` bean in isolation.

A project that only adds `spring-boot-starter-webflux` to use `WebClient` inside MVC does not necessarily run a reactive server. Adding the WebFlux dependency does not automatically switch the entire HTTP server stack from Servlet to reactive.

## 17. Precedence Between Properties, Annotations, and Java Config

There is no single formula where "every annotation always beats every property" across all types/features, but here is a useful mental model:

- **spring.jackson.*** sets the defaults for the Boot-configured mapper.
- **Jackson2ObjectMapperBuilderCustomizer** modifies the builder, follows ordering, and can override certain options if using the same setters.
- **@JsonProperty / @JsonFormat / @JsonInclude** set local rules on types/properties, which Jackson typically inspects when choosing serializers/deserializers.
- **Jackson Module** registers type-level handlers that can alter how Jackson performs mapping.
- **Message converter/codec** determines which `ObjectMapper` is used at the HTTP boundary.
- **Manually created ObjectMapper/JsonMapper** may bypass all of the above mechanisms.

When conflicts arise, verify with **serialization and deserialization tests on the actual type/endpoint**. Do not rely on general inferences from property names to assert final behavior.

## 18. Designing Safe and Stable APIs

### 18.1. Unknown Fields: Lenient or Strict?

`fail-on-unknown-properties=false` aids API backward/forward compatibility in certain cases, but risks clients thinking a field is supported while the server silently ignores it. For sensitive APIs, use DTOs accepting only valid fields, explicit validation, or strict mode depending on the contract.

In particular, avoid binding request bodies directly to entities containing administrative fields like `admin`, `role`, `ownerId`, or `internalStatus`. Jackson naming/inclusion does not replace authorization and mass-assignment protection.

### 18.2. Do Not Enable Polymorphic Default Typing Carelessly

With untrusted JSON, avoid enabling Jackson polymorphic default typing that could accept arbitrary class names from input. Polymorphic features require valid type constraints and security review; never configure them just to "deserialize any object" without an appropriate allowlist/validator.

### 18.3. Large and Deep JSON Limits

Jackson has parser/stream constraints and Spring HTTP has request size/buffer limits; these properties vary across Boot/Jackson versions. Avoid disabling all limits just to accept one malformed payload. When large data is needed, consider streaming, chunking, size limits, and observability.

### 18.4. Do Not Serialize Sensitive Data

`NON_NULL` is not a tool for hiding passwords or tokens. Omitting nulls only means fields without values are absent; fields holding secrets will still be serialized. Use separate response DTOs, appropriate `@JsonIgnore`, and data minimization principles.

## 19. Troubleshooting: Why Is Configuration Having No Effect?

| Symptom | Common Cause | How to Check |
|---|---|---|
| `productName` still outputs as camelCase | Property not loaded; controller returns String; another ObjectMapper is in use | Check Environment, response DTO, converter/codec, and test the mapper bean |
| `optionalNote=null` still appears | NON_NULL does not apply to that mapper or `@JsonInclude` overrides it | Test ObjectMapper and DTO annotations |
| `MoneyAmount` outputs as an object instead of a string | Customizer bean not scanned or mapper not built via Boot's builder | Check bean/customizer, correct package, and JsonNode assertions |
| `Jackson2ObjectMapperBuilderCustomizer` not found | Boot 3 vs 4 mix-up, wrong dependency or import | Boot 3.5 uses `org.springframework.boot.autoconfigure.jackson.*` |
| `com.fasterxml.jackson.*` imports fail after moving to Boot 4 | Boot 4 prefers Jackson 3 with `tools.jackson.*` packages | Read the migration guide, update APIs, or use Jackson 2 compatibility intentionally |
| Syntactically invalid JSON still rejected despite `unknown-properties=false` | This flag does not permit invalid JSON syntax | Check `HttpMessageNotReadableException` and parser errors |
| Changing `time-zone` does not affect `LocalDateTime` | `LocalDateTime` carries no offset/zone | Choose the right domain type or `@JsonFormat` per contract |
| Java Time fails to serialize | Manual `new ObjectMapper()` missing required module | Use the Boot-managed mapper or register `JavaTimeModule` appropriately |
| Two customizers conflict | Both modify the same feature with different orders | Define explicit order, reduce overlapping config, and test JSON |
| WebFlux endpoint uses a different format from MVC | Different codecs/mappers registered | Check custom `CodecCustomizer`, Jackson encoder/decoder |
| 406 when `Accept` is XML | Server only supports JSON or mapping only produces JSON | Check content negotiation/codecs, not only Jackson properties |
| 415 when sending `text/plain` to a JSON endpoint | Wrong `Content-Type` or `consumes` | Fix request headers/body contract |
| JSON field omitted but business validation does not run | `NON_NULL` controls output, does not validate input | Use `@Valid`, Bean Validation, and service constraints |

### 19.1. Diagnose with Tests, Not Guesses from Logs

A systematic approach:

1. Call `objectMapper.writeValueAsString(new ProductResponse(...))` with the application-injected mapper bean.
2. Call the real API or MockMvc/WebTestClient with the corresponding DTO.
3. Compare the JSON across both layers.
4. If `ObjectMapper` is right but HTTP is wrong, check converters/codecs and return types.
5. If both are wrong, check property loading, `@Configuration`, component scanning, and customizer order.
6. If only one field is wrong, look for `@JsonProperty`/`@JsonFormat`/`@JsonInclude` or a custom serializer on that type.
7. If input fails, inspect `Content-Type`, request body, validation, and actual exceptions.

With Spring Boot Actuator, endpoints such as `/actuator/configprops` or `/actuator/env` can help inspect effective properties when installed and properly secured. Never expose full configurations or secrets publicly to debug JSON.

## 20. Pre-Merge Checklist

- [ ] Verified the Spring Boot/Jackson version running; e.g., Jackson 2 applies to corresponding Boot 3.x versions.
- [ ] Used `spring.jackson.*` where properties exist instead of hastily creating a custom `ObjectMapper`.
- [ ] Naming strategy matches client contracts without breaking released APIs.
- [ ] Null inclusion/unknown field behavior is deliberately chosen and tested.
- [ ] Not confusing `Accept`/`Content-Type`/`consumes`/`produces` with serialization/deserialization.
- [ ] Required Java Time or Optional modules are not lost after customization.
- [ ] Custom serializers/deserializers apply only to appropriate types without unintended overrides.
- [ ] Customizer beans reside in a Spring-scanned package with explicit order if conflicts exist.
- [ ] Avoided creating multiple `ObjectMapper` beans that cause ambiguity and alter converters unexpectedly.
- [ ] Tested both serialization and deserialization across the actual HTTP boundary, not just `ObjectMapper` in isolation.
- [ ] Checked security, secret fields, mass assignment, and JSON payload limits.
- [ ] All global JSON changes have regression tests for affected clients and message schemas.

## 21. Key Takeaways

In **Spring Boot 3.5.x**, `spring.jackson.*` is the declarative configuration layer for common Jackson 2 features: naming, null inclusion, date/time, and serialization/deserialization features. `Jackson2ObjectMapperBuilderCustomizer` is the extension point for adding behavior not well expressed by properties, especially serializers/deserializers for custom types.

**You do not need to replace ObjectMapper to change a small setting.** Use the Boot-managed builder, scope extensions clearly, and test the actual mapper used by MVC converters/WebFlux codecs. Before upgrading to Spring Boot 4.x, review the Jackson 3 migration since the default API and customizer group have changed.

## Official Documentation

- [Spring Boot 3.5 — Common Application Properties: JSON](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/)
- [Spring Boot 3.5.16 — Jackson2ObjectMapperBuilderCustomizer API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/jackson/Jackson2ObjectMapperBuilderCustomizer.html)
- [Spring Boot 3.5 — Spring MVC JSON Customization](https://docs.spring.io/spring-boot/3.5/how-to/spring-mvc.html)
- [Spring Framework 6.2 — Jackson2ObjectMapperBuilder API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/http/converter/json/Jackson2ObjectMapperBuilder.html)
- [Spring Boot 4 — JSON (Jackson 3 and Jackson 2 compatibility)](https://docs.spring.io/spring-boot/reference/features/json.html)
