# Testing Consumer Groups, Acknowledgments, and Pending Entries

**Redis Streams** persist messages for consumers to read later and support **consumer groups** to distribute work across multiple workers. In **Spring Data Redis**, this is commonly implemented using `StreamOperations`, `StreamMessageListenerContainer`, or `StreamReceiver`. However, an application reading an event does not prove the event was processed successfully: Redis also tracks events **delivered but not yet acknowledged** inside the group's **Pending Entries List (PEL)**.

When testing, do not merely prove “sent an event, listener received an event.” Verify every operationally meaningful scenario:

- How are new events distributed across a consumer group?
- When does `XACK` remove an event from the PEL?
- If a worker stops or crashes **before ACK**, where does the event go?
- Can a new worker claim and reprocess the old event?
- If side effects committed yet the ACK failed to send, how do we avoid duplicate processing?
- If the stream is trimmed or the group was created at the wrong offset, can records still be recovered?
- How do Spring Data Redis APIs reflect Redis state?

This lesson builds a test model from **Redis CLI** to **JUnit + Testcontainers + Spring Data Redis**, covering failure cases and how to structure tests without relying on arbitrary sleeps.

## 1. Distinguish Three States Before Writing Tests

A message in Redis Streams passes through at least three milestones:

1. **Persisted:** `XADD` succeeded and the entry received a stream ID.
2. **Delivered:** `XREADGROUP` handed the entry to a consumer; Redis tracks the unacknowledged entry in the group's PEL.
3. **Processed:** business code completed side effects and the application called `XACK` per policy.

```text
Producer                        Redis Stream                  Consumer
   |                                 |                            |
   | --- XADD event ---------------->|                            |
   |                                 | stores entry ID 100-0      |
   |                                 |                            |
   |                                 |<---- XREADGROUP ... > -----|
   |                                 |----- event 100-0 --------->|
   |                                 |                            |
   |                                 | PEL holds 100-0            |
   |                                 |                            | process business logic
   |                                 |                            | commit succeeds
   |                                 |<------- XACK 100-0 --------|
   |                                 |                            |
   |                                 | PEL no longer has 100-0    |
```

Key point: **`XACK` does not delete the payload from the stream.** It removes the entry from **one group's** pending list. Removing payloads is a separate concern involving `XDEL`, `XTRIM`, retention, and stream management.

### State Verification Table

| State | Entry Still in Stream | Entry in Group's PEL | Consumer Processed Business Work |
|---|---|---|---|
| Just `XADD`ed, unread by group | Yes | No | No |
| Returned by `XREADGROUP`, unACKed | Yes | Yes | Uncertain |
| Handler failed, no ACK | Yes unless deleted/trimmed | Yes | Failed or unknown |
| Handler succeeded, crashed before ACK | Yes | Yes | Likely succeeded |
| `XACK`ed | Yes unless deleted/trimmed | No | Application declared done |
| Payload `XDEL`ed/trimmed while pending | No | Pending trace may remain | Cannot auto-recover deleted payload |

Therefore, asserting only that the listener was invoked is **insufficient**. Verify PEL state, actual ACK counts, and side effects in the business store.

## 2. Redis Streams Commands Used in Testing

| Command | Role | What to Check |
|---|---|---|
| `XADD` | Append entry to stream | Generated ID, payload, ordering |
| `XGROUP CREATE` | Create group from an offset | Start from history vs. new events only |
| `XREADGROUP` | Read as a consumer in a group | Delivered events, consumer assignment, pending entries |
| `XACK` | Acknowledge processed entries | ACK count and updated PEL |
| `XPENDING` | Inspect PEL summary/details | Pending count, owner, idle time, delivery count |
| `XCLAIM` | Transfer specific pending entries to another consumer | Ownership transfer, payload returned |
| `XAUTOCLAIM` | Scan and claim idle pending entries | Scan cursor, batch claim, reprocessing |
| `XINFO GROUPS` | Inspect group metadata | Consumers, last-delivered ID, pending, lag when present |
| `XINFO CONSUMERS` | Inspect consumer metadata | Per-consumer pending count and idle time |
| `XRANGE` | Inspect remaining stream entries | Payload persists after ACK |
| `XLEN` | Current stream length | Do not confuse with pending count |
| `XTRIM`/`XDEL` | Prune entries | Behavior when payloads disappear |
| `XGROUP DESTROY` | Delete group | Clean up test group state without deleting stream |

Two critical read syntaxes:

```text
XREADGROUP ... STREAMS stream:key >
    -> Receive NEW messages never yet delivered to the group.

XREADGROUP ... STREAMS stream:key 0
    -> Re-read PENDING history owned by that exact consumer per group rules.
```

Never treat `>` as “re-read all unprocessed events.” It does not automatically scan the PEL of a dead consumer.

## 3. Creating a Group at Offset `0` vs. `$`: Two Different Tests

Redis lets you initialize a consumer group at an explicit starting position.

### Reading All Existing History

```bash
redis-cli XADD stream:test:orders '*' eventId e-1 type CREATED
redis-cli XADD stream:test:orders '*' eventId e-2 type PAID

redis-cli XGROUP CREATE stream:test:orders group-from-start 0
redis-cli XREADGROUP GROUP group-from-start worker-a \
    COUNT 10 STREAMS stream:test:orders '>'
```

With a group created at `0`, entries already in the stream are delivered when reading new group messages. This fits consumers that must process retained history.

### Receiving Only Entries Added After Group Creation

```bash
redis-cli XGROUP CREATE stream:test:orders group-from-now '$'

redis-cli XADD stream:test:orders '*' eventId e-3 type SHIPPED

redis-cli XREADGROUP GROUP group-from-now worker-b \
    COUNT 10 STREAMS stream:test:orders '>'
```

A group created at `$` starts at the tail of the stream at creation time. Entries already present **are not delivered as new messages** when reading `>` on this group.

**Tests must state where the group starts.** If a test expects old entries yet creates the group at `$`, it fails due to the wrong offset rather than a broken consumer handler.

Naming note: `0` is treated by Redis as the start of the stream; `0-0` is the full ID form, both commonly used to start from history.

## 4. Manual Testing: Delivery, Pending Entries, and ACK

Use a **test-dedicated Redis** with non-colliding stream/group names. Never run destructive commands on shared or production Redis.

### 4.1. Initializing a New Stream and Group

```bash
redis-cli DEL stream:test:payments
redis-cli XADD stream:test:payments '*' eventId pay-1 type AUTHORIZED
redis-cli XADD stream:test:payments '*' eventId pay-2 type CAPTURED
redis-cli XADD stream:test:payments '*' eventId pay-3 type SETTLED

redis-cli XGROUP CREATE stream:test:payments payment-workers 0
```

Redis returns real stream IDs formatted as `<milliseconds>-<sequence>`. Use the actual IDs returned in subsequent steps rather than copying placeholder IDs into a real environment.

### 4.2. Consumer A Reads Two Events

```bash
redis-cli XREADGROUP GROUP payment-workers worker-a \
    COUNT 2 STREAMS stream:test:payments '>'
```

Expected:

- Up to two undelivered entries are returned.
- Both enter the group's pending list.
- Owner is `worker-a`.
- The third event remains undelivered.

Inspect:

```bash
redis-cli XPENDING stream:test:payments payment-workers
redis-cli XPENDING stream:test:payments payment-workers - + 10
redis-cli XINFO GROUPS stream:test:payments
```

Meaningful check: pending count equals 2, not 3, because `pay-3` has not been delivered to any worker yet.

### 4.3. ACKing Exactly One Event

Replace `<ID-of-pay-1>` with the real stream ID:

```text
XACK stream:test:payments payment-workers <ID-of-pay-1>
```

Expected:

- `XACK` returns `1` as the pending entry in the group is acknowledged.
- Pending count drops from 2 to 1.
- `pay-2` stays pending, still owned by `worker-a`.
- `pay-1`'s payload remains in the stream because ACK is not `XDEL`.

Verify payload still exists:

```bash
redis-cli XRANGE stream:test:payments - +
```

If you ACK the same ID again:

```text
XACK stream:test:payments payment-workers <ID-of-pay-1>
```

It normally returns `0` because the entry is no longer pending in the group. **Never treat `0` on a duplicate ACK as proof the handler never processed it successfully**; the group may simply have acknowledged it earlier.

### 4.4. Consumer B Receives New Events

```bash
redis-cli XREADGROUP GROUP payment-workers worker-b \
    COUNT 10 STREAMS stream:test:payments '>'
```

Once `pay-1` and `pay-2` were delivered to A, B reading `>` receives only `pay-3`. UnACKed `pay-2` **is not automatically reassigned to B**. This is a core assertion distinguishing normal group delivery from recovery.

## 5. Testing Crash Before ACK

A realistic test does not have to kill the JVM: simply **read an event, simulate a handler error, and skip calling ACK**. Redis retains the pending entry for observation and recovery.

```text
T0: XADD event e-10
T1: worker-a XREADGROUP e-10
T2: e-10 sits in PEL, owner worker-a
T3: handler throws exception or worker stops
T4: No XACK
T5: worker-b reads ... >, does not receive e-10
T6: worker-b XCLAIM/XAUTOCLAIM e-10
T7: worker-b processes, XACKs
```

The test must verify **two contrasting behaviors**:

1. Simply calling `XREADGROUP ... >` never brings `e-10` back automatically.
2. Recovery via claiming transfers ownership of `e-10` when eligible and payload remains.

### 5.1. Reading Pending Entries of the Same Consumer

If worker A reconnects using the **exact same consumer name**, it can read its own pending entries:

```bash
redis-cli XREADGROUP GROUP payment-workers worker-a \
    COUNT 10 STREAMS stream:test:payments 0
```

This does not fetch entries pending under B. When a new instance deploys with a different consumer name, you need a claiming path.

### 5.2. Reclaiming Pending Entries via `XCLAIM`

If `pay-2`'s ID is known, worker B can run:

```text
XCLAIM stream:test:payments payment-workers worker-b 0 <ID-of-pay-2>
```

`0` is the minimum idle-time threshold in milliseconds to claim immediately in tests; **never use `0` in production**, as it can steal messages from a healthy worker A still processing normally.

After claiming, inspect:

```bash
redis-cli XPENDING stream:test:payments payment-workers - + 10
redis-cli XINFO CONSUMERS stream:test:payments payment-workers
```

Expect the claimed event's owner to change to `worker-b`; the group's total pending count does not drop because **claim is not ACK**.

Once B finishes processing, call `XACK` with the exact ID to clear the pending entry.

### 5.3. Reclaiming Pending Entries via `XAUTOCLAIM`

When you do not know pending IDs ahead of time, Redis scans the PEL via `XAUTOCLAIM`:

```bash
redis-cli XAUTOCLAIM stream:test:payments payment-workers worker-b \
    0 0-0 COUNT 10
```

In tests, min-idle `0` avoids sleeping. Results include the next scan cursor and claimed entries; supported Redis versions also report IDs whose payloads were deleted.

In production, pick a min-idle matching valid processing/lease durations, e.g.:

```bash
redis-cli XAUTOCLAIM stream:orders:v1 order-workers worker-b \
    60000 0-0 COUNT 100
```

60,000 ms is illustrative only. Continue scanning from the returned cursor if more entries remain, and remember that advancing the scan cursor does not mean all PEL entries have finished processing.

## 6. Testing Multiple Consumers in One Group and Multiple Independent Groups

### 6.1. Two Consumers in One Group Sharing Work

```text
Stream: [e1, e2, e3, e4]

Consumer group: order-workers
    worker-a -> e1, e2
    worker-b -> e3, e4
```

Each new message is delivered to **one consumer in the group** under standard worker distribution. Never write tests expecting every worker in the same group to receive all events.

When two consumers concurrently call `XREADGROUP ... >`, exact distribution depends on scheduling and request timing; assert **the combined set of delivered events with zero loss**, rather than hardcoding “A always gets e1, B always gets e2” without explicit coordination.

### 6.2. Two Independent Groups Receiving the Same Events

```text
Stream: [e1, e2]

Group A: billing-workers       -> processes e1, e2
Group B: notification-workers  -> processes e1, e2
```

Each group tracks its own offset and PEL. `XACK` of `e1` in group A **does not ACK `e1` in group B**.

Tests should verify:

- The same event is delivered independently to each group.
- `XPENDING` tracks separate state per group.
- ACKs in group A do not reduce pending counts in group B.
- Retention accommodates the slowest group if both require replay.

### 6.3. ACKing the Wrong Group

If an ID is pending in `billing-workers` and the test runs:

```text
XACK stream:test:payments notification-workers <ID-of-e1>
```

this never ACKs `e1` in `billing-workers`. Redis tracks PEL **per group**, not globally by stream ID.

Checking group names helps catch bugs when an app handles multiple event types on one stream or misconfigures variables.

## 7. Designing Isolated, Deterministic Tests

Timing-, concurrency-, and Redis-based tests easily turn **flaky** if written with `Thread.sleep(1000)` hoping a worker finished reading. Design tests with explicit preconditions and observations.

### 7.1. Isolate Data per Test

Use unique stream keys:

```text
stream:test:orders:<test-id>
group:test:orders:<test-id>
```

Or run each test against a dedicated Redis container. Under parallel JUnit execution, fixed stream and consumer group names cause tests to collide in the same PEL.

If sharing a test Redis instance:

- Namespace streams and groups per test.
- Delete only the test's own keys during setup/cleanup.
- Never run `FLUSHALL` on a Redis shared with other tests or services.
- Prevent background listeners from earlier tests from continuing to run and stealing events from later tests.

### 7.2. Never Use Infinite Blocking Waits

Commands like:

```text
XREADGROUP ... BLOCK 0 ...
```

can block forever waiting for an event. In integration tests, use short explicit deadlines (e.g., 100–500 ms) paired with concrete assertions.

When testing blocking delivery, use `CountDownLatch`, futures with timeouts, or similar coordination to ensure the listener started before publishing events.

### 7.3. Never Guess Based on Redis's Clock

PEL tracks idle time from delivery/claim; CI machines vary widely in speed. To test **claim mechanics** rather than idle timing, pass min-idle `0` in controlled tests. To test **do not claim before threshold**, use generous durations and windows rather than fragile millisecond margins.

### 7.4. Do Not Hardcode Stream IDs

Redis-generated IDs depend on timestamps and sequences. Capture the `RecordId` returned by `XADD` and use it for ACKs/claims. Avoid hardcoding IDs like `1780000000000-0` unless the test intentionally supplies explicit valid IDs and understands Redis's monotonicity rules.

## 8. Spring Boot Test Environment with Real Redis

For consumer group tests, mocking `RedisTemplate` is insufficient to prove PEL, claiming, and group offsets behave properly. **Testcontainers** runs real Redis in a reproducible test environment.

Gradle dependencies example:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:testcontainers'
}
```

Match dependency versions to your project's BOM/dependency management. The Redis container must run a version supporting the tested commands: `XAUTOCLAIM` requires a newer Redis version than `XREADGROUP`/`XACK`.

Spring Boot test harness example:

```java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
@SpringBootTest
class RedisStreamIntegrationTest {

    @Container
    static final GenericContainer<?> REDIS =
            new GenericContainer<>(
                    DockerImageName.parse("redis:7.4-alpine"))
                    .withExposedPorts(6379);

    @DynamicPropertySource
    static void redisProperties(DynamicPropertyRegistry registry) {
        registry.add(
                "spring.data.redis.host",
                REDIS::getHost);
        registry.add(
                "spring.data.redis.port",
                () -> REDIS.getMappedPort(6379));
    }

    // @Test methods follow in the sections below.
}
```

In a real project, this test class runs alongside a Spring Boot application/test configuration providing `StringRedisTemplate` or `RedisTemplate`. This is an illustrative integration-test skeleton, not an instruction to start Redis manually in production.

**Never run tests against production Redis.** Scenarios using `DEL`, `XGROUP CREATE`, `XCLAIM`, or `XTRIM` mutate state and can disrupt real consumers.

## 9. JUnit Tests: `XADD`, `XREADGROUP`, PEL, and `ACK`

Let us implement a test following Spring Data Redis semantics. With `StringRedisTemplate`, Stream commands live under `opsForStream()`.

### 9.1. Preparing an Isolated Stream for Tests

```java
import java.util.Map;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.data.redis.connection.stream.ReadOffset;
import org.springframework.data.redis.connection.stream.RecordId;
import org.springframework.data.redis.core.StringRedisTemplate;

class StreamTestSupport {

    @Autowired
    StringRedisTemplate redis;

    String streamKey;

    void setUpStream(String testId) {
        streamKey = "stream:test:orders:" + testId;
        redis.delete(streamKey);
    }

    RecordId append(String eventId) {
        return redis.opsForStream().add(
                streamKey,
                Map.of(
                        "eventId", eventId,
                        "type", "ORDER_CHANGED"));
    }

    void createGroupFromStart(String group) {
        // Stream must exist: call append(...) before creating group.
        redis.opsForStream().createGroup(
                streamKey,
                ReadOffset.from("0-0"),
                group);
    }
}
```

In the tests below, to avoid collisions during parallel runs, stream names are generated with `UUID`. These are self-contained test methods; if extracting a helper, preserve the order of appending before creating the group.

### 9.2. Testing Pending Counts Change on ACK

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.util.List;
import java.util.Map;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.data.redis.connection.stream.Consumer;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.PendingMessagesSummary;
import org.springframework.data.redis.connection.stream.ReadOffset;
import org.springframework.data.redis.connection.stream.RecordId;
import org.springframework.data.redis.connection.stream.StreamOffset;
import org.springframework.data.redis.core.StreamReadOptions;
import org.springframework.data.redis.core.StringRedisTemplate;

class StreamGroupContractTests {

    @Autowired
    StringRedisTemplate redis;

    @Test
    void deliveredEntriesStayPendingUntilAck() {
        String stream = "stream:test:orders:" + UUID.randomUUID();
        String group = "group-a";

        RecordId first = redis.opsForStream().add(
                stream, Map.of("eventId", "evt-1"));
        RecordId second = redis.opsForStream().add(
                stream, Map.of("eventId", "evt-2"));

        redis.opsForStream().createGroup(
                stream, ReadOffset.from("0-0"), group);

        List<MapRecord<String, Object, Object>> records =
                redis.opsForStream().read(
                        Consumer.from(group, "worker-a"),
                        StreamReadOptions.empty().count(10),
                        StreamOffset.create(
                                stream, ReadOffset.lastConsumed()));

        assertNotNull(records);
        assertEquals(2, records.size());

        PendingMessagesSummary before =
                redis.opsForStream().pending(stream, group);
        assertEquals(2L, before.getTotalPendingMessages());

        Long acknowledged = redis.opsForStream()
                .acknowledge(stream, group, first);
        assertEquals(1L, acknowledged);

        PendingMessagesSummary after =
                redis.opsForStream().pending(stream, group);
        assertEquals(1L, after.getTotalPendingMessages());

        // Second XACK does not re-ACK an already-acknowledged entry.
        Long repeated = redis.opsForStream()
                .acknowledge(stream, group, first);
        assertEquals(0L, repeated);

        // Second message remains in PEL until acknowledged.
        redis.opsForStream().acknowledge(stream, group, second);
        assertEquals(
                0L,
                redis.opsForStream()
                        .pending(stream, group)
                        .getTotalPendingMessages());
    }
}
```

Run this inside a Spring Boot test context with a Redis container and autowired `StringRedisTemplate`; you can merge these test cases into `RedisStreamIntegrationTest` from the previous section.

**This verifies the infrastructure pending/ACK contract**, not that the business handler committed. The next sections add crash and side-effect simulation.

### 9.3. Separate Two Assertion Categories

- **Infrastructure assertion:** `XPENDING` drops, `XACK` returns 1 then 0.
- **Business assertion:** database side effects committed **before** ACK; retries do not duplicate the outcome.

Checking only infrastructure still allows premature ACKs. Checking only the database lets pending entries pile up in the group for hours.

## 10. Testing Claim and Recovery in Java

Spring Data Redis exposes `claim(...)` matching Redis `XCLAIM` in supported versions. Example transferring a pending entry to another consumer:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.data.redis.connection.stream.Consumer;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.ReadOffset;
import org.springframework.data.redis.connection.stream.RecordId;
import org.springframework.data.redis.connection.stream.StreamOffset;
import org.springframework.data.redis.core.StreamReadOptions;

@Test
void anotherConsumerCanClaimUnackedEntry() {
    String stream = "stream:test:orders:" + UUID.randomUUID();
    String group = "order-workers";

    RecordId id = redis.opsForStream().add(
            stream, Map.of("eventId", "evt-unacked"));
    redis.opsForStream().createGroup(
            stream, ReadOffset.from("0-0"), group);

    List<MapRecord<String, Object, Object>> delivered =
            redis.opsForStream().read(
                    Consumer.from(group, "worker-a"),
                    StreamReadOptions.empty().count(1),
                    StreamOffset.create(
                            stream, ReadOffset.lastConsumed()));

    assertNotNull(delivered);
    assertEquals(1, delivered.size());

    // Simulate worker-a crash: DO NOT call XACK.
    assertEquals(
            1L,
            redis.opsForStream().pending(
                    stream, group).getTotalPendingMessages());

    List<MapRecord<String, Object, Object>> claimed =
            redis.opsForStream().claim(
                    stream,
                    group,
                    "worker-b",
                    Duration.ZERO,  // Use only in controlled tests.
                    id);

    assertEquals(1, claimed.size());
    assertEquals(id, claimed.get(0).getId());

    // Claiming does not automatically ACK.
    assertEquals(
            1L,
            redis.opsForStream().pending(
                    stream, group).getTotalPendingMessages());

    // Assume worker-b completed business processing successfully.
    Long acked = redis.opsForStream()
            .acknowledge(stream, group, id);
    assertEquals(1L, acked);
}
```

This test illustrates `claim`'s contract; exact signatures and generic types must match your project's Spring Data Redis version. When using Redis/driver versions with `XAUTOCLAIM`, add dedicated integration tests for scan cursors and min-idle thresholds.

Note: `Duration.ZERO` simply **skips unnecessary waiting in tests**. In real environments, claiming immediately can cause two workers to process the same message while the original owner is simply busy rather than dead.

### Why Does Claiming Not Reduce the Pending Count?

The PEL continues tracking unACKed events. `XCLAIM` updates ownership and idle bookkeeping; afterward, a handler still needs to process and `XACK`. Concluding a claim failed just because pending count stays `1` is a semantic misunderstanding.

Inspect the owner via detailed `XPENDING` or `XINFO CONSUMERS`, and verify the ID in the claim result.

## 11. Testing That Reading New Messages Does Not Auto-Redeliver Pending Ones

A common bug:

```text
worker-a reads e1
worker-a crashes before ACK
worker-b repeatedly calls XREADGROUP ... >
worker-b never sees e1
```

This is expected Redis behavior: `e1` stays pending under consumer A.

A test should confirm:

1. Worker A receives `e1` without ACKing.
2. Worker B reads `>` and does not receive `e1` as a “new message.”
3. The PEL still holds `e1`.
4. Worker B uses `XCLAIM`/`XAUTOCLAIM` and receives `e1`.
5. B ACKs `e1` after processing.

Never use `BLOCK 0` to prove step 2: the test will hang forever. Use non-blocking polls or short bounded blocks and assert an empty result:

```java
List<MapRecord<String, Object, Object>> next =
        redis.opsForStream().read(
                Consumer.from(group, "worker-b"),
                StreamReadOptions.empty().count(10),
                StreamOffset.create(
                        stream, ReadOffset.lastConsumed()));

boolean nothingNew = next == null || next.isEmpty();
// Assert nothingNew == true when no new events arrived.
```

For callers reading streams outside a consumer group, offset semantics differ; do not apply `XREADGROUP` test rules to plain `XREAD`.

## 12. Testing ACK After Commit, Not Immediately After Receipt

A business consumer normally follows this flow:

```text
XREADGROUP
    |
    v
Validate payload
    |
    v
Start DB transaction
    |
    v
Apply side effect
    |
    v
Commit DB successfully
    |
    v
XACK Redis
```

If ACK runs **before** side effects actually commit, a crash drops the event from the PEL even though business work never completed.

### 12.1. Synchronous Consumer Example

```java
import java.util.List;

import org.springframework.data.redis.connection.stream.Consumer;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.ReadOffset;
import org.springframework.data.redis.connection.stream.StreamOffset;
import org.springframework.data.redis.core.StreamReadOptions;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderStreamWorker {

    private final StringRedisTemplate redis;
    private final OrderEventHandler handler;

    public OrderStreamWorker(
            StringRedisTemplate redis,
            OrderEventHandler handler) {
        this.redis = redis;
        this.handler = handler;
    }

    public int pollAndProcess(
            String stream, String group, String consumerName) {

        List<MapRecord<String, Object, Object>> batch =
                redis.opsForStream().read(
                        Consumer.from(group, consumerName),
                        StreamReadOptions.empty().count(10),
                        StreamOffset.create(
                                stream, ReadOffset.lastConsumed()));

        if (batch == null || batch.isEmpty()) {
            return 0;
        }

        int acknowledged = 0;

        for (MapRecord<String, Object, Object> record : batch) {
            // Handler must return successfully only after side effects commit.
            handler.handle(record.getValue());

            Long count = redis.opsForStream()
                    .acknowledge(stream, group, record.getId());

            if (Long.valueOf(1L).equals(count)) {
                acknowledged++;
            }
        }

        return acknowledged;
    }
}
```

Interface:

```java
import java.util.Map;

public interface OrderEventHandler {
    void handle(Map<Object, Object> payload);
}
```

When `handler` throws an exception, ACK for that record is skipped. Note, however, that the entire batch was already delivered by Redis before the `for` loop began; if the handler fails on the second item, subsequent items in that batch are also pending. Recovery must process all pending entries, not only the one that threw.

### 12.2. Assertions with a Failing Handler

Use a simulated failing handler:

```java
OrderEventHandler failingHandler = payload -> {
    throw new IllegalStateException("DB unavailable");
};
```

After invoking `pollAndProcess(...)`, assert:

- The exception propagates per contract.
- Delivered yet unACKed events remain in the PEL.
- No `finally` block accidentally ACKs regardless of success or failure.
- When retried with a healthy handler, events are recovered and ACKed.

**Asserting only that the method threw an exception is not enough.** Verify the PEL and confirm business side effects were not marked complete.

## 13. Testing Crash After Commit Before ACK

This is the foundational scenario of **at-least-once** delivery:

```text
Worker A:
    XREADGROUP e1
    DB INSERT/UPDATE succeeds
    DB COMMIT succeeds
    process crashes before XACK e1

Worker B:
    reclaims e1
    re-runs business handler
```

If the business handler simply increments a counter:

```sql
UPDATE summary SET paid_count = paid_count + 1;
```

then `e1` increments `paid_count` twice. Redis does not know the database transaction committed; keeping `e1` in the PEL is proper Redis behavior.

### 13.1. Designing Idempotency to Test

An event carries a unique business ID:

```json
{
  "eventId": "evt-001",
  "orderId": "order-42",
  "type": "ORDER_PAID",
  "version": 3
}
```

Inside the **same database transaction**, the handler:

1. Checks whether `eventId` is already recorded.
2. If not, applies the side effect.
3. Inserts `eventId` into `processed_events` protected by a unique constraint.
4. Commits the transaction.
5. Then ACKs Redis.

Sample schema:

```sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
```

Depending on SQL dialect, use insert-if-absent or handle unique violations cleanly. Never do `SELECT exists` followed by `INSERT` in two separate transactions and assume two concurrent consumers are protected.

### 13.2. Assertions Required

A crash-after-commit test can verify:

| Step | Business State | PEL |
|---|---|---|
| Worker A receives `e1` | Unchanged | Contains `e1` |
| Handler A commits | Changed once | Still contains `e1` |
| A crashes before ACK | Still accurate | Still contains `e1` |
| B claims `e1` | Still accurate | Contains `e1`, owner B |
| Handler B reprocesses `e1` | No second side effect | Still contains `e1` |
| B ACKs successfully | Still accurate | No longer contains `e1` |

The goal is not “handler B is never invoked.” At-least-once systems **may redeliver**; the guarantee to verify is that **business effects are never applied twice**.

## 14. Testing Multiple Events, Partial ACKs, and Processing Order

Suppose a batch contains three messages:

```text
e1 -> processed successfully -> XACK e1
e2 -> processing failed      -> DO NOT ACK
e3 -> not yet processed      -> already delivered by XREADGROUP
```

Afterward, both `e2` and `e3` remain in the PEL. Group state and the PEL include entries **delivered even though the handler never ran on them**, not just entries where the handler threw.

Tests should verify:

- ACKing `e1` returns `1` and removes `e1` from the PEL.
- `e2` remains pending.
- `e3` remains pending if included in the delivered batch.
- Reading new events via `>` skips `e2` and `e3`.
- Recovery fetches `e2` and `e3`, handling them per ordering/versioning rules.

If business logic demands strict ordering per order, processing `e3` ahead of `e2` can corrupt state even though Redis permits out-of-order claims and ACKs. **Delivery reliability** and **side-effect ordering** are distinct requirements.

### 14.1. Non-Contiguous ACKs Are Valid in the PEL

You can legitimately end up with:

```text
e1 pending
e2 ACKed
e3 pending
e4 ACKed
```

Do not assume ACKs happen strictly from lowest ID to highest ID. However, if an application maintains a **custom checkpoint** outside the group, it must never advance past incomplete entries in a way that drops data during replay.

Redis consumer groups maintain the PEL precisely so teams never have to “fix lag” by jumping group offsets to the tail just to make dashboards look clean.

## 15. Testing Shutdown/Restart and Recovery by Consumer Name

Two distinct cases:

### Worker Restarts with the Same Name

```text
worker-a receives e1 and e2
worker-a crashes
worker-a restarts with the same consumer name
```

It can read its own pending entries via `XREADGROUP ... 0`, reprocess, and ACK. Tests must verify startup code **actually scans pending entries**, rather than jumping straight into polling `>`.

### Replacement Worker Has a Different Name

```text
worker-a receives e1 and e2 and dies
worker-b replaces it
```

`worker-b` does not own `worker-a`'s pending entries. It must use `XCLAIM`/`XAUTOCLAIM` once the idle threshold passes.

In multi-replica deployments, consumer naming must match your ownership model. Having all instances share one consumer name makes inspecting pending work, liveness, and ownership harder, even though Redis permits duplicate names.

### Testing Controlled Shutdown

A reliable shutdown flow:

```text
Mark worker draining
          |
          v
Stop polling new batches
          |
          v
Wait for in-flight work up to deadline
          |
      +---+---+
      |       |
    Done    Timed out
      |       |
      v       v
     ACK   Leave pending
      |       |
      +---+---+
          |
          v
     Stop worker
```

Tests should simulate a shutdown timeout and verify unfinished messages stay unACKed. Never assume container `stop()` handles business draining and ACKs automatically.

## 16. Testing `XAUTOCLAIM` with Cursors and Idle Thresholds

`XAUTOCLAIM` scans the PEL to transfer entries whose idle time exceeds a threshold to another consumer.

```text
XAUTOCLAIM stream group new-consumer min-idle start COUNT N
```

Typical output includes:

- Cursor for continuing the scan.
- Claimed entries.
- On supported Redis versions, IDs whose stream entries no longer have payloads.

Tests should not call it once and declare “all messages recovered.” For large PELs, loop using the cursor and recognize that reaching the end-of-scan cursor does not mean every entry finished processing/ACKing.

### 16.1. Testing “Do Not Claim Before Threshold”

Suppose worker A runs a 5-second task. If worker B claims after 100 ms, both execute concurrently. A test can configure a high min-idle and prove the command skips newly delivered entries.

To keep tests non-flaky:

- Never `sleep(50)` expecting Redis's clock to align to the millisecond.
- Pick wide, stable thresholds and deadlines for tests.
- Keep immediate-claim tests (`min-idle 0`) separate from lease/idle-policy tests.
- Use explicit liveness/workflow markers if the architecture needs to know whether a worker is still actively healthy.

### 16.2. Testing “Claim Then ACK”

Expected progression:

```text
Before claim:
    pending owner = worker-a
    pending count = 1

After claim:
    pending owner = worker-b
    pending count = 1

After XACK:
    pending count = 0
```

This assertion layout is much cleaner than expecting pending count to drop on claim.

## 17. Testing Retention: Entries Deleted or Trimmed While Pending

Redis Streams retain entries per configured retention, not forever. A group's PEL **does not force Redis to retain payloads indefinitely**.

Example on an isolated test stream:

```bash
redis-cli XADD stream:test:retention '*' eventId e-old
redis-cli XGROUP CREATE stream:test:retention retention-workers 0
redis-cli XREADGROUP GROUP retention-workers worker-a \
    COUNT 1 STREAMS stream:test:retention '>'
```

Suppose it returned `id-old` and did not ACK. Then delete the entry in a controlled test:

```text
XDEL stream:test:retention <id-old>
```

The test then checks:

- `XRANGE` no longer holds payload `e-old`.
- PEL and recovery commands reflect the deleted entry per your Redis version's semantics.
- Workers cannot reconstruct the payload solely from the PEL.
- Monitoring alerts that a pending event lost its required payload.

With `XTRIM`, the same situation occurs if max stream length falls below producer volume while a consumer is paused.

### 17.1. Retention Must Account for the Slowest Group

Suppose:

```text
Group billing:
    processes fast, small pending list

Group analytics:
    offline for two hours, large backlog
```

If the stream trims solely around billing's progress, analytics loses unread events. Never test retention with a single group and conclude every group is safe.

Tests should simulate **slow or offline consumers** for the full policy window and verify payloads remain intact—or verify clear alerting triggers if retention is exceeded.

## 18. Testing Connection Failures and Timeouts: Never Guess an ACK

Consider this sequence:

```text
1. Redis XREADGROUP succeeds, client receives event.
2. Business handler commits successfully.
3. Client sends XACK.
4. Connection drops before receiving the reply.
```

At step 4, the client cannot tell whether `XACK` ran. Never catch a timeout and treat the event as “ACK succeeded,” and never mark business processing failed when the side effect already committed.

Tests should verify:

- Business state is tracked independently with idempotency.
- If ACK ran, the PEL no longer holds the entry; a retried ACK normally returns 0.
- If ACK did not run, the entry remains in the PEL; recovery redelivers it and the idempotent handler handles it cleanly.
- The application never treats an ACK response as a distributed transaction spanning the database.

In Redis, `XACK` clears pending tracking—it does not perform business side effects like charging money. Retrying `XACK` on the exact stream/group/ID is generally safe, yet **never interpret a `0` return from a retried ACK as proof business logic never ran**.

### Isolating Infrastructure for Redis Outage Tests

Use Testcontainers/Toxiproxy or an integration setup that can cut connections deterministically. Never shut down production Redis to test failures. When cutting connectivity:

1. Ensure workers do not ACK before the handler commits.
2. Ensure requests/workers have finite timeouts instead of hanging forever.
3. Observe distinct connection exceptions rather than mistaking them for an “empty stream.”
4. Restore Redis and run pending recovery.
5. Verify zero lost business events and zero duplicate side effects.

## 19. Testing Reactive `StreamReceiver` and Demand

Spring Data Redis provides reactive Streams APIs producing a `Flux` via `StreamReceiver`. Reactive demand only controls how many items downstream requests; **it does not guarantee records are ACKed only after side effects**.

### 19.1. `Mono`/`Flux` Completion Does Not Mean ACK

A reactive listener might consume records like:

```java
receiver.receive(
        Consumer.from(group, consumerName),
        StreamOffset.create(
                stream, ReadOffset.lastConsumed()))
    .concatMap(record ->
        processBusiness(record)
            .then(acknowledge(record)));
```

Here `processBusiness` and `acknowledge` are illustrative application methods. Choose receiver and offset APIs matching your exact Spring Data Redis version.

Assertions required:

- Business processing completed before ACK.
- If `processBusiness` errors, ACK is not called for that entry.
- Canceling the subscription mid-flight leaves unACKed entries recoverable.
- Avoid auto-ACK variants when requiring “business commit before ACK” unless you verify exact auto-ACK timing in your version.

### 19.2. `ReadOffset.latest()` Can Skip Messages Between Polls

When downstream demand hits 0, the receiver may pause polling. Resuming with `ReadOffset.latest()` can skip entries appended while polling was paused.

Test:

```text
T0: Consumer is receiving event e1.
T1: Downstream stops requesting more items.
T2: Producer XADDs e2 and e3.
T3: Downstream requests again.
T4: Verify whether e2/e3 are received under the configured offset.
```

For zero-loss workloads, test `ReadOffset.lastConsumed()` with a consumer group and pending recovery rather than defaulting to `latest`.

Note: `ReadOffset.lastConsumed()` on the new-messages path does not automatically recover previously delivered unACKed entries. Reactive tests still need a separate PEL recovery test.

## 20. Testing Concurrency: Multiple Consumers Without Premature ACKs

A concurrency integration test can use two workers reading small batches coordinated by a `CountDownLatch`:

```text
Main test:
    XADD e1..e20
    create group at 0
    release worker A and B simultaneously
    await total 20 events processed or timeout

Worker A/B:
    XREADGROUP COUNT n
    run handler
    XACK after commit
```

Assertions should check:

- Total **unique event IDs** processed successfully equals 20.
- No retained event needing processing was missed.
- Once quiescent, the group's PEL count is 0.
- When simulating crashes/recovery, there may be duplicate **attempts**, yet only one **business effect** per event ID.
- Never require each worker to process exactly 10 events; Redis distribution depends on scheduling.

If the test stores seen IDs in a `HashSet` across threads, use a concurrent set or explicit synchronization; races inside the test harness itself produce bogus failures.

### Why Not Assert “Handler Called Exactly Once”?

Redis Streams with consumer groups and recovery implement at-least-once delivery. If a worker crashes after business commit and before ACK, the event is reprocessed. Asserting “handler strictly runs once” contradicts that design goal.

Instead:

```text
handler attempts >= 1
business effects == 1
event eventually ACKed == true
```

Always enforce test deadlines so failed workers never hang the suite.

## 21. Testing Message Ordering and Consumer Groups

In Redis Streams, stream IDs are strictly ordered. However, **log entry order** does not equal **side-effect completion order** when multiple workers run concurrently.

Example:

```text
Stream:
    e1: ORDER_CREATED
    e2: ORDER_PAID
    e3: ORDER_CANCELLED

Consumer group:
    worker-a gets e1, slow
    worker-b gets e2, fast
    worker-c gets e3, fast
```

If handlers overwrite database rows without checking versions, state can be updated out of order.

Tests should verify one of these strategies:

- A single sequential consumer processes events for the same aggregate.
- Partition streams/consumers by `orderId` to preserve per-aggregate ordering.
- Check `version` before updating projections and ignore stale events.
- Enforce valid domain state transitions rather than relying on request completion order.
- During pending recovery, ensure an older event never overwrites newer state.

You do not have to force Redis to serialize all workers globally if the architecture allows parallel side effects guarded by version checks.

## 22. Testing Poison Messages and Retry Policies

A message with a malformed payload can cause handlers to fail indefinitely.

```text
XREADGROUP e-bad
    |
    v
Handler deserialization fails
    |
    v
Do not ACK
    |
    v
PEL retains e-bad
    |
    v
Recovery claim -> fails again
```

Tests should verify:

1. Poison messages are not ACKed immediately when the handler throws.
2. Retries enforce backoff or min-idle rather than spinning in a tight infinite loop.
3. Delivery/attempt counts are capped per application policy.
4. Once capped, the system writes a **dead-letter record** to a durable store.
5. Only after completing the dead-letter write does it ACK the source event per workflow rules.
6. The Redis PEL does not accumulate poison messages forever without alerts.
7. Replaying from the DLQ enforces proper idempotency and authorization.

### Target Flow Example

```text
event e-bad:
    attempt 1 -> invalid payload
    attempt 2 -> invalid payload
    attempt 3 -> invalid payload
    -> XADD dlq:orders ...
    -> XACK source e-bad
```

Note that writing to the DLQ and ACKing the source are two distinct steps; crashing between them can produce a duplicate DLQ entry on retry. Tests should ensure the same `eventId` does not cause unintended duplicate side effects.

## 23. Testing Trimming, Deletion, and Retention Policies

To test retention properly, distinguish:

- **Undelivered events:** still in stream or trimmed?
- **Delivered, unACKed events:** payload still available for recovery or deleted?
- **ACKed events:** entries kept in stream for other groups to read?
- **Multiple consumer groups:** does the slowest group still have enough history?

Test with `MAXLEN`:

```bash
redis-cli XADD stream:test:bounded MAXLEN ~ 1000 '*' eventId e-1
```

The `~` triggers approximate trimming for performance. In integration tests needing exact counts, use **exact** trimming configurations or explicitly `XDEL` an ID to simulate payload loss.

Using approximate trimming and asserting `XLEN == 1000` strictly creates flaky or invalid tests.

## 24. Testing Recreated Consumer Groups or Misaligned Offsets

Some deployment scripts run:

```bash
redis-cli XGROUP CREATE stream:orders:v1 order-workers '$' MKSTREAM
```

and start reading `>`. If the stream already holds backlog events the group must process, those events are skipped.

Scenarios to test:

- A new group starting at `0` reads retained history.
- A new group starting at `$` receives only events added afterward.
- Restarting an existing group **never accidentally recreates it from scratch**.
- If a group already exists, creation returns `BUSYGROUP`; idempotent initialization must handle that intentionally.
- Never delete/recreate groups on every startup just to dodge `BUSYGROUP`: doing so wipes the PEL and delivery progress.
- Never run `XGROUP SETID` to hide lag without planning for pending entries, duplicates, and skips.

**Group lifecycle is durable system state**, not ephemeral setup to reset on every deployment.

## 25. Testing Pending Ownership and Operational Metrics

Redis provides rich inspection commands:

```bash
redis-cli XINFO STREAM stream:orders:v1
redis-cli XINFO GROUPS stream:orders:v1
redis-cli XINFO CONSUMERS stream:orders:v1 order-workers
redis-cli XPENDING stream:orders:v1 order-workers
redis-cli XPENDING stream:orders:v1 order-workers - + 100
```

In a test with consumers A and B, verify:

- Event `e1` is pending under A after `XREADGROUP`.
- Claiming `e1` to B updates the owner.
- Delivery count and idle time update per Redis rules.
- Total pending count does not decrease on claim.
- `XACK` after processing reduces pending count.
- When a consumer goes inactive, stale pending entries can still be discovered and reclaimed.

Never confuse **zero group lag** with **zero pending entries**. A group can have delivered up to the end of the stream while thousands of events remain unACKed.

### Metrics to Keep Separate

| Metric | Meaning |
|---|---|
| `stream_append_total` | Events written to Redis by producers |
| `stream_delivered_total` | Events delivered to the group |
| `stream_ack_success_total` | Events successfully ACKed |
| `stream_pending_count` | Delivered, unACKed events |
| `stream_pending_oldest_age` | Age of the oldest pending entry |
| `stream_claim_total` | Number of event reclaims |
| `stream_handler_attempt_total` | Handler invocations, including retries |
| `stream_business_success_total` | Business side effects completed |
| `stream_duplicate_event_total` | Previously processed event IDs skipped |
| `stream_dlq_total` | Messages routed to DLQ |
| `stream_recovery_lag` | Delay recovering pending entries after failure |
| `stream_trimmed_pending_total` | Pending entries missing payloads (if observable) |

Never attach `eventId` as a metric label across all events, as cardinality explodes. Label by stream/group name, event type, and error code; keep `eventId` details inside controlled logs and traces.

## 26. Common Mistakes When Testing

| Mistake in Tests or Code | Consequence | Fix |
|---|---|---|
| Asserting only that listener received message | Fails to prove ACK or recovery | Assert PEL and business effects |
| Reading event and ACKing before handler | Crash loses retry capability | ACK after commit |
| Expecting worker B to read A's pending via `>` | Misunderstands Redis semantics | Use claim/recovery |
| Creating group at `$` while expecting history | Misses pre-existing events | Create from `0` when history matters |
| Fixed consumer names in parallel tests | PEL and ownership collide | Isolate streams/groups/consumers |
| Very short `Thread.sleep` waiting for events | Flaky tests | Explicit latches/futures/deadlines |
| Testing immediate claim with long prod min-idle | Slow and unstable tests | Use `Duration.ZERO` when testing claim contract |
| Using min-idle 0 in production | Two workers process the same message | Tune appropriate idle/lease thresholds |
| Asserting pending count is 0 after `XCLAIM` | Confuses claim with ACK | Assert owner changed and pending persisted |
| Reading `XREADGROUP ... >` on restart and skipping PEL | Old pending entries stay stranded | Startup/periodic pending recovery |
| Ignoring `XAUTOCLAIM` cursor | Misses pending entries in later batches | Loop over cursor with bounded cap |
| Assuming ACK deletes payload | Broken retention tests | Separate `XACK` from `XDEL` |
| Trimming payloads yet expecting claim recovery | Deleted data cannot be recreated | Maintain adequate retention and alerts |
| Asserting workers split load evenly | Scheduling does not guarantee 50/50 split | Assert unique ID total and invariants |
| Asserting handler runs strictly once after crash | Violates at-least-once model | Assert business effect occurs once |
| Leaving listeners/subscriptions open across tests | Later tests capture stray events | Manage lifecycle and cleanup |
| Only mocking Redis for PEL tests | Misses real server semantics | Integration test against real Redis |
| Using production Redis for trim/claim tests | Corrupts live data | Dedicated Testcontainers/test Redis |

## 27. Recommended Testing Workflow

```text
Start: Need to verify consumer group
                     |
                     v
          Create isolated test stream
                     |
                     v
           XADD event with eventId
                     |
                     v
       Create group at intentional offset
                     |
                     v
            XREADGROUP ... >
                     |
              +------+------+
              |             |
          Handler OK   Handler errors/crashes
              |             |
              v             v
       Commit side effect  Do not ACK
              |             |
              v             v
             XACK       Check XPENDING
              |             |
              v             v
        PEL drops      Same-consumer replay
                         or XCLAIM/
                          XAUTOCLAIM
                              |
                              v
                       Idempotent handler
                              |
                              v
                             XACK
                              |
                              v
                     Assert business state
                      and pending = 0
                              |
                              v
                  Test retention, failover,
                  multiple groups, and concurrency
```

Layer tests in increasing complexity:

1. **Unit tests** for payload mapping, idempotency policies, and ACK-after-success rules; mock handlers and gateways as needed.
2. **Real Redis integration tests** for `XADD`, group offsets, `XREADGROUP`, `XPENDING`, `XACK`, `XCLAIM`, and `XAUTOCLAIM`.
3. **Real database integration tests** for business transactions and `eventId` deduplication.
4. **Failure/chaos tests** for crash-before-ACK, crash-after-commit, Redis disconnects, failover, retention, and multi-replica runs.

Tests do not have to form one massive end-to-end scenario. Small independent tests clarify whether a failure lives in the protocol, API, business handler, or infrastructure.

## 28. End-to-End Scenario: Processing `ORDER_PAID`

Suppose an app uses:

```text
Stream: stream:orders:v1
Group:  billing-projections
Consumers: billing-a, billing-b
```

Each `ORDER_PAID` event updates a summary table, and the database has a `processed_events` table ensuring revenue is never counted twice.

### Scenario 1: Normal Success

```text
XADD e1
billing-a XREADGROUP e1
DB commits side effect and processed_events(e1)
billing-a XACK e1
XPENDING == 0
```

Assertions:

- `processed_events` holds `e1` exactly once.
- Total revenue increased once for `e1`.
- PEL no longer holds `e1`.
- Entry `e1` can remain in the stream until retention removes it.

### Scenario 2: DB Fails Before Commit

```text
XADD e2
billing-a XREADGROUP e2
DB rolls back / handler errors
NO XACK
billing-b claims e2 after idle threshold
DB commits e2
billing-b XACK e2
```

Assertions:

- Before claim, `e2` stays pending.
- After claim, owner moves to B while still pending.
- After commit and ACK, pending drops.
- Business effect for `e2` occurs exactly once.

### Scenario 3: Crash After Commit Before ACK

```text
XADD e3
billing-a XREADGROUP e3
DB commits e3
Crash before XACK
billing-b claims e3
Handler B detects e3 already processed
B does not add revenue a second time
B XACKs e3
```

Assertions:

- Handler can be retried.
- Business table does not increment twice.
- Final PEL hits 0.
- Do not let “replay” trigger duplicate emails/invoices if those side effects also require idempotency.

### Scenario 4: Offline Longer Than Retention

```text
billing-a/b stop reading
producer keeps XADDing
stream trims via MAXLEN
consumers return
```

Assertions:

- The system detects a gap of unprocessable/missing payloads.
- Does not report “all caught up” merely because group lag dropped.
- Has a recovery path from an event log/authoritative store if business rules forbid data loss.
- Retention policy must expand or storage architecture must change if this gap is unacceptable.

## 29. Consumer Group Testing Exit Criteria

A system relying on Redis Streams for critical events should prove these invariants:

1. **New events are read** starting at the group offset intended by design.
2. **Delivery does not equal completion:** delivered entries stay in the PEL until ACKed.
3. **ACK happens only after success** at the defined commit boundary.
4. **Duplicate ACKs cause no duplicate work**, and returning `0` is understood accurately.
5. **Crash before ACK recovers** from pending entries while payloads exist.
6. **New workers do not only read `>`**, they also claim stale pending entries.
7. **Claim is never mistaken for ACK**; ownership and pending state are checked separately.
8. **Crash after commit before ACK creates no double side effects** thanks to idempotency.
9. **Multiple groups track progress independently** without sharing ACKs.
10. **Retention spans offline windows**, retries, and peak-load recovery.
11. **Tests use isolation and deadlines**, avoiding infinite blocks or lucky scheduling order.
12. **Metrics separate delivered, processed, ACKed, and pending**, avoiding misleading single-lag conclusions.

## 30. Conclusion

**Testing consumer groups, acknowledgments, and pending entries** in Spring Data Redis requires verifying both **Redis state** and **business outcomes**. `XREADGROUP` creates a processing responsibility, `XPENDING` reveals unfinished responsibilities, `XCLAIM`/`XAUTOCLAIM` hand over responsibilities after failures, and `XACK` confirms completion for that group—without deleting stream data or committing database transactions.

A dependable suite deliberately exercises critical failure windows: **read-then-crash, handler failure, commit-then-crash-before-ACK, new consumers reclaiming pending entries, and stream trimming under backlog**. At the same time, tests must verify business-layer idempotency: events may arrive more than once, yet business effects must never repeat unintentionally.

**Core principle:** Do not ask only “how many messages did the consumer receive?” Ask **“which messages were delivered, which remain pending, which committed successfully, and what happens to each message when a worker disappears?”** Once those questions are verified against real Redis with explicit business assertions, the system has a solid foundation for operating Redis Streams consumer groups safely.
