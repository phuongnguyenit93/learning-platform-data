# Boundary Between Spring Boot Auto-Configuration and Manual Configuration

Spring Kafka provides components for sending and receiving records such as `KafkaTemplate`, `ProducerFactory`, `ConsumerFactory`, and listener containers. Spring Boot can automatically create and wire most of these components based on dependencies on the classpath and `spring.kafka.*` properties. When an application has custom needs, you can add a bean or replace only the exact component that needs customization. Switch to full manual configuration only when the application genuinely requires controlling how Kafka clients are created and managed throughout their lifecycle.

This boundary matters because auto-configuration gets an application started quickly and keeps settings consistent; manual configuration gives deeper control, but also makes the application responsible for wiring components, managing multiple configurations, and maintaining them during upgrades.

## 1. Configuration Layers in a Spring Kafka Application

A Spring Boot application using Spring Kafka typically has the following layers:

1. **Dependencies:** Spring Kafka and Kafka client libraries present on the classpath.
2. **External configuration:** `application.yml`, environment variables, or other configuration sources supplying brokers, serializers, deserializers, group ID, security, and listener options.
3. **Spring Boot auto-configuration:** reads `KafkaProperties`, evaluates conditions, and registers default beans if the application has not provided matching beans.
4. **Application configuration:** declares extra beans or replaces part of the default configuration for business requirements.
5. **Application code:** sends events via `KafkaTemplate` and receives events via `@KafkaListener`.

The initialization flow can be visualized as follows:

```mermaid
flowchart TD
    A[Spring Kafka dependencies] --> C[Kafka auto-configuration]
    B[application.yml / environment] --> D[KafkaProperties]
    D --> C
    C --> E[ProducerFactory and KafkaTemplate]
    C --> F[ConsumerFactory and listener container factory]
    C --> G[KafkaAdmin and related components]
    H[Application custom beans] --> C
    E --> I[Producer code]
    F --> J[@KafkaListener]
    I --> K[Kafka cluster]
    J <--> K
    G <--> K
```

The diagram shows the boundary of responsibilities: Boot stands up foundational beans when conditions are satisfied; the application decides which pieces need adjustment for real-world requirements.

## 2. What Does Auto-Configuration Do?

When the required dependencies are present, Spring Boot registers Kafka-related auto-configurations. Depending on the Boot version and application conditions, the provided set of beans commonly includes:

- `ProducerFactory` to create Kafka producers.
- `ConsumerFactory` to create Kafka consumers.
- `KafkaTemplate` to send records.
- `KafkaAdmin` to perform administrative operations such as declaring topics via `NewTopic` beans.
- A default `ConcurrentKafkaListenerContainerFactory` to create listener containers for `@KafkaListener`.
- Supporting components for transactions or Kafka Streams when matching configuration and dependencies are present.

Exact beans also depend on the classpath, configuration properties, and application-registered beans. Do not treat the list above as a guarantee that every bean always appears in every application.

`KafkaProperties` is a typed configuration object bound from the `spring.kafka` property group. Boot uses it to construct settings for Kafka clients and listener infrastructure. For example, `spring.kafka.producer.*` targets producers, `spring.kafka.consumer.*` targets consumers, `spring.kafka.listener.*` targets listener containers, and `spring.kafka.template.*` targets `KafkaTemplate`.

Auto-configuration typically relies on conditions such as:

| Condition | Meaning |
|---|---|
| Classpath condition | Applies only when required classes or libraries are present |
| Missing-bean condition | Creates a default bean only when no matching bean already exists in the context |
| Property condition | Activates a configuration branch only when properties satisfy conditions |
| Configuration import | Loads related configurations when the foundational configuration is active |

This explains why adding a dependency can introduce Kafka beans the application did not declare directly, and why declaring a custom bean in the application can prevent the corresponding default bean from being created.

## 3. Starting with `spring.kafka.*` Properties

If the requirement is simply selecting brokers, serializers, deserializers, consumer group, or acknowledgement mode, property-based configuration is usually the best choice. Example:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      acks: all
    consumer:
      group-id: billing-v1
      auto-offset-reset: earliest
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        "[spring.json.trusted.packages]": com.example.orders
    listener:
      ack-mode: record
```

In this example, Boot uses the same broker addresses for all clients unless overridden under producer or consumer. The producer sends string keys and JSON values; the consumer uses group `billing-v1`, starts from retained logs when no valid committed offset exists, and the listener container commits record-by-record after the listener finishes processing.

Property groups have distinct scopes:

| Group | Example | Affected components |
|---|---|---|
| `spring.kafka.bootstrap-servers` | `localhost:9092` | Default brokers for clients |
| `spring.kafka.producer.*` | `acks`, serializers, retries | Producers and producer factory |
| `spring.kafka.consumer.*` | `group-id`, deserializers, reset policy | Consumers and consumer factory |
| `spring.kafka.listener.*` | `ack-mode`, concurrency, poll timeout | Listener container |
| `spring.kafka.template.*` | `default-topic`, timeout | `KafkaTemplate` |
| `spring.kafka.admin.*` | fail-fast, operation timeout | `KafkaAdmin` |
| `spring.kafka.properties.*` | native Kafka client properties | Clients sharing common configuration |

For security properties such as SASL, SSL, or truststores, you can use Boot-supported properties or corresponding native Kafka properties. Secrets should be supplied via environment variables or a secret management system; never commit passwords or private keys to the repository. When a native property and a typed property configure the same key, avoid duplicate declarations and verify the effective client configuration for your Boot version.

Prefer typed properties when Boot provides them because property names are explicit and easier to validate. Use `spring.kafka.*.properties` for Kafka client options without dedicated Boot properties.

## 4. Customizing a Part While Keeping Auto-Configuration

A specific requirement does not mean you must manually construct all Kafka beans. Auto-configuration is designed so applications can replace individual pieces. For example, if you only want to set a default topic on `KafkaTemplate`, you can declare your own `KafkaTemplate` bean and continue using the `ProducerFactory` provided by Boot:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.ProducerFactory;

@Configuration
class KafkaTemplateConfiguration {

    @Bean
    KafkaTemplate<Object, Object> kafkaTemplate(
            ProducerFactory<Object, Object> producerFactory) {

        KafkaTemplate<Object, Object> template =
                new KafkaTemplate<>(producerFactory);
        template.setDefaultTopic("orders");
        return template;
    }
}
```

When the context already contains a matching `KafkaTemplate` bean, the auto-configuration method that creates the default `KafkaTemplate` under a missing-bean condition backs off. `ProducerFactory` can still come from Boot, so configured serializers, brokers, and producer properties remain in effect.

This illustrates the principle of **replacing only the bean you need to replace**. Check the bean conditions in the Spring Boot version you use: some conditions check by bean type, while others check by bean name. Do not assume that adding any bean with similar functionality disables all Kafka auto-configuration.

## 5. Creating a Dedicated Listener Container Factory for a Listener Group

Suppose most listeners process records one by one, but one listener needs batch delivery to optimize database writes. You can create an additional container factory sharing Boot's `ConsumerFactory`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.boot.autoconfigure.kafka.ConcurrentKafkaListenerContainerFactoryConfigurer;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;

@Configuration
class BatchListenerConfiguration {

    @Bean("ordersBatchFactory")
    ConcurrentKafkaListenerContainerFactory<Object, Object> ordersBatchFactory(
            ConcurrentKafkaListenerContainerFactoryConfigurer configurer,
            ConsumerFactory<Object, Object> consumerFactory) {

        var factory = new ConcurrentKafkaListenerContainerFactory<Object, Object>();
        configurer.configure(factory, consumerFactory);
        factory.setBatchListener(true);
        factory.setConcurrency(3);
        return factory;
    }
}
```

The listener selects this factory by bean name:

```java
import java.util.List;
import org.springframework.stereotype.Component;
import org.springframework.kafka.annotation.KafkaListener;

@Component
class OrdersBatchListener {

    private final OrderBatchService orderBatchService;

    OrdersBatchListener(OrderBatchService orderBatchService) {
        this.orderBatchService = orderBatchService;
    }

    @KafkaListener(
            topics = "orders",
            groupId = "billing-batch-v1",
            containerFactory = "ordersBatchFactory")
    public void onOrders(List<OrderCreated> orders) {
        orderBatchService.processBatch(orders);
    }
}
```

The example uses `ConcurrentKafkaListenerContainerFactoryConfigurer` to apply Boot's shared listener properties to the new factory before enabling batching and setting custom concurrency. That way, shared settings such as acknowledgement mode and Boot-supported container customizations are still inherited. Payload types and parameter signatures must match the deserializer, message converter, and Spring Kafka version of the application. The default factory continues serving other listeners. Thus, a custom concurrency or batch requirement can be isolated without replacing the entire consumer infrastructure.

Note that `concurrency` creates consumer threads for the container. The number of consumers actually assigned partitions still depends on partition counts, group membership, and rebalance state. Setting concurrency higher than the partition count does not increase how many partitions can be processed in parallel within the same group.

## 6. When Do You Need to Replace `ProducerFactory` or `ConsumerFactory`?

`ProducerFactory` and `ConsumerFactory` sit closer to the Kafka client boundary. Consider replacing or adding them when requirements cannot be expressed cleanly via properties alone, such as:

- Producers and consumers must connect to different clusters.
- One flow requires its own serializer, deserializer, or interceptor.
- Customizing how Kafka clients are cached, instantiated, or closed.
- Certain listeners require consumers with distinct isolation levels, client IDs, or security identities.
- The application serves multiple tenants or multiple processing flows requiring independent Kafka configurations.

Before writing a new factory, verify whether standard `spring.kafka.producer.*` or `spring.kafka.consumer.*` settings already solve the requirement. If only a few native client properties need tweaking, adding them to configuration is usually simpler than building maps manually.

When creating a custom factory, you become responsible for all critical properties of the corresponding client: bootstrap servers, serializers/deserializers, security, timeouts, retries, acknowledgements, isolation level, and related settings. If the new factory should still share common Boot configuration, derive settings from `KafkaProperties` or Boot-supported customizer mechanisms, then override only what must differ. Avoid copying a standalone configuration map that easily misses security updates or new properties during upgrades.

When multiple factories of the same type exist, give beans clear names and use `@Qualifier` at injection points. If one default bean should be injected when no qualifier is specified, `@Primary` may be considered; do not use `@Primary` to mask choosing the wrong cluster.

## 7. Full Manual Configuration and Excluding Auto-Configuration

Exclude Kafka auto-configuration only when the application needs to take full ownership of creating and wiring foundational components, such as a multi-cluster application with custom architecture or a runtime integrating Kafka in a specialized way.

Auto-configuration can be excluded via annotation on the application class:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.kafka.KafkaAutoConfiguration;

@SpringBootApplication(exclude = KafkaAutoConfiguration.class)
public class MessagingApplication {

    public static void main(String[] args) {
        SpringApplication.run(MessagingApplication.class, args);
    }
}
```

After excluding it, the application must explicitly declare the beans needed for its design, such as:

- `ProducerFactory` and `KafkaTemplate` for the sending flow.
- `ConsumerFactory` and `ConcurrentKafkaListenerContainerFactory` for the receiving flow.
- `KafkaAdmin` if the application manages topics via Spring.
- Transaction manager and transaction configuration if Kafka transactions are needed.
- Annotation-driven infrastructure for `@KafkaListener` if the excluded auto-configuration previously provided it.

With completely manual listener configuration, you typically need to enable annotation infrastructure with `@EnableKafka` and register an appropriate listener container factory. Review the excluded auto-configuration list and other configurations in the application to avoid accidentally dropping a component the application still relies on.

Excluding `KafkaAutoConfiguration` is a broad change. It is not the tool for adjusting one timeout or swapping a serializer. If only a single custom bean is needed, keep auto-configuration and replace the bean at a narrower scope.

## 8. Choosing the Right Configuration Level

The table below helps decide where to stop:

| Need | Configuration level to choose | Reason |
|---|---|---|
| Change broker, group ID, serializer, deserializer, retry, or security property | `application.yml` / environment | Boot already provides matching properties or supports native client properties |
| Set default topic, message converter, or shared listener behavior | Custom bean or customizer | Replaces only what is needed while keeping default factories |
| One listener needs custom batching, concurrency, or error handling | Additional container factory | Isolates behavior for that listener group |
| One flow needs a consumer/producer with different config | Separate factory and qualifier | Lets remaining flows keep default configuration |
| Multiple clusters, multi-tenant, or specialized client lifecycle | Intentional manual configuration | Application needs explicit control over each factory, template, and listener container |

A practical rule is to start with properties, then customize individual beans, and only then build custom factories or exclude auto-configuration. Every deeper step increases the configuration surface the team must maintain.

## 9. Common Misconceptions

| Misconception | Reality | How to handle |
|---|---|---|
| Having `spring.kafka.*` means no need to understand beans | Properties are just inputs; Boot uses them to build and wire beans | Know which beans receive which settings when debugging or extending |
| Creating one custom Kafka bean disables all auto-configuration | Missing-bean conditions typically back off only the specific replaced bean | Check conditions and bean types of each configuration |
| Adding `@Primary` resolves every conflict | `@Primary` only prioritizes a candidate during injection; it does not satisfy every condition | Use qualifiers to explicitly select a factory or cluster |
| Every listener must use a single container factory | You can declare multiple factories and pick via `containerFactory` | Separate listeners by batching, concurrency, or error handling |
| Manual configuration always yields better performance | Custom factories do not automatically make Kafka faster | Measure bottlenecks before changing architecture |
| Excluding auto-configuration is an easy way to change one property | Excluding drops an entire group of related default beans | Exclude only when intending to manage every affected piece yourself |
| `@KafkaListener` creates everything without configuration | Listeners require an appropriate container factory, consumer factory, and deserialization config | Inspect which factory the listener uses and its payload config |

## 10. Diagnosing Missing or Replaced Auto-Configured Beans

When a Kafka bean is missing from the context or the application uses the wrong factory, check in this order:

1. **Classpath:** are Spring Kafka and Kafka client dependencies on the runtime classpath?
2. **Properties:** do `spring.kafka.*` keys have the right prefix, data types, and active profile?
3. **Condition evaluation:** was auto-configuration imported, and which conditions matched or did not match?
4. **Competing beans:** did the application or another library register a bean with the same type/name?
5. **Injection point:** did `@Qualifier`, `@Primary`, or generic types cause Spring to select a different bean?
6. **Listener mapping:** does `@KafkaListener` point to the intended `containerFactory`?

You can enable the condition report with `--debug` when running Spring Boot:

```bash
java -jar messaging-service.jar --debug
```

The condition evaluation report shows which configurations were applied and why others were skipped. If Spring Boot Actuator is enabled, the `conditions` endpoint can also aid inspection; expose this endpoint only according to your environment's operational and security policies.

During debugging, verify the actual injected beans and effective client configuration. Reading a YAML file alone is not enough to conclude a consumer uses the right group, cluster, or deserializer, especially with multiple profiles and custom factories.

## 11. Pre-Production Configuration Checklist

- Start with `spring.kafka.*` for every option Boot supports.
- Identify the exact bean to replace before adding a `@Bean`.
- Use separate factories when there are genuine differences in cluster, serializers, security, or listener behavior.
- Give clear names and qualifiers when multiple `ProducerFactory`, `ConsumerFactory`, or container factories exist.
- Avoid mixing the same native property across multiple places without understanding precedence.
- Manage credentials outside source code and verify configuration per environment profile.
- Exclude auto-configuration only after listing every bean the application will manage itself.
- Use the condition report and inspect actual beans whenever startup behavior differs from expectations.

In a Spring Kafka application, auto-configuration is the default foundation for wiring clients and listeners. Manual configuration is an extension tool where specific requirements demand it. Understanding bean creation conditions and the boundaries between properties, factories, templates, and listener containers helps keep configuration clear while supporting complex messaging flows.
