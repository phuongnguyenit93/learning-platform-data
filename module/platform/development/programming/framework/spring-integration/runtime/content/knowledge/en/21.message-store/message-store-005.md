# MessageGroup Metadata and Message Release in Spring Integration Runtime

## Learning Objectives

In **SPRING_INTEGRATION_RUNTIME**, some endpoints process messages immediately upon arrival; others must **retain multiple messages** until conditions are met for processing. Aggregators and resequencers are two classic examples. They must know **which group** a message belongs to, **how many parts the group has received**, **when results may be emitted**, and **how long metadata should be kept** to handle late-arriving messages.

That is the role of **MessageGroup**, **MessageGroupStore**, group metadata, and the **message release** mechanism. If managed improperly, a group can wait forever, release prematurely due to duplicate messages, mis-correlate, or be recreated after completion.

After this lesson, you will be able to:

- Distinguish **MessageStore**, **MessageGroupStore**, **MessageGroup**, and **MessageGroupMetadata**.
- Read key metadata: creation/update timestamps, size, completion flag, group condition, and resequencing progress.
- Explain **CorrelationStrategy**, **ReleaseStrategy**, and **MessageGroupProcessor** at runtime.
- Distinguish **release**, **complete**, **expire**, **discard**, and **partial release**; understand behavior with late arrivals.
- Configure an aggregator with a message store, release strategy, timeout, and state cleanup policy.
- Diagnose issues with threads, locking, transactions, retries, persistent stores, idempotency, and performance when scaling across instances.

> **Core point:** A group that has been **released** has not necessarily been **completely removed from the store**. Retained metadata may be precisely what enables the system to recognize and discard a late-arriving message.

## 1. Why Does Runtime Need to Store MessageGroup?

Suppose an order is confirmed only after three independent results arrive:

1. Payment succeeded.
2. Inventory check succeeded.
3. Shipping address confirmed.

Results may arrive out of order and from different threads or instances.

~~~mermaid
flowchart LR
    A["PaymentResult<br/>orderId=O-42"] --> C["CorrelationStrategy<br/>groupId=O-42"]
    B["InventoryResult<br/>orderId=O-42"] --> C
    D["AddressResult<br/>orderId=O-42"] --> C
    C --> S[("MessageGroupStore<br/>messages + metadata")]
    S --> R{"ReleaseStrategy<br/>condition met?"}
    R -- "Not yet" --> S
    R -- "Met" --> P["MessageGroupProcessor"]
    P --> O["OrderReady"]
~~~

A **MessageGroup** is a collection of Spring **Message<?>** instances sharing a **groupId**. The group ID is typically taken from the **correlationId** header, but can be produced by a custom rule, such as **orderId** in a header. The group ID is the group's key in the store, **not synonymous** with each message's **MessageHeaders.ID**.

In the example above, after receiving only PaymentResult and InventoryResult, the aggregator must not emit OrderReady yet. When AddressResult arrives, it re-evaluates the release strategy and can emit the result. If the emitting component fails, you must know how the store, transactions, and retries determine group state.

### How Do MessageStore and MessageGroupStore Differ?

| Component | Function | Typical Use Case |
| --- | --- | --- |
| **MessageStore** | Strategy for storing/retrieving Spring Messages | Storing messages for later processing; foundation for specialized stores |
| **MessageGroupStore** | Manages messages by **groupId** and group metadata | Aggregator, resequencer, delayer/correlation endpoints |
| **ChannelMessageStore** | Storage operations tailored for queue channels | Store-backed QueueChannel |
| **MessageGroup** | Runtime view of a group: messages, groupId, state | ReleaseStrategy and MessageGroupProcessor |
| **MessageGroupMetadata** | Group metadata value object without requiring all payloads to load | Quick inspection of size, timestamps, complete flag, condition |

A single store can implement multiple contracts, but **do not misconfigure** a ChannelMessageStore where a MessageGroupStore is required. In real systems, sharing a **physical storage region** also does not mean every aggregator should share the same **MessageGroupStore instance** and expiry callbacks.

## 2. What Does a MessageGroup's Metadata Contain?

The relevant APIs live in package **org.springframework.integration.store**. A MessageGroup stores messages and lifecycle control info. **MessageGroupMetadata** is a value object describing metadata, retrieved via:

~~~java
MessageGroupMetadata metadata =
        messageGroupStore.getGroupMetadata("O-42");
~~~

This call can fetch group state **without loading all group payloads**, which helps when a group holds thousands of messages in DB/Redis/MongoDB.

| Metadata / API | Meaning | Appropriate Usage |
| --- | --- | --- |
| **groupId** | Logical key used to fetch the group in the store | Lookup by orderId or correlationId; parameter to **getGroupMetadata(groupId)** |
| **size()** | Current number of messages in the group | Monitoring backlog or simple count checks |
| **isComplete()** | Whether the group is marked complete | Helps block adding messages to finished groups; tied to late-arrival handling |
| **getTimestamp()** | Group creation time, epoch milliseconds | Measuring group age since creation |
| **getLastModified()** | Most recent update time of the group | Assessing whether a group is active or stalled |
| **getCondition()** | Business condition string/state summary, if configured | ReleaseStrategy can inspect metadata instead of scanning every message |
| **getMessageIds()** | List of message IDs per metadata | Group diagnostics; **not** a list of payloads |
| **getLastReleasedMessageSequenceNumber()** | Sequence progress released so far, for resequencing | Restoring or diagnosing a resequencer |

**Note:** Group ID is the store's key, not a **getGroupId()** method on **MessageGroupMetadata**. If you need the groupId directly from the group object, use **MessageGroup.getGroupId()**.

### Example: Reading Metadata for Inspection

~~~java
import java.time.Instant;
import org.springframework.integration.store.MessageGroupMetadata;
import org.springframework.integration.store.MessageGroupStore;

public final class GroupInspector {
    private final MessageGroupStore store;

    public GroupInspector(MessageGroupStore store) {
        this.store = store;
    }

    public void inspect(String orderId) {
        MessageGroupMetadata metadata = store.getGroupMetadata(orderId);
        if (metadata == null) {
            System.out.println("No group for " + orderId);
            return;
        }

        System.out.printf(
                "group=%s size=%d complete=%s created=%s modified=%s condition=%s%n",
                orderId,
                metadata.size(),
                metadata.isComplete(),
                Instant.ofEpochMilli(metadata.getTimestamp()),
                Instant.ofEpochMilli(metadata.getLastModified()),
                metadata.getCondition());
    }
}
~~~

This code **reads state**; it does not release groups. The metadata you read is a **snapshot**: the group can be altered by another thread/instance immediately afterward. Do not write logic like "read size from inspector → if 3, manually send output" because the check and emission are not synchronized with the aggregator.

### Which Metadata Does Not Tell the Whole Truth?

- **size() = 3** does not guarantee **three distinct business steps**. All three could be redelivered PaymentResults with different Message IDs.
- **isComplete() = true** does not guarantee downstream committed business side effects. It only reflects **group** status per the store/endpoint.
- **getLastModified()** does not replace a business SLA deadline. Timing also depends on poll schedules, schedulers, timeouts, and infrastructure latency.
- The list of **Message IDs** is not a list of **eventId/idempotencyKey** values; a replayed event can create a new Spring Message.
- **condition** is data following application/framework conventions, not automatically an evaluated or satisfied expression.

## 3. CorrelationStrategy Decides Which Group Receives a Message

Core contract:

~~~java
public interface CorrelationStrategy {
    Object getCorrelationKey(Message<?> message);
}
~~~

By default, an aggregator extracts the correlation key from the **correlationId** header. This can be replaced with a rule such as **headers['orderId']**. Every message for order O-42 must share the same group ID if they are meant to converge.

~~~text
PaymentResult   headers['orderId'] = O-42 ┐
InventoryResult headers['orderId'] = O-42 ├─ groupId O-42
AddressResult   headers['orderId'] = O-42 ┘

PaymentResult   headers['orderId'] = O-43 ── groupId O-43
~~~

### Common Correlation Bugs

- A transformer creates a new Message and **forgets to preserve orderId/correlationId**.
- Using each message's **MessageHeaders.ID** as the group key, putting every message into its own separate group.
- Two different flows reuse short keys like O-42 in a shared store region and **mix groups**.
- A business key is reused for a new run while metadata from the old group still exists.
- Generating group keys from mutable values like timestamps or request attempts, causing retries to enter different groups.

Define explicit **key namespaces**, such as **order-confirmation:v1:O-42**, in environments with multiple aggregator types. Especially with persistent stores, changing the correlation-key function during a deployment can leave old messages unreleased forever.

**Missing key case:** A message lacking the expected correlationId/orderId must be treated as invalid data, routed separately, or properly enriched before the aggregator. Never assign a shared fallback groupId like UNKNOWN, which can merge unrelated orders.

## 4. ReleaseStrategy Decides When a Group Is Released

Contract:

~~~java
public interface ReleaseStrategy {
    boolean canRelease(MessageGroup group);
}
~~~

After a new message enters the group, the aggregator evaluates the release strategy. When it returns **true**, **MessageGroupProcessor** transforms the group's contents into an output message or appropriate result.

A **ReleaseStrategy** decides **whether release conditions are met**, while **MessageGroupProcessor** decides **what content to emit**. Never place side effects like sending emails or calling payment APIs inside **canRelease()**: the strategy can be invoked repeatedly across incoming messages, timeouts, or retries.

### Default Strategy: Sequence Headers

For message groups originating from a splitter, Spring Integration commonly uses these headers:

~~~text
correlationId = group-42
sequenceNumber = 1 / 2 / 3
sequenceSize = 3
~~~

By default an aggregator uses **SimpleSequenceSizeReleaseStrategy**, which releases once sequence count is reached. Since Spring Integration 5.0, this is the standard default when partial sequence releases are not required.

| Arrival | Sequence Numbers Arrived | Size | Result |
| --- | --- | ---: | --- |
| 1 | [2] | 1 | Not released yet |
| 2 | [2, 1] | 2 | Not released yet |
| 3 | [2, 1, 3] | 3 | Eligible for release |

**Risk:** A count-based release mechanism can mistake a **duplicate** for a missing part. **SimpleSequenceSizeReleaseStrategy** is optimized for performance and does not perform the same duplicate sequence-number checks as the older **SequenceSizeReleaseStrategy**. If sources can redeliver or drop messages, implement proper deduplication, a stricter release strategy, or explicit partial-release policies.

### Do Not Use size() == 3 Blindly

For the three-step business example, this expression is **error-prone**:

~~~text
release-strategy-expression="size() == 3"
~~~

It can release when the group holds **two duplicate payment records + one inventory record**, while still missing the address. Moreover, if a group already holds more than three parts due to retries, **== 3** may never match again.

It is safer to verify **all three distinct result types** and guard against business duplicates. Example release strategy inspecting each part:

~~~java
import java.util.EnumSet;
import java.util.Set;
import org.springframework.integration.aggregator.ReleaseStrategy;
import org.springframework.integration.store.MessageGroup;
import org.springframework.messaging.Message;

enum Step { PAYMENT, INVENTORY, ADDRESS }

record OrderPart(String orderId, String eventId, Step step) {}

public final class RequiredOrderSteps implements ReleaseStrategy {
    private static final Set<Step> REQUIRED = EnumSet.allOf(Step.class);

    @Override
    public boolean canRelease(MessageGroup group) {
        Set<Step> arrived = EnumSet.noneOf(Step.class);
        for (Message<?> message : group.getMessages()) {
            if (!(message.getPayload() instanceof OrderPart part)) {
                return false; // Payload violates contract.
            }
            arrived.add(part.step());
        }
        return arrived.containsAll(REQUIRED);
    }
}
~~~

**Limitation of this example:** It solves "all required step types arrived," but **does not eliminate duplicate eventIds** and **does not pick the valid result when the same step appears multiple times**. Inbound handling must validate data and enforce idempotency; the output processor must specify how duplicates/conflicting results are handled.

For large groups, calling **getMessages()** on every incoming message can cause significant I/O and deserialization overhead, especially with persistent stores. In such cases, use safely updated metadata/conditions or redesign aggregation to avoid scanning the full group continuously.

## 5. Configuring the Aggregator and Message Store

A typical XML configuration illustrating correlation, release, and group lifecycle:

~~~xml
<bean id="orderGroupStore"
      class="org.springframework.integration.store.SimpleMessageStore"/>

<bean id="requiredOrderSteps"
      class="com.example.integration.RequiredOrderSteps"/>

<int:aggregator
    id="orderAggregator"
    input-channel="orderParts"
    output-channel="orderReady"
    message-store="orderGroupStore"
    correlation-strategy-expression="headers['orderId']"
    release-strategy="requiredOrderSteps"
    discard-channel="lateOrRejectedParts"
    expire-groups-upon-completion="false"/>
~~~

Prerequisites for this example:

1. Bean **RequiredOrderSteps** is the Java class above. A real project needs proper packages/imports and Spring Integration XML namespace configuration.
2. Producers send **OrderPart** with an **orderId** header. Channels **orderParts**, **orderReady**, **lateOrRejectedParts**, and their consumers must be defined.
3. **SimpleMessageStore** is an in-RAM store suitable for demos/tests; JVM restarts lose state.
4. By default, the aggregator uses an appropriate output processor to combine messages/payloads. Business logic should produce an explicit **OrderReady** instead of making downstream guess results from a list of parts.
5. **expire-groups-upon-completion="false"** retains metadata after complete release, allowing late arrivals with the same correlation key to be rejected. It requires a subsequent metadata cleanup policy.

This is **an illustrative aggregator configuration**, not a standalone runnable app; do not assume it applies verbatim to every protocol adapter, schema, or Spring Integration version.

### When a Persistent Store Is Needed

Available implementations include:

| Store | Advantage | Must Control |
| --- | --- | --- |
| **SimpleMessageStore** | Lightweight setup, no external infra | Data lost on restart, RAM grows with backlog |
| **JdbcMessageStore** | Stores messages/groups in RDBMS | Schema, transactions, serialization, indexes, contention, cleanup |
| **RedisMessageStore** | Access via Redis, shared across instances | Persistence config, serialization, locking, TTL/cleanup |
| **MongoDbMessageStore** | Document storage, scales group data | Collections/indexes, schema, transactions/concurrency, document size |

A persistent store reduces the risk of losing **durably committed state**, but does not guarantee "exactly once". If payloads or headers are not serializable, saving/reading back can fail or drop metadata. Watch out especially for **replyChannel/errorChannel**, headers carrying Java objects, or transport resources that may only be valid in the old JVM.

**Store partitioning:** If two aggregators have different expiry logic, use separate store instances/regions/collections, or at minimum design group IDs and callbacks independently. Never share a **MessageGroupStore instance** across multiple correlation endpoints with expiry callbacks in an unsupported manner.

## 6. Release, Complete, Expire: Three Distinct Operations

In Spring Integration, group lifecycle is not simply "receive enough → delete".

~~~mermaid
stateDiagram-v2
    [*] --> Accumulating: First message
    Accumulating --> Accumulating: Add message, release not met
    Accumulating --> Released: ReleaseStrategy=true
    Released --> Completed: Mark group complete
    Completed --> Retained: Keep metadata, reject late messages
    Completed --> Removed: expire-groups-upon-completion=true
    Retained --> Removed: Later expiry/reaper
    Accumulating --> TimedOut: Timeout or reaper
    TimedOut --> Partial: Emit partial if configured
    TimedOut --> Discarded: Drop partial if configured
    Partial --> Removed: Expire upon timeout policy
    Discarded --> Removed: Expire upon timeout policy
~~~

The diagram illustrates **common scenarios**. The framework also supports partial releases, resequencing, and force-complete strategies, so exact state transitions may vary by endpoint/version.

| Concept | Meaning | Subsequent Metadata |
| --- | --- | --- |
| **Release** | Group satisfies release strategy; unreleased messages pass to output processor | Emitted messages can be removed from group; state depends on whether group is complete |
| **Complete** | Group is marked to accept no further messages | Metadata may remain even when group is empty |
| **Expire/remove** | Completely removes group from store | Subsequent message with same groupId can start a **new** group |
| **Discard** | Excludes message (or expired group) from business output; can route to discard channel | Depends on expire/retain policy |
| **Partial release** | Emits result of an incomplete group due to timeout/special strategy | Downstream must recognize it as a **partial result**, not treat it as complete |

### Retaining Metadata to Block Late Arrivals

If **expireGroupsUponCompletion=false** (the default for normal completion), after a group completes, the store can keep an **empty completed group**. When a message with the same key arrives too late, the aggregator recognizes the completed group and routes it to the **discard channel** if configured, rather than emitting a new result.

If **expireGroupsUponCompletion=true**, the completed group is deleted immediately. A later message with the old groupId **can create a new group**. That may fit session-based recurring groups, but is very dangerous if groupId identifies a unique order and messages get redelivered.

**Example:**

~~~text
09:00  O-42 receives PAYMENT + INVENTORY + ADDRESS → emits OrderReady.
09:00  Metadata for O-42 retained in completed state, messages may be empty.
09:05  Broker redelivers PAYMENT for O-42.
       → Group completed: routed to discard/late handling.

If O-42 metadata was deleted:
09:05  PAYMENT can create a new O-42 group, waiting for more parts.
       → Backlog grows and risks duplicate processing if other parts also arrive again.
~~~

Therefore, choose the **metadata retention period** based on redelivery windows, retries, broker retention, and business rules. Do not keep metadata infinitely when group counts are huge; yet do not delete it too early while late messages can still arrive.

## 7. Group Timeout, MessageGroupStoreReaper, and Partial Results

Not every group receives all its messages. A downstream service may fail to reply, a message may be filtered out, or a sequence may be missing.

Two common timeout mechanisms:

| Mechanism | Scope | Timing |
| --- | --- | --- |
| **group-timeout / group-timeout-expression** | Scheduled **per group** when release strategy isn't met | Typically measured from the latest message; expressions can define custom rules |
| **MessageGroupStoreReaper** | Scans groups in a **store** on a schedule | Execution schedule and group age threshold decide when expiry callbacks fire |

When a timeout forces a group to complete, the release strategy may be queried once more. If still incomplete and **send-partial-result-on-expiry=true**, the aggregator can emit a **partial** result. If false, remaining parts follow discard/expire policy. Never assume a partial result represents a "complete order".

Intentional configuration example:

~~~xml
<int:aggregator
    id="orderAggregator"
    input-channel="orderParts"
    output-channel="orderReady"
    message-store="orderGroupStore"
    correlation-strategy-expression="headers['orderId']"
    release-strategy="requiredOrderSteps"
    group-timeout="30000"
    send-partial-result-on-expiry="false"
    expire-groups-upon-completion="false"
    expire-groups-upon-timeout="false"
    discard-channel="lateOrRejectedParts"/>
~~~

In this configuration, if timeout occurs while the group lacks parts, logic favors **not emitting an incomplete OrderReady**. Expired group metadata is retained per timeout policy for observability and rejecting late arrivals; an additional cleanup process must be configured. **expire-groups-upon-timeout** is an option independent of **expire-groups-upon-completion**; defaults and configurability may vary by version.

This is **a variation** of the previous section's configuration—do not create two aggregators sharing the same store in a real application.

### Reapers Run on Schedule, Not Exact Precision

If the expiry threshold is 10 minutes but the reaper only runs hourly, a group can persist past the threshold. Conversely, expiring too early erases late-arrival protection. Tune reaper frequency according to SLAs, pending group counts, and store scan cost.

With persistent stores, beyond the reaper you must address **orphaned groups**: groups stored prior to an application restart whose in-process timeout timers vanished. Spring Integration offers **expireTimeout/expireDuration** options on correlating handlers in supported versions to sweep stale state. Never assume all in-memory timers survive intact simply because the store is durable.

**Error note:** The `TaskScheduler` triggering expiration may run on a separate thread. If an expiration callback emits a message and downstream throws an exception, that error must be observed by the scheduler/appropriate error handler. An exception in a callback does not mean emitted data or store deletions automatically roll back.

## 8. Group Condition: Metadata for Efficient Release

Since Spring Integration **5.5**, **MessageGroup** supports a String **condition** field. Depending on the application, this can represent an expected count, end marker, or summary state. Store API:

~~~java
messageGroupStore.setGroupCondition(groupId, condition);
~~~

And the release strategy can read it:

~~~java
String condition = group.getCondition();
~~~

Spring Integration also provides **groupConditionSupplier** on correlating handlers to recompute the condition as each new message arrives, based on the incoming message and current condition. This updates metadata **inline with group processing** instead of loading and scanning all payloads on every release check.

**Application example:** A file splitter emits a footer marker indicating **lineCount**. Due to parallel executor processing, the footer marker may arrive before all line messages. When the marker arrives, the condition can store the expected line count; the release strategy only compares received progress against that count. Supporting components like **FileMarkerReleaseStrategy** apply this idea.

~~~text
groupId = import-file-42
condition = "expectedLines=1000"
current messages = 995

ReleaseStrategy:
    Do not release yet with only 995/1000 valid lines.
    Release once 1000 distinct lines arrive per business rules.
~~~

**You must define how conditions are encoded and parsed**. The framework does not automatically convert arbitrary String conditions into booleans. When using received counts, account for duplicates: condition and size are accurate only if the source and store ensure the same record is never counted twice.

For very large groups, using conditions or metadata avoids scanning the entire group; however, updating metadata on every message adds write load. Measure latency and contention before optimizing.

## 9. Persistent MessageGroupStore: Metadata and Payloads Can Have Separate Access Paths

A persistent store may persist **group metadata** and **actual messages** in separate structures. **getGroupMetadata(groupId)** lets you read group info without necessarily deserializing all payloads. This differs from **getMessageGroup(groupId)** or **getMessagesForGroup(groupId)**.

With many persistent implementations, Spring Integration supports **lazy loading**. Since version **5.5**, MessageGroupStore also provides:

~~~java
try (var stream = store.streamMessagesForGroup(groupId)) {
    stream.forEach(message -> {
        // Process/count as needed; avoid holding the entire group in RAM.
    });
}
~~~

With persistent stores, always **close the Stream** to release DB/client access resources. Do not use a stream when you only need count/completion status; metadata APIs are usually more appropriate.

### Restart/Deployment Scenarios

**1. In-flight groups:** The store still holds parts that already arrived. The new application needs the same **correlation strategy**, compatible schemas/serializers, and active expiry/release mechanisms after restart.

**2. Non-serializable headers:** A Message carrying transport objects, replyChannel, or exceptions may fail to serialize as expected. Use header mapping, channel names, or proper serializer config; test reading back records written by the previous version.

**3. Schema version changes:** Changing payload class packages/fields breaks deserialization of older messages. Implement schema evolution, migrations, or stable format contracts.

**4. Shared store:** Two instances reading the same group may evaluate release concurrently. **Locking, transactions, and duplicate side effects** must be coordinated.

**5. Completed groups still consuming resources:** Empty metadata is retained to block late messages; enforce TTL/state cleanup without breaking the deduplication window.

## 10. Thread Safety, LockRegistry, and Transactions During Release

Two producers can send messages into the same **DirectChannel** concurrently. **ExecutorChannel** enables parallel worker execution; pollers can run multiple tasks. When scaling across replicas, messages with the same orderId can arrive at **two different JVMs**.

~~~mermaid
flowchart TD
    A["Instance A / worker 1"] --> K["groupId=O-42"]
    B["Instance B / worker 2"] --> K
    K --> L["Appropriate LockRegistry"]
    L --> S[("Shared MessageGroupStore")]
    S --> R["Evaluate release + update group"]
    R --> O["Output processor"]
~~~

Within one JVM, per-group synchronization may protect in-memory state. Across multiple JVMs, **DefaultLockRegistry** only provides **local** locks; a **distributed LockRegistry** matching your infrastructure is required when multiple instances operate on shared groups. Spring Integration supports configuring `LockRegistry` on correlating handlers and, in newer versions, locking at the store layer.

**Never assume a persistent store replaces locking.** The store preserves data, locks coordinate concurrent access, and transactions govern atomicity and rollback of covered changes. Test:

- Two messages with the same groupId arriving nearly simultaneously.
- Two instances both seeing a group about to satisfy release conditions.
- An instance crashing between saving a message, marking complete, and sending output.
- An output being retried after the store already updated metadata.

Even when groups are properly locked, **an output message can be redelivered** if callers/brokers retry or external send outcomes are ambiguous. Downstream still needs **business idempotency**, such as a unique constraint on **orderId + eventType + version**.

### Transaction Boundaries Do Not Cross Executors

If a poller starts a transaction on thread A and sends to an **ExecutorChannel**, thread B running the aggregator later does not automatically join thread A's transaction. To process groups and outputs durably, design transactions **on the appropriate consumer side**, specifying which store/broker/resources are covered and how to recover if sending output fails.

**MessageGroupStore** does not automatically turn HTTP calls or broker publishes into a distributed transaction with the DB. Use transactional outboxes, inbox/idempotency tables, and reconciliation when send outcomes can be uncertain.

## 11. Retries, Message Release, and Correlation Errors

A failure can happen before or after a group releases:

| Error | Possible Impact | How to Handle |
| --- | --- | --- |
| Source redelivers the same part | Group may receive duplicate messages with new Message IDs | Use **eventId/idempotencyKey**; deduplicate before counting |
| Transformer drops correlationId | Message enters wrong group or is rejected | Preserve stable keys; verify headers before aggregator |
| Output processor fails | Business result not produced | Design exception/error flows/transactions; test store state after errors |
| Timeout before all parts arrive | Group waits forever or triggers partial release | Define SLA, `sendPartialResultOnExpiry`, and clear discard/recovery |
| Group complete but another part arrives late | Discarded or starts a new group if metadata was deleted | Choose proper retention and provide a **discard channel** |
| App restarts mid-flight | Timers/group state may need recovery | Persistent store + purge/reaper/reconciliation mechanisms |
| Two instances evaluate release concurrently | May emit duplicate output or contend on group updates | Distributed `LockRegistry`, transactions, downstream idempotency |

**Especially important:** Handler retries, broker redeliveries, and DLQ replays operate at **different layers**. If each layer retries the entire flow, you may observe multiple releases or multiple messages under the same group key. Each retry should preserve **business correlation** while generating a distinct attempt ID for diagnostics if needed.

In error flows, do not read **ErrorMessage** headers assuming correlation is there. Look up **originalMessage** or **MessagingException.failedMessage** when available, and persist `requestId`/`orderId` in a durable FailureJournal.

### Intentional GroupId Reuse

If business rules require running **multiple aggregation rounds for the same orderId**, do not use `orderId` alone as the group key. A key like **orderId + workflowVersion/runId** distinguishes separate runs while keeping old group metadata intact and preventing late events from mixing in.

Do not delete group metadata just to "allow reprocessing" without a deduplication strategy; doing so erases proof that the group already completed.

## 12. Observing Performance and Runtime State

When operating an aggregator, observe **arrival rates**, **wait time until release**, **store health**, and **error paths**:

| Metric/Signal | Diagnostic Hint |
| --- | --- |
| **Incomplete** group count | Groups awaiting inputs; steady growth suggests missing parts or correlation bugs |
| Group age P95/P99, lastModified age | Identifies stale groups making no progress |
| Group size and size distribution | Detects duplicates, excessive parts, memory pressure |
| Release rate and latency | Indicates bottlenecks in release strategy or output processor |
| Partial/timeout/discard/late-arrival counts | Validates SLAs, expiry policies, and late input rates |
| Store read/write latency, serialization failures | DB/Redis/MongoDB overloaded or schema errors |
| Lock wait time / contention | Too many messages sharing a key or cross-instance lock contention |
| Retries and duplicate outputs | Misaligned transactions, redeliveries, or idempotency |
| Orphaned/retained completed groups | Missing cleanup or overly long retention |

A structured log entry might look like:

~~~text
flow=orderAggregation endpoint=orderAggregator
groupId=order-confirmation:v1:O-42
orderId=O-42 correlationId=checkout-42
groupSize=2 expectedStages=3 groupComplete=false
groupAgeMs=42000 lastModifiedAgeMs=12000
decision=WAITING_FOR_ADDRESS thread=aggregator-worker-2
~~~

Logs should distinguish **groupId**, **messageId**, **businessId**, and **attemptId**. Avoid logging full payloads containing personal info or secrets. If the release strategy must deserialize thousands of messages each time, switch to appropriate metadata/condition structures and measure CPU, allocation, and DB I/O before expanding the executor pool.

### Questions to Ask When a Group Does Not Release

1. Do the group's messages share the **same correlation key** and correct namespace?
2. Have all **distinct** required parts arrived, or only enough total items including duplicates?
3. Is **ReleaseStrategy** actually being invoked, and which condition returns false?
4. Do **Metadata** fields (`complete`, `condition`, `timestamp`) match expectations?
5. Has the group timed out, been discarded, or been deleted and recreated?
6. Is the persistent store reading/writing successfully and recovering across restarts?
7. Is there lock contention, an error flow firing, or a transaction rollback?
8. Did an upstream splitter/filter drop a message, invalidating **sequenceSize**?

## 13. Hands-On Lab: Aggregating a Three-Part Order

**Problem statement:** Three sources—PAYMENT, INVENTORY, ADDRESS—send messages asynchronously. Some messages are redelivered; two application instances share a persistent store. SLA per order is 2 minutes. If any part is missing, a complete **OrderReady** must not be emitted.

### Reference Design

1. **Correlation:** Use a stable key **order-confirmation:v1:{orderId}:{runId}**; validate business keys before the aggregator.
2. **Deduplication:** Each part carries an **eventId**. Store/check `eventId` atomically/idempotently so redeliveries are not counted as new steps.
3. **Store:** Use a **persistent MessageGroupStore** with configured schema, serializer, and isolated data region.
4. **Release:** Emit only when all three valid result types exist. Never use `size() == 3` when sources can duplicate.
5. **Timeout:** After 2 minutes, record an **OrderAssemblyTimedOut** or transition state to quarantine; never emit an incomplete OrderReady.
6. **Late arrivals:** Retain completed/timed-out metadata longer than the redelivery window, then clean up cleanly.
7. **Concurrency:** Coordinate per-`groupId` locks across instances and use appropriate transactions.
8. **Output:** Process idempotently by **orderId + runId**, persisting an outbox event if broker publishing must survive crashes.
9. **Monitoring:** Track overdue waiting groups, groups missing stages, duplicates, expiry callback failures, and backlog.

### Essential Test Cases

| Case | Input | Expected Outcome |
| --- | --- | --- |
| Arbitrary order | INVENTORY → PAYMENT → ADDRESS | Exactly one OrderReady after the third part |
| Missing part | PAYMENT + INVENTORY | No release before timeout |
| Duplicate message | PAYMENT (event E1) twice, INVENTORY | Not mistaken for all three steps |
| Late arrival | ADDRESS arrives after group ended | Routed to discard/quarantine; no duplicate business action |
| Two independent groups | O-42 and O-43 interleaved | No payload/correlation mixing |
| Two instances, same key | Concurrent sends for parts of O-42 | No lost updates, no duplicate emissions |
| Store restart | Persist 2/3 parts then restart | Restores the 2 parts accurately and releases only after the 3rd |
| Timeout reached | Only 2/3 parts arrive by SLA deadline | Clear timeout outcome, explicit partial-state handling |
| Output failure | Group complete but consumer throws exception | Error/transaction/recovery traced; state not silently lost |
| Schema migration | Messages from previous version remain in store | Deserialized cleanly or handled via migration/quarantine |

**Self-check question:** After the aggregator emits OrderReady, metadata for the group remains while `size() = 0`. Is this corrupted data?

**Explanation:** **Not necessarily.** A **completed empty group** can be intentionally retained to recognize and discard late-arriving messages. Check **isComplete()**, the **expireGroupsUponCompletion** policy, and cleanup schedules instead of looking at `size()` alone.

## 14. Pre-Production Checklist

- Did you pick the right store for the aggregator (**MessageGroupStore**) and verify whether state survives restarts?
- Are group IDs generated deterministically, namespaced, and free of collisions across flows/versions?
- Does `ReleaseStrategy` verify **complete business criteria**, not merely message count including duplicates?
- Have you distinguished **release**, **complete**, and **expire**, and defined a policy for late arrivals?
- Are **expireGroupsUponCompletion** and **expireGroupsUponTimeout** configured appropriately?
- Are **groupTimeout/reaper** and cleanup schedules set up for incomplete, orphaned, and completed groups?
- Is there an explicit decision on **partial release** and how downstream identifies partial results?
- Is metadata/condition updated safely without forcing full group loads during inspection?
- Does the persistent store have proper schema, serializer, indexes, region, and migration strategy?
- With multiple instances, is there a distributed **LockRegistry** or equivalent coordination mechanism?
- Can handler, poller, or broker retries/transactions duplicate output, and is downstream idempotent?
- Are logs/metrics in place for pending groups, timeouts, releases, discards, lock contention, and `failedMessage`/correlation?
- Do integration tests cover out-of-order, duplicate, late arrival, restart, and concurrent release cases?

## Conclusion

**MessageGroup metadata** is the state layer that lets Spring Integration track what a group has received, when it was updated, whether it is complete, and whether it must be retained to catch late messages. **ReleaseStrategy** decides when results are emitted; **MessageGroupProcessor** constructs the result; and **MessageGroupStore** safeguards messages and metadata across the group lifecycle.

To run reliably at runtime, design **correlation keys**, **release conditions**, **retention/expiry**, **locking**, **transactions**, **retries/idempotency**, and observability together. In particular, distinguish a **released** group from a group whose **metadata was deleted**: that distinction determines how the system reacts to late arrivals and duplicate processing.

## References

- [Spring Integration Reference — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html)
- [Spring Integration Reference — Aggregator](https://docs.spring.io/spring-integration/reference/aggregator.html)
- [Spring Integration API — MessageGroup](https://docs.spring.io/spring-integration/docs/6.5.x/api/org/springframework/integration/store/MessageGroup.html)
- [Spring Integration API — MessageGroupMetadata](https://docs.spring.io/spring-integration/docs/6.5.x/api/org/springframework/integration/store/MessageGroupMetadata.html)
- [Spring Integration API — MessageGroupStore](https://docs.spring.io/spring-integration/docs/6.5.x/api/org/springframework/integration/store/MessageGroupStore.html)
- [Spring Integration API — AbstractCorrelatingMessageHandler](https://docs.spring.io/spring-integration/docs/6.5.x/api/org/springframework/integration/aggregator/AbstractCorrelatingMessageHandler.html)
