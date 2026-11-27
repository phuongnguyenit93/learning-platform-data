# Pausing, Resuming Consumption, and Monitoring Idle Consumers

A Kafka consumer does not always need to receive data continuously. An application may need to pause consumption when a downstream system is overloaded, during maintenance windows, to throttle processing rate, or when an operational workflow requires holding a backlog for later processing. Afterward, the consumer must resume from its saved position without losing progress.

The Spring Cloud Stream Kafka binder supports pausing and resuming an input binding via the binding lifecycle. This capability relies on pause/resume in Spring Kafka's listener container. The consumer continues participating in Kafka's poll mechanism while paused, allowing it to maintain consumer group membership and avoid rebalances solely because the application temporarily stopped taking records.

This lesson covers distinguishing pause from stop, controlling bindings via API and Actuator, configuring idle events, detecting when a consumer becomes active again, and monitoring state in production.

## 1. Distinguishing pause, resume, and stop

These operations serve different purposes:

| State | Behavior | Impact on Consumer Group |
|---|---|---|
| **PAUSED** | Temporarily stops pulling new records from Kafka. The listener container still polls but delivers no records to the application. | Consumer maintains group membership; generally avoids rebalances caused merely by pausing. |
| **RESUMED** | Resumes receiving records after the binding was paused. | Consumer continues reading from its current progress according to committed offsets and processing state. |
| **STOPPED** | Stops the binding and consumer container. | Consumer leaves the group; Kafka may rebalance and assign partitions to other members. |
| **STARTED** | Restarts a stopped binding. | Consumer rejoins the group and receives partition assignments via rebalance. |

When you need to temporarily halt consumption while keeping the consumer in the group, choose **pause**. When you truly need to shut down consumption, release resources, or perform container maintenance, **stop** may be more appropriate.

~~~mermaid
stateDiagram-v2
    [*] --> STARTED
    STARTED --> PAUSED: pause
    PAUSED --> RESUMED: resume
    RESUMED --> PAUSED: pause
    STARTED --> STOPPED: stop
    PAUSED --> STOPPED: stop
    RESUMED --> STOPPED: stop
    STOPPED --> STARTED: start
~~~

Pausing does not delete records from the topic and does not automatically commit offsets. Producers can continue writing data to the topic while the consumer is paused. Consequently, backlog can grow; retention capability remains subject to topic retention, broker storage, and topic policies.

## 2. Why Does Pause Not Trigger a Rebalance Like Stop?

A Kafka consumer must continue calling `poll()` to remain alive and participate in group management. If an application stops polling for too long, the consumer can exceed `max.poll.interval.ms`, be deemed inactive, and trigger partition reassignment.

Spring Kafka implements pause by instructing the container to pause record fetching at the next poll boundary. The container keeps polling Kafka while fetching no new records during the pause. As a result, the consumer maintains group membership while the application temporarily halts data processing.

Important caveats:

- A pause command is a control request; the actual paused state takes effect on the next eligible poll cycle.
- Records already returned from the preceding poll may still be finishing processing before pause takes effect.
- Upon resume, the consumer continues fetching records per offset progress and configured ACK/commit rules.
- If the consumer stops completely, loses connectivity, or fails to poll on time, Kafka can still rebalance for those reasons.
- Pausing does not stop producers from publishing and does not extend topic retention.

Spring Kafka provides `pause()` and `resume()` on listener containers for safe control. With Spring Cloud Stream applications, control through the binding lifecycle rather than extracting the raw Kafka Consumer from headers and calling methods on it from an arbitrary thread.

## 3. Identifying the Exact Input Binding to Control

Suppose the application declares a consumer function:

~~~java
@Bean
public Consumer<OrderCreated> ordersConsumer(OrderService service) {
    return service::handle;
}
~~~

With the function named `ordersConsumer`, the default input binding is:

~~~text
ordersConsumer-in-0
~~~

This binding can be configured to read from the `orders` topic:

~~~yaml
spring:
  cloud:
    function:
      definition: ordersConsumer
    stream:
      bindings:
        ordersConsumer-in-0:
          destination: orders
          group: order-service
          content-type: application/json
~~~

Pause/resume calls must use the binding name, not the topic name or consumer group. If the application renames the binding via `spring.cloud.stream.function.bindings`, use the configured alias name. For explicitly created bindings not tied to a function, the binding name may also differ from the `in-0`/`out-0` convention.

When a function has multiple inputs, each input binding has its own lifecycle. You can pause one input without necessarily stopping other bindings in the same application.

## 4. Controlling Bindings with BindingsLifecycleController

Since Spring Cloud Stream 3.1, `BindingsLifecycleController` is registered as a bean so applications can manage individual binding lifecycles. Its API exposes `pause`, `resume`, `stop`, and `start`.

Example creating a consumer control service:

~~~java
import org.springframework.cloud.stream.binding.BindingsLifecycleController;
import org.springframework.stereotype.Service;

@Service
public class OrdersConsumerControl {

    private static final String BINDING_NAME = "ordersConsumer-in-0";

    private final BindingsLifecycleController bindings;

    public OrdersConsumerControl(
            BindingsLifecycleController bindings) {
        this.bindings = bindings;
    }

    public void pause() {
        bindings.pause(BINDING_NAME);
    }

    public void resume() {
        bindings.resume(BINDING_NAME);
    }

    public void stop() {
        bindings.stop(BINDING_NAME);
    }

    public void start() {
        bindings.start(BINDING_NAME);
    }
}
~~~

The application can call this service from an internal admin API, an orchestration workflow, or a business condition. Never grant arbitrary external requests permission to pause/resume bindings; enforce access control and audit who or what workflow triggered the action.

To set state generically, the controller also supports `changeState` with `BindingsLifecycleController.State.PAUSED`, `RESUMED`, `STOPPED`, and `STARTED`.

### Inspecting Binding State

`BindingsLifecycleController` can query binding states. In current versions, query results may include one or more `Binding` objects corresponding to lifecycle instances. Each binding exposes details such as whether it is running or paused. When a binding uses concurrency, inspect the state of its instances rather than checking only a single application-level flag.

A safe control workflow should:

1. Confirm the binding exists and is running.
2. Issue the pause or resume request.
3. Observe `ConsumerPausedEvent` or `ConsumerResumedEvent`, or query state to confirm the transition.
4. Log the binding name, timestamp, reason, and requesting user/flow.

Do not treat the return of the `pause` method as proof that all consumer threads stopped receiving records at the exact instant of the call. Effective state is applied according to the listener container lifecycle.

## 5. Controlling via the Actuator Endpoint

To control bindings from operational tooling or management systems, you can use the `bindings` Actuator endpoint.

Actuator and a web runtime dependency are required:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
~~~

If the application uses WebFlux, use `spring-boot-starter-webflux` instead of the web MVC starter.

Expose the `bindings` endpoint:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,bindings
~~~

After the application starts, list bindings:

~~~http
GET /actuator/bindings
~~~

Inspect a single binding's state:

~~~http
GET /actuator/bindings/ordersConsumer-in-0
~~~

Pause the consumer:

~~~bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{"state":"PAUSED"}' \
  http://localhost:8080/actuator/bindings/ordersConsumer-in-0
~~~

Resume consumption:

~~~bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{"state":"RESUMED"}' \
  http://localhost:8080/actuator/bindings/ordersConsumer-in-0
~~~

Stop the binding completely:

~~~bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{"state":"STOPPED"}' \
  http://localhost:8080/actuator/bindings/ordersConsumer-in-0
~~~

Restart the binding:

~~~bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{"state":"STARTED"}' \
  http://localhost:8080/actuator/bindings/ordersConsumer-in-0
~~~

Because the `bindings` endpoint allows remote lifecycle control, it must be protected by Spring Security, an administrative network, or equivalent authentication. Never expose pause/resume endpoints to the public internet or general application users. Expose only necessary endpoints and write audit logs for administrative actions.

## 6. Which Binders Support PAUSED and RESUMED?

Pause/resume support depends on the binder and underlying messaging technology. Current Spring Cloud Stream documentation explicitly notes that Kafka and Solace support `PAUSED`/`RESUMED`. Never assume every binder supports these two states.

| Binder | Pause/Resume Binding | Notes |
|---|---|---|
| Apache Kafka binder | Yes | Consumer continues polling while paused to avoid rebalances from temporarily halting reads. |
| Solace binder | Yes | Per the pause/resume capabilities of the binder and underlying broker. |
| RabbitMQ binder | Does not support `PAUSED`/`RESUMED` under the current common binding lifecycle. | Use Rabbit-binder-specific throttling/control mechanisms if needed. |
| Pulsar binder | Not listed as supporting `PAUSED`/`RESUMED` in current binding lifecycle documentation. | Check the API and capabilities of the deployed binder version. |
| Kafka Streams binder | Does not support `PAUSED`/`RESUMED` | This binder supports `STARTED` and `STOPPED` for binding visualization/control. |

In particular, the Kafka binder and the Kafka Streams binder are two different binders. The Kafka Streams binder currently supports only `STARTED` and `STOPPED` lifecycle states; do not extrapolate regular Kafka binder pause/resume examples to assume a Kafka Streams topology can be paused at the binding level.

If `PAUSED` or `RESUMED` is invoked on an unsupported binder, the framework may log a warning without performing the expected action. Always check documentation for your exact binder and dependency version.

## 7. Monitoring Idle Consumers with ListenerContainerIdleEvent

A consumer may be healthy yet receive no records for a period of time. This can happen when the topic has no new data, the producer stopped publishing, or the consumer is subscribed to the wrong destination. To observe this condition, the Kafka binder can configure `idleEventInterval`.

This property sits under the binding's Kafka consumer properties:

~~~yaml
spring:
  cloud:
    function:
      definition: ordersConsumer
    stream:
      bindings:
        ordersConsumer-in-0:
          destination: orders
          group: order-service
      kafka:
        bindings:
          ordersConsumer-in-0:
            consumer:
              idle-event-interval: 30000
~~~

The value is in milliseconds. This example instructs the listener container to publish a `ListenerContainerIdleEvent` after roughly 30 seconds without receiving records. The Kafka binder currently defaults `idleEventInterval` to 30,000 ms; you can set a different value based on monitoring needs.

`ListenerContainerIdleEvent` is a Spring application event emitted by the listener container. It carries key fields:

- **listenerId:** identifier of the listener/container emitting the event.
- **idleTime:** duration the container has received no records, in milliseconds.
- **topicPartitions:** list of topic/partitions currently assigned when the event is emitted.
- **paused:** pause status of the consumer when the event was created.

When a record is received again after an idle period, Spring Kafka can emit `ListenerContainerNoLongerIdleEvent`. This event is useful for measuring data wait durations and confirming the consumer has resumed activity.

### Receiving Idle and Active Events

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ListenerContainerIdleEvent;
import org.springframework.kafka.event.ListenerContainerNoLongerIdleEvent;
import org.springframework.stereotype.Component;

@Component
public class KafkaConsumerIdleMonitor {

    @EventListener
    public void onIdle(ListenerContainerIdleEvent event) {
        log.info(
                "Kafka listener {} idle {} ms; partitions={}; paused={}",
                event.getListenerId(),
                event.getIdleTime(),
                event.getTopicPartitions(),
                event.isPaused()
        );
    }

    @EventListener
    public void onActive(ListenerContainerNoLongerIdleEvent event) {
        log.info(
                "Kafka listener {} resumed receiving records; partitions={}",
                event.getListenerId(),
                event.getTopicPartitions()
        );
    }
}
~~~

An application context may receive events from multiple listener containers. If the application has multiple input bindings or concurrency, filter by the appropriate listener ID. The actual ID may be a listener ID or container name; child containers created by concurrency may carry specific suffixes. Log the first event to verify the actual ID before writing filter conditions.

`ListenerContainerIdleEvent` is emitted repeatedly on an interval while the container remains idle. Therefore, handlers should record metrics or state idempotently; avoid firing new alerts on every event if the idle state has not changed.

## 8. Distinguishing Idle from a Non-Responsive Consumer

Idle does not mean broken. A consumer can poll normally while the topic simply has no new records. This differs from a consumer stuck inside `poll()` or unable to communicate with the broker.

| Event | Meaning | Interpretation |
|---|---|---|
| `ListenerContainerIdleEvent` | No records received within `idleEventInterval`. | Can be normal when no new data arrives. |
| `ListenerContainerNoLongerIdleEvent` | A new record arrived after an idle period. | Consumer has returned to active data flow. |
| `ListenerContainerPartitionIdleEvent` | A specific partition received no records during the configured interval. | Useful when some partitions have traffic while others do not. |
| `NonResponsiveConsumerEvent` | Consumer appears blocked inside `poll()`. | Investigate broker connectivity, poll timeout, networking, and threads. |
| `ConsumerPausedEvent` | Consumer/container transitioned to paused state. | Confirms the pause operation took effect. |
| `ConsumerResumedEvent` | Consumer/container transitioned to resumed state. | Confirms the consumer resumed receiving. |

If a consumer never returns from `poll()`, the container cannot emit a normal idle event because it never completes a poll cycle to check for empty records. Spring Kafka provides `NonResponsiveConsumerEvent` to signal an unresponsive poll according to container monitoring thresholds.

Therefore, do not use idle events as a sole health check. Combine:

- Binding lifecycle state.
- Consumer lag and backlog per partition.
- Time since the last record received.
- Poll count or consumer thread status.
- Connection state and binder health indicator.
- Error logs for authentication, authorization, timeouts, or rebalances.

## 9. Conditional Auto-Resume

An application can automatically resume when operational conditions allow. For instance, a consumer is paused while a downstream service is overloaded; once monitoring confirms the downstream service has recovered, the application resumes the binding.

You can combine idle events with a dedicated control policy:

~~~java
@Component
public class OrdersConsumerAutoResume {

    private static final String BINDING_NAME = "ordersConsumer-in-0";
    private static final String LISTENER_ID_PREFIX = "ordersConsumer-in-0";

    private final BindingsLifecycleController bindings;
    private final ResumePolicy resumePolicy;

    public OrdersConsumerAutoResume(
            BindingsLifecycleController bindings,
            ResumePolicy resumePolicy) {
        this.bindings = bindings;
        this.resumePolicy = resumePolicy;
    }

    @EventListener
    public void onIdle(ListenerContainerIdleEvent event) {
        if (!event.getListenerId().startsWith(LISTENER_ID_PREFIX)) {
            return;
        }

        if (event.isPaused() && resumePolicy.isReadyToResume()) {
            bindings.resume(BINDING_NAME);
        }
    }
}
~~~

`ResumePolicy` is an application business component responsible for confirming resume conditions—such as downstream health checks passing, a circuit breaker closing, or a maintenance window ending. Replace `LISTENER_ID_PREFIX` with the actual ID observed from your application's events; when multiple child containers exist, filter by prefix or an explicit naming rule.

Never auto-resume solely because the consumer is idle. Idle can simply be normal when a topic has no traffic. An explicit readiness condition is required to avoid continuous pause/resume flapping or resuming consumption while a dependency is still unhealthy.

If the application event multicaster is configured to run listeners asynchronously, never call methods directly on the Kafka Consumer attached to an event. With Spring Cloud Stream, prefer controlling via `BindingsLifecycleController`; this avoids depending on the thread owning the Kafka Consumer.

## 10. Monitoring Pause and Resume Events

Spring Kafka emits `ConsumerPausedEvent` and `ConsumerResumedEvent` when the container actually transitions state. Listen to these events to record lifecycle transitions:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ConsumerPausedEvent;
import org.springframework.kafka.event.ConsumerResumedEvent;
import org.springframework.stereotype.Component;

@Component
public class KafkaConsumerLifecycleMonitor {

    @EventListener
    public void onPaused(ConsumerPausedEvent event) {
        log.info(
                "Kafka consumer paused; partitions={}",
                event.getPartitions()
        );
    }

    @EventListener
    public void onResumed(ConsumerResumedEvent event) {
        log.info(
                "Kafka consumer resumed; partitions={}",
                event.getPartitions()
        );
    }
}
~~~

Pause/resume events report the partitions involved in the transition. If a binding runs multiple consumer instances, multiple corresponding events may be emitted. Do not count a single event as an application-wide pause without aggregating across containers and partitions.

Useful metrics:

- Pause and resume counts per binding.
- Total duration a binding spends paused.
- Listener container idle duration.
- Transitions from idle back to receiving records.
- Consumer lag before, during, and after a pause.
- Backlog growth while paused and drain rate after resume.
- Unexpected rebalance counts.

When pausing to shed load, monitor both backlog accumulation rate and post-resume consumption rate. If producers generate data much faster than single-consumer capacity, you may need to scale concurrency or replicas after recovery.

## 11. Testing Pause, Resume, and Idle Events

Tests should use a real test Kafka broker to verify polling, partition assignment, and backlog behavior. The Test Binder can test Spring Cloud Stream-level logic, but does not fully simulate Kafka pause/resume and rebalancing.

### Pause and Resume Scenario

1. Start Kafka and the application with input binding `ordersConsumer-in-0`.
2. Send several records and verify normal consumer processing.
3. Call `BindingsLifecycleController.pause()` or Actuator with state `PAUSED`.
4. Verify the consumer emits `ConsumerPausedEvent`.
5. Send additional records while the binding is paused.
6. Verify the application does not process new records during the pause window.
7. Call resume and verify `ConsumerResumedEvent`.
8. Verify the backlog is consumed and progress continues by offset.
9. Inspect group membership to verify pausing did not trigger a rebalance merely from halting reads.

### Test Matrix

| Scenario | Setup | Expected Outcome |
|---|---|---|
| Pause binding | Call `controller.pause(bindingName)`. | Binding transitions to paused; consumer stops fetching new records. |
| Resume binding | Call `controller.resume(bindingName)`. | Consumer resumes receiving records. |
| Stop binding | Call `controller.stop(bindingName)`. | Container stops and the group may rebalance. |
| Actuator pause | POST state `PAUSED`. | Endpoint controls the exact named binding. |
| Actuator resume | POST state `RESUMED`. | Binding resumes receiving data. |
| Idle event | Send no records for longer than `idleEventInterval`. | `ListenerContainerIdleEvent` is emitted. |
| No longer idle | Send a record after the listener became idle. | `ListenerContainerNoLongerIdleEvent` is emitted. |
| Partition idle | One partition has no records for the configured interval. | Partition idle event identifies the exact topic/partition. |
| Non-responsive poll | Simulate a blocked poll or unresponsive broker in a suitable test environment. | Unresponsive monitoring alert/event fires per configuration. |
| Multiple bindings | Application has two input bindings. | Pausing one binding does not unexpectedly stop the other binding. |
| Multiple replicas | Run a consumer group with multiple instances. | Track state and events per container/partition. |
| Unsupported binder | Attempt `PAUSED` on an unsupported binder. | Application logs a warning and does not assume it paused. |

### Checking Backlog and Offsets

In tests, record sent count, processed count, and consumer lag before pausing. During the pause, producers keep writing so lag may rise. After resuming, verify the consumer catches up and lag drains.

Do not expect offsets to be strictly contiguous in every topic; compaction, transactions, and log mechanics can create observable gaps. Verify actual processed record counts and commit progress rather than inferring data loss solely from a skipped offset number.

## 12. Common Pitfalls

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `PAUSED` has no effect | Binder does not support pause/resume or wrong binding name used. | Confirm regular Kafka binder is in use and verify binding name. |
| A few records still process after pause | Records already returned from the preceding poll are finishing. | Wait for the current poll cycle to finish and check `ConsumerPausedEvent` timing. |
| Stop causes unintended rebalances | Used `STOPPED` when only temporary pause was needed. | Use `PAUSED` when you need to keep the consumer in the group. |
| Resume receives no data | Wrong binding name, container not resumed, or topic has no new records. | Check lifecycle events, binding state, and backlog. |
| Idle event never appears | `idleEventInterval` not configured or listener not bound. | Check Kafka consumer extended properties and input binding. |
| Idle events fire continuously | Topic has no records or `idleEventInterval` is too short. | Treat as observational state; lengthen interval or reduce repetitive logging. |
| Consumer is stuck with no idle event | `poll()` never returns so the container cannot detect cycle-based idle state. | Monitor `NonResponsiveConsumerEvent`, poll timeouts, and broker connectivity. |
| Auto-resume triggers too early | Policy checks only idle without verifying downstream readiness. | Use `ResumePolicy` or a reliable recovery signal. |
| Event listener acts on wrong binding | Single context receives events from multiple containers. | Filter by actual listener ID / container ID and corresponding binding. |
| Kafka Streams binder fails to pause | Confusing regular Kafka binder capabilities with Kafka Streams binder. | Use `STARTED`/`STOPPED` per Kafka Streams binder capabilities. |

When investigating, check in order: binder type, binding name, lifecycle state, pause/resume events, `idleEventInterval`, listener ID, partition assignment, and consumer lag. Distinguish a legitimately idle consumer from a consumer unresponsive inside `poll()` before restarting or modifying the group.

## 13. Pre-Deployment Checklist

- [ ] Exact input binding to control is identified.
- [ ] `PAUSED`/`RESUMED` used on regular Kafka binder for temporary pauses.
- [ ] `STOPPED`/`STARTED` used when stopping and restarting the container is required.
- [ ] Confirmed binder and version support `PAUSED`/`RESUMED`.
- [ ] Backlog, retention, and post-resume drain rate accounted for.
- [ ] `idleEventInterval` enabled on bindings requiring idle monitoring.
- [ ] Event listeners filter by exact listener/container ID.
- [ ] Normal idle distinguished from `NonResponsiveConsumerEvent`.
- [ ] Auto-resume policy enforces explicit recovery conditions.
- [ ] Actuator endpoints protected with authentication and authorization.
- [ ] Logs/metrics cover pause, resume, idle, backlog, and rebalances.
- [ ] Integration tests verify consumer resumes from expected progress after resume.

Spring Cloud Stream lets you control the lifecycle of Kafka input bindings via `BindingsLifecycleController` or Actuator. Pausing keeps the consumer polling to avoid rebalances from temporarily halting reads; stopping shuts down the container and can cause the group to rebalance. `idleEventInterval` along with Spring Kafka events helps observe listeners receiving no data, becoming active again, or becoming unresponsive in `poll()`. Combining binding controls with backlog monitoring, container state, and recovery conditions allows applications to pause and resume Kafka consumption safely and deterministically.

## References

- [Spring Cloud Stream — Pausing and Resuming the Consumer](https://docs.spring.io/spring-cloud-stream/reference/5.0/kafka/kafka-binder/pause_resume.html)
- [Spring Cloud Stream — Binding Visualization and Control](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding_visualization_control.html)
- [Spring Cloud Stream — Kafka Binder Reference Guide](https://docs.spring.io/spring-cloud-stream-binder-kafka/docs/current/reference/html/spring-cloud-stream-binder-kafka.html)
- [Spring for Apache Kafka — Pausing and Resuming Listener Containers](https://docs.spring.io/spring-kafka/reference/kafka/pause-resume.html)
- [Spring for Apache Kafka — Application Events](https://docs.spring.io/spring-kafka/reference/kafka/events.html)
