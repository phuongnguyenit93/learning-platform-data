# Jackson, ObjectMapper, and Spring Boot Auto-Configuration

## Learning Objectives

When building a REST API, a Spring Boot application often needs to convert JSON in an HTTP request into Java objects and transform Java objects into a JSON response. **Jackson** is a popular library that performs this process. **ObjectMapper** is the centerpiece of Jackson 2; Spring Boot also adds auto-configuration so controllers and HTTP clients can use Jackson without manually instantiating every component.

After this lesson, you will be able to:

- Distinguish serialization, deserialization, JSON mapper, module, HTTP message converter, and reactive codec.
- Understand under what conditions Spring Boot 3.5 automatically creates a Jackson 2 ObjectMapper and how it integrates with Spring MVC/WebFlux.
- Customize Jackson using application.properties, annotations, Jackson2ObjectMapperBuilderCustomizer, Module, and @JsonComponent.
- Know when you need to create an ObjectMapper manually and which auto-configurations may back off when replacing the default bean.
- Choose the right Java types for JSON: record/DTO, Instant/LocalDate, optional fields, generic List, JsonNode.
- Distinguish malformed JSON errors, content negotiation errors, and mapping errors in an HTTP API.
- Understand major changes when upgrading to Spring Boot 4.x: Jackson 3, JsonMapper, new packages, and settings to review.
- Write and test a Java 17+ JSON endpoint based on the Boot-configured mapper.

## 1. Where Does Jackson Sit in the HTTP Pipeline?

For example, a client sends JSON:

~~~http
POST /api/orders HTTP/1.1
Content-Type: application/json
Accept: application/json

{"customer_name":"An","quantity":2}
~~~

The controller wants to receive a Java record CreateOrderRequest and return an OrderView. Conceptually:

~~~text
HTTP request
  headers + JSON bytes
          |
          v
Spring HTTP message reader/converter
          |
          v
Jackson deserialization
          |
          v
CreateOrderRequest Java object
          |
          v
@Controller / @RestController
          |
          v
OrderView Java object
          |
          v
Jackson serialization
          |
          v
HTTP message writer/converter
          |
          v
HTTP response: Content-Type + JSON bytes
~~~

Distinguish the responsibilities:

| Component | Responsibility |
|---|---|
| Jackson | Reads/writes the JSON format and maps it to Java types. |
| ObjectMapper in Jackson 2 | Object-level API managing serializers, deserializers, modules, naming, features, and the JSON tree. |
| HttpMessageConverter in Spring MVC | Connects reading/writing the HTTP body with Java objects according to media type. |
| HttpMessageReader/HttpMessageWriter in Spring WebFlux | Connects the reactive body with the appropriate codec, supporting asynchronous data streaming. |
| Spring Boot auto-configuration | Creates/configures the mapper and integrates it when classpath/bean conditions are met. |
| Bean/DTO annotation | Describes specific serialization/deserialization rules per type or property. |

Jackson does not decide the URL route or HTTP status. A syntactically valid JSON body can still be rejected because the endpoint does not support the Content-Type. Conversely, a 200 status does not prove that the JSON was serialized according to the API contract.

## 2. Serialization and Deserialization

**Serialization** converts a Java object into JSON:

~~~text
new User(7, "An")  ->  {"id":7,"name":"An"}
~~~

**Deserialization** converts JSON into a Java object:

~~~text
{"id":7,"name":"An"}  ->  new User(7, "An")
~~~

Jackson typically maps types such as:

| JSON | Typical Java Type | Notes |
|---|---|---|
| string | String | Requires encoding conventions and length limits from the API. |
| integer number | int, long, BigInteger | Overly large numbers can cause errors or overflow if cast improperly. |
| decimal number | BigDecimal, double | Use BigDecimal when decimal precision is required, such as currency. |
| boolean | boolean, Boolean | Wrapper types can represent null. |
| null | Object reference null | Primitives cannot hold null; a clear handling strategy is needed. |
| object | POJO, record, Map, JsonNode | Use a concrete DTO when the contract is known. |
| array | List<T>, T[], Collection<T> | Generic types require type information during manual deserialization. |
| ISO date/time string | Instant, OffsetDateTime, LocalDate | Requires an appropriate module/format; distinguish timezones. |

A DTO used to transfer data over HTTP should generally be independent of the JPA entity. Do not directly expose entity relationships, lazy proxies, passwords, internal fields, or database structure unless the API contract explicitly requires it.

### Java Records and Jackson

With Java 17+, a record is often a concise choice for an immutable DTO:

~~~java
public record UserView(long id, String name) {
}
~~~

When Jackson and a version supporting records are present, it can read and write record components. Annotations such as @JsonProperty or @JsonIgnore help adjust property names and visibility.

## 3. How Does Spring Boot 3.5 Auto-Configure ObjectMapper?

Most runnable examples in this lesson use **Spring Boot 3.5.x + Java 17+**, which defaults to Jackson 2.

With Spring Boot 3.5:

1. Appropriate dependencies bring Jackson onto the classpath; typically the Spring Web or Spring Reactive Web starter already pulls in the required JSON starter.
2. Spring Boot applies **JacksonAutoConfiguration** when its conditions are satisfied.
3. Boot auto-configures **Jackson2ObjectMapperBuilder**, then creates an **ObjectMapper bean** if no existing bean causes auto-configuration to back off.
4. Boot applies **spring.jackson.*** properties and **Jackson2ObjectMapperBuilderCustomizer** beans.
5. **com.fasterxml.jackson.databind.Module** beans are registered into the Boot-managed builder.
6. MVC or WebFlux integrates the JSON mapper into HTTP converters/codecs when properly configured by Boot/Spring.

Simplified diagram:

~~~text
spring-boot-starter-web / spring-boot-starter-webflux
                  |
                  v
            Jackson on classpath
                  |
                  v
         JacksonAutoConfiguration
                  |
      +-----------+--------------+
      |                          |
spring.jackson.*         Jackson2ObjectMapperBuilderCustomizer
      |                          |
      +------------+-------------+
                   |
                   v
          Jackson2ObjectMapperBuilder
                   |
                   +-- Module beans / Jackson support
                   |
                   v
             ObjectMapper bean
                   |
          +--------+---------+
          |                  |
        Spring MVC         Spring WebFlux
      HTTP converter        JSON codec
~~~

The diagram illustrates the common auto-configuration path; it does not assert that every ObjectMapper or every manually created HTTP client uses the exact same object instance. For example, a WebClient you create manually with custom ExchangeStrategies may have different codec settings.

**Important:** Spring Boot does not necessarily define an ObjectMapper bean if Jackson is not on the classpath, if you have already defined a replacement bean, or if the relevant auto-configuration conditions are not met.

### Boot 3.5 Defaults to Know

According to official Spring Boot 3.5 documentation, the Boot-configured mapper typically has the following settings:

- MapperFeature.DEFAULT_VIEW_INCLUSION: disabled.
- DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES: disabled.
- SerializationFeature.WRITE_DATES_AS_TIMESTAMPS: disabled.
- SerializationFeature.WRITE_DURATIONS_AS_TIMESTAMPS: disabled.

Accordingly:

- JSON with unknown properties is typically ignored by default during deserialization, though this can be switched to strict.
- java.time types can be serialized into appropriate date/time representations instead of numeric timestamps when the corresponding module is supported.
- Do not use a manually instantiated `new ObjectMapper()` as the reference to infer the behavior of the Boot-configured mapper.

These defaults may differ when moving to Spring Boot 4.x/Jackson 3, when the application replaces the bean itself, or when other customizers are present.

## 4. Dependencies and Choosing Versions

### Maven for Spring Boot 3.5

A Spring MVC project with the Boot parent/BOM can use:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
~~~

A WebFlux project:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
~~~

Both typically bring in Jackson 2 JSON support through the appropriate starter. Do not manually pin separate jackson-databind, jackson-core, or jackson-annotations versions that conflict with the Spring Boot BOM.

### Gradle

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

If using Spring Boot 4.x, starters and JSON modules have been reorganized by major version: use the corresponding starters and inspect the dependency tree. This lesson intentionally keeps runnable Java examples consistent with Boot 3.5, while the Boot 4 upgrade section highlights the differences.

Check dependencies when encountering class errors:

~~~bash
./mvnw dependency:tree
~~~

Or:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Dependencies coming from plugins or external libraries can pull in Jackson 2 in a Boot 4 application, so you must know whether you are using a Jackson 2 or Jackson 3 mapper.

## 5. Using ObjectMapper Outside Controllers

In Jackson 2:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;

ObjectMapper mapper = ...;

String json = mapper.writeValueAsString(value);
UserView user = mapper.readValue(json, UserView.class);
~~~

This is an illustrative API snippet; it requires an object value and appropriate exception handling. These methods are convenient when JSON is needed outside HTTP, such as message queues, files, or object mapping in certain workflows.

### Java 17+ Example with Injected ObjectMapper

~~~java
package com.example.json;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Service;

@Service
public class JsonTextService {

    private final ObjectMapper mapper;

    public JsonTextService(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    public String toJson(Object value) throws JsonProcessingException {
        return mapper.writeValueAsString(value);
    }
}
~~~

Here, Spring injects an ObjectMapper bean that it can resolve. In a Boot 3.5 application with no replacement mapper, the bean is typically the auto-configured mapper.

**Do not overuse ObjectMapper in @RestController:** If a controller returns an object or ResponseEntity<T>, Spring already uses the appropriate HTTP converter/codec. There is no need to call writeValueAsString and return a String, as this can easily cause incorrect media types or escaping, or even double-encoded JSON.

### Generic List and JavaType

This snippet does not preserve full generic type information:

~~~java
List<?> values = mapper.readValue(json, List.class);
~~~

When deserializing an object list, Jackson may create Maps instead of DTOs. With Jackson 2, use TypeReference or JavaType:

~~~java
List<UserView> users = mapper.readValue(
    json,
    new com.fasterxml.jackson.core.type.TypeReference<List<UserView>>() {}
);
~~~

The example above requires List and UserView to be imported and defined. That is why generic type information should not be dropped when manually reading JSON outside HTTP.

### JsonNode for JSON Trees

If the schema is only known at runtime or you only need to inspect a few fields, you can use:

~~~java
JsonNode root = mapper.readTree(json);
String name = root.path("name").asText("");
~~~

JsonNode is Jackson's tree API, suitable for flexible data; however, if the contract is stable, concrete DTOs are easier to validate, test, and maintain.

## 6. Customizing via application.properties

With Spring Boot 3.5, the simplest way to change application-wide JSON policies configured by Boot is to set **spring.jackson.*** properties.

Example:

~~~properties
spring.jackson.default-property-inclusion=non_null
spring.jackson.serialization.indent_output=true
spring.jackson.serialization.write-dates-as-timestamps=false
spring.jackson.deserialization.fail-on-unknown-properties=false
~~~

Meaning:

| Property | Effect | Notes |
|---|---|---|
| spring.jackson.default-property-inclusion=non_null | Omits properties with null values under the global inclusion policy. | Does not mean empty strings or empty lists are omitted; a different policy is needed for that. |
| spring.jackson.serialization.indent_output=true | Pretty-prints JSON instead of compact formatting. | Increases response byte size; evaluate before enabling in production. |
| spring.jackson.serialization.write-dates-as-timestamps=false | When the appropriate date/time module is present, prefers string date/time representation. | Does not automatically choose a timezone for every field. |
| spring.jackson.deserialization.fail-on-unknown-properties=true | Switches to strict mode when input contains properties not recognized by the DTO. | Can cause older clients to get 400 when the API adds unsupported fields. |

The configuration snippet above illustrates **false** for unknown-properties to match the Boot 3.5 default. If you want strict mode, intentionally switch it to true and add integration tests.

Property binding does not replace input validation. For example, a request with quantity = -3 is valid JSON and can be deserialized into an int, but business logic still requires Bean Validation or explicit checks.

### Equivalent YAML

~~~yaml
spring:
  jackson:
    default-property-inclusion: non_null
    serialization:
      indent_output: true
      write-dates-as-timestamps: false
    deserialization:
      fail-on-unknown-properties: false
~~~

Do not place conflicting settings for the same key across multiple profile files, environment variables, or command-line arguments without knowing the override order. The effective value depends on Spring Boot's externalized configuration mechanism.

## 7. Jackson Annotations to Adjust a Single DTO

Common annotations in Jackson 2 (many of which continue to exist when migrating to Jackson 3):

| Annotation | Purpose | Example |
|---|---|---|
| @JsonProperty | Renames a field in JSON or declares property name/metadata. | orderId to order_id. |
| @JsonIgnore | Ignores a property during serialization/deserialization as configured. | Excludes internalNote. |
| @JsonInclude | Selects the condition for a property to appear in JSON. | NON_NULL for a DTO. |
| @JsonFormat | Adjusts date/time representation, pattern, or shape. | LocalDate in a specific date format. |
| @JsonCreator | Specifies how Jackson constructs an object via a factory/constructor when needed. | Complex immutable DTOs. |
| @JsonAlias | Accepts alternative input names during deserialization. | Supports property renaming when receiving JSON. |
| @JsonView | Groups properties by JSON view. | Different API outputs. |
| @JsonTypeInfo | Explicitly controls polymorphic metadata. | Type hierarchies with a clear contract. |

Do not add annotations "just in case": choose a consistent JSON contract. For example, if using a global SNAKE_CASE naming strategy, you do not necessarily need to write @JsonProperty on every field.

### Record Example with JSON Name and Internal Field

~~~java
package com.example.json;

import java.time.Instant;

import com.fasterxml.jackson.annotation.JsonIgnore;
import com.fasterxml.jackson.annotation.JsonProperty;

public record OrderView(
        @JsonProperty("order_id") long id,
        String customer,
        Instant createdAt,
        @JsonIgnore String internalNote,
        String note
) {
}
~~~

With the Boot-configured Jackson 2 mapper and the NON_NULL policy applied:

~~~java
OrderView view = new OrderView(
    7,
    "An",
    Instant.parse("2026-01-02T03:04:05Z"),
    "not-for-clients",
    null
);
~~~

Equivalent JSON in terms of values (no fixed property order required):

~~~json
{
  "order_id": 7,
  "customer": "An",
  "createdAt": "2026-01-02T03:04:05Z"
}
~~~

internalNote is omitted due to @JsonIgnore; the null note is omitted due to global NON_NULL. With Jackson Java Time support and WRITE_DATES_AS_TIMESTAMPS=false, Instant is serialized in ISO-8601 format.

**Security note:** @JsonIgnore on an output DTO is not a complete substitute for separating domain entities from response schemas. If an application returns a JPA entity directly, lazy relationships, private data, or proxy mechanisms can produce hard-to-control side effects.

### @JsonFormat and Timezones

~~~java
public record ReportView(
    @JsonFormat(pattern = "yyyy-MM-dd") LocalDate reportDate
) {
}
~~~

Formatting LocalDate differs from Instant, which represents a point in time with an offset/timezone. Do not convert Instant to a local time string without stating the timezone. For APIs spanning multiple timezones, prefer UTC or OffsetDateTime/Instant according to a clear contract.

## 8. Java Time: Why Does the Module Matter?

Jackson 2 requires proper support for java.time (such as JavaTimeModule from jackson-datatype-jsr310). Spring Boot typically registers well-known modules when they are present via dependency management/starters.

If you manually create an ObjectMapper using `new ObjectMapper()` without the required module, types like LocalDate, Instant, or OffsetDateTime may not serialize/deserialize the way the Boot-managed mapper does.

A manual Jackson 2 approach:

~~~java
ObjectMapper custom = new ObjectMapper();
custom.registerModule(new JavaTimeModule());
custom.disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
~~~

To compile, you need the imports:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
~~~

The snippet above only illustrates Jackson 2 and is **not** the default approach for a Boot application: doing so bypasses many other auto-configuration features if you use that custom mapper to replace the default bean. Prefer the Boot-configured mapper, properties, or a builder customizer when appropriate.

When using Jackson 3 in Boot 4, module/feature mechanisms and packages change. Do not copy Jackson 2 imports into a Jackson 3 project without checking the migration guide.

## 9. Jackson2ObjectMapperBuilderCustomizer in Boot 3.5

One way to customize globally while preserving Spring Boot's mapper building process is to declare a **Jackson2ObjectMapperBuilderCustomizer** bean.

Example enabling strict unknown-property handling:

~~~java
package com.example.json;

import com.fasterxml.jackson.databind.DeserializationFeature;
import org.springframework.boot.autoconfigure.jackson.Jackson2ObjectMapperBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class JacksonConfig {

    @Bean
    Jackson2ObjectMapperBuilderCustomizer strictJson() {
        return builder -> builder.featuresToEnable(
            DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES
        );
    }
}
~~~

This is an **alternative configuration** to setting fail-on-unknown-properties=false in section 6. Do not declare both with conflicting values in the same demo; choose one strategy and test the actual behavior.

Advantages:

- Boot still creates and manages the ObjectMapper through the builder.
- Other Boot configurations continue to apply.
- Multiple customizer beans can be used, though conflicts should be avoided and ordering should be specified when callbacks modify the same feature.

Use a customizer only for things that cannot be conveniently expressed via properties or when controlled logic is needed. If you only want to omit nulls from JSON, the `spring.jackson.default-property-inclusion` property is usually easier to read and operate.

### Customizer Ordering

Spring Boot has a default customizer with its own order. Application customizers can use @Order or Ordered to run before or after it; order matters when configuring the same property. Do not rely on arbitrary bean order or assume a later customizer always overrides in every situation if the builder applies specialized callbacks.

## 10. Module and @JsonComponent for Custom Serializers/Deserializers

Jackson supports modules to package serializers, deserializers, and additional features. In Boot 3.5, beans of type **com.fasterxml.jackson.databind.Module** are automatically integrated into the Boot-managed mapper builder.

If you need special formatting for a business data type, you can:

1. Use @JsonFormat or @JsonProperty for simple needs.
2. Create a custom JsonSerializer/JsonDeserializer and register it via a SimpleModule bean.
3. Or use Spring Boot 3.5 **@JsonComponent** to register serializer/deserializer beans conveniently.

Example of a Jackson 2 serializer for a Money type, represented as a string:

~~~java
package com.example.json;

import java.io.IOException;
import java.math.BigDecimal;

import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.databind.JsonSerializer;
import com.fasterxml.jackson.databind.SerializerProvider;

public record Money(BigDecimal amount, String currency) {
}

class MoneySerializer extends JsonSerializer<Money> {

    @Override
    public void serialize(
            Money money,
            JsonGenerator out,
            SerializerProvider serializers
    ) throws IOException {
        out.writeString(money.amount().toPlainString()
            + " " + money.currency());
    }
}
~~~

This snippet illustrates two logically related types together; in standard Java source files, you must separate `public record Money` into **Money.java** and create a non-public **MoneySerializer.java**, or organize the classes according to Java rules. A custom serializer changes how Money appears in responses; ensure the API contract for the currency string is clear.

Registering via a SimpleModule bean:

~~~java
@Configuration(proxyBeanMethods = false)
class MoneyModuleConfig {

    @Bean
    com.fasterxml.jackson.databind.Module moneyModule() {
        SimpleModule module = new SimpleModule();
        module.addSerializer(Money.class, new MoneySerializer());
        return module;
    }
}
~~~

To compile this bean snippet, import @Bean, @Configuration, and **com.fasterxml.jackson.databind.module.SimpleModule**, and ensure Money/MoneySerializer are in the right package.

**Do not assume a custom serializer is automatically bidirectional:** A serializer only writes JSON. If you want to read the string "12.50 USD" back into Money, you need a corresponding custom deserializer, or choose a JSON object structure that is easier to deserialize.

### @JsonComponent

Spring Boot 3.5 supports the annotation:

~~~java
import org.springframework.boot.jackson.JsonComponent;
~~~

You can place @JsonComponent on a JsonSerializer/JsonDeserializer bean or an enclosing class containing implementations so Boot detects and registers them into the mapper, per the official guide. With Jackson 3/Spring Boot 4, the name is changed to **@JacksonComponent**; do not use the old import for Boot 4 examples.

## 11. When Should You NOT Declare Your Own @Bean ObjectMapper?

The following example often causes surprises:

~~~java
@Configuration
public class JsonConfig {

    @Bean
    ObjectMapper objectMapper() {
        return new ObjectMapper();
    }
}
~~~

An application-declared ObjectMapper bean can cause Boot's default ObjectMapper auto-configuration to **back off**. When that happens, features that previously went through the Boot builder, properties, and Module beans may not be applied to the object you just instantiated.

Observed symptoms:

- Instant or LocalDate no longer serializes as before.
- JSON naming or null inclusion differs from spring.jackson.*.
- A custom Module bean or @JsonComponent is not attached to the replacement mapper as expected.
- REST controllers and object-to-JSON utilities use two mappers with different behaviors.

Prefer the following order:

1. `spring.jackson.*` properties if a suitable property exists.
2. Jackson annotations for rules specific to one DTO/property.
3. Jackson2ObjectMapperBuilderCustomizer for adjusting Boot 3.5's builder.
4. Module or @JsonComponent when custom serializers/deserializers are needed.
5. Only replace the ObjectMapper bean yourself when you deliberately want full control, have thorough tests, and understand which auto-configurations back off.

If you need a different mapper for **only one** internal feature, create a separate mapper with a clear name/qualifier and do not accidentally make it a global candidate replacing the web layer's JSON mapper. With multiple beans, use @Primary/@Qualifier appropriately and verify which mapper MVC/WebFlux actually uses.

### Should You Replace ObjectMapper with new ObjectMapper() Per Request?

No. Repeatedly creating a mapper incurs configuration/initialization overhead and easily introduces configuration discrepancies. A mapper is generally thread-safe to share once **fully configured before use**. Once requests are being served, avoid mutating the mapper's global configuration across concurrent threads; use ObjectReader/ObjectWriter or a dedicated mapper for special requirements.

## 12. Complete Spring Boot 3.5 + Java 17+ Example

The following example uses Spring Boot 3.5.x, Java 17+, and **spring-boot-starter-web**. Create a project from Spring Initializr or a Maven project with the Spring Boot parent/BOM. You do not need to declare an ObjectMapper bean; Boot will manage the mapper.

### 12.1. application.properties

File: src/main/resources/application.properties

~~~properties
server.port=8080
spring.jackson.default-property-inclusion=non_null
spring.jackson.serialization.write-dates-as-timestamps=false
~~~

This demo does not use a strict-mode customizer. When a POST has valid input, the controller uses Jackson to read the DTO; on GET, the controller returns an object for Spring to write as JSON.

### 12.2. JsonApplication.java

File: src/main/java/com/example/json/JsonApplication.java

~~~java
package com.example.json;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JsonApplication {

    public static void main(String[] args) {
        SpringApplication.run(JsonApplication.class, args);
    }
}
~~~

### 12.3. OrderView.java

File: src/main/java/com/example/json/OrderView.java

~~~java
package com.example.json;

import java.time.Instant;

import com.fasterxml.jackson.annotation.JsonIgnore;
import com.fasterxml.jackson.annotation.JsonProperty;

public record OrderView(
        @JsonProperty("order_id") long id,
        String customer,
        Instant createdAt,
        @JsonIgnore String internalNote,
        String note
) {
}
~~~

### 12.4. CreateOrderRequest.java

File: src/main/java/com/example/json/CreateOrderRequest.java

~~~java
package com.example.json;

import com.fasterxml.jackson.annotation.JsonProperty;

public record CreateOrderRequest(
        @JsonProperty("customer_name") String customer,
        int quantity
) {
}
~~~

### 12.5. OrderController.java

File: src/main/java/com/example/json/OrderController.java

~~~java
package com.example.json;

import java.net.URI;
import java.time.Instant;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final AtomicLong sequence = new AtomicLong(6);

    @GetMapping("/{id}")
    public OrderView get(@PathVariable long id) {
        return new OrderView(
            id,
            "An",
            Instant.parse("2026-01-02T03:04:05Z"),
            "internal-secret",
            null
        );
    }

    @PostMapping
    public ResponseEntity<OrderView> create(
            @RequestBody CreateOrderRequest request) {

        if (request.customer() == null || request.customer().isBlank()
                || request.quantity() <= 0) {
            return ResponseEntity.badRequest().build();
        }

        long id = sequence.incrementAndGet();
        OrderView created = new OrderView(
            id,
            request.customer().trim(),
            Instant.parse("2026-01-02T03:04:05Z"),
            "internal-secret",
            null
        );

        return ResponseEntity
            .created(URI.create("/api/orders/" + id))
            .body(created);
    }
}
~~~

The controller demonstrates JSON conversion without a database. Returning mock data on GET for any id simply focuses on JSON mapping and does not represent production REST business logic.

**Validation note:** The if check in the controller is a minimal example; real systems should use Bean Validation, DTO constraints, exception handling, and appropriate business rules.

### 12.6. Running the Application and Inspecting JSON

Run the Maven Wrapper from the project root:

~~~bash
./mvnw spring-boot:run
~~~

On Windows:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Call GET:

~~~bash
curl -i -H "Accept: application/json" http://localhost:8080/api/orders/7
~~~

Expected status is 200, with Content-Type compatible with application/json. The JSON has equivalent fields and values:

~~~json
{
  "order_id": 7,
  "customer": "An",
  "createdAt": "2026-01-02T03:04:05Z"
}
~~~

**internalNote** is excluded via @JsonIgnore; **note** is excluded via NON_NULL. Field order or whitespace in the body must not be used as a success criterion if the API contract does not mandate ordering.

Call POST:

~~~bash
curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"customer_name":"Binh","quantity":2}'
~~~

In a freshly started process, sequence starts at 6, so the first POST creates order_id 7. The response has status 201 Created and Location: /api/orders/7. The JSON body contains customer: "Binh" and createdAt from the demo data.

Send an invalid business request:

~~~bash
curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{"customer_name":"","quantity":0}'
~~~

The controller returns 400 Bad Request because the data is invalid. This is **not** a Jackson error: the JSON is still syntactically valid and was deserialized successfully.

## 13. Testing the JSON Mapper and HTTP Contract

Use **spring-boot-starter-test** with Spring Boot 3.5. If the project uses Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

### 13.1. Testing HTTP with MockMvc

File: src/test/java/com/example/json/OrderControllerTest.java

~~~java
package com.example.json;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class OrderControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void jsonUsesConfiguredNamingAndExclusion() throws Exception {
        mvc.perform(get("/api/orders/7")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.order_id").value(7))
            .andExpect(jsonPath("$.customer").value("An"))
            .andExpect(jsonPath("$.createdAt")
                .value("2026-01-02T03:04:05Z"))
            .andExpect(jsonPath("$.internalNote").doesNotExist())
            .andExpect(jsonPath("$.note").doesNotExist());
    }
}
~~~

The test verifies Spring Boot's **actual HTTP serializer** output, not just an ObjectMapper called manually. When a project uses Spring Boot 4.x, some test auto-configuration packages have changed; use imports matching that version.

### 13.2. Testing the Mapper Independently

A unit test for the Boot-injected ObjectMapper can verify both serialization and deserialization:

~~~java
@Autowired
ObjectMapper mapper;

@Test
void jacksonReadsInputDto() throws Exception {
    String json = "{\"customer_name\":\"Binh\",\"quantity\":2}";
    CreateOrderRequest input =
        mapper.readValue(json, CreateOrderRequest.class);

    assertEquals("Binh", input.customer());
    assertEquals(2, input.quantity());
}
~~~

This snippet illustrates a method in a JUnit class with a configured Spring test context and imports, including assertEquals from JUnit. Do not use `new ObjectMapper()` in tests if the goal is to verify the Boot-managed bean used by the application.

### 13.3. Testing Strict Unknown Properties

If you set `spring.jackson.deserialization.fail-on-unknown-properties=true`, send JSON containing an undeclared field and verify that deserialization is rejected according to the contract.

If you keep the Boot 3.5 default, JSON with unknown fields can still deserialize, but ignoring fields is not necessarily safe for every business case. Choose strict or tolerant based on explicit backward/forward compatibility requirements.

## 14. JSON and Spring MVC: HttpMessageConverter

In Spring MVC, the HTTP message converter determines how to read/write the body. For Jackson 2, the common converter is **MappingJackson2HttpMessageConverter**, which pairs with the mapper to convert JSON.

Example controller:

~~~java
@PostMapping(
    path = "/api/users",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
public UserView create(@RequestBody UserView input) {
    return input;
}
~~~

This is an illustrative method inside a @RestController; appropriate imports are required. Content-Type describes the **request body** format, while Accept relates to the **response** format desired by the client.

If you provide your own MappingJackson2HttpMessageConverter bean, be aware: in some Boot configurations, a custom converter bean may **replace** the corresponding default converter. This can prevent expected ObjectMapper features/modules from being used.

Do not add @EnableWebMvc just to make JSON work in a standard Boot project. @EnableWebMvc can cause Boot MVC auto-configuration to back off, altering how converters, static resources, and other integrations are configured.

An application may return HTTP status 415 Unsupported Media Type when a request has no matching reader or its Content-Type is not accepted, and 406 Not Acceptable when no writer exists for the response media type requested by the client. These are not always Jackson parser errors.

## 15. JSON and Spring WebFlux: Codecs Instead of Servlet Converters

In WebFlux, reactive bodies are processed through **HttpMessageReader/HttpMessageWriter** and Encoder/Decoder. Jackson still performs serialization/deserialization, but processing is tied to the reactive pipeline, DataBuffer, and subscribers.

Example:

~~~java
@PostMapping("/api/echo")
public Mono<EchoResponse> echo(
        @RequestBody Mono<EchoRequest> input) {
    return input.map(value ->
        new EchoResponse(value.message())
    );
}
~~~

This is an illustrative method in a WebFlux @RestController; it requires concrete DTOs/imports and is not a standalone runnable file. The framework subscribes to the Publisher and uses the appropriate JSON codec.

### maxInMemorySize Is Not Purely a Jackson Setting

With WebFlux, the JSON decoder may need to buffer data to decode an object. If it exceeds the threshold, `DataBufferLimitException` can occur.

Example property in Boot versions that support it:

~~~properties
spring.http.codecs.max-in-memory-size=1MB
~~~

This property relates to **codec buffering**, not an ObjectMapper feature or the maximum length of all uploads. Do not blindly raise it to hundreds of MB instead of considering streaming, gateway limits, multipart handling, and memory budgets.

In Boot 3.5, you can use **org.springframework.boot.web.codec.CodecCustomizer** to configure the Boot-managed CodecConfigurer. In Boot 4.x, the CodecCustomizer package also changes. Codec/server/client changes must be tested separately alongside the JSON mapper.

### WebClient May Use a Different Mapper/Configuration

A Spring Boot auto-configured WebClient can receive appropriate Boot customizations. A WebClient created manually via `WebClient.builder()` with custom strategies does **not automatically** inherit every mapper/codec bean configured by the application.

When you see JSON responses from an outbound WebClient differing from controller JSON responses:

1. Identify the **server's** mapper/codec.
2. Identify the **client's** mapper/codec.
3. Compare naming, modules, media types, date handling, and maxInMemorySize.
4. Check whether a separate JsonMapper/ObjectMapper or ExchangeStrategies was created manually.

## 16. Major Change: Spring Boot 4.x and Jackson 3

**This is a version-specific distinction.** Spring Boot 4.x prefers **Jackson 3**, whereas the runnable examples above use **Jackson 2 in Boot 3.5**.

According to Spring Boot 4.x documentation:

- Jackson 3 is the **default and preferred** JSON library.
- Instead of configuring a Jackson 2 ObjectMapper bean as the Boot 3.5 default, Boot 4 auto-configures **JsonMapper** for Jackson 3.
- Most Jackson 3 packages and Maven group IDs change from com.fasterxml.jackson to **tools.jackson**. An important exception is **jackson-annotations**, which retains com.fasterxml.jackson.annotation and its historical group ID.
- Customizer classes are renamed or adjusted in API: from **Jackson2ObjectMapperBuilderCustomizer** to **JsonMapperBuilderCustomizer**.
- Jackson 2 compatibility in Boot 4 includes the **spring-boot-jackson2** module, but this support is marked deprecated and should only be used as a transition bridge.
- Spring Boot 4.0 adds discovery for additional Jackson modules from the classpath; check for serialization differences when upgrading.
- Several JSON read/write properties move into the **spring.jackson.json.read.*** and **spring.jackson.json.write.*** namespaces.
- Boot integration annotations like **@JsonComponent** and **@JsonMixin** are renamed to **@JacksonComponent** and **@JacksonMixin** per the upgrade documentation.

Comparison table:

| Item | Spring Boot 3.5 / Jackson 2 | Spring Boot 4.x / Jackson 3 |
|---|---|---|
| Default JSON mapper | com.fasterxml.jackson.databind.ObjectMapper | JsonMapper from Jackson 3, under tools.jackson |
| Builder customizer | Jackson2ObjectMapperBuilderCustomizer | JsonMapperBuilderCustomizer |
| Jackson databind namespace | com.fasterxml.jackson.databind | tools.jackson.databind (and subpackages) |
| Jackson annotations | com.fasterxml.jackson.annotation | Many annotations keep com.fasterxml.jackson.annotation |
| Custom serializer API | JsonSerializer / JsonDeserializer from Jackson 2 | Jackson 3 serializer/deserializer APIs changed; check migration guide |
| Boot component annotation | @JsonComponent | @JacksonComponent |
| Legacy mapper compatibility | Primary | Deprecated spring-boot-jackson2 module if still needed |

### How to Customize the Mapper in Boot 4

In Spring Boot 4, use a **JsonMapperBuilderCustomizer** bean or appropriate properties instead of copying Boot 3.5 classes.

Interface name and package published in Boot 4 documentation:

~~~java
import org.springframework.boot.jackson.autoconfigure.JsonMapperBuilderCustomizer;
~~~

Conceptual example:

~~~java
@Bean
JsonMapperBuilderCustomizer jsonMapperCustomizer() {
    return builder -> {
        // Intentional changes on JsonMapper.Builder.
    };
}
~~~

This snippet illustrates the extension point and is not a standalone runnable Java file; do not copy an arbitrary Jackson 2 feature to Jackson 3 without verifying the API. For simple needs, Boot 4 properties are easier to test and migrate.

Specifically: **In Spring Boot 4, defining a Jackson 2 ObjectMapper bean is not enough to replace the auto-configured Jackson 3 JsonMapper.** If you intentionally want to replace the default Jackson 3 JSON mapper, you must manage an appropriate **JsonMapper** bean or customize the builder/bean within the corresponding framework version.

A setting that helps reduce differences during migration:

~~~properties
spring.jackson.use-jackson2-defaults=true
~~~

This is a Boot 4 option to bring JsonMapper defaults closer to Jackson 2/Boot 3. It does not replace JSON contract testing and does not guarantee every Jackson 2 library works under Jackson 3.

When both Jackson 2 and 3 are present, Boot 4 can choose a preferred mapper per integration layer. Relevant properties may include **spring.http.codecs.preferred-json-mapper** for WebFlux and **spring.http.converters.preferred-json-mapper** for MVC. Only set jackson2 when there is a clear transition reason and you have checked the version-specific docs; do not treat a temporary workaround as a long-term target.

### Checklist for Migrating Boot 3.5 → 4.x

1. Confirm the target Boot BOM and supported Java version.
2. Audit all Jackson 2 dependencies and libraries incompatible with Jackson 3.
3. Review com.fasterxml.jackson.databind imports versus tools.jackson.databind.
4. Review custom ObjectMapper beans, Jackson2ObjectMapperBuilderCustomizer, and Module beans.
5. Review custom serializers/deserializers, @JsonComponent/@JsonMixin, and JSON tree APIs.
6. Audit spring.jackson.* feature properties, especially json.read/json.write.
7. Audit date/time, unknown fields, property inclusion, nulls, naming strategy, and polymorphism.
8. Compare JSON snapshot/contract tests in Spring MVC and WebFlux.
9. Check outbound WebClient if it uses a different mapper from the server.
10. Use spring-boot-jackson2 only as a planned transitional step.

## 17. Common Errors and How to Diagnose Them

### 400 Bad Request on Invalid JSON Input

Common causes: malformed JSON syntax, invalid data types, missing constructor/creator, or strict unknown-field policy. Use exception cause logs, DTO schemas, and readValue unit tests to separate parse errors from business validation.

Example:

~~~json
{"quantity": "not-a-number"}
~~~

If the DTO expects an int, the mapper may report a conversion error depending on coercion settings. Do not "fix" it by turning off all validation.

### 415 Unsupported Media Type

The client sent Content-Type text/plain while the controller only accepts application/json; or no matching reader exists. Check Content-Type, consumes, and converters/codecs.

### 406 Not Acceptable

The client requested a response media type that the endpoint/codec does not support. Check Accept, produces, and writers. Do not blame ObjectMapper before checking content negotiation.

### 500 or Serialization Error

May be caused by an unserializable Java type, reference cycle, buggy custom serializer, or missing module. Inspect the root cause; do not expose stack traces in production responses.

### Infinite Recursion with Bidirectional Entity Relationships

An entity referencing a child that in turn references the parent can cause the serializer to loop infinitely. Prefer cycle-free API DTOs. If you must serialize a graph, use appropriate Jackson annotations carefully; never return a raw JPA entity and expect Jackson to infer business relationships.

### Unexpected Dates/Times

Usually caused by a mapper missing the Java Time module, numeric timestamps, timezones, or inconsistent @JsonFormat. Check Instant versus LocalDateTime, test timezones, and verify the schema contract.

### Missing Nulls in JSON

If NON_NULL is set, null fields are omitted. This differs from JSON having `"field": null`. A client may treat **missing** and **null** as two distinct states. Choose the policy based on the API contract.

### @JsonIgnore Hiding a Required Input Property

One annotation can affect both serialization and deserialization. When a field should only be read or only be written, consider separate input/output DTOs or @JsonProperty access rules; do not place @JsonIgnore casually and still expect clients to send that field.

### Manually Created ObjectMapper Ignoring spring.jackson.*

When calling `new ObjectMapper()`, you are no longer automatically using Boot's builder. Check bean creation sites, @Primary, @Qualifier, and injected HTTP converters/codecs. Prefer properties and customizers.

### Missing or Duplicate Module Registration

Especially when integrating multiple libraries, verify the mapper instance and the list of modules actually configured. A custom serializer can be overridden by another module or not registered on the mapper used during requests.

### Polymorphism on Untrusted Input

Do not enable overly broad default typing or deserialize arbitrary Java types from untrusted client payloads. Polymorphic type handling poses security risks if it allows instantiating classes outside a controlled list. Prefer fixed DTOs or an explicit allowlist of subtypes.

### Manually Returning a JSON String in a Controller

If a method returns String, Spring may use a String converter instead of a JSON object converter, producing unexpected Content-Type or escaping. Return an object/record or ResponseEntity<DTO> so the framework uses JSON serialization.

## 18. Pre-Production Checklist for Jackson Changes

- **Version:** Have you distinguished Jackson 2 in Boot 3.5 from Jackson 3 in Boot 4?
- **DTO contract:** Are JSON field names, required/optional status, null/missing semantics, and unknown fields clear?
- **Data types:** Are date/time, BigDecimal, enums, generic Lists, and Unicode tested?
- **Mapper ownership:** Is any manual `new` or `@Bean ObjectMapper/JsonMapper` causing Boot to back off?
- **Customization:** Did you follow property → annotation → customizer → module as needed?
- **Dependency:** Are JSON starters, Jackson modules, and the BOM aligned?
- **Web layer:** Is the MVC converter or WebFlux codec using the right mapper?
- **Security:** Are you avoiding returning sensitive domain entities and broad polymorphic typing on untrusted input?
- **Errors:** Are parse/binding/validation errors distinguished from 406/415 and server errors?
- **Regression:** Do mapper unit tests and HTTP integration tests verify status, Content-Type, and body?
- **Client:** If using WebClient, are outbound/inbound JSON payloads tested?
- **Performance:** Are you avoiding creating mappers per request, serializing excessive data, and buffering large bodies in RAM?
- **Migration:** If moving to Boot 4, have you tested JSON diffs and deprecated Jackson 2 modules?

## 19. Self-Check Questions

1. How do serialization and deserialization differ in conversion direction?
2. What is the role of ObjectMapper in Jackson 2, and why do controllers usually not need to call it manually?
3. In Boot 3.5, which property is appropriate to omit nulls from JSON application-wide?
4. Why can declaring your own `new ObjectMapper()` bean prevent `spring.jackson.*` policies from taking effect?
5. When should you use Jackson2ObjectMapperBuilderCustomizer instead of application.properties?
6. What three purposes do @JsonProperty, @JsonIgnore, and @JsonInclude serve?
7. Why might Instant fail on a manually instantiated ObjectMapper yet work in Boot?
8. At what layer does MappingJackson2HttpMessageConverter differ from a WebFlux JSON decoder?
9. If a request sends Content-Type text/plain to an endpoint that consumes application/json, what is the typical status?
10. If a client requests Accept application/xml but the endpoint only has a JSON writer, what is the typical status?
11. Does Boot 4 prefer Jackson 2 ObjectMapper or Jackson 3 JsonMapper by default?
12. In Boot 4, does a Jackson 2 ObjectMapper bean automatically replace the default JsonMapper?
13. What is the risk of deserializing polymorphic types from untrusted JSON?

### Suggested Answers

1. Serialization is Java → JSON; deserialization is JSON → Java.
2. The mapper manages how JSON is read/written; Spring integrates converters/codecs so controllers can return DTOs directly.
3. `spring.jackson.default-property-inclusion=non_null`.
4. A manually created mapper does not have Boot's builder apply properties, modules, and customizers by default.
5. When you need to customize the builder programmatically or support features without a simple property.
6. Rename a JSON field, ignore a property, and control when a property is included.
7. Missing Java Time module or corresponding settings; Boot usually configures well-known modules.
8. MVC uses HttpMessageConverter on the Servlet stack; WebFlux uses reactive readers/writers and codecs.
9. Typically 415 Unsupported Media Type.
10. Likely 406 Not Acceptable.
11. Jackson 3 JsonMapper.
12. No; to replace the Jackson 3 mapper you must provide/customize the corresponding JsonMapper.
13. It can allow an application to instantiate or use types outside the expected list, creating security risks; use allowlists/type constraints.

## 20. Official References

- [Spring Boot 3.5 — JSON](https://docs.spring.io/spring-boot/3.5/reference/features/json.html): Jackson 2 ObjectMapper, modules, and @JsonComponent.
- [Spring Boot 3.5 — Customize Jackson ObjectMapper](https://docs.spring.io/spring-boot/3.5/how-to/spring-mvc.html): builder, spring.jackson.* properties, Jackson2ObjectMapperBuilderCustomizer, and HTTP converters.
- [Spring Boot 4.x — JSON](https://docs.spring.io/spring-boot/reference/features/json.html): Default Jackson 3 JsonMapper and compatibility for Jackson 2.
- [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide): new packages, Jackson 3, property migration, @JacksonComponent, and default changes.
- [Spring Boot 4.x — Customize JsonMapper](https://docs.spring.io/spring-boot/how-to/spring-mvc.html): JsonMapperBuilderCustomizer and Jackson 3 properties.
- [Spring Framework — HTTP Message Conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html): Spring MVC HttpMessageConverter and JSON.
- [Spring Framework — WebFlux Codecs](https://docs.spring.io/spring-framework/reference/web/webflux/config.html#webflux-config-message-codecs): WebFlux HttpMessageReader/Writer and CodecConfigurer.
- [Jackson databind](https://github.com/FasterXML/jackson-databind): ObjectMapper, JsonNode, and serialization/deserialization in Jackson 2.
