# Registering Jackson Modules, Serializers, and Deserializers in Spring Boot

## 1. Purpose and Context

When a REST API receives or returns JSON, Spring Boot typically uses **Jackson** to convert between JSON structures and Java objects. Most common types such as records, JavaBeans, Lists, Maps, Strings, and numbers are supported by the default configuration. However, some business data types require a custom JSON representation: identifiers, currencies, quantities with units, non-standard date formats, or contracts compatible with a legacy system.

In that case, three core concepts are:

- **JsonSerializer<T>**: writes an object of type T as JSON. Direction: Java → JSON.
- **JsonDeserializer<T>**: reads JSON and creates an object of type T. Direction: JSON → Java.
- **Module / SimpleModule**: packages and registers serializers/deserializers along with related Jackson configurations into an ObjectMapper.

In a **Spring Boot 3.3.x (Jackson 2, Spring Framework 6.1.x, Java 17+)** application, a `com.fasterxml.jackson.databind.Module` bean can be collected by Spring Boot auto-configuration to configure the Boot-managed ObjectMapper. With Spring WebFlux, Jackson encoders/decoders are wired into HTTP codecs; with Spring MVC, Jackson operates inside HTTP message converters. The two stacks differ, but at the data layer they can share the same Jackson module when using a mapper configured with that module.

This lesson focuses on **registering modules, serializers, and deserializers**—not designing a new HTTP server, replacing the entire WebFlux framework, or using Spring Boot 4.x Jackson 3 APIs. You must verify APIs when migrating an application across major versions.

Learning objectives:

1. Distinguish JsonSerializer, JsonDeserializer, SimpleModule, ObjectMapper, and HTTP JSON codecs.
2. Build a serializer/deserializer pair for a Price business type with a clear JSON contract.
3. Register the module via a Spring bean instead of calling `registerModule` per request.
4. Test both Java → JSON and JSON → Java directions.
5. Verify the module is used in the real HTTP body of a Spring WebFlux endpoint.
6. Know alternatives such as `@JsonComponent`, `@JsonSerialize`/`@JsonDeserialize`, and `Jackson2ObjectMapperBuilderCustomizer`.
7. Diagnose when a custom module works with `ObjectMapper` directly but not in WebFlux codecs or MVC converters.
8. Recognize the impact of null values, invalid data, module scope, precedence order, streaming, and security.

## 2. Where Do JSON Codecs Sit in Spring Boot?

A WebFlux annotation controller HTTP flow:

~~~mermaid
flowchart TD
    A["POST HTTP JSON body"] --> B["Reactive HTTP server / HttpHandler"]
    B --> C["DispatcherHandler + HandlerAdapter"]
    C --> D["HttpMessageReader / Jackson2JsonDecoder"]
    D --> E["ObjectMapper + Module + JsonDeserializer"]
    E --> F["Java request DTO"]
    F --> G["Controller / Service"]
    G --> H["Java response DTO"]
    H --> I["HandlerResultHandler + HttpMessageWriter"]
    I --> J["Jackson2JsonEncoder / ObjectMapper / JsonSerializer"]
    J --> K["HTTP JSON response"]
~~~

In **Spring MVC**, the JSON body reading/writing branches pass through `HttpMessageConverter`, such as `MappingJackson2HttpMessageConverter`, instead of reactive `HttpMessageReader`/`HttpMessageWriter`. However, the custom serializer/deserializer remain the same Jackson components.

### Classes with Distinct Responsibilities

| Component | Responsibility |
| --- | --- |
| Java DTO / record | Data in code; does not solely dictate the full wire format representation |
| ObjectMapper | Jackson engine managing configuration, modules, serializers, and deserializers |
| JsonSerializer<T> | Converts an object of type T into JSON |
| JsonDeserializer<T> | Reads JSON to construct type T |
| SimpleModule | Registers serializers/deserializers by type along with extensions |
| @Bean Module | Contributes a module to the Boot-managed Jackson configuration |
| Jackson2JsonDecoder | Uses ObjectMapper to decode JSON bodies in WebFlux |
| Jackson2JsonEncoder | Uses ObjectMapper to encode JSON bodies in WebFlux |
| HttpMessageReader/Writer | Spring WebFlux abstraction for reading/writing HTTP bodies |
| MappingJackson2HttpMessageConverter | HTTP body conversion for Spring MVC Servlet |
| @JsonComponent | Spring Boot 3.x way to auto-register serializers/deserializers via component scanning |
| @JsonSerialize/@JsonDeserialize | Attaches conversion directly to a type or property |

**A serializer does not automatically create a REST endpoint; a module does not automatically enable Jackson in an application missing Jackson dependencies.** Conversely, a `@RestController` returning a normal record usually does not need a custom module because Boot already configures Jackson.

## 3. When Do You Need Custom Serializers and Deserializers?

Use built-in configuration before writing code.

| Requirement | Solution to Try First | When a Module Is Needed |
| --- | --- | --- |
| Rename JSON fields from camelCase to snake_case | `@JsonProperty` or Jackson naming strategy | When the contract depends on a complex type |
| Hide a field | `@JsonIgnore` or a separate DTO | If rules must integrate across multiple types/libraries |
| ISO date/time formatting | `JavaTimeModule` and `@JsonFormat` | If a specialized format cannot be expressed |
| Omit null fields | `spring.jackson.default-property-inclusion` | When type-specific null semantics are needed |
| Convert Price to JSON string `"USD:12.50"` | No default serializer matches this contract | `JsonSerializer` + `JsonDeserializer` in `SimpleModule` |
| Serialize an entire legacy class without standard getters | DTO/annotation/mixin | When the class or contract cannot be changed |
| Support ID/value object types across many endpoints | `@JsonValue`/`@JsonCreator` when simple | Module if you want to group shared rules |
| Define a non-JSON media type | Appropriate HTTP codec/message converter | A Jackson module alone is insufficient |
| Change only a single query parameter | Converter/Formatter | No Jackson module needed |

Do not replace the global `ObjectMapper` just because one DTO has a field that needs renaming.

## 4. End-to-End Contract Example: The Price Type

An internal API has the object:

~~~java
public record Price(String currency, BigDecimal amount) {
}
~~~

With default Jackson behavior, the JSON would be represented as an object:

~~~json
{"currency":"USD","amount":12.50}
~~~

However, an integrating system requires `Price` to be **a JSON string** in the format:

~~~json
"USD:12.50"
~~~

Example request/response:

~~~json
{
  "sku": "book-7",
  "price": "USD:12.50"
}
~~~

Contract used in this lesson:

- `currency` is exactly three uppercase A-Z letters, such as `USD`, `EUR`, `VND`. This is **syntax validation only**; it does not check whether the ISO-4217 code actually exists.
- A colon `":"` separates currency and amount.
- `amount` is non-negative and represented with **exactly two decimal places** on the wire, e.g., `12.50` or `0.00`.
- Negative numbers, `"USD 12.50"` format, a JSON object instead of a string, or numbers without two decimal digits in JSON are rejected.
- No currency conversion is performed; we do not claim every currency in the world has two decimal places. This is an **example contract only**, not meant to be used verbatim as an international finance library.

Because both reading and writing matter, we need **a pair** of serializer and deserializer.

## 5. How Jackson Invokes a Serializer

When a Java DTO contains a `Price`, `ObjectMapper` looks up the serializer for that type and uses `JsonGenerator` to write JSON tokens.

Core Jackson 2 signature:

~~~java
public abstract class JsonSerializer<T> {

    public abstract void serialize(
            T value,
            JsonGenerator gen,
            SerializerProvider serializers) throws IOException;
}
~~~

This is an **illustrative signature excerpt**, not a complete source class to compile on its own.

Notes:

- `JsonGenerator.writeString` writes a **JSON string token** and performs standard JSON escaping rather than merely concatenating quotes.
- `JsonGenerator.writeStartObject`/`writeEndObject` are used when the wire format is a JSON object.
- `SerializerProvider` helps look up other serializers or configuration details; unnecessary when just writing a string.
- A shared serializer must avoid per-request mutable state in singleton fields.
- Do not use `System.out` or write HTTP responses directly from `JsonSerializer`.
- If a type can be null, Jackson typically handles null via a null serializer first; `JsonSerializer.serialize` is not necessarily called for null.

### Serializer for Price

File `PriceJsonSerializer.java` in the sample app:

~~~java
package com.example.jsoncodec;

import java.io.IOException;

import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.databind.JsonSerializer;
import com.fasterxml.jackson.databind.SerializerProvider;

public final class PriceJsonSerializer extends JsonSerializer<Price> {

    @Override
    public void serialize(
            Price price,
            JsonGenerator generator,
            SerializerProvider provider) throws IOException {

        String wire = price.currency() + ":"
                + price.amount().toPlainString();

        generator.writeString(wire);
    }
}
~~~

When a valid `Price` has normalized `amount` to scale 2, `toPlainString` produces `"12.50"` without scientific notation like `1.25E+1`. Calling `writeString` ensures it is escaped according to the JSON specification.

Do not write:

~~~java
generator.writeRaw("\"" + price.currency() + ":" +
        price.amount() + "\"");
~~~

The `writeRaw` pattern is unnecessary and easily misses escaping when wire data is complex. For a JSON string, use `writeString`.

## 6. How Jackson Invokes a Deserializer

In the reverse direction: `ObjectMapper` reads JSON tokens via `JsonParser`, selects `JsonDeserializer<Price>`, and constructs the Java object.

Core signature:

~~~java
public abstract class JsonDeserializer<T> {

    public abstract T deserialize(
            JsonParser parser,
            DeserializationContext context) throws IOException;
}
~~~

This is a contract description, not a complete class.

A good deserializer must:

1. Verify which token type is accepted (e.g., `VALUE_STRING`).
2. Parse according to an explicit contract without guessing types.
3. Reject malformed/unsupported input with a Jackson mapping exception.
4. Return a valid domain object; avoid returning null for invalid strings and letting errors leak into services.
5. Never make blocking database/network calls during JSON decoding.
6. Bound input size and avoid regexes that can trigger high CPU usage.

### Deserializer for Price

File `PriceJsonDeserializer.java`:

~~~java
package com.example.jsoncodec;

import java.io.IOException;
import java.math.BigDecimal;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonToken;
import com.fasterxml.jackson.databind.DeserializationContext;
import com.fasterxml.jackson.databind.JsonDeserializer;
import com.fasterxml.jackson.databind.JsonMappingException;
import com.fasterxml.jackson.databind.exc.InvalidFormatException;

public final class PriceJsonDeserializer extends JsonDeserializer<Price> {

    private static final Pattern WIRE =
            Pattern.compile("([A-Z]{3}):([0-9]+\\.[0-9]{2})");

    @Override
    public Price deserialize(
            JsonParser parser,
            DeserializationContext context) throws IOException {

        if (!parser.hasToken(JsonToken.VALUE_STRING)) {
            throw JsonMappingException.from(
                    parser, "Price must be a JSON string");
        }

        String text = parser.getText();
        Matcher matcher = WIRE.matcher(text);

        if (!matcher.matches()) {
            throw InvalidFormatException.from(
                    parser,
                    "Expected price format CUR:12.34",
                    text,
                    Price.class);
        }

        return new Price(
                matcher.group(1),
                new BigDecimal(matcher.group(2)));
    }
}
~~~

**Detailed explanation:**

- `JsonToken.VALUE_STRING` rejects JSON numbers/objects/arrays/booleans for `Price`.
- The pattern does not need `^...$` because `Matcher.matches` checks the **entire** string.
- Two backslashes in a Java string before the dot produce regex `\.` to match a **literal dot**, not any arbitrary character.
- `new BigDecimal(String)` preserves decimal precision instead of converting through `double`, which can introduce floating-point error.
- `InvalidFormatException` carries Jackson semantics: data is present but does not match the type's expected format.
- Currency codes are illustrative; if you want to validate real ISO currencies you can use `java.util.Currency`, but you must explicitly decide how to handle currencies with scale 0 or 3.
- Invalid data raises an error; when the exception propagates through the HTTP body reader, Spring WebFlux typically returns **400 Bad Request** unless a custom error handler alters the status.

### The Null Case

JSON:

~~~json
{"sku":"book-7","price":null}
~~~

Jackson typically **does not call `deserialize`** on a deserializer for the `VALUE_NULL` token, using separate null-handling instead. Therefore, the custom deserializer above **does not guarantee `price` is non-null**. If the API requires the field to have a value, you need DTO validation (`@NotNull` and an appropriate Jakarta Validation provider), constructor invariants, or an input DTO design with explicit checks. Serializers/deserializers do not completely replace API-layer and business validation.

## 7. Domain Record Price Enforces Invariants

A serializer should not have to guess whether `price.amount()` is negative or has too many decimal digits. The data type itself should protect its invariants.

File `Price.java`:

~~~java
package com.example.jsoncodec;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Locale;
import java.util.Objects;

public record Price(String currency, BigDecimal amount) {

    public Price {
        Objects.requireNonNull(currency, "currency");
        Objects.requireNonNull(amount, "amount");

        currency = currency.trim().toUpperCase(Locale.ROOT);

        if (!currency.matches("[A-Z]{3}")) {
            throw new IllegalArgumentException(
                    "currency must have three ASCII letters");
        }

        if (amount.signum() < 0) {
            throw new IllegalArgumentException(
                    "amount must not be negative");
        }

        amount = amount.setScale(2, RoundingMode.UNNECESSARY);
    }
}
~~~

Java 17's **compact canonical constructor** for records lets you normalize parameters before record fields are automatically assigned. For `amount`, `RoundingMode.UNNECESSARY` rejects values that require rounding to reach two decimal places; for example, `12.345` throws `ArithmeticException`. This is an intentional policy of the example, not a general Jackson requirement.

Table:

| Java Expression Creating Price | Result |
| --- | --- |
| `new Price("usd", new BigDecimal("12.5"))` | Normalized currency `USD`, amount `12.50` |
| `new Price("USD", new BigDecimal("12.50"))` | Valid |
| `new Price("EUR", new BigDecimal("0"))` | Valid, amount `0.00` |
| `new Price("USD", new BigDecimal("-1.00"))` | `IllegalArgumentException` |
| `new Price("USD", new BigDecimal("1.234"))` | `ArithmeticException` because rounding is required |
| `new Price("UNKNOWN", new BigDecimal("1"))` | `IllegalArgumentException` |
| `new Price(null, new BigDecimal("1"))` | `NullPointerException` with message `currency` |

**Important:** Java constructors throwing exceptions can lead to 500 if your service constructs invalid values mid-request. During HTTP deserialization, design error mapping to classify client input errors as 400 when appropriate; never return full stack traces to clients.

## 8. Bidirectional Registration with SimpleModule

Jackson 2 provides `com.fasterxml.jackson.databind.module.SimpleModule` to register serializers/deserializers by Java type.

Core code snippet:

~~~java
SimpleModule module = new SimpleModule("price-wire-v1");
module.addSerializer(Price.class, new PriceJsonSerializer());
module.addDeserializer(Price.class, new PriceJsonDeserializer());
~~~

On its own, this snippet **has no effect** if the module is not registered with the `ObjectMapper` used by the framework.

### Approach A: Plain Java ObjectMapper

Outside Spring, you can do:

~~~java
ObjectMapper mapper = new ObjectMapper();

SimpleModule module = new SimpleModule("price-wire-v1");
module.addSerializer(Price.class, new PriceJsonSerializer());
module.addDeserializer(Price.class, new PriceJsonDeserializer());

mapper.registerModule(module);
~~~

This illustrative snippet requires imports and the `Price*` classes. In an application without Spring, this is valid. However, **never create a new ObjectMapper per request** or call `registerModule` on a mapper already serving concurrent requests.

### Approach B: Spring Boot @Bean Module — Focus of This Lesson

In Spring Boot 3.3, the common approach is:

~~~java
package com.example.jsoncodec;

import com.fasterxml.jackson.databind.Module;
import com.fasterxml.jackson.databind.module.SimpleModule;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class PriceJacksonConfiguration {

    @Bean
    public Module priceWireModule() {
        SimpleModule module = new SimpleModule("price-wire-v1");

        module.addSerializer(
                Price.class, new PriceJsonSerializer());
        module.addDeserializer(
                Price.class, new PriceJsonDeserializer());

        return module;
    }
}
~~~

This is a complete class for the Spring Boot example in section 15. Boot auto-configuration picks up `Module` beans and applies them to `Jackson2ObjectMapperBuilder` and the Boot-configured `ObjectMapper`. Consequently, JSON HTTP readers/writers using that mapper can see the module.

**Do not add `@EnableWebFlux`** solely to register a `Module`. In Spring Boot, `@EnableWebFlux` alters WebFlux auto-configuration levels and can prevent certain Boot settings from applying as expected.

### Why Is @Bean Module Useful?

- Easy dependency injection and startup lifecycle management.
- Can bundle multiple related serializers/deserializers into one module.
- Avoids modifying every controller.
- Avoids repeatedly calling `new ObjectMapper()` inside handlers.
- Easy to verify via the `ObjectMapper` bean and HTTP integration tests.
- Separates the serialization contract from domain controllers.

**Scope of effect:** a `Module` bean only affects mappers configured to use it. If a library instantiates a standalone `new ObjectMapper()`, or a custom HTTP codec intentionally uses a different mapper, the `Module` bean does not automatically inject itself into every mapper in the JVM.

## 9. Why Can a Module Bean Affect Spring WebFlux Codecs?

Spring Boot 3.3 provides Jackson configuration for WebFlux HTTP codecs. Under default auto-configuration, Jackson JSON encoders/decoders use the Boot-configured mapper, including modules applied through Jackson auto-configuration.

Actual flow for the endpoint:

~~~text
POST Content-Type: application/json
          |
          v
HttpMessageReader / Jackson2JsonDecoder
          |
          v
Jackson ObjectMapper (with priceWireModule)
          |
          v
PriceJsonDeserializer.deserialize(...)
          |
          v
Quote(sku, Price)
          |
          v
Controller / HandlerResultHandler
          |
          v
Jackson2JsonEncoder (mapper with priceWireModule)
          |
          v
PriceJsonSerializer.serialize(...)
          |
          v
HTTP JSON string in price field
~~~

**Do not confuse:**

- `JsonDeserializer` only participates when decoding/deserializing JSON.
- `Jackson2JsonDecoder` is an HTTP-layer codec that can use `ObjectMapper` to instantiate objects.
- A module does not change `Content-Type` or convert JSON media types to CSV/XML.
- A Java POJO does not always need a custom deserializer; Jackson has built-in mechanisms for records/beans.
- `WebClient` has its own JSON codecs on the client side; verify the codec configuration of a specific `WebClient`, especially if built manually with custom `ExchangeStrategies`.

### Why Testing Only the ObjectMapper Bean Is Not Enough

A unit test calling `ObjectMapper.writeValueAsString` can PASS while HTTP requests still use a different mapper if the application replaced the HTTP codecs. Therefore **two levels of testing** are needed:

1. Direct `ObjectMapper` tests to confirm the module is registered.
2. Real HTTP tests via `WebTestClient`/`MockMvc` to confirm HTTP decoders and encoders use the module.

## 10. An Alternative: Spring Boot 3.x @JsonComponent

Spring Boot provides the **org.springframework.boot.jackson.JsonComponent** annotation to register serializers/deserializers discovered via component scanning.

Conceptual example:

~~~java
@JsonComponent
public class PriceJsonComponent {

    public static class Serializer extends JsonSerializer<Price> {
        @Override
        public void serialize(
                Price value,
                JsonGenerator generator,
                SerializerProvider provider) throws IOException {
            generator.writeString(
                    value.currency() + ":" +
                    value.amount().toPlainString());
        }
    }

    public static class Deserializer extends JsonDeserializer<Price> {
        @Override
        public Price deserialize(
                JsonParser parser,
                DeserializationContext context) throws IOException {
            // parse Price according to the described contract
            throw new UnsupportedOperationException(
                    "Example skeleton: use PriceJsonDeserializer logic");
        }
    }
}
~~~

**This is an illustrative skeleton, NOT a runnable complete class**: it needs imports and replacing the deserializer body with actual implementation. Do not put this skeleton into the section 15 project, which already has both complete classes.

Differences:

| Approach | Appropriate When |
| --- | --- |
| `@Bean Module` + `SimpleModule` | You want to register a set of serializers/deserializers in an explicit module |
| `@JsonComponent` | You want Boot to auto-detect serializers/deserializers via component scan without writing a `Module` bean |
| `@JsonSerialize`/`@JsonDeserialize` | You want local configuration on a specific type or property |
| `Jackson2ObjectMapperBuilderCustomizer` | You want to customize how `ObjectMapper` is built per application policy |
| `mapper.registerModule(...)` | Configuring a mapper outside Spring Boot or a self-managed mapper |
| WebFlux HTTP codec customization | HTTP codecs genuinely need a non-default mapper/media type/codec |

Do not use `@JsonComponent` **at the same time** as a `Module` bean to register two different implementations for the same Java type unless you intentionally control precedence. Ambiguity easily causes inconsistent behavior across environments.

## 11. Attaching Serializers/Deserializers with Jackson Annotations

If only one type or specific field has a special contract, you can annotate it:

~~~java
@JsonSerialize(using = PriceJsonSerializer.class)
@JsonDeserialize(using = PriceJsonDeserializer.class)
public record Price(String currency, BigDecimal amount) {
    // ...
}
~~~

This snippet illustrates annotation design; in the complete project in section 15 we **do not use** these two annotations because we register a module instead.

The annotation approach has the advantage of being obvious when reading the class, but has drawbacks:

- Couples the domain type to Jackson.
- Harder to vary the contract by API/version/context.
- Third-party classes whose source cannot be edited may require mixins/modules.
- Property-level annotations have different precedence from type-level annotations; test when mixing them.

Sometimes **@JsonValue + @JsonCreator** suffices for a simple value object:

~~~java
public record ExternalCode(String value) {

    @JsonValue
    public String asJson() {
        return value;
    }

    @JsonCreator(mode = JsonCreator.Mode.DELEGATING)
    public ExternalCode {
        // only illustrates the annotation on the canonical constructor
    }
}
~~~

This is a conceptual illustration, not a mandatory pattern: record canonical constructors, `@JsonCreator` mode, visibility, parameter types, and version behavior must be verified. For a task requiring a module and an explicit custom parser, `SimpleModule` is ideal to demonstrate the full API.

## 12. Modifying ObjectMapper via Builder Customizer

Spring Boot 3.3 provides **Jackson2ObjectMapperBuilderCustomizer** to configure mappers built from `Jackson2ObjectMapperBuilder`.

Example when standardizing a global property:

~~~java
@Bean
Jackson2ObjectMapperBuilderCustomizer jacksonPolicy() {
    return builder -> builder.serializationInclusion(
            JsonInclude.Include.NON_NULL);
}
~~~

This is an illustrative method inside `@Configuration`, requiring imports `org.springframework.boot.autoconfigure.jackson.Jackson2ObjectMapperBuilderCustomizer` and `com.fasterxml.jackson.annotation.JsonInclude`. In many cases a property suffices:

~~~properties
spring.jackson.default-property-inclusion=non_null
~~~

**Do not replace the entire default ObjectMapper bean just to add a module**. Declaring `@Bean ObjectMapper` or creating `new ObjectMapper()` can bypass pre-configured Java Time modules, naming strategies, Boot features, and codec wiring. If you must define your own mapper, test all modules and actual codec paths.

### Ordering and Conflicts

- One module can register a serializer for the same Java type as another module.
- Class/property annotations can affect selection and precedence.
- Global custom serializers/deserializers can alter multiple REST endpoints.
- Do not assume "the last module always wins" without verifying order, metadata, and actual Jackson serializer resolution.
- Prefer a single clear owner for each type's JSON contract; keep integration tests as guardrails when upgrading versions.

## 13. JSON String, JSON Object, and JSON Null — Three Different Cases

In our example, a `Price` is represented as a JSON scalar:

~~~json
"USD:12.50"
~~~

not:

~~~json
{"currency":"USD","amount":12.50}
~~~

and not:

~~~json
null
~~~

This decision affects:

- All API requests/responses containing `Price` that share the same mapper/module.
- OpenAPI contracts and generated client schemas.
- Non-Java clients such as JavaScript/Python/Go.
- Searchability, validation, schema evolution, and versioning.
- Representation of null, invalid values, and backward compatibility.

If a public API previously returned an object and now switches to a string, that is normally a **breaking change**. Do not change a global module without updating API contracts, client tests, versioning, or a migration plan.

### Why Can a JSON String Sometimes Be Poor Design?

A JSON string saves structure, but clients must know a custom grammar. For data with multiple fields or frequent evolution, a JSON object is usually easier to extend and debug. For instance, if `Price` gains `tax`, `currencyScale`, or `roundingPolicy`, it becomes hard to pack into a short string. Choose wire formats based on the contract, not because a custom serializer looks concise.

## 14. Deserialization Errors, HTTP Status, and Error Contracts

The deserializer rejects input when:

- The JSON token is not a string.
- The string does not match the regex in full.
- Currency is not three A-Z letters.
- Amount is negative, lacks two decimal places, or exceeds what the parser accepts.
- The DTO has an incompatible shape.
- The request body is too large or JSON is malformed, even before reaching the custom deserializer.

In WebFlux, invalid decode errors are typically translated by Spring into **400 Bad Request** when reading `@RequestBody`, though the exact outcome depends on the exception, route mapping, controller advice, error handlers, and response commit state. If JSON syntax is invalid, the parser can fail before `JsonDeserializer<Price>`. If `Content-Type` is invalid, the result can be 415 Unsupported Media Type; if `Accept` cannot be satisfied by response formats, it can be 406 Not Acceptable.

**Never return stack traces, classpaths, internal file paths, or raw tokens to clients.** In real APIs, design a consistent error body (such as Problem Details) and log internally with a correlation ID. Avoid logging raw client-submitted `price` strings verbatim if the application extends to sensitive data.

### Do Not Turn Every Error into Null

Dangerous pattern:

~~~java
try {
    return parse(text);
} catch (RuntimeException ex) {
    return null;
}
~~~

For a required field, returning null delays the failure, the service may throw a `NullPointerException`, and the client receives 500 instead of 400. Throw an explicit `JsonMappingException` for JSON data violating the contract.

## 15. Complete Spring Boot WebFlux + Jackson Module Application (Java 17)

A standalone runnable project proving both directions over a REST API.

**Stack and scope:** Java 17; Spring Boot 3.3.13; Reactor Netty from `spring-boot-starter-webflux`; Boot-managed Jackson 2. Do not add `spring-boot-starter-web` so Boot does not default to Spring MVC when both starters are on the classpath.

### 15.1 Structure

~~~text
json-module-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/jsoncodec/
    │   ├── JsonCodecApplication.java
    │   ├── Price.java
    │   ├── PriceJsonSerializer.java
    │   ├── PriceJsonDeserializer.java
    │   ├── PriceJacksonConfiguration.java
    │   ├── Quote.java
    │   └── QuoteController.java
    └── test/java/com/example/jsoncodec/
        └── PriceCodecIntegrationTests.java
~~~

### 15.2 settings.gradle

~~~groovy
rootProject.name = 'json-module-demo'
~~~

### 15.3 build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
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
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`starter-webflux` pulls in the appropriate HTTP/Jackson dependencies for Boot 3.3.x. There is no need to add `com.fasterxml.jackson.core:jackson-databind` with a manually chosen version because Boot manages versions. If the application uses dependency exclusions or another dependency platform, verify `runtimeClasspath`.

### 15.4 JsonCodecApplication.java

~~~java
package com.example.jsoncodec;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JsonCodecApplication {

    public static void main(String[] args) {
        SpringApplication.run(JsonCodecApplication.class, args);
    }
}
~~~

### 15.5 Price.java

~~~java
package com.example.jsoncodec;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Locale;
import java.util.Objects;

public record Price(String currency, BigDecimal amount) {

    public Price {
        Objects.requireNonNull(currency, "currency");
        Objects.requireNonNull(amount, "amount");

        currency = currency.trim().toUpperCase(Locale.ROOT);

        if (!currency.matches("[A-Z]{3}")) {
            throw new IllegalArgumentException(
                    "currency must have three ASCII letters");
        }
        if (amount.signum() < 0) {
            throw new IllegalArgumentException(
                    "amount must not be negative");
        }

        amount = amount.setScale(2, RoundingMode.UNNECESSARY);
    }
}
~~~

### 15.6 PriceJsonSerializer.java

~~~java
package com.example.jsoncodec;

import java.io.IOException;

import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.databind.JsonSerializer;
import com.fasterxml.jackson.databind.SerializerProvider;

public final class PriceJsonSerializer extends JsonSerializer<Price> {

    @Override
    public void serialize(
            Price price,
            JsonGenerator generator,
            SerializerProvider provider) throws IOException {

        generator.writeString(
                price.currency() + ":" +
                price.amount().toPlainString());
    }
}
~~~

### 15.7 PriceJsonDeserializer.java

~~~java
package com.example.jsoncodec;

import java.io.IOException;
import java.math.BigDecimal;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonToken;
import com.fasterxml.jackson.databind.DeserializationContext;
import com.fasterxml.jackson.databind.JsonDeserializer;
import com.fasterxml.jackson.databind.JsonMappingException;
import com.fasterxml.jackson.databind.exc.InvalidFormatException;

public final class PriceJsonDeserializer extends JsonDeserializer<Price> {

    private static final Pattern WIRE =
            Pattern.compile("([A-Z]{3}):([0-9]+\\.[0-9]{2})");

    @Override
    public Price deserialize(
            JsonParser parser,
            DeserializationContext context) throws IOException {

        if (!parser.hasToken(JsonToken.VALUE_STRING)) {
            throw JsonMappingException.from(
                    parser, "Price must be a JSON string");
        }

        String text = parser.getText();
        Matcher matcher = WIRE.matcher(text);

        if (!matcher.matches()) {
            throw InvalidFormatException.from(
                    parser,
                    "Expected price format CUR:12.34",
                    text,
                    Price.class);
        }

        return new Price(
                matcher.group(1),
                new BigDecimal(matcher.group(2)));
    }
}
~~~

### 15.8 PriceJacksonConfiguration.java

~~~java
package com.example.jsoncodec;

import com.fasterxml.jackson.databind.Module;
import com.fasterxml.jackson.databind.module.SimpleModule;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class PriceJacksonConfiguration {

    @Bean
    public Module priceWireModule() {
        SimpleModule module = new SimpleModule("price-wire-v1");
        module.addSerializer(Price.class, new PriceJsonSerializer());
        module.addDeserializer(Price.class, new PriceJsonDeserializer());
        return module;
    }
}
~~~

Register the module **once when the application context is built**, not inside the controller. Do not call `ObjectMapper.registerModule` on every HTTP request.

### 15.9 Quote.java

~~~java
package com.example.jsoncodec;

public record Quote(String sku, Price price) {
}
~~~

This is the Java DTO for returning results. Jackson handles `Quote` as a normal record and, upon encountering the `price` field, uses the `Price` serializer/deserializer from the registered module.

### 15.10 QuoteController.java

~~~java
package com.example.jsoncodec;

import java.math.BigDecimal;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/quotes")
public class QuoteController {

    @GetMapping(
            path = "/{sku}",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<Quote> get(@PathVariable("sku") String sku) {
        return Mono.just(new Quote(
                sku, new Price("USD", new BigDecimal("12.50"))));
    }

    @PostMapping(
            path = "/echo",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<Quote> echo(@RequestBody Mono<Quote> incoming) {
        return incoming;
    }
}
~~~

GET demonstrates the Java → JSON direction. POST `/echo` demonstrates JSON → Java → JSON, because the same `price` field goes through the deserializer on input and the serializer on output. In real applications, use separate request and response DTOs when contracts or validation rules differ.

### 15.11 PriceCodecIntegrationTests.java

~~~java
package com.example.jsoncodec;

import java.math.BigDecimal;
import java.util.Map;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class PriceCodecIntegrationTests {

    @LocalServerPort
    private int port;

    @Autowired
    private ObjectMapper objectMapper;

    private WebTestClient client() {
        return WebTestClient.bindToServer()
                .baseUrl("http://127.0.0.1:" + port)
                .build();
    }

    @Test
    void objectMapperBeanSerializesAndDeserializesPrice()
            throws Exception {

        Price price = new Price(
                "usd", new BigDecimal("12.5"));

        String json = objectMapper.writeValueAsString(price);
        assertThat(json).isEqualTo("\"USD:12.50\"");

        Price decoded = objectMapper.readValue(
                "\"USD:12.50\"", Price.class);
        assertThat(decoded).isEqualTo(
                new Price("USD", new BigDecimal("12.50")));
    }

    @Test
    void httpResponseUsesCustomSerializer() {
        client().get()
                .uri("/api/quotes/book-7")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.sku").isEqualTo("book-7")
                .jsonPath("$.price").isEqualTo("USD:12.50");
    }

    @Test
    void httpRequestUsesCustomDeserializer() {
        client().post()
                .uri("/api/quotes/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of(
                        "sku", "book-8",
                        "price", "EUR:9.50"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.sku").isEqualTo("book-8")
                .jsonPath("$.price").isEqualTo("EUR:9.50");
    }

    @Test
    void invalidPriceFormatReturnsBadRequest() {
        client().post()
                .uri("/api/quotes/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of(
                        "sku", "book-9",
                        "price", "EUR 9.50"))
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void wrongJsonTokenReturnsBadRequest() {
        client().post()
                .uri("/api/quotes/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of(
                        "sku", "book-9",
                        "price", Map.of(
                                "currency", "EUR",
                                "amount", 9.50)))
                .exchange()
                .expectStatus().isBadRequest();
    }
}
~~~

The tests use `RANDOM_PORT` instead of a fixed port to avoid collisions in CI. They verify both the **ObjectMapper bean** and **real HTTP** through Reactor Netty/WebFlux. JSONPath checks field values instead of property ordering in the object. The tests require no database or external services.

For JUnit, the results represent **logical expectations of the sample code**, not a report of a pre-executed run within this document. Run the test command and resolve any real environment issues if present.

## 16. Running the Example and Verifying with cURL

### 16.1 Build and Test

In the `json-module-demo` directory:

~~~bash
gradle clean test
~~~

If the project has the Gradle wrapper:

~~~bash
./gradlew clean test
~~~

With Windows PowerShell:

~~~powershell
.\gradlew.bat clean test
~~~

### 16.2 Start the Server

~~~bash
gradle bootRun
~~~

Under standard default configuration, embedded Reactor Netty listens on port 8080 if unused and not overridden.

### 16.3 GET: Verify the Serializer

~~~bash
curl -i \
  'http://127.0.0.1:8080/api/quotes/book-7'
~~~

Expected HTTP 200 and equivalent body:

~~~json
{"sku":"book-7","price":"USD:12.50"}
~~~

Key takeaway: the `price` field is a **JSON string**, not a JSON object with `currency` and `amount`. That is the effect of `PriceJsonSerializer`.

### 16.4 POST: Verify the Deserializer and Serializer

~~~bash
curl -i -X POST \
  'http://127.0.0.1:8080/api/quotes/echo' \
  -H 'Content-Type: application/json' \
  -d '{"sku":"book-8","price":"EUR:9.50"}'
~~~

Expected HTTP 200 and body:

~~~json
{"sku":"book-8","price":"EUR:9.50"}
~~~

Meaning: `Jackson2JsonDecoder` reads the JSON string for `price` into a `Price` record. The controller returns `Quote`; `Jackson2JsonEncoder` writes `Price` back to a JSON string. Matching output confirms **both directions** follow the same contract.

### 16.5 POST with Malformed Price Format

~~~bash
curl -i -X POST \
  'http://127.0.0.1:8080/api/quotes/echo' \
  -H 'Content-Type: application/json' \
  -d '{"sku":"book-9","price":"EUR 9.50"}'
~~~

Expected HTTP 400 because the custom deserializer rejects a space in place of the colon. Do not assume a specific error body shape, as Spring Boot error handlers and detail visibility settings vary.

### 16.6 POST with a JSON Object Instead of a JSON String

~~~bash
curl -i -X POST \
  'http://127.0.0.1:8080/api/quotes/echo' \
  -H 'Content-Type: application/json' \
  -d '{"sku":"book-9","price":{"currency":"EUR","amount":9.50}}'
~~~

Expected HTTP 400 because the deserializer only accepts `VALUE_STRING`. If you want to support both formats for migrating from a legacy API, implement explicit compatibility and test both; do not silently accept arbitrary shapes without validation.

## 17. JSON Codecs in WebFlux Do Not Mean All HTTP Formats

In Spring WebFlux:

- **HttpMessageReader** selects how to read request bodies based on target type and media type.
- **HttpMessageWriter** selects how to write response bodies.
- **Jackson2JsonDecoder** and **Jackson2JsonEncoder** are used for matching JSON representations.
- **ObjectMapper** decides which Java types map to which JSON tokens.
- **Module** provides serializers/deserializers for specific Java types.

If an endpoint returns `text/plain` or the application uses another XML/CBOR/Protobuf codec, a custom Jackson JSON module will not automatically participate.

### HTTP Content-Type and Accept

A POST expecting the Jackson JSON decoder to run must generally send `Content-Type: application/json` matching the route contract. With the wrong `Content-Type`, you can receive 415 Unsupported Media Type **before** `PriceJsonDeserializer` is ever called.

With `Accept: application/xml` when the endpoint only declares `produces=application/json`, you can receive 406 Not Acceptable. Do not debug your custom serializer when the request is rejected at the content negotiation layer.

## 18. When Explicit WebFlux Codec Customization Is Needed

With default Boot auto-configuration, registering a `Module` bean is usually enough. Only look into `CodecCustomizer` / `WebFluxConfigurer` and `ServerCodecConfigurer` when the HTTP layer needs a different mapper or custom media types.

### 18.1 Adjusting Buffering Limits

Example:

~~~properties
spring.codec.max-in-memory-size=256KB
~~~

Or in code:

~~~java
@Configuration
class WebFluxCodecs implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {
        configurer.defaultCodecs().maxInMemorySize(256 * 1024);
    }
}
~~~

This is an illustrative snippet: it requires imports `org.springframework.context.annotation.Configuration`, `org.springframework.web.reactive.config.WebFluxConfigurer`, and `org.springframework.http.codec.ServerCodecConfigurer`.

`maxInMemorySize` limits in-memory buffering for certain codecs, **not the total byte limit for all streaming bodies**. If a JSON payload requires parsing a huge object, `DataBufferLimitException` or related codec errors can occur. When using JSON streaming/NDJSON, buffering semantics differ, so test with realistic inputs.

### 18.2 Binding a Specific Mapper to Jackson2JsonEncoder/Decoder

Spring Boot 3.3 and Spring Framework 6.1 provide the `CodecCustomizer` hook. The illustrative snippet below should only be used when you **intentionally** require a specific `ObjectMapper` on WebFlux JSON HTTP codecs:

~~~java
@Bean
CodecCustomizer customJsonCodecs(ObjectMapper objectMapper) {
    return configurer -> {
        configurer.defaultCodecs().jackson2JsonEncoder(
                new Jackson2JsonEncoder(objectMapper));
        configurer.defaultCodecs().jackson2JsonDecoder(
                new Jackson2JsonDecoder(objectMapper));
    };
}
~~~

Required imports:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.boot.web.codec.CodecCustomizer;
import org.springframework.http.codec.json.Jackson2JsonEncoder;
import org.springframework.http.codec.json.Jackson2JsonDecoder;
import org.springframework.context.annotation.Bean;
~~~

**Do not add this snippet to the sample project if the module already works.** Replacing the decoder/encoder can drop other Boot codec settings unless you consistently preserve configuration (memory size, logging, streaming behavior, and codec customizations). When customizing codecs, test real HTTP in both directions and error cases.

### 18.3 JSON Streaming and NDJSON

Jackson encoders/decoders can process JSON streams according to configuration and supported media types, such as `application/x-ndjson` in certain cases. A `Flux<Quote>` can cause the `Price` serializer to be called per element. However:

- Do not assume chunking behavior solely from the number of `Flux` elements.
- A JSON array and NDJSON are **two different wire formats**.
- Backpressure does not guarantee handling infinite payloads without resource limits.
- Custom serializers must remain stateless and non-blocking.
- Test content negotiation, cancellation, memory limits, and errors after response commit.

A module controls the JSON representation of **a type**; it does not decide transport chunk boundaries or when responses are committed.

## 19. Jackson Modules in Spring MVC

If the same `Price` type is used in a Spring MVC application with `spring-boot-starter-web`, Jackson typically lives inside **MappingJackson2HttpMessageConverter** and the Boot-managed `ObjectMapper`.

Registering `@Bean Module` as in section 8 remains the right choice when Boot auto-configures Jackson. The difference is:

~~~text
Spring MVC:
  @RequestBody -> HttpMessageConverter (Jackson)
  @ResponseBody -> HttpMessageConverter (Jackson)

Spring WebFlux:
  @RequestBody -> HttpMessageReader / Jackson2JsonDecoder
  return body  -> HttpMessageWriter / Jackson2JsonEncoder
~~~

Do not confuse the two extension APIs. Do not call `WebMvcConfigurer.configureMessageConverters` in a WebFlux-only application expecting to change WebFlux Jackson codecs. Conversely, `WebFluxConfigurer.configureHttpMessageCodecs` does not configure Servlet MVC converters.

**Testing:** MVC uses `MockMvc` in many cases; WebFlux uses `WebTestClient`. In both, testing HTTP response bodies and invalid JSON requests verifies that the module reaches the right mapper.

## 20. Module Scope, Serializer Scope, and KeyDeserializer

The custom module in the example registers a serializer/deserializer **for values of type Price**. If you have:

~~~java
Map<Price, String> data
~~~

then `Price` appears as a **JSON object key**, not a value. JSON object keys are strings, and Jackson uses dedicated key serializers/deserializers. `JsonSerializer<Price>` for object values is not sufficient to ensure `Map<Price, String>` works per the expected contract.

Jackson `SimpleModule` provides related APIs:

~~~java
module.addKeySerializer(Price.class, ...);
module.addKeyDeserializer(Price.class, ...);
~~~

The `"..."` here is an **illustrative API placeholder, not compilable Java code**. If you have no `Map` key use case, do not register key serializers. If you do, design escaping, formatting, and object key uniqueness clearly—especially if two distinct `Price` values could produce the same key text.

Container types you may encounter:

- `List<Price>`: the module uses the value serializer/deserializer for each element.
- `Quote` containing `Price`: the module is used for the `price` field.
- `Optional<Price>`: depends on Jackson JDK8 module configuration and the API contract.
- `Map<String, Price>`: the module handles values.
- `Map<Price, String>`: requires key handling; does not automatically reuse the value serializer.
- Generic `wrapper<T>`: requires checking type information, Jackson `JavaType`, and generic binding.

## 21. Jackson Null, Absent, Default, and Unknown Properties

JSON has multiple states:

~~~json
{}
~~~

~~~json
{"price":null}
~~~

~~~json
{"price":"USD:0.00"}
~~~

They are **not equivalent**:

- Missing `price`: the DTO may receive null, default, or fail depending on creator/validation/Jackson setup.
- Explicit null: null-handling can bypass the deserializer for `Price`.
- Valid `Price` `0.00`: a complete `Price` object.

If `price` is required, design explicit request DTOs and validation. With Spring Boot 3.3 and Jakarta Bean Validation, add `spring-boot-starter-validation` when a provider is needed, and test `@Valid`/constraints on the actual stack.

### Unknown Fields

Jackson in Spring Boot 3.3 defaults differ from a plain `new ObjectMapper()`—for example, `FAIL_ON_UNKNOWN_PROPERTIES` is normally disabled on the Boot-configured builder mapper. If you want to reject unknown JSON fields, decide on an explicit policy and test against the API contract.

Do not treat the absence of failure on extra fields as proof that the `Price` deserializer is wrong: unknown property handling occurs at the DTO level before or outside the custom value deserializer.

## 22. Thread Safety, Performance, and Security

### 22.1 Configure Modules at Startup

`ObjectMapper` is typically used concurrently across many requests. Per Jackson guidance, it is safe to share when all configuration is completed **before** the first read/write. Do not swap modules/serializers on a singleton mapper while serving concurrent requests and assume caches update safely.

### 22.2 Keep Serializers/Deserializers Stateless

Do not store request-specific data in instance fields for subsequent requests. Use local variables inside `serialize`/`deserialize`. Static immutable `Pattern` instances as in the example are safe to share.

### 22.3 Do Not Block the Reactive Event Loop

In Spring WebFlux, JSON decoding/encoding can run on reactive pipelines tied to event-loop threads. Avoid database lookups, HTTP calls, `Thread.sleep`, or blocking file I/O inside `JsonSerializer`/`JsonDeserializer`. This is not the place to validate user permissions via a synchronous repository.

### 22.4 Do Not Enable Polymorphic Default Typing Carelessly

Do not use `ObjectMapper.activateDefaultTyping` with untrusted client data without understanding subtype validators and security implications. Broad polymorphic deserialization introduces severe risks by allowing Jackson to instantiate unexpected classes. For REST APIs, prefer strongly typed DTOs and allowlist polymorphic subtypes when needed.

### 22.5 Limit JSON Size and Complexity

A JSON document can be overly large, deeply nested, or contain huge strings/numbers. In production:

- Set appropriate request body limits at gateway/server/codec layers.
- Test WebFlux `max-in-memory-size` when decoders aggregate bodies.
- Use Jackson `StreamReadConstraints` when version/requirements warrant it.
- Avoid complex regex backtracking on unbounded strings.
- Avoid recursive serialization on cyclic object graphs without an explicit policy.
- Never log raw payloads containing tokens, user info, or sensitive content.
- Design reasonable timeouts, cancellation, and error responses.

### 22.6 BigDecimal for Decimal Values

Construct from `BigDecimal(String)` rather than `BigDecimal(double)` to avoid floating-point errors when representing money. Never convert currency to `double` just to make a serializer easier to write. At the same time, do not treat the two-decimal example as a universal rule for every real-world currency.

## 23. How Standalone Serializer/Deserializer Tests Differ from HTTP Tests

| Test Level | What It Verifies | What It Cannot Prove Alone |
| --- | --- | --- |
| Unit test with a test-created `ObjectMapper` + module | Serialization/deserialization logic works | Boot auto-registration |
| Test with `@Autowired ObjectMapper` in Spring context | Module is attached to Boot-created mapper | That WebFlux HTTP codecs definitely use the same mapper if custom codecs exist |
| `WebTestClient` `bindToServer` + `RANDOM_PORT` | Real HTTP request/response through embedded server and codecs | That production proxies or client environments match local |
| `MockMvc` in MVC | Servlet handler + message converter with mock requests | That a real TCP socket is open |
| Contract/integration tests between services | Client/server wire format compatibility | Business correctness outside the contract |

The sample project uses both **ObjectMapper bean + WebTestClient HTTP**. This provides strong protection when upgrading Boot/Jackson versions or changing codec registration.

### Tests to Add for Real Projects

- Null input, missing property, and empty string.
- Invalid currency, lowercase letters, negative amount, too many decimal digits.
- JSON number/object/array instead of string.
- JSON body size constraints.
- Locale independence (e.g., ensuring locale `tr_TR` does not alter wire currency formatting).
- Round-trip serialization/deserialization inside nested DTOs.
- Behavior when proxy/client sends inappropriate `Content-Type` or `Accept`.
- Backward compatibility tests if the API previously used a JSON object.
- Concurrency/thread-safety tests if custom logic is complex.
- OpenAPI/schema contract tests verifying clients receive JSON type `string`.

## 24. Common Mistakes and Fixes

### Mistake 1: Registering the Module on a Different Mapper from HTTP Codecs

Symptom: a test with `new ObjectMapper().registerModule(...)` PASSES, but the WebFlux endpoint still returns a JSON object instead of a string.

Fix: use `@Bean Module` via Boot configuration, inspect the injected `ObjectMapper`, verify whether custom codecs use a separate mapper, and test over real HTTP.

### Mistake 2: Registering Only a Serializer and Forgetting the Deserializer

Symptom: GET returns `"USD:12.50"`, but POST on the same field fails or Jackson tries to construct `Price` from a string using an unsuitable default deserializer.

Fix: `addDeserializer(Price.class, ...)` and test POST, not just GET.

### Mistake 3: Forgetting @Bean or Placing the Class Outside Component Scan

Symptom: `PriceJacksonConfiguration` exists in source, yet Spring never registers the `Module` bean.

Fix: verify `@Configuration`, `@Bean`, and that the package is under `@SpringBootApplication`'s package (or declare `@Import` appropriately).

### Mistake 4: Creating a New ObjectMapper in Controllers

Symptom: HTTP converters and service `ObjectMapper` produce different results, or Java Time modules are missing.

Fix: use the Boot-managed mapper or a consistently configured builder; never call `new ObjectMapper()` per request.

### Mistake 5: Using @EnableWebFlux to "Turn On" a Serializer

Symptom: alters auto-configuration or endpoint behavior unexpectedly.

Fix: remove `@EnableWebFlux` when you only need to add a `Module` bean in Spring Boot.

### Mistake 6: Using JsonSerializer for Object Keys

Symptom: `Map<Price, String>` does not serialize as expected.

Fix: look into `KeySerializer`/`KeyDeserializer`; do not confuse value serializers with key serializers.

### Mistake 7: Parsing Numbers Through double

Symptom: monetary values lose precision or produce decimal strings violating the contract.

Fix: build `BigDecimal` from `String` and use `toPlainString` per documented scale/rounding policy.

### Mistake 8: Catching Every Error and Returning Null

Symptom: invalid JSON turns into incomplete objects, causing the controller to return 500 or misbehave in business logic.

Fix: throw semantically accurate `JsonMappingException`/`InvalidFormatException`; validate required fields at the DTO/service layer.

### Mistake 9: Reading JSON Bodies with an Incompatible Content-Type

Symptom: POST returns 415 before reaching the deserializer.

Fix: verify `consumes`/`Content-Type`, JSON body syntax, and HTTP codec selection.

### Mistake 10: Not Testing Nested DTO Types

Symptom: serializing `Price` directly produces a string, yet nested `Quote.price` behaves differently due to annotations, mappers, or custom configuration.

Fix: test both direct `Price` and nested `Quote` through actual HTTP endpoints.

### Mistake 11: Assuming a Custom Serializer Also Validates Null

Symptom: `price:null` is still accepted.

Fix: design a null policy and `@NotNull`/DTO validation or custom `NullValue` handling when genuinely needed.

### Mistake 12: Changing the Global Mapper When Only One Field Needs Customizing

Symptom: unrelated APIs change wire formats.

Fix: consider property-level `@JsonSerialize`/`@JsonDeserialize` or a clearly scoped DTO-specific mapper/module.

### Mistake 13: Applying Jackson 2 Examples to Spring Boot 4/Jackson 3

Symptom: packages/classes/APIs do not match current dependencies.

Fix: verify the exact major version, `JsonMapper`/Jackson 3 APIs, and corresponding Spring Framework/Boot docs before porting code.

## 25. Production Implementation Checklist

1. Identify the existing JSON contract and backward compatibility requirements.
2. Evaluate default Jackson annotations/configs before writing a new serializer.
3. Target the exact Java type to customize; avoid matching `Object.class`.
4. Finalize the wire format and rules for invalid/null values.
5. Write serializers using `JsonGenerator`, avoiding raw string concatenation for JSON tokens.
6. Write deserializers that check tokens, validate formats, and throw clear exceptions.
7. Use `BigDecimal`/Java Time according to business meaning; avoid casual conversions to `double`/`String`.
8. Package both directions in `SimpleModule`.
9. Register the `Module` bean in a package covered by Spring Boot component scanning.
10. Avoid replacing `ObjectMapper`/HTTP codecs when Boot's default configuration suffices.
11. Write `@Autowired ObjectMapper` tests for both read and write directions.
12. Write HTTP integration tests with `WebTestClient`/`MockMvc`.
13. Test malformed JSON, wrong tokens, null, missing fields, and `Content-Type`/`Accept`.
14. Keep serializers/deserializers stateless and non-blocking.
15. Configure body size, codec memory, and parser depth limits per use case.
16. Protect sensitive data; never log raw request bodies indiscriminately.
17. Document JSON field types and contract samples in OpenAPI.
18. Verify JSON behavior after upgrading Boot/Jackson modules.
19. In WebFlux, distinguish codec configuration from MVC message converters.
20. Monitor error rates, throughput, and latency after deploying custom serialization.

## 26. Summary

**JsonSerializer** handles the Java → JSON direction; **JsonDeserializer** handles JSON → Java; **SimpleModule** packages both directions for registration into Jackson's **ObjectMapper**. In Spring Boot 3.3, the convenient integration approach is declaring a **@Bean Module** and letting Jackson auto-configuration apply it to the framework-managed mapper.

In WebFlux, body reading/writing continues to be managed by **Jackson2JsonEncoder / Jackson2JsonDecoder** and HTTP message codecs. A custom module changes the representation of a Java type; it does not alter the HTTP protocol or handle media types on its own. The most reliable verification is testing both the **ObjectMapper bean** and **HTTP POST/GET against the server**, especially when the application defines custom codecs.

The `Price` exercise with JSON string `"USD:12.50"` demonstrates how a module can represent a domain type consistently across requests and responses. However, any global change must be managed like an API contract change: clarify null policies, validation, error statuses, backward compatibility, and client expectations before rollout.

## 27. References

- Spring Boot 3.3 — JSON and @JsonComponent: https://docs.spring.io/spring-boot/3.3/reference/features/json.html
- Spring Boot 3.3 — Spring MVC and Jackson configuration: https://docs.spring.io/spring-boot/3.3/how-to/spring-mvc.html
- Spring Boot 3.3 — Reactive Web Applications / HTTP Codecs: https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html
- Spring Framework 6.1 — WebFlux Configuration: https://docs.spring.io/spring-framework/reference/6.1/web/webflux/config.html
- Jackson 2 — Module API: https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/2.17.2/com/fasterxml/jackson/databind/Module.html
- Jackson 2 — SimpleModule API: https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/2.17.2/com/fasterxml/jackson/databind/module/SimpleModule.html
- Jackson 2 — JsonSerializer / JsonDeserializer: https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/2.17.2/index.html
- Jackson databind — Introduction and usage: https://github.com/FasterXML/jackson-databind
