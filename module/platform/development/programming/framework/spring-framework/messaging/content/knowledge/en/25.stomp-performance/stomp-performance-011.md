# WebSocketMessageBrokerStats and Connection Load Diagnostics in Spring STOMP

## Objective

When an application uses Spring WebSocket + STOMP, an increase in connections is not necessarily a failure. A system can sustain thousands of sessions stably if message rates, payload sizes, fan-out, network, and processing resources stay within limits. Incidents usually occur when one of the layers becomes bottlenecked: WebSocket transport, STOMP processing, inbound/outbound channel executors, the SockJS heartbeat scheduler, or the broker relay.

Spring provides the **WebSocketMessageBrokerStats** bean to gather counters and statistics from the messaging infrastructure. This bean helps answer questions such as:

- How many WebSocket/SockJS sessions are currently active?
- How many sessions closed abnormally due to sending no frames, slow sends, or transport errors?
- Are CONNECT, CONNECTED, and DISCONNECT counts balanced?
- Is the inbound channel queuing messages, or is the outbound channel congested by slow clients?
- When using a broker relay, does the number of TCP connections to the broker match the number of client sessions?
- Does the SockJS task scheduler have enough capacity to send heartbeats?

These statistics are a starting point for narrowing down the issue. They do not replace metrics from the JVM, WebSocket container, reverse proxy, database, or external broker.

## 1. How Is WebSocketMessageBrokerStats Created?

When messaging is configured with **@EnableWebSocketMessageBroker** or XML **websocket:message-broker**, Spring automatically declares a bean named **webSocketMessageBrokerStats** of type **WebSocketMessageBrokerStats**. The bean aggregates information from the main components of STOMP over WebSocket.

By default, Spring logs aggregated statistics at **INFO level every 30 minutes**. The bean can be exported via JMX using **MBeanExporter** to inspect at runtime, for example with JConsole or an equivalent JMX tool. The logging interval can be adjusted via **setLoggingPeriod(long)**; the unit is milliseconds, and a value less than or equal to 0 cancels scheduled logging.

Since Spring Framework 6.2, the bean provides additional accessors returning structured statistics objects:

- **getWebSocketSessionStats()**: WebSocket and SockJS session metrics.
- **getStompSubProtocolStats()**: counters for CONNECT, CONNECTED, and DISCONNECT frames processed at the STOMP layer.
- **getStompBrokerRelayStats()**: counters for the broker relay if a relay is configured.

These accessors may return **null** if the corresponding component is not configured or does not exist. For example, an application using the simple broker will not have broker relay statistics. On Spring versions older than 6.2, rely on the aggregated stats string and the APIs available in the Javadoc for the exact version running.

One way to take a structured snapshot:

~~~java
@Component
public class StompStatsSnapshot {

    private static final Logger log =
            LoggerFactory.getLogger(StompStatsSnapshot.class);

    private final WebSocketMessageBrokerStats stats;

    public StompStatsSnapshot(WebSocketMessageBrokerStats stats) {
        this.stats = stats;
    }

    public void logNow() {
        var sessions = stats.getWebSocketSessionStats();
        if (sessions != null) {
            log.info(
                    "WebSocket sessions: ws={}, sockjsStreaming={}, " +
                    "sockjsPolling={}, total={}, noFirstMessage={}, " +
                    "sendLimitExceeded={}, transportErrors={}",
                    sessions.getWebSocketSessions(),
                    sessions.getHttpStreamingSessions(),
                    sessions.getHttpPollingSessions(),
                    sessions.getTotalSessions(),
                    sessions.getNoMessagesReceivedSessions(),
                    sessions.getLimitExceededSessions(),
                    sessions.getTransportErrorSessions());
        }

        var stomp = stats.getStompSubProtocolStats();
        if (stomp != null) {
            log.info(
                    "STOMP frames: CONNECT={}, CONNECTED={}, DISCONNECT={}",
                    stomp.getTotalConnect(),
                    stomp.getTotalConnected(),
                    stomp.getTotalDisconnect());
        }

        var relay = stats.getStompBrokerRelayStats();
        if (relay != null) {
            log.info(
                    "Broker relay: handlers={}, CONNECT={}, CONNECTED={}, DISCONNECT={}",
                    relay.getTotalHandlers(),
                    relay.getTotalConnect(),
                    relay.getTotalConnected(),
                    relay.getTotalDisconnect());
        }

        log.info(
                "Inbound executor={}, outbound executor={}, SockJS scheduler={}",
                stats.getClientInboundExecutorStatsInfo(),
                stats.getClientOutboundExecutorStatsInfo(),
                stats.getSockJsTaskSchedulerStatsInfo());
    }
}
~~~

This is an illustrative component for reading snapshots as operationally needed; the application needs the corresponding Spring/SLF4J imports. The **WebSocketMessageBrokerStats** bean is already provided by Spring when the STOMP message broker is enabled, so do not create a second bean of the same type. In most systems, default logging and JMX are sufficient for inspection; add a custom snapshot only when integration with dashboards or dedicated diagnostic workflows is needed.

## 2. Understanding Each Statistics Group

### Client WebSocket Sessions

| Field | Meaning | How to Use |
|---|---|---|
| **Current** | Current session count, broken down by WebSocket, SockJS HTTP streaming, and HTTP polling | Measure concurrent connections per instance |
| **Total** | Total sessions established since process start | Track connection creation rate and churn |
| **Connect Failures / No Messages Received** | Sessions established that received no sub-protocol message within 60 seconds | Investigate clients not sending STOMP CONNECT, proxies, or network |
| **Send Limit Exceeded** | Sessions closed due to exceeding send time limit or buffer limit | Investigate slow clients, weak networks, large fan-out |
| **Transport Errors** | Sessions closed after WebSocket or HTTP transport read/write errors | Investigate network, proxy, container, and client disconnects |

**Current** is a concurrent gauge; **Total** is a cumulative counter. Do not compare these two numbers as if they share the same time unit. For example, stable Current with rapidly rising Total may indicate clients constantly reconnecting, load balancers closing connections, flaky mobile networks, or the application creating many short-lived sessions.

Connect Failures does not necessarily mean the HTTP handshake failed. According to Spring, these are sessions that were established but did not receive a first message within 60 seconds. With STOMP, the common case is that WebSocket opened but the client did not send CONNECT, or CONNECT never reached the application due to proxy, network, or client bugs.

Send Limit Exceeded is commonly related to slow clients. Spring uses only one thread at a time to send to a client; subsequent messages are buffered while a send is in progress. When sending exceeds the time or buffer limit, Spring can close the session to prevent a slow client from occupying too many resources.

Transport Errors include errors when reading or writing on a WebSocket connection or SockJS HTTP request/response. This is a sign to correlate logs from the WebSocket server, reverse proxy, ingress, TLS, and client.

### STOMP Frames

This group counts total frames:

- **CONNECT**: client requests to open a STOMP session.
- **CONNECTED**: server/broker replies that STOMP connection succeeded.
- **DISCONNECT**: session termination frame processed.

These are connection lifecycle counters, not total SEND, MESSAGE, or SUBSCRIBE counters. Do not use CONNECT/CONNECTED/DISCONNECT to infer message throughput.

DISCONNECT is normally lower than CONNECT when sessions close abnormally or clients close the transport without sending a DISCONNECT frame. If CONNECT rises while CONNECTED does not rise correspondingly, check authentication, CONNECT frame errors, unresponsive brokers, or relay connection failures.

### STOMP Broker Relay

This group is only meaningful when Spring uses **enableStompBrokerRelay(...)** to forward to an external broker.

| Field | Meaning | Sign to Check |
|---|---|---|
| **TCP Connections** | TCP connections to the broker on behalf of WebSocket/STOMP clients | Compare with current client sessions and the system connection |
| **STOMP Frames** | CONNECT, CONNECTED, and DISCONNECT forwarded to or received from the broker | Check broker connectivity, heartbeats, and protocol errors |
| **Total Handlers** | Number of connection handlers the relay is tracking | Cross-check with connected clients and broker state |

Normally, the broker relay's TCP connection count is approximately the number of client WebSocket sessions plus **one shared system connection** for messages emitted from the application. This is a quick sanity-check rule of thumb, not an invariant at every instant: counts can diverge while connections are opening/closing or when the system experiences errors.

Spring sends DISCONNECT to the broker when a WebSocket session closes, even if the client closed abnormally. Therefore, if the relay's DISCONNECT counter is significantly lower than established connections, the broker may be actively closing TCP connections. Check broker logs, missed heartbeats, invalid frames, connection limits, or authentication errors.

With the built-in simple broker, there is no TCP relay to an external broker; the relay group may be null or absent.

### Client Inbound Channel

**clientInboundChannel** receives STOMP messages from WebSocket clients and passes them through interceptors, security, controllers, or broker handlers depending on destination.

Executor stats reveal:

- Number of existing and active threads.
- Number of tasks waiting in the queue.
- Number of completed tasks.
- Pool size and processing state.

Exact names and formatting depend on the actual executor, as Spring provides the thread pool's info string. Key things to watch are whether the queue grows continuously, whether active threads frequently hit the cap, and whether completed tasks keep advancing or stall.

A growing inbound queue indicates the application is processing messages slower than they arrive. Common causes:

- Controllers make synchronous database or REST API calls and wait a long time.
- Services hold locks or perform heavy CPU work.
- Message converters or validation consume heavy CPU.
- A client sends messages at an excessively high rate.
- The inbound thread pool is small relative to an I/O-bound workload.
- Downstream dependencies such as the database connection pool are exhausted, blocking inbound threads.

If processing is mostly CPU-bound, thread count should be close to CPU cores. If processing is mostly I/O-bound waiting on databases or external systems, more threads may be needed. However, increasing threads only helps if downstream dependencies still have capacity; if the database is already bottlenecked, adding threads can increase queued waiting requests.

### Client Outbound Channel

**clientOutboundChannel** delivers messages from the broker or application back to WebSocket clients. It typically bears heavy load when a message is broadcast to many subscribers.

A growing outbound queue can indicate:

- Clients on slow networks or low bandwidth.
- Some clients not reading frames fast enough.
- Payloads too large or send frequency too high.
- A topic with too many subscribers.
- Fan-out creating many concurrent send tasks.
- Outbound thread pool or buffer limits not properly sized.

Unlike inbound, outbound load depends heavily on the network and client consumption speed. Increasing threads can help serve more slow clients, but cannot eliminate bandwidth limits or device receive capacity. Check Send Limit Exceeded, payload size, fan-out, and network throughput together.

### SockJS Task Scheduler

SockJS uses a task scheduler to send heartbeats for sessions when needed. Scheduler stats help detect an overloaded heartbeat thread pool or many queued tasks.

If STOMP heartbeats have been negotiated, SockJS's own heartbeat is disabled. Therefore, when reading scheduler stats, know whether the application uses raw WebSocket, SockJS fallback, or STOMP heartbeats. Do not conclude the scheduler is broken solely from low task counts or absent SockJS heartbeats.

## 3. Distinguishing Spring Stats from System Metrics

**WebSocketMessageBrokerStats** aggregates metrics of the Spring messaging infrastructure. It does not provide the complete operational picture.

Also monitor:

| Layer | Metrics to Inspect | Why Important |
|---|---|---|
| JVM | CPU, heap/non-heap, GC pauses, thread count, direct buffers | Distinguish CPU, memory, and thread bottlenecks |
| WebSocket container | Active connections, write errors, message-size errors, buffer usage | Identify limits of Tomcat/Jetty/Undertow or the server in use |
| Reverse proxy / ingress | Active connections, upstream timeouts, 4xx/5xx, resets, idle timeouts | Detect proxies closing sockets or failing to forward heartbeats |
| Inbound/outbound executors | Active threads, queue depth, completed tasks, rejected tasks | Identify which channel is congested |
| Database and HTTP clients | Pool active/idle, pending acquire, query latency, timeouts | Find why inbound threads are blocked |
| External broker | Connection count, queue depth, unacked messages, publish/delivery rate, memory/disk alarms | Distinguish app relay bottlenecks from broker bottlenecks |
| Network | Bytes/s, packet loss, retransmissions, RTT, open file descriptors | Identify data transfer limits and connection resource limits |

Do not assume every metric in **WebSocketMessageBrokerStats** automatically becomes a Micrometer meter. This bean has aggregated logging and JMX export. If time-series dashboards are needed, add appropriate Micrometer instrumentation or scrape JMX with your monitoring system.

Spring Boot Actuator has the **/actuator/metrics** endpoint to inspect currently registered meters and their current values. This endpoint is useful for manual diagnostics; it should not be used as a metrics backend or scraped periodically in production. For Prometheus, use the corresponding Prometheus registry and endpoint; secure management endpoints and expose only necessary endpoints.

When creating custom meters from stats, clearly distinguish:
- **Gauge** for current session counts, active threads, or queue depth.
- **Counter/FunctionCounter** for total sessions created, total errors, and monotonically increasing counters.
- **Timer/DistributionSummary** for latency and message sizes if the application instruments processing paths itself.

Do not attach session IDs, user IDs, or destinations with unique identifiers to metric tags. Excessively high cardinality can exhaust the metrics system's RAM, CPU, and storage. Use bounded-cardinality tags such as transport, channel, or normalized destination group.

## 4. Connection Load Diagnostic Process

A repeatable process:

1. **Define the scope**: does the issue occur on one node or the whole cluster; only WebSocket or also SockJS; only one topic or all destinations; when did it start.
2. **Capture baseline**: record Current, Total, abnormal close counters, STOMP frames, relay connections, and inbound/outbound executors under normal load.
3. **Compare over time**: take multiple snapshots within the same process uptime. Observe deltas of Total, Connect Failures, Send Limit Exceeded, and Transport Errors; do not look only at absolute numbers.
4. **Locate the congested channel**: if the inbound queue grows, check controllers, interceptors, databases, and REST dependencies; if the outbound queue grows, check slow clients, payloads, and fan-out.
5. **Cross-check the broker**: if using a relay, compare Spring's TCP connections and STOMP frames with broker logs/management metrics.
6. **Cross-check infrastructure**: check CPU, GC, memory, file descriptors, network, proxy timeouts, and connection limits.
7. **Controlled testing**: increase client counts and message rates step by step, keeping payloads, subscriptions, and heartbeats close to production.
8. **Verify after tuning**: re-run the same workload, comparing queue depth, error rates, latency, memory, and stable session count.

Counters in stats are typically cumulative since process startup. After a restart, values may reset to 0. Therefore, when comparing over time, record process uptime or mark deploy/restart timestamps so a counter reset is not misinterpreted as a resolved issue.

### Examples of Identifying Causes from Symptoms

| Symptom | Accompanying Signs | First Investigation Direction |
|---|---|---|
| Current sessions lower than expected | Total rising fast, Connect Failures rising | Client reconnects, proxy timeouts, STOMP CONNECT not reaching server |
| CONNECT rising but CONNECTED low | Low relay connections or errors in broker logs | Authentication, broker availability, heartbeats, frame errors |
| Send Limit Exceeded rising | Outbound queue growing, slow client networks | Slow consumers, large payloads, fan-out, send timeout/buffer |
| Transport Errors rising | Proxy resets or container write/read errors | TLS, reverse proxy, network, WebSocket container |
| Inbound queue growing continuously | High active threads, DB/HTTP pools waiting | Blocking controllers, database latency, external APIs, inbound pool |
| Outbound queue growing while inbound is normal | Many subscribers, slow clients, send errors | Outbound pool, bandwidth, reduce message rate or payload |
| Relay DISCONNECT much lower than CONNECT | Broker actively closing sockets | Heartbeats, broker logs, connection limits, invalid frames |
| SockJS scheduler queue growing | Delayed heartbeats or many polling/streaming sessions | TaskScheduler capacity, transport fallback, heartbeat config |
| High CPU without obvious queue growth | Message converters, serialization, fan-out, or GC | CPU profile, payload size, subscriber count per topic |

These are diagnostic hypotheses, not automatic conclusions. A single symptom can have multiple causes; always correlate timestamps, logs, and metrics across relevant layers.

## 5. Configuring Inbound and Outbound Executors

Spring configures executors for **clientInboundChannel** and **clientOutboundChannel**. By default, both have a thread count equal to roughly twice the number of available processors. This is a starting point, not the optimal size for every workload.

Configuration example:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfiguration implements WebSocketMessageBrokerConfigurer {

    @Override
    public void configureClientInboundChannel(ChannelRegistration registration) {
        registration.taskExecutor()
                .corePoolSize(8)
                .maxPoolSize(16)
                .queueCapacity(500);
    }

    @Override
    public void configureClientOutboundChannel(ChannelRegistration registration) {
        registration.taskExecutor()
                .corePoolSize(8)
                .maxPoolSize(16)
                .queueCapacity(500);
    }
}
~~~

The numbers are only examples to illustrate configuration, not recommendations for every server. Benchmark on actual hardware, message sizes, subscriber counts, and I/O ratios.

A common misconception of **ThreadPoolExecutor**: if the queue has an unbounded capacity, tasks are typically placed into the queue once core threads are busy; the pool does not scale up to maxPoolSize. Thus, simply setting corePoolSize=8 and maxPoolSize=16 with an unbounded queue does not mean the pool will automatically expand to 16 threads. Queue capacity, core size, and max size must be designed together.

Do not enlarge the inbound pool simply because queues occasionally appear. If the cause is an exhausted database connection pool, adding threads can make even more requests wait on the database. Check dependency latency and capacity before enlarging the pool.

The outbound pool should not grow unboundedly either. If clients are on slow networks, adding threads only allows more concurrent sends; send buffers and timeout limits are still needed to prevent one client from holding too much memory.

## 6. Send and Buffer Limits for Slow Clients

For a single client, Spring uses only one thread at a time to send. Additional messages are buffered while a send is in progress. Two important settings:

- **sendTimeLimit**: maximum time allowed for sending.
- **sendBufferSizeLimit**: maximum amount buffered when sending to a client.

Example:

~~~java
@Override
public void configureWebSocketTransport(WebSocketTransportRegistration registration) {
    registration
            .setSendTimeLimit(15 * 1000)
            .setSendBufferSizeLimit(512 * 1024);
}
~~~

The example above sets a 15-second send timeout and a 512 KiB buffer. Adjust based on message size, broadcast frequency, and network characteristics. Too low a timeout can mistakenly disconnect valid clients on mobile networks; too large a buffer can spike memory usage when many clients are slow simultaneously.

When Send Limit Exceeded increases, do not just raise the timeout and buffer. First determine:
- How large is a single message?
- How many subscribers does a topic have?
- Does the publish rate exceed the client's average receive rate?
- Are client callbacks blocking synchronously for too long?
- Can updates be coalesced, sampled, throttled, or sent as deltas instead of full snapshots?

For real-time data, dropping stale updates and keeping only the latest state is sometimes better than buffering a long queue of outdated messages. If business logic requires every event, use an appropriate storage/queue mechanism rather than treating the WebSocket outbound buffer as a durable queue.

## 7. Message Size Limits and Reassembly Overhead

WebSocket containers usually have their own message size limits. STOMP clients may split a large message into multiple smaller WebSocket messages; Spring must buffer and reassemble them before processing the complete STOMP frame.

STOMP message limits can be configured in Spring:

~~~java
@Override
public void configureWebSocketTransport(WebSocketTransportRegistration registration) {
    registration.setMessageSizeLimit(128 * 1024);
}
~~~

The limit above is 128 KiB in the example. Choose a value sufficient for valid payloads without exceeding the memory budget. A large message can be split into multiple WebSocket frames, requiring buffering/reassembly and increasing both memory usage and latency. If many clients send large messages simultaneously, total memory usage can rise significantly.

When encountering message size errors:
- Check limits in Spring, the WebSocket container, reverse proxies, and client libraries.
- Measure size after serialization, not just object size before JSON conversion.
- Prefer pagination, small payloads, or sending references/IDs for clients to fetch large data over HTTP when appropriate.
- Do not raise all limits at once without load testing and memory checks.

## 8. Message Ordering and Performance Cost

Both inbound and outbound channels are executor-backed. Multiple messages of the same session can be processed on different threads, so processing or delivery order to the client can differ from the original order.

If business logic requires preserving order, Spring provides these options:

~~~java
@Override
public void registerStompEndpoints(StompEndpointRegistry registry) {
    registry.setPreserveReceiveOrder(true);
}

@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setPreservePublishOrder(true);
}
~~~

- **setPreserveReceiveOrder(true)** preserves processing order of messages received from the same client session.
- **setPreservePublishOrder(true)** preserves publish order of messages sent to the same client session.

These two settings have a performance cost because they reduce parallel processing within the scope of a session. Enable them only when business logic clearly needs ordering; do not use them as a general remedy for growing queues.

Even when order is preserved within one session, that does not automatically guarantee global ordering across multiple users, multiple nodes, or independent producers. If business logic requires ordering per entity, use partition keys/sequence numbers or appropriate ordering mechanisms at the broker and application layers.

## 9. SockJS, Heartbeats, and Connection Load

SockJS can use WebSocket or fall back to HTTP streaming/polling. Consequently, Current Sessions are broken down by transport. When the ratio of HTTP streaming/polling rises abnormally, check why WebSocket is not being used: proxies not supporting Upgrade, TLS/network policies, client browsers, or SockJS configuration.

The SockJS task scheduler sends heartbeats when needed. If STOMP heartbeats are negotiated, SockJS heartbeats are disabled. Configure the scheduler with enough capacity for fallback sessions and heartbeat frequency, but do not scale threads solely from total sessions without checking actual transports.

Heartbeats serve two roles:
- Detecting dead or unresponsive connections.
- Keeping connections from being treated as idle by proxies/load balancers.

Too frequent heartbeats increase task scheduling and network chatter; too sparse heartbeats delay disconnect detection or allow proxies to close sockets first. Choose intervals based on reverse proxy, load balancer, and broker timeouts, then test on real networks.

When using Spring **WebSocketStompClient** as a load generator, each client can create heartbeat scheduling tasks. When simulating thousands of clients from one machine, the load generator's own heartbeat scheduler can become the bottleneck. Spring suggests considering disabling heartbeats in load tests when the goal is to measure connection counts from a single machine. This applies only to proper load test design; do not disable heartbeats in production to mask connection issues.

## 10. Broker Relay and Multi-Instance Scaling

Spring's built-in simple broker holds subscriptions in memory and does not support multi-instance deployment as a distributed broker. If multiple instances run independently, each instance may only know subscriptions of clients connected to itself.

When using a full-featured STOMP broker via **enableStompBrokerRelay(...)**, each application instance connects to the broker; messages broadcast from one instance can be forwarded by the broker to clients connected through another instance.

When diagnosing a cluster:
- Record Current Sessions and executor stats per instance.
- Aggregate cluster metrics, but do not mistakenly sum cumulative counters across restarts.
- Check broker relay TCP connections on each node.
- Check broker connection limits, queue depth, unacked messages, memory, and disk.
- Verify the load balancer keeps each WebSocket session on the same upstream throughout the connection's lifetime.
- Check the user registry and user destination broadcast mechanism if the application sends per-user messages across nodes.

A broker relay does not automatically make everything infinitely scalable. The external broker still has connection, throughput, queue, memory, and network limits. Test total sessions across the cluster together with message rates and fan-out.

## 11. Meaningful Load Testing

A test that only opens many WebSocket connections without sending STOMP CONNECT or subscribing does not fully reflect the load of a STOMP application. Clearly define what is being measured:

- Capacity to hold concurrent connections.
- STOMP CONNECT/CONNECTED rate.
- Subscriptions per session.
- SEND messages/second.
- Fan-out to subscribers.
- Payload size and serialization.
- Heartbeat rate.
- Reconnect capability after network or broker disruptions.

A realistic test scenario should:
1. Ramp up client counts in steps.
2. Have each client complete handshake and STOMP CONNECT.
3. Subscribe to the same number of destinations as production.
4. Send messages with representative payloads and frequencies.
5. Measure end-to-end latency, inbound/outbound queues, send limits, transport errors, and resource usage.
6. Hold steady load long enough to uncover memory leaks, steadily growing queues, and reconnect churn.
7. Test slow clients, high network latency, and broker restarts separately.
8. Record server, JVM, container, proxy, broker, and load generator configurations so results are reproducible.

When using WebSocketStompClient as a load generator, provide an appropriate TaskScheduler for STOMP heartbeats if you want to measure heartbeat overhead as well. If disabling heartbeats to focus on connection counts, clearly document this condition in test results; do not compare directly against production with heartbeats enabled.

Do not look only at maximum session count. A system holding 50,000 idle sockets may not handle the same socket count when each client receives 10 messages/second and each message fans out to hundreds of subscribers.

## 12. Quick Diagnostic Checklist

### When connection counts drop suddenly
- Check Current by transport and per node.
- Check deltas for Connect Failures, Send Limit Exceeded, and Transport Errors.
- Check proxy/ingress timeouts, network resets, TLS, and broker logs.
- Compare CONNECT vs. CONNECTED to see whether STOMP connections are completing.

### When inbound messages are slow
- Check inbound executor active threads and queue.
- Measure controller/service duration and database/HTTP dependencies.
- Check message rate, payload size, converters, and interceptors.
- Check whether the database pool has pending acquires or timeouts.

### When clients receive messages slowly
- Check outbound executor queue and Send Limit Exceeded.
- Measure fan-out, payload size, network throughput, and client callback speed.
- Reduce message rate or payload if business logic allows.
- Tune send timeout/buffer after understanding the memory budget.

### When the broker relay has errors
- Compare relay TCP connections against current client sessions.
- Compare CONNECT, CONNECTED, and DISCONNECT.
- Check broker connection limits, heartbeats, authentication, and broker availability.
- Read broker logs alongside Spring logs using aligned timestamps.

### When SockJS fallback increases
- Check HTTP streaming/polling session counts.
- Check WebSocket Upgrade through proxies/load balancers.
- Check the heartbeat scheduler and HTTP transport timeouts.
- Verify whether clients genuinely need fallback or are being unintentionally downgraded.

## 13. Limitations and Safe Interpretation

**WebSocketMessageBrokerStats is not a full APM.** It does not show how many messages each individual user sends, which destination has the largest fan-out, p50/p95/p99 latency per controller, or which payload drives memory growth. To get that data, instrumentation at the application and broker layers is needed.

Do not conclude an incident from a single snapshot. A brief queue at one instant may be a normal burst; a counter rising since process start does not tell whether errors are happening fast or slow without a time delta. Always compare over the same time window, same process uptime, and same workload.

When changing thread pools, queue capacity, send timeout, buffers, or message size limits, change one targeted group at a time and re-run the same load scenario. If everything is changed at once, it becomes difficult to know which setting actually improved performance or caused side effects.

## References

- Spring Framework — Monitoring: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/stats.html
- Spring Framework — WebSocketMessageBrokerStats Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/socket/config/WebSocketMessageBrokerStats.html
- Spring Framework — SubProtocolWebSocketHandler.Stats Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/socket/messaging/SubProtocolWebSocketHandler.Stats.html
- Spring Framework — StompSubProtocolHandler.Stats Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/socket/messaging/StompSubProtocolHandler.Stats.html
- Spring Framework — StompBrokerRelayMessageHandler.Stats Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/stomp/StompBrokerRelayMessageHandler.Stats.html
- Spring Framework — Performance: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/configuration-performance.html
- Spring Framework — Flow of Messages: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html
- Spring Framework — Order of Messages: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/ordered-messages.html
- Spring Framework — STOMP Client: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/client.html
- Spring Boot — Actuator Metrics Endpoint: https://docs.spring.io/spring-boot/api/rest/actuator/metrics.html
