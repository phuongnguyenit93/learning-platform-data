# @GetExchange, @PostExchange, and Method Parameter Mapping in Spring HTTP Service Client

## 1. What Problem Does This Lesson Solve?

When a Java service frequently calls HTTP APIs, manual code using `RestClient.get().uri(...).retrieve()` or `WebClient.post().bodyValue(...).retrieve()` can be repeated in many places. Spring Framework's **HTTP Service Client** lets you describe external endpoints with **an annotated Java interface**, and Spring then creates a proxy that builds and executes HTTP requests whenever you call the corresponding method.

Focus of this lesson:

- `@GetExchange` represents an HTTP **GET** request; `@PostExchange` represents an HTTP **POST**.
- `@PathVariable`, `@RequestParam`, `@RequestHeader`, `@CookieValue`, `@RequestBody`, and `@RequestPart` determine **where** Java parameters are placed in the HTTP request.
- `@HttpExchange` defines shared configuration, and `HttpServiceProxyFactory` turns the interface into a runnable client via `RestClientAdapter` or `WebClientAdapter`.
- Choosing synchronous/reactive return values, handling errors, and avoiding misunderstandings when using annotations that resemble Spring MVC controller annotations.

Main example scope: **Java 17+, Spring Framework 6.1.x (Spring Boot 3.3.x)**. HTTP Service Client has existed since Spring Framework 6.0; `RestClient` and the `HttpServiceProxyFactory.builderFor(...)` style used below match Spring 6.1+. Newer conveniences in Spring 7 may differ; they are not needed for this lesson.

## 2. How It Works: interface → proxy → HTTP request

```text
Business code: notesApi.find(42, "vi", "req-123")
   │
   ▼
Proxy created by HttpServiceProxyFactory
   │  Reads @GetExchange and each parameter's annotation
   ├─ GET + URL "/notes/{id}" → "/notes/42"
   ├─ @RequestParam("lang")   → "?lang=vi"
   └─ @RequestHeader("X-Trace-Id") → HTTP header
   │
   ▼
RestClientAdapter or WebClientAdapter
   │
   ▼
RestClient / WebClient → HTTP transport → server
   │
   ▼
Response → decode → return type declared on interface
```

**Important distinctions:**

1. Annotations on the interface **describe the HTTP request**. They do not open sockets or run a server by themselves.
2. `HttpServiceProxyFactory.createClient(YourInterface.class)` creates a proxy object; when a method is called, the proxy builds the request from the method metadata and actual arguments.
3. `RestClientAdapter` uses the synchronous `RestClient` API; `WebClientAdapter` uses the reactive `WebClient` client. The interface is not locked to a specific HTTP library, but **the return type** must match the adapter.
4. `@GetExchange` and `@PostExchange` are specialized forms of `@HttpExchange`. This is a **client-side contract**; although Spring allows sharing some interfaces with controllers, this lesson focuses on the **API-calling** side.

## 3. Declaring Endpoints with @HttpExchange, @GetExchange, and @PostExchange

Example of a notes service:

```java
package demo;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;
import org.springframework.web.service.annotation.PostExchange;

@HttpExchange(url = "/api/v1", accept = MediaType.APPLICATION_JSON_VALUE)
public interface NotesHttpClient {

    @GetExchange("/notes/{id}")
    NoteDto find(
            @PathVariable("id") long id,
            @RequestParam("lang") String language,
            @RequestHeader("X-Trace-Id") String traceId);

    @PostExchange(
            url = "/notes",
            contentType = MediaType.APPLICATION_JSON_VALUE)
    NoteDto create(
            @RequestBody CreateNoteRequest request,
            @RequestHeader("X-Trace-Id") String traceId);
}

record NoteDto(long id, String text) {}
record CreateNoteRequest(String text) {}
```

This is a **contract illustration**: DTOs must be placed where Java can access them; a JSON codec/message converter (such as Jackson) is required at runtime. A complete standalone runnable program is in section 8.

Reading the declaration in order:

- `@HttpExchange(url="/api/v1", accept="application/json")` at the **interface level** applies shared settings to methods: path prefix and expected response format via the `Accept` header.
- `@GetExchange("/notes/{id}")` selects the HTTP GET method and appends the path to the prefix. `{id}` is a URI template variable populated from `@PathVariable("id")`.
- `@PostExchange(url="/notes", contentType="application/json")` selects POST and specifies the `Content-Type` of the request with a body.
- `accept` expresses the **desired response** format; `contentType` expresses the **outgoing request body** format. These two attributes are not synonymous. If the receiver supports multiple formats, `accept` can contain multiple media types.
- `@GetExchange(value="/notes/{id}")` and `@GetExchange(url="/notes/{id}")` are equivalent regarding the path; `value` is an alias for `url`. The same applies to `@PostExchange`.

Other HTTP shortcuts include `@PutExchange`, `@PatchExchange`, and `@DeleteExchange`. When a specific HTTP method is needed, using the corresponding shortcut makes the interface more self-descriptive than `@HttpExchange(method="GET")`.

**HTTP semantics:** GET is used to retrieve information and should normally be safe and idempotent; POST typically creates resources or triggers state-changing operations. Adding annotations **does not make the backend automatically follow HTTP semantics**: the API server itself must implement them properly. Do not use GET to perform transactions with side effects simply because it is convenient to call.

## 4. Mapping Table from Java Parameters to HTTP Request Locations

| Interface declaration | HTTP component | Illustrated result |
| --- | --- | --- |
| `@PathVariable("id") long id` | Replaces `{id}` in URL path | `/notes/42` |
| `@RequestParam("lang") String lang` | Query string (typically) | `?lang=vi` |
| `@RequestParam("tag") List<String> tags` | Multiple query/form values with same name | `?tag=java&tag=spring` |
| `@RequestHeader("X-Trace-Id") String id` | Request header | `X-Trace-Id: req-123` |
| `@CookieValue("session") String token` | Request cookie | `Cookie: session=...` |
| `@RequestBody CreateNoteRequest body` | Entire request body | JSON when JSON is configured |
| `@RequestPart("file") Resource file` | One part in a multipart body | `multipart/form-data` |
| `@RequestAttribute("key") Object attr` | Client-internal request attribute | Does not become a header/query automatically |
| `URI uri` (no annotation) | Dynamic URL, overrides annotation URL | Runtime URL |
| `UriBuilderFactory factory` (no annotation) | Factory creating the URI for invocation | Controls base URL/encoding |
| `HttpMethod method` (no annotation) | Overrides HTTP method | Use only when truly dynamic |

`String`, numeric, and enum values can be converted according to Spring's conversion mechanism. `@RequestParam` and `@RequestHeader` can accept `Collection`, `Map`, and `MultiValueMap` under the appropriate rules; check whether the server accepts multiple values with the same name. `@PathVariable` also supports a map containing multiple path variables.

**Crucial:** `@RequestParam` on a client does not mean "form parameter" in every situation. With `Content-Type: application/x-www-form-urlencoded`, parameters are sent in the **form body**; other requests use the query string. Do not guess the physical location based on the annotation name alone.

### 4.1 @PathVariable: Filling the URI Template

```java
@GetExchange("/users/{userId}/orders/{orderId}")
String getOrder(
        @PathVariable("userId") long userId,
        @PathVariable("orderId") String orderId);
```

Calling `getOrder(15, "A-9")` produces the logical path `/users/15/orders/A-9` (plus interface prefix and client base URL). The parameter names `"userId"` and `"orderId"` must match the placeholders. If they mismatch, the request may fail during URI resolution; verify this immediately in tests.

You should **explicitly specify the annotation name** like `@PathVariable("userId")` rather than `@PathVariable long userId` to avoid depending on compiler parameter-name retention (`-parameters`). Dynamic values are encoded by the URI template; do not manually concatenate URL strings from arbitrary input.

### 4.2 @RequestParam: Query and Form-Urlencoded

Common GET:

```java
@GetExchange("/books")
List<BookDto> search(
        @RequestParam("q") String keyword,
        @RequestParam("page") int page,
        @RequestParam(value = "lang", required = false) String language);
```

Calling `search("spring web", 2, null)` semantically produces a query containing `q=spring%20web&page=2` (exact percent-encoding depends on the URI builder). `lang` is omitted when null is allowed. Do not assert that every space is always encoded as `%20`: some form/query strategies may use `+`. Use `UriComponentsBuilder`/URI templates instead of manually concatenating `?q=`.

POST form:

```java
@PostExchange(
        url = "/oauth/token",
        contentType = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
String exchangeToken(
        @RequestParam("grant_type") String grantType,
        @RequestParam("code") String code);
```

Here `grant_type` and `code` belong to the **form body** (e.g., `grant_type=authorization_code&code=abc`), **not JSON**. For a JSON body, use `@RequestBody` instead of misusing `@RequestParam`.

`@RequestParam("tag") List<String> tags` and `MultiValueMap<String, String>` are useful for multi-value filters; server parsing behavior must be tested with actual requests.

### 4.3 @RequestHeader and @CookieValue

```java
@GetExchange("/profile")
String profile(
        @RequestHeader("Authorization") String bearerToken,
        @RequestHeader("X-Request-Id") String requestId,
        @CookieValue("locale") String locale);
```

These headers **are only sent** per the arguments passed when calling the method; there is no automatic login. Production examples usually prefer configuring authorization in a `RestClient.Builder` interceptor or `WebClient.Builder` filter / security integration, because passing raw tokens through every method signature is repetitive and risks leaking them in logs.

`@RequestHeader` in an HTTP interface can **append** values to headers that already exist on the client; do not assume it overwrites a default header. Duplicate headers such as `Authorization` can cause errors or risks; verify your actual configuration. `@CookieValue` adds a client-side Cookie; it does not read cookies from incoming server requests unless the application explicitly forwards them.

### 4.4 @RequestBody: Sending the Whole Entity

```java
record CreateUser(String name, String email) {}
record UserView(long id, String name) {}

@PostExchange(
        url = "/users",
        contentType = MediaType.APPLICATION_JSON_VALUE,
        accept = MediaType.APPLICATION_JSON_VALUE)
UserView createUser(@RequestBody CreateUser payload);
```

JSON serialized (with Jackson):

```http
POST /users HTTP/1.1
Content-Type: application/json
Accept: application/json

{"name":"Lan","email":"lan@example.org"}
```

`@RequestBody` defines the entire HTTP payload rather than spreading each object property into query parameters. The `record` payload is encoded by HTTP message converters (RestClient) or codecs (WebClient). If the JSON codec is missing, `Content-Type` is wrong, or the server returns JSON incompatible with the DTO, encode/decode errors may occur.

With WebClient, `@RequestBody Mono<CreateUser>` can also send reactive data; however, do not use publisher/reactive return types with `RestClientAdapter` and expect it to convert to reactive automatically.

### 4.5 @RequestPart: Multipart Upload

```java
import org.springframework.core.io.Resource;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.service.annotation.PostExchange;

// Fragment inside an HTTP service interface
@PostExchange(
        url = "/attachments",
        contentType = MediaType.MULTIPART_FORM_DATA_VALUE)
String upload(
        @RequestPart("description") String description,
        @RequestPart("file") Resource file);
```

`@RequestPart` maps *one part* of a multipart body; each part has a name and can have its own Content-Type. `Resource` typically represents a file; `HttpEntity<?>` helps set per-part headers; supporting clients may also accept `MultipartFile` or Spring `Part` depending on the adapter and version. Do not combine plain JSON `@RequestBody` with multiple `@RequestPart` parameters expecting Spring to assemble a multipart request automatically. Check file size limits, streaming, buffering, and filename protection in practice.

### 4.6 Optional Parameters and Null Values

Parameters cannot arbitrarily take `null`: the framework needs to know which annotations allow `required=false` or are declared optional (e.g., `Optional<T>`). If a field is optional, express the contract clearly:

```java
@GetExchange("/books")
String list(@RequestParam(value = "category", required = false)
            String category);
```

When the user does not select a category, the method can receive `null` and **omit** this parameter. For required data, validate at the business boundary before calling the HTTP client to fail earlier rather than relying on the proxy to enforce business constraints.

## 5. From Interface to Real HTTP Client with HttpServiceProxyFactory

An HTTP interface **is not implemented with `new NotesHttpClient()`**; it needs a proxy. With Spring Framework 6.1 and `RestClient`:

```java
import org.springframework.web.client.RestClient;
import org.springframework.web.client.support.RestClientAdapter;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;

RestClient restClient = RestClient.builder()
        .baseUrl("https://notes.example.org")
        .defaultHeader("X-App", "learning")
        .build();

RestClientAdapter adapter = RestClientAdapter.create(restClient);
HttpServiceProxyFactory factory =
        HttpServiceProxyFactory.builderFor(adapter).build();

NotesHttpClient notes = factory.createClient(NotesHttpClient.class);
NoteDto note = notes.find(42L, "vi", "req-123");
```

This is a fragment meant for a project that already has `NotesHttpClient` and `NoteDto` from section 3; `notes.example.org` is only an illustrative host and does not actually run. **Note `builderFor(adapter)`:** this is the appropriate initialization style for Spring 6.1+, replacing `HttpServiceProxyFactory.builder(adapter)` which was deprecated in 6.1.

In Spring Boot, you can register the client proxy as a bean:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.support.RestClientAdapter;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;

@Configuration
class RemoteNotesConfiguration {

    @Bean
    NotesHttpClient notesHttpClient(RestClient.Builder builder) {
        RestClient client = builder
                .baseUrl("https://notes.example.org")
                .build();

        return HttpServiceProxyFactory
                .builderFor(RestClientAdapter.create(client))
                .build()
                .createClient(NotesHttpClient.class);
    }
}
```

This is a **Spring configuration fragment**. Inject the Boot-managed `RestClient.Builder` to leverage shared customizations if present. Reuse the proxy bean and underlying client; do not rebuild the factory on every call. Explicitly configure the base URL per environment/configuration, along with appropriate timeouts, TLS, authentication, logging/metrics, and retries.

### Choosing WebClient When Reactive Is Needed

```java
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.support.WebClientAdapter;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;
import reactor.core.publisher.Mono;

interface ReactiveNotesClient {
    @GetExchange("/notes/{id}")
    Mono<String> find(@org.springframework.web.bind.annotation.PathVariable("id")
                      long id);
}

WebClient webClient = WebClient.builder()
        .baseUrl("https://notes.example.org")
        .build();

ReactiveNotesClient reactive =
        HttpServiceProxyFactory
                .builderFor(WebClientAdapter.create(webClient))
                .build()
                .createClient(ReactiveNotesClient.class);

Mono<String> publisher = reactive.find(42L);
```

This fragment is used inside a Java method (loose variable declarations cannot be placed directly at file level). It requires `spring-webflux` and an appropriate HTTP connector. `Mono<String>` is a publisher: the actual request runs upon subscription. In a WebFlux handler, return the publisher; do not call `block()` on the event loop. With `RestClientAdapter`, signatures like `String`, `List<T>`, `ResponseEntity<T>`, or `void` are natural; with `WebClientAdapter`, both `Mono<T>` and `Flux<T>` are supported.

## 6. Parameter Mapping: Commonly Misunderstood Scenarios

| Scenario | Intended code | Generated HTTP | Correct approach |
| --- | --- | --- | --- |
| GET item by id | `@GetExchange("/items/{id}")` + `@PathVariable("id")` | GET `/items/7` | Match variable names exactly |
| GET filter | `@RequestParam("sort")` | Query `?sort=newest` | Encode user input, do not concatenate raw URLs |
| POST JSON | `@PostExchange(contentType="application/json")` + `@RequestBody` | JSON in body | Have JSON codec configured |
| POST HTML form | `@PostExchange(contentType="application/x-www-form-urlencoded")` + `@RequestParam` | key=value pairs in body | Server must parse form data |
| POST upload | `@PostExchange(contentType="multipart/form-data")` + `@RequestPart` | Multipart body | Specify part names accurately |
| Dynamic header | `@RequestHeader("X-Trace-Id")` | HTTP header | Avoid duplicates / logging secrets |
| Dynamic URL | `URI uri` | Runtime URI replacing static url | Validate target host beforehand |

**Do not infer that these annotations behave identically to Spring MVC controller argument resolution.** This is the **outgoing request** direction, so `@RequestBody` serializes for sending (not deserializing an incoming client request); `@RequestHeader` adds an outgoing request header (not reading an incoming header). Moreover, not every server-side annotation like `@ModelAttribute` or `@RequestMapping` has the same meaning on an HTTP Service Client.

### Dynamic URI and Method (Advanced Case)

```java
import java.net.URI;
import org.springframework.http.HttpMethod;
import org.springframework.web.service.annotation.HttpExchange;

interface DynamicClient {
    @HttpExchange(method = "GET", url = "/fallback")
    String exchange(URI uri, HttpMethod method);
}
```

Spring recognizes `URI` and `HttpMethod` as two special parameters that allow overriding the declared URL/method. **Do not pass arbitrary end-user URIs directly into the method**: this risks SSRF, sending credentials to unknown hosts, or bypassing the intended base URL. Use only when the endpoint must be chosen dynamically and with allowlist/validation.

### When Custom Argument Mapping Is Needed

A business parameter like `SearchCriteria` is not automatically expanded by Spring into multiple query fields. You can declare each `@RequestParam` explicitly, or register an `HttpServiceArgumentResolver` on `HttpServiceProxyFactory.Builder` when the pattern genuinely repeats. A custom resolver must recognize the parameter type, translate it into request data on `HttpRequestValues.Builder`, and return `true` if handled; otherwise return `false`. That is a **proxy** extension, not a replacement for controller argument resolvers.

## 7. Return Types, HTTP Errors, and Lifecycle

### 7.1 Return Types by Adapter

| Backend type | HTTP Service method return type | Meaning |
| --- | --- | --- |
| `RestClientAdapter` | `String`, `BookDto`, `List<BookDto>` | Synchronous call and body decoding |
| `RestClientAdapter` | `ResponseEntity<BookDto>` | Includes status, headers, body |
| `RestClientAdapter` | `ResponseEntity<Void>` or `void` | Only status matters / no body needed |
| `WebClientAdapter` | `Mono<BookDto>` | Single reactive value |
| `WebClientAdapter` | `Flux<BookDto>` | Multiple reactive elements/stream |
| `WebClientAdapter` | `Mono<ResponseEntity<BookDto>>` | Reactive status/headers/body |

Do not declare `Flux<T>` with synchronous RestClient expecting it to stream automatically; do not declare synchronous signatures and call them on an event-loop thread expecting them not to block.

### 7.2 HTTP Statuses and Network Failures

By default, `RestClient`/`WebClient` usually turn **4xx/5xx** into errors when the HTTP Service method processes the response. With RestClient, you can set `defaultStatusHandler(...)`; with WebClient, configure `defaultStatusHandler(...)` or filters on the underlying client. DNS, connect, timeout, and TLS errors are **transport failures**, not 404/500 responses, and require a different handling strategy.

Keep in mind:

- 404 is sometimes a normal "not found" case; use `ResponseEntity` or a status handler when the contract calls for returning appropriate empty/null instead of propagating every error.
- Do not blindly retry resource-creating POSTs without an idempotency key; duplicates can occur if the first request succeeded but the response was lost.
- Timeouts, connection pools, proxies, TLS, logging, and observability live in the underlying RestClient/WebClient/HTTP engine configuration, **not** as attributes of `@GetExchange`.
- `@RequestHeader("Authorization")` and `@CookieValue` may contain secrets. Do not log full method arguments/URIs.
- If an external API changes JSON fields or statuses, the proxy does not automatically "heal" the schema; contract/integration tests are required.

## 8. Standalone Runnable Java 17+ Example: Demonstrating GET, POST, and Parameter Mapping

This example uses the JDK `HttpServer` as an HTTP server running on localhost, `RestClient` as the client, and an `@GetExchange`/`@PostExchange` HTTP interface. **No account or Internet connection is needed to call the API**; Gradle downloads Maven dependencies on the first run if not cached.

Directory structure:

```text
http-service-demo/
├── build.gradle
└── src/main/java/demo/HttpInterfaceDemo.java
```

`build.gradle` (reference run with Spring Boot 3.3.13 → Spring Framework 6.1.21):

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web:3.3.13'
}

application {
    mainClass = 'demo.HttpInterfaceDemo'
}
```

`src/main/java/demo/HttpInterfaceDemo.java`:

```java
package demo;

import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.support.RestClientAdapter;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;
import org.springframework.web.service.annotation.PostExchange;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;

public class HttpInterfaceDemo {

    @HttpExchange("/v1")
    public interface NotesApi {
        @GetExchange("/notes/{id}")
        String get(
                @PathVariable("id") long id,
                @RequestParam("lang") String language,
                @RequestHeader("X-Trace-Id") String traceId);

        @PostExchange(
                url = "/notes",
                contentType = MediaType.TEXT_PLAIN_VALUE,
                accept = MediaType.TEXT_PLAIN_VALUE)
        String post(
                @RequestBody String text,
                @RequestHeader("X-Trace-Id") String traceId);
    }

    public static void main(String[] args) throws IOException {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/v1/notes", HttpInterfaceDemo::handle);
        server.start();

        try {
            String baseUrl =
                    "http://127.0.0.1:" + server.getAddress().getPort();

            RestClient restClient = RestClient.builder()
                    .baseUrl(baseUrl)
                    .build();

            NotesApi notes = HttpServiceProxyFactory
                    .builderFor(RestClientAdapter.create(restClient))
                    .build()
                    .createClient(NotesApi.class);

            System.out.println(notes.get(42, "vi", "T-01"));
            System.out.println(notes.post("Spring Client", "T-02"));
        } finally {
            server.stop(0);
        }
    }

    private static void handle(com.sun.net.httpserver.HttpExchange exchange) throws IOException {
        try {
            String method = exchange.getRequestMethod();
            String trace =
                    exchange.getRequestHeaders().getFirst("X-Trace-Id");
            String result;

            if ("GET".equals(method)) {
                result = "GET " + exchange.getRequestURI().getRawPath()
                        + "?" + exchange.getRequestURI().getRawQuery()
                        + " trace=" + trace;
            } else if ("POST".equals(method)) {
                String body = new String(
                        exchange.getRequestBody().readAllBytes(),
                        StandardCharsets.UTF_8);
                result = "POST body=" + body + " trace=" + trace;
            } else {
                exchange.sendResponseHeaders(405, -1);
                return;
            }

            byte[] bytes = result.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=UTF-8");
            exchange.sendResponseHeaders(200, bytes.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(bytes);
            }
        } finally {
            exchange.close();
        }
    }
}
```

Run:

```bash
gradle run
```

If the project has a Gradle Wrapper: macOS/Linux `./gradlew run`; Windows PowerShell `.\gradlew.bat run`. With Java 17+ and the right dependencies, the two lines printed by the program are:

```text
GET /v1/notes/42?lang=vi trace=T-01
POST body=Spring Client trace=T-02
```

That is **stdout produced by `System.out.println`**; Gradle may print additional build logs. The server uses a random loopback port so no port is hardcoded. The `/v1` path comes from interface-level `@HttpExchange`, `/notes/{id}` from `@GetExchange`, `42` substitutes `{id}`, `lang=vi` comes from `@RequestParam`, and `X-Trace-Id` becomes a header. POST sends the exact string `Spring Client` as a text/plain body.

Note that the program does not start a `SpringApplication` or create an MVC controller. This proves that the HTTP interface works through a proxy and a real HTTP client without needing a Spring IoC container to run.

### Switching POST from text/plain to JSON

In real applications, you can replace the declaration with:

```java
record CreateNoteRequest(String text) {}
record NoteDto(long id, String text) {}

@PostExchange(
        url = "/notes",
        contentType = MediaType.APPLICATION_JSON_VALUE,
        accept = MediaType.APPLICATION_JSON_VALUE)
NoteDto create(@RequestBody CreateNoteRequest request);
```

This is a **fragment**; the corresponding server must understand JSON, return JSON, and the project must have a JSON codec/message converters. Unlike the demo, you will need a real note-creation handler and response DTO.

## 9. Common Mistakes and How to Avoid Them

1. **Not creating a proxy:** annotated interfaces do not become beans automatically. Create one with `HttpServiceProxyFactory` or configure a version-compatible auto-registration mechanism.
2. **Mixing server/client annotations:** `@RequestParam` on an HTTP service *builds an outgoing request*; it does not read queries from incoming Spring MVC server requests.
3. **Forgetting explicit @PathVariable names:** `{id}` and `@PathVariable("userId")` mismatching will fail. Keep names consistent.
4. **Sending JSON via @RequestParam:** for JSON POSTs, use `@RequestBody` and the proper `contentType`; form-urlencoded is a different scenario.
5. **Sending a body with @GetExchange:** GET APIs should not rely on a request body; many proxies/caches/servers do not support it or lack stable semantics.
6. **Declaring @RequestPart with Content-Type application/json:** multipart requires `multipart/form-data` and per-part formats supported by the server.
7. **Unclear null parameter validity:** explicitly declare `required=false`/`Optional` for optional parameters; validate required inputs.
8. **Sending duplicate Authorization from defaultHeader + @RequestHeader:** check header-appending behavior and avoid turning a token into an unintended header list.
9. **Using @PostExchange for non-idempotent operations with auto-retry:** can create duplicate data. Define an idempotency key and retry policy.
10. **Switching RestClient ↔ WebClient while keeping incompatible return types:** choose sync/reactive types matching the adapter; do not block on the WebFlux event loop.
11. **Ignoring error codes and timeouts:** 400/500 statuses differ from network errors; configure handlers, controlled logging, and timeouts on the underlying client.
12. **Allowing uncontrolled dynamic URIs:** can send requests to out-of-scope hosts or cause SSRF. Validate scheme, host, port, and destination network.
13. **Assuming Accept is Content-Type:** `Accept` describes the expected response; `Content-Type` describes the request payload.
14. **Writing tests that only assert mock interface method returns:** also have tests that actually send requests to a mock/local server to verify URLs, headers, query/body, and HTTP statuses.

## 10. Practice Exercises and Comprehension Check

**Exercise 1 – Read the request.**

```java
@HttpExchange("/api")
interface ProductApi {
    @GetExchange("/products/{id}")
    String find(
            @PathVariable("id") int id,
            @RequestParam("region") String region,
            @RequestHeader("X-Client") String client);
}
```

Assuming the base URL is `https://shop.example.org`, calling `find(9, "vn", "portal")`. Structurally, the result is:

```http
GET /api/products/9?region=vn HTTP/1.1
Host: shop.example.org
X-Client: portal
```

There is no JSON request body. The HTTP lines above represent the logical request; actual HTTP transport may use HTTP/2 or add other headers.

**Exercise 2 – Fix the mapping.** Does the following code send a JSON POST properly?

```java
@PostExchange(url = "/customers", contentType = "application/json")
String create(@RequestParam("name") String name);
```

**Answer:** Not if the server requires a JSON body. Use a DTO/record and `@RequestBody`. Here `@RequestParam` adds a query parameter because the content type is not form-urlencoded.

**Exercise 3 – Optional.** If an HTTP service interface has parameter `@RequestParam(value="sort", required=false) String sort`, can it be called with `null`? **Answer:** Yes; Spring is allowed to omit optional parameters. For required params, pass a value or use an appropriate optional mechanism.

**Exercise 4 – Choose the adapter.** What should an interface returning `Mono<BookDto>` use? **Answer:** `WebClientAdapter` / a reactive backend; whereas sync return types like `BookDto`/`ResponseEntity<BookDto>` are natural with `RestClientAdapter`.

**Exercise 5 – Distinguish headers.** What headers does `@PostExchange(contentType="application/json", accept="application/json")` produce? **Answer:** `Content-Type: application/json` to describe the outgoing body and `Accept: application/json` to indicate the client wants JSON back.

## Official References

- [Spring Framework — REST Clients: HTTP Service Clients, Method Parameters, Return Values](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html#rest-http-interface)
- [Spring Framework 6.1 — @HttpExchange Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/service/annotation/HttpExchange.html)
- [Spring Framework 6.1 — @GetExchange Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/service/annotation/GetExchange.html)
- [Spring Framework 6.1 — @PostExchange Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/service/annotation/PostExchange.html)
- [Spring Framework 6.1 — HttpServiceProxyFactory Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/service/invoker/HttpServiceProxyFactory.html)
