# Interceptors, Error Status Handling, and Idempotency-Driven Retry Design

## 1. Why Do Synchronous HTTP Clients Need Three Separate Mechanisms?

A Spring application calling another service over HTTP usually needs to attach shared request metadata, interpret error responses, and retry transient failures. These three concerns are related, yet **are not a single mechanism**:

1. **Interceptors**: hook before/after an HTTP call on the client to add correlation IDs, appropriate headers, observe response times, trace, or apply shared policies.
2. **Error status handling**: classify HTTP 4xx/5xx, transport errors, timeouts, and invalid bodies, translating them into meaningful business results/exceptions.
3. **Idempotency-driven retries**: repeat a request only when repetition is safe according to **HTTP method, operation semantics, request body state, server contract, attempt count, and time budget**.

The most critical insight: **a connection timeout does not prove the server failed to process the request**. The client may have sent the POST, the server may have written to the DB, and the response may have been lost. If the client retries POST automatically, it can create two orders or charge twice.

This lesson belongs to **synchronous HTTP clients**, built on **Spring Framework 6.1 / Spring Boot 3.3.5 / Java 17**. The primary API is `RestClient` (introduced in Spring Framework 6.1), alongside comparisons with `RestTemplate` for existing systems. `RestClient` is a synchronous/blocking client, **not reactive WebClient**.

### What Will You Be Able to Do?

- Distinguish `ClientHttpRequestInterceptor` from status/error handlers and retry wrappers.
- Write an interceptor that executes a request strictly once per attempt, logs safely, and avoids leaking unclosed responses.
- Understand default error behavior of `RestClient.retrieve()`, `onStatus(...)`, `defaultStatusHandler(...)`, `exchange(...)`, and `RestTemplate.ResponseErrorHandler`.
- Properly classify 400, 401, 403, 404, 409, 412, 422, 429, 500, 502, 503, 504, and network errors.
- Understand HTTP *safe*, *idempotent*, and *non-idempotent* semantics and the difference between “idempotent HTTP method” and “repeatable business operation”.
- Select which operations are eligible for retries, handling `Retry-After`, exponential backoff, jitter, max attempts, timeouts, and budgets.
- Design `Idempotency-Key` on both client **and server**, never mistaking an arbitrary header for duplicate protection.
- Build a runnable Maven project with `RestClient`/`MockRestServiceServer` verifying exact attempt counts across 4xx/5xx/timeouts.
- Recognize production concerns such as circuit breakers, retry storms, distributed tracing, PII logging, pool starvation, and concurrency.

## 2. Execution Path of a RestClient Call

A synchronous HTTP request passes through these layers:

```text
Business service
   |
   v
Retry boundary (only for eligible operations)
   |
   +--> attempt 1
   |       |
   |       v
   |     RestClient request specification
   |       |
   |       v
   |     ClientHttpRequestInterceptor chain
   |       |
   |       v
   |     ClientHttpRequestFactory -> HTTP transport
   |       |
   |       v
   |     HTTP response
   |       |
   |       v
   |     retrieve() status handler -> body conversion
   |       |
   |       +--> success value
   |       +--> typed HTTP exception
   |       +--> transport exception
   |
   +--> (if retryable and budget remains)
   |       attempt 2 -> full new RestClient execution
   |
   v
Final success / terminal failure
```

**Retries should wrap an entire attempt** rather than arbitrarily calling `execution.execute(...)` multiple times inside an interceptor. This structure lets `retrieve()`'s status handler inspect each response, while the caller decides whether the operation may be repeated.

An interceptor can observe both HTTP 404 and HTTP 503 without **converting them into exceptions itself**. Status handlers run after the transport/interception stage of `RestClient.retrieve()`. Network errors occurring before a response arrives must be kept distinct from HTTP errors that carry a status code.

### Related Abstractions

| Type | Package/Object | Responsibility |
| --- | --- | --- |
| Fluent client | `org.springframework.web.client.RestClient` | Build requests, send synchronously, receive responses |
| Legacy synchronous client | `org.springframework.web.client.RestTemplate` | Template API, still common in existing apps |
| Interceptor | `org.springframework.http.client.ClientHttpRequestInterceptor` | Intercept request/response before/after HTTP execution |
| Request factory | `ClientHttpRequestFactory` | Connections, timeouts, transport implementation |
| RestClient status handler | `retrieve().onStatus(...)` | Per-request error mapping |
| Global status handler | `RestClient.Builder.defaultStatusHandler(...)` | Default rule across requests |
| RestTemplate handler | `ResponseErrorHandler` | Detect errors and handle error responses |
| HTTP response exception | `RestClientResponseException` | Status, response headers, and error body |
| I/O exception | `ResourceAccessException` | Transport timeouts, connection, TLS, and I/O issues |
| Client mock | `MockRestServiceServer` | Test requests, headers, responses, and retry counts |

## 3. Where Do RestClient and RestTemplate Differ?

### RestClient: Spring Framework 6.1 Fluent API

```java
RestClient client = RestClient.builder()
        .baseUrl("https://catalog.example.test")
        .build();

CatalogItem item = client.get()
        .uri("/items/{id}", 42)
        .accept(MediaType.APPLICATION_JSON)
        .retrieve()
        .body(CatalogItem.class);
```

This is a snippet; `CatalogItem` is the DTO in the complete example. Calling `body(...)` executes the request synchronously, reads, and converts the response. Normally, if the upstream returns HTTP 4xx/5xx, `retrieve()` **raises a `RestClientException` by default**, usually a subclass of `RestClientResponseException`.

### RestTemplate in Existing Applications

```java
RestTemplate template = new RestTemplate();

ResponseEntity<CatalogItem> response = template.exchange(
        "https://catalog.example.test/items/{id}",
        HttpMethod.GET,
        HttpEntity.EMPTY,
        CatalogItem.class,
        42);
```

`RestTemplate` remains useful for existing code. It uses `ResponseErrorHandler` (defaulting to `DefaultResponseErrorHandler`) and supports the same `ClientHttpRequestInterceptor`. Spring provides `RestClient.builder(restTemplate)` to carry over base configuration during incremental migration.

**There is no need to rewrite all of RestTemplate just to add interceptors/retries.** API contracts, timeouts, status mappings, tests, and transactional data matter more. Likewise, do not switch from RestClient to WebClient solely to get retries; WebClient uses a different reactive pipeline and cannot magically make a non-idempotent POST safe.

## 4. What Is ClientHttpRequestInterceptor?

Core signature:

```java
@FunctionalInterface
public interface ClientHttpRequestInterceptor {
    ClientHttpResponse intercept(
            HttpRequest request,
            byte[] body,
            ClientHttpRequestExecution execution)
            throws IOException;
}
```

This presents the Spring API signature, not an interface you define yourself.

- `request` holds HTTP method, URI, and mutable headers.
- `body` is the request body bytes prepared for execution; handle carefully regarding memory and secrets.
- `execution.execute(request, body)` invokes the next interceptor or the request factory/transport.
- `ClientHttpResponse` exposes status/headers and the server response.
- An interceptor can short-circuit, provided it returns a valid response or throws an exception with clear semantics.

A typical interceptor should invoke **`execution.execute(...)` strictly once on the success path**. Re-executing inside an interceptor on 503 risks replaying POSTs, breaking body replay guarantees, and complicating error handling.

### Ordering Multiple Interceptors

`RestClient.Builder.requestInterceptor(...)` appends an interceptor to the chain; `requestInterceptors(...)` lets you manage the full list. Ordering determines:
- Is the auth header attached before or after request signing?
- Which phase does a trace span cover?
- Do logs see request headers after modifications?
- Are retries (if external) outside or inside metrics/observability?

Do not rely on class names or non-deterministic bean scan order. Specify order explicitly in config and verify headers in HTTP mock tests.

### Do Not Read/Log Entire Request Bodies

`byte[] body` can contain PII, passwords, access tokens, payment details, or uploaded files. Logging it poses a security risk. Instead log:
- Logical service name.
- HTTP method and endpoint template (not raw query parameters containing secrets).
- HTTP status/code family.
- Duration, attempt count, and safe server trace/request IDs.
- Error category (timeout/4xx/5xx), without dumping authorization headers.

Never log `Authorization`, `Cookie`, `Set-Cookie`, or raw `ResponseEntity` instances with sensitive bodies.

## 5. Interceptors Are Not the Default Place for Retries

Anti-pattern:

```java
// ANTI-PATTERN — interceptor calls upstream multiple times itself.
return execution.execute(request, body);
// ...if 503 then execution.execute(request, body) once more...
```

Besides illustrating a flawed flow, this idea has serious problems:
1. The interceptor **cannot know for sure** whether the business operation is repeatable.
2. The HTTP body may be a non-replayable stream/file upload under the current request factory.
3. An interceptor is typically shared across GET, POST, PUT, DELETE, and special requests.
4. If a response was already received and the interceptor decides to retry, it must **close the old response** properly; failing to do so leaks connections/pool resources.
5. `RestClient.retrieve()` status/error handlers have usually not run inside the interceptor.
6. Auth refreshes, idempotency keys, tracing, and metrics get tangled together.
7. Client cancellation/thread interruption can be ignored while sleeping on backoff inside an interceptor.

**Preferred design:** keep interceptors for transport decoration/observability; place the **retry boundary** at the service method or resilience policy with explicit per-operation metadata; let `RestClient.retrieve()`/`onStatus` decide error mapping.

## 6. Error Statuses: RestClient.retrieve() and RestClient.exchange()

### Default retrieve()

```java
CatalogItem item = client.get()
        .uri("/items/{id}", id)
        .retrieve()
        .body(CatalogItem.class);
```

By default, **4xx and 5xx** responses are treated as errors; code typically receives subclasses of `RestClientResponseException`, exposing:
- `getStatusCode()` (Spring `HttpStatusCode`).
- `getResponseHeaders()`.
- `getResponseBodyAsString()` or bytes.
- Additional HTTP response metadata per implementation.

Never forward raw error bodies from internal services to public clients if they contain hostnames, stack traces, or secrets.

### Per-Request onStatus

```java
CatalogItem item = client.get()
        .uri("/items/{id}", id)
        .retrieve()
        .onStatus(
                code -> code.value() == 404,
                (request, response) -> {
                    throw new CatalogNotFoundException(
                            "Catalog item unavailable");
                })
        .body(CatalogItem.class);
```

This is a snippet; `CatalogNotFoundException` is an application-defined custom exception. This request's `onStatus` handler takes over 404 handling and explicitly throws a domain exception. Avoid swallowing the error and unintentionally trying to decode a 404 body as a success DTO.

Some APIs may want 404 → `Optional.empty()` instead of an exception. Design the contract clearly; `exchange(...)` can inspect status directly and return Optional, though **`exchange` does not apply default retrieve status handlers automatically**.

### Client-Wide defaultStatusHandler

```java
RestClient restClient = RestClient.builder()
        .defaultStatusHandler(
                HttpStatusCode::is5xxServerError,
                (request, response) -> {
                    throw new IllegalStateException(
                            "Upstream server returned 5xx");
                })
        .build();
```

This is an illustrative snippet, not an ideal production choice because it **loses the status code and Retry-After** from the default exception. When retrying on 502/503/504, preserve `RestClientResponseException` or wrap it in a custom exception retaining status code, headers, and retry hints.

`defaultStatusHandler`s execute in registration order, after request-specific handlers. Never install a catch-all status handler that accidentally turns 404/409 into 500 or 429 into domain invalid input.

### exchange(...) Bypasses retrieve() Status Handlers

```java
Boolean exists = client.head()
        .uri("/items/{id}", 42)
        .exchange((request, response) ->
                response.getStatusCode().is2xxSuccessful());
```

This is a snippet; 404 returns `false` instead of throwing an exception per default `retrieve()`, because the `exchange` callback owns status handling. Use it only when you intentionally inspect statuses/headers and ensure the response is handled/closed properly. For services whose retry policy relies on `RestClientResponseException`, replacing retrieve with exchange will **alter retry conditions**.

### Status Handlers vs Transport Errors

If DNS fails to resolve, TLS handshake fails, or a socket times out **before an HTTP response arrives**, there is no HTTP 503 status for `onStatus` to handle. These errors travel through `ResourceAccessException` or other client I/O errors. Classify them separately and preserve internal causes/traces.

## 7. Error Code Classification Table for Retry Design

| Code | Typical Meaning | Auto-Retry? |
| --- | --- | --- |
| 200/201/204 | Success | No |
| 301/302/307/308 | Redirect | Not an error to simply retry; check redirects/credentials/method |
| 400 | Malformed request/validation failure | No; fix input |
| 401 | Unauthenticated/expired token | Do not retry infinitely; may refresh credentials at most once per policy |
| 403 | Forbidden | No; fix authz/ACL |
| 404 | Resource not found | Usually no; eventual consistency only if contract permits and bounded |
| 408 | Request Timeout | May retry **if operation is safe** and context permits |
| 409 | Conflict | Not by default; check version/concurrency |
| 412 | Precondition Failed | No; refresh ETag/state |
| 422 | Unprocessable Content | No; fix data |
| 425 | Too Early | Client may retry in some cases without early data; requires TLS/protocol policy |
| 429 | Too Many Requests | May honor Retry-After/quota, only if operation is replay-safe |
| 500 | Internal Server Error | Not by default; depends on API/incident semantics |
| 502 | Bad Gateway | Possibly transient; controlled retry |
| 503 | Service Unavailable | Often transient; honor Retry-After |
| 504 | Gateway Timeout | Possibly transient, **server may already have applied side effects** |
| Transport timeout/reset | No reliable response | Retry only if business operation is replay-safe |
| TLS certificate error | Misconfigured security | Do not retry in a loop; fix configuration |

This table is a **starting point**, not an immutable law. A `GET /export/start` that spawns a job or incurs charges violates safe semantics despite using GET; a `POST /payments` with a valid idempotency key may be retried safely if the server enforces atomic deduplication.

**Never write `if (status >= 500) retry` for every method.** A 500 may be a business/configuration bug that will not improve across attempts; moreover, 504 does not prove the operation never ran.

## 8. Safe, Idempotent, and Replayable Are Different

Per RFC 9110:

- **Safe methods**: semantically, the client requests no state change on the server. GET, HEAD, OPTIONS, and TRACE are defined as safe, even though servers may still log or count metrics.
- **Idempotent methods**: multiple identical requests have the same intended effect on the server as a single request. Safe methods plus **PUT** and **DELETE** are idempotent by HTTP semantics.
- **Not idempotent by default**: POST and PATCH (unless the server explicitly designs custom idempotency semantics).

### GET Example

`GET /catalog/items/42` only reads an item. If a socket resets after sending the request, calling again normally creates no new data. Even so:
- The API server must honor those semantics.
- The request might contain a one-time token or counter that should not repeat.
- Retries still consume quota and can push a struggling server deeper into overload.

### PUT Example

`PUT /users/42` with a resource representation and matching ETag/precondition can be treated as idempotent in intended effect. However:
- If the request uses `If-Match`, retrying after the first attempt succeeded can return **412** because the version changed. That does not mean the final state failed; business/ETag logic is needed to interpret it.
- The upload body must be replayable.
- A server implementing “PUT increments billable access count” violates expected semantics; never trust the HTTP method name over the actual contract.

### DELETE Example

`DELETE /resources/42` twice usually has the desired effect “resource no longer exists”. The second call might return 404 after the first succeeded: **idempotency does not mean identical responses**. If the backend triggers non-idempotent side effects on DELETE, fix the contract or disable retries.

### Payment POST Example

`POST /payments` creates a charge. If the client times out right after sending, the request **may already have been recorded**; retrying can double-charge. Do not auto-retry solely because of 503/timeout. A server-supported Idempotency-Key with stored deduplication results can enable safe retries, but requires system guarantees rather than just adding a header.

### Three Conditions Required Before Retrying

1. **Semantically safe/idempotent or protected by server-side deduplication**.
2. **Replayable request** (body is not a one-shot stream and credentials/headers remain valid).
3. **Retry budget** with max attempts, deadline, backoff, and classification of genuinely transient errors.

If any condition is missing, **do not auto-retry**.

## 9. Why Is “Sent but No Response Received” Dangerous?

Picture this:

```text
Client                Network                 Payment service
  | POST /payments       |                           |
  |--------------------->|-------------------------->|
  |                      |                      Record charge
  |                      |<--------------------------|
  |    timeout / reset   X                           |
  |                      |                           |
  | Client does not know whether operation committed |
  |                      |                           |
  | POST /payments again |                           |
  |--------------------->|-------------------------->|
  |                      |                       2nd charge?
```

**At-least-once attempts** do not guarantee **exactly-once business effects**. To prevent duplicates:
- The client generates one stable idempotency key for **one logical business operation**.
- The server stores the key, request fingerprint, in-progress/result state, and returns the stored outcome per policy.
- Persisting the key must be atomic with the side-effect transaction (or backed by a strong consistency strategy).
- Define TTL, concurrency conflict rules, and tenant/user scoping.
- The client sends the **exact same key** when retrying the **same operation**, never generating a fresh key per attempt.
- If the same key arrives with a different payload, the server should report a conflict per contract.
- Do not rely solely on a reverse proxy or simple Redis cache where the side effect can commit while recording deduplication fails.

### The Key Holds No Magic by Itself

`Idempotency-Key: abc123` is just a header. If the server does not implement storage and verification, resending POST still creates a second charge. If the server writes the key only after the DB transaction commits and crashes in between, a race condition exists. Idempotency must be designed across storage, transactions, and brokers.

Never reuse a key for different operations. Never put sensitive keys in URLs. Enforce TTL, entropy, and scoping; prevent clients from guessing another user's key to retrieve cached responses.

## 10. Retry-After: How Long Does the Server Ask You to Wait?

`Retry-After` has two standard HTTP formats:

1. **delta-seconds**: `Retry-After: 5` — wait at least 5 seconds.
2. **HTTP-date**: `Retry-After: Wed, 21 Oct 2026 15:00:00 GMT` — timestamp when retrying is allowed.

The HTTP-date format is sensitive to client/server clock skew; the parser must support valid RFC 1123/HTTP-date formats and clamp negative durations to 0 when the timestamp is in the past.

A server may send 429 or 503 with `Retry-After`. If the requested wait **exceeds the client's remaining budget**, the sensible choice is **not to retry within that call**, surfacing the failure to the caller/circuit breaker or scheduling the job externally; **never** silently shorten `Retry-After` and hammer the server.

`Retry-After` is not a guarantee that the next request will succeed after waiting. Auth, idempotency, deadlines, and server quotas still govern the final outcome.

### When Retry-After Is Absent

Use **exponential backoff + jitter**. With a 100 ms base and 2 s cap, attempts wait for increasing yet randomized intervals (full jitter) so thousands of clients do not hammer the server in lockstep.

Do not call `Thread.sleep(100)` inside an unbounded loop. A synchronous request holds a thread during sleep; under server load, this strategy needs tight bounds or offloading to a queue/async processor.

## 11. Retry Budgets and the Risk of Retry Storms

A service call can pass through multiple retry layers:

```text
Browser retries 2x
   |
   v
API gateway retries 3x
   |
   v
Application retries 3x
   |
   v
Load balancer retries 2x
   |
   v
Downstream dependency
```

In the worst case, a single logical action can generate **2 × 3 × 3 × 2 = 36 attempts** at the downstream. When a downstream is overloaded, retries worsen the outage. Therefore:
- Place **retries in one clear owning layer** whenever possible.
- Cap **max attempts**, including the initial attempt.
- Cap the **per-call deadline** (connect + read + sleeps + attempts).
- Cap **process-wide retry concurrency/budget**, not just per request.
- Respect 429/503 Retry-After and health signals.
- Use circuit breakers, bulkheads, and rate limits where appropriate.
- Emit telemetry separating logical requests from raw attempts.

**Never promise total timeout = readTimeout**: readTimeout typically applies to a single network I/O phase, not necessarily DNS, queue waits, multiple attempts, and sleeps. End-to-end deadlines must be measured and bounded separately.

## 12. Three-Layer Design in Spring

Clean, testable architecture:

```text
OrderFacade / business operation
   |
   +--> CatalogGateway.get(id) -- calls RetryExecutor for GET
   |                                 |
   |                                 +--> RestClient.get().retrieve()
   |
   +--> PaymentGateway.create(...) -- does not auto-retry POST
                                     |
                                     +--> RestClient.post().retrieve()

RestClient configuration
   +--> baseUrl
   +--> connect/read timeouts
   +--> ClientHttpRequestInterceptor (safe trace/log)
   +--> request factory
   +--> codecs / Jackson
   +--> per-operation status handling
```

**Separation of responsibilities:**
- Interceptor: per-attempt tracing, trusted config headers, safe metrics/diagnostics.
- Gateway method: knows URL, DTOs, domain statuses, and operation semantics.
- RetryExecutor: knows retryable errors, method whitelist, budgets, backoff, and Retry-After.
- Business service: decides how to handle missing resources, conflicts, authorization, or idempotency keys.
- Downstream server: actually enforces deduplication/transactions when unsafe method retries are permitted.

Do not hardcode operation/payment checks inside a retry utility via `if (path.startsWith("/payments"))`; passing an explicit policy is far safer than string-matching paths.

## 13. Complete Maven Project — Java 17, Spring Boot 3.3.5

The demo uses `RestClient` to call a hypothetical catalog upstream. Runtime features:
- `SimpleClientHttpRequestFactory` with explicit connect/read timeouts.
- `ClientHttpRequestInterceptor` attaching `X-Client-Attempt-Id` per attempt and logging method/status/duration.
- `RetryExecutor` allowing only `GET`/`HEAD`; transport errors and 408/429/502/503/504 are eligible.
- Bounded randomized backoff and `Retry-After` support for delta-seconds/HTTP-date; stops retrying if the server asks to wait longer than the budget.
- `CatalogGateway` with policy-safe `get` and **non-retried** `create` POST.
- Unit/integration-style client tests using `MockRestServiceServer` with no live Internet calls.

**Deliberate demo scope limits:** No server-side transaction/idempotency-key store or distributed retry budget. `ResourceAccessException` is treated as potentially transient in the demo **for GET/HEAD only**; production should filter out non-retryable TLS certificate/DNS configuration failures. Overall deadlines, bulkheads/circuit breakers, and metrics should be added per workload.

### 13.1. Project Structure

```text
sync-http-retry-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/example/syncclient/
    │   │   ├── SyncClientApplication.java
    │   │   ├── HttpClientConfig.java
    │   │   ├── CatalogItem.java
    │   │   ├── CatalogDraft.java
    │   │   ├── RetryExecutor.java
    │   │   └── CatalogGateway.java
    │   └── resources/application.properties
    └── test/java/example/syncclient/
        └── CatalogGatewayTest.java
```

### 13.2. Maven pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>sync-http-retry-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Spring Boot Web starter brings Spring Web, Jackson, and logging. `spring-boot-starter-test` provides JUnit 5, `MockRestServiceServer`, and Spring MVC test utilities. **No WebFlux starter is needed** to use RestClient.

### 13.3. Application Class

**`src/main/java/example/syncclient/SyncClientApplication.java`**

```java
package example.syncclient;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SyncClientApplication {

    public static void main(String[] args) {
        SpringApplication.run(SyncClientApplication.class, args);
    }
}
```

This is a complete Spring Boot app. No `CommandLineRunner` is defined to call the mock catalog automatically: starting the server does not require Internet access. Client code is invoked from services or tests as needed.

### 13.4. URL Configuration

**`src/main/resources/application.properties`**

```properties
catalog.base-url=https://catalog.example.test
```

The `example.test` domain is a valid demo placeholder, **not a live catalog service**. Tests use MockRestServiceServer so they run offline. In production, supply an environment-specific trusted base URL via application config/secrets management; never accept hosts from user requests to prevent SSRF.

### 13.5. Configuring RestClient and Interceptor

**`src/main/java/example/syncclient/HttpClientConfig.java`**

```java
package example.syncclient;

import java.io.IOException;
import java.util.UUID;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.http.client.ClientHttpRequestInterceptor;
import org.springframework.http.client.ClientHttpResponse;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration
public class HttpClientConfig {

    private static final Logger log =
            LoggerFactory.getLogger(HttpClientConfig.class);

    @Bean
    RestClient catalogRestClient(
            RestClient.Builder builder,
            Environment environment) {

        SimpleClientHttpRequestFactory factory =
                new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(2_000);
        factory.setReadTimeout(3_000);

        ClientHttpRequestInterceptor interceptor =
                (request, body, execution) -> {
                    // Each attempt gets its own ID.
                    request.getHeaders().set(
                            "X-Client-Attempt-Id",
                            UUID.randomUUID().toString());

                    long start = System.nanoTime();
                    try {
                        ClientHttpResponse response =
                                execution.execute(request, body);

                        long elapsedMs =
                                (System.nanoTime() - start)
                                        / 1_000_000;

                        log.info(
                                "catalog method={} status={} durationMs={}",
                                request.getMethod(),
                                response.getStatusCode().value(),
                                elapsedMs);

                        return response;
                    } catch (IOException error) {
                        log.warn(
                                "catalog method={} transportError={}",
                                request.getMethod(),
                                error.getClass().getSimpleName());
                        throw error;
                    }
                };

        String baseUrl = environment.getProperty(
                "catalog.base-url",
                "https://catalog.example.test");

        return builder.baseUrl(baseUrl)
                .requestFactory(factory)
                .requestInterceptor(interceptor)
                .build();
    }
}
```

**Why is this interceptor safer than common “logging interceptors”?**

- Each attempt invokes `execution.execute(request, body)` **once**.
- `X-Client-Attempt-Id` changes per attempt for inspecting network logs; **it is not an Idempotency-Key**.
- Does not log bodies, URL queries, or authentication headers.
- Logs low-sensitivity metadata: method, status, and duration.
- The interceptor does not retry itself. When the retry boundary issues a fresh request, the interceptor runs again and assigns a new attempt ID.
- `ClientHttpResponse` is returned to RestClient for normal handling/closing. If an interceptor **already received a response and then throws**, it must close the response before throwing per API contract; this snippet does not throw after receiving a response.
- Configuring timeouts on the request factory keeps synchronous requests from waiting indefinitely in basic phases.

**Limitations:** `SimpleClientHttpRequestFactory` is backed by JDK URLConnection; production apps may pick Apache HttpClient/JDK HttpClient request factories with appropriate connection pooling, TLS, and proxy settings. Connect/read timeouts **are not an overall deadline**. If Boot customizers register other RestClient interceptors, check ordering/headers and avoid accidentally disabling instrumentation.

### 13.6. DTO Records

**`src/main/java/example/syncclient/CatalogItem.java`**

```java
package example.syncclient;

public record CatalogItem(long id, String name) {}
```

**`src/main/java/example/syncclient/CatalogDraft.java`**

```java
package example.syncclient;

public record CatalogDraft(String name) {}
```

Jackson in Spring Boot handles Java records as DTOs. `CatalogDraft` omits a validation framework in the demo to keep focus on the HTTP client; production apps should validate inputs before calling upstream and handle response schemas/versions.

### 13.7. RetryExecutor: GET/HEAD Whitelist, Max 3 Attempts

**`src/main/java/example/syncclient/RetryExecutor.java`**

```java
package example.syncclient;

import java.time.Duration;
import java.time.Instant;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.util.concurrent.ThreadLocalRandom;
import java.util.function.Supplier;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;

public final class RetryExecutor {

    @FunctionalInterface
    public interface Sleeper {
        void sleep(Duration delay) throws InterruptedException;
    }

    private static final Duration MAX_DELAY =
            Duration.ofSeconds(2);

    private final int maxAttempts;
    private final Sleeper sleeper;

    public RetryExecutor(int maxAttempts, Sleeper sleeper) {
        if (maxAttempts < 1) {
            throw new IllegalArgumentException(
                    "maxAttempts must be positive");
        }
        this.maxAttempts = maxAttempts;
        this.sleeper = sleeper;
    }

    public <T> T execute(
            HttpMethod method,
            Supplier<T> action) {

        // Demo auto-retries only the two safe read methods.
        // PUT/DELETE may be idempotent per HTTP, yet require
        // verifying replayable body and upstream contract separately.
        if (method != HttpMethod.GET &&
                method != HttpMethod.HEAD) {
            return action.get();
        }

        for (int attempt = 1; ; attempt++) {
            try {
                return action.get();
            } catch (RestClientException error) {
                if (attempt >= maxAttempts
                        || !isRetryable(error)) {
                    throw error;
                }

                Duration wait = delayFor(attempt, error);

                // Retry-After too long -> give up,
                // DO NOT retry earlier than the server requested.
                if (wait.compareTo(MAX_DELAY) > 0) {
                    throw error;
                }

                try {
                    sleeper.sleep(wait);
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException(
                            "Retry interrupted", interrupted);
                }
            }
        }
    }

    private boolean isRetryable(RestClientException error) {
        if (error instanceof ResourceAccessException) {
            // Only for read-only GET/HEAD; production needs
            // filtering out DNS/certificate/configuration failures.
            return true;
        }

        if (error instanceof RestClientResponseException http) {
            int code = http.getStatusCode().value();
            return code == 408 || code == 429
                    || code == 502 || code == 503
                    || code == 504;
        }

        return false;
    }

    private Duration delayFor(
            int attempt,
            RestClientException error) {

        Duration requested = retryAfter(error);
        if (requested != null) {
            return requested;
        }

        // Full jitter, exponential growth, small cap.
        int shift = Math.min(attempt - 1, 3);
        long upperMs = Math.min(400L, 50L << shift);
        long chosenMs = ThreadLocalRandom.current()
                .nextLong(upperMs + 1);
        return Duration.ofMillis(chosenMs);
    }

    private Duration retryAfter(RestClientException error) {
        if (!(error instanceof RestClientResponseException http)) {
            return null;
        }

        HttpHeaders headers = http.getResponseHeaders();
        if (headers == null) {
            return null;
        }

        String raw = headers.getFirst(HttpHeaders.RETRY_AFTER);
        if (raw == null || raw.isBlank()) {
            return null;
        }

        String value = raw.trim();
        try {
            long seconds = Long.parseLong(value);
            if (seconds < 0) {
                return null;
            }
            return Duration.ofSeconds(seconds);
        } catch (NumberFormatException ignored) {
            // HTTP-date instead of delta-seconds.
        }

        try {
            Instant when = ZonedDateTime.parse(
                    value, DateTimeFormatter.RFC_1123_DATE_TIME)
                    .toInstant();
            Duration remaining = Duration.between(
                    Instant.now(), when);
            return remaining.isNegative()
                    ? Duration.ZERO
                    : remaining;
        } catch (DateTimeParseException ignored) {
            return null;
        }
    }
}
```

### Explaining RetryExecutor's Policy

1. Only `GET`/`HEAD` are considered for automatic retries. **PUT/DELETE**, despite being HTTP-idempotent, are disabled in the demo because replayable request bodies and per-operation contracts must be verified.
2. `maxAttempts = 3` means **at most 3 HTTP attempts including the initial attempt**, not 1 + 3 retries.
3. `ResourceAccessException` is treated as a transient candidate only for safe methods; this is still too broad for production if TLS certificate or DNS misconfigurations exist.
4. For HTTP statuses, only 408, 429, 502, 503, and 504 are retried; 400/401/403/404/409/412/422/500 are not retried by default.
5. `Retry-After` in seconds or RFC 1123 date takes precedence. If the requested wait exceeds the **2-second per-backoff budget**, the code **stops** instead of retrying prematurely.
6. When `Retry-After` is absent, small exponential backoff with full jitter is used. Exact delays vary per run; tests do not assert an exact delay value.
7. Thread interruption restores the interrupt flag; never swallow interruption and keep issuing HTTP calls.
8. The retry wrapper sits outside RestClient: each attempt goes through interceptors, transport, and status handlers as a fresh request.
9. **There is no absolute total deadline** in the demo code; production should enforce a total budget accounting for attempt durations. With a 3-second read timeout per attempt, total elapsed time can exceed several seconds.
10. `Thread.sleep` in the Sleeper implementation is **intentionally blocking** because this lesson covers synchronous clients; never run this utility on a Reactor Netty event loop or an under-provisioned task executor.

### A Note on HTTP-Date and Clock Skew

`Instant.now()` reads the client machine's clock. If clocks drift, HTTP-date calculations can produce inaccurate durations. Production can inject a `Clock` and consider the HTTP `Date` header/clock skew, but should never treat a far-future server-supplied date as a reason to sleep a thread for hours. With small budgets, fail fast.

### When to Expand the Policy?

When an upstream confirms PUT/DELETE are replay-safe and the body can be reconstructed, pass an **operation-level policy** instead of editing an app-wide whitelist. For POST protected by Idempotency-Key, enable the policy specifically on that method with atomic server deduplication; never turn on retries for all POSTs just because one endpoint supports keys.

### 13.8. Registering RetryExecutor with Spring

Add the Bean to **`HttpClientConfig.java`** from section 13.5, before the closing class brace:

```java
@Bean
RetryExecutor catalogRetryExecutor() {
    return new RetryExecutor(
            3,
            delay -> Thread.sleep(delay.toMillis()));
}
```

This is an **addition placed inside `HttpClientConfig`**, not a standalone source file. The config class already imports `Bean`. Because `RetryExecutor` and the config share the same package, no import is needed. In production, load max attempts/backoff from validated properties rather than hardcoding.

### 13.9. CatalogGateway: Retry GET, Do Not Retry POST

**`src/main/java/example/syncclient/CatalogGateway.java`**

```java
package example.syncclient;

import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class CatalogGateway {

    private final RestClient client;
    private final RetryExecutor retry;

    public CatalogGateway(
            RestClient catalogRestClient,
            RetryExecutor catalogRetryExecutor) {
        this.client = catalogRestClient;
        this.retry = catalogRetryExecutor;
    }

    public CatalogItem get(long id) {
        if (id <= 0) {
            throw new IllegalArgumentException(
                    "id must be positive");
        }

        return retry.execute(HttpMethod.GET, () -> {
            CatalogItem item = client.get()
                    .uri("/items/{id}", id)
                    .accept(MediaType.APPLICATION_JSON)
                    .retrieve()
                    .body(CatalogItem.class);

            if (item == null) {
                throw new IllegalStateException(
                        "Empty catalog response");
            }
            return item;
        });
    }

    public void create(CatalogDraft draft) {
        if (draft == null || draft.name() == null
                || draft.name().isBlank()) {
            throw new IllegalArgumentException(
                    "name required");
        }

        // POST intentionally performs only ONE attempt.
        // Retry only when server has an Idempotency-Key
        // contract and client preserves the same key.
        client.post()
                .uri("/items")
                .contentType(MediaType.APPLICATION_JSON)
                .body(draft)
                .retrieve()
                .toBodilessEntity();
    }
}
```

**Why not catch 404 and retry?** HTTP 404 is usually the final outcome for a nonexistent resource. Callers can map it to a domain “catalog item not found” error without retrying. If `get` receives 503 and policy permits, RetryExecutor runs up to 3 attempts automatically.

**Why does POST not retry even on 503?** The upstream may have already created the item while a reverse proxy returned 503 or the response was lost. Only when the catalog API has a genuine idempotency/dedup contract should you consider enabling retries with a stable key.

### Steps to Use the Demo Code

- `mvn test`: runs tests against the mock upstream, requiring no network connection to the placeholder domain.
- `mvn spring-boot:run`: starts the app normally; the RestClient Bean points to the demo catalog URL only **when code invokes CatalogGateway**. The `example.test` domain does not serve a real API.
- When integrating a real catalog service, configure `catalog.base-url` to the trusted endpoint and invoke `CatalogGateway` from business services; never take arbitrary hosts from clients.

## 14. MockRestServiceServer: Verifying Exact Attempt Counts

`MockRestServiceServer` simulates downstream HTTP responses **without opening real sockets**. It lets you assert:
- Method, URI, and headers sent by RestClient.
- Status code returned on each attempt.
- Exactly 1 or 3 requests were issued.
- Response DTO decoding.
- Whether a long Retry-After halts retries.
- Whether POST and ineligible HTTP errors avoid retries.

### 14.1. Complete Test File

**`src/test/java/example/syncclient/CatalogGatewayTest.java`**

```java
package example.syncclient;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.HttpServerErrorException;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

class CatalogGatewayTest {

    private MockRestServiceServer server;
    private CatalogGateway gateway;
    private RetryExecutor retries;

    @BeforeEach
    void prepare() {
        RestClient.Builder builder = RestClient.builder()
                .baseUrl("https://catalog.example.test")
                .requestInterceptor((request, body, execution) -> {
                    request.getHeaders().set(
                            "X-Client-Attempt-Id", "from-test");
                    return execution.execute(request, body);
                });

        server = MockRestServiceServer.bindTo(builder).build();

        // Do not actually sleep in unit tests.
        retries = new RetryExecutor(
                3,
                duration -> { });

        gateway = new CatalogGateway(builder.build(), retries);
    }

    @Test
    void get200ReturnsDecodedDtoAndInterceptorHeader() {
        server.expect(requestTo(
                    "https://catalog.example.test/items/7"))
                .andExpect(method(HttpMethod.GET))
                .andExpect(header(
                        "X-Client-Attempt-Id", "from-test"))
                .andRespond(withSuccess(
                        "{\"id\":7,\"name\":\"Pen\"}",
                        MediaType.APPLICATION_JSON));

        assertEquals(new CatalogItem(7, "Pen"),
                gateway.get(7));
        server.verify();
    }

    @Test
    void get503Then200RetriesExactlyOnce() {
        server.expect(requestTo(
                    "https://catalog.example.test/items/8"))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withStatus(
                        HttpStatus.SERVICE_UNAVAILABLE));

        server.expect(requestTo(
                    "https://catalog.example.test/items/8"))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withSuccess(
                        "{\"id\":8,\"name\":\"Notebook\"}",
                        MediaType.APPLICATION_JSON));

        assertEquals("Notebook", gateway.get(8).name());
        server.verify();
    }

    @Test
    void get429Then200CanRetry() {
        server.expect(requestTo(
                    "https://catalog.example.test/items/9"))
                .andRespond(withStatus(
                        HttpStatus.TOO_MANY_REQUESTS)
                        .header("Retry-After", "0"));

        server.expect(requestTo(
                    "https://catalog.example.test/items/9"))
                .andRespond(withSuccess(
                        "{\"id\":9,\"name\":\"Ruler\"}",
                        MediaType.APPLICATION_JSON));

        assertEquals("Ruler", gateway.get(9).name());
        server.verify();
    }

    @Test
    void get404DoesNotRetry() {
        server.expect(requestTo(
                    "https://catalog.example.test/items/11"))
                .andRespond(withStatus(HttpStatus.NOT_FOUND));

        assertThrows(HttpClientErrorException.class,
                () -> gateway.get(11));
        server.verify();
    }

    @Test
    void get400DoesNotRetry() {
        server.expect(requestTo(
                    "https://catalog.example.test/items/12"))
                .andRespond(withStatus(HttpStatus.BAD_REQUEST));

        assertThrows(HttpClientErrorException.class,
                () -> gateway.get(12));
        server.verify();
    }

    @Test
    void get500DoesNotRetryByThisPolicy() {
        server.expect(requestTo(
                    "https://catalog.example.test/items/13"))
                .andRespond(withStatus(
                        HttpStatus.INTERNAL_SERVER_ERROR));

        assertThrows(HttpServerErrorException.class,
                () -> gateway.get(13));
        server.verify();
    }

    @Test
    void get502ExhaustsThreeAttempts() {
        for (int n = 0; n < 3; n++) {
            server.expect(requestTo(
                        "https://catalog.example.test/items/14"))
                    .andExpect(method(HttpMethod.GET))
                    .andRespond(withStatus(
                            HttpStatus.BAD_GATEWAY));
        }

        assertThrows(HttpServerErrorException.class,
                () -> gateway.get(14));
        server.verify();
    }

    @Test
    void tooLongRetryAfterSkipsFurtherAttempts() {
        server.expect(requestTo(
                    "https://catalog.example.test/items/15"))
                .andRespond(withStatus(
                        HttpStatus.TOO_MANY_REQUESTS)
                        .header("Retry-After", "30"));

        assertThrows(HttpClientErrorException.class,
                () -> gateway.get(15));
        server.verify();
    }

    @Test
    void post503MustNotBeRetried() {
        server.expect(requestTo(
                    "https://catalog.example.test/items"))
                .andExpect(method(HttpMethod.POST))
                .andRespond(withStatus(
                        HttpStatus.SERVICE_UNAVAILABLE));

        assertThrows(HttpServerErrorException.class,
                () -> gateway.create(
                        new CatalogDraft("Keyboard")));
        server.verify();
    }

    @Test
    void retryExecutorWillNotRetryPostEvenForIoError() {
        AtomicInteger calls = new AtomicInteger();

        assertThrows(ResourceAccessException.class,
                () -> retries.execute(HttpMethod.POST, () -> {
                    calls.incrementAndGet();
                    throw new ResourceAccessException(
                            "simulated socket reset");
                }));

        assertEquals(1, calls.get());
    }

    @Test
    void retryExecutorCanRetryIoErrorForGet() {
        AtomicInteger calls = new AtomicInteger();

        String value = retries.execute(HttpMethod.GET, () -> {
            int n = calls.incrementAndGet();
            if (n == 1) {
                throw new ResourceAccessException(
                        "simulated transient I/O error");
            }
            return "ok";
        });

        assertEquals("ok", value);
        assertEquals(2, calls.get());
    }
}
```

**11 test methods**, with no actual sleeping thanks to the no-op injected `Sleeper`. Each `server.expect(...)` registers an expectation for **one** request; `server.verify()` asserts all expectations were executed. If RetryExecutor wrongly retries 404, 400, 500, or POST, the test fails on unexpected requests.

### Reading the Assertions Carefully

- 503→200 and 429→200 tests: confirm transient responses and successful retry.
- 502 exhausted test: exactly three HTTP attempts matching max attempts.
- 404/400/500 tests: fail immediately, issuing no second request.
- Retry-After 30 seconds test: since the per-backoff budget is only 2 seconds, the code **does not retry**; it does not wait 2 seconds and violate the 30-second hint.
- POST 503 test: the client **sends only one POST** because there is no server idempotency contract.
- GET transport exception test: policy illustrates retrying read-only calls.
- POST transport exception test: even with no HTTP status, the unsafe operation is not repeated.
- Header test: proves the interceptor ran and added request metadata without sleeping or hitting the Internet.

### Runtime QA Note

The code was written to match Java 17, Spring Boot 3.3.5, Spring Framework 6.1, and `MockRestServiceServer.bindTo(RestClient.Builder)` APIs. Within the scope of authoring Knowledge on Google Sheets, **no Maven run was performed on a workspace**; implementers must run `mvn test` with an installed toolchain. Do not treat expected assertion descriptions as executed test results.

### Additional Tests Needed for Production

- HTTP-date Retry-After with an injected Clock and clock skew.
- Read timeouts occurring after the server received the request.
- TLS certificate errors and DNS configuration failures marked non-retryable.
- Redirect policies, preserving Authorization, and preventing cross-host redirects.
- Body replayability when retrying PUT/POST; streaming uploads.
- Real connect/read timeouts against a local test server, not only MockRestServiceServer.
- Total retry budget when a single attempt hangs for 3 seconds plus multiple sleeps.
- Pool exhaustion and bulkhead behavior under concurrent load.
- End-to-end Idempotency-Key with atomic server dedup and parallel duplicate submits.
- Partial success / business 409/412 behavior.
- Observability: logical request vs attempt spans and PII masking.
- Proxies, mTLS, rate limits, circuit breakers, and client cancellation/interruption.

## 15. Example: Mapping 404 to Optional Instead of an Exception

If the application contract treats a missing catalog item as an expected outcome, you can use `exchange`:

```java
Optional<Boolean> result = client.head()
        .uri("/items/{id}", id)
        .exchange((request, response) -> {
            int status = response.getStatusCode().value();
            if (status == 404) {
                return Optional.empty();
            }
            if (status >= 200 && status < 300) {
                return Optional.of(Boolean.TRUE);
            }
            throw new IllegalStateException(
                    "Unexpected upstream status " + status);
        });
```

This is a snippet assuming existing `client`/`id` and `Optional` import. It demonstrates how **not to use default retrieve() exceptions** when you want direct status control. Avoid `if (status >= 400) return Optional.empty()` because that disguises 429/503 as “resource does not exist”.

**Important:** this snippet has no retries. To retry after `exchange`, convert 429/502/503/504 into a typed error or custom result carrying retry metadata that RetryExecutor understands. Any change to error mapping affects retry policies.

With `RestClient.retrieve()`, if 404 is expected, `onStatus` can throw a dedicated domain exception handled by the caller. That is a choice of API semantics; no single pattern fits all clients.

## 16. RestTemplate: Interceptors and ResponseErrorHandler

In a `RestTemplate` codebase:

```java
RestTemplate restTemplate = new RestTemplate();

restTemplate.setInterceptors(
        List.of((request, body, execution) -> {
            request.getHeaders().set(
                    "X-Caller-Service", "inventory");
            return execution.execute(request, body);
        }));

restTemplate.setErrorHandler(
        new DefaultResponseErrorHandler());
```

This snippet needs `List`, `RestTemplate`, and `DefaultResponseErrorHandler` imports. The default handler is already present by default; `setErrorHandler` is shown here to highlight the configuration point. It handles 4xx/5xx per template semantics; custom implementations can alter classification.

To migrate to RestClient while retaining base configuration from the template:

```java
RestClient client = RestClient.builder(restTemplate)
        .build();
```

This is a supported API that copies several RestTemplate configurations into the builder (request factory, converters, interceptors, URI settings, error handler). After migrating, test interceptor ordering, status exceptions, client metrics, and retry counts; never assume identical behavior for every custom RestTemplate extension.

### Custom ResponseErrorHandler

`ResponseErrorHandler` has `hasError(ClientHttpResponse)` and `handleError(...)`. Distinguish clearly:
- A custom handler only changes status-to-error mapping.
- It does not know which operations are idempotent.
- It does not provide retries/backoff.
- If the handler simply swallows 503, the caller may try to parse a 503 error body as a success DTO.

Keep retry policies in the operation/service layer, never buried inside `handleError`.

## 17. Timeouts: Connect, Response/Read, and Whole-Call

A synchronous HTTP call occupies a thread while:
- Waiting for connection/DNS/TLS.
- Waiting for the server response.
- Reading body bytes.
- Sleeping on backoff before sending another attempt.

`SimpleClientHttpRequestFactory.setConnectTimeout(2_000)` and `setReadTimeout(3_000)` set some low-level transport bounds. However:
- DNS resolution can behave differently.
- A response stream trickling data slowly can keep the total request alive longer than read timeout on each wait.
- TLS handshake/proxy timeouts may require client-implementation-specific configuration.
- Connection pool waits are not always covered by connect timeout.
- Three attempts can take roughly three times the timeout plus backoffs.

**Per-request timeout differs from end-to-end deadline.** If an upstream HTTP handler has a 2-second deadline while a retry wrapper can hold the thread up to 10 seconds, server requests will breach their budget. Production requires total caller deadlines, client-specific cancel/timeout policies, and resource pools.

### Never Sleep Very Long on a Synchronous API Thread

If the server sends `Retry-After: 120`, there are two options:
1. Surface the failure/metadata to a higher layer without retrying inline.
2. Reschedule the work via a durable queue/job scheduler if the task allows it.

Never block a Tomcat request thread sleeping 120 seconds just to retry a GET. If the caller is genuinely a low-concurrency batch worker, policy may differ, though bounds are still required.

## 18. Exponential Backoff, Jitter, and Variables

Common backoff formula:

\[
B_n = \min(B_{\max}, B_0 \cdot 2^{n-1})
\]

With full jitter:

\[
W_n \sim U(0,B_n)
\]

Where:
- `n` is the attempt number that just failed (first attempt n=1).
- `B0` is the base delay.
- `Bmax` is the cap.
- `Wn` is chosen randomly between 0 and Bn.

Example with 100ms base / 1,000ms cap:

| Failure After Attempt | Unjittered Upper Bound | One Valid Delay |
| --- | --- | --- |
| 1 | 100 ms | 74 ms |
| 2 | 200 ms | 11 ms |
| 3 | 400 ms | 205 ms |
| 4 | 800 ms | 690 ms |
| 5 | 1000 ms | 447 ms |

The delays on the right are **examples only**, not fixed output when running code. Jitter spreads out requests from many clients, avoiding synchronized “thundering herds”. **Never** use random jitter to ignore a larger `Retry-After`.

### Count-Based and Time-Based Retry Budgets

`maxAttempts=3` bounds attempt counts, which is not enough. If each attempt takes 10 seconds and sleeps 2 seconds, one logical request can tie up a thread for >30 seconds. You need:
- Per-attempt connect/read timeouts.
- An absolute deadline/remaining budget propagated from the caller.
- Total queue/concurrency limits.
- Budgets aligned across gateways and other clients.
- Metrics for logical latency and attempt counts.

### Circuit Breakers Differ from Retries

Retries fit brief transient failures. Circuit breakers stop calling an upstream when it is consistently failing/overloaded; bulkheads cap concurrent requests; rate limiters prevent generating excessive load. These are **complementary** mechanisms and should not be configured to multiply retries across layers.

## 19. Idempotency-Key: How Must the Server Handle the Contract?

A common pattern for POST creation:

```http
POST /payments HTTP/1.1
Host: payments.example.test
Content-Type: application/json
Idempotency-Key: 2fb18684-1dbd-484e-b188-87dc29d4dace

{"orderId":"order-1024","amount":1500}
```

The key is illustrative. Real systems must:
1. Validate principal/tenant and payment creation rules.
2. Lock/deduplicate the key **per tenant+operation scope**.
3. Compare payload fingerprints; the same key with a different payload must conflict.
4. On the first request, record the side effect and result per transaction/consistency policy.
5. On retries with the same key, return a well-defined outcome (same status/body or status lookup).
6. For concurrent identical submissions, only one request executes the side effect; others receive the cached result or an in-progress status.
7. Enforce a TTL suited to the client retry window; once expired, the key may be treated as new again.
8. Emit metrics/audits without leaking another user's operation outcome.

A client can attach the key via:

```java
UUID logicalOperationId = UUID.randomUUID();

client.post()
        .uri("/payments")
        .header(
                "Idempotency-Key",
                logicalOperationId.toString())
        .body(paymentRequest)
        .retrieve()
        .toBodilessEntity();
```

This is a **snippet without retry implementation** using hypothetical `client`/`paymentRequest` variables. When business logic decides to retry the same logical operation, it must **keep the same logicalOperationId** across all attempts—never generate a new UUID inside an interceptor per attempt.

**Do not enable POST retries solely because of this snippet.** If the payment server lacks idempotency-key handling, the header will not stop duplicates. And if a streaming body is not replayable, the client must also reconstruct bytes for each attempt.

## 20. Observability: Logical Requests vs Individual Attempts

One logical operation can produce three physical HTTP attempts. Emit two telemetry levels:

```text
Logical operation: catalog.get(id=42)
   |
   +-- attempt=1, status=503, duration=350ms
   +-- wait=100ms
   +-- attempt=2, status=502, duration=120ms
   +-- wait=200ms
   +-- attempt=3, status=200, duration=80ms
   |
   +-- finalOutcome=SUCCESS
   +-- logicalLatency=850ms
```

Latency numbers are illustrative. Counting only attempts inflates request counts 3x and makes error-rate metrics look high even when the logical caller succeeds. Measuring only logical operations can hide upstream 503 storms.

Measure:
- Logical outcome and attempts-per-operation.
- Status distribution by upstream service and **endpoint template**, not raw IDs/queries.
- Retries attempted/exhausted/suppressed (unsafe, non-retryable, budget expired, Retry-After too long).
- Per-attempt duration vs overall latency.
- Connect/read timeouts, pool waits, and response deserialization errors.
- Concurrency, circuit breaker state, and load.
- Trace IDs via frameworks like Micrometer Observation/tracing; never log raw Authorization headers.

### Correlation IDs

A single request attempt can carry its own ID for debugging. The logical operation should have a stable higher-level trace/span or business correlation ID. **Idempotency-Key is a business deduplication key, not a trace ID**, and a per-attempt UUID must never be used as an idempotency key.

## 21. Security and Privacy in Interceptors

### Never Log Secrets

Exercise special caution with:
- `Authorization`/Bearer tokens.
- `Cookie` and `Set-Cookie`.
- Basic auth credentials.
- JWT claims or query tokens.
- Payment/card data and body contents.
- Request URLs containing customer identifiers.

You may log HTTP method, upstream service name, status family, duration, and a sanitized correlation ID.

### Prevent SSRF

Never let callers pass arbitrary absolute hosts or user-supplied URLs into a `RestClient` that can reach internal networks. Use trusted `baseUrl` values, host/scheme allowlists, and redirect controls. An interceptor that automatically attaches Authorization to all redirects/cross-host calls can leak credentials without proper redirect/host policies.

### TLS and Certificates

Never retry certificate validation errors as if the upstream were merely overloaded. Never disable hostname verification to “fix” `ResourceAccessException`. Configure trust stores, mTLS/client certs, and proxy/HTTPS settings properly.

### Headers and Duplicate Authorization

An interceptor should avoid overwriting headers set by a secure auth mechanism unless intentional. With Spring Security OAuth2 client, use the provided integrations to refresh/attach tokens rather than infinitely retrying 401 or logging tokens.

## 22. Practical Retry Scenarios

### 22.1. GET Catalog 503 Then 200

Bounded retry is safe, ideally honoring Retry-After. Final result is item 200 across two attempts. No data dedup is needed since GET is read-only per contract.

### 22.2. GET 404 Immediately After Creating a Resource

If the upstream is eventually consistent and the contract **allows read lag**, use polling/backoff for “resource readiness” in a **dedicated workflow**, rather than enabling 404 retries for every GET. Timeout/polling budgets and visibility semantics must be explicit.

### 22.3. PUT with If-Match

PUT is idempotent in intended effect, yet a retry can receive 412 because the first attempt committed and changed the ETag. The client must re-read the resource/version to determine the final state. Never retry endlessly with a stale ETag.

### 22.4. DELETE Succeeded, Then Retry Returns 404

The desired state “resource no longer exists” may already be achieved. An API contract might treat 404 after a retry as acceptable or define specific semantics. Distinguish business operation success from the HTTP status of the final attempt.

### 22.5. Payment POST Timeout

Do not retry without a server idempotency contract. With keys/dedup, retry the same logical operation and reconcile with a payment status endpoint. Never generate a new key per attempt.

### 22.6. 429 with Retry-After: 60

If the caller has only 3 seconds of budget left, fail fast or reschedule the job after 60 seconds. Never sleep 3 seconds and resend in violation of the server's hint.

### 22.7. 500 Due to Deserialization/Schema Mismatch

Do not retry: the same malformed response body will keep failing. Separate mapping errors (Jackson/DTO versioning) from upstream 500 statuses, and alert on schema compatibility.

### 22.8. 502/504 at an API Gateway

Can occur after the upstream already received a side-effecting request. Retry only if idempotent/replay-safe. A gateway 504 is not proof the request never ran.

## 23. Testing Idempotency End-to-End with a Fake Payment Server

A client unit test for POST no-retry is necessary but **insufficient** to prove an exactly-once charge. For a server supporting Idempotency-Key, integration tests should:

1. Send the same `Idempotency-Key` and identical payload twice.
2. Verify **only one** payment record/charge exists in the DB/ledger.
3. Verify the second response matches the contract (same ID/result).
4. Send the same key with a different payload; server returns conflict.
5. Send two concurrent requests with the same key to expose race conditions.
6. Simulate a crash between charge commit and dedup persistence.
7. Verify TTL and key scoping per principal/tenant.
8. Simulate response loss after commit and retry with the same key.

If the server returns 200 to both attempts while the DB holds two charges, idempotency **failed** even though HTTP responses looked fine. Exactly-once business effects require server-side atomicity/coordination tested under concurrency and failures.

## 24. Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| GET 503 does not retry | Caller bypassed RetryExecutor or custom status handler swallowed exception | Keep typed error, invoke retry boundary for eligible operations |
| POST creates duplicate records | Retried unsafe operation without idempotency contract | Do not auto-retry POST; server key + atomic dedup |
| Infinite retries | Missing maxAttempts/deadline | Bounded attempts and total budget |
| Retries earlier than Retry-After | Used fixed sleep/backoff only | Parse Retry-After and skip if over budget |
| Retries 400/403 | Treated all 4xx as transient | Fail fast and fix input/ACL |
| Pointless 500 retries | Code bug or schema mismatch | Classify errors, never blanket-retry 5xx |
| 429 response loses headers | Custom exception wrapper stripped response headers | Preserve status, Retry-After, safe diagnostics |
| 404 turned into empty DTO | Swallowed status in onStatus/handler | Map missing explicitly to Optional/domain exception |
| Used `exchange()` expecting `onStatus` to run | `exchange` bypasses status handlers | Handle status directly inside callback |
| Interceptor runs twice per attempt | Duplicate registration or self-retrying execute | Check registration/chain, one execute |
| Connection pool exhausted | Response interceptor threw after receiving response without closing | Close response before throwing, monitor pool |
| Logs leak passwords | Dumped body/Authorization/query | Sanitize metadata, never log raw bodies |
| New idempotency key per retry | Generated UUID inside interceptor | Create key once at logical business operation |
| Same key with two different payloads | Missing fingerprint check/server scope | Server 409/conflict rule |
| Client keeps retrying TLS cert error | ResourceAccessException treated all errors as transient | Filter certificate/DNS config failures |
| Very long total latency | Bounded only per-attempt timeout | Enforce end-to-end deadline and budget |
| Synchronized bursts after outage | Fixed sleep without jitter | Full jitter/backoff/rate limits |
| Retry storm across gateway/app | Each layer retries independently | Pick one owning layer, global budget |
| Error-rate metric inflated 3x | Counted raw attempts as logical operations | Separate logical vs attempt metrics |
| Client leaks credentials to wrong host | Missing redirect/SSRF policy | Trusted base URL, redirect allowlist |
| Blocking threads stall | Long sleep on synchronous web request | Fail fast/deferred job or async architecture |
| Second DELETE returning 404 treated as failure | Confused idempotency with response equality | Check desired state and contract |
| Second PUT returns 412 | Stale If-Match after first attempt committed | Reconcile resource/ETag |
| Retry fails on body stream | One-shot body is non-replayable | Bounded buffering/reconstruct request body |
| Test fails to assert attempt count | Asserted only final 200 | Use MockRestServiceServer.verify and explicit expectations |

## 25. Synchronous HTTP Client Design Checklist

- [ ] Pick `RestClient`/`RestTemplate` appropriately for the project and supported Spring version.
- [ ] Interceptors only decorate requests/responses and never auto-retry every request.
- [ ] Log metadata safely; never log bodies/secrets.
- [ ] Never leak responses when an interceptor throws after receiving an HTTP response.
- [ ] Separate HTTP errors from I/O errors.
- [ ] `retrieve()`/`exchange()` semantics are understood and tested.
- [ ] Specific policies exist for 400/401/403/404/409/412/422/429/5xx.
- [ ] Retries enabled only when operations are semantically safe/idempotent/replayable.
- [ ] POST/PATCH do not retry by default; Idempotency-Key only works when server-supported.
- [ ] Max attempts include the initial attempt, with per-attempt timeouts and an overall deadline.
- [ ] Honor Retry-After delta-seconds/HTTP-date.
- [ ] Backoff uses jitter and stays within caller budget.
- [ ] No retry storms across gateway/app/load balancer.
- [ ] Never retry TLS certificate/configuration errors as transient errors.
- [ ] One logical operation shares a trace ID; each attempt has separate diagnostics.
- [ ] Auth token refresh is bounded; never enable infinite 401 retries.
- [ ] Verify exact requests/headers/statuses/attempt counts with MockRestServiceServer.
- [ ] Test socket timeouts and real HTTP transport separately.
- [ ] Test server-side idempotency under concurrent duplicate requests and fault injection.
- [ ] Monitor circuit breakers, bulkheads, and metrics before production rollout.

## 26. Hands-On Exercises

### Exercise 1 — RestClient Status Mapping

Have a mock upstream return 404, 429, 500, and 503. Write three versions:
1. Default `retrieve()`.
2. `retrieve().onStatus(...)` mapping 404 specifically.
3. `exchange(...)` returning a domain result per status.

Prove that `exchange(...)` **does not trigger** retrieve's status handlers and must retain retry metadata when needed.

### Exercise 2 — Retrying 503 with Retry-After

Mock GET returning 503 + `Retry-After: 0`, then 200. Verify **two** attempts occur. Change Retry-After to 30 seconds with a 2-second budget: only **one** attempt occurs. Do not actually sleep in tests; inject Sleeper and capture requested delays.

### Exercise 3 — Method Selection

Simulate socket resets for GET, HEAD, PUT, DELETE, POST, and PATCH. With the demo RetryExecutor, only GET/HEAD auto-retry. Explain why PUT/DELETE are idempotent per RFC yet still require separate policies for body replayability, preconditions, and server semantics before enabling.

### Exercise 4 — Payment Idempotency-Key

Create a mock server with a DB and unique constraint per tenant + key. Send the same key/payload twice and return the same payment ID. Send that key with a different payload and return conflict. Run two concurrent requests to uncover races; handle crashes/TTLs and avoid cross-tenant leakage.

### Exercise 5 — Stopping Retry Storms

Simulate gateway retries 2x and application retries 3x. Measure raw downstream attempts vs logical calls. Pick one retry owner, add a circuit breaker and budget, and verify attempt counts drop.

### Exercise 6 — Classifying I/O Errors

Simulate connect timeout, connection reset, certificate validation failure, and DNS configuration error. For a safe GET, decide which errors deserve retries and which should fail fast. Never rely solely on `instanceof ResourceAccessException` in production.

### Exercise 7 — Safe Logging

Add an interceptor logging method/status/latency/correlation ID. Assert logs contain **no** bearer tokens, body passwords, customer IDs in queries, or full exception response bodies. If the interceptor throws after receiving a response, verify the response is closed.

## 27. Self-Check Questions

1. What parameters does `ClientHttpRequestInterceptor` receive and what does it return?
2. Why should an interceptor call `execution.execute` once per attempt?
3. How does `RestClient.retrieve()` normally handle 4xx/5xx?
4. Does `RestClient.exchange()` run default status handlers?
5. How does `onStatus` differ from `defaultStatusHandler` in scope and order?
6. Is `RestTemplate.ResponseErrorHandler` a retry policy?
7. How does `RestClientResponseException` differ from `ResourceAccessException`?
8. Can server side effects occur even if the client receives a timeout?
9. How do safe methods and idempotent methods compare?
10. Why are GET and HEAD generally easier to retry than POST?
11. Does PUT/DELETE idempotency mean the retried response always equals the first response?
12. Why does HTTP 504 not prove an operation never ran?
13. Should statuses 400/403/404/409/412 be auto-retried?
14. Which header can accompany 429 and 503 to suggest a wait duration?
15. What are the two formats of Retry-After?
16. If Retry-After is 60s while remaining deadline is 2s, how should you handle it?
17. What is the maximum number of HTTP requests for MaxAttempts=3?
18. Why should exponential backoff include jitter?
19. Why do multiple retry layers cause retry storms?
20. What does Idempotency-Key accomplish if the server has not implemented deduplication?
21. Why must the key remain unchanged for the same logical operation across attempts?
22. How should the same key with a different payload be handled?
23. Can you rely on a process-local cache to guarantee exactly-once charges in a cluster?
24. Why must TLS certificate errors not be retried repeatedly?
25. Why is read timeout not a total deadline?
26. When using a custom `ResponseErrorHandler`, does it know which business operations are safe?
27. In a test, how do you assert a 503 GET was called twice rather than only asserting the final 200?
28. Why should interceptors not log raw response bodies?
29. When using RestClient.Builder(RestTemplate), what must be re-verified?
30. If the request body is a one-shot input stream, what risk does retrying introduce?
31. Why does POST `Idempotency-Key` need backend transactions/unique constraints?
32. Does `HttpStatusCode` differ from an integer status?
33. Does `onStatus` run only when an HTTP response arrived, or also on DNS timeout?
34. When is a circuit breaker more helpful than continuing retries?
35. What is the primary role of MockRestServiceServer in this lesson?

**Hints:** (1) HttpRequest, byte[] body, execution; ClientHttpResponse. (2) Avoid duplicate side effects and response leaks. (3) Throws RestClientException for error statuses. (4) No. (5) Per request vs client-wide defaults. (6) No. (7) HTTP response received vs network access failure. (8) Yes. (9) Safe requests no side effects; idempotent repeats yield equivalent intended effects. (10) Read-only semantics. (11) No. (12) Upstream may have already committed. (13) Not by default. (14) Retry-After. (15) delta-seconds, HTTP-date. (16) Fail/defer, do not retry early. (17) Three, including the initial attempt. (18) Spread out synchronized bursts. (19) Multiplicative attempts. (20) No guarantee if the server ignores the key. (21) Deduplicates the same operation. (22) Conflict. (23) No. (24) Configuration errors do not fix themselves. (25) Multiple phases/attempts/sleeps exist. (26) No. (27) Expect two requests and verify. (28) Secrets/privacy. (29) Factory, interceptors, codecs, error/status behavior. (30) Non-replayable. (31) Prevents double-side-effect races. (32) Spring abstraction for status codes. (33) Only when a response exists. (34) When an upstream stays unhealthy for a sustained period. (35) Verifying requests/statuses/attempts without needing the Internet.

## 28. Official Reference Documentation

- [Spring Framework — REST Clients: RestClient and RestTemplate](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html)
- [Spring Framework 6.1 — RestClient Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/client/RestClient.html)
- [Spring Framework 6.1 — RestClient.Builder Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/client/RestClient.Builder.html)
- [Spring Framework 6.1 — ClientHttpRequestInterceptor Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/http/client/ClientHttpRequestInterceptor.html)
- [Spring Framework 6.1 — ClientHttpRequestExecution Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/http/client/ClientHttpRequestExecution.html)
- [Spring Framework 6.1 — RestClientResponseException Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/client/RestClientResponseException.html)
- [Spring Framework 6.1 — DefaultResponseErrorHandler Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/client/DefaultResponseErrorHandler.html)
- [Spring Framework 6.1 — ResourceAccessException Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/client/ResourceAccessException.html)
- [Spring Framework — MockRestServiceServer](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-client.html)
- [Spring Boot 3.3 — Calling REST Services](https://docs.spring.io/spring-boot/3.3/reference/io/rest-client.html)
- [RFC 9110 — HTTP Semantics, Safe and Idempotent Methods](https://www.rfc-editor.org/rfc/rfc9110.html)
- [RFC 9110 — Retry-After header](https://www.rfc-editor.org/rfc/rfc9110.html#field.retry-after)
- [RFC 6585 — 429 Too Many Requests](https://www.rfc-editor.org/rfc/rfc6585.html)
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html)

**Summary:** `ClientHttpRequestInterceptor` is a mechanism for adding headers/observability around **each HTTP attempt**, not a place to automatically replay every request. `RestClient.retrieve()`, `onStatus`/`defaultStatusHandler`, and `RestTemplate.ResponseErrorHandler` turn HTTP statuses into structured error information, yet **never decide by themselves whether an operation is safe to repeat**. Retries must be governed by semantics (safe/idempotent/replayable), error classification, `Retry-After`, backoff/jitter, total budgets, and server-side `Idempotency-Key` guarantees when operations carry side effects. In synchronous services, retries hold threads and multiply load—so **fail fast on non-transient errors and unsafe POSTs**, test exact attempt counts, measure both logical requests and attempts, and add resilience mechanisms only where genuinely needed.
