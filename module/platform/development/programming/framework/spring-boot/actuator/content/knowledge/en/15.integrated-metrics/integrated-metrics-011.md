# Identifying Kafka, RabbitMQ, and Integration Library Metrics by Dependency

## 1. Why Do Two Applications Both Having Actuator Show Different Metrics?

An HTTP-only application and an application consuming Kafka messages can both use Spring Boot Actuator, yet their lists of metrics are not alike. Actuator provides the observation mechanism; the components actually present in the application determine which data sources exist to observe.

A **library dependency** is the starting clue to predict observability, not proof that every library metric already exists or has traffic. For example, adding Spring Kafka can create a `KafkaTemplate` in the Spring context. Still, an actual producer may not have been created yet if the app has not sent any messages.

To identify an integrated metric, connect the following chain:

```text
Library present on classpath
        ↓
Auto-configuration conditions satisfied
        ↓
Bean or actual resource created
        ↓
Meter binder attached to the right object
        ↓
Meter registered, either before or after the first operation
        ↓
Actual operations update the metric
        ↓
Registry exports data via endpoint or monitoring system
```

Any link in this chain can fail. Thus, "not seeing a metric" does not automatically mean a library is missing, and "seeing a metric name" does not automatically prove messages were processed.

This lesson uses Spring Boot **3.3.x**, Spring Kafka **3.2.x**, Spring AMQP **3.1.x**, and Micrometer **1.13.x** as context. Java examples use Java 17+ syntax; the demo project selects JDK 21. In real projects, inspect resolved versions in your dependency tree instead of using latest-version docs to back-infer older behavior.

## 2. Separate Three Observation Layers Before Looking at Meter Names

A messaging system has at least three places providing information:

| Layer | Object Being Measured | Typical Questions Answered |
| --- | --- | --- |
| In-JVM client | Kafka producer/consumer or RabbitMQ Java client | How much did the client send/receive, are there retries/errors, how many connections/channels? |
| Spring integration | Template, listener container, integration flow components | How long did a send operation or listener invocation take, did it succeed or fail? |
| Broker/infrastructure | Kafka broker, RabbitMQ node/queue, and cluster | Are partition replicas healthy, how many messages remain in the queue, is the broker resource-starved? |

Client and Spring metrics are collected inside the application process. Broker metrics require collection from the broker or an appropriate monitoring tool. Adding Kafka/RabbitMQ libraries to an app does not turn `/actuator/metrics` into a complete statistics dashboard of the external cluster.

For example, "consumer fetched a record from Kafka," "listener method finished executing," and "business logic saved data successfully" are three distinct events. A timer's duration must be understood according to the exact processing segment it wraps.

### Common Name Groups

| Micrometer Name Group | Typical Source | Initial Interpretation |
| --- | --- | --- |
| `kafka.producer.*` | Kafka producer client | Native producer metrics bridged into the registry |
| `kafka.consumer.*` | Kafka consumer client | Native consumer metrics, per client and assigned partitions |
| `kafka.stream.*` | Kafka Streams | Streams client/thread/task activity, when a Streams runtime actually exists |
| `spring.kafka.template` | Spring Kafka | Timer for operations through `KafkaTemplate` |
| `spring.kafka.listener` | Spring Kafka | Timer for listener invocations |
| `rabbitmq.*` | RabbitMQ Java client | Client-side connection, channel, and message operation metrics |
| `spring.rabbitmq.listener` | Spring AMQP, pre-Observation timer mechanism | Listener call duration, with that mechanism's result/exception tags |
| `spring.rabbit.listener`, `spring.rabbit.template` | Spring AMQP Observation | Timers created via Observation, using corresponding tag conventions |
| `spring.integration.*` | Spring Integration | Metrics for channels, handlers, sources, or integration flow observations |

The `*` here denotes a **name group**, not a literal meter name containing `*`. Actual lists depend on versions, created resources, and metrics configuration.

## 3. Kafka: Identifying Client Metrics vs. Spring Metrics

### 3.1. Which Dependencies Unlock Integration?

In a project with Spring Boot version management, the two primary dependencies for the Kafka experiment are:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-actuator'
implementation 'org.springframework.kafka:spring-kafka'
```

Spring Kafka pulls in the Kafka Java client transitively. Adding only `org.apache.kafka:kafka-clients` lets an app construct Java producers/consumers itself, yet does not mean Boot created `KafkaTemplate` and Spring Kafka factories.

For Boot-auto-configured producer/consumer factories, Boot attaches `MicrometerProducerListener` and `MicrometerConsumerListener`. These listeners wire client metrics into `MeterRegistry` following client creation/closing lifecycles. Boot also integrates `KafkaStreamsMicrometerListener` for `StreamsBuilderFactoryBean` when matching conditions hold. [Boot 3.3 Kafka metrics configuration](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/metrics/KafkaMetricsAutoConfiguration.java).

What to verify is **the factory has a metrics listener** and **the client has been created**. An existing `ProducerFactory` does not prove the producer has sent messages. Likewise, consumer configuration alone does not prove the container is running and assigned partitions.

Kafka Streams is a separate capability: adding Spring Kafka does not automatically create a topology, processing tasks, or state stores. Only look for Streams meters when the app actually has Streams libraries and configuration.

### 3.2. Recognizing Native Meters

Micrometer maps Kafka's metric groups and names into dotted names. For instance, group `producer-metrics` with `record-send-total` can become `kafka.producer.record.send.total`. Kafka tags like `client-id` convert to `client.id`; Spring listeners may add `spring.id`. [Micrometer 1.13 KafkaMetrics mapper](https://raw.githubusercontent.com/micrometer-metrics/micrometer/v1.13.0/micrometer-core/src/main/java/io/micrometer/core/instrument/binder/kafka/KafkaMetrics.java).

| Common Micrometer Name | Meaning to Identify |
| --- | --- |
| `kafka.producer.record.send.total` | Total records sent per producer statistics |
| `kafka.producer.record.error.total` | Record send errors per producer |
| `kafka.producer.record.retry.total` | Retry attempts per producer |
| `kafka.consumer.fetch.manager.records.consumed.total` | Records consumed by the consumer per fetch manager stats |
| `kafka.consumer.fetch.manager.records.lag.max` | Lag in records reported by the consumer |

These names are for **search orientation**, not a guarantee every client has all series right at startup. Per-topic/partition metrics may appear only once the client has corresponding resources or traffic.

Specifically, the Kafka client's `records-lag-max` is based on the consumer's current position, not necessarily on committed offsets. Therefore, it is not equivalent to total unfinished business work or commit lag of an entire consumer group. To monitor cluster-wide group lag, choose an appropriate source and metric definition. [Kafka 3.7 monitoring docs](https://kafka.apache.org/37/operations/monitoring/#consumer-fetch-metrics).

### 3.3. Spring Kafka Timers Are a Different Layer

`spring.kafka.template` measures sends via `KafkaTemplate`; `spring.kafka.listener` measures listener invocations. In the traditional timer mechanism, tags typically include `name`, `result`, and `exception`. With concurrent listeners, names can distinguish worker threads. [Spring Kafka 3.2 monitoring guide](https://docs.spring.io/spring-kafka/reference/3.2/kafka/micrometer.html).

A timer has recorded count (`COUNT`), total duration (`TOTAL_TIME`), and possibly max (`MAX`). Thus:

- Having `spring.kafka.template` in the registry with `COUNT = 0` does not prove messages were sent.
- Listener `COUNT` is not unique business messages when retries, failures, or batching occur.
- Consumer fetched records can differ from listener completions; do not force those two counters to always match.
- Template latency does not measure end-to-end time from send until the receiver finishes business processing.

Do not manually add `@Timed` onto every listener merely to duplicate built-in measurement. If measuring a distinct business phase, pick a distinct name and scope to keep it separate from framework timers.

### 3.4. When the App Constructs Factories or Clients Manually

Application-defined beans can cause Boot auto-configuration to back off. In that case, do not assume Boot's customizers ran on your factory.

The example below is a **method inside a configuration class**, used when owning the producer factory explicitly. It is not a standalone program and does not belong in an experiment using auto-configured factories:

```java
import java.util.HashMap;
import java.util.Map;

import io.micrometer.core.instrument.MeterRegistry;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.StringSerializer;
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.MicrometerProducerListener;

@Bean
DefaultKafkaProducerFactory<String, String> producerFactory(MeterRegistry registry) {
    Map<String, Object> properties = new HashMap<>();
    properties.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, "127.0.0.1:9092");
    properties.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG, StringSerializer.class);
    properties.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, StringSerializer.class);

    var factory = new DefaultKafkaProducerFactory<String, String>(properties);
    factory.addListener(new MicrometerProducerListener<>(registry));
    return factory;
}
```

The address above is a lab broker; the snippet does not create a broker. Nor is it a complete configuration for authentication, transactions, or production operation. Consumer factories have the corresponding `MicrometerConsumerListener`.

If you already use a Boot-configured factory with a metrics listener attached, do not add a second registration path just because numbers are not visible yet. For raw `KafkaProducer`/`KafkaConsumer` outside Spring factories, manage binding and closing `KafkaClientMetrics` yourself; an object created with `new` does not automatically become Boot-monitored.

## 4. RabbitMQ: Java Client Metrics and Listener Metrics

### 4.1. Dependency and Configuration Conditions

For Spring Boot AMQP integration, use:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-actuator'
implementation 'org.springframework.boot:spring-boot-starter-amqp'
```

Starter AMQP brings in Spring Rabbit and the RabbitMQ Java client. Boot can configure the connection factory and `RabbitTemplate` from `spring.rabbitmq.*` properties. An existing template does not confirm a broker connection is open or messages were sent successfully. [AMQP integration in Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/messaging/amqp.html).

Boot supports instrumenting the RabbitMQ connection factory; client metrics use the `rabbitmq` prefix. Inspect the actual managed factory and active collectors/customizers, especially if the app creates factories manually or runs multiple factories. [RabbitMQ metrics in Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.supported.rabbitmq).

### 4.2. Recognizing Client Metrics

Common RabbitMQ Java client metrics include:

| Micrometer Name | Typical Type | Scope |
| --- | --- | --- |
| `rabbitmq.connections` | Gauge | Connections tracked by the client-side collector |
| `rabbitmq.channels` | Gauge | Channels tracked by the client-side collector |
| `rabbitmq.published` | Counter | Publish operations recorded by the collector |
| `rabbitmq.consumed` | Counter | Message deliveries recorded by the collector |
| `rabbitmq.acknowledged` | Counter | Acknowledgements recorded by the collector |
| `rabbitmq.rejected` | Counter | Rejections recorded by the collector |

The list and finer details depend on Java client version. `rabbitmq` is only a prefix of a meter family, not a single metric summarizing everything. [RabbitMQ Java client MicrometerMetricsCollector implementation](https://github.com/rabbitmq/rabbitmq-java-client/blob/main/src/main/java/com/rabbitmq/client/impl/MicrometerMetricsCollector.java).

Distinguish these meanings:

- A client-recorded publish does not prove the message routed to the intended queue or was processed by a consumer.
- Publisher confirms are a separate mechanism from consumer acknowledgements.
- Acknowledgement counters depend on ack mode and actual execution paths; do not assume every consume increments them one-to-one.
- Current connections/channels are gauges, not total connections ever created since application startup.

To conclude "the order completed," business evidence is needed. Library counters prove only the events defined and collected by that library.

### 4.3. Listener Timers and Limits of Client Data

In Spring AMQP's traditional timer mechanism, listener containers can register `spring.rabbitmq.listener`, with tags such as `listenerId`, `queue`, `result`, and `exception`. `MeterRegistry` and the `micrometerEnabled` setting are conditions to check. [Micrometer integration in Spring AMQP 3.1](https://docs.spring.io/spring-amqp/reference/3.1/amqp/receiving-messages/micrometer.html).

This timer measures listener invocations, not a direct count of messages still sitting in the queue. When you need ready messages, unacknowledged messages, node capacity, or cluster health, use proper RabbitMQ broker data. The `rabbitmq_prometheus` plugin is a broker-side monitoring source; that is a separate collection path from the application's Actuator endpoint. [Broker-side RabbitMQ monitoring](https://www.rabbitmq.com/docs/monitoring).

Example: a consumer receives a message and processes slowly. The consumed counter can rise while the queue still has backlog and unacknowledged messages stay high. Never infer an empty queue just because consumed is rising.

## 5. Observation Can Change Timer Creation Paths and Tag Sets

Micrometer Observation describes an observed operation. With suitable handlers, the same operation can produce metrics and tracing data. Metrics do not require configuring a full tracing system to work; conversely, having a metrics registry does not mean optional operations have Observation enabled.

In Boot 3.3 auto-configuration, the following properties enable Observation on the corresponding components:

```properties
spring.kafka.template.observation-enabled=true
spring.kafka.listener.observation-enabled=true

spring.rabbitmq.template.observation-enabled=true
spring.rabbitmq.listener.simple.observation-enabled=true
```

If using a Rabbit direct container instead of a simple container, check `spring.rabbitmq.listener.direct.observation-enabled`. Pick the matching container type; the simple setting does not automatically configure direct containers. [Boot 3.3 configuration properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html).

In Spring Kafka 3.2, enabling Observation on template/container switches timer creation to Observation instead of traditional Micrometer timers. Base names `spring.kafka.template` and `spring.kafka.listener` may still look similar, yet do not assume old tags remain identical. For batch listeners, check version-specific support before applying record-listener conclusions. [Spring Kafka 3.2 Monitoring and Observation](https://docs.spring.io/spring-kafka/reference/3.2/kafka/micrometer.html#micrometer-observation).

With Spring AMQP 3.1, Observation must likewise be enabled on the corresponding template/container. Observation timer names are typically `spring.rabbit.template` and `spring.rabbit.listener`, differing from the legacy name `spring.rabbitmq.listener`. That is why searching only for an old prefix can miss active metrics. [Spring AMQP 3.1 Observation](https://docs.spring.io/spring-amqp/reference/3.1/amqp/receiving-messages/micrometer-observation.html), [Rabbit observation names](https://docs.spring.io/spring-amqp/reference/appendix/micrometer.html).

New names can be accompanied by timers tracking in-flight operations with an `.active` suffix. Those are not error counts or messages queued on the broker. Always read meter type, description, and unit before naming charts.

Enabling Observation does not replace native metrics from the Kafka/RabbitMQ Java clients. One group reveals client-library activity; the other frames Spring-level operations. Both can coexist and answer different questions.

## 6. Experiment: Changing Dependencies While Keeping Inspection Code Identical

This experiment distinguishes three states: **library class present**, **integration bean present**, **meter registered**. No broker is needed to run the first two steps because the program creates no business listeners and sends no messages.

### 6.1. Baseline Project

Create a standalone demo project using JDK 21 and Gradle 8.5 or compatible. Minimal structure:

```text
integration-metrics-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/example/integrationmetrics/IntegrationMetricsApplication.java
    └── resources/application.properties
```

`settings.gradle`:

```groovy
rootProject.name = 'integration-metrics-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    // Kafka step: uncomment the matching line and restart.
    // implementation 'org.springframework.kafka:spring-kafka'

    // RabbitMQ step: add only when running the RabbitMQ experiment.
    // implementation 'org.springframework.boot:spring-boot-starter-amqp'
}
```

These are intentional dependency choices for the experiment, not a recommendation to add both messaging systems to every application. Let Boot's BOM manage library versions instead of manually mixing incompatible Micrometer and Spring Kafka/AMQP versions.

`application.properties`:

```properties
server.address=127.0.0.1
management.endpoints.web.exposure.include=health,metrics
```

This configuration serves a local machine experiment. Endpoint access in a secured application remains governed by the application's security setup.

### 6.2. Inspection Program

Save the exact content below to `IntegrationMetricsApplication.java` in the specified folder:

```java
package example.integrationmetrics;

import java.util.Arrays;
import java.util.List;

import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.util.ClassUtils;

@SpringBootApplication
public class IntegrationMetricsApplication {
    private static final List<String> PREFIXES = List.of(
            "kafka.", "rabbitmq.", "spring.kafka.",
            "spring.rabbit.", "spring.rabbitmq.", "spring.integration.");

    public static void main(String[] args) {
        SpringApplication.run(IntegrationMetricsApplication.class, args);
    }

    @Bean
    ApplicationRunner inspect(ApplicationContext context, MeterRegistry registry) {
        return args -> {
            printBeans(context, "kafka", "org.springframework.kafka.core.KafkaTemplate");
            printBeans(context, "rabbit", "org.springframework.amqp.rabbit.core.RabbitTemplate");

            List<String> names = registry.getMeters().stream()
                    .map(meter -> meter.getId().getName())
                    .filter(name -> PREFIXES.stream().anyMatch(name::startsWith))
                    .distinct()
                    .sorted()
                    .toList();
            System.out.println("DEMO integrationMeters=" + names);
        };
    }

    private static void printBeans(ApplicationContext context, String label,
            String className) {
        ClassLoader loader = IntegrationMetricsApplication.class.getClassLoader();
        boolean present = ClassUtils.isPresent(className, loader);
        String[] beans = present
                ? context.getBeanNamesForType(ClassUtils.resolveClassName(className, loader))
                : new String[0];
        Arrays.sort(beans);
        System.out.println("DEMO " + label + ".classpath=" + present
                + " beans=" + Arrays.toString(beans));
    }
}
```

The program only inspects existing state without creating fake Kafka/RabbitMQ counters to simulate integration. Filtering by `PREFIXES` is a lesson-oriented list, not an exhaustive detector for every technology possible in an application.

Run using the Gradle wrapper if present:

```powershell
.\gradlew.bat bootRun
```

Or using a compatible installed Gradle:

```powershell
gradle bootRun
```

The first run may need to download plugins and libraries from dependency repositories.

### 6.3. Baseline Run: Without Kafka/AMQP

With the baseline project itself, stdout lines prefixed with `DEMO` are:

```text
DEMO kafka.classpath=false beans=[]
DEMO rabbit.classpath=false beans=[]
DEMO integrationMeters=[]
```

The application still has other metrics such as JVM or startup times. `integrationMeters=[]` only says no names matched the filtered prefixes; it does not say the registry is empty.

### 6.4. Adding Only Spring Kafka

Uncomment the `spring-kafka` dependency, stop the app, and restart. Keep the Java code unchanged and leave Observation disabled for this comparison. With no other customizations and only default beans, expected `DEMO` stdout is:

```text
DEMO kafka.classpath=true beans=[kafkaTemplate]
DEMO rabbit.classpath=false beans=[]
DEMO integrationMeters=[spring.kafka.template]
```

The template timer already exists, even though the program has neither sent a message nor run a consumer. Read the meter to check its value:

```powershell
curl.exe "http://localhost:8080/actuator/metrics/spring.kafka.template"
```

In this no-send run, the timer's `COUNT` remains 0. A timer being registered early is concrete proof that **a meter existing** and **an operation occurring** are two separate things.

Having no `kafka.producer.*`/`kafka.consumer.*` groups yet in that state makes sense: actual clients have not been created. Conversely, if another project adds listeners or sending code, clients may be created before the runner prints the list; do not expect this exact stdout from an active project.

### 6.5. Trying With RabbitMQ and Real Traffic

To compare RabbitMQ separately, remove Spring Kafka from the experiment, add the AMQP starter, and restart. Inspect `RabbitTemplate`, actual beans, and registered `rabbitmq.*` meters. Do not assume RabbitMQ's meter list or counts behave identically to Kafka's; its collector can register some meters before connections or messages exist.

When moving on to observe real traffic, you need a reachable lab broker and matching connection settings. The properties below are sample configuration and do not start an external broker or data:

```properties
# Use Kafka group only during the Kafka experiment.
spring.kafka.bootstrap-servers=127.0.0.1:9092
spring.kafka.producer.key-serializer=org.apache.kafka.common.serialization.StringSerializer
spring.kafka.producer.value-serializer=org.apache.kafka.common.serialization.StringSerializer
spring.kafka.consumer.group-id=metrics-demo
spring.kafka.consumer.key-deserializer=org.apache.kafka.common.serialization.StringDeserializer
spring.kafka.consumer.value-deserializer=org.apache.kafka.common.serialization.StringDeserializer

# Use RabbitMQ group only during the RabbitMQ experiment.
spring.rabbitmq.host=127.0.0.1
spring.rabbitmq.port=5672
```

With Kafka, prepare a test topic and send/receive via Spring-managed `KafkaTemplate`/listeners. With RabbitMQ, prepare a queue, exchange/binding, and permissions, then send/receive via the corresponding components. How Boot configures Kafka components is described in [Kafka 3.3 integration docs](https://docs.spring.io/spring-boot/3.3/reference/messaging/kafka.html).

Record meter names before and after operations, then compare both counters and timers. Do not expect one fixed total across every environment: retries, errors, rebalances, and batch listener handling can make operation counts differ from initial message counts.

The example's runner prints only a **startup snapshot**. After generating activity, use the metrics endpoint to inspect updated state; prior stdout does not refresh as the registry updates.

If you only want the stdout check without opening HTTP, run:

```powershell
.\gradlew.bat bootRun --args="--spring.main.web-application-type=none"
```

In that case do not run `curl` commands against this app.

## 7. Finding Metrics From Runtime Evidence

### 7.1. Checking Actual Dependencies

For Gradle projects, inspect the `runtimeClasspath` tree rather than looking only at declarations in `build.gradle`:

```powershell
.\gradlew.bat dependencies --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency spring-kafka --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency kafka-clients --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency spring-rabbit --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency amqp-client --configuration runtimeClasspath
```

In multi-module builds, prepend the specific project path to the task name. Check both direct and transitive dependencies: another starter can bring a library in without the module declaring that library directly. Also distinguish test-only dependencies from runtime dependencies of the running application.

If a library is on the classpath yet beans do not appear, check auto-configuration conditions: excluded configurations, user beans causing auto-config to back off, active profiles, or missing prerequisite classes/beans. Run with `--debug` to view the condition evaluation report; do not guess by blindly adding dependencies one by one hoping metrics appear.

### 7.2. List Names First, Then Query Individual Meters

In PowerShell:

```powershell
$inventory = Invoke-RestMethod "http://localhost:8080/actuator/metrics"
$inventory.names |
    Where-Object { $_ -match '^(kafka\.|rabbitmq\.|spring\.(kafka|rabbitmq|rabbit|integration)\.)' } |
    Sort-Object
```

Once an actual name appears, query details. For example:

```powershell
curl.exe "http://localhost:8080/actuator/metrics/spring.kafka.template"
curl.exe "http://localhost:8080/actuator/metrics/rabbitmq.connections"
```

Only run commands for meters that exist. Read `description`, `baseUnit`, `measurements`, and `availableTags`, then use `tag=KEY:VALUE` to narrow down a bean/client or outcome. Unfiltered values may aggregate multiple series sharing the same name. [Actuator metrics API](https://docs.spring.io/spring-boot/api/rest/actuator/metrics.html).

The following example **applies only to the traditional Kafka timer mechanism**, after confirming `name` and `result` tags in the response:

```powershell
curl.exe "http://localhost:8080/actuator/metrics/spring.kafka.template?tag=name:kafkaTemplate&tag=result:success"
```

Do not apply old filters to Observation and conclude the app lost its metrics. Equivalent tags can be renamed by observation conventions or across versions.

### 7.3. Keep the Distinction Among Three States Clear

| Observation Result | What Can Be Concluded | What Cannot Be Concluded Yet |
| --- | --- | --- |
| Meter name absent | That meter was not seen in this registry at read time | Cannot conclude its value is 0 |
| Meter present, counter/count is 0 | Series exists, yet no matching event recorded in its scope | Does not prove the whole broker has no activity |
| Meter rises after operation | That measurement path recorded activity | Does not prove end-to-end business success across services |
| Endpoint unreachable | There is an endpoint access or application issue | Unknown whether meters exist inside the registry |

When querying across multiple instances, verify which instance actually handles the traffic. Sending a request to instance one and reading metrics on instance two can create the illusion that "the counter isn't moving" even though both work properly.

## 8. Other Integration Libraries: Apply the Same Reasoning

You do not need to memorize the entire metric catalog. Know which library and component leads to which name group:

| Dependency/Component in Application | Name Group to Look For | Conditions to Cross-Check |
| --- | --- | --- |
| Spring Integration | `spring.integration.*` | Real channels/handlers/sources and registry; traditional vs. Observation |
| Spring Data repository | `spring.data.repository.invocations` | Spring-created repository invoked; matching metrics config |
| MongoDB driver via Boot config | `mongodb.driver.commands`, `mongodb.driver.pool.*` | MongoClient has metrics listener attached, matching operations/connections |
| JPA/Hibernate | `hibernate.*` | `hibernate-micrometer` present and Hibernate statistics enabled; JPA starter alone is not enough |
| Spring Batch | Job/step meters such as `spring.batch.job`, `spring.batch.step` | Batch infrastructure present and job/step executed; check version and Observation |

This is an orientation map, not a list of dependencies to add to every module. Boot documents MongoDB, repository, and Hibernate integrations and their conditions in [Boot 3.3 supported metrics catalog](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).

With Spring Integration 6.3, for instance, `spring.integration.send` timers and `spring.integration.receive` counters attach to specific component types, while gauges `spring.integration.channels`, `handlers`, and `sources` count components in the app. Those gauges are neither Kafka partitions nor RabbitMQ broker queues. When Observation is enabled, verify names and conventions along that path. [Spring Integration 6.3 metrics](https://docs.spring.io/spring-integration/reference/6.3/metrics.html).

A single message can pass through a Kafka client, a Spring Kafka listener, and then a Spring Integration handler. It then generates data across multiple layers. Summing counters across all layers into a "total messages" figure would double-count events with different meanings.

## 9. Reading Exported Data With Exact Names and Types

To use the Prometheus endpoint in the demo project, add the registry and expose the endpoint:

```groovy
runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
```

```properties
management.endpoints.web.exposure.include=health,metrics,prometheus
```

The name for querying `/actuator/metrics/{name}` is the Micrometer name, such as `spring.kafka.listener`. In Prometheus output, timers typically become series like `spring_kafka_listener_seconds_count` and `spring_kafka_listener_seconds_sum`. Counter `rabbitmq.published` typically becomes `rabbitmq_published_total`. Inspect actual output because registries, conventions, and versions affect names and labels.

```powershell
curl.exe "http://localhost:8080/actuator/prometheus" |
    Select-String "kafka_|rabbitmq_|spring_kafka_|spring_rabbit"
```

PromQL example for the rate of publish operations recorded by the RabbitMQ Java client once that name is confirmed present:

```promql
sum by (job) (rate(rabbitmq_published_total[5m]))
```

This is the client-side publish event rate scraped across those jobs. It is not queue length and does not prove individual messages were processed successfully.

For the Kafka listener timer, average duration in an observation window can be calculated as total duration increase divided by count increase, with identical filters/grouping:

```promql
sum by (job) (rate(spring_kafka_listener_seconds_sum[5m]))
/
sum by (job) (rate(spring_kafka_listener_seconds_count[5m]))
```

If there are no executions in the window, the denominator can be 0 and the ratio has no useful value. This is neither a p95/p99 calculation nor end-to-end latency across the whole system.

For connection/channel gauges or lag, read values with current-state semantics; do not apply `rate` just because a number appears on a dashboard. For measurements already computed as rates by the Kafka client, do not take `rate` again as if they were cumulative counters. Before writing queries, check meter type and unit from the actual source.

## 10. Diagnosing Missing Metrics Link by Link

| Symptom | Next Check |
| --- | --- |
| Actuator present, yet no Kafka names appear | Check Spring Kafka on runtime classpath and actual beans; does the app really use Kafka? |
| `KafkaTemplate` and `spring.kafka.template` exist, yet no `kafka.producer.*` | Has a producer been created yet, or did the app only initialize the template? |
| Sent via Kafka, yet native metrics missing | Identify which factory creates clients and which metrics listener is attached; check for manually created raw clients |
| Consumer metrics missing | Check whether listener/container is running, client created, and partitions assigned; producer metrics do not substitute for consumer metrics |
| RabbitMQ meter names exist, yet connection count is 0 | Check whether the app has opened a connection yet; collector can exist before the first connection |
| RabbitMQ shows consumed, yet backlog is unknown | Switch to broker-side queue metrics; client counters do not directly report queue depth |
| Enabled Observation and old-tag queries return nothing | Re-list meter names and `availableTags`; confirm conventions and listener type for your version |
| Dependency declared, yet bean missing | Check actual versions, dependency scope, profiles, exclusions, and auto-configuration condition report |
| Meter exists in registry, yet missing in Prometheus | Check registry export, endpoint exposure, meter filters, and exact scrape target |
| Metrics seen with debug, yet count stays unchanged | Debug shows configuration; operations must still flow through the instrumented component |

Meter filter properties can also suppress an entire group. For example, `management.metrics.enable.kafka=false` targets names starting with `kafka`; the `spring.kafka.*` group has a different prefix and must be considered separately. Do not use the presence of one group to conclude the other was never disabled.

Tag customization should use bounded values such as app name, environment, or stable listener name. Never attach payloads, message IDs, or per-message order IDs to metrics: every new tag combination spawns extra time series and makes storage/comparison costly.

## 11. Self-Verification Practice

1. **Baseline project:** run the example without Spring Kafka/AMQP. Explain why JVM metrics still appear while the filtered integration list is empty.
2. **Add only Spring Kafka:** verify three distinct pieces of evidence: runtime dependency, `KafkaTemplate` bean, and `COUNT` of `spring.kafka.template` before sending.
3. **Generate activity on a lab broker:** capture meter lists before/after sending and before/after starting a consumer. Classify each new name under client, Spring timer, or broker data.
4. **Switch measurement mechanism deliberately:** enable Observation for the matching template/listener, restart, and compare names/tags. Do not use a dashboard with stale filters as sole proof that data vanished.
5. **Analyze a RabbitMQ scenario:** consumed rises while the queue still holds many unacknowledged messages. Explain why that is not contradictory and which broker source verifies it.
6. **Inspect another library:** pick a dependency actually used by your app, trace bean/resource/binder first, and only then look up its meter group. Do not add libraries merely to lengthen the metrics list.

After these experiments, for every chart you should be able to point to **the measured component, the library/version generating the metric, the registration path, the meter type, distinguishing tags, and the operation that changes it**. That foundation lets you read integrated metrics accurately whenever dependencies or application architecture change.
