# Distinguishing Multiple Independent Functions from a Function Processing Pipeline

A Spring Cloud Stream application can declare multiple function beans at the same time. However, having multiple functions in one application does not mean they automatically execute sequentially. Some functions may handle independent message streams; others may be composed into a pipeline where the output of one function becomes the input of the next.

This distinction directly affects the number of bindings created, the destinations to configure, how messages flow through the application, error boundaries, and scalability. Within the `Supplier`/`Function`/`Consumer` functional model of `SPRING_CLOUD_STREAM`, you must understand when to declare multiple independent functions and when to define a processing pipeline using Spring Cloud Function composition. Those bindings then connect application logic to Kafka, RabbitMQ, or Pulsar through a binder.

This lesson belongs to the **Functional Programming Model** chapter and focuses on the question: how does activating multiple functions simultaneously differ from a function processing pipeline? We will use an order-processing example to clearly compare both approaches.

## 1. Two Ways to Organize Functions

Suppose a system receives an `OrderPlaced` event. After an order is placed, the system must update inventory, send a notification, and record analytics metrics. There are two different ways to view this:

**Multiple independent functions:** each function fulfills a distinct responsibility and receives data from its own binding. They may read the same destination under independent consumer groups, or read from different destinations. There is no sequential invocation relationship between functions merely because they live in the same application.

```text
                         orders.placed
                              |
             +----------------+----------------+
             |                |                |
             v                v                v
      inventoryUpdater  orderNotifier    orderMetrics
             |                |                |
             v                v                v
       Update stock      Send notice      Record metric
```

**A function processing pipeline (composition):** functions are chained in sequence. The return value of the preceding function is passed directly as the argument to the next function. A pipeline typically has one input binding and one output binding when the final result comes from a `Function`.

```text
orders.placed
     |
     v
normalizeOrder
     |
     v
validateOrder
     |
     v
enrichOrder
     |
     v
orders.ready
```

The core difference: multiple independent functions are separate processing endpoints; composition is a logical pipeline whose steps depend on the output of the preceding step.

## 2. Multiple Independent Functions in the Same Application

Spring Cloud Function allows an application to have multiple `Supplier`, `Function`, or `Consumer` beans. To activate multiple independent functions, list their names in `spring.cloud.function.definition` separated by semicolons (`;`). The semicolon means separate definitions are activated together; it does not mean passing the result of one function into another.

Example with three independent consumers:

```java
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record OrderPlaced(String orderId, long total) {}

@Configuration
class OrderConsumers {

    @Bean
    Consumer<OrderPlaced> inventoryUpdater() {
        return event -> {
            System.out.println("Update inventory for " + event.orderId());
        };
    }

    @Bean
    Consumer<OrderPlaced> orderNotifier() {
        return event -> {
            System.out.println("Notify customer for " + event.orderId());
        };
    }

    @Bean
    Consumer<OrderPlaced> orderMetrics() {
        return event -> {
            System.out.println("Record order metric: " + event.total());
        };
    }
}
```

Configuration activating all three functions:

```yaml
spring:
  cloud:
    function:
      definition: inventoryUpdater;orderNotifier;orderMetrics
    stream:
      bindings:
        inventoryUpdater-in-0:
          destination: orders.placed
          group: inventory-projection
          content-type: application/json
        orderNotifier-in-0:
          destination: orders.placed
          group: order-notification
          content-type: application/json
        orderMetrics-in-0:
          destination: orders.placed
          group: order-metrics
          content-type: application/json
```

Each consumer gets its own input binding following the `<functionName>-in-0` convention. All three bindings read from the `orders.placed` destination, yet use different groups so each responsibility receives an independent stream of messages. If all three shared the same consumer group on Kafka, instances would split partitions within that group instead of each function receiving every record. For RabbitMQ and Pulsar, configure separate queues or subscriptions corresponding to each group.

These functions do not call one another. `inventoryUpdater` does not wait for `orderNotifier`; `orderMetrics` does not receive outputs from the other two functions. Each function can be scaled, observed, retried, and deployed according to its own responsibility, within the constraints of how the application and binder are deployed.

### When to Choose the Independent Approach

Choose multiple independent functions when:

- Multiple components must react to the same event without depending on each other's results.
- One consumer may be slow or paused without blocking other consumers.
- Each responsibility has different load, access control, retry, or message retention requirements.
- You want to isolate processing streams to track failures and scale each responsibility separately.

For example, a notification service should not delay inventory updates simply because an email provider is temporarily unavailable. Both responsibilities can consume the same event through two independent groups with separate retry policies.

## 3. A Processing Pipeline Using Function Composition

Composition combines multiple compatible functions into a single logical function. In Spring Cloud Function, the pipe operator (`|`) expresses composition order: the left function runs first, and its result is passed to the right function.

Suppose an order-processing workflow has three steps:

1. Normalize the order ID and input data.
2. Validate business conditions.
3. Enrich with routing details or a processing label.

Each step can be written as a separate `Function`:

```java
import java.util.Locale;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record OrderPlaced(String orderId, long total) {}

record NormalizedOrder(String orderId, long total) {}

record ValidatedOrder(String orderId, long total) {}

record EnrichedOrder(String orderId, long total, String processingLane) {}

@Configuration
class OrderPipelineFunctions {

    @Bean
    Function<OrderPlaced, NormalizedOrder> normalizeOrder() {
        return event -> new NormalizedOrder(
            event.orderId().trim().toUpperCase(Locale.ROOT),
            event.total()
        );
    }

    @Bean
    Function<NormalizedOrder, ValidatedOrder> validateOrder() {
        return event -> {
            if (event.orderId().isBlank() || event.total() <= 0) {
                throw new IllegalArgumentException("Invalid order");
            }
            return new ValidatedOrder(event.orderId(), event.total());
        };
    }

    @Bean
    Function<ValidatedOrder, EnrichedOrder> enrichOrder() {
        return event -> new EnrichedOrder(
            event.orderId(),
            event.total(),
            event.total() >= 10_000_000 ? "priority" : "standard"
        );
    }
}
```

The type signatures show that adjacent output and input types match:

| Step | Input Type | Output Type |
|---|---|---|
| `normalizeOrder` | `OrderPlaced` | `NormalizedOrder` |
| `validateOrder` | `NormalizedOrder` | `ValidatedOrder` |
| `enrichOrder` | `ValidatedOrder` | `EnrichedOrder` |

Declaring the composition:

```yaml
spring:
  cloud:
    function:
      definition: normalizeOrder|validateOrder|enrichOrder
    stream:
      bindings:
        'normalizeOrder|validateOrder|enrichOrder-in-0':
          destination: orders.placed
          group: order-pipeline
          content-type: application/json
        'normalizeOrder|validateOrder|enrichOrder-out-0':
          destination: orders.enriched
          content-type: application/json
```

In this configuration, `normalizeOrder|validateOrder|enrichOrder` is one composed function definition. The input binding receives `OrderPlaced`; intermediate functions pass data directly within the pipeline; the output binding emits `EnrichedOrder`. Intermediate steps do not create separate topics or queues and do not publish intermediate results to the broker.

### Requirements for Composing Functions

Functions must have compatible data signatures. If `normalizeOrder` returns `NormalizedOrder`, the next function must accept that type or a type supported by conversion. When composing multiple functions, verify:

- The output type of the previous step is compatible with the input type of the next step.
- Steps have a clear order and no hidden dependencies on external mutable state.
- Functions follow a consistent error-handling contract; a failure in any step fails the current pipeline invocation.
- Payload and header conversions are intentional, especially when using `Message<T>` rather than raw payloads.
- The processing cost of the steps fits running within a single processing thread/flow.

Composition suits sequential transformation or validation steps. If individual steps require durable state, independent retries, or separate deployment, consider splitting them into separate applications or messaging streams.

## 4. The `;` and `|` Separators Do Not Mean the Same Thing

This is the most common source of confusion when declaring multiple functions:

| Syntax | Meaning | Execution Model |
|---|---|---|
| `inventoryUpdater;orderNotifier;orderMetrics` | Activates multiple independent functions | Each function gets its own bindings; results are not forwarded between functions |
| `normalizeOrder|validateOrder|enrichOrder` | Composes functions into one pipeline | Output of each step is passed into the next step |
| `normalizeOrder|validateOrder;orderNotifier` | One pipeline and one independent function | Pipeline is composed; `orderNotifier` is a separate definition |

Do not use a semicolon when you want the result of function A to enter function B. Likewise, do not use a pipe just because you want multiple consumers reading the same event. A pipe establishes sequential execution; multiple independent consumers require appropriate destinations and groups/subscriptions.

Example combining both forms:

```yaml
spring:
  cloud:
    function:
      definition: normalizeOrder|validateOrder;orderMetrics
    stream:
      bindings:
        'normalizeOrder|validateOrder-in-0':
          destination: orders.placed
          group: order-validation
        'normalizeOrder|validateOrder-out-0':
          destination: orders.validated
        orderMetrics-in-0:
          destination: orders.placed
          group: order-metrics
```

The `normalizeOrder|validateOrder` pipeline receives and publishes messages through its two pipeline bindings. `orderMetrics` independently reads events from `orders.placed`. Neither execution path waits for the other to finish.

## 5. Binding Names and Destinations in Both Models

Binding names are generated from the function name or composition name. Destinations are determined by configuration. Therefore, multiple independent functions normally create multiple bindings, whereas a function pipeline typically has one pair of bindings at its endpoints if composing `Function` into `Function`.

| Model | Input Binding | Output Binding | Illustrative Destinations |
|---|---|---|---|
| Three independent consumers | `inventoryUpdater-in-0`, `orderNotifier-in-0`, `orderMetrics-in-0` | None for `Consumer` | Same `orders.placed` with separate groups |
| One independent function | `calculateRisk-in-0` | `calculateRisk-out-0` | `orders.placed` → `orders.risk-scored` |
| Three-function pipeline | `normalizeOrder|validateOrder|enrichOrder-in-0` | `normalizeOrder|validateOrder|enrichOrder-out-0` | `orders.placed` → `orders.enriched` |

When a composition binding name contains `|`, wrap the YAML key in quotes to avoid confusion with YAML syntax. Your configuration must match the exact binding name generated by the framework from the function definition.

## 6. Does Intermediate Data Travel Through the Broker?

In a composition, steps invoke one another within the same pipeline. For example, `normalizeOrder` returns `NormalizedOrder`, and `validateOrder` receives that value immediately. Intermediate messages do not need to be serialized, published to a topic, and consumed again by another consumer.

```text
Single message receipt
        |
        v
  deserialize input
        |
        v
  normalizeOrder
        |  NormalizedOrder (in-memory)
        v
  validateOrder
        |  ValidatedOrder (in-memory)
        v
  enrichOrder
        |
        v
  serialize output
        |
        v
  publish orders.enriched
```

This reduces broker hops and works well for short transformation chains. In exchange, the steps share a single message-processing lifecycle. If the second step fails, the pipeline produces no final output; the binder handles the failure at the binding boundary according to retry, acknowledgment, and DLQ configuration. There is no independent commit checkpoint for each intermediate function merely because they are written as separate beans.

If intermediate messages must be retained, observed independently, or replayed from a checkpoint, create explicit destinations and bindings for each stage. The architecture then becomes multiple messaging stages connected through the broker rather than an in-memory composition.

## 7. Supplier, Function, and Consumer in a Pipeline

The three function types represent three roles:

- `Supplier<T>` produces data and receives no input argument from a binding.
- `Function<T, R>` receives data and returns transformed data.
- `Consumer<T>` receives data and completes an action without producing a function output.

Composition can combine roles when type contracts and flow goals match—for instance, a supplier producing an event, a function normalizing it, and a consumer recording the result. However, for clarity of observation and configuration, this lesson focuses on `Function` chains as the primary example. For pipelines with a `Supplier` or `Consumer` at the start or end, verify signatures and how Spring Cloud Function interprets the definition in your target version.

Avoid turning every operation into one long chain. A consumer with side effects such as sending emails or deducting inventory may need independent retries and delivery control. Putting it in a long composition means a failure in that step fails the entire pipeline message invocation. If an action needs independent operation, emit an event or command for a dedicated consumer to receive.

## 8. Fan-Out Is Not Composition

Fan-out distributes one message to multiple independent recipients. Composition passes data sequentially through multiple steps. These two patterns solve different needs:

| Need | Suitable Organization | Example |
|---|---|---|
| Multiple parties need to know an order was created | Fan-out to multiple groups/queues/subscriptions | Inventory, analytics, and notifications all receive `OrderPlaced` |
| Data needs normalization, then validation, then enrichment | Composition | `normalizeOrder|validateOrder|enrichOrder` |
| One step emits a new business event for multiple parties to react to | Function publishes output to a destination, then multiple independent consumers receive it | `OrderValidated` is published to inventory and analytics |
| Background task needs independent retries and operations | Independent consumer on a dedicated destination | Email service receives `NotificationRequested` |

Do not compose `updateInventory|sendEmail|recordMetrics` if those three tasks do not depend on each other's return values. Such a chain would cause slow email sending or email failures to disrupt metric recording and inventory updates. Publish a shared event and let each consumer handle its own responsibility.

## 9. Errors and Recoverability

How functions are organized determines where errors surface and the scope of retries:

**With independent functions:** each binding has its own consumption flow and error policy as configured on the binder. A failure in `orderNotifier` does not necessarily impact `inventoryUpdater`, provided the two consumers genuinely use independent groups/queues/subscriptions.

**With composition:** a failure at any step can fail the pipeline invocation. The binder sees the processing outcome of the entire composed function. On retry, the pipeline can re-run from the start; any step with side effects must be idempotent or designed not to repeat effects.

For example, if `normalizeOrder` and `validateOrder` are pure data transformations, re-running them normally causes no side effects. If `enrichOrder` calls a fee calculation service or writes to a database, idempotency and transactions must be designed explicitly. Never assume the framework creates a transaction spanning all steps and external services.

Some principles:

- Keep composition steps as pure as possible: identical inputs produce consistent outputs with no unintended side effects.
- Configure timeouts and retries for external dependencies at the right layer, with bounds and backoff.
- Use a stable event ID or idempotency key whenever a pipeline may be redelivered.
- If a step encounters a data error that retries cannot fix, route the message to a DLQ or quarantine flow per policy.
- If a responsibility needs independent replay, consider splitting it into an independent consumer with its own destination and group.

## 10. Testing Both Models

Testing must verify both function logic and how the framework wires bindings:

| Test Aspect | Multiple Independent Functions | Composition |
|---|---|---|
| Logic check | Invoke each consumer/function individually | Test individual steps and the full pipeline output |
| Bindings | Verify each function has its own bindings | Verify input/output bindings of the composition name |
| Message flow | Each function receives messages per its destination/group | Output of each step feeds into the next step |
| Failures | Failure in one consumer does not halt other independent consumers | Failure in one step fails the pipeline invocation |
| Delivery | Verify retry/DLQ per binding | Verify retry/DLQ at pipeline boundary and duplicate side effects |

Unit test examples for composition steps can invoke each bean and verify data types:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class OrderPipelineFunctionsTest {

    @Test
    void normalizesOrderId() {
        var result = new OrderPipelineFunctions()
            .normalizeOrder()
            .apply(new OrderPlaced(" ord-42 ", 500_000));

        assertEquals("ORD-42", result.orderId());
    }
}
```

For integration tests, use the test binder or a real broker as appropriate to verify that destinations, groups, and bindings are created properly. Directly mocking functions only proves Java logic; it does not prove messages actually traverse the broker as intended. When testing multiple independent consumers, verify each group receives its own copy of the message. When testing composition, verify that one input message yields the expected final output without generating unintended intermediate destinations.

## 11. Choosing a Model Based on Business Requirements

Before choosing how to declare functions, answer these questions:

1. Do the steps need each other's outputs? If yes, composition may fit.
2. Can the responsibilities run independently? If yes, split them into multiple independent functions.
3. Should a failure in one step block the remaining steps? If not, do not put them in the same synchronous pipeline.
4. Do intermediate results need to be stored or replayed? If yes, create explicit destinations.
5. Do the steps have different scaling, retry, permission, or deployment schedules? If yes, separate bindings or services appropriately.
6. Is the output of the preceding step compatible with the input of the next step? If not, introduce an explicit conversion step or a different message contract.

| Criterion | Multiple Independent Functions | Function Composition Pipeline |
|---|---|---|
| Relationship between steps | Do not depend on each other's results | Later step consumes earlier step's output |
| Number of bindings | Each function has its own bindings by role | Typically one input and one output for function composition |
| Broker hops between steps | Each function can read from a separate or shared destination | No broker hops between internal steps |
| Failures | Isolatable per binding | One failing step fails the current pipeline invocation |
| Scaling | Scaled per consumer group/queue/subscription | Scaled as a single pipeline consumption unit |
| Use when | Fan-out, independent tasks | Sequential transformations, sequential validations |

## 12. Configuration and Verification Workflow

When building a Spring Cloud Stream application with multiple functions, follow these steps:

1. List all function beans and each bean's role (`Supplier`, `Function`, `Consumer`).
2. Diagram the data flow: which functions are independent, which need sequential composition.
3. Use `;` for multiple independent definitions; use `|` for ordered composition.
4. Determine the binding names generated from each function or composition.
5. Assign destination, group, and content type for each binding suited to the broker.
6. If multiple consumers must receive the same event, assign an independent group/queue/subscription to each responsibility.
7. Verify data types between composition steps and exception-handling rules.
8. Test bindings, message flows, retries, DLQs, and safe re-execution.
9. Monitor lag, throughput, and errors per binding to identify where scaling is needed.

## 13. Self-Check

- [ ] Can explain why having multiple function beans in the same application does not automatically chain them together.
- [ ] Can distinguish the meanings of `;` and `|` in `spring.cloud.function.definition`.
- [ ] Can determine the binding names of independent functions and of a function composition.
- [ ] Can describe how multiple independent consumers read the same destination using separate groups.
- [ ] Can explain how the output of one function becomes the input of the next function.
- [ ] Knows that intermediate data in a composition passes in-application and does not automatically go through the broker.
- [ ] Can analyze error and retry boundaries in both models.
- [ ] Can choose fan-out or composition based on business dependencies.

## Conclusion

Multiple independent functions are activated using separate definitions and each receives its own bindings; they do not automatically pass results to one another. Composition uses the pipe (`|`) operator to chain compatible functions into a pipeline where data flows sequentially from one step to the next. The semicolon (`;`) separates multiple independent definitions. Choosing the right model clarifies bindings, destinations, groups, error boundaries, and scaling strategies. With Spring Cloud Stream, use composition for sequential transformation steps and use independent consumers for responsibilities that must react, recover, or scale independently.
