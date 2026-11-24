# Reading Path Variables, Query Parameters, Headers, and Cookies in Spring Boot

## 1. Goals and Overview

An HTTP request has more than just a body. A Spring Boot endpoint frequently needs to read **path variables**, **query parameters**, **HTTP headers**, and **cookies** to identify resources, filter or paginate results, inspect request metadata, and track client preferences. In annotated controllers in Spring MVC and Spring WebFlux, the common annotations are:

- **@PathVariable**: extracts a matched value from the path template, such as itemId in /api/items/42.
- **@RequestParam**: extracts a query parameter, such as page=2 or tag=java in ?page=2&tag=java.
- **@RequestHeader**: extracts an HTTP request header, such as X-Request-Id: req-42.
- **@CookieValue**: extracts a request cookie by name, such as Cookie: theme=dark.

These four sources differ in their location in the HTTP request, whether values can repeat, their semantics, and their level of trustworthiness. Reading from the right data source is only the first step; you must also perform **type conversion, default assignment, validation, length limiting, and security checks** before passing the data into business logic.

This lesson uses **Java 17+, Spring Boot 3.3.x, and Spring Framework 6.1.x**. The complete runnable example uses Spring MVC with embedded Tomcat, followed by a comparison of the annotation-based and functional APIs in Spring WebFlux. This topic focuses on **reading HTTP request data**, not replacing full authentication, an API gateway, or a routing framework.

By the end of this lesson, you will be able to:

1. Choose the appropriate annotation and Java type for path, query, header, and cookie values.
2. Distinguish between missing, empty, invalid-type, and multi-valued cases.
3. Explain how DispatcherServlet/DispatcherHandler resolves arguments.
4. Safely read encoded input and mitigate risks from trusting client-controlled headers/cookies.
5. Build a working Java 17 REST controller and test it with MockMvc and cURL.
6. Recognize the differences when using Spring WebFlux annotated controllers and functional endpoints.

## 2. Examining a Concrete HTTP Request

Suppose a client sends:

~~~http
GET /api/items/42?page=2&tag=spring&tag=java HTTP/1.1
Host: localhost:8080
Accept: application/json
X-Request-Id: req-42
Cookie: theme=dark; locale=vi
~~~

Parts to distinguish:

| Source | Part in request | Example value | Spring annotation |
| --- | --- | --- | --- |
| Path variable | Path matching /api/items/{itemId} | itemId = "42" | @PathVariable("itemId") |
| Query parameter | Portion after ? in the URL | page = "2" | @RequestParam("page") |
| Repeated query | Multiple pairs with the same key | tag = ["spring", "java"] | @RequestParam("tag") List<String> |
| Header | HTTP metadata line | X-Request-Id = "req-42" | @RequestHeader("X-Request-Id") |
| Cookie | Value in the request Cookie header | theme = "dark" | @CookieValue("theme") |

**Not everything is a path parameter.** The string page=2 appears in the URL, but it belongs to the **query string**, not a path segment. Cookies are sent by the client via the Cookie header, yet @CookieValue is a dedicated abstraction that extracts a single cookie by name; @RequestHeader("Cookie") returns the raw header string rather than an application-level parsed cookie value.

An HTTP request body, such as JSON for a POST request, is a separate source: it is normally read with @RequestBody, not by substituting @RequestParam or @CookieValue.

### Distinguishing URL, URI, and the Decoded Portion

URL:

~~~text
http://localhost:8080/api/items/42?page=2&tag=spring
                           ^^^^^^^^^^^^ ^^^^^^^^^^^^^^^^^
                           request path  query string
~~~

The framework matches the path template against the path portion; the query string **does not create a new path segment**. Encoding, proxy rewrites, context path, and the path-matching strategy can all affect the result; these are discussed in detail below.

## 3. @PathVariable: Extracting Values from the URL Path

### 3.1 Basic Declaration

~~~java
@GetMapping("/api/items/{itemId}")
public String find(@PathVariable("itemId") long itemId) {
    return "item=" + itemId;
}
~~~

This is an **illustrative method** and must be placed inside a @RestController with appropriate imports. On GET /api/items/42, Spring finds the matching mapping and converts the path string "42" into long 42.

Key points:

- **{itemId}** is the variable name in the URI template.
- **@PathVariable("itemId")** binds the Java parameter to that variable.
- **long** instructs Spring to perform type conversion. If /api/items/abc is received, binding to long fails and the framework typically returns HTTP 400.
- If the route does not match, the controller method is not selected; a route mismatch is distinct from a conversion failure.

Specifying the name explicitly in the annotation keeps the code independent of whether the compiler preserves Java parameter names:

~~~java
@PathVariable("itemId") long itemId
~~~

compared to:

~~~java
@PathVariable long itemId
~~~

Both can work in projects configured to preserve parameter names, though the first form is more explicit and easier to verify.

### 3.2 Multiple Path Variables

~~~java
@GetMapping("/shops/{shopId}/items/{itemId}")
public String find(
        @PathVariable("shopId") String shopId,
        @PathVariable("itemId") long itemId) {
    return shopId + ":" + itemId;
}
~~~

For example, GET /shops/hn-01/items/42 returns the body "hn-01:42" when the method belongs to a @RestController or has @ResponseBody. The variable names in the route and the annotations must match.

### 3.3 Data Types and Conversion Errors

Spring supports many common conversions:

- String for alphanumeric codes.
- long, int, UUID, enum (depending on enum naming and registered converters).
- Domain Java types with a registered Converter/Formatter.
- Optional<T> or other designs when the framework and mapping support them.

With @PathVariable long, if the path matches the route template but the value cannot be parsed, Spring MVC typically throws MethodArgumentTypeMismatchException or a conversion-related exception and produces HTTP 400. Do not write try/catch NumberFormatException in every controller when the framework already handles binding; customize the error contract if clients need a uniform JSON error format.

### 3.4 Are Path Variables Always Optional?

Normally, a path variable is a **required component for the route to match**. Using @PathVariable(required=false) does not automatically make "/items/{id}" match "/items" unless you also define the alternative mapping. If there are two distinct routes, declare them explicitly:

~~~java
@GetMapping({"/api/items", "/api/items/{itemId}"})
public String listOrFind(
        @PathVariable(name = "itemId", required = false) Long itemId) {
    return itemId == null ? "all" : "item=" + itemId;
}
~~~

This snippet must be placed in an appropriate controller. Use the wrapper Long rather than the primitive long when the value can be absent. However, REST design is usually clearer when GET /items and GET /items/{id} are separated into two methods.

### 3.5 Special Characters and Encoded Slashes

Paths can contain percent-encoded characters. Never assume %2F is always treated as a literal "/" within a single path variable: proxies, servlet containers, firewalls/path matching, and framework versions can handle encoded slashes differently. If an identifier needs to contain special characters or slashes, consider designing URL-safe IDs or using a query parameter as appropriate.

Never concatenate raw path variables directly into OS file paths, SQL queries, shell commands, or internal URLs without context-appropriate validation/encoding. The framework helps extract the value; **it does not make every value safe for every sink**.

## 4. @RequestParam: Extracting Query Parameters

### 4.1 Required Parameters and Default Parameters

~~~java
@GetMapping("/api/search")
public String search(
        @RequestParam("q") String keyword,
        @RequestParam(name = "page", defaultValue = "1") int page) {
    return keyword + ":" + page;
}
~~~

This is an illustrative method. For GET /api/search?q=spring&page=3, the corresponding Java values are "spring" and 3.

By default, @RequestParam has no defaultValue and has required=true; if a required query parameter is missing, Spring MVC typically returns HTTP 400 with MissingServletRequestParameterException. WebFlux has corresponding exceptions in the reactive stack; not every MVC exception class applies in WebFlux.

When declaring:

~~~java
@RequestParam(name = "page", defaultValue = "1") int page
~~~

Spring uses the default "1" when no value is provided and in empty-value cases where default handling applies. defaultValue also implies that the parameter is no longer required in annotation semantics. If the client sends page=abc, the value is present but of the wrong type; **defaultValue does not mean invalid-type inputs are replaced with 1**.

### 4.2 required=false and Optional<T>

Two common ways to represent a potentially missing value:

~~~java
@RequestParam(name = "sort", required = false) String sort
~~~

~~~java
@RequestParam(name = "sort") Optional<String> sort
~~~

The snippets above are parameter declarations, not standalone classes. With String and required=false, your code must handle null safely; Optional<String> expresses presence/absence more explicitly. Avoid primitive int/boolean if you actually want to accept null; use wrapper types Integer/Boolean or defaultValue instead.

**A missing value differs from an empty value.** For example, "?q=" is not completely identical to omitting q; default/required/conversion behavior depends on the annotation and parameter type. Test the exact API rules you intend to support rather than assuming all cases behave identically.

### 4.3 Repeated Query Parameters

Example:

~~~text
GET /api/items?tag=spring&tag=java&tag=backend
~~~

A common way to read this:

~~~java
@RequestParam(name = "tag", required = false)
List<String> tags
~~~

Spring can bind multiple values into List<String>. If missing, handle null/empty explicitly at the controller boundary. Do not assume every query key always has only one value; an API may allow repetition, and frameworks/clients may have different conventions regarding comma-separated lists.

When you need **all query parameters** while preserving duplicate keys, in Spring MVC you can use:

~~~java
@RequestParam MultiValueMap<String, String> query
~~~

This requires importing org.springframework.util.MultiValueMap. A plain Map<String,String> cannot represent multiple values for the same key. For public endpoints, accepting specific named parameters selectively is generally safer and easier to document than accepting an unbounded Map.

### 4.4 Query Strings and Form Data Are Not Always the Same

In the Spring MVC Servlet stack, @RequestParam can work with request parameters provided by the Servlet container, including the query string and form-encoded fields in appropriate situations. In Spring WebFlux, @RequestParam is tied to query parameters under reactive semantics; form data has its own API/binding mechanism. Do not write a library assuming both stacks always treat query strings and form bodies as a single source.

For JSON POST payloads, use a @RequestBody DTO; @RequestParam does not automatically deserialize a JSON object from the request body.

## 5. @RequestHeader: Reading HTTP Metadata

### 5.1 Reading a Single Header

~~~java
@GetMapping("/api/trace")
public String trace(
        @RequestHeader("X-Request-Id") String requestId) {
    return requestId;
}
~~~

Header names in HTTP are case-insensitive by specification. A client may send x-request-id instead of X-Request-Id and the HTTP layer treats them as the same header name, though specific casing/normalization can vary across proxies.

### 5.2 Optional Headers and Defaults

~~~java
@RequestHeader(name = "X-Request-Id", required = false)
String requestId
~~~

or:

~~~java
@RequestHeader(name = "X-Client-Version", defaultValue = "unknown")
String clientVersion
~~~

If the application uses a client-supplied request ID for logging, enforce length limits, allowed characters, and normalization; never blindly trust any string sent by a client. Headers can also be stripped, modified, or regenerated by proxies/gateways.

### 5.3 Multi-Valued Headers

HTTP defines headers that allow lists of values as well as headers with specialized syntax. Spring can provide:

~~~java
@RequestHeader HttpHeaders headers
~~~

or an appropriate MultiValueMap<String,String>. HttpHeaders is org.springframework.http.HttpHeaders and provides getFirst(name), get(name), and specialized accessors.

Do not split every header blindly on commas. For example, Set-Cookie syntax has special rules and cannot be parsed reliably with split(","). For Authorization, Content-Type, and headers with complex semantics, prefer framework/HTTP APIs instead of raw string parsing.

### 5.4 Common Headers

| Header | Common purpose | Notes |
| --- | --- | --- |
| Accept | Media types the client wants to receive | Spring uses content negotiation; 406 may occur |
| Content-Type | Media type of the request body | Critical for @RequestBody; 415 may occur |
| Authorization | Credentials/token | Handle via Spring Security; do not log or trust raw token strings blindly |
| X-Request-Id | Convention-based correlation/tracing | Validate, restrict length, generate a new ID if needed |
| If-None-Match | Conditional request/ETag | Use HTTP response/cache abstractions |
| If-Modified-Since | Time-based conditional request | Requires proper parser/semantics |
| Forwarded / X-Forwarded-* | Information from reverse proxies | Trust only when ingress proxies are controlled and trust is explicitly configured |

**Headers are data controlled by the sender or proxies**, not an authentication source by default. Reading a username from X-User-Id and assuming the user is authenticated is a security vulnerability if the gateway does not protect that header.

### 5.5 Should You Read All Headers?

A controller can accept HttpHeaders for inspection, but do not serialize the entire header map back to the client or dump it into logs. It may contain Authorization, Cookie, API keys, or sensitive information. Extracting only the required fields reduces coupling and data-leakage risk.

## 6. @CookieValue: Reading Request Cookies

### 6.1 How Are Cookies Sent?

After a server responds with an appropriate Set-Cookie header, the browser may send cookies on subsequent requests:

~~~http
Cookie: theme=dark; locale=vi
~~~

In an annotated controller:

~~~java
@GetMapping("/api/preferences")
public String preferences(
        @CookieValue(name = "theme", defaultValue = "light")
        String theme) {
    return theme;
}
~~~

When the request includes theme=dark, the method receives "dark". When the theme cookie is absent, defaultValue="light" is used.

### 6.2 How Do Cookies Differ from Headers?

- **Cookie** in a request carries name=value pairs sent by the client according to scope policy.
- **Set-Cookie** is a response header instructing the browser to store/update a cookie and its attributes.
- Attributes such as HttpOnly, Secure, SameSite, Path, Domain, and Max-Age appear in the **response Set-Cookie**, not as fields the client sends back in the Cookie header on every request.
- Browsers enforce rules for sending cookies based on domain/path/secure/SameSite and browser policies. Custom HTTP clients can still forge the Cookie header.

Example response setting a cookie:

~~~http
Set-Cookie: theme=dark; Path=/; SameSite=Lax
~~~

This header is illustrative only; for sensitive session cookies, HttpOnly, Secure over HTTPS, appropriate SameSite/CSRF design, and proper expiration are normally required. A simple UI theme cookie is not equivalent to a secure session cookie.

### 6.3 Setting Cookies with ResponseCookie

Spring provides org.springframework.http.ResponseCookie; a controller or filter can add it through the response API. Spring MVC example:

~~~java
ResponseCookie cookie = ResponseCookie.from("theme", "dark")
        .path("/")
        .httpOnly(false)
        .sameSite("Lax")
        .build();
response.addHeader(HttpHeaders.SET_COOKIE, cookie.toString());
~~~

This is a snippet inside a method that already has HttpServletResponse response, requiring imports. In Spring WebFlux, response.getCookies().add(...) is the appropriate way on ServerHttpResponse. For a session cookie, choosing httpOnly(false) as in the theme example is **not** appropriate for a credential cookie; enable HttpOnly and Secure as required by the use case.

### 6.4 Cookies Are Not Inherently a Trusted Identity Source

A client can place "role=admin" or "userId=42" in the Cookie header and send it to the server. **You cannot authorize access based on unverified cookie text**. A session ID must be verified against server-side session storage or an authenticated/integrity-protected token mechanism; use Spring Security and proper CSRF defenses.

For preference data such as UI themes, whitelist allowed values ("light", "dark"), limit length, and avoid passing unvalidated cookie values into HTML, SQL, or other headers.

### 6.5 Cookies with the Same Name and Scope

In practice, multiple cookies with the same name but different Path/Domain attributes can exist; a request may carry multiple pairs with the same name. Do not build business logic assuming "the first cookie is always the right one" when your application uses complex cookie scoping. Design clear cookie names and scopes, and rely on proven security infrastructure for sessions and auth.

## 7. How Spring Resolves These Annotations

### 7.1 Spring MVC

In Spring MVC:

~~~mermaid
flowchart TD
    A["HTTP request / Tomcat"] --> B["Servlet Filter chain"]
    B --> C["DispatcherServlet"]
    C --> D["RequestMappingHandlerMapping"]
    D --> E["Selected HandlerMethod"]
    E --> F["RequestMappingHandlerAdapter"]
    F --> G["HandlerMethodArgumentResolver"]
    G --> H["ConversionService / Formatter / Validator"]
    H --> I["Controller method"]
    I --> J["Return-value handler / HttpMessageConverter"]
    J --> K["HTTP response"]
~~~

This flow represents the standard annotated controller model. Spring registers HandlerMethodArgumentResolver implementations for each data source: path variables, request parameters, request headers, cookies, etc. The resolver extracts the raw value; the conversion service or binder converts it to the Java parameter type. If required data is missing or conversion fails, the request can fail with an error **before the controller method is invoked**.

**HandlerMapping only selects the method; it does not turn the query "page=2" into an int.** Argument creation belongs to the HandlerAdapter/argument resolvers layer.

### 7.2 Spring WebFlux Annotated Controllers

Spring WebFlux uses DispatcherHandler instead of DispatcherServlet, ServerWebExchange instead of HttpServletRequest, and reactive HandlerAdapter/argument resolution. However, the four annotations @PathVariable, @RequestParam, @RequestHeader, and @CookieValue are also used in annotated controllers.

The core difference lies in the framework runtime and the underlying data sources, not in renaming these four annotations. WebFlux's @RequestParam focuses on query parameters; reactive body handling typically uses @RequestBody Mono<T> or a DTO depending on decoder support, rather than copying a Servlet-specific controller verbatim.

**Do not assume a server is running WebFlux solely because a method returns Mono.** A Spring MVC controller can also return certain reactive return types via Servlet async support.

## 8. Required, Optional, and defaultValue — Choosing Intentionally

The annotations support expressing different input contracts:

| Scenario | Example | Rule to document |
| --- | --- | --- |
| Required path variable | @PathVariable("id") long id | Route requires path segment and valid type |
| Required query | @RequestParam("q") String q | Missing q normally returns 400 |
| Query with default | @RequestParam(name="page", defaultValue="1") int page | Default when missing/empty per annotation semantics |
| Optional query | @RequestParam(name="sort", required=false) String sort | Controller must handle null |
| Optional header | @RequestHeader(name="X-Trace", required=false) String trace | Do not treat as authentication |
| Header with default | @RequestHeader(name="X-Client", defaultValue="web") String client | Meaningful default value |
| Cookie with default | @CookieValue(name="theme", defaultValue="light") String theme | Should be whitelisted |
| Required cookie | @CookieValue("session") String id | Session validation should normally be delegated to Spring Security |

**Do not use defaultValue to hide invalid-type input errors.** For a parameter like page, test page=0, page=-1, page=abc, page=, and omitted page. Acceptance criteria are part of the API contract, not determined solely by annotations.

### Is Optional<T> Appropriate?

Optional<String> helps express the presence or absence of an input. However, do not turn every method parameter into Optional when defaultValue is clearer or the business logic requires the value. In response DTOs, Optional is generally not a good JSON field type to overuse.

## 9. Type Conversion

Annotated method parameters do not have to be String:

~~~java
@GetMapping("/api/tasks/{id}")
public String task(
        @PathVariable("id") UUID id,
        @RequestParam(name = "limit", defaultValue = "20") int limit,
        @RequestHeader(name = "X-Debug", defaultValue = "false")
        boolean debug) {
    // ...
}
~~~

This snippet illustrates parameter types; it requires importing UUID and placing it inside an appropriate controller.

Common conversions:

- Path String "42" -> long 42.
- Query String "true" -> boolean true via conversion support.
- Valid UUID String -> java.util.UUID.
- Matching enum String -> enum value.
- Date String -> LocalDate with appropriate format/configuration.

For a date query parameter:

~~~java
@RequestParam("day")
@DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
LocalDate day
~~~

Requires importing org.springframework.format.annotation.DateTimeFormat and java.time.LocalDate.

**Do not confuse ConversionService with the JSON decoder.** @RequestBody JSON typically uses HttpMessageConverter (MVC) or HttpMessageReader (WebFlux) and Jackson. A Formatter/Converter for path/query/header/cookie values does not automatically rename JSON fields or apply the same serializer.

### Custom Value Objects

If the domain uses OrderId instead of long/String, you can register a Converter<String,OrderId> or Formatter<OrderId> via WebMvcConfigurer (MVC) or WebFluxConfigurer (WebFlux). Choose a custom converter to enforce domain type representation invariants, not to bypass validation or replace the security layer.

## 10. Input Validation and Common HTTP Errors

Some errors occur **before the method executes**:

| Request | Cause | Typical result |
| --- | --- | --- |
| GET /api/items/abc | @PathVariable long cannot be converted | 400 Bad Request |
| GET /api/search without q | @RequestParam("q") is required | 400 Bad Request |
| GET /api/items/42?page=abc | @RequestParam int conversion fails | 400 Bad Request |
| GET /api/items/42?page=0 | Conversion succeeds, but business rule rejects | 400 if application validates/throws appropriately |
| Missing required @RequestHeader | Required header is absent | 400 under default argument resolution |
| Missing required @CookieValue | Required cookie is absent | 400 under default argument resolution |
| GET /api/unknown | No matching mapping | 404 Not Found |
| POST to a GET-only route | Method not supported | 405 Method Not Allowed |

These are typical behaviors of Spring MVC/WebFlux under default error configuration. Exception classes and error bodies differ across the two stacks, versions, and custom @ControllerAdvice/WebExceptionHandler setups. Do not guarantee that every failure returns the exact same JSON body unless you have designed a unified error response contract.

### Validating Scalar Values

You can use Jakarta Validation annotations such as @Min(1), @NotBlank, and @Pattern with proper method validation setup. Spring Boot 3.x normally requires the spring-boot-starter-validation dependency for a Jakarta Validation provider. Spring Framework 6.1 includes built-in method validation for controller types; the thrown exception can be HandlerMethodValidationException or another type depending on the stack and configuration.

In the standalone runnable example in this lesson, we check page >= 1 with an explicit guard so it does not depend on extra validation configuration. In real applications, apply constraints cleanly on API DTOs/methods and standardize error responses.

### Validating Relationships Across Sources

A single request might supply shopId in the path, tenantId in a header, and a session cookie. The fact that all three parse successfully **does not prove they belong to the same tenant/user**. After authentication, the service/security layer must verify authorization across the principal, tenant, and resource.

## 11. Encoding and Normalizing Request Data

### 11.1 Query Parameters

Query strings use percent-encoding for reserved or unsafe characters. With cURL, you can use --get --data-urlencode to send values instead of concatenating strings manually:

~~~bash
curl --get --data-urlencode 'q=Spring Boot & WebFlux' \
  'http://localhost:8080/api/search'
~~~

This command illustrates query encoding; it is not a required endpoint in the runnable example below.

Many clients treat "+" using form-style conventions as a space in queries; behavior can be affected by parsers and proxies. When values matter, prefer an HTTP client library with a proper URI builder instead of manual string concatenation.

### 11.2 Path Variables

Do not manually encode an entire URL with an ad-hoc replace(). Use an HTTP client's URI builder to encode path segments when needed. For IDs containing "/" or special characters, design URL-safe endpoints; do not assume encoded slashes are permitted uniformly by every reverse proxy or servlet container.

### 11.3 Headers

Header names are case-insensitive; header values have format-specific syntax. Do not copy unvalidated input into response headers. While Spring guards against certain invalid characters, you must still validate request IDs, enforce length limits, and prevent log injection.

### 11.4 Cookies

Cookie names/values have their own syntax and scoping rules. Do not construct cookies by concatenating unencoded strings; use ResponseCookie or your stack's cookie API. Avoid placing complex JSON directly inside cookies when server-side sessions or a properly signed/authenticated format can be used.

## 12. Runnable Spring Boot MVC Example: Reading All Four Sources

Let us build a REST endpoint GET /api/items/{itemId} that returns JSON containing data bound from all four sources. The project uses **Java 17, Spring Boot 3.3.13, Gradle**, with no database required.

Requirements:

- Path {itemId} is converted to long.
- Query page defaults to 1 and must be >= 1.
- Query tag can repeat; if absent, treated as an empty list.
- Header X-Request-Id is optional.
- Cookie theme defaults to light; only light or dark is allowed.
- Response is JSON serialized from a Java record.
- Tests verify binding, default values, header/cookie handling, and conversion errors.

### 12.1 Project Structure

~~~text
request-input-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/requestdata/
    │   ├── RequestDataApplication.java
    │   └── ItemController.java
    └── test/java/com/example/requestdata/
        └── ItemControllerTest.java
~~~

### 12.2 settings.gradle

~~~groovy
rootProject.name = 'request-input-demo'
~~~

### 12.3 build.gradle

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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

spring-boot-starter-web typically brings in Spring MVC, Jackson, and embedded Tomcat. spring-boot-starter-test provides JUnit 5, Spring Test, and MockMvc. If the project includes the Gradle wrapper, you can use ./gradlew on Linux/macOS or gradlew.bat on Windows.

### 12.4 RequestDataApplication.java

~~~java
package com.example.requestdata;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RequestDataApplication {

    public static void main(String[] args) {
        SpringApplication.run(RequestDataApplication.class, args);
    }
}
~~~

### 12.5 ItemController.java

~~~java
package com.example.requestdata;

import java.util.List;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.CookieValue;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/items")
public class ItemController {

    @GetMapping("/{itemId}")
    public ItemView read(
            @PathVariable("itemId") long itemId,
            @RequestParam(name = "page", defaultValue = "1") int page,
            @RequestParam(name = "tag", required = false)
                    List<String> tags,
            @RequestHeader(
                    name = "X-Request-Id", required = false)
                    String requestId,
            @CookieValue(name = "theme", defaultValue = "light")
                    String theme) {

        if (page < 1) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "page must be >= 1");
        }

        if (!theme.equals("light") && !theme.equals("dark")) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "unsupported theme");
        }

        List<String> safeTags =
                tags == null ? List.of() : List.copyOf(tags);

        return new ItemView(
                itemId, page, safeTags, requestId, theme);
    }
}

record ItemView(
        long itemId,
        int page,
        List<String> tags,
        String requestId,
        String theme) {
}
~~~

This is a valid Java file containing one public class ItemController and a package-private record ItemView in the same package. Spring Boot component scan picks up the controller. Jackson in Boot 3.3 supports Java records and serializes their components into JSON.

Each annotation has a clear responsibility:

| Java parameter | HTTP source | If missing | If invalid |
| --- | --- | --- | --- |
| itemId: long | Path /api/items/{itemId} | Route may not match | Conversion typically returns 400 |
| page: int | Query page | 1 | Unparseable or <= 0 is rejected |
| tags: List<String> | Repeated query tag | [] after normalization | List/encoding rules should be tested per client |
| requestId: String | Header X-Request-Id | null | Example does not yet whitelist request IDs |
| theme: String | Cookie theme | "light" | Values other than light/dark return 400 |

**Security scope of this example:** theme is only a UI preference, not a session cookie. X-Request-Id illustrates binding; production systems should limit its length/format before logging it. The project has no authentication, so it must not be used as a real multi-tenant system.

### 12.6 Running and Calling the Endpoint

In the project directory:

~~~bash
gradle clean test bootRun
~~~

In another terminal:

~~~bash
curl -i --get \
  --data-urlencode 'page=2' \
  --data-urlencode 'tag=spring' \
  --data-urlencode 'tag=java' \
  -H 'X-Request-Id: req-42' \
  -b 'theme=dark' \
  'http://127.0.0.1:8080/api/items/42'
~~~

Expected HTTP 200, JSON body equivalent to:

~~~json
{
  "itemId": 42,
  "page": 2,
  "tags": ["spring", "java"],
  "requestId": "req-42",
  "theme": "dark"
}
~~~

JSON field order and infrastructure headers like Date/Connection depend on the encoder/server; assert by field rather than comparing raw bytes.

### 12.7 Missing Query/Header/Cookie

~~~bash
curl -i 'http://127.0.0.1:8080/api/items/42'
~~~

Expected HTTP 200 and logical fields:

~~~json
{
  "itemId": 42,
  "page": 1,
  "tags": [],
  "requestId": null,
  "theme": "light"
}
~~~

This is the expected body based on the code and default Jackson configuration, not output executed inside this document. If the application configures a different null inclusion policy, the requestId field may be omitted instead of appearing as null.

### 12.8 Wrong Path or Query Type

~~~bash
curl -i 'http://127.0.0.1:8080/api/items/abc'
curl -i 'http://127.0.0.1:8080/api/items/42?page=abc'
curl -i 'http://127.0.0.1:8080/api/items/42?page=0'
~~~

In the example application, these cases typically return 400: the first two at the conversion layer, and page=0 via the business guard. The default error body can vary depending on Spring Boot properties.

### 12.9 Cookie Outside the Whitelist

~~~bash
curl -i -b 'theme=script' \
  'http://127.0.0.1:8080/api/items/42'
~~~

Expected HTTP 400 with reason unsupported theme. This shows that even seemingly "harmless" cookies need acceptance rules if used in output or logic.

## 13. MockMvc Testing: Verifying Binding and Pre-Controller Errors

Create ItemControllerTest.java:

~~~java
package com.example.requestdata;

import jakarta.servlet.http.Cookie;

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
    private MockMvc mockMvc;

    @Test
    void readsAllFourSources() throws Exception {
        mockMvc.perform(get("/api/items/{itemId}", 42)
                .param("page", "2")
                .param("tag", "spring", "java")
                .header("X-Request-Id", "req-42")
                .cookie(new Cookie("theme", "dark")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.itemId").value(42))
            .andExpect(jsonPath("$.page").value(2))
            .andExpect(jsonPath("$.tags[0]").value("spring"))
            .andExpect(jsonPath("$.tags[1]").value("java"))
            .andExpect(jsonPath("$.requestId").value("req-42"))
            .andExpect(jsonPath("$.theme").value("dark"));
    }

    @Test
    void usesDefaultsForMissingOptionalValues() throws Exception {
        mockMvc.perform(get("/api/items/{itemId}", 42))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.page").value(1))
            .andExpect(jsonPath("$.tags").isEmpty())
            .andExpect(jsonPath("$.theme").value("light"));
    }

    @Test
    void rejectsNonNumericPathVariable() throws Exception {
        mockMvc.perform(get("/api/items/abc"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void rejectsNonNumericQueryParameter() throws Exception {
        mockMvc.perform(get("/api/items/42").param("page", "abc"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void rejectsNonPositivePage() throws Exception {
        mockMvc.perform(get("/api/items/42").param("page", "0"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void rejectsInvalidCookieValue() throws Exception {
        mockMvc.perform(get("/api/items/42")
                .cookie(new Cookie("theme", "untrusted")))
            .andExpect(status().isBadRequest());
    }
}
~~~

Run:

~~~bash
gradle test
~~~

**MockMvc** uses mock Servlet requests/responses to execute the Spring MVC request pipeline, including argument resolvers, conversion, and the controller, without opening a real HTTP socket on port 8080 in this test. Thus tests can run in CI without local port dependencies. If you want real TCP integration testing, use @SpringBootTest(webEnvironment = RANDOM_PORT) and a corresponding HTTP client.

JSON assertions use JSONPath so they do not depend on JSON key order. When debugging a failing test, determine whether it failed at mapping, conversion, controller validation, or serialization instead of immediately concluding Spring "cannot read query parameters".

## 14. Reading All Values via the Servlet API When Truly Needed

In Spring MVC, you can inject HttpServletRequest into a controller to access raw Servlet information:

~~~java
@GetMapping("/inspect")
public String inspect(HttpServletRequest request) {
    String rawQuery = request.getQueryString();
    String page = request.getParameter("page");
    String header = request.getHeader("X-Request-Id");
    Cookie[] cookies = request.getCookies();
    // ...
}
~~~

This is an illustrative method; it requires importing jakarta.servlet.http.HttpServletRequest and jakarta.servlet.http.Cookie and placing it inside a controller class. **getQueryString does not always return decoded data**, whereas getParameter uses container parsing. The Servlet API lets you read raw data, but couples the controller directly to the Servlet stack.

Prefer @PathVariable/@RequestParam/@RequestHeader/@CookieValue when you only need a few named values. Use HttpServletRequest when framework abstractions are insufficient, such as infrastructure request metadata, controlled debugging, or custom middleware.

### Do Not Use HttpServletRequest in a WebFlux Reactive Server

A Spring WebFlux controller normally uses ServerWebExchange, ServerHttpRequest, or annotation binding. Pulling Servlet-specific APIs into a reactive controller is not a valid porting approach.

## 15. Spring WebFlux: The Four Annotations Still Apply

In an application with **only spring-boot-starter-webflux**, an annotated controller can be written similarly:

~~~java
@RestController
class ReactiveItemController {

    @GetMapping("/reactive/items/{itemId}")
    Mono<String> read(
            @PathVariable("itemId") long itemId,
            @RequestParam(name = "page", defaultValue = "1")
                    int page,
            @RequestHeader(name = "X-Request-Id", defaultValue = "none")
                    String requestId,
            @CookieValue(name = "theme", defaultValue = "light")
                    String theme) {

        return Mono.just(itemId + ":" + page + ":"
                + requestId + ":" + theme);
    }
}
~~~

This is an **illustrative class**; it requires importing org.springframework.web.bind.annotation.* and reactor.core.publisher.Mono, and does not belong inside the MVC project from Section 12. Spring WebFlux's RequestMappingHandlerAdapter resolves annotated arguments for the reactive stack.

Example HTTP GET:

~~~text
/reactive/items/42?page=3
X-Request-Id: req-x
Cookie: theme=dark
~~~

Expected body:

~~~text
42:3:req-x:dark
~~~

However, if you add starter-webflux to the MVC project in Section 12 and declare a new controller there, Spring Boot **still defaults to Spring MVC** when both starters are present. To test a pure reactive stack, create a separate project or set spring.main.web-application-type=reactive intentionally.

### What Stays the Same

- Never trust header/cookie values as authenticated.
- Validate path/query values following the same principles as MVC.
- Encoding/decoding and HTTP semantics still must be right.
- Do not block the Netty event loop to fetch other data when the controller already uses a reactive pipeline.

### What Differs

- WebFlux handles HTTP via ServerWebExchange/DispatcherHandler instead of HttpServletRequest/DispatcherServlet.
- Reactive request bodies typically use HttpMessageReader/codecs.
- WebFlux's @RequestParam is based on query parameters; form bodies use a separate API.
- In Java WebFlux functional endpoints, the same controller annotations are not used; read from ServerRequest instead.

## 16. WebFlux Functional Endpoints: Path, Query, Header, Cookie

With functional routing, the handler receives org.springframework.web.reactive.function.server.ServerRequest. Methods to use:

~~~java
request.pathVariable("itemId");
request.queryParam("page");
request.headers().firstHeader("X-Request-Id");
request.cookies().getFirst("theme");
~~~

Common types:

| Source | API | Type |
| --- | --- | --- |
| Path variable | ServerRequest.pathVariable(name) | String |
| Query parameter | ServerRequest.queryParam(name) | Optional<String> |
| Repeated query | ServerRequest.queryParams().get(name) | List<String> or null |
| Header | ServerRequest.headers().firstHeader(name) | String or null |
| Cookie | ServerRequest.cookies().getFirst(name) | HttpCookie or null |

Example class that can be placed in a Spring Boot WebFlux project with starter-webflux:

~~~java
package com.example.functional;

import java.util.Map;
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpCookie;
import org.springframework.web.reactive.function.server.RequestPredicates;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@Configuration
public class RequestRoutes {

    @Bean
    public RouterFunction<ServerResponse> routes() {
        return RouterFunctions.route(
                RequestPredicates.GET("/functional/items/{itemId}"),
                request -> {
                    String itemId = request.pathVariable("itemId");
                    String page =
                            request.queryParam("page").orElse("1");

                    String header =
                            request.headers().firstHeader("X-Request-Id");
                    String requestId =
                            header == null ? "none" : header;

                    HttpCookie cookie =
                            request.cookies().getFirst("theme");
                    String theme =
                            cookie == null ? "light" : cookie.getValue();

                    return ServerResponse.ok().bodyValue(Map.of(
                            "itemId", itemId,
                            "page", page,
                            "requestId", requestId,
                            "theme", theme));
                });
    }
}
~~~

This is a **complete Java class** for a WebFlux application whose component scan covers com.example.functional, though it does not provide a main method or Gradle files on its own. The import java.util.Optional in the snippet is unused and can be removed without affecting behavior; the Java compiler accepts unused imports if the class exists. The JSON output from the functional route contains itemId and page as Strings, unlike the MVC example that converts them to long/int. **Functional handlers do not perform automatic @PathVariable/@RequestParam argument conversion**, so you must parse and validate them yourself if you want typed data.

To avoid giving the impression that security features are built in: this functional route does not yet verify that page is positive, whitelist theme, or validate requestId. In a real application, add proper validation and error handling.

## 17. Cookies in Applications Using Spring Security

For sessions or login, never write a controller that reads @CookieValue("JSESSIONID") and treats that as proof a user is logged in. Spring Security or the corresponding session framework handles authentication, session fixation protection, CSRF protection, and lifecycle management.

Notes:

- **HttpOnly** prevents browser-side JavaScript from reading the cookie via document.cookie, but does not prevent the browser from automatically sending the cookie on requests.
- **Secure** restricts browsers to sending cookies over secure connections according to browser rules; use HTTPS.
- **SameSite** affects cross-site cookie transmission, but does not replace full CSRF protection.
- **Cookie signing/encryption** or server-side session lookup must be designed properly if a cookie holds values affecting authorization.
- CORS and cookie credentials are separate mechanisms; configuring Access-Control-Allow-Credentials does not automatically make any cookie safe.
- Authorization headers and session cookies should never be placed directly into error bodies or logs.

Distinguishing **reading a cookie** from **trusting a cookie** is a fundamental security principle.

## 18. Headers from Reverse Proxies and Client Identification

Applications sitting behind Nginx, an ingress, an API gateway, or a load balancer may receive headers such as Forwarded, X-Forwarded-For, X-Forwarded-Proto, and X-Forwarded-Host.

Do not write:

~~~java
String clientIp = request.getHeader("X-Forwarded-For");
// Then assume clientIp is definitely the user's real IP.
~~~

The pattern above is an **insecure example**. Clients can spoof headers if proxies do not strip and overwrite them. With Spring Boot, use server.forward-headers-strategy appropriate to your topology and trust headers only from trusted reverse proxies; configure the proxy to drop forged external headers.

If the application needs IP addresses for rate limiting, auditing, or fraud controls, clearly define the trusted proxy chain and logging policy. A matching header name does not mean a trustworthy value.

## 19. Designing the API Contract for Each Source

### Path Variable: Identifying a Resource

Path variables are suited for resource identity, such as /orders/{orderId}. Resources may require validation/authorization; a valid ID does not mean the user is allowed to view the resource.

### Query Parameter: Query Options

Queries should carry filters, sorting, page, limit, cursor, field selection, or search criteria. Enforce limits on page size, repeated tag count, and search string length so a client cannot send thousands of parameters and waste CPU/memory.

### Header: Request Metadata

Headers suit correlation IDs, content negotiation, conditional requests, and protocol metadata. Avoid putting critical business contract data in an undocumented custom header, as proxies/clients make this hard to debug. For authentication, use standard mechanisms.

### Cookie: Scoped Client-Resent State

Cookies fit sessions or certain client preferences with defined scope and policy. Never stuff large amounts of data into cookies: browsers and servers enforce header size limits, and cookies are resent on many requests, increasing bandwidth.

### Body: Large or Structured Business Data

POST/PUT/PATCH JSON payloads normally use @RequestBody DTOs with validation. Do not try to pass a multi-kilobyte JSON document as a query parameter or Cookie just to "avoid using a body".

## 20. Common Debugging Pitfalls

| Symptom | Causes to check |
| --- | --- |
| @PathVariable id is always null or fails to match | Mismatch between {id} and annotation name, or wrong path template |
| /items/abc returns 400 even though the route exists | Type conversion to long failed |
| ?page=0 still enters the method | Conversion succeeded; business validation is missing |
| @RequestParam does not see JSON fields | JSON body is not query parameters |
| Repeated query tag only captures one value | Single-valued String/Map used instead of List/MultiValueMap |
| required=false String returns null | Matches contract; needs guard/default |
| defaultValue did not save page=abc | Invalid-type value differs from missing value |
| Header is absent on the server even though client sent it | Proxy/gateway may not forward or may rename headers |
| X-Forwarded-For contains unexpected IPs | May be spoofed or traversed multiple proxies |
| CookieValue does not see theme | Cookie not sent due to domain/path/SameSite/Secure/browser policy |
| Session cookie is visible but user is not authenticated | Not verified by authentication/session infrastructure |
| Requiring @CookieValue("theme") makes API browser-dependent | Non-browser clients may omit cookies; need default/contract |
| Added starter-webflux but controller still runs Servlet MVC | Boot defaults to MVC when both starters are on the classpath |
| WebFlux functional request ignores @RequestParam | Functional handlers use ServerRequest API, not annotated argument binding |
| Response JSON omits requestId | Jackson null inclusion policy may omit null fields |
| HTTP 404 on expected path | Wrong HandlerMapping/route or context path, not necessarily argument binding |

You do not need to enable full HTTP TRACE logging to investigate every simple error. Start by checking whether the route matched, the actual request values, argument conversion/validation, and the returned status.

## 21. Systematic Debugging Workflow

1. Send a request with explicit path/query/header/cookie values using cURL/Postman/an HTTP client.
2. Verify the target URI, proper encoding, and that proxy rewrites did not alter the path.
3. Check whether handler mapping matches the endpoint.
4. Check the annotation name and Java parameter type.
5. Distinguish a missing value from an empty value, type mismatch, or repeated query key.
6. Check the root exception if the controller was never invoked: required parameter, type mismatch, or validation?
7. Once the controller runs, verify validation and authorization before calling the service.
8. Identify which JSON response formatter/serializer is actually used.
9. If a cookie is missing, check Set-Cookie, domain/path, browser credentials, SameSite, and HTTPS.
10. If a header comes from a proxy, verify the proxy trust boundary and forward-header configuration.
11. Write tests covering at least one happy path, one default/optional path, and several invalid inputs.
12. Document the API contract in OpenAPI or endpoint docs so clients know where each value must be sent.

Suggested Spring MVC loggers in local/test environments:

~~~properties
logging.level.org.springframework.web.servlet.DispatcherServlet=DEBUG
logging.level.org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping=TRACE
~~~

For WebFlux:

~~~properties
logging.level.org.springframework.web.reactive.DispatcherHandler=DEBUG
logging.level.org.springframework.web.reactive.result.method.annotation=TRACE
~~~

Never log tokens, Authorization headers, full Cookies, or personal data in production. Enable TRACE in a controlled manner and turn it off once diagnosed.

## 22. Frequently Asked Questions

**1. Can @PathVariable and @RequestParam be used in the same method?**

Yes. They read from two different sources, e.g., /items/{id}?page=2. Just make sure the route/annotation names match and type conversion succeeds.

**2. Are header names case-sensitive?**

Per HTTP semantics, header field names are case-insensitive. However, do not compare a raw header dump using case-sensitive String.equals to conclude the server did not receive a header.

**3. Do cookies only exist when the client is a browser?**

No. Any HTTP client can send a Cookie header manually. Browsers merely manage storage/transmission policies; the server must still treat received cookie data as client-controlled.

**4. What happens if @CookieValue(required=false) and the cookie is absent?**

With String, the framework can pass null; with defaultValue, it receives the default value. Choose an explicit contract and test it.

**5. What if a query parameter has two values?**

Use List<String> or MultiValueMap if the API allows repetition. Do not silently take one value and ignore the rest without documenting it.

**6. How do I receive a LocalDate from a query parameter?**

Use @DateTimeFormat with LocalDate and an ISO/appropriate format. Date fields inside a JSON body are handled separately by the codec/Jackson.

**7. Does a path variable used as an ID need validation?**

Yes. Converting to long or UUID only validates syntax, not that the ID exists or that the user is authorized to access it.

**8. Does @RequestHeader("Authorization") replace Spring Security?**

No. It only reads the header string. Validating tokens, signatures, expiry, scopes, and authorization is the responsibility of the security stack/architecture.

**9. Does @RequestParam read fields from a JSON POST body?**

That is not the standard mechanism for JSON bodies. Use a @RequestBody DTO. Query parameters can accompany a POST request, but do not mix sources ambiguously.

**10. Should an invalid client-supplied X-Request-Id be trusted?**

No. Validate its length/characters, normalize it, or generate a new ID per tracing policy. Never use the raw value as a file name, log format string, or database key without sanitization.

**11. Should cookies be read from the raw request header or via @CookieValue?**

For a specific named cookie in an annotated controller, @CookieValue is simpler. Only read the raw Cookie header when you genuinely need protocol-level handling at the infrastructure layer and understand duplicate/scoping edge cases.

**12. Should I write a custom argument resolver for every value?**

No. Standard annotations cover most use cases. A custom resolver is suitable when constructing a reusable domain object from multiple request sources, after considering trust boundaries.

## 23. Final Checklist

- [ ] Path template declares the exact variables and annotation names.
- [ ] Query parameters specify required/defaultValue/Optional matching the API contract.
- [ ] Multi-valued query parameters are handled with List/MultiValueMap when needed.
- [ ] Java types and converters/formatters match the input data.
- [ ] Header names are correct and only needed headers are read.
- [ ] Client-supplied header/cookie values are treated as untrusted.
- [ ] Cookies use proper names/scopes with explicit defaults or required flags.
- [ ] Inputs are validated for format, length, and access permissions.
- [ ] Unverified request metadata is never used for authorization.
- [ ] Avoid logging Authorization/Cookie/session tokens.
- [ ] HTTP statuses 400/404/405 are distinguished by root cause.
- [ ] Tests cover success, missing values, wrong types, and invalid data.
- [ ] When using WebFlux, Servlet-specific APIs are not mixed in.
- [ ] Encoded inputs are verified with a real HTTP client.

## 24. Summary

In Spring Boot, **@PathVariable** extracts data from a matched path, **@RequestParam** reads query parameters (and stack-appropriate request parameters), **@RequestHeader** reads HTTP metadata, and **@CookieValue** extracts a named request cookie. Spring MVC and annotated WebFlux use argument resolvers and type conversion to supply these values as method parameters. These are **binding** mechanisms—not proof that input is valid, safe, or that the user is authenticated.

Good API design starts by choosing the right source, defining required/default behavior explicitly, selecting appropriate types, testing missing/invalid/multi-value cases, encoding URIs properly, and enforcing trust boundaries on headers and cookies. For standard needs, built-in annotations are clearer and easier to maintain than custom request parsing.

## 25. References

- Spring Framework — MVC @PathVariable: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/uri-templates.html
- Spring Framework — MVC @RequestParam: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestparam.html
- Spring Framework — MVC @RequestHeader: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestheader.html
- Spring Framework — MVC @CookieValue: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/cookievalue.html
- Spring Framework — WebFlux annotated controller method arguments: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/arguments.html
- Spring Framework — WebFlux functional endpoints: https://docs.spring.io/spring-framework/reference/web/webflux-functional.html
- Spring Boot 3.3 — Servlet Web Applications: https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html
- Spring Boot 3.3 — Reactive Web Applications: https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html
- MDN Web Docs — HTTP cookies: https://developer.mozilla.org/en-US/docs/Web/HTTP/Cookies
