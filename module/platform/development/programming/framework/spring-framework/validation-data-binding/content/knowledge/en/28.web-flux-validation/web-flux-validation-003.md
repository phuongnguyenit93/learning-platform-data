# Converting Query, Path, Header, and Form Data in Spring WebFlux

## 1. The Big Picture: All Are HTTP Strings, Different Data Sources

In **Spring WebFlux** (the reactive web stack), an HTTP request can pass data to a handler through several places:

- **Query parameters**: `GET /orders?size=20&active=true`.
- **Path variables**: `GET /orders/123` with route `/orders/{id}`.
- **Request headers**: `X-Retry: 2`, `Accept-Language: vi-VN`.
- **Form fields** in an `application/x-www-form-urlencoded` body: `name=Lan&age=26`.
- **Multipart form**: text fields and file parts in `multipart/form-data`.

For a handler to receive Java types like `int`, `long`, `UUID`, `boolean`, `LocalDate`, `enum`, or a form DTO, WebFlux needs two steps: **select the right data source** and then **convert raw strings/values into the target type** using `ConversionService`, `Converter`, `Formatter`, or WebFlux data binding.

The easiest mistake when coming from Spring MVC: **in WebFlux, `@RequestParam` only reads query parameters**. Servlet MVC has a request parameter map that merges query, form, and possibly multipart; WebFlux **separates** them on `ServerWebExchange`. To bind query, form, and multipart into a command object, use `@ModelAttribute`/data binding; to read form data directly, use `ServerWebExchange#getFormData()`. That is the explicitly documented contract of Spring WebFlux, not behavior inferred from Spring MVC.

HTTP example:

~~~http
POST /api/convert/form-query?name=Mai
Content-Type: application/x-www-form-urlencoded

name=Lan&age=26
~~~

In WebFlux, `@RequestParam("name")` receives `"Mai"` from the **query**. `exchange.getFormData()` receives `"Lan"` from the **form body**. Do not assume both sources are automatically merged into one map like servlet request parameters.

## 2. Annotation/API Selection Table by Source

| HTTP Source | WebFlux Annotation or API | Convertible Target Types | Notes |
| --- | --- | --- | --- |
| Query `?page=3` | `@RequestParam("page") int page` | String → int, enum, UUID, list... | **Query only**, does not automatically read form body. |
| Path `/orders/{id}` | `@PathVariable("id") UUID id` | String → UUID | Must match route template; missing/wrong type usually leads to 4xx. |
| Header `X-Retry: 2` | `@RequestHeader("X-Retry") int retry` | String → int, enum, collection... | Client-sent header, not implicitly trustworthy. |
| Cookie `sessionHint=...` | `@CookieValue("sessionHint") String hint` | String → supported types | Use dedicated annotation; do not confuse with header/query. |
| Form-urlencoded | `@ModelAttribute FormDto form` or `exchange.getFormData()` | Fields → bean properties/constructor args; or `MultiValueMap<String,String>` | `getFormData()` returns `Mono<MultiValueMap<String,String>>`. |
| Multipart | `@ModelAttribute FormDto` or `@RequestPart("file") FilePart`; `exchange.getMultipartData()` | Form fields, `FilePart`/`Part` | `FilePart` differs from Servlet MVC's `MultipartFile`. |
| JSON body | `@RequestBody Dto dto` or `Mono<Dto>` | JSON → DTO via `HttpMessageReader`/codec | **Not** `@RequestParam` property binding. |
| Raw request context | `ServerWebExchange` | Query `MultiValueMap`, headers, path, reactive form/multipart | Use when fine-grained source control is needed. |

A handler can combine sources:

~~~java
@GetMapping("/orders/{id}")
String detail(@PathVariable UUID id,
              @RequestParam(defaultValue = "1") int page,
              @RequestHeader(name = "X-Retry",
                             defaultValue = "0") int retry) {
    return id + "|" + page + "|" + retry;
}
~~~

This is a **snippet** that belongs inside an `@RestController` with imports. WebFlux resolves each argument separately: `id` comes from path, `page` from query, `retry` from header; then conversion runs for each type. They do not all read from a single parameter map.

## 3. `@RequestParam`: Converting **Query Parameters** in WebFlux

Suppose the URL is:

~~~http
GET /search?keyword=spring&page=3&active=true&tag=java&tag=reactor
~~~

Handler:

~~~java
@GetMapping("/search")
String search(
        @RequestParam String keyword,
        @RequestParam(defaultValue = "1") int page,
        @RequestParam(defaultValue = "false") boolean active,
        @RequestParam(name = "tag", required = false)
                List<String> tags) {

    return keyword + ":" + page + ":" + active + ":" + tags;
}
~~~

This is a snippet in a controller with `List` imported. `keyword` is a string, `page` is converted to `int`, `active` to `boolean`, and `tags` can receive repeated values. For the request above, the logic returns something like `spring:3:true:[java, reactor]` via `List#toString()` on the sample data. Repeated values should not be collapsed to the first value if business logic needs all of them.

### `required`, `defaultValue`, and `Optional`

- `@RequestParam("page") int page`: by default `required=true`; if missing, the handler does not run and WebFlux typically returns HTTP 400.
- `@RequestParam(name="page", required=false) Integer page`: allows absence, usually receiving null. Use a wrapper instead of a primitive when absence is meaningful.
- `@RequestParam(defaultValue="1") int page`: sets a fallback value; declaring a default also makes the parameter optional.
- `@RequestParam Optional<Integer> page`: expresses presence/absence; requires importing `java.util.Optional`.
- When an empty string is converted to null (such as `UUID` or wrapper types depending on the converter), Spring may treat it as a missing value. Set `required=false` or use a nullable type when the contract allows it.

A clear pattern for pagination:

~~~java
@GetMapping("/products")
String products(@RequestParam(defaultValue = "0") int page,
                @RequestParam(defaultValue = "20") int size) {
    return "page=" + page + ", size=" + size;
}
~~~

Converting to `int` **does not automatically guarantee** `page >= 0` or `size <= 100`. Business validation/range checks are needed if limits apply. Do not equate *type conversion* with *validation*.

### Mapping multiple query parameters

`@RequestParam MultiValueMap<String,String> params` (without specifying a name) can capture all query values, including repeated keys. `Map<String,String>` fits when only one value per key is needed. Use `MultiValueMap` for repeated tags/filters or when element counts matter. Do not manually parse URLs with `split("&")` because percent-encoding and special characters should be handled by the framework.

## 4. `@PathVariable`: Converting Path Segments to Java Types

Sample route:

~~~java
@GetMapping("/orders/{orderId}")
String order(@PathVariable("orderId") UUID id) {
    return "ORDER:" + id;
}
~~~

Request:

~~~http
GET /orders/123e4567-e89b-12d3-a456-426614174000
~~~

WebFlux extracts `{orderId}` from the matched route, and `ConversionService` converts `String` to `java.util.UUID`. The name in `@PathVariable("orderId")` is the **template variable name**, while the Java parameter name `id` can differ. Only omit the name in `@PathVariable UUID id` when you are certain parameter names are compiled/discovered properly.

Cases:

- `/orders/not-a-uuid`: the route may still match the path segment, but conversion fails → typically HTTP 400.
- `/orders/`: **does not match** `/orders/{orderId}`; typically HTTP 404, not an "invalid UUID" error from that handler.
- `/orders/123?orderId=xyz`: the path variable comes from the **path**, not overridden by a query parameter of the same name.
- For a date path segment, use `@DateTimeFormat(iso = DateTimeFormat.ISO.DATE)` on `LocalDate` to specify the format.

Date example:

~~~java
@GetMapping("/calendar/{day}")
String calendar(
        @PathVariable("day")
        @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
        LocalDate day) {
    return "DAY:" + day;
}
~~~

`/calendar/2026-11-06` creates `LocalDate.of(2026,11,6)`. `/calendar/not-a-date` fails ISO date conversion → HTTP 400 with default configuration. Use `@DateTimeFormat`/formatters instead of manually splitting year, month, and day strings in the handler.

Note that route matching and conversion are **two steps**: the path must match the mapping first, and only then is the argument converted. Having a `UUID` or `int` path variable type does not automatically turn the route into a regular expression.

## 5. `@RequestHeader`: Headers Are a Separate Source, Still Convertible

Example request:

~~~http
GET /api/convert/orders/123e4567-e89b-12d3-a456-426614174000?page=3
X-Retry: 2
Accept-Language: vi-VN,vi;q=0.9
~~~

Handler:

~~~java
@GetMapping("/retry")
String retry(@RequestHeader(name = "X-Retry",
                            defaultValue = "0") int attempts) {
    return "retry=" + attempts;
}
~~~

`X-Retry: 2` is converted to `int` by the configured conversion service. `X-Retry: abc` cannot be converted to `int`, typically resulting in HTTP 400 when argument resolution fails.

You can declare `@RequestHeader("Accept") List<String> types`; Spring can split comma-separated header strings into arrays/collections when supported by type converters. If you need all headers, use `@RequestHeader HttpHeaders headers` or `ServerWebExchange#getRequest().getHeaders()`. For multi-valued headers, `HttpHeaders#getValuesAsList("Accept")` and `get("Accept")` have distinct semantics; never assume a header line always holds only one value.

**Security note:** headers can be set or altered by browsers, clients, CDNs, or reverse proxies. Do not rely on a custom header like `X-User-Id` to verify identity without a trusted boundary and authentication mechanism. `@RequestHeader` only reads and converts; it does not determine whether a header is trustworthy. Headers are not automatically treated as query or form data.

### Request attributes and cookies are not header binding

- `@CookieValue` reads a cookie by name; cookies travel in the HTTP Cookie header but have their own annotation.
- `@RequestAttribute` retrieves an attribute already placed on the request exchange by a server-side filter/interceptor; it is not a client-sent parameter.
- `@RequestHeader` does not need `@ModelAttribute` to convert individual values.

## 6. Form Data in WebFlux: `@ModelAttribute` and `getFormData()`

### 6.1. Do not confuse the form body with the query map

In Servlet MVC, `HttpServletRequest#getParameterMap()` merges query/form per the Servlet API. In Spring WebFlux:

~~~java
MultiValueMap<String, String> query =
        exchange.getRequest().getQueryParams();

Mono<MultiValueMap<String, String>> form =
        exchange.getFormData();
~~~

This is a snippet inside a method with `ServerWebExchange exchange` and appropriate imports, not a standalone file. The two sources are **separate**:

- `getQueryParams()`: values on the URL, immediately available as `MultiValueMap<String,String>`.
- `getFormData()`: `application/x-www-form-urlencoded` content parsed by `FormHttpMessageReader`, returning **`Mono<MultiValueMap<String,String>>`**. The result may be cached by WebFlux for subsequent reads through the form data API.
- `getMultipartData()`: multipart data, returning `Mono<MultiValueMap<String,Part>>`. Do not use `getFormData()` to retrieve file parts.
- In reactive code, chain `.map(...)`, `.flatMap(...)`, or return `Mono` to the WebFlux subscriber; **never call `.block()` inside a handler on the event loop** to force synchronous form reading.

Example handler reading both sources explicitly:

~~~java
@PostMapping(path = "/form-query",
             consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
Mono<String> compare(
        @RequestParam(name = "name", required = false)
        String queryName,
        ServerWebExchange exchange) {

    return exchange.getFormData().map(values -> {
        String query = queryName == null ? "none" : queryName;
        String formName = values.getFirst("name");
        return "QUERY:" + query + "|FORM:" + formName;
    });
}
~~~

This is a snippet inside `@RestController`; the full runnable example is in section 9. With URL `/form-query?name=Mai` and body `name=Lan`, the output is **`QUERY:Mai|FORM:Lan`**. Without query `name`, the output is **`QUERY:none|FORM:Lan`**. Understanding this difference prevents bugs when porting MVC code to WebFlux.

**Do not mix multiple ways of consuming the raw body**: once the body has been decoded/cached as form data, do not try to read the raw `Flux<DataBuffer>` a second time expecting it to remain intact for another parser. Choose one clear pipeline.

### 6.2. `@ModelAttribute` binds a form into a command object

When you want multiple typed fields bound into a form object:

~~~java
@PostMapping("/form")
ResponseEntity<?> save(
        @Valid @ModelAttribute("registration") RegistrationForm form,
        BindingResult result) {

    if (result.hasErrors()) {
        return ResponseEntity.badRequest().body("FORM_INVALID");
    }
    return ResponseEntity.ok("OK");
}
~~~

This is a controller snippet, not a standalone program. `@ModelAttribute` in WebFlux can bind **form data, query parameters, URI path variables, and request headers** into a model object. According to the docs, **form and query parameters take precedence over URI variables and headers**; URI/header values are only added when they do not override input parameters of the same name. Header names may be normalized by stripping hyphens.

`WebDataBinder` performs constructor/property binding using conversion services and formatters. Nested paths like `address.city` and `items[0].quantity` can be resolved if the target/property paths and binder settings permit them.

Place `BindingResult` **immediately after** `@ModelAttribute` (with no other parameter in between) if you want to handle errors directly. For `age=abc` when property `age` is Integer, Spring can create a `FieldError` with code `typeMismatch` in `BindingResult`. With `@Valid` and DTO constraints, Bean Validation errors also go into `BindingResult`. If unhandled locally, WebFlux usually throws **`WebExchangeBindException`** and responds with HTTP 400.

**Reactive wrapper:** Spring WebFlux also supports `@ModelAttribute Mono<Form>` in appropriate contexts, but if you want an adjacent `BindingResult` parameter, the model attribute should be declared without wrapping in `Mono`. With the reactive form, errors should be handled inside the pipeline rather than via an adjacent `BindingResult`.

### 6.3. `@ModelAttribute` with query/path/headers also needs a source policy

Suppose `@PostMapping("/orders/{ownerId}/update")` has a form object containing `ownerId` and `name`. WebFlux can populate `ownerId` from the URI variable if request values do not already supply that name. However, if a client can send `ownerId` in the form or query, the request value may take precedence. **Never use a form-bound ownerId as proof that the client is authorized to modify that resource.** Obtain the owner identity from the authentication context and check permissions separately.

Similarly, an `X-Role: ADMIN` header is not a source of truth for updating a role property. Use a dedicated DTO and field whitelist.

### 6.4. Form field markers/defaults and nested properties

`WebDataBinder` supports HTML checkbox markers like `_subscribed` when a checkbox is unchecked, as well as field defaults like `!age`. With a form:

~~~html
<input type="hidden" name="_newsletter" value="present">
<input type="checkbox" name="newsletter" value="true">
~~~

If the user unchecks the checkbox, only the marker is submitted; the binder can reset the boolean field to `false` instead of retaining an old value. This is a feature of **data binding**, and does not apply similarly to a query-only `@RequestParam boolean`. Markers are not security controls; clients can easily forge form names and values.

## 7. Multipart in WebFlux Differs from Servlet MVC

For uploads via `multipart/form-data`:

- WebFlux uses `org.springframework.http.codec.multipart.Part` and `FilePart` (not Servlet `MultipartFile`).
- `@RequestPart("file") FilePart file` receives the named part.
- An `@ModelAttribute` command object can contain `FilePart` alongside form fields.
- `ServerWebExchange#getMultipartData()` returns `Mono<MultiValueMap<String, Part>>`.
- `@RequestPart("metadata") Metadata metadata` can use a message reader/codec to deserialize a JSON part based on the part's Content-Type.

Upload snippet:

~~~java
@PostMapping(path = "/files",
             consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
Mono<String> upload(@RequestPart("file") FilePart file) {
    // Here we only illustrate the file name; production must handle content safely.
    return Mono.just("FILE:" + file.filename());
}
~~~

This example does not save the file; it is an illustrative controller snippet. **Do not treat `file.filename()` as a trusted path** and never concatenate it directly into a filesystem save path. You must validate/limit size, file type, run content scanning, handle streams, and release DataBuffers according to contract.

If you only need URL-encoded text fields, use `getFormData()`, not multipart. For a pure JSON body, `@RequestBody` goes through `HttpMessageReader`, not `@ModelAttribute`/query conversion. With `@Valid @RequestBody`, validation failures typically produce `WebExchangeBindException`; JSON syntax parsing errors belong to the message-reading step.

## 8. ConversionService, Formatter, and Converter: How Type Conversion Works

### 8.1. Automatic conversion for single arguments

`@RequestParam`, `@PathVariable`, `@RequestHeader`, `@CookieValue`, and other text-based arguments can all be converted by Spring WebFlux from `String` to target Java types. Basic types like `int`, `long`, `boolean`, enums, or `UUID` have built-in conversions depending on registration/configuration.

Example:

~~~java
@GetMapping("/demo/{id}")
String demo(@PathVariable UUID id,
            @RequestParam int count,
            @RequestHeader("X-Retry") Integer retry) {
    return id + "|" + count + "|" + retry;
}
~~~

`UUID` requires a valid string; `count=not-an-integer` or `X-Retry: abc` causes a type conversion failure and typically HTTP 400. You do not need `Integer.parseInt`/`UUID.fromString` in the controller when a conversion service is active.

### 8.2. Date/time formatting with `@DateTimeFormat`

For HTML form or path/query dates, specifying ISO explicitly:

~~~java
@GetMapping("/calendar/{day}")
String calendar(@PathVariable("day")
                @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
                LocalDate day) {
    return "DAY:" + day;
}
~~~

`@DateTimeFormat` affects how Spring converts **textual request values** into Java date/time types; if the value is inside a **JSON body**, mapping is primarily handled by codecs/Jackson and its serializer/deserializer configuration, not necessarily the same WebDataBinder formatter.

### 8.3. Custom Converter for enum aliases

Suppose the client sends `level=exp` while the backend expects `ShippingLevel.EXPRESS`. Instead of comparing strings in every handler, register `Converter<String,ShippingLevel>` via `WebFluxConfigurer#addFormatters(FormatterRegistry)`:

~~~java
@Override
public void addFormatters(FormatterRegistry registry) {
    registry.addConverter(String.class, ShippingLevel.class,
            text -> switch (text.trim().toLowerCase(Locale.ROOT)) {
                case "standard", "std" -> ShippingLevel.STANDARD;
                case "express", "exp" -> ShippingLevel.EXPRESS;
                default -> throw new IllegalArgumentException(
                        "Unsupported shipping level");
            });
}
~~~

This is a snippet inside `WebFluxConfigurer`; the full source is in section 9. Once registered, handlers can declare `@RequestParam ShippingLevel level` and Spring applies the converter. If the user enters an unknown value, the converter signals a conversion error, and WebFlux usually returns 400 (not 500 when argument resolution recognizes the conversion failure).

**Do not overuse global converters:** a converter applies across every place needing `ShippingLevel`. If an alias belongs to only one endpoint, consider adjusting the input contract or using a scoped DTO/formatter. Converters should be stateless, deterministic, and never perform blocking I/O.

### 8.4. `@InitBinder` vs `WebFluxConfigurer`

- `WebFluxConfigurer#addFormatters`: registers converters/formatters across the WebFlux conversion service; suitable for standardizing type conversion across controllers.
- `@InitBinder` in `@Controller`/`@ControllerAdvice`: customizes `WebDataBinder` for matching model objects/arguments, such as `setAllowedFields` or custom editors.
- `Validator`/`@Valid`: validates **values after conversion**; it is not responsible for parsing text.
- `HttpMessageReader`/codec: reads **JSON bodies, raw bodies, multipart parts**; the same JSON DTO may follow different mapping rules than a form binder.

Under Spring WebFlux config, number and date/time formatters are registered by default in many cases; they can be customized via `@DateTimeFormat` and `addFormatters`. Be explicit about locale/time zone when dates include zones, and test across real locales.

## 9. Complete Java 17+ and Spring Boot WebFlux Example: Query, Path, Header, Form

This example targets a **Spring Boot 3.x**, **Java 17+**, Maven project using **Spring WebFlux only** (do not add `spring-boot-starter-web` to avoid accidentally selecting Servlet MVC). With a Spring Boot parent/BOM, add these dependencies to `pom.xml`:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Create the files in package `com.example.webfluxbinding` with the exact names below. Ensure the Spring Boot Maven plugin is configured in a standard project and use consistent dependencies managed by the Boot BOM.

### 9.1. `WebFluxBindingApplication.java`

File `src/main/java/com/example/webfluxbinding/WebFluxBindingApplication.java`:

~~~java
package com.example.webfluxbinding;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebFluxBindingApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebFluxBindingApplication.class, args);
    }
}
~~~

### 9.2. `ShippingLevel.java`

File `src/main/java/com/example/webfluxbinding/ShippingLevel.java`:

~~~java
package com.example.webfluxbinding;

public enum ShippingLevel {
    STANDARD,
    EXPRESS
}
~~~

### 9.3. `WebFluxConversionConfig.java`

File `src/main/java/com/example/webfluxbinding/WebFluxConversionConfig.java`:

~~~java
package com.example.webfluxbinding;

import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.reactive.config.WebFluxConfigurer;

import java.util.Locale;

@Configuration
public class WebFluxConversionConfig implements WebFluxConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(
                String.class,
                ShippingLevel.class,
                value -> switch (
                        value.trim().toLowerCase(Locale.ROOT)) {
                    case "standard", "std" -> ShippingLevel.STANDARD;
                    case "express", "exp" -> ShippingLevel.EXPRESS;
                    default -> throw new IllegalArgumentException(
                            "Unsupported shipping level: " + value);
                });
    }
}
~~~

In real applications, consider omitting raw input from exceptions/logs if the input could be sensitive; `ShippingLevel` is a non-sensitive enum example. The converter holds no mutable state so it can be shared safely. `WebFluxConfigurer` and `@Configuration` are picked up by Spring Boot WebFlux at startup.

### 9.4. `RegistrationForm.java`

File `src/main/java/com/example/webfluxbinding/RegistrationForm.java`:

~~~java
package com.example.webfluxbinding;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class RegistrationForm {

    @NotBlank
    private String name;

    @NotNull
    @Min(18)
    private Integer age;

    private boolean newsletter;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public Integer getAge() {
        return age;
    }

    public void setAge(Integer age) {
        this.age = age;
    }

    public boolean isNewsletter() {
        return newsletter;
    }

    public void setNewsletter(boolean newsletter) {
        this.newsletter = newsletter;
    }
}
~~~

`@NotBlank` and `@NotNull @Min(18)` are **validation**; they do not convert String to Integer themselves. `WebDataBinder` runs conversion first; if `age=abc`, a binding error can occur before the age constraint is evaluated.

### 9.5. `WebFluxBindingController.java`

File `src/main/java/com/example/webfluxbinding/WebFluxBindingController.java`:

~~~java
package com.example.webfluxbinding;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

import java.time.LocalDate;
import java.util.UUID;

@RestController
@RequestMapping("/api/convert")
public class WebFluxBindingController {

    @GetMapping("/orders/{orderId}")
    public String order(
            @PathVariable("orderId") UUID id,
            @RequestParam("page") int page,
            @RequestParam(name = "active",
                          defaultValue = "false") boolean active,
            @RequestHeader(name = "X-Retry",
                           defaultValue = "0") int retry) {

        return "ORDER:" + id
                + "|page=" + page
                + "|active=" + active
                + "|retry=" + retry;
    }

    @GetMapping("/day/{day}")
    public String day(
            @PathVariable("day")
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
            LocalDate day) {

        return "DAY:" + day;
    }

    @GetMapping("/shipping")
    public String shipping(
            @RequestParam("level") ShippingLevel level) {
        return "LEVEL:" + level;
    }

    @PostMapping(path = "/form-query",
                 consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public Mono<String> compareFormAndQuery(
            @RequestParam(name = "name", required = false)
            String queryName,
            ServerWebExchange exchange) {

        // @RequestParam: reads only the URL query string.
        // getFormData(): reads the form-urlencoded body separately.
        return exchange.getFormData().map(values -> {
            String query = queryName == null
                    ? "none" : queryName;
            return "QUERY:" + query
                    + "|FORM:" + values.getFirst("name");
        });
    }

    @InitBinder("registration")
    public void configureRegistrationBinder(WebDataBinder binder) {
        binder.setAllowedFields("name", "age", "newsletter");
    }

    @PostMapping(path = "/form",
                 consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<String> form(
            @Valid @ModelAttribute("registration")
            RegistrationForm registration,
            BindingResult result) {

        if (result.hasErrors()
                || result.getSuppressedFields().length != 0) {
            return ResponseEntity.badRequest()
                    .body("FORM_INVALID");
        }

        return ResponseEntity.ok(
                "FORM:" + registration.getName()
                + ":" + registration.getAge()
                + ":" + registration.isNewsletter());
    }

    @PostMapping(path = "/json",
                 consumes = MediaType.APPLICATION_JSON_VALUE)
    public String json(
            @Valid @RequestBody JsonRegistration body) {
        return "JSON:" + body.name() + ":" + body.age();
    }

    public record JsonRegistration(
            @NotBlank String name,
            @NotNull @Min(18) Integer age) {
    }
}
~~~

Key highlights of the program:

1. `order` receives three sources: `id` from the route template, `page`/`active` from the query, and `X-Retry` from the header; all typed parameters are converted by Spring before invoking the method body.
2. `day` illustrates `@DateTimeFormat` on a path variable, without manual `LocalDate` parsing.
3. `shipping` uses the custom `String → ShippingLevel` converter: clients can send `level=exp` and the handler receives `ShippingLevel.EXPRESS`.
4. `compareFormAndQuery` proves `@RequestParam` **does not** read the WebFlux form body, while `getFormData()` reads form data **asynchronously** without `block()`.
5. `form` receives `RegistrationForm` via `@ModelAttribute`. `@InitBinder` allows only three fields; `BindingResult` immediately after the form captures conversion/validation errors. The method explicitly returns 400 if there are errors or suppressed fields.
6. `json` uses **`@RequestBody` and an HTTP message reader**; the `JsonRegistration` record is a separate request DTO, unaffected by form property-binding whitelists.
7. `@RestController` writes returned `String` values to the response body. Examples return plain text so tests clearly show the data source, rather than using template views.

**Why import `@Min` in the controller?** It is only for the annotation on the `JsonRegistration` record. There is no direct `@Min` constraint on `@RequestParam page` in this demo so that type conversion is not mixed with method validation; if `page >= 1` is required, design and test validation separately.

## 10. WebTestClient Testing: Observable Results

Create `src/test/java/com/example/webfluxbinding/WebFluxBindingApplicationTest.java`:

~~~java
package com.example.webfluxbinding;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class WebFluxBindingApplicationTest {

    private static final String ID =
            "123e4567-e89b-12d3-a456-426614174000";

    @Autowired
    WebTestClient client;

    @Test
    void convertsPathQueryAndHeader() {
        client.get()
                .uri("/api/convert/orders/" + ID
                        + "?page=3&active=true")
                .header("X-Retry", "2")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("ORDER:" + ID
                        + "|page=3|active=true|retry=2");
    }

    @Test
    void usesDefaultsWhenOptionalQueryAndHeaderMissing() {
        client.get()
                .uri("/api/convert/orders/" + ID + "?page=1")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("ORDER:" + ID
                        + "|page=1|active=false|retry=0");
    }

    @Test
    void missingRequiredQueryIsBadRequest() {
        client.get()
                .uri("/api/convert/orders/" + ID)
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void invalidPathUuidIsBadRequest() {
        client.get()
                .uri("/api/convert/orders/not-a-uuid?page=1")
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void invalidHeaderNumberIsBadRequest() {
        client.get()
                .uri("/api/convert/orders/" + ID + "?page=1")
                .header("X-Retry", "not-a-number")
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void convertsIsoDateFromPath() {
        client.get()
                .uri("/api/convert/day/2026-11-06")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("DAY:2026-11-06");
    }

    @Test
    void invalidDateIsBadRequest() {
        client.get()
                .uri("/api/convert/day/not-a-date")
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void customConverterHandlesAlias() {
        client.get()
                .uri("/api/convert/shipping?level=exp")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("LEVEL:EXPRESS");
    }

    @Test
    void unsupportedEnumValueIsBadRequest() {
        client.get()
                .uri("/api/convert/shipping?level=unknown")
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void requestParamDoesNotReadFormBody() {
        client.post()
                .uri("/api/convert/form-query")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData("name", "Lan"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("QUERY:none|FORM:Lan");
    }

    @Test
    void queryAndFormSameKeyStaySeparate() {
        client.post()
                .uri("/api/convert/form-query?name=Mai")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData("name", "Lan"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("QUERY:Mai|FORM:Lan");
    }

    @Test
    void bindsValidFormToModelAttribute() {
        client.post()
                .uri("/api/convert/form")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData("name", "Lan")
                        .with("age", "26")
                        .with("newsletter", "true"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("FORM:Lan:26:true");
    }

    @Test
    void badFormNumberIsHandledViaBindingResult() {
        client.post()
                .uri("/api/convert/form")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData("name", "Lan")
                        .with("age", "not-a-number"))
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody(String.class)
                .isEqualTo("FORM_INVALID");
    }

    @Test
    void disallowedFormFieldIsRejected() {
        client.post()
                .uri("/api/convert/form")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData("name", "Lan")
                        .with("age", "26")
                        .with("admin", "true"))
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody(String.class)
                .isEqualTo("FORM_INVALID");
    }

    @Test
    void jsonUsesMessageReaderInsteadOfFormBinder() {
        client.post()
                .uri("/api/convert/json")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                        {"name":"Lan","age":26}
                        """)
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("JSON:Lan:26");
    }

    @Test
    void invalidJsonDtoIsBadRequest() {
        client.post()
                .uri("/api/convert/json")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                        {"name":"","age":16}
                        """)
                .exchange()
                .expectStatus().isBadRequest();
    }
}
~~~

Run from the root of the Maven project:

~~~bash
./mvnw test -Dtest=WebFluxBindingApplicationTest
~~~

On Windows use `mvnw.cmd test -Dtest=WebFluxBindingApplicationTest`; if Maven is installed you can use `mvn test -Dtest=WebFluxBindingApplicationTest`. With Spring Boot 3.x WebFlux, Bean Validation, and the test starter set up as above, **16 tests are designed to pass**. They verify actual handler HTTP statuses and application-returned bodies without relying on Spring's default error text.

Summary of key outcomes:

| Input | HTTP status | Expected Application Result |
| --- | --- | --- |
| `/orders/{UUID}?page=3&active=true`, `X-Retry: 2` | 200 | `ORDER:{UUID}|page=3|active=true|retry=2` |
| `/orders/{UUID}?page=1` without optional values | 200 | `active=false|retry=0` |
| Missing `page` | 400 | Required query parameter error. |
| Malformed path UUID | 400 | Path conversion error. |
| Non-numeric `X-Retry` header | 400 | Header conversion error. |
| `/day/2026-11-06` | 200 | `DAY:2026-11-06` |
| Non-ISO date | 400 | Date conversion error. |
| `/shipping?level=exp` | 200 | `LEVEL:EXPRESS` |
| `/shipping?level=unknown` | 400 | Custom converter rejects unknown alias. |
| POST form body `name=Lan`, no query name | 200 | `QUERY:none|FORM:Lan` |
| POST query `name=Mai` and form `name=Lan` | 200 | `QUERY:Mai|FORM:Lan` |
| POST valid form `name=Lan&age=26&newsletter=true` | 200 | `FORM:Lan:26:true` |
| POST form `age=not-a-number` | 400 | `FORM_INVALID` via BindingResult. |
| POST form with `admin=true` outside allowlist | 400 | `FORM_INVALID` due to suppressed field. |
| POST valid JSON | 200 | `JSON:Lan:26` |
| POST JSON violating `@NotBlank`/`@Min` | 400 | `WebExchangeBindException` handled by default. |

**Scope limitations:** tests use default Spring Boot WebFlux settings without Spring Security. Adding CSRF, authentication, custom `@ControllerAdvice`, or codec configuration may require updating status/response assertions. To test a controller in isolation without opening a port, you can also use `WebTestClient.bindToController(...)` or `bindToApplicationContext(...)` as needed; here the integration test uses `RANDOM_PORT` to exercise the full WebFlux path.

### Sending real requests with curl

When running the app with `./mvnw spring-boot:run`:

~~~bash
curl -i "http://localhost:8080/api/convert/orders/123e4567-e89b-12d3-a456-426614174000?page=3&active=true" \
  -H "X-Retry: 2"

curl -i -X POST "http://localhost:8080/api/convert/form-query?name=Mai" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "name=Lan"

curl -i -X POST "http://localhost:8080/api/convert/form" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "name=Lan&age=26&newsletter=true"

curl -i "http://localhost:8080/api/convert/shipping?level=exp"
~~~

These are Unix shell examples. On PowerShell, use `curl.exe` and adjust quoting/line continuation; do not use old PowerShell's `curl` alias assuming it supports GNU curl flags.

## 11. Error Handling: Conversion vs Validation vs Body Reading

Not all HTTP 400 responses share the same root cause:

| Error | Location in WebFlux Pipeline | Typical Manifestation |
| --- | --- | --- |
| Missing required query `page` | `@RequestParam` argument resolution | 400, exception in input/required value category. |
| Path `{id}` fails UUID conversion | `ConversionService`/argument resolver | 400, type conversion error. |
| Header `X-Retry: abc` → `int` | `ConversionService`/argument resolver | 400, type conversion error. |
| Form `age=abc` → Integer | `WebDataBinder`/`BindingResult` | Field error `typeMismatch`; controller receives `BindingResult` or `WebExchangeBindException`. |
| Form object fails `@NotBlank` | Bean Validation on `@ModelAttribute` | `WebExchangeBindException` if not handled locally. |
| Malformed JSON body | `HttpMessageReader`/JSON codec | HTTP body read/decode error before Bean Validation has an object. |
| JSON deserializes cleanly but `@Valid` fails | Validation on `@RequestBody` | `WebExchangeBindException`, typically HTTP 400. |
| Method has direct constraints on parameters/return | Method validation | Possibly `HandlerMethodValidationException` depending on signature/Spring version. |
| No handler matches path | Route matching | 404, distinct from conversion failure on a matched path variable. |

Local form error handling example:

~~~java
@PostMapping("/form")
ResponseEntity<String> submit(
        @Valid @ModelAttribute RegistrationForm form,
        BindingResult result) {

    if (result.hasErrors()) {
        result.getFieldErrors().forEach(error ->
                System.out.println(error.getField()
                        + ":" + error.getCode()));
        return ResponseEntity.badRequest()
                .body("FORM_INVALID");
    }

    return ResponseEntity.ok("OK");
}
~~~

This is a snippet needing appropriate imports and DTO, not a second method with the same mapping in the demo. In production use a structured logger instead of printing raw output. Do not return `FieldError#getRejectedValue()` to clients when a field may contain passwords, tokens, emails, or sensitive data.

### Why should `@RequestParam` not be used to read forms?

Because in WebFlux, query parsing is separated from `getFormData()`. If an app migrates from MVC to WebFlux assuming "`@RequestParam` always receives form fields", endpoints may receive null or report a missing required parameter even when the body contains the field. Fix this by using `@ModelAttribute` for form DTOs or `ServerWebExchange#getFormData()` when a direct map is needed.

### When to use `@RequestBody`?

When the client sends **JSON** or another body representation requiring an `HttpMessageReader`/codec. For JSON, do not send individual fields with `@RequestParam`; use `@RequestBody JsonRegistration` or `Mono<JsonRegistration>` and apply `@Valid`/`@Validated` when Bean Validation is desired. Do not feed a JSON body into a form-data binder expecting JSON decoder behavior. For form-urlencoded, `@ModelAttribute` is usually the simpler choice.

## 12. Security, Performance, and Reactive Operations

### 12.1. Mass assignment and untrusted data

Form binders can assign properties by client-supplied names. If you bind directly to an entity containing `role`, `admin`, `ownerId`, or `accountBalance`, users can attempt to submit those fields, including via nested paths. Ways to reduce risk:

- Use an **input DTO** containing strictly the fields clients are allowed to edit; never bind sensitive persistence entities directly.
- With property binding, configure `@InitBinder` and `setAllowedFields(...)` appropriately; check `BindingResult#getSuppressedFields()` if you want to actively reject out-of-contract input.
- With constructor binding/immutable DTOs, review constructor arguments carefully since they are also populated from client data; `setAllowedFields` primarily governs setter/property binding rather than automatically allowing/disallowing all constructor arguments.
- Validation (e.g., `@NotNull`, `@Min`) does not replace **authorization**. Permission to modify an entity must be enforced at the service boundary.
- Headers, query params, paths, and forms are all untrusted user input and should never serve as a trust anchor for authentication/tenant/role.

### 12.2. Do not block the event loop

WebFlux operates on reactive I/O. Methods like `getFormData()` and `getMultipartData()` return `Mono` because the body must be decoded asynchronously. Never call `.block()` on a request-handling/event-loop thread to grab form data synchronously; instead return `Mono` or compose the pipeline with `flatMap`.

Custom Converters/Formatters should be fast, deterministic, and never call blocking databases or HTTP services. If business rules require I/O checks, execute them after conversion in a reactive service using async APIs, rather than stuffing network waits into a converter.

### 12.3. Multipart and resource limits

Large file uploads require attention to memory/buffer limits, multipart parser limits, filename/path sanitization, file types, and `DataBuffer` lifecycle. Do not load entire files into a `String` or store `FilePart` in a singleton. With `Flux<PartEvent>` streaming, consume/release buffers according to contract; use streaming APIs only when genuinely needed.

### 12.4. Locale and normalization

`DateTimeFormat`, `NumberFormat`, and global converters can be affected by locale or input formatting. For machine-to-machine APIs, prefer ISO date/time and fixed-contract number formats. For user-facing HTML forms, consider locale/time zone and test real inputs rather than hardcoding a single format if the UX requires localization.

## 13. Checklist for Choosing the Right Data Source

- [ ] For `@RequestParam` in WebFlux: the source is **query**, not form body automatically.
- [ ] For `@PathVariable`: the name matches the URI template, and route matching happens before conversion.
- [ ] For `@RequestHeader`: header names are exact, defaults/optionals are used when absence is allowed, and headers are not treated as trusted identity.
- [ ] For form-urlencoded: choose `@ModelAttribute` to bind a typed DTO, or `ServerWebExchange#getFormData()` to obtain `Mono<MultiValueMap<String,String>>`.
- [ ] For multipart: use `FilePart`/`Part`, `@RequestPart`, or `getMultipartData()`; do not use Servlet `MultipartFile` in WebFlux.
- [ ] For JSON: use `@RequestBody` and codecs; do not expect JSON to turn into query parameters.
- [ ] Use `@Valid`/`@Validated` when constraint validation is needed; handle `BindingResult` and `WebExchangeBindException` in the proper place.
- [ ] Have converters/formatters for `UUID`, `LocalDate`, enum aliases, or domain types, and test malformed inputs.
- [ ] Do not call `block()` on the reactive request path; converters/formatters perform no blocking I/O.
- [ ] Form DTOs/constructor binding/allowed fields prevent mass assignment; update permissions are verified separately.
- [ ] Integration tests cover query/path/header, missing/default values, date formats, custom Converters, same-named query-vs-form keys, form validation, and JSON bodies.

**One-sentence summary:** In Spring WebFlux, **pick the right HTTP source first, then convert types**: `@RequestParam` reads only query, `@PathVariable` reads the route, `@RequestHeader` reads headers, and form bodies use `@ModelAttribute` or `getFormData()`. This source separation is a crucial difference from Servlet MVC.

## References

- Spring Framework Reference — WebFlux `@RequestParam` (query-only): https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/requestparam.html
- Spring Framework Reference — WebFlux `@RequestHeader`: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/requestheader.html
- Spring Framework Reference — WebFlux `@ModelAttribute` and binding form/query/path/header: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/modelattrib-method-args.html
- Spring Framework Reference — WebFlux Type Conversion: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/typeconversion.html
- Spring Framework Reference — Reactive Core, Form/MultiPart Data: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
- Spring Framework Reference — WebFlux Multipart and `FilePart`: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/multipart-forms.html
- Spring Framework Reference — WebFlux Config, `WebFluxConfigurer#addFormatters`: https://docs.spring.io/spring-framework/reference/web/webflux/config.html
- Spring Framework Reference — WebFlux `@RequestBody` and validation: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/requestbody.html
