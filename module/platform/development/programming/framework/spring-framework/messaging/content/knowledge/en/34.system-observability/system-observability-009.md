# Application Readiness When the Broker or Transport Is Unavailable

## 1. What Is Readiness?

Readiness describes whether an instance is currently eligible to receive additional work. For a Spring Messaging application, this depends on its ability to perform the workload assigned to it: accepting HTTP requests that produce messages, publishing to a broker, consuming from a queue, or calling a peer over RSocket.

A process can still be running normally yet unable to serve its workload. For example:

- The Spring ApplicationContext has initialized and the HTTP server is listening, but the JMS broker has not started yet.
- The application has created a `JmsTemplate`, but the first send fails because the broker is not accepting connections.
- `@JmsListener` is registered in Spring, but the listener container has not connected to the destination.
- The application has created an `RSocketRequester`, but the remote peer is unreachable.
- The broker has recovered, but the consumer has not re-registered its subscription or completed required initialization steps.

Readiness tells the deployment platform which instances can receive new traffic or work. It is an operational signal, not a connection self-healing mechanism. Spring JMS, the JMS provider, the RSocket client, and retry policies remain responsible for communication recovery.

Distinguish three concepts:

- **Liveness:** whether the process is alive and able to continue on its own. If liveness fails, Kubernetes may restart the container.
- **Readiness:** whether the instance should receive new traffic/workload. If readiness fails, Kubernetes removes the instance from ready endpoints.
- **Startup probe:** whether the application has finished initial startup. This probe prevents Kubernetes from concluding an instance is dead when startup takes a long time.

A temporarily unavailable broker is usually a readiness or degraded-state issue. Never turn every external connectivity failure into a liveness failure, as restarting instances en masse can put extra load on a recovering broker.

## 2. Determining Whether a Broker or Transport Is Required

Before adding a dependency to readiness, decide whether it is essential to the functionality the instance provides.

| Scenario | What readiness should reflect |
|---|---|
| App receives an HTTP command and must publish to JMS to complete the request | Not ready if unable to publish per the API contract |
| App solely consumes a required queue to perform its primary function | Not ready if the broker or consumer subscription is not active |
| App sends emails via an optional queue, able to write to an outbox and process later | Can stay ready; expose degraded state and monitor backlog |
| RSocket peer is a required dependency for every request | Not ready if required calls to the peer cannot succeed |
| RSocket only serves a secondary feature with a fallback | Can stay ready; only that feature returns degraded/fallback |
| Shared broker across all replicas loses connectivity | Weigh removing all replicas from traffic; errors can be handled at the call layer if the app has a fallback |

A broker outage does not automatically mean the entire application must stop accepting HTTP traffic. If the application can still handle queries, persist requests into an outbox, or provide a valid fallback, readiness can remain accepting traffic. What matters is that the application's responses remain honest to its business commitments: never return success for an operation the system has not durably saved or safely accepted.

For an instance running multiple capabilities, you can separate readiness by workload group or endpoint. A dependency should only affect the group that truly requires it.

## 3. Readiness in the Spring Boot Lifecycle

A typical lifecycle has these steps:

1. JVM and Spring ApplicationContext start up.
2. Beans, configuration, connection factories, listener containers, and transports are created.
3. Spring runs required startup tasks.
4. The application transitions from `REFUSING_TRAFFIC` to `ACCEPTING_TRAFFIC` once startup finishes.
5. During runtime, the broker/peer may disconnect. The instance re-evaluates its ability to accept workload.
6. When essential dependencies recover and required listeners/transports are working again, the instance can accept traffic.
7. During shutdown, the instance switches to refusing traffic before stopping listeners and releasing resources.

Spring Boot manages availability state through `ApplicationAvailability`. The common readiness states are:

- `ReadinessState.REFUSING_TRAFFIC`
- `ReadinessState.ACCEPTING_TRAFFIC`

Actuator provides `ReadinessStateHealthIndicator` to expose this state in the health endpoint. Applications can update the state using `AvailabilityChangeEvent`.

Note: ApplicationContext initialization alone does not prove the broker or remote peer is ready. Default startup readiness mostly reflects application lifecycle; external dependencies must be evaluated separately.

## 4. Liveness and Readiness Must Not Be Used Interchangeably

### 4.1. Liveness does not depend on the broker

Liveness should check the process's ability to operate on its own: whether the event loop or web server responds, whether critical threads are hung, or whether the application has entered an unrecoverable state.

If the broker disconnects:

- Liveness usually remains healthy.
- Listener containers can keep attempting to reconnect.
- Publishers can record errors or persist requests to an outbox.
- Readiness is decided based on whether the broker is essential to the workload.

Putting JMS health into liveness can cause broker downtime to restart all pods in Kubernetes. Newly restarted pods then simultaneously reconnect to an overloaded or still-recovering broker, creating a restart and reconnect storm.

### 4.2. Readiness reflects capacity to accept workload

Readiness can combine application state and certain mandatory dependencies. If the broker is a prerequisite for an instance to take new requests, readiness needs to check the broker or an equivalent connection state.

If a dependency has a fallback, circuit breaker, or reliable outbox, you can keep the instance ready and return errors/degraded responses for the affected feature.

### 4.3. Startup probe for slow-starting applications

If an application needs a long time to create listeners, initialize schemas, register subscriptions, or load configuration, Kubernetes can use a `startupProbe` to avoid evaluating liveness too early. Readiness must still refuse traffic until startup completes.

A startup probe does not replace readiness. It only adjusts how the platform observes the startup phase.

## 5. Spring Boot Actuator and Kubernetes Probes

### 5.1. Enabling health probes

When using Spring Boot Actuator, the endpoints typically take the form:

- `/actuator/health/liveness`
- `/actuator/health/readiness`

Spring Boot automatically manages availability state and provides matching health groups when probes are enabled. You can configure it explicitly:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      show-details: when-authorized
~~~

By default, Spring Boot does not automatically add every external health indicator to the readiness group. If you need to check a JMS broker, include its indicator in the group.

### 5.2. Including JMS health in readiness

Spring Boot provides a JMS health indicator with ID `jms` when JMS and Actuator are configured. This indicator checks broker connectivity via `ConnectionFactory`. It is not in the readiness group by default.

If the broker is a mandatory dependency, you can configure:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: readinessState,jms
      show-details: when-authorized
~~~

When the broker is unreachable, `jms` reports `DOWN`, making the readiness group unhealthy. When the broker recovers and the check succeeds, the group returns to healthy.

The package name of the JMS health indicator changes across Spring Boot major versions. Use the API matching your project version; Boot 3.x and Boot 4.x use different packages.

**JMS health does not prove the entire message flow works.** Connecting to the broker successfully does not guarantee the destination exists, the user has publish/consume permissions, listeners are subscribed, selectors are valid, or consumers can process messages. If those conditions are mandatory, add targeted checks tailored to your workload.

### 5.3. Kubernetes probes

Abbreviated configuration example:

~~~yaml
livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  periodSeconds: 10
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  periodSeconds: 5
  failureThreshold: 2

startupProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  periodSeconds: 5
  failureThreshold: 30
~~~

These numbers are examples; tune them to startup time, timeouts, reconnect cycles, and SLAs. Probes must respond quickly and avoid adding heavy load to the broker.

If the management endpoint runs on a separate port, probes might succeed against the management server even when the main server cannot accept connections. You can enable additional paths on the main server port:

~~~yaml
management:
  endpoint:
    health:
      probes:
        add-additional-paths: true
~~~

Spring Boot then exposes additional paths such as `/livez` and `/readyz` on the main port. Ensure probes target the application's actual port and path.

## 6. Managing Availability State with Spring Boot

When an application has a connection monitor or lifecycle coordinator, it can publish `AvailabilityChangeEvent` to change readiness:

~~~java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Component;

import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;

@Component
public class MessagingAvailability {

    private final ApplicationEventPublisher publisher;

    public MessagingAvailability(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void refuseTraffic() {
        AvailabilityChangeEvent.publish(
            publisher, this, ReadinessState.REFUSING_TRAFFIC);
    }

    public void acceptTraffic() {
        AvailabilityChangeEvent.publish(
            publisher, this, ReadinessState.ACCEPTING_TRAFFIC);
    }
}
~~~

Call `refuseTraffic()` when a mandatory dependency or core capability cannot serve workload. Call `acceptTraffic()` only after all required conditions have recovered.

**Do not let individual dependencies publish ACCEPTING_TRAFFIC independently.** For instance, the broker recovers while the database is still down; if the JMS monitor immediately publishes accepting, it can overwrite the refusing state caused by the database. In applications with multiple dependencies, use a readiness coordinator that aggregates the state of all mandatory components.

The coordinator should also apply debounce or hysteresis: transition state only after an appropriate number of checks or confirmation window, preventing readiness from flapping on/off during flaky networks.

If you already use a health group combining `readinessState` and `jms`, you do not necessarily need to publish availability events for every broker failure. Health indicators can reflect dependency state directly; use availability events when the application needs to coordinate global state or conditions that cannot be expressed by a single indicator.

## 7. JMS: Startup, Listener Recovery, and Sending Messages

### 7.1. ConnectionFactory and JmsTemplate

`JmsTemplate` requires a `ConnectionFactory`. Creating the template bean does not mean the broker connection has been verified. Actual send calls use resources to create connections/sessions/producers according to the provider and connection factory implementation.

Example:

~~~java
jmsTemplate.convertAndSend("orders.commands", command);
~~~

If the broker is unavailable, the operation may throw a JMS error translated by Spring into an unchecked exception. The application must decide whether to return an error to the caller, store it in an outbox, or retry per policy. Do not hold HTTP requests or handler threads in an infinite retry loop.

For critical commands/events, a transactional outbox is usually better than long synchronous publish retries: write business state and the outbox row in the same database transaction, then let a relay publish when the broker recovers.

### 7.2. @JmsListener and DefaultMessageListenerContainer

Spring uses listener containers to connect consumers to the JMS provider, register to receive messages, and manage threading/resources. In typical cases, `DefaultMessageListenerContainer` is the appropriate default.

This container can recover when the broker goes down. According to Spring Framework documentation, the default backoff retries every 5 seconds; applications can configure a custom `BackOff` to control the recovery interval.

This means a listener can still be in the middle of reconnecting while the broker is unavailable. Do not rely solely on a listener bean existing to conclude the consumer can receive messages.

Distinguish:

- The listener endpoint is registered in Spring.
- The listener container is running per lifecycle.
- The JMS connection is established.
- The consumer has successfully subscribed to the destination.
- Messages can actually be received and processed.

These states are not synonymous. If the workload requires consumer subscriptions to be ready before a pod accepts traffic, readiness must reflect actual subscription readiness or an equivalent health check.

### 7.3. Checking listener containers

`JmsListenerEndpointRegistry` gives access to listener containers created by `@JmsListener`. You can inspect lifecycle state for diagnostics or a readiness coordinator:

~~~java
import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.listener.MessageListenerContainer;
import org.springframework.stereotype.Component;

@Component
public class ListenerStatus {

    private final JmsListenerEndpointRegistry registry;

    public ListenerStatus(JmsListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public boolean requiredListenerRunning(String id) {
        MessageListenerContainer container =
            registry.getListenerContainer(id);

        return container != null && container.isRunning();
    }
}
~~~

Declare the listener to check with an explicit ID, such as `ordersListener`, and pass that ID to `requiredListenerRunning`.

This is a lifecycle check. `isRunning()` does not guarantee the broker is accepting connections or the subscription is currently active. With `DefaultMessageListenerContainer`, the container can be running and continuously attempting to reconnect while the broker is down.

Therefore, combine container status with broker health or subscription state reported by the provider/container. Never treat a lifecycle boolean as an end-to-end test.

### 7.4. Recovery and backoff

Backoff determines how often reconnection is attempted. A sound policy should:

- Increase the wait interval as failures persist.
- Have an upper cap so retries still happen periodically.
- Add jitter when multiple replicas might reconnect simultaneously.
- Avoid creating a second reconnect loop competing with the listener container's built-in recovery.
- Rate-limit logs to avoid log storms.
- Distinguish permanent configuration errors such as bad credentials from transient network errors.

`DefaultMessageListenerContainer` supports custom `BackOff`. Read your provider's and Spring version's documentation to choose the right configuration. For brief broker outages, built-in recovery is usually sufficient; customize only for specific operational needs.

### 7.5. Handling broker recovery

When the broker comes back, do not immediately mark the whole application ready just because the TCP port opens. Wait until:

1. ConnectionFactory can establish valid connections.
2. Authentication and permissions are verified.
3. Listener containers reconnect.
4. Consumers register required destinations/subscriptions.
5. Local application initialization steps have finished.

Only then should the coordinator flip readiness to accepting, provided other mandatory dependencies are also ready.

If messages are redelivered after reconnect, handlers must be idempotent and have a duplicate-handling strategy. Connection recovery does not guarantee exactly-once processing.

## 8. RSocket and Transports Connecting to Remote Peers

### 8.1. Creating RSocketRequester does not mean connected

Spring's `RSocketRequester` offers a fluent API to send requests over RSocket. A requester can be built as:

~~~java
RSocketRequester requester = RSocketRequester.builder()
    .tcp("localhost", 7000);
~~~

According to Spring documentation, the `tcp` or `webSocket` call in this example does not connect immediately. The shared connection is established when the application starts sending a request.

Therefore, the ApplicationContext creating an `RSocketRequester` bean does not prove the peer is up. Readiness for a mandatory RSocket dependency must verify the ability to perform an actual interaction or track connection state from the client/transport.

### 8.2. Using a side-effect-free check route

You can define a lightweight route that only returns status:

~~~java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
class PeerReadinessController {

    @MessageMapping("system.readiness")
    public Mono<Boolean> readiness() {
        return Mono.just(true);
    }
}
~~~

The client can call that route with a bounded timeout:

~~~java
import java.time.Duration;
import reactor.core.publisher.Mono;

Mono<Boolean> peerReady = requester
    .route("system.readiness")
    .retrieveMono(Boolean.class)
    .timeout(Duration.ofSeconds(2))
    .onErrorReturn(false);
~~~

This is an example of an application-level probe. The route must exist on the peer and should only assert conditions it actually guarantees. If the peer simply returns `true` whenever its process is alive, that does not prove dependencies behind the peer are also ready.

Do not send a heavy probe on every Kubernetes readiness call. You can run probes periodically with a timeout, cache the latest state, and let readiness read the updated state. The probe interval should be short enough to detect outages without overloading the peer.

### 8.3. Distinguishing inbound server and outbound client

- **Inbound RSocket server:** readiness reflects that the transport is bound, the responder can accept requests, and required handler dependencies are available.
- **Outbound RSocket client:** readiness may depend on the remote peer if the peer is mandatory for the workload.
- **Optional peer:** keep the instance ready if fallbacks or remaining features still satisfy contracts; record degraded state separately.

If you only have a requester bean and no request has been sent yet, you cannot conclude a remote connection exists. Conversely, one successful probe does not guarantee the connection stays up forever; handle timeouts and errors on every request.

## 9. Retries, Timeouts, Circuit Breakers, and Outboxes

Readiness only gates accepting new workload. In-flight requests can still fail, so communication-layer resilience policies are needed.

### 9.1. Timeouts

Set bounded timeouts on connect, send, and request-response operations. Timeouts must align with SLAs and upstream caller timeouts.

If timeouts are too long, threads or connections can stay pinned while the broker/peer is down. If too short, the application may reject valid operations during brief slowdowns.

### 9.2. Bounded retries

Retries suit recoverable errors only. Use exponential backoff and jitter to avoid all replicas retrying at once. Cap retry attempts or total retry duration; afterward, return a clear error, persist to an outbox, or route the message to an appropriate error-handling mechanism.

Do not blindly retry unrecoverable errors such as bad credentials, invalid schemas, or denied permissions.

### 9.3. Circuit breakers

A circuit breaker stops requests from hammering a failing dependency. When the breaker is open, callers can fail fast or use a fallback. This can allow an application to remain ready if that dependency is not vital to the entire workload.

A circuit breaker does not self-heal a JMS listener container and does not replace readiness probes. The two mechanisms solve different layers of problems.

### 9.4. Outbox and durable messaging

If requests must be accepted even during temporary broker outages, the application can write commands/events to an outbox within the business transaction. A relay worker republishes when the broker recovers.

In this model, readiness can stay accepting if the database/outbox is the durable intake point and the system commits to asynchronous processing. Monitor backlog, oldest message age, and outbox capacity; if backlog exceeds thresholds or the database cannot write, readiness may need to flip.

Never return success if the message only sits in memory and could be lost on process restart.

## 10. Graceful Shutdown While Using Messaging

Upon receiving a shutdown signal, an instance should:

1. Switch readiness to `REFUSING_TRAFFIC` to stop receiving new workload.
2. Stop accepting new requests at the application layer or relevant routes.
3. Stop or pause listener containers according to the application's drain policy.
4. Allow in-flight messages to finish within the grace period.
5. Commit transactions/acks according to consumer semantics.
6. Release connections and transports.
7. Let the broker redeliver unacknowledged messages per provider policy.

Spring Boot HTTP graceful shutdown does not automatically guarantee all JMS listeners have drained safely. Configure lifecycle and shutdown grace periods aligned with containers, transactions, brokers, and message processing durations.

Never acknowledge a message before critical work is committed. If a consumer dies between processing and ack, the message may be redelivered; handlers must handle duplicates safely.

## 11. Observing Messaging State

Readiness endpoints are only one piece of operations. Also monitor:

**JMS/broker**

- Connection failures and reconnect counts.
- Duration the broker was unavailable.
- Listener container states and active consumer counts.
- Queue depth, consumer lag, and oldest message age.
- Publish failures, redeliveries, rollbacks, and dead-letter counts.
- Outbox backlog and time waiting to publish.

**RSocket/transport**

- Connection counts and connection failures.
- Keepalive timeouts or disconnects.
- Request latency, timeouts, and error rates per route.
- Reconnect/resume counts if those mechanisms are configured.
- Probe success rate and age of the latest probe.

**Application**

- How many times readiness state transitions occurred.
- Time from broker recovery to the application becoming ready.
- Requests rejected due to dependencies.
- Circuit breaker open/half-open transitions.
- Shutdown duration and remaining in-flight messages.

Logs should include correlation ID, destination/route, message ID, and error category. Do not log credentials, tokens, or full sensitive payloads. Health details should also have restricted access.

## 12. Testing Scenarios When Brokers or Transports Are Unavailable

A valuable readiness test must simulate real dependency failures or equivalent test doubles rather than only calling the health endpoint while everything is running.

| Scenario | Outcome to verify |
|---|---|
| App starts while broker is down | Process does not suffer continuous liveness restarts; readiness refuses if JMS is mandatory |
| Broker starts after app | Listeners reconnect; readiness accepts only after required conditions are met |
| Broker disconnects while app runs | Liveness stays healthy; readiness changes per dependency policy |
| Bad credentials or missing destination permissions | No infinite retries; errors are observed and readiness reflects affected functionality |
| Broker recovers after a long outage | Listeners resume, messages process, duplicates cause no repeat side effects |
| Queue backlog grows high | Alerts fire on lag/age; readiness switches to refusing only when defined thresholds hit |
| RSocket peer down before first request | Probe detects peer unavailable; requester bean existence is not treated as connected |
| RSocket peer disconnects between two requests | Requests fail with clear timeout/error; probe updates state per policy |
| Secondary dependency down | Instance stays ready if the fallback genuinely fulfills the contract |
| Shutdown while messages are in-flight | Instance stops taking new work, drains or redelivers messages per semantics |

In Kubernetes, confirm the readiness probe removes the instance from endpoints when refusing traffic and restores it when healthy. Also test when all replicas become unready at once to understand how Services/Ingress/load balancers behave in your actual deployment environment.

## 13. Common Mistakes

1. **Putting the broker into liveness.** Broker downtime causes mass pod restarts and reconnect storms. Keep liveness independent of external dependencies.
2. **Assuming readiness checks JMS by default.** Spring Boot does not automatically add every external health indicator to the readiness group; include it explicitly.
3. **Assuming a JmsTemplate means the broker is connected.** Bean existence does not prove an actual send will succeed.
4. **Assuming @JmsListener means the consumer is subscribed.** Check container lifecycle, connections, and subscriptions.
5. **Assuming a requester bean is an RSocket connection.** Spring RSocketRequester connects lazily when a request is sent.
6. **Probes executing real business logic.** Probes could create orders, send emails, or mutate state. Use lightweight, bounded, read-only routes/operations.
7. **Infinite retries on request threads.** Exhausts threads, spikes latency, and amplifies outages. Use timeouts, backoff, outboxes, or fail fast.
8. **Letting each dependency set readiness accepting.** One recovering dependency can overwrite a refusing state from another dependency. Use an aggregating coordinator.
9. **Continuous readiness flapping.** Flaky networks cause instances to be repeatedly added and removed from load balancers. Use debounce/hysteresis.
10. **Not draining listeners on shutdown.** Messages can be lost or double-processed if ack/transactions are mishandled. Design shutdown and idempotency carefully.

## 14. Design Checklist

- [ ] Identify which brokers/transports are mandatory for each workload.
- [ ] Distinguish liveness, readiness, and startup probes.
- [ ] Keep external dependency failures out of liveness when the app can self-recover.
- [ ] Configure the Actuator readiness group with the right essential dependencies.
- [ ] Do not assume JMS health proves listeners are subscribed or the full message flow works.
- [ ] Do not assume an RSocketRequester bean equals an active remote connection.
- [ ] Ensure probes have timeouts, low cost, and zero side effects.
- [ ] Use a single coordinator when multiple dependencies jointly determine readiness.
- [ ] Configure proper backoff/reconnect without creating retry storms.
- [ ] Use an outbox or durable intake mechanism if broker downtime must be tolerated.
- [ ] Monitor queue depth, lag, reconnects, DLQ, and recovery duration.
- [ ] Implement graceful shutdown and handle in-flight messages.
- [ ] Run fault-injection tests for broker down, recovery, permission failures, and peer disconnects.

## 15. References

- [Spring Boot Reference — Actuator Endpoints: Health and Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): health groups, liveness/readiness state, probe paths, and evaluating external dependencies.
- [Spring Boot API — ApplicationAvailability](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/availability/ApplicationAvailability.html): querying the application's current availability state.
- [Spring Boot API — AvailabilityChangeEvent](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/availability/AvailabilityChangeEvent.html): publishing events to update readiness/liveness state.
- [Spring Boot API — JmsHealthIndicator](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/jms/health/JmsHealthIndicator.html): health indicator checking JMS ConnectionFactory and broker.
- [Spring Framework Reference — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html): JmsTemplate, ConnectionFactory, listener containers, and DefaultMessageListenerContainer recovery.
- [Spring Framework Reference — RSocketRequester](https://docs.spring.io/spring-framework/reference/rsocket.html): building requesters, lazy connection, request/response, and TCP/WebSocket transports.
