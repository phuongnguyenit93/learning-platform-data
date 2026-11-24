# SASL and TLS

A Spring Kafka application connecting to a broker must prove that **the connection is allowed**, **the client identity is valid**, and **data in transit is protected**. Two common mechanisms are **TLS (Transport Layer Security)** and **SASL (Simple Authentication and Security Layer)**. TLS encrypts the connection channel and verifies the server's certificate; SASL authenticates the client using mechanisms such as SCRAM, PLAIN, GSSAPI/Kerberos, or OAUTHBEARER. Kafka ACL/authorizer is a separate layer that decides whether the authenticated principal is allowed to read a topic, write to a topic, join a consumer group, or use a transactional ID.

In Spring Kafka, security configuration is typically passed to the producer, consumer, and AdminClient via Kafka client properties. A common configuration for production is **SASL_SSL**: TLS protects the connection, while SASL authenticates the client. If mutual TLS (mTLS) is used, the client also presents its certificate to the broker. TLS and SASL solve different problems; enabling one mechanism does not automatically replace the other.

This lesson belongs to the **Operational Security** chapter of Spring Kafka Reliability Operations. It covers the security model, Spring Boot configuration, truststore/keystore, SCRAM, ACLs, secret and certificate rotation, and runbooks for investigating production connection errors.

## 1. Distinguishing TLS, SASL, and Kafka ACL

Three layers commonly appear together:

| Layer | Question Answered | Mechanism |
|---|---|---|
| **TLS** | Is the connection encrypted and is the server's identity genuine? | X.509 certificates, CA trust, hostname verification, TLS handshake. |
| **SASL** | Who is the client? | SCRAM, PLAIN, GSSAPI/Kerberos, OAUTHBEARER, or another broker-supported mechanism. |
| **Authorization** | What is this principal allowed to do? | Kafka authorizer and ACL/resource policy. |

A SASL_SSL flow:

~~~text
Spring Kafka application
        |
        | 1. TLS handshake
        |    - verify broker certificate
        |    - establish encrypted channel
        v
     Kafka broker
        |
        | 2. SASL authentication
        |    - SCRAM / PLAIN / OAuth / Kerberos
        |    - identify principal
        v
     Authenticated principal
        |
        | 3. Authorization
        |    - topic READ / WRITE
        |    - group READ
        |    - transactional ID permissions
        v
     Kafka operation permitted
~~~

A client can succeed in the TLS handshake and succeed in SASL authentication, yet still receive `TopicAuthorizationException` when reading a topic. In that case, you need to fix the ACL—not replace the truststore or change the password.

**TLS does not automatically authorize a client's business permissions**, SASL does not encrypt data when using `SASL_PLAINTEXT`, and ACLs do not replace TLS/SASL for protecting data in transit.

## 2. `security.protocol` Values

Kafka clients use the `security.protocol` property to select the connection type:

| Value | TLS encryption | SASL authentication | Usage |
|---|---:|---:|---|
| `PLAINTEXT` | No | No | Suitable only for networks/labs protected by a separate model; avoid using for sensitive production traffic. |
| `SSL` | Yes | No | TLS server authentication; client certificate/mTLS can be enabled. |
| `SASL_PLAINTEXT` | No | Yes | Uses SASL, but data transmitted over the network is not protected by TLS. |
| `SASL_SSL` | Yes | Yes | Common for production when both encryption and SASL authentication are required. |

If `SASL_PLAINTEXT` is used, usernames/passwords or SASL credentials can be exposed on the wire if the network lacks an equivalent protection layer. Do not choose it merely to simplify configuration when clients and brokers communicate over untrusted networks.

With TLS-only, `security.protocol=SSL` can still authenticate the client via certificate if the broker requires client authentication. That is **mTLS**; SASL is not needed if the system intentionally uses certificate identity as the principal.

## 3. Choosing a SASL Mechanism

Kafka supports multiple SASL mechanisms; the broker and client must agree on the enabled and configured mechanism:

| Mechanism | Description | Operational Notes |
|---|---|---|
| `PLAIN` | Username/password over SASL PLAIN. | Use only over TLS in production networks; manage passwords as secrets. |
| `SCRAM-SHA-256` | Challenge-response based on salted password and SHA-256. | Credentials must be configured on the broker side; suitable for username/password authentication. |
| `SCRAM-SHA-512` | SCRAM with SHA-512. | Often chosen when supported by broker/client; still requires credential lifecycle management and TLS. |
| `GSSAPI` | Kerberos authentication. | Requires principal, keytab, ticket, and realm/KDC configuration. |
| `OAUTHBEARER` | Authentication based on OAuth bearer tokens. | Requires token acquisition/refresh, issuer, audience, TLS, and corresponding callbacks/config. |

Not every Kafka cluster or managed Kafka service enables all mechanisms. Verify the **broker listener**, Kafka version, managed service policy, and client library support for the chosen mechanism.

### How do PLAIN and SCRAM differ?

PLAIN sends credentials in the SASL exchange; TLS is the critical transport protection layer so credentials cannot be observed on the network. SCRAM uses challenge-response and does not send the plaintext password like PLAIN, but **SCRAM does not replace TLS**: TLS still protects traffic, metadata, and payloads, and reduces MITM risk.

SCRAM credentials must be created/provisioned on the broker or managed service control plane. Simply adding a username/password to the Spring Boot client does not automatically create the principal on the Kafka cluster.

## 4. TLS Server Authentication: Truststore

When a client makes a TLS connection to a broker, it must verify the broker's certificate chain. The **truststore** holds the CA certificates or certificate chains that the client trusts.

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
  - root CA / trusted chain
       |
       v
TLS server certificate validation
~~~

The client must verify:
- The certificate is within its validity period (NotBefore, NotAfter).
- The certificate chain leads to a trusted CA.
- The hostname the client connects to matches the certificate's Subject Alternative Name (SAN).
- The TLS protocol/cipher complies with policy.
- The certificate has not been revoked if the system performs appropriate revocation checks.

**Do not disable hostname verification to fix certificate errors.** The Kafka client property `ssl.endpoint.identification.algorithm` typically defaults to `https` to verify the hostname. Setting an empty value disables hostname verification and opens up man-in-the-middle risk. Reissue the certificate with a SAN containing the hostname the client actually uses.

## 5. mTLS: Client Keystore and Broker Trust

With mutual TLS, the broker also verifies the client certificate. This requires two-way trust:

~~~text
Client:
  truststore -> trusts CA that issued broker certificate
  keystore   -> holds client certificate + private key

Broker:
  truststore -> trusts CA that issued client certificate
  keystore   -> holds broker certificate + private key
~~~

Distinguish between them:
- **Truststore** contains certificates used to verify the peer.
- **Keystore** contains the endpoint's own certificate and private key.
- The keystore password and the password protecting the private key can be different.
- A truststore can hold multiple CAs to support rotation periods.
- Client certificate identity can be mapped by the broker to a principal according to Kafka configuration.

If the cluster only uses TLS server authentication, the client usually only needs a truststore; no client keystore is required. If the broker requires a client certificate, the client must be issued an appropriate certificate and configured with a keystore.

## 6. Configuring Spring Boot with SASL_SSL and SCRAM

Example configuration for producer, consumer, and admin sharing security properties:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1.example.net:9093,kafka-2.example.net:9093

    properties:
      "[security.protocol]": SASL_SSL
      "[sasl.mechanism]": SCRAM-SHA-512
      "[sasl.jaas.config]": 'org.apache.kafka.common.security.scram.ScramLoginModule required username="orders-app" password="INJECTED_SECRET";'
      "[ssl.truststore.location]": /etc/kafka/tls/truststore.p12
      "[ssl.truststore.password]": "INJECTED_TRUSTSTORE_PASSWORD"
      "[ssl.truststore.type]": PKCS12
      "[ssl.endpoint.identification.algorithm]": https

    consumer:
      group-id: orders-service-v1
      enable-auto-commit: false

    producer:
      acks: all
      properties:
        "[enable.idempotence]": true
~~~

`INJECTED_SECRET` and `INJECTED_TRUSTSTORE_PASSWORD` are placeholders; they must be replaced with values obtained from a secret manager or the deployment's secret injection mechanism. Do not commit real passwords into Git, Docker images, or logs.

Spring Boot maps `spring.kafka.properties` to shared Kafka client properties. If the producer, consumer, and AdminClient need different security settings, configure `spring.kafka.producer.properties`, `spring.kafka.consumer.properties`, and `spring.kafka.admin.properties` according to the Boot version in use. Avoid configuring different values for the same key at multiple levels without understanding the merge/override rules.

What matters is the final Kafka property that the client receives. When investigating, inspect the resolved configuration in a way that does not expose credentials.

## 7. JAAS Config for SCRAM

For SCRAM, Kafka clients typically use a JAAS login module:

~~~text
org.apache.kafka.common.security.scram.ScramLoginModule required
    username="orders-app"
    password="SECRET_FROM_SECRET_MANAGER";
~~~

The configuration can be passed via `sasl.jaas.config` in Kafka client properties. Because this is a JAAS string, be careful with quotes, semicolons, and escaping when placing it in YAML, environment variables, or Helm charts.

Example Java configuration from injected secrets:

~~~java
Map<String, Object> props = new HashMap<>();
props.put(CommonClientConfigs.SECURITY_PROTOCOL_CONFIG, "SASL_SSL");
props.put(SaslConfigs.SASL_MECHANISM, "SCRAM-SHA-512");

String username = credentials.username();
String password = credentials.password();

String jaas = "org.apache.kafka.common.security.scram.ScramLoginModule required "
        + "username=\"" + escapeJaas(username) + "\" "
        + "password=\"" + escapeJaas(password) + "\";";

props.put(SaslConfigs.SASL_JAAS_CONFIG, jaas);
~~~

This is illustrative code; `credentials` must come from a secure secret provider and `escapeJaas` must properly handle special characters according to JAAS grammar. If username/password contains quotes or backslashes, direct string concatenation without escaping can produce invalid configuration or open a configuration injection vector.

Do not log the `jaas` variable, as this string contains the password. Also do not include the raw value in exception messages, tracing attributes, or actuator endpoints.

## 8. Configuring Truststore and Keystore in Spring Boot

TLS server authentication:

~~~yaml
spring:
  kafka:
    properties:
      "[security.protocol]": SSL
      "[ssl.truststore.location]": /etc/kafka/tls/broker-truststore.p12
      "[ssl.truststore.password]": "INJECTED_TRUSTSTORE_PASSWORD"
      "[ssl.truststore.type]": PKCS12
      "[ssl.endpoint.identification.algorithm]": https
~~~

TLS mutual authentication:

~~~yaml
spring:
  kafka:
    properties:
      "[security.protocol]": SSL

      "[ssl.truststore.location]": /etc/kafka/tls/broker-truststore.p12
      "[ssl.truststore.password]": "INJECTED_TRUSTSTORE_PASSWORD"
      "[ssl.truststore.type]": PKCS12

      "[ssl.keystore.location]": /etc/kafka/tls/client-keystore.p12
      "[ssl.keystore.password]": "INJECTED_KEYSTORE_PASSWORD"
      "[ssl.keystore.type]": PKCS12
      "[ssl.key.password]": "INJECTED_PRIVATE_KEY_PASSWORD"

      "[ssl.endpoint.identification.algorithm]": https
~~~

File paths must exist and be readable inside the **actual container/runtime**. A path existing on a developer's machine does not mean it exists in the pod. Check volume mounts, file permissions, ownership, PKCS12/JKS format, and passwords.

Some keystores use the same password for the store and the private key; others use separate ones. Set `ssl.key.password` if the private key requires a separate password. Do not assume a truststore password is always mandatory to read every truststore type; configure according to your store format and system policy.

## 9. Combining SASL with mTLS

A client can use both SASL authentication and a TLS client certificate:

~~~yaml
spring:
  kafka:
    properties:
      "[security.protocol]": SASL_SSL
      "[sasl.mechanism]": SCRAM-SHA-512
      "[sasl.jaas.config]": 'org.apache.kafka.common.security.scram.ScramLoginModule required username="orders-app" password="INJECTED_SECRET";'

      "[ssl.truststore.location]": /etc/kafka/tls/broker-truststore.p12
      "[ssl.truststore.password]": "INJECTED_TRUSTSTORE_PASSWORD"
      "[ssl.truststore.type]": PKCS12

      "[ssl.keystore.location]": /etc/kafka/tls/client-keystore.p12
      "[ssl.keystore.password]": "INJECTED_KEYSTORE_PASSWORD"
      "[ssl.keystore.type]": PKCS12
      "[ssl.key.password]": "INJECTED_PRIVATE_KEY_PASSWORD"
~~~

In this model:
- TLS verifies the broker and encrypts the channel.
- A client certificate may be required and verified by the broker.
- SASL authenticates the principal using SCRAM.
- Authorizer/ACL decides permission to execute Kafka operations.

Verify that the broker listener is configured to support both TLS client authentication and the SASL mechanism. Not all managed Kafka services allow arbitrarily combining mTLS with SASL; follow the provider's contract.

## 10. Separate Security Configuration for Producer, Consumer, and Admin

Many applications share one cluster and the same credentials for producer/consumer/admin. However, some systems require different principals or broker endpoints by function.

Spring Boot supports configuring client-specific properties under the respective namespaces, depending on the version:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka.example.net:9093

    consumer:
      group-id: orders-reader-v1
      properties:
        "[security.protocol]": SASL_SSL
        "[sasl.mechanism]": SCRAM-SHA-512
        "[sasl.jaas.config]": 'org.apache.kafka.common.security.scram.ScramLoginModule required username="orders-reader" password="READER_SECRET";'

    producer:
      properties:
        "[security.protocol]": SASL_SSL
        "[sasl.mechanism]": SCRAM-SHA-512
        "[sasl.jaas.config]": 'org.apache.kafka.common.security.scram.ScramLoginModule required username="orders-writer" password="WRITER_SECRET";'

    admin:
      properties:
        "[security.protocol]": SASL_SSL
        "[sasl.mechanism]": SCRAM-SHA-512
        "[sasl.jaas.config]": 'org.apache.kafka.common.security.scram.ScramLoginModule required username="orders-admin" password="ADMIN_SECRET";'
~~~

This is an example of principal separation, not a recommendation to grant broad admin privileges to an application. Typically, a runtime service **does not need** cluster administration privileges; schema/topic provisioning can be handled by a deployment pipeline or platform team using a separate principal.

When configuring multiple client factories in Java, make sure producer, consumer, and AdminClient all receive appropriate security properties. A listener may work while producer sends fail if the two factories use different principals or different truststores.

## 11. SASL Authentication Is Not Kafka Authorization

After SASL authentication succeeds, the broker has a principal. The authorizer decides whether the principal has permissions on the resource.

Example permissions by workload:

| Principal | Resource | Permissions Typically Needed |
|---|---|---|
| `User:orders-writer` | Topic `orders.created` | WRITE; may need DESCRIBE depending on operation/client. |
| `User:orders-reader` | Topic `orders.created` | READ and DESCRIBE depending on configuration/operation. |
| `User:orders-reader` | Group `orders-reader-v1` | READ to join group and commit offsets. |
| `User:orders-writer` | Transactional ID prefix | Appropriate permissions to use transactions if the producer is transactional. |
| Deployment/admin principal | Topic/group/cluster | Grant only the administrative permissions genuinely needed. |

Exact ACLs depend on the Kafka version, operation, resource pattern, transactional/idempotent producer settings, and authorizer policy. Do not copy a broad ACL list for every service. Use **least privilege** and verify the operations the application actually performs.

Errors can be categorized:
- `SaslAuthenticationException`: credential, mechanism, JAAS, or auth backend issue.
- `TopicAuthorizationException`: principal is authenticated but lacks topic permission.
- `GroupAuthorizationException`: lacks consumer group permission.
- `TransactionalIdAuthorizationException`: lacks permission on transactional ID.
- `ClusterAuthorizationException`: lacks cluster-level permission for the corresponding operation.

If SASL auth succeeds but `poll()` or `send()` fails with an authorization error, changing the password usually will not help. Identify the **effective principal** and the denied resource/operation.

## 12. SCRAM Credential Lifecycle

With SCRAM, credentials are managed on the Kafka broker/control plane. A production process requires:
- A separate principal per service or workload.
- Not sharing an admin user across all producers/consumers.
- Strong passwords stored in a secret manager.
- Controlled provisioning, rotation, and revocation procedures.
- Monitoring authentication failures after rotation.
- Optionally using two principals during a transition period if supported by the platform.

A safe rotation approach typically involves creating a new credential/principal, granting corresponding least-privilege ACLs, deploying the new secret to a canary instance, verifying produce/consume, then rolling out the remaining instances, and finally revoking the old credential. Changing the password directly on the same principal without an overlap period may cause pods not yet updated to lose connection when the old credential becomes invalid.

Do not let old and new passwords coexist indefinitely. Document the revocation timestamp, owner, dependent applications, and rollback procedure.

## 13. Certificate Lifecycle and Rotation

Certificates have expiration dates; rotation must be planned before broker/client certificates expire.

### Rotating the Broker's CA

A CA transition procedure with overlap:

~~~text
Phase 1:
  Client truststore trusts old CA

Phase 2:
  Update client truststore to trust old CA + new CA
  Roll out client and confirm TLS still works

Phase 3:
  Broker switches to certificate issued by new CA

Phase 4:
  Confirm all clients connect using new certificate

Phase 5:
  Remove old CA from truststore after no broker uses old certificate
~~~

### Rotating Client Certificates in mTLS

1. Issue a new client certificate with appropriate SAN/subject and identity mapping.
2. Ensure the broker truststore trusts the CA issuing the new certificate.
3. Update the secret/keystore in a canary instance.
4. Recreate or refresh the Kafka client according to the mechanism supported by the application.
5. Verify TLS handshake, principal, and ACLs.
6. Roll out the rest.
7. Revoke the old certificate according to PKI policy.

Kafka clients do not necessarily reload truststores/keystores automatically when mounted files change. In practice, recreating the client/producer/consumer or performing a rolling restart is often required as supported by the framework and version. Do not assume that updating a Kubernetes Secret volume immediately switches all open connections to the new certificate.

## 14. Managing Secrets in Kubernetes and Deployments

Do not hard-code SASL passwords, truststore passwords, or private key passwords in:
- Git repositories.
- Committed `application.yml`.
- Dockerfiles or image layers.
- Public Helm values.
- Logs, exception messages, or unprotected actuator environment endpoints.

A deployment can mount secrets as files:

~~~yaml
volumes:
  - name: kafka-security
    secret:
      secretName: orders-kafka-security

containers:
  - name: orders-service
    volumeMounts:
      - name: kafka-security
        mountPath: /etc/kafka/tls
        readOnly: true
~~~

Secret names and file keys must match actual manifests/secret managers. Only the service account should be granted permission to read the corresponding secret. File permissions should be restricted to the user running the application; private keys must not be world-readable.

For password environment variables, understand how secrets are injected and how the application resolves config. Avoid printing the entire environment or `Environment` object to logs. If using an external secret provider, monitor secret refreshes and the lifecycle of clients holding old credentials.

## 15. Broker Listeners and `advertised.listeners`

Clients can connect properly only when broker listeners and advertised addresses match the client's environment.

For example, a client bootstraps to `kafka-bootstrap.example.net:9093`, but broker metadata may return per-broker hostnames. All advertised addresses must:
- Resolve from the application's network.
- Have appropriate routing/firewalls.
- Use the port/listener with the right security protocol.
- Have hostnames matching the broker certificate's SAN.
- Use the same authentication mechanism configured on the client.

A common mistake is that the bootstrap hostname has a valid certificate, but the hostname in a broker's `advertised.listeners` is not in the SAN. The initial TLS handshake succeeds, and then connecting to the specific broker fails.

Do not check only the bootstrap address. Check all broker endpoints the client receives from metadata, especially when using Kubernetes, private DNS, load balancers, or multi-region networks.

## 16. TLS Protocols, Ciphers, and Hostname Verification

Kafka clients have TLS properties such as:
- `ssl.protocol`
- `ssl.enabled.protocols`
- `ssl.cipher.suites`
- `ssl.endpoint.identification.algorithm`
- `ssl.truststore.location`, `ssl.truststore.type`, `ssl.truststore.password`
- `ssl.keystore.location`, `ssl.keystore.type`, `ssl.keystore.password`, `ssl.key.password`

Enable only protocols/ciphers supported by your organization and the broker. Do not downgrade to weak TLS versions just to "make the connection work" without a security review. Keep hostname verification enabled unless an equivalent approved protection design exists.

When encountering `SSLHandshakeException`, check:
1. Which hostname is the client connecting to?
2. Does the broker certificate have a SAN matching the hostname?
3. Does the chain include the full intermediate CA(s)?
4. Does the truststore have the right CA and right file path?
5. Is the certificate expired or not yet valid?
6. Are the TLS protocol/ciphers compatible?
7. Is a proxy/load balancer replacing the certificate?

Do not work around it by disabling `ssl.endpoint.identification.algorithm`; that hides identity errors and weakens protection against MITM.

## 17. Protecting Principals and Least Privilege

A service that only needs to publish `orders.created` should not have permissions to read all topics, create topics, delete topics, or modify cluster-wide ACLs.

Principal design:
- One principal per workload or trust boundary.
- Separate runtime producer and consumer principals if justified by security and operational manageability.
- Grant permissions on exact topic and group patterns.
- For transactional producers, grant permissions for the transactional ID prefix per policy.
- Separate CI/CD/admin principals from runtime applications.
- Periodically audit unused principals and overly broad ACLs.

When using mTLS, understand how the broker maps certificate DN/subject to a principal. Certificates sharing the same CA do not mean all certificates have the same permissions; principal mapping and ACLs determine actual permissions.

Do not name principals after end users or pass individual end-user credentials into the Kafka client unless required by the architecture. Normally, applications use workload identities, while business authorization is handled at the service layer.

## 18. Classifying Security Connection Errors

| Symptom/Log | Likely Failing Layer | First Check |
|---|---|---|
| `SSLHandshakeException` | TLS handshake/certificate/protocol | Trust chain, SAN/hostname, expiry, TLS/cipher, keystore. |
| `SaslAuthenticationException` | SASL authentication | Username/password, JAAS, mechanism, broker listener. |
| `UnsupportedSaslMechanismException` | SASL mechanism mismatch | Broker enabled mechanisms and client `sasl.mechanism`. |
| `TopicAuthorizationException` | Topic ACL | Effective principal, topic, and READ/WRITE/DESCRIBE operation. |
| `GroupAuthorizationException` | Group ACL | Group ID and corresponding READ permission. |
| `TransactionalIdAuthorizationException` | Transactional ID ACL | Transactional ID/prefix and principal permissions. |
| `ConfigException` related to SSL/SASL | Client configuration | Property name, type, JAAS syntax, store path/password. |
| `UnknownHostException` / connect timeout | DNS/network/listener | Bootstrap and advertised broker endpoints, firewall, route. |
| Authentication succeeds but send fails | Authorization or producer config | Topic ACL, transactional ACL, idempotence/acks. |
| Only one broker has TLS errors | Inconsistent certificate/listener | Broker hostname, certificate SAN/chain, and `advertised.listeners`. |

Do not lump everything together as "Kafka auth error." Identify whether the error occurs before TLS, during the SASL exchange, or after the principal has been authenticated.

## 19. Inspecting Certificates and Truststores

You can use OpenSSL from an authorized environment to inspect the endpoint certificate:

~~~bash
openssl s_client \
  -connect kafka-1.example.net:9093 \
  -servername kafka-1.example.net \
  -showcerts
~~~

This command lets you inspect the certificate chain and TLS handshake result from the machine running the command. It does not prove that SASL authentication or Kafka ACLs work.

You can inspect certificate details:

~~~bash
openssl x509 -in broker.crt -noout -subject -issuer -dates -ext subjectAltName
~~~

For PKCS12/JKS, use `keytool` appropriately:
- List aliases and certificate chains.
- Confirm the CA certificate is correct.
- Confirm the client keystore contains a private key entry if using mTLS.
- Confirm expiry and subject/SAN.
- Do not export private keys to unprotected locations.

Do not send private key files, truststores with secrets, or passwords in insecure tickets/chats/logs when asking for help.

## 20. End-to-End Security Testing

A smoke test should verify all three layers:

**TLS**
- Client connects to the right broker listener.
- Certificate chain is valid.
- Hostname verification succeeds.
- If mTLS, broker accepts client certificate.

**SASL**
- Client authenticates with the expected principal.
- Client and broker mechanisms match.
- Credentials come from the correct secret version.

**Authorization**
- Producer can send to authorized topics.
- Consumer can read authorized topics and groups.
- If using transactions, producer can commit using the transactional ID.
- Forbidden operations are still denied (negative test) to verify least privilege.

Example business-aligned smoke test:
1. Using the service's principal, send a test record to an authorized topic.
2. Using an authorized test consumer group, read that topic.
3. Confirm the record is received and offsets advance.
4. Attempt to access an unauthorized topic; expect an authorization failure.
5. If using a transactional producer, test transaction begin/send/commit.
6. Record the principal, broker endpoint, topic/group, and outcome without logging credentials.

Testing only with `openssl s_client` is insufficient; it only verifies part of TLS and does not test SASL, ACLs, producer send, or consumer poll.

## 21. Runbook: SASL Authentication Fails

Suppose a service repeatedly reports `SaslAuthenticationException` after deployment.

**Step 1 — Verify endpoint.** Check that the bootstrap server, port, and listener being used require the expected security protocol.

**Step 2 — Check mechanism.** Is the client's `sasl.mechanism` in the list enabled on the broker listener? SCRAM-SHA-256 and SCRAM-SHA-512 are not interchangeable.

**Step 3 — Check JAAS.** Does the login module match the mechanism? Are username/password resolved from the latest secret? Are quotes, semicolons, and escaping valid?

**Step 4 — Check credential lifecycle.** Was the secret rotated/revoked mid-rollout? Are old pods still using the old password? Is the principal disabled?

**Step 5 — Check TLS before SASL.** If the TLS handshake fails, the SASL exchange cannot complete; read the root cause instead of looking only at wrapper exceptions.

**Step 6 — Check broker logs/control plane.** Identify the rejected principal or mechanism from safe information provided by the broker.

**Step 7 — Canary credential.** Test with one instance or test client using the same endpoint and secret version before propagating changes to all pods.

**Step 8 — Confirm.** Producer/consumer establish new connections, authenticate successfully, and execute the authorized operations.

Do not print JAAS strings, passwords, or tokens into logs to troubleshoot. Log the secret version/rotation ID, not the secret value.

## 22. Runbook: TLS Handshake Fails

Symptoms: `SSLHandshakeException`, `PKIX path building failed`, `No subject alternative DNS name matching`, or protocol/cipher errors.

1. Confirm the broker hostname the client actually connects to, including addresses from advertised metadata.
2. Inspect certificate SAN, issuer, validity period, and chain.
3. Confirm the truststore inside the container has the right file, format, and secret version.
4. For mTLS, check that the keystore has the private key and matching client certificate chain.
5. Check file mount permissions and store/key passwords.
6. Confirm the TLS protocol/ciphers are supported by broker/client.
7. If a CA was just rotated, verify the truststore holds both old/new CAs during the overlap period.
8. Fix the certificate or trust chain; keep hostname verification enabled.
9. Recreate Kafka clients / rolling restart as needed to load new material.
10. Confirm all broker endpoints in metadata complete the TLS handshake successfully.

Do not disable hostname verification to work around SAN errors. Fix the certificate or advertised hostname.

## 23. Runbook: SASL Succeeds but Authorization Denied

Suppose logs show `TopicAuthorizationException` when the producer sends.

1. Identify the principal the broker successfully authenticated.
2. Confirm the topic name and cluster being accessed.
3. Identify the denied operation: WRITE, READ, DESCRIBE, group access, or transaction.
4. Check the ACL/resource pattern for the exact principal.
5. For consumers, check permissions for both the topic and the actual group ID, not just the intended group ID in YAML.
6. For transactional producers, check transactional ID/prefix permissions.
7. Grant the exact least-privilege permissions through the governance process.
8. Retry the operation and confirm it is permitted; negative tests on unauthorized resources must still be denied.

Do not grant superuser or cluster-wide wildcard permissions to resolve a missing ACL on a single topic.

## 24. Zero-Outage Rotation

A rotation process should have an owner, schedule, canary, and completion criteria:

~~~text
Prepare new credential/certificate
             |
             v
Update trust/ACL to accept new identity
             |
             v
Mount new secret/material on canary
             |
             v
Create new Kafka client connection
             |
             v
Verify TLS + SASL + ACL + produce/consume
             |
         Succeeded?
          /      \
         No      Yes
         |        |
         v        v
Rollback      Roll out remaining pods
or fix            |
                  v
         Confirm no old clients remain
                  |
                  v
         Revoke old credential/certificate
~~~

For CA rotation, the truststore typically must trust both old and new CAs before brokers switch certificates. For SCRAM rotation, a new principal may be needed to create overlap; changing the password directly on the same username can cause old pods to fail. For mTLS, the broker must trust the new certificate's CA before client rollout.

Do not revoke old credentials/certificates immediately when the canary succeeds; wait until the rollout completes, confirm all instances use the new identity, and keep rollback possible within the defined window.

## 25. Observability for Security Operations

Monitor these signals:
- TLS handshake failure count per broker endpoint.
- SASL authentication failures by sanitized service/principal.
- Authorization denied count by resource/operation.
- Upcoming certificate expiry and remaining time.
- Secret/certificate version active in each pod.
- Kafka connection/reconnect rate.
- Producer send failures and consumer poll/lag after rotation.
- Transaction commit/abort if a transactional producer uses a new principal.
- Time from rollout until all pods confirm the new security material.

Do not put passwords, tokens, private keys, or full JAAS strings into logs/traces/metrics. You may log the principal name or credential version if policy allows; do not log authentication data.

Metric names are instrumented by the platform or application and do not have identical default names across all Kafka exporters/managed services. Alerts should distinguish **authentication failure** from **authorization failure** and **TLS handshake failure** to route to the responsible team.

## 26. Common Configuration Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Using `SASL_PLAINTEXT` on untrusted network | SASL credentials are not protected by TLS. | Switch to `SASL_SSL` if cluster supports it. |
| Client uses different mechanism than broker | SASL auth fails or unsupported mechanism. | Align mechanism and broker listener config. |
| Truststore missing intermediate CA | PKIX path validation fails. | Install complete trusted CA chain. |
| Broker certificate SAN mismatches advertised hostname | TLS hostname verification fails. | Fix SAN or advertised listener hostname. |
| Disabling hostname verification to make it work | Loss of identity protection against MITM. | Keep verification enabled and fix certificate. |
| Pods hold different secret versions | Some replicas connect, some fail. | Use canary/rollout and observe secret versions. |
| Password committed in Git/logs | Credential exposure requiring emergency rotation. | Revoke, rotate, use secret manager, check log retention. |
| Principal authenticates but lacks ACL | Topic/group/transaction operation denied. | Grant least-privilege permission on exact resource. |
| Testing TLS only with OpenSSL | Does not test SASL or Kafka ACLs. | Run Kafka produce/consume smoke test. |
| Secret file updated but client still fails | Kafka client still holds old SSL context/credentials. | Recreate client or rolling restart per lifecycle. |

## 27. Pre-Production Checklist

- [ ] Correct `security.protocol` chosen (`SASL_SSL` or `SSL` per approved model).
- [ ] Broker listener enables the corresponding SASL mechanism.
- [ ] TLS certificate chain is valid and hostname verification remains enabled.
- [ ] Truststore/keystore have the right file path, format, password, and permissions in runtime.
- [ ] mTLS is fully configured if broker requires client certificates.
- [ ] SASL JAAS config retrieves credentials from secret manager, not committed/logged.
- [ ] Dedicated principal per workload; no admin credentials in runtime if unnecessary.
- [ ] ACLs grant permissions on exact topic, group, and transactional ID resources.
- [ ] Producer, consumer, and AdminClient all receive appropriate security properties.
- [ ] Bootstrap and all advertised broker endpoints are DNS/network/TLS reachable.
- [ ] Credential/certificate rotation process exists with overlap, canary, and rollback.
- [ ] Known whether Kafka clients require recreate/restart to load new secrets/certificates.
- [ ] Smoke tests exist covering TLS + SASL + authorization + produce/consume.
- [ ] Separate alerts exist for TLS, authentication, and authorization failures.
- [ ] Passwords, tokens, private keys, or JAAS strings are never logged.
- [ ] Runbook exists classifying errors and owners for broker, PKI, identity, and application.

## 28. Conclusion

**TLS and SASL protect two different layers of a Kafka connection.** TLS encrypts data in transit and verifies certificate identity; SASL authenticates the client using a broker-supported mechanism; Kafka ACLs determine whether the principal is allowed to perform a specific operation. In many production environments, `SASL_SSL` is the common choice, combining a truststore to verify the broker and optionally adding a keystore if mTLS is needed.

Secure operations require managing credentials/certificates as lifecycle assets: storing them in a secret manager, granting least-privilege permissions, rotating in phased overlaps, verifying all broker endpoints, and testing TLS, SASL, and ACLs thoroughly. When classifying incidents by the exact layer, operations teams can fix trust chains, credentials, mechanisms, or ACLs accurately without accidentally disabling hostname verification or granting overly broad permissions just to make connections work again.
