# Expression-Based Router

## 1. The Problem: Deciding the Path from Message Data

In an order-intake system, domestic orders go to the Vietnam processing team, international orders go to customs inspection, and high-risk orders must undergo manual review. If every handler writes its own `if/else` to choose the next step, routing logic becomes scattered everywhere, hard to test, and hard to trace.

**Message Router** is a pattern in **Enterprise Integration Patterns (EIP)**: it receives a message from a channel, evaluates a rule, and forwards the message to the appropriate destination channel. In Spring Integration, an **expression-based router** uses **Spring Expression Language (SpEL)** to compute a *routing key* or destination from payload/headers. As a result, branch selection rules are described centrally at the Router endpoint, while downstream consumers only handle their own branch's business logic.

This lesson belongs to the **Message router** chapter of the **SPRING_INTEGRATION_PATTERN** module. It connects directly to the goal of building loosely coupled, extensible message flows using **Gateway, Filter, Transformer, Router, Splitter, Aggregator, retry, error channel, and correlation**, while keeping every path testable.

After this lesson, you will be able to:

1. Distinguish *routing expression*, *routing key*, *channel mapping*, and *default output channel*.
2. Write SpEL expressions reading payload properties and headers, including ternary conditions.
3. Configure an Expression Router in Spring Integration Java DSL.
4. Handle missing data, unmapped branches, and expression evaluation errors.
5. Test main branches, fallback, errors, and correlation traceability.

## 2. Where Does the Router Stand in a Message Flow?

~~~mermaid
flowchart LR
    A["Gateway: OrderPlaced"] --> IN["orders.in"]
    IN --> T["Transformer: normalize"]
    T --> R{"Expression Router<br/>payload.market()"}
    R -->|"VN"| VN["orders.vn"]
    R -->|"US"| US["orders.us"]
    R -->|"Other"| O["orders.other"]
    VN --> H1["Domestic consumer"]
    US --> H2["US consumer"]
    O --> H3["Further classification consumer"]
~~~

At the Router, an incoming message is evaluated to determine its *recipient destination*. The Router forwards the message per channel configuration; concrete business steps occur **after the Router**. It does not transform payloads itself, does not guarantee durable storage, and does not automatically apply retry policies for destination handlers.

For example: a message with `market = "VN"` yields key `VN`; mapping `VN → orders.vn` determines the receiving channel. A message with `market = "FR"` does not match declared mappings and is routed to `orders.other` if fallback is configured.

| Concept | Meaning | Example |
|---|---|---|
| **Input message** | Message received by the Router from the input channel | `Message<OrderPlaced>` |
| **Routing expression** | SpEL expression computing the decision value | `payload.market()` |
| **Routing key** | Result of evaluating the expression | `"VN"` |
| **Channel mapping** | Maps a key to a destination channel name | `"VN" → "orders.vn"` |
| **Default output channel** | Fallback destination when no destination is resolved from the key | `"orders.other"` |
| **Downstream consumer** | Endpoint processing messages on the selected channel | Handler processing VN orders |

A helpful rule of thumb: **the expression decides "where to go"; the handler decides "what to do"**. If risk classification logic is complex, let a pure Java service compute the risk level first, and have the Router simply read that result to route.

## 3. Spring Expression Language in a Router

SpEL can access message data using familiar objects:

- `payload`: business content of the message.
- `headers`: metadata such as source code, priority, or correlation ID.
- Operators such as `==`, `!=`, `>`, `and`, `or`, and the ternary conditional operator `condition ? a : b`.
- Methods belonging to the payload object, when permitted and matching the runtime type.

Typical expressions:

| SpEL Expression | Expected Value | When to Use |
|---|---|---|
| `payload.market()` | `"VN"` | Payload is a Java record with method `market()` |
| `payload.region` | `"VN"` | Payload is a bean with a readable property, e.g. `getRegion()` |
| `headers['tenantTier']` | `"PREMIUM"` | Decision based on a controlled header |
| `headers['riskLevel'] == 'HIGH' ? 'REVIEW' : 'AUTO'` | `"REVIEW"` or `"AUTO"` | Conditional key selection |
| `payload.quantity() > 100 ? 'BULK' : 'STANDARD'` | `"BULK"` or `"STANDARD"` | Classification by quantitative property |

**Note on Java records:** when using `record OrderPlaced(String market)`, the generated accessor method is `market()`. The expression `payload.market()` invokes this method directly and avoids relying on how different framework versions expose record accessors as bean properties.

**Expressions are evaluated at runtime**, not type-checked by Java at compile time. If the runtime payload lacks the called method, or a property is `null`, evaluation can throw an exception. Therefore, the ingress boundary should validate schema/types and normalize data before the Router.

From a design standpoint, keep expressions **short, purely computational, and side-effect free**. Do not call databases, HTTP endpoints, or update state inside SpEL just to pick a branch; those operations belong in separate handlers/services where timeouts, transactions, and retries are easier to manage.

## 4. Example: Market-Based Router in Java DSL

Consider an order message:

~~~java
record OrderPlaced(
    String orderId,
    String market,
    int quantity
) {}
~~~

We will filter invalid data, normalize `market`, and then evaluate `payload.market()`. Channel/consumer beans are given explicit names to make the flow observable.

~~~java
@Configuration
@EnableIntegration
class OrderRoutingFlows {

    @Bean
    IntegrationFlow classifyOrders() {
        return IntegrationFlow.from("orders.in")
            .filter(OrderPlaced.class,
                order -> order.orderId() != null
                    && !order.orderId().isBlank()
                    && order.market() != null
                    && !order.market().isBlank()
                    && order.quantity() > 0,
                filter -> filter.discardChannel("orders.invalid"))
            .transform(OrderPlaced.class,
                order -> new OrderPlaced(
                    order.orderId(),
                    order.market().trim().toUpperCase(Locale.ROOT),
                    order.quantity()))
            .route("payload.market()",
                router -> router
                    .channelMapping("VN", "orders.vn")
                    .channelMapping("US", "orders.us")
                    .defaultOutputChannel("orders.other"))
            .get();
    }

    @Bean
    IntegrationFlow vnOrders() {
        return IntegrationFlow.from("orders.vn")
            .handle(m -> System.out.println("VN: " + m.getPayload()))
            .get();
    }

    @Bean
    IntegrationFlow usOrders() {
        return IntegrationFlow.from("orders.us")
            .handle(m -> System.out.println("US: " + m.getPayload()))
            .get();
    }

    @Bean
    IntegrationFlow otherOrders() {
        return IntegrationFlow.from("orders.other")
            .handle(m -> System.out.println("OTHER: " + m.getPayload()))
            .get();
    }

    @Bean
    IntegrationFlow invalidOrders() {
        return IntegrationFlow.from("orders.invalid")
            .handle(m -> System.out.println("INVALID: " + m.getPayload()))
            .get();
    }
}
~~~

The example uses **Spring Integration Java DSL** and a Java record (Java 17+); Java/Spring imports are omitted to focus on the flow. `IntegrationFlow.from("orders.in")` creates the message intake path by channel name; the other flows attach consumers to each destination channel. When integrating into an application, place these beans in scanned Spring configuration with the corresponding Spring Integration dependencies.

Data trace:

| Input | After Filter/Transformer | Routing Key | Receiving Channel |
|---|---|---|---|
| `("O-1", " vn ", 2)` | `market="VN"` | `VN` | `orders.vn` |
| `("O-2", "US", 1)` | `market="US"` | `US` | `orders.us` |
| `("O-3", "DE", 3)` | `market="DE"` | `DE` | `orders.other` |
| `("O-4", "", 2)` | Rejected by Filter | Not evaluated | `orders.invalid` |
| `("O-5", "VN", 0)` | Rejected by Filter | Not evaluated | `orders.invalid` |

**Filter discard differs from Router fallback.** `orders.invalid` receives invalid data **before** evaluating the expression; `orders.other` receives potentially valid data that does not yet have a dedicated processing route. Separating these makes logs, alerts, and retry rules meaningful.

The example prints to the console for observation. In a real system, each branch can invoke a service, publish to an outbound adapter, or run a separate workflow. Guard against handlers applying side effects multiple times if messages are retried/redelivered.

## 5. Header-Based Router Instead of Payload

A routing decision can depend on metadata, such as customer tier or priority already verified by the application. In that case, the expression reads headers:

~~~java
@Bean
IntegrationFlow priorityRoutingFlow() {
    return IntegrationFlow.from("priority.in")
        .route("headers['riskLevel'] == 'HIGH' ? 'REVIEW' : 'AUTO'",
            r -> r.channelMapping("REVIEW", "orders.review")
                  .channelMapping("AUTO", "orders.automatic")
                  .defaultOutputChannel("orders.unknown"))
        .get();
}
~~~

This example selects `orders.review` when the `riskLevel` header is `"HIGH"` and `orders.automatic` for everything else. **A missing header also routes to `AUTO`** because the condition evaluates to false rather than hitting the default output. That can be dangerous if `riskLevel` has not been determined.

When missing headers must be handled separately, write the condition explicitly:

~~~java
.route(
    "headers['riskLevel'] == null ? 'UNKNOWN' : headers['riskLevel']",
    r -> r.channelMapping("HIGH", "orders.review")
          .channelMapping("LOW", "orders.automatic")
          .defaultOutputChannel("orders.unknown"))
~~~

The second snippet is **a replacement flow step** for the Router above; do not chain the two Routers back-to-back in the same example without defining the intended processing boundary. With a `null` header, the expression returns `UNKNOWN`, which has no dedicated mapping, so the Router forwards to `orders.unknown`.

Note: headers can originate from external systems and be untrusted. Never let raw header values freely dictate bean/channel names, especially channels for sensitive operations. Validate the source and allowed values, then use explicit mappings for supported branches.

## 6. How Do Routing Key, Channel Mapping, and Fallback Work?

Logical workflow of an Expression Router:

~~~mermaid
flowchart TD
    M["Message arrives at Router"] --> E["Evaluate SpEL"]
    E -->|Valid result| K["Routing key"]
    E -->|Evaluation error| EX["Exception / error handling path"]
    K --> MAP{"Matching channel mapping / destination?"}
    MAP -->|Yes| OUT["Send to selected channel"]
    MAP -->|No| DEF{"Default output channel configured?"}
    DEF -->|Yes| FALL["Send to fallback"]
    DEF -->|No| NO["No valid route: handle per router config"]
~~~

**Three situations to distinguish:**

1. **Key has a mapping**: e.g., `VN` maps to `orders.vn`.
2. **Key has no matching mapping**: uses `defaultOutputChannel` if declared; do not assume unknown values are safely ignored by default.
3. **Expression throws an exception**: the failure occurs **before the mapping lookup**. `defaultOutputChannel` is not a `catch` mechanism for syntax errors, missing methods, type conversion errors, or exceptions thrown by invoked logic.

If no fallback is configured, behavior when no channel is resolved depends on the router's required-resolution options and channel-name resolution settings. For critical business flows, **configure an explicit fallback branch or error-reporting mechanism** rather than allowing messages to disappear unobserved.

The fallback branch should also have bounded responsibilities: `orders.other` can record events for further classification, whereas `orders.invalid` is for schema or core business-rule failures. Do not use fallback as a hiding place for all errors.

## 7. Conditional Expressions: Concise Yet Expressive of Business Intent

SpEL supports the ternary conditional operator:

~~~text
headers['tenantTier'] == 'VIP' ? 'PRIORITY' : 'STANDARD'
payload.quantity() >= 100 ? 'BULK' : 'NORMAL'
headers['market'] == null ? 'UNKNOWN' : headers['market']
~~~

In Java DSL, you can route by quantity:

~~~java
.route(
    "payload.quantity() >= 100 ? 'BULK' : 'NORMAL'",
    r -> r.channelMapping("BULK", "orders.bulk")
          .channelMapping("NORMAL", "orders.standard"))
~~~

This example is a **standalone snippet** using a validated and normalized `OrderPlaced` payload. The condition `quantity >= 100` may be a simple classification rule; if actual thresholds depend on customer contracts, time, or inventory data, compute an `OrderCategory` in a pure Java business step and route on that computed category.

Expressions growing longer are a sign to move the decision into a testable function:

~~~java
record RoutedOrder(
    String orderId,
    String market,
    String processingLane
) {}

// Service computes business category per dedicated rules:
String lane = routingPolicy.determineLane(order);

// Router simply reads the category published on the payload:
// .route("payload.processingLane()", spec -> ...)
~~~

This keeps **Pipes and Filters** independent: Transformer/Service Activator computes classification, Router selects the channel, and the target handler performs the action. Changing business rules does not force complex logic into SpEL.

## 8. Comparing Expression Router with Other Routing Approaches

Spring Integration provides several ways to express routing decisions. Choose based on complexity and where rules live:

| Mechanism | Criterion | When to Use |
|---|---|---|
| **ExpressionEvaluatingRouter** | SpEL expression on payload/headers | Rules reading properties or concise conditions |
| **HeaderValueRouter** | Value of a designated header | Only need to route by one header, without complex SpEL |
| **PayloadTypeRouter** | Runtime type of payload | Each event class goes to its corresponding flow |
| **MethodInvokingRouter** | Result of an invoked Java method | Routing rule requires unit-testable Java code |
| **RecipientListRouter** | Conditional list of recipients | Same message needs to go to multiple destinations per policy |

An **expression-based router** typically evaluates to a branch-selection key; it fits questions like "VN or US?". If you need to send one message concurrently to multiple subscribers, evaluate **Recipient List Router** or an appropriate publish-subscribe mechanism. Do not assume an expression returning a comma-separated string will automatically split into multiple channel names.

**Router does not replace Filter.** Filter solves "may this message continue?". Router solves "which branch should a valid message take?". **Transformer does not replace Router**: Transformer changes payload/headers; Router chooses the path. Combining all three patterns keeps flows clear and testable.

## 9. Payload Types and Null Handling

An expression depends on the data shape at **the exact moment** the router receives the message. If a Transformer converts `OrderPlaced` into a `Map`, the expression `payload.market()` will no longer work. Thus, the Router's input needs a well-defined contract.

Example:

~~~java
record OrderPlaced(String orderId, String market, int quantity) {}

Message<OrderPlaced> msg = MessageBuilder
    .withPayload(new OrderPlaced("O-21", "VN", 3))
    .setHeader("correlationId", "O-21")
    .build();
~~~

With this type:

- `payload.market()` calls the record accessor method.
- `headers['correlationId']` retrieves the corresponding header.
- `payload['market']` must **not** be assumed equivalent syntax across all payload types: map/index access syntax and getter invocation work differently.

When an expression uses an optional header, distinguish **`null`**, empty strings, and unsupported values. For instance, `headers['riskLevel'] == null` only catches missing/`null`; an empty string `""` needs a validation step or separate condition. For data arriving from HTTP/brokers, perform decoding, validation, and normalization at ingress so the Router receives a stable structure.

### Why Never Build Expressions from User Input?

**Never concatenate untrusted input into a SpEL expression and evaluate it.** SpEL is an expression language capable of accessing properties and methods; an expression constructed from user input can cause errors or unintended execution privileges if unrestricted. Keep the expression under application control as static configuration, and treat user data strictly as **values read** from payload/headers and matched against a key allowlist.

In multi-tenant setups, also avoid building channel names via string concatenation like `"orders." + tenantId` to send to arbitrary matching beans. Map against an explicit allowlist of tenants/routes, with an unknown branch and alerts on unexpected values.

## 10. Does a Router Modify Messages or Correlation IDs?

A Router primarily determines **the destination channel**. It is not a Transformer, so the forwarded message's payload normally retains the value received by the Router. Tracing and correlation headers can also be preserved depending on how flows/adapters pass messages.

However, **do not blindly rely on header preservation** when Transformers, Gateways, broker adapters, or serializers sit between steps: header mapping, filtering, and constructing new messages can alter metadata. In a **Splitter → Router → Aggregator** flow, specifically verify `correlationId`, `sequenceNumber`, and `sequenceSize` so parts of the same order are grouped accurately.

~~~mermaid
flowchart LR
    S["Splitter: order O-10"] --> A["Line 1 + correlation O-10"]
    S --> B["Line 2 + correlation O-10"]
    A --> R{"Router: item type"}
    B --> R
    R --> X["Regular item processing"]
    R --> Y["Special item processing"]
    X --> G["Aggregator by correlation"]
    Y --> G
    G --> RES["OrderSummary O-10"]
~~~

In the example, the Router can send each line item to a different branch; the Aggregator still needs correlation metadata to know they belong to the same order. If one branch stalls, errors out, or is dropped, design **timeouts, release strategies, and handling for incomplete groups** rather than waiting forever.

When a message is redelivered via a broker, the Spring `Message`'s `messageId` may change. To prevent duplicate processing, use a stable business identifier or event ID defined in the contract, rather than treating each message's fresh ID as a uniqueness guarantee.

## 11. Synchronous, Asynchronous, and Backpressure Behavior

The Router itself does not dictate whether the flow runs synchronously or asynchronously. That depends on input/output channels and downstream endpoints:

| Channel After Router | Typical Execution | What to Observe |
|---|---|---|
| `DirectChannel` | Consumer runs on sender thread via synchronous dispatch | Does a slow handler throttle the producer? |
| `ExecutorChannel` | Work is handed off to an executor | Full executor queue, async errors, completion order |
| `QueueChannel` | Message is placed in a queue waiting for a polling consumer | Backlog, capacity, send timeout, data loss on restart |
| Outbound adapter to broker | Message is sent to an external system | Ack/publish confirm, retries, durability, delivery semantics |

Suppose the Router sends 90% of messages into a slow processing branch. Even if the expression evaluates rapidly, that branch's queue and workers can still saturate. Therefore, measure **message share per route, throughput, latency, errors, backlog, and message age**.

Avoid heavy computations or external resource calls inside routing expressions. Routing rules should never become a shared bottleneck for every message.

## 12. Error Channel, Fallback, and Retry: Three Distinct Responsibilities

Do not collapse every situation into "send to default":

| Situation | Appropriate Mechanism | Example |
|---|---|---|
| Message violates business/contract data before Router | Filter discard or validation error | `quantity <= 0` |
| Valid message without a dedicated branch | Router default output channel | `market="DE"` when only VN/US are supported |
| SpEL expression fails to evaluate | Flow exception/error handling | Wrong payload type, calling method on `null` |
| Destination channel hits transient failure | Retry by error type and execution boundary | Handler calling inventory service times out |
| Message exhausted retries | Error workflow, DLQ/quarantine, or manual handling | Broker redelivery exceeds limit |

**Default output channel does not catch exceptions.** If `payload.market()` throws an exception, the framework does not treat that error as key `OTHER`. In synchronous `DirectChannel` flows, exceptions can propagate back to the caller/Gateway; in asynchronous flows, pollers or adapters have their own error-channel/error-handler policies.

Retries belong to **transient** failures. Retrying an expression that fails due to a missing method or schema-invalid payload rarely fixes the root cause. If a handler already produced side effects before failing, retrying may repeat the business action; ensure **idempotency**, bounded attempts, and explicit backoff.

Design separate metrics for fallbacks and exceptions: high volume into `orders.other` suggests a new market may have emerged, whereas rising SpEL errors point to a contract mismatch or configuration bug.

## 13. Testing an Expression-Based Router

To test routes deterministically, use **`QueueChannel` beans for output channels in test configuration**. You can then send a message to `orders.in` and use `receive(timeout)` to pull the message from the expected channel instead of inspecting console logs.

Example declaring destination channels **for test environment only** (replacing the consuming application flows in the runnable example):

~~~java
@TestConfiguration
class RoutingTestChannels {

    @Bean(name = "orders.vn")
    PollableChannel vn() {
        return new QueueChannel();
    }

    @Bean(name = "orders.us")
    PollableChannel us() {
        return new QueueChannel();
    }

    @Bean(name = "orders.other")
    PollableChannel other() {
        return new QueueChannel();
    }

    @Bean(name = "orders.invalid")
    PollableChannel invalid() {
        return new QueueChannel();
    }
}
~~~

With a Spring test context loading `classifyOrders()` and the test beans above, a test for the domestic branch can be written as:

~~~java
@Autowired
ApplicationContext context;

@Test
void routesNormalizedVietnamOrder() {
    MessageChannel input = context.getBean(
        "orders.in", MessageChannel.class);
    PollableChannel vn = context.getBean(
        "orders.vn", PollableChannel.class);
    PollableChannel us = context.getBean(
        "orders.us", PollableChannel.class);

    Message<OrderPlaced> event = MessageBuilder
        .withPayload(new OrderPlaced("O-101", " vn ", 2))
        .setHeader("correlationId", "O-101")
        .build();

    assertTrue(input.send(event));
    Message<?> received = vn.receive(1000);

    assertNotNull(received);
    assertEquals("VN", ((OrderPlaced) received.getPayload()).market());
    assertEquals("O-101",
        received.getHeaders().get("correlationId"));
    assertNull(us.receive(0));
}
~~~

The example illustrates only the test body; configure JUnit/Spring Test to load the flow and test configuration class. **Do not declare both the production consumer on `orders.vn` and a test `QueueChannel` with the same name.** The test channel replaces the runtime destination to observe messages accurately.

Minimum test matrix:

| Case | Input | Expected Channel/Condition |
|---|---|---|
| Standard VN | `market="VN"` | `orders.vn` |
| Unnormalized VN | `market=" vn "` | After Transformer, arrives at `orders.vn` |
| US | `market="US"` | `orders.us` |
| Undeclared | `market="DE"` | `orders.other` |
| Blank market | `market=""` | `orders.invalid`, Router does not run |
| Negative quantity | `quantity=-1` | `orders.invalid` |
| Missing header | No `riskLevel` | Unknown branch if expression handles null explicitly |
| Wrong payload type | Producer sends `String` instead of `OrderPlaced` | Conversion/evaluation error observed, not silently routed |
| Consumer failure | Downstream handler throws exception | Error path matches channel type, bounded retry |
| Interleaved orders | Different `correlationId` | Groups do not mix across Splitter/Aggregator |

For asynchronous flows, use latches or timed assertions; avoid relying on fixed `Thread.sleep`. When testing error channels, determine whether the exception arises on the caller, executor thread, or poller, and observe at the right point.

## 14. Observing and Diagnosing Routing

To answer "where did this order go?", capture:

- **Computed routing key** and **destination route/channel name** in logs or metrics without sensitive data.
- **Correlation ID**, event ID, and order ID to link Gateway → Transformer → Router → consumer steps.
- Message count per branch, fallback rate, and SpEL evaluation error count.
- Processing latency per branch and backlog on asynchronous branches.
- Retry count, timeouts, and messages routed to failure-handling workflows.

If Micrometer/observation is enabled for Spring Integration, keep channel and endpoint names consistent. Never place full payloads, account numbers, tokens, or customer data into metric labels, as this leaks data and causes label *cardinality* explosion.

When a Router appears to send a message to the wrong branch, inspect in order: **runtime payload type → data after Transformer → expression result → mapping/fallback → resolved channel bean → downstream consumer**. This is a clearer diagnostic path than looking only at logs in the final handler.

## 15. Common Mistakes with Expression Routers

**Putting complex business logic in SpEL.** Long expressions, database queries, or service calls are hard to test. Let a domain policy/service compute the result, then route on a stable field/key.

**Confusing default with error channel.** Default applies when a key has no matching route. Exceptions during expression evaluation or channel dispatch need dedicated error/recovery mechanisms.

**Assuming a header is always present.** A missing header can produce `null` or evaluate a condition to false and take the wrong branch; define unknown/invalid explicitly and test missing-data cases.

**Passing channel names directly from untrusted input.** Arbitrary routing by user/tenant values can open unintended processing paths. Use an allowlisted set of keys with explicit channel mappings.

**Updating the Transformer while forgetting the expression.** After changing payload types, calling old methods or properties can fail at runtime. Write contract tests for the inputs/outputs of each flow segment.

**Forgetting a consumer on the fallback branch.** Having a mapping without a valid destination channel/handler causes flow failures or leaves messages unprocessed as expected. Every route needs a clear owner.

**Ignoring correlation impacts.** Routing Splitter child messages to multiple branches can leave one branch slow or broken; the Aggregator needs timeouts and safe release conditions.

**Assuming the Router guarantees exactly-once.** A Router only dispatches to channels. Delivery, idempotency, transactions, retries, and durability depend on the surrounding components.

## 16. Comprehensive Practice Exercise

Build an **OrderRouting** flow consisting of:

1. **Gateway** accepting `OrderPlaced(orderId, market, quantity)`.
2. **Filter** rejecting orders with blank ID, empty market, or non-positive quantity.
3. **Transformer** normalizing market codes to uppercase.
4. **Expression Router** reading `payload.market()` and routing `VN → orders.vn`, `US → orders.us`, and the rest to `orders.other`.
5. Add another Router based on the `riskLevel` header; missing headers must go to a dedicated classification workflow.
6. Each branch's consumer records results into a test channel or calls a mock service. Run one branch through an executor/queue to observe sync vs. async differences.
7. Intentionally trigger a handler error; verify the error path, appropriate retry policy, idempotency, and correlation on redelivery.

**Completion criteria:** Have a flow diagram, a routing key → channel table, tests for all three markets and invalid inputs, tests for missing headers and expression errors, per-branch message metrics, and traceability for one order across the Router. If adding Splitter/Aggregator, demonstrate that parts still reassemble under the right correlation ID.

## 17. Key Takeaways

**Expression Router** uses SpEL to compute a routing decision from a message, while **channel mapping** binds that decision to a destination channel. **Default output channel** handles keys without a matching route; **error channel/exception handling** resolves execution failures, and **Filter** removes invalid data before the Router.

In Spring Integration, keep expressions concise, validate types and values before routing, configure explicit fallbacks, preserve correlation across adapters, and test every branch. Combined with other EIPs, the Router keeps message flows adaptable and extensible without mixing transport logic with business logic.
