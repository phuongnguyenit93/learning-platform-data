# Messaging Adapters for Unsupported Technologies

**Spring Cloud Contract** is not limited to verifying HTTP APIs. A producer might publish an `OrderCreated` event, a consumer might receive a `ReserveInventory` command, or two services might communicate over an internal messaging platform. Contracts must describe **destination, payload, headers, and observable behavior**, then generate **producer verification tests**, publish `stubs` artifacts, let **Stub Runner** trigger events in consumer tests, and wire tests into CI/CD.

Problems arise when a team uses a **proprietary broker, internal SDK, homegrown message gateway, or protocol without a built-in Spring Cloud Contract integration**. If generated tests cannot send or receive messages over that technology, an otherwise valid Groovy/YAML contract still fails to verify the producer. The solution is building a **messaging adapter at the test boundary**, translating Spring Cloud Contract's test calls into send/receive operations of the target transport, while keeping a strict boundary between **mock/fake transports** and **real brokers**.

This lesson belongs to the **Customization and Extension** chapter of the **SPRING_CLOUD_CONTRACT** module. The focus is designing, implementing, and testing an adapter for an unsupported messaging technology, while continuing to practice Groovy/YAML DSL, generated producer tests, stub packaging, Stub Runner, and CI to detect breaking changes between producer and consumer.

Java snippets in this lesson illustrate **integration architecture on Spring Cloud Contract 4.x**. Exact SPI signatures and configuration APIs can vary across library releases, so verify against actual resolved dependencies and generated tests in your project. `TestBusPort`, `BusEnvelope`, and the broker name `AsterBus` are **hypothetical examples**, not built-in Spring Cloud Contract APIs.

## 1. When Is a Custom Adapter Truly Needed?

Spring Cloud Contract provides built-in messaging integrations for popular Spring stacks such as **Spring Cloud Stream, Spring Integration, Spring JMS, and Apache Camel**. For technologies outside those provided integrations, you need a bridge between the verifier and the transport.

| Scenario | Option to Consider | Why |
| --- | --- | --- |
| Application uses Spring Cloud Stream with a supported binder | Use the built-in integration/test binder | Less code to maintain; sufficient for many producer/consumer contract tests. |
| Uses Spring JMS on a properly integrated broker | Use the Spring JMS integration | Avoids reimplementing send/receive from scratch. |
| Uses Apache Camel routes with an existing adapter | Leverage Camel integration | Keeps contracts at the message/destination level. |
| Uses a **proprietary broker SDK** without an integration | Write a `MessageVerifierSender`/`MessageVerifierReceiver` adapter | Must translate verifier calls into SDK send/receive calls. |
| Uses Kafka/RabbitMQ and only wants fast payload tests | Use test binder/fake if suitable, **plus broker integration tests** | Avoids writing a custom adapter when the framework handles most of it. |
| Needs to verify binary wire protocols, schema registries, broker delivery guarantees | Adapter + integration tests against real transport | Message-level contract verification alone may not cover wire bytes/metadata. |

**Do not write an adapter just because you can.** An adapter is code you must maintain across Spring Cloud Contract upgrades, broker SDK updates, and header convention changes. Confirm first whether the app can use an existing integration or wrap the transport with a Spring Cloud Stream binder without altering essential semantics.

## 2. Architecture: Where Does the Adapter Live?

~~~mermaid
flowchart TD
    A["Groovy/YAML messaging contract"] --> B["Spring Cloud Contract Plugin"]
    B --> C["Generated producer verification tests"]
    B --> D["JAR artifact classifier stubs"]
    C --> E["ContractVerifierMessaging / message exchange"]
    E --> F["MessageVerifierSender / Receiver adapter"]
    F --> G["TestBusPort: maps destination, payload, headers"]
    G --> H["Broker test environment or fake transport"]
    H --> I["Real producer publisher / consumer listener"]
    D --> J["Stub Runner"]
    J --> K["StubTrigger by label"]
    K --> F
~~~

**Producer path:**

1. The contract defines the message the producer must emit or consume.
2. The plugin generates tests; generated tests trigger the producer and await messages via the **verifier receiver**, or send inputs via the **verifier sender**.
3. The adapter translates these calls into actions against the broker/test port.
4. Tests assert destination, payload, and headers per the DSL.

**Consumer path:**

1. Stub Runner downloads the `stubs` artifact from a producer-verified contract.
2. Consumer tests invoke `StubTrigger.trigger(label)` or the equivalent API to emit a sample message.
3. The **MessageVerifierSender adapter** pushes the message onto the transport read by the consumer's real listener.
4. Consumer tests assert business outcomes after the listener processes it.

**Note:** a single adapter class can serve both producer and consumer tests, yet the two sides usually have **separate Spring contexts, test ports, and broker credentials**. Never share mutable singleton state across CI jobs and treat the two verification flows as independent.

## 3. Essential SPIs to Know

Spring Cloud Contract documentation describes two interfaces:

- `org.springframework.cloud.contract.verifier.messaging.MessageVerifierSender<M>`: sends a message to a **logical destination**.
- `org.springframework.cloud.contract.verifier.messaging.MessageVerifierReceiver<M>`: receives a message from a destination, typically with a bounded **timeout**.

A unified `MessageVerifier<M>` interface extends both sender and receiver in supporting library versions. Exact methods and contract metadata parameters depend on the version.

Across many Spring Cloud Contract 3.x/4.x lines, adapters may need to implement overloads involving `YamlContract`, such as:

~~~java
// Illustrative signatures showing SPI responsibilities.
void send(Message<?> message, String destination, YamlContract contract);

<T> void send(
    T payload,
    Map<String, Object> headers,
    String destination,
    YamlContract contract
);

Message<?> receive(
    String destination,
    long timeout,
    TimeUnit unit,
    YamlContract contract
);

Message<?> receive(String destination, YamlContract contract);
~~~

`YamlContract` is an internal contract representation used by some SPI versions; **authors writing Groovy DSL do not have to manually convert all contracts to YAML**. Simpler overloads may be default methods delegating to the contract-aware overloads. When building a real adapter, inspect the **interface from your resolved dependency** to match exact generics, packages, and annotations.

| SPI | Responsibility | Must Guarantee |
| --- | --- | --- |
| Sender | Send payload/message over transport. | Exact destination, content type, serialization, required headers. |
| Receiver | Await and return message emitted by producer. | Exact destination, finite timeout, never pick up stale messages. |
| Message conversion | Convert `byte[]`/JSON/records into objects the verifier can assert. | Preserve nulls/types/headers; never alter payload semantics. |
| Destination resolution | Map logical DSL names to physical queues/topics. | Centralized config with validation; never route messages to production. |
| Lifecycle | Connect/register listeners and close resources. | Test isolation, clear offsets/queues, shut down clients and threads. |

**Core point:** Spring Cloud Contract describes **message behavior**; it has no built-in knowledge of proprietary SDK calls like `publishAsync(...)` or `pollPartition(...)`. The adapter is where those operations are translated.

## 4. Choosing an End-to-End Scenario: AsterBus

Suppose the organization uses **AsterBus**—a **hypothetical** broker with an internal SDK. Order Service calls `AsterBusClient.publish(destination, bytes, headers)`; Billing Service registers a listener. Expected contract:

~~~text
Producer: order-service
Logical destination: orders.created
Event type: OrderCreated
Schema version: 1
Content type: application/json
Payload:
  eventId: evt-00042
  orderId: ORD-42
  amountMinor: 125000
  currency: VND
~~~

A transport-level message envelope:

~~~text
Destination: tenant-test.orders.created
Headers:
  eventType: OrderCreated
  schemaVersion: 1
  contentType: application/json
  correlationId: test-run-123
Payload bytes (UTF-8 JSON):
  {"eventId":"evt-00042","orderId":"ORD-42",
   "amountMinor":125000,"currency":"VND"}
~~~

**`orders.created` in the contract is a logical name**, while `tenant-test.orders.created` is an illustrative physical name after test-namespace mapping. The adapter must never rewrite `orderId`, `amountMinor`, or `currency`; otherwise generated tests would assert adapter-fabricated data instead of producer output.

## 5. Defining a Message Contract in Groovy DSL

Placed on the producer side, e.g., `src/test/resources/contracts/messaging/order_created_v1.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'shouldPublishOrderCreatedV1'
    description 'Order Service emits OrderCreated v1 over AsterBus'
    label 'orderCreatedV1'

    input {
        triggeredBy('publishOrderCreated()')
    }

    outputMessage {
        sentTo('orders.created')
        headers {
            header('contentType', 'application/json')
            header('eventType', 'OrderCreated')
            header('schemaVersion', 1)
        }
        body(
            eventId: 'evt-00042',
            orderId: 'ORD-42',
            amountMinor: 125000,
            currency: 'VND'
        )
    }
}
~~~

Explanation:

1. `input.triggeredBy(...)` tells the generated test to **invoke a method on the base test**, thereby triggering **real producer code**.
2. `outputMessage.sentTo(...)` specifies the logical destination the test observes.
3. `headers` contains **cross-service metadata**; the adapter must map types and values faithfully.
4. `body` contains the sample payload; generated tests assert all fields required by the contract.
5. `label` lets **consumer tests** trigger the sample message via Stub Runner once stub messaging is wired.

**Never have `publishOrderCreated()` in the base test fabricate a fake message and push it directly into the adapter receiver.** That would let generated tests PASS even when the production publisher is broken. The trigger method must exercise the **actual code path the producer uses** to emit messages, at least at the application publisher boundary under test.

### 5.1. YAML DSL Variant

If a team prefers YAML, an equivalent contract:

~~~yaml
name: shouldPublishOrderCreatedV1
description: Order Service emits OrderCreated v1 over AsterBus
label: orderCreatedV1
input:
  triggeredBy: publishOrderCreated()
outputMessage:
  sentTo: orders.created
  headers:
    contentType: application/json
    eventType: OrderCreated
    schemaVersion: 1
  body:
    eventId: evt-00042
    orderId: ORD-42
    amountMinor: 125000
    currency: VND
~~~

This is an **alternative**, not a second contract to load alongside the Groovy file. YAML syntax may require adjustments for your plugin/DSL version; after generating tests, inspect **generated test sources and stub artifacts** to confirm expectations.

## 6. Inbound Contracts: When the Producer Consumes Messages

Not every messaging contract starts with `triggeredBy(...)`. If Order Service **receives** a `ReserveInventory` command from another service, a contract can describe an **input message**:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'shouldHandleReserveInventory'
    description 'Listener processes valid inventory reservation command'

    input {
        messageFrom('inventory.reserve')
        messageHeaders {
            header('contentType', 'application/json')
            header('eventType', 'ReserveInventory')
        }
        messageBody(
            requestId: 'req-42',
            sku: 'SKU-42',
            quantity: 2
        )
        assertThat('inventoryWasReserved()')
    }
}
~~~

**Key distinction:**

- For **outbound**: call `triggeredBy(...)` so the producer emits, then the **receiver adapter** observes the message.
- For **inbound**: the generated test uses the **sender adapter** to push the command to `messageFrom(...)`, then checks **side effects** via `assertThat(...)`/base test per DSL and plugin version.

Never make `inventoryWasReserved()` unconditionally return `true`. It must verify **domain state modified by the real consumer listener**. When testing async handlers, await the condition with a finite timeout before deciding.

If a handler emits a response message after receiving a command, the contract can describe both input and output; the adapter must then safeguard **both directions** and ensure receive never picks up leftovers from a prior run.

## 7. Decoupling the Adapter from the SDK via `TestBusPort`

To keep integration logic independent of proprietary SDK APIs, start with a test-owned port interface:

~~~java
package com.acme.contracttest.bus;

import java.time.Duration;
import java.util.Map;

public interface TestBusPort {
    void publish(String destination, BusEnvelope envelope);

    // Returns null if no message arrives within the given timeout.
    BusEnvelope receive(String destination, Duration timeout);

    record BusEnvelope(
        byte[] payload,
        Map<String, Object> headers
    ) {}
}
~~~

**`TestBusPort` is not a Spring Cloud Contract SPI.** It is a project abstraction so the adapter stays decoupled from AsterBus SDK retry, partition, session, or acknowledgment details.

This design brings three advantages:

1. **The adapter depends on a narrow port**, runnable in unit tests without booting a broker.
2. Teams can swap `InMemoryTestBusPort` with `AsterBusSdkTestPort` without touching Groovy/YAML contracts.
3. You can write **port conformance tests**: publish–receive, headers, payload bytes, timeouts, and destination isolation.

**Critical boundary:** if both the producer publisher and the adapter share a **hand-written fake port**, tests verify integration at the fake level, **not that the real AsterBus SDK serializes, routes, and acknowledges properly**. Maintain at least one test layer exercising the real transport or a sufficiently representative test environment.

## 8. An In-Memory Fake Port for Learning and Testing the Adapter

A broker-free example using a separate queue per destination:

~~~java
package com.acme.contracttest.bus;

import java.time.Duration;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

public final class InMemoryTestBusPort implements TestBusPort {

    private final ConcurrentHashMap<String,
            BlockingQueue<BusEnvelope>> queues =
            new ConcurrentHashMap<>();

    private BlockingQueue<BusEnvelope> queue(String destination) {
        return queues.computeIfAbsent(
            destination, key -> new LinkedBlockingQueue<>()
        );
    }

    @Override
    public void publish(String destination, BusEnvelope envelope) {
        queue(destination).add(envelope);
    }

    @Override
    public BusEnvelope receive(String destination, Duration timeout) {
        try {
            return queue(destination).poll(
                timeout.toMillis(), TimeUnit.MILLISECONDS
            );
        }
        catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                "Interrupted while awaiting " + destination,
                interrupted
            );
        }
    }
}
~~~

**This is an illustrative fake**, not a full broker simulator. It does not simulate delivery semantics, acknowledgments, retention, partition assignment, or security. In real codebases, guard against mutable payloads/headers: defensively copy data on publish/receive when tests run concurrently so queued bytes/Maps aren't mutated in flight.

The fake should be **recreated per test context or reset cleanly**. If `queues` survives across tests, a generated test might consume a stale message and PASS falsely. Never use this fake in production or interpret green fake tests as broker certification.

## 9. Adapter Bridge: Implementing Sender and Receiver

When targeting Spring Cloud Contract 3.x/4.x SPIs with `YamlContract`, an illustrative bridge looks like:

~~~java
package com.acme.contracttest.bus;

import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Map;
import java.util.concurrent.TimeUnit;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.cloud.contract.verifier.converter.YamlContract;
import org.springframework.cloud.contract.verifier.messaging.MessageVerifierReceiver;
import org.springframework.cloud.contract.verifier.messaging.MessageVerifierSender;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public final class AsterBusMessageVerifier
        implements MessageVerifierSender<Message<?>>,
                   MessageVerifierReceiver<Message<?>> {

    private final TestBusPort bus;
    private final ObjectMapper mapper;

    public AsterBusMessageVerifier(
            TestBusPort bus, ObjectMapper mapper) {
        this.bus = bus;
        this.mapper = mapper;
    }

    @Override
    public void send(
            Message<?> message,
            String destination,
            YamlContract contract) {
        bus.publish(destination, new TestBusPort.BusEnvelope(
            toBytes(message.getPayload()),
            Map.copyOf(message.getHeaders())
        ));
    }

    @Override
    public <T> void send(
            T payload,
            Map<String, Object> headers,
            String destination,
            YamlContract contract) {
        bus.publish(destination, new TestBusPort.BusEnvelope(
            toBytes(payload),
            Map.copyOf(headers)
        ));
    }

    @Override
    public Message<?> receive(
            String destination,
            long timeout,
            TimeUnit unit,
            YamlContract contract) {
        TestBusPort.BusEnvelope envelope = bus.receive(
            destination, Duration.ofMillis(
                unit.toMillis(timeout)
            )
        );
        if (envelope == null) {
            return null;
        }
        return MessageBuilder.withPayload(
                new String(envelope.payload(), StandardCharsets.UTF_8))
            .copyHeaders(envelope.headers())
            .build();
    }

    @Override
    public Message<?> receive(
            String destination, YamlContract contract) {
        return receive(
            destination, 5, TimeUnit.SECONDS, contract
        );
    }

    private byte[] toBytes(Object value) {
        if (value instanceof byte[] bytes) {
            return bytes;
        }
        if (value instanceof String text) {
            return text.getBytes(StandardCharsets.UTF_8);
        }
        try {
            return mapper.writeValueAsBytes(value);
        }
        catch (Exception ex) {
            throw new IllegalArgumentException(
                "Cannot encode test message payload", ex
            );
        }
    }
}
~~~

**This is an illustrative skeleton; verify compilation against the exact SPI resolved by your project.** Overloads, default methods, or generic return types may vary by version; never copy code blindly without checking dependency Javadocs. A production-ready test implementation must also add destination validation, timeouts, content type handling, and SDK error handling.

### 9.1. Hidden Decisions in the Example

- `toBytes(...)` encodes objects as **UTF-8 JSON**, yet not every broker uses JSON. For Avro, Protobuf, or binary contracts, use the **real codec**.
- `receive(...)` returns the body as a **UTF-8 String**, suited for many JSON text scenarios. For binary payloads or other verifier expectations, return `byte[]` or the expected object.
- `Map.copyOf(...)` rejects null keys and values. If the SDK permits null headers, apply a **header normalization policy** instead of blind copying.
- Some Spring `MessageHeaders` hold internal metadata (`id`, `timestamp`) that should not leak to the broker. A production-grade adapter needs a **header allowlist/mapper**.
- `receive(...)` returns `null` upon timeout; never construct a synthetic “empty” message that tricks generated tests into thinking a message arrived.

A solid adapter preserves **contract semantics**, rather than merely “making generated tests turn green”.

## 10. Converting Headers and Payloads Without Losing Semantics

Spring messages may have payloads and headers structured differently from a proprietary broker envelope:

~~~text
Spring Message
  payload: Object | String | byte[]
  headers: MessageHeaders (id, timestamp, contentType, custom metadata)

Adapter
  validate destination
  encode payload with agreed charset/codec
  map header types + allowlist
  translate logical destination -> physical routing key

AsterBus Envelope
  payload: byte[]
  headers: Map<String, native field>
  destination: tenant-test.orders.created
~~~

| Field | Risk of Adapter Misbehavior | Verification Rule |
| --- | --- | --- |
| `contentType` | `MediaType` serialized to wrong string or dropped. | Inspect actual value on envelope and upon receive. |
| `schemaVersion` | Integer `1` turned into string `"1"` violating contract. | Preserve meaningful types or apply documented normalization. |
| `eventType` | Header name casing altered or header dropped. | Enforce explicit policy; consumer test reads exact key. |
| `correlationId` | SDK auto-generates/overwrites silently. | Distinguish app-promised headers from transport metadata. |
| JSON number | `125000` encoded as string. | Verify types via JSON parser and wire tests. |
| Timestamp | Offset/timezone mutated on serialization. | Use standard formats and properly scoped matchers. |
| `null` vs. missing | Converter strips null fields unexpectedly. | Test per schema/consumer compatibility policy. |
| Binary payload | Decoding through UTF-8 String corrupts bytes. | Keep raw `byte[]` and matching codec/schema. |

**Never copy all Spring-internal headers to a real broker.** Headers like message `id`, `timestamp`, or converter metadata may be meaningless externally. Conversely, never silently drop contracted headers like `eventType` just to simplify the adapter.

### 10.1. Destination Mapping Policy

A dedicated mapper decouples contract names from physical transport names:

~~~java
public final class TestDestinationResolver {
    private final String prefix;

    public TestDestinationResolver(String testNamespace) {
        if (testNamespace.isBlank()) {
            throw new IllegalArgumentException(
                "testNamespace must not be blank");
        }
        this.prefix = testNamespace + ".";
    }

    public String physical(String logical) {
        return switch (logical) {
            case "orders.created" -> prefix + "orders.created";
            case "inventory.reserve" -> prefix + "inventory.reserve";
            default -> throw new IllegalArgumentException(
                "Unknown contract destination: " + logical);
        };
    }
}
~~~

When using a resolver, **sender and receiver must apply the exact same mapping**; producer publisher tests and consumer listeners must bind to the matching namespace. **Fail fast** on undeclared destinations rather than defaulting to a production topic.

## 11. Connecting to the Real AsterBus SDK: A Transport Adapter

Since **AsterBus is hypothetical**, the snippet below shows responsibility flow in **pseudocode**, not an importable library:

~~~java
// PSEUDOCODE — replace with your project's real AsterBus SDK API.
public final class AsterBusSdkTestPort implements TestBusPort {

    private final AsterBusClient client; // Hypothetical API
    private final TestDestinationResolver resolver;

    @Override
    public void publish(String destination, BusEnvelope message) {
        String topic = resolver.physical(destination);
        client.publishAndAwaitAck(
            topic, message.payload(), message.headers()
        );
    }

    @Override
    public BusEnvelope receive(
            String destination, Duration timeout) {
        String topic = resolver.physical(destination);
        AsterBusRecord record = client.pollOne(topic, timeout);
        return record == null ? null : new BusEnvelope(
            record.payloadBytes(), record.headers()
        );
    }
}
~~~

Adapt the design to your real broker:

1. **Sync/async sending:** `publishAndAwaitAck` illustrates waiting for publish confirmation. If the SDK returns a future, await with a timeout rather than ignoring background failures.
2. **Receive semantics:** queue consumption removes/acks messages; topic subscriptions track consumer groups/offsets. Never conflate the two with naive polling.
3. **Cleanup:** test clients, subscriptions, and consumer groups must close cleanly and stay isolated so leftover messages never bleed across tests.
4. **Retries:** adapters must not retry indefinitely, hanging generated tests; enforce bounded policies and clear errors.
5. **Ordering:** if the contract promises ordering, verify partition/key/sequence; otherwise do not assert arbitrary ordering.
6. **Environment:** block CI tests from sending to production queues/topics; scope test credentials strictly to test namespaces.

**This adapter tests real transport better than a fake**, yet still distinguish a send–receive test using the SDK alone from a test proving the **real application listener/publisher** traverses the SDK. Standalone adapter tests do not replace service contract tests.

## 12. Registering the Adapter in the Spring Test Context

Assuming a `contract` test profile, an illustrative configuration:

~~~java
package com.acme.orders;

import com.acme.contracttest.bus.AsterBusMessageVerifier;
import com.acme.contracttest.bus.InMemoryTestBusPort;
import com.acme.contracttest.bus.TestBusPort;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;

@TestConfiguration
public class ContractBusTestConfiguration {

    @Bean
    TestBusPort testBusPort() {
        return new InMemoryTestBusPort();
    }

    @Bean
    AsterBusMessageVerifier asterBusMessageVerifier(
            TestBusPort testBusPort, ObjectMapper objectMapper) {
        return new AsterBusMessageVerifier(
            testBusPort, objectMapper);
    }
}
~~~

To test against a **real broker**, swap the `TestBusPort` bean for the SDK-backed test environment port, ensuring producer business components also **publish to that exact broker/namespace**. If the production publisher was replaced by a fake just to make tests green, the run will not verify real publishing behavior.

### 12.1. Avoiding Collisions with Built-in Auto-Configuration

When Spring Cloud Stream/JMS/Camel/Integration sits on the classpath, Spring Cloud Contract may auto-register a messaging integration. Adding a custom sender/receiver alongside it can cause:

- Multiple beans of the same type and **ambiguous injection**.
- Generated tests silently picking the **default adapter** instead of your custom adapter.
- Consumer Stub Runner publishing to an in-memory channel instead of the broker your real listener reads.

In the test context, **inspect which bean is actually injected** and check auto-configuration conditions for your version. Use `@Primary` or exclude conflicting auto-configurations if supported, explicitly ensuring **only one transport adapter is active per test scope** rather than hiding errors with global bean overriding.

## 13. Producer Base Test: Triggering the Real Publisher

Contract `triggeredBy('publishOrderCreated()')` requires a method invoked by generated tests:

~~~java
package com.acme.orders;

import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.verifier.messaging.boot.AutoConfigureMessageVerifier;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest(classes = OrderApplication.class)
@AutoConfigureMessageVerifier
@ActiveProfiles("contract")
@Import(ContractBusTestConfiguration.class)
public abstract class OrderMessagingContractBase {

    @Autowired
    OrderApplicationPublisher publisher;

    @BeforeEach
    void prepareFixture() {
        // Seed Order 42 and reset test transport state.
    }

    protected void publishOrderCreated() {
        // Call the real application method that emits OrderCreated.
        publisher.publishCreatedOrder(42L);
    }
}
~~~

**`OrderApplicationPublisher` is a hypothetical application component.** `OrderApplication` and fixtures must exist in the project. Maven/Gradle Spring Cloud Contract config must point `baseClassForTests` to `OrderMessagingContractBase` with a compatible test framework.

Verify the package of `@AutoConfigureMessageVerifier` in your resolved version (Spring Cloud Contract messaging auto-configuration commonly uses `org.springframework.cloud.contract.verifier.messaging.boot`). Generated tests must pick up the **right adapter** and **right test profile**.

### 13.1. Never Confuse “Triggering” with “Injecting a Fake Message”

Wrong:

~~~java
protected void publishOrderCreated() {
    testBusPort.publish("orders.created",
        new BusEnvelope(staticJson, staticHeaders));
}
~~~

This tests **the base test's own fake payload**. Regressions in Order Service's serializer, event mapper, or publisher go undetected.

Right direction:

~~~text
publishOrderCreated()
    -> OrderApplicationPublisher
    -> maps Order domain object to event
    -> app outbound adapter/SDK test config
    -> broker/test port
    -> MessageVerifierReceiver
    -> generated assertions
~~~

Even when using an in-memory port for speed, verify that the publisher uses the same transport abstraction/adapter as production at the appropriate boundary, and complement with integration tests for the real SDK.

## 14. What Does a Generated Producer Test Do?

A generated test for an outbound contract has this **logical shape**:

~~~java
// PSEUDOCODE — not verbatim generator output.
@Test
void shouldPublishOrderCreatedV1() {
    publishOrderCreated();

    ContractVerifierMessage actual =
        contractVerifierMessaging.receive("orders.created", contract);

    assertThat(actual).isNotNull();
    assertThat(actual.getHeader("eventType").toString())
        .isEqualTo("OrderCreated");
    assertThat(actual.getHeader("schemaVersion").toString())
        .isEqualTo("1");

    // Parse payload and verify eventId, orderId, amountMinor, currency.
}
~~~

Actual generated tests may use different helper classes or JUnit/Spock syntax. This sketch clarifies the **chain of responsibility**:

1. Invoke the trigger method.
2. Await a message at the destination.
3. Fail if no message arrives within the wait window.
4. Assert headers, body, matchers, and metadata per the contract.

**Never edit generated tests directly to “fix” an adapter.** If no message arrives, inspect destination mapping, bean wiring, and the SDK/test broker first. To change expected behavior, update the contract DSL and verify both producer and consumer compatibility.

## 15. Timeouts, Polling, and Asynchrony: Designing Without Flakiness

A receiver adapter needs explicit policies:

| Concern | Risk | Design Approach |
| --- | --- | --- |
| **Timeout** | `receive` blocks forever, hanging CI. | Finite timeout, consistent units, return null/throw per SPI. |
| **Poll interval** | Polling too tightly overloads broker; too slowly drags tests. | Controlled long-poll/await, no busy spinning. |
| **Send completion** | Async future incomplete when generated test calls receive. | Await ack/future within timeout when semantics require it. |
| **Retries** | Duplicate delivery causes flaky test failures. | Use event IDs and explicit retry/idempotency policies. |
| **Leftover queue items** | Test consumes stale event from prior run. | Isolated namespace/consumer group, reset state, or correlation filter. |
| **Parallel tests** | Two receivers compete for the same queue. | Separate destinations/groups or serialize non-independent suites. |
| **Clock** | Dynamic timestamps break exact matchers. | Assert format/bounds, inject test `Clock` if needed. |
| **Cleanup** | Clients/background threads outlive tests. | Close/stop cleanly in test lifecycle hooks. |

**Never use `Thread.sleep(5000)` as a blanket fix.** Fixed sleeps still fail when CI runs slower than 5 seconds and slow down suites when brokers are fast. Use bounded receive/poll timeouts and diagnostic await conditions.

### 15.1. Timeouts Paired with Selective Logging

When no message arrives, a helpful error reports:

~~~text
Expected message was not received:
  logicalDestination = orders.created
  physicalDestination = run-483.orders.created
  waitTime = 5 s
  testRunId = run-483
  eventType = OrderCreated
~~~

Never print **Authorization**, broker passwords, raw customer payloads, or tokens in logs. When logging correlation IDs, use synthetic test IDs following security rules.

## 16. Headers, Content Types, and Matchers for Messages

In HTTP contracts, response matchers often use JSONPath. In messaging, similar constraints apply to **destination, message headers, and payload**.

A contract with a dynamic `eventId`:

~~~groovy
outputMessage {
    sentTo('orders.created')
    headers {
        header('eventType', 'OrderCreated')
        header('schemaVersion', 1)
        header('contentType', 'application/json')
    }
    body(
        eventId: 'evt-example',
        orderId: 'ORD-42',
        amountMinor: 125000,
        currency: 'VND'
    )
    bodyMatchers {
        jsonPath('$.eventId', byRegex('evt-[A-Za-z0-9-]+'))
    }
}
~~~

**Do not relax every field to “any String”.** Consumers depend on `orderId`, `amountMinor`, and `currency`, so key values and types must remain protected via fixtures or invariants. If the adapter always emits a hardcoded String of its own making, body matchers lose all value.

A subtle bug is **header type conversion**: the broker delivers `schemaVersion="1"` while the contract checks numeric `1`. Agree on a **documented boundary normalization rule** or update the contract if wire semantics mandate strings. Never silently coerce types just to get green builds.

## 17. Adapter Unit Tests: Testing the Bridge Itself

An adapter can harbor bugs even when producer and consumer are healthy. Write a minimal **conformance test suite** independent of generated contract tests.

| Case | Input | Expectation |
| --- | --- | --- |
| Send JSON | `OrderCreated` payload object | Port receives equivalent JSON bytes and right destination. |
| Send binary | `byte[]` | Bytes preserved intact without String conversion. |
| Headers | `eventType`, `schemaVersion`, `contentType` | Contract headers retain exact semantics. |
| Undeclared destination | `unknown.topic` | Fail explicitly; never route to default/prod topic. |
| Receive message | Port holds event on right destination | Verifier receives exact payload and headers. |
| Timeout | No message arrives | Returns timeout result per SPI without hanging. |
| Interrupt | Thread interrupted | Preserves interrupt semantics and cleans up. |
| Multiple destinations | Events A and B | Never cross-reads wrong queue. |
| Serialization error | Unencodable payload | Fail fast; never publish empty payload. |
| Stale message | Queue holds prior run's event | Isolated/cleared/filtered by test run ID. |

A concise port test:

~~~java
@Test
void keepsPayloadAndDestination() {
    TestBusPort bus = new InMemoryTestBusPort();
    byte[] body = "{\"orderId\":\"ORD-42\"}"
        .getBytes(java.nio.charset.StandardCharsets.UTF_8);

    bus.publish("orders.created",
        new TestBusPort.BusEnvelope(
            body, Map.of("eventType", "OrderCreated")));

    TestBusPort.BusEnvelope received =
        bus.receive("orders.created", Duration.ofSeconds(1));

    assertThat(received).isNotNull();
    assertThat(received.payload()).containsExactly(body);
    assertThat(received.headers())
        .containsEntry("eventType", "OrderCreated");
}
~~~

This tests the **fake `TestBusPort`**, not `AsterBusMessageVerifier` or the real broker. Write separate tests for the verifier adapter to test codecs and header mapping before wiring it into generated producer tests.

## 18. Stub Runner with a Custom Messaging Adapter

Producer verification passed and published an artifact:

~~~text
com.acme:order-service:1.0.0:stubs
~~~

In **Billing Service**, consumer tests can use `@AutoConfigureStubRunner` and trigger events by `label`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.StubTrigger;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;
import org.springframework.context.annotation.Import;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@Import(BillingContractBusTestConfiguration.class)
@AutoConfigureStubRunner(
    ids = "com.acme:order-service:1.0.0:stubs",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class BillingOrderCreatedContractTest {

    @Autowired
    StubTrigger stubTrigger;

    @Autowired
    BillingEventProbe billingEventProbe;

    @Test
    void handlesPublishedOrderCreated() {
        assertThat(stubTrigger.trigger(
            "com.acme:order-service", "orderCreatedV1"
        )).isTrue();

        assertThat(billingEventProbe.awaitOrder(
            "ORD-42", java.time.Duration.ofSeconds(5)
        )).isTrue();
    }
}
~~~

`BillingContractBusTestConfiguration` and `BillingEventProbe` are **project-created test components**; `BillingEventProbe.awaitOrder(...)` must observe outcomes from the **real listener** rather than unconditionally returning `true`.

**Mandatory requirements:**

1. `LOCAL` requires the stub JAR in the consumer test runner's Maven local repo; `REMOTE` fetches from an artifact repository with proper credentials/auth.
2. `StubTrigger.trigger(...)` uses the contract's **label**. `StubFinder` can also be used since it extends triggering capabilities; this is not an HTTP port API.
3. The Spring context must have an **active sender adapter**. Downloading the `stubs` artifact without a transport sender will never deliver messages to the consumer listener.
4. Consumer tests should assert the listener's **business side effects**—e.g., Billing recorded an event or updated status—not merely that trigger returned `true`.
5. Trigger returning success does not prove broker **delivery/acknowledgment** if the adapter sends asynchronously without awaiting confirmation.

### 18.1. Using Stub Runner JUnit 5 Extension Instead of Spring Annotations

Stub Runner’s JUnit 5 extension builder APIs may allow passing **sender/receiver implementations** directly instead of relying solely on a Spring context:

~~~java
// PSEUDOCODE API shape: verify exact builder methods per version.
StubRunnerExtension extension = new StubRunnerExtension()
    .stubsMode(StubRunnerProperties.StubsMode.LOCAL)
    .downloadStub("com.acme:order-service:1.0.0:stubs")
    .messageVerifierSender(customSender)
    .messageVerifierReceiver(customReceiver);
~~~

**Do not combine this with the annotation as two mandatory steps.** Choose either **Spring annotations/config beans** or the **JUnit extension builder** per your test architecture, and verify which setters your Stub Runner version provides. Omitting messaging sender/receiver on the JUnit extension can cause message triggering to throw instead of sending.

## 19. Testing Against a Real Broker: Different Scope from a Fake Adapter

Another test layer may use a **broker container/test tenant** instead of a fake. If AsterBus lacks a Testcontainers module, you can:

- Start a service container from an **approved image** or docker-compose file in CI.
- Use a **test cluster/tenant** with isolated queue/topic prefixes and least-privilege credentials.
- Build a real SDK port targeting the test endpoint with health checks and cleanup.
- Tag test messages with a unique `runId`/`correlationId` to avoid reading another job's messages.

| Verification Level | Catches Well | Does Not Prove |
| --- | --- | --- |
| **Adapter unit test with fake** | Send/receive structure, mapping, basic timeouts. | Real broker SDK or transport. |
| **Producer contract test with well-bounded fake** | Publisher produces contract-compliant data at the chosen boundary. | Wire encoding and broker delivery semantics. |
| **Broker integration test** | SDK serialization, headers, routing, send/receive, ack/retry in test env. | Every production configuration/policy. |
| **Consumer Stub Runner test via test broker** | Real listener handles contract sample messages. | Real producer deployment unless backed by producer verification/deploy provenance. |
| **End-to-end staging** | Multi-service flows in production-like environments. | Repeatability and isolation of contract tests. |

**Do not turn every contract test into a heavyweight E2E test**, yet never claim fake tests “proved production Kafka/AsterBus”. Layering keeps suites fast and stable while catching SDK/codec bugs at the integration layer.

### 19.1. Inspecting Wire Bytes When Necessary

Suppose `amountMinor` is numeric, yet a serializer turns it into a string:

~~~json
{"orderId":"ORD-42","amountMinor":"125000"}
~~~

If adapter tests bypass the real codec, generated producer tests might inspect a domain object and PASS even though **real consumers fail parsing the wire bytes**. Maintain integration tests that read **bytes published by the real SDK**, decode them using the shared schema, and assert:

- `amountMinor` remains a JSON number or promised Avro/Protobuf type.
- Timestamps, enums, nulls/missing fields, and numeric precision are exact.
- `contentType`/`schemaVersion` and transport metadata match.
- Supported consumer decoder versions accept the payload.

Especially with Avro/Protobuf, schema registries and compatibility modes are part of the test environment, not just `outputMessage.body(...)`.

## 20. Security of Custom Messaging Adapters

A custom adapter has permission to publish and consume messages, so misconfiguration can **cause real side effects**.

| Risk | Mitigation |
| --- | --- |
| CI publishes to a production topic | Destination allowlists, mandatory test namespaces, test-tenant-only credentials. |
| Broker secrets leaked in logs | Inject secrets at runtime, never log Authorization/token headers, redact logs. |
| Stub artifacts contain real data | Use synthetic fixtures; scan Groovy/YAML/stubs for secrets. |
| Consumer tests compete on production queues | Use isolated test queues; never subscribe to live customer traffic. |
| SSL verification disabled to “make tests pass” | Configure proper CA/truststores; reject insecure TLS workarounds. |
| Adapter allows arbitrary destinations | Fail closed, validate mappings, prevent untrusted input from choosing queue names. |
| Infinite retries cause flooding | Cap attempts/backoff, enforce timeouts and test quotas. |
| Using broker admin credentials | Use least-privilege identities scoped to test topics/namespaces. |

**Never place secrets in contract DSLs or stub JARs.** Those artifacts may be downloaded by many consumer teams for testing, so treat their contents as shared documents.

## 21. CI/CD: Ensuring Producer and Consumer Tests Use the Same Contract

~~~mermaid
flowchart TD
    A["Producer commit + Groovy/YAML contract"] --> B["Resolve Spring Cloud Contract Plugin + adapter version"]
    B --> C["Run adapter conformance tests"]
    C --> D["Generate producer verification tests"]
    D --> E["Run producer contract tests"]
    E --> F{"Tests actually ran and passed?"}
    F -->|No| G["Block stub publish"]
    F -->|Yes| H["Broker SDK integration tests per policy"]
    H --> I["Package immutable stubs JAR"]
    I --> J["Publish version + checksum/provenance"]
    J --> K["Consumer CI fetches exact stub artifact"]
    K --> L["Stub Runner triggers via custom sender"]
    L --> M["Assert real listener + business outcome"]
~~~

A pipeline should record:

1. **Contract source Git SHA**, Groovy/YAML path, and version/label.
2. Compatible **Spring Cloud Contract plugin/starter/BOM versions**.
3. **Custom adapter version** and SDK version.
4. **Producer generated test report** with executed test counts, not merely `BUILD SUCCESS`.
5. **Broker integration test report**, if required.
6. **Stub JAR Maven coordinates + SHA-256** so consumers fetch exact bytes.
7. **Consumer CI run**, artifact version, test profile, and whether backend was fake or real broker.
8. **Test environment ID**/namespace and redacted logs for debugging flakiness.

**Never publish stubs merely because a converter emitted files**; require generated producer tests verifying the implementation and an artifact with provenance. With custom adapters, also block publication if **adapter conformance tests fail**.

### 21.1. Maven and Gradle Dependencies

Producers need Contract Verifier in **test scope** plus the Maven/Gradle Contract Plugin to generate tests; consumers need Stub Runner in **test scope**. Example Maven dependencies:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-contract-verifier</artifactId>
    <scope>test</scope>
</dependency>
~~~

On the consumer side:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-contract-stub-runner</artifactId>
    <scope>test</scope>
</dependency>
~~~

Gradle Groovy DSL:

~~~groovy
dependencies {
    testImplementation(
        'org.springframework.cloud:spring-cloud-starter-contract-verifier'
    )
    // Consumer module, if needed:
    testImplementation(
        'org.springframework.cloud:spring-cloud-starter-contract-stub-runner'
    )
}
~~~

These are **configuration fragments**, not complete builds. Include a Spring Cloud BOM compatible with Spring Boot/Contract Plugin; add the **AsterBus SDK** and adapter test module per your project. **Never blindly add both Verifier and Stub Runner to every module** if the role is not needed.

## 22. Common Pitfalls When Writing Custom Adapters

| Symptom | Possible Cause | How to Investigate |
| --- | --- | --- |
| Generated test reports missing messaging verifier | Missing `@AutoConfigureMessageVerifier`, wrong bean type, or context didn't load. | Check annotations, bean report, plugin/starter compatibility. |
| Two `MessageVerifierSender` beans found | Auto-integration and custom adapter both registered. | Inspect bean selection, profiles, auto-config conditions. |
| Producer trigger runs yet receive sees no event | Publisher sends to different physical destination than receiver. | Log redacted logical→physical mapping; check namespace. |
| Generated test receives stale message and PASSes | Queue/offset not reset, shared consumer group. | Isolate test runs, correlation IDs, and cleanup. |
| `receive` hangs CI | Infinite poll or SDK ignores timeout. | Enforce finite timeout, check cancellation and cleanup. |
| `receive` returns null too early | Poll timeout too low or async send incomplete. | Check send ack, timeout policy, and scheduling. |
| Header `schemaVersion` comparison fails | SDK converts integer to string. | Apply agreed normalization or fix mapping; test wire metadata. |
| JSON payload is double-encoded | `ObjectMapper` re-serializes a String as a quoted JSON string. | Separate String/byte[]/object paths and test codecs. |
| Binary payload corrupted | Bytes converted through UTF-8 String. | Preserve raw bytes/matching serializer. |
| Stub Runner reports trigger label not found | Wrong label or `stubs` JAR lacks contract. | Check contract label, artifact version/content, source scan. |
| Trigger succeeds yet listener doesn't run | Sender enqueues into different fake than listener port, or doesn't await delivery. | Check shared context/namespace and verify business side effects. |
| Passes on fake, fails on broker | Routing, serialization, acks, auth differ. | Run broker integration tests with real SDK. |
| 401/403/SSL error downloading stubs | Repository credentials/TLS, not messaging destinations. | Distinguish artifact download from message transport. |
| Messaging tests fail in parallel CI | Shared topic/group/queue, stale events, or port collisions. | Use dedicated test namespaces/consumer groups and reset state. |
| Required header missing in test | Adapter allowlist too narrow or converter stripped metadata. | Inspect envelope before/after adapter and contract DSL. |
| Gradle/Maven build green yet generated tests don't run | Plugin/source paths/test runner misconfigured. | Inspect generated sources, test reports, and test counts. |

**Diagnostic path:** DSL loaded → generated tests exist → right verifier bean → trigger calls real publisher → adapter mapping matches → broker/test port receives message → verifier assertions pass → stub artifact has right label/version → Stub Runner sends to real listener → consumer side effect verified.

## 23. Mutation Tests Prove the Adapter Doesn't Hide Bugs

A hand-written bridge can easily become a “green-test machine”. Test intentional mutations on a branch:

| Mutation | Expected Outcome |
| --- | --- |
| Producer changes `amountMinor` to String | **FAIL** contract/wire codec test. |
| Producer changes `orders.created` to `orders.cancelled` | **FAIL** destination receive check. |
| Producer drops `eventType` | **FAIL** header assertion. |
| Producer bumps `schemaVersion` from 1 to 2 unversioned | **FAIL** if consumer expects v1. |
| Producer emits valid payload missing `orderId` | **FAIL** required body field. |
| `eventId` changes value while staying within allowed format | **PASS** if contract promises format only. |
| Test broker goes down | **FAIL clearly**, never silently pass via a NoOp adapter. |
| Consumer listener skips processing event | **FAIL** side-effect assertion. |
| Stub Runner uses wrong trigger label | **FAIL** citing clear label/artifact info. |
| Receives message from an old test run | **FAIL or filtered out**, never false-pass. |

**Never write an adapter that synthesizes an “expected message” after timing out.** When no message arrives, tests must fail or receive the SPI-defined timeout result. Write a conformance test on the receiver proving it never fabricates payloads when the broker is silent.

## 24. Rollout Roadmap for a Custom Messaging Adapter in a Team

A practical sequence:

1. **Define adapter responsibilities**: needed for producer outbound, consumer inbound, Stub Runner trigger, or all three?
2. **Evaluate built-in integrations** before writing custom code.
3. **Choose contract source/versions** and destination/header semantics consumers genuinely need.
4. **Define `TestBusPort`** plus SDK-independent codec/destination/header policies.
5. **Write a fake port** for adapter unit/conformance tests.
6. **Implement custom Sender/Receiver** matching your project's Spring Cloud Contract SPI version.
7. **Register beans in the test context** and resolve auto-configuration conflicts.
8. **Create base tests** where generated tests trigger the **real publisher** or assert real listener side effects.
9. **Write the SDK transport port** against a broker test tenant/container, testing serialization/headers/acks/offsets.
10. **Generate and run producer tests**, checking test counts and negative mutations.
11. **Package/publish the `stubs` JAR** with fixed coordinates/version.
12. **Configure consumer Stub Runner** and supply the sender adapter to the test context/JUnit extension.
13. **Trigger by label** and assert the real listener handled the event.
14. **Isolate CI test namespaces**, timeouts, cleanup, and broker permissions; record artifact checksums/provenance.
15. **Review and document the adapter**: SDK, test modes, supported content types, header mappings, and known limitations.

**Start with a single destination and one JSON event**, then expand to multiple schemas/destinations, async retries, DLQs, binary serializers, and parallel execution as needed. Avoid building a generic broker framework before proving a single contract end-to-end from producer to consumer.

## 25. Hands-On Exercise: Integrating Unsupported AsterBus

This exercise uses the **hypothetical AsterBus broker** with producer **Order Service** and consumer **Billing Service**. Learners can use the fake in unit tests and swap in the real SDK/broker where an environment is available.

1. **Write Groovy contract** `order_created_v1.groovy` with `label=orderCreatedV1`, `triggeredBy('publishOrderCreated()')`, `sentTo('orders.created')`, headers `eventType`/`schemaVersion`, and payload `orderId`/`amountMinor`/`currency`.
2. **Write an equivalent YAML contract to compare**, keeping only one active DSL per generation run.
3. **Define `TestBusPort`** with `publish(destination, envelope)` and `receive(destination, timeout)`.
4. **Create an in-memory fake port**, one queue per destination; test publish/receive preserving bytes and headers.
5. **Implement the `MessageVerifierSender`/`MessageVerifierReceiver` adapter**, separating object/String/byte[] paths without swallowing serializer errors.
6. **Register the adapter in the Spring Test context** via `@TestConfiguration`; verify bean types/versions and avoid duplicate auto-configured verifiers.
7. **Create `OrderMessagingContractBase`** with `@AutoConfigureMessageVerifier`; `publishOrderCreated()` invokes the real application publisher.
8. **Run generated producer verification**, confirming the test receives the message at the right destination and asserts payload/headers.
9. **Break a header** like `eventType` or turn `amountMinor` into a String, ensuring the test FAILS; revert afterward.
10. **Swap the fake for the AsterBus test broker SDK port** if available; verify real publisher, byte serialization, header mapping, and broker delivery.
11. **Add an inbound contract** for `ReserveInventory` using `messageFrom` and assert domain side effects after the sender adapter pushes input.
12. **Package the producer `stubs` artifact** with an explicit version; inspect the JAR to confirm labels/contracts exist.
13. **In Billing**, configure Stub Runner and the custom sender, trigger `orderCreatedV1`, and assert the listener updates order status.
14. **Simulate timeouts and stale messages**, proving the receiver never fabricates payloads or consumes events from the wrong run.
15. **Run two tests/destinations in parallel** and observe topic/queue/consumer-group isolation.
16. **Build CI gates**: conformance tests → producer verification → broker integration tests per policy → publish stubs → consumer Stub Runner tests.
17. **Record results** with Git SHA, adapter version, Spring Cloud Contract version, broker test mode, stub checksum, and test reports.

**Passing criteria:** generated producer tests PASS only when **the producer application actually emits a contract-compliant message**; the adapter honors destinations/payloads/headers and timeouts; consumer Stub Runner triggers the **real listener** through the adapter; contract-breaking mutations FAIL while valid dynamic metadata causes no false failures; reports clearly distinguish **fake tests** from **real broker integration tests**.

## 26. Self-Check Questions

1. When should you leverage Spring Cloud Stream/JMS/Camel integrations instead of writing a custom adapter?
2. How do the responsibilities of `MessageVerifierSender` and `MessageVerifierReceiver` differ?
3. Why is a custom `TestBusPort` not a built-in Spring Cloud Contract SPI?
4. How do `triggeredBy(...)` and `messageFrom(...)` differ in test direction?
5. Why must `publishOrderCreated()` call the real application publisher rather than pushing a static payload onto a queue?
6. Should `outputMessage.sentTo(...)` represent a logical name or a CI runner's physical topic name?
7. When mapping destinations, why are allowlists/namespaces needed to avoid publishing to production?
8. Why should you avoid copying all Spring `MessageHeaders` to the broker?
9. When is converting a payload to a UTF-8 String unsafe?
10. How can `schemaVersion=1` as an Integer differ from `"1"` as a String?
11. If the receiver sees no message within the timeout, what should happen so tests do not false-pass?
12. Why do fixed sleeps often make messaging CI flaky?
13. When a Spring Cloud Stream auto-configured verifier is already present, what error can adding a custom sender/receiver cause?
14. Where is `@AutoConfigureMessageVerifier` needed in producer messaging test setup?
15. What does Stub Runner triggering by label do, and why is a sender adapter required?
16. Does Stub Runner successfully sending a message prove the consumer handles business logic properly?
17. What can an in-memory fake queue test—and what can it not test—about a broker?
18. Why are integration tests on the SDK/codec/broker essential when transports use Avro/Protobuf or custom headers?
19. In parallel CI runs, how do topics, consumer groups, and offsets affect tests?
20. Why must `stubs` artifacts carry versions/checksums alongside producer verification reports?
21. When should an adapter fail fast instead of normalizing data to “fit the contract”?
22. Which mutations prove the adapter does not hide breaking changes?

## 27. Further Reading and Version Upgrade Guidelines

- **Spring Cloud Contract — Messaging:** https://docs.spring.io/spring-cloud-contract/reference/project-features-messaging.html
- **Spring Cloud Contract 4.1 — Messaging:** https://docs.spring.io/spring-cloud-contract/reference/4.1/project-features-messaging.html
- **Stub Runner Core / Messaging Stubs:** https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-core.html
- **Stub Runner JUnit Extension with Messaging:** https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-junit.html
- **Spring Cloud Contract — YAML Schema:** https://docs.spring.io/spring-cloud-contract/reference/yml-schema.html

When upgrading Spring Cloud Contract, re-verify **sender/receiver SPI signatures**, auto-configuration, generated test imports, Stub Runner builder APIs, codec/header behavior, and Spring Boot/BOM compatibility. Package, annotation, and `YamlContract` examples in this lesson depict **one common integration style**, not an immutable API across all versions.

**Remember:** **A custom messaging adapter bridges contracts and messaging transports—it is not a place to “manufacture green test results”.** Keep Groovy/YAML DSL describing exact destinations, headers, payloads, and semantics; implement `MessageVerifierSender`/`MessageVerifierReceiver` over a controlled port; use generated producer tests to verify **real publisher/listener code**, Stub Runner to test **real consumer code**, and add integration tests whenever you must prove codecs, broker routing, acks/retries, or schema registries. Enforce environment isolation, finite timeouts, zero production publishing, and proper `stubs` artifact/version/CI evidence. That way, Spring Cloud Contract still protects producer–consumer compatibility even when your team's messaging platform lacks a built-in adapter.
