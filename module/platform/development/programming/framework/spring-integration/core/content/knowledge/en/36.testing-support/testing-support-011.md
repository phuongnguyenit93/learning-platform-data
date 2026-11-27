# Testing Splitter-Aggregator

## 1. Objectives and scope

In the **Testing support** chapter of the **SPRING_INTEGRATION_CORE** module, this lesson shows how to test a flow that splits a message, processes each part, and aggregates the results. The focus is the contract between `Message`, `MessageChannel`, splitter endpoints, transformers, and aggregators in the Java DSL.

After this lesson, you will be able to:

- Verify payloads and headers correlating split parts.
- Prove an aggregator waits for sufficient data and does not mix requests.
- Construct test data that arrives out of order, late, missing, or duplicated.
- Distinguish testing expiry policies from testing the scheduler.
- Observe outputs, discard branches, errors, and group state using clear checkpoints.

Examples use Java 17, JUnit Jupiter, Spring Test, and Spring Integration 6.5.x APIs. Choose library versions compatible with your project's BOM; do not mix arbitrary Spring versions. The example classes are independent of Spring Boot, brokers, and databases.

## 2. The problem: getting the right sum is not enough to prove the flow

Suppose a request holds the list `[1, 2, 3]`. Each item is multiplied by `10`; the aggregator computes the sum:

~~~text
[1, 2, 3] → 1, 2, 3 → 10, 20, 30 → 60
~~~

A single check `payload == 60` cannot answer the following questions:

- Was any message routed into another request's group by mistake?
- Did the group emit a result before the last part arrived?
- Was an unexpected extra result emitted?
- Were business headers preserved after the transformer?
- Does a late message reopen an already completed request?
- If the second part never arrives, how long is data retained?

Therefore, verify **values**, **output counts**, and **state transitions**. With addition, reordering does not change the sum; if business logic requires ordering, add a separate ordering check.

~~~mermaid
flowchart LR
    A["Request: List<Integer>"] --> B["Splitter"]
    B --> C["Transformer: x * 10"]
    C --> D["Pre-aggregator channel"]
    D --> E["Aggregator"]
    E <--> S[("MessageGroupStore")]
    E --> F["Result: sum"]
    E --> G["Discard"]
    B --> H["Empty input"]
~~~

In this lesson, there are three testing levels:

| Level | Where to send data? | Where to observe? | Primary question |
|---|---|---|---|
| Splitter | Before splitter | Channel holding parts | Are split payloads and headers correct? |
| Aggregator | Directly before aggregator | Output, discard, and store | Are groups held, released, and closed properly? |
| Full flow | Business entry point | Final result | Do endpoints collaborate properly? |

Do not mock the splitter or aggregator when testing their own contracts. In a real system, you can replace a pricing service or remote adapter with a controlled collaborator.

## 3. Message contracts to verify

### 3.1. Headers after the splitter

With the default splitter, a fixed-size `List` input, and `applySequence` enabled, parts carry sequence headers. Use constants from `IntegrationMessageHeaderAccessor` in test code to avoid typos in header names. See [the splitter contract](https://docs.spring.io/spring-integration/reference/6.5/splitter.html).

| Header | Meaning in the example | What to assert |
|---|---|---|
| `CORRELATION_ID` | Links parts of a split | Parts share the same value; with the default splitter here, it equals the input message's ID |
| `SEQUENCE_NUMBER` | Item position | Respectively `1, 2, 3` |
| `SEQUENCE_SIZE` | Expected total parts | All equal `3` |
| `orderId` | Application-set business key | Preserves expected value |

`orderId` does not automatically become the grouping key just because it looks like an order ID. To group by a business key, configure a correlation strategy and test that strategy.

These assertions apply to the specific splitter in the example. For custom splitters or nested splits, write matching contracts.

### 3.2. Correlation, release, and result generation are three decisions

An aggregator must answer:

1. Which group does the message belong to?
2. Is the group ready to emit a result?
3. When emitting, how is the result payload computed?

The default configuration uses the correlation header for grouping and sequence size for release. The example below keeps those two decisions and only replaces the processor to compute the sum. See [the aggregator model](https://docs.spring.io/spring-integration/reference/6.5/aggregator.html).

Place checkpoints at the boundary of each decision. If a full-flow test fails, smaller tests distinguish post-splitter metadata errors from release or summation errors.

### 3.3. Distinguishing group completion from group removal

A group can be completed—holding no remaining items—while still keeping a record to recognize late arrivals. With `expireGroupsUponCompletion(false)`, the example intentionally keeps this marker. Thus, do not expect `getMessageGroupCount() == 0` for every completion case.

Check `isComplete()`, `size()`, and behavior on late arrivals separately. See [AggregatingMessageHandler lifecycle](https://docs.spring.io/spring-integration/api/org/springframework/integration/aggregator/AggregatingMessageHandler.html).

## 4. Preparing dependencies and environment

In a project that already has Spring Boot dependency management, you can use:

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

If not using Boot, manage compatible versions for `spring-integration-core`, `spring-test`, JUnit Jupiter, and related test libraries. Configure your build tool to run JUnit Platform.

The main test suite below uses only Spring Test and JUnit; `spring-integration-test` supports endpoint-substitution scenarios later on. `@SpringIntegrationTest` provides `MockIntegrationContext` when part of a flow needs replacing; it is not mandatory merely to run an `IntegrationFlow` in Spring Test. See [testing support and the test context](https://docs.spring.io/spring-integration/reference/6.5/testing.html).

## 5. Complete test suite for splitter, aggregator, and full flow

The example creates independent entry points:

- `splitInput` goes only through the splitter, convenient for inspecting parts.
- `aggregateInput` accepts parts that already have headers, convenient for controlling release timing.
- `fullInput` runs through the splitter and transformer and feeds into the same aggregator.

Result receivers are `QueueChannel` instances so the test can read messages explicitly. Processing channels are `DirectChannel` instances, so sends and normal processing in this setup run synchronously.

Place the following class in your project's test source set when practicing:

~~~java
import java.util.List;
import java.util.UUID;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.store.SimpleMessageStore;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.*;

@SpringJUnitConfig(SplitterAggregatorTest.Config.class)
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class SplitterAggregatorTest {

    @Autowired
    @Qualifier("splitInput")
    DirectChannel splitInput;

    @Autowired
    @Qualifier("splitParts")
    QueueChannel splitParts;

    @Autowired
    @Qualifier("emptySplits")
    QueueChannel emptySplits;

    @Autowired
    @Qualifier("fullInput")
    DirectChannel fullInput;

    @Autowired
    @Qualifier("aggregateInput")
    DirectChannel aggregateInput;

    @Autowired
    @Qualifier("totals")
    QueueChannel totals;

    @Autowired
    @Qualifier("discarded")
    QueueChannel discarded;

    @Autowired
    SimpleMessageStore groupStore;

    @Test
    void splitterPublishesPayloadsAndSequenceHeaders() {
        Message<List<Integer>> request =
                MessageBuilder.withPayload(List.of(1, 2, 3))
                        .setHeader("orderId", "ORD-101")
                        .build();

        assertTrue(splitInput.send(request));

        for (int number = 1; number <= 3; number++) {
            Message<?> part = splitParts.receive(0);
            assertNotNull(part);

            assertEquals(number, part.getPayload());
            assertEquals(request.getHeaders().getId(),
                    part.getHeaders().get(
                            IntegrationMessageHeaderAccessor.CORRELATION_ID));
            assertEquals(Integer.valueOf(number),
                    part.getHeaders().get(
                            IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER,
                            Integer.class));
            assertEquals(Integer.valueOf(3),
                    part.getHeaders().get(
                            IntegrationMessageHeaderAccessor.SEQUENCE_SIZE,
                            Integer.class));
            assertEquals("ORD-101", part.getHeaders().get("orderId"));
        }

        assertNull(splitParts.receive(0));
        assertNull(emptySplits.receive(0));
    }

    @Test
    void emptyListIsSentToSplitterDiscardChannel() {
        Message<List<Integer>> request =
                MessageBuilder.withPayload(List.<Integer>of()).build();

        assertTrue(splitInput.send(request));

        assertNull(splitParts.receive(0));
        Message<?> rejected = emptySplits.receive(0);
        assertNotNull(rejected);
        assertEquals(request.getHeaders().getId(),
                rejected.getHeaders().getId());
        assertEquals(List.of(), rejected.getPayload());
        assertNull(emptySplits.receive(0));
    }

    @Test
    void aggregatorWaitsUntilAllThreePartsArrive() {
        UUID groupId = UUID.randomUUID();

        assertTrue(aggregateInput.send(part(groupId, 1, 3, 10)));
        assertNull(totals.receive(0));
        assertEquals(1, groupStore.getMessageGroup(groupId).size());
        assertFalse(groupStore.getMessageGroup(groupId).isComplete());

        assertTrue(aggregateInput.send(part(groupId, 2, 3, 20)));
        assertNull(totals.receive(0));
        assertEquals(2, groupStore.getMessageGroup(groupId).size());

        assertTrue(aggregateInput.send(part(groupId, 3, 3, 30)));
        assertTotal(60);
        assertTrue(groupStore.getMessageGroup(groupId).isComplete());
        assertEquals(0, groupStore.getMessageGroup(groupId).size());
        assertNull(discarded.receive(0));
    }

    @Test
    void outOfOrderArrivalStillProducesTheExpectedSum() {
        UUID groupId = UUID.randomUUID();

        assertTrue(aggregateInput.send(part(groupId, 3, 3, 30)));
        assertNull(totals.receive(0));

        assertTrue(aggregateInput.send(part(groupId, 1, 3, 10)));
        assertNull(totals.receive(0));

        assertTrue(aggregateInput.send(part(groupId, 2, 3, 20)));
        assertTotal(60);
    }

    @Test
    void interleavedGroupsAreNotMixed() {
        UUID groupA = UUID.randomUUID();
        UUID groupB = UUID.randomUUID();

        assertTrue(aggregateInput.send(part(groupA, 1, 2, 10)));
        assertTrue(aggregateInput.send(part(groupB, 1, 2, 100)));
        assertNull(totals.receive(0));
        assertEquals(1, groupStore.getMessageGroup(groupA).size());
        assertEquals(1, groupStore.getMessageGroup(groupB).size());

        assertTrue(aggregateInput.send(part(groupA, 2, 2, 20)));
        assertTotal(30);
        assertFalse(groupStore.getMessageGroup(groupB).isComplete());
        assertEquals(1, groupStore.getMessageGroup(groupB).size());

        assertTrue(aggregateInput.send(part(groupB, 2, 2, 200)));
        assertTotal(300);
    }

    @Test
    void latePartIsDiscardedWhenCompletedGroupIsRetained() {
        UUID groupId = UUID.randomUUID();

        assertTrue(aggregateInput.send(part(groupId, 1, 2, 10)));
        assertTrue(aggregateInput.send(part(groupId, 2, 2, 20)));
        assertTotal(30);

        Message<Integer> late = part(groupId, 2, 2, 999);
        assertTrue(aggregateInput.send(late));

        assertNull(totals.receive(0));
        Message<?> rejected = discarded.receive(0);
        assertNotNull(rejected);
        assertEquals(late.getHeaders().getId(),
                rejected.getHeaders().getId());
        assertEquals(999, rejected.getPayload());
        assertNull(discarded.receive(0));
    }

    @Test
    void fullFlowSplitsTransformsAndAggregates() {
        Message<List<Integer>> request =
                MessageBuilder.withPayload(List.of(1, 2, 3))
                        .setHeader("orderId", "ORD-202")
                        .build();

        assertTrue(fullInput.send(request));

        assertTotal(60);
        assertTrue(groupStore.getMessageGroup(
                request.getHeaders().getId()).isComplete());
        assertNull(discarded.receive(0));
    }

    private void assertTotal(int expected) {
        Message<?> output = totals.receive(0);
        assertNotNull(output);
        assertEquals(expected, output.getPayload());
        assertNull(totals.receive(0));
    }

    private static Message<Integer> part(
            UUID groupId, int number, int size, int payload) {
        return MessageBuilder.withPayload(payload)
                .setHeader(IntegrationMessageHeaderAccessor.CORRELATION_ID,
                        groupId)
                .setHeader(IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER,
                        number)
                .setHeader(IntegrationMessageHeaderAccessor.SEQUENCE_SIZE,
                        size)
                .build();
    }

    @Configuration
    @EnableIntegration
    static class Config {

        @Bean
        DirectChannel splitInput() {
            return new DirectChannel();
        }

        @Bean
        QueueChannel splitParts() {
            return new QueueChannel();
        }

        @Bean
        QueueChannel emptySplits() {
            return new QueueChannel();
        }

        @Bean
        DirectChannel fullInput() {
            return new DirectChannel();
        }

        @Bean
        DirectChannel aggregateInput() {
            return new DirectChannel();
        }

        @Bean
        QueueChannel totals() {
            return new QueueChannel();
        }

        @Bean
        QueueChannel discarded() {
            return new QueueChannel();
        }

        @Bean
        SimpleMessageStore groupStore() {
            return new SimpleMessageStore();
        }

        @Bean
        IntegrationFlow splitterProbeFlow() {
            return IntegrationFlow.from(splitInput())
                    .split(spec -> spec
                            .applySequence(true)
                            .discardChannel(emptySplits()))
                    .channel(splitParts())
                    .get();
        }

        @Bean
        IntegrationFlow fullFlow() {
            return IntegrationFlow.from(fullInput())
                    .split()
                    .transform(Integer.class, value -> value * 10)
                    .channel(aggregateInput())
                    .get();
        }

        @Bean
        IntegrationFlow aggregationFlow() {
            return IntegrationFlow.from(aggregateInput())
                    .aggregate(spec -> spec
                            .messageStore(groupStore())
                            .outputProcessor(group -> group.getMessages()
                                    .stream()
                                    .mapToInt(message ->
                                            (Integer) message.getPayload())
                                    .sum())
                            .expireGroupsUponCompletion(false)
                            .discardChannel(discarded()))
                    .channel(totals())
                    .get();
        }
    }
}
~~~

### 5.1. Why does the test read immediately with receive(0)?

This configuration has no executors, pollers, or timeout tasks. Once `DirectChannel.send()` returns successfully, processing along the send path is complete; any result is already in the output queue. `receive(0)` simply fetches available data without waiting.

This also makes the assertion "no result after the first part" unambiguous. When switching a segment to `ExecutorChannel`, change the waiting mechanism; do not copy instantaneous assertions unchanged into an asynchronous flow. Calling-thread behavior of `DirectChannel` is described in [error handling](https://docs.spring.io/spring-integration/reference/6.5/error-handling.html).

### 5.2. Why does each test get a clean context?

Both the aggregator and queues are stateful. A test might leave an incomplete group or unread messages behind. `@DirtiesContext` in the example forces rebuilding the context for the next test, keeping scenarios independent.

This prioritizes clarity for a small fixture. For larger suites, use per-test isolated stores and controlled resource cleanup. Switching group IDs to UUIDs alone does not clean up dangling groups left in the store.

### 5.3. Why not use QueueChannel as a mid-flow observation channel?

If a `QueueChannel` has both a real processing poller and a test calling `receive()`, both compete for messages. The test could steal an item meant for the aggregator.

In the example, `splitParts` is the terminal channel of a dedicated probe flow. It is not simultaneously the input to downstream processing. When observing a real flow, use an interceptor or observation branch that does not consume messages away from the flow; define the observation point clearly before writing assertions.

### 5.4. What the test suite has and has not proved

The test suite proves the in-memory configuration handles the stated scenarios correctly. It does not prove durability across restarts, multi-instance group aggregation, database rollbacks, or broker redelivery policies.

A full-flow result of `60` shows that parts reached the same group with all required metadata. If the contract also requires preserving `orderId`, inspect individual messages right before the aggregator and assert that header; do not infer preservation of all headers solely from the final sum.

## 6. Testing timeouts without relying on Thread.sleep()

### 6.1. Separating two timing questions

For a group that has received two of three parts, there are two distinct things to verify:

| Question | Test type |
|---|---|
| When forcing an incomplete group to finish, emit a partial result or discard? | Expiry policy test |
| Does the scheduler trigger expiry handling after the configured interval? | Scheduler integration test |

`sendPartialResultOnExpiry(true)` chooses how expiry is handled; this option alone does not create an expiry schedule. When configuring, also distinguish keeping a group marker from removing the group completely. These APIs are in [CorrelationHandlerSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/CorrelationHandlerSpec.html).

Do not write every test by sending messages, calling `Thread.sleep(1000)`, and then checking. That slows down the suite and depends on machine load.

### 6.2. Testing policy with a test-only adapter

The class below exposes a method calling the handler's protected `forceComplete`. It uses the real aggregator, real in-memory store, and real queues; it only triggers the group-completion event explicitly.

This is a policy test; it bypasses the store's expired-group selection callback and does not test scheduler timing. `forceComplete` is a `protected` extension point; keep the adapter strictly in test code and review it upon framework upgrades. See [AbstractCorrelatingMessageHandler API](https://docs.spring.io/spring-integration/api/org/springframework/integration/aggregator/AbstractCorrelatingMessageHandler.html).

~~~java
import java.util.UUID;

import org.junit.jupiter.api.Test;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.integration.aggregator.AggregatingMessageHandler;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.store.SimpleMessageStore;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.*;

class AggregatorExpiryPolicyTest {

    @Test
    void expiryCanProduceAPartialResult() {
        verifyExpiry(true);
    }

    @Test
    void expiryCanDiscardTheIncompleteGroup() {
        verifyExpiry(false);
    }

    private void verifyExpiry(boolean partialResult) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            TestAggregator handler = context.getBean(TestAggregator.class);
            SimpleMessageStore store =
                    context.getBean(SimpleMessageStore.class);
            QueueChannel results =
                    context.getBean("results", QueueChannel.class);
            QueueChannel discarded =
                    context.getBean("discarded", QueueChannel.class);

            handler.setSendPartialResultOnExpiry(partialResult);

            UUID groupId = UUID.randomUUID();
            handler.handleMessage(part(groupId, 1, 3, 10));
            handler.handleMessage(part(groupId, 2, 3, 20));

            assertNull(results.receive(0));
            assertEquals(2, store.getMessageGroup(groupId).size());

            handler.expireNow(groupId);

            if (partialResult) {
                Message<?> output = results.receive(0);
                assertNotNull(output);
                assertEquals(30, output.getPayload());
                assertNull(results.receive(0));
                assertNull(discarded.receive(0));
            }
            else {
                assertNull(results.receive(0));
                Message<?> first = discarded.receive(0);
                Message<?> second = discarded.receive(0);
                assertNotNull(first);
                assertNotNull(second);
                int sum = (Integer) first.getPayload()
                        + (Integer) second.getPayload();
                assertEquals(30, sum);
                assertNull(discarded.receive(0));
            }

            assertEquals(0, store.getMessageGroupCount());
            assertEquals(0, store.getMessageCountForAllMessageGroups());
        }
    }

    private static Message<Integer> part(
            UUID groupId, int number, int size, int payload) {
        return MessageBuilder.withPayload(payload)
                .setHeader(IntegrationMessageHeaderAccessor.CORRELATION_ID,
                        groupId)
                .setHeader(IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER,
                        number)
                .setHeader(IntegrationMessageHeaderAccessor.SEQUENCE_SIZE,
                        size)
                .build();
    }

    static class TestAggregator extends AggregatingMessageHandler {

        private final SimpleMessageStore store;

        TestAggregator(SimpleMessageStore store) {
            super(group -> group.getMessages().stream()
                    .mapToInt(message -> (Integer) message.getPayload())
                    .sum(), store);
            this.store = store;
        }

        void expireNow(Object groupId) {
            forceComplete(this.store.getMessageGroup(groupId));
        }
    }

    @Configuration
    @EnableIntegration
    static class Config {

        @Bean
        SimpleMessageStore store() {
            return new SimpleMessageStore();
        }

        @Bean
        QueueChannel results() {
            return new QueueChannel();
        }

        @Bean
        QueueChannel discarded() {
            return new QueueChannel();
        }

        @Bean
        TestAggregator aggregator() {
            TestAggregator handler = new TestAggregator(store());
            handler.setOutputChannel(results());
            handler.setDiscardChannel(discarded());
            handler.setDiscardIndividuallyOnExpiry(true);
            handler.setExpireGroupsUponTimeout(true);
            return handler;
        }
    }
}
~~~

Expecting `getMessageGroupCount() == 0` here is valid because the fixture explicitly sets `expireGroupsUponTimeout(true)`. It differs from the earlier fixture that retains groups after normal completion.

`setDiscardIndividuallyOnExpiry(true)` specifies that each expired message is sent individually to discard. Avoiding assumptions about store iteration order, the test sums the payloads of the two received messages instead of requiring `10` to always arrive before `20`.

### 6.3. Adding a real test with the scheduler

To verify timing wiring in the application, create a dedicated fixture, for example:

~~~java
.aggregate(spec -> spec
        .messageStore(timeoutStore)
        .groupTimeout(200)
        .sendPartialResultOnExpiry(true)
        .expireGroupsUponTimeout(true))
~~~

`timeoutStore` is a store dedicated to that aggregator. In an integration-enabled context, ensure the flow's scheduler is running. Send two parts with `sequenceSize = 3`, then wait:

~~~java
Message<?> output = results.receive(5_000);
assertNotNull(output);
assertEquals(30, output.getPayload());
~~~

`5_000` is the test's wait bound, not the business timeout value. If you need to confirm no second result is emitted, use a finite observation window suited to the fixture; an instantaneous check does not prove no future messages will arrive.

Add a test where the group receives all three parts before the timeout. The group must emit one complete result; the remaining timeout task must not produce duplicate output. When exact time-boundary assertions are required, use a controllable scheduler rather than asserting on exact wall-clock milliseconds.

When choosing reaper-based cleanup, `MessageGroupStoreReaper.run()` triggers the store scan; tests can invoke it directly after aging the group. See [MessageGroupStoreReaper API](https://docs.spring.io/spring-integration/api/org/springframework/integration/store/MessageGroupStoreReaper.html). The direct `forceComplete` test above does not replace testing the reaper's aged-group selection.

## 7. Boundary cases that need dedicated design

### 7.1. Duplicate items: distinguishing message ID from sequence number

The following two scenarios are not equivalent:

~~~java
Message<Integer> original = part(groupId, 1, 3, 10);

// Resending the exact same object, preserving MessageHeaders.ID.
aggregateInput.send(original);
aggregateInput.send(original);

// Two new messages: same sequence number, different IDs.
aggregateInput.send(part(groupId, 1, 3, 10));
aggregateInput.send(part(groupId, 1, 3, 10));
~~~

The store may treat these two scenarios differently. Do not use the first scenario to conclude the system performs business deduplication in the second scenario.

`SimpleSequenceSizeReleaseStrategy` compares the number of parts in the group against the expected size without guaranteeing duplicate sequence-number checks. Hence, a correct sum in a non-duplicate scenario does not prove idempotency. See [SimpleSequenceSizeReleaseStrategy API](https://docs.spring.io/spring-integration/api/org/springframework/integration/aggregator/SimpleSequenceSizeReleaseStrategy.html).

If duplicate sequence numbers within a group must be blocked, evaluate `SequenceSizeReleaseStrategy` with a matching handler; this API provides support for detecting duplicate sequences. Still test the real configuration. See [SequenceSizeReleaseStrategy API](https://docs.spring.io/spring-integration/api/org/springframework/integration/aggregator/SequenceSizeReleaseStrategy.html).

A suitable test dataset:

| Step | Sequence number | Payload | Expectation if contract requires deduplication |
|---|---|---|---|
| 1 | `1/3` | `10` | Not yet released |
| 2 | `1/3`, new message ID | `10` | Not yet released, not added to sum |
| 3 | `2/3` | `20` | Not yet released |
| 4 | `3/3` | `30` | Emits strictly one result `60` |

If the same item key has different payloads—for example, two `1/3` parts with `10` and `99`—decide explicitly whether to keep the first, keep the latest, or report a conflict. A release strategy alone does not fully define that business policy.

For data arriving from a broker, deduplication keys typically need to include both the request's business ID and the item's ID. Also test resending the whole request after the old group has been removed, because the aggregator may then open a new group.

### 7.2. A filter between splitter and aggregator

Suppose the splitter produces three parts, yet a filter discards one:

~~~text
sequenceSize = 3
       ↓
10 → keep
20 → discard
30 → keep
       ↓
aggregator receives only 2 parts
~~~

Write a test sending `[1, 2, 3]` into the flow with the filter and observe:

1. Two parts are forwarded to the aggregator.
2. One part goes to the filter's discard channel per configuration.
3. The group has not emitted a full result.
4. The incomplete-group handling policy triggers as designed.

Given a contract requiring three results, receiving only two parts is not enough to consider the request complete. Options include emitting a compensating message representing the rejected item, computing the valid count before splitting, or using another business release condition. Each choice needs tests distinguishing "sufficient results" from "all parts finished processing".

Do not arbitrarily mutate `sequenceSize` on a few messages just to make a test green; metadata must stay consistent with the design of the entire group.

### 7.3. Iterators or unknown-size sources

For sources where total part count cannot be determined beforehand, `sequenceSize` can be `0`. Assert the actual header value before testing release, instead of assuming it always equals the number of received parts.

If the contract has no total part count, use an end-of-stream signal, total count metadata from the source, or a time-based completion policy. Use the same business data to test both `List` inputs and unknown-size sources, while writing release expectations per each source's contract. See also [splitter Iterator handling](https://docs.spring.io/spring-integration/reference/6.5/splitter.html#splitter-iterators).

### 7.4. Empty inputs and a splitter returning null

The main test suite explicitly configures discard handling for empty inputs. No parts are sent to the aggregator, so you cannot expect the aggregator to produce a sum of `0` on its own.

If business logic needs to return an empty order, route empty inputs to a dedicated result-building branch before the splitter and test that branch.

Do not conflate an empty iterable container with a splitter function returning `null`. The splitter's discard option applies to empty iterable results, not as a blanket rule for every `null` return value. See [SplitterSpec API](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/SplitterSpec.html).

### 7.5. Results requiring exact ordering

Addition in the example is order-independent. If the output is a list with business-significant positions, define ordering right in the output processor, such as sorting by sequence number:

~~~java
.outputProcessor(group -> group.getMessages().stream()
        .sorted(java.util.Comparator.comparingInt(message ->
                message.getHeaders().get(
                        IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER,
                        Integer.class)))
        .map(Message::getPayload)
        .toList())
~~~

This snippet assumes sequence headers are present and valid. Send parts in order `3, 1, 2` and assert the result list is `[10, 20, 30]`. Do not rely on a store's iteration order as a business contract.

If individual messages must be emitted in order rather than producing one aggregated result, evaluate a resequencer. Tests should reflect the output shape actually used by the application.

## 8. Testing errors during per-part processing

Suppose the transformer for item `2` throws an exception. Two questions must be separated:

- To which caller or error channel is the exception routed?
- Does error handling produce a compensating result so the group can still complete?

### 8.1. With synchronous flows

Create a dedicated fixture with an intentionally failing transformer:

~~~java
.transform(Integer.class, value -> {
    if (value == 2) {
        throw new IllegalStateException("Cannot process item 2");
    }
    return value * 10;
})
~~~

When sending via a direct channel, assert the exception per the endpoint contract; business exceptions may be wrapped in messaging exceptions. Do not assert verbatim on full stack traces or every wrapping layer unless the application guarantees them.

In the example's synchronous flow without recovery advice, a failure on the second part may halt sending the list before the third part is even sent. Verify how many parts actually reached the aggregator, what remains incomplete in the group, and how that group is cleaned up.

Do not assume a single send through a splitter is an atomic transaction covering every part that passed through the flow.

### 8.2. With asynchronous flows

Use an observable error channel and wait for an `ErrorMessage` with a bounded timeout. Verify:

- The ultimate business root cause of the failure.
- The failed message and the request or item identifier.
- The number of emitted results and group state.
- Outcomes after retry, recovery, or compensating messages, if configured.

Simply asserting "`send()` does not throw an exception" does not prove asynchronous workers succeeded. Wait for both outputs and errors per the flow contract. Error mechanics depend on the configured executor, poller, and error handler; not every custom executor shares the same error-publishing policy.

### 8.3. Gateway timeout does not mean the aggregator was cleaned up

If the application uses a messaging gateway to wait for results, the gateway's reply timeout is a caller-side contract. Groups held in the aggregator represent processing-flow state.

Write a separate test for the scenario where the gateway times out while the group is still missing parts. Then check the aggregator's timeout or store-cleanup policy. Do not treat the caller giving up on waiting as evidence that the group has terminated.

## 9. Isolating external services while keeping the real splitter-aggregator

When a flow makes HTTP pricing calls, splitter-aggregator tests typically check call counts, metadata, and how results are aggregated. Assign explicit endpoint IDs to external service endpoints, then use `MockIntegrationContext` to replace those endpoint handlers in tests.

A suitable sequence:

1. Load the real flow and enable `@SpringIntegrationTest`.
2. Replace the pricing endpoint handler with a reply-producing test handler.
3. Send a multi-part request to the real entry point.
4. Verify every part was processed with expected data.
5. Verify the real aggregator emits the right result.
6. Restore the endpoint with `resetBeans()` after the test.

`substituteMessageHandlerFor` takes **the consumer endpoint name**, not a channel name and not a guessed handler ID. If using plain Mockito for a reply handler, configure appropriate replies; a handler that only counts calls without replying can starve the group of parts.

Do not replace the aggregator with a mock and claim you verified the release strategy. That test only shows the upstream segment sent data to the expected point.

## 10. Concurrency testing and persistent stores

### 10.1. Concurrency testing

Testing parts arriving in order `3, 1, 2` is an arrival-order test, not a multi-threaded execution test.

When the real application processes in parallel, add a fixture with a managed executor that is shut down after the test. Use a latch or barrier to coordinate workers to the contention point; await futures with a timeout, then inspect outputs.

Invariants to maintain within a group:

- Exact result count per contract.
- No valid items lost.
- No correlation mixing between two requests.
- No re-emission of results on late arrivals.
- No incomplete groups retained past the retention policy.

Do not use `Thread.sleep` to hope a race condition happens. When a test fails, capture group data, sequences, and worker causes so it is reproducible.

### 10.2. Testing with a persistent MessageGroupStore

`SimpleMessageStore` is an in-memory store suited for isolated examples. It does not prove behavior when the application process stops and restarts. See [SimpleMessageStore API](https://docs.spring.io/spring-integration/api/org/springframework/integration/store/SimpleMessageStore.html).

With a persistent store, a valuable integration scenario is:

1. Start the store and first aggregator.
2. Send parts `1/3` and `2/3`, confirming data is persisted.
3. Simulate the target restart condition for the test.
4. Start a new aggregator pointing to the same data.
5. Send part `3/3`.
6. Verify the output and remaining state in the store.

Distinguish a graceful shutdown from an abrupt process crash: shutdown lifecycle hooks can affect groups. Recovery test scenarios must document which condition is simulated.

Use stable group identifiers, transaction settings, and serialization matching the real system. When multiple instances operate concurrently, test appropriate locking mechanisms; results from an in-memory store in a single JVM do not cover that case.

When using callback-based expiry, dedicate a logical store per aggregator so one endpoint does not affect another endpoint's groups. They can share physical storage infrastructure if the implementation's partitioning configuration allows it.

## 11. Test matrix to select by business contract

| Scenario | Test data produced | Core expectation |
|---|---|---|
| Single item | List with one item | One part with sequence `1/1`; one result |
| Multiple valid items | List with three items | Full headers, right payloads, and strictly one result |
| Incomplete parts | `1/3` then `2/3` | Not yet released; group holds two parts |
| Out-of-order arrival | `3/3`, `1/3`, `2/3` | Released once complete; output order per contract |
| Two interleaved groups | A1, B1, A2, B2 | Outputs for A and B stay separate |
| Empty list | No parts | Empty or discard branch handled explicitly |
| One part filtered out | Only two of three parts reach aggregator | Does not pretend completion; incomplete-group policy applies |
| Duplicate sequence | Same sequence number, different ID | Handled per deduplication or conflict policy |
| Late arrival | Sent after group completion | Discarded or opens new group per configuration |
| Expired, partial results allowed | Missing one part | Partial result emitted and store state accurate |
| Expired, partial results disallowed | Missing one part | Data discarded properly; no normal result emitted |
| Transformer fails | One part throws exception | Error observable and incomplete group handled |
| Parallel processing | Multiple workers sending concurrently | No lost, mixed, or extra emissions outside contract |
| Restart | Store holds partial group | Recovers properly per operational policy |

This is a menu of design-driven choices, not a mandate to cram every scenario into a single test. Each test should have one easy-to-explain reason to fail.

## 12. How to diagnose when a test receives no result

Start from the observation point closest to the failure:

1. **Did the splitter actually emit parts?** Check input payload, empty results, and part count.
2. **Are all headers intact before the aggregator?** Verify correlation, sequence number, and sequence size.
3. **Do groups share the right key?** Two keys that look identical in logs can differ in data type.
4. **Was the group already marked complete from a prior run?** Check store state and the discard branch.
5. **Does the release strategy match the data?** Especially with filters and unknown-size sources.
6. **Did an intermediate step throw an exception?** Check the send exception or error channel.
7. **Did the test steal parts from an intermediate channel?** Inspect queues and active consumers.
8. **If using timeouts, is the scheduler running?** Distinguish scheduling bugs from expiry-policy bugs.

When inspecting the store, prefer querying by specific group ID. `getMessageGroupCount()` and `getMessageCountForAllMessageGroups()` answer two different questions; group count does not equal message count. Expiry and statistics operations are described in [MessageGroupStore](https://docs.spring.io/spring-integration/api/org/springframework/integration/store/MessageGroupStore.html).

A useful splitter-aggregator test reveals which group data belongs to, when it is released, which output it reaches, and what state remains afterward. That provides the foundation to extend the flow with routers, filters, gateways, or error handling while keeping integration contracts intact.
