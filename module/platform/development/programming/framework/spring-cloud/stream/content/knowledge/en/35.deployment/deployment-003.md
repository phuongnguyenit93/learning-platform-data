# Readiness Ordering of Broker, Bindings, and Application

In a **Spring Cloud Stream** application, a successfully running Java process does not mean the service can already send or receive events. Spring Boot can create the ApplicationContext while Kafka has not yet served metadata, RabbitMQ does not yet have a valid queue, or Pulsar does not yet allow subscriptions. Even after bindings are created, consumers may still be waiting for assignment; Kafka Streams also needs to restore state stores before serving accurate data.

This lesson covers the readiness sequence when deploying `Supplier`/`Function`/`Consumer` functions across Kafka, RabbitMQ, and Pulsar. The goal is to handle slow-starting brokers, uninitialized bindings, HTTP APIs receiving traffic too early, mass application restarts during broker incidents, or processors receiving messages before business dependencies are ready.

## 1. There Are Multiple Levels of "Ready," Not Just One

| Level | What Has Happened | What Is Not Yet Guaranteed |
| --- | --- | --- |
| Container running | Container has been created and the process is alive | JVM/Spring Boot is ready |
| Spring Boot started | ApplicationContext and beans have been built | Broker, bindings, and consumers are operational |
| Broker reachable | Client can connect to the broker | Topic/queue/ACL/schema are valid |
| Binding started | Input/output binding lifecycle is running | Consumer has received partitions or messages are written successfully |
| Consumer/processor ready | Consumer can process; required topology/state is ready | All downstream business logic will always succeed |
| Application ready | Service capabilities can accept traffic per policy | No errors will ever occur after startup |

Liveness, readiness, binding lifecycle, and broker health are distinct signals. Never replace them with a single TCP check or an HTTP endpoint that always returns 200.

~~~mermaid
flowchart TD
  A[Start container] --> B[Spring Boot builds ApplicationContext]
  B --> C[Select binder and configure bindings]
  C --> D{Broker ready for binding?}
  D -->|No| E[Retry binding or fail-fast]
  E --> D
  D -->|Yes| F[Create and start bindings]
  F --> G[Consumer subscribes or joins group]
  G --> H{Assignment and state ready?}
  H -->|Not yet| I[Rebalance or restore]
  I --> H
  H -->|Yes| J[Functional readiness]
  J --> K[Serve traffic or process events]
~~~

This diagram is an operational model. Producer bindings, consumer bindings, assignments, and state restoration can happen asynchronously, and the exact sequence depends on the binder.

## 2. Example of a Startup Race

Consider a deployment with Order Service and Kafka:

1. 10:00:00: Kubernetes creates the Kafka pod and the Order Service pod.
2. 10:00:05: Kafka opens its TCP port, but metadata/controller state is not yet stable.
3. 10:00:08: Spring Boot starts creating bindings for the `orders.created` topic.
4. 10:00:10: Kafka client cannot fetch metadata yet, so binding creation may fail or wait to retry.
5. 10:00:20: Kafka is ready to serve topics, ACLs, and metadata.
6. 10:00:24: Bindings are created; the consumer joins its group.
7. 10:00:30: The consumer receives partitions; the application is eligible to serve capabilities requiring message flow.

These timestamps are illustrative only. If readiness only checks the web server at step 3, callers may send requests while the producer is not operational. If liveness requires the broker to always be UP, Kubernetes may repeatedly restart Order Service while Kafka is merely starting up, making things worse.

## 3. A Running Broker Is Not the Same as a Usable Broker

A successful TCP connection does not prove the broker can actually serve the workload. You also need to verify:

- DNS and connection addresses; with Kafka, advertised listeners must match the client's network.
- Valid, non-expired TLS/SASL, username/password, or tokens.
- Permissions to create/read/write topics, exchanges, queues, namespaces, and subscriptions.
- Topics/queues exist or are properly provisioned under the binder's permissions.
- Kafka metadata, partition leaders, and required replication/acknowledgment settings.
- RabbitMQ virtual host, exchanges, queue arguments, and compatible bindings.
- Pulsar service URL, topic lookup, subscriptions, and schema compatibility.

Distinguish three failure categories: late-arriving broker, transient connection drop, and unrecoverable misconfiguration. Late arrivals can be retried; wrong ACLs/hostnames/queue arguments require configuration intervention. Do not use infinite retries to mask permanent errors.

## 4. Binding Names and Binding Creation Sequence

Example of a function:

~~~java
@Bean
public Function<OrderCreated, OrderValidated> validateOrder(
        OrderValidator validator) {
    return validator::validate;
}
~~~

By default naming rules, Spring Cloud Stream creates **validateOrder-in-0** and **validateOrder-out-0**. If aliases are defined in the function bindings configuration, operational controls must use the actual alias names.

~~~yaml
spring:
  cloud:
    function:
      definition: validateOrder
    stream:
      bindings:
        validateOrder-in-0:
          destination: orders.created
          group: validation-service
        validateOrder-out-0:
          destination: orders.validated
~~~

A binding connects function inputs/outputs to middleware destinations. Creating the ApplicationContext does not prove the binding succeeded. Likewise, a producer binding in the STARTED state does not guarantee every subsequent send will be acknowledged by the broker.

For consumers, there is also joining the group/subscription and assignment. For Kafka Streams, you must add restoring state and waiting for stream threads to transition to the appropriate running state.

## 5. Retrying When the Broker Is Not Ready During Binding Creation

Spring Cloud Stream provides **spring.cloud.stream.bindingRetryInterval** to retry binding creation when a binder does not support late binding and the broker is not ready yet. The value is in seconds; the documentation describes a default of **30 seconds**.

~~~yaml
spring:
  cloud:
    stream:
      binding-retry-interval: 15
~~~

If set to **0**, binding creation failures covered by this mechanism are treated as fatal and the application will not complete startup.

| Mechanism | Which Stage Does It Handle? |
| --- | --- |
| bindingRetryInterval | Binding could not be created yet |
| Consumer maxAttempts | Handler is processing a message and throws an exception |
| Client reconnect/backoff | Broker connection is lost or changes |
| HTTP/database client retries | Business downstream has a transient error |

Do not use `consumer.maxAttempts` to fix binding creation failures. Do not treat `bindingRetryInterval` as a guarantee of auto-recovery for every error type across every binder: some configuration, authentication, or bean initialization errors fail before the retry mechanism; some binders support late binding in their own way.

Choose **retry** when the broker may arrive late or experience brief interruptions and the application has proper readiness/alerting. Choose **fail-fast** when startup must fail explicitly so the orchestrator or runbook can intervene. Both approaches require logging the root cause and bounding investigation time.

## 6. AutoStartup for Inputs and Outputs

By default, consumer and producer bindings start automatically. You can disable auto-startup on a binding when coordinating prerequisites:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        validateOrder-in-0:
          destination: orders.created
          group: validation-service
          consumer:
            auto-startup: false
        validateOrder-out-0:
          destination: orders.validated
          producer:
            auto-startup: true
~~~

This is useful when you want to finish migrations, load config, or validate policies before receiving events. However, if `consumer.auto-startup=false`, the input will not receive messages until started via the lifecycle API or an application-managed mechanism.

AutoStartup is lifecycle control, not a health check. If a consumer is intentionally stopped, the readiness of any feature depending on that consumer should reflect it.

## 7. Querying and Controlling Binding Lifecycles

Spring Cloud Stream provides **BindingsLifecycleController** and Actuator **/actuator/bindings** to observe and control bindings.

~~~java
import org.springframework.cloud.stream.binding.BindingsLifecycleController;
import org.springframework.cloud.stream.binder.Binding;

Binding<?> binding = controller.queryState("validateOrder-in-0");
if (binding != null && !binding.isRunning()) {
    controller.start("validateOrder-in-0");
}
~~~

`controller` in the example is the framework's `BindingsLifecycleController` bean. If the binding has not been created yet, is in an error state, or the binder does not support an operation, handle that case instead of assuming `start` always succeeds.

Enable the endpoint if HTTP management is needed:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,bindings
~~~

Read operations:

~~~bash
curl -fsS http://localhost:8080/actuator/bindings
curl -fsS http://localhost:8080/actuator/bindings/validateOrder-in-0
~~~

To START a stopped binding:

~~~bash
curl -X POST http://localhost:8080/actuator/bindings/validateOrder-in-0 \
  -H "Content-Type: application/json" \
  -d '{"state":"STARTED"}'
~~~

Because the endpoint can start/stop/pause bindings, it must be protected with authentication, authorization, and network policies. Never expose control endpoints to the public Internet. PAUSED/RESUMED are only available when supported by the binder and underlying technology.

**isRunning() only measures lifecycle state.** Consumers also involve assignment, broker connectivity, retries, and state restoration; producers also involve send outcomes and acknowledgments.

## 8. Liveness and Readiness in Spring Boot

Spring Boot Actuator exposes Application Availability:

- **/actuator/health/liveness**: Is the application still in an internal state worth keeping running?
- **/actuator/health/readiness**: Should the application receive traffic under the current policy?

During startup, Spring Boot typically transitions from liveness BROKEN/readiness REFUSING_TRAFFIC, to liveness CORRECT/readiness REFUSING_TRAFFIC, and finally readiness ACCEPTING_TRAFFIC once startup tasks finish.

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
  endpoints:
    web:
      exposure:
        include: health,info
~~~

When a web server is present, Actuator provides **/actuator/health/liveness** and **/actuator/health/readiness**. With `add-additional-paths`, Spring Boot can also expose **/livez** and **/readyz** on the main port, which is helpful when the management port differs from the application port.

By default, Spring Boot does not automatically include all external system `HealthIndicator` beans in the readiness group. This is by design to prevent all replicas from being removed from routing when a shared dependency goes DOWN.

## 9. Do Not Put Broker Health in Liveness

If a shared broker experiences an incident and every pod's liveness depends on the broker:

1. All replicas report liveness DOWN.
2. Kubernetes restarts replicas en masse.
3. The broker receives a surge of simultaneous connections, authentications, consumer group joins, and binding provisioning requests.
4. Rebalancing and restoration can drag out, slowing recovery.

Liveness should reflect internal issues that a process restart can potentially fix, such as a deadlock. A brief loss of connectivity to Kafka/RabbitMQ/Pulsar usually calls for client reconnection and alerting, not killing the entire application.

Readiness may consider an external dependency if that dependency is **strictly required to serve HTTP requests**. However, putting a shared broker into readiness can also remove every replica from the Service. The decision must depend on the application's serving model and fallbacks.

## 10. Readiness by Workload Role

| Application Type | Appropriate Readiness Policy | Notes |
| --- | --- | --- |
| HTTP API that must publish an event before returning success | Check that required producer capabilities are ready | A STARTED binding does not guarantee subsequent sends always succeed |
| Pure consumer serving no HTTP requests | Focus on measuring consumer lifecycle, lag, errors, and reconnects | K8s readiness does not automatically pause consumers |
| Kafka Streams with state queries | Required tasks/threads are running and state is restored | The web server may open before stores finish recovering |
| Service with multiple optional bindings | Only truly required bindings should block readiness | Do not let a secondary stream take down the entire API |

**Crucial point:** Kubernetes readiness decides whether a pod stays in EndpointSlice/Service routing to receive network traffic. It **does not stop a running Kafka consumer, Rabbit listener, or Pulsar subscription**. Consumers can continue processing messages even when HTTP readiness returns DOWN.

If you want a consumer to wait on a prerequisite, you must control the binding lifecycle or add an appropriate gating mechanism in the processor. HTTP readiness is not a switch to pause message consumption.

## 11. Checking Bindings in Readiness

For a required input binding, you can create a custom `HealthIndicator`:

~~~java
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.cloud.stream.binder.Binding;
import org.springframework.cloud.stream.binding.BindingsLifecycleController;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class BindingReadinessConfiguration {

    @Bean("inputBindingReady")
    HealthIndicator inputBindingReady(BindingsLifecycleController controller) {
        return () -> {
            try {
                Binding<?> binding = controller.queryState("validateOrder-in-0");
                if (binding != null && binding.isRunning()) {
                    return Health.up().build();
                }
            }
            catch (RuntimeException ex) {
                // Avoid exposing credentials or stack traces in health responses.
            }
            return Health.down()
                    .withDetail("binding", "validateOrder-in-0")
                    .build();
        };
    }
}
~~~

Include the indicator in the readiness group:

~~~yaml
management:
  endpoint:
    health:
      group:
        readiness:
          include: readinessState,inputBindingReady
~~~

This is a **minimal lifecycle** check. A running binding does not prove Kafka partition assignment, Rabbit queue message dispatch, or an active Pulsar subscription. For critical workloads, add necessary business/transport signals with bounded timeouts.

Health probes should be fast, without creating new producers/AdminClients or making continuous network calls per request. If you must probe the broker, cache the status and bound frequency/timeouts.

## 12. Binder HealthIndicator and Its Limitations

When Actuator is present, Spring Cloud Stream can provide a health contributor named **binders**, configured via **management.health.binders.enabled**:

~~~yaml
management:
  health:
    binders:
      enabled: true
  endpoint:
    health:
      show-details: when_authorized
~~~

Support levels vary by binder:

- **Kafka binder:** Provides a health indicator checking communication with Kafka/metadata. An UP result does not prove end-to-end message delivery.
- **Rabbit binder:** Health relies mainly on Spring Boot's `RabbitHealthIndicator`, reflecting connectivity.
- **Kafka Streams binder:** Monitors stream thread states; documentation states UP when all registered threads are in the RUNNING state.
- **Pulsar binder:** Check the binder/Spring Pulsar version and actual health capabilities, adding custom checks as needed.

Do not assume every binder always provides a `HealthIndicator`. Having `binders` health UP also does not guarantee messages are acknowledged or consumers have zero lag.

## 13. Docker Compose: Waiting for Healthy Dependencies

The short `depends_on` form only coordinates container start order; it does not wait until the broker is ready to use. When you need to wait at startup, use `condition: service_healthy` and a `healthcheck`.

Example with RabbitMQ:

~~~yaml
services:
  rabbitmq:
    image: rabbitmq:4-management
    healthcheck:
      test: ["CMD", "rabbitmq-diagnostics", "-q", "ping"]
      interval: 5s
      timeout: 5s
      retries: 12
      start_period: 15s

  order-service:
    image: example/order-service:1.0
    environment:
      SPRING_RABBITMQ_HOST: rabbitmq
    depends_on:
      rabbitmq:
        condition: service_healthy
~~~

Compose waits for the `rabbitmq` healthcheck to report healthy before creating `order-service`. However, `rabbitmq-diagnostics ping` only checks the node at a basic level; it does not verify exchanges/queues, arguments, ACLs, or the application's consume permissions.

`depends_on` primarily handles **startup ordering**, not reconnection if the broker fails later. For Kafka/Pulsar, readiness checks should match the image and verify metadata/lookup capabilities rather than just an open TCP port.

## 14. Kubernetes: Startup, Liveness, and Readiness Probes

Kubernetes does not automatically guarantee a broker Deployment finishes before an application Deployment simply because manifests were applied in a certain order. The scheduler can create pods in parallel; you must actively handle a late-arriving broker.

Example of a Spring Boot HTTP service:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: order-service
  template:
    metadata:
      labels:
        app: order-service
    spec:
      terminationGracePeriodSeconds: 60
      containers:
        - name: app
          image: example/order-service:1.0
          ports:
            - name: http
              containerPort: 8080
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 5
            failureThreshold: 30
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
            failureThreshold: 3
            successThreshold: 1
~~~

The startup probe here allows roughly 150 seconds (30 × 5) for the application to start before kubelet begins liveness/readiness checks. These numbers are illustrative and must be measured in a production-like environment. The startup probe succeeds once and stops; readiness continues running throughout the pod's lifecycle.

If the application has no web server, choose an exec probe or a dedicated management endpoint that accurately reflects functionality rather than adding a fake HTTP endpoint just to return 200.

### Can an Init Container Replace This?

Init containers are useful for waiting on finite prerequisites such as configuration or database migrations. However, merely checking a broker's TCP port does not guarantee valid topics/queues/subscriptions and ACLs. Init containers also do not handle broker outages after startup. Therefore, use them to complement retries and lifecycle management, not replace them.

## 15. Explicitly Starting Consumers After Prerequisites

When you want a consumer to process only after a preparation step, the sequence can be:

1. Start Spring Boot and observability components.
2. Validate required configs/secrets, schemas, migrations, or caches with a timeout.
3. Confirm the path to the broker/destination meets prerequisites.
4. Call `BindingsLifecycleController.start` for inputs with `auto-startup=false`.
5. Wait for consumer assignment/topology readiness if applicable.
6. Publish readiness for the relevant capability.

Do not block `ApplicationRunner` indefinitely waiting for the broker. If conditions are not met within the deadline, choose retry-with-alerting or fail-fast. If bindings start asynchronously, completing step 4 still does not prove step 5 has succeeded.

## 16. Kafka: Metadata, Topics, and Consumer Groups

Kafka readiness has multiple layers:

- Bootstrap broker is reachable.
- Topic metadata and advertised listeners are correct.
- Topics exist with sufficient partitions and proper ACLs.
- Producers can publish under the acks/durability policy.
- Consumers subscribe, join the group, and receive partitions.
- If stateful processing is used, the processor completes necessary restoration steps.

Regular Kafka binder example:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      binding-retry-interval: 15
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: order-service
          consumer:
            auto-startup: true
      kafka:
        binder:
          brokers: kafka:9092
~~~

Add SASL/TLS if required by the broker. Connecting to a bootstrap broker is not enough to verify the application's ACLs/topics.

During rolling deployments or scaling, consumer groups may rebalance; temporary shifts in partition assignment are normal. Do not immediately restart a pod just because a single snapshot shows no assignments yet. Watch for prolonged stalls, consumer lag, and processing progress.

## 17. RabbitMQ: Connection, Exchange, Queue, and Listener

The Rabbit binder typically requires these steps:

1. Connect to a RabbitMQ node with valid credentials and virtual host.
2. Exchanges, queues, and bindings exist or are validly provisioned.
3. Queue arguments such as durable, TTL, and DLX/queue-type do not conflict.
4. Listener containers start and consumers are registered.
5. Messages are delivered and acked/rejected according to semantics.

A **PRECONDITION_FAILED: inequivalent arg** error during queue declaration is a topology misconfiguration, not an unready broker. Retries will not resolve it until the queue/config is aligned consistently. Access refused errors also require fixing permissions.

The Rabbit health indicator checks connectivity, but does not prove a specific queue has correct routing or dead-lettering. Test provisioning, consumption, acknowledgment, and DLQ behavior with separate integration tests.

## 18. Pulsar: Lookup, Schema, and Subscription

The Pulsar binder builds on Spring for Apache Pulsar. Steps to verify:

- `service-url` and authentication are correct;
- topics/namespaces exist or creation is permitted;
- producers have publish permissions and compatible schemas;
- consumers look up topics and subscribe with the right subscription type/name;
- message processing and ack/redelivery work;
- dead-letter/retry-letter policies are configured if needed.

Input example:

~~~yaml
spring:
  pulsar:
    client:
      service-url: pulsar://pulsar-broker:6650
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: persistent://public/default/orders-created
          group: order-service
~~~

Depending on the binder version, `group` and extended consumer settings determine the actual subscription identity/type. Do not assume Pulsar subscriptions share identical semantics with Kafka consumer groups or use the exact same health configuration.

## 19. Kafka Streams: State Restoration Before Business Readiness

The Kafka Streams binder uses KStream/KTable/GlobalKTable and may create RocksDB state stores and changelog/repartition topics. Even when Kafka is reachable, the topology may still be:

- creating/verifying internal topics;
- joining the group, rebalancing, and assigning stream tasks;
- reading changelogs to restore state stores;
- updating standby/warmup tasks;
- transitioning stream threads to RUNNING.

When an application exposes queries against state or windowed aggregates, readiness for that capability must wait until state is usable. The Kafka Streams binder provides a health indicator tracking thread states; RUNNING is helpful, but with multiple topologies/stores you still need to define readiness around API and business requirements.

If `state.dir` resides on an ephemeral volume, a cold restore after rescheduling can take longer than a warm restart. Size startup/readiness probes from measured timings, and do not tie broker outages into liveness so pods are not killed mid-restore.

## 20. Broker Disconnection After Startup

| Scenario | Typically Appropriate Response |
| --- | --- |
| Brief broker interruption, client supports reconnect | Keep the process alive, monitor, let the client recover |
| HTTP API required to publish events | Return errors/circuit-break appropriately; consider tying readiness to publish capability |
| Pure consumer not serving HTTP | Monitor reconnects, lag, and processed message count; do not rely on readiness to pause |
| Kafka Streams during rebalance/restore | Monitor tasks/state; temporarily restrict state-dependent APIs |
| Bad secret/ACL after credential rotation | Diagnose and refresh/restart client per runbook |
| Destination deleted or queue arguments changed | Investigate provisioning drift; avoid silent infinite retries without alerts |

Not every error across every binder recovers automatically. Some failures during binding creation require rebinding/restarting; some active connections can self-heal. Verify with your exact version and topology.

Reconnects or redeliveries can produce duplicates; use event IDs, idempotency, or outbox/inbox patterns when side effects matter. "Ready" does not mean exactly-once.

## 21. Graceful Shutdown and Rolling Deployment

A safe shutdown sequence:

1. Stop accepting new HTTP traffic via readiness/graceful shutdown if a web server exists.
2. Stop triggers or `Supplier`/schedulers from emitting unnecessary events.
3. Allow in-flight processing to finish within the configured limit.
4. Stop consumer bindings/streams processors, flush, and ack/commit per binder behavior.
5. Close clients, releasing local state and connections.

Spring Boot's graceful shutdown for the web server does not automatically guarantee all consumer messages finish. Kafka, RabbitMQ, Pulsar, and Kafka Streams have different lifecycles/ack/commit behaviors; test them individually.

`terminationGracePeriodSeconds` must accommodate long-running messages, open transactions, and client shutdown. If too short, a pod killed by SIGKILL may cause message redelivery. If too long, deployments stall when processes hang.

## 22. Readiness Testing Matrix

| Scenario | Observable Signal | Expectation |
| --- | --- | --- |
| App starts before broker | Binding retries, Actuator health | Retries or fails fast as intended, does not report business-ready prematurely |
| TCP open but topic not created | Metadata/provision logs | Clear error or valid permission-based provisioning |
| Invalid credentials/ACL | Authentication/authorization failures | Do not mask errors with infinite retries |
| Consumer `auto-startup=false` | Actuator bindings | Binding remains STOPPED until explicitly started |
| Kafka consumer rebalance | Group assignment, lag | No pointless restarts over transient assignment changes |
| Kafka Streams cold restore | Store restore, thread state | State-dependent readiness turns UP only after restoration |
| Broker DOWN mid-processing | Liveness, error rate, retries | Do not mass-restart pods over a shared broker fault |
| Broker recovers | Binding/client state, new processing | Reconnects or rebinds per binder capability |
| Rolling update and SIGTERM | In-flight ack/commit, redelivery | No lost messages; duplicates handled idempotently |
| Consumer HTTP readiness DOWN | Kafka/Rabbit/Pulsar consume metrics | Verify readiness does not automatically block consumption |

Test Binder validates function/binding logic, but does not fully simulate broker metadata, assignment, or recovery. Use Testcontainers for Kafka, RabbitMQ, or Pulsar to test real ordering behavior.

A practical test scenario: start the application while the broker is down and observe binding state; start the broker; send an event with a fixed `eventId`; stop the broker after the consumer is active; restore the broker; inspect liveness, readiness, lag, and side-effect counts. Repeat with multiple replicas.

## 23. Tracking Time to Business-Ready

Timestamps and metrics to collect:

- Spring Boot `ApplicationStarted` and `ApplicationReady`.
- Timestamp when bindings are created and enter the `STARTED` state.
- Count/latency of binding creation retries.
- Kafka assignment/rebalance duration and consumer lag.
- RabbitMQ connection recovery and queue declaration failures.
- Pulsar lookup/subscription failures.
- Kafka Streams restore duration, thread state, and changelog lag.
- Elapsed time from process start to business-ready capability.
- First send/receive errors after startup.

Do not put synthetic publish/consume checks into every production HTTP readiness probe; it wastes resources and can create side effects. Use updated metrics/lifecycle state and controlled end-to-end tests in appropriate environments.

## 24. Runbook When a Pod Is Running but Not Ready

1. Check Kubernetes events, pod restart count, and probe failures.
2. Inspect liveness/readiness groups; see which custom health check is DOWN.
3. Query `/actuator/bindings` (over a secured management channel).
4. Check `bindingRetryInterval` and `autoStartup`.
5. Check broker DNS, advertised listeners/`service-url`, TLS/SASL, credentials, and ACLs.
6. Check topics, partitions, exchanges, queues, subscriptions, and schemas.
7. Check Kafka assignments/lag or Pulsar subscription state.
8. For Kafka Streams, inspect state restoration, changelogs, and thread states.
9. Determine whether an overly strict shared dependency health check is causing all replicas to lose readiness.
10. If the broker has recovered but bindings did not self-recover, rebind or restart according to a tested runbook.

Never conclude a service is healthy simply because HTTP `/actuator/health` returns 200. Cross-check binding lifecycle, broker metrics, and actual message send/receive outcomes.

## 25. Production Checklist

- Define input/output bindings, destinations, and groups/subscriptions.
- Verify broker DNS, networking, credentials, ACLs, and provisioning.
- Configure binding retries or fail-fast according to policy.
- Distinguish binding retries from message retries.
- Disable `autoStartup` only when consumer orchestration is genuinely needed, with an explicit start step.
- Monitor and secure the Actuator bindings endpoint.
- Keep liveness independent of routine broker outages.
- Define readiness around functionality, not just an HTTP port.
- Remember that Kubernetes readiness does not pause broker consumers.
- For Kafka Streams, account for assignment/state restoration time.
- Use Compose `service_healthy` when needed, while still handling post-startup outages.
- Configure appropriate Kubernetes startup/liveness/readiness probes and graceful termination.
- Test late-arriving brokers, interruptions, reconnects, and rolling deployments.
- Ensure idempotency for redeliveries/duplicates.
- Track time to business-ready, error rates, and consumer lag.

## References

- [Spring Cloud Stream — Binding Service Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-service-properties.html)
- [Spring Cloud Stream — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
- [Spring Cloud Stream — Binding visualization and control](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding_visualization_control.html)
- [Spring Cloud Stream — Binder Health Indicator](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/health-indicator.html)
- [Spring Cloud Stream — Kafka Binder Configuration](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html)
- [Spring Cloud Stream — Rabbit Binder Health Indicator](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview/health-indicator.html)
- [Spring Cloud Stream — Kafka Streams Health Indicator](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/health-indicator.html)
- [Spring Cloud Stream — Pulsar Binder](https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html)
- [Spring Boot Actuator — Endpoints and Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Kubernetes — Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/concepts/workloads/pods/probes/)
- [Docker Compose — Control startup and shutdown order](https://docs.docker.com/compose/how-tos/startup-order)

Configuration and health indicator capabilities depend on the Spring Boot, Spring Cloud Stream, and binder versions. Check your BOM/release train before deploying to production.

## Conclusion

**Broker reachable**, **binding STARTED**, **processor ready**, and **application ready** are related but distinct states. Spring Cloud Stream supports binding creation retries and lifecycle management; Spring Boot provides liveness/readiness; Kubernetes uses readiness solely to route network traffic to pods. Coordinating these properly helps services tolerate late-starting brokers, avoids continuous restarts during shared broker faults, and prevents accepting requests or running processors before critical data/state is truly ready.
