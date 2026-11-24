# Reading @RequestParam, @RequestHeader, and @CookieValue in Spring WebFlux

## 1. Objectives

An HTTP endpoint often receives data from several parts of the request:

- **Query string** in the URL, for example `?page=2&sort=price`.
- **Request headers**, for example `Accept-Language`, `X-Request-Id`, or `If-None-Match`.
- **Cookies** sent by the client in the `Cookie` header, for example `theme=dark`.

In a Spring WebFlux annotation-based controller, the three corresponding annotations are:

| Annotation | Data source | Example |
| --- | --- | --- |
| `@RequestParam` | Query parameters in the URL | `?page=2` |
| `@RequestHeader` | An HTTP request header | `X-Request-Id: req-42` |
| `@CookieValue` | Value of a specifically named cookie | `Cookie: theme=dark` |

Spring reads the request, finds the value by name, converts it to the method parameter type, and then calls the handler. The controller does not need to parse the URL string, split headers, or read the entire Cookie header by hand in ordinary cases.

This lesson focuses on **Spring WebFlux annotated controllers**. The annotations have the same names as in Spring MVC, but an important difference is that `@RequestParam` in WebFlux binds only query parameters; form data and multipart are handled through separate mechanisms.

## 2. Distinguishing Data Locations in an HTTP Request

Look at the illustrative request:

```http
GET /api/products?page=2&tag=reactor&tag=webflux HTTP/1.1
Host: localhost:8080
Accept: application/json
Accept-Language: vi
X-Request-Id: req-42
Cookie: theme=dark; session=opaque-session-value
```

The values are extracted as follows:

- `page=2`, two `tag` values: query parameters, read with `@RequestParam`.
- `Accept-Language: vi` and `X-Request-Id: req-42`: headers, read with `@RequestHeader`.
- `theme=dark` or `session=...`: cookie pairs, each cookie read with `@CookieValue`.

A request can have multiple query parameters with the same name, multiple header values, or multiple distinct cookies. Choose a parameter type that accurately reflects the data you need to receive, instead of always using `String` for everything.

### 2.1. Differences Between WebFlux and Spring MVC

In Spring MVC, the concept of servlet request parameters combines query parameters, form fields, and some multipart parameters into one model. In **Spring WebFlux**, `@RequestParam` binds only **query parameters**. Form data and multipart are accessed separately through `ServerWebExchange` or bound into a command object using `@ModelAttribute`; files/multipart parts have the `@RequestPart` mechanism.

Do not copy assumptions from an MVC controller to WebFlux without checking. If a WebFlux endpoint receives `application/x-www-form-urlencoded`, using `@RequestParam("email")` is not generally equivalent to servlet MVC.

## 3. Using @RequestParam to Read Query Parameters

### 3.1. Reading a Single Value

Example:

```java
@GetMapping("/products")
public Mono<String> products(
        @RequestParam("page") int page) {

    return Mono.just("page=" + page);
}
```

With the URL `GET /products?page=3`, Spring converts the string `"3"` to `int 3` and passes it to the method. If the query parameter does not exist, the parameter is **required** by default; a request missing `page` is usually handled as HTTP 400 Bad Request.

You can use the `name` attribute instead of `value`:

```java
@RequestParam(name = "page") int page
```

The two forms are equivalent. The name should be written explicitly when the query parameter name is part of the API contract.

### 3.2. Naming Differently from the Java Variable Name

The name in HTTP does not have to match the parameter name:

```java
@GetMapping("/products")
public Mono<String> products(
        @RequestParam(name = "page_size") int pageSize) {

    return Mono.just("pageSize=" + pageSize);
}
```

The client sends `?page_size=20`, while the Java code uses the readable name `pageSize`. Maintain a consistent naming convention for the API.

### 3.3. Default Values and Optional Parameters

There are three commonly used approaches:

**Approach A – provide defaultValue:**

```java
@RequestParam(name = "page", defaultValue = "1") int page
```

If the query parameter is not sent or has an empty value, Spring uses the default value according to the annotation's rules. When `defaultValue` is present, `required` is implicitly turned into `false`.

**Approach B – required=false:**

```java
@RequestParam(name = "page", required = false) Integer page
```

When the parameter is missing, the value can be `null`. Use wrapper types `Integer`, `Long`, or a suitable nullable type; **do not use primitives** `int`/`long` if you want to receive null.

**Approach C – Optional:**

```java
@RequestParam(name = "page") Optional<Integer> page
```

When the query parameter is absent, Spring provides `Optional.empty()`. For annotations that have a `required` attribute, `Optional<T>` is supported and is equivalent to `required=false`. There is no need to repeat both `required=false` and `Optional` unless you want to make the intent explicit for readers.

| Request | Declaration | Expected result |
| --- | --- | --- |
| `?page=4` | `int page` | `4` |
| Without `page` | `defaultValue="1"` | `1` |
| Without `page` | `required=false, Integer` | `null` |
| Without `page` | `Optional<Integer>` | `Optional.empty()` |
| `?page=abc` | `int page` | Conversion error, usually HTTP 400 |
| `?page=` | `defaultValue="1"` | Uses default value |

**Do not use a primitive with required=false to represent an absent value.** If you need to distinguish "not sent", "sent empty", and "sent a valid value", use an appropriate type and define the contract clearly.

### 3.4. A Query Parameter with Multiple Values

The client can send the same name multiple times:

```http
GET /products?tag=reactor&tag=webflux&tag=spring
```

Use an array or collection:

```java
@GetMapping("/products")
public Mono<List<String>> products(
        @RequestParam(name = "tag", required = false)
        List<String> tags) {

    List<String> safeTags =
            tags == null ? List.of() : List.copyOf(tags);

    return Mono.just(safeTags);
}
```

With the request above, the list can be `["reactor", "webflux", "spring"]`. You can use `String[]` if appropriate. For repeated parameters, a collection expresses the intent more clearly.

### 3.5. Reading All Query Parameters

If the method needs the whole query map instead of one key:

```java
@GetMapping("/search")
public Mono<Map<String, List<String>>> search(
        @RequestParam MultiValueMap<String, String> params) {

    Map<String, List<String>> result = new LinkedHashMap<>();
    params.forEach((name, values) ->
            result.put(name, List.copyOf(values)));

    return Mono.just(result);
}
```

When `@RequestParam` does not specify a name on a `Map<String,String>` or `MultiValueMap<String,String>` parameter, Spring populates all query parameters into the map. `MultiValueMap` keeps multiple values of the same name; `Map<String,String>` expresses only one value per key and is therefore unsuitable if the API allows repetition.

This is a useful choice for dynamic search filters, but if the API has a stable schema, explicit parameters or a DTO are usually easier to validate and maintain.

### 3.6. Encoding and Empty Values

The query string is encoded according to URI rules. Special characters, spaces, and Vietnamese text must be properly URL-encoded on the client. Do not decode multiple times yourself; Spring already handles this through the request mapping mechanism.

Distinguish:

- Key absent: `/products`.
- Key with an empty value: `/products?keyword=`.
- Key with spaces or an encoded string: check the value after decoding.
- Repeated key: `?tag=a&tag=b`.

With `String`, an empty string may remain an empty string. With numeric or UUID types, an empty string after conversion may be treated as a missing value if the converter returns null. If the business logic needs to distinguish them precisely, use `String` or a wrapper type, inspect the input, and then convert according to your own rules.

## 4. Using @RequestHeader to Read HTTP Headers

### 4.1. Reading One Header

Example:

```java
@GetMapping("/client-info")
public Mono<String> clientInfo(
        @RequestHeader("Accept-Language") String language,
        @RequestHeader("X-Request-Id") String requestId) {

    return Mono.just(
            "language=" + language + ", requestId=" + requestId);
}
```

Spring binds the header value to the method parameter. Header names in HTTP are case-insensitive, so `X-Request-Id` and `x-request-id` represent the same header name per the HTTP standard.

If a required header is missing, the request usually receives HTTP 400. You can use `required=false`, `Optional<T>`, or `defaultValue` just as with query parameters.

### 4.2. Type Conversion

Headers usually arrive as strings. If the Java parameter has a type other than `String`, Spring applies its conversion system:

```java
@GetMapping("/poll")
public Mono<String> poll(
        @RequestHeader("Keep-Alive") long keepAlive,
        @RequestHeader(name = "X-Retry", defaultValue = "0")
        int retry) {

    return Mono.just(
            "keepAlive=" + keepAlive + ", retry=" + retry);
}
```

Automatic conversion avoids manual parsing in the controller. If the header cannot be converted to the target type, Spring reports a binding/conversion error and normally returns HTTP 400.

### 4.3. Multi-Value Headers

You can use an array or collection for headers that have multiple values:

```java
@GetMapping("/accept")
public Mono<List<String>> accept(
        @RequestHeader("Accept") List<String> acceptValues) {

    return Mono.just(List.copyOf(acceptValues));
}
```

Spring supports converting some comma-separated header strings into arrays/collections. However, **do not assume every header can be joined or split by commas**. The meaning of a list depends on the definition of each header.

If you need to preserve all header values, you can use `HttpHeaders` or `MultiValueMap<String,String>`:

```java
@GetMapping("/headers")
public Mono<Map<String, List<String>>> headers(
        @RequestHeader HttpHeaders headers) {

    Map<String, List<String>> result =
            new TreeMap<>(String.CASE_INSENSITIVE_ORDER);

    headers.forEach((name, values) ->
            result.put(name, List.copyOf(values)));

    return Mono.just(result);
}
```

Declare `@RequestHeader HttpHeaders headers` without a specific header name to receive the request's header collection. `HttpHeaders` is the more appropriate structure when you need to access many headers, including repeated values.

**Warning:** do not split complex headers by commas yourself if the header's grammar can contain commas inside a value. Use an API/formatter suited to that header. For sensitive headers such as Authorization, avoid logging the raw value.

### 4.4. Some Commonly Seen Headers

| Header | Common meaning | How to use |
| --- | --- | --- |
| `Accept` | Content types the client accepts | Content negotiation |
| `Accept-Language` | Language preferred by the client | Locale/response localization |
| `Authorization` | Authentication credentials | Let Spring Security or the auth mechanism handle it; do not log tokens |
| `X-Request-Id` | Correlation ID by application convention | Log/tracing tracking; verify the source if used for trusted logic |
| `If-None-Match` | Validator for conditional caching | ETag/304 handling |
| `Content-Type` | Content type of the request body | Check body format |

Custom headers such as `X-Request-Id` are only an application convention and carry no security meaning on their own. Do not use a client-sent header to prove identity or permissions.

## 5. Using @CookieValue to Read a Cookie

### 5.1. Reading a Cookie by Name

Example of a request with a header:

```http
Cookie: theme=dark; session=opaque-session-value
```

Controller reads one cookie:

```java
@GetMapping("/theme")
public Mono<String> theme(
        @CookieValue("theme") String theme) {

    return Mono.just("theme=" + theme);
}
```

Spring binds **the value of the cookie named `theme`** to the parameter. You do not have to parse the whole Cookie header string yourself.

### 5.2. Required, Optional, and Default Cookies

Similar to the other annotations:

```java
@GetMapping("/session")
public Mono<String> session(
        @CookieValue("session") String sessionId,
        @CookieValue(name = "theme", defaultValue = "light")
        String theme,
        @CookieValue(name = "campaign", required = false)
        String campaign) {

    return Mono.just("session=" + sessionId
            + ", theme=" + theme
            + ", campaign=" + campaign);
}
```

- `session` is required by default; a missing cookie usually receives HTTP 400.
- `theme` uses `light` if the cookie is absent or has an empty value according to default-value rules; declaring a default implicitly sets required to false.
- `campaign` is optional; if missing, the Java value can be null.

You can use `Optional<String>` for an optional cookie if you want to represent absence explicitly:

```java
@CookieValue("campaign") Optional<String> campaign
```

### 5.3. Reading All Cookies

`@CookieValue` is suitable when you need one cookie whose name is known. If you need to iterate over all cookies, use `ServerHttpRequest` or `ServerWebExchange`:

```java
@GetMapping("/cookies")
public Mono<Map<String, List<String>>> cookies(
        ServerHttpRequest request) {

    Map<String, List<String>> result = new TreeMap<>();

    request.getCookies().forEach((name, cookies) ->
            result.put(name, cookies.stream()
                    .map(HttpCookie::getValue)
                    .toList()));

    return Mono.just(result);
}
```

In WebFlux, `ServerHttpRequest.getCookies()` returns a multi-value structure keyed by cookie name, using Spring's `HttpCookie` type. This is the right API if you need to iterate over all cookies or read request-level information. Do not use `javax.servlet.http.Cookie` in a WebFlux controller; that is a Servlet API.

### 5.4. Cookie Value Does Not Contain Cookie Attributes

Clients usually send `name=value` pairs in the request Cookie header. Attributes such as `Secure`, `HttpOnly`, `SameSite`, `Path`, and `Domain` are set by the server via the Set-Cookie response header to control how the browser stores and sends cookies; they **are not sent back as attributes in the request Cookie header**.

Therefore, `@CookieValue("session")` reads only the cookie value. It does not tell you whether the cookie was set with `HttpOnly` or what `SameSite` was used. If you need to change cookie attributes, create a response cookie with `ResponseCookie`/the `Set-Cookie` response header; do not modify the received value expecting to change browser attributes.

## 6. Type Conversion: From HTTP Strings to Java Types

All three annotations may need conversion from string data to the parameter type:

```java
@GetMapping("/report")
public Mono<String> report(
        @RequestParam("count") int count,
        @RequestHeader("X-Enabled") boolean enabled,
        @CookieValue("version") long version) {

    return Mono.just(count + ":" + enabled + ":" + version);
}
```

The example above requires:

- Query `count` converted to an integer.
- Header `X-Enabled` converted to a boolean.
- Cookie `version` converted to a long.

Spring uses the `ConversionService`/converters and formatters system. Common simple types are supported out of the box. When the parameter is a custom type, you can register a converter or formatter.

### 6.1. Handling Conversion Errors

If the client sends:

```http
GET /report?count=abc
X-Enabled: maybe
Cookie: version=not-a-number
```

Spring cannot convert those values to the required Java types. The request is usually handled as HTTP 400 Bad Request; the controller may not have been invoked because resolving method arguments failed.

Do not catch every error and silently assign 0 or false. That can turn an invalid request into one that is syntactically valid but business-wise wrong. Let binding errors be reported clearly or handle them via an exception handler with an appropriate message.

### 6.2. Empty Strings and Null After Conversion

An easily overlooked detail is that an empty string can be turned into null by a converter for some types such as `Long` or `UUID`. Spring treats a null result after conversion the same as a missing input value for required parameters. Since Spring Framework 5.3, non-null parameters are also checked after conversion.

If you want to allow null, declare `required=false` on the annotation or use `@Nullable` appropriately. With primitives, null cannot be received. With complex business types, clearly distinguish an empty string, an absent key, and a malformed value.

### 6.3. Registering a Custom Converter or Formatter

Suppose the API accepts the query parameter `direction=asc` or `direction=desc` and wants to convert it to an enum:

```java
public enum SortDirection {
    ASC, DESC
}
```

Register the converter:

```java
@Configuration
public class WebConfig implements WebFluxConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(
                String.class,
                SortDirection.class,
                value -> SortDirection.valueOf(
                        value.trim().toUpperCase(Locale.ROOT)));
    }
}
```

Then the controller can declare:

```java
@GetMapping("/sorted-products")
public Mono<String> sortedProducts(
        @RequestParam("direction") SortDirection direction) {

    return Mono.just(direction.name());
}
```

This is a simple converter example. In a real application, decide clearly whether to accept uppercase/lowercase, whitespace, aliases, and invalid values. Do not use a converter to hide errors with a default enum not requested by the client.

## 7. Complete Spring Boot WebFlux Example

The example below combines all three annotations in one controller. It receives page and tags from the query, request ID/language from headers, and theme from a cookie.

### 7.1. Project Structure

The example is for Java 17+ and Spring Boot 3.x, using Spring Boot's dependency management:

```text
request-binding-demo/
  src/
    main/
      java/demo/
        RequestBindingApplication.java
        RequestMetadataController.java
    test/
      java/demo/
        RequestMetadataControllerTest.java
  build.gradle
```

In Gradle, the project needs the main dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

This dependency snippet assumes the project already configures a compatible Spring Boot plugin and BOM. Let the BOM manage the versions of Spring Framework, Reactor, Jackson, and test libraries; do not add a different incompatible Spring version yourself.

### 7.2. Application Class

File `src/main/java/demo/RequestBindingApplication.java`:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RequestBindingApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                RequestBindingApplication.class, args);
    }
}
```

### 7.3. Controller

File `src/main/java/demo/RequestMetadataController.java`:

```java
package demo;

import java.util.List;
import java.util.Map;
import java.util.TreeMap;

import org.springframework.http.HttpCookie;
import org.springframework.http.HttpHeaders;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.web.bind.annotation.CookieValue;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class RequestMetadataController {

    @GetMapping("/api/demo")
    public Mono<DemoResponse> demo(
            @RequestParam(name = "page", defaultValue = "1")
            int page,
            @RequestParam(name = "tag", required = false)
            List<String> tags,
            @RequestHeader(name = "X-Request-Id", required = false)
            String requestId,
            @RequestHeader(name = "Accept-Language",
                    defaultValue = "vi")
            String language,
            @CookieValue(name = "theme", defaultValue = "light")
            String theme) {

        List<String> safeTags =
                tags == null ? List.of() : List.copyOf(tags);

        return Mono.just(new DemoResponse(
                page, safeTags, requestId, language, theme));
    }

    @GetMapping("/api/required")
    public Mono<String> required(
            @RequestParam("code") int code,
            @RequestHeader("X-Client") String client,
            @CookieValue("session") String session) {

        return Mono.just(
                "code=" + code
                        + ";client=" + client
                        + ";session=" + session);
    }

    @GetMapping("/api/all-headers")
    public Mono<Map<String, List<String>>> allHeaders(
            @RequestHeader HttpHeaders headers) {

        Map<String, List<String>> result =
                new TreeMap<>(String.CASE_INSENSITIVE_ORDER);

        headers.forEach((name, values) ->
                result.put(name, List.copyOf(values)));

        return Mono.just(result);
    }

    @GetMapping("/api/all-cookies")
    public Mono<Map<String, List<String>>> allCookies(
            ServerHttpRequest request) {

        Map<String, List<String>> result = new TreeMap<>();

        request.getCookies().forEach((name, cookies) ->
                result.put(name, cookies.stream()
                        .map(HttpCookie::getValue)
                        .toList()));

        return Mono.just(result);
    }

    public record DemoResponse(
            int page,
            List<String> tags,
            String requestId,
            String language,
            String theme) {
    }
}
```

Explanation of the `/api/demo` endpoint's parameters:

- `page` has a default of 1; the query does not need to send page.
- `tag` is optional; multiple repeated values are bound into a List.
- `X-Request-Id` is optional; if missing, the response may contain null in the requestId field.
- `Accept-Language` defaults to vi.
- The `theme` cookie defaults to light.

The other two endpoints illustrate how to receive all headers through `HttpHeaders` and all cookies through `ServerHttpRequest`. The `/api/required` endpoint intentionally requires all of query, header, and cookie to demonstrate missing-parameter errors.

### 7.4. Running and Calling the Endpoints

Run the application:

```bash
./gradlew bootRun
```

Call the endpoint with full data:

```bash
curl -i 'http://localhost:8080/api/demo?page=2&tag=reactor&tag=webflux'   -H 'X-Request-Id: req-42'   -H 'Accept-Language: vi'   -b 'theme=dark'
```

Main JSON response of the example:

```json
{
  "page": 2,
  "tags": ["reactor", "webflux"],
  "requestId": "req-42",
  "language": "vi",
  "theme": "dark"
}
```

Try calling without passing query/header/cookie:

```bash
curl -i 'http://localhost:8080/api/demo'
```

The result has page 1, tags as an empty array, requestId as null, language as vi, and theme as light. This endpoint allows optional/default fields to be omitted; the `/api/required` endpoint does not.

Call the endpoint requiring all three sources:

```bash
curl -i 'http://localhost:8080/api/required?code=7'   -H 'X-Client: web'   -b 'session=session-123'
```

If all three values are present, the body is:

```text
code=7;client=web;session=session-123
```

If `code`, `X-Client`, or the `session` cookie is missing, the request does not satisfy the required contract and usually receives HTTP 400.

### 7.5. Testing Binding with WebTestClient

File `src/test/java/demo/RequestMetadataControllerTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.http.MediaType.APPLICATION_JSON;

@WebFluxTest(RequestMetadataController.class)
class RequestMetadataControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void bindsQueryHeaderAndCookie() {
        client.get()
                .uri("/api/demo?page=2&tag=reactor&tag=webflux")
                .header("X-Request-Id", "req-42")
                .header("Accept-Language", "vi")
                .cookie("theme", "dark")
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .contentTypeCompatibleWith(APPLICATION_JSON)
                .expectBody()
                .jsonPath("$.page").isEqualTo(2)
                .jsonPath("$.tags[0]").isEqualTo("reactor")
                .jsonPath("$.tags[1]").isEqualTo("webflux")
                .jsonPath("$.requestId").isEqualTo("req-42")
                .jsonPath("$.language").isEqualTo("vi")
                .jsonPath("$.theme").isEqualTo("dark");
    }

    @Test
    void usesDefaultsWhenValuesAreAbsent() {
        client.get()
                .uri("/api/demo")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.page").isEqualTo(1)
                .jsonPath("$.tags").isEmpty()
                .jsonPath("$.language").isEqualTo("vi")
                .jsonPath("$.theme").isEqualTo("light");
    }

    @Test
    void rejectsInvalidIntegerConversion() {
        client.get()
                .uri("/api/demo?page=not-a-number")
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void rejectsMissingRequiredQueryHeaderOrCookie() {
        client.get()
                .uri("/api/required")
                .header("X-Client", "web")
                .cookie("session", "session-123")
                .exchange()
                .expectStatus().isBadRequest();

        client.get()
                .uri("/api/required?code=7")
                .cookie("session", "session-123")
                .exchange()
                .expectStatus().isBadRequest();

        client.get()
                .uri("/api/required?code=7")
                .header("X-Client", "web")
                .exchange()
                .expectStatus().isBadRequest();
    }
}
```

This test uses `@WebFluxTest` to initialize the controller and WebTestClient in the test context. The `spring-boot-starter-test` dependency provides JUnit and the corresponding test support. If the project has security filters or custom WebFlux configuration, you may need to import/configure them according to the project's test slice.

Run the tests:

```bash
./gradlew test
```

The tests verify binding multiple query values, headers, cookies, default values, and conversion/required errors. There is no need to spin up a real server for basic binding tests.

## 8. When Do You Need to Access ServerWebExchange Directly?

The three annotations are very convenient for specific values whose names are known. If you need more information or need to process data at the request level, the controller can accept:

```java
@GetMapping("/request-details")
public Mono<String> details(ServerWebExchange exchange) {
    String path = exchange.getRequest().getPath().value();
    String method = exchange.getRequest().getMethod().name();

    return Mono.just(method + " " + path);
}
```

`ServerWebExchange` contains the request, response, session, and related information. Some cases where you should use it directly:

- Needing to read many cookies, headers, or query parameters.
- Needing the request URI, method, remote address, or attributes.
- Needing to control response headers/status or the session.
- Needing to work with form/multipart using the WebFlux API.
- Needing to inspect a header/cookie with multiple values that a single annotation does not express adequately.

Do not accept the exchange and parse everything manually in every controller if annotations already solve it clearly. Using a narrower abstraction makes method signatures easier to read and test.

## 9. Combining with Validation and Error Handling

**Type conversion is not synonymous with business validation.** Converting the string `"0"` to int 0 succeeds as a data type, but page 0 may be invalid for your API.

You can check explicitly in the service/controller:

```java
@GetMapping("/products")
public Mono<List<ProductDto>> products(
        @RequestParam(defaultValue = "1") int page) {

    if (page < 1) {
        return Mono.error(new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "page must be greater than or equal to 1"));
    }

    return productService.findPage(page);
}
```

This is an **illustrative snippet** that requires `ProductDto` and `productService` defined by the application. Another approach is using Bean Validation with suitable constraints and configuring method validation compatible with the running Spring Framework version.

Common errors:

- Missing required parameter: usually HTTP 400.
- Unconvertible string: usually HTTP 400.
- Value converts successfully but violates business rules: validation/service needs to decide the response.
- Logically invalid header/cookie: must be checked explicitly, rather than relying only on Spring binding succeeding.

Use `@RestControllerAdvice` or WebFlux's exception handling mechanism to standardize error responses, avoiding returning stack traces or internal information to the client. Do not catch every exception and turn it into HTTP 200.

## 10. Security When Receiving Headers and Cookies

### 10.1. Do Not Trust Client-Sent Data

Query parameters, headers, and cookie values are all untrusted input data. They can be modified by the client or sent directly by a non-browser script. Validate length, format, value range, and permission to use before passing them into business logic.

### 10.2. Do Not Use Request ID as Identity

A client can send `X-Request-Id: admin-request` or any arbitrary string itself. A correlation ID is useful for logging, but it does not prove the sender is an admin or that the request is trusted. If you need identity, use standard authentication/authorization such as Spring Security.

### 10.3. Session Cookies Need Protection

Cookies carrying a session identifier or sensitive information should have an appropriate policy:

- **HttpOnly:** prevents JavaScript from reading the cookie via normal browser APIs; does not prevent the server from reading the cookie.
- **Secure:** sends the cookie only over HTTPS connections per browser policy.
- **SameSite:** restricts certain cross-site cookie sending cases, helping reduce CSRF, though it does not replace a full CSRF defense.
- **Path/Domain:** limits the scope where the cookie is sent.
- **Max-Age/Expires:** controls storage duration.

The server can create a secure cookie using ResponseCookie:

```java
ResponseCookie sessionCookie = ResponseCookie
        .from("session", opaqueSessionId)
        .httpOnly(true)
        .secure(true)
        .sameSite("Lax")
        .path("/")
        .maxAge(Duration.ofHours(8))
        .build();

return ResponseEntity.ok()
        .header(HttpHeaders.SET_COOKIE, sessionCookie.toString())
        .body("session created");
```

This is an illustrative snippet inside a handler that requires importing the corresponding types and having an `opaqueSessionId` generated by the session system. Do not store sensitive access tokens in cookies that can be read by JavaScript; do not log session cookies or Authorization values.

### 10.4. CSRF When Using Cookie-Based Authentication

Browsers can automatically send cookies according to the domain/path scope and SameSite policy. Therefore, if the backend uses cookies for authentication, evaluate CSRF for state-changing operations. `@CookieValue` only helps read the cookie; it does not verify signatures, check sessions, prevent CSRF, or grant permissions.

### 10.5. Forwarded Headers and Proxies

Headers such as `Forwarded` or `X-Forwarded-For` can be sent by a reverse proxy, but can also be spoofed by clients if the application trusts every source. Trust forwarded headers only from configured/trusted proxies. Do not use client-sent IP/headers as the sole authentication mechanism.

## 11. Common Mistakes

| Mistake | Consequence | How to fix |
| --- | --- | --- |
| Thinking `@RequestParam` in WebFlux reads form fields like MVC | Controller does not receive form data as expected | Use `@ModelAttribute`/form data API or `@RequestPart` for multipart |
| Forgetting the query/header/cookie name | Wrong binding or parameter is not resolved | Declare `name/value` explicitly when the API name differs from the variable name |
| Using a primitive for an optional value | Cannot represent null when missing | Use a wrapper, `Optional`, or a default value |
| Missing required parameter | Handler is not called, usually returns 400 | Choose required, Optional, or defaultValue per the contract |
| Sending a string of the wrong type | Conversion error | Validate input and return a structured 400 error |
| Thinking List always has exactly one element | Drops repeated query values | Use List/array/MultiValueMap appropriately |
| Splitting every header by commas yourself | Can break header grammar | Use HttpHeaders or a header-compliant parser |
| Using @CookieValue to read all cookies | Gets only one cookie by name | Use ServerHttpRequest.getCookies() |
| Using Servlet Cookie in WebFlux | Mixes Servlet API and reactive stack | Use Spring HttpCookie/ServerHttpRequest |
| Trusting a cookie as authenticated data | Risk of session/logic spoofing | Validate the session and permissions at the security layer |
| Logging Authorization or session cookies | Credential leakage | Redact sensitive data |
| Thinking HttpOnly prevents the server from reading the cookie | Misunderstands cookie attributes | HttpOnly restricts browser-side JavaScript, not the server |
| Trusting X-Forwarded-For from every client | Source address can be spoofed | Trust only configured proxies |
| Arbitrarily wrapping query/header/cookie arguments in Mono | Argument resolver does not expect a reactive wrapper for non-blocking data | Use ordinary value types or Optional for these parameters |

## 12. Endpoint Design Checklist

Before finishing a controller, check:

1. Is the data in the query, header, cookie, body, or path? Choose the right annotation.
2. If using WebFlux, did you remember that `@RequestParam` reads only query parameters?
3. Is the parameter required? If not, choose defaultValue, required=false, or Optional.
4. Does the Java type reflect the valid value range? Avoid primitives for nullable parameters.
5. Can values repeat? Choose List/array/MultiValueMap/HttpHeaders appropriately.
6. Can type conversion fail? Does the API return a clear 400 error?
7. Is there business validation after conversion?
8. Do cookies/sessions and headers have sensitive data? Have you avoided logging them and protected them properly?
9. If all data is needed, should you use map/HttpHeaders/ServerHttpRequest instead of writing many separate parameters?
10. Do tests cover normal, missing, empty, repeated, and malformed values, as well as missing cookies/headers?

## 13. Selection Summary

| Need | Recommended declaration to start with |
| --- | --- |
| One query parameter | `@RequestParam("page") int page` |
| Query parameter with a default | `@RequestParam(defaultValue = "1") int page` |
| Optional query parameter | `@RequestParam(required = false) Integer page` or `Optional<Integer>` |
| Multiple values for the same query key | `@RequestParam("tag") List<String> tags` |
| All query parameters | `@RequestParam MultiValueMap<String,String> params` |
| One request header | `@RequestHeader("X-Request-Id") String requestId` |
| Optional header | `@RequestHeader(value="X-Request-Id", required=false) String requestId` |
| All request headers | `@RequestHeader HttpHeaders headers` |
| One cookie | `@CookieValue("theme") String theme` |
| Cookie with a default | `@CookieValue(value="theme", defaultValue="light") String theme` |
| All cookies | `ServerHttpRequest.getCookies()` |

## 14. References

- [Spring Framework – WebFlux Method Arguments](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/arguments.html): list of supported method argument types and the scope of reactive wrappers.
- [Spring Framework – @RequestParam in WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/requestparam.html): query parameters, required/default, Optional, Map, and MultiValueMap.
- [Spring Framework – @RequestHeader in WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/requestheader.html): binding one header, multiple values, HttpHeaders, and type conversion.
- [Spring Framework – @CookieValue in WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/cookievalue.html): binding a cookie by name and type conversion.
- [Spring Framework – Type Conversion in WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/typeconversion.html): converters, formatters, empty strings, and null after conversion.
- [Spring Framework – WebFlux Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods.html): overview of handler methods and argument/return value types.

## 15. Key Takeaways

Three annotations address three different data sources: **`@RequestParam` reads query parameters; `@RequestHeader` reads request headers; `@CookieValue` reads one cookie by name**. Spring automatically binds and converts values to Java parameter types, while providing clear rules for required, default, and Optional.

When designing a WebFlux controller, especially remember that `@RequestParam` does not replace reading form data/multipart as in Servlet MVC. Use collections when data repeats, use `HttpHeaders` or `ServerHttpRequest` when all metadata is needed, and always validate data arriving from the client. For cookies/sessions, add HttpOnly, Secure, SameSite, CSRF protection, and verify sessions at the security layer.
