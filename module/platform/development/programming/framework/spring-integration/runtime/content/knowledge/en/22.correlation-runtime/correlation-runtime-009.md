# Testing Out-of-Order or Missing Messages in Spring Integration Runtime

## Lesson Objectives

In **SPRING_INTEGRATION_RUNTIME**, message flows commonly receive data from multiple consumers, pollers, queues, HTTP clients, or worker threads. Messages belonging to the same business process can **arrive out of send order**, be **delayed**, **missing**, **redelivered**, or processed concurrently by multiple instances. Testing only the happy path with three messages arriving in order lets correlation or release bugs slip straight into production.

This lesson belongs to the **Correlation runtime** chapter and focuses on **testing out-of-order or missing messages**. Examples use an aggregator waiting for three pieces of an order while connecting to message stores, endpoints, channels, executors, transactions, retries, error flows, and lifecycles.

After this lesson, you will be able to:

- Design test suites for **out-of-order, missing, late, duplicated**, and **concurrent** messages.
- Distinguish **correlation key**, **sequenceNumber/sequenceSize**, **eventId**, **requestId**, and **Spring MessageHeaders.ID**.
- Verify that **ReleaseStrategy** emits output only when business data is genuinely complete.
- Test **group timeout**, partial results, discard channels, and state inside **MessageGroupStore**.
- Write integration tests with Spring Integration channels, sending messages across permutations and asserting **no premature output**.
- Diagnose common failures under multithreading, restarts, retries, or multiple application instances.

> **Correctness criterion:** For each business group, the system does not emit a complete result when conditions are still missing; once valid messages arrive, the result is independent of arrival order; duplicate messages and messages arriving after completion must never trigger repeated business side effects.

## 1. Why can messages arrive out of order or go missing?

Suppose order confirmation O-42 requires three independent steps:

| Step | Data received | Source |
| --- | --- | --- |
| PAYMENT | Payment accepted | Payment service |
| INVENTORY | Stock reserved | Inventory service |
| ADDRESS | Delivery address validated | Address service |

An ideal flow might emit in order PAYMENT → INVENTORY → ADDRESS. Actual runtime may observe ADDRESS → PAYMENT → INVENTORY due to differing workers, networks, and latencies.

~~~mermaid
sequenceDiagram
    participant P as Payment service
    participant I as Inventory service
    participant A as Address service
    participant G as Aggregator
    participant O as Order consumer
    Note over P,A: Tasks run independently
    A->>G: ADDRESS, group=O-42
    P->>G: PAYMENT, group=O-42
    Note right of G: Fewer than 3 steps: wait
    I->>G: INVENTORY, group=O-42
    G->>O: OrderReady
~~~

Sources of out-of-order/missing messages:

- **ExecutorChannel / TaskExecutor:** workers finish at different durations.
- **QueueChannel and polling consumers:** multiple pollers or concurrent consumers; fetch order and completion order need not match.
- **Broker/adapter:** partitions, rebalances, redeliveries, and retries change when messages become visible. Ordering guarantees, if any, usually hold only within a specific scope like partition/key.
- **Transformer/filter/router:** a failed branch, filter, or mutated correlation header can prevent the aggregator from seeing a part.
- **External services:** timeouts can happen even after a side effect succeeded; result events may be re-emitted with a new message ID.
- **Restarts/scale-out:** messages remain in a persistent store, yet deadlines and scheduler jobs may need recovery or reconciliation.

Do not expect a **DirectChannel** to guarantee global ordering: it runs synchronously per `send()` call, yet **two different threads can still send concurrently** to the same handler.

## 2. Define “correct” precisely before writing tests

No correlation test suite is useful if the business has not defined when a group counts as complete. For order O-42, assume these conditions:

1. All three **step types** PAYMENT, INVENTORY, and ADDRESS are present.
2. All steps belong to the same **orderId + runId**.
3. Each event carries a stable **eventId** to recognize redelivery.
4. No failed results or conflicting versions exist; otherwise a dedicated failure branch is required.
5. Output **OrderReady** is emitted **once in business terms** for the same orderId + runId, even after restarts or redeliveries.

A baseline test matrix can be described in a table:

| Scenario | Input | Expectation |
| --- | --- | --- |
| In order | PAYMENT → INVENTORY → ADDRESS | One result after the third part |
| Out of order | ADDRESS → PAYMENT → INVENTORY | One equivalent result |
| Missing part | PAYMENT + ADDRESS, no INVENTORY | No complete OrderReady |
| Duplicated | PAYMENT(E1) twice + ADDRESS | Must not count as three step types |
| Late arrival | After group completes, INVENTORY is redelivered | Discard/quarantine or handle per late-message policy |
| Multiple interleaved groups | O-42 and O-43 each receive all three parts | Two outputs, never mixed |
| Concurrent sends | Three producers send concurrently for O-42 | One output, no lost updates |
| Timeout | Group missing INVENTORY exceeds SLA | Timeout status recorded; no complete OrderReady created |
| Restart | Persist 2/3 parts then restart | Saved parts preserved when using a durable store |

**Key point:** “No output” only proves a **transient state**. Missing-message tests must also verify what happens when the wait expires: quarantine, emitting a flagged partial result, holding the group for recovery, or purging state.

## 3. Message identity: distinguishing the keys

A sample message:

~~~text
payload:
  orderId=O-42, runId=R-7
  step=PAYMENT, eventId=payment-event-19, accepted=true

headers:
  groupKey=order-ready:v1:O-42:R-7
  correlationId=checkout-O-42
  requestId=checkout-request-91
  id=<Spring Message UUID>
~~~

| Field | Role | Use in tests |
| --- | --- | --- |
| **groupKey** | Unique key for the aggregator to partition groups | Verify messages of the same run join one group and different runs stay separate |
| **correlationId** | Links messages across a business journey; may be adjusted by EIP components | Verify header propagates properly across transforms/gateways |
| **orderId + runId** | Identifies a business aggregation round | Verify two different confirmations of the same order do not merge |
| **eventId** | Identifies the source event across retries/redeliveries | Verify deduplication before or inside aggregation |
| **MessageHeaders.ID** | Technical ID of one Spring Message | Never use as an idempotency key across replays or rebuilt messages |
| **sequenceNumber/sequenceSize** | Ordering and part count set by splitter/producer | Used when choosing sequence-based release; not synonymous with unique business events |

**Do not confuse the two correlation styles:** Header **correlationId** is Spring Integration's standard convention and default across many correlating endpoints, whereas **groupKey** in this lesson is a **custom header**. When configuring the aggregator, explicitly instruct it to use **headers['groupKey']**. Otherwise, tests will not exercise the intended grouping rule.

For a standard splitter, sequence headers may suffice to reassemble fragments of **one root message**. When combining **three business outcomes from three services**, raw message count or sequence size alone is usually insufficient to stop duplicates.

## 4. ReleaseStrategy must be invariant to arrival order

ReleaseStrategy answers: **is the group ready to emit?** It should be a side-effect-free check so repeated evaluations from retries, timeouts, or concurrency never trigger extra payments, HTTP calls, or events.

Simple model example:

~~~java
package example;

public enum Step {
    PAYMENT, INVENTORY, ADDRESS
}

// Place record in OrderPart.java, in package example.
public record OrderPart(
        String orderId,
        String runId,
        String eventId,
        Step step,
        boolean accepted) {
}
~~~

A strategy that releases only when **all three step types** hold valid status:

~~~java
package example;

import java.util.EnumSet;
import org.springframework.integration.aggregator.ReleaseStrategy;
import org.springframework.integration.store.MessageGroup;
import org.springframework.messaging.Message;

public final class RequiredStepsReleaseStrategy implements ReleaseStrategy {

    private static final EnumSet<Step> REQUIRED =
            EnumSet.allOf(Step.class);

    @Override
    public boolean canRelease(MessageGroup group) {
        EnumSet<Step> accepted = EnumSet.noneOf(Step.class);

        for (Message<?> message : group.getMessages()) {
            if (!(message.getPayload() instanceof OrderPart part)) {
                return false;
            }
            if (!part.accepted()) {
                return false;
            }
            accepted.add(part.step());
        }

        return accepted.containsAll(REQUIRED);
    }
}
~~~

Because the strategy uses a **Step** set, both **ADDRESS → PAYMENT → INVENTORY** and **INVENTORY → ADDRESS → PAYMENT** yield the same decision. A duplicate PAYMENT cannot substitute for INVENTORY.

However, this is only a **release guard**, **not a complete duplicate defense**:

- Two PAYMENT events with identical eventIds still enter the group unless ingress filters them; when the group releases, the processor may receive multiple PAYMENT parts.
- If two PAYMENTs have conflicting statuses, such as one accepted=true and one accepted=false, the strategy returns false, yet an explicit policy is needed to route conflicts to an error flow/quarantine.
- If a message accidentally carries a **groupKey** mismatched with **orderId/runId in its payload**, the strategy does not automatically detect the correlation mismatch. Validate that invariant before storing the group.
- With persistent stores, **group.getMessages()** may load many payloads; very large groups need metadata/condition-based release logic or appropriate progress tracking.

Therefore, tests must check both **timely release** and **accurate post-release payload contents**. If the output is a collection containing two PAYMENTs, the test must not be considered fully passing merely because it arrived on time.

## 5. Building a test flow with channels and MessageGroupStore

To test a real aggregator, send messages through Spring Integration channels/endpoints rather than calling **canRelease()** directly alone. The XML snippet below is an illustrative test configuration; beans/channels are declared in the same application context. Place it in **order-aggregation-test.xml** under test resources when applying to a project.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:int="http://www.springframework.org/schema/integration"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/integration
           https://www.springframework.org/schema/integration/spring-integration.xsd">

    <int:channel id="orderParts"/>
    <int:channel id="orderReady">
        <int:queue/>
    </int:channel>
    <int:channel id="discardedParts">
        <int:queue/>
    </int:channel>

    <bean id="groupStore"
          class="org.springframework.integration.store.SimpleMessageStore"/>
    <bean id="requiredSteps"
          class="example.RequiredStepsReleaseStrategy"/>

    <int:aggregator
            id="orderAggregator"
            input-channel="orderParts"
            output-channel="orderReady"
            message-store="groupStore"
            correlation-strategy-expression="headers['groupKey']"
            release-strategy="requiredSteps"
            discard-channel="discardedParts"
            expire-groups-upon-completion="false"/>
</beans>
~~~

This test design has intentional characteristics:

- **orderParts** is a synchronous input channel; sending from one thread and waiting for the call to finish lets the test know deterministically when the aggregator processed that part.
- **orderReady** and **discardedParts** are **QueueChannel**s, so the test can call **receive(timeout)** to observe presence/absence of output.
- **SimpleMessageStore** holds state only in RAM and within one context; sufficient for testing logic, **not for proving restarts or multi-instance behavior**.
- **RequiredStepsReleaseStrategy** checks all three step types; in production the aggregator needs a business **MessageGroupProcessor/output processor** to construct the real OrderReady object. With the default processor, output can be a collection of payloads; do not assume it is already a business DTO.
- **expire-groups-upon-completion=false** retains completed metadata so late arrivals are recognized instead of immediately spawning a new group.
- The example intentionally **omits timeout configuration**: first verify complete/missing behavior without expiry. Dedicated timeout tests follow later.

## 6. Integration test: three messages arriving out of order

The JUnit 5 example below uses the same XML configuration from the previous section. Package is **example**, and types **Step** and **OrderPart** are defined in Section 4. Each test uses a **unique groupKey** so groups do not interfere across tests.

~~~java
package example;

import static org.junit.jupiter.api.Assertions.*;
import static example.Step.*;

import java.util.Collection;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(locations = "classpath:order-aggregation-test.xml")
class OutOfOrderAggregationTest {

    @Autowired
    @Qualifier("orderParts")
    MessageChannel input;

    @Autowired
    @Qualifier("orderReady")
    PollableChannel output;

    private Message<OrderPart> part(
            String groupKey, String eventId, Step step) {
        return MessageBuilder.withPayload(
                    new OrderPart("O-42", "run-1", eventId, step, true))
                .setHeader("groupKey", groupKey)
                .setHeader("correlationId", "checkout-O-42")
                .setHeader("requestId", "request-O-42")
                .build();
    }

    @Test
    void releasesOnceWhenMessagesArriveOutOfOrder() {
        String group = "order-ready:v1:" + UUID.randomUUID();

        assertTrue(input.send(part(group, "address-1", ADDRESS)));
        assertNull(output.receive(0), "Not all 3 step types yet");

        assertTrue(input.send(part(group, "payment-1", PAYMENT)));
        assertNull(output.receive(0), "Still missing INVENTORY");

        assertTrue(input.send(part(group, "inventory-1", INVENTORY)));
        Message<?> released = output.receive(1000);
        assertNotNull(released, "Must emit result once all 3 steps arrive");
        assertNull(output.receive(0), "Must not emit a second time");

        // With default output processor: verify aggregated payloads.
        assertInstanceOf(Collection.class, released.getPayload());
        Collection<?> payloads =
                (Collection<?>) released.getPayload();
        Set<Step> actualSteps = payloads.stream()
                .map(value -> ((OrderPart) value).step())
                .collect(Collectors.toSet());
        assertEquals(Set.of(PAYMENT, INVENTORY, ADDRESS), actualSteps);
        assertEquals(3, payloads.size());
    }
}
~~~

**How to interpret the result:**

1. Every send call before the final send returned, yet QueueChannel **remained empty**. That proves the aggregator did not release prematurely on this synchronous test path.
2. After receiving INVENTORY, **exactly one** output appeared containing all three steps, regardless of arrival order.
3. Assertion **payloads.size() == 3** ensures the output contains no accidental duplicate on the happy path.
4. Because contexts may be shared across tests, use unique group keys, drain output channels, or isolate application contexts when running tests in parallel.

### Testing all permutations

With three step types, there are **6 permutations**. Instead of testing only ADDRESS → PAYMENT → INVENTORY, use a parameterized test covering these sequences:

~~~text
PAYMENT, INVENTORY, ADDRESS
PAYMENT, ADDRESS, INVENTORY
INVENTORY, PAYMENT, ADDRESS
INVENTORY, ADDRESS, PAYMENT
ADDRESS, PAYMENT, INVENTORY
ADDRESS, INVENTORY, PAYMENT
~~~

For each permutation, use a **fresh groupKey**, send each part, assert **no output after parts 1 and 2**, and assert exactly one result after part 3. Then check the **content set**, **eventId**s, and business keys rather than asserting fixed positions in the collection unless the business requires ordering.

A collection preserving store insertion order **does not mean** business ordering is guaranteed. If downstream requires a fixed output order, **MessageGroupProcessor** must sort by Step/sequence or construct a DTO with explicit named fields.

## 7. Testing missing messages: proving no premature release

Case with only PAYMENT and ADDRESS, missing INVENTORY. A simple test:

~~~java
@Test
void doesNotReleaseWhenInventoryIsMissing() {
    String group = "order-ready:v1:" + UUID.randomUUID();

    assertTrue(input.send(part(group, "payment-2", PAYMENT)));
    assertTrue(input.send(part(group, "address-2", ADDRESS)));

    assertNull(output.receive(0));

    // If the test needs to prove 2 parts were stored, inject
    // MessageGroupStore and inspect the group by key.
}
~~~

Inspecting group state when needed:

~~~java
@Autowired
@Qualifier("groupStore")
org.springframework.integration.store.MessageGroupStore groupStore;

// Inside the test after two input.send(...) calls:
var groupState = groupStore.getMessageGroup(group);
assertEquals(2, groupState.size());
assertFalse(groupState.isComplete());
~~~

Do not use a **Thread.sleep(30_000)** to “prove a missing message”. Without timeout configured, you can only assert **unreleased at the moment of observation**. To verify deadlines, write a dedicated test with a group timeout and an observable completion/expiry signal.

### Distinguishing missing messages from unmet release conditions

Commonly conflated causes:

| Symptom | Possible real cause | Verification |
| --- | --- | --- |
| Group O-42 has only two parts | Third service never sent or failed sending | Inspect third source's outbound logs and error flow |
| All three messages arrived yet still waiting | One payload has **accepted=false** or wrong Step type | Inspect each payload and ReleaseStrategy evaluation |
| Unclear where the third message went | groupKey header dropped or mutated after transformer | Trace channels before/after transform; inspect headers |
| Group waits even after sending all messages | Message landed in **a different group** due to wrong runId/key | Compare group list in store |
| Group “disappears” after restart | In-memory SimpleMessageStore | Use a persistent store and test restarts |
| Group timed out yet produced no result | Partial release disabled or discard/expiry not observed | Check timeout, discard channel, and message store |

A good test suite separates **data absent**, **data invalid**, **correlation mismatch**, and **scheduler/expiry** errors. They have different fixes.

## 8. Testing duplicates and redelivery

Suppose the broker redelivers PAYMENT due to a lost consumer ack:

~~~text
1. PAYMENT, eventId=pay-19, Spring messageId=M1
2. PAYMENT, eventId=pay-19, Spring messageId=M2  ← redelivery
3. ADDRESS, eventId=addr-5
4. INVENTORY, eventId=stock-8
~~~

If the release strategy only checks **size() >= 3**, it can release right at step 3 despite missing INVENTORY. **RequiredStepsReleaseStrategy** from Section 4 avoids that premature release, yet when step 4 arrives, the group can still hold **two copies of PAYMENT**.

Separate two assertions:

- **Release correctness:** never emit OrderReady when a Step is missing.
- **Deduplication correctness:** output never contains two business events with the same eventId and never triggers side effects twice.

To satisfy both, you typically need an **idempotent receiver/filter** before the aggregator, a unique constraint on eventId, or an equivalent durable deduplication mechanism:

~~~text
Inbound message
    ↓ validate orderId/runId/eventId
    ↓ idempotently check / record eventId
    ├─ already seen → discard with reason DUPLICATE
    └─ new          → Aggregator
~~~

Note on **synchronization**: two concurrent consumers with the same eventId must not both pass “check then put” if the store lacks atomic operations. If duplicates arrive across multiple JVMs, in-process memory is insufficient; prefer a store supporting unique constraints or atomic claims.

### Essential duplicate test cases

1. Send two messages with the same **eventId** but **different MessageHeaders.ID**; verify they do not count as two separate steps.
2. Send two messages for the same **Step** with different eventIds and conflicting payloads; verify conflict policy rather than picking arbitrarily.
3. Resend all three parts **after release**; verify group complete/retained state and downstream idempotency.
4. Send duplicates concurrently from two producers; verify a single claim in the store.
5. Restart after receiving one part then redeliver; verify dedup keys remain effective across restarts.

A test that only expects identical **Message IDs** by reusing the same mock Message object is insufficient. Real broker adapters typically construct a brand-new Spring Message on redelivery.

## 9. Timeouts, partial release, and late-arriving messages

Missing messages indefinitely accumulate incomplete groups unless there is a clear lifecycle. Spring Integration supports mechanisms such as **groupTimeout**, **sendPartialResultOnExpiry**, and store/reaper cleanup depending on configuration.

~~~mermaid
stateDiagram-v2
    [*] --> Waiting: Receive first part
    Waiting --> Waiting: Condition not yet met
    Waiting --> Released: All three step types present
    Waiting --> TimedOut: SLA exceeded
    TimedOut --> Quarantined: Do not emit partial
    TimedOut --> Partial: Partial allowed by contract
    Released --> Completed: Mark group complete
    Completed --> Retained: Retain metadata
    Retained --> Discard: Receive late message
~~~

**Timeout design must be a business decision:**

- If an order may be confirmed only when all three parts arrive, configure **sendPartialResultOnExpiry=false**; timeouts route to failure/quarantine per policy.
- If the business accepts partials (e.g., dashboards displaying provisional counts), output **must explicitly flag partial status** so downstream never mistakes it for complete.
- If groups are **deleted immediately upon completion** or timeout, a late message can open a **new group** with the same key. Retaining completion metadata helps detect late arrivals, though it needs a cleanup plan.
- If timeouts/deadlines are measured from the latest message, redelivering a part can unexpectedly extend “wait age”; decide whether deadlines measure from **first receipt** or **last update**.

### How to test timeouts without flaky tests

Create **two separate test configurations**:

1. **No-timeout fixture** for permutation, pre-expiry missing, and duplicate tests, preventing the scheduler from interfering mid-assertion.
2. **Timeout fixture** with a short timeout inside a generous test deadline, explicit channels receiving timeout/discard events, and explicitly declared partial policy.

With the timeout fixture, send 2/3 parts then await the **terminal signal** via a pollable channel/spy or group state, using synchronization/await primitives on the condition rather than hardcoded sleeps. Assertions should verify **no complete OrderReady**, presence of timeout/quarantine events if contracted, and proper group retention/expiry. When running on busy CI, keep result timeouts generous relative to the test SLA.

**Do not confuse receive timeout with group timeout:**

~~~java
assertNull(orderReady.receive(100));
~~~

This call only says **no message appeared on output QueueChannel within 100 ms**. It **does not configure** a group deadline and **does not prove** the aggregator's timeout event ran. To verify group timeout, observe **post-expiry callbacks/status** or inspect the store per contract.

### Testing late arrivals after group completion

With **expire-groups-upon-completion=false**, you can design a test:

~~~java
String groupKey = "order-ready:v1:" + UUID.randomUUID();
input.send(part(groupKey, "pay-1", PAYMENT));
input.send(part(groupKey, "stock-1", INVENTORY));
input.send(part(groupKey, "address-1", ADDRESS));
assertNotNull(output.receive(1000));

// Late-arriving message: same groupKey, e.g., redelivery.
input.send(part(groupKey, "pay-redelivered", PAYMENT));
assertNull(output.receive(0), "Must not emit OrderReady again");

// Check discardedParts or store state per configured policy.
~~~

Asserting empty output alone is **insufficient** to prove late messages were handled properly. Inspect **discard/quarantine** or group metadata, and ensure no memory leak occurs from holding metadata too long.

## 10. Testing concurrent arrivals and interleaved groups

Sequential tests verify correlation logic; they do not prove thread safety. When multiple producers invoke the same DirectChannel or ExecutorChannel, groups can be updated concurrently.

Example sending three parts concurrently:

~~~java
var pool = java.util.concurrent.Executors.newFixedThreadPool(3);
var start = new java.util.concurrent.CountDownLatch(1);
String groupKey = "order-ready:v1:" + java.util.UUID.randomUUID();

try {
    var futures = java.util.List.of(
        pool.submit(() -> {
            start.await();
            return input.send(part(groupKey, "p", PAYMENT));
        }),
        pool.submit(() -> {
            start.await();
            return input.send(part(groupKey, "i", INVENTORY));
        }),
        pool.submit(() -> {
            start.await();
            return input.send(part(groupKey, "a", ADDRESS));
        })
    );

    start.countDown();
    for (var future : futures) {
        assertTrue(future.get(5, java.util.concurrent.TimeUnit.SECONDS));
    }

    assertNotNull(output.receive(1000));
    assertNull(output.receive(0), "No second result");
} finally {
    pool.shutdownNow();
}
~~~

This is an **in-JVM concurrency test pattern**. It starts three tasks together and waits for all sends to finish, avoiding sleep-based timing. Repeat across many groups/keys, including cases where one thread sends a duplicate and another injects a fault.

**Do not share one groupKey across tests running in parallel**: tests will step on each other. When tests share a context, use unique group keys and drain or isolate output queues.

### Interleaving multiple groups

Send O-42 PAYMENT, O-43 ADDRESS, O-42 INVENTORY, O-43 PAYMENT, O-42 ADDRESS, O-43 INVENTORY. Expectations:

- **Two** outputs appear: one for O-42 and one for O-43.
- Each output contains strictly **the three messages of its own runId**.
- No ordering constraint holds **between the two outputs** if groups run on different executors.
- Tests match content/correlation by **groupKey**, never assuming output[0] is always O-42.

### Scaling across multiple JVMs

For genuine multi-instance testing, you need a **shared MessageGroupStore**, a **LockRegistry or equivalent coordination**, and at least two application instances. A test using only SimpleMessageStore and ExecutorService **does not prove** multi-process safety.

Key scenarios: two instances concurrently deliver the final part to an almost-complete group, or one instance dies between group update and publish. Verify:

- No messages are lost in the store and no unintended double releases occur.
- Locks/transactions operate across instances, not only in one JVM's memory.
- Downstream consumers are idempotent because outputs may still redeliver after network faults or crashes.

## 11. Retries, transactions, and error flows in the test suite

A correlation test only proves state along the **happy path** unless faults are deliberately injected. At runtime, retries and transactions can change what ends up persisted in the store.

~~~mermaid
flowchart TD
    IN["Inbound message"] --> T["Transformer / validator"]
    T --> C["CorrelationStrategy"]
    C --> S[("MessageGroupStore")]
    S --> R{"ReleaseStrategy"}
    R -- "Not ready" --> W["Waiting / timeout"]
    R -- "Ready" --> P["MessageGroupProcessor"]
    P --> OUT["Output channel / consumer"]
    T -. "exception" .-> ER["Error flow"]
    S -. "exception" .-> ER
    P -. "exception" .-> ER
    OUT -. "exception" .-> ER
~~~

### Boundaries to verify

| Component | What to verify |
| --- | --- |
| **DirectChannel** | Does an exception from a synchronous handler propagate to the sender? Does the transaction share the same thread? |
| **ExecutorChannel** | Where do errors on worker threads go? The sender's transaction does not automatically cover downstream |
| **Poller** | If poll/handler fails, does the source reclaim the message? Where do ack, transaction, and retry policies apply? |
| **MessageGroupStore** | Do add/release/mark-complete roll back with the transaction? Is the store durable across crashes? |
| **RetryAdvice/broker redelivery** | Could the same eventId be reprocessed as new business work? Are multiple retry layers nested? |
| **ErrorMessage** | Can failed/original message and groupKey/requestId be extracted from the error? |
| **MessageGroupProcessor** | If building output throws, what state does the group stay in and what will the next retry do? |

**Tests you should not skip:**

1. Parser receives a malformed message before the aggregator: must not create a group with a null/UNKNOWN key.
2. Handler/processor throws after the group qualifies: error propagates or routes to the error flow; never swallowed.
3. Transaction rolls back after the store received the final part: post-rollback group state and output match the resource/transaction manager's guarantees.
4. Broker redelivers after rollback: same eventId causes no extra side effect.
5. Error occurs **after output was already sent**: downstream requires idempotency because a DB rollback does not undo HTTP/broker events.

Do not assume **message store + aggregator = exactly once**. Consistency between store and output depends on transaction managers, adapters, and topology; external side effects typically need **outbox/inbox, unique constraints**, or reconciliation.

## 12. Restarts and recovering incomplete groups

**SimpleMessageStore** works well for small unit/integration tests, yet state vanishes when the JVM stops. To verify flows survive restarts, use **JdbcMessageStore, RedisMessageStore, or MongoDbMessageStore** matching production configuration and test against real storage.

Scenario:

~~~text
T0: Instance A receives PAYMENT (O-42)
T1: Instance A receives ADDRESS (O-42)
T2: MessageGroupStore durably writes 2/3 parts
T3: Stop instance A
T4: Start instance B sharing the same store/schema
T5: B sends INVENTORY (O-42)
T6: Aggregator releases one accurate result for O-42
~~~

Additional checks:

- **groupKey** and payloads still deserialize across version upgrades.
- Incomplete group state is neither reset nor duplicated by fresh beans.
- Group timeouts/reapers or expiry mechanisms still trigger after restart; in-RAM per-group timers must not be assumed to restore intact automatically.
- Completed/late-arrival metadata is kept or cleaned up per policy.
- Some headers such as channel objects or transport callbacks may not be serializable; define explicit header mappings.
- Two instances sharing a store need proper locking rather than relying solely on data living in DB/Redis.

For real crash tests, terminate the process or stop an instance at a controlled checkpoint. Simply calling **context.close()** after a transaction finishes is a normal restart test, **not yet** a crash test between commit and publish.

## 13. Observability and diagnosing a group that never completes

Good logs must distinguish **group ID, business ID, event ID, message ID, and attempt**:

~~~text
flow=orderConfirmation
endpoint=orderAggregator
groupKey=order-ready:v1:O-42:R-7
correlationId=checkout-O-42
eventId=stock-8
step=INVENTORY
groupSize=2
presentSteps=PAYMENT,INVENTORY
missingSteps=ADDRESS
decision=WAIT
thread=aggregation-worker-3
~~~

This is a **custom-designed log format**, not fields emitted automatically by Spring Integration.

Runtime signals to monitor:

| Metric | Operational question |
| --- | --- |
| Count of **incomplete groups** | Are messages missing, mis-correlated, or dropped by filters? |
| Group **age** and **lastModified age** | Which groups have gone un-updated past SLA? |
| Messages/group vs. **unique eventId** count | Are duplicates inflating size while steps remain missing? |
| Release rate and wait-to-release latency | Are groups stalling because one upstream is slow? |
| Timeout, partial, discard, late arrival | Is the missing-part policy behaving properly? |
| FailedMessage/errorChannel count | Are errors logged-and-ignored or losing correlation? |
| Store latency, serialization errors, lock contention | Is DB/Redis/instance causing bottlenecks or state errors? |
| Retry/redelivery and duplicate outputs | Are nested retries active or idempotency insufficient? |

When tracking down an unreleased group, investigate in order:

1. **Source:** were all three steps truly emitted, evidenced by which eventIds?
2. **Aggregator input:** what **groupKey** does each message carry after transformers/filters/routers?
3. **Store:** how many parts, what complete flag, and what timestamps exist for the expected key?
4. **ReleaseStrategy:** which condition is unmet, or are there duplicates/conflicts/invalid payloads?
5. **Timeout:** has the deadline passed, and are schedulers/reapers running after restarts?
6. **Thread/transaction:** were tasks rejected, rolled back, deadlocked, or blocked on locks?
7. **Output:** did release succeed while the output processor, adapter, or downstream failed somewhere?

Checking **group.size()** alone is never enough; inspect the **set of unique steps**, payload status, and processing run info.

## 14. Extended exercise: failure matrix to verify

**Prompt:** An order-confirmation flow must receive three steps from a broker and may run across multiple instances. SLA is **2 minutes** from group start; if parts are missing, record **OrderAssemblyTimedOut** and do not emit **OrderReady**. The broker provides at-least-once delivery and may produce duplicates after restarts.

Design tests following this matrix:

| Case | Simulated condition | Verification expectation |
| --- | --- | --- |
| A | All six permutations of 3 parts | Each group emits exactly one OrderReady once qualified |
| B | Omit each Step type in turn | No early release; SLA expiration enters timeout flow |
| C | One Step delivered twice with same eventId | Duplicate not counted; no early release |
| D | One Step sends accepted=false payload | Conflict/failure handled; no success emitted |
| E | Third part arrives after timeout | Follows late-arrival policy; never creates bogus OrderReady |
| F | Same orderId with different runId | Two independent groups; no mixed payloads |
| G | Two orderIds interleaved | Groups stay separate; independent of cross-group output order |
| H | Three producers send concurrently | No lost state; no double emission |
| I | Restart after 2/3 parts | Persistent store resumes with 2/3 persisted parts |
| J | Two instances send final part simultaneously | Locking/idempotency preserves business correctness |
| K | Output processor throws exception | Error flow triggers; state/retry verified |
| L | Producer times out then resends | eventId/idempotency key preserved; side effect not repeated |
| M | Group completed and metadata cleaned up | Late message handled per designed policy; no duplicate business emission |

### Suggestions for organizing the test suite

Split into independent layers:

- **ReleaseStrategy unit tests:** all Step subsets, duplicates, accepted=false, wrong payload types. Fast logic checks, though they do **not** prove channel/store correctness.
- **Single-context integration tests:** DirectChannel + QueueChannel + aggregator + SimpleMessageStore. Verify release timing, headers, message grouping, and output.
- **Scheduler/timeout integration tests:** groupTimeout, expiry/discard, post-timeout store state; use synchronization conditions/signals instead of arbitrary sleeps.
- **Stress/concurrency tests:** multiple producers, same and distinct groupKeys, bounded timeouts, checking total output and deadlocks.
- **End-to-end with broker/persistent store:** redelivery, restarts, two instances, transactions, locks, idempotency, and downstream output.

Heavy stress tests need not run on every commit, yet **out-of-order, missing, and duplicate** conditions should be recurring regression tests whenever release strategies, correlation mappings, or payload schemas change.

## 15. Pre-deployment checklist

- What business steps are **required**? Raw message count or **unique message types**?
- Are **groupKey / correlationId / eventId / requestId / MessageHeaders.ID** cleanly separated?
- Is ReleaseStrategy **invariant to arrival order** and free of side effects?
- Were all critical permutations tested, asserting **no release after incomplete subsets**?
- Were missing messages tested **both before and after the deadline**, with observable timeout states?
- Can duplicates arrive with a **new Message ID**; is deduplication atomic across instances?
- Once a group completes, where do late arrivals go; how long is metadata kept/deleted?
- Is **partial release** allowed; if so, does downstream know the result is incomplete?
- Does the group ID include a namespace and **runId** to prevent mixing processing sessions?
- Is the store durable across restarts; have serialization, transactions, and locks been verified?
- Does the flow have ExecutorChannel/poller/broker redelivery that alters ordering and transactions?
- Does ErrorMessage retain **failedMessage, correlation, and business key** for diagnosis?
- Did tests verify **output payload**, **emission count**, **store state**, and **real side effects**?
- Do metrics cover incomplete/expired groups, duplicates, contention, and SLA-exceeding ages?

## Conclusion

**Testing out-of-order or missing messages** is how you prove a correlating flow works under real runtime conditions. In Spring Integration, verify that **CorrelationStrategy** groups messages accurately, **ReleaseStrategy** releases only when conditions are satisfied, **MessageGroupStore** maintains lifecycle state, and **timeout/recovery** reaches a clear outcome when parts are missing.

Never stop at “send three messages and receive one result”. Test every significant ordering, intentionally drop a part, inject duplicates, deliver late messages, run concurrently, and restart. Combine business idempotency, transactions, locking, and observability so that one OrderReady means **once in business terms**, regardless of multiple technical attempts and deliveries.

## References

- [Spring Integration Reference — Aggregator](https://docs.spring.io/spring-integration/reference/aggregator.html)
- [Spring Integration Reference — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html)
- [Spring Integration Reference — Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html)
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html)
- [Spring Integration Reference — Testing](https://docs.spring.io/spring-integration/reference/testing.html)
- [Spring Integration API — ReleaseStrategy](https://docs.spring.io/spring-integration/api/org/springframework/integration/aggregator/ReleaseStrategy.html)
- [Spring Integration API — MessageGroupStore](https://docs.spring.io/spring-integration/api/org/springframework/integration/store/MessageGroupStore.html)
