# Jackson and Version-Appropriate Data Mapping Configuration in Spring

## 1. Why Does This Topic Matter?

In a Spring MVC API, controllers typically receive JSON via `@RequestBody` and return JSON via `@ResponseBody`, `@RestController`, or `ResponseEntity`. Spring MVC does not turn JSON into Java objects by manually matching keys to controller fields one by one. It delegates reading/writing the **HTTP message body** to an `HttpMessageConverter`, typically a converter integrating **Jackson**.

Jackson handles *data mapping* between JSON representations and Java objects: field names, constructors, records, dates/times, enums, nulls, nested object relationships, and custom serializers/deserializers. Spring adds the integration layer that chooses a converter by HTTP `Content-Type`/`Accept` and configures the mapper through beans, properties, or MVC config.

A critical point when upgrading: **Spring Framework 6.x / Spring Boot 3.x primarily use Jackson 2**, whereas **Spring Framework 7.x / Spring Boot 4.x default to Jackson 3**. You cannot carry over old imports, builder customizers, and every legacy property unchanged into the newer generation.

This lesson focuses on the **Spring MVC Servlet stack**, version milestones, JSON transport mechanics, configuration choices, and verifying API contracts with tests. Spring WebFlux uses a different codec/reactive stack; do not mechanically apply MVC `HttpMessageConverter` details to WebFlux.

## 2. JSON Processing Chain from Request to Response

Suppose a client sends:

```http
POST /api/books HTTP/1.1
Content-Type: application/json
Accept: application/json

{"book_title":"Spring MVC","published_on":"2026-10-01"}
```

Basic flow in Spring MVC:

```text
HTTP request
     |
DispatcherServlet selects @PostMapping("/api/books")
     |
@RequestBody BookRequest
     |
RequestResponseBodyMethodProcessor
     |
HttpMessageConverter selected by media type + Java type
     |
Jackson JSON converter -> Jackson mapper reads JSON
     |
BookRequest Java object -> controller
     |
BookResponse or ResponseEntity<BookResponse>
     |
Jackson mapper writes JSON
     |
HTTP response: Content-Type: application/json
```

Each component has a distinct role:

- `@RequestBody` requests decoding the request body into the parameter's Java type. Commonly used for JSON APIs.
- `@ResponseBody` marks the return value to be written directly to the response body. `@RestController` has the same meaning as `@Controller` combined with `@ResponseBody` at the class level.
- `ResponseEntity<T>` gives explicit control over status, headers, and body; it does not choose the JSON format by itself.
- `HttpMessageConverter` determines read/write capability based on media type and Java type. Spring MVC has multiple converters for strings, byte arrays, JSON, XML, and more depending on the classpath/configuration.
- **Jackson mapper** reads JSON tokens, instantiates objects, converts data, and applies annotations/custom serializers; in reverse, it writes objects to JSON.

Differences to distinguish:

| Component | Function | Example |
| --- | --- | --- |
| HTTP `Content-Type` | Format of the **request body** | `application/json` |
| HTTP `Accept` | Format **accepted by the client for the response** | `application/json` |
| Jackson JSON mapper | JSON ↔ Java mapping rules | `@JsonProperty("book_title")` |
| Bean Validation | Checks constraints after reading DTO | `@Valid`, `@NotBlank` |
| Service/business logic | Checks data against system state | Does the book code already exist? |
| Database mapping | Converts Java entity ↔ storage data | JPA/Hibernate ORM |

**Jackson is neither Hibernate ORM nor Hibernate Validator.** Do not use Jackson annotations in place of authorization, business checks, or database constraints.

## 3. Matrix of Spring Versions, Jackson, and Configuration APIs

| Common Platform | Default/Preferred Jackson Generation | Mapper Type | JSON Converter in MVC | Typical Customization Approach |
| --- | --- | --- | --- | --- |
| Spring Framework 5.x + Boot 2.x | Jackson 2 | `com.fasterxml.jackson.databind.ObjectMapper` | `MappingJackson2HttpMessageConverter` | `spring.jackson.*`, `Jackson2ObjectMapperBuilderCustomizer`; many Jakarta APIs still under `javax.*` |
| Spring Framework 6.0–6.2 + Boot 3.0–3.5 | Jackson 2 | `com.fasterxml.jackson.databind.ObjectMapper` | `MappingJackson2HttpMessageConverter` | `spring.jackson.*`, `Jackson2ObjectMapperBuilderCustomizer`, Jackson 2 modules |
| Spring Framework 7.0+ + Boot 4.0+ | Jackson 3 **preferred by default** | `tools.jackson.databind.json.JsonMapper` | `JacksonJsonHttpMessageConverter` | `spring.jackson.*` per Boot 4 schema, `JsonMapperBuilderCustomizer`, Jackson 3 modules |
| Boot 4.x during migration | Deprecated Jackson 2 support can be enabled | `com.fasterxml.jackson.databind.ObjectMapper` for legacy path | Jackson 2 converter if suitably installed/configured | `spring-boot-jackson2` module, `spring.jackson2.*` config namespace |

Compatible versions are **determined by the actual BOM and dependency tree**; the ranges in the table reflect common release generations and do not guarantee exact versions in projects that override dependencies.

Key milestones to remember:

1. **Boot 3 / Spring 6:** typical JSON Java code imports `com.fasterxml.jackson.databind.ObjectMapper`; the customizer is `org.springframework.boot.autoconfigure.jackson.Jackson2ObjectMapperBuilderCustomizer`.
2. **Boot 4 / Spring 7:** moves most dependency groups/packages to `tools.jackson`; the mapper configured by Spring Boot is typically `JsonMapper`, and the customizer is `org.springframework.boot.jackson.autoconfigure.JsonMapperBuilderCustomizer`.
3. **Package exception:** common Jackson annotations such as `@JsonProperty`, `@JsonAlias`, `@JsonInclude`, and `@JsonTypeInfo` remain in `com.fasterxml.jackson.annotation`. Do not blindly change them to `tools.jackson.annotation`.
4. `MappingJackson2HttpMessageConverter` and `Jackson2ObjectMapperBuilder` are the Jackson 2 integration path; **do not use them as the default setup for a new Jackson 3 system**. Spring Framework 7 retains deprecated Jackson 2 support as an upgrade bridge.
5. Spring Boot 4 offers `spring.jackson.use-jackson2-defaults=true` to align Jackson 3 defaults closer to Boot 3's Jackson 2 behavior; this is a **defaults compatibility mode**, not a switch back to the Jackson 2 library.
6. In Boot 4, if you intentionally retain Jackson 2, use `spring.jackson2.*` settings with the deprecated compatibility module. New JSON reader/writer properties such as `spring.jackson.json.read.*` and `spring.jackson.json.write.*` must be checked against Boot 4 documentation when upgrading.
7. Some Spring MVC APIs for **configuring the converter list** also changed between Framework 6.2 and 7.0; verify the exact `WebMvcConfigurer` overload before copying examples from documentation.

**Upgrade rule:** classify code into Jackson annotations, Jackson databind/parser, Spring MVC converter, or Spring Boot auto-configuration, then match **the exact major version of each layer**. Do not assume changing one import is enough.

## 4. Which Jackson Annotation Solves Which Problem?

The following annotations take effect when the corresponding mapper is invoked through Spring MVC or called directly.

| Annotation | Purpose | Notes |
| --- | --- | --- |
| `@JsonProperty("external_name")` | Sets the JSON property name independently of the Java name | Affects serialization/deserialization depending on placement |
| `@JsonAlias({"oldName"})` | Accepts alternative names **when reading JSON** | Writing responses still uses the primary name, not aliases |
| `@JsonIgnore` | Excludes a property from mapping per annotation context | Does not replace authorization or DTO strategy |
| `@JsonIgnoreProperties(ignoreUnknown=true)` | Ignores unknown JSON keys on the annotated type | Can hide misspelled client fields |
| `@JsonInclude(Include.NON_NULL)` | Omits properties with Java value `null` | Differs from `NON_EMPTY`, `NON_DEFAULT`; does not require input presence |
| `@JsonFormat(pattern="yyyy-MM-dd")` | Formats dates on read/write if supported by type and module | Test timezone, locale, and format against contract |
| `@JsonPropertyOrder` | Controls field output order | Do not make JSON key order part of the contract unless genuinely required |
| `@JsonCreator` | Selects a constructor/factory to instantiate the object | Useful for immutable types/special constructors |
| `@JsonValue` | Representative value when serializing enums/value objects | Check corresponding deserialization impact |
| `@JsonView` | Selects property groups by view on view-configured endpoints | Not an authorization layer; test default inclusion |
| `@JsonTypeInfo` | Writes/reads polymorphic type info | Be extremely careful with type ids and allowed subtypes |

Java records example:

```java
import com.fasterxml.jackson.annotation.JsonAlias;
import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;

record CreateAuthorRequest(
        @JsonProperty("full_name")
        @JsonAlias({"name", "authorName"})
        String fullName) {
}

@JsonInclude(JsonInclude.Include.NON_NULL)
record AuthorResponse(
        @JsonProperty("full_name") String fullName,
        String middleName) {
}
```

With request JSON `{"authorName":"An"}`, Jackson can bind it to `CreateAuthorRequest("An")`. Returning `new AuthorResponse("An", null)` produces an object with `"full_name":"An"` and **no `middleName`** if the mapper applies the annotations. `@JsonAlias` is for backward-compatible input; it does not emit `"authorName"` in responses.

**Do not assume that putting `@JsonIgnore` on an entity's password is enough to secure an API.** Another endpoint might serialize that entity via a different type, view, or mixin. A response DTO containing only allowed fields is a clearer choice.

## 5. Complete Example for Spring Boot 3.x / Spring Framework 6.x

This section provides a runnable mini REST API on Java 17+ in a Spring Boot **3.x** project using Spring MVC and Jackson **2**. Do not drop this unchanged into an unconverted Boot 4 project: dependencies, imports, and mapping defaults differ.

### 5.1. Dependencies

Example `build.gradle` **fragment** when the project already has the Spring Boot plugin, dependency management, repositories, and Java toolchain:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-web` in Boot 3 usually pulls in `spring-boot-starter-json` and Jackson 2. To support `LocalDate`, Jackson Java Time is enabled via the JSR-310 module bundled with the starter and configured by Boot. Do not instantiate a bare `ObjectMapper` that skips default modules.

### 5.2. Runnable Source

Create **`src/main/java/demo/jackson/JacksonDemoApplication.java`**:

```java
package demo.jackson;

import com.fasterxml.jackson.annotation.JsonAlias;
import com.fasterxml.jackson.annotation.JsonFormat;
import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.time.LocalDate;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class JacksonDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(JacksonDemoApplication.class, args);
    }
}

record BookRequest(
        @JsonProperty("book_title") String title,
        @JsonProperty("published_on")
        @JsonAlias({"publication_date"})
        @JsonFormat(pattern = "yyyy-MM-dd") LocalDate publishedOn,
        String note) {
}

@JsonInclude(JsonInclude.Include.NON_NULL)
record BookResponse(
        String id,
        @JsonProperty("book_title") String title,
        @JsonProperty("published_on")
        @JsonFormat(pattern = "yyyy-MM-dd") LocalDate publishedOn,
        String note) {
}

@RestController
@RequestMapping("/api/books")
class BookController {

    @PostMapping(
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<BookResponse> create(@RequestBody BookRequest body) {
        BookResponse result = new BookResponse(
                "bk-1", body.title(), body.publishedOn(), body.note());
        return ResponseEntity.status(HttpStatus.CREATED).body(result);
    }

    @GetMapping(
            path = "/{id}",
            produces = MediaType.APPLICATION_JSON_VALUE)
    BookResponse get(@PathVariable String id) {
        return new BookResponse(
                id, "Spring MVC", LocalDate.of(2026, 10, 1), null);
    }
}
```

This is a **valid compiling Java file on a Boot 3 classpath**, because only `JacksonDemoApplication` is `public`; the remaining records/controller are package-private. Place it in package `demo.jackson` so `@SpringBootApplication` component scanning discovers the controller.

This controller intentionally omits a database and validation. It highlights JSON mapping clearly:

- `@JsonProperty("book_title")` keeps the JSON contract stable even though the Java accessor is `title()`.
- `@JsonAlias("publication_date")` accepts the old input name, while responses always emit `published_on`.
- `LocalDate` is read/written in ISO date form per `@JsonFormat(pattern = "yyyy-MM-dd")`; invalid date input can trigger a conversion error.
- `@JsonInclude(NON_NULL)` applies to `BookResponse`, so when `note=null` the response **omits the note field completely**, rather than returning `"note":null`.
- `POST` returns 201 and `GET` returns 200. This behavior has nothing to do with real persistence; ID `bk-1` is a demo value.

### 5.3. Running and Observing HTTP

Start the application using the project's Gradle wrapper:

```bash
./gradlew bootRun
```

POST request using the canonical JSON names:

```bash
curl -i -X POST 'http://localhost:8080/api/books' \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  -d '{"book_title":"Spring MVC","published_on":"2026-10-01"}'
```

Typical output:

```http
HTTP/1.1 201
Content-Type: application/json

{"id":"bk-1","book_title":"Spring MVC","published_on":"2026-10-01"}
```

Actual headers such as charset, content length, and date may differ by server. **JSON key order is not part of the contract** in this example. The JSON above shows the expected set of properties.

Request with the old alias:

```bash
curl -sS -X POST 'http://localhost:8080/api/books' \
  -H 'Content-Type: application/json' \
  -d '{"book_title":"Spring MVC","publication_date":"2026-10-01"}'
```

The response still returns the canonical key `published_on`, never `publication_date`:

```json
{"id":"bk-1","book_title":"Spring MVC","published_on":"2026-10-01"}
```

GET request:

```bash
curl -sS 'http://localhost:8080/api/books/bk-9'
```

Expected body:

```json
{"id":"bk-9","book_title":"Spring MVC","published_on":"2026-10-01"}
```

The curl commands in this section assume the project runs on port 8080 with no filters/security/proxies altering the protocol. If you add request validation, error handling, or JSON config, re-test the outcomes.

## 6. Customizing Jackson in Spring Boot 3

There are three option levels: **annotations on DTOs**, **Boot properties**, and **customizer beans**. Start at the narrowest level that satisfies the requirement, avoiding unnecessary replacement of auto-configuration.

### 6.1. Configuration via Application Properties

In Boot 3, for example:

```properties
# Applies only to the Boot auto-configured mapper in the Boot 3 line.
spring.jackson.default-property-inclusion=non_null
spring.jackson.deserialization.fail-on-unknown-properties=true
spring.jackson.serialization.indent-output=false
spring.jackson.property-naming-strategy=SNAKE_CASE
```

These illustrative properties are **optional customizations**; do not add all of them blindly to the sample app, because changing a global naming strategy affects other DTOs. If `@JsonProperty` is already specified explicitly, test those external field names separately when combined with a global naming strategy.

- `default-property-inclusion=non_null` omits null properties in responses for objects using the shared config; `@JsonInclude` on a class/field can override it locally.
- `deserialization.fail-on-unknown-properties=true` makes JSON with unknown keys fail instead of being silently ignored, unless the type defines its own rule such as `@JsonIgnoreProperties(ignoreUnknown=true)`.
- `serialization.indent-output` controls pretty printing; the JSON gets extra whitespace without changing the data model.
- `property-naming-strategy=SNAKE_CASE` converts e.g. Java `publishedOn` to JSON `published_on` when no explicit name is set.

**Unknown-fields policy is an API contract decision**: strict catches typos early; permissive lets client/server evolve with less friction. Neither setting is universally optimal. Pair it with validation, because a misspelled field can become `null` and validation will enforce requiredness if enabled.

### 6.2. Customizing the Builder in Boot 3

Create `src/main/java/demo/jackson/Jackson2Config.java`:

```java
package demo.jackson;

import org.springframework.boot.autoconfigure.jackson.Jackson2ObjectMapperBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class Jackson2Config {

    @Bean
    Jackson2ObjectMapperBuilderCustomizer prettyJson() {
        return builder -> builder.indentOutput(true);
    }
}
```

This runs with Boot 3 APIs; it sets indented output on the mapper built by Boot's builder. If `spring.jackson.serialization.indent-output=false` is also declared, **customizer application order** decides the final outcome; avoid conflicting settings across two sources. For predictability, pick one configuration source and write a verifying test.

For complex serializer/deserializer logic, consider a **Jackson `Module`** to register serializers for a specific type. Do not create random `new ObjectMapper()` instances in controllers/services: those mappers can miss Java Time, naming policies, inclusion policies, and custom modules managed by Boot.

### 6.3. When Do You Need `ObjectMapper` Directly?

In a service or internal batch job in Boot 3:

```java
import com.fasterxml.jackson.databind.ObjectMapper;

class JsonExportService {
    private final ObjectMapper mapper;

    JsonExportService(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    String toJson(Object value) throws Exception {
        return mapper.writeValueAsString(value);
    }
}
```

This is a Java class illustrating DI; it is not a standalone controller. Injecting Spring's configured mapper keeps JSON rules consistent with MVC. However, remember that the actual converter might use a separate mapper if someone altered `HttpMessageConverters` configuration; therefore, **do not assume an injected `ObjectMapper` bean is guaranteed to be the mapper handling HTTP** if the app has custom converters.

Jackson 2 `ObjectMapper` can be configured before use; when shared across an application, avoid mutating runtime config concurrently with serialization across threads. The safe pattern is to configure once, then reuse the mapper or dedicated readers/writers.

## 7. Message Converter Configuration: Order, Media Types, and Spring Boot Impact

In Spring MVC, `RequestMappingHandlerAdapter` holds a list of `HttpMessageConverter`s to handle bodies. Not every request can be read by **just any** converter; Spring considers content type, target type, and converter support.

Example API accepting and returning JSON:

```java
@PostMapping(
    path = "/payload",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE)
public Payload handle(@RequestBody Payload payload) {
    return payload;
}
```

This is an illustrative method inside a `@RestController`; `Payload` and `MediaType` require definitions/imports. With a suitable converter:

- `Content-Type: application/json` with valid JSON → deserialization runs.
- `Content-Type: text/plain` with a JSON body can lead to **415 Unsupported Media Type** because of `consumes` and converters.
- `Accept: application/xml` when only JSON is declared/writable can lead to **406 Not Acceptable**.
- Malformed JSON or values unmappable to Java types can throw `HttpMessageNotReadableException` and typically return **400 Bad Request**.
- JSON parsed into an object successfully but violating `@Valid`/`@Validated` is a separate validation step; the exception usually differs from parse errors.

In **Framework 6.2**, `WebMvcConfigurer#configureMessageConverters(List<HttpMessageConverter<?>>)` configures a custom list (replacing defaults depending on mechanism); `extendMessageConverters(List<HttpMessageConverter<?>>)` is suited when you only want to adjust registered converters. Boot also adds converter beans discovered via auto-configuration. Pick a consistent configuration approach and test every media type genuinely supported.

In **Framework 7.x**, official documentation presents configuration via `configureMessageConverters(HttpMessageConverters.ServerBuilder)` and Jackson 3 converters. Framework 7 projects should not copy the `List<HttpMessageConverter<?>>` signature verbatim from 6.2 if the API changed.

Never force a JSON converter globally onto XML, form, byte array, or file download endpoints. Converter order can affect content negotiation and read/write capability.

## 8. Spring Boot 4 and Spring Framework 7: Using Jackson 3

### 8.1. Package and Dependency Changes

Typical differences:

```text
Boot 3 / Jackson 2
  implementation 'org.springframework.boot:spring-boot-starter-web'
  com.fasterxml.jackson.databind.ObjectMapper
  MappingJackson2HttpMessageConverter
  Jackson2ObjectMapperBuilderCustomizer

Boot 4 / Jackson 3
  Spring MVC web starter per Boot 4 BOM/starters
  tools.jackson.databind.json.JsonMapper
  JacksonJsonHttpMessageConverter
  JsonMapperBuilderCustomizer
```

This is a **quick-reference comparison**, not a verbatim Gradle snippet. Spring Boot 4 reorganizes modules/starters for the new generation; check available dependencies via Boot 4's BOM/guide before adding individual starters.

For Jackson 3, core/databind modules live under the Maven group `tools.jackson` (e.g., `tools.jackson.core:jackson-databind`). **Jackson annotations remain in `com.fasterxml.jackson.annotation`**. Databind types such as mapper, module, and serializer/deserializer may change packages or API names. Do not mechanically find-and-replace all `com.fasterxml.jackson.*` imports.

### 8.2. Jackson 3 Java Config in Boot 4

In a **Boot 4 / Jackson 3** project with Spring MVC and auto-configuration, you can create **`src/main/java/demo/jackson/Jackson3Config.java`**:

```java
package demo.jackson;

import org.springframework.boot.jackson.autoconfigure.JsonMapperBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import tools.jackson.databind.SerializationFeature;

@Configuration
class Jackson3Config {

    @Bean
    JsonMapperBuilderCustomizer prettyJson() {
        return builder -> builder.enable(
                SerializationFeature.INDENT_OUTPUT);
    }
}
```

This example is **Boot 4 specific**; it will not compile in Boot 3 because `JsonMapperBuilderCustomizer` and Jackson 3's `tools.jackson.databind.SerializationFeature` do not exist on the older baseline. Spring Boot applies the customizer to the auto-configured mapper builder.

In a Framework 7 project configuring MVC directly, the standard JSON converter path is `JacksonJsonHttpMessageConverter` with `JsonMapper`. Standalone illustrative mapper snippet:

```java
import tools.jackson.databind.json.JsonMapper;
import tools.jackson.databind.SerializationFeature;

JsonMapper mapper = JsonMapper.builder()
        .enable(SerializationFeature.INDENT_OUTPUT)
        .build();
```

This is only a **Jackson 3 fragment** with contextual imports/variables. This mapper is not yet registered into Spring MVC; in a Boot application, prefer Boot's builder/customizer or converter registration mechanism.

### 8.3. Property Configuration in Boot 4

Example `application.properties` for **Jackson 3 in Boot 4**:

```properties
spring.jackson.serialization.indent-output=true
spring.jackson.use-jackson2-defaults=false
spring.jackson.find-and-add-modules=true
```

In Boot 4, specialized JSON reader/writer features are grouped under `spring.jackson.json.read.*` and `spring.jackson.json.write.*`. Do not copy old `spring.jackson.read.*` or `spring.jackson.write.*` settings without checking feature type, property name, and equivalent mapping. Some options no longer map 1:1 and require a customizer.

For step-by-step migration:

```properties
# Temporarily aligns Jackson 3 defaults with the defaults Boot 3 used
# for Jackson 2; does NOT switch the runtime back to Jackson 2.
spring.jackson.use-jackson2-defaults=true
```

Enable this flag only when you have evidence your JSON contract relies on old defaults and need a transition period. The end goal is **explicit JSON contract tests** so you do not over-rely on framework defaults.

### 8.4. When Jackson 2 Is Needed in Boot 4

Spring Boot 4 provides a deprecated transition path for Jackson 2:

```groovy
// Only in Boot 4 projects temporarily needing Jackson 2 compatibility.
dependencies {
    implementation 'org.springframework.boot:spring-boot-jackson2'
}
```

Settings for the Jackson 2 path live in the `spring.jackson2.*` namespace and **do not mix automatically** with the `spring.jackson.*` Jackson 3 mapper. Merely adding the compatibility module does not prove the HTTP converter is using the Jackson 2 mapper; inspect the classpath, auto-configuration, selected converter, and test the endpoints.

If code has an API dependency requiring Jackson 2 in one module, consider keeping the Jackson 2 mapper **local to that module boundary** while the application's HTTP JSON continues using Jackson 3; both generations can coexist as long as mapping rules are unambiguous. Legacy support is a temporary bridge scheduled for removal.

## 9. Migrating Jackson 2 Config to Jackson 3 Without Breaking JSON Contracts

Before migrating, build **a suite of JSON contract samples** covering inputs/outputs and status codes used by clients. Run them on the current system before upgrading libraries.

| Concern | Boot 3 / Jackson 2 | Boot 4 / Jackson 3 |
| --- | --- | --- |
| Runtime mapper | `com.fasterxml.jackson.databind.ObjectMapper` | `tools.jackson.databind.json.JsonMapper` |
| Spring Boot customizer | `Jackson2ObjectMapperBuilderCustomizer` | `JsonMapperBuilderCustomizer` |
| Spring converter | `MappingJackson2HttpMessageConverter` | `JacksonJsonHttpMessageConverter` |
| Custom module/serializer | Jackson 2 `Module`, `JsonSerializer`, `JsonDeserializer` | Jackson 3 module/serializer API; check name/signature changes |
| Core properties config | `spring.jackson.*` per Boot 3 | `spring.jackson.*` per Boot 4, some property branches renamed |
| JSON reader/writer feature settings | `spring.jackson.read.*`/`write.*` branches in older versions | `spring.jackson.json.read.*`/`json.write.*` for corresponding JSON features |
| Keeping defaults close to older version | Defaults set by Boot 3 | `spring.jackson.use-jackson2-defaults=true` (migration aid only) |
| Keeping Jackson 2 temporarily in Boot 4 | Built in at baseline | Deprecated `spring-boot-jackson2` and `spring.jackson2.*` |
| Common Jackson annotations | `com.fasterxml.jackson.annotation.*` | Still `com.fasterxml.jackson.annotation.*` for common annotations |

Minimum regression tests should cover:

1. **Field names:** `camelCase`, `snake_case`, `@JsonProperty`, and legacy client aliases accepted on input.
2. **Null / absent fields:** do responses omit nulls or return null? Is input missing a field accepted? Test "absent", "null", and "empty value" separately.
3. **Dates/times:** `LocalDate`, `LocalDateTime`, `OffsetDateTime`, and timezones; ISO dates, epoch timestamps, millisecond precision. Do not apply one date-time format to every type.
4. **Enums:** enum names, casing, unrecognized values, custom JSON values via `@JsonCreator`/`@JsonValue`.
5. **Numbers:** large `long`s, `BigDecimal`, floating point, rounding/scale where business-significant; avoid converting large IDs to `double` in JavaScript clients.
6. **Unknown fields:** are unknown fields rejected? Are aliases/backward compatibility present? Verify HTTP errors.
7. **Nested objects/collections:** handling of generics, null elements, immutable constructors/records.
8. **Polymorphic data:** allowlisted valid types; never let payloads pick arbitrary Java classes.
9. **Error responses:** malformed JSON, mismatched types, unsupported media types, validation errors, and `ProblemDetail`/API error contract shapes.
10. **Mixed dependencies:** verify which mapper/converter handles each endpoint and that Java Time support modules were not accidentally dropped.

Safe migration relies on **outcome tests**. Simply asserting an `ObjectMapper` bean exists in the context does not prove Spring MVC is using that mapper.

## 10. Mapping Issues That Commonly Cause Bugs

### 10.1. Dates and Times with `java.time`

In Boot 3, `spring-boot-starter-json` typically provides and Boot registers the Java Time module. If you instantiate a standalone `new ObjectMapper()`, `LocalDate` may not read/write as expected due to a missing `JavaTimeModule` or timestamp settings. Plain Jackson 2 example, **not necessarily needed in Boot 3**:

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

ObjectMapper mapper = new ObjectMapper()
        .registerModule(new JavaTimeModule());
```

This **fragment** requires the corresponding `jackson-datatype-jsr310` dependency. In a Boot application, it is better to inject the auto-configured mapper so you do not lose global rules. In Jackson 3, the module ecosystem and defaults change; do not blindly copy `com.fasterxml.jackson.datatype.jsr310` imports into 3.x code.

Distinguish:

- `LocalDate` represents a date **without time or timezone**; pattern `yyyy-MM-dd` fits calendar dates.
- `LocalDateTime` has date and time **without offset/timezone**; it is insufficient to identify an absolute instant.
- `OffsetDateTime` and `Instant` represent instants with offset/UTC semantics; pick ISO 8601 format and explicit timezone conversion policies.
- Changing the global timezone does not make all `java.time` types share the same semantics. Write tests with different offsets.

### 10.2. Object Structure and Records

Jackson can use a default constructor + setters, a constructor marked with `@JsonCreator`, a record's canonical constructor, and other introspection mechanisms depending on the version. With Java 17 records, record component names are part of the Java structural contract; `@JsonProperty` pins the JSON name.

If a DTO only has a multi-argument constructor and the mapper cannot find how to instantiate it, errors typically mention "no Creators" or "cannot construct instance". Fix: use an appropriate DTO/record, declare `@JsonCreator`/`@JsonProperty` where needed, or write a specific deserializer. Avoid enabling global "field visibility ANY" just to fix one DTO, as it can expose unintended fields on other types.

### 10.3. Unknown Fields in Input

Two policies:

```java
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

// Accept unknown fields for this specific DTO only:
@JsonIgnoreProperties(ignoreUnknown = true)
record FlexibleRequest(String name) {}
```

Or, in Boot 3 if wanting **global** strictness:

```properties
spring.jackson.deserialization.fail-on-unknown-properties=true
```

Do not set two conflicting choices on the same DTO without understanding precedence. If a client sends `{"nmae":"An"}` instead of `{"name":"An"}`, strict mapping catches the error early; permissive mapping may create the object with `name=null`. Bean Validation (if present and active) must separately enforce required names.

### 10.4. Serialization Is Not Validation

`@JsonProperty(required=true)` is not a switch replacing all `@NotNull`/`@NotBlank` constraints. The behavior of `required` depends on where the property/creator is declared and the Jackson version; do not rely on it as the sole business data check.

In an API:

```java
@PostMapping
public ResponseEntity<Void> create(
        @Valid @RequestBody CreateRequest body) {
    return ResponseEntity.status(201).build();
}
```

This is a **method fragment**: it requires importing `jakarta.validation.Valid` and declaring `CreateRequest` with constraints. The flow is that Jackson **deserializes** first; once the object exists, Bean Validation checks constraints. Unparseable body errors and invalid constraint errors are **two separate error groups**, so handlers should treat them differently.

### 10.5. Do Not Serialize JPA Entities Directly

Entities can hold lazy proxies, bidirectional relationships, internal fields, sensitive data, or circular references. Letting Jackson traverse a wide graph can cause infinite recursion, extra SQL queries/N+1, or accidental data leaks. Response DTOs keep the contract bounded:

```java
record UserView(long id, String displayName) {}
```

Do not treat `@JsonIgnore` on an entity as a complete API architecture; at the HTTP boundary, converting entities to DTOs and serializing DTOs is much easier to control.

## 11. How Spring MVC Picks a Mapper and Common HTTP Errors

| Symptom | Typical Failure Path | What to Check |
| --- | --- | --- |
| `415 Unsupported Media Type` | Incompatible `Content-Type`/`consumes` | Did the client send JSON with `application/json` or `text/plain`? |
| `406 Not Acceptable` | No converter/media type satisfies `Accept` | `produces`, converters, and `Accept` header |
| `400 Bad Request` with invalid JSON syntax | Jackson fails to deserialize | Malformed JSON, field types, enum/date formats |
| `400 Bad Request` after DTO is read | Validation failed | `@Valid`/`@Validated`, `BindingResult`, and error handler |
| `500 Internal Server Error` when writing JSON | Serialization failed during response | Circular references, lazy-loading, serializers, module config |
| Response field disappears | `@JsonIgnore` or inclusion policy | `@JsonInclude`, MixIn, `JsonView`, null/empty |
| Response field name changed | Naming strategy / annotation / migration | `@JsonProperty`, `SNAKE_CASE`, schema contract |
| JSON date becomes timestamp/array | Different module/format/defaults | `JavaTimeModule`, mapper, `@JsonFormat`, Jackson generation |
| Only one endpoint has different JSON | Separate converter/mapper or view | Converter registry, custom `ObjectMapper`, annotation scope |

**The statuses above are only common paths.** `@ControllerAdvice`, Spring Security, proxies, filters, or custom exception resolvers can alter the final outcome. Seeing HTTP 400 alone does not distinguish whether JSON parsing or validation failed.

Example REST exception handler (placed in the sample Boot 3 project, handling malformed JSON only):

```java
package demo.jackson;

import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class JsonErrorAdvice {

    @ExceptionHandler(HttpMessageNotReadableException.class)
    ResponseEntity<Map<String, String>> malformedJson(
            HttpMessageNotReadableException ex) {

        // Do not send ex.getMostSpecificCause().getMessage() to the client.
        return ResponseEntity.badRequest()
                .body(Map.of("code", "INVALID_JSON"));
    }
}
```

This is a complete class, though it requires the application's Spring context. If this advice is enabled, invalid JSON tests can assert `{"code":"INVALID_JSON"}`. In production systems, consider `ProblemDetail` and a unified error strategy so clients can distinguish invalid JSON, invalid fields, unauthorized, and conflict.

## 12. Testing JSON Mapping with MockMvc

After adding the test starter as in Section 5, create **`src/test/java/demo/jackson/JacksonDemoApplicationTests.java`**:

```java
package demo.jackson;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class JacksonDemoApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void readsCanonicalNamesAndOmitsNullInResponse() throws Exception {
        mvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("""
                    {"book_title":"Spring MVC",
                     "published_on":"2026-10-01"}
                    """))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.id").value("bk-1"))
            .andExpect(jsonPath("$.book_title").value("Spring MVC"))
            .andExpect(jsonPath("$.published_on").value("2026-10-01"))
            .andExpect(jsonPath("$.note").doesNotExist());
    }

    @Test
    void acceptsAliasButWritesCanonicalName() throws Exception {
        mvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"book_title":"Spring MVC",
                     "publication_date":"2026-10-01"}
                    """))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.published_on").value("2026-10-01"))
            .andExpect(jsonPath("$.publication_date").doesNotExist());
    }

    @Test
    void returnsKnownJsonPropertyNames() throws Exception {
        mvc.perform(get("/api/books/bk-9")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value("bk-9"))
            .andExpect(jsonPath("$.book_title").value("Spring MVC"))
            .andExpect(jsonPath("$.published_on").value("2026-10-01"))
            .andExpect(jsonPath("$.note").doesNotExist());
    }

    @Test
    void rejectsMalformedDate() throws Exception {
        mvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"book_title":"Spring MVC",
                     "published_on":"not-a-date"}
                    """))
            .andExpect(status().isBadRequest());
    }

    @Test
    void rejectsNonJsonContentType() throws Exception {
        mvc.perform(post("/api/books")
                .contentType(MediaType.TEXT_PLAIN)
                .content("""
                    {"book_title":"Spring MVC"}
                    """))
            .andExpect(status().isUnsupportedMediaType());
    }
}
```

Run:

```bash
./gradlew test
```

All five test methods are expected to **pass** on a Boot 3 project with the default JSON converter and no Security or error customization altering statuses. Checks use JSONPath so they do not depend on field order or whitespace.

If you want to test strict unknown-field handling, add `spring.jackson.deserialization.fail-on-unknown-properties=true` in a test profile, send a body containing `"unexpected_field":1`, and assert 400. If you want to test permissive mapping, create a dedicated DTO with `@JsonIgnoreProperties(ignoreUnknown=true)` and test the response. Never rely on an untested Jackson default when upgrading major versions.

### Testing the Mapper Directly vs. HTTP Tests

| Test Type | Covers | Does Not Cover |
| --- | --- | --- |
| Direct `ObjectMapper` test in Boot 3 | Serialization/deserialization, annotations, modules | MVC converter selection, Content-Type, Accept, controller mappings |
| Direct `JsonMapper` test in Boot 4 | Jackson 3 mapping rules | Converter/Boot MVC integration |
| `@JsonTest` (Spring Boot test slice) | JSON slice configuration and component mapping | Full MVC filter chain/endpoints |
| `@WebMvcTest` + `MockMvc` | MVC controllers, converters, selected web infrastructure | Full application/services/database unless added |
| `@SpringBootTest` + `@AutoConfigureMockMvc` | Web application context and request/response handling | Reverse proxy, browser, real network transport |

To verify a Boot 3 → Boot 4 upgrade, combine mapper-level and HTTP contract tests. A unit test serializing a DTO with a manually created mapper can **pass** while the production controller uses a different mapper/converter.

## 13. Risks of Deep Customization

### Replacing the `ObjectMapper` Bean

In Boot 3, if you declare a custom `ObjectMapper` bean replacing Boot's auto-configured bean, make sure to register essential modules and policies (Java Time, Java Optional, parameter names, inclusion/naming, custom serializers). Boot cannot automatically apply all of your settings onto a manually constructed mapper. Similarly, Boot 4 has its own auto-configured `JsonMapper`/builder; do not register a Jackson 2 bean and expect Jackson 3 converters to use it.

### Polymorphic Deserialization

Avoid enabling **overly broad default typing** for JSON payloads coming from untrusted clients, especially metadata modes allowing arbitrary Java class names to select subtypes. If polymorphism is needed, declare a bounded set of valid subtypes using `@JsonTypeInfo`/`@JsonSubTypes` strictly, paired with validation/authorization. Review CVEs and keep Jackson/Spring patched appropriately.

### Date and Decimal Fidelity

Choose Java types suited to the data:

- Monetary amounts: `BigDecimal` instead of `double` when exact decimal arithmetic and controlled scale/rounding are required.
- 64-bit IDs: test with JavaScript clients to avoid precision loss when JSON numbers exceed JS's safe integer limit; if needed, design ID contracts as strings.
- Instants: `Instant`/`OffsetDateTime` with ISO format and explicit timezone; never send `LocalDateTime` and force clients to guess the timezone.
- Enums and name casing: enforce strict contracts at boundaries, testing unknown values and migrations.

### Separating Request DTOs and Response DTOs

Input DTOs may accept aliases, whereas outputs should use canonical names. Do not reuse multi-purpose entities if internal fields could be serialized outward. Never treat `@JsonView` or `@JsonIgnore` as the sole access-control boundary.

## 14. Verifiable Jackson and Spring Upgrade Procedure

1. **Pin actual versions:** inspect `spring-webmvc`, Spring Boot BOM, `jackson-databind`, Jackson modules, and the dependency tree. With Gradle, use `./gradlew dependencies --configuration runtimeClasspath` and `dependencyInsight` for key dependencies.
2. **Pin the HTTP JSON contract:** save sample requests/responses for critical endpoints; define statuses, Content-Type, Accept, field names, nulls, dates, enums, and unknown-field policy.
3. **Inventory custom code:** locate `ObjectMapper`, `JsonMapper`, `Jackson2ObjectMapperBuilderCustomizer`, custom converters, serializers/deserializers, mixins, Java Time usage, `@JsonProperty`, `@JsonView`, and `spring.jackson.*`.
4. **Pick the migration path:** moving to Boot 4 and Jackson 3 is preferred; if a module is incompatible, use time-boxed Jackson 2 compatibility with a clear scope.
5. **Update imports/APIs accurately:** move most databind/parser types to `tools.jackson`; keep annotation imports in `com.fasterxml.jackson.annotation`; update Spring customizers/converters for the target version.
6. **Review property configs:** check renamed reader/writer property branches; decide whether to temporarily enable `use-jackson2-defaults`; remove obsolete customizers.
7. **Run unit and integration tests:** verify the Jackson mapper directly **and** the HTTP pipeline through MVC with both positive and negative cases.
8. **Check errors, security, and observability:** do not leak sensitive rejected input; verify content negotiation, 400/406/415/500, monitoring, and logging after deployment.
9. **Remove compatibility bridges:** once the contract is stable and all dependent libraries support Jackson 3, remove the deprecated Jackson 2 path and workaround-only tests.

An upgrade milestone is complete when critical clients receive the **same data contract** or an explicitly published versioned API change, not merely when the build turns green.

## 15. Self-Check Exercises

1. A Boot 3 controller declares `@PostMapping(consumes="application/json")` with `@RequestBody BookRequest`. A client sends `Content-Type: text/plain` with a valid JSON body: which step rejects it and what HTTP status is expected?
2. A Java record has accessor `bookTitle()`, but the API must return key `book_title`. Compare `@JsonProperty` on the field/record component with global `SNAKE_CASE`. Which is better if only one DTO has special naming?
3. From input `{"publication_date":"2026-10-01"}` to `BookRequest` and response `BookResponse`, explain why `@JsonAlias` accepts the old input name while output always uses `published_on`.
4. A client sends date `2026-02-30`; why can this fail **deserialization** before Bean Validation runs? Verify with a `MockMvc` test.
5. After upgrading Boot 3 → Boot 4, code importing `com.fasterxml.jackson.databind.ObjectMapper` and a Jackson 2 customizer no longer affect new HTTP responses. Point out the Jackson 3 changes and how to verify the active converter.
6. When `spring.jackson.use-jackson2-defaults=true` is set in Boot 4, is the app actually running Jackson 2? Contrast **defaults compatibility** with **library/runtime generation**.
7. An endpoint serializes an entity with a bidirectional relationship and a `passwordHash` field. Propose a response DTO and tests proving JSON does not leak internal fields.
8. Build a contract test matrix for enums, `BigDecimal`, null/absent fields, unknown JSON properties, and `OffsetDateTime` across Boot 3/4. Note behaviors to preserve and changes intentionally accepted.
9. Write an equivalent customizer in Boot 3 (`Jackson2ObjectMapperBuilderCustomizer`) and Boot 4 (`JsonMapperBuilderCustomizer`), then prove in HTTP tests that output is affected.

## 16. Authoritative Version-Specific References

- [Spring Framework 6.2 — HTTP Message Conversion](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/message-converters.html): `MappingJackson2HttpMessageConverter`, Jackson 2 `ObjectMapper`.
- [Spring Framework 6.2 — Message Converters Configuration](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/message-converters.html): `WebMvcConfigurer`, converter list for Framework 6.
- [Spring Framework 7 — HTTP Message Conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html): Jackson 3 converter using `JsonMapper`.
- [Spring Framework 7 — MVC Converter Configuration](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/message-converters.html): `HttpMessageConverters.ServerBuilder` and Jackson 3 converters.
- [Spring MVC — `@RequestBody`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html): resolver, message converter, and validation.
- [Spring Boot 3 — JSON](https://docs.spring.io/spring-boot/3.4/reference/features/json.html): auto-configuring Jackson 2 and custom serializers/deserializers.
- [Spring Boot 4 — JSON](https://docs.spring.io/spring-boot/reference/features/json.html): Jackson 3, `JsonMapper`, and new configuration.
- [Spring Boot 4 — MVC Configuration](https://docs.spring.io/spring-boot/how-to/spring-mvc.html): Jackson 3 customizers/configuration properties.
- [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide): Jackson 3 changes, packages, customizers, Jackson 2 compatibility, and properties.
- [Spring Framework 7.0 Release Notes](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-7.0-Release-Notes): Jackson 3 preferred by default and Jackson 2 deprecated.
- [Introducing Jackson 3 support in Spring — Spring Blog](https://spring.io/blog/2025/10/07/introducing-jackson-3-support-in-spring/): migration goals, compatibility defaults, and Boot 3/4 customizer examples.
