# Managing Destination Addresses and Resource Limits via Externalized Configuration

> Objective: move queue names, topics, destinations, and operational limits out of source code; configure them separately per environment; and control consumer concurrency, in-flight message volume, payload size, and other limits so Spring Messaging applications operate reliably.

## 1. Why Externalized Configuration Is Needed

Messaging applications typically run across multiple environments such as local, test, staging, and production. Each environment may use different brokers, virtual hosts, queues, topics, exchanges, or routing keys. Resource capacity also varies: production may allow more consumers, larger prefetch counts, or different payload limits than development environments.

If these values are hardcoded in source code, every destination rename or load adjustment requires modifying code and releasing the application again. Externalized configuration enables:

- Changing destination addresses without modifying business logic.
- Setting limits aligned with CPU, memory, database pools, and broker capacity.
- Using the same build artifact across multiple environments.
- Validating configuration at startup and catching invalid values early.
- Managing operational changes through configuration, deployment workflows, and separate access controls.

In Spring, distinguish **external destination names** from **in-application MessageChannels**. A `MessageChannel` is a message-sending abstraction; depending on how it is configured, it may only connect beans within the same process. Queues, topics, exchanges, or destinations are resources of a specific messaging system. A channel is not automatically equivalent to a broker queue.

## 2. Destination Addresses Depend on the Messaging Platform

Naming and routing mechanisms differ by technology:

| Platform | Commonly configured addresses or resources | Meaning |
|---|---|---|
| JMS | Queue or Topic name | Destination that producers send to and consumers subscribe to |
| RabbitMQ | Exchange, routing key, queue, binding | Exchange routes messages per exchange type and bindings; queue stores messages for consumers |
| Kafka | Topic and consumer group | Topic stores records; consumer group coordinates assigning partitions to consumers |
| Internal Spring Messaging | Bean name or MessageChannel | In-application channel connecting senders and handlers |

Do not lump every address type into a single concept of "queue". For example, a RabbitMQ producer typically publishes to an exchange with a routing key; a Kafka producer writes to a topic; a JMS producer sends to a queue or topic. Configuration should reflect the exact model of the broker in use.

Destination names can be declared in configuration files, environment variables, or configuration management systems. Queue/topic infrastructure usually needs to be provisioned beforehand using administrative tools, IaC, or broker provisioning policies. Putting a name in `application.yaml` does not mean that resource automatically exists on the broker.

## 3. Spring Boot Externalized Configuration

Spring Boot supports loading configuration from multiple sources such as `application.properties`, `application.yaml`, profile-specific files, environment variables, Java system properties, and command-line arguments. External sources can override defaults packaged inside the application according to Spring Boot's property precedence rules.

Example declaring a destination and several limits in `application.yaml`:

```yaml
app:
  messaging:
    orders:
      destination: ${ORDERS_DESTINATION:orders.incoming}
      concurrency: ${ORDERS_CONCURRENCY:2-8}
      max-payload-bytes: ${ORDERS_MAX_PAYLOAD_BYTES:262144}
```

Meaning:

- `destination` selects the queue or destination name for the order flow.
- `concurrency` is the concurrent consumer range in the JMS example, minimum 2 and maximum 8.
- `max-payload-bytes` is the application-enforced payload limit, here defaulting to 256 KiB.
- The `${ENV_VAR:default}` syntax allows using an environment variable when set, falling back to the default value otherwise.

Production can supply `ORDERS_DESTINATION=orders.prod.incoming` and other limits via the deployment environment. Profiles can also be used to separate development, test, and production values. Do not put broker passwords, tokens, or private keys directly into committed configuration files; retrieve secrets from a secret manager or the runtime environment's security mechanism.

## 4. Grouping Typed Configuration with @ConfigurationProperties

For a group of related properties, `@ConfigurationProperties` is usually easier to manage than scattered `@Value` strings. It groups configuration into a typed object, supports relaxed binding, and can combine with Bean Validation to validate values.

Example using Spring Boot 3 and Jakarta Validation:

```java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.messaging.orders")
public record OrdersMessagingProperties(
        @NotBlank String destination,
        @NotBlank
        @Pattern(regexp = "[1-9][0-9]*(?:-[1-9][0-9]*)?")
        String concurrency,
        @Min(1024) @Max(10485760) int maxPayloadBytes
) {
}
```

Register configuration scanning in the application:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class MessagingApplication {
    public static void main(String[] args) {
        SpringApplication.run(MessagingApplication.class, args);
    }
}
```

The annotations validate a non-blank destination, concurrency format, and payload limit from 1 KiB to 10 MiB. The regex for concurrency accepts formats like `2` or `2-8`; if you need to guarantee the minimum is not greater than the maximum, add a custom validator. If validation fails, the application should fail to start so it avoids running with invalid configuration.

If not using Spring Boot, beans can be configured via Java configuration, `Environment`, or `@Value`; `@ConfigurationProperties` is a utility belonging to Spring Boot.

## 5. Using Configured Destinations in Spring JMS

With JMS, a producer can send to a destination retrieved from properties. A listener can also use a placeholder in the `@JmsListener` annotation.

```java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
@EnableJms
class OrdersJmsConfiguration {
    @Bean("ordersListenerFactory")
    DefaultJmsListenerContainerFactory ordersListenerFactory(
            ConnectionFactory connectionFactory,
            OrdersMessagingProperties properties) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setConcurrency(properties.concurrency());
        return factory;
    }
}
```

Producer:

```java
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;

@Service
class OrdersPublisher {
    private final JmsTemplate jmsTemplate;
    private final OrdersMessagingProperties properties;

    OrdersPublisher(JmsTemplate jmsTemplate,
                    OrdersMessagingProperties properties) {
        this.jmsTemplate = jmsTemplate;
        this.properties = properties;
    }

    void publish(String jsonPayload) {
        jmsTemplate.convertAndSend(properties.destination(), jsonPayload);
    }
}
```

Listener:

```java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
class OrdersListener {
    @JmsListener(
            destination = "${app.messaging.orders.destination}",
            containerFactory = "ordersListenerFactory"
    )
    public void handle(String jsonPayload) {
        // Deserialize, validate, and process message.
    }
}
```

The destination name in both the producer and listener comes from the exact same property, avoiding cases where messages are sent to one queue while the listener listens on another. `DefaultJmsListenerContainerFactory.setConcurrency` configures the number of consumers for the listener container; the `2-8` format lets the container scale consumer count within that range according to the container's mechanism.

This code assumes the application has already configured `ConnectionFactory`, `JmsTemplate`, a message converter if needed, and that the broker has the corresponding destination. If the broker requires queues/topics to be pre-provisioned, create those resources outside the application.

## 6. Externalized Configuration for RabbitMQ and Kafka

The same externalized configuration principle applies to other brokers, though property names and limits depend on the integration.

### RabbitMQ

You can externalize the queue name to application configuration:

```yaml
app:
  messaging:
    orders:
      queue: ${ORDERS_QUEUE:orders.incoming}

spring:
  rabbitmq:
    listener:
      simple:
        concurrency: 2
        max-concurrency: 8
        prefetch: 20
```

A listener can reference the queue name:

```java
@RabbitListener(queues = "${app.messaging.orders.queue}")
public void handle(OrderMessage message) {
    // Process message.
}
```

The `spring.rabbitmq.listener.simple.*` properties apply to the simple listener container auto-configured by Spring Boot. `prefetch` limits how many unacknowledged messages the broker can deliver ahead of time per consumer under RabbitMQ's mechanism. Queue, exchange, routing key, and binding names still need to be configured to match the actual topology.

### Kafka

Example configuring a topic and poll limits:

```yaml
app:
  messaging:
    orders:
      topic: ${ORDERS_TOPIC:orders.events}

spring:
  kafka:
    consumer:
      max-poll-records: 100
      properties:
        max.poll.interval.ms: 300000
    listener:
      concurrency: 3
```

A listener can use the topic retrieved from configuration:

```java
@KafkaListener(topics = "${app.messaging.orders.topic}")
public void handle(OrderEvent event) {
    // Process record.
}
```

`max.poll.records` limits the number of records returned in a single poll. `max.poll.interval.ms` sets the maximum interval between polls before the consumer may be considered stalled and removed from the group. Listener concurrency should match the partition count and processing capacity; increasing concurrency beyond the number of assigned partitions does not automatically create useful extra parallelism.

Do not copy JMS configuration verbatim to RabbitMQ or Kafka. Choose the exact properties of the integration and broker being used.

## 7. Types of Resource Limits to Manage

### 7.1. Consumer Count and Concurrent Processing Threads

Concurrency determines how many consumers or listener workers process messages simultaneously. Increasing consumer count can raise throughput while the broker, CPU, and database still have headroom; however, it also increases connections, threads, transactions, and concurrent demand on downstream systems.

Set limits based on:

- Number of CPU cores and whether processing time is CPU-bound or I/O-bound.
- Number of database connections allocatable to listeners after subtracting what HTTP requests and other tasks use.
- Number of partitions or load-sharing capability of the queue/topic.
- Load capacity of APIs or services that consumers call downstream.
- Memory capacity for messages currently held in-process.

If each consumer requires a database connection, configuring 20 consumers when the connection pool only has 8 connections can leave most consumers waiting on a connection. Concurrency should stay within the application's overall resource budget.

### 7.2. Prefetch, Batching, and Pending In-Flight Messages

Prefetch is the number of messages the broker can pre-deliver to a consumer while prior messages remain unacknowledged, depending on the broker and protocol. High prefetch can reduce round trips, but also increases the number of messages sitting in consumer memory and can hurt fairness across consumers.

An initial estimate for delivered but unacknowledged messages in RabbitMQ is:

\[\text{in-flight messages} \approx \text{consumer count} \times \text{prefetch per consumer}\]

This is an estimate for one consumer group and a specific configuration scope; the actual count also depends on the number of queues, subscriptions, already received messages, and how the broker dispatches. Do not treat this as a system-wide memory bound.

With Kafka, `max.poll.records` limits how many records are returned per poll, while batch size and partitions affect how much data a consumer processes in one cycle. Balance batch processing time against `max.poll.interval.ms`.

### 7.3. Payload Size and Memory

A large message consumes memory in the producer, broker, network buffers, consumer, and potentially copies created during deserialization. Size limits should be enforced at multiple layers:

- **Producer/application:** check data size before sending.
- **Broker:** configure message or record limits according to broker capabilities.
- **Consumer:** reject or route payloads exceeding the application limit to separate handling.
- **Schema:** avoid embedding entire large files or bulky objects; store files in object storage and send a reference with proper access permissions instead.

Application limits and broker limits are two distinct controls. A `maxPayloadBytes` property in Java does not automatically configure the broker's limit. Align units of measurement, encoding, and handling of oversized messages.

### 7.4. Queue Depth, Retention Time, and Consumption Rate

Queues can absorb traffic spikes, but do not have infinite capacity. Monitor queue depth, age of the oldest message, publish/consume rates, redelivery counts, and dead letters. If the publish rate continuously exceeds the processing rate, queue length and latency will grow over time.

Consider queue length limits, message TTL, retention, overflow policies, and alerting. When a queue is full, define whether producers are blocked, rejected, or messages follow another broker policy.

### 7.5. Connections, Executors, and Retries

Beyond concurrency and prefetch, manage connection pools, session counts, thread pools, executor queue capacity, timeouts, and retry backoff. Avoid executors with unbounded queues if messages can arrive faster than they are processed; an unboundedly growing queue turns load pressure into out-of-memory errors.

Retries should have limits, backoff, and dead-lettering or an error-message handling workflow. Unlimited continuous retries can occupy all consumers and starve new messages. Do not retry permanent data errors such as invalid schemas the same way as transient connection errors.

## 8. Validating Payload Limits in the Application

Example of a listener receiving a JSON string and checking its UTF-8 byte length before processing:

```java
import java.nio.charset.StandardCharsets;

import org.springframework.stereotype.Component;

@Component
class OrdersPayloadValidator {
    private final OrdersMessagingProperties properties;

    OrdersPayloadValidator(OrdersMessagingProperties properties) {
        this.properties = properties;
    }

    void validate(String jsonPayload) {
        int payloadBytes = jsonPayload.getBytes(StandardCharsets.UTF_8).length;
        if (payloadBytes > properties.maxPayloadBytes()) {
            throw new IllegalArgumentException(
                    "Order message exceeds configured payload limit");
        }
    }
}
```

This snippet illustrates checking the string after the message has already been converted to `String`. If the application deserializes the payload before calling the validator, memory has already been allocated to construct objects. For strict protection against oversized payloads, check size at the receiving/serialization layer or broker configuration before deserializing. An exception from a listener can trigger redelivery depending on transactions, acknowledgements, and broker configuration; combine with bounded retries and dead-lettering.

## 9. Monitoring and Tuning Configuration

Do not pick limits based solely on a single default number. Measure under load testing and monitor in production:

- Throughput: number of messages sent and processed per second.
- Latency: time from publish to consume and consumer processing duration.
- Queue depth and age of oldest message.
- Active consumer count, busy thread count, and connection pool wait time.
- CPU, heap, garbage collection, and in-flight message volume.
- Retries, redeliveries, timeouts, and dead-letter rate.

Tune each group of settings in a controlled manner. Before increasing concurrency, check the database pool and downstream services. Before increasing prefetch, check heap and fairness. Before increasing max payload, check broker limits, network, and memory. Changing one parameter can shift the bottleneck to another component.

Properties bound at application startup usually do not automatically update every listener container when a configuration file changes. The common operational approach is deploying/restarting instances with the new configuration; if using refresh mechanisms or dynamic container updates, verify integration support and test the consumer lifecycle.

## 10. Common Configuration Mistakes

- **Hardcoding destinations in multiple classes:** producers and consumers can diverge on queue names when switching environments. Centralize values into a shared configuration group.
- **Confusing channel names with queue names:** Spring's internal channels do not automatically create resources on a broker.
- **Increasing concurrency without bounds:** can exhaust connection pools, CPU, or downstream capacity.
- **Setting prefetch too high:** consumers can hold many unprocessed messages, increasing heap usage and causing unbalanced load distribution.
- **Limiting payload size only in Java:** the broker may still accept or reject messages at a different limit; configure limits consistently across layers.
- **Not validating configuration:** blank destination names, malformed concurrency strings, or zero limits can cause confusing failures at runtime.
- **Changing a destination without provisioning the queue/topic:** the application may start, then fail on send/receive when the resource does not exist or permissions are missing.
- **Keeping configuration containing secrets in the repository:** credentials can leak through Git history and deployment logs.
- **Assuming editing a config file updates running listeners:** many properties are only applied when containers are created; use a restart workflow or a supported refresh mechanism.

## 11. Safe Deployment Workflow

1. Identify the actual destination type: JMS queue/topic, Rabbit exchange/queue/routing key, Kafka topic, or internal channel.
2. Declare destination names and limits in a clearly namespaced configuration group.
3. Use environment variables or environment-specific config sources to override defaults.
4. Bind configuration into typed objects and validate values at startup.
5. Provision queues, topics, exchanges, bindings, and access permissions using appropriate infrastructure tooling.
6. Set concurrency, prefetch/batch, payload size, timeouts, and retries based on the resource budget.
7. Measure throughput, latency, queue depth, heap, and downstream saturation under load testing.
8. Roll out changes with monitoring; verify listeners picked up the new configuration and have a rollback plan.

## 12. Conclusion

Destination addresses and resource limits are operational configuration and should be separated from business logic and managed per environment. Spring Boot provides externalized configuration and `@ConfigurationProperties` to bind, validate, and consume those values; integrations such as JMS, RabbitMQ, and Kafka have their own property sets for destinations and listeners.

Configure the right address type per broker, and bound concurrency, prefetch/batch, payloads, and queues based on real resource capacity. A sound configuration must be validated at startup, observed via metrics, and changed through a controlled deployment process.