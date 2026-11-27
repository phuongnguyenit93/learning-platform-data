# Managing Passwords, Keys, and Certificates with Externalized Configuration

A Spring Cloud Stream application typically connects to Kafka, RabbitMQ, or Pulsar using service accounts, tokens, TLS certificates, and private keys. These values vary by environment and have their own lifecycles: passwords can expire, tokens can be revoked, certificates have expiration dates, and private keys must be replaced if suspected of compromise.

Do not package these values into source code, configuration files inside a JAR, or Docker images. Spring Boot allows loading configuration from environment variables, external files, volume mounts, and secret management systems. Spring Cloud Stream forwards those properties to the corresponding binder and client. This lesson covers separating configuration from secrets, injecting passwords/keys/certificates at runtime, securing connections to all three brokers, and organizing credential rotation without unplanned interruption to event flows.

## 1. Distinguishing Regular Configuration from Secrets

An application needs many kinds of information to connect to a broker. Not every value must be protected like a password, but all must be managed within the proper scope.

| Data Type | Examples | Protection Level |
|---|---|---|
| Connection config | Host, port, topic, exchange, namespace | Regular; may still be internal information |
| Service account | Username, client ID, principal | Access-restricted per environment |
| Passwords and tokens | RabbitMQ password, SASL password, Pulsar token, Vault token | Secret; issued only to workloads that need them |
| Public certificates | CA certificate, client certificate, certificate chain | Not necessarily secret, but integrity and trust source must be protected |
| Private keys | PEM private key, private key inside a keystore | Highly sensitive secret |
| Keystore passwords | Store password, key password | Secret; managed independently from the keystore file |
| Truststore | List of trusted CAs/certificates | Not necessarily secret; altering trust anchors can change trust boundaries |

A certificate typically contains a public key, an identity, and a CA signature. It can be distributed publicly. The corresponding private key must remain confidential because whoever holds the key can prove identity or decrypt data depending on the protocol. A truststore contains CAs or certificates that the client accepts; a keystore typically contains the client's or server's own certificate and private key.

Three distinct goals should be separated:

- **Authentication** verifies who the application or user is.
- **Authorization** decides which topics, exchanges, subscriptions, or resource management actions that identity is allowed to perform.
- **Transport security** protects data in transit over the network and verifies the endpoint via TLS.

Having the right password does not mean the application is permitted to publish. TLS connection encryption also does not replace broker ACLs or policies.

## 2. Why Not Store Secrets in application.yml or Source Code?

The following example is unsuitable for a shared repository:

~~~yaml
spring:
  rabbitmq:
    host: rabbit.internal
    username: order-service
    password: my-production-password
  cloud:
    stream:
      kafka:
        binder:
          configuration:
            sasl.jaas.config: org.apache.kafka.common.security.plain.PlainLoginModule required username="app" password="my-secret";
~~~

If this file is committed, secrets can end up in Git history, build artifacts, CI caches, artifact registries, image layers, logs, or backups. Removing the password line in a later commit does not remove the value stored in history.

The following approaches do not make secrets safe either:

- Encoding passwords with Base64; Base64 is only encoding.
- Putting passwords in Java constants or static variables.
- Renaming the file to .secret while still committing it to Git.
- Putting passwords in a Dockerfile via ARG/ENV and building the image.
- Passing passwords via command-line arguments if they can appear in process lists or logs.
- Using the same account and password across development, staging, and production.
- Logging passwords, tokens, JAAS strings, or private keys during debugging.

Configuration files packaged in the application should contain property names, resource addresses, and paths to certificate files. Secret values are supplied at runtime from a secret store or restricted volume.

## 3. How Does Spring Boot Load Externalized Configuration?

Spring Boot constructs a Spring Environment from multiple PropertySources. Common sources include:

- Default values provided by the application.
- application.properties or application.yml files on the classpath.
- Configuration files outside the JAR.
- Process environment variables.
- Java system properties.
- JSON configuration via SPRING_APPLICATION_JSON.
- Command-line arguments.
- Configuration imported from files, config trees, or external systems like Vault.

Sources follow an order of precedence. A higher-precedence source can override values from a lower-precedence source. This lets the same artifact run in multiple environments, but can also cause secret values to be overridden unintentionally.

For example, a file inside the JAR can set a default broker address for local development. During deployment, environment variables or external configuration provide production endpoints. For secrets, tightly control which sources are allowed to override them and do not use command-line arguments as a channel for distributing passwords.

External file paths can be configured with SPRING_CONFIG_ADDITIONAL_LOCATION or declared via spring.config.import. If using spring.config.location, remember that this property replaces the default configuration search locations; spring.config.additional-location adds new locations while keeping the defaults.

Do not put production values in the default profile. A profile only selects a configuration set; it is not a secret manager. Secrets must still come from a protected source.

## 4. Using Config Trees to Read Secrets from Mounted Files

A container-friendly approach is mounting each secret as an individual file. Spring Boot supports the **configtree:** prefix to turn filenames into property names and file contents into property values.

Example runtime directory mount:

~~~text
/run/secrets/
  spring.rabbitmq.username
  spring.rabbitmq.password
  spring.cloud.stream.kafka.binder.configuration.sasl.jaas.config
  spring.cloud.stream.kafka.binder.configuration.ssl.truststore.password
  spring.pulsar.client.authentication.param.token
~~~

A file named **spring.rabbitmq.password** creates a property with the same name; the file content is the password. Similarly, a file named **spring.pulsar.client.authentication.param.token** creates the token property for the Pulsar client.

Declare the import in application.yml:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/"
  application:
    name: order-stream
~~~

Files in the directory are loaded into the Spring Environment. They can be accessed like regular properties using @Value, Environment, or @ConfigurationProperties. Config trees support String and byte[] values depending on the expected content.

Directory and file names beneath a config tree form the property name. Dotted filenames can be used to represent hierarchical properties. If a secret required for a production connection is missing, let the application fail on startup rather than silently falling back to a default account. Only add the optional: prefix when the absence of that directory is genuinely acceptable.

### Non-Secret Configuration and Secret Files

The application.yml file can contain non-sensitive properties:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/"
  cloud:
    stream:
      kafka:
        binder:
          brokers: kafka.prod.internal:9093
          configuration:
            security.protocol: SASL_SSL
            sasl.mechanism: SCRAM-SHA-512
            ssl.truststore.location: /run/messaging-certs/kafka-truststore.p12
            ssl.truststore.type: PKCS12
  rabbitmq:
    addresses: amqps://rabbit.prod.internal:5671
    ssl:
      enabled: true
      trust-store: /run/messaging-certs/rabbit-truststore.p12
      trust-store-type: PKCS12
  pulsar:
    client:
      service-url: pulsar+ssl://pulsar.prod.internal:6651
      authentication:
        plugin-class-name: org.apache.pulsar.client.impl.auth.AuthenticationToken
~~~

Secret files in /run/secrets provide passwords, JAAS configs, and tokens. Certificates/keystores are mounted read-only at /run/messaging-certs. File paths can live in application.yml because paths are not private keys or passwords; sensitive file contents remain managed separately.

When mounting files, restrict read permissions to the user running the application. Do not mount the entire secret directory into every container in a Pod if that container does not need access. If the platform supports read-only volumes, use that mode for certificates and secret files.

## 5. Environment Variables and Limitations for Secrets

Environment variables are a common way to pass configuration into containers. Example:

~~~text
SPRING_RABBITMQ_USERNAME=order-service
SPRING_RABBITMQ_PASSWORD=<secret-from-platform>
SPRING_CLOUD_STREAM_KAFKA_BINDER_BROKERS=kafka.prod.internal:9093
~~~

Spring Boot translates environment variable names into property names. This works well for many settings and some simple secrets. However, environment variables can appear in process diagnostics, container specs, dumps, or administrative tools permitted to inspect the environment. Evaluate your platform's threat model before using them for private keys or broad-privilege tokens.

Environment variable names do not preserve all dots, hyphens, and casing in property names. For properties with case-sensitive names, keep the exact property name in YAML and reference the environment variable as the value.

For example, Pulsar OAuth2 requires the exact parameter name **issuerUrl**:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/"
~~~

With a config tree, mount the secret as a file named exactly **spring.pulsar.client.authentication.param.issuerUrl** containing the issuer URL. If using environment variables, keep the camelCase property in YAML and reference the environment variable as its value; do not rely on Spring Boot inferring issuerUrl from an environment variable normalized to issuerurl. Spring Pulsar documentation requires names under authentication.param to match exact plugin parameter names.

Do not pass passwords via the command line if alternatives exist. Command lines are often readable from process metadata or deployment system logs. Prefer a secret manager, config tree, or workload identity mechanism.

## 6. Using Kubernetes Secrets and Docker Secrets

Kubernetes can mount a Secret into a Pod as a volume or inject it as environment variables. With a volume mount, each key of the Secret becomes a file. Combined with configtree, the application can read those files as properties.

Example manifest illustrating structure without secret values:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: order-stream
spec:
  containers:
    - name: app
      image: registry.example/order-stream:1.0
      volumeMounts:
        - name: messaging-secrets
          mountPath: /run/secrets
          readOnly: true
        - name: messaging-certs
          mountPath: /run/messaging-certs
          readOnly: true
  volumes:
    - name: messaging-secrets
      secret:
        secretName: order-stream-messaging
    - name: messaging-certs
      secret:
        secretName: order-stream-certificates
~~~

When the volume is mounted, application.yml imports the config tree at /run/secrets. Certificate/keystore files are read from the declared paths. Never put Secret contents in public manifests, Git, or images.

A Kubernetes Secret object does not automatically guarantee data is securely encrypted at every layer. Base64 in manifests is merely representation. You must configure encryption at rest for the cluster datastore, RBAC restricting who can read Secrets, access auditing, and limits on which Pods/service accounts may mount secrets. For stricter requirements, use an external secret store or the Secrets Store CSI Driver to retrieve secrets from a dedicated management system.

Docker Swarm Secrets can also be mounted as files inside containers. Spring Boot configtree can read that directory in the same way. Regardless of the platform, verify read permissions, file lifecycle, and how secrets are updated across releases.

## 7. Using Spring Cloud Vault as a Secret Configuration Source

HashiCorp Vault can store passwords, tokens, certificate metadata, or generate time-bound credentials. Spring Cloud Vault integrates with the Spring Boot ConfigData API, exposing Vault data into the Spring Environment as a PropertySource.

Add the Spring Cloud Vault Config dependency matching your application's release train. Configuration example:

~~~yaml
spring:
  application:
    name: order-stream
  config:
    import: "vault://"
  cloud:
    vault:
      uri: https://vault.internal:8200
      authentication: KUBERNETES
      kubernetes:
        role: order-stream
~~~

In a Kubernetes environment, the application can authenticate to Vault using its Kubernetes service account identity. Do not put a root token or administrative token in application.yml. Vault policies should only allow the workload to read the exact paths and keys it needs.

By default, Spring Cloud Vault can mount a KV path based on the application name, such as secret/order-stream, and add contexts for active profiles. You can declare a contextual location if you want to read only a specific path:

~~~yaml
spring:
  config:
    import: "vault:///secret/messaging/order-stream"
~~~

Keys in Vault can be named after Spring properties, for example:

~~~text
spring.rabbitmq.username
spring.rabbitmq.password
spring.cloud.stream.kafka.binder.configuration.sasl.jaas.config
spring.pulsar.client.authentication.param.token
~~~

Once Vault loads those keys into the Environment, binders and Spring Boot auto-configuration read them like any other property. Property source precedence still matters: do not let a value in an application profile or environment variable unintentionally override a secret from Vault.

Spring Cloud Vault supports multiple authentication methods and secret backends. For leased dynamic secrets, Spring Cloud Vault manages lifecycles such as renewal, rotation upon lease expiration, and revocation on application shutdown as supported by the backend. Static tokens are not automatically renewed or revoked by lease like dynamic credentials.

**Loading a new secret into the Environment does not automatically recreate existing binder clients.** Kafka producers/consumers, Rabbit connection factories, and Pulsar clients are usually initialized from configuration at creation time. When a password, token, or certificate changes, you must have a plan to reconnect or recreate clients using the updated configuration. Test the exact behavior of your binder version and refresh mechanism; do not assume every client re-reads the Environment automatically.

## 8. Managing Kafka Username, Password, and SASL

The Kafka Binder accepts shared security properties via **spring.cloud.stream.kafka.binder.configuration**. This is a client property map passed to producers and consumers created by the binder. Because it is shared, it is well suited for properties like security.protocol, SASL mechanism, and TLS trust material. If there are multiple Kafka clusters, each named binder can have its own authentication configuration.

Example SASL/SCRAM over TLS:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          brokers: kafka.prod.internal:9093
          configuration:
            security.protocol: SASL_SSL
            sasl.mechanism: SCRAM-SHA-512
            sasl.jaas.config: <LOAD_FROM_SECRET_PROPERTY>
            ssl.truststore.location: /run/messaging-certs/kafka-truststore.p12
            ssl.truststore.type: PKCS12
            ssl.truststore.password: <LOAD_FROM_SECRET_PROPERTY>
~~~

In real environments, sasl.jaas.config and ssl.truststore.password must come from a secret store or mounted file. An example JAAS value can be structured as:

~~~text
org.apache.kafka.common.security.scram.ScramLoginModule required username="order-stream" password="<secret>";
~~~

Never commit this value to Git. Kafka clients support SASL mechanisms like PLAIN, SCRAM, and GSSAPI depending on the broker/client. Choose the mechanism matching broker configuration and organizational policy. With SASL_SSL, SASL authenticates the client and TLS encrypts/verifies the broker certificate.

If using Kerberos, Spring Cloud Stream can read a JAAS configuration file via the java.security.auth.login.config system property or use Spring Boot properties under kafka.binder.jaas. Do not mix a JAAS file with Spring Boot JAAS properties in the same application; binder documentation states that when the java.security.auth.login.config system property is present, Spring Boot JAAS configuration is ignored.

### One-Way TLS and Mutual TLS

With one-way TLS, the client needs to trust the CA that signed the broker's certificate. The Kafka client can use a truststore:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          configuration:
            security.protocol: SSL
            ssl.truststore.location: /run/messaging-certs/kafka-truststore.p12
            ssl.truststore.type: PKCS12
            ssl.truststore.password: <LOAD_FROM_SECRET_PROPERTY>
~~~

With mutual TLS, the broker also requires a client certificate. In that case, additionally configure a keystore containing the client certificate and private key:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          configuration:
            security.protocol: SSL
            ssl.truststore.location: /run/messaging-certs/kafka-truststore.p12
            ssl.truststore.type: PKCS12
            ssl.truststore.password: <LOAD_FROM_SECRET_PROPERTY>
            ssl.keystore.location: /run/messaging-certs/kafka-client.p12
            ssl.keystore.type: PKCS12
            ssl.keystore.password: <LOAD_FROM_SECRET_PROPERTY>
            ssl.key.password: <LOAD_FROM_SECRET_PROPERTY>
~~~

The truststore holds CAs/certificates trusted by the client. The keystore holds the client's certificate and private key. Keystore password and key password can differ; do not assume one password protects all material. Kafka supports PEM in modern client versions with specific formatting constraints; check your kafka-clients version and key/certificate formats before switching from PKCS12/JKS to PEM.

If a Kafka app has multiple binder instances connecting to different clusters, place JAAS configs and trust material in the exact scope of each binder. Dedicated SASL JAAS configurations can be set via sasl.jaas.config per cluster; never share credentials if two clusters have different identities and policies.

In secure environments, topics, partitions, and ACLs are usually provisioned by infrastructure teams. Do not grant admin permissions to a consumer just so the binder can auto-create topics. Grant least-privilege permissions according to read/write and group needs.

## 9. Managing RabbitMQ Username, Password, and TLS

The RabbitMQ Binder uses the Spring Boot ConnectionFactory by default. Therefore, connection and SSL properties usually use the **spring.rabbitmq** prefix. This differs from Kafka: the application normally does not need to create a custom connection factory for the binder.

Example:

~~~yaml
spring:
  rabbitmq:
    host: rabbit.prod.internal
    port: 5671
    username: <LOAD_FROM_SECRET_PROPERTY>
    password: <LOAD_FROM_SECRET_PROPERTY>
    virtual-host: /orders
    ssl:
      enabled: true
      trust-store: /run/messaging-certs/rabbit-truststore.p12
      trust-store-type: PKCS12
      trust-store-password: <LOAD_FROM_SECRET_PROPERTY>
      validate-server-certificate: true
      verify-hostname: true
~~~

If the broker requires mutual TLS, add the client keystore:

~~~yaml
spring:
  rabbitmq:
    ssl:
      key-store: /run/messaging-certs/rabbit-client.p12
      key-store-type: PKCS12
      key-store-password: <LOAD_FROM_SECRET_PROPERTY>
      trust-store: /run/messaging-certs/rabbit-truststore.p12
      trust-store-type: PKCS12
      trust-store-password: <LOAD_FROM_SECRET_PROPERTY>
~~~

The placeholders in the example represent properties supplied from a secret store or config tree. Never store real values in YAML. Spring Boot supports SSL bundles for certain auto-configured connections; bundles can be used if your Spring Boot and Spring AMQP versions support that connection type. When using direct RabbitMQ properties, verify the SSL properties corresponding to your Spring Boot release train.

Do not disable certificate validation or hostname verification as a "quick fix" for TLS errors. When a handshake fails, check the CA chain, certificate SANs, broker hostname, system clock, keystore type, and password. Disabling hostname verification can cause the client to accept a spoofed endpoint even though data is encrypted.

RabbitMQ username/password establishes the principal. Permissions on virtual hosts, exchanges, and queues are still controlled by broker permissions. Use a dedicated user per application and grant least-privilege configure/write/read permissions. Never use guest/guest in production environments.

## 10. Managing Pulsar Tokens, Certificates, and Keys

The Pulsar Spring Boot Starter auto-configures PulsarClient. The Pulsar Binder uses Spring for Apache Pulsar components, so Spring Boot properties under **spring.pulsar.client** can be used for the binder.

Token authentication example:

~~~yaml
spring:
  pulsar:
    client:
      service-url: pulsar+ssl://pulsar.prod.internal:6651
      authentication:
        plugin-class-name: org.apache.pulsar.client.impl.auth.AuthenticationToken
        param:
          token: <LOAD_FROM_SECRET_PROPERTY>
~~~

Tokens must be retrieved from a secret store. For OAuth2, parameter names like issuerUrl must retain exact casing required by the plugin. Do not put OAuth2 private keys in committed configuration files; use a file mount or secret provider supported by the plugin.

### TLS with PEM and Customizers

Spring Boot auto-configuration does not currently expose all TLS properties for the Pulsar client in the same way as Kafka or RabbitMQ. You can use **PulsarClientBuilderCustomizer** to configure TLS on the client builder. Pulsar supports PEM and JKS.

Mutual TLS example with mounted PEM files:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.pulsar.core.PulsarClientBuilderCustomizer;

@Configuration
public class PulsarTlsConfiguration {

    @Bean
    PulsarClientBuilderCustomizer pulsarClientTlsCustomizer() {
        return builder -> {
            builder.allowTlsInsecureConnection(false);
            builder.enableTlsHostnameVerification(true);
            builder.tlsTrustCertsFilePath(
                "/run/messaging-certs/pulsar-ca.pem"
            );
            builder.tlsCertificateFilePath(
                "/run/messaging-certs/pulsar-client.crt"
            );
            builder.tlsKeyFilePath(
                "/run/messaging-certs/pulsar-client.key"
            );
        };
    }
}
~~~

Paths in the example point to files mounted outside the container. Never package private keys into the classpath or JAR. Grant read permissions only to the user running the application. If only server certificate verification is needed, configure CA trust without supplying a client certificate/private key; if the broker requires mTLS, the client certificate/key are required.

If the binder uses PulsarAdmin to provision topics, configure TLS and authentication for the admin client correspondingly via **PulsarAdminBuilderCustomizer**. Configuring only PulsarClientBuilderCustomizer may not suffice for the admin path. Both broker URL and admin URL must use matching TLS schemes/ports, typically pulsar+ssl:// for client and https:// for admin.

Do not enable allowTlsInsecureConnection or disable hostname verification in production. Those options can be helpful in a local test with self-signed certificates, but weaken broker identity verification.

## 11. Distinguishing Truststore, Keystore, and Certificate Chain

Names that are easy to confuse:

| Component | What Does It Contain? | What Is It Used For? |
|---|---|---|
| CA certificate | Public certificate of a CA | Verify certificates signed by that CA |
| Server certificate | Public certificate of a broker | Verify the broker is the expected endpoint |
| Client certificate | Public certificate of an application | Present the application's identity in mTLS |
| Private key | Private key matching a certificate | Prove ownership of the certificate |
| Truststore | CAs/certificates trusted by a client | Verify the server or peer |
| Keystore | Client/server private key and certificate | Supply TLS identity |
| Certificate chain | Leaf certificate plus intermediate CAs | Allow the peer to build a trust chain |

A truststore is not a place to store broker passwords. A keystore is not a copy of a truststore. If the client only verifies the server, usually only a truststore is needed. If the broker requires mutual TLS, the client additionally needs a keystore or PEM certificate/private key.

Private keys must be protected much more strictly than public certificates. Never send private keys over email, tickets, chat, or logs. Do not use the same client key across all environments. Issue separate certificates per workload or group of workloads sharing the same trust boundary.

## 12. Organizing Secret and Certificate Directories on Deployment

Text-based secret files and key/certificate files can be separated into two volumes:

~~~text
/run/secrets/
  spring.rabbitmq.username
  spring.rabbitmq.password
  spring.cloud.stream.kafka.binder.configuration.sasl.jaas.config
  spring.cloud.stream.kafka.binder.configuration.ssl.truststore.password
  spring.pulsar.client.authentication.param.token

/run/messaging-certs/
  kafka-truststore.p12
  kafka-client.p12
  rabbit-truststore.p12
  rabbit-client.p12
  pulsar-ca.pem
  pulsar-client.crt
  pulsar-client.key
~~~

The Spring config tree reads file contents in /run/secrets as properties. Binders read certificates/keystores from paths in /run/messaging-certs. These are two different delivery mechanisms: config tree turns file content into property values; certificate files must remain intact as files for TLS libraries to read.

When deploying:

- Mount secrets and certificates read-only.
- Restrict file permissions and readable user/group.
- Do not mount secrets into sidecar containers that do not need them.
- Do not bake secrets into image layers or build args.
- Use volumes/secret managers that support version updates.
- Name secrets after the application, environment, and broker cluster.
- Separate Kafka, RabbitMQ, and Pulsar credentials.
- Monitor certificate expiration dates and token lifetimes.

There is no need to put all cluster secrets into one giant configuration file. One file per key makes permission control, auditing, and version rotation clearer.

## 13. Managing Multiple Binders and Multiple Clusters

A single Spring Cloud Stream application can include Kafka, RabbitMQ, and Pulsar binders simultaneously. It can also connect to two different Kafka clusters using named binders. Each cluster may require different usernames, passwords, JAAS configs, CAs, and client certificates.

Named Kafka binders example:

~~~yaml
spring:
  cloud:
    stream:
      binders:
        kafkaOrders:
          type: kafka
          environment:
            spring:
              cloud:
                stream:
                  kafka:
                    binder:
                      brokers: kafka-orders.internal:9093
                      configuration:
                        security.protocol: SASL_SSL
                        sasl.mechanism: SCRAM-SHA-512
                        sasl.jaas.config: <ORDERS_CLUSTER_SECRET>
                        ssl.truststore.location: /run/certs/orders-trust.p12
                        ssl.truststore.password: <ORDERS_TRUST_SECRET>
        kafkaAudit:
          type: kafka
          default-candidate: false
          environment:
            spring:
              cloud:
                stream:
                  kafka:
                    binder:
                      brokers: kafka-audit.internal:9093
                      configuration:
                        security.protocol: SASL_SSL
                        sasl.mechanism: SCRAM-SHA-512
                        sasl.jaas.config: <AUDIT_CLUSTER_SECRET>
                        ssl.truststore.location: /run/certs/audit-trust.p12
                        ssl.truststore.password: <AUDIT_TRUST_SECRET>
~~~

Each binder needs its own secret issued for the right workload. When using explicit binder configuration, declare every binder the application uses; do not assume a default binder will still be auto-configured as when only a single implementation is on the classpath.

Do not share a single JAAS config across multiple clusters just because the SASL mechanism is the same. Principals, usernames/passwords, truststores, and access permissions may differ. Inspect the exact property sources of each binder instance to avoid having the audit binder accidentally inherit the orders binder's credentials.

## 14. Managing Secrets with @ConfigurationProperties

For custom application configuration, properties can be grouped into a record or class annotated with @ConfigurationProperties. This validates required settings and reduces scattered Environment lookups.

Example managing only alias names and file paths while passwords remain loaded from external sources:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.messaging.tls")
public record MessagingTlsProperties(
    String kafkaTrustStore,
    String rabbitTrustStore,
    String pulsarCaCertificate
) {
}
~~~

Register with @ConfigurationPropertiesScan or @EnableConfigurationProperties. These values are not necessarily secrets if they are only paths. Never create a class holding all passwords and log the entire object while debugging.

If you must bind a secret into a bean, keep its scope and lifecycle minimal, avoid exposing unnecessary getters via APIs, and exclude it from toString, log records, or exception messages. Data in the Spring Environment still resides in process memory; externalization helps control distribution and lifecycle, not eliminate secrets from memory.

## 15. Planned Password and Token Rotation

Rotating secrets requires coordinating the broker, secret store, and application. If you change a password on the broker immediately while instances still use the old password, new connections may fail. If you delete the old user before all instances switch to the new user, flows may be disrupted.

A safe credential rotation workflow:

1. Create a new user or credential on the broker with the required least-privilege permissions.
2. Verify read/write permissions on topics, exchanges, queues, or namespaces.
3. Store the new credential in the secret manager under a new version.
4. Update deployment configuration so workloads read the new version.
5. Recreate or reconnect clients using the tested mechanism.
6. Verify consumer groups/subscriptions are active and producers can publish.
7. Monitor authentication errors, reconnects, lag, and DLQs.
8. Revoke the old credential after all instances have transitioned successfully.

For tokens with TTLs, track expiration times and token issuance mechanisms. Do not use non-expiring tokens for long-running workloads if your platform supports short-lived tokens or workload identities.

Do not rotate credentials simultaneously across multiple brokers without rollback capability. Roll out broker by broker or instance group by instance group to bound blast radius.

## 16. Rotating Certificates and Private Keys

TLS certificates have start and expiration dates. An expired certificate can prevent clients from establishing a TLS connection even when username/password are valid.

A typical CA/certificate rotation workflow includes:

1. Issue the new CA or certificate and verify hostname/SAN, chain, validity period, and key usage.
2. Update the client truststore to trust both the old CA and the new CA during the transition period if needed.
3. Update broker certificates or client certificates per plan.
4. Mount the new keystore/PEM files into the workload.
5. Recreate TLS clients/connections using a mechanism supported by the binder.
6. Verify handshakes and hostname verification.
7. Once all clients have migrated, remove the old CA from the truststore.
8. Revoke old certificates/keys per policy.

If you replace the server certificate before clients trust the new CA, handshakes will fail. If you remove the old CA too early, un-updated brokers or instances may lose connectivity. An overlap period enables controlled migration.

New private keys should be generated inside an HSM or key management system when security requirements are high. There is no need to export private keys to files if libraries and infrastructure support using keys from HSM/PKCS#11. If using PEM/PKCS12 files, restrict read permissions and avoid unnecessary copies.

## 17. Secret Rotation Does Not Mean Automatic Binder Refresh

The Spring Environment may receive updated values from config trees or Vault, yet some components read properties only when constructed. For example:

- Kafka producers/consumers may already be constructed with the initial SSL/SASL config.
- Rabbit ConnectionFactory may hold an open connection authenticated with the old password.
- PulsarClient may hold authentication objects and TLS contexts created from old files.

Therefore, verify whether your framework/client versions support reloading material and reconnecting. Spring Boot SSL bundles have a reload mechanism when files change, but only SSL consumers compatible with reloadable bundles pick them up automatically. Do not assume Kafka Binder, Rabbit connection factories, or Pulsar clients automatically reload just because files changed.

If a client does not support safe reloading, perform a rolling restart or recreate clients/containers in the framework-supported manner. During a rolling restart, maintain enough instances/partition consumers to avoid losing processing capacity. For producers, verify publish error rates and confirms after instances restart.

With Vault dynamic credentials, lease renewal keeps secrets valid; updating credentials inside the client still must be supported or triggered by the application. Test the real lifecycle: secret rotates, old connection closes, new client authenticates with the new secret, and message flow continues.

## 18. Checking Certificates, Keys, and Configurations Before Deployment

Common mistakes detectable before rollout:

| Check | What to Verify |
|---|---|
| Certificate validity | Not Before/Not After are currently valid |
| Hostname/SAN | Broker name matches certificate |
| Certificate chain | Intermediate and root CAs are complete |
| Truststore | Contains the CA that signed the broker certificate |
| Keystore | Contains private key and matching certificate |
| Key password | Matches the private key or store |
| Store type | PKCS12/JKS/PEM compatible with client |
| File permissions | App user can read, other users cannot |
| Broker ACLs | Principal has the exact required permissions |
| Token/password TTL | Remaining lifetime covers the rollout |
| Clock synchronization | Host/container clocks are synchronized to validate certificate/token lifetimes |

You can use keytool to inspect keystore metadata:

~~~bash
keytool -list -v -keystore /run/messaging-certs/kafka-client.p12 -storetype PKCS12
~~~

The command prompts for the store password if required. Never put passwords on the command line or in committed scripts. For PEM, use OpenSSL tools to inspect certificates, private keys, and chains; avoid printing private keys to terminal logs or CI artifacts.

Do not check only that the file exists. A certificate file may exist yet be expired, lack a matching SAN, miss an intermediate in its chain, or have a private key that does not match the certificate.

## 19. Protecting Secrets in Logs, Actuator, and Diagnostics

When broker connection errors occur, logs should provide enough detail for diagnosis without containing secret values.

Safe to log:

- Configured broker host/port or alias.
- Binder type and binding name.
- Authentication/TLS error category.
- Certificate subject/issuer and validity period if permitted.
- Non-sensitive secret version or credential identifier.
- Reconnect timestamps and retry counts.

Never log:

- Passwords, tokens, or JAAS strings.
- Private keys or keystore contents.
- Authorization headers.
- The entire Environment or all Kafka client properties.
- Stack traces containing configuration strings with secrets.

Actuator endpoints such as env and configprops can expose application configuration. Expose only necessary endpoints, restrict administrative access, and use Spring Boot sanitization policies. Never expose sensitive diagnostic endpoints to public networks. Inspect startup logs, client debug logs, and deployment system logs before releasing to production.

## 20. Testing Security Configuration Against Real Brokers

The Test Binder can verify functions and bindings at the framework level, but it does not prove SASL, TLS handshakes, certificate chains, or broker ACLs. You need integration tests against a security-configured broker or production-like staging environment.

Scenarios to verify:

1. Valid credentials: consumer connects and receives messages.
2. Wrong password/token: application reports an authentication error and does not fall back to default credentials.
3. Principal lacks permissions: topic read or publish is denied according to policy.
4. Untrusted CA certificate: TLS handshake fails.
5. Hostname does not match SAN: client rejects broker.
6. Invalid or expired client certificate: mTLS fails.
7. Rotated secret: client reconnects using the new secret.
8. Replaced certificate: client uses the new truststore/keystore after the designed reload or restart mechanism.
9. Multi-binder: each cluster uses its own credentials and trust material.
10. Broker restart: connections recover without logging secrets.
11. Vault unavailable at startup: application behaves per chosen fail-fast or optional policy.
12. Revoked secret: application detects errors, alerts, and switches to valid credentials per procedure.

Tests should include negative cases. A test that only verifies the application connects with a valid password does not prove the client rejects spoofed certificates or expired credentials.

## 21. Common Errors and Resolutions

| Symptom | Possible Cause | Resolution Direction |
|---|---|---|
| Kafka reports SASL authentication failed | JAAS config, username/password, or mechanism mismatch | Check sasl.mechanism, JAAS, and credential version |
| Kafka SSL handshake failed | Truststore missing CA, expired certificate, or protocol mismatch | Check chain, validity period, and TLS protocol |
| Kafka client cannot read keystore | Wrong path, permissions, or store password | Check file mount, type, and secret property |
| RabbitMQ ACCESS_REFUSED | User lacks permissions on virtual host/exchange/queue | Check broker permissions and vhost |
| RabbitMQ SSL peer verification failed | Invalid CA or hostname | Check truststore, SAN, and hostname verification |
| Pulsar authentication failed | Wrong plugin class or token parameter | Check authentication plugin and exact property names |
| Pulsar TLS client fails to connect | Missing client builder/admin builder config or wrong URL scheme | Use pulsar+ssl://, https://, and matching customizers |
| Application still uses old password | Client was created before secret updated | Recreate/reconnect client or rolling restart |
| Vault returns stale properties | Wrong path, profile context, or property source precedence | Check ConfigData import and secret version |
| Secret not loaded from configtree | Wrong filename or wrong import path | Check dotted filename, mount path, and file permissions |
| Environment uses wrong credential | Higher-precedence property source overrides intended secret | Check PropertySource order and environment variables |
| Local tests pass but production fails | Local uses plaintext or default credentials | Add equivalent TLS/SASL/ACL integration tests |

## 22. Production Checklist

- Do not commit passwords, tokens, JAAS configs, private keys, or keystore passwords.
- Separate regular configuration from secrets.
- Choose secret delivery sources: Kubernetes Secrets, Docker Secrets, config trees, or Vault.
- Use configtree for mounted secret files and keep certificates/keys at dedicated file paths.
- Use workload identity or appropriate Vault authentication mechanisms; avoid static root tokens.
- Issue dedicated credentials per application and per broker cluster.
- Grant least-privilege Kafka ACLs, RabbitMQ permissions, and Pulsar tenant/namespace permissions.
- Use TLS and hostname verification; never trust-all certificates.
- Distinguish truststore from keystore and CA certificates from private keys.
- Use PKCS12/JKS/PEM according to client version capabilities.
- Track expiration of passwords, tokens, certificates, and leases.
- Establish an overlap process when rotating CAs or certificates.
- Have a plan to reconnect/recreate clients after secrets change.
- Do not assume an Environment refresh automatically updates binder clients.
- Never log secrets or expose env/configprops endpoints publicly.
- Test invalid credentials, invalid certificates, missing ACLs, and rotation.
- Verify rolling restarts do not drop consumer capacity or cause prolonged publish errors.

## 23. References

- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html), PropertySource precedence, environment variables, and config trees.
- [Spring Boot — SSL](https://docs.spring.io/spring-boot/reference/features/ssl.html), SSL bundles with JKS/PKCS12 and PEM, trust material, and reloading.
- [Spring Cloud Stream — Kafka Binder Security Configuration](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/security-config.html), SASL, SSL, JAAS, and multi-binder credentials.
- [Spring Cloud Stream — Kafka Binder Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html), shared client properties of the Kafka Binder.
- [Spring Cloud Stream — RabbitMQ Binder Properties](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview/binder-properties.html), Rabbit binder using Spring Boot ConnectionFactory and the spring.rabbitmq prefix.
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/index.html), username/password and RabbitMQ SSL properties.
- [Spring for Apache Pulsar — Pulsar Client](https://docs.spring.io/spring-pulsar/reference/reference/pulsar/pulsar-client.html), TLS, authentication plugins, tokens, PEM/JKS, and client builder customizers.
- [Spring Cloud Stream — Pulsar Binder](https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html), binder using Spring for Apache Pulsar and client properties.
- [Spring Cloud Vault — ConfigData API](https://docs.spring.io/spring-cloud-vault/reference/config-data.html), vault:// imports and mounting secret backends as PropertySources.
- [Spring Vault — Property Sources](https://docs.spring.io/spring-vault/reference/vault/propertysource.html), VaultPropertySource and credential rotation.
- [Apache Kafka — Consumer Configuration](https://kafka.apache.org/43/configuration/consumer-configs/), SSL keystore/truststore, SASL, and security.protocol.

Managing passwords, keys, and certificates via externalized configuration lets the same Spring Cloud Stream artifact run safely across multiple environments without carrying production credentials. Spring Boot provides the Environment and config trees; Spring Cloud Vault can supply secrets from a backend; each binder receives its own security properties for Kafka, RabbitMQ, or Pulsar. To maintain long-lived connections reliably, enforce least privilege, verify certificates, monitor expiration, and design reconnect or restart workflows when secrets rotate.
