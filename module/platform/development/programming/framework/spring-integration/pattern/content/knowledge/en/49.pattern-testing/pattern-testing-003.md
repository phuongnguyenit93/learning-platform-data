# Testing Linear Flows in Spring Integration

## 1. What Is a Linear Flow and Why Test It?

In **Enterprise Integration Patterns (EIP)**, a message flow can consist of multiple endpoints connected in sequence. The simplest case is a **linear flow**: a message passes through processing steps in a defined order, from entry point to exit point. Each step receives the result of the previous step and forwards it to the next.

Example with Spring Integration:

~~~mermaid
flowchart LR
    A["Input Channel"] --> B["Transformer: trim"]
    B --> C["Filter: non-blank"]
    C --> D["Header Enricher"]
    D --> E["Transformer: uppercase"]
    E --> F["Service Activator"]
    F --> G["Output Channel"]
    C -.->|Rejected| H["Discard Channel"]
~~~

This lesson belongs to the **Pattern Testing** chapter of the **SPRING_INTEGRATION_PATTERN** module. The module focuses on building loosely coupled and extensible message flows using Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation; testing linear flows is the foundation for verifying individual segments before composing multi-branch flows.

After this lesson, you will be able to:

1. Define the inputs, outputs, and invariants of a chain of endpoints.
2. Write flow tests using the Java DSL, JUnit 5, and in-memory channels.
3. Verify the final data, preserved headers, and emitted message count.
4. Prove that steps execute in the right order, especially when order changes the result.
5. Test Filter termination points, mid-flow exceptions, and timeout conditions.
6. Distinguish what is guaranteed by a synchronous flow from what requires separate checks when asynchronous processing is involved.

A linearly shaped flow **does not guarantee that every message will always reach the destination**. A Filter can reject a message; a Transformer can throw an error; a Service Activator can return no reply. These early-termination points are precisely what tests must describe.

## 2. Defining the Contract Before Writing Tests

Suppose the system receives string item codes and wants to normalize them before recording:

~~~text
Input:
  payload  = "  sku-7  "
  tenantId = "shop-a"

Step 1. trim                 -> "sku-7"
Step 2. filter !isBlank()    -> keep message
Step 3. add stage            -> stage="validated"
Step 4. uppercase            -> "SKU-7"
Step 5. service activator    -> "accepted:SKU-7"

Output:
  payload  = "accepted:SKU-7"
  tenantId = "shop-a"
  stage    = "validated"
~~~

From this description, create a contract table:

| Checkpoint | Minimal Input | Expected Outcome |
| --- | --- | --- |
| Happy path | Payload \`"  sku-7  "\` and \`tenantId="shop-a"\` | One output, payload \`"accepted:SKU-7"\` |
| Processing order | Payload with whitespace and lowercase letters | \`trim\` then \`uppercase\`, preserving business semantics |
| Business header | \`tenantId="shop-a"\` | Header remains present and unchanged |
| Enriched header | No \`stage\` | Output has \`stage="validated"\` |
| Filter rejects message | Payload \`"   "\` | No success output; discard receives payload trimmed to empty string |
| No duplicate emission | One valid input | Exactly one output |
| Multi-input ordering | Send \`" b "\` then \`" a "\` through synchronous flow | Receive \`"accepted:B"\` then \`"accepted:A"\` |
| Mid-flow failure | An endpoint intentionally throws an exception in test | Exception reaches caller or goes to error channel per execution model |

**Choose discriminating test data.** Payload \`"sku-7"\` does not tell you whether the \`trim\` Transformer ran. Payload \`"  sku-7  "\` proves whitespace trimming. Payload \`"   "\` proves that the **Filter runs after the Transformer**, because after trimming the payload becomes \`""\`.

## 3. Testing Levels for a Flow

| Level | What It Verifies | Appropriate Tools |
| --- | --- | --- |
| Unit test | Normalization functions, filter predicates, business transformations | JUnit, AssertJ; no Spring context needed |
| Flow test | Channel configuration, endpoint order, messages, and headers | \`@SpringJUnitConfig\`, Spring Integration Java DSL, \`QueueChannel\` |
| Boundary/adapter test | Mapping over HTTP, AMQP, Kafka, databases, or external gateways | Test adapters, stubs, Testcontainers, or suitable integration environment |
| End-to-end test | Entire business process across multiple systems | Fewer tests, with clear data and operational conditions |

A unit test can verify that \`"  sku-7  "\` turns into \`"sku-7"\`, but it does not prove the Transformer is wired to the right channel. A flow test executes endpoints inside Spring Integration, catching wiring mistakes, wrong channel names, Filter behavior, headers, and final results. This is the core level of this lesson.

With Spring Boot, the typical dependency set includes:

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

The Java snippets below use **Java 17, Spring Integration 6.x, JUnit 5, and AssertJ**. Use compatible Spring Boot and Spring Integration versions in real projects. The examples are strictly in-memory; no broker or database startup is required.

## 4. Complete Example: Testing a Linear Flow

Create the test file \`src/test/java/example/LinearFlowTest.java\` as follows. The flow uses synchronous channels by default and ends in \`QueueChannel\` instances for easy result collection:

~~~java
package example;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Locale;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(LinearFlowTest.Config.class)
class LinearFlowTest {

    @Autowired
    ApplicationContext context;

    private MessageChannel input() {
        return context.getBean("codes.in", MessageChannel.class);
    }

    private QueueChannel out() {
        return context.getBean("codes.out", QueueChannel.class);
    }

    private QueueChannel discard() {
        return context.getBean("codes.discard", QueueChannel.class);
    }

    private static Message<String> message(String code) {
        return MessageBuilder.withPayload(code)
                .setHeader("tenantId", "shop-a")
                .build();
    }

    @Test
    void valid_input_passes_through_all_steps() {
        assertThat(input().send(message("  sku-7  "))).isTrue();

        Message<?> result = out().receive(1_000);
        assertThat(result).isNotNull();
        assertThat(result.getPayload()).isEqualTo("accepted:SKU-7");
        assertThat(result.getHeaders().get("tenantId")).isEqualTo("shop-a");
        assertThat(result.getHeaders().get("stage")).isEqualTo("validated");

        assertThat(out().receive(0)).isNull();     // No duplicate emission
        assertThat(discard().receive(0)).isNull(); // Not discarded
    }

    @Test
    void blank_input_stops_at_filter_after_trim() {
        assertThat(input().send(message("   "))).isTrue();

        Message<?> rejected = discard().receive(1_000);
        assertThat(rejected).isNotNull();
        assertThat(rejected.getPayload()).isEqualTo("");
        assertThat(rejected.getHeaders().get("tenantId")).isEqualTo("shop-a");
        assertThat(rejected.getHeaders()).doesNotContainKey("stage");
        assertThat(out().receive(0)).isNull();
    }

    @Test
    void synchronous_flow_preserves_send_order() {
        input().send(message(" b "));
        input().send(message(" a "));

        Message<?> first = out().receive(1_000);
        Message<?> second = out().receive(1_000);

        assertThat(first).isNotNull();
        assertThat(second).isNotNull();
        assertThat(first.getPayload()).isEqualTo("accepted:B");
        assertThat(second.getPayload()).isEqualTo("accepted:A");
        assertThat(out().receive(0)).isNull();
    }

    @Configuration
    @EnableIntegration
    static class Config {

        @Bean("codes.out")
        QueueChannel output() {
            return new QueueChannel();
        }

        @Bean("codes.discard")
        QueueChannel discardOutput() {
            return new QueueChannel();
        }

        @Bean
        IntegrationFlow normalizeCodes() {
            return IntegrationFlow.from("codes.in")
                    .transform(String.class, String::trim)
                    .filter(String.class, text -> !text.isBlank(),
                            filter -> filter.discardChannel("codes.discard"))
                    .enrichHeaders(headers ->
                            headers.header("stage", "validated"))
                    .transform(String.class,
                            text -> text.toUpperCase(Locale.ROOT))
                    .handle(String.class,
                            (payload, headers) -> "accepted:" + payload)
                    .channel("codes.out")
                    .get();
        }
    }
}
~~~

The tests produce three distinct outcomes using the same flow:

- **Happy path:** One input yields one output with normalized payload and preserved header.
- **Early stop:** The Filter rejects the empty payload and routes the message to the discard channel; the \`stage\` header is absent because the Header Enricher sits **after** the Filter.
- **Ordering:** Without an executor and with all endpoints along the path running synchronously, two consecutive \`send\` calls produce two results in the exact send order.

Every test drains all messages it sent to the output/discard channels. If parallel test execution is enabled with a shared Spring context, isolate queues/contexts or disable parallelism for tests sharing channels so one test does not accidentally read another test's messages.

### Why Use QueueChannel at the End?

\`DirectChannel\` dispatches messages directly to the registered handler and typically executes on the caller's thread. \`QueueChannel\` buffers messages so tests can pull them via \`receive(timeout)\`. This is a convenient **way to observe outputs**; QueueChannel itself does not spawn a separate worker thread to run preceding steps.

\`receive(1_000)\` bounds the wait time for a message, preventing the test from hanging if wiring is wrong. For the synchronous flow above, \`receive(0)\` confirms that no message remains in the queue **immediately after the send call finishes**. If the flow involves asynchronous processing, this instant check does not prove that a late message will not arrive.

## 5. Proving Step Order, Not Just the Final Result

Some transformations yield the same output even when executed out of order, so asserting only the final output cannot verify that every step ran correctly. Pick test data where order affects the result, or observe an intermediate point.

Example:

~~~text
Input: "   "

Right: trim -> "" -> filter(!isBlank) -> discard payload ""
Wrong: filter(!isBlank) before trim -> discard payload "   "
~~~

If the requirement is to reject whitespace-only strings, testing \`"   "\` must end at the discard channel. Seeing payload \`""\` in discard also proves the \`trim\` Transformer ran **before** the Filter.

Another example, when processing steps are conditional on state:

~~~text
Input: " abc "

1. trim         -> "abc"
2. validate     -> valid
3. uppercase    -> "ABC"
4. prefix       -> "accepted:ABC"
~~~

At each milestone, identify an observable signal: payload changes, header added, message dropped, or handler invoked. Avoid introducing global variables just to log steps in production code; if interaction checks are needed, use a spy at a service boundary or a channel tap in test configuration.

### Observing Mid-Flow Messages with a Wire Tap

Spring Integration provides **Wire Tap**, which sends a copy of a message passing through a channel to an observation channel. You can extend the test flow to inspect the payload right after the first Transformer:

~~~java
@Bean("codes.afterTrim")
QueueChannel afterTrim() {
    return new QueueChannel();
}

// Inside the flow definition:
return IntegrationFlow.from("codes.in")
        .transform(String.class, String::trim)
        .wireTap("codes.afterTrim")
        .filter(String.class, text -> !text.isBlank())
        // ... remaining steps
        .get();
~~~

After sending \`"  sku-7  "\`, receiving from \`codes.afterTrim\` should yield payload \`"sku-7"\`. Wire Tap lets you verify a **boundary** without altering the main transformation logic. This is an illustrative snippet to add to an appropriate flow, not a standalone compilable Java class. When adding a tap in real code, make sure the observation channel is registered and drained in tests; if the tap uses a bounded queue or a handler with side effects, the tap itself can affect test execution.

For multi-step flows, prefer selective observation (e.g., before/after critical stages) rather than tapping every channel. Excessive mid-flow assertions make tests brittle when internal steps are reorganized without changing the external contract.

## 6. Testing Errors at a Mid-Flow Step

A linear flow can terminate with an exception before producing any output. With \`DirectChannel\` and synchronous endpoints, exceptions normally propagate back to the caller of \`send()\` or the Gateway. To test this, build a small flow with a handler that always throws, separate from the normalization flow:

~~~java
@Bean
IntegrationFlow failingFlow() {
    return IntegrationFlow.from("failure.in")
            .transform(String.class, String::trim)
            .handle(String.class, (payload, headers) -> {
                throw new IllegalStateException("simulated failure");
            })
            .get();
}
~~~

In a test whose context registers the flow above:

~~~java
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import org.springframework.messaging.MessagingException;

@Test
void synchronous_failure_propagates_to_sender() {
    MessageChannel failureInput =
            context.getBean("failure.in", MessageChannel.class);

    assertThatThrownBy(() ->
            failureInput.send(
                    MessageBuilder.withPayload(" bad ").build()))
            .isInstanceOf(MessagingException.class)
            .hasRootCauseInstanceOf(IllegalStateException.class);
}
~~~

This snippet checks the **root cause** wrapped inside the messaging exception, avoiding assertions on fragile error message text. Depending on endpoint configuration, the exact wrapper type may differ; verify the actual exception used in your project. If part of the path uses an \`ExecutorChannel\` or an asynchronous adapter, exceptions generally do not reach \`send()\` in the same way: check for an \`ErrorMessage\` via the configured error handler/error channel instead.

Failure scenarios to test include:

| Where Error Occurs | What to Verify |
| --- | --- |
| Transformer | No success output; caller or error handler receives the right cause |
| Filter | Message is intentionally rejected per discard policy, distinct from technical errors |
| Header Enricher | Required headers are not lost during normal processing; exceptions follow the right path if an expression fails |
| Service Activator | A \`null\` reply is not treated as success if business rules require an output |
| External adapter | Connection failures, timeouts, retries, and recovery follow the adapter's contract |

**Distinguish Filter rejection from exceptions:** A Filter returning \`false\` can be a valid business outcome that produces no output on the main branch; do not treat it as a system failure unless business requirements explicitly state so.

## 7. Interactions with Gateway, Retry, and Correlation

A linear flow is often a segment within a larger pipeline. When placed behind a Gateway, wrapped in retry advice, or connected to a Splitter/Aggregator, test assertions need additional coverage.

### Gateway: One Request Must Have a Valid Reply

A Gateway turns a Java call into a request message and awaits or receives a reply as configured. For example, a method \`String normalize(String code)\` should return \`"accepted:SKU-7"\` for input \`"  sku-7  "\`.

If the end of the flow only has a Filter that drops the message without producing a reply, a synchronous Gateway may wait until timeout. Set a finite timeout and verify the result/exception per contract. Do not treat \`send()\` on a request channel returning \`true\` as proof that the Gateway received a reply.

### Retry: Steps May Execute Multiple Times

Suppose a Service Activator calls an external system and fails transiently. With \`RequestHandlerRetryAdvice\`, a single message may cause the handler to be invoked multiple times. Tests should prove:

1. The handler fails on the first attempt and succeeds on the second if retry is configured for two attempts.
2. Exactly one successful result is emitted to the reply channel.
3. The business \`requestId\` header is preserved for tracing and idempotency support.
4. On persistent failure, execution stops at the configured limit and follows the recovery/error path.

Note: retry **may** wrap an individual endpoint or a flow segment depending on configuration. Do not assume every upstream Transformer and Filter re-executes each time the Service Activator retries. Measure attempts right at the boundary where the advice is applied.

### Correlation: When Does It Need Testing?

In a 1-in, 1-out linear flow, correlation is merely a business header if the system needs it. When a Splitter/Aggregator is introduced, the flow changes message counts and uses correlation/sequence metadata for grouping. Verify those specific invariants separately:

~~~text
Before Splitter:    1 message, requestId="r1"
After Splitter:     2 messages, same correlationId="g1"
After Aggregator:   1 message, result only from group "g1"
~~~

When sending two groups \`g1\` and \`g2\` interleaved, the outputs must keep each group's data separate. This is an extension **after** each branch's linear flow already works accurately; there is no need to add \`sequenceNumber\` to every linear test.

## 8. When Is Ordering No Longer Guaranteed?

A key distinction is between **endpoint order in the flow definition** and **completion order across multiple messages**:

~~~mermaid
flowchart TD
    A["DirectChannel\nSynchronous execution"] --> B["Step 1"]
    B --> C["Step 2"]
    C --> D["Output follows sequential send order"]
    E["ExecutorChannel\nMultiple workers"] --> F["Step 1 for A/B"]
    F --> G["Step 2 for A/B"]
    G --> H["Outputs may complete out of order"]
~~~

In a chained synchronous flow, a \`send()\` call normally finishes only after downstream synchronous endpoints finish, or upon error. When inserting an \`ExecutorChannel\`, work can move to another thread. With multiple workers, message B may finish before A, even though both went through Step 1 then Step 2.

Adjust tests to match the contract:

| Architecture | Appropriate Assertion |
| --- | --- |
| Synchronous \`DirectChannel\`, sequential sends | \`containsExactly("A", "B")\` if nothing else alters order |
| Multi-worker executor, no ordering guarantee | Receive expected count and \`containsExactlyInAnyOrder("A", "B")\` |
| Ordering required despite parallel processing | Configure sequence/resequencing or an ordering mechanism, then test ordering per that policy |
| Flow with PollableChannel | Test must trigger the poller or consume via the corresponding mechanism |

Avoid testing asynchronous flows with \`Thread.sleep(500)\` and guessing the system has finished. Use condition waits, \`receive(timeout)\`, and bounded timeouts. When asserting **no message** in an asynchronous flow, use a meaningful observation window or a completion signal showing all tasks have finished.

## 9. Observing Message Count and Path

A standard linear flow expects **one valid input → one output**. However, message counts change when using a Splitter, Aggregator, publish-subscribe, Filter, or an endpoint that intentionally emits multiple outputs.

State the exact rule for the segment under test:

~~~text
Input       -> 1 message
Transformer -> 1 message
Filter      -> 0 if rejected, 1 if accepted
Enricher    -> 1 message when kept
Activator   -> 1 reply when handler returns a value
Output      -> 0 or 1 message (per the rules above)
~~~

On the happy path, after receiving the first output, verify there is no second output if the entire path is synchronous. On the invalid path, verify both that the main output is empty and that the discard channel receives exactly one message. When adding a Router or publish-subscribe, message-count assertions must follow the branching contract rather than mechanically applying a 1 → 1 rule.

To trace branches in production, you can log \`id\`, \`correlationId\`, or \`requestId\` along with the emitting channel. Tests should verify actual data and observation channels rather than relying on log line counts, since log levels and async appenders can change.

## 10. Common Testing Pitfalls

| Error-Prone Test Practice | Consequence | Fix |
| --- | --- | --- |
| Asserting only non-\`null\` output | Fails to catch wrong payload values | Assert exact payload value and type |
| Testing only already-normalized input | Cannot tell if the Transformer ran | Use input that differs from output, e.g. \`"  sku-7  "\` |
| Testing only valid input | Misses disconnected or broken Filter | Add payload \`"   "\` and verify discard |
| Checking only output, ignoring headers | Tenant/correlation can be silently dropped | Assert headers belonging to the business contract |
| Assuming every message produces a reply | Gateway may hang until timeout | Test no-reply cases with a finite timeout |
| Always asserting output order | Tests turn flaky when an executor is added | Assert order only if the architecture guarantees it |
| Checking empty output right after async \`send()\` | Can miss late-arriving messages | Synchronize or use an observation window |
| Sharing queues with leftover data across tests | Tests read wrong messages | Drain queues, isolate contexts, or use correlation |
| Starting broker and database for every test | Slow tests and harder root-cause analysis | Separate unit, flow, and adapter tests |
| Checking logs only | Logs do not fully reflect the contract | Assert outputs, exceptions, and headers |

An effective test suite reports failures where they are easiest to fix: unit tests catch broken predicates; flow tests catch broken wiring; adapter tests catch broken mappings. There is no need to turn every case into a long end-to-end test.

## 11. Practice Exercises

Use the \`LinearFlowTest\` class in section 4 and complete the following exercises.

### Exercise A — Verify Trim → Filter Order

Create inputs \`"   "\` and \`" a "\`. Prove that:

- \`"   "\` is rejected after the trim step, arriving with payload \`""\` on the discard channel.
- \`" a "\` reaches the output with payload \`"accepted:A"\`.
- \`stage\` appears only on messages that passed the Filter.

### Exercise B — Strengthen Header Verification

Attach header \`requestId="req-19"\` to the input. Assert that \`requestId\` remains present on the output, with type String and the exact value. Try adding a Header Enricher with overwrite behavior, then write tests distinguishing **preserve existing value** vs. **overwrite** policies.

### Exercise C — Inject Failure at the Service Activator

Create a flow test whose handler throws \`IllegalStateException\`. With \`DirectChannel\`, assert that the caller receives the error and no success output is produced. Then move the failure point to an asynchronous flow with an error handler and write a test asserting the \`ErrorMessage\` on the error channel.

### Exercise D — Add a Branch After the Linear Flow

Once the normalization flow works, add a Router to separate item codes prefixed with \`VIP-\` from standard codes. Create one message for each branch; check both the chosen channel and the other channel. Compare the new assertions with the linear test to see why the **1 input → 1 main output** rule must be adjusted once branching is introduced.

### Completion Criteria

A linear flow test suite meets the standard when each scenario answers: **where the message starts, what transformations it undergoes, under what condition it stops or continues, and exactly how many outputs with what payload/headers are produced**. At the same time, tests must remain independent, use finite timeouts, and assert ordering only when the configuration actually guarantees it.

From this foundation, you can compose linear segments into multi-branch Router/Filter/Transformer flows, add Gateway, retry, and error channels, or introduce Splitter/Aggregator with correlation while still pinpointing exactly which segment altered message behavior.
