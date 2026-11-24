# Timeouts, conditional retries, and request idempotency in Spring WebClient

## 1. Why combine timeouts, retries, and idempotency?

An HTTP client operating over a network can always encounter failures: slow DNS, inability to acquire a connection from the pool, TCP connection failure, slow server response, mid-stream response interruption, or temporary dependency overload. **Timeouts** limit how long the application waits. **Retries** re-attempt when the failure is likely transient. **Idempotency** ensures re-sending the same operation produces no unintended side effects.

These three mechanisms must be designed together.

For example, an application submits an order creation command:

1. The client sends POST /orders.
2. The server creates the order successfully.
3. The response is lost in transit.
4. The client does not know whether the server processed it and times out.
5. If the client blindly resends POST, the server may create a second order.

Timeouts keep the client from waiting forever, yet do not prove the server has not executed the operation. Retries recover from transient failures, yet can duplicate operations. An idempotency key lets the server recognize a resend of the same logical operation and return the stored result.

This lesson covers:

- Timeout layers of WebClient and Reactor Netty.
- Differences between transport timeouts and Reactor Publisher timeouts.
- Classifying retryable vs. non-retryable errors.
- Exponential backoff, jitter, retry limits, and overall deadlines.
- HTTP safe/idempotent semantics per RFC 9110.
- Idempotency-Key, fingerprints, storing results, and handling concurrent requests.
- Replaying request bodies on retry.
- Testing retries with MockWebServer and StepVerifier.
- A Java 17, Spring Boot 3.3.5, and WebClient example with explicit timeout/retry configuration.

## 2. Timeouts in HTTP clients

A timeout is a time limit on a specific activity. No single timeout covers every stage of a request.

A WebClient request can go through:

~~~text
Subscribe
   |
   v
Acquire connection from pool
   |
   v
DNS resolution
   |
   v
TCP connect
   |
   v
TLS handshake (HTTPS)
   |
   v
Send request headers/body
   |
   v
Wait for response headers
   |
   v
Read response body
   |
   v
Decode body into object
   |
   v
Complete
~~~

If you only place a timeout at the Mono level, the application can cap overall pipeline duration, but cannot tell which stage was slow. If you only set a response timeout, waiting for a connection or pool slot can still stretch according to another limit.

### 2.1. Common timeout types

| Type | Limits which activity | Common configuration |
| --- | --- | --- |
| **Pool acquire timeout** | Waiting for an available connection in the pool | ConnectionProvider.pendingAcquireTimeout |
| **Connect timeout** | Establishing a TCP connection to the remote host | ChannelOption.CONNECT_TIMEOUT_MILLIS |
| **DNS timeout** | Resolving domain names | Resolver/transport configuration |
| **TLS handshake timeout** | Completing the TLS handshake | HttpClient.secure(...) |
| **Response timeout** | Waiting for response/read per connector | HttpClient.responseTimeout |
| **Read timeout** | No data read within the allowed window | ReadTimeoutHandler |
| **Write timeout** | Writing data to transport takes too long | WriteTimeoutHandler |
| **Publisher timeout** | A Mono/Flux emits no signal within the allowed time | Mono.timeout / Flux.timeout |
| **Business deadline** | Entire business operation, possibly spanning multiple HTTP calls | Service/application-layer deadline |

Exact names and configurability depend on the HTTP connector. WebClient can use Reactor Netty, JDK HttpClient, Jetty, or another connector. Examples below use Reactor Netty.

### 2.2. Pool acquire timeout

WebClient typically uses a connection pool when running on Reactor Netty. If the pool reaches its limit and no idle connection is available, a request must wait for a slot.

You can configure:

~~~java
ConnectionProvider provider = ConnectionProvider.builder("orders")
    .maxConnections(50)
    .pendingAcquireTimeout(Duration.ofSeconds(2))
    .maxIdleTime(Duration.ofSeconds(20))
    .build();
~~~

- **maxConnections** limits the number of connections managed for the corresponding host/pool.
- **pendingAcquireTimeout** limits how long to wait to acquire a connection.
- **maxIdleTime** limits how long a connection remains idle in the pool.

If the pool is too small, requests can time out before ever being sent to the server. That is a capacity/pool issue, not necessarily a slow server. Monitor active, idle, and pending connections before increasing timeouts.

### 2.3. Connect timeout

Connect timeout limits the time to establish a TCP connection. With Reactor Netty:

~~~java
HttpClient httpClient = HttpClient.create()
    .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 2_000);
~~~

The value is in milliseconds. This timeout does not limit how long the server takes to process the request after connecting.

### 2.4. Response timeout

You can configure a response timeout:

~~~java
HttpClient httpClient = HttpClient.create()
    .responseTimeout(Duration.ofSeconds(3));
~~~

This is a Reactor Netty-layer configuration. It limits waiting for response data per the connector's mechanism; it is not equivalent to an overall deadline for an entire business operation.

For streaming responses, distinguish the interval between data reads from the total duration of the stream. A valid stream may stay open for minutes while periodically emitting data.

### 2.5. Read timeout and write timeout

When read/write limits on the Netty pipeline are needed:

~~~java
HttpClient httpClient = HttpClient.create()
    .doOnConnected(connection -> connection
        .addHandlerLast(new ReadTimeoutHandler(5))
        .addHandlerLast(new WriteTimeoutHandler(5))
    );
~~~

These handlers have specific semantics and can affect reused connections. Add them only when you understand request/connection idle behavior. Do not set every timeout to the same value out of habit; choose values based on payload characteristics and target service behavior.

### 2.6. Timeouts at the Mono and Flux level

Reactor provides the timeout operator:

~~~java
Mono<OrderResponse> response = webClient.get()
    .uri("/orders/{id}", id)
    .retrieve()
    .bodyToMono(OrderResponse.class)
    .timeout(Duration.ofSeconds(5));
~~~

For Mono, timeout limits the wait for a result from subscription until the Mono emits a result/completes per operator semantics.

For Flux:

~~~java
Flux<Quote> quotes = webClient.get()
    .uri("/quotes")
    .retrieve()
    .bodyToFlux(Quote.class)
    .timeout(Duration.ofSeconds(10));
~~~

Timeout on Flux generally limits the wait for the next signal; the timer resets after each signal. It is useful as a stream idle timeout, but not an overall deadline for the entire stream if the stream continuously emits items.

When you need to cap an entire operation involving multiple retries, place the deadline outside the retry sequence. Example:

~~~java
Mono<OrderResponse> operation =
    Mono.defer(this::oneAttempt)
        .retryWhen(retryPolicy)
        .timeout(Duration.ofSeconds(8));
~~~

The outermost timeout caps the total time of attempts and backoff. If per-attempt timeouts are needed, place a timeout inside oneAttempt.

### 2.7. A timeout does not mean the server stopped processing

When the client times out, Reactor cancels the client-side subscription. That does not guarantee the server aborted its work or transaction.

What may have happened:

- The request never reached the server.
- The server received it but has not processed it yet.
- The server executed the side effect, yet the response has not returned.
- The server sent the response, yet the connection dropped.
- The client received headers, yet the body was interrupted.

Therefore, a timeout on a POST/data-creating command usually leaves **an indeterminate outcome**. If a request can cause side effects, use idempotency or a status-query mechanism before resending.

## 3. Configuring WebClient with Reactor Netty

A WebClient instance should be reused. Configure the connector once rather than creating a new client per request.

Example:

~~~java
@Configuration
public class WebClientConfiguration {

    @Bean(destroyMethod = "dispose")
    ConnectionProvider ordersConnectionProvider() {
        return ConnectionProvider.builder("orders")
            .maxConnections(50)
            .pendingAcquireTimeout(Duration.ofSeconds(2))
            .maxIdleTime(Duration.ofSeconds(20))
            .build();
    }

    @Bean
    WebClient ordersWebClient(
        WebClient.Builder builder,
        ConnectionProvider ordersConnectionProvider
    ) {
        HttpClient httpClient = HttpClient
            .create(ordersConnectionProvider)
            .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 2_000)
            .responseTimeout(Duration.ofSeconds(3));

        return builder
            .baseUrl("https://orders.example")
            .clientConnector(
                new ReactorClientHttpConnector(httpClient)
            )
            .build();
    }
}
~~~

Key imports:

~~~java
import java.time.Duration;

import io.netty.channel.ChannelOption;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;

import reactor.netty.resources.ConnectionProvider;
import reactor.netty.http.client.HttpClient;
~~~

This configuration illustrates:

- Wait on pool at most 2 seconds.
- TCP connect at most 2 seconds.
- Response timeout of 3 seconds.
- At most 50 connections in the pool.
- Idle connections kept at most 20 seconds.

Actual values should be based on target latency, load, connection pools, and downstream service timeouts. Proxy/load balancer timeouts must also be factored in.

### 3.1. WebClient does not only support Reactor Netty

If the application uses JDK HttpClient or a Jetty connector, timeout APIs differ. Do not apply Netty configuration to a WebClient using another connector and expect it to take effect.

Inspect which connector is created in Spring Boot configuration and declare explicit dependencies if consistent behavior is needed.

### 3.2. Do not set timeouts too low

Overly tight timeouts can cancel valid requests while the server is still processing. If the client then retries, the server may receive multiple requests for the same operation.

Set timeouts based on:

- p50, p95, and p99 latency.
- Normal processing time of the dependency.
- Pool wait time.
- Request/response payload sizes.
- TLS and network overhead.
- Overall business deadline.
- Safety of retrying.

## 4. Retries in Reactor

A retry re-subscribes to a Publisher when it emits onError and the strategy permits another attempt.

Simple example:

~~~java
Mono<String> response = webClient.get()
    .uri("/health")
    .retrieve()
    .bodyToMono(String.class)
    .retry(2);
~~~

**retry(2)** means at most two resubscriptions after the initial attempt: up to three total attempts. The bare retry operator does not distinguish transient from permanent errors; without filtering, it can repeat 400 errors, deserialization errors, or configuration errors.

For HTTP clients, use conditional retries.

### 4.1. Errors that are usually retryable

Depending on the API contract and business logic, the following can be transient failures:

- Connection reset or unexpected connection close.
- Connect timeout.
- Response timeout.
- HTTP 408 Request Timeout.
- HTTP 502 Bad Gateway.
- HTTP 503 Service Unavailable.
- HTTP 504 Gateway Timeout.
- HTTP 429 Too Many Requests when Retry-After is handled properly.

HTTP 500 may be a transient failure or an application bug. Only retry it if the target service's contract permits and with strict bounds.

### 4.2. Errors that should usually not be retried automatically

| Error | Reason |
| --- | --- |
| 400 Bad Request | Invalid payload or request syntax |
| 401 Unauthorized | Requires valid authentication/token |
| 403 Forbidden | Insufficient permissions |
| 404 Not Found | Resource does not exist |
| 409 Conflict | Business or state conflict |
| 422 Unprocessable Content | Data violates semantic rules |
| JSON decode error | Response does not match schema |
| SSL certificate error | Configuration/certificate failure; retrying rarely helps |
| Invalid URI/configuration | Client configuration error |
| Validation error | Data must be fixed rather than resent unchanged |

This is a starting policy, not a rigid rule for every API. For example, 404 can be temporary in an eventual-consistency system; 409 may have a dedicated retry contract. Let the target API documentation decide.

### 4.3. RetryBackoffSpec

Reactor provides **Retry.backoff(...)**:

~~~java
Retry retryPolicy = Retry.backoff(
        2,
        Duration.ofMillis(200)
    )
    .maxBackoff(Duration.ofSeconds(2))
    .jitter(0.5)
    .filter(this::isRetryable)
    .doBeforeRetry(signal ->
        log.warn(
            "Retry attempt {}, cause={}",
            signal.totalRetries() + 1,
            signal.failure().getClass().getSimpleName()
        )
    );
~~~

- **backoff(2, ...)**: at most two retries after the initial attempt.
- **maxBackoff(...)**: caps the maximum wait duration.
- **jitter(...)**: adds randomness so multiple clients do not retry simultaneously.
- **filter(...)**: retries only selected exceptions.
- **doBeforeRetry(...)**: logs the attempt and cause.

RetryBackoffSpec is immutable/copy-on-write and can be configured as a reusable policy.

### 4.4. Exponential backoff

Backoff grows after each failure. For example, starting at 200 ms with a multiplier of 2:

| Retry attempt | Base delay |
| --- | ---: |
| Retry 1 | 200 ms |
| Retry 2 | 400 ms |
| Retry 3 | 800 ms |
| Retry 4 | 1,600 ms |

Actual values are also capped by maxBackoff and adjusted by jitter.

Backoff gives the target service time to recover. If clients retry immediately and continuously, a minor glitch can escalate into a retry storm.

### 4.5. Jitter

Suppose 10,000 clients receive 503 at once and all wait exactly 1 second; they could resend simultaneously 1 second later. Jitter spreads retry timestamps out, reducing load spikes.

In Reactor:

~~~java
Retry.backoff(3, Duration.ofMillis(200))
    .maxBackoff(Duration.ofSeconds(3))
    .jitter(0.5);
~~~

The jitter factor must be between 0.0 and 1.0. The default in RetryBackoffSpec is 0.5.

### 4.6. Retry-After and HTTP 429/503

A server may return a **Retry-After** header suggesting the client wait before trying again. The value can be a number of seconds or an HTTP-date.

A fixed Retry.backoff does not automatically guarantee compliance with Retry-After. If the target API uses this header, parse it and construct the corresponding delay, while enforcing an upper bound so the business deadline is not exceeded.

Do not ignore Retry-After and retry faster than the server requested. For 429, retrying early can keep the client rate-limited.

## 5. HTTP idempotency

An operation is **idempotent** if executing the same request multiple times has the same intended effect on server state as executing it once.

Examples:

- PUT /profiles/42 sets the profile to the same content. Resending does not create an extra profile.
- DELETE /profiles/42 deletes the same resource. The second call may return 404, yet the final state remains that the resource is deleted.
- GET /profiles/42 reads data and requests no business state change.

Idempotency concerns **intended effect**, not requiring identical responses every time. The server may still write logs, update audit history, or increment metrics on each received request.

### 5.1. Safe and idempotent are not the same

- **Safe**: a method defined as read-only, requesting no state change to resources.
- **Idempotent**: sending the same request multiple times has the same intended effect as sending it once.

A method can be idempotent without being safe. PUT and DELETE are examples.

Per RFC 9110:

| HTTP method | Safe | Idempotent | Notes |
| --- | --- | --- | --- |
| GET | Yes | Yes | Reads representation |
| HEAD | Yes | Yes | Retrieves metadata like GET |
| OPTIONS | Yes | Yes | Queries communication options |
| TRACE | Yes | Yes | Echoes request info per method semantics |
| PUT | No | Yes | Replaces/creates state at URI |
| DELETE | No | Yes | Deletes the identified resource |
| POST | No | Not by default | May produce side effects |
| PATCH | No | Not by default | Depends on patch document semantics |

Do not infer idempotency solely from the method name. A POST endpoint can be designed idempotently by contract, whereas a poorly designed GET endpoint could cause side effects violating HTTP semantics.

### 5.2. When is retrying allowed?

RFC 9110 permits clients to automatically retry an idempotent request when a communication failure occurs before the client reads the response, because repeating the request does not alter the intended effect.

For non-idempotent methods like POST, clients should not retry automatically unless they can prove the request was not applied or have a mechanism ensuring the operation is truly idempotent.

This is why a POST timeout must be handled carefully: the server may have created data while the response was lost.

## 6. Idempotency-Key for POST and operations with side effects

**Idempotency-Key** is a unique key generated by the client for a logical operation. The client sends the same key when retrying that operation. The server stores the key and outcome to recognize duplicate requests.

Example:

~~~http
POST /api/orders
Content-Type: application/json
Idempotency-Key: "8e03978e-40d5-43e8-bc93-6894a57f9324"

{
  "customerId": "C-42",
  "sku": "BK-01",
  "quantity": 2
}
~~~

If the first response is lost, the client resends the same payload with the same key. The server can return the stored result instead of creating a second order.

**Idempotency-Key does not create idempotency by itself.** If the server does not read and persist the key, the header is just metadata. The client must know whether the target API supports this header and what the API contract specifies for using it.

### 6.1. Generate the key once per logical operation

Generate the key before starting the retry chain:

~~~java
String idempotencyKey = UUID.randomUUID().toString();

return orderClient.create(command, idempotencyKey);
~~~

Across every attempt of that operation, reuse the exact same key. Do not generate a new UUID inside each retry, or the server will treat each attempt as a separate operation.

When a user intentionally creates a new order, generate a new key. Never reuse a previous operation's key for a different payload.

### 6.2. The key must be bound to the payload

The server should store a fingerprint of the request alongside the key. The fingerprint can be derived from:

- Hashing the full payload after canonicalization.
- Key business fields.
- A request digest or signature.
- Fields specified in the API contract.

If the same key arrives with a different payload, the server should reject it rather than treating it as a valid retry. Without payload validation, a client could accidentally reuse a key and receive the wrong result from another request.

### 6.3. How does the server store idempotency records?

A storage table might include:

| Field | Purpose |
| --- | --- |
| tenant_id | User/tenant scope |
| operation | Endpoint or operation type |
| idempotency_key | Key from the request |
| request_fingerprint | Payload hash/identifier |
| status | PROCESSING, COMPLETED, or FAILED |
| response_status | Stored HTTP status |
| response_body | Result to return |
| created_at | Start timestamp |
| expires_at | Expiration timestamp |

Create a unique constraint on the appropriate key scope, such as tenant + operation + idempotency_key.

Conceptual flow:

1. Receive request and validate key.
2. Compute fingerprint from payload.
3. Atomically attempt to insert an idempotency record in PROCESSING state.
4. If insertion succeeds, execute business logic.
5. Store the result and transition the record to COMPLETED inside the appropriate transaction.
6. If the key already exists and the fingerprint matches, return the stored result.
7. If the key exists with a different fingerprint, return an error per contract.
8. If the key is still PROCESSING, return a conflict/in-progress status or wait according to the published policy.

### 6.4. Handling concurrent requests

Two requests with the same key can arrive nearly simultaneously. With only a read-then-write check, both might see the key absent and both create an order.

A unique constraint or atomic reservation mechanism is required so only one request becomes owner of the operation. The other request must observe the PROCESSING/COMPLETED state and behave according to the contract.

Do not rely solely on separate Redis GET then SET calls without proper atomic operations. When using Redis, databases, or distributed locks, handle expiry, crashes, and owner recovery.

### 6.5. Side effects outside the database

If order creation also calls a payment gateway or publishes a message to a broker, a plain database transaction does not guarantee all side effects commit together.

Options include:

- Transactional outbox to record events to publish in the same transaction as business data.
- Passing an idempotency key onward to the payment provider if supported.
- Consumer idempotency to guard against duplicate message processing.
- A state machine for long-running operations with explicit pending/completed/failed states.

Do not claim exactly-once simply because a header exists. In practice, systems achieve **effectively-once** semantics through durable deduplication, transactions, and idempotent consumers.

### 6.6. Key retention period

The server must publish its key retention window. Deleting keys too early lets late client retries trigger new side effects. Keeping them forever grows the idempotency store without bound.

Retention should exceed the retry/recovery window committed by the API, with proper indexing and cleanup of expired records.

### 6.7. Status of the Idempotency-Key specification

At the time this lesson was written, **draft-ietf-httpapi-idempotency-key-header-08** is an Internet-Draft under discussion in the IETF, not yet a published RFC. The draft describes unique keys, fingerprints, expiry, and handling duplicate/concurrent requests.

Real-world APIs may have custom contracts for quotes, key length, key scope, status codes, and retention. Follow the target service's documentation; do not assume every server follows the same draft version.

## 7. Combining timeout, retry, and idempotency in WebClient

A safe client must define:

1. Per-attempt timeout.
2. Overall operation deadline.
3. Which errors are retried.
4. Maximum retry attempts.
5. Backoff and jitter.
6. Whether the request body is replayable.
7. Whether the operation is idempotent or carries an idempotency key.
8. Whether error responses are decoded and released properly.

Example:

~~~java
Mono<OrderResponse> createOrder(
    CreateOrderCommand command,
    String idempotencyKey
) {
    return Mono.defer(() -> webClient.post()
        .uri("/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .header("Idempotency-Key", idempotencyKey)
        .bodyValue(command)
        .retrieve()
        .bodyToMono(OrderResponse.class)
        .timeout(Duration.ofSeconds(2))
    )
    .retryWhen(retryPolicy)
    .timeout(Duration.ofSeconds(7));
}
~~~

Meaning:

- Mono.defer builds a fresh request pipeline for each subscription/retry.
- The 2-second timeout bounds each attempt.
- retryPolicy filters transient errors and waits through backoff.
- The 7-second timeout bounds the entire chain of attempts and backoff.
- The same command and idempotencyKey are used across every attempt.

If the API follows the Structured Header syntax in the current draft, the Idempotency-Key value may need to be sent as a quoted string. Some earlier APIs use unquoted UUIDs. Always follow the target server's contract.

### 7.1. Retries must construct a new request

Do not manually re-subscribe to the same ClientResponse or retain a consumed body stream and try to resend it. Each attempt must create a fresh request.

With immutable DTOs/records and bodyValue, re-serialization usually works naturally. With a Publisher, file InputStream, or single-read source, recreate the source for every attempt.

Publisher body example:

~~~java
Mono.defer(() -> {
    Flux<DataBuffer> body = fileService.openFreshBody();

    return webClient.post()
        .uri("/upload")
        .body(body, DataBuffer.class)
        .retrieve()
        .bodyToMono(UploadResponse.class);
})
.retryWhen(retryPolicy);
~~~

This snippet assumes fileService.openFreshBody() opens a fresh source on each invocation. Never reuse a consumed InputStream.

### 7.2. Retries and response bodies

When using retrieve(), 4xx/5xx statuses become WebClientResponseException by default. The exception retains status and response data for retry classification.

If using onStatus() to decode error bodies, read the body inside that callback and convert it into an exception carrying sufficient details. Never attempt to read the same response body multiple times.

With exchangeToMono()/exchangeToFlux(), process the response inside the callback and consume any needed body. The framework releases unconsumed bodies when the callback completes per the API contract.

### 7.3. Avoid retrying all errors

Do not write:

~~~java
webClient.get()
    .uri("/orders")
    .retrieve()
    .bodyToMono(OrderResponse.class)
    .retryWhen(Retry.indefinitely());
~~~

This can infinitely retry 400, 401, decode errors, certificate errors, or programming bugs. It can also keep requests running indefinitely and trigger cascading load.

Use a filter and bounded attempts:

~~~java
Retry retryPolicy = Retry.backoff(2, Duration.ofMillis(200))
    .maxBackoff(Duration.ofSeconds(2))
    .jitter(0.5)
    .filter(this::isRetryable);
~~~

## 8. Error classification for WebClient

A classifier should inspect both HTTP statuses and transport exceptions.

Policy example:

~~~java
private boolean isRetryable(Throwable error) {
    if (error instanceof WebClientResponseException response) {
        int status = response.getStatusCode().value();

        return status == 408
            || status == 502
            || status == 503
            || status == 504;
    }

    if (error instanceof TimeoutException) {
        return true;
    }

    if (error instanceof WebClientRequestException) {
        if (hasCause(error, SSLException.class)
                || hasCause(error, UnknownHostException.class)) {
            return false;
        }

        return hasCause(error, ConnectException.class)
            || hasCause(error, SocketTimeoutException.class)
            || hasCause(error, IOException.class)
            || hasCauseNamed(
                error,
                "ConnectTimeoutException",
                "ReadTimeoutException",
                "PrematureCloseException"
            );
    }

    return false;
}
~~~

This is an illustrative classifier. Exact exceptions depend on the connector, Netty version, and transport. In production, observe actual cause chains and expand for failures verified as transient.

### 8.1. Why not retry all 5xx errors?

Some 5xx errors are transient, yet 500 can also stem from a code or data bug where every retry fails. Only retry statuses documented by the target API as recoverable.

### 8.2. Why not retry 401/403?

401 may require refreshing a token; 403 usually indicates missing permissions. If the system supports token refresh, perform a bounded refresh flow and retry the request only after the token is replaced. Never let a retry policy loop indefinitely with the same invalid credentials.

### 8.3. Handling 429

For 429, read Retry-After. If the server omits the header, use policy-based backoff. If present, choose an appropriate delay while still respecting the overall deadline and upper limit.

Do not use a single shared retry policy for every dependency. Payment, catalog, and notification services can have different error contracts and SLAs.

## 9. Retry budgets, circuit breakers, and system load

Retries help recover from brief glitches, yet can worsen outages if all clients retry at once.

A production strategy should include:

- Small, fixed retry count.
- Exponential backoff and jitter.
- Overall business deadline.
- Bounded connection pool.
- Rate limits and bulkheads.
- Circuit breaker when a dependency fails repeatedly.
- Separate metrics for initial attempts and retries.
- Cap on total retries across layers.

If the frontend retries 3 times, service A retries 3 times, and service B retries 3 times, a single logical operation can generate many requests to a dependency. Calculate retry amplification across the entire call graph.

### 9.1. Do not retry independently at every layer

Pick one layer responsible for retrying each dependency. If gateway, service, and SDK all retry, coordinate budgets and deadlines.

### 9.2. Circuit breaker

A circuit breaker prevents new requests from hitting a continuously failing dependency. When the circuit is open, clients fail fast rather than waiting on timeouts and retries.

Retries and circuit breakers can work together, though operator ordering affects behavior. Design according to the resilience library's contract and test execution order.

### 9.3. Bulkheads and connection pools

Limit concurrent requests so one slow dependency does not consume all application resources. Connection pools, pending acquire queues, and concurrency limits should be sized for expected load.

Do not raise maxConnections infinitely to mask pool acquire timeouts. Doing so increases sockets, memory, and pressure on the target server.

## 10. Complete Java 17+ example: WebClient with timeouts, retries, and idempotency key

The example uses **Spring Boot 3.3.5**, Spring Framework 6.1.x, Java 17, Reactor Netty, and MockWebServer.

The client submits an order creation command via POST. It:

- Sets connect and response timeouts in Reactor Netty.
- Sets a per-attempt timeout.
- Sets an overall deadline across the retry chain.
- Retries only a subset of transient failures.
- Uses exponential backoff and jitter.
- Preserves the same Idempotency-Key across every attempt.
- Verifies actual requests with MockWebServer.

Structure:

~~~text
webclient-timeout-retry-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/
    │       └── com/example/retrydemo/
    │           ├── CreateOrderCommand.java
    │           ├── OrderResponse.java
    │           ├── OrderClient.java
    │           └── OrderClientConfiguration.java
    └── test/
        └── java/
            └── com/example/retrydemo/
                └── OrderClientTest.java
~~~

### 10.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>webclient-timeout-retry-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>

        <dependency>
            <groupId>com.squareup.okhttp3</groupId>
            <artifactId>mockwebserver</artifactId>
            <version>4.12.0</version>
            <scope>test</scope>
        </dependency>

        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
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
~~~

### 10.2. CreateOrderCommand.java

~~~java
package com.example.retrydemo;

import java.math.BigDecimal;

public record CreateOrderCommand(
    String customerId,
    String sku,
    int quantity,
    BigDecimal unitPrice
) {}
~~~

### 10.3. OrderResponse.java

~~~java
package com.example.retrydemo;

public record OrderResponse(
    String orderId,
    String status
) {}
~~~

### 10.4. OrderClientConfiguration.java

~~~java
package com.example.retrydemo;

import java.time.Duration;

import io.netty.channel.ChannelOption;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

@Configuration
public class OrderClientConfiguration {

    @Bean(destroyMethod = "dispose")
    ConnectionProvider orderConnectionProvider() {
        return ConnectionProvider.builder("order-client")
            .maxConnections(50)
            .pendingAcquireTimeout(Duration.ofSeconds(2))
            .maxIdleTime(Duration.ofSeconds(20))
            .build();
    }

    @Bean
    WebClient orderWebClient(
        WebClient.Builder builder,
        ConnectionProvider orderConnectionProvider
    ) {
        HttpClient httpClient = HttpClient
            .create(orderConnectionProvider)
            .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 2_000)
            .responseTimeout(Duration.ofSeconds(3));

        return builder
            .baseUrl("https://orders.example")
            .clientConnector(
                new ReactorClientHttpConnector(httpClient)
            )
            .build();
    }
}
~~~

ConnectionProvider has its lifecycle managed by Spring and is disposed when the ApplicationContext closes. WebClient can be reused across many requests.

### 10.5. OrderClient.java

~~~java
package com.example.retrydemo;

import java.io.IOException;
import java.net.ConnectException;
import java.net.SocketTimeoutException;
import java.net.UnknownHostException;
import java.time.Duration;
import java.util.Set;
import java.util.concurrent.TimeoutException;

import javax.net.ssl.SSLException;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientRequestException;
import org.springframework.web.reactive.function.client.WebClientResponseException;

import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

public class OrderClient {

    private static final Logger log =
        LoggerFactory.getLogger(OrderClient.class);

    private final WebClient webClient;
    private final Duration perAttemptTimeout;
    private final Duration totalTimeout;
    private final Retry retryPolicy;

    public OrderClient(
        WebClient webClient,
        Duration perAttemptTimeout,
        Duration totalTimeout
    ) {
        this.webClient = webClient;
        this.perAttemptTimeout = perAttemptTimeout;
        this.totalTimeout = totalTimeout;

        this.retryPolicy = Retry
            .backoff(2, Duration.ofMillis(100))
            .maxBackoff(Duration.ofSeconds(1))
            .jitter(0.25)
            .filter(this::isRetryable)
            .doBeforeRetry(signal ->
                log.warn(
                    "Retry order request: attempt={}, error={}",
                    signal.totalRetries() + 1,
                    signal.failure().getClass().getSimpleName()
                )
            );
    }

    public Mono<OrderResponse> create(
        CreateOrderCommand command,
        String idempotencyKey
    ) {
        return Mono.defer(() -> webClient.post()
                .uri("/api/orders")
                .contentType(org.springframework.http.MediaType.APPLICATION_JSON)
                .accept(org.springframework.http.MediaType.APPLICATION_JSON)
                .header(
                    "Idempotency-Key",
                    "\"" + idempotencyKey + "\""
                )
                .bodyValue(command)
                .retrieve()
                .bodyToMono(OrderResponse.class)
                .timeout(perAttemptTimeout)
            )
            .retryWhen(retryPolicy)
            .timeout(totalTimeout);
    }

    private boolean isRetryable(Throwable error) {
        if (error instanceof WebClientResponseException response) {
            int status = response.getStatusCode().value();

            return status == 408
                || status == 502
                || status == 503
                || status == 504;
        }

        if (error instanceof TimeoutException) {
            return true;
        }

        if (error instanceof WebClientRequestException) {
            if (hasCause(error, SSLException.class)
                    || hasCause(error, UnknownHostException.class)) {
                return false;
            }

            return hasCause(error, ConnectException.class)
                || hasCause(error, SocketTimeoutException.class)
                || hasCause(error, IOException.class)
                || hasCauseNamed(
                    error,
                    Set.of(
                        "ConnectTimeoutException",
                        "ReadTimeoutException",
                        "PrematureCloseException"
                    )
                );
        }

        return false;
    }

    private static boolean hasCause(
        Throwable error,
        Class<? extends Throwable> type
    ) {
        for (Throwable current = error;
             current != null;
             current = current.getCause()) {
            if (type.isInstance(current)) {
                return true;
            }
            if (current.getCause() == current) {
                break;
            }
        }
        return false;
    }

    private static boolean hasCauseNamed(
        Throwable error,
        Set<String> names
    ) {
        for (Throwable current = error;
             current != null;
             current = current.getCause()) {
            if (names.contains(current.getClass().getSimpleName())) {
                return true;
            }
            if (current.getCause() == current) {
                break;
            }
        }
        return false;
    }
}
~~~

Key points to understand:

- **Mono.defer** recreates the request for each attempt.
- **bodyValue(command)** reuses the same DTO.
- The same **idempotencyKey** is attached to every attempt.
- A 2-second timeout bounds each attempt.
- Retries at most twice after the initial attempt.
- A 7-second deadline bounds the entire chain of attempts and backoff.
- Only a select group of errors is retried.
- 400, 401, 403, 404, 409, 422, and decode errors are not retried by this classifier.

In production, the classifier must be verified against the actual connector's cause chains. The example above excludes 429 because the client needs to read and obey Retry-After per the server's contract.

### 10.6. OrderClientTest.java

~~~java
package com.example.retrydemo;

import java.io.IOException;
import java.math.BigDecimal;
import java.util.concurrent.TimeUnit;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;

import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.*;

class OrderClientTest {

    private MockWebServer server;
    private OrderClient client;

    @BeforeEach
    void setUp() throws IOException {
        server = new MockWebServer();
        server.start();

        WebClient webClient = WebClient.builder()
            .baseUrl(server.url("/").toString())
            .build();

        client = new OrderClient(
            webClient,
            java.time.Duration.ofSeconds(2),
            java.time.Duration.ofSeconds(7)
        );
    }

    @AfterEach
    void tearDown() throws IOException {
        server.shutdown();
    }

    @Test
    void retries503AndReusesSameIdempotencyKey() throws Exception {
        server.enqueue(
            new MockResponse()
                .setResponseCode(503)
                .setHeader(
                    "Content-Type",
                    MediaType.APPLICATION_JSON_VALUE
                )
                .setBody("{\"code\":\"TEMPORARY_UNAVAILABLE\"}")
        );

        server.enqueue(
            new MockResponse()
                .setResponseCode(201)
                .setHeader(
                    "Content-Type",
                    MediaType.APPLICATION_JSON_VALUE
                )
                .setBody(
                    "{\"orderId\":\"ORD-100\",\"status\":\"created\"}"
                )
        );

        CreateOrderCommand command = new CreateOrderCommand(
            "C-42",
            "BK-01",
            2,
            new BigDecimal("12.50")
        );

        String key = "8e03978e-40d5-43e8-bc93-6894a57f9324";

        StepVerifier.create(client.create(command, key))
            .assertNext(response -> {
                assertEquals("ORD-100", response.orderId());
                assertEquals("created", response.status());
            })
            .verifyComplete();

        RecordedRequest first =
            server.takeRequest(2, TimeUnit.SECONDS);
        RecordedRequest second =
            server.takeRequest(2, TimeUnit.SECONDS);

        assertNotNull(first);
        assertNotNull(second);

        assertEquals("POST", first.getMethod());
        assertEquals("/api/orders", first.getPath());
        assertEquals("POST", second.getMethod());

        String expectedHeader = "\"" + key + "\"";

        assertEquals(
            expectedHeader,
            first.getHeader("Idempotency-Key")
        );
        assertEquals(
            expectedHeader,
            second.getHeader("Idempotency-Key")
        );

        assertEquals(
            first.getBody().readUtf8(),
            second.getBody().readUtf8()
        );

        assertEquals(2, server.getRequestCount());
    }

    @Test
    void doesNotRetryBadRequest() {
        server.enqueue(
            new MockResponse()
                .setResponseCode(400)
                .setHeader(
                    "Content-Type",
                    MediaType.APPLICATION_JSON_VALUE
                )
                .setBody("{\"code\":\"INVALID_ORDER\"}")
        );

        CreateOrderCommand command = new CreateOrderCommand(
            "C-42",
            "BK-01",
            0,
            BigDecimal.ONE
        );

        StepVerifier.create(
                client.create(command, "key-for-invalid-order")
            )
            .expectError(
                WebClientResponseException.BadRequest.class
            )
            .verify();

        assertEquals(1, server.getRequestCount());
    }
}
~~~

The first test enqueues a 503 response followed by a 201 response. It verifies the client retries once, preserves the Idempotency-Key, and resends the identical body.

The second test returns 400 and verifies the request is sent only once. This is an important check to avoid retrying unrecoverable payload errors.

### 10.7. Running tests

Requires JDK 17+ and Maven:

~~~bash
mvn clean test
~~~

MockWebServer receives real HTTP requests sent by WebClient, so tests can verify method, path, headers, body, and request count. No external orders service is needed.

## 11. Generating Idempotency-Key at the business layer

A service can generate a key for a new operation:

~~~java
public Mono<OrderResponse> submitNewOrder(
    CreateOrderCommand command
) {
    String key = UUID.randomUUID().toString();

    return orderClient.create(command, key);
}
~~~

If an upper layer might retry submitNewOrder itself, generating the key inside this method could create a new key on each invocation. In that case, the key should be generated at the boundary where the logical operation starts and passed down through all layers.

Example:

~~~java
String key = commandContext.idempotencyKey();

return orderClient.create(command, key);
~~~

The command context must preserve a stable key when the application recovers or resumes an already-started operation.

### 11.1. Do not generate a new key on each retry

Wrong:

~~~java
Mono.defer(() -> {
    String key = UUID.randomUUID().toString();

    return orderClient.create(command, key);
}).retryWhen(retryPolicy);
~~~

Each retry generates a different key, so the server cannot recognize it as the same operation.

Right:

~~~java
String key = UUID.randomUUID().toString();

Mono.defer(() -> orderClient.create(command, key))
    .retryWhen(retryPolicy);
~~~

The same key is used across all submissions of this operation.

## 12. Observability and operations

A retry policy is hard to operate if logs only say "request failed." Monitor:

- Logical request count.
- Initial attempts and retry attempts.
- Retry rate by dependency and status.
- Timeouts by pool/connect/response/total.
- Per-attempt latency and total latency.
- Retry exhaustion.
- Requests rejected by circuit breakers.
- Idempotency duplicate hits.
- Idempotency key conflicts due to differing payloads.
- Requests stuck in PROCESSING too long.
- Client cancellations and connection resets.

Never log full idempotency keys if keys could be treated as sensitive information. Log a shortened hash or a separate correlation ID instead.

### 12.1. Retry exhaustion

When retries are exhausted, Reactor emits a retry-exhausted error with the last failure attached as cause. You can use Exceptions.isRetryExhausted(...) to distinguish it during error mapping.

Do not turn every retry exhaustion into a generic 500 error if callers need to know which dependency failed. Return a stable error code and log the dependency and attempts.

### 12.2. Deadlines across multiple services

If a request traverses multiple services, propagate the deadline or remaining timeout rather than having each service set an independent long timeout. Total dependency time must fit inside the original request's deadline.

Example:
- Gateway has an 8-second deadline.
- Service A allocates at most 5 seconds to dependency B.
- Service A reserves the remaining time for processing and responding.
- B's retries must fit within the 5-second budget.

Do not let each layer retry 3 times and wait 10 seconds when the original request deadline is only 8 seconds.

## 13. Common mistakes and fixes

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Request waits too long before sending | Waiting on connection pool or DNS | Configure pool acquire and resolver timeouts |
| TCP connect takes too long | Inappropriate connect timeout | Set CONNECT_TIMEOUT_MILLIS |
| Server responds slowly | No response timeout configured | Configure HttpClient.responseTimeout |
| Entire business flow exceeds deadline | Only transport timeouts were set | Set an outermost operation deadline |
| Retrying 400 errors too | Unfiltered retry | Use RetryBackoffSpec.filter |
| Infinite retries | Using Retry.indefinitely | Cap attempts and deadline |
| Multiple clients retrying simultaneously | No jitter | Use exponential backoff and jitter |
| 429 continues hitting rate limits | Ignoring Retry-After | Parse and obey Retry-After |
| POST creates duplicate orders | Retrying after timeout without server deduplication | Use Idempotency-Key and durable result storage |
| Retries change the key | Generating UUID inside each attempt | Generate the key once per logical operation |
| Same key with different payload | Server checks key only, not fingerprint | Store and compare request fingerprint |
| Two same-key requests both cause side effects | Non-atomic check-then-insert | Unique constraint/atomic reservation |
| File upload retry fails | Single-read body stream | Recreate the body source for each attempt |
| Timeout yet server still processes | Client cancel does not roll back remote work | Use idempotency and status queries |
| Retries amplify load | Multiple layers retrying independently | Coordinate retry budgets across the call graph |
| Looking only at final status without attempt count | Missing retry metrics | Record retry count, latency, and dependency |
| Treating 500 as transient in every case | Not distinguishing transient server glitches from code bugs | Pick statuses per API contract |
| Waiting longer than caller's deadline | Unsynchronized timeouts across layers | Propagate remaining deadline |
| Storing idempotency keys too briefly | Keys expire before client retries | Publish and size retention properly |

## 14. Timeout and retry design checklist

Before deploying WebClient to production, confirm:

1. Is the actual connector Reactor Netty, JDK HttpClient, or Jetty?
2. Is pool acquire timeout configured?
3. Is connect timeout configured?
4. Do TLS handshake and DNS have appropriate limits?
5. Is response timeout suited to latency and streaming behavior?
6. Are Mono/Flux-level timeouts used with the right semantics?
7. Does the overall deadline include backoff and retries?
8. Are retries restricted to transient errors?
9. Are 400/401/403/404/409/422 excluded from retries per contract?
10. Does 429 obey Retry-After?
11. Do retries have bounded attempts, backoff, and jitter?
12. Are retry storms and retry amplification avoided?
13. Can the request body be replayed on every attempt?
14. Is the HTTP method idempotent per RFC 9110 and the API contract?
15. Do POST/PATCH operations with side effects carry an Idempotency-Key when needed?
16. Is the key unique per logical operation and preserved across retries?
17. Does the server store fingerprint and result atomically?
18. Are concurrent requests with the same key handled properly?
19. Is there a retention/expiry policy?
20. Are metrics emitted for timeouts, retries, duplicates, and exhaustion?
21. Are there tests for successful retry after 503?
22. Are there tests verifying 400 is not retried?
23. Are there tests verifying key/body are preserved across attempts?
24. Are timeouts and retry budgets tested at integration level?

## 15. Hands-on exercises

**Exercise 1 — Connect timeout:** Configure CONNECT_TIMEOUT_MILLIS and call an unreachable host. Observe the exception and completion time.

**Exercise 2 — Response timeout:** Use MockWebServer to delay response headers. Set responseTimeout and observe the error.

**Exercise 3 — Pool acquire timeout:** Set a small maxConnections, hold connections open, and send extra requests to observe pendingAcquireTimeout.

**Exercise 4 — Mono timeout:** Add timeout to bodyToMono and compare with Reactor Netty's responseTimeout.

**Exercise 5 — Flux idle timeout:** Create a stream emitting data periodically. Test Flux.timeout with different idle intervals and explain how the timer resets after each element.

**Exercise 6 — Retry 503:** Have MockWebServer return 503 then 200. Verify request count and final outcome.

**Exercise 7 — Do not retry 400:** Return 400 and verify the classifier does not resubscribe.

**Exercise 8 — Jitter:** Run multiple clients hitting a transient failure simultaneously. Observe whether retry timestamps are spread out.

**Exercise 9 — Retry-After:** Return 429 with Retry-After. Write a policy waiting the requested duration while respecting the overall deadline.

**Exercise 10 — Idempotency key:** Send POST twice with the same key and same payload. Design the server to return the same result while creating only one order.

**Exercise 11 — Fingerprint conflict:** Send the same key with a different payload. Verify the server rejects it per contract.

**Exercise 12 — Concurrent duplicate:** Send two concurrent requests with the same key. Prove only one request executes the side effect.

**Exercise 13 — Lost response:** Simulate the server saving the order but closing the connection before the client reads the response. Retry with the same key and verify no second order is created.

**Exercise 14 — Replay body:** Send a body using a Flux or file stream. Make the first attempt fail and prove the subsequent attempt creates a fresh body source.

## 16. Key takeaways

Timeouts bound waiting at each layer; retries re-attempt likely transient failures; idempotency protects server state when requests are resent. None of these three mechanisms replaces the other two.

With WebClient, combine Reactor Netty timeouts for pool/connect/response with Mono/Flux timeouts and an overall deadline. Use RetryBackoffSpec with a filter, bounded attempts, exponential backoff, and jitter. Retry only statuses/exceptions verified as transient.

Under RFC 9110, safe methods and PUT/DELETE have idempotent semantics; POST/PATCH are not idempotent by default. When retrying data-creating operations, generate one Idempotency-Key per logical operation, keep the key and payload identical across every attempt, and require the server to store fingerprints and results atomically.

A timeout after sending a request can leave an indeterminate outcome. Design client, server, transactions, outbox, retry budgets, and observability together to recover from failures without creating duplicate side effects.

## 17. References

- Spring Framework Reference — WebClient Configuration and Timeouts: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html
- Spring Framework Reference — WebClient retrieve(): https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html
- Spring Framework Reference — WebClient exchangeToMono/exchangeToFlux: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-exchange.html
- Reactor Netty Reference — HTTP Client Timeout Configuration: https://projectreactor.io/docs/netty/release/reference/http-client.html
- Reactor Core API — RetryBackoffSpec: https://projectreactor.io/docs/core/release/api/reactor/util/retry/RetryBackoffSpec.html
- Reactor Reference Guide — Error Handling and Retry: https://projectreactor.io/docs/core/release/reference/
- RFC 9110 — HTTP Semantics, Safe and Idempotent Methods: https://www.rfc-editor.org/rfc/rfc9110.html
- IETF Internet-Draft — The Idempotency-Key HTTP Header Field, draft-ietf-httpapi-idempotency-key-header-08 (work in progress): https://datatracker.ietf.org/doc/draft-ietf-httpapi-idempotency-key-header/
- MDN — Idempotency-Key header: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Idempotency-Key
- Spring Framework API — WebClient: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/reactive/function/client/WebClient.html
