# Explicit Binding Creation with input-bindings and output-bindings

Spring Cloud Stream normally creates bindings based on `Supplier`, `Function`, or `Consumer` beans. However, some applications receive data from another framework, such as Spring Integration, or emit events from REST controllers, schedulers, and business services. In those cases, the application may need bindings without declaring a function bean solely to serve as the entry or exit point of a stream.

Spring Cloud Stream supports explicit binding declaration via two properties: **spring.cloud.stream.input-bindings** and **spring.cloud.stream.output-bindings**. These properties create bindings independently of functions. An input binding connects data from the broker into the application; an output binding connects data sent by the application out to the broker. The application is responsible for wiring those bindings to its processing logic or data producers.

## 1. When are explicit bindings needed?

Use explicit bindings when the names and directions of data streams are known, but the producer or processor is not represented as a `Supplier`, `Function`, or `Consumer`.

Common scenarios include:

- A REST controller receives an HTTP request and emits an event to the broker.
- A scheduled job or `ApplicationRunner` reads data from another system and emits messages.
- A Spring Integration flow needs to receive messages from the broker over a channel and process them with an `IntegrationFlow`.
- The application integrates an external library or framework that has its own message channel model.
- The application needs output bindings created eagerly at startup so destination, binder, and producer configuration are applied before the first send request occurs.

For example, an order service might receive events from an **orders** topic or queue and pass them into an `IntegrationFlow` for processing. Once processed, another REST endpoint can send notifications to the **notifications** destination through `StreamBridge`. Neither binding has to be attached to a `Function` bean.

## 2. The two properties for declaring input and output bindings

Both property names are plural because each can accept multiple binding names:

| Property | Purpose | Data direction |
|---|---|---|
| **spring.cloud.stream.input-bindings** | Creates one or more input bindings. | Broker → application |
| **spring.cloud.stream.output-bindings** | Creates one or more output bindings. | Application → broker |

Binding names are separated by semicolons (**;**). For example:

~~~yaml
spring:
  cloud:
    stream:
      input-bindings: ordersIn;refundsIn
      output-bindings: notificationsOut;auditOut
~~~

The configuration above instructs the framework to create two input bindings named **ordersIn** and **refundsIn**, along with two output bindings named **notificationsOut** and **auditOut**.

Explicit bindings do not need **-in-0** or **-out-0** suffixes. The declared name itself is the binding name, because the input or output direction is already determined by which property contains the name. For example, output binding **notificationsOut** is configured using **spring.cloud.stream.bindings.notificationsOut.destination**, not **notificationsOut-out-0.destination**.

This differs from bindings derived from functions. If a `Function` bean is named **normalizeOrder**, Spring Cloud Stream creates bindings **normalizeOrder-in-0** and **normalizeOrder-out-0**. With explicit bindings, names like **ordersIn** or **notificationsOut** are used directly.

## 3. Configuring destination and properties per binding

After declaring binding names, configure destination and common properties following the pattern:

**spring.cloud.stream.bindings.<binding-name>.<property>**

Complete example:

~~~yaml
spring:
  application:
    name: order-integration
  cloud:
    stream:
      input-bindings: ordersIn;refundsIn
      output-bindings: notificationsOut;auditOut
      bindings:
        ordersIn:
          destination: orders
          group: order-integration
          content-type: application/json
        refundsIn:
          destination: refunds
          group: refund-integration
          content-type: application/json
        notificationsOut:
          destination: notifications
          content-type: application/json
        auditOut:
          destination: audit-events
          content-type: application/json
~~~

In this example:

- **ordersIn** receives messages from destination **orders** and belongs to consumer group **order-integration**.
- **refundsIn** receives messages from destination **refunds** and belongs to consumer group **refund-integration**.
- **notificationsOut** sends messages to destination **notifications**.
- **auditOut** sends messages to destination **audit-events**.

The **destination** property specifies the messaging resource the binding connects to. Depending on the binder, destination may correspond to a Kafka topic, an exchange and queue managed by the RabbitMQ binder, or a Pulsar topic. Do not infer physical resource names solely from binding names; check how the binder provisions resources.

The **group** property applies only to input bindings. Groups help replicas of the same processing capability coordinate message consumption according to broker semantics. If `group` is omitted, the binding may act as an anonymous consumer and consumption state may not persist as desired across restarts. For business streams that must resume reliably across deployments, pick a meaningful group and keep its name consistent.

The **content-type** property describes the content format so Spring Cloud Stream performs appropriate message conversion. If an external system sends data in a custom format or uses native broker serialization, configure the corresponding serializer/deserializer and conversion mode per binder.

## 4. Connecting an input binding to Spring Integration

Declaring **input-bindings** only creates the binding and its receiving channel. The application must still register a component listening on that channel to process messages. A natural integration approach is using the Spring Integration Java DSL.

For example, configuring an input binding:

~~~yaml
spring:
  cloud:
    stream:
      input-bindings: ordersIn
      bindings:
        ordersIn:
          destination: orders
          group: order-integration
          content-type: application/json
~~~

Creating an `IntegrationFlow` that reads from the channel named **ordersIn**:

~~~java
@Configuration
public class OrderIntegrationConfiguration {

    @Bean
    IntegrationFlow ordersFlow(OrderService orderService) {
        return IntegrationFlow.from("ordersIn")
                .handle(orderService, "handle")
                .get();
    }
}
~~~

The **handle** method of `OrderService` receives the object converted according to the message converter configuration and runs business logic. The channel name in **IntegrationFlow.from("ordersIn")** must match the declared input binding name. If you rename the binding, update every place referencing the channel as well.

The data flow can be visualized as follows:

~~~mermaid
flowchart LR
    A[Kafka, RabbitMQ, or Pulsar] --> B[Input binding ordersIn]
    B --> C[Message channel]
    C --> D[Spring IntegrationFlow]
    D --> E[OrderService]
~~~

Other Spring Integration adapters or endpoints can also be used to subscribe to the channel. The key point is that the channel must have a message-receiving component; otherwise, the binding may still be created, but data will not reach business logic as expected.

## 5. Connecting an output binding to StreamBridge

With an explicit output binding, the application can send data through **StreamBridge**. This is a good fit when data originates from a REST controller, a service, or a component other than a `Supplier`.

Configuring the output binding:

~~~yaml
spring:
  cloud:
    stream:
      output-bindings: notificationsOut
      bindings:
        notificationsOut:
          destination: notifications
          content-type: application/json
~~~

A service can send notifications:

~~~java
@Service
public class NotificationPublisher {

    private final StreamBridge streamBridge;

    public NotificationPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    public boolean publish(Notification notification) {
        return streamBridge.send("notificationsOut", notification);
    }
}
~~~

The name passed to **streamBridge.send("notificationsOut", notification)** must match the declared output binding. Because the binding is already created from **output-bindings**, the application can preconfigure destination, content type, and binder for that binding before sending data.

Example REST integration:

~~~java
@RestController
@RequestMapping("/notifications")
public class NotificationController {

    private final NotificationPublisher publisher;

    public NotificationController(NotificationPublisher publisher) {
        this.publisher = publisher;
    }

    @PostMapping
    public ResponseEntity<Void> publish(@RequestBody Notification notification) {
        if (publisher.publish(notification)) {
            return ResponseEntity.accepted().build();
        }
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).build();
    }
}
~~~

The boolean returned by **StreamBridge.send** reflects the result of sending through the application's message channel. Do not interpret it as confirmation that the target consumer has processed the message. End-to-end delivery guarantees also depend on publisher confirms, transactions, acknowledgements, and binder/broker-specific configuration.

## 6. Explicit bindings vs. StreamBridge dynamic bindings

If you call **StreamBridge.send** with an output name that does not exist yet, `StreamBridge` can create an output binding dynamically on the first send and reuse that binding for subsequent sends. This is convenient when the destination is only known at runtime.

However, when the binding name and destination are known in advance, **spring.cloud.stream.output-bindings** creates the binding right at startup. The two approaches serve different goals:

| Output creation method | Creation time | When appropriate |
|---|---|---|
| **output-bindings** | When the application initializes bindings. | Destination is known ahead of time; early configuration and provisioning are needed. |
| StreamBridge dynamic binding | When calling **send** for the first time with an unknown name. | Destination is determined at runtime or varies per request. |

Example pre-creating two output bindings:

~~~yaml
spring:
  cloud:
    stream:
      output-bindings: notificationsOut;auditOut
      bindings:
        notificationsOut:
          destination: notifications
        auditOut:
          destination: audit-events
~~~

You can then invoke:

~~~java
streamBridge.send("notificationsOut", notification);
streamBridge.send("auditOut", auditRecord);
~~~

Do not confuse binding names with dynamic destination names. When the **notificationsOut** binding is already declared, `StreamBridge` sends via the configured binding whose destination is **notifications**. If you call **send** with an undeclared name like **tenant-events-42**, `StreamBridge` may treat that name as a dynamic binding/destination and create a binding dynamically. Control the inputs used to construct dynamic names so an unbounded number of names does not exhaust resources or caches inside the process.

## 7. Configuring binders for explicit bindings

Explicit bindings use binders just like bindings created from functions. If multiple binders are on the classpath or the application connects to multiple brokers, you can specify a binder for each binding using the **binder** property:

~~~yaml
spring:
  cloud:
    stream:
      input-bindings: ordersIn
      output-bindings: auditOut
      bindings:
        ordersIn:
          destination: orders
          group: order-integration
          binder: kafka
        auditOut:
          destination: audit-events
          binder: rabbit
~~~

This example assumes the application has already configured binders named **kafka** and **rabbit** respectively. The binder name must match a binder instance name declared in application configuration. Only add this property when you specifically need to pick a binder; if only one appropriate default binder exists, you can let the framework choose the default binder.

Not all extension properties are shared across Kafka, RabbitMQ, and Pulsar. Common properties such as **destination**, **group**, and **content-type** are configured under the binding name. Specific properties for send confirmation, consumer acknowledgement, TLS, retry, partitioning, or dead-lettering must follow the namespace and documentation of the chosen binder.

## 8. Distinguishing the three binding styles

Binding names and creation mechanisms are easy to confuse when an application combines functions, explicit bindings, and `StreamBridge`.

| Characteristic | Function binding | Explicit binding | Dynamic binding |
|---|---|---|---|
| How created | Derived from bean and function definition. | Declared via `input-bindings` or `output-bindings`. | Created when `StreamBridge` sends to a non-existent name. |
| Example input name | **normalizeOrder-in-0** | **ordersIn** | Not applicable to inputs via `StreamBridge` dynamic output mechanism. |
| Example output name | **normalizeOrder-out-0** | **notificationsOut** | Name passed to `send`, e.g., **tenant-events-42**. |
| Linked to a function | Yes. | Not required. | Not required. |
| Destination config | Under the function's binding name. | Under the directly declared name. | Can be generated from runtime target name or dynamic configuration. |

With function bindings, **spring.cloud.function.definition** selects which functions to run. With explicit bindings, **input-bindings** and **output-bindings** create channels without needing a function. With dynamic bindings, `StreamBridge` creates outputs when asked to send to a previously unregistered name. Do not use **input-bindings** or **output-bindings** as a replacement for **spring.cloud.function.definition**.

## 9. Testing explicit bindings

Three layers should be tested separately: whether the bindings are created, whether the channels are wired to application logic, and whether the real broker receives/delivers messages according to configuration.

Spring Cloud Stream's test binder lets you test flows inside the application without starting Kafka, RabbitMQ, or Pulsar. You can launch a test application with properties:

~~~text
spring.cloud.stream.input-bindings=ordersIn;refundsIn
spring.cloud.stream.output-bindings=notificationsOut;auditOut
~~~

Key test cases to cover:

| Scenario | How to test | Expected result |
|---|---|---|
| Single input binding | Declare **input-bindings=ordersIn**. | Binding and channel **ordersIn** are created. |
| Multiple input bindings | Declare semicolon-separated names. | Each input binding is created with its exact name. |
| Multiple output bindings | Declare **output-bindings=notificationsOut;auditOut**. | Output bindings are created at startup. |
| Names without suffixes | Check binding names in context or binding inspection tools. | Names are **ordersIn** or **notificationsOut**, without **-in-0** or **-out-0** appended. |
| Input via IntegrationFlow | Send a test message to the input binding. | `IntegrationFlow` receives the message and invokes the right service. |
| Output via StreamBridge | Invoke the service to send a test message. | Message passes through the right output binding and destination. |
| Multiple binders | Assign a binder per binding and run with corresponding test binders. | Each binding connects to the right binder. |
| Invalid destination or missing permissions | Use invalid test configuration. | Application clearly logs provisioning or connection failure; does not mark the message as processed. |

After testing with the test binder, run integration tests against a real broker or suitable broker container. Verify that topics, exchanges, queues, or subscriptions are provisioned; confirm the input binding's group; send and receive messages with realistic payloads; and verify serializers, content types, and access permissions.

## 10. Common errors

| Symptom | Possible cause | Resolution |
|---|---|---|
| Binding is not created | Wrong property name, wrong namespace, or name omitted from list. | Check **spring.cloud.stream.input-bindings** and **spring.cloud.stream.output-bindings**. |
| Application cannot find binding when sending | Name in **StreamBridge.send** does not match created output binding name. | Cross-check declared name and name passed to `send` verbatim. |
| Input channel does not process messages | No `IntegrationFlow` or subscriber listening on the channel. | Connect the channel to a handling endpoint and test incoming messages. |
| Framework cannot find destination | Wrong destination config or broker disallows provisioning. | Check destination name, resource-creation permissions, and binder logs. |
| Configuration does not apply to output | Using **-out-0** suffix on an explicit binding or configuring the wrong channel name. | Use the explicit output binding name directly under **spring.cloud.stream.bindings**. |
| Input does not keep expected consumption state | Missing group or unstable group name. | Set a clear group and verify broker semantics. |
| Channel-level send succeeds but consumer does not receive | Confusing **StreamBridge.send** return value with end-to-end delivery, or misconfigured broker/binding. | Check publisher confirms, destination, permissions, consumer group, and broker logs. |
| Multiple bindings connect to wrong broker | Missing `binder` or wrong binder name. | Verify multi-binder configuration and each binding's **binder** property. |

When investigating, verify in order: the binding name list, the created binding names, destination/group properties, selected binder, the channel or `StreamBridge` in use, and only then broker state and business logic. This separates binding-declaration bugs from message-processing bugs.

## 11. Pre-deployment checklist

- [ ] Every explicit input/output binding has a unique name and right direction.
- [ ] Multiple binding names are separated by semicolons.
- [ ] Explicit binding names are used directly without appending function suffixes.
- [ ] Every binding has an explicit destination.
- [ ] Input bindings have stable groups when durable consumption state is needed.
- [ ] Input channels are wired to an `IntegrationFlow` or actual subscriber.
- [ ] Output bindings are invoked by exact name through `StreamBridge`.
- [ ] The right binder is selected if the application uses multiple brokers.
- [ ] Content type, serializer, and producer/consumer properties fit the broker.
- [ ] Integration tests verify broker resources, sending, receiving, and message processing.
- [ ] Monitoring for connection failures, provisioning errors, and send outcomes is configured.

Explicit bindings allow Spring Cloud Stream to connect brokers to components not modeled as function beans. **input-bindings** creates inputs for application channels, while **output-bindings** pre-creates outputs for `StreamBridge` or message-producing components. When you keep binding names consistent, configure destinations accurately, and test both channels and brokers, applications can integrate external frameworks and event sources cleanly.

## References

- [Spring Cloud Stream — Explicit binding creation](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/explicit-binding-creation.html)
- [Spring Cloud Stream — Producing and consuming messages](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Spring Cloud Stream — Binding properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
