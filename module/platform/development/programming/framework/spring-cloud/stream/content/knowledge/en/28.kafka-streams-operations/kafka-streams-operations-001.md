# Configuring StreamsBuilderFactoryBean and the Kafka Streams Client

Kafka Streams requires two parts to run a topology: a builder that describes data sources and transformations, and a runtime that connects to Kafka to consume, process, and emit records. In a Spring application, Spring for Apache Kafka provides `StreamsBuilderFactoryBean` to manage `StreamsBuilder` and the `KafkaStreams` lifecycle. The Spring Cloud Stream Kafka Streams binder uses this mechanism under the hood when creating processors from `Function`, `BiFunction`, or `Consumer` beans.

When operating with Spring Cloud Stream, the application typically declares the topology using a function bean and configures the client using Kafka Streams binder properties. If you need to hook into the lifecycle, state listener, or `KafkaStreams` instance, you can provide a `StreamsBuilderFactoryBeanConfigurer`. For applications using Spring Kafka directly, you can declare `KafkaStreamsConfiguration` yourself and enable `@EnableKafkaStreams` so Spring creates the default factory bean.

This lesson explains the role of each component, how to configure Kafka Streams client properties, how to customize the factory bean at the right time, state and shutdown management, and how to test the configuration when deploying Spring Cloud Stream.

## Learning Objectives

After this lesson, you will be able to:

- Distinguish between `StreamsBuilder`, `Topology`, `KafkaStreams`, and `StreamsBuilderFactoryBean`.
- Explain how the factory bean manages the Kafka Streams lifecycle in Spring.
- Distinguish Kafka Streams binder configuration from standalone Spring Kafka configuration.
- Configure `application.id`, bootstrap servers, Serdes, processing guarantees, and client security.
- Choose binder-level or per-function configuration when running multiple processors.
- Use `StreamsBuilderFactoryBeanConfigurer` and `KafkaStreamsCustomizer`.
- Monitor `RUNNING`, `REBALANCING`, `ERROR` states, and the state restoration process.
- Manage `state.dir`, close timeout, and graceful shutdown.
- Test client configuration, lifecycle, and topology with a Kafka broker.

## 1. Components in the Kafka Streams Lifecycle

A Kafka Streams application typically goes through these steps:

1. Build the topology from source topics and transformations.
2. Create `KafkaStreams` from the topology and client properties.
3. Initialize the required consumers, producers, admin client, and state stores.
4. Join the consumer group, receive partition assignments, and restore state.
5. Transition to the `RUNNING` state to process records.
6. Close the runtime in a controlled manner when the application stops.

Four key types:

| Component | Role |
|---|---|
| StreamsBuilder | DSL for declaring sources, KStream, KTable, and transformations |
| Topology | Processing graph generated from StreamsBuilder |
| KafkaStreams | Runtime that executes the topology and manages threads, clients, state, and rebalances |
| StreamsBuilderFactoryBean | Spring factory bean that creates StreamsBuilder and manages the KafkaStreams lifecycle |

~~~mermaid
flowchart TD
    A["Spring Cloud Stream function beans"] --> B["Kafka Streams binder"]
    B --> C["StreamsBuilder"]
    C --> D["Topology"]
    E["Kafka Streams client properties"] --> F["StreamsBuilderFactoryBean"]
    D --> F
    F --> G["KafkaStreams runtime"]
    G --> H["Kafka consumers / producers"]
    H --> I["Kafka cluster"]
~~~

`StreamsBuilder` describes what work needs to be done; it does not connect to brokers by itself. `KafkaStreams` executes the topology. `StreamsBuilderFactoryBean` connects these two parts to the Spring `ApplicationContext` and container lifecycle.

## 2. Why StreamsBuilderFactoryBean Is Needed

If you instantiate `KafkaStreams` manually in a configuration method and call `start()`, the application must take responsibility for:
- Starting after the topology has been declared.
- Stopping the runtime when the Spring context closes.
- Closing clients and threads at the right time.
- Monitoring state and errors.
- Coordinating multiple processors within the same application.

`StreamsBuilderFactoryBean` solves lifecycle management by implementing Spring `SmartLifecycle`. The factory bean provides `StreamsBuilder` to topology beans and creates `KafkaStreams` when started. When the Spring context stops, the factory bean closes `KafkaStreams` according to its configuration.

An important rule is that `KStream`/`KTable` definitions must be declared before `KafkaStreams` begins running. With an auto-starting factory bean, the topology must be created before `ApplicationContext` refresh completes.

In the Spring Cloud Stream Kafka Streams binder, the binder manages the factory bean for the processor. The application's function bean describes the topology; the binder maps the input/output bindings and creates the runtime. Therefore, the application usually does not need to declare an additional parallel `StreamsBuilderFactoryBean`.

## 3. Two Integration Approaches: Kafka Streams Binder vs. Direct Spring Kafka

The two models share similar goals, but differ in who owns lifecycle management.

| Aspect | Spring Cloud Stream Kafka Streams binder | Direct Spring Kafka |
|---|---|---|
| Topology declaration | Function bean taking/returning KStream or KTable | StreamsBuilder and KStream beans |
| Input/output | Bindings mapped by the binder | Topics declared in the DSL |
| Client properties | `kafka.streams.binder` prefix and function-specific configuration | `KafkaStreamsConfiguration` bean |
| Factory bean | Binder creates and manages the processor factory bean | Spring Kafka creates via `@EnableKafkaStreams` or a manually declared bean |
| Lifecycle customization | `StreamsBuilderFactoryBeanConfigurer` | Direct `StreamsBuilderFactoryBeanConfigurer` |
| Best suited for | Spring Cloud Stream applications using the binder | Applications needing direct Kafka Streams integration |

Do not configure both models as if they own the same processor. If you already use the Kafka Streams binder, let the binder build the topology from the function and use supported customizers to hook into the factory bean. Only declare `StreamsBuilderFactoryBean` manually when the application intentionally uses Spring Kafka directly or has an independent processor outside the binder.

## 4. StreamsBuilderFactoryBean in Direct Spring Kafka

When using Spring Kafka without the Kafka Streams binder, you can enable `@EnableKafkaStreams`. Spring creates the default factory bean if a `KafkaStreamsConfiguration` bean with the standard name is present.

~~~java
import java.util.HashMap;
import java.util.Map;

import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.streams.StreamsConfig;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.annotation.EnableKafkaStreams;
import org.springframework.kafka.config.KafkaStreamsConfiguration;
import org.springframework.kafka.config.KafkaStreamsDefaultConfiguration;

@Configuration
@EnableKafkaStreams
class DirectKafkaStreamsConfiguration {

    @Bean(name = KafkaStreamsDefaultConfiguration.DEFAULT_STREAMS_CONFIG_BEAN_NAME)
    KafkaStreamsConfiguration kafkaStreamsConfiguration() {
        Map<String, Object> props = new HashMap<>();

        props.put(StreamsConfig.APPLICATION_ID_CONFIG, "order-projection");
        props.put(StreamsConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
        props.put(
            StreamsConfig.DEFAULT_KEY_SERDE_CLASS_CONFIG,
            Serdes.String().getClass().getName()
        );
        props.put(
            StreamsConfig.DEFAULT_VALUE_SERDE_CLASS_CONFIG,
            Serdes.String().getClass().getName()
        );

        return new KafkaStreamsConfiguration(props);
    }
}
~~~

With this configuration, Spring Kafka creates the default `StreamsBuilderFactoryBean` and provides `StreamsBuilder` to topology beans. If you need additional factory beans, you can declare them separately with distinct names.

When using `@EnableKafkaStreams`, do not create another default bean with the same name. Likewise, do not manually declare a `StreamsBuilderFactoryBean` while expecting the annotation to create a second default bean. Choose one management approach per processor.

## 5. Configuring Client Properties in Spring Cloud Stream

Kafka Streams uses `StreamsConfig` properties. The Spring Cloud Stream Kafka Streams binder allows setting them at the binder level or per function.

Common properties:

| Kafka Streams Property | Meaning |
|---|---|
| application.id | Processor identifier and internal consumer group |
| bootstrap.servers | List of brokers to connect to |
| default.key.serde | Default Serde for keys |
| default.value.serde | Default Serde for values |
| processing.guarantee | Processing guarantee level, e.g., `at_least_once` or `exactly_once_v2` |
| num.stream.threads | Number of stream threads per instance |
| state.dir | Directory for storing local state |
| commit.interval.ms | Commit interval based on processing configuration |
| replication.factor | Replication factor for internal topics created by Streams |
| security.protocol | Connection security protocol |

Example binder configuration:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          binder:
            brokers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}
            configuration:
              default.key.serde: org.apache.kafka.common.serialization.Serdes$StringSerde
              default.value.serde: org.apache.kafka.common.serialization.Serdes$StringSerde
              processing.guarantee: exactly_once_v2
              num.stream.threads: 2
              state.dir: ${KAFKA_STREAMS_STATE_DIR:/var/lib/app/kafka-streams}
~~~

This is binder-level configuration. Properties inside `binder.configuration` can apply to every processor belonging to that binder. If the application has multiple function processors, consider separating the application ID and processor-specific settings per function to avoid unintended sharing.

The Kafka Streams binder has its own `brokers` property. Other Kafka Streams API properties are placed under `configuration`. Do not mistakenly use the regular Kafka message-channel binder prefix for `StreamsConfig` properties.

## 6. Global and Per-Function Application ID

`application.id` defines the identity of a Kafka Streams application. It affects the consumer group, internal topics, state store changelogs, and progress recovery capabilities.

If there is only one processor, you can set the application ID at the binder level:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          binder:
            applicationId: order-projection
~~~

If there are multiple function processors, you should assign separate IDs:

~~~yaml
spring:
  cloud:
    function:
      definition: enrichOrder;aggregatePayment
    stream:
      kafka:
        streams:
          binder:
            functions:
              enrichOrder:
                applicationId: order-enricher
              aggregatePayment:
                applicationId: payment-aggregator
~~~

Each processor with its own application ID will have separate consumption progress and internal state. Do not use the same application ID for two independent topologies if they are not designed to belong to the same Kafka Streams application.

Changing the application ID is not simply renaming a log label. Kafka Streams may treat it as a brand-new application and re-read data according to the offset policy, creating new internal topics and state. Before changing it, evaluate retention, replay, and downstream side effects.

## 7. Per-Processor Configuration

When running multiple processors, the binder supports function-specific configuration. Example:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          binder:
            functions:
              enrichOrder:
                applicationId: order-enricher
                configuration:
                  processing.guarantee: exactly_once_v2
                  num.stream.threads: 2
              aggregatePayment:
                applicationId: payment-aggregator
                configuration:
                  processing.guarantee: at_least_once
                  num.stream.threads: 1
~~~

Per-function configuration is useful when:
- Processors have different load and latency profiles.
- Processors have different processing requirements.
- Separate application IDs are needed.
- One topology requires exactly-once within Kafka while another accepts at-least-once.
- You want to avoid unintended effects from binder-level configuration.

Function-level configuration only applies to the specified function. Verify that the bean name in the Spring context matches the function name in the configuration. If a function uses composition or binding overrides, the final function name must be verified against the actual bindings.

## 8. Bootstrap Servers and Client Security

Kafka Streams creates Kafka clients internally. These clients must connect to the right cluster and have permissions to read input topics, write output topics, access groups, and manage internal topics.

Example `SASL_SSL` configuration with secrets injected via environment variables:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          binder:
            brokers: ${KAFKA_BOOTSTRAP_SERVERS}
            configuration:
              security.protocol: SASL_SSL
              sasl.mechanism: SCRAM-SHA-512
              sasl.jaas.config: ${KAFKA_SASL_JAAS_CONFIG}
              ssl.truststore.location: ${KAFKA_TRUSTSTORE_LOCATION}
              ssl.truststore.password: ${KAFKA_TRUSTSTORE_PASSWORD}
~~~

Never write usernames, passwords, JAAS strings, or truststore passwords directly in committed configuration files. Provide them through a secret manager, Kubernetes Secret, or your environment's secret provisioning mechanism.

ACLs must allow:
- Reading input topics.
- Writing output topics.
- Using the application ID/consumer group.
- Creating or accessing changelog and repartition topics.
- Performing metadata operations required by the cluster configuration.

When encountering authorization errors, check both business topics and internal topics. A topology may be able to read input yet still fail to start if it cannot create or write to changelog/repartition topics.

## 9. Processing Guarantee and Producer/Consumer Configuration

The `processing.guarantee` property determines the guarantee level of Kafka Streams.

- `at_least_once` allows records to be reprocessed when an error occurs at a commit boundary.
- `exactly_once_v2` coordinates offsets, state stores, and output records inside Kafka transactions according to cluster/client support.

Kafka Streams exactly-once protects the processing flow within the scope of Kafka Streams and Kafka transactions. It does not automatically cover calling a REST API, sending an email, or updating an external database. Side effects outside Kafka still require idempotency, an outbox pattern, or a dedicated coordination mechanism.

Example configuration:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          binder:
            configuration:
              processing.guarantee: exactly_once_v2
              replication.factor: 3
~~~

Exactly-once requires a cluster that supports transactions and appropriate replication settings. For production, verify broker version, transaction state log replication, min ISR, and the replication factor of internal topics. Do not simply enable the property and assume the system achieves end-to-end exactly-once.

## 10. Customizing StreamsBuilderFactoryBean in the Kafka Streams Binder

The Kafka Streams binder creates a `StreamsBuilderFactoryBean` for each processor. When you need to set a state listener, close timeout, `KafkaStreamsCustomizer`, or other factory bean options, provide a `StreamsBuilderFactoryBeanConfigurer` bean.

Example for state monitoring:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.StreamsBuilderFactoryBeanConfigurer;

@Configuration
class StreamsLifecycleConfiguration {

    private static final Logger log =
        LoggerFactory.getLogger(StreamsLifecycleConfiguration.class);

    @Bean
    StreamsBuilderFactoryBeanConfigurer streamsBuilderFactoryBeanConfigurer() {
        return factoryBean -> factoryBean.setStateListener(
            (newState, oldState) ->
                log.info("Kafka Streams state changed: {} -> {}", oldState, newState)
        );
    }
}
~~~

The binder invokes the configurer before the factory bean starts. At this point, you can modify supported factory bean properties. This is the appropriate place to attach listeners or configure customizers.

If the application has multiple processors, each processor has its own factory bean. You can inspect the application ID from the factory bean and apply configuration only to the target processor. Do not apply a specific exception policy or state listener to every processor if topologies have different operational requirements.

## 11. Customizing KafkaStreams with KafkaStreamsCustomizer

`StreamsBuilderFactoryBean` can accept a `KafkaStreamsCustomizer` to customize the `KafkaStreams` instance right before the runtime starts.

Example attaching an uncaught exception handler:

~~~java
import org.apache.kafka.streams.errors.StreamsUncaughtExceptionHandler;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.config.StreamsBuilderFactoryBeanConfigurer;

@Configuration
class StreamsExceptionConfiguration {

    private static final Logger log =
        LoggerFactory.getLogger(StreamsExceptionConfiguration.class);

@Bean
StreamsBuilderFactoryBeanConfigurer streamsBuilderFactoryBeanConfigurer() {
    return factoryBean -> factoryBean.setKafkaStreamsCustomizer(
        kafkaStreams -> kafkaStreams.setUncaughtExceptionHandler(exception -> {
            log.error("Uncaught Kafka Streams exception", exception);
            return StreamsUncaughtExceptionHandler.StreamThreadExceptionResponse
                .SHUTDOWN_APPLICATION;
        })
    );
}
}
~~~

Kafka Streams provides response options for uncaught exceptions in stream threads. For example:
- `REPLACE_THREAD`: replaces the failed thread with a new thread if appropriate.
- `SHUTDOWN_CLIENT`: stops the current `KafkaStreams` client.
- `SHUTDOWN_APPLICATION`: requests shutting down the entire application.

The policy must be chosen based on the error type and recoverability. Do not blindly return `REPLACE_THREAD` for every error: configuration errors or recurring bad data can cause the replacement thread to fail repeatedly. For severe errors, stopping the application so an orchestrator can perform a controlled restart may be safer.

`KafkaStreamsCustomizer` is called near start time, so do not retrieve the `KafkaStreams` instance too early from `ApplicationContext`. If you need access to `StreamsBuilder` or `Topology` to add infrastructure, use `KafkaStreamsInfrastructureCustomizer` instead of calling `factoryBean.getObject()` while the factory bean is still initializing.

## 12. Selecting the Right Processor When Multiple Factory Beans Exist

An application may have multiple function processors. The binder creates a corresponding factory bean for each processor, so a shared customizer needs to check the application ID before applying specific configuration.

~~~java
import org.apache.kafka.streams.StreamsConfig;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.config.StreamsBuilderFactoryBeanConfigurer;

@Configuration
class OrderProcessorConfiguration {

    private static final Logger log =
        LoggerFactory.getLogger(OrderProcessorConfiguration.class);

@Bean
StreamsBuilderFactoryBeanConfigurer orderProcessorConfigurer() {
    return factoryBean -> {
        String applicationId = factoryBean.getStreamsConfiguration()
            .getProperty(StreamsConfig.APPLICATION_ID_CONFIG);

        if ("order-enricher".equals(applicationId)) {
            factoryBean.setStateListener((newState, oldState) ->
                log.info("order-enricher: {} -> {}", oldState, newState)
            );
        }
    };
}
}
~~~

Use the application ID configured for the corresponding processor. If the application ID is auto-generated, inspect its actual value in `StreamsConfiguration` before comparing. Do not assume all factory beans belong to the same topology.

You can use `Ordered` to sort multiple configurers if they modify the same factory bean. When multiple customizers modify the same property, execution order affects the final result; grouping related changes into a single configurer is usually easier to control.

## 13. Customizing StreamsBuilder and Topology

There are two distinct customization groups:

- `StreamsBuilderFactoryBeanConfigurer` configures the factory bean and runtime lifecycle.
- `KafkaStreamsInfrastructureCustomizer` customizes `StreamsBuilder` or `Topology` before `KafkaStreams` is created.

Example infrastructure customizer skeleton:

~~~java
import org.springframework.kafka.config.KafkaStreamsInfrastructureCustomizer;
import org.apache.kafka.streams.StreamsBuilder;
import org.apache.kafka.streams.Topology;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.config.StreamsBuilderFactoryBeanConfigurer;

@Configuration
class StreamsInfrastructureConfiguration {

@Bean
StreamsBuilderFactoryBeanConfigurer globalStoreConfigurer() {
    return factoryBean -> factoryBean.setInfrastructureCustomizer(
        new KafkaStreamsInfrastructureCustomizer() {
            @Override
            public void configureBuilder(StreamsBuilder builder) {
                // Register required stores or sources before the topology is built.
            }

            @Override
            public void configureTopology(Topology topology) {
                // Inspect or customize the built topology.
            }
        }
    );
}
}
~~~

In a Spring Cloud Stream application, the function bean remains the primary way to describe business topology. The infrastructure customizer is intended for special infrastructure needs such as a global state store or low-level topology intervention.

Do not call `factoryBean.getObject()` inside a configurer just to obtain `StreamsBuilder`. The factory bean may still be initializing, and accessing it prematurely can create a circular dependency. Use the infrastructure customizer to operate on the builder/topology following the lifecycle provided by Spring Kafka.

## 14. Monitoring State and the Restoration Process

`KafkaStreams` has states reflecting operational progress. Common states include:

| State | Operational Meaning |
|---|---|
| CREATED | Runtime has been created but is not running yet |
| REBALANCING | Joining or changing partition assignments |
| RUNNING | Topology is ready to process records |
| PENDING_SHUTDOWN | Shutting down |
| NOT_RUNNING | No longer running |
| ERROR | Runtime encountered a critical error |

State listeners help record state transitions and emit metrics/alerts. For example:
- Staying in `REBALANCING` too long may be caused by brokers, group coordination, or state restoration.
- Failing to transition to `RUNNING` may be caused by connection issues, ACLs, Serdes, or internal topics.
- Transitioning to `ERROR` requires checking exception logs and the uncaught exception handler policy.

For stateful topologies, monitor `StateRestoreListener` to track state store restoration progress. When a new instance receives partitions, it may need to read changelogs to rebuild local state before normal processing begins.

Do not equate Spring `ApplicationContext` having started with Kafka Streams being `RUNNING`. A web application may open its HTTP port while the processor is still rebalancing or restoring state.

## 15. State Directory and Local State Recovery

Kafka Streams stores local state stores in the `state.dir` directory. This is the instance's working data, tied to the application ID and tasks/partitions.

Operational principles:
- Each instance needs its own local directory; avoid having two processes write to the same state directory.
- Grant appropriate filesystem permissions to the user running the application.
- Disk capacity must be sufficient for state stores, caches, and the restoration process.
- Monitor disk usage and restoration speed.
- Never delete a state directory currently in use by a process.
- Have a recovery plan from changelogs if local state is lost.

Example:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          binder:
            configuration:
              state.dir: /var/lib/my-service/kafka-streams
~~~

In containers, you can use a local volume or ephemeral storage depending on requirements. If local state is lost, Kafka Streams can rebuild it from the changelog when configuration and data remain intact. This may lengthen startup time; it does not mean you need to manually back up every state directory as a primary data source.

Do not share the same `state.dir` across multiple replicas. If persistence across restarts is needed, ensure volumes are bound to the right instance and not mounted for concurrent writes by two pods.

## 16. Graceful Shutdown and Close Timeout

When the Spring context stops, `StreamsBuilderFactoryBean` calls `KafkaStreams.close()` to stop threads and release clients. You can configure a close timeout to control how long shutdown waits.

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.config.StreamsBuilderFactoryBeanConfigurer;

@Configuration
class StreamsShutdownConfiguration {

@Bean
StreamsBuilderFactoryBeanConfigurer shutdownConfigurer() {
    return factoryBean -> factoryBean.setCloseTimeout(30);
}
}
~~~

The parameter to `setCloseTimeout` is in seconds. The example above sets the maximum wait time for closing `KafkaStreams` to 30 seconds.

In production environments:
- Set the container's termination grace period longer than the expected shutdown time.
- Stop accepting new work before the process is killed if an orchestration mechanism is used.
- Allow Kafka Streams to finish processing and committing according to the processing guarantee.
- Monitor the duration from `PENDING_SHUTDOWN` to `NOT_RUNNING`.
- Avoid `kill -9` or hard stops in normal deployment procedures.

Do not call `KafkaStreams.close()` arbitrarily from a business handler if the factory bean owns the lifecycle. Use Spring lifecycle hooks or appropriate binding control to stop the processor. If conditional stop/start is required, operate properly on the factory bean and check state after each transition.

## 17. Health, Metrics, and Client Observability

A processor can experience issues even while the JVM remains alive. Combine monitoring of:
- Kafka Streams state.
- Consumer lag per input partition.
- Input/output throughput.
- Processing latency.
- State restore duration.
- Rebalance count and rebalance duration.
- RocksDB/state store disk usage.
- Producer errors and commit failures.
- Thread uncaught exceptions.
- DLQ or skipped record counts if a recovery handler is configured.

Spring for Apache Kafka supports a Micrometer listener for `KafkaStreams` instances managed by the factory bean. You can register the listener with `MeterRegistry` and tag by processor/application ID. Verify metric names for the library version in use.

A health indicator does not replace business-level monitoring. A processor may be `RUNNING` while output still makes no progress because input has no data, filter logic drops every record, or the downstream topic is misconfigured. Monitor both runtime state and data flow.

## 18. Common Configuration Errors

| Symptom | Possible Cause | Resolution |
|---|---|---|
| KafkaStreams fails to start | Missing application ID or bootstrap servers | Check `StreamsConfig` and binder properties |
| Processor creates wrong group | Duplicate or unexpectedly changed application ID | Use a stable, unique ID per processor |
| Serde exception | Default/key/value Serde mismatches data | Explicitly configure Serde for bindings |
| Cannot create changelog topic | Improper ACLs or replication factor | Check permissions and cluster configuration |
| Processor stuck in REBALANCING | Broker, group coordinator, or slow restore | Inspect brokers, lag, and `StateRestoreListener` |
| Factory bean customizer does not run | Wrong interface, package, or bean not scanned | Check Spring Kafka dependency and component scan |
| Customizer applies to wrong processor | Not filtering by application ID | Inspect `StreamsConfiguration` before modifying |
| State restore takes very long | Large changelog or lost local state | Monitor restore, storage, and retention |
| Prolonged shutdown | Close timeout too short or busy threads | Adjust timeout and termination grace period |
| Two instances have state conflict | Shared `state.dir` | Create a separate directory per process |
| Exactly-once still produces duplicates in external API | Kafka transactions do not cover external side effects | Use idempotency/outbox |
| Reads input but cannot write output | Missing ACLs for output/internal topics | Check producer and internal topic permissions |

## 19. Testing Configuration and Lifecycle

Testing should be divided into three layers.

### Configuration Verification

- Verify the application ID is set correctly for each function.
- Check bootstrap servers, Serdes, and processing guarantee.
- Verify secrets/security properties are injected properly without logging secret values.
- Check that binder-level configuration does not accidentally override function-specific configuration.
- Verify `state.dir` exists and is writable.

### Integration Tests with Kafka

Use a test Kafka broker or Testcontainers to:
1. Start the Spring context and binder.
2. Verify `StreamsBuilderFactoryBean` is created and the processor transitions to `RUNNING`.
3. Send records to the input topic.
4. Verify the topology processes and writes output.
5. Restart the processor and check state/offset restoration.
6. Stop the context and verify runtime shutdown.
7. Simulate broker unavailability or Serde errors to test state/error handling.

### Customizer Testing

- Verify the state listener receives state transitions.
- Verify the customizer only applies to the intended application ID.
- Test the uncaught exception policy in a test environment.
- Test close timeout and graceful shutdown.
- For stateful topologies, check the restore listener and recovery time.

Do not test only that `ApplicationContext` starts successfully. A client configuration is only verified when the processor connects to brokers, receives partitions, processes records, and shuts down properly.

## 20. Hands-on Lab: Operating the order-projection Processor

Build a Spring Cloud Stream Kafka Streams processor reading the `orders` topic and writing `order-projections`:

1. Declare a function bean creating a topology from `KStream`.
2. Set the application ID to `order-projection`.
3. Configure bootstrap servers via environment variables.
4. Configure key/value Serdes matching the schema.
5. Choose the processing guarantee according to requirements and cluster capabilities.
6. Set a dedicated `state.dir` for the instance.
7. Declare a `StreamsBuilderFactoryBeanConfigurer` to monitor state.
8. Filter the factory bean by application ID if the application has multiple processors.
9. Attach a `KafkaStreamsCustomizer` for an appropriate uncaught exception policy.
10. Run integration tests with a Kafka broker.
11. Send records and verify the output topic.
12. Restart the processor and observe state restoration.
13. Stop the Spring context and verify graceful shutdown.
14. Check metrics, lag, and logs to confirm stable processor operation.

Acceptance Checklist:

| Item | Expected Verification Result |
|---|---|
| Factory bean ownership | Binder or Spring Kafka manages exactly one lifecycle per processor |
| Topology | Declared before runtime starts |
| Application ID | Stable and non-conflicting |
| Client properties | Broker, Serde, guarantee, and security are correct |
| Function configuration | Processor-specific properties do not affect other processors |
| Customizer | Invoked before the factory bean starts |
| State listener | Records transitions and errors |
| State directory | Dedicated per instance, with sufficient disk space |
| Shutdown | Appropriate close timeout and termination grace period |
| Integration test | Actually processes input, output, restore, and stop |

## Conclusion

`StreamsBuilderFactoryBean` connects the Kafka Streams topology with the Spring lifecycle. `StreamsBuilder` defines the processing flow; `KafkaStreams` executes the topology and manages consumers, producers, state, and rebalances; the factory bean creates the runtime, starts it, and stops it according to the application lifecycle.

With the Spring Cloud Stream Kafka Streams binder, let the binder manage the factory bean and configure clients via the `kafka.streams.binder` prefix or function-specific configuration. When lifecycle customization is needed, use `StreamsBuilderFactoryBeanConfigurer` and `KafkaStreamsCustomizer`; filter by application ID when multiple processors exist. Monitor state and restoration, provide dedicated `state.dir` paths, configure security/processing guarantees properly, and test graceful shutdown against an actual Kafka broker.

## References

- [Spring Cloud Stream 5.0.4 – StreamsBuilderFactoryBean configurer](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/streamsbuilderfactorybean-customizer.html)
- [Spring Cloud Stream 5.0.4 – Kafka Streams binder configuration options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/configuration-options.html)
- [Spring for Apache Kafka 4.2 – Apache Kafka Streams Support](https://docs.spring.io/spring-kafka/reference/streams.html)
- [Apache Kafka – StreamsConfig API](https://kafka.apache.org/documentation/#streamsconfigs)
- [Apache Kafka Streams – Developer Guide](https://kafka.apache.org/documentation/streams/)
