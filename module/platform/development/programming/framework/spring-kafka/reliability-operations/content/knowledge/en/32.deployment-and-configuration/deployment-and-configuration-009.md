# Configuring Security in Spring Kafka Reliability Operations

## 1. Why Is Security Part of Reliability?

A Spring Kafka application may run smoothly locally against `localhost:9092`, yet encounter very different failures on staging or production: rejected TLS connections, failed SASL logins, principals lacking topic read permissions, expired certificates, or credential rotations while consumers are actively processing data.

Security failures do more than cause "cannot connect." If an operator responds by **switching to `PLAINTEXT`**, **disabling hostname verification**, **changing consumer groups**, or **pointing to another cluster**, the consequences can be far worse: exposed sensitive data, broken tenant isolation, skipped events, or duplicate data processing.

Within *Deployment and Configuration* of **Spring Kafka Reliability Operations**, "Configuring Security" focuses on integrating Kafka protections into **Spring Boot/Spring Kafka**, aligning them with broker settings, managing secrets, and operating changes safely.

After this lesson, you will be able to:

1. Distinguish **TLS encryption**, **SASL authentication**, **mTLS**, **Kafka ACL/RBAC**, and **network controls**.
2. Configure `security.protocol`, `sasl.mechanism`, `sasl.jaas.config`, and truststores/keystores in Spring Boot.
3. Choose appropriately among `SSL`, `SASL_SSL`, `PLAINTEXT`, and `SASL_PLAINTEXT` by environment.
4. Keep credentials out of source code/JARs using secret managers, mounted secrets, and `configtree:`.
5. Design principals, topic/group ACLs, and DLT publish rights under least privilege.
6. Rotate certificates and passwords via rolling deployments without arbitrarily altering offsets or group identities.
7. Test connectivity, authentication, authorization, TLS, and controlled failure scenarios.
8. Diagnose authentication failures, authorization failures, SSL handshakes, and wrong broker endpoints.

Primary examples use **Java 17+, Spring Boot 3.x, Spring Kafka 3.x**. The principles apply more broadly, though exact property names and APIs must match your Spring Boot BOM, Kafka client, and broker versions.

## 2. End-to-End Kafka Protection Model

A consumer/producer connection traverses multiple layers:

~~~text
                  Spring Kafka Application
                           |
                      Kafka clients
                           |
        +------------------+-------------------+
        |                  |                   |
        v                  v                   v
     Network             TLS               Identity
   DNS / firewall    encryption +        SASL credential
   VPC / policy     server identity      or client cert
        |                  |                   |
        +------------------+-------------------+
                           |
                           v
                        Broker
                           |
                 Authenticate principal
                           |
                           v
                 Authorize Topic / Group
                           |
                           v
                    Read / Write / Commit
                           |
                           v
                   Business processing
                idempotency / auditing
~~~

| Layer | Question to Answer | Mechanisms |
| --- | --- | --- |
| **Network** | Is the client allowed to reach this broker? | Firewalls, security groups, VPC, Kubernetes `NetworkPolicy`, private endpoints. |
| **Encryption in transit** | Is traffic encrypted on the wire? | TLS via `SSL` or `SASL_SSL`. |
| **Server authentication** | Is the client talking to the genuine broker? | Truststore, CA chain, hostname verification. |
| **Client authentication** | How does the broker identify the client? | SASL/SCRAM, SASL/PLAIN, OAuth, mTLS, or provider-specific mechanisms. |
| **Authorization** | Can the principal read/write topics or join groups? | Kafka ACLs, platform RBAC, broker policies. |
| **Application security** | Does the record match tenant/schema rules without duplicate processing? | Validation, idempotency, schema governance, auditing. |
| **Secret lifecycle** | How are credentials issued, rotated, and revoked? | Vault/cloud secret managers, workload identity, RBAC, rotation. |

**TLS, SASL, and ACLs do not replace one another.** A client can complete the TLS handshake yet fail SASL with a wrong password; pass SASL yet lack `Read` rights on a topic; or hold topic rights yet lack `Group` rights.

## 3. Choosing the Right `security.protocol`

Kafka clients support common protocol options:

| `security.protocol` | Connection Encryption | Typical Authentication | When Is It Appropriate? |
| --- | --- | --- | --- |
| `PLAINTEXT` | No | Usually no Kafka-protocol client auth | Only approved isolated local/test environments. |
| `SSL` | Yes | Server TLS; optional **mTLS** when broker requires client certs | Kafka using TLS, commonly mTLS. |
| `SASL_PLAINTEXT` | No | SASL (e.g., SCRAM/PLAIN) without TLS | **Avoid on production networks**; credentials and data lack TLS protection. |
| `SASL_SSL` | Yes | TLS verifies broker + SASL authenticates client | Common choice for SCRAM/PLAIN/OAuth over TLS. |

Common deployment rules:

~~~text
local/test isolated     -> PLAINTEXT (only when approved)
production with SCRAM   -> SASL_SSL
production with mTLS    -> SSL + client certificate
managed Kafka platform  -> per provider (usually TLS + SASL/OAuth/IAM)
~~~

There is no single "universal production config" for every cluster. You must know **which listeners, ports, SASL mechanisms, and CAs the broker exposes**. A Spring Kafka client cannot unilaterally choose an auth method the broker does not support.

### One-Way TLS vs. mTLS

**One-way TLS:** the client verifies the broker's certificate. The broker does not necessarily authenticate the client via certificate; client identity may be verified via SASL.

**mTLS (mutual TLS):** in addition to the client checking the broker certificate, the broker requires a **client certificate**, verifies its chain, and maps the certificate to a principal. Typically uses `security.protocol=SSL` with both a client truststore and keystore.

**Truststore** holds CAs/certificates to trust the remote peer; **keystore** holds the client's own private key and certificate. Never place private keys in a ConfigMap or Git.

## 4. How Is Spring Boot Kafka Security Configuration Loaded?

Spring Boot loads properties from `application.yml`, profiles, environment variables, command-line args, external files, secrets/`configtree`, and additional Config Data imports.

~~~text
application.yml (base configuration)
          |
          +-- application-local.yml
          |
          +-- application-prod.yml
          |
          +-- env / ConfigMap / secret mount
                          |
                          v
                  Spring Environment
                          |
                          v
                  KafkaProperties
                          |
                 +--------+---------+
                 |                  |
                 v                  v
            ConsumerFactory    ProducerFactory
                 |                  |
                 v                  v
           @KafkaListener      KafkaTemplate
~~~

Kafka client properties enter through:

- `spring.kafka.properties.*`: shared Kafka properties, such as `security.protocol`.
- `spring.kafka.consumer.properties.*`: consumer-specific properties.
- `spring.kafka.producer.properties.*`: producer-specific properties.
- `spring.kafka.ssl.*`: Spring Boot-supported SSL properties.
- `spring.kafka.consumer.*`, `spring.kafka.producer.*`, `spring.kafka.listener.*`: Spring Boot typed/shortcut properties.

**Do not confuse `spring.kafka.properties.sasl.jaas.config` with an application property named `app.kafka.*`.** Application namespaces apply only where your code binds and reads them; Kafka client properties must pass into the factories.

### Keeping Dotted Kafka Client Keys Intact

In YAML, keep Kafka client property keys in their native dotted form:

~~~yaml
spring:
  kafka:
    properties:
      security.protocol: SASL_SSL
      sasl.mechanism: SCRAM-SHA-512
~~~

Keys like `sasl.jaas.config`, `ssl.endpoint.identification.algorithm`, and `max.poll.interval.ms` contain dots. When overriding from the environment, put placeholders in the **value** instead of guessing an env var name representing nested map keys:

~~~yaml
spring:
  kafka:
    properties:
      security.protocol: ${KAFKA_SECURITY_PROTOCOL:SASL_SSL}
~~~

For mandatory production settings, avoid dangerous fallbacks like `PLAINTEXT` or `localhost:9092`.

## 5. Practice Environment Setup

Illustrative project layout:

~~~text
secure-orders-worker/
├── build.gradle
└── src/main/
    ├── java/com/example/orders/
    │   ├── SecureOrdersApplication.java
    │   ├── MessagingProperties.java
    │   ├── OrderConsumer.java
    │   └── ResultProducer.java
    └── resources/
        ├── application.yml
        ├── application-local.yml
        └── application-prod.yml

deployment/
├── orders-configmap.yml
└── orders-deployment.yml
~~~

### Dependencies

`build.gradle` for a Spring Boot 3.x project:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.kafka:spring-kafka'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
}
 
tasks.named('test') {
    useJUnitPlatform()
}
~~~

Let Spring Boot dependency management align compatible versions of Spring Kafka and Kafka clients. Never bump Kafka clients alone to an arbitrary version assuming all SASL/TLS/metrics behavior stays compatible.

To stay focused on security, examples use `String` messages; real systems should add serializers, schema validation, record size limits, and input checks.

## 6. Credential-Free Base Configuration

File `src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: secure-orders-worker

  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS}

    client-id: ${KAFKA_CLIENT_ID:secure-orders-worker}

    consumer:
      group-id: ${KAFKA_CONSUMER_GROUP}
      enable-auto-commit: false
      auto-offset-reset: ${KAFKA_AUTO_OFFSET_RESET:none}
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer

    listener:
      ack-mode: record
      concurrency: ${KAFKA_LISTENER_CONCURRENCY:2}

    producer:
      acks: all
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
      properties:
        enable.idempotence: true

app:
  messaging:
    orders-topic: ${KAFKA_ORDERS_TOPIC}
    results-topic: ${KAFKA_RESULTS_TOPIC}
~~~

These values are **externalized** so a single image runs across environments.

| Setting | Role | Reliability Impact |
| --- | --- | --- |
| `bootstrap-servers` | Broker bootstrap endpoints | Wrong cluster can corrupt/mix data, not just drop connections. |
| `group-id` | Consumer group identity | Changing group can replay or skip backlog per offset policy. |
| `enable-auto-commit: false` | Disables Kafka consumer auto-commit | Spring Kafka container manages offset commit timing. |
| `ack-mode: record` | Commits per record processing semantics | Does not create an atomic transaction with external databases. |
| `auto-offset-reset: none` | Does not pick earliest/latest when valid offset is missing | Fails fast for new groups; prevents silent skips/replays. |
| `acks: all` | Producer waits for broker ACKs per ISR | Improves durability when brokers are configured accordingly. |
| `enable.idempotence: true` | Producer deduplicates eligible retry requests within a session | Does not replace app idempotency on consumer redelivery. |

`auto-offset-reset=none` illustrates a cautious production policy. When initializing a new group, maintain an explicit **offset plan**. Security failures must never serve as an excuse to arbitrarily swap `group-id`.

## 7. Local Configuration: `PLAINTEXT` Only in Isolated Environments

File `application-local.yml`:

~~~yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}
    consumer:
      group-id: ${KAFKA_CONSUMER_GROUP:secure-orders-worker-local}
      auto-offset-reset: earliest
    properties:
      security.protocol: PLAINTEXT

app:
  messaging:
    orders-topic: ${KAFKA_ORDERS_TOPIC:orders.events.local}
    results-topic: ${KAFKA_RESULTS_TOPIC:orders.results.local}
~~~

Run locally:

~~~bash
java -jar secure-orders-worker.jar \
  --spring.profiles.active=local
~~~

**Never use the local profile as a production default.** A classic outage occurs when a deployment omits the active profile and falls back to `localhost`/`PLAINTEXT`, leaving the Pod "running cleanly" while consuming nothing or hitting the wrong broker.

Inside Docker, `localhost` refers to that container itself; use the Kafka service DNS on the Docker network rather than defaulting to the host machine.

## 8. Production with SASL/SCRAM over TLS

Suppose the broker is configured with:

- A listener supporting TLS and SASL.
- `SCRAM-SHA-512` enabled.
- A principal with matching credentials and Kafka ACLs.
- A broker certificate trust chain trusted by the client.
- Firewall/network policy permitting the port.

File `application-prod.yml`:

~~~yaml
spring:
  config:
    import: "configtree:/etc/kafka-secrets/"

  kafka:
    properties:
      security.protocol: SASL_SSL
      sasl.mechanism: SCRAM-SHA-512
      sasl.jaas.config: ${kafka.sasl.jaas.config}

    ssl:
      trust-store-location: ${KAFKA_TRUSTSTORE_LOCATION:file:/etc/kafka-certs/truststore.p12}
      trust-store-type: PKCS12
      trust-store-password: ${kafka.truststore.password}
~~~

In this example:

- `security.protocol` selects the broker transport/auth protocol.
- `sasl.mechanism` must match what the broker and principal support.
- `sasl.jaas.config` holds login credentials loaded from a secret file.
- The truststore verifies the broker certificate.
- `configtree:` reads mounted files as configuration properties.
- **Never** let raw JAAS credentials appear in source, Dockerfiles, ConfigMaps, or Git.

Note: truststores depend on broker certificate issuers. If public CAs are already trusted by the JVM and policy does not mandate a custom truststore, the custom truststore block may be optional. When specifying a custom truststore, ensure it contains **all CAs needed** for every target Kafka endpoint.

### 8.1. Separately Provisioned Secret Contents

Inside the Pod:

~~~text
/etc/kafka-secrets/
  kafka.sasl.jaas.config
  kafka.truststore.password

/etc/kafka-certs/
  truststore.p12
~~~

Spring Boot `configtree:` treats each filename as a property key; `kafka.sasl.jaas.config` supplies `${kafka.sasl.jaas.config}`. Operators must mount exact filenames and paths.

**Example JAAS syntax with placeholders—NO real credentials:**

~~~text
org.apache.kafka.common.security.scram.ScramLoginModule required
username="example-orders-worker"
password="REPLACE_WITH_SECRET";
~~~

In real mounted files, this is stored as a valid JAAS configuration string. Real usernames and passwords come from secret-management workflows and must never be copied into docs, logs, or tickets.

### 8.2. About `SCRAM-SHA-512`

SCRAM provides challenge-response authentication between client and broker; the broker needs matching SCRAM credentials provisioned. However:

- SCRAM **does not replace TLS** for record encryption or MITM protection.
- A valid client config does not automatically create a SCRAM account on the broker.
- If the principal exists but lacks ACLs, SASL succeeds while consume/produce still fails.
- If the broker supports only `SCRAM-SHA-256` or `PLAIN`, use the approved matching mechanism.

### 8.3. Never Disable Hostname Verification

Kafka TLS clients typically use `ssl.endpoint.identification.algorithm=https` to verify the broker hostname against its certificate, depending on client version/config.

**Never set it to an empty string** merely to bypass a certificate hostname mismatch. That weakens server authentication and opens the door to MITM attacks.

Fix the root cause: certificate SAN/CN, broker DNS, `advertised.listeners`, trust chain, or actual endpoint hostname.

## 9. When to Use SASL/PLAIN, OAuth, or IAM?

| Mechanism | High-Level Operation | Notes |
| --- | --- | --- |
| `SCRAM-SHA-256` / `SCRAM-SHA-512` | Username/password with challenge-response | Pair with TLS, credential rotation, and ACLs. |
| `PLAIN` | Username/password over SASL | **Must rely on TLS per production security policy**, since PLAIN does not encrypt passwords itself. |
| `OAUTHBEARER` | Tokens issued by an identity provider | Requires login callback/token refresh and matching issuer/audience/TTL. |
| Cloud-specific IAM/OAuth | Workload identity credentials or callback/provider plugin | Requires Kafka client plugin/config per provider docs. |
| mTLS | Client certificate/private key | Authorizes via certificate principal with CA/rotation management. |

Never assume switching `sasl.mechanism` to `OAUTHBEARER` is enough on its own. Many platforms require specific `sasl.login.callback.handler.class`, login modules, or plugins. Likewise, AWS IAM authentication does not share SCRAM's JAAS configuration.

On cloud-managed Kafka, consult **your exact provider and version documentation** to pick the auth mechanism. Avoid static passwords in properties when the platform supports short-lived workload identities.

## 10. Production with Mutual TLS

When brokers require client certificates, the client uses TLS with a keystore holding the workload's certificate and private key:

~~~text
Spring Kafka consumer
   |
   | TLS ClientHello
   v
Kafka broker certificate ---> client checks truststore, SAN/hostname
   |
   | Server requests client certificate
   v
Client certificate + proof private key
   |
   v
Broker verifies CA cert and maps principal
   |
   v
ACL/RBAC for topic/group
~~~

**Alternative** profile example for mTLS (do not apply simultaneously as a random override on top of SCRAM config):

~~~yaml
spring:
  kafka:
    properties:
      security.protocol: SSL

    ssl:
      trust-store-location: file:/etc/kafka-certs/truststore.p12
      trust-store-type: PKCS12
      trust-store-password: ${kafka.truststore.password}

      key-store-location: file:/etc/kafka-certs/client-keystore.p12
      key-store-type: PKCS12
      key-store-password: ${kafka.keystore.password}
      key-password: ${kafka.key.password}
~~~

`${kafka.*.password}` placeholders load from `configtree`/secret providers just like SASL. This uses **PKCS12**; some organizations use PEM or other key formats—match your client config accordingly.

Note that mTLS involves **broker configuration as well**. Brokers must enable an `SSL` listener and require/verify client certificates; if the broker does not request client certs, you only get one-way TLS. The client cannot force broker-side client verification on its own.

**Never store private keys in a ConfigMap.** Public certificates alone may be less sensitive yet still governed by policy; keystores containing private keys are secrets.

## 11. Transport Security Is Not Enough: Authorization Is Required

After authentication succeeds, the Kafka broker identifies the principal to enforce **ACLs** or RBAC. Permissions bind a **resource type** (Topic, Group, Cluster, TransactionalId, etc.) and an **operation** (Read, Write, Describe, etc.).

### 11.1. Separating Producer and Consumer Principals

For critical systems, create two distinct workload identities:

~~~text
orders-consumer-principal
    |
    +-- READ orders.events.v1
    +-- READ consumer group orders-worker-v1
    +-- no WRITE to unrelated topics

orders-result-producer-principal
    |
    +-- WRITE orders.results.v1
    +-- no READ to orders.events.v1
    +-- no access to unrelated groups
~~~

If the same JVM uses one credential set for both producer and consumer, its principal needs the union of rights; that is simpler but widens blast radius on compromise. Separating workloads allows stricter least privilege.

### 11.2. Illustrative Permission Requirements

| Operation | Typical Kafka Permissions Needed | Additional Checks |
| --- | --- | --- |
| Consume from topic | `Read` on Topic; `Read` on Group, plus describe rights depending on broker | Topic exists, group authorized, valid offsets. |
| Produce to topic | `Write` on Topic; possibly `Describe` or related rights | Quotas/ACLs, acks, retention. |
| Publish to DLT | `Write` on DLT topic | Valid error handler/recoverer, matching serializer, and ACLs. |
| Use transactional producer | Matching rights on `TransactionalId` and topics | `transactionIdPrefix` and broker transaction support. |
| Idempotent producer | Idempotent-write rights per Kafka broker/version | `acks=all`, idempotence, and compatible client configs. |
| Create/alter topics | `Create`/`Alter` per policy | Reserve for admin/IaC rather than granting to apps by default. |
| Inspect cluster metadata | `Describe` or related rights | Never grant `Cluster All` to ordinary clients. |

Exact permissions depend on broker version, authorizer, and provider. **Never copy-paste a "full access" ACL template.** Verify least privilege via real auth/authorization tests and Kafka cluster audit logs.

### 11.3. Sample ACLs via Kafka CLI

The snippet below **contains no usernames/passwords** and applies only with a compatible Apache Kafka authorizer/CLI:

~~~bash
# Assume principal User:orders-consumer already exists.
kafka-acls.sh --bootstrap-server broker-admin.example.internal:9093 \
  --add --allow-principal User:orders-consumer \
  --operation Read --topic orders.events.v1

kafka-acls.sh --bootstrap-server broker-admin.example.internal:9093 \
  --add --allow-principal User:orders-consumer \
  --operation Read --group orders-worker-v1

# Producer is granted Write on the results topic.
kafka-acls.sh --bootstrap-server broker-admin.example.internal:9093 \
  --add --allow-principal User:orders-producer \
  --operation Write --topic orders.results.v1
~~~

**These illustrate ACL permissions, not a recipe to run directly against production.** Admin CLIs also need `--command-config` or broker auth settings and must follow approval/Infrastructure-as-Code workflows. Never pass raw passwords on the command line.

Group permissions can target exact names or controlled prefixes. Wildcards or broad prefixes easily grant unintended access, especially when principals span multiple tenants.

## 12. Consumer Group Identity and Permissions

Consumers need both topic and group permissions. A classic error:

~~~text
SASL handshake: SUCCESS
Topic metadata: SUCCESS
JoinGroup: GroupAuthorizationException
~~~

This means the broker authenticated the principal and topic permissions may even be valid, yet **the `group-id` lacks Read permission**. Changing `group-id` to another name just to "be allowed to join" is dangerous because consumer group identity governs committed offsets.

~~~text
group-id = orders-worker-v1
  committed offset partition 0: 2000

change group-id = orders-worker-v2
  no committed offsets yet
       |
       +-- earliest -> may replay a large volume of records
       +-- latest   -> may skip existing backlog
       +-- none     -> throws error because no valid offset exists
~~~

Proper fix: verify the principal, group ACL, and topic ACL. If business logic genuinely requires switching groups, execute an offset migration/cutover plan with idempotency testing and reconciliation.

## 13. Do Not Grant Admin Rights to Applications Just to Silence Errors

In some setups, applications use `NewTopic`/`KafkaAdmin` to auto-create topics. Once ACLs are enforced, startup fails because the principal lacks `Create` permissions.

Never resolve this by granting `All` on the Cluster or all Topics. Safer choices:

1. Manage topics, partitions, replication, retention, and ACLs via Terraform/Strimzi/GitOps/Kafka admin.
2. Give applications only the `Read`/`Write` permissions they need.
3. Disable or constrain auto-creation if disallowed in production.
4. Ensure missing topics fail visibly and trigger alerts in tests.
5. If self-provisioning is truly necessary, grant narrowly scoped rights with full auditing.

Changing broker security policy belongs to infrastructure delivery, distinct from processing business messages.

## 14. Secrets Must Never Live in Source Code or Images

The following patterns easily leak secrets:

~~~text
BAD:
  application-prod.yml contains real password
  Dockerfile: ENV KAFKA_PASSWORD=...
  java -jar worker.jar --spring.kafka.properties.sasl.jaas.config="..."
  Helm values.yaml commits raw JAAS credentials
  CI logs print all environment variables
  REST debug endpoint returns all KafkaProperties
~~~

Even when values are Base64-encoded inside Kubernetes Secret manifests, **Base64 is not encryption**. If a secret file was committed to Git, adding `.gitignore` later does not scrub history; revoke/rotate the secret and handle history per policy.

### Secret Delivery Channels

| Channel | Usage | Things to Verify |
| --- | --- | --- |
| Vault | Workload identity fetches secrets or mounts via agent | Lease/TTL, policies, auditing, rotation. |
| AWS Secrets Manager | Pod/VM uses IAM role/workload identity | Least-privilege scope per secret ARN. |
| Google Cloud Secret Manager | Workload identity fetches versioned secrets | IAM, auditing, namespace/project boundaries. |
| Azure Key Vault | Managed identity retrieves credentials/certificates | Roles/permissions and rotation. |
| Kubernetes Secret | File mount or env injection | etcd encryption, Kubernetes RBAC, node/Pod permissions. |
| External Secrets Operator/CSI | Syncs secrets from provider into files/mounts | Sync/refresh does not equal Kafka client reload. |

`configtree:/etc/kafka-secrets/` is a practical Spring Boot approach: app config stays in Git while secret values arrive via a protected filesystem mount.

### Why Mounted Secrets Alone Do Not Solve the Full Lifecycle

Kafka clients typically read JAAS configs, keystores, or callback handlers **at initialization time**. If mounted files update during rotation:

- Files on disk may already reflect the new value.
- The `Spring Environment` or previously created Kafka clients **do not necessarily reload automatically**.
- Active connections may continue using old credentials or certificates.
- Producers/consumers may require restarts or recreating factories/containers.

Never assume hot reload works merely because Kubernetes updates a projected Secret volume. Tested rolling restarts/refreshes are far more predictable.

## 15. Kubernetes: Separating ConfigMap and Secret

Deployment diagram:

~~~text
GitOps:
  orders-kafka-config (ConfigMap)
       | -- KAFKA_BOOTSTRAP_SERVERS
       | -- KAFKA_CONSUMER_GROUP
       | -- KAFKA_ORDERS_TOPIC
       | -- KAFKA_RESULTS_TOPIC
       v
  Deployment
       |
       +-- envFrom ConfigMap
       |
       +-- Secret volume: kafka.jaas.config
       +-- Secret volume: kafka.truststore.password
       +-- Secret volume: truststore.p12
                 |
                 v
           Spring Boot configtree
                 |
                 v
            SASL_SSL clients
~~~

### 15.1. ConfigMaps Contain No Credentials

File `deployment/orders-configmap.yml`:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: secure-orders-kafka-settings
data:
  KAFKA_BOOTSTRAP_SERVERS: "broker-1.prod.example.internal:9093,broker-2.prod.example.internal:9093"
  KAFKA_CONSUMER_GROUP: "orders-worker-v1"
  KAFKA_CLIENT_ID: "orders-worker"
  KAFKA_ORDERS_TOPIC: "orders.events.v1"
  KAFKA_RESULTS_TOPIC: "orders.results.v1"
  KAFKA_AUTO_OFFSET_RESET: "none"
  KAFKA_LISTENER_CONCURRENCY: "2"
~~~

These addresses and topic names are **illustrative**. They are not live endpoints.

### 15.2. Deployment Mounting Separately Provisioned Secrets

File `deployment/orders-deployment.yml`:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: secure-orders-worker
spec:
  replicas: 2
  selector:
    matchLabels:
      app: secure-orders-worker
  template:
    metadata:
      labels:
        app: secure-orders-worker
    spec:
      containers:
        - name: worker
          image: registry.example.org/secure-orders-worker:1.0.0
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: prod
          envFrom:
            - configMapRef:
                name: secure-orders-kafka-settings
          volumeMounts:
            - name: kafka-auth
              mountPath: /etc/kafka-secrets
              readOnly: true
            - name: kafka-certs
              mountPath: /etc/kafka-certs
              readOnly: true
      volumes:
        - name: kafka-auth
          secret:
            secretName: secure-orders-kafka-auth
            items:
              - key: jaas-config
                path: kafka.sasl.jaas.config
              - key: truststore-password
                path: kafka.truststore.password
        - name: kafka-certs
          secret:
            secretName: secure-orders-kafka-truststore
            items:
              - key: truststore.p12
                path: truststore.p12
~~~

**Note:** the manifest above does not create the two credential Secrets. They must be pre-provisioned through a separate security workflow. Production deployments also require resource requests/limits, probes, service accounts, RBAC, network policies, rollout policies, and log management.

### 15.3. Pod Secret Access

Ensure:

- Only authorized workloads/namespaces can read the Secrets.
- Pods and containers do not run with broader privileges than required.
- Secret volumes mount read-only with strict filesystem permissions.
- Service accounts lack broad `list`/`get` Secret permissions unless required.
- etcd and backups are encrypted and access-controlled per cluster standards.
- Unauthorized users cannot `kubectl exec` or debug into Pods holding secrets.
- Diagnostic collectors never copy secret files into build artifacts or logs.

Kubernetes Secrets are distinct from Kafka ACLs: permission to read a Kubernetes Secret **does not prove** Kafka principal permissions, and Kafka ACLs do not restrict who reads a Secret resource if Kubernetes RBAC is misconfigured.

## 16. Networking and Broker Endpoints Are Also Security Components

In Kafka, `bootstrap.servers` is only the initial entry point to fetch metadata. Clients then connect directly to the broker endpoints returned in `advertised.listeners`.

~~~text
Application
   |
   | bootstrap: kafka-bootstrap.example:9093
   v
Bootstrap broker
   |
   | metadata includes:
   | broker1.internal.example:9093
   | broker2.internal.example:9093
   v
Client connects directly to returned broker endpoints
~~~

If clients outside an internal network cannot resolve the hostnames advertised by brokers, the app can:

- Pass TLS bootstrap yet fail to read or write messages.
- Hit continuous timeouts/reconnects.
- Report hostname mismatch on child broker certificates.
- Look like a "wrong Kafka password" when the root cause is DNS/listener configuration.

Check:

1. DNS resolution from inside the actual Pod/VM.
2. Network routes, firewalls, security groups, and Kubernetes `NetworkPolicy`.
3. Port/protocol matching the listener: `SSL` vs. `SASL_SSL`.
4. Certificate SANs covering both bootstrap and advertised broker endpoints.
5. Broker `advertised.listeners` returning hostnames reachable by clients.
6. Kafka ACLs once networking and auth succeed.

**Never disable certificate validation to "fix" a DNS or `advertised.listeners` issue.**

## 17. Should Producer and Consumer Share Security Settings or Differ?

Spring Boot's `spring.kafka.properties` applies broadly per Boot config rules; role-specific settings go under:

~~~yaml
spring:
  kafka:
    properties:
      security.protocol: SASL_SSL

    consumer:
      properties:
        # Consumer-specific Kafka client properties.
        max.poll.interval.ms: 300000

    producer:
      properties:
        # Producer-specific Kafka client properties.
        delivery.timeout.ms: 120000
~~~

In many systems, consumers and producers authenticate with the same principal. When permissions must be separated:

- Give each Kafka client factory its own credentials/JAAS config.
- Separate `ConsumerFactory` and `ProducerFactory` with distinct property maps.
- When creating factories manually, copy SSL/SASL settings properly from `KafkaProperties` or explicit mappings; **never drop security properties**.
- Check whether admin clients (`KafkaAdmin`) need separate credentials.
- If using Kafka Streams, Schema Registry, Connect, or REST Proxy, each component has **its own** security config and does not automatically inherit all `spring.kafka` properties.

Do not confuse `spring.kafka.consumer.properties.sasl.jaas.config` with `spring.kafka.properties.sasl.jaas.config`; the former applies only to consumers. A common failure is consumers connecting cleanly while the DLT publisher fails because the producer lacks credentials.

## 18. `KafkaTemplate`, Listeners, and Security Configuration

Spring Boot auto-configuration builds `ConsumerFactory`, `ProducerFactory`, `KafkaTemplate`, and listener containers from bound properties.

A simple consumer:

~~~java
package com.example.orders;

import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderConsumer {

    @KafkaListener(topics = "${app.messaging.orders-topic}")
    public void handle(String payload) {
        // Parse, validate schema, check business key, and process idempotently.
        // Exceptions pass to the error handler per app policy.
    }
}
~~~

Producer:

~~~java
package com.example.orders;

import java.util.concurrent.CompletableFuture;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Component;

@Component
public class ResultProducer {

    private final KafkaTemplate<String, String> kafka;
    private final MessagingProperties messaging;

    public ResultProducer(
            KafkaTemplate<String, String> kafka,
            MessagingProperties messaging) {
        this.kafka = kafka;
        this.messaging = messaging;
    }

    public CompletableFuture<SendResult<String, String>> publish(
            String orderId, String resultJson) {

        return kafka.send(
                messaging.resultsTopic(), orderId, resultJson);
    }
}
~~~

Property binding:

~~~java
package com.example.orders;

import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.messaging")
public record MessagingProperties(
        @NotBlank String ordersTopic,
        @NotBlank String resultsTopic) {
}
~~~

On the `@SpringBootApplication` class, add `@ConfigurationPropertiesScan` so record properties register cleanly. `orders-topic` in YAML binds to `ordersTopic` via Boot's relaxed binding.

**Important:** Spring Kafka cannot fix broken broker ACLs in listener code. These classes rely on the credentials and permissions defined by `spring.kafka.*` and broker provisioning.

`KafkaTemplate.send` returns a future; a send is **not durable merely because the method returned**. Handle completion/failure callbacks properly and avoid logging payloads containing sensitive data.

## 19. Never Put Secrets in `JobParameters`, Headers, or Payloads for Debugging

Even with Kafka TLS enabled, data can still surface in:

- Producer/consumer logs.
- DLT payloads and error headers.
- Application traces or monitoring backends.
- Record keys, topic names, headers, and message bodies.
- Output databases or state stores.
- Kafka broker or downstream service backups.

A header such as:

~~~text
Authorization: Bearer <raw-access-token>
~~~

must never be placed inside Kafka messages for "another worker to reuse." A consumer authorized to read a topic via ACL may not be authorized to hold external system credentials. If a downstream step needs a token, resolve that workload's own credentials through the secret manager.

### Error Handlers and DLT

When a record fails, `DefaultErrorHandler`/`DeadLetterPublishingRecoverer` (or retry-topic mechanisms) can route the record to a DLT per policy. Ensure:

- The producer principal holds `Write` on the DLT topic.
- The DLT topic has proper retention, ACLs, and encryption at rest.
- Error headers never expose passwords, tokens, or sensitive exception messages.
- DLT/quarantine consumers have tight permissions, access auditing, and clear replay workflows.
- Never treat the DLT as a safe place to dump raw requests containing secrets.

Adding a DLT name to YAML **does not automatically create** an error handler or DLT publish rights; configure recovery logic explicitly.

## 20. Safe Credential Rotation

A typical rotation lifecycle requires an **overlap window** accepting both old and new credentials when supported by the platform.

~~~text
T0  Broker accepts credential A
 |
T1  Provision credential B and equivalent ACLs
 |
T2  Update Secret/secret manager for B
 |
T3  Rolling Deployment: new Pods use B
 |
T4  Verify producers/consumers on new Pods work
 |
T5  Old Pods using A drain and stop
 |
T6  Revoke credential A, check audit and auth errors
~~~

If the broker does not allow simultaneous credentials or policy mandates immediate revocation, schedule an appropriate maintenance window or transition strategy.

### SASL Password Rotation

- Never print `sasl.jaas.config` during checks.
- Verify principal B has the **exact required ACL set**, no broader.
- Never alter `group-id` to help new Pods join faster.
- Watch consumer lag, rebalances, authentication failures, and producer send errors.
- Stop old consumers cleanly so overlapping workloads do not trigger non-idempotent downstream actions.

### Certificate Rotation

- New CAs may need to be added to truststores **before** brokers switch to certificates signed by the new CA.
- When replacing broker certificates, SANs must match every client-facing endpoint.
- When replacing mTLS client certificates, broker principal mapping (e.g., subject DN) may change, breaking old ACLs.
- New keystore/truststore passwords must stay in sync with mounted files.
- Kafka clients may require restarts to load updated key material.

### Emergency Revocation

If a secret may be compromised, prioritize revocation/rotation per incident response. Still plan carefully so the entire consumer group does not lose access simultaneously. Never keep a compromised credential alive merely out of fear of rebalances; execute a recovery plan protecting both security and data.

## 21. Rollouts and Incident Control for Security Changes

Security settings are **runtime configuration**, yet Java Kafka clients do not automatically refresh all properties when `ConfigMap`/`Secret` objects change.

A practical rollout workflow:

1. Identify old and new config/secret versions, target environment, and blast radius.
2. Validate secrets/protocols via integration tests or a production-equivalent staging cluster.
3. Provision broker principals, ACLs, and trust anchors before rolling out clients.
4. Update ConfigMaps/Secrets via versioned GitOps/secret management workflows.
5. Rolling-deploy new Pods so Kafka clients load the updated config.
6. Monitor readiness, auth/authorization failures, consumer membership, lag, and producer ACKs.
7. Reconcile side effects after rebalances/redeliveries (DB, APIs, audits).
8. Once new Pods stabilize, terminate old Pods and revoke old credentials.
9. Record change records, config versions, and rollback steps.

**Rollbacks involve broker state too.** If credential A was already revoked, rolling new Pods back to an old image/config using A will fail. Sequence broker/client changes and transition windows explicitly in the runbook.

### Consumer Shutdown and Rebalances

Rolling deployments trigger consumer group rebalances or partition ownership handoffs. A record may commit to the DB right before a Pod shuts down without committing its Kafka offset, causing redelivery.

~~~text
Consumer A processes event X
   |
   v
DB commit succeeds
   |
   v
Pod stops before offset commit
   |
   v
Consumer B receives event X again
```

SASL/TLS protects the transport; **it does not provide exactly-once guarantees for external databases**. Use idempotency keys, unique constraints, transactional outboxes, or matching consistency strategies.

## 22. Security Observability: What to Monitor?

A Spring Kafka production dashboard should track both connectivity and business signals:

| Signal | Meaning |
| --- | --- |
| Authentication failures | Wrong credentials, mechanism, rotation mismatch, or broker login errors. |
| SSL handshake errors | Trust chain, hostname, certificate expiry, or protocol mismatch. |
| Authorization exceptions | Principal lacks topic, group, or transactional ID permissions. |
| Consumer group lag | Consumer stalling or insufficient throughput. |
| Consumer group member count | Are Pods actually joining the right group? |
| Rebalance rate | Are rollouts, timeouts, or crashes destabilizing the group? |
| Producer send errors/timeouts | Broker ACK, ACL, connectivity, or quota issues. |
| DLT publish failures | Does the recovery path have permissions and connectivity? |
| Secret/certificate expiry | Are rotations needed before expiration? |
| Business throughput/idempotency failures | Are records processing cleanly or duplicating/skipping? |

**Never assume HTTP health `200` means Kafka is authenticated and consumers hold partition assignments.** Spring Boot provides health indicators depending on dependencies/config, yet no default check proves the full consumer group and business outputs are healthy.

### Safe Logging

Record useful diagnostic fields:

~~~text
service=secure-orders-worker
environment=production
clientId=orders-worker
groupId=orders-worker-v1
topic=orders.events.v1
authProtocol=SASL_SSL
errorCategory=authorization_failed
deploymentRevision=1.0.0
~~~

Never print:

~~~text
sasl.jaas.config
password
oauth access token
private key
keystore content
complete Spring Environment
HTTP Authorization header
full payload if it contains secrets or personal data
~~~

If exceptions or Kafka client debug logs expose sensitive values, review log redaction and backend log access controls. Never leave debug logging enabled long-term in production merely to troubleshoot a connectivity issue.

## 23. Diagnosing TLS Errors

### 23.1. `SSLHandshakeException` or `PKIX path building failed`

Common causes:

- Truststore lacks the CA that signed the broker certificate.
- Expired certificate or incomplete chain.
- Keystore/truststore failed to load due to wrong path, password, or type.
- Client pointed at a non-TLS port.
- JVM lacks TLS version/ciphers required by the broker.
- Proxy or SSL interception altered the certificate chain.

Procedure:

1. Read the **error category**, without printing raw secrets.
2. Confirm `security.protocol` and the Kafka listener port.
3. Verify DNS and the broker certificate chain using approved TLS inspection tools.
4. Check truststore path/type/password **by load outcome**, without printing passwords.
5. Check system clock skew and certificate validity dates.
6. Match certificate SAN hostnames against advertised broker endpoints.
7. Update truststores/certificates properly, roll out, and measure.

Never disable TLS or hostname verification to make tests turn green.

### 23.2. Hostname Verification Failed

If a broker certificate lists only `broker-1.example.internal` while the client connects via an IP or unlisted DNS alias, the handshake can be rejected.

**Proper fix:** align certificate SANs, DNS aliases, or `advertised.listeners` so endpoints match the certificate. Avoid setting `ssl.endpoint.identification.algorithm` to an empty string.

### 23.3. Client Certificate Rejected

For mTLS, verify:

- Is the broker configured to require client certificates?
- Does the client keystore hold the right private key and certificate chain?
- Is the client cert unexpired and trusted by the broker?
- Did principal mapping based on subject/SAN change?
- Does the mapped principal have the right Kafka ACLs?

An mTLS handshake can succeed while ACLs still fail if principal mapping changed after certificate rotation.

## 24. Diagnosing SASL and ACL Errors

| Symptom | Likely Layer | Hint |
| --- | --- | --- |
| `SaslAuthenticationException` | Authentication | Username/password, mechanism, JAAS syntax, credential rotation. |
| SSL error before SASL | TLS | Truststore, cert, hostname, protocol/port. |
| `TopicAuthorizationException` | Topic Authorization | Kafka `Read`/`Write` ACLs for principal and topic. |
| `GroupAuthorizationException` | Group Authorization | Group ID, ACL; never change group arbitrarily. |
| `ClusterAuthorizationException` | Cluster Authorization | API requests cluster-level rights; evaluate necessity. |
| Transactional producer rejected | TransactionalId/Topic ACL | Permissions, `transactional.id`, and broker policy. |
| DLT publisher permission error | DLT Authorization | Does the producer principal have `Write` on DLT? |
| Continuous reconnects | Network/TLS/Auth | DNS, bootstrap vs. `advertised.listeners`, cert/JAAS. |
| Consumer gets no partitions | Group assignment/Topic | Consumer count, partitions, group, and subscription. |
| Consumer receives no records | Offsets/Topic/Error handling | Do not blame security for every issue. |

### Distinguishing Authentication and Authorization

~~~text
Authentication:
    "Who are you?"
    -> SASL challenge-response / mTLS client certificate

Authorization:
    "What is this identity allowed to do?"
    -> Topic Read / Write, Group Read, TransactionalId, ...
~~~

A principal with the right password but missing ACLs needs **the exact missing permission** granted via Kafka admin procedures. Never "fix" it by creating another password, changing topics, resetting offsets, or disabling TLS.

### When Brokers Are Unreachable from a Pod

The fault may lie outside client security. Check:

~~~bash
# From an environment permitted to test connectivity:
nslookup broker-1.prod.example.internal

# Check port from an authorized test host.
# Depending on Linux distro, you can use:
nc -vz broker-1.prod.example.internal 9093
~~~

These two commands test DNS/TCP only; **they do not prove SASL/TLS/ACLs work**. Stronger probe tools must use secure client configs without passing raw credentials on the command line or saving them in shell history.

## 25. Testing Security Configuration

Goals are proving that:

- Property binding picks up the right protocol, mechanism, and topics.
- Production fails startup if mandatory secrets/paths are missing.
- Real clients complete TLS and SASL handshakes against a test broker.
- Principals hold **exact required permissions**, no more.
- Rotating credentials/certs per runbook causes no skipped or duplicated records.
- Logs/metrics contain no credentials.

Separate test layers instead of building a single monolithic test.

### 25.1. Binding Tests with Spring Boot

Write a unit test for the application namespace:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.mock.env.MockEnvironment;

import static org.junit.jupiter.api.Assertions.*;

class MessagingPropertiesBindingTest {

    @Test
    void bindsTopicsFromExternalConfiguration() {
        MockEnvironment env = new MockEnvironment()
                .withProperty(
                    "app.messaging.orders-topic", "orders.events.test")
                .withProperty(
                    "app.messaging.results-topic", "orders.results.test");

        MessagingProperties props = Binder.get(env)
                .bind(
                    "app.messaging",
                    Bindable.of(MessagingProperties.class))
                .orElseThrow();

        assertEquals("orders.events.test", props.ordersTopic());
        assertEquals("orders.results.test", props.resultsTopic());
    }
}
~~~

This verifies binding only; it does **not** initialize Kafka clients or perform handshakes. To test `@NotBlank`, use a Spring context with validation enabled or invoke a `Validator` explicitly.

### 25.2. Failing Startup When Production Secrets Are Missing

Boot a Spring Boot test context with the `prod` profile while intentionally omitting `/etc/kafka-secrets/`. Because:

~~~yaml
spring:
  config:
    import: "configtree:/etc/kafka-secrets/"
~~~

omits `optional:`, missing that mandatory directory must fail startup. This validates configuration safety, though it does not prove the credentials inside are valid.

If the test runner lacks this path, point a test profile to a dedicated test `configtree` directory rather than mounting production secrets onto developer machines.

### 25.3. Broker Integration Tests with Real SASL/TLS

Default `@EmbeddedKafka` or Kafka Testcontainers setups typically run **without SASL/TLS**. Testing producers/consumers over `PLAINTEXT` proves message flow only, not that production security works.

A genuine security integration test needs:

1. A test broker exposing TLS/SASL listeners matching production, with test certificates and test credentials.
2. Provisioned test principals and corresponding Kafka ACLs.
3. A Spring context receiving bootstrap servers and `configtree`/secret paths via test profile.
4. Producer connecting, sending records, and awaiting ACKs.
5. Consumer in the right group receiving and processing records.
6. Negative tests with wrong password, wrong CA, and missing topic/group ACLs.
7. Verification that test logs and reports print zero credentials.

Use Testcontainers configured with a secured Kafka broker image or a dedicated staging/test cluster for security integration. Never cite a default `PLAINTEXT` Kafka container as proof that `SASL_SSL` was tested.

### 25.4. Testing Negative Scenarios

| Scenario | Expected Outcome |
| --- | --- |
| Missing `KAFKA_BOOTSTRAP_SERVERS` in prod | Context fails readiness or validation cleanly. |
| Missing mandatory `configtree` directory | Config import fails before the app operates. |
| Wrong JAAS username/password | Authentication fails without logging raw secrets. |
| Untrusted broker certificate | TLS handshake fails. |
| SAN hostname mismatch | Hostname verification rejects connection. |
| Consumer lacks Topic Read | Topic authorization fails. |
| Consumer lacks Group Read | Group authorization fails. |
| Producer lacks Write | Publish fails; future reports error. |
| DLT producer lacks rights | Recoverer publish fails with alert. |
| Secret rotated, new Pod uses B | Traffic continues; offsets and side effects reconcile cleanly. |
| Principal tries reading another topic | Rejected per least privilege. |

Never run negative security tests with production credentials or mutate ACLs on a cluster serving live business traffic.

## 26. Type-Safe Validation and Fail-Safe Deployment

Validate critical preconditions **before the application serves traffic**:

- Active profile matches environment; prod never runs `PLAINTEXT` outside policy.
- `bootstrap-servers` is non-empty and never defaults to `localhost`.
- `sasl.mechanism` aligns with `security.protocol`.
- Topic/group IDs are non-blank and follow naming conventions.
- Required secret files exist with proper read permissions.
- Certificates are unexpired and hostnames match.
- Principals hold required Kafka rights, never broad admin rights.
- `auto-offset-reset` and group ID follow an offset plan for new groups.
- Producer settings do not contradict `acks`/idempotence requirements.
- `/actuator/env` is never exposed and raw `KafkaProperties` are never dumped.

`@ConfigurationProperties` with Bean Validation catches missing/malformed app settings. Deployment preflights or integration tests must catch TLS/ACL errors. Never assume YAML binding means Kafka clients authenticated successfully.

### Security Considerations for Kubernetes Probes

Readiness probes typically only check whether the HTTP server responds. A probe can report `Ready` while consumers hold no partitions or producers fail to send. Combine readiness with business-appropriate Kafka connectivity/group-assignment signals without creating continuous restart loops during brief broker blips.

Liveness probes must not react to authentication failures by killing/restarting Pods endlessly: if a secret or ACL is wrong, restarts will not cure the root cause. Monitoring and alerts must surface the configuration error and remediation path.

## 27. Security Does Not Automatically Solve Duplicate Messages

Even with TLS, SASL, and ACLs enabled:

~~~text
Kafka partition: record offset 250
          |
          v
Consumer authenticated + authorized
          |
          v
Business DB commit succeeds
          |
          X process dies before offset commit
          |
          v
Record offset 250 is redelivered
          |
          v
New consumer reprocesses it
~~~

You still need:

- Proper unique business keys/idempotency keys.
- Explicit transaction boundaries.
- Transactional outboxes or consistency patterns when producing after DB commits.
- Category-based retry/backoff/DLT handling.
- Auditing of critical side effects.
- Post-rotation and post-rolling-deployment reconciliation.

Kafka producer `enable.idempotence=true` does not make consumer business requests exactly-once. Kafka transactions carry specific scope guarantees; side effects outside Kafka transactions need separate consistency mechanisms.

## 28. Kafka Security Deployment Runbook

| Step | Action | Expected Outcome |
| --- | --- | --- |
| 1 | Verify cluster, environment, and listener endpoints | Never target wrong staging/prod cluster or port. |
| 2 | Lock auth mechanism: SCRAM, mTLS, OAuth/IAM | Client and broker support matching protocol. |
| 3 | Provision principals/credentials/certs via approved system | Zero raw secrets in Git or JARs. |
| 4 | Grant least-privilege topic/group/transaction/DLT ACLs | Producers and consumers hold exact needed rights. |
| 5 | Configure ConfigMap + secret mounts/`configtree` | `spring.kafka.*` receives right values/paths. |
| 6 | Verify TLS chain and hostnames | Hostname verification stays enabled. |
| 7 | Test on security-equivalent staging/test broker | Positive and negative auth/authorization tests pass. |
| 8 | Roll out gradually | Monitor lag, rebalances, and producer send errors. |
| 9 | Reconcile data and audits | No policy-violating duplicates or data loss. |
| 10 | Revoke old credentials after cutover | Rotation finishes with zero outage. |
| 11 | Record runbook, config version, and cert expiry schedule | Prepared for the next rotation cycle. |

### Incident Example: TLS Works, Group ACL Missing

~~~text
Time: after production deployment
Spring application: STARTED
TLS: handshake succeeded
SASL: authentication succeeded
Kafka: GroupAuthorizationException
Consumer lag: increasing
Producer: unaffected

Root cause:
  principal orders-consumer is allowed Read Topic
  but not yet allowed Read Group orders-worker-v1

Correct action:
  grant Group Read to the right principal and group
  via Kafka admin workflow
  rollout/restart as needed and confirm consumer joins group
  reconcile offsets + data after recovery

Wrong action:
  change group-id to an arbitrary name
  disable TLS
  grant Cluster All to bypass errors
~~~

### Incident Example: Expired Certificate

~~~text
Time: broker certificate expired
Symptom: SSLHandshakeException on new clients
Cause: cert rotation workflow was not executed before expiry

Response:
  confirm cert/hostname/CA status
  issue valid cert matching broker endpoints
  update broker/truststore per rolling plan
  verify auth/ACLs and data after recovery

Prevention:
  alert before certificate expiry
  dual-trust/rotation runbook
  test in staging with new cert
~~~

Both incidents illustrate why security failures must be diagnosed at the **right layer**, rather than patched with hasty config overrides that weaken data safety.

## 29. Common Mistakes

**1. Using `PLAINTEXT` in production because it worked locally.** Traffic and credentials travel without TLS protection.

**2. Using `SASL_PLAINTEXT` on untrusted networks.** SASL does not encrypt all traffic; production policies require TLS.

**3. Confusing truststore and keystore.** Truststores verify the remote peer; keystores hold your own private key and client certificate.

**4. Putting raw passwords in `application-prod.yml`.** Secrets leak into Git, artifacts, backups, and logs.

**5. Base64-encoding passwords in ConfigMap/Secret manifests and calling it encryption.** Base64 offers zero confidentiality.

**6. Disabling hostname verification on TLS errors.** Weakens broker authentication and masks real DNS/certificate/config bugs.

**7. Assuming SASL success means everything works.** Topic/Group ACLs can still reject requests.

**8. Granting `All` on Cluster to a topic-reading app.** Violates least privilege and expands blast radius.

**9. Changing consumer group ID to escape Group ACL errors.** Causes unintended replays or skipped backlogs.

**10. Assuming updating a ConfigMap/Secret refreshes Kafka clients automatically.** Clients normally require restarts/recreation to load new credentials.

**11. Setting `sasl.jaas.config` only on the consumer when the producer also sends to DLT.** The producer fails authentication.

**12. Using `PLAINTEXT` `@EmbeddedKafka` as proof `SASL_SSL` is tested.** You need a secured test broker.

**13. Printing full `KafkaProperties` or debug logs to troubleshoot.** Risks leaking JAAS passwords, tokens, and private keys.

**14. Treating TLS/SASL as exactly-once.** Authentication and encryption do not eliminate redeliveries or DB side-effect duplicates.

**15. Rotating credentials and revoking the old one before new Pods are ready.** Causes fleet-wide outages.

**16. Forgetting certificate SANs for advertised broker endpoints.** Bootstrap succeeds while subsequent broker connections fail.

**17. Exposing Actuator endpoints publicly for monitoring.** Risks leaking config or system internals.

**18. Changing only client config when the broker policy does not support the mechanism.** SCRAM/mTLS/OAuth always require compatible broker and client setup.

## 30. Hands-On Exercises

### Exercise 1 — Compare Protocols

Diagram `PLAINTEXT`, `SSL`, `SASL_PLAINTEXT`, and `SASL_SSL`. For each, indicate whether TLS encryption is active and how the broker authenticates clients.

### Exercise 2 — Local and Prod Profiles

Write `application-local.yml` targeting an isolated test Kafka broker. Write `application-prod.yml` using `SASL_SSL`, SCRAM, and a secret-file truststore. Keep the application image identical across both environments.

### Exercise 3 — Secrets via `configtree`

Create **dummy** secrets in a test directory containing `kafka.sasl.jaas.config`. Verify Spring Boot binds the property correctly and tests print zero credential values to logs. Never use real passwords/tokens in fixtures.

### Exercise 4 — Least-Privilege ACLs

Design a consumer principal allowed to read `orders.events.v1` and use group `orders-worker-v1` with no write rights, plus a producer principal allowed only to write `orders.results.v1`. Build a permissions matrix and negative tests.

### Exercise 5 — TLS Handshake

Use a test broker with a TLS certificate, then test valid/invalid truststores and valid/invalid hostnames. Record the error types. Never disable hostname verification to make tests pass.

### Exercise 6 — `GroupAuthorizationException`

Grant Topic Read while intentionally withholding Group Read on a test broker. Observe the consumer failing to join; add the missing ACL and verify consumption resumes without changing the group ID.

### Exercise 7 — SCRAM Rotation

Create test credentials A/B (on a broker supporting dual credentials). Roll Pods from A to B, measure consumer lag/rebalances, and verify zero policy-violating duplicates. Revoke A only after B is healthy.

### Exercise 8 — mTLS

Create a client certificate/keystore and configure a test broker requiring client certs. Test both a valid certificate and an untrusted client cert; verify errors occur at the expected layer and principal mapping works.

### Exercise 9 — DLT Security

Use `DefaultErrorHandler` and a DLT publisher in a test environment. Intentionally withhold DLT Write permission, observe failure and alerts, then grant the right permission. Verify logs/error headers contain no secrets.

### Exercise 10 — Security Incident Drill

Simulate a JAAS password leaked in test logs. Plan revocation, rotation, log access controls, backup retention, rolling deploy, and ACL verification. Never use production credentials in drills.

## 31. Official References

- [Spring Boot — Apache Kafka Support](https://docs.spring.io/spring-boot/reference/messaging/kafka.html)
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Kafka — Reference](https://docs.spring.io/spring-kafka/reference/)
- [Spring Kafka — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html)
- [Spring Kafka — Exactly Once Semantics](https://docs.spring.io/spring-kafka/reference/kafka/exactly-once.html)
- [Apache Kafka — Documentation](https://kafka.apache.org/documentation/)
- [Apache Kafka — Security](https://kafka.apache.org/documentation/#security)
- [Apache Kafka — Consumer Configs](https://kafka.apache.org/documentation/#consumerconfigs)
- [Apache Kafka — Producer Configs](https://kafka.apache.org/documentation/#producerconfigs)
- [Kubernetes — Secrets](https://kubernetes.io/docs/concepts/configuration/secret/)
- [Kubernetes — ConfigMaps](https://kubernetes.io/docs/concepts/configuration/configmap/)
- [Kubernetes — Network Policies](https://kubernetes.io/docs/concepts/services-networking/network-policies/)
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)

