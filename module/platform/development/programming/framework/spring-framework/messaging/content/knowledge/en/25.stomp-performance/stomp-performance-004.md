# setPreserveReceiveOrder and Receive Ordering by Supported Version

In Spring WebSocket/STOMP applications, messages sent by clients to the server pass through `clientInboundChannel`. This channel is typically processed by a thread pool, so messages received in order on the same connection can still be processed concurrently and finish in a different order. Starting from Spring Framework 6.1, you can enable `StompEndpointRegistry.setPreserveReceiveOrder(true)` so that Spring dispatches messages from the same STOMP session into `clientInboundChannel` one by one in the order received.

This is a setting for the client → server direction. It differs from `MessageBrokerRegistry.setPreservePublishOrder(true)`, which controls the order in which the server sends messages to the client and has been available since Spring Framework 5.1.

## 1. Why Can Receive Order Change?

A WebSocket connection maintains data order on a single connection. However, after Spring decodes a STOMP frame, the message is sent into `clientInboundChannel` for further processing. The channel is backed by a `ThreadPoolExecutor` by default; tasks can run on different threads.

For example, a client sends three consecutive commands on the same session:

~~~text
M1: increase product quantity by 1
M2: set cart value to 200
M3: confirm cart
~~~

The transport receives M1, then M2, then M3. If the three tasks are processed concurrently, M2 or M3 may be processed before M1. In that case, the business state can differ from what the client intended.

This is especially important when handlers:

- Update the same record or aggregate.
- Mutate state step by step.
- Process sequential commands such as creating an order and then confirming it.
- Depend on state just updated by the previous message.
- Record history or event sequences that must preserve order.

By default, Spring prioritizes parallel channel processing. If message ordering from a session is a business requirement, you need to enable the corresponding ordering mechanism.

## 2. Enabling setPreserveReceiveOrder Since Spring Framework 6.1

The `setPreserveReceiveOrder(boolean)` API was added in Spring Framework 6.1. It is configured through `StompEndpointRegistry` in the `registerStompEndpoints` method:

~~~java
package com.example.messaging;

import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfiguration
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.setPreserveReceiveOrder(true);
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

When set to `true`, Spring sends messages belonging to the same session to `clientInboundChannel` one message at a time in the exact order they were received. Other sessions can still be processed concurrently.

If this method is not called or is set to `false`, Spring keeps the default behavior: messages on `clientInboundChannel` can be processed concurrently and the processing order may differ from the receive order.

`setPreserveReceiveOrder` is a `StompEndpointRegistry`-level configuration, not an annotation on individual `@MessageMapping` methods. It applies to the handling mechanism of STOMP endpoints registered in that registry.

## 3. Guarantee Scope: Per Session

Suppose there are two client sessions A and B:

~~~text
Session A receives: A1 -> A2 -> A3
Session B receives: B1 -> B2 -> B3
~~~

When `setPreserveReceiveOrder(true)` is enabled, Spring preserves the order A1 → A2 → A3 within session A and B1 → B2 → B3 within session B. The two sessions can still proceed concurrently; Spring does not create a global queue forcing all clients to wait for one another.

Therefore, the guarantee scope is:

- Preserves receive order among messages within the same STOMP session.
- Does not establish a global order across different sessions.
- Does not merge multiple sessions of the same user into a single sequential stream.
- Does not reorder messages by client-supplied timestamps.
- Does not replace sequence numbers or business-layer synchronization when multiple clients update the same resource.

A user who opens two browser tabs typically has two separate STOMP sessions. If both tabs send commands to the same order, `setPreserveReceiveOrder(true)` does not determine which tab's command must run first. The application needs business-layer synchronization rules for concurrent writes from multiple sessions.

## 4. Distinguishing Receive Order and Publish Order

Spring has two easily confused option names that control opposite directions:

| Option | Configuration Location | Message Direction | Supported Version |
|---|---|---|---|
| `setPreserveReceiveOrder(true)` | `StompEndpointRegistry` in `registerStompEndpoints` | Client → server, via `clientInboundChannel` | Since Spring Framework 6.1 |
| `setPreservePublishOrder(true)` | `MessageBrokerRegistry` in `configureMessageBroker` | Server → client, via `clientOutboundChannel` | Since Spring Framework 5.1 |

### Receive Order from Client

`setPreserveReceiveOrder` handles the case where the server receives M1, M2, M3 from the same client session. Spring passes them into `clientInboundChannel` one by one so server-side processing preserves the receive order.

~~~java
@Override
public void registerStompEndpoints(StompEndpointRegistry registry) {
    registry.setPreserveReceiveOrder(true);
    registry.addEndpoint("/ws");
}
~~~

### Send Order to Client

`setPreservePublishOrder` handles the case where the broker emits multiple messages to the same client session. Because `clientOutboundChannel` also uses a thread pool, published messages may reach the WebSocket session in a different order. Enable this option so Spring sends messages in the same session one by one:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableSimpleBroker("/topic", "/queue");
    registry.setPreservePublishOrder(true);
}
~~~

The two options are independent. If the application needs to preserve order both when receiving commands from the client and when sending results back to the client, both can be enabled:

~~~java
@Override
public void registerStompEndpoints(StompEndpointRegistry registry) {
    registry.setPreserveReceiveOrder(true);
    registry.addEndpoint("/ws");
}

@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableSimpleBroker("/topic", "/queue");
    registry.setPreservePublishOrder(true);
}
~~~

Enabling one option does not automatically enable the other. Nor should you enable `setPreservePublishOrder` to try to fix the order of messages sent by clients; it applies only to the outbound direction.

## 5. Differences by Spring Framework Version

`setPreserveReceiveOrder` is available starting from Spring Framework 6.1. The Javadoc for `StompEndpointRegistry` clearly states this API was added in version 6.1; the feature is also noted in the Spring Framework 6.1 release notes.

| Spring Framework Version | `setPreserveReceiveOrder` | `setPreservePublishOrder` |
|---|---|---|
| 5.0 and earlier | Not available | Not available |
| 5.1 through 6.0.x | Not available | Available |
| 6.1 and later | Available | Available |

If a project uses Spring Framework 6.0 or earlier, calling `registry.setPreserveReceiveOrder(true)` will not compile because the method does not yet exist in that API. `setPreservePublishOrder` has existed since 5.1, but it cannot substitute for sequential receive handling.

When a project uses Spring Boot, check the actual Spring Framework version resolved by dependency management, rather than inferring solely from the Boot version or a single declared version line in the build file. With Gradle you can check:

~~~bash
./gradlew dependencyInsight --dependency spring-websocket --configuration runtimeClasspath
~~~

With Maven:

~~~bash
mvn dependency:tree -Dincludes=org.springframework:spring-websocket
~~~

Check the `spring-websocket` module actually running. If the application is pinned to an older Spring Framework version than the BOM, the API may not exist even though other modules have been upgraded.

### If You Cannot Upgrade to 6.1 Yet

In Spring 5.x or 6.0, `setPreserveReceiveOrder` does not exist in `StompEndpointRegistry`. You can handle ordering at the application layer with a per-session sequential queue, a sequential executor keyed by key/session, or sequence numbers to detect and handle out-of-order messages.

Do not arbitrarily set a single-threaded executor for the entire `clientInboundChannel` just to preserve order for each client. That approach can serialize all clients across the whole application, creating a bottleneck and hurting scalability. If a fallback is needed, design queues per session or per aggregate that needs protection.

## 6. Performance Impact

Preserving order means messages within the same session are no longer processed in parallel on `clientInboundChannel`. That prevents reordering, but limits per-session parallelism.

Things to consider:

- A slow-running handler will make subsequent messages from the same session wait.
- If a session sends messages faster than they can be processed, the queue can increase latency.
- Other sessions can still use the remaining threads of the inbound channel.
- Increasing the thread pool does not make a single session process in parallel again while preserve receive order is enabled.
- Handlers should avoid prolonged blocking I/O; use timeouts, controlled asynchronous processing, or offload long work to an appropriate pipeline.

In STOMP configuration, `clientInboundChannel` is executed by a thread pool. Pool size, queue capacity, and handler workload type remain important. For CPU-bound workloads, thread count should be close to available CPUs. For I/O-bound workloads that wait on a database or external service, you need to measure and tune accordingly.

Do not increase pool size to fix a slow handler within the same session when receive ordering is enabled. That session's next message still has to wait for the previous message to finish its synchronous processing on the channel.

## 7. Limits with Asynchronous Processing and Multiple Write Sources

`setPreserveReceiveOrder` controls the order in which messages are passed through `clientInboundChannel`. It does not create a shared transaction across handlers, nor does it control any asynchronous tasks that a handler launches.

For example, a handler receives a command and submits a task to another executor:

~~~java
@MessageMapping("/orders/{orderId}/commands")
public void handle(
        @DestinationVariable String orderId,
        @Payload OrderCommand command) {

    asyncExecutor.execute(() -> orderService.apply(orderId, command));
}
~~~

Spring may receive and dispatch commands in order, but tasks in `asyncExecutor` can still finish in a different order if the executor allows parallel execution. Similarly, asynchronous HTTP calls, `CompletableFuture`, reactive pipelines, or out-of-band event processing can complete in a different order than originally received.

If business completion order is mandatory, it must be protected at the business execution layer, for example:

- Use a sequential queue keyed by `orderId` or aggregate key.
- Attach a monotonically increasing sequence number to each command stream and reject or buffer out-of-order commands.
- Use optimistic locking/versioning to detect stale updates.
- Use transactions and appropriate locking mechanisms when multiple sessions write to the same resource.
- Design idempotent handlers so message retries do not cause duplicate application.

This feature also does not provide ordering across server instances. If multiple nodes receive messages from different sessions or a user connects to multiple nodes, separate distributed ordering and synchronization must be designed.

## 8. Example of Testing Receive Order

You can verify this feature with a STOMP client sending commands numbered sequentially. The controller records the processing order:

~~~java
@Controller
public class SequenceController {

    private final List<Integer> received =
            new CopyOnWriteArrayList<>();

    @MessageMapping("/sequence")
    public void receive(@Payload Integer sequence) {
        received.add(sequence);
    }

    public List<Integer> receivedMessages() {
        return List.copyOf(received);
    }
}
~~~

Client sends consecutively:

~~~java
for (int sequence = 1; sequence <= 5; sequence++) {
    session.send("/app/sequence", sequence);
}
~~~

In the integration test, wait until all five messages are processed and compare the received list with:

~~~text
[1, 2, 3, 4, 5]
~~~

To test the exact scope:

1. Use one session to send multiple consecutive messages and verify processing order.
2. Run the test with `setPreserveReceiveOrder(false)` to understand that the thread pool can process concurrently; do not require every run to reorder because reordering is a possibility, not a guaranteed outcome.
3. Enable `true` and verify messages from the same session are processed sequentially.
4. Open two sessions and verify they can still proceed concurrently.
5. Test a slow synchronous handler to observe subsequent messages in the same session waiting.
6. Test a handler that offloads work to another executor to observe that asynchronous task completion is not automatically serialized.
7. If server publish ordering is needed, test `setPreservePublishOrder(true)` separately.

In real tests, use latches or timed wait conditions instead of fixed `Thread.sleep`. That makes tests more reliable when CI or test machines have varying loads.

## 9. Common Errors and How to Handle Them

| Symptom | Common Cause | How to Check or Fix |
|---|---|---|
| Cannot compile `setPreserveReceiveOrder` | Using Spring Framework earlier than 6.1 | Check `spring-websocket` dependency; upgrade to 6.1+ or use application-level serialization. |
| Enabled `setPreservePublishOrder` but inbound messages still reorder | Configured the server → client direction | Use `StompEndpointRegistry.setPreserveReceiveOrder(true)` for client → server. |
| Messages in the same session process in order, but two tabs still conflict | Each tab is a separate STOMP session | Use locks, versions, or sequences per aggregate at the business layer. |
| Handler receives in order, but database commits out of order | Handler offloads or executes asynchronously | Serialize at the executor/service or use appropriate transactions/versions. |
| Enabling receive order gives a session high latency | Slow synchronous handler blocks the session's next message | Reduce handler duration, limit I/O, and move long work to a separate ordered pipeline. |
| Increased thread pool, but one session still runs sequentially | Intentional behavior of preserve receive order | Evaluate per-session throughput and enable only when business logic requires it. |
| Assuming all sessions run sequentially globally | Misunderstood per-session scope | Re-verify: different sessions can still process concurrently. |
| Relying on client timestamps to infer order | Client clocks can drift and requests can arrive out of order | Use sequence numbers or actual receive order of the same session. |

## 10. Configuration Selection Checklist

Before enabling `setPreserveReceiveOrder(true)`, answer:

1. Does business logic depend on the order of messages from the same session?
2. Do handlers perform sequential state updates?
3. Are any handlers blocking or holding threads for a long time?
4. Is any asynchronous work offloaded to another executor?
5. Is the ordering requirement per session, per user, or per aggregate? This API only solves per session.
6. Is the actual `spring-websocket` version 6.1 or higher?
7. Do you also need to preserve server → client publish order separately with `setPreservePublishOrder`?
8. Do tests cover same-session, multi-session, and asynchronous processing?

Enable only when there is a clear requirement. If the system needs correctness across multiple clients editing the same resource, combine per-session ordering control with synchronization and version checks at the business layer.

## References

- [Spring Framework Reference — Order of Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/ordered-messages.html): explains why inbound/outbound channels can process out of order and how to configure both options.
- [Spring Framework 6.1.11 Javadoc — StompEndpointRegistry](https://www.springframework.org/spring/docs/6.1.11/javadoc-api/org/springframework/web/socket/config/annotation/StompEndpointRegistry.html): `setPreserveReceiveOrder(boolean)` and same-session ordering guarantee scope.
- [Spring Framework 6.1.11 Javadoc — WebMvcStompEndpointRegistry](https://www.springframework.org/spring/docs/6.1.11/javadoc-api/org/springframework/web/socket/config/annotation/WebMvcStompEndpointRegistry.html): STOMP endpoint registry implementation and receive order API.
- [Spring Framework 6.1 — Performance](https://docs.spring.io/spring-framework/reference/6.1/web/websocket/stomp/configuration-performance.html): `clientInboundChannel`/`clientOutboundChannel` thread pools and performance impact.
- [Spring Framework 6.x — What's New](https://github.com/spring-projects/spring-framework/wiki/What's-New-in-Spring-Framework-6.x): notes the `preserveReceiveOrder` feature added in Spring Framework 6.1.
