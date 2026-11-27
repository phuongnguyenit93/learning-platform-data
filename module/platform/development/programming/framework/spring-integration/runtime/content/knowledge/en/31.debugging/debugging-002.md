# Isolating Channels Without Subscribers

When operating Spring Integration, a common error is that a message was sent to a channel with no endpoint receiving it. Logs may contain the phrase **<code>Dispatcher has no subscribers</code>**, a <code>MessageDispatchingException</code>, or merely show a missing reply symptom. These symptoms are **not equivalent**: some channels require a subscriber immediately upon send, some store messages for a poller to pick up later, and some broadcast events while allowing zero subscribers by configuration.

The lesson **"Isolating Channels Without Subscribers"** belongs to the **Debugging** chapter of the **SPRING_INTEGRATION_RUNTIME** module. Its goal is to trace message flow steps through channels, consumer endpoints, pollers, executors, routers, and dynamic <code>IntegrationFlow</code> instances; distinguish wiring errors from lifecycle or delivery errors; and then use runtime observation, Java/JUnit experiments, and checks across transactions, retries, error channels, and correlation to pinpoint the exact root cause.

> **First rule:** Before editing configuration, identify the **specific channel type**, the **subscriber count at the time of failure**, and **which thread the error handling runs on**. Do not hastily attach a dummy subscriber just to silence the exception: doing so can turn a delivery failure into silent data loss.

## 1. What Is a Subscriber Really?

In Spring Messaging, <code>SubscribableChannel</code> lets a <code>MessageHandler</code> register via <code>subscribe(handler)</code> and unregister via <code>unsubscribe(handler)</code>. Spring Integration's event-driven endpoints, such as <code>EventDrivenConsumer</code> or a <code>@ServiceActivator</code> endpoint bound to a <code>DirectChannel</code>, manage the corresponding handler subscription when the endpoint runs.

In a flow:

~~~text
HTTP adapter / gateway
   → orders.input (DirectChannel)
   → orders.consumer (EventDrivenConsumer)
   → OrderService.process() (MessageHandler)
   → orders.out
~~~

A **channel** is responsible for transferring messages. An **endpoint** connects the channel to the handler and manages lifecycle. A **handler** executes logic. Creating a handler bean does **not automatically** mean it is subscribed to the intended channel; proper endpoint/DSL/annotation wiring and a running state are required.

~~~mermaid
flowchart LR
    P["Producer"] --> C["orders.input<br/>DirectChannel"]
    E["EventDrivenConsumer<br/>STARTED"] --> H["Order handler"]
    C -- "dispatch if subscribed" --> E
    S["SmartLifecycle"] -. "start: subscribe" .-> E
    S -. "stop: unsubscribe" .-> E
    C -. "0 subscribers" .-> X["MessageDispatchingException"]
~~~

The diagram illustrates an event-driven endpoint. It does **not** describe a <code>QueueChannel</code>: a queue does not require a <code>MessageHandler</code> to subscribe directly; instead, a polling consumer retrieves messages using <code>receive()</code>.

## 2. Classification Table: Channel Type Determines Error Symptoms

| Channel | How consumers receive messages | What happens with no consumer/subscriber? | First check |
|---|---|---|---|
| <code>DirectChannel</code> | <code>SubscribableChannel</code>; dispatches immediately on sender thread | <code>UnicastingDispatcher</code> with no handler throws <code>MessageDispatchingException</code> | <code>getSubscriberCount()</code>, endpoint <code>isRunning()</code> |
| <code>ExecutorChannel</code> | Subscriber invoked via executor/worker | No handler causes a dispatch error; with a handler, send may return before the worker finishes | Subscriber count, executor queue/rejection, worker logs |
| <code>PublishSubscribeChannel</code> | Broadcasts to all subscribers | **Default** <code>minSubscribers=0</code>; send may be treated as successful even with no receiver. <code>requireSubscribers=true</code> turns zero subscribers into an error | <code>getSubscriberCount()</code>, <code>requireSubscribers</code>, <code>minSubscribers</code> |
| <code>QueueChannel</code> | <code>PollableChannel.receive()</code>; typically called by a poller | Having no subscribers is **normal**; messages can remain in the queue until consumed or the queue fills up | Queue size, poller lifecycle, <code>receiveTimeout</code> |
| <code>FluxMessageChannel</code> | Reactive Streams <code>Publisher</code> and subscriber demand | Neither <code>SubscribableChannel</code> nor <code>PollableChannel</code>; inspect reactive subscription/backpressure rather than imperative subscriber counts | Reactive subscriber, <code>request(n)</code>, completion/error |
| Global <code>errorChannel</code> | Typically a publish–subscribe channel for errors | Since Spring Integration 5.4.3, the default error channel requires subscribers; secondary errors can report no subscribers if the error flow is unavailable | Identify the original error and the error channel receiving the message |

Therefore, the statement "this channel has **0 subscribers**" only proves **a problem exists** when the channel is designed to dispatch directly to a required handler. For a <code>QueueChannel</code>, the right question is "has the poller received the message yet?", not "who is subscribed?".

### Two Most Commonly Confused Configurations

<code>DirectChannel</code> is point-to-point and requires at least one handler to dispatch. <code>PublishSubscribeChannel</code> is broadcast: by default since Spring Integration 3.0, the <code>minSubscribers</code> threshold is 0, so a send can succeed even if no subscribers are currently registered.

~~~java
PublishSubscribeChannel optionalEvents = new PublishSubscribeChannel();
// Having no subscribers can still be treated as a successful send.

PublishSubscribeChannel mandatoryEvents =
    new PublishSubscribeChannel(true);
// With requireSubscribers: having no subscribers causes a dispatch error.
~~~

<code>requireSubscribers</code> has been supported since 5.4.3. If the business flow mandates a consumer, configure it explicitly rather than relying on publish–subscribe "appearing to send".

## 3. Identifying the Stack Trace: Where and When Did the Error Occur?

A typical error exhibits these signs:

~~~text
org.springframework.integration.MessageDispatchingException:
Dispatcher has no subscribers for channel '...'
    at ...UnicastingDispatcher.dispatch(...)
    at ...AbstractSubscribableChannel.doSend(...)
    at ...AbstractMessageChannel.send(...)
~~~

Exact method names/message strings vary by version. <code>MessageDispatchingException</code> extends <code>MessageDeliveryException</code> and reflects a dispatch failure. Do not write code that matches the entire exception string verbatim; rely on **exception type, failed message/channel, cause, and runtime state**.

Three symptom groups:

1. **True dispatch error:** <code>MessageDispatchingException</code> is thrown when a dispatching channel has no eligible handler or cannot dispatch under runtime conditions.
2. **Send succeeds but nobody processes:** occurs on publish–subscribe allowing 0 subscribers, or when a queue accepted the message but no poller is pulling from it.
3. **Handler received it but no reply arrived:** may be caused by a one-way handler, unmatched router branch, downstream delay/async execution, or gateway timeout. This is **not necessarily** a subscriber issue.

**Emergency triage checkpoint:** If logs mention "no subscribers", determine whether it is on the **business input channel**, a **downstream channel after a router**, or the **errorChannel**. A secondary exception from an unsubscribed error channel can mask the original business exception.

## 4. Isolation Strategy Along the Actual Path

When an error occurs, start where the message is sent and walk **hop by named hop**:

~~~mermaid
flowchart TD
    A["Error / no reply"] --> B{"Channel name and exception present?"}
    B -->|Yes| C["Identify actual channel bean + type"]
    B -->|No| D["Trace from producer, gateway, correlation ID"]
    D --> C
    C --> E{"SubscribableChannel?"}
    E -->|Yes| F["Read subscriber count at investigation time"]
    E -->|Queue| Q["Read queue depth, poller/consumer running"]
    E -->|Reactive| R["Check subscription, demand, onError"]
    F --> G{"count = 0?"}
    G -->|Yes| H["Inspect endpoint/wiring/lifecycle"]
    G -->|No| I["Inspect routing, handler failure, concurrency"]
    H --> J["Fix the right endpoint / start policy"]
    I --> J
    Q --> J
    R --> J
    J --> K["Retest failure and recovery"]
~~~

Step-by-step procedure:

1. Collect the **original exception**, thread, timestamp, channel name, message ID, correlation ID, and tenant/flow ID with sensitive data masked.
2. Locate the **actual channel bean** from the <code>ApplicationContext</code>, not just from documentation names.
3. Determine whether it is a <code>DirectChannel</code>, <code>PublishSubscribeChannel</code>, <code>ExecutorChannel</code>, <code>QueueChannel</code>, or reactive channel.
4. If it is a <code>SubscribableChannel</code>, read the subscriber count **at the time of state capture**; if it is a queue, check the receiver/poller.
5. When subscriber count is 0, check whether the endpoint is declared, started, wired to the right channel, or was stopped/destroyed.
6. When count is greater than 0, proceed to inspect handler errors, routers, filters, advice, transactions, and downstream branches.
7. Create a minimal reproduction with a test covering thread boundaries and channel-type assertions.

Do not immediately try to solve it by increasing <code>sendTimeout</code>: that is not a fix for a channel with no subscribers.

## 5. Measuring Subscriber Count at Runtime

Spring Integration provides the <code>SubscribableChannelManagement</code> interface with <code>getSubscriberCount()</code> for direct-dispatch channels. Implementations such as <code>DirectChannel</code>, <code>ExecutorChannel</code>, and <code>PublishSubscribeChannel</code> support this API.

~~~java
@Component
public class ChannelInspector {
    private final ApplicationContext applicationContext;

    public ChannelInspector(ApplicationContext applicationContext) {
        this.applicationContext = applicationContext;
    }

    public void inspect(String channelBeanName) {
        Object bean = applicationContext.getBean(channelBeanName);
        if (bean instanceof SubscribableChannelManagement managed) {
            System.out.printf(
                "channel=%s, type=%s, subscribers=%d%n",
                channelBeanName,
                bean.getClass().getSimpleName(),
                managed.getSubscriberCount());
        } else if (bean instanceof PollableChannel) {
            System.out.printf(
                "channel=%s is PollableChannel (no direct subscribers)%n",
                channelBeanName);
        } else {
            System.out.printf(
                "channel=%s, type=%s: check its specific contract%n",
                channelBeanName,
                bean.getClass().getName());
        }
    }
}
~~~

Key types: <code>org.springframework.integration.support.management.SubscribableChannelManagement</code>, <code>org.springframework.messaging.PollableChannel</code>, <code>org.springframework.context.ApplicationContext</code>, <code>org.springframework.stereotype.Component</code>.

Usage example:

~~~java
inspector.inspect("orders.input");
// channel=orders.input, type=DirectChannel, subscribers=1
~~~

**Note:** Subscriber count is a snapshot, not a lock guaranteeing the state will not change. Another thread can stop the endpoint immediately after you read <code>1</code>. With dynamic flows or rolling deployments, take repeated timestamped measurements and correlate them with lifecycle events.

### Listing All Managed Subscribable Channels

~~~java
Map<String, SubscribableChannelManagement> channels =
    applicationContext.getBeansOfType(SubscribableChannelManagement.class);

channels.forEach((name, channel) ->
    log.info("channel={}, subscribers={}",
        name, channel.getSubscriberCount()));
~~~

This is a quick check within a single application context; beans in other contexts, proxies, or dynamic graphs may require separate inspection. Do not list beans and stop at "no subscriber found" without verifying **which context/process** the endpoint runs in.

## 6. Checking Endpoint State Instead of Looking Only at Channels

An <code>EventDrivenConsumer</code> typically subscribes its handler when the endpoint calls <code>start()</code> and unsubscribes on <code>stop()</code>. Therefore, if the handler bean exists yet the channel has no subscribers, inspect the **endpoint lifecycle**:

~~~text
Channel "orders.input" exists   ✓
OrderService bean exists        ✓
EventDrivenConsumer bean        ✓
isRunning()                     ✗
Subscriber count                0
~~~

This is the case where **wiring exists but the endpoint is inactive**. Typical causes:

- <code>autoStartup=false</code> due to production or test configuration.
- Startup phase has not been reached or a bean failed to start.
- The endpoint was stopped via control plane/JMX/Control Bus or orchestration code.
- A dynamic <code>IntegrationFlow</code> was removed/destroyed.
- A conditional configuration/profile prevented the endpoint from being created.
- A test used <code>@SpringIntegrationTest(noAutoStartup=...)</code> and has not started the endpoint manually.

For an endpoint with a stable ID, you can look it up:

~~~java
SmartLifecycle consumer =
    applicationContext.getBean("orders.consumer", SmartLifecycle.class);

log.info("orders.consumer running={}, autoStartup={}",
    consumer.isRunning(), consumer.isAutoStartup());
~~~

<code>SmartLifecycle</code> is in <code>org.springframework.context</code>. The bean name <code>orders.consumer</code> must match the **actual endpoint ID**, not the service class name. If the application did not assign an ID, inspect the topology/bean registry to find the corresponding endpoint.

**Do not blindly force auto-start in production just because an endpoint is stopped.** Check why it stopped: source maintenance, deleted tenant, pre-deploy drain, or intentionally delayed startup.

## 7. Fixing Incorrect Wiring: Channel Bean, inputChannel, and Endpoint ID

### Case A — Channel Declared Without a Consumer

~~~java
@Configuration
@EnableIntegration
public class IncorrectConfig {
    @Bean(name = "orders.input")
    DirectChannel ordersInput() {
        return new DirectChannel();
    }

    // No endpoint is subscribing to "orders.input".
}
~~~

When sending a <code>Message</code> to that channel, the channel has no handler to dispatch to. The channel name existing in the Spring context only proves the bean was created, **not** that a consumer is listening.

### Case B — Handler Registered to a Different Channel

~~~java
@Component
public class OrderConsumer {
    @ServiceActivator(inputChannel = "orders.inbound")
    public void process(OrderCommand command) {
        // ...
    }
}

// Meanwhile, the producer sends to the bean named "orders.input".
~~~

If <code>orders.inbound</code> is a valid channel while the producer uses <code>orders.input</code>, each side can initialize without error on its own, leaving <code>orders.input</code> with no subscribers. If the channel does not exist at all, bean/destination resolution may fail before sending.

**Fix:** Standardize channel names by contract, ideally via constants or typed wiring within the same module when appropriate; verify producer code, channel beans, annotations, and router mappings. Do not "hotfix" by creating a bean alias before confirming where the router/gateway is actually supposed to send.

### Case C — Java DSL Creating an Endpoint with the Right Name

~~~java
public record OrderCommand(String orderId, int quantity) {}

@Service
public class OrderService {
    public void process(OrderCommand command) {
        if (command.quantity() <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }
        // business processing; one-way method
    }
}

@Configuration
@EnableIntegration
public class OrdersFlowConfig {
    @Bean(name = "orders.input")
    DirectChannel ordersInput() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow ordersFlow(OrderService service) {
        return IntegrationFlow.from("orders.input")
            .handle(service, "process",
                endpoint -> endpoint.id("orders.consumer"))
            .get();
    }
}
~~~

With the endpoint started normally, <code>orders.input</code> will have a consumer. <code>orders.consumer</code> is the endpoint name for management/testing, while <code>OrderService</code> is the business bean. A <code>void</code> handler is one-way terminal: do not invoke it via a request–reply gateway and expect a reply automatically when no reply setup exists.

Send and verification example:

~~~java
DirectChannel input = context.getBean("orders.input", DirectChannel.class);
assertEquals(1, input.getSubscriberCount());
assertTrue(input.send(MessageBuilder
    .withPayload(new OrderCommand("O-42", 2))
    .setHeader("correlationId", "checkout-O-42")
    .build()));
~~~

Main imports: <code>org.springframework.integration.dsl.IntegrationFlow</code>, <code>org.springframework.integration.config.EnableIntegration</code>, <code>org.springframework.integration.channel.DirectChannel</code>, <code>org.springframework.integration.support.MessageBuilder</code>, and Spring Framework annotations.

### Component Scanning and @EnableIntegration

If a class with <code>@ServiceActivator</code> is outside the component scan scope, it will not become a bean and the endpoint will not be created. If a Spring Integration configuration is disabled by <code>@Profile</code>, <code>@ConditionalOnProperty</code>, or a bean initialization error, the subscriber will also be absent.

In a Spring Boot project, auto-configuration may initialize Spring Integration infrastructure depending on dependencies; in a manual Spring context, <code>@EnableIntegration</code> may be needed. Inspect the **actual context**, rather than assuming the framework scanned a package just because a class has annotations.

## 8. Not Seeing a Reply Does Not Mean There Is No Subscriber

The following two timelines look identical from the outside but have different causes:

~~~mermaid
sequenceDiagram
    participant S as Sender/Gateway
    participant C as DirectChannel
    participant H as Handler
    participant O as Output/Reply
    alt Channel has no subscribers
      S->>C: send(request)
      C--xS: MessageDispatchingException
    else Subscriber exists but handler is one-way
      S->>C: send(request)
      C->>H: handle
      H-->>C: completes, produces no reply
      C-->>S: send succeeds
      Note over S,O: Gateway may time out waiting for a reply
    end
~~~

Thus, when encountering <code>MessageTimeoutException</code> or a gateway timeout:

1. Check whether the channel has subscribers.
2. Check whether the handler produces a reply or is one-way only.
3. Check <code>replyChannel</code>, output channels, and filters/routers.
4. Check whether crossing an <code>ExecutorChannel</code>/<code>QueueChannel</code> delayed the reply.
5. Check whether downstream threw an error or an error flow recovered without returning a reply.

Do not convert a terminal <code>void</code> handler into request–reply just to make a test pass: define the flow's contract explicitly.

## 9. QueueChannel Has No Subscribers: Isolate by Poller

For a <code>QueueChannel</code>, having 0 subscribers does not indicate a problem. Messages are placed into the queue, and a polling consumer retrieves them via <code>receive()</code>.

~~~java
QueueChannel queue = new QueueChannel(2);
Message<String> message = MessageBuilder.withPayload("O-42").build();

assertTrue(queue.send(message));
assertEquals("O-42", queue.receive(0).getPayload());
~~~

If the queue backs up:

| Symptom | What to check |
|---|---|
| Queue depth grows continuously | Poller not running, processing rate slower than send rate, consumer failing |
| Poller <code>isRunning=false</code> | <code>autoStartup</code>, startup error, intentional stop, phase |
| Poller running but not receiving | <code>receiveTimeout</code>, trigger, worker pool, message source, lock/transaction |
| Messages are picked up but never finish | Downstream handler failing, transaction rollback/retry, blocking IO |
| Queue empty yet producer reports send success | Consumer already picked it up quickly; check consumer metrics/logs instead of queue snapshots |
| Persistent queue grows across restarts | <code>JdbcChannelMessageStore</code>, ACK/rollback, deserialization capability and schema |

When a flow uses:

~~~text
orders.queue (QueueChannel) → PollingConsumer → OrderHandler
~~~

do not "fix" it by subscribing a <code>MessageHandler</code> directly to <code>QueueChannel</code>: that interface does not support <code>subscribe()</code>. What you need to check is whether the **poller and endpoint are registered, configured, and started**.

## 10. PublishSubscribeChannel: A Source of Silent Message Loss

<code>PublishSubscribeChannel</code> is commonly used for notifications. With the default configuration, if the subscriber count is 0, <code>send()</code> may still be marked successful because <code>minSubscribers=0</code>.

~~~java
PublishSubscribeChannel notifications = new PublishSubscribeChannel();
assertEquals(0, notifications.getSubscriberCount());
assertTrue(notifications.send(
    MessageBuilder.withPayload("event").build()));
// No handler received the event, yet send is considered successful.
~~~

When delivery is mandatory, you can require subscribers:

~~~java
PublishSubscribeChannel required = new PublishSubscribeChannel(true);

assertThrows(MessageDispatchingException.class, () ->
    required.send(MessageBuilder.withPayload("event").build()));
~~~

<code>MessageDispatchingException</code> is in <code>org.springframework.integration</code>. Meanwhile, <code>setMinSubscribers(n)</code> sets the minimum threshold for <code>send()</code> to be considered successful by the channel. When an executor is configured, success here only confirms enough eligible subscribers existed **at dispatch time**, not that all subscribers finished business processing.

**Do not use <code>requireSubscribers=false</code> to hide errors** if notifications are a required part of a transaction or must reach an audit consumer. When events must not be lost, consider a transactional outbox/durable broker along with redelivery/idempotency contracts.

### Global errorChannel Has Its Own Rules

Spring Integration's default global <code>errorChannel</code> is a special publish–subscribe channel. Since 5.4.3, it is configured with <code>requireSubscribers=true</code> to avoid silently dropping errors when nothing is listening; the property <code>spring.integration.channels.error.requireSubscribers</code> can adjust this behavior.

If a "no subscribers" error appears on <code>errorChannel</code>:

1. Find the **root exception** in the worker/poller/adapter that produced the <code>ErrorMessage</code>.
2. Check whether the error subscriber is registered and still running, or was stopped/shut down.
3. Check whether the message's <code>errorChannel</code> header points to a custom channel, and whether that channel has subscribers.
4. Review source ACK, retry, and transaction behavior, because failure to deliver an <code>ErrorMessage</code> can affect nacking/redelivery decisions.

An error flow is **not** the place to register a <code>message -> {}</code> handler solely to suppress errors: without recording or observing the cause, delivery failures can turn into untraceable losses.

## 11. ExecutorChannel: When Failures Happen on Another Thread

<code>ExecutorChannel</code> also relies on subscribers but dispatches work via an executor. Distinguish two cases:

- **No subscribers at dispatch time:** the channel has no receiver; the error may surface immediately when the producer sends.
- **Subscribers exist but a downstream handler fails:** the producer may already receive a successful send return; the exception occurs on the worker thread and is handled by the configured error handler/error flow.

~~~mermaid
sequenceDiagram
    participant P as Producer thread
    participant C as ExecutorChannel
    participant X as Executor worker
    participant H as Handler
    P->>C: send(message)
    alt no subscribers
       C--xP: dispatch error
    else subscribed
       C->>X: submit task
       C-->>P: send accepted
       X->>H: handle message
       H--xX: exception
       Note over P,H: Errors after handoff are not on the producer call stack
    end
~~~

Do not merely catch exceptions around <code>send()</code> and conclude every message succeeded. Check subscriber counts, executor active/queue/rejection metrics, error handlers, and worker state. Increasing the thread pool will not fix a channel that **has no handler**.

With <code>DirectChannel</code>, the handler runs on the sender's thread and can participate in an active thread-bound transaction. Across an <code>ExecutorChannel</code>, the sender's transaction does not automatically propagate to the worker. Therefore, switching channels to "dodge" a dispatch error can inadvertently alter transaction boundaries, ordering, and retry behavior.

## 12. Dynamic IntegrationFlow: Subscribers Vanishing After Stop/Remove

A dynamic flow can be registered via <code>IntegrationFlowContext</code> and later stopped or destroyed:

~~~java
var registration = flowContext.getRegistrationById("tenant.flow.T42");

if (registration != null) {
    log.info("Flow still has registration, id={}", registration.getId());
    // Inspect isRunning() on the corresponding flow endpoint's SmartLifecycle.
    // Only invoke stop/destroy according to operational procedures.
}
~~~

<code>IntegrationFlowRegistration</code> provides <code>getId()</code>, <code>start()</code>, <code>stop()</code>, and <code>destroy()</code>; **there is no standalone <code>isRunning()</code> method on this interface**. To check whether the component is running, query the corresponding endpoint's <code>SmartLifecycle</code> or graph/lifecycle state.

<code>registration.stop()</code> can cause an event-driven endpoint to unsubscribe from its input channel; <code>registration.destroy()</code> or <code>flowContext.remove(id)</code> removes the registration and managed dependent beans. A shared channel can **continue to exist** even after the subscriber from the deleted flow is gone.

A common race condition:

~~~text
Thread A: checks tenant flow is ACTIVE
Thread B: stops/destroys registration
Thread A: sends to shared DirectChannel
→ MessageDispatchingException: no subscribers remaining
~~~

**Proper handling:** use an admission gate to block new messages before stopping, drain in-flight work, and only then remove the flow. Maintain durable tenant/generation state if multiple pods can provision or delete the same flow. Do not auto-restart a flow belonging to a DELETING tenant merely because a monitor saw subscriber count drop to 0.

After adding or removing dynamic flows, graph topology may be cached. If using <code>IntegrationGraphServer</code>, call <code>rebuild()</code> as needed to see the updated snapshot rather than relying on a stale graph to assume a handler is still subscribed.

## 13. Using IntegrationGraphServer to Inspect Wiring

<code>IntegrationGraphServer</code> exports a runtime graph containing channels, handlers, endpoints, and discovered links. It helps answer:

- Which **channel node** is the producer sending to?
- Does the channel have a corresponding input endpoint?
- Is the endpoint connected to a handler, or is a node isolated?
- After a router/splitter, does any branch terminate at a channel with no consumer?
- How does the current topology differ from before the dynamic registration/deployment?

~~~java
IntegrationGraphServer graphServer =
    applicationContext.getBean(IntegrationGraphServer.class);

Graph snapshot = graphServer.rebuild();
log.debug("Integration topology: {}", snapshot);
~~~

Types belong to <code>org.springframework.integration.graph</code>. This snippet assumes an <code>IntegrationGraphServer</code> bean has been declared (or created by admin infrastructure). <code>rebuild()</code> matters when components were added/removed; <code>getGraph()</code> returns the existing graph snapshot.

**Do not treat the graph as final proof of a single message delivery.** It describes topology at snapshot build time, while <code>SmartLifecycle</code> states and subscriber counts can change right afterward. Combine the graph, start/stop logs, and a controlled test send.

### Places Where Links Commonly Break

| Location | Symptom | Check |
|---|---|---|
| Producer output channel | Logs show sends to unexpected name | Endpoint <code>outputChannel</code>, <code>replyChannel</code> header |
| Router mapping | Only one message type fails while others pass | Router mappings, channel keys, <code>defaultOutputChannel</code> |
| Splitter / aggregator | One fragment fails or group never releases | Correlation, sequence, group store, discard/expire flow |
| Filter | No output and no exception | Filter discard policy, throwExceptionOnRejection |
| Service activator | Handler is created but not subscribed | Endpoint inputChannel, <code>isRunning()</code>, ID/bean |
| Outbound gateway | Request goes out with no reply | Gateway reply timeout, remote I/O, consumer response |
| Error flow | Original error followed by secondary "no subscribers" | Error channel bean, headers, subscriber lifecycle |

## 14. Using Logs and Observation Without Changing Behavior

For hard-to-reproduce incidents, you can enable **scoped** DEBUG logging for relevant packages:

~~~properties
logging.level.org.springframework.integration.channel=DEBUG
logging.level.org.springframework.integration.dispatcher=DEBUG
logging.level.org.springframework.integration.endpoint=DEBUG
~~~

Exact logger names and verbosity depend on version and channel type. Do not leave full TRACE enabled across all of Spring Integration in production if messages contain large payloads or sensitive data.

Log at least:

~~~text
timestamp
channelBeanName, channelType, subscriberCount (if applicable)
endpointId, isRunning, flowId
messageId, correlationId, businessEventId
threadName, exceptionType, failedMessageId
~~~

<code>MessageHeaders.ID</code> identifies a **specific message**; <code>correlationId</code> links steps/batches; business event ID supports idempotency. When a transformer creates a new message or a source redelivers, message IDs can change. Do not attach raw high-cardinality IDs as Micrometer tags on every message.

### Caution with WireTap and Logging Adapters

A <code>WireTap</code> is a channel interceptor that copies/observes messages to a secondary channel. It **does not turn a <code>DirectChannel</code> with 0 subscribers into a channel with a business consumer**. You might see "message entered channel" logs from the wiretap while the primary dispatch still fails.

If you genuinely want to **terminate a one-way flow** and explicitly drop output, use a destination such as <code>nullChannel</code> or a terminal handler per contract. That is an intentional design choice, not a workaround for missing subscribers on a flow required to deliver messages.

## 15. Practice: Reproducing and Fixing No-Subscriber with JUnit 5

### 15.1. DirectChannel Without Subscribers Must Fail

~~~java
@Test
void directChannelWithoutSubscriberFails() {
    DirectChannel channel = new DirectChannel();
    Message<String> request =
        MessageBuilder.withPayload("order-42").build();

    assertEquals(0, channel.getSubscriberCount());
    assertThrows(MessageDispatchingException.class,
        () -> channel.send(request));
}
~~~

This test verifies failure caused by missing subscribers; it does not depend on matching the exact exception message text.

### 15.2. Subscribe and Unsubscribe Change State

~~~java
@Test
void directChannelWorksOnlyWhileHandlerIsSubscribed() {
    DirectChannel channel = new DirectChannel();
    AtomicInteger calls = new AtomicInteger();

    MessageHandler handler = message -> calls.incrementAndGet();
    assertTrue(channel.subscribe(handler));
    assertEquals(1, channel.getSubscriberCount());

    Message<String> request =
        MessageBuilder.withPayload("order-42").build();
    assertTrue(channel.send(request));
    assertEquals(1, calls.get());

    assertTrue(channel.unsubscribe(handler));
    assertEquals(0, channel.getSubscriberCount());
    assertThrows(MessageDispatchingException.class,
        () -> channel.send(request));
}
~~~

Types: <code>org.springframework.integration.channel.DirectChannel</code>, <code>org.springframework.messaging.MessageHandler</code>, <code>org.springframework.integration.MessageDispatchingException</code>, <code>java.util.concurrent.atomic.AtomicInteger</code>, <code>org.springframework.integration.support.MessageBuilder</code>, and JUnit Jupiter assertions.

In a real Spring Integration application, **do not use manual subscribe calls to patch a framework-managed endpoint**. If an endpoint is stopped, fix its lifecycle or wiring and let the framework subscribe/unsubscribe according to its lifecycle.

### 15.3. PublishSubscribeChannel: Verifying Both Policies

~~~java
@Test
void publisherMayAllowZeroSubscribersUnlessRequired() {
    Message<String> message =
        MessageBuilder.withPayload("event").build();

    PublishSubscribeChannel optional = new PublishSubscribeChannel();
    assertEquals(0, optional.getSubscriberCount());
    assertTrue(optional.send(message));

    PublishSubscribeChannel required = new PublishSubscribeChannel(true);
    assertEquals(0, required.getSubscriberCount());
    assertThrows(MessageDispatchingException.class,
        () -> required.send(message));
}
~~~

This test is a reminder that **no exception does not guarantee a consumer exists**. When using publish–subscribe for critical auditing/notifications, the subscriber requirement policy must be reflected in both configuration and tests.

### 15.4. QueueChannel: The Right Criterion Is Poller/Receive

~~~java
@Test
void queueChannelAcceptsWithoutDirectSubscriber() {
    QueueChannel channel = new QueueChannel(1);
    Message<String> message =
        MessageBuilder.withPayload("queued").build();

    assertTrue(channel.send(message));
    assertEquals("queued", channel.receive(0).getPayload());
    assertNull(channel.receive(0));
}
~~~

This test does not prove a polling consumer is running; it only confirms the queue stores and returns messages. To prove the consumer works, test the endpoint with a real trigger/poller or drive it with a mock source and wait for completion.

## 16. Integration Test: Endpoint autoStartup=false Makes the Subscriber Disappear

A very realistic scenario is having both channel and handler beans present, yet the endpoint does not start due to configuration. You can build a minimal Spring context using <code>OrdersFlowConfig</code> from section 7:

~~~java
@SpringJUnitConfig(OrdersFlowConfig.class)
@SpringIntegrationTest(noAutoStartup = "orders.consumer")
class SubscriberLifecycleTest {

    @Autowired
    @Qualifier("orders.input")
    DirectChannel input;

    @Autowired
    @Qualifier("orders.consumer")
    SmartLifecycle endpoint;

    @Test
    void endpointStartChangesSubscriberCount() {
        assertFalse(endpoint.isRunning());
        assertEquals(0, input.getSubscriberCount());

        Message<OrderCommand> request = MessageBuilder
            .withPayload(new OrderCommand("O-42", 2))
            .build();

        assertThrows(MessageDispatchingException.class,
            () -> input.send(request));

        endpoint.start();
        try {
            assertTrue(endpoint.isRunning());
            assertEquals(1, input.getSubscriberCount());
            assertTrue(input.send(request));
        } finally {
            endpoint.stop();
        }

        assertEquals(0, input.getSubscriberCount());
    }
}
~~~

<code>@SpringJUnitConfig</code> is in <code>org.springframework.test.context.junit.jupiter</code>; <code>@SpringIntegrationTest</code> is in <code>org.springframework.integration.test.context</code>. The code demonstrates lifecycle testing; if run in a suite using the Spring TestContext cache, restore the endpoint state as required by the fixture after the test. Do not place <code>@Transactional</code> on the test expecting to infer handler transaction behavior directly.

### What This Test Actually Proves

- Channel and handler beans **can both exist** while the endpoint is stopped.
- For an event-driven <code>DirectChannel</code>, starting the endpoint registers the subscriber.
- Stopping can drop the subscriber count back to 0, causing subsequent sends to fail.
- This test does not yet prove broker redelivery, queue persistence, or processing after an executor handoff.

## 17. When Count Is Greater Than 0 Yet Dispatch Errors Still Appear

Subscriber count is a necessary condition for a dispatching channel, not a guarantee that every message will be processed successfully.

| Symptom | What may be happening |
|---|---|
| <code>getSubscriberCount()=1</code> yet earlier logs show errors | Endpoint just started after the incident; snapshot was taken at a different time |
| Error reports channel B, inspecting channel A shows subscribers | Router/transformer routed to a **different channel** |
| Multiple subscribers exist but handler A always throws | Dispatcher tries handlers per failover/load-balancing; read the full exception chain |
| <code>ExecutorChannel</code> has subscribers, no output | Worker has not run yet, executor overloaded, handler threw after handoff |
| <code>PublishSubscribeChannel</code> has subscribers, send returns success | With an executor, success does not mean subscribers finished |
| Subscribers exist yet gateway times out | Handler did not produce a reply or sent reply to the wrong channel |
| Consumer receives yet business DB does not change | Transaction rolled back, validation/filter rejected message, retry has not succeeded |

For <code>UnicastingDispatcher</code>, an <code>AggregateMessageDeliveryException</code> may occur if every attempted handler throws an exception; that is a case of **handlers exist but failed to process**, distinct from a dispatcher having no handlers. Separate exception types and nested causes so you do not fix the wrong topology.

## 18. Transactions, Retries, and Delivery Consequences

No-subscriber failures can happen **before** any handler executes. In that case, retry on **handler advice** may not trigger because no handler was invoked. To retry a send to an unready channel, you need retry at the **sender/message source**, a durable queue, or a strategy waiting for endpoint startup, depending on business requirements.

| Processing path | Where does the no-subscriber error go? | Consequence to test |
|---|---|---|
| <code>DirectChannel</code> from synchronous gateway/service | Exception can propagate back to sender | Sender-side transaction may roll back if exception is not swallowed |
| Poller sending to <code>DirectChannel</code> | Exception surfaces in the polling task | Error handler and message source rollback/redelivery |
| Kafka/JMS inbound adapter sending to channel | Exception can reach callback/container | ACK, NACK, retry/redelivery per adapter config |
| <code>ExecutorChannel</code> with subscriber then handler fails | Worker thread/error handler | Sender does not necessarily see that error |
| Default <code>PublishSubscribeChannel</code> with no subscribers | May throw no error | Risk of silent event loss; nothing to retry if sender treats it as success |
| <code>QueueChannel</code> with no poller | Enqueue may succeed; no handler runs | Backlog, memory/storage pressure, recovery capability after restart |

**Do not assert that "no subscribers will always redeliver"**: the message source/adapter, transaction manager, ACK mode, and error recovery determine that. If an error flow swallows the exception and returns success, upstream may treat the message as processed even though the business handler never ran.

In systems that must prevent data loss, options worth considering include:

- enabling producers only when consumers are ready, with appropriate health/admission gates;
- placing a durable queue between producer and consumer when downtime tolerance is required;
- applying bounded retry/backoff at boundaries capable of resending messages;
- using business idempotency keys, because retries/redeliveries can create duplicates;
- preserving trace/correlation and failed messages in a DLQ/quarantine per policy.

## 19. Case Study: Three Situations That Look Identical in the UI

### Case A — "Dispatcher has no subscribers" Immediately After Deploy

**Signal:** Producer sends to <code>orders.input</code>, and an exception appears immediately on the request thread. <code>getSubscriberCount()</code> returns 0. Bean <code>orders.consumer</code> exists, but <code>isRunning=false</code>.

**Isolation:** The fault is in endpoint lifecycle, not the repository or business validation. Inspect <code>autoStartup</code>, startup phases, test configuration leaking into runtime, or an earlier stop command.

**Fix:** Start the endpoint through valid operational procedures, add health/admission gates, and test start/stop transitions. Do not raise the gateway timeout.

### Case B — Sending Notifications "Succeeds" but Audit Is Missing

**Signal:** <code>PublishSubscribeChannel.send()</code> returns <code>true</code> with no exception. Subscriber count is 0 because the audit consumer was not scanned into the context.

**Isolation:** Default publish–subscribe policy permits zero subscribers; send result does not prove audit received the event.

**Fix:** Restore wiring; if auditing is mandatory, use <code>requireSubscribers=true</code> and a more reliable event delivery mechanism (outbox/broker), with tests verifying output.

### Case C — Messages "Disappear" as Traffic Increases

**Signal:** <code>QueueChannel.send()</code> continues to succeed, business handlers do not run, and queue depth rises.

**Isolation:** This is not a missing-subscriber error on the channel. The poller may be stopped or blocked by downstream/database/executor bottlenecks. Check <code>isRunning()</code>, poll schedule, throughput, thread dumps, and receive/ACK behavior.

**Fix:** Restore poller/capacity and define a backlog policy; do not subscribe handlers directly to <code>QueueChannel</code>.

## 20. Short Production Runbook

| Order | Verification question | Evidence |
|---|---|---|
| 1 | At which channel did the error occur? | Exception, failed message, stack trace, correlation ID |
| 2 | What is the channel type? | Bean type in Spring context |
| 3 | Does it require an immediate subscriber? | Direct/Executor/PubSub policy vs. Queue/Flux semantics |
| 4 | Count/lifecycle at the time of failure? | Subscriber count, endpoint ID, isRunning, start/stop logs |
| 5 | Does wiring match names and context? | Input/output channels, router branches, endpoint graph |
| 6 | Is a dynamic flow, deploy, or shutdown in progress? | Registration lifecycle, rebuilt graph, app status |
| 7 | Is the error synchronous or on a worker/poller? | Thread, executor metrics, error channel |
| 8 | Was the message ACKed, committed, queued, or retried? | Adapter/source, transaction logs, store, and DLQ |
| 9 | After fixing, is there a test reproducing the exact failure? | JUnit/integration test for no-subscriber, startup, recovery |

Add alerts when **subscriber count equals 0 on channels requiring a consumer**, but only while the endpoint is expected to be RUNNING. Avoid noisy alerts on channels permitted to have zero subscribers or on queue/pollable channels that have no subscriber concept.

### Checklist Before Concluding the Issue Is Resolved

- [ ] Distinguished <code>MessageDispatchingException</code> from gateway timeouts, queue backlogs, and handler exceptions.
- [ ] Identified the exact channel bean and type: <code>Direct</code>/<code>Executor</code>/<code>PublishSubscribe</code>/<code>Queue</code>/<code>Flux</code>.
- [ ] For <code>SubscribableChannel</code>, inspected <code>getSubscriberCount()</code> and endpoint state at the same point in time.
- [ ] Verified <code>@ServiceActivator</code>, Java DSL, or adapter wiring uses the right <code>inputChannel</code>.
- [ ] Checked <code>autoStartup</code>, profiles/component scanning, and dynamic flow stop/remove.
- [ ] For publish–subscribe requiring event delivery, reviewed <code>requireSubscribers</code> and reliability contracts.
- [ ] For queues, measured poller running state, message backlog, and receive/ACK/rollback instead of looking for subscribers.
- [ ] For async flows, observed errors on workers/error channels rather than only catching exceptions around <code>send()</code>.
- [ ] Evaluated retries, transactions, DLQ, and idempotency to avoid losing or duplicating messages during recovery.
- [ ] Added tests for the happy path, no-subscriber failure, and restart/stop within the supported application scope.

**Conclusion:** "Channel has no subscribers" is not a catch-all diagnosis for every missing output. With <code>DirectChannel</code>, missing subscribers typically raise an explicit dispatch error; with <code>PublishSubscribeChannel</code>, messages can be accepted even with nobody listening; with <code>QueueChannel</code>, lack of polling is a backlog issue, not a subscription failure. By following **channel type → subscriber count → endpoint lifecycle → wiring/topology → error and transaction boundaries**, you can pinpoint the exact break in the message flow and recover safely.

## References

- [Spring Integration Reference — Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html)
- [Spring Integration Reference — Configuring Message Channels](https://docs.spring.io/spring-integration/reference/channel/configuration.html)
- [Spring Integration Reference — Message Endpoints](https://docs.spring.io/spring-integration/reference/endpoint.html)
- [Spring Integration Javadoc — SubscribableChannelManagement](https://docs.spring.io/spring-integration/docs/6.3.5/api/org/springframework/integration/support/management/SubscribableChannelManagement.html)
- [Spring Integration Javadoc — MessageDispatchingException](https://docs.spring.io/spring-integration/docs/6.4.x/api/org/springframework/integration/MessageDispatchingException.html)
- [Spring Integration Reference — Integration Graph](https://docs.spring.io/spring-integration/reference/graph.html)
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html)
