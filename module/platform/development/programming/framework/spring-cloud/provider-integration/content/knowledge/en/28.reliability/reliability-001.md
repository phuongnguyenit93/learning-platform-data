# Setting Operation Deadlines and Per-Call Timeouts

A Spring Boot request might sequentially call a database, Azure Blob Storage, and Service Bus. If each client is configured with its own timeout without an overall limit, the total processing time can be much longer than the caller is willing to wait. Conversely, setting overly short timeouts on every connection can cause requests to fail even when a service is only experiencing temporary latency.

It is necessary to distinguish an **operation deadline** from a **per-call timeout**. A deadline defines the latest point in time by which a business operation is allowed to finish; a per-call timeout limits the time allotted to a single step such as acquiring a connection, sending an HTTP request, querying a database, or sending a message. Child timeouts must stay within the remaining budget of the parent operation.

This lesson belongs to the **Reliability** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module: practicing the integration of Spring Boot with managed services from AWS, Azure, and Google Cloud via the corresponding Spring Cloud libraries; focusing on identity/permissions, storage, messaging, data, secrets, integration testing, and evaluating differences across cloud providers.

## 1. Learning Objectives

After this lesson, learners can:

1. Distinguish **deadline**, **overall request timeout**, **per-call timeout**, **connect timeout**, **response/read timeout**, and **idle timeout**.
2. Allocate a time budget across multiple sequential or parallel steps in Spring Boot.
3. Propagate remaining time to HTTP clients, Azure SDKs, databases, and messaging clients.
4. Design retries/backoff so they do not exceed the deadline, avoid retry storms, and handle non-idempotent operations.
5. Understand the difference between timeout and cancellation, especially when using synchronous SDKs, CompletableFuture, or Reactor.
6. Test timeouts using fake clocks, mock clients, test servers, and cloud test environments.
7. Observe latency, timeouts, retries, and deadline exhaustion without logging sensitive data.

## 2. Deadline and Timeout Are Not the Same Concept

A **deadline** is the final point in time by which an operation must complete. A **timeout** is a duration limit on a specific activity or an entire request. A single deadline can encompass multiple child timeouts as well as time spent waiting in queues.

| Concept | Question Answered | Example |
| --- | --- | --- |
| **Operation deadline** | By when at the latest must this business operation finish? | Order creation API has a 2.5-second budget |
| **Overall request timeout** | How long at most does the caller or ingress wait for the request? | HTTP client waits up to 3 seconds for a response |
| **Per-call timeout** | How long is a single downstream call allowed to take? | Blob call takes at most 800 ms within the remaining budget |
| **Connect timeout** | How long does the client wait to establish a connection? | TCP/TLS or proxy connection takes at most 300 ms |
| **Response/read timeout** | How long at most does the client wait for a response or subsequent read data per transport semantics? | Waiting for a response from the HTTP server up to 900 ms |
| **Connection-pool acquisition timeout** | How long at most to wait for an available connection from the pool? | Waiting on the pool up to 100 ms |
| **Idle timeout** | After how long of inactivity is a connection closed? | Proxy closes an idle tunnel after a period of time |
| **Queue/lock timeout** | How long can a task/message wait or be held? | Service Bus message lock or receive wait duration |

Exact names and semantics depend on the client/transport. For example, the **response timeout** of an HTTP provider may measure the wait time for a response/read per stage, not necessarily bounding the entire operation from start until the body is completely read.

### Example: Individual Timeouts Can Accumulate

Suppose an API makes three sequential calls:

~~~text
User request
    ├── Database query: up to 2 seconds
    ├── Blob upload: up to 2 seconds
    └── Service Bus send: up to 2 seconds
~~~

If each call uses a 2-second timeout without a shared deadline, the total time can exceed 6 seconds, not counting validation, serialization, token acquisition, connection-pool waiting, and retries.

If the user only waits 3 seconds, the request may be terminated by the client or gateway while the server continues uploading the Blob or sending the message. That creates an ambiguous state: **the caller sees a timeout, yet side effects may have already occurred**.

## 3. Time Budget of an Operation

An operation deadline should include all time controlled by the system:

- Waiting for admission control, thread pool, scheduler, or connection pool.
- Authentication and token acquisition if needed.
- DNS, proxy, TCP, TLS, and connecting to the service.
- Sending the request, waiting for the response, reading the body, and processing the result.
- Retries, backoff, and wait time between attempts.
- Writing to the database, message settlement, cleanup, and building the response.
- A reserve buffer to return a controlled error or complete cleanup tasks.

### Example of Allocating a 2,500 ms Budget

| Stage | Illustrative Budget | Notes |
| --- | ---: | --- |
| Request authentication, validation, and admission | 150 ms | Includes wait time before business logic |
| Database query | 450 ms | Includes connection-pool wait if the operation needs a connection |
| Blob upload | 850 ms | May involve multiple HTTP requests/chunks per the SDK |
| Service Bus send | 400 ms | Per the messaging client timeout |
| Retry/backoff reserve | 350 ms | Used only while deadline remains and errors are retryable |
| Completion, serialization, and returning response | 300 ms | Avoid exhausting the budget before returning the result |
| **Total** | **2,500 ms** | Operation deadline |

These numbers are only design examples. Actual budgets must be based on SLOs, latency distributions, payload size, deployment region, service limits, and business requirements.

**Do not split timeouts equally across all dependencies.** A cache query might only need a few tens of milliseconds; uploading a large file may take longer. Allocate according to criticality and service characteristics.

## 4. Parent Deadline and Child Timeouts

When a request calls multiple dependencies, each child call must use the **remaining time**, rather than starting a new timeout independent of the original deadline.

~~~mermaid
flowchart TD
    A[Inbound request: deadline 2500 ms] --> B[Validation: 150 ms]
    B --> C[Database call: max 450 ms]
    C --> D[Blob call: max min 850 ms, remaining]
    D --> E[Service Bus call: max min 400 ms, remaining]
    E --> F[Response and cleanup]
    A -. deadline expires at any step .-> X[Stop starting new work / return timeout error]
~~~

Rule:

\[
T_{child} = \min(T_{configured}, T_{remaining})
\]

Where:

- (T_{configured}) is the maximum configured timeout for the dependency.
- (T_{remaining}) is the remaining budget of the operation.
- (T_{child}) must not exceed the remaining time.

For example, Blob is configured for a maximum of 850 ms, but the database has already consumed 1,900 ms out of a 2,500 ms budget. Only 600 ms remains; the Blob call must use at most 600 ms or be skipped if the business operation can no longer complete safely.

### A Deadline Is an Upper Bound, Not a Target to Consume Fully

If an operation finishes early, return the result immediately. There is no need to wait out the full budget. If the remaining time is too small for a call to have a chance of completing or cleaning up, you can refuse to start a new call and return a controlled error.

## 5. Measuring Time in the JVM Using a Monotonic Clock

Within a single JVM process, use **System.nanoTime()** to measure durations and relative deadlines. Do not use **System.currentTimeMillis()** to compute elapsed time because the system clock can be synchronized or adjusted.

- **Instant/UTC wall clock** is suitable for recording timestamps and exchanging points in time across systems.
- **System.nanoTime()** is suitable for measuring elapsed time within a single process.
- A nanoTime value is not a calendar timestamp and must not be sent to another machine.

### Minimal Deadline Class

~~~java
import java.time.Duration;

public final class Deadline {

    private final long expiresAtNanos;

    private Deadline(long expiresAtNanos) {
        this.expiresAtNanos = expiresAtNanos;
    }

    public static Deadline after(Duration budget) {
        if (budget == null || budget.isNegative() || budget.isZero()) {
            throw new IllegalArgumentException(
                    "Deadline budget must be positive");
        }

        long now = System.nanoTime();
        long durationNanos = budget.toNanos();
        return new Deadline(now + durationNanos);
    }

    public Duration remaining() {
        long remainingNanos = expiresAtNanos - System.nanoTime();
        return Duration.ofNanos(Math.max(0L, remainingNanos));
    }

    public boolean isExpired() {
        return remaining().isZero();
    }

    public Duration cap(Duration configuredTimeout) {
        if (configuredTimeout == null ||
                configuredTimeout.isNegative() ||
                configuredTimeout.isZero()) {
            throw new IllegalArgumentException(
                    "Configured timeout must be positive");
        }

        Duration remaining = remaining();
        if (remaining.isZero()) {
            return Duration.ZERO;
        }

        return configuredTimeout.compareTo(remaining) < 0
                ? configuredTimeout
                : remaining;
    }
}
~~~

This is an illustrative helper for short time budgets within a single process. Production applications should add overflow checks when accepting very large durations, context propagation rules, metrics, and handling for expired deadlines. Do not persist expiresAtNanos in a database or transmit it over the network.

### Using Deadline for Each Call

~~~java
import java.time.Duration;
import java.util.concurrent.TimeoutException;

@FunctionalInterface
interface TimedCall<T> {
    T execute(Duration timeout) throws Exception;
}

public final class DeadlineCalls {

    private DeadlineCalls() {}

    public static <T> T invoke(
            Deadline deadline,
            Duration configuredTimeout,
            TimedCall<T> call) throws Exception {

        Duration timeout = deadline.cap(configuredTimeout);
        if (timeout.isZero()) {
            throw new TimeoutException("Operation deadline exceeded");
        }

        // The adapter must actually apply the received timeout
        // to the client/driver; passing Duration alone does not cancel I/O.
        return call.execute(timeout);
    }
}
~~~

Usage example:

~~~java
Deadline deadline = Deadline.after(Duration.ofMillis(2500));

String result = DeadlineCalls.invoke(
        deadline,
        Duration.ofMillis(850),
        timeout -> blobGateway.upload(document, timeout));
~~~

**Important condition:** blobGateway.upload must pass the timeout to the HTTP client/SDK or a mechanism that actually bounds the operation. If the adapter ignores the timeout parameter, the helper only checks the budget before calling; it cannot enforce a timeout on an in-flight I/O call.

## 6. Propagating Deadlines Across Multiple Services

In a multi-service architecture, deadlines need to be propagated in a way that can be interpreted at each hop.

There are two common approaches:

- **Absolute deadline:** pass the final UTC timestamp, such as an internal header X-Request-Deadline. The receiving service computes the remaining time from its own UTC clock, accounting for clock skew.
- **Remaining timeout/budget:** pass the remaining duration, such as X-Request-Timeout-Ms. The receiving service initializes a local deadline from this budget.

Some protocols like **gRPC** have their own built-in deadline/timeout mechanism. For HTTP REST, custom headers must have a clear contract between services; headers arriving from the public Internet should not be blindly trusted.

### Rules When Propagating Deadlines

1. Create the deadline at the first trusted boundary, such as an API gateway or the ingress service receiving the request.
2. If the caller sends a timeout, apply a **service-defined maximum cap**; do not let callers request minutes if the API only allows a few seconds.
3. When calling a downstream service, pass the **remaining budget** after time already consumed.
4. A downstream service must not extend the parent deadline.
5. Reserve a buffer for response handling, settlement, and cleanup.
6. When the deadline expires, stop starting new work and cancel in-flight work if the client supports safe cancellation.

Do not send System.nanoTime() over the network. Each process has its own monotonic clock. If passing an absolute UTC timestamp, account for clock skew; if passing a remaining duration, clearly specify the unit, bounds, and how negative/invalid values are handled.

### Multi-Service Flow Example

~~~mermaid
sequenceDiagram
    participant U as API Gateway
    participant O as Orders API
    participant D as Database
    participant B as Blob service
    participant M as Service Bus
    U->>O: Request + budget 2500 ms
    O->>D: Query, timeout per remaining
    D-->>O: Result
    O->>B: Upload, timeout per remaining
    B-->>O: Blob reference
    O->>M: Send, timeout per remaining
    M-->>O: Accepted
    O-->>U: Response before deadline
~~~

If the database consumes 1,200 ms, Blob and Service Bus must share only the remaining budget. Each downstream service can also enforce its own deadline for internal work, but must not exceed the deadline passed down by a trusted caller.

## 7. Distinguishing Timeouts in HTTP Clients

An HTTP request typically goes through multiple stages:

~~~text
Wait for connection pool
    → DNS
    → TCP connect
    → TLS handshake
    → send request
    → wait for response headers
    → read response body
    → process result
~~~

Not every HTTP client has a single timeout covering all stages. You must check the exact transport semantics.

| Timeout | Effect | Configuration Example |
| --- | --- | --- |
| Pool acquisition | Waiting for an available connection | Connection-request timeout |
| Connect | Establishing a connection to the host/proxy | Connect timeout |
| TLS handshake | Completing the TLS handshake | May fall under connect or a dedicated transport handshake timeout |
| Response/read | Waiting for a response or readable data | Response/read timeout |
| Whole call | From start until the response finishes | Request/call timeout if supported by the client |
| Business deadline | Includes queuing, multiple calls, and business processing | Application deadline context |

### Spring RestClient Example with Connect and Read Timeouts

With Spring Framework supporting **RestClient**, you can configure a request factory. For example, using **SimpleClientHttpRequestFactory**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
public class PartnerHttpConfiguration {

    @Bean
    RestClient partnerRestClient() {
        SimpleClientHttpRequestFactory requestFactory =
                new SimpleClientHttpRequestFactory();

        requestFactory.setConnectTimeout(300);
        requestFactory.setReadTimeout(900);

        return RestClient.builder()
                .requestFactory(requestFactory)
                .build();
    }
}
~~~

In this example:

- The 300 ms connect timeout limits connection establishment time according to the request factory's capabilities.
- The 900 ms read timeout limits read wait time according to the implementation's semantics.
- The two values **do not automatically form a 1,200 ms operation deadline**.
- Pool wait, DNS, TLS, and processing time may behave differently depending on the request factory/JDK.

If you need a connection pool and finer control, you can use Apache HttpComponents or another HTTP provider, but you must configure **connection acquisition**, **connect**, **response**, and **overall deadline** according to that provider's API.

### Timeouts in WebClient/Reactor Netty

For reactive applications, you can configure timeouts on the connector and bound the publisher at the operation level:

~~~java
import java.time.Duration;
import io.netty.channel.ChannelOption;
import reactor.netty.http.client.HttpClient;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
public class PartnerWebClientConfiguration {

    @Bean
    WebClient partnerWebClient() {
        HttpClient httpClient = HttpClient.create()
                .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 300)
                .responseTimeout(Duration.ofMillis(900));

        return WebClient.builder()
                .clientConnector(
                        new ReactorClientHttpConnector(httpClient))
                .build();
    }
}
~~~

An overall operation bound can be placed on the publisher:

~~~java
Mono<PartnerResponse> response = webClient.get()
        .uri("/status")
        .retrieve()
        .bodyToMono(PartnerResponse.class)
        .timeout(Duration.ofMillis(1200));
~~~

**Mono.timeout** limits how long the publisher has to complete after subscription and emits a timeout/cancel signal according to Reactor semantics. Ensure subscription starts at the right point for measuring the deadline and that cancellation is actually handled by the connector/remote client. It cannot undo a side effect that has already occurred on the server.

## 8. Timeouts with Azure SDK for Java

Azure SDK for Java has multiple builders and transports; you should not treat a Blob client's timeout as a universal timeout for every Azure service.

For HTTP-based SDKs, distinguish:

- **HTTP transport timeout:** connect, response/read, write, and pool settings depending on the provider.
- **SDK retry policy:** retry count, backoff, retryable status/errors, and service-specific limits.
- **Service operation semantics:** upload/download may involve multiple requests or chunks; total operation time is not just a single HTTP exchange.
- **Credential timeout:** Azure Identity may need a separate connection to acquire tokens; configuring transport for Blob does not necessarily configure token-acquisition transport.
- **Application deadline:** encompasses token acquisition, requests/chunks, retries, and post-SDK processing.

### Example of Configuring HTTP Transport for Blob

With the Azure Core Netty provider, you can build an HTTP client with connect/response timeouts and attach it to **BlobServiceClientBuilder**. Specific APIs should be checked against the azure-core-http-netty version managed by the BOM.

~~~java
import com.azure.core.http.HttpClient;
import com.azure.core.http.netty.NettyAsyncHttpClientBuilder;
import com.azure.core.credential.TokenCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;
import java.time.Duration;

TokenCredential credential =
        new DefaultAzureCredentialBuilder().build();

HttpClient httpClient = new NettyAsyncHttpClientBuilder()
        .connectTimeout(Duration.ofMillis(300))
        .responseTimeout(Duration.ofMillis(900))
        .build();

BlobServiceClient blobClient = new BlobServiceClientBuilder()
        .endpoint(blobEndpoint)
        .credential(credential)
        .httpClient(httpClient)
        .buildClient();
~~~

This example illustrates timeouts for the **HTTP transport**. It does not guarantee an entire large upload completes in 900 ms: the upload may be split into multiple requests/chunks, retries, and data processing. Nor does it guarantee token acquisition uses the same transport.

### Retry Options Do Not Replace a Deadline

An SDK can automatically retry transient errors. If each attempt is allowed 900 ms and the SDK retries multiple times, the total time can exceed the operation budget. Therefore, you should:

- Choose retry counts/backoff aligned with SLOs.
- Check the ability to bound individual attempt times in the SDK/service.
- Enforce an operation deadline at the application layer and avoid starting new attempts once the budget is exhausted.
- Manage cancellation when supported by the SDK.
- Never loop indefinitely on 401/403 or permanent configuration errors.

Some Azure services have **separate retry options** and different semantics. For instance, the Storage SDK has retry options for Storage requests; the Service Bus SDK has retry options on the messaging client. Do not configure one generic retry policy and assume every SDK applies it identically.

### Large Uploads and Multiple Requests

A single business upload call may consist of:

1. Initialization / precondition checks.
2. Uploading blocks/chunks.
3. Retrying individual requests.
4. Committing the block list.
5. Processing the response and returning the result.

Therefore, even if each HTTP request has a 900 ms response timeout, the upload operation can take longer than 900 ms. Set an overall operation limit at the appropriate layer and tune chunk size/concurrency based on file size, bandwidth, and service limits.

## 9. Timeouts for Databases and Connection Pools

Database timeouts typically have multiple independent layers:

| Type | Example | If Unbounded |
| --- | --- | --- |
| Connection pool acquisition | Hikari connectionTimeout | Threads wait indefinitely for a connection when the pool is exhausted |
| Connection establishment | JDBC driver connect/login timeout | Connecting to DB hangs due to network issues |
| Query/statement timeout | JDBC Statement.setQueryTimeout or driver-specific option | Long-running queries monopolize connections |
| Transaction timeout | Spring transaction timeout | Transactions hold locks/connections for too long |
| Socket/read timeout | Driver network timeout | Waiting for data from DB without a proper bound |

### HikariCP and JDBC Example

An illustrative configuration:

~~~yaml
spring:
  datasource:
    hikari:
      connection-timeout: 500
      validation-timeout: 300
~~~

These are timeouts for acquiring a connection and validating a connection in HikariCP; they are **not query timeouts**.

With JDBC, you can bound a statement:

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement =
             connection.prepareStatement(
                     "select status from orders where id = ?")) {

    statement.setLong(1, orderId);
    statement.setQueryTimeout(1);

    try (ResultSet resultSet = statement.executeQuery()) {
        // Process result
    }
}
~~~

setQueryTimeout uses seconds in the JDBC API; drivers/databases may differ in how they cancel a query. You should verify query timeout, network timeout, and transaction behavior for your specific driver.

### Transaction Timeouts and External Calls

Do not keep a database transaction open while waiting on slow Blob uploads or Service Bus sends unless necessary. A long-running transaction can hold locks/connections, increase contention, and degrade system resilience.

Consider:

- Committing business data first or using the outbox pattern to publish events durably.
- Avoiding calling slow cloud services inside a database transaction whenever steps can be separated.
- Using appropriate transaction timeouts and cleaning up when the deadline expires.
- Designing compensation/idempotency when multiple services cannot participate in a single distributed transaction.

## 10. Timeouts for Messaging and Background Workers

Messaging has different semantics from HTTP request-response. A consumer typically performs:

~~~text
Receive message
    → Process business logic
    → Persist data
    → Complete / acknowledge / checkpoint
~~~

Timeouts to distinguish:

| Type | Meaning |
| --- | --- |
| Receive wait timeout | Waiting for a message within a given period |
| Message lock / visibility timeout | How long the consumer holds exclusive processing rights before the message can be redelivered |
| Processing deadline | Maximum time allowed for business logic to process a message |
| Settlement timeout | Time allotted for complete/abandon/dead-letter/ack |
| Lock renewal | Extending the lock during long processing when supported by the service |

With Azure Service Bus, **message lock duration** and **auto lock renewal** are not operation deadlines. If processing exceeds the lock, the message may be redelivered; two consumers could execute side effects concurrently if the design is not idempotent.

With AWS SQS, **visibility timeout** plays a similar role at the delivery level. With Google Cloud Pub/Sub, distinguish **ack deadline** and lease extension mechanisms. The names differ, but all raise the same question: how long does the consumer still hold the right to process the message?

### Worker Deadlines

A worker should have a message processing deadline while leaving time for settlement. For example, if 30 seconds remain on a lock and business processing is expected to take 25 seconds, do not spend the entire 25 seconds on downstream calls leaving no time to complete the message.

When the deadline expires:

- Stop new work.
- Cancel downstream requests if cancellation is supported.
- If the business outcome cannot be confirmed, handle settlement per policy: abandon, retry, dead-letter, or let the lock expire by design.
- Ensure redelivery does not cause duplicate side effects.

**A timeout does not mean the message failed on the service side.** If the client loses the response after the broker already accepted the message, retrying can send a duplicate. Use message IDs, idempotency keys, outbox/inbox, or appropriate deduplication.

## 11. Retries Must Stay Within the Deadline

Retries help with transient errors, but they increase latency and request volume. A retry policy must consider:

1. Is the error recoverable? For example, 429/503 or connection resets may be retryable depending on the operation.
2. Is the operation safe to repeat?
3. Is there enough remaining time for the next attempt and cleanup?
4. Does the service provide **Retry-After** or backoff hints?
5. Are other retry layers also retrying simultaneously?

### Retry Budget Formula

With (n) attempts, each attempt having timeout (t_i) and backoff interval (b_i):

\[
T_{retry} = \sum_{i=1}^{n} t_i + \sum_{i=1}^{n-1} b_i
\]

So the operation does not exceed the deadline:

\[
T_{retry} \leq T_{remaining}
\]

This is a necessary budget condition; you still need to reserve time for pre/post steps and scheduler/transport overhead.

### Bounded Retry Example

With 1,000 ms remaining budget and each attempt capped at 300 ms:

| Component | Budget |
| --- | ---: |
| Attempt 1 | 300 ms |
| Backoff 1 | 100 ms |
| Attempt 2 | 300 ms |
| Backoff 2 | 100 ms |
| Attempt 3 | 150 ms |
| Completion/cleanup | 50 ms |
| **Total** | **1,000 ms** |

The final attempt is shortened to 150 ms because that is all the budget left. If an SDK does not support adjusting the timeout per attempt, the application may need to reduce the retry count or use a client/adapter mechanism that supports deadlines.

### Exponential Backoff and Jitter

Increasing backoff helps avoid continuous retries:

\[
b_k = \min(b_{max}, b_0 \times 2^{k-1}) + jitter
\]

Jitter prevents clients from retrying at the exact same moment after an incident. In practice, combine this with **Retry-After** when provided by the service and never exceed the remaining deadline.

Do not automatically retry errors that are typically configuration or permission failures such as **401/403** without a specific reason. Retries will not fix a wrong tenant, missing role, nonexistent endpoint, or invalid proxy authentication.

## 12. Timeout, Cancellation, and Side Effects

Timing out at the caller and stopping work on the server are two different events.

~~~mermaid
sequenceDiagram
    participant C as HTTP caller
    participant A as Spring Boot API
    participant B as Azure Blob
    C->>A: Request
    A->>B: Upload
    C--xA: Caller timeout / disconnect
    Note over A,B: Server may still be uploading
    B-->>A: Upload succeeded
    Note over C,A: Caller never received the response
~~~

If a client times out after sending a request, several states are possible:

- Azure never received the request.
- Azure received it but has not finished processing.
- Azure finished, but the response was lost.
- The server continues the work even though the caller disconnected.

Therefore, **timeout does not equal the operation never happened**.

### Difference Between Timeout and Cancel

- **Timeout:** a time limit has expired.
- **Cancel:** a signal requesting an in-flight computation/I/O to stop.
- **Abort:** the transport/SDK actually stops the request or closes associated resources.
- **Compensation:** another business operation to reconcile side effects that already occurred.

Not every client propagates cancellation down to the socket or SDK operation. Future.cancel(true) only sends an interrupt; blocking libraries may not respond. CompletableFuture.orTimeout completes the future with a TimeoutException, but **does not guarantee the underlying network call stopped**. Reactor cancellation typically propagates through the publisher/connector, yet side effects on the remote server may have already occurred.

### When a Timeout Happens After a Write Operation

For a Blob upload, if a timeout happens while committing the block list, check the blob status before retrying if the operation is not idempotent. For a Service Bus send, the message may have already been accepted by the broker even if the client missed the acknowledgment. For a database commit, the transaction may have committed before the connection dropped.

Resilient designs typically use:

- Idempotency keys or deterministic resource/message IDs.
- Conditional writes/ETags where appropriate.
- Outbox/inbox patterns for databases and messaging.
- Querying state after a timeout when possible.
- Explicit compensation rather than assuming automatic rollback across multiple services.

## 13. Applying in Spring Boot: One Deadline for the Whole Request

One approach is to create a **Deadline context** at the application service layer and pass it through the adapters. Avoid letting each repository/client invent its own default timeout unaware of the parent budget.

### 13.1. Service Orchestration Example

~~~java
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import org.springframework.stereotype.Service;

@Service
public class OrderWorkflow {

    private final OrderRepository orders;
    private final DocumentGateway documents;
    private final EventPublisher events;

    public OrderWorkflow(
            OrderRepository orders,
            DocumentGateway documents,
            EventPublisher events) {
        this.orders = orders;
        this.documents = documents;
        this.events = events;
    }

    public OrderResult create(CreateOrderCommand command) throws Exception {
        Deadline deadline = Deadline.after(Duration.ofMillis(2500));

        ensureTime(deadline);
        Order order = orders.save(command, deadline.cap(
                Duration.ofMillis(450)));

        ensureTime(deadline);
        String blobName = documents.upload(
                command.document(),
                deadline.cap(Duration.ofMillis(850)));

        ensureTime(deadline);
        events.publish(
                new OrderCreated(order.id(), blobName),
                deadline.cap(Duration.ofMillis(400)));

        ensureTime(deadline);
        return new OrderResult(order.id(), blobName);
    }

    private static void ensureTime(Deadline deadline)
            throws TimeoutException {
        if (deadline.isExpired()) {
            throw new TimeoutException("Order operation deadline exceeded");
        }
    }
}
~~~

Illustrative interfaces:

~~~java
public interface DocumentGateway {
    String upload(Document document, Duration timeout);
}

public interface EventPublisher {
    void publish(OrderCreated event, Duration timeout);
}
~~~

**This is architecture-oriented pseudocode**: the adapter must apply the received timeout to the real SDK/driver and have an appropriate error/cancellation mechanism. Calling deadline.cap only calculates the maximum timeout; it does not automatically configure JDBC or Azure SDK if the adapter ignores that value.

If orders.save uses a transaction, inspect the transaction timeout and connection/query timeout separately. Do not assume a Duration passed into a gateway automatically controls the transaction manager.

### 13.2. Mapping Timeouts by Dependency

| Adapter | Timeouts to Configure |
| --- | --- |
| JDBC repository | Pool acquisition, connection, query/statement, transaction |
| RestClient/WebClient | Connect, response/read, pool acquisition, and whole publisher/request |
| Azure Blob SDK | HTTP transport, SDK retry, total upload duration |
| Azure Service Bus | Send/receive timeout, lock/renewal, and settlement |
| Cosmos DB | Request/connection timeout, retry/throttling, and query/page iteration |
| Key Vault | HTTP transport, retry, and total operation time |
| Executor/thread pool | Queue wait time, concurrency limit, and deadline check before starting |

## 14. Timeouts at the Server and Ingress Layers

Even when clients/SDKs have timeouts configured, check the timeouts of layers wrapping the request:

~~~text
External caller
    → API gateway / ingress / load balancer
        → Servlet container / reactive server
            → Spring controller
                → Application service deadline
                    → Downstream client timeouts
~~~

Practical rules:

- The application deadline should be small enough that the server can return a controlled error before the ingress closes the connection.
- The client timeout should be large enough to receive a response or a meaningful timeout from the server, without forcing users to wait indefinitely.
- Do not set the server timeout longer than the sum of all downstream timeouts without good reason.
- For async MVC, WebFlux, background tasks, or streaming, timeouts must fit their specific lifecycle and semantics; do not apply one property globally to every request.
- When the caller disconnects, the application should decide which work can be stopped and which work must complete to preserve consistency.

**spring.mvc.async.request-timeout** only applies to Spring MVC asynchronous request processing according to its configuration; it is not a general timeout for all synchronous controllers, JDBC, and Azure SDKs. Always check timeouts at each actual layer.

## 15. Observing and Measuring Timeouts

A reliable system must know where timeouts occur, not just count total HTTP 500s.

### Metrics to Track

| Metric | Meaning |
| --- | --- |
| Operation duration | Total duration of the business operation |
| Deadline remaining at call start | Remaining budget when starting a dependency call |
| Per-call duration | Latency per dependency/operation |
| Timeout count by phase | Timeouts at pool, connect, response, query, or operation |
| Retry count | Number of attempts and retries |
| Deadline exhausted count | Operations that exhausted their budget before completing |
| Cancellation count | Number of tasks receiving a cancel signal |
| Late completion count | Tasks finishing after the caller already timed out/disconnected |
| Queue/lock renewal count | Frequency of prolonged messaging processing |

### Logs and Traces

Log/record:

- Operation name, correlation/trace ID.
- Dependency/service name and operation type.
- Configured timeout and remaining budget at call time.
- Attempt number, backoff duration, status/error code.
- Actual duration and the phase that caused the timeout.

Do not log access tokens, secrets, SAS URLs, connection strings, payloads containing personal data, or full sensitive headers. Avoid using request IDs as high-cardinality metric labels; put them in logs/traces instead.

### Distinguishing High Latency from Overly Short Deadlines

An increasing timeout rate in a service may be caused by:

- A new SLO being too tight compared to actual latency.
- Pools being too small, causing requests to wait long before sending.
- Proxy/DNS/TLS increasing connect time.
- Azure throttling/429 increasing backoff.
- Retries stacking across multiple layers.
- Scaling up consumer replicas without downstream scaling.
- Congested network egress or Private Endpoints.

Do not simply raise timeouts to mask a bottleneck; inspect **p50/p95/p99** percentiles, throughput, concurrency, pool saturation, and error codes before tuning.

## 16. Testing Deadlines and Timeouts

### 16.1. Unit Tests with a Fake Clock

Do not use long Thread.sleep calls in unit tests to verify deadline logic. Inject a clock/ticker abstraction to control elapsed time and verify:

- While budget remains, the adapter receives a timeout no greater than remaining.
- When the deadline expires, no new downstream call is started.
- Child timeouts are capped by the configured timeout.
- Retries/backoff do not exceed the budget.
- Timeout errors map to the right business result.

The illustrative Deadline class above calls System.nanoTime() directly. For deterministic testing, extract a **Ticker/MonotonicClock interface** and inject a fake implementation.

### 16.2. Integration Tests with a Mock HTTP Server

Use an HTTP test server to simulate:

- Slow connection establishment or slow responses.
- Returning response headers quickly but streaming the body slowly.
- Closing connections mid-flight.
- Returning 429/503 with Retry-After.
- Accepting a request without sending a response to verify timeout/cancellation.

Verify status/error mapping, actual elapsed time, request counts, and whether the transport releases connections properly.

### 16.3. Testing Azure SDK and Managed Services

In an Azure dev/test environment:

1. Run with the runtime's real identity and endpoints.
2. Provision test Blob or Service Bus resources with cleanup.
3. Configure transport timeouts/retries under a test profile.
4. Induce controlled network/403/429 failure scenarios when allowed by the service or environment.
5. Verify the operation deadline includes SDK retry time, not just a single HTTP request.
6. Confirm cancellation does not cause the application to ignore side effects that already happened.

Azurite is useful for testing parts of the Blob API, but it does not fully simulate Azure throttling, managed identity, RBAC, Private Endpoints, or real service latency.

### 16.4. Testing Messaging

For Service Bus, verify:

- Receive wait timeout.
- Processing deadline shorter than or compatible with lock duration/renewal.
- Settlement timeout.
- Redelivery when a worker dies or a lock expires.
- Idempotency when the sender misses the acknowledgment but the broker accepted the message.

Do not only test that send() throws a timeout; verify whether the message exists in the broker in the test environment and whether the consumer handles duplicates safely.

## 17. Comparison with AWS and Google Cloud

| Topic | Azure | AWS | Google Cloud |
| --- | --- | --- | --- |
| HTTP client | Azure Core HttpClient per transport | AWS SDK HTTP client per service/client | HTTP/gRPC transport depending on API |
| Request timeout | HTTP transport + SDK options + application deadline | HTTP client + SDK client configuration + application deadline | Client settings/gRPC deadline + application deadline |
| Retry | Azure SDK/service retry options | SDK retry strategy and service behavior | Client retry settings and RPC behavior |
| Messaging lease | Service Bus lock/renewal, Event Hubs processing/checkpoint | SQS visibility timeout, Kinesis checkpoint | Pub/Sub ack deadline/lease extension |
| Database | JDBC/Cosmos request/query options | JDBC/DynamoDB request options | JDBC/Firestore/Spanner client options |
| Deadline propagation | Application context or protocol with built-in support | Similar, client/protocol dependent | gRPC has widespread deadline semantics |
| Operations | Azure Monitor/OTel and SDK diagnostics | CloudWatch/OTel and SDK metrics | Cloud Monitoring/OTel and client metrics |

Providers differ in property names, transports, and retry semantics. A **1-second timeout** in one HTTP provider does not necessarily mean the same thing as a **1-second timeout** in another. When switching clouds, inspect connect/read/operation deadlines, cancellation, and message lease/ack behavior.

## 18. Lab Exercise: Bounding a 2.5-Second Workflow

**Context:** The POST /orders API performs three tasks: saves the order to the database, uploads a document to Blob, and sends an OrderCreated event to Service Bus. The entire request must have a 2,500 ms deadline.

### Part A — Define the Budget

1. Set a 2,500 ms deadline at the application boundary.
2. Allocate time for validation, database, Blob, Service Bus, retries, and response.
3. Set each adapter's timeout to the smaller of its configured timeout and remaining budget.
4. Ensure connection-pool wait, token acquisition, and retries are included in the budget.

### Part B — Implement Adapters

1. For JDBC, configure appropriate connection-pool acquisition and query/transaction timeouts.
2. For Blob, configure HTTP transport timeouts and SDK retries; measure the entire upload, including chunks.
3. For Service Bus, configure send timeout, account for settlement time, and design message IDs/idempotency.
4. Propagate the deadline through the application service; do not create a new deadline per dependency.

### Part C — Fault Injection

1. Make the database return slower than its expected budget; verify Blob does not start once the deadline has expired.
2. Force a Blob request timeout after the server may have received the data; check blob state before retrying according to the design.
3. Drop the Service Bus send acknowledgment; verify duplicate message handling and consumer idempotency.
4. Simulate 429/503 and backoff; verify total time does not exceed the deadline.
5. Disconnect the caller mid-processing; inspect whether the server continues work and how side effects are handled.
6. Collect traces containing total duration, per-call duration, remaining budget, attempt count, and timeout phase.

### Deliverables

- Workflow diagram showing the deadline and per-step timeouts.
- Configuration table of timeouts for HTTP, database, Blob, and Service Bus.
- Test results when the deadline has remaining time and when it expires.
- Evidence that retries/backoff do not exceed the budget.
- Explanation of a timeout scenario where side effects already occurred, along with the idempotency/compensation strategy.

### Self-Check Questions

1. Why do three dependencies each with a 2-second timeout not guarantee the API finishes in 2 seconds?
2. What is the difference between connect timeout, read timeout, and operation deadline?
3. Why must System.nanoTime() be used to calculate elapsed time in the JVM?
4. Why must nanoTime() values never be sent directly over HTTP?
5. If the caller times out but Blob already finished uploading, how should the API handle retries?
6. Why does CompletableFuture.orTimeout() not guarantee canceling the underlying network request?
7. How can retries cause the total duration to exceed the deadline?
8. Why is Service Bus lock duration not a processing deadline?
9. How does a query timeout differ from a connection-pool acquisition timeout?
10. Why does spring.mvc.async.request-timeout not replace Azure SDK timeouts?

## 19. Takeaways

- A **deadline** bounds the entire business operation; a **per-call timeout** bounds a single step. Every child timeout must be capped by the parent deadline's remaining budget.
- Budgets must account for queue/pool wait, DNS/TLS/proxy, token acquisition, request/response, retries/backoff, and cleanup.
- Use a **monotonic clock** within a single process; when propagating across services, pass an absolute UTC deadline or remaining budget under a clear contract.
- Connect/read/response timeouts are not automatically whole-operation timeouts. Check the semantics of the HTTP transport, JDBC driver, Azure SDK, and messaging client.
- Retries must be bounded by the deadline, backoff/jitter, and idempotency. Do not infinitely retry configuration/permission errors.
- Timeouts and cancellation do not prove a remote side effect did not happen. Use idempotency, outbox/inbox, state re-checks, or compensation.
- Test against real runtimes/dependencies and observe p95/p99, deadline exhaustion, retries, cancellation, and late completions.

## References

- [Spring Framework — REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html)
- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html)
- [Project Reactor — Mono timeout](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html)
- [Azure SDK for Java — HTTP client pipeline](https://learn.microsoft.com/azure/developer/java/sdk/http-client-pipelines)
- [Azure SDK for Java — Retry policy](https://learn.microsoft.com/azure/developer/java/sdk/retries)
- [Azure Storage Blob client library for Java](https://learn.microsoft.com/java/api/overview/azure/storage-blob-readme)
- [Azure Service Bus message locks and settlement](https://learn.microsoft.com/azure/service-bus-messaging/message-transfers-locks-settlement)
- [HikariCP configuration](https://github.com/brettwooldridge/HikariCP#gear-configuration-knobs-baby)
- [JDBC Statement API](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Statement.html)
