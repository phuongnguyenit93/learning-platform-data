# Verifying applied configuration

An `application.yml` file may contain the exact values you expect, yet the application still connects to the wrong broker, uses the wrong consumer group, or fails to apply serializers as intended. The root cause often lies in the active profile, environment variables overriding configuration, properties loaded from another source, or a manually declared Kafka bean replacing Spring Boot auto-configuration.

For a Spring Kafka application, configuration must be verified across multiple layers: values loaded into the Spring Environment, properties bound into Boot's Kafka configuration, the actual configuration used to create producers/consumers, and the actual state of brokers/topics. Checking layer by layer pinpoints exactly where configuration went wrong.

## 1. Distinguishing configuration layers

There is no single screen showing that everything in Kafka is configured correctly. Distinguish these four layers:

| Layer | What to verify | Where to observe |
| --- | --- | --- |
| Spring Environment | Which property wins after merging YAML files, profiles, environment variables, system properties, and command-line arguments | Actuator `env`, startup logs, debugger |
| Spring Boot binding | Values bound into `KafkaProperties` and auto-configuration | Actuator `configprops`, beans in ApplicationContext |
| Kafka client runtime | Actual configuration of created producers, consumers, and admins | Dependency/bean inspection, Kafka client logs, send/receive tests |
| Kafka broker/topic | Which brokers are responding, whether topics exist, partitions, and active topic settings | Kafka CLI, `AdminClient`, broker logs |

For example, `spring.kafka.bootstrap-servers=localhost:9092` in the Environment only shows the application loaded that property. It does not prove `KafkaTemplate` is using that broker: a manually declared `ProducerFactory` may use a different configuration. Likewise, a producer connecting to a broker does not prove the topic has the required retention or partition count.

## 2. Checking profiles and configuration sources

Spring Boot can load configuration from multiple sources. Sources have different precedences; higher-precedence sources can override values in `application.yml`. Common sources include:

- `application.yml` or `application.properties` packaged inside the application.
- Profile-specific files, such as `application-local.yml`, `application-test.yml`, or `application-prod.yml`.
- External configuration files outside the JAR, specified config directories, or imported configs.
- Operating system / container environment variables.
- Java system properties and command-line arguments at startup.
- Values supplied by test frameworks during testing.

First, confirm the active profile. It can be passed at launch:

```bash
java -jar messaging-service.jar --spring.profiles.active=local
```

Or set as an environment variable:

```bash
SPRING_PROFILES_ACTIVE=local
```

In an IDE, check the Run Configuration because profiles can be passed via VM options, program arguments, or environment variables. When running in Docker Compose or Kubernetes, inspect container environment variables and mounted ConfigMaps/Secrets.

Example profile-based configuration:

```yaml
# application.yml
spring:
  kafka:
    consumer:
      group-id: order-service
      auto-offset-reset: earliest
```

```yaml
# application-local.yml
spring:
  kafka:
    bootstrap-servers: localhost:9092
```

```yaml
# application-docker.yml
spring:
  kafka:
    bootstrap-servers: broker:19092
```

If the application is running with the `docker` profile, `localhost:9092` in the local file is not the chosen connection address. Verify the profile and property sources before changing code.

Environment variables commonly used to override Spring Kafka configuration:

| Property | Environment variable |
| --- | --- |
| `spring.kafka.bootstrap-servers` | `SPRING_KAFKA_BOOTSTRAP_SERVERS` |
| `spring.kafka.consumer.group-id` | `SPRING_KAFKA_CONSUMER_GROUP_ID` |
| `spring.kafka.consumer.auto-offset-reset` | `SPRING_KAFKA_CONSUMER_AUTO_OFFSET_RESET` |
| `spring.kafka.producer.acks` | `SPRING_KAFKA_PRODUCER_ACKS` |

PowerShell example:

```powershell
$env:SPRING_KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"
$env:SPRING_PROFILES_ACTIVE = "local"
.\mvnw.cmd spring-boot:run
```

When a value in YAML differs from an environment variable, inspect the active property sources. Do not keep editing YAML repeatedly if the value is being overridden from Run Configuration or the runtime environment.

## 3. Inspecting values in Spring Environment with Actuator

Spring Boot Actuator provides the `env` endpoint to view property sources and property origins. The `configprops` endpoint shows how `@ConfigurationProperties` beans were bound. These are two useful inspection points when suspecting configuration was not loaded or was overridden.

Add Actuator if the project does not yet have the dependency:

Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

Gradle:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-actuator'
```

In a local environment, diagnostic endpoints can be exposed:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,env,configprops
```

After the application starts, inspect:

```text
GET http://localhost:8080/actuator/env/spring.kafka.bootstrap-servers
GET http://localhost:8080/actuator/configprops
```

The `env` endpoint helps determine which source a property comes from and which value wins. The `configprops` endpoint verifies data bound into Boot's configuration beans. Bean names and response structure may vary by Spring Boot version.

Actuator has masking mechanisms for sensitive values, but you should not rely on default masking to expose configuration endpoints to the network. `env` and `configprops` can reveal hostnames, system layout, or internal config values. Expose them only in protected diagnostic environments, restrict access, and keep sensitive-value visibility in a safe mode. Never share raw endpoint responses without stripping secrets first.

If you only need to check bound configuration, look at `configprops`. If you need to locate which property source overrode a value, inspect `env` and cross-check profiles, environment variables, system properties, and launch arguments.

## 4. Inspecting bound Spring Kafka configuration

Spring Boot binds the `spring.kafka.*` group into `KafkaProperties`. Commonly used groups include:

| Property group | Contents |
| --- | --- |
| `spring.kafka.bootstrap-servers` | Bootstrap broker addresses |
| `spring.kafka.client-id` | Default client ID |
| `spring.kafka.admin.*` | Kafka admin configuration |
| `spring.kafka.producer.*` | Serializers, acks, retries, batching, and producer properties |
| `spring.kafka.consumer.*` | Group ID, deserializers, offset reset, and consumer properties |
| `spring.kafka.listener.*` | Boot-level listener container configuration |
| `spring.kafka.properties.*` | Shared Kafka client properties |

Example configuration:

```yaml
spring:
  kafka:
    bootstrap-servers:
      - localhost:9092
    client-id: order-service
    producer:
      acks: all
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
    consumer:
      group-id: order-projection
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        "[spring.json.trusted.packages]": com.example.messaging.event
```

When using the JSON deserializer, configure type mapping/trusted packages matching your data contract and Spring Kafka version. Do not widen trusted packages beyond necessity just to avoid deserialization errors.

You can inspect the `KafkaProperties` bean in a debugger or via Actuator `configprops`. However, bound values are not necessarily the final Kafka client configuration. Spring Boot further builds configuration maps for producers, consumers, and admins; customizers or application-declared beans can modify them afterward.

## 5. Verifying auto-configuration and actual beans

Spring Boot auto-configures Kafka components when auto-configuration conditions match. If the application declares its own beans, some default configurations may be replaced or auto-configuration will back off.

Important beans to inspect in ApplicationContext include:

- `KafkaTemplate`: the object services typically inject to send records.
- `ProducerFactory`: creates Kafka producers and supplies producer configuration.
- `ConsumerFactory`: creates Kafka consumers for listener containers.
- `ConcurrentKafkaListenerContainerFactory`: factory creating listener containers.
- `KafkaAdmin`: performs topic and broker administration operations.

If the project has multiple beans of the same type, check `@Primary`, `@Qualifier`, bean names, and the parameters injected into services/listeners. A `KafkaTemplate` could be built from a different `ProducerFactory` than the one you are inspecting.

You can enable the condition evaluation report when running the application:

```bash
java -jar messaging-service.jar --debug
```

The report shows which auto-configurations were applied or skipped due to missing classes, properties, or existing beans. It does not print the full effective Kafka client config, but it helps explain why Boot did not create an expected bean.

When deeper inspection is needed, set a breakpoint where `ProducerFactory`/`ConsumerFactory` is created, or inspect the beans in a debugger. If using Spring Kafka's default factories, you can inspect configuration properties on the respective implementation; avoid relying on internal APIs or casting an interface to an implementation if the application might swap factories.

## 6. Distinguishing client configuration from broker and topic configuration

A common diagnostic mistake is looking for `retention.ms` in `application.yml` and assuming that is the value the broker uses. Retention is a topic/broker setting; it is not a normal producer or consumer property.

| Example | Where it applies | How to verify |
| --- | --- | --- |
| `bootstrap.servers` | Kafka client | Actuator/configprops, client config, and live connection |
| `group.id` | Kafka consumer | Consumer config, `@KafkaListener`, consumer group CLI |
| `key.serializer` | Kafka producer | Producer config and send tests |
| `key.deserializer` | Kafka consumer | Consumer config and receive tests |
| `retention.ms` | Topic | Kafka AdminClient or `kafka-configs.sh` |
| `cleanup.policy` | Topic | Kafka AdminClient or `kafka-configs.sh` |
| `num.partitions` | Topic default at topic creation | `kafka-topics.sh --describe` or AdminClient |
| `log.retention.hours` | Broker default | Broker config via administrative tools |

Spring Kafka can create topics via `NewTopic` beans, yet once a topic exists, you must read the actual configuration from the broker. Declaring a bean in source code does not by itself prove the broker applied that configuration if the topic already existed beforehand or admin permissions were insufficient.

## 7. Checking brokers and topics with Kafka CLI

Check broker responsiveness and API versions:

```bash
kafka-broker-api-versions.sh --bootstrap-server localhost:9092
```

List topics:

```bash
kafka-topics.sh --bootstrap-server localhost:9092 --list
```

Inspect topic partitions, leaders, and replicas:

```bash
kafka-topics.sh --bootstrap-server localhost:9092 --describe --topic orders.events
```

Inspect topic configuration:

```bash
kafka-configs.sh --bootstrap-server localhost:9092 \
  --entity-type topics --entity-name orders.events --describe
```

Inspect consumer group progress:

```bash
kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
  --describe --group order-projection
```

When reading results, verify you are checking the right cluster and topic. A topic may exist locally yet be absent in staging; the same topic name on two clusters does not mean they share data or configuration.

The topic `--describe` command confirms partition count, leaders, and replicas. `kafka-configs.sh` reveals topic settings applied by the broker. The consumer group command shows current offset, log end offset, and lag; low lag alone does not prove the listener processed business logic properly, though it is an important operational signal.

## 8. Checking with Kafka AdminClient inside the application

When checking brokers from code or writing an internal diagnostic endpoint, you can use `AdminClient`. The following example creates a client with bootstrap servers and reads cluster metadata:

```java
import java.util.HashMap;
import java.util.Map;

import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.AdminClientConfig;

public class KafkaClusterInspector {

    public void inspect(String bootstrapServers) throws Exception {
        Map<String, Object> properties = new HashMap<>();
        properties.put(
                AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG,
                bootstrapServers);

        try (AdminClient admin = AdminClient.create(properties)) {
            var description = admin.describeCluster();
            System.out.println("Cluster ID: " + description.clusterId().get());
            System.out.println("Nodes: " + description.nodes().get());
        }
    }
}
```

In environments with SASL or TLS, the map passed to AdminClient must include the corresponding security configuration. Do not create a diagnostic client with `bootstrap.servers` alone if the broker requires authentication.

To read topic configuration:

```java
import java.util.List;

import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.Config;
import org.apache.kafka.clients.admin.ConfigEntry;
import org.apache.kafka.common.config.ConfigResource;

public void inspectTopicConfig(AdminClient admin, String topicName)
        throws Exception {
    ConfigResource resource = new ConfigResource(
            ConfigResource.Type.TOPIC, topicName);

    Config config = admin.describeConfigs(List.of(resource))
            .values()
            .get(resource)
            .get();

    for (ConfigEntry entry : config.entries()) {
        String value = entry.isSensitive() ? "[hidden]" : entry.value();
        System.out.printf("%s=%s (source=%s)%n",
                entry.name(), value, entry.source());
    }
}
```

`ConfigEntry.source()` helps distinguish values set directly on the topic from values inherited from default settings. The snippet only illustrates reading topic config; real applications must handle timeouts, authorization exceptions, and connection errors. Never log sensitive broker values.

## 9. Verifying producers and consumers actually work

Configuration that looks right can still fail when creating clients or when the broker rejects connections. Perform an end-to-end check:

1. Confirm the broker responds via the configured bootstrap address.
2. Confirm the topic exists with the expected partition count.
3. Send a test record through `KafkaTemplate` and wait for the future to complete.
4. Confirm returned record metadata has the right topic and a valid partition.
5. Receive the record in the expected consumer group and verify deserialized key/value.
6. Check consumer group offset/lag to confirm the consumer advanced.

Example of testing a producer in an integration test with Embedded Kafka:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.kafka.support.SendResult;

@SpringBootTest
@EmbeddedKafka(
        partitions = 1,
        topics = "configuration-check",
        bootstrapServersProperty = "spring.kafka.bootstrap-servers")
class KafkaConnectionIntegrationTest {

    @Autowired
    private KafkaTemplate<String, String> kafkaTemplate;

    @Test
    void producerUsesConfiguredBroker() throws Exception {
        SendResult<String, String> result = kafkaTemplate
                .send("configuration-check", "probe", "configuration-ok")
                .get(10, TimeUnit.SECONDS);

        assertThat(result.getRecordMetadata().topic())
                .isEqualTo("configuration-check");
        assertThat(result.getRecordMetadata().partition())
                .isGreaterThanOrEqualTo(0);
    }
}
```

The test above verifies that the Spring context creates `KafkaTemplate` and the producer sends successfully to the embedded broker. It does not test consumer listeners or an external broker environment. To verify listeners, add a test receiving the record and awaiting assertions under the actual consumer group; to verify production settings, test in an environment with equivalent configuration.

## 10. Using logs to diagnose connections

When you need to see what errors the Kafka client is encountering, temporarily raise log levels:

```yaml
logging:
  level:
    org.springframework.kafka: DEBUG
    org.apache.kafka.clients.NetworkClient: INFO
```

These logs help identify DNS errors, connection refused, timeouts, authentication failures, metadata issues, or serialization/deserialization errors. Enable verbose logging only during diagnostics and revert to appropriate levels afterward. Avoid enabling TRACE or logging the entire client configuration in production because logs may contain sensitive data or generate excessive log volume.

Several common indicators:

| Log / symptom | What to check |
| --- | --- |
| `Connection to node ... could not be established` | Bootstrap servers, advertised listeners, DNS, port mappings, and firewalls |
| `Topic ... not present in metadata` | Topic name, access permissions, auto-create policy, and target cluster |
| `SaslAuthenticationException` | SASL mechanism, username/password, JAAS, or loaded secrets |
| `SSLHandshakeException` | Truststore, keystore, hostname verification, and certificates |
| `SerializationException` | Serializers/deserializers and payload contract |
| Consumer receives no records | Group ID, offsets, partition assignment, subscription, and consumer lag |

## 11. Checklist when configuration does not take effect as expected

Before modifying code, check in order:

- [ ] Is the active profile right for the environment?
- [ ] Are environment variables, JVM options, or command-line arguments overriding YAML?
- [ ] Does `spring.kafka.bootstrap-servers` after binding have the right host and port?
- [ ] Is the application running on the host or in a container; does the listener match the network location?
- [ ] Which `ProducerFactory` is `KafkaTemplate` using?
- [ ] Which `ConsumerFactory`/container factory is the listener container using?
- [ ] Is a custom-declared bean causing Boot auto-configuration to back off?
- [ ] Do serializers/deserializers match data types and the event schema?
- [ ] Are the actual broker, topic, partitions, and topic settings correct?
- [ ] Is the consumer group assigned partitions and advancing offsets?
- [ ] Are there authentication, TLS, ACL, DNS, or firewall errors?
- [ ] Does an integration test reproduce the running configuration?

Never paste full Actuator output, Kafka client configs, or environment variables into public tickets or chats. Mask passwords, tokens, JAAS configs, private keys, truststore passwords, and sensitive internal addresses before sharing.

## 12. Conclusion

To know whether Spring Kafka configuration has been applied, verify from property sources to beans and the Kafka client, then cross-check against the real broker and topic. Actuator `env` identifies property origins and winning values; `configprops` shows bound configuration; condition reports and bean inspection reveal overridden auto-configuration; Kafka CLI or AdminClient verifies the cluster and topics; integration tests prove producers and consumers can actually communicate.

Always distinguish client configuration from broker/topic configuration, verify the right profile and listener addresses for where the application runs, and protect credentials in logs and diagnostic endpoints. When inspected layer by layer, misconfiguration causes become easy to locate and fix in the right place.

## References

- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot Actuator — Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot — Apache Kafka Support](https://docs.spring.io/spring-boot/reference/messaging/kafka.html)
- [Spring Kafka — Reference](https://docs.spring.io/spring-kafka/reference/)
- [Apache Kafka — Admin API](https://kafka.apache.org/documentation/#adminapi)
