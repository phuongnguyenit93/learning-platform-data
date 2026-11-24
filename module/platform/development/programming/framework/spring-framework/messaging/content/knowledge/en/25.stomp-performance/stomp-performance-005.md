# Distinguishing Frame Order, Execution Order, and Business Order

In a STOMP application, seeing a client send message A before message B does not mean the server is guaranteed to finish processing A before B, nor does it mean the client will receive result A before result B. Ordering exists at multiple layers: frame order on the connection, message order as Spring dispatches through channels, completion order of asynchronous work, and business order required by the domain.

To build a correct system, you must identify exactly which layer needs to preserve order. Spring has options to preserve receive and publish order per WebSocket session. When business logic requires ordering by order, account, or a specific entity, the application must still design sequences, concurrency control, and transactions at the business layer.

## 1. Three Types of Ordering to Distinguish

| Order Type | Question to Answer | Guarantee Scope |
| --- | --- | --- |
| **Frame order** | Which frame was sent/received first on a STOMP connection? | Byte/frame order on each connection stream |
| **Execution order** | Which message does Spring process first, which handler finishes first, which outbound frame is written first? | Depends on channel executors, ordering configuration, and asynchronous work |
| **Business order** | Which command must take effect first according to domain rules? | Designed by the specific application and broker, usually by aggregate or business key |

For example, a client sends two commands on the same WebSocket session:

1. Message A: update order quantity to 2.
2. Message B: confirm the order.

The client sent A before B on the stream. However, if the server processes the two messages on different worker threads, B can complete before A. If B requires the order to have already been updated, the result can be wrong even though the frames were sent in the right order.

## 2. Frame Order on a STOMP Connection

STOMP is a frame-based protocol running over a reliable two-way streaming transport such as TCP. On a single connection, bytes are transmitted in order; thus, frames written consecutively by a client to the same STOMP connection are read by the server in stream order. Similarly, the server writes frames in a certain order onto that connection and the client receives them in transmission order.

This applies only per connection. If two browsers, two devices, or two producers open two different connections and send messages simultaneously, STOMP defines no global order between the two streams. Send timestamps from two machines are also insufficient to establish an absolute order because clocks, network latency, and scheduling differ.

Furthermore, STOMP treats destinations as opaque strings and does not define delivery semantics for destinations. The meaning of /topic, /queue, delivery order, queue durability, or distribution among consumers depends on the specific server/broker. You cannot infer global FIFO solely from a destination name.

## 3. Message Flow and Concurrency Points in Spring

In Spring WebSocket/STOMP, frames received from WebSocket are decoded into Spring Messages and sent through channels:

~~~text
WebSocket client
      |
      v
STOMP frame decoder
      |
      v
clientInboundChannel
      |
      +---- /app/... ----> @MessageMapping controller
      |                         |
      |                         v
      |                    brokerChannel
      |                         |
      +---- /topic,... ---------+
                                |
                                v
                           Message broker
                                |
                                v
                        clientOutboundChannel
                                |
                                v
                         WebSocket session
~~~

Important channels:

- **clientInboundChannel**: receives messages from the WebSocket client and routes them to a controller or broker.
- **brokerChannel**: transfers messages from server-side code to the message broker.
- **clientOutboundChannel**: transfers messages from the broker back to the WebSocket client.

Spring uses asynchronous channels backed by executors/thread pools. Therefore, messages can be processed by different threads. By default, the order in which handlers are invoked or the order in which clients receive messages does not necessarily match the order messages were received or published.

A request may pass through a controller, call a service, query a database, wait on an HTTP API, or send results asynchronously. Each waiting point can change completion order. This is why frame receive order must be distinguished from work completion order.

## 4. Preserving Order of Messages Sent by Clients to Spring

Since Spring Framework 6.1, you can instruct Spring to process inbound messages in receive order within the same session using **setPreserveReceiveOrder(true)** on **StompEndpointRegistry**.

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfiguration
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
        registry.setPreserveReceiveOrder(true);
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

When this flag is enabled, messages from the same client session are passed to **clientInboundChannel** one message at a time, preserving the order Spring received them. Other sessions can still be processed concurrently.

If client A sends frame 1 and then frame 2, Spring dispatches frame 1 before frame 2 on that session's inbound channel. However, this flag does not establish order between two different client sessions.

**Version note:** setPreserveReceiveOrder was added in Spring Framework 6.1. Projects using Spring 6.0 or earlier do not have this API. Check the actual version before using this configuration.

## 5. Preserving Order of Messages Sent by Spring to Clients

The outbound direction has a similar issue. Messages from the broker are passed to **clientOutboundChannel** to be written to the WebSocket session. Because the channel uses a ThreadPoolExecutor, messages can be processed by multiple threads and clients may receive results in a different order from the original publish order.

You can enable **setPreservePublishOrder(true)** on **MessageBrokerRegistry**:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableSimpleBroker("/topic", "/queue");
    registry.setPreservePublishOrder(true);
}
~~~

When enabled, messages within the same client session are passed through clientOutboundChannel one message at a time to preserve publish order. This flag has been available since Spring Framework 5.1.

Both flags can be enabled in the same configuration:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class OrderedWebSocketConfiguration
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
        registry.setPreserveReceiveOrder(true);
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
        registry.setPreservePublishOrder(true);
    }
}
~~~

The two flags have different purposes:

| Configuration | Location | Preserves Order Of |
| --- | --- | --- |
| setPreserveReceiveOrder(true) | registerStompEndpoints | Client sending into Spring, per session |
| setPreservePublishOrder(true) | configureMessageBroker | Spring/broker publishing to client, per session |

Both incur performance overhead. Enable them only when the application needs ordering for messages within a session. They do not guarantee ordering across sessions, across multiple Spring instances, or across independent producers.

## 6. Important Limitation: Dispatch Order Is Not Completion Order

Spring's two flags control the order in which messages are passed through channels. They do not force an asynchronous job to complete before the next job starts.

Spring allows `@MessageMapping` -> Spring allows @MessageMapping methods to return **CompletableFuture**, **CompletionStage**, or an equivalent future. This is useful when handling long I/O tasks, but two futures can complete in the reverse order of their creation.

Illustrative example:

~~~java
@Controller
public class OrderController {

    private final OrderService orderService;
    private final Executor taskExecutor;

    public OrderController(
            OrderService orderService,
            @Qualifier("applicationTaskExecutor") Executor taskExecutor) {
        this.orderService = orderService;
        this.taskExecutor = taskExecutor;
    }

    @MessageMapping("/orders/update")
    public CompletableFuture<OrderResult> update(
            @Payload OrderCommand command) {

        return CompletableFuture.supplyAsync(
                () -> orderService.apply(command),
                taskExecutor);
    }
}
~~~

Suppose the client sends two consecutive commands:

- Command sequence 10 starts querying an external system and takes 2 seconds.
- Command sequence 11 only updates cached data and takes 100 ms.

Even with **setPreserveReceiveOrder(true)** enabled, the controller can launch the future for sequence 10, return immediately, and then process sequence 11. The future for 11 finishes before the future for 10. If results are sent when futures complete, the client can receive the result for sequence 11 before sequence 10.

Similarly, **setPreservePublishOrder(true)** only preserves the order of messages as they are placed into the outbound channel. If asynchronous work completed in order 11 then 10, the outbound channel will preserve order 11 then 10; it has no idea that sequence 10 was supposed to be emitted first.

If completion order matters, coordinate work by business key or wait for the previous work for the same key to finish before starting the next one.

## 7. Business Order Must Be Defined by the Domain

A system may need different rules:

- Updates to the same order must follow a sequence.
- Operations on the same account must be serialized to prevent negative balances.
- Events from the same device must follow measurement or emission order.
- Independent notifications for two users can be processed in parallel.

You should not use a global queue if only certain entities need serialization. Usually you preserve order by **aggregate ID**, such as orderId or accountId, and allow different aggregates to be processed concurrently.

There are three common approaches:

1. **Sequence number:** the producer or authoritative system issues monotonically increasing sequence numbers per aggregate. The consumer checks the next expected sequence before applying.
2. **Partition/queue by key:** the broker or messaging platform routes the same aggregate into the same partition/consumer lane, guaranteeing sequential processing within the scope supported by the broker.
3. **Database serialization:** use transactions and per-entity locking so only one transaction updates the aggregate at a time; check sequence/version before committing.

Whichever approach you choose, clearly define how to handle duplicates, missing sequences, and retries. Ordering is meaningless if an event is applied twice or an event is lost.

## 8. Sequence Control Inside a Transaction

For example, a command has orderId, eventId, and sequence. The sequence is issued by the authoritative system when creating the command. The consumer locks the order record inside a transaction, checks the sequence, and only applies the next command.

~~~java
public record OrderCommand(
        UUID orderId,
        String eventId,
        long sequence,
        String action) {
}
~~~

The repository can lock the row to be updated:

~~~java
public interface OrderRepository extends JpaRepository<Order, UUID> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select o from Order o where o.id = :id")
    Optional<Order> findForUpdate(@Param("id") UUID id);
}
~~~

Service processing the command:

~~~java
@Service
public class OrderCommandService {

    private final OrderRepository orders;
    private final ProcessedEventRepository processedEvents;

    public OrderCommandService(
            OrderRepository orders,
            ProcessedEventRepository processedEvents) {
        this.orders = orders;
        this.processedEvents = processedEvents;
    }

    @Transactional
    public void apply(OrderCommand command) {
        Order order = orders.findForUpdate(command.orderId())
                .orElseThrow();

        if (processedEvents.existsById(command.eventId())) {
            return; // Same event was already processed.
        }

        long expected = order.getLastAppliedSequence() + 1;

        if (command.sequence() != expected) {
            throw new OutOfOrderCommandException(
                    "Expected sequence " + expected
                            + " but received " + command.sequence());
        }

        order.apply(command.action());
        order.setLastAppliedSequence(command.sequence());

        processedEvents.save(new ProcessedEvent(command.eventId()));
    }
}
~~~

This is an illustrative example; entities, repositories, and exceptions must be defined according to the project. The PESSIMISTIC_WRITE lock serializes transactions updating the same order row. The sequence check detects out-of-order commands; the transaction rolls back so state is not updated.

If the sequence is greater than expected, do not silently drop the command. You can store the command in a pending area and reprocess it when the missing sequence arrives, or send it to a retry/dead-letter workflow. If the sequence is less than expected but the eventId has never been processed, it may be a stale command or conflicting data; a clear policy is needed rather than treating every case as a duplicate.

Checking eventId and updating the aggregate should happen in the same transaction to avoid marking an event processed while the order change did not commit, or vice versa. When publishing events to a broker after commit, consider a transactional outbox to store the event in the same data transaction, after which a publisher emits in aggregate sequence order.

## 9. Multiple Producers and Global Ordering

When two clients send commands at the same time, there is no natural global order based solely on client timestamps. Device clocks can drift and messages can traverse the network with different latencies.

If the domain needs an order, you must choose an authoritative source to establish it:

- Database generating a sequence inside a transaction.
- A single service issuing versions for the aggregate.
- A broker partition chosen by key with clear ordering semantics.
- A coordinator serializing commands for the same aggregate.

For example, two clients concurrently update order-42. Both may send expected sequence 8. A database lock/version check lets one command win and the other receive a conflict. The client must reload state or send a new command with the right version; do not assume send time decides which command wins.

Across multiple Spring application instances, Java locks such as **synchronized** only take effect within one JVM. They do not protect an entity when a request is processed on another instance. Use database locks/versions, distributed locks with fencing tokens, or broker partitioning as appropriate for the requirement.

## 10. Transactions and Event Publish Ordering

Another issue arises when the application updates the database and publishes a STOMP event. If published before the transaction commits, subscribers may receive notifications about uncommitted state. If the transaction rolls back, the sent event still exists and clients see state that never actually happened.

One option is emitting events after transaction commit, but if the process dies between commit and publish, the event can be lost. A transactional outbox closes this gap by storing domain changes and events in the same database transaction; a separate publisher reads the outbox and emits events.

The outbox should store aggregate ID and sequence so the publisher emits in exact order per aggregate. If there are multiple publisher workers, you must partition or lock by aggregate to prevent a later worker from publishing sequence 12 before a worker processing sequence 11. Consumers should still be idempotent and check sequence numbers because the network/broker can redeliver.

**@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)** can be useful for emitting events after commit in simple applications. However, an after-commit listener does not guarantee durable event delivery if the process stops between commit and publish; an outbox is more suitable when losing events is unacceptable.

## 11. Broker Ordering and STOMP Limitations

STOMP does not define delivery semantics for destinations. Names like **/topic** or **/queue** do not automatically guarantee FIFO, durability, or ordering across producers. Check the documentation for your specific broker.

Even when a broker provides a FIFO queue, check the scope of the guarantee:

- Is FIFO per queue or per partition?
- Do multiple producers have global order or only per-connection order?
- Can multiple consumers process in parallel and finish in reverse order?
- Can redelivery after an error appear ahead of newer messages?
- Do retries/dead-lettering change the order?
- Does the broker support message groups or key-based routing?

For example, a broker delivers message 21 and then 22 to the same consumer, but the consumer uses two worker threads. Worker 22 finishes before worker 21. The broker may have delivered in order, yet the application still completes business processing out of order. To preserve end-to-end order, both broker delivery and consumer processing must follow the same serialization rules.

## 12. Performance When Preserving Order

Preserving order typically reduces concurrency within the scope being serialized. With Spring:

- **setPreserveReceiveOrder(true)** limits inbound dispatch within the same session to sequential order.
- **setPreservePublishOrder(true)** limits outbound publish to the same session to sequential order.
- Other sessions can still be processed concurrently.
- Asynchronous work inside controllers/services still requires its own coordination mechanism.
- Preserving order does not fix bottlenecks caused by databases, external APIs, or slow clients.

By default, Spring configures thread pools for clientInboundChannel and clientOutboundChannel at twice the number of available processors. Pool sizes must match CPU-bound or I/O-bound load types. Increasing thread pools does not create order; enabling preserve-order also does not replace proper pool sizing and backpressure design.

If only certain business flows need ordering, prefer serializing by aggregate key rather than forcing the entire system to process one message at a time. Measure throughput, p95/p99 latency, and queue depth before and after enabling the flags.

## 13. How to Diagnose Out-of-Order Messages

When events arrive out of order, do not look only at timestamps displayed on the UI. Record the following milestones:

1. **Client send:** session ID, frame/event ID, sequence, and client send time.
2. **Server receive:** time the frame is decoded and placed into clientInboundChannel.
3. **Handler start:** time `@MessageMapping` begins processing.
4. **Business commit:** time the transaction completes and the new version/sequence is committed.
5. **Broker publish:** time the event is sent to brokerChannel or the broker.
6. **Outbound send:** time the message is placed into clientOutboundChannel and written to WebSocket.
7. **Client receive:** time the client receives and processes the message.

Attach a **correlationId**, **aggregateId**, and **sequence** across all logs. Use sequence to verify logical order; timestamps only help locate delays and intervals. If you only log low-precision timestamps, two messages can share the same timestamp even though their actual order differs.

Common symptoms:

| Observation | Layer Likely Responsible |
| --- | --- |
| Client writes frame A then B, but server logs receiving B before A on the same session | Check client framing, transport, session mapping, and logging points |
| Server receives A then B, but handler starts B before A | Inbound channel executor; consider preserveReceiveOrder |
| Handler A starts before B, but B commits before A | Async service, database lock, or I/O duration; needs business sequencing |
| Service commits A then B, but client receives B before A | Outbound channel; consider preservePublishOrder and broker behavior |
| Two different sessions have different orders | No global order; needs business sequence if domain requires it |
| Broker delivers A then B, but consumer completes B before A | Consumer concurrency; process by key or sequence |

## 14. Testing Ordering

A good test should isolate layers rather than only asserting final order on the client:

- Send A then B on the same session; record handler start order with preserveReceiveOrder off and on.
- Use CountDownLatch or CompletableFuture to control completion timing so B deliberately completes before A; verify the inbound flag does not automatically guarantee completion order.
- Publish two events in deterministic order to the same session; verify the outbound flag preserves publish order.
- Send to the same aggregate from two different sessions; verify sequence checks prevent out-of-order updates.
- Send duplicate eventIds; verify the consumer processes idempotently.
- Send a sequence with a gap; verify the event is retried/pended or reports a clear error.
- Run tests with multiple application instances if production is deployed clustered.
- Test transaction rollback and outbox retry to ensure events are not emitted with invalid state or wrong sequence.

Avoid using Thread.sleep to force ordering in tests. Use latches, barriers, futures, or test executors to precisely control when each handler starts and completes.

## 15. References

- [Spring Framework — Order of Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/ordered-messages.html): preserveReceiveOrder, preservePublishOrder, and per-session scope.
- [Spring Framework — Flow of Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html): clientInboundChannel, brokerChannel, clientOutboundChannel, and message routing.
- [Spring Framework — Performance](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/configuration-performance.html): channel thread pools, blocking work, send limits, and scaling.
- [Spring Framework — Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-annotations.html): @MessageMapping and CompletableFuture/CompletionStage support.
- [STOMP 1.2 Specification](https://stomp.github.io/stomp-specification-1.2.html): ordered stream, destination semantics, and ACK/transaction protocol.
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): transaction boundaries and transaction synchronization.
