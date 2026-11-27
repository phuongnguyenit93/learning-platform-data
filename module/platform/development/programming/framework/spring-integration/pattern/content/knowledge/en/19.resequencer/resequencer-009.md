# Late Messages After a Sequence Has Released

## 1. Why Are Late Messages a Business Problem?

In the **Resequencer** chapter of the **SPRING_INTEGRATION_PATTERN** module, we learn to implement Enterprise Integration Patterns with **Spring Integration** to build loosely coupled, scalable, testable, and observable messaging flows. Resequencer fixes **message arrival order** when networks, brokers, or parallel branches cause messages to arrive out of their original order.

Suppose an order fulfillment tracking app receives four events for the same batch:

| Sequence number | Event | Meaning |
| ---: | --- | --- |
| 1 | ORDER_ACCEPTED | Order accepted |
| 2 | STOCK_RESERVED | Stock reserved |
| 3 | PAYMENT_CONFIRMED | Payment confirmed |
| 4 | SHIPMENT_CREATED | Shipment created |

If messages traverse multiple channels, `ExecutorChannel`s, queues, or workers, they may arrive in order **2, 4, 1, 3**. Resequencer can hold the messages and emit them in `sequenceNumber` order **1, 2, 3, 4**.

Yet what happens when a message **arrives after the entire sequence has already released**?

- Message 2 is redelivered by the broker even though group 1–4 is already complete.
- Message 3 was delayed in the network and just arrived after the group timed out and closed.
- Message 4 is replayed hours later, after the old group metadata was purged.
- Another workflow accidentally reuses the `correlationId` of a completed group.

If handled improperly, the application may **create a new group from an old message**, emit a duplicate event, hang waiting for a sequence that will never complete, or execute a side effect a second time.

~~~mermaid
flowchart LR
    P["Producer: 1,2,3,4"] --> Q["Broker / network"]
    Q -->|"2,4,1,3"| R["Resequencer"]
    R -->|"1,2,3,4"| D["Downstream handler"]
    Q -.->|"2 (late redelivery)"| R
    R -.->|"Late discard / quarantine"| L["Late message policy"]
~~~

**Lesson Objectives**

1. Understand precisely what a **late message** is after a group or sequence segment has released.
2. Distinguish messages **arriving slowly to fill a gap**, **duplicates**, **arriving after timeout**, and **arriving after group metadata was deleted**.
3. Understand **`releasePartialSequences`**, **`sendPartialResultOnExpiry`**, **`expireGroupsUponTimeout`**, **`MessageGroupStore`**, and **`discardChannel`**.
4. Explain why retaining **empty completed groups** enables detecting late arrivals, while deleting too early can spawn new groups.
5. Design retention, recovery, idempotency, error channels, and observability for late messages.
6. Use Java DSL to configure Resequencer, then test ordering, duplicates, group completion, and late arrivals.

## 2. How Does Resequencer Differ from Aggregator?

Both **Resequencer** and **Aggregator** can group messages by **`correlationId`**, but their goals differ:

| Component | What It Does to Messages | Typical Output |
| --- | --- | --- |
| **Resequencer** | Buffers out-of-order messages and re-emits them by `sequenceNumber` | Individual messages in order |
| **Aggregator** | Collects messages of the same group and combines them into one result | One aggregated message, such as `BatchReport` |
| **Splitter** | Splits one large message into child messages | Multiple child messages |
| **Router** | Chooses destination | Messages sent to selected channels |
| **Filter** | Keeps or drops based on condition | Messages continue or go to discard |

Example:

~~~text
Input:  B(2), D(4), A(1), C(3)

Resequencer:
  output A(1)
  output B(2)
  output C(3)
  output D(4)

Aggregator:
  output Collection[A, B, C, D] or one BatchReport
~~~

Resequencer **does not summarize payloads itself** and does not guarantee a business event was not previously processed. After resequencing, a Service Activator might write to a database, a Gateway might call an external service, or a Router might pick another branch; those steps need their own retry/idempotency mechanisms.

### 2.1. Resequencer Solves One Kind of Order, Not Every Kind of Order

Resequencer relies on **`sequenceNumber` within a correlation group**. It cannot determine on its own:

- Whether `PAYMENT_CONFIRMED` truly happened after `STOCK_RESERVED`.
- Whether 2 events from two producers share a **global total order**.
- Whether the broker permanently lost message #3.
- Whether event #2 was processed **exactly once** in the database.
- Whether client-supplied sequence metadata is trustworthy.

If upstream assigns wrong `sequenceNumber`s, Resequencer will emit **according to those wrong numbers**. You need a producer sequence contract and trusted data boundaries.

## 3. Three Metadata Fields Governing Resequencing

A grouped message typically carries:

| Header | Meaning | Example |
| --- | --- | --- |
| **correlationId** | Identifies the group of messages to reorder | `shipment-880:attempt-1` |
| **sequenceNumber** | Position of the message in the group, typically 1-based | `3` |
| **sequenceSize** | Expected number of elements | `4` |

~~~text
Message #3
  payload: PAYMENT_CONFIRMED
  correlationId: shipment-880:attempt-1
  sequenceNumber: 3
  sequenceSize: 4
~~~

By default, Spring Integration uses the framework's sequencing headers for Resequencer. When a Splitter creates child messages, the framework can add `correlationId`/`sequenceNumber`/`sequenceSize`. When messages arrive over HTTP or an external broker, the application must **verify** these values rather than blindly copying them into internal headers.

### 3.1. Technical Correlation ID Is Not Automatically the Business ID

Distinguish three identities:

- **businessStreamId**: e.g., `shipment-880`, stable for one business stream.
- **correlationId**: distinguishes the message set to resequence within one attempt/epoch.
- **eventId**: identifies **one logical event** to support deduplication/redelivery.

If you reuse a completed `correlationId` to send a **new sequence** of different messages, the old group may treat them as late and discard them. Conversely, if you change `correlationId` for a **redelivery of an old sequence**, Resequencer may treat it as a brand-new group.

Therefore, you need a way to identify the sequence's **generation/epoch/version**. Example:

~~~text
businessStreamId = shipment-880
sequenceEpoch = 17
correlationId = shipment-880:17
~~~

Increment the epoch only for a **genuinely new sequence**, never unconditionally when retrying the same sequence. Keep `eventId` stable across redeliveries.

### 3.2. `SequenceSize` May Be Unknown Upfront

If upstream does not know how many messages will belong to the group or uses a streaming source, `sequenceSize` may be missing/unusable. Waiting for `sequenceSize` is then no longer a valid completion criterion.

Choose another protocol: **end-of-stream marker**, sequence manifest, time window, deadline, or workflow state. Never pretend `sequenceSize=4` just because four messages have arrived so far; a fifth message might still be in flight.

## 4. "Release" Has at Least Three Contexts

The word **release** is easily misunderstood because there are multiple moments:

1. **Full-group release:** Resequencer has received all required messages and emits them in order. The group is marked complete, usually retaining metadata for a period.
2. **Contiguous-segment release:** with **`releasePartialSequences(true)`**, a valid prefix can emit early while the group still awaits later parts.
3. **Timeout release or expiry:** the group is incomplete, yet timeout policy decides either to emit buffered messages or discard them.

A message arriving "after release" means different things across these three cases.

### 4.1. Full Release by Default

Spring Integration documents **`releasePartialSequences`** as defaulting to **false**. Without partial emission, Resequencer waits until the group satisfies sequence completion metadata, then emits messages in order.

~~~text
Receive: 3 -> 1 -> 4 -> 2
After 3: wait
After 1: wait
After 4: wait
After 2: group 1..4 complete
Emit: 1, 2, 3, 4
Group: COMPLETED
~~~

Afterward, a **repeated message 2** with the same `correlationId` is a late arrival hitting a completed group.

### 4.2. Releasing Contiguous Prefixes Incrementally

With **`releasePartialSequences(true)`**, the framework can emit sequence parts **contiguously from the next valid position**, rather than waiting for the entire sequence. The following illustrates:

~~~text
Receive 2: no prefix 1..n yet -> wait
Receive 1: have 1,2 -> emit 1,2
Receive 4: missing 3 -> hold 4
Receive 3: have 3,4 -> emit 3,4
Group: COMPLETED
~~~

Message 3 here **arrived after 1,2 had released**, yet **is not a late message to discard**: it arrived to fill a gap in an active group.

If an operator sees "3 arrived after 1,2 emitted" and blocks 3 as a duplicate, the pipeline will **lose valid data**.

### 4.3. Partial Release on Expiry

Suppose 1,2,4 arrived, **3 never arrived**, and a timeout forces the group to close:

~~~text
Expected 1..4
Arrived 1,2,4
Group timeout
Policy: sendPartialResultOnExpiry = true
Output on expiry: messages eligible to emit in order
Group: closed per timeout policy
Arrives later: message 3
~~~

Here message 3 is a **late arrival after timeout**. If the framework retains empty-group metadata, it can be discarded instead of altering already-emitted output.

**Note:** do not assume every timeout setup emits exactly "1,2,4" without checking release strategy, sequence gaps, and Spring Integration version. Actually test what emits on expiry and how groups close.

## 5. Decision Table: Where Does a Late Message Go?

| Group State | Arriving Message | Expected Behavior / Handling |
| --- | --- | --- |
| Waiting for 1–4, has 2,4 | 1 | Adds 1; if partial release, may emit 1,2 |
| Prefix 1,2 released, holding 4 | 3 | Fills gap, then may emit 3,4 |
| Group 1–4 completed, metadata kept | Duplicate 2 | Late/duplicate → `discardChannel` if configured |
| Group timed out, tombstone metadata kept | Very late 3 | Late → discard/quarantine per policy |
| Group completely deleted from store | Old 2 | Can spawn a new group; very dangerous without dedup |
| New `correlationId` but same `eventId` | Old event | May enter new group; needs event-level dedup |
| Waiting group receives same `sequenceNumber` twice | Pre-release duplicate | Needs dedup/validation; do not treat as two positions |
| Group completed but new sequence reuses wrong `correlationId` | Valid message of new epoch | May be wrongly discarded; must separate epochs |

**Principle:** Resequencer understands **groups and order**; it does not decide on its own whether an old message should be *reopened*, *dropped*, *replayed*, or *reconciled* in business logic. The late-arrival policy must be declared and tested.

## 6. Why Does Spring Integration Retain Empty Group Metadata?

Suppose a sequence emits complete 1,2,3,4. Waiting payloads are sent to output. However, if the system **immediately erases every trace of the group**, when message #2 is redelivered, the resequencer no longer knows this group **already completed**.

~~~mermaid
flowchart TD
    A["Group G-880 has 1,2,3,4"] --> B["Release 1,2,3,4"]
    B --> C{"Retain completed metadata?"}
    C -->|"Yes"| D["Empty completed group / tombstone"]
    C -->|"No, or already cleaned up"| E["Group no longer in store"]
    D --> L["Late msg #2"] --> X["Discard / audit late"]
    E --> M["Late msg #2"] --> N["Create new group G-880"]
    N --> O["Wait for missing 1,3,4; or time out again"]
~~~

Spring Integration retains released group state to **detect and drop subsequent arrivals**. Aggregator/Resequencer documentation refers to these as **empty groups**: released message payloads may no longer sit in the store, yet completed-group metadata remains valuable for late-arrival handling.

This is analogous to a **tombstone** in distributed state management: a marker saying "this group existed and has ended."

### 6.1. Retaining Metadata Does Not Mean Keeping Payloads Forever

A completed group no longer holds waiting message payloads, yet still occupies memory/space in `MessageGroupStore` for group metadata. Keeping metadata long enough detects late replies, while keeping it **forever** causes memory/DB growth.

Therefore you need:

- A retention window covering the realistic **maximum redelivery time**.
- Cleanup/reaper mechanisms aligned with retention.
- A **more durable business dedup source** if messages can redeliver after group metadata is purged.
- Metrics measuring retained completed groups and late messages.

You cannot simultaneously **wipe all state completely** and still guarantee accurate detection of arbitrary old redeliveries indefinitely.

### 6.2. How Does `expireGroupsUponTimeout(false)` Help?

When a group **times out**, **`expireGroupsUponTimeout`** controls what happens to group state after timeout. Documentation describes the default as **false**: retaining empty group metadata so late arrivals can be recognized and discarded. When set to **true**, the framework may delete the group entirely, allowing a later message with the same `correlationId` to spawn **a brand-new group**.

In a timeout caused by missing sequence #3:

~~~text
Old group: 1,2,4
Timeout, marked closed and metadata retained
Message #3 arrives later:
  -> sees old group is closed
  -> discard/quarantine if configured
~~~

Conversely:

~~~text
Old group: 1,2,4
Timeout, group completely deleted
Message #3 arrives later:
  -> no old group found
  -> may create a new group holding only #3
  -> new group unlikely to reach 1..4, keeps waiting or times out
~~~

**Do not set `expireGroupsUponTimeout(true)` solely to save memory** without another dedup/late-arrival mechanism. For critical workflows, treat it as a **semantics-changing decision**, not merely a resource optimization.

### 6.3. Normal Completion vs. Timeout Expiration

Distinguish two termination types:

| Termination Type | Why Did It End? | Post-Termination Question |
| --- | --- | --- |
| **Completed** | Received all messages per release strategy | Must duplicate sequences still be blocked longer? |
| **Timeout/Expired** | Incomplete at deadline, policy forced closure | Should late-arriving missing messages trigger compensation? |
| **Manually closed** | Operator/workflow chose to terminate | Is reopening under a new epoch allowed? |

Settings for retaining metadata after completion vs. after timeout do not always share identical APIs or behaviors across versions. When implementing, read the Javadoc of **`ResequencerSpec`/`AbstractCorrelatingMessageHandler`** for your actual dependency.

## 7. `MessageGroupStore` and Timely Group Cleanup

Spring Integration offers several `MessageGroupStore` options for group state:

- **In-memory store**: simple, fits demos or short sequences, but loses state on restart.
- **Persistent store** like JDBC/Redis/Mongo depending on module: used when state recovery and tombstones must survive restarts.
- **Shared store**: useful when multiple instances process groups, though requiring proper locking and concurrency control.

A persistent store **does not automatically** provide end-to-end exactly-once delivery: it persists group state, while downstream side effects must still be idempotent.

### 7.1. `MessageGroupStoreReaper`

Spring Integration docs mention **`MessageGroupStoreReaper`** to clean up long-lived groups. For a resequencer, the reaper is not just a message deleter:

- It can expire unreleased **partial groups**.
- It can purge **empty completed groups** after an interval.
- Once group metadata is purged, the ability to detect late arrivals via that group **disappears**.

**`minimumTimeoutForEmptyGroups` / `empty-group-min-timeout`** allows keeping completed group metadata longer than partial groups in supporting configurations. Actual cleanup timing also depends on reaper/scheduler cadence and timeouts; never assume millisecond-exact deletion.

### 7.2. Budgeting Retention from Broker Characteristics

Do not pick a 30-second retention just because a demo runs in 30 seconds. For a real system:

| Parameter | Question to Answer |
| --- | --- |
| **Max redelivery delay** | How long after initial send can the broker redeliver? |
| **Offline recovery window** | How long can a consumer stay offline before recovery? |
| **Retry/DLQ replay** | How much later might operators replay messages from DLQ? |
| **Business correction window** | Can an already-completed event be corrected? |
| **Available store capacity** | How many groups' metadata can stay stored concurrently? |
| **Dedup ledger lifetime** | Once a group is purged, how long is the business key still protected? |

Illustrative retention budget:

~~~text
Resequencer active group timeout:        2 minutes
Completed-group metadata retention:     24 hours
Business dedup ledger retention:        30 days
Operator reprocess window:              30 days
~~~

These numbers are **not Spring Integration defaults** and do not fit every system. The key is that completed-group metadata only protects **while it remains in the store**; beyond that window, a durable ledger keyed by `eventId`/business key must continue guarding side effects.

### 7.3. State Loss on Restart

Scenario:

1. JVM A finishes releasing 1,2,3,4; completed metadata sits in an in-memory store.
2. JVM A restarts; store is empty.
3. Broker redelivers message 2 with the same `correlationId`.
4. Resequencer has no tombstone left and may spawn a new group.

When old side effects must not replay after restarts, use persistent stores/ledgers and design ACKs/transactions carefully. Never evaluate late behavior solely inside a single continuously running process.

### 7.4. Multiple Instances and Ownership Boundaries

If messages 1,2 reach instance A while 3,4 reach instance B, each using a separate in-memory `MessageGroupStore`, neither instance ever sees complete 1..4.

Common options:

1. Broker partitions/routes by **`correlationId`** so the whole group goes to one owner.
2. Shared `MessageGroupStore` with appropriate **`LockRegistry`/transactions** to prevent cross-instance races.
3. A workflow coordinator persisting state keyed by `businessStreamId`/epoch.

Sharing a database without locking/ownership does not fix races between two workers updating the same group. Integration test concurrent arrivals and failovers.

## 8. Discard Channel Is Where You Observe Late Messages

When a message arrives after its group was marked complete, Spring Integration can send it to **`discardChannel`** if configured. This differs from:

- **`errorChannel`**: receives `ErrorMessage` when processing throws exceptions in matching setups.
- **Dead-letter queue (DLQ)**: where a broker or app parks messages unprocessable after retries.
- **`outputChannel`**: normal path for messages released in sequence.

~~~mermaid
flowchart TD
    M["Incoming sequenced message"] --> R["Resequencer"]
    R -->|"Valid & ready to release"| O["orderedOutputChannel"]
    R -->|"Group completed/late"| D["lateDiscardChannel"]
    R -.->|"Processing exception"| E["errorChannel / caller"]
    D --> P["Audit / metric / quarantine"]
~~~

### 8.1. Why Not Drop Late Messages Silently?

A late arrival can signal:

- Normal broker redelivery while consumer remains safe.
- Lost ACK after downstream already processed the message.
- Group retention too short.
- Producer mistakenly reusing `correlationId`.
- One branch running too slowly or suffering queue starvation.
- Missing business data arriving after a timeout.

Not every late message needs reprocessing, yet it **should be observed and classified**. At minimum track **`late_messages_total`** by kind, component, and bounded-cardinality source.

### 8.2. Never Route All Late Messages Back Into Resequencer

Anti-example:

~~~text
Resequencer -> discardChannel -> same resequencer input
~~~

If the group still holds a completed tombstone, the message is discarded again in a loop. If the group was deleted, it can spawn a new group and time out again. Discard paths should terminate in audit/quarantine or an explicit **replay coordinator**, never feeding messages unconditionally back around.

### 8.3. Discard Does Not Mean the Whole Request Failed

If sequence 1..4 already released and processed successfully, discarding a duplicate message 2 is the **desired** behavior. Never mark the entire workflow failed merely because late metrics rise; first separate **duplicate redelivery** from **first-time missing events arriving after timeout**.

## 9. Late Messages Can Be Valid: Do Not Drop Just Because They Are "Late"

A message arriving after a technical deadline is not necessarily worthless to the business. Examples:

- Payment confirmation arrives after a report was emitted as `INCOMPLETE`.
- Sensor telemetry arrives late, yet analytics still wants historical tables updated.
- A business adjustment is approved after the initial sequence ended.

For these cases, three policies are common:

| Policy | When Applied | What Else Is Needed? |
| --- | --- | --- |
| **Freeze** | Already-emitted output is considered final | Discard/audit late message; never alter output |
| **Correction** | Allows updating previously published results | Revision/compensation; downstream supports edits |
| **New epoch** | Event belongs to a new sequence, not old replay | New correlation, mapped from `businessStreamId` |

Merely flipping **`expireGroupsUponTimeout(true)`** does not turn an old message into a valid correction. Amending historical results requires a **business workflow** creating a correction/revision with new identity, auditing, and proper side effects.

### 9.1. Freeze Example

Sequence #1–#4 produces a final shipping report; a late duplicate of #2 is simply logged:

~~~text
Result version 1: FINAL
Late event #2: DUPLICATE_REDELIVERY
Action: DISCARD_AND_COUNT
~~~

### 9.2. Correction Example

After timeout, the system emitted an `INCOMPLETE` report missing #3. When #3 later arrives:

~~~text
Result version 1: INCOMPLETE, missing=[3]
Late event #3: FIRST_ARRIVAL_AFTER_DEADLINE
Action: create correction proposal
Result version 2: RECONCILED, if business rules permit
~~~

Never mutate version 1 in place if downstream may already have used it for billing/payment. A correction must track who was notified and whether compensating side effects are needed.

### 9.3. New Epoch Example

Group `shipment-880:17` completed. A new state sequence begins upon transfer to another warehouse:

~~~text
Old correlationId: shipment-880:17
New correlationId: shipment-880:18
~~~

If the new message still carries `shipment-880:17`, it may be treated as late. The producer must intentionally mint epoch 18 and keep it stable across retries of that epoch.

## 10. Java 17: Event Model and Test Data

To separate **technical ordering** from **business identity**, the example model uses:

~~~java
record ShipmentStepEvent(
        String eventId,
        String shipmentId,
        int epoch,
        int position,
        String eventType) {

    ShipmentStepEvent {
        if (eventId == null || eventId.isBlank()
                || shipmentId == null || shipmentId.isBlank()
                || epoch <= 0
                || position < 1
                || position > 4
                || eventType == null || eventType.isBlank()) {
            throw new IllegalArgumentException(
                    "INVALID_SHIPMENT_STEP_EVENT");
        }
    }
}
~~~

Here **`position`** is business metadata for testing and auditing; actual Resequencer sorting relies on the **`sequenceNumber` header**. In production, verify `position` and the `sequenceNumber` header match. If producers can attach wrong or spoofed headers, validate at ingress before entering Resequencer.

An internal message factory:

~~~java
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

final class ShipmentMessages {
    private ShipmentMessages() {}

    static Message<ShipmentStepEvent> sequenced(
            ShipmentStepEvent event) {

        String group = event.shipmentId() + ":" + event.epoch();

        return MessageBuilder.withPayload(event)
                .setHeader(
                        IntegrationMessageHeaderAccessor.CORRELATION_ID,
                        group)
                .setHeader(
                        IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER,
                        event.position())
                .setHeader(
                        IntegrationMessageHeaderAccessor.SEQUENCE_SIZE,
                        4)
                .setHeader("businessEventId", event.eventId())
                .build();
    }
}
~~~

**Trust boundary note:** the example constructs headers in internal code. Never let HTTP client inputs arbitrarily dictate `correlationId`, `sequenceSize`, `replyChannel`, or `errorChannel` without authentication and validation. If a flow handles sequence types with differing lengths, read `sequenceSize` from a trusted manifest instead of hard-coding 4.

## 11. Java DSL: Resequencer Releasing Only When Group Is Complete

When **no messages may emit before the group is complete**, start with an explicit configuration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
class CompleteSequenceResequencerConfig {

    @Bean
    MessageChannel sequenceInputChannel() {
        return new DirectChannel();
    }

    @Bean
    QueueChannel orderedStepsChannel() {
        return new QueueChannel();
    }

    @Bean
    QueueChannel lateSequenceDiscardChannel() {
        return new QueueChannel();
    }

    @Bean
    IntegrationFlow resequenceShipmentSteps() {
        return IntegrationFlow.from("sequenceInputChannel")
                .resequence(r -> r
                        .releasePartialSequences(false)
                        .sendPartialResultOnExpiry(false)
                        .expireGroupsUponTimeout(false)
                        .discardChannel("lateSequenceDiscardChannel"))
                .channel("orderedStepsChannel")
                .get();
    }
}
~~~

**Key points:**

1. **`releasePartialSequences(false)`**: waits for full group completion before emitting the sequence.
2. **`sendPartialResultOnExpiry(false)`**: never emits incomplete parts as a successful sequence merely because the group expired.
3. **`expireGroupsUponTimeout(false)`**: if the group times out/expires per configuration, retains metadata for late-arrival handling.
4. **`discardChannel`**: provides a place to observe messages treated as late/unadmitted to a group.
5. **`QueueChannel`** on output/discard is only for easy test assertions. Production requires consumers or bounded stores rather than unbounded in-memory queues.

**Important distinction:** the template above has no `groupTimeout`/reaper declared yet. Thus a group permanently missing message 3 could wait indefinitely without an expiration policy. Add timeout/reaper settings when the real application must resolve incomplete groups.

### 11.1. Adding a Deadline and Handling Incomplete Groups

The DSL snippet below illustrates a policy when a group waits too long:

~~~java
.resequence(r -> r
        .releasePartialSequences(false)
        .groupTimeout(30_000)
        .sendPartialResultOnExpiry(false)
        .expireGroupsUponTimeout(false)
        .discardChannel("lateSequenceDiscardChannel"))
~~~

With this policy, an incomplete group expires rather than releasing as a complete sequence. **`groupTimeout` triggers based on group activity and scheduler mechanics**; do not assume it is an exact 30-second wall-clock deadline from the first event. If an immutable business deadline is required, track a dedicated state/deadline by `businessStreamId`.

In systems needing replay, add a persistent `MessageGroupStore` and appropriate timeout/reaper; configure **`messageStore(...)`**, **`taskScheduler(...)`**, and **`minimumTimeoutForEmptyGroups(...)`** according to your version and store type.

### 11.2. XML Is an Alternative Configuration Style

An XML-based application can configure the equivalent resequencer:

~~~xml
<int:resequencer
    input-channel="sequenceInputChannel"
    output-channel="orderedStepsChannel"
    discard-channel="lateSequenceDiscardChannel"
    release-partial-sequences="false"
    send-partial-result-on-expiry="false"
    expire-group-upon-timeout="false" />
~~~

This is an **XML fragment** assuming the `int` namespace and channels are declared. For active expiration, configure group timeout/scheduler or a reaper separately. Option names between Java DSL and XML can differ slightly; check the exact API for your Spring Integration version.

## 12. Java DSL: Allowing Contiguous Partial Sequence Release

An order-progress display might want to emit **contiguous steps from the start** immediately without waiting for all 4 steps.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
class ContiguousPrefixResequencerConfig {

    @Bean
    MessageChannel prefixInputChannel() {
        return new DirectChannel();
    }

    @Bean
    QueueChannel prefixOutputChannel() {
        return new QueueChannel();
    }

    @Bean
    QueueChannel prefixLateDiscardChannel() {
        return new QueueChannel();
    }

    @Bean
    IntegrationFlow prefixResequenceFlow() {
        return IntegrationFlow.from("prefixInputChannel")
                .resequence(r -> r
                        .releasePartialSequences(true)
                        .sendPartialResultOnExpiry(false)
                        .discardChannel("prefixLateDiscardChannel"))
                .channel("prefixOutputChannel")
                .get();
    }
}
~~~

Example send sequence:

~~~text
Send 1  -> emit 1
Send 2  -> emit 2
Send 4  -> wait for 3
Send 3  -> emit 3,4
Group   -> completed
~~~

**Meaning:** message 3 is not an error just because it arrived after 1,2 released. It is the **awaited missing element**. Only once the group has completed/expired per policy while closed metadata remains active does a message fall under late discard.

### 12.1. Do Not Use Partial Release for Every Business Flow

If step #2 **holds funds** and step #3 **checks fraud**, while business rules only permit recording the chain once 1..4 are complete, emitting prefix 1,2 early could trigger irreversible side effects.

Choose:

- **Full release** when downstream needs integrity of the entire sequence before acting.
- **Partial contiguous release** when each valid step can proceed immediately without knowing the future and recovery exists if later steps fail to arrive.

Never choose `true` simply to lower average latency; evaluate the semantics of downstream actions.

## 13. Integration Test: Late Message After Completed Group Is Discarded

The test below uses **JUnit 5 + spring-test** with the config from section 11. It sends events 3,1,2 and verifies no output yet; sends 4 to complete and receives 1,2,3,4 in order; then sends a **duplicate #2** in the same group and verifies it does not appear on output, routing instead to the discard channel.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(CompleteSequenceResequencerConfig.class)
class LateAfterCompleteResequencerTest {

    @Autowired
    @Qualifier("sequenceInputChannel")
    MessageChannel input;

    @Autowired
    @Qualifier("orderedStepsChannel")
    QueueChannel output;

    @Autowired
    @Qualifier("lateSequenceDiscardChannel")
    QueueChannel discarded;

    @BeforeEach
    void clearQueues() {
        while (output.receive(0) != null) {
            // Clear test queue.
        }
        while (discarded.receive(0) != null) {
            // Clear test queue.
        }
    }

    private ShipmentStepEvent event(int n) {
        return new ShipmentStepEvent(
                "evt-880-" + n, "shipment-880", 17, n,
                "STEP_" + n);
    }

    private void send(int n) {
        assertTrue(input.send(
                ShipmentMessages.sequenced(event(n))));
    }

    @Test
    void completedGroupDiscardsLateDuplicate() {
        send(3);
        send(1);
        send(2);
        assertNull(output.receive(0));

        send(4);
        List<Integer> emitted = new ArrayList<>();
        for (int i = 0; i < 4; i++) {
            Message<?> next = output.receive(0);
            assertNotNull(next);
            emitted.add(
                    ((ShipmentStepEvent) next.getPayload()).position());
        }
        assertEquals(List.of(1, 2, 3, 4), emitted);
        assertNull(output.receive(0));

        send(2); // Same correlationId and sequenceNumber.
        assertNull(output.receive(0));

        Message<?> late = discarded.receive(0);
        assertNotNull(late);
        assertEquals(2,
                ((ShipmentStepEvent) late.getPayload()).position());
    }
}
~~~

**What this test proves inside a single non-restarting JVM:**

- When `releasePartialSequences=false`, output does not emit before the group completes.
- Resequencer emits messages in ascending `sequenceNumber` order.
- Once the group completes and metadata remains, a subsequent duplicate is not emitted as a normal message.
- Discard channel lets us observe the late message.

This test **does not prove** persistent store/reaper behavior across restarts, duplicates when two workers send concurrently, or idempotent downstream side effects. Those require separate integration tests.

### 13.1. Note on Test Independence

Reusing the same `correlationId` across multiple tests in one Spring context can cause leftover completed-group metadata to unexpectedly discard messages in later tests. Give each test a **unique `correlationId`/epoch**, or create separate contexts/stores per test. Draining the output `QueueChannel` alone does not clear `MessageGroupStore`.

## 14. Integration Test: Gap-Filling vs. Late Duplicate

With `ContiguousPrefixResequencerConfig` from section 12, send order **1, 2, 4, 3** shows:

- 1 emits because the prefix started.
- 2 emits immediately following 1.
- 4 waits for message 3.
- 3 arrives later as a **valid unreleased element**; 3 and 4 emit in order.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(ContiguousPrefixResequencerConfig.class)
class PrefixGapResequencerTest {

    @Autowired
    @Qualifier("prefixInputChannel")
    MessageChannel input;

    @Autowired
    @Qualifier("prefixOutputChannel")
    QueueChannel output;

    @Autowired
    @Qualifier("prefixLateDiscardChannel")
    QueueChannel late;

    private void send(int position) {
        ShipmentStepEvent event = new ShipmentStepEvent(
                "evt-prefix-" + position,
                "shipment-prefix", 1, position,
                "STEP_" + position);
        assertTrue(input.send(
                ShipmentMessages.sequenced(event)));
    }

    private int nextPosition() {
        Message<?> message = output.receive(0);
        assertNotNull(message);
        return ((ShipmentStepEvent) message.getPayload()).position();
    }

    @Test
    void missingPositionIsNotDiscardedWhileGroupIsOpen() {
        send(1);
        assertEquals(1, nextPosition());

        send(2);
        assertEquals(2, nextPosition());

        send(4);
        assertNull(output.receive(0)); // Still waiting for step #3.

        send(3);
        assertEquals(List.of(3, 4),
                List.of(nextPosition(), nextPosition()));
        assertNull(output.receive(0));
        assertNull(late.receive(0));
    }
}
~~~

**This test adds a key perspective:** never add an interceptor that rejects every message whose `sequenceNumber` is above or below some time-based guess. Inspect the open group, already-released positions, awaited gaps, and timeout policy.

### 14.1. After Partial Release Before Completion, What About Old Duplicates?

Suppose 1 and 2 have emitted, while 3 and 4 have not arrived yet. If message 1 is redelivered:

~~~text
Released prefix: 1,2
Expected next: 3
Incoming: 1 (duplicate)
~~~

An application must ensure **1 is not emitted again**; however, whether the framework discards/ignores it or how the group handles duplicates prior to completion depends on release strategy configuration and version. If reliable tracking is needed, add **deduplication by `eventId`/position** at the right boundary and test directly against your target version.

Never assume every duplicate in an incomplete group routes to `discardChannel` identically to late messages on a completed group. Those are two separate states requiring separate tests.

## 15. Testing Timeouts and Late Arrivals After Expiry

Real-clock tests using `Thread.sleep` easily flake in CI. A reliable integration test plan controls **`TaskScheduler`** or uses bounded await utilities, creates an incomplete group, and triggers expiration deterministically.

### 15.1. Core Scenario Set

| Step | Action | Outcome to Observe |
| --- | --- | --- |
| 1 | Send 1,2,4 of group G | Group incomplete due to missing `#3` |
| 2 | Reach `groupTimeout` with `sendPartialResultOnExpiry=false` | Never falsely emits full ordered sequence |
| 3 | `expireGroupsUponTimeout=false` | Group metadata retained to detect late arrivals |
| 4 | Send `#3` after timeout | Does not silently patch closed result |
| 5 | Enable `discardChannel` | Late `#3` observed or stored per policy |
| 6 | Test with `expireGroupsUponTimeout=true` | Old group deleted; `#3` may spawn a new group |
| 7 | Check reaper cleanup | Metadata eventually purged per retention |

**Key caution:** with timeouts, groups may be processed by a scheduler; tests should wait for a **group-expired event** or inspect store state rather than merely sleeping for the configured millisecond duration.

### 15.2. Avoid Testing "Nothing Emitted" with an Unbounded Wait

If a test blocks indefinitely on `QueueChannel` when a group never releases, the test hangs. Use:

~~~java
Message<?> unexpected = orderedOutput.receive(200);
assertNull(unexpected);
~~~

Here **200 ms** is an example check window; design tests around real schedulers, events, and timeouts so they never flake. `receive(200)==null` only proves **no output was seen within that window**, not that output will never appear later if a scheduler keeps running.

### 15.3. Testing Both Timeout Policies

For the same sequence missing `#3`:

- **No partial, retain metadata:** group closes per policy; late `#3` produces no successful output.
- **Partial enabled:** available messages emit per timeout policy; downstream report must show **missing `#3`** and never treat the sequence as fully complete.

Resequencer does not auto-generate an **`INCOMPLETE` `BatchReport`**. If business logic needs to know which positions are missing, maintain a **sequence manifest** or separate workflow state store to reconcile against. Observing output 1,2,4 alone does not prove `#3` never existed.

## 16. When Group Metadata Is Purged: Deduplicating at the Business Layer

Even when Resequencer operates properly, a broker redelivery after completed-group metadata expires beyond retention can be treated as a new group. When downstream executes side effects, guard **at the exact point where effects occur**.

Suppose the handler after Resequencer writes a shipment audit record:

~~~text
Event: evt-880-2
Business stream: shipment-880
Epoch: 17
Sequence position: 2
Operation: record-shipment-step
~~~

A stable identity:

~~~text
effectKey =
    trustedTenantId
    + ":" + businessStreamId
    + ":" + epoch
    + ":" + eventId
    + ":" + logicalActionId
~~~

If `eventId` is already globally unique across tenants and actions, the key can be simplified; if `eventId` is only unique per stream, include stream/epoch. Declare the uniqueness scope explicitly rather than concatenating arbitrary strings.

### 16.1. Table Recording Executed Effects

~~~sql
CREATE TABLE shipment_step_execution (
    tenant_id VARCHAR(80) NOT NULL,
    shipment_id VARCHAR(80) NOT NULL,
    epoch INTEGER NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    action_id VARCHAR(80) NOT NULL,
    sequence_position INTEGER NOT NULL,
    status VARCHAR(24) NOT NULL,
    processed_at TIMESTAMPTZ,
    PRIMARY KEY (
        tenant_id, shipment_id, epoch, event_id, action_id
    )
);
~~~

Example transaction recording an event for the first time:

~~~sql
INSERT INTO shipment_step_execution (
    tenant_id, shipment_id, epoch, event_id,
    action_id, sequence_position, status, processed_at
) VALUES (
    :tenant, :shipment, :epoch, :eventId,
    :action, :position, 'COMPLETED', CURRENT_TIMESTAMP
)
ON CONFLICT DO NOTHING;
~~~

If a row with that key already exists, the app checks existing status and skips repeating side effects. Yet **`ON CONFLICT DO NOTHING`** only guards this INSERT; if inventory updates, HTTP calls, or shipment creation also run, coordinate transactions, outboxes, or external service idempotency properly.

### 16.2. Writing Idempotency Record and Effect in the Same Transaction

When effects live in the same database, a service can insert the ledger entry and update business state in **the same transaction**. If the transaction rolls back, both changes roll back together. If it commits and the message redelivers, the unique constraint/ledger prevents duplicate effects.

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant R as Resequencer
    participant S as Domain Service
    participant DB as Database
    B->>R: event E (first delivery)
    R->>S: ordered E
    S->>DB: TX: claim E + apply effect
    DB-->>S: Commit
    B->>R: event E (late redelivery)
    Note over R: If metadata kept: discard
    R-->>B: late discard
    Note over S: If metadata lost and E returns
    R->>S: E once more
    S->>DB: TX: claim E
    DB-->>S: Already completed
~~~

**Two complementary defense layers:**

- **Resequencer metadata** manages ordering and group lifecycles.
- **Business idempotency** protects side effects even after group metadata expires.

### 16.3. External Side Effects Cannot Roll Back via DB

If downstream sends emails or calls a payment provider, a database transaction cannot undo an external call that already succeeded.

You need:

1. **Idempotency keys** supported by the provider.
2. An `UNKNOWN` state when a request may have executed before the response was lost.
3. Lookup/reconciliation before issuing new side-effecting commands.
4. Outbox or reliable delivery mechanisms to recover across crashes.
5. Late-event policies keyed to the business operation, not just `sequenceNumber`.

No Resequencer setting creates system-wide exactly-once effects on its own.

## 17. Which Data Detects Late Messages?

Never just compare **event timestamp** against the receive clock. A message with an old timestamp can still arrive on time for an incomplete group; a message with a fresh timestamp can still be a duplicate.

Classify using:

| Signal | What It Determines | Limitation |
| --- | --- | --- |
| **`correlationId` + epoch** | Which group the message belongs to | Can be misused if reused |
| **`sequenceNumber`** | Position in group | Not a system-wide unique identity |
| **`eventId`** | Whether logical event was seen/completed | Must be kept stable and unique |
| **Group status** | `ACTIVE`, `COMPLETED`, or `EXPIRED`? | Can be lost after cleanup/restart |
| **Last released position** | Which prefix already emitted | Needs durable state if critical |
| **Business deadline** | Until when results can still be amended | Not equivalent to `groupTimeout` |
| **Ledger effect status** | Whether side effect already committed | Must share transaction / proper reconciliation |

### 17.1. An Application-Level Decision Algorithm

~~~text
Receive sequenced message
  -> verify tenant, eventId, epoch, and sequence bounds
  -> check if business event/operation is already COMPLETED?
      -> Yes: mark duplicate, produce no new side effect
      -> No:
          -> group ACTIVE, position still missing: submit to Resequencer
          -> group COMPLETED/EXPIRED:
               -> policy FREEZE: audit/discard
               -> policy CORRECTION: spawn revision workflow
               -> policy NEW_EPOCH: accept only with new epoch
          -> group does not exist:
               -> check ledger/manifest before treating as a new group
~~~

This is an **application-layer policy**, not Resequencer's built-in algorithm. In real deployments, handle concurrency, ownership, and transactions before acting on this state.

### 17.2. Duplicate vs. First-Time Missing Event

Two late-arrival types have opposite requirements:

~~~text
LATE_DUPLICATE:
  eventId already processed before group closed
  → do not re-execute; only audit/count

LATE_FIRST_ARRIVAL:
  eventId never processed
  group expired due to missing position
  → freeze/quarantine or correction per policy
~~~

If you treat both as late and drop them blindly, the system can **miss reconciling an event that was truly never processed**. Conversely, processing everything risks duplicate effects. Classifying by event identity and durable state is the key.

## 18. Common Pipeline Bugs with Resequencer

### 18.1. Adding a Filter Before Resequencer Without Updating Completion

Suppose producer sends four messages with `sequenceSize=4`, and a Filter drops message `#3`. Resequencer receives only 1,2,4 and may wait forever.

~~~mermaid
flowchart LR
    P["Producer 1,2,3,4"] --> F["Filter"]
    F -->|"1,2,4"| R["Resequencer"]
    F -.->|"3 dropped"| D["Discard"]
    R --> X["Wait for #3 or time out"]
~~~

If message `#3` is **genuinely unneeded**, rebuild the manifest/sequence before attaching sequence metadata, or emit a contract-bound failure/skip marker carrying identity. Never quietly rewrite `sequenceSize` to 3 on individual messages to mask a missing member.

### 18.2. Mutating `sequenceNumber` Inside a Transformer

A Transformer may construct a new `Message` and alter headers. If `sequenceNumber` turns into arrival order instead of producer logical order, Resequencer can no longer fix scrambled order.

Test **header propagation** across Transformers, Routers, Splitters, Gateways, and adapters; avoid minting accidental new business `eventId`/`correlationId` values mid-group.

### 18.3. Sharing One `correlationId` Across Independent Requests

Two shipments both have `sequenceNumber=1..4`. If both use `correlationId="current"`, Resequencer merges messages from both shipments into one group.

~~~text
shipment-A seq1 --> group "current"
shipment-B seq1 --> group "current"  // Wrong
~~~

Build `correlationId` from a sufficiently unique **business stream + epoch**. Verify tenant IDs in multi-tenant systems.

### 18.4. Deleting a Group to "Fix" a Missing Message

If a group is missing `#3` and an operator manually deletes the group then replays `#3`:

- The new group lacks `#1`, `#2`, `#4`.
- It will hang waiting forever.
- Knowledge that `#1`, `#2` may have already released or executed effects is lost.

To replay, use a workflow backed by manifests, event state, and deduplication—never treat **deleting the group** as a generic data-repair command.

### 18.5. Setting Timeouts Without Monitoring Late Arrivals

Group timeouts keep the app from waiting forever, yet messages arriving past the deadline still need classification. Without `discardChannel` or auditing, events dropped by timeout policies may go unnoticed until business reconciliation.

### 18.6. Treating Ordered Output Emission as Business Commit

Resequencer only emits messages in order. If a downstream handler subsequently writes to a database or calls a service and fails, proper emission order does not mean the effect completed. Design ACKs, retries, and transactions at the downstream consumer separately.

### 18.7. Allowing Late Replays to Mint a New `eventId`

If an operator replays an old event with a brand-new `eventId`, the business ledger sees it as a new event and executes side effects a second time. Replays of the same logical event must preserve a stable identity; intentional corrections should carry a **new operation/revision identity** linked to the prior event.

## 19. Observability and Alerting

A healthy Resequencer shows more than ordered output counts. Measure **how many groups are waiting, how many messages are buffered, and how many messages arrive after group closure**.

| Signal | Operational Meaning |
| --- | --- |
| **`resequencer_inbound_total`** | Messages entering Resequencer |
| **`resequencer_released_total`** | Messages emitted per release policy |
| **`resequencer_late_discard_total{reason}`** | Late messages discarded by reason |
| **`resequencer_duplicate_total`** | Duplicates by `eventId`/sequence identity |
| **`resequencer_gap_waiting_groups`** | Groups currently missing a position |
| **`resequencer_group_pending`** | Incomplete `MessageGroup`s |
| **`resequencer_group_age_seconds`** | Age of waiting groups |
| **`resequencer_group_timeout_total`** | Expired groups |
| **`resequencer_partial_release_total`** | Prefix/partial releases per policy |
| **`resequencer_empty_group_count`** | Retained completed-group metadata entries |
| **`resequencer_group_reaped_total`** | Groups/metadata cleaned up |
| **`resequencer_correlation_rejected_total`** | Messages with invalid group identity |
| **`resequencer_store_operation_failed_total`** | `MessageGroupStore` read/write errors |
| **`resequencer_discard_handler_failed_total`** | Late/discard handler failures |
| **`resequencer_recovery_attempts_total`** | Intentional recovery attempts |
| **`downstream_idempotency_skip_total`** | Prevented duplicate side effects |

Labels should come from small bounded sets: component, source, reason, deployment version. **Never put unbounded `eventId`, `shipmentId`, `tenantId`, or `correlationId` values into metric labels**, as cardinality explodes. Keep those IDs in access-controlled logs/traces with appropriate retention.

### 19.1. Log for a Late Duplicate

~~~json
{
  "eventId": "evt-880-2",
  "businessStreamId": "shipment-880",
  "sequenceEpoch": 17,
  "sequenceNumber": 2,
  "groupStatus": "COMPLETED",
  "classification": "LATE_DUPLICATE",
  "action": "DISCARD_AND_AUDIT"
}
~~~

### 19.2. Log for a First-Time Late Arrival

~~~json
{
  "eventId": "evt-880-3",
  "businessStreamId": "shipment-880",
  "sequenceEpoch": 17,
  "sequenceNumber": 3,
  "groupStatus": "EXPIRED",
  "classification": "LATE_FIRST_ARRIVAL",
  "action": "QUARANTINE_FOR_RECONCILIATION"
}
~~~

These are sample logs showing **business decisions after classification**, not the framework's default `ErrorMessage` or discard message structure. Log only needed metadata; avoid recording tokens, sensitive payloads, or untrusted control headers.

### 19.3. Alert-Worthy Conditions

1. Sharp spike in late duplicates after broker ACK/retry changes.
2. Rise in late first-time arrivals after deploying a slow processing branch.
3. Pending group count climbs steadily without timeouts/cleanup.
4. Completed empty groups grow while reaper is not running.
5. Discard rate jumps after shortening retention or restarting.
6. `MessageGroupStore` unavailable while consumers still ACK messages.
7. After failover, completed correlation groups reappear as new groups.
8. Duplicate `sequenceNumber` or conflicting `sequenceSize` inside the same group.
9. Previously committed side effect executes a second time after replay.
10. Operator corrections occur without clear audit trails and revision identities.

## 20. Runbook for Investigating a Late Message

When alerted on a late message, do not rush to resend it back into Resequencer. Determine:

### Step 1 — Verify Message Identity

Collect `eventId`, trusted tenant, `businessStreamId`, epoch, `correlationId`, `sequenceNumber`, `sequenceSize`, `schemaVersion`, and trace ID. Check whether header provenance is trustworthy. Never rely on message timestamps alone to declare a duplicate.

### Step 2 — Determine Group Lifecycle

Check whether the group is `ACTIVE`, `COMPLETED`, or `EXPIRED`; whether metadata still exists or was swept by the reaper; and whether a recent restart/failover happened. If no group exists, inspect the ledger/manifest and execution history before concluding this message belongs to a new sequence.

### Step 3 — Classify

| Label | Illustrative Condition | Starting Action |
| --- | --- | --- |
| `DUPLICATE_REDELIVERY` | Event effect already `COMMITTED` | Discard with audit |
| `GAP_FILLER_ACTIVE` | Group open and position unreleased | Admit through resequencing |
| `LATE_FIRST_ARRIVAL` | Group timed out, effect never ran | Quarantine/correction per policy |
| `NEW_EPOCH_MESSAGE` | Approved different sequence epoch | Handle as new group |
| `CORRELATION_COLLISION` | Two streams share one group ID | Block, fix producer, reconcile |
| `UNKNOWN_STATE` | Uncertain whether effect occurred | Reconcile before retrying |

### Step 4 — Check Downstream Impact

A message emitted by Resequencer is not guaranteed to have completed in the database. Cross-check service ledgers, transaction commits, provider idempotency responses, and outboxes—not just "dispatched successfully" logs.

### Step 5 — Choose Action

- **Freeze:** preserve prior result, discard/audit.
- **Correction:** create a new version/revision with necessary adjusting effects.
- **Replay:** retry with stable `eventId` if unprocessed and policy permits.
- **New epoch:** only for genuinely new business cycles, never for resending an old message.

### Step 6 — Monitor After Remediation

Reconcile expected, received, released, discarded, completed, and pending counts per logical stream. Confirm no duplicate side effects or silent missing events appeared.

## 21. Pre-Production Test Matrix

| Scenario | Key Observation |
| --- | --- |
| 3,1,4,2 with full release | Output 1,2,3,4 after group completes |
| 1,2,4,3 with partial release | 1,2 first; 3,4 later; 3 is not discarded |
| Duplicate `#2` after full completion | Not emitted twice; late discard recorded |
| Duplicate `#2` while group is `ACTIVE` | No duplicate effect; verified behavior |
| `#3` arrives after timeout, metadata kept | Classified as late; does not reopen old group |
| `#3` arrives after timeout, metadata purged | May spawn new group; business ledger protects |
| Restart with in-memory store | Risk of lost group state observed |
| Restart with persistent store | Completed/expired state preserved per retention |
| Two instances handle one group | No misordered release or double emission |
| Two groups concurrently | No cross-correlation mixing |
| `correlationId` reused for another epoch | Validation catches error or separates new group properly |
| `sequenceNumber` outside `1..sequenceSize` | Rejected/quarantined before resequencer |
| Inconsistent `sequenceSize` in one group | Blocked/alerted; no wrong release |
| Reaper cleans up completed group | State swept per retention; ledger still protects |
| Error/discard channel has no consumer | Monitoring catches failure; no silent data loss |
| Message `#2` redelivered after DB commit | Downstream does not apply effect twice |
| Intentional late correction | Carries revision and audit; never silently overwrites old result |

### 21.1. How to Test Restarts

An integration test using a database `MessageGroupStore` and application container can:

1. Send 1,2,3,4; wait for release and verify completed marker persisted.
2. Stop the application **without wiping the database**.
3. Restart the application pointing at the same store.
4. Resend message 2 with the same `correlationId`.
5. Verify it does not emit normally while the marker stays within retention.
6. After retention/reaper cleanup, resend and verify the **business dedup ledger** still blocks duplicate effects.

This is a **test plan**, not something inferred from an in-memory `QueueChannel` unit test. In STEP 4 we write guides and examples; content QA or actual test execution runs as a separate step.

### 21.2. How to Test Multiple Instances

Spin up two consumers receiving messages of the same correlation group. With a shared store, configure a lock registry/transactions to prevent races. Send interleaved 1–4 across both instances, followed by duplicate `#2`. Verify:

- One logical sequence releases in exact order.
- Zero duplicate effects.
- When one node crashes, the surviving node recovers the group or handles per failover policy.
- Late messages are classified consistently regardless of which node receives them.

Never treat a passing single-JVM local test as proof of safe distributed processing.

## 22. Practice Lab: Detecting Late Messages in an Order Fulfillment Flow

Build an `IntegrationFlow` tracking the 5 events of **one shipment**:

| Sequence | Event type | Meaning |
| ---: | --- | --- |
| 1 | SHIPMENT_REQUESTED | Request received |
| 2 | STOCK_CHECKED | Stock checked |
| 3 | STOCK_RESERVED | Stock reserved |
| 4 | LABEL_CREATED | Shipping label created |
| 5 | SHIPMENT_DISPATCHED | Handed over for shipping |

Inputs may arrive in order **3,1,2,5,4**, one or more messages may be redelivered by the broker, and message 4 may arrive after timeout.

### 22.1. Functional Requirements

1. Groups are identified by **`shipmentId + sequenceEpoch`**.
2. Each message carries a **stable `eventId`** and `sequenceNumber` in `1..5`.
3. Configure Resequencer for full-group wait or contiguous-prefix release, with tests proving your choice.
4. A late-arriving message **filling a gap while the group is still active** must continue in proper order.
5. A duplicate arriving after group completion must be observed via **`discardChannel`**, never emitted normally.
6. Group timeouts must enforce an explicit policy: freeze or correction; never synthesize a fake successful sequence.
7. Completed-group retention must match realistic redelivery windows.
8. Across restarts, side effects remain protected by a **durable idempotency ledger**.
9. A new epoch starts when the shipment begins a new business cycle, never on mere retries.
10. Tests cover duplicates, gaps, timeouts, late arrivals, and correlation collisions.

### 22.2. Implementation Steps

1. Design `ShipmentEvent` and a sequence manifest with `expectedSequenceSize=5`, `schemaVersion`, and trusted `tenantId`.
2. Build an internal helper creating `Message`s with `correlationId`, `sequenceNumber`, and `sequenceSize` headers.
3. Wire an `IntegrationFlow` from a `DirectChannel` → Resequencer → `QueueChannel`.
4. Declare a `discardChannel` with a consumer/queue to record late events per contract.
5. Write a test sending `3,1,2,5,4` and verifying output `1,2,3,4,5`.
6. Resend event `#2` after completion; verify it is not emitted again.
7. Create a `releasePartialSequences(true)` config, send `1,2,5,4,3`; verify prefix `1,2` emits early, then `3,4,5`.
8. Add an appropriate `groupTimeout` and simulate losing event `#4`; verify the whole sequence is never reported `COMPLETE`.
9. Compare `expireGroupsUponTimeout(false)` vs. `true` when event `#4` arrives after timeout.
10. Design a persistent `MessageGroupStore` and completed-group retention.
11. Implement a ledger keyed by `tenantId + shipmentId + epoch + eventId + actionId`, testing redelivery after commit.
12. Test restarts both while metadata remains and after metadata was swept by the reaper.
13. Test two instances receiving interleaved events, verifying locking/correlation.
14. Add metrics for late duplicates, late first arrivals, active groups, and group cleanup.
15. Write a runbook guiding operators on choosing freeze/correction/new epoch.

### 22.3. Testing Three Late Cases

**Case A — Late but still needed:**

~~~text
Release policy: partial contiguous
Arrivals: 1,2,5,4,3
After 1,2: output 1,2
After 5,4: wait for 3
After 3: output 3,4,5
Expected: Do not discard 3
~~~

**Case B — Duplicate after completed:**

~~~text
Release policy: wait full group
Arrivals: 3,1,2,5,4
Output: 1,2,3,4,5
Arrive #2 again with same correlationId:
Expected: Discard/audit; no second business effect
~~~

**Case C — Missing event arrives after expiry:**

~~~text
Arrivals: 1,2,3,5 (missing 4)
Group timeout -> EXPIRED
Arrive #4 after group closes
Expected: Late classification, no silent "complete" report
Next step: freeze or correction per business policy
~~~

In Case C, if operators want to amend old results, creating a **correction workflow** must be explicit rather than merely pushing `#4` into a fresh Resequencer hoping the original sequence heals itself.

## 23. Self-Check Questions

1. How does Resequencer's output differ from Aggregator's?
2. Why does receiving messages in order `2,4,1,3` not automatically mean events occurred out of business order?
3. What roles do `correlationId`, `sequenceNumber`, and `sequenceSize` play?
4. When should `releasePartialSequences(false)` be used?
5. With `releasePartialSequences(true)`, why can message 3 arriving after prefix 1,2 still be valid?
6. Why does a duplicate `#2` after group completion differ from a missing `#3` while the group is `ACTIVE`?
7. What does retaining empty completed-group metadata prevent?
8. What consequences can deleting a group immediately upon completion have for late messages?
9. How do `expireGroupsUponTimeout(false)` and `true` differ regarding late arrivals?
10. How does `MessageGroupStoreReaper` affect the window during which late messages can be detected?
11. Why does an in-memory store fail to guarantee late messages are discarded after a restart?
12. Why must business `eventId` be distinguished from `MessageHeaders.ID`?
13. Does a message routed to `discardChannel` always mean bad input?
14. Should `discardChannel` ever route straight back to Resequencer's input? Why or why not?
15. Can timestamps alone prove whether a message is a duplicate?
16. Why is Resequencer alone insufficient to guarantee exactly-once side effects?
17. When is a correction/revision needed instead of silent replay?
18. If the same group is processed across two instances, what ownership/locking must be added?
19. Why is `sequenceSize` unsuitable when upstream does not know when the source ends?
20. Does a properly ordered sequence release prove an external API call committed?

## 24. Checklist Before Deploying Resequencer to Production

- Clearly defined **correlation group unit** and sequence epoch.
- `sequenceNumber` and `sequenceSize` generated or verified by a trusted source.
- Determined whether **full release** or **partial contiguous release** fits business semantics.
- Tested late-arriving messages filling a gap and still releasing properly.
- Tested duplicates after group completion being discarded/audited.
- `discardChannel` actively consumed; no loop feeding back into Resequencer.
- `groupTimeout`/expiry/reaper configured if a message might never arrive.
- `sendPartialResultOnExpiry` chosen per contract; partial never conflated with complete.
- `expireGroupsUponTimeout` chosen after evaluating late arrivals, not merely to save memory.
- Completed empty-group retention covers real-world redelivery windows.
- Limits enforced on waiting groups, buffered messages, and `MessageGroupStore` resources.
- With an in-memory store, restart risks documented; with a persistent store, recovery tested.
- Multiple instances have partition ownership or shared store/locking.
- Independent **event identity and idempotency ledger** protects side effects.
- Late first-time arrivals distinguished from duplicate redeliveries.
- Published freeze, correction, or new-epoch policies for already-emitted results.
- Logs and metrics track old groups, pending gaps, late discards, and duplicates.
- Gateways, Routers, Transformers, Filters, and broker adapters preserve required metadata.
- Unit/integration tests cover out-of-order, complete, partial, timeout, late, restart, and concurrency cases.
- Runbook never instructs operators to delete groups or replay directly without checking the ledger.

**Conclusion:** "Late messages after a sequence has released" is not a single monolithic scenario. If Resequencer only emitted **a prefix** while the group remains active, a later message **filling a gap** must still be processed. If the entire group **completed or expired**, late messages can be discarded thanks to retained **empty-group metadata**. Once metadata is purged, old messages can look like members of a new group, making **business idempotency** and **correlation epochs** essential safeguards. Designing release policies, retention, timeouts, discard channels, corrections, and state-specific tests lets Resequencer reorder messages without losing valid events or repeating business side effects.

## References

- [Spring Integration Reference — Resequencer](https://docs.spring.io/spring-integration/reference/resequencer.html): resequencing principles, `releasePartialSequences`, group expiry, empty groups, and late arrivals.
- [Spring Integration Reference — Aggregators and Resequencers (Java DSL)](https://docs.spring.io/spring-integration/reference/dsl/java-aggregators.html): `resequence()` and `aggregate()` examples in `IntegrationFlow`.
- [Spring Integration Reference — Aggregator](https://docs.spring.io/spring-integration/reference/aggregator.html): correlation groups, group completion, `MessageGroupStore`, expiry, and late arrivals.
- [Spring Integration API — ResequencerSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/ResequencerSpec.html): `releasePartialSequences` and inherited correlation handler settings.
- [Spring Integration API — SequenceSizeReleaseStrategy](https://docs.spring.io/spring-integration/api/org/springframework/integration/aggregator/SequenceSizeReleaseStrategy.html): partial sequence emission semantics and release strategies.
- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): `DirectChannel`, `QueueChannel`, `ExecutorChannel`, and ordering impacts.
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): distinguishing `ErrorMessage`, `errorChannel`, and discarded messages.
- [Spring Integration Reference — Idempotent Receiver](https://docs.spring.io/spring-integration/reference/handler-advice/idempotent-receiver.html): message deduplication and limits of idempotent advice.
- [Enterprise Integration Patterns — Resequencer](https://www.enterpriseintegrationpatterns.com/patterns/messaging/Resequencer.html): foundational pattern for ordered message delivery.
