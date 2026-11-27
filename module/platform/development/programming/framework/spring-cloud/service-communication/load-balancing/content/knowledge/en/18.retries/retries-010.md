# Idempotency, Deduplication Keys, and Unknown Outcomes

When calling a microservice over HTTP, **retries** help recover from transient failures such as a reset connection, a recently terminated instance, or a sluggish response. Yet for write operations, retries can also cause **the same business intent to be executed twice**: creating two orders, reserving stock twice, or charging twice. Incidents typically arise when the caller **does not know** whether the server already finished the first request.

This lesson belongs to the **Retries** chapter of the **SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING** module. In Spring Cloud LoadBalancer, a client selects a `ServiceInstance` by service ID from discovery, health checks, and routing policies; a retry may route to a different instance. Therefore, understanding **idempotency**, **idempotency keys**, and **unknown outcomes** is essential before configuring retries and timeouts on RestClient, WebClient, or OpenFeign.

> Core message: **a timeout does not prove the request failed on the server; retries do not automatically create idempotency; and LoadBalancer does not guarantee a business operation runs only once.** Safety must be designed into the API contract and side-effect handling.

## 1. Why can retries produce duplicate outcomes?

Suppose `order-service` calls `reservation-service`:

~~~http
POST /api/reservations HTTP/1.1
Host: reservation-service
Content-Type: application/json

{"sku":"sku-42","quantity":1}
~~~

On the first attempt, instance A records a reservation successfully. The response is lost in transit, causing the caller to time out. The caller resends the same body; LoadBalancer may pick instance B. If the server lacks a mechanism to recognize that this command already ran, B creates a second reservation.

~~~mermaid
sequenceDiagram
    autonumber
    participant Caller as order-service
    participant LB as Spring Cloud LoadBalancer
    participant A as reservation-a
    participant B as reservation-b
    participant DB as Database

    Caller->>LB: POST /api/reservations, attempt 1
    LB-->>Caller: Select A
    Caller->>A: POST request
    A->>DB: INSERT reservation #101
    DB-->>A: COMMIT succeeded
    A--xCaller: Response delayed or lost
    Note over Caller: Timeout, outcome unknown
    Caller->>LB: Retry same intent, attempt 2
    LB-->>Caller: May select B
    Caller->>B: POST request
    B->>DB: INSERT reservation #102
    DB-->>B: COMMIT succeeded
    B-->>Caller: HTTP 201, reservation #102
    Note over Caller,DB: Two reservations for one intent
~~~

From the caller's perspective, attempt 1 failed at **communication**; from the server's perspective, attempt 1 succeeded in **business terms**. Both truths coexist without contradiction.

Distinguish three entities:

- **Business operation**: the business intent, e.g., "reserve one unit for order X."
- **HTTP attempt**: one network request execution; one operation can have multiple attempts.
- **Business side effect**: an actual state change or external action, such as creating a reservation, charging money, or emitting an event.

When retrying, the goal is not to stop HTTP attempts from repeating; the goal is to prevent **unintended duplicate business side effects**.

## 2. What is idempotency really?

An operation is **idempotent** if applying the same operation multiple times has an **intended state effect** equivalent to applying it once. For example, setting `status=ACTIVE` twice normally still leaves the state ACTIVE.

Written symbolically:

~~~text
f(f(state, command), command) = f(state, command)
~~~

Here equality refers to the **important business outcome**, not necessarily identical logs, timestamps, HTTP statuses, or processing cost.

### HTTP methods and business semantics

| HTTP method | Idempotency per HTTP semantics | Practical warning |
|---|---|---|
| GET, HEAD | Safe and idempotent per HTTP contract | Should not mutate business state; logs/metrics may still change |
| PUT | Idempotent in the sense of replacing resource state | Buggy implementations or external non-DB side effects can still cause trouble |
| DELETE | Idempotent with respect to resource effect | First call `204`, next call `404` can still match an idempotent effect |
| POST | Not idempotent by default | Usually requires an idempotency key for creating resources/actions |
| PATCH | Not idempotent by default | "Set stock=10" differs from "increase stock by 10" |

Examples:

~~~text
PUT /items/42 {"stock":10}       -> calling again still leaves stock=10
PATCH /items/42 {"stockDelta":+1} -> calling again may increment stock multiple times
POST /payments {"amount":500}    -> calling again may create another transaction
~~~

Never judge an operation safe purely from its method name: inspect the **contract, actual server execution, and external dependencies**. A poorly coded PUT might send an email every time, while a POST can be genuinely idempotent if the API is designed to recognize repeated intent.

**Safe** (not intended to alter business state) and **idempotent** (repeating does not multiply intended side effects) are distinct concepts. An idempotent request does not have to consume zero CPU or emit zero extra logs.

## 3. Where do "unknown outcomes" come from?

When a caller receives no response, several states are possible:

| Failure stage | Might the server have executed? | What does the caller know for sure? |
|---|---|---|
| No `ServiceInstance` to pick | No HTTP request sent to target server on this pick | Not executed via this unsent attempt |
| Connection error before sending HTTP request | Usually never reached server, though verify transport | Connection setup failed |
| Connection dropped while sending body | Server may have received part or all | Cannot deduce certainty from one I/O error |
| Read/response timeout expired | May be unprocessed, in progress, or already committed | Response did not arrive in time |
| Server committed, response lost | **Already executed** | Caller may still see only a timeout |
| Received HTTP 500/503 | Server or gateway returned an error | Does not prove prior side effects rolled back |
| Received valid, decoded success response | Evidence per HTTP/API contract | Must still understand the business definition of "success" |

In distributed systems, a caller cannot infer a definite transaction state merely from a timeout. Therefore, model an explicit state like `UNKNOWN` or `PENDING_VERIFICATION` instead of equating it with `FAILED`.

~~~mermaid
flowchart TD
    A["Caller sends operation K"] --> B{"Response per contract?"}
    B -->|"Success"| C["COMPLETED"]
    B -->|"Definitive business error"| D["FAILED per contract"]
    B -->|"Timeout / lost response"| E["UNKNOWN"]
    E --> F["Look up operation by key K"]
    F --> G{"Observed status?"}
    G -->|"COMPLETED"| C
    G -->|"PENDING"| H["Backoff and poll again"]
    H --> F
    G -->|"Unclear / query error"| I["Keep UNKNOWN; reconcile"]
    G -->|"NOT_FOUND"| J["Insufficient to prove first request never arrived"]
    J --> K["Retry only with same K if server supports durable dedup"]
~~~

Specifically, `NOT_FOUND` can appear because a query ran too early, read from a lagging replica, or the key wasn't persisted yet while the first request was still running. It is **insufficient** to justify retrying with a brand-new key.

## 4. Idempotency key: identifying an intent, not an attempt

A common way to make POST retry-safe is sending a header:

~~~http
POST /api/reservations HTTP/1.1
Host: reservation-service
Idempotency-Key: 0b8d3a2e-...-operation
Content-Type: application/json

{"sku":"sku-42","quantity":1}
~~~

The key represents **one business operation**. The caller generates the key **before the first attempt**, keeps the exact same key across all retries or status checks of that operation, and generates a **new key for a new business operation**.

| Practice | Right or wrong? | Why? |
|---|---|---|
| Retry same body, same key K | Right if server supports idempotency | Attempts are recognized as one intent |
| Retry same body, generate new key K2 | Dangerous | Server may treat it as a second operation |
| Reuse K for a different payload | Wrong under normal contracts | Must not silently return an old result for a different command |
| Query status with K after timeout | Useful | Helps verify if the server exposes a lookup endpoint |
| Store keys per instance in memory | Insufficient with LoadBalancer | Retries can land on another instance |
| Add header K when backend ignores it | Insufficient | A header alone creates no duplicate protection |

There is no single mandatory key format across all APIs. You may use a hard-to-guess random UUID or an agreed business identifier, provided you ensure **uniqueness within the contract scope**, avoid leaking secrets, and prevent callers from guessing someone else's key.

### How should a key be scoped?

Typically combine:

~~~text
(tenant_id or principal, operation_type, idempotency_key)
~~~

For instance, the same string `request-123` sent by tenant A and tenant B must never leak A's outcome to B. Also define whether the key belongs to an endpoint, an operation type, or a larger workflow so the same key never accidentally merges distinct actions.

## 5. Same key with different payload: conflicts must be detected

Suppose the first request is:

~~~json
{"sku":"sku-42","quantity":1}
~~~

The second attempt uses the same key, yet sends:

~~~json
{"sku":"sku-42","quantity":4}
~~~

If the server checks only the key and replays the old receipt, the caller may believe four items were reserved when only one was. Therefore, store a **request fingerprint** alongside the key. The fingerprint should cover business-meaningful fields, operation, scope, and a stable canonical format.

A contract may specify:

| Key state | Payload | Recommended outcome |
|---|---|---|
| Never seen K | Valid | Accept, create PENDING record |
| K is COMPLETED | Equivalent payload | Return stored result |
| K is PENDING | Equivalent payload | Return PENDING/202 or bounded wait policy |
| K exists | Different payload | Return conflict, e.g., HTTP `409` per contract |
| K expired past retention | Record may be gone | Define retry horizon and reconciliation |

These HTTP codes are **design suggestions**, not built-in rules enforced by Spring Cloud LoadBalancer. Server implementation defines the exact contract.

When hashing JSON, do not hash raw JSON strings naively when field ordering, whitespace, or equivalent formatting can vary. Canonicalize or select stable business fields, excluding irrelevant values like trace IDs.

## 6. Guarding concurrent duplicate requests: "check then insert" is not enough

A common bug:

~~~java
if (!repository.existsByKey(key)) {
    repository.insertReservation(command);
    repository.saveKey(key);
}
~~~

When two requests with the same key hit two instances concurrently:

~~~mermaid
sequenceDiagram
    autonumber
    participant A as reservation-a
    participant B as reservation-b
    participant DB as Shared DB

    A->>DB: exists(K)?
    DB-->>A: false
    B->>DB: exists(K)?
    DB-->>B: false
    A->>DB: INSERT reservation #101
    B->>DB: INSERT reservation #102
    A->>DB: SAVE idempotency key K
    B->>DB: SAVE idempotency key K
    Note over A,B: Race without unique constraint/transaction
~~~

Checking `exists` then `insert` spans multiple separate steps, failing to stop two concurrent requests from both passing the check. You need an **atomic decision point** in a shared datastore, such as:

- A unique constraint on `(tenant_id, operation, idempotency_key)`.
- Appropriate transactions for claiming the key, applying side effects, and recording the result.
- A key-ownership mechanism or state machine handling concurrency, crashes, and retention.
- If side effects live outside the transaction, add idempotency at the target system or reconciliation/outbox/saga protocols.

A single-JVM mutex likewise fails to protect requests hitting **two different replicas**. Especially with Spring Cloud LoadBalancer, retries can route to a new `ServiceInstance`.

## 7. Durable state model for requests

A deduplication record should store at minimum:

| Field | Purpose |
|---|---|
| `tenant_id` | Bounds owner scope |
| `operation_type` | Distinguishes operations |
| `request_key` | Identifies one business operation |
| `request_hash` | Detects key reuse with a different payload |
| `status` | `PENDING`, `COMPLETED`, or `FAILED` per contract |
| `result_reference` | Identifier of the created reservation/payment |
| `response_snapshot` or result fields | Replays a consistent response |
| `created_at/updated_at` | Operations, timeout handling, and retention |

Illustrative PostgreSQL schema:

~~~sql
CREATE TABLE idempotency_records (
    tenant_id VARCHAR(100) NOT NULL,
    operation_type VARCHAR(100) NOT NULL,
    request_key VARCHAR(200) NOT NULL,
    request_hash VARCHAR(128) NOT NULL,
    status VARCHAR(32) NOT NULL,
    result_reference VARCHAR(200),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (tenant_id, operation_type, request_key)
);

CREATE TABLE reservations (
    id BIGSERIAL PRIMARY KEY,
    tenant_id VARCHAR(100) NOT NULL,
    sku VARCHAR(100) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0)
);
~~~

This is an **illustrative schema**, not a complete production deduplication system. Design transaction isolation, ownership rules, stuck-record timeouts, response snapshots, access control, storage, and cleanup according to real requirements.

### Transaction processing flow

~~~text
1. Validate tenant, key, payload
2. Compute request fingerprint
3. Atomically try to claim key in shared durable store
4a. If key exists, compare fingerprint:
    - Mismatch: conflict
    - COMPLETED: return saved result
    - PENDING: return in-progress / bounded wait
4b. If claim succeeded:
    - Execute business logic, write domain record
    - Persist result and COMPLETED state consistently
5. Commit and return response
~~~

For local DB logic, a transaction can combine claiming the key with writing domain data, or use a short-lived PENDING record when work takes longer. If splitting transactions, handle **crashes after claiming but before completing** so keys never stay PENDING forever.

Never delete a PENDING row and rerun blindly without checking whether side effects already occurred. Lease/timeout expiration only tells you the worker holding the key may have died—**it does not prove external non-DB work failed to finish**.

## 8. Illustrating atomic claims with a unique constraint

With databases supporting upserts, competing for the right to process a key can start atomically:

~~~sql
INSERT INTO idempotency_records
    (tenant_id, operation_type, request_key, request_hash, status)
VALUES
    (:tenantId, 'CREATE_RESERVATION', :key, :requestHash, 'PENDING')
ON CONFLICT (tenant_id, operation_type, request_key)
DO NOTHING;
~~~

Application code then distinguishes **whether the insert succeeded or conflicted** via affected row count. On conflict, read the existing row to compare fingerprint and status rather than creating a new reservation.

**Transaction warning:** the SQL snippet above **illustrates claiming the key only**. Never treat `ON CONFLICT DO NOTHING` alone as enough for exactly-once guarantees. Coordinate updating the reservation and idempotency record inside proper transactions or recoverable workflows, accounting for uncommitted concurrent transactions and deadlocks/lock timeouts.

For instance, a local flow can use **the same DB transaction** to insert the reservation and mark the idempotency record COMPLETED before committing. If an error triggers rollback, neither the reservation nor the key outcome commits, allowing a later attempt to retry. For side effects hitting Kafka, email, or external payment systems outside the DB transaction, add dedicated durability mechanisms.

## 9. Lab example: same key prevents a second reservation in one JVM

To observe the behavior clearly, create a Spring Boot server simulating saving a reservation before a slow response. The lab uses `ConcurrentHashMap.compute` for atomicity **per key in a single process**. It does not prove safety across multiple replicas or restarts.

Records:

~~~java
package demo.reservation;

record ReservationRequest(String sku, int quantity) {}

record ReservationReceipt(
    String reservationId,
    String sku,
    int quantity
) {}

record StoredReservation(
    ReservationRequest request,
    ReservationReceipt receipt
) {}
~~~

Controller:

~~~java
package demo.reservation;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.core.env.Environment;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/reservations")
class ReservationController {

    private final Map<String, StoredReservation> saved =
        new ConcurrentHashMap<>();
    private final AtomicLong sequence = new AtomicLong(1000);
    private final String instanceId;

    ReservationController(Environment env) {
        this.instanceId = env.getProperty("instance.id", "local");
    }

    @PostMapping
    ResponseEntity<ReservationReceipt> create(
        @RequestHeader("Idempotency-Key") String key,
        @RequestBody ReservationRequest request
    ) throws InterruptedException {

        if (key.isBlank() || request.quantity() <= 0) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Invalid key or quantity");
        }

        StoredReservation entry = saved.compute(key, (k, existing) -> {
            if (existing != null) {
                if (!existing.request().equals(request)) {
                    throw new ResponseStatusException(
                        HttpStatus.CONFLICT,
                        "Key reused with a different request");
                }
                return existing;
            }

            String id = instanceId + "-" + sequence.incrementAndGet();
            ReservationReceipt receipt = new ReservationReceipt(
                id, request.sku(), request.quantity());

            return new StoredReservation(request, receipt);
        });

        System.out.println(
            "STORED instance=" + instanceId +
            " key=" + key +
            " reservation=" + entry.receipt().reservationId()
        );

        // Lab only: state is already saved; response is deliberately delayed.
        Thread.sleep(2500);

        return ResponseEntity.status(HttpStatus.CREATED)
            .body(entry.receipt());
    }

    @GetMapping("/by-key/{key}")
    ResponseEntity<ReservationReceipt> find(@PathVariable String key) {
        StoredReservation entry = saved.get(key);
        if (entry == null) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.ok(entry.receipt());
    }
}
~~~

You need a Spring Boot application with `@SpringBootApplication` and `spring-boot-starter-web` to run the controller. Assume it is packaged as `reservation-service.jar`.

**Intentional lab limitations:**

1. No real authentication, tenant scoping, persistence, or transactions.
2. `ConcurrentHashMap` is only safe within one JVM and loses data on restart.
3. `compute` prevents two threads in the **same process** from creating two receipts for one key, yet does not stop two separate instances from creating two receipts.
4. `Thread.sleep(2500)` simulates a slow response in the lab; unsuitable for production.
5. The key is not fingerprinted via a hash here, instead comparing request record fields directly; real systems need canonicalization and explicit scoping.
6. Every replay returns HTTP 201; production may replay the original response or return another status per contract, especially while PENDING.

## 10. Verifying timeout followed by retrying with the exact same key

Run one instance:

~~~bash
java -jar reservation-service.jar --server.port=18081 --instance.id=reservation-a
~~~

Send a request with a 1-second deadline, shorter than the 2.5-second response delay:

~~~bash
curl -v --max-time 1 \
  -X POST "http://localhost:18081/api/reservations" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: reserve-001" \
  -d '{"sku":"sku-42","quantity":1}'
~~~

The caller sees a timeout because the response did not arrive. Yet the server wrote to the map before sleeping. Query status:

~~~bash
curl -i "http://localhost:18081/api/reservations/by-key/reserve-001"
~~~

Expected result:

~~~json
{
  "reservationId": "reservation-a-1001",
  "sku": "sku-42",
  "quantity": 1
}
~~~

Resend the **same key and same payload**, this time allowing enough time for the response:

~~~bash
curl -i --max-time 5 \
  -X POST "http://localhost:18081/api/reservations" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: reserve-001" \
  -d '{"sku":"sku-42","quantity":1}'
~~~

Expect the result to still return `reservationId=reservation-a-1001`. Resending with the same key and `quantity=2` returns HTTP `409` per the demo code; sending a **new key** creates a new receipt.

### Testing two concurrent requests

Open two terminals and send two POSTs with the same key before the first request returns. Within **one process**, `ConcurrentHashMap.compute` executes atomically per key and both requests receive the same receipt.

To contrast with a distributed setup, start a **second instance**:

~~~bash
java -jar reservation-service.jar --server.port=18082 --instance.id=reservation-b
~~~

Send the same key directly to ports 18081 and 18082: because the two maps are independent, you can receive two different reservation IDs, such as `reservation-a-1001` and `reservation-b-1001`. That is why a **shared durable idempotency store** is mandatory across multiple `ServiceInstance` replicas.

## 11. Retrying via Spring Cloud LoadBalancer: same intent, possibly different target

On the caller side, `SimpleDiscoveryClient` can declare two static instances under one service ID in a lab:

~~~yaml
spring:
  application:
    name: order-service
  cloud:
    discovery:
      client:
        simple:
          instances:
            reservation-service:
              - uri: http://localhost:18081
              - uri: http://localhost:18082
~~~

A `RestClient` built from a `@LoadBalanced` builder can invoke:

~~~java
import java.util.UUID;

import org.springframework.http.MediaType;
import org.springframework.web.client.RestClient;

record CreateReservationRequest(String sku, int quantity) {}

record ReservationDto(String reservationId, String sku, int quantity) {}

String operationKey = UUID.randomUUID().toString();

ReservationDto receipt = reservationRestClient.post()
    .uri("http://reservation-service/api/reservations")
    .header("Idempotency-Key", operationKey)
    .contentType(MediaType.APPLICATION_JSON)
    .body(new CreateReservationRequest("sku-42", 1))
    .retrieve()
    .body(ReservationDto.class);
~~~

Here `reservationRestClient` must be created from a `@LoadBalanced RestClient.Builder` in the Spring context; the snippet focuses only on the request rather than a complete Java application.

If attempt 1 hits instance A and times out, a retry may go to B per LoadBalancer/HTTP client policy. **Never assume retries always switch instances**, yet also **never design servers assuming all attempts always land on A**. With real idempotency, instances must coordinate through a shared datastore.

Important: `UUID.randomUUID()` above is called **once before all attempts**. Generating a UUID inside a helper called on every retry causes the server to treat each try as a separate operation.

## 12. Bounded WebClient retries preserving the same key

With reactive `WebClient`, `retryWhen` re-subscribes when the publisher emits an eligible error. A fresh HTTP request can pass through LoadBalancer and pick another instance.

~~~java
import java.time.Duration;
import java.util.UUID;

import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.WebClientRequestException;

import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

String operationKey = UUID.randomUUID().toString();
CreateReservationRequest command =
    new CreateReservationRequest("sku-42", 1);

Mono<ReservationDto> result = reservationWebClient.post()
    .uri("http://reservation-service/api/reservations")
    .header("Idempotency-Key", operationKey)
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(command)
    .retrieve()
    .bodyToMono(ReservationDto.class)
    .timeout(Duration.ofSeconds(1))
    .retryWhen(
        Retry.backoff(2, Duration.ofMillis(200))
            .maxBackoff(Duration.ofSeconds(1))
            .filter(error ->
                error instanceof WebClientRequestException ||
                error instanceof java.util.concurrent.TimeoutException)
    )
    .timeout(Duration.ofSeconds(4));
~~~

This is a **mechanism illustration**, not a default production policy:

- `operationKey` is created once outside the publisher; every retry re-subscription uses the exact same key.
- `Retry.backoff(2, ...)` grants at most **two retries after the initial attempt**; up to three HTTP attempts may occur.
- `timeout(1s)` before `retryWhen` acts as a per-attempt deadline on the publisher.
- `timeout(4s)` after `retryWhen` acts as the overall deadline for this publisher; it covers backoff though not necessarily time before the app subscribes.
- The predicate illustrates only I/O errors and Reactor timeouts. Other exception types depend on the connector; inspect the cause before broadening it.
- Retrying POST in this example **is business-valid only when the server has durable idempotency**. The lab's in-memory map server **does not satisfy that requirement with two instances**.

Never call `block()` on a WebFlux event loop. In reactive controllers, return `Mono<ReservationDto>` or map to an appropriate response.

An HTTP `503` may surface as `WebClientResponseException` and is **excluded by the filter above**; to retry `503`/`429`, add explicit rules accounting for `Retry-After`, idempotency, and time budgets.

## 13. RestClient and OpenFeign: retries do not automatically include duplicate safety

With `RestClient`, you can wrap service-ID calls in a resilience layer. With OpenFeign, Feign integration and `Retryer`/`ErrorDecoder` config govern retry conditions. Spring Cloud OpenFeign may default to `Retryer.NEVER_RETRY` depending on release/config; never infer from core Feign or a dependency that POSTs will retry.

Example OpenFeign interface:

~~~java
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;

@FeignClient(name = "reservation-service")
interface ReservationClient {

    @PostMapping("/api/reservations")
    ReservationDto create(
        @RequestHeader("Idempotency-Key") String operationKey,
        @RequestBody CreateReservationRequest request
    );
}
~~~

When business logic re-invokes `client.create(key, request)`, it must supply the **same key and same request** for one operation. If enabling automatic retries, cap and observe attempt counts, test dead-instance/no-instance behavior, and avoid multiplying retries across layers.

### Key differences to remember

| Option | Where retries are configured | What is not automatically guaranteed |
|---|---|---|
| RestClient | Resilience wrapper, Spring Retry/Resilience4j, or compatible LB integration | Not automatically idempotent for POST |
| WebClient | Reactor `retryWhen` or appropriate resilience/LB layer | Does not automatically replay keys with business semantics |
| OpenFeign | Feign `Retryer` and corresponding Spring Cloud/CB config | Not guaranteed to retry identically across versions |
| Spring Cloud LoadBalancer | Retry integration depending on client/version | Does not guarantee switching instances next time |
| Gateway/service mesh | Infrastructure retry policy | Does not know whether backend side effects already committed |

Let **one place** intentionally own retries for a failure class, or at minimum calculate total HTTP attempts across all layers.

## 14. The outbox problem and side effects outside the database

Suppose `reservation-service` writes a reservation to the database, then emits a `ReservationCreated` event or calls a payment gateway. Storing an idempotency key in the database alone may not prevent emitting the event twice if code replays after a crash.

~~~mermaid
flowchart TD
    A["POST with key K"] --> B["DB transaction"]
    B --> C["Write idempotency record"]
    B --> D["Write reservation"]
    B --> E["Write outbox event"]
    B --> F["COMMIT"]
    F --> G["Outbox worker publishes event"]
    G --> H["Broker / downstream"]
    H --> I["Idempotent consumer by event ID"]
~~~

A **transactional outbox** typically writes the domain row and outgoing event inside the same DB transaction. A worker publishes the event after commit, preventing cases where "DB committed but the process died before publishing." However, the outbox worker can still publish an event **multiple times** on retry, so consumers need deduplication/idempotency by event ID.

When the side effect is a **third-party payment**, pass an idempotency key or transaction ID supported by the payment provider alongside reconciliation. If the external party lacks duplicate protection, redesign the workflow—never promise end-to-end "exactly once" from an internal unique constraint alone.

## 15. "Exactly once" requires defining the scope

Three easily confused concepts:

| Goal | Meaning | How is it achieved? |
|---|---|---|
| At-most-once **business effect** | One intent never creates side effects more than once | Deduplication key + atomic side effect inside a controlled boundary |
| At-least-once **delivery/attempts** | Can resend multiple times to raise execution likelihood | Bounded retries and acceptance mechanisms |
| Exactly-once **end-to-end** | Zero loss and zero duplication of all side effects system-wide | Cannot be inferred from HTTP retries/keys alone; requires contracts and mechanisms per boundary |

For example, a system may send three HTTP requests with the same key for **at-least-once attempts**, while the backend creates one reservation in a DB transaction for **at-most-once side effect** on reservations. That still does not make a Kafka event or email fire once if those are separate steps.

Never throw around labels like "exactly once" or "idempotent" without naming **the protected target**: reservation row, payment authorization, inventory update, email, or full workflow.

## 16. Key retention and handling stuck PENDING records

Idempotency records cannot be kept forever in every system, yet deleting them too early lets the same key execute again as a brand-new request.

Example:

~~~text
T0     POST key=K -> creates reservation
T+5m   caller retries after an outage
T+1h   reconciliation batch checks because webhook didn't arrive
T+24h  last valid replay window under contract
~~~

Key TTL must reflect **retry horizon + reconciliation window + business and legal requirements**, not a 1-second HTTP timeout. Before purging records, consider results stored elsewhere, lookup by operation ID, and long-term duplicate protection.

For long-lived PENDING records:

1. Determine whether the worker owning the attempt is still alive or dead.
2. Check side effects by operation ID and external non-DB dependency states.
3. Apply proper lease/recovery mechanisms if work can continue.
4. Never re-run side effects simply because `updated_at` looks old.
5. Record the reconciliation outcome before transitioning state and releasing the key.

A process dying right after sending a command to a payment gateway and before receiving a response is especially dangerous: query transaction status at the gateway instead of creating a brand-new payment.

## 17. Observability to distinguish operations from HTTP attempts

If you only count HTTP statuses per instance, one operation retried three times looks like three independent requests. Link attempts to a **business operation ID**.

| Field or metric | Purpose |
|---|---|
| `operationId` / masked key | Connects all attempts of one intent |
| `attemptNumber` | Shows which send attempt this is |
| `serviceId` | Identifies logical downstream |
| `selectedInstance` | Shows which replica LoadBalancer picked |
| `timeoutKind` / exception cause | Distinguishes connect, read, response, and overall deadline |
| `httpStatus` | Shows whether an HTTP response arrived |
| `idempotencyOutcome` | NEW, REPLAY, CONFLICT, PENDING, COMPLETED |
| `businessResultId` | Cross-checks the created reservation/payment |
| `retryDelay` / remaining deadline | Spots overly dense retries or budget overruns |
| `dedupConflictCount` | Detects callers reusing a key with different payloads |
| `inflightOperations` | Tracks PENDING keys and queues |
| `reconciliationLag` | Measures how long UNKNOWN stays unresolved |

**Illustrative** log example, not a default Spring Cloud format:

~~~text
caller op=op-71 attempt=1 key_hash=*** service=reservation-service instance=A
server-A op=op-71 idem=NEW reservation=reservation-101 committed=true
caller op=op-71 attempt=1 result=READ_TIMEOUT
caller op=op-71 attempt=2 key_hash=*** instance=B
server-B op=op-71 idem=REPLAY reservation=reservation-101
caller op=op-71 result=COMPLETED reservation=reservation-101
~~~

Never write full tokens, Authorization headers, sensitive payloads, or raw keys into public logs. For metrics, avoid high-cardinality tags like operation ID or idempotency key; put fine details in access-controlled traces/logs.

If caller and server clocks drift, never deduce event ordering solely by subtracting timestamps from two hosts. Use trace context, server transaction logs, and correlation IDs as evidence.

## 18. Retry budgets: preventing load amplification during outages

Suppose a service receives 200 business operations/second, each permitted up to **three attempts**:

~~~text
No retry:          200 HTTP attempts/second
When most fail:    up to ~600 HTTP attempts/second
Load multiplier:   up to ~3x
~~~

If a gateway also retries each caller HTTP attempt three times, downstream attempt volume can surge far higher depending on active retry conditions. Increasing load right when a dependency is slow triggers a timeout → retry → overload → timeout loop.

A retry policy needs:

- **Total attempts** and clearly defined retry counts; many APIs count "maxRetries" excluding the initial attempt.
- **Bounded backoff**, usually with jitter to reduce synchronization.
- **Overall deadline** aligned with SLOs and remaining time before the next attempt.
- **Allowlist of recoverable errors**; never retry validation, auth, or payload conflict errors.
- **Idempotency precondition** for any side-effecting operation.
- **Circuit breakers, bulkheads/concurrency limits, and load shedding** when dependencies overload.
- **Dedicated metrics** for retry attempts, timeouts, and operation success/failure/unknown.

When a `429`/`503` includes `Retry-After`, evaluate it against the caller's deadline; never wait indefinitely just because the server suggested a long delay. When an operation is UNKNOWN, prefer querying status by key/operation ID or retrying idempotently instead of sending a new key.

## 19. Retry decision matrix by method and outcome

| Request/situation | Suggested handling | Safety conditions |
|---|---|---|
| GET hits transient network fault | Can retry with limits | GET causes zero business side effects |
| GET returns valid 404 | Do not retry mechanically | Contract confirms resource does not exist |
| PUT sets absolute state | Consider retrying | Implementation is genuinely idempotent |
| PATCH increments counters | Do not retry blindly | Requires key/dedup or operation token |
| Reservation-creating POST, connect timeout | Retry with same key if needed | Server supports key/shared store |
| Reservation-creating POST, read timeout | UNKNOWN; query status or retry with same key | Never change key; atomic dedup |
| POST returns 409 for key with different payload | Do not retry verbatim as transient | Fix payload/key usage per contract |
| HTTP 429/503 | Conditional retry | Deadline, backoff, Retry-After, no overload |
| No ServiceInstance available | Distinguish discovery/health error | More retries won't create instances |
| Server returns 500 after side effect | UNKNOWN unless contract guarantees rollback | Query/replay same key; never create new operation |
| Status API temporarily fails | Keep UNKNOWN, reconcile | Never turn a query failure into FAILED |

This matrix is an evaluation framework. In production, verify each endpoint's semantics and business state definitions rather than rigidly relying on HTTP method/status alone.

## 20. Required test suite before enabling retries on writes

A reliable idempotency mechanism must be tested across **failure windows**:

| Scenario | Evidence to collect |
|---|---|
| Two concurrent POSTs with same key/payload | Exactly one domain side effect |
| POST with same key, different payload | Conflict, no second write |
| Server commits then loses response | Caller enters UNKNOWN; lookup finds outcome |
| Retry same key onto another instance | Shared result returned; no second reservation created |
| Caller times out while server is PENDING | Only one processor executes the work |
| Process crashes after claiming key | Record recovers; never stuck indefinitely |
| Crash after DB commit, before publishing event | Outbox/event still publishes per contract |
| Outbox emits duplicate event | Consumer deduplicates/handles idempotently |
| Payment gateway succeeded, local missed response | Reconciles using provider key |
| Key expires within valid retry window | System does not create out-of-contract duplicates |
| Retries active in both client and gateway | Total attempts stay within budget |
| No healthy ServiceInstance left | Caller classifies failure prior to HTTP |
| Server returns 409/400/401/403 | Not retried as transient errors |
| Operation already COMPLETED yet status query fails | Never swaps keys or starts a new operation |
| Service restarts with shared DB | Keys and outcomes remain intact |

With the in-memory lab in section 9, **single-process** tests can run immediately to verify local deduplication. **Multi-instance/restart** tests must use a shared storage implementation; re-running the in-memory lab across two processes will produce duplicates **as expected**, not prove production readiness.

## 21. Implementation checklist and misconceptions to avoid

Before enabling retries in the Spring Cloud LoadBalancer module, verify:

1. **What operation is being protected?** Separate HTTP requests from business intent.
2. **Is the request genuinely idempotent?** Never rely solely on the method name.
3. **Where is the idempotency key generated?** It must stay stable across all attempts of one operation.
4. **Is the key scoped by tenant/owner and operation?** Prevent cross-caller data leaks.
5. **Are payloads/fingerprints compared?** Same key with a different command must conflict.
6. **Are atomic claims and unique constraints in place?** Prevent two replicas from both processing.
7. **Are keys/outcomes in a shared durable store?** LoadBalancer can select another replica.
8. **Are PENDING/COMPLETED/FAILED explicit?** Never turn every timeout into FAILED.
9. **Is there a status API or operation ID for reconciliation?** Crucial when responses are lost.
10. **Is retention long enough?** Keys must not expire mid-retry or mid-reconciliation.
11. **Are there non-DB side effects?** Account for outbox, idempotent consumers, and provider keys.
12. **Which layers have retries enabled?** Sum total attempts, backoff, and deadlines.
13. **Does the HTTP client separate pre-response errors from status responses?**
14. **Can health/discovery switch instances on retry?** Test with two replicas.
15. **Do logs/traces include operation ID, attempt, and idempotency outcome?**
16. **Are concurrency, crash, timeout, and replay scenarios tested?**

Statements to avoid:

- "Client timeout means the server didn't run."
- "With POST you can never retry."
- "Just setting the `Idempotency-Key` header is enough."
- "A JVM lock is safe enough because LoadBalancer picks one instance."
- "Having a unique key means all system-wide side effects are exactly-once."
- "Retrying via LoadBalancer always switches to another instance."
- "Seeing HTTP `500` proves the DB rolled back."
- "A `404` status query proves the first request never ran."
- "Setting key TTL equal to the HTTP read timeout is enough."

## 22. Summary

**Idempotency** is a property of **business behavior** when repeating an operation. An **idempotency key** lets the server recognize attempts sharing one intent; working correctly requires payload comparison, unique/atomic claims, durable state and outcome storage, cross-instance sharing, and handling external side effects. **Unknown outcomes** arise when the caller lacks proof of whether the backend completed the request; the right response is keeping the same operation key, querying/reconciling, and retrying in a controlled manner per contract.

In **Spring Cloud LoadBalancer**, each HTTP attempt through RestClient, WebClient, or OpenFeign can traverse discovery, health checks, `ServiceInstance` selection, and timeouts. Those components assist routing and communication recovery—they **do not automatically prevent duplicate execution**. Before raising retry counts for higher availability, protect side effects with **durable idempotency**, enforce **budgeted deadlines and backoff**, and clearly distinguish **HTTP attempt counts** from **completed business operations**.
