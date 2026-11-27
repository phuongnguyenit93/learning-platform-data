# Managed Endpoints and Runtime Properties in Spring Integration

## 1. What Is a Managed Endpoint and Why Manage It at Runtime?

In **SPRING_INTEGRATION_RUNTIME**, a flow may consist of inbound adapters, message channels, consumer endpoints, handlers, pollers, executors, and outbound adapters. Once the application is running, operations teams often need to know **which endpoints are active**, whether **new work intake can be paused**, how to measure latency/throughput, and how to tune flows during maintenance or incidents.

The topic **Control and Management → Managed Endpoints and Runtime Properties** focuses on the ability to:

1. Accurately identify **endpoint IDs**, handler beans, and channels, avoiding managing the wrong object.
2. Understand the `SmartLifecycle` contract: `autoStartup`, `phase`, `start()`, `stop()`, `isRunning()`.
3. Distinguish **configuration properties** from **runtime-manageable** state and operations.
4. Control endpoints via Java APIs, Control Bus, JMX, or appropriate observability tools.
5. Monitor graphs, metrics, logging, threads, pollers, transactions, retries, and in-flight message states.
6. Operate safely during stop/restart, rolling deployments, and dynamic `IntegrationFlow` registration/removal.

**A managed endpoint is not synonymous with a REST endpoint.** In this lesson, an *endpoint* is the Spring Integration component connecting a channel to a handler or message source, such as `EventDrivenConsumer`, `PollingConsumer`, and inbound adapters. *Managed* means the endpoint exposes state, lifecycle, or properties that management tools or application code can inspect and control.

~~~mermaid
flowchart LR
    S["Inbound source"] --> C["MessageChannel"]
    C --> E["Consumer endpoint (SmartLifecycle)"]
    E --> H["MessageHandler"]
    H --> O["Output channel / downstream"]
    M["Control Bus / Java / JMX"] -.->|"start / stop / status"| E
    E -.-> P["Management / Metrics / Graph"]
    P -.-> A["Dashboard / operator"]
~~~

When an endpoint is stopped, the real effect depends on the channel and source type. A `DirectChannel` with no other consumers may reject new messages, whereas a persistent queue may continue holding messages until the poller restarts. Never infer that every `stop()` command means "freeze the entire flow with zero work running".

## 2. Distinguishing Component, Handler, Endpoint, and Flow

Spring Integration does not manage every object the same way:

| Component | Example | Role | Runtime Operations to Watch |
| --- | --- | --- | --- |
| **Channel** | `DirectChannel`, `QueueChannel`, `ExecutorChannel` | Transports messages, defines synchronous/async boundaries | Subscribers, queue depth, send/receive metrics |
| **Handler** | `ServiceActivatingHandler`, custom `MessageHandler` | Processes payload/headers, produces replies or side effects | Exceptions, latency, retries, advice, transactions |
| **Endpoint** | `EventDrivenConsumer`, `PollingConsumer` | Connects channel/source to handler and manages lifecycle | `start`, `stop`, `isRunning`, `autoStartup`, `phase` |
| **Source adapter** | JDBC/file/JMS/HTTP inbound adapter | Creates/receives messages from external systems | Poll/listener lifecycle, acknowledgements |
| **Poller** | `SourcePollingChannelAdapter` or polling consumer | Actively pulls messages on a trigger | Poll interval, `maxMessagesPerPoll`, executor |
| **Integration flow** | Endpoints/channels wired with Java DSL | Orchestration logic along paths | Starting/stopping endpoints, dynamic registration, deregistration |
| **Management view** | Graph, metrics, JMX MBeans | Observes and controls per published contract | Does not create transactions, queues, or retries |

A `@ServiceActivator` method is turned by Spring Integration into a **message handler** plus a **consumer endpoint** sitting in front of the handler. An operator may need to stop the **consumer endpoint** without deleting the business bean.

### IDs Are Not Class Names

~~~text
Business bean:         orderService
Handler adapter:       service-activating handler (framework-created)
Consumer endpoint ID:  orderConsumer
Input channel:         orders
Flow registration ID:  ordersFlow
~~~

These IDs can be related, yet **they are not always identical**. Configuring an explicit ID for an endpoint avoids relying on framework-generated bean names derived from annotations or DSL. Stable IDs also keep logs, JMX object naming, flow graphs, alerts, and Control Bus commands clear across deployments.

**Rule:** to `start()`/`stop()` accurately, identify which bean implements `Lifecycle`/`SmartLifecycle` and its corresponding ID. A custom `MessageHandler` bean does not automatically gain endpoint lifecycle solely because a method carries an annotation.

## 3. `SmartLifecycle`: The Foundational API of Managed Endpoints

Many Spring Integration endpoints extend `AbstractEndpoint` and implement Spring Framework's `SmartLifecycle`. Common management entry points:

~~~java
import org.springframework.context.SmartLifecycle;

SmartLifecycle endpoint = ...;

boolean running = endpoint.isRunning();
boolean auto = endpoint.isAutoStartup();
int phase = endpoint.getPhase();

endpoint.start();
endpoint.stop();
~~~

`Lifecycle`/`SmartLifecycle` are Spring contracts, not unique to Spring Integration. Some adapters have specialized lifecycles, so always verify the actual start/stop behavior of the specific implementation.

| API / Property | Role | Effective Behavior to Understand |
| --- | --- | --- |
| `start()` | Starts the lifecycle component | Activates subscriptions or polling/listener schedules per endpoint type |
| `stop()` | Stops the component | Typically stops accepting new work; in-flight handling depends on the component |
| `isRunning()` | Reports component lifecycle state | Does **not** mean healthy, zero backlog, or error-free |
| `isAutoStartup()` | Whether to auto-start on Spring context refresh | A startup policy, not a switch toggled on every poll |
| `getPhase()` | Lifecycle phase value used for ordering | Higher values normally start later and stop earlier than lower values |
| `stop(Runnable callback)` | Supports callback-based lifecycle stopping | Some components stop asynchronously; the callback signals shutdown completion per contract |

### Phase and Startup Ordering

Within a group of `SmartLifecycle` beans managed by Spring's lifecycle processor:

- At **startup**, components with a smaller `phase` start before components with a larger `phase`.
- At **shutdown**, components with a larger `phase` stop before components with a smaller `phase`.
- Explicit dependencies between beans can affect actual order; `phase` does not replace defining dependencies.

For instance, to ensure outbound resources/channel infrastructure are ready before a listener begins accepting traffic, use appropriate phase/configuration/dependencies. Never use "magic" phase numbers without testing startup and shutdown of the specific adapters.

~~~mermaid
sequenceDiagram
    participant C as ApplicationContext
    participant D as Downstream infrastructure
    participant P as Poller consumer
    participant O as Operator
    C->>D: start() lower phase
    C->>P: start() higher phase
    O->>P: stop()
    P-->>O: isRunning() = false
    O->>P: start()
    P-->>O: isRunning() = true
    C->>P: stop() on shutdown
    C->>D: stop() on shutdown
~~~

If an endpoint has `autoStartup=false`, it **does not start automatically on context refresh**, though it can be started via API or management mechanisms once ready.

## 4. Which Properties Can Actually Change at Runtime?

Here is the crucial distinction between a **managed property**, a **configuration property**, and **runtime state**.

| Property / Object | Where Configured | Mutable While Running? | Notes |
| --- | --- | --- | --- |
| Endpoint ID / bean name | DSL, annotation, XML, bean registration | **Should not** change on a live bean | Used to identify components and management targets |
| `autoStartup` | Endpoint config before context start | Usually treated as **startup configuration** | To toggle immediately, use `start()`/`stop()` |
| `phase` | Lifecycle config | Usually **startup/shutdown configuration** | Changing while running does not immediately reorder flows |
| `isRunning()` | Runtime lifecycle | **Readable** | Does not guarantee the last message committed |
| `start()`/`stop()` | Endpoint operation | **Yes**, when supported by the component | Requires authorization and understanding of in-flight work |
| Input/output channel | Endpoint config | Do not treat as a default runtime hot-switch | Often requires stopping and recreating the flow/endpoint |
| Poller `fixedDelay`/`cron` | Trigger/poller config | Depends on implementation and trigger API | No universal button guarantees live updates on all pollers |
| `maxMessagesPerPoll` | Poller config | Depends on actual endpoint/setter/JMX API | Not the same as a concurrency limit |
| Executor pool/queue capacity | Executor bean | Depends on executor type and configuration | Adjusting pools can affect backpressure |
| Retry/advice chain | Endpoint/handler config | Usually requires reconfiguration/re-registration | Changing advice arbitrarily mid-flight can break semantics |
| Transaction manager / message store | Endpoint/source wiring | **Do not** swap arbitrarily while live | Swapping resources can compromise atomicity/durability |
| Metrics/observability | Integration management/registry | Depends on version/config | Not every component exposes identical counters/JMX operations |

**Do not conclude from the presence of a Java setter that it is safe to call while the endpoint is running.** Many setters exist for *pre-initialization* configuration. For structural changes (channels, pollers, retry policies), the safe approach is usually preparing a new flow version, testing it, stopping/draining the old flow, and performing a controlled cutover.

## 5. Complete Java Example: Starting and Stopping `EventDrivenConsumer`

Java 17+, Spring Boot, and Spring Integration example. Place all code in `ManagedEndpointDemoApplication.java` under package `demo.integration`. Requires Spring Integration core or a compatible `spring-boot-starter-integration`.

The demo includes:

- A `DirectChannel` named `orders`.
- An `EventDrivenConsumer` named `orderConsumer` with `autoStartup=false`.
- An `ApplicationRunner` that explicitly starts the consumer, sends a message successfully, stops it, and attempts to send after stopping.
- A simple message handler to observe which messages actually reach the endpoint.

~~~java
package demo.integration;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.endpoint.EventDrivenConsumer;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageDeliveryException;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.SubscribableChannel;
import org.springframework.messaging.support.MessageBuilder;

@SpringBootApplication
@EnableIntegration
public class ManagedEndpointDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ManagedEndpointDemoApplication.class, args);
    }

    @Bean("orders")
    SubscribableChannel orders() {
        return new DirectChannel();
    }

    @Bean("orderConsumer")
    EventDrivenConsumer orderConsumer(
            @Qualifier("orders") SubscribableChannel orders) {

        MessageHandler handler = message -> {
            System.out.printf("HANDLE payload=%s traceId=%s thread=%s%n",
                    message.getPayload(),
                    message.getHeaders().get("traceId"),
                    Thread.currentThread().getName());
        };

        EventDrivenConsumer endpoint =
                new EventDrivenConsumer(orders, handler);
        endpoint.setAutoStartup(false);
        endpoint.setPhase(100);
        return endpoint;
    }

    @Bean
    ApplicationRunner demo(
            @Qualifier("orderConsumer") EventDrivenConsumer endpoint,
            @Qualifier("orders") MessageChannel orders) {

        return args -> {
            System.out.println("BEFORE running=" + endpoint.isRunning());

            endpoint.start();
            try {
                System.out.println("AFTER_START running="
                        + endpoint.isRunning());

                orders.send(MessageBuilder
                        .withPayload("ORD-101")
                        .setHeader("traceId", "trace-101")
                        .build());

                endpoint.stop();
                System.out.println("AFTER_STOP running="
                        + endpoint.isRunning());

                try {
                    orders.send(MessageBuilder
                            .withPayload("ORD-102")
                            .setHeader("traceId", "trace-102")
                            .build());
                }
                catch (MessageDeliveryException ex) {
                    System.out.println("SEND_AFTER_STOP_FAILED: "
                            + ex.getClass().getSimpleName());
                }
            }
            finally {
                endpoint.stop();
            }
        };
    }
}
~~~

Behavioral output:

~~~text
BEFORE running=false
AFTER_START running=true
HANDLE payload=ORD-101 traceId=trace-101 thread=...
AFTER_STOP running=false
SEND_AFTER_STOP_FAILED: MessageDeliveryException
~~~

Explanation:

1. The consumer bean is created, but `autoStartup=false` prevents the Spring context from auto-starting it.
2. `endpoint.start()` subscribes the consumer to the corresponding `SubscribableChannel`.
3. `DirectChannel` invokes the handler **synchronously** on the sending thread; message `ORD-101` is processed.
4. `endpoint.stop()` stops the consumer's subscription.
5. When `DirectChannel` has **no remaining subscribers**, sending `ORD-102` can throw `MessageDeliveryException` because there is no receiver.
6. `isRunning()` reports the consumer's state, **not** proof that database/HTTP calls succeeded or that backlog is zero.

If there is **another consumer** on the same `orders` channel, stopping one consumer does not guarantee new messages are rejected; the dispatcher may route to the remaining subscriber. With channels backed by executors or pollers, commit and error timing also differ.

### Why Grab the Endpoint Bean Instead of Calling the Handler Directly?

If code simply does:

~~~java
orderService.process(order);
~~~

you have invoked the **business method directly**, bypassing the messaging endpoint, channel, transaction/advice/retry wiring, and lifecycle. A `start()`/`stop()` command must target the Spring Integration–managed endpoint, not the business method.

## 6. Annotations and Java DSL: IDs for Management

In real projects, most endpoints are created via annotations or DSL rather than instantiating `EventDrivenConsumer` manually.

Java DSL example (an alternative to Section 5's example):

~~~java
@Bean
IntegrationFlow processingFlow(OrderService service) {
    return IntegrationFlow.from("orders")
        .handle(service, "process", e -> e
            .id("ordersHandlerEndpoint")
            .autoStartup(false))
        .get();
}
~~~

This snippet assumes `OrderService`/channels are defined and DSL imports are present. The endpoint ID `ordersHandlerEndpoint` can be looked up and controlled via the bean registered in the context by the DSL. **Do not** keep a second consumer on the same channel if your example assumes a single consumer.

Some endpoint annotations support lifecycle settings—for example, `@ServiceActivator` supports input channel, `autoStartup`, and `phase` depending on version. When using annotations, inspect the **generated endpoint bean** and its ID rather than guessing from the handler class name. Always check dependency versions before copying annotation/DSL attributes.

### IDs and Endpoint Names in the Runtime Graph

- Custom handler bean name may be `orderService`.
- Explicit DSL endpoint ID may be `ordersHandlerEndpoint`.
- Flow ID may be `processingFlow`.
- Input channel is `orders`.

The graph and JMX may present these identities differently; never perform loose string searches and accidentally stop the wrong adapter.

## 7. Control Bus: Controlling Endpoints via Messages

The **Control Bus** in Spring Integration is a pattern that turns a **message containing a control expression** into an invocation on an allowed bean/operation. It is convenient for message-driven operations, but it is a **sensitive control channel** that must be carefully protected.

Java DSL configuration example:

~~~java
@Bean
IntegrationFlow controlFlow() {
    return IntegrationFlow.from("controlCommands")
            .controlBus()
            .get();
}
~~~

Requires the `controlCommands` channel and endpoint beans in the context. A permitted SpEL payload can invoke:

~~~text
@orderConsumer.stop()
@orderConsumer.start()
@orderConsumer.isRunning()
~~~

Commands can be sent from authorized internal code:

~~~java
MessageChannel commands = ...;

commands.send(MessageBuilder
        .withPayload("@orderConsumer.stop()")
        .build());
~~~

**Important note:** The Control Bus is not a public HTTP endpoint. SpEL can invoke operations on beans; never let payloads from untrusted clients pass directly into a Control Bus. Restrict command sources, enforce authentication/authorization, allowlist commands, record audit logs (actor, timestamp, reason), enforce timeouts, and have a recovery procedure if something is stopped by mistake.

Also, channel acceptance of a command **does not** always mean endpoint shutdown has finished across async boundaries. For traffic-impacting changes, verify `isRunning()` and measure in-flight work.

### When Does the Control Bus Make Sense?

| Need | Should You Use Control Bus? | Notes |
| --- | --- | --- |
| Temporarily pause an internal poller with a known ID | Possibly | With auditing and authorization |
| Restart a consumer per runbook | Possibly | Only when messages won't be lost |
| Let any HTTP client submit free-form SpEL | **No** | Risks invoking unauthorized beans/operations |
| Swap a transaction manager while the flow runs | Not solved by `start/stop` | Requires tested migration/re-registration |
| Check `isRunning()` from management code | Can use Java API directly | Often simpler within the same process |
| Control a multi-instance cluster | Requires additional design | Each context has its own endpoints/lifecycles |

A command sent to instance A's Control Bus **does not automatically stop** the corresponding endpoint on instance B. Multi-node coordination or per-instance execution via a controlled operational mechanism is required.

## 8. JMX and Management Properties

Spring Integration supports JMX management via exporter/integration management mechanisms depending on version. When JMX is configured, eligible endpoints/channels/handlers appear as **MBeans** with framework-exported attributes and operations.

Commonly observable capabilities:

| Management Area | Examples to Inspect | What Not to Assume |
| --- | --- | --- |
| Lifecycle | Running state, start/stop on supported endpoints | Every bean with a name has an MBean |
| Handler/channel stats | Send count, receive count, error count, duration | Identical metric/MBean attribute names across versions |
| Polling | Active poller, messages per poll | `fixedDelay` can be hot-updated in every implementation |
| Channel | Queue depth, active subscribers, dispatch behavior | Every channel has a persistent backlog |
| Dynamic flows | Flow registrations, endpoint state | JMX automatically tracks arbitrary unregistered custom state |
| Errors | Exception rates and error flows | Having an error count implies a durable DLQ exists |

**A JMX MBean `ObjectName` is not simply the bean name.** `IntegrationMBeanExporter` applies naming domains, types, and object-name mappings depending on integration config/version. Never hardcode JMX `ObjectName` strings without inspecting an actual running instance.

Spring Boot Actuator can also expose **`integrationgraph`** and metrics endpoints when required dependencies/modules are installed and exposed. The graph primarily serves **topology observation**, not command execution with lifecycle privileges.

On security:

- Never expose remote JMX publicly without authentication, TLS, and network policies.
- Never expose all sensitive Actuator endpoints to the internet.
- Limit headers/payloads containing private data in graphs, metrics, and logs.
- Separate read-only monitoring from state-mutating Control Bus/JMX operations.

## 9. Graph and Observability: Running Does Not Mean Healthy

Spring Integration can describe runtime topology: channels, handlers, endpoints, links, and flow components. The graph helps answer:

- Which channel feeds which handler?
- Which endpoint ID needs to be stopped?
- Is any branch missing a consumer?
- Is there an async boundary between two handlers?
- Which components belong to a newly registered dynamic flow?

However, the graph shows **structure and partial state**, not proof that messages committed. A running endpoint can still:

- Block on I/O and fail to complete messages.
- Have a running poller receiving zero messages.
- Have a full executor queue and saturated thread pool.
- Continuously retry/backoff with near-zero throughput.
- Route messages to an error channel whose recovery consumer is failing.
- Hold message groups indefinitely because correlation/release strategies never complete.

### Three Layers of Observability

| Layer | Question | Signals |
| --- | --- | --- |
| **Topology/lifecycle** | Does the endpoint exist and is it running? | Graph, `isRunning()`, bean state, JMX |
| **Flow-level performance** | How long from input → output, and what is throughput? | Metrics, tracing, queue/backlog, poll duration |
| **Business-level completion** | Did the order commit, did the broker ack, was the error stored? | DB/broker/DLQ/outbox, `eventId` and `traceId` |

Never put raw `orderId`, `eventId`, or `correlationId` into metric tags due to high cardinality. Use endpoint, channel, outcome, exception class, and traffic group as tags; put business IDs in controlled traces/logs.

## 10. Poller Properties and Runtime Impact

Polling consumers actively pull messages from a `PollableChannel` or inbound message source. Common parameters:

- `fixedDelay` / `fixedRate` / `cron`: poll trigger schedule.
- `maxMessagesPerPoll`: maximum messages processed per poll cycle.
- `receiveTimeout`: wait time when the channel has no message.
- `taskExecutor`: where poll tasks execute when configured.
- `adviceChain`: may wrap transactional polling, retries, or custom advice.
- `errorChannel`/error handler: where exceptions at the polling boundary are captured.

**Illustrative** XML example (not a standalone XML file):

~~~xml
<int:service-activator
        id="ordersPollingConsumer"
        input-channel="ordersQueue"
        ref="orderHandler"
        method="process"
        auto-startup="false"
        phase="100">
    <int:poller fixed-delay="1000"
                max-messages-per-poll="10"/>
</int:service-activator>
~~~

Requires configuring the `int` namespace, an `ordersQueue` channel of type `PollableChannel`, the `orderHandler` bean, and transaction/error infrastructure where needed. This is a **pre-runtime configuration example**, not a promise that every poller attribute can be hot-edited via JMX while running.

### When Stopping a Polling Consumer

~~~text
QueueChannel + persistent MessageStore
       |
       v
PollingConsumer stop()
       |
       +-- No new polls once stopped
       +-- New messages may stay in the queue if producer/store permits
       +-- In-flight handling/transactions must be observed until completion
       +-- Queue depth grows if producers keep sending
~~~

Do not assume `stop()` undoes a `receive()` that already happened, rolls back an active transaction, or returns messages to a queue. Behavior depends on the source/store, transaction manager, retry/error policy, and exact timing.

### Poller Metrics Worth Tracking

| Metric | Investigative Value |
| --- | --- |
| Poll trigger count | Is the poller actually being scheduled? |
| Messages received/processed | Are polls empty or carrying data? |
| Poll duration p95/p99 | Are polls stretched by slow handlers/transactions? |
| Oldest queued message age | Is backlog becoming severe? |
| Queue depth | Is the producer outpacing the consumer? |
| Executor active/queued tasks | Is the thread pool saturated? |
| Errors/retries/recoveries | Are failures dragging down throughput? |

If a poller is intentionally paused, dashboards should display **paused intentionally** rather than raising a total-outage alert, while monitoring queue capacity and retention to prevent backlog-induced data loss.

## 11. `ExecutorChannel`: Stopping Endpoints and In-Flight Tasks

With `ExecutorChannel`, messages are handed off asynchronously to worker threads. Calling `stop()` on a consumer endpoint does not cancel or roll back tasks already handed off.

~~~mermaid
sequenceDiagram
    participant S as Sender thread
    participant C as ExecutorChannel
    participant W as Worker
    participant O as Operator
    S->>C: send(M1)
    C->>W: submit task M1
    C-->>S: handoff accepted
    O->>W: stop consumer endpoint
    Note over W: M1 may already be executing
    W->>W: handler/transaction/retry
    Note over O,W: Must observe in-flight tasks
~~~

Key points to remember:

- Senders may treat the handoff as successful before the handler ever runs.
- Worker exceptions do not automatically propagate to a caller that already left the stack.
- Imperative transaction contexts normally do not propagate across worker threads.
- Stopping may halt accepting new work, yet running tasks may not finish immediately.
- When shutting down an executor, define policies for queued tasks, active tasks, interruption, and rejections.
- Without durable storage before handoff, restarts can lose accepted but unfinished work.

**Endpoint management differs from executor management.** Endpoint `isRunning()` and executor `activeCount`/`queueSize` are distinct signals. A stopped endpoint may still have tasks finishing.

## 12. Transactions, Retries, and `ErrorMessage` During Endpoint Control

| Scenario | Risk | Operational Handling |
| --- | --- | --- |
| Stop before handler finishes | In-flight work uncommitted; callers may time out | Graceful drain; check outstanding work |
| Stop during a transactional poll cycle | Message received but not yet committed/rolled back | Wait for transaction boundary; check source redelivery |
| Restart the same consumer | Accumulated backlog surges in | Rate limiting, concurrency limits, monitor downstream capacity |
| Retry/backoff in progress | Workers hold resources after stop is issued | Review retry policy, timeouts, active invocation count |
| Recovery sends `ErrorMessage` | Error consumer might be stopped or missing | Keep error flows active before starting intake |
| Dynamic flow destroyed | Reply/error destinations or subscriptions may vanish | Drain and verify all in-flight work/correlation |
| Rolling deployment | Two app versions consume the same source concurrently | Verify message ownership, idempotency, and compatibility |

### Stop Is Not Rollback

A handler that wrote to the DB and committed before endpoint stop **is not undone** just because lifecycle state changed. Conversely, a transactional inbound adapter may roll back on processing failure, causing the broker to redeliver after the consumer restarts.

**Do not confuse them:** `errorChannel` is a path for `ErrorMessage`; it does not automatically roll back an old transaction or guarantee a message was saved to a DLQ. Across stops/restarts, always verify **business state** and **acknowledgement state** on the actual resources.

### Safe Sequence to Pause Processing

1. Stop sources from generating new messages or pause the appropriate inbound endpoints.
2. Inspect in-flight tasks, active pollers, and open transactions.
3. Ensure error/recovery paths still have active consumers to handle trailing failures.
4. Wait or enforce a controlled timeout/drain policy.
5. Record achieved state: committed events, queue depth, DLQ entries, and unfinished work.
6. Perform maintenance/deployment/configuration changes.
7. Start downstream dependencies first, then enable inbound/consumer endpoints in order.
8. Monitor drain rate, retry storms, duplicates, and post-restart latency.

## 13. Cluster-Wide Start/Stop: Each `ApplicationContext` Is Separate

In multi-pod systems, each pod owns its **own** `ApplicationContext`, registry, endpoint lifecycles, and executors.

~~~text
Pod A: endpoint ordersConsumer -> running
Pod B: endpoint ordersConsumer -> running
Pod C: endpoint ordersConsumer -> stopped
~~~

Stopping the endpoint on pod C **does not** stop pods A or B. When reading from a shared broker/queue, stopping one consumer shifts load onto the remaining consumers and can overheat them.

For clusters:

- Maintain a controller/runbook tracking target instances, management permissions, and per-instance results.
- Distinguish **draining one instance** from **pausing the entire logical flow**.
- When using a shared message store/lock registry, verify ownership and concurrency rules.
- During scale-in/rolling restarts, handle acks, rebalances, pending tasks, and retries per adapter behavior.
- Ensure dynamic registrations do not collide on IDs within a context, and understand that identical IDs across contexts do not refer to the same bean object.
- Never let a networked Control Bus turn into cluster-wide remote code execution.

## 14. Dynamically Registering and Destroying `IntegrationFlow`s

Spring Integration provides `IntegrationFlowContext` for runtime flow registration. This fits scenarios where you must spin up or tear down a group of endpoints with their own lifecycle (e.g., per tenant), rather than mutating configuration of already-initialized beans.

Java DSL illustration:

~~~java
IntegrationFlow newFlow = flow -> flow
        .filter(String.class, s -> !s.isBlank())
        .handle(message -> System.out.println(message.getPayload()));

IntegrationFlowContext.IntegrationFlowRegistration registration =
        flowContext.registration(newFlow)
                .id("tenantAFlow")
                .autoStartup(false)
                .register();

registration.start();
// ... send messages via the registration's input channel or messaging template ...
registration.stop();
registration.destroy();
~~~

This is a design snippet requiring an `IntegrationFlowContext` bean and version-appropriate imports; the input channel must be resolved before sending real messages. Builder/registration APIs may vary slightly across Spring Integration versions. **Do not** write code that destroys a flow immediately while replies are pending without verifying cleanup and acks.

### `stop` vs. `destroy`

| Action | Effect | When to Use |
| --- | --- | --- |
| `start()` | Allows endpoint/flow registration to receive and process per contract | Resuming a prepared flow |
| `stop()` | Halts or restricts accepting new work | Maintenance, load shedding, resumable pauses |
| `destroy()` registration | Removes dynamic beans/registration from context | Tenant/service no longer needs the flow, deploying new config |
| Stop inbound adapter | Halts creating/receiving messages from a specific source | Pausing ingress, draining downstream |
| Stop polling consumer | Halts polling a queue | Retaining backlog if queue/store supports it |

Dynamic flows may share infrastructure beans with other flows: message stores, executors, transaction managers, `RequestHandlerRetryAdvice`, error channels. Destroying one flow **does not** remove shared dependencies.

## 15. Managing Other Runtime Properties vs. Dynamic Reconfiguration

Suppose you want to change a poll interval from 1 second to 5 seconds. There are at least three strategies:

| Strategy | Advantage | What Must Be Checked |
| --- | --- | --- |
| Modify a property via a component-**supported** management operation | No restart needed if the API guarantees it | Thread safety, whether triggers actually reschedule properly |
| Stop/reconfigure/start the endpoint using official APIs | Clearer boundaries | Whether setters are permitted post-initialization, whether tasks are active |
| Spin up a new registration/flow and shift traffic | Easier to test and roll back configuration | No duplicate consumers, no lost in-flight work, clean IDs/keys |

**Do not** mutate arbitrary Spring bean fields via JMX/SpEL and assume schedulers, transaction interceptors, and handler dispatchers will pick them up automatically. Every hot-update must be verified against **implementation and version**. For structural changes, versioning config, registering a new flow, and performing a controlled cutover is usually far more reliable.

### Concurrency and Throughput

Changing `maxMessagesPerPoll` or executor pool size can boost throughput, yet:

- The poller might be waiting on `receiveTimeout` or I/O rather than being capped by max messages.
- A synchronous `DirectChannel` will not benefit from tuning another executor if it still runs on the sender thread.
- An aggregator/`LockRegistry` hitting one hot correlation key still serializes critical sections.
- Databases/remote APIs have rate limits; adding workers can trigger retry storms.
- Repeatedly stopping/starting does not fix serialization bugs, message store issues, or correlation strategies.

Measure p95/p99 latency, queue depth, retry/error rates, and active thread counts before and after tuning.

## 16. Diagnosing an Endpoint That Is "Running With No Output"

| Symptom | Possible Cause | How to Verify |
| --- | --- | --- |
| `isRunning()=true` yet zero messages | Empty source/poller, upstream stopped, wrong channel | Graph, send/receive counts, source metrics |
| After `start()`, `DirectChannel` still throws no-subscribers error | Started wrong bean, wrong input channel, endpoint init error | Endpoint ID, actual subscribers, logs |
| `stop()` called yet processing logs continue | In-flight worker/poller or another consumer | Active tasks, correlation, thread timeline |
| One consumer stopped yet messages still flow | Channel has another subscriber | Topology/dispatcher |
| Poller running yet queue depth rises | Slow handler, DB locks, small `maxMessagesPerPoll` | Poll duration, executor, store latency |
| Executor queue full while endpoint running | Thread pool saturation, blocking I/O/retries | Queue size, active workers, rejection counts |
| Flow restarted and processed duplicates | Broker redelivery, source replay, missing idempotency | `eventId`, ack logs, inbox/outbox |
| Endpoint missing in JMX | Export not enabled or different naming/filter rules | Management config, `MBeanServer` registry |
| Integration graph lacks newly created flow | Graph snapshot not refreshed / management disabled | Registration state and graph endpoint |
| Error count increases yet `errorChannel` is empty | Sync errors thrown to caller, publisher signals, or other error handler | Thread/boundary, error publishing config |
| Locks/transactions linger after stop | In-flight operations, TTL/lease, un-drained work | Thread dump, transaction duration, lock ownership |
| `autoStartup=false` yet consumer still receives | Another consumer/flow shares the same source | Graph, bean IDs, handler subscriptions |

### Evidence-Driven Debugging Procedure

1. **Identify IDs:** endpoint bean, handler bean, input channel, source adapter, and flow registration.
2. **Read state:** `isRunning`, startup phase, `autoStartup` config, and build version.
3. **Trace topology:** from source → channel → endpoint → handler → output/error channels.
4. **Collect traffic metrics:** messages in/out, queue depth, oldest message age, poll rate, success/failure counts.
5. **Mark async boundaries:** executors, pollers, broker listeners, reactive publishers.
6. **Cross-check transactions/retries:** commit points, swallowed/trapped exceptions, retry callbacks, and DLQ.
7. **Test stop/start in a controlled environment:** confirm zero message loss and zero duplicate consumers.
8. **Evaluate aftermath:** backlogs, side effects, correlation groups, and resource cleanup.

You can enable controlled DEBUG logging for Spring Integration endpoints/dispatchers and Spring transactions. Never log sensitive payloads or headers in production solely for debugging.

## 17. Operational Scenarios with Runbooks

### Scenario A — Stopping a Poller for Database Maintenance

**Context:** A `QueueChannel` backed by a persistent message store feeds a polling consumer writing to a DB. The DB is about to be upgraded.

**Recommended procedure:**

1. Confirm the queue is durable and upstream sources can safely accumulate backlog within capacity limits.
2. Stop the polling consumer (exact endpoint ID).
3. Wait for active transactions to finish and verify zero in-flight database writes remain.
4. Perform DB maintenance; verify error flows were not inadvertently disabled.
5. Start the poller; monitor drain rate and redelivery errors.
6. Reconcile `eventId`/DB records against the broker/store to verify no gaps or duplicates.

**Pitfall:** if the queue is in-memory only and pods restart during maintenance, backlog will be lost. `stop()` does not turn an in-memory queue into a persistent store.

### Scenario B — Pausing an Inbound Adapter During Downstream Outage

**Context:** Payment API returns 503; handlers are retrying and tying up workers.

**Recommendation:** throttle intake by stopping the inbound endpoint while ensuring source messages remain safe per ack policy; wait for current attempts to finish or time out, keep error/recovery consumers alive, then resume at a bounded rate.

**Pitfall:** a source adapter that already read and acked messages before stopping may not redeliver them; verify the adapter contract rather than relying on the lifecycle flag.

### Scenario C — Registering a New Tenant Flow

**Context:** Tenant A requires a dedicated routing handler.

**Recommendation:** register the flow with a stable ID and `autoStartup=false`, verify output/error dependencies, start at the right moment, monitor `eventId`/correlation, and stop/drain before destroying when the tenant offboards.

**Pitfall:** avoid accidentally creating two competing consumers on the same input channel; avoid destroying while request-reply gateways still await responses.

## 18. Practice Exercises

1. **Basic lifecycle:** run `ManagedEndpointDemoApplication`, verify `isRunning()` before/after start and after stop; observe send errors when `DirectChannel` has no subscribers.
2. **Multiple consumers:** attach a second subscriber to the same channel, stop one consumer, and explain why `send()` can still succeed.
3. **Startup phases:** create two endpoints with different phases and log start/stop hooks to observe lifecycle order during context startup and shutdown.
4. **Control Bus:** configure an internal channel and `.controlBus()` flow, send `@orderConsumer.stop()`/`start()`; restrict command senders and write audit logs.
5. **Poller:** replace `DirectChannel` with `QueueChannel` and a polling consumer; inspect backlog on stop and across restarts (compare in-memory vs. persistent store).
6. **Executor:** use `ExecutorChannel`; run a slow task, call stop, and verify that endpoint state and in-flight task count are separate quantities.
7. **JMX:** enable integration management in a version-appropriate test environment; locate the endpoint by ID and read its running state and exported counters.
8. **Graph:** enable the Actuator integration graph per version, cross-check endpoints/channels against flow definitions, and detect unconsumed branches.
9. **Fault injection:** make a handler throw after writing to the DB; compare exception behavior across `DirectChannel`, executor, and poller.
10. **Retry/backoff:** trigger transient failures and stop the endpoint while retries are pending; record when stop was requested vs. when in-flight retries finished.
11. **Dynamic flows:** register a new `IntegrationFlow`, start/stop/destroy by ID, and verify no orphaned subscriptions or reply handlers remain.
12. **Rolling restart:** run two app instances sharing a broker/message store, stop one and bring it back up, and measure redeliveries and duplicates.
13. **Monitoring:** build a dashboard covering running state, in/out throughput, p95 latency, queue age, error rate, and DLQ depth.
14. **Runbook:** author a pause/drain/resume procedure with explicit verification conditions rather than bare stop/start steps.

### Self-Check Questions

- How does a handler bean differ from a consumer endpoint?
- How does `autoStartup=false` differ from calling `stop()` after startup?
- How does a smaller `phase` affect startup order and shutdown order?
- Why does `isRunning()=true` not prove business messages committed?
- When stopping one consumer on a `DirectChannel` with multiple subscribers, are new messages rejected?
- With a `QueueChannel` and poller, where does the backlog reside after stopping?
- Why can a Control Bus command introduce security risks?
- When sending to an `ExecutorChannel`, why can the sender return success before the handler executes?
- Is changing a poller trigger while running guaranteed to take effect immediately?
- Does stopping an endpoint in pod A stop the entire cluster?
- When should you register/destroy a new flow rather than mutating a live bean?

## 19. Pre-Production Checklist

- Endpoint IDs/flow IDs are stable; diagrams cover source → channel → endpoint → handler → error paths.
- Components supporting `start/stop` and readable status are clearly identified.
- `autoStartup`/`phase` are tested alongside bean dependencies; phase is never treated as transaction semantics.
- Control Bus/JMX access is restricted, audited, and guarded by command allowlists.
- Drain plans cover in-flight tasks, transactions, and broker acks during stops/restarts.
- Stopping pollers will not push backlog past capacity/retention limits; queue durability is verified.
- Retries, recovery/error consumers, and message stores continue operating per contract while intake is paused.
- Clusters have per-instance orchestration rather than assuming local controls affect all pods.
- Only properties with clear runtime hot-update contracts are modified live; structural changes use cutover/re-registration.
- Metrics/graphs/alerts cover health, queue depth, throughput, p95 latency, and failure rates.
- Fault injection tests prove zero message loss and no unintended duplicate side effects outside contract.

## 20. Official References

- [Spring Integration — System Management](https://docs.spring.io/spring-integration/reference/system-management.html): component management, Control Bus, monitoring, and graph.
- [Spring Integration — Control Bus](https://docs.spring.io/spring-integration/reference/control-bus.html): SpEL control commands and message-based management.
- [Spring Integration — JMX Support](https://docs.spring.io/spring-integration/reference/jmx.html): managing MBeans and exported attributes/operations.
- [Spring Integration — Message Endpoints](https://docs.spring.io/spring-integration/reference/endpoint.html): polling/event-driven consumers and endpoint lifecycle.
- [Spring Integration — Polling Consumer](https://docs.spring.io/spring-integration/reference/polling-consumer.html): poller triggers and `maxMessagesPerPoll`.
- [Spring Integration — Java DSL Dynamic and Runtime Flows](https://docs.spring.io/spring-integration/reference/dsl/java-runtime-flows.html): dynamic flow registration via `IntegrationFlowContext`.
- [Spring Integration — Integration Graph](https://docs.spring.io/spring-integration/reference/graph.html): topology and integration graph management.
- [Spring Integration Javadoc — AbstractEndpoint](https://docs.spring.io/spring-integration/api/org/springframework/integration/endpoint/AbstractEndpoint.html): lifecycle, startup, and phase.
- [Spring Framework — Lifecycle / SmartLifecycle](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html): managing start/stop and phases.
- [Spring Boot Actuator — Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): exposure and security configuration for management endpoints.
