# Safe Repeatability of GET vs. Data-Mutating Operations

## 1. Why Can Retries Both Save a Request and Create Duplicate Data?

In a microservices system, **Spring Cloud Gateway** serves as the common entry point: it matches routes with predicates, executes filter chains, transforms paths/headers, discovers service instances, and forwards requests to backends. A request can encounter transient network glitches, timeouts, HTTP 502/503 responses, or an instance shutting down during deployment.

**Retry** means replaying an operation after a previous attempt did not yield an acceptable result. For `GET /api/catalog/products/42`, retrying after a transient failure is usually reasonable. For `POST /api/payments`, however, a timeout can happen **after the backend already debited the account**: replaying the POST can charge a second time.

The topic **"Safe Repeatability of GET vs. Data-Mutating Operations"** belongs to the **Request Retries** chapter, **Spring Cloud Gateway** module. This lesson explains how to:

1. Distinguish **safe**, **idempotent**, and "identical responses."
2. Evaluate GET against POST, PUT, DELETE, and PATCH under HTTP semantics and business logic.
3. Understand ambiguous states when the backend processed the request but the Gateway never received the response.
4. Configure `Retry GatewayFilter` for GET-only via YAML in Gateway Server WebFlux.
5. Protect write operations with **Idempotency-Key**, unique constraints, and state recovery.
6. Test how many times the upstream actually receives requests, along with backoff, body caching, timeouts, rate limiting, circuit breakers, TLS, and observability.

> **Scope:** Spring Cloud Gateway **Server WebFlux** and `Retry GatewayFilter`. Route examples illustrate both the newer `spring.cloud.gateway.server.webflux.routes` namespace and `spring.cloud.gateway.routes` commonly used in the 4.x branch. Server MVC is a different stack, particularly around caching/replaying request bodies; always check documentation for your exact version.

## 2. Safe and Idempotent Are Two Different Properties

### 2.1. Safe: The Client Requests Read-Only Semantics

According to **RFC 9110**, a *safe* method has primarily read-only semantics: the client is not requesting a state change on the resource. Methods defined as safe include **GET, HEAD, OPTIONS, TRACE**.

Example:

~~~http
GET /api/catalog/products/42 HTTP/1.1
Host: api.example.test
~~~

The client wants to view product 42. The system may still record access logs, metrics, or auxiliary view counts without violating the client's read-only intent. However, if an API implements `GET /api/payments/charge?id=42` to **actually debit money**, that endpoint violates HTTP semantics; it must never be treated as safe to retry just because the method is GET.

### 2.2. Idempotent: Repeating Has the Same Intended Effect

A request is *idempotent* if executing the **same request multiple times** has the same intended effect on the resource as executing it once.

Example:

~~~http
PUT /api/users/42/settings HTTP/1.1
Content-Type: application/json

{"language":"en","darkMode":true}
~~~

If PUT genuinely **sets** the settings value, two identical PUTs leave the final state identical to one PUT. On the other hand:

~~~http
POST /api/wallets/42/credits HTTP/1.1
Content-Type: application/json

{"amount":100000}
~~~

If POST means **add 100,000**, repeating it twice adds 200,000. An identical payload does not mean the operation is deduplicated.

### 2.3. HTTP Methods Comparison Table

| Method | Safe per HTTP? | Idempotent per HTTP? | Guidance When Considering Retries |
| --- | --- | --- | --- |
| **GET** | Yes | Yes | Usually the first candidate, if the endpoint is genuinely read-only |
| **HEAD** | Yes | Yes | Usually suitable for transient failures |
| **OPTIONS** | Yes | Yes | Semantically possible, but enable only when truly needed |
| **TRACE** | Yes per spec | Yes | Disabled by many systems for security; do not enable automatically |
| **PUT** | No | Yes | Requires proper semantics and protection for secondary side effects and version/concurrency |
| **DELETE** | No | Yes | Must ensure deletion effect and secondary side effects are not duplicated |
| **POST** | No | Not guaranteed | **Do not auto-retry** without idempotency/dedup |
| **PATCH** | No | Not guaranteed | Inspect per operation; some patches are idempotent, others are not |

**Idempotent does not mean identical responses.** A first DELETE may return 204 and the next 404, yet the resource is in the "non-existent" state either way. A repeated GET may return a new price because someone else updated the data; the GET operation itself still did not ask to mutate state.

### 2.4. Do Not Equate GET with Immutable Data

GET is safe/idempotent under the HTTP contract, yet responses can change over time, by user, or by version. If business logic needs version consistency, design ETags/conditional requests, snapshots, or proper version control; **Retry does not provide transaction isolation**.

## 3. How Are Write Operations Risky?

### 3.1. POST Creating an Order or Payment

~~~http
POST /api/orders HTTP/1.1
Content-Type: application/json

{"customerId":"u-42","items":[{"sku":"book-1","quantity":1}]}
~~~

Suppose order-service creates `orderId=1001`, yet the Gateway loses the connection before receiving the response. If the Gateway automatically retries POST, the service may create `orderId=1002`. The client sees one browser request, while the database holds two orders.

What matters is the **business effect**, not whether the JSON bytes match.

### 3.2. PUT Is Idempotent, Yet Does Not Automatically Guard Every Side Effect

~~~http
PUT /api/users/42/profile HTTP/1.1
Content-Type: application/json

{"displayName":"Lan"}
~~~

If the backend always **sets** `displayName` to Lan, the core state is idempotent. However:

- Sending a "Profile Updated" email **on every attempt** can send two emails.
- Publishing two un-deduplicated Kafka events can trigger duplicate consumer side effects.
- A handler that improperly **increments a revision counter** can break idempotency.
- Under concurrent edits, retrying a stale PUT can overwrite newer data.

For versioned state, consider `If-Match` and ETags. If the server returns `412 Precondition Failed`, do not blindly retry a PUT to bypass version checks.

### 3.3. DELETE Is State-Idempotent, Yet Can Fail on Secondary Events

~~~http
DELETE /api/carts/42/items/7 HTTP/1.1
~~~

Repeating a DELETE may still leave the item "deleted," yet if the handler enqueues two refund jobs or two domain events leading to charges/refunds, the system still breaks. Retrying write requests requires examining **all significant consequences**, not just the primary database row.

### 3.4. PATCH Depends on the Operation

A PATCH that "sets status to PAID" may be idempotent by design; a PATCH that "increments stock by 1" typically is not. Never infer retry safety solely from the PATCH method; check the operation contract, transaction, and versioning.

## 4. Timeout: The Gateway Cannot Know for Certain Whether the Backend Committed

A dangerous case is an **ambiguous outcome**: the backend finished processing, yet the response was lost.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant G as Gateway
    participant S as payment-service
    participant D as Database
    C->>G: POST /api/payments
    G->>S: POST /payments
    S->>D: COMMIT payment P-1001
    D-->>S: OK
    Note over G,S: Connection lost before response
    G-->>C: 504 / timeout error
    Note over G,C: No proof payment was not created
    C->>G: Resend POST with same body, no dedup
    G->>S: POST /payments 2nd time
    S->>D: COMMIT payment P-1002
~~~

When a `TimeoutException` or `504 Gateway Timeout` occurs, **it does not mean the backend did not process the request**. Different failure points carry different risks:

| Failure Point | What the Gateway Sees | What Can Be Concluded |
| --- | --- | --- |
| DNS fails before sending request | Unknown host | Never connected to that destination |
| TCP connect refused before sending | Connect error | Typically no business call reached this instance |
| Partial body sent then connection drops | I/O error | Uncertain whether backend applied anything |
| Backend commits successfully, response lost | Timeout/504 | Side effect **may already have happened** |
| Intermediate proxy returns 502/503 | HTTP error | Uncertain whether final endpoint processed it |
| Response already began streaming to client | Response committed | Cannot act as if no response existed to cleanly retry |

**Safety principle:** for **non-idempotent** operations, never replay automatically without a contractual idempotency guarantee or proof that the request was never applied. RFC 9110 also notes limits on automatic retries for non-idempotent requests.

## 5. `Retry GatewayFilter` in Spring Cloud Gateway

### 5.1. What Happens When Adding Retry to a Route?

In **Spring Cloud Gateway Server WebFlux**, `Retry` is a **GatewayFilter factory**. It can re-execute the **downstream portion of the filter chain** when the response status or exception matches the policy.

~~~mermaid
flowchart TD
    C["Client request"] --> P{"Route predicate?"}
    P -->|"Matches"| R["Retry GatewayFilter"]
    P -->|"No"| N["Other route / no route"]
    R --> F["Downstream filters + HTTP routing"]
    F --> O{"Attempt result"}
    O -->|"Success or non-retryable"| A["Final response"]
    O -->|"Matching error and retries left"| B["Wait backoff"]
    O -->|"Retry budget exhausted"| A
    B --> F
~~~

**Keep in mind:** filters **after Retry** may execute multiple times. Spring Security's `WebFilter` outside the Gateway route chain does not automatically re-run the same way. Custom filters downstream of Retry that log, increment counters, mutate headers, or call external systems must tolerate multiple executions.

### 5.2. Parameters and Defaults

| Parameter | Purpose | Notes |
| --- | --- | --- |
| `retries` | Number of **additional retry attempts**, excluding first call | `retries: 2` → up to 3 attempts |
| `methods` | Specifies HTTP methods eligible for retry | Filter default when enabled is **GET** |
| `series` | HTTP status series to retry | Defaults to **5xx** series |
| `statuses` | Specific statuses to retry | Must be evaluated alongside active `series` |
| `exceptions` | Exception types triggering retry | WebFlux docs list defaults `IOException`, `TimeoutException` |
| `backoff` | Delay between attempts | Disabled by default |
| `jitter` | Random variation on backoff | Available in newer releases; verify version |
| `timeout` | Time limit within Retry mechanism | Version-dependent; do not confuse with end-to-end timeout |

Spring Cloud Gateway WebFlux docs describe notable defaults when Retry is attached: **3 retries**, **GET**, **5xx series**, **IOException/TimeoutException**, and **no backoff**. Thus a single request can generate up to **4 attempts** if each matches policy and is not stopped early.

Not every GET route retries automatically: **the `Retry` filter must be attached** to the route or configured via a dedicated mechanism.

### 5.3. Status Code vs. Exception

- **Status-based retry:** backend/proxy returns a response like `502` or `503`; Retry evaluates `series` or `statuses`.
- **Exception-based retry:** connection closes, times out, or hits an I/O error with no response received; Retry evaluates the exception type.

A `500` from a deterministic bug usually **does not** recover on retry. A `503` from overload might require waiting longer than the retry window. Policy must reflect real behavior, not blind infinite retries on every 5xx.

## 6. Configuring Retry for GET-Only in YAML

### 6.1. Server WebFlux Example with Newer Namespace

Suppose Gateway is at `localhost:8080` and `catalog-service` is at `localhost:8081`. The client calls `GET /api/catalog/products/42`; the backend handles `GET /catalog/products/42`.

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: catalog-get-with-retry
              uri: http://localhost:8081
              predicates:
                - Path=/api/catalog/**
                - Method=GET
              filters:
                - StripPrefix=1
                - name: Retry
                  args:
                    retries: 2
                    methods: GET
                    series: SERVER_ERROR
                    backoff:
                      firstBackoff: 100ms
                      maxBackoff: 500ms
                      factor: 2
                      basedOnPreviousValue: false
~~~

Breakdown:

1. **`Path` and `Method=GET` predicates**: match only the GET read route.
2. **`methods: GET` inside Retry**: extra safeguard if the route predicates change later.
3. **`retries: 2`**: 1 initial call + up to 2 retries.
4. **`series: SERVER_ERROR`**: example allowing retries on 5xx; in production consider narrowing to 502/503/504 to avoid retrying application 500 bugs.
5. **`backoff`**: adds progressive wait durations with a cap.
6. **`StripPrefix=1` placed before Retry**: backend receives `/catalog/products/42`; this path mutation does not need to sit inside the retried segment.
7. Upstream URI is illustrative; `lb://CATALOG-SERVICE` can be used when LoadBalancer/discovery is configured properly.

This is a **GET demo**. It does not automatically enable Spring Security, rate limiters, circuit breakers, or a service registry.

### 6.2. Equivalent Configuration in WebFlux 4.x

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog-get-with-retry
          uri: http://localhost:8081
          predicates:
            - Path=/api/catalog/**
            - Method=GET
          filters:
            - StripPrefix=1
            - name: Retry
              args:
                retries: 2
                methods: GET
                series: SERVER_ERROR
                backoff:
                  firstBackoff: 100ms
                  maxBackoff: 500ms
                  factor: 2
                  basedOnPreviousValue: false
~~~

**These two snippets are merely version-dependent alternative namespaces**—do not declare both routes in one application. Check effective routes after upgrades so a mismatched namespace does not silently leave Retry unloaded.

### 6.3. Payment POST Route Without Auto-Retry

Define **a separate route** for the write API:

~~~yaml
# An entry in the routes list, not a standalone YAML file:
- id: payment-write-no-auto-retry
  uri: http://localhost:8082
  predicates:
    - Path=/api/payments
    - Method=POST
  filters:
    - StripPrefix=1
~~~

This route **has no Retry GatewayFilter attached**; however, clients, ingress, service meshes, or SDKs at other layers might still retry. When auditing critical write operations, examine **every layer**.

### 6.4. Configuring Specific Statuses

`Retry` supports `statuses`, for example:

~~~yaml
# Optional example inside args:
retries: 2
methods: GET
statuses: BAD_GATEWAY
~~~

**Do not assume only 502 is retried** if the default `series=SERVER_ERROR` remains active. Inspect effective configuration and run real tests for your project's release when narrowing the exact status set.

## 7. Backoff, Jitter, and Retry Budget

### 7.1. Avoiding Retry Storms

If 1,000 requests hit a backend 503 simultaneously and each fires 3 immediate retries, upstream calls can surge near 4,000 attempts in a brief window. That **load amplification** can worsen the outage.

To prevent this:

- Bound `retries` and overall request deadlines.
- Use **exponential backoff** with `maxBackoff`.
- Use **jitter** when supported by your version so clients do not retry in lockstep.
- Never retry deterministic failures like 400 validation or 403 forbidden.
- Monitor concurrency and upstream health; consider circuit breakers, bulkheads, and load shedding.
- Never let browser, Gateway, mesh, and service SDK each retry three times without accounting for the total.

### 7.2. Backoff Illustration

With:

~~~yaml
backoff:
  firstBackoff: 100ms
  maxBackoff: 500ms
  factor: 2
  basedOnPreviousValue: false
~~~

Theoretical wait intervals are roughly 100 ms, 200 ms, 400 ms, then capped at 500 ms. This is not a precision clock due to async scheduling, system load, and jitter.

Newer WebFlux versions also support:

~~~yaml
# Additional option inside args on supported versions:
jitter:
  randomFactor: 0.5
~~~

Do not assume older releases share the exact same `jitter` and `timeout` properties. Verify against docs and test property binding.

### 7.3. `Retry-After` and 429

A response may signal:

~~~http
HTTP/1.1 503 Service Unavailable
Retry-After: 10
~~~

or 429 with `Retry-After`. **Do not assume Retry GatewayFilter automatically parses every `Retry-After`** just because the header exists; honoring delta-seconds/HTTP-dates requires explicit policy/client support and dedicated tests. Under rate limiting, never auto-retry 429 immediately or exceed the overall budget.

### 7.4. Timeouts Causing Ambiguous Writes

If the Gateway timeout is only 300 ms while the backend occasionally takes 500 ms to process a payment, the Gateway may report an error even though the payment completes afterward. **Never simply increase retries to "fix timeouts."** Adjust SLOs, timeouts, async APIs, or operation ID lookup mechanisms instead.

## 8. `Idempotency-Key`: Supporting Controlled POST Retries

### 8.1. One Key per Business Intent

An **idempotency key** is a stable identifier generated by the client **once per business intent** and reused when retrying that exact command.

~~~http
POST /api/payments HTTP/1.1
Host: api.example.test
Content-Type: application/json
Idempotency-Key: 2b3c16bb-2026-4fbf-8e19-a632c0001122

{"orderId":"ord-42","amount":500000,"currency":"VND"}
~~~

If the response is lost, the client resends the **exact same key and payload**. Never generate a fresh key per attempt, as the backend will treat a new key as a separate transaction.

**The header alone does not make an operation idempotent.** The payment service or payment provider must implement deduplication and enforce the key. The Gateway can forward the header, yet cannot automatically deduplicate for every upstream.

### 8.2. Common Contract

| Scenario | Illustrative Backend Behavior |
| --- | --- |
| New key, valid input | Claim key and create one operation |
| Completed key, same payload | Return the same result/resource; create no new operation |
| Same key, different payload | Reject conflict, e.g., 409 |
| Same key while first is still running | Return 202/in-progress or wait boundedly; do not execute concurrently |
| Missing key on required endpoint | Return input validation error per contract |
| Expired key | Reuse semantics clearly defined in retention policy |
| Two tenants use the same key string | Partition keys by authenticated principal/tenant |

Exact status codes (`200`, `201`, `202`, `409`, etc.) depend on the API contract. The core invariant is **never duplicating the business effect**.

Example initial response:

~~~http
HTTP/1.1 201 Created
Location: /api/payments/pay-1001
Content-Type: application/json

{"paymentId":"pay-1001","status":"SUCCEEDED"}
~~~

When resending the same key and payload, the backend can return the same `pay-1001` resource instead of creating `pay-1002`. Returned results and replay statuses must be clearly documented.

### 8.3. Keys Must Not Contain Sensitive Data

- Generate a sufficiently random key (such as a random UUID) per operation.
- Never use raw access tokens, card numbers, emails, or phone numbers as keys.
- Partition by verified tenant/client and validate length/characters.
- Store a payload fingerprint to detect same-key, different-body mismatches.
- Set a TTL/retention longer than the expected retry/recovery window.
- Never log keys alongside full request bodies or tokens in observability pipelines.

## 9. Deduplication Must Be Atomic in the Backend

### 9.1. Race Condition When Two Concurrent POSTs Arrive With the Same Key

Wrong approach:

~~~text
Request A: SELECT key -> not found
Request B: SELECT key -> not found
Request A: create payment P-1
Request B: create payment P-2
Request A: INSERT key -> OK
Request B: INSERT key -> unique violation, yet P-2 was already created
~~~

You cannot just "SELECT first, then process if absent" and call it deduplication. You need a **unique constraint**, transaction, locking, or consistent coordination before executing side effects.

### 9.2. Illustrative Data Table

~~~sql
CREATE TABLE idempotency_requests (
    tenant_id          VARCHAR(80)  NOT NULL,
    idempotency_key    VARCHAR(160) NOT NULL,
    request_hash       CHAR(64)     NOT NULL,
    state              VARCHAR(20)  NOT NULL,
    resource_id        VARCHAR(120),
    response_status    INTEGER,
    created_at         TIMESTAMP    NOT NULL,
    PRIMARY KEY (tenant_id, idempotency_key)
);
~~~

This is solely a conceptual schema. Production applications must design transaction isolation, retention, `IN_PROGRESS`/`SUCCEEDED`/`FAILED` states, stuck-record recovery, and access control.

### 9.3. Recommended Processing Flow

~~~mermaid
flowchart TD
    A["POST + Idempotency-Key"] --> B["Auth principal + validate input"]
    B --> C{"Atomically claim key?"}
    C -->|"New key"| D["Record IN_PROGRESS"]
    D --> E["Execute business logic safely"]
    E --> F["Save result and resource ID"]
    F --> G["Return response"]
    C -->|"Existing key"| H{"Fingerprint matches?"}
    H -->|"No"| I["Conflict"]
    H -->|"Yes"| J{"Already completed?"}
    J -->|"Yes"| K["Return stored result"]
    J -->|"In progress"| L["202/PENDING or bounded wait"]
~~~

If the system calls an **external payment provider**, an internal database transaction does not guarantee atomicity at the provider. Pass the same idempotency key to the provider if supported, or use an outbox/reconciliation pattern and clear recovery procedures. Never claim "exactly once" across services merely because an idempotency table exists.

### 9.4. Status Lookup API Instead of Blind Retries

If a client times out after a POST, a sound design records/returns an operation ID and exposes:

~~~http
GET /api/payments/pay-1001 HTTP/1.1
~~~

The client queries status instead of infinitely resending the creation command. If the client never received the resource ID yet holds the idempotency key, the backend can offer an **authenticated** lookup API by key/operation ID. Avoid leaking transaction state across tenants.

## 10. Why Not Enable Retry for POST Just via `methods`?

The framework lets you pick methods; **being configurable** does not mean **safe to operate**.

~~~yaml
# WARNING: do not use for payments without true deduplication!
filters:
  - name: Retry
    args:
      retries: 3
      methods: GET,POST
      series: SERVER_ERROR
~~~

A POST that already committed yet returned 500 or timed out can be replayed. Before enabling retries for POST, prove that:

1. Same key/payload cannot trigger side effects twice.
2. External side effects (payments, emails, events, webhooks) are deduplicated.
3. The body replays accurately and fits within memory budgets.
4. Methods, statuses, and exceptions are tightly scoped.
5. Client, Gateway, mesh, and SDK retries share an end-to-end budget.
6. Reconciliation exists if responses still fail to reach clients.
7. Timeouts and circuit breakers never fabricate fake "success" states.

**Gateway Retry does not replace an idempotency implementation in the business service.**

## 11. Request Body and Memory Risks in WebFlux

### 11.1. GET Is Easier to Retry at the Transport Layer

GET normally carries no large request body. POST/PUT/PATCH often carry JSON, multipart forms, or upload streams. In WebFlux, a body may be single-read, so replaying it requires **body caching/replay**.

Gateway Server WebFlux documentation notes that when using Retry for HTTP methods with bodies, **the body may be cached**, risking Gateway memory exhaustion under heavy load. The body is stored in the `ServerWebExchangeUtils.CACHED_REQUEST_BODY_ATTR` exchange attribute as a `DataBuffer` in the documented implementation.

~~~text
100 concurrent requests x 1 MiB body  -> noticeable, depending on overhead
100 concurrent requests x 50 MiB body -> severe RAM/direct-memory risk
~~~

This illustrates data scale, not an exact memory footprint calculation. Do not enable body retries for large uploads without memory budgets, size limits, concurrency caps, and load testing.

### 11.2. `RequestSize` and Codec Limits Do Not Replace Architecture

`RequestSize` can limit request size, though some versions rely heavily on `Content-Length` and require testing against chunked/streaming requests. `spring.codec.max-in-memory-size` is not a total upload cap for every streamed proxy request.

Coordinate body limits at ingress, upstream, and gateway, plus concurrent upload caps and timeouts. For large uploads, consider resumable uploads or signed URLs directly to object storage instead of retrying whole payloads through the Gateway.

### 11.3. Do Not Copy Server MVC `cacheBody` Into WebFlux

Server MVC uses separate mechanisms such as `cacheBody` and `AdaptCachedBody`. Do not copy `cacheBody: true` from **Server MVC** examples into WebFlux, because the factories and body replay mechanisms differ. Always consult the matching Server WebFlux documentation/version.

## 12. Filter Order, Rate Limiter, Circuit Breaker, and LoadBalancer

A `Retry` can re-execute **downstream filters**. Conceptual pipeline:

~~~text
RequestRateLimiter
  -> Retry
       -> StripPrefix / custom filter
       -> LoadBalancer / HTTP routing
~~~

During a retry:

- Downstream custom filters may log, call sidecar services, or add headers multiple times.
- `RequestRateLimiter` before Retry can count **client requests**, whereas after Retry it may consume quota differently.
- `CircuitBreaker` before or after Retry can observe different failure sets.
- Retry does not guarantee a subsequent attempt chooses a **different** instance under `lb://`.
- Once Netty starts flushing response bytes to the client, retry cannot "take back" committed bytes.

This example illustrates the mechanism only; YAML order alone does not guarantee effective order when `GlobalFilter`, `OrderedGatewayFilter`, and internal filters interact. Verify effective order with integration tests and version documentation.

| Mechanism | Goal | Risk if Misconfigured |
| --- | --- | --- |
| **Retry** | Bounded recovery for transient errors | Load amplification, repeated side effects |
| **Circuit breaker** | Shed traffic when upstream is unstable | False trips/opening, fallbacks hiding bugs |
| **Rate limiting** | Cap request rate per principal/tenant | Multi-layer retries skewing quota |
| **Timeout/deadline** | Cap wait time | Timing out after backend already committed |
| **LoadBalancer** | Pick instance | Retry does not automatically switch instances |
| **Idempotency** | Prevent duplicate write effects | Not provided by framework retries |

Never let browser, Gateway, mesh, HTTP SDK, and database client each retry three times without tracking **total attempts**.

## 13. Which HTTP Statuses Are Worth Retrying?

| HTTP Status | GET/Read API | POST/Write API |
| --- | --- | --- |
| **2xx** | No retry needed | No retry needed |
| **400/422** | Invalid input; fix request | Never auto-retry same body |
| **401/403** | Bad auth/permissions; retrying won't help | Same |
| **404** | Usually no; eventual consistency needs its own policy | Do not blindly resend |
| **409** | Analyze conflict | Same key with different body must fix input |
| **412** | Version/precondition mismatch | Do not blindly overwrite |
| **429** | Slow down; Retry-After/backoff if applicable | Never auto-retry writes unless idempotent |
| **500** | Retry only with evidence of transience | Could have failed **after commit** |
| **502** | Often retryable on GET within budget | Does not prove write was not applied |
| **503** | Retryable on GET with backoff/jitter | Do not retry without deduplication |
| **504** | Retryable on GET while budget remains | **Ambiguous outcome** for write operations |

This is design guidance, not an exact default table for every Spring Gateway version. Never repeatedly retry a 500 caused by a deterministic bug, and never treat every GET as safe if a backend misuses GET to mutate business state.

## 14. Testing with a Mock Upstream and curl

### 14.1. Preparing the Test Setup

Suppose:

- Gateway at `http://localhost:8080`.
- Mock catalog-service at `http://localhost:8081`.
- Mock payment-service at `http://localhost:8082`.
- GET route with `Retry`, `retries: 2`, `series: SERVER_ERROR`.
- Payment POST route **without Retry**.

The mock catalog-service needs per-attempt response scripting:

~~~text
GET /catalog/products/42
  call #1 -> 502 Bad Gateway
  call #2 -> 200 OK
  call #3 -> not called since #2 succeeded
~~~

Never rely solely on seeing `200 OK` to conclude Retry worked: **count the requests actually received by the backend** and reset counters before each case.

### 14.2. GET: Successful Retry

~~~bash
curl -i "http://localhost:8080/api/catalog/products/42"
~~~

Expected mock test result:

~~~text
Client -> Gateway: 1 GET request
Gateway -> catalog-service: 2 GET attempts
Client <- Gateway: 200 OK after successful attempt
~~~

This is an expected test outcome, not an observed run. When executing for real, check route ID, upstream counters, and attempt logs.

### 14.3. GET: Retry Budget Exhausted

Mock returns 503 continuously:

~~~bash
curl -i "http://localhost:8080/api/catalog/products/42"
~~~

With `retries: 2`, at most 3 attempts execute when errors consistently match policy and are not cut short by deadlines/cancellations. Final response depends on the error type and active error handler.

### 14.4. POST: No Auto-Retry, Using Key When Needed

~~~bash
curl -i \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: demo-payment-001" \
  -d '{"orderId":"ord-42","amount":500000,"currency":"VND"}' \
  "http://localhost:8080/api/payments"
~~~

Have mock payment-service **commit successfully** and then drop the connection before responding. Because the POST route has no Retry, the Gateway must not automatically issue a second attempt via `Retry GatewayFilter`.

Afterward, the client can resend the **same key** to the test backend with dedup enabled. Assert **a single payment resource** despite two HTTP requests. Never reuse a fixed `demo-payment-001` across multiple real transactions.

### 14.5. Integration Test Matrix

| Case | Scenario | Required Assertions |
| --- | --- | --- |
| G1 | GET: 502 then 200 | 1 client request, 2 upstream attempts, final 200 |
| G2 | GET: continuous 503 | Attempts never exceed retry budget |
| G3 | GET: 400/404 | No retry when policy covers only 5xx |
| G4 | GET: IOException/TimeoutException | Retries only when exception is in policy |
| G5 | GET streaming response committed then dropped | Does not attempt to recreate full response |
| W1 | POST route without Retry | No extra attempt added by Gateway |
| W2 | Same key and payload, two POSTs | Only one resource when dedup works |
| W3 | Same key, different payload | Backend reports conflict, creates no second command |
| W4 | Two concurrent POSTs with same key | Transaction/unique constraint prevents duplicate side effect |
| W5 | PUT with stale `If-Match` ETag | 412, no blind overwrite |
| W6 | DELETE twice | Final state correct, secondary events deduplicated |
| O1 | Gateway + client + mesh all retrying | Count total attempts and elapsed time |
| O2 | RateLimiter and Retry in different orders | Quota deducted according to policy |
| O3 | Large POST accidentally retried | Monitor heap/direct memory and cancellation |
| O4 | Upstream commits then times out | GET/reconciliation path resolves outcome |

Keep tests on **mocks or controlled staging**, never creating real payments. Never put bearer tokens, payment details, or session cookies in reports/logs.

## 15. Observing Retries and Diagnosing Issues

### 15.1. One Client Request Can Become Three Attempts

Example sanitized log:

~~~text
traceId: test-abc-123
routeId: catalog-get-with-retry
method: GET
clientRequests: 1
upstreamAttempts: 3
outcomes: [502, 503, 200]
finalStatus: 200
totalLatencyMs: 340
~~~

Measuring only `finalStatus` 200 misses the two prior backend failures. Track metrics for **attempt count**, retry count, per-attempt status/exception, total backoff, p95/p99 latency, and operation IDs where applicable.

### 15.2. Retries and Latency

An attempt taking 400 ms before timing out followed by another 400 ms attempt can push total latency past the SLO even when ultimately returning 200. **Retries are not free**: they consume resources and can worsen tail latency.

For write APIs, measure **ambiguous outcome rate**, in-flight operation count, and reconciliation volume. Never interpret multiple attempts in HTTP access logs as multiple valid business transactions.

### 15.3. Common Reasoning Mistakes

| Symptom | Possible Reason | Fix |
| --- | --- | --- |
| POST creates two orders after timeout | Auto-retry without dedup | Disable retry or implement atomic idempotency keys |
| GET hits backend multiple times | Retry matching 5xx/exception | Inspect counters and policy |
| PUT finishes yet sends two emails | Non-idempotent side effect | Outbox/event deduplication |
| Second DELETE returns 404 | Confusing response with final state | Check resource state |
| PATCH increment adds twice | Assuming PATCH is always idempotent | Analyze operation semantics |
| Retrying 500 does not help | Deterministic bug | Fix upstream; narrow status list |
| Retrying 429 immediately | Ignoring rate limit/backoff | Stop, wait, or use budgeted retries |
| `retries: 3` produces 4 attempts | Confusing retry count with total attempts | Calculate `1 + retries` |
| Large POST causes Gateway OOM | Caching request body | Do not retry large uploads; cap concurrency |
| Custom filter runs multiple times | Placed downstream of Retry | Fix ordering or make filter idempotent |
| 504 yet DB committed | Timeout only means response did not return | Idempotency + operation query |
| Same key still creates duplicates | Non-atomic dedup or external PSP duplicate | Unique constraint/transaction/provider key/reconciliation |
| GET creates transactions | Violated HTTP semantics | Change endpoint to a write method |
| Retries always hit failing instance | No guarantee of switching backend | Check LB selection/health |

## 16. Hands-On Exercise: Catalog GET and Payment POST

**Scenario:** A Gateway exposes product catalog read APIs and payment creation APIs. Catalog occasionally returns 502; the payment service may finish processing and then drop the connection.

Requirements:

1. Create a `GET /api/catalog/**` route with bounded Retry, backoff, and method GET.
2. Create a `POST /api/payments` route **without** Gateway retries.
3. Mock catalog returning 502 then 200; assert backend sees two GETs while client sent one GET.
4. Mock catalog returning continuous 503; assert max attempts never exceed configuration.
5. Mock payment committing then dropping response; verify Gateway does not automatically replay POST.
6. Implement `Idempotency-Key` in payment-service with a per-tenant unique constraint.
7. Test same key/same body, same key/different body, and two concurrent requests with the same key.
8. If payments call an external provider, verify provider idempotency/reconciliation support.
9. Add circuit breaker, rate limiting, and timeouts per policy, then measure filter-order effects.
10. Set an end-to-end retry budget and measure p95/p99 latency to prevent retry storms.
11. Preserve trace/request IDs and operation IDs without logging secrets.
12. Document client guidance when payment outcome is **ambiguous**: poll status instead of firing a new payment command.

### Pre-Production Checklist

- [ ] GET endpoints are genuinely read-only and never hide writes inside queries.
- [ ] `retries` counts **additional** attempts after the initial call.
- [ ] `methods`, `series`, `statuses`, and `exceptions` are tested on the exact target version.
- [ ] Backoff/jitter/deadlines fit SLOs and concurrency limits.
- [ ] POST/PATCH do not auto-retry without an idempotency contract.
- [ ] PUT/DELETE preserve semantics and control secondary side effects and versions.
- [ ] Operation keys remain stable across attempts; never mint a new key on retry.
- [ ] Deduplication is atomic, with payload fingerprinting, TTL, and in-progress handling.
- [ ] Off-DB effects (Kafka, email, PSP) have deduplication/recovery mechanisms.
- [ ] Body caching does not cause memory pressure; large uploads use dedicated designs.
- [ ] Filter order, rate limiter, breaker, LoadBalancer, and response commit are verified.
- [ ] Never auto-retry 400/401/403/409/412 or immediately retry 429.
- [ ] Metrics track upstream attempts, final outcomes, latency, and ambiguous outcomes.
- [ ] A post-timeout result lookup API and reconciliation process exist.
- [ ] Client, Gateway, mesh, and SDK share a managed retry budget.

## 17. Summary

**GET** is both safe and idempotent under HTTP, making it the primary candidate for bounded retries after transient failures. **PUT and DELETE** are idempotent in **intended effect**, yet still require guarding secondary side effects. **POST and PATCH** are not idempotent by default: a timeout, 502, or 504 does not guarantee the backend did not commit.

In Spring Cloud Gateway Server WebFlux, `Retry GatewayFilter` supports methods, statuses/series, exceptions, and backoff, notably defaulting to retrying **GET** when enabled. Filters downstream of Retry may re-execute, and requests with bodies may require caching that consumes RAM.

For critical writes like payments and order creation, correctness must rely on **idempotency keys, unique constraints, transactions, side-effect protection, and reconciliation**. Never use retry settings as a substitute for those guarantees. Only by combining retry budgets, timeouts, circuit breakers, rate limiting, TLS, and attempt observability can the Gateway boost availability without duplicating data.

### References

- [RFC 9110 — Safe and Idempotent Methods](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.2).
- [Spring Cloud Gateway Server WebFlux — Retry GatewayFilter Factory](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/retry-factory.html).
- [Spring Cloud Gateway 4.x — GatewayFilter Factories](https://docs.spring.io/spring-cloud-gateway/docs/current/reference/html/).
- [RFC 5789 — PATCH Method for HTTP](https://www.rfc-editor.org/rfc/rfc5789).
