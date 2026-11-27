# Selecting a Binder When Sending with StreamBridge to Dynamic Destinations

`StreamBridge` lets an application send messages from a REST controller, scheduler, or external event source into Spring Cloud Stream. When a destination name is only known at runtime, `StreamBridge` can dynamically create an output binding on the first send. If the application has multiple binders, such as Kafka and RabbitMQ, the destination name alone is not enough to decide which broker should receive the message. The application must select a binder for that dynamic binding creation.

The `StreamBridge` API provides overloads that accept a binder name:

~~~java
boolean send(String bindingName, String binderName, Object data);
boolean send(
        String bindingName,
        String binderName,
        Object data,
        MimeType outputContentType);
~~~

The `binderName` parameter tells `BindingService` which binder will create the dynamic binding. The first parameter remains the output binding name; when the binding does not yet exist, this name is used as the dynamic destination name. Therefore, you need to clearly understand binding name, destination, and binder name before routing.

## 1. Distinguishing binding name, destination, and binder name

These three names play different roles:

| Value | Meaning | Example |
|---|---|---|
| `bindingName` | Name of the output binding in Spring Cloud Stream; for dynamic bindings, it is also the destination name being bound | `orders.eu` |
| `destination` | Actual resource name on the broker, such as a Kafka topic or RabbitMQ exchange | `orders.events.eu` |
| `binderName` | Name of the binder instance chosen by the application to create the binding | `kafkaWest`, `rabbitOps` |

With a statically declared binding, the binding name can differ from the destination. For example, binding `ordersKafka` can send to topic `orders.events` via binder `kafkaWest`.

With a dynamic destination, if no binding with that name exists and there is no dedicated mapping configuration, `StreamBridge` uses the binding name as the destination. For example, `send("orders.eu", "kafkaWest", event)` creates a dynamic output binding named `orders.eu` and instructs the Kafka binder to create or use destination `orders.eu`.

Do not pass a broker name or binder name in the `bindingName` position. Likewise, do not use a topic name as `binderName`; the two parameters have different responsibilities.

## 2. Why must a binder be selected explicitly?

When there is only one binder on the classpath, Spring Cloud Stream can select it automatically. When multiple binders are configured, the application must specify the binder for each binding. For example, the same application can receive commands from Kafka, send business events to Kafka, and send an audit copy to RabbitMQ.

~~~text
REST / Scheduler / Service
          |
          v
      StreamBridge
          |
          +---- bindingName = orders.eu
          |     binderName  = kafkaWest
          |            |
          |            v
          |        Kafka topic
          |
          +---- bindingName = audit.events
                binderName  = rabbitOps
                       |
                       v
                 Rabbit exchange
~~~

If `binderName` is omitted, `StreamBridge` uses the default binder. When multiple binders exist without a clear default binder, binding creation may fail because the framework does not know which broker to use. If a default binder exists but is a different broker than desired, messages may go to the wrong system.

Selecting a binder does not replace broker connection configuration. The Kafka binder still needs bootstrap servers, and the Rabbit binder still needs host/port and credentials. `binderName` only selects a binder configuration already declared in the application.

## 3. Declaring multiple binders in application.yml

Example of an application connecting to Kafka in the West environment and RabbitMQ for auditing:

~~~yaml
spring:
  cloud:
    stream:
      default-binder: kafkaWest
      binders:
        kafkaWest:
          type: kafka
          environment:
            spring:
              kafka:
                bootstrap-servers: localhost:9092
        rabbitOps:
          type: rabbit
          default-candidate: false
          environment:
            spring:
              rabbitmq:
                host: localhost
                port: 5672
                username: guest
                password: guest
      dynamic-destinations:
        - orders.eu
        - orders.us
        - audit.events
      dynamic-destination-cache-size: 64
~~~

In this example:

- `kafkaWest` and `rabbitOps` are binder configuration names. These are the names that can be passed to the `StreamBridge.send` overload.
- `type` specifies the binder type used to create the configuration: `kafka` or `rabbit`.
- `environment` contains the Spring Boot properties dedicated to that binder.
- `default-binder` sets Kafka as the default choice when a binding does not specify a binder.
- `default-candidate: false` ensures `rabbitOps` is only selected when explicitly referenced by the application.
- `dynamic-destinations` restricts which destination names are allowed to bind dynamically.
- `dynamic-destination-cache-size` adjusts how many dynamic output bindings are kept in the cache.

This is a local development configuration. Production must fetch addresses, usernames, and passwords from the deployment environment's secret/configuration management; do not commit real credentials into source control.

If the application uses auto-discovered binders by their default names, the binder names are typically `kafka` and `rabbit`. If custom binder configurations such as `kafkaWest` or `rabbitOps` are declared, pass those exact configuration names when calling `StreamBridge`.

## 4. Sending to a dynamic destination and specifying the binder

Suppose the system receives order events from a REST API. The order's region determines the target topic; audit events always go to RabbitMQ:

~~~java
import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.stereotype.Service;
import org.springframework.util.MimeTypeUtils;

record OrderCreated(
        String orderId,
        String customerId,
        Region region,
        long totalMinorUnits) {}

record AuditEvent(
        String eventId,
        String action,
        String aggregateId) {}

enum Region {
    EU,
    US
}

@Service
class OrderEventPublisher {

    private final StreamBridge streamBridge;

    OrderEventPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    boolean publishOrder(OrderCreated event) {
        String destination = switch (event.region()) {
            case EU -> "orders.eu";
            case US -> "orders.us";
        };

        return streamBridge.send(
                destination,
                "kafkaWest",
                event,
                MimeTypeUtils.APPLICATION_JSON);
    }

    boolean publishAudit(AuditEvent event) {
        return streamBridge.send(
                "audit.events",
                "rabbitOps",
                event,
                MimeTypeUtils.APPLICATION_JSON);
    }
}
~~~

In `publishOrder`, `orders.eu` or `orders.us` is the dynamic binding/destination name; `kafkaWest` selects the Kafka binder. In `publishAudit`, `audit.events` is the dynamic destination name and `rabbitOps` selects the Rabbit binder.

This example uses `MimeTypeUtils.APPLICATION_JSON` to request JSON payload conversion. The three-argument overload can be used if the binding's default content type is suitable. When passing a Spring `Message`, the content type in the message headers is also respected via content-type negotiation.

When a destination is created for the first time, the corresponding binder performs binding and provisions broker resources if the binder is configured to allow it. Subsequent sends can reuse the cached output binding.

## 5. Do not accept arbitrary binder names from external requests

Do not write an API that directly takes both `destination` and `binderName` from an HTTP request and passes both values verbatim into `StreamBridge`:

~~~java
// Do not do this: clients could request binding to unintended resources.
streamBridge.send(request.destination(), request.binderName(), request.payload());
~~~

Dynamic destinations can cause a binder to create new topics or exchanges. If the destination name and binder are chosen by the client, the endpoint can inadvertently become an avenue for creating arbitrary resources, sending data to unintended brokers, or causing unbounded growth in bindings.

Instead, map validated business values to an allowed list of destinations and binders:

~~~java
String destination = switch (region) {
    case EU -> "orders.eu";
    case US -> "orders.us";
};

String binderName = "kafkaWest";
streamBridge.send(destination, binderName, event);
~~~

If each tenant has its own broker, obtain the binder name from managed tenant configuration and verify access permissions before sending. Do not trust arbitrary headers or query parameters to decide the broker.

## 6. Using dynamic-destinations to restrict destination names

The `spring.cloud.stream.dynamic-destinations` property serves as an allowlist for destinations permitted to bind dynamically:

~~~yaml
spring:
  cloud:
    stream:
      dynamic-destinations:
        - orders.eu
        - orders.us
        - audit.events
~~~

When this property is configured, only destinations in the list are allowed to bind dynamically. When unconfigured, the framework allows any dynamic destination by default.

This allowlist restricts destination names; it does not select a binder. Binder selection still must be performed via the `binderName` parameter of `StreamBridge.send` or the `binder` property of a static binding.

If the application needs routing by customer ID, you do not necessarily have to put every customer ID into the allowlist. Consider using a small set of stable partitioned topics such as `orders.eu` and placing `tenantId` in the key/header/payload per your data contract. This keeps destination counts and resource provisioning permissions well controlled.

## 7. Caching dynamic output bindings

`StreamBridge` caches dynamic output bindings so subsequent sends do not have to recreate bindings. The cache uses eviction; current documentation describes a default size of 10, adjustable via `spring.cloud.stream.dynamic-destination-cache-size`.

Example:

~~~yaml
spring:
  cloud:
    stream:
      dynamic-destination-cache-size: 128
~~~

Choose the size based on the number of concurrently active destinations, not the total number of customers or total topics that have ever existed. When the number of destinations exceeds the cache size, an older binding may be evicted and have to be recreated the next time it is used; this can increase latency on the next send.

Do not set an extremely large cache size to mask a destination model with unbounded cardinality. If the application creates a new destination per request or per user, revisit your data partitioning model and broker resource lifecycle.

## 8. Important rule: a binding name does not switch its binder

The `binderName` parameter takes effect when `StreamBridge` creates a dynamic binding. If the binding was pre-created via `spring.cloud.stream.output-bindings`, or the binding name was already created with a different binder, a `binderName` passed in a later call will not change that binding's binder.

Example:

~~~java
streamBridge.send("orders.out", "kafkaWest", event1);

// Do not reuse the same binding name expecting to switch the existing binding to Rabbit.
streamBridge.send("orders.out", "rabbitOps", event2);
~~~

After the first call, `orders.out` has already been created with `kafkaWest`. The second call is not a way to switch the existing binding over to `rabbitOps`.

If you need to send to two brokers using the same logical destination, create two static output bindings with different names and map both to the corresponding destination:

~~~yaml
spring:
  cloud:
    stream:
      output-bindings: ordersKafka;ordersRabbit
      bindings:
        ordersKafka:
          destination: orders.events
          binder: kafkaWest
        ordersRabbit:
          destination: orders.events
          binder: rabbitOps
~~~

Send through each binding:

~~~java
streamBridge.send("ordersKafka", event);
streamBridge.send("ordersRabbit", event);
~~~

Here, each binding already has an explicitly configured binder. There is no need to pass `binderName` when calling `send`; the binding name resolves to its static configuration. Two brokers can share the same logical destination name, while each binding is managed separately.

## 9. Static or dynamic binder selection?

| Need | Suitable approach |
|---|---|
| All messages always go to one fixed Kafka topic | Static output binding with `binder: kafkaWest` |
| Destination varies by region but only uses Kafka | `StreamBridge.send(destination, "kafkaWest", data)` |
| Destination varies and may go to Kafka or RabbitMQ | Pass `binderName` explicitly for each dynamic binding creation |
| Two brokers need to receive the same logical destination | Two separate static output bindings, each specifying its binder |
| Only want to change the default for bindings without an explicit binder | `spring.cloud.stream.default-binder` |
| Want to restrict dynamic destinations | `spring.cloud.stream.dynamic-destinations` |

If the set of destinations is known in advance and each target needs specific producer configuration, static output bindings are usually easier to operate. Dynamic bindings are useful when destinations are genuinely decided only at runtime and can be governed via allowlists, caching, provisioning permissions, and monitoring.

## 10. Dedicated binder configuration for multiple brokers of the same type

An application can connect to two Kafka clusters or two RabbitMQ brokers. In this case, `type` is the same, while the binder configuration names differ:

~~~yaml
spring:
  cloud:
    stream:
      binders:
        kafkaPrimary:
          type: kafka
          environment:
            spring:
              kafka:
                bootstrap-servers: kafka-primary.internal:9092
        kafkaArchive:
          type: kafka
          default-candidate: false
          environment:
            spring:
              kafka:
                bootstrap-servers: kafka-archive.internal:9092
~~~

Each configuration can be selected individually:

~~~java
streamBridge.send("orders.live", "kafkaPrimary", event);
streamBridge.send("orders.archive", "kafkaArchive", event);
~~~

`kafkaPrimary` and `kafkaArchive` are two binder names, even though both have `type: kafka`. When selecting a specific broker, do not pass the generic value `kafka` if the application has declared multiple binder configurations of the same type and requires routing to a specific instance.

When configuring binders explicitly, declare all binders used by the application. Enabling custom binder configuration may prevent the default binder discovery process from applying as before. `default-candidate: false` is helpful when a binder should only be selected by explicit name and should not participate in default selection.

## 11. Binder name and binder type

`type` in binder configuration specifies the integration type, such as `kafka` or `rabbit`. The key name under `spring.cloud.stream.binders` is the binder configuration name referenced by the application, such as `kafkaPrimary`, `rabbitOps`.

The current API uses the parameter name `binderName`. Some older version documentation uses the name `binderType`; check the `StreamOperations`/`StreamBridge` API for the exact Spring Cloud Stream version managed by your application's Spring Cloud BOM. The intent to preserve is selecting a configured binder identifier, not a data type or destination name.

Example:

~~~yaml
spring:
  cloud:
    stream:
      binders:
        rabbitOps:
          type: rabbit
~~~

In this case, to select the configuration above, pass `rabbitOps` as the binder name argument. If there is only an auto-discovered Rabbit binder without a custom configuration declared, the binder name is typically `rabbit`.

## 12. Selecting a default binder does not replace destination-based selection

`spring.cloud.stream.default-binder` specifies the default binder for bindings that have not specified a binder. This is an application-wide fallback, not a destination-name routing rule.

Example:

~~~yaml
spring:
  cloud:
    stream:
      default-binder: kafkaWest
~~~

If you call:

~~~java
streamBridge.send("orders.eu", event);
~~~

and `orders.eu` is a dynamic binding not yet created, the framework uses the default binder. If you want to send to RabbitMQ in an application where Kafka is the default, specify:

~~~java
streamBridge.send("audit.events", "rabbitOps", event);
~~~

Do not rely on dependency ordering or binder order on the classpath to choose a broker. When multiple binders are present, the choice must be expressed in configuration or in the send call's argument.

## 13. Message payload and content type

`StreamBridge.send` accepts `Object`, so you can pass a POJO or a Spring `Message`. The framework applies the same output conversion, content type, and partitioning pipeline as function/supplier outputs.

Sending a POJO with an explicit content type:

~~~java
streamBridge.send(
        "orders.eu",
        "kafkaWest",
        event,
        MimeTypeUtils.APPLICATION_JSON);
~~~

Or building a message with headers:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.util.MimeTypeUtils;

Message<OrderCreated> message = MessageBuilder
        .withPayload(event)
        .setHeader("event-source", "order-api")
        .setHeader("schema-version", "1")
        .setHeader("contentType", MimeTypeUtils.APPLICATION_JSON)
        .build();

streamBridge.send("orders.eu", "kafkaWest", message);
~~~

If a `Message` is passed, the content type in the header is used during conversion per Spring Cloud Stream's mechanism. Ensure consumer-side serializers/deserializers are compatible with the sent format. Selecting a binder does not automatically synchronize schemas between Kafka and RabbitMQ; each broker/binding still needs an explicit message contract.

## 14. Return value of send

The `send` overloads return a boolean. `true` indicates the message was sent through the output channel; `false` indicates the channel did not accept the message. Binder configuration errors, provisioning errors, or conversion errors may throw exceptions.

Example handling the result:

~~~java
boolean accepted = streamBridge.send(
        "orders.eu",
        "kafkaWest",
        event,
        MimeTypeUtils.APPLICATION_JSON);

if (!accepted) {
    throw new IllegalStateException("Output channel rejected the event");
}
~~~

By default, `StreamBridge` uses the calling thread and the send operation is blocking. If async mode is enabled via `streamBridge.setAsync(true)`, sending is performed asynchronously. In that case, do not treat the returned boolean as final confirmation that the broker has persisted the message; monitor asynchronous send errors per the binder's mechanism and configure appropriate observability.

If business logic requires durable confirmation, check the acknowledgement semantics of the binder and broker in use. Selecting the right binder only determines where to send; it does not automatically provide exactly-once or durability guarantees for messages.

## 15. Provisioning and broker permissions

When creating a dynamic destination, the binder may need permissions to create topics, exchanges, or related resources. Provisioning behavior depends on the binder and broker configuration:

- The Kafka binder can provision topics if the account has permissions and auto-create is allowed.
- The Rabbit binder can declare exchanges/queues/bindings based on producer and binder configuration.
- Destination names must follow system conventions and broker policies.
- Production environments may require pre-creating resources via infrastructure pipelines rather than letting applications auto-provision.

If the application lacks permissions to create resources, dynamic binding may fail even when `binderName` is right. Distinguish binder selection errors from connectivity, authentication, authorization, or provisioning errors.

## 16. Monitoring and limiting destination counts

When using dynamic destinations across multiple binders, monitor at minimum:

- Send count per binder and destination.
- Cached dynamic binding count and cache eviction count.
- Rate of `send` returning `false`.
- Exceptions when creating bindings or provisioning resources.
- Send latency and connection errors per broker.
- Number of new destinations created within a time window.

Do not put sensitive payloads or credentials into logs. Logs should include event ID, binding name, binder name, allowed destination, and send result.

Set limits on allowed destination counts and resource-creation permissions on the broker. If a misconfigured tenant causes every request to generate a new destination, allowlists, caches, and quotas help contain the impact.

## 17. Testing binder selection

Tests should verify both the selected binder and the resource receiving the message:

1. Configure two binders, send a dynamic destination with `kafkaWest`, and verify the record appears in Kafka.
2. Send another destination with `rabbitOps`, and verify the message appears on RabbitMQ.
3. Send a destination not listed in `dynamic-destinations`, and verify the binding is not created.
4. Send to the same binding name with a different binder after the first binding was already created; verify the application does not rely on that call to switch binders.
5. Start with a static output binding and `binder` property; verify the static binder takes precedence per configuration.
6. Test `default-binder` when calling an overload without passing a binder name.
7. Verify JSON payloads, content types, and headers on the consumer side.
8. Simulate authentication/provisioning errors on one broker; verify logs and metrics pinpoint the right binder.
9. Test cache eviction when the destination count exceeds the cache size.

`StreamOperations` can be used in unit tests instead of depending directly on the `StreamBridge` class, as `StreamBridge` implements this contract. Integration tests still require real binders or an equivalent broker environment to verify routing and provisioning.

## 18. Common errors

| Symptom | Possible cause | Resolution |
|---|---|---|
| Messages always go to Kafka even when RabbitMQ is intended | Calling the two-argument overload or relying on the default binder | Use `send(bindingName, binderName, data)` |
| Binder not found | Passing the wrong binder configuration name | Use the exact key name under `spring.cloud.stream.binders` |
| Second call still uses the old binder | The binding name was already created earlier with another binder | Use a separate binding name or declare two static output bindings |
| `binderName` has no effect | The binding was pre-created via `output-bindings` or static config | Only use this argument for dynamic bindings not yet created |
| Dynamic binding rejected | Destination is not in the allowlist | Add approved destinations or fix mapping |
| Too many bindings created | Destinations generated from unbounded values | Constrain destinations and adjust partitioning model |
| Binding fails to create | Broker disallows provisioning or credentials lack permissions | Check permissions and pre-create resources per policy |
| No default binder | Multiple binders exist without a default or without passing binder name | Set `default-binder` or specify the binder explicitly |
| Consumer cannot decode | Content type/schema mismatch | Align serializers, converters, and schemas |

## 19. Pre-release checklist

- Determine whether destinations are static bindings or dynamic destinations.
- Distinguish `bindingName`, `destination`, and `binderName` in every send call.
- Declare complete binder configurations and separate broker connections.
- Use exact binder configuration names in `StreamBridge.send`.
- Set `default-binder` if the application needs a default choice.
- Use `dynamic-destinations` to restrict dynamically bindable destinations.
- Do not let clients pass arbitrary destinations or binder names.
- Do not reuse a binding name expecting to switch to another binder after the binding is created.
- Use separate static output bindings if the same logical destination is needed across multiple brokers.
- Size the cache according to concurrently active destinations.
- Verify content type, serializers, and schemas on the consumer side.
- Verify resource provisioning permissions on each broker.
- Monitor send results, binder errors, cache evictions, and destination counts.
- Test routing with each binder in an integration environment.

When sending to dynamic destinations in a multi-binder application, select the binder at binding creation time using the `StreamBridge.send(bindingName, binderName, data)` overload. The binder name must match a binder configuration in the application; the destination name is still supplied separately via the binding name. Static bindings specify the binder in configuration, while dynamic bindings pass the binder name upon first creation. Combine explicit selection with allowlists, bounded caches, provisioning permissions, and per-broker testing to avoid routing to the wrong system or creating uncontrolled destinations.

## References

- [Spring Cloud Stream 5.0 — Producing and Consuming Messages: StreamBridge](https://docs.spring.io/spring-cloud-stream/reference/5.0/spring-cloud-stream/producing-and-consuming-messages.html)
- [Spring Cloud Stream 5.0 — Multiple Binders on the Classpath](https://docs.spring.io/spring-cloud-stream/reference/5.0/spring-cloud-stream/multiple-binders.html)
- [Spring Cloud Stream 5.0 — Connecting to Multiple Systems](https://docs.spring.io/spring-cloud-stream/reference/5.0/spring-cloud-stream/multiple-systems.html)
- [Spring Cloud Stream — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
- [StreamBridge API — Spring Cloud Stream 5.0.2](https://javadoc.io/static/org.springframework.cloud/spring-cloud-stream/5.0.2/spring.cloud.stream/org/springframework/cloud/stream/function/StreamBridge.html)
