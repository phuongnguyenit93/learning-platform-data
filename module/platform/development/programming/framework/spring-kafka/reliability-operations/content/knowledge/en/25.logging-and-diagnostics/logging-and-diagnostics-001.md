# Log container config

When a Spring Kafka consumer processes the wrong group, does not receive partitions as expected, commits offsets at a different time than designed, or the listener fails to start, the first question is usually: **what configuration is the container actually running with?** Looking only at application.yml or a @KafkaListener snippet is not enough, because configuration can come from multiple layers: Spring Boot properties, ConsumerFactory, listener container factory, annotation overrides, customizers, and configuration added at runtime.

Spring Kafka provides the **logContainerConfig** property on **ContainerProperties**. When enabled, the listener container **logs container configuration information at INFO level during startup**, helping engineers verify effective container settings without enabling DEBUG for the entire consumption process. This is a small but useful tool in the **Logging and Diagnostics** chapter of the **Spring Kafka Reliability Operations** module.

This article explains how to enable the property, how to read the logs within the right scope, how to distinguish container configuration from KafkaConsumer client properties, how to diagnose offset/concurrency/transaction/pause issues, and how to operate logging safely across multi-pod systems.

## 1. Why looking only at application.yml is not enough?

A Kafka listener in Spring Boot is typically formed from multiple layers:

~~~mermaid
flowchart TD
    A["application.yml / env vars"] --> B["Spring Boot KafkaProperties"]
    B --> C["ConsumerFactory"]
    B --> D["KafkaListenerContainerFactory"]
    E["Java @Bean / customizer"] --> D
    F["@KafkaListener annotation"] --> G["Actual listener container"]
    D --> G
    C --> G
    G --> H["KafkaConsumer instances"]
    H --> K["Kafka broker"]
~~~

Initial configuration example:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: orders-projection
      enable-auto-commit: false
    listener:
      ack-mode: record
      concurrency: 2
~~~

However, @KafkaListener can override several options:

~~~java
@KafkaListener(
    id = "orders-main",
    topics = "orders.created",
    groupId = "orders-projection-v2",
    concurrency = "4"
)
public void handle(OrderCreated event) {
    orderService.apply(event);
}
~~~

If reading only YAML, an operator might believe the group is orders-projection with concurrency=2, whereas the actual listener may be using groupId=orders-projection-v2 and concurrency=4.

In addition, a custom ConcurrentKafkaListenerContainerFactory bean created by the application may use a different AckMode or set properties different from Spring Boot auto-configuration. Container config logging helps clarify which container layer is operating.

### 1.1 Effective configuration is not a single object

It helps to distinguish:

- **Spring Boot configuration:** properties bound from application.yml, profiles, and environment.
- **ConsumerFactory:** Kafka client properties, serializers/deserializers, and security.
- **ContainerProperties:** poll/ack/error/idle/pause/transaction-related container behavior.
- **Listener endpoint:** id, topics, groupId, concurrency, and overrides from @KafkaListener.
- **KafkaConsumer runtime:** client.id, group membership, assignment, broker coordinator, metrics, and fetch state.
- **Business listener:** processing logic, database/HTTP dependencies, and retry semantics.

**logContainerConfig does not produce a complete dump of all these layers.** It primarily helps inspect listener container configuration; the other components must be verified separately.

## 2. What is the logContainerConfig property?

Spring Kafka provides the API:

~~~java
ContainerProperties containerProperties = ...;
containerProperties.setLogContainerConfig(true);
~~~

This is a boolean option in ContainerProperties.

| Property | Meaning |
|---|---|
| Name | logContainerConfig |
| Setter | setLogContainerConfig(boolean) |
| Location | ContainerProperties |
| Default | false |
| When enabled | Logs container configuration at INFO level when the container starts |
| Does it log every Kafka record? | No |
| Does it change commit/retry/partition assignment? | No |
| Does it automatically enable DEBUG for the Kafka client? | No |
| Does it replace metrics/tracing? | No |

The most important thing to remember: **logContainerConfig mainly serves startup information**. Do not treat it as a command that enables dynamic logging for every poll or a way to retrieve all runtime changes after the container is already running.

### 2.1 Setting true does not mean the log is always visible

If the logging backend or logger level blocks INFO, the Spring Kafka container log line may not appear.

A commonly used Spring Boot configuration:

~~~yaml
logging:
  level:
    org.springframework.kafka.listener: INFO
~~~

There is no need to switch the entire root logger to DEBUG just to view container configuration.

### 2.2 Log format may vary across Spring Kafka versions

The exact content and format depend on the Spring Kafka version's code, how ContainerProperties represents configuration, the container type, and the logging framework.

Do not write production parsers or alerts that hard-depend on a specific toString() line without checking the version. If long-term machine-readable data is needed, add a separate structured startup inventory or application metrics with a stable schema.

## 3. Enabling log container config on ConcurrentKafkaListenerContainerFactory

In applications using @KafkaListener, the most direct approach is configuring the factory used by the annotation.

~~~java
@Configuration
public class OrderKafkaConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
    ordersKafkaListenerFactory(
            ConsumerFactory<String, OrderCreated> consumerFactory) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<
                String, OrderCreated>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);

        factory.getContainerProperties()
               .setLogContainerConfig(true);

        return factory;
    }
}
~~~

Listener:

~~~java
@Component
public class OrderConsumer {

    private final OrderService service;

    public OrderConsumer(OrderService service) {
        this.service = service;
    }

    @KafkaListener(
        id = "orders-main",
        topics = "orders.created",
        groupId = "orders-projection",
        containerFactory = "ordersKafkaListenerFactory"
    )
    public void handle(OrderCreated order) {
        service.apply(order);
    }
}
~~~

**Key point:** the listener must reference the exact factory on which logContainerConfig was enabled. If @KafkaListener uses a different factory, changes on ordersKafkaListenerFactory will have no effect on that listener.

### 3.1 A factory can serve multiple endpoints

A single factory can create multiple listener containers. If multiple @KafkaListener annotations share that factory, each container created from it can inherit the logContainerConfig setting.

Example:

~~~text
ordersKafkaListenerFactory
  -> orders-main container
  -> orders-retry container
  -> orders-audit container
~~~

If you want to log only one group of listeners, you can separate factories or configure the exact corresponding container. Do not assume that enabling the setting on one factory automatically affects all Kafka listeners in the application.

### 3.2 Configure before container start

A clear workflow:

1. Declare ProducerFactory/ConsumerFactory and the listener factory.
2. Set logContainerConfig=true on the factory's ContainerProperties.
3. Let Spring create the listener containers from the factory.
4. The container starts, and startup logging is emitted according to the logger level.
5. Inspect the logs of the running instance.

If you change the property after the container has started, **do not expect startup configuration logs to appear retroactively**. A controlled restart of the container or application may be required to observe the new startup snapshot; restarting can trigger consumer rebalancing.

## 4. The Spring Boot auto-configuration case

If the application uses Spring Boot Kafka auto-configuration, Spring Boot can create the factory from KafkaProperties. When customizing a factory, avoid dropping retry, message converter, transaction, or AckMode settings that Boot has prepared.

A common approach is leveraging **ConcurrentKafkaListenerContainerFactoryConfigurer**:

~~~java
@Configuration
public class OrdersKafkaFactoryConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, String>
    ordersKafkaListenerFactory(
            ConcurrentKafkaListenerContainerFactoryConfigurer configurer,
            ConsumerFactory<String, String> consumerFactory) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<String, String>();

        configurer.configure(factory, consumerFactory);

        factory.getContainerProperties()
               .setLogContainerConfig(true);

        return factory;
    }
}
~~~

This method lets you use the Boot configurer to preserve Boot's corresponding settings, then apply the specific properties needed.

**Note:** method signatures, bean types, injection, and customizers may vary across Spring Boot versions. If the project has multiple Kafka configs, check bean wiring to ensure the configurer is used properly and no later configuration overrides the value just set.

### 4.1 When not creating a new factory

For a simple application, you can configure the existing factory directly via valid bean configuration/customization in the project. Avoid creating a bean with the default name just to enable logging if doing so unintentionally alters other options.

Some Boot-level configuration options change across versions; the stable expression in this lesson is the ContainerProperties.setLogContainerConfig(true) API on the actual factory.

### 4.2 Reading @KafkaListener overrides

Annotation attributes such as id, groupId, topics, topicPattern, clientIdPrefix, concurrency, or autoStartup can affect the actual container created.

Example:

~~~java
@KafkaListener(
    id = "payments-main",
    topics = "payments.confirmed",
    groupId = "payments-processing",
    concurrency = "6",
    autoStartup = "false",
    containerFactory = "paymentsKafkaListenerFactory"
)
public void onPayment(PaymentEvent event) {
    // ...
}
~~~

If autoStartup=false, the listener container may not have started yet; you may not see its startup configuration log when the application first boots.

You need to start the listener according to its actual lifecycle and inspect logs at the time the container starts.

## 5. Directly declared KafkaMessageListenerContainer case

Not every application uses @KafkaListener. Some projects create KafkaMessageListenerContainer directly in Java.

~~~java
@Bean
KafkaMessageListenerContainer<String, String> manualOrdersContainer(
        ConsumerFactory<String, String> consumerFactory) {

    ContainerProperties properties =
        new ContainerProperties("orders.created");

    properties.setGroupId("manual-orders-group");
    properties.setAckMode(ContainerProperties.AckMode.RECORD);
    properties.setLogContainerConfig(true);

    properties.setMessageListener(
        (MessageListener<String, String>) record ->
            System.out.println(record.value())
    );

    return new KafkaMessageListenerContainer<>(
        consumerFactory,
        properties
    );
}
~~~

This is a standalone example to clearly illustrate ContainerProperties; production code should replace System.out.println with controlled logging or a business handler, proper exception handling, and full security.

A direct container bean is not necessarily registered in the KafkaListenerEndpointRegistry of annotation-driven listeners. When you need to retrieve it for pause/stop or diagnostics, inject the bean by its appropriate name/reference.

### 5.1 Concurrency in a direct container

A direct KafkaMessageListenerContainer corresponds to a single KafkaConsumer/container. To run multiple consumers under the same logical listener, applications typically use ConcurrentMessageListenerContainer or a @KafkaListener factory with concurrency.

The logContainerConfig setting still belongs to ContainerProperties, though how the container creates and manages child instances differs.

## 6. Container config log vs. Kafka consumer config log

Two concepts are easily confused:

**Spring Kafka container config log**

- Enabled via ContainerProperties.logContainerConfig.
- Belongs to the listener container framework.
- Reflects a set of container configurations.
- Used to inspect AckMode, poll, and listener-related settings as logged by the version.

**Apache Kafka client config log**

- Emitted by Kafka ConsumerConfig/ProducerConfig and Kafka client logging.
- Includes client properties such as bootstrap.servers, group.id, auto.offset.reset, request.timeout.ms, enable.auto.commit, and many Kafka client parameters.
- Has its own logging mechanism and loggers, not directly controlled by logContainerConfig.
- May expose more infrastructure/security-related config details; verify before enabling broad logging levels.

Table:

| Question | Primary source |
|---|---|
| Which AckMode does the Spring listener use? | ContainerProperties / container config log |
| Does the container have observationEnabled? | Effective ContainerProperties / observability startup inventory |
| What auto.offset.reset does the Kafka consumer use? | ConsumerFactory / Kafka client effective config |
| Which partitions are assigned to the Kafka consumer? | Consumer assignment logs/events/metrics |
| Which topics does the listener actually process? | @KafkaListener endpoint + container subscription/runtime assignment |
| How many partitions does the Kafka broker hold? | Kafka admin/broker metadata |
| What is the consumer group committed offset? | Kafka group offset query |
| Is the listener retrying indefinitely? | ErrorHandler config + retry logs/metrics |

**Do not mistake a single container config log line for proof that all KafkaConsumer properties were applied correctly.**

### 6.1 Why does group.id especially need verification?

In Spring Kafka, @KafkaListener.id can become the group ID when no separate groupId is provided, depending on the idIsGroup setting.

Example:

~~~java
@KafkaListener(
    id = "orders-main",
    topics = "orders.created"
)
public void handle(OrderCreated event) {
    // ...
}
~~~

If idIsGroup=true and there is no explicit groupId, the actual group.id may be orders-main instead of the spring.kafka.consumer.group-id value the operator read from YAML.

A new group has its own committed offset namespace; the service may replay data or start at a different offset according to auto.offset.reset. This is a critical reliability bug that can be misunderstood as “Kafka is not receiving messages”.

Explicit approach:

~~~java
@KafkaListener(
    id = "orders-main",
    groupId = "orders-projection-prod",
    topics = "orders.created"
)
~~~

Container config logging is one source of evidence; you still must verify effective group membership/committed offsets on the broker.

## 7. Important ContainerProperties attributes to know

ContainerProperties has many options controlling listener container behavior. Which subset appears in the config log may vary by Spring Kafka version.

| Property | Operational role | Symptoms requiring investigation |
|---|---|---|
| ackMode | Offset acknowledgment/commit boundary | Commits too early or too late |
| syncCommits | Uses synchronous or asynchronous commit | Commit latency or error visibility |
| ackCount | Record threshold for COUNT/COUNT_TIME | Slow offset progression |
| ackTime | Time threshold for TIME/COUNT_TIME | Periodic commit not matching expectations |
| pollTimeout | KafkaConsumer poll timeout | Latency, CPU, and polling cadence |
| pollTimeoutWhilePaused | Poll timeout while container is paused | High CPU while paused |
| idleEventInterval | Interval for emitting listener idle events | Missing IdleEvent or emitted too frequently |
| noPollThreshold | Threshold for assessing nonresponsive poll | Consumer unresponsive alerts |
| monitorInterval | Interval for checking nonresponsive consumers | Monitoring event cadence |
| pauseImmediate | Pause after current record or end of poll | Slow backpressure reaction |
| stopImmediate | Stop timing after current record | Shutdown duration |
| logContainerConfig | Whether to log startup configuration at INFO | Missing startup snapshot |
| commitLogLevel | Log level for offset commits | Commit debug too noisy or missing |
| missingTopicsFatal | Startup failure when topics are missing | Listener fails to start |
| authExceptionRetryInterval | Retry after authorization error per policy | Consumer stopped or waiting due to ACL |
| observationEnabled | Enable Micrometer Observation | Traces/metrics not appearing |
| micrometerEnabled | Enable legacy Micrometer listener timers | Missing timers or duplicated with observation |

**Do not infer that every property in the table is always printed verbatim by logContainerConfig.** The framework's toString/config print content depends on version and implementation.

### 7.1 Related properties at different layers

Some information is close to the container but is not a ContainerProperties field in the same way:

- **Concurrency:** usually configured on ConcurrentMessageListenerContainer or the factory, and can be overridden by @KafkaListener.
- **CommonErrorHandler:** usually attached to the container/factory; do not expect logContainerConfig to show full BackOff/DLT semantics.
- **Deserializer:** belongs to ConsumerFactory/Kafka client setup.
- **Kafka transaction manager:** belongs to transaction integration; inspect bean wiring.
- **Broker partition count:** obtained from broker metadata.

Comprehensive diagnostics require combining multiple sources rather than relying on a single log line.

## 8. Example of reading startup logs in context

Depending on the Spring Kafka version, a configuration log may have different structures/formats. The following diagram only illustrates the meaning:

~~~text
INFO [orders-main] Spring Kafka listener container configuration:
  topics: [orders.created]
  ackMode: RECORD
  pollTimeout: 5000
  logContainerConfig: true
  observationEnabled: false
~~~

**This is an illustrative log, not a byte-for-byte guaranteed output from a specific Spring Kafka version.** In practice, it may be a text snippet like ContainerProperties{...}, include different fields, or be emitted under another logger in the listener package.

When inspecting, combine:

- Startup timestamp.
- Pod/instance ID.
- Application version and Spring Kafka version.
- Listener/container ID.
- Consumer group ID.
- Topic subscription.
- Concurrency/child client IDs if any.
- Container config snapshot.
- Partition assignment events appearing after startup.

### 8.1 Do not grep a single field and jump to conclusions

If ackMode is not visible in the log line, do not conclude it equals a specific value. That version may not print this field, or the log line may have been truncated by the collector.

Cross-check configuration beans and runtime metadata when needed. Logs are **evidence**, not the complete specification of effective configuration.

### 8.2 Snapshot vs. live state

If a container is paused after startup, the startup config log may indicate pauseImmediate=true but **does not prove the container is currently paused**.

Similarly, a startup log showing concurrency=3 does not prove all three consumers currently have partition assignments. The Kafka topic may have fewer partitions, or a group rebalance may leave a child without an assigned partition.

Combine container state APIs, Application Events, and Kafka metrics.

## 9. Example: diagnosing AckMode and offset commits

A service reports “the consumer processed records, but offsets are not advancing steadily”. It is possible AckMode is BATCH instead of RECORD, or errors are occurring during commit.

Explicit configuration example:

~~~java
factory.getContainerProperties()
       .setAckMode(ContainerProperties.AckMode.RECORD);

factory.getContainerProperties()
       .setLogContainerConfig(true);
~~~

Suppose one poll receives A, B, C, D; the listener processes each record.

- **AckMode.RECORD:** the container typically acknowledges/commits per successfully processed record and commit policy.
- **AckMode.BATCH:** the container processes records from the poll and commits at the batch boundary.
- **AckMode.TIME/COUNT/COUNT_TIME:** commits depend on the corresponding thresholds.
- **AckMode.MANUAL/MANUAL_IMMEDIATE:** the application must acknowledge per contract.

The config log helps identify the value the container holds. However, it does not prove **each commit actually succeeded**.

### 9.1 Commit logs differ from config logs

ContainerProperties has **commitLogLevel** to adjust the log level related to offset commits depending on API/version. Example:

~~~java
factory.getContainerProperties().setCommitLogLevel(
    LogIfLevelEnabled.Level.DEBUG
);
~~~

This is a different mechanism from setLogContainerConfig(true):

- logContainerConfig: logs **configuration** at startup.
- commitLogLevel: log level for **offset commit** information during operation.

To investigate commit progression, enabling only logContainerConfig is usually insufficient; check consumer group offsets, Kafka client metrics, and commit outcomes.

### 9.2 Manual AckMode requires inspecting listener code

A manual-ack listener:

~~~java
@KafkaListener(
    topics = "orders.created",
    containerFactory = "manualAckFactory"
)
public void onOrder(
        ConsumerRecord<String, OrderCreated> record,
        Acknowledgment ack) {

    orderService.apply(record.value());
    ack.acknowledge();
}
~~~

If the code does not call acknowledge() after processing, offsets may not advance as expected. No config log replaces understanding listener acknowledgment logic.

**Do not place ack.acknowledge() in a finally block** if failed business logic requires retry.

### 9.3 Auto commit is a separate layer

The Kafka client property **enable.auto.commit** can alter semantics if unintentionally enabled. This is a client property and must be verified on ConsumerFactory/effective Kafka consumer config.

Do not conclude auto-commit behavior solely from ContainerProperties ackMode. In Spring Kafka, the framework typically coordinates commits and disables auto-commit by default unless explicitly configured in modern versions; still, always verify the effective value.

## 10. Diagnosing concurrency and partition assignment

A common scenario: the application sets concurrency=8, but the topic only has 3 partitions and the consumer group shows only a few consumers receiving records.

~~~text
Topic orders.created:
  partitions: 0, 1, 2

Listener concurrency: 8
Consumer group members/child consumers: up to 8

At most 3 members have assigned partitions
The remaining members may be idle
~~~

Multiple child consumers not processing messages does not mean the listener container is misconfigured. A consumer group generally does not assign multiple consumers to read the same partition simultaneously.

### 10.1 Configuration in factory and annotation

~~~java
factory.setConcurrency(4);
~~~

The annotation can override it:

~~~java
@KafkaListener(
    id = "orders-main",
    concurrency = "8",
    topics = "orders.created"
)
~~~

Concurrency is not just a ContainerProperties setting. Check effective concurrency on the ConcurrentMessageListenerContainer/endpoint and the actual number of child consumers.

### 10.2 Child containers have their own IDs

A concurrent container can generate child IDs:

~~~text
orders-main-0
orders-main-1
orders-main-2
orders-main-3
~~~

Suffix conventions depend on the framework/runtime. Client IDs also have suffixes and may differ from listener IDs. When searching logs, match the parent endpoint and its children rather than looking at one parent line and assuming all consumers are ready.

### 10.3 Configuration does not equal runtime ownership

Even when startup config is correct, a group can rebalance because:

- A new pod joins or leaves the group.
- A consumer exceeds max.poll.interval.ms.
- Topic partition count changes.
- Broker/coordinator error occurs.
- Network interruption happens.
- Consumer shutdown/restart occurs.

Inspect partition assignment logs, ConsumerPartitionAssignedEvent/RevokedEvent depending on version, Kafka group describe output, and lag per partition. Container config logging is only the starting point.

## 11. Diagnosing startup failures caused by missing topics

Spring Kafka has the **missingTopicsFatal** setting in ContainerProperties in supported versions.

If a listener references a nonexistent topic, the container may:

- Fail startup if policy requires the topic to exist.
- Wait for the topic to appear or handle it per another version/configuration.
- Be blocked by metadata/authentication errors that make the failure look like a missing topic.

You can log the option explicitly:

~~~java
factory.getContainerProperties()
       .setMissingTopicsFatal(true);

factory.getContainerProperties()
       .setLogContainerConfig(true);
~~~

When a container fails to start, check:

1. Actual topic name from @KafkaListener.
2. Bootstrap servers and cluster environment.
3. ACLs for Describe/Read.
4. Whether the topic exists in the cluster.
5. missingTopicsFatal value.
6. Error logs at startup.
7. KafkaAdmin auto topic creation policy.
8. Network and broker metadata availability.

### 11.1 Do not infer a missing topic solely from empty assignment

A consumer with no assigned partitions may result from the topic having fewer partitions than consumers, a group rebalance, or a different subscription, rather than the topic not existing.

Container config logs help identify the intended topic; broker metadata confirms reality.

### 11.2 Do not enable auto-create topic as a quick fix

Auto-creating topics can result in partition counts, replication factors, or retention policies that violate production policy. If a wrong topic name is discovered, fix the configuration and provisioning workflow instead of enabling uncontrolled auto-creation.

## 12. Diagnosing pauseImmediate and backpressure

An operator calls pause(), yet the listener still processes many records before stopping. Check:

- Does the container have pauseImmediate enabled?
- Is the listener record-based or batch-based?
- What is max.poll.records?
- Does the current record take long to process?
- Does the parent concurrent container have multiple children not yet paused?

Example:

~~~java
factory.getContainerProperties()
       .setPauseImmediate(true);

factory.getContainerProperties()
       .setLogContainerConfig(true);
~~~

Per semantics:

- pauseImmediate=false: the container may finish processing all records from the prior poll before pausing.
- pauseImmediate=true: a record listener can stop after the current record, keeping remaining records in memory until resumed.

Config logs help identify the setting, but **do not indicate whether the pause has currently taken effect**. Inspect:

~~~java
MessageListenerContainer container =
    registry.getListenerContainer("orders-main");

boolean requested = container.isPauseRequested();
boolean effective = container.isConsumerPaused();
~~~

For concurrent containers, requested and effective states can diverge temporarily while children finish processing in-flight records.

### 12.1 Pause and consumer poll

When a container is paused, Spring Kafka may still poll to maintain group membership. Depending on the version, pollTimeoutWhilePaused determines the timeout for these polls.

If the listener blocks for a very long time before pause takes effect, max.poll.interval.ms can still be exceeded. LogContainerConfig does not fix the root cause; configure downstream timeouts and monitor listener processing duration.

## 13. Diagnosing transactions/EOS

If a listener uses Kafka transactions, the application needs to verify:

- Is ProducerFactory transaction-capable?
- Is KafkaTransactionManager attached to the right container/factory?
- Is the listener running inside a Kafka transaction?
- Are consumer offsets committed together with Kafka output?
- Does downstream use read_committed when required?

Some transaction-related container settings may be reflected in container config, but **logContainerConfig alone does not prove the entire Kafka transaction wiring is correct**.

Example scenario:

~~~text
@KafkaListener receives order event
  -> KafkaTemplate sends orders.out
  -> Container commits consumed offset

Expected: output + offset in the same Kafka transaction
~~~

Actual verification requires:

- A transaction-capable ProducerFactory with transactionIdPrefix.
- KafkaTransactionManager or a version-appropriate Kafka-aware manager.
- Listener container transaction configuration.
- KafkaTemplate using the correct transactional factory.
- Commit/abort integration tests.
- Producer fencing/transaction commit logs.
- Downstream consumer isolation.level=read_committed when needed.

### 13.1 Avoid confusing startup config with commit outcome

Even if logs show the container has transaction support attached, Kafka commits can still fail due to:

- ProducerFencedException.
- Transaction timeout.
- Broker coordinator error.
- Kafka send failure.
- Consumer group rebalance.
- Network interruption.

**A “container config” line is not proof that a transaction commit succeeded.**

### 13.2 Transaction manager configured outside ContainerProperties

Across different Spring Kafka versions, the API for attaching KafkaAwareTransactionManager to a listener container has changed. Do not copy an old setter from a blog and expect it to compile in newer versions.

LogContainerConfig assists diagnostics; tests and bean wiring verification prove Kafka transactions actually take effect.

## 14. Container config logging and error handlers

Spring Kafka provides error handling components such as DefaultErrorHandler, BackOff, DeadLetterPublishingRecoverer, AfterRollbackProcessor, and retry topic infrastructure.

A reader may see some retry/error handler information in container logs, but should not assume it outputs all of:

- BackOff initial interval.
- Maximum attempts.
- List of non-retryable exceptions.
- DLT topic routing.
- Exception classification logic.
- Recovery commit policy.
- Retry topic delay.
- ErrorHandlingDeserializer config.

These details may reside in other beans/factories and require a separate startup inventory or application configuration inspection.

### 14.1 Retry policy example

~~~java
@Bean
DefaultErrorHandler ordersErrorHandler(
        DeadLetterPublishingRecoverer recoverer) {

    var backOff = new FixedBackOff(1_000L, 4L);

    return new DefaultErrorHandler(
        recoverer,
        backOff
    );
}
~~~

This example uses a 1-second FixedBackOff and four retries according to the handler's semantics. Understand the API version to determine total deliveries and recoverer behavior.

If an operator observes records repeating many times, logContainerConfig reveals only part of the container setup. You must inspect the handler bean, exception path, and DLT outcomes.

### 14.2 Do not use unbounded DEBUG for every record

To investigate a case, you can temporarily raise the log level for a specific package/class, but overly verbose logging on high-throughput consumers can cause:

- High disk and network I/O.
- CPU spent on serialization/log formatting.
- Metric/log backend overload.
- PII or payload leakage.
- Increased latency and poll interval violations.
- High retention costs.

Enabling logContainerConfig at INFO helps because it does not actively log every record, though you still need to consider container count and startup volume during scale-out.

## 15. How should logging levels be configured?

In Spring Boot:

~~~yaml
logging:
  level:
    root: INFO
    org.springframework.kafka.listener: INFO
    org.apache.kafka.clients: WARN
~~~

This is only an illustrative policy. You do not necessarily have to set the entire Apache Kafka client package to WARN if you want other useful client warnings/info.

The primary goal is that **the container logger allows INFO**. If the runtime uses custom Logback/Log4j2 config, package overrides and appender filters can also determine whether the log appears.

### 15.1 When debugging only one listener

Instead of setting:

~~~yaml
logging:
  level:
    root: DEBUG
~~~

prefer:

1. Enable logContainerConfig on the target listener factory.
2. Keep the org.springframework.kafka.listener package at INFO.
3. Collect startup logs from the pod under investigation.
4. If insufficient, enable DEBUG on a specific class for a limited duration.
5. Remove DEBUG after closing the incident.

In applications with hundreds of child containers, startup logging can produce many lines. Even without logging every record, size and retention must be controlled.

### 15.2 Logging Kafka client config is a separate option

Apache Kafka clients can log lines like ConsumerConfig values or ProducerConfig values during client creation, though exact content, log level, and redaction depend on client version.

Do not treat client config logs as output of logContainerConfig. If you need to log Kafka client config for investigation, check first for potential exposure of sensitive settings and enable only the necessary scope.

## 16. Supplementary structured startup inventory

Because logContainerConfig does not guarantee all operator-needed details are present, a complex application can add **selective, schema-stable, sanitized** logging.

Example of an application logging inventory:

~~~text
event=KAFKA_LISTENER_CONFIG
service=orders-projection
instance=pod-a
listenerId=orders-main
groupId=orders-projection-prod
topics=orders.created
concurrency=3
ackMode=RECORD
observationEnabled=true
logContainerConfig=true
applicationVersion=2026.11.15
~~~

This is an **application-defined schema**, not a default Spring Kafka format. Only log fields verified directly from actual beans/endpoints.

### 16.1 Why sanitize?

Some configuration objects may contain:

- Bootstrap addresses and internal hostnames.
- Security mechanisms.
- Truststore/keystore paths.
- Sensitive business-related topic names.
- Client IDs or environment-specific routing.
- Custom interceptors/converters whose toString() contains unwanted data.

Do not log:

- Raw sasl.jaas.config.
- Username/password, API tokens, OAuth credentials.
- Private key material.
- Full TLS keystore content.
- Raw Kafka message payloads.
- Header values containing PII or secrets.

Even if Spring/Kafka has built-in masking mechanisms, do not rely entirely on them for a custom startup dump.

### 16.2 Example: logging the list of listener IDs

In a Spring application with a @KafkaListener registry:

~~~java
@Component
public class KafkaListenerStartupInventory {

    private static final Logger log =
        LoggerFactory.getLogger(KafkaListenerStartupInventory.class);

    private final KafkaListenerEndpointRegistry registry;

    public KafkaListenerStartupInventory(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    @EventListener(ApplicationReadyEvent.class)
    public void report() {

        for (MessageListenerContainer container :
                registry.getListenerContainers()) {

            log.info(
                "event=KAFKA_LISTENER_INVENTORY listenerId={} running={} " +
                "pauseRequested={}",
                container.getListenerId(),
                container.isRunning(),
                container.isPauseRequested()
            );
        }
    }
}
~~~

This snippet logs only state fields through the container API; it does not attempt to serialize KafkaConsumer or the entire ConsumerFactory properties map. Verify getListenerId() and state APIs against your actual version if using custom listener container types.

### 16.3 Avoid calling KafkaConsumer outside the consumer thread

Do not use inventory code to grab KafkaConsumer directly and call subscribe/assignment/pause/seek arbitrarily from the ApplicationReadyEvent thread. KafkaConsumer enforces thread-ownership rules; improper access can cause races or ConcurrentModificationException/IllegalStateException.

Use registry/container APIs and Application Events supported by Spring Kafka.

## 17. Diagnosing listener ID, group ID, and client ID

Logs typically contain at least three identities:

- **Listener ID:** endpoint/container identity, e.g., orders-main.
- **Group ID:** Kafka consumer group, e.g., orders-projection-prod.
- **Client ID:** Kafka client metric/log identifier, such as orders-projection-0, orders-projection-1.

They are not synonymous.

~~~text
@KafkaListener.id        = orders-main
@KafkaListener.groupId   = orders-projection-prod
client.id for child      = orders-client-0
~~~

When an incident is reported on a specific client.id, map the client back to its child container/listener and group. Container configuration shows intent, whereas runtime client metrics and assignments show what that specific consumer is doing.

### 17.1 Does changing the listener ID have side effects?

When groupId is explicitly declared, changing the listener ID can affect registry lookups, monitoring labels, and application event filtering.

When groupId is omitted and idIsGroup=true, changing @KafkaListener.id can even **change group.id**, leading to a new offset namespace. That is a much more dangerous misconfiguration than renaming a log label.

### 17.2 Why does log container config help?

If a deployment recently refactored listener IDs, startup logs help verify actual IDs/containers and catch discrepancies with the operational contract.

Still, do not decide to reset offsets based on a single log line. Always inspect actual group committed offsets on Kafka.

## 18. Diagnosing environment and profile overrides

A service has:

~~~yaml
# application.yml
spring:
  kafka:
    consumer:
      group-id: orders-projection
~~~

Yet the production environment may override it:

~~~text
SPRING_KAFKA_CONSUMER_GROUP_ID=orders-projection-blue
~~~

Or @KafkaListener(groupId="orders-projection-prod") may take precedence with yet another value.

Configuration sources should be cross-checked in an order consistent with Spring Boot:

- application.yml / application-profile.yml.
- Environment variables.
- ConfigMaps/Secrets.
- Command-line arguments.
- Bean configuration.
- Container factory customizers.
- @KafkaListener overrides.
- Runtime lifecycle changes.

Do not rely on memory to deduce precedence in a system with many customizers; inspect **effective configuration** and test actual behavior.

### 18.1 Startup logs are per-instance evidence

Pod A and Pod B may run different app versions or different environment variables during a rolling deployment. Do not take Pod A's startup config log and conclude Pod B uses the exact same configuration.

Tag logs with:

~~~text
service, environment, pod/instance, build version, listener id, timestamp
~~~

If the log collector strips these labels, fix the logging pipeline before assessing config drift.

### 18.2 Comparing config drift across replicas

When a group has 5 pods:

1. Collect the startup config log of each pod.
2. Compare key container properties and app versions.
3. Compare runtime group IDs, client IDs, and assignments.
4. Check whether differences are intentional due to an in-progress rollout.
5. Identify which instance has the incorrect setting.
6. Fix ConfigMap/Deployment/Bean configuration.
7. Roll out in a controlled manner and re-measure group rebalancing.
8. Do not reset offsets merely because of config drift.

Drift in AckMode or transaction config across replicas can cause pod-specific behavior differences that are very hard to diagnose from aggregate dashboards alone.

## 19. Container config logging and Micrometer Observation

In modern Spring Kafka:

~~~java
factory.getContainerProperties()
       .setObservationEnabled(true);

factory.getContainerProperties()
       .setLogContainerConfig(true);
~~~

These two properties serve independent purposes:

- logContainerConfig: startup configuration logging.
- observationEnabled: produces observations that can drive metrics/tracing.

If the spring.kafka.listener metric is missing, container config logs can indicate what values observationEnabled or micrometerEnabled hold. However, you also need to verify:

- Are ObservationRegistry/MeterRegistry configured?
- Is the Prometheus exporter working?
- Is the tracing bridge enabled?
- Has the listener actually received records yet?
- Is there a MeterFilter or sampling policy?

**Do not treat logContainerConfig as end-to-end verification of metrics/tracing.** It is only a complementary tool for the observability pipeline.

### 19.1 Legacy timers and Observation

When observationEnabled is enabled, Spring Kafka may disable the corresponding legacy Micrometer listener timer mechanism to avoid duplicate instrumentation, depending on the version. Seeing micrometerEnabled=true in source without checking observationEnabled is not enough to determine the final metric schema.

What matters is inspecting actual registry metrics and tracing spans after startup.

## 20. What information can log container config expose?

Operational configuration is usually not public data. Even though logContainerConfig does not actively dump every Kafka client secret, startup logs can still contain internal metadata and container design details.

Information types to consider:

- Topic and consumer group names can reveal business workflows.
- Bootstrap hosts and cluster names can reveal topology.
- Listener IDs and bean names can reveal service structure.
- Custom container properties or message listener toString() may contain proprietary data.
- Exception strings in the same startup log may contain paths or endpoint names.
- If client configuration logs are also enabled, security properties must be properly redacted.

### 20.1 Safe logging policy

- Enable only with a clear operational purpose.
- Use INFO on appropriate packages/classes; avoid global DEBUG.
- Do not stringify and log the entire KafkaProperties/Environment/ConsumerFactory map.
- Sanitize structured inventory.
- Restrict read access to startup logs.
- Set appropriate retention.
- Verify log pipeline masking/redaction.
- Do not include secrets in error details.
- Differentiate dev/staging/prod policies.

### 20.2 Should it be kept on long-term?

It can be kept enabled long-term if:

- Restart frequency is not excessively high.
- Log volume is low and cost is acceptable.
- Configuration strings have been verified not to leak secrets.
- Operations teams actually use startup config during incident investigation.
- Log retention and access control are appropriate.

It is not mandatory to keep it on for every container. In systems with thousands of consumers and frequent rollouts, the cost can be significant. Weigh support needs against log volume.

## 21. Container config logging does not alter behavior by itself

Some operators worry that enabling logging might cause a listener to switch AckMode, pause, or change group membership. **logContainerConfig** itself is an instrumentation/logging option, not a business/reliability policy.

It does not by itself:

- Change Kafka offsets.
- Commit or roll back Kafka transactions.
- Restart Kafka consumers.
- Increase concurrency.
- Change group.id.
- Seek to a new offset.
- Route records to a DLT.
- Enable pauseImmediate.
- Create a Kafka AdminClient.
- Enable Micrometer Observation.

**However, how you deploy the change can still have side effects.** If you enable the setting by deploying a new build or restarting containers, the rollout/restart can trigger rebalancing and affect latency. Distinguish the impact of **deployment** from logContainerConfig itself.

## 22. Investigation sequence when startup config logs are missing

If setLogContainerConfig(true) is set but the log line does not appear:

1. Confirm the code has been deployed to the pod under investigation.
2. Confirm the Spring Kafka version supports this API.
3. Check which container factory @KafkaListener actually uses.
4. Check whether a customizer overwrites ContainerProperties after you set it.
5. Confirm the container started and does not have autoStartup=false.
6. Confirm the package/class logger allows INFO.
7. Check Logback/Log4j2 appender filters.
8. Check whether the log collector captures startup logs from container start time.
9. Check whether the container config log has a different format than assumed.
10. If using a concurrent container, inspect parent/child logs around the same timestamp.
11. If the pod restarts too quickly, check previous container logs.
12. Run a controlled startup in staging with the same factory.

**Do not enable root DEBUG** before checking the right listener factory and logging pipeline.

### 22.1 A common bean factory mistake

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, String>
debugFactory(ConsumerFactory<String, String> cf) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, String>();

    factory.setConsumerFactory(cf);
    factory.getContainerProperties().setLogContainerConfig(true);

    return factory;
}
~~~

Yet the annotation uses:

~~~java
@KafkaListener(
    topics = "orders.created",
    containerFactory = "kafkaListenerContainerFactory"
)
~~~

The application enabled logging on debugFactory, while the listener uses kafkaListenerContainerFactory. This is a wiring mistake, not a Logback issue.

## 23. Investigation sequence when the container misbehaves despite correct logs

If the logs look right yet behavior remains abnormal:

1. Confirm the config snapshot and application version.
2. Inspect Kafka client effective properties separately.
3. Inspect broker metadata/topic partitions/ACLs.
4. Inspect committed offsets and group membership.
5. Read consumer assignment/rebalance events.
6. Inspect error handler/retry/DLT configuration.
7. Inspect listener exceptions and business side effects.
8. Inspect transaction manager/producer factory if using Kafka EOS.
9. Inspect pause/resume state and poll liveness.
10. Inspect metrics/traces, especially consumer lag, retries, and processing latency.
11. Reproduce in integration/staging if needed.
12. Change configuration only after identifying the root cause.

LogContainerConfig provides **initial configuration**, not a substitute for runtime evidence.

## 24. Diagnostic scenarios table

| Symptom | What to check in container config | Additional sources needed |
|---|---|---|
| Listener does not start | autoStartup, missingTopicsFatal, topic subscription | Startup exceptions, broker metadata, ACLs |
| Consumer unexpectedly reads from beginning | Listener/group ID and endpoint overrides | Group committed offsets, auto.offset.reset |
| Offsets advance slowly | AckMode, ackCount, ackTime, syncCommits | Offset query, commit logs, listener duration |
| Some child consumers idle | Concurrent container setting, listener ID | Topic partition count, group assignment |
| Pause reacts slowly | pauseImmediate, pollTimeout | Current record duration, paused events |
| Unresponsive poll | pollTimeout/monitor settings | Thread dump, downstream timeouts, max.poll.interval.ms |
| Too many retries | Container error configuration if present | DefaultErrorHandler, BackOff, DLT metrics |
| No Kafka tracing | observationEnabled | ObservationRegistry, trace headers/exporter |
| Send/offset not atomic | Partial transaction container wiring | KafkaTransactionManager, ProducerFactory, integration test |
| Config log missing | logContainerConfig, INFO logger | Factory wiring, lifecycle, logging pipeline |
| Broker auth error | Insufficient data from container log | Kafka client security settings, ACLs, broker logs |
| High CPU while paused | pollTimeoutWhilePaused | CPU profiler, poll metrics, actual pause state |

One symptom can have multiple causes; do not treat a single field as conclusive without supporting evidence.

## 25. Testing configuration logging on deployment

A useful integration test does more than assert that the setter was called. It should start the actual listener container and confirm the startup log is present when the flag is on.

### 25.1 Test flag on

1. Create a listener factory with logContainerConfig=true.
2. Create a listener container from the factory.
3. Enable INFO for the Spring Kafka container logger package/class.
4. Attach a suitable test log appender or log capture.
5. Start the container in the test context.
6. Wait for the startup lifecycle to complete.
7. Assert the log contains container configuration details matching the version format.
8. Stop the container properly to prevent test leaks.

Do not assert byte-for-byte string equality against the entire ContainerProperties.toString(), as minor versions may change field order/format.

### 25.2 Test flag off

1. Create a second listener factory with flag=false.
2. Start the container with the INFO logger.
3. Assert no startup config log from that flag mechanism appears for that container.
4. Do not assume all Kafka client config logs disappear as well; client logging is a separate mechanism.

### 25.3 Test factory wiring

1. Register factory A with flag=true and factory B with flag=false.
2. Create two @KafkaListeners using explicit containerFactory attributes.
3. Start the context.
4. Cross-check listener/container IDs in the logs.
5. Confirm only the container using A emits the corresponding config log.
6. Verify annotations do not reference the wrong bean.

### 25.4 Test group ID override

1. ConsumerFactory has group.id=from-factory.
2. @KafkaListener sets groupId=from-annotation.
3. Start the listener.
4. Observe endpoint/container metadata and actual group membership.
5. Confirm the Kafka group uses from-annotation.
6. Do not use group reset/seek in the test just to verify logging.

### 25.5 Test sanitized inventory

If the application has a custom startup inventory:

- Inject a fake secret into the test configuration.
- Capture logs.
- Assert the secret does not appear.
- Assert allowed identifiers are still present.
- Verify the log record contains service/pod/version context.
- Do not test secret masking by printing a real secret.

## 26. Notes on version compatibility

Spring Kafka has evolved many APIs across 2.x, 3.x, and 4.x releases. logContainerConfig is a ContainerProperties attribute, however:

- Package names and setters of some related properties may differ.
- How containers are created from listener factories may change.
- Transaction manager/observation APIs differ across versions.
- New properties may be added to toString/config logs.
- Exact log format and logger class may change.
- Spring Boot property bindings/configurer may change.

Therefore, record in the runbook:

~~~text
Application version
Spring Boot version
Spring Kafka version
Kafka client version
Listener factory bean name
Container endpoint ID
Timestamp/pod instance of the config log
~~~

This is metadata for cross-referencing, not mandatory default content inside logContainerConfig.

### 26.1 Do not use newer version logs to infer an older incident

If an error occurred before a rolling deployment, the new pod's container config log may reflect already-fixed code/config. To find the root cause, obtain logs from the **instance and version at the time of the failure**, including previous container logs if the pod restarted.

### 26.2 Avoid writing overly brittle parsers

If a pipeline parses startup logs into an automated inventory, prefer custom structured logs with an application-owned schema. Do not parse a framework toString() as a multi-year stable contract.

## 27. A safe runbook for rolling out container config logging

When needing to investigate a specific listener in production:

1. Identify the service, listener ID, and Kafka consumer group.
2. Check whether a startup config log already exists.
3. If not, identify the right factory and enable setLogContainerConfig(true).
4. Ensure the Spring Kafka listener logger allows INFO.
5. Verify configuration does not print secrets and follows log policy.
6. Deploy a controlled canary/rolling deployment.
7. Collect logs from the exact pod and build version.
8. Verify AckMode, poll, pause, idle/monitor, and available properties.
9. Verify annotation overrides, actual group ID, and concurrency.
10. Inspect Kafka client config/assignment/offsets separately.
11. Combine application events, lag, retries, DLT, and transaction outcomes to identify root cause.
12. When finished, decide whether to keep the flag on or off based on log volume and policy.
13. Record the necessary effective configuration in the incident report without attaching secrets.
14. Update tests to detect config drift if the issue could recur.

**Do not restart all Kafka consumers solely to grab logs during an active incident if restarting could erase evidence and cause unnecessary rebalancing.** Extract existing logs/state first; roll out only when aligned with incident priority.

## 28. Common misconceptions

**“logContainerConfig=true logs every Kafka record.”** False. It is startup container configuration logging.

**“Enabling logContainerConfig gives full consumer properties.”** False. KafkaConsumer client config and container config belong to different layers.

**“Logs showing the listener running mean it has assigned partitions.”** False. Runtime assignment must be checked separately.

**“Correct container config proves offsets committed properly.”** False. Commit success is a runtime outcome.

**“Correct container config proves Kafka transactions are atomic.”** False. Transaction manager/factory wiring and integration tests are required.

**“Config on one factory applies to every @KafkaListener.”** False. Only listeners using that factory inherit it.

**“logContainerConfig lets you see all runtime changes over time.”** False. It mainly logs a snapshot at startup.

**“Not seeing the log means flag=false.”** Not necessarily. The logger might filter INFO, the container might not have started, logs might be dropped, or another factory might be in use.

**“One @KafkaListener has a single KafkaConsumer.”** Not when concurrency>1.

**“@KafkaListener.id is just a display name.”** Not quite. Registry lookup and sometimes group.id depend on ID when idIsGroup=true.

**“Root DEBUG must be enabled to see container config.”** No. Use INFO on the appropriate container logger.

**“Logging all config is always safe.”** No. Internal metadata and sensitive values can appear; sanitization and access control are needed.

**“Enabling the flag cannot affect operations in any way.”** The flag itself does not change behavior, but deploying/restarting to enable it can trigger rebalancing.

## 29. Pre- and post-enablement checklist

**Scope**

- [ ] Identified the right listener ID and factory bean.
- [ ] Read effective annotation groupId/concurrency/topics.
- [ ] setLogContainerConfig(true) is set before container startup.
- [ ] Did not create a new factory that drops error handler/transaction settings.
- [ ] Know whether the container has autoStartup=false.

**Logging**

- [ ] Spring Kafka listener logger allows INFO.
- [ ] Log collector captures logs at startup.
- [ ] Logs include service/instance/version/timestamp.
- [ ] No raw credentials or Kafka payloads logged.
- [ ] Appropriate retention and access control in place.
- [ ] Log volume evaluated relative to container/pod count.

**Diagnostics**

- [ ] Distinguished container properties from Kafka client properties.
- [ ] Verified runtime group membership/partition assignment.
- [ ] Verified committed offsets when investigating AckMode.
- [ ] Verified pause requested/effective when investigating backpressure.
- [ ] Verified error handler/BackOff/DLT separately.
- [ ] Verified Kafka transaction outcomes separately when using EOS.
- [ ] Used metrics/tracing to observe runtime, not just the startup snapshot.

**Verification**

- [ ] Tested enabling the flag on staging.
- [ ] Observed actual listener startup logs.
- [ ] Tested the flag=false case.
- [ ] Tested factory wiring and @KafkaListener overrides.
- [ ] Verified sanitization of custom inventory.
- [ ] Have a runbook for keeping/disabling the flag after an incident.

## 30. References

- Spring for Apache Kafka — Listener Container Properties: https://docs.spring.io/spring-kafka/reference/kafka/container-props.html
- Spring for Apache Kafka — Message Listener Containers: https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html
- Spring Kafka API — ContainerProperties: https://docs.spring.io/spring-kafka/api/org/springframework/kafka/listener/ContainerProperties.html
- Spring Kafka API — KafkaListenerEndpointRegistry: https://docs.spring.io/spring-kafka/api/org/springframework/kafka/config/KafkaListenerEndpointRegistry.html
- Apache Kafka consumer configuration: https://kafka.apache.org/documentation/#consumerconfigs

The links above are reference points; verify against the project's actual Spring Kafka/Kafka client versions before applying APIs/configurations.

## 31. Conclusion

**logContainerConfig** is a simple yet useful property on **ContainerProperties**: when enabled, Spring Kafka logs listener container configuration at **INFO level when the container starts**. It reduces investigation time for bugs caused by mismatches between YAML, Spring Boot auto-configuration, listener factories, and @KafkaListener annotations.

The real value of this feature lies in using it within the **right scope**. It is not a dump of all Kafka client properties, does not replace runtime assignment/offset/transaction metrics, does not track every post-startup change, and does not guarantee configuration content is completely non-sensitive. Combining protected config logs with listener IDs, group IDs, client IDs, Kafka consumer metrics, application events, and integration tests creates a reliable diagnostic workflow without turning on widespread DEBUG or unintentionally changing Kafka processing behavior.

