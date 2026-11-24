# TLS Between Application and Kafka

A Spring Kafka application connects to brokers using the Kafka Java client. When data in transit needs protection, configure TLS (Transport Layer Security) for producer, consumer, and related Kafka client connections. TLS encrypts network traffic, verifies the broker's identity using a certificate, and—if mutual TLS (mTLS) is enabled—also verifies the application's certificate.

Spring Kafka does not implement a custom TLS protocol of its own. It passes configuration to the Kafka client through `ProducerFactory`, `ConsumerFactory`, `KafkaAdmin`, and corresponding components. Therefore, Kafka client SSL configuration is the foundation for secure connections in a Spring application.

## 1. What Does TLS Protect?

When an application connects to Kafka over TLS, both sides perform a handshake to negotiate an encrypted session and verify certificates. After the handshake, Kafka data is transmitted inside the TLS channel.

TLS provides three main properties:

- **Confidentiality:** network observers cannot read encrypted payloads, keys, headers, and protocol traffic.
- **Integrity:** tampering with data in transit is detected.
- **Authentication:** the client verifies the broker based on the certificate chain; with mTLS, the broker also verifies the client's certificate.

```text
Spring Kafka application                         Kafka broker
        |                                              |
        |---- ClientHello / TLS negotiation ---------->|
        |<--- Server certificate + handshake ----------|
        |                                              |
        | Verify CA chain, validity, hostname           |
        |                                              |
        |---- (mTLS) Client certificate --------------->|
        |<--- (mTLS) Server verifies client ------------|
        |                                              |
        |========== Encrypted TLS session ==============|
        |---- Kafka protocol: produce / fetch / commit ->|
        |<--- Kafka responses --------------------------|
```

TLS only protects the transit path between the two TLS endpoints. It does not encrypt data at rest on the Kafka broker, does not replace ACLs/authorization, and does not itself determine which user is allowed to read or write topics.

## 2. Distinguishing TLS, mTLS, and SASL

These three concepts often appear together, but they serve different roles:

| Mechanism | Verification | Purpose |
| --- | --- | --- |
| One-way TLS (server-auth TLS) | Client verifies the broker's certificate | Encrypt connections and authenticate the broker |
| Mutual TLS (mTLS) | Client verifies the broker; broker verifies the client's certificate | Authenticate both endpoints using certificates |
| SASL | Broker authenticates the principal using the configured SASL mechanism | Authenticate the application with SCRAM, PLAIN, OAuth, or another supported mechanism |

In Kafka, `security.protocol=SSL` uses TLS. `security.protocol=SASL_SSL` combines TLS with SASL authentication. With one-way TLS alone, the broker is authenticated to the client, but the client is not authenticated by a certificate at the TLS layer; the broker may still require another authentication mechanism.

Do not confuse TLS with authorization. After authentication, Kafka ACLs or the cluster's authorizer determine whether a principal is allowed to `READ`, `WRITE`, `CREATE`, `DESCRIBE` topics, or join a consumer group.

## 3. Certificates, CAs, and the Trust Chain

An X.509 certificate contains a public key and subject identity information, signed by a CA (Certificate Authority). When the broker presents its certificate, the client verifies the signature and builds a trust path to a CA that the client trusts.

A server certificate typically has:

- Subject/SAN specifying the broker's hostname or DNS name.
- A public key corresponding to the private key on the broker.
- `Not Before` and `Not After` validity dates.
- Extended Key Usage appropriate for TLS server authentication.
- An intermediate certificate chain if the CA uses multiple tiers.

The client truststore contains CA certificates or trusted certificates used to verify the broker. Normally, the client only needs the CA certificate, not the broker's private key.

If a cluster has multiple brokers, the client may connect to other brokers after bootstrap, for example when receiving metadata or fetching from a partition leader. Each broker's certificate needs a SAN matching the hostname advertised in `advertised.listeners` and the hostname the client actually connects to.

## 4. How Do Truststore and Keystore Differ?

| Component | What Does It Contain? | Where Is It Used? |
| --- | --- | --- |
| Truststore | CA certificates or trusted certificates | Client verifies the broker certificate |
| Keystore | The client's own certificate and corresponding private key | Client presents its identity when the broker requires mTLS |

With one-way TLS, the application typically only needs a truststore. With mTLS, the application needs both a truststore and a keystore:

```text
Client application
  truststore: CA that signed the broker certificate
  keystore:   client certificate + client private key

Kafka broker
  keystore:   broker certificate + broker private key
  truststore: CA that signed the client certificate
```

A truststore does not need to contain private keys. The private key in the keystore must be protected as a secret; do not commit it to Git, embed it in a JAR or container image, or write it to logs.

## 5. Enabling TLS in Spring Boot

The Kafka client receives SSL properties through `spring.kafka.properties`. Example of one-way TLS using a PKCS12 truststore:

```yaml
spring:
  kafka:
    bootstrap-servers: broker-1.example.net:9093,broker-2.example.net:9093
    properties:
      "[security.protocol]": SSL
      "[ssl.truststore.location]": ${KAFKA_TRUSTSTORE_LOCATION}
      "[ssl.truststore.password]": ${KAFKA_TRUSTSTORE_PASSWORD}
      "[ssl.truststore.type]": PKCS12
      "[ssl.endpoint.identification.algorithm]": https
```

In this example, `KAFKA_TRUSTSTORE_LOCATION` points to a truststore mounted at runtime, and the password is retrieved from a secret store or environment injection. Do not write real passwords into committed configuration files.

Properties under `spring.kafka.properties` are shared Kafka client configuration. Therefore, producers, consumers, and other clients configured from this property group can use the same TLS settings. If a producer or consumer needs separate configuration, overrides can be placed under `spring.kafka.producer.properties` or `spring.kafka.consumer.properties` depending on your needs and Spring Boot version.

`security.protocol=SSL` requires the corresponding broker listener to have SSL enabled. Changing the port from 9092 to 9093 in the example is only an illustrative convention; use the exact address and port provided by your cluster.

## 6. Configuring mTLS for Clients

If the broker requires a client certificate, add the application's keystore:

```yaml
spring:
  kafka:
    bootstrap-servers: broker-1.example.net:9093
    properties:
      "[security.protocol]": SSL
      "[ssl.truststore.location]": ${KAFKA_TRUSTSTORE_LOCATION}
      "[ssl.truststore.password]": ${KAFKA_TRUSTSTORE_PASSWORD}
      "[ssl.truststore.type]": PKCS12
      "[ssl.keystore.location]": ${KAFKA_KEYSTORE_LOCATION}
      "[ssl.keystore.password]": ${KAFKA_KEYSTORE_PASSWORD}
      "[ssl.key.password]": ${KAFKA_PRIVATE_KEY_PASSWORD}
      "[ssl.keystore.type]": PKCS12
      "[ssl.endpoint.identification.algorithm]": https
```

In mTLS:

- The client's truststore trusts the CA that signed the broker certificate.
- The client's keystore contains a certificate and private key that the broker can verify.
- The broker needs a truststore configured to trust the CA that signed the client certificate.
- The broker must enable client authentication, such as `ssl.client.auth=required`, if all clients are required to present a certificate.

`ssl.keystore.password` protects the keystore container; `ssl.key.password` can protect the private key inside it. With some keystores, the two passwords may be the same; do not assume that if your PKI issues them separately.

## 7. Configuring SSL with PEM

The Kafka client supports PEM in supported Kafka versions. When using PEM, you can provide the certificate chain, private key, and CA certificates directly instead of a JKS/PKCS12 file:

```yaml
spring:
  kafka:
    properties:
      "[security.protocol]": SSL
      "[ssl.truststore.type]": PEM
      "[ssl.truststore.certificates]": ${KAFKA_CA_CERTIFICATE}
      "[ssl.keystore.type]": PEM
      "[ssl.keystore.certificate.chain]": ${KAFKA_CLIENT_CERTIFICATE_CHAIN}
      "[ssl.keystore.key]": ${KAFKA_CLIENT_PRIVATE_KEY}
      "[ssl.endpoint.identification.algorithm]": https
```

This is an mTLS example; for one-way TLS, the client only needs the CA certificate in the truststore and does not need a client keystore. The PEM private key must be in a format supported by the Kafka client; if the key is encrypted, configure the corresponding password according to the Kafka client documentation for your version.

Do not put private key contents directly in YAML committed to a repository. The example variables should be provided via a secret manager or securely mounted files; if using file paths, check process read permissions and host user access rights.

## 8. Configuring ProducerFactory and ConsumerFactory in Java

When creating Kafka factories manually, place SSL properties into the Kafka client configuration map. Example using a truststore for the producer:

```java
import java.util.HashMap;
import java.util.Map;

import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.config.SslConfigs;
import org.apache.kafka.common.serialization.StringSerializer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.ProducerFactory;

@Configuration
public class KafkaProducerConfiguration {

    @Bean
    public ProducerFactory<String, String> producerFactory() {
        Map<String, Object> properties = new HashMap<>();
        properties.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
                "broker-1.example.net:9093");
        properties.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
                StringSerializer.class);
        properties.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
                StringSerializer.class);
        properties.put("security.protocol", "SSL");
        properties.put(SslConfigs.SSL_TRUSTSTORE_LOCATION_CONFIG,
                System.getenv("KAFKA_TRUSTSTORE_LOCATION"));
        properties.put(SslConfigs.SSL_TRUSTSTORE_PASSWORD_CONFIG,
                System.getenv("KAFKA_TRUSTSTORE_PASSWORD"));
        properties.put(SslConfigs.SSL_TRUSTSTORE_TYPE_CONFIG, "PKCS12");
        properties.put(SslConfigs.SSL_ENDPOINT_IDENTIFICATION_ALGORITHM_CONFIG,
                "https");

        return new DefaultKafkaProducerFactory<>(properties);
    }

    @Bean
    public KafkaTemplate<String, String> kafkaTemplate(
            ProducerFactory<String, String> producerFactory) {
        return new KafkaTemplate<>(producerFactory);
    }
}
```

The consumer factory needs similar SSL properties:

```java
properties.put("security.protocol", "SSL");
properties.put(SslConfigs.SSL_TRUSTSTORE_LOCATION_CONFIG, truststoreLocation);
properties.put(SslConfigs.SSL_TRUSTSTORE_PASSWORD_CONFIG, truststorePassword);
properties.put(SslConfigs.SSL_TRUSTSTORE_TYPE_CONFIG, "PKCS12");
properties.put(SslConfigs.SSL_ENDPOINT_IDENTIFICATION_ALGORITHM_CONFIG, "https");
```

Set these properties on both the producer and consumer factories if both connections require TLS. If using Spring Boot auto-configuration, you do not need to manually recreate the factories just to enable SSL; the YAML configuration shown earlier is usually sufficient.

The Java example uses `System.getenv()` to illustrate a runtime configuration source. In real applications, validate environment variables at startup and fail clearly if a path or password is missing. Avoid including passwords in logs or exception messages.

## 9. Hostname Verification Matters

TLS does not just check whether a certificate was signed by a trusted CA. The client must also verify that the certificate belongs to the exact broker it is connecting to. The Kafka Java client defaults to `ssl.endpoint.identification.algorithm=https` to perform hostname verification.

For example, if a client connects to `broker-1.example.net:9093`, the server certificate needs the DNS SAN `broker-1.example.net`. If the broker advertises `kafka-1.internal` while the certificate only has SAN `broker-1.example.net`, the handshake can fail when the client connects to the advertised hostname.

Do not disable hostname verification by setting `ssl.endpoint.identification.algorithm` to an empty string as a "quick fix" for certificate errors. Doing so stops the client from verifying whether the broker has the expected hostname, opening the door to connecting to an imposter server if the CA or network is compromised.

If you encounter a hostname mismatch error, fix the certificate SAN or `advertised.listeners`/DNS so the connection hostname matches the certificate.

## 10. Kafka Broker Configuration

An application can only connect over TLS successfully when the broker also has an SSL listener and valid certificates. Illustrative broker configuration example:

```properties
listeners=SSL://0.0.0.0:9093
advertised.listeners=SSL://broker-1.example.net:9093
listener.security.protocol.map=SSL:SSL

ssl.keystore.location=/etc/kafka/secrets/broker.keystore.p12
ssl.keystore.password=${BROKER_KEYSTORE_PASSWORD}
ssl.key.password=${BROKER_PRIVATE_KEY_PASSWORD}
ssl.keystore.type=PKCS12

ssl.truststore.location=/etc/kafka/secrets/broker.truststore.p12
ssl.truststore.password=${BROKER_TRUSTSTORE_PASSWORD}
ssl.truststore.type=PKCS12
```

This is an illustrative configuration for an SSL listener; secret loading syntax depends on how Kafka is deployed. With one-way TLS, the broker does not necessarily require a client certificate. With mandatory mTLS:

```properties
ssl.client.auth=required
```

The broker truststore must trust the CA that signed the client certificate. If the cluster has multiple brokers, each broker needs a certificate SAN matching its advertised hostname. In KRaft or legacy ZooKeeper clusters, internal and controller listeners must be configured according to their own topology; do not blindly copy the client-facing listener configuration to every listener.

## 11. TLS for Producer, Consumer, and Kafka Admin

A Spring Kafka application can create multiple Kafka clients:

- `KafkaProducer` managed by `ProducerFactory`.
- `KafkaConsumer` managed by `ConsumerFactory`.
- `AdminClient` used by `KafkaAdmin` to inspect or create topics.

If you only configure SSL on the producer while the consumer still connects to a plaintext listener, half of the application remains unprotected. Identify all clients and bootstrap endpoints used by the application.

With shared configuration via `spring.kafka.properties`, Spring Boot can pass SSL settings to clients configured from the shared property map. When creating custom factories/admin clients or connecting to different clusters/endpoints, attach the appropriate SSL properties to each respective client.

## 12. TLS and SASL_SSL

If the cluster requires username/password or token authentication, use `SASL_SSL` to both encrypt the connection and authenticate via SASL. Example with SCRAM:

```yaml
spring:
  kafka:
    properties:
      "[security.protocol]": SASL_SSL
      "[sasl.mechanism]": SCRAM-SHA-512
      "[sasl.jaas.config]": org.apache.kafka.common.security.scram.ScramLoginModule required username="${KAFKA_USERNAME}" password="${KAFKA_PASSWORD}";
      "[ssl.truststore.location]": ${KAFKA_TRUSTSTORE_LOCATION}
      "[ssl.truststore.password]": ${KAFKA_TRUSTSTORE_PASSWORD}
      "[ssl.truststore.type]": PKCS12
      "[ssl.endpoint.identification.algorithm]": https
```

This example only illustrates combining TLS with SASL SCRAM. Passwords must be injected from a secret store; do not commit them to YAML. When using OAuth or another SASL mechanism, configure the callback handler, login module, and token provider accordingly.

TLS is responsible for protecting the transport channel and verifying certificates. SASL authenticates the application principal. Kafka ACLs determine which operations the principal is allowed to perform on topics and groups.

## 13. Certificate Management and Rotation

Certificates have expiration dates. Without tracking expiration dates, producers and consumers can lose connectivity when a certificate expires or when a CA is replaced.

A safe rotation workflow typically includes:

1. Issue the new CA/certificate and verify SANs, validity period, and key usage.
2. Update the client truststore to trust the new CA before brokers switch certificates, if a CA change is required.
3. Roll out the new certificate to brokers using an appropriate rolling strategy.
4. Update the client keystore if mTLS is used and client certificates are rotated.
5. Reinitialize or refresh Kafka clients using a mechanism supported by the application.
6. Verify handshakes, hostnames, producer sends, and consumer fetches on each broker.
7. Remove the old CA/certificate after all connections have switched over.

Spring Kafka's `DefaultKafkaProducerFactory` and `DefaultKafkaConsumerFactory` manage client lifecycles. Replacing truststore/keystore files on disk does not mean running Kafka clients automatically reload the new contents. You need a factory or application refresh/restart strategy suited to your version and deployment model.

Do not rotate a CA by removing the old CA before all brokers and clients have finished switching. Use an overlap period to avoid connection outages.

## 14. Protecting Secrets and Certificate Files

Truststore/keystore files and passwords must be managed as security-sensitive configuration:

- Store passwords in a secret manager or the environment's secret management platform.
- Mount certificates/keys as read-only files with minimal permissions.
- Do not commit keystores, private keys, or passwords to Git.
- Do not expose secrets in command lines, logs, exceptions, or diagnostic dumps.
- Separate certificates across dev/test/staging/production environments.
- Issue separate client certificates per service or workload so they can be revoked independently.
- Have a revocation procedure in case a private key is compromised.

The truststore holds public CA certificates, yet you should still manage changes and trusted sources carefully. Adding an untrusted CA to the truststore can cause clients to accept a rogue broker.

## 15. Testing TLS Connections

Testing must verify both the handshake and Kafka operations after the handshake.

### Verifying the TLS Handshake

- The client connects to the right hostname matching the certificate SAN.
- The certificate is within its validity period and the CA chain is complete.
- The truststore contains the appropriate CA.
- With mTLS, the broker accepts the client certificate and the client has the matching private key.
- Both sides support the negotiated TLS protocol/cipher.

### Spring Kafka Integration Testing

1. Start a test broker with an SSL listener.
2. Configure the Spring Boot producer/consumer to use the test truststore.
3. Send a record with `KafkaTemplate`.
4. Receive the record with `@KafkaListener`.
5. Verify metadata and payload are correct.
6. If using mTLS, repeat with a valid client certificate and verify that a client with a missing or untrusted certificate is rejected.
7. Verify that producer, consumer, and Kafka Admin all use the TLS endpoint as designed.

Do not rely solely on plaintext Embedded Kafka and conclude that TLS works. Use a test broker configured with SSL or mTLS similar to your real environment. You can verify the handshake independently with an appropriate TLS tool, but integration tests still need to verify the Kafka protocol after the handshake.

## 16. Common Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `SSLHandshakeException: PKIX path building failed` | Truststore is missing a CA/intermediate or the chain is invalid | Update the truststore with the correct CA chain |
| `No subject alternative DNS name matching` | Connection hostname is missing from the certificate SAN | Fix the SAN or hostname/advertised listener |
| `Keystore was tampered with, or password was incorrect` | Wrong password or wrong file type | Check password, file path, and `ssl.keystore.type` |
| `UnrecoverableKeyException` | Wrong private key password or invalid key entry | Check `ssl.key.password` and the private key |
| Broker requires client certificate but client does not send one | Keystore not configured or broker truststore does not trust client CA | Configure two-way mTLS and verify the certificate chain |
| Producer uses TLS but consumer fails with plaintext error | SSL properties were only set on the producer factory | Configure the consumer/admin client accordingly |
| Some brokers connect while others fail | Inconsistent SAN/chain/advertised listener | Check certificates and DNS on each broker |
| Connections fail after rotation | Old clients have not reloaded the new truststore or old CA was removed too early | Use CA overlap and controlled client refresh/restart |
| Handshake succeeds but topic operations are denied | TLS verified the channel, but the principal lacks Kafka ACL permissions | Grant appropriate topic/group/transactional ID permissions |

## 17. Deployment Checklist

- [ ] Brokers expose an SSL listener with the correct endpoint/port.
- [ ] Truststore contains trusted CAs and the full required chain.
- [ ] Broker certificates have SANs matching advertised hostnames.
- [ ] Hostname verification remains enabled.
- [ ] One-way TLS or mTLS is chosen according to requirements.
- [ ] If mTLS, broker truststore trusts the client CA and clients have valid keystores.
- [ ] Producer, consumer, and Kafka Admin all use TLS as designed.
- [ ] Secrets are injected from a secure environment and never committed to the repository.
- [ ] Certificate expiration and rotation have a tracking process.
- [ ] ACLs/authorization are configured separately alongside TLS.
- [ ] Integration tests use a real SSL/mTLS broker.
- [ ] Logs do not contain passwords or private keys.

## 18. Conclusion

TLS between an application and Kafka encrypts data in transit and lets the client verify brokers using certificates. With one-way TLS, the client needs a truststore to trust the CA that signed the broker certificate. With mTLS, the client adds a keystore containing its certificate and private key; the broker also needs a truststore trusting the client's CA.

In Spring Kafka, SSL configuration is passed to the Kafka client via `spring.kafka.properties` or the `ProducerFactory`/`ConsumerFactory` property map. Keep hostname verification enabled, keep certificate SANs aligned with `advertised.listeners`, and manage secrets and rotation in a controlled way. If principal authentication via username/password or token is needed, combine with `SASL_SSL`, then use Kafka ACLs to restrict permissions. TLS is a transport protection layer—it does not replace authorization and does not automatically encrypt data stored on the broker.

## References

- [Apache Kafka — Encryption and Authentication using SSL](https://kafka.apache.org/documentation/#security_ssl)
- [Apache Kafka — SSL Configurations](https://kafka.apache.org/documentation/#brokerconfigs_ssl)
- [Spring for Apache Kafka — Connecting to Kafka](https://docs.spring.io/spring-kafka/reference/kafka/connecting.html)
- [Spring Boot — Apache Kafka Support](https://docs.spring.io/spring-boot/reference/messaging/kafka.html)
