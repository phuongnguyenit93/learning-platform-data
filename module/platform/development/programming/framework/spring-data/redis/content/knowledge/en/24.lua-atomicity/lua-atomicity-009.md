# Packaging, Testing, and Versioning Lua Scripts in Spring Data Redis

## 1. Lesson Objectives

When a business operation needs to **read state, check conditions, and update Redis data as a single unit without other commands interleaving**, a Lua script is a practical tool. Examples include reserving stock, capping promo-code usage, checking and releasing token-owned locks, or updating multiple related fields.

Writing a few lines of Lua is only the first step. For scripts to survive in a long-lived Spring Boot project, we must solve three additional challenges:

1. **Packaging:** where to store scripts, how to invoke them via Spring Data Redis, and how to specify `KEYS`, `ARGV`, and return values cleanly.
2. **Testing:** verifying behavior against real Redis, testing error cases, retries, and concurrency, while understanding the exact boundaries of atomicity.
3. **Versioning:** keeping Java code and scripts deployed in sync, supporting rolling deployments, handling schema changes, and coping with Redis script cache evictions.

This lesson builds one end-to-end example: **reserving product stock quantities with Lua and Spring Data Redis**. The goal is learning how to integrate scripts into a project cleanly and controllably, rather than pasting Lua into Java strings with inconsistent conventions across call sites.

## 2. Within What Scope Does Lua Provide Atomicity?

A single Redis command is processed according to that command's semantics. Lua scripts let you combine multiple operations into one `EVAL` or `EVALSHA` call. While a script executes on Redis, commands from other clients cannot interleave between operations inside the script.

Error-prone flow when sending sequential commands from Java:

~~~text
Client A                          Client B
--------                          --------
GET stock -> 5                    GET stock -> 5
sees 4 available                  sees 4 available
DECRBY stock 4                    DECRBY stock 4

Result: stock can drop to -3, and both clients believe they reserved successfully.
~~~

With Lua:

~~~text
Client A                  Redis                    Client B
--------                  -----                    --------
EVAL reserve.lua --------> reads stock = 5
                          checks 4 available
                          updates stock = 1
                          returns success
                                                   EVAL reserve.lua -->
                          reads stock = 1
                          sees fewer than 4
                          returns insufficient stock
~~~

Both executions are serialized by Redis. Client B observes the state produced after Client A's operation.

**However, atomicity here does not mean every failure rolls back.** If a script completes a write command and then hits a runtime error on the next command, prior changes can remain. Redis Lua guarantees other commands do not interleave mid-script—**it does not provide automatic rollback like an SQL transaction**.

Therefore, well-designed scripts should:

- Validate inputs and checkable preconditions **before writing**.
- Minimize write steps and limit operations that could fail after the first write.
- Stay short, avoiding unbounded loops.
- Return explicit result codes and plan business-level retry handling.
- Never attempt HTTP, email, or external non-Redis calls from inside a script.

## 3. Directory Conventions in a Spring Boot Project

Instead of embedding long Lua snippets in Java string literals, store them as **Git-tracked resources**:

~~~text
inventory-service/
├── pom.xml or build.gradle
├── src/
│   ├── main/
│   │   ├── java/com/example/inventory/
│   │   │   ├── config/
│   │   │   │   └── RedisScriptConfig.java
│   │   │   ├── service/
│   │   │   │   └── InventoryReservationService.java
│   │   │   └── model/
│   │   │       └── ReservationOutcome.java
│   │   └── resources/
│   │       └── redis/
│   │           └── scripts/
│   │               ├── reserve-stock-v1.lua
│   │               └── README.md
│   └── test/
│       └── java/com/example/inventory/
│           └── InventoryReservationIntegrationTest.java
~~~

Benefits of placing files in `src/main/resources`:

- Spring loads them via `ClassPathResource`, even when packaged as an executable JAR.
- Lua files are reviewed, diffed, and versioned alongside Java code.
- Each build artifact bundles the exact Java code and Lua scripts that Java calls.
- Integration and contract tests sit right next to the consuming code.
- No reliance on absolute server paths or process working directories.

Example resource path:

~~~text
classpath:redis/scripts/reserve-stock-v1.lua
~~~

Never use `new File("src/main/resources/...")` in production. That path only exists in the development source layout and will likely fail inside a JAR or container.

### Why Does the Filename Have a v1 Suffix?

The name `reserve-stock-v1.lua` expresses the **script contract version**, covering how `KEYS`, `ARGV`, Redis data structures, and result codes are interpreted. When changing a contract in a way that affects callers or shared data, create `v2` rather than silently altering `v1` while multiple app versions call it.

Even for minor bug fixes that preserve the contract, remember that **changing a single byte in source produces a different script SHA**. Whether to bump the major contract version depends on your team's versioning rules, not merely SHA changes.

## 4. Designing the Contract Before Writing Lua

Consider a per-SKU inventory reservation system. We choose **one Redis Hash per SKU**:

~~~text
Key: inventory:{sku-42}:state

Hash fields:
  available         -> "10"
  reservation:r-101 -> "3"
  reservation:r-102 -> "2"
~~~

In this model:

- `available` is the unreserved unit count.
- `reservation:<reservationId>` stores the quantity reserved for a unique request.
- Retrying with the **same reservationId and same quantity** returns "already applied earlier" without deducting stock again.
- Retrying with the **same reservationId but a different quantity** reports a conflict.
- One reservation updates `available` and the reservation field in **a single multi-field `HSET` command**.

Using a single Hash keeps the example to **one Redis key** and makes the main write **one Redis command**. Production systems still need reservation release flows, order statuses, cleanup policies for old reservations, and bounds on Hash field growth over time. Here we focus on packaging contracts and script testing.

### Contract v1

| Component | Value | Meaning |
| --- | --- | --- |
| `KEYS[1]` | `inventory:{sku-42}:state` | Redis Hash holding SKU state |
| `ARGV[1]` | `reservationId` | Reservation request ID, used for idempotency |
| `ARGV[2]` | `quantity` | Positive integer quantity to reserve, passed as string |
| `return 1` | Newly created | Quantity subtracted and reservation recorded |
| `return 2` | Identical retry | Reservation already exists with the same quantity |
| `return 0` | Insufficient stock | Nothing written |
| `return -1` | Missing inventory | Hash or `available` field not initialized |
| `return -2` | Idempotency conflict | Reservation ID already used for another quantity |
| Redis error reply | Invalid data/arguments | Caller must treat as error, not out-of-stock |

In Spring Data Redis, `KEYS` holds **Redis key names**, while `ARGV` holds **non-key arguments**. Document the positional contract clearly: swapping `ARGV[1]` and `ARGV[2]` can corrupt logic silently while still compiling.

### Required Data Structure Stability

Expected setup:

~~~redis
HSET inventory:{sku-42}:state available 10
HGET inventory:{sku-42}:state available
~~~

If another caller accidentally runs `SET inventory:{sku-42}:state "10"`, the key becomes a Redis String instead of a Hash. `HGET` will fail with `WRONGTYPE`. Every namespace needs **one agreed data convention** and clear ownership.

## 5. Complete Lua File: reserve-stock-v1.lua

Place the following content in `src/main/resources/redis/scripts/reserve-stock-v1.lua`:

~~~lua
-- reserve-stock-v1.lua
--
-- Contract:
--   KEYS[1]: Redis Hash storing inventory for one SKU
--   ARGV[1]: reservationId (non-empty)
--   ARGV[2]: quantity (integer from 1 to 1,000)
--
-- Return:
--    1  = new reservation succeeded
--    2  = valid duplicate request, stock not deducted again
--    0  = insufficient stock
--   -1  = inventory not initialized
--   -2  = same reservationId with different quantity
--   error reply = invalid input or invalid data state

if #KEYS ~= 1 or #ARGV ~= 2 then
    return redis.error_reply("ERR_BAD_ARGUMENT_COUNT")
end

local inventoryKey = KEYS[1]
local reservationId = ARGV[1]
local rawQuantity = ARGV[2]

if not reservationId or reservationId == "" then
    return redis.error_reply("ERR_EMPTY_RESERVATION_ID")
end

-- Input limits prevent floating-point inaccuracy and oversized operations.
local quantity = tonumber(rawQuantity)
if not quantity
    or quantity ~= math.floor(quantity)
    or quantity < 1
    or quantity > 1000 then
    return redis.error_reply("ERR_INVALID_QUANTITY")
end

-- HGET returns false if the Hash field does not exist.
local currentRaw = redis.call("HGET", inventoryKey, "available")
if not currentRaw then
    return -1
end

local available = tonumber(currentRaw)
if not available
    or available ~= math.floor(available)
    or available < 0
    or available > 1000000000 then
    return redis.error_reply("ERR_INVALID_STOCK")
end

local reservationField = "reservation:" .. reservationId
local existingRaw = redis.call("HGET", inventoryKey, reservationField)

if existingRaw then
    if tonumber(existingRaw) == quantity then
        return 2
    end
    return -2
end

if available < quantity then
    return 0
end

local remaining = available - quantity

-- Single write command after validating all preconditions.
redis.call(
    "HSET",
    inventoryKey,
    "available", string.format("%.0f", remaining),
    reservationField, string.format("%.0f", quantity)
)

return 1
~~~

The script uses Lua supported by Redis (Lua 5.1 in traditional Redis scripting). Array indices `KEYS` and `ARGV` start at **1**.

### Why Use One Multi-Field HSET Command?

An error-prone variant is:

~~~lua
redis.call("HINCRBY", KEYS[1], "available", -quantity)
redis.call("HSET", KEYS[1], reservationField, quantity)
~~~

If the second command fails, the stock subtraction in the first command remains applied; **Lua scripts do not automatically roll back**. The v1 design checks preconditions upfront and uses a single `HSET` to update both Hash fields together.

In real systems, also account for full operation failures, external persistence, Hash size limits, and release/confirm flows. A reservation script alone does not solve the whole order lifecycle.

### Why Not Call TIME Inside the Script?

This example does not need time. When logic requires a deadline, pass the timestamp explicitly via `ARGV` per contract and verify time-source consistency. That also keeps tests deterministic.

Across Redis versions, replication rules and certain command restrictions can vary. Avoid randomness, time-dependent behavior, or restricted commands inside scripts unless you understand the target Redis version thoroughly.

## 6. Calling the Script from Java Using DefaultRedisScript

Spring Data Redis offers `DefaultRedisScript<T>` to specify the script source and result type. Declare the bean once and reuse it:

~~~java
package com.example.inventory.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.data.redis.core.script.RedisScript;

@Configuration
public class RedisScriptConfig {

    @Bean
    public RedisScript<Long> reserveStockV1Script() {
        DefaultRedisScript<Long> script = new DefaultRedisScript<>();
        script.setLocation(
            new ClassPathResource(
                "redis/scripts/reserve-stock-v1.lua"
            )
        );
        script.setResultType(Long.class);
        return script;
    }
}
~~~

`Long.class` fits because Lua `return 1`, `return 0`, or `return -2` produces Redis integer replies. Never specify `String.class` for integer codes expecting Spring to convert them into business semantics automatically.

Keep script beans in standard singleton scope rather than creating `DefaultRedisScript` and re-reading resources manually on every request. Spring Data Redis computes and uses the script's SHA1 automatically during execution.

### Spring Service Using StringRedisTemplate

~~~java
package com.example.inventory.service;

import java.util.List;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.RedisScript;
import org.springframework.stereotype.Service;

@Service
public class InventoryReservationService {

    private final StringRedisTemplate redis;
    private final RedisScript<Long> reserveStockV1;

    public InventoryReservationService(
            StringRedisTemplate redis,
            RedisScript<Long> reserveStockV1Script) {
        this.redis = redis;
        this.reserveStockV1 = reserveStockV1Script;
    }

    public ReservationOutcome reserve(
            String sku,
            String reservationId,
            int quantity) {

        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku is required");
        }
        if (reservationId == null || reservationId.isBlank()) {
            throw new IllegalArgumentException("reservationId is required");
        }

        // Hash tag {sku} keeps keys in the same slot for Cluster scaling.
        String key = "inventory:{" + sku + "}:state";

        Long code = redis.execute(
            reserveStockV1,
            List.of(key),
            reservationId,
            Integer.toString(quantity)
        );

        if (code == null) {
            throw new IllegalStateException(
                "Lua script returned no result"
            );
        }

        return switch (code.intValue()) {
            case 1 -> ReservationOutcome.CREATED;
            case 2 -> ReservationOutcome.ALREADY_RESERVED;
            case 0 -> ReservationOutcome.INSUFFICIENT_STOCK;
            case -1 -> ReservationOutcome.INVENTORY_MISSING;
            case -2 -> ReservationOutcome.IDEMPOTENCY_CONFLICT;
            default -> throw new IllegalStateException(
                "Unknown Lua result: " + code
            );
        };
    }

    public enum ReservationOutcome {
        CREATED,
        ALREADY_RESERVED,
        INSUFFICIENT_STOCK,
        INVENTORY_MISSING,
        IDEMPOTENCY_CONFLICT
    }
}
~~~

With `StringRedisTemplate`, String keys and arguments are serialized per template string conventions. Lua receives the strings in `KEYS` and `ARGV`, and Redis handles Hash updates internally.

Before calling, inventory data must be initialized:

~~~java
String key = "inventory:{sku-42}:state";

redis.opsForHash().put(key, "available", "10");

var result = reservationService.reserve("sku-42", "r-101", 3);
~~~

After a successful reservation:

~~~redis
HGET inventory:{sku-42}:state available
HGET inventory:{sku-42}:state reservation:r-101
~~~

Outputs are `"7"` and `"3"` respectively. Calling again with `r-101` and quantity 3 returns `ALREADY_RESERVED`, while available stock remains 7.

### Which Java Types Receive Replies?

| Lua return | Redis/Spring Data Redis | Recommended handling |
| --- | --- | --- |
| `return 1` | Integer reply, Java `Long` when configured with `Long.class` | Map to enum/result code |
| `return 0` | `Long(0)` | Insufficient stock |
| `return -2` | `Long(-2)` | Idempotency conflict |
| `return redis.error_reply(...)` | Redis error via exception | Catch and classify error |
| `return false` | May map to nil/null depending on contract | Avoid using for result codes in this example |
| `return {1, 2}` | Array reply | Requires matching `resultType` and mapping |

Keeping the v1 return contract as **a single integer** makes Java code far less ambiguous than returning a complex Lua table.

## 7. RedisScript, EVAL, and EVALSHA

At the Redis level, there are two traditional script execution commands:

~~~redis
EVAL "<Lua source>" 1 inventory:{sku-42}:state r-101 3
EVALSHA <sha1> 1 inventory:{sku-42}:state r-101 3
~~~

- `EVAL` sends the script source directly.
- `EVALSHA` sends the SHA1 of script content already known to Redis; if missing from cache, Redis replies `NOSCRIPT`.
- `SCRIPT LOAD` proactively loads a script into cache; `SCRIPT EXISTS` checks cache presence on the queried Redis server.
- `SCRIPT FLUSH` clears the server's script cache; the cache can also change on restarts, failovers, or Redis version eviction policies.

When using `RedisTemplate.execute(redisScript, keys, args...)`, Spring Data Redis defaults to **trying `EVALSHA` and falling back to `EVAL` when the script is not cached**. Thus, applications normally do not need to call `SCRIPT LOAD` before every run.

~~~text
Spring RedisScript
     |
     v
Compute/get SHA1 of Lua source
     |
     v
EVALSHA -------------------+
     |                     |
     | script present      | NOSCRIPT
     v                     v
Redis runs script        EVAL with full source
                               |
                               v
                         Redis runs script
~~~

**Never treat the script cache as durable storage.** The source of truth remains the resource file inside the application's deployable artifact. Whenever the cache is empty, the app must be able to resend the source.

### SHA Is Content Identity, Not Business Version

Suppose:

~~~text
reserve-stock-v1.lua (content A) -> SHA_A
reserve-stock-v1.lua (content B) -> SHA_B
~~~

Changing a single space or comment alters SHA1. Conversely, naming a file v2 does not make its contract different if its contents match v1.

Distinguish clearly:

- **SHA1:** uniquely identifies exact Lua bytes so Redis can look them up in the script cache.
- **Contract name/version (v1, v2):** application convention covering inputs, data schema, and result semantics.
- **Application version:** the Spring Boot build artifact containing Java callers and script resources.

These three serve different purposes and never substitute for one another.

## 8. KEYS and ARGV Rules in Redis Cluster

In Redis Cluster, all keys accessed by a script must follow key distribution rules; specifically, keys touched in one execution must belong to the **same hash slot**.

Two keys example:

~~~text
inventory:{sku-42}:state
inventory:{sku-42}:audit
~~~

Same hash tag `{sku-42}`, so same slot. Conversely:

~~~text
inventory:{sku-42}:state
inventory:{sku-99}:audit
~~~

normally map to different slots, and a script accessing both can be rejected in Cluster.

**Every Redis key accessed by a script must be declared via `KEYS` per contract.** Never sneak another key through `ARGV` or dynamically build Redis key names from undeclared values. In v1, `"reservation:" .. reservationId` is only a **field inside one Hash**, not a new Redis key.

These rules let Redis Cluster route commands properly, improve governance, and prevent `CROSSSLOT` errors.

### When Should You Avoid Grouping Multiple Keys in One Slot?

Hash tags are a data placement tool, not advice to place the entire app into one slot. If every SKU shared one tag, all keys would pile onto one node, causing severe load imbalance.

In our example:

~~~text
inventory:{sku-42}:state
inventory:{sku-99}:state
~~~

each SKU distributes independently; only keys that must update together share that specific SKU's tag.

## 9. Wrapping the Contract to Avoid Positional Parameter Mistakes

Scripts accept parameters by index. Over time, scattered direct calls like:

~~~java
redis.execute(script, List.of(key), "r-101", "3");
redis.execute(script, List.of(key), "r-102", "5");
~~~

invite bugs where maintainers swap arguments, pass wrong types, or invoke the wrong script version.

The solution is **a single service/wrapper** responsible for:

- Constructing keys using namespace and hash-tag conventions.
- Validating inputs in Java for fast feedback.
- Selecting the right script version.
- Passing `KEYS` and `ARGV` in exact order.
- Mapping numeric return codes to named enums or domain outcomes.
- Attaching script name and version to logs/metrics.
- Handling exceptions, retries, and timeouts per business rules.

Never expose `RedisScript<Long>` directly to controllers. Controllers should interact only with clean APIs such as `reservationService.reserve(sku, requestId, qty)`.

A brief contract note can live in the scripts folder:

~~~markdown
# reserve-stock-v1

- Keys: 1 Hash key, inventory:{sku}:state.
- ARGV[1]: reservationId.
- ARGV[2]: positive integer quantity, max 1000.
- Codes: 1 created, 2 already applied, 0 insufficient,
  -1 missing, -2 conflicting request.
- Failure: Redis error reply for malformed input/state.
- Data: fields available and reservation:<id>.
- Atomic write: one HSET updating both fields.
- Idempotency: reservationId scoped to inventory key.
- Compatibility: callers using v1 must keep this schema.
~~~

The sample above is simply documentation for the script—not a QA file, and not something extra you need to create on your own in this lesson.

## 10. Three-Tier Testing Strategy

Because Lua correctness depends on Redis behavior, testing should cover three tiers:

| Tier | Goal | Approach |
| --- | --- | --- |
| Contract and configuration checks | Resource file exists, result type and wiring are valid | Bean/service context tests |
| Integration tests against real Redis | Verify Lua syntax, Redis commands, reply types, and state | Local Redis / Testcontainers |
| Concurrency and operational tests | Multiple clients never oversell; retries, cache misses, and failovers behave safely | Bounded concurrency and system tests |

Mocking `StringRedisTemplate` is useful for checking Java mapping, yet **mocks never execute Lua**. A test verifying only "called `redis.execute` with `List.of(key)`" does not prove the script is right, does not prove atomicity, and cannot catch `WRONGTYPE` or `NOSCRIPT`.

### Why Prefer Real Redis in Tests?

Lua runs inside Redis with specific rules:

- `redis.call` and `redis.pcall` behave and error per Redis semantics.
- `KEYS` and `ARGV` arrive as serialized strings.
- `nil`/`false` and Lua tables convert to Redis replies per Redis scripting rules.
- Hash, String, Set, and TTL commands follow Redis semantics.
- Inter-client contention is observable only under concurrent calls.

Using a dedicated test Redis instance therefore gives far higher confidence than stubbing Redis behavior in Java.

## 11. Mandatory Test Cases for Script v1

Test matrix for the stock reservation example:

| Scenario | Initial data | Expected return | Post-state |
| --- | --- | --- | --- |
| Successful reservation | available=10, no r-101 | `1` | available=7, reservation:r-101=3 |
| Identical retry | r-101=3 exists | `2` | available stays 7 |
| Conflicting retry | r-101=3 exists, quantity=4 | `-2` | Unchanged |
| Insufficient stock | available=2, request 3 | `0` | Unchanged |
| Missing Hash | Key does not exist | `-1` | No new key created |
| quantity=0 | available=10 | Error | Unchanged |
| Negative/non-integer quantity | available=10 | Error | Unchanged |
| Non-numeric available | available="abc" | Error | Unchanged |
| Wrong Redis key type | Key is String | Redis `WRONGTYPE` | Unchanged |
| Two competing requests | available=1, two IDs each requesting 1 | Only one returns `1` | available=0 |
| Retry after timeout | Client unsure if first attempt succeeded | `1` or `2` depending on first run | Never deducted twice for one ID |
| Multiple SKUs | Two distinct keys | Independent outcomes | No cross-namespace writes |

This matrix verifies **core contract behavior**, including edge cases prone to failing in production.

### Timeout Scenarios Are Especially Critical

A client can time out after Redis **finished executing the script**, yet before receiving the response. The client then does not know whether the request succeeded:

~~~text
Spring ---> Redis runs reserve ---> stock subtracted, reservation written
   ^
   |
   +---- network times out before Java receives result
~~~

If the caller retries with a **new reservationId**, stock can be subtracted a second time. Retrying with the **same reservationId** lets v1 detect the recorded field and return `2` without subtracting again. That is why idempotency belongs in both the script contract and the caller, rather than relying solely on Redis atomic execution.

## 12. Integration Test Example with Testcontainers and JUnit 5

A standard setup runs a real Redis container and configures Spring to connect to the mapped random port. Dependencies typically include Spring Data Redis Starter, Spring Boot Test, Testcontainers, and JUnit Jupiter.

Illustrative example matching the application structure above:

~~~java
package com.example.inventory;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import com.example.inventory.service.InventoryReservationService;
import com.example.inventory.service.InventoryReservationService.ReservationOutcome;

@Testcontainers
@SpringBootTest
class InventoryReservationIntegrationTest {

    private static final String KEY = "inventory:{sku-42}:state";

    @Container
    static final GenericContainer<?> REDIS =
        new GenericContainer<>(DockerImageName.parse("redis:7.2"))
            .withExposedPorts(6379);

    @DynamicPropertySource
    static void configureRedis(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add(
            "spring.data.redis.port",
            () -> REDIS.getMappedPort(6379)
        );
    }

    @Autowired
    StringRedisTemplate redis;

    @Autowired
    InventoryReservationService service;

    @BeforeEach
    void resetInventory() {
        redis.delete(KEY);
        redis.opsForHash().put(KEY, "available", "10");
    }

    @Test
    void reservesStockExactlyOnceForSameRequestId() {
        assertThat(service.reserve("sku-42", "r-101", 3))
            .isEqualTo(ReservationOutcome.CREATED);

        assertThat(service.reserve("sku-42", "r-101", 3))
            .isEqualTo(ReservationOutcome.ALREADY_RESERVED);

        assertThat(redis.opsForHash().get(KEY, "available"))
            .isEqualTo("7");

        assertThat(redis.opsForHash().get(KEY, "reservation:r-101"))
            .isEqualTo("3");
    }

    @Test
    void insufficientStockDoesNotWriteReservation() {
        assertThat(service.reserve("sku-42", "r-102", 11))
            .isEqualTo(ReservationOutcome.INSUFFICIENT_STOCK);

        assertThat(redis.opsForHash().get(KEY, "available"))
            .isEqualTo("10");

        assertThat(redis.opsForHash().get(KEY, "reservation:r-102"))
            .isNull();
    }

    @Test
    void rejectsSameRequestIdWithDifferentQuantity() {
        assertThat(service.reserve("sku-42", "r-103", 2))
            .isEqualTo(ReservationOutcome.CREATED);

        assertThat(service.reserve("sku-42", "r-103", 4))
            .isEqualTo(ReservationOutcome.IDEMPOTENCY_CONFLICT);

        assertThat(redis.opsForHash().get(KEY, "available"))
            .isEqualTo("8");
    }
}
~~~

This test assumes Spring Boot properties `spring.data.redis.host` and `spring.data.redis.port`. Depending on Spring Boot version, container setup, package scanning, or configuration, adjust imports, dependencies, and test context setup accordingly.

**Never share a production Redis instance for integration tests.** Tests must control namespaces, reset data, and isolate execution order to avoid colliding with other services.

### Key Assertions in Tests

Good tests do not stop at asserting return codes. They inspect **Redis state after execution**, because bugs can make a script return a success code while skipping a field update or throw an error after partially mutating data.

For retries, assert `available` was not decremented again. For insufficient stock, assert no reservation field was created. These domain invariants matter far more than exact exception wording.

## 13. Concurrency Testing to Prove No Overselling

Suppose stock starts at 10 units and 20 distinct requests each attempt to reserve 1 unit. Expected outcome:

- **Exactly 10** requests succeed as newly created (code `1`).
- Remaining requests return insufficient stock (code `0`).
- `available = 0`.
- Stock never goes negative.
- Every succeeded `reservationId` appears exactly once.

JUnit pseudocode:

~~~java
var pool = java.util.concurrent.Executors.newFixedThreadPool(20);
var start = new java.util.concurrent.CountDownLatch(1);
var tasks = new java.util.ArrayList<
    java.util.concurrent.Future<ReservationOutcome>
>();

try {
    for (int i = 0; i < 20; i++) {
        final String requestId = "parallel-" + i;

        tasks.add(pool.submit(() -> {
            start.await();
            return service.reserve("sku-42", requestId, 1);
        }));
    }

    start.countDown();

    long created = 0;

    for (var future : tasks) {
        var outcome = future.get();
        if (outcome == ReservationOutcome.CREATED) {
            created++;
        }
    }

    assertThat(created).isEqualTo(10L);
    assertThat(redis.opsForHash().get(KEY, "available"))
        .isEqualTo("0");
} finally {
    pool.shutdownNow();
}
~~~

The snippet above is meant to sit **inside a test method** with `service`, `redis`, `KEY`, and imports already in place. It must run against real Redis; mocking `RedisTemplate` only checks Java calls and proves nothing about server execution ordering.

Concurrency tests provide empirical evidence for the "no oversell" invariant on that flow. They do not replace race-condition analysis for the rest of the workflow—especially when payment, restocking, or external database updates occur outside the script.

## 14. Testing Error Cases and Limits of Atomicity

Intentionally inject malformed data in an isolated test Redis instance:

~~~redis
DEL inventory:{sku-42}:state
SET inventory:{sku-42}:state "not-a-hash"
~~~

Then invoke the script. When `HGET` hits a String key, Redis replies `WRONGTYPE`. In Java, Spring Data Redis translates this into an appropriate exception through driver/exception translation.

Tests should assert no unintended side effects occurred.

Another case:

~~~redis
DEL inventory:{sku-42}:state
HSET inventory:{sku-42}:state available invalid
~~~

The script returns `ERR_INVALID_STOCK` before writing. This pattern minimizes malformed-input mutations.

### Atomic Execution Without Rollback

Consider a script to avoid:

~~~lua
redis.call("INCR", KEYS[1])
redis.call("HSET", KEYS[1], "field", "value")
return 1
~~~

`INCR` increments a String counter successfully. `HSET` on the same String key triggers `WRONGTYPE`. By the time the client receives the error, the counter **has already incremented**. Redis does not roll back `INCR` just because a later statement failed.

Keep these four properties distinct:

- **Isolation/no interleaving:** other clients cannot interleave commands while a script executes.
- **Rollback:** undoing prior writes when a script fails—Redis Lua scripts do not provide this guarantee.
- **Idempotency:** retries do not multiply side effects—must be explicitly designed.
- **Durability:** state survives a Redis crash—depends on persistence/replication, not Lua alone.

These are four separate properties. Calling `EVAL` alone does not grant all four.

## 15. Managing Source and Script Cache Across Deployments

Lua scripts belong to **application source code**, whereas the Redis script cache is **runtime state**.

~~~text
Git repository
  reserve-stock-v1.lua
          |
          v
CI packages into JAR / image
          |
          v
Spring RedisScript bean
          |
          v
EVALSHA -> if NOSCRIPT -> EVAL
          |
          v
Redis executes and may cache script
~~~

Scenarios to plan for:

**Redis restart:** The script cache may be empty. Callers must still retain the Lua body for fallback.

**Failover:** The new primary may not share the prior primary's script cache. Never assume every node already holds the SHA.

**SCRIPT FLUSH:** Cache cleared. Subsequent calls need a fallback path. Note that the script cache and Redis Function libraries are separate mechanisms.

**Redis Cluster:** Nodes can hold different script cache states. `SCRIPT EXISTS` on one node does not prove every node has cached the script.

**Redis server version:** Script retention and eviction policies can differ across versions (such as evicting `EVAL`-loaded scripts in newer releases). Application code should rely on fallback-capable execution rather than assuming scripts remain cached indefinitely.

Never write a startup job that calls `SCRIPT LOAD` on one node and treats that as a permanent cluster-wide guarantee. Preloading can reduce initial fallbacks, **not replace bundling the source in the artifact**.

## 16. Versioning Strategy for Lua Scripts

Version scripts by **contract**, not merely by checksum.

A clean convention:

~~~text
src/main/resources/redis/scripts/
  reserve-stock-v1.lua
  reserve-stock-v2.lua
  release-reservation-v1.lua
  README.md
~~~

For each script, contract documentation covers:

| Aspect to version | Question |
| --- | --- |
| Number and order of KEYS | Can older callers still invoke it? |
| Number and meaning of ARGV | Are new parameters mandatory? |
| Return type and codes | Does older Java code understand every code? |
| Redis key/field structure | Can two app versions read/write shared data safely? |
| Algorithm and invariants | Did reservation semantics change? |
| Idempotency scope | Will old request IDs be interpreted differently? |
| Timeout and complexity | Does the new script alter Redis load? |
| Minimum Redis/Spring versions | Does it use newer commands or APIs? |

Example change warranting v2:

~~~text
v1:
  KEYS[1] = inventory hash
  ARGV[1] = reservationId
  ARGV[2] = quantity
  return = integer code

planned v2:
  KEYS[1] = inventory hash
  ARGV[1] = reservationId
  ARGV[2] = quantity
  ARGV[3] = expiresAtEpochMillis
  return = new code for expired reservation
~~~

If you overwrite `reserve-stock-v1.lua` to require `ARGV[3]`, older Java instances still sending two arguments will fail. During a rolling deployment, that breakage happens immediately as soon as part of the fleet upgrades.

To keep old callers working:

- Keep v1 intact until it can be retired safely.
- Add a separate v2 file and `reserveStockV2Script` bean.
- Route new code to v2 via feature flags or deployment config.
- Ensure v1 and v2 read/write data under a compatible strategy.
- Delete v1 only once zero clients need it and rollback plans no longer depend on it.

**New Lua content generates a new SHA**, while v1/v2 filenames give humans clean compatibility management without memorizing long SHAs.

## 17. Rolling Deployment: Risks from Two Running App Versions

Common scenario:

~~~text
Time            App instance A              App instance B
---------       --------------              --------------
T0              release 1 calls Lua v1      release 1 calls Lua v1
T1              release 2 calls Lua v2      release 1 calls Lua v1
T2              release 2 calls Lua v2      release 2 calls Lua v2
~~~

At `T1`, v1 and v2 **operate concurrently on Redis**. If v2 renames a field from `available` to `freeUnits` without backward compatibility, v1 and v2 can see two different stock counts.

Serious consequence: each app version thinks it validated stock, yet both read different counters. This is a **data schema compatibility** problem, not merely a SHA cache issue.

### The Expand–Migrate–Contract Process

A structured rollout for major changes:

1. **Expand:** deploy code capable of reading both old and new schemas without breaking old callers.
2. **Migrate:** backfill or transform data in batches, running safely during the compatibility window.
3. **Switch:** shift traffic to script v2 via rollout or feature flags.
4. **Observe:** monitor result codes, errors, latency, and business invariants.
5. **Contract:** once rollback to v1 is no longer needed, remove old code paths and legacy data on schedule.

If v1 and v2 cannot share a schema, consider versioned key namespaces or a controlled write freeze during migration. Never assume "new app deployed successfully" means it is safe to mutate data structures still read by an older version.

### Deciding When to Retire Old Scripts

An older script may still be needed by:

- Unupgraded pods or instances.
- Long-running jobs or consumers still on the old release.
- Operational/CLI tools invoking fixed scripts.
- Application rollback plans.
- Legacy data awaiting reads or release.

Set explicit retirement criteria before deleting v1 so bugs do not surface only during a rollback.

## 18. Wiring Script Versions in Java Without Brittle Dynamic Strings

Separate bean declarations:

~~~java
@Bean
public RedisScript<Long> reserveStockV1Script() {
    DefaultRedisScript<Long> script = new DefaultRedisScript<>();
    script.setLocation(
        new ClassPathResource("redis/scripts/reserve-stock-v1.lua")
    );
    script.setResultType(Long.class);
    return script;
}

@Bean
public RedisScript<Long> reserveStockV2Script() {
    DefaultRedisScript<Long> script = new DefaultRedisScript<>();
    script.setLocation(
        new ClassPathResource("redis/scripts/reserve-stock-v2.lua")
    );
    script.setResultType(Long.class);
    return script;
}
~~~

When two beans share the type `RedisScript<Long>`, **explicitly disambiguate which bean is injected**, such as via `@Qualifier("reserveStockV1Script")` or matching parameter names with appropriate injection rules. Never leave script selection up to Spring autowiring ambiguity.

Example:

~~~java
public InventoryReservationService(
        StringRedisTemplate redis,
        @Qualifier("reserveStockV1Script")
        RedisScript<Long> script) {
    this.redis = redis;
    this.reserveStockV1 = script;
}
~~~

Instead of letting controllers pick `v1` vs. `v2`, build an adapter that selects the implementation via deployment configuration. If using a feature flag, guarantee both versions obey a compatible data contract throughout the rollout.

### Script Versions in Logs and Metrics

Record fields such as:

~~~text
redis_script_name=reserve-stock
redis_script_contract=v1
redis_result_code=1
redis_duration_ms=2.3
application_release=2026.11.13
~~~

This helps pinpoint issues affecting only one release or subset of instances. Never log sensitive `ARGV` payloads like tokens, emails, or payment details; keep only safe correlation IDs and diagnostic metadata.

## 19. How Do Redis Lua Scripts Differ from Redis Functions?

Beyond `EVAL`/`EVALSHA`, modern Redis versions support **Redis Functions**, managing named function libraries invoked via `FCALL` or `FCALL_RO` where applicable.

High-level comparison:

| Criterion | Traditional Lua scripts | Redis Functions |
| --- | --- | --- |
| Invocation | `EVAL`, `EVALSHA` | `FCALL`, `FCALL_RO` |
| Execution identity | Script content/SHA | Function name inside a library |
| Deployment source | Bundled inside the Spring application | Library deployed and managed on Redis |
| Cache/loading | Ephemeral script cache and fallback | Dedicated function library management |
| Upgrades | Java code + resource + new SHA | Library lifecycle and caller coordination |
| Best fit | Few short scripts tightly coupled to an app | Shared server-side libraries managed as Redis components |

Redis Functions do not remove the need for testing, contract versioning, schema migration, or concurrency handling. They are a complementary architectural option, **not a reason to mix Functions and `EVALSHA` haphazardly**.

If you currently use Spring Data Redis `RedisScript`, this guide follows the traditional scripting model. Adopting Redis Functions requires redesigning deployment and invocation APIs to match your client and server versions.

## 20. Performance and Script Execution Limits

Lua scripts execute inside Redis. Long-running scripts block Redis from serving other commands. Scripts should never:

- Scan the entire keyspace with `KEYS *`.
- Loop unboundedly over client-controlled data.
- Run tens of thousands of Redis commands inside an unbounded request.
- Parse huge payloads or allocate massive Lua tables.
- Combine unrelated work simply because "one `EVAL` is atomic."
- Run heavy computation better suited to the application tier.

Redis logs warnings when scripts exceed a configured time threshold, yet **client timeouts are never a safe cancellation mechanism**. A Java timeout never proves Redis did not execute the script.

Notably, `SCRIPT KILL` cannot stop scripts that have already performed writes. Never build production workflows assuming you can kill any running script safely mid-flight.

### Good Design Pattern

~~~text
Java validates inputs
       |
       v
Short EVAL script:
  read a few keys/fields
  validate
  bounded update
  return code
       |
       v
Java continues business workflow
~~~

For jobs scanning millions of IDs or coordinating across systems, use workers and batches. Lua is meant for **a short critical section** inside Redis, not a workflow engine.

## 21. Retries, Timeouts, and Idempotency in Operations

Even a short script can experience:

- Disconnection before Redis receives the command.
- Redis executing the script while the reply is lost.
- Failover leaving the client unsure whether execution completed.
- Automatic retries at client or service layers.
- Nearly simultaneous duplicate requests carrying the same ID.

"No response received" does not prove the script did not run. Therefore:

1. Generate a stable `reservationId` per business request.
2. Include that ID in the script contract.
3. Persist the processed marker inside the same critical Redis operation.
4. On retry, send the **exact same ID and decisive arguments**.
5. On a conflict code, investigate instead of generating a new ID and retrying.

In v1:

~~~text
Attempt 1:
  reserve(sku-42, r-101, 3)
  Redis writes successfully, then client times out.

Attempt 2:
  reserve(sku-42, r-101, 3)
  Redis sees reservation:r-101 = 3
  -> returns 2, does not deduct again.
~~~

If the caller creates a fresh ID on retry, this protection disappears.

### Idempotency Only Lasts as Long as the Underlying Data

If the Redis Hash is deleted or expires, the `reservation:r-101` marker vanishes. Retrying that ID against a recreated inventory Hash treats it as a new request. Critical workflows must define **idempotency record retention** and an authoritative source of truth for reservations.

When releases, refunds, payments, or external databases are involved, manage cross-system consistency separately; the reservation script only protects the Redis update step.

## 22. Observability and Error Handling After Deployment

When a script fails in production, classify errors cleanly:

| Error category | Example | Action |
| --- | --- | --- |
| Contract error | Wrong `KEYS`/`ARGV` count | Fix caller; do not retry endlessly |
| Data error | `WRONGTYPE`, non-numeric stock | Halt operation, investigate data |
| Valid out-of-stock | Returns `0` | Return business outcome; do not log as exception |
| Valid retry | Returns `2` | Treat request as already fulfilled |
| Idempotency conflict | Returns `-2` | Check for improperly reused request ID |
| Script cache miss | `NOSCRIPT` | Executor falls back to `EVAL`; not a data error |
| Timeout/connection | Lost reply | Retry idempotently, inspect state |
| Slow script | Redis busy/latency spike | Reduce complexity, consider splitting work |

Monitoring should cover:

- Script name and **contract version**.
- Invocation count, success rate, and result-code distribution.
- Client-side latency and timeouts.
- Serialization, command, and `WRONGTYPE` error counts.
- Correlation between script traffic and Redis server latency.
- Business invariants: non-negative stock, reservation totals matching deductions.
- Retry and idempotency-conflict rates.

Never watch only Java exception counts. A script perpetually returning `0` due to corrupted input can break API success rates completely without throwing a single exception.

## 23. Planning a v2 Release

Suppose we need to add `expiresAt` to each reservation. A structured rollout looks like:

~~~text
Phase 1: Prepare
  - Define v2 contract (additional ARGV deadline).
  - Create reserve-stock-v2.lua.
  - Add v2 tests and v1/v2 compatibility tests on shared schema.
  - Leave v1 untouched.

Phase 2: Compatibility
  - Update readers/release paths to understand both old and new reservations.
  - Add schema/metadata so v1 continues functioning cleanly.
  - Verify rollback path.

Phase 3: Shift traffic
  - Deploy Java containing both v1 and v2.
  - Enable v2 for a slice of traffic.
  - Monitor return codes, latency, and data invariants.
  - Ramp traffic once stable.

Phase 4: Cleanup
  - Confirm zero remaining v1 callers or rollback need.
  - Remove v1 code, beans, and resources on schedule.
  - Clean up legacy data as needed.
~~~

Most critically: **test the overlap phase where both releases run concurrently**. Testing v2 only on an empty Redis instance misses bugs when v2 reads v1-created records or v1 touches new records.

### Avoid Unnecessary Version Bumps

You do not need v2 just for editing a comment or formatting. Still, changing Lua code inside v1 alters the source hash and can alter runtime behavior between builds, so follow full review, testing, and rollout discipline. Contract version names track contract changes, while build/artifact versions track individual source releases.

## 24. Common Mistakes

### Mistake 1: Embedding Long Lua Scripts as Java Strings

~~~java
String lua = "local x = redis.call('GET', KEYS[1]); ..."
           + "...";
~~~

For long scripts, inline strings are hard to diff, review, and keep free of quote/newline mistakes. Tiny snippets are occasionally fine inline, whereas real business logic belongs in resource files.

### Mistake 2: Building Redis Key Names from ARGV Inside the Script

~~~lua
local key = "inventory:" .. ARGV[1]
redis.call("GET", key)
~~~

Redis scripting requires accessed keys to be declared properly via `KEYS`. Hidden key construction breaks especially on Redis Cluster. Build keys at the caller, pass them in `KEYS`, and reserve `ARGV` for regular values.

### Mistake 3: Believing Lua Rolls Back Automatically on Errors

Scripts are atomic against interleaving, yet leave prior mutations behind on runtime errors. Validate before writing and minimize write steps as the primary defense.

### Mistake 4: Assuming EVALSHA Always Succeeds After Preloading

The script cache can vanish on restarts, failovers, flushes, or eviction policies. Use a fallback-capable executor or handle `NOSCRIPT` explicitly at low levels.

### Mistake 5: Overwriting the v1 Contract Directly with v2

During rolling deployments, older callers still call v1. Changing `ARGV` counts or field schemas in place breaks mixed-version fleets. Keep both versions until migration completes.

### Mistake 6: Asserting Only Return Codes Without Checking Redis Data

A script can return an expected code while writing the wrong field or omitting updates. Tests must verify Redis post-state invariants.

### Mistake 7: Testing Only with a Mocked RedisTemplate

Mocks prove Java called the right method, without running Lua or proving atomicity. Use real Redis for integration tests.

### Mistake 8: Retrying with a New Request ID

A missing reply does not prove the operation never ran. Using a new ID risks reserving stock twice. Keep idempotency keys stable across retries.

### Mistake 9: Treating Scripts as a Place for Entire Workflows

Lua holds Redis busy while executing; never use it to scan huge datasets or run multi-step long jobs. External service calls belong in application workers with proper durability.

### Mistake 10: Ad-Hoc Key Concatenation in Cluster

Multi-key scripts in Redis Cluster obey slot rules. Design hash tags purposefully and test against real Cluster topologies.

## 25. Team Workflow for Lua Scripts

A disciplined script lifecycle:

**Creating a new script**

1. Document `KEYS`, `ARGV`, return types, data schemas, and idempotency contract.
2. Place the resource under a stable name with a version suffix when appropriate.
3. Keep Lua short and validate before mutations.
4. Declare a `RedisScript<T>` bean with an explicit `resultType`.
5. Encapsulate calls inside one dedicated service/adapter.
6. Add integration tests against real Redis, including errors and concurrency.
7. Verify compatibility with supported active releases.
8. Track script/version/outcome metrics after deployment.

**Modifying an active script**

1. Determine whether the change is internal or contract-breaking.
2. If contract-breaking, create v2 and a migration strategy.
3. Test against both old-created and new-created data.
4. Test concurrent execution of old and new app versions.
5. Set clear monitoring thresholds and a concrete rollback plan.
6. Retire v1 only after all callers and legacy data are handled.

**Handling Redis restarts/failovers**

The application must still load script source from its resource and fall back on cache misses. Never rebuild a JAR just to restore a missing SHA; proper script execution handles reloading automatically.

## 26. Extended Exercises

### Exercise A: Release Reservation

Design `release-reservation-v1.lua` accepting:

~~~text
KEYS[1] = inventory hash
ARGV[1] = reservationId
~~~

Requirements:

- If the reservation exists, add its exact quantity back to `available` and remove the reservation field.
- If release is retried, return a distinct code and **do not add twice**.
- Never allow `available` to go negative or violate business limits.
- Test concurrent release calls.

Note: if release uses two write commands (`HINCRBY` and `HDEL`), remember the partial-write risk on errors; compute upfront and use appropriate writes or adjust representation to reduce risk.

### Exercise B: Upgrading the Contract to v2

Add a `deadline` to each reservation and design metadata reads that do not break v1. Write a compatibility matrix covering v1/v2 apps and pre-/post-migration data.

### Exercise C: Recovering After Timeouts

Wrap the service to simulate losing the response after Redis executed the script. Retry with the same ID and verify stock decremented only once. Contrast with retrying using a fresh ID.

### Exercise D: Verifying Redis Cluster Behavior

Design a script using `inventory:{sku-42}:state` and `inventory:{sku-42}:audit`. Explain why they share a hash slot and what happens if the second key changes to `inventory:{sku-99}:audit`.

### Exercise E: Optimizing a Long Script

An old script scans thousands of members and performs heavy checks per request. Split scanning into Java/worker batching and keep a short script strictly for the final critical section; compare latency under load.

## 27. Official References

- [Spring Data Redis – Scripting](https://docs.spring.io/spring-data/redis/reference/redis/scripting.html)
- [Spring Data Redis – RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html)
- [Spring Data Redis – RedisScript API](https://docs.spring.io/spring-data/redis/reference/api/java/org/springframework/data/redis/core/script/RedisScript.html)
- [Spring Data Redis – DefaultRedisScript API](https://docs.spring.io/spring-data/redis/reference/api/java/org/springframework/data/redis/core/script/DefaultRedisScript.html)
- [Redis – Scripting with Lua](https://redis.io/docs/latest/develop/programmability/eval-intro/)
- [Redis – EVAL](https://redis.io/docs/latest/commands/eval/)
- [Redis – EVALSHA](https://redis.io/docs/latest/commands/evalsha/)
- [Redis – SCRIPT LOAD](https://redis.io/docs/latest/commands/script-load/)
- [Redis – Redis Functions](https://redis.io/docs/latest/develop/programmability/functions-intro/)
- [Redis – Redis Cluster specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/)

## 28. Summary

A production Lua script in Spring Data Redis must be managed as **part of your API and data model**, not just a snippet sent to Redis:

- **Packaging:** store files in `src/main/resources`, declare `DefaultRedisScript`, and expose callers through a service with an explicit contract.
- **Atomicity:** other Redis commands do not interleave mid-script; however, errors after writes **do not automatically roll back**.
- **Testing:** run against real Redis, verifying post-operation state, error cases, retries, and concurrency.
- **Cache management:** `EVALSHA` can hit `NOSCRIPT`; keep script source in the artifact for fallback.
- **Versioning:** v1/v2 track contract compatibility while SHA identifies exact bytes; rolling deployments require v1 and v2 to coexist safely on shared data during transitions.
- **Operations:** keep scripts short, measure latency, enforce idempotency, respect Redis Cluster rules, and maintain safe rollback paths.

Following these practices turns Lua into a reliable, maintainable tool for protecting critical sections in Redis while letting Spring Boot applications evolve versions without breaking Redis data contracts.
