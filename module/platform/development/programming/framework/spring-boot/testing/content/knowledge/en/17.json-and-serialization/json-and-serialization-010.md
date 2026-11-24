# Aligning Mapper Configuration in Tests with the Real Application Mapper

## 1. Core problem: JSON tests are green yet the real API returns different JSON

In Spring Boot, an application can use Jackson to convert between Java and JSON. However, a test successfully calling `new ObjectMapper().writeValueAsString(...)` **does not prove** that the JSON returned by Spring MVC or an application HTTP client has the same shape. Reason: the mapper manually created by the test may **lack configurations applied by Spring Boot, application properties, customizers, Jackson modules, and message converters**.

Even when a test injects an `ObjectMapper` bean, you should still verify the output of the **HTTP path actually using the mapper**. An application can have multiple mappers, a custom `MappingJackson2HttpMessageConverter`, WebFlux codecs, custom Jackson serializers, or modules loaded only under one profile.

Common bug examples:

- Production specifies `snake_case` field names like `order_id`, while tests use a default mapper and expect `orderId`.
- Production omits null properties, while tests instantiate a fresh mapper so JSON still includes `"internalNote":null`.
- Production serializes `LocalDate` as an ISO string, while the test mapper lacks the `java.time` module and throws or formats differently.
- The app enables `FAIL_ON_UNKNOWN_PROPERTIES` to reject undeclared JSON keys, while tests use Boot's default mapper and miss the stricter contract.
- `@JsonTest` passes for a DTO, yet the app has a `@Configuration` customizing the mapper **outside the slice's scan scope**.
- A `@Bean ObjectMapper` or custom MVC converter alters the HTTP path, while tests inject or instantiate **a different mapper**.
- Upgrading from Spring Boot 3/Jackson 2 to Spring Boot 4/Jackson 3 and changing only dependency names without updating `JsonMapper`/customizers/modules.

This lesson focuses on one practical question:

> **How do you prove the JSON expected by tests is the exact JSON the application actually writes/reads at the HTTP boundary?**

The approach is **reusing production configuration in the JSON slice**, verifying the **auto-configured mapper bean** directly, and then verifying **Spring MVC request/response conversion** on the full test context; if the contract covers transport, add tests through a real HTTP server.

### Learning goals

After this lesson, you will be able to:

1. Distinguish a manually created Jackson mapper from a Spring Boot-managed mapper.
2. Understand configuration sources: `spring.jackson.*`, builder customizers, `Module`, `@JsonComponent`, `@JsonMixin`, DTO annotations, and `HttpMessageConverter`.
3. Use `@JsonTest` + `JacksonTester` and intentionally **`@Import` shared configuration**.
4. Use `@SpringBootTest` + `@AutoConfigureMockMvc` to assert exact JSON across controllers, converters, and exception handling.
5. Know when to add `RANDOM_PORT` + an HTTP client to prove JSON travels over a socket.
6. Understand the differences between Spring Boot 3.x/Jackson 2 and Spring Boot 4.x/Jackson 3.
7. Avoid "false green" tests, profile drift, and mapper configurations applied twice or not at all.

**Execution scope:** Java 17+, Spring Boot **3.x**, JUnit Jupiter, Spring MVC Servlet stack, and Jackson 2. Sections specific to Spring Boot 4.x are compatibility guidance only—**do not assume** you can copy 3.x Java files verbatim into Boot 4.x.

## 2. Three different things commonly called "the mapper"

| Object | Role | What tests prove when using it |
|---|---|---|
| `new ObjectMapper()` | Jackson 2 mapper manually created by Java code with initial defaults | Only the behavior of **that instance**, not Boot customizers/modules |
| `ObjectMapper` bean from Spring `ApplicationContext` | Mapper auto-configured by Boot or declared by the application | Policy of the **injected bean** in that test context |
| Mapper/codec actually used by the HTTP layer | E.g., the mapper inside `MappingJackson2HttpMessageConverter` or codecs | JSON shape flowing in/out of the tested **request/response path** |

All three **may** share the same policy, yet are not automatically the same instance in every app. The third layer must be verified whenever the goal is an HTTP contract.

### 2.1. Jackson has two independent directions

**Serialization**:

```text
PurchaseEvent Java record
    │
    └── ObjectMapper / HTTP message converter
           └── JSON: {"order_id":"PO-42","purchased_at":"2026-11-08"}
```

**Deserialization**:

```text
JSON request body
    │
    └── ObjectMapper / HTTP message converter
           └── PurchaseEvent Java record
```

Configuration can affect each direction differently:

- Naming strategy affects property names in both directions.
- Inclusion strategy (e.g. `NON_NULL`) mainly controls **which fields are written**.
- `FAIL_ON_UNKNOWN_PROPERTIES` affects **reading JSON**.
- `WRITE_DATES_AS_TIMESTAMPS` and the Java Time module affect temporal representations.
- Custom serializers affect writing; custom deserializers affect reading.
- `@JsonView`, `@JsonProperty`, `@JsonIgnore`, `@JsonFormat`, or mixins can tailor individual DTOs/endpoints.

A test that only writes JSON does not prove reading works; a test that only parses JSON does not prove response serialization.

### 2.2. Spring Boot 3.x and Jackson 2 configuration

With Spring Boot 3.x and Jackson on the classpath, Boot can auto-configure an `ObjectMapper`. Key configuration sources:

- Application properties under `spring.jackson.*`.
- `Jackson2ObjectMapperBuilderCustomizer` beans customizing `Jackson2ObjectMapperBuilder`.
- Jackson `Module` beans and modules supported by Boot auto-registration depending on line/version.
- `@JsonComponent` or `@JsonMixin` discovered via Boot's mechanisms.
- Annotations on models/records, such as `@JsonProperty`, `@JsonFormat`.
- `@Bean ObjectMapper` or `@Bean MappingJackson2HttpMessageConverter` when the app overrides defaults.

These configuration classes do not necessarily appear in a **JSON test slice** if you merely add `@JsonTest` and expect Spring to scan the entire application configuration like `@SpringBootTest`.

## 3. Why is manually creating `ObjectMapper` in tests error-prone?

### 3.1. Common counterexample

```java
ObjectMapper mapper = new ObjectMapper();
String json = mapper.writeValueAsString(
        new PurchaseEvent("PO-42", LocalDate.of(2026, 11, 8), null));
```

This is a **counterexample snippet**, assuming `PurchaseEvent` and its imports are declared; **it is not a standalone runnable test**. The freshly created mapper does not receive Boot config, customizer beans, or modules registered by the application context. For a Java Time type like `LocalDate`, a plain mapper may lack `JavaTimeModule` and behave differently from Boot's configured mapper.

Do not "fix" it merely by adding:

```java
mapper.registerModule(new JavaTimeModule());
```

because you can still miss naming, inclusion, custom serializers, date/time policies, mixins, unknown-field policy, custom converters, and profile-specific settings.

### 3.2. Recommended approach

- To test **pure JSON mapping**: use `@JsonTest`, inject `JacksonTester<T>` and `ObjectMapper`, and import critical production configuration not auto-loaded by the slice.
- To test **HTTP responses/bodies**: use `@WebMvcTest` or `@SpringBootTest(MOCK) + @AutoConfigureMockMvc`, send requests through MockMvc, and assert actual response JSON.
- To test **HTTP wire format** or container-specific behavior: use `@SpringBootTest(RANDOM_PORT)` with a real HTTP client.
- If testing a pure Java helper that builds its own explicitly configured mapper, assert that instance—just do not call the result "production mapper parity" unless the app builds its mapper identically.

### 3.3. A crucial comparison rule

**Do not compare two outputs generated by the same test mapper** and conclude the controller uses that mapper. For example:

```java
String left = mapper.writeValueAsString(event);
String right = mapper.writeValueAsString(event);
assertEquals(left, right);
```

This is an anti-pattern: calling the same method twice on the same instance only proves the instance is self-consistent, **never passing through Spring MVC**. You need independent observations via `MockMvc.perform(...)` or an HTTP client.

## 4. Choosing the test layer: @JsonTest, @WebMvcTest, or @SpringBootTest?

| Technique | Context / behavior | Use to |
|---|---|---|
| JUnit + `new ObjectMapper(...)` | No Spring; test-created mapper | Unit test a mapper used **by that exact code**, fully manually configured |
| **`@JsonTest`** | JSON slice; auto-configures JSON mapper/tester, restricts scanned components | Test serializers/deserializers and JSON configuration brought into the slice |
| `@WebMvcTest(Controller.class)` | MVC slice with controller, converters, validation, advice; services normally mocked | Test web-layer HTTP contract quickly in isolation |
| **`@SpringBootTest(MOCK) + @AutoConfigureMockMvc`** | Full test `ApplicationContext` + in-process MockMvc, no server socket | Check parity of mapper bean and converter/HTTP output against full app config |
| `@SpringBootTest(RANDOM_PORT)` + HTTP client | Real embedded server and requests over socket | Verify JSON wire contract over HTTP port + container/client |
| End-to-end in staging | Deployed staging infrastructure | Verify proxies, TLS, routing, gateways, and deployed config |

`@JsonTest` **does not mean** "load every `@Configuration` used in production." It is a slice that intentionally narrows component scanning. In Spring Boot 3.x, JSON-related types like `@JsonComponent` and Jackson `Module` are supported by the slice. Regular services and general configuration beans are not scanned automatically as in a full context.

When mapper customizations live in a regular configuration class, **`@Import(SharedJsonConfiguration.class)`** cleanly lets the exact same config class serve both production and the slice. Never duplicate mapper setters into tests: when business requirements change the naming strategy, the two copies will drift.

### 4.1. Priority principles

1. Identify the **exact HTTP/framework boundary** you need to prove.
2. Reuse **production configuration** instead of writing test-only config just to "turn tests green."
3. Assert **both serialization and deserialization** per contract.
4. For HTTP, assert output/bodies at the controller/converter boundary, not just an injected `ObjectMapper`.
5. When multiple mappers/converters exist, identify **which mapper a given code path actually uses**.

## 5. Defining a measurable JSON contract

We use a Java record:

```java
public record PurchaseEvent(
        String orderId,
        LocalDate purchasedAt,
        String internalNote
) {}
```

This is a **DTO structure snippet**; the complete file is in section 7.

Suppose the contract the application intends to expose is:

| Aspect | Policy | Concrete contract |
|---|---|---|
| Field names | `SNAKE_CASE` | `orderId` → `order_id`, `purchasedAt` → `purchased_at` |
| Null inclusion | `NON_NULL` | If `internalNote == null`, response **omits** `internal_note` |
| Java Time dates | ISO string, no timestamp array | `LocalDate.of(2026,11,8)` → `"2026-11-08"` |
| Unknown JSON keys | `FAIL_ON_UNKNOWN_PROPERTIES = true` | Input with `unknown_field` → deserialization error; HTTP → 400 in Spring MVC |
| Input/output symmetry | Jackson mapping follows same conventions | `snake_case` JSON parses into record and writes back identically |

Valid JSON for an event with `internalNote = null`:

```json
{
  "order_id": "PO-42",
  "purchased_at": "2026-11-08"
}
```

Example JSON **violating** that contract:

```json
{
  "orderId": "PO-42",
  "purchasedAt": "2026-11-08",
  "internalNote": null
}
```

Not every project wants snake_case, `NON_NULL`, or rejecting unknown fields. These policies are **chosen intentionally so tests can observe clear differences**, not recommended blindly for every API. For example, many public APIs prioritize backward/forward compatibility and deliberately ignore unknown fields.

## 6. Production configuration: properties, customizers, modules, and converters

### 6.1. Application properties in Spring Boot 3.x

You can define several mapper rules in `application.properties`:

```properties
spring.jackson.property-naming-strategy=SNAKE_CASE
spring.jackson.default-property-inclusion=non_null
spring.jackson.serialization.write-dates-as-timestamps=false
spring.jackson.deserialization.fail-on-unknown-properties=true
```

This is an **alternative configuration approach** to the Java config in section 7; **do not add both simultaneously to that sample and try to deduce precedence rules from it**. These properties are supported in Spring Boot 3.x; verify exact property keys in your project's version.

Advantages: policies are easy to inspect in config and override per profile. Limitation: slice tests may load a **different file/profile** or have overriding test properties, so verify effective configuration rather than assuming which file was loaded.

### 6.2. `Jackson2ObjectMapperBuilderCustomizer`

When configuring in code, Spring Boot 3.x supports:

```java
org.springframework.boot.autoconfigure.jackson
        .Jackson2ObjectMapperBuilderCustomizer
```

A bean of this type customizes the builder Boot uses to construct the mapper. It is usually preferable to replacing `ObjectMapper` outright because it preserves Boot's auto-configuration and modules.

A customizer can configure:

- `propertyNamingStrategy(...)`;
- `serializationInclusion(...)`;
- `featuresToEnable(...)` or `featuresToDisable(...)`;
- date/time formats, serializers/deserializers, visibility, or modules as needed.

**Watch ordering:** if a project has multiple customizers, application order affects the final settings. A slice test importing only one customizer while production has another can still diverge. To prove the contract, verify the effective behavior in a full context too.

### 6.3. Jackson Modules

Jackson modules can supply:

- Java Time serializers/deserializers;
- support for JDK8 types, optionals, or domain types;
- custom serializers/deserializers;
- mixins, subtypes, or polymorphic typing behavior.

If a test creates `new ObjectMapper()` and forgets a module, output differs from Boot's mapper. If a production module is declared via `@Bean Module` in a `@Configuration` excluded by the slice, the JSON slice can miss it. Import the right module/config intentionally when needed.

**Avoid "registering lots of modules just in case."** Modules can change behavior, conflict on serializers, or already be auto-registered by Boot depending on version. Identify required modules and write behavioral tests for them.

### 6.4. `@JsonComponent`, `@JsonMixin`, and DTO annotations

- `@JsonComponent` in Boot 3.x registers Spring-integrated Jackson serializers/deserializers.
- `@JsonMixin` attaches Jackson annotations to a type without editing that type's source.
- `@JsonProperty("...")` pins a specific field name regardless of global naming strategy.
- `@JsonFormat` sets formatting for individual temporal properties.
- `@JsonInclude`/`@JsonIgnore` can override global rules at the type/field level.
- `@JsonView` can make controller responses differ from default mapper output when views differ.

Do not assume "global mapper naming strategy is broken" just because one DTO overrides a name with `@JsonProperty`. When an endpoint uses a Jackson view, tests must supply that view or assert the HTTP response rather than simply calling default `mapper.writeValueAsString(dto)`.

### 6.5. MVC HTTP message converters can use a different mapper

Spring MVC uses `HttpMessageConverter` to read/write HTTP bodies. In Boot 3.x with Jackson, the standard converter is `MappingJackson2HttpMessageConverter`. However, an application can:

- declare a dedicated converter with its own mapper;
- have customizers/converters alter global configuration;
- pick a different converter by `Content-Type`/`Accept`;
- use another serializer like Gson or JSON-B in configured setups;
- apply endpoint-specific views, response wrappers, or request body advice.

Therefore, **that the mapper bean shares the same policy as the HTTP converter** must be proven by **HTTP contract tests**. Assuming "I injected `ObjectMapper` A, so every endpoint uses A" is unsafe in multi-converter apps.

## 7. Runnable Java 17+ / Spring Boot 3.x example

The example includes **one shared production configuration**, a JSON slice test, a full-context MVC test, and a live HTTP test to verify parity across all three boundaries. It requires **no Docker, database, external service, or Spring Security**.

All production sources live in package `com.example.mapperparity`; test classes share the same package. It uses Spring Boot 3.x (such as the 3.5 line), Java 17+, JUnit Jupiter, starter web, and starter test. Do not add a second production `ObjectMapper` or custom MVC converter into this exact sample.

### 7.1. Dependencies

Gradle Groovy DSL — dependencies/test task snippet in a project **already configured** with the Spring Boot plugin, repositories, dependency management, and Java 17 toolchain:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

Maven — dependencies snippet in a project already configured with the Spring Boot parent/BOM, Java 17 compiler/toolchain, and Surefire for JUnit Jupiter:

```xml
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
```

**These are build file snippets, not complete `pom.xml`/`build.gradle` files.** In Boot 3.x, starter web includes Jackson JSON support and Java Time modules via managed dependencies; the test starter includes Spring Test, `JacksonTester` integration, JUnit Jupiter, and AssertJ.

### 7.2. File structure

```text
src/
├── main/java/com/example/mapperparity/
│   ├── MapperParityApplication.java
│   ├── PurchaseEvent.java
│   ├── SharedJsonConfiguration.java
│   └── PurchaseEventController.java
└── test/java/com/example/mapperparity/
    ├── PurchaseEventJsonSliceTest.java
    ├── PurchaseEventMvcContractTest.java
    └── PurchaseEventLiveHttpTest.java
```

**No separate properties file is needed** to run the example. Production configuration resides in `SharedJsonConfiguration`, without being copied into divergent test logic.

### 7.3. Application class

**File `src/main/java/com/example/mapperparity/MapperParityApplication.java`:**

```java
package com.example.mapperparity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MapperParityApplication {
    public static void main(String[] args) {
        SpringApplication.run(MapperParityApplication.class, args);
    }
}
```

Placing the main class in the root package ensures component scanning picks up both the controller and production JSON configuration in the full application context.

### 7.4. DTO as a Java record

**File `src/main/java/com/example/mapperparity/PurchaseEvent.java`:**

```java
package com.example.mapperparity;

import java.time.LocalDate;

public record PurchaseEvent(
        String orderId,
        LocalDate purchasedAt,
        String internalNote
) {}
```

No `@JsonProperty` or `@JsonFormat` is placed on the DTO in this example so the **effect of shared mapper configuration** is clearly visible. Java records generate accessors matching component names; Jackson provided by Boot 3/starter web supports records and Java Time.

### 7.5. Mapper configuration actually used by the application

**File `src/main/java/com/example/mapperparity/SharedJsonConfiguration.java`:**

```java
package com.example.mapperparity;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.SerializationFeature;

import org.springframework.boot.autoconfigure.jackson.Jackson2ObjectMapperBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class SharedJsonConfiguration {

    @Bean
    Jackson2ObjectMapperBuilderCustomizer jsonContractCustomizer() {
        return builder -> {
            builder.propertyNamingStrategy(
                    PropertyNamingStrategies.SNAKE_CASE);
            builder.serializationInclusion(
                    JsonInclude.Include.NON_NULL);
            builder.featuresToEnable(
                    DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
            builder.featuresToDisable(
                    SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
        };
    }
}
```

**Explanation:**

1. `@Configuration` and `@Bean` create a customizer inside the full application context.
2. `propertyNamingStrategy(SNAKE_CASE)` turns `orderId` into `order_id`, `purchasedAt` into `purchased_at`, and `internalNote` into `internal_note`.
3. `serializationInclusion(NON_NULL)` omits null properties from JSON responses.
4. `FAIL_ON_UNKNOWN_PROPERTIES` causes the mapper to reject JSON with properties outside the DTO.
5. `WRITE_DATES_AS_TIMESTAMPS` is disabled; with `JavaTimeModule` in Boot 3's starter setup, `LocalDate` serializes as an ISO string like `"2026-11-08"`.
6. The slice test **must import this configuration** since it is not part of the default scanned JSON components; full `@SpringBootTest` picks it up through application component scanning.

The strength of this design: changing a JSON policy edits **one production class**, and both the JSON slice and HTTP tests immediately reflect the updated contract. There is no "test-only `ObjectMapper`" duplicating settings.

### 7.6. Controller using Spring MVC request/response JSON

**File `src/main/java/com/example/mapperparity/PurchaseEventController.java`:**

```java
package com.example.mapperparity;

import java.time.LocalDate;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/purchases")
public class PurchaseEventController {

    @GetMapping("/sample")
    public PurchaseEvent sample() {
        return new PurchaseEvent(
                "PO-42",
                LocalDate.of(2026, 11, 8),
                null);
    }

    @PostMapping("/echo")
    public PurchaseEvent echo(@RequestBody PurchaseEvent event) {
        return event;
    }
}
```

The controller does not inject `ObjectMapper` directly. Spring MVC selects the HTTP message converter for request/response bodies. That is intentional: **HTTP tests cannot succeed via a test-created mapper**, and must pass through the application's configured JSON converter.

Endpoints:

- `GET /api/purchases/sample` → object with snake_case names, ISO date, and no null property.
- `POST /api/purchases/echo` with valid JSON → deserializes into the record and serializes back.
- POST with an unknown field → HTTP 400 because the converter fails reading the body under strict unknown-field policy.
- POST using undeclared camelCase keys → under this strict setup, the converter rejects them as unknown properties.

Bean Validation is omitted here to avoid mixing validation 400 errors with Jackson deserialization 400 errors.

### 7.7. JSON slice test — reusing production configuration

**File `src/test/java/com/example/mapperparity/PurchaseEventJsonSliceTest.java`:**

```java
package com.example.mapperparity;

import java.time.LocalDate;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.databind.exc.UnrecognizedPropertyException;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.json.JsonTest;
import org.springframework.boot.test.json.JacksonTester;
import org.springframework.context.annotation.Import;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@JsonTest
@Import(SharedJsonConfiguration.class)
class PurchaseEventJsonSliceTest {

    @Autowired
    JacksonTester<PurchaseEvent> json;

    @Autowired
    ObjectMapper mapper;

    @Test
    void writesConfiguredNamesDatesAndNullInclusion()
            throws Exception {

        PurchaseEvent event = new PurchaseEvent(
                "PO-42", LocalDate.of(2026, 11, 8), null);

        assertThat(json.write(event)).isEqualToJson(
                """
                {
                  "order_id": "PO-42",
                  "purchased_at": "2026-11-08"
                }
                """);

        String encoded = mapper.writeValueAsString(event);
        assertThat(encoded)
                .contains("\"order_id\"")
                .contains("\"purchased_at\"")
                .doesNotContain("\"internal_note\"");
    }

    @Test
    void readsConfiguredSnakeCaseJsonIntoRecord()
            throws Exception {

        String content = """
                {
                  "order_id": "PO-42",
                  "purchased_at": "2026-11-08"
                }
                """;

        PurchaseEvent actual = json.parseObject(content);

        assertThat(actual).isEqualTo(new PurchaseEvent(
                "PO-42", LocalDate.of(2026, 11, 8), null));
    }

    @Test
    void rejectsUnknownJsonField()
            throws Exception {

        String invalid = """
                {
                  "order_id": "PO-42",
                  "purchased_at": "2026-11-08",
                  "unknown_field": "not-in-contract"
                }
                """;

        assertThatThrownBy(() ->
                mapper.readValue(invalid, PurchaseEvent.class))
                .isInstanceOf(UnrecognizedPropertyException.class);
    }

    @Test
    void confirmsEffectiveMapperFeatureConfiguration() {
        assertThat(mapper.getPropertyNamingStrategy())
                .isSameAs(PropertyNamingStrategies.SNAKE_CASE);

        assertThat(mapper.getSerializationConfig()
                .getDefaultPropertyInclusion()
                .getValueInclusion())
                .isEqualTo(JsonInclude.Include.NON_NULL);

        assertThat(mapper.isEnabled(
                DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES))
                .isTrue();

        assertThat(mapper.isEnabled(
                SerializationFeature.WRITE_DATES_AS_TIMESTAMPS))
                .isFalse();
    }
}
```

**Expected:** 4 `@Test` methods pass in Spring Boot 3.x with the described dependencies. `@JsonTest` creates a JSON-focused context and auto-configures `JacksonTester`. `@Import(SharedJsonConfiguration.class)` forces the slice to apply the **exact customizer bean used in production**, without duplicating mapper policy in test code.

The four tests verify independent contracts:

- JSON serialization shape;
- deserialization from `snake_case` + ISO date;
- strict unknown-field handling;
- effective mapper settings inside the JSON slice.

Note: `@JsonTest` is not a full MVC test; it **does not yet** prove the controller's HTTP converter uses the same policy. The next section does that.

### 7.8. Full-context MockMvc test — verifying the actual HTTP converter

**File `src/test/java/com/example/mapperparity/PurchaseEventMvcContractTest.java`:**

```java
package com.example.mapperparity;

import java.time.LocalDate;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(
    classes = MapperParityApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.MOCK
)
@AutoConfigureMockMvc
class PurchaseEventMvcContractTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ObjectMapper mapper;

    @Test
    void mvcResponseMatchesConfiguredMapperContract()
            throws Exception {

        MvcResult result = mvc.perform(
                get("/api/purchases/sample")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.order_id").value("PO-42"))
                .andExpect(jsonPath("$.purchased_at")
                        .value("2026-11-08"))
                .andExpect(jsonPath("$.internal_note").doesNotExist())
                .andReturn();

        PurchaseEvent expectedValue = new PurchaseEvent(
                "PO-42", LocalDate.of(2026, 11, 8), null);

        JsonNode expectedFromBean = mapper.valueToTree(expectedValue);
        JsonNode actualFromMvc = mapper.readTree(
                result.getResponse().getContentAsByteArray());

        assertThat(actualFromMvc).isEqualTo(expectedFromBean);
    }

    @Test
    void mvcRequestAndResponseUseSnakeCaseContract()
            throws Exception {

        mvc.perform(post("/api/purchases/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {
                          "order_id": "PO-99",
                          "purchased_at": "2026-11-09"
                        }
                        """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.order_id").value("PO-99"))
                .andExpect(jsonPath("$.purchased_at")
                        .value("2026-11-09"))
                .andExpect(jsonPath("$.internal_note").doesNotExist());
    }

    @Test
    void mvcRejectsUnknownJsonFieldWithBadRequest()
            throws Exception {

        mvc.perform(post("/api/purchases/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {
                          "order_id": "PO-42",
                          "purchased_at": "2026-11-08",
                          "unknown_field": true
                        }
                        """))
                .andExpect(status().isBadRequest());
    }

    @Test
    void mvcRejectsCamelCaseKeyWhenStrictSnakeCaseIsRequired()
            throws Exception {

        mvc.perform(post("/api/purchases/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {
                          "orderId": "PO-42",
                          "purchased_at": "2026-11-08"
                        }
                        """))
                .andExpect(status().isBadRequest());
    }
}
```

**Expected:** 4 tests pass. Unlike the JSON slice:

1. Spring Boot loads the **full application context** from `MapperParityApplication`; `SharedJsonConfiguration` is a production bean found via component scan.
2. MockMvc sends GET/POST requests through Spring MVC and the configured HTTP converters.
3. Tests check JSON **on the response**, not merely direct calls to `mapper.writeValueAsString(...)`.
4. The test reads the HTTP response into `JsonNode` and compares against `mapper.valueToTree(expectedValue)`. Because independent JSONPath assertions also check the HTTP boundary, a converter accidentally using camelCase or emitting null fields cannot slip through silently.
5. POST verifies **HTTP request deserialization**; two negative tests prove the unknown/camelCase rejection policy is enforced by the converter.

**Never keep only the `JsonNode expected == actual` assertion.** Because the test uses the mapper bean to parse the response, if the mapper and converter somehow drifted yet agreed on one representation, you need independent JSONPath assertions to pin **external field names**. This class uses both.

### 7.9. Live HTTP smoke test — JSON traveling over server and socket

**File `src/test/java/com/example/mapperparity/PurchaseEventLiveHttpTest.java`:**

```java
package com.example.mapperparity;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    classes = MapperParityApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class PurchaseEventLiveHttpTest {

    @LocalServerPort
    int port;

    @Autowired
    ObjectMapper mapper;

    private final HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(3))
            .build();

    private URI endpoint(String path) {
        return URI.create(
                "http://127.0.0.1:" + port + path);
    }

    @Test
    void actualHttpResponseHasSameJsonFieldContract()
            throws Exception {

        assertThat(port).isGreaterThan(0);

        HttpRequest request = HttpRequest.newBuilder(
                endpoint("/api/purchases/sample"))
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));

        assertThat(response.statusCode()).isEqualTo(200);
        assertThat(response.headers()
                .firstValue("Content-Type")
                .orElse(""))
                .contains("application/json");

        JsonNode body = mapper.readTree(response.body());
        assertThat(body.path("order_id").asText())
                .isEqualTo("PO-42");
        assertThat(body.path("purchased_at").asText())
                .isEqualTo("2026-11-08");
        assertThat(body.has("internal_note")).isFalse();
        assertThat(body.has("orderId")).isFalse();
    }

    @Test
    void actualHttpRequestRejectsUnknownField()
            throws Exception {

        HttpRequest request = HttpRequest.newBuilder(
                endpoint("/api/purchases/echo"))
                .timeout(Duration.ofSeconds(5))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(
                        """
                        {
                          "order_id": "PO-42",
                          "purchased_at": "2026-11-08",
                          "unknown_field": "must-reject"
                        }
                        """, StandardCharsets.UTF_8))
                .build();

        HttpResponse<String> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));

        assertThat(response.statusCode()).isEqualTo(400);
    }
}
```

**Expected:** 2 tests pass on a valid Spring Boot 3.x Servlet MVC project; the full example has **10 tests: 4 JSON slice, 4 MVC full-context, and 2 live HTTP**.

The live HTTP tests verify the embedded server, client serialization, and HTTP response bodies over a socket. They **do not prove** production proxies/TLS/ingress or deployment configuration, as the test uses `http://127.0.0.1` and the JVM's test profile.

### 7.10. Running tests from IDE/Gradle/Maven

On Linux/macOS:

```bash
# Gradle — run each class individually:
./gradlew test --tests "com.example.mapperparity.PurchaseEventJsonSliceTest"
./gradlew test --tests "com.example.mapperparity.PurchaseEventMvcContractTest"
./gradlew test --tests "com.example.mapperparity.PurchaseEventLiveHttpTest"

# Or Maven — run each class individually:
./mvnw -Dtest=PurchaseEventJsonSliceTest test
./mvnw -Dtest=PurchaseEventMvcContractTest test
./mvnw -Dtest=PurchaseEventLiveHttpTest test
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.mapperparity.PurchaseEventJsonSliceTest"
.\gradlew.bat test --tests "com.example.mapperparity.PurchaseEventMvcContractTest"
.\gradlew.bat test --tests "com.example.mapperparity.PurchaseEventLiveHttpTest"

# Or Maven:
.\mvnw.cmd "-Dtest=PurchaseEventJsonSliceTest" test
.\mvnw.cmd "-Dtest=PurchaseEventMvcContractTest" test
.\mvnw.cmd "-Dtest=PurchaseEventLiveHttpTest" test
```

Use only the commands for the build tool your project uses. Running the three classes with three separate commands runs only that class's tests each time; running `./gradlew test` or `./mvnw test` contributes these 10 tests alongside the rest of the project's tests.

There is no specific stdout line intentionally printed by the source. JUnit runners, Boot startup, and build tools print logs/reports depending on version; verify **test counts, pass/fail/skipped, and root causes**. Use the wrapper so IDE and CI share the same build tool version.

### 7.11. Comparison table across the three boundaries

| Contract | `@JsonTest` | Full-context MockMvc | Real HTTP |
|---|---|---|---|
| Uses production `SharedJsonConfiguration` | Explicit `@Import` | App component scan | App component scan |
| Mapper bean writes `snake_case` | Checked directly | Bean present and observed in response | Observed in response over socket |
| Null property omitted | Asserted on serialization | JSONPath `doesNotExist()` | Parsed body, `has(...) == false` |
| `LocalDate` is ISO string | Asserted via JSON tester | JSONPath response and POST parsing | GET response |
| Unknown field rejected | Mapper `UnrecognizedPropertyException` | HTTP 400 via request-body converter | HTTP 400 over socket |
| MVC converter actually obeys config | No, slice has no endpoints | **Yes** | **Yes** |
| TCP/embedded container works | No | No | **Yes** |
| Production proxy/TLS/ingress works | No | No | No, unless testing through that exact infra |

## 8. When `@JsonTest` differs from the full application: concrete causes

### 8.1. Production configuration lies outside the slice

`@JsonTest` intentionally narrows component scanning. For example:

```java
@Configuration
class ApplicationJsonConfiguration {
    @Bean
    Jackson2ObjectMapperBuilderCustomizer customize() {
        return builder ->
                builder.propertyNamingStrategy(
                        PropertyNamingStrategies.SNAKE_CASE);
    }
}
```

This is a **non-standalone snippet** illustrating a production configuration. If a test writes:

```java
@JsonTest
class OrderJsonTest {
    @Autowired JacksonTester<Order> json;
}
```

you **must not assume** `ApplicationJsonConfiguration` was scanned. If the builder customizer is a required part of the contract, add `@Import(ApplicationJsonConfiguration.class)` on the test class. Reuse the production source-of-truth config instead of defining another customizer just to pass.

### 8.2. Profile/property drift

Suppose production sets:

```properties
spring.jackson.default-property-inclusion=non_null
```

while the test sets:

```java
@JsonTest(properties = 
        "spring.jackson.default-property-inclusion=always")
class ProfileDependentJsonTest {
}
```

When a test deliberately overrides production settings, divergent output is the **right behavior under different configuration**. Never label it a "serialization bug" before comparing:

- active Spring profiles;
- `application.properties`/`application-test.properties`/config imports;
- `properties` attributes on `@JsonTest`/`@SpringBootTest`;
- `@TestPropertySource` or `@DynamicPropertySource` if present;
- runtime OS env vars/JVM system properties/CLI args;
- customizer ordering and conditional bean creation.

Only compare outputs side by side when both sides share the **exact same contract configuration**. Some tests need separate profiles to isolate DB/security, yet JSON contracts should be pinned via assertions or configuration imports so they do not drift unintentionally.

### 8.3. `@JsonComponent` / Jackson Modules may be scanned differently

In Spring Boot 3.x, `@JsonTest` scans a restricted set of components such as `@JsonComponent` and `Module` (when Jackson is present). However:

- A `@Bean Module` declared inside a `@Configuration` class excluded from the slice can be absent.
- A `@JsonComponent` class outside the scan root package does not appear automatically.
- Auto-configuration/module discovery changes across Boot/Jackson versions.
- A custom module overriding a DTO's serializer produces different results from a mapper without that module registered.

If that production module is required, explicitly import the configuration packaging it, or use a full-context test for the contract. Do not clone serializer logic into tests.

### 8.4. Multiple mapper beans

An application might declare:

```java
@Bean
@Primary
ObjectMapper apiMapper() {
    // Custom mapper for API.
}
```

**This snippet only illustrates the concept, not runnable source** (the body lacks a return statement and should not be copied verbatim). Pitfalls to inspect:

- `@Primary` affects injection by type, without guaranteeing every converter/client uses it.
- A converter might hold a reference to a separately instantiated mapper.
- An HTTP client like `RestClient`/`WebClient` might have different codec/converter configuration.
- Kafka/Redis producers or logging might use a separate mapper.
- Replacing Boot's auto-configured `ObjectMapper` bean can disable Boot's builder defaults/customizers/modules.

To verify, check the mapper/converter along the **real execution path**, not just `context.getBean(ObjectMapper.class)`.

## 9. Inspecting the mapper used by MVC converters during deep debugging

In Spring MVC on Boot 3.x, you can inspect the message converters configured on `RequestMappingHandlerAdapter`:

```java
@Autowired
RequestMappingHandlerAdapter handlerAdapter;

@Test
void listJacksonMappersForDiagnostics() {
    handlerAdapter.getMessageConverters().stream()
            .filter(MappingJackson2HttpMessageConverter.class::isInstance)
            .map(MappingJackson2HttpMessageConverter.class::cast)
            .forEach(converter -> {
                ObjectMapper used = converter.getObjectMapper();
                assertNotNull(used);
            });
}
```

This is a **diagnostic snippet**, not a complete runnable class; it requires the right imports, an MVC test context, and JUnit assertions. Asserting only non-null here has limited value; to prove real parity, inspect **mapper configuration or response JSON**.

Several deeper notes:

1. In apps with multiple Jackson converters, `getMessageConverters()` may return several converters serving different media types. Never assume "the first converter handles every response."
2. Jackson converters can carry type-specific or media-type-specific configurations depending on Spring Framework version.
3. A converter's `ObjectMapper` and an injected bean can be different references with identical behavior. Comparing `==` does not replace API-contract assertions.
4. On WebFlux, JSON encoding/decoding uses reactive `Encoder/Decoder` beans and codec configuration; do not look for MVC's `RequestMappingHandlerAdapter` as a universal solution.
5. With custom `@JsonView`, a view-aware serializer can produce different output from `mapper.writeValueAsString(value)` and still be completely right.

In real projects, prefer keeping **black-box** tests with JSONPath/JSON body assertions, reserving mapper introspection for tracking down drift.

## 10. Why should you avoid replacing the ObjectMapper bean just to fix tests?

A common reaction to JSON slice failures is adding:

```java
@TestConfiguration
class ExtraTestConfig {
    @Bean
    ObjectMapper objectMapper() {
        return new ObjectMapper();
    }
}
```

This is an **anti-pattern** for parity; it omits imports and illustrates what not to do. It may get the test context to start, yet the fresh mapper lacks production's modules, naming strategy, and serialization config.

Another anti-pattern is spying/mocking `ObjectMapper` and stubbing `writeValueAsString(...)` with hard-coded JSON: the test then exercises your own stub rather than real Jackson.

When a JSON bean is missing in `@JsonTest`, distinguish:

- Is the bean a Jackson `Module` or `@JsonComponent`? Check scanning/packages/module registration.
- Is the bean a `Jackson2ObjectMapperBuilderCustomizer` in a configuration class? `@Import` the source of truth.
- Does the bean depend on a DB/service unrelated to JSON? Separate mapper config from business infrastructure.
- Are you only testing a DTO? Use a contract-matching mapper without pulling in the full context unnecessarily.
- Do you need to prove the application's converter? Use full-context MockMvc or live HTTP.

### 10.1. Customizers and `@Bean ObjectMapper` are not the same

In Boot 3.x, auto-config builds `ObjectMapper` from Boot's customized builder. A `Jackson2ObjectMapperBuilderCustomizer` participates in that build step, whereas declaring a user `@Bean ObjectMapper` causes Boot to **back off** from creating its default mapper.

If you build the mapper yourself, you take responsibility for:

- registering required modules;
- maintaining defaults for dates/times, unknown fields, and naming;
- thread-safe lifecycle/configuration before use;
- ensuring converters/clients receive that exact mapper;
- custom serialization and corresponding tests.

When you only want to adjust a few rules, using properties or builder customizers is far less risky.

## 11. Date/time: how data types and timezones skew JSON

### 11.1. `LocalDate` is not `Instant`

In the example, `LocalDate.of(2026,11,8)` is a **calendar date without time or timezone**. Valid JSON is `"2026-11-08"` when Jackson's Java Time module and date settings match the sample.

Never set `spring.jackson.time-zone=Asia/Ho_Chi_Minh` and expect `LocalDate` to shift to another day. `LocalDate` carries no offset or instant to shift by timezone the way `Date`/`Instant` might when formatted.

### 11.2. `Instant` and `OffsetDateTime` are different contracts

For types like `Instant`, `OffsetDateTime`, or `ZonedDateTime`:

- agree on API format, UTC/offset policy, and fractional-second precision;
- distinguish timezone-formatted serialization from the underlying instant;
- avoid relying on developer/CI system default timezones;
- use fixed test values, never `LocalDateTime.now()`/`Instant.now()` when asserting exact JSON;
- verify whether Jackson modules or `@JsonFormat` override global rules.

Example domain choice: transaction timestamps can normalize to UTC; birthdates should use `LocalDate`. Never swap Java temporal types just to satisfy a string match in tests.

### 11.3. Null, missing, and empty string are three states

- `"internal_note": null`: field **present** with JSON null.
- No `internal_note`: field **absent**.
- `"internal_note": ""`: field has an empty string.

Global `NON_NULL` omits nulls during **serialization**; it does not automatically drop empty strings, empty collections, or alter deserialization behavior. Tests should use `JsonNode.has(...)`/JSONPath to distinguish "absent" from "key present with null value."

### 11.4. Do not enforce JSON field order unless it is contracted

Two JSON objects with identical key/value pairs in different orders represent the same JSON structure. `JacksonTester.isEqualToJson(...)` or `JsonNode` comparisons are normally more appropriate than raw literal string checks when field order is uncontracted.

If a system signs payloads by byte sequence or mandates a canonical JSON spec, that is a separate contract: use a dedicated serializer/canonicalizer and test exact bytes rather than inferring from structural JSON equality.

## 12. Unknown fields and backwards compatibility

### 12.1. Why did the sample enable strict unknown fields?

Spring Boot 3/Jackson 2 adjusts several defaults, including disabling `DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES` in many default setups. The sample **deliberately enables** this feature to catch JSON clients sending out-of-contract keys.

If a client sends:

```json
{
  "order_id": "PO-42",
  "purchased_at": "2026-11-08",
  "unrecognized_key": 5
}
```

the Jackson 2 `ObjectMapper` in strict mode rejects the unknown key; through Spring MVC's request converter, this maps to `HttpMessageNotReadableException` and HTTP 400.

### 12.2. Strict is not always the best choice

If an API allows clients to send newer fields not yet recognized by older servers, ignoring unknown fields improves compatibility. If an API is a strict internal command, strict mode catches schema typos early.

**Choose policy by contract:** good tests follow the published and consistently enforced API policy, not the arbitrary default of any particular Jackson version.

### 12.3. 400 errors have multiple sources

A POST can return 400 due to:

- Jackson failing to parse JSON syntax;
- wrong field type in JSON;
- unknown field under strict config;
- missing required creator property per rules;
- Bean Validation `@Valid`/constraints;
- controller advice mapping domain errors to 400.

When debugging, inspect the resolved exception/matched handler rather than assuming any 400 proves strict unknown-property checking ran. The sample omits `@Valid` to keep these causes clearly separated.

## 13. Multi-profile setups and test context caching

### 13.1. Are tests really using the same configuration?

If production activates profile `prod` with extra Jackson beans, while tests use `@ActiveProfiles("test")` and those beans carry `@Profile("prod")`, the two mappers cannot match.

Many apps **intentionally** avoid enabling production profiles in tests to prevent live DB/external connections. In that case:

1. Keep JSON contract configuration **environment-independent** whenever possible.
2. When config must be profile-specific, define the JSON contract per profile and test each explicitly.
3. Never run tests with production secrets or connections just to make "the mapper match production."
4. Use a test profile while **importing/enabling the same JSON contract source of truth**.
5. Keep regression tests at the HTTP boundary to catch config added by the full context.

### 13.2. Cache keys and test state

Spring TestContext caches application contexts to reduce startup overhead. Test settings (profiles, properties, imports, mock overrides) contribute to the context cache key.

If a test calls:

```java
mapper.setPropertyNamingStrategy(
        PropertyNamingStrategies.LOWER_CAMEL_CASE);
```

on the injected singleton mapper after the context is running, you mutate **shared mutable config** on that mapper, impacting other tests or already-constructed converters. This is an **anti-pattern**; Jackson 2 recommends configuring mappers **before use** and using `ObjectReader`/`ObjectWriter` for per-request variations.

Never mutate the shared production mapper singleton inside `@BeforeEach` to create scenarios; use dedicated test config/beans, `mapper.copy()` in unit tests when appropriate, or separate contexts for alternative configurations. When testing dynamic runtime config changes, account for bean/converter lifecycles and real concurrency.

### 13.3. `@DirtiesContext` does not substitute for design

`@DirtiesContext` can evict a context from the cache when state gets dirtied, yet it slows down the suite and does not solve configuration intent. Keep mappers effectively immutable in usage, isolate test classes by contract, and maintain a single source of configuration truth.

## 14. Jackson modules, mixins, and custom serializers: verifying registration paths

### 14.1. Configuration via `@JsonComponent`

A custom serializer for money, enums, or value objects can be annotated `@JsonComponent` in Boot 3.x. When both the JSON slice and the full context scan it, behavior matches.

However, if `@JsonComponent` lies outside the root scan package or is excluded by filters, the slice test may miss it. Then:

- check package scanning, include filters, and imports;
- check serializer/deserializer classes target the right type;
- check whether another module/converter overrides the serializer;
- add a contract test for that concrete type.

Do not assert only that the bean exists; serialize a real value to prove the serializer actually ran.

### 14.2. `@JsonMixin` affects annotations that DTOs do not show

Mixins can attach `@JsonIgnore`, `@JsonProperty`, or formatting to third-party classes whose source cannot be modified. A DTO test using a plain mapper unaware of mixins produces different output from production.

To test parity, ensure mixin registration is included in the test slice via Boot's mechanism, and add a full-context HTTP test for endpoints using that type. Note Boot 3.x uses `@JsonMixin` (distinct from Boot 4's `@JacksonMixin`).

### 14.3. Third-party library modules

When adding a library supporting a new type, the mapper may need a dedicated module. Never assume `findAndRegisterModules()` behaves identically across Boot versions: Spring Boot 3 and Boot 4 have different module discovery policies.

When a module is part of the API contract, test a value of that type for both read and write. Subtle bugs often surface only during **deserialization** even while serialization passes.

### 14.4. When mappers used by `RestClient`/`WebClient` differ from MVC

An app acting as both HTTP server and HTTP client may use:

- Spring MVC `MappingJackson2HttpMessageConverter`;
- `RestClient`/`RestTemplate` converters;
- WebFlux `Jackson2JsonEncoder`/`Jackson2JsonDecoder` or other codecs;
- message broker serializers;
- custom `ObjectMapper` instances in business libraries.

They do not automatically share the same mapper bean. Test every **contracted boundary**: server responses, outbound remote requests, message payloads, or cache representations. A passing JSON slice proves the DTO contract for the test mapper; it does not replace outbound HTTP client tests.

## 15. Spring Boot 3.x to 4.x: switching from Jackson 2 to Jackson 3

This is a major change, **not merely swapping one annotation import**.

| Topic | Spring Boot 3.x / Jackson 2 | Spring Boot 4.x / Jackson 3 default |
|---|---|---|
| Primary mapper | `com.fasterxml.jackson.databind.ObjectMapper` | `tools.jackson.databind.json.JsonMapper` |
| Builder customizer | `Jackson2ObjectMapperBuilderCustomizer` | `JsonMapperBuilderCustomizer` |
| Example customizer package | `org.springframework.boot.autoconfigure.jackson` | `org.springframework.boot.jackson.autoconfigure` |
| JSON component | `@JsonComponent` | `@JacksonComponent` |
| Mixin annotation | `@JsonMixin` | `@JacksonMixin` |
| Jackson modules | Jackson 2 `Module` | Jackson 3 `JacksonModule` |
| Naming/date/property options | `spring.jackson.*` for Boot 3 | `spring.jackson.*` for Jackson 3, with updated group/feature names |
| Jackson 2 compatibility | Default stack in Boot 3 | Boot 4 includes a **deprecated** Jackson 2 support module, not a long-term solution |
| JSON tests | Jackson 2 `@JsonTest` and `JacksonTester` | Jackson 3 `@JsonTest` and test support (version-specific APIs) |

The Spring Boot 4.0 migration guide states that **Jackson 3** is the preferred and default JSON library. Jackson databind/core packages move from `com.fasterxml.jackson...` to `tools.jackson...` (with the annotations package being an important exception). In Jackson 3, the JSON-focused mapper is `JsonMapper`; Boot provides `JsonMapperBuilderCustomizer`.

**Do not copy** `SharedJsonConfiguration` from section 7 into Boot 4 and change only dependencies. Rewrite the customizer using Jackson 3 APIs, and update imports, modules, properties, and mapping tests for the Boot 4 line in use.

### 15.1. Mapper beans in Boot 4 follow a different contract

In Boot 4/Jackson 3:

- `JsonMapper` is auto-configured for JSON.
- `@JacksonComponent`, `@JacksonMixin`, and Jackson 3 modules are the corresponding extension points.
- Defining an `ObjectMapper` bean **is no longer the default way to replace the JSON mapper**; the migration guide instructs providing a `JsonMapper` bean when replacing the JSON mapper.
- `JsonMapperBuilderCustomizer` hooks into Boot's auto-configured mapper builder, serving a similar goal with a different type/API from Boot 3.
- Jackson 3 changes several defaults compared to Jackson 2; keep **contract assertions at the HTTP boundary**, rather than relying solely on successful compilation after migration.

### 15.2. Jackson 2 compatibility on Boot 4

Spring Boot 4 provides deprecated Jackson 2 support for gradual migration. Its properties use the `spring.jackson2.*` prefix, while `spring.jackson.*` targets Jackson 3 for corresponding settings. When both mappers coexist, MVC/WebFlux/clients can select the preferred mapper via properties such as `spring.http.converters.preferred-json-mapper`.

Consequently, a test `@Autowired ObjectMapper` for Jackson 2 might pass in Boot 4 while **real MVC endpoints use Jackson 3 `JsonMapper`**. That is precisely the kind of parity bug to guard against.

**Do not design a Boot 3/Jackson 2 sample and assume its tests prove a Boot 4/Jackson 3 application.** Update the code and run contract tests on the target stack.

### 15.3. Check version-accurate documentation

- Spring Boot 3.5: JSON docs, `@JsonTest`, `Jackson2ObjectMapperBuilderCustomizer`, and MVC converters.
- Spring Boot 4.x: Jackson 3 JSON docs, `JsonMapperBuilderCustomizer`, migration guide, and corresponding `@JsonTest`.
- For projects using custom platform BOMs, verify actual resolved dependencies (especially if Jackson 2 and 3 coexist).

Never edit tests just to "fit a snapshot" when an upgrade unintentionally alters the contract; when backward compatibility is required, add regression tests and migrate libraries/configs intentionally.

## 16. Debugging when the JSON slice passes yet HTTP integration fails

| Symptom | Possible cause | Resolution |
|---|---|---|
| `@JsonTest` outputs `orderId`, HTTP outputs `order_id` | Slice does not import production naming customizer | Reuse `@Import(SharedJsonConfiguration.class)` or equivalent config |
| `new ObjectMapper()` fails to serialize `LocalDate` | Missing `JavaTimeModule`/Boot defaults | Inject Boot's mapper or fully configure a unit-test mapper if needed |
| Test omits null while HTTP includes null | HTTP converter/mapper has a different inclusion policy | Inspect MVC converters, JSONPath, and full-context config |
| Test accepts unknown fields while HTTP returns 400 | Strict deserialization enabled only in app config | Compare `FAIL_ON_UNKNOWN_PROPERTIES` and config sources |
| JSON slice fails only on CI | Different profiles, dependencies, locale/timezone, or test runner | Run wrapper; check resolved BOM and active profiles |
| `@JsonTest` fails missing service bean | Slice excludes regular service beans | Separate JSON config and import only the small config class; avoid pulling the service graph |
| `@Import` causes JSON slice to load database | Imported config pulls too much production infrastructure | Separate JSON-only configuration from DB/service configs |
| HTTP body writes dates as arrays/timestamps | `WRITE_DATES_AS_TIMESTAMPS` or Java Time module differs | Inspect mapper features at runtime and actual responses |
| `@JsonProperty` field ignores naming strategy | Explicit annotation overrides global naming | Test property-level contract; global config is not broken |
| HTTP content type is not JSON | `Accept`/`Content-Type`, converter selection, or return type differs | Send proper media type; inspect response and converters |
| HTTP 400 caused by malformed JSON rather than unknown fields | Syntax error or DTO creator type mismatch | Inspect resolved exception and root cause in tests |
| Injected `ObjectMapper` matches while HTTP JSON differs | Custom `MappingJackson2HttpMessageConverter` uses another mapper | Assert HTTP responses and inspect converters per media type |
| Mutating mapper bean makes suite flaky | Shared singleton config modified after startup/context cache | Never mutate; configure before startup, isolate tests |
| Boot 4 test injects `ObjectMapper` while JSON API uses `JsonMapper` | Jackson 3 is default; two stacks coexist | Check preferred mapper and HTTP contract; test beyond Jackson 2 |
| `@JsonTest` fails with custom `Module` | Module missing from slice or incompatible version | Check bean/module registration and classpath |
| MockMvc passes while live HTTP fails | Server, port, encoding, filters, proxies, or profile differ | Identify actual boundary; add live HTTP/infra tests |
| Golden JSON too strict on key order | Comparing raw JSON string when order is uncontracted | Use `JsonContent`/`JsonNode` for structural comparison |

### 16.1. Ordered diagnostic checklist

1. **Verify versions:** Boot major/minor, Jackson 2 or 3, Spring Framework, Java toolchain.
2. **Verify which mapper the test uses:** new instance, `@JsonTest` bean, or full-context bean.
3. **Verify properties/profiles:** `spring.jackson.*` and active test overrides.
4. **Verify customizers/modules:** are they registered in the slice? In the full context?
5. **Verify DTO annotations:** `@JsonProperty`, `@JsonFormat`, `@JsonInclude`, `@JsonView`, mixins.
6. **Verify converter/codec:** does the actual HTTP endpoint use Jackson, Gson, JSON-B, or a custom mapper?
7. **Compare behavior:** stringify a fixed DTO, parse fixed JSON, send HTTP GET/POST via MockMvc.
8. **If network matters:** send HTTP to `RANDOM_PORT` and assert the encoded body.
9. **Verify error paths:** unknown fields, malformed JSON, conversion errors, and expected HTTP statuses.
10. **Re-run CI command:** use the wrapper, verify test reports and classpath dependency resolution.

### 16.2. Logging and security

Never print full request/response bodies containing production sensitive data into test logs. JSON contract tests should use synthetic fixtures, such as `PO-42` and fixed dates. Avoid golden files holding access tokens, PII, or real production payloads.

When inspecting beans/converters, log only types/names/features needed for debugging; never dump the full environment. When an API uses custom masking, add tests ensuring sensitive fields never accidentally appear in JSON.

## 17. Reinforcement exercises

### Exercise A — Spotting mapper drift

The application sets `spring.jackson.property-naming-strategy=SNAKE_CASE`, while a test creates `new ObjectMapper()` and expects `"orderId"`. Does a passing test prove the API is right?

**Answer:** No. The test only verifies a fresh mapper lacking Spring Boot config. Use `@JsonTest` with app-equivalent config, then verify HTTP JSON via MockMvc/full context.

### Exercise B — JSON slice missing customizer

Production defines `@Bean Jackson2ObjectMapperBuilderCustomizer` in a regular `@Configuration`; `@JsonTest` returns camelCase. How should you fix it?

**Answer:** Identify the config class/module bean loaded in production and explicitly bring it into the slice via `@Import(SharedJsonConfiguration.class)`, or design a standalone reusable JSON config. Never copy the customizer into a separate `@TestConfiguration`, as the two will drift.

### Exercise C — Mapper bean matches while converter differs

A test injects `ObjectMapper mapper` and serializes an event as snake_case; HTTP returns camelCase. Which result should you trust when evaluating the API contract?

**Answer:** The HTTP output is what clients see. Investigate custom `MappingJackson2HttpMessageConverter` or converter/mapper selection, fix the app config, and keep HTTP regression tests. Checking the mapper bean alone is insufficient.

### Exercise D — Null and missing

The client contract specifies omitting `internal_note` if null. Should the test assert `jsonPath("$.internal_note").value(null)` or `doesNotExist()`?

**Answer:** Use `doesNotExist()` alongside JSON structure/`JsonNode` checks (`has(...) == false`) when proving **key absence**. "Field present with null" and "field absent" are not the same. In Spring MVC, choose the JSONPath matcher matching your exact goal for null vs missing.

### Exercise E — Boot 4 upgrade

A project migrates from Boot 3 to 4; tests still inject `com.fasterxml.jackson.databind.ObjectMapper` and pass, yet production responses diverge. Why?

**Answer:** Boot 4 defaults to Jackson 3 `tools.jackson.databind.json.JsonMapper`; Jackson 2 may coexist via a compatibility module. Testing a Jackson 2 mapper does not prove HTTP converters use Jackson 2. Migrate customizers/beans/modules and keep HTTP response contract tests against the real mapper.

### Exercise F — `LocalDate` and timezone

A test tries to force `LocalDate.of(2026,11,8)` to become `2026-11-07` simply by setting another timezone. Is that expectation right by default?

**Answer:** No. `LocalDate` has no instant or timezone; ISO local-date representation does not apply a UTC offset shift. When instant/timezone conversion is required, pick a domain type like `Instant`/`OffsetDateTime` and matching formatting policy.

### Exercise G — Never rely on JSON text key order

A test fails because a response has the right keys in a different order. Should you modify business code to preserve property order?

**Answer:** Only when property order is a true contract (very rare for typical JSON APIs). Usually use structural JSON comparison/JSONPath or `JsonNode`; isolate canonical JSON requirements separately when byte-level payload signing is required.

### Exercise H — Unknown fields: strict or lenient?

A public API requires forward compatibility for clients sending extra metadata; the QA team enables `FAIL_ON_UNKNOWN_PROPERTIES` just because it catches typos easily. Should they?

**Answer:** It depends on the API contract. Strict mode can break compatibility; if the API allows unknown metadata, test accepting/ignoring it per policy. The sample enables strict mode to illustrate drift, not as a universal default for every service.

## 18. Checklist before concluding JSON parity tests pass

- [ ] Identified whether the app uses Jackson 2/Jackson 3, Gson, or JSON-B and checked resolved dependencies.
- [ ] Identified the **real** mapper of the HTTP converter/codec under test.
- [ ] Never assumed `new ObjectMapper()` shares the Boot bean's config without proof.
- [ ] `@JsonTest` loads the required production customizers/modules/mixins.
- [ ] Used `@Import` on the source of truth instead of copying mapper configuration into tests.
- [ ] Tested both serialization and deserialization, not just one direction.
- [ ] Asserted API naming strategy: camelCase/snake_case or explicit names.
- [ ] Asserted null vs missing, without confusing either with empty strings.
- [ ] Asserted Java Time formatting/offset/timezone per the right domain type.
- [ ] Asserted unknown fields, malformed JSON, or wrong types per contract.
- [ ] Full-context MVC test verifies real JSON requests/responses through the converter.
- [ ] In apps with multiple converters, never inferred from one injected mapper that all endpoints use it.
- [ ] Verified profiles, application properties, and customizer ordering do not cause test drift.
- [ ] Never mutated a shared mapper singleton after the context was used.
- [ ] Never used `@DirtiesContext` to mask state mutation.
- [ ] Never replaced the `ObjectMapper` bean with a bare instance just to get tests to start.
- [ ] When upgrading to Boot 4, verified Jackson 3 `JsonMapper`, `@JacksonComponent`, `JsonMapperBuilderCustomizer`, and the preferred HTTP JSON mapper.
- [ ] When real HTTP contracts matter, included `RANDOM_PORT`/socket client tests without mislabeling localhost tests as full e2e.
- [ ] Fixtures use fixed synthetic dates, names, and data without leaking secrets.
- [ ] Tests were actually executed via IDE/Gradle/Maven/CI with verified counts.
- [ ] Golden JSON assertions check JSON structure without depending on key order unnecessarily.

## 19. Conclusion

**Mapper parity is the agreement between the serialization/deserialization configuration tested by tests and the configuration actually producing JSON at the application's boundary.** A `@JsonTest` importing real production customizers catches JSON errors quickly in isolation; to prove the HTTP API contract, supplement with `@SpringBootTest + @AutoConfigureMockMvc` or live HTTP tests based on risk.

A solid design has three traits: **a single source of truth for JSON config**, **assertions pinning the public contract (field names, nulls, temporal values, errors)**, and **verification on the real mapper/converter**. When upgrading Boot/Jackson or changing modules, these tests distinguish valid changes from drift that can break clients.

## Official Reference Documentation

- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@JsonTest`, `JacksonTester`, slice vs full context, MVC tests.
- [Spring Boot 3.5 — JsonTest Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/json/JsonTest.html): `@JsonComponent`/`Module` scan scope and test properties.
- [Spring Boot 3.5 — Jackson2ObjectMapperBuilderCustomizer Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/jackson/Jackson2ObjectMapperBuilderCustomizer.html): effect of builder customizers.
- [Spring Boot 3.5 — JSON Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): `spring.jackson.*` and feature toggles.
- [Spring Boot 3.x — Customize the Jackson ObjectMapper](https://docs.spring.io/spring-boot/3.4/how-to/spring-mvc.html): MVC `HttpMessageConverter`s, `ObjectMapper` beans, and builder configuration.
- [Spring Framework — HTTP Message Conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html): how MVC picks converters to read/write payloads.
- [Spring Boot 4 — JSON](https://docs.spring.io/spring-boot/reference/features/json.html): Jackson 3 `JsonMapper`, Jackson 2 compatibility, modules/mixins, and preferred mappers.
- [Spring Boot 4.0 Migration Guide — Upgrading Jackson](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide): package, builder, component, and format-specific mapper changes.
- [Spring Boot 4 — JsonMapperBuilderCustomizer Javadoc](https://docs.spring.io/spring-boot/4.0/api/java/org/springframework/boot/jackson/autoconfigure/JsonMapperBuilderCustomizer.html): customizer on Jackson 3.
- [Spring Boot 4 — JsonTest Javadoc](https://docs.spring.io/spring-boot/4.0/api/java/org/springframework/boot/test/autoconfigure/json/JsonTest.html): updated JSON slice scope.
