# Messaging Contracts and Data for Stub Runner

In **Spring Cloud Contract**, an HTTP contract typically produces a **WireMock mapping** so the consumer can simulate REST calls. With **messaging**, the story is different: the producer emits a message to a destination, and the consumer receives the message via a broker or integration channel. A **messaging stub** is not simply an HTTP endpoint returning JSON. **Stub Runner** must be able to read the contract data, know **which scenario to trigger**, **where the message will be sent**, what **headers** and **sample payload** to emit, and have a **messaging adapter** wired into the test infrastructure.

This lesson belongs to the **Stub Generation and Packaging** chapter of the **SPRING_CLOUD_CONTRACT** module. The module teaches how to write producer–consumer contracts in **Groovy/YAML DSL**, generate **producer verification tests**, build and publish **stubs** artifacts, use **Stub Runner**, and integrate the whole workflow into CI to detect incompatible communication changes. The focus here is on the **messaging content packaged inside the stub artifact** and how consumers use that content, rather than solely how to define messages in the DSL.

After this lesson, you will be able to distinguish messaging contracts from HTTP mappings, organize an event with a clear `label`/destination/payload/headers, build a producer verification → `stubs` packaging → Stub Runner consumer test workflow, and diagnose cases where the artifact downloads cleanly yet the consumer **does not receive the message**.

## 1. How do messaging stubs differ from HTTP stubs?

Suppose we have **Order Service** (producer) and **Billing Service** (consumer). After an order is created successfully, Order Service publishes an `OrderCreated` event to destination `orders.created`. Billing listens for the event and generates an invoice.

~~~mermaid
flowchart TD
    A["Order Service: create order"] --> B["Publish OrderCreated"]
    B --> C["orders.created on broker/binder"]
    C --> D["Billing Service receives and processes"]
    E["Messaging Contract"] --> F["Generated producer test"]
    F --> B
    E --> G["Stub artifact containing contract data"]
    G --> H["Stub Runner + messaging adapter"]
    H --> C
~~~

The two testing modes must be understood separately:

| Aspect | HTTP stub | Messaging stub |
| --- | --- | --- |
| Simulated interaction | Consumer sends an HTTP request; stub returns status/headers/body. | Consumer receives a sample message; test triggers and observes the message via a messaging channel. |
| Core data | Method, URL, request matcher, and response. | `label`, destination, headers, payload, and input/trigger conditions. |
| Typical simulation tool | WireMock HTTP server. | Stub Runner combined with an appropriate messaging adapter/integration. |
| HTTP port | May require a port, e.g., 8089. | Does not require an HTTP port just to emit messages; requires a configured channel/binder. |
| What consumer tests verify | Client sends requests and handles HTTP responses. | Listener/deserializer/business handler receives and processes events. |
| What it does not prove alone | Real producer returned the right HTTP response if verification was skipped. | Real producer published properly, or broker guarantees delivery/retry/ordering without verification/integration tests. |

**Key point:** an artifact can contain **messaging contracts with zero WireMock mappings for those scenarios**. That is not necessarily a packaging error. Check the **messaging contract files and Stub Runner's ability to read/trigger them**, rather than merely counting JSON files in the `mappings` folder.

## 2. Separating contract data from test setup

A producer event has these components:

| Component | Example | Role |
| --- | --- | --- |
| `label` | `orderCreatedV1` | Scenario identifier so Stub Runner can trigger the message stub. |
| `input` | `triggeredBy('publishOrderCreated()')` | States how the generated producer test triggers the producer to emit the message. |
| `sentTo` | `orders.created` | Logical destination where the output message must be sent/observed. |
| `headers` | `contentType=application/json`, `eventType=OrderCreated` | Metadata the consumer may use to route/parse the event. |
| `body` | JSON with `eventId`, `orderId`, `amountMinor` | Sample payload the consumer handles and the producer must satisfy. |
| `matchers`, if any | `eventId` conforms to a specified format | Allows dynamically generated producer values while preserving key constraints. |

Beyond the contract, **test setup** requires:

- On the **producer**: a method or input message to trigger behavior, fixtures, message-sending service, output capture channel, and Contract Verifier messaging configuration.
- On the **consumer**: a listener subscribed to the right destination, message converter, mechanism for Stub Runner to inject messages into a test binder/broker, and assertions on processing outcomes.
- In **CI**: producer build, versioned stub artifact, repository, download permissions, and test execution order.

**Do not embed transient environment details into payloads** just to make Stub Runner work: machine-specific broker addresses, real tokens, randomly generated topic names unknown to consumers, or real user data. Fixture data must be deterministic and not confused with environment infrastructure addresses.

## 3. Sample scenario: OrderCreated v1

Suppose both sides agree on an `OrderCreated` event carrying these fields:

~~~json
{
  "eventId": "evt-00042",
  "orderId": "ORD-1042",
  "amountMinor": 125000,
  "currency": "VND",
  "occurredAt": "2026-01-15T10:20:30Z"
}
~~~

The message carries metadata:

~~~text
destination: orders.created
contentType: application/json
eventType: OrderCreated
schemaVersion: 1
~~~

Business conventions:

1. `eventId` uniquely identifies an event and can support deduplication.
2. `orderId` identifies the order that Billing must invoice.
3. `amountMinor` is an integer in the **smallest currency unit defined by the system**, not an ambiguous floating-point number; `currency` clarifies the currency unit.
4. `occurredAt` is a UTC timestamp string in the agreed format.
5. `eventType` and `schemaVersion` are metadata **actually used by the consumer**; if the consumer does not use them, avoid adding meaningless assertions.

Values such as `evt-00042` and `ORD-1042` are **samples** for stable tests; they do not mean the production producer is allowed to emit the same `eventId` for every order. If the producer generates dynamic IDs, use an appropriate matcher for producer verification and a fixed value for the consumer stub.

## 4. Defining a messaging contract in Groovy DSL

Create a file at `src/test/resources/contracts/messages/order_created.groovy` in the **producer** repository:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    label 'orderCreatedV1'
    description 'Publish OrderCreated v1 to Billing when order is created successfully'

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
            orderId: 'ORD-1042',
            amountMinor: 125000,
            currency: 'VND',
            occurredAt: '2026-01-15T10:20:30Z'
        )
    }
}
~~~

**Meaning of each section during test and stub generation:**

- `label 'orderCreatedV1'`: scenario name allowing consumer tests to ask Stub Runner to **emit the sample event**. Give it a unique, meaningful name that stays stable across builds.
- `triggeredBy('publishOrderCreated()')`: the method call the **generated producer test** invokes to make the real producer emit the event. It is **not** a method name that consumer tests call.
- `sentTo('orders.created')`: the destination where the generated producer test expects the producer to send the message and where the messaging stub routes the sample payload; the adapter/binder must know how to map this destination.
- `headers`: metadata. Verify that headers are preserved and converted to the right types across the real messaging transport if the consumer relies on them.
- `body`: event data checked on the producer and used as the sample message for the consumer.

This example uses a **static payload** to highlight the data that gets packaged. When adding matchers for dynamic IDs/timestamps, keep **consumer sample values** and **producer matchers** consistent—do not use overly broad regexes or sample values outside the allowed domain.

### 4.1. When event IDs are generated dynamically by the producer

In Groovy DSL, you can separate the two perspectives in the **output message body** using `consumer(...)` and `producer(...)`. Illustrative variant for `eventId`:

~~~groovy
body(
    eventId: $(consumer('evt-00042'),
               producer(regex('evt-[0-9]{5}'))),
    orderId: 'ORD-1042',
    amountMinor: 125000,
    currency: 'VND',
    occurredAt: '2026-01-15T10:20:30Z'
)
~~~

From the **consumer stub** perspective, `evt-00042` is a concrete sample the test can observe. From the **producer verification** perspective, the regex validates the real ID against the published format without forcing the producer to emit the exact same ID in production. Confirm that your current Spring Cloud Contract version supports this matcher/serialization pattern on messaging and inspect the generated test code.

**Do not treat a regex as a uniqueness guarantee** for `eventId`. Non-duplication across emissions must be tested with appropriate business/integration tests.

## 5. YAML contract: same intent, verify schema by version

If your team uses **YAML DSL**, the same data can be expressed as:

~~~yaml
description: Publish OrderCreated v1 to Billing
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
    orderId: ORD-1042
    amountMinor: 125000
    currency: VND
    occurredAt: "2026-01-15T10:20:30Z"
~~~

**Note:** this shows **the intent of a messaging contract in YAML**; support, key names, and matcher syntax must be verified against the **Spring Cloud Contract version your project uses**. A parseable YAML document does not guarantee Contract Verifier will interpret it and generate stubs as expected. Run the plugin, inspect generated producer tests, and test triggering via Stub Runner.

Keep **only one active DSL** for the same event in a single build. Keeping both equivalent Groovy and YAML files in the path scanned by the plugin can generate duplicate tests/stubs or cause the two versions to drift out of sync.

## 6. Producer verification: how to prove the event was emitted?

Contract Verifier does not execute producer business logic from `outputMessage` alone. For a `triggeredBy` contract, the generated test must invoke the right method and **capture the actual message** emitted by the application.

Suppose Order Service uses **Spring Cloud Stream**. It may have a publisher:

~~~java
package com.acme.orders;

import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;
import org.springframework.util.MimeTypeUtils;

@Service
public class OrderEventPublisher {
    private final StreamBridge bridge;

    public OrderEventPublisher(StreamBridge bridge) {
        this.bridge = bridge;
    }

    public void publishOrderCreated() {
        Message<OrderCreated> message = MessageBuilder
            .withPayload(new OrderCreated(
                "evt-00042", "ORD-1042", 125000L,
                "VND", "2026-01-15T10:20:30Z"))
            .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.APPLICATION_JSON)
            .setHeader("eventType", "OrderCreated")
            .setHeader("schemaVersion", 1)
            .build();

        boolean accepted = bridge.send("ordersCreated-out-0", message);
        if (!accepted) {
            throw new IllegalStateException("Cannot publish OrderCreated");
        }
    }
}
~~~

This example assumes a Java record `OrderCreated` with `eventId`, `orderId`, `amountMinor`, `currency`, and `occurredAt`, along with compatible Spring Cloud Stream dependencies. `StreamBridge.send(...)` takes an in-app **binding name**, which is not necessarily the external broker topic/queue name.

Sample configuration mapping the binding to a destination:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        ordersCreated-out-0:
          destination: orders.created
          content-type: application/json
~~~

**Base test** class for the generated test to invoke the trigger:

~~~java
package com.acme.orders;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
public abstract class MessageContractTestBase {
    @Autowired
    private OrderEventPublisher publisher;

    public void publishOrderCreated() {
        publisher.publishOrderCreated();
    }
}
~~~

**Important:** this base test **only provides the trigger**; it is not a complete messaging verification setup. The project also needs a **MessageVerifier, test binder, or messaging adapter** so Contract Verifier can observe output messages, depending on your Spring Cloud Contract tools and version. Without an appropriate adapter, the generated test may fail to find any message even though the publisher method was called.

### 6.1. Tests must verify the right layer

A meaningful generated messaging producer test:

~~~text
1. Prepare fixtures for Order Service
2. Call publishOrderCreated() on the base test
3. Wait for the message on destination orders.created
4. Assert headers eventType, schemaVersion, contentType
5. Assert OrderCreated payload against the contract's body/matchers
~~~

This is a **flow description**, not verbatim Java code generated by the plugin. If the adapter intercepts the message **before serialization**, a green test does not prove the bytes sent to production Kafka/RabbitMQ match the wire format. When consumers depend on the wire schema, add real codec/transport tests.

## 7. Generating and packaging the stubs artifact

Once contracts are ready, the producer uses the Contract Verifier plugin to generate tests and stub resources. Example Maven plugin configuration (partial `pom.xml`):

~~~xml
<plugin>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-contract-maven-plugin</artifactId>
    <version>4.1.5</version>
    <extensions>true</extensions>
    <configuration>
        <testFramework>JUNIT5</testFramework>
        <baseClassForTests>com.acme.orders.MessageContractTestBase</baseClassForTests>
    </configuration>
</plugin>
~~~

`4.1.5` is **an example version from the 4.1.x line**, not a required version for every project; pick plugin/dependency versions matching the Spring Boot and Spring Cloud BOM/release train you use. The project needs Contract Verifier, Spring Boot Test, Spring Cloud Stream, and an appropriate messaging test adapter/binder. Never arbitrarily set `testMode=MOCKMVC` as a substitute for a message-capturing environment: HTTP test modes and messaging verification are completely different things.

On a properly configured Maven producer, a reference workflow is:

~~~shell
mvn clean verify
~~~

After confirming producer verification passes, build/install the artifact locally:

~~~shell
mvn install
~~~

In CI/release, after verification and other quality gates pass, publish the artifact to the chosen repository using the project's Maven deploy/publishing workflow:

~~~shell
mvn deploy
~~~

**Do not turn this sequence into a requirement to run builds three times in every CI job.** Depending on the lifecycle and pipeline, `install` or `deploy` may re-run test phases. What matters is that **generated producer tests run and pass before a stub is trusted**, not producing a JAR at any cost. Never pass `-DskipTests` in a release step meant to prove producer compliance.

### 7.1. Distinguishing the application JAR from the stub JAR

Typically a producer can generate:

~~~text
order-service-1.0.0.jar
order-service-1.0.0-stubs.jar
~~~

Maven coordinates for the stub:

~~~text
groupId    = com.acme
artifactId = order-service
version    = 1.0.0
classifier = stubs
~~~

Short form:

~~~text
com.acme:order-service:1.0.0:stubs
~~~

**The application JAR** holds runnable code for Order Service; **the stubs JAR** holds data for consumers to simulate communication. Stub Runner uses the **stub artifact**, eliminating the need to boot the entire producer application to run consumer message contract tests.

## 8. What resources are inside a messaging stub JAR?

Spring Cloud Contract typically places stub data under `META-INF` organized by group/artifact/version. An **illustrative** layout for `order-service-1.0.0-stubs.jar`:

~~~text
order-service-1.0.0-stubs.jar
└── META-INF/
    └── com.acme/
        └── order-service/
            └── 1.0.0/
                ├── contracts/
                │   └── messages/
                │       └── order_created.groovy
                └── mappings/
                    └── ... (if the module also has HTTP contracts)
~~~

**The actual layout can vary by version and packaging configuration**; inspect the generated JAR to be certain. Things worth checking:

1. **The right artifact** with the `stubs` classifier, matching the groupId, artifactId, and version requested by the consumer.
2. Presence of **messaging contracts** or the equivalent representation supported by Stub Runner; content was not excluded during packaging.
3. The contract defines **label** `orderCreatedV1` and the agreed destination/payload/headers.
4. If the module also has HTTP contracts, the JAR may contain **WireMock mappings** for HTTP. If it only has messaging contracts, **HTTP mappings do not need to exist**.
5. The artifact can be resolved in the consumer's `LOCAL`/`REMOTE` mode, rather than being an untracked `.jar` without proper coordinates.

A common mistake is checking `stubs.jar` solely by counting `mappings/*.json` files. For messaging, **counting 0 mappings does not prove messaging contracts are missing**. Check the contract resources and test **triggering** them in a consumer test with messaging integration.

### 8.1. What data does Stub Runner need to emit a message?

| Data | Included in contract | What Consumer/Stub Runner uses it for |
| --- | --- | --- |
| `label=orderCreatedV1` | Yes | Selects the specific scenario when the test requests emitting an event. |
| `outputMessage.sentTo=orders.created` | Yes | Indicates where the adapter must deliver the message. |
| `outputMessage.body` | Yes | Supplies the sample payload the consumer's listener will receive. |
| `outputMessage.headers` | Yes | Provides metadata for conversion/routing/assertions. |
| `input.triggeredBy` | Yes | Primarily used by **generated producer tests** to trigger behavior; not a stub REST URL. |
| Real broker hostname/port | Usually should **not** be hardcoded in contracts | Comes from the consumer's test binder/broker configuration. |
| Consumer listener/function | **No** | Provided by the consumer application and executed by tests. |
| Queue/test probe and timeout | **No** | Controlled by consumer test fixtures. |

Do not treat `triggeredBy` as a remote call to execute a producer method during consumer tests. Stub Runner **does not start the producer**; it uses the **packaged output message data** to emit a simulated message through the configured adapter.

## 9. LOCAL, REMOTE, and stub versioning

**LOCAL** fits when the producer has installed the artifact into local Maven and consumer tests run on the same machine/environment:

~~~java
@AutoConfigureStubRunner(
    ids = "com.acme:order-service:1.0.0:stubs",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
~~~

**REMOTE** fits consumer CI on separate machines/runners once the stub is published to a Maven repository:

~~~java
@AutoConfigureStubRunner(
    ids = "com.acme:order-service:1.0.0:stubs",
    stubsMode = StubRunnerProperties.StubsMode.REMOTE,
    repositoryRoot = "https://repo.example.org/maven-releases"
)
~~~

`https://repo.example.org/maven-releases` is an **illustrative placeholder URL**, not a real repository. In projects, configure the actual URL, read credentials/permissions, and store secrets securely in CI. You can externalize the repository URL via properties instead of hardcoding it.

**Why pin the version?** If the consumer uses a silently shifting stub version, the same consumer commit can pass today and fail tomorrow without any code changes. Pinning `1.0.0` or intentionally selecting a version keeps tests **reproducible** and traceable to a producer commit. If using snapshot versions, accept and manage mutable-artifact risks per CI policy.

For **messaging-only** stubs, the consumer does not necessarily supply an HTTP port in the `ids` string. What it needs is a connected **messaging adapter/binder** so events reach the listener. If the consumer also uses HTTP stubs from the same artifact, HTTP mappings can use a corresponding port.

## 10. Stub Runner on the consumer: using labels to emit events

In Billing Service, assume a Spring Cloud Stream consumer already receives `OrderCreated` from destination `orders.created`. The test needs **Stub Runner**, an appropriate **message adapter**, and a mechanism to await the listener's output.

An illustrative JUnit 5 test:

~~~java
package com.acme.billing;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.StubTrigger;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.acme:order-service:1.0.0:stubs",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class BillingMessageContractTest {
    @Autowired
    private StubTrigger stubTrigger;

    @Autowired
    private BillingEventProbe probe;

    @Test
    void consumesOrderCreatedV1() {
        stubTrigger.trigger("orderCreatedV1");

        BillingOrderCreated received =
            probe.awaitEvent("evt-00042");

        assertThat(received.orderId()).isEqualTo("ORD-1042");
        assertThat(received.amountMinor()).isEqualTo(125000L);
        assertThat(received.currency()).isEqualTo("VND");
    }
}
~~~

This is an **illustrative test skeleton**, not a standalone runnable class: `BillingEventProbe`, `BillingOrderCreated`, and `awaitEvent` must be implemented by the consumer; it also requires Stub Runner dependencies, Spring Cloud Stream messaging integration, an appropriate binder/test broker, and test setup containing the listener.

Calling `stubTrigger.trigger(...)` **does not by itself guarantee** the listener received it. You must configure the adapter so Stub Runner **sends to the exact destination Billing subscribes to**, and assert **observable side effects**. `awaitEvent` must have a **bounded timeout** to avoid hanging tests when a binder/label is wrong.

### 10.1. A minimal listener and probe

Suppose a converter on the consumer side maps the JSON event into a record:

~~~java
package com.acme.billing;

public record BillingOrderCreated(
    String eventId,
    String orderId,
    long amountMinor,
    String currency,
    String occurredAt
) {}
~~~

A test probe can use a `BlockingQueue` to record events:

~~~java
package com.acme.billing;

import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

import org.springframework.stereotype.Component;

@Component
public class BillingEventProbe {
    private final BlockingQueue<BillingOrderCreated> events =
        new LinkedBlockingQueue<>();

    public void accept(BillingOrderCreated event) {
        events.offer(event);
    }

    public BillingOrderCreated awaitEvent(String eventId) {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(3);
        while (System.nanoTime() < deadline) {
            BillingOrderCreated event;
            try {
                event = events.poll(100, TimeUnit.MILLISECONDS);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException("Interrupted", e);
            }
            if (event != null && event.eventId().equals(eventId)) {
                return event;
            }
        }
        throw new AssertionError("No OrderCreated event: " + eventId);
    }
}
~~~

A Spring Cloud Stream functional consumer can connect to the probe:

~~~java
@Configuration
class BillingConsumerConfig {
    @Bean
    Consumer<BillingOrderCreated> orderCreatedConsumer(
            BillingEventProbe probe) {
        return probe::accept;
    }
}
~~~

Consumer binding configuration:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orderCreatedConsumer-in-0:
          destination: orders.created
          content-type: application/json
~~~

**Scope of this example:** this illustrates the **destination → converter → listener → probe** flow; with the Spring Cloud Stream functional model, projects may need function-definition configuration so the binder identifies the consumer properly. Some binders/test adapters pass `Message<T>` rather than converting straight to a DTO; align the function signature and converter accordingly. Never ship a test-only `BillingEventProbe` in production services if its sole purpose is collecting test events.

## 11. If the trigger never reaches the listener, what should you check?

A consumer test might resolve the stub artifact and obtain a `StubTrigger` bean, yet the listener still never receives the event. Trace along the path:

~~~mermaid
flowchart TD
    A["Did consumer download the right stubs artifact?"] --> B["Do the messaging contract and label exist?"]
    B --> C["Is Stub Runner messaging adapter enabled and ready?"]
    C --> D["Is the contract destination mapped properly?"]
    D --> E["Did binder/test broker deliver message to consumer?"]
    E --> F["Did deserializer understand payload/contentType?"]
    F --> G["Did listener execute business logic?"]
    G --> H["Did probe/assertion observe the right event?"]
~~~

| Symptom | Likely cause to check | Investigation path |
| --- | --- | --- |
| Stub artifact not found. | Wrong group/artifact/version/classifier, not installed/published, unreachable repo. | Compare `ids` against JAR coordinates and repository. |
| Cannot trigger `orderCreatedV1`. | Contract missing from package, missing/duplicate label, or Stub Runner cannot parse contract format. | Open JAR and inspect contract, label, and Stub Runner startup logs. |
| Trigger succeeds but message never arrives. | Missing messaging integration or binder/test broker; destination mismatch. | Check adapter, `sentTo` mapping, and binding/listener config. |
| Message arrives but DTO is null/wrong. | Mismatched `Content-Type`, converter, or field naming/serialization. | Inspect raw payload, headers, and deserializer config. |
| Flaky test failures. | Async listener processing, short timeout, leftover messages in queue. | Use distinct `eventId`s, clean fixtures, deadline-based awaits, never `sleep`. |
| Consumer receives two events. | Duplicate trigger or leftover event from an earlier test. | Isolate queues/destinations, reset probe, verify idempotency. |

Never edit a contract to drop important headers/fields just because a test adapter was misconfigured. Distinguish **packaging** errors, **wiring** errors, **serialization** errors, and **consumer business logic** errors.

## 12. Input message followed by output message

Not every messaging contract is triggered by a method on the base test. A producer can **receive an input message** and then **emit an output message**:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    label 'invoiceRequestHandled'

    input {
        messageFrom('billing.invoice.request')
        messageBody(orderId: 'ORD-1042')
        messageHeaders {
            header('contentType', 'application/json')
        }
    }

    outputMessage {
        sentTo('billing.invoice.created')
        headers {
            header('contentType', 'application/json')
        }
        body(
            orderId: 'ORD-1042',
            invoiceStatus: 'CREATED'
        )
    }
}
~~~

Differences from `triggeredBy`:

- In producer tests, you must **inject a valid input message** into the channel the application listens on, then observe the output.
- In consumer stub tests, you must understand **stub behavior on receiving an input message** and how your adapter links input to output.
- Do not assume `StubTrigger.trigger(label)` simulates a full production broker round-trip by itself; simulation capabilities depend on the integration and version.

For complex scenarios (request–reply messaging, transactional outbox, retries, dead-letter queues), add integration tests. Stub contracts describe selected communication cases; they do not automatically simulate full broker delivery semantics.

## 13. Sample data, matchers, and consumer compatibility

A good stub payload must be **specific enough for consumer tests to verify handler logic**, yet **not silently turn a sample into the only valid value**.

| Field | Stub sample | Constraint possibly needed on producer | Risk if sample-only |
| --- | --- | --- | --- |
| `eventId` | `evt-00042` | Format, non-empty; unique per system policy. | Producer could always emit the same ID without single-message tests catching it. |
| `orderId` | `ORD-1042` | Schema-compliant ID matching a real created order. | Consumer test does not prove the order exists. |
| `amountMinor` | `125000` | Integer, allowed range, explicit currency unit. | Scale errors or boundary overflows go unnoticed. |
| `currency` | `VND` | Set of supported currency codes. | Fails to test other currencies if the API permits multiple. |
| `occurredAt` | `2026-01-15T10:20:30Z` | ISO timestamp per contract; explicit timezone/precision. | Consumer might break on different offsets or precision. |
| `schemaVersion` | `1` | Versioning/decoding rules. | Consumer might fail to handle v2. |

In an **output message**, producer verification can use matchers to validate dynamic values, while consumer stubs receive **static sample** values. That fits well because Stub Runner primarily **simulates the promise** rather than running ID generation algorithms. Still, if the contract body uses the wrong JSON type, consumer tests can fail in the converter—or worse, accept data that diverges from production.

### 13.1. Missing vs. null in payloads

These two shapes:

~~~json
{"orderId":"ORD-1042","note":null}
~~~

~~~json
{"orderId":"ORD-1042"}
~~~

are **not equivalent** when a consumer distinguishes "clear the note" from "do not send a note". If the producer converter is configured to strip null values, the wire payload may no longer match the contract. A messaging test inspecting objects before serialization can miss that discrepancy; add **serializer/transport tests** when field presence matters to consumers.

### 13.2. Headers are contract data too

Especially in messaging, consumers may route by `eventType` or use `schemaVersion` to pick a decoder. A message with a valid body yet missing a header might never reach the right handler.

With Spring Cloud Stream/Kafka/RabbitMQ, header types and values can undergo conversion. When a header is part of the contract, verify:

1. Is the header created before publishing?
2. Does the binder/serializer preserve and send the header properly?
3. Can the consumer adapter read the expected type?
4. Does Stub Runner emit the same metadata per the contract?

Do not assume every `MessageHeaders` entry appears verbatim as a JSON field. Payload body and transport metadata are two distinct information channels.

## 14. Messaging stubs do not replace broker integration tests

A check via Stub Runner verifies that the consumer **can process sample events** and that listeners/wiring work in the test environment. It does not prove every operational property:

- **Delivery semantics:** at-most-once, at-least-once, retries, and duplicate delivery.
- **Ordering:** cross-event ordering, partitioning/keys, and concurrency.
- **Transactions/outbox:** whether database state and message publishing stay consistent on failures.
- **Serialization/native encoding:** JSON, Avro, Protobuf, schema registry, and actual bytes on the wire.
- **DLQ/retry topology:** broker routing, dead-letter policies, and consumer acknowledgements.
- **Security:** broker credentials, ACLs, TLS, and publish/subscribe permissions.
- **Performance:** throughput, latency, backpressure, and resource usage.

If these are product requirements, add **integration tests with an appropriate binder/broker** (such as Testcontainers for Kafka/RabbitMQ when used by the project) alongside operational measurements. Never expect Stub Runner to replace a full production broker.

## 15. CI workflow: from producer contract to independent consumer

~~~mermaid
flowchart TD
    A["PR edits message contract or producer"] --> B["Review payload/headers/destination/label"]
    B --> C["Generate & run producer messaging tests"]
    C --> D["Check serialization/adapter if needed"]
    D --> E{"Producer verification passed?"}
    E -->|No| F["Block artifact publishing"]
    E -->|Yes| G["Package JAR with stubs classifier"]
    G --> H["Verify contracts and metadata inside JAR"]
    H --> I["Publish version to Maven repository"]
    I --> J["Consumer CI fetches stubs via Stub Runner"]
    J --> K["Trigger label + listener assertions"]
    K --> L["Verify old consumer remains compatible"]
~~~

Critical CI rules:

1. **Never publish a stub unverified by the producer.** Successful packaging does not guarantee generated producer tests ran.
2. **Tie artifacts to commits and versions** for traceability back to the exact source contracts that produced them.
3. **Inspect JAR contents**, not merely whether the JAR exists. For messaging, specifically check `contracts`/`label`/destination and triggerability.
4. **Never rely on a shared local Maven repository across two independent CI jobs.** Producer publishes `stubs`; consumer fetches through an appropriate repository.
5. **Pin artifact versions** or select versions intentionally, avoiding mutable builds that unexpectedly alter payloads.
6. **Verify both producer and consumer branches.** Producer tests ensure emission conforms to the contract; consumer tests ensure listeners handle it per the contract.
7. **Maintain supported contracts** or plan versioning/migration before deleting fields, renaming topics, changing enums, altering headers, or narrowing value ranges.

### 15.1. Reviewing potentially breaking changes

| Change | Example | Potential impact |
| --- | --- | --- |
| Rename destination | `orders.created` → `orders.v2` | Old listeners stop receiving events. |
| Remove or rename header | `eventType=OrderCreated` removed | Consumers misroute or fail deserialization. |
| Rename field | `amountMinor` → `totalAmount` | Consumer DTO fails to read the value. |
| Change data type | Number → String | Old consumers fail parsing or misinterpret values. |
| Change enum | `CREATED` → `NEW` | Handler fails to recognize the state. |
| Remove required field | Delete `orderId` | Consumer loses the key linking the invoice. |
| Change semantics | `amountMinor` changed from minor units to major units | Consumer miscalculates money despite a similar schema. |
| Remove test label | `orderCreatedV1` removed | Consumer CI fails to trigger old stubs; requires planned transition. |

**Labels** form the interface for stub/test scenarios, so they also need stability in consumer verification workflows. Still, changing a label by itself is not necessarily a production protocol change; separate **broker event compatibility** from **tooling/test compatibility** when assessing impact.

## 16. Common errors and diagnostic rules

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Only empty `mappings` found in JAR. | Module has messaging contracts only, no HTTP contracts. | Inspect messaging contracts, labels, and try triggering; do not infer failure from HTTP mapping counts. |
| `StubTrigger` fails to trigger label. | Contract missing from artifact, wrong label name, wrong artifact/version. | Open the actual JAR and compare labels against `ids`. |
| Trigger succeeds yet probe times out. | Adapter not wired to right binder/destination; listener not subscribed. | Check Spring Cloud Stream bindings, integration setup, and logs. |
| Consumer fails to parse event. | `Content-Type`, `schemaVersion`, converter, or field type mismatch. | Capture payload/headers at consumer and compare against contract. |
| Producer test finds no message. | `triggeredBy` calls wrong method or `MessageVerifier` unconfigured. | Check generated test/base test, test binder, and output capture channel. |
| Producer test passes yet production emits wrong bytes. | Test inspects message pre-serialization; production binder differs. | Add serialization/transport integration tests. |
| Consumer CI cannot download stub. | Wrong repository, missing classifier, unpublished version, missing read permissions. | Check Maven coordinates and `LOCAL`/`REMOTE` mode. |
| Tests flake when running in parallel. | Shared queue, label, `eventId`, or stale events left in probe. | Reset/isolate fixtures, use deadlines, avoid shared state. |
| Stub emits message yet consumer ignores it. | Listener not registered or wrong function binding. | Inspect function definition and destination. |
| Consumer test passes while real producer changes payload. | Producer verification not enforced before publish. | Configure CI to block publishing and run backward-compatibility checks. |

When debugging, trace in order: **stub coordinates → JAR contents → label → messaging adapter → destination/binder → converter → listener → assertion**. In parallel, check the producer side: **trigger → producer publish → MessageVerifier → generated assertions**. Both paths meet at **the contract**, not by sharing a live producer process.

## 17. Lab: packaging and triggering OrderCreated

Practice on a Spring Boot/Spring Cloud Stream producer configured with Spring Cloud Contract Verifier and a consumer using Stub Runner:

1. **Define the contract** for `OrderCreatedV1` with `label=orderCreatedV1`, `sentTo=orders.created`, headers, and payload from section 3.
2. **Write the Groovy messaging contract** per section 4 and place it in the producer's contracts folder.
3. **Implement the producer publisher** via `StreamBridge`, configuring bindings to point to `orders.created`.
4. **Create the base test** exposing `publishOrderCreated()` and configure the messaging adapter/test binder so generated tests capture the event.
5. **Run producer verification**; verify tests are actually generated, executed, and pass body/header/destination assertions.
6. **Introduce an intentional fault:** change `currency` to `USD` or `orderId` to an invalid contract value, re-run to confirm the producer test FAILS, then revert.
7. **Package/install the `stubs` artifact** after producer verification passes; open the JAR and verify contract, label, destination, and body.
8. **Test the consumer with Stub Runner `LOCAL`**, trigger `orderCreatedV1`, and verify the Billing listener receives the event and records/executes the expected business side effect.
9. **Test broken wiring:** change the consumer's destination and observe probe timeout; restore and confirm PASS.
10. **Run in CI across two independent machines/runners:** producer publishes `stubs` artifact to repository; consumer fetches via `REMOTE` and passes the same test without starting Order Service.
11. **Simulate a breaking change:** drop `orderId` or change `eventType`; identify affected consumers and plan compatibility/versioning.

**Completion criteria:** a **stub artifact with accurate coordinates**, containing **a message contract recognized by Stub Runner**, producer tests verifying the publisher, consumer tests triggering the exact **label** and receiving **payload/headers via adapter**, and a pipeline blocking publishing when the producer violates the contract.

## 18. Self-check questions

1. Why might a JAR with only messaging contracts contain zero WireMock HTTP mappings?
2. How does `label 'orderCreatedV1'` differ from `sentTo('orders.created')`?
3. Is `triggeredBy('publishOrderCreated()')` used by the producer branch or the consumer Stub Runner?
4. What is needed for `stubTrigger.trigger("orderCreatedV1")` to actually deliver a message to the Billing listener?
5. Why does successfully downloading the `stubs` artifact not prove the messaging adapter is configured properly?
6. Why might a generated producer test checking Spring `Message` before serialization miss byte/header bugs on the broker?
7. When should you pick Stub Runner `LOCAL` vs. `REMOTE`, and why pin versions?
8. Why is a WireMock no-match HTTP 404 unrelated to a listener failing to receive a messaging event?
9. If you change the destination while keeping the payload unchanged, can that still be a breaking change?
10. Why are both producer verification and consumer Stub Runner tests required before declaring an event version compatible?

**Remember:** **A messaging stub is contract data that Stub Runner can trigger and route through a messaging adapter—not a live producer or an HTTP WireMock endpoint**. Clearly define **label, destination, headers, and sample payload**, verify the producer emits the right event, package the proper **`stubs` classifier** artifact, inspect JAR contents, and configure binders so consumers receive messages. When CI enforces passing producer verification before publishing and consumers test with Stub Runner against pinned versions, inter-service communication changes are caught early without booting the entire system.
