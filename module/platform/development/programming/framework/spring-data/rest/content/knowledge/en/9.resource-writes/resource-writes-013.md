# HTTP Method Idempotency and the Risks of Retrying Write Requests

In Spring Data REST, repositories are commonly exposed as HTTP resources. Clients can read collections, create new entities, update an entity, or delete resources through methods such as GET, POST, PUT, PATCH, and DELETE. When the network is flaky, a client may retry a request after a timeout. Without understanding method idempotency and endpoint contracts, retrying can create duplicate data, trigger duplicate payments, or send notifications multiple times.

Idempotency helps determine which requests can be safely retried at the level of their requested effect. It does not by itself guarantee that every side effect in the application happens only once.

## 1. What is idempotency?

An operation is **idempotent** when executing the same request once or repeating it multiple times produces the same intended effect on server state.

For example, setting an order's status to PAID is an operation that can be designed to be idempotent:

- The first request changes the status from PENDING to PAID.
- The second request again requests the status PAID.
- After both requests, the order status remains PAID.

Conversely, adding 100 points to an account is not idempotent:

- The first call increases points by 100.
- The second call increases points by another 100.
- Retrying the request alters the business outcome.

Three aspects must be distinguished:

1. **Resource state:** the final business data the request intends to establish.
2. **HTTP response:** status code, headers, and body returned by the server for each call.
3. **Secondary side effects:** logging, emitting events, sending emails, calling payment services, or updating other systems.

Two calls to an idempotent method are not required to return identical responses. For example, the first DELETE may return 204, while a subsequent call may return 404 because the resource no longer exists. What matters is that the intended effect on resource state remains equivalent: the resource remains nonexistent.

HTTP idempotency also does not mean all secondary side effects are automatically deduplicated. If every PUT triggers an email or a payment charge, the application can still send emails or charge money multiple times even though the resource state does not change across requests.

## 2. Distinguishing safe methods and idempotent methods

These two concepts are related but not synonymous.

- **Safe method:** a method defined for clients to request reading or observing data; the client does not ask the server to alter business state.
- **Idempotent method:** a method whose intended effect is the same whether the request is executed once or multiple times.

| HTTP method | Safe | Idempotent | Primary meaning |
|---|---|---|---|
| GET | Yes | Yes | Retrieve a resource representation |
| HEAD | Yes | Yes | Retrieve metadata/headers like GET, without returning a body |
| OPTIONS | Yes | Yes | Query communication options or capabilities |
| TRACE | Yes | Yes | Echo request information per TRACE semantics; often disabled for security reasons |
| PUT | No | Yes | Create or replace resource state at the target URI |
| DELETE | No | Yes | Request that the target resource no longer exist |
| POST | No | Not by default | Submit data for the resource to process, commonly to create a resource or perform an action |
| PATCH | No | Not guaranteed | Apply a partial change to a resource |
| CONNECT | No | No | Establish a tunnel to a destination |

Safe methods are also idempotent. PUT and DELETE are idempotent but not safe because they can change server state. POST and PATCH require examining the specific endpoint contract.

For custom HTTP methods or APIs with custom semantics, read the API contract instead of inferring behavior from method names alone.

## 3. Meaning of each method when working with Spring Data REST

Spring Data REST typically maps repositories to collection resources and item resources. For example, suppose a repository manages Order and the API exposes:

- Collection: /orders
- Item: /orders/42

Actual path names depend on the application's repository configuration, base path, and resource mapping.

### 3.1. POST: creating new items and the risk of duplicate records

POST to a collection is typically used to create a new entity.

~~~http
POST /orders
Content-Type: application/json

{
  "customerId": 17,
  "total": 250000
}
~~~

If the server already created the Order but the response was lost in transit, the client only sees a timeout. When the client retries POST, the server may create another Order. Two requests with the same body can still create two resources because each POST can be interpreted as a new creation request.

POST is not idempotent by default. Do not automatically retry POST simply because the client did not receive a response.

Common measures to prevent duplicates include:

- Server-supported idempotency keys.
- Unique business request codes backed by a database unique constraint.
- An operation resource with a stable ID so clients can query the result.
- Deduplication mechanisms in the business layer.

### 3.2. PUT: setting resource state at a known URI

PUT is typically used to create or replace the representation of a resource at a known URI.

~~~http
PUT /orders/42
Content-Type: application/json

{
  "customerId": 17,
  "total": 250000,
  "status": "PENDING"
}
~~~

If two identical PUT requests target /orders/42 with the same content, the resource state the client requests to set is the exact same state. Hence PUT is defined as idempotent.

Responses from the two calls can still differ. The first call might create the resource and return 201 Created; the second call might update the existing resource and return 200 OK or 204 No Content.

Do not use PUT as an accumulative command or to trigger a new side effect on every call. If PUT handling sends emails, publishes events without deduplication keys, or calls a billing service on every processed request, those side effects can still repeat.

### 3.3. PATCH: depends on the patch content

PATCH is used to apply a partial change to a resource. PATCH itself is not guaranteed to be idempotent; this property depends on the patch content and how the API processes it.

A patch setting a concrete value can be idempotent:

~~~http
PATCH /orders/42
Content-Type: application/merge-patch+json

{
  "status": "PAID"
}
~~~

Repeating the request to set status to PAID still aims for the same state.

A patch with cumulative semantics is not idempotent:

~~~http
PATCH /accounts/17
Content-Type: application/json

{
  "balanceDelta": 100
}
~~~

If the API interprets balanceDelta as adding 100, each retry will keep increasing the balance. Actual field names and semantics are defined by the application; this example illustrates a custom patch API.

Therefore, before retrying PATCH, know whether the patch document expresses setting a value or mutating state incrementally.

### 3.4. DELETE: deleting a resource

DELETE on an item resource requests that the target resource no longer exist.

~~~http
DELETE /orders/42
~~~

The first call may return 204 No Content. If resent after the resource has been deleted, the server may return 404 Not Found. The two responses differ, yet the target state remains that the resource does not exist, so DELETE has idempotent semantics.

DELETE's idempotency does not mean every action related to deletion runs only once. For example, a listener or event handler sending a notification email on each accepted delete request still needs side-effect control.

## 4. Why retrying write requests can cause bugs

A timeout does not prove the server has not executed the request. There are at least three scenarios:

1. The request never reached the server or was rejected before processing. The business operation did not occur.
2. The server processed and committed the transaction, but the response was lost in transit. The business operation already occurred.
3. The server is still processing when the client times out. The client does not yet know the final outcome.

The second scenario is especially dangerous for POST or non-idempotent operations.

Example of a client creating an order:

~~~text
Client                         Server
  |                              |
  | POST /orders                 |
  |----------------------------->|
  |                              | Create Order #101
  |                              | Commit transaction
  |         response 201         |
  |<--------- X -----------------| Response lost
  |                              |
  | Timeout                      |
  |                              |
  | POST /orders (retry)         |
  |----------------------------->|
  |                              | Create Order #102
  |<-----------------------------|
  |         response 201         |
~~~

The client intended to create one order, yet the database may end up containing two orders. If the same workflow also triggers payment or notifications, the consequences can be worse than duplicate records.

You cannot conclude a request failed just because the client did not receive a response. Clients need a way to determine whether the outcome committed before deciding to retry.

## 5. Retry rules by method

| Method | Guidance on timeout |
|---|---|
| GET, HEAD, OPTIONS | Generally safe to retry due to safe and idempotent semantics; still bound retries and handle infrastructure errors |
| PUT | Can retry with the same URI, same content, and same write conditions if the endpoint preserves idempotent semantics |
| DELETE | Can retry when the goal remains that the resource does not exist; handle 404 responses per the API contract |
| PATCH | Retry only when the patch operation is designed to be idempotent or has a deduplication mechanism |
| POST | Do not retry blindly; require an idempotency key, unique business code, or operation status query |

Principles that apply to all methods:

- Retries must keep the same identifier for a single business operation. Do not generate a new idempotency key per attempt.
- Keep the exact method, URI, payload, and preconditions from the initial attempt when semantics require it.
- Retry only likely transient errors, such as connection timeouts, 408, 429, 502, 503, or 504; honor Retry-After when the server sends that header.
- Do not repeatedly retry authentication, authorization, validation, or business errors without addressing the root cause.
- Use bounded retry counts, exponential backoff, and jitter to prevent many clients from retrying simultaneously.
- When the outcome is ambiguous, prefer querying resource or operation status before issuing a new write operation.

Method idempotency only protects the effect defined at the HTTP level. It does not replace checking side effects and business invariants of the endpoint.

## 6. Idempotency keys for POST and non-idempotent writes

When an API needs to let clients retry POST, an idempotency key mechanism can be added at the application layer. This is a contract convention between client and server; HTTP and Spring Data REST do not automatically handle this header unless the application implements it.

Example request:

~~~http
POST /orders
Content-Type: application/json
Idempotency-Key: 9f3c2b7e-8c1d-4f10-a8a1-7d2e8b9c0012

{
  "customerId": 17,
  "total": 250000
}
~~~

The client generates the key once per business action. On timeout, the client resends the same key and the same payload.

The server can implement the processing flow as follows:

1. Receive the key along with user/tenant identity, method, URI, and payload.
2. Compute a request fingerprint to verify whether the request content matches the first attempt.
3. Record the key with a unique constraint so two concurrent requests cannot both perform the side effect.
4. Perform the business change and store the processing result within the same transaction or a mechanism with equivalent consistency guarantees.
5. When receiving the same key with a matching fingerprint again, return the stored result or the status of the in-progress operation.
6. When receiving the same key with a different payload, reject the request per the API contract, typically with a conflict error.
7. Define key retention TTL, key scope, and handling when an operation has not yet completed.

An idempotency key storage table typically needs at least:

| Field | Purpose |
|---|---|
| key | Unique identifier of the operation |
| scope | User, tenant, or business scope |
| request fingerprint | Detects reusing the key with a different payload |
| status | IN_PROGRESS, SUCCEEDED, or FAILED per the processing model |
| response/result reference | Result that can be returned on retry |
| created_at / expires_at | Key lifecycle management |

Do not store the key only in cache and write to the database in an independent step without handling failures between the two steps. If the key is marked completed while the business transaction fails, or the transaction commits while the key is not saved, the system can return wrong results or create duplicate data.

For external side effects outside the database—such as sending emails, calling payment gateways, or publishing messages—add an outbox, provider-side idempotency keys, or consumer deduplication. A single database transaction alone cannot guarantee external side effects occur only once.

**Correlation IDs do not replace idempotency keys.** Correlation IDs link logs and traces across multiple components. Idempotency keys identify the same business operation across retries.

## 7. Combining conditional requests and optimistic locking

Idempotency solves repeating the same operation. It does not by itself resolve conflicts when multiple clients edit the same resource.

Suppose two clients both read Order #42 at a version with ETag "v7". Client A updates successfully and the resource moves to a new version. Client B still submits data based on the old version. If the API supports conditional requests, B can send:

~~~http
PUT /orders/42
If-Match: "v7"
Content-Type: application/json

{
  "status": "PAID"
}
~~~

The server accepts the update only if the current ETag still matches. If the resource changed, the server can return 412 Precondition Failed to prevent overwriting newer data.

Conditional requests and idempotency serve different goals:

- **If-Match / ETag:** prevents updates based on stale versions.
- **Idempotency key:** identifies the same operation across multiple submissions and prevents duplicate side effects.
- **Unique constraint:** protects a data invariant in the database, such as prohibiting duplicate order codes.

If the first PUT succeeded but the response was lost, retrying with the old If-Match may receive 412 because the version changed. That does not prove the first attempt failed. The client needs to GET the resource again or query the operation to reconcile the result. If the endpoint must return the exact response from the first attempt, combine it with an appropriate idempotency key mechanism.

Spring Data REST can participate in optimistic locking when resources and the application are configured to support versioning/ETags. Check the actual endpoint contract and how clients send preconditions; do not assume every repository resource already has this enabled.

## 8. Points to control in a Spring Data REST application

When designing write endpoints, inspect both repository operations and the logic running around them.

- **Repository event handlers:** handlers such as HandleAfterCreate, HandleAfterSave, or HandleAfterDelete can trigger side effects. Ensure handlers do not send duplicate notifications or spawn duplicate tasks on retry.
- **Entity listeners and domain events:** saving an entity can trigger additional logic. Determine whether an event represents a state transition or every incoming request.
- **Database constraints:** use unique constraints for business keys that must be unique. Database constraint checks protect data even when concurrent requests arrive simultaneously.
- **Transaction boundaries:** resource writes and idempotency records need an explicit transactional relationship. For messages or external services, consider a transactional outbox and consumer deduplication.
- **Optimistic locking:** use version/ETag and preconditions when needing to prevent overwriting another client's updates.
- **Response contract:** specify clearly whether retries return the original response, current state, or a conflict/precondition error.
- **Access control and key scoping:** never share keys across tenants or users if doing so could expose another operation's result.

Do not rely on the frontend accidentally not submitting twice to protect data. Clients can retry on timeouts, users can click buttons multiple times, proxies can retry per configuration, and multiple requests can arrive concurrently.

## 9. Design choice examples

| Need | Suitable design | What to avoid |
|---|---|---|
| Read order details | GET /orders/42 | Performing business writes in GET |
| Set order status to PAID | PUT or PATCH with value-setting semantics; optionally add If-Match | Turning the request into an accumulative or charge-per-call operation |
| Create a new order | POST with idempotency key or unique request code | Blindly retrying POST after timeout |
| Delete an order | DELETE with handling for already-absent resources | Sending repeated emails/refunds without deduplication |
| Credit an account balance | Business command with operation ID/idempotency key and appropriate transaction | Assuming PATCH is automatically idempotent |
| Update a resource with multiple clients | Version/ETag, If-Match, and conflict handling | Overwriting newer data with stale reads |

## 10. Design verification before enabling retries

For each write endpoint, answer these questions:

1. Which operation do the method and URI represent? Does the request set state or create a new action?
2. If resent with the exact method, URI, payload, and preconditions, does the final business state change further?
3. What side effects run when the request is processed: events, emails, payments, messages, or other service calls?
4. If the server commits but the response is lost, can the client determine the outcome via GET or an operation ID?
5. Do non-idempotent POST/PATCH endpoints have an idempotency key, unique constraint, or deduplication mechanism?
6. Can two concurrent requests with the same key trigger two business operations?
7. How is the same key with a different payload handled?
8. Do retries preserve the key and use bounded attempts, backoff, jitter, and Retry-After handling?
9. If using ETag/If-Match, how does the client handle 412 and reconcile results after a timeout?
10. Is deduplication controlled for messages or side effects outside the database transaction?

Test cases where the request succeeds on the server but the response is dropped, two requests with the same idempotency key arrive concurrently, the same key arrives with a different payload, retries occur after the resource was deleted, and retries use a stale ETag. These scenarios catch bugs that single-request happy-path tests often miss.

## Conclusion

Safe describes a client not requesting business state changes; idempotent describes an intended effect that stays unchanged when repeating the same request. GET, HEAD, OPTIONS, TRACE, PUT, and DELETE have idempotent semantics; POST is not idempotent by default, and PATCH depends on how the operation is defined.

When building APIs with Spring Data REST, evaluate resource state, responses, and side effects together. PUT/DELETE can be retried according to contract; POST/PATCH need idempotency or deduplication mechanisms when operations are not idempotent. A timeout only tells the client it has not received a response—it does not prove the server did not commit.