# Distinguishing Caller Timeouts from Requests Completed on the Target

In HTTP communication between microservices, **a caller-side timeout does not mean the server did not process the request**. The caller only knows that it **did not receive a result in time**. At that moment, the request may not have reached the server, may still be running, may have already committed data while the response was delayed or lost, or may have failed on the server. If the caller immediately resends a write operation without safeguards, the system can create **duplicate orders, double inventory deductions, or repeated payments**.

This lesson belongs to the **Timeouts** chapter in the **SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING** module. Its focus is distinguishing **what the HTTP client observes** from **the actual outcome at the target instance**, in a context where Spring Cloud LoadBalancer routes by service ID, retrieves `ServiceInstance` entries from discovery/health suppliers, and RestClient, WebClient, or OpenFeign executes the HTTP request. Content moves from timelines and consistency models to a simulation lab, idempotency, timeout budgets, retries, and observability.

> Core principle: **“No response received” is an indeterminate state, not proof that “the server rolled back.”** Only proper result verification, idempotency, or an explicit business contract lets the caller decide safely what to do next.

## 1. One Timeout Can Hide Many Different Outcomes

Suppose `order-service` sends `POST /api/orders` to service ID `payment-service`. LoadBalancer picks an instance and the HTTP client sends the request. The caller configures a 1-second response/read timeout.

There are multiple possibilities:

| Situation | Target-side state | What the caller may see | Safe to immediately resend POST? |
|---|---|---|---|
| Could not select an instance | Request never reached target server | Target-selection error | Identify discovery fault; retry depends on context |
| Could not establish connection | Request likely not sent | Connection error/timeout | Classify stage and risk |
| Request arrived; server still processing | May commit after caller times out | Read/response timeout | **Unknown**; must use idempotency/verification |
| Server committed, preparing response | Operation succeeded | Read timeout | **Do not** blindly retry with a new key |
| Server sent response, network lost/delayed it | Operation may have succeeded | Read timeout/reset | Must treat as indeterminate outcome |
| Server failed before commit | No intended state change | Timeout or HTTP error if response arrives | Verify and follow contract |

You cannot distinguish every row in this table solely from a `SocketTimeoutException` or `WebClientRequestException`. The exception name describes **what the client observed**, not whether the target transaction committed.

### Four Concepts Not to Conflate

- **Timeout**: a component's wait time limit was exceeded.
- **Cancellation**: the caller no longer wants the result and may send an abort signal; does not automatically undo work already done.
- **Transaction rollback**: restoring transactional state according to the server's resource manager semantics.
- **Idempotency**: sending the same request multiple times produces no extra side effects beyond the defined contract.

A client closing its connection has no authority to automatically “roll back” a database transaction already committed in another process.

## 2. Timeline: Caller Times Out While Server Already Completed

Suppose an instance receives a POST, writes a record, and commits at around 300 ms, then hits a slow step before returning the response. The caller sets a 1,000 ms timeout:

~~~mermaid
sequenceDiagram
    autonumber
    participant C as order-service (caller)
    participant LB as Spring Cloud LoadBalancer
    participant S as payment-service instance
    participant DB as Database

    C->>LB: POST http://payment-service/api/orders
    LB-->>C: Select instance B
    C->>S: POST /api/orders, Idempotency-Key=abc
    S->>DB: Save order and commit
    DB-->>S: COMMIT OK at ~300 ms
    Note over S: Response is delayed
    Note over C: Response timeout expires at ~1000 ms
    C--xS: Caller stops waiting / closes request
    S-->>C: HTTP 201 at ~3000 ms (caller no longer listening)
    Note over S,DB: Order still exists after caller timeout
~~~

This timeline is constructed for explanation; in reality, ordering may vary. After the caller closes the connection, the late response write may fail. Yet if the DB already committed, failing to send the response **does not undo the earlier commit**.

Written along three time tracks:

~~~text
t=0ms    caller starts POST, LoadBalancer picks target
t=300ms  server commits record #1001
t=1000ms caller times out; UI receives "outcome indeterminate"
t=3000ms server finishes post-commit step / tries to send response
t=3500ms caller GETs status by idempotency key -> finds #1001
~~~

If the caller tells the user “definitely failed” at t=1000ms, the user may click submit again and trigger a second write even though the first succeeded.

## 3. Where Does Spring Cloud LoadBalancer Act?

LoadBalancer selects **where to send the HTTP request**; it does not manage transactions inside the target server:

~~~mermaid
flowchart TD
    A["Caller creates request with service ID"] --> B["ServiceInstanceListSupplier: discovery, cache, health/filter"]
    B --> C{"ServiceInstance available?"}
    C -->|No| D["No HTTP sent to instance"]
    C -->|Yes| E["LoadBalancer picks A or B"]
    E --> F["HTTP transport connects and sends request"]
    F --> G["Server processes, may commit"]
    G --> H{"Did response reach caller before timeout?"}
    H -->|Yes| I["Caller sees HTTP status/response"]
    H -->|No| J["Caller only sees timeout; server outcome indeterminate"]
~~~

Key points:

1. **Discovery and health checks** show which instances qualified at selection time; they do not prove subsequent requests will succeed.
2. **Round Robin, Random, and other policies** decide which instance is tried, not whether the request commits.
3. **HTTP client timeouts** govern connecting and receiving responses; they do not issue a transaction rollback command to a server that already processed the work.
4. **Retrying via LoadBalancer** can pick a **different instance**. If each instance stores idempotency state separately in RAM, retrying to another instance can create duplicate data.
5. A stale instance-list cache can cause connection errors; yet once a request has been sent to a backend, you still must handle indeterminate outcomes if the response is lost.

## 4. Distinguishing Types of Timeouts Along the Path

“Timeout” is not a single clock. One request can pass through multiple independent limits:

| Component / stage | Example limit | Meaning when expired |
|---|---|---|
| Waiting for connection from pool | Pending acquire timeout | Request likely was not sent yet |
| Instance selection / discovery lookup | Application deadline or related config | No target selected yet |
| Opening TCP socket | Connect timeout | TCP connection not established per transport |
| TLS handshake | Handshake timeout | Secure channel not completed |
| Sending request body | Write timeout or application deadline | Unknown how much server received if connection breaks |
| Waiting for response / reading socket | Read/response timeout | Server may still be processing or may have completed |
| Whole business operation | End-to-end deadline | Caller stops waiting due to time budget |
| Gateway/proxy | Upstream timeout | Proxy may return HTTP 504 while it can still send a response |

Read the documentation of your **specific HTTP connector**, because “read timeout” is sometimes an inter-read wait limit rather than the entire HTTP request duration. With streaming/SSE, valid responses may keep connections open very long with periodic heartbeats.

### HTTP 408, 503, and 504 Are Not Equivalent to Caller Timeout Exceptions

- `408 Request Timeout` is an **HTTP status** sent by a server when it waited too long for the client's request per HTTP semantics.
- `503 Service Unavailable` is an **HTTP status** signaling temporary unavailability or overload; it can be generated by a server or gateway.
- `504 Gateway Timeout` is an **HTTP status** a gateway/proxy can return when it fails to receive a timely response from upstream.
- **Client-side timeout** happens when the HTTP client itself stops waiting; in this case **no HTTP status at all** may arrive from the target.

Some proxies log code 499 for “client closed request”; that is not a universal standard HTTP status code and does not prove the server rolled back the request.

## 5. Why Request Cancellation Does Not Guarantee Side-Effect Cancellation

In standard HTTP request-response, client and server are **two independent processes**.

If the caller's wait expires:

- The TCP connection may be closed/reset, or the logical HTTP/2 stream cancelled.
- The server framework may detect client disconnect while writing the response or receive cancellation; there is no guarantee of instant detection inside every blocking operation.
- If the transaction already committed, cancelling the response does not automatically revert data.
- If a task was handed off to a queue or job executor, it may continue even after the original HTTP request ends.
- A further downstream service may have already received and completed a command even though the original caller stopped waiting.

With `WebClient`, cancellation in the reactive pipeline can propagate upstream and free I/O; still, it is **not a distributed transaction rollback**. With synchronous `RestClient` or OpenFeign, the calling thread may stop waiting, yet whether the backend already finished still requires verification.

**A cancel signal means “the caller is no longer waiting,” not “erase all work that occurred.”**

## 6. Lab Example: A Service Records Results Before Delaying the Response

Build a `payment-service` backend with `POST /api/orders`. To demonstrate target-side completion, the backend **stores a receipt right before intentionally sleeping 3 seconds and returning the response**.

Types used in the lab:

~~~java
package demo.payment;

record CreateOrderRequest(String sku, int quantity) {}

record OrderReceipt(long orderId, String sku, int quantity) {}
~~~

Sample Spring MVC application:

~~~java
package demo.payment;

import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class PaymentApplication {

    private final Map<String, OrderReceipt> receiptsByKey =
        new ConcurrentHashMap<>();
    private final AtomicLong sequence = new AtomicLong(1000);

    public static void main(String[] args) {
        SpringApplication.run(PaymentApplication.class, args);
    }

    @PostMapping("/api/orders")
    ResponseEntity<OrderReceipt> createOrder(
            @RequestHeader("Idempotency-Key") String key,
            @RequestBody CreateOrderRequest request)
            throws InterruptedException {

        // State storage simulation only: single JVM, not durable.
        OrderReceipt receipt = receiptsByKey.computeIfAbsent(
            key,
            unused -> new OrderReceipt(
                sequence.incrementAndGet(),
                request.sku(),
                request.quantity()
            )
        );

        System.out.println(
            "SERVER_STORED key=" + key +
            " orderId=" + receipt.orderId()
        );

        // Lab only: simulate a slow-arriving response.
        Thread.sleep(3000);

        return ResponseEntity.status(HttpStatus.CREATED).body(receipt);
    }

    @GetMapping("/api/orders/by-key/{key}")
    ResponseEntity<OrderReceipt> findByKey(@PathVariable String key) {
        return ResponseEntity.of(
            Optional.ofNullable(receiptsByKey.get(key))
        );
    }
}
~~~

**Limitations of the demo code:**

- `ConcurrentHashMap` is **in-memory state**, lost on restart and not shared across instances. It only demonstrates that **a caller timeout does not erase state already written inside that process**.
- `computeIfAbsent` reuses the same receipt for a key within the process; production needs a shared database, unique constraints, transactions, and request-payload matching.
- `Thread.sleep(3000)` simulates a slow response, **never use it** for real business logic. Even if the server thread is interrupted on client disconnect, state saved beforehand still remains.
- The key-lookup endpoint is a lab tool. Production requires authentication/authorization and must forbid probing keys or reading other users' receipts.
- Status `201` is used for simplicity; when replaying a request with an old key, production must specify returning the original response or appropriate status per the idempotency contract.

Suppose you built `payment-service.jar`, run it:

~~~bash
java -jar payment-service.jar --server.port=18081
~~~

First check the backend directly:

~~~bash
curl -i http://localhost:18081/api/orders/by-key/demo-001
~~~

Before any request uses `demo-001`, the demo endpoint returns `404`. That reflects **no receipt in this process's RAM yet**, not universal proof that no transaction exists outside the system.

## 7. Using curl to Prove Client Timeout Does Not Roll Back

To separate Spring Cloud from HTTP fundamentals, send a request directly to the backend with a client timeout shorter than the response delay:

~~~bash
curl -v --max-time 1 \
  -X POST "http://localhost:18081/api/orders" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: demo-001" \
  -d '{"sku":"sku-42","quantity":1}'
~~~

`--max-time 1` sets a 1-second deadline for the entire curl operation. The backend already saved the receipt before sleeping 3 seconds. The caller exits with a timeout error, while server logs print:

~~~text
SERVER_STORED key=demo-001 orderId=1001
~~~

After the timeout, query again:

~~~bash
curl -i http://localhost:18081/api/orders/by-key/demo-001
~~~

Expected result while the process is still running:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"orderId":1001,"sku":"sku-42","quantity":1}
~~~

That means **the client got no response for POST, yet server state changed**.

If you re-run the same POST with **the same key `demo-001`**, within that single JVM `computeIfAbsent` does not create a second receipt for that key. If you switch to **`demo-002`**, the demo server creates a second record—which is precisely the risk when callers retry with a new key.

### Reverse Experiment

Try setting the client timeout longer than the sleep duration, such as `--max-time 5`. Then the caller is likely to receive HTTP `201`, while the target-side data persistence behaves identically.

Try aborting curl before the response arrives. Depending on the server, client transport, and request state, the backend may finish or detect the disconnect. The takeaway is not “it always finishes,” but that **you cannot rely on a disconnect alone to conclude a rollback occurred**.

## 8. Integrating RestClient with Spring Cloud LoadBalancer

To practice within the module's scope, set up a caller `order-service` calling the backend via `http://payment-service` instead of `localhost:18081`.

Gradle dependencies with a compatible Spring Boot/Spring Cloud BOM:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.cloud:spring-cloud-starter-loadbalancer'
}
~~~

For the test environment, configure `SimpleDiscoveryClient`:

~~~yaml
server:
  port: 18090

spring:
  application:
    name: order-service
  cloud:
    discovery:
      client:
        simple:
          instances:
            payment-service:
              - uri: http://localhost:18081
~~~

Use a single instance so lab results are reproducible. When adding another instance, use a **shared durable idempotency store** before testing write retries across multiple instances.

Create a `@LoadBalanced` builder with a read timeout shorter than the backend delay:

~~~java
package demo.caller;

import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
class ClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        SimpleClientHttpRequestFactory factory =
            new SimpleClientHttpRequestFactory();

        factory.setConnectTimeout(1000);
        factory.setReadTimeout(1000);

        return RestClient.builder().requestFactory(factory);
    }

    @Bean
    RestClient paymentRestClient(
            RestClient.Builder loadBalancedRestClientBuilder) {
        return loadBalancedRestClientBuilder
            .baseUrl("http://payment-service")
            .build();
    }
}
~~~

These timeout values are in milliseconds in this request factory API. In production, choose a pooled HTTP transport and configurations compatible with your version. Specifically, `read timeout` depends on the request factory/connector; it is **not equivalent to a single end-to-end deadline**.

### Caller Sends POST and Distinguishes Errors

~~~java
package demo.caller;

import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;

record CreateOrderRequest(String sku, int quantity) {}

record OrderReceipt(long orderId, String sku, int quantity) {}

@Service
class PaymentGateway {

    private final RestClient paymentRestClient;

    PaymentGateway(RestClient paymentRestClient) {
        this.paymentRestClient = paymentRestClient;
    }

    OrderReceipt createOrder(String idempotencyKey) {
        return paymentRestClient.post()
            .uri("/api/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .header("Idempotency-Key", idempotencyKey)
            .body(new CreateOrderRequest("sku-42", 1))
            .retrieve()
            .body(OrderReceipt.class);
    }

    OrderReceipt findByKey(String idempotencyKey) {
        return paymentRestClient.get()
            .uri("/api/orders/by-key/{key}", idempotencyKey)
            .retrieve()
            .body(OrderReceipt.class);
    }
}
~~~

Calling `createOrder("demo-lb-001")` uses service ID `payment-service`, and LoadBalancer picks instance 18081. The backend saves the receipt and sleeps 3 seconds, while RestClient times out after about 1 second waiting for data.

At the application boundary, distinguish transport timeouts from error HTTP responses:

~~~java
try {
    OrderReceipt receipt = gateway.createOrder("demo-lb-001");
    // Success response received: process receipt.
} catch (ResourceAccessException ex) {
    // May be a read/connect timeout or I/O failure.
    // DO NOT conclude createOrder did not execute on the server.
    // Transition to UNKNOWN/PENDING_VERIFICATION state.
} catch (org.springframework.web.client.RestClientResponseException ex) {
    // Error HTTP response received; classify by status/contract.
}
~~~

`ResourceAccessException` is only a common I/O error wrapper in RestClient; **not every pre-HTTP instance-selection failure is guaranteed to belong to this class**. Inspect the exception chain and actual connector rather than relying on a single catch block.

If the caller received `HTTP 201`, it has contractual proof of success. On timeout, call `findByKey("demo-lb-001")` to check, instead of issuing a POST with a new key.

## 9. Essential Facts About Read Timeout and Connect Timeout

### Connect Timeout

Failures during connection setup generally mean the request likely did not reach the target HTTP server. However, if the caller goes through a proxy, a retrying proxy, or a multi-step connector, rely on transport evidence to know exactly how far the request traveled.

### Response/Read Timeout

Failures while **waiting for a response** carry much higher uncertainty. The request may have reached the server, gone to the database, and committed. For write calls, treat this as an **unknown outcome** until verified or protected by an anti-duplication contract.

### Overall Timeout

Even with a 1-second connect timeout and 1-second read timeout, that **does not mean** the call always ends in at most 2 seconds. It can also include connection pool wait, discovery, TLS, redirects, multiple reads, and retries depending on the HTTP stack.

Production therefore needs an **overall deadline budget** derived from SLOs, not just two isolated transport timeout numbers.

## 10. WebClient: Cancelling a Subscription Does Not Prove the Server Rolled Back

With WebClient, errors are emitted via reactive signals rather than thrown synchronously when constructing the `Mono`.

Example WebClient using Reactor Netty:

~~~java
import java.time.Duration;

import io.netty.channel.ChannelOption;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;

@Bean
@LoadBalanced
WebClient.Builder loadBalancedWebClientBuilder() {
    HttpClient httpClient = HttpClient.create()
        .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 1000)
        .responseTimeout(Duration.ofSeconds(1));

    return WebClient.builder()
        .clientConnector(new ReactorClientHttpConnector(httpClient));
}
~~~

Assume `WebClient` is built from this builder with `baseUrl("http://payment-service")`.

~~~java
Mono<OrderReceipt> result = paymentWebClient.post()
    .uri("/api/orders")
    .header("Idempotency-Key", "demo-web-001")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(new CreateOrderRequest("sku-42", 1))
    .retrieve()
    .bodyToMono(OrderReceipt.class);
~~~

The actual request executes when the publisher is **subscribed**, not when the `result` variable is created. On a response timeout, the pipeline emits an error and closes/cancels connection resources. Yet if the backend already wrote data before that moment, the business effect can still persist.

You can add an application-level deadline:

~~~java
Mono<OrderReceipt> limited = result
    .timeout(Duration.ofSeconds(2));
~~~

`Mono.timeout` cancels upstream when the threshold is crossed in the reactive pipeline, yet it also **does not roll back server transactions**. The timeout operator and Reactor Netty's `responseTimeout` measure different things; check connector/version docs to avoid unintended overlap or misdiagnosis on failure.

If the business contract requires certainty after a timeout, implement `GET /api/orders/by-key/{key}` under idempotency rather than doing `onErrorResume(error -> createOrder(newKey))`.

## 11. OpenFeign: readTimeout Also Only Bounds Caller Wait Time

In a project using Spring Cloud OpenFeign:

~~~java
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;

@FeignClient(name = "payment-service")
interface PaymentClient {

    @PostMapping("/api/orders")
    OrderReceipt create(
        @RequestHeader("Idempotency-Key") String key,
        @RequestBody CreateOrderRequest request
    );

    @GetMapping("/api/orders/by-key/{key}")
    OrderReceipt findByKey(@PathVariable("key") String key);
}
~~~

Configure the Feign client by service name:

~~~yaml
spring:
  cloud:
    openfeign:
      client:
        config:
          payment-service:
            connectTimeout: 1000
            readTimeout: 1000
~~~

You need the corresponding dependency and `@EnableFeignClients`, plus Spring Cloud LoadBalancer integrated when selecting instances by service ID.

When `PaymentClient.create(...)` hits a read timeout, classify it as **caller did not receive result in time**, never assuming the server definitely did not create the order. Feign may surface transport/Feign exceptions such as `RetryableException` depending on the case; inspect the cause and actual `Retryer`/`ErrorDecoder` config.

**OpenFeign, RestClient, and WebClient differ in APIs and error reporting; no client guarantees exactly-once write execution through timeouts alone.**

## 12. How to Verify State After a Timeout

A common pattern generates an **idempotency key** at the start of a business operation and preserves it across every attempt for that operation.

~~~mermaid
flowchart TD
    A["Caller sends POST with key K"] --> B{"Success response?"}
    B -->|Yes| C["Save result / order ID"]
    B -->|No, timeout| D["Mark outcome UNKNOWN"]
    D --> E["GET status by K or query result"]
    E --> F{"Result available?"}
    F -->|COMPLETED| C
    F -->|PENDING| G["Wait/backoff and check again"]
    G --> E
    F -->|NOT_FOUND| H["Consider retrying with same key K"]
    H --> A
    F -->|Cannot verify| I["Keep UNKNOWN state / reconcile"]
~~~

Be careful on the `NOT_FOUND` branch: **not finding a record at query time does not prove the first operation was never received or committed**. The server may still be processing, replication may lag, or the idempotency record may not have been written yet. When retrying, always reuse **the exact same key K** and ensure atomic server handling so two competing requests cannot produce two results.

### States to Keep Distinct

| Contract status | Meaning |
|---|---|
| `PENDING` | Accepted, currently processing |
| `COMPLETED` | Task finished and result is readable |
| `FAILED` | Task failed per contract—not merely inferred from a timeout |
| `UNKNOWN` (caller-side) | Caller has not yet verified the outcome |
| `NOT_FOUND` | No record found at queried source; **insufficient** to prove the request was never received |

For long-running operations, the API can return `202 Accepted` with an operation ID for client polling, or deliver results via callbacks/events. `202` only means accepted for processing, not that work completed successfully.

## 13. Idempotency Key: True Protection Against Duplicate Execution

An `Idempotency-Key` uniquely identifies **one business intent**, such as “create order for cart X.” The caller must generate the key before the first attempt and reuse **the same key** when retrying or polling status.

~~~text
POST key=order-7f2a -> yields orderId=1001
POST key=order-7f2a -> does not create orderId=1002
POST key=order-7f2a -> returns recorded result or processing status
~~~

Adding a header alone is not enough. The server must implement a consistent protocol covering at least:

1. **Scope keys properly**: e.g., tenant/account + idempotency key; never share a key namespace across unrelated customers as one operation.
2. **Bind request content**: store a request fingerprint/hash; if the same key arrives with a different body, return a conflict error like `409` per contract.
3. **Ensure atomicity**: use unique constraints, transactions, or durable synchronization; two concurrent requests with the same key must never create two records.
4. **Persist PENDING/COMPLETED/FAILED state and results** long enough for caller retries or lookups.
5. **Return consistent responses**: replays should return the original operation/result or progress status without re-executing committed side effects.
6. **Use a shared store across replicas**: if instances A and B are independent, a key in A's RAM does not protect a retry routed to B.
7. **Expire keys methodically**: idempotency TTL must cover the caller's retry/reconciliation window, not be overly short.
8. **Enforce access control on lookups**: callers may only inspect transaction status they own.

Simple transactional model:

~~~sql
-- PostgreSQL illustration; not a full production schema.
CREATE TABLE idempotency_records (
    tenant_id VARCHAR(100) NOT NULL,
    request_key VARCHAR(200) NOT NULL,
    request_hash VARCHAR(128) NOT NULL,
    status VARCHAR(32) NOT NULL,
    order_id BIGINT,
    PRIMARY KEY (tenant_id, request_key)
);
~~~

An order worker can insert the unique-key record inside the same transaction as the order insert, or manage pending state in a dedicated flow. When an existing key is encountered, check the hash and status instead of creating a new order.

**Even a unique key is insufficient if external side effects happen before saving the key.** For payment gateways, message brokers, or downstream services outside a shared transaction, use the outbox pattern, sagas, downstream-recognized keys, or dedicated reconciliation.

### Idempotent HTTP Methods Alone Do Not Prevent Business Duplicates

In HTTP semantics, GET/PUT/DELETE have specific idempotency rules, whereas POST is not idempotent by default. In reality, behavior depends on the backend: a poorly designed GET can mutate state; a PUT might emit side-effect logs/notifications; DELETE might trigger external side effects. Rely on **the contract and server implementation**, not just the HTTP verb.

## 14. Retrying After Timeout: Re-Selecting Instances Can Increase Risk

Spring Cloud LoadBalancer can pick a different instance for a retry depending on config and policy. For example:

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant LB as LoadBalancer
    participant A as Instance A
    participant DB as Shared DB
    participant B as Instance B

    C->>LB: POST key=K, attempt 1
    LB-->>C: Instance A
    C->>A: POST key=K
    A->>DB: Commit orderId=1001
    Note over C: Timeout before receiving response
    C->>LB: Retry POST key=K, attempt 2
    LB-->>C: Instance B
    C->>B: POST key=K
    B->>DB: Look up unique key K
    DB-->>B: Already COMPLETED, orderId=1001
    B-->>C: Result of K, no new order created
~~~

If A and B use **two independent in-memory idempotency stores**, B will not see K and will create a duplicate order. Therefore, deduplication must hold across **the full scope of instances LoadBalancer can choose**, not just one JVM.

### When Is Retrying Sensible?

- Retry **read-only requests** on transient failures when the deadline budget allows, after verifying real side effects.
- Retry **write requests** only when the contract permits, using the exact same key and accurate server-side idempotency.
- Cap attempts, use exponential backoff/jitter where appropriate, and honor an overall deadline.
- Do not keep retrying when all instances are overloaded or a circuit breaker is open.
- Never stack duplicate retries across the HTTP client, Spring Cloud LoadBalancer, gateway, and service mesh.
- Track attempt numbers and chosen instances to spot business requests generating multiple HTTP attempts.

If each request allows up to three attempts, a system receiving 100 business ops/sec can generate up to 300 HTTP attempts/sec when attempts fail. Amplifying load onto an already struggling dependency produces even more timeouts.

## 15. Splitting Timeout Budgets from the Business Deadline

Suppose a caller endpoint must reply within **4 seconds**. You cannot give every downstream a 4-second read timeout plus three retries: total duration would far exceed the deadline.

An illustrative budget plan:

| Stage | Reference budget |
|---|---:|
| Authentication and input handling | 200 ms |
| Instance lookup / pool acquisition / connect | 300 ms |
| First HTTP attempt | 1,200 ms |
| Backoff before retry | 200 ms |
| Second HTTP attempt | 1,200 ms |
| Persist status / write response | 400 ms |
| Reserve for scheduling / variance | 500 ms |
| **Total** | **4,000 ms** |

These intervals illustrate **budget allocation**, not a rigid formula for every client. Measure p95/p99 and real call paths: one attempt includes multiple phases, request factory timeouts have specific semantics, and multiple downstream calls may run sequentially or in parallel.

Good practices:

- Establish one **overall deadline** at the business boundary.
- For each attempt, use `remaining budget` to choose wait limits rather than letting subsequent attempts spend the full original timeout.
- If insufficient time remains to verify outcome after a write timeout, return PENDING/UNKNOWN with an operation ID or hand off to reconciliation.
- Never block indefinitely just to “be sure,” as thread and connection pools will exhaust.

## 16. When Is a Result Considered “Completed” on the Server?

The phrase “the server completed” also needs exact definition:

| Server milestone | Considered business-complete? |
|---|---|
| Controller starts receiving request | Not yet |
| Server parsed/validated input | Not yet |
| Enqueued a background job | Only “accepted”; job may not have executed |
| Database transaction committed successfully | Side effects within transaction scope persisted |
| Downstream payment called and confirmed | May be partially complete; depends on contract and reconciliation |
| Wrote HTTP response to socket | Does not prove caller received it |
| Caller received HTTP 2xx and decoded response | Caller has contractual proof; still honor business semantics |

Even a database commit does not guarantee the **entire inter-service workflow** finished. An order row may exist in the DB while inventory deduction or event publishing is still pending. Multi-step workflows need explicit operation states, outbox/sagas, or event-driven reconciliation.

Never treat `200 OK` from a health endpoint as proof a write operation finished; health checks measure point-in-time availability, not specific transactions.

## 17. Observing from Both Sides to Determine Outcomes

When investigating production timeouts, correlate data across **caller + LoadBalancer + target server + database/dependencies** by the same operation ID or idempotency key.

| Observation point | What to measure/log? |
|---|---|
| Caller | request ID, key, attempt, timeout type, elapsed time, remaining deadline |
| LoadBalancer | service ID, selected instance, candidate count, reason if none chosen |
| HTTP transport | pool wait, connect time, TLS, request send time, time-to-first-byte, response read |
| Server | request received, handler started, side effect started, commit success/failure, response write |
| Database | transaction/unique key, order ID, commit timestamp, conflict/duplicate detection |
| Retry/resilience | attempts, backoff, instance switches, circuit breaker state |
| Status API / reconciliation | operation state and final completion timestamp |

Target log example:

~~~text
caller: POST operation=op-42 key=K attempt=1 instance=A
server-A: received operation=op-42 key=K
server-A: committed operation=op-42 orderId=1001
caller: read_timeout operation=op-42 elapsed_ms=1000
caller: status_query operation=op-42 key=K
server-A: status_query key=K -> COMPLETED orderId=1001
caller: reconciled operation=op-42 -> SUCCESS
~~~

This format is illustrative, not a Spring Cloud default. In real systems, never log full payment tokens, card data, cookies, Authorization headers, or PII. Mask or hash sensitive keys when observing.

### Caution When Comparing Timestamps Across Machines

If caller and server clocks drift, do not conclude “committed before or after timeout” solely by subtracting timestamps across machines. Use consistent distributed trace contexts, operation IDs, event ordering, monotonic clocks for local elapsed durations, and clock synchronization to aid analysis.

If the server finished processing while a proxy already returned 504, backend logs may show success at one layer and gateway logs may show timeout at another. Those two events **do not contradict**: they measure outcomes at two different boundaries.

## 18. Indeterminate-Outcome Testing Checklist

Test suites should deliberately inject failure windows rather than only calling healthy APIs.

| Scenario | What to verify |
|---|---|
| Backend commits fast, response slower than timeout | Caller times out, but key lookup finds existing result |
| Backend crashes before processing | No result; retry per contract |
| Backend crashes after commit, before response | Caller sees unknown; retry with same key creates no duplicate |
| Network drops mid-request-body upload | System does not falsely assume request wasn't received |
| Gateway returns 504 | Backend status is reconciled rather than assumed rolled back |
| Retry with same key hits different instance | Shared idempotency store prevents duplicate side effects |
| Retry with same key but different body | Server rejects conflict per contract |
| Status API returns PENDING | Caller does not mint a new key; bounded poll/backoff |
| Status API temporarily errors | Caller keeps UNKNOWN and has a reconciliation path |
| Read timeout too long | Threads/pools are not held beyond SLO |
| Read timeout too short | System does not trigger floods of false retries |
| Two overlapping POST attempts | Unique constraint/transaction guarantees one outcome |
| Cache/discovery contains dead instance | Separate selection/connect failures from accepted transactions |
| HTTP 2xx received but decode fails | Do not retry POST with a new key solely due to client decode error |

Specifically test **the same idempotency key hitting two replicas concurrently**. The lab's `ConcurrentHashMap` code only proves single-JVM behavior; it is **not** a distributed idempotency test.

### Reproducible Lab Checks

1. Run the sample backend on `localhost:18081`.
2. Send `POST` with `--max-time 1`, key `demo-001`; confirm curl reports timeout.
3. Verify `SERVER_STORED` logs and `GET /api/orders/by-key/demo-001` show the same order ID.
4. Resend the same key; confirm the ID stays unchanged in that process.
5. Send a different key; observe a new record created, illustrating why retrying with a new key is dangerous.
6. Use the `@LoadBalanced` RestClient caller with a 1-second read timeout; verify the same behavior via service ID.
7. Try WebClient or OpenFeign with equivalent timeouts, recording exact exception/error signal types instead of assuming identical behavior to RestClient.
8. When scaling to two instances, replace the demo map with shared durable storage before drawing conclusions about idempotency.

## 19. Common Design Mistakes

- Returning “order creation failed” to the user **merely because the caller timed out**, when the backend may have committed.
- Cancelling a WebClient publisher or closing TCP and assuming the server transaction automatically rolled back.
- Retrying a POST with a **new idempotency key** for the same business intent.
- Storing keys only in one instance's RAM while LoadBalancer can route retries to another instance.
- Checking only HTTP status codes, ignoring failures where the server succeeded but the response was lost.
- Treating `NOT_FOUND` on a lagging read replica as proof the initial request never existed.
- Claiming exactly-once delivery just because the client retries once or the server uses a non-durable map.
- Setting read timeout equal to the business deadline while still allowing multiple retries.
- Unbounded retries when a dependency is overloaded, causing retry storms.
- Confusing an HTTP 504 from a gateway with a backend transaction rollback.
- Treating `ResourceAccessException` or `RetryableException` as business proof of “not executed.”
- Missing correlation IDs/idempotency keys, making it impossible to link caller logs to backend commits.
- Returning receipts from status endpoints without authentication or authorization checks.
- Reusing the same key for two different payloads without detecting conflicts.
- Ignoring side effects outside the DB—such as payments, messages, or emails—when designing idempotency.

## 20. Summary

When a **caller times out**, the only certainty is that the caller **did not get a result in time**. You must never infer that the server never received the request, never committed, rolled back, or stopped processing. For reads, you can retry cautiously within a deadline; for writes, you need **an idempotency key reused across all attempts**, a **shared durable state store**, the ability to **query/reconcile outcomes**, and explicit handling of **UNKNOWN** states.

Spring Cloud LoadBalancer helps find and select a `ServiceInstance` using discovery, caches, health checks, and routing policies; **it does not govern server-side transactions**. RestClient, WebClient, and OpenFeign provide different timeout mechanisms, yet none turns a timeout into a guarantee of “not executed.” Stable inter-service communication requires combining **timeout budgets, bounded retries, idempotency, observability, and status-verification contracts**, especially when requests have side effects.
