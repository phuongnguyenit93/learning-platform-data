# Starting, Stopping Bindings, and Lifecycle Control Limitations

Kafka Streams processors in Spring Cloud Stream typically start automatically alongside the Spring Boot application. In operations, you sometimes need to delay processing until state stores finish restoring, stop a processor during maintenance, or re-enable it once configuration and resources are ready. The Kafka Streams Binder provides processor-level lifecycle control through bindings, Spring Boot Actuator, and programmatic APIs.

An important point is that Kafka Streams bindings are not completely independent like regular message-channel bindings. Input and output bindings belonging to the same function are typically backed by the same `StreamsBuilderFactoryBean` and the same `KafkaStreams` instance. Therefore, calling stop on one binding of a function stops that entire processor; it does not merely pause a single topic. In addition, the Kafka Streams Binder only supports two control states: `STARTED` and `STOPPED`. `PAUSED` and `RESUMED` states are not supported through the binder's binding lifecycle.

## 1. Lifecycle Layers to Distinguish

In a Spring Cloud Stream application using Kafka Streams, several components share lifecycles:

| Component | Role | How to Control |
|---|---|---|
| Spring Boot application | JVM, Spring context, and beans | Start/stop the process or context |
| Kafka Streams processor | A topology managed by `StreamsBuilderFactoryBean` | `StreamsBuilderFactoryManager` or binding lifecycle |
| Input/output binding | Logical connection point between a function and Kafka topics | `BindingsLifecycleController` or Actuator |
| Kafka consumer group/application ID | Consumption progress, partition distribution, and processor state | Kafka Streams configuration; not a binding start/stop button |

A function of type `Consumer<KStream<...>>` typically has an input binding named `functionName-in-0`. A `Function<KStream<...>, KStream<...>>` typically has input `functionName-in-0` and output `functionName-out-0`. Binding names are used when configuring destinations and invoking control endpoints.

Example:

~~~java
@Bean
Consumer<KStream<String, OrderCreated>> processOrders() {
    return orders -> orders.foreach((key, event) ->
        orderService.record(event));
}
~~~

The default input binding is `processOrders-in-0`. For a processor with both input and output:

~~~java
@Bean
Function<KStream<String, OrderCreated>,
         KStream<String, OrderSummary>> summarizeOrders() {
    return orders -> orders.mapValues(event ->
        new OrderSummary(event.orderId(), event.total()));
}
~~~

The two default bindings are `summarizeOrders-in-0` and `summarizeOrders-out-0`. Both belong to the same `summarizeOrders` processor function.

## 2. Default Lifecycle: Processors Auto-Start

When the Spring context starts, the Kafka Streams Binder creates topologies from function beans, creates corresponding bindings, and starts Kafka Streams processors per default configuration. The processor joins its consumer group, receives partitions, restores state stores if present, and begins processing records once ready.

Manual starting is unnecessary in normal cases. Let the binder manage the lifecycle so Spring can shut down processors cleanly along with the application context lifecycle.

A processor with a large state store may need time to restore from its changelog topic before transitioning to `RUNNING`. If restoration takes a long time during startup, deployment platform readiness/liveness probes may misjudge the application as unhealthy and restart it repeatedly. In that case, you can decouple Spring Boot startup from processor startup.

## 3. Observing Binding State via Actuator

Spring Cloud Stream provides the `bindings` endpoint to list bindings and control their lifecycle. You need Spring Boot Actuator and a web runtime:

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

If the application uses WebFlux, you can use `spring-boot-starter-webflux` instead of `spring-boot-starter-web`.

Expose the endpoint:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: bindings
~~~

List bindings:

~~~bash
curl http://localhost:8080/actuator/bindings
~~~

The response may include fields such as:

~~~json
[
  {
    "bindingName": "summarizeOrders-in-0",
    "group": "summarizeOrders-applicationId",
    "pausable": false,
    "state": "running",
    "paused": false,
    "input": true
  },
  {
    "bindingName": "summarizeOrders-out-0",
    "group": "summarizeOrders-applicationId",
    "pausable": false,
    "state": "running",
    "paused": false,
    "input": false
  }
]
~~~

Exact details depend on the binder version and binding. With the Kafka Streams Binder, `pausable` is usually `false` because the binder does not support `PAUSED`/`RESUMED`. The `state` field reflects the binding state managed by Spring Cloud Stream and does not replace all internal states of `KafkaStreams`.

You can inspect a specific binding at `/actuator/bindings/{bindingName}`. Use the binding name derived from the function definition; do not substitute the topic name unless they happen to be identical.

## 4. Stopping a Processor via Actuator

Send a `POST` with state `STOPPED`:

~~~bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{"state":"STOPPED"}' \
  http://localhost:8080/actuator/bindings/summarizeOrders-in-0
~~~

Once the processor stops, its topology stops receiving and processing records. Unprocessed records remain in Kafka subject to topic retention and compaction policies; when the processor restarts, Kafka Streams resumes from committed offsets and restores state per its application ID/state store configuration.

Do not treat `STOPPED` as deleting topics, deleting consumer groups, or resetting offsets. This is a binder-managed processor stop operation. Resetting offsets or replaying from the beginning is a separate operational procedure.

## 5. Restarting a Processor

Send a `POST` with state `STARTED`:

~~~bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{"state":"STARTED"}' \
  http://localhost:8080/actuator/bindings/summarizeOrders-in-0
~~~

The Kafka Streams processor restarts. It may need to rejoin the group, receive partitions, and restore local state before normal processing resumes. The `STARTED` command requests startup; do not treat a successful HTTP response as proof that all state stores have finished restoring and the processor is `RUNNING`. Watch health indicators, Kafka Streams state, lag, and restore logs to confirm the processor is truly ready.

## 6. Limitation: Kafka Streams Binder Only Supports STARTED and STOPPED

Spring Cloud Stream defines a general binding lifecycle API with `STARTED`, `STOPPED`, `PAUSED`, and `RESUMED` states. However, actual support depends on the binder.

For the Kafka Streams Binder:

| Requested State | Supported | Meaning |
|---|---|---|
| `STARTED` | Yes | Starts the processor |
| `STOPPED` | Yes | Stops the processor |
| `PAUSED` | No | Cannot use binding lifecycle to pause a consumer while keeping the processor in a paused state |
| `RESUMED` | No | No corresponding resume operation after `PAUSED` |

Do not use `PAUSED`/`RESUMED` with the Kafka Streams Binder assuming parity with the Kafka message-channel binder. If processing must be halted temporarily, you can stop the processor and restart it later; account for rebalances, state restoration, and the impact of other processors continuing to run.

## 7. One Function with Multiple Bindings Has Only One Processor Lifecycle

This is a critical limitation when a function has multiple inputs or outputs. Example:

~~~java
@Bean
BiFunction<KStream<String, OrderCreated>,
           KTable<String, Customer>,
           KStream<String, EnrichedOrder>> enrichOrders() {
    return (orders, customers) -> orders.leftJoin(
        customers,
        (order, customer) -> new EnrichedOrder(order, customer)
    );
}
~~~

The function above has two input bindings:

- `enrichOrders-in-0`
- `enrichOrders-in-1`

and one output binding:

- `enrichOrders-out-0`

All bindings of the same function are backed by the same `StreamsBuilderFactoryBean`. Consequently, sending `STOPPED` to `enrichOrders-in-0`, `enrichOrders-in-1`, or `enrichOrders-out-0` controls the same `enrichOrders` processor. You cannot use the binding endpoint to stop only one input while keeping the same topology processing the remaining input.

If independent lifecycles are required, split them into separate functions/processors so each processor has its own factory bean and appropriate application ID. Do not split purely for lifecycle control if the topology relies on joins or shared state; splitting can alter semantics, repartitioning, and pipeline latency.

## 8. Controlling via BindingsLifecycleController

In addition to REST endpoints, Spring Cloud Stream registers a `BindingsLifecycleController` bean for programmatic binding control:

~~~java
import org.springframework.cloud.stream.binding.BindingsLifecycleController;
import org.springframework.stereotype.Component;

@Component
public class ProcessorLifecycle {

    private final BindingsLifecycleController controller;

    public ProcessorLifecycle(BindingsLifecycleController controller) {
        this.controller = controller;
    }

    public void stopOrdersProcessor() {
        controller.stop("summarizeOrders-in-0");
    }

    public void startOrdersProcessor() {
        controller.start("summarizeOrders-in-0");
    }

    public boolean isRunning() {
        var binding = controller.queryState("summarizeOrders-in-0");
        return binding != null && binding.isRunning();
    }
}
~~~

The convenience `start`/`stop` methods correspond to changing binding state. You can use `changeState` with `State.STARTED` or `State.STOPPED` to specify states explicitly. This API is useful when an in-application condition governs when a processor starts or stops, such as completion of a business initialization step.

Do not call `start`/`stop` repeatedly per message or per request. Lifecycle operations act at the processor level and can cause Kafka Streams to close/reopen, rejoin consumer groups, and restore state. Use a coordinator with explicit state and prevent multiple threads from mutating lifecycle state concurrently without synchronization.

## 9. Delaying Auto-Start for All Processors

If you want Spring Boot to start first and only start Kafka Streams once the application is ready, set:

~~~yaml
spring:
  kafka:
    streams:
      auto-startup: false
~~~

This property disables auto-start for all Kafka Streams processors in the application. When ready to start, use `StreamsBuilderFactoryManager` provided by the Kafka Streams Binder:

~~~java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.cloud.stream.binder.kafka.streams.StreamsBuilderFactoryManager;

@Configuration
public class KafkaStreamsStartupConfiguration {

    @Bean
    ApplicationRunner startKafkaStreamsProcessors(
            StreamsBuilderFactoryManager manager) {
        return args -> manager.start();
    }
}
~~~

`StreamsBuilderFactoryManager` manages the multiple `StreamsBuilderFactoryBean` instances created by the binder. When using the Kafka Streams Binder, control them through this manager instead of grabbing internal `KafkaStreams` objects directly or manually declaring `StreamsBuilderFactoryBean`. The binder retains ownership of factory beans and associated bindings.

The pattern above starts all managed processors. If the application has multiple processors and you only want to start a subset, do not use `manager.start()` for selective control; use `auto-startup` on individual consumer bindings and control the corresponding processor through binding lifecycle.

## 10. Delaying Auto-Start for a Single Processor

You can set `auto-startup=false` on an input consumer binding:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        reconcileOrders-in-0:
          destination: orders.events
          group: order-reconciler
          consumer:
            auto-startup: false
~~~

The application starts and other processors still auto-start per their configurations. The `reconcileOrders` processor does not start until triggered with `STARTED` via Actuator or `BindingsLifecycleController`.

For a function with multiple inputs, setting `auto-startup=false` on one input binding suffices to delay the processor because the inputs share one factory bean. Setting it on all input bindings can make configuration clearer to read. This property only applies to consumer bindings; setting it on an output binding does not disable processor auto-start.

## 11. Starting a Delayed Processor

After setting `auto-startup=false`, you can start it via Actuator:

~~~bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{"state":"STARTED"}' \
  http://localhost:8080/actuator/bindings/reconcileOrders-in-0
~~~

Or via `BindingsLifecycleController`:

~~~java
controller.start("reconcileOrders-in-0");
~~~

This pattern lets the application complete other startup steps before the processor joins the consumer group. One use case is a large state store requiring restore time. However, design readiness probes accordingly: the application process may be alive while the processor is not yet handling messages. Liveness should reflect whether the process needs restarting; readiness should reflect whether the processor is ready for traffic per deployment requirements.

## 12. Monitoring Health When Processors Are Stopped

The Kafka Streams Binder provides a binder-level property:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          binder:
            include-stopped-processors-for-health-check: true
~~~

By default, `includeStoppedProcessorsForHealthCheck` is `false`. Processors stopped via Actuator are excluded from the health check. Set it to `true` if you want health checks to account for `STOPPED` processors.

Choose the policy based on how your application uses `STOPPED`:

- If stopping is an intentional maintenance state, you may not want that processor to mark the entire application's health as `DOWN`.
- If the processor must always be running to fulfill core functionality, ignoring a stopped processor can mask an unintended outage; enable the check and configure appropriate alerts.

Health indicators and binding state answer different questions. A running binding indicates the lifecycle was started; health and `KafkaStreams` state indicate whether the processor is functioning normally, finished restoring, and actively processing.

## 13. Stopping a Binding Does Not Delete Local State

When stopping a Kafka Streams binding, local state stores are not deleted by default. This has been Spring Kafka's default behavior since version 2.7 and is preserved by the Kafka Streams Binder.

This helps during brief maintenance: the processor can be restarted and reuse existing local state while Kafka Streams syncs deltas from the changelog. Never delete state directories manually while a processor is running or while another instance is using the same state directory.

If you need to control local state cleanup on start/stop, the Kafka Streams Binder detects a `CleanupConfig` bean in the application context. This bean lets you configure cleanup on start, on stop, or never. Only enable cleanup once you understand its impact on restore times and changelog availability; wiping local state typically forces the processor to rebuild state from Kafka.

Stopping and restarting a binding also does not reset committed offsets. The regular Kafka message-channel binder's `resetOffsets` consumer property has no effect on the Kafka Streams Binder. If you need to replay from the beginning, plan offsets/application ID/state stores separately and execute a controlled operational runbook.

## 14. Distinguishing Stop/Start from Closing KafkaStreams Directly

`KafkaStreams` exposes `start()` and `close()` methods. However, once a `KafkaStreams` instance has been closed, `start()` cannot be called on that same instance to reuse it; a new `KafkaStreams` instance must be created.

Spring for Apache Kafka provides `StreamsBuilderFactoryBean` to manage creating and closing `KafkaStreams`. The Kafka Streams Binder layers `StreamsBuilderFactoryManager` on top to manage multiple factory beans across processors. When using the binder, control lifecycles through the manager or binding controller.

Do not inject the internal `KafkaStreams` object and call `close()` directly while the binder is managing the binding. Doing so can desynchronize Spring binding state from `KafkaStreams` state. Use the lifecycle APIs supported by the binder to stop/start and let Spring manage shutdown.

## 15. Processor State and Restore Time

After a `STARTED` command, a processor goes through phases such as initialization, group join, partition assignment, state store restoration, and finally steady-state running. For stateless topologies, readiness time can be brief. For topologies with large state, restoration can take many minutes.

Do not rely solely on the HTTP response from the endpoint. Observe:

- Binding state via `/actuator/bindings`.
- `KafkaStreams` state and health indicators.
- State restoration start/end logs.
- Consumer lag and processing rate.
- Rebalances and partition assignments.
- Local state store/changelog status.

If you need to determine when a processor is business-ready, build readiness conditions on these signals rather than relying solely on the binding entering `STARTED`.

## 16. Common Operational Limitations

| Need | Appropriate Approach | Limitation to Remember |
|---|---|---|
| View running bindings | `GET /actuator/bindings` | Requires Actuator, web runtime, and exposed endpoint |
| Stop processor | `POST` state `STOPPED` | Stops the entire processor sharing the factory bean |
| Start processor | `POST` state `STARTED` | May require time to join group and restore state |
| Pause/resume without stopping | Not supported by Kafka Streams Binder via binding lifecycle | `PAUSED`/`RESUMED` are unavailable |
| Delay all processors | `spring.kafka.streams.auto-startup=false` and `StreamsBuilderFactoryManager` | `manager.start()` starts all managed processors |
| Delay one processor | `consumer.auto-startup=false` on an input binding | Do not set on output bindings |
| Programmatic control | `BindingsLifecycleController` | Invoke on operational events, not continuously |
| Clean local state | `CleanupConfig` | Can increase restoration time |
| Replay from beginning | Dedicated offset/state procedure | Starting a binding does not reset offsets |

## 17. Lifecycle Testing

Verify the following behaviors in integration tests:

1. Start the application and confirm processors default to running state.
2. Call Actuator `STOPPED` and confirm the processor stops consuming/processing records.
3. Send additional records while stopped; verify records remain in Kafka per retention/compaction and are processed when the processor restarts.
4. Call `STARTED` and wait for the processor to restore state and join the group before asserting readiness.
5. For a function with two inputs and one output, stop via the first input name and verify the whole processor stops; start via the output binding and verify the processor runs again.
6. Verify `PAUSED`/`RESUMED` are not valid states for the Kafka Streams Binder.
7. Set global `auto-startup=false` and verify processors have not started prior to `manager.start()`.
8. Set consumer `auto-startup=false` on one processor and verify another processor still auto-starts.
9. Check health when a processor is `STOPPED` with `include-stopped-processors-for-health-check` set to `false` and `true`.
10. Stop/start a processor with a state store and verify local state is retained under default configuration.
11. Test graceful application shutdown so Kafka Streams closes with the Spring lifecycle.

The Test Binder can verify wiring and some application logic, but does not fully simulate rebalances, partition assignments, state restoration, or the Kafka Streams lifecycle. Use a real Kafka broker or Testcontainers for integration tests, especially for stateful topologies.

## 18. Securing Control Endpoints

The Bindings Actuator can stop or start processors handling production data. Expose only necessary endpoints and place them behind authentication/authorization, an admin network, or an internal API gateway. Never expose all Actuator endpoints to the public internet just to enable the `bindings` endpoint.

If binding responses contain extended configuration with sensitive values, use Spring Boot's appropriate sanitization mechanisms. Never log credentials, SASL JAAS configs, SSL keys, or secrets in operational logs.

## 19. Deployment Checklist

- [ ] Identified actual binding names from function definitions.
- [ ] Identified which bindings share a single processor/`StreamsBuilderFactoryBean`.
- [ ] Added Actuator and web runtime if controlling via REST.
- [ ] Exposed the `bindings` endpoint in a controlled manner.
- [ ] Secured `STOPPED`/`STARTED` operations with authentication and authorization.
- [ ] Accounted for Kafka Streams Binder supporting only `STARTED`/`STOPPED`.
- [ ] Selected global `auto-startup` or selective consumer `auto-startup` as needed.
- [ ] Used `StreamsBuilderFactoryManager` when managing auto-start across all processors.
- [ ] Designed readiness checks for state store restoration windows.
- [ ] Decided whether health checks should include `STOPPED` processors.
- [ ] Understood local state is not deleted by default on stop.
- [ ] Defined a separate procedure if offset resets or state rebuilds are needed.
- [ ] Tested stop/start, multi-input functions, state restoration, and graceful shutdown against real Kafka.

The Spring Cloud Stream Kafka Streams Binder enables observing and controlling processor lifecycles through bindings. Use Actuator or `BindingsLifecycleController` to stop/start; use `StreamsBuilderFactoryManager` to delay auto-start for all processors, or `consumer.auto-startup` to target a single processor. Always remember that bindings of the same function share one lifecycle, the binder does not support `PAUSED`/`RESUMED`, and stopping neither wipes local state nor resets offsets.

## References

- [Spring Cloud Stream — Binding Visualization and Control in Kafka Streams Binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/binding-visualization-and-control-in-binder.html)
- [Spring Cloud Stream — Manually Starting Kafka Streams Processors](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/manually-starting-processors.html)
- [Spring Cloud Stream — Manually Starting Kafka Streams Processors Selectively](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/manually-starting-processors-selectively.html)
- [Spring Cloud Stream — Binding Visualization and Control](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding_visualization_control.html)
- [Spring for Apache Kafka — Kafka Streams Lifecycle](https://docs.spring.io/spring-kafka/reference/streams.html)
