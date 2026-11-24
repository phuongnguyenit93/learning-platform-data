# Verifying Secure Connections

## 1. Checking Layer by Layer

A Spring Kafka application successfully reaching a broker does not mean the entire security configuration is correct. Kafka connectivity spans multiple layers: DNS and network, TLS, SASL authentication or client certificates, ACL authorization, and finally actual producer/consumer operations.

For example, `order-service` might open TCP to `broker.example:9093` yet fail while verifying the TLS certificate. Or both TLS and SASL might succeed while the producer still cannot write to topic `orders` because its principal lacks `WRITE` permission.

Verify in order:

1. The application resolves the hostname and opens a connection to the broker.
2. The TLS handshake succeeds, the broker certificate is valid, and the hostname matches the SAN.
3. SASL or mutual TLS authenticates the client identity properly.
4. The broker permits the principal to perform required operations.
5. The producer can send records and the consumer can read records using the right consumer group.

~~~mermaid
flowchart TD
    A["Spring Kafka client"] --> B["DNS / TCP"]
    B --> C["TLS handshake"]
    C --> D["SASL authentication or mTLS"]
    D --> E["Kafka ACL"]
    E --> F["Metadata / produce / fetch / commit"]
    B --> X1["Network / DNS error"]
    C --> X2["SSLHandshakeException"]
    D --> X3["SaslAuthenticationException"]
    E --> X4["Authorization error"]
~~~

When a step fails, fix it at the right layer. Do not change ACLs to fix a certificate error or disable TLS hostname verification to bypass broken DNS.

## 2. Distinguishing TLS, SASL, and ACLs

| Mechanism | Question Answered | Example |
|---|---|---|
| TLS | Is the channel encrypted and does the broker have the right identity? | Broker certificate signed by a trusted CA |
| SASL | Which identity is the client connecting with? | SCRAM username/password |
| mTLS | Which certificate does the client present to prove identity? | Client certificate and private key |
| ACL | What is the authenticated identity allowed to do? | Principal allowed to `WRITE` topic `orders` |

Common `security.protocol` values:

| Value | TLS | SASL | Use Case |
|---|---:|---:|---|
| `PLAINTEXT` | No | No | Isolated development environments |
| `SSL` | Yes | No | TLS, optionally combined with client certificates |
| `SASL_PLAINTEXT` | No | Yes | Avoid on untrusted networks |
| `SASL_SSL` | Yes | Yes | Common for production using SASL |

`SASL_SSL` combines TLS with SASL; a client certificate is not required unless the broker enforces mTLS. TLS protects the transport channel and verifies the broker. SASL authenticates the principal. ACLs control which topics, groups, or admin operations the principal may access.

## 3. TLS: Truststore and Broker Certificate

When a client connects over TLS, it must trust the CA that signed the broker's certificate. For the Java Kafka client, CAs are typically placed in a JKS or PKCS12 truststore.

| Property | Purpose |
|---|---|
| `ssl.truststore.location` | Path to truststore containing trusted CAs |
| `ssl.truststore.password` | Truststore password if configured |
| `ssl.truststore.type` | Truststore format, such as `PKCS12` or `JKS` |
| `ssl.endpoint.identification.algorithm` | Broker hostname verification algorithm |

The broker certificate needs a SAN matching the hostname the client uses. If the application connects to `broker.example.com` while the certificate only lists SAN `kafka.internal`, TLS hostname verification will fail.

Do not disable hostname verification by setting `ssl.endpoint.identification.algorithm` to an empty string just to get a connection working. Fix DNS, `advertised.listeners`, or the certificate SAN so they match.

Example of a PKCS12 truststore mounted in a container:

~~~text
/run/secrets/kafka/truststore.p12
~~~

The truststore typically holds root and intermediate CAs needed to verify the certificate chain. Never put the broker's private key inside the client truststore.

## 4. Spring Boot with `SASL_SSL` and SCRAM

The example below uses TLS to encrypt the connection and SASL/`SCRAM-SHA-512` to authenticate username/password:

~~~yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS}
    properties:
      security.protocol: SASL_SSL
      sasl.mechanism: SCRAM-SHA-512
      sasl.jaas.config: "${KAFKA_SASL_JAAS_CONFIG}"
      ssl.truststore.location: "${KAFKA_TRUSTSTORE_LOCATION}"
      ssl.truststore.password: "${KAFKA_TRUSTSTORE_PASSWORD}"
      ssl.truststore.type: PKCS12
      ssl.endpoint.identification.algorithm: https
    producer:
      acks: all
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
    consumer:
      group-id: order-service
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
~~~

Placeholders represent environment variables or values supplied from a secret manager. Example value for `KAFKA_SASL_JAAS_CONFIG`:

~~~text
org.apache.kafka.common.security.scram.ScramLoginModule required username="order-service" password="secret-from-secret-manager";
~~~

In real environments, never write usernames/passwords into YAML, Git, Docker images, or logs. Inject secrets via Kubernetes Secrets, Vault, or a secret manager; restrict read access on secrets and rotate credentials per operational policy.

`spring.kafka.properties` is where shared Kafka properties are configured. If producer, consumer, or admin client needs different settings, use `spring.kafka.producer.properties`, `spring.kafka.consumer.properties`, or `spring.kafka.admin.properties` respectively. Avoid configuring the same property in multiple places with conflicting values.

`SCRAM-SHA-512` is only an example. The SASL mechanism must match the broker listener and provisioned credentials. Some clusters use `SCRAM-SHA-256`, `PLAIN`, or OAuth Bearer; take the exact mechanism from platform configuration.

## 5. SASL Mechanism and JAAS

SASL provides the authentication mechanism. The Kafka Java client needs `sasl.mechanism` and `sasl.jaas.config` matching the mechanism permitted by the broker.

SCRAM example:

~~~properties
sasl.mechanism=SCRAM-SHA-512
sasl.jaas.config=org.apache.kafka.common.security.scram.ScramLoginModule required username="order-service" password="replace-with-secret";
~~~

PLAIN example:

~~~properties
sasl.mechanism=PLAIN
sasl.jaas.config=org.apache.kafka.common.security.plain.PlainLoginModule required username="order-service" password="replace-with-secret";
~~~

`PLAIN` should only be used over `SASL_SSL` to protect credentials in transit. Never use `SASL_PLAINTEXT` on untrusted networks.

Common configuration mistakes:

- Selecting `SCRAM-SHA-512` on the client while the broker only enables `SCRAM-SHA-256`.
- JAAS module does not match the mechanism.
- Username/password rotated, but the application still uses the old secret.
- JAAS string missing quotes or the trailing semicolon.
- Secret contains special characters improperly escaped in YAML or environment variables.

Never put JAAS strings in logs. Log only the mechanism and non-sensitive secret reference names; never log passwords or tokens.

For OAuth Bearer, the callback handler and token endpoint depend on the library/provider. Do not copy SCRAM/PLAIN JAAS snippets for OAuth; use the official configuration for your identity provider and Kafka client version.

## 6. Mutual TLS: Client Authentication via Certificate

Some clusters require clients to present their own certificates in addition to verifying the broker certificate. This is mutual TLS (mTLS).

The client needs a truststore containing trusted CAs to verify the broker, a keystore containing the client certificate and private key, plus keystore/key passwords if protected. The broker needs matching principal mapping to identify and authorize the certificate.

Add these properties when the broker requires mTLS:

~~~yaml
spring:
  kafka:
    properties:
      security.protocol: SSL
      ssl.truststore.location: "${KAFKA_TRUSTSTORE_LOCATION}"
      ssl.truststore.password: "${KAFKA_TRUSTSTORE_PASSWORD}"
      ssl.truststore.type: PKCS12
      ssl.keystore.location: "${KAFKA_KEYSTORE_LOCATION}"
      ssl.keystore.password: "${KAFKA_KEYSTORE_PASSWORD}"
      ssl.key.password: "${KAFKA_PRIVATE_KEY_PASSWORD}"
      ssl.keystore.type: PKCS12
      ssl.endpoint.identification.algorithm: https
~~~

If the cluster requires both SASL and mTLS, use `SASL_SSL` while configuring truststore, keystore, and SASL mechanism together. The client certificate authenticates at the TLS layer; SASL acts as an additional authentication layer if the listener requires both.

Do not confuse truststore and keystore:

- Truststore holds CA certificates the client trusts.
- Keystore holds the client's identity and private key.

Private keys must be protected like credentials. Do not commit keystores to repositories, and do not share one client certificate across services when per-principal auditing and independent revocation are required.

## 7. Verifying with Kafka Command-Line Tools

Before debugging the Spring application, you can use the Kafka CLI with the same bootstrap server and security config to isolate environment issues from code issues.

Create a `client.properties` file outside the repository with restricted read permissions:

~~~properties
security.protocol=SASL_SSL
sasl.mechanism=SCRAM-SHA-512
sasl.jaas.config=org.apache.kafka.common.security.scram.ScramLoginModule required username="order-service" password="replace-with-secret";
ssl.truststore.location=/run/secrets/kafka/truststore.p12
ssl.truststore.password=replace-with-secret
ssl.truststore.type=PKCS12
ssl.endpoint.identification.algorithm=https
~~~

Run an API versions check:

~~~bash
kafka-broker-api-versions.sh \
  --bootstrap-server broker.example.com:9093 \
  --command-config client.properties
~~~

This command checks connectivity and protocol negotiation with the broker. It does not prove the principal has permission to write or read a specific topic.

Check topic metadata:

~~~bash
kafka-topics.sh \
  --bootstrap-server broker.example.com:9093 \
  --command-config client.properties \
  --describe \
  --topic orders
~~~

The `--describe` command needs appropriate permissions to view topic metadata. If connection and authentication succeed but the command is denied, check ACLs for the principal.

Never put `client.properties` containing secrets into Git, build artifacts, or CI logs. Use a temporary file provisioned from a secret manager and delete it per policy after testing.

## 8. Verifying with `AdminClient`

You can use Kafka `AdminClient` to inspect broker metadata from the same runtime environment as the Spring application. The example below creates a client with `SASL_SSL` configuration and requests cluster metadata:

~~~java
import java.util.Properties;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.CommonClientConfigs;
import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.AdminClientConfig;
import org.apache.kafka.common.config.SaslConfigs;
import org.apache.kafka.common.config.SslConfigs;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class KafkaConnectionProbe {

    private static final Logger log =
        LoggerFactory.getLogger(KafkaConnectionProbe.class);

    public void verify(
            String bootstrapServers,
            String jaasConfig,
            String truststorePath,
            String truststorePassword) throws Exception {

        var properties = new Properties();
        properties.put(
            AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG,
            bootstrapServers
        );
        properties.put(
            CommonClientConfigs.SECURITY_PROTOCOL_CONFIG,
            "SASL_SSL"
        );
        properties.put(SaslConfigs.SASL_MECHANISM, "SCRAM-SHA-512");
        properties.put(SaslConfigs.SASL_JAAS_CONFIG, jaasConfig);
        properties.put(
            SslConfigs.SSL_TRUSTSTORE_LOCATION_CONFIG,
            truststorePath
        );
        properties.put(
            SslConfigs.SSL_TRUSTSTORE_PASSWORD_CONFIG,
            truststorePassword
        );
        properties.put(
            SslConfigs.SSL_TRUSTSTORE_TYPE_CONFIG,
            "PKCS12"
        );
        properties.put(
            SslConfigs.SSL_ENDPOINT_IDENTIFICATION_ALGORITHM_CONFIG,
            "https"
        );

        try (AdminClient admin = AdminClient.create(properties)) {
            var nodes = admin.describeCluster()
                .nodes()
                .get(10, TimeUnit.SECONDS);

            log.info(
                "Kafka metadata probe succeeded, brokerCount={}",
                nodes.size()
            );
        }
    }
}
~~~

This example verifies connectivity, TLS, SASL, and cluster metadata queries. `describeCluster()` may require cluster-level `DESCRIBE` permission depending on broker configuration. If a principal only has topic produce/consume permissions without cluster describe permission, the probe may fail with authorization even when secure connectivity succeeded.

In Spring Boot, reuse the externalized Kafka configuration instead of building a second configuration set. The probe must use the exact same bootstrap server, truststore, SASL mechanism, and secrets as the real producer/consumer.

Do not invoke the probe on every message. Run it at startup, in a readiness check with a finite timeout, or in a scheduled operational tool. Avoid creating many `AdminClient` instances repeatedly.

## 9. Verifying Actual Produce and Consume Permissions

A metadata probe does not prove the producer has write permission or the consumer has read permission. Test each operation using the actual principal and topics the application uses.

### Verifying Producer

Use a dedicated provisioned probe topic and a `KafkaTemplate` whose type/serializer matches the probe payload. The example below assumes `KafkaTemplate<String, String>` using `StringSerializer`; if using the service's JSON template, send a properly typed probe event instead of forcing generics to `String`:

~~~java
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.springframework.kafka.core.KafkaTemplate;

public class KafkaProducerProbe {

    private final KafkaTemplate<String, String> kafkaTemplate;

    public KafkaProducerProbe(
            KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void verifyWrite() throws Exception {
        String probeId = "probe-" + UUID.randomUUID();

        var result = kafkaTemplate.send(
            "connection-check",
            probeId,
            "secure-connection-check"
        ).get(10, TimeUnit.SECONDS);

        var metadata = result.getRecordMetadata();

        System.out.printf(
            "Produce OK: topic=%s partition=%d offset=%d%n",
            metadata.topic(),
            metadata.partition(),
            metadata.offset()
        );
    }
}
~~~

A completed future indicates the broker acknowledged the send per `acks` configuration. This check also verifies serializers, connectivity, and permissions needed for topic writes. It does not prove consumers can read the record.

Use a probe topic with short retention and restricted write access. Never write arbitrary test records into business topics because production consumers could process them as real data.

### Verifying Consumer

Use a dedicated test consumer group to verify the principal can subscribe and read the topic. CLI example:

~~~bash
kafka-console-consumer.sh \
  --bootstrap-server broker.example.com:9093 \
  --consumer.config client.properties \
  --topic connection-check \
  --group connection-check-probe \
  --from-beginning \
  --timeout-ms 10000
~~~

The consumer needs `READ` on the topic and `READ` on the group per broker ACLs. A brand-new group ID can start per `auto.offset.reset`; use `--from-beginning` only on controlled probe topics.

To verify the full flow, send a probe record and read it with the test consumer. If the producer succeeds while the consumer cannot read, check topic ACLs, group ACLs, subscription, offsets, and deserializers.

## 10. Distinguishing Authentication and Authorization

These two error types have different meanings:

- **Authentication failure:** the broker could not verify the client's identity. For example, wrong username/password, unsupported SASL mechanism, or invalid client certificate.
- **Authorization failure:** the broker identified the principal, but the principal lacks permission to perform the operation. For example, missing topic `WRITE` or group `READ`.

Common Kafka permissions:

| Operation | Commonly Needed Permission |
|---|---|
| Send record | `WRITE` on topic; some client flows may need `DESCRIBE` |
| Read record | `READ` on topic |
| Join consumer group and commit offsets | `READ` on group |
| View topic metadata | `DESCRIBE` on topic |
| View cluster metadata | `DESCRIBE` on cluster |
| Create topic | `CREATE` at the granted scope or equivalent permission per broker policy |

Resources, operations, and permission inheritance depend on the Kafka ACL authorizer and broker config. Grant least-privilege permissions per service principal; never grant superuser to fix authorization errors.

If the producer can write while the consumer cannot read, check topic and group permissions separately. If the `AdminClient` probe fails due to missing cluster `DESCRIBE`, do not conclude SASL/TLS is broken when permitted business operations still work.

## 11. Diagnosing Common Connection Errors

| Error or Symptom | Likely Failing Layer | Inspection and Resolution |
|---|---|---|
| `UnknownHostException` | DNS | Check hostname, DNS inside container/pod, and broker addresses |
| `Connection refused` | TCP/listener | Check port, firewall, broker listener, and service endpoint |
| Timeout fetching metadata | Network or advertised listener | Check routes to all brokers advertised in metadata |
| `SSLHandshakeException` | TLS | Check protocol, certificate chain, truststore, expiry, and TLS version |
| `PKIX path building failed` | Trust chain | Import the right CA/intermediate into the truststore and check the certificate chain |
| Hostname/SAN mismatch | TLS identity | Connect with a hostname listed in SAN or issue a certificate with the right SAN |
| `SaslAuthenticationException` | SASL authentication | Check mechanism, JAAS module, username/password, and credential state |
| `UnsupportedSaslMechanismException` | SASL negotiation | Select a mechanism enabled on the broker |
| `TopicAuthorizationException` | Topic ACL | Grant the right operation permissions on the topic |
| `GroupAuthorizationException` | Consumer group ACL | Grant `READ` for the required group |
| `ClusterAuthorizationException` | Cluster ACL | Verify whether admin operations are permitted |
| CLI succeeds while Spring fails | Config or runtime mismatch | Compare bootstrap servers, secrets, truststore mounts, serializers, and client properties |

### Note on `advertised.listeners`

Clients only use `bootstrap.servers` to find an initial broker. After fetching metadata, the Kafka client connects to the addresses advertised by brokers via `advertised.listeners`.

Thus, a client can reach the bootstrap broker yet still time out during produce/consume if hostnames in metadata are unresolvable or unreachable from the application's network. TLS certificates must also be valid for the hostnames the client actually connects to after receiving metadata.

When running in Kubernetes, test DNS and network policies from inside the exact pod/namespace. Testing from a laptop does not prove production containers share the same network path.

## 12. Checking Spring's Effective Configuration

When the CLI succeeds while the Spring Kafka application fails, compare the effective configuration of both clients:

- `bootstrap.servers` and all broker hostnames in `advertised.listeners`.
- Whether `security.protocol` is `SASL_SSL` or `SSL` as required by the broker listener.
- Whether `sasl.mechanism` and the JAAS module match.
- Whether secrets are mounted at the right path and readable by the process.
- Whether truststore/keystore formats are right and certificates are not expired.
- Whether `ssl.endpoint.identification.algorithm` was accidentally disabled.
- Whether producer, consumer, and `AdminClient` receive shared properties.
- Whether producer/consumer overrides overwrite the security protocol or SASL settings.

Spring Boot can apply shared properties alongside per-client settings. If one client works while another does not, inspect that specific client's configuration rather than looking only at `spring.kafka.properties`.

Never dump entire `Environment`, `Properties`, or JAAS strings to logs. If debugging is required, log only non-sensitive property names and configured/missing status; mask passwords, tokens, private keys, and truststore passwords.

## 13. Testing Security in the Right Environment

Testing Kafka against a local `PLAINTEXT` broker is helpful for messaging logic, but it does not verify TLS, SASL, certificate rotation, or production ACLs.

A testing strategy should include:

1. **Unit tests:** verify property binding and that secrets flow through configuration without leaking secret values into logs.
2. **TLS integration tests:** run a test broker with a private CA and matching client truststore.
3. **SASL integration tests:** enable the corresponding mechanism and verify valid credentials connect while invalid credentials are rejected.
4. **ACL integration tests:** permitted principals produce/consume successfully; unauthorized principals receive authorization errors.
5. **Staging smoke tests:** use certificates, secret managers, DNS, network policies, and broker listeners matching production.
6. **Rotation tests:** rotate credentials or certificates per procedure and verify clients restart/recreate safely.

Testcontainers only verifies security if the broker container is configured with matching TLS/SASL/ACLs. A default test broker without these mechanisms enabled cannot prove production connectivity is secure.

Never use production certificates or credentials in tests. Create dedicated CAs, principals, and secrets for test environments.

## 14. Readiness, Health Checks, and Operations

A Kafka connection probe can verify that the application can communicate with brokers before receiving traffic. However, distinguish:

- **Liveness:** the application process is alive and not deadlocked.
- **Readiness:** the application is ready to perform work requiring Kafka.
- **Operation probe:** whether a specific operation such as describe cluster, produce, or consume succeeds.

Do not tie liveness directly to Kafka in all cases. If brokers briefly lose connectivity, Kubernetes restarting all pods continuously can worsen the incident. Readiness can reflect Kafka unavailability if the application cannot serve traffic without brokers; this choice depends on architecture.

Probes must have finite timeouts, bounded frequency, and never write records to business topics. If produce/consume checks are needed, use a dedicated probe topic and group with separate ACLs.

When certificates or passwords are rotated, already-created Kafka clients may still hold old configurations. Rotation workflows must update secrets, recreate producers/consumers, or restart the application per deployment strategy. Never assume merely replacing a secret file on disk causes Kafka clients to automatically reload truststores, keystores, or SASL credentials.

## 15. Secure Connection Verification Checklist

- [ ] Verify DNS, TCP, and network routes to bootstrap servers.
- [ ] Verify all broker addresses in `advertised.listeners` are reachable from runtime.
- [ ] Choose the right `security.protocol` matching the broker listener.
- [ ] Verify certificate chain, validity period, and SAN hostnames.
- [ ] Use a truststore with the right CA; never disable hostname verification to bypass errors.
- [ ] If using mTLS, verify client certificate, private key, and keystore.
- [ ] If using SASL, verify mechanism, JAAS module, and secrets.
- [ ] Use SASL PLAIN only over TLS.
- [ ] Separate authentication failures from authorization failures.
- [ ] Grant least-privilege ACLs for topics, groups, and required admin operations.
- [ ] Test with the Kafka CLI using the exact same security configuration.
- [ ] Check metadata with `AdminClient` if the principal holds appropriate permissions.
- [ ] Test produce and consume on a dedicated probe topic.
- [ ] Never write secrets, tokens, passwords, or private keys to logs or repositories.
- [ ] Test certificate/credential rotation and readiness in staging.

Verifying secure connections requires proving the transport channel, identity, and operation permissions. TLS protects the channel and verifies the broker; SASL or mTLS authenticates the client; ACLs restrict operations on topics, groups, and the cluster. By verifying each layer with the CLI, `AdminClient`, and an actual produce/consume check, development teams can pinpoint exact configuration failures and operate Spring Kafka more safely.
