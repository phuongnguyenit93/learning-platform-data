# Safe Requests, Idempotency, and Retry Side Effects

## 1. Why Can Retries Cause Business Errors?

In distributed systems, clients and servers communicate over a network, so a request can fail at many points: the client cannot connect, the connection drops mid-flight, the server exceeds a timeout, a proxy returns an error, or the server finishes the business operation yet the response never reaches the client. Consequently, when a client sees a timeout or network error, it usually **cannot be sure whether the server already executed the operation**.

If a client retries mechanically, a side-effecting operation can execute multiple times. For example, a user clicks pay, the server creates a transaction and submits a charge to a payment gateway, and the response is lost. The client times out and retries. If the server treats the retry as a brand-new request, the customer can be charged twice.

Retry is a recovery mechanism for transient failures. The safety of retrying depends on HTTP semantics, business design, duplicate-request detection, and retry limits. A sound retry policy must answer three questions:

1. Is this error likely to resolve itself upon retrying?
2. If the previous attempt actually succeeded, will sending it again produce additional side effects?
3. Is there enough time and budget to retry without overloading the system?

There is no single safe retry configuration for every API. Design it around each operation type and its side effects.

## 2. Distinguishing Safe Methods from Idempotent Methods

HTTP defines semantic properties for methods. Two key properties when designing retries are **safe** and **idempotent**.

- **Safe method**: the client requests reading or retrieving information; the requested operation does not alter the business state of the resource. The server may still record access logs, metrics, or operational telemetry.
- **Idempotent method**: executing the same request once or multiple times has the same intended effect on resource state. Responses across attempts may differ.
- **Retry**: the client resends a request after encountering a failure considered potentially recoverable. Retrying is a decision made by the client or an intermediary, not an automatic property of the server.

| HTTP method | Safe? | Idempotent? | Meaning for retries |
|---|---|---|---|
| GET | Yes | Yes | Safe to retry on transient failures if the request is genuinely read-only. |
| HEAD | Yes | Yes | Same as GET, except the response has no message body. |
| OPTIONS | Yes | Yes | Typically safe to retry when discovering capabilities. |
| TRACE | Yes per HTTP semantics | Yes | Rarely enabled in production apps; follow security policies. |
| PUT | No | Yes | Sends the same representation to set resource state to the same desired value. |
| DELETE | No | Yes | Requests that the resource be in a deleted state; later responses may differ from the first. |
| POST | No | Not guaranteed | Can create a resource or trigger a new side effect each time; safe to retry only when the business contract supports deduplication/idempotency. |
| PATCH | No | Not guaranteed | Depends on patch document definition and update logic; evaluate per API. |

**Safe is not synonymous with idempotent.** Every safe method is also idempotent, yet an idempotent method such as PUT or DELETE still modifies resource state.

**Idempotent does not mean responses must be identical.** For example, the first DELETE might return 204 No Content and the second might return 404 Not Found. If the business goal is that the resource no longer exists, the final state is identical. An API may also choose to return 204 even when the resource is already deleted to simplify the contract, provided behavior is documented consistently.

### 2.1. Examples of PUT and POST

Suppose an API exposes an endpoint to update a shipping address:

~~~http
PUT /customers/42/address
Content-Type: application/json

{
  "city": "Da Nang",
  "street": "Le Duan"
}
~~~

PUT sets customer 42's address representation to the submitted value. Resending the same request does not create a second address; the desired state remains that address. This operation naturally fits retries if other business conditions are also satisfied.

By contrast:

~~~http
POST /payments
Content-Type: application/json

{
  "orderId": "ORD-2026-0042",
  "amount": 1500000
}
~~~

POST can create a new payment each time it receives a request. If retried, the server might create two payments for the same order. To retry POST safely, the API must add duplicate-request detection, typically via an Idempotency-Key header and persisted execution results.

### 2.2. PATCH Must Be Evaluated by Content

A PATCH such as "set status to APPROVED" can yield the same state after repeated executions. A PATCH such as "increment quantity by 1" will keep incrementing on each call. Therefore, never assume PATCH is always idempotent or always non-idempotent. Inspect the patch document, preconditions, version checks, and actual side effects.

## 3. A Timeout Does Not Prove the Operation Did Not Run

Suppose a client sends a request with a 2-second timeout. The server may have already gone through these steps:

1. Received and authenticated the request.
2. Persisted business data in the database.
3. Called an external system.
4. Generated the response.
5. The response was delayed or lost on the network.

The client only observes a timeout at step 5. If the client retries immediately, the server might repeat step 2 or 3. This is an **ambiguous outcome** from the client's perspective.

Distinguish these scenarios:

- Connection failed before the request was sent: server processing likely never started, though the client or library must have sufficient evidence to conclude this.
- Request was sent yet no response arrived: the server may not have processed it yet, may be processing it, or may have already committed.
- Server returned 429, 503, or another transient error: retryable per the contract and server guidance.
- Server returned a validation or authorization error: retrying the exact same request usually will not help.
- Client actively canceled the request: stopping waiting for a response does not guarantee the server aborted running backend work.

For creating payments, placing orders, transferring funds, issuing tickets, or sending emails, assume the request may have been processed even if the client received no response. Idempotency must be solved on the server or in the system performing the side effect.

## 4. Idempotency Keys for Side-Effecting Operations

A common way to make POST retries safe is for the client to send a unique identifier in the Idempotency-Key header:

~~~http
POST /payments
Idempotency-Key: 8a8c7b2a-5a54-4a0c-b64c-3dbd7f0f4a21
Content-Type: application/json

{
  "orderId": "ORD-2026-0042",
  "amount": 1500000,
  "currency": "VND"
}
~~~

The client generates a key for **one business intent** and reuses that key across every retry of that intent. If the user initiates a new transaction, the client must generate a new key. Never generate a fresh key per retry, or the server cannot tell those requests belong to the same operation.

The server looks up the key within an appropriate scope, such as tenant or account + operation name + key. Once processed, the server saves the state and outcome so retries replay the recorded result instead of repeating side effects.

### 4.1. Lifecycle of an Idempotency Key

A basic design can use these states:

- IN_PROGRESS: the first request claimed processing rights for the key and is currently executing.
- COMPLETED: the business operation finished; the server stores status and response for replay.
- FAILED_FINAL: the operation failed in a way that should not be re-executed with the same payload, depending on the API contract.

Processing flow:

1. Authenticate caller and determine tenant/owner.
2. Check whether the key exists within the operation scope.
3. Compute a fingerprint from the meaningful business fields of the request.
4. If the key does not exist, insert an IN_PROGRESS record atomically or using a database unique constraint.
5. Execute the business operation.
6. Persist the final state, HTTP status code, and replayable response payload.
7. Upon receiving the same key and fingerprint again, return the saved result or report the in-progress status.
8. Upon receiving the same key with a different payload, reject it because the client misused the key.

An illustrative storage table:

~~~sql
CREATE TABLE idempotency_record (
    tenant_id       VARCHAR(100) NOT NULL,
    operation_name  VARCHAR(100) NOT NULL,
    idempotency_key VARCHAR(200) NOT NULL,
    request_hash    VARCHAR(128) NOT NULL,
    state           VARCHAR(20) NOT NULL,
    response_status INTEGER,
    response_body   TEXT,
    created_at      TIMESTAMP NOT NULL,
    updated_at      TIMESTAMP NOT NULL,
    PRIMARY KEY (tenant_id, operation_name, idempotency_key)
);
~~~

This is generic illustrative SQL; data types, indexes, and response storage must be adapted to your database and security policy. Do not store raw sensitive data or payment credentials in a response cache without justification and proper protection.

### 4.2. Unique Constraints Are the Real Concurrency Guard

Never implement idempotency solely with an in-memory Map in one application instance. With multiple instances or server restarts, instances will not know what keys another instance processed. Two concurrent requests could also both check "key does not exist" and both trigger side effects.

A database unique constraint, transactions, and insert-conflict handling ensure only one request wins the right to execute the key. Clearly define behavior for requests arriving while a key is IN_PROGRESS: wait briefly for the result, return 202 Accepted with a status lookup URL, or return 409 Conflict with a handleable error code. Document this behavior so clients know whether to poll or retry later.

If using a distributed cache, understand durability, atomicity, failover, and key-eviction risks. A cache can serve as a supporting layer only when business consistency guarantees still hold.

### 4.3. Disallow the Same Key with a Different Payload

If the same key arrives with a different payload, the server must never silently treat it as a new request. For example, the client sends key K1 for a 1,500,000 VND payment and accidentally reuses K1 for 2,000,000 VND. The server must detect the different request fingerprint and return a clear error, typically 409 Conflict or an error code defined by the API contract.

The fingerprint should hash business fields that affect the outcome. Canonicalize the representation before hashing so inconsequential differences such as JSON property ordering do not make equivalent requests look different. At the same time, never omit meaningful fields like currency, account, or destination.

### 4.4. Key Retention Time and Result Replay

Keys must be retained longer than the window during which clients can retry, including retries after app restarts or users reopening a screen. Deleting keys too early lets a late retry trigger duplicate side effects.

Retention depends on business needs and client contracts. Some APIs publish explicit idempotency windows. Once expired, clients must not assume the server still remembers the key. Clearly define:

- How long keys are retained.
- Which responses are replayed.
- How IN_PROGRESS keys are handled.
- Whether terminal errors are cached.
- How old records are purged without deleting active in-flight records.
- Behavior when the same key is sent after retention expires.

An idempotency key is neither a request ID nor a trace ID. A request ID identifies one request transmission; a trace ID links spans in an observability flow; an idempotency key identifies one business intent across multiple transmissions.

## 5. Side Effects Inside and Outside the Database

A database transaction guarantees atomic updates across tables within the same database, yet it does not automatically span external systems. For example:

1. Write the order to the database.
2. Call the payment gateway.
3. Send a confirmation email.

If the payment gateway call succeeds and the database update rolls back, the system can enter an inconsistent state. Retrying the entire transaction could re-send the payment charge.

Common solutions:

- **Provider-side idempotency**: pass the same idempotency key to the payment gateway or external service when supported.
- **Transactional outbox**: write the outbound event to an outbox table in the same transaction as business data; a worker dispatches events after commit.
- **Consumer inbox/deduplication**: the consumer records processed event IDs to ensure duplicate deliveries do not cause duplicate side effects.
- **Saga/compensation**: break multi-step workflows into steps with compensating actions on failure; compensation cannot always erase every prior side effect.
- **Reconciliation**: periodic reconciliation against external systems to resolve ambiguous states.

Never promise "exactly once" merely because a message broker or retries exist. In distributed systems, delivery can repeat; the practical goal is safe duplicate handling via idempotency, deduplication, transaction boundaries, and reconciliation.

## 6. When Should You Retry?

Only retry errors that are plausibly transient and where a subsequent attempt has reason to succeed. Common cases to evaluate:

| Error / outcome | Retryable? | Conditions |
|---|---|---|
| Transient DNS or connection error | Possibly | Confirm the request caused no side effect or the operation has idempotency protection. |
| Response read timeout | Possibly | For non-idempotent operations, deduplication or status lookup is mandatory before re-issuing. |
| HTTP 408 Request Timeout | Possibly | Respect the overall deadline and ensure safe repeatability. |
| HTTP 429 Too Many Requests | Possibly | Honor Retry-After, bound retries, and shed load. |
| HTTP 500 Internal Server Error | Case by case | Retry only if potentially transient; deterministic business errors or bugs will not self-heal. |
| HTTP 502, 503, 504 | Possibly | Often transient gateway/service issues; still require idempotency and a deadline. |
| HTTP 400, 401, 403, 404, 422 | Usually no | Fix payload, authentication, authorization, or resource first before resending. |
| HTTP 409 Conflict | Depends on contract | Could be a version conflict, in-progress key, or business conflict; do not retry blindly. |
| HTTP 501 Not Implemented | Usually no | Server lacks the capability; retrying the same request will not change that. |

This list is guidance, not a universal rule for every API. A 500 can occur after side effects committed; 409 can indicate an in-progress idempotency key needing polling; 429 can include Retry-After. Always follow the target service's error codes and documentation.

### 6.1. Backoff, Jitter, and Retry Limits

If many clients retry simultaneously, traffic can spike and prevent a struggling service from recovering. Use exponential backoff to widen wait intervals and jitter to spread out retry timing.

A reference formula:

\[
delay_n = \min(cap,\ base \times 2^n \times random(0.5,\ 1.5))
\]

Where n is the retry attempt count so far, base is the initial wait, and cap is the maximum delay. Real systems may use other jitter strategies, provided both upper and lower bounds exist.

A retry policy needs:

- Maximum attempts, specifying clearly whether the initial call counts toward the total.
- An overall deadline for the entire operation.
- Per-attempt timeouts.
- Backoff and jitter bounds.
- An allowlist of retryable exceptions/statuses.
- Logic honoring Retry-After.
- Concurrency limits and retry budgets to prevent load amplification.
- Logs/metrics distinguishing initial calls from retries.

Never configure a high retry count without considering the overall deadline. For example, a 5-second per-attempt timeout with 4 retries plus backoff can stretch a single request to tens of seconds—exceeding user patience or gateway deadlines.

### 6.2. Avoid Stacked Retries Across Layers

If the frontend retries 3 times, the gateway retries 3 times, and an internal service retries 3 times, a single action can multiply up to 27 calls at the deepest layer. Decide which layer owns retries for each error class. Other layers should propagate deadlines, honor cancellation, and avoid adding extra retries without an explicit contract.

Circuit breakers, bulkheads, and rate limits complement retries. Retries handle transient failures; circuit breakers pause calls to failing services; bulkheads isolate resource pools per dependency; rate limits protect capacity. They solve distinct problems and must work together.

## 7. Applying This in Spring Boot Applications

### 7.1. Payment Creation API Accepting Idempotency-Key

A controller can require the key in a header:

~~~java
@RestController
@RequestMapping("/payments")
class PaymentController {

    private final PaymentService payments;

    PaymentController(PaymentService payments) {
        this.payments = payments;
    }

    @PostMapping
    ResponseEntity<PaymentResponse> create(
            @RequestHeader("Idempotency-Key") String key,
            @Valid @RequestBody CreatePaymentRequest request) {

        PaymentResponse response = payments.createOnce(key, request);
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }
}
~~~

This is an illustrative Spring MVC snippet. The PaymentService, PaymentResponse, and CreatePaymentRequest types belong to the application. In production, the controller or service must also authenticate the caller, bound key length/format, check authorization, and return appropriate statuses when a key is in progress or reused with a different payload.

The service must execute key checks and outcome persistence in the persistence layer. Do not put idempotency logic solely in the controller because other call paths could bypass it. Nor should you rely on synchronized blocks or static variables as the primary guard across multiple instances.

### 7.2. Structuring Transactions

When side effects are purely writes inside one relational database, creating the idempotency record, updating business tables, and saving the outcome can be coordinated in a suitable transaction. A unique constraint protects concurrent requests sharing a key. When the second request hits a duplicate-key error, the service reads the existing record and returns the saved outcome or in-progress status.

Note that long transactions holding locks hurt throughput. When business flows call external systems, do not hold a database transaction open across network waits. Use an outbox or stateful workflow to separate database commits from outbound calls.

### 7.3. Retrying an HTTP Call with WebClient

The snippet below illustrates bounded retries for a POST call carrying an idempotency key, retrying only selected errors:

~~~java
Mono<PaymentResult> submitPayment(
        WebClient webClient,
        PaymentCommand command,
        String idempotencyKey) {

    return webClient.post()
            .uri("/payments")
            .header("Idempotency-Key", idempotencyKey)
            .bodyValue(command)
            .retrieve()
            .bodyToMono(PaymentResult.class)
            .retryWhen(Retry.backoff(3, Duration.ofMillis(200))
                    .maxBackoff(Duration.ofSeconds(2))
                    .jitter(0.5)
                    .filter(this::isTransientFailure));
}

private boolean isTransientFailure(Throwable error) {
    if (error instanceof WebClientResponseException response) {
        int status = response.getStatusCode().value();
        return status == 408
                || status == 429
                || status == 502
                || status == 503
                || status == 504;
    }
    return error instanceof WebClientRequestException;
}
~~~

This snippet requires Reactor, Spring WebFlux, and application PaymentCommand/PaymentResult types. It does not yet handle Retry-After, overall deadlines, retry budgets, or payload replayability; add those policies before production use. For POST, keep the key identical across every retry. Never retry a side-effecting request if the server does not support idempotency.

With RestClient or other synchronous clients, implement retries at the service boundary or via an appropriate resilience library. Classify exceptions accurately, do not retry validation/authentication errors, and prevent unexpected multi-layer retry amplification.

### 7.4. Distinguishing Errors in Responses

APIs should return stable error responses, for example:

~~~json
{
  "code": "IDEMPOTENCY_KEY_REUSED",
  "message": "The idempotency key was already used with a different request.",
  "traceId": "..."
}
~~~

traceId supports observability and troubleshooting; never use it as an idempotency key. Clients should inspect code and HTTP status to decide their next step. Never expose stack traces, database details, or secrets in responses.

## 8. Testing Idempotency and Retries

A test that calls an endpoint once does not prove the API handles retries safely. Test failure and concurrency scenarios:

1. Send the same PUT twice; the final state must match the requested representation.
2. Send DELETE twice; the resource remains deleted per the API contract.
3. Send the same POST with the same idempotency key twice; only one payment/order is created and the second call receives the saved result or defined status.
4. Send the same key with a different payload; the server must reject it.
5. Send two concurrent requests with the same key to different instances; only one request may produce the side effect.
6. Simulate server commit succeeding while the response is lost; retrying must not create a second side effect.
7. Simulate an IN_PROGRESS key; the client receives the expected wait, polling, or conflict response.
8. Simulate 429 with Retry-After; the client respects the retry delay and stays within deadline.
9. Simulate 400/401/403/422; the client does not blindly retry.
10. Restart the service or route retries to another instance; idempotency still holds because state is persisted durably.
11. Test key expiration and the effect of late retries.
12. Test outbox/consumers when the same event is delivered multiple times.

Concurrency tests should run against a real database or production-like integration environment. Tests with mocked repositories alone cannot prove unique constraints and transactions behave properly under parallel load.

## 9. Observability and Operations

Track separate metrics for:

- Initial requests vs. retry attempts.
- Retry success rate after transient errors.
- Replayed keys, IN_PROGRESS keys, and keys reused with different payloads.
- Timeout, 429, and 5xx rates plus per-dependency wait times.
- Deduplicated side effects.
- Age of in-progress records and expired idempotency records.
- Retry exhaustion, open circuit breakers, and retry budget consumption.

Logs should include trace ID, request ID, operation, retry status, attempt number, and a masked or hashed key identifier if keys could contain sensitive data. Avoid logging full payment payloads or personal data. Metrics must keep bounded cardinality; never attach unique idempotency keys as metric labels, which causes time-series explosion.

When investigating a timed-out transaction, look up the business state and idempotency record. Clients should never infer from "no response received" that "the transaction failed." Provide a status-lookup endpoint if callers or users need to learn the final outcome.

## 10. Design Checklist Before Enabling Retries

- [ ] Identify the method and operation semantics: safe, idempotent, or repeating side effects.
- [ ] Identify all side effects inside the database and in external systems.
- [ ] For POST or non-idempotent operations, define an idempotency key and uniqueness scope.
- [ ] Enforce a unique constraint in the persistence layer and handle concurrent requests.
- [ ] Compute a request fingerprint to detect key reuse with a different payload.
- [ ] Specify key retention duration, IN_PROGRESS handling, and response replay behavior.
- [ ] Retry only plausibly transient errors; never retry validation/authentication failures by default.
- [ ] Configure max attempts, timeouts, deadlines, exponential backoff, jitter, and Retry-After handling.
- [ ] Prevent stacked retries across layers and bound the retry budget.
- [ ] Test scenarios where the server commits but the response is lost.
- [ ] Test concurrent duplicate requests, restarts, and multiple instances.
- [ ] Monitor retries, deduplication, timeouts, and side effects in production.

## 11. Principles to Remember

HTTP methods give clients semantics for whether a request can repeat, yet they do not automatically protect every business workflow. GET normally fits retries; PUT and DELETE carry idempotent semantics; POST and PATCH require examining the specific contract. When a client times out, the outcome is ambiguous because the server may have already performed side effects while the response was lost.

For creating orders, processing payments, or issuing external commands, identify each business intent with an idempotency key, persist state durably, guard concurrency with unique constraints, and replay recorded outcomes. Apply retries only to transient failures with backoff/jitter, deadlines, and load bounds. Designing this way improves system resilience without turning a network glitch into duplicate transactions.
