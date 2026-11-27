# Testing Routers Route by Route in Spring Integration

## 1. Objectives of This Lesson

A **Router** is an Enterprise Integration Pattern used to decide which channel a message should proceed to next. In **Spring Integration**, the decision can be based on the payload, one or more headers, a SpEL expression, the payload type, or business logic. Router bugs are easy to miss if you only assert that "a message arrived at the output": a message may go to the wrong branch, get broadcast to an extra branch, be lost when no route matches, or carry corrupted metadata after routing.

The lesson **Testing Routers Route by Route** belongs to the **Pattern Testing** chapter of the **SPRING_INTEGRATION_PATTERN** module. It forms the foundation for building loosely coupled, extensible message flows; after a Router, individual branches can chain Filters, Transformers, Splitters, Aggregators, Gateways, retry, error channels, and correlation steps.

After this lesson, you will be able to:

1. Enumerate the routes to test from the input contract rather than from branches that happened to be coded.
2. Send **one minimal message per route** and verify that the right channel receives it.
3. Assert that **all remaining channels receive no message** for single-destination Routers.
4. Test default routes, missing headers, unknown values, and wrong data types.
5. Distinguish a single-destination Router from a Recipient List or publish-subscribe setup with multiple destinations.
6. Verify payload, headers, exceptions, correlation, and synchronous/asynchronous behavior at the routing boundary.

Most importantly: a route test meets the standard when it proves both that **the message arrived at the right branch** and that **it did not appear on any branch outside the contract**.

## 2. Understanding the Router Contract Before Writing Tests

Suppose an order-processing system routes messages by a \`route\` header:

~~~mermaid
flowchart LR
    IN["orders.in\npayload + headers"] --> R{"Router\nheaders['route']"}
    R -->|VIP| VIP["orders.vip"]
    R -->|STANDARD| STD["orders.standard"]
    R -->|BULK| BULK["orders.bulk"]
    R -->|other or missing| DEF["orders.fallback"]
~~~

In the example, the Router uses the exact \`route\` header value **as sent**:

| \`route\` Value | Expected Channel | Channels That Must Be Empty After Receiving |
| --- | --- | --- |
| \`"VIP"\` | \`orders.vip\` | \`standard\`, \`bulk\`, \`fallback\` |
| \`"STANDARD"\` | \`orders.standard\` | \`vip\`, \`bulk\`, \`fallback\` |
| \`"BULK"\` | \`orders.bulk\` | \`vip\`, \`standard\`, \`fallback\` |
| \`"UNKNOWN"\` | \`orders.fallback\` | \`vip\`, \`standard\`, \`bulk\` |
| Missing \`route\` header | \`orders.fallback\` | \`vip\`, \`standard\`, \`bulk\` |

This is an **example contract**: real projects may choose an exception, a default channel, or discard for invalid routes. Define the policy before writing assertions; never assume every Router has a fallback.

A minimal message for the VIP route:

~~~java
Message<String> message = MessageBuilder.withPayload("order-7")
        .setHeader("route", "VIP")
        .setHeader("tenantId", "shop-a")
        .build();
~~~

Payload \`"order-7"\` lets you verify that the message is not unexpectedly modified; \`route\` drives the routing decision; \`tenantId\` is a business header that must remain intact. Do not fabricate \`sequenceSize\`, \`replyChannel\`, or \`correlationId\` if this Router does not use them.

### Distinguishing Three Layers of the Contract

| Layer | Test Question | Example Assertion |
| --- | --- | --- |
| **Decision** | Which channel does the route value select? | \`VIP\` goes only to \`orders.vip\` |
| **Data** | What payload/headers does the message carry after the Router? | Payload remains \`order-7\`, tenant preserved |
| **Cardinality** | Did the Router emit the exact required number of messages? | One valid input → exactly one output on one channel |

Without the cardinality layer, a test could pass even if the Router sent the same message to both VIP and STANDARD. Without the data layer, a test would miss bugs that drop \`tenantId\` or alter the payload in an endpoint attached to the Router.

## 3. Choosing the Testing Level

### Unit Tests for Classification Logic

If the routing decision is a pure Java function, test it directly:

~~~java
static String selectRoute(int orderAmount) {
    if (orderAmount >= 10_000) {
        return "VIP";
    }
    return "STANDARD";
}

@Test
void amount_at_boundary_goes_to_vip() {
    assertThat(selectRoute(9_999)).isEqualTo("STANDARD");
    assertThat(selectRoute(10_000)).isEqualTo("VIP");
}
~~~

Unit tests catch boundary comparison bugs, but cannot tell whether \`"VIP"\` is actually mapped to \`orders.vip\` in the Spring context. Therefore, a **flow test** is needed to verify actual wiring.

### Flow Tests for Mappings and Output Channels

A flow test builds the Router and channels in memory, sends messages to the input channel, and reads the results. \`QueueChannel\` is useful because it buffers messages for tests to call \`receive(timeout)\`. No HTTP server, Kafka, RabbitMQ, or database is needed when testing a Router in isolation.

The examples use **Java 17, JUnit 5, AssertJ, and Spring Integration Java DSL 6.x**. With Maven and Spring Boot, projects typically include:

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

Use compatible Spring Boot and Spring Integration versions. The snippet below focuses on a synchronously running Router; cases involving executors or message brokers are covered later.

## 4. Complete Example: Testing Each Route

Create the class \`src/test/java/example/RouteByHeaderTest.java\`. We explicitly define four output \`QueueChannel\` beans and a flow that reads the \`route\` header:

~~~java
package example;

import static org.assertj.core.api.Assertions.assertThat;

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

@SpringJUnitConfig(RouteByHeaderTest.Config.class)
class RouteByHeaderTest {

    private static final String[] OUTPUTS = {
            "orders.vip", "orders.standard",
            "orders.bulk", "orders.fallback"
    };

    @Autowired
    ApplicationContext context;

    private MessageChannel input() {
        return context.getBean("orders.in", MessageChannel.class);
    }

    private QueueChannel output(String name) {
        return context.getBean(name, QueueChannel.class);
    }

    private Message<String> request(String orderId, Object route) {
        var builder = MessageBuilder.withPayload(orderId)
                .setHeader("tenantId", "shop-a")
                .setHeader("requestId", "req-7");

        if (route != null) {
            builder.setHeader("route", route);
        }
        return builder.build();
    }

    private void assertOnlyRoute(
            String expectedChannel, String orderId, Object route) {
        Message<String> inputMessage = request(orderId, route);
        assertThat(input().send(inputMessage)).isTrue();

        Message<?> actual = output(expectedChannel).receive(1_000);
        assertThat(actual)
                .as("Expected one message on %s", expectedChannel)
                .isNotNull();
        assertThat(actual.getPayload()).isEqualTo(orderId);
        assertThat(actual.getHeaders().get("tenantId")).isEqualTo("shop-a");
        assertThat(actual.getHeaders().get("requestId")).isEqualTo("req-7");

        if (route == null) {
            assertThat(actual.getHeaders()).doesNotContainKey("route");
        } else {
            assertThat(actual.getHeaders().get("route")).isEqualTo(route);
        }

        // Expected message already consumed; all four queues must now be empty.
        for (String channel : OUTPUTS) {
            assertThat(output(channel).receive(0))
                    .as("Unexpected extra message on %s", channel)
                    .isNull();
        }
    }

    @Test
    void vip_goes_only_to_vip_channel() {
        assertOnlyRoute("orders.vip", "order-1", "VIP");
    }

    @Test
    void standard_goes_only_to_standard_channel() {
        assertOnlyRoute("orders.standard", "order-2", "STANDARD");
    }

    @Test
    void bulk_goes_only_to_bulk_channel() {
        assertOnlyRoute("orders.bulk", "order-3", "BULK");
    }

    @Test
    void unknown_route_uses_fallback() {
        assertOnlyRoute("orders.fallback", "order-4", "UNKNOWN");
    }

    @Test
    void missing_header_uses_fallback() {
        assertOnlyRoute("orders.fallback", "order-5", null);
    }

    @Test
    void wrong_type_is_not_treated_as_known_route() {
        assertOnlyRoute("orders.fallback", "order-6", 42);
    }

    @Configuration
    @EnableIntegration
    static class Config {

        @Bean("orders.vip")
        QueueChannel vip() {
            return new QueueChannel();
        }

        @Bean("orders.standard")
        QueueChannel standard() {
            return new QueueChannel();
        }

        @Bean("orders.bulk")
        QueueChannel bulk() {
            return new QueueChannel();
        }

        @Bean("orders.fallback")
        QueueChannel fallback() {
            return new QueueChannel();
        }

        @Bean
        IntegrationFlow routeOrders() {
            return IntegrationFlow.from("orders.in")
                    .route("headers['route']", spec -> spec
                            .channelMapping("VIP", "orders.vip")
                            .channelMapping("STANDARD", "orders.standard")
                            .channelMapping("BULK", "orders.bulk")
                            .defaultOutputChannel("orders.fallback"))
                    .get();
        }
    }
}
~~~

**Notable points in the example:**

- The three valid routes have three independent tests. If \`EXPRESS\` is added later, update the contract table, add the channel, and add a test for that route.
- \`"UNKNOWN"\`, missing header, and integer \`42\` serve as control branches. They prove the fallback does not corrupt input data.
- \`assertOnlyRoute\` reads exactly one output and then checks that all four queues are empty, catching both misrouted messages and duplicate dispatches in a synchronous flow.
- Payload and the \`tenantId\` and \`requestId\` headers are verified because they belong to the contract; the test does not compare framework-generated \`id\` or \`timestamp\` headers to exact values.
- Each test sends only one input at a time. Every test must consume all messages it produced so it does not depend on JUnit execution order.

**Note on fallback policies:** Spring Integration supports different channel-resolution modes; whether the resulting value is used directly as a channel name, mapped via \`channelMapping\`, or sent to a default channel depends on Router configuration. The example intentionally maps recognized values and specifies a default channel. If the system must *accept only declared routes*, also verify the channel-key fallback options for your Spring Integration version and ensure no unlisted channel is accidentally selected.

## 5. Testing Every Route Does Not Mean Testing Only the Happy Path

A Router with three business branches often needs more than three tests. Testing **one valid value per branch** is the minimum to cover mappings; afterward, add boundary cases for the route selector.

| Scenario | Sample Input | Question to Answer |
| --- | --- | --- |
| Valid VIP route | \`route="VIP"\` | Does only VIP receive the message? |
| Valid STANDARD route | \`route="STANDARD"\` | Was it accidentally sent to VIP? |
| Valid BULK route | \`route="BULK"\` | Is there a duplicate message elsewhere? |
| Unmatched mapping | \`route="UNKNOWN"\` | Default, exception, or discard? |
| Missing header | No \`route\` | Which policy applies? |
| Wrong type | \`route=42\` | Is it coerced or misrouted? |
| Wrong casing | \`route="vip"\` | Does the system normalize case? |
| Leading/trailing spaces | \`route=" VIP "\` | Is there a trim step or is it invalid? |
| Empty value | \`route=""\` | Default, validation error, or discard? |
| Valid route but bad payload | \`route="VIP"\`, invalid payload | Is the Router responsible for validation, or a Filter after the Router? |

There is no need to build every case if it is unrelated to requirements. However, the **precedence between validation and routing** must be explicitly verified. For example, if header \`" vip "\` must become \`"VIP"\`, use a Transformer or Header Enricher before the Router to normalize it, then test both raw input and result. Never assume SpEL or \`channelMapping\` trims and uppercases automatically.

### Turning a Route Table into a Parameterized Test Set

As the number of routes grows, replace repetitive tests with \`@ParameterizedTest\`:

~~~java
@ParameterizedTest
@CsvSource({
    "VIP, orders.vip",
    "STANDARD, orders.standard",
    "BULK, orders.bulk",
    "UNKNOWN, orders.fallback"
})
void routes_to_expected_channel(String route, String channel) {
    assertOnlyRoute(channel, "order-x", route);
}
~~~

This snippet belongs to the same \`RouteByHeaderTest\` class and requires importing \`org.junit.jupiter.params.ParameterizedTest\` and \`org.junit.jupiter.params.provider.CsvSource\`. With a compatible \`spring-boot-starter-test\` version, JUnit Jupiter Params is usually already available. Missing-header cases should be tested separately because representing empty strings vs. \`null\` in CSV requires explicit rules; do not accidentally turn "missing header" into an empty-string header.

Parameterized tests are especially effective when routes share the same policy. If each route requires different payload content or has distinct side effects, keep dedicated tests that clearly describe each branch's behavior.

## 6. Testing Policies for Invalid Routes

A **default channel** is only one possible Router policy. Pick the behavior specified by the product and write clear tests:

### Case A — Routing to the Default Channel

The scenario in the example: \`route="UNKNOWN"\` sends the message intact to \`orders.fallback\`. The test must assert that fallback receives exactly one message and all business channels remain empty.

### Case B — Failing Explicitly

If an unknown route value must be rejected, configure the Router without a default output and require route resolution. On a synchronous path, an unresolvable route can throw a \`MessagingException\`:

~~~java
assertThatThrownBy(() ->
        input.send(MessageBuilder.withPayload("order-x")
                .setHeader("route", "UNKNOWN")
                .build()))
        .isInstanceOf(MessagingException.class);
~~~

This is an **assertion skeleton**, assuming \`input\` belongs to a separate flow configured to reject invalid routes. You must confirm the exact Router policy, including default channel, route-key-as-channel-name behavior, and \`resolutionRequired\`. If there is a dedicated error-handling branch, also verify the root cause exception and ensure no success output is emitted.

### Case C — Intentionally Discarding Messages

Some flows intentionally drop messages without a valid route. In that case, verify that the message appears on no output channel and that discard tracking/counters match requirements. Never treat "no output" as proof of success when you do not know whether the Router *intentionally discarded* the message or failed due to miswiring.

### Distinguishing a Valid Route with No Subscriber

A valid route key does not mean the target channel is ready to receive. With \`DirectChannel\`, sending to a channel without subscribers can throw \`MessageDeliveryException\` on \`send()\`; with \`QueueChannel\`, the message may sit queued without further processing. This is a **delivery and wiring** concern, separate from route-selection logic. Flow tests should verify the exact type of target channel declared.

## 7. Testing Routers Based on Payload or Expressions

Not every Router reads a \`route\` header. Below are common routing strategies and the minimal data to test them:

| Router Type | Criterion | Minimal Input |
| --- | --- | --- |
| Header-value Router | \`headers['route']\` | Two messages with different \`route\`, same payload |
| Payload-value Router | Payload \`"VIP"\`/\`"STANDARD"\` | Two payloads from the two groups |
| Payload-type Router | Java class of the payload | One \`String\` and one DTO |
| Expression Router | SpEL returning mapping key | Inputs on both sides of the condition |
| Method Router | Java method computing route | Unit test method + mapping test |

Example when routing is computed from the payload:

~~~java
@Bean
IntegrationFlow routeByAmount() {
    return IntegrationFlow.from("amount.in")
            .route(Integer.class,
                    amount -> amount >= 10_000 ? "VIP" : "STANDARD",
                    spec -> spec
                            .channelMapping("VIP", "amount.vip")
                            .channelMapping("STANDARD", "amount.standard"))
            .get();
}
~~~

This is an illustrative configuration snippet assuming \`amount.vip\` and \`amount.standard\` are already registered. A minimal test set should send \`9_999\` and \`10_000\`, then verify the branches below and at the threshold. Picking two values on the same side of the threshold fails to prove the boundary comparison.

If an expression uses multiple headers (e.g., \`tenantId\` and \`priority\`), build a clear truth table before writing tests. With three Boolean conditions, do not test only one "all true" message, because that test fails to verify the branches where conditions evaluate to false.

## 8. Testing Payload and Headers After Routing

A Router normally picks a message's destination; payload transformations, filtering, or header enrichment are typically the responsibility of endpoints before or after the Router. Tests should catch boundary bugs:

~~~text
Input:
  payload     = "order-7"
  route       = "VIP"
  tenantId    = "shop-a"
  requestId   = "req-7"

After Router:
  expected channel = orders.vip
  payload          = "order-7"
  route            = "VIP"
  tenantId         = "shop-a"
  requestId        = "req-7"
~~~

Do not compare the entire input and output header maps, because the framework may add or update control metadata (\`id\`, \`timestamp\`, reply/error channel depending on processing points). Instead, assert **the headers belonging to the business contract**. If the module uses tracing, verify that \`requestId\` or the correlation ID stays intact across the Router so operators can trace the same request.

### Route Before or After a Transformer?

Suppose an incoming message has \`route=" vip "\`. If business rules allow normalizing the route, a sensible pipeline is:

~~~mermaid
flowchart LR
    IN["route=' vip '"] --> T["Header Enricher\ntrim + uppercase"]
    T --> R{"Router"}
    R -->|"VIP"| V["VIP channel"]
    R -->|"other"| F["Fallback / Error"]
~~~

Minimal tests include one message needing normalization and one non-matching message. Verify the output hits the right channel, the header is normalized, and the payload remains unchanged. If a Transformer only operates on the payload, it **does not automatically normalize headers**; you need an endpoint that explicitly modifies headers or a route selector that handles it explicitly.

## 9. When a Router Selects Multiple Destinations

Previous examples used the contract **one message goes to exactly one channel**. However, Spring Integration also has \`RecipientListRouter\`, \`PublishSubscribeChannel\`, and multi-recipient flows. In those cases, asserting "every other branch is empty" is wrong because the message is **intentionally fanned out to multiple targets**.

Example contract:

~~~text
Input:
  payload = "order-7"
  audit = true

Expected recipients:
  order.processing  -> 1 message
  order.audit       -> 1 message
  order.alert       -> 0 messages
~~~

In this case, tests must:

1. Assert that each **selected** channel receives exactly one message.
2. Assert that **unselected** channels receive no message.
3. Verify that payload/headers are preserved or updated in line with copy and sequence policies.
4. Test error handling when one recipient fails: does the Router stop, continue sending, or ignore the error depending on configuration?

If \`applySequence\` is enabled, \`sequenceNumber\` and \`sequenceSize\` metadata may be added to message copies going to different recipients. Assert sequence headers only when enabled and their meaning in the flow is defined; never assume every Router generates sequence metadata.

## 10. Synchronous, Asynchronous, and Testing for Absence of Messages

The example in section 4 uses synchronous endpoints before \`QueueChannel\`. Once \`send()\` returns, \`receive(0)\` immediately confirms the state of the output queues. However, if an \`ExecutorChannel\` or broker sits along the path, a branch may receive its message late.

| Model | Appropriate Observation Approach | Things to Watch Out For |
| --- | --- | --- |
| Synchronous \`DirectChannel\` | Send one message, read chosen channel, check other queues empty | Check only after \`send()\` completes |
| Asynchronous \`ExecutorChannel\` | \`receive(timeout)\` on expected branch; observe unselected branches within an appropriate window | Immediate \`receive(0)\` does not prove no late message arrives |
| Message broker | Test adapter with timeout, unique correlation ID, and test queue cleanup | Messages may be redelivered or left over from a prior run |
| Multi-recipient Router | Wait for all designated outputs | Do not apply the "exactly one total output" rule |

Avoid relying on \`Thread.sleep(500)\` to infer that tasks have completed. Use completion signals, an appropriate barrier/test latch, or a well-defined bounded observation window. If the project requires at-most-once delivery without duplicates in an environment with retry, test both side effects and idempotency mechanisms, because a message can still be reprocessed even when Router logic is sound.

### Isolating Messages Between Tests

Each test should consume all its own results. If multiple tests share a Spring context and run in parallel, a shared \`QueueChannel\` can cause test A to read test B's message. Fix this by isolating contexts/channels, using unique request IDs, or running tests that share queues sequentially. Never name channels in a way that depends on leftover state from a previous test.

## 11. Routers in Multi-Pattern Flows

In practice, a Router is a decision gate leading into independent processing pipelines:

~~~mermaid
flowchart TD
    IN["Gateway / Input"] --> R{"Router"}
    R -->|VIP| T["Transformer"]
    T --> A["Service Activator"]
    R -->|STANDARD| F{"Filter"}
    F -->|valid| S["Splitter"]
    S --> G["Aggregator"]
    F -->|rejected| D["Discard"]
    R -->|UNKNOWN| E["Fallback / Error"]
    A --> O1["VIP Reply"]
    G --> O2["Standard Result"]
~~~

To test effectively, split checks by boundary:

- **Router test:** Assert only that the message reaches the right branch, payload/headers are not altered outside the contract, and output count is right.
- **Branch test:** Independently test each branch's Transformer, Filter, Splitter/Aggregator, correlation, and error conditions.
- **Gateway/integration test:** Verify the complete request/reply, timeout, retry, and error handling against the end-to-end contract.

An end-to-end test failing on the final result could be caused by the Router, Filter, or Aggregator. Having dedicated Router tests per route lets you quickly rule out mapping errors and focus on the failing branch.

### How Do Retry and Error Channels Affect Routing?

A Router may route properly while a downstream handler throws an exception. On a synchronous path, the error may propagate to the caller; on an asynchronous path with an error handler, the error may reach the error channel. Therefore:

1. Test the Router independently with in-memory receiving channels to verify the exact selected route.
2. Test each branch's handler for exceptions, retry, and recovery.
3. Combine tests on key paths to ensure \`requestId\`/correlation ID traces a message across multiple endpoints.

Do not treat \`send()\` returning \`true\` as proof that business processing succeeded when downstream execution is asynchronous. It only confirms that the send operation was accepted by the channel according to that channel's semantics.

## 12. Practice Exercises and Completion Criteria

### Exercise A — Add the EXPRESS Route

Starting from the example in section 4, add channel \`orders.express\`, mapping \`"EXPRESS"\`, and a test for \`"EXPRESS"\`. Extend the \`OUTPUTS\` array in the helper to verify every unselected channel remains empty. After adding the route, existing tests must continue to pass because old mappings remain unchanged.

### Exercise B — Normalize the Header

Allow \`route=" vip "\` to be handled as \`VIP\`. Add a normalization step before the Router and write tests verifying:

- Input \`" vip "\` routes to VIP after normalization.
- The \`route\` header on the output matches the new contract.
- Input \`"unknown"\` still routes to the default channel.
- Invalid messages do not accidentally fall into VIP.

### Exercise C — Reject Invalid Routes

Replace the fallback with a policy that throws an error for undeclared routes. Send \`"UNKNOWN"\` and a message without \`route\`. Assert the appropriate synchronous exception, zero success outputs, and a root cause clear enough for diagnostics. If using an asynchronous error channel, adjust the assertions to match that model.

### Exercise D — Test a Recipient List

Suppose input \`audit=true\` must go to both \`orders.process\` and \`orders.audit\`. Write a test confirming that **both recipients** receive exactly one message; when \`audit=false\`, only \`orders.process\` receives it. Check that no stray messages appear in any remaining channels.

### Self-Assessment Criteria

A route-by-route Router test suite meets the standard when:

1. Every valid route value has an explicit test or data-table case.
2. Invalid routes, missing headers, and boundary cases follow the defined policy.
3. Each test accurately checks **selected outputs, unselected outputs, and message count**.
4. Payload and essential business headers are preserved or modified per contract.
5. Timing and ordering assertions match synchronous vs. asynchronous channels.
6. Tests can run independently; Router failures are distinguishable from downstream endpoint failures.

Once every route is verified with a minimal message and proper control cases, you can introduce additional patterns while retaining full control over message paths, business data, and observability across the entire Spring Integration flow.
