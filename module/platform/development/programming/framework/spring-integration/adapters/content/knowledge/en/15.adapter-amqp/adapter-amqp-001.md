# AMQP inbound channel adapter

## Learning Objectives

After this lesson, you will be able to:

- Explain the path of an AMQP message from a **RabbitMQ exchange/binding/queue** to a **MessageChannel** in Spring Integration.
- Distinguish a one-way **AMQP inbound channel adapter** from an **AMQP inbound gateway** with a request–reply contract.
- Understand the role of the **listener container**, **ConnectionFactory**, **MessageConverter**, payload, headers, and channel at the receiving boundary.
- Write a **Spring Integration Java DSL** flow that receives messages from a RabbitMQ queue and forwards them to an internal handler.
- Analyze **acknowledgment, redelivery, requeue, dead-letter, retry, idempotency, prefetch, concurrency**, and post-restart application states.
- Build a test suite and operational metrics to detect connection errors, data errors, backlog, and duplicate message processing.

## 1. Problem to Solve

An e-commerce system emits an **OrderCreated** event when an order is created. Another Spring Boot application needs to receive the event, validate the data, and trigger its own business logic. The applications do not necessarily run at the same time or use the same programming language.

RabbitMQ can act as an intermediary: the producer publishes an AMQP message, the broker routes it to a queue, and the consumer retrieves the message when ready. In the receiving application, Spring Integration's **AMQP inbound channel adapter** connects the RabbitMQ message-receiving mechanism to an internal **MessageChannel**. Downstream handlers behind the channel only need to know the payload and headers contract, without directly programming message consumption with the RabbitMQ client.

~~~mermaid
flowchart LR
    P["Producer<br/>OrderCreated"] --> X["RabbitMQ Exchange<br/>orders.events"]
    X -->|"Routing key + binding"| Q["Queue<br/>orders.created.q"]
    Q --> L["Spring AMQP<br/>Listener container"]
    L --> A["AMQP inbound<br/>channel adapter"]
    A --> M["Spring Message<br/>payload + headers"]
    M --> C["MessageChannel<br/>rabbitOrders"]
    C --> H["Validator / Transformer<br/>Service activator"]
~~~

**AMQP** is the protocol/message model; **RabbitMQ** is the broker used in the example. Spring Integration AMQP integrates with **Spring AMQP** to use the connection factory, listener container, and message converter. Choose this model when the application needs to receive one-way messages from the broker and feed them into an integration flow.

The scope of an inbound adapter is **broker → application**. Do not confuse it with an **AMQP outbound adapter** (application → broker) or an **AMQP gateway** (which involves request and reply).

## 2. Components to Understand Before Configuring

RabbitMQ does not pass messages from the producer directly into a Spring MessageChannel. There are two systems and a conversion layer in between:

| Component | Role | Things to Keep in Mind |
| --- | --- | --- |
| **Exchange** | Receives published messages from producers and routes them according to exchange type and bindings | Producers typically publish to an exchange; an exchange is not where consumers directly pull data from |
| **Routing key** | Participates in the exchange's routing rules | With a direct exchange, it is typically matched against the binding key |
| **Binding** | Links an exchange to a queue according to rules | Misconfiguration prevents messages from reaching the intended queue |
| **Queue** | Holds messages waiting for consumers according to broker policies | A durable queue alone does not guarantee all messages survive if messages are not persistent or the broker does not meet required guarantees |
| **ConnectionFactory** | Creates and manages RabbitMQ connections for the application | Needs configuration for authentication, TLS, host, virtual host, and reconnection capability |
| **Listener container** | Consumes deliveries from the queue; coordinates concurrency and acknowledgment | ACK timing, exception handling, requeue behavior, and active consumers depend on the container |
| **Inbound channel adapter** | Converts an AMQP delivery into a Spring Integration Message and sends it to a channel | One-way; does not wait for a business reply |
| **MessageConverter** | Maps between AMQP body/properties and the payload | The payload type does not automatically match a domain type |
| **MessageChannel** | Delivers the message to downstream endpoints | DirectChannel is synchronous; ExecutorChannel/QueueChannel have different semantics |

### 2.1. Exchange, Queue, and Binding Are Not Interchangeable

In the example, the producer publishes to the direct exchange **orders.events** with the routing key **orders.created**. The queue **orders.created.q** is bound to the exchange with a binding key of the same value. If the topology is declared properly, deliveries enter the queue for the listener container to consume.

~~~mermaid
flowchart TD
    PX["Publisher"] --> EX["Direct Exchange<br/>orders.events"]
    EX -->|"orders.created"| Q1["orders.created.q"]
    EX -. "Different routing key,<br/>no matching binding" .-> NO["Does not reach this queue"]
    Q1 --> C["Application consumer"]
~~~

A single queue can be consumed by multiple consumers to share load; that is **different** from having multiple independent queues bound to the same exchange so each system receives a copy. If each system needs its own processing stream, design the appropriate queues/bindings instead of assuming that multiple consumers on the same queue each receive every message.

### 2.2. Spring AMQP Listener Differs from Spring Integration Poller

Inbound AMQP follows a **message-driven** model: the listener container receives deliveries from RabbitMQ via the client and invokes the endpoint. Normally, **no Spring Integration Poller is needed** to scan the queue the way File/SFTP/JDBC inbound adapters use a MessageSource.

The listener container has its own I/O mechanism, delivery reception, concurrency, prefetch, and acknowledgment. A flow using an AMQP inbound adapter still exchanges data through a MessageChannel, but the source trigger is a **listener**, not a periodic **poller** from the Integration DSL.

## 3. How Does a Message Enter Spring Integration?

The receiving process can be divided into seven steps:

1. **Producer publishes** an AMQP message with a body, properties, exchange, and routing key.
2. **Broker routes** it into the queue matching the binding; if there is no route, behavior depends on publish policies, mandatory/return settings, and broker configuration.
3. **Listener container** receives the delivery along with the delivery tag, redelivery flag, properties, and body content.
4. **MessageConverter**, as configured, converts the content from its AMQP representation into an appropriate payload, such as a byte array, String, or DTO.
5. **Inbound adapter** creates/forwards a Spring Integration Message, maps appropriate metadata into headers, and sends it to the output channel.
6. **MessageChannel** passes the message to the next transformer, filter, router, or service activator.
7. **Listener container** handles acknowledgment or errors according to its mode/configuration. Do not assume ACK always happens at the same moment as sending to the channel.

~~~mermaid
sequenceDiagram
    participant B as RabbitMQ queue
    participant L as Listener container
    participant A as AMQP inbound adapter
    participant C as MessageChannel
    participant H as Business handler
    B-->>L: AMQP delivery
    L->>A: Invoke listener
    A->>C: Message(payload, headers)
    C->>H: Deliver message
    H-->>C: Complete or throw exception
    C-->>A: Finish synchronous processing
    A-->>L: Finish listener callback
    L-->>B: ACK / NACK based on mode and result
~~~

The diagram illustrates a **DirectChannel and synchronous handler** scenario. If switched to an asynchronous channel, the handler may still be running after the listener callback returns. In that case, the listener ACK could happen **before business processing actually completes** unless an appropriate coordination mechanism is in place.

## 4. Inbound Adapter or Inbound Gateway?

AMQP can support both one-way and request–reply communication, but the two contracts require different endpoints:

| Requirement | Appropriate Endpoint | Behavior |
| --- | --- | --- |
| Receive an OrderCreated event and process it internally | **AMQP inbound channel adapter** | Receives the delivery, emits the message to a channel; sends no business reply |
| Producer sends a request and waits for a result from the processing system | **AMQP inbound gateway** | Receives the request, sends it into the flow, obtains the response, and sends a reply per the AMQP contract |
| Application publishes an event to an external queue/topic | **AMQP outbound channel adapter** | Sends one-way to the broker |
| Flow sends an AMQP request and needs the returned result | **AMQP outbound gateway** | Request–reply; requires timeout and correlation |

**A broker ACK is not a business reply.** The inbound adapter can participate in delivery acknowledgment according to Spring AMQP, but the producer does not automatically receive an OrderResult object as in a request–reply pair. If the producer needs to know whether an order was approved or rejected, design a gateway or an asynchronous response workflow with a correlation ID and a reply destination.

## 5. Payload and Headers: The Contract at the AMQP Boundary

A message at the broker has an AMQP **body** along with **properties/headers**. In Spring Integration, the handler receives a **Spring Message** with a **payload** and **MessageHeaders**. You can visualize it as:

~~~text
RabbitMQ delivery
├── body: byte[] in wire format
├── contentType, contentEncoding
├── messageId, correlationId, timestamp (if provided by producer)
├── headers / routing metadata
└── delivery metadata
           |
           v
Spring AMQP MessageConverter + header mapper
           |
           v
Spring Message<?>
├── payload: byte[] / String / DTO / ...
└── headers: metadata mapped as configured
~~~

Do not assume AMQP inbound always emits a **String** or a **DTO**. The payload type depends on the converter and content type:

- With a basic converter, a **text/plain** body can be decoded into a String.
- With **application/json**, obtaining a DTO usually requires a JSON converter or an appropriate transformer; the default converter cannot automatically infer arbitrary domain structures.
- With a binary payload, you can keep a byte array and deserialize it in a downstream step.

### 5.1. Metadata to Consider

| Metadata | Typical Use | Warning |
| --- | --- | --- |
| **contentType/encoding** | Determines the body's serializer or charset | A valid-looking header does not guarantee a valid body |
| **correlationId** | Matches request/reply or traces flows | Not automatically a business idempotency key |
| **messageId** | Tracks messages set by the producer | May be missing; not guaranteed to be business-unique |
| **routing key / queue** | Identifies which stream the message came from | Adapter-mapped metadata, not the payload itself |
| **redelivered** | Indicates the broker has redelivered the message | Cannot be used alone to conclude the message was not processed |
| **delivery tag/channel** | Supports delivery-level ACK when using manual mode | Do not pass client references arbitrarily to another system |
| **eventId/orderId** | Domain key for deduplication and reconciliation | Should be clearly defined in the business contract |

When multiple event types share a single queue, include an explicit **eventType** and **schemaVersion** so handlers can classify and validate them. Important business information can be placed in the payload as defined by the contract rather than relying on AMQP metadata that not all consumers preserve.

## 6. Java DSL Example: RabbitMQ → Inbound Adapter → DirectChannel

Let's build a minimal example to receive a message containing two fields **orderId|totalVnd** from RabbitMQ:

- Direct exchange: **orders.events**.
- Routing key: **orders.created**.
- Durable queue: **orders.created.q**.
- AMQP inbound adapter consumes deliveries from the queue.
- Internal MessageChannel: **rabbitOrders**.
- Service handler parses the String and logs the received result.

This is a **one-way** example to clearly show the adapter boundary. The handler does not write to a database yet; do not treat it as proof of business completion. With Spring Boot, you need the **spring-boot-starter-amqp**, **spring-boot-starter-integration**, and **spring-integration-amqp** dependencies, at versions managed by Spring Boot's dependency management.

### 6.1. Declaring Topology and IntegrationFlow

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.amqp.dsl.Amqp;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class OrderAmqpInboundConfiguration {

    public static final String EXCHANGE = "orders.events";
    public static final String ROUTING_KEY = "orders.created";
    public static final String QUEUE = "orders.created.q";

    @Bean
    public DirectExchange orderExchange() {
        return new DirectExchange(EXCHANGE, true, false);
    }

    @Bean
    public Queue orderQueue() {
        return new Queue(QUEUE, true);
    }

    @Bean
    public Binding orderBinding(
            Queue orderQueue, DirectExchange orderExchange) {
        return BindingBuilder.bind(orderQueue)
            .to(orderExchange)
            .with(ROUTING_KEY);
    }

    @Bean
    public MessageChannel rabbitOrders() {
        return new DirectChannel();
    }

    // Broker delivery -> AMQP inbound adapter -> MessageChannel.
    @Bean
    public IntegrationFlow ordersInbound(ConnectionFactory connectionFactory) {
        return IntegrationFlow
            .from(Amqp.inboundAdapter(connectionFactory, QUEUE))
            .channel("rabbitOrders")
            .get();
    }

    // MessageChannel -> illustrative handler.
    @Bean
    public IntegrationFlow inspectOrders() {
        return IntegrationFlow.from("rabbitOrders")
            .handle(String.class, (body, headers) -> {
                String[] fields = body.split("\\|", -1);
                if (fields.length != 2 || fields[0].isBlank()) {
                    throw new IllegalArgumentException(
                        "Message must have format orderId|totalVnd");
                }

                long totalVnd = Long.parseLong(fields[1]);
                if (totalVnd <= 0) {
                    throw new IllegalArgumentException(
                        "Total amount must be greater than 0");
                }

                System.out.println(
                    "Received order " + fields[0] + ", totalVnd=" + totalVnd);
                return null; // One-way endpoint, no business reply.
            })
            .get();
    }
}
~~~

**Prerequisites for the example:** a RabbitMQ broker must be running and the application must have ConnectionFactory configured (host, port, virtual host, username/password, or TLS depending on the environment). Exchange, Queue, and Binding beans are only automatically declared on the broker when the application has an appropriate **RabbitAdmin/AmqpAdmin**, the account has declaration permissions, and auto-declaration is enabled. If infrastructure manages topology externally, adjust the declaration workflow according to deployment policy.

**Payload type:** the example uses **String** because in the test-sending step we use RabbitTemplate.convertAndSend with a String payload, which the default converter emits as text content. If an external producer sends JSON or bytes with a different content type, the handler must be paired with a contract-appropriate converter/transformer; do not try to force every payload into a String.

**Production scope:** the illustrative logger does not replace idempotent logic, transactions, or verified ACKs. In a real system, separate a transformer to parse the contract and a service activator to handle business logic; consider an error queue before allowing producers to send live data.

### 6.2. Sending a Test Message with RabbitTemplate

From an integration test or service with a Spring Boot–configured RabbitTemplate:

~~~java
import org.springframework.amqp.rabbit.core.RabbitTemplate;

public class OrderEventPublisher {
    private final RabbitTemplate rabbitTemplate;

    public OrderEventPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void sendExample() {
        rabbitTemplate.convertAndSend(
            "orders.events", "orders.created", "O-1001|150000");
    }
}
~~~

If the topology and converter match, the message is routed to **orders.created.q**. The listener container passes the delivery through the AMQP inbound adapter into **rabbitOrders**; the handler prints the order details.

Do not confuse calling **convertAndSend** with the consumer application having completed its business logic. It only sends the message through the producer via RabbitTemplate's mechanism; producer/broker confirmations must be configured and monitored separately if required.

### 6.3. Testing Sequence

1. Prepare RabbitMQ and configure the Spring AMQP connection using an account with appropriate permissions.
2. Start the application; verify that the exchange, queue, and binding exist on the broker (created by the application's admin bean or deployment tooling).
3. Send the string **O-1001|150000** using the sendExample method.
4. Check that the handler received and printed the data after the listener received the delivery.
5. Send **O-1002|90000** to verify that another message also reaches the channel.
6. Send malformed data such as **bad-message** to observe the error path. **Do not test repeatedly on a production queue** before retry/requeue/DLQ is configured, because a faulty message may be redelivered in a loop.
7. Pause the receiving application, publish additional messages, and then restart it. Observe the backlog in the queue and consumption behavior when the listener comes back up.

## 7. Acknowledgment: When Is a Message Considered Received?

This is the most critical decision for AMQP inbound. **A delivery being received by the listener** does not mean **the business transaction has committed**. RabbitMQ uses acknowledgment to know whether a delivery has been confirmed by the consumer or needs further handling per policy.

In Spring AMQP, three modes are commonly encountered:

| AcknowledgeMode | Meaning | Risks to Evaluate |
| --- | --- | --- |
| **AUTO** | Container ACKs when the listener completes successfully; handles errors per container policy | If the listener returns before asynchronous business logic finishes, ACK may happen too early |
| **MANUAL** | Application is responsible for ACK/NACK using delivery tag and channel | Easy to leak unacked messages if confirmation is forgotten; every error branch must be managed |
| **NONE** | Broker considers the message acknowledged upon delivery under a mode that requires no consumer ACK | Easy to lose redelivery opportunities if the consumer crashes after receiving before processing |

### 7.1. AUTO with Synchronous DirectChannel

In the Java DSL example, the adapter sends to a **DirectChannel** and the handler is invoked directly within the listener processing chain. If the handler completes successfully, the listener can return so the container performs an ACK in AUTO mode. If the handler throws an exception and it propagates to the container, the container can reject/nack according to the configured policy.

This **does not automatically guarantee an atomic transaction** between RabbitMQ and the database. If the handler writes to the DB successfully but the connection drops before ACK, the broker may redeliver the message. Store an idempotency key and enforce duplicate checks in the business layer.

### 7.2. AUTO with Asynchronous ExecutorChannel

Suppose the channel after the inbound adapter is changed to an **ExecutorChannel**. The adapter can hand off the work to the executor and return immediately. The listener sees that sending the message to the channel completed, while the handler on another thread is still processing. If the container ACKs at that moment, downstream business failures **are no longer guaranteed to be redelivered by the broker** under the old delivery's ACK.

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant L as Listener
    participant E as ExecutorChannel
    participant H as Async handler
    B-->>L: AMQP delivery
    L->>E: send(message)
    E-->>L: Work handed off to executor
    L-->>B: May ACK when callback succeeds
    E->>H: Starts processing later
    H--xE: Business error
    Note over B,H: ACK may have already happened<br/>before the error occurred
~~~

Therefore, **do not replace a DirectChannel with an asynchronous channel just to increase throughput** if ACK must be tied to the business processing outcome. When asynchronicity is required, design a durable storage boundary and a separate ACK point, or use a thoroughly tested manual acknowledgment mechanism.

### 7.3. MANUAL: Use Only When Every Branch Is Controlled

In manual mode, the consumer must know the delivery tag and the appropriate RabbitMQ channel to ACK/NACK. Spring Integration/Spring AMQP can provide the necessary metadata via headers when configured; header names and object types must be verified against the actual library version. Do not assume an arbitrary handler can ACK after a message has detached from the delivery lifecycle or the channel has closed.

Manual ACK is a tool for special requirements, not a default "safer" option. If you forget to ACK, messages remain in the unacked state until the connection/channel closes or another condition occurs; throughput can become capped by prefetch.

## 8. Retry, Requeue, and Dead-Letter

An AMQP message can fail for several reasons:

- **Transient errors:** database timeout, slow downstream service, dropped connection.
- **Data errors:** invalid JSON, missing fields, wrong schema, invalid business ID.
- **Infrastructure errors:** insufficient permissions, consumer not ready, or misconfigured connection.
- **Unknown state:** side effects occurred, but ACK never reached the broker.

You should not handle every error with **infinite requeue**.

### 8.1. Distinguishing Retry from Requeue

| Mechanism | What Happens | When Appropriate |
| --- | --- | --- |
| **In-listener retry** | Retries processing the same delivery according to policy/backoff | Transient errors that can recover quickly |
| **NACK/reject with requeue** | Broker puts the message back into the queue for redelivery per policy | When there is reason to expect the next delivery attempt will succeed |
| **Reject without requeue** | Delivery is rejected; if a suitable DLX is configured, it can go to a dead-letter queue | Permanently invalid data or retries exhausted |
| **DLQ/DLX** | System isolates failed messages for later investigation/reprocessing | Prevents a poison message from disrupting the entire flow |

In many Spring AMQP configurations, an exception from the listener in AUTO mode can trigger requeue by default. If the data is definitely invalid, the broker can redeliver it repeatedly and consume resources. Configure **bounded retries**, **reject without requeue**, dead-letter exchange/queue, and a dedicated handling workflow.

**A DLQ does not appear automatically just by throwing an exception.** You must define dead-letter routing, appropriate queues/bindings, and the listener's reject policy. Also check TTL, size limits, and data lifecycle on the DLQ.

~~~mermaid
flowchart TD
    Q["orders.created.q"] --> L["AMQP inbound adapter"]
    L --> V{"Validate and process"}
    V -->|"Success"| ACK["ACK per configuration"]
    V -->|"Transient error"| R["Bounded retry + backoff"]
    R --> V
    V -->|"Permanent error or retries exhausted"| N["Reject/NACK without requeue"]
    N --> DX["Dead-letter exchange<br/>if configured"]
    DX --> DQ["orders.created.dlq"]
~~~

### 8.2. Idempotency Is Mandatory When Redelivery Exists

If the consumer saves order O-1001 and the process terminates before ACK, the broker may redeliver the same event. The consumer must avoid creating duplicate records:

1. Generate an **eventId** or use a stable **partnerId + orderId** per contract.
2. Use an appropriate unique constraint/checkpoint or inbox table to mark processed events.
3. Wrap the business write and idempotency marker in a data transaction whenever possible.
4. Only ACK when the committed completion level is reached, following either a synchronous model or a designed durable storage mechanism.
5. Record/reconcile cases where it is uncertain whether processing occurred.

The **redelivered = true** header only hints that the broker has redelivered the message; it should not be used to decide whether to skip processing. A business duplicate message can arrive as a brand-new publish without the redelivered flag.

## 9. Prefetch, Concurrency, and Throughput

As message volume grows, two adjustments are commonly considered on the listener container:

- **Concurrent consumers:** the number of consumers processing in parallel. Can improve throughput if downstream systems and the broker have sufficient capacity.
- **Prefetch count:** the number of unacked deliveries the broker is allowed to push ahead within the configured scope. A large prefetch can reduce overhead, but increases the number of messages held by the consumer, consumes memory, and reduces fairness across consumers.

| Symptom | Check Before Raising Configuration Limits |
| --- | --- |
| Queue depth rising | Downstream latency, consumer count, publish rate, DB/broker bottleneck |
| Many unacked messages | Slow handler, prefetch, forgotten manual ACK, hung transaction |
| High CPU, queue still growing | Heavy parsing/validation or excessive concurrency |
| Frequent redeliveries | Data errors, rollback/requeue, dropped connection before ACK |
| Out-of-order processing | Multiple consumers/prefetch breaking business ordering assumptions |
| One consumer holds too many deliveries | Prefetch and uneven processing time distribution |

**Ordering:** RabbitMQ queues have a notion of order, but concurrency, requeue, priorities, and multiple consumers can make **actual processing order** differ from publish order. If sequential processing is required for the same order ID, design a routing/partitioning key or versioning rules rather than relying solely on using a single queue.

**Capacity:** if the broker delivers 500 messages/second while the database can only handle 100 messages/second, adding more consumers is unlikely to help. A sound solution may require input throttling, business batching, database scaling, or an architecture that holds backlog in the broker and processes at sustainable capacity.

## 10. Adapter, Listener Container, and Connection Lifecycle

The AMQP inbound channel adapter is tied to the listener container and RabbitMQ resources. Endpoint running state and broker readiness **are not the same thing**.

### 10.1. When the Application Starts

Typically:

At the Spring level, many endpoints and listener containers participate in the **Lifecycle/SmartLifecycle** mechanism. Depending on the bean and configuration, **autoStartup**, **start()/stop()**, and **phase** help control when message consumption begins as well as component shutdown order. Do not treat toggling a lifecycle flag as a message acknowledgment mechanism or a guarantee that all backlog has been drained.

1. Spring creates the ConnectionFactory bean, topology declarations, and related endpoints.
2. RabbitAdmin/AmqpAdmin (if configured) may declare exchanges, queues, and bindings on the broker per policy.
3. The listener container starts consuming from the queue according to lifecycle and **autoStartup**.
4. The inbound adapter passes received messages into the MessageChannel.

Do not infer from **isRunning() = true** that the connection is completely healthy. A container may be attempting to reconnect because the broker is unavailable or the user lacks permissions. Observe actual connections, logs, and consumption metrics as well.

### 10.2. During Shutdown or Maintenance

When stopping an endpoint/listener, in-flight deliveries may need to finish, roll back, or be redelivered depending on ACK mode, transactions, and container settings. Do not expect **stop()** to mean all downstream tasks have finished draining, especially when an ExecutorChannel or asynchronous tasks are involved.

A sensible operational sequence is typically:

1. Stop accepting new work or pause the listener using a supported mechanism.
2. Monitor **in-flight/unacked**, active handlers, queue depth, and running tasks.
3. Wait for processing to finish within an operational timeout or prepare for safe redelivery.
4. Close resources and processes following the Spring lifecycle.
5. On restart, check remaining messages in the broker, checkpoints, and business idempotency.

Shared connections/sessions should not be closed arbitrarily just to stop a single inbound adapter. Examine which bean owns the resource and whether other endpoints share it.

## 11. Observability and Security in Operations

An AMQP inbound adapter is not a "black box": message reception must be monitored on both the broker and the application.

| Group | Metrics or Information to Observe |
| --- | --- |
| Broker | Ready messages, unacked messages, consumer count, publish/deliver/ack rates |
| Listener | Consumer concurrency, reconnects, queue declaration errors, listener failures |
| Internal flow | Messages entering channel, handler latency, failure rate, active processing |
| Retry | Retry count, requeued messages, messages routed to DLQ, poison messages |
| Business | Processed event IDs, orders persisted, duplicates discarded |
| Latency | Time from publish to processing, backlog age, ACK duration |
| Security | TLS, virtual host/queue/exchange permissions, credential rotation, log masking |

When configuring for production:

- Use RabbitMQ accounts with permissions scoped by virtual host, exchange, and queue.
- Enable TLS if the environment requires transport encryption and verify certificates properly.
- Do not write credentials or full sensitive payloads to logs.
- Define TTL, retention, or quota policies for queues/DLQs to prevent unbounded growth.
- Establish topology and policies (queue durability, dead-letter, message size, quorum/classic as needed) with the broker operations team.
- Test broker restarts, network partitions, consumer reconnects, and credential expiration scenarios.

**A healthy broker does not mean healthy business processing.** A shrinking queue while messages are ACKed too early, asynchronous handlers fail, or errors go to an unhandled errorChannel still causes business loss. Reconcile broker metrics with the number of records actually processed.

## 12. Real-World Integration Scenarios

### 12.1. One Queue for a Worker Pool Processing Orders

If multiple instances of the same service consume **orders.created.q**, RabbitMQ distributes deliveries among consumers via queue mechanics. This is the **competing consumers** pattern for load sharing. Each message is delivered to one consumer at a time per the broker, though it may be redelivered if unacked.

The application must:

- Tolerate redelivery and avoid creating duplicate orders.
- Not rely on strict processing order when multiple consumers run.
- Set prefetch and concurrency appropriately for database capacity.
- Manage graceful shutdown so active consumers do not lose state.

### 12.2. Multiple Systems Needing the Same Event

Both the warehouse system and the analytics system need OrderCreated. If both consume from **a single queue**, they typically **split** messages between them instead of each receiving a copy. The proper design is for each system to have its own queue, bound to the exchange under the needed routing conditions.

~~~mermaid
flowchart TD
    P["Order publisher"] --> X["orders.events exchange"]
    X --> Q1["warehouse.orders.q"]
    X --> Q2["analytics.orders.q"]
    Q1 --> W["Warehouse inbound adapter"]
    Q2 --> A["Analytics inbound adapter"]
~~~

Choose direct/topic/fanout exchanges based on routing rules rather than assuming one routing key or one queue fits every subscriber.

### 12.3. Receiving from AMQP and Persisting to a Database

Suppose an inbound adapter receives OrderCreated, a service activator writes to the database, and then an outbound adapter sends a receipt to another system. There is no automatic transaction spanning RabbitMQ, the database, and the external destination.

If the database commit succeeds but the outbound publish fails, an outbox may be needed to persist unsent message state. If the broker redelivers after the database has committed, idempotency is needed on the consumer. **ACK must be tied to a well-designed completion boundary**, not merely to successfully parsing the payload.

## 13. Testing: From Happy Path to Failure Scenarios

| Scenario | Action | Expected Result |
| --- | --- | --- |
| Valid routing | Publish with orders.events / orders.created | Message reaches orders.created.q and enters rabbitOrders |
| Invalid routing | Use a key with no matching binding | Does not reach target queue; check return/mandatory if needed |
| Valid payload | Send O-1001|150000 as text/plain | Handler receives String, processes, and completes |
| Malformed data | Send message missing fields or invalid number | Error detected; no infinite requeue; retry/DLQ applied per config |
| Consumer paused | Stop consumer then publish | Queue holds messages per policy; resume can consume backlog |
| Handler throws exception | Simulate DB failure | Verify ACK/NACK/requeue and retry per configuration |
| Connection dropped | Disconnect broker during delivery | Verify reconnect, in-flight handling, and redelivery behavior |
| Duplicate | Publish same eventId multiple times | Business logic produces result once thanks to idempotency |
| High load | Publish burst and build backlog | Monitor queue ready/unacked, latency, prefetch, throughput |
| Scale out | Run two consumers on the same queue | Competing-consumer behavior as expected, not broadcast by default |
| Restart | Stop and restart application | Unacked messages are reprocessed per broker; business state not duplicated |

### 13.1. Do Not Just Check the "Received" Log

If the handler only prints **Received order O-1001**, we only know the payload reached the service handler in the example. To conclude an order was safely persisted, real tests must check the database, idempotency state, ACK, and post-restart behavior.

In integration tests, you can use a dedicated RabbitMQ instance in the test environment or a test container managed by the build system. However, do not turn a demo into an exactly-once guarantee test merely by running a single successful send.

## 14. Common Mistakes

**Confusing an AMQP queue with a Spring MessageChannel.** A queue belongs to RabbitMQ and is managed by the broker; a MessageChannel belongs to the Spring Integration application and has internal communication semantics.

**Using a Spring Integration poller for every AMQP inbound endpoint.** A message-driven AMQP inbound adapter typically uses a listener container and does not need a periodic polling source like File/SFTP.

**Treating a single queue as a broadcast mechanism for all applications.** Multiple consumers on the same queue typically compete for messages; if each system needs a copy, design separate queues/bindings.

**Assuming AUTO ACK means business processing always finishes before ACK.** This also depends on the channel and asynchronous execution. With an ExecutorChannel, the adapter can return before the handler finishes.

**Letting malformed messages requeue continuously.** Poison messages can cause a delivery loop; bounded retries and an explicitly configured DLQ are needed.

**Using redelivered or messageId as a unique idempotency key.** Use a stable eventId/orderId and perform business-level checks when writing state.

**Increasing prefetch or consumers without limits.** This can inflate the unacked backlog, overload the DB, consume memory, and make processing order hard to control.

**Confusing consumer ACK with a business reply.** If the producer must know the outcome, use an inbound/outbound gateway or an asynchronous reply flow.

**Believing a durable queue suffices for every data-loss scenario.** Consider message persistence, broker policies, topology, ACK, and incident handling.

**Monitoring only isRunning.** Also monitor RabbitMQ connectivity, ready/unacked counts, retries, DLQ, processing duration, and business outcomes.

## 15. Self-Check Questions

1. How do a RabbitMQ exchange, binding, and queue differ? Why does an inbound adapter typically consume from a queue rather than directly from an exchange?
2. When using an AMQP inbound adapter, why is a Spring Integration Poller usually unnecessary?
3. How does an AMQP inbound channel adapter differ from an inbound gateway? Is an ACK a business reply?
4. When a producer publishes a String, what conditions cause the inbound adapter to receive a String instead of a byte array?
5. With a synchronous DirectChannel and AUTO ACK, how does the timing of the listener returning relate to when the handler finishes processing?
6. If switched to an ExecutorChannel, why can an ACK occur before business processing fails?
7. A message containing invalid-schema JSON repeatedly throws an exception. How should retry, requeue, and DLQ be designed?
8. If the consumer finishes writing to the database but the process crashes before ACK, what mechanism prevents duplicate records when the message is redelivered?
9. How do high prefetch and multiple consumers affect unacked messages, throughput, and processing order?
10. Two applications both need OrderCreated. Why should they not compete on a single queue if each application must receive every event?
11. What metrics help distinguish a listener that cannot connect to the broker from a healthy listener where the queue has no messages?
12. Why does a durable queue not mean the entire pipeline has an exactly-once guarantee?

## Summary

The **AMQP inbound channel adapter** is a one-way bridge from a **RabbitMQ queue**, through a **Spring AMQP listener container** and **MessageConverter**, to a **MessageChannel** in a Spring Integration application. To use this endpoint properly, you need to understand **exchange–binding–queue**, payload and header types after conversion, and the relationship between **ACK, exceptions, redelivery, and business outcomes**. A synchronous DirectChannel keeps the processing path clear; switching to asynchronous processing requires re-evaluating the ACK point. A reliable flow requires bounded retries, a DLQ, idempotency, prefetch/concurrency control, connection security, and operational metrics for both RabbitMQ and the application. This is the foundation for connecting AMQP with other adapters, gateways, and service activators in Spring Integration without confusing technical delivery with business completion.
