# Rotating Certificates and Credentials

A Spring Kafka application must authenticate with the Kafka broker before a producer sends records or a consumer reads data. Depending on the cluster's security mechanism, clients may use one-way TLS, mutual TLS (mTLS), SASL/SCRAM, SASL/PLAIN, or SASL/OAUTHBEARER. Certificates and credentials have expiration dates, can be compromised, or must be changed per security policy; therefore, the system must have a rotation process without disrupting messaging flows beyond acceptable limits.

Rotation means replacing certificates, private keys, passwords, tokens, or principals currently used by clients with new authentication material. A safe workflow typically includes an overlap period: issue and trust the new material, deploy clients using the new material, verify connectivity works, and only then revoke the old material. If old credentials are revoked before all clients switch over, un-updated producers and consumers can lose connectivity.

This lesson belongs to the **Security** chapter of the **SPRING_KAFKA_MESSAGING** module. The module focuses on building event-driven applications with Spring Kafka, `KafkaTemplate`, and `@KafkaListener`, understanding topics, partitions, offsets, and consumer groups, while learning serialization, retries, dead-letter handling, transactions, exactly-once semantics, concurrency, and testing to run reliable messaging flows.

## 1. What Needs Rotation in a Kafka Connection

A Kafka connection may rely on one or more security layers:

| Component | Material to Manage | Purpose |
| --- | --- | --- |
| Broker TLS certificate | Broker-side certificate and private key | Client verifies the broker is the legitimate server. |
| Client TLS certificate | Client-side certificate and private key | Broker verifies client identity in mTLS. |
| Truststore | Trusted CA certificates or certificate chains | Verify the peer's certificate. |
| Keystore | Private key and certificate chain of the client/broker itself | Provide TLS identity. |
| SASL credentials | Username/password or matching secret | Authenticate the client via SASL. |
| OAuth credentials/tokens | Client secret, signing key, or access token | Issue tokens for SASL/OAUTHBEARER. |
| Kafka principal and ACLs | Identity and access permissions | Decide what the client may do after authentication. |

Not every cluster uses every component. For example, a cluster using SASL/SCRAM over TLS needs a truststore to verify the broker and username/password to authenticate the client; a cluster using mTLS needs a truststore along with a client keystore.

Distinguish three concepts:

- **Authentication:** who is the client?
- **Authorization:** which topics may the client read/write, or which consumer groups may it use?
- **Encryption:** how is data protected in transit?

Rotating credentials successfully does not guarantee connections work if the new principal has not been granted matching ACLs.

## 2. One-Way TLS and Mutual TLS

In one-way TLS, the client verifies the broker's certificate. The client needs a truststore containing the CA or certificate chain used by the broker.

In mutual TLS, the broker also requires the client to present a certificate. Both sides verify each other's identity:

~~~mermaid
flowchart TD
    A[Spring Kafka client] --> B[TLS handshake]
    B --> C[Client verifies broker certificate]
    C --> D{Valid broker certificate?}
    D -->|No| E[Handshake fails]
    D -->|Yes| F[Client sends certificate if broker requires mTLS]
    F --> G[Broker verifies client certificate]
    G --> H{Valid client certificate?}
    H -->|No| I[Authentication fails]
    H -->|Yes| J[TLS channel established]
    J --> K[Kafka authorization checks ACL]
~~~

The truststore typically holds CA certificates used to verify peers. The keystore holds the private key and certificate chain of the connecting identity itself. Do not confuse truststore with keystore: a truststore does not need to hold the client's private key.

If the cluster uses one-way TLS, do not configure a client keystore just to verify the broker. If the broker enables mTLS, the client needs an appropriate keystore and the broker must trust the CA that issued client certificates.

## 3. Certificate Structure and Trust Chains

An X.509 certificate is typically signed by a CA. The client verifies the chain from the broker's leaf certificate up to a CA the client trusts.

~~~text
Kafka broker certificate
        |
        v
Intermediate CA
        |
        v
Root CA
        |
        v
Client truststore
~~~

When inspecting a certificate, pay attention to:

- Subject and Subject Alternative Name (SAN).
- Issuer and CA chain.
- `Not Before` and `Not After`.
- Key usage and extended key usage.
- Signature algorithm and key size.
- Whether the broker hostname matches the SAN.

Kafka clients connect to hostnames in `bootstrap.servers` and broker addresses advertised via metadata. The broker certificate must match the hostname the client actually connects to, not just the initial bootstrap hostname.

If a broker certificate is reissued with a wrong SAN or missing intermediate certificate, the TLS handshake can fail even when the certificate is unexpired and the CA is trusted.

You can inspect a PEM certificate:

~~~bash
openssl x509 -in broker.crt -noout -subject -issuer -dates -ext subjectAltName
~~~

For a PKCS12 keystore:

~~~bash
keytool -list -v -keystore client-keystore.p12 -storetype PKCS12
~~~

These commands only read certificate/keystore metadata. Never put private keys or passwords on the command line or in terminal logs.

## 4. Keystores, Truststores, and Storage Formats

The Kafka client supports SSL configuration with storage formats compatible with the Kafka client/JVM, commonly JKS and PKCS12. PEM can also be used depending on configuration and Kafka client version.

| Component | Contents | Example |
| --- | --- | --- |
| Client keystore | Client private key and certificate chain | `client-keystore.p12` |
| Client truststore | CA used to verify the broker | `kafka-truststore.p12` |
| Broker keystore | Broker private key and certificate chain | `broker-keystore.p12` |
| Broker truststore | CA used to verify client certificates in mTLS | `client-ca-truststore.p12` |

Passwords protecting keystores/truststores are also credentials that require rotation. Changing a store file password without updating the application's secret will prevent the client from opening the store.

Private keys must be protected more strictly than public certificates. Never commit private keys, keystore passwords, or SASL passwords to Git, Docker images, logs, or documentation. Secret read permissions should be scoped by service identity and environment.

## 5. Configuring TLS in Spring Boot

Spring Boot provides the `spring.kafka.ssl.*` property group to configure SSL for Kafka clients. Exact property names may vary by Spring Boot version; check the configuration metadata for the version you use.

Example client verifying the broker using a truststore:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka.internal:9093
    properties:
      security.protocol: SSL
    ssl:
      trust-store-location: file:/etc/kafka/tls/client-truststore.p12
      trust-store-password: <injected-truststore-password>
      trust-store-type: PKCS12
~~~

Example mTLS adding a client keystore:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka.internal:9093
    properties:
      security.protocol: SSL
    ssl:
      trust-store-location: file:/etc/kafka/tls/client-truststore.p12
      trust-store-password: <injected-truststore-password>
      trust-store-type: PKCS12
      key-store-location: file:/etc/kafka/tls/client-keystore.p12
      key-store-password: <injected-keystore-password>
      key-password: <injected-private-key-password>
      key-store-type: PKCS12
~~~

File paths here are runtime mount points. Passwords are placeholders illustrating secrets injected from a secret manager or secret volume; never put real values in committed config files.

If a project configures Kafka client properties directly, the corresponding properties are typically `ssl.truststore.location`, `ssl.truststore.password`, `ssl.keystore.location`, `ssl.keystore.password`, `ssl.key.password`, and `ssl.keystore.type`.

## 6. Configuring SASL/SCRAM

SASL/SCRAM authenticates clients with username/password via challenge-response. TLS should still be enabled to encrypt the entire connection and protect data, metadata, and authentication details in transit.

Example `SCRAM-SHA-512` over TLS:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka.internal:9093
    properties:
      security.protocol: SASL_SSL
      sasl.mechanism: SCRAM-SHA-512
      sasl.jaas.config: >-
        org.apache.kafka.common.security.scram.ScramLoginModule required
        username="order-service-v2"
        password="<injected-scram-password>";
    ssl:
      trust-store-location: file:/etc/kafka/tls/client-truststore.p12
      trust-store-password: <injected-truststore-password>
      trust-store-type: PKCS12
~~~

The client simultaneously needs:

- `security.protocol: SASL_SSL` to run SASL inside TLS.
- `sasl.mechanism: SCRAM-SHA-512` to select the authentication mechanism.
- `sasl.jaas.config` to provide the login module and credentials.
- A truststore to verify the broker certificate.

Username is the principal used for authorization; password is the authentication secret. When switching the username to a new principal, grant ACLs to the new principal before deploying clients.

Do not use SASL/PLAIN or SCRAM over `PLAINTEXT` connections in untrusted environments. SCRAM does not replace TLS because TLS also protects all traffic and prevents broker impersonation.

## 7. SASL/PLAIN and OAuth Credentials

SASL/PLAIN uses username/password and is typically configured via `PlainLoginModule`:

~~~yaml
spring:
  kafka:
    properties:
      security.protocol: SASL_SSL
      sasl.mechanism: PLAIN
      sasl.jaas.config: >-
        org.apache.kafka.common.security.plain.PlainLoginModule required
        username="order-service"
        password="<injected-password>";
~~~

SASL/PLAIN should only be used over TLS because this mechanism provides no built-in encryption for passwords in transit.

With SASL/OAUTHBEARER, clients use tokens instead of static passwords. You must manage:

- Client ID and client secret if required by the identity provider.
- Access token expiration.
- Mechanism to obtain a fresh token before expiration.
- Signing keys/JWKS and trust with the identity provider.
- Clock synchronization and time skew.
- Handling token revocation or identity provider unavailability.

Short-lived tokens limit how long a leaked credential can be abused, but the application must have a callback/login handler or OAuth mechanism compatible with its Kafka client version. Never hardcode long-lived tokens inside `sasl.jaas.config`.

## 8. Authentication Success Is Not Enough: Principals and ACLs

After authentication, the broker resolves the principal and applies authorization policy. In Kafka ACLs, the principal can come from a SASL username or a TLS certificate identity, depending on the mechanism and the broker's principal mapping configuration.

A consumer service typically needs permissions:

| Activity | Commonly Needed Permission |
| --- | --- |
| Producer writes events to topic | `WRITE` on topic |
| Consumer reads events | `READ` on topic |
| Consumer joins group | `READ` on consumer group |
| Transactional producer | Appropriate permissions on transactional ID and topic |
| Idempotent producer | `IdempotentWrite` permission on cluster when required by ACL authorizer |

When rotating from an old principal to a new principal, copy the exact permissions needed by the workload. Do not grant wildcards or admin privileges just to make the new connection work.

With mTLS, the certificate subject can be mapped to a Kafka principal via broker configuration. If a new certificate has a different subject, the principal may change and old ACLs will no longer match. Verify principal mapping before deploying new certificates.

## 9. Rotating Client Certificates in mTLS

Suppose the client currently uses a certificate issued by an old CA and needs to move to a new CA. The broker verifies the client certificate, so the broker truststore must trust the new CA before clients switch certificates.

Safe sequence:

1. Issue the new client certificate and new private key.
2. Add the new CA to the broker's truststore while keeping the old CA.
3. Confirm brokers have loaded the new truststore per the environment's reload/rolling restart mechanism.
4. Provision the new certificate to a canary client.
5. Restart or recreate the Kafka client using the new certificate.
6. Verify TLS handshake, principal, ACLs, and produce/consume.
7. Roll out the new certificate to all remaining instances.
8. Monitor connections and confirm no clients still use the old certificate.
9. Revoke the old certificate and remove the old CA from the broker truststore after the overlap period.

Do not remove the old CA before all clients have switched. If the broker does not support live truststore reload in your deployment setup, perform a controlled rolling restart.

## 10. Rotating Broker Certificates

When a broker certificate nears expiration or needs a CA change, the client is the party verifying the broker certificate. Therefore, the client truststore must trust the new CA before brokers switch certificates.

Sequence:

1. Issue the new broker certificate with SANs matching advertised listener hostnames.
2. Update the client truststore to trust both the old CA and the new CA.
3. Distribute the new truststore to all applications and confirm clients are using it.
4. Replace broker certificates following the Kafka cluster's rolling procedure.
5. Test connections to every broker, including brokers advertised in metadata.
6. Confirm producers/consumers operate across all brokers.
7. After the overlap period, remove the old CA from the client truststore once no certificates depend on it.
8. Revoke old certificates per CA policy.

If the new certificate is still signed by the same old CA, changing the trust anchor may not be necessary; however, still verify SAN, chain, validity, and broker certificate reload. Never assume replacing a keystore file on disk automatically causes a running broker or client to load the new certificate.

## 11. Rotating SASL/SCRAM Credentials

With SASL/SCRAM, the username identifies the principal and the password proves the client holds that principal's credential. One transition approach with overlap is creating a new principal, granting the right ACLs, and then migrating applications to the new username/password.

Recommended procedure:

1. Create a new principal, such as `order-service-v2`.
2. Create the new SCRAM credential in the Kafka cluster or corresponding identity system.
3. Copy the exact required ACLs from the old principal to the new principal.
4. Store the new password in the secret manager.
5. Update a canary instance to use the new principal.
6. Verify authentication, authorization, produce, consume, and consumer group behavior.
7. Roll out the remaining instances.
8. Confirm no clients still use the old principal.
9. Revoke the old credential and ACLs per schedule.

Creating a new principal keeps both credentials valid simultaneously during the transition. If changing the password directly on the same principal, un-updated clients can fail on reconnect or reauthentication; overlap support depends on the broker and configured SASL mechanism.

Do not delete the old principal right after the canary connects successfully. Confirm all replicas, batch jobs, connectors, scheduled tasks, and dependent applications have migrated.

## 12. Granting ACLs for a New Principal

Authentication only confirms identity; authorization still has to be configured separately. When creating a new principal, determine which permissions the workload needs.

For example, a consumer reading topic `order-events` in group `order-service` typically needs `READ` on the topic and `READ` on the group. A producer sending to a topic typically needs `WRITE` on the topic. Transactional or idempotent workloads may need additional permissions on the transactional ID or cluster depending on the active authorizer.

ACL migration procedure:

- Export or record ACLs of the old principal.
- Identify the minimum permissions actually used by the workload.
- Grant equivalent permissions to the new principal.
- Test using the exact client config and production-like topics/groups.
- Monitor authorization errors during the canary phase.
- Once all clients have switched, revoke the old principal's ACLs.

Do not copy wildcards or admin rights mechanically. Credential rotation is an opportunity to review least privilege, though you should avoid simultaneously altering permissions beyond required scope without testing.

If using mTLS, ACLs bind to the Kafka principal derived from the certificate identity. A new certificate can change the principal if the subject or principal mapping changes. Verify the identity actually seen by the broker before rolling out.

## 13. Rotating SASL/PLAIN Passwords

SASL/PLAIN uses static passwords, so it needs a secret-change process with overlap. If the broker supports multiple identities, the safer pattern is creating a new username instead of changing the password of a username actively used by all clients.

If you must change the password on the same principal:

1. Determine the broker's credential-update behavior and when the new credential takes effect.
2. Prepare to roll out the new client config before revoking the old password if the platform supports overlap.
3. Identify existing connections that may be impacted on reconnect/reauthentication.
4. Run a canary and monitor authentication failures.
5. Roll out all clients and confirm no connections remain on the old password.
6. Revoke the old password per the identity provider/broker mechanism.

Do not assume an already-open connection retains access forever after a password changes. Brokers may require reauthentication, or connections may close for various reasons. Design so clients can open new connections with the active credential.

SASL/PLAIN must run over TLS. If a password leaks, prioritize emergency revocation per incident procedure rather than extending an unsafe overlap.

## 14. Rotating OAuth Client Secrets and Tokens

With OAuth, distinguish client secrets from access tokens:

- Client secret is used by the client to authenticate with the identity provider.
- Access token is the short-lived credential sent during SASL/OAUTHBEARER.
- Signing key/JWKS verifies the token signature.
- Token expiry determines when the client must fetch a new token.

The procedure for changing a client secret depends on the identity provider. If the provider supports two active secrets concurrently, create the new secret, update a canary client, verify new tokens, and roll out all clients before revoking the old secret. If the provider does not support overlap, schedule a synchronized cutover or create a new client registration.

The application must fetch a new token before the current token expires and handle token issuance failures, clock skew, identity provider timeouts, and revoked tokens. Never store long-lived access tokens in YAML or logs.

If the identity provider's signing key changes, token verifiers must receive the new JWKS/key before new tokens are widely issued. Keep old and new keys overlapping for a window matching circulating token lifetimes.

## 15. Distributing Secrets in Spring Boot and Deployment Environments

Applications should not contain real credentials in committed `application.yml` files. Instead, inject secrets at runtime from a managed source:

- Kubernetes Secrets mounted as files or supplied via environment.
- HashiCorp Vault or a cloud provider secret manager.
- Secret stores built into the deployment platform.
- Internal PKI that automatically issues and renews certificates.

YAML examples should only hold paths and variable names:

~~~yaml
spring:
  kafka:
    properties:
      security.protocol: SASL_SSL
      sasl.mechanism: SCRAM-SHA-512
      sasl.jaas.config: >-
        org.apache.kafka.common.security.scram.ScramLoginModule required
        username="order-service"
        password="<runtime-injected-secret>";
~~~

Placeholders must be replaced by secrets supplied by the environment. Never write real passwords in source code, Docker build arguments, image layers, shell history, or configuration logs.

Environment variables are convenient at process startup but can be hard to rotate inside a running process. Secret volumes can have files updated by the platform, yet Kafka clients do not automatically reload keystores or JAAS configs when files change on disk.

## 16. When Must Kafka Clients Be Recreated?

Kafka clients read configuration when the client/producer/consumer is created. Replacing a secret file on disk does not guarantee existing connections use the new certificate or credentials.

With Spring Kafka:

- `ProducerFactory` can manage and cache producer instances.
- Listener containers manage consumer instances across their lifecycle.
- `KafkaTemplate` uses producers supplied by `ProducerFactory`.
- Refreshing a property source does not automatically ensure existing producers/consumers reload credentials.

The simplest and most verifiable operational approach is rolling out/restarting the application in batches once new secrets are mounted. For zero-restart reload requirements, explicitly design closing/recreating producers, consumers, and listener containers using your Spring Kafka version's APIs; test transactions, in-flight sends, consumer assignments, and offsets before using it in production.

Do not merely replace a keystore file and assume TLS sessions are already using the new certificate. Monitor the active certificate fingerprint or serial number from client/broker telemetry if supported by your environment.

## 17. Non-Disruptive Rolling Rotation

To avoid outages, there must be a window where both old and new credentials are accepted. A rollout can be broken into these steps:

~~~mermaid
flowchart TD
    A[Inventory clients and old credentials] --> B[Issue new certificate/credential]
    B --> C[Add new trust or ACLs]
    C --> D[Deploy canary with new credential]
    D --> E{Connections and permissions work?}
    E -->|No| F[Roll back canary, keep old credential]
    E -->|Yes| G[Rolling deploy remaining clients]
    G --> H[Confirm no old clients remain]
    H --> I[Revoke old credential]
    I --> J[Remove old trust anchor after overlap]
~~~

Key notes:

- Grant new permissions and trust before switching clients.
- Revoke old credentials only after inventorying all clients.
- Roll out in small batches and wait for health checks.
- Monitor both producers and consumers, not just one client type.
- Preserve rollback capability during the overlap window.
- Broker-side changes need their own rolling procedure so quorum or availability is not lost.

Zero downtime cannot be guaranteed solely by using a rolling deployment. Outcomes also depend on replica counts, partition assignment, broker availability, consumer lag, reconnect time, and how the system handles in-flight requests.

## 18. Same-CA Certificate Renewal vs. Switching CAs

These two scenarios follow different procedures:

| Scenario | What Changes | What to Do |
| --- | --- | --- |
| Renew certificate issued by the same CA | Leaf certificate/private key or validity changes | Verify subject/SAN, chain, and key usage, then update keystore; truststore usually still trusts the current CA. |
| Switch to a new CA | Trust anchor changes | Add the new CA to the truststore first, rotate certificates, and only then remove the old CA. |
| Change subject/principal | Kafka identity may change | Update principal mapping/ACLs before clients use the new certificate. |
| Change broker hostname | Endpoint changes | SAN must match the new hostname and clients must reach the advertised endpoint. |

Even with the same CA, new private keys must still be protected and provisioned properly. Do not reuse an old private key just to skip config updates if PKI policy requires fresh keys.

When changing CAs, the truststore can temporarily hold both old and new CAs. Remove the old CA only after confirming no valid broker/client certificates still depend on it.

## 19. Verifying Certificates and Credentials Before Rollout

Before deploying, inspect metadata and validity:

~~~bash
openssl x509 -in client.crt -noout -subject -issuer -dates -ext subjectAltName
openssl verify -CAfile ca-chain.pem client.crt
keytool -list -v -keystore client-keystore.p12 -storetype PKCS12
~~~

For mTLS, also verify the certificate includes client authentication in extended key usage and that the private key matches the certificate. For broker certificates, confirm the SAN contains the broker hostnames Kafka clients will connect to.

Test connectivity using a client configured like Spring Kafka:

- Right `security.protocol`.
- Right SASL mechanism or TLS keystore/truststore.
- Right principal and ACLs.
- Right broker endpoints and DNS.
- Right topics, groups, and transactional IDs if using transactions.

A successful TLS check alone does not prove Kafka ACLs are right. Test produce/consume with the new principal to confirm both authentication and authorization.

## 20. Monitoring Expiration and Authentication Errors

Start rotation well before expiration—do not wait until clients are rejected. Monitor:

- Certificate `Not After` and days remaining.
- Active certificate serial number/fingerprint in use.
- Deployed truststore/keystore version.
- SASL authentication failures by principal.
- TLS handshake failures, hostname verification failures, and expired certificates.
- Authorization failures by topic/group/transactional ID.
- OAuth token refresh failures and token expirations.
- Producer reconnects, consumer disconnects, and rebalances.
- Consumer lag and send failure rates during rollout.

Set alert thresholds per organizational policy, such as 30 days, 14 days, and 7 days before expiration. Factor certificate issuance, approval, rollout, and rollback time into alert thresholds.

Never log passwords, tokens, private keys, or full JAAS configs. Logging principal, error class, endpoint, publicly shareable certificate fingerprint, and correlation ID is sufficient for most investigations.

## 21. Rollback and Handling Compromised Credentials

During scheduled rotation, keep the old credential valid for a defined rollback window. If a canary using the new credential fails, revert to the old configuration while investigating trust, ACLs, certificate chains, or secret injection.

When a credential is compromised, prioritize containment:

1. Identify the affected principal, certificate, or secret.
2. Inspect access logs and the identity's permission scope.
3. Create a replacement identity/credential and grant least-privilege permissions.
4. Migrate legitimate workloads to the new credential.
5. Revoke the compromised credential based on urgency.
6. Verify unauthorized connections no longer work.
7. Check other secrets that may have been exposed from the same source.
8. Document the root cause and update rotation procedures.

During a leak incident, do not extend overlap merely for rollback convenience if doing so leaves the compromised credential active. Coordinate between security incident response and Kafka operations.

Certificate revocation via CRL/OCSP depends on the CA, broker, JVM, and environment TLS configuration. Do not assume every Kafka deployment automatically checks revocation; verify the actual mechanism and have an appropriate revocation procedure.

## 22. Certificate and Credential Rotation Checklist

Before marking a rotation complete, confirm:

1. Inventoried all producers, consumers, Kafka Streams apps, connectors, and jobs using the old identity.
2. Identified the security type: TLS, mTLS, SASL/SCRAM, PLAIN, or OAUTHBEARER.
3. New certificates have valid chains, SANs, validity windows, and key usages.
4. Truststores trust the new CA before peers switch certificates.
5. Keystores contain the exact private key and certificate chain.
6. Keystore/truststore passwords are injected from a secret manager.
7. New principals have been granted least-privilege required ACLs.
8. Certificate subject/principal mapping does not accidentally drop permissions.
9. Canary produce/consume succeeded using the new credential.
10. All instances have been rolled out and use the new secret version.
11. Kafka clients were recreated/restarted as needed to load new configuration.
12. No connections or workloads still depend on the old credential.
13. Authentication, authorization, TLS, and consumer lag metrics are stable.
14. Old credentials were revoked and old CAs removed at the right time.
15. Audit evidence, owner, rotation timestamp, and next rotation plan are recorded.

Rotating certificates and credentials requires an overlap period, principal/ACL verification, and controlled client rollout. With mTLS, distinguish the truststore that verifies peers from the keystore holding the client's own private key; with SASL, replace credentials while preserving principal access permissions. Spring Kafka does not automatically reload every secret or certificate when files change, so proactively recreate clients or perform rolling restarts, monitor handshakes/authentication, and revoke old material only after all workloads have transitioned.

