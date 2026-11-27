# Triggering the producer with triggeredBy

## Learning objectives

In **Spring Cloud Contract**, a contract does not only describe HTTP requests and responses—it can also describe **messages** exchanged via Spring Cloud Stream, Spring Integration, JMS, or any configured messaging technology. The producer is the service that **emits messages**; the consumer is the service that **receives and handles messages**. **Groovy/YAML DSL** contracts serve as the source to generate **producer-side tests**, package **stubs**, drive **Stub Runner** on the consumer side, and run verification in **CI** to catch incompatible interface changes.

This lesson is part of the **Message contracts** chapter and focuses on `triggeredBy`: how to instruct the generated producer test to **invoke a method in the base test** to initiate message-producing behavior, instead of waiting for another incoming message.

After this lesson, you will be able to:

- Explain the role of `input.triggeredBy` in a messaging contract.
- Write Groovy DSL and YAML DSL describing an **event emitted directly by the producer** after an action.
- Define trigger methods in the **base test class** and wire them to real producer code.
- Read generated producer tests to verify **trigger → receive output → assert payload/headers**.
- Distinguish producer-side `triggeredBy` from consumer-side `label` and `StubTrigger.trigger(...)`.
- Control destinations, binders, fixtures, and wait timeouts so messaging tests remain stable.
- Recognize contract test limits regarding brokers, retries, message ordering, and transactions.

## 1. When do you need triggeredBy?

For example, an inventory management system has two services:

- **Inventory Service** is the producer, emitting a `StockChanged` event whenever item quantities change.
- **Checkout Service** is the consumer, listening to that event to update item orderability.

When the quantity of SKU-101 drops to 0, Inventory emits an illustrative event:

~~~json
{
  "eventType": "StockChanged",
  "sku": "SKU-101",
  "quantity": 0
}
~~~

The event is sent to logical destination `stock-events` and may include headers `eventType: StockChanged`, `contentType: application/json`.

A producer may emit an event for reasons such as:

- A service method is called after completing a business operation.
- An internal command triggers an inventory update.
- A scheduled task finishes processing.
- An internal event is written to an outbox and forwarded.

In all of these cases, **the generated contract test still needs a deterministic action to trigger the producer**. That is when `triggeredBy` is used.

### Core semantics

~~~groovy
input {
    triggeredBy('emitStockChanged()')
}
~~~

This states: **in the producer test, invoke the `emitStockChanged()` method**. The team defines this method in the base test class or somewhere accessible to the generated test, and calling it must lead the producer to emit the event.

`triggeredBy` is **not** a topic name, queue name, or consumer callback. It also **does not emit a message on its own** if the invoked method does nothing.

Separate three concepts clearly:

| Component | Who uses it? | Purpose |
|---|---|---|
| `triggeredBy('emitStockChanged()')` | **Generated producer test** | Calls the method that initiates producer behavior |
| `outputMessage.sentTo('stock-events')` | **Generated test / messaging adapter** | Specifies the destination where the output message must be observed |
| `label 'stock_changed'` | **Consumer test with Stub Runner** | Names the stub event so consumer tests can actively emit it via `StubTrigger` |

Never swap `triggeredBy` with `label` or vice versa. They belong to two different stages of contract testing.

## 2. Seeing the full two-sided flow

~~~mermaid
sequenceDiagram
    participant D as Contract Groovy/YAML
    participant T as Generated producer test
    participant B as Base test class
    participant P as Real producer
    participant M as Messaging verifier / test binder
    participant S as Stub Runner
    participant C as Consumer test
    D->>T: Generate test from triggeredBy + outputMessage
    T->>B: Call emitStockChanged()
    B->>P: Invoke business logic emitting StockChanged
    P->>M: Send message to stock-events
    T->>M: Receive message and assert payload, headers
    D->>S: Package contract into stubs artifact
    C->>S: trigger("stock_changed")
    S->>C: Emit simulated message to destination
    C->>C: Verify handler and consumer state
~~~

**The two verification paths do not replace each other:**

1. **Producer tests** verify that real producer code **actually emits** the right message after being triggered.
2. **Consumer tests** use message stubs to verify that real consumer code **handles** the message according to the contract.

A green consumer test with Stub Runner does not prove Inventory code emits the right message. A green producer test does not prove Checkout handles the message properly.

## 3. A complete Groovy DSL contract

Suppose Inventory emits an event when `SKU-101` goes out of stock. Place the contract in the directory the plugin is configured to scan, for example:

~~~text
src/test/resources/contracts/inventory/
└── stockChanged.groovy
~~~

Contents:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Publish event when SKU-101 stock reaches 0'
    label 'stock_changed'

    input {
        triggeredBy('emitStockChanged()')
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

### Reading each section

| DSL snippet | Meaning | Mistake to avoid |
|---|---|---|
| `description` | Human-readable scenario description | Treating description as a technical assertion |
| `label 'stock_changed'` | Name for consumer tests to trigger the message stub | Thinking label is a Java method name |
| `input.triggeredBy` | Method called by the generated producer test | Thinking it is a topic/broker name |
| `outputMessage.sentTo` | Destination expected to receive the message | Thinking simply writing the string wires up a binder |
| `outputMessage.body` | Expected message content | Confusing `quantity: 0` with string `'0'` |
| `outputMessage.headers` | Headers the producer must emit | Confusing HTTP `Content-Type` with messaging header configuration |
| `messagingContentType(applicationJson())` | Message content is JSON via DSL helper | Assuming consumers always get the right Java type without checking converters |

`body` has three fields with **specific data types**: `eventType` and `sku` are strings, and `quantity` is a number. If the consumer deserializes `quantity` as a number, changing `0` to the string `"0"` can break the contract.

`sentTo('stock-events')` is only an **illustrative destination name**. This name must align with your actual binding or messaging integration configuration.

### What happens in the generated test?

Behaviorally, the generator must produce a test equivalent to:

~~~text
WHEN
    emitStockChanged()

THEN
    receive one expected message from destination "stock-events"
    assert message exists
    assert header eventType == "StockChanged"
    assert messaging contentType == "application/json"
    assert body.eventType == "StockChanged"
    assert body.sku == "SKU-101"
    assert body.quantity == 0 (number)
~~~

This is **pseudocode**, not a verbatim copy of the generated Java test. Exact syntax, classes, and payload-parsing code vary across Spring Cloud Contract versions and messaging adapters. What matters is that the test **actually invokes the trigger method** and **receives a message from the destination**, rather than checking a static JSON fixture.

## 4. Equivalent YAML DSL

Spring Cloud Contract supports expressing the equivalent scenario in YAML. For example, `stockChanged.yml`:

~~~yaml
description: 'Publish event when SKU-101 stock reaches 0'
label: stock_changed
input:
  triggeredBy: emitStockChanged()
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

Differences:

- YAML uses `input.triggeredBy: emitStockChanged()` instead of Groovy `triggeredBy('emitStockChanged()')`.
- `outputMessage.body` is a YAML mapping. Strings, numbers, and booleans must preserve their proper types.
- `headers` is a mapping. `contentType` here belongs to the **message**, not an HTTP request.
- Do not copy the Groovy helper `messagingContentType(...)` verbatim into YAML.

**Choose one format per scenario in a real build**, unless your team intentionally creates distinct contracts and ensures no duplicate mappings/events are generated. Placing both `stockChanged.groovy` and `stockChanged.yml` for the same event can yield duplicate tests or redundant stubs.

### Be careful with YAML quoting

~~~yaml
outputMessage:
  body:
    sku: '00123'
    quantity: 0
    available: false
~~~

`'00123'` is a string identifier; `0` is a number; `false` is a boolean. Changing them to `quantity: '0'` or `available: 'false'` alters the message types. YAML parsers also vary by version/schema for `on`, `off`, `yes`, and `no`, so quote them whenever they must be literal text.

## 5. Writing the trigger method in the base test

A contract with `triggeredBy('emitStockChanged()')` is only useful when the generated test **can invoke** that method. With Spring Boot, the base test class typically boots the application context, registers the messaging verifier, and calls the message-publishing service.

Example Java implementation:

~~~java
package com.example.inventory.contract;

import com.example.inventory.InventoryApplication;
import com.example.inventory.StockEventPublisher;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.verifier.messaging.boot.AutoConfigureMessageVerifier;

@SpringBootTest(classes = InventoryApplication.class)
@AutoConfigureMessageVerifier
public abstract class InventoryMessageContractBase {

    @Autowired
    private StockEventPublisher publisher;

    public void emitStockChanged() {
        publisher.publishStockChanged("SKU-101", 0);
    }
}
~~~

**Mandatory points:**

- The method name `emitStockChanged()` must match the string declared in `triggeredBy`.
- The method must be **accessible** from the generated test; `public` is the clearest choice in examples.
- The method must trigger **real producer code**. If it only logs or builds an object without sending a message, the test will receive no event.
- `@AutoConfigureMessageVerifier` is required to set up messaging verifier infrastructure per Spring Cloud Contract guidance.
- `@SpringBootTest` starts the application in a test environment; it does not automatically ensure every broker, queue, or topic is ready.
- The base class **must be configured in the plugin** via `baseClassForTests` or an appropriate base-class mapping mechanism; simply having a Java file in `src/test` is not enough.

### Which layer should the trigger method call?

| Method approach | Assessment | Why |
|---|---|---|
| Call real application service, which emits the event | **Preferred** when protecting publishing behavior | Test executes through the promised producer code |
| Call real publisher component directly | Suitable when the contract verifies the publisher itself | Does not cover business conditions deciding when to publish |
| Call real controller to trigger business logic | Possible, but involves heavier setup | Requires managing HTTP/auth/backing data |
| Call a fake emitter sending the fixture directly, bypassing producer | **Unsuitable** if the goal is verifying the producer | Test can stay green even when producer code is broken |
| Call a method that emits nothing | Wrong | Generated test waits for a message and fails/times out |
| Call a method that emits multiple random events | Unstable | Test may receive the wrong message or become order-dependent |

Name the method after the **business action**, such as `emitStockChanged()`, `completeShipment()`, or `markInvoicePaid()`. Avoid names like `test1()` or `doSomething()` that obscure where the event originates.

## 6. Example producer publishing via Spring Cloud Stream

Suppose Inventory uses **Spring Cloud Stream `StreamBridge`** to emit events. An illustrative Java component:

~~~java
package com.example.inventory;

import java.util.Map;

import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Component;

@Component
public class StockEventPublisher {

    private final StreamBridge streamBridge;

    public StockEventPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    public void publishStockChanged(String sku, int quantity) {
        Message<Map<String, Object>> message = MessageBuilder
            .withPayload(Map.<String, Object>of(
                "eventType", "StockChanged",
                "sku", sku,
                "quantity", quantity
            ))
            .setHeader("eventType", "StockChanged")
            .setHeader(MessageHeaders.CONTENT_TYPE, "application/json")
            .build();

        boolean sent = streamBridge.send("stockChanged-out-0", message);
        if (!sent) {
            throw new IllegalStateException("Cannot publish stock event");
        }
    }
}
~~~

And destination configuration, for example:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        stockChanged-out-0:
          destination: stock-events
          content-type: application/json
~~~

In this example:

- `stockChanged-out-0` is the **logical binding name** used by the component when calling `StreamBridge.send(...)`.
- `stock-events` is the **destination** where the message is routed.
- The contract declares `sentTo('stock-events')` so the verifier observes the right target.
- `eventType` is an application-set header; `contentType` is specified via the DSL helper and appropriate message header/configuration.

**Important:** this is a Spring Cloud Stream architectural example, not a guarantee that any project will run merely by copying these two files. The producer still needs the right starter/binder, compatible Spring Boot/Cloud versions, and test configuration. If your `StreamBridge` or converter transforms payload/headers differently from the example, inspect the **actual message in the generated test** and adjust configuration accordingly.

### Test binder instead of a production broker

In contract test environments with Spring Cloud Stream, you can use the **test binder** to observe messages without running production Kafka/RabbitMQ. Per Spring Cloud Contract documentation, the test dependency typically looks like:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-stream</artifactId>
    <classifier>test-binder</classifier>
    <type>test-jar</type>
    <scope>test</scope>
</dependency>
~~~

With Gradle, it can be declared as:

~~~groovy
testImplementation(
    group: 'org.springframework.cloud',
    name: 'spring-cloud-stream',
    classifier: 'test-binder'
)
~~~

Depending on the version, you may also need test-binder configuration or `@ImportAutoConfiguration(TestChannelBinderConfiguration.class)` to ensure the test binder is actually active. **Do not assume** merely adding the dependency switches Spring completely to the test binder in every setup. When multiple binders are present, explicitly specify which binder is tested.

### How much does a producer test protect?

Directly calling `StockEventPublisher` only verifies that the component emits a message with the right payload/headers within the test scope. If the real requirement is “emit `StockChanged` only when an order is successfully confirmed”, a test calling only the publisher **does not verify business conditions** or transactions. Design additional service/integration tests, or have the trigger method call the **real application service** for the scenario.

## 7. Connecting the base class to the Spring Cloud Contract plugin

In the producer module, the plugin must know which base class generated tests should extend.

Illustrative Maven configuration:

~~~xml
<plugin>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-contract-maven-plugin</artifactId>
    <version>REPLACE_WITH_COMPATIBLE_VERSION</version>
    <extensions>true</extensions>
    <configuration>
        <testFramework>JUNIT5</testFramework>
        <baseClassForTests>
            com.example.inventory.contract.InventoryMessageContractBase
        </baseClassForTests>
    </configuration>
</plugin>
~~~

`REPLACE_WITH_COMPATIBLE_VERSION` is just a placeholder; use a Spring Cloud Contract version compatible with your project's Spring Boot and Spring Cloud release train. `testFramework` determines the framework for generated tests; JUnit 5 is not necessarily the fixed default across all versions.

With Gradle (illustrative configuration snippet):

~~~groovy
contracts {
    testFramework = 'JUNIT5'
    baseClassForTests =
        'com.example.inventory.contract.InventoryMessageContractBase'
}
~~~

The snippets above are **not complete build files**; you must also apply the plugin, add `spring-cloud-starter-contract-verifier`, repositories, and compatible messaging dependencies. If a project has multiple contract groups requiring different base classes, use the base-class mapping mechanism supported by the plugin.

**Do not choose `testMode=MOCKMVC` just to try messaging:** HTTP test modes and messaging integration are separate mechanisms. For messaging, what matters is `@AutoConfigureMessageVerifier` with the right adapter/binder, not setting up MockMvc when there is no HTTP request.

## 8. Checking what the generated producer test actually does

After configuring the build, the producer runs test generation and execution. With Maven, you can run:

~~~bash
./mvnw clean verify
~~~

Generated tests are typically located at:

~~~text
Maven:
  target/generated-test-sources/contracts/

Gradle:
  build/generated-test-sources/contracts/
~~~

Exact filenames and paths depend on the plugin/version and build output directory. Inspect the build logs to see **how many message contracts were discovered and tests executed**, rather than assuming a green build means all contracts ran.

### Four pieces of evidence to check

For `stockChanged.groovy`, open the corresponding generated test and verify:

1. **Trigger:** The test genuinely calls `emitStockChanged()` (not a stub returning a canned message).
2. **Receive:** After triggering, the test receives a message from `stock-events` via the messaging verifier.
3. **Headers:** The test asserts `eventType`, `contentType`, or whatever headers consumers rely on.
4. **Payload:** The test asserts `eventType`, `sku`, and `quantity` with the promised types/values or matchers.

A conceptual view of the generated test (**pseudocode, not literal Java output**):

~~~text
TEST validate_stockChanged:
  WHEN:
    emitStockChanged()  // method from base class

  THEN:
    message = messagingVerifier.receive("stock-events")
    assert message != null
    assert message.headers["eventType"] == "StockChanged"
    assert contentType is application/json

    payload = decodeJson(message)
    assert payload.eventType == "StockChanged"
    assert payload.sku == "SKU-101"
    assert payload.quantity == 0
~~~

Similar behavior is described in Spring Cloud Contract documentation: the generated test calls the method in `triggeredBy`, then receives a message at the destination and checks body/headers. Assertion syntax may use JsonPath, assertion utilities, or an object mapper depending on the generator.

**Never edit generated tests directly.** If assertions fail or the method is not found, fix the DSL, base class, or binder/test setup and regenerate. Generated files are overwritten on subsequent builds.

### Signs of “green yet insufficient”

- The test sees a message sent, yet fails to check `quantity` even though the consumer requires a number.
- The test never actually ran due to a task filter or undiscovered contracts.
- The base class pushes a fixture directly into a test queue without calling the real publisher.
- A new contract dropped an important field and producer code dropped it too; the new generated test passes while old consumers still break.
- The generated test picks up a leftover message from an earlier test because the destination was shared without resetting.

In such cases, examine **test coverage boundaries** and execution evidence rather than relying solely on CI's green status.

## 9. Distinguishing triggeredBy from messageFrom

The two messaging contract styles serve different scenarios.

### A. Producer emits a message directly after an action

~~~groovy
input {
    triggeredBy('emitStockChanged()')
}
outputMessage {
    sentTo('stock-events')
    body(eventType: 'StockChanged', sku: 'SKU-101', quantity: 0)
}
~~~

Here there is no need to describe a specific input message. The test **invokes a method** to make the producer emit the message.

### B. Producer emits an output triggered by receiving another message

~~~groovy
input {
    messageFrom('stock-commands')
    messageBody(
        command: 'RefreshStock',
        sku: 'SKU-101'
    )
    messageHeaders {
        header('contentType', 'application/json')
    }
}
outputMessage {
    sentTo('stock-events')
    body(
        eventType: 'StockRefreshed',
        sku: 'SKU-101'
    )
}
~~~

Here the generated producer test must **feed a message into** destination `stock-commands` and observe the output. That differs from calling `emitStockChanged()`.

| Question | `triggeredBy` | `messageFrom` + `messageBody` |
|---|---|---|
| Action that starts the test | Calls a method on the base class | Sends a message to an input destination |
| Is an input message needed? | No, unless the method itself triggers an internal message flow | Yes, described in the contract |
| Producer behavior verified | Publishing messages from an operation/task | Processing an input message and emitting output |
| Required setup | Trigger method, service publisher, output adapter | Input adapter/listener, message converter, output adapter |
| Common mistake | Empty method or injecting a fake fixture directly | Test bypasses the real listener |

Avoid declaring both `triggeredBy` and `messageFrom` for the same scenario unless there is a specific reason and you have verified that your DSL supports that combination. Pick the **interaction model matching how the producer actually works**.

## 10. Label and StubTrigger: triggering events on the consumer side

This is the most frequently confused part.

The contract contains:

~~~groovy
label 'stock_changed'
input {
    triggeredBy('emitStockChanged()')
}
~~~

There are **two distinct names**:

- `emitStockChanged()` is the method **on the producer base test**. The generated producer test calls this method.
- `stock_changed` is the **label of the message stub**. The consumer test can call `StubTrigger.trigger("stock_changed")` to tell Stub Runner to emit the simulated event.

**The consumer test never calls the producer's `emitStockChanged()` method.** It only needs the right stubs artifact version and Stub Runner's messaging integration.

### Stub Trigger API

Spring Cloud Contract provides the interface:

~~~java
import org.springframework.cloud.contract.stubrunner.StubTrigger;
~~~

Common usage patterns:

~~~java
stubTrigger.trigger("stock_changed");

// When multiple stubs share a label, specify the producer explicitly:
stubTrigger.trigger("com.example:inventory-producer", "stock_changed");

// You can inspect loaded labels:
stubTrigger.labels();
~~~

Some versions allow a single `artifactId` instead of `groupId:artifactId` as the first argument of the two-parameter overload. In multi-producer systems, prefer full identification to avoid triggering the wrong event.

### Consumer test skeleton example

~~~java
package com.example.checkout.contract;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.StubTrigger;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.example:inventory-producer:1.0.0:stubs",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class StockChangedConsumerContractTest {

    @Autowired
    StubTrigger stubTrigger;

    @Test
    void triggersStockChangedMessage() {
        boolean triggered = stubTrigger.trigger(
            "com.example:inventory-producer",
            "stock_changed"
        );
        assertThat(triggered).isTrue();

        // Wait for Checkout's event handler to process the event.
        // Assert Checkout's real projection/logic reflects quantity=0.
        // Do not merely assert triggered==true and consider the consumer tested.
    }
}
~~~

This is a **skeleton**: it lacks the real consumer/projection class or test binder/broker setup to receive the message. In your project, connect the messaging destination to the consumer handler and assert the **post-processing state**. `LOCAL` requires the stubs artifact in the local Maven repository; CI can use an appropriate repository and configuration mode.

`triggered==true` only indicates that Stub Runner found/triggered the label via its API; **it does not prove the consumer processed it properly**. Add real assertions, such as verifying SKU-101's projection transitions to `OUT_OF_STOCK`.

## 11. Consumer tests and asynchronous handling

Messaging is typically asynchronous, so consumer state may not update immediately after `stubTrigger.trigger(...)`. A test written as:

~~~java
stubTrigger.trigger("stock_changed");
assertThat(stockProjection.find("SKU-101").quantity()).isEqualTo(0);
~~~

can be **flaky** if the handler processes the event on another thread or via a broker. Use bounded waiting rather than fixed `Thread.sleep` calls whenever a better option exists.

Pseudocode example with Awaitility (requires the appropriate test dependency):

~~~java
boolean triggered = stubTrigger.trigger(
    "com.example:inventory-producer",
    "stock_changed"
);
assertThat(triggered).isTrue();

await()
    .atMost(Duration.ofSeconds(5))
    .untilAsserted(() ->
        assertThat(
            stockProjection.find("SKU-101").quantity()
        ).isEqualTo(0)
    );
~~~

You need imports for `org.awaitility.Awaitility.await`, `java.time.Duration`, and the assertions. `stockProjection` merely represents real consumer code. The goal is to **wait until the business condition holds**, within a reasonable timeout, instead of sleeping for an arbitrary interval hoping processing finished.

### Repeatability in tests

- Clear or reset old messages/state before each test.
- Use consistent illustrative data keys like `SKU-101` and quantities.
- Avoid sharing topics/destinations across tests without isolation or correlation filtering.
- If consumers may process duplicate events, add dedicated idempotency tests.
- Avoid overly long sleeps that slow down CI while still risking race conditions.

## 12. Destination and integration: why wasn't the message received?

`outputMessage.sentTo` should not be treated as an arbitrary string. Spring Cloud Contract resolves destinations via the active messaging integration:

- With **Spring Cloud Stream/Spring Integration**, the system typically tries resolving by binding/channel destination, then by channel name using the corresponding mechanism.
- With **Apache Camel**, the name may use component URI syntax, such as `activemq:output`.
- With **JMS/AMQP/Kafka**, queue, topic, binder, broker, and destination semantics depend on the configured framework/adapter.

Thus, in the example:

~~~groovy
outputMessage {
    sentTo('stock-events')
}
~~~

if the component sending to `stockChanged-out-0` is configured with a different destination, the producer test may **receive no message** even though the publisher called `send(...)` successfully.

### Message routing configuration checklist

1. Which binding name is `StreamBridge.send(...)` using?
2. Which `destination` does that binding point to in the test profile?
3. Does `sentTo(...)` resolve to the right target under the messaging adapter?
4. Is the test using the **test binder** or a real broker?
5. Is the `contentType` header set consistently by the converter?
6. Does the destination hold leftover messages from another test?
7. If using a real broker, do the queue/topic exist with publish/subscribe permissions?

**Never fix a destination failure by changing `sentTo` to an arbitrary target just to make tests pass.** The contract must reflect the exact interface consumers subscribe to.

### Multiple messaging frameworks on the classpath

If the application has Spring Cloud Stream, Spring Integration, or other messaging libraries on the classpath simultaneously, Stub Runner may need explicit configuration specifying which integration is active. Spring Cloud Contract documentation provides properties to enable/disable those adapters. With the wrong integration active, message stubs can be misrouted or fail to initialize.

Inspect dependencies, configuration for your **project version**, and Stub Runner logs; never assume “having every messaging starter means Stub Runner picks the right one automatically”.

## 13. Payload and headers: what to fix, what to match?

Contracts should specify the fields consumers truly need. For `StockChanged`, suppose Checkout depends on:

| Field | Illustrative value | Recommended constraint level |
|---|---|---|
| `eventType` | `StockChanged` | Fixed per event type |
| `sku` | `SKU-101` | Concrete sample value or ID format if multiple SKUs apply |
| `quantity` | `0` | Number; tests the out-of-stock branch |
| `eventId` | `evt-1001` | Stable sample in stub; format/constraint on producer if IDs are dynamic |
| `occurredAt` | `2026-01-15T08:30:00Z` | Stable sample + format/controlled clock on producer |
| Header `contentType` | `application/json` | Must be compatible with the consumer's converter |
| Header `eventType` | `StockChanged` | Verify if consumers route based on the header |

If the producer generates varying UUIDs or timestamps, do not hardcode them in producer assertions unless tests control the generator/clock. Spring Cloud Contract Groovy DSL provides **consumer/producer values** and matchers; YAML has its own schema matchers. Place matchers according to **which side is being verified** (request/response or input/output messaging), rather than replacing everything with `.*`.

**Counterproductive example:** checking only `eventType` while ignoring `quantity` even though Checkout relies on it to block orders. Tests could remain green if the producer changed `quantity` from a number to a string.

### Empty or error messages

Some business rules require verifying:

- No event emitted when an update causes no state change.
- No event emitted when a transaction rolls back.
- No duplicate events emitted for an idempotent operation.
- Event emitted with valid schema when quantity hits 0.
- Compatibility preserved with older consumer versions.

Not every “**must not emit**” rule or transaction/deduplication constraint is fully expressible by a single `triggeredBy + outputMessage` contract. Add service/integration tests for state, transaction/outbox behavior, and negative cases.

## 14. Common errors when using triggeredBy

| Symptom | Possible cause | How to investigate |
|---|---|---|
| Generated test reports `emitStockChanged()` not found | Wrong base class or inaccessible method | Check `baseClassForTests`, package, method signature, and generated class |
| Trigger method runs yet test receives no event | Method doesn't call publisher, wrong destination, or binder misconfigured | Check publisher/binder logs, `sentTo`, binding config |
| Test fails on `ContractVerifierMessaging`/message verifier bean | Missing `@AutoConfigureMessageVerifier` or adapter/dependency | Inspect base test and classpath |
| Test receives event from another fixture | Destination has leftover messages or producer emits multiple events | Isolate/clear state, check message count and identifying keys |
| Test waits then times out | Not published, wrong topic, listener unsubscribed, or async incomplete | Trace trigger and receive calls, timeout configuration |
| Stub Trigger cannot find label | Missing/wrong label, stale stubs artifact | Inspect `labels()`, artifact contents, and version |
| `trigger(...)` returns true yet consumer state unchanged | Stub triggered, but consumer not listening or handler errored | Check binder/broker, consumer handler, and state assertions |
| Consumer receives `quantity` as a string | Wrong YAML quoting or serialization differs from commitment | Inspect raw payload, check types and contract |
| Producer test passes yet consumer fails | New contract broke old schema or consumer uses another stub revision | Run consumer tests against candidate stub, compatibility review |
| Passes locally, fails on CI | Missing test binder dependency/repository/profile | Compare CI config and plugin/binder logs |
| Event emitted twice during parallel tests | Shared destination/state or non-idempotent trigger | Isolate data and inspect underlying operation |

### Distinguishing four failure categories

1. **Compile/test-generation failure:** Trigger method or base class is not wired properly.
2. **Receive timeout:** Trigger ran, yet no message reached the destination observed by the verifier.
3. **Assertion failure:** Message arrived, yet fields/headers differ from the contract.
4. **Consumer handler failure:** Stub emitted the event, yet the consumer failed to handle it properly.

Diagnosing by category is faster than randomly tweaking `sentTo`, labels, or timeouts.

## 15. Integrating producer and consumer message tests into CI

A realistic pipeline should carry evidence from the contract to both sides:

~~~mermaid
flowchart TD
    A["PR modifies Groovy/YAML message contract"] --> B["Validate DSL, label, destination"]
    B --> C["Generate producer tests"]
    C --> D["Run triggeredBy base method"]
    D --> E{"Event received + body/headers asserted?"}
    E -->|No| F["Block merge, investigate code/binder/schema"]
    E -->|Yes| G["Package versioned stubs artifact"]
    G --> H["Consumer Stub Runner loads candidate stub"]
    H --> I["trigger(label) + test consumer handler"]
    I --> J{"Consumer tests pass?"}
    J -->|No| K["Fix contract/consumer, plan migration"]
    J -->|Yes| L["Review compatibility and release"]
~~~

Minimum steps:

1. **Contract preflight:** `input.triggeredBy` references an existing method; `label` and `sentTo` represent the true interface.
2. **Generated test discovery:** the plugin finds contracts and executes tests; never treat a green build with 0 tests as success.
3. **Producer verification:** the trigger method invokes real producer code; the message reaches the right destination and body/header assertions pass.
4. **Stub packaging:** publish stubs containing messaging contract definitions from the exact verified revision; avoid overwriting immutable artifacts.
5. **Consumer verification:** Stub Runner loads the right artifact, triggers by label, and tests consumer handlers with bounded timeouts.
6. **Compatibility review:** changing topics, keys, headers, fields, JSON types, or event names must be evaluated against running consumers.
7. **Traceability:** record DSL commit, producer commit, artifact version, and consumer test results.

### Versioning matters

Consumer tests must specify exactly which stub they use, such as `com.example:inventory-producer:1.0.0:stubs` if that is the published coordinate. Never test only against an untraceable `latest` alias and claim a candidate version is verified.

Unlike HTTP stubs that usually represent request/response pairs in WireMock mappings, **messaging stubs need contract definitions and supported messaging routes** for Stub Runner to trigger events. Therefore, verify that the **actual stubs artifact contains the contract** and expected label, rather than looking only for HTTP WireMock JSON mappings.

## 16. Practice exercise: fixing a contract that emits no event

### Scenario

Inventory has a service:

~~~java
public void publishOutOfStock(String sku) {
    publisher.publishStockChanged(sku, 0);
}
~~~

The team writes a contract:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    label 'stock_out'
    input {
        triggeredBy('triggerStockOut()')
    }
    outputMessage {
        sentTo('wrong-destination')
        body(
            eventType: 'StockChanged',
            sku: 'SKU-101',
            quantity: '0'
        )
    }
}
~~~

The team's base class:

~~~java
public void triggerStockOut() {
    // InventoryService or publisher has not been called yet.
}
~~~

Meanwhile, the producer actually sends messages to destination `stock-events` and the consumer expects `quantity` as a **number**.

**Questions:**

1. How many errors prevent the test from verifying the intended behavior?
2. What will the generated producer test do when the trigger method is empty?
3. If you fix the method but keep the wrong destination, what happens?
4. If you fix the destination but keep `quantity: '0'`, what is the risk?
5. Should the consumer test call `triggerStockOut()` or `StubTrigger.trigger("stock_out")`?

### Suggested solution

**At least three errors need fixing:**

1. `triggerStockOut()` does not invoke real producer logic yet.
2. `sentTo('wrong-destination')` does not match destination `stock-events`.
3. `quantity: '0'` is a string, whereas the consumer expects the number `0`.

Fixed version of the contract:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    label 'stock_out'
    input {
        triggeredBy('triggerStockOut()')
    }
    outputMessage {
        sentTo('stock-events')
        body(
            eventType: 'StockChanged',
            sku: 'SKU-101',
            quantity: 0
        )
        headers {
            messagingContentType(applicationJson())
        }
    }
}
~~~

Base test method that can be used:

~~~java
@Autowired
private InventoryService inventoryService;

public void triggerStockOut() {
    inventoryService.publishOutOfStock("SKU-101");
}
~~~

Ensure `InventoryService` actually defines `publishOutOfStock` in the learning project, along with a configured publisher/binder and suitable test state.

**How to interpret outcomes:**

- If the trigger method is empty, the generated test usually receives no message and may time out or fail.
- If the destination is wrong, the verifier may listen in the wrong place even though the publisher emitted the event.
- If `quantity` has the wrong type, even when the event arrives, assertions/consumer deserialization can violate the contract.
- On the consumer side, use `StubTrigger.trigger("stock_out")` to emit the simulated event. Never call the producer's Java method.
- Consumer tests must prove handler logic, not stop at `trigger(...)` returning `true`.

### Advanced exercise

Change the event to `StockChanged` with auto-generated `eventId` and `occurredAt` fields from the producer. Propose:

- Stable sample values for the stub.
- Matchers or tests checking formats on the producer.
- Which fields consumers depend on.
- How to avoid flakiness when consumers process asynchronously.
- How to verify idempotency and event duplication in supplementary tests.

## 17. Checklist before approving a message contract

- [ ] Producer/consumer roles and business semantics of the event are clearly defined.
- [ ] `input.triggeredBy` describes an appropriate trigger method; the method exists and is accessible.
- [ ] The base test is properly selected by the plugin and annotated with `@AutoConfigureMessageVerifier`.
- [ ] The trigger method invokes real producer code instead of sending a fake fixture bypassing the implementation.
- [ ] Messaging adapter/binder/destination align with `outputMessage.sentTo`.
- [ ] `outputMessage.body` preserves exact data types and fields consumers depend on.
- [ ] `outputMessage.headers` protects required headers and content type.
- [ ] Generated tests actually run, receive the right event, and assert payload/headers.
- [ ] `label` is stable and unique enough not to collide across stubs.
- [ ] The stubs artifact contains the message contract from the right revision and is clearly versioned.
- [ ] Consumer tests use `StubTrigger.trigger(label)` and assert real handler/state outcomes.
- [ ] Async tests have bounded timeouts; state/queues are isolated.
- [ ] Destination/schema/version changes are evaluated against older consumers.
- [ ] CI stores producer and consumer test results linked to the same contract revision.

## 18. Key takeaways and references

**`triggeredBy` is how generated producer tests invoke an action that triggers event emission—it is neither a topic name nor a consumer call.** Place it in the `input` block of a messaging contract, and specify outputs via `outputMessage.sentTo`, `body`, and `headers`. The base test must declare that method, call into real producer code, and configure an appropriate messaging verifier/binder.

On the consumer side, **`label` together with `StubTrigger.trigger(...)`** lets Stub Runner emit a simulated event to test the handler. Both sides must use matching contract and stub versions, and CI must actually execute tests rather than merely generating files.

Official references:

- [Spring Cloud Contract – Messaging](https://docs.spring.io/spring-cloud-contract/reference/project-features-messaging.html): `triggeredBy`, `outputMessage`, messaging integrations, and `StubTrigger`.
- [Spring Cloud Contract – YML Schema](https://docs.spring.io/spring-cloud-contract/reference/yml-schema.html): YAML structure for `input.triggeredBy` and `outputMessage`.
- [Spring Cloud Contract – Getting Started](https://docs.spring.io/spring-cloud-contract/reference/getting-started/first-application.html): test generation, base classes, and implementing producer–consumer contracts.

Final note: a contract verifying that an event is emitted with the right payload/headers **does not by itself prove** transactional outbox behavior, broker delivery guarantees, retries, event ordering, or idempotency in production. Those properties require additional tests at the service, integration, and messaging-infrastructure layers.
