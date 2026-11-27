# Testing Splitter and Aggregator by Correlation

## 1. Problem and Objectives

In **Enterprise Integration Patterns (EIP)**, a **Splitter** divides one message into multiple child messages; an **Aggregator** collects related messages and emits a result once a group satisfies its completion condition. These two patterns often appear together in Spring Integration, though not necessarily adjacent: Transformers, Filters, Routers, Service Activators, or asynchronous processing may sit between them.

The challenge is not just verifying message counts. When two requests are processed concurrently, the Aggregator must know **which messages belong to the same request**. Without correlation tests, a flow may work for a single order yet mix data together when receiving multiple interleaved orders.

This lesson belongs to the **Pattern Testing** chapter of the **SPRING_INTEGRATION_PATTERN** module. The module aims to build loosely coupled, extensible message flows using Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation, while testing and tracing message paths. Here, we focus on **proving that data is split accurately, grouped accurately, merged accurately, and emitted at the right time**.

After this lesson, you will be able to:

1. Identify the payload and headers to check when a Splitter creates child messages.
2. Verify \`correlationId\`, \`sequenceNumber\`, and \`sequenceSize\` against the flow's contract.
3. Prove that an Aggregator waits for all messages before emitting a result.
4. Use two interleaved groups to detect cross-group mixing bugs.
5. Write flow tests with JUnit 5, Spring Integration Java DSL, and in-memory channels.
6. Design additional tests for missing, duplicate, out-of-order, timed-out, and retried messages.

## 2. What Is Correlation in a Splitter → Aggregator Flow?

Suppose request \`R-A\` has two order lines \`["A1", "A2"]\`. The Splitter creates two messages; both must be recognized as members of the same group. Request \`R-B\` also has two order lines \`["B1", "B2"]\`, but belongs to a **different group**.

~~~mermaid
flowchart TD
    A["Request A: [A1, A2]"] --> SA["Splitter A"]
    B["Request B: [B1, B2]"] --> SB["Splitter B"]
    SA --> A1["A1 / correlation=A / seq=1/2"]
    SA --> A2["A2 / correlation=A / seq=2/2"]
    SB --> B1["B1 / correlation=B / seq=1/2"]
    SB --> B2["B2 / correlation=B / seq=2/2"]
    A1 --> AGG["Aggregator"]
    B1 --> AGG
    B2 --> AGG
    A2 --> AGG
    AGG --> OA["Result A: [A1, A2]"]
    AGG --> OB["Result B: [B1, B2]"]
~~~

In Spring Integration, the relevant headers are commonly accessed via \`IntegrationMessageHeaderAccessor\`:

| Header | Meaning in Example | Useful Assertion |
| --- | --- | --- |
| \`correlationId\` | Key identifying a group | Elements of the same group share the same key; different groups have different keys |
| \`sequenceNumber\` | Position of the element in the group, typically starting at 1 | For a two-element group, both positions 1 and 2 are present |
| \`sequenceSize\` | Expected number of elements in the group | Both child messages carry value 2 |
| \`requestId\` | Business tracking key set by the application | Preserved if required by the flow, not implicitly substituted for correlation |
| \`id\`, \`timestamp\` | Framework-managed metadata | Check only when truly needed; avoid fixed UUID/timestamp values |

**Do not conflate correlation with sequence.** \`correlationId\` answers *which group?*; \`sequenceNumber\` answers *at what position?*; \`sequenceSize\` answers *how many elements are expected?*. If two messages both have \`sequenceNumber=1\` but different correlations, they can still belong to two separate valid groups.

A standard Splitter generates sequence headers when sequence application is enabled. When a Splitter creates a group from an input message, correlation is typically derived from the source message's identity. However, **do not hardcode a specific correlation ID** in tests if the code does not assign one explicitly; what must be proven is consistency across messages in the same group.

## 3. Defining the Contracts to Test

Before writing Java code, describe each boundary:

~~~text
Request:
  payload   = ["A1", "A2"]
  requestId = "r-A"

After Splitter:
  message #1: payload="A1", correlation=G, sequenceNumber=1, sequenceSize=2
  message #2: payload="A2", correlation=G, sequenceNumber=2, sequenceSize=2

At Aggregator:
  received #1/2 -> no output yet
  received #2/2 -> one output containing ["A1", "A2"]
~~~

| Scenario | Minimal Input | What Must Be Proven |
| --- | --- | --- |
| Basic Splitter | One list with two elements | Two outputs, exact payloads, full sequence metadata |
| Preserve business metadata | One list and \`requestId\` | Both child messages retain \`requestId\` if required by contract |
| Aggregator waits for full group | Two messages with same correlation, size 2 | No output after receiving only one message |
| Aggregator completes group | Second message of the group | One result emitted, no extra emissions |
| Correlation isolation | Group A (two items), Group B (two items) | No mixing of A and B when sent interleaved |
| Full pipeline check | One list message passing Splitter then Aggregator | One result with all payloads, none missing or duplicated |
| Wrong correlation | One item carrying a different correlation | Not counted toward the incomplete group |
| Error or missing element | One group receives only the first item | Timeout, group retention, or partial-result policy is clear |

**The minimal message count depends on the test objective.** Two elements suffice to prove basic split/aggregate behavior; **four messages across two distinct correlations** are required to expose group-mixing bugs.

## 4. Setting Up the Flow Test Environment

The examples use **Java 17, JUnit 5, AssertJ, and Spring Integration Java DSL 6.x**. They use default \`DirectChannel\` and \`QueueChannel\` instances as observable outputs, so no Kafka, RabbitMQ, HTTP server, or database is required.

For a Spring Boot project, compatible dependencies can be used:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-integration</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

To pinpoint errors easily, create **three independent flows in the same context**:

~~~mermaid
flowchart LR
    S1["split.in"] --> S2["Splitter"] --> S3["split.out"]
    A1["aggregate.in"] --> A2["Aggregator"] --> A3["aggregate.out"]
    E1["roundtrip.in"] --> E2["Splitter"] --> E3["Aggregator"] --> E4["roundtrip.out"]
~~~

- The first flow lets you inspect **payloads and sequence headers directly after the Splitter**.
- The second flow lets you send **messages with explicit correlations** to test the Aggregator.
- The third flow tests the **Splitter → Aggregator interaction** as a complete pipeline.

This is a way to organize the test suite, not a requirement to duplicate three flows in production.

## 5. Complete Java Example: Three Test Groups

Create the file \`src/test/java/example/SplitAggregateCorrelationTest.java\`:

~~~java
package example;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(SplitAggregateCorrelationTest.Flows.class)
class SplitAggregateCorrelationTest {

    @Autowired
    ApplicationContext context;

    private MessageChannel input(String name) {
        return context.getBean(name, MessageChannel.class);
    }

    private QueueChannel output(String name) {
        return context.getBean(name, QueueChannel.class);
    }

    private Message<?> receive(String name) {
        Message<?> result = output(name).receive(1_000);
        assertThat(result)
                .as("Expected a message on channel %s", name)
                .isNotNull();
        return result;
    }

    private static Message<String> part(
            String groupId, int position, int size, String payload) {
        return MessageBuilder.withPayload(payload)
                .setHeader(
                        IntegrationMessageHeaderAccessor.CORRELATION_ID,
                        groupId)
                .setHeader(
                        IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER,
                        position)
                .setHeader(
                        IntegrationMessageHeaderAccessor.SEQUENCE_SIZE,
                        size)
                .build();
    }

    private static List<String> items(Message<?> aggregated) {
        assertThat(aggregated.getPayload()).isInstanceOf(List.class);
        return ((List<?>) aggregated.getPayload()).stream()
                .map(String.class::cast)
                .toList();
    }

    @Test
    void splitter_produces_two_correlated_messages() {
        Message<List<String>> request = MessageBuilder
                .withPayload(List.of("A1", "A2"))
                .setHeader("requestId", "r-A")
                .build();

        assertThat(input("split.in").send(request)).isTrue();

        Message<?> first = receive("split.out");
        Message<?> second = receive("split.out");

        assertThat(List.of(first.getPayload(), second.getPayload()))
                .containsExactlyInAnyOrder("A1", "A2");
        assertThat(first.getHeaders().get("requestId")).isEqualTo("r-A");
        assertThat(second.getHeaders().get("requestId")).isEqualTo("r-A");

        Object correlation = first.getHeaders().get(
                IntegrationMessageHeaderAccessor.CORRELATION_ID);
        assertThat(correlation).isNotNull();
        assertThat(second.getHeaders().get(
                IntegrationMessageHeaderAccessor.CORRELATION_ID))
                .isEqualTo(correlation);

        assertThat(List.of(
                first.getHeaders().get(
                        IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER),
                second.getHeaders().get(
                        IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER)))
                .containsExactlyInAnyOrder(1, 2);
        assertThat(first.getHeaders().get(
                IntegrationMessageHeaderAccessor.SEQUENCE_SIZE)).isEqualTo(2);
        assertThat(second.getHeaders().get(
                IntegrationMessageHeaderAccessor.SEQUENCE_SIZE)).isEqualTo(2);

        assertThat(output("split.out").receive(0)).isNull();
    }

    @Test
    void aggregator_waits_until_group_is_complete() {
        input("aggregate.in").send(part("group-1", 1, 2, "A1"));

        // Only one of two elements present: must not release yet.
        assertThat(output("aggregate.out").receive(0)).isNull();

        input("aggregate.in").send(part("group-1", 2, 2, "A2"));

        Message<?> result = receive("aggregate.out");
        assertThat(items(result)).containsExactlyInAnyOrder("A1", "A2");
        assertThat(output("aggregate.out").receive(0)).isNull();
    }

    @Test
    void aggregator_does_not_mix_interleaved_groups() {
        input("aggregate.in").send(part("group-A", 1, 2, "A1"));
        input("aggregate.in").send(part("group-B", 1, 2, "B1"));
        assertThat(output("aggregate.out").receive(0)).isNull();

        // B completes first; A is still missing A2.
        input("aggregate.in").send(part("group-B", 2, 2, "B2"));
        Message<?> resultB = receive("aggregate.out");
        assertThat(items(resultB)).containsExactlyInAnyOrder("B1", "B2");
        assertThat(output("aggregate.out").receive(0)).isNull();

        input("aggregate.in").send(part("group-A", 2, 2, "A2"));
        Message<?> resultA = receive("aggregate.out");
        assertThat(items(resultA)).containsExactlyInAnyOrder("A1", "A2");
        assertThat(output("aggregate.out").receive(0)).isNull();
    }

    @Test
    void two_batches_from_splitter_have_distinct_correlation() {
        input("split.in").send(MessageBuilder
                .withPayload(List.of("A1", "A2")).build());
        Message<?> a1 = receive("split.out");
        Message<?> a2 = receive("split.out");

        input("split.in").send(MessageBuilder
                .withPayload(List.of("B1", "B2")).build());
        Message<?> b1 = receive("split.out");
        Message<?> b2 = receive("split.out");

        String header = IntegrationMessageHeaderAccessor.CORRELATION_ID;
        Object groupA = a1.getHeaders().get(header);
        Object groupB = b1.getHeaders().get(header);

        assertThat(groupA).isNotNull();
        assertThat(groupB).isNotNull();
        assertThat(a2.getHeaders().get(header)).isEqualTo(groupA);
        assertThat(b2.getHeaders().get(header)).isEqualTo(groupB);
        assertThat(groupA).isNotEqualTo(groupB);
        assertThat(output("split.out").receive(0)).isNull();
    }

    @Test
    void roundtrip_splits_and_aggregates_one_batch() {
        input("roundtrip.in").send(MessageBuilder
                .withPayload(List.of("SKU-1", "SKU-2", "SKU-3"))
                .setHeader("requestId", "request-42")
                .build());

        Message<?> result = receive("roundtrip.out");
        assertThat(items(result))
                .containsExactlyInAnyOrder("SKU-1", "SKU-2", "SKU-3");
        assertThat(output("roundtrip.out").receive(0)).isNull();
    }

    @Configuration
    @EnableIntegration
    static class Flows {

        @Bean("split.out")
        QueueChannel splitOutput() {
            return new QueueChannel();
        }

        @Bean("aggregate.out")
        QueueChannel aggregateOutput() {
            return new QueueChannel();
        }

        @Bean("roundtrip.out")
        QueueChannel roundtripOutput() {
            return new QueueChannel();
        }

        @Bean
        IntegrationFlow splitOnly() {
            return IntegrationFlow.from("split.in")
                    .split()
                    .channel("split.out")
                    .get();
        }

        @Bean
        IntegrationFlow aggregateOnly() {
            return IntegrationFlow.from("aggregate.in")
                    .aggregate()
                    .channel("aggregate.out")
                    .get();
        }

        @Bean
        IntegrationFlow splitAndAggregate() {
            return IntegrationFlow.from("roundtrip.in")
                    .split()
                    .aggregate()
                    .channel("roundtrip.out")
                    .get();
        }
    }
}
~~~

The \`roundtrip\` test does not require the output list to preserve order because the contract here is solely **all three elements present, none missing and none extra**. When the product requires ordering, configure an appropriate preservation/sorting mechanism and write a dedicated ordering test; relying on the behavior observed in a single run is not enough.

### How to Interpret Each Test

1. \`splitter_produces_two_correlated_messages\` verifies exactly **two** messages, individual payloads, two sequence numbers, shared correlation, and the business header \`requestId\`.
2. \`aggregator_waits_until_group_is_complete\` proves the Aggregator **does not release early** after the first element; upon receiving the second element, it emits **exactly one** group message.
3. \`aggregator_does_not_mix_interleaved_groups\` sends A1, B1, B2, A2; group B arrives before A, without containing any element from A. This is the most direct test for correlation.
4. \`two_batches_from_splitter_have_distinct_correlation\` proves two independent requests produce two distinct group keys when using a standard sequence-producing splitter.
5. \`roundtrip_splits_and_aggregates_one_batch\` proves the composition of both patterns works and the output retains all elements.

**Why not compare \`correlationId\` against a hardcoded UUID?** A Splitter can derive correlation from the source message. When not assigning a group key yourself, tests should assert *same group equals, different groups differ*. This keeps tests stable when IDs are randomly generated by the framework.

**Why assert \`sequenceSize=2\`?** The Aggregator's default release strategy typically uses sequence metadata to decide when a group has all elements. If messages declare \`sequenceSize=3\` when only two items exist, the Aggregator may keep waiting even if business logic considers the group finished.

## 6. Testing Out-of-Order Message Arrival

In real systems, two messages may arrive at the Aggregator out of order—not 1 then 2. With an ExecutorChannel, broker, or parallel processing, element \`sequenceNumber=2\` may arrive before \`sequenceNumber=1\`.

Test this scenario with a separate group:

~~~java
@Test
void aggregator_accepts_out_of_order_fragments() {
    input("aggregate.in").send(part("group-reverse", 2, 2, "second"));
    assertThat(output("aggregate.out").receive(0)).isNull();

    input("aggregate.in").send(part("group-reverse", 1, 2, "first"));
    Message<?> result = receive("aggregate.out");

    assertThat(items(result))
            .containsExactlyInAnyOrder("first", "second");
    assertThat(output("aggregate.out").receive(0)).isNull();
}
~~~

This test can be added to \`SplitAggregateCorrelationTest\`. It tests the ability to **wait for all elements** despite different arrival orders. It does **not** prove the Aggregator always outputs the list sorted by sequence number: if output ordering is part of the business contract, configure group processing/sorting by \`sequenceNumber\` or place a suitable Resequencer and assert \`containsExactly("first", "second")\`.

Distinguish clearly:

- **Arrival order**: order in which messages are sent/received on the channel.
- **Assembly order**: order of elements inside the payload produced by \`MessageGroupProcessor\`.
- **Group release order**: whichever group completes first may emit first, regardless of which group started first.

A flow can guarantee exact counts and proper correlation **without** guaranteeing all three orders above.

## 7. Missing Elements and Timeouts

Suppose a group declares three elements, but only two arrive:

~~~text
G1: sequenceSize=3
  1/3 -> arrives
  2/3 -> arrives
  3/3 -> lost or processing failed
~~~

Production cannot wait forever. You must define and test one of the following policies:

| Policy | Test Expectation |
| --- | --- |
| Wait for full group | With only 2/3 present, no output yet |
| Timeout then discard group | After timeout, no success output; group resources cleaned per policy |
| Timeout then emit partial result | After timeout, a clearly marked/distinguishable partial result is emitted |
| Route incomplete group to error path | An error signal or expiry event carrying correlation ID for investigation |
| Wait for retry of one element | After retry succeeds and 3/3 arrives, the group emits once |

Relevant settings may include \`groupTimeout\`, \`sendPartialResultOnExpiry\`, \`expireGroupsUponCompletion\`, \`MessageGroupStore\`, and group-processing components. **Exact parameters and behavior must be checked against your Spring Integration version and project configuration.** Do not write tests expecting partial results unless the flow explicitly enables them.

For timeout tests, use short delays that remain stable in CI; rely on controllable clocks/triggers if supported by your setup. Use \`receive(timeout)\` or condition waits instead of fixed \`Thread.sleep\`. If the Aggregator relies on a scheduler/poller, ensure the scheduler actually runs during the test.

### Testing Incomplete Groups While Cleaning Up State

A test that sends only the first message and stops can leave a dangling group in a shared in-memory store. For simple tests, send the remaining element and consume the output as in \`aggregator_waits_until_group_is_complete\`. For timeout/expiry tests, use an isolated group store or explicit cleanup. This is a common reason Aggregator tests pass individually yet fail when run as a full suite.

## 8. Duplicate Messages, Retry, and Idempotency

In message flows, retry can cause a fragment to be resent. An Aggregator relying solely on **counting messages** risks treating a duplicate message as a new element unless deduplication is in place.

~~~text
Group G: sequenceSize=2
  arrives: 1/2 (A)
  arrives: 1/2 (A) again
  2/2 (B) has not arrived yet

Business requirement: must NOT emit a result containing [A, A].
~~~

If this test fails under the default configuration, that indicates a need for an **idempotent receiver**, a group storage strategy, or a release strategy inspecting element identities. Never assume having \`sequenceNumber\` automatically deduplicates messages.

A safe contract for an order system might be:

1. Each fragment has a unique business key, such as \`lineId\` scoped under \`correlationId\`.
2. An already-processed fragment is never counted twice.
3. Release only when all required element identifiers have been received.
4. If a fragment arrives after group completion, handle it according to an explicit policy (ignore, warn, start new group, or error event).

**Retry** on a Service Activator upstream of the Aggregator and **message redelivery** on a broker can both increase how many times a fragment traverses the same path. Testing the happy path once does not prove idempotency. Duplicate tests must exercise the actual deduplication setup to confirm expected behavior.

## 9. Correlation Key: How to Choose Safely?

A correlation ID can be generated by the Splitter or set by the application. When an Aggregator receives fragments from multiple sources, a business key is often clearer, for example:

~~~text
correlationId = "tenant:shop-a/order:1729"
~~~

When deriving correlation from business data, prevent unrelated groups from accidentally sharing a key. In multi-tenant systems, an \`orderId\` unique only within a single tenant may not suffice; use a tenant/order pair if that is the system contract.

The test matrix should include:

| Fragment | Tenant | Order | Expected Correlation |
| --- | --- | --- | --- |
| A1, A2 | \`shop-a\` | \`order-7\` | Group A |
| B1, B2 | \`shop-b\` | \`order-7\` | Group B |
| C1, C2 | \`shop-a\` | \`order-8\` | Group C |

This catches bugs where correlation only uses \`orderId\` and mixes two tenants together. With a Gateway or Router, ensure no branch strips the correlation header before the Aggregator. When a Transformer rebuilds a \`Message\`, verify required headers are still forwarded.

### Correlation Edge Cases to Classify Explicitly

- **Missing \`correlationId\`**: does the flow reject it, derive one from source data, or route to an error channel?
- **Wrong correlation type**: some keys may be UUID, String, or custom objects; sources must agree on type to group together.
- **Same value, different type**: \`"42"\` (String) and \`42\` (Integer) should not collide as the same key unless the application normalizes them intentionally.
- **Reused key**: an already-completed correlation ID reappearing later may create a new group or be rejected depending on store and expiry policy.
- **Nested splitters**: multi-level splitting creates distinct sequence/correlation scopes; confirm which level the Aggregator correlates on.

These cases have no single universal answer across all products. Tests must explicitly express your flow's business rules and configuration.

## 10. Filter Between Splitter and Aggregator: A Common Trap

Suppose a Splitter creates three messages with \`sequenceSize=3\`, but a Filter discards the second element:

~~~mermaid
flowchart LR
    IN["[A, B, C]"] --> S["Splitter, size=3"]
    S --> A["A / 1/3"]
    S --> B["B / 2/3"]
    S --> C["C / 3/3"]
    A --> AG["Aggregator"]
    B --> F["Filter rejects B"]
    C --> AG
    AG --> X["Group missing 1 element"]
~~~

If the Aggregator still uses a release strategy waiting for three elements, the group may never complete normally. This is the **difference between "3 fragments were created" and "3 fragments will reach the Aggregator"**.

Tests for this scenario must answer:

1. Can the Filter drop messages before they reach the Aggregator?
2. Does the Aggregator recognize a filtered-out member as a valid outcome?
3. Do you need a marker/placeholder to keep the sequence complete, an adjusted release strategy, or moving the Filter before the Splitter?
4. If the group only completes on timeout, how is the partial result handled?

Do not patch \`sequenceSize\` by guessing how many messages remain along each branch. Design an explicit contract across Splitter, Filter, and Aggregator. A test with list \`["A", "B", "C"]\` and a Filter dropping \`"B"\` is usually enough to expose this risk.

## 11. Testing Synchronous vs. Asynchronous Execution

The Java example above uses synchronous flows before \`QueueChannel\`. Once \`send()\` returns, you can immediately check whether the queue holds a message:

~~~java
input("aggregate.in").send(part("g", 1, 2, "A"));
assertThat(output("aggregate.out").receive(0)).isNull();
~~~

In this case, \`receive(0)\` is a **non-blocking** read at a deterministic point. If the flow includes an \`ExecutorChannel\`, broker, or poller, a message may arrive late; \`receive(0) == null\` right after \`send()\` does not prove the Aggregator will not release prematurely a few milliseconds later.

| Flow Type | What to Verify | How to Observe |
| --- | --- | --- |
| Synchronous \`DirectChannel\` | No release when incomplete; right result once complete | \`receive(0)\` and \`receive(timeout)\` |
| Multi-threaded \`ExecutorChannel\` | Right grouping regardless of timing and arrival order | Wait for expected outputs via condition, compare element sets |
| Redelivering broker | No duplicate result when a fragment is redelivered | Combine idempotency tests with real adapter |
| Persistent \`MessageGroupStore\` | Pending groups recovered after restart? | Test with real store and proper context lifecycle |
| Timeout/partial result | Incomplete group expires per policy? | Wait for event or result within finite timeout |

With parallel flows, **do not assert group completion order** if the product only requires each group to yield the right result. For instance, A1, B1, A2, B2 may let A finish before B; A1, B1, B2, A2 lets B finish before A. Each group's assembled result must still be right in both cases.

## 12. Observability, Errors, and Boundary Checks

In real systems, payload-only tests are sometimes insufficient. When a group gets stuck, operators need the correlation ID, number of received fragments, expected fragment count, and cause of delay.

You can track the following via properly designed logs, metrics, or tracing:

- \`correlationId\` or the business key used for grouping.
- Current group size and expected \`sequenceSize\`.
- Duration from the first message to group release.
- Number of expired groups, duplicate fragments, or late arrivals.
- Exceptions from a Transformer/Service Activator upstream of the Aggregator.

Do not log full sensitive payloads just to identify correlation. In tests, use dummy IDs and payloads such as \`group-A\`, \`A1\`, and \`B1\`.

If a fragment fails **before reaching the Aggregator**, the error may propagate to the caller on a synchronous path or reach the error channel if an error handler is configured for an asynchronous path. Tests must specify whether the failed fragment is retried, discarded, sent to a dead-letter destination, or fails the entire group. An error channel receiving an exception **does not mean** the Aggregator automatically knows the group can no longer complete.

## 13. Common Testing Mistakes

| Mistake | Why Is It Dangerous? | Improvement |
| --- | --- | --- |
| Testing only a single group | Fails to catch mixing two correlations | Send two interleaved groups |
| Asserting only non-\`null\` output | Misses missing or extra members | Verify all element payloads |
| Asserting only message count after Splitter | Does not verify sequence and correlation | Inspect every relevant header |
| Assuming output always has order 1, 2, 3 | Tests turn flaky under parallel execution | Assert order-independent content unless ordering is guaranteed |
| Comparing auto-generated correlation to fixed UUID | False failures when IDs change | Assert same-group equality / cross-group inequality |
| Not checking output after the first fragment | Aggregator may release prematurely | Assert no output before completion condition is met |
| Not draining test queues | Leftover messages break subsequent tests | Consume all outputs or isolate context/store |
| Assuming \`sequenceSize\` implies deduplication | Duplicates can trigger early release | Test duplicates and idempotency mechanisms |
| Not testing Filter between Splitter and Aggregator | Group may wait forever | Test partial group and expiry policy |
| Using fixed \`Thread.sleep\` | Slow and flaky tests | Use condition waits and finite timeouts |

## 14. Practice Exercises

### Exercise A — Add a Third Group

Extend the Aggregator test with three groups \`G1\`, \`G2\`, \`G3\`, two fragments each. Send in the order \`G1-1, G2-1, G3-1, G3-2, G1-2, G2-2\`. Verify that the three outputs contain the exact data for groups G3, G1, and G2 respectively in the example's **synchronous flow**.

### Exercise B — Reverse Sequence Order

Send \`2/2\` before \`1/2\`. Prove the Aggregator emits nothing after the first fragment and emits only one result once both fragments arrive. If the application requires output ordered by sequence, configure explicit sorting and test that order.

### Exercise C — Lost Fragment

Create a three-element group but send only \`1/3\` and \`2/3\`. Configure timeout/expiry matching your project's policy; verify no early success result is emitted, then verify the group is handled upon expiry without leaving unexpected dangling state.

### Exercise D — Redelivered Fragment

Send \`1/2\` twice, and only then send \`2/2\`. The goal is to design and test a deduplication mechanism so two copies of \`1/2\` are not treated as two valid members. The test passes only when the Aggregator emits exactly one result containing **A and B**, never two copies of A.

### Exercise E — Filter Between Splitter and Aggregator

Have a Splitter emit three elements \`A\`, \`B\`, \`C\` while a Filter drops \`B\`. Explain why a release condition based on \`sequenceSize=3\` no longer fits without handling rejected members. Choose a policy and write a test proving the group does not live forever.

## 15. Completion Criteria

A Splitter/Aggregator correlation test suite meets the standard when it verifies all of the following:

1. The Splitter emits the exact message count, exact payloads, and required sequence headers.
2. Fragments of one request share the same correlation; independent requests are never merged.
3. The Aggregator does not release when elements are missing and produces the exact expected output count upon completion.
4. Two or more interleaved groups still produce separate results without mixing data.
5. Out-of-order, missing, duplicate, or late arrivals follow an explicit policy.
6. Tests use finite timeouts, isolate group stores, and do not depend on unguaranteed timing or ordering.

Once correlation and release conditions are verified at the message level, you can wire in Routers, Filters, Gateways, retries, error channels, and asynchronous processing while still tracing **which group a message belongs to, whether the group is ready, and why a result was emitted**.
