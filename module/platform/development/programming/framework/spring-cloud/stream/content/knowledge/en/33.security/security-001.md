# Authenticating and Encrypting Kafka Connections with SASL, SSL, and TLS

## Objectives

A Spring Cloud Stream application connects to Kafka through the clients created by the Kafka binder: producer, consumer, AdminClient, and, for the corresponding processing model, Kafka Streams. In production, the connection must verify the correct broker, encrypt data in transit, authenticate the application's identity, and restrict access by topic/group.

Kafka provides two sets of mechanisms that are commonly configured together:

- **SSL/TLS** protects data in transit with encryption and verifies the broker's certificate. Kafka still uses the `ssl.*` configuration prefix even though the actual security protocol is TLS.
- **SASL** authenticates client identity using mechanisms such as SCRAM, PLAIN, Kerberos, or OAuth.
- **mTLS** is TLS with mutual certificate authentication: the broker verifies the client certificate when the listener requires it.
- **ACL** determines which resources an authenticated principal is allowed to read, write, or administer.

This lesson focuses on Spring Cloud Stream Kafka binder client configuration, distinguishing SSL/SASL protocols, setting up truststores/keystores, using JAAS for SASL, configuring the Kafka Streams binder, managing secrets, and testing secure connections.

After this lesson, you will be able to:

- Distinguish between TLS encryption, SASL authentication, mTLS certificate authentication, and ACL authorization.
- Choose the right security.protocol: SSL, SASL_SSL, or SASL_PLAINTEXT.
- Configure a truststore to verify the broker's certificate.
- Configure a keystore when the broker requires a client certificate.
- Configure SASL/PLAIN, SCRAM, GSSAPI, or OAUTHBEARER according to the broker.
- Place security properties in the Kafka binder namespace.
- Distinguish between configuring the regular Kafka binder and the Kafka Streams binder.
- Manage JAAS, credentials, and certificates using secret management.
- Grant least-privilege ACLs for producers, consumers, groups, and internal topics.
- Test TLS handshake, SASL authentication, authorization, and troubleshoot common errors.

## 1. Three Security Layers to Distinguish

A secure Kafka connection typically requires multiple layers. They answer different questions:

| Layer | Question Answered | Mechanism |
|---|---|---|
| Transport encryption | Can an eavesdropper on the network read the data? | TLS |
| Authentication | Who is the connecting client? Is the broker's identity genuine? | SASL, server certificate, mTLS |
| Authorization | What is this principal allowed to do? | Kafka ACL or authorizer |

TLS encrypts data between the client and the broker. In standard TLS, the client verifies the server certificate; the broker does not necessarily verify the client's identity at the certificate layer. If the broker enables client authentication, the client must present a certificate signed by a CA that the broker trusts.

SASL authenticates the Kafka principal using a mechanism enabled on the broker. When using SASL_SSL, TLS protects the handshake and data, while SASL authenticates the Kafka identity. After authentication, the broker uses the principal to check ACLs.

A client can establish a TLS connection successfully and still be rejected due to invalid SASL credentials. A client can also authenticate via SASL successfully and still get a TopicAuthorizationException if the principal lacks permissions on the topic.

## 2. security.protocol Values

Kafka clients use the security.protocol property to select the connection type:

| security.protocol | TLS Encryption | SASL Authentication | Scenario |
|---|---|---|---|
| PLAINTEXT | No | No | Isolated test environments only, with no sensitive data or credentials |
| SSL | Yes | No | TLS server authentication; mTLS can be added |
| SASL_PLAINTEXT | No | Yes | Only in controlled test environments; credentials are not encrypted in transit |
| SASL_SSL | Yes | Yes | Common choice for production when using SASL |

SSL is the protocol name in Kafka configuration and the prefix of client properties; modern connections use TLS. There is no separate Kafka protocol named TLS required to enable encryption.

**SASL_SSL** is usually the appropriate choice when the application needs both principal authentication via SASL and transport encryption via TLS. **SSL** is suitable when the system uses client certificates for authentication or only requires TLS server authentication per policy. Avoid using SASL_PLAINTEXT on untrusted networks because usernames/passwords or authentication data can be exposed.

## 3. How Does TLS Protect the Connection?

During the TLS handshake, the client and broker negotiate a cipher suite, verify certificates, and establish a session key. After the handshake, Kafka protocol data is transmitted inside the TLS channel.

To verify the broker, the client needs to trust the CA that signed the server certificate. The broker certificate must have a Subject Alternative Name (SAN) matching the hostname or IP that the client uses to connect.

Connection flow:

    Spring Cloud Stream application
        -> Kafka binder / Kafka client
        -> TLS handshake
        -> Verify certificate chain and broker hostname
        -> (If using SASL_SSL) SASL authentication
        -> Kafka authorization via ACL
        -> Produce / consume / metadata request

If the hostname in bootstrap.servers is kafka-1.example.internal but the certificate's SAN only contains kafka-old.example.internal, hostname verification will fail even if the truststore has the right CA.

Kafka clients enable hostname verification by default in modern versions. The ssl.endpoint.identification.algorithm property is typically https. Do not disable hostname verification with an empty string just to bypass certificate errors; fix the SAN, DNS, or advertised.listeners address instead.

## 4. How Do Truststore and Keystore Differ?

These two store types are often confused:

| Store | What does it contain? | Who uses it? | Purpose |
|---|---|---|---|
| Truststore | CAs or certificates that the connecting party trusts | Client trusts broker; broker trusts client CA in mTLS | Verify the peer's certificate |
| Keystore | Private key and certificate chain of the party's own identity | Broker holds server identity; client holds client identity in mTLS | Present identity using a certificate |

With standard one-way TLS:

- The broker has a keystore containing its private key and server certificate.
- The client has a truststore containing the CA that signed the server certificate.
- The client does not need a keystore if the broker does not require a client certificate.

With mutual TLS:

- The client still has a truststore to verify the broker.
- The client additionally has a keystore containing the client private key and certificate.
- The broker configures client authentication and a truststore containing the CA that signed the client certificate.

The private key in a keystore is sensitive data. A truststore containing public CAs is usually not secret, though you still need to control its issuing source to avoid trusting an untrusted CA.

## 5. Configuring TLS-Only in the Kafka Binder

If the broker listener uses TLS and does not require SASL, the regular Kafka binder can configure SSL as follows:

    spring:
      cloud:
        stream:
          kafka:
            binder:
              brokers: kafka-1.example.internal:9093,kafka-2.example.internal:9093
              configuration:
                security.protocol: SSL
                ssl.truststore.location: ${KAFKA_TRUSTSTORE_LOCATION}
                ssl.truststore.password: ${KAFKA_TRUSTSTORE_PASSWORD}
                ssl.truststore.type: PKCS12
                ssl.endpoint.identification.algorithm: https
                ssl.enabled.protocols: TLSv1.2,TLSv1.3

Key properties:

- brokers must point to the TLS listener, not the PLAINTEXT listener.
- security.protocol: SSL enables TLS for the Kafka client.
- ssl.truststore.location is the truststore path inside the container/host running the application.
- ssl.truststore.password unlocks the truststore if the store has a password.
- ssl.truststore.type must match the actual format, such as PKCS12 or JKS.
- ssl.endpoint.identification.algorithm enables hostname verification.
- ssl.enabled.protocols restricts the TLS versions allowed to be negotiated.

TLS 1.2 is a widely compatible baseline; TLS 1.3 can be enabled when the JDK, Kafka client, and broker all support it. Do not enable older TLS versions just for compatibility with an end-of-life broker; upgrade the endpoint or establish a time-bound compatibility plan.

## 6. Configuring mTLS When the Broker Requires a Client Certificate

If the listener requires a client certificate, the broker needs to verify the client's certificate chain. The client adds a keystore:

    spring:
      cloud:
        stream:
          kafka:
            binder:
              brokers: kafka-1.example.internal:9093
              configuration:
                security.protocol: SSL
                ssl.truststore.location: ${KAFKA_TRUSTSTORE_LOCATION}
                ssl.truststore.password: ${KAFKA_TRUSTSTORE_PASSWORD}
                ssl.truststore.type: PKCS12
                ssl.keystore.location: ${KAFKA_KEYSTORE_LOCATION}
                ssl.keystore.password: ${KAFKA_KEYSTORE_PASSWORD}
                ssl.key.password: ${KAFKA_PRIVATE_KEY_PASSWORD}
                ssl.keystore.type: PKCS12
                ssl.endpoint.identification.algorithm: https

In the example:

- The truststore helps the client verify the broker.
- The keystore contains the client certificate and private key.
- ssl.keystore.password unlocks the keystore.
- ssl.key.password unlocks the private key if the private key has its own password.

On the broker side, client authentication must be enabled, such as ssl.client.auth=required, with a truststore containing the CA that signed the client certificate. If the broker only requires TLS server authentication, there is no need to provide a client keystore.

When combining mTLS with SASL, the client can both present a client certificate during the TLS handshake and perform SASL authentication. Both layers can coexist if the cluster's listener and policies are configured accordingly.

## 7. Combining SASL_SSL and SCRAM

SCRAM-SHA-256 and SCRAM-SHA-512 authenticate username/password via challenge-response. Kafka supports SCRAM on both brokers and clients; the mechanism must be enabled on the broker, and the client must select the exact mechanism name.

Example of a regular Kafka binder using SASL_SSL with SCRAM-SHA-512:

    spring:
      cloud:
        stream:
          kafka:
            binder:
              brokers: kafka-1.example.internal:9093,kafka-2.example.internal:9093
              configuration:
                security.protocol: SASL_SSL
                sasl.mechanism: SCRAM-SHA-512
                sasl.jaas.config: 'org.apache.kafka.common.security.scram.ScramLoginModule required username="${KAFKA_USERNAME}" password="${KAFKA_PASSWORD}";'
                ssl.truststore.location: ${KAFKA_TRUSTSTORE_LOCATION}
                ssl.truststore.password: ${KAFKA_TRUSTSTORE_PASSWORD}
                ssl.truststore.type: PKCS12
                ssl.endpoint.identification.algorithm: https
                ssl.enabled.protocols: TLSv1.2,TLSv1.3

The JAAS config specifies the login module and credentials. The placeholders in the example are resolved from external configuration; never commit real usernames/passwords into source control.

The broker must enable SCRAM-SHA-512 on the listener and have credentials created for the principal. Configuring the client alone does not create the user or credentials on the broker. User provisioning should be managed using cluster admin tools and privileges.

SCRAM should run over TLS. TLS prevents eavesdroppers from observing the authentication exchange and protects Kafka data after authentication.

## 8. Common SASL Mechanisms

| Mechanism | Authentication Method | When to Use | Notes |
|---|---|---|---|
| PLAIN | Username/password | Systems with a user store or authentication callback | Use only with TLS in production |
| SCRAM-SHA-256 | Challenge-response with SCRAM credentials | Username/password without sending the password directly in the SASL exchange | Use TLS and strong passwords |
| SCRAM-SHA-512 | Challenge-response with SHA-512 | Common choice for clusters supporting SCRAM | Broker must provision credentials and enable the mechanism |
| GSSAPI | Kerberos ticket/principal | Environments already using Kerberos or Active Directory | Requires service principal, keytab, and krb5 config |
| OAUTHBEARER | OAuth bearer token | Integration with an identity provider/token service | Requires a production-grade callback/token handler |

The mechanism name in the configuration must match the broker listener. If the broker only enables SCRAM-SHA-256 while the client selects SCRAM-SHA-512, the handshake will fail.

### PLAIN

The client uses the login module:

    sasl.mechanism: PLAIN
    sasl.jaas.config: 'org.apache.kafka.common.security.plain.PlainLoginModule required username="${KAFKA_USERNAME}" password="${KAFKA_PASSWORD}";'

PLAIN does not encrypt the password itself. Use SASL_SSL so TLS protects credentials and data over the network. Do not use SASL_PLAINTEXT for PLAIN credentials in production environments.

### Kerberos/GSSAPI

A client configuration can use a keytab:

    sasl.mechanism: GSSAPI
    sasl.kerberos.service.name: kafka
    sasl.jaas.config: 'com.sun.security.auth.module.Krb5LoginModule required useKeyTab=true storeKey=true keyTab="${KAFKA_KEYTAB}" principal="${KAFKA_PRINCIPAL}";'

The application needs a valid krb5.conf and read permission for the keytab. The service name must match the broker's service principal. In a Kerberos environment, use consistent FQDNs for bootstrap.servers and advertised.listeners to avoid DNS/SPN errors.

### OAuth/OAUTHBEARER

OAuth bearer allows the client to use a token issued by an identity provider. Configuration typically requires sasl.mechanism=OAUTHBEARER and a callback handler compatible with the token issuance/refresh system. Kafka has a default implementation intended for development; do not use those unsecured tokens in production.

For production OAuth, use a callback handler or platform-provided integration to fetch, refresh, and verify tokens. Do not hardcode long-lived access tokens in YAML; handle expiration, clock skew, and credential revocation.

## 9. Security Configuration in the Spring Cloud Stream Regular Kafka Binder

Spring Cloud Stream provides the property:

    spring.cloud.stream.kafka.binder.configuration

This map passes Kafka client properties to the clients created by the binder. Therefore, you can place security.protocol, sasl.mechanism, sasl.jaas.config, and ssl.* properties here.

Flat property example:

    spring.cloud.stream.kafka.binder.configuration.security.protocol=SASL_SSL
    spring.cloud.stream.kafka.binder.configuration.sasl.mechanism=SCRAM-SHA-512
    spring.cloud.stream.kafka.binder.configuration.ssl.endpoint.identification.algorithm=https

You can use a nested YAML map as shown in the earlier examples. Security properties apply to the clients created by the binder, including producer, consumer, and AdminClient according to the binder configuration.

This matters because an application might send messages successfully while AdminClient fails to create topics due to missing configuration or ACLs. When security is enabled, check every client path, not just the producer or consumer.

In production environments, auto topic creation/partition management is usually disabled in the application, and topics/ACLs are provisioned through administrative workflows. The runtime account does not necessarily have admin permissions to create or alter topics.

## 10. Security Configuration for the Kafka Streams Binder

The Kafka Streams binder has its own configuration namespace. If the application uses functions accepting KStream/KTable, security properties must be placed under the Kafka Streams binder configuration:

    spring:
      cloud:
        stream:
          kafka:
            streams:
              binder:
                brokers: kafka-1.example.internal:9093
                configuration:
                  security.protocol: SASL_SSL
                  sasl.mechanism: SCRAM-SHA-512
                  sasl.jaas.config: 'org.apache.kafka.common.security.scram.ScramLoginModule required username="${KAFKA_USERNAME}" password="${KAFKA_PASSWORD}";'
                  ssl.truststore.location: ${KAFKA_TRUSTSTORE_LOCATION}
                  ssl.truststore.password: ${KAFKA_TRUSTSTORE_PASSWORD}
                  ssl.truststore.type: PKCS12
                  ssl.endpoint.identification.algorithm: https

This is the Kafka Streams binder namespace, not the regular Kafka binder. Do not copy the configuration into spring.cloud.stream.kafka.binder and assume the Kafka Streams topology will automatically pick it up.

Kafka Streams also needs permissions for the applicationId consumer group and internal topics such as changelog/repartition topics. The principal's ACLs must allow reading input topics, writing output topics, and performing the necessary operations on internal topics. When transactions or idempotent producers are enabled, add the appropriate permissions for the transactional ID per application configuration.

If the application uses multiple binders, each binder may require its own brokers, credentials, truststore, and ACLs.

## 11. Multiple Kafka Clusters with Separate Credentials

Spring Cloud Stream supports multiple binder instances. Each binder can have its own environment to configure a separate cluster and SASL JAAS.

Configuration skeleton example:

    spring:
      cloud:
        stream:
          binders:
            secureKafkaA:
              type: kafka
              environment:
                spring:
                  cloud:
                    stream:
                      kafka:
                        binder:
                          brokers: kafka-a.example.internal:9093
                          configuration:
                            security.protocol: SASL_SSL
                            sasl.mechanism: SCRAM-SHA-512
                            sasl.jaas.config: 'org.apache.kafka.common.security.scram.ScramLoginModule required username="${KAFKA_A_USERNAME}" password="${KAFKA_A_PASSWORD}";'
                            ssl.truststore.location: ${KAFKA_A_TRUSTSTORE}
                            ssl.truststore.password: ${KAFKA_A_TRUSTSTORE_PASSWORD}
            secureKafkaB:
              type: kafka
              environment:
                spring:
                  cloud:
                    stream:
                      kafka:
                        binder:
                          brokers: kafka-b.example.internal:9093
                          configuration:
                            security.protocol: SASL_SSL
                            sasl.mechanism: SCRAM-SHA-512
                            sasl.jaas.config: 'org.apache.kafka.common.security.scram.ScramLoginModule required username="${KAFKA_B_USERNAME}" password="${KAFKA_B_PASSWORD}";'
                            ssl.truststore.location: ${KAFKA_B_TRUSTSTORE}
                            ssl.truststore.password: ${KAFKA_B_TRUSTSTORE_PASSWORD}
          bindings:
            orders-out-0:
              destination: orders.secure
              binder: secureKafkaA
            audit-out-0:
              destination: audit.secure
              binder: secureKafkaB

Each binder has its own environment and credentials. Do not share the same JAAS string between two clusters if the principal or password differs. Ensure each binding is assigned to the right binder and each truststore contains the CA of the corresponding cluster.

If JAAS is configured via the sasl.jaas.config property, that property takes high precedence when selecting the login configuration. Spring Cloud Stream also supports JAAS files and certain Spring Boot JAAS properties. Do not mix a JAAS file with Spring Boot JAAS properties in the same application when binder documentation notes that the java.security.auth.login.config system property may cause Spring Cloud Stream to ignore the Boot configuration.

## 12. Corresponding Broker Listener Configuration

Client and broker must agree on the protocol. If the client uses SASL_SSL, the broker must have a SASL_SSL listener, a valid certificate, and the corresponding SASL mechanism enabled.

Minimal broker configuration example for a SCRAM-over-TLS listener:

    listeners=SASL_SSL://0.0.0.0:9093
    advertised.listeners=SASL_SSL://kafka-1.example.internal:9093
    sasl.enabled.mechanisms=SCRAM-SHA-512
    ssl.keystore.type=PKCS12
    ssl.keystore.location=/etc/kafka/secrets/broker.keystore.p12
    ssl.keystore.password=<broker-keystore-password>
    ssl.key.password=<broker-private-key-password>
    ssl.client.auth=none

The broker holds its private key and server certificate in its keystore. The client needs to trust the CA that signed that certificate. For mTLS, set ssl.client.auth=required and configure a broker truststore containing the CA that signed the client certificate.

A real-world listener setup also needs internal listeners, controller/inter-broker listeners, advertised listeners, an ACL authorizer, and credential provisioning. Do not copy a minimal example directly into a production cluster without defining the broker topology.

### Broker Enabling a SASL Mechanism

Example where the broker enables only SCRAM-SHA-512:

    sasl.enabled.mechanisms=SCRAM-SHA-512

Create credentials for the client principal using Kafka's admin tool according to the cluster version. With KRaft, SCRAM credentials are stored in the metadata log. Do not create users on the client side only; the broker must have the corresponding credentials or integrate with an authentication backend.

## 13. JAAS Files and Spring Boot Properties

There are two common ways to provide JAAS:

1. The sasl.jaas.config client property, typically placed in the Kafka binder configuration.
2. A JAAS file loaded by the JVM via the java.security.auth.login.config system property.

Example JAAS file for a Kerberos client:

    KafkaClient {
        com.sun.security.auth.module.Krb5LoginModule required
        useKeyTab=true
        storeKey=true
        keyTab="/etc/security/keytabs/kafka-client.keytab"
        principal="stream-service@EXAMPLE.COM";
    };

Launch the JVM with:

    -Djava.security.auth.login.config=/etc/kafka/kafka-client-jaas.conf
    -Djava.security.krb5.conf=/etc/krb5.conf

If using a JAAS file, ensure the file is readable only by the user running the application. For password-based mechanisms, do not commit files containing credentials to the repository.

Spring Cloud Stream also provides the properties jaas.loginModule, jaas.controlFlag, and jaas.options for the login context supported by the binder, which are particularly useful with Kerberos. For SCRAM/PLAIN, the sasl.jaas.config client property is a direct way to supply the login module and options.

Do not mix JAAS strategies in the same application without understanding precedence. Check startup logs and the effective client configuration to see which configuration is actually used.

## 14. TLS Certificates, Hostnames, and Trust Chains

Steps to prepare certificates:

1. Use an internal CA or an organization-trusted CA to issue a certificate for each broker.
2. Each broker holds its private key and certificate chain in its keystore.
3. The certificate's SAN must include the hostname/IP in advertised.listeners that clients will connect to.
4. The client truststore contains the root CA and any required intermediate CAs.
5. If using mTLS, the client has its own certificate/private key and the broker trusts the CA that signed that certificate.
6. Establish certificate validity periods, rotation schedules, and expiration alerts.

Do not use arbitrary self-signed certificates in production. If using an internal CA, manage the CA private key as a highly sensitive asset. Do not distribute the CA signing key to client applications; clients only need the public CA certificate in their truststore.

When the broker returns metadata, the client may connect to other brokers listed in advertised.listeners. Every advertised hostname must be resolvable and the corresponding broker certificate must have a SAN matching that hostname. A correct bootstrap server with an incorrect advertised listener can still cause errors after the initial metadata request.

### Checking Certificates

You can use openssl to inspect the certificate and SAN:

    openssl s_client -connect kafka-1.example.internal:9093 -servername kafka-1.example.internal -showcerts

This command helps verify the TLS handshake and chain at the TLS level. It does not verify SASL authentication or Kafka ACLs. When testing with openssl, use the actual hostname so SNI and hostname verification are meaningful.

## 15. Managing Credentials and Secrets

Do not commit passwords, tokens, private key passwords, or JAAS strings with real credentials to Git. Configurations should reference secrets from the deployment environment:

    sasl.jaas.config: 'org.apache.kafka.common.security.scram.ScramLoginModule required username="${KAFKA_USERNAME}" password="${KAFKA_PASSWORD}";'

Secret sources can be Kubernetes Secrets, Vault, a cloud secret manager, or Spring Boot config trees. Ensure secrets are injected into the right process and do not appear in logs, actuator endpoints, diagnostic dumps, or error messages.

Key principles:

- Use a dedicated principal per service/environment.
- Do not use a superuser account for runtime applications.
- Restrict read permissions on secrets and private keys.
- Rotate passwords/tokens/certificates on a schedule.
- Have a credential update process that does not disrupt all replicas simultaneously.
- Mask sensitive values in logs and displayed configurations.
- Do not pass passwords via the command line if they could be listed in the process list or shell history.
- Check YAML/JAAS escaping when passwords contain quotes, backslashes, or special characters.

When rotating certificates, an overlap period may be needed: brokers/clients trust both the old and new CAs or certificates during the transition. The rollout order must ensure new clients trust the new broker before the broker switches certificates, and new client certificates are trusted by the broker before the client uses them.

## 16. SASL Authentication Does Not Replace ACLs

After the client authenticates, Kafka creates a principal. The authorizer checks whether that principal has permissions on the resource.

Examples of commonly required permissions:

| Client role | Resource | Permissions to Consider |
|---|---|---|
| Producer | Output topic | Write, Describe |
| Consumer | Input topic | Read, Describe |
| Consumer | Consumer group | Read |
| Kafka Streams | Input/output topics | Read/Write |
| Kafka Streams | Application group | Read and required group permissions |
| Kafka Streams | Changelog/repartition topics | Read/Write/Describe, sometimes Create |
| AdminClient | Topic/cluster | Describe, or Create/Alter if the application is allowed to administer |
| Transactional producer | Transactional ID | Appropriate transaction permissions |

The Kafka CLI has convenience ACLs for producers and consumers, but a Kafka Streams topology adds internal topics, groups, and sometimes transactional IDs. You must verify actual permissions based on the topology and enabled features.

In secure environments, topics, partitions, ACLs, and internal topic policies are usually provisioned through administrative processes. If autoCreateTopics/autoAddPartitions are disabled, operations teams need to pre-create the required destinations. A runtime account might only have produce/consume permissions rather than topic creation rights.

Do not use allow.everyone.if.no.acl.found=true in production as a quick fix for authorization errors. That setting can open any resource without an ACL to every principal.

## 17. Testing Secure Connections

Testing should isolate the layers so you know where a failure occurs.

| Test | What to Prove | How to Perform |
|---|---|---|
| TLS handshake | Client trusts the certificate chain and broker hostname | openssl or Kafka client with truststore |
| SASL authentication | Credentials/mechanism are valid | Kafka CLI or application client |
| Authorization | Principal has the right ACLs | Attempt to read/write the target topic/group |
| Binder startup | All binder clients use the security config | Start the Spring context and check binder logs |
| Produce/consume | Message flow actually works | Send and receive messages through bindings |
| Kafka Streams | Input/output/internal topics are permitted | Start topology, create state, and verify changelog |
| Negative test | Invalid credentials/CA/ACLs are rejected | Use wrong credentials or truststore in a test environment |

### Testing with the Kafka CLI

Create a client.properties file containing the secure client configuration:

    security.protocol=SASL_SSL
    sasl.mechanism=SCRAM-SHA-512
    sasl.jaas.config=org.apache.kafka.common.security.scram.ScramLoginModule required username="stream-service" password="secret-from-test-secret";
    ssl.truststore.location=/etc/kafka/client.truststore.p12
    ssl.truststore.password=<test-truststore-password>
    ssl.truststore.type=PKCS12
    ssl.endpoint.identification.algorithm=https

Use this file with Kafka tools:

    bin/kafka-broker-api-versions.sh --bootstrap-server kafka-1.example.internal:9093 --command-config client.properties
    bin/kafka-topics.sh --bootstrap-server kafka-1.example.internal:9093 --command-config client.properties --list

These commands verify the Kafka connection and permissions for the corresponding requests. Listing/describing the cluster or topics may require separate ACLs. Do not put real passwords in shell commands; only use a secure file with restricted read permissions and delete the test file when no longer needed.

### Integration Tests with Spring Cloud Stream

Use a test broker configured with TLS/SASL equivalent to production. The in-memory test binder does not perform a TLS handshake and does not verify SASL/ACLs, so it cannot replace a broker integration test.

Tests should verify:

1. The Spring context starts with the right security properties.
2. AdminClient fetches metadata or checks topics successfully.
3. The producer sends messages through the output binding.
4. The consumer receives messages through the input binding.
5. The principal is rejected when using an incorrect password.
6. The client is rejected when the truststore does not trust the CA.
7. Hostname mismatch is detected.
8. A valid principal lacking ACLs receives an authorization error.
9. The Kafka Streams binder creates/reads/writes internal topics with proper permissions.
10. Certificate/password rotation causes no unplanned disruption.

Run negative test cases in a dedicated cluster; do not repeatedly test invalid credentials against production as this can trigger rate limits, alerts, or lockouts in the authentication backend.

## 18. Diagnosing Common Errors

| Error | Possible Cause | Resolution |
|---|---|---|
| SSLHandshakeException: PKIX path building failed | Truststore is missing the CA/intermediate or certificate chain is incomplete | Update truststore and inspect the chain |
| No subject alternative names matching | Hostname used by client is missing from the certificate SAN | Fix SAN, DNS, or advertised.listeners |
| Received fatal alert: bad_certificate | Client certificate is not trusted by broker or key/chain is invalid | Check client keystore and broker truststore |
| SaslAuthenticationException | Incorrect username/password, invalid JAAS, or principal not provisioned | Check mechanism, JAAS, and broker credentials |
| UnsupportedSaslMechanismException | Client selected a mechanism not enabled on the broker | Align sasl.mechanism and sasl.enabled.mechanisms |
| TopicAuthorizationException | Principal lacks permissions on the topic | Grant ACL for the exact resource/operation |
| GroupAuthorizationException | Consumer lacks permissions on the group | Grant Read ACL for the consumer group |
| ClusterAuthorizationException | AdminClient lacks cluster-level permissions | Determine if binder is creating/describing topics; grant least-privilege permissions |
| Timeout after successful bootstrap | Incorrect advertised.listeners, DNS, or firewall | Check all broker endpoints returned in metadata |
| SSL keystore password incorrect | Wrong store password or key password | Distinguish ssl.keystore.password and ssl.key.password |
| Client cannot find truststore | Path in container does not exist or mount is wrong | Check secret volume and file permissions |
| SASL config has no effect | Property placed in wrong namespace or overridden by JAAS file | Check binder config and JAAS precedence |
| Kafka Streams fails to start | Missing ACLs for group/internal topics or config in wrong binder | Check applicationId, Streams binder namespace, and ACLs |
| Topic is not created | Runtime principal lacks Create permission | Provision topic via admin or grant controlled permission |

### Distinguishing TLS, SASL, and ACL Errors

- If the TLS handshake fails, the client has not reached the SASL authentication step yet.
- If TLS succeeds but SASL fails, check the mechanism, credentials, and JAAS.
- If SASL succeeds but requests are rejected, check ACLs and the principal.
- If bootstrap succeeds but requests to another broker time out, check advertised.listeners, DNS, and the certificate SAN of each broker.

Do not disable hostname verification or switch to PLAINTEXT to mask errors. Fix the root cause in the certificate, DNS, credentials, or ACLs.

## 19. Production Deployment Checklist

Before releasing a Spring Cloud Stream application connecting to secure Kafka:

1. Choose the right listener and security.protocol: SSL or SASL_SSL.
2. Confirm the broker has the right SASL mechanism enabled.
3. Provision a dedicated principal per service and environment.
4. Configure a truststore containing the trusted CA.
5. Verify certificate SANs match all advertised broker hostnames.
6. If using mTLS, issue client certificates and configure keystore/truststore on both sides.
7. Place security properties in the regular Kafka binder or Kafka Streams binder according to the processing model.
8. Store passwords, tokens, and store passwords in secret management.
9. Verify ACLs for topics, groups, internal topics, cluster, and transactional ID if needed.
10. Provision topics/partitions/ACLs using an appropriate administrative workflow.
11. Test handshake, SASL, authorization, produce/consume, and Streams topology.
12. Verify logs do not print secrets or JAAS strings.
13. Have a plan to rotate certificates, passwords, and tokens.
14. Monitor authentication failures, authorization failures, TLS handshake errors, and connection retries.
15. Document broker, Kafka client, Spring Boot, and Spring Cloud Stream versions in the runbook.

## 20. Conclusion

TLS encrypts data in transit and enables clients to verify brokers via certificates. SASL authenticates principals using PLAIN, SCRAM, Kerberos, or OAuth. mTLS adds client authentication via certificates. Kafka ACLs determine which resources an authenticated principal can read, write, or administer.

For the regular Spring Cloud Stream Kafka binder, place Kafka client security properties under spring.cloud.stream.kafka.binder.configuration. For the Kafka Streams binder, use spring.cloud.stream.kafka.streams.binder.configuration. The security.protocol, SASL mechanism/JAAS, and ssl.* properties must match the broker's listener and certificate.

In production, prefer SASL_SSL or SSL depending on your identity model; use TLS 1.2 or higher, keep hostname verification enabled, and manage CAs/keystores/truststores and secrets cleanly. Do not treat authentication as authorization: grant least-privilege ACLs for topics, consumer groups, internal topics, and transactional IDs. Consider the connection complete only when integration tests prove the TLS handshake, SASL authentication, ACLs, and actual produce/consume flows.

## Official References

- [Spring Cloud Stream 5.0.4 — Kafka Binder Security Configuration](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/security-config.html)
- [Apache Kafka 4.4 — Authentication using SASL](https://kafka.apache.org/44/security/authentication-using-sasl/)
- [Apache Kafka 4.4 — Encryption and Authentication using SSL](https://kafka.apache.org/44/security/encryption-and-authentication-using-ssl/)
- [Apache Kafka 4.4 — Authorization and ACLs](https://kafka.apache.org/44/security/authorization-and-acls/)
- [Apache Kafka 4.4 — Security Model](https://kafka.apache.org/44/security/security-model/)

When implementing, choose the reference guide matching the exact release of Spring Cloud Stream, Kafka client, and broker in use. A property present in a newer Kafka client does not guarantee that an older binder or broker supports the same behavior.
