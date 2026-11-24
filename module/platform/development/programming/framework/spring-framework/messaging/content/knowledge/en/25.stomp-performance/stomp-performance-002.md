# Pool Sizing, Queues, and the Impact of Blocking Tasks in Spring STOMP

## Learning Objectives

After this lesson, you can:

- Describe the message flow through `clientInboundChannel`, `brokerChannel`, and `clientOutboundChannel`.
- Distinguish between thread pools, executor task queues, and per-WebSocket-session send buffers.
- Explain the relationship between `corePoolSize`, `maxPoolSize`, and `queueCapacity` of `ThreadPoolExecutor`.
- Choose different pool configurations for CPU-bound work, I/O-bound work, and sending messages to slow clients.
- Recognize how a blocking operation inside `@MessageMapping` increases latency and message backlog.
- Offload blocking work to a separate executor or handle it asynchronously.
- Set buffer limits, send time limits, and message size limits to control backpressure.
- Monitor metrics and perform load testing to tune configuration based on real data.

## 1. Why Does STOMP Performance Depend on Pools and Queues?

Spring STOMP does not process all messages on a single thread. Messages pass through channels; some channels use executors and thread pools to perform work asynchronously.

A common processing flow:

~~~text
WebSocket clients
       |
       v
clientInboundChannel
       |
       +---- /app/... ----> @MessageMapping controller
       |                         |
       |                         v
       |                    brokerChannel
       |                         |
       +---- /topic/... --------+
                                 |
                                 v
                            Message broker
                                 |
                                 v
                         clientOutboundChannel
                                 |
                                 v
                         WebSocket sessions
~~~

Three main channels:

| Channel | Data Direction | Work |
|---|---|---|
| `clientInboundChannel` | Client → server | Receives STOMP frames, routes to controller or broker |
| `brokerChannel` | Server application → broker | Transfers messages sent by controllers, services, or `SimpMessagingTemplate` to the broker |
| `clientOutboundChannel` | Broker → client | Sends messages to the corresponding WebSocket sessions |

By default, `clientInboundChannel` and `clientOutboundChannel` are configured with thread pools sized at twice the number of available processors. This is a framework starting value, not the optimal size for every application.

Performance depends on multiple factors at the same time:

- Number of active WebSocket sessions.
- Messages per second and number of subscribers receiving each message.
- Payload size and JSON conversion overhead.
- Processing time of `@MessageMapping` methods.
- Ratio of CPU-bound and I/O-bound work.
- Network speed and the client's ability to receive data.
- Connection counts and limits of databases, HTTP services, or external brokers.

There is no single thread pool number suitable for every workload. You need to understand where each queue lives and what work it is waiting on.

## 2. Distinguishing Thread Pools and Queue Types

In a STOMP application, the word "queue" can refer to several different things:

1. **Executor task queue:** holds tasks waiting to be processed when worker threads are busy. For example, the queue of `clientInboundChannel`.
2. **Per-session send buffer:** holds messages waiting to be sent to a specific WebSocket client when the previous send has not yet completed.
3. **Broker queue or broker backlog:** queue state managed by an external message broker, if the application uses an external broker.
4. **Business queue:** a work queue created separately by the application, such as an executor for report processing or background tasks.

These queue types have different limits and measurement methods. Increasing `queueCapacity` on the inbound executor does not increase the client send buffer. Increasing `sendBufferSizeLimit` also does not make the database or broker process faster.

A single message can pass through multiple waiting points. For example:

~~~text
clientInboundChannel task queue
          |
          v
@MessageMapping handler
          |
          v
brokerChannel
          |
          v
broker processing / broker queue
          |
          v
clientOutboundChannel task queue
          |
          v
per-session send buffer
          |
          v
network and client
~~~

If you only look at the total number of waiting messages without identifying where they sit, increasing a pool may speed up one segment of the flow while overloading the next segment.

## 3. Three Key Properties of ThreadPoolExecutor

A `ThreadPoolExecutor` has three properties you need to understand:

| Property | Meaning |
|---|---|
| `corePoolSize` | Baseline number of worker threads the pool maintains |
| `maxPoolSize` | Maximum number of worker threads that can be created |
| `queueCapacity` | Number of tasks that can wait in the queue when existing workers are busy |

Overview of how it works:

1. If the number of running workers is less than `corePoolSize`, the executor creates a new worker to take the task.
2. Once `corePoolSize` is reached, new tasks are placed in the queue if space remains.
3. Only when the queue is full does the executor increase workers beyond core, up to `maxPoolSize`.
4. If the queue is full and the pool has reached `maxPoolSize`, new tasks are rejected according to the executor's rejection policy.

A common misconception is that setting `corePoolSize=10` and `maxPoolSize=20` means the pool will always automatically scale from 10 to 20 when load increases.

By default, Spring uses a very large queue capacity (`Integer.MAX_VALUE`) for normally registered task executors. When the queue is virtually unbounded, new tasks continue to be queued once core threads are busy; the pool does not need to scale up to max. Therefore, `maxPoolSize` is effectively ignored.

Example:

- Core = 8, Max = 32, Queue = 1000.
- Eight workers are busy processing tasks.
- New tasks keep entering the queue.
- The pool only creates additional workers when the queue is full.
- If the queue never fills up, the pool may run only eight workers even though max is 32.

An unbounded queue can mask a shortage of workers: requests continue to be accepted, but wait times grow longer and longer, memory increases, and latency eventually becomes uncontrollable.

## 4. Configuring Pools for clientInboundChannel and clientOutboundChannel

Spring allows configuring separate executors for the two channels:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfiguration
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void configureClientInboundChannel(
            ChannelRegistration registration) {

        registration.taskExecutor()
                .corePoolSize(8)
                .maxPoolSize(24)
                .queueCapacity(200)
                .keepAliveSeconds(60);
    }

    @Override
    public void configureClientOutboundChannel(
            ChannelRegistration registration) {

        registration.taskExecutor()
                .corePoolSize(8)
                .maxPoolSize(24)
                .queueCapacity(500)
                .keepAliveSeconds(60);
    }

    @Override
    public void registerStompEndpoints(
            StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(
            MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

The numbers 8, 24, 200, and 500 are only illustrative values to explain configuration. Do not use them as a fixed production recommendation.

### 4.1 clientInboundChannel

This channel receives messages from clients and passes them to controllers or the broker. If handlers are primarily CPU-bound, the thread count should usually be close to the number of available processors. If handlers frequently wait on a database, HTTP service, or external resource, the pool may need more threads so other workers can continue processing messages.

However, increasing threads does not make the database process faster. If the database connection pool only allows 20 connections, creating hundreds of workers all waiting on the database can increase context switching and contention without increasing throughput.

### 4.2 clientOutboundChannel

This channel sends messages from the server to WebSocket clients. Clients on fast networks usually consume messages quickly. Clients on slow or low-bandwidth networks prolong send times, causing many outbound tasks to wait for processing.

Increasing the pool can help serve more slow clients, but per-session buffer and send time limits are still needed. A large pool cannot compensate indefinitely for clients that receive messages slowly.

## 5. How Do Blocking Tasks Starve the Inbound Pool?

Suppose `@MessageMapping` calls an external API that takes 2 seconds:

~~~java
@MessageMapping("/orders/status")
public OrderStatus getStatus(OrderRequest request) {
    return orderService.fetchStatusFromRemoteApi(request.orderId());
}
~~~

If the method makes a synchronous HTTP call, the `clientInboundChannel` worker thread must wait for the entire duration of the call. Meanwhile, other messages continue arriving on the channel and wait in the executor queue.

Example with a pool of 8 workers:

- Eight messages concurrently call the slow API.
- All eight workers are waiting on I/O.
- The ninth message has no free worker and must be queued.
- As load increases, the queue keeps growing.
- Latency for new messages increases even when those messages themselves require very little CPU processing.

Tasks that commonly cause blocking:

- Slow JDBC queries or waiting to acquire a connection.
- Synchronous HTTP requests to other services.
- Filesystem or remote storage calls.
- Waiting on a lock or monitor held by another thread.
- `Thread.sleep()`, `Future.get()`, or `CompletableFuture.join()` inside a handler.
- Waiting synchronously for a background task to complete.

A blocking handler does not only affect its own message. It occupies a worker thread that other messages need to use.

## 6. Choosing Pool Sizes by Workload Type

### CPU-bound

Examples: computation, encryption, in-memory data processing.

- Start with a worker count close to the number of available CPUs.
- Monitor CPU utilization and context switching.
- Increasing threads too much usually increases CPU contention.
- Optimizing algorithms and reducing data processed is usually more helpful than enlarging the pool.

### I/O-bound

Examples: database calls or HTTP services with significant wait time.

- May require more workers than CPUs.
- Measure actual wait time and the ratio of blocked threads.
- Limit concurrent tasks according to connection pools and quotas of external services.
- Use timeouts for external requests.
- Consider offloading to a separate executor or asynchronous APIs.

### Mixed Workload

A handler that converts JSON, checks permissions, queries a database, and broadcasts messages has multiple stages with different characteristics. You need to measure each stage to find what actually consumes time.

Do not choose pool sizes based solely on the number of WebSocket sessions. One session may send many messages, while a single message may broadcast to hundreds of subscribers.

## 7. Offloading Blocking Work to a Separate Executor

If a handler needs to perform blocking I/O, that part can be moved to a separate executor. When the method returns a `CompletableFuture`, Spring can continue handling the result asynchronously.

Example:

~~~java
@Configuration
public class WorkExecutorConfiguration {

    @Bean
    public ThreadPoolTaskExecutor blockingIoExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(8);
        executor.setMaxPoolSize(24);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("stomp-io-");
        executor.initialize();

        return executor;
    }
}
~~~

Controller using the separate executor:

~~~java
@Controller
public class OrderController {

    private final OrderService orderService;
    private final Executor blockingIoExecutor;

    public OrderController(
            OrderService orderService,
            @Qualifier("blockingIoExecutor")
            Executor blockingIoExecutor) {
        this.orderService = orderService;
        this.blockingIoExecutor = blockingIoExecutor;
    }

    @MessageMapping("/orders/status")
    public CompletableFuture<OrderStatus> getStatus(
            OrderRequest request) {

        return CompletableFuture.supplyAsync(
                () -> orderService.fetchStatusFromRemoteApi(
                        request.orderId()),
                blockingIoExecutor);
    }
}
~~~

When the handler returns a `CompletableFuture`, the inbound worker can be freed while the I/O task continues on the separate executor. When the future completes, Spring processes the return value and sends the message via the normal mechanism.

Notes:

- Use an executor with a bounded queue to control pending work.
- Configure timeouts for HTTP/database operations.
- Handle future exceptions so errors are not lost or only appear in logs.
- Set a concurrency limit appropriate for the target service.
- Do not blindly use `ForkJoinPool.commonPool()` for blocking I/O.
- Do not offload every tiny operation to another executor if scheduling overhead outweighs the benefit.

Offloading only helps when the new executor is properly configured and monitored. If the separate executor also has an unbounded queue and all workers are waiting on the database, the problem simply moves from the inbound channel to the new executor.

## 8. Bounded Queues and Backpressure

When the task arrival rate exceeds the processing rate, the queue grows. If the queue is unbounded, the application can keep accepting tasks until excessive memory is consumed.

A bounded queue gives the application a clear backlog threshold:

~~~java
registration.taskExecutor()
        .corePoolSize(8)
        .maxPoolSize(24)
        .queueCapacity(200);
~~~

When the queue is full and the pool has reached max, the executor rejects tasks according to the configured rejection policy. The application must observe and handle that situation.

Some principles:

1. Size the queue based on acceptable latency, not just available RAM.
2. The longer a task waits, the staler the message is when processed.
3. For messages carrying the latest state, you can design coalescing or drop stale updates as business rules allow.
4. For important business commands, return an error or apply an appropriate retry/durable buffering mechanism; do not silently drop them.
5. Avoid letting producers emit messages faster than consumers over sustained periods without limits.

Backpressure is not just increasing the queue. It is how you regulate producer rates, limit concurrent work, and decide what the application does when consumers cannot keep up.

## 9. BrokerChannel and the Impact of Asynchronous Sending

`brokerChannel` transfers messages from server-side code to the message broker. By default, messages from the application to the broker are sent synchronously. This means code calling `SimpMessagingTemplate` can receive an exception if sending fails.

An executor can be configured for the broker channel:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableSimpleBroker("/topic", "/queue");

    registry.configureBrokerChannel()
            .taskExecutor()
            .corePoolSize(4)
            .maxPoolSize(16)
            .queueCapacity(200);
}
~~~

When an executor is added, sending messages to the broker becomes asynchronous. Code calling the template may finish before the broker processes the message, so send errors no longer necessarily surface immediately at the call site.

Only configure an executor for the broker channel when you understand the change in error timing and have appropriate observability in place. If business logic requires confirmation that a message was accepted, use a receipt or broker-appropriate acknowledgment mechanism; do not treat normal return of the send method as proof that all subscribers received the message.

## 10. Outbound Buffer and Slow Clients

Even when `clientOutboundChannel` has enough workers, a WebSocket session must still handle message sending safely. At any given time, only one thread sends data to a client; other messages may have to wait in the session's buffer.

If the server emits messages faster than the client can receive:

- The per-session send buffer grows.
- Memory used for that session increases.
- Outbound tasks may have to wait.
- Slow clients can affect overall throughput.

Spring provides two limits:

- `sendTimeLimit`: limits the send time.
- `sendBufferSizeLimit`: limits the amount of data buffered when sending to a WebSocket session or an HTTP response in SockJS fallback.

Example:

~~~java
@Override
public void configureWebSocketTransport(
        WebSocketTransportRegistration registration) {

    registration
            .setSendTimeLimit(15 * 1000)
            .setSendBufferSizeLimit(512 * 1024);
}
~~~

The values 15 seconds and 512 KiB are illustrative examples. Choose based on message size, publish rate, subscriber count, network, and client receiving capacity.

When the send or buffer limit is exceeded, Spring can clear the session state and attempt to close the connection. This is a mechanism to protect resources from clients that cannot keep up, not a guarantee of successful message delivery.

If clients need the latest data, consider reducing broadcast frequency, batching multiple updates, sending deltas only, or letting clients fetch a fresh snapshot via an API.

## 11. Message Size Limit and Memory

Message size directly affects memory used by:

- Payloads waiting in executor queues.
- Per-session send buffers.
- Buffers reassembling multiple WebSocket messages into one STOMP message.
- JSON converters and objects inside the application.
- External brokers or HTTP transports.

Spring allows limiting the size of incoming STOMP messages:

~~~java
@Override
public void configureWebSocketTransport(
        WebSocketTransportRegistration registration) {

    registration.setMessageSizeLimit(128 * 1024);
}
~~~

`setMessageSizeLimit` limits the size of a sub-protocol message such as a STOMP frame that may be assembled from multiple WebSocket messages. This is a different limit from `sendBufferSizeLimit`, which controls the amount of data waiting to be sent to a session.

Do not increase the message size limit just to silence large-payload errors. First, check whether clients are sending unnecessary payload data and whether pagination, compression, file references, or a separate data download API can be used.

## 12. Processing Order and Preserve Order Overhead

Because executors have multiple threads, messages can be processed concurrently. The order received from the client or the order published by the broker does not necessarily match the order handlers finish or the order clients receive them.

If the application needs to preserve order within the same session, you can enable:

~~~java
@Override
public void registerStompEndpoints(
        StompEndpointRegistry registry) {
    registry.addEndpoint("/ws")
            .setPreserveReceiveOrder(true);
}

@Override
public void configureMessageBroker(
        MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableSimpleBroker("/topic");
    registry.setPreservePublishOrder(true);
}
~~~

- `setPreserveReceiveOrder(true)` preserves the processing order of messages received from the same client session.
- `setPreservePublishOrder(true)` preserves the publish order to the same client session.

These two options have a performance cost because messages in a session are processed sequentially at the corresponding stage. Enable them only when business logic truly requires ordering.

Across multiple clients or multiple sessions, these two options do not create a global order for all messages. If business ordering is required, use sequence numbers, versions, or domain-level synchronization mechanisms.

## 13. Monitoring Pools and Queues

When using `@EnableWebSocketMessageBroker`, Spring provides the `WebSocketMessageBrokerStats` bean to aggregate infrastructure metrics. According to current documentation, this bean logs at INFO level every 30 minutes by default and can be exported via JMX.

Metrics to monitor:

| Metric | Sign to Watch |
|---|---|
| Current / Total WebSocket sessions | Active connections and total sessions created |
| Abnormally closed / Connect failures | Proxy, network, heartbeat, or transport errors |
| Send limit exceeded | Client receiving too slowly or buffer/send timeout too low |
| Client inbound channel | Growing task queue indicates the application cannot keep up with inbound messages |
| Client outbound channel | Growing task queue may indicate slow clients or weak networks |
| STOMP broker relay TCP connections | Connections to external broker compared with WebSocket session count |
| SockJS task scheduler | Status of the scheduler sending heartbeats for HTTP fallback |

Combine Spring stats with system metrics:

- Executor active threads, queue depth, completed tasks, and rejected tasks.
- CPU, heap, garbage collection, and thread dumps.
- Database connection pool active/pending and query latency.
- HTTP client connection pool and timeouts.
- Broker queue depth, publish/consume rate, and consumer lag.
- WebSocket send latency, disconnect rate, and payload size.

If the inbound queue grows, check handler duration, database queries, and HTTP calls. If the outbound queue grows, check slow clients, fan-out, message size, and send buffers.

## 14. Metric-Driven Tuning Process

A practical tuning process:

1. Record baseline: session count, message rate, payload size, p95/p99 latency, CPU, heap, and queue depth.
2. Separate CPU-bound and I/O-bound workloads.
3. Measure average and high-percentile processing times of handlers.
4. Check database/HTTP pools before increasing inbound threads.
5. Configure core, max, and bounded queues for inbound and outbound separately.
6. Set send timeout and send buffer limits according to client capabilities.
7. Gradually increase load to identify the point where queues start growing continuously.
8. Verify behavior when queues are full and when clients are slow.
9. Compare throughput, p95/p99 latency, rejections, and memory before and after each change.
10. Keep the simplest configuration that meets target load and re-test when message size or fan-out changes.

Do not change all parameters simultaneously. If you increase max threads, queue capacity, send buffer, and message size limit all at once, it will be hard to tell which change produced the effect.

## 15. Common Configuration Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Only increasing `maxPoolSize` while keeping an unbounded queue | Pool still runs near core size | Set a bounded queue capacity if the pool needs to scale beyond core |
| Making the inbound pool too large | Increases contention and puts pressure on databases/HTTP services | Measure blocking ratio and limit according to downstream resources |
| Using one pool for all types of work | Slow tasks can occupy message processing workers | Separate executors for blocking I/O or background work |
| Using an unbounded queue | Backlog and memory grow when producers outpace consumers | Set a bounded queue and a policy for handling a full queue |
| Only increasing the outbound pool | Does not solve slow clients and growing per-session buffers | Combine with send timeout and send buffer limits |
| Increasing send buffer indefinitely | A slow client can hold large amounts of data in the heap | Set limits and reduce fan-out/message frequency |
| Enabling preserve order by default | Reduces parallelism even when business logic does not require it | Enable only for flows that truly need ordering |
| Ignoring brokerChannel | Asynchronous sending can change when errors are observed | Understand synchronous/asynchronous semantics before configuring |
| Measuring CPU only | Misses queue backlogs and downstream waits | Monitor executors, database, broker, outbound buffers, and latency |

## 16. Self-Check Exercises

### Exercise 1

A pool has `corePoolSize=8`, `maxPoolSize=32`, `queueCapacity=Integer.MAX_VALUE`. When all eight workers are busy, how is a new task normally handled?

**Answer:** The new task is placed in the unbounded queue. Because the queue still accepts tasks, the executor does not need to scale workers beyond core; `maxPoolSize` effectively has no impact.

### Exercise 2

A handler queries the database synchronously and typically waits 1 second. Why can the inbound queue grow even though CPU is not high?

**Answer:** Inbound workers are being held while waiting on I/O. When multiple workers wait on the database at the same time, new messages must wait in the queue even though the CPU still has idle capacity.

### Exercise 3

Does increasing `sendBufferSizeLimit` make a client on a slow network receive messages faster?

**Answer:** No. It only allows holding more pending outbound data before hitting the limit. If the publish rate continuously exceeds the receive rate, the buffer will continue to fill and latency will still rise.

### Exercise 4

When should `setPreservePublishOrder(true)` be used?

**Answer:** When the application needs to preserve publish order within the same client session. This option has a performance cost, so enable it only when business logic requires it.

### Exercise 5

What does `brokerChannel` sending synchronously by default mean for code calling `SimpMessagingTemplate`?

**Answer:** Code calling the template can immediately receive an exception when sending to the broker fails. If an executor is configured for brokerChannel, sending becomes asynchronous and the timing of error reporting changes.

## References

- [Spring Framework — Performance](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/configuration-performance.html)
- [Spring Framework — Flow of Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html)
- [Spring Framework — Monitoring](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/stats.html)
- [Spring Framework — Order of Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/ordered-messages.html)
- [Spring Framework Javadoc — TaskExecutorRegistration](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/config/TaskExecutorRegistration.html)
- [Spring Framework Javadoc — MessageBrokerRegistry](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/config/MessageBrokerRegistry.html)
- [Spring Framework Javadoc — WebSocketTransportRegistration](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/socket/config/annotation/WebSocketTransportRegistration.html)
