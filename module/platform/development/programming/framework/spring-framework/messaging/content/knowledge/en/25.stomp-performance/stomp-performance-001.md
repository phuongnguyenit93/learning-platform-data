# Configuring Executors for clientInboundChannel and clientOutboundChannel

## 1. Role of the Two Message Channels

In Spring WebSocket/STOMP, messages pass through internal channels before reaching a controller, broker, or WebSocket client. The two most important client-facing channels are:

- **clientInboundChannel** receives messages from the WebSocket client after Spring decodes the STOMP frame. Frames such as CONNECT, SUBSCRIBE, SEND, and DISCONNECT enter this channel to be processed, checked by interceptors, and routed further.
- **clientOutboundChannel** receives messages from the broker or server application to send back to the WebSocket client. Spring converts the message into a STOMP frame and writes it to the corresponding session.

Overview of the flow:

~~~mermaid
flowchart LR
    C["WebSocket client"] -->|"STOMP frames"| I["clientInboundChannel"]
    I -->|"SEND /app/**"| H["@MessageMapping controller"]
    I -->|"SUBSCRIBE /topic/**"| B["Message broker"]
    H -->|"application message"| BC["brokerChannel"]
    BC --> B
    B --> O["clientOutboundChannel"]
    H -->|"user / direct reply"| O
    O -->|"STOMP frames"| C
~~~

In this flow:

- Messages from the client pass through `clientInboundChannel`.
- Messages from server-side code to the broker usually pass through `brokerChannel`.
- Messages from the broker or application sent to the client pass through `clientOutboundChannel`.

`clientInboundChannel` and `clientOutboundChannel` are `ExecutorSubscribableChannel` instances backed by thread pools. The two channels have separate executors because their workloads differ: inbound mainly processes frames and application logic; outbound mainly distributes messages to WebSocket sessions.

## 2. Why Configure the Executors?

The executor determines how many message tasks can be processed concurrently, how many tasks are queued, and how the system responds under increasing load.

If the pool is too small:

- Messages have to wait a long time in the queue.
- Processing time increases and clients experience real-time latency.
- Inbound controllers may not keep up with the client's sending rate.
- Outbound messages may be delayed when many clients receive broadcasts at the same time.

If the pool or queue is too large:

- The application may create too many threads, causing CPU and memory contention.
- A large queue holds many messages in the heap, increasing latency and risking out-of-memory errors.
- Database connection pools or external services may become overloaded if too many handlers wait on I/O simultaneously.
- Increasing max threads does not automatically increase throughput if the bottleneck is in the database, broker, network, or client.

The goal is to choose sizes suited to the type of work, processing time, number of clients, message rate, and system resource limits.

## 3. Configuration via WebSocketMessageBrokerConfigurer

Spring provides two separate callbacks:

- `configureClientInboundChannel(ChannelRegistration registration)` to configure the executor for messages from clients.
- `configureClientOutboundChannel(ChannelRegistration registration)` to configure the executor for messages sent to clients.

Use `registration.taskExecutor()` to obtain the thread pool configuration. Main methods:

| Method | Meaning |
|---|---|
| `corePoolSize(n)` | Number of core threads maintained in the pool. |
| `maxPoolSize(n)` | Maximum number of threads the pool can scale up to. |
| `queueCapacity(n)` | Maximum number of tasks queued waiting for a thread to process. |
| `keepAliveSeconds(n)` | Time that threads above the core size can remain idle before being reclaimed. |

Example configuring the two pools independently:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.ChannelRegistration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketTransportRegistration;

@Configuration
@EnableWebSocketMessageBroker
public class MessagingWebSocketConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");

        // Preserve the order of messages sent by the client within the same session.
        registry.setPreserveReceiveOrder(true);
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.enableSimpleBroker("/topic", "/queue");

        // Preserve the order of messages sent back to the same client session.
        registry.setPreservePublishOrder(true);
    }

    @Override
    public void configureClientInboundChannel(ChannelRegistration registration) {
        registration.taskExecutor()
                .corePoolSize(8)
                .maxPoolSize(16)
                .queueCapacity(200)
                .keepAliveSeconds(60);
    }

    @Override
    public void configureClientOutboundChannel(ChannelRegistration registration) {
        registration.taskExecutor()
                .corePoolSize(8)
                .maxPoolSize(16)
                .queueCapacity(500)
                .keepAliveSeconds(60);
    }

    @Override
    public void configureWebSocketTransport(WebSocketTransportRegistration registration) {
        registration
                .setSendTimeLimit(15_000)
                .setSendBufferSizeLimit(512 * 1024);
    }
}
~~~

The numbers 8, 16, 200, and 500 are only illustrative values for how to configure the pools, not general recommendations. Measure actual load, CPU count, processing time, message size, and database limits before choosing production values.

If the application already has a `WebSocketMessageBrokerConfigurer` class, add the callbacks to the existing configuration instead of creating multiple unnecessary configuration classes. Spring allows multiple configurers to work together, but splitting configuration should be intentional to avoid making it hard to follow.

## 4. How ThreadPoolExecutor Uses Core, Queue, and Max

Understanding the exact task acceptance order of `ThreadPoolExecutor` is very important:

1. If the number of running threads is less than `corePoolSize`, the executor creates a new thread to process the task.
2. Once enough core threads exist, a new task is placed in the queue if there is space.
3. Only when the queue is full does the executor create additional threads beyond the core size, up to `maxPoolSize`.
4. If the queue is full and the thread count has reached max, the task is rejected according to the rejection policy.

For example, core=8, max=16, and queueCapacity=200:

- Up to the first 8 tasks can run concurrently on core threads.
- Subsequent tasks are queued, up to 200 tasks.
- When the queue is full, the pool can grow additional threads from 8 up to 16.
- When both the pool and the queue reach their limits, new tasks cannot be accepted under the current configuration.

An easily misunderstood point: if the queue is unbounded (the default in `TaskExecutorRegistration` is `Integer.MAX_VALUE`), new tasks continue to be queued once core threads are busy. The queue is virtually never full, so `maxPoolSize` has no effect in scaling the pool. An unbounded queue can also hold too many tasks and cause out-of-memory errors when the arrival rate exceeds the processing rate.

A bounded queue limits the amount of pending work and allows the pool to expand up to max size. However, a queue that is too small can cause tasks to be rejected during short load bursts. Throughput and wait time must be measured to choose a reasonable capacity.

## 5. Sizing clientInboundChannel

`clientInboundChannel` processes messages sent in by clients. For example:

- SUBSCRIBE to `/topic/**` or `/user/**`.
- SEND to `/app/**` routed to `MessageMapping`.
- Interceptors checking authentication, authorization, headers, and data.
- Handlers processing payloads and calling business services.

How to size the pool depends on the type of work:

### CPU-bound Work

If handlers mainly parse data, validate rules, compute, or transform payloads, the thread count should be close to the number of available CPUs. Increasing threads too much does not make the CPU perform more calculations; it can increase context switching.

### I/O-bound Work

If handlers must wait on a database, HTTP service, or other system, more threads than CPUs may be needed to utilize the waiting time. However, this must be cross-checked against connection pools and limits of dependent systems. For example, opening 100 inbound threads while the database only allows 10 connections can create a queue waiting on the database instead of increasing throughput.

For long-running tasks such as generating reports, calling slow services, or running workflows, consider offloading that work to a separate executor or business queue. Do not let one handler hold an inbound channel thread for too long if other messages need to be processed quickly.

Controller handlers are typically invoked concurrently on multiple threads. Singleton controllers should not hold shared mutable state without proper synchronization. Use thread-safe services, clear transaction boundaries, and do not assume all messages from one user will automatically run sequentially.

## 6. Sizing clientOutboundChannel

`clientOutboundChannel` processes messages sent back to WebSocket clients, including messages from the broker and some messages sent directly from the application.

Outbound load is affected by:

- Number of connected clients.
- Number of destinations each client subscribes to.
- Broker publish frequency.
- Payload size.
- Bandwidth and JavaScript processing speed of each client.
- Number of clients on mobile networks or high-latency connections.

If clients are on fast networks and consume messages promptly, the pool can be close to the CPU count. If there are many slow or low-bandwidth clients, outbound tasks may wait longer; a larger pool can help other sessions continue to be served.

However, Spring uses only one thread at a time to write messages to a given client session. Other messages for that session are buffered. Therefore, increasing the outbound pool does not cause a slow WebSocket to receive multiple messages concurrently. You need to combine send time limits, buffer limits, publish rate control, and a policy for disconnecting clients that cannot keep up.

## 7. Send Limits for Slow Clients

Configuring the outbound executor does not replace transport configuration. `configureWebSocketTransport` provides two useful limits:

- `setSendTimeLimit(milliseconds)` limits the time spent sending a message to a client.
- `setSendBufferSizeLimit(bytes)` limits the amount of data buffered when sending to a client.

Example:

~~~java
@Override
public void configureWebSocketTransport(WebSocketTransportRegistration registration) {
    registration
            .setSendTimeLimit(15 * 1000)
            .setSendBufferSizeLimit(512 * 1024);
}
~~~

These are illustrative values. When a client cannot read fast enough, outbound data can accumulate. When the send time or buffer limit is exceeded, Spring can close the session to protect server resources.

You should not increase the buffer indefinitely to mask slow clients. Doing so can hold large amounts of messages in memory, causing stale data to keep being sent after it is no longer useful. For recoverable data, it is sometimes better to disconnect the slow session and let the client reconnect and synchronize a snapshot.

## 8. Preserving Message Order

Because both inbound and outbound use thread pools, processing order is not guaranteed by default to match the original receive or publish order.

Spring provides two separate options:

### Receive Order from Client

`StompEndpointRegistry.setPreserveReceiveOrder(true)` instructs Spring to pass messages from the same session into `clientInboundChannel` one by one in the order received.

This is useful when a client sends dependent commands, such as updating state and then sending a follow-up operation based on the new state. This option was added in Spring Framework 6.1.

### Send Order to Client

`MessageBrokerRegistry.setPreservePublishOrder(true)` instructs Spring to send messages to the same client session through `clientOutboundChannel` one by one in publish order.

This option is useful when a client needs to receive a sequence of events in the exact order. It adds performance overhead, so enable it only when the business logic requires it.

Both options only guarantee order within the scope of the same client session. They do not establish global ordering across multiple users, multiple sessions, multiple brokers, or multiple producers. If business ordering matters, you should still include a `sequence` or `version` in the payload and verify it on the consumer side.

## 9. Thread Safety and Processing Boundaries

Because the executor can run multiple messages in parallel:

- Controllers are singletons by default; do not store per-client state in unprotected mutable fields.
- Collections shared among multiple handlers must use thread-safe structures or appropriate locking mechanisms.
- Do not assume two messages from the same session always execute sequentially if preserve receive order is not enabled.
- Do not carry a transaction or thread-local context across another executor boundary as if still on the same thread.
- Do not perform long blocking work inside a handler if it can be offloaded to a dedicated service or worker.
- Do not share a single small executor for both inbound and outbound if the two flows have different load characteristics and doing so lets one side exhaust all threads.

If you need to limit concurrent operations per user or per resource, apply semaphores, rate limiters, or throttling mechanisms at the business layer. A thread pool only controls the number of tasks running and waiting in the channel; it has no built-in awareness of an account's quota.

## 10. Monitoring Executors and Channels

When using `EnableWebSocketMessageBroker`, Spring provides the `WebSocketMessageBrokerStats` bean to aggregate infrastructure metrics. According to the Spring Framework 6.2 documentation, this bean logs statistics at INFO level every 30 minutes by default and can be exported via JMX.

Metrics to observe:

| Metric | Sign to Watch |
|---|---|
| Inbound pool active threads | A pool frequently busy with all threads may lack processing capacity. |
| Inbound queue size | A continuously growing queue indicates handlers or dependencies are slower than the incoming message rate. |
| Outbound pool active threads | Prolonged pool busyness may be caused by a large volume of messages to send. |
| Outbound queue size | A growing queue may indicate slow-consuming clients or excessively high broadcast volume. |
| WebSocket sessions | Compare the current session count with the expected number of clients. |
| Send limit exceeded | Clients are exceeding the send timeout or send buffer limit. |
| Transport errors | WebSocket or HTTP transport read/write errors are occurring. |
| STOMP frames | Compare CONNECT, CONNECTED, and DISCONNECT to detect abnormal session closures. |

Do not look at just a single snapshot of metrics. Track trends in queue size, active count, task completion, latency, and rejections during both normal load and peak periods. If the queue only grows without shrinking, increasing max pool size may not resolve the bottleneck; check handlers, the database, the broker, or clients.

## 11. Practical Tuning Process

A repeatable process:

1. **Measure baseline**: record client count, messages/second, payload size, CPU, heap, latency, and queue size.
2. **Separate inbound and outbound**: identify which channel has the backlog.
3. **Find the bottleneck**: inbound is usually related to handlers or I/O; outbound is usually related to slow clients, broker fan-out, or large payloads.
4. **Choose core size**: based on CPU count and I/O wait ratio.
5. **Choose max size and queue capacity**: bounded queue to control memory; max size to absorb short load bursts.
6. **Check dependency limits**: database connection pool, HTTP connection pool, broker connections, and CPU.
7. **Load test**: gradually increase client count and message rate, monitoring p95/p99 latency, queues, memory, and errors.
8. **Adjust one variable at a time**: change core, max, queue, or send limits individually to see the impact.
9. **Test overload**: verify the system rejects or disconnects in a controlled manner rather than letting queues grow indefinitely.
10. **Document the configuration**: record tested parameters, workload, infrastructure limits, and the rationale for the final values.

There is no single optimal executor configuration for every application. Pools should be re-evaluated when container CPU quotas, client counts, brokers, payloads, or handler processing times change.

## 12. Common Mistakes

- **Increasing maxPoolSize while keeping an unbounded queue:** the queue accepts tasks before the pool scales; max may never be used. Set a bounded queue capacity if scaling beyond core is needed.
- **Using the same pool for inbound and outbound:** a high-load flow can starve the other flow. Configure them separately to observe and tune independently.
- **Setting core/max too high:** threads contend for CPU, heap, and connection pools. Start from measured workload and increase incrementally.
- **Queue too large:** latency increases and stale tasks may still be processed after they have lost value. Set limits based on acceptable wait time and memory capacity.
- **Only increasing outbound threads when clients are slow:** a single session is still written sequentially; check sendTimeLimit, sendBufferSizeLimit, and client speed.
- **Ignoring message order:** parallel processing can reorder messages. Enable preserveReceiveOrder or preservePublishOrder if needed and measure overhead.
- **Using mutable state in singleton controllers:** multiple messages running concurrently can cause race conditions. Use state stores or thread-safe data.
- **Evaluating the system by CPU alone:** queues can grow due to a slow database, slow broker, or slow-reading clients even when CPU is not high.

## 13. Pre-Production Checklist

- [ ] Clearly understand inbound, outbound, and brokerChannel flows.
- [ ] Configured separate executors for clientInboundChannel and clientOutboundChannel.
- [ ] Set corePoolSize, maxPoolSize, and queueCapacity based on load testing.
- [ ] Verified that an unbounded queue does not unexpectedly disable maxPoolSize.
- [ ] Checked database and HTTP connection pools against the inbound thread count.
- [ ] Configured sendTimeLimit and sendBufferSizeLimit for slow clients.
- [ ] Enabled preserveReceiveOrder/preservePublishOrder if business requirements need ordering.
- [ ] Controllers and handlers are thread-safe under concurrent execution.
- [ ] Monitored WebSocketMessageBrokerStats and queue backlog.
- [ ] Load tested normal load, bursts, and overload.
- [ ] Defined behavior when the queue is full or tasks are rejected.

## 14. Key Takeaways

`clientInboundChannel` processes messages going from the client into Spring; `clientOutboundChannel` processes messages going from the broker/application back to the client. Configure the two executors independently using `configureClientInboundChannel` and `configureClientOutboundChannel`. When tuning, understand the interaction between corePoolSize, maxPoolSize, and queueCapacity: an unbounded queue can prevent maxPoolSize from being used. Inbound must match controller workload and I/O dependencies; outbound must account for slow clients along with sendTimeLimit/sendBufferSizeLimit. Preserve ordering with preserveReceiveOrder or preservePublishOrder when business logic requires it, then validate with metrics and load tests.

## References

- [Spring Framework 6.2 — Performance](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/configuration-performance.html)
- [Spring Framework 6.2 — Monitoring](https://docs.spring.io/spring/reference/6.2/web/websocket/stomp/stats.html)
- [Spring Framework 6.2 — Order of Messages](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/ordered-messages.html)
- [TaskExecutorRegistration API 6.2](https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/messaging/simp/config/TaskExecutorRegistration.html)
- [WebSocketMessageBrokerConfigurer API 6.2](https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/web/socket/config/annotation/WebSocketMessageBrokerConfigurer.html)