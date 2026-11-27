# Distinguishing Dispatchers from Routers

In Spring Integration, both dispatchers and routers are involved in where a message goes, yet they operate at two different layers. A dispatcher is a channel-level mechanism that delivers a message to subscribers registered on that channel. A router is a message-processing endpoint that inspects the payload or headers and decides which channel(s) the message should be sent to next.

Confusing these two concepts easily leads to misconfiguration: expecting `DirectChannel` to route by order type on its own, or expecting a router to perform load balancing across handlers subscribed to one channel. To read a flow accurately, trace two steps: the router selects an output channel; the output channel's dispatcher delivers the message to a subscriber.

## 1. Dispatchers Operate at the Channel Layer

A channel can have one or multiple subscribers. For subscribable channels, the dispatcher accepts messages sent to the channel and executes the delivery policy to subscribers.

In Spring Integration, two common internal implementations are:

- `UnicastingDispatcher`: selects one subscriber to receive the message.
- `BroadcastingDispatcher`: sends the message to all registered subscribers.

The dispatcher does not inspect business rules such as order type, tenant, or header values to choose an output channel. It executes the channel's dispatch policy based on the subscriber list and channel configuration.

### DirectChannel and UnicastingDispatcher

`DirectChannel` uses unicast semantics: each send dispatches a message to one subscriber. When multiple subscribers exist, the channel uses a load-balancing strategy; the default is round robin. Because processing usually happens on the sending thread, `DirectChannel` suits synchronous flows and can propagate handler exceptions back to the producer.

Visualizing it:

~~~mermaid
flowchart TD
    M[Message sent to DirectChannel] --> D[UnicastingDispatcher]
    D -->|Select in turn via load balancing| A[Subscriber A]
    D -->|Next turn| B[Subscriber B]
    D -->|Following turn| C[Subscriber C]
~~~

If the channel has three subscribers and uses round robin, consecutive messages are distributed across the subscribers in turn. The dispatcher does not check which subscriber handles which message type. If you need content-based branching, place a router before the target channels.

`DirectChannel` supports configuring a load-balancing strategy and failover. When failover is enabled, the dispatcher can try another subscriber if the selected subscriber throws an exception. Understand the consequence: the first handler may have already executed partial side effects before failing; the next handler receiving the same message may execute those side effects again. Consequently, handlers participating in failover must be idempotent or have duplicate-prevention mechanisms.

### PublishSubscribeChannel and BroadcastingDispatcher

`PublishSubscribeChannel` uses broadcast semantics: a single message is delivered to multiple registered subscribers. This is channel-level fan-out, typically used when the same event must be processed by multiple independent branches.

~~~mermaid
flowchart TD
    M[Message sent to PublishSubscribeChannel] --> D[BroadcastingDispatcher]
    D --> A[Subscriber A: audit]
    D --> B[Subscriber B: notification]
    D --> C[Subscriber C: analytics]
~~~

If the channel is configured with an executor, dispatching to subscribers can occur asynchronously. Otherwise, subscribers are typically invoked on the sending thread. Depending on the `ignoreFailures` setting, an error from one subscriber can affect dispatching to remaining subscribers. If all independent branches must continue even when one branch fails, configure and test an appropriate error policy.

## 2. Routers Operate at the Message Flow Layer

A router is a `MessageHandler` endpoint. It receives a message from an input channel, evaluates its payload or headers, and selects one or more output channels to send the message to next.

Commonly used routers:

| Router | Output Selection Basis |
|---|---|
| `HeaderValueRouter` | Based on the value of a message header |
| `PayloadTypeRouter` | Based on payload type |
| `RecipientListRouter` | Selects a configured list of recipients/channels based on configured logic |
| `ExceptionTypeRouter` | Selects a channel based on exception type in an error flow |
| Custom router | Based on custom business rules |

A router can pick one channel or multiple channels depending on the router type and routing result. It is not the input channel's dispatcher: the router is a subscribed endpoint on the input channel, while the input channel's dispatcher is responsible for delivering the message to that router endpoint.

Example: `@Router` choosing an output channel by order type:

~~~java
@Component
public class OrderRouter {

    @Router(inputChannel = "orders.input")
    public String route(Order order) {
        return order.isPriority()
                ? "orders.priority"
                : "orders.standard";
    }
}
~~~

Here the router reads business data `isPriority()` and returns the target channel name. Ensure the `orders.priority` and `orders.standard` channels are declared or resolvable in the application context.

Target flows can be declared separately:

~~~java
@Bean
IntegrationFlow priorityOrderFlow(OrderService orderService) {
    return IntegrationFlow.from("orders.priority")
            .handle(orderService, "processPriority")
            .get();
}

@Bean
IntegrationFlow standardOrderFlow(OrderService orderService) {
    return IntegrationFlow.from("orders.standard")
            .handle(orderService, "processStandard")
            .get();
}
~~~

The router decides which channel receives the message. Once the message arrives at the target channel, that channel's dispatcher decides which subscriber executes.

## 3. Two Dispatch Layers Within the Same Flow

Consider a flow where a router sends priority orders to `orders.priority` and standard orders to `orders.standard`. If `orders.priority` is a `DirectChannel` with two subscribers, that channel's dispatcher picks one subscriber according to its load-balancing strategy.

~~~mermaid
flowchart TD
    IN[orders.input] --> D1[Input channel dispatcher]
    D1 --> R[Router endpoint]
    R -->|priority| P[orders.priority]
    R -->|standard| S[orders.standard]
    P --> DP[UnicastingDispatcher]
    DP --> P1[Priority handler A]
    DP --> P2[Priority handler B]
    S --> DS[Standard channel dispatcher]
    DS --> SH[Standard handler]
~~~

In the diagram:

1. `orders.input`'s dispatcher delivers the message to the subscribed router endpoint.
2. The router inspects the payload and selects an output channel.
3. The output channel's dispatcher selects a subscriber or broadcasts depending on channel type.

These are two independent decisions. To split by business criteria, use a router. For multiple subscribers to all receive an event, use `PublishSubscribeChannel`. To distribute turns across consumers handling the same message type, use a unicast channel with multiple subscribers and an appropriate load-balancing configuration.

## 4. Load Balancing Is Not Routing

Load balancing distributes messages across subscribers of the same channel according to a dispatch strategy. Routing selects a channel based on message content or routing rules.

| Criterion | Dispatcher Load Balancing | Router Routing |
|---|---|---|
| Input | Channel's subscriber list | A message and its data |
| Decision | Which subscriber receives the message | Which channel receives the message |
| Basis | Strategy such as round robin or custom strategy | Payload, header, exception, or business rule |
| Result | One subscriber or multiple subscribers depending on dispatcher type | One or more output channels |
| Example | Splitting messages across workers subscribed to `orders.work` | VIP orders to `orders.priority`, standard orders to `orders.standard` |

Round robin neither guarantees the same customer always lands on the same worker nor preserves completion order. If you need partitioning by customer ID or order ID, route by key or use an explicit partitioning mechanism.

## 5. UnicastingDispatcher and Failover

`UnicastingDispatcher` is responsible for selecting one subscriber per dispatch. With `DirectChannel`, the default strategy is round robin when multiple subscribers exist. A different load-balancing strategy can be configured to match requirements, but custom strategies must be verified for thread safety and fairness.

Failover is the policy for handling when the selected subscriber does not succeed. When enabled, the dispatcher can continue trying other subscribers in dispatch order. This is not equivalent to durable retry: the dispatcher does not persist messages to retry after a JVM restart, nor does it guarantee once-only execution.

Distinguish among:

- **Subscriber failover:** trying another subscriber within the same dispatch attempt.
- **Retry advice:** re-invoking the operation per a retry policy, typically with attempt limits and backoff.
- **Broker redelivery:** broker redelivering the message per acknowledgement/transaction semantics.
- **Dead-letter/error flow:** forwarding failed messages to a dedicated handling path.

Do not enable failover blindly if multiple subscribers perform side effects. If handler A partially updates a database before failing, handler B can receive the same message and write duplicates. Use idempotency keys, unique constraints, or clearly separated subscriber responsibilities.

## 6. BroadcastingDispatcher and Fan-Out

`BroadcastingDispatcher` sends a message to the subscribers of a `PublishSubscribeChannel`. Unlike a router, broadcast does not choose a single branch based on payload; every configured subscriber participates in receiving the message.

Several settings can influence behavior:

- Executor: determines whether subscribers run synchronously or are dispatched asynchronously.
- `ignoreFailures`: decides how subscriber exceptions are handled during broadcast.
- `applySequence`: can attach sequence metadata to messages sent to multiple subscribers.
- `minSubscribers`: sets the minimum number of subscribers required to send a message in versions supporting this property.

Broadcast does not create durability on its own. If a subscriber is inactive or a message fails after dispatch, the channel is not an event log for later replay. If each branch needs independent delivery guarantees, consider a broker/topic or separate queues for each consumer.

## 7. When a Router Cannot Find a Target Channel

A router must resolve output channel names to actual channels. Routing errors can happen when:

- No channel mapping exists for a header/payload value.
- The target channel has not been declared or its name is misspelled.
- The router has no default output channel when no mapping matches.
- Configuration requires successful channel resolution, yet no matching bean exists.

When designing a router, decide explicitly how unmatched messages are handled: send to a default channel, forward to an error channel, deliberately discard, or raise an error for upstream handling. Do not leave unmatched cases as obscure implicit behavior.

Fallback rule example:

~~~java
@Router(inputChannel = "orders.input",
        defaultOutputChannel = "orders.unmatched")
public String route(Order order) {
    return switch (order.getType()) {
        case PRIORITY -> "orders.priority";
        case STANDARD -> "orders.standard";
        default -> null;
    };
}
~~~

Channel names in the annotation and return values must match channel beans in the application context. Test both valid and unmatched values; in particular, verify whether a router returning `null` goes to the configured default output channel.

## 8. Choosing Channels and Routers by Goal

| Goal | Appropriate Mechanism |
|---|---|
| One of several handlers processes each message, sharing load | `DirectChannel` with multiple subscribers and a load-balancing strategy |
| Invoke handler on the sending thread, keeping call stack synchronous | `DirectChannel` |
| Offload processing to a worker executor | `ExecutorChannel` |
| Multiple subscribers all receive one message | `PublishSubscribeChannel` |
| Buffer messages for consumers to receive later | `QueueChannel` or broker-backed channel |
| Select output by header | `HeaderValueRouter` |
| Select output by payload type | `PayloadTypeRouter` |
| Select output by custom business logic | Custom router or `@Router` |
| Send to a determined set of recipients | `RecipientListRouter` or publish-subscribe channel, depending on semantics |

Do not use `PublishSubscribeChannel` just to replace a router when only one branch should process the message. Conversely, do not create multiple router endpoints merely to broadcast the same event to all subscribers when a publish-subscribe channel expresses that intent directly.

## 9. Observing Dispatchers and Routers at Runtime

When a message does not reach the right handler, identify at which layer the message stopped:

1. Was the message sent to the input channel?
2. Does the channel have subscribers and did the dispatcher select one?
3. If the subscriber is a router, did the router compute the expected output channel?
4. Does the output channel exist and have subscribers/consumers?
5. Did the output channel's dispatcher succeed in dispatching?
6. Did the handler succeed or trigger an exception/error flow?

Logs should include the channel/component name, message ID, Correlation ID, route key, and selected output channel. Avoid logging full payloads if they contain sensitive data.

Common symptoms:

| Symptom | Possibilities to Check |
|---|---|
| Message enters channel but no handler sees it | Subscriber not registered, endpoint not started, or channel has no consumer |
| Message always goes to the same handler | Only one subscriber, unexpected load-balancing strategy, or unexpected topology |
| Message is processed by the wrong handler type | Using load balancing instead of a business router |
| Router cannot find output | Missing mapping, misspelled channel name, or missing default output channel |
| One message runs in multiple branches | `PublishSubscribeChannel` or router returning multiple recipients/channels |
| Duplicate side effects after exception | Subscriber failover, retry, or redelivery; check idempotency |
| One failing subscriber prevents other branches from running | Check `ignoreFailures` and `BroadcastingDispatcher` semantics |

Message History and Integration Graph can help identify traversed components/channels and registered topology. However, the graph only describes runtime structure; logs keyed by message ID/Correlation ID are what pinpoint which branch a specific message actually took.

## 10. Design Checklist

- [ ] Determine whether you need to select a subscriber or select an output channel.
- [ ] Use `DirectChannel`/unicast dispatcher for one subscriber per dispatch.
- [ ] Use `PublishSubscribeChannel`/broadcast dispatcher when every subscriber must receive the message.
- [ ] Use a router when the decision depends on payload, headers, or business rules.
- [ ] Do not confuse round robin with key-based or tenant-based routing.
- [ ] Evaluate failover and the risk of executing side effects multiple times.
- [ ] Configure a default output/error path for unmatched messages.
- [ ] Verify the target channel has active subscribers or consumers.
- [ ] Identify executors and thread boundaries when dispatching asynchronously.
- [ ] Log the route key, component/channel name, and message ID for diagnostics.

Dispatchers and routers complement each other. A router chooses where a message needs to go based on content or business rules; the channel's dispatcher handles delivery to subscribers according to the channel policy. Separating these two layers clearly lets you design routing, load balancing, and fan-out accurately, and diagnose whether errors occur at branch selection or at dispatch.

## References

- [Spring Integration Reference: Message Channels](https://docs.spring.io/spring-integration/reference/channel.html)
- [Spring Integration Reference: Routers](https://docs.spring.io/spring-integration/reference/router.html)
- [Spring Integration API: DirectChannel](https://docs.spring.io/spring-integration/docs/6.4.x/api/org/springframework/integration/channel/DirectChannel.html)
- [Spring Integration API: PublishSubscribeChannel](https://docs.spring.io/spring-integration/docs/6.4.x/api/org/springframework/integration/channel/PublishSubscribeChannel.html)
- [Spring Integration API: AbstractMessageRouter](https://docs.spring.io/spring-integration/docs/6.4.x/api/org/springframework/integration/router/AbstractMessageRouter.html)
