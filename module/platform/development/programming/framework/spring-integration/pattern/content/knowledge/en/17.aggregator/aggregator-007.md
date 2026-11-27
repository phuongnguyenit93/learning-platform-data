# Expiring Groups and Handling Incomplete Parts

> **Chapter:** Aggregator  
> **Module:** `SPRING_INTEGRATION_PATTERN` — learning to implement Enterprise Integration Patterns with Spring Integration to build loosely coupled, extensible message flows; practicing Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation, while testing and observing branches. This lesson focuses on **message group expiration** and **how to handle unarrived or incomplete parts** without corrupting business results.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain how an Aggregator **message group** is formed, stored, released, and expired; distinguish **successful release**, **expiration due to timeout**, **removing completed groups**, and **reaping long-lived groups in `MessageStore`**.
2. Design policies for **complete parts, missing parts, zero parts, late arrivals, duplicates, and partial failures**, instead of assuming Aggregator merely counts messages.
3. Understand the roles of `correlationStrategy`, `releaseStrategy`, `groupTimeout`, `sendPartialResultOnExpiry`, `expireGroupsUponCompletion`, and the `MessageGroupStoreReaper` mechanism within their proper scopes.
4. Build a Spring Integration flow using **Splitter → independent handlers → Aggregator** and produce a `BatchOutcome` that clearly expresses **completeness** and **business outcome**.
5. Handle **partial results**, callback timeouts, retries, idempotency, late arrivals, group tombstones, and memory/backpressure limits.
6. Test complete scenarios as well as expirations, zero-reply groups, duplicates/out-of-order arrivals, restart crashes, and non-repeating side effects.

## 2. The Problem: Three Inventory Check Requests, Only Two Replies Received

Order `ORD-801` has three line items. Splitter creates three independent requests to check inventory across different warehouses:

~~~text
Batch ORD-801 / execution RUN-001
  expected item IDs = [LINE-1, LINE-2, LINE-3]
       |
       v
   Splitter (3 child requests)
       |
       +--> LINE-1 -> Inventory A -> reply RESERVED
       +--> LINE-2 -> Inventory B -> reply NOT_AVAILABLE
       +--> LINE-3 -> Inventory C -> no reply
       |
       v
   Aggregator receives 2/3 replies
~~~

If Aggregator only releases when all three results arrive, it can hold the group indefinitely when `LINE-3` is lost or its consumer fails to reply. Conversely, if it merely counts **two** results and treats the whole batch as successful, the application skips a critical order line.

**Group expiration** answers the question: *After a deadline when the group has not yet met release conditions, what should be done with the group and the messages already received?*

~~~mermaid
flowchart TD
    S["Splitter: 3 requests"] --> A["Aggregator group RUN-001"]
    R1["Reply LINE-1"] --> A
    R2["Reply LINE-2"] --> A
    R3["LINE-3: missing"] -.-> A
    A --> D{"All replies present?"}
    D -->|Yes| C["Release: ALL_REPLIES"]
    D -->|No| T{"Deadline / timeout?"}
    T -->|No| W["Hold group, keep waiting"]
    T -->|Expired| P["Expire: PARTIAL / ERROR / RECONCILE"]
    W --> D
~~~

An illustrative partial result:

~~~json
{
  "batchId": "ORD-801",
  "executionId": "RUN-001",
  "expectedCount": 3,
  "receivedCount": 2,
  "completeness": "PARTIAL_EXPIRED",
  "businessOutcome": "INCOMPLETE",
  "missingItemIds": ["LINE-3"]
}
~~~

This result **does not** state that `LINE-3` is out of stock, nor does it declare that the inventory check at warehouse C failed. It only states that **no valid reply for that item arrived before the group expired**.

## 3. States That Must Be Distinguished

| Concept | Meaning | Example | What Must Not Be Inferred |
| --- | --- | --- | --- |
| **Group created/open** | At least one message has been added to the group | First reply for `RUN-001` | The entire batch started successfully |
| **Group complete** | Release strategy determined all required parts arrived per contract | LINE-1, LINE-2, LINE-3 all present | All warehouses returned `RESERVED` |
| **Group released** | Aggregator produces output from the group | `BatchOutcome` emitted | Final consumer committed business state |
| **Group expired** | Group exceeded deadline per timeout/expiry policy | Received 2/3 before deadline | Remaining parts failed at business level |
| **Partial result** | Output contains information from a subset of expected parts | 2/3 item replies | Result can substitute for a complete result |
| **Group removed** | Group data deleted/freed from store | After completion or expiry | Late replies will be recognized as old |
| **Group tombstone** | Record of closed group stored separately or via store policy | `RUN-001: CLOSED` | Group key can be safely reused immediately |

**Two independent axes:** *completeness* and *business outcome*. A group can be **complete** while one item returned `NOT_AVAILABLE`, or **incomplete** even though both received items succeeded.

| Completeness | Business Outcome | Example |
| --- | --- | --- |
| `ALL_REPLIES` | `ALL_SUCCEEDED` | All three replies, all RESERVED |
| `ALL_REPLIES` | `SOME_FAILED` | All three replies, one NOT_AVAILABLE |
| `PARTIAL_EXPIRED` | `INCOMPLETE` | Only two replies, remaining item unknown |
| `NO_REPLIES_TIMEOUT` | `INCOMPLETE` | Zero replies; needs a deadline outside Aggregator if no group exists |

Do not collapse all four cases into a single Boolean `success`.

## 4. Lifecycle of an Aggregator Message Group

An Aggregator typically consists of these logical components:

1. **Correlation strategy:** determines which group a reply belongs to.
2. **Message group store:** holds waiting messages alongside group metadata.
3. **Release strategy:** decides when output emission conditions are met.
4. **Output processor:** builds the aggregated result from messages in the group.
5. **Expiry/timeout policy:** decides what to do when an incomplete group becomes overdue.
6. **Group cleanup:** manages group metadata, resources, and post-release/post-expiry state.

~~~mermaid
flowchart LR
    IN["Item replies"] --> COR["Correlation strategy"]
    COR --> G["MessageGroupStore: group RUN-001"]
    G --> REL{"Release strategy"}
    REL -->|Complete| O["Output processor: complete"]
    REL -->|Incomplete| WAIT["Waiting group"]
    WAIT -->|Timeout| EXP{"Expiration policy"}
    EXP -->|Send partial| PO["Output processor: partial"]
    EXP -->|No partial| ER["Discard / error / observe"]
    O --> CLEAN["Cleanup / tombstone"]
    PO --> CLEAN
    ER --> CLEAN
~~~

### 4.1. `release` Differs from `expire`

**Release:** policy sees conditions are met—for example, **exactly one valid result received for each expected item**. Aggregator builds the outcome and sends it downstream.

**Expire:** release conditions were not met, so timeout, expiration, or group cleanup intervened. Depending on configuration, the group may emit a **partial result** or go to a discard/error/quarantine path. Never describe every expiration as a successful release.

### 4.2. `expireGroupsUponCompletion` Differs from Group Timeout

`expireGroupsUponCompletion` controls **how the group is handled after a normal completion release**. It is not a "30-second wait timer." If the group is deleted immediately upon completion, a late/duplicate reply with the same correlation key can create a **new group**, unless a closed-group check prevents it.

`groupTimeout` is an Aggregator timeout mechanism for **incomplete groups**. Understand its trigger semantics per version/configuration: do not assume it always means "fixed deadline from when the batch was created" unless the application sets that up.

### 4.3. `MessageGroupStoreReaper` Differs from Per-Group Timeout

`MessageGroupStoreReaper` is for **cleaning up/expiring stale groups in the message group store** on a scan schedule. It can be necessary to clean up long-lived groups or when using a persistent store; however, it **does not replace** an explicit business deadline rule and can lag by up to the scan interval.

For example, if the requirement is "every order must have an outcome at or before 12:00:00Z," a reaper job scanning once per minute **must not be treated as an exact wall-clock deadline guarantee**.

## 5. Four Policies When a Group Expires

Choose a policy based on the **business impact** of each part.

| Policy | Behavior When Parts Missing | When Appropriate | Risk |
| --- | --- | --- | --- |
| **Emit partial result** | Return available results + missing list | Dashboards, stats, progress reports, domains accepting incomplete | Consumers treat partial as complete |
| **No partial; send error/timeout** | Close group with controlled error outcome | Payments, atomic contract orders, approvals requiring all sources | Caller must receive reply/error rather than waiting forever |
| **Retry/reconcile before closing** | Query unresponsive items, resend idempotently | Outbound calls with network errors and unknown outcome | Duplicate side effects if retry is unsafe |
| **Hold state / route to manual review** | Pause in pending state for operator/worker handling | Long-running workflows requiring manual decisions | `MessageGroupStore` and state must be durable, with TTL/monitoring |

**Selection rule:** for inventory checks, partial may yield `INCOMPLETE` and trigger a re-query. For "charge payment successfully after all three steps," downstream must never treat a partial result as a completed commit.

### 5.1. What Is `sendPartialResultOnExpiry(true)` For?

When using Aggregator with a suitable expiration mechanism, `sendPartialResultOnExpiry(true)` allows **passing the messages accumulated in the group to the output processor when the group expires**. The output processor must produce a contract **explicitly marking missing data**, never treating a partial message list as a full group.

In the demo below, we assign `PARTIAL_EXPIRED` when the received item ID set does not equal the expected item ID set. That is an intentional convention of the **illustrative flow**, not a guarantee that every `MessageGroup` automatically carries a header named `partial`.

### 5.2. What Does `sendPartialResultOnExpiry(false)` Mean?

When not emitting partial results, you must design **how to record and report errors/close the workflow**. Do not simply disable partial and assume Gateway will receive `TimeoutResponse`; no output may be emitted and the caller may wait until its own timeout.

An application may need a handler that records `BatchTimedOut` to a state store, emits a dedicated error/timeout event, or routes to a reconciliation queue. Test specifically against the expiration/discard behavior of your Spring Integration version.

### 5.3. Expiring a "Group" Is Not Expiring "Each Child"

If a child reply arrives at 31 seconds while the group deadline is 30 seconds, the question must be resolved at the **batch level**: accept the late reply to update the final result, trigger compensation, or discard with audit? Do not place a per-child timeout Filter and treat it as a complete Aggregator expiry policy.

## 6. Designing the Data Contract: Know Exactly What Is Awaited

`expectedCount=3` alone is not enough to control duplicates. For example, receiving `LINE-1` twice and `LINE-2` once gives **three messages**, yet `LINE-3` is still missing.

To avoid miscounting, know the **expected ID list** or at least a stable item identifier. In this lesson, each batch has a contract:

~~~text
GroupContract
  executionId = RUN-001         // One specific execution
  batchId = ORD-801             // Business order ID
  expectedItemIds = [LINE-1, LINE-2, LINE-3]

ItemReply
  batchId = ORD-801
  itemId = LINE-1
  outcome = RESERVED
  reasonCode = null
~~~

**Why have both `batchId` and `executionId`?** Order `ORD-801` may be reprocessed due to a valid new request or replay. Using only `batchId` for correlation could mix two executions together. `executionId` identifies the **aggregation session**; side-effect idempotency needs a separate key per contract, such as `(commandId, lineId, operation)`.

### 6.1. Immutable Java 17 Records

~~~java
import java.util.Objects;
import java.util.Set;
import java.util.List;

enum ItemState {
    RESERVED, NOT_AVAILABLE, FAILED
}

record GroupContract(
    String executionId,
    String batchId,
    Set<String> expectedItemIds
) {
    GroupContract {
        if (executionId == null || executionId.isBlank()
                || batchId == null || batchId.isBlank()) {
            throw new IllegalArgumentException("Group identity missing");
        }
        expectedItemIds = Set.copyOf(
            Objects.requireNonNull(expectedItemIds, "expectedItemIds"));
        if (expectedItemIds.isEmpty()) {
            throw new IllegalArgumentException(
                "Empty group requires a separate ingress outcome");
        }
        if (expectedItemIds.stream().anyMatch(
                id -> id == null || id.isBlank())) {
            throw new IllegalArgumentException("Invalid expected item ID");
        }
    }
}

record ItemReply(
    String batchId,
    String itemId,
    ItemState state,
    String reasonCode
) {
    ItemReply {
        if (batchId == null || batchId.isBlank()
                || itemId == null || itemId.isBlank()) {
            throw new IllegalArgumentException("Reply identity missing");
        }
        Objects.requireNonNull(state, "state");
    }
}

enum CompletionState {
    ALL_REPLIES,
    PARTIAL_EXPIRED
}

enum BusinessOutcome {
    ALL_SUCCEEDED,
    SOME_FAILED,
    INCOMPLETE
}

record BatchOutcome(
    String executionId,
    String batchId,
    int expectedCount,
    int receivedCount,
    CompletionState completeness,
    BusinessOutcome businessOutcome,
    List<ItemReply> replies,
    List<String> missingItemIds
) {
    BatchOutcome {
        replies = List.copyOf(replies);
        missingItemIds = List.copyOf(missingItemIds);
    }
}
~~~

These `record` definitions describe an in-JVM demo contract. If `ItemReply` crosses Kafka/AMQP/HTTP, you need appropriate **schemas and header mapping** to reconstruct `GroupContract` safely at ingress; never assume a Java record placed in a header serializes everywhere automatically.

### 6.2. Trust Boundary of the Expected List

`expectedItemIds` must be determined where the batch is authorized to be formed (e.g., after validation/Splitter), not taken from a reply self-reported by an external service. If a consumer could alter `expectedCount` from 3 down to 1, it could force the Aggregator to release prematurely.

In production, a more robust approach is storing an **immutable `GroupContract` in an authoritative store** keyed by `executionId` and validating every reply against that record. Headers in the demo merely illustrate the algorithm in internal tests.

## 7. Release Logic: All Expected Item IDs, Not Blind Message Counting

A message group may contain multiple replies, even duplicates from redelivery. We should release when **all expected items have valid replies**, not when `group.size() >= expectedCount`.

~~~java
import java.util.HashSet;
import java.util.Set;

import org.springframework.integration.store.MessageGroup;
import org.springframework.messaging.Message;

final class BatchGroupLogic {
    private BatchGroupLogic() {}

    static GroupContract contract(MessageGroup group) {
        Object value = group.getOne()
            .getHeaders().get("batchContract");
        if (!(value instanceof GroupContract contract)) {
            throw new IllegalArgumentException("Batch contract missing");
        }
        return contract;
    }

    static boolean allExpectedReceived(MessageGroup group) {
        GroupContract contract = contract(group);
        Set<String> ids = new HashSet<>();

        for (Message<?> message : group.getMessages()) {
            if (!(message.getPayload() instanceof ItemReply reply)
                    || !contract.batchId().equals(reply.batchId())
                    || !contract.expectedItemIds().contains(reply.itemId())) {
                // Invalid data must be blocked at ingress;
                // never treat it as proof the group is complete.
                return false;
            }
            ids.add(reply.itemId());
        }

        return ids.equals(contract.expectedItemIds());
    }
}
~~~

**Do not push full validation/authorization logic into the release strategy.** This component only decides whether the group is complete. Before letting a reply enter Aggregator, validate `executionId`, verified source/tenant, `itemId` membership in the expected set, and contract/schema validity. Invalid replies belong in an error/rejection flow rather than sitting in the group forever.

### 7.1. Duplicates and Conflicting Duplicates

If `LINE-1` is returned twice with the same outcome, downstream can deduplicate by `itemId`. However, if the second reply says `FAILED` while the first said `RESERVED`, the system has a **conflict**. Never randomly pick whichever reply "arrived last" and treat it as valid.

You should:

1. Define a reply idempotency key at ingress, such as `(executionId, itemId, attempt/operation)`.
2. Apply a **first committed result wins**, higher version/attempt wins, or controlled aggregate state policy—per contract.
3. Log alerts and reconcile when two replies share a key yet have conflicting content.
4. Block unnecessary duplicates before Aggregator or handle them explicitly in the output processor.

### 7.2. Are Sequence Headers Enough?

`correlationId`, `sequenceNumber`, and `sequenceSize` generated by Splitter can assist Aggregator. However, `sequenceSize=3` **does not prove** three distinct items arrived. When deduplication and per-SKU/per-line reconciliation are required, business item IDs are still necessary.

Furthermore, after crossing a broker or Transformer, sequence headers may be lost or remapped without metadata propagation configuration. Never rely on grouping metadata surviving every boundary untested.

## 8. Output Processor: Distinguishing Complete, Partial, and Business Failure

Upon release or expiry, the output processor builds a `BatchOutcome` containing the received replies and missing IDs. The example below extends `BatchGroupLogic` (place these methods in that same class when using them in a project):

~~~java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.integration.store.MessageGroup;
import org.springframework.messaging.Message;

static BatchOutcome toOutcome(MessageGroup group) {
    GroupContract contract = contract(group);
    Map<String, ItemReply> unique = new LinkedHashMap<>();

    for (Message<?> message : group.getMessages()) {
        ItemReply reply = (ItemReply) message.getPayload();
        if (!contract.batchId().equals(reply.batchId())
                || !contract.expectedItemIds().contains(reply.itemId())) {
            throw new IllegalStateException("UNEXPECTED_REPLY_IN_GROUP");
        }

        ItemReply old = unique.putIfAbsent(reply.itemId(), reply);
        if (old != null && !old.equals(reply)) {
            throw new IllegalStateException("CONFLICTING_DUPLICATE_REPLY");
        }
    }

    List<String> missing = contract.expectedItemIds().stream()
        .filter(id -> !unique.containsKey(id))
        .sorted()
        .toList();

    CompletionState completeness = missing.isEmpty()
        ? CompletionState.ALL_REPLIES
        : CompletionState.PARTIAL_EXPIRED;

    BusinessOutcome business;
    if (!missing.isEmpty()) {
        business = BusinessOutcome.INCOMPLETE;
    } else if (unique.values().stream().allMatch(
            reply -> reply.state() == ItemState.RESERVED)) {
        business = BusinessOutcome.ALL_SUCCEEDED;
    } else {
        business = BusinessOutcome.SOME_FAILED;
    }

    return new BatchOutcome(
        contract.executionId(),
        contract.batchId(),
        contract.expectedItemIds().size(),
        unique.size(),
        completeness,
        business,
        List.copyOf(unique.values()),
        missing);
}
~~~

**This is a method fragment extending `BatchGroupLogic`**, not a standalone Java class. It assumes only **two demo output paths**: release when all IDs have arrived, or partial on timeout. If you have another release strategy, `missing.isEmpty()` only tells whether data is missing/full, **not confirming that the release cause was a timeout**; when fine-grained distinction is needed, pass an explicit reason/event from the lifecycle handler or state store.

Note that `toOutcome` throws an error if it encounters an invalid reply or conflicting duplicate. That is a clear signal for the lesson, whereas production needs to **route such data to quarantine/reconciliation before group expiry** so it does not prevent emitting a partial result at timeout.

### 8.1. Why Not Just Return `List<ItemReply>`?

A list with two replies does not tell the caller **how many parts there were supposed to be**, which parts are missing, or whether further updates may arrive. `BatchOutcome` must carry full metadata:

- `expectedCount` and `receivedCount`.
- `missingItemIds` for follow-up/reconciliation.
- `completeness` stating **completeness**.
- `businessOutcome` stating **business success or failure among resolved parts**.
- `executionId` and `batchId` for tracing and preventing run mix-ups.

### 8.2. Output Order Is Not Input Order

`MessageGroup.getMessages()` should not be assumed to preserve stable business order across stores and transports. If downstream requires original line-item order, use a verified `lineIndex`/`sequenceNumber` and **sort explicitly** in the output processor. The example above only sorts `missingItemIds` and does not promise `replies` follow the original list order.

## 9. Spring Integration Java DSL: Expiring and Sending Partial Results

The example below uses a `DirectChannel` to ingest validated `ItemReply` messages and a `QueueChannel` to receive `BatchOutcome`. The illustrative group timeout is **30 seconds**. This is an in-memory setup for learning mechanics—no durability across restarts is implied.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
class BatchAggregationConfiguration {

    @Bean("inventory.replies.in")
    DirectChannel repliesInput() {
        return new DirectChannel();
    }

    @Bean("inventory.batch.outcomes")
    QueueChannel batchOutcomes() {
        return new QueueChannel();
    }

    @Bean
    IntegrationFlow aggregateItemReplies() {
        return IntegrationFlow.from("inventory.replies.in")
            .aggregate(a -> a
                .correlationStrategy(message -> {
                    GroupContract contract = (GroupContract)
                        message.getHeaders().get("batchContract");
                    return contract.executionId();
                })
                .releaseStrategy(BatchGroupLogic::allExpectedReceived)
                .groupTimeout(30_000L)
                .sendPartialResultOnExpiry(true)
                .expireGroupsUponCompletion(true)
                .outputProcessor(BatchGroupLogic::toOutcome))
            .channel("inventory.batch.outcomes")
            .get();
    }
}
~~~

**Mandatory assumptions before Aggregator in this demo:**

1. Every message has a valid `ItemReply` and a verified `batchContract` header of type `GroupContract`.
2. `executionId` is the unique group key for one processing session; never reused across sessions.
3. The `expectedItemIds` set is consistent across every reply in the same execution.
4. Individual replies are not permitted to alter the issued contract.
5. When duplicates occur, input is deduplicated/validated per policy so no conflict enters the group.

The code intentionally omits adapter/Filter validation in the same snippet to keep **Aggregator** clear. This is not a production example ready to accept raw Internet requests directly.

### 9.1. Role of Each DSL Clause

| DSL | Responsibility |
| --- | --- |
| `.correlationStrategy(...)` | Selects group by `executionId`, not by individual message UUID |
| `.releaseStrategy(...)` | Releases when **all expected item IDs** are present |
| `.groupTimeout(30_000L)` | Sets group timeout via the framework-supported Aggregator mechanism |
| `.sendPartialResultOnExpiry(true)` | On group expiry, lets the output processor process accumulated parts |
| `.expireGroupsUponCompletion(true)` | Allows cleaning up/expiring group after completion; needs late-reply policy |
| `.outputProcessor(...)` | Builds `BatchOutcome` distinguishing `ALL_REPLIES` and `PARTIAL_EXPIRED` |

**Version note:** DSL syntax is shown for modern Spring Integration API families. In a real project, verify your version and configured `TaskScheduler`/message store; this STEP 4 work **has not run a build or deep Content QA**.

### 9.2. Group Timeout Is Not Always a "Fixed Deadline from Batch Creation"

A simple `groupTimeout` may be rescheduled as the group receives additional messages depending on Aggregator mechanics. Thus, for a batch created at T0 whose first reply arrives at T0+20s, the group deadline is not necessarily T0+30s.

If business rules require an **absolute deadline** (e.g., "finish within 45 seconds of batch creation"), persist `createdAt/deadlineAt` from a trusted source and apply a timeout policy computed against that deadline; test with a controllable clock. Never use another JVM's clock or an untrusted client header without controlling drift/clock skew.

### 9.3. No Output If No Group Exists Yet

Aggregator only knows about groups formed by **arriving messages**. If Splitter produces three requests yet **zero replies arrive**, there may be **no existing group** for per-group timeout to fire on.

Therefore, the "zero replies" problem requires a **batch-level deadline watcher** or workflow registry:

~~~text
BatchCreated(RUN-001, expected=[A,B,C], deadline=T)
       |
       +--> Dispatch requests
       |
       +--> Deadline watcher at T
             |
             +--> If already COMPLETE: no-op
             +--> If PARTIAL: mark incomplete/reconcile
             +--> If NO_REPLIES: emit BatchTimedOut(no replies)
~~~

The watcher must coordinate with Aggregator around a **single terminal state**, avoiding emitting both partial from Aggregator and timeout from the watcher as **two final outcomes**.

## 10. Handling Late Replies After Group Expiration

Suppose group `RUN-001` expires at 30 seconds and emits `PARTIAL_EXPIRED`. Reply `LINE-3` arrives at 31 seconds. Three common options:

1. **Discard with audit:** record the late arrival, do not alter emitted results.
2. **Reconcile/upsert:** update batch state, emit a **new event version** (never disguised as the first output).
3. **Compensation/manual review:** handle when the reply proves a side effect occurred while the workflow thought it failed.

**Do not** spin up a new Aggregator group and treat a late reply as a brand-new batch merely because the old group was deleted.

### 10.1. Late Messages and Deleted Groups

When `expireGroupsUponCompletion(true)` or expiry cleanup removes a group from the store, the system may lose metadata indicating `executionId` already closed. A late reply can enter a fresh empty group with the same key, wait for timeout, and emit a **second partial outcome**.

A policy with a **closed-group registry/tombstone** blocks this behavior:

~~~text
Incoming reply
   |
   v
Lookup BatchExecutionState by executionId
   |
   +--> OPEN     -> validate itemId -> Aggregator
   +--> COMPLETE -> duplicate/late path -> audit or ignore
   +--> EXPIRED  -> late path -> reconcile or quarantine
   +--> UNKNOWN  -> reject or manual investigation
~~~

In production, the registry needs TTL and persistent storage matching the **maximum delay/replay window**. If messages can be replayed days later, a tombstone lasting a few seconds is insufficient. You must also prevent races between "group just expired" and "reply arrived right at expiry" using proper transactions/CAS/state transitions.

### 10.2. A Late Reply Does Not Mean Automatic Retry Is Safe

A late reply may report `RESERVED`—meaning the warehouse already reserved stock even though aggregation emitted `INCOMPLETE`. Retrying `RESERVE_STOCK` again could cause duplicate side effects. Always **query/reconcile state** before reissuing commands.

## 11. `MessageGroupStore` and Cleaning Up Long-Lived Groups

Aggregator uses `MessageStore`/`MessageGroupStore` to retain replies and grouping metadata. An in-memory store is simple for examples; production may require a persistent store to recover groups across restarts, depending on SLAs and topology.

| Aspect | Simple In-Memory | Persistent Store / Cluster |
| --- | --- | --- |
| Restart while group is open | Risk of losing received parts | Can retain state with proper transactions/recovery |
| Unbounded data growth | Consumes heap | Consumes database/store space and I/O |
| Group timeout | Relies on in-process scheduler | Must coordinate scheduling, restarts, and recovery |
| Multiple instances | Each instance has separate groups if uncoordinated | Needs shared store, locking, and clear routing/ownership |
| Group cleanup | Release/expiry frees memory | Needs expiry/reaper and retention policies |
| Duplicate messages | May be added multiple times | Needs idempotency + store consistency; persistence doesn't dedup by itself |

**A persistent store does not automatically create "exactly once".** If consumers redeliver messages or two nodes handle the same group, concurrency control, deduplication, and downstream idempotency are still needed.

### 11.1. `MessageGroupStoreReaper`

A message group store reaper scans groups and triggers expiration per policy. When using it, decide:

- **Scan interval:** how often does it scan?
- **Group timeout/age:** how old must a group be to count as overdue?
- **Partial policy:** do reaped expired groups emit partial output or only clean up?
- **Concurrency:** if Aggregator releases just as the reaper scans, who is allowed to close the group?
- **Monitoring:** which metrics detect a failing or stalled reaper?
- **Retention:** how long are tombstones/closed states kept?

Never leave `groupTimeout` and a reaper uncoordinated such that both emit **two partial results**. Timeout/cleanup mechanisms must coordinate, and final output must be guarded by an idempotent `OPEN → CLOSED` state transition.

### 11.2. Sizing the Number of Open Groups

A quick back-of-the-envelope estimate:

~~~text
100 batch/s × 60 s average open group duration
≈ 6,000 pending groups

If each group stores 4 replies × 2 KiB payload:
≈ 48,000 KiB for payloads alone (~47 MiB),
excluding headers, object/store metadata, and indexes.
~~~

If groups never expire or the reaper stops running, sustained growth can exhaust heap or the message store. Track **open group count**, **oldest group age**, **store size**, **expiry rate**, **late reply rate**, and **partial result rate**.

## 12. Correlation and Release Strategy: Bugs Often Are Not in Timeout

An Aggregator hanging indefinitely is not only caused by slow workers. Other causes:

| Cause | Symptom | How to Check |
| --- | --- | --- |
| Different correlation keys | Replies from same batch split across groups | Inspect `executionId` and header mapping |
| Missing child from Filter drop | 2/3, no `ItemRejected` | Inspect discard channel and release policy |
| Wrong sequence size | Aggregator waits for non-existent parts | Inspect Splitter/source collection |
| Duplicate replaces missing reply | Group count met yet unique IDs missing | Count by unique item ID |
| Branch has no consumer | One item's reply never returns | Queue/poller/handler health |
| `replyChannel` lost across broker | Handler runs yet fails to return to right place | Message header mapping / reply routing |
| Item handler fails asynchronously | Error goes to `errorChannel`, never becomes `ItemReply` | Error flow and timeout |
| Group key reused | Late replies mix into new batch | Unique execution ID + closed registry |
| Misconfigured reaper | Groups never cleaned up | `TaskScheduler`, lifecycle, store age |
| Wrong clock/deadline | Unexpectedly early/late expiry | UTC, clock skew, policy start time |

**Never fix bugs by shrinking `expectedCount` to fit received replies.** That makes the system look complete while hiding missing items, breaking the contract, and risking missing inventory or transactions.

### 12.1. Correlation Does Not Replace Idempotency

Correlation answers "which **group** does this reply belong to?". Idempotency answers "has this exact **business operation** already been executed?". A batch may be replayed in the same or a different execution, yet reserving stock for the same `lineId` must not execute twice if the contract requires once.

At an Inventory Gateway/handler, an idempotency key might be:

~~~text
(commandId, lineId, "RESERVE_STOCK")
~~~

That is a business-designed key, not the per-send framework-generated `MessageHeaders.id`.

## 13. Error Channel, Retry, and "Uncertain" Outcomes

When an item reply has not arrived, at least four situations are possible:

1. The request never left the queue.
2. The request reached the consumer, and the consumer failed before executing.
3. The consumer executed the side effect, yet the response was lost.
4. The consumer replied late after the deadline.

Merely looking at a group missing an item **cannot distinguish** those four cases. Therefore, `BatchOutcome(INCOMPLETE)` should be a signal to **reconcile**, not blindly re-run every request.

### 13.1. Retry Per Item, Do Not Re-Broadcast the Entire Batch Recklessly

If `LINE-1` and `LINE-2` already have results and only `LINE-3` is unknown, check `LINE-3`'s status first. Retrying the entire `OrderBatch` from the start could send all three commands to the warehouse system again.

When retrying per item, enforce:

- Finite timeouts and backoff.
- Idempotency at side-effecting consumers.
- Tracking attempt counts, request IDs, and lookup results.
- Never silently reassigning task ownership if one party already received/committed.
- Clear criteria for escalating from retries to manual reconciliation.

### 13.2. `errorChannel` Differs from `partial result`

With `DirectChannel`, exceptions from handlers can propagate back. With pollers/`ExecutorChannel`/brokers, exceptions can be sent as `ErrorMessage` to an error channel depending on configuration. A technical error message **does not automatically become** `ItemReply(FAILED)` just because Aggregator is waiting for it.

If Aggregator should release all parts when a handler errors, an **error-to-result adapter** can translate classified errors into `ItemReply(FAILED)` per contract; however, avoid turning "unknown whether warehouse/carrier processed it" into a definitive `FAILED` when it is really `UNKNOWN`.

### 13.3. Expiration Is Not Rollback

Aggregator expiring a group **cannot undo committed side effects** in external systems. If two warehouses reserved stock while the order needs all three to agree, releasing existing reservations may require **compensating commands**, which themselves can fail and need dedicated retry/observability.

## 14. Gateway Request–Reply and "Zero Replies"

A synchronous Gateway requesting an outcome for `OrderBatch` may wait on Aggregator. If the group expires with partial results, it can receive `BatchOutcome(INCOMPLETE)` *if the reply flow is designed properly*. If configuration suppresses partial results and has no error-reporting branch, the caller may **time out separately**.

Establish a clear API contract:

| Scenario | Suggested Contract Response/Event |
| --- | --- |
| All replies received and all reserved | `BatchOutcome(ALL_REPLIES, ALL_SUCCEEDED)` |
| All replies received with some unavailable | `BatchOutcome(ALL_REPLIES, SOME_FAILED)` |
| Expired with some replies | `BatchOutcome(PARTIAL_EXPIRED, INCOMPLETE)` |
| Zero replies | `BatchTimedOut(NO_REPLIES)` from deadline watcher |
| Bad correlation / spoofed reply | Reject/quarantine and error/audit |
| Downstream timeout with unknown outcome | `RECONCILIATION_REQUIRED`, never assume final failure |

**Important:** When using a Gateway, messages emitted by Aggregator must carry proper reply routing/correlation. Across brokers/adapters, `replyChannel` may not be serializable or propagated; design explicit request/reply IDs and consumers rather than relying on a channel object in headers.

## 15. Testing Complete Release with Spring Integration

Use `BatchAggregationConfiguration` from Section 9 with a `QueueChannel` receiving output to verify **all three IDs → one complete `BatchOutcome`**.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Set;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(BatchAggregationConfiguration.class)
class AggregatorCompleteTest {

    @Autowired @Qualifier("inventory.replies.in")
    MessageChannel input;

    @Autowired @Qualifier("inventory.batch.outcomes")
    PollableChannel output;

    @Test
    void releasesOnceAllExpectedItemIdsHaveArrived() {
        GroupContract contract = new GroupContract(
            "RUN-001", "ORD-801",
            Set.of("LINE-1", "LINE-2", "LINE-3"));

        assertTrue(send(contract, "LINE-1", ItemState.RESERVED));
        assertTrue(send(contract, "LINE-2", ItemState.NOT_AVAILABLE));

        // Not enough unique IDs yet: group must not release.
        assertNull(output.receive(0));

        assertTrue(send(contract, "LINE-3", ItemState.RESERVED));

        Message<?> message = output.receive(1000);
        assertNotNull(message);
        assertInstanceOf(BatchOutcome.class, message.getPayload());

        BatchOutcome result = (BatchOutcome) message.getPayload();
        assertEquals("RUN-001", result.executionId());
        assertEquals(3, result.expectedCount());
        assertEquals(3, result.receivedCount());
        assertEquals(CompletionState.ALL_REPLIES, result.completeness());
        assertEquals(BusinessOutcome.SOME_FAILED, result.businessOutcome());
        assertTrue(result.missingItemIds().isEmpty());

        assertNull(output.receive(0), "No extra batch outcome");
    }

    private boolean send(
            GroupContract contract, String itemId, ItemState state) {
        ItemReply reply = new ItemReply(
            contract.batchId(), itemId, state, null);

        return input.send(MessageBuilder.withPayload(reply)
            .setHeader("batchContract", contract)
            .setHeader("businessCorrelationId", contract.batchId())
            .build());
    }
}
~~~

### 15.1. What Does This Test Prove?

- Replies are placed in the same group via `executionId`.
- Two replies are **insufficient**, so no complete result is emitted.
- All three item IDs trigger release.
- One `NOT_AVAILABLE` reply makes `businessOutcome` equal `SOME_FAILED` even though `completeness` is `ALL_REPLIES`.
- Output is **one group result**, not three batch results.

The test **does not** prove real warehouse APIs committed transactions, that a group store survives restarts, or that late replies will be blocked. Separate tests are needed for those boundaries.

### 15.2. Watch Out for Test State

Incomplete groups remain in `MessageGroupStore`; Spring Test may cache application contexts. Other timeout/duplicate tests should not reuse old `executionId`s and queues without resetting state. Use unique execution IDs per test or isolated contexts/stores, and clean up properly to avoid flaky tests.

## 16. Testing Partial Expiry: Requires Real Scheduler and Timeout

Partial expiry tests should set a short timeout **in a dedicated test configuration**, e.g., a few hundred milliseconds, with a suitable `TaskScheduler`. Never change production's 30-second timeout just for tests, and never rely on `Thread.sleep(100)` and guess the event happened.

**Executable test scenario:**

~~~text
Given:
  Group RUN-EXP-1 expected LINE-1, LINE-2, LINE-3
  Aggregator configured with groupTimeout=shortTimeout
  sendPartialResultOnExpiry=true
  outputProcessor returns BatchOutcome

When:
  Send LINE-1 and LINE-2
  Do NOT send LINE-3
  Wait for outcome using QueueChannel.receive(timeout)
     with timeout comfortably greater than configured group timeout

Then:
  Exactly one BatchOutcome
  completeness = PARTIAL_EXPIRED
  businessOutcome = INCOMPLETE
  expectedCount = 3
  receivedCount = 2
  missingItemIds = [LINE-3]
  No successful business completion event is emitted
~~~

Above is a **test scenario**, not executed JUnit code. To test reliably, verify `groupTimeout` trigger timing for your framework/version, provide a scheduler, isolate the group store, and await output conditionally with a finite timeout.

### 16.1. Testing Timeout Near Arrival of the Final Message

This is an important race condition:

~~~text
T ~ deadline:
  Thread A: receives LINE-3 reply, reaching 3/3
  Thread B: timeout/expiration callback, sees 2/3
~~~

Desired behavior must be governed by **a single final state transition**: complete **or** partial (according to whichever wins atomically), **never emitting two final outcomes** for the same execution. Test under real concurrency and store/lock policies, especially in multi-node setups.

### 16.2. Testing Late Reply After Expiry

After receiving `PARTIAL_EXPIRED`, send reply `LINE-3` for the same `executionId`. Assert one of the chosen contracts:

- Late reply is **discarded/audited**; no new batch result is emitted.
- Late reply is **reconciled**; emits `BatchOutcomeUpdated(version=2)` without silently overwriting the v1 event.
- If late-handling is absent in the demo, the test **must expose** the risk of creating a new group rather than claiming production is safe.

### 16.3. Testing Zero Replies from Deadline Watcher

Send no messages to Aggregator for `RUN-NO-REPLY`. The test harness must create `BatchStarted` in the registry and trigger the deadline watcher; assert that the system emits `BatchTimedOut(NO_REPLIES)` exactly **once**. Do not write a test expecting Aggregator to expire a group that never existed.

## 17. Advanced Test Matrix

| Case | Input/State | Expectation |
| --- | --- | --- |
| Complete 1/1 | One expected reply | Release complete |
| Complete 3/3, all reserved | Three distinct IDs | `ALL_REPLIES + ALL_SUCCEEDED` |
| Complete 3/3, one not available | Three replies, one business failure | `ALL_REPLIES + SOME_FAILED` |
| 2/3 received then timeout | LINE-3 never returns | `PARTIAL_EXPIRED + INCOMPLETE` |
| 0/3 replies | No group exists | Batch deadline watcher emits timeout |
| 1/3 then error | Child handler throws exception | Error flow and partial/reconcile per contract |
| Duplicate LINE-1 | Two messages with same item ID | Does not count as two unique replies |
| Conflicting duplicate | LINE-1 both RESERVED and FAILED | Quarantine/reconcile; never pick arbitrarily |
| Out-of-order | LINE-3, LINE-1, LINE-2 | Proper release; independent of arrival order |
| Wrong correlation ID | Reply tagged `RUN-OTHER` | Does not enter wrong group |
| Header contract mismatch | Two replies in group with different expected sets | Reject/alert before aggregation |
| Filter drops a child | No `ItemRejected` | Timeout or emit rejection result per policy |
| Late reply after expiry | LINE-3 arrives at second 31 | Does not produce a second final outcome |
| Late reply after complete | Duplicate redelivered | Does not start a new group causing wrong output |
| Batch retried | Some warehouses already committed | No repeated side effects |
| Restart while at 2/3 | In-memory vs. persistent store | Matches recovery contract |
| Scheduler stops | Expiry never fires | Monitoring/alerting on oldest group |
| Reaper and timer run together | Two expiry mechanisms race | Never emit two final outcomes |
| Oversized group | 100,000-item batch | Quotas/chunking/backpressure |
| Caller Gateway waits for reply | Partial or zero replies | Response/error meets SLA, no infinite wait |
| Multi-node handles same group | Two instances see replies | Proper locking/store/idempotency |

**Do not measure only line coverage.** A trustworthy suite validates **lifecycle transitions, race conditions, and the invariant "never emit a final result twice"**, even when some children are lost or arrive late.

## 18. Observability: Measuring Open Groups and Expired Groups

If you only log `aggregator output=OK`, you will never know how many items the system waited on or which item failed to respond. Distinguish these measurement points:

| Measurement Point | Signal | Meaning |
| --- | --- | --- |
| Splitter | Batch count, expected item count | How many parts must be processed |
| Child handlers | Sent/accepted/processed, retries, errors | Status of each item |
| Aggregator | Open groups, unique parts received, age | What the batch is waiting on |
| Timeout/expiry | Partial count, missing count, timeout reason | Why groups expired |
| `MessageGroupStore` | Store size, oldest group, cleanup lag | Leak/persistence lag risk |
| Late-handler | Late arrivals, reconciled, discarded | Replies arriving after closure |
| Final outcome | Complete/partial/failed, business result | Outcome reported to caller |
| Reaper/scheduler | Tick success, last scan time, expiry failures | Whether cleanup is running |

**Metric tags:** `completeness`, `businessOutcome`, `endpoint`, and `errorCategory` typically have low cardinality. `batchId`, `executionId`, `lineId`, and `correlationId` typically have high cardinality; keep them in access-controlled logs/traces rather than metric tags.

### 18.1. A Useful Decision Log

~~~json
{
  "event": "aggregation_expired",
  "executionId": "RUN-001",
  "batchId": "ORD-801",
  "expectedCount": 3,
  "receivedCount": 2,
  "missingItemIds": ["LINE-3"],
  "completionState": "PARTIAL_EXPIRED",
  "businessOutcome": "INCOMPLETE"
}
~~~

In production, consider data security: IDs and business metadata can be sensitive; never log full payloads, payment details, tokens, or PII at every step just to debug timeouts.

### 18.2. Channel Send Differs from Business Completion

A `postSend(sent=true)` on the reply channel only reflects the send at that boundary. A message arriving at `inventory.batch.outcomes` also **does not prove** the final outcome consumer finished persisting or compensation completed. Measure outcomes where **business responsibility resides** and maintain execution/event idempotency.

## 19. Common Anti-Patterns

| Anti-Pattern | Consequence | Fix |
| --- | --- | --- |
| Using only `group.size() == expectedCount` | Duplicates trigger early release despite missing items | Count unique item IDs and check expected set |
| Treating `PARTIAL_EXPIRED` as `SUCCESS` | Ignores unknown parts | Separate completeness and business outcome |
| No timeout/cleanup | Groups remain in store forever | Suitable group timeout/reaper/deadline watcher |
| Using only group timeout for 0-reply case | No group exists to expire | Deadline watcher from `BatchStarted` |
| Treating `groupTimeout` as absolute deadline from batch creation | Misses SLA deadlines | Persist trusted deadline and test timing |
| Deleting group and forgetting late replies | Late message starts a new group | Closed registry/tombstone, late path |
| Retrying whole batch when one item loses reply | Repeated side effects on succeeded items | Per-item retry and idempotency |
| Using `correlationId` as business dedup key | Reprocessing causes duplicates or misgrouping | Separate operation ID/line ID and execution ID |
| Disabling partial with no error/reply path | Gateway waits until uncontrolled timeout | Explicit timeout/rejection response |
| Error channel returns no `ItemResult` while still waiting for all | Aggregator never releases | Error-to-result or timeout/reconciliation |
| Letting two instances expire same group uncoordinated | Two final outcomes or data loss | Shared store, locking/CAS, idempotent emission |
| Using in-memory `MessageStore` for SLAs spanning restarts | Groups lost on restart | Persistent `MessageGroupStore` if needed |
| Assuming `sequenceSize` guarantees all children processed | Misses lost messages/duplicates | Track each item and business ACK |
| Unbounded group/item counts | Store/heap exhaustion and throughput drop | Quotas, chunking, backpressure |
| Logging full payloads/PII on timeout | Data leak | Minimal reason/ID logs, access control |

## 20. Pre-Deployment Checklist

- [ ] Each batch has a unique **execution ID** and a trusted expected item ID list.
- [ ] Correlation strategy and release strategy are tested with duplicates/out-of-order arrivals.
- [ ] Separate contracts exist for **completeness** and **business outcome**.
- [ ] Group timeout, business deadline, reaper, and group cleanup are not conflated.
- [ ] Clear decision on whether partial results are emitted and how callers handle partial.
- [ ] **Zero-reply** case is handled by a deadline watcher.
- [ ] Each child has its own error/retry/reconciliation; never blindly retry the whole batch.
- [ ] Late replies after completion/expiration have a discard, reconcile, or versioned update policy.
- [ ] Mechanism exists to block **two final outcomes** for the same execution when timeout races with final reply.
- [ ] For multi-instance, group store, locks, transactions, and `TaskScheduler` are coordinated properly.
- [ ] Group store has TTL/retention/cleanup and monitors oldest-group age.
- [ ] Stable idempotency keys exist on side-effecting handlers.
- [ ] Gateway request–reply has clear timeout/error responses, never waiting forever.
- [ ] Unit tests cover policies and integration tests cover Aggregator lifecycle.
- [ ] Metrics/logging cover incomplete/late/duplicate/reaper without exposing sensitive data.

## 21. Hands-On Exercise

An insurance quote aggregator sends requests to three providers `P1`, `P2`, `P3`. A quote has `quoteId`, `providerId`, `price`, and `validUntil`. The public API has an 8-second SLA. A provider may reply after 12 seconds; sometimes the system receives zero replies.

**Requirements:**

1. Define `QuoteBatch(executionId, requestedProviders, deadlineAt)` and `QuoteReply(providerId, ...)`.
2. Write a correlation strategy by `executionId` and a release strategy by the set of received `providerId`s rather than just `group.size()`.
3. Design policies for **all 3/3**, **partial 2/3**, **0 replies**, and **invalid quote values** (negative price, expired) under an explicit contract.
4. Configure Aggregator with an appropriate timeout/partial policy; explain why 8 seconds from request creation may need a separate deadline watcher.
5. When `P3` replies at second 12, decide whether to ignore, update v2, or reconcile; ensure there are never two unversioned "final responses".
6. Design `MessageGroupStore` if group recovery across restarts is mandatory. Specify `TaskScheduler`, cleanup/reaper, and monitoring.
7. Write tests: 3/3, 2/3 timeout, 0/3, duplicate P1, late P3, out-of-order, and race near deadline.
8. If multiple replicas receive replies concurrently, how do you control release/expiry authority?
9. Distinguish `QuoteBatchResult(ALL_REPLIES, SOME_FAILED)` from `QuoteBatchResult(PARTIAL_EXPIRED, INCOMPLETE)`; when can the best available result be returned to the user?
10. Propose logging/metrics without recording policy numbers or personal information as metric tags.

**Hint:** `Gateway → Recipient List sending requests → Outbound Gateways → Reply channels → Aggregator → QuoteBatchOutcome`, accompanied by a deadline watcher and an **execution-state registry** to handle 0-reply/late-reply cases. If a provider returns a technical error, distinguish `FAILED` (known outcome) from `UNKNOWN` (uncertain whether the action happened).

## 22. Summary

**Expiring groups and handling incomplete parts** are essential so an Aggregator neither holds groups forever nor emits false results. You must understand **when a group qualifies for release, when timeout/expiry must intervene, whether partial output is allowed, and what partial results mean to business logic**. A good `BatchOutcome` contains not only received replies, but also **missing items, completeness, business status, and execution ID**.

In Spring Integration, `correlationStrategy` and `releaseStrategy` define groups and completion conditions; `groupTimeout`, `sendPartialResultOnExpiry`, `expireGroupsUponCompletion`, and cleanup/reaper mechanisms help manage group lifecycles per configuration. However, **without a group, per-group timeout cannot detect 0 replies; deleting a group also does not automatically block late replies**. Therefore, workflows with strict SLAs need deadline watchers, closed-state/tombstones, idempotency, per-item retry/reconciliation, an appropriate `MessageGroupStore`, and concurrency tests to avoid losing data or emitting two final outcomes for the same batch.

**References:** Gregor Hohpe & Bobby Woolf, *Enterprise Integration Patterns* (Aggregator, Message Sequence, Correlation Identifier, Splitter); Spring Integration documentation on Aggregator, Message Groups, `MessageGroupStore`, `MessageGroupStoreReaper`, Java DSL, Error Handling, and Testing; Java SE documentation on `Set`, `Map`, `AtomicReference`, and concurrency primitives.
