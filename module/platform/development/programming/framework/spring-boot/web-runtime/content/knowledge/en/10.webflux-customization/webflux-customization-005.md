# Customizing Formatters, Argument Resolvers, and Response Content in Spring WebFlux

## 1. Learning Objectives and Three Layers to Distinguish

Spring WebFlux provides extension points for turning an HTTP request into a Java method invocation and turning a Java result into an HTTP response. Three seemingly similar needs must be solved at **three different layers**:

1. **Formatter / Converter**: converts a **value** between a String and a Java type—for example, path variable `"ord-0042"` into `OrderCode("ORD-0042")`, or formatting dates/times according to rules. The typical hook is `WebFluxConfigurer.addFormatters(FormatterRegistry)`.
2. **HandlerMethodArgumentResolver**: supplies an **entire argument** for a controller method—for example, `@TenantHeader TenantContext` built from the `X-Tenant` header. The typical hook is `WebFluxConfigurer.configureArgumentResolvers(ArgumentResolverConfigurer)`.
3. **Response content**: decides the HTTP status, headers, Content-Type, and how the body is serialized/streamed. Depending on the need, use `ResponseEntity`, `@ResponseStatus`, `ServerResponse`, Jackson annotations/`ObjectMapper`, `HttpMessageWriter`/codecs, `WebFilter.beforeCommit`, or a specialized `HandlerResultHandler`.

Do not default to writing a custom `HandlerAdapter` or replacing `DispatcherHandler` for these requirements. In most applications, `WebFluxConfigurer` and the built-in extension points are sufficient.

This lesson applies to **Spring Boot 3.3.x, Spring Framework 6.1.x, and Java 17+**, focusing on **Spring WebFlux**. Spring MVC has many similar annotations, but its configuration method names and argument resolver interfaces differ; do not take an MVC example and mechanically swap imports to WebFlux.

After this lesson, you will be able to register a custom Formatter, build a custom reactive `HandlerMethodArgumentResolver`, control JSON bodies and response headers, write a standalone runnable application, and test both success and error cases.

## 2. First Requirement: The Application Actually Runs Spring WebFlux

Common Gradle dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

Spring Boot normally uses Reactor Netty as the embedded server when only `starter-webflux` is added. If both `spring-boot-starter-web` and `spring-boot-starter-webflux` are present, Boot **defaults to Servlet/Spring MVC**. In that case, `WebFluxConfigurer` will not configure the server controllers you expect.

In a project using only `starter-webflux`, you do not need to force the application type. If both starters must be present and you genuinely want a reactive server, declare:

~~~properties
spring.main.web-application-type=reactive
~~~

This setting selects the reactive web application type; it does not make JDBC, `Thread.sleep`, or synchronous libraries non-blocking.

Summary of the processing flow:

~~~mermaid
flowchart TD
    A["HTTP request / Reactor Netty"] --> B["HttpHandler and WebFilter chain"]
    B --> C["DispatcherHandler"]
    C --> D["HandlerMapping selects HandlerMethod"]
    D --> E["RequestMappingHandlerAdapter (WebFlux)"]
    E --> F["Argument resolution"]
    F --> G["FormattingConversionService"]
    F --> H["Custom HandlerMethodArgumentResolver"]
    G --> I["Invoke controller method"]
    H --> I
    I --> J["HandlerResultHandler"]
    J --> K["HttpMessageWriter / Jackson codec"]
    K --> L["ServerHttpResponse"]
    L --> M["HTTP status + headers + body"]
~~~

Not every request passes through every branch. `HandlerMapping` might find no route; a `WebFilter` might short-circuit; a custom resolver might return `Mono.error`; the controller might return `ResponseEntity`, `ServerResponse`, or a stream; error handling might write the response before the normal result handler runs.

### Three Keywords to Remember

- **Parse/print**: formatters and conversion service.
- **Create method argument**: argument resolver.
- **Write response representation**: result handler and HTTP message codecs.

## 3. Extension Point Selection Table

| Need | Suitable extension point | Avoid choosing first |
| --- | --- | --- |
| Convert a path/query String into a typed identifier | Formatter or Converter | Reading HttpServletRequest or custom HandlerAdapter |
| Parse a Locale-aware date in a request parameter | Formatter/FormatterRegistrar | Jackson serializer |
| Create a controller parameter from app-defined headers/metadata | Reactive HandlerMethodArgumentResolver | Custom body codec |
| Map a JSON request body to a DTO | @RequestBody + HttpMessageReader/Jackson | Formatter |
| Validate an input DTO | Jakarta Validation + @Valid, validation framework | WebFilter manually parsing JSON |
| Set status and headers on a single endpoint | ResponseEntity/ResponseStatusException | Replacing DispatcherHandler |
| Change field names of a JSON DTO | @JsonProperty / @JsonFormat or Jackson config | Formatter |
| Configure body aggregation limits or readers/writers | ServerCodecConfigurer | Custom argument resolver |
| Add a response header across many endpoints | WebFilter or appropriate response-handling tool | Custom serializer |
| Standardize response structure per contract | DTO, mapper, ResponseEntity, Jackson | Regex string replacement on JSON after serialization |
| Support an entirely new media type | HttpMessageReader/HttpMessageWriter, Encoder/Decoder | Formatter for a path variable type |
| Support an entirely new return-type contract | HandlerResultHandler with careful ordering | Workaround modifying every controller |

Each extension point should carry **the smallest responsibility needed**. That makes maintenance and testing much cleaner.

## 4. How Do Formatter, Converter, and ConversionService Differ?

### 4.1 Converter<S,T>

`org.springframework.core.convert.converter.Converter<S,T>` converts a source Java type `S` to `T`. For example, `Converter<String, OrderCode>` fits when neither `Locale` nor reverse printing is needed.

~~~java
public final class OrderCodeConverter
        implements Converter<String, OrderCode> {

    @Override
    public OrderCode convert(String source) {
        return new OrderCode(source.trim().toUpperCase(Locale.ROOT));
    }
}
~~~

This is an **abbreviated class illustration**: it needs imports and should validate the format of `source`. A Converter is usually sufficient for IDs, special enum mappings, or one-way value-object conversions.

### 4.2 Formatter<T>

`org.springframework.format.Formatter<T>` combines **Printer<T>** and **Parser<T>** with the signatures:

~~~java
String print(T object, Locale locale);
T parse(String text, Locale locale) throws ParseException;
~~~

Here `Locale` enables locale-specific formatting and parsing. Formatter fits values such as currency amounts, percentages, dates, or domain types with textual representations.

For an order code with a fixed format, we can still use `Formatter` to see the full parse/print mechanism. When a code does not depend on `Locale`, `Converter` can be simpler.

### 4.3 FormattingConversionService

Spring Framework wires `Formatter`s, `Converter`s, and standard mechanisms into `FormattingConversionService`. WebFlux configures this service for annotated controller argument binding.

Example method:

~~~java
@GetMapping("/orders/{code}")
public Mono<OrderView> find(@PathVariable OrderCode code) {
    // ...
}
~~~

When the URL contains `/orders/ord-0042`, the framework must convert the raw path variable String into an `OrderCode`. A registered Formatter can perform that conversion before the controller is called.

**Important limitation:** Formatter does **not** automatically change how Jackson serializes a JSON DTO. Jackson uses its own serializers/annotations/configuration. A `ResponseEntity<OrderView>` returning JSON does not pass through `Formatter<OrderCode>` merely because the DTO holds an `OrderCode`.

## 5. Writing a Formatter for an Order Code

Assume the business format is `ORD-0001`, `ORD-0042`, `ORD-9999`. We accept lowercase input and normalize it to uppercase.

~~~java
package com.example.customwebflux;

public record OrderCode(String value) {
}
~~~

An `OrderCode.java` file containing the public record above compiles on Java 17+.

File `OrderCodeFormatter.java`:

~~~java
package com.example.customwebflux;

import java.text.ParseException;
import java.util.Locale;

import org.springframework.format.Formatter;

public final class OrderCodeFormatter implements Formatter<OrderCode> {

    @Override
    public OrderCode parse(String text, Locale locale)
            throws ParseException {

        if (text == null) {
            throw new ParseException("Order code is required", 0);
        }

        String normalized = text.trim().toUpperCase(Locale.ROOT);

        if (!normalized.matches("ORD-[0-9]{4}")) {
            throw new ParseException(
                    "Expected order code such as ORD-0042", 0);
        }

        return new OrderCode(normalized);
    }

    @Override
    public String print(OrderCode object, Locale locale) {
        return object.value();
    }
}
~~~

Explanation:

1. `parse` receives the String from an HTTP request parameter or path variable.
2. `Locale.ROOT` is used for uppercasing because the code format is locale-invariant; using `Locale.getDefault()` can lead to unexpected behavior in certain locales.
3. The regex requires `ORD-` followed by exactly four digits.
4. `ParseException` signals malformed input; Spring WebFlux can turn binding/conversion errors into `400 Bad Request` via its default pipeline.
5. `print` returns the textual representation of the object. In other flows, Spring's formatting system can use it to convert the Java type to a String; JSON bodies still follow codecs/serializers.

Do not assume `parse` only ever runs on the event loop or only once per request type. It must be small, side-effect-free, and thread-safe. Never perform database or network calls inside a formatter.

### Where Should You NOT Use a Formatter?

- Reading HTTP headers + cookies + tokens to construct `TenantContext`: that is the job of an argument resolver.
- Deserializing a JSON request body into an `OrderCreateRequest` record: that is the job of a message reader.
- Renaming a JSON field from `orderCode` to `order_code`: that is the job of Jackson serialization.
- Injecting an `X-Trace` header into every response: that is a response/filter concern.

## 6. Registering a Formatter with WebFluxConfigurer

Spring WebFlux provides the interface:

~~~java
org.springframework.web.reactive.config.WebFluxConfigurer
~~~

To register a formatter, override:

~~~java
@Override
public void addFormatters(FormatterRegistry registry) {
    registry.addFormatter(new OrderCodeFormatter());
}
~~~

This snippet goes inside a `@Configuration implements WebFluxConfigurer` class; **it is not a standalone Java file**.

Spring Boot normally auto-configures WebFlux. When you want to add a formatter, use:

~~~java
@Configuration
public class WebConfig implements WebFluxConfigurer {
    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addFormatter(new OrderCodeFormatter());
    }
}
~~~

This snippet illustrates class structure and requires imports. Complete code is provided in section 15.

**Do not add `@EnableWebFlux` just to register a formatter.** In Spring Boot, `@EnableWebFlux` shifts framework configuration control to the application and can cause some of Boot's WebFlux auto-configuration to stop applying as before. For small customizations, `@Configuration + implements WebFluxConfigurer` is the standard choice.

### Built-in Format Types

Spring supports built-in conversions/formatters for enums, numbers, date/time types, and annotations like `@DateTimeFormat`. Write a custom formatter only when the input contract is truly custom.

Example:

~~~java
@GetMapping("/report")
public Mono<String> report(
        @RequestParam @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
        LocalDate date) {
    return Mono.just(date.toString());
}
~~~

This snippet requires importing `LocalDate`, `DateTimeFormat`, and the matching WebFlux annotations. If ISO format already satisfies your needs, you do not need a custom `Formatter<LocalDate>`.

## 7. When Must You Use HandlerMethodArgumentResolver?

A controller method sometimes needs an argument that **does not map directly from a single String value**. For instance, every internal endpoint might want to accept:

~~~java
@TenantHeader TenantContext tenant
~~~

where `tenant` is determined from the `X-Tenant-Id` header. Repeating `@RequestHeader` and parsing/validating it across hundreds of endpoints is verbose and error-prone. A custom resolver can:

- Recognize parameters annotated with `@TenantHeader` and typed as `TenantContext`.
- Read the header from `ServerWebExchange`.
- Validate presence and format.
- Return a `Mono` containing `TenantContext`.
- Emit a reactive error if the input is invalid.

This is a fit for **`org.springframework.web.reactive.result.method.HandlerMethodArgumentResolver`**, not the similarly named Spring MVC interface.

### Key WebFlux API

~~~java
boolean supportsParameter(MethodParameter parameter);

Mono<Object> resolveArgument(
        MethodParameter parameter,
        BindingContext bindingContext,
        ServerWebExchange exchange);
~~~

In WebFlux, `resolveArgument` returns **`Mono<Object>`**. Spring MVC Servlet uses a different argument resolver API that typically returns `Object` directly from `NativeWebRequest`/`WebDataBinderFactory`. Do not copy MVC interfaces into reactive packages.

### Why Return Mono<Object>?

An argument resolver may need to fetch data from a reactive request context that is not immediately available. Returning a publisher lets the framework compose the resolution of multiple arguments without blocking threads. In a simple header case, `Mono.just` or `Mono.defer` is enough. For asynchronous I/O sources, stay fully reactive; never call `.block()` to "turn a Mono into an Object."

## 8. Building the Annotation and TenantContext Type

File `TenantHeader.java`:

~~~java
package com.example.customwebflux;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.PARAMETER)
@Retention(RetentionPolicy.RUNTIME)
public @interface TenantHeader {
}
~~~

Meaning:

- `@Target(PARAMETER)` restricts the annotation to method parameters.
- `@Retention(RUNTIME)` lets `HandlerMethodArgumentResolver` inspect the annotation at runtime.
- Do not assume declaring an annotation handles authentication or authorization; annotations are only metadata.

File `TenantContext.java`:

~~~java
package com.example.customwebflux;

public record TenantContext(String id) {
}
~~~

An immutable record suits request-scoped data. Tenant identity should be resolved **after** the security layer authenticates the header's source if a multi-tenant application requires strict trust boundaries. This example demonstrates only the resolver mechanism and **does not imply a header-supplied tenant is an authenticated identity**.

## 9. Building a Custom Reactive Argument Resolver

File `TenantHeaderResolver.java`:

~~~java
package com.example.customwebflux;

import java.util.Locale;

import org.springframework.core.MethodParameter;
import org.springframework.http.HttpStatus;
import org.springframework.web.reactive.BindingContext;
import org.springframework.web.reactive.result.method.HandlerMethodArgumentResolver;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

public final class TenantHeaderResolver
        implements HandlerMethodArgumentResolver {

    @Override
    public boolean supportsParameter(MethodParameter parameter) {
        return parameter.hasParameterAnnotation(TenantHeader.class)
                && parameter.getParameterType().equals(TenantContext.class);
    }

    @Override
    public Mono<Object> resolveArgument(
            MethodParameter parameter,
            BindingContext bindingContext,
            ServerWebExchange exchange) {

        return Mono.defer(() -> {
            String header = exchange.getRequest().getHeaders()
                    .getFirst("X-Tenant-Id");

            if (header == null || header.isBlank()) {
                return Mono.error(new ResponseStatusException(
                        HttpStatus.BAD_REQUEST,
                        "X-Tenant-Id is required"));
            }

            String tenantId = header.trim().toLowerCase(Locale.ROOT);

            if (!tenantId.matches("[a-z0-9-]{1,24}")) {
                return Mono.error(new ResponseStatusException(
                        HttpStatus.BAD_REQUEST,
                        "Invalid X-Tenant-Id"));
            }

            return Mono.just((Object) new TenantContext(tenantId));
        });
    }
}
~~~

This is a standalone class with complete imports for Spring WebFlux/Spring Boot 3.3 and Reactor. It does not read the body and does not call `subscribe()`.

Key points to understand:

1. `supportsParameter` checks **both the annotation and the type**; matching by parameter name alone could unintentionally capture unrelated methods.
2. `Mono.defer` ensures header reading and validation execute when the framework subscribes. For simple headers, `Mono.just` could also work; `Mono.defer` keeps lazy semantics clear.
3. `Mono.error` turns parameter errors into a reactive error signal; `ResponseStatusException` can lead to HTTP 400 via WebFlux's default error handler.
4. The example validates format only; **never trust a tenant header from a public client without authentication, authorization, and tenant access checks**.
5. Argument resolvers should avoid blocking lookups. If tenant verification against a database is required, prefer a reactive repository or perform it in the service/security layer per your architecture.
6. A new `TenantContext` instance is created for each resolution; never store the current request's tenant in a mutable singleton field.

### Registering the Resolver

The right hook in Spring WebFlux:

~~~java
@Override
public void configureArgumentResolvers(
        ArgumentResolverConfigurer configurer) {
    configurer.addCustomResolver(new TenantHeaderResolver());
}
~~~

`ArgumentResolverConfigurer` resides in package:

~~~text
org.springframework.web.reactive.result.method.annotation.ArgumentResolverConfigurer
~~~

Do not confuse it with `WebMvcConfigurer.addArgumentResolvers(List<HandlerMethodArgumentResolver>)` in Spring MVC. In WebFlux, **`WebFluxConfigurer.configureArgumentResolvers`** is the configuration method.

Custom resolvers plug into WebFlux's annotated controller handling infrastructure. Do not rely on this custom resolver to automatically resolve parameters of functional `HandlerFunction<ServerResponse>` endpoints: functional routing has its own `ServerRequest`, headers, attributes, and filter APIs.

## 10. Resolver Ordering and Tricky Cases

`RequestMappingHandlerAdapter` in Spring WebFlux uses framework-built argument resolvers to support `@PathVariable`, `@RequestParam`, `@RequestBody`, `ServerWebExchange`, `Model`, validation, and many built-in types.

A custom resolver is not necessarily the **first resolver** consulted for every parameter. Therefore:

- Pick a distinct annotation and Java type to avoid colliding with built-in resolvers.
- Do not try to override `@RequestBody` or `@RequestParam` with a resolver whose `supportsParameter` is overly broad.
- If a built-in resolver claims the parameter first, your custom resolver may never run.
- When upgrading Spring versions, re-check resolver order, new built-in resolvers, and tests.
- If no resolver supports a parameter, the controller will not be invoked and the framework raises an argument resolution error.

Do not expect a custom resolver to directly invoke arbitrary controller beans. Its job is supplying **one parameter value**, while `RequestMappingHandlerAdapter` coordinates handler invocation.

### A Simpler Alternative

If you only need a raw string from a header with no shared logic:

~~~java
@GetMapping("/who")
public Mono<String> who(
        @RequestHeader("X-Tenant-Id") String tenantId) {
    return Mono.just(tenantId);
}
~~~

The built-in approach is enough. Custom resolvers shine when you need a clear abstraction, reusable validation/normalization, and independent testability.

## 11. How Is WebFlux Response Content Produced?

Spring WebFlux separates a controller **returning a value** from the framework **writing bytes** to the client.

Example annotated controller:

~~~java
@GetMapping("/status")
public Mono<ResponseEntity<StatusView>> status() {
    return Mono.just(ResponseEntity.ok(
            new StatusView("READY", "reactive")));
}
~~~

Typical steps:

1. `DispatcherHandler` locates the `HandlerMethod`.
2. WebFlux `RequestMappingHandlerAdapter` resolves arguments and invokes the controller.
3. The controller returns `Mono<ResponseEntity<StatusView>>`.
4. `ReactiveAdapterRegistry` and result handling adapt reactive return types.
5. `HandlerResultHandler` (for example, `ResponseEntityResultHandler`) applies status/headers and passes the body to an `HttpMessageWriter`.
6. The encoder/codec (typically Jackson for JSON) converts `StatusView` into response bytes; `ServerHttpResponse` writes the data.
7. The `Mono<Void>` at the HTTP handler layer completes when response processing finishes.

The snippet illustrates a method; `StatusView` must be defined in the application to compile.

### Independent Dimensions

- **HTTP status**: 200, 201, 204, 400, 404...
- **HTTP headers**: `Location`, `Cache-Control`, `ETag`, `X-Request-Id`, `Content-Type`...
- **Media type**: `application/json`, `text/plain`, `application/problem+json`...
- **Representation body**: JSON DTO, String, DataBuffer, Server-Sent Events...
- **Errors**: `@ExceptionHandler`, `ResponseStatusException`, `WebExceptionHandler`...
- **Timing/streaming**: `Mono`, `Flux`, cancellation, response commit.

Changing one dimension does not automatically change the others.

## 12. ResponseEntity, @ResponseStatus, and Functional ServerResponse

### 12.1 ResponseEntity

When you want control over status + headers + body:

~~~java
return Mono.just(
        ResponseEntity.status(HttpStatus.CREATED)
                .header("Location", "/api/orders/ORD-0042")
                .body(new OrderView("ORD-0042", "shop-a", "created")));
~~~

This snippet is a return expression inside a method with a matching signature.

`ResponseEntity` is usually the first choice in annotated REST controllers; you do not need to write a custom `HttpMessageWriter` just to return status 201.

### 12.2 @ResponseStatus

For a fixed status:

~~~java
@ResponseStatus(HttpStatus.NO_CONTENT)
@DeleteMapping("/{id}")
public Mono<Void> delete(@PathVariable String id) {
    return Mono.empty();
}
~~~

This snippet belongs in a controller with appropriate imports. `@ResponseStatus` is convenient when a handler always returns the same status, but when status varies dynamically or headers need control, `ResponseEntity` is clearer.

### 12.3 Functional ServerResponse

Functional endpoints use:

~~~java
return ServerResponse.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(view);
~~~

This snippet is the return value of a `HandlerFunction<ServerResponse>` inside a `RouterFunction`. Functional routing does not use `RequestMappingHandlerAdapter`'s annotation argument resolvers; handlers receive `ServerRequest` and extract data from the request context themselves.

Do not confuse `ServerResponse` with Servlet's `HttpServletResponse`. `ServerResponse` belongs to Spring WebFlux's functional endpoints API.

## 13. JSON Body: Jackson and WebFlux HTTP Codecs

WebFlux uses **HttpMessageReader / HttpMessageWriter** and Encoder/Decoder. In Spring MVC, the common name is `HttpMessageConverter`. Same JSON need, different extension APIs.

When a controller accepts:

~~~java
@PostMapping(
        path = "/echo",
        consumes = MediaType.APPLICATION_JSON_VALUE)
public Mono<EchoView> echo(@RequestBody Mono<EchoRequest> input) {
    return input.map(v -> new EchoView(v.message()));
}
~~~

The Jackson decoder reads JSON into `EchoRequest`. When the controller returns `EchoView`, the Jackson encoder writes the JSON response.

**Formatters do not control how JSON is serialized**. To rename fields, format dates, hide properties, configure null inclusion, or set global serializer policies, use DTO/Jackson annotations and appropriate `ObjectMapper` configuration.

### @JsonProperty Controls Field Names

~~~java
record OrderView(
        @JsonProperty("order_code") String orderCode,
        String tenant,
        String status) {
}
~~~

With default Jackson in Boot 3.3, the JSON looks like:

~~~json
{"order_code":"ORD-0042","tenant":"shop-a","status":"ready"}
~~~

This snippet requires importing `com.fasterxml.jackson.annotation.JsonProperty` and defining the record in the package. `@JsonProperty` changes the JSON representation, but **does not** automatically convert path variable `"/api/orders/ord-0042"` into `OrderCode`. That is the formatter's job.

### Is a Formatter Ever Needed for JSON?

Formatters can participate in data bound via `ConversionService` in certain specialized mechanisms, yet JSON bodies read by Jackson follow codec contracts and should not rely on `FormatterRegistry` as a general serialization solution. Keeping these two pipelines distinct is the central principle of this lesson.

## 14. Configuring ServerCodecConfigurer

`WebFluxConfigurer` provides:

~~~java
@Override
public void configureHttpMessageCodecs(
        ServerCodecConfigurer configurer) {
    configurer.defaultCodecs().maxInMemorySize(256 * 1024);
}
~~~

This is a complete method when placed inside a `WebFluxConfigurer` class importing `org.springframework.http.codec.ServerCodecConfigurer`.

- `maxInMemorySize` configures the default memory limit for codecs that perform buffering/aggregation, as applied by each codec.
- It helps reduce the risk of holding excessive data in memory when deserializing large bodies.
- It is **not an absolute cap on all request bodies or `Flux` streams**; an actively streaming endpoint can process more data without aggregating into a single object.
- If a body exceeds the limit when a codec needs to aggregate, the error can involve `DataBufferLimitException`; the exact HTTP response depends on the framework, error mapping, and configuration.
- Also check proxy/gateway limits, header size limits, and multipart limits if your API handles large uploads.

In Boot, there is also a property:

~~~properties
spring.codec.max-in-memory-size=256KB
~~~

Normally, use the property for simple environment-based limits. Avoid setting both the property and Java code for the same limit unless you have a clear reason regarding precedence.

### Custom Codecs for New Formats

`ServerCodecConfigurer` allows registering additional decoders/encoders or `HttpMessageReader`/`Writer` implementations. Do this only when a media type/schema is genuinely unsupported by the framework.

When writing a custom codec:

1. Define the supported media types and `ResolvableType`.
2. Distinguish streaming versus single-value aggregation.
3. Handle backpressure, cancellation, and `DataBuffer` lifecycles properly.
4. Never log bodies containing tokens or sensitive data.
5. Test `Content-Type`/`Accept`, decoding errors, encoding, memory limits, and codec ordering.
6. Avoid replacing the entire default codec list, which easily breaks JSON, String, or form/multipart support.

`configurer.defaultCodecs()` lets you tune many built-in codecs; `configurer.customCodecs()` exposes codec registration methods depending on the version. Do not guess Spring 7 method names and assume they apply verbatim in Boot 3.3 / Spring 6.1.

### Specialized Jackson Example

You can use `@JsonProperty`/`@JsonFormat` on DTOs, or configure `ObjectMapper`/`Jackson2ObjectMapperBuilderCustomizer` for global policies. In Spring Boot, prefer configuring Jackson through Boot so you do not accidentally lose framework-managed modules (Java Time, Kotlin, JDK8, etc.), rather than doing `new ObjectMapper()` and replacing all codecs.

## 15. Complete Java 17+ Application: Three Customizations Working Together

The example includes:

- Spring Boot WebFlux + Reactor Netty, without `starter-web`.
- A Formatter converting case-insensitive path variables into a normalized `OrderCode`.
- Custom `@TenantHeader` + `TenantHeaderResolver` reading `X-Tenant-Id`.
- `ResponseEntity` controlling status/headers/body.
- `@JsonProperty` customizing a JSON key.
- `WebFilter.beforeCommit` adding a common header before response commit.
- `ServerCodecConfigurer` capping aggregation memory.
- A `WebTestClient` integration test using `RANDOM_PORT`.

### 15.1 Directory Structure

~~~text
webflux-custom-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   └── java/com/example/customwebflux/
    │       ├── CustomWebFluxApplication.java
    │       ├── OrderCode.java
    │       ├── OrderCodeFormatter.java
    │       ├── TenantHeader.java
    │       ├── TenantContext.java
    │       ├── TenantHeaderResolver.java
    │       ├── WebFluxCustomConfig.java
    │       ├── OrderController.java
    │       └── ResponseHeadersFilter.java
    └── test/
        └── java/com/example/customwebflux/
            └── WebFluxCustomizationTests.java
~~~

### 15.2 settings.gradle

~~~groovy
rootProject.name = 'webflux-custom-demo'
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

All classes in the example use package `com.example.customwebflux`. Install Gradle compatible with Spring Boot 3.3.x, or use a Gradle wrapper if your project includes one. Do not force Reactor/Netty versions different from Boot's BOM in this example.

### 15.4 CustomWebFluxApplication.java

~~~java
package com.example.customwebflux;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CustomWebFluxApplication {

    public static void main(String[] args) {
        SpringApplication.run(CustomWebFluxApplication.class, args);
    }
}
~~~

### 15.5 OrderCode.java and OrderCodeFormatter.java

`OrderCode.java`:

~~~java
package com.example.customwebflux;

public record OrderCode(String value) {
}
~~~

`OrderCodeFormatter.java`:

~~~java
package com.example.customwebflux;

import java.text.ParseException;
import java.util.Locale;

import org.springframework.format.Formatter;

public final class OrderCodeFormatter implements Formatter<OrderCode> {

    @Override
    public OrderCode parse(String text, Locale locale)
            throws ParseException {

        if (text == null) {
            throw new ParseException("Order code is required", 0);
        }

        String normalized = text.trim().toUpperCase(Locale.ROOT);

        if (!normalized.matches("ORD-[0-9]{4}")) {
            throw new ParseException(
                    "Expected order code such as ORD-0042", 0);
        }

        return new OrderCode(normalized);
    }

    @Override
    public String print(OrderCode object, Locale locale) {
        return object.value();
    }
}
~~~

### 15.6 TenantHeader.java and TenantContext.java

`TenantHeader.java`:

~~~java
package com.example.customwebflux;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.PARAMETER)
@Retention(RetentionPolicy.RUNTIME)
public @interface TenantHeader {
}
~~~

`TenantContext.java`:

~~~java
package com.example.customwebflux;

public record TenantContext(String id) {
}
~~~

### 15.7 TenantHeaderResolver.java

~~~java
package com.example.customwebflux;

import java.util.Locale;

import org.springframework.core.MethodParameter;
import org.springframework.http.HttpStatus;
import org.springframework.web.reactive.BindingContext;
import org.springframework.web.reactive.result.method.HandlerMethodArgumentResolver;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

public final class TenantHeaderResolver
        implements HandlerMethodArgumentResolver {

    @Override
    public boolean supportsParameter(MethodParameter parameter) {
        return parameter.hasParameterAnnotation(TenantHeader.class)
                && parameter.getParameterType().equals(TenantContext.class);
    }

    @Override
    public Mono<Object> resolveArgument(
            MethodParameter parameter,
            BindingContext bindingContext,
            ServerWebExchange exchange) {

        return Mono.defer(() -> {
            String header = exchange.getRequest().getHeaders()
                    .getFirst("X-Tenant-Id");

            if (header == null || header.isBlank()) {
                return Mono.error(new ResponseStatusException(
                        HttpStatus.BAD_REQUEST,
                        "X-Tenant-Id is required"));
            }

            String tenantId = header.trim().toLowerCase(Locale.ROOT);

            if (!tenantId.matches("[a-z0-9-]{1,24}")) {
                return Mono.error(new ResponseStatusException(
                        HttpStatus.BAD_REQUEST,
                        "Invalid X-Tenant-Id"));
            }

            return Mono.just((Object) new TenantContext(tenantId));
        });
    }
}
~~~

This resolver is instructional and **does not replace authentication/authorization**: a client can forge `X-Tenant-Id` if the server does not authenticate requests. In production, tenant context should be derived/verified from an authenticated principal and proper access policies.

### 15.8 WebFluxCustomConfig.java

~~~java
package com.example.customwebflux;

import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.http.codec.ServerCodecConfigurer;
import org.springframework.web.reactive.config.WebFluxConfigurer;
import org.springframework.web.reactive.result.method.annotation.ArgumentResolverConfigurer;

@Configuration
public class WebFluxCustomConfig implements WebFluxConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addFormatter(new OrderCodeFormatter());
    }

    @Override
    public void configureArgumentResolvers(
            ArgumentResolverConfigurer configurer) {
        configurer.addCustomResolver(new TenantHeaderResolver());
    }

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {
        configurer.defaultCodecs().maxInMemorySize(256 * 1024);
    }
}
~~~

We do not use `@EnableWebFlux`: the `@Configuration` class implementing `WebFluxConfigurer` adds features without overriding how Spring Boot normally applies auto-configuration.

These three methods are three independent extension points; do not assume `configureArgumentResolvers` can modify codecs or that `addFormatters` can alter JSON field names.

### 15.9 OrderController.java

~~~java
package com.example.customwebflux;

import com.fasterxml.jackson.annotation.JsonProperty;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    @GetMapping(
            path = "/{code}",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<OrderView>> find(
            @PathVariable("code") OrderCode code,
            @TenantHeader TenantContext tenant) {

        OrderView view =
                new OrderView(code.value(), tenant.id(), "ready");

        return Mono.just(ResponseEntity.ok()
                .header("X-Handler", "orders")
                .body(view));
    }

    @PostMapping(
            path = "/echo",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<EchoView>> echo(
            @RequestBody Mono<EchoRequest> input,
            @TenantHeader TenantContext tenant) {

        return input.map(request -> {
            if (request.message() == null
                    || request.message().isBlank()) {
                throw new ResponseStatusException(
                        HttpStatus.BAD_REQUEST,
                        "message is required");
            }

            EchoView view = new EchoView(
                    tenant.id(), request.message().trim());

            return ResponseEntity.status(HttpStatus.CREATED)
                    .header("X-Handler", "orders")
                    .body(view);
        });
    }
}

record OrderView(
        @JsonProperty("order_code") String orderCode,
        String tenant,
        String status) {
}

record EchoRequest(String message) {
}

record EchoView(String tenant, String message) {
}
~~~

On GET:

- Path `"ord-0042"` is converted by the Formatter into `OrderCode("ORD-0042")`.
- `@TenantHeader` reads `X-Tenant-Id: Shop-A` and builds `TenantContext("shop-a")`.
- The controller returns `ResponseEntity` with status 200, header `X-Handler`, and `OrderView`.
- Jackson uses `@JsonProperty("order_code")` to name the JSON field.

On POST:

- `@RequestBody Mono<EchoRequest>` is processed by the WebFlux JSON reader, **not** by `OrderCodeFormatter`.
- Custom `TenantHeaderResolver` still supplies the `tenant` argument.
- If `message` is null or blank, `ResponseStatusException` leads to HTTP 400 before creating `EchoView`.
- If valid, the controller returns HTTP 201 with the trimmed JSON body.

### 15.10 ResponseHeadersFilter.java

~~~java
package com.example.customwebflux;

import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@Component
@Order(0)
public class ResponseHeadersFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        exchange.getResponse().beforeCommit(() -> {
            exchange.getResponse().getHeaders()
                    .set("X-WebFlux-Custom", "enabled");
            return Mono.empty();
        });

        return chain.filter(exchange);
    }
}
~~~

This `WebFilter` only modifies a response header; it does not read the body and does not call `subscribe()`.

**`beforeCommit`** registers a callback invoked right before the response commits. For common statuses/headers or correlation data, this is far better than trying to modify JSON bytes after Jackson encodes them. The callback must not perform blocking I/O.

## 16. Running the Example and Inspecting Results

### 16.1 Build and Start

Inside the project directory:

~~~bash
gradle clean test bootRun
~~~

This assumes Gradle compatible with Spring Boot 3.3 is installed. In projects with a Gradle wrapper, replace `gradle` with `./gradlew` or `gradlew.bat`.

### 16.2 GET with Formatter and Resolver

~~~bash
curl -i 'http://127.0.0.1:8080/api/orders/ord-0042' \
  -H 'X-Tenant-Id: Shop-A'
~~~

Expected HTTP status: 200 OK.

Expected application headers:

~~~text
X-Handler: orders
X-WebFlux-Custom: enabled
~~~

Equivalent JSON body:

~~~json
{"order_code":"ORD-0042","tenant":"shop-a","status":"ready"}
~~~

Do not assert JSON field order or all Reactor Netty HTTP headers, as codecs and the server determine how they are emitted.

### 16.3 POST with JSON Reader and Status 201

~~~bash
curl -i -X POST 'http://127.0.0.1:8080/api/orders/echo' \
  -H 'Content-Type: application/json' \
  -H 'X-Tenant-Id: shop-a' \
  -d '{"message":"  hello WebFlux  "}'
~~~

Expected HTTP 201 Created and equivalent body:

~~~json
{"tenant":"shop-a","message":"hello WebFlux"}
~~~

The trim operation in the controller happens **after** the JSON body is decoded into `EchoRequest`. That is not `FormatterRegistry`'s job.

### 16.4 Missing Tenant Header

~~~bash
curl -i 'http://127.0.0.1:8080/api/orders/ord-0042'
~~~

Expected HTTP 400 Bad Request because the custom argument resolver returns `Mono.error(ResponseStatusException)`. Boot's default error body varies by config and version; do not predict exact JSON error bodies unless an error contract is configured.

### 16.5 Malformed Order Code

~~~bash
curl -i 'http://127.0.0.1:8080/api/orders/nope' \
  -H 'X-Tenant-Id: shop-a'
~~~

Expected HTTP 400 Bad Request from the path variable type-conversion failure before reaching the controller. There is no need to write `OrderController.find(...)` to accept a raw String `"nope"` and validate it manually there.

### 16.6 Malformed JSON Body or Wrong Content-Type

~~~bash
curl -i -X POST 'http://127.0.0.1:8080/api/orders/echo' \
  -H 'Content-Type: text/plain' \
  -H 'X-Tenant-Id: shop-a' \
  -d 'plain text'
~~~

The endpoint declares `consumes=application/json`, so a `text/plain` request typically receives `415 Unsupported Media Type` per WebFlux's content-type matching rules.

These statuses are **expected outcomes deduced from the code and configuration**, not logs from an execution run captured in this document.

## 17. Integration Test Running on a Dynamic Port

File `WebFluxCustomizationTests.java`:

~~~java
package com.example.customwebflux;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class WebFluxCustomizationTests {

    @LocalServerPort
    private int port;

    private WebTestClient client() {
        return WebTestClient.bindToServer()
                .baseUrl("http://127.0.0.1:" + port)
                .build();
    }

    @Test
    void formatterResolverAndJsonResponseWorkTogether() {
        client().get()
                .uri("/api/orders/ord-0042")
                .header("X-Tenant-Id", "Shop-A")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals("X-Handler", "orders")
                .expectHeader().valueEquals(
                        "X-WebFlux-Custom", "enabled")
                .expectBody()
                .jsonPath("$.order_code").isEqualTo("ORD-0042")
                .jsonPath("$.tenant").isEqualTo("shop-a")
                .jsonPath("$.status").isEqualTo("ready");
    }

    @Test
    void missingCustomArgumentGetsBadRequest() {
        client().get()
                .uri("/api/orders/ord-0042")
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void invalidFormattedPathGetsBadRequest() {
        client().get()
                .uri("/api/orders/nope")
                .header("X-Tenant-Id", "shop-a")
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void jsonBodyAndResponseStatusCanBeCustomized() {
        client().post()
                .uri("/api/orders/echo")
                .header("X-Tenant-Id", "shop-a")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("message", "  hello WebFlux  "))
                .exchange()
                .expectStatus().isCreated()
                .expectHeader().valueEquals("X-Handler", "orders")
                .expectHeader().valueEquals(
                        "X-WebFlux-Custom", "enabled")
                .expectBody()
                .jsonPath("$.tenant").isEqualTo("shop-a")
                .jsonPath("$.message").isEqualTo("hello WebFlux");
    }
}
~~~

Run:

~~~bash
gradle test
~~~

- `WebTestClient.bindToServer` sends real HTTP requests to the embedded server; tests verify the formatter, custom argument resolver, Jackson JSON, and response headers together.
- `RANDOM_PORT` avoids colliding with port 8080 in CI.
- Tests asserting data should not depend on JSON field order.
- A test using only `bindToController` or a mocked context verifies WebFlux logic but **does not** test the real network adapter.
- If the application includes `spring-boot-starter-web` and Boot selects Servlet MVC, fix the dependency/web application type before concluding WebFlux configuration is broken.

## 18. Narrower-Scope Response Content Customization

### 18.1 Per Endpoint: DTOs and ResponseEntity

The easiest approach to maintain:

- Create dedicated DTOs for public APIs rather than exposing persistence entities directly.
- Use `ResponseEntity` when status and headers are needed.
- Use Jackson annotations for field names, timestamp formatting, or hidden fields.
- Use explicit contracts for success and error payloads; never build JSON via string concatenation.

Example:

~~~java
record PublicOrder(
        @JsonProperty("order_code") String orderCode,
        @JsonProperty("display_name") String displayName) {
}
~~~

This snippet requires importing `JsonProperty`; a DTO alone is neither a server nor an endpoint. `Formatter<OrderCode>` will not automatically rename JSON fields.

### 18.2 Across All Endpoints: JSON Mapper / Codec Policy

If your application wants consistent null inclusion, naming strategy, or Java Time formatting, prefer configuring Jackson/Boot accordingly. Properties such as:

~~~properties
spring.jackson.default-property-inclusion=non_null
~~~

can be used. Exact property names and compatibility must be checked against your Spring Boot version. Omitting null fields in JSON is unrelated to formatting query/path parameters; do not try to use `FormatterRegistry` for serialization goals.

### 18.3 Adding a Shared HTTP Header

Use a `WebFilter` or a dedicated server response component. The section 15 example uses `beforeCommit`. If only one controller needs a header, `ResponseEntity` is enough; no global filter is required.

### 18.4 Response Wrappers

If all responses need a structure such as `data`/`error`/`meta`, consider:

- Using explicit response DTOs at the service/controller boundary.
- Creating helper/factory methods to avoid repeating `ResponseEntity` boilerplate.
- For functional APIs, using `ServerResponse` explicitly.
- Building a custom `HandlerResultHandler` only if the return-type contract is genuinely new and you can control its precedence relative to built-in handlers.

**Do not assume Spring WebFlux has Spring MVC's `ResponseBodyAdvice` with the same mechanism.** Do not take `ResponseBodyAdvice` patterns from `org.springframework.web.servlet` and treat them as a general WebFlux hook. If global JSON body transformation is needed, evaluate strategies at the DTO/serialization/codec layer or wrapper return type instead of a filter that reads and rewrites entire bodies.

### 18.5 Why You Shouldn't Rewrite JSON Bodies in a WebFilter

A response body in WebFlux is a reactive stream of `DataBuffer`s. Intercepting and modifying bytes requires decorating `ServerHttpResponse` and handling:

- `Content-Length` and transfer encoding.
- Media types and charsets.
- Streaming, SSE, chunked data, and compression.
- Pooled `DataBuffer` memory and release/retain accounting.
- Backpressure, cancellation, and error signals.
- Cases where the response has already committed.

This is an advanced infrastructure problem—**unsuitable** for simple policies like renaming a JSON field or adding a header. It increases memory/latency and risks corrupting payloads.

## 19. Returning Streaming Content

Example Server-Sent Events endpoint:

~~~java
@GetMapping(
        path = "/events",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<String> events() {
    return Flux.just("one", "two", "three");
}
~~~

This is an illustrative method inside a `@RestController` requiring imports for `Flux`, `GetMapping`, and `MediaType`.

With `text/event-stream`, the framework uses appropriate message writers to stream items according to the media type rules. Do not replace codecs or add a wrapper that buffers an entire `Flux` into a `List` before returning, as that destroys streaming and backpressure.

If status/headers are needed for a stream:

~~~java
public Mono<ResponseEntity<Flux<String>>> eventsWithHeaders() {
    return Mono.just(ResponseEntity.ok()
            .contentType(MediaType.TEXT_EVENT_STREAM)
            .body(Flux.just("one", "two")));
}
~~~

This snippet shows how to set response metadata before streaming the body; it is not a standalone class. In practice you can use `ResponseEntity<Flux<String>>` directly or `Mono<ResponseEntity<Flux<String>>>` depending on your API design.

Neither a Formatter nor a custom argument resolver controls stream ordering, chunking, or termination. That responsibility belongs to the `Publisher`, codecs, and `ServerHttpResponse`.

## 20. Validation and Exception Handling During Customization

### 20.1 Bad Request from Formatting

When `OrderCodeFormatter.parse` rejects an invalid URL segment, the framework can send HTTP 400 due to a type conversion error. Verify actual error resolution if your application has custom `@ControllerAdvice` or `WebExceptionHandler` beans.

### 20.2 Bad Request from an Argument Resolver

`TenantHeaderResolver` in the example uses `ResponseStatusException(BAD_REQUEST)`. This is clearer than throwing a generic `IllegalStateException` and expecting the framework to always infer 400.

### 20.3 JSON Body Validation

In WebFlux, `@Valid @RequestBody DTO` can trigger Jakarta Bean Validation when a provider is present. In Spring Boot, to enable Jakarta validation, typically add:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-validation'
~~~

Do not assume `starter-webflux` always includes a full validation provider. With `@RequestBody Mono<DTO>`, applying validation inside reactive pipelines follows specific rules; test invalid inputs and check exact exception types for your Spring Framework version.

### 20.4 Error Contracts

`@RestControllerAdvice` and `@ExceptionHandler` handle supported errors within annotated controllers; `WebExceptionHandler` can handle errors in the `WebHandler` chain. Never expose internal exception messages containing tokens or infrastructure details.

Once response headers have committed, an exception handler cannot arbitrarily change the status or write a fresh error JSON without corrupting the response. With `Flux` streaming in particular, check cancellation and error behavior.

## 21. Debugging When a Formatter or Resolver Does Not Run

### 21.1 Is the Formatter Being Called?

Check:

1. Is the application running the WebFlux reactive stack?
2. Is the `@Configuration implements WebFluxConfigurer` class within component scan scope?
3. Does `addFormatters` register the right `Formatter<T>`?
4. Is the controller parameter the exact type `T`, and does the input go through data binding/conversion?
5. Is another `Converter` taking precedence or a built-in annotation handling it first?
6. Does the path/query input match your regex, `Locale`, and trimming rules?
7. Did the failure happen during route mapping or during conversion after mapping?
8. Test with `WebTestClient` using both valid and malformed inputs.

### 21.2 Is the Custom Argument Resolver Being Called?

Check:

1. Are you using the reactive `HandlerMethodArgumentResolver` interface?
2. Is the overridden method `WebFluxConfigurer.configureArgumentResolvers`, not `WebMvcConfigurer.addArgumentResolvers`?
3. Is `ArgumentResolverConfigurer` from the Spring WebFlux package?
4. Does `supportsParameter` return `true` for the actual parameter?
5. Does the controller parameter have `@TenantHeader` and the exact `TenantContext` type?
6. Did a built-in resolver claim the parameter first?
7. Does `Mono<Object>` emit the right object without manual `subscribe()` or `block()`?
8. Did proxies or security layers pass the `X-Tenant-Id` header through?
9. Does your authorization policy actually trust the tenant value?

### 21.3 Is JSON Output Not Changing as Expected?

Check:

1. Does the controller have `@RestController`/`@ResponseBody` or an appropriate return type?
2. Does `ResponseEntity` have the right status, headers, and body?
3. Are the request `Accept` media type and endpoint `produces` compatible?
4. Is Jackson on the classpath and are DTO annotations correct?
5. Is `@JsonProperty` applied to the right field, getter, or record component?
6. Did a custom codec replace Boot's auto-configured `ObjectMapper`?
7. Did the response already commit before a filter tried to set headers?
8. Did a reverse proxy or `WebFilter` alter headers/body afterward?
9. Are custom serializers, Jackson mixins, JSON views, or naming strategies taking effect?
10. For streams, is a codec buffering/aggregating unintentionally?

### Logs and Breakpoints

In local/test environments, you can inspect:

~~~properties
logging.level.org.springframework.web.reactive.DispatcherHandler=DEBUG
logging.level.org.springframework.web.reactive.result.method.annotation=TRACE
logging.level.org.springframework.web.server.adapter.HttpWebHandlerAdapter=DEBUG
~~~

To verify the exact resolution order, place breakpoints in `RequestMappingHandlerAdapter`, `InvocableHandlerMethod`, and your `OrderCodeFormatter`/`TenantHeaderResolver`. `TRACE` can expose request metadata; do not enable it broadly in production.

## 22. Design Mistakes to Avoid

- **Using `WebMvcConfigurer` in an app meant to run WebFlux**: its methods and SPIs do not apply to a WebFlux server.
- **Adding `@EnableWebFlux` unconditionally**: shifts configuration control away from Boot and can disable expected auto-configurations.
- **Using a Formatter to customize JSON**: `FormatterRegistry` is primarily for type conversion/binding, whereas JSON is handled by HTTP codecs/Jackson.
- **Custom resolver returning `Object` instead of `Mono<Object>`**: does not match the WebFlux interface.
- **Overly broad `supportsParameter`**: can collide with built-in resolvers and break other method arguments.
- **Calling `.block()` inside an argument resolver**: stalls the event loop and hurts scalability.
- **Reading `X-Tenant-Id` from clients and treating it as authorization**: opens cross-tenant access vulnerabilities.
- **Calling `subscribe()` manually on bodies or responses**: detaches the Publisher from the request lifecycle, causing races and losing error/cancellation propagation.
- **Replacing all codecs** just to tweak one JSON field: risks losing form/multipart/string readers and writers.
- **Assuming `maxInMemorySize` caps the entire HTTP request**: it depends on how each codec buffers data.
- **Retaining a `DataBuffer` after response commit**: can leak memory or read already-released buffers.
- **Modifying status/headers after commit**: may have no effect or raise errors.
- **Applying Servlet `ResponseBodyAdvice` as a WebFlux equivalent**: mixes stacks and extension semantics.
- **Asserting JSON by field order**: JSON object key order is not a contract; assert individual field values instead.
- **Testing only via direct controller calls**: skips binding, argument resolvers, codecs, and HTTP result handling.

## 23. Implementation Checklist

1. Confirm Boot runs **`WebApplicationType.REACTIVE`** and the right server stack.
2. Choose `Formatter`/`Converter` for simple path/query/field value conversions.
3. Choose a custom reactive `HandlerMethodArgumentResolver` for arguments combining request metadata.
4. Use distinct annotations and parameter types; avoid hijacking built-in arguments.
5. Register both via `WebFluxConfigurer`, without mixing in MVC SPIs.
6. Use DTOs/`ResponseEntity`/Jackson to define status, headers, and body contracts.
7. Use `ServerCodecConfigurer` for codec settings; prefer Boot properties when sufficient.
8. Use `WebFilter` only for genuine cross-cutting middleware.
9. Never manually subscribe, block, or swallow reactive errors.
10. Separate format validation from business authorization.
11. Test with `WebTestClient` for valid/invalid inputs and response headers.
12. Test streaming and large bodies when changing codec/memory settings.
13. Verify `Content-Type`/`Accept`, HTTP 400/415/406, and response commit behavior.
14. Monitor latency, blocking, and memory when introducing custom extensions.
15. Keep configuration minimal, intentional, and documented for the Spring version in use.

## 24. Summary

In Spring WebFlux, **`FormatterRegistry`** handles converting single request values into Java types; **`ArgumentResolverConfigurer`** adds logic to construct controller parameters from `ServerWebExchange`; and **`HandlerResultHandler` along with HTTP message codecs** handle serializing results into HTTP responses.

The `OrderCodeFormatter`, `TenantHeaderResolver`, and `OrderController` example shows all three working together without replacing `DispatcherHandler`, building `HttpHandler` manually, or customizing the Reactor Netty server. When status/headers need adjustment, use `ResponseEntity`/`WebFilter`; when JSON needs adjustment, use DTOs/Jackson—or codecs only when genuinely needed. Respecting layer boundaries keeps customizations independently testable, side-effect-free, and truly reactive.

## 25. References

- Spring Framework 6.1 — WebFlux Config: https://docs.spring.io/spring-framework/reference/6.1/web/webflux/config.html
- Spring Framework 6.1 — WebFluxConfigurer Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/reactive/config/WebFluxConfigurer.html
- Spring Framework 6.1 — ArgumentResolverConfigurer Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/reactive/result/method/annotation/ArgumentResolverConfigurer.html
- Spring Framework 6.1 — Reactive HandlerMethodArgumentResolver Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/reactive/result/method/HandlerMethodArgumentResolver.html
- Spring Framework — WebFlux Annotated Controllers: https://docs.spring.io/spring-framework/reference/web/webflux/controller.html
- Spring Framework — WebFlux HTTP Message Codecs: https://docs.spring.io/spring-framework/reference/web/webflux/config.html#webflux-config-message-codecs
- Spring Boot 3.3 — Reactive Web Applications: https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html
- Spring Boot 3.3 — Application Properties: https://docs.spring.io/spring-boot/3.3/appendix/application-properties/