# Parameter Constraints, Return Values, and Spring Version Conditions

In **Spring WebFlux**, a controller method does not simply accept arbitrary Java parameters and return just any type. Spring needs to know **where to take input data from**, **how to convert or decode that data**, **how the return type represents a response**, and **which Spring version supports that mechanism**.

Three groups of decisions need to be considered together:

- **Method arguments:** values come from the path, query, headers, cookies, body, multipart, session, or request context; Spring converts and validates them before or during the handler call.
- **Return values:** the handler returns a value, an asynchronous publisher, a multi-element stream, a response with custom status/headers, or a view.
- **Version conditions:** Spring generations change the Java baseline, the validation namespace (javax/jakarta), how method validation works, and support for asynchronous types.

This lesson focuses on Spring WebFlux annotated controllers, with examples in Java 17, Reactor, Bean Validation, and WebTestClient.

## 1. Learning objectives

After this lesson, you can:

1. Distinguish parameter sources such as **@PathVariable**, **@RequestParam**, **@RequestHeader**, **@CookieValue**, **@RequestBody**, **@RequestPart**, and **@ModelAttribute**.
2. Choose an appropriate synchronous or reactive parameter type; understand why Mono<T>/Flux<T> are usually used only where body reading or asynchronous I/O is needed.
3. Explain how Spring converts strings to Java types such as UUID, int, LocalDate, and enums, and apply default/optional/required.
4. Distinguish Mono<T>, Flux<T>, Mono<Void>, ResponseEntity<T>, ResponseEntity<Flux<T>>, String, Model, and void in the return position.
5. Understand encoding/decoding with HttpMessageReader and HttpMessageWriter, media types, and streaming responses.
6. Use @Valid, @Validated, constraint annotations, BindingResult, and handle validation exceptions.
7. Recognize key milestones: WebFlux since Spring 5.0, Kotlin coroutine support since 5.2, the Jakarta namespace since 6.0, built-in method validation since 6.1, and the Spring 7 baseline.
8. Design controllers compatible with the actual dependency versions, avoiding copying javax examples into a jakarta project or using APIs that do not exist yet.
9. Test binding, validation, status, headers, and body with WebTestClient.

## 2. Processing flow of a controller method

When an HTTP request arrives at an annotated controller, Spring WebFlux performs a general sequence of steps:

~~~text
HTTP request
    |
    v
Choose handler by @RequestMapping
    |
    v
Resolve method arguments
(path/query/header/cookie/body/session...)
    |
    v
Type conversion + data binding + validation
    |
    v
Invoke controller method
    |
    v
Receive return value
(Mono / Flux / ResponseEntity / void / view...)
    |
    v
Encode response with HttpMessageWriter or render view
    |
    v
HTTP response
~~~

Not all parameters are resolved in the same way:

- Path, query, header, and cookie usually start as strings and then go through the conversion service.
- The request body is decoded through codecs/HttpMessageReader.
- @ModelAttribute uses data binding to populate an object.
- Mono/Flux in supported positions represents data being supplied asynchronously.
- The return value is interpreted according to the return handler type; String can be a view name, whereas in @RestController an object is usually written as the response body.

**Important point:** WebFlux has reactive I/O, but that does not mean every parameter should be wrapped in Mono. Simple parameters such as path variables or query parameters are usually resolved to Java values before calling the handler. Using a reactive wrapper in the wrong place can make the signature unsupported or add unnecessary complexity to the code.

## 3. Commonly used method argument types

### 3.1. Request and exchange objects

A handler can receive objects that give direct access to the request/response:

| Parameter | Purpose |
| --- | --- |
| ServerWebExchange | High-level container for request, response, session, and request attributes. |
| ServerHttpRequest | Reads method, URI, headers, cookies, and body at the HTTP level. |
| ServerHttpResponse | Controls status, headers, and response body when direct manipulation is needed. |
| WebSession | Accesses the reactive session; the session is not necessarily created anew if no operation requires it. |
| Principal | Authenticated user, if an appropriate security context exists. |
| HttpMethod | HTTP method of the current request. |
| Locale, TimeZone, ZoneId | Locale/time zone context according to the application's resolver configuration. |
| UriComponentsBuilder | Builds URLs based on the request's scheme, host, port, and context path. |

Example:

~~~java
@GetMapping("/debug")
Mono<String> debug(
        ServerWebExchange exchange,
        ServerHttpRequest request,
        HttpMethod method) {

    String path = request.getURI().getPath();
    String client = request.getHeaders()
        .getFirst("X-Client");

    return Mono.just(
        method + " " + path + " client=" + client
    );
}
~~~

This is an integration snippet that needs imports for the corresponding Spring WebFlux types. Do not receive HttpServletRequest/HttpServletResponse in a WebFlux controller: use reactive abstractions such as ServerHttpRequest, ServerHttpResponse, or ServerWebExchange.

### 3.2. @PathVariable

Used to extract values from the URI template:

~~~java
@GetMapping("/orders/{id}")
Mono<OrderView> get(@PathVariable("id") UUID id) {
    return orderService.findById(id);
}
~~~

With the request /orders/6a..., Spring takes the {id} segment and converts it to UUID. If the string is invalid, conversion fails before the handler is called and enters the binding/conversion error-handling mechanism.

A path variable is normally required because the path pattern itself requires it. Naming it explicitly in the annotation keeps the code independent of whether the compiler retains parameter names via the -parameters option.

### 3.3. @RequestParam

In WebFlux, @RequestParam is used to get **query parameters**:

~~~java
@GetMapping("/search")
Flux<ProductView> search(
        @RequestParam("q") String keyword,
        @RequestParam(defaultValue = "0") int page,
        @RequestParam(defaultValue = "20") int size) {
    return productService.search(keyword, page, size);
}
~~~

Example request:

~~~text
GET /api/products/search?q=keyboard&page=0&size=20
~~~

Important attributes:

- name/value: query parameter name.
- required: default true.
- defaultValue: used when the parameter is absent or the value is empty; when a default is present, the parameter is no longer required.
- Map<String, String> or MultiValueMap<String, String> can be used when many query parameters need to be retrieved.

For optional values, you can use Optional<T>:

~~~java
@GetMapping("/products")
Flux<ProductView> list(
        @RequestParam(required = false) Optional<String> category) {
    return productService.list(category);
}
~~~

Optional.empty() represents an absent query parameter; avoid using the string "null" as a signal for missing data.

**Difference to remember:** in Spring MVC, @RequestParam can include query/form parameters under the Servlet model. In Spring WebFlux, @RequestParam focuses on query parameters. For a form body, use @ModelAttribute, ServerWebExchange.getFormData(), or an appropriate body-reading approach.

### 3.4. @RequestHeader and @CookieValue

@RequestHeader binds a value from an HTTP header:

~~~java
@GetMapping("/me")
Mono<String> me(
        @RequestHeader("X-Request-Id") String requestId,
        @RequestHeader(name = "Accept-Language", required = false)
        Optional<String> language) {
    return Mono.just("request=" + requestId
        + ", language=" + language.orElse("vi"));
}
~~~

@CookieValue binds a cookie value:

~~~java
@GetMapping("/preferences")
Mono<String> preferences(
        @CookieValue(name = "locale", defaultValue = "vi")
        String locale) {
    return Mono.just("locale=" + locale);
}
~~~

Headers/cookies are also converted to the appropriate Java type when a converter exists. Do not use required=false if the logic genuinely needs a required value; define a default or handle Optional explicitly.

### 3.5. @RequestBody and HttpEntity

@RequestBody decodes the request body via HttpMessageReader/codecs. With WebFlux, you can use a direct value type or a reactive wrapper depending on your needs:

~~~java
@PostMapping("/orders")
Mono<OrderView> create(@RequestBody CreateOrderRequest request) {
    return orderService.create(request);
}
~~~

Or when you want to compose the body in a reactive pipeline:

~~~java
@PostMapping("/orders")
Mono<OrderView> create(
        @RequestBody Mono<CreateOrderRequest> request) {
    return request.flatMap(orderService::create);
}
~~~

With a streaming body:

~~~java
@PostMapping(
    path = "/events/import",
    consumes = "application/stream+json"
)
Mono<ImportSummary> importEvents(
        @RequestBody Flux<EventInput> events) {
    return importService.process(events);
}
~~~

Flux<T> can help process elements one by one when the codec and media type support streaming. Do not assume that every JSON body is an unbounded stream; the media type and codec determine how it is read. For small finite bodies, a direct DTO or Mono<DTO> is usually easier to manage.

HttpEntity<T> gives access to both headers and body:

~~~java
@PostMapping("/echo")
Mono<ResponseEntity<String>> echo(
        HttpEntity<Mono<String>> entity) {
    return entity.getBody()
        .defaultIfEmpty("")
        .map(body -> ResponseEntity.ok()
            .header("X-Received", "true")
            .body(body));
}
~~~

This is an illustrative integration snippet. Use HttpEntity when you need request headers together with the body in one parameter; if you only need the body, @RequestBody is clearer.

### 3.6. @RequestPart and multipart

For multipart/form-data, @RequestPart accesses one part by name:

~~~java
@PostMapping(
    path = "/files",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
Mono<String> upload(@RequestPart("file") FilePart file) {
    return file.transferTo(
        Paths.get("/tmp/uploads", file.filename())
    ).thenReturn(file.filename());
}
~~~

This is an illustrative snippet that needs imports for FilePart, Paths, and an appropriate storage path configuration. Do not use the client-supplied filename directly to build a trusted path; a real application must check the name, permissions, size, content type, and storage location.

If you need to stream multipart at a low level, WebFlux also provides Part/Flux<Part> and ServerWebExchange APIs. Choose between reading the entire multipart or streaming part by part according to data size and memory requirements.

### 3.7. @ModelAttribute

@ModelAttribute uses data binding to create or update a command object from supported request values:

~~~java
record ProductFilter(String category, Integer minPrice) {}

@GetMapping("/products/filter")
Flux<ProductView> filter(@ModelAttribute ProductFilter filter) {
    return productService.filter(filter);
}
~~~

If a parameter is not annotated and is not recognized by another resolver, Spring usually treats simple types as request parameters and complex objects as model attributes. Use explicit annotations in important APIs so the contract is easy to read.

Data binding can put client-sent values into many properties of an object. To avoid mass assignment, use a DTO containing only the fields allowed to bind; configure allowed fields or an appropriate binder via @InitBinder. Do not bind persistence entities directly if they have many sensitive fields such as role, ownerId, balance, or audit fields.

### 3.8. @SessionAttribute, @RequestAttribute, Errors, and BindingResult

- @SessionAttribute: reads an attribute that already exists in WebSession.
- @RequestAttribute: reads an attribute placed in the request by a filter/interceptor.
- Errors/BindingResult: reads data binding/validation errors of a command object.

BindingResult or Errors must be placed **immediately after** the validated parameter for Spring to attach errors to the right object:

~~~java
@PostMapping("/profile")
Mono<String> save(
        @Valid @ModelAttribute ProfileForm form,
        BindingResult errors) {
    if (errors.hasErrors()) {
        return Mono.just("invalid");
    }
    return profileService.save(form).thenReturn("saved");
}
~~~

If another parameter sits between the object and BindingResult, Spring cannot associate errors this way. For reactive argument wrappers or method-level validation, check the rules for the exact Spring version in use; do not mechanically copy a BindingResult pattern from another signature.

## 4. Where are reactive wrappers supported?

Mono<T> and Flux<T> are not annotations to turn every parameter asynchronous. Spring WebFlux supports reactive types on arguments that need asynchronous I/O resolution, for example:

- @RequestBody Mono<T> or @RequestBody Flux<T>.
- HttpEntity<Mono<T>> and corresponding reactive body types.
- @RequestPart when handling multipart reactively.
- Certain arguments such as WebSession and Principal can be provided via reactive types.

For @PathVariable, @RequestParam, @RequestHeader, and @CookieValue, direct Java types such as UUID, String, int, and Optional<String> are normally used. Do not write Mono<UUID> for a query parameter just because the controller is WebFlux.

A useful rule:

| Data source | Commonly used type |
| --- | --- |
| Path variable | UUID, String, long... |
| Query/header/cookie | Java value or Optional<T> |
| Single JSON body | Direct DTO or Mono<DTO> |
| Body stream | Flux<T> if the codec/media type supports it |
| Multipart part | FilePart, Part, or reactive part type |
| Request/session context | ServerWebExchange, WebSession, Principal |

**Specific versions and resolvers can affect special cases.** For example, Spring 5.3 documentation once described reactive wrappers for @ModelAttribute; when upgrading to a newer branch, check the current argument table and test the actual signature. If you need BindingResult, a non-reactive-wrapped command object type is clearer and more compatible.

## 5. Type conversion and data binding

Spring converts input values to Java types through the conversion/formatting mechanism. Example:

~~~java
@GetMapping("/orders/{id}")
Mono<OrderView> get(
        @PathVariable UUID id,
        @RequestParam(defaultValue = "2026-01-01")
        LocalDate fromDate,
        @RequestParam(defaultValue = "1")
        int page) {
    return orderService.find(id, fromDate, page);
}
~~~

Common conversions:

- String to integer/floating-point number.
- String to UUID.
- String to enum.
- Date/time according to configured formatters/converters.
- Header/cookie/query to Optional<T> or collections when supported by the resolver.

If the date format is non-ISO or an enum has special conventions, register an appropriate Converter/Formatter instead of parsing manually in each controller. This can be configured via WebFluxConfigurer.addFormatters(...).

Conversion errors differ from validation errors:

- **Conversion error:** "abc" cannot be converted to int.
- **Validation error:** quantity=0 converts to a valid int but violates @Min(1).
- **Decode error:** the JSON body is syntactically invalid or incompatible with the DTO.
- **Missing value:** a required parameter/body is absent.

Proper classification helps the API return meaningful errors and avoids collapsing everything into a hard-to-diagnose “bad request” message.

## 6. Validation: @Valid, @Validated, and constraints

### 6.1. Validating command objects

Bean Validation places constraints on fields/record components:

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

record CreateOrderRequest(
    @NotBlank String customer,
    @Min(1) @Max(100) int quantity
) {}
~~~

In the controller:

~~~java
@PostMapping("/orders")
Mono<OrderView> create(
        @Valid @RequestBody CreateOrderRequest request) {
    return orderService.create(request);
}
~~~

Once the body is decoded into an object, Spring applies validation. If data violates constraints, the handler may not be called and Spring raises WebExchangeBindException under the per-object validation mechanism.

### 6.2. Validating method parameters directly

Constraints such as @Min, @Max, and @NotBlank can be placed directly on parameters:

~~~java
@GetMapping("/orders")
Flux<OrderView> list(
        @RequestParam(defaultValue = "20")
        @Min(1) @Max(100) int limit) {
    return orderService.list(limit);
}
~~~

This is **method validation**. Since Spring Framework 6.1, WebFlux has built-in method validation support for @RequestMapping methods. When method validation is triggered, Spring may throw HandlerMethodValidationException.

@Valid itself **is not a constraint**; it requests validating constraints nested inside an object. Direct constraints such as @Min or @NotBlank on a method parameter/return value are what trigger method validation.

### 6.3. Distinguishing the two validation exceptions

| Exception | Common case |
| --- | --- |
| WebExchangeBindException | Validation of an individual command object such as @RequestBody, @ModelAttribute, @RequestPart. |
| HandlerMethodValidationException | Method-level validation due to direct constraints on parameters or return value. |

A single controller can produce both kinds depending on the method signature. If error standardization is needed, @ControllerAdvice/@ExceptionHandler should handle both, rather than catching only WebExchangeBindException.

Simple error-handling example:

~~~java
@RestControllerAdvice
class ApiValidationAdvice {

    @ExceptionHandler(WebExchangeBindException.class)
    ResponseEntity<Map<String, String>> handleBinding(
            WebExchangeBindException ex) {
        Map<String, String> errors = new LinkedHashMap<>();
        ex.getFieldErrors().forEach(error ->
            errors.put(error.getField(), error.getDefaultMessage())
        );
        return ResponseEntity.badRequest().body(errors);
    }

    @ExceptionHandler(HandlerMethodValidationException.class)
    ResponseEntity<Map<String, String>> handleMethodValidation(
            HandlerMethodValidationException ex) {
        return ResponseEntity.badRequest().body(
            Map.of("message", "Method argument validation failed")
        );
    }
}
~~~

This is an illustrative snippet for Spring 6.1+ and needs imports for the validation exceptions, Map, LinkedHashMap, and ResponseEntity. In a real API, convert each ParameterValidationResult into an error with a field/path and stable error code, rather than returning only a generic message.

### 6.4. BindingResult and parameter ordering

If using BindingResult, it must sit immediately after the validated command object:

~~~java
@PostMapping("/forms")
Mono<ResponseEntity<?>> submit(
        @Valid @ModelAttribute RegistrationForm form,
        BindingResult result) {
    if (result.hasErrors()) {
        return Mono.just(ResponseEntity.badRequest().body(result.getAllErrors()));
    }
    return registrationService.save(form)
        .map(saved -> ResponseEntity.ok(saved));
}
~~~

With method-level validation, Spring calls the handler only if errors are on parameters that have Errors/BindingResult immediately following them per method validation rules. If there is an error on another parameter not handled through BindingResult, HandlerMethodValidationException is still raised.

## 7. Controller return values

### 7.1. @ResponseBody and @RestController

With @RestController, return values are by default written to the response body through HttpMessageWriter:

~~~java
@GetMapping("/health")
Mono<Map<String, String>> health() {
    return Mono.just(Map.of("status", "UP"));
}
~~~

With @Controller, @ResponseBody is needed if you want to write an object as the response body. Otherwise, some types such as String may be interpreted as a view name to render.

### 7.2. Mono<T>: zero or one value

Use Mono<T> when the endpoint returns an asynchronous single result:

~~~java
@GetMapping("/{id}")
Mono<ProductView> get(@PathVariable UUID id) {
    return productService.findById(id);
}
~~~

Mono.empty() can represent no result; how it maps to 404, 204, or an empty body depends on the API contract. Do not assume Mono.empty() automatically returns 404 in every controller.

### 7.3. Flux<T>: many values

~~~java
@GetMapping
Flux<ProductView> list() {
    return productService.findAll();
}
~~~

WebFlux can write elements as they arrive instead of buffering everything in memory. Exact encoding depends on media type and codec. For large data or long-lived sources, streaming avoids buffering the whole list, though the client must accept that the response can be written incrementally.

If an error occurs after the response has started writing, the server may no longer be able to replace the response with a complete status/error body. When the contract requires deciding errors before sending the response, you can collect finite data first, at the cost of memory and latency.

### 7.4. Mono<Void> and void

Mono<Void> represents an asynchronous operation that only needs to signal completion/error, such as deletion or sending a signal:

~~~java
@DeleteMapping("/{id}")
Mono<Void> delete(@PathVariable UUID id) {
    return productService.deleteById(id);
}
~~~

void can also be used if the handler already handles the response itself via ServerHttpResponse, ServerWebExchange, or @ResponseStatus. In reactive code, Mono<Void> usually expresses the lifecycle more clearly because it can be composed, handle errors, and support cancellation.

### 7.5. ResponseEntity<T>

ResponseEntity<T> lets you choose status, headers, and body:

~~~java
@GetMapping("/{id}")
Mono<ResponseEntity<ProductView>> get(@PathVariable UUID id) {
    return productService.findById(id)
        .map(ResponseEntity::ok)
        .defaultIfEmpty(ResponseEntity.notFound().build());
}
~~~

You can use ResponseEntity<Mono<T>> or ResponseEntity<Flux<T>> when status/headers can be decided immediately while the body is emitted asynchronously:

~~~java
@GetMapping("/stream")
ResponseEntity<Flux<EventView>> stream() {
    Flux<EventView> body = eventService.stream();
    return ResponseEntity.ok()
        .contentType(MediaType.valueOf("application/stream+json"))
        .body(body);
}
~~~

Distinguish the two forms:

- Mono<ResponseEntity<T>>: status/headers can be decided after asynchronous data is ready.
- ResponseEntity<Mono<T>>: status/headers can be returned immediately, and the body continues emitting later.

### 7.6. Server-Sent Events

For SSE, use text/event-stream:

~~~java
@GetMapping(
    path = "/events",
    produces = MediaType.TEXT_EVENT_STREAM_VALUE
)
Flux<ServerSentEvent<EventView>> events() {
    return eventService.stream()
        .map(event -> ServerSentEvent.builder(event).build());
}
~~~

You can return Flux<EventView> without wrapping in ServerSentEvent if you only need event data. Use the wrapper when you need event id, event name, retry, or comments. SSE is a long-lived stream; account for cancellation on client disconnect, heartbeats, subscriber limits, and appropriate timeouts.

### 7.7. View and model

In controllers serving HTML, types such as String, View, Model, Map, or Rendering can participate in view rendering. Example:

~~~java
@GetMapping("/dashboard")
Mono<Rendering> dashboard() {
    return dashboardService.load()
        .map(data -> Rendering.view("dashboard")
            .modelAttribute("dashboard", data)
            .build());
}
~~~

This is an integration snippet. Do not mistake String for a response body in every controller: with a traditional @Controller, String is usually interpreted as a view name; with @RestController or @ResponseBody, it is written to the body.

## 8. Version compatibility: milestones to know

Controller signatures must be compatible with the running Spring Framework and dependencies. The biggest changes concern WebFlux, the Java baseline, the validation namespace, and method validation.

| Spring Framework Version | What to remember |
| --- | --- |
| 5.0 | WebFlux introduced; Java 8 baseline; uses the Java EE/javax ecosystem in corresponding APIs. |
| 5.2 | Kotlin coroutine support for annotated WebFlux controllers, including suspend and Flow in supported cases. |
| 5.3 | Many reactive APIs refined; RxJava 1/2 deprecated as of 5.3.11, moving toward RxJava 3. |
| 6.0 | JDK 17 and Jakarta EE 9 baseline; many packages changed from javax.* to jakarta.*. |
| 6.1 | Added built-in method validation for @RequestMapping controllers; HandlerMethodValidationException joins the validation error model. |
| 6.2 | Maintains JDK 17 and Jakarta EE 9/10 baseline; continues supporting current controller and validation mechanisms. |
| 7.0 | JDK 17, Jakarta EE 11 baseline; continues WebFlux APIs and method validation; requires dependencies compatible with the new generation. |

### 8.1. Spring 5.x: javax and Java 8 baseline

On the Spring 5.x branch, Bean Validation usually uses the namespace:

~~~java
import javax.validation.Valid;
import javax.validation.constraints.NotBlank;
~~~

Spring Framework 5.0 is the generation that introduced WebFlux. Spring 5.3 supports Java 8 and above per the 5.3 release matrix. Kotlin coroutine support has been available since Spring 5.2; using it requires adding the appropriate Kotlin/coroutines dependencies.

If a project still uses Spring 5.x, you cannot simply change imports to jakarta.validation and expect compatibility with the old provider. Check the Bean Validation provider version, servlet/container, and related dependencies.

### 8.2. Spring 6.x: JDK 17 and Jakarta namespace

Spring Framework 6.0 raised the baseline to JDK 17 and Jakarta EE 9. Validation imports changed to:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Min;
~~~

This is an important source-level change when upgrading from Spring 5.x. The javax.servlet, javax.validation, and javax.persistence packages cannot be arbitrarily substituted for jakarta.* in newer Jakarta dependencies.

Both Spring 6.0 and 6.2 require JDK 17; choose containers and providers matching the Jakarta EE baseline that the branch supports.

### 8.3. Spring 6.1: built-in method validation

Since Spring Framework 6.1, WebFlux has built-in method validation for @RequestMapping methods. When you want to use this built-in mechanism, **do not place class-level @Validated on the controller**. If class-level @Validated is present, method validation is performed via an AOP proxy under the older mechanism.

Before 6.1, method validation usually needed AOP configuration such as @Validated and MethodValidationPostProcessor; per-object validation via @Valid remained a separate mechanism. When upgrading, check exception handlers and retest because how validation is triggered/classified may differ.

### 8.4. Spring 7.0

Spring Framework 7.0 keeps the JDK 17 baseline and raises the Jakarta EE baseline to generation 11. For new projects, check the Spring Boot, JDK, servlet container, validation provider, and test framework versions together; do not upgrade spring-webflux alone.

At the time of writing, official documentation lists Spring Framework 7.0.x and 6.2.x as stable branches; patch versions change over time. Use the official release/support page to confirm supported patches rather than copying a fixed version number from an old lesson.

### 8.5. Managing versions via Spring Boot BOM

In Spring Boot applications, prefer letting the Spring Boot BOM/dependency management select a compatible set of Spring Framework, Reactor, Jackson, validation provider, and test dependencies. Avoid pinning a spring-webflux version different from spring-core or spring-web.

If using standalone Gradle, manage all Spring Framework modules consistently at the same version. Check the dependency tree when encountering NoSuchMethodError, ClassNotFoundException, NoClassDefFoundError, or linkage errors after an upgrade.

## 9. A runnable Spring Boot WebFlux program

The example below uses Java 17 and Spring Boot 3.3.5, based on Spring Framework 6.1.x. It demonstrates:

- @PathVariable UUID and @RequestParam.
- Optional @RequestHeader and @CookieValue.
- @Valid @RequestBody with Jakarta Bean Validation.
- Method validation on query parameters since Spring 6.1.
- Return values Mono<ResponseEntity<T>>, Flux<T>, and Mono<ResponseEntity<Void>>.

### 9.1. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

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
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Versions are pinned so the example is reproducible; Spring Boot manages the compatible Spring Framework 6.1.x version. For new applications, choose a still-supported Spring Boot version and let the BOM manage dependencies.

### 9.2. src/main/java/demo/BindingDemoApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BindingDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(BindingDemoApplication.class, args);
    }
}
~~~

### 9.3. src/main/java/demo/OrderController.java

~~~java
package demo;

import java.net.URI;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.CookieValue;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

record CreateOrderRequest(
    @NotBlank String customer,
    @Min(1) @Max(100) int quantity
) {}

record OrderView(UUID id, String customer, int quantity) {}

@RestController
@RequestMapping("/api/orders")
class OrderController {

    private final ConcurrentMap<UUID, OrderView> orders =
        new ConcurrentHashMap<>();

    @GetMapping
    Flux<OrderView> list(
            @RequestParam(defaultValue = "20")
            @Min(1) @Max(100) int limit) {
        return Flux.fromIterable(orders.values())
            .take(limit);
    }

    @GetMapping("/{id}")
    Mono<ResponseEntity<OrderView>> get(
            @PathVariable UUID id,
            @RequestHeader(
                name = "X-Request-Id", required = false
            ) Optional<String> requestId,
            @CookieValue(
                name = "locale", required = false
            ) Optional<String> locale) {

        return Mono.justOrEmpty(orders.get(id))
            .map(order -> {
                ResponseEntity.BodyBuilder response =
                    ResponseEntity.ok();

                requestId.ifPresent(value ->
                    response.header("X-Request-Id", value));
                locale.ifPresent(value ->
                    response.header("Content-Language", value));

                return response.body(order);
            })
            .defaultIfEmpty(
                ResponseEntity.<OrderView>notFound().build()
            );
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    Mono<ResponseEntity<OrderView>> create(
            @Valid @RequestBody CreateOrderRequest request) {

        return Mono.fromSupplier(() -> {
            UUID id = UUID.randomUUID();
            OrderView saved = new OrderView(
                id, request.customer(), request.quantity()
            );
            orders.put(id, saved);

            return ResponseEntity
                .created(URI.create("/api/orders/" + id))
                .body(saved);
        });
    }

    @DeleteMapping("/{id}")
    Mono<ResponseEntity<Void>> delete(@PathVariable UUID id) {
        return Mono.fromSupplier(() -> {
            OrderView removed = orders.remove(id);
            return removed == null
                ? ResponseEntity.<Void>notFound().build()
                : ResponseEntity.noContent().build();
        });
    }
}
~~~

This is a demo application using an in-memory map, not a production persistence design. ConcurrentHashMap protects basic map operations under concurrent request access; it does not replace transactions/databases.

Note the list method: @Min and @Max placed directly on parameters are Spring 6.1+ method validation. The controller has no class-level @Validated, so built-in method validation can be used. @Valid on the body illustrates validation of an individual command object.

### 9.4. Running the application and trying calls

Start:

~~~bash
gradle bootRun
~~~

Or with the Gradle Wrapper:

~~~bash
./gradlew bootRun
~~~

On Windows:

~~~powershell
.\gradlew.bat bootRun
~~~

List up to 10 orders:

~~~bash
curl -i "http://localhost:8080/api/orders?limit=10"
~~~

Query an existing UUID:

~~~bash
curl -i \
  -H "X-Request-Id: req-42" \
  -H "Cookie: locale=vi" \
  http://localhost:8080/api/orders/00000000-0000-0000-0000-000000000001
~~~

The ID above is just a format example; the demo app generates a random UUID on POST, so use the ID received from the actual response.

Create a valid order:

~~~bash
curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{"customer":"Lan","quantity":3}'
~~~

The response body has a randomly generated UUID, so there is no fixed stdout for the whole command. A successful response has status 201 Created and a Location header.

Try invalid body validation:

~~~bash
curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{"customer":" ","quantity":0}'
~~~

With validation configured, the request is rejected before creating the order and usually returns 400 Bad Request.

Try method validation:

~~~bash
curl -i "http://localhost:8080/api/orders?limit=0"
~~~

limit=0 violates @Min(1), so method validation rejects the request. This is a Spring Framework 6.1+-dependent point in the example.

## 10. Testing with WebTestClient

Create src/test/java/demo/OrderControllerTest.java:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@WebFluxTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void invalidBodyIsRejected() {
        client.post()
            .uri("/api/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"customer\":\" \",\"quantity\":0}")
            .exchange()
            .expectStatus().isBadRequest();
    }

    @Test
    void methodConstraintRejectsInvalidLimit() {
        client.get()
            .uri("/api/orders?limit=0")
            .exchange()
            .expectStatus().isBadRequest();
    }

    @Test
    void invalidUuidCannotBindToPathVariable() {
        client.get()
            .uri("/api/orders/not-a-uuid")
            .exchange()
            .expectStatus().isBadRequest();
    }

    @Test
    void validEmptyListReturnsSuccess() {
        client.get()
            .uri("/api/orders?limit=10")
            .exchange()
            .expectStatus().isOk();
    }
}
~~~

Run:

~~~bash
gradle test
~~~

Or ./gradlew test / .\gradlew.bat test. The tests verify:

- Bean Validation on the request body.
- Method validation on the query parameter.
- Conversion of String to UUID.
- Return value Flux<OrderView> encoded into a JSON response.

@WebFluxTest creates a slice test for the controller. If the controller has service dependencies, provide appropriate mock beans or use @SpringBootTest with WebTestClient when full application context testing is needed.

## 11. Version and migration issues

### 11.1. javax.validation and jakarta.validation errors

Common symptoms when upgrading:

- ClassNotFoundException: javax.validation...
- NoClassDefFoundError: jakarta.validation...
- Validation provider not found or annotations not recognized.

How to handle:

- Spring 5.x usually uses javax.validation.*.
- Spring 6.x/7.x uses jakarta.validation.*.
- Choose a Hibernate Validator/provider compatible with the namespace.
- Let the Spring Boot BOM manage starter and provider versions.
- Do not let both namespaces appear mixed in DTOs/controllers without a clear reason.

### 11.2. Class-level @Validated in Spring 6.1+

If a controller has:

~~~java
@Validated
@RestController
class ProductController {
    // ...
}
~~~

method validation is performed via an AOP proxy. To use Spring Framework 6.1's built-in method validation for @RequestMapping controllers, remove class-level @Validated from the controller and use the built-in mechanism. If you need AOP method validation per the older design, actively configure MethodValidationPostProcessor and understand the proxy scope.

### 11.3. Do not use javax.servlet in WebFlux

Spring WebFlux uses reactive abstractions such as ServerWebExchange, ServerHttpRequest, and ServerHttpResponse. Servlet types such as HttpServletRequest are not standard WebFlux controller parameters. If an application uses both Spring MVC and WebFlux, you must identify the right web application type and programming model for each controller.

### 11.4. RxJava and reactive libraries

WebFlux uses Reactor Mono/Flux internally and can adapt to supported Reactive Streams publishers/libraries. RxJava 1/2 was deprecated in Spring Framework 5.3.11; for new code, prefer Reactor or RxJava 3 per the Spring version's compatibility matrix. Do not assume a type from an arbitrary reactive library is automatically supported without a corresponding adapter.

### 11.5. Kotlin coroutines

Spring Framework 5.2 added coroutine support for WebFlux annotated controllers, including suspend functions and Flow/Deferred in supported cases. This is a Kotlin feature and requires matching kotlinx-coroutines/Spring Kotlin support dependencies; it does not apply directly to Java controllers.

Illustrative Kotlin example:

~~~kotlin
@GetMapping("/orders/{id}")
suspend fun get(@PathVariable id: UUID): OrderView =
    orderService.findById(id)
~~~

This is a Kotlin snippet, not Java code. For streams, you can use Flow<T> via coroutine adapters supported by Spring.

## 12. Common mistakes and how to fix them

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using Mono<String> for a simple @RequestParam | Wrapper does not fit scalar argument resolvers | Use String, UUID, int, Optional<T> |
| Using HttpServletRequest in WebFlux | Wrong programming model and incompatible with standard handlers | Use ServerHttpRequest or ServerWebExchange |
| Confusing query parameters with form bodies | Cannot bind form data as expected | Use @ModelAttribute or form data APIs |
| Receiving a persistence entity directly via @ModelAttribute | Risk of mass assignment into sensitive fields | Use a request DTO and allowed fields |
| Thinking @Valid always triggers method validation | @Valid itself is not a constraint | Distinguish object validation from method-level constraints |
| Catching only WebExchangeBindException | Can miss HandlerMethodValidationException | Handle both when using Spring 6.1+ |
| Placing BindingResult far from the object | Spring does not attach errors to the right parameter | Place it immediately after the validated argument |
| Thinking Flux<T> always buffers the entire response | Can misunderstand streaming and memory | Check media type/codec; stream as needed |
| Using String thinking it is always body text | In @Controller, it can be a view name | Use @ResponseBody/@RestController when a body is needed |
| Returning Mono.empty() and expecting HTTP 404 always | Empty does not define a status on its own | Use switchIfEmpty, ResponseEntity, or exception mapping |
| Changing javax imports to jakarta without upgrading the provider | Linkage error or validation does not run | Align Spring, provider, and namespace |
| Using new method validation on Spring 6.0 | API/behavior does not exist in that version | Use a compatible AOP mechanism or upgrade to 6.1+ |
| Upgrading spring-webflux alone | Spring modules have mismatched versions | Use the Spring Boot BOM or manage versions consistently |
| Using class-level @Validated while expecting 6.1 built-in | Validation goes through an AOP proxy | Remove class-level @Validated when choosing built-in method validation |

## 13. Controller method design checklist

Before writing a controller signature, ask yourself:

1. **Where is the data source?** Path, query, header, cookie, body, multipart, session, or request attribute?
2. **What is the appropriate Java type?** Scalar value, Optional<T>, DTO, Mono<T>, or Flux<T>?
3. **Is conversion needed?** Do UUID, date-time, enum, and custom types have suitable converters/formatters?
4. **Which codec does the body use?** Are Content-Type, DTO, HttpMessageReader, streaming, and size appropriate?
5. **At what level is validation?** @Valid for objects, direct constraints for methods, BindingResult, or exception handler?
6. **Does the Spring version support it?** Especially the javax/jakarta namespace, built-in method validation, and reactive argument types.
7. **Does the return value match the HTTP contract?** Body, status, headers, view, stream, SSE, or completion-only?
8. **Is there a risk of blocking threads?** Do not call block() or subscribe() manually in a handler to wait for/trigger work.
9. **Can the response fail after committing?** If streaming, define how the client should handle partial responses.
10. **Have binding and version-specific behavior been tested?** Use WebTestClient to check conversion, validation, status, headers, content type, and response body.

**Remember:** method arguments describe how Spring retrieves and converts request data; return values describe how Spring writes the body, status, headers, stream, or view. Mono/Flux are used in positions suited to reactive I/O, not to wrap every parameter. When upgrading Spring, pay special attention to the JDK baseline, javax/jakarta, and method validation changes since 6.1.

## References

- Spring Framework — WebFlux Handler Methods: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods.html
- Spring Framework — Method Arguments: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/arguments.html
- Spring Framework — Return Values: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html
- Spring Framework — Validation in WebFlux: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-validation.html
- Spring Framework — WebFlux Configuration and Validators: https://docs.spring.io/spring-framework/reference/web/webflux/config.html
- Spring Framework 5.3 — Web on Reactive Stack: https://docs.spring.io/spring-framework/docs/5.3.x/reference/html/web-reactive.html
- Spring Framework 6.0 Release Notes: https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-6.0-Release-Notes
- Spring Framework 7.0 Release Notes: https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-7.0-Release-Notes
- Spring Framework Versions and Support: https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-Versions
