# ExchangeFilterFunction and Shared Configuration in WebClient

## 1. Context: Why Does WebClient Need Filters?

`WebClient` is the reactive HTTP client in Spring WebFlux. An application often calls many external APIs, and those calls share recurring rules: setting a base address, adding headers, sending authentication credentials, logging, attaching tracing IDs, or observing response statuses.

If every method repeats these tasks itself, business logic gets mixed with HTTP mechanics; when a policy changes, you have to edit many places. `WebClient.Builder` handles **shared default configuration**, whereas `ExchangeFilterFunction` handles **cross-cutting logic per HTTP exchange**. The two mechanisms work together with distinct responsibilities.

For example, an order service needs to call an inventory API. Business code only cares about "fetching stock for a product"; shared configuration can hold `baseUrl` and `Accept`, while a filter can add a trace ID and record the method, path, and status code. An individual request can still be customized separately.

Goals of this lesson:

- Understand where filters execute in the `WebClient` call chain and the roles of `ClientRequest`, `ExchangeFunction`, and `ClientResponse`.
- Know how to create, register, order, and compose `ExchangeFilterFunction` instances.
- Distinguish `defaultHeader`, `defaultRequest`, `filter`, and `mutate()`; organize configuration for multiple HTTP clients.
- Know how to pass per-request data to a filter, test filters, and avoid pitfalls involving reactive async execution, security, and response bodies.

## 2. How ExchangeFilterFunction Works

A filter has this core contract:

```java
Mono<ClientResponse> filter(ClientRequest request, ExchangeFunction next);
```

Where:

| Component | Meaning |
| --- | --- |
| `ClientRequest` | The request represented as method, URL, headers, cookies, body, and attributes; in principle an immutable object. |
| `ExchangeFunction next` | The next step in the chain: either the next filter or the component that actually sends HTTP. |
| `ClientResponse` | The HTTP response containing status, headers, and a streaming body for further processing. |
| `Mono<ClientResponse>` | The asynchronous result of an exchange; the filter can transform, observe, or return an error using Reactor semantics. |

A minimal filter:

```java
ExchangeFilterFunction addClientHeader = (request, next) -> {
    ClientRequest updated = ClientRequest.from(request)
            .headers(headers -> headers.set("X-Client-Name", "inventory-service"))
            .build();

    return next.exchange(updated);
};

WebClient client = WebClient.builder()
        .baseUrl("https://inventory.example")
        .filter(addClientHeader)
        .build();
```

`ClientRequest.from(request)` copies existing request data into a builder to modify what is needed. `headers(...set(...))` sets a single header value; use `header("Name", "value")` to append a value if that is the intent. In the filter above, `next.exchange(updated)` keeps the chain moving. Omitting `next.exchange` means the filter short-circuits the default path and must itself return an appropriate `Mono<ClientResponse>` or error signal.

**Execution timing:** calling `client.get().uri(...).retrieve().bodyToMono(...)` constructs a reactive work description. Filters execute when the stream is subscribed to, such as by an upstream layer or `block()` in a demo program. Never assume that merely building the `Mono` has already sent the request.

### 2.1 Filter Order: Outbound and Inbound

Suppose the builder registers `filterA` and then `filterB`:

```text
Subscribe to stream
    |
    v
A: before next.exchange(...)
    |
    v
B: before next.exchange(...)
    |
    v
HTTP exchange
    |
    v
B: observe ClientResponse
    |
    v
A: observe ClientResponse
    |
    v
WebClient caller receives result
```

The request-side order is **A → B → HTTP**; as the response returns through corresponding `flatMap`/`doOnNext` steps, the order is **HTTP → B → A**. If an error occurs before a `ClientResponse` exists, `doOnError`/`onErrorResume` branches registered along the chain observe or handle that signal. Each subscription to the stream can re-run the exchange; this is especially important when combined with `retry`.

A filter that records input/output metadata without consuming the body:

```java
ExchangeFilterFunction logMetadata = (request, next) -> {
    long started = System.nanoTime();
    System.out.println("Request: " + request.method() + " " + request.url().getPath());

    return next.exchange(request)
            .doOnNext(response -> {
                long elapsedMs = (System.nanoTime() - started) / 1_000_000;
                System.out.println("Status: " + response.statusCode().value()
                        + ", elapsedMs=" + elapsedMs);
            })
            .doOnError(error ->
                    System.err.println("Transport/filter failure: "
                            + error.getClass().getSimpleName()));
};
```

This is a learning example; in real applications, use a configured logger and integrated observability libraries. Never log `Authorization`, `Cookie`, bodies containing personal data, or full URLs containing secret parameters. If measuring duration per subscription or retry attempt, capture the start timestamp inside `Mono.defer(...)` or use dedicated instrumentation to avoid reusing stale timestamps.

## 3. Creating Purpose-Specific Filters

### 3.1 Full Form and Processor Helpers

The two-parameter lambda `(request, next) -> ...` is useful when inspecting both request and response. For one-sided operations, you can use:

```java
ExchangeFilterFunction requestOnly =
        ExchangeFilterFunction.ofRequestProcessor(request ->
                Mono.just(ClientRequest.from(request)
                        .headers(headers -> headers.set("X-Source", "web"))
                        .build()));

ExchangeFilterFunction responseOnly =
        ExchangeFilterFunction.ofResponseProcessor(response -> {
            System.out.println("HTTP " + response.statusCode().value());
            return Mono.just(response);
        });
```

Import `reactor.core.publisher.Mono` and `org.springframework.web.reactive.function.client.*` types. These two factories are convenient when transforming only one side without managing `next.exchange(...)`. You must return a valid request/response for the chain to proceed.

You can compose two filters in order with `first.andThen(second)`; when using `WebClient.Builder`, calling `filter(...)` multiple times is usually clearer.

### 3.2 Authentication, Tokens, and Header Policies

`ExchangeFilterFunctions.basicAuthentication(username, password)` is a built-in filter for sending HTTP Basic Authentication, appropriate when the API actually requires Basic Auth and secrets are supplied securely from external configuration.

If a Bearer token varies per request, you can set the header directly on the request or build a filter that accepts a token source. Structural example for an already available token, without fetching tokens over the network:

```java
ExchangeFilterFunction bearerToken(String token) {
    return (request, next) -> {
        ClientRequest authorized = ClientRequest.from(request)
                .headers(headers -> headers.setBearerAuth(token))
                .build();
        return next.exchange(authorized);
    };
}
```

This is an **illustrative method** placed inside a Java class and requiring a valid token for the target API. Never hardcode real secrets in source code, and never share a single fixed token across all users if the token represents individual identities. When a token must be loaded/refreshed asynchronously, return a `Mono` chain from the token provider; never perform blocking I/O on the event loop. Only send credentials to trusted configured hosts; never automatically forward auth headers to other hosts.

### 3.3 Blocking Requests and Handling Responses

A filter can enforce policies before sending, such as rejecting requests missing a required attribute:

```java
ExchangeFilterFunction requireTenant = (request, next) -> {
    if (request.attribute("tenantId").isEmpty()) {
        return Mono.error(new IllegalArgumentException("Missing tenantId"));
    }
    return next.exchange(request);
};
```

This is a local client-side error, **not** an HTTP 4xx response. If you want to construct a synthetic `ClientResponse` to short-circuit sending, define its status/body and semantics for callers clearly.

**Pay special attention to the body:** a filter sees `ClientResponse`, whose body must be consumed or released properly. A filter that only observes metadata and does `return Mono.just(response)` is generally safe because the caller still receives the response to read its body. Conversely, if a filter reads or discards the response itself (e.g., switching flows after HTTP 401), it must release the old content, such as via `response.releaseBody()`, before making another request. Never call `response.bodyToMono(String.class)` just to "preview-log" and then pass the already consumed response downstream; that risks body-reading failures or resource leaks.

`retrieve()` normally turns HTTP 4xx/5xx into errors under default response handling; `next.exchange(...)` itself can successfully emit a `ClientResponse` carrying status 404/500. Thus a filter's `doOnError` **does not replace** `doOnNext(response -> inspect status)` for observing HTTP statuses. Business error-code mapping should sit close to the specific API via `retrieve().onStatus(...)` when appropriate.

## 4. Shared Configuration with WebClient.Builder

`WebClient.Builder` gathers common settings before building the client:

| Builder API | When to use | Points to remember |
| --- | --- | --- |
| `baseUrl(String)` | Many requests share an API host/prefix. | Requests passing absolute URIs can target a different host; guard against credential leakage. |
| `defaultHeader(name, values...)` | Default headers such as `Accept` or app identification. | Only adds defaults if the request has not already provided that header name. |
| `defaultHeaders(Consumer<HttpHeaders>)` | Add, replace, or remove declared default headers. | Distinct from mutating headers on a single request passing through a filter. |
| `defaultCookie(...)`, `defaultCookies(...)` | Default cookies for suitable requests. | Do not use sensitive cookies on clients calling multiple domains. |
| `defaultRequest(Consumer<RequestHeadersSpec<?>>)` | Customize each request upon creation, e.g., setting attributes. | Does not handle responses; do not substitute for filters that observe responses. |
| `filter(ExchangeFilterFunction)` | Append a filter to the end of the chain. | Registration order matters. |
| `filters(Consumer<List<ExchangeFilterFunction>>)` | Inspect/reorder/remove the filter list. | Use intentionally; avoid duplicate additions. |
| `clientConnector(...)` | Choose and configure HTTP transport, timeouts/connections at the right layer. | Do not confuse with stream business timeouts. |
| `codecs(...)` | Configure encoders/decoders and memory limits. | Not a filter's responsibility. |

Example declaring a shared client via Spring configuration; usable with Spring Framework/Spring Boot with `spring-webflux`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.ClientRequest;
import org.springframework.web.reactive.function.client.ExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class RemoteClientConfig {

    @Bean
    WebClient inventoryClient(WebClient.Builder sharedBuilder) {
        ExchangeFilterFunction clientTag = (request, next) -> {
            ClientRequest updated = ClientRequest.from(request)
                    .headers(headers -> {
                        if (!headers.containsKey("X-Client-Tag")) {
                            headers.set("X-Client-Tag", "inventory");
                        }
                    })
                    .build();
            return next.exchange(updated);
        };

        return sharedBuilder.clone()
                .baseUrl("https://inventory.example")
                .defaultHeader(HttpHeaders.ACCEPT, MediaType.APPLICATION_JSON_VALUE)
                .filter(clientTag)
                .build();
    }
}
```

`WebClient.Builder` is injected automatically in a Spring Boot app with the corresponding feature enabled; in plain Spring Framework, declare a builder bean yourself or create one via `WebClient.builder()`. `clone()` isolates configuration changes on the builder from other places using the same builder. Do not pass a `WebClient.Builder` that can be mutated across threads for per-request dynamic configuration.

Concise call snippet reusing the configured bean:

```java
Mono<String> stockResponse = inventoryClient.get()
        .uri("/api/stocks/{sku}", "SKU-123")
        .retrieve()
        .bodyToMono(String.class);
```

This is an **illustrative snippet inside a component/service** with access to `inventoryClient`; not a standalone Java program. Running it for real requires the API, DTOs, authentication config, and error handling suited to your system.

### 4.1 Sharing Core Configuration, Splitting Clients by API

Typical organization:

```text
Shared app configuration (safe logging, observability, codecs/connector)
                  |
                  v
           WebClient.Builder
              /       \
             v         v
     inventoryClient  paymentClient
     baseUrl A         baseUrl B
     headers A         auth/filter B
```

Do not share API A's `baseUrl`, credentials, or specific filters with API B. If injecting the same mutable builder, call `clone()` before applying per-client settings. Creating a `WebClient` on every call also scatters configuration; typically create shared instances at startup or derive intentional variants.

### 4.2 Immutable WebClient and mutate()

After `build()`, `WebClient` has no API to modify the constructed configuration directly. `mutate()` creates a new builder carrying the current settings; calling `build()` creates a **new client** without altering the old one:

```java
WebClient original = WebClient.builder()
        .baseUrl("https://inventory.example")
        .filter(requestOnly)
        .build();

WebClient extended = original.mutate()
        .filter(responseOnly)
        .build();
```

In this example, `original` has `requestOnly`; `extended` has both `requestOnly` and `responseOnly`. `requestOnly` and `responseOnly` are the filters defined earlier. To move a filter to the front or remove an old filter, use `mutate().filters(list -> ...)`. Understand the order and identity of filters before editing the list; appending a filter every time a method calls `mutate()` can cause unwanted filter duplication.

## 5. Passing Per-Request Data to Filters via Attributes

`ClientRequest` has an attributes map used **internally by the filter chain**, never sent over the network like HTTP headers. A request can attach an attribute to alter filter behavior:

```java
ExchangeFilterFunction selectiveAudit = (request, next) -> {
    boolean skip = Boolean.TRUE.equals(
            request.attribute("skipAudit").orElse(false));

    if (!skip) {
        System.out.println("Audit " + request.method() + " "
                + request.url().getPath());
    }
    return next.exchange(request);
};

WebClient client = WebClient.builder()
        .filter(selectiveAudit)
        .build();

Mono<String> value = client.get()
        .uri("https://service.example/resource")
        .attribute("skipAudit", true)
        .retrieve()
        .bodyToMono(String.class);
```

In the example, `skipAudit` is only a client/filter flag, not an HTTP header. To transmit data to the server, explicitly convert it into a header, body, or query parameter per the API contract.

When per-subscriber data is needed across a reactive chain, distinguish attributes from Reactor `Context`: an attribute is attached to a single `ClientRequest`, whereas `Context` propagates along the subscription chain. Avoid relying carelessly on `ThreadLocal` in reactive processing because execution can switch threads. `defaultRequest(...)` can set default attributes, though identity/correlation lookup policies should be designed consistently.

## 6. Network-Independent Runnable Example: Verifying Filters and Headers

The snippet below has a complete `main` method; it uses a fake `ExchangeFunction` to produce responses so **no real HTTP traffic occurs**. It requires Java 17+ and Spring WebFlux + Project Reactor libraries on the classpath (e.g., a Spring Boot project declaring `org.springframework.boot:spring-boot-starter-webflux` with compatible version management).

**File `FilterDemo.java`:**

```java
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.ClientRequest;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.ExchangeFilterFunction;
import org.springframework.web.reactive.function.client.ExchangeFunction;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

public class FilterDemo {

    public static void main(String[] args) {
        ExchangeFunction fakeTransport = request -> {
            System.out.println(
                    "transport: " + request.headers().getFirst("X-Client-Id"));
            return Mono.just(ClientResponse.create(HttpStatus.OK)
                    .header(HttpHeaders.CONTENT_TYPE, MediaType.TEXT_PLAIN_VALUE)
                    .body("pong")
                    .build());
        };

        ExchangeFilterFunction audit = (request, next) -> {
            System.out.println(
                    "before: " + request.method() + " " + request.url().getPath());
            return next.exchange(request)
                    .doOnNext(response ->
                            System.out.println(
                                    "after: " + response.statusCode().value()));
        };

        WebClient client = WebClient.builder()
                .baseUrl("https://example.invalid")
                .defaultHeader("X-Client-Id", "learning-module")
                .exchangeFunction(fakeTransport)
                .filter(audit)
                .build();

        String body = client.get()
                .uri("/ping")
                .retrieve()
                .bodyToMono(String.class)
                .block(); // Only use at the synchronous boundary of the demo.

        System.out.println("body: " + body);
    }
}
```

**Expected stdout, exact for the example (excluding environment/build-tool messages):**

```text
before: GET /ping
transport: learning-module
after: 200
body: pong
```

Why:

1. When `block()` subscribes to the stream, the `audit` filter runs and prints the `before` line.
2. `next.exchange(request)` invokes `fakeTransport`. The transport receives the default header `X-Client-Id` and returns a 200 `ClientResponse` with body `pong`.
3. `doOnNext` observes the response and prints the `after` line.
4. `retrieve().bodyToMono(String.class)` decodes the body to a string, and finally `main` prints `body`.

In a Spring Boot/Gradle project, add `implementation 'org.springframework.boot:spring-boot-starter-webflux'` to dependencies if not already present; place `FilterDemo.java` in the source set and run `FilterDemo.main` from your IDE or Java launcher with the Gradle library classpath. Running `javac FilterDemo.java` alone is **not enough** because Spring/Reactor JARs are required. `block()` here is an exception for verification in `main`; inside a WebFlux server handler, return `Mono`/`Flux` instead of blocking the event loop.

### 6.1 Try Modifying to Self-Test

- Change `.filter(audit)` to `.filter(audit).filter(secondFilter)` where `secondFilter` prints `B-before` before `next.exchange` and `B-after` via `doOnNext`. Observe the order `A-before → B-before → transport → B-after → A-after`.
- Add `.header("X-Client-Id", "override")` right before `.retrieve()`. The transport will see `override` because per-request headers take precedence over `defaultHeader`.
- Remove `.block()` and do not subscribe; the exchange will not run.
- On a real client, set `attribute("skipAudit", true)` and observe the filter using the attribute to decide whether to log metadata.

## 7. Common Misconceptions and Risks

| Mistake | Consequence | How to avoid |
| --- | --- | --- |
| Confusing `ExchangeFilterFunction` with server-side `WebFilter` | Intervening on the wrong side of HTTP. | `ExchangeFilterFunction` is for **outbound** `WebClient` requests; `WebFilter` sits in the WebFlux server pipeline. |
| Calling `next.exchange(request)` twice or nesting retries arbitrarily | Can send the same request multiple times, dangerous for non-idempotent POST/PUT. | Define retries intentionally by HTTP method, error codes, limits, and idempotency; never resend unconditionally. |
| Using `doOnError` to count all HTTP 4xx/5xx | Misses statuses when `exchange` returns a normal `ClientResponse`. | Observe `response.statusCode()`; handle business statuses in `retrieve().onStatus(...)` when appropriate. |
| Reading the body in a filter and returning the same response | Downstream loses the expected body or leaks resources. | Do not consume the body just to log; if handling and discarding a response, release the body properly. |
| Printing all headers/bodies | Exposes tokens, cookies, PII, and payment details. | Log only method, path pattern, status, duration, and controlled IDs. |
| Using `ThreadLocal` to fetch tokens in reactive streams | Lost/wrong context across thread switches. | Pass data transparently via request attributes or Reactor Context, depending on the problem. |
| Calling `block()` in a filter or reactive controller | Blocks the event loop, increases latency, and can cause errors. | Compose asynchronously using `flatMap`, `Mono.defer`, or appropriate publishers. |
| Mutating a shared builder after use | Inconsistent configuration across clients. | Finish configuring before `build()`; use `clone()`/`mutate()` when creating variants. |
| Putting all business logic into filters | Hard to test and hard to separate per-endpoint errors. | Filters solve cross-cutting concerns; handle responses/DTOs/business statuses in the client service layer. |
| Treating filters as a timeout/connection pool mechanism | Fails to fix transport configuration issues. | Configure `clientConnector`, timeouts, pooling, and resource lifecycles at the proper layer. |

## 8. Organizational Recommendations in Applications

In applications with multiple HTTP clients, separate global configuration (observability, connector, safe logging policy) from per-service clients (base URL, authentication, specific headers). Extract reusable filters into functions/beans when they merit independent testing; append filters in order with `filter(...)` and inspect/control the list with `filters(...)`. Place parameters like endpoints, timeouts, and application names in appropriate environment configuration sources.

A design checklist for every filter:

1. **Does it modify the request, only observe the response, or control the exchange chain?** Choose the simplest API that does the job.
2. **Does it need per-request data?** Use headers when the server needs it, attributes when only the client/filter needs it, and Reactor Context when per-subscriber context is required.
3. **Can it consume or discard the response?** If yes, clearly define body reading/releasing and error policy.
4. **Is it safe under concurrency and multiple subscriptions?** Avoid unsynchronized shared mutable state and non-idempotent side effects.
5. **Can it be tested without real HTTP calls?** Use a fake `ExchangeFunction` as shown, or a mock HTTP server when testing serialization, real headers, and connections.

## 9. Knowledge Summary

- `WebClient.Builder` holds shared configuration; `ExchangeFilterFunction` intercepts an HTTP exchange across `ClientRequest → ExchangeFunction → ClientResponse`.
- Filters run when the publisher is subscribed to; filter order determines the nesting of request and response processing.
- `ClientRequest.from(request)` creates a new request when altering headers/attributes; `next.exchange(...)` forwards the exchange.
- `defaultHeader` supplies defaults, `defaultRequest` customizes each request, and `filter` handles cross-cutting logic; `WebClient.mutate()` creates a derived client without altering the original.
- When handling responses in a filter, always preserve or release the body properly; never log sensitive information or block reactive threads.

**Official Reference Documentation (Spring Framework):**

- [WebClient — Filters](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-filter.html)
- [WebClient — Configuration](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html)
- [WebClient — Attributes](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-attributes.html)
- [Java API — ExchangeFilterFunction](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/client/ExchangeFilterFunction.html)
