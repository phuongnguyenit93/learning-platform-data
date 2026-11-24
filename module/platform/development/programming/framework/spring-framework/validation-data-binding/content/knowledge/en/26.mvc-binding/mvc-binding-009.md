# @RequestParam, @PathVariable, and @RequestHeader with Type Conversion in Spring MVC

In Spring MVC, an HTTP request can carry data in the **query string**, **form body**, **URI path**, or **HTTP headers**. Controllers do not need to accept these values as `String` and parse them manually: Spring provides dedicated annotations to select the **data source**, specify the **input name**, handle **missing values / default values**, and apply **type conversion** to turn HTTP strings into the right Java types.

The three core annotations are:

- `@RequestParam`: extracts a Servlet request **request parameter**, typically a query parameter or a URL-encoded form field.
- `@PathVariable`: extracts a **URI template variable** matched by the route handler.
- `@RequestHeader`: extracts an **HTTP request header** or collection of headers.

All three work with `String`, numbers, enums, and many other types when an appropriate `ConversionService` / formatter is registered. For example, `?page=3` can become `int page = 3`, `/orders/42` can become `long id = 42`, or header `X-Retry-Count: 2` can become `int retryCount = 2`.

**Scope:** this lesson explains Spring MVC on the **Servlet stack**, using Java 17+ and Spring Boot 3.x examples. Do not conflate it with Spring WebFlux: in WebFlux, `@RequestParam` mainly reads query parameters, whereas in Servlet MVC the concept of request parameters also includes form data.

## 1. Comparing the three data sources

A sample request:

~~~http
GET /api/items/42?page=3&tag=java&tag=spring HTTP/1.1
Host: localhost:8080
X-Client-Id: mobile
X-Retry-Count: 2
~~~

A controller can declare:

~~~java
@GetMapping("/api/items/{itemId}")
public Object find(
        @PathVariable("itemId") long itemId,
        @RequestParam("page") int page,
        @RequestParam("tag") List<String> tags,
        @RequestHeader("X-Client-Id") String clientId,
        @RequestHeader("X-Retry-Count") int retryCount) {
    // Use parameters resolved and converted by Spring.
    return ...;
}
~~~

This snippet illustrates the method signature and is **not a standalone Java program**. In the complete project in section 6, each field receives:

| Java argument | HTTP source | Converted Java value |
|---|---|---|
| `long itemId` | `/api/items/42`, URI template `{itemId}` | `42L` |
| `int page` | `?page=3` | `3` |
| `List<String> tags` | `tag=java&tag=spring` | `["java","spring"]` |
| `String clientId` | Header `X-Client-Id: mobile` | `"mobile"` |
| `int retryCount` | Header `X-Retry-Count: 2` | `2` |

The three annotations **are not interchangeable ways to write the same thing**. They share Spring's type conversion components, yet pull from **different input locations**. A URL `/api/items/42?page=3` does not automatically turn `42` into `@RequestParam("itemId")`, nor `page` into `@PathVariable("page")`.

### Annotation selection rules

| Scenario | Choice | Why? |
|---|---|---|
| Resource ID in the URL, e.g., `/users/42` | `@PathVariable` | Resource is identified by URI structure |
| Filters, page, sort order: `?page=2&sort=recent` | `@RequestParam` | Parameters refine retrieval/listing |
| HTML form sending `application/x-www-form-urlencoded` | `@RequestParam` for a few fields or `@ModelAttribute` for a DTO | Form fields belong to Servlet request parameters |
| Client/protocol values in request headers | `@RequestHeader` | Not query/form/path |
| JSON body `{"name":"A"}` | `@RequestBody` | JSON requires HTTP message conversion, not query binding |
| Reading all query/form keys | `@RequestParam Map` or `MultiValueMap` without a name | Captures the parameter set rather than one key |
| Reading all HTTP headers | `@RequestHeader HttpHeaders` | Processes the complete header set |
| Complex business field set needing DTO validation | `@ModelAttribute` (form) or `@RequestBody` (JSON) | Avoids overly long handler signatures |

## 2. `@RequestParam`: query parameters and form parameters

### 2.1. Specifying the parameter name

~~~java
@GetMapping("/search")
public String search(
        @RequestParam("term") String keyword,
        @RequestParam("page") int page) {
    return keyword + ":" + page;
}
~~~

With `GET /search?term=spring&page=2`, Spring assigns `keyword = "spring"` and `page = 2`. The HTTP name is `term` even though the Java variable is named `keyword`, because the annotation explicitly specifies the name. Declaring `@RequestParam("term")` explicitly keeps the code independent of whether the compiler preserves `-parameters`.

The annotation has two synonymous attributes: `value` and `name`. These forms are equivalent:

~~~java
@RequestParam("page") int page
@RequestParam(name = "page") int page
@RequestParam(value = "page") int page
~~~

These lines are **illustrative parameter declarations**, not valid outside a Java method signature.

In Spring MVC, `@RequestParam` reads Servlet request parameters. This source normally includes:

- Query parameters: `GET /search?page=2`.
- URL-encoded form parameters: `POST /search` with body `page=2` and Content-Type `application/x-www-form-urlencoded`.
- Multipart form parameters, when multipart processing is configured.

Do not treat `@RequestParam` as an annotation for reading a JSON body. For JSON, use `@RequestBody` and an appropriate DTO.

### 2.2. `required`, `Optional`, and `defaultValue`

By default `@RequestParam` is **required** (`required=true`):

~~~java
@GetMapping("/required")
public String required(@RequestParam("q") String q) {
    return q;
}
~~~

Requests missing `q` are typically rejected by Spring MVC with HTTP 400 before the handler runs, commonly via `MissingServletRequestParameterException`. If the value should be optional:

~~~java
@GetMapping("/optional")
public String optional(
        @RequestParam(name = "q", required = false)
        String q) {
    return q == null ? "none" : q;
}
~~~

Or use `Optional`:

~~~java
@GetMapping("/optional-wrapper")
public String optionalWrapper(
        @RequestParam("q") java.util.Optional<String> q) {
    return q.orElse("none");
}
~~~

`Optional<String>` expresses clearly that the parameter may be omitted. For numeric types, avoid declaring `int page` with `required=false` and no default: primitive `int` cannot hold `null`. Use `Integer`, `Optional<Integer>`, or a valid default.

Common pagination pattern:

~~~java
@GetMapping("/items")
public String items(
        @RequestParam(name = "page", defaultValue = "1")
        int page) {
    return "page=" + page;
}
~~~

`defaultValue = "1"` has two effects:

1. When parameter `page` is missing, Spring takes the default string `"1"` and **converts it to `int`**.
2. `defaultValue` implicitly sets `required=false`; the default is also applied when an empty string is sent in request-param resolution.

Thus both `GET /items` and `GET /items?page=` receive `page = 1` in standard setups. However, `GET /items?page=abc` does **not** fall back to the default: the input is present but type conversion fails, typically returning HTTP 400.

**Do not confuse `required=false` with validation rules.** It only states that the HTTP input may be omitted; `@Min(1)` or another constraint expresses the valid numeric domain after conversion.

### 2.3. Multiple values for the same key

~~~http
GET /search?tag=java&tag=spring&tag=backend HTTP/1.1
Host: localhost:8080
~~~

Controller:

~~~java
@GetMapping("/search")
public List<String> search(
        @RequestParam("tag") List<String> tags) {
    return tags;
}
~~~

Spring resolves repeated parameters sharing the same key into a list. You can use `String[]`, `List<String>`, or collections of convertible types. Some converters also split comma-separated strings where applicable, but do not assume clients treat “repeated keys” and “one comma-separated key” identically: specify the API contract and test the exact input format.

If you need **all request parameters** without knowing names ahead of time:

~~~java
@GetMapping("/debug-params")
public Map<String, String> oneValuePerKey(
        @RequestParam Map<String, String> params) {
    return params;
}
~~~

~~~java
@GetMapping("/debug-multiple")
public org.springframework.util.MultiValueMap<String, String>
        allValues(@RequestParam
        org.springframework.util.MultiValueMap<String, String> params) {
    return params;
}
~~~

When `@RequestParam` **specifies no name** and the parameter type is `Map` or `MultiValueMap`, Spring collects all request parameter names into the map. `Map<String,String>` fits when only one value per key matters; `MultiValueMap` preserves multiple values per key.

These are **illustrative** handlers; omit them from the demo controller unless needed. Avoid using unbounded maps to directly update entities or write sensitive audit logs.

### 2.4. Implicit request params for simple types

In Spring MVC, a handler argument of a simple type (per `BeanUtils.isSimpleProperty`) not handled by another resolver can be treated as `@RequestParam` **even without the annotation**. For example:

~~~java
@GetMapping("/implicit")
public String implicit(String term) {
    return term;
}
~~~

However, **write `@RequestParam("term")` explicitly** in documentation, public APIs, and large codebases. It clarifies the data source, required/optional status, defaults, and avoids relying on compiled parameter-name metadata.

## 3. `@PathVariable`: converting URI variables to Java types

### 3.1. Only extracts variables present in the URI template

Route example:

~~~java
@GetMapping("/orders/{orderId}")
public String detail(
        @PathVariable("orderId") long id) {
    return "order=" + id;
}
~~~

`GET /orders/125` → `id == 125L`. Distinguish:

- `/orders/125` matches the template.
- `/orders/abc` still matches the `{orderId}` template during routing, but converting `abc` to `long` **fails**, typically producing HTTP 400.
- `/orders` **does not match** a template containing `{orderId}`, so normally no handler matches and Spring returns 404. `required=false` on `@PathVariable` does not create a route for URLs missing the segment.

Some APIs declare both paths when they genuinely need to support “with and without ID”:

~~~java
@GetMapping({"/orders", "/orders/{orderId}"})
public String optionalId(
        @PathVariable(name = "orderId", required = false)
        Long orderId) {
    return orderId == null ? "all" : "one=" + orderId;
}
~~~

This is a separate illustrative snippet. Use the wrapper `Long` instead of primitive `long` because when the route omits `orderId`, the value is `null`. In REST APIs, it is usually cleaner to define two separate handlers `GET /orders` and `GET /orders/{id}` to distinguish collection and resource semantics.

### 3.2. URI variable name vs Java parameter name

~~~java
@GetMapping("/products/{sku}")
public String product(@PathVariable("sku") String code) {
    return code;
}
~~~

The URI variable name is `sku`, while the Java argument name is `code`. Do not expect Spring to guess that two different names correspond; specify `@PathVariable("sku")`.

Some projects omit the name in the annotation when the Java parameter matches the URI variable name and `-parameters` metadata is enabled. Still, specifying the name explicitly reduces build-config coupling and makes the contract obvious to readers.

### 3.3. URL pattern constraints and conversion errors

Routes can include regex patterns:

~~~java
@GetMapping("/orders/{orderId:\\d+}")
public String numericOrder(
        @PathVariable("orderId") long orderId) {
    return "order=" + orderId;
}
~~~

Inside a Java annotation string literal, `\d+` must be escaped as `\\d+` as shown. This pattern **matches only segments consisting of digits**, so `/orders/abc` is rejected at route matching rather than failing type conversion.

A route pattern does not replace business rules. `/orders/0` still matches `\\d+` and converts to `0L`; to forbid ID 0, add appropriate business or Bean Validation checks.

### 3.4. Multiple URI variables and maps

~~~java
@GetMapping("/shops/{shopId}/products/{productId}")
public String product(
        @PathVariable("shopId") long shopId,
        @PathVariable("productId") long productId) {
    return shopId + ":" + productId;
}
~~~

To collect all template variables:

~~~java
@GetMapping("/shops/{shopId}/products/{productId}")
public Map<String, String> pathMap(
        @PathVariable Map<String, String> variables) {
    return variables;
}
~~~

`@PathVariable Map` **without a specific name** gathers all URI template variables. Values in the map are strings, whereas individual `long` parameters undergo conversion. The map does not guarantee variables are authorized for access; URL IDs remain untrusted input.

### 3.5. UUID, enum, and custom types

~~~java
@GetMapping("/documents/{id}")
public String document(
        @PathVariable("id") java.util.UUID id) {
    return id.toString();
}
~~~

When the URI contains a valid UUID string, Spring's conversion system produces a `UUID`. An unparseable string triggers a conversion error rather than an arbitrary `UUID` value.

`enum`s can also be used:

~~~java
public enum OrderState {
    NEW, PAID, CANCELLED
}

@GetMapping("/orders/by-state/{state}")
public String byState(
        @PathVariable("state") OrderState state) {
    return state.name();
}
~~~

These snippets illustrate controller usage; the enum definition belongs in `OrderState.java` or as a valid nested enum. The default `String`-to-`Enum` converter matches **enum constant names**, and does not automatically accept lowercase or aliases. If the contract requires `paid` to map to `PAID`, define an explicit converter instead of relying on implicit behavior.

## 4. `@RequestHeader`: converting HTTP headers to method arguments

### 4.1. Reading a specific header

Request:

~~~http
GET /status HTTP/1.1
Host: localhost:8080
X-Client-Id: mobile
X-Retry-Count: 2
~~~

Controller:

~~~java
@GetMapping("/status")
public String status(
        @RequestHeader("X-Client-Id") String clientId,
        @RequestHeader("X-Retry-Count") int retryCount) {
    return clientId + ":" + retryCount;
}
~~~

`X-Client-Id` becomes `String` and `X-Retry-Count` converts to `int`. HTTP header names are **case-insensitive**, so `x-client-id` also matches, though code conventionally uses readable casing.

Like `@RequestParam`, `@RequestHeader` defaults to `required=true`; you can use `required=false`, `Optional<T>`, or `defaultValue`.

~~~java
@GetMapping("/status")
public String status(
        @RequestHeader(
            name = "X-Retry-Count",
            defaultValue = "0") int retryCount) {
    return "retry=" + retryCount;
}
~~~

When the header is absent, `retryCount == 0`. If the header is present with value `not-a-number`, conversion to `int` fails; a default **does not** silently discard a mistyped value.

### 4.2. Multi-value headers, lists, and media types

Many headers contain comma-separated lists of tokens, for example:

~~~http
Accept: application/json, text/plain
~~~

Spring supports converting certain comma-separated headers into `String[]`/`List<String>` when appropriate:

~~~java
@GetMapping("/accepts")
public List<String> accepts(
        @RequestHeader("Accept") List<String> accept) {
    return accept;
}
~~~

This is an illustrative snippet. When you need accurate parsing of **HTTP media type semantics** including `q` weights, use dedicated classes such as `MediaType`/`HttpHeaders` or content negotiation rather than naively splitting strings on commas. Some headers have complex grammars where comma-splitting breaks.

### 4.3. Reading all headers

~~~java
@GetMapping("/all-headers")
public Map<String, String> allHeaders(
        @RequestHeader Map<String, String> headers) {
    return headers;
}
~~~

Or preserving multiple values:

~~~java
@GetMapping("/all-headers")
public org.springframework.http.HttpHeaders allHeaders(
        @RequestHeader
        org.springframework.http.HttpHeaders headers) {
    return headers;
}
~~~

In the second example, `HttpHeaders` offers convenient header accessors such as `getFirst("X-Client-Id")`. Unnamed `@RequestHeader` paired with `Map`, `MultiValueMap`, or `HttpHeaders` collects the header set. Both snippets share route `/all-headers` so they are **alternatives**, not methods to add together in one controller.

Never echo all headers back to clients in production for debugging: cookies, authorization tokens, and infrastructure headers can expose sensitive data.

### 4.4. Custom headers and security

A custom header like `X-User-Id`, `X-Role`, or `X-Admin` is **not trustworthy just because it arrives via `@RequestHeader`**. HTTP clients can usually send arbitrary headers. Authentication and authorization must use proper security/trusted gateway mechanisms; if a gateway injects user headers, ensure clients cannot spoof them or bypass the gateway.

`@RequestHeader` only reads and converts values; **it does not verify signatures, permissions, or header provenance**.

## 5. How does type conversion work?

### 5.1. From input strings to Java types

Handler arguments often accept `Integer`, `Long`, `UUID`, `LocalDate`, `Enum`, or collections instead of `String`. Spring MVC uses configured converters/formatters to produce the target values.

~~~text
HTTP request
  |
  +-- query/form parameter ----> @RequestParam
  |
  +-- URI template variable ---> @PathVariable
  |
  +-- request header ----------> @RequestHeader
                                   |
                                   v
                    MVC HandlerMethodArgumentResolver
                                   |
                                   v
                     WebDataBinder / ConversionService
                                   |
              +--------------------+---------------------+
              |                                          |
        conversion OK                             conversion error
              |                                          |
              v                                          v
       Java method argument                     MVC error/exception
       (Long, int, enum, Date...)               (typically HTTP 400)
              |
              v
       Controller method body
~~~

All three annotations rely on Spring's extensible type conversion system, while **input extraction and missing-value errors** are specific to each argument resolver. Do not confuse `ConversionService` with Jackson deserialization: `@RequestBody` for JSON typically runs through `HttpMessageConverter`.

### 5.2. Common types

| String data in HTTP | Java target | Result when valid |
|---|---|---|
| `"42"` | `long` or `Long` | `42L` |
| `"3"` | `int` or `Integer` | `3` |
| `"true"` | `boolean` or `Boolean` | `true` |
| `"8.50"` | `BigDecimal` | `new BigDecimal("8.50")` by value |
| `"9a3a..."` valid UUID format | `UUID` | `UUID` instance |
| `"PAID"` | `OrderState` enum | `OrderState.PAID` |
| `"2026-11-06"` | `LocalDate` with ISO formatter | November 6, 2026 |
| `tag=java&tag=spring` | `List<String>` | two elements |
| `"application/json"` from header | `MediaType` when converter supports it | a media type object |

For numbers, do not assume every locale parses `1,5` as `1.5`. For dates, do not assume `dd/MM/yyyy` equals ISO. Declare formats explicitly and test against the HTTP/locale contract.

### 5.3. `@DateTimeFormat` for date parameters

~~~java
@GetMapping("/reports")
public String report(
        @RequestParam("from")
        @org.springframework.format.annotation.DateTimeFormat(
            iso = org.springframework.format.annotation.DateTimeFormat.ISO.DATE)
        java.time.LocalDate from) {
    return from.toString();
}
~~~

`GET /reports?from=2026-11-06` → `LocalDate` for 2026-11-06. This is an illustrative handler to place in a controller with appropriate imports/routes. Prefer ISO formatting when you want a clear API contract easy to share across clients.

If a request sends `from=06/11/2026` while the formatter expects ISO, conversion fails and typically returns HTTP 400. This differs from a `@NotNull` or `@Past` violation: conversion must succeed before constraints can evaluate a valid `LocalDate`.

In some cases `@NumberFormat` or `@DurationFormat` should be used to declare number/duration formats; do not apply `@DateTimeFormat` to every type.

### 5.4. `@NumberFormat` and locale

~~~java
@GetMapping("/prices")
public String price(
        @RequestParam("amount")
        @org.springframework.format.annotation.NumberFormat(
            pattern = "#,##0.00")
        java.math.BigDecimal amount) {
    return amount.toPlainString();
}
~~~

This is an illustrative snippet requiring locale awareness. `,` and `.` can have opposite meanings depending on the request locale. For public JSON REST APIs expecting locale-invariant numbers, defining a uniform format contract is usually simpler than localized number formatting. If accepting localized user input, test every supported locale.

### 5.5. Custom converter for a value object

Suppose the domain expects IDs formatted as `INV-123` and represents them with a record type instead of passing `String` into services.

File `InvoiceKey.java`:

~~~java
package com.example.customconvert;

public record InvoiceKey(long number) {
}
~~~

File `InvoiceKeyConverter.java`:

~~~java
package com.example.customconvert;

import org.springframework.core.convert.converter.Converter;

public final class InvoiceKeyConverter
        implements Converter<String, InvoiceKey> {

    @Override
    public InvoiceKey convert(String source) {
        if (!source.matches("INV-[0-9]+")) {
            throw new IllegalArgumentException(
                "Invoice key must look like INV-123");
        }

        try {
            long number = Long.parseLong(source.substring(4));
            return new InvoiceKey(number);
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException(
                "Invoice key is outside the long range", ex);
        }
    }
}
~~~

File `MvcConversionConfig.java`:

~~~java
package com.example.customconvert;

import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class MvcConversionConfig implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new InvoiceKeyConverter());
    }
}
~~~

Once Spring scans these three files and applies the MVC config, a handler can be written as:

~~~java
@GetMapping("/invoices/{id}")
public InvoiceKey find(
        @PathVariable("id") InvoiceKey id) {
    return id;
}
~~~

A request `GET /invoices/INV-123` produces `new InvoiceKey(123)`. This is an illustrative handler snippet **inside a `@RestController` within the same application that registered the converter**, not a runnable project separate from the three files above. If the pattern fails or the number overflows `long`, the converter throws an exception signaling conversion failure so Spring returns a request error.

A `Converter<String,InvoiceKey>` can also serve `@RequestParam` or `@RequestHeader` parameters of the same target type when registered in MVC's `ConversionService`. That is its strength: **one conversion mechanism** reused across multiple input locations.

Avoid writing converters that automatically query the database to load entities with side effects; for resource IDs, convert to a simple value object and let the service load data after authorization checks. If a converter queries a DB, carefully account for request lifecycle, not-found errors, and cost.

### 5.6. `@InitBinder` vs application-wide converters

For controller-level binding customization, Spring also provides `@InitBinder` and `WebDataBinder`. It is useful when format/binding rules apply only to specific endpoints; `WebMvcConfigurer.addFormatters(...)` suits converters shared across MVC. Do not replace Boot's entire configured `ConversionService` just to add one converter; register additions via the proper extension point.

## 6. Runnable Spring Boot example: combining all three annotations

This example consists of two files in package `com.example.requestinputs`, using Spring Boot 3.x, Java 17+, Servlet MVC, and Gradle. It accepts a URL containing a numeric ID, query parameters with defaults/lists/dates, and two HTTP headers. The controller returns a JSON object showing the converted values.

### 6.1. Dependencies

In a project with a valid Spring Boot Gradle plugin and dependency management:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

To test `@Min`/`@NotBlank` in the validation section below, add `spring-boot-starter-validation`. The core conversion example only needs Spring MVC conversion and does not require a validation provider to parse `long`, `int`, or `LocalDate`.

The commands below assume the project has `settings.gradle`, a Gradle build, and the Gradle wrapper generated by Spring Initializr or an existing Boot project. You cannot compile with plain JDK `javac` alone because the code imports Spring MVC.

### 6.2. Entry point — `RequestInputsApplication.java`

Create `src/main/java/com/example/requestinputs/RequestInputsApplication.java`:

~~~java
package com.example.requestinputs;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RequestInputsApplication {

    public static void main(String[] args) {
        SpringApplication.run(RequestInputsApplication.class, args);
    }
}
~~~

`@SpringBootApplication` enables component scanning for the current package and subpackages, so the controller in the same package is discovered automatically.

### 6.3. Controller — `ItemController.java`

Create `src/main/java/com/example/requestinputs/ItemController.java`:

~~~java
package com.example.requestinputs;

import java.time.LocalDate;
import java.util.List;

import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ItemController {

    @GetMapping("/api/items/{itemId}")
    public ItemView findItem(
            @PathVariable("itemId") long itemId,
            @RequestParam(
                name = "page",
                defaultValue = "1") int page,
            @RequestParam(
                name = "tag",
                required = false) List<String> tags,
            @RequestParam(
                name = "since",
                required = false)
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
                LocalDate since,
            @RequestHeader(
                name = "X-Client-Id",
                defaultValue = "web") String clientId,
            @RequestHeader(
                name = "X-Retry-Count",
                defaultValue = "0") int retryCount) {

        return new ItemView(
            itemId,
            page,
            tags == null ? List.of() : tags,
            since,
            clientId,
            retryCount
        );
    }

    public record ItemView(
        long itemId,
        int page,
        List<String> tags,
        LocalDate since,
        String clientId,
        int retryCount
    ) {
    }
}
~~~

Each parameter demonstrates a specific feature:

- `@PathVariable("itemId") long itemId`: reads `{itemId}` from the URI and converts it to `long`.
- `@RequestParam(name="page", defaultValue="1") int page`: defaults to `1` when missing or empty; other numeric values are parsed.
- `@RequestParam(name="tag",required=false) List<String> tags`: multiple query values sharing one key; when absent, the controller normalizes to an empty list rather than returning `null`.
- `@RequestParam(name="since",required=false) @DateTimeFormat(ISO.DATE) LocalDate since`: ISO date query parameter when provided; `null` when absent.
- `@RequestHeader(name="X-Client-Id",defaultValue="web") String clientId`: reads the header and defaults to `"web"` if missing.
- `@RequestHeader(name="X-Retry-Count",defaultValue="0") int retryCount`: reads the header and converts it to an integer.
- `ItemView` is a Java `record` used solely to return resolved values; it is not a persisted database entity.

Explicitly naming keys in all three annotations prevents mismatches between Java argument names and client keys.

### 6.4. Running the app

Unix/macOS:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Spring Boot listens on `http://localhost:8080` by default if `server.port` is unchanged and the port is available.

Send a request with all fields:

~~~bash
curl -i "http://localhost:8080/api/items/42?page=3&tag=java&tag=spring&since=2026-11-06" \
  -H "X-Client-Id: mobile" \
  -H "X-Retry-Count: 2"
~~~

Expected **HTTP 200 OK** with JSON matching (key order is not guaranteed):

~~~json
{
  "itemId": 42,
  "page": 3,
  "tags": ["java", "spring"],
  "since": "2026-11-06",
  "clientId": "mobile",
  "retryCount": 2
}
~~~

Send a request omitting optional query/header parameters:

~~~bash
curl -i "http://localhost:8080/api/items/42"
~~~

Expected **HTTP 200** with:

~~~json
{
  "itemId": 42,
  "page": 1,
  "tags": [],
  "since": null,
  "clientId": "web",
  "retryCount": 0
}
~~~

Send a wrong type for the path variable:

~~~bash
curl -i "http://localhost:8080/api/items/abc"
~~~

Route `/api/items/{itemId}` matches segment `abc`, but `long itemId` fails conversion. With default MVC error handling, the result is typically **HTTP 400 Bad Request**. The exact error body varies by Spring Boot version and error configuration, so no fixed JSON message is asserted here.

Send a wrong type in the query string:

~~~bash
curl -i "http://localhost:8080/api/items/42?page=xyz"
~~~

Expected **HTTP 400** because `xyz` cannot parse as `int`. `defaultValue="1"` does not rescue a present-but-invalid value.

Send a wrong type in a header:

~~~bash
curl -i "http://localhost:8080/api/items/42" \
  -H "X-Retry-Count: no"
~~~

Expected **HTTP 400** because the header cannot parse as `int`.

Send a non-ISO date:

~~~bash
curl -i "http://localhost:8080/api/items/42?since=06-11-2026"
~~~

Expected **HTTP 400** because `@DateTimeFormat(ISO.DATE)` expects `yyyy-MM-dd` with a valid calendar date.

Send a non-matching path:

~~~bash
curl -i "http://localhost:8080/api/items"
~~~

There is no `/api/items` mapping in the demo, so the typical result is **HTTP 404 Not Found**, unlike a type conversion failure where the segment exists but fails to parse.

### 6.5. Form POST behaves the same for `@RequestParam` conversion

In Servlet MVC, URL-encoded form fields are also request parameters. Example separate handler in a controller:

~~~java
@PostMapping(
    path = "/api/search",
    consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
public String search(
        @RequestParam("term") String term,
        @RequestParam(name = "page", defaultValue = "1")
        int page) {
    return term + ":" + page;
}
~~~

This is an additional snippet requiring imports for `@PostMapping`, `MediaType`, and `@RequestParam`. If a client sends body `term=spring&page=3` with `Content-Type: application/x-www-form-urlencoded`, the handler returns `spring:3`. For forms with many fields, `@ModelAttribute SearchForm form` is usually easier to manage than individual `@RequestParam`s.

## 7. Testing with MockMvc: conversion success and failure

Add `spring-boot-starter-test` as in the dependencies section. File `src/test/java/com/example/requestinputs/ItemControllerTest.java`:

~~~java
package com.example.requestinputs;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ItemControllerTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void bindsAllThreeSourcesAndConvertsTypes()
            throws Exception {
        mvc.perform(get("/api/items/42")
                .param("page", "3")
                .param("tag", "java", "spring")
                .param("since", "2026-11-06")
                .header("X-Client-Id", "mobile")
                .header("X-Retry-Count", "2"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.itemId").value(42))
            .andExpect(jsonPath("$.page").value(3))
            .andExpect(jsonPath("$.tags[0]").value("java"))
            .andExpect(jsonPath("$.tags[1]").value("spring"))
            .andExpect(jsonPath("$.since").value("2026-11-06"))
            .andExpect(jsonPath("$.clientId").value("mobile"))
            .andExpect(jsonPath("$.retryCount").value(2));
    }

    @Test
    void appliesDefaultsForMissingValues()
            throws Exception {
        mvc.perform(get("/api/items/42"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.page").value(1))
            .andExpect(jsonPath("$.tags").isEmpty())
            .andExpect(jsonPath("$.since").value(
                org.hamcrest.Matchers.nullValue()))
            .andExpect(jsonPath("$.clientId").value("web"))
            .andExpect(jsonPath("$.retryCount").value(0));
    }

    @Test
    void rejectsInvalidPathId() throws Exception {
        mvc.perform(get("/api/items/not-a-number"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void rejectsInvalidQueryNumber() throws Exception {
        mvc.perform(get("/api/items/42")
                .param("page", "abc"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void rejectsInvalidHeaderNumber() throws Exception {
        mvc.perform(get("/api/items/42")
                .header("X-Retry-Count", "abc"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void rejectsInvalidDateFormat() throws Exception {
        mvc.perform(get("/api/items/42")
                .param("since", "06-11-2026"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void pathMustMatchRoute() throws Exception {
        mvc.perform(get("/api/items"))
            .andExpect(status().isNotFound());
    }
}
~~~

Run:

~~~bash
./gradlew test
~~~

On Windows:

~~~powershell
.\gradlew.bat test
~~~

In a Spring Boot 3.x project with default MVC configuration, all seven tests are expected to **PASS**. They test from the request boundary through `MockMvc` (argument resolution, conversion, response rendering), rather than only calling `Long.parseLong` or Java setters directly. In real projects with Spring Security or custom filters, add matching security test configuration.

If a project uses Spring Boot 4+, test dependencies/modules and packages may differ; this test code targets **Spring Boot 3.x**.

## 8. Distinguishing missing parameters from type conversion errors

An application must return consistent HTTP errors without lumping every error into “validation error”.

| Scenario | Phase where it occurs | Common default behavior |
|---|---|---|
| `@RequestParam("page") int page` without sending `page` | Resolving required parameter | `MissingServletRequestParameterException` → HTTP 400 |
| `@RequestHeader("X-Key") String key` without the header | Resolving required header | `MissingRequestHeaderException` → HTTP 400 |
| URI `/items/abc` with `@PathVariable long id` | Type conversion after route match | `MethodArgumentTypeMismatchException` → HTTP 400 |
| Query `?page=abc` with `int page` | Type conversion | `MethodArgumentTypeMismatchException` → HTTP 400 |
| Header `X-Retry-Count: abc` with `int retryCount` | Type conversion | `MethodArgumentTypeMismatchException` → HTTP 400 |
| Empty query value converted to `null` by a converter | Conversion then required check | May be treated as missing value after conversion |
| URI missing segment of route `/items/{id}` | Handler mapping | Typically HTTP 404, not “missing path variable” inside handler |
| `@Min(1)` on `page` with value `0` | Bean/method validation (if enabled) | Corresponding method validation exception; not type mismatch |
| Service logic cannot find valid ID in DB | Business/service | Application decides 404 or other error |

**Special empty values:** the Spring reference notes that if a string converts to `null`, a required argument can be treated as missing. If a parameter is genuinely nullable, use `required=false` or `@Nullable`/`Optional` per contract. `required=false` does not mean invalid values are accepted.

### Do not “catch all exceptions and return 200”

A REST API can use `@RestControllerAdvice` to convert errors into consistent JSON. Illustrative snippet:

~~~java
@RestControllerAdvice
public class InputErrorAdvice {

    @ExceptionHandler(
        org.springframework.web.method.annotation
            .MethodArgumentTypeMismatchException.class)
    public ResponseEntity<Map<String, String>> wrongType(
            org.springframework.web.method.annotation
                .MethodArgumentTypeMismatchException ex) {

        return ResponseEntity.badRequest().body(
            Map.of(
                "error", "INVALID_TYPE",
                "argument", ex.getName()));
    }
}
~~~

This is a **separate sample**, requiring imports for `@RestControllerAdvice`, `@ExceptionHandler`, `ResponseEntity`, `Map`, and placement in a scanned package. It illustrates mapping conversion errors; it does not yet separately handle missing parameters, missing headers, malformed bodies, Bean Validation, or unmatched request paths. In real applications, design consistent error responses and never expose stack traces or sensitive data to clients.

A matched route that fails conversion is completely different from an unmatched route. When debugging, inspect both **mapping conditions** and **conversion service**, rather than blindly catching exceptions.

## 9. Is Bean Validation on controller arguments the same as type conversion?

No. Type conversion parses/changes the input's type (`"2"` into `2`), whereas Jakarta Bean Validation evaluates constraints (whether `2` satisfies `@Min(1)`). General sequence:

~~~text
@RequestParam("page") String "0"
             |
             v
ConversionService -> int 0
             |
             v
Bean Validation if method validation is enabled
             |
             v
@Min(1) => valid or violated?
~~~

Illustrative example with Spring MVC 6.1+ and the validation starter:

~~~java
@GetMapping("/paged")
public String paged(
        @RequestParam(defaultValue = "1")
        @jakarta.validation.constraints.Min(1)
        int page) {
    return "page=" + page;
}
~~~

With Spring MVC 6.1+, constraints directly on handler method parameters can be checked via **built-in handler method validation**, and a violation typically produces `HandlerMethodValidationException`. This mechanism is separate from Spring AOP service method validation; **do not assume `@RequestParam` performs Bean Validation by itself**.

If a project uses an older Spring MVC version or places class-level `@Validated` on the controller, the validation mechanism and exception types can differ; verify your Spring version and active validation path. To enable Bean Validation in Spring Boot 3, typically add:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

Having `@Min(1)` active **does not fix** `page=abc`, because the input cannot even convert to `int`. Conversely, `page=0` parses successfully yet fails validation. Distinguish these two error layers for accurate tests and error messages.

## 10. Registering converters and formatters in MVC configuration

### 10.1. Using `WebMvcConfigurer.addFormatters`

Spring documentation recommends the `WebMvcConfigurer` extension point to register formatters/converters used in MVC. Example:

~~~java
@Configuration
public class MyMvcConfig implements WebMvcConfigurer {

    @Override
    public void addFormatters(
            org.springframework.format.FormatterRegistry registry) {
        registry.addConverter(new InvoiceKeyConverter());
    }
}
~~~

This is part of the converter example in section 5; if placed in a separate file, import `Configuration`, `WebMvcConfigurer`, and `InvoiceKeyConverter` in the same package. Do not declare both `MvcConversionConfig` and `MyMvcConfig` registering the same converter without reason.

### 10.2. Formatters for date/time

`@DateTimeFormat(iso = ISO.DATE)` is a direct choice for an individual parameter. Application-wide, you can configure a unified ISO date-formatting strategy with `DateTimeFormatterRegistrar` inside `addFormatters` when the product contract requires it. Mind locale behavior when using non-ISO patterns.

### 10.3. Why not parse everything manually in controllers?

~~~java
// Avoid repeating across dozens of handlers:
@GetMapping("/bad-example")
public String bad(
        @RequestParam("id") String rawId) {
    long id = Long.parseLong(rawId);
    return "id=" + id;
}
~~~

This snippet runs inside a `@RestController`, yet manual parsing forces every handler to catch `NumberFormatException`, construct HTTP errors, and duplicate conversion logic. Prefer writing:

~~~java
@GetMapping("/better-example")
public String better(
        @RequestParam("id") long id) {
    return "id=" + id;
}
~~~

Let Spring convert and reject invalid inputs at the MVC boundary. When the domain genuinely requires a custom format (like `INV-123`), register a single unified converter. Keep security checks and DB lookups in the service layer instead of stuffing them into converters.

## 11. API design: what should go in path, query, and header?

### 11.1. IDs in the path

`GET /users/42` identifies the target resource. `@PathVariable("id") Long id` converts the ID, yet **does not** verify that user 42 exists or that the caller has permission to view it. If the ID does not exist, the service can return not-found; if unauthorized, enforce security/domain rules.

### 11.2. Filters and pagination in the query

`GET /users?status=ACTIVE&page=1&size=20` fits filtering and pagination. `@RequestParam` supports defaults, enums, numbers, and collections. Enforce bounds on `size`, allowed sort keys, and filter values on the server; successful type conversion does not guarantee values satisfy business rules.

### 11.3. Metadata in headers

Headers typically carry metadata for content negotiation, tracing, correlation, locale, preconditions, or client capabilities. Use `@RequestHeader` when the header itself is part of the HTTP contract, not as a substitute body for complex business payloads.

**Security note:** headers like `Authorization`, `Cookie`, or `X-Api-Key` must never be logged in full, echoed to clients, or treated as plain-text proof of authentication. Headers injected by a reverse proxy require clear trust boundaries and anti-spoofing guarantees.

### 11.4. Distinguishing route mapping from type conversion

Route mapping determines **which handler** receives the request; type conversion determines **which Java arguments** are passed to that handler. For example, `GET /orders/new` and `GET /orders/{id}` may need explicit route separation to avoid attempting to convert `new` into `long`. Use unambiguous route patterns rather than relying on exceptions to tell actions apart from resource IDs.

## 12. Common errors and how to fix them

| Symptom | Likely cause | How to fix |
|---|---|---|
| `@RequestParam` receives `null` even though URL has `/42` segment | Wrong data source used | Use `@PathVariable` for URI template variables |
| `@PathVariable` reports missing name | Annotation name differs from URI variable or missing parameter metadata | Write `@PathVariable("orderId")` explicitly |
| `@RequestHeader` fails to read query `?token=...` | Header is not a query parameter | Send an actual header or switch to `@RequestParam` per API contract |
| `page=abc` causes HTTP 400 | String cannot convert to `int` | Fix input, use appropriate formatter/converter, or return clear error response |
| `page=0` is accepted when minimum page is 1 | Conversion succeeded but business constraint missing | Add `@Min(1)` with method validation or check in service |
| `required=false int page` fails on missing input | Primitive cannot hold `null` | Use `Integer`, `Optional<Integer>`, or `defaultValue` |
| `/orders` does not invoke `/orders/{id}` handler | Missing path segment so route does not match | Declare a separate collection mapping |
| `/orders/abc` does not enter method with `long id` | Conversion failure | Return HTTP 400; distinguish from route mismatch |
| Header `X-Retry-Count: abc` fails before handler | Conversion failure on numeric header | Require a properly formatted integer |
| `since=06-11-2026` fails | Formatter expects ISO date | Use `yyyy-MM-dd` or deliberately update contract/formatter |
| `?tag=a&tag=b` keeps only one value | Using single-value `String`/`Map` per key | Use `List<String>` or `MultiValueMap` |
| Header values lost when using `Map<String,String>` | One key can have multiple values | Use `HttpHeaders`/`MultiValueMap` when needed |
| Lowercase enum fails to parse | Default enum conversion matches enum constant names | Register custom converter for aliases/case-insensitivity |
| Custom `Converter` never runs | Not added to MVC `ConversionService` or config not scanned | Register via `WebMvcConfigurer.addFormatters` |
| Client sends JSON but `@RequestParam` reads nothing | JSON is not a Servlet request parameter map | Use `@RequestBody` with a DTO |
| Logic trusts client-sent `X-Role: admin` | Missing authentication/authorization step | Use a trusted authentication/authorization mechanism |
| HTTP 400 lacks desired JSON format | Error handling not defined | Use `@RestControllerAdvice`; do not swallow exceptions |
| Test uses default yet errors on empty/space values | Rules differ for empty strings, post-conversion nulls, and defaults | Test missing, empty, whitespace, invalid, and valid cases |
| Controller signature uses implicit parameter name and fails to resolve | Build lacks `-parameters` or name was altered | Specify `name`/`value` explicitly in annotations |

### Useful debugging order

1. Confirm actual HTTP method and path; does the route match?
2. Identify where the input lives: query/form, URI template, or header?
3. Check whether annotation `name`/`value` matches the key/URI variable?
4. Check `required`, `defaultValue`, `Optional`, and Java primitive/wrapper types.
5. If the value exists but fails, inspect `ConversionService`, locale, `@DateTimeFormat`/`@NumberFormat`, and custom converters.
6. Read the exception: missing request param/header, type mismatch, route mismatch, or validation error.
7. Only after parsing succeeds, evaluate business rules, authorization, and persistence.

Never “fix” a conversion error by removing all validation or blindly turning every parameter into `String`. Type-safe method signatures keep controller contracts clear and centralize error handling.

## 13. Self-check exercises

**Exercise 1 — Defaults and missing parameters.** With `@RequestParam(defaultValue="10") int size`, compare `GET /items`, `GET /items?size=`, `GET /items?size=20`, and `GET /items?size=oops`. Answer: they yield 10, 10, 20, and a type conversion error, respectively. A default cannot fix a present-but-mistyped value.

**Exercise 2 — Path and query.** With `@GetMapping("/products/{id}")`, determine why `GET /products/21?page=2` requires `@PathVariable("id") long id` and `@RequestParam("page") int page`. Swapping the two annotations prevents Spring from reading the intended values.

**Exercise 3 — Headers and trust boundaries.** A client sends `X-User-Role: ADMIN`. Is `@RequestHeader String role` enough to prove the user is an admin? No; HTTP headers can be forged by clients and require authentication/authorization per your security architecture.

**Exercise 4 — Date conversion.** A handler uses `@DateTimeFormat(iso=ISO.DATE) LocalDate from`. Which input is valid: `2026-11-06` or `06/11/2026`? Under `ISO.DATE`, the first is valid. Supporting other formats requires declaring an appropriate formatter/contract.

**Exercise 5 — Repeated query parameters.** With `?tag=java&tag=spring`, should you use `String tag` or `List<String> tags` when both values are needed? Use `List<String>`; or `MultiValueMap` if you need multiple keys as well.

**Exercise 6 — Logic checks.** With `int page`, the request sends `page=0`. Does conversion fail? No, because `"0"` is a valid numeric string. Forbidding page 0 requires a separate constraint or business check.

**Exercise 7 — Custom types.** If an API accepts `/invoices/INV-123` and the method wants `InvoiceKey`, what do you register? A `Converter<String,InvoiceKey>` in MVC's `ConversionService`, then use `@PathVariable("id") InvoiceKey id`.

**Exercise 8 — Route vs mismatch.** How do `/items` and `/items/abc` behave differently when only `/items/{itemId}` with `long itemId` is mapped? `/items` fails route matching (typically 404); `/items/abc` matches the route and fails conversion (typically 400).

## 14. Project adoption checklist

- [ ] Choose annotations matching each source: `@RequestParam`, `@PathVariable`, `@RequestHeader`.
- [ ] Write key/template/header names explicitly to avoid depending on parameter-name metadata.
- [ ] Clarify required vs optional fields; use `required=false`, `Optional`, or `defaultValue` deliberately.
- [ ] Do not use primitives for optional parameters without a default.
- [ ] Verify `Integer`, `Long`, `UUID`, enums, `LocalDate`, and collections used in the API contract.
- [ ] For locale-dependent dates/numbers, specify formats via `@DateTimeFormat` / `@NumberFormat` or an appropriate formatter.
- [ ] For custom value objects, implement a converter and register it via `WebMvcConfigurer.addFormatters`.
- [ ] Test valid, missing, empty, wrong-type, multi-value, and unmatched-route inputs with `MockMvc`.
- [ ] Distinguish conversion errors from Bean Validation constraints; return consistent HTTP errors.
- [ ] Never echo all headers or trust custom security headers without a verified trust boundary.
- [ ] For multi-field forms, consider `@ModelAttribute`; for JSON bodies, use `@RequestBody`.
- [ ] Keep validation, authorization, and business logic at their proper layers after argument conversion completes.

**Key takeaway:** `@RequestParam` selects **query/form** data, `@PathVariable` selects **URI template variables**, and `@RequestHeader` selects **HTTP headers**. Spring MVC resolves the source first, then uses **`ConversionService`/formatters** to produce Java arguments; missing values, conversion failures, unmatched routes, and Bean Validation errors are **distinct situations** that must be handled at the right boundary.

## Official references

- [Spring Framework 6.2 — @RequestParam](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/requestparam.html)
- [Spring Framework — URI patterns and @PathVariable](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html)
- [Spring Framework — @RequestHeader](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestheader.html)
- [Spring Framework — Type Conversion for Controller Method Arguments](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/typeconversion.html)
- [Spring Framework — MVC Conversion and Formatting](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/conversion.html)
- [Spring Framework — MVC Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Boot — Spring MVC and Web Features](https://docs.spring.io/spring-boot/reference/web/servlet.html)
