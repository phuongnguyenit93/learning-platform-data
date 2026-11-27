# Input, outputMessage, and source/target addresses

## Lesson objectives

In **Spring Cloud Contract**, contracts are not limited to HTTP requests and responses. Many systems integrate via **asynchronous messages**: a service receives a command from a queue/topic, executes business logic, and then emits an event for another service. With **Groovy DSL** or **YAML DSL**, you can describe the trigger condition and the **message the producer commits to emitting**, generating producer-side tests, creating stubs, and letting consumers use **Stub Runner** in CI.

The most important point of this lesson: always read a message contract **from the perspective of the producer being verified**. In a contract:

- `input` describes **what initiates the producer's behavior**: calling a test method or sending a message to a source the producer listens to.
- `outputMessage` describes **the message the producer must emit** after the trigger condition: target destination, body, and headers.
- `messageFrom(...)` inside `input` and `sentTo(...)` inside `outputMessage` represent two **different directions**; their physical meaning depends on the adapter and messaging system configuration.

After this lesson, you will be able to:

1. Distinguish `triggeredBy(...)` from `messageFrom(...)` in `input`.
2. Place `messageBody`, `messageHeaders`, `body`, and `headers` in the right sections of a contract.
3. Identify the intake source and output destination of a message when using queues, topics, or bindings.
4. Write message contracts in Groovy DSL and YAML DSL for two scenarios: **producer emits an event directly** and **producer receives a command and emits an event**.
5. Set up producer test verification, labels/stub triggers, and consumer tests via Stub Runner.
6. Recognize a contract's limits regarding retries, ordering, idempotency, broker configuration, and CI.

## 1. Producer perspective: incoming and outgoing messages

Suppose the system has two activities:

1. **Order Service** receives a request to pay for an order.
2. When payment succeeds, Order Service emits an `ORDER_PAID` event for **Shipping Service** to receive and start shipping processing.

There are two ways to trigger testing of the event-emitting behavior:

- Call a **test-side** method to trigger order processing directly.
- Send a **command message** to the source where Order Service receives messages.

Both ways can lead to the same output event, but they are not the same kind of `input`.

~~~mermaid
flowchart LR
    T["Trigger action"] --> P["Order Service<br/>producer under test"]
    Q["Command on intake source<br/>orders.commands"] --> P
    P --> E["ORDER_PAID event"]
    E --> D["Target destination<br/>orders.events"]
    D --> C["Shipping Service<br/>consumer"]
~~~

In the diagram:

- `orders.commands` is the **source where the producer receives messages** if the scenario is triggered by a command.
- `orders.events` is the **destination where the producer emits the event**.
- Shipping Service is the **consumer of the event**, not a mandatory participant in the producer test.
- If `triggeredBy` is used, the command-message branch may not be needed in that test.

**Do not equate `outputMessage` with an HTTP response.** An HTTP response can be returned immediately, whereas an event is emitted through a broker; sometimes a producer even emits multiple events or processes asynchronously. The contract describes an observable commitment that the tooling and test environment can verify.

## 2. Main components of a message contract

| DSL component | Where it lives | Meaning |
| --- | --- | --- |
| `label` | Contract level | Memorable scenario name; often useful for triggering message stubs by label |
| `input` | Contract level | Condition or source that triggers the producer |
| `triggeredBy(...)` | Inside `input` | References a method invoked by the generated producer test to produce the event |
| `messageFrom(...)` | Inside `input` | Source/binding/channel holding the message **fed into the producer** |
| `messageBody(...)` | Inside `input` | Content of the input command/message in a message-receiving scenario |
| `messageHeaders` | Inside `input` | Headers of the input message |
| `outputMessage` | Contract level | Message the producer must emit |
| `sentTo(...)` | Inside `outputMessage` | Destination/binding/channel where the output message is sent |
| `body(...)` | Inside `outputMessage` | Expected payload of the emitted message |
| `headers` | Inside `outputMessage` | Headers the producer must set on the emitted message |

The names above are the common **Groovy DSL** expressions. In YAML DSL, they appear as correspondingly structured properties. Exact support and destination resolution depend on the Spring Cloud Contract version and messaging integration in use.

### Rule of thumb

~~~text
input:
  triggeredBy  = generated test calls a trigger method
  messageFrom  = generated test feeds a command into the producer
  messageBody  = data of the incoming command
  messageHeaders = metadata of the incoming command

outputMessage:
  sentTo       = where the producer must emit the event
  body         = expected event payload
  headers      = expected event metadata
~~~

For a single scenario, usually pick **one appropriate trigger mechanism**: `triggeredBy` or `messageFrom`. Do not include both just for “completeness”; doing so easily causes the test to invoke the producer twice or obscures where the processing flow begins.

## 3. Example 1: producer actively emits an event via triggeredBy

Suppose Order Service already has payment-confirmation logic. We want to verify that calling that logic emits a properly structured event.

### Groovy DSL

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description "When order is paid, publish ORDER_PAID"
    label "order_paid"

    input {
        triggeredBy("markTestOrderAsPaid()")
    }

    outputMessage {
        sentTo("orders.events")
        body(
            eventId: "EVT-TEST-0001",
            eventType: "ORDER_PAID",
            orderId: "ORD-TEST-1001",
            paidAmount: 150000
        )
        headers {
            header("eventType", "ORDER_PAID")
            header("correlationId", "CORR-TEST-0001")
        }
    }
}
~~~

Explaining each part:

1. `label "order_paid"` sets the **scenario label**. This label is not a broker topic name.
2. `input.triggeredBy("markTestOrderAsPaid()")` references the method the generated producer test must call to trigger the behavior.
3. `outputMessage.sentTo("orders.events")` specifies the expected destination for the emitted event.
4. `body(...)` is the event payload observed by consumers.
5. `headers` checks metadata attributes consumers may rely on, such as event type and correlation ID.

The codes `EVT-TEST-0001`, `ORD-TEST-1001`, and `CORR-TEST-0001` are **synthetic** data, not taken from production. The scenario must have suitable fixtures so the producer emits the expected content. If real IDs or timestamps are dynamic, use controlled values in the base test or appropriate matchers rather than copying production values into the contract.

**Attention:** `markTestOrderAsPaid()` is a test-side method; it is **not** executed inside Stub Runner when the consumer receives the event. The method must exist in the producer test context and genuinely trigger the message-emitting logic under verification.

### Equivalent YAML DSL

~~~yaml
description: "When order is paid, publish ORDER_PAID"
label: order_paid
input:
  triggeredBy: markTestOrderAsPaid()
outputMessage:
  sentTo: orders.events
  body:
    eventId: EVT-TEST-0001
    eventType: ORDER_PAID
    orderId: ORD-TEST-1001
    paidAmount: 150000
  headers:
    eventType: ORDER_PAID
    correlationId: CORR-TEST-0001
~~~

YAML expresses the same idea using mappings. Specific message contract syntax, such as field names and matchers in each section, must be verified against the Spring Cloud Contract version your project uses. **Do not keep both Groovy and YAML files describing the exact same scenario in the build source directory unintentionally**, as that can generate duplicate tests/stubs.

## 4. Example 2: producer receives a command via messageFrom and emits an event

This is the clearest scenario for distinguishing the **intake address** from the **target address**.

Order Service receives the `PAY_ORDER` command on source `orders.commands`, then emits `ORDER_PAID` to destination `orders.events`.

### Groovy DSL for input message

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description "Receive PAY_ORDER and publish ORDER_PAID"
    label "pay_order_command"

    input {
        messageFrom("orders.commands")
        messageBody(
            commandId: "CMD-TEST-0001",
            commandType: "PAY_ORDER",
            orderId: "ORD-TEST-1001"
        )
        messageHeaders {
            header("correlationId", "CORR-TEST-0001")
        }
    }

    outputMessage {
        sentTo("orders.events")
        body(
            eventId: "EVT-TEST-0001",
            eventType: "ORDER_PAID",
            orderId: "ORD-TEST-1001"
        )
        headers {
            header("correlationId", "CORR-TEST-0001")
        }
    }
}
~~~

**Flow explanation:**

1. The generated producer test must send a message with `messageBody` and `messageHeaders` to the **input source** that the producer listens on.
2. The producer handles the command through its real listener/handler within the test configuration.
3. The producer emits a message to the **output destination** declared in `sentTo`.
4. The test uses the message verifier integration to capture the output, then compares body and headers against the contract.

In this scenario, `input` is a **message entering the producer**, not an HTTP request and not data the consumer receives from the producer. `outputMessage` is the message emitted by the producer.

### Equivalent YAML DSL

~~~yaml
description: "Receive PAY_ORDER and publish ORDER_PAID"
label: pay_order_command
input:
  messageFrom: orders.commands
  messageBody:
    commandId: CMD-TEST-0001
    commandType: PAY_ORDER
    orderId: ORD-TEST-1001
  messageHeaders:
    correlationId: CORR-TEST-0001
outputMessage:
  sentTo: orders.events
  body:
    eventId: EVT-TEST-0001
    eventType: ORDER_PAID
    orderId: ORD-TEST-1001
  headers:
    correlationId: CORR-TEST-0001
~~~

Exactly how the adapter uses `messageFrom` and `sentTo` must be configured. There is no guarantee that simply writing address names in YAML will cause Spring Cloud Contract to auto-create the corresponding Kafka topic, JMS queue, Spring Integration channel, or Spring Cloud Stream binding.

## 5. Sequence diagram: test sends a command and captures an event

~~~mermaid
sequenceDiagram
    participant T as Generated producer test
    participant M as Message verifier/adapter
    participant P as Order Service
    participant B as Messaging infrastructure
    T->>M: Send PAY_ORDER to orders.commands
    M->>B: Route message onto configured intake channel
    B->>P: Deliver command to listener/handler
    P->>P: Process order ORD-TEST-1001
    P->>B: Publish ORDER_PAID to orders.events
    B->>M: Provide output message to verifier
    M-->>T: Body + headers + destination
    T->>T: Verify contract commitments
~~~

The diagram shows the **flow that must be configured**; it does not imply every plugin uses a real broker. Some projects use a test binder/channel or custom message verifier; others run a broker testcontainer. Which mechanism is chosen determines how far the producer test's coverage extends.

**There is no need to force a production-like broker just to run contract tests** if the goal is checking event content and publishing logic. However, if topic names, routing, serializers, partition keys, or broker configuration are critical compatibility factors, you must have appropriate integration tests verifying those aspects.

## 6. Are source/target addresses logical or physical?

`messageFrom("orders.commands")` and `sentTo("orders.events")` hold address identifier strings. However, **the meaning of those strings depends on the messaging system and Spring Cloud Contract integration**.

| Context | What the address may represent | What must be verified |
| --- | --- | --- |
| Spring Integration | Channel name | Channel bean exists; test adapter sends/receives on the right channel |
| Spring Cloud Stream | Binding or destination per app configuration | Binding maps to the actual destination; appropriate test binder |
| Kafka | Topic or logical destination defined by the adapter | Producer publishes to the right topic; serializer/headers/key preserved |
| RabbitMQ/AMQP | Queue/exchange/routing key per specific setup | Exchange–queue route and routing metadata |
| JMS | Queue/topic or destination name supported by the adapter | Destination type and message delivery |
| Test double | Channel/buffer in a fake implementation | Test results are only valid within the scope of that fake |

For example, an application might use **binding name** `orderPaid-out-0` in config while the real broker receives messages on topic `orders.events.v2`. If the contract writes `sentTo("orderPaid-out-0")`, you must know whether the adapter matches **binding names** or **physical destinations**.

**Avoid assuming:** “changing the name in `sentTo` changes the topic name on the broker”. A text change in the contract only changes the verification assertion as understood by the tooling; deployment infrastructure still needs corresponding configuration.

### Changing a destination name can be a breaking change

If consumers subscribe to `orders.events` and the producer starts publishing to `orders.events.v2`, old consumers may **receive zero events**, even if the JSON payload stays identical.

To release safely, the team can:

1. Support both old and new destinations in parallel during a transition period.
2. Update and test consumers using the old destination.
3. Publish the version, subscription instructions, and deprecation schedule.
4. Run real routing tests in an appropriate environment if the route itself is part of the commitment.

Do not judge compatibility solely by `body` content; **target address, headers, and delivery mechanism** can be equally critical.

## 7. Input payload vs. output payload

The two payloads in the `PAY_ORDER` → `ORDER_PAID` example have different semantics:

~~~json
{
  "commandId": "CMD-TEST-0001",
  "commandType": "PAY_ORDER",
  "orderId": "ORD-TEST-1001"
}
~~~

This is a **command input**: one party asks Order Service to do something.

~~~json
{
  "eventId": "EVT-TEST-0001",
  "eventType": "ORDER_PAID",
  "orderId": "ORD-TEST-1001"
}
~~~

This is an **event output**: Order Service announces an event that has occurred.

| Property | Command input | Event output |
| --- | --- | --- |
| Role | Triggers processing | Announces completed result/action |
| Type field | `commandType` | `eventType` |
| Identifier | `commandId` | `eventId` |
| Linking data | `orderId` | `orderId` |
| Address | `messageFrom` | `sentTo` |
| Headers | `messageHeaders` | `headers` |

A good contract declares only the fields that consumers and producers actually agree on. Do not force consumers to accept the producer's entire internal entity, and do not strip fields consumers depend on—such as `eventType`, `orderId`, or correlation IDs—when they are part of the promise.

## 8. Headers and routing information

In messaging systems, headers may carry:

- `contentType` or serialization metadata.
- `eventType` and `schemaVersion` helping consumers choose how to parse the payload.
- `correlationId` linking commands and events.
- `tenantId` for multi-tenant processing (use safe test data).
- Technical metadata such as partition keys, trace IDs, or routing information.

Not all broker metadata is an **application header**. For instance, a Kafka record key, a RabbitMQ routing key, or certain native JMS properties have their own representations and transport paths. **Putting a field in `headers` inside a contract does not automatically prove all physical metadata is mapped properly**; if consumers depend on it, verify via the appropriate adapter or integration test.

### Two-way correlation ID example

~~~text
PAY_ORDER sent to orders.commands
  header correlationId = CORR-TEST-0001
  body orderId = ORD-TEST-1001
                  |
                  v
ORDER_PAID emitted to orders.events
  header correlationId = CORR-TEST-0001
  body orderId = ORD-TEST-1001
~~~

Using the same correlation ID is a **business/protocol requirement** if agreed by the parties; it is not something Spring Cloud Contract generates automatically. In tests, fixtures must prepare data so the producer genuinely preserves or maps the correlation ID correctly.

A matcher checking only that correlation ID is a string does not prove **equality between input and output**. If consistency between the two messages is a commitment, use an appropriate assertion/fixture or DSL mechanism to verify that relationship.

## 9. Message verifier and base test class

For HTTP, the generated test sends a request and asserts the response. For messaging, the generated test must have a mechanism to **inject a message or trigger the producer**, and **capture the emitted message**. This relies on the messaging integration and configuration of a **MessageVerifier** or equivalent adapter.

Example base class with a producer trigger method:

~~~java
// Sketch: depends on the application and test configuration,
// not a standalone runnable base class.
public abstract class OrderMessagingContractBase {

    @Autowired
    private OrderApplicationService orderService;

    public void markTestOrderAsPaid() {
        orderService.confirmPayment("ORD-TEST-1001");
    }
}
~~~

A real base class also needs the Spring test context, fixtures, message verifier/binder, a way to wait for output, and state cleanup after tests. The `markTestOrderAsPaid()` method must trigger the **producer's event-emitting logic**, not simply send a hardcoded message copied from the contract just to make the test PASS.

### Two different verification strategies

| Strategy | How it works | Scope of evidence |
| --- | --- | --- |
| **In-process messaging tests** | Uses channels/test binder/message verifier; calls real handler/service | Verifies payload, headers, and publishing logic within the simulated binder scope |
| **Integration tests with a real broker in test env** | Producer sends/receives via Kafka/JMS/AMQP testcontainer or managed broker | Can cover serializers, routing, and part of infrastructure configuration |

You do not always need a real broker, but **you must know which kind of address you are testing**. Passing a test over an in-memory channel does not prove production has configured the right Kafka topic or RabbitMQ routing key.

With asynchronous messages, tests must **wait on conditions with a bounded timeout** and clean up messages/queues between scenarios. Hardcoding `Thread.sleep(1000)` commonly causes flaky tests: wasteful on fast machines, still insufficient on busy CI runners.

## 10. `label` is not synonymous with `sentTo`

Place them side by side:

~~~groovy
label "order_paid"

outputMessage {
    sentTo("orders.events")
    body(eventType: "ORDER_PAID", orderId: "ORD-TEST-1001")
}
~~~

- `order_paid` is the **contract label**, helping humans identify the scenario and enabling label-based stub triggering in Stub Runner messaging modes.
- `orders.events` is the **destination** where the message is published.
- `ORDER_PAID` is the **event type inside the payload**.

These are **three separate concepts**. Changing `label` does not necessarily change where the message is published or its event type. Conversely, changing `sentTo` can break subscribers even if `label` stays unchanged.

### Consumer uses Stub Runner to test receiving the event

A consumer handling `ORDER_PAID` can use stubs published by the producer to generate sample messages. In configurations supporting label-based triggers, consumer tests can call Stub Runner's **StubTrigger** mechanism:

~~~java
// Consumer test sketch in an environment configured with
// Stub Runner and the appropriate messaging integration.
@Autowired
StubTrigger stubTrigger;

@Test
void shouldHandleOrderPaidEvent() {
    stubTrigger.trigger("order_paid");

    // Wait for the consumer handler to process the event.
    // Assert the order moved to the shipping step,
    // or that consumer state changed as expected.
}
~~~

Stub Runner initialization, broker/binder setup, artifact versioning, and how the test awaits consumer processing are omitted from the sketch above; they must be configured per the actual tools and versions. **Not every message contract automatically supports label-based triggering in every adapter**.

Stub trigger **does not call `markTestOrderAsPaid()` on the producer**. The consumer receives a simulated event matching the stubs artifact. Separate producer tests verify that the real producer logic emits the event per the contract.

## 11. Consumer–producer interaction directions to test separately

In an event-driven architecture, there are at least two testing perspectives:

### Producer as an event publisher

~~~text
Order Service (producer) --ORDER_PAID--> Shipping Service (consumer)
~~~

A contract with `input.triggeredBy` and `outputMessage.sentTo` helps verify that the producer emits the event. The event stub lets Shipping Service test its message-handling logic without running a real Order Service.

### Producer as a command receiver that emits an event

~~~text
Checkout --PAY_ORDER--> Order Service --ORDER_PAID--> Shipping Service
~~~

A contract with `input.messageFrom` and `outputMessage.sentTo` describes the flow from command to event. It lets the producer test send a sample command and observe the emitted event. However:

- Checkout still needs to know whether the command it constructs matches the schema.
- Shipping Service needs to know whether the event it receives matches the schema.
- A message-flow test for Order Service **does not automatically verify all consumers**.
- If multiple producers or multiple subscribers share a destination, clarify who owns which contract.

Depending on the architecture, you may need **separate contracts for commands and events** or multiple scenarios to thoroughly verify integration directions. Do not assume a single contract file replaces all contract testing across the system.

## 12. Payload format, schema, and dynamic values

In the `ORDER_PAID` example, the payload is a JSON map:

~~~json
{
  "eventId": "EVT-TEST-0001",
  "eventType": "ORDER_PAID",
  "orderId": "ORD-TEST-1001",
  "paidAmount": 150000
}
~~~

The specification may need to commit to:

1. **JSON types:** `paidAmount` is a number, `orderId` is a string.
2. **Required fields:** are `eventType` and `orderId` always present?
3. **Enum:** is `ORDER_PAID` the official name of the event type?
4. **Dynamic IDs:** in what format is a new `eventId` generated?
5. **Version:** does the payload include `schemaVersion` or a version header?
6. **Address:** is the event published to the exact destination subscribers use?

If event IDs are dynamically generated by the producer, use matchers or test fixtures that control ID generation. Do not call `UUID.randomUUID()` inside a Groovy contract script to generate expected bodies per build; the same contract commit could produce differing outputs.

### Messages are not always JSON

Kafka/JMS/AMQP can transmit strings, byte arrays, JSON, Avro, Protobuf, or custom formats. If real messages are serialized to bytes, tests need to understand **schemas/serializers/content types**. A contract expressing a body as a map does not by itself prove the wire format is JSON exactly as the consumer decodes it.

When consumers depend on a schema registry, schema IDs, or compatibility modes, add corresponding schema checks and serializer/deserializer integration tests. Payload-level contract testing remains valuable, but it **does not replace** serialization-layer guarantees.

## 13. Do not infer broader guarantees from a single sample event

A passing `PAY_ORDER` → `ORDER_PAID` contract typically proves **one input scenario triggered an output matching the expected structure**. It **does not automatically prove**:

| Property | Why a single contract does not prove it |
| --- | --- |
| **At-least-once/exactly-once** | Requires checking how broker, producer, and consumer handle retries/acks/transactions |
| **Idempotency** | Requires testing duplicate commands or replayed events |
| **Ordering** | A single event does not test multi-event/partition ordering |
| **No duplicates** | Requires inducing redelivery, crashes/retries, and comparing |
| **Delivery guarantee** | Stubs may bypass the real broker/network |
| **Retention/DLQ** | Depends on broker configuration and error-handling policies |
| **Performance** | Provides no evidence of throughput/latency or backpressure |
| **Authorization** | Publish/subscribe permissions belong to security and broker setup |

Therefore, when a consumer must handle duplicate or out-of-order events, add appropriate **integration tests or behavioral tests**. Do not stretch the meaning of a passing Contract Verifier run beyond its designed scope.

## 14. Message contracts when the producer handles errors

Suppose `PAY_ORDER` references a nonexistent order. The producer might:

- Emit no `ORDER_PAID`, log an error, and reject the command.
- Emit an `ORDER_PAYMENT_REJECTED` event with its own schema.
- Route the message to an error channel or dead-letter queue after retries.

**You cannot take a success contract and infer error behavior.** If consumers depend on a rejection event, declare a separate scenario with the corresponding expected input and output.

Example **illustrative YAML DSL** for when the producer emits a rejection event:

~~~yaml
description: "Reject payment for nonexistent order"
label: payment_rejected
input:
  messageFrom: orders.commands
  messageBody:
    commandType: PAY_ORDER
    orderId: ORD-TEST-NOT-FOUND
outputMessage:
  sentTo: orders.events
  body:
    eventType: ORDER_PAYMENT_REJECTED
    orderId: ORD-TEST-NOT-FOUND
    reason: ORDER_NOT_FOUND
~~~

This is a **hypothetical business convention** for learning contract design. The event name and `ORDER_NOT_FOUND` code are only valid if the real producer and consumer agree on them. If the system specifies **not emitting any message**, choose an appropriate test assertion strategy; do not assume an empty `outputMessage` is the way to prove absence.

For retries or DLQs, dedicated integration tests are usually needed to verify broker states and timers. Message contract tests primarily describe observable messages, rather than simulating every infrastructure failure mode.

## 15. Common mistakes when writing input and outputMessage

| Symptom | Possible cause | How to resolve |
| --- | --- | --- |
| Generated test cannot find trigger method | `triggeredBy` calls a method missing from the base test | Declare the method, configure the right base class, inspect generated tests |
| Test receives no output message | Producer did not emit, verifier listens on wrong target, or async timeout | Verify routing, binder, fixtures, and wait mechanism |
| Using `sentTo` as an input source | Confusing producer intake and producer emission | Use `messageFrom` for input, `sentTo` for output |
| Using `label` as a broker topic | Confusing scenario label with destination | Distinguish label, eventType, and sentTo |
| Real broker lacks expected destination | Logical binding name differs from physical destination | Check adapter/binder mapping and deployment config |
| Contract test passes yet events miss subscribers | Test uses in-memory channel and skips broker routing | Add integration tests with the right messaging stack |
| Correlation ID header is lost | Publisher or adapter fails to forward header | Check contract and actual serialization/header mapping |
| JSON body is right yet consumer fails to decode | Wrong content type, serializer, schema, or encoding | Check wire format and consumer deserializer |
| Stub trigger emits no event | Messaging integration unconfigured or wrong label | Check stub version, label, and Stub Runner setup |
| Flaky timeout failures | Asynchrony, shared data, or hardcoded sleeps | Isolate state, wait on conditions with bounded timeouts |
| Consumer CI passes with stale stub | Version/revision not pinned | Publish new stub and run consumer against the right artifact |

For message-based failures, investigate in order: **contract discovered** → **generated test executed** → **input triggered the right handler** → **real output appeared at the right destination** → **matchers checked body/headers** → **stubs artifact and consumer tests use the matching version**.

## 16. Testing and publishing message stubs in CI

~~~mermaid
flowchart TD
    A["Groovy/YAML contract reviewed"] --> B["Verifier loads and generates producer tests"]
    B --> C["Base test configures messaging verifier/adapter"]
    C --> D["Invoke trigger or send command"]
    D --> E{"Output captured at right destination?"}
    E -->|No| X["BLOCK"]
    E -->|Yes| F["Verify body/headers/event type"]
    F --> G{"Generated tests PASS and not skipped?"}
    G -->|No| X
    G -->|Yes| H["Package stubs with pinned version"]
    H --> I["Consumer fetches via Stub Runner"]
    I --> J["Trigger stub message and assert consumer"]
    J --> K{"Consumer tests PASS?"}
    K -->|No| X
    K -->|Yes| L["Archive evidence and review compatibility scope"]
~~~

Points CI must enforce:

1. **Correct sources:** Groovy/YAML files are discovered and not silently excluded by filters or directory moves.
2. **Producer tests actually run:** not merely generated and marked green.
3. **Proper messaging infrastructure:** producer tests have the adapter and fixtures to send inputs and capture outputs.
4. **No production data leaks:** payloads, headers, logs, and stubs use synthetic data; never put real tokens in sample messages.
5. **Stub provenance:** artifacts are built from the exact contract revision and producer build that passed tests.
6. **Consumer tests the right stub:** never rely on an old release or a label/event that has not been packaged.
7. **Adequate scope:** critical producers/consumers, addresses, and error branches are verified before rollout.

A **project-designed evidence record**:

~~~yaml
# Illustrative evidence record, not a default SCC configuration.
producer_revision: "order-service@abc123"
contract_revision: "message-contracts@def456"
message_contracts:
  - order_paid
  - pay_order_command
input_destinations:
  - orders.commands
output_destinations:
  - orders.events
producer_message_tests: PASS
stub_artifact: "com.example:order-service:2.4.0:stubs"
consumer_version: "shipping-service:1.9.0"
consumer_stub_tests: PASS
coverage_note: "Does not cover retries, ordering, or broker failover"
~~~

The values here only illustrate traceability. They are not proof that a real pipeline ran. When testing multiple message adapters, explicitly record whether an in-memory binder or a broker testcontainer was used to avoid overstating the report's coverage.

## 17. Guided practice

### Exercise A — Identify input/output direction

Order Service receives `RESERVE_STOCK` at `inventory.commands` and emits `STOCK_RESERVED` at `inventory.events`.

**Task:** place `messageFrom` and `sentTo` in the right blocks, and state which message belongs to `messageBody` and which belongs to `outputMessage.body`.

**Hint:** `input.messageFrom("inventory.commands")` indicates the command intake source; `outputMessage.sentTo("inventory.events")` indicates the event emission destination. The corresponding payloads belong in input and output respectively.

### Exercise B — `triggeredBy` or `messageFrom`?

The producer has a method `completePayment("ORD-TEST-1001")`. Design a contract verifying the `ORDER_PAID` event **without sending a command through a broker**.

**Task:** use `input.triggeredBy(...)`, `outputMessage.sentTo(...)`, body, and label. Explain where the method runs.

**Hint:** the base test defines a zero-argument method referenced by `triggeredBy`, which calls the service under test. Consumer stubs use the label to trigger a simulated output rather than calling the producer's method.

### Exercise C — Distinguish three names

A contract has `label "order_paid"`, `sentTo("orders.events")`, and a body containing `eventType: "ORDER_PAID"`. A teammate suggests renaming the label to `orders.events` because “label is the topic”.

**Task:** explain the mistake and identify what changes when each value is renamed.

**Hint:** `label` is the scenario/stub-trigger label; `sentTo` is the destination; `eventType` is a payload field. All three serve independent roles.

### Exercise D — Correlation ID

The command carries header `correlationId = CORR-TEST-0001`. The outgoing event has the right body but lacks the `correlationId` header, while Shipping Service needs it to correlate transactions.

**Task:** update the contract and design fixtures/producer assertions to verify the header is forwarded properly. Explain why a string-type matcher does not prove the input and output values are equal.

**Hint:** declare `messageHeaders` on input and `headers` on output with consistent sample data; if consumers require a dynamic relationship, add appropriate test assertions/logic.

### Exercise E — Misconfigured broker

A producer test using an in-memory channel passes with `sentTo("orders.events")`; production publishes to a different Kafka topic instead. Shipping Service receives no events.

**Task:** identify the evidence gap and propose an additional integration test.

**Hint:** test the binding → Kafka topic mapping, serializer, and headers in a broker test environment; do not conclude broker routing is verified solely from a payload contract.

### Exercise F — CI passes yet remains incompatible

Producer tests pass and consumer Stub Runner tests pass; however, Shipping Service used an old stub version while the new producer changed the destination and added a required field.

**Task:** list the steps required before release and how to link evidence from both sides.

**Hint:** pin the contract revision, producer build, and stubs artifact; re-run consumer tests with the new stub; evaluate destination/schema changes against active subscribers and plan a compatible rollout.

## 18. Checklist when finalizing a message contract

- [ ] Clearly identified the **producer under verification** and input/output direction from the producer's perspective.
- [ ] Each scenario selects the right trigger mechanism: `triggeredBy` or `messageFrom`.
- [ ] If using `messageFrom`, `messageBody` and `messageHeaders` accurately describe the input message.
- [ ] If using `triggeredBy`, the base test defines the referenced method and it triggers real producer behavior.
- [ ] `outputMessage.sentTo` specifies the right address per the adapter/binder convention in use.
- [ ] `outputMessage.body` and `headers` express the data consumers actually need.
- [ ] `label`, destination, and `eventType` are never confused.
- [ ] Verified binding/logical destination against broker/physical destination when that falls within the commitment.
- [ ] Serialization, schema, content type, and required metadata have been verified.
- [ ] Contract data, fixtures, and stubs contain no sensitive production information.
- [ ] Producer tests genuinely send/trigger inputs and observe outputs, rather than mocking only the final result.
- [ ] Asynchronous waits have bounded timeouts; data and topics/queues are isolated between tests.
- [ ] Error scenarios are considered, with additional tests for retries/idempotency/ordering when needed.
- [ ] The stubs artifact is built from the exact contract revision and passing producer build.
- [ ] Consumer tests use the matching Stub Runner version and verify message-handling logic.
- [ ] CI explicitly documents evidence scope and never treats a passing message contract as a guarantee of system-wide delivery/ordering.

**Key takeaway:** `input` is the **producer's trigger point**, coming either from a test method via `triggeredBy` or an incoming message via `messageFrom`; `outputMessage` is **what the producer must emit**, including `sentTo`, body, and headers. Understanding **data direction and destination semantics** accurately is essential for Spring Cloud Contract to generate useful producer tests, stubs, and CI checks that catch compatibility breaks in message-driven systems.
