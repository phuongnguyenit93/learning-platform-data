# Duplicate Request Prevention and Idempotency Key Management with Spring Data Redis

> **Module:** Spring Data Redis  
> **Chapter:** Application Patterns  
> **Topic:** Designing duplicate request handling in Spring Boot applications, using Redis to register idempotency keys, controlling concurrent requests, storing results for replay on retry, and coordinating with databases or business systems to avoid duplicated side effects.

## 1. Real-World Problem: A User Sends One Request, the Server May Receive It Multiple Times

Suppose a user clicks **Place Order**. The server creates the order successfully, but the response is lost on the network. The browser or client retries sending it:

~~~text
Client                      Spring Boot              Database
  | POST /orders (K=abc) ----> |                         |
  |                            | -- CREATE order ------> |
  |                            | <--- order=o-101 ------ |
  |        (lost response)   X |                         |
  | POST /orders (K=abc) ----> |                         |
  |                            | -- CREATE order ------> |
  |                            | <--- order=o-102 ------ |
  | <--- order=o-102 --------- |                         |
~~~

The business intent is **creating one order**, yet the outcome is two orders. Other situations can also cause duplicates:

- A user clicks a button twice very quickly.
- An HTTP client automatically retries on timeouts, connection errors, or `502`/`503`.
- A load balancer routes a request to another instance after the first instance drops.
- A gateway or synchronization service resends a request when the prior outcome is unknown.
- A webhook is delivered multiple times by the provider to increase delivery reliability.
- A consumer processes a message successfully and then crashes before sending an acknowledgement.
- A scheduled task is triggered redundantly due to failover.
- A request is re-sent after a mobile app loses connectivity.

You cannot solve this completely by **disabling the UI button** or "the client remembering to call only once": many request sources are outside server control, and network failures prevent clients from knowing whether a prior request actually executed.

The goal is: **multiple submissions of the same business intent do not produce multiple unwanted side effects**, while still allowing customers to submit a genuinely *new* request when needed.

### 1.1. Definition of Idempotency

Ideally, an operation is idempotent if executing it repeatedly with the same semantics leads to the same final state rather than multiplying side effects.

For example:

~~~redis
SET feature:enabled true
SET feature:enabled true
~~~

Setting the same value twice yields the same final state. Conversely:

~~~redis
INCR orders:created
INCR orders:created
~~~

Running `INCR` twice increments the counter twice; by itself, this command is **not idempotent** if the goal is "one business event is counted only once."

At the HTTP layer:

- `PUT /profiles/101` with the same body *can* be designed to be idempotent.
- `POST /orders` typically creates a new resource and is not inherently idempotent.
- An HTTP method is not enough to guarantee business logic is idempotent: a `PUT` can trigger side effects like sending an email or appending logs if poorly implemented.

An **idempotency key** identifies **the same operational intent** when a request is resent. It does not automatically turn business code into an atomic transaction; the server must design how the key is used properly.

### 1.2. Three Easily Confused Concepts

| Concept | Primary Question | Example |
|---|---|---|
| **Deduplication** | Have we seen this identifier/event before? | Ignoring a webhook with the same event ID |
| **Idempotency** | If the same operation is requested again, what should the result/side effect be? | Returning the same order ID for the same Idempotency-Key |
| **Mutual exclusion / lock** | Can two workers execute a code block at the same time? | Only one worker holds a processing lease for a key at a time |

A Redis lock with a TTL can block two **concurrent** requests, but it does not automatically know a request succeeded earlier. A Redis set storing "seen keys" can prevent running a second time, but cannot replay the previous response. A complete idempotent system generally needs **processing state, result tracking, and retry rules**.

## 2. What Is an Idempotency-Key?

The client generates a stable identifier for **one logical operation**. When retrying the same intent, the client sends **the exact same key**.

HTTP example:

~~~http
POST /api/orders HTTP/1.1
Content-Type: application/json
Idempotency-Key: 5ab802da-df68-414f-959c-ff41bbfd8f87

{
  "sku": "desk-01",
  "quantity": 2
}
~~~

If the client receives no response and retries, it keeps the same header and body. If the user intentionally creates **a second order**, the client generates a new Idempotency-Key.

### 2.1. Distinguishing the Client Key from the Redis Key

A system typically has at least two keys:

1. **Client-supplied Idempotency-Key:** for example, a UUID or random token.
2. **Internal Redis key:** constructed from the business scope and client key, such as `idem:v1:7ac3...`.

Do not use the raw client-supplied string directly as a Redis key without validation and namespacing. A Redis key should generally be built from:

~~~text
Redis key = prefix + hash(
    authenticatedTenantId,
    HTTP operation / endpoint identity,
    client Idempotency-Key
)
~~~

Why scope it? Customers of tenant A and tenant B might both send `request-001`, yet they must not be treated as **the same request**. The same client key used on `POST /orders` and `POST /refunds` should also not collide.

### 2.2. Desirable Properties of Client Keys

- **Stable across retries** of the same intent.
- **Distinct** for new intents.
- **Unpredictable or sufficiently high entropy**, such as UUID v4.
- **Bounded in length and restricted to valid characters** to protect memory and logging.
- Must not contain access tokens, passwords, card details, or sensitive data.
- Has a **supported retention window**: servers cannot keep every used key indefinitely.

Do not use a second-precision timestamp or a product code as a shared Idempotency-Key if multiple independent operations can share that value. Also do not generate a new key on **every retry**: the server would have no signal that they represent the same logical operation.

### 2.3. Why Not Use a Request Fingerprint as the Sole Idempotency-Key?

Two orders for the same SKU and quantity **can** genuinely be two different orders:

~~~text
Attempt 1: buy 1 desk-01
Attempt 2: 1 hour later, buy another desk-01
~~~

If the server uses the body hash as the sole key, the second attempt can be falsely flagged as a duplicate. Therefore:

- **Client idempotency key** distinguishes logical operations.
- **Request fingerprint** verifies a key is not being reused with a **different** payload.

The two concepts complement each other rather than replacing one another.

## 3. Expected Outcomes When Encountering an Existing Key

Suppose `POST /orders` receives Idempotency-Key `K`. Define the handling rules:

| Scenario | What to Do | Possible HTTP Response |
|---|---|---|
| Never seen `K` | Register processing right and execute | `201 Created` upon completion |
| `K` already completed with same fingerprint | Do not re-execute; return **the same prior result** | Return stored `201` + body/orderId |
| `K` is being processed by another worker | Do not execute side effect a second time | `409 Conflict`, `202 Accepted`, or published "in progress" response |
| `K` already used with a different request | Reject improper reuse | `409 Conflict` |
| Redis/key store error or unknown state | Do not silently treat as a new request | `503`/fail-closed policy; or use durable operation ledger |
| Old key expired past TTL | No longer deduplicated by Redis without another durable source | Define retry window and reconciliation |
| Business operation definitely failed before side effects | May allow retry per policy | Only when deterministic failures and ambiguous failures can be distinguished |
| Business operation may have succeeded, response lost | Must not blindly re-execute | Query authoritative state or use idempotency at the durable source |

Choosing `202` vs `409` for an in-progress state is an **API contract decision**, not a hard Redis rule. You can return a `Location` header for status polling and `Retry-After` when appropriate, depending on request type and processing time.

### 3.1. What Response Data Should Be Stored?

If the goal is replaying the same result, a completed record can store:

- HTTP status, e.g. `201`.
- Normalized response body or exact initial body.
- A safe subset of headers such as `Location`.
- Business resource ID, e.g. `orderId`.
- Request fingerprint.
- Creation/completion timestamps and schema version.

Do not blindly store every HTTP header, as headers like session cookies, tokens, or trace identifiers may be inappropriate to replay. When replaying, reapply **authorization** for the current caller. An idempotency record must never become a way for another user to read sensitive responses simply by guessing a key.

## 4. State Model: NEW → PROCESSING → SUCCEEDED

A practical design uses at least two stored states:

- **PROCESSING:** a worker has claimed the key and is executing.
- **SUCCEEDED:** the operation succeeded and has a response to replay.

Optional additions:

- **FAILED_FINAL:** deterministic failure that should not be retried with the same key if the contract calls for caching terminal errors.
- **RECONCILIATION_REQUIRED:** outcome unclear; needs reconciliation against the authoritative source.
- **EXPIRED:** state no longer in Redis; typically represented by **absence of the key**, not necessarily an actual value stored in Redis.

~~~mermaid
flowchart TD
    START["Request (tenant, operation, key, fingerprint)"] --> CLAIM{"SET key PROCESSING NX EX"}
    CLAIM -- "Created successfully" --> PROCESS["Worker owns lease"]
    CLAIM -- "Key already exists" --> GET["Read state/fingerprint"]
    GET --> FINGER{"Fingerprint matches?"}
    FINGER -- "No" --> CONFLICT["409: key reused for different payload"]
    FINGER -- "Yes" --> STATE{"State?"}
    STATE -- "SUCCEEDED" --> REPLAY["Return stored response"]
    STATE -- "PROCESSING" --> BUSY["Report in progress / poll / retry later"]
    STATE -- "FAILED_FINAL" --> FINAL["Return stored terminal error"]
    PROCESS --> BUSINESS["Execute business logic idempotently at source"]
    BUSINESS --> SUCCESS["Source confirms success"]
    SUCCESS --> CAS["Lua CAS: PROCESSING -> SUCCEEDED"]
    CAS --> RETURN["Return response"]
    BUSINESS --> UNKNOWN["Error or uncertain outcome"]
    UNKNOWN --> RECON["Do not delete blindly: reconcile state"]
~~~

The `PROCESSING` record needs an **owner token** or random claim identifier to identify which worker is authorized to transition state. Without owner verification, an old worker could overwrite a newer result after lease expiration.

### 4.1. Why Is the PROCESSING State Needed?

If you only store results after processing completes:

~~~text
Worker A: GET idem:K -> does not exist
Worker B: GET idem:K -> does not exist
Worker A: creates order o-101
Worker B: creates order o-102
Worker A: SET idem:K = o-101
Worker B: SET idem:K = o-102
~~~

The final record only shows `o-102`, yet **two side effects occurred**.

To prevent both workers from entering execution at once, an **atomic** conditional claim must occur before the business operation.

## 5. Redis SET NX EX: The Atomic Claim Operation

Redis supports:

~~~redis
SET idem:v1:example "PROCESSING:token-abc" NX EX 60
~~~

Meaning:

- `NX`: write only if the key **does not yet exist**.
- `EX 60`: attach a 60-second TTL in the very same command.
- If the write succeeds, the client can treat the key as claimed.
- If the key already exists, Redis does not overwrite it and returns a failure result for the NX condition.

In Spring Data Redis:

~~~java
Boolean claimed = stringRedisTemplate.opsForValue()
        .setIfAbsent(
                "idem:v1:example",
                "PROCESSING:token-abc",
                Duration.ofSeconds(60));

if (Boolean.TRUE.equals(claimed)) {
    // Client claimed the key.
} else if (Boolean.FALSE.equals(claimed)) {
    // Key already exists; read state.
} else {
    // Some pipelining/transaction contexts do not return a Boolean
    // immediately; do not confuse null with false or true.
}
~~~

For normal calls outside pipelines/transactions, the result is typically a Boolean. Using `Boolean.TRUE.equals(...)` avoids `NullPointerException` when the result is null in special contexts.

### 5.1. Why Not Use GET Followed by SET?

Unsafe:

~~~java
if (redis.opsForValue().get(key) == null) {
    redis.opsForValue().set(key, "PROCESSING");
    performBusinessAction();
}
~~~

Both workers can observe that the key does not exist before either calls SET. This is a *check-then-act race*.

Similarly, avoid:

~~~java
if (redis.opsForValue().setIfAbsent(key, token)) {
    redis.expire(key, Duration.ofSeconds(60));
}
~~~

when the API supports `setIfAbsent(key, value, Duration)`. When SETNX and EXPIRE are **two commands**, crashing between them can leave a key with no TTL, getting stuck forever. `SET ... NX EX ...` performs the condition and TTL in a single command.

### 5.2. A Claim Is a Lease, Not Permanent Ownership

A PROCESSING key with a 60-second TTL means that after 60 seconds the key can expire even if the original worker is still processing.

~~~text
t=00  Worker A claims key K with 60s TTL
t=10  A starts calling a slow service
t=60  Redis key K expires
t=61  Worker B successfully claims key K again
t=62  A is still running
t=63  B is also running
~~~

Redis behaved correctly according to the TTL. **`SET NX EX` cannot strictly guarantee a single side effect** if the lease is shorter than processing time, or if a worker pauses, disconnects, or fails over.

Solutions must consider the business layer:

- Choose an appropriate lease and extend it when needed.
- Perform CAS by owner token upon completion.
- Use an operation ID/idempotency key at **the side-effect source**.
- Use database unique constraints/transactions when durable execution is required.
- Use fencing/version tokens when the downstream resource supports rejecting stale owners.

Do not present a Redis lease as "exactly-once" for a business transaction.

## 6. Designing Redis Keys, Fingerprints, and TTLs

### 6.1. Internal Redis Key Naming

A pattern:

~~~text
idem:<schema-version>:<sha256(scope + client-key)>
~~~

Where scope can include:

~~~text
authenticated tenant ID
+ operation ID (POST /orders, POST /refunds...)
+ API contract version
+ client Idempotency-Key
~~~

Example:

~~~text
idem:v1:9d99d7d3a8ae9d52...
~~~

SHA-256 produces a fixed-length key and reduces raw identifier exposure in Redis keys. It **does not replace** authentication or authorization checks: a client might know an Idempotency-Key yet have no permission to view another tenant's order.

### 6.2. Request Content Fingerprint

The server computes a stable fingerprint:

~~~text
fingerprint = SHA-256(
    operation contract version
    + canonicalized business request body
)
~~~

Same key + same fingerprint => likely a retry of the same intent.

Same key + different fingerprint => reject with `409 Conflict`.

**Canonicalization must be defined.** The following two JSON payloads can represent the same business request despite differing bytes:

~~~json
{"sku":"desk-01","quantity":2}
~~~

~~~json
{
  "quantity": 2,
  "sku": "desk-01"
}
~~~

Hashing the raw HTTP body produces different fingerprints for these two payloads. Options include:

- Parse into a DTO with fixed fields and canonicalize serialization under stable rules.
- Define an explicit field order before hashing.
- Normalize Unicode, decimals, currency, and time zones when business rules require it.
- Ignore metadata that does not affect results, such as tracing headers.
- Require keeping fields **that affect business behavior**, such as amount, currency, shipping address, and discount code.

Do not arbitrarily normalize two different requests to the same fingerprint if a field actually changes the side effect.

### 6.3. PROCESSING TTL vs. Completed Result TTL

The two TTLs should not be conflated.

| State Type | Purpose | How to Choose TTL |
|---|---|---|
| `PROCESSING` | Lease to prevent concurrent workers from executing | Based on processing timeout, watchdog, and recovery needs |
| `SUCCEEDED` | Replay result when client retries | Based on published retry window, business rules, and reconciliation span |
| `FAILED_FINAL` | Replay deterministic errors if needed | Per API contract |
| Durable DB record | Ensure the same business operation never duplicates | Per business/compliance retention, not tied to Redis TTL |

Setting `PROCESSING` to 2 minutes and `SUCCEEDED` to 24 hours is **merely an illustrative choice**. If partners are allowed to retry within 7 days, retaining Redis results for 24 hours is insufficient; a durable idempotency ledger or matching retention is required.

Too short a TTL lets late retries be treated as new requests. Too long a TTL accumulates keys in RAM. Monitor key counts, response sizes, retention, and eviction.

## 7. A Single Redis Record: Simplifying Atomic State Transitions

There are two storage approaches:

1. **One Redis String key** storing JSON for PROCESSING or SUCCEEDED state.
2. **Multiple Redis keys**: one lock/lease key, one result and metadata key.

To avoid unsynchronized state windows across keys, the example favors **one JSON key** with Lua compare-and-set transitions.

### 7.1. PROCESSING Record

~~~json
{
  "state": "PROCESSING",
  "fingerprint": "sha256-of-request",
  "ownerToken": "f7238bd1-c536-48f1-99ad-f3a30bb842fa",
  "httpStatus": null,
  "responseBody": null
}
~~~

### 7.2. SUCCEEDED Record

~~~json
{
  "state": "SUCCEEDED",
  "fingerprint": "sha256-of-request",
  "ownerToken": "f7238bd1-c536-48f1-99ad-f3a30bb842fa",
  "httpStatus": 201,
  "responseBody": "{\"orderId\":\"o-101\",\"status\":\"CREATED\"}"
}
~~~

Storing the response body as a JSON string inside a JSON record is a deliberate design choice: the client receives the original body while the service manages metadata. You can store the business result in another structure to save space and control schema.

**Design point:** the stored response must comply with security policies, size limits, and versioning. If responses contain personal data, restrict Redis permissions, TTLs, and logging, and consider storing only the resource ID and reconstructing the response from the database on replay.

### 7.3. Avoid Uncontrolled Java Object Serialization

This example chooses:

- `StringRedisTemplate` so Redis keys/values are UTF-8 Strings.
- Jackson `ObjectMapper` to convert `IdempotencyRecord` ↔ JSON.
- Version inside the key prefix `idem:v1:`.
- JSON payloads without internal Java class names.

If changing the storage format, maintain compatibility for old records during the TTL window or bump the version prefix. Never switch from JSON to JDK serialization within the same namespace without a migration plan.

## 8. Lua CAS: Only the Owner May Write the Result

Suppose worker A claims successfully. Before finishing, the lease expires and worker B claims. If A blindly runs:

~~~redis
SET idem:K "{\"state\":\"SUCCEEDED\",...}"
~~~

A can overwrite the state owned by B. Worse, A could record a stale response after B already finished.

The solution is **compare-and-set** directly on the Redis server. Transition state only when the current value is still the PROCESSING record that this worker claimed.

### 8.1. Conditional Completion Script

~~~lua
-- KEYS[1]: Redis idempotency key
-- ARGV[1]: PROCESSING JSON stored by owner
-- ARGV[2]: SUCCEEDED JSON to write
-- ARGV[3]: Result TTL, milliseconds

if redis.call('GET', KEYS[1]) ~= ARGV[1] then
    return 0
end

redis.call('PSETEX', KEYS[1], tonumber(ARGV[3]), ARGV[2])
return 1
~~~

Every step (`GET`–compare–`PSETEX`) runs inside **one atomic Lua script** on the Redis server; an old worker cannot overwrite a changed value while the script runs.

The script touches **one Redis key**, which also works cleanly with Redis Cluster since two keys cannot fall in different slots. If extending the script to access additional Redis keys, you must adhere to cluster hash slot constraints.

### 8.2. Why Does Comparing the Full JSON Work Here?

In this pattern, the worker retains **the exact JSON string** it wrote to Redis during the claim step. The script compares byte-for-byte against the current value. This CAS approach is safe if no other code modifies the record while PROCESSING.

In systems with a heartbeat updating dynamic fields by rewriting JSON, comparing the full string may fail because the record changed. In that case:

- Store the token in a stable field inside a Redis Hash and compare the token with Lua `HGET`.
- Or use a JSON model whose token is parsed/checked properly on the server.
- Design CAS around separating the **owner token** from **status** rather than depending on the whole value string.
- Never allow one worker to extend another worker's lease.

CAS protects **writing the result record in Redis**, not side effects already executed in the database or payment provider before CAS.

## 9. Spring Boot Example: Data Models and Business Contract

The example uses **Java 17+**, Spring Boot with imperative Spring Data Redis, Jackson, and Spring Web. The goal is illustrating a clear idempotency gate, not claiming Redis is the guaranteed source of exactly-once for critical transactions.

### 9.1. Dependencies

Gradle Kotlin DSL:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-data-redis")
}
~~~

Spring Boot normally provides `StringRedisTemplate` when an appropriate connection factory is configured. Jackson is included via the web starter in typical configurations.

Redis connection via YAML:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      timeout: 2s
~~~

If production uses Cluster, Sentinel, managed Redis/TLS, or ACLs, update the configuration accordingly. A Redis idempotency store requires monitoring, timeouts, and explicit RAM/eviction policies.

### 9.2. Request and Business Result

~~~java
// File CreateOrderRequest.java
public record CreateOrderRequest(
        String sku,
        int quantity) {
}

// File OrderReceipt.java
public record OrderReceipt(
        String orderId,
        String status) {
}
~~~

Business service contract:

~~~java
// File OrderApplicationService.java
public interface OrderApplicationService {

    OrderReceipt createOrGet(
            String tenantId,
            String operationKey,
            String requestFingerprint,
            CreateOrderRequest request);
}
~~~

**This is an application interface, not a built-in Spring Data Redis API.**

`createOrGet` must have durable semantics: if the same `tenantId + operationKey` is invoked again, it returns the previously recorded order instead of creating a new one, while validating the fingerprint. In critical systems, the implementation needs database transactions and unique constraints, or payment-provider idempotency.

Without this durable guarantee layer, the outer Redis gate is only **best-effort deduplication during the TTL window**.

### 9.3. JSON-Serializable Redis Record

~~~java
// File IdempotencyRecord.java
public record IdempotencyRecord(
        String state,
        String fingerprint,
        String ownerToken,
        Integer httpStatus,
        String responseBody) {
}
~~~

In practice you can add `createdAt`, `completedAt`, `schemaVersion`, `businessResourceId`, `correlationId`, and a result checksum. You do not need to store the raw request body if the fingerprint suffices to verify reuse under your API policy.

## 10. Writing the Redis Gate Class: Claim, Read, Finish

### 10.1. Implementation

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Duration;
import java.util.HexFormat;
import java.util.List;
import java.util.UUID;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.stereotype.Component;

@Component
public class RedisIdempotencyGate {

    private static final Duration LEASE = Duration.ofMinutes(2);
    private static final Duration RESULT_TTL = Duration.ofHours(24);

    private static final DefaultRedisScript<Long> FINISH_SCRIPT =
            new DefaultRedisScript<>();

    static {
        FINISH_SCRIPT.setScriptText("""
            if redis.call('GET', KEYS[1]) ~= ARGV[1] then
                return 0
            end
            redis.call('PSETEX', KEYS[1], tonumber(ARGV[3]), ARGV[2])
            return 1
            """);
        FINISH_SCRIPT.setResultType(Long.class);
    }

    private final StringRedisTemplate redis;
    private final ObjectMapper mapper;

    public RedisIdempotencyGate(
            StringRedisTemplate redis,
            ObjectMapper mapper) {
        this.redis = redis;
        this.mapper = mapper;
    }

    public String redisKey(
            String tenantId, String operation, String clientKey) {
        // Input values must be validated before calling.
        String scoped = tenantId + "\u0000"
                + operation + "\u0000" + clientKey;
        return "idem:v1:" + sha256(scoped);
    }

    public Claim tryClaim(String key, String fingerprint) {
        String token = UUID.randomUUID().toString();

        IdempotencyRecord processing = new IdempotencyRecord(
                "PROCESSING", fingerprint, token, null, null);
        String json = encode(processing);

        Boolean claimed =
                redis.opsForValue().setIfAbsent(key, json, LEASE);

        if (Boolean.TRUE.equals(claimed)) {
            return new Claim(true, json, processing);
        }

        if (Boolean.FALSE.equals(claimed)) {
            return new Claim(false, null, read(key));
        }

        throw new IllegalStateException(
                "Redis claim result unavailable");
    }

    public IdempotencyRecord read(String key) {
        String json = redis.opsForValue().get(key);
        if (json == null) {
            return null;
        }
        try {
            return mapper.readValue(json, IdempotencyRecord.class);
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException(
                    "Cannot decode idempotency record", ex);
        }
    }

    public boolean finish(
            String key,
            String expectedProcessingJson,
            IdempotencyRecord completed) {

        String completedJson = encode(completed);

        Long changed = redis.execute(
                FINISH_SCRIPT,
                List.of(key),
                expectedProcessingJson,
                completedJson,
                Long.toString(RESULT_TTL.toMillis()));

        return Long.valueOf(1L).equals(changed);
    }

    private String encode(IdempotencyRecord record) {
        try {
            return mapper.writeValueAsString(record);
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException(
                    "Cannot serialize idempotency record", ex);
        }
    }

    public static String sha256(String value) {
        try {
            byte[] digest = MessageDigest
                    .getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException("SHA-256 unavailable", ex);
        }
    }

    public record Claim(
            boolean acquired,
            String expectedProcessingJson,
            IdempotencyRecord current) {
    }
}
~~~

Explanation:

- `tryClaim` uses a single Redis `SET NX EX` command for the PROCESSING state and TTL.
- When the key already exists, it reads state/fingerprint so the caller can decide between replay, conflict, or reporting in-progress.
- `finish` uses Lua CAS to avoid overwriting another owner's state.
- `sha256` generates fixed-length internal Redis key names.
- `IdempotencyRecord` is JSON-encoded using Jackson and the Redis String serializer rather than default Java object serialization.

### 10.2. A Small Race Window When Reading an Existing Record

Scenario:

~~~text
SET NX returns false: key exists
Immediately afterward, key expires past TTL
GET returns null
~~~

This can happen because `SET NX` and the `GET` on the existing branch are two separate commands. **Never** infer from `GET null` that the request was never processed and execute business logic immediately.

The caller can return a temporary status asking to retry, or look up the durable ledger to decide. If retrying the claim, it must run **the atomic claim** again rather than bypassing it.

### 10.3. Limit When the Lease Expires Mid-Processing

Lua CAS returns 0 if the lease expired or was replaced by a new owner. Do not interpret "CAS=0 therefore the earlier business operation did not happen." Order creation may already have committed before Redis rejected writing the cached result.

That is why `OrderApplicationService.createOrGet` needs its own durable guarantee. The Redis gate cuts down duplicate work, **and is not the sole guarantor that an order is created exactly once**.

## 11. Service Combining the Redis Gate and Business Logic

This example returns `ResponseEntity<String>` directly to illustrate replaying the stored response body.

~~~java
import java.util.regex.Pattern;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;

@Service
public class IdempotentOrderFacade {

    private static final Pattern IDEMPOTENCY_KEY =
            Pattern.compile("[A-Za-z0-9._-]{8,128}");

    private final RedisIdempotencyGate gate;
    private final OrderApplicationService orders;
    private final ObjectMapper mapper;

    public IdempotentOrderFacade(
            RedisIdempotencyGate gate,
            OrderApplicationService orders,
            ObjectMapper mapper) {
        this.gate = gate;
        this.orders = orders;
        this.mapper = mapper;
    }

    public ResponseEntity<String> create(
            String authenticatedTenantId,
            String clientKey,
            CreateOrderRequest request) {

        if (authenticatedTenantId == null
                || authenticatedTenantId.isBlank()
                || clientKey == null
                || !IDEMPOTENCY_KEY.matcher(clientKey).matches()
                || request == null
                || request.sku() == null
                || !request.sku().matches("[A-Za-z0-9._-]{1,64}")
                || request.quantity() <= 0) {

            return ResponseEntity.badRequest()
                    .body("Invalid request or Idempotency-Key");
        }

        String operation = "POST:/api/orders:v1";
        String redisKey = gate.redisKey(
                authenticatedTenantId, operation, clientKey);

        // For this DTO, encode fields in an explicit order.
        String fingerprint = RedisIdempotencyGate.sha256(
                "CreateOrder:v1\u0000"
                + request.sku() + "\u0000"
                + request.quantity());

        RedisIdempotencyGate.Claim claim =
                gate.tryClaim(redisKey, fingerprint);

        if (!claim.acquired()) {
            IdempotencyRecord existing = claim.current();

            if (existing == null) {
                // Key may have just expired between SET NX and GET.
                return ResponseEntity.status(503)
                        .body("State changed; retry safely");
            }

            if (!fingerprint.equals(existing.fingerprint())) {
                return ResponseEntity.status(409)
                        .body("Idempotency-Key reused with new payload");
            }

            if ("SUCCEEDED".equals(existing.state())) {
                return ResponseEntity
                        .status(existing.httpStatus())
                        .body(existing.responseBody());
            }

            if ("PROCESSING".equals(existing.state())) {
                return ResponseEntity.status(409)
                        .body("Request is still processing");
            }

            return ResponseEntity.status(503)
                    .body("Idempotency state requires reconciliation");
        }

        // Only the worker owning the claim proceeds to business logic.
        // The business source must still enforce createOrGet idempotently.
        OrderReceipt receipt = orders.createOrGet(
                authenticatedTenantId,
                clientKey,
                fingerprint,
                request);

        String body;
        try {
            body = mapper.writeValueAsString(receipt);
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException(
                    "Cannot serialize order receipt", ex);
        }

        IdempotencyRecord completed = new IdempotencyRecord(
                "SUCCEEDED",
                fingerprint,
                claim.current().ownerToken(),
                201,
                body);

        boolean stored = gate.finish(
                redisKey,
                claim.expectedProcessingJson(),
                completed);

        if (!stored) {
            // Business operation may already have committed.
            // Never create a second order automatically.
            return ResponseEntity.status(503)
                    .body("Order outcome recorded; reconcile state");
        }

        return ResponseEntity.status(201).body(body);
    }
}
~~~

### 11.1. Which Parts Are Illustrative and Which Are Commitments?

- The facade code shows the **Redis gate protocol**: claim → validate existing → call business logic → CAS store result.
- `OrderApplicationService` is a **required application-implemented dependency**.
- Critical assumption: `orders.createOrGet(...)` **already implements** durable idempotency to guard against Redis lease expiration/failover.
- The illustrative code omits full controller details, authentication, tracing, circuit breakers, logging, timeouts, and complete HTTP error mapping.
- The Redis error branch throws exceptions through the template if no API handler is present; production needs proper response mapping.
- The business error branch **does not delete the claim immediately** because it is unknown whether side effects occurred. Recovery/reconciliation must follow policy.

Without durable protection at the source, the sample **is only a best-effort deduplication layer** and must not be advertised as "exactly once" for payments or orders.

### 11.2. Creating the Endpoint in Spring MVC

A controller can extract tenant ID from the authenticated principal rather than trusting an arbitrary client-supplied `X-Tenant-Id` header:

~~~java
@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final IdempotentOrderFacade facade;
    private final TenantIdentity tenantIdentity;

    public OrderController(
            IdempotentOrderFacade facade,
            TenantIdentity tenantIdentity) {
        this.facade = facade;
        this.tenantIdentity = tenantIdentity;
    }

    @PostMapping
    public ResponseEntity<String> create(
            @RequestHeader("Idempotency-Key") String key,
            @RequestBody CreateOrderRequest request) {

        String tenantId = tenantIdentity.currentTenantId();
        return facade.create(tenantId, key, request);
    }
}
~~~

`TenantIdentity` is an application-provided abstraction retrieving the authenticated/authorized tenant from the security context.

A request missing the header should receive an appropriate HTTP error handled by Spring MVC and the API contract; do not auto-generate a new key on the server when a client **is retrying** without keeping its old key, because the server cannot tell the two requests share the same logical intent.

## 12. Ensuring Durability: A Redis Gate Does Not Replace Business Transactions

This is the most important boundary.

### 12.1. Scenario: Redis Stores Claim, Database Creates Order, Then Application Crashes

~~~text
1. Redis: idem:K = PROCESSING (2-minute TTL)
2. Database: creates order o-101 and COMMITS
3. Spring instance crashes before writing SUCCEEDED to Redis
4. Client retries:
   - Within TTL: receives PROCESSING
   - After TTL: Redis key is gone, a new claim can succeed
5. If business logic lacks DB-level idempotency:
   - Post-TTL request may create o-102
~~~

Storing the result in Redis after the DB commit involves **two operations across two different systems**. Redis CAS does not form a distributed transaction with the database.

### 12.2. Durable Idempotency Ledger Record

For critical operations, maintain an idempotency table in the source database:

~~~sql
CREATE TABLE idempotency_operations (
    tenant_id         VARCHAR(64)  NOT NULL,
    operation_name    VARCHAR(100) NOT NULL,
    idempotency_key   VARCHAR(128) NOT NULL,
    request_hash      CHAR(64)     NOT NULL,
    state             VARCHAR(32)  NOT NULL,
    resource_id       VARCHAR(128),
    response_json     TEXT,
    created_at        TIMESTAMP NOT NULL,
    updated_at        TIMESTAMP NOT NULL,
    PRIMARY KEY (tenant_id, operation_name, idempotency_key)
);
~~~

An appropriate transaction can:

1. Attempt to register the operation via unique key.
2. If the key already exists, compare `request_hash`.
3. If the operation already succeeded, return the stored result/resource ID.
4. If not yet processed and the caller holds claim authority via transaction/row-lock/version, execute business logic.
5. Insert the order and update the operation to `SUCCEEDED` **within the same DB transaction**, if business rules and data sources allow.
6. Commit.
7. The Redis cache can be updated post-commit so subsequent retries are faster.

The essence is **the unique constraint and DB transaction**, not having a table named `idempotency_operations`. You must ensure creating the order and marking the operation succeeded genuinely lie within an appropriate commit boundary.

### 12.3. Illustrative SQL Protocol

A common pattern on PostgreSQL:

~~~sql
INSERT INTO idempotency_operations (
    tenant_id, operation_name, idempotency_key,
    request_hash, state, created_at, updated_at
)
VALUES (
    :tenant_id, :operation_name, :key,
    :request_hash, 'PROCESSING', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
)
ON CONFLICT (tenant_id, operation_name, idempotency_key)
DO NOTHING;
~~~

Afterward you must **check the inserted row count**, handle collisions and existing records using proper locking/versioning. Do not treat `INSERT ... ON CONFLICT DO NOTHING` alone as sufficient atomicity between the ledger and orders.

Inside an appropriate transaction, create the order and update:

~~~sql
UPDATE idempotency_operations
SET state = 'SUCCEEDED',
    resource_id = :order_id,
    response_json = :response_json,
    updated_at = CURRENT_TIMESTAMP
WHERE tenant_id = :tenant_id
  AND operation_name = :operation_name
  AND idempotency_key = :key;
~~~

These SQL snippets illustrate uniqueness and commit boundaries, not a complete production stored procedure. Under transaction locks, deadlocks, constraint errors, and retries must have explicit policies.

### 12.4. When Calling an External Payment System

If the side effect is calling a payment provider, a database transaction **cannot commit atomically with the payment API**. You should:

- Pass a stable idempotency key downstream to the provider **if supported by the provider**.
- Persist the operation ID and state in the DB before calling the provider.
- On timeout, **query payment status** by operation ID/provider request ID before retrying.
- Use an outbox/saga/workflow to execute side effects statefully and recoverably.
- Never assume HTTP 504 means the provider definitely did not charge.

Idempotency must be implemented **at the side-effect boundary**, not solely at the Redis API gateway.

## 13. Difference Between Duplicate Suppression and Response Replay

A very lightweight pattern:

~~~java
Boolean first = redis.opsForValue().setIfAbsent(
        "webhook:seen:" + eventId,
        "1",
        Duration.ofDays(2));

if (Boolean.TRUE.equals(first)) {
    processWebhook();
}
~~~

This approach only marks that the event was **seen**, without knowing whether `processWebhook()` succeeded.

### 13.1. Problem with Marking Before Processing

~~~text
SETNX seen:event-101 = true   -> succeeds
processWebhook()              -> fails midway
Webhook is resent             -> blocked because seen already exists
~~~

An event **not successfully processed** is treated as handled. This can lose work.

### 13.2. Problem with Marking After Processing

~~~text
Worker A: sees event not yet processed
Worker B: sees event not yet processed
A: process webhook
B: process webhook
A: set seen
B: set seen
~~~

Without an atomic pre-claim, two workers can process the same event.

### 13.3. When Is Simple SET NX Enough?

Suitable for *best-effort* signals where occasional drops or duplicates are acceptable, such as a minor secondary notification. Do not use it standalone for:

- Payment confirmations.
- Accounting ledger writes.
- Granting legally binding entitlements.
- Money transfers.
- Authoritative inventory synchronization.
- Webhooks that must eventually be processed.

For critical events, use a durable inbox/ledger and confirm completion after side effects finish, paired with retries/idempotency.

## 14. Why Not Rely Solely on a Redis Distributed Lock?

A distributed lock following the pattern:

~~~redis
SET lock:order:101 token-abc NX PX 30000
~~~

provides **mutual exclusion during the lease**. However, it does not store business results and does not guarantee a transaction finished before the lease expired.

### 14.1. Problem of an Old Owner Deleting a New Lock

Unsafe:

~~~text
t=0   Worker A acquires lock token=A
t=30  Lock A expires
t=31  Worker B acquires lock token=B
t=32  Worker A calls DEL lock (deletes B's lock)
t=33  Worker C can also acquire the lock
~~~

Never use an unconditional `DEL` to release a lock that may have expired or switched owners.

### 14.2. Lua Compare-and-Delete

~~~lua
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
~~~

Deletes only if the Redis value matches the owner token. This pattern prevents A from deleting B's lock, yet **does not stop worker A from starting a side effect before losing the lease**. Downstream resources must reject stale owners themselves for strict protection.

### 14.3. Fencing Token

A *fencing token* is a monotonically increasing sequence/version issued alongside operational authority, where **the final resource** records the highest token received and rejects smaller tokens.

~~~text
Worker A receives fencing token 41
Worker A pauses
Worker B receives fencing token 42
Storage records token 42 and applies B's update
Worker A resumes with token 41
Storage rejects A's update
~~~

Generating a token in Redis without the downstream system validating it provides **no fencing effect**. Redis failover and durability must also be considered if the fencing sequence lives there.

### 14.4. Does Redlock Replace Unique Constraints?

Some systems use distributed lock algorithms like Redlock. Regardless of lock algorithm, it does not turn HTTP side effects, database commits, and payment gateways into one atomic transaction. For "creating exactly one order," unique constraints and durable operation IDs at the authoritative source are generally required.

## 15. Extending the PROCESSING Lease Safely

A business operation may run longer than expected, such as waiting on a payment provider. Setting a fixed multi-hour TTL leaves retries stuck if a worker crashes; making the TTL too short risks a second owner entering.

One strategy is a **heartbeat** extending the lease while the worker is alive and still owns it.

### 15.1. Only the Owner May Extend

With immutable PROCESSING JSON, you can use Lua:

~~~lua
-- KEYS[1]: idempotency key
-- ARGV[1]: PROCESSING JSON claimed by owner
-- ARGV[2]: new lease, milliseconds

if redis.call('GET', KEYS[1]) ~= ARGV[1] then
    return 0
end
return redis.call('PEXPIRE', KEYS[1], tonumber(ARGV[2]))
~~~

If the current value was modified by another worker or transitioned to SUCCEEDED, the script does not extend it. If a heartbeat times out without a reply, do not assume ownership remains intact.

### 15.2. Lease Extension Is Not Enough for Exactly-Once

- The JVM can pause for a long time due to GC.
- Network partitions can stop heartbeats from reaching Redis.
- Redis failover can change the visible state.
- A worker unaware its lease was lost can still send side effects to the database.
- Another worker can claim after TTL expires.

Therefore, lease extension mainly reduces concurrent work. **The business source must still check idempotency/fencing.**

### 15.3. Crash Recovery Strategy

Persist durable operation status in the DB. When encountering a Redis PROCESSING state lasting too long, a worker/reconciler checks:

1. Does the operation exist in the DB ledger?
2. Is there already a corresponding order/payment result?
3. If succeeded, restore SUCCEEDED and replay the response.
4. If actively being processed by another worker, do not re-execute.
5. If deterministically failed prior to side effects, allow retry per policy.
6. If outcome is ambiguous, query the external provider or route into a reconciliation workflow.

Do not simply wait for the Redis key to expire and blindly create a new operation.

## 16. Caching Return Results: Store Full Response or Store Resource ID?

### 16.1. Store Full Response

~~~json
{
  "state": "SUCCEEDED",
  "httpStatus": 201,
  "responseBody": "{\"orderId\":\"o-101\",\"status\":\"CREATED\"}"
}
~~~

Pros:

- Retries can return the exact initial response.
- No extra database query needed.
- Preserves `201` and `Location` semantics per contract.

Cons:

- Uses RAM if responses are large.
- May store sensitive data.
- Responses might contain timestamps or fields that change later.
- Response schemas can become unreadable across code upgrades if serialized via Java class metadata.
- Requires a safe policy for retaining/updating headers.

### 16.2. Store Business Result ID

~~~json
{
  "state": "SUCCEEDED",
  "resourceId": "o-101",
  "httpStatus": 201
}
~~~

Pros:

- Smaller Redis entries.
- Can read the current version from the database to construct the response.
- Avoids storing unnecessary copies of sensitive data.

Cons:

- Replayed responses can **differ in body from the first call** if data changed.
- Must query the source to replay.
- Requires contract clarity on "same business outcome" vs "exact same HTTP response."

For APIs requiring **exact** response replay, store safe status/body/headers. For APIs only requiring no duplicate resource creation, storing the resource ID in a durable ledger and reconstructing the response can be a sound choice.

### 16.3. Which Errors Should Be Stored?

These can be categorized as follows:

| Outcome Type | Store as Terminal Result? | Reason |
|---|---|---|
| Order created successfully | Yes | Ensures retries return the same order |
| Business validation failed before side effects | Policy-dependent | Can return the same error, or let client fix request with a new key |
| `409` due to key reused with different body | Do not overwrite original record | Preserves the original key's contract |
| Transient `503` from Redis/database errors | Typically not finalized | Needs to permit recovery without repeating unknown side effects |
| Payment provider returned a deterministic final outcome | Can store once verified | Enables replaying the final decision |
| Network timeout calling payment provider | Do not assume "payment did not occur" | Requires status reconciliation |

Do not write a catch-all like "on any exception SET FAILED and allow retry" if the operation could already have committed before the exception was thrown.

## 17. When Two Requests Hit Two Spring Boot Pods Concurrently

Suppose Pod A and Pod B both receive the same key `K`:

~~~mermaid
sequenceDiagram
    participant CA as Client request A
    participant A as Spring Pod A
    participant R as Redis
    participant B as Spring Pod B
    participant CB as Client request B
    participant DB as Database
    CA->>A: POST /orders K
    CB->>B: POST /orders K
    A->>R: SET K PROCESSING NX EX
    B->>R: SET K PROCESSING NX EX
    R-->>A: TRUE
    R-->>B: FALSE
    B->>R: GET K
    R-->>B: PROCESSING
    B-->>CB: In progress
    A->>DB: createOrGet(K)
    DB-->>A: order o-101
    A->>R: Lua CAS PROCESSING -> SUCCEEDED
    R-->>A: 1
    A-->>CA: 201 o-101
~~~

Because `SET ... NX EX` is a single Redis command, when one primary node handles requests, only one request claims the key at a time. This eliminates the `GET`-then-`SET` race.

However, Redis replication/failover and lease expiration can cause a previously confirmed claim to disappear after failover or TTL expiry. Therefore, do not treat this diagram as an absolute single-execution guarantee across all failure modes.

### 17.1. Request Already Completed When Client Retries

~~~text
Request A: claim -> create order o-101 -> store SUCCEEDED
Request B: claim=false -> GET SUCCEEDED -> replay o-101
~~~

Do not call `orders.createOrGet(...)` again in the replay branch when a result is already present, unless the contract deliberately re-verifies against the authoritative source.

### 17.2. Request Still Running Long

You can report:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/json

{"code":"REQUEST_IN_PROGRESS"}
~~~

Or design an async API:

~~~http
HTTP/1.1 202 Accepted
Location: /api/operations/op-101
~~~

If exposing a status endpoint, it must verify authorization and never leak another tenant's response.

## 18. Redis Cluster and Idempotency Keys

A single key:

~~~text
idem:v1:<hash>
~~~

is mapped by Redis Cluster to one hash slot. `SET NX`, `GET`, and Lua CAS reference **one key**, so they will not hit multi-key `CROSSSLOT` errors.

If the application creates separate keys:

~~~text
idem:lock:<hash>
idem:result:<hash>
idem:metadata:<hash>
~~~

and needs to update multiple keys atomically in one script, they must share **the same hash tag**:

~~~text
idem:{op-101}:lock
idem:{op-101}:result
idem:{op-101}:metadata
~~~

However, tags can concentrate load. Usually, keeping **one compact Redis key holding state/result** is best when feasible, reducing command count and cross-key atomicity needs.

### 18.1. Why Not Use One Global Tag?

Avoid naming keys like:

~~~text
idem:{all}:request-1
idem:{all}:request-2
idem:{all}:request-3
~~~

All keys with tag `all` map to a single hash slot and can create a hot shard. Hash tags should scope to the smallest operation/aggregate that actually needs co-location, never system-wide.

### 18.2. Lua CAS and Cluster Failover

Lua CAS only enforces atomic transitions **on the primary node currently owning that key**. There is no distributed transaction with the database, and no guarantee under all configurations that a just-confirmed record replicated durably to a replica before failover.

If business logic demands strong durability, Redis should only act as an acceleration layer while authoritative state lives in an appropriately durable store.

## 19. Redis Expiration, Eviction, and Memory Management

A system receiving millions of new Idempotency-Keys daily can accumulate a huge number of Redis keys.

### 19.1. Memory Estimation

Example:

~~~text
Rate:              100 requests/second
Result retention:  24 hours
Estimated keys:    100 × 86,400 = 8,640,000 keys
~~~

If each entry holds a few hundred bytes of payload plus key/object/allocator overhead, total memory can be substantial. Never take raw JSON string length as actual RAM usage. Benchmark and measure Redis `used_memory` and memory fragmentation.

Options:

- Align TTL to the client retry and reconciliation window.
- Store the result ID instead of the full HTTP body when the contract permits.
- Never place raw request bodies or PII into keys.
- Cap Redis retention and keep durable outcomes in the DB.
- Use clear namespaces and versions.
- Monitor memory, hit/miss rates, and eviction.

### 19.2. Eviction Can Break the Idempotency Window

Suppose `SUCCEEDED` has a 24-hour TTL. If Redis runs `allkeys-lru` and runs low on RAM, an entry can be **evicted after 5 minutes**. A retry at minute 6 sees the key missing and acquires a new claim.

Therefore:

> **A 24-hour TTL does not mean Redis guarantees keeping an idempotency record for 24 hours.**

If Redis is the only deduplication layer for sensitive operations, eviction or failover data loss can violate guarantees. You need a durable ledger or memory/eviction policies matching business reliability—and even `noeviction` causes writes to fail when RAM fills up.

### 19.3. Useful Redis Metrics

~~~bash
redis-cli INFO memory
redis-cli INFO stats
redis-cli INFO keyspace
redis-cli CONFIG GET maxmemory
redis-cli CONFIG GET maxmemory-policy
~~~

Some managed Redis offerings restrict `CONFIG GET`; use the control plane or monitoring dashboards instead.

Watch especially for:

- `evicted_keys`.
- `expired_keys`.
- `used_memory`.
- Error rates on `SET NX`/Lua/GET.
- Timeouts and reconnects.
- Claim contention and reprocessing counts.

Do not run `KEYS idem:*` repeatedly in large production environments for statistics; use application metrics, Redis monitoring, and controlled `SCAN`.

## 20. Monitoring and Measuring Idempotency Behavior

Emit application-level metrics:

| Metric | Meaning |
|---|---|
| `idempotency_claim_total{result="acquired"}` | Number of new operations started |
| `idempotency_claim_total{result="existing"}` | Number of times key already existed |
| `idempotency_replay_total` | Number of stored responses replayed |
| `idempotency_inflight_conflict_total` | Duplicate requests received while processing |
| `idempotency_payload_conflict_total` | Keys reused with a different payload |
| `idempotency_cas_failed_total` | Completion where owner/state no longer matched |
| `idempotency_reconcile_total` | Operations requiring reconciliation |
| `idempotency_store_error_total` | Redis errors or serialization errors |
| `idempotency_processing_duration` | Time from claim to business outcome |
| `idempotency_response_size_bytes` | Size of cached result payload |

Do not place raw Idempotency-Keys, request hashes, or high-cardinality user IDs in metric labels. You can log a hashed or truncated identifier for troubleshooting while upholding data protection policies.

### 20.1. Structured Logs

A sensible log entry:

~~~json
{
  "operation": "POST:/api/orders:v1",
  "state": "SUCCEEDED",
  "redisKeySuffix": "a5f...e90",
  "businessResourceId": "o-101",
  "event": "IDEMPOTENCY_COMPLETED"
}
~~~

Never log full payment details, card data, or access tokens. Logs should show which operation was claimed, replayed, or conflicted and correlate back to source transactions.

### 20.2. Alert Signals

- Spikes in `CAS failed`: lease may be too short, Redis failover occurred, or ownership was lost.
- Prolonged `PROCESSING`: slow business service or crashed workflow.
- Rising payload conflicts: clients misusing keys.
- Rising evictions: TTL is no longer a reliable retention bound.
- Rising Redis errors: risk of bad fail-open or blocked claims.
- Rising database unique constraint conflicts: requests bypassing Redis gate or retrying past TTL.
- Very high replay rates: client retry storms or network issues.

## 21. Testing: Verifying Both Concurrency and Failure Modes

### 21.1. Minimum Test Suite

| Scenario | Expected Outcome |
|---|---|
| New request | Claim succeeds, creates one order, stores SUCCEEDED |
| Retry same key/body after completion | Does not create another order, returns same orderId |
| Two concurrent requests with same key/body | Only one claims initially; the other gets processing/replay |
| Same key with different body | `409`, does not overwrite original record |
| Same body with new key | Allows creating a new operation |
| Same key across two tenants | Isolated by scope |
| Redis GET returns null right after claim=false | Does not run business logic blindly |
| Worker crashes after claim, before side effect | Lease expiry or recovery permits safe retry |
| Crash after DB commit, before Redis SUCCEEDED | Durable ledger prevents creating a second order |
| Lease expires while old worker is running | Redis CAS from old owner fails; DB still protects side effect |
| Redis evicts SUCCEEDED before TTL | Durable ledger still prevents duplicates |
| Redis outage | Fail-closed or fall back to durable ledger per policy; no duplicates |
| Retry after payment provider timeout | Query outcome before resending if provider lacks idempotency |

### 21.2. Example Duplicate Response Check

Suppose initial call:

~~~http
POST /api/orders
Idempotency-Key: 5ab802da-df68-414f-959c-ff41bbfd8f87
Content-Type: application/json

{"sku":"desk-01","quantity":2}
~~~

Server returns:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json

{"orderId":"o-101","status":"CREATED"}
~~~

Second call, **same key and same request**:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json

{"orderId":"o-101","status":"CREATED"}
~~~

No `o-102` appears in the database.

If same key with `quantity=3`:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/json

{"code":"IDEMPOTENCY_KEY_REUSED"}
~~~

### 21.3. Multi-Worker Concurrency Testing

An integration test can launch multiple concurrent futures/request threads submitting the same key and assert **only one order ID** exists once all requests complete or replay. Checking only how many times Redis `SET NX` returned TRUE is insufficient: verify the durable side effect at the source too.

With Redis Cluster, test failover/connection interruption in staging to assess claim/result loss risks. Do not simulate "network success" with mocks and treat that as durability proof.

### 21.4. TTL Testing

A test can create PROCESSING with a short TTL, observe `PTTL`, and verify CAS refuses to transition state once the owner token no longer matches. However, this test **does not** prove end-to-end idempotency if the operation has external side effects. Corresponding ledger/transaction and recovery tests are required.

## 22. Practical Application Patterns

### 22.1. Creating Orders via REST API

**Context:** clients retry on timeouts.

**Recommended structure:**

- Client generates an Idempotency-Key per checkout confirmation click.
- Redis `SET NX EX` curbs concurrent execution.
- Database enforces a unique operation key and order creation inside an appropriate transaction.
- Redis caches the response for fast replay.
- Retries after Redis loses a record still check the database before creating anything new.

Redis serves as **fast-path coordination + response cache**; the database is the **authoritative duplicate arbiter**.

### 22.2. Payment Webhooks

**Context:** payment providers re-deliver the same event multiple times and may deliver events out of order.

**Recommended structure:**

- Extract verified `providerEventId` and `paymentId` from the webhook.
- Use a durable inbox unique on provider + event ID.
- Check payment state and version so stale events do not overwrite newer states.
- Redis `SET NX` can cut duplicate work.
- Mark handled only after internal side effects complete.
- Never just return `200` and ignore retries if the first attempt did not commit.

Webhook signature verification and idempotency are distinct controls: validly signed events can still be delivered repeatedly.

### 22.3. Event-Driven Email Delivery

**Context:** a message may be reprocessed after a crash.

If sending email is a side effect whose provider lacks idempotency:

1. Persist the business event ID and status in a durable store.
2. Claim processing.
3. Send email with a provider request ID if available.
4. Record the provider message ID and status.
5. On ambiguous outcomes, query the provider or define an acceptable duplicate-risk policy.

A Redis set key reduces concurrency, but does not give the email provider exactly-once delivery.

### 22.4. Generating Discount Codes

**Context:** multiple clicks generate valuable promo codes.

You can use a Redis key `idem:coupon:<operationId>` as a claim, but code issuance must be protected by unique constraints or atomic reservation at the issuing source. If codes have TTLs and limited quantities, separate the **coupon TTL** from the **idempotency record TTL**.

### 22.5. Redis Streams Consumers

**Context:** a handler processes a Stream entry and crashes before `XACK`.

~~~text
XREADGROUP -> record eventId=e-101
DB update completed
Crash before XACK
Record is reclaimed -> handler runs again
~~~

The consumer needs durable idempotency keyed by `eventId` or business aggregate/version. Redis `XACK` only acknowledges processing within the consumer group; it forms no automatic transaction with the database.

A `seen:e-101` key in Redis can reduce duplicate compute, yet cannot replace a durable inbox when processing must be accurate and lossless.

### 22.6. Scheduled Tasks Across Multiple Pods

**Context:** a sync job runs every minute and two pods may trigger simultaneously.

A Redis lease can help keep only one pod running the job within the expected window. However, over long jobs, GC pauses, or Redis failovers, two pods can run concurrently. For critical batch updates, use job-run IDs, durable checkpoints, idempotent updates, and fencing/versioning so stale results do not overwrite newer ones.

Do not confuse **distributed scheduler locking** with **request idempotency**: they are related but have different scopes and lifecycles.

## 23. Common Mistakes

### 23.1. GET Then SET to Check a Key

Two parallel requests can both read null and both execute.

**Replace with:** `SET key value NX EX ...` or an atomic Lua claim script.

### 23.2. SETNX Then EXPIRE in Two Commands

A crash in between can leave a key without a TTL.

**Replace with:** `setIfAbsent(key, value, Duration)` corresponding to `SET NX EX`.

### 23.3. Writing the Key Only After Processing Finishes

Does not stop two concurrent requests from both executing side effects.

**Replace with:** claim PROCESSING first, then CAS to SUCCEEDED.

### 23.4. Storing Only "Key Seen" Before Processing

If a worker crashes after marking yet before processing, retries are skipped and work is lost.

**Replace with:** distinguish PROCESSING/SUCCEEDED and provide recovery paths.

### 23.5. Deleting the Claim in Every Catch Block

If the business commit succeeded and the response was lost, deleting the claim lets retries re-execute side effects.

**Replace with:** determine outcome at the source or keep a state requiring reconciliation; do not delete blindly.

### 23.6. Using Too Short a TTL

The worker is still running when the lease expires and another worker claims it. Both can reach the side effect.

**Replace with:** adequate lease, CAS-protected heartbeat, and durable idempotency/fencing at the source.

### 23.7. Using Too Long a TTL Without Recovery

When a worker crashes, retries remain stuck in PROCESSING for a long time.

**Replace with:** separate lease TTL from completed retention, plus operation status/reconciler.

### 23.8. Thinking SET NX Guarantees Exactly-Once

Redis can expire/evict/failover; side effects can commit before SUCCEEDED is saved. **`SET NX` is only one part of the protocol.**

### 23.9. Relying Solely on Redis for Money Transfers

A Redis gate does not replace ledger transactions and unique constraints, especially with external payment providers.

**Replace with:** durable ledger + transaction/outbox/provider idempotency at business boundaries.

### 23.10. Replaying on Same Key with Different Body

This can return another request's order for a new operation that accidentally reused the key.

**Replace with:** request fingerprint and HTTP 409.

### 23.11. Using Body Hash as the Sole Idempotency Key

Two distinct intents with identical bodies can be wrongly blocked.

**Replace with:** client-issued key per logical operation; body hash only verifies reuse.

### 23.12. Failing to Scope by Tenant and Operation

Tenant A and B can collide on the same key; worse, one tenant could view another's response if authorization is missing.

**Replace with:** scope using authenticated identity, operation route, and version.

### 23.13. Overwriting SUCCEEDED with PROCESSING

A retry must not reset a completed state.

**Replace with:** `SET NX` for claims, owner-checked CAS to finalize, and never use unconditional SET.

### 23.14. Returning "Success" Before Side Effects Are Confirmed

Acquiring a Redis lock does not mean the order/payment committed. Return success only when the source confirms the outcome.

### 23.15. Ignoring Redis Eviction

Keys with TTLs can still be evicted early, letting duplicate requests slip through.

**Replace with:** sizing, monitoring, durable ledger, and deliberate eviction policies.

### 23.16. Using `@Cacheable` Instead of an Idempotency Gate

Spring Cache `@Cacheable` optimizes method results; under concurrent cache misses it can still invoke methods multiple times, and caching provides no durable transaction with side effects.

**Replace with:** an explicitly designed claim/ledger/response-replay mechanism. `@Cacheable(sync=true)` does not guarantee distributed exactly-once across pods.

## 24. Frequently Asked Questions

**Q1. Is an idempotency key the same as a Redis key?**

No. The client key identifies a logical request; the Redis key should be a server-generated namespaced/scoped representation. Both are distinct from the business resource ID.

**Q2. Can the fingerprint be omitted?**

Without a fingerprint, the same client key could be reused with a different body while the server replays the old result. For APIs with parameters affecting side effects, fingerprints are strongly recommended.

**Q3. Why must SET NX be used?**

Because "create only if key does not exist" must be atomic. Separate GET then SET has a race condition.

**Q4. Why attach TTL immediately at SET NX?**

To avoid permanent claims if a worker crashes before EXPIRE. Use `SET key value NX EX seconds` or `setIfAbsent(key, value, Duration)`.

**Q5. Should the full HTTP response be stored in Redis?**

Yes, when exact replay is required. Protect sensitive data and watch memory usage. If only avoiding duplicate resource creation matters, store the resource ID and rebuild the response per contract.

**Q6. Should the key be deleted after successful processing?**

Usually **no** immediately, if a window remains where clients may retry. Transition to SUCCEEDED with a retention TTL and replay when the key is reused.

**Q7. If an operation fails, should PROCESSING be deleted so the client can retry immediately?**

Only when certain no side effect occurred or retries are protected by durable idempotency. If the outcome is ambiguous, reconcile instead of deleting blindly.

**Q8. Does Redis SET NX block two pods concurrently?**

Provided one primary handles the key and the lease has not expired, the atomic claim yields a single winner. It does not guarantee a unique side effect across lease expiry, failover, or external systems.

**Q9. Are retries after the result TTL protected?**

By the Redis record alone, no. Define a retry window or use a durable ledger for longer guarantees.

**Q10. Is hashing the raw request body enough?**

Not always. JSON differing only in whitespace or key order shares semantics. Use canonicalization/normalized DTOs and an explicit contract version.

**Q11. What does Lua CAS solve?**

It prevents a worker that no longer owns the Redis state from overwriting the current record. It does not undo committed database side effects.

**Q12. Is a distributed lock library like Redisson required?**

Depends on architecture. A library can help manage leases/locks, but **idempotency semantics, response replay, and durable side effects** must still be designed by the application.

**Q13. Why pass a key downstream to the payment provider?**

Because internal Redis and databases cannot know whether an external payment charged when a response is lost. If the provider supports key-based idempotency, it avoids duplicate processing right at the side-effect boundary.

**Q14. If a webhook already has an eventId, is an Idempotency-Key header still needed?**

Not necessarily. A verified provider event ID can serve as the logical dedupe key, scoped by provider/tenant/event type and paired with out-of-order event handling.

**Q15. HTTP 409 or 202 for PROCESSING?**

Both appear in API designs: `409` indicates a conflict with an in-flight operation; `202` indicates the request was accepted and clients may poll status. Publish a consistent contract.

**Q16. Do we need both Redis and a database ledger?**

Not required for every use case. For best-effort notifications, Redis may suffice. When duplicate resources or charges must be prevented even across Redis failovers or key evictions, a durable ledger at the business source is essential.

## 25. Pre-Production Design Checklist

1. Is the **logical operation** clearly defined? Which intent does a shared request key represent?
2. Is the **client key** stable across retries, high-entropy, and bounded in length?
3. Does **scoping** include the authenticated tenant/user and operation name?
4. Does the **fingerprint** cover all fields affecting side effects?
5. Does **claiming** use a single atomic `SET NX EX` command?
6. Does **state** distinguish PROCESSING, SUCCEEDED, and ambiguous outcomes?
7. Is the **owner token** checked on finalize/extend/release?
8. Is the **completed response** stored/replayed according to contract?
9. Does **PROCESSING TTL** account for p99 latency, GC pauses, and workflow timeouts?
10. Does **completed TTL** cover the published retry window?
11. Could **eviction/failover** drop idempotency records? If so, how are side effects protected?
12. Does the **database/source of truth** enforce a unique constraint or idempotent operation ID?
13. Does the **external provider** offer idempotency or status-query APIs for timeouts?
14. Do **Redis errors** fail closed or fall back to the durable ledger; could anything run side effects when claim state is unclear?
15. Can **recovery** reconcile operations after crashes or lease expirations?
16. Do **multi-instance concurrency tests** verify database outcomes rather than only Redis SET NX?
17. Does **security** prevent tenant collisions, key guessing, response disclosure, and PII in Redis/logs?
18. Do **metrics** track claims, replays, conflicts, CAS failures, and reconciliations?
19. Are **key/value schemas and versions** compatible across deployments?
20. Is **ownership** of business outcomes, retry policies, and idempotency windows documented in the API contract?

## 26. Summary

**Duplicate request prevention is more than placing a Redis lock.** A practical pattern includes:

1. Client sends a stable `Idempotency-Key` for the same logical operation.
2. Server scopes the key by authenticated tenant and operation, and computes a request fingerprint.
3. Redis `SET NX EX` atomically claims the PROCESSING state.
4. Duplicate requests receive an in-progress status or a **replayed** SUCCEEDED result.
5. The worker executes business logic with **idempotency at the side-effect source** when strong reliability is needed.
6. The worker uses owner-checked Lua CAS to transition Redis state to SUCCEEDED with a result retention TTL.
7. When outcomes are ambiguous, leases expire, failovers occur, or Redis records disappear, the application **reconciles with the authoritative source** instead of blindly retrying.
8. Monitor memory, TTL/eviction, conflicts, retries, and reconciliation cases.

Redis excels at reducing duplicate work and serving fast response replays across multiple Spring Boot instances. Yet **end-to-end idempotency must be guarded right where side effects actually occur**, especially for order creation, money transfers, payments, webhooks, and durable data transactions.

## References

- Redis — [SET command](https://redis.io/docs/latest/commands/set/): `NX`, `EX`/`PX`, and conditional key creation.
- Redis — [EXPIRE command](https://redis.io/docs/latest/commands/expire/): TTL and Redis key lifecycle.
- Redis — [PSETEX command](https://redis.io/docs/latest/commands/psetex/): storing values with millisecond TTLs.
- Redis — [Scripting with Lua](https://redis.io/docs/latest/develop/programmability/eval-intro/): atomic server-side scripts and limitations.
- Redis — [Distributed locks](https://redis.io/docs/latest/develop/clients/patterns/distributed-locks/): owner tokens, leases, compare-and-delete, and caveats.
- Redis — [Key eviction](https://redis.io/docs/latest/reference/eviction/): `maxmemory` and risks of evicting keys before TTL.
- Spring Data Redis — [RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html): StringRedisTemplate, serializers, and Redis operations.
- Spring Data Redis — [Redis Scripting](https://docs.spring.io/spring-data/redis/reference/redis/scripting.html): `RedisScript`/`DefaultRedisScript` and Lua execution.
- Spring Data Redis — [Redis Transactions](https://docs.spring.io/spring-data/redis/reference/redis/transactions.html): MULTI/EXEC limits and differences from database transactions.
