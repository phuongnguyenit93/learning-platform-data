# Routing Templates with Qualifiers

A Spring Kafka application may need to send events to multiple topics, use multiple serializers, or connect to multiple Kafka clusters. In those cases, declaring multiple `KafkaTemplate` beans separates sending configuration by purpose. Spring uses `@Qualifier` to pick the right bean when injecting into services.

`@Qualifier` solves **dependency selection inside the Spring ApplicationContext**. It does not route records by key, select partitions, or choose clusters dynamically based on message contents. Business flows call the injected template; that template uses its backing `ProducerFactory` to send records.

## 1. Why are multiple KafkaTemplate beans needed?

`KafkaTemplate` is Spring Kafka's abstraction for sending records. Each template is built from a `ProducerFactory`, so it uses the producer settings supplied by that factory: bootstrap servers, serializers, security, retries, and other Kafka client properties.

In small applications, a single template can send to multiple topics:

```java
kafkaTemplate.send("orders", orderId, orderCreated);
kafkaTemplate.send("billing-events", orderId, billingEvent);
```

This works well when streams share the same cluster, serializers, and producer policy. However, as an application grows, separating templates by role can help:

| Template | Purpose | Possible differing configuration |
|---|---|---|
| `ordersKafkaTemplate` | Send order events | Default topic, payload type |
| `billingKafkaTemplate` | Send payment events | Default topic, serializer |
| `auditKafkaTemplate` | Send audit events | Separate cluster or security |
| `notificationKafkaTemplate` | Send notifications | Separate retries, timeouts, or cluster |

Separating templates makes intent clear in code. A service publishing invoices does not need to know bean names or how producers are built; it simply receives the dependency matching its role.

You do not need multiple templates merely because there are multiple topics. If topics share producer configuration and call sites pass topics explicitly, a single template can be simpler. Split only when configuration boundaries or sending responsibilities are meaningful.

## 2. Declaring multiple KafkaTemplate beans

Suppose two sending flows share the same Kafka cluster, serializers, and producer factory, but want dedicated templates with different default topics. You can declare two beans:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.ProducerFactory;

@Configuration
class KafkaTemplateConfiguration {

    @Bean("ordersKafkaTemplate")
    KafkaTemplate<Object, Object> ordersKafkaTemplate(
            ProducerFactory<Object, Object> producerFactory) {

        KafkaTemplate<Object, Object> template =
                new KafkaTemplate<>(producerFactory);
        template.setDefaultTopic("orders");
        return template;
    }

    @Bean("billingKafkaTemplate")
    KafkaTemplate<Object, Object> billingKafkaTemplate(
            ProducerFactory<Object, Object> producerFactory) {

        KafkaTemplate<Object, Object> template =
                new KafkaTemplate<>(producerFactory);
        template.setDefaultTopic("billing-events");
        return template;
    }
}
```

Both templates use the same `ProducerFactory`, so they share producer settings and client creation behavior. What differs in this example is the default topic. When calling `sendDefault()`, each template sends to its configured default topic.

This example also highlights an important point: bean names help Spring distinguish dependencies of the same type. Both beans have type `KafkaTemplate<Object, Object>`, so injecting by type alone yields multiple candidates.

Two templates sharing a factory also share `client.id` and the factory's producer management. Splitting templates by default topic alone does not create isolated metrics or quotas per template. If independent traffic tracking and rate limits are needed, create separate producer factories with dedicated client IDs and settings.

## 3. Using @Qualifier when injecting into services

`@Qualifier` specifies which bean a constructor parameter should receive. Prefer constructor injection so dependencies appear directly in the service signature:

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
class EventPublisher {

    private final KafkaTemplate<Object, Object> ordersTemplate;
    private final KafkaTemplate<Object, Object> billingTemplate;

    EventPublisher(
            @Qualifier("ordersKafkaTemplate")
            KafkaTemplate<Object, Object> ordersTemplate,
            @Qualifier("billingKafkaTemplate")
            KafkaTemplate<Object, Object> billingTemplate) {

        this.ordersTemplate = ordersTemplate;
        this.billingTemplate = billingTemplate;
    }

    void publishOrder(OrderCreated event) {
        ordersTemplate.sendDefault(event.orderId(), event);
    }

    void publishBilling(BillingCreated event) {
        billingTemplate.sendDefault(event.orderId(), event);
    }
}
```

When Spring instantiates `EventPublisher`, it looks up the bean matching each qualifier and injects it into the corresponding constructor parameter. Thus `ordersTemplate` always represents the order-sending template and `billingTemplate` represents the billing-event template.

In this example, `sendDefault(key, value)` uses the default topic set on each template. If you want to pick the topic per call, use `send(topic, key, value)`; the qualifier still selects the template, while the topic argument selects the destination within the cluster that the template connects to.

When a bean name is declared with `@Bean("ordersKafkaTemplate")`, Spring can also match by parameter name as a fallback qualifier. Writing `@Qualifier("ordersKafkaTemplate")` explicitly still makes intent obvious to readers and avoids relying on parameter-name inference.

## 4. Separating ProducerFactory when producer configs differ

Two templates sharing a factory only differ in call sites or default topics. If you need to connect to two different Kafka clusters, create two `ProducerFactory` beans with separate configurations and wire each template to its matching factory.

Example configuring a producer factory for an audit cluster:

```java
import java.util.HashMap;
import java.util.Map;

import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.StringSerializer;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.ProducerFactory;
import org.springframework.kafka.support.serializer.JsonSerializer;

@Configuration
class MultiClusterProducerConfiguration {

    @Bean("auditProducerFactory")
    ProducerFactory<Object, Object> auditProducerFactory(
            @Value("${app.kafka.audit.bootstrap-servers}")
            String bootstrapServers) {

        Map<String, Object> properties = new HashMap<>();
        properties.put(
                ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
                bootstrapServers
        );
        properties.put(
                ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
                StringSerializer.class
        );
        properties.put(
                ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
                JsonSerializer.class
        );

        return new DefaultKafkaProducerFactory<>(properties);
    }

    @Bean("auditKafkaTemplate")
    KafkaTemplate<Object, Object> auditKafkaTemplate(
            @Qualifier("auditProducerFactory")
            ProducerFactory<Object, Object> producerFactory) {

        KafkaTemplate<Object, Object> template =
                new KafkaTemplate<>(producerFactory);
        template.setDefaultTopic("audit-events");
        return template;
    }
}
```

Corresponding environment property:

```yaml
app:
  kafka:
    audit:
      bootstrap-servers: audit-kafka-1:9092,audit-kafka-2:9092
```

In this example, `auditKafkaTemplate` uses only `auditProducerFactory`. Spring Boot's default producer factory can continue serving other business templates. A real configuration for a separate cluster must also include security, timeouts, acknowledgements, compression, and serializer/deserializer settings matching that cluster's requirements.

When creating multiple producer factories, put qualifiers both at dependency declaration sites and injection sites. Omitting the qualifier on a `ProducerFactory` parameter can prevent Spring from knowing which factory to use or cause it to inject the wrong factory when multiple beans share the same type.

## 5. Distinguishing qualifier, bean name, and @Primary

These three mechanisms are related but do not replace each other:

| Mechanism | Role | When to use |
|---|---|---|
| Bean name | Identifier of a bean in the ApplicationContext | Give clear names to each template or factory |
| `@Qualifier` | Narrows candidates when injecting a dependency | A service must pick one exact template |
| `@Primary` | Prioritizes one bean when injecting by type without an explicit qualifier | There is one default template for most existing code |

Example marking a default template:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;

@Bean("defaultKafkaTemplate")
@Primary
KafkaTemplate<Object, Object> defaultKafkaTemplate(
        ProducerFactory<Object, Object> producerFactory) {
    return new KafkaTemplate<>(producerFactory);
}
```

When a constructor injects `KafkaTemplate<Object, Object>` without a qualifier, Spring prefers the `@Primary` bean. When a constructor specifies `@Qualifier("auditKafkaTemplate")`, Spring picks the audit bean via the qualifier.

Do not use `@Primary` to express business routing. It only resolves default injection ambiguity; it does not inspect event types or record contents.

## 6. Generic types and multiple templates

Spring can use generic types to distinguish beans. For example:

```java
@Bean("orderTemplate")
KafkaTemplate<String, OrderCreated> orderTemplate(
        ProducerFactory<String, OrderCreated> producerFactory) {
    return new KafkaTemplate<>(producerFactory);
}

@Bean("invoiceTemplate")
KafkaTemplate<String, InvoiceCreated> invoiceTemplate(
        ProducerFactory<String, InvoiceCreated> producerFactory) {
    return new KafkaTemplate<>(producerFactory);
}
```

When injecting `KafkaTemplate<String, OrderCreated>`, generic types can help Spring select the right bean. However, if templates share identical generic types, qualifiers are required to tell them apart. Even when generic types differ, explicit qualifiers remain helpful when business meaning matters more than Java types.

Avoid injecting raw `KafkaTemplate` or overly broad wildcards when the application has multiple templates. Specific types let the compiler verify keys and payloads, while qualifiers let Spring pick the right instance.

## 7. Routing on runtime conditions

`@Qualifier` works when a service knows at construction or method time which template it needs. It does not dynamically pick a template from fields inside an event.

If the sending destination depends on event type or tenant at runtime, write an explicit business routing layer. For example:

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;

@Component
class EventRouter {

    private final KafkaTemplate<Object, Object> ordersTemplate;
    private final KafkaTemplate<Object, Object> billingTemplate;

    EventRouter(
            @Qualifier("ordersKafkaTemplate")
            KafkaTemplate<Object, Object> ordersTemplate,
            @Qualifier("billingKafkaTemplate")
            KafkaTemplate<Object, Object> billingTemplate) {
        this.ordersTemplate = ordersTemplate;
        this.billingTemplate = billingTemplate;
    }

    void publish(Object event) {
        if (event instanceof OrderCreated order) {
            ordersTemplate.sendDefault(order.orderId(), order);
            return;
        }

        if (event instanceof BillingCreated billing) {
            billingTemplate.sendDefault(billing.orderId(), billing);
            return;
        }

        throw new IllegalArgumentException(
                "Unsupported event type: " + event.getClass().getName()
        );
    }
}
```

The router class still uses qualifiers to receive the right dependencies. Runtime logic resides in `publish()`, which picks the template by event type. With many event types, you can replace the `if` chain with a strategy map, registry, or per-event-type publisher interface.

Do not construct bean names from untrusted data or let payloads look up arbitrary beans in the ApplicationContext. Map validated business values to an explicit strategy instead.

## 8. Handling send results and producer errors

Choosing the right template does not guarantee the broker acknowledged the record. `KafkaTemplate` send methods return a future so applications can observe outcomes asynchronously. In Spring Kafka 3.x, the send API uses `CompletableFuture`:

```java
ordersTemplate.sendDefault(event.orderId(), event)
        .whenComplete((result, exception) -> {
            if (exception != null) {
                log.error("Could not publish order event", exception);
                return;
            }

            var metadata = result.getRecordMetadata();
            log.info(
                    "Published order event to topic={}, partition={}, offset={}",
                    metadata.topic(),
                    metadata.partition(),
                    metadata.offset()
            );
        });
```

If using an older Spring Kafka version, the future type may be `ListenableFuture`. Use the API matching your application's library version.

Do not ignore the future result when business logic needs to know whether sending succeeded or failed. For critical flows, define retries, timeouts, error handling, and duplicate-handling strategy. Logs should capture topic, partition, and offset on success and root cause on failure; avoid logging sensitive payloads.

## 9. Testing template wiring

When multiple templates exist, common bugs are wrong qualifiers, nonexistent bean names, or templates wired to the wrong producer factory. You can inspect the ApplicationContext to verify beans are registered:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.kafka.core.KafkaTemplate;

@SpringBootTest
class KafkaTemplateWiringTest {

    @Autowired
    ApplicationContext context;

    @Test
    void registersNamedTemplates() {
        assertThat(context.getBean("ordersKafkaTemplate"))
                .isInstanceOf(KafkaTemplate.class);

        assertThat(context.getBean("billingKafkaTemplate"))
                .isInstanceOf(KafkaTemplate.class);
    }
}
```

This test confirms the bean names exist and have the expected type. Having Spring instantiate services with constructor qualifiers also tests wiring: if a qualifier fails to match, the context fails to start.

To verify a template actually sends to the expected cluster or topic, test at the producer integration level with a test broker or appropriate mocked producer factory. Checking bean existence alone does not prove bootstrap servers, serializers, or default topics are right.

## 10. Common mistakes

| Symptom | Cause | Resolution |
|---|---|---|
| `NoUniqueBeanDefinitionException` when injecting template | Multiple beans of the same type without a qualifier or primary | Add `@Qualifier` to each constructor parameter |
| `NoSuchBeanDefinitionException` | Qualifier name does not match any registered bean or config class not scanned | Verify `@Bean` names, package scanning, and profiles |
| Template sends to the wrong cluster | Template injected with the wrong factory | Add explicit qualifiers on `ProducerFactory` parameters when building templates |
| Payload serialization fails | Template uses a factory whose serializer does not match the payload | Verify producer factory, serializers, and data types |
| Sent to the wrong default topic | Wrong `setDefaultTopic()` configuration or wrong qualifier used | Check bean names and default topics; consider passing topic explicitly |
| Too many producer clients created | Each template builds an independent producer factory unnecessarily | Share factories when producer settings are identical |
| Adding a custom template removes expected default template | Auto-configuration may back off when Boot detects user-defined beans | Check the condition evaluation report and declare a default template intentionally |
| `@Primary` causes a service to send to the wrong flow | Service injects by type without a qualifier and gets the primary template | Use qualifiers wherever clear business boundaries matter |

## 11. Checklist for designing multiple KafkaTemplates

1. Create multiple templates only when default topics, producer config, serializers, clusters, or business responsibilities genuinely differ.
2. Share a `ProducerFactory` if templates truly use the same producer configuration.
3. Create separate `ProducerFactory` beans when distinct clusters, security, or serializers are needed.
4. Give beans descriptive names like `ordersKafkaTemplate` and `auditKafkaTemplate`.
5. Use `@Qualifier` on constructor parameters and factory dependencies when multiple beans share the same type.
6. Reserve `@Primary` for a default template; never use it for event-based routing.
7. Use concrete generic types to catch key and payload mismatches.
8. Isolate runtime routing logic in a testable service or strategy.
9. Observe send futures and design retries/idempotency per business requirements.
10. Test bean wiring and verify cluster/topic settings before deployment.

When an application has multiple sending streams, each `KafkaTemplate` should represent a clear purpose. Combining descriptive bean names, `@Qualifier`, and properly configured `ProducerFactory` beans lets services emit events to the right destinations while keeping dependencies and operational responsibilities straightforward to verify.
