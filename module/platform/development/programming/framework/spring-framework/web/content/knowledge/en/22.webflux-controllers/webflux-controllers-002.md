# Reading Parameters, Headers, Cookies, Principal, and Data in ServerWebExchange

## 1. Objectives and Scope

An HTTP request sent to Spring WebFlux carries multiple data sources: **query parameters** in the URI, **path variables**, **headers**, **cookies**, the **request body** (JSON, form, or multipart), an authenticated **principal**, and server-created **exchange attributes**. They are not synonymous, and they have different lifecycles and trust levels. Controllers should use WebFlux argument resolvers when only a single value is needed; when you need the broader picture, use `ServerWebExchange` while preserving the asynchronous model.

This lesson belongs to the **WebFlux Controllers** section of Spring Framework, using **Java 17+, Spring Framework 6.x, Spring Boot 3.x** (reactive stack, typically Reactor Netty). By the end of this lesson, you will be able to:

- Use `@RequestParam` with `required`/`defaultValue`/`Optional`, type conversion, and multi-value queries.
- Distinguish *missing parameter*, *empty parameter*, *unconvertible value*, and *repeated parameter*.
- Read `@RequestHeader`, `HttpHeaders`, and `@CookieValue`; avoid trusting client-sent `X-User` or tokens as identity.
- Retrieve `java.security.Principal` or `Mono<Principal>`, handle anonymous requests explicitly, and understand the relationship with Spring Security.
- Use `ServerWebExchange.getRequest()`, `getResponse()`, `getAttributes()`, `getPrincipal()`, `getSession()`, `getFormData()`, `getMultipartData()`, `getLocaleContext()`, and their associated limitations.
- Distinguish form-urlencoded, multipart, JSON, and query strings in WebFlux without treating everything as `@RequestParam`.
- Practice with a Spring Boot WebFlux application featuring a `WebFilter` that generates a correlation ID, a controller, HTTP examples, and `WebTestClient`.
- Avoid reading the body twice, blocking the Netty event loop with `block()`, logging secrets, or skipping validation/authorization.

**Key takeaway:** In **Spring WebFlux**, `@RequestParam` binds **query parameters only**. By contrast, the Servlet/Spring MVC concept of “request parameter” can also include form-data and some multipart values. In WebFlux, form and multipart data have dedicated APIs via `ServerWebExchange` or appropriate data binding. This difference is explicitly documented in the Spring Framework reference.

## 2. Map of Data in a Request

Example:

```http
POST /api/input/notes/42?tag=java&tag=webflux&page=2 HTTP/1.1
Host: localhost:8080
Content-Type: application/json
Accept: application/json
X-Client: mobile-app
Cookie: theme=dark; session=opaque

{"message":"Hello"}
```

Breakdown:

| Location | Example | How to read in WebFlux |
| --- | --- | --- |
| Path variable | `42` | `@PathVariable("id")` |
| Query param | `tag=java&tag=webflux` | `@RequestParam` or `exchange.getRequest().getQueryParams()` |
| Header | `X-Client: mobile-app` | `@RequestHeader` or `getRequest().getHeaders()` |
| Cookie | `theme=dark` | `@CookieValue` or `getRequest().getCookies()` |
| JSON body | `{"message":"Hello"}` | `@RequestBody Mono<NoteInput>` |
| Principal | Not self-declared client info | `Principal`, `Mono<Principal>`, or `exchange.getPrincipal()` |
| Exchange attribute | `app.traceId` written by filter | `@RequestAttribute` or `exchange.getAttribute(...)` |
| Web session | Server-managed session state | `exchange.getSession()` or `WebSession` |
| URL-encoded form body | `name=An&topic=java` | `exchange.getFormData()` |
| Multipart | Field/file parts | `exchange.getMultipartData()`, `@RequestPart` |

*Request headers/cookies/query/body are generally client-supplied data and must be validated.* Even after URL decoding or automatic conversion to a Java type, they are not automatically “sanitized” or authenticated. Principal is likewise trustworthy only when the authentication/security chain is actually configured properly.

## 3. Should You Use Annotations or ServerWebExchange?

Usually choose the smallest option:

```java
@GetMapping("/books")
public Mono<Book> one(
        @RequestParam("id") long id,
        @RequestHeader("Accept-Language") String language) {
    return repository.find(id, language);
}
```

This is a **snippet** requiring a `repository` bean and `Book` record; it is not a complete Java file. The controller receives the exact two values directly instead of manually parsing the raw request.

Use `ServerWebExchange` when you need multiple components together or infrastructure capabilities—such as reading repeated query values, retrieving request attributes from a `WebFilter`, accessing form/multipart maps, session, headers, or principal.

```java
@GetMapping("/inspect")
public Mono<String> inspect(ServerWebExchange exchange) {
    String method = exchange.getRequest().getMethod().name();
    String client = exchange.getRequest()
            .getHeaders().getFirst("X-Client");
    return Mono.just(method + ":" + client);
}
```

This is also a snippet requiring imports. **Do not use ServerWebExchange just to avoid learning annotation binding.** When taking the entire raw request, you must decide which fields may be read/echoed/logged, how to convert them, how to validate them, and how to handle missing values. With argument binding, Spring handles many of these steps cleanly and consistently.

## 4. @RequestParam: Query Parameters in WebFlux

WebFlux binds parameters from the query string:

```text
GET /api/search?q=spring&page=3
GET /api/search?q=a%26b
GET /api/search?tag=java&tag=webflux
```

Example:

```java
@GetMapping("/search")
public Mono<SearchView> search(
        @RequestParam("q") String q,
        @RequestParam(name = "page", defaultValue = "1") int page) {
    return Mono.just(new SearchView(q, page));
}
```

Given `record SearchView(String q,int page) {}`, the URL `?q=spring&page=3` produces the corresponding values. Query strings are URI data, independent of whether the request is GET or POST: a POST request can also carry query params.

### Required and defaultValue

- `@RequestParam("q") String q`: **required=true** by default; omitting `q` causes a request binding error (usually status 400).
- `@RequestParam(name="q",required=false) String q`: if omitted, the value is typically null; logic must check for it.
- `@RequestParam(name="q",defaultValue="all") String q`: uses the default when missing or empty per the annotation contract; `defaultValue` implicitly sets `required=false`.
- `@RequestParam Optional<String> q`: Spring supports `Optional`, distinguishing presence/absence via the resolver; do not use `Optional<Optional<T>>`.
- For `int page` with no default when missing, use explicit required behavior or `Integer`/`Optional<Integer>` to express optionality.

### Missing vs Empty

```text
/search               -> q is not present
/search?q=            -> q is present with an empty string value
/search?q=hello       -> q="hello"
/search?q=%20         -> q=" " after percent-decoding
```

If business logic forbids empty values, **add explicit validation** such as checking `isBlank()`/Bean Validation; do not assume `required=true` always blocks `q=`. With `defaultValue`, an empty value may be replaced by the default, so do not use it to prove the client sent a real value.

### Type Conversion

`@RequestParam int page` converts String → int via the conversion service; `?page=abc` typically produces HTTP 400 (type mismatch), not 500 when default error handling is intact. `?page=-1` is still a valid int for conversion, yet may be **invalid for business logic**. Enforce `page>=1`/`page<=max` rules separately.

For enums, UUIDs, LocalDates, and decimals, ConversionService can apply the appropriate converter; ensure formats and error messages are consistent rather than accepting strings and hastily parsing them inside the controller.

## 5. Multi-Value Queries and MultiValueMap

A query string can repeat the same key:

```http
GET /api/search?tag=java&tag=webflux&tag=reactor
```

`exchange.getRequest().getQueryParams()` returns a `MultiValueMap<String,String>`, preserving **multiple values for the same key**:

```java
MultiValueMap<String, String> query =
        exchange.getRequest().getQueryParams();

List<String> tags = query.getOrDefault("tag", List.of());
String first = query.getFirst("tag");
```

This is a snippet inside a method with `ServerWebExchange exchange` and imports `java.util.List`, `org.springframework.util.MultiValueMap`. For the example request, `tags` contains `["java","webflux","reactor"]` and `first` is `"java"`.

With `@RequestParam MultiValueMap<String,String> params`, Spring can also bind all query params. If you only use `Map<String,String>`, you can lose repeated values; if an API specifies a single value, **define a policy for duplicates**, especially when a gateway and backend may interpret queries differently.

### Do Not Split Raw Queries Manually on & or =

A value like `q="a&b=c"` in a URI must be properly component-encoded:

```text
?q=a%26b%3Dc  -> one q: "a&b=c"
?q=a&b=c      -> two parameters q="a", b="c"
```

Use a URI builder on the client and Spring argument binding on the server. Do not decode percent sequences a second time in the controller (for example, `%252F` should remain literal `%2F` after one decode). Query parsing and auth policies must interpret delimiters identically across reverse proxies and gateways.

## 6. @RequestHeader: Reading HTTP Metadata

Header names are case-insensitive under HTTP semantics. Common forms:

```java
@GetMapping("/headers")
public Mono<String> headers(
        @RequestHeader("X-Client") String client,
        @RequestHeader(name = "Accept-Language",
                       required = false) String language) {
    return Mono.just(client + ":" + language);
}
```

This snippet requires `X-Client` unless `required=false` or `defaultValue` is set. If the header is missing and required=true, Spring typically returns 400. `Accept-Language` can contain multiple values/ranges; do not manually split a string to select a locale when the framework already provides `LocaleContextResolver`.

### Single Header, Multiple Values, and Typed Headers

```java
@RequestHeader(name = "X-Retry", defaultValue = "0") int retry;
@RequestHeader(name = "X-Flag", required = false)
        Optional<String> flag;
```

The declarations above are **method parameter snippets**, not standalone Java statements. Spring can convert String → target type; `X-Retry: not-number` causes a conversion error. Some headers allow multiple values; use `List<String>`/`String[]` or `@RequestHeader MultiValueMap<String,String>`/`HttpHeaders` to read all of them.

```java
@GetMapping("/selected-header")
public Mono<String> chosen(@RequestHeader HttpHeaders headers) {
    return Mono.just(headers.getFirst("X-Client") == null
            ? "unknown" : headers.getFirst("X-Client"));
}
```

This is a snippet inside a controller requiring `org.springframework.http.HttpHeaders`. **Do not dump all HttpHeaders into responses or logs**: Authorization, Cookie, and tokens can be exposed.

### Headers Are Not Proof of Identity

Client-sent `X-User: admin` or `X-Role: root` **does not authenticate** a user. If an upstream proxy authenticates and forwards identity via headers, you need a trust boundary: the gateway verifies authentication, strips client-supplied headers, internal connections are protected, and downstream validates metadata. Typically, **Spring Security reactive** should establish a trusted Authentication/Principal in the security chain.

`Host`, `Forwarded`, and `X-Forwarded-*` can also be spoofed if proxy trust is misconfigured; never build absolute links or make tenant/redirect decisions from unverified headers.

## 7. @CookieValue: Reading Individual Cookies

Cookies travel in the `Cookie` request header but have their own resolver:

```java
@GetMapping("/theme")
public Mono<String> theme(
        @CookieValue(name = "theme",
                     defaultValue = "light") String theme) {
    return Mono.just(theme);
}
```

- `@CookieValue("theme")` is required by default; omitting it can cause HTTP 400.
- `required=false`, `Optional<String>`, or `defaultValue` is appropriate when a cookie is optional.
- `@CookieValue` converts the value via converters when the target type is not String.
- `exchange.getRequest().getCookies()` returns `MultiValueMap<String,HttpCookie>` when you need to inspect multiple cookies/metadata.
- Cookies with the same name may come from different paths/domains; do not pick one carelessly when making a security decision.

Example:

```java
MultiValueMap<String, HttpCookie> cookies =
        exchange.getRequest().getCookies();
HttpCookie first = cookies.getFirst("theme");
String value = first == null ? "light" : first.getValue();
```

This is a snippet inside a method with `ServerWebExchange` and imports `org.springframework.http.HttpCookie`.

### HttpOnly, Secure, and SameSite Do Not Create Authentication Automatically

- `HttpOnly` prevents browser JavaScript from normally reading the cookie, while **the server still receives the cookie** on matching HTTP requests.
- `Secure` restricts the browser to sending the cookie over secure connections; it does not verify business content integrity.
- `SameSite` helps mitigate certain cross-site cookie-sending scenarios, but **does not replace** CSRF protection when the application needs it.
- Cookie values can be tampered with unless signed/encrypted and server-validated; a cookie named `role=admin` is not a real role.
- Session cookies must configure Secure/HttpOnly/SameSite and session security policies appropriate for the environment; never echo session tokens in JSON or logs.

Cookies are untrusted input to validate, not a trusted server store merely because the browser manages them.

## 8. Principal: Framework-Authenticated Identity

WebFlux supports `java.security.Principal` as a method argument (and reactive wrappers where appropriate), alongside `ServerWebExchange.getPrincipal()` returning `Mono<Principal>`.

```java
@GetMapping("/whoami")
public Mono<String> whoami(ServerWebExchange exchange) {
    return exchange.getPrincipal()
            .map(Principal::getName)
            .defaultIfEmpty("anonymous");
}
```

This is a snippet inside a controller importing `java.security.Principal`. If there is no principal, `Mono.empty()` is mapped to the string `"anonymous"`. **Do not conclude that an unauthenticated user is allowed to access every resource**: public endpoints may return anonymous; protected endpoints must be blocked by policy (401/403) before reaching the controller.

### @AuthenticationPrincipal Belongs to Spring Security

When integrating `spring-boot-starter-security`/Spring Security WebFlux:

```java
@GetMapping("/secure/profile")
public Mono<ProfileView> profile(
        @AuthenticationPrincipal CustomUser user) {
    return service.profileFor(user.id());
}
```

This is a **conceptual snippet** requiring the Spring Security dependency, `CustomUser`/`ProfileView` types, and a `service` bean. `@AuthenticationPrincipal` is a Spring Security annotation (`org.springframework.security.core.annotation.AuthenticationPrincipal`), not part of plain `spring-boot-starter-webflux`. Do not add it to a demo file without security.

`Authentication` in Spring Security normally implements `Principal`; `Principal.getName()` is an identifier string and does not automatically guarantee application-specific roles, tenants, or permissions. To check permissions, use reactive security configuration, method security where applicable, and domain-level authorization.

### Principal Can Be Empty

`exchange.getPrincipal()` is a Mono; never call `.block()` on the Netty event loop to extract it in a controller. Compose it:

```java
return exchange.getPrincipal()
    .map(Principal::getName)
    .defaultIfEmpty("anonymous")
    .map(name -> new UserView(name));
```

This is non-blocking composition; WebFlux subscribes and writes the HTTP response. If code reads the principal from `@RequestHeader("X-User")` without trusted authentication middleware, a client can switch it to any name.

## 9. What Is ServerWebExchange?

`org.springframework.web.server.ServerWebExchange` encapsulates the entire interaction at the WebFlux layer:

| API | Type or meaning |
| --- | --- |
| `getRequest()` | `ServerHttpRequest` (method, URI, headers, cookies, query params, path, ID...) |
| `getResponse()` | `ServerHttpResponse` (status, headers, cookies, body writing) |
| `getAttributes()` | Mutable `Map<String,Object>` for **one exchange** |
| `getAttribute(key)` | Reads an existing attribute, may be null |
| `getRequiredAttribute(key)` | Required lookup; errors if missing |
| `getAttributeOrDefault(key, fallback)` | Fallback when the key is absent |
| `getPrincipal()` | `Mono<Principal>` or empty Mono |
| `getSession()` | `Mono<WebSession>` |
| `getFormData()` | `Mono<MultiValueMap<String,String>>` |
| `getMultipartData()` | `Mono<MultiValueMap<String,Part>>` |
| `getLocaleContext()` | LocaleContext from the resolver |
| `getLogPrefix()` | Log correlation prefix for the exchange |
| `checkNotModified(...)` | Support for ETag/Last-Modified conditional requests |

**An exchange is not a singleton:** each HTTP interaction has its own attributes and response state. Do not store `ServerWebExchange` in a static map or background thread that outlives the request. When the result body is an incomplete `Flux`, the exchange/connection still has an active lifecycle requiring cleanup on cancel and error.

### Common getRequest() Calls

```java
ServerHttpRequest request = exchange.getRequest();
String method = request.getMethod().name();
String path = request.getPath().value();
String rawQuery = request.getURI().getRawQuery();
String client = request.getHeaders().getFirst("X-Client");
String firstTag = request.getQueryParams().getFirst("tag");
String requestId = request.getId();
```

The snippet above requires imports. `getRawQuery()` can be null if the URI has no query. `getPath().value()` is not a filesystem path; never concatenate it into file APIs. `getId()`/`getLogPrefix()` aid logging and are not security credentials.

### Response Headers/Status

```java
exchange.getResponse().getHeaders()
        .add("X-App-Info", "webflux");
```

Headers can be set before the response is committed; after commit, modifying status/headers is not guaranteed to take effect. Typically controllers return `ResponseEntity<T>` to control status/headers, while a `WebFilter` adds cross-cutting correlation headers.

Do not call `getResponse().setComplete()` and then return a Publisher writing JSON to the same response. Either let the framework manage the body, or handle the response explicitly with `Mono<Void>` per contract.

## 10. Exchange Attributes: Internal Data for a Single Request

A filter can attach metadata when a request arrives:

```java
exchange.getAttributes().put("app.traceId", traceId);
return chain.filter(exchange);
```

The controller reads it via:

```java
String trace = exchange.getRequiredAttribute("app.traceId");
```

Or declares:

```java
@GetMapping("/trace")
public Mono<String> trace(
        @RequestAttribute("app.traceId") String traceId) {
    return Mono.just(traceId);
}
```

`@RequestAttribute` retrieves an **attribute created by the server/filter**, not a query param or header of the same name. Do not confuse `@RequestAttribute` with `@RequestParam` or `@SessionAttribute`.

Rules:

- Use a clear namespaced key such as `app.traceId` to avoid colliding with framework keys.
- Attributes live for **one exchange** and do not persist across requests.
- Attributes can hold any Java object, not just Strings; avoid unsafe casts.
- Do not place credentials/secrets in attributes unless you control everything that can log or serialize them.
- If a filter does not run (due to different route/filter configuration), a missing required attribute causes an error; use `required=false` or fallback checks where appropriate.
- Use a server-generated correlation ID or one verified by trusted ingress. A client-supplied `X-Request-Id` header should be validated/normalized before serving as a trusted trace ID.

**Attributes are not a Session:** reloading a page sends a new request and old exchange attributes are gone. **Attributes are not Reactor Context:** context flows along the subscriber chain, not as a mutable map replacing propagation across schedulers.

## 11. Reading form-urlencoded Data: getFormData()

Request:

```http
POST /api/input/form?name=query HTTP/1.1
Content-Type: application/x-www-form-urlencoded

name=Linh&topic=java&topic=webflux
```

In WebFlux:

```java
@PostMapping(path = "/form",
             consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
public Mono<FormView> form(ServerWebExchange exchange) {
    return exchange.getFormData()
        .map(form -> new FormView(
            form.getFirst("name"),
            form.getOrDefault("topic", List.of())));
}
```

This is a snippet assuming `record FormView(String name,List<String> topic) {}` in the controller.

`getFormData()` returns `Mono<MultiValueMap<String,String>>` decoded from the **form-urlencoded body**. Spring uses the configured `HttpMessageReader`. If Content-Type does not match, the contract returns an empty map rather than “parsing every body as a form.”

**Critical difference:** WebFlux `@RequestParam("name")` reads `?name=query` from the URI and **does not automatically read** `name=Linh` from the form body. In Servlet Spring MVC, request parameters often merge query and form data; do not apply that assumption to the reactive stack.

### Can getFormData Be Called Twice?

`DefaultServerWebExchange` reads and parses the form body into a map and then **caches the result** so `getFormData()` can be called multiple times without re-reading the network stream. That does not mean raw body `Flux<DataBuffer>` streams can be freely read repeatedly.

Because the parser must consume/buffer form data, enforce payload size/memory budgets and reject huge form bodies. For JSON, use `@RequestBody Mono<Dto>` so the framework decodes it instead of calling `getFormData()`.

## 12. Reading Multipart Data: getMultipartData()

For `multipart/form-data`:

```bash
curl -i -F 'description=demo' \
  -F 'file=@sample.txt' \
  http://localhost:8080/api/input/multipart
```

`exchange.getMultipartData()` returns `Mono<MultiValueMap<String,Part>>`, where `Part` represents a form or file part, such as `FormFieldPart` or `FilePart`.

An endpoint inspecting only **metadata** about part names can be written as:

```java
@PostMapping(path = "/multipart",
             consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public Mono<UploadSummary> multipart(ServerWebExchange exchange) {
    return exchange.getMultipartData()
        .map(parts -> new UploadSummary(
            parts.keySet().stream().sorted().toList(),
            parts.values().stream().mapToInt(List::size).sum()));
}
```

This snippet assumes `record UploadSummary(List<String> names,int count) {}`. This is not full upload handling: it neither saves nor scans the file, only counting parts. **Do not log raw file contents or client-supplied raw filenames.**

### Very Important Limitations

- `getMultipartData()` reads/parses the request into a `MultiValueMap` and caches **the parts map** where appropriate; **the contents of each Part are not cached for repeated reading**.
- For large files, full multipart map parsing incurs overhead and memory/disk limits depending on the codec; consider streaming `Flux<PartEvent>` and configuration limits if needed.
- When accessing `Part.content()` as `Flux<DataBuffer>`, data buffers must be consumed, forwarded, or released properly; do not accumulate DataBuffers in an unbounded list.
- `FilePart.filename()` is an **untrusted client-supplied name**; never use it directly as a storage file path.
- Validate file size, part count, MIME/content signatures, filename canonicalization, storage permissions, and antivirus/quarantine depending on risk.
- Set appropriate `maxInMemorySize`/multipart codec limits. Since one request can contain many parts, enforce a total request budget rather than only per-field limits.
- `@RequestPart("file") FilePart file` or `@RequestPart("meta") Mono<Dto>` is a good choice when only a few parts are needed.

**Do not mix two body-consumption mechanisms** (`getMultipartData()` and raw `@RequestBody Flux<PartEvent>`) on the same request and expect to read the same bytes twice.

## 13. Reading JSON Bodies: @RequestBody Mono<T>

With a JSON request body:

```http
POST /api/input/json HTTP/1.1
Content-Type: application/json

{"message":"Hello"}
```

Declaration:

```java
@PostMapping(path = "/json",
             consumes = MediaType.APPLICATION_JSON_VALUE)
public Mono<NoteView> json(
        @RequestBody Mono<NoteInput> input) {
    return input.map(v -> new NoteView(v.message()));
}
```

This snippet requires DTO records/imports. `@RequestBody` uses the appropriate `HttpMessageReader`/Jackson decoder to parse JSON. A body Mono lets you chain operators without blocking the event loop.

**Never call `exchange.getRequest().getBody().collectList().block()` in a controller.** It both blocks and buffers bytes into memory while draining the stream away from the decoder, causing errors if another handler reads the body. To log bodies in a WebFilter, you need a bounded decorator/buffer architecture, redaction, reference counting, and security review—not simply “read once and forward as-is.”

Form-urlencoded, multipart, and JSON are **different body formats**; you cannot simply switch `@RequestParam` annotations and expect WebFlux to read all three.

## 14. getSession(): WebSession and State Storage Limits

`exchange.getSession()` returns `Mono<WebSession>`. When server-managed per-user state is needed, use WebSession instead of Exchange attributes:

```java
@GetMapping("/session-info")
public Mono<SessionView> sessionInfo(
        ServerWebExchange exchange) {
    return exchange.getSession()
        .map(s -> new SessionView(
            s.isStarted(), s.getAttributes().size()));
}
```

This snippet does not return the session ID/token to the client. `WebSession` provides `getId()`, `getAttributes()`, `getMaxIdleTime()`, `invalidate()`, and `save()`; it is not an API for storing unlimited data across requests.

Spring WebFlux method arguments can also accept `WebSession` (or an appropriate reactive wrapper). Calling `getSession()` to read does not necessarily start a new session on the client; per Spring docs, a session is normally not started until attributes are added or the start API is invoked.

### Attributes, Sessions, and Principal Are Not Interchangeable

| Concept | Lifetime | Purpose |
| --- | --- | --- |
| Exchange attribute | Single HTTP exchange | Trace, filter metadata, request-local state |
| Reactor Context | Single subscription chain | Trace/security/reactive context propagation |
| WebSession | Persists across requests per session policy | Server-side user session state |
| Cookie | Sent back by client per browser policies | Session identifier or client preference |
| Principal | Identity from authentication chain | Identifies current user when auth is configured |
| Database record | Durable per domain | Business data and authorization data |

Do not store `ServerWebExchange` or objects holding references to the request/response inside `WebSession`. When using Redis WebSession, store only small, config-serializable data without unintended sensitive details. Sessions do not replace authorization checks on every protected resource access.

## 15. Locale, Method, URI, and Request Context

`ServerWebExchange.getLocaleContext()` provides the locale/time zone from the application's resolver. Method argument `Locale` is supported directly by Spring WebFlux. Do not manually inspect `Accept-Language` and pick the first token when the resolver already supplies this logic.

```java
@GetMapping("/locale")
public Mono<String> locale(Locale locale) {
    return Mono.just(locale.toLanguageTag());
}
```

This snippet returns the locale tag resolved by the application. When a client sends `Accept-Language: vi-VN,vi;q=0.9`, the result—depending on the locale resolver—can be `vi-VN` if configured appropriately; do not treat locale as user identity or country.

Reading paths/canonical request data:

```java
String uri = exchange.getRequest().getURI().toString();
String rawPath = exchange.getRequest().getURI().getRawPath();
String path = exchange.getRequest().getPath().value();
String method = exchange.getRequest().getMethod().name();
String logPrefix = exchange.getLogPrefix();
```

These are snippets. `rawPath` preserves URI percent-encoding; `getPath().value()` represents the WebFlux API path (do not decode twice). Never use raw URI/query as a filesystem path, authorization key, or full log entry when URLs may contain secrets. Forwarded headers can be spoofed unless trusted proxies are configured.

## 16. Data Lifecycle in the Reactive Pipeline

Diagram:

```text
HTTP headers + query + cookies  ──────> Handler argument binding
       |
       +-- WebFilter writes exchange attribute
       |
HTTP body (JSON/form/multipart) ───────> Mono/Flux decoder/parser
       |
Authentication middleware  ───────────> exchange.getPrincipal()
       |
WebSession manager ────────────────────> exchange.getSession()
       |
Controller returns Mono<DTO> / Flux<T>
       |
HTTP infrastructure subscribes / writes response
       |
complete / error / cancel -> cleanup
```

Header/query/cookie data is typically already available in request metadata; body reading is **reactive** and may execute only when downstream subscribes. Do not manually call `subscribe()` to “read the body early” and then return an independent response.

`Mono<Principal>` or `Mono<MultiValueMap<...>>` does not guarantee a new asynchronous thread; Reactor schedules signals and demand. Never call `block()` inside a controller or WebFilter on the Netty event loop. Request data belongs to the exchange; after completion/cancel, do not hold a background lambda referencing the exchange to mutate the response.

## 17. Runnable Code: Spring Boot 3 WebFlux + Java 17

Create a Spring Initializr Maven project:

- Java 17+, Spring Boot **3.x**.
- Dependency `spring-boot-starter-webflux`.
- Dependency `spring-boot-starter-test` (test scope), plus `io.projectreactor:reactor-test` if not already present.
- **Do not add `spring-boot-starter-web`** if you want to be sure Boot selects the WebFlux reactive application type under default configuration.

The demo program needs neither a database nor Spring Security, so `exchange.getPrincipal()` has no user by default and falls back to `"anonymous"`. The demo only **echoes** selected values; it does not expose an endpoint dumping all headers/cookies.

Structure:

```text
src/main/java/com/example/demo/
  DemoApplication.java
  CorrelationFilter.java
  InputController.java
src/test/java/com/example/demo/
  InputControllerTest.java
```

### 17.1. DemoApplication.java

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

### 17.2. CorrelationFilter.java

```java
package com.example.demo;

import java.util.UUID;

import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@Component
@Order(-100)
public class CorrelationFilter implements WebFilter {

    public static final String TRACE_ID = "app.traceId";

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange, WebFilterChain chain) {

        // Server generates the trace ID rather than trusting client-sent X-Trace-Id.
        String trace = UUID.randomUUID().toString();

        exchange.getAttributes().put(TRACE_ID, trace);
        exchange.getResponse().getHeaders()
                .set("X-Trace-Id", trace);

        return chain.filter(exchange);
    }
}
```

The filter sets an exchange-scoped attribute and a response header with the same value. The UUID illustrates a **correlation ID**, not an access token, secret, or authorization input. In production, use observation/tracing infrastructure to correlate spans/requests and order the filter relative to security per policy.

### 17.3. InputController.java

```java
package com.example.demo;

import java.security.Principal;
import java.util.List;

import org.springframework.http.MediaType;
import org.springframework.http.HttpCookie;
import org.springframework.http.HttpHeaders;
import org.springframework.util.MultiValueMap;
import org.springframework.web.bind.annotation.CookieValue;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/input")
public class InputController {

    @GetMapping(path = "/query",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<QueryView> query(
            @RequestParam("q") String q,
            @RequestParam(name = "page", defaultValue = "1") int page,
            @RequestHeader(name = "X-Client",
                           defaultValue = "unknown") String client,
            @CookieValue(name = "theme",
                         defaultValue = "none") String theme,
            @RequestAttribute(CorrelationFilter.TRACE_ID)
                    String traceId,
            ServerWebExchange exchange) {

        // Repeated query params are preserved in MultiValueMap.
        List<String> tags = exchange.getRequest().getQueryParams()
                .getOrDefault("tag", List.of());

        // Without an Authentication provider, principal may be empty.
        return exchange.getPrincipal()
                .map(Principal::getName)
                .defaultIfEmpty("anonymous")
                .map(name -> new QueryView(
                    q, page, List.copyOf(tags), client,
                    theme, name, traceId));
    }

    @GetMapping(path = "/raw",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<RawView> raw(ServerWebExchange exchange) {
        var request = exchange.getRequest();

        String method = request.getMethod().name();
        String path = request.getPath().value();
        String firstTag = request.getQueryParams().getFirst("tag");
        String firstClient = request.getHeaders().getFirst("X-Client");

        HttpCookie cookie = request.getCookies().getFirst("theme");
        String theme = cookie == null ? "none" : cookie.getValue();

        return Mono.just(new RawView(
            method, path,
            firstTag == null ? "none" : firstTag,
            firstClient == null ? "unknown" : firstClient,
            theme,
            exchange.getRequiredAttribute(
                    CorrelationFilter.TRACE_ID)));
    }

    @GetMapping(path = "/whoami",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<UserView> whoami(ServerWebExchange exchange) {
        return exchange.getPrincipal()
                .map(Principal::getName)
                .defaultIfEmpty("anonymous")
                .map(UserView::new);
    }

    @GetMapping(path = "/session-info",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<SessionView> session(ServerWebExchange exchange) {
        // Do not return session ID/token to the client.
        return exchange.getSession()
                .map(s -> new SessionView(
                    s.isStarted(), s.getAttributes().size()));
    }

    @PostMapping(path = "/form",
                 consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE,
                 produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<FormView> form(
            @RequestParam(name = "name", required = false)
                    String queryName,
            ServerWebExchange exchange) {

        // @RequestParam in WebFlux reads only query "name".
        // getFormData reads name and topic from the form-urlencoded BODY.
        return exchange.getFormData()
                .map(values -> new FormView(
                    queryName == null ? "(none)" : queryName,
                    values.getFirst("name"),
                    List.copyOf(values.getOrDefault(
                        "topic", List.of()))));
    }

    @PostMapping(path = "/json",
                 consumes = MediaType.APPLICATION_JSON_VALUE,
                 produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<NoteView> json(
            @RequestBody Mono<NoteInput> input) {
        return input.map(value -> new NoteView(value.message()));
    }

    @PostMapping(path = "/multipart",
                 consumes = MediaType.MULTIPART_FORM_DATA_VALUE,
                 produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<UploadView> multipart(
            ServerWebExchange exchange) {
        // Only summarizes part names; does NOT read/store file bytes.
        return exchange.getMultipartData()
                .map(parts -> new UploadView(
                    parts.keySet().stream().sorted().toList(),
                    parts.values().stream()
                        .mapToInt(List::size).sum()));
    }

    public record QueryView(
            String q, int page, List<String> tags,
            String client, String theme,
            String principal, String traceId) {}

    public record RawView(
            String method, String path,
            String firstTag, String client,
            String theme, String traceId) {}

    public record UserView(String name) {}

    public record SessionView(
            boolean started, int attributeCount) {}

    public record FormView(
            String queryName, String formName, List<String> topics) {}

    public record NoteInput(String message) {}
    public record NoteView(String message) {}

    public record UploadView(
            List<String> partNames, int partCount) {}
}
```

**Why does this code use two paths to read metadata?** The `/query` endpoint demonstrates annotation binding plus Principal; `/raw` demonstrates direct `ServerWebExchange` APIs. Both run on the same Spring WebFlux handler infrastructure.

**Why the Principal fallback?** The demo project does not include Spring Security; `getPrincipal()` is typically empty. In an app with security, principal may be present per policy. `"anonymous"` is only a display output label, **not** an authenticated identity.

**Why do form queryName and formName differ?** To prove that WebFlux `@RequestParam` reads only the URI query while `getFormData()` reads the form body. Do not conflate them as in Spring MVC.

**Why does Multipart only count parts?** The topic is reading data from the exchange; real upload handling requires size limits, file-signature checks, safe storage, and dedicated streaming choices. File contents can still consume resources even when an endpoint only counts part names; never enable a demo metadata endpoint outside test environments without access control.

**About imports:** `HttpHeaders` and `MultiValueMap` were shown in earlier snippets and are not directly referenced in the complete methods; Java permits unused imports (standard Java compilers do not treat them as errors). You may remove them in your IDE to keep the code tidy.

### 17.4. Running the Application

macOS/Linux:

```bash
./mvnw spring-boot:run
```

Windows PowerShell:

```powershell
.\mvnw.cmd spring-boot:run
```

By default, endpoints are served at `http://localhost:8080`. Spring Boot code requires the Maven/Gradle classpath; standalone `javac InputController.java` cannot compile due to missing Spring/Reactor dependencies.

## 18. Curl: Query, Header, Cookie, Principal, and Trace

### 18.1. Query with Repeated Tags and Header/Cookie

```bash
curl -i 'http://localhost:8080/api/input/query?q=a%2Bb%26c&page=2&tag=java&tag=webflux' \
  -H 'X-Client: mobile-app' \
  -H 'Cookie: theme=dark'
```

Expected HTTP 200 with a body containing these fields:

```json
{
  "q": "a+b&c",
  "page": 2,
  "tags": ["java", "webflux"],
  "client": "mobile-app",
  "theme": "dark",
  "principal": "anonymous",
  "traceId": "UUID-varies-per-request"
}
```

The string `"UUID-varies-per-request"` in the JSON above is only an **illustrative placeholder**, not literal stdout. In reality, `traceId` is a UUID generated by the server filter, such as `"550e8400-e29b-41d4-a716-446655440000"`, and the response header `X-Trace-Id` carries the exact same value. Do not hardcode UUIDs or JSON property ordering in tests.

### 18.2. Default Values

```bash
curl -i 'http://localhost:8080/api/input/query?q=hello'
```

Expected `page=1`, `tags=[]`, `client="unknown"`, `theme="none"`, `principal="anonymous"`, while `traceId` changes on every request.

### 18.3. Missing Required Query Param

```bash
curl -i 'http://localhost:8080/api/input/query'
```

Expected **HTTP 400 Bad Request** because `q` is missing. The error body depends on Spring Boot/WebFlux error handling; do not rely on a single fixed JSON format without configuring a custom `ErrorWebExceptionHandler`.

### 18.4. Invalid page Type

```bash
curl -i 'http://localhost:8080/api/input/query?q=ok&page=abc'
```

Expected **400** due to failed String→int conversion. Conversely, `page=-1` still converts, requiring domain validation if disallowed.

### 18.5. Reading ServerWebExchange Metadata Directly

```bash
curl -i 'http://localhost:8080/api/input/raw?tag=java&tag=webflux' \
  -H 'X-Client: cli' \
  -b 'theme=light'
```

Example JSON body:

```json
{
  "method": "GET",
  "path": "/api/input/raw",
  "firstTag": "java",
  "client": "cli",
  "theme": "light",
  "traceId": "UUID-varies-per-request"
}
```

The response `X-Trace-Id` and JSON traceId must match; this tests that the filter creates an exchange attribute and the controller reads it, **not reading a trace directly from a client-sent header**.

### 18.6. Principal Without Security Installed

```bash
curl -i 'http://localhost:8080/api/input/whoami'
```

Expected 200:

```json
{"name":"anonymous"}
```

In an app with Spring Security requiring authentication, requests lacking valid credentials may receive 401/redirect instead of hitting the controller; that is expected policy behavior, not a bug in `exchange.getPrincipal()`.

### 18.7. Session Exposes Metadata Only

```bash
curl -i 'http://localhost:8080/api/input/session-info'
```

Expected JSON response with `started` (boolean) and `attributeCount` (integer). In a demo project without added session attributes, typically `started=false` and `attributeCount=0`. Never echo session IDs or Set-Cookie session tokens as “proof.”

## 19. Curl: form-urlencoded Differs from Query Params

Send a form body:

```bash
curl -i -X POST \
  'http://localhost:8080/api/input/form?name=query' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data 'name=Linh&topic=java&topic=webflux'
```

Expected JSON:

```json
{
  "queryName": "query",
  "formName": "Linh",
  "topics": ["java", "webflux"]
}
```

Because `@RequestParam(name="name")` in WebFlux inspects only the query string, `queryName="query"`, whereas `getFormData().getFirst("name")` is `"Linh"`. If you omit `?name=query`, `queryName` becomes `"(none)"` per the demo code while the body retains Linh.

To avoid manually encoding form fields:

```bash
curl -i -X POST \
  'http://localhost:8080/api/input/form' \
  --data-urlencode 'name=Linh' \
  --data-urlencode 'topic=a+b' \
  --data-urlencode 'topic=Spring & WebFlux'
```

`--data-urlencode` encodes data form-style so literal `+` and `&` do not become unintended delimiters. If you send raw `topic=a+b` in a form body, `+` may be interpreted as a space by the parser; for a literal plus sign, use `%2B`.

### Why Not Use URLDecoder in the Controller?

`getFormData()` has already been decoded by the form parser. If a value is literal `"%2F"`, sent on the wire as `%252F`, the application receives `"%2F"`. Running `URLDecoder.decode(...)` a second time converts it into a slash `"/"` and can cause security bugs or corrupt business values.

## 20. Curl: JSON and Multipart

### 20.1. JSON Body

```bash
curl -i -X POST \
  'http://localhost:8080/api/input/json' \
  -H 'Content-Type: application/json' \
  -d '{"message":"Hello WebFlux"}'
```

Expected HTTP 200:

```json
{"message":"Hello WebFlux"}
```

This uses `@RequestBody Mono<NoteInput>`, not `@RequestParam` or `getFormData`. Sending malformed JSON causes the reactive body reader to typically return 400. If `message` is omitted, the record may receive null under Jackson unless validated; real applications need `@Valid`/constraints and domain checks.

### 20.2. Multipart Form

Create a small file `sample.txt` containing test data and run:

```bash
curl -i -X POST \
  'http://localhost:8080/api/input/multipart' \
  -F 'description=demo' \
  -F 'file=@sample.txt'
```

Example body:

```json
{"partNames":["description","file"],"partCount":2}
```

The Spring multipart codec governs parsing and limits. Do not use a “count parts” example to conclude that uploaded files have been stored, virus-scanned, or MIME-verified. For malicious filenames or oversized files, production code must reject/sanitize properly and clean up resources rather than merely echoing metadata.

## 21. WebTestClient: Testing Controllers and Filters Over Real HTTP

File `src/test/java/com/example/demo/InputControllerTest.java`:

```java
package com.example.demo;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class InputControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void queryHeaderCookieAndFilterAttribute() {
        client.get()
            .uri("/api/input/query?q=a%2Bb%26c&page=2"
                + "&tag=java&tag=webflux")
            .header("X-Client", "mobile-app")
            .cookie("theme", "dark")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().exists("X-Trace-Id")
            .expectBody()
            .jsonPath("$.q").isEqualTo("a+b&c")
            .jsonPath("$.page").isEqualTo(2)
            .jsonPath("$.tags[0]").isEqualTo("java")
            .jsonPath("$.tags[1]").isEqualTo("webflux")
            .jsonPath("$.client").isEqualTo("mobile-app")
            .jsonPath("$.theme").isEqualTo("dark")
            .jsonPath("$.principal").isEqualTo("anonymous")
            .jsonPath("$.traceId").isNotEmpty();
    }

    @Test
    void missingRequiredQueryParameterReturns400() {
        client.get().uri("/api/input/query")
            .exchange().expectStatus().isBadRequest();
    }

    @Test
    void wrongPageTypeReturns400() {
        client.get().uri("/api/input/query?q=ok&page=nope")
            .exchange().expectStatus().isBadRequest();
    }

    @Test
    void rawExchangeSeesRequestMetadata() {
        client.get().uri("/api/input/raw?tag=java&tag=reactor")
            .header("X-Client", "cli")
            .cookie("theme", "light")
            .exchange().expectStatus().isOk()
            .expectBody()
            .jsonPath("$.method").isEqualTo("GET")
            .jsonPath("$.path").isEqualTo("/api/input/raw")
            .jsonPath("$.firstTag").isEqualTo("java")
            .jsonPath("$.client").isEqualTo("cli")
            .jsonPath("$.theme").isEqualTo("light");
    }

    @Test
    void withoutSecurityPrincipalIsAnonymous() {
        client.get().uri("/api/input/whoami")
            .exchange().expectStatus().isOk()
            .expectBody()
            .jsonPath("$.name").isEqualTo("anonymous");
    }

    @Test
    void formBodyIsDifferentFromQueryString() {
        client.post()
            .uri("/api/input/form?name=query")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .body(BodyInserters.fromFormData("name", "Linh")
                .with("topic", "java")
                .with("topic", "webflux"))
            .exchange().expectStatus().isOk()
            .expectBody()
            .jsonPath("$.queryName").isEqualTo("query")
            .jsonPath("$.formName").isEqualTo("Linh")
            .jsonPath("$.topics[0]").isEqualTo("java")
            .jsonPath("$.topics[1]").isEqualTo("webflux");
    }

    @Test
    void jsonBodyIsDecodedByHttpMessageReader() {
        client.post().uri("/api/input/json")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("message", "hello"))
            .exchange().expectStatus().isOk()
            .expectBody()
            .jsonPath("$.message").isEqualTo("hello");
    }

    @Test
    void contentTypeIsPartOfMappingContract() {
        client.post().uri("/api/input/json")
            .contentType(MediaType.TEXT_PLAIN)
            .bodyValue("not-json")
            .exchange()
            .expectStatus().isUnsupportedMediaType();
    }
}
```

Run in a Maven Boot 3 project:

```bash
./mvnw test
```

PowerShell:

```powershell
.\mvnw.cmd test
```

The tests assert exact core values **without hardcoding the filter UUID**. If you want to verify that the `X-Trace-Id` response header **equals** the `traceId` field in the body, use `EntityExchangeResult<byte[]>` and a JSON parser/Jackson or a `WebTestClient` consumer to compare the two dynamic values within the same response. Checking only existence/non-emptiness (as in the sample test) does not prove equality; that is a useful additional assertion.

**Limitations:** this is sample test code, not a claim that it has been executed in a user repository. With Spring Security enabled, requests may be blocked by authentication/CSRF and tests must provide an appropriate security context or credentials. `RANDOM_PORT` exercises a real HTTP server, though it does not cover reverse proxies/CDNs or production configuration.

## 22. Testing a Real Principal with Spring Security

To test an authenticated Principal, add Spring Security WebFlux:

- `spring-boot-starter-security` at runtime, defining a `SecurityWebFilterChain` matching policy.
- `spring-security-test` for testing with mock authentication.
- Use `@AuthenticationPrincipal` or `ReactiveSecurityContextHolder` when the contract needs more than `Principal` name.
- When using WebTestClient, configure `mutateWith(mockUser("alice"))` on a mock-bound WebTestClient or equivalent setups per Spring Security testing docs; do not assume it works with every `RANDOM_PORT` live server not bound to a test security context.
- Over real HTTP, pass Basic/Bearer/cookie/session credentials through the security filter; never fake `X-User: alice` and treat it as a Principal.
- Verify the distinction between **401 Unauthorized** when credentials are missing and **403 Forbidden** when authenticated without sufficient permissions; exact statuses depend on Spring Security configuration, so test against actual policy.
- Verify authentication before returning sensitive content or metadata. Do not treat the presence of an `Optional<Principal>` as authorization in place of checking roles/tenant/resource owner.

A very short snippet (not a standalone compilable file):

```java
@GetMapping("/secure/me")
public Mono<String> me(ServerWebExchange exchange) {
    return exchange.getPrincipal()
        .map(Principal::getName)
        .switchIfEmpty(Mono.error(
            new ResponseStatusException(HttpStatus.UNAUTHORIZED)));
}
```

This endpoint only **reflects the principal name** and is not a complete security policy; in WebFlux Security, protect routes via `SecurityWebFilterChain`. If the authentication is an anonymous Authentication object, distinguish it from a real user per Spring Security policy rather than merely checking whether `Mono<Principal>` emits a value.

## 23. Security: Which Data Is Trustworthy?

### Authentication vs Client-Declared Data

| Input | Inherently trustworthy? | Requirement |
| --- | --- | --- |
| Query `userId=42` | No | Authz check: can the actor read resource 42? |
| Header `X-Role=ADMIN` | No | Read only if a trusted gateway validates and strips client spoofing |
| Cookie `role=admin` | No | Signed/encrypted/server-validated value if needed |
| `Principal` from security chain | Identity established by security | Still must check permission/tenant |
| Exchange attribute from trusted WebFilter | Trusted per internal contract | Do not allow untrusted callers to overwrite |
| Session attribute | Server-side state per session policy | CSRF/session fixation and authz still required |
| `Forwarded`/`X-Forwarded-For` | Can be spoofed | Configure trusted proxy, do not trust directly |
| JSON/form/multipart body | No | Validation, size limits, authorization |

Never construct redirect URLs or external HTTP fetches from raw `Host`/`Forwarded` headers without validation: this risks host-header poisoning, open redirects, or SSRF.

### Privacy in Logs and Responses

Never log or echo all of `exchange.getRequest().getHeaders()`, `getCookies()`, or the raw query string, as they may contain tokens, emails, phone numbers, session IDs, and PII. `Principal.getName()` can also be a personal identifier; return it only in endpoints with proper authorization and clear purpose. The `/query` demo echoes principal for teaching the API, not for verbatim use in public production.

Client-supplied headers like `X-Request-Id` must be bounded in length and allowed characters to prevent log injection or trace spoofing. Server-generated correlation IDs avoid some risks, yet are still not authentication tokens.

## 24. Common Mistakes and How to Fix Them

1. **Using @RequestParam to read a form-urlencoded body in WebFlux.** Out of scope; use `getFormData`/`@ModelAttribute` as appropriate.
2. **Confusing WebFlux with Spring MVC Servlet request parameters.** The two stacks do not merge query and form data in the same way.
3. **Forgetting required=true is the default.** Missing a required query/header/cookie typically causes 400.
4. **Confusing missing q with empty q.** Use validation if blank values are disallowed.
5. **Assuming String→int conversion also checks value ranges.** `-999` is an integer, yet may be invalid for the domain.
6. **Using Map<String,String> for repeated tags.** Use MultiValueMap/List and define a policy for duplicates.
7. **Splitting queries on '&'/'=' after decoding.** Encoded data can turn into delimiters.
8. **Calling URLDecoder.decode again after binding.** Double-decodes and alters original characters.
9. **Treating the X-User header as an authenticated identity.** Headers are client-declared.
10. **Logging full Authorization/Cookie headers.** Leaks credentials.
11. **Returning session IDs in response DTOs.** Leaks tokens and risks session hijacking.
12. **Assuming HttpOnly cookies cannot be read by the server.** HttpOnly blocks JS, not the HTTP server.
13. **Treating Principal.getName as proof of admin privileges.** Authorization is separate.
14. **Assuming exchange attributes persist across multiple requests.** They are request-scoped.
15. **Using @RequestAttribute without the WebFilter that sets it.** A missing required attribute causes an error.
16. **Using both getFormData and getRequest().getBody as independent sources.** Competing body consumption.
17. **Assuming getMultipartData caches file part contents.** The map is cached, but part contents cannot be read twice.
18. **Retaining DataBuffers from multipart without releasing/consuming them.** Can leak native memory.
19. **Trusting FilePart.filename as a safe filesystem path.** Risks path traversal and name collisions.
20. **Failing to limit multipart count/size.** Risks memory/disk exhaustion.
21. **Calling getPrincipal().block() on the Netty event loop.** Blocks reactive processing.
22. **Manually subscribing to Mono<Principal>/getFormData to mutate shared variables.** Race conditions and lifecycle bugs.
23. **Using WebSession as an unbounded global cache.** Increases memory usage and data retention.
24. **Trusting Forwarded/X-Forwarded headers from any client.** Host/proxy spoofing.
25. **Returning internal principal/session/tracing values in public DTOs without checking intent.** Leaks identity/metadata.
26. **Not testing 400/415 in controller argument handling.** Happy paths alone are insufficient.
27. **Not distinguishing JSON @RequestBody from multipart @RequestPart.** Different codecs and validation.
28. **Writing the response body manually while also returning a ResponseEntity/Mono DTO.** Causes double-writing.
29. **Not handling client disconnect/cancel on long uploads.** Leaks file handles and buffers.
30. **Assuming ServerWebExchange is safe to retain after HTTP completion.** Request/response lifecycles are bounded.
31. **Using RequestParam Optional<T> and forgetting empty checks.** Null/empty contracts must be explicit.
32. **Hardcoding case-sensitive header names in custom logic.** HTTP header names are case-insensitive.
33. **Not checking security before echoing another user's cookies/query.** Inadvertent data exposure.
34. **Relying on raw URI as a tenant/authorization identity.** Requires canonical path and domain policy.
35. **Assuming @RequestParam cannot appear on POST requests.** Query params can exist on any HTTP method.

## 25. Production Deployment Checklist

### Binding and Validation

- [ ] Clearly identified which parameters belong to query, path, header, cookie, and JSON/form/multipart body?
- [ ] `@RequestParam` in WebFlux used for query only, without assuming Servlet behavior?
- [ ] `required=false`/`defaultValue`/`Optional` have a clear missing/empty contract?
- [ ] Format/range/size checks enforced on values and conversion errors handled as 400?
- [ ] Repeated query params preserved or rejected according to policy?
- [ ] URL not decoded a second time after Spring binding?
- [ ] `HttpHeaders`/`MultiValueMap` logged with proper redaction?
- [ ] Cookie flags, data integrity, and CSRF/authorization configured?

### Exchange, Principal, and Session

- [ ] Principal comes from a trusted authentication chain, not self-declared headers?
- [ ] Authorization checks the actor, tenant, resource, and action?
- [ ] `Mono.empty()`/anonymous handled appropriately for public vs protected routes?
- [ ] Request attributes have clear namespaced keys and producers?
- [ ] Exchange/session IDs/HTTP objects not stored beyond their valid lifetime?
- [ ] Reactor Context/security context not lost via manual subscribe?
- [ ] WebSession does not retain PII/credentials beyond retention policy?
- [ ] Raw forwarded headers from unconfigured proxies not trusted?

### Bodies and Resources

- [ ] JSON uses `@RequestBody Mono<T>` and the proper decoder?
- [ ] Form-urlencoded uses `getFormData`/binding without colliding with raw body reads?
- [ ] Multipart enforces file size/count limits, safe storage, scanning, and cleanup?
- [ ] Part content/DataBuffers consumed/released properly without double reading?
- [ ] HTTP response not already committed before setting headers/status?
- [ ] Client disconnect/cancel triggers cleanup?
- [ ] Event loop never blocked with `block()`/JDBC/blocking I/O?

### Testing

- [ ] `WebTestClient` verifies query/header/cookie/trace and data conversion?
- [ ] Tested form queryName distinct from formName, plus repeated values?
- [ ] Tested unauthenticated/authenticated principal with real security configuration?
- [ ] Tested JSON input, 400, 415, and malformed bodies?
- [ ] Tested upload metadata/size limits and rejected oversized payloads in realistic environments?
- [ ] Tested through proxy/ingress to verify trusted forwarded headers?
- [ ] Logs verified free of Authorization/Cookie/session/query secrets?

## 26. Knowledge Self-Check

**1.** In WebFlux, does `@RequestParam("name")` automatically read a `name` field from a form body?

**Answer:** No. WebFlux `@RequestParam` binds query parameters only. Use `getFormData()`/`@ModelAttribute` as appropriate for form bodies.

**2.** Are `@CookieValue` and `@RequestHeader("Cookie")` the same?

**Answer:** Both access cookie-related data, but `@CookieValue` binds an individual cookie by name whereas `@RequestHeader` retrieves the raw header string. For multiple cookies and decoding, prefer cookie-aware APIs.

**3.** What happens when `@RequestParam("page") int page` receives `page=abc`?

**Answer:** Conversion fails; typically HTTP 400 under standard error handling.

**4.** What map type should `getRequest().getQueryParams()` return?

**Answer:** `MultiValueMap<String,String>` to preserve repeated query parameters.

**5.** Can Principal be taken directly from a client-sent `X-User` header?

**Answer:** No. Accept identity only from trusted auth middleware/the Spring Security chain, and still enforce authorization checks.

**6.** Why does `exchange.getPrincipal()` return `Mono<Principal>`?

**Answer:** WebFlux uses reactive abstractions; a principal may or may not be present and is composed into the pipeline without blocking.

**7.** Where does `@RequestAttribute` read from?

**Answer:** An exchange/request attribute previously set, for instance by a `WebFilter`; not a query param or header of the same name.

**8.** Can `getFormData()` be called multiple times?

**Answer:** In `DefaultServerWebExchange`, the form body is parsed and cached as a map; calling this API again returns the cached map, which does not mean raw bodies can be consumed twice.

**9.** Does `getMultipartData()` cache the contents of each file part?

**Answer:** No. The map/parts are cached per contract, while each Part's content is not guaranteed to be re-readable.

**10.** Can `WebSession.getId()` be returned in public JSON as an illustration?

**Answer:** You should not. Session IDs/tokens are sensitive data that can lead to session hijacking.

**11.** If there is no principal and the route is public, what should be done?

**Answer:** Handle empty Mono/fallbacks explicitly; for protected routes, the security filter must require authentication rather than treating anonymous as an authorized user.

**12.** How long do ServerWebExchange attributes live?

**Answer:** For the lifetime of a single HTTP exchange; they do not automatically carry over to another request.

**13.** Why shouldn't you read `getRequest().getBody()` and call `block()`?

**Answer:** It blocks the event loop, may consume the single-use body stream, and breaks decoders/memory budgets; use reactive reader/binding APIs.

**14.** Can the `Forwarded` header be trusted unconditionally to determine the original host/protocol?

**Answer:** No. You need trusted proxy configuration and validation to prevent spoofing.

**15.** When should you use `ServerWebExchange` instead of just annotations?

**Answer:** When you need multiple request/response components, attributes, session, principal, form/multipart maps, or infrastructure access that annotation binding cannot express cleanly with a few explicit parameters.

## 27. References

- Spring Framework 6.2 — WebFlux Controller Method Arguments: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/arguments.html
- Spring Framework 6.2 — `@RequestParam` query-only in WebFlux: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/requestparam.html
- Spring Framework 6.2 — `@RequestHeader`: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/requestheader.html
- Spring Framework 6.2 — `@CookieValue`: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/cookievalue.html
- Spring Framework 6.2 — `@RequestAttribute`: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/requestattrib.html
- Spring Framework 6.2 — `@ModelAttribute` / Data Binding: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/modelattrib-method-args.html
- Spring Framework 6.2 — Multipart Content: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/multipart-forms.html
- Spring Framework 6.2 — `@RequestBody`: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/requestbody.html
- Spring Framework 6.2 — WebHandler API and form/multipart parsing: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html
- Spring Framework 6.2 — ServerWebExchange API: https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/web/server/ServerWebExchange.html
- Spring Framework 6.2 — ServerHttpRequest API: https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/http/server/reactive/ServerHttpRequest.html
- Spring Framework — WebTestClient: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
- Spring Security — Reactive WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/index.html
- Spring Security — WebFlux testing: https://docs.spring.io/spring-security/reference/reactive/test/web/index.html
- Reactor Core reference: https://projectreactor.io/docs/core/release/reference/
