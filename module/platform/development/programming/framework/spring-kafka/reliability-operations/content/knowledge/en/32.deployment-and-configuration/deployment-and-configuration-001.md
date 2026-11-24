# Externalized Kafka Configuration in Spring Kafka Reliability Operations

## 1. Context: Why Externalize Kafka Configuration Outside the Application?

A Spring Kafka service may run the exact same source code version on a laptop, in test environments, in staging, and in production. However, each environment has different **bootstrap servers, topics, consumer groups, authentication methods, TLS certificates, concurrency levels, and processing limits**. Hardcoding those values in Java or packaging secrets directly into the JAR easily leads to two dangerous failures:

- A build intended for staging accidentally points to production Kafka or reads another tenant's topic.
- When rotating credentials or changing brokers, the operations team must edit source code and rebuild the image, while old secrets remain in Git, image layers, and CI systems.

**Externalized Kafka configuration** is a design where **a single application artifact** receives appropriate configuration from the deployment environment, while maintaining clear boundaries between regular configuration, security secrets, and reliability policies.

~~~text
                   ONE APPLICATION ARTIFACT
                  orders-worker:1.2.0
                           |
            +--------------+--------------+
            |              |              |
          LOCAL          STAGING          PROD
            |              |              |
       local config     ConfigMap        ConfigMap
       test broker      + Secret         + Secret
            |              |              |
            v              v              v
       localhost:9092  staging brokers   prod brokers
       PLAINTEXT        SASL_SSL          SASL_SSL
       test topics      test groups       prod groups
~~~

In *Spring Kafka Reliability Operations*, this is not merely a configuration topic. A single wrong value can cause a consumer to **skip messages**, **process duplicates**, trigger **continuous rebalances**, **lose connectivity**, or break isolation between environments.

### Learning Outcomes

After this lesson, you will be able to:

1. Organize `application.yml`, profiles, environment variables, ConfigMaps, and Secrets clearly.
2. Understand how `spring.kafka.*` is translated by Spring Boot into Kafka client configurations.
3. Separate business topics and group IDs into `@ConfigurationProperties` with validation.
4. Keep `SASL_SSL`/TLS configurations out of images and Git using `configtree:` or a secret provider.
5. Identify which configuration changes affect offsets, partitions, idempotency, and consumer groups.
6. Design rollouts, rotations, and pre-production checks before shifting production traffic.
7. Test configuration binding, broker connectivity, and missing-configuration errors.
8. Diagnose wrong brokers, wrong advertised listeners, ACLs, TLS, and profile issues.

The main examples use **Spring Boot 3.x, Spring Kafka 3.x, Java 17+**. The principles remain applicable to newer releases, though property names and APIs should be verified against the BOM/Javadoc of your actual version.

## 2. Configuration Groups to Separate

You should not dump everything into one giant config file or a single uncontrolled `KAFKA_CONFIG_JSON` variable.

| Group | Examples | Recommended Source |
| --- | --- | --- |
| Connectivity | `bootstrap-servers`, DNS, cluster | ConfigMap, deployment variables, service discovery. |
| Consumer identity | `group-id`, `client-id` | Configured per workload/environment, with change review. |
| Producer reliability | `acks`, idempotence, delivery timeout | Version-controlled base config, overridden with justification. |
| Consumer reliability | auto commit, ack mode, poll interval, concurrency | Base config + bounded operational overrides. |
| Business routing | input topic, DLT topic, audit topic | Validated `app.messaging.*`, ConfigMap. |
| Security | SASL mechanism, TLS protocol, certificate location | Protocol/method in ConfigMap; keys/passwords in secret store. |
| Actual secrets | password, JAAS credential, private key | Kubernetes Secret, Vault, cloud secret manager, mounted file. |
| Monitoring | client ID, metric tags, tracing | Base config and observability configuration. |
| Deployment | replica count, resources, rolling update | Kubernetes manifests/Helm/GitOps; never put in Java code. |

**Rule:** configuration is responsible for *routing and behavior*, whereas the secret manager is responsible for *authentication values*. Secret names or paths can also be sensitive; evaluate them before exposing them in logs/dashboards.

## 3. How Does Spring Boot Load Configuration?

Spring Boot supports **externalized configuration** from multiple sources: `application.yml`, `application-<profile>.yml`, files outside the JAR, environment variables, Java system properties, command-line arguments, configuration trees, and additional Config Data imports.

For example, an application has base configuration inside the JAR:

~~~yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS}
~~~

At deployment time, you can provide:

~~~bash
export KAFKA_BOOTSTRAP_SERVERS="kafka-1.example.internal:9093,kafka-2.example.internal:9093"
java -jar orders-worker.jar --spring.profiles.active=prod
~~~

Or inject environment variables into the Kubernetes manifest. **There is no need to rebuild the JAR** when changing the bootstrap servers list.

### 3.1. Precedence Order

In principle, a configuration source with **higher precedence** overrides a lower one. Command-line options such as `--spring.kafka.bootstrap-servers=...` usually take precedence over properties loaded from files. Environment variables also typically override values in the packaged `application.yml`.

However, the full precedence order also includes Config Data imports, profile-specific documents, Java system properties, and other sources. **Do not invent a simplified precedence table and assume it always holds**: consult the Spring Boot documentation for your exact version and verify actual binding results.

~~~text
application.yml inside the JAR
       |
       v
profile + external config + env + command line
       |
       v
       Spring Environment
       |
       +--> Spring Boot KafkaProperties
       |
       +--> @ConfigurationProperties(app.messaging)
       |
       v
Kafka ConsumerFactory / ProducerFactory / Listener
~~~

Environment variables typically use uppercase underscore naming:

~~~text
spring.kafka.bootstrap-servers   -> SPRING_KAFKA_BOOTSTRAP_SERVERS
spring.kafka.consumer.group-id   -> SPRING_KAFKA_CONSUMER_GROUP_ID
spring.kafka.listener.concurrency -> SPRING_KAFKA_LISTENER_CONCURRENCY
~~~

Note: `spring.kafka.properties` and `consumer.properties` are **Maps containing dotted Kafka client properties**. Arbitrarily replacing `.` with `_` can break map key binding/normalization. For Kafka keys like `max.poll.interval.ms` or `sasl.jaas.config`, the least ambiguous approach is to **keep the key intact in YAML and supply the value via a placeholder** from the environment or secret.

### 3.2. Placeholders and Default Values

~~~yaml
app:
  messaging:
    max-attempts: ${KAFKA_MAX_ATTEMPTS:3}
~~~

`${KAFKA_MAX_ATTEMPTS:3}` allows a default value of 3. For **mandatory** settings such as production bootstrap servers, topics, groups, or security references, do not overuse local default values because production might accidentally connect to the wrong cluster.

For example:

~~~yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS}
~~~

If a required value is missing, the application should **fail early** instead of silently defaulting to `localhost:9092` unintentionally.

## 4. Distinguishing `spring.kafka.*` and `app.messaging.*`

Spring Boot automatically binds properties under `spring.kafka.*` into Kafka client configurations. In contrast, `app.messaging.*` is an **application-defined namespace** used for topic names, business policies, or system-level retries.

For example:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: ${KAFKA_CONSUMER_GROUP}

app:
  messaging:
    input-topic: ${KAFKA_INPUT_TOPIC}
    dlt-topic: ${KAFKA_DLT_TOPIC}
~~~

Here:

- `spring.kafka.consumer.group-id` is a property supported by Spring Boot Kafka.
- `app.messaging.input-topic` does **not** automatically create topics or auto-connect. The application must read the property and use it in `@KafkaListener`/publishers.
- Configuration under `app.messaging` can be validated using `@ConfigurationProperties`.
- Do not confuse application topic names with Kafka broker properties or topic-level configurations.

### Common Spring Boot Property Groups

| Group | Examples |
| --- | --- |
| Common client | `spring.kafka.bootstrap-servers`, `spring.kafka.client-id`, `spring.kafka.properties.*` |
| Consumer | `spring.kafka.consumer.group-id`, `enable-auto-commit`, `auto-offset-reset`, `properties.*` |
| Producer | `spring.kafka.producer.acks`, `key-serializer`, `value-serializer`, `properties.*` |
| Listener | `spring.kafka.listener.ack-mode`, `concurrency`, `type` |
| SSL | `spring.kafka.ssl.*` or appropriate Kafka client SSL properties |
| Admin | `spring.kafka.admin.*` |
| Template/Streams | Dedicated property groups if the project uses KafkaTemplate or Kafka Streams |

Client-level properties placed under `spring.kafka.properties` can serve as shared configuration. `spring.kafka.consumer.properties` and `spring.kafka.producer.properties` allow client-specific overrides based on how Spring Boot builds client configs.

## 5. Practice Project Structure

~~~text
orders-worker/
├── build.gradle
└── src/main/
    ├── java/com/example/orders/
    │   ├── OrdersWorkerApplication.java
    │   ├── MessagingProperties.java
    │   ├── OrderConsumer.java
    │   └── AuditPublisher.java
    └── resources/
        ├── application.yml
        ├── application-local.yml
        └── application-prod.yml

deployment/
├── orders-configmap.yaml
└── orders-deployment.yaml
~~~

All configuration files in Git contain **only public values or placeholders**—never real SASL passwords, access tokens, or private keys.

### 5.1. Dependencies

Gradle example for Spring Boot 3.x:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.kafka:spring-kafka'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:kafka'
}
~~~

Keep Spring Boot, Spring Kafka, and Kafka client versions aligned via dependency management/BOM. Testcontainers Kafka module names and container APIs changed across some 1.x and 2.x lines, so the sample test below explicitly notes its version context.

## 6. Creating `application.yml` as the Base Configuration

File `src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: orders-worker

  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS}
    client-id: ${KAFKA_CLIENT_ID:orders-worker}

    consumer:
      group-id: ${KAFKA_CONSUMER_GROUP}
      enable-auto-commit: false
      auto-offset-reset: ${KAFKA_AUTO_OFFSET_RESET:none}
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      properties:
        max.poll.records: ${KAFKA_MAX_POLL_RECORDS:100}
        max.poll.interval.ms: ${KAFKA_MAX_POLL_INTERVAL_MS:300000}

    listener:
      ack-mode: record
      concurrency: ${KAFKA_LISTENER_CONCURRENCY:2}

    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
      acks: all
      properties:
        enable.idempotence: true
        delivery.timeout.ms: 120000

app:
  messaging:
    input-topic: ${KAFKA_INPUT_TOPIC}
    dlt-topic: ${KAFKA_DLT_TOPIC}
~~~

The example uses `String` to keep focus on externalized config. If the application uses JSON/Avro/Protobuf, serializers/deserializers and Schema Registry must also be configured, compatibility-checked, and paired with deserialization error handling.

### 6.1. Reliability Choices in the Example

**`enable-auto-commit: false`**: the application delegates offset commits to the Spring Kafka container according to the acknowledgment mode rather than periodic Kafka client auto-commit.

**`ack-mode: record`**: for a standard record listener, the container can commit the offset after a record is successfully processed by the listener, according to the actual semantics of the container/error handler. This does not automatically create a transaction between Kafka and an external database.

**`auto-offset-reset: none`**: if the group has no valid committed offset yet, the consumer will not silently start at `earliest` or `latest`; it throws an error that must be handled intentionally. This is an **illustrative fail-fast policy**, not the right value for every system. If business requirements allow replaying from the beginning, use `earliest`; if only new events are needed, `latest` may fit provided you understand the risk of skipping backlog.

**`max.poll.records`**: caps the number of records returned in a single poll. It does not by itself guarantee listener processing time.

**`max.poll.interval.ms`**: limits the time between polls for consumer group membership. If processing takes too long, the consumer may lose membership and trigger a rebalance. Balance this against batch size, downstream latency, heartbeats, and pause/retry mechanisms.

**`concurrency`**: the number of consumer threads requested by the container. If the total consumer threads across all replicas exceeds the number of partitions assigned to the group, some threads will sit idle. For example, 3 pods x concurrency 2 = 6 consumers; if the topic has only 4 partitions, not every consumer will receive a partition.

**`acks: all` and `enable.idempotence: true`**: improve safety when the producer retries requests within the same producer session and with properly configured brokers. They **do not guarantee exactly-once when the consumer writes to a database, makes HTTP calls, or when the app itself emits the same business event multiple times**.

## 7. `application-local.yml`: Local Profile Without Production Credentials

File `src/main/resources/application-local.yml`:

~~~yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}
    consumer:
      group-id: ${KAFKA_CONSUMER_GROUP:orders-worker-local}
      auto-offset-reset: earliest
    properties:
      security.protocol: PLAINTEXT

app:
  messaging:
    input-topic: ${KAFKA_INPUT_TOPIC:orders.events.local}
    dlt-topic: ${KAFKA_DLT_TOPIC:orders.events.local.DLT}
~~~

Run locally with the profile:

~~~bash
java -jar orders-worker.jar --spring.profiles.active=local
~~~

Or:

~~~bash
export SPRING_PROFILES_ACTIVE=local
export KAFKA_BOOTSTRAP_SERVERS=localhost:9092
java -jar orders-worker.jar
~~~

Default values like `localhost`, `PLAINTEXT`, and `earliest` only make sense in an **isolated development environment**. Never use the local profile as an automatic fallback in production.

Note: `localhost` inside a Docker container or Kubernetes Pod means that container/Pod itself, **not the host machine or another broker**. For Docker Compose, use the service hostname on the Compose network; for Kubernetes, use the appropriate DNS/service endpoint.

## 8. `application-prod.yml`: Security and Fail-Fast Configuration

File `src/main/resources/application-prod.yml`:

~~~yaml
spring:
  config:
    import: "configtree:/etc/kafka-secrets/"

  kafka:
    properties:
      security.protocol: SASL_SSL
      sasl.mechanism: SCRAM-SHA-512
      sasl.jaas.config: ${kafka.jaas.config}

    ssl:
      trust-store-location: ${KAFKA_TRUSTSTORE_LOCATION:file:/etc/kafka-certs/truststore.p12}
      trust-store-type: PKCS12
      trust-store-password: ${kafka.truststore.password}
~~~

These parameters serve distinct purposes:

| Property | Purpose |
| --- | --- |
| `security.protocol=SASL_SSL` | TLS connection combined with SASL authentication. |
| `sasl.mechanism=SCRAM-SHA-512` | Agreed Kafka client/broker authentication mechanism. |
| `sasl.jaas.config` | SASL login credentials; **contains secrets**, never commit to Git. |
| `trust-store-location` | Location of the truststore used to verify the broker certificate. |
| `trust-store-type=PKCS12` | Truststore format used in this example. |
| `trust-store-password` | Password to open the truststore if set; sourced from secret. |

This is an **example for a Kafka cluster using SCRAM-SHA-512 and TLS**; it does not apply verbatim to all managed Kafka services. Clusters using mTLS, OAuthBearer, IAM authentication, or other mechanisms require corresponding configs/security providers.

The path `configtree:/etc/kafka-secrets/` **omits the `optional:` prefix**, so that if the mandatory secret directory does not exist, the application will not silently start up without credentials. Directory and file names must match the deployment mounts.

### 8.1. File Layout of the Config Tree

After secrets are mounted into the Pod, you may see:

~~~text
/etc/kafka-secrets/
    kafka.jaas.config
    kafka.truststore.password

/etc/kafka-certs/
    truststore.p12
~~~

Each **filename** in the config tree corresponds to a property key; the file content is the property value. Thus the file `kafka.jaas.config` is referenced via `${kafka.jaas.config}` in YAML.

Example format for the JAAS file content, **not a real credential**:

~~~text
org.apache.kafka.common.security.scram.ScramLoginModule required username="example-user" password="REPLACE-WITH-SECRET";
~~~

Do not store this actual content in repositories or logs. An external secret provisioning system outside Git—such as External Secrets Operator, Vault CSI driver, a cloud secret manager, or a secured provisioning mechanism—delivers the real files to the Pod.

### 8.2. Why Choose Secret Files Over Environment Variables?

Environment variables can also externalize credentials, for instance via a `${KAFKA_SASL_JAAS_CONFIG}` placeholder. However:

- Environment variables may appear in process diagnostics, dumps, certain tooling, and improper container access.
- On Kubernetes, secrets injected into environment variables **do not automatically update in a running process** when the Secret resource changes.
- File mounts can simplify permission and rotation management, though **Kafka clients do not automatically reload every credential merely because a file or Config Data property changes**.

The file model does not eliminate all risk; secrets still enter Java memory and Kafka configuration when clients initialize. You must protect Pod access, Kubernetes/etcd APIs, logs, backups, and rolling restart procedures.

## 9. Kubernetes: ConfigMap for Non-Secrets, Secret for Credentials

A production deployment typically separates concerns clearly:

~~~text
Git / GitOps
   |
   +-- ConfigMap
   |    KAFKA_BOOTSTRAP_SERVERS
   |    KAFKA_CONSUMER_GROUP
   |    KAFKA_INPUT_TOPIC
   |    KAFKA_DLT_TOPIC
   |    KAFKA_LISTENER_CONCURRENCY
   |
   +-- Deployment
        image, replicas, resources, probes
              |
              v
             Pod
              |
              +-- envFrom(ConfigMap)
              |
              +-- volumeMount(Secret files)
                        |
                        v
             Spring Boot configtree
                        |
                        v
                  Kafka clients
~~~

### 9.1. ConfigMap

File `deployment/orders-configmap.yaml`:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: orders-kafka-settings
data:
  KAFKA_BOOTSTRAP_SERVERS: "kafka-1.prod.example.internal:9093,kafka-2.prod.example.internal:9093"
  KAFKA_CONSUMER_GROUP: "orders-worker-v1"
  KAFKA_CLIENT_ID: "orders-worker"
  KAFKA_INPUT_TOPIC: "orders.events.v1"
  KAFKA_DLT_TOPIC: "orders.events.v1.DLT"
  KAFKA_LISTENER_CONCURRENCY: "2"
  KAFKA_MAX_POLL_RECORDS: "100"
  KAFKA_MAX_POLL_INTERVAL_MS: "300000"
  KAFKA_AUTO_OFFSET_RESET: "none"
~~~

These hosts, topics, and groups are **illustrative names**; in real deployments, replace them with values managed for the target environment.

A ConfigMap is **not a secret store**. Never put passwords, bearer tokens, or PEM private keys in a ConfigMap.

### 9.2. Deployment

File `deployment/orders-deployment.yaml`:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-worker
spec:
  replicas: 2
  selector:
    matchLabels:
      app: orders-worker
  template:
    metadata:
      labels:
        app: orders-worker
    spec:
      containers:
        - name: app
          image: registry.example.org/orders-worker:1.2.0
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: prod
          envFrom:
            - configMapRef:
                name: orders-kafka-settings
          volumeMounts:
            - name: kafka-credentials
              mountPath: /etc/kafka-secrets
              readOnly: true
            - name: kafka-certs
              mountPath: /etc/kafka-certs
              readOnly: true
      volumes:
        - name: kafka-credentials
          secret:
            secretName: orders-kafka-auth
            items:
              - key: jaas-config
                path: kafka.jaas.config
              - key: truststore-password
                path: kafka.truststore.password
        - name: kafka-certs
          secret:
            secretName: orders-kafka-truststore
            items:
              - key: truststore.p12
                path: truststore.p12
~~~

This is an **illustrative manifest**; before production use, add resource requests/limits, health probes, rollout strategy, service account/Pod security, and applicable cluster policies.

The two Secrets `orders-kafka-auth` and `orders-kafka-truststore` must be provisioned via a separate secure workflow. **Never commit Secret manifests containing real values**, even when Base64-encoded: Base64 is encoding, not encryption.

### 9.3. What Kubernetes Does Not Do Automatically

- Editing a ConfigMap does not mean running Kafka consumers immediately reconfigure themselves.
- Secret volumes may be updated by kubelet, but running Java/Kafka clients generally must be **reinitialized or rolled out** to use new credentials.
- Environment variables injected at Pod creation time do not update when a ConfigMap/Secret changes.
- Changing `group-id` is not equivalent to a simple rolling restart: it changes the **consumer group identity** and can cause data replay or skipped records.
- `replicas` x `listener.concurrency` is the expected consumer thread count and must account for partition count and downstream capacity.

**Do not use `kubectl describe`, logs, or debug endpoints to print raw secrets.** During investigation, prioritize metadata, reference names, mount status, and permission checks rather than dumping contents.

## 10. Externalized Configuration on VMs or Docker Compose

Not every application runs on Kubernetes.

### 10.1. VM / systemd

You can use configuration files located outside the JAR:

~~~bash
java -jar orders-worker.jar \
  --spring.profiles.active=prod \
  --spring.config.additional-location=file:/etc/orders-worker/
~~~

For example, `/etc/orders-worker/application-prod.yml` contains only non-secret configuration and references. Credential values still come from a secret store or properly protected files.

Never pass passwords directly in command-line arguments: values can become visible in process listings, shell history, and CI logs.

### 10.2. Local Docker Compose

~~~yaml
services:
  orders-worker:
    image: registry.example.org/orders-worker:1.2.0
    environment:
      SPRING_PROFILES_ACTIVE: local
      KAFKA_BOOTSTRAP_SERVERS: kafka:9092
      KAFKA_CONSUMER_GROUP: orders-worker-local
      KAFKA_INPUT_TOPIC: orders.events.local
      KAFKA_DLT_TOPIC: orders.events.local.DLT
    depends_on:
      - kafka
~~~

`kafka` must be a valid service DNS name on the Compose network; this example does not deploy the broker itself.

If you use `.env` during development, add files containing secrets to `.gitignore`, but remember **gitignore does not protect data that was already committed**. If a secret is exposed, revoke/rotate it and handle history per policy.

## 11. Type-Safe Configuration for Topics and Business Settings

Scattering `@Value("${...}")` across many classes invites typos and makes validation difficult. Use `@ConfigurationProperties` for the **application namespace**:

~~~java
package com.example.orders;

import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.messaging")
public record MessagingProperties(
        @NotBlank String inputTopic,
        @NotBlank String dltTopic) {
}
~~~

In the application entry class:

~~~java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class OrdersWorkerApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersWorkerApplication.class, args);
    }
}
~~~

`@ConfigurationPropertiesScan` discovers record properties; `spring-boot-starter-validation` enforces `@NotBlank` checks during binding.

### Usage in Listener

~~~java
package com.example.orders;

import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderConsumer {

    @KafkaListener(topics = "${app.messaging.input-topic}")
    public void consume(String payload) {
        // Parse + validate + execute idempotent business logic.
        // On processing error: throw exception so the error handler applies the policy.
    }
}
~~~

### Usage in Publisher

~~~java
package com.example.orders;

import java.util.concurrent.CompletableFuture;

import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Component;

@Component
public class AuditPublisher {

    private final KafkaTemplate<String, String> kafkaTemplate;
    private final MessagingProperties properties;

    public AuditPublisher(
            KafkaTemplate<String, String> kafkaTemplate,
            MessagingProperties properties) {
        this.kafkaTemplate = kafkaTemplate;
        this.properties = properties;
    }

    public CompletableFuture<SendResult<String, String>> publishAudit(
            String businessKey, String payload) {
        // Illustrative example: can be changed to a dedicated audit topic.
        return kafkaTemplate.send(
                properties.dltTopic(), businessKey, payload);
    }
}
~~~

Here, the method name `publishAudit` only illustrates how to read the configuration property; in a real project, **do not use the DLT as an audit topic**. Define a dedicated `audit-topic` property if you need to publish audit events. The DLT is reserved for unprocessable records under the error-handling policy.

Returning a `CompletableFuture` does not mean the broker has ACKed at the moment the method returns. Callers must handle completion/failure properly, especially when critical messages require an outbox or transaction.

## 12. Client-Level Kafka Configuration and Proper Overrides

A common mistake is placing a property under the wrong branch.

~~~yaml
spring:
  kafka:
    properties:
      security.protocol: SASL_SSL

    consumer:
      properties:
        max.poll.interval.ms: 300000
        fetch.min.bytes: 1

    producer:
      properties:
        enable.idempotence: true
        delivery.timeout.ms: 120000
~~~

| Location | Effect |
| --- | --- |
| `spring.kafka.properties.*` | Common properties applied to Kafka client factories when applicable. |
| `spring.kafka.consumer.properties.*` | Consumer-specific properties; can override shared properties with the same key. |
| `spring.kafka.producer.properties.*` | Producer-specific properties. |
| `spring.kafka.listener.*` | Container/acknowledgment behavior managed by Spring Kafka. |
| `app.messaging.*` | Application-managed properties; not automatically passed to Kafka clients. |

Do not assume every Kafka client config has a Boot typed shortcut. Specific Kafka client keys such as `max.poll.interval.ms`, `request.timeout.ms`, and `sasl.jaas.config` can be passed through the `properties` Map.

**Important:** dotted keys stay as-is in the YAML Map; avoid "transforming" keys into environment strings that do not bind as expected. When overrides are needed, it is best to supply the env value via the corresponding placeholder and verify the resulting property in a test.

## 13. Configurations That Directly Impact Reliability

Kafka configuration can be externalized, but changing certain values requires an **operational procedure**, not just `kubectl apply`.

| Property | What happens if changed improperly? | How to decide |
| --- | --- | --- |
| Bootstrap servers | Connection failure or connecting to the wrong cluster | Manage endpoints per environment; verify DNS/TLS. |
| Consumer group ID | May replay data or skip backlog depending on offset-reset | Treat as a data-processing identity change; requires a migration plan. |
| `auto.offset.reset` | `earliest` may cause huge replay; `latest` may drop old records | Choose per data contract; never use as an incident quick-fix. |
| `enable.auto.commit` | Increases risk of committing before processing finishes if misconfigured | Define explicit ack strategy and error handler. |
| Ack mode | Alters when offsets are committed | Test failures, retries, rebalances, and side effects. |
| Listener concurrency | Spawns extra consumer threads, load, and rebalances | Balance partition count, replicas, and database capacity. |
| `max.poll.records` | Too many records per poll lengthens processing time | Benchmark latency and batch size. |
| `max.poll.interval.ms` | Too short triggers rebalances during slow processing | Measure p99 processing time and recovery. |
| Producer `acks` | `acks=0/1` has a different failure window than `all` | Align with durability requirements; understand broker `min.insync.replicas`. |
| Producer idempotence | Conflicting settings can prevent the client from starting | Use `acks=all`, compatible retries, and in-flight settings. |
| Delivery/request timeouts | Too short causes failures or duplicate retries at the app layer | Balance against SLAs and broker/network latency. |
| SASL/TLS | Auth, handshake, or trust verification fails | Align with broker policy and certificate chain. |
| Topic name | Consumer reads wrong topic or DLT does not exist | Review IaC/ACLs and verify topic existence. |

### 13.1. `acks=all` Alone Is Not Exactly-Once

`acks=all` requires broker ACKs according to the current ISR condition. Producer idempotence helps limit duplicates caused by retries within an eligible producer session. However, if a consumer writes to a database and crashes **before the offset is committed**, the message can be redelivered.

~~~text
Kafka record #42
      |
      v
Consumer processes -> DB COMMIT succeeds
      |
   process crash
      |
   offset NOT YET COMMITTED
      |
      v
Kafka redelivery -> reprocess record #42
~~~

The solution lies in transaction/outbox design or business idempotency (e.g., a unique key on event ID), **not solely in a YAML property**. Kafka transactions and Spring Kafka Exactly Once Semantics have specific preconditions and scopes; they do not automatically encompass external databases outside the Kafka transaction.

### 13.2. Changing a Consumer Group Is a Data Change

If you change:

~~~text
KAFKA_CONSUMER_GROUP=orders-worker-v1
```

to:

~~~text
KAFKA_CONSUMER_GROUP=orders-worker-v2
~~~

then the new group has a different set of committed offsets. With `earliest`, it can replay a large backlog; with `latest`, it can skip records that existed before the new group joined. With `none`, the consumer may throw an error if no offset exists yet. **Do not change the group ID just to clear lag alerts or speed up a rollout.**

## 14. Config Validation and Fail-Fast

Beyond validating `MessagingProperties`, include several safeguards:

1. Reject empty bootstrap servers or `localhost` defaults outside the local profile.
2. Disallow `PLAINTEXT` in prod unless security policy explicitly approves an equivalent configuration.
3. Require non-empty topic and group names matching naming conventions.
4. Require positive concurrency bounded by capacity.
5. Verify mandatory secret files/configtree exist before creating Kafka clients.
6. Validate data types (e.g., integer milliseconds) and value ranges.
7. Verify certificate trust chains/hostnames and cluster ACLs.
8. Never emit raw secrets into validation error logs.

**Distinguish between configuration binding successfully and Kafka connectivity actually working.** An application may start up yet its listener fails to join the group due to wrong ACLs or DNS; Spring startup validation does not replace a real Kafka client check.

### Example Profile-Specific Validation for Production

You can build an `ApplicationRunner` to check safe property invariants:

~~~java
@Bean
ApplicationRunner validateKafkaDeployment(
        Environment environment,
        MessagingProperties messaging) {

    return args -> {
        if (environment.acceptsProfiles(Profiles.of("prod"))) {
            String brokers = environment.getRequiredProperty(
                    "spring.kafka.bootstrap-servers");
            String protocol = environment.getRequiredProperty(
                    "spring.kafka.properties.security.protocol");

            if (brokers.isBlank()) {
                throw new IllegalStateException(
                        "Kafka bootstrap servers are missing");
            }
            if (!"SASL_SSL".equals(protocol)) {
                throw new IllegalStateException(
                        "Production Kafka must use SASL_SSL");
            }
        }
    };
}
~~~

This is an **illustrative policy** for an organization using SCRAM/TLS only. A system using `SSL` with mTLS or another security mechanism must adapt the check accordingly rather than copying this policy universally.

An `ApplicationRunner` may execute after certain Kafka beans have already been created; if you must block **before** any Kafka client/listener starts, place checks during configuration binding/bean construction or deployment admission, and prove it with tests. Do not rely solely on `ApplicationRunner` for a strict fail-fast boundary.

## 15. Managing Topics and ACLs Outside the Application

Topic names are configuration, but **topic creation**, partition count, replication factor, retention, and ACLs must be managed intentionally.

~~~text
Application configuration:
    input-topic=orders.events.v1
    group-id=orders-worker-v1
    dlt-topic=orders.events.v1.DLT

Kafka infrastructure:
    topic exists?
    partition count?
    replication factor?
    min.insync.replicas?
    retention.ms?
    ACL: read topic + read group?
    producer ACL to DLT?
~~~

In some Spring Boot/Spring Kafka setups, `NewTopic` beans or `KafkaAdmin` can create topics. However, in production environments with strict access control, auto-creating topics on startup can mask misspelled topic names or produce unexpected schemas/partitions.

Common practice uses Terraform, Strimzi, a GitOps operator, or a dedicated Kafka admin platform to provision topics and ACLs. The application simply verifies that the topics and permissions match its needs.

### Do Not Configure a DLT Without a Recovery Policy

Merely externalizing `KAFKA_DLT_TOPIC` does **not** automatically route failing records to the DLT. The application must configure an error handler/recoverer or Spring Kafka non-blocking retry, accounting for retry budgets, headers, serialization, and poison messages.

For example, `DefaultErrorHandler`, backoff, and `DeadLetterPublishingRecoverer` belong to **error-handling code**. If you want retry policies configurable externally, bind the policy into a dedicated `@ConfigurationProperties` class and wire the handler explicitly. Do not treat a topic property alone as a complete reliability implementation.

## 16. What Actually Happens When Runtime Config Changes?

Values are loaded by Spring Boot into `Environment` and bound during bean creation. Kafka producers/consumers maintain their own internal client configuration created at initialization time.

Therefore:

- Updating a ConfigMap in the cluster **does not guarantee** running consumers immediately switch groups/topics or poll timeouts.
- Updating a Secret volume may update the mounted file, but the JAAS config already loaded by the client may remain stale.
- Changing `spring.kafka.consumer.group-id` in a ConfigMap without rolling out Pods can leave **Pods running with different group IDs** during a partial transition.
- Enabling any dynamic refresh mechanism requires understanding how listener containers, producer factories, and secret references are recreated; never assume hot reload works out of the box.

**The more predictable approach is a rolling restart/new deployment after config changes**, sequenced properly and accompanied by monitoring.

### Rolling Change Plan

1. Identify the property to change and its impact on delivery/offsets.
2. Version the configuration and ensure the change is reviewed.
3. Test in a staging environment with matching auth/protocol configuration.
4. Update the ConfigMap/Secret using approved management tooling.
5. Trigger a Deployment rolling update so new Pods load the updated configuration.
6. Monitor consumer group membership, lag, rebalances, error rates, and producer errors.
7. Verify outputs/idempotency under retries/redelivery.
8. If errors occur, roll back **both configuration and workload** per plan; never reset offsets blindly.

If changing the group ID, source topic, serialization, or offset policy, treat it as a **data migration decision** requiring a cutover plan and reconciliation evidence, not merely a rolling deployment.

## 17. Rotating Kafka Secrets Without Prolonged Downtime

In production, passwords or certificates require periodic or emergency rotation.

A safe process depends on the broker supporting **multiple valid credentials during a transition window**:

~~~text
T0: Kafka broker accepts credential A
T1: Create credential B and grant verified equivalent permissions
T2: Secret manager provides B to new Pods
T3: Rolling update: new Pods connect using B
T4: Verify all old Pods have stopped using A
T5: Revoke A; check connections and auth errors
~~~

If the broker does not allow simultaneous A/B credentials or old/new certs, you must schedule a maintenance window or design another suitable rotation strategy.

Keep in mind:

- New Pods load secret B; old Pods typically keep using credential A until restarted.
- Changing TLS CAs/hostnames may require updating the truststore before server-side rotation.
- Never log JAAS strings, passwords, or private keys while debugging.
- Do not rely on a basic readiness probe to conclude a consumer has joined its group and is processing the right topic.
- Monitor authentication errors, consumer lag, and unavailable time throughout the rollout.

## 18. Testing Property Binding Before Connecting to a Broker

Separate configuration tests from real-Kafka tests to catch typos quickly.

Example test for `@ConfigurationProperties` using Spring Boot `Binder`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.mock.env.MockEnvironment;

import static org.junit.jupiter.api.Assertions.*;

class MessagingPropertiesBindingTest {

    @Test
    void bindsTopicNamesFromEnvironment() {
        MockEnvironment env = new MockEnvironment()
                .withProperty(
                        "app.messaging.input-topic",
                        "orders.events.test")
                .withProperty(
                        "app.messaging.dlt-topic",
                        "orders.events.test.DLT");

        MessagingProperties props = Binder.get(env)
                .bind(
                    "app.messaging",
                    Bindable.of(MessagingProperties.class))
                .orElseThrow();

        assertEquals("orders.events.test", props.inputTopic());
        assertEquals("orders.events.test.DLT", props.dltTopic());
    }
}
~~~

This test only proves binding; it does **not** run container validation and does **not** connect to Kafka. To test `@NotBlank`, use a Spring Boot application context with validation active or invoke a `Validator` explicitly.

### Fail-Fast Test for Missing Properties

In a dedicated test context for the `prod` profile, intentionally **omit** `KAFKA_BOOTSTRAP_SERVERS`, topics, or required secret files. Expect the app not to start a ready listener; depending on wiring, the failure may be an unresolved placeholder, config location not found, validation failure, or Kafka client initialization failure.

Never add a `localhost:9092` default for prod just to make startup tests green. This test protects you from deploying a "Ready" Pod that connects to the wrong broker.

## 19. Integration Testing with Real Kafka via Testcontainers

Include a test that spins up a real Kafka broker in a container to verify configuration, producer/consumer behavior, and offsets.

With **Testcontainers 1.x** compatible with the chosen image, a skeleton example:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.KafkaContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;
import org.springframework.boot.autoconfigure.kafka.KafkaProperties;

import static org.junit.jupiter.api.Assertions.*;

@Testcontainers
@SpringBootTest(properties = {
    "spring.kafka.consumer.group-id=orders-worker-it"
})
@ActiveProfiles("local")
class KafkaConfigIT {

    @Container
    static KafkaContainer kafka = new KafkaContainer(
            DockerImageName.parse(
                "confluentinc/cp-kafka:7.6.1"));

    @DynamicPropertySource
    static void kafkaProperties(DynamicPropertyRegistry registry) {
        registry.add(
            "spring.kafka.bootstrap-servers",
            kafka::getBootstrapServers);
        registry.add(
            "app.messaging.input-topic",
            () -> "orders.events.test");
        registry.add(
            "app.messaging.dlt-topic",
            () -> "orders.events.test.DLT");
    }

    @Autowired KafkaProperties kafkaProperties;
    @Autowired MessagingProperties messaging;

    @Test
    void bindsTestBrokerAndTopics() {
        assertTrue(kafkaProperties.getBootstrapServers()
                .contains(kafka.getBootstrapServers()));
        assertEquals(
            "orders.events.test", messaging.inputTopic());
    }
}
~~~

This is a **binding test inside a context with a broker container**. To verify end-to-end flow, create the topic properly, send a record with `KafkaTemplate`, await listener receipt, and assert the target state. Testcontainers 2.x has different Kafka container APIs/packages; use dependencies and documentation matching your version.

Integration scenarios to cover:

| Scenario | Verification |
| --- | --- |
| Local profile with valid broker | Producer/consumer initialize and process records. |
| Wrong bootstrap server | Connection logs and readiness/alerts reflect failure; not confused with an empty topic. |
| Wrong topic name | Listener does not process the expected topic; topic management policy detects mismatch. |
| New consumer group | Offset reset follows the chosen policy; no unintended skipping/replay. |
| Invalid TLS certificate | Handshake fails and errors are recorded safely. |
| Invalid SASL credentials | Auth fails; JAAS string is not exposed in logs. |
| Missing group/topic ACLs | Cannot consume or publish; operational signal emitted. |
| Rollout while consuming | Rebalance and redelivery do not cause duplicate side effects. |
| ConfigMap / Secret rotation | New Pods use new config; old Pods drain/shut down cleanly. |

## 20. Observability for Kafka Configuration

A system can start up cleanly yet its Kafka consumer fails to process data. Monitoring should track:

- **Kafka consumer lag**, record consumption rate, and assigned partition count.
- **Rebalance rate** and record processing duration.
- **Producer send errors**, request latency, retries, and delivery failures.
- **Authentication/authorization errors** by category, without logging secrets.
- **Listener errors**, processed record counts, retries, and DLT publishing.
- **Consumer group membership** per environment and workload.
- **Actual business outcomes**: orders updated, idempotency collisions, backlog.
- **Configuration version / deployment revision** to compare before and after rollout.

When using Spring Boot Actuator, enable appropriate observability levels. Never assume Actuator health indicates "the Kafka consumer joined the right group, reads the right topic, and holds offsets" merely because HTTP status is 200.

### What Should Logging Record?

An appropriate log entry:

~~~text
kafka_client_ready
  app=orders-worker
  profile=prod
  clientId=orders-worker
  groupId=orders-worker-v1
  topic=orders.events.v1
  authProtocol=SASL_SSL
~~~

Never log:

~~~text
sasl.jaas.config
password
access token
private key
raw Authorization header
all Spring Environment properties
~~~

`/actuator/env`, `/actuator/configprops`, and other management endpoints require restricted exposure, authorization, and masking. Do not rely solely on default masking; prevent secrets from entering logs/traces at the source.

## 21. Diagnosing Common Configuration Errors

### 21.1. Unable to Connect to Broker

Common symptoms are continuous reconnects or metadata fetch timeouts.

Check in order:

1. Is the right profile active?
2. Does `KAFKA_BOOTSTRAP_SERVERS` point to endpoints in the right environment?
3. Can the Pod/VM resolve DNS and reach the bootstrap servers?
4. Do the brokers return `advertised.listeners` that the client can **actually reach**?
5. Is that port configured for PLAINTEXT, SSL, or SASL_SSL?
6. If using TLS, are the CA/hostname and truststore valid?
7. Do broker/group/topic ACLs permit the corresponding operations?

Note: `bootstrap.servers` is only the **initial entry point** for the Kafka client to fetch metadata. Afterward, the client must connect using the broker endpoints in `advertised.listeners`. You can reach a bootstrap broker and still fail to connect to brokers advertised via internal-only hostnames from another network.

### 21.2. SASL Authentication Failed

Possible causes:

- Wrong username/password or JAAS syntax.
- Broker does not support the selected mechanism.
- TLS handshake or hostname validation failed prior to SASL.
- Credentials were rotated, but the Pod still holds the old version.
- Secret mount/configtree path does not exist or filename is wrong.
- Worker can read the secret, but the principal lacks required Kafka ACLs.

Distinguish **authentication** (proving identity) from **authorization** (permission to access topics/groups). A successful login does not mean the consumer can read the topic.

### 21.3. Consumer Sees No Records Even Though Producer Sent Them

Check:

- Are both pointing to the same cluster and topic?
- What is the consumer group ID, and where are its committed offsets?
- How is `auto-offset-reset` applied when no offset exists or offsets are invalid?
- Are partitions actually assigned to the consumer?
- Are deserialization errors occurring before the listener receives data?
- Are multiple Pods/consumers in the same group placing the records on another thread?
- Is the listener error handler retrying/seeking/pausing and stalling a partition?

**Do not immediately reset offsets or change the group ID** before determining the root cause. Those operations can cause replay or drop backlog depending on policy.

### 21.4. Pod Works Locally but Fails in Production

Usually the difference lies in profiles, DNS, truststores, ACLs, or mounted files. Verify final property names via **safe binding tests** without dumping the entire `Environment` to logs. When verifying secrets, check existence, permissions, and source rather than printing raw values.

## 22. Configuration Changes Require Risk-Based Review

Categorize changes so the right reviewers approve them:

| Change Category | Examples | Impact Level |
| --- | --- | --- |
| Observability | Log level, metrics sampling | Usually low, though carries risk of logging sensitive data. |
| Performance | Poll records, concurrency, timeouts | Can increase load/rebalances; requires benchmarking. |
| Reliability | Ack mode, idempotence, retry policy | Requires fault/restart/idempotency testing. |
| Routing | Topic name, DLT, consumer group | Can alter data flow/offsets; high risk. |
| Security | SASL mechanism, credentials, truststore | Can cause outage or secret exposure; requires rotation plan. |
| Cluster migration | Bootstrap servers, DNS, network | Can switch clusters; requires cutover/data plan. |

**Good configuration governance is part of reliability.** ConfigMaps/Helm values should live in reviewed version control; secrets should reside in an audited secret manager; deployments should trace config revisions alongside image revisions.

## 23. Runbook for Deploying a Kafka Configuration Change

| Step | Action | What to Verify |
| --- | --- | --- |
| 1 | Identify target environment | Local/staging/prod and correct namespace/cluster. |
| 2 | Review profile and property sources | No fallback from prod to localhost/PLAINTEXT. |
| 3 | Review topic, group ID, bootstrap servers | Correct cluster, correct data-processing identity. |
| 4 | Review TLS/SASL and secret references | Credentials exist, least-privilege scope, not logged. |
| 5 | Validate ConfigMap and Secret mounts | Configtree files and truststore have exact names/paths. |
| 6 | Test connectivity, ACLs, and data flow in staging | Listener consumes/producer sends; DLT handled per policy. |
| 7 | Roll out gradually | Monitor readiness, rebalances, lag, and auth errors. |
| 8 | Reconcile data post-rollout | No unintended replays, skips, or duplicates outside policy. |
| 9 | Record config version and results | Enables root-cause tracing during incidents. |
| 10 | Prepare rollback | Image, config, and offset-preservation mechanism. |

### Incident Example

~~~text
Time: after prod v1.2.0 rollout
Symptom: consumer receives no records, lag increases
Findings:
  app profile = prod
  cluster endpoint = correct
  group-id = orders-worker-v2 (unintentionally changed)
  auto-offset-reset = none
  group v2 has no committed offsets yet

Root cause:
  Consumer identity changed from v1 to v2 when updating ConfigMap.

Resolution:
  Halt further rollout.
  Evaluate offset policy and data that needs processing.
  Restore the correct v1 group according to plan.
  Rolling update and reconcile records/output.
  Add a review rule for group-id changes.
~~~

In this case, `auto-offset-reset=none` helped catch that the new group ID had no offsets instead of silently skipping data. However, if the business contract genuinely requires creating a new group, you must plan proper offset initialization.

## 24. Hands-on Exercises

### Exercise 1 — Externalize Brokers and Topics

Create a Spring Boot app with `application.yml`, `application-local.yml`, and `application-prod.yml`. Do not hardcode brokers in Java. When running locally, use `localhost:9092`; when running the prod profile without `KAFKA_BOOTSTRAP_SERVERS`, the application must fail per policy.

### Exercise 2 — Type-Safe Configuration

Create `MessagingProperties` with `inputTopic` and `dltTopic` annotated with `@NotBlank`. Use it in a publisher and a `@KafkaListener`. Test binding with test-environment topic names.

### Exercise 3 — `SASL_SSL` from a Config Tree

Use **dummy** secrets in a test directory containing `kafka.jaas.config`. Configure `spring.config.import=configtree:` and verify Spring Boot reads the reference correctly without printing values to logs. Never use real secrets in fixtures.

### Exercise 4 — ConfigMap and Secret

Write manifests so that a ConfigMap supplies broker/topic/group/concurrency while a Secret mounts JAAS/truststore. Explain why updating a Secret in the cluster does not automatically refresh credentials in a running Kafka client.

### Exercise 5 — Detecting Wrong Kafka Groups

Configure two profiles with different groups. Send a batch of messages, inspect committed offsets, and predict behavior when the new group uses `earliest`, `latest`, and `none`. Do not reset offsets on a production cluster.

### Exercise 6 — Testcontainers Kafka

Create an integration test that sends a record via `KafkaTemplate` to a test topic, receives it in a listener, and asserts the business side effect. Inject bootstrap servers dynamically with `@DynamicPropertySource`; do not use production Kafka for tests.

### Exercise 7 — Rebalance and Throughput

Test with partition count 3, replicas 2, and concurrency 1 then 3. Observe how many consumers receive partition assignments, idle threads, throughput, and rebalances. Explain why increasing concurrency does not automatically increase partition count.

### Exercise 8 — Security Rotation

Simulate credentials A and B in a test environment, create a rolling rotation plan, verify new Pods use B, and confirm old Pods close cleanly before revoking A.

### Exercise 9 — Failure Injection

Intentionally misconfigure DNS, SASL mechanism, truststore, or ACLs against a test broker. Classify the failure at the right layer and ensure logs contain no credentials.

### Exercise 10 — Configuration Review

Build an impact table for changing: broker list, group ID, input topic, `enable-auto-commit`, ack mode, `max.poll.interval.ms`, `acks`, idempotence, and SASL. For each change, specify mandatory tests and rollback feasibility.

## 25. Official References

- [Spring Boot — Apache Kafka Support](https://docs.spring.io/spring-boot/reference/messaging/kafka.html)
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
- [Spring Kafka — Reference](https://docs.spring.io/spring-kafka/reference/)
- [Spring Kafka — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html)
- [Spring Kafka — Exactly Once Semantics](https://docs.spring.io/spring-kafka/reference/kafka/exactly-once.html)
- [Apache Kafka — Consumer Configuration](https://kafka.apache.org/documentation/#consumerconfigs)
- [Apache Kafka — Producer Configuration](https://kafka.apache.org/documentation/#producerconfigs)
- [Kubernetes — ConfigMaps](https://kubernetes.io/docs/concepts/configuration/configmap/)
- [Kubernetes — Secrets](https://kubernetes.io/docs/concepts/configuration/secret/)
- [Kubernetes — Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/)
- [Testcontainers — Kafka Module](https://java.testcontainers.org/modules/kafka/)

