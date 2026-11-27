# Controlling STARTED, STOPPED, PAUSED, and RESUMED Based on Binder Capabilities

Spring Cloud Stream allows observing and controlling the lifecycle of each binding. Through Actuator or the in-application API, you can start a stopped binding, stop a running binding, pause a consumer, or resume a paused consumer.

The four common states are:

- **STARTED:** the binding is started.
- **STOPPED:** the binding is stopped.
- **PAUSED:** the consumer temporarily stops receiving messages while potentially keeping its connection.
- **RESUMED:** the consumer resumes receiving messages after being paused.

The key point is that **PAUSED/RESUMED depends on whether the binder and underlying component support pausing**. Current Spring Cloud Stream documentation lists the Kafka binder and Solace binder for these two states. The Kafka Streams binder only supports STARTED/STOPPED. Do not assume the RabbitMQ or Pulsar binder supports pause/resume merely because the Actuator endpoint accepts the same state values.

This lesson focuses on the Spring Cloud Stream binding lifecycle in event-driven systems, controlling it via Actuator and the Java API, differences between stop and pause, support scope across binders, and safe operational procedures.

## 1. Where does the binding lifecycle live?

Spring Cloud Stream connects application functions to destinations through bindings and binders. A binding has its own lifecycle, created by the binder at application startup or when a binding is created dynamically.

Function example:

~~~java
@Bean
Consumer<OrderCreated> processOrder(OrderService service) {
    return order -> service.process(order);
}
~~~

For a function named `processOrder`, the default input binding is `processOrder-in-0`. That binding connects the consumer to the configured destination, such as a Kafka topic or RabbitMQ queue.

~~~text
Spring Boot application
       |
       v
Spring Cloud Stream binding
  processOrder-in-0
       |
       v
Binder
       |
       v
Broker destination
  orders.created
~~~

The lifecycle controller controls the binding named `processOrder-in-0`. It does not directly control the entire Spring Boot application, does not stop the JVM, and does not alter topic/queue configuration on the broker.

Distinguish three scopes:

| Scope | Example | Controlled by |
|---|---|---|
| Application instance | A JVM or a pod | Process manager, Kubernetes, systemd |
| Spring Cloud Stream binding | `processOrder-in-0` | Binding lifecycle controller / Actuator |
| Broker resource | Kafka topic, Rabbit queue, Pulsar subscription | Broker administration tools |

When stopping one binding, the application instance can still remain running, the health endpoint still responds, and other bindings continue operating.

## 2. The four states: STARTED, STOPPED, PAUSED, and RESUMED

| State | Meaning | When to use |
|---|---|---|
| `STARTED` | Start a stopped binding | Re-enable a consumer or producer binding that was STOPPED |
| `STOPPED` | Stop components attached to the binding | Maintenance, config changes requiring restart, or halting the flow |
| `PAUSED` | Temporarily suspend receiving messages on a supported consumer | Pause consumption while keeping connection/partition state |
| `RESUMED` | Resume a PAUSED consumer | Resume receiving messages once operational conditions recover |

There are two pairs of operations:

~~~text
STARTED  <---->  STOPPED
RESUMED  <---->  PAUSED
~~~

Do not mix up the two pairs:

- After `STOPPED`, use `STARTED` to run again.
- After `PAUSED`, use `RESUMED` to continue.
- `STARTED` is not an alias for `RESUMED`.
- `STOPPED` is not an alias for `PAUSED`.

`STARTED` and `STOPPED` are the basic Lifecycle phases. `PAUSED` and `RESUMED` require the consuming component to implement Spring Integration's `Pausable` capability or an equivalent mechanism provided by the binder.

## 3. How is STOPPED different from PAUSED?

This is the most important distinction when operating Kafka consumers.

### STOPPED

When a binding is STOPPED, the component managed by the binding is stopped. With the regular Kafka consumer, the consumer container stops and leaves the consumer group. This can trigger Kafka to perform a partition rebalance to redistribute partitions among the remaining active consumers.

Use STOPPED when you need to fully stop a binding, for example:

- Consumer configuration changes requiring a restart.
- Application maintenance.
- Temporarily taking a binding out of service.
- Preparing for deployment or topology changes.

### PAUSED

When a consumer is PAUSED, it temporarily stops receiving/dispatching records while potentially maintaining its broker connection. With the regular Kafka binder, pause/resume is designed to stop consumption without triggering a partition rebalance.

That is useful when:

- The downstream database is undergoing maintenance.
- You need to pause processing to investigate an incident.
- Processing rate needs to be throttled briefly.
- You want to retain current partition assignments while the consumer rests.

A paused endpoint may still be considered running at the Lifecycle level. Therefore, when checking status, inspect the `paused` or `pausable` flags as well, not just `state=running`.

~~~text
Kafka consumer binding

Running
   |
   | PAUSED
   v
Pause receiving records
Retain consumer/container and assignments
   |
   | RESUMED
   v
Resume receiving records

Running
   |
   | STOPPED
   v
Consumer container stops
May leave consumer group and trigger rebalance
   |
   | STARTED
   v
Consumer starts and rejoins group
~~~

Pausing does not mean the broker stops accepting messages from producers. Producers can keep writing. Backlogs can grow while the consumer is paused. Pausing also does not automatically handle messages already mid-processing in a function; check processing times and binder acknowledgments before acting.

## 4. Which binders support pause/resume?

Spring Cloud Stream provides a common lifecycle API, but actual capabilities are determined by the binder and underlying components.

According to current Spring Cloud Stream documentation:

| Binder / binding type | STARTED / STOPPED | PAUSED / RESUMED | Notes |
|---|---:|---:|---|
| Regular Kafka binder | Yes | Yes, for consumers | Pauses consumer without triggering partition rebalance |
| Kafka Streams binder | Yes | No | Only supports STOPPED and STARTED |
| Solace binder | Yes | Yes per general docs | Check specific Solace version and config |
| RabbitMQ binder | Yes via common lifecycle | Not listed in general docs | Do not assume pause/resume takes effect |
| Pulsar binder | Yes via common lifecycle | Not listed in general docs | Do not assume pause/resume takes effect |
| Custom binder | Depends on implementation | Only if supported | Target component must implement pausable capability |

This table describes capabilities documented by Spring Cloud Stream, not a guarantee that every binder version behaves identically. Cross-check the exact Spring Cloud Stream, binder, and client versions your application uses.

### Regular Kafka binder

The Kafka binder supports pause/resume for consumers. Its dedicated documentation describes using binding lifecycle with `State.PAUSED` and `State.RESUMED`. The goal is to pause consumption without causing partition rebalances.

### Kafka Streams binder

The Kafka Streams binder has separate control documentation. It only supports two lifecycle phases, `STOPPED` and `STARTED`; `PAUSED` and `RESUMED` are not available.

In addition, bindings of the same Kafka Streams function are backed by the same `StreamsBuilderFactoryBean`. Therefore, calling STOPPED/STARTED on either the input or output binding of a function can control the same processor. Do not treat each binding name of a Kafka Streams function as an independent process.

### RabbitMQ and Pulsar

The common lifecycle API allows controlling STARTED/STOPPED. General documentation currently does not list RabbitMQ and Pulsar among binders supporting PAUSED/RESUMED. If dedicated pause functionality is needed, check the documentation for your exact version or test against the deployed binder; do not infer support merely because the REST endpoint accepts the request.

## 5. Enabling the Binding Actuator endpoint

Actuator lets you list bindings, inspect a single binding, and submit state change requests.

It requires the Actuator dependency and a web runtime. Maven example:

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

If the application uses WebFlux, use `spring-boot-starter-webflux` instead of `spring-boot-starter-web`.

Configuration to expose the endpoint:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,bindings
~~~

The bindings endpoint is not necessarily exposed by default. Only add `bindings` to the exposure list when the application actually needs it.

After the application starts, you can access:

~~~text
GET /actuator/bindings
GET /actuator/bindings/{bindingName}
POST /actuator/bindings/{bindingName}
~~~

Example for a binding named `processOrder-in-0`:

~~~bash
curl http://localhost:8080/actuator/bindings
curl http://localhost:8080/actuator/bindings/processOrder-in-0
~~~

The name in the URL is the **binding name**, not necessarily the topic or queue name. For function `processOrder`, the default input binding is `processOrder-in-0`.

## 6. Reading binding state via Actuator

GETting the bindings list helps observe the bindings currently managed:

~~~bash
curl http://localhost:8080/actuator/bindings
~~~

The response may include information such as:

~~~json
[
  {
    "bindingName": "processOrder-in-0",
    "name": "processOrder-in-0",
    "group": "order-projection",
    "pausable": true,
    "state": "running",
    "paused": false,
    "input": true,
    "extendedInfo": {}
  }
]
~~~

Fields to pay attention to:

| Field | Meaning |
|---|---|
| `bindingName` | Binding name in Spring Cloud Stream |
| `name` | Managed binding name |
| `group` | Consumer group or group information provided by the binder |
| `pausable` | Whether the binding supports pause/resume |
| `state` | Lifecycle state, typically running or stopped |
| `paused` | Whether the consumer is currently paused |
| `input` | Whether the binding is an input or output |
| `extendedInfo` | Additional information provided by the binder |

Actual responses may differ by binder and version. For instance, the Kafka Streams binder returns `pausable: false`, `paused: false`, and only provides STARTED/STOPPED.

When wanting to pause, check `pausable` first. If `pausable=false`, do not send PAUSED and assume the consumer stopped receiving messages.

## 7. Controlling state with HTTP POST

Spring Cloud Stream uses the same endpoint to change state. The body is JSON containing a `state` field.

### Stopping a binding

~~~bash
curl -X POST   http://localhost:8080/actuator/bindings/processOrder-in-0   -H "Content-Type: application/json"   -d '{"state":"STOPPED"}'
~~~

### Restarting a binding

~~~bash
curl -X POST   http://localhost:8080/actuator/bindings/processOrder-in-0   -H "Content-Type: application/json"   -d '{"state":"STARTED"}'
~~~

### Pausing a consumer

~~~bash
curl -X POST   http://localhost:8080/actuator/bindings/processOrder-in-0   -H "Content-Type: application/json"   -d '{"state":"PAUSED"}'
~~~

### Resuming a consumer

~~~bash
curl -X POST   http://localhost:8080/actuator/bindings/processOrder-in-0   -H "Content-Type: application/json"   -d '{"state":"RESUMED"}'
~~~

After POSTing, read the binding back:

~~~bash
curl http://localhost:8080/actuator/bindings/processOrder-in-0
~~~

Do not rely solely on the HTTP status of the request to conclude the broker stopped or resumed delivering messages. Confirm the binding state and verify actual consumption behavior.

## 8. Controlling with BindingsLifecycleController

In addition to Actuator, Spring Cloud Stream provides the `BindingsLifecycleController` bean since version 3.1. You can inject this bean into a management service or internal listener.

Example:

~~~java
import org.springframework.cloud.stream.binding.BindingsLifecycleController;
import org.springframework.cloud.stream.binder.Binding;
import org.springframework.stereotype.Service;

@Service
public class StreamBindingOperations {

    private final BindingsLifecycleController lifecycle;

    public StreamBindingOperations(
            BindingsLifecycleController lifecycle) {
        this.lifecycle = lifecycle;
    }

    public boolean isRunning(String bindingName) {
        Binding<?> binding = lifecycle.queryState(bindingName);
        return binding != null && binding.isRunning();
    }

    public void stop(String bindingName) {
        lifecycle.stop(bindingName);
    }

    public void start(String bindingName) {
        lifecycle.start(bindingName);
    }

    public void pause(String bindingName) {
        lifecycle.pause(bindingName);
    }

    public void resume(String bindingName) {
        lifecycle.resume(bindingName);
    }
}
~~~

Convenience methods corresponding to lifecycle operations:

| Method | Effect |
|---|---|
| `queryState(name)` | Retrieve the binding to inspect its state |
| `stop(name)` | Stop the binding |
| `start(name)` | Start a stopped binding |
| `pause(name)` | Pause if the target component supports it |
| `resume(name)` | Resume if the binding is paused and supported |
| `changeState(name, state)` | Change state using the provided lifecycle enum |

Official documentation example:

~~~java
BindingsLifecycleController controller =
    context.getBean(BindingsLifecycleController.class);

Binding<?> binding = controller.queryState("echo-in-0");

if (binding.isRunning()) {
    controller.stop("echo-in-0");
}

// You can use the convenience method:
controller.start("echo-in-0");
~~~

If a binding does not support pause, calling pause does not grant new capabilities to the binder. Check `pausable` and application logs. Never build a management API that returns success when the underlying operation is unsupported.

## 9. Controlling bindings by function name

Default binding names are generated from the function bean name and input/output index.

~~~java
@Bean
Function<Order, Order> normalizeOrder() {
    return order -> order.normalized();
}

@Bean
Consumer<PaymentReceived> processPayment() {
    return payment -> paymentService.process(payment);
}
~~~

Default bindings:

| Function | Binding |
|---|---|
| `normalizeOrder` input | `normalizeOrder-in-0` |
| `normalizeOrder` output | `normalizeOrder-out-0` |
| `processPayment` input | `processPayment-in-0` |

When configuring custom destinations:

~~~yaml
spring:
  cloud:
    function:
      definition: normalizeOrder;processPayment

    stream:
      bindings:
        normalizeOrder-in-0:
          destination: orders.raw

        normalizeOrder-out-0:
          destination: orders.normalized

        processPayment-in-0:
          destination: payments.received
~~~

The binding names remain `normalizeOrder-in-0` or `processPayment-in-0`. Do not send Actuator commands to `orders.raw` if that is only the destination name.

## 10. Manual consumer startup with autoStartup

Input bindings have an `autoStartup` property. By default, consumers start automatically. You can set it to false if the application needs to control when consumption begins.

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder

    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: order-projection
          consumer:
            autoStartup: false
~~~

When `autoStartup=false`, the consumer does not start automatically with the application. Once the application is ready, you can use the binding lifecycle controller or Actuator with state STARTED.

A possible workflow:

1. The application starts and completes dependency checks.
2. Verify database, schema, configuration, and broker permissions.
3. Confirm the instance is ready to process.
4. Send STARTED to the input binding.
5. Monitor backlog, errors, and throughput.

This property applies to consumer bindings. It does not replace Kubernetes readiness/liveness management or application health checks.

## 11. PAUSED and RESUMED on the regular Kafka binder

The regular Kafka binder can pause a consumer without triggering a partition rebalance. This is useful when you want to temporarily halt processing while keeping the consumer in the group.

Example:

~~~bash
curl -X POST http://localhost:8080/actuator/bindings/processOrder-in-0   -H "Content-Type: application/json"   -d '{"state":"PAUSED"}'
~~~

While paused:

- Producers can continue sending records.
- The consumer stops receiving/dispatching new records to the listener.
- Backlog/lag may increase.
- The consumer can maintain its connection and current assignments.
- Processing that started before the pause may take time to finish.

Resuming:

~~~bash
curl -X POST http://localhost:8080/actuator/bindings/processOrder-in-0   -H "Content-Type: application/json"   -d '{"state":"RESUMED"}'
~~~

After resuming, the consumer resumes receiving records from its existing position and committed state. Pausing does not rewind offsets, clear the backlog, or change the consumer group.

The Kafka binder documentation also describes auto-resuming by listening for `ListenerContainerIdleEvent` via `ApplicationListener` or `@EventListener`. The frequency of idle events is controlled by `idleEventInterval`. This is an option when you want an automated rule to resume after consumer idleness; design the resume condition carefully to avoid loops or resuming at the wrong time.

## 12. Kafka Streams binder only supports STARTED and STOPPED

The Kafka Streams binder has its own lifecycle control. Its documentation explicitly states that only two phases are supported:

- `STOPPED`
- `STARTED`

`PAUSED` and `RESUMED` are not available in the Kafka Streams binder.

Function example:

~~~java
@Bean
Consumer<KStream<String, String>> logEvents() {
    return stream -> stream.foreach(
        (key, value) -> log.info("event={}", value)
    );
}
~~~

The default input binding is `logEvents-in-0`. It can be stopped and restarted:

~~~bash
curl -X POST http://localhost:8080/actuator/bindings/logEvents-in-0   -H "Content-Type: application/json"   -d '{"state":"STOPPED"}'

curl -X POST http://localhost:8080/actuator/bindings/logEvents-in-0   -H "Content-Type: application/json"   -d '{"state":"STARTED"}'
~~~

For a Kafka Streams function with multiple bindings, all bindings of that function are backed by the same `StreamsBuilderFactoryBean`. Consequently, a lifecycle operation on one binding can stop or start the processor tied to that function. Re-read the endpoint and check the entire function rather than assuming only an individual input/output was affected.

Do not use PAUSED/RESUMED as a substitute for STARTED/STOPPED on the Kafka Streams binder. If you need to pause topology processing, design a mechanism suited to the Kafka Streams runtime and your version.

## 13. RabbitMQ and Pulsar: verify per binder

Spring Cloud Stream offers a common lifecycle interface, but pause/resume does not automatically exist across every broker.

For RabbitMQ and Pulsar:

- STARTED/STOPPED are controlled through the common binding lifecycle.
- Current Spring Cloud Stream documentation does not list these two binders among those supporting PAUSED/RESUMED.
- If you send PAUSED to an unsupported binding, the framework may log a warning; do not treat that as proof the consumer stopped.
- When you need to stop consumption, use STOPPED if the binder's lifecycle impact is acceptable.
- If you need to pause while preserving subscription/consumer state, verify the binder's native API and supported integration in your running version.

Do not use broker admin commands to delete queues, subscriptions, or consumer groups merely as a workaround for pause. Those actions can discard backlogs, cursors, or acknowledgment state.

## 14. Controlling a binding in a multi-binder application

An application can use multiple binders simultaneously, such as one input reading from Kafka and one output writing to RabbitMQ. Each binding has its own name and can be attached to a different binder.

~~~yaml
spring:
  cloud:
    function:
      definition: enrichOrder

    stream:
      bindings:
        enrichOrder-in-0:
          destination: orders.created
          binder: kafka

        enrichOrder-out-0:
          destination: orders.enriched
          binder: rabbit
~~~

Controlling the input:

~~~bash
curl -X POST http://localhost:8080/actuator/bindings/enrichOrder-in-0   -H "Content-Type: application/json"   -d '{"state":"PAUSED"}'
~~~

This command only performs a pause if the Kafka input binder in use supports it. The Rabbit output binding is not automatically paused alongside the input. If you want to stop the output or the entire function, target the right binding and evaluate the impact of halting publishing.

In multi-binder applications, always inspect binding details before acting. Never infer the binder from a topic name or function name.

## 15. Controlling across multiple instances or pods

The binding lifecycle controller operates within a single instance's application context. If a service runs multiple replicas, a POST to one pod only controls the binding inside that pod.

Example with three replicas:

~~~text
order-projection deployment
  |
  +-- pod A: processOrder-in-0
  +-- pod B: processOrder-in-0
  +-- pod C: processOrder-in-0
~~~

Sending PAUSED to pod A does not pause pod B or pod C. In a Kafka group, the remaining two consumers continue receiving their assigned partitions; consumer A keeps its assignments in a paused state if the binder supports it.

If you need to stop the entire service:

1. Identify all running instances.
2. Send lifecycle commands to each instance or use a control plane capable of fan-out.
3. Confirm the state of each binding.
4. Monitor backlog and in-flight processing.
5. Complete maintenance only when all instances are in the desired state.

Do not send one Actuator call to a load balancer and assume every pod received it. Load balancers typically route a request to a single instance.

In Kubernetes, you can coordinate binding lifecycle with rollout strategies and readiness. However, readiness does not automatically pause bindings; the two mechanisms solve different problems.

## 16. Safe operational procedures

### Pausing for downstream maintenance

With the regular Kafka binder:

1. Check that the binding has `pausable=true`.
2. Record current consumer lag and processing rate.
3. Send PAUSED.
4. Read the binding back to confirm `paused=true`.
5. Monitor rising backlog and in-flight work.
6. Perform downstream maintenance.
7. Confirm the dependency is ready.
8. Send RESUMED.
9. Verify `paused=false`, lag decreasing, and throughput returning.

### Stopping a binding for configuration changes

1. Identify the exact binding name.
2. Evaluate impact on the consumer group and rebalances.
3. Stop or drain in-flight work as supported by the application.
4. Send STOPPED.
5. Confirm the binding is no longer running.
6. Apply configuration changes following your deployment process.
7. Send STARTED or restart the application as planned.
8. Check the binding, consumer group, and backlog.

Do not assume STOPPED means every in-flight message finished or offsets were committed. Check acknowledgment mode, transactions, retries, and processing durations for your specific binder.

## 17. Securing the Actuator binding endpoint

The POST endpoint can halt or resume message consumption. It is an administrative API with direct operational impact.

Guidelines:

- Expose the bindings endpoint only when necessary.
- Do not expose all Actuator endpoints just to enable binding control.
- Restrict access via Spring Security or platform authentication layers.
- Use a network policy, dedicated management port, or internal network for management endpoints.
- Grant permissions only to operations groups authorized to change lifecycle state.
- Record audit logs including binding name, old state, new state, actor, timestamp, and reason.
- Protect the endpoint against forged or duplicate requests.
- Inspect extended binding properties for sensitive information.

Binding Actuator can return extra configuration details. Spring Cloud Stream documentation recommends using Spring Boot's `SanitizingFunction` to mask sensitive values such as `sasl.jaas.config` or SSL details.

Example bean masking a SASL value:

~~~java
import org.springframework.boot.actuate.endpoint.SanitizingFunction;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ActuatorSanitizationConfiguration {

    @Bean
    SanitizingFunction sanitizingFunction() {
        return data -> {
            if ("sasl.jaas.config".equals(data.getKey())) {
                return data.withValue("******");
            }
            return data;
        };
    }
}
~~~

Audit any other sensitive keys used by your application. Never write tokens, passwords, or private keys into logs when controlling bindings.

## 18. Testing binding lifecycle

Tests should verify both in-application state and message reception behavior.

### Testing STARTED and STOPPED

You can retrieve the controller from the Spring context:

~~~java
BindingsLifecycleController controller =
    context.getBean(BindingsLifecycleController.class);

Binding<?> binding = controller.queryState("processOrder-in-0");

assertThat(binding.isRunning()).isTrue();

controller.stop("processOrder-in-0");

Binding<?> stopped = controller.queryState("processOrder-in-0");
assertThat(stopped.isRunning()).isFalse();

controller.start("processOrder-in-0");

Binding<?> started = controller.queryState("processOrder-in-0");
assertThat(started.isRunning()).isTrue();
~~~

Example using AssertJ. In real tests, initialize the application context and appropriate binder, and wait asynchronously if the binder needs time to start.

### Testing PAUSED and RESUMED with the Kafka binder

With the regular Kafka binder:

1. Start a test Kafka broker.
2. Create an input binding and consumer group.
3. Send several messages and verify the consumer receives them.
4. Verify the binding has `pausable=true`.
5. Send PAUSED.
6. Send more messages to the topic.
7. Verify the application stops receiving new messages while paused.
8. Verify the consumer group does not undergo a partition rebalance due to the pause.
9. Send RESUMED.
10. Verify the consumer resumes processing the backlog.

To verify there is no rebalance, observe Spring Kafka's assignment and rebalance listener rather than merely checking the received message count.

### Testing binders that do not support pause

For binders without pause/resume:

- Verify `pausable=false` or equivalent metadata.
- Send PAUSED in a test environment.
- Inspect warning logs.
- Confirm the consumer is not reported as paused if the binder does not support it.
- Use STOPPED/STARTED according to the semantics provided by the binder.

### Testing the Kafka Streams binder

With the Kafka Streams binder:

- Confirm the initial binding state is running.
- Send STOPPED and verify the processor stops processing.
- Send STARTED and verify the processor resumes operating.
- Verify the endpoint shows `pausable=false`.
- Do not write tests expecting PAUSED/RESUMED to work.

## 19. Common issues

| Symptom | Cause | How to resolve |
|---|---|---|
| `/actuator/bindings` not found | Missing Actuator or Web/WebFlux | Add the appropriate dependencies |
| Endpoint returns 404 | `bindings` not exposed | Configure management exposure |
| POST returns security error | Spring Security/CSRF blocks request | Grant admin permissions and configure security properly |
| Binding not found | Destination used instead of binding name | Check the function binding name |
| PAUSED has no effect | Binder or endpoint does not support Pausable | Check `pausable` and binder docs |
| Warning logged on pause | Target component does not support pause | Use STOPPED or a binder-specific solution |
| Kafka Streams cannot pause | Kafka Streams binder only supports STARTED/STOPPED | Use supported lifecycle phases |
| One pod paused but service still processes | Other replicas are still running | Control all instances if full stop is needed |
| STOPPED triggers rebalance | Consumer leaves the group | Use PAUSED if Kafka binder supports it and preserving assignment is desired |
| Resumed but no messages arrive | Wrong binding name, failing consumer, or no backlog | Check state, logs, offsets, and broker |
| Output binding does not stop with input | Each binding has its own lifecycle | Control the specific output or whole function per binder |
| Actuator exposes sensitive config data | Extended info not sanitized | Configure SanitizingFunction |

## 20. Pre-production operations checklist

| Item | Question |
|---|---|
| Binding name | Have you identified the exact input/output binding? |
| Binder | Is the binding using Kafka, Kafka Streams, RabbitMQ, Pulsar, or Solace? |
| Capability | Does the binding support pause/resume? |
| Current state | Is it running, stopped, or paused? |
| Instance scope | Does the command apply to one pod or all replicas? |
| Consumer group | Will STOPPED cause the consumer to leave the group and rebalance? |
| In-flight work | Are there messages mid-processing or uncommitted transactions? |
| Backlog | How much can backlog/lag grow during the pause? |
| Recovery | Should STARTED or RESUMED be used to restore the right state? |
| Security | Who is authorized to call the POST endpoint? |
| Audit | Are actor, reason, and timestamp recorded? |
| Verification | Did you re-GET the binding and verify broker behavior? |

## 21. Hands-on exercise and completion criteria

Create a Spring Cloud Stream application with a `processOrder` function reading from the `processOrder-in-0` binding.

1. Add Actuator and Web dependencies.
2. Expose the `bindings` endpoint.
3. Start the application and call GET `/actuator/bindings`.
4. Identify binding name, destination, group, state, and pausable capability.
5. With the regular Kafka binder, send PAUSED and confirm the consumer temporarily stops receiving records.
6. Send more messages to the topic while paused and observe the backlog.
7. Send RESUMED and confirm the consumer resumes processing.
8. Send STOPPED then STARTED and compare with pause/resume.
9. Repeat with the Kafka Streams binder, confirming only STARTED/STOPPED are supported.
10. Check the RabbitMQ or Pulsar binder for your project version without assuming PAUSED/RESUMED.
11. Run two replicas and demonstrate that a request to one pod controls only that instance.
12. Secure the endpoint with authentication/authorization and verify sensitive data is sanitized.
13. Write an integration test verifying state and broker behavior.

You have completed the exercise when you can distinguish STOPPED from PAUSED; choose STARTED or RESUMED appropriately to recover; control bindings with Actuator and BindingsLifecycleController; identify capabilities of Kafka, Kafka Streams, RabbitMQ, and Pulsar binders; and establish a safe operational workflow across multiple instances.

## 22. Official references

- [Spring Cloud Stream — Binding Visualization and Control](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding_visualization_control.html) — Actuator endpoint, BindingLifecycleController, lifecycle states, security, and sanitization.
- [Spring Cloud Stream 5.0 — Pausing and Resuming the Consumer](https://docs.spring.io/spring-cloud-stream/reference/5.0/kafka/kafka-binder/pause_resume.html) — pausing/resuming Kafka consumers without triggering partition rebalance.
- [Spring Cloud Stream — Kafka Streams Binder: Binding Visualization and Control](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/binding-visualization-and-control-in-binder.html) — Kafka Streams binder limitation supporting only STARTED/STOPPED.
- [Spring Cloud Stream — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html) — binding names, consumer properties, and autoStartup.
- [Spring Integration — Pausable API](https://docs.spring.io/spring-integration/docs/current/api/org/springframework/integration/core/Pausable.html) — endpoint pause/resume contract and connection semantics.
