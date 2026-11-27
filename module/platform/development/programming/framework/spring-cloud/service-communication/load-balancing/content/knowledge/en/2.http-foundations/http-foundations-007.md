# Idempotency and the Impact of Retrying Requests

In inter-microservice communication, a request may be resent when the client encounters a timeout, connection loss, or transient error. Spring Cloud LoadBalancer can also try another instance when a retry policy is enabled. However, the client often does not know for certain whether the server already processed the earlier request. If an order creation or payment operation is executed twice, retrying can cause duplicate records and severe business impact.

**Idempotency** is the property ensuring an operation produces the same final business outcome whether executed once or multiple times with the same input. It is the foundation for designing APIs that can be retried safely. This lesson focuses on HTTP semantics, request retry scenarios, and how to implement idempotency keys on the application side.

## 1. What Is Idempotency?

An operation is called idempotent if executing it multiple times produces the same final business state as executing it once. This concept can be expressed as:

\[
f(f(x)) = f(x)
\]

Where \(x\) is the initial state and \(f\) is the operation. Calling the operation again on the updated state leaves the business state unchanged.

Examples:

- Setting an order's status to **CANCELLED** is idempotent if every call brings the order to that same state.
- Deleting a resource by ID is generally idempotent with respect to state: after the first deletion, the resource no longer exists; a subsequent deletion changes the state no further.
- Incrementing a wallet balance by 100,000 VND is not idempotent: calling it twice increases the balance by 200,000 VND.
- Creating a new order is generally not idempotent: each call may create another order.

Idempotency refers to the **intended effect on business state**, not requiring every HTTP response to be identical. For example, the first DELETE may return 204 No Content, while the next may return 404 Not Found because the resource is already gone. The final state remains the same.

An idempotent API may still write logs, increment monitoring counters, or record call history. Those side activities do not alter the conclusion about the primary business effect, though they must be designed not to introduce unintended side effects.

## 2. Distinguishing Safe Methods and Idempotent Methods in HTTP

HTTP defines semantics for each method so clients and servers agree on the kind of effect a request intends. Two key concepts are **safe** and **idempotent**:

- **Safe method:** the client requests to read or retrieve information; the server must not treat the request as a request to alter business state.
- **Idempotent method:** multiple identical requests have the same intended effect on server state as a single request.

According to RFC 9110, all safe methods are also idempotent. An idempotent method can still modify state, such as PUT and DELETE.

| HTTP method | Safe | Idempotent under HTTP semantics | Implications for retries |
| --- | --- | --- | --- |
| GET | Yes | Yes | Usually safe to retry on transient failures |
| HEAD | Yes | Yes | Usually safe to retry on transient failures |
| OPTIONS | Yes | Yes | Usually safe to retry on transient failures |
| TRACE | Yes | Yes | Has safe and idempotent semantics; commonly restricted in real applications |
| PUT | No | Yes | Can resend the same payload to set the resource to the same state |
| DELETE | No | Yes | Can resend the request to delete the same resource |
| POST | No | Not guaranteed | Safe to retry only when the API has deduplication or the business logic is inherently idempotent |
| PATCH | No | Not guaranteed | Must inspect the specific patch semantics and API contract |

### 2.1. PUT and DELETE

PUT typically represents creating or replacing the state of a resource at a known URI. Sending the same representation to the same URI multiple times must have the same intended effect.

~~~http
PUT /api/customers/42/address
Content-Type: application/json

{
  "street": "12 Nguyen Hue",
  "city": "Ho Chi Minh City"
}
~~~

If the request above is resent, the customer's address is still set to the same value. The API should not interpret each PUT as an instruction to create an additional new address.

DELETE requests deleting the resource identified by the URI:

~~~http
DELETE /api/orders/ORD-2026-001
~~~

On the first call, the server may delete the order or mark it as deleted. On the next call, the resource is already nonexistent or deleted. The responses may differ, yet the intended effect remains that the resource no longer exists.

### 2.2. POST and PATCH

POST typically asks the server to perform an action according to the target resource's semantics. For example, creating an order:

~~~http
POST /api/orders
Content-Type: application/json

{
  "customerId": "CUS-42",
  "items": [
    {
      "sku": "BOOK-01",
      "quantity": 2
    }
  ]
}
~~~

If the server creates a new order record on every POST, resending the request will create duplicate orders. HTTP does not provide built-in deduplication guarantees for POST.

PATCH applies a partial change to a resource. Its effect depends on the patch contents:

- Setting a status field to a specific value, such as **status = "CANCELLED"**, can be designed to be idempotent.
- Incrementing a quantity field by 1 is not idempotent if each application adds another 1.
- A patch containing an append-to-list operation can create duplicate items when resent.

Therefore, one cannot conclude that every PATCH is safe or that no POST can be idempotent. What decides is the semantics and contract of the specific API. However, clients should not assume a POST or PATCH is idempotent unless the server explicitly publishes and implements that guarantee.

## 3. Why Do Timeouts Make Retries Dangerous?

A connection error does not tell you for sure whether the server already executed the business operation. Consider an order creation flow:

~~~mermaid
sequenceDiagram
    participant C as Order Client
    participant L as LoadBalancer
    participant A as Order Service instance A
    participant B as Order Service instance B
    C->>L: POST /orders
    L->>A: Forward request
    A->>A: Save order successfully
    A--xC: Response lost on the network
    C->>C: Wait timeout expires
    C->>L: Retry request
    L->>B: Select instance B
    B->>B: Create order again
    B-->>C: Return second order
~~~

The client only observes a timeout. In reality, there are at least three possibilities:

1. The request never reached the server, so the business operation was not executed.
2. The server received the request but has not finished processing it.
3. The server completed the business operation and sent the response, but the response was lost or arrived after the client's deadline.

If the client retries in the first case, the second request can help complete the operation. If it retries in the third case without API deduplication, the operation may execute twice.

This is why you cannot deduce "the server has not processed it" solely from the client receiving no response. A timeout describes what the client observed, not proof of the transaction state on the server.

### 3.1. Common failure points

| When the failure occurs | What the client knows | Risk on retry |
| --- | --- | --- |
| Cannot resolve service ID or select an instance | Request was not sent to a business instance | Usually no side effect on the target service |
| Connection error before sending request | Request may not have reached the server | Check which stage of the HTTP client and proxy raised the error |
| Connection sent request, but client hit read timeout | Unknown whether the server committed | May cause duplicate side effects |
| Server returns 503 or 504 after a downstream component processed it | Only knows an error code was received | Business work may already have completed in a dependency |
| Client receives a successful response | Knows the returned result | No need to retry that operation |

Not every 5xx error means the operation has not run. A proxy may return 504 while the target service still completes the transaction. Retry policies must rely on API semantics and deduplication capabilities, not status codes alone.

## 4. Idempotency Keys for Non-Inherently Idempotent Operations

For an operation such as order creation or payment, the client can send an **idempotency key** to identify a single logical business execution. The server stores the key along with the processing result. If the request is resent with the same key and the same payload, the server recognizes it as a retry of the earlier operation and returns the stored result.

The header can be designed as follows:

~~~http
POST /api/payments
Idempotency-Key: 9a91f8e2-7c31-4f89-a88c-1c5c9fd4d207
Content-Type: application/json

{
  "orderId": "ORD-2026-001",
  "amount": 250000,
  "currency": "VND"
}
~~~

The header name and key interpretation are part of the API contract that the system must agree upon. Merely sending the header does not create idempotency; the server must store and check the key in a coordinated manner across instances.

### 4.1. Key lifecycle

A key represents **one logical business operation**, not one HTTP transmission attempt. The client must generate the key before the first attempt and reuse that exact key across all retries of the same operation.

~~~mermaid
flowchart TD
    A["Client initiates payment operation"] --> B["Generate an Idempotency-Key"]
    B --> C["Send request with key"]
    C --> D["Server checks key and fingerprint"]
    D --> E{"Key already exists?"}
    E -->|No| F["Claim key atomically"]
    F --> G["Execute business logic"]
    G --> H["Save result and COMPLETED status"]
    H --> I["Return response"]
    E -->|Completed, same content| J["Return stored response"]
    E -->|In progress| K["Return in-progress status per contract"]
    E -->|Same key, different content| L["Reject inconsistent request"]
    I --> M["Client retries with same key if needed"]
    J --> M
    M --> D
~~~

For example: a user clicks the pay button once, and the application generates the key **PAY-CUS42-ORDER001-01**. If the first attempt times out, the next attempt must reuse that exact key. Generating a new UUID on each attempt makes the server treat them as two separate operations and prevents duplicate detection.

### 4.2. Identity scope and fingerprint

Using only the key as the lookup key can cause collisions across users or endpoints. The server should scope the key by appropriate dimensions, such as:

- Authenticated user, tenant, or account identity.
- Operation name or business endpoint.
- Client-supplied idempotency key.

The server should also compute a **request fingerprint** from business-significant data, such as a hash of the canonicalized payload combined with the operation type. The goal is to detect cases where a client accidentally reuses the same key for different content.

| Situation | Expected behavior |
| --- | --- |
| Same user, same operation, same key, same content, already completed | Return the stored result |
| Same key but different payload or business parameters | Reject, typically using 409 Conflict per API contract |
| Same key currently being processed by another request | Return an in-progress status or instruct the client to check back |
| Key belongs to a different user or tenant | Never share results across two security scopes |
| Key retention period has expired | Handle according to the published expiration policy |

Do not embed secrets or unnecessary personal information into the key itself. Keys should be unpredictable, have sufficient entropy, and never contain access tokens.

## 5. Implementing Server-Side Deduplication

### 5.1. Shared idempotency state storage

Because Spring Cloud LoadBalancer can route retries to a different instance, idempotency state must be shared across instances. Storing keys in a static variable or per-process memory is insufficient: instance A may have processed the request while instance B knows nothing about that key.

A storage table may include the following columns:

| Column | Purpose |
| --- | --- |
| scope | User, tenant, or API scope |
| operation | Type of business operation |
| idempotency_key | Key sent by the client |
| request_hash | Fingerprint of request content |
| state | Status such as IN_PROGRESS or COMPLETED |
| response_status | HTTP status code of the processed result |
| response_body | Replayable response content |
| created_at, expires_at | Creation timestamp and key retention expiration |

Create a unique constraint on the composite key of scope, operation, and idempotency_key. A unique constraint is a critical safeguard when two identical requests reach two instances almost simultaneously.

Abbreviated DDL example for PostgreSQL:

~~~sql
CREATE TABLE idempotency_record (
    scope             VARCHAR(160) NOT NULL,
    operation         VARCHAR(120) NOT NULL,
    idempotency_key   VARCHAR(200) NOT NULL,
    request_hash      CHAR(64) NOT NULL,
    state             VARCHAR(20) NOT NULL,
    response_status   INTEGER,
    response_body     JSONB,
    created_at        TIMESTAMPTZ NOT NULL,
    expires_at        TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (scope, operation, idempotency_key)
);
~~~

Data types and response storage structure should be tailored to the database engine and API requirements. Do not store sensitive headers such as Authorization in recorded responses.

### 5.2. Processing requests atomically

A general processing flow:

1. Authenticate the caller and determine scope and operation.
2. Validate key format and validate the request.
3. Canonicalize relevant data and compute the request fingerprint.
4. Attempt to claim the key via an atomic operation protected by a unique constraint.
5. If the key already exists, compare fingerprints. If they differ, reject the request. If they match and processing is complete, return the stored result.
6. If the key is still in progress, return a status per the API contract without executing the business logic a second time.
7. For a new key, execute the business change and persist the completed status together with the result.
8. Return the response to the client.

The example below illustrates the service-level flow; unique constraint contention handling, transactions, and response mapping must be implemented in the appropriate repository/service:

~~~java
public PaymentResponse createPayment(
        String idempotencyKey,
        CreatePaymentRequest request) {

    String scope = currentCustomerId();
    String operation = "CREATE_PAYMENT";
    String requestHash = fingerprint(request);

    IdempotencyRecord existing =
            idempotencyRepository.find(scope, operation, idempotencyKey);

    if (existing != null) {
        if (!existing.requestHash().equals(requestHash)) {
            throw new IdempotencyConflictException(
                    "The key was used with a different request");
        }

        if (existing.isCompleted()) {
            return existing.toPaymentResponse();
        }

        throw new RequestStillProcessingException();
    }

    // Claim the key atomically before performing the business operation.
    idempotencyRepository.insertInProgress(
            scope, operation, idempotencyKey, requestHash);

    Payment payment = paymentRepository.create(request);
    PaymentResponse response = PaymentResponse.from(payment);

    idempotencyRepository.complete(
            scope, operation, idempotencyKey, response);

    return response;
}
~~~

This is pseudocode to show the sequence, not a complete implementation to copy verbatim. In a real application, two concurrent requests could both read that the key does not exist yet. Therefore, claiming the key must be an atomic operation; you cannot rely on a plain SELECT followed by an INSERT without handling contention.

If the business mutation and the idempotency record live in the same database, use a transaction to commit them together. When inserting a key hits a unique constraint violation, the losing request must re-read the existing record and handle it by state/fingerprint. Be careful about transactions marked rollback-only after a constraint error; conflicts may need to be handled at a separate transaction boundary.

### 5.3. Avoiding failure windows between business work and key recording

Suppose the server creates a payment transaction first and only then records COMPLETED. If the process crashes between those two steps, a retry might see the key still IN_PROGRESS or lacking a result and create the transaction again. Conversely, recording COMPLETED before the real transaction finishes can cause the server to replay an inaccurate success result.

For data in the same database, commit the business change and the idempotency result in the same transaction. For side effects in external systems, such as a payment gateway, the application's database transaction cannot atomically span the external transaction. In that case:

- Forward a stable deduplication key to the payment provider if they support it.
- Record the state of outbound commands and returned results for reconciliation.
- Use a transactional outbox to persist events to be sent in the same transaction as business data.
- Design consumers or workflows to tolerate redelivered messages without duplicating side effects.
- Have a reconciliation process for indeterminate states instead of automatically creating a new transaction.

Idempotency in one service does not automatically guarantee that side effects in all downstream dependencies occur only once. Each system boundary needs its own deduplication contract and mechanism. Nor does this turn the network into an "exactly-once" channel: requests or messages can still be delivered multiple times. The practical goal is deduplicating business effects within a defined key scope and time window.

### 5.4. Key retention period

Keys cannot be stored indefinitely in every system. Servers typically set an expiration period based on how long clients may retry, asynchronous processing durations, and reconciliation requirements. The TTL must exceed the published retry window.

Deleting key records too early can cause a late-arriving old request to be treated as a new operation. For financial workflows, retention periods and reconciliation needs may be much longer than typical HTTP timeouts.

The expiration policy should be documented in the API contract. Clients should not resend the same operation after a key expires without checking business state first.

## 6. Sending Idempotency Keys from Spring HTTP Clients

### 6.1. RestClient

Generate the key once at the business operation boundary, then pass that key into the client. Never generate a new key inside each retry attempt:

~~~java
public PaymentResponse createPayment(
        String idempotencyKey,
        CreatePaymentRequest request) {

    return restClient.post()
            .uri("http://payment-service/api/payments")
            .header("Idempotency-Key", idempotencyKey)
            .contentType(MediaType.APPLICATION_JSON)
            .body(request)
            .retrieve()
            .body(PaymentResponse.class);
}
~~~

When the HTTP client or retry layer resends the request, the same key must be preserved. The target service must store the key in a shared store and perform the checks described earlier.

### 6.2. WebClient

With WebClient, pass the header following the same principle:

~~~java
public Mono<PaymentResponse> createPayment(
        String idempotencyKey,
        CreatePaymentRequest request) {

    return webClient.post()
            .uri("http://payment-service/api/payments")
            .header("Idempotency-Key", idempotencyKey)
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(request)
            .retrieve()
            .bodyToMono(PaymentResponse.class);
}
~~~

The publisher may be subscribed to or retried according to the application's design. Ensure every subscription for the same business operation uses the exact same key and payload. Never generate a random key inside code that re-executes on every subscribe.

### 6.3. OpenFeign

With Feign, declare the header as a client method parameter:

~~~java
@FeignClient(name = "payment-service")
interface PaymentFeignClient {

    @PostMapping("/api/payments")
    PaymentResponse createPayment(
            @RequestHeader("Idempotency-Key") String idempotencyKey,
            @RequestBody CreatePaymentRequest request);
}
~~~

The caller must pass the same key when calling the method again for the same operation. Feign does not generate idempotency keys automatically, nor does it make POST idempotent on its own.

## 7. Coordinating Idempotency with Spring Cloud LoadBalancer Retries

Spring Cloud LoadBalancer can retry a request on the same instance or a next instance, depending on configuration and HTTP client type. When a retry shifts to another instance, the new instance must see the same idempotency state from the prior attempt. This requires shared storage or a consistent coordination mechanism across instances.

Example configuration capping retry attempts at the LoadBalancer layer:

~~~yaml
spring:
  cloud:
    loadbalancer:
      retry:
        enabled: true
        max-retries-on-same-service-instance: 0
        max-retries-on-next-service-instance: 1
        retryable-status-codes:
          - 502
          - 503
          - 504
~~~

This configuration merely illustrates attempt caps and a set of status codes. Actual retry capability depends on the HTTP client, adapter, and Spring Cloud version. Enabling retries does not create idempotency keys, does not store results, and does not guarantee POST requests will not be processed twice.

A retry policy should satisfy these principles:

1. Prefer retrying safe or idempotent methods as defined by the API contract.
2. For POST or PATCH operations with side effects, retry only when the server has a verified deduplication mechanism.
3. Retry only errors likely to be transient; honor Retry-After when the server returns 429 or 503 with appropriate guidance.
4. Bound retry attempts, apply backoff and jitter, and respect the original request's deadline.
5. Avoid stacking retries across multiple layers without calculating total attempts. For example, two layers each allowing three attempts can produce up to nine calls to a dependency.
6. Record retry counts and duplicate-request detection rates to spot retry storms or misconfiguration.

Do not retry all 5xx errors by default. A 500 error may be returned after business logic already committed. For non-idempotent operations, idempotency keys must be enforced by the server before callers rely on retries for recovery.

### 7.1. Example payment flow across two instances

Suppose Payment Service has two instances A and B:

1. Order Service generates a key for the order's payment operation.
2. LoadBalancer routes the POST to instance A.
3. A claims the key in the shared store, executes the transaction, and saves the COMPLETED result.
4. The response is lost, so Order Service times out.
5. LoadBalancer routes the retry to instance B with the same key and payload.
6. B finds the completed key, verifies the matching fingerprint, and returns the stored result.
7. Only one payment transaction is created.

If A and B stored keys in private in-memory maps, step 6 would fail because B does not know A already processed it. If the client generated a new key at step 5, the server would also treat it as a separate operation. Both cases break deduplication guarantees.

## 8. Common Design Mistakes

| Mistake | Consequence | Remedy |
| --- | --- | --- |
| Generating a new key on every retry | Each request is treated as a new operation | Generate the key at the start of the business operation and reuse it |
| Storing keys only in instance memory | Retries routed to another instance fail to recognize prior requests | Use a shared store with a unique constraint or equivalent coordination |
| Checking keys with SELECT before INSERT | Two concurrent requests can both pass the check | Claim the key atomically and handle unique conflicts |
| Not checking request fingerprint | The same key can be reused for different content | Store a hash of the canonicalized payload and reject mismatches |
| Saving the key after side effects occurred | Process may crash before writing the key, causing retries to repeat side effects | Commit business data and idempotency record in one transaction or use dependency idempotency |
| Expiring keys too early | Late-arriving old requests can trigger a new operation | Set TTL based on retry window and business requirements |
| Retrying all POSTs or all 5xx errors | Creates duplicate data or amplifies load on failing dependencies | Retry conditionally, with bounds, grounded in the idempotency contract |
| Using idempotency keys in place of authentication | Others might guess or reuse keys to view results | Scope keys to principal/tenant and enforce authorization on every request |

## 9. Testing Idempotency and Retries

Do not test only normal happy-path requests. The most critical bugs appear when responses are lost or multiple requests arrive within a short window.

| Test scenario | How to execute | Expected outcome |
| --- | --- | --- |
| Same key sent twice sequentially | Send two POSTs with identical key and payload | Only one business record created; second call receives the stored result |
| Same key sent concurrently | Dispatch two requests almost simultaneously to two instances | Only one request claims the key and executes the business logic |
| Same key, different payload | Change amount or order ID while keeping the same key | Server rejects the inconsistent request |
| Response lost after commit | Let server commit, then intentionally drop the connection before client receives response | Client retries with same key and receives the prior result |
| Retry to another instance | First attempt hits A, second hits B | B recognizes the key from shared storage and does not repeat side effects |
| Instance restart | Restart instance after successful processing | Retry is still recognized from durable storage |
| Expired key | Resend request after published TTL | Behavior matches expiration policy; no unexpected transaction created |
| Retry exceeds deadline | Make dependency respond slower than caller deadline | Caller stops retrying and records indeterminate state for reconciliation |

For payment operations, use a sandbox or mock dependency. Compare business record counts, dependency call counts, and returned responses; checking HTTP status alone is insufficient to prove no duplicate side effects occurred.

## 10. Checklist for Designing Retry-Safe APIs

- [ ] Identify the method and operation semantics: safe, idempotent, or non-idempotent side effects.
- [ ] Document whether the API permits retries and which error categories are retryable.
- [ ] For creation or payment operations, define the idempotency key and key scope.
- [ ] Require clients to reuse the same key and payload across all attempts of an operation.
- [ ] Store a fingerprint to detect key reuse with differing content.
- [ ] Use a unique constraint or atomic operation to handle concurrent requests.
- [ ] Share idempotency state across all instances eligible to receive requests.
- [ ] Persist enough result data to replay responses per the API contract.
- [ ] Synchronize business transactions with idempotency records; handle external system side effects separately.
- [ ] Set TTL longer than the retry window and maintain a reconciliation process for ambiguous states.
- [ ] Bound retries by attempt count, backoff, jitter, and deadline; avoid multi-layer retry multiplication.
- [ ] Test lost responses after commit, concurrent requests, and cross-instance retries.

## 11. Conclusion

Idempotency is a property of business operations and API contracts. HTTP specifies that GET, HEAD, OPTIONS, TRACE, PUT, and DELETE carry idempotent semantics; POST and PATCH must be evaluated based on how the application implements them. When an operation is not inherently idempotent but needs retries, idempotency keys let the server recognize submissions belonging to the same operation.

In Spring Cloud systems, retries can route requests to a different instance. Therefore, all instances must share the same deduplication mechanism and handle contention atomically. Timeouts, retries, and idempotency should be designed together so systems recover under unstable networks without repeating business side effects.

## 12. References

- [RFC 9110 - HTTP Semantics, Section 9.2.2 Idempotent Methods](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.2.2): definition of idempotent methods and implications for retries.
- [RFC 9110 - HTTP Semantics, Section 9.2.1 Safe Methods](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.2.1): semantics of safe methods.
- [Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): instance selection, retries, and LoadBalancer configuration.
- [Spring Framework - REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): using RestClient and WebClient.
