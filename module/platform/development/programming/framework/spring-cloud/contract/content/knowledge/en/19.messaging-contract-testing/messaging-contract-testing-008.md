# Timeouts, Synchronization, and Awaiting Asynchronous Processing Outcomes

## Learning Objectives

In **Spring Cloud Contract**, a contract describes how a **producer** (the message-emitting service) communicates with a **consumer** (the message-receiving and processing service). Contracts can use **Groovy/YAML DSL** to generate producer verification tests, build stubs for consumer tests via **Stub Runner**, and integrate into **CI** to detect incompatible interface changes.

In the **Messaging Contract Testing** chapter, the major challenge is not only confirming the JSON payload is right. Messages are typically sent, received, processed, and persisted **asynchronously**; therefore, assertions running too early can fail, while overly long timeouts or waiting on the wrong condition can produce false positives or flaky tests.

After this lesson, you will be able to:

- Distinguish **sending a message**, **receiving a message**, **successful processing**, and **observing updated business state**.
- Understand the roles of **timeouts when generated producer tests receive output messages** and **timeouts when consumer tests await handler execution**.
- Write Groovy/YAML contracts for an event, configure base tests, and know what generated tests must wait for.
- Use **Stub Runner + StubTrigger** and **bounded polling** mechanisms like Awaitility to test asynchronous consumers.
- Detect **race conditions**, stale messages, wrong destinations, scheduling delays, and mismatched correlation IDs.
- Choose reasonable timeout durations, polling intervals, fixtures, and isolation mechanisms for CI.
- Understand which guarantees contract tests provide and which scenarios need dedicated broker/transaction/retry tests.

## 1. Real-World Problem: The Delayed StockChanged Event

Suppose **Inventory Service** is the producer. After updating stock, it emits a `StockChanged` event to destination `stock-events`. **Checkout Service** is the consumer: upon receiving the event, it updates an internal projection and then decides whether orders can be placed.

Agreed payload between both teams:

~~~json
{
  "eventType": "StockChanged",
  "sku": "SKU-101",
  "quantity": 0
}
~~~

Checkout may process it in steps:

1. Receive message from broker/binder.
2. Deserialize JSON and validate `eventType`, `sku`, and `quantity`.
3. Update the stock projection in database/cache.
4. Once updated, the business flow reads `OUT_OF_STOCK` status.

These steps may execute on different threads or incur persistence latency. A test that calls `trigger(...)` and immediately reads the projection can execute its assertion **before step 3 completes**, even though the consumer works properly.

### Illustrative Timeline

~~~mermaid
sequenceDiagram
    participant Test as Consumer test
    participant Stub as Stub Runner
    participant Bus as Test binder / broker
    participant Handler as Checkout handler
    participant DB as Stock projection
    Test->>Stub: trigger("stock_changed")
    Stub->>Bus: Publish StockChanged
    Stub-->>Test: Trigger accepted
    Test->>DB: Read quantity immediately
    DB-->>Test: Old value (8)
    Bus-->>Handler: Deliver message
    Handler->>DB: Save quantity = 0
    Test->>DB: Retry read with bounded polling
    DB-->>Test: New value (0)
~~~

**Core point:** `trigger(...)` returning success only means **the stub-trigger command was accepted** per the Stub Runner API. It **does not guarantee** the handler finished, the database committed, or the projection is ready for a fresh read.

## 2. Three Different Levels of "Success"

| Level | Example | Corresponding Evidence | Does Not Prove Alone |
|---|---|---|---|
| **Emit invoked** | `inventoryService.changeStock(...)` returns | Trigger method was called | Message arrived at the right destination |
| **Message appeared on destination** | Verifier receives `StockChanged` | Producer messaging contract test received and asserted payload/headers | Consumer processed it successfully |
| **Consumer finished processing** | SKU-101 projection becomes 0 | Consumer test observes final business state | Production broker always delivers or preserves order |

Some applications also have a fourth level: messages are durably persisted to a broker/outbox and delivered to consumers per dedicated policies. Contract tests with a test binder verify **contents and emission flow in the test environment**, but do not prove durability, exactly-once semantics, or real broker delivery guarantees.

### Where Are Synchronous vs. Asynchronous Parts?

- **Synchronous in tests:** the test method calls `emitStockChanged()` and gets control back.
- **Asynchronous in the app:** the producer may publish on a scheduler, listener, transactional event, or separate thread.
- **Asynchronous in the consumer:** the handler may update the projection after Stub Runner returns.
- **Eventual consistency:** reads right after publishing may temporarily return the old value before reflecting the new one.

**The entire messaging pipeline does not have to run synchronously for tests to be deterministic.** Instead, **wait for the right outcome signal** with a bounded timeout and isolated data.

## 3. Which Timeout Are We Talking About?

The word "timeout" is often overloaded across several mechanisms:

| Timeout Type | Start and End Points | What Does It Check? |
|---|---|---|
| **Producer receive timeout** | After trigger, generated test awaits output message | Did the producer emit to the right destination within the wait window? |
| **Consumer processing wait** | After stub emits event, test awaits application state | Did the handler process and persist the expected state? |
| **Broker poll/receive timeout** | Client/binder awaits a message from queue/topic | Is there a message to read in that poll window? |
| **Request/reply timeout** | A call awaits a matching reply message | Did a correlated reply arrive before deadline? |
| **Retry/backoff deadline** | Multiple attempts or a retrying workflow | When to stop trying and report failure? |
| **JUnit/build timeout** | Total execution time of a test or job | Prevents jobs from hanging forever on setup or broken tests |

These timeouts **do not substitute for one another**. For example, raising the JUnit timeout from 5 to 60 seconds will not help a generated producer test if the messaging receiver only waits a brief configured interval. Conversely, inflating message-receive timeouts can mask destination bugs or slow CI down.

**Do not confuse with HTTP timeouts:** HTTP `504 Gateway Timeout` is an HTTP response from a gateway/server, whereas when a messaging consumer awaits a broker or handler, typically **no HTTP status** is involved.

## 4. Groovy DSL for an Asynchronous Event

Suppose Inventory emits a message after a stock update action. An illustrative Groovy contract can live at `src/test/resources/contracts/inventory/stockChanged.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Emit StockChanged when SKU-101 reaches 0'
    label 'stock_changed'

    input {
        triggeredBy('changeStockForContract()')
    }

    outputMessage {
        sentTo('stock-events')

        body(
            eventType: 'StockChanged',
            sku: 'SKU-101',
            quantity: 0
        )

        headers {
            header('eventType', 'StockChanged')
            messagingContentType(applicationJson())
        }
    }
}
~~~

Meaning of each part:

| DSL | Used By | Role |
|---|---|---|
| `label 'stock_changed'` | Consumer / Stub Runner | Identifies event stub for active triggering |
| `triggeredBy('changeStockForContract()')` | Generated producer test | Calls method in base class to make producer emit event |
| `sentTo('stock-events')` | Messaging verifier | Specifies destination to observe |
| `body(...)` | Generated assertions and stubs | Committed payload and data types |
| `headers {...}` | Generated assertions and stubs | Consumer-relied headers, like event type and content type |

`quantity: 0` is a number, **not** the string `'0'`. If Checkout deserializes quantity into an integer, changing this type can break consumers even when the event delivers cleanly.

Here, `changeStockForContract()` is a method the team **must write in the base test**. Spring Cloud Contract does not automatically know which stock record to mutate or how to await database transactions.

### Equivalent YAML DSL

YAML can be used instead of Groovy:

~~~yaml
description: 'Emit StockChanged when SKU-101 reaches 0'
label: stock_changed
input:
  triggeredBy: changeStockForContract()
outputMessage:
  sentTo: stock-events
  body:
    eventType: 'StockChanged'
    sku: 'SKU-101'
    quantity: 0
  headers:
    eventType: 'StockChanged'
    contentType: 'application/json'
~~~

Both examples carry **the same intent**; do not include both in the same build as two independent contracts for the same scenario if that duplicates tests and stubs.

YAML `input.triggeredBy` is a **method name/invocation**, not a delay configuration. `outputMessage.sentTo` is a **destination**, not a Java variable name. For producer tests to observe the event, the base test and messaging integration must match the actual destination.

## 5. Producer Base Test: Trigger Real Code Then Let Verifier Receive Output

A Spring Boot base class might look like:

~~~java
package com.example.inventory.contract;

import com.example.inventory.InventoryApplication;
import com.example.inventory.InventoryService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.verifier.messaging.boot.AutoConfigureMessageVerifier;

@SpringBootTest(classes = InventoryApplication.class)
@AutoConfigureMessageVerifier
public abstract class InventoryMessageContractBase {

    @Autowired
    private InventoryService inventoryService;

    public void changeStockForContract() {
        inventoryService.changeQuantity("SKU-101", 0);
    }
}
~~~

`InventoryService` and `changeQuantity(...)` are **illustrative** APIs that must match real producer code. The base class must be selected by the Spring Cloud Contract plugin via `baseClassForTests` or plugin base-class mappings.

**What must be protected:** `changeStockForContract()` must actually invoke the **producer's business/publisher flow**. If the method simply pushes a fixture straight to the verifier or mocks all publishing, generated tests can pass without proving the real publisher behaves correctly.

### Publishing After the Method Returns

Suppose `changeQuantity` saves data and emits an event asynchronously. When the generated test invokes the method, the event may arrive at the destination shortly afterward. In the test flow, Spring Cloud Contract's receiver must wait for the output message.

If the producer runs an infrequent outbox worker or a broker takes seconds to spin up, a default generated test might time out before the event appears.

To handle this, prioritize:

1. Ensuring the **test binder/receiver is ready** before invoking the trigger.
2. Configuring scheduling/transactions/binders in tests so events arrive deterministically.
3. Checking the actual timeout of the **messaging verifier/receiver** for your Spring Cloud Contract version and integration.
4. Raising the wait window only after verifying valid events legitimately arrive slightly later under test conditions.
5. If workflows truly depend on slow outbox schedules, adding a **dedicated integration test** rather than forcing every generated contract test onto long timers.

### Test Binder and Verification Scope

With **Spring Cloud Stream**, you can use the **test binder** to avoid depending directly on production Kafka/RabbitMQ. Test binder dependencies and activation depend on your Spring Cloud Stream version.

Example dependency for Spring Cloud Stream lines using a dedicated test-binder artifact:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-stream-test-binder</artifactId>
    <scope>test</scope>
</dependency>
~~~

In certain other configurations/versions, docs use `spring-cloud-stream` with classifier `test-binder` and type `test-jar`. **Do not mix both approaches mechanically.** Use the dependency and activation compatible with your project's Spring Boot/Spring Cloud release train; check logs to confirm the verifier attached to the **right binder and destination**.

The test binder focuses on **contract payloads, headers, and publisher logic** within test scope. It does not prove partition assignment, retry topics, broker retention, or message durability in production.

## 6. Reading Generated Producer Tests: What Is the Test Waiting For?

After configuring Spring Cloud Contract Verifier on the producer module and running the appropriate build lifecycle, generated tests are typically output to directories such as:

~~~text
Maven:
  target/generated-test-sources/contracts/

Gradle:
  build/generated-test-sources/contracts/
~~~

Paths and class names can vary by plugin version/configuration. Check real build logs to confirm tests were generated and **actually executed**.

### Shape of a Generated Test

By Spring Cloud Contract semantics, generated tests perform equivalent steps (**pseudocode**, not verbatim Java output):

~~~text
WHEN:
    changeStockForContract()

THEN:
    msg = messagingVerifier.receive("stock-events", contractSettings)

    assert msg != null
    assert msg.headers["eventType"] == "StockChanged"
    assert msg.contentType matches "application/json"

    payload = decodeJson(msg)
    assert payload.eventType == "StockChanged"
    assert payload.sku == "SKU-101"
    assert payload.quantity == 0  // number
~~~

In official documentation, generated tests call **receive** to fetch a message from the destination along with contract metadata/settings. How timeouts are passed, receiver defaults, polling mechanics, and exact Java APIs depend on version or messaging integration. Therefore, **do not invent a YAML property like `receiveTimeoutMs` assuming Spring Cloud Contract will automatically read it**.

### Five Crucial Pieces of Evidence

When reviewing generated tests, verify:

1. `changeStockForContract()` is actually called and executes against the producer test application.
2. The receiver reads from the **exact destination `stock-events`**, not another queue/topic.
3. The receive call can **wait** for the message with a time bound; understand timeouts per the real API.
4. Assertions verify **headers and payload with proper types**, not just that any message arrived.
5. If multiple messages arrive, the test does not accidentally accept a stale message or an event from another test as proof.

**Receiving a message does not guarantee it came from the trigger that just ran.** If the destination holds stale messages with matching payloads, tests can pass falsely. Isolate state or use distinct test correlation data.

### When Producer Tests Time Out

Diagnose in order:

~~~mermaid
flowchart TD
    A["Generated producer test times out"] --> B{"Was trigger method called?"}
    B -->|No| C["Check base class, generated test, JUnit lifecycle"]
    B -->|Yes| D{"Did producer code publish?"}
    D -->|No| E["Check business logic, transactions, scheduler, error logs"]
    D -->|Yes| F{"Right destination and binder?"}
    F -->|No| G["Check StreamBridge bindings, sentTo, converters"]
    F -->|Yes| H{"Message arrives after timeout?"}
    H -->|Yes| I["Review actual latency, setup, and appropriate receive timeout"]
    H -->|Unclear| J["Trace message IDs, headers, and queue state"]
~~~

Do not edit `outputMessage.body` to make tests wait less. A wrong body causes an **assertion mismatch** once received, whereas a **receive timeout** usually points to triggers, routing, binders, or timing. The two errors require different investigations.

## 7. Consumer Tests: Wait for **Business State**, Not Just the Trigger

On the consumer side, Spring Cloud Contract **Stub Runner** can emit a stub message by `label` via `StubTrigger`.

Illustrative test class example:

~~~java
package com.example.checkout.contract;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.StubTrigger;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.example:inventory-producer:1.0.0:stubs",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class StockChangedConsumerContractTest {

    @Autowired
    StubTrigger stubTrigger;

    @Autowired
    StockProjection stockProjection;

    @Test
    void updatesProjectionAfterStockChanged() {
        // Fixture must create clean initial state.
        // Example: SKU-101 currently has quantity = 8.

        boolean triggered = stubTrigger.trigger(
            "com.example:inventory-producer",
            "stock_changed"
        );
        assertThat(triggered).isTrue();

        await()
            .atMost(Duration.ofSeconds(5))
            .pollInterval(Duration.ofMillis(100))
            .untilAsserted(() ->
                assertThat(stockProjection.quantityOf("SKU-101"))
                    .isEqualTo(0)
            );
    }
}
~~~

**This is a skeleton** and does not include `StockProjection` wiring, database cleanup, or Checkout's binder config. A real project must declare the projection interface/service, seed initial fixtures, ensure the handler listens on `stock-events`, and include Awaitility on the test classpath.

`LOCAL` assumes the stub artifact is already in the local Maven repository. In CI, use the appropriate repository/mode and pin the **exact candidate stub version**, avoiding stale cached artifacts.

### Why Use `untilAsserted`?

With a plain assertion:

~~~java
stubTrigger.trigger("stock_changed");
assertThat(stockProjection.quantityOf("SKU-101")).isEqualTo(0);
~~~

the test may execute too early and read the old value `8`. Using `Thread.sleep(2000)` always wastes at least two seconds even if the handler finishes in 20 ms, and still risks failing when CI load spikes.

With Awaitility:

- Assertions run **repeatedly** until they pass or time runs out.
- The test is **bounded**, never hanging forever.
- Polling exits early once the consumer finishes processing.
- On timeout, the test fails clearly showing the state did not converge within the wait budget.

**What Awaitility does NOT do:** it does not publish messages, manage transactions, register listeners, or fix race conditions in production code. It only **observes the final condition** at the right moment.

### What Makes a Condition Strong Enough?

Do not merely wait for "projection is non-null" if the fixture already created a projection beforehand.

Better:

~~~java
await().atMost(Duration.ofSeconds(5)).untilAsserted(() -> {
    StockView view = stockProjection.find("SKU-101");
    assertThat(view).isNotNull();
    assertThat(view.quantity()).isEqualTo(0);
    assertThat(view.status()).isEqualTo("OUT_OF_STOCK");
});
~~~

`StockView` and `stockProjection` above are **illustrative application types**, not Spring Cloud Contract APIs. Assertions must verify **the exact behavior the consumer relies on**. When tests re-run, make sure initial fixtures do not start with quantity 0 before triggering, or tests could pass without handling the new message.

## 8. Avoiding False Greens: Verify the **Transition**, Not Pre-Existing State

A common bug:

1. A previous test processed `StockChanged` for `SKU-101` and persisted quantity 0.
2. The next test does not reset the database.
3. The next test triggers the event, yet the listener crashes.
4. Awaitility checks `quantity == 0` and **passes immediately** on stale data.

Here the test reports green even though the consumer failed to process the event in the current run.

### Designing Against False Positives

- **Reset projections** to an initial value (e.g., 8) before each test and assert the reset succeeded.
- **Use distinct SKUs/IDs** for independent cases to avoid collisions during parallel runs.
- If events carry an `eventId`, record/observe the last processed ID to distinguish new events from old ones.
- When using databases, ensure reset transactions commit and listener transactions can actually see the needed state.
- If the producer or consumer has **deduplication**, choose test IDs and states so valid messages are not skipped as "already processed".

Mental model:

~~~text
BEFORE:
  projection(SKU-101).quantity == 8
  processedEventId != evt-contract-101

TRIGGER:
  StubTrigger.trigger(stock_changed)

AWAIT:
  projection(SKU-101).quantity == 0
  processedEventId == evt-contract-101
~~~

`evt-contract-101` is an illustrative ID. If the contract does not expose an event ID or the app does not persist it, do not add fields solely for test convenience. At minimum, **isolate fixtures and assert pre-trigger state**.

## 9. Where Should Wait Conditions Be Placed?

| Scenario | What Should You Wait For? | What Should You NOT Wait For Alone? |
|---|---|---|
| Producer just called publisher | Message with right headers/body appears at test destination | Publisher method returning |
| Consumer receives StockChanged | Projection committed with new quantity | Stub trigger returning `true` |
| Consumer saves order after event | Business record actually exists/changed state | Listener method entered before transaction commits |
| Request/reply messaging | Reply matching correlation ID and payload | *Any* message on reply topic |
| Consumer retries on transient errors | Eventually reaches valid outcome or expected retry-exhausted state | Only the first attempt |
| Dead-letter flow | Failed message routed to DLQ with agreed metadata | An exception logged without clear handling outcome |

**Waiting on outcome conditions** keeps tests aligned with real behavior. Still, be careful: some side effects like sending emails or calling external services are hard to observe directly. When needed, fake/mock the external boundary and wait on a meaningful observable signal—never replace core consumer logic with an empty stub.

### Wait Conditions Can Include Multiple Assertions

In an `OrderConfirmed` event test, checking only `status=CONFIRMED` could miss that the total amount never updated. When the consumer depends on both, require both inside the same `untilAsserted`:

~~~java
await().atMost(Duration.ofSeconds(5)).untilAsserted(() -> {
    OrderView order = orderProjection.find("ORD-101");
    assertThat(order.status()).isEqualTo("CONFIRMED");
    assertThat(order.amount()).isEqualTo(125000);
});
~~~

This check requires read consistency adequate for the assertion. If two fields commit in two separate transactions, tests must clarify what the application guarantees and whether intermediate states are acceptable.

## 10. Choosing Timeouts and Poll Intervals with a Grounded Budget

No single timeout number fits every project. Wait duration depends on:

- Context/binder startup time.
- Publisher send latency.
- Broker or test binder latency.
- Thread scheduling and consumer concurrency.
- Deserialization, business processing, and transaction commit time.
- CI runner resource load.

One estimation formula:

~~~text
T_budget =
    T_publish
  + T_delivery
  + T_processing
  + T_commit
  + T_scheduling_margin
~~~

**Illustrative** measurements in a test environment:

| Phase | Typically Observed Range |
|---|---|
| Publish/binder | 30 ms |
| Delivery/scheduler | 60 ms |
| Handler | 150 ms |
| Commit/visibility | 80 ms |
| CI load buffer | 500 ms |
| **Sample budget** | **820 ms** |

Numbers in this table only illustrate the method—**they are not benchmarks or Spring Cloud Contract defaults**. Tests usually need a safety margin above observed values to prevent flakiness, yet should not be bumped to 60 seconds whenever something fails.

### Poll Interval Is Not Timeout

With `atMost(5s)` and `pollInterval(100ms)`:

- **5 seconds** is the maximum wait ceiling.
- **100 ms** is the interval between checks (subject to defaults and specific library settings).
- The test can finish early as soon as the condition holds.

Polling too aggressively wastes CPU and database load; polling too rarely slows failure/success detection. Pick an interval suited to processing speed and projection query cost.

### When Should You Increase a Timeout?

Consider it only after confirming:

1. The message **reached the right destination** yet valid consumer work needs more time.
2. The business scenario is **genuinely asynchronous** and the old limit was below valid execution time.
3. CI has measured scheduler latency and the test still keeps a reasonable deadline.
4. No race conditions or unhandled shared state exist.

If the message was never emitted, went to the wrong queue, or the listener never ran, raising the timeout just makes the test fail **more slowly**.

## 11. Synchronizing Setup and Listeners Before Triggering

A subtle bug is **publishing before the consumer/binder is ready**.

Illustrative scenario:

~~~mermaid
sequenceDiagram
    participant Test as Test thread
    participant Context as Spring context
    participant Listener as Event listener
    participant Bus as Broker / test binder
    Test->>Context: Start
    Context-->>Test: Some beans created
    Test->>Bus: Trigger event too early
    Bus--xListener: No ready subscription / wrong route
    Context->>Listener: Start subscription later
    Test->>Test: Await projection, then timeout
~~~

Fixes:

- Let the test framework build the **full application context** before the test method begins; if listeners initialize asynchronously, wait on a proper readiness condition.
- Use a deterministically configured test binder, and reset/prepare channels before sending events.
- When running real Kafka/RabbitMQ in integration tests, await subscription/consumer assignment using the library's readiness mechanisms rather than sleeping an arbitrary fixed duration.
- Avoid kicking off async tasks in `@BeforeAll` and testing immediately without verifying readiness.
- With multiple listeners, inspect destinations/groups/filters so the right handler activates.

**Never equate** Spring application context startup with all broker subscriptions being ready in every architecture. Readiness semantics depend on framework and infrastructure.

## 12. Message Correlation, Ordering, and Multiple Events on One Destination

A generated test may await a single output message, yet real producers sometimes emit multiple events together:

~~~text
stock-events:
  StockChanged(SKU-202, quantity=5)
  StockChanged(SKU-101, quantity=0)
  StockChanged(SKU-303, quantity=9)
~~~

If the test grabs only the **first message** and asserts `SKU-101`, it can fail by receiving `SKU-202` first. Some receivers read strictly by destination and arrival order; do not assume automatic filtering by business fields.

### Designing Tests to Avoid Collisions

- Use **dedicated test destinations/channels** or isolated environments/binders per test when needed.
- Use deterministic `sku`/event IDs to identify the test's event.
- If the application legitimately emits multiple outputs by design, contracts/tests must describe the **relevant event** and how to select it.
- Keep queues/binders clean between tests; leave no leftover payloads from earlier runs.
- Avoid running contracts sharing a destination in parallel mode when the verifier lacks proper isolation.
- For systems requiring ordering guarantees, verify ordering at the **broker/integration layer** using real partition keys and config rather than inferring it from a simple test binder.

### Correlation in Request/Reply

In **request/reply messaging**, a consumer sends a request message and awaits a reply. Under concurrent requests, replies must carry a **correlation ID** so the caller matches the right response.

A test waiting merely for "any reply on `stock-replies`" can pick up another request's reply. Proper tests assert **correlation keys, payloads, and reply types**. How correlation headers are configured depends on the framework, so do not assume a specific header name like `correlationId` is universal across every broker.

Spring Cloud Contract can describe input/output messages, yet guaranteeing request/reply correctness under high concurrency requires dedicated concurrency tests.

## 13. `messageFrom` and `triggeredBy`: Different Wait Paths

### Scenario A: Producer Emits After an Action

~~~groovy
input {
    triggeredBy('changeStockForContract()')
}
outputMessage {
    sentTo('stock-events')
    body(eventType: 'StockChanged', sku: 'SKU-101', quantity: 0)
}
~~~

The generated test **calls a method** to trigger, then **awaits output**.

### Scenario B: Producer Processes an Input Message

~~~groovy
input {
    messageFrom('stock-commands')
    messageBody(
        command: 'RefreshStock',
        sku: 'SKU-101'
    )
}
outputMessage {
    sentTo('stock-events')
    body(eventType: 'StockRefreshed', sku: 'SKU-101')
}
~~~

The generated test must **send or feed the input message** into the system via the appropriate adapter, then **await output**.

Common principle: **output waiting** is meaningful only when the input/trigger passes through **real producer code** and the right messaging integration. The difference is how processing starts: invoking a method vs. sending a message.

| Criterion | `triggeredBy` | `messageFrom` |
|---|---|---|
| Starts with | Method in base class | Input message on destination |
| Fits when | Task/service/scheduler emits event | Listener consumes command/event and responds |
| Critical setup | Trigger method, business logic, publisher | Input binding/listener, converters, output binding |
| Common wait failure | Method never publishes or publishes post-transaction | Input misses handler or listener unready |
| Ends with | Receiving output message and asserting | Receiving output message and asserting |

Do not add a fake `triggeredBy` into a `messageFrom` contract just to force tests to run: pick the communication model the producer actually exposes.

## 14. Can Retries, Dead-Lettering, and "No Message" Be Verified?

### Retries Can Delay Outcomes

If a consumer hits transient errors and retries, the projection may update only after several attempts. Tests need to:

- Wait for a final business outcome with a **bounded deadline**.
- If proving retry behavior, assert attempt counts or signals exposed by the application.
- Ensure no stale event lets the test pass before the current retry succeeds.
- Avoid excessive real-time delays just to wait out retry backoffs; use fake clocks/schedulers when supported.

### Dead-Letter Queue (DLQ)

When payloads are invalid or handlers fail repeatedly, the broker/binder may route events to a DLQ per config. A contract for a **valid payload** does not test dead-letter policy. Use integration or adapter tests to verify:

- Conditions triggering DLQ routing.
- Retry counts and backoff intervals.
- Error metadata/correlation on dead-lettered messages.
- Safe reprocessing if required by business rules.

### Testing "No Message Emitted"

This is a **negative assertion**: under some condition, the producer must not emit an event. A test waiting 200 ms and observing nothing **cannot prove absolutely** that an event will not appear at 201 ms.

To test non-emission:

1. Identify the **time/behavior boundary** the application guarantees.
2. Prefer asserting **business/transaction decisions** directly whenever possible.
3. If observing a destination, set a justified finite receive window and ensure the queue starts clean.
4. Never treat a single receive timeout as airtight proof producer code can never publish.

With outbox patterns, you may want to assert **no outbox record was created** on transaction rollback or unmet preconditions, rather than merely watching a silent destination.

## 15. Common Causes of Flaky Tests

| Symptom | Possible Cause | Remediation |
|---|---|---|
| Consumer test fails right after `trigger` | Assertion runs before handler | Bounded polling on business state |
| Test passes even with listener disabled | Projection already holds data from prior test | Seed/reset state before test, use event IDs |
| Producer test times out on receive | Method never publishes, wrong destination/binder | Trace trigger → publisher → binding → receiver |
| Fails only in CI | Scheduler load, slow binder startup, overly tight timing | Measure latency, readiness, and set grounded timeouts |
| Fails under parallel runs | Shared destination, state, or event ID | Isolate resources/test cases |
| Test receives wrong payload | Stale messages or producer emits multiple events | Correlation and queue cleanup |
| Stub Trigger returns `false` | Label missing from artifact or stub not loaded | Check `labels()`, artifact version, and messaging adapter |
| Trigger returns `true` yet projection unchanged | Handler unsubscribed, threw error, wrong topic, or uncommitted | Check consumer logs, binder, state, and assertions |
| Message arrives yet headers/types wrong | Converter/schema drift, wrong YAML quotes | Inspect raw message, fix DSL/converter types |
| Retries exceed test timeout | Backoff longer than deadline or persistent failure | Design retry budget and fake clocks |
| Passes solo yet fails in full suite | Shared mutable state or duplicate listener registration | Reset beans/binders/state, enforce test isolation |

### Layering Failures for Debugging

Do not label every failure a "timeout". Categorize them:

1. **Trigger failure:** Method cannot be called or `StubTrigger` cannot find the label.
2. **Publish failure:** Producer code fails to send the message.
3. **Routing/binder failure:** Message emitted yet fails to reach the expected destination.
4. **Receive timeout:** Verifier fails to observe output within the wait window.
5. **Assertion mismatch:** Message received yet headers/body mismatch.
6. **Consumer processing timeout:** Stub emitted, handler may have received it, yet final state was not reached.
7. **Test isolation failure:** Consumed stale messages or state from another test.

Each category has its own diagnostic method; raising `atMost` usually helps only category (6) after confirming the root cause.

## 16. What Consumer Tests with Stub Runner Do Not Prove Alone

| Scope | Well Covered by Contract/Stub Runner | When Are Extra Tests Needed? |
|---|---|---|
| Event payload/headers | Producer tests and stubs verify committed message | Complex schema evolution, custom encodings |
| Consumer reading and handling payload | Consumer tests with stubs, state assertions | Edge branches and boundary data lacking contracts |
| Async handler completion | Awaitility/observable state in tests | Performance and throughput under high load |
| Broker delivery | Test binder simulates delivery within setup scope | Kafka/RabbitMQ retention, partitions, failover |
| Exactly-once/idempotency | Single-event tests can be extended for logic | Duplicate delivery, retries, transactions |
| Ordering | Scenario-specific tests | Multi-partition concurrency and ordering guarantees |
| Outbox transactions | Tests can trigger business logic | Atomic DB commits and real publishing |
| Recovery after disconnects | Fault simulation in test environment | Broker/network failure integration tests |
| Backward compatibility | New contracts + consumer tests with candidate stubs | Older consumers, versioning, live rollouts |

**A producer test passing against a new contract does not mean all existing consumers remain compatible.** If the producer changes `quantity` from a number to a string and edits the DSL simultaneously, new generated tests can still pass. Run real consumer tests using the **same-revision candidate stub** to evaluate compatibility before publishing.

## 17. Bringing Asynchronous Verification into CI

~~~mermaid
flowchart TD
    A["PR updates message contract"] --> B["Validate DSL, label, and destination"]
    B --> C["Generate producer tests"]
    C --> D["Base test triggers publisher"]
    D --> E{"Receive + assert within timeout?"}
    E -->|No| F["Block merge, categorize failure"]
    E -->|Yes| G["Package versioned candidate stub"]
    G --> H["Stub Runner loads right artifact"]
    H --> I["Trigger label and await business state"]
    I --> J{"Consumer processes properly?"}
    J -->|No| K["Investigate listener/schema/state"]
    J -->|Yes| L["Compatibility review then release"]
~~~

### Recommended CI Gates

1. **Contract discovery:** Generator reads the right Groovy/YAML files; never accept a green build with `0 tests`.
2. **Producer setup:** `@AutoConfigureMessageVerifier`, binder, and base class are wired properly.
3. **Producer receive:** Actually receives events from the destination and asserts payload and header types within a reasonable deadline.
4. **Stub artifact:** Tied to a traceable version/commit and contains the event label.
5. **Consumer setup:** Listeners, binders, and projections start clean before triggering.
6. **Consumer wait:** Assertions target business outcomes with clear timeouts and polling.
7. **Isolation:** Parallel tests never unintentionally share messages/state.
8. **Compatibility:** Changes to schemas, headers, destinations, or field types are tested against consumers running older versions.
9. **Observability:** On failure, logs exclude sensitive data yet report trigger, destination, event ID, and actual wait elapsed.
10. **Never ignore flakiness:** Intermittent failures are signals to investigate, not excuses for infinite job auto-retries.

### Recording Traceable Evidence

A useful PR/CI report should show:

~~~text
Contract revision: <commit>
Producer revision: <commit>
Generated test: <class/method>
Messaging integration: <test binder or broker>
Message destination: stock-events
Stub artifact: com.example:inventory-producer:<version>:stubs
Consumer revision: <commit>
Consumer test: <class/method>
Wait condition: quantity(SKU-101) == 0
Wait budget: <configured duration>
Result: PASS / FAIL / TIMEOUT + diagnostic
~~~

Values in `<...>` are placeholders for real reports, not data auto-filled by the plugin.

## 18. Practice Exercise: Fixing an Unreliable Asynchronous Test

### Problem Statement

Checkout uses `StockChanged` events to update its projection. A colleague wrote this test:

~~~java
@Test
void handlesStockChanged() {
    stubTrigger.trigger("stock_changed");
    Thread.sleep(200);
    assertThat(stockProjection.quantityOf("SKU-101"))
        .isEqualTo(0);
}
~~~

The test passes on a local laptop yet intermittently fails in CI. Moreover, even when disabling the listener, the test occasionally still passes.

**Questions:**

1. Why does `Thread.sleep(200)` fail to synchronize reliably with the handler?
2. Why can the test still pass when the listener is not running?
3. What should be verified before triggering?
4. Which wait condition expresses the business outcome properly?
5. If multiple events arrive at the same destination, how do you know the result belongs to the current test's event?

### Reference Solution

**Issue 1:** `Thread.sleep(200)` only pauses the test thread for 200 ms; it does not guarantee the listener received the message and committed data. Under CI load, the handler may need longer.

**Issue 2:** The projection may already contain quantity 0 from an earlier test; the current assertion does not prove the listener processed a new event.

**Issue 3:** Seed/reset fixtures so before the test `SKU-101` has quantity 8; assert that pre-state, drain old events, or use isolated IDs.

**Issue 4:** Use Awaitility and check final state within a deadline:

~~~java
@Test
void handlesStockChanged() {
    assertThat(stockProjection.quantityOf("SKU-101"))
        .isEqualTo(8);

    assertThat(stubTrigger.trigger("stock_changed"))
        .isTrue();

    await()
        .atMost(Duration.ofSeconds(5))
        .pollInterval(Duration.ofMillis(100))
        .untilAsserted(() ->
            assertThat(stockProjection.quantityOf("SKU-101"))
                .isEqualTo(0)
        );
}
~~~

This snippet is only the **test body**; you still need fixture setup, imports, beans, stub artifact, binder, and a real consumer listener. Five seconds is an **illustrative budget**, not a universal optimal default.

**Issue 5:** Use event IDs, correlation/keys if exposed by the interface, or isolate destinations/test data. Never accept an old message with a matching body as evidence for the newly triggered event.

### Extended Exercise: Producer Receives Message Too Late

The generated producer test invokes `changeStockForContract()`, yet the receiver sees no `StockChanged` within the wait window. Producer logs show the event arrives on `stock-events` a few seconds later after a scheduler job runs.

Propose a troubleshooting sequence:

1. Check contract `sentTo`, bindings, and headers.
2. Confirm the trigger method actually invokes the publisher flow.
3. Inspect transactions/outbox/schedulers and measure latency.
4. Decide whether the test should guard the publisher directly or the full scheduled workflow.
5. If keeping the async workflow, configure test setup/receiver timeouts using the **actual API of your Spring Cloud Contract version**.
6. Add broker/outbox integration tests if contract tests only observe part of the interface.

**Do not** "fix" the test by deleting message assertions or immediately setting huge timeouts.

## 19. Pre-Approval Checklist for Messaging Changes

- [ ] Contract specifies `label`, destination, headers, and payload matching consumer needs.
- [ ] `triggeredBy` or `messageFrom` reflects the real action causing the producer to emit the event.
- [ ] Base test calls real producer code and uses the right messaging verifier/binder.
- [ ] Generated test receives the **right message**, not a stale event from another test.
- [ ] Payload and headers are asserted with exact types and matchers.
- [ ] Producer receive timeout is justified and does not mask publish/routing bugs.
- [ ] Consumer Stub Runner uses the **right candidate stub artifact**.
- [ ] Consumer listeners/subscriptions are ready before triggering.
- [ ] Consumer fixtures are reset and **pre-trigger** state is verified.
- [ ] Consumer tests wait for **final business state**, not merely `trigger()==true`.
- [ ] Polling/timeouts are bounded and tuned for CI load.
- [ ] Parallel tests do not share dangerous mutable message state.
- [ ] Retry, duplicate, ordering, DLQ, and transaction behaviors have supplementary tests when business logic depends on them.
- [ ] CI records revision, stub artifact, tests, and actual wait budgets.
- [ ] When changing message schemas/destinations, existing consumers are checked for compatibility.

## 20. Key Takeaways and References

**In messaging contract testing, "trigger succeeded" does not mean "consumer finished processing".** Generated producer tests must **initiate producer behavior and receive the output message** to assert its contents; consumer tests must **use Stub Runner to emit events and await business outcomes** within bounded timeouts. Prioritize polling on observable state, clean fixtures, explicit correlation, and listener readiness.

Spring Cloud Contract protects the message interactions declared in **Groovy/YAML DSL**, without proving every guarantee of brokers, transactions, retries, message ordering, or exactly-once delivery on its own. Combining producer tests, consumer Stub Runner tests, and properly scoped integration tests lets CI catch incompatible message changes while avoiding flaky tests.

### Official References

- [Spring Cloud Contract — Messaging](https://docs.spring.io/spring-cloud-contract/reference/project-features-messaging.html): `triggeredBy`, `messageFrom`, `outputMessage`, verifiers, messaging integrations, and `StubTrigger`.
- [Spring Cloud Contract — YML Schema](https://docs.spring.io/spring-cloud-contract/reference/yml-schema.html): `input` and `outputMessage` structure for YAML DSL.
- [Spring Cloud Contract — Stub Runner](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-boot.html): triggering message stubs by label.
- [Spring Cloud Stream — Testing](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/spring_integration_test_binder.html): choosing the test binder to verify messaging integrations.

**Conclusion:** timeouts must guard a meaningful boundary, polling must observe a meaningful outcome, and every test run must prove **the current run's event** was processed. When those three things are controlled, asynchronous messaging tests become far more reliable and valuable than a fixed `Thread.sleep`.
