# Configuration by profiles and environment variables

A Spring Kafka application typically runs across multiple environments: developer machines, integration environments, staging, and production. Each environment may use different Kafka clusters, broker addresses, consumer groups, security mechanisms, and operational limits. Putting these values directly into source code or hardcoding them inside a single configuration file makes deployments prone to environment mix-ups and makes protecting sensitive information difficult.

Spring Boot supports **externalized configuration**: the application reads configuration from YAML/properties files, environment variables, command-line arguments, and external configuration sources. Combining profiles with environment variables lets you use the same artifact across multiple environments while still changing Kafka connection settings.

## 1. Distinguishing profiles and environment variables

These two mechanisms solve two different needs:

- **Profiles** select a group of configurations according to the runtime purpose, such as `local`, `dev`, `staging`, `prod`, or `test`.
- **Environment variables** pass specific values from the deployment environment into the application, such as Kafka hostnames, consumer groups, or authentication credentials.

Profiles normally decide *which group of configurations is loaded*. Environment variables supply *the values of those configurations* at runtime.

For example, the same `prod` profile might run on two different Kubernetes clusters. Both use production settings and SASL_SSL, yet `KAFKA_BOOTSTRAP_SERVERS` and credentials are supplied differently by each deployment environment.

Do not create a separate configuration file per host if only hostnames or passwords differ. Keep a shared configuration structure and externalize values that vary by environment.

## 2. Spring Boot configuration file structure

Spring Boot automatically loads configuration files by naming convention. A common layout:

```text
src/main/resources/
├── application.yml
├── application-local.yml
├── application-dev.yml
├── application-staging.yml
└── application-prod.yml
```

- `application.yml` holds shared settings and safe defaults for development.
- `application-local.yml` holds settings for running on a local machine.
- `application-dev.yml` holds differences for the development environment.
- `application-staging.yml` and `application-prod.yml` hold settings for their respective environments.

When the `dev` profile is active, Spring Boot loads the shared configuration along with the profile-specific configuration. Values in profile-specific files can override shared values with the same key.

### Shared configuration: application.yml

Example of a basic Spring Kafka configuration:

```yaml
spring:
  application:
    name: spring-kafka-messaging

  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}

    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      acks: all

    consumer:
      group-id: ${KAFKA_CONSUMER_GROUP_ID:order-service}
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.trusted.packages: com.example.messaging.event
```

Values in the example:

- `bootstrap-servers` is the list of broker addresses the Kafka client uses to initiate connections and discover the cluster.
- The producer uses serializers matching the outgoing key and payload types.
- The consumer uses deserializers matching the record format.
- `group-id` identifies the consumer group; instances processing the same business stream usually share the same group ID.
- `auto-offset-reset` applies only when the group has no valid offset yet or the current offset no longer exists. It does not automatically reset offsets of a group that already has valid offsets.

The placeholder `${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}` means use the environment variable if present, otherwise fall back to `localhost:9092`. For critical production settings, you can omit the default value so the application fails immediately when a required variable is missing.

The package name in `spring.json.trusted.packages` is only an example. Restrict it to packages containing events that the application genuinely trusts; do not broaden the list arbitrarily.

## 3. Creating dedicated configurations per profile

### Local: application-local.yml

Developer machines usually connect to Kafka running via Docker Compose or a local installation:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092

    consumer:
      group-id: order-service-local
      auto-offset-reset: earliest

logging:
  level:
    org.springframework.kafka: INFO
```

A dedicated group ID can be used locally so test data does not alter the reading progress of development or production consumer groups.

### Development: application-dev.yml

Development environments often use a shared Kafka cluster inside an internal network:

```yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS}
    consumer:
      group-id: order-service-dev
```

Here, no default value is set for `KAFKA_BOOTSTRAP_SERVERS`. If the environment does not supply this variable, the application cannot resolve the placeholder and startup fails fast. This catches missing configuration instead of accidentally connecting to an unintended default broker.

### Production: application-prod.yml

Production typically requires TLS or SASL depending on the Kafka cluster's security policy:

```yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS}

    properties:
      security.protocol: SASL_SSL
      sasl.mechanism: PLAIN
      sasl.jaas.config: ${KAFKA_SASL_JAAS_CONFIG}

    producer:
      acks: all

    consumer:
      group-id: ${KAFKA_CONSUMER_GROUP_ID}
```

`KAFKA_SASL_JAAS_CONFIG` holds the JAAS configuration supplied by the deployment platform or secret manager. Never commit real values to Git, never print them to logs, and never include secrets in documentation examples or screenshots.

The configuration above only illustrates SASL_SSL with the PLAIN mechanism. The actual authentication mechanism must match the broker. If the cluster uses SCRAM, OAuth, or TLS client certificates, configure the corresponding mechanism, callback handler, and certificates.

If using a truststore or keystore, Spring Boot provides properties under `spring.kafka.ssl.*`, such as `trust-store-location`, `trust-store-password`, `key-store-location`, and `key-store-password`. Certificate file paths are typically mounted into containers from securely managed secrets or volumes.

## 4. Activating profiles

There are several ways to activate a profile. Choose the one fitting the application's runtime environment.

### Command-line arguments

```bash
java -jar messaging-service.jar --spring.profiles.active=dev
```

### Environment variables

On Linux or macOS:

```bash
export SPRING_PROFILES_ACTIVE=dev
java -jar messaging-service.jar
```

On PowerShell:

```powershell
$env:SPRING_PROFILES_ACTIVE = "dev"
java -jar messaging-service.jar
```

### In the IDE

You can set the environment variable `SPRING_PROFILES_ACTIVE=local` in the Run Configuration. When running the application, Spring Boot loads `application-local.yml` alongside the shared configuration.

Do not hardcode `spring.profiles.active` inside a profile-specific file such as `application-prod.yml`. Profiles should be selected from a configuration source independent of the profile being chosen, such as environment variables, command-line arguments, or deployment configuration.

### Activating multiple profiles

Spring Boot can run multiple profiles simultaneously, for example:

```bash
java -jar messaging-service.jar --spring.profiles.active=prod,metrics
```

This is useful when separating configuration by environment and by functional concern. However, if multiple profiles define the same key, clearly establish precedence and avoid unpredictable combinations. For simpler setups, a single environment profile is usually easier to operate.

## 5. Mapping Spring properties to environment variables

Spring Boot supports relaxed binding. The standard rule for converting a property name to an environment variable is:

1. Replace dots (`.`) with underscores (`_`).
2. Remove hyphens (`-`).
3. Convert everything to uppercase.

Example:

| Spring property | Environment variable |
|---|---|
| `spring.profiles.active` | `SPRING_PROFILES_ACTIVE` |
| `spring.kafka.bootstrap-servers` | `SPRING_KAFKA_BOOTSTRAP_SERVERS` |
| `spring.kafka.consumer.group-id` | `SPRING_KAFKA_CONSUMER_GROUP_ID` |
| `spring.kafka.producer.acks` | `SPRING_KAFKA_PRODUCER_ACKS` |
| `spring.kafka.properties.security.protocol` | `SPRING_KAFKA_PROPERTIES_SECURITY_PROTOCOL` |

For properties containing hyphens, the hyphens are stripped when forming the environment variable name. Thus, `group-id` becomes `GROUP_ID`, not `GROUP-ID`.

Example environment configuration:

```text
SPRING_PROFILES_ACTIVE=prod
SPRING_KAFKA_BOOTSTRAP_SERVERS=kafka-1.example.internal:9093,kafka-2.example.internal:9093
SPRING_KAFKA_CONSUMER_GROUP_ID=order-service
```

When using a custom placeholder like `KAFKA_BOOTSTRAP_SERVERS`, that variable is referenced directly in YAML via `${KAFKA_BOOTSTRAP_SERVERS}`. When using the Spring Boot property-based variable name, such as `SPRING_KAFKA_BOOTSTRAP_SERVERS`, Spring Boot can bind directly to the corresponding property without needing a separate placeholder.

Avoid declaring two sources with the same meaning yet different values unless you understand precedence. For example, YAML sets `bootstrap-servers` to one value while the environment sets `SPRING_KAFKA_BOOTSTRAP_SERVERS` to another; the environment variable can override the file configuration and connect the application to an unexpected cluster.

## 6. Configuration source precedence

Spring Boot merges configuration from many sources. Practically, keep in mind:

- Shared configuration files provide default values.
- Profile-specific files override shared values when the corresponding profile is active.
- Environment variables and system properties can override file-based configuration.
- Command-line arguments normally take higher precedence than standard configuration sources.

The full precedence order includes additional sources such as test properties, `SPRING_APPLICATION_JSON`, imported configs, and framework-added property sources. When conflicts arise, do not guess based on directory file order; verify the effective values by inspecting the loaded configuration.

For example: `application.yml` sets `bootstrap-servers` to `localhost:9092`, `application-prod.yml` sets the production endpoint, yet `SPRING_KAFKA_BOOTSTRAP_SERVERS` in the container contains the staging endpoint. The value from the environment variable can win over the file values, causing the application to connect to staging. This is why manifests and environment variables must be managed per deployment environment.

## 7. Passing configuration into Docker Compose

In Docker Compose, applications typically connect to Kafka's service name on the same Docker network. Inside an application container, `localhost` points to the application container itself, not the Kafka container.

Example application service:

```yaml
services:
  messaging-service:
    image: example/messaging-service:1.0.0
    environment:
      SPRING_PROFILES_ACTIVE: dev
      KAFKA_BOOTSTRAP_SERVERS: kafka:9092
      KAFKA_CONSUMER_GROUP_ID: order-service-dev
    depends_on:
      - kafka
```

The address `kafka:9092` only works if the Kafka service advertises a listener reachable from the Compose network. The broker's `advertised.listeners` setting must match the hostname and port the application uses after receiving metadata.

If Compose is used for production or shared environments, supply credentials via the platform's secret mechanism. Never place real passwords directly inside a Compose file committed to a repository.

## 8. Passing configuration into Kubernetes

Kubernetes typically separates non-sensitive configuration from sensitive credentials:

- **ConfigMap** stores profiles, bootstrap servers, consumer groups, and non-secret parameters.
- **Secret** stores passwords, SASL JAAS configs, private keys, or truststore passwords.

Abbreviated Deployment example:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: messaging-service
spec:
  replicas: 2
  selector:
    matchLabels:
      app: messaging-service
  template:
    metadata:
      labels:
        app: messaging-service
    spec:
      containers:
        - name: app
          image: example/messaging-service:1.0.0
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: prod
            - name: KAFKA_BOOTSTRAP_SERVERS
              valueFrom:
                configMapKeyRef:
                  name: messaging-config
                  key: kafka-bootstrap-servers
            - name: KAFKA_SASL_JAAS_CONFIG
              valueFrom:
                secretKeyRef:
                  name: kafka-credentials
                  key: sasl-jaas-config
```

ConfigMaps and Secrets must be created separately in the deployment namespace. Secret read permissions should be restricted by service account and RBAC. Kubernetes Secrets do not automatically mean data is encrypted across every storage layer; operational environments should configure encryption at rest and proper credential management/rotation workflows.

When a ConfigMap or Secret is mounted as environment variables, running processes do not automatically pick up new values. Normally a Pod rollout/restart is needed for the application to read updated configuration. When mounted as files, whether files update and how the application reloads depends on the application's configuration mechanism; the Kafka client also does not automatically reconfigure every connection setting merely because a file changed.

## 9. Grouping business configuration with @ConfigurationProperties

Standard Kafka properties are already bound by Spring Boot via `spring.kafka.*`. For application-specific settings, such as topic names, business-specific consumer group names, or publisher feature flags, group them into a strongly typed configuration class.

Example:

```yaml
app:
  kafka:
    order-topic: order-events
    audit-topic: audit-events
```

Declare a configuration record:

```java
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "app.kafka")
@Validated
public record AppKafkaProperties(
    @NotBlank String orderTopic,
    @NotBlank String auditTopic
) {
}
```

Constraints such as `@NotBlank` require a Jakarta Bean Validation implementation. If the project does not yet have a validation provider, add `spring-boot-starter-validation` to runtime dependencies (Maven uses group `org.springframework.boot`, artifact `spring-boot-starter-validation`; Gradle uses `implementation("org.springframework.boot:spring-boot-starter-validation")`). In Spring Boot 3, validation annotations belong to the `jakarta.validation` namespace.

Enable configuration properties scanning on the application class:

```java
@SpringBootApplication
@ConfigurationPropertiesScan
public class MessagingApplication {

    public static void main(String[] args) {
        SpringApplication.run(MessagingApplication.class, args);
    }
}
```

Then inject `AppKafkaProperties` into publishers or listeners that need topic names. You can use `@EnableConfigurationProperties(AppKafkaProperties.class)` instead of `@ConfigurationPropertiesScan` if you want explicit registration.

For required properties, apply validations such as `@NotBlank`, `@NotNull`, `@Min`, or appropriate constraints. Missing configuration should fail the application at startup rather than surfacing late while processing records.

Do not recreate a `@ConfigurationProperties` class for all of `spring.kafka.*` when Spring Boot already provides `KafkaProperties` and auto-configuration. Use a dedicated prefix such as `app.kafka` for business-specific settings.

## 10. Testing profile-based configuration

Profile-based configuration should also be tested. Use `@ActiveProfiles` to select a profile in tests:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@ActiveProfiles("test")
class KafkaConfigurationTest {

    @Autowired
    private Environment environment;

    @Test
    void loadsTestProfile() {
        assertThat(environment.getActiveProfiles())
            .contains("test");
    }
}
```

If an integration test uses Embedded Kafka, let `@EmbeddedKafka` supply the bootstrap address to Spring Kafka:

```java
@SpringBootTest
@ActiveProfiles("test")
@EmbeddedKafka(
    partitions = 1,
    topics = "order-events",
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
class OrderMessagingIntegrationTest {
    // Test KafkaTemplate and @KafkaListener here.
}
```

The `test` profile can set defaults for testing, while the embedded broker address is written by the annotation into the specified property. Do not let tests accidentally use dev or production endpoints via environment variables on the test runner machine.

You can validate profile-specific configurations in CI by running dedicated tests or starting the application context with the corresponding profile. There is no need to connect to production Kafka just to verify that placeholders and validations work.

## 11. Diagnostic workflow when the application connects to the wrong Kafka

When the application cannot connect or sends records to an unintended cluster, inspect in order:

1. **Active profile**: verify whether `SPRING_PROFILES_ACTIVE` or `--spring.profiles.active` is correct.
2. **Effective bootstrap servers**: check `spring.kafka.bootstrap-servers` after all configuration sources are merged.
3. **Environment variables**: verify variable names, values, comma separators between brokers, and injection into the exact process/container.
4. **Broker listeners**: ensure brokers advertise hostnames/ports reachable from where the application runs.
5. **Security**: verify `security.protocol`, SASL mechanism, credentials, truststore, and certificates.
6. **Consumer group**: check group IDs so multiple environments do not accidentally share one group.
7. **Updated configuration**: confirm the Pod or process was restarted after changing environment variables or secrets.

Never print the entire environment or dump all property sources to logs in production because they may contain credentials. If you need to inspect effective configuration, log only non-sensitive fields such as active profiles, masked broker hostnames, or consumer groups. Actuator endpoints like `env` and `configprops` must be strictly protected if enabled in operational environments.

## 12. Operational principles

- Use `application.yml` for shared settings and profile-specific files for genuine differences between environments.
- Select profiles via environment variables or deployment arguments; never hardcode the production profile in source code.
- Use environment variables or a secret manager to supply per-environment endpoints and credentials.
- Keep secrets out of Git, logs, image layers, and packaged configuration files.
- Use `@ConfigurationProperties` with validation for mandatory business configurations.
- Separate consumer groups by environment to avoid environments unintentionally sharing reading progress.
- Verify `advertised.listeners` and network paths from the exact container/Pod running Spring Boot.
- After changing connection settings, roll out or restart the application according to deployment procedures so the Kafka client picks up the new configuration.

When profiles, environment variables, and secrets are clearly organized, the same Spring Kafka application can run in local, development, and production with the right Kafka cluster, serializers, consumer groups, and security mechanisms for each environment.

