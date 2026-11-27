# Distinguishing Read Retries from Resending Create or Update Operations

## Objectives

After this lesson, you will be able to:

- Explain why GET can generally be retried more safely than write operations.
- Distinguish safe and idempotent properties of HTTP methods.
- Recognize timeout scenarios where the client does not know whether the server already executed a write operation.
- Design bounded retries with backoff and Retry-After handling.
- Prevent duplicate record creation using idempotency keys or business key identifiers.
- Use ETag and If-Match to avoid overwriting someone else's updates.

## 1. Retrying is not the same as resending every request

Retrying means a client resends a request after a previous attempt encountered a transient failure or an unclear outcome. This is helpful when the network flickers, the server is overloaded, or a downstream dependency is temporarily unavailable.

However, before retrying, two questions must be answered:

1. Could the previous request already have been executed by the server?
2. If the same request is sent again, will data state be mutated an additional time?

For read requests, resending usually creates no additional records and triggers no extra business actions. For create or update requests, the server may have committed the transaction even though the response was lost on the way back to the client. Blindly resending can create duplicate records, trigger repeated side effects, or overwrite a newer change.

In Spring Data REST, clearly distinguish collection resources used to create entities, item resources used to read/update entities, and association resources used to access relationships. Clients should discover URLs from HAL links when possible, and apply retries according to HTTP method semantics and the API contract.

## 2. Safe and idempotent in HTTP

Two commonly confused concepts:

- **Safe**: the request is defined as read-only and does not ask the server to alter resource state.
- **Idempotent**: executing the same request one or more times has the same intended effect on server state as executing it once.

| Method | Safe | Idempotent per HTTP | Meaning for retries |
|---|---|---|---|
| GET | Yes | Yes | Usually safe to retry on transient failures |
| HEAD | Yes | Yes | Similar to GET but returns no body |
| OPTIONS | Yes | Yes | Can be retried when reading capabilities |
| PUT | No | Yes | Can repeat the same resource-replacement intent, but concurrency and application side effects must be considered |
| DELETE | No | Yes | The deletion effect is achieved after the first call; subsequent responses may differ |
| POST | No | Not by default | Risks creating duplicate resources or repeating business actions |
| PATCH | No | Not by default | Depends on the patch contents and server implementation |

Idempotency refers to the intended effect on resource state, not a guarantee that every response is identical. For instance, a first GET may return older data and the next GET may return newer data updated by another user.

A repeated PUT may return a different status or emit additional logs, audit records, or notifications if the application executes side effects per request. Therefore, HTTP semantics form the baseline for retry design, while the business contract and implementation still need verification.

## 3. Retrying read requests with GET

GET is both safe and idempotent. If a client fails to receive a response due to network errors or temporary server overload, resending GET normally does not mutate data.

Example reading an item resource:

~~~http
GET /orders/42
Accept: application/hal+json
~~~

Or reading an association:

~~~http
GET /orders/42/customer
Accept: application/hal+json
~~~

Clients can retry on transient failures such as:

- Connection dropped before receiving a response.
- Connect timeout or read timeout.
- HTTP 408 Request Timeout.
- HTTP 429 Too Many Requests, honoring Retry-After if provided.
- HTTP 502, 503, or 504 in gateway/proxy infrastructure.

Do not retry indefinitely. Enforce a maximum attempt count, an overall deadline, and increasing wait intervals. If a response includes Retry-After, the client must respect the wait duration requested by the server.

Example read command:

~~~bash
curl -i -H "Accept: application/hal+json" \
  "http://localhost:8080/orders/42"
~~~

This request can be rerun on transient errors. If the first attempt succeeded and the response was lost, the subsequent GET simply reads the current state.

Note: GET may return different data across two calls if the underlying data changed. Idempotent does not mean responses are immutable; it means the request introduces no additional write effect on resource state.

## 4. Resource-creating POST: timeouts can create duplicate records

Spring Data REST typically publishes collection resources for creating entities via POST:

~~~http
POST /orders
Content-Type: application/json
Accept: application/hal+json

{
  "status": "CREATED",
  "reference": "WEB-2026-0042"
}
~~~

On success, the server normally returns HTTP 201 Created and a Location header pointing to the newly created item resource.

A dangerous scenario:

1. Client sends POST.
2. Server receives the request, creates the order, and commits the transaction.
3. Server sends the 201 response.
4. Connection drops before the client receives the response.
5. Client sees only a timeout and does not know the order was created.
6. Client resends POST; the server may create a second order.

A client timeout does not prove the server never processed the request. This is why POST must not be retried automatically and blindly.

After a POST with an ambiguous outcome:

- Retain the request payload and business reference identifier.
- Check state via a GET/search resource that looks up by the business reference if supported by the API.
- If the created resource is found, use its Location/self link and do not create it again.
- If the outcome remains undetermined, keep the operation status as **UNKNOWN/PENDING_RECONCILIATION** and continue reconciling per the API contract.
- Resend POST only when there is proof the prior attempt was not executed or when the endpoint supports a deduplication mechanism.

Do not treat a single GET not yet returning the record as absolute proof that POST failed if the system uses eventual consistency, asynchronous indexing, or queries hitting a lagging read replica.

## 5. Idempotency keys to prevent duplicate creation

For workflows requiring safe POST retries, a common solution is an idempotency key. The client generates a unique key for a single business intent and sends the same key on every retry of that intent.

Example:

~~~http
POST /api/orders
Content-Type: application/json
Idempotency-Key: 7e7f4f2a-5df7-4dc1-8e8f-9d4eaf9a1f31

{
  "reference": "WEB-2026-0042",
  "status": "CREATED"
}
~~~

The server must actively implement this contract. Merely sending an **Idempotency-Key** header does not automatically make Spring Data REST or HTTP deduplicate creation requests.

A server-side implementation typically needs to:

1. Accept the key in the request and define its scope, such as per tenant or user.
2. Persist the key along with a request hash, processing state, and created outcome.
3. Enforce a unique constraint on the key in the database so concurrent requests cannot produce two results.
4. Perform key recording and resource creation within a transaction or equivalent synchronization mechanism.
5. If the key already completed with the same payload, return the stored result, such as the status and Location of the original resource.
6. If the key was reused with a different payload, reject it per an explicit contract, typically as a conflict.
7. Retain keys long enough to cover the retry and reconciliation window.

One creation intent must reuse the exact same key across retries. An independent new creation operation must use a new key. If the client generates a fresh UUID on every retry, deduplication will not work.

A unique business key, such as an order code from an upstream system, can also prevent duplicates at the data layer. This is a valuable safeguard even when the API already enforces idempotency keys.

## 6. PUT for updating resources

PUT is defined as idempotent: resending the same content to the same URI has the same intended effect on resource state.

Example replacing an item's representation:

~~~http
PUT /orders/42
Content-Type: application/json
Accept: application/hal+json

{
  "status": "PAID",
  "reference": "WEB-2026-0042"
}
~~~

If the first request succeeded and the response was lost, resending the same PUT normally leaves the resource in the same desired state. Still, keep these points in mind:

- The payload must preserve the exact update intent; do not rebuild a new payload from stale data arbitrarily.
- PUT typically replaces the representation per the endpoint's semantics; fields omitted from the payload may behave differently than with PATCH.
- An application may emit notifications, write audits, or trigger side effects on every handled request. Design such side effects to be idempotent if clients can retry.
- Another user may update the resource between attempts. Resending an older payload could then overwrite newer data.

Use PUT only when the endpoint and contract permit replacing the resource in that manner. With Spring Data REST, verify the exact item URI and media types supported by the API.

## 7. PATCH for partial updates: inspect the patch payload

PATCH is not guaranteed to be idempotent under HTTP. A patch may or may not be idempotent depending on the operation it expresses.

Example setting a field to a fixed value:

~~~http
PATCH /orders/42
Content-Type: application/merge-patch+json

{
  "status": "PAID"
}
~~~

If the same patch is sent again, status remains PAID. This operation has an idempotent effect assuming no extra side effects.

Conversely, an operation like "increment quantity by 1" or "append an item to a list" can apply the effect multiple times if resent. A JSON Patch using an add operation at the end of an array requires particular caution.

With PATCH, ask:

- Does the patch assign a deterministic value or apply a relative transformation?
- Will resending the patch append elements, increment/decrement numbers, or re-trigger an action?
- Can the server return current state so the client can reconcile?
- Are ETag/If-Match needed to protect the resource version?

If a patch cannot be proven idempotent, do not retry automatically after an ambiguous timeout. Read the resource again and reconcile before deciding.

## 8. ETag and If-Match to avoid overwriting newer updates

Spring Data REST can apply optimistic locking when an entity has a version property marked with **@Version**. Item responses can include an ETag so clients know the representation version.

Entity example:

~~~java
@Entity
public class PurchaseOrder {

    @Id
    @GeneratedValue
    private Long id;

    @Version
    private Long version;

    private OrderStatus status;
}
~~~

The client reads the resource and receives:

~~~http
GET /orders/42
Accept: application/hal+json
~~~

~~~http
HTTP/1.1 200 OK
ETag: "5"
~~~

When updating, the client sends the version precondition:

~~~http
PUT /orders/42
If-Match: "5"
Content-Type: application/json

{
  "status": "PAID"
}
~~~

If another client has updated the resource and the current ETag is no longer "5", the server can return HTTP 412 Precondition Failed. This prevents the client from overwriting a newer version with stale data.

When receiving 412:

1. Do not retry the same request with the old ETag.
2. GET the item resource again.
3. Compare the new state against the business intent.
4. Recompute the necessary change.
5. Send a new request with the new ETag if the business operation is still valid.

ETag and If-Match must be supported and properly configured on the endpoint. Never guess ETag values or strip the version condition just to make a retry succeed.

## 9. Classifying errors before retrying

Not every HTTP error is a transient error.

| Situation | Handling guidance |
|---|---|
| DNS/connect failure, reset, or timeout | For GET, bounded retries are allowed; for writes, determine whether the request might already have been processed |
| 408 Request Timeout | Can be retried per policy; for writes, account for ambiguous outcomes |
| 429 Too Many Requests | Wait per Retry-After if present, then retry within bounds |
| 502, 503, 504 | Usually transient failures; apply backoff and deadlines |
| 500 Internal Server Error | Could be transient or a business/server bug; for writes, reconcile before resending |
| 400 Bad Request / 422 Unprocessable Content | Fix payload or validation; do not retry the same request |
| 401 Unauthorized | Refresh credentials via the security mechanism, then re-evaluate the request |
| 403 Forbidden | Check permissions; retrying the same request usually will not resolve it |
| 404 Not Found | Check URI/resource; do not retry indefinitely |
| 409 Conflict | Read state and handle the business conflict |
| 412 Precondition Failed | GET the latest version, recompute changes, and use the new ETag |

For writes, both 500 and timeouts can happen after a transaction has already committed. Therefore, a client-side status code or exception is not always sufficient to conclude the operation did not occur.

## 10. Backoff, jitter, and retry bounds

If many clients retry immediately when a server is overloaded, traffic spikes can worsen the outage. Use exponential backoff to increase delays across attempts and add jitter so clients do not synchronize retries at the same instant.

Illustrative retry schedule:

| Next attempt | Base wait |
|---|---:|
| Attempt 2 | 200 ms |
| Attempt 3 | 400 ms |
| Attempt 4 | 800 ms |
| Attempt 5 | 1,600 ms |

Actual wait times can include random jitter and must honor Retry-After when supplied by the server.

A retry policy should define:

- Maximum number of attempts.
- Overall deadline for the entire request.
- Bounded backoff with jitter.
- Allowlist of retryable errors.
- Separate rules for GET, POST, PUT, and PATCH.
- Logging of attempts, request correlation IDs, and reconciliation outcomes.
- A circuit breaker or concurrency cap when a service fails continuously.

Do not retry validation errors, invalid data, permission denials, or conflicts requiring business handling.

## 11. Client decision flow

The following workflow can be applied:

1. Identify the HTTP method and business semantics of the request.
2. If GET/HEAD, perform bounded retries on transient errors.
3. If PUT/DELETE, confirm the operation is idempotent per contract and enforce concurrency control; after timeouts, still account for side effects.
4. If POST, check whether the API provides an idempotency key or unique business key.
5. If PATCH, evaluate whether the patch can be repeated safely.
6. If a write times out or loses its response, mark the outcome unknown and reconcile via GET/search or business state.
7. Resend a write only when deduplication is established or the previous attempt is proven not to have executed.
8. When using optimistic locking, re-GET the ETag and recompute the update if 412 is returned.

Pseudocode:

~~~text
send(request)

if response received:
    handle response and status

else if request is a read:
    retry with bounded backoff when failure is transient

else if request is a write:
    mark outcome as UNKNOWN
    reconcile current resource/business state

    if operation is already applied:
        use the existing result; do not repeat the mutation

    else if the API provides idempotency protection:
        retry with the same idempotency key

    else:
        do not blindly resend
        escalate or follow the API's reconciliation contract
~~~

## 12. Practicing with curl

Read an item resource:

~~~bash
curl -i \
  -H "Accept: application/hal+json" \
  http://localhost:8080/orders/42
~~~

Create a resource via a collection resource:

~~~bash
curl -i -X POST \
  -H "Content-Type: application/json" \
  -H "Accept: application/hal+json" \
  -d '{"reference":"WEB-2026-0042","status":"CREATED"}' \
  http://localhost:8080/orders
~~~

Add an idempotency key header only if your application's custom API implements and documents that mechanism:

~~~bash
curl -i -X POST \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: 7e7f4f2a-5df7-4dc1-8e8f-9d4eaf9a1f31" \
  -d '{"reference":"WEB-2026-0042","status":"CREATED"}' \
  http://localhost:8080/api/orders
~~~

Partially update a resource:

~~~bash
curl -i -X PATCH \
  -H "Content-Type: application/merge-patch+json" \
  -d '{"status":"PAID"}' \
  http://localhost:8080/orders/42
~~~

During practice, simulate a case where the server processes the request but the client loses the response. Check record counts in the database and the resource state before deciding to resend. Never run a POST retry loop against production data just for testing.

## 13. Self-study exercises

1. Why can a timed-out GET usually be resent, whereas a timed-out order-creation POST requires reconciliation first?
2. Distinguish safe from idempotent. Why is PUT idempotent but not safe?
3. If the server commits a POST but the 201 response is lost, what consequences can occur if the client resends?
4. Design an idempotency key for an order-creation API: where is the key generated, how is it stored, and how are two concurrent requests handled?
5. Compare a PATCH assigning a fixed status with a PATCH incrementing quantity by one unit. Which operation can be repeated safely?
6. A PUT times out and a subsequent GET shows the resource is already in the desired state. How should the client proceed?
7. When receiving 412 Precondition Failed, why should you not resend the payload with the old ETag?
8. Design a retry policy incorporating exponential backoff, jitter, Retry-After, attempt limits, and a deadline.

**Remember:** Retrying GET is usually safe because the request is read-only. For POST, PATCH, and even PUT, clients must evaluate operation semantics, whether the server may have committed, side effects, and version conflicts. When a write outcome is ambiguous, reconcile state; use idempotency keys where duplicate creation must be prevented and ETag/If-Match to protect concurrent updates.

## References

- [RFC 9110 — HTTP Semantics: Safe and Idempotent Methods](https://www.rfc-editor.org/rfc/rfc9110.html)
- [RFC 5789 — PATCH Method for HTTP](https://www.rfc-editor.org/rfc/rfc5789.html)
- [Spring Data REST Reference](https://docs.spring.io/spring-data/rest/reference/)
- [Spring Data REST — Conditional Operations and ETags](https://docs.spring.io/spring-data/rest/reference/etags-and-other-conditionals.html)
