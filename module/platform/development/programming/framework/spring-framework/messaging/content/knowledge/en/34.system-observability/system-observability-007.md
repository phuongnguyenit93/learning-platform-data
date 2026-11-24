# Micrometer Observation for JMS by Version Capability and Configuration

## Objectives

After this lesson, you can enable observability for JMS flows in Spring, know the exact versions and dependencies required, distinguish message send duration from message processing duration, verify observations are created on both producer and consumer, and export metrics/traces to a backend in a cardinality-safe way.

## 1. What Is Observation?

Micrometer Observation is an abstraction for recording an ongoing operation in an application. A single observation can be handled by multiple `ObservationHandler` implementations:

- A metrics handler creates timers, counters, or corresponding meters.
- A tracing handler creates spans and links the operation to the active trace.
- A custom handler can log events or push data to a specialized observability system.

`ObservationRegistry` is where observations are registered and dispatched. Without matching handlers, observations may not produce any metrics or traces. Therefore, seeing a `setObservationRegistry(...)` call in code is not enough to conclude data is being exported to a backend.

Distinguish three layers:

1. **Observation instrumentation:** Spring/Micrometer determines when the JMS operation starts and ends and collects its metadata.
2. **Observation handlers and registry:** turn observations into metrics, traces, or other telemetry.
3. **Exporter/backend:** receives metrics or traces, such as Prometheus, an OTLP collector, Zipkin, or an APM system.

Micrometer Observation does not replace logs and does not automatically expose all internal broker state.

## 2. Capabilities by Version and Dependency

JMS Observation depends simultaneously on the Spring version, JMS API, and Micrometer instrumentation.

| Component | Requirement |
|---|---|
| Spring Framework | Observation configuration APIs for `JmsTemplate` and listener containers exist since Spring Framework 6.1 |
| JMS API | `micrometer-jakarta9` instruments Jakarta Messaging (`jakarta.jms`) |
| Micrometer | Requires `io.micrometer:micrometer-jakarta9` on the classpath for JMS instrumentation |
| Spring Boot | Spring Boot 3.2.x documentation describes auto-instrumentation for available `JmsTemplate` beans and `@JmsListener` methods |
| Metrics backend | Requires an appropriate `MeterRegistry`/registry exporter to export metrics externally |
| Tracing backend | Requires a Micrometer Tracing bridge and appropriate exporter/tracer to export spans |

Two key APIs added in Spring Framework 6.1:

- `JmsTemplate.setObservationRegistry(ObservationRegistry)` to record publish operations.
- `AbstractJmsListenerContainerFactory.setObservationRegistry(ObservationRegistry)` to record listener container processing.

With Spring Framework 6.0 or older, do not assume these two setters exist. For Spring Boot 2 / Spring Framework 5 applications using `javax.jms`, the `micrometer-jakarta9` dependency is not compatible with the legacy API. Check the dependency tree and Javadoc of your exact version before applying these examples.

### Maven dependency

In a Spring Boot project, let the Spring Boot BOM manage Micrometer versions instead of picking an isolated version manually:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>

    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-jakarta9</artifactId>
    </dependency>

    <!-- Choose a registry for your backend, e.g., Prometheus. -->
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

`spring-boot-starter-actuator` provides Spring Boot's management foundation and observability auto-configuration. `micrometer-jakarta9` adds Jakarta JMS instrumentation. The Prometheus registry is just an example; choose OTLP, Datadog, New Relic, or another registry according to your stack.

You do not need to declare separate versions for Micrometer dependencies if your project uses the matching Spring Boot dependency management/BOM. When not using Boot's BOM, use the Micrometer BOM and verify the compatibility matrix among Micrometer, Spring Framework, and your JMS provider.

## 3. Two Primary Observations for JMS

Spring Framework together with Micrometer Jakarta JMS instrumentation produces two observation types:

| Observation | Timing | Meaning |
|---|---|---|
| `jms.message.publish` | Producer sends a message to a destination | Measures send operation duration via a JMS producer, typically through `JmsTemplate` |
| `jms.message.process` | Consumer processes a received message | Measures listener processing duration, typically through `MessageListener` or `@JmsListener` |

Currently this instrumentation does not create a separate `jms.message.receive` observation for time spent waiting to receive a message. Measuring wait time inside `MessageConsumer.receive()` is not synonymous with processing time and does not automatically provide trace context to follow the handler after receipt.

This leads to an important limitation: `jms.message.process` tells you whether the listener processes fast or slow, but does not directly tell you how long the message sat in the queue before delivery. To measure queue age/consumer lag, use broker metrics or record a business/created-at timestamp on publish and compute latency on the consumer.

## 4. Enabling Observation for Producers with JmsTemplate

With Spring Framework 6.1+, configure `ObservationRegistry` on `JmsTemplate`:

~~~java
import io.micrometer.observation.ObservationRegistry;
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsTemplate;

@Configuration
class JmsProducerConfiguration {

    @Bean
    JmsTemplate observedJmsTemplate(
            ConnectionFactory connectionFactory,
            ObservationRegistry observationRegistry) {

        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setObservationRegistry(observationRegistry);
        return template;
    }
}
~~~

When calling:

~~~java
jmsTemplate.convertAndSend("orders.created", orderEvent);
~~~

Spring/Micrometer creates a `jms.message.publish` observation around the send operation. The observation measures time to send the message to the broker, and instrumentation can propagate tracing context via JMS message headers.

If using `JmsMessagingTemplate`, build it from the `JmsTemplate` configured with ObservationRegistry:

~~~java
import org.springframework.jms.core.JmsMessagingTemplate;
import org.springframework.jms.core.JmsTemplate;

JmsMessagingTemplate messagingTemplate =
    new JmsMessagingTemplate(observedJmsTemplate);
~~~

Do not instantiate a separate unconfigured `JmsTemplate` and expect observations to appear automatically.

## 5. Enabling Observation for @JmsListener

Consumer observation must be configured on the exact `JmsListenerContainerFactory` used by the listener.

~~~java
import io.micrometer.observation.ObservationRegistry;
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
@EnableJms
class JmsListenerObservationConfiguration {

    @Bean
    DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory,
            ObservationRegistry observationRegistry) {

        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setObservationRegistry(observationRegistry);
        return factory;
    }
}
~~~

A listener can be declared as follows:

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
class OrderEventListener {

    @JmsListener(
        destination = "orders.created",
        containerFactory = "jmsListenerContainerFactory"
    )
    public void handle(OrderCreated event) {
        // Business processing.
    }
}
~~~

When the listener container processes a message, the `jms.message.process` observation measures listener execution time. If the listener throws an exception, the observation records the error state and exception per convention. Acknowledgement/rollback behavior still depends on transaction configuration and the JMS provider; Observation does not roll back messages on its own.

### When using Spring Boot

The Spring Boot 3.2.x reference describes auto-instrumentation for `JmsTemplate` beans and `@JmsListener` methods. Boot also provides ObservationRegistry and matching handlers when Actuator/observability is configured.

However, a `@JmsListener` can reference a custom factory via its `containerFactory` attribute. If you declare a custom factory, ensure that factory is configured with ObservationRegistry. Using `DefaultJmsListenerContainerFactoryConfigurer` lets you retain Boot's defaults and then add the registry:

~~~java
import io.micrometer.observation.ObservationRegistry;
import jakarta.jms.ConnectionFactory;

import org.springframework.boot.autoconfigure.jms.DefaultJmsListenerContainerFactoryConfigurer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
class CustomJmsFactoryConfiguration {

    @Bean
    DefaultJmsListenerContainerFactory observedFactory(
            ConnectionFactory connectionFactory,
            DefaultJmsListenerContainerFactoryConfigurer configurer,
            ObservationRegistry observationRegistry) {

        var factory = new DefaultJmsListenerContainerFactory();
        configurer.configure(factory, connectionFactory);
        factory.setObservationRegistry(observationRegistry);
        return factory;
    }
}
~~~

In a Boot project, reference the right factory bean in the annotation:

~~~java
@JmsListener(
    destination = "orders.created",
    containerFactory = "observedFactory"
)
public void handle(OrderCreated event) {
    // Business processing.
}
~~~

If you only use Boot's default factory and auto-configuration already works, do not declare a new factory just to duplicate default settings.

## 6. Propagating Trace Context Over JMS

Producer and consumer observations can produce two linked spans in the same distributed trace:

1. Producer is handling a request or business operation.
2. `JmsTemplate` starts a `jms.message.publish` observation.
3. Instrumentation writes trace context into JMS message headers via propagation.
4. Consumer receives the message.
5. `jms.message.process` restores trace context from headers and creates a linked processing span.

As a result, traces can connect HTTP/API handling with message publishing and consumer processing, even across different threads or processes.

To produce real traces, the application needs a configured Micrometer Tracing bridge and tracer/exporter. Having only an `ObservationRegistry` or only a metrics registry does not mean distributed tracing is active.

Trace propagation also depends on message headers surviving across brokers and middleware. If a bridge, custom converter, or integration layer strips the relevant properties/headers, the trace breaks. Do not embed trace context inside the business payload when instrumentation already supports header propagation.

## 7. Understanding Key Values and Cardinality

Default JMS observations include several common key values.

| Group | Key | Meaning |
|---|---|---|
| Low cardinality | `error` | Exception class name or `none` |
| Low cardinality | `messaging.destination.temporary` | Whether the destination is a temporary queue/topic |
| Low cardinality | `messaging.operation` | `publish` or `process` |
| High cardinality | `messaging.message.conversation_id` | Correlation ID of the message |
| High cardinality | `messaging.destination.name` | Destination name |
| High cardinality | `messaging.message.id` | Provider-assigned message ID |

Low-cardinality values have a finite number of values and are suitable as metric tags. High-cardinality values can grow very large, so by default they belong in traces/spans and should not be used as metric labels.

Examples:
- `messaging.operation=publish` has only a small fixed set of values.
- `error=JmsException` generally has a finite set of exception classes.
- `messaging.message.id=ID:...` can differ for every message; putting this key into metric labels would create millions of time series.
- `messaging.message.conversation_id` can also be unique per request; it fits better in traces.

Do not add customer ID, order ID, email, or payload into low-cardinality tags. When you need to look up a specific message, use logs with correlation IDs or trace search while following data protection policies.

You can use a custom ObservationConvention/ObservationFilter to adjust metadata. Before promoting any key to metrics, estimate its maximum cardinality and check its impact on cardinality, memory, storage, and backend costs.

## 8. Viewing Metrics with Spring Boot Actuator

If the application has an appropriate registry, you can inspect metric names through Actuator:

~~~properties
management.endpoints.web.exposure.include=health,metrics,prometheus
~~~

The `/actuator/metrics` endpoint is helpful for diagnosing meters on a single instance. For example:

~~~text
GET /actuator/metrics/jms.message.publish
GET /actuator/metrics/jms.message.process
~~~

Metric names in Actuator follow code/convention naming. When exported to Prometheus, naming conventions may convert dots to underscores and add unit suffixes, representing timers as corresponding series.

If using Prometheus, add the registry dependency and configure Prometheus to scrape `/actuator/prometheus`. The endpoint should be exposed and secured according to the application's security policy. Do not use the metrics endpoint as a production storage backend; use Prometheus or a real monitoring backend.

### What should you monitor?

- Publish duration and publish error rate.
- Process duration and processing error rate.
- Latency distributions by operation/destination if destinations have low cardinality in your system.
- Traces for messages with abnormal processing durations.
- Queue depth, enqueue age, consumer count, DLQ depth, and broker health from the broker's monitoring system.

Spring JMS observations do not replace broker metrics. Queue depth and backlog typically must come from Artemis management/JMX, IBM MQ monitoring, or the provider's corresponding API.

## 9. Testing Observation

A good test should verify that real operations pass through instrumentation and produce meters, not merely that an `ObservationRegistry` bean exists.

### Creating a registry for tests

~~~java
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;
import io.micrometer.observation.ObservationRegistry;

SimpleMeterRegistry meterRegistry = new SimpleMeterRegistry();

ObservationRegistry observationRegistry = ObservationRegistry.create();
observationRegistry.observationConfig().observationHandler(
    new DefaultMeterObservationHandler(meterRegistry)
);
~~~

This setup is for tests; in a Boot application, registries and handlers are usually auto-configured. Tests require `micrometer-core` and `micrometer-jakarta9` dependencies.

### Verifying publish observation

1. Create a `JmsTemplate` backed by a real broker and configure `setObservationRegistry(observationRegistry)`.
2. Send a message to a dedicated test destination.
3. Verify the test consumer receives the expected message.
4. Look up the `jms.message.publish` timer in `SimpleMeterRegistry`.
5. Assert the timer recorded at least one measurement and the operation tag has value publish.

Assertion example with AssertJ:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

var publishTimer = meterRegistry.find("jms.message.publish").timer();

assertThat(publishTimer).isNotNull();
assertThat(publishTimer.count()).isGreaterThanOrEqualTo(1);
~~~

### Verifying process observation

1. Configure `ObservationRegistry` on the listener container factory.
2. Send a message to the `@JmsListener` destination.
3. Use `CountDownLatch` or `BlockingQueue` to wait for the listener to finish.
4. Look up the `jms.message.process` timer.
5. Assert the timer recorded a sample after the listener ran.

To test error observations, make the listener deliberately throw an exception and verify error metadata. With transacted listeners, the broker may redeliver; configure redelivery count, delay, and DLQ so the test stays deterministic. Do not assume a single exception creates only one process observation if the broker redelivers the message multiple times.

### Testing context propagation

With an active producer span, send a message and let the consumer process it. Verify the test trace backend/tracer contains linked publish and process spans sharing trace context. Asserting only that the message carries a correlation ID is not enough to prove distributed tracing was propagated.

### Testing when Observation is disabled

Run a control test with a no-op registry or without configuring a registry. This catches cases where a test accidentally measures meters from another instrumentation source. Compare before/after using meter names, counts, and tags; do not merely check that an HTTP endpoint returns 200.

## 10. When Not Using Spring JmsTemplate

If an application calls the Jakarta JMS API directly, Micrometer provides `JmsInstrumentation.instrumentSession(...)` to instrument a session:

~~~java
import io.micrometer.jakarta9.instrument.jms.JmsInstrumentation;
import io.micrometer.observation.ObservationRegistry;

import jakarta.jms.Session;

Session instrumentedSession =
    JmsInstrumentation.instrumentSession(originalSession, observationRegistry);
~~~

Then create producers/consumers from the instrumented session. Ensure you do not instrument the same session multiple times or create duplicate observations. For code using `JmsTemplate` and `@JmsListener`, prefer configuring the registry on Spring's abstractions to avoid double instrumentation.

## 11. Limitations and Common Mistakes

- **Actuator present without `micrometer-jakarta9`:** registries may work for HTTP/JVM while JMS instrumentation is missing.
- **Using Spring Framework below 6.1:** `setObservationRegistry` setters may not exist.
- **Using `javax.jms` with `micrometer-jakarta9`:** incompatible API packages; do not mix javax and jakarta.
- **Configuring only JmsTemplate:** publishes are observed, but listener processing remains uninstrumented.
- **Configuring only the default factory:** listeners using a custom `containerFactory` may lack the registry.
- **Having Observation without handlers:** observations are created but never exported as metrics or traces.
- **Having metrics and expecting traces:** requires configuring a Micrometer Tracing bridge and exporter.
- **Looking for `jms.message.receive`:** current JMS instrumentation focuses on publish and process and does not create a separate receive observation.
- **Using message ID as a metric tag:** causes uncontrolled cardinality explosion.
- **Expecting queue depth from JMS Observation:** requires broker metrics/management APIs.
- **Measuring process time and calling it queue latency:** process time begins when the application starts handling, excluding time the message waited in the broker.
- **Building JmsMessagingTemplate from an uninstrumented template:** the registry must be configured on the underlying template.
- **Creating a new factory and losing Boot defaults:** when customizing a factory in Boot, use the configurer to preserve converters and required defaults.

## 12. Implementation Checklist

- [ ] Confirm Spring Framework 6.1+ when using ObservationRegistry setters.
- [ ] Confirm the JMS API is Jakarta (`jakarta.jms`) when using `micrometer-jakarta9`.
- [ ] Check the dependency tree includes Micrometer Jakarta JMS instrumentation.
- [ ] Confirm Spring Boot Actuator/ObservationRegistry is configured.
- [ ] Configure the registry on every `JmsTemplate` used for publishing.
- [ ] Configure the registry on the exact `JmsListenerContainerFactory` for each listener.
- [ ] Verify `jms.message.publish` and `jms.message.process` appear after a real message test.
- [ ] If tracing is needed, add a bridge/tracer/exporter and verify trace context across JMS headers.
- [ ] Keep IDs and sensitive data out of metric tags.
- [ ] Use broker metrics for queue depth, backlog, DLQ, and consumer health.
- [ ] Expose Actuator endpoints selectively and secure them.
- [ ] Include integration tests for publish, process, error, and trace propagation.

## References

- [Spring Framework 6.2 — Observability Support](https://docs.spring.io/spring-framework/reference/6.2/integration/observability.html): JMS observation names, dependencies, and registry configuration.
- [Spring Framework 6.1 — JmsTemplate Javadoc](https://docs.spring.io/spring-framework/docs/6.1.1/javadoc-api/org/springframework/jms/core/JmsTemplate.html): `setObservationRegistry`, available since 6.1.
- [Spring Framework 6.1 — AbstractMessageListenerContainer Javadoc](https://docs.spring.io/spring-framework/docs/6.1.9/javadoc-api/org/springframework/jms/listener/AbstractMessageListenerContainer.html): registry for JMS message processing observations, available since 6.1.
- [Spring Boot 3.2 — JMS Metrics](https://docs.spring.io/spring-boot/docs/3.2.10/reference/html/actuator.html): auto-instrumentation for `JmsTemplate` and `@JmsListener`.
- [Micrometer — JMS Instrumentation](https://docs.micrometer.io/micrometer/reference/reference/jms.html): `micrometer-jakarta9` dependency, observations, and key values.
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): ObservationRegistry, handlers, metrics, and tracing.
