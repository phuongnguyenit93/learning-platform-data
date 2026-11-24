# WebClient: Error Handling, Bounded Retries, and Avoiding Duplicate Side Effects

## Learning Objectives

After this lesson, you can distinguish HTTP errors from connection errors when calling services with Spring WebClient; decide which errors may be retried; configure bounded retry counts, backoff, jitter, and timeouts; and avoid creating orders, charging payments, or writing data twice when a request is resent. The focus is **business behavior safety**, not merely making an HTTP call eventually return success.

WebClient is a reactive HTTP client returning Mono or Flux. A pipeline executes only when subscribed to (or via `block` in a console app). **`retryWhen` resubscribes to upstream upon an error signal**: if upstream contains an HTTP operation, the request may be sent again. Therefore, retrying is a business decision with impact on external systems.

## 1. Understanding Error Categories Correctly

With the common call **retrieve().bodyToMono(...)**, Spring by default converts HTTP 4xx/5xx into `WebClientResponseException`, carrying status, headers, and response body. Failures before receiving a complete HTTP response—such as connection, DNS, or TLS errors—are typically represented by `WebClientRequestException`. JSON parsing errors, data processing errors, or exceptions thrown by application code belong to different categories; do not automatically retry them merely because they also travel down the `onError` branch.

| Case | Typical meaning | Recommended handling |
| --- | --- | --- |
| 200/201/204 | Success; 204 usually has no body | Read body with right type; handle Mono.empty if appropriate |
| 400/422 | Invalid or malformed request data | Fix input, return business error; usually do not retry |
| 401/403 | Missing authentication or unauthorized | Handle auth/permissions per contract; do not retry unconditionally |
| 404 | Resource not found | Map to business error or empty value per requirements |
| 409/412 | Version/state conflict | Resolve conflict, check write preconditions; do not retry blindly |
| 408/429 | Server request timeout or rate limited | May retry when request is safe; honor Retry-After if server provides it |
| 500/502/503/504 | Server/gateway error; some are transient | Retry only allowlisted codes and when the operation is safe to repeat |
| Connection drop, client-side timeout | Unclear whether the server finished processing | Especially dangerous for write operations; requires deduplication contract |

Do not equate "HTTP returned 5xx" with "the server definitely wrote nothing." For example, the server may have persisted the order, then failed while serializing the response; the client sees 500 or a timeout even though the side effect already happened.

## 2. Catching and Transforming Errors in WebClient

**retrieve()** is convenient when you mainly want the response body. Without customization, 4xx/5xx emit `WebClientResponseException`. Use **onStatus** when you need a specific business exception; the handler receives `ClientResponse` and must return a `Mono` containing a `Throwable` or an error `Mono`. The example below is a **service-integration snippet**, not a standalone program:

~~~java
Mono<Product> findProduct(String id) {
    return webClient.get()
        .uri("/products/{id}", id)
        .retrieve()
        .onStatus(
            status -> status.value() == 404,
            response -> Mono.just(new ProductNotFoundException(id))
        )
        .bodyToMono(Product.class);
}
~~~

Above, `Product` and `ProductNotFoundException` are application types; `webClient` is a configured `WebClient` with a `baseUrl`. When status is 404, the error is converted to a dedicated type so callers can handle it intentionally. Avoid converting all errors into `Mono.empty`, as that erases the difference between "no data" and "service failed."

If you need to inspect status/headers and choose body decoding across multiple branches, use **exchangeToMono** or **exchangeToFlux**; for example:

~~~java
Mono<String> result = webClient.get()
    .uri("/health/details")
    .exchangeToMono(response -> {
        if (response.statusCode().is2xxSuccessful()) {
            return response.bodyToMono(String.class);
        }
        return response.createException()
            .flatMap(Mono::error);
    });
~~~

Here an error response is converted into an exception carrying status/body. Body consumption must happen inside the `ClientResponse` handler; do not retain `ClientResponse` for use after the publisher returned by `exchangeToMono` completes.

Distinguish these operators:
- **doOnError**: observe/log; does not swallow or recover from the error.
- **onErrorMap**: transform the error; preserve the original cause when wrapping exceptions.
- **onErrorResume**: actively recover with another publisher; use only when a valid business fallback exists.
- **retryWhen**: resubscribe upstream, potentially resending the HTTP request.
- **onErrorReturn**: replace the error with a value; dangerous if returning fake data hides an outage.

Operator placement also matters: `doOnError` placed **before** `retryWhen` sees each failed attempt; placed **after** `retryWhen`, it typically sees only the final error when the retry policy could not save the request.

## 3. Bounded Retries: Conditions, Attempt Counts, and Backoff

A safe retry policy must answer four questions: **which errors**, **which methods/operations**, **how many times at most**, and **how long to wait**. Never put `retryWhen(Retry.indefinitely())` on outbound HTTP inside a user request flow.

Project Reactor provides **Retry.backoff(maxRetries, minBackoff)**. For example, `maxRetries = 2` means **one initial call + at most two retries = at most three HTTP requests**. Exponential backoff eases pressure while a service is failing; `maxBackoff` caps overly long waits; jitter prevents many clients from retrying in lockstep at the exact same instant. In the demo below, `jitter = 0` is used solely for repeatable output; in production, non-zero jitter should usually be used.

Example logic deciding retryable errors for a **read-only GET** request:

~~~java
static boolean isTransientHttpFailure(Throwable error) {
    if (error instanceof WebClientResponseException response) {
        int status = response.getStatusCode().value();
        return status == 408 || status == 429 ||
               status == 502 || status == 503 || status == 504;
    }
    return error instanceof WebClientRequestException;
}
~~~

This is an **illustrative policy**, not a universal default retry list for every API. One API returns 500 for a transient error while another returns 500 after persisting; whether to include 500 in the filter must follow the service contract. For 429/503 with `Retry-After`, basic backoff retry **does not automatically honor this header**; custom logic is needed to read the header and schedule retries per server policy if the API requires it.

Application pattern:

~~~java
Retry policy = Retry.backoff(2, Duration.ofMillis(200))
    .maxBackoff(Duration.ofSeconds(2))
    .jitter(0.5)
    .filter(MyClient::isTransientHttpFailure)
    .doBeforeRetry(signal ->
        logger.warn("Retry #{} due to {}",
            signal.totalRetries() + 1,
            signal.failure().toString()))
    .onRetryExhaustedThrow((spec, signal) -> signal.failure());

Mono<String> body = webClient.get()
    .uri("/catalog/{id}", id)
    .retrieve()
    .bodyToMono(String.class)
    .retryWhen(policy);
~~~

This is also an integration snippet: `MyClient`, `logger`, `webClient`, and `id` belong to application code. **`onRetryExhaustedThrow`** here returns the final HTTP/original error instead of a generic "retry exhausted" wrapper, helping upper layers classify the root cause. Log only attempt number, error type, request/correlation ID, and timing; avoid logging tokens, passwords, personal data, or sensitive bodies. `Retry.backoff` does not cap total business duration unless paired with timeouts/budgets at the right layer.

### Timeouts and Total Budget

- **Per-attempt timeout**: use an HTTP connector timeout (e.g., Reactor Netty `HttpClient.responseTimeout`) or a timeout operator placed before `retryWhen`, evaluating the resulting error type carefully.
- **Whole-chain timeout**: place a timeout after `retryWhen` to cap total duration across attempts and backoff.
- **`TimeoutException`** from `Mono.timeout` does not automatically match a filter that only checks `WebClientRequestException`/`WebClientResponseException`; if you want to retry it, decide explicitly.
- Even if the client times out, the earlier request **may still be running on the server**. A timeout is not a rollback command.
- Settings must fit the caller's budget: an API needing a 2-second response cannot have three 2-second timeouts plus seconds of backoff.

## 4. Complete Example: GET Fails with 503 Twice Then Succeeds

The following Java 17+ example starts a small HTTP server in the same JVM that intentionally returns 503 for the first two requests, then returns 200. WebClient calls GET with bounded retries. This JDK server is purely for demo purposes; there are no write operations. The example uses Spring WebFlux and Reactor Netty supplied by `spring-boot-starter-webflux`.

Place the files in the directory:

~~~text
webclient-retry-demo/
├── pom.xml
└── src/main/java/demo/WebClientRetryDemo.java
~~~

**pom.xml** (Spring Boot 3.3.13 is pinned for reproducibility; for real projects choose a currently supported branch):

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>webclient-retry-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/WebClientRetryDemo.java**:

~~~java
package demo;

import com.sun.net.httpserver.HttpServer;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientRequestException;
import org.springframework.web.reactive.function.client.WebClientResponseException;
import reactor.util.retry.Retry;

public final class WebClientRetryDemo {
    private WebClientRetryDemo() {}

    public static void main(String[] args) throws Exception {
        AtomicInteger hits = new AtomicInteger();
        HttpServer server = HttpServer.create(
            new InetSocketAddress("127.0.0.1", 0), 0);

        server.createContext("/items/42", exchange -> {
            int attempt = hits.incrementAndGet();
            int status = attempt <= 2 ? 503 : 200;
            String response = status == 503 ? "temporarily unavailable" : "item-42";
            byte[] bytes = response.getBytes(StandardCharsets.UTF_8);

            exchange.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=UTF-8");
            exchange.sendResponseHeaders(status, bytes.length);
            try (OutputStream stream = exchange.getResponseBody()) {
                stream.write(bytes);
            }
        });
        server.start();

        try {
            int port = server.getAddress().getPort();
            WebClient client = WebClient.builder()
                .baseUrl("http://127.0.0.1:" + port)
                .build();

            Retry boundedRetry = Retry.backoff(2, Duration.ofMillis(100))
                .maxBackoff(Duration.ofMillis(300))
                .jitter(0.0) // Only to give the demo deterministic wait times.
                .filter(WebClientRetryDemo::canRetryGet)
                .onRetryExhaustedThrow((spec, signal) -> signal.failure());

            String item = client.get()
                .uri("/items/42")
                .retrieve()
                .bodyToMono(String.class)
                .retryWhen(boundedRetry)
                .block(Duration.ofSeconds(5)); // Only used in console demo.

            System.out.println("Result: " + item);
            System.out.println("Request count: " + hits.get());
        } finally {
            server.stop(0);
        }
    }

    private static boolean canRetryGet(Throwable error) {
        if (error instanceof WebClientResponseException response) {
            int code = response.getStatusCode().value();
            return code == 429 || code == 502 ||
                   code == 503 || code == 504;
        }
        return error instanceof WebClientRequestException;
    }
}
~~~

Install JDK 17+ and Maven, then inside `webclient-retry-demo` run:

~~~bash
mvn -q compile
mvn -q exec:java -Dexec.mainClass=demo.WebClientRetryDemo
~~~

The two lines printed explicitly by the program are:

~~~text
Result: item-42
Request count: 3
~~~

Maven or libraries may print extra logs depending on the environment. The server returns 503 on attempts 1 and 2; those two errors match the filter, so Reactor resubscribes twice; the 3rd request receives 200. **There is no 4th attempt** because `maxRetries = 2`. Change the server condition to `attempt <= 3` to test retry exhaustion: the final 503 error propagates out and the two success lines are not printed. Change the status to 400 to observe the filter refusing retries on the very first failure.

In a Spring WebFlux application, **never call `block()` on a reactive/event-loop thread**. Services/controllers should return `Mono`/`Flux` for the framework to subscribe. `block()` here is solely for observing synchronous results from `main`.

## 5. Avoiding Duplicate Operations with Side Effects

### 5.1. HTTP Methods and Idempotency

**Idempotent** means sending the same operation multiple times has an **intended final effect on server state equivalent to sending it once**. It does not mean "only one HTTP request happened," "no duplicate log entries," or "every response is identical."

| Method | Semantics per HTTP specification | Retry decision |
| --- | --- | --- |
| GET/HEAD | Safe (read-only) and idempotent per HTTP contract | Usually suitable for transient error retries if implemented properly |
| PUT | Idempotent given the same URI and target state | Can retry when the API genuinely upholds that contract |
| DELETE | Idempotent in deletion effect; subsequent tries may return 404 | Treat 404/204 per contract to avoid false errors |
| POST | Not idempotent by default | Do not auto-retry writes without a deduplication mechanism |
| PATCH | Not idempotent by default | Depends on patch semantics and conditional update rules |

Even GET is not "safe" in a system violating the contract (e.g., a GET that charges money); verify the actual contract. PUT like "set quantity to 5" differs from POST like "add 5 to quantity." Sending the same POST three times can create three orders.

### 5.2. The Dangerous Failure Window

For example, the client sends **POST /orders** to create an order:
1. The server receives POST, saves order #123, and commits the transaction.
2. The network drops before the 201 response reaches the client.
3. WebClient sees a request exception/timeout without knowing the server committed.
4. `retryWhen` resends POST. If the server lacks deduplication, it may create a duplicate order #124.

Catching `WebClientRequestException` and retrying does not resolve the uncertainty in step 3. **You cannot conclude "the request never reached the server" from a client-side error alone.**

### 5.3. Idempotency-Key Must Be Enforced by the Server

A common pattern for resource-creating/payment POSTs is generating **one unique key per business operation** and reusing **that exact key across all retries**. Client-side example (integration snippet):

~~~java
String operationKey = /* stable ID of an order creation request */;
Mono<OrderResponse> request = webClient.post()
    .uri("/orders")
    .header("Idempotency-Key", operationKey)
    .bodyValue(command)
    .retrieve()
    .bodyToMono(OrderResponse.class);

// Only configure retry when the server guarantees idempotency key handling
// and errors are classified as transient.
~~~

`OrderResponse`, `command`, and `operationKey` are application values; the snippet is not a standalone program. Never generate a new UUID **inside** `Mono.defer` or per retry attempt; doing so sends a different key each time and defeats deduplication. Conversely, never reuse one key for **two independent business operations**.

Proper server-side idempotency enforcement must ensure:
- Store the key within the appropriate scope—typically tenant/user + endpoint/operation + key—along with a request fingerprint; reusing a key with different content must return a conflict error rather than silently running a new operation.
- **Check/claim the key and persist the business outcome atomically** (e.g., transaction/unique constraint or equivalent mechanism). Checking "key does not exist" and then inserting without locking races under concurrent requests.
- If the same key and payload arrive again after completion, return the stored result or contract-defined status instead of re-executing side effects.
- Define handling for in-flight requests, failed outcomes, TTL/retention, access control, and crash recovery. An expired TTL may permit re-execution, so key lifetime must align with business requirements.
- For systems publishing events or calling other services, a database transaction alone is not enough to prevent duplicate messages; consider transactional outbox, unique operation IDs, and idempotent consumers.

An `Idempotency-Key` **does not take effect just because the client sends the header**; the server must support and document the contract. If the server does not support it, the safe choice may be **not retrying writes**; instead query status by operation ID or use a result-lookup API before deciding whether to resend. For payments, handle unknown outcomes per provider policy.

## 6. Retrying at the Right Scope and Controlling Load

**A publisher can be subscribed to multiple times.** `retryWhen` resubscribes to the entire upstream chain to its left, including side effects triggered upon subscription. Avoid placing side effects like sending emails, writing to a DB, or emitting events inside the retried section unless they have deduplication keys.

~~~java
// Dangerous if savePayment has side effects and lacks deduplication:
savePayment(command)
    .then(webClient.get().uri("/receipt").retrieve().bodyToMono(String.class))
    .retryWhen(retryPolicy); // May invoke savePayment again.

// Only retry the HTTP read portion when appropriate:
savePayment(command)
    .then(
        webClient.get().uri("/receipt")
            .retrieve()
            .bodyToMono(String.class)
            .retryWhen(retryPolicy)
    );
~~~

This snippet illustrates **resubscribe scope** only; `savePayment`, `command`, `webClient`, and `retryPolicy` are assumed application components. Narrowing the scope does not protect `savePayment` if an outer caller retries the whole flow; idempotency still needs evaluation at every layer.

In real systems, retrying across multiple layers (HTTP client, service, message consumer, gateway, job) multiplies traffic: three layers each allowing up to three attempts can generate up to **27 attempts** for a single action. Design retries at a small number of intentional layers and enforce **retry budgets**, concurrency limits, and rate limiters/circuit breakers when needed. Backoff with jitter softens "retry storms" but does not replace capacity limits. Apply retries only to **short-lived recoverable errors**; input errors or logic bugs require fixing the root cause.

For operational observability, measure actual attempt counts, post-retry success rates, status codes, timeouts, end-to-end latency, backoff wait times, and budget-rejected requests. Distinguish "user performed one action" from "client sent three HTTP requests." Alert if retries raise load without improving success rates.

## 7. Common Implementation Pitfalls

1. **Retrying every exception**: `WebClientResponseException` 400/401/404 and parsing errors keep retrying even though the request never changes. Filter by status and error class.
2. **Miscounting attempts**: `Retry.backoff(3, ...)` allows up to three retries **after** the initial attempt—meaning up to four attempts total, not three.
3. **Retrying all POSTs**: a lost response does not prove the server wrote nothing. Require a server-enforced `Idempotency-Key`, conditional writes, or a status-query mechanism.
4. **Generating a new key per attempt**: every retry looks like a brand-new operation. Keys must be stable per operation.
5. **No timeout/budget**: multiple timeouts plus backoff exceed the caller's SLA and pile up hanging requests.
6. **Ignoring `Retry-After`**: clients hammer a rate-limited API; adapt retry scheduling to the service's protocol.
7. **Swallowing errors with fake fallbacks**: `onErrorResume` returning "empty success" for a payment misleads downstream callers. Fallbacks must make clear business sense.
8. **Placing retry too broadly**: retrying a chain containing DB writes/event emissions duplicates work; narrow the resubscribed region.
9. **Confusing request timeout with rollback**: the client stops waiting, yet the server may still be processing.
10. **Calling `block()` in a reactive handler**: blocks the event loop, cuts throughput, and risks runtime errors; return `Mono`/`Flux` instead of blocking.
11. **Testing only the happy path**: missing tests for 400, 404, 429, 503, request exceptions, exhausted retries, duplicate keys, mismatched payloads with same key, and concurrent requests.

## 8. Decision Checklist Before Enabling Retries

Determine in order: (1) is this a read-only GET or an operation that mutates state; (2) if the server succeeds but the response is lost, is a second send safe; (3) is an idempotency key/conditional write or server contract supported; (4) are errors explicitly classified and recoverable; (5) do total attempts, backoff, jitter, and timeouts fit the budget; (6) are metrics/logs and duplicate-request tests in place.

**Principle to remember:** retries improve completion odds against transient failures, but **do not automatically provide exactly-once semantics for side effects**. For writes, safety must come from the protocol and server state (idempotency, unique constraints, transactional outbox/consumer deduplication) before the client decides to retry.

## References

- Spring Framework Reference — WebClient retrieve and onStatus: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html
- Spring Framework Reference — exchangeToMono/exchangeToFlux: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-exchange.html
- Project Reactor API — RetryBackoffSpec, filter, jitter, maxBackoff, and onRetryExhaustedThrow: https://projectreactor.io/docs/core/release/api/reactor/util/retry/RetryBackoffSpec.html
- HTTP Semantics — safe/idempotent methods and Retry-After: https://www.rfc-editor.org/rfc/rfc9110
