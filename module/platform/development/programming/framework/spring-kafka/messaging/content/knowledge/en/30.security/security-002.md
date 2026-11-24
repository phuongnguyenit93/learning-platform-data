# SASL and Authentication Mechanisms

Kafka needs to know which client is connecting before allowing it to use the cluster. **SASL (Simple Authentication and Security Layer)** is the mechanism for a client to prove its identity to the broker using an authentication mechanism such as PLAIN, SCRAM, GSSAPI, or OAUTHBEARER. In Spring Kafka, SASL settings are passed to the Kafka client via Spring Boot configuration or manually configured factories.

SASL answers the question **"who is the client?"**. After authentication, the broker still has to check **"what is the client allowed to do?"** using authorization, typically through ACLs. These two steps are independent: a successful login does not mean the client is allowed to read every topic, write to every topic, or join every consumer group.

This lesson belongs to the **Security** chapter of the **SPRING_KAFKA_MESSAGING** module, focusing on SASL mechanisms, how to combine SASL with TLS, and how to configure authentication for producers, consumers, and the Kafka Admin client in Spring Kafka.

## Learning Outcomes

After this lesson, you will be able to:

- Explain the role of SASL in the Kafka connection process.
- Distinguish authentication from authorization.
- Recognize the PLAIN, SCRAM, GSSAPI, and OAUTHBEARER mechanisms.
- Distinguish `SASL_SSL` from `SASL_PLAINTEXT`.
- Configure the SASL mechanism and JAAS login config in Spring Boot.
- Configure a TLS truststore to verify the broker.
- Apply shared configuration or separate credentials for producer, consumer, and `AdminClient`.
- Manage credentials using a secret store and plan rotation.
- Distinguish authentication errors, TLS errors, and ACL errors.
- Test connectivity and access permissions with least-privilege accounts.

## 1. Where Does SASL Fit in a Kafka Connection?

When a producer or consumer connects to a broker, the Kafka client establishes a network connection, negotiates the security protocol, and authenticates its identity before performing Kafka operations that require access permissions.

Overview flow:

~~~mermaid
sequenceDiagram
    participant Client as Spring Kafka client
    participant Broker as Kafka broker
    Client->>Broker: Open network connection
    opt SASL_SSL
        Client->>Broker: TLS handshake and verify broker certificate
        Broker-->>Client: TLS session established
    end
    Client->>Broker: SASL handshake (mechanism)
    Client->>Broker: SASL authentication exchange
    Broker-->>Client: Authentication result
    Client->>Broker: Kafka API request
    Broker->>Broker: Authorize principal against ACL
    Broker-->>Client: API response or authorization error
~~~

SASL does not replace the Kafka protocol. It is the authentication layer used during connection establishment. After authentication, the client proceeds to send requests such as Metadata, Produce, Fetch, OffsetCommit, or admin APIs.

With `SASL_SSL`, TLS protects the transport channel before SASL exchanges authentication credentials. With `SASL_PLAINTEXT`, SASL runs over an unencrypted connection; exchanged information can be eavesdropped on untrusted networks.

## 2. Authentication vs. Authorization

These two concepts are often confused:

| Concept | Question | Handled by Kafka Using |
|---|---|---|
| Authentication | Who is the client? | SASL mechanism or TLS client certificate authentication. |
| Authorization | What is the client allowed to do? | ACLs or the authorizer configured on the broker. |

Example:

- A producer logs in successfully as user `orders-publisher`.
- The broker determines the corresponding principal.
- An ACL allows that principal to write to topic `orders.created`.
- If the producer sends to `payments.private` without permission, the broker rejects it even though authentication succeeded.

A consumer typically needs permission to read the topic and permission to use the consumer group. Exact permissions depend on the API and cluster configuration, but successful authentication does not automatically grant read/write access.

Do not use SASL username/password as an authorization mechanism in application code. Access permissions must be configured and enforced on the broker.

## 3. Kafka Security Protocols

The Kafka client has a `security.protocol` property to choose the connection protection layer:

| Protocol | TLS Encryption | SASL Authentication | Purpose |
|---|---:|---:|---|
| `PLAINTEXT` | No | No | Unprotected connection, usually only for isolated local environments. |
| `SSL` | Yes | No | TLS, optionally combined with client certificate authentication. |
| `SASL_PLAINTEXT` | No | Yes | SASL over an unencrypted connection. |
| `SASL_SSL` | Yes | Yes | SASL authentication inside a TLS connection. |

For production clusters traversing networks that are not fully trusted, `SASL_SSL` should normally be chosen. `SASL_PLAINTEXT` does not encrypt Kafka traffic and does not protect credential confidentiality in transit.

TLS also lets the client verify the broker certificate to avoid connecting to the wrong endpoint. Do not disable hostname verification or certificate validation just to get a test connection working.

## 4. SASL/PLAIN

PLAIN is a simple SASL mechanism that uses a username and password for authentication. Client configuration typically declares a login module:

~~~properties
security.protocol=SASL_SSL
sasl.mechanism=PLAIN
sasl.jaas.config=org.apache.kafka.common.security.plain.PlainLoginModule required username="orders-app" password="secret";
~~~

PLAIN does not encrypt the username/password by itself. When used over `SASL_SSL`, TLS protects the credentials in transit. If used over `SASL_PLAINTEXT`, credentials are at risk of network exposure.

PLAIN is typically suitable when the Kafka platform provides username/password credentials and has configured SASL/PLAIN on the broker. How credentials are stored and verified on the broker depends on the deployment platform.

Do not write real passwords into source code, Git, Docker images, or logs. The example above only illustrates the JAAS structure; real values must be provided via secret management.

## 5. SASL/SCRAM

SCRAM (Salted Challenge Response Authentication Mechanism) uses a challenge-response flow to authenticate without sending the password directly like PLAIN. Kafka commonly supports:

- `SCRAM-SHA-256`
- `SCRAM-SHA-512`

Example:

~~~properties
security.protocol=SASL_SSL
sasl.mechanism=SCRAM-SHA-512
sasl.jaas.config=org.apache.kafka.common.security.scram.ScramLoginModule required username="orders-app" password="secret";
~~~

The broker must be configured to support the corresponding mechanism, and the user's SCRAM credentials must be provisioned beforehand. Client and broker must agree on the mechanism; if the client selects SHA-512 while the listener only supports SHA-256, authentication will fail.

SCRAM does not replace TLS. Use `SASL_SSL` to encrypt all traffic, protect metadata and payloads, and verify the broker certificate.

## 6. SASL/GSSAPI with Kerberos

GSSAPI is commonly used in enterprise environments integrated with Kerberos. The client authenticates using a principal and Kerberos ticket, typically obtaining the ticket via a keytab or the environment's login mechanism.

A JAAS login module can look like:

~~~properties
security.protocol=SASL_SSL
sasl.mechanism=GSSAPI
sasl.kerberos.service.name=kafka
sasl.jaas.config=com.sun.security.auth.module.Krb5LoginModule required useKeyTab=true storeKey=true keyTab="/run/secrets/orders.keytab" principal="orders-app@EXAMPLE.COM";
~~~

Kerberos configuration also depends on the realm, KDC, DNS, clock synchronization, the broker's service principal, and the `krb5.conf` file. A keytab is a sensitive credential; protect its read permissions and rotate it according to organizational policy.

GSSAPI is usually appropriate for infrastructure that already runs Kerberos. Do not choose this mechanism simply because Kafka supports it if your system does not operate a KDC and corresponding principals.

## 7. SASL/OAUTHBEARER

OAUTHBEARER lets clients authenticate using OAuth bearer tokens. The client needs a way to obtain tokens, refresh tokens, and provide tokens to the Kafka SASL callback handler.

Unlike PLAIN or SCRAM, which use static usernames/passwords in JAAS, OAuth usually depends on the identity provider, issuer, audience, scope, expiry, and a callback handler compatible with the Kafka platform.

Configuration may require properties such as:

~~~properties
security.protocol=SASL_SSL
sasl.mechanism=OAUTHBEARER
sasl.login.callback.handler.class=com.example.kafka.OAuthLoginCallbackHandler
~~~

The callback handler name and additional properties depend on the library or Kafka provider. There is no single generic callback handler configuration that works with every identity provider.

Do not hardcode long-lived bearer tokens in configuration files. Tokens should be short-lived and refreshed through a callback handler or provider-supported integration. When deploying OAuth, test token acquisition, refresh, and token expiration handling.

## 8. Which Mechanism Should You Choose?

| Mechanism | Credential | Key Considerations |
|---|---|---|
| PLAIN | Username/password | Easy to configure; must use TLS to protect in transit. |
| SCRAM-SHA-256/512 | Username/password + challenge-response | Broker must provision SCRAM credentials and support the exact hash mechanism. |
| GSSAPI | Kerberos principal/ticket | Requires KDC, service principal, keytab or ticket cache. |
| OAUTHBEARER | OAuth access token | Requires identity provider and callback handler for token management. |

The choice depends on your Kafka platform, existing identity system, credential issuance/revocation process, and security requirements. Producers and consumers do not have to use the same principal; separate identities can be issued by role to limit permissions.

Whichever mechanism you choose, verify that the broker listener has enabled that mechanism and the client uses the exact mechanism name. Spring Boot configuration alone does not enable SASL on the broker.

## 9. Configuring SASL/SCRAM in Spring Boot

Spring Boot forwards Kafka client properties via `spring.kafka.properties`. Example using SCRAM-SHA-512 and TLS:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1.example.net:9093,kafka-2.example.net:9093
    properties:
      security.protocol: SASL_SSL
      sasl.mechanism: SCRAM-SHA-512
      sasl.jaas.config: >-
        org.apache.kafka.common.security.scram.ScramLoginModule required
        username="${KAFKA_USERNAME}"
        password="${KAFKA_PASSWORD}";
      ssl.truststore.location: ${KAFKA_TRUSTSTORE_PATH}
      ssl.truststore.password: ${KAFKA_TRUSTSTORE_PASSWORD}
      ssl.truststore.type: PKCS12
~~~

In this example:

- `security.protocol` selects SASL combined with TLS.
- `sasl.mechanism` selects SCRAM-SHA-512.
- `sasl.jaas.config` specifies the login module and credentials.
- `ssl.truststore.*` helps the JVM trust the broker's certificate chain.

Placeholders must be supplied from the environment or secret integration at runtime. Do not put real values into committed YAML files.

If the broker certificate is signed by a CA already present in the JVM's default truststore, separate truststore configuration may not be necessary. Use a trust chain approved by your organization and do not disable certificate checks to bypass errors.

## 10. Configuring Separate Credentials for Producer and Consumer

If the producer and consumer use two different principals, you can set per-client properties instead of sharing credentials:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1.example.net:9093
    properties:
      security.protocol: SASL_SSL
      ssl.truststore.location: ${KAFKA_TRUSTSTORE_PATH}
      ssl.truststore.password: ${KAFKA_TRUSTSTORE_PASSWORD}
      ssl.truststore.type: PKCS12

    producer:
      properties:
        sasl.mechanism: SCRAM-SHA-512
        sasl.jaas.config: >-
          org.apache.kafka.common.security.scram.ScramLoginModule required
          username="${KAFKA_PRODUCER_USERNAME}"
          password="${KAFKA_PRODUCER_PASSWORD}";

    consumer:
      properties:
        sasl.mechanism: SCRAM-SHA-512
        sasl.jaas.config: >-
          org.apache.kafka.common.security.scram.ScramLoginModule required
          username="${KAFKA_CONSUMER_USERNAME}"
          password="${KAFKA_CONSUMER_PASSWORD}";
~~~

Separating principals helps restrict permissions:

- The producer only needs write permission on permitted topics.
- The consumer only needs read permission on permitted topics and groups.
- Operations or `AdminClient` accounts can use another principal with separate administrative permissions.

If producer and consumer share `spring.kafka.properties`, both usually inherit the same shared client properties. Properties under `spring.kafka.producer.properties` or `spring.kafka.consumer.properties` allow per-client overrides. Check the effective configuration when the application has multiple custom `ConsumerFactory`, `ProducerFactory`, or template beans.

## 11. Configuring SASL for the Kafka Admin Client

Spring Boot can create `KafkaAdmin` to provision or inspect topics. The admin client also needs proper authentication and authorization.

Separate properties can be configured:

~~~yaml
spring:
  kafka:
    admin:
      properties:
        security.protocol: SASL_SSL
        sasl.mechanism: SCRAM-SHA-512
        sasl.jaas.config: >-
          org.apache.kafka.common.security.scram.ScramLoginModule required
          username="${KAFKA_ADMIN_USERNAME}"
          password="${KAFKA_ADMIN_PASSWORD}";
        ssl.truststore.location: ${KAFKA_TRUSTSTORE_PATH}
        ssl.truststore.password: ${KAFKA_TRUSTSTORE_PASSWORD}
~~~

Do not use an administrative principal for producers/consumers just to avoid ACL errors. Grant dedicated `AdminClient` permissions only for required operations, such as describing or creating topics per an approved process.

If the application creates `AdminClient` manually with `AdminClient.create(props)`, you must pass the security configuration into that properties map. `spring.kafka.admin.properties` only applies to the Boot-autoconfigured `KafkaAdmin` and does not automatically modify custom-built `AdminClient` instances.

## 12. TLS Truststore and SASL Are Two Different Parts

In `SASL_SSL`, the two mechanisms have distinct responsibilities:

- TLS encrypts the connection and verifies the broker certificate.
- SASL authenticates the client principal.

The truststore holds CAs or certificates that the client trusts to verify the broker. It is not where SCRAM usernames/passwords are stored. If mutual TLS is used, the client keystore holds the client private key and certificate; that is a separate TLS authentication layer.

| Component | Function |
|---|---|
| Truststore | Trusts the broker's certificate chain. |
| Keystore | Holds the client's certificate/private key when mutual TLS is needed. |
| JAAS config | Provides the login module and credentials for SASL. |
| SASL mechanism | Specifies the authentication protocol. |
| ACL | Specifies what operations the principal is allowed to perform. |

If you encounter `SSLHandshakeException`, check the certificate chain, hostname, truststore, and certificate expiration. If you encounter `SaslAuthenticationException`, check the mechanism, username/password, token, or principal.

## 13. The Broker Must Be Configured Accordingly

The client only declares how to connect; the broker must have a matching listener. For example, if the client uses `SASL_SSL` with `SCRAM-SHA-512`, the corresponding broker listener must enable SASL over TLS and support that mechanism.

Broker/platform prerequisites typically include:

- The listener binds to the right port and protocol.
- The SASL mechanism chosen by the client is enabled.
- TLS certificates are configured for the listener.
- Corresponding SCRAM/OAuth/Kerberos users or credentials are provisioned.
- An authorizer and ACLs are configured if permissions need to be restricted.
- Network routes from the application to the broker are allowed.

Listener names, user provisioning mechanisms, and authorizer configuration depend on the Kafka distribution or managed Kafka service. Do not copy a broker configuration from another environment without verifying the version and platform.

## 14. ACLs After SASL Authentication Succeeds

After authentication, the broker creates a principal for the client. The authorizer uses the principal and ACLs to decide whether a request is allowed.

Examples of commonly needed permissions:

| Role | Commonly Needed Permissions |
|---|---|
| Producer | `WRITE` and usually `DESCRIBE` on the target topic. |
| Consumer | `READ` and usually `DESCRIBE` on the source topic; `READ` on the consumer group. |
| Topic admin | Topic/cluster administrative permissions matching the operations. |
| Transactional producer | Required permissions on the transactional ID along with topic/cluster permissions per the ACL model in use. |

Exact permissions depend on Kafka version, authorizer, operation, and resource pattern. When transactions are enabled, the producer may need permissions on the transactional ID in addition to topic write permissions.

Do not grant `ALL` to every principal just to make the application run. Start from actual operations, grant least-privilege permissions, and test authorization errors after authentication.

## 15. Managing Usernames, Passwords, Keytabs, and Tokens

Credentials are sensitive data. Principles to follow:

- Do not commit passwords, tokens, private keys, or keytabs to Git.
- Do not log the full JAAS config.
- Do not expose secrets in exception messages or diagnostic endpoints.
- Use Kubernetes Secrets, Vault, a cloud secret manager, or your organization's secret store.
- Restrict secret read access by service account and application identity.
- Encrypt secret data at rest and protect the distribution channel.
- Use separate credentials for producer, consumer, and `AdminClient` when appropriate.
- Revoke credentials when a service no longer needs access.
- Do not use personal developer accounts as production credentials.

Environment variables in examples are only an illustration of configuration injection. In production, protect both the source providing environment variables and process/container environment readability.

## 16. Credential Rotation

Credentials may need periodic rotation or immediate rotation if compromise is suspected. A safe process usually includes:

1. Create new credentials or update secrets according to broker capabilities.
2. If supported by the platform, maintain an overlap window where both old and new credentials are valid.
3. Update the application's secrets.
4. Recreate or restart clients/containers per the deployment procedure.
5. Verify that producer, consumer, and `AdminClient` authenticate with the new credentials.
6. Revoke the old credentials after all instances have switched over.
7. Monitor authentication and connection errors during the transition.

Do not assume changing an environment variable automatically updates the JAAS config of running Kafka clients. Existing producers/consumers typically retain the configuration and connections already created; refresh behavior depends on the mechanism, callback handler, and client lifecycle.

With OAuth, a callback handler can refresh tokens per supported integrations. With static username/password JAAS configs, recreating clients or restarting the application is usually needed to cleanly apply new credentials.

## 17. Distinguishing Authentication, TLS, and ACL Errors

| Symptom | Common Cause Group | What to Check |
|---|---|---|
| `SaslAuthenticationException` | Wrong username/password, token, principal, or JAAS | Check secrets, login module, and broker mechanism. |
| Unsupported SASL mechanism | Client mechanism not supported by listener | Compare `sasl.mechanism` against the broker listener. |
| `SSLHandshakeException` | Truststore, certificate, hostname, or TLS protocol | Check CA, hostname, and certificate expiration. |
| `TopicAuthorizationException` | Principal lacks topic permissions | Check ACLs for the topic and operation. |
| `GroupAuthorizationException` | Principal lacks consumer group permissions | Check ACLs for the group resource. |
| `ClusterAuthorizationException` | Missing cluster/admin operation permissions | Check corresponding admin permissions. |
| Timeout or disconnect | Network, DNS, listener, firewall, or broker unavailable | Check routes, bootstrap servers, and broker logs. |

Do not handle every connection error with infinite retries. Wrong passwords or missing ACLs do not fix themselves by waiting; continuous retries only create log noise and load on the broker. Classify errors to alert and fix configuration.

## 18. Testing SASL and Authorization

A security test suite should verify both valid connections and rejected behavior.

| Scenario | What to Verify |
|---|---|
| Valid credentials | Producer/consumer connect and perform authorized operations. |
| Wrong password | Authentication fails and no records are written/read. |
| Non-existent username | Broker rejects authentication. |
| Wrong mechanism | Client cannot complete the SASL handshake. |
| Untrusted certificate | TLS handshake fails before using Kafka APIs. |
| Hostname mismatch | Client rejects the certificate due to hostname verification. |
| Principal lacks WRITE permission | Produce is rejected even though authentication succeeded. |
| Consumer lacks READ on group | Group join/commit is rejected per ACL. |
| Admin lacks permissions | Administrative operations fail as expected. |
| Credential rotation | New instances connect with new secrets and old credentials are revoked on schedule. |

You can use Testcontainers or a test Kafka environment configured with SASL/TLS. You must create the broker listener, users, mechanism, and corresponding ACLs; configuring only the client in Spring Boot is not enough to establish a SASL test environment.

Integration tests should verify producer, consumer, and `AdminClient` if the application uses all three. Do not just check that the application starts up: connections to brokers can be created lazily, and errors may only appear when the client sends its first request.

## 19. Operations Checklist

Before taking a Spring Kafka application using SASL to production, verify:

- [ ] The broker listener enables the right security protocol and SASL mechanism.
- [ ] Clients use the right bootstrap servers and listener port.
- [ ] TLS certificates are verified with a valid truststore.
- [ ] Usernames/passwords, keytabs, or tokens are supplied from a secret store.
- [ ] Producer and consumer have separate principals when appropriate.
- [ ] ACLs grant only necessary permissions for topics, groups, transactional IDs, and administrative operations.
- [ ] Secrets do not appear in Git, images, logs, or diagnostic endpoints.
- [ ] A credential rotation and revocation process exists.
- [ ] Authentication errors are distinguished from TLS, network, and authorization errors.
- [ ] Alerts are configured for spikes in authentication failures and authorization denials.
- [ ] Integration tests verify both successful connections and denied permissions.
- [ ] Runbooks document the owner, secret locations, and connection recovery steps.

## 20. Capstone Exercise: Securing Order Service with SASL/SCRAM

Configure Spring Kafka so Order Service connects to the cluster via `SASL_SSL` and `SCRAM-SHA-512`.

Requirements:

1. Verify that the broker listener supports `SASL_SSL` and `SCRAM-SHA-512`.
2. Create separate principals for producer and consumer.
3. Provision SCRAM credentials on the broker or managed Kafka platform.
4. Configure `security.protocol`, `sasl.mechanism`, and `sasl.jaas.config`.
5. Configure the TLS truststore and verify the broker certificate.
6. Inject username/password from a secret store.
7. Configure the producer with `WRITE` permission only on topic `orders.created`.
8. Configure the consumer with `READ` permission on the topic and `READ` on group `orders-fulfillment`.
9. Use `AdminClient` with a separate administrative principal if creating or describing topics is needed.
10. Test a wrong password and observe the authentication failure.
11. Test a mechanism not supported by the broker.
12. Test producing to an unauthorized topic and verify the authorization failure.
13. Rotate credentials in a test environment and verify new clients connect with the new secret.
14. Verify logs do not contain passwords, tokens, or JAAS secrets.
15. Write integration tests and a runbook for handling authentication/authorization errors.

The exercise is complete when producer, consumer, and `AdminClient` authenticate as the proper principals, each principal can only perform its granted operations, TLS verifies the broker, and credentials can be rotated without exposure.

## 21. Learning Path and Completion Criteria

| Stage | Core Content | Self-Check Criteria |
|---|---|---|
| 1. Security model | Authentication and authorization | Distinguish client identity from operation permissions. |
| 2. Protocol | `PLAINTEXT`, `SSL`, `SASL_PLAINTEXT`, `SASL_SSL` | Choose the right protocol for security requirements. |
| 3. Mechanisms | PLAIN, SCRAM, GSSAPI, OAUTHBEARER | Explain credentials and broker support requirements. |
| 4. Spring Boot | Kafka client properties and JAAS | Configure producer/consumer with the right mechanism. |
| 5. TLS | Truststore and certificate verification | Verify the broker certificate. |
| 6. Client identities | Producer, consumer, and `AdminClient` | Use role-based principals. |
| 7. ACL | Topic, group, transactional ID | Grant least-privilege permissions for needed operations. |
| 8. Secrets | Secret store and credential rotation | Never commit/log secrets and rotate credentials cleanly. |
| 9. Troubleshooting | SASL, TLS, ACL, and network errors | Identify the exact failing layer. |
| 10. Testing/operations | Negative tests, metrics, runbooks | Prove valid connections and proper permission denials. |

The lesson is complete when you can choose an appropriate SASL mechanism, configure Spring Kafka clients with TLS, authenticate producer/consumer/`AdminClient` with separate principals, and distinguish authentication errors from authorization errors. You should also have processes for secret management, rotation, and access control testing.

SASL verifies client identity; ACLs decide what the client may do; TLS protects the connection and verifies the broker. When all three parts are configured properly, a Spring Kafka application can connect securely to Kafka and access only its granted topics, groups, or resources.

