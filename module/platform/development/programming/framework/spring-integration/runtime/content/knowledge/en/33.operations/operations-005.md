# Restarting endpoints and reconnecting producers in Spring Integration runtime

## 1. Distinguishing restart, reconnect, and replay

In the **SPRING_INTEGRATION_RUNTIME** module, a message flow is orchestrated across `MessageChannel`, endpoints, consumers, pollers, and executors, then reaches handlers, transactions, message stores, or an external system. When a TCP, MQTT, or broker connection drops, operators may say "restart producer", yet that phrase covers **three actions with different scopes**:

1. **Restart endpoint:** calling `stop()` then `start()` on a lifecycle-managed bean to halt and reopen receiving/sending messages per the component's contract.
2. **Reconnect transport:** re-establishing an adapter's or connection factory's connection/socket/session, often without restarting the entire endpoint.
3. **Retry or replay logical message:** resending an event already received without a confirmed outcome; requires inspecting acknowledgements, transactions, message stores, and idempotency.

This is directly the focus of **Operations → Restarting endpoints and reconnecting producers**. The goal is evidence-based operations: pick the right target object, verify state, handle in-flight messages, restore connections, and confirm business outcomes—never simply calling a method and assuming success.

**Key principle:** `isRunning() == true` does not mean a socket is connected. A connected socket does not mean the remote peer processed the message. `retryConnection()` does not mean messages that failed before the disconnect were replayed.

~~~mermaid
flowchart TD
    S["Source / producer"] --> A["Adapter / endpoint"]
    A --> L["Lifecycle: running?"]
    A --> T["Transport: connected?"]
    A --> M["Message outcome: ack/commit?"]
    L --> O["stop() / start()"]
    T --> R["Reconnect policy / retryConnection()"]
    M --> P["Retry / replay + idempotency"]
    O --> V["Validation"]
    R --> V
    P --> V
    V --> H["Healthy processing, no lost/duplicate events"]
~~~

The sections below use Java 17+, Spring Integration 6.x/7.x, noting API differences across versions. TCP examples require `spring-integration-ip` and a TCP test server. This exercise does **not** run Gradle or STEP 6 academic QA.

## 2. Is "Producer" an inbound producer or an outbound sender?

In Spring Integration, an inbound adapter typically **produces** messages onto a channel; an outbound handler **sends** messages to another system. With TCP, there can be both an inbound adapter actively connecting to a server to receive data and an outbound adapter actively opening a client connection on start.

| Component | Path | Managed object | Common recovery |
| --- | --- | --- | --- |
| `EventDrivenConsumer` + `DirectChannel` | Channel → handler | Consumer endpoint/subscription | `start()/stop()`, no socket |
| `SourcePollingChannelAdapter` | Remote source → channel | Poller, message source, session factory | Poller lifecycle and session recovery |
| TCP inbound adapter server mode | TCP peer → inbound channel | Server connection factory/listener | Listener lifecycle and TCP events |
| TCP inbound adapter `client-mode=true` | Client connects to peer then receives | Client-mode adapter/connection factory | Client-mode reconnect while running |
| TCP outbound adapter `client-mode=true` | Channel → TCP server | `TcpSendingMessageHandler` and client factory | Scheduler, `retryConnection()` |
| JMS/AMQP listener | Broker → message flow | Listener container/connection factory | Container recovery + ack/requeue |
| MQTT inbound/outbound | Broker ↔ flow | MQTT client/adapters | Paho automatic reconnect or lifecycle |
| HTTP outbound handler | Flow → HTTP API | HTTP client/pool | Request retry, connection pool, not default endpoint stop |

**Do not build a generic `allProducers.reconnect()` method assuming every adapter shares the same API.** For each flow, first identify the exact bean owning the connection, endpoint lifecycle, channel, and adapter version.

## 3. Three state axes to monitor

| Lifecycle | Connection health | Business outcome | Interpretation |
| --- | --- | --- | --- |
| Stopped | Disconnected | No new work accepted | Intentional pause or startup incomplete |
| Running | Disconnected | Unknown | Endpoint alive but disconnected; may be retrying |
| Running | Connected | Pending | Socket open yet messages remain in queue/worker/transaction |
| Running | Connected | Acked/committed | Evidence that logical events completed |
| Stopping | Socket may still exist | In-flight | Stopping does not necessarily drain all work |
| Running | Flapping | Retrying | Risk of reconnect storm, duplicates, and backlog |

`TcpSendingMessageHandler.isClientModeConnected()` reflects the client-mode connection state at **the instant of the call**, not a guarantee that the server will remain healthy for the next few minutes. Business completion must be proven via reply/ack/commit or a safe probe operation, never a connection flag alone.

## 4. Spring lifecycle: start, stop, autoStartup, and phase

Many integration endpoints implement `SmartLifecycle` or equivalent via `AbstractEndpoint`. Foundational APIs:

~~~java
import org.springframework.context.SmartLifecycle;

// In the application, inject the right endpoint bean.
SmartLifecycle endpoint = endpointBean;

boolean running = endpoint.isRunning();
boolean autoStart = endpoint.isAutoStartup();
int phase = endpoint.getPhase();

endpoint.stop();
endpoint.start();
~~~

| Operation/property | Meaning | Limitation |
| --- | --- | --- |
| `start()` | Starts lifecycle, subscribes/schedules/listens per implementation | Does not mean connected or delivery complete |
| `stop()` | Requests endpoint to stop per lifecycle | Does not automatically cancel/roll back all in-flight work |
| `isRunning()` | Component state | Does not prove throughput, empty queues, or healthy downstream |
| `autoStartup` | Starts on context refresh or waits for explicit start | Does not auto-start when remote server recovers if endpoint was stopped |
| `phase` | `SmartLifecycle` startup/shutdown order | Does not replace dependencies or transaction boundaries |
| `stop(Runnable)` | Callback when component completes stop per contract | Does not replace DB commit or broker ack confirmation |

In Spring's lifecycle processor, lower-phase components typically start before higher-phase ones and stop in reverse order. Still, actual order also depends on bean dependencies and implementation. **Restarting an endpoint differs from restarting the ApplicationContext/pod**: restarting the process also loses in-memory queues, cached state, or pending tasks unless durable.

~~~mermaid
stateDiagram-v2
    [*] --> Created
    Created --> Running: autoStartup or start()
    Running --> Stopped: stop()
    Stopped --> Running: start()
    Running --> [*]: context shutdown
    Stopped --> [*]: destroy
~~~

This diagram simplifies lifecycle; an adapter can have intermediate internal states such as CONNECTING, FAILED, or QUIESCING.

## 5. How stopping an endpoint affects the flow

### DirectChannel and EventDrivenConsumer

`EventDrivenConsumer` subscribes/unsubscribes on a `SubscribableChannel` during start/stop. If `DirectChannel` has only one subscriber, stopping it causes new sends to throw `MessageDeliveryException`. If another subscriber remains on the channel, messages can still be dispatched.

**Mistake:** stopping handler A, seeing the sender still succeed, and concluding `stop()` does not work. Check whether the dispatcher has consumer B on the same channel.

### QueueChannel and poller

`QueueChannel` is pollable. When the polling consumer is stopped, producers can keep enqueuing, increasing queue depth. If the queue is in-memory only, restarting the pod will **not make backlog durable**. With a persistent `MessageStore` and proper transactions, pending messages can survive restart per provider contract.

A poller that already pulled a message and is running its handler does not automatically roll back just because stop was called.

### ExecutorChannel

`send()` typically hands a task to an executor. Stopping the endpoint does not automatically cancel already-submitted tasks. Observe active workers, pending queue, rejection policy, and worker-thread transactions. The sender may receive an "accepted" send result while business processing fails later.

### Inbound adapters and listener containers

Stopping an inbound adapter limits **new work**, yet source-specific acks, sessions, leases, offsets, and consumer rebalances must be interpreted per adapter. The broker may redeliver unacked messages after restart; this is **not a bug by itself** under an at-least-once contract.

## 6. Runnable Java 17 example: stopping and starting a consumer

Put all code in `EndpointRestartDemoApplication.java`, package `demo.integration`. This example uses Spring Boot + Spring Integration core with no TCP server. It demonstrates lifecycle with `DirectChannel` and `EventDrivenConsumer` before diving into network connections.

~~~java
package demo.integration;

import java.util.concurrent.atomic.AtomicInteger;

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
public class EndpointRestartDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(EndpointRestartDemoApplication.class, args);
    }

    @Bean("orders")
    SubscribableChannel orders() {
        return new DirectChannel();
    }

    @Bean
    AtomicInteger processedCount() {
        return new AtomicInteger();
    }

    @Bean("ordersConsumer")
    EventDrivenConsumer ordersConsumer(
            @Qualifier("orders") SubscribableChannel input,
            AtomicInteger processedCount) {

        MessageHandler handler = message -> {
            int count = processedCount.incrementAndGet();
            System.out.printf(
                "HANDLE #%d payload=%s eventId=%s thread=%s%n",
                count, message.getPayload(),
                message.getHeaders().get("eventId"),
                Thread.currentThread().getName());
        };

        EventDrivenConsumer consumer =
                new EventDrivenConsumer(input, handler);

        consumer.setAutoStartup(false);
        consumer.setPhase(100);
        return consumer;
    }

    @Bean
    ApplicationRunner demo(
            @Qualifier("ordersConsumer") EventDrivenConsumer endpoint,
            @Qualifier("orders") MessageChannel orders,
            AtomicInteger processedCount) {

        return args -> {
            System.out.println("INITIAL running=" + endpoint.isRunning());

            endpoint.start();
            System.out.println("STARTED running=" + endpoint.isRunning());
            send(orders, "ORD-101");

            endpoint.stop();
            System.out.println("STOPPED running=" + endpoint.isRunning());

            try {
                send(orders, "ORD-102");
                System.out.println("UNEXPECTED accepted while stopped");
            }
            catch (MessageDeliveryException ex) {
                System.out.println("SEND_WHILE_STOPPED "
                        + ex.getClass().getSimpleName());
            }

            endpoint.start();
            System.out.println("RESTARTED running=" + endpoint.isRunning());
            send(orders, "ORD-103");

            System.out.println("PROCESSED=" + processedCount.get());
            endpoint.stop();
        };
    }

    private static void send(MessageChannel channel, String payload) {
        boolean accepted = channel.send(MessageBuilder
                .withPayload(payload)
                .setHeader("eventId", "evt-" + payload)
                .build());
        if (!accepted) {
            throw new IllegalStateException("Send rejected: " + payload);
        }
    }
}
~~~

Logical output:

~~~text
INITIAL running=false
STARTED running=true
HANDLE #1 payload=ORD-101 eventId=evt-ORD-101 thread=...
STOPPED running=false
SEND_WHILE_STOPPED MessageDeliveryException
RESTARTED running=true
HANDLE #2 payload=ORD-103 eventId=evt-ORD-103 thread=...
PROCESSED=2
~~~

Explanation:

1. The consumer bean is created but does not auto-start.
2. `start()` registers the subscription on `DirectChannel`.
3. `ORD-101` is handled synchronously during `send`.
4. `stop()` unsubscribes; with no subscriber left on the channel, `ORD-102` has nowhere to go.
5. `start()` again lets `ORD-103` flow through.
6. **`ORD-102` is not automatically saved or replayed.** `DirectChannel` is not a persistent queue.
7. The counter proves the handler ran, **not that a DB committed or broker acked**.

If multiple subscribers exist, the assumption "sending after stop always rejects" no longer holds. If the channel uses an executor, an accepted send does not prove the handler finished either.

## 7. TCP client-mode: real reconnect mechanics

According to the Spring Integration TCP Adapters and IP Endpoint Reference:

- The TCP inbound adapter defaults to **server mode**, listening for clients. With `client-mode=true`, the inbound adapter uses a client connection factory to actively connect to a remote server and **receive** data.
- A TCP outbound adapter using a client factory normally connects **when sending the first message**. With `client-mode=true`, the adapter attempts to connect at **start**.
- Client-mode requires the client connection factory to have `single-use=false` (long-lived socket).
- `retry-interval` is the interval between reconnect attempts in **milliseconds**, defaulting to **60,000 ms** per the IP adapters attribute reference.
- The adapter uses a `TaskScheduler` to schedule reconnects; on disconnect, outbound client-mode can reconnect via the scheduler or when the next message is sent.
- On a **running** client-mode adapter, you can call `retryConnection()` to request an immediate connection attempt; inspect status with `isClientModeConnected()`.

~~~mermaid
stateDiagram-v2
    [*] --> Stopped
    Stopped --> RunningDisconnected: start()
    RunningDisconnected --> Connecting: retry interval or retryConnection()
    Connecting --> RunningConnected: connect succeeded
    Connecting --> RunningDisconnected: connect failed
    RunningConnected --> RunningDisconnected: peer closed socket / network error
    RunningConnected --> Stopped: stop()
    RunningDisconnected --> Stopped: stop()
~~~

**Do not assume `retryInterval=5s` means every outage recovers within 5s.** Connection timeouts, DNS, TLS, scheduler load, remote overload, half-open socket detection, and business readiness checks all affect recovery time.

### Comparing the two connection directions

| TCP adapter | `client-mode=false` | `client-mode=true` |
| --- | --- | --- |
| Inbound (receive data) | Usually server mode listening | Actively connects to server to receive |
| Outbound (send data) | Client connection on first message sent | Actively connects on endpoint start |
| Required config in client-mode | Setup-dependent | Client factory, `single-use=false`, retry interval |
| Manual reconnect | No general meaning | `retryConnection()` on running `ClientModeCapable` |

## 8. TCP outbound: Java configuration with reconnect

Requires `spring-integration-ip` and a TCP test peer listening at `127.0.0.1:7001`. Put the code below in `TcpOutboundConfiguration.java`; this is **complete configuration for the outbound component** though a full flow still needs a Spring Boot application, a peer-compatible serializer, and the `tcpOutboundRequests` channel.

~~~java
package demo.integration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.ip.tcp.TcpSendingMessageHandler;
import org.springframework.integration.ip.tcp.connection.TcpNetClientConnectionFactory;
import org.springframework.messaging.MessageChannel;

@Configuration
class TcpOutboundConfiguration {

    @Bean("tcpOutboundRequests")
    MessageChannel tcpOutboundRequests() {
        return new DirectChannel();
    }

    @Bean("tcpClientFactory")
    TcpNetClientConnectionFactory tcpClientFactory() {
        TcpNetClientConnectionFactory factory =
                new TcpNetClientConnectionFactory("127.0.0.1", 7001);
        factory.setSingleUse(false);
        return factory;
    }

    @Bean("tcpOutboundAdapter")
    @ServiceActivator(inputChannel = "tcpOutboundRequests")
    TcpSendingMessageHandler tcpOutboundAdapter(
            TcpNetClientConnectionFactory tcpClientFactory) {

        TcpSendingMessageHandler adapter =
                new TcpSendingMessageHandler();
        adapter.setConnectionFactory(tcpClientFactory);
        adapter.setClientMode(true);
        adapter.setRetryInterval(5_000L); // milliseconds
        return adapter;
    }
}
~~~

Sample dependencies in a project using Spring Boot BOM:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-integration")
    implementation("org.springframework.integration:spring-integration-ip")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

**Do not send arbitrary payloads to a TCP peer without matching framing/codec.** Spring Integration provides TCP serializers/deserializers; defaults must match the specific server protocol. A connected socket does not prove the peer can decode your message.

### Java API to inspect and request reconnect

`TcpSendingMessageHandler` implements `ClientModeCapable`, exposing `isClientModeConnected()` and `retryConnection()`.

~~~java
package demo.integration;

import java.util.Map;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.ip.tcp.TcpSendingMessageHandler;
import org.springframework.stereotype.Service;

@Service
class TcpConnectionOperations {

    private final TcpSendingMessageHandler sender;

    TcpConnectionOperations(
            @Qualifier("tcpOutboundAdapter")
            TcpSendingMessageHandler sender) {
        this.sender = sender;
    }

    Map<String, Boolean> connectionSnapshot() {
        return Map.of(
                "running", sender.isRunning(),
                "clientMode", sender.isClientMode(),
                "connected", sender.isClientModeConnected());
    }

    synchronized boolean reconnectIfNeeded() {
        if (!sender.isRunning()) {
            // Already stopped: manage endpoint lifecycle first.
            return false;
        }
        if (!sender.isClientMode()) {
            throw new IllegalStateException("Not a client-mode adapter");
        }
        if (sender.isClientModeConnected()) {
            return true;
        }
        sender.retryConnection();

        // Immediate snapshot, does not guarantee attempt has finished.
        return sender.isClientModeConnected();
    }
}
~~~

Returning `false` **does not prove reconnect completely failed**: the attempt may still be in progress. Never write `while (!connected) retryConnection()`, which triggers tight retry loops and overloads the server. Wait for TCP events or use a bounded await with an appropriate interval.

### Two lifecycle layers can differ

~~~text
tcpOutboundRequests (channel)
    -> ServiceActivator consumer endpoint (subscription)
    -> TcpSendingMessageHandler (handler + client-mode lifecycle)
    -> TcpNetClientConnectionFactory
    -> TCP peer
~~~

Stopping the consumer endpoint prevents new messages from arriving from the channel, yet does not automatically disconnect sockets held by the handler/factory. Reconnecting the sender does not automatically re-subscribe a stopped consumer. Runbooks must target **the exact bean and layer**.

## 9. TCP XML: outbound and inbound client-mode

The fragments below are **two alternative configurations**, not a recommendation for both adapters to share one client factory without verifying ownership.

### Outbound: connect on start

~~~xml
<int-ip:tcp-connection-factory
        id="outboundClientFactory"
        type="client"
        host="127.0.0.1"
        port="7001"
        single-use="false"/>

<int-ip:tcp-outbound-channel-adapter
        id="tcpOutboundAdapter"
        channel="tcpOutboundRequests"
        connection-factory="outboundClientFactory"
        client-mode="true"
        retry-interval="5000"/>
~~~

### Inbound: client connects to receive

~~~xml
<int-ip:tcp-connection-factory
        id="inboundClientFactory"
        type="client"
        host="127.0.0.1"
        port="7002"
        single-use="false"/>

<int-ip:tcp-inbound-channel-adapter
        id="tcpInboundClient"
        channel="tcpInboundEvents"
        connection-factory="inboundClientFactory"
        client-mode="true"
        retry-interval="5000"/>
~~~

Requires the `int-ip` namespace, channels, and matching codec/remote server; these are not standalone XML files. Both use `retry-interval` in **milliseconds**, not business handler retry backoff.

## 10. Control Bus: message-driven operations under control

Spring Integration **Control Bus** allows sending internal commands to invoke exposed/filtered operations on beans. Syntax varies by version/documentation:

- **Current Control Bus reference**: command payloads of the form `beanName.methodName`, with arguments passed in the `IntegrationMessageHeaderAccessor.CONTROL_BUS_ARGUMENTS` header.
- **Older documentation used SpEL expressions**: such as `@beanName.start()` or `@adapter.retryConnection()`.

Current syntax examples:

~~~text
ordersConsumer.stop
ordersConsumer.start
tcpOutboundAdapter.retryConnection
tcpOutboundAdapter.isClientModeConnected
~~~

Older documentation:

~~~text
@ordersConsumer.stop()
@ordersConsumer.start()
@tcpOutboundAdapter.retryConnection()
@tcpOutboundAdapter.isClientModeConnected()
~~~

**Do not mix both syntaxes in the same deployment.** Check `ControlBusCommandRegistry` and your exact version's documentation. Calling Java bean APIs directly within the same process can be simpler when writing operational code.

Illustrative Java DSL:

~~~java
@Bean
IntegrationFlow controlFlow() {
    return IntegrationFlow.from("controlCommands")
            .controlBus()
            .get();
}
~~~

Requires the `controlCommands` channel and imports. This is a **state-mutating management channel**—never expose it openly to untrusted HTTP/Kafka/client inputs. Enforce authentication/authorization, command allowlists, auditing, and transport security. A command on one pod **does not** automatically affect endpoints on other pods.

## 11. TCP connection events: observe rather than guess

Spring Integration IP publishes application events when connections open, close, or fail:

| Event | Meaning |
| --- | --- |
| `TcpConnectionOpenEvent` | Connection has opened |
| `TcpConnectionCloseEvent` | Connection has closed |
| `TcpConnectionExceptionEvent` | Exception on a connection |
| `TcpConnectionFailedEvent` | Client failed to establish a connection |
| `TcpDeserializationExceptionEvent` | Protocol/frame decode error |
| `TcpConnectionFailedCorrelationEvent` | No matching connection ID / late reply |

You can subscribe via `@EventListener` in the same ApplicationContext:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.integration.ip.tcp.connection.TcpConnectionOpenEvent;
import org.springframework.integration.ip.tcp.connection.TcpConnectionCloseEvent;
import org.springframework.integration.ip.tcp.connection.TcpConnectionFailedEvent;
import org.springframework.stereotype.Component;

@Component
class TcpOperationsEvents {

    @EventListener
    public void opened(TcpConnectionOpenEvent event) {
        System.out.println("TCP_OPEN " + event.getConnectionId());
    }

    @EventListener
    public void closed(TcpConnectionCloseEvent event) {
        System.out.println("TCP_CLOSE " + event.getConnectionId());
    }

    @EventListener
    public void failed(TcpConnectionFailedEvent event) {
        System.out.println("TCP_FAILED " + event);
    }
}
~~~

This is an auxiliary bean used alongside TCP configuration. Never put raw connection IDs, IP/credentials, or full exception payloads into metric labels. **A `TcpConnectionOpenEvent` only means transport opened**, not that the remote peer successfully received business events.

## 12. Distinguishing reconnect, handler retry, and broker redelivery

| Mechanism | Trigger condition | Effect | What it does not guarantee |
| --- | --- | --- | --- |
| TCP reconnect | Socket lost/cannot be created | Re-establishes transport path | Replay of already-sent messages |
| `RequestHandlerRetryAdvice` | Handler throws exception | Repeats handler invocation | Exactly-once or remote transaction |
| Reactor `retryWhen` | Publisher emits `onError` | Resubscribes publisher | Non-duplication of side effects |
| Broker redelivery | Message unacked or transaction rolled back | Redelivers the same logical event | That external peer did not commit |
| Outbox replay | Pending event without confirmed outcome | Resends event from durable state | Non-duplication if receiver lacks idempotency |

Dangerous scenario:

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant R as Remote peer
    participant D as Receiver DB
    P->>R: send eventId=evt-42
    R->>D: commit order
    Note over P,R: TCP disconnects before response reaches client
    P->>P: reconnect socket
    Note over P: Unsure whether event committed
    P->>R: replay evt-42 (keep same idempotency key)
    R->>D: check inbox/unique eventId
    D-->>R: event already exists
    R-->>P: return prior outcome, no duplicate commit
~~~

If a new event ID is generated on replay, the receiver cannot deduplicate based on transport alone. **Transport reconnect is not exactly-once delivery.** For unknown outcomes, check remote/outbox state and retry only under an idempotency contract. Never assume "TCP wrote bytes" means the remote DB committed.

## 13. When to restart an endpoint vs when to reconnect only

| Symptom | Preferred action | What to verify afterward |
| --- | --- | --- |
| Endpoint `isRunning=false` from pause, dependencies ready | `start()` the exact bean | Subscription/poll/listener active |
| Endpoint running yet TCP client disconnected | Built-in reconnect policy or controlled `retryConnection()` | Open event, connected state |
| Connected yet backlog rising | Inspect poller/executor/handler/store, not just reconnect | Queue age and completion rate |
| Continuous payload decode failures | Fix framing/serializer/schema | Test message decodes cleanly |
| Business handler throws 4xx or invalid data | Classify errors/quarantine on retry | Clear outcome, no reconnect loop |
| Expired credentials/certificates | Rotate secret/config, recreate if adapter does not reload | Authenticated connection and probe |
| Dynamic flow structure changed | `IntegrationFlowContext` register/stop/destroy per contract | New graph, no orphan handlers |
| Broker listener interrupted | Container-specific recovery | Ack, consumer lag, redelivery |
| Process/VM failure | Rolling restart with drain and persistence | No lost backlog or duplicate side effects |

**Choose the least intrusive action targeting the true root cause.** Restarting the entire process can drop in-memory state, trigger cluster-wide reconnect storms, and obscure investigation of a single socket fault.

## 14. Safe restart runbook: pause → drain → recover → verify

A good runbook defines **entry criteria**, **target objects**, **deadlines**, **success criteria**, and **rollback**. For flows with transactions or brokers, never start with `kill -9`/pod restart if connection recovery at the right layer is still viable.

~~~mermaid
flowchart TD
    A["Error detected"] --> B["Snapshot state"]
    B --> C{"Endpoint running?"}
    C -->|No| D["Verify valid pause; prepare start"]
    C -->|Yes| E{"Transport disconnected?"}
    E -->|Yes| F["Reconnect policy / bounded retryConnection"]
    E -->|No| G["Inspect backlog, poller, handler, transaction"]
    D --> H["Pause ingress, drain if needed"]
    F --> H
    G --> H
    H --> I["Chosen action"]
    I --> J["Verify lifecycle + connection"]
    J --> K["Synthetic message + commit/ack"]
    K --> L{"Criteria met?"}
    L -->|Yes| M["Resume load gradually, monitor backlog/duplicates"]
    L -->|No| N["Escalate / rollback / quarantine"]
~~~

### Before taking action: snapshot checklist

| Question | Data to record |
| --- | --- |
| Which instance is affected? | Pod/hostname, deployment version, tenant/partition |
| Which bean holds the connection? | Handler ID, adapter ID, connection factory name |
| Which endpoint can stop/start? | `isRunning()`, `isAutoStartup()`, `phase` |
| What is the socket/session state? | Connected flag, TCP open/close/failed events |
| Are messages in-flight? | Active workers, pending replies, transactional records |
| Where is backlog stored? | In-memory `QueueChannel` or persistent `MessageStore`/broker |
| Is the error flow working? | `errorChannel`, recovery handler, DLQ/sink |
| Is there replay risk? | Last acked offset/sequence, event IDs, unknown outcomes |
| Is the remote peer ready? | DNS/TLS/auth, host:port, listener, rate limits |
| Were there recent config changes? | Endpoint, serializer, connection pool, secrets, timeouts |

### Sequence when a graceful restart is needed

1. **Control intake:** stop or throttle inbound traffic at the right source to avoid exceeding backlog capacity. For brokers, use pause/stop per adapter contract—never delete queues.
2. **Wait for in-flight work:** monitor active workers, uncommitted transactions, pending replies, and error/retry callbacks with a finite timeout.
3. **Keep error paths alive:** do not stop recovery consumers prematurely, because final failures may still need to be persisted to a DLQ.
4. **Apply intervention:** if only a TCP socket dropped, prefer reconnect; if an endpoint stopped or handler config broke, consider start/stop or rebuilding the flow via the right API.
5. **Verify layer by layer:** lifecycle running, transport connected, test message processed properly, and durable outcome confirmed.
6. **Resume at bounded rate:** poller max messages, listener concurrency, or producer rate; monitor queue age and failure rate.
7. **Record incident timeline:** detection, command, reconnect attempt, first open event, first successful business operation, return to normal throughput.

`stop()` **is not a rollback command**; a message committed to the DB before stop will not be "undone". Conversely, an unacked delivery can be redelivered by the broker after start.

## 15. Graceful drain depends on the endpoint boundary

### DirectChannel

If a sender invokes a handler synchronously, stopping the endpoint only changes subscription/lifecycle. Do not assume it interrupts the running thread or undoes side effects. Multiple subscribers may exist on the same channel.

### ExecutorChannel

A task accepted by an executor may still sit in its queue or be running when an operator stops the consumer. `isRunning()==false` **does not prove the executor queue is empty**. On application shutdown, behavior depends on executor `waitForTasksToCompleteOnShutdown`, task rejection, cancellation, and interruption policies.

If work lives only in executor memory, restarting the process before completion risks losing tasks. For at-least-once processing, you usually need a durable inbound broker/queue store and consistent transactions/retries.

### QueueChannel and PollingConsumer

Stopping a polling consumer prevents new polls once stop completes per contract, yet already-dequeued/in-flight messages must follow the source transaction. Producers can keep enqueuing and growing queue depth. With a persistent store, verify readback across restarts with real tests rather than trusting `QueueChannel.getQueueSize()` alone.

### TCP outbound

Stopping a consumer endpoint in front of `TcpSendingMessageHandler` prevents new messages from reaching the handler, but does not mean the socket closed as expected. Stopping the handler or connection factory can affect other flows if they share the resource. Check bean ownership and invoke **the API of the exact right object**.

## 16. When excessive reconnecting causes an outage

A **reconnect storm** occurs when many instances or failing messages simultaneously recreate connections at high frequency, overloading the peer and causing continued failures.

~~~text
Pod A: connect -> fail -> 1s -> connect -> fail ...
Pod B: connect -> fail -> 1s -> connect -> fail ...
Pod C: connect -> fail -> 1s -> connect -> fail ...
Remote TCP server: accept backlog spikes, socket quota exhausted
~~~

Common causes:

- Retry interval too short relative to peer recovery time.
- Many pods starting simultaneously during a rolling deployment.
- Calling `retryConnection()` on every handler failure even while the built-in scheduler already retries.
- Permanent DNS/TLS/auth errors retried infinitely.
- Load balancers/firewalls/NAT closing idle sockets with mismatched heartbeats.
- Remote server enforcing connection quotas while exponential retries synchronize.
- Framing/serializer mismatch causing the peer to close the socket immediately.

### Backoff, cooldown, and jitter

If writing reconnect orchestration outside the adapter, you can apply capped exponential backoff with jitter:

\[
d_n = \min(d_{\max}, d_0 \cdot 2^n) \times (0.5 + 0.5U)
\]

With `U` uniformly distributed in `[0,1]`. For example `d0=1s`, `dmax=30s` prevents many instances from retrying at the exact same instant. **This is an illustrative policy formula, not the TCP adapter's default algorithm**: `retry-interval` in Spring Integration TCP is a configured retry interval, not exponential backoff by default.

Principles:

- Prefer the adapter's built-in reconnect mechanism when stable.
- If building a custom coordinator, ensure it **does not fire in parallel** with unnecessary internal attempts.
- An operator should trigger bounded manual reconnects only after understanding state and cause.
- Enforce retry budgets, cooldowns, and escalation after repeated failures.
- Never retry immutable credential/serializer errors as if they were transient network glitches.
- Across many pods, stagger startups and watch the peer's connection quota.

## 17. Readiness and liveness while a socket is disconnected

~~~text
Spring Boot application started
    != Endpoint running
    != TCP connection established
    != Business path ready to commit
~~~

A client-mode adapter can be **running yet disconnected** while the scheduler keeps attempting to connect. Distinguish:

| Health indicator | Question | Example |
| --- | --- | --- |
| Liveness | Is the process still operating normally? | JVM serves health endpoint, no deadlock |
| Readiness | Can the instance currently take traffic per policy? | Required dependencies or durable buffering have capacity |
| Transport status | TCP/broker/session connected? | `isClientModeConnected()` + connection events |
| Business probe | Can an event be sent safely and outcome verified? | Reply, commit, ack, idempotent probe |
| Degraded state | Can the flow accept locally while unable to send remotely? | Outbox holding backlog with retention |

If the application can only fulfill requests while the remote TCP peer is alive, readiness may need to report not ready. If it has a durable queue/outbox and tolerates holding work temporarily, it can report conditional readiness with transport degraded. Never use `isClientModeConnected()` as the **sole liveness check**, because a shared dependency outage should not force every pod to restart.

**Warning:** all pods failing liveness due to a remote outage can trigger a worse restart loop and reconnect storm. Health policies must reflect system goals and SLOs.

## 18. Metrics for reconnect and business recovery

| Suggested metric/signal | Meaning | Notes |
| --- | --- | --- |
| `integration.endpoint.running` | Lifecycle gauge | Does not reflect healthy connection |
| `tcp.connection.open.total` | Socket open count | Distinguish healthy reconnect from flapping |
| `tcp.connection.close.total` | Socket close count | Compare against opens over a time window |
| `tcp.connection.failed.total` | Failed connection attempts | May need error grouping |
| `tcp.connection.active` | Active sockets | Per factory/adapter |
| `producer.reconnect.attempts` | Connection retry count | Distinguish scheduled vs manual if possible |
| `producer.reconnect.duration` | Detect-to-connected | Not message recovery |
| `producer.reconnect.consecutive_failures` | Prolonged outage | Alert trigger |
| `integration.messages.accepted` | Producer/channel accepted | Does not mean remote committed |
| `integration.messages.completed` | Reached business outcome | Define milestone explicitly |
| `integration.messages.failed.retried` | Failure/retry rates | Retry storm indicator |
| `queue.depth` / `queue.oldest.age` | Backlog while consumer paused | Needs bounded retention |
| `executor.active` / `executor.pending` | Running/queued workers/tasks | Verify drain |
| `outbox.pending` / `dlq.count` | Durability and recovery | Should not rely solely on reading logs |

**These are suggested metric names for instrumentation**, not a list of default framework meters. Spring Integration supports Micrometer Observation on instrumented components, while TCP events typically need an `ApplicationListener`/`@EventListener` and application metric code.

### Metric cardinality

Never put raw connection IDs, event IDs, payloads, customer IDs, or arbitrary exception messages into metric labels. Pick low-cardinality tags: endpoint ID (fixed set), adapter type, direction, outcome, bounded exception class, and deployment region. Connection IDs/event IDs belong in structured logs/traces per security policy.

### Two latencies to measure separately

- **Detect-to-connected:** from detecting transport loss to establishing a new connection.
- **Detect-to-first-successful-business-event:** from the incident until a message achieves a real business outcome after recovery.

If the socket reconnects in 2 seconds while 50,000 queued messages and a slow downstream exist, business recovery can take minutes. Never conflate both numbers under `reconnect_time`.

## 19. Observing error paths during reconnect

A system can surface errors in multiple places:

| Error | Where it appears | How to inspect |
| --- | --- | --- |
| TCP connect failed | `TcpConnectionFailedEvent` / adapter logs | Event listener, remote endpoint |
| TCP established then closed | `TcpConnectionCloseEvent` | Connection ID, time window |
| TCP decode error | `TcpDeserializationExceptionEvent` | Framing/codec and bytes |
| Sync handler throw via DirectChannel | Exception at caller | Call stack, transaction outcome |
| Async handler throw via executor | Error handler/`ErrorMessage` per config | `errorChannel`/DLQ |
| Broker listener redelivery | Container/adapter and broker | Ack, delivery ID, committed offsets |
| External API business failure | Handler response/exception | Response semantics, retry classification |

**A TCP connection event is not a Spring Messaging `ErrorMessage`.** `ErrorMessage` is a message wrapping a Throwable emitted at supported error-publishing boundaries. A socket event is an `ApplicationEvent` from integration IP. One outage can emit both, yet they do not share the same contract, data, or automatic linkage.

When classifying errors, preserve:

- Stable `eventId` across retries.
- `correlationId` for aggregator/splitter and tracing.
- Connection factory/adapter name.
- Retry attempt number and type, when actually measured.
- Error class, root cause, stage, and timestamp.
- Durable message status (pending/committed/DLQ).

## 20. Transactions, retries, and idempotency after restart

Suppose a producer writes a message to a TCP socket, the remote peer processes it and commits its DB, yet the response is lost to a connection reset. Seeing an error, the producer retries after reconnect:

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant R as Remote handler
    participant D as Remote DB
    P->>R: SEND eventId=evt-101
    R->>D: INSERT + COMMIT
    D-->>R: Success
    Note over P,R: TCP disconnects before response
    P->>P: Reconnect succeeded
    P->>R: RETRY eventId=evt-101
    R->>D: INSERT with idempotency key evt-101?
    D-->>R: Already processed / return prior outcome
    R-->>P: Confirmed
~~~

If the event ID changes between attempts, the receiver cannot tell it is the same logical event from transport alone. Design measures:

1. **Sender-side outbox:** persist events durably with pending/confirmed state; do not delete simply because bytes were written.
2. **Receiver-side inbox/idempotency:** unique key per logical event; duplicate handling returns prior outcome when appropriate.
3. **Proper transaction boundaries:** coordinate DB commits and broker acks per a sound model; TCP does not participate in two-phase JDBC transactions automatically.
4. **Bounded retries:** transient network errors can retry, while permanent schema/auth errors should quarantine/escalate.
5. **Reconciliation:** when outcomes are unknown, look up remote state instead of resending blindly.
6. **Replay preserves correlation:** never replace a stable logical ID with a freshly generated `MessageHeaders.ID`.

Do not promise "exactly-once" solely from `retryConnection()` and `RequestHandlerRetryAdvice`; end-to-end reliability depends on application protocols and side-effect stores.

## 21. MQTT/JMS/AMQP/SFTP have different reconnect semantics from TCP

| Adapter | Recovery surface | What to verify |
| --- | --- | --- |
| TCP client-mode | `ClientModeCapable.retryConnection()`, scheduler | `single-use=false`, TCP events, framing |
| MQTT Paho v3/v5 | `MqttConnectOptions`/`MqttConnectionOptions` and adapter lifecycle | Automatic reconnect, subscriptions, QoS, delivery events |
| JMS listener | Listener container/session/connection factory | Recovery interval, transactions, session state |
| AMQP RabbitMQ | Listener container, connection factory | Consumer restart, acks/requeue, broker policy |
| SFTP/FTP polling | Session factory, cache, source poller | Session recreation, remote listing, file filters |
| HTTP outbound | Client pool/request retry | Timeouts, idempotency, response status |
| JDBC polling | DataSource/transaction manager | DB reconnect, row locks, poller state |

Current MQTT documentation lists `MqttConnectionFailedEvent`, `MqttMessageSentEvent`, `MqttMessageDeliveredEvent`, `MqttMessageNotDeliveredEvent`, and `MqttSubscribedEvent` depending on adapter and mode. For MQTT v5, documentation advises considering `MqttConnectionOptions.setAutomaticReconnect(true)`; otherwise, some scenarios require intentionally restarting the inbound adapter. **Never apply TCP APIs directly to MQTT**.

For remote files and JDBC, "producer reconnect" in practice often means **recovering `MessageSource.receive()`** and session/connection pools rather than a long-lived TCP adapter. If the error sits in the poller while the remote system is still down, restarting the poller just repeats failures; find the root cause first.

## 22. Dynamic IntegrationFlow and rolling deployments

Spring Integration provides `IntegrationFlowContext` for dynamically registered flows:

~~~java
IntegrationFlowContext.IntegrationFlowRegistration registration =
        flowContext.registration(dynamicFlow)
                .id("tenantOrdersFlow")
                .autoStartup(false)
                .register();

registration.start();
// ... monitor flow, messages, and connections ...
registration.stop();
// Drain pending work if required.
registration.destroy();
~~~

This is a snippet requiring valid `flowContext` and `dynamicFlow` beans. **`stop()` differs from `destroy()`**: `stop` keeps the registration to start again, whereas `destroy` tears down the flow and dependent beans per contract. If only a socket needs reconnecting, do not destroy and recreate the entire flow.

During rolling deployments:

- Start downstream infrastructure/consumer readiness before opening inbound traffic.
- Drain only a subset of pods per batch; avoid dropping cluster-wide connections simultaneously.
- Check serializers, protocol versions, TLS, and secrets across old and new versions.
- Monitor pending messages, group stores, broker offsets, and lock ownership.
- Keep the same logical event ID across versions to deduplicate replays.
- Use a central runbook coordinator, because a Control Bus/JMX command on one ApplicationContext does not affect other contexts automatically.

## 23. Testing endpoint restart with JUnit

From section 6's example, you can build an isolated test context (without running the demo `ApplicationRunner`) and assert:

~~~java
@Test
void consumerCanStopAndRestart() {
    endpoint.stop();
    assertFalse(endpoint.isRunning());

    endpoint.start();
    assertTrue(endpoint.isRunning());

    assertTrue(orders.send(MessageBuilder
            .withPayload("ORD-T1")
            .setHeader("eventId", "evt-T1")
            .build()));

    assertEquals(1, processedCount.get());
    endpoint.stop();
}
~~~

This is a **JUnit fragment** requiring injected `endpoint`, `orders`, `processedCount` beans, JUnit imports, and resetting counters/state before the test. Because `DirectChannel` dispatches synchronously, asserting immediately after `send()` is valid.

Negative test when the channel has only one subscriber:

~~~java
endpoint.stop();

assertThrows(MessageDeliveryException.class, () ->
        orders.send(MessageBuilder
                .withPayload("ORD-STOPPED")
                .build()));
~~~

If a second subscriber exists or the channel type differs, **do not** assert as if `send()` always throws. Test your application's actual topology, behavior, and durable outcomes.

## 24. Fault-injection TCP reconnect: testing with evidence

Use a TCP test server that can start/stop and receive payloads using real framing/serializers:

1. Start the test server and the outbound client-mode adapter.
2. Wait for `TcpConnectionOpenEvent` or `isClientModeConnected()` with a finite timeout.
3. Send event `evt-ok-1` and verify the peer received and processed it per contract.
4. Shut down the server or forcibly close the connection.
5. Record the timing of `TcpConnectionCloseEvent`/`TcpConnectionFailedEvent`; confirm the adapter **remains running**.
6. Restart the server; let the scheduler reconnect or trigger **a single** `retryConnection()` per runbook.
7. Wait for the open event or connected flag; **never use `Thread.sleep(5000)` as the sole assertion**.
8. Send event `evt-ok-2`; verify outcome at the peer/application-level contract.
9. Send an event while disconnected to create an unknown outcome; retry only with a stable `eventId` and verify dedup.
10. Verify connections/threads do not leak across repeated cycles.

Structural snippet with Awaitility and a custom TCP test fixture:

~~~java
// Pseudo integration test: requires tcpSender bean and testTcpServer fixture.
assertTrue(tcpSender.isRunning());

await().atMost(Duration.ofSeconds(10))
        .until(tcpSender::isClientModeConnected);

testTcpServer.closeConnections();

await().atMost(Duration.ofSeconds(10))
        .until(() -> !tcpSender.isClientModeConnected());

testTcpServer.restart();
tcpSender.retryConnection();

await().atMost(Duration.ofSeconds(10))
        .until(tcpSender::isClientModeConnected);
~~~

Requires Awaitility/Duration/JUnit imports and a TCP test server fixture. This is **not a self-contained runnable test** because the fixture is assumed. When connections recover very quickly, the disconnected window may be too brief and cause flaky assertions; capture and await **connection events** or keep the server down long enough for the test.

Always add a **send/response/commit** assertion after reconnect. Checking that the socket is connected alone does not prove business recovery.

## 25. Timeouts, intervals, and recovery duration

A recovery cycle can be broken down as:

\[
T_{\text{recovery}} \approx
T_{\text{detect}} +
T_{\text{wait for retry}} +
T_{\text{connect}} +
T_{\text{validate}} +
T_{\text{resume}}
\]

This is an **analytical model**, and intervals may overlap depending on implementation. `retry-interval=5000 ms` only governs attempt scheduling; it does not guarantee `T_recovery <= 5 s`.

| Component | Cause of delay | Metric to measure |
| --- | --- | --- |
| Detect | TCP half-open/idle timeout | Last successful I/O → close/failed event |
| Wait retry | `retryInterval`/busy scheduler | Disconnect → reconnect attempt |
| Connect | DNS, TCP handshake, TLS/auth, server queue | Attempt → open/fail |
| Validate | Health/business probe, peer warm-up | Connected → first valid reply |
| Resume | Queue backlog, poller/worker limits, DB pool | First successful event → normal throughput |

Do not confuse **connection recovered** with **throughput recovered**. A TCP socket may open in 2 seconds while a 20,000-event pending queue takes minutes to drain.

## 26. Production diagnostic table

| Symptom | Possible cause | Priority checks |
| --- | --- | --- |
| Endpoint running yet TCP disconnected | Peer down, network, TLS/DNS, scheduler has not tried yet | TCP failed/close events, remote health |
| `retryConnection()` returns yet status is false | Attempt still in progress or failed | Open/failed events and deadline |
| Endpoint restarted yet no messages flow | Empty source, wrong channel, unsubscribed consumer | Integration graph, poller/handler state |
| Socket connected yet payload fails | Framing/serializer/schema mismatch | Raw protocol test, deserialization events |
| Send accepted yet peer never commits | Async handoff, disconnect, lost ack | End-to-end reply/ack/business state |
| Duplicate messages after restart | Redelivery when ack did not commit | eventId, inbox, outbox |
| Process restart loses backlog | In-memory queue/task executor | Store durability, shutdown policy |
| Continuous TCP OPEN/CLOSE | LB idle timeout, peer quota, server restarts | Event rate, keepalive, peer logs |
| Multiple pods fail together after deploy | Wrong credentials/protocol and synchronized reconnect | Config diff, rollout coordination |
| Poller running yet zero output | Receive timeout, session failure, handler errors | Poller metrics, MessageSource logs |
| ErrorMessage emitted yet caller send succeeded | Async boundary | errorChannel, worker transaction |
| MQTT connected yet not subscribed | Subscription not restored | MqttSubscribedEvent, session/QoS |
| Cluster-wide readiness fails due to remote outage | Over-coupled health policy | Liveness/readiness/degraded state |

### Field debugging procedure

1. Identify the **exact bean ID/flow ID/pod**.
2. Snapshot lifecycle/connection/message state **before** intervening.
3. Distinguish transport failures from schema, handler, queue saturation, and transaction issues.
4. Check remote availability, network, TLS, DNS, credentials, and recent config changes.
5. Choose socket reconnect, endpoint start/stop, flow re-registration, or rolling restart based on root cause.
6. Monitor bounded attempts and error events; avoid unbounded parallel retries.
7. Prove post-recovery health using a **synthetic business event** with outcome and ack/commit.
8. Watch backlog, retries, duplicates, and resource leaks after resuming.
9. Record the incident timeline, config changes, and rollback criteria.

## 27. Real-world scenario: TCP peer restarts while sending an order

A service sends orders over outbound TCP client-mode. The peer restarts mid-transmission of order `evt-42`; the sender does not know whether the peer committed.

**Wrong approach:**

~~~text
Connection reset -> restart all pods -> resend entire batch
~~~

Consequences can include a reconnect storm, lost in-memory tasks, duplicate orders, and no way to tell which events were already processed.

**Proper runbook:**

1. Confirm from TCP events that transport dropped rather than invalid business payload.
2. Throttle ingress or ensure outbox/queue capacity remains sufficient.
3. Let the client-mode scheduler reconnect; if needed invoke `retryConnection()` **once** and audit it.
4. Wait for connected, then run a real probe rather than looking only at `isRunning`.
5. Query pending/unknown `eventId`s from the durable store.
6. If a peer status-lookup API exists, prefer reconciliation before resending.
7. Retry events with the **same idempotency key** and bounded backoff.
8. Verify committed, pending, DLQ, duplicate suppression, and backlog.
9. Ramp load up gradually and record recovery-time metrics and incident timeline.

Even when a broker transaction rolls back, a remote TCP peer may already have committed, so **a one-sided transaction is not enough to prevent duplicates**. Idempotent receivers or business reconciliation are mandatory when business rules require them.

## 28. Hands-on exercises

1. Run `EndpointRestartDemoApplication`; verify `ORD-101`/`ORD-103` process and `ORD-102` does not auto-replay.
2. Add a second subscriber to `DirectChannel`, stop the main consumer, and observe sends can still succeed.
3. Switch the flow to `QueueChannel` + `PollingConsumer`; stop the poller, measure queue depth, restart, and verify draining.
4. Use `ExecutorChannel` + a latch-waiting handler; call stop while the handler is in-flight and compare `isRunning` against actual task completion.
5. Configure TCP client-mode outbound with a local TCP test server and observe open/close events.
6. Change `retry-interval` from 5,000 to 30,000 ms in tests and measure detect-to-connected.
7. Keep the adapter running, stop the server, invoke `retryConnection()` **once**, and measure attempts and outcome.
8. Compare TCP inbound server mode against inbound client-mode in a valid test topology.
9. Use `@EventListener` to log a timeline of `TcpConnectionOpenEvent`, `TcpConnectionCloseEvent`, and `TcpConnectionFailedEvent`.
10. Pick the Control Bus syntax matching your running version and send an internal command with auditing/allowlisting.
11. Simulate the TCP peer committing before socket loss; replay the same `eventId` and verify inbox deduplication.
12. Combine `RequestHandlerRetryAdvice` with TCP reconnect and cap attempts to avoid retry storms.
13. Test broker redelivery after consumer stop; compare acknowledged vs unacknowledged messages.
14. Use MQTT v5 automatic reconnect per version and verify subscriptions restore after an outage.
15. With a persistent `QueueChannel` or message store, restart the process and read back pending messages.
16. Simulate the TCP peer returning malformed framing; explain why reconnecting does not fix it.
17. Write a readiness indicator with `healthy`, `degraded`, and `not ready` states matching your durability contract.
18. Run 3 instances while the server is down; record concurrent reconnect attempts and test staggered recovery.
19. Attach Micrometer counters to TCP events without putting `connectionId` into metric tags.
20. Write a runbook with entry criteria, actions, rollback, verification, and escalation.

### Self-check questions

- At which layer does `start()/stop()` differ from `retryConnection()`?
- Why can a running TCP adapter still be disconnected?
- When does TCP outbound open a connection immediately on start vs waiting for the first send?
- Why does client-mode require `single-use=false`?
- Is `retry-interval` an upper bound on maximum recovery time?
- Does reconnecting replay a message partially received by the peer?
- Why does `isClientModeConnected()==true` not prove business outcomes?
- If the socket closes after the peer committed, what data must a retry preserve?
- Does `EventDrivenConsumer.stop()` stop a connection factory shared by handlers?
- Does an in-memory `QueueChannel` guarantee survival across process restarts?
- Why can broker redelivery and TCP reconnect produce duplicates?
- Does a Control Bus command on one pod control the entire cluster?
- When is `IntegrationFlowContext.destroy()` needed instead of an endpoint restart?
- How do TCP connection events differ from Spring `ErrorMessage`?

## 29. Production checklist

- Inventory endpoint IDs, flow IDs, connection factory owners, and input/output/error channels per instance.
- Separate lifecycle state, connection status, and business outcomes into distinct signals.
- Use client-mode reconnect APIs per contract, only while the adapter is running.
- Enforce bounded retry intervals, timeouts, cooldowns, and thundering-herd protection.
- Never retry permanent credential/serializer errors as transient network glitches.
- Record TCP/broker/MQTT events, retries, connection health, and reconnection timelines.
- Keep error/recovery consumers available while draining producers/inbound sources.
- Define shutdown policies for in-memory queues and pending executor tasks; use persistent storage when durability is required.
- Independently verify broker acks/transactions/outbox/inbox/idempotency.
- Maintain probes verifying **message processing completes**, not merely that sockets are connected.
- Restrict Control Bus/JMX write access with permissions and auditing.
- Perform rolling restarts in batches with sufficient drain time and remote load protection.
- Include rollback/escalation criteria and retry cutoffs for prolonged failures in runbooks.
- Run fault-injection tests: peer down/up, half-open sockets, serializer mismatches, unknown outcomes, and duplicate replays.
- Maintain dashboards for backlog, p95/p99 processing latency, retries, and time-to-first-business-success.

## 30. Official references

- [Spring Integration — TCP Adapters](https://docs.spring.io/spring-integration/reference/ip/tcp-adapters.html): inbound/outbound client mode, reconnect, and retry interval.
- [Spring Integration — TCP Endpoint Configuration Attributes](https://docs.spring.io/spring-integration/reference/ip/endpoint-reference.html): `client-mode`, `single-use`, `retry-interval`, and defaults.
- [Spring Integration — TCP Connection Events](https://docs.spring.io/spring-integration/reference/ip/tcp-events.html): open/close/failed/exception/correlation events.
- [Spring Integration — TCP Connection Factories](https://docs.spring.io/spring-integration/reference/ip/tcp-connection-factories.html): ownership, connection caching/failover, and serializers.
- [Spring Integration Javadoc — ClientModeCapable](https://docs.spring.io/spring-integration/docs/5.5.17/api/org/springframework/integration/ip/tcp/connection/ClientModeCapable.html): `isClientModeConnected()` and `retryConnection()`.
- [Spring Integration Javadoc — TcpSendingMessageHandler](https://docs.spring.io/spring-integration/docs/6.4.2/api/org/springframework/integration/ip/tcp/TcpSendingMessageHandler.html): handler lifecycle and client-mode setter/API.
- [Spring Integration — Control Bus](https://docs.spring.io/spring-integration/reference/control-bus.html): managed operations, command registry, and security.
- [Spring Integration — Message Channels](https://docs.spring.io/spring-integration/reference/channel/implementations.html): sync/async/pollable boundaries.
- [Spring Integration — Source Polling Channel Adapter](https://docs.spring.io/spring-integration/reference/channel-adapter.html): poller lifecycle and pause semantics.
- [Spring Integration — Runtime Integration Flows](https://docs.spring.io/spring-integration/reference/dsl/java-runtime-flows.html): `IntegrationFlowContext` registration, start/stop/destroy.
- [Spring Integration — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): error channels and async error handling.
- [Spring Integration — MQTT Support](https://docs.spring.io/spring-integration/reference/mqtt.html): Paho reconnect and MQTT events.
- [Spring Framework — Lifecycle / SmartLifecycle](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html): start/stop, phase, and dependency ordering.
