# Authentication Failure

In **Spring Kafka Reliability Operations**, an **authentication failure** occurs when a Kafka client fails to prove its identity to the broker or an intermediary authentication component. The failure can prevent producers from sending records, consumers from fetching data, `AdminClient` from querying the cluster, or listener containers from continuing normal operation.

Distinguish **authentication** from **authorization**:

- **Authentication (AuthN)** answers: who is the client, and are its credentials valid?
- **Authorization (AuthZ)** answers: is the authenticated principal permitted to perform this operation on this topic, group, cluster, or transactional ID?

A wrong username/password, expired token, untrusted certificate, or invalid Kerberos ticket is an authentication issue. A principal that authenticates successfully yet lacks `READ` or `WRITE` permission on a topic is an authorization issue. Both errors can cause consumers/producers to fail, but their remediations differ.

In **Health and readiness**, the goal is not merely catching exceptions. The application must accurately represent Kafka dependency status, avoid reporting healthy when mandatory work cannot be performed, and avoid restart loops when brokers or credential providers experience issues.

The operational workflow should be: **classify error → identify principal and security mechanism → inspect client/broker configuration → fix credentials or permissions → safely recover clients → verify the exact Kafka operation → update readiness**.

## 1. Where do authentication failures appear?

Spring Kafka uses Kafka clients underneath. An application can initialize multiple client types for different purposes:

- **KafkaConsumer**: subscribes, joins groups, polls, and fetches records.
- **KafkaProducer**: sends records, optionally participating in transactions.
- **KafkaTemplate**: Spring Kafka's abstraction over the producer.
- **KafkaAdmin/AdminClient**: describes the cluster, checks topics, and performs administrative operations.
- **Transactional producer**: also requires permissions for a transactional ID.
- **Consumer group coordinator**: verifies permissions to join and use a group.

Each client can use the same or different security configurations. If producer and consumer use different principals, one client working does not prove the other client authenticates properly.

Example:

~~~text
order-service
  |
  +-- KafkaConsumer
  |     principal = User:orders-reader
  |     group = orders-service
  |     topic = orders.events
  |
  +-- KafkaProducer
  |     principal = User:orders-writer
  |     topic = orders.projected
  |
  +-- KafkaAdmin
        principal = User:orders-admin-check
~~~

In practice, you do not necessarily have to create three principals. The diagram emphasizes that you must identify **which client raised the error** and which credentials/ACLs apply to that client.

## 2. How do authentication and authorization differ?

| Attribute | Authentication | Authorization |
|---|---|---|
| Question | Who is the client? | What is the client allowed to do? |
| Verification | Password, token, certificate, Kerberos ticket | ACL, role, policy, resource permission |
| Timing | Typically when establishing or authenticating connection/session | When the client invokes an operation on a resource |
| Example error | SASL authentication failed | Topic authorization failed |
| Remediation | Fix identity, secret, mechanism, trust | Grant proper permissions to the principal |
| Impact | Client cannot authenticate with the broker | Can connect, but the operation is rejected |

A consumer can complete the SASL handshake yet still fail to read a topic due to missing `READ` permission. Similarly, a producer can authenticate successfully yet fail to `WRITE` to a topic.

Never change a password when the real cause is an ACL. Nor should you grant broad permissions like superuser just to hide an authentication error.

## 3. Common failure categories

| Error Group | Symptoms | What to Check |
|---|---|---|
| SASL username/password | Authentication failed | Username, password, mechanism, JAAS |
| SASL mechanism mismatch | Broker/client disagree on mechanism | `SCRAM-SHA-256`/`512`, `PLAIN`, `GSSAPI`, `OAUTHBEARER` |
| OAuth token | Token expired/invalid/audience mismatch | Issuer, audience, scope, callback handler, clock |
| TLS trust | PKIX path building or certificate unknown | Truststore, CA chain, hostname |
| TLS client certificate | Bad certificate/handshake failure | Keystore, cert validity, client-auth policy |
| Kerberos | Login/GSS initiate failure | Principal, keytab, SPN, clock skew, DNS |
| Topic authorization | `TopicAuthorizationException` | `READ`/`WRITE`/`DESCRIBE` ACLs |
| Group authorization | `GroupAuthorizationException` | `GROUP` resource ACL |
| Transaction authorization | Transactional ID authorization failure | `WRITE`/`DESCRIBE` on transactional ID |
| Cluster authorization | Cluster operation denied | Cluster ACL/admin role |
| Network/connectivity | Timeout, disconnect, DNS failure | Broker endpoint, firewall, routing |

**A timeout is not automatically an authentication failure.** An unreachable broker, DNS failure, or unready broker can prevent the client from completing a handshake without credentials being wrong.

## 4. Exceptions to recognize

Kafka clients have exceptions related to authentication and authorization. Common ones include:

- **AuthenticationException**: general authentication error class in Kafka clients.
- **SaslAuthenticationException**: SASL authentication failed.
- **TopicAuthorizationException**: missing permission on a topic.
- **GroupAuthorizationException**: missing permission on a consumer group.
- **ClusterAuthorizationException**: missing permission for a cluster-level operation.
- **TransactionalIdAuthorizationException**: missing permission for a transactional ID.
- **SSLHandshakeException** or corresponding SSL errors: TLS handshake failed; inspect certificates/trust.
- **TimeoutException**: operation timed out; investigate network/broker rather than assuming credential failure.

Class names and exception wrapping can depend on Kafka client version and call path. Read the root cause and broker/client logs instead of classifying solely by the outermost exception.

An error in `KafkaAdmin` can appear during startup or health checks, whereas a consumer error can surface during `poll`/`fetch`. Producers can report errors through the send future. Not every authentication exception passes through a listener method.

## 5. SASL and TLS serve two different roles

Kafka can use TLS to protect the transport channel and authenticate certificates, and SASL to authenticate the principal under a configured mechanism.

Common security protocols:

| Protocol | Meaning |
|---|---|
| `PLAINTEXT` | No TLS/SASL |
| `SSL` | TLS; can perform client certificate authentication if broker is configured |
| `SASL_PLAINTEXT` | SASL authentication over a non-TLS connection |
| `SASL_SSL` | SASL authentication inside a TLS connection |

In production, **SASL_SSL** is commonly chosen when using a SASL mechanism and encrypting transport. If mutual TLS is used, the client certificate also participates in authentication at the TLS layer.

Do not confuse:
- Truststore usually holds the CA/certificate chain that the client trusts to verify the broker.
- Keystore holds the client certificate and private key when the client must present a certificate.
- SASL credentials are the username/password, token, or login details per mechanism.
- ACLs are the permissions of a principal after the broker identifies it.

A client can succeed at TLS while failing SASL; or have valid SASL credentials while its TLS trust chain is invalid.

## 6. Configuring SASL_SSL with SCRAM

Example Spring Boot configuration using `SCRAM-SHA-512`:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka.example.internal:9093
    properties:
      security.protocol: SASL_SSL
      sasl.mechanism: SCRAM-SHA-512
      sasl.jaas.config: org.apache.kafka.common.security.scram.ScramLoginModule required username="INJECTED_USERNAME" password="INJECTED_SECRET";
~~~

`INJECTED_USERNAME` and `INJECTED_SECRET` are illustrative placeholders; supply real credentials through proper secret management. Never commit passwords to source control or print them in logs.

If producer, consumer, and admin use different principals, shared settings under `spring.kafka.properties` may not fit. Spring Boot supports client-specific properties for producer, consumer, and admin; place credentials in the right scope to avoid accidentally using the wrong principal.

Directional example:

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        security.protocol: SASL_SSL
        sasl.mechanism: SCRAM-SHA-512
        sasl.jaas.config: INJECTED_CONSUMER_JAAS_CONFIG
    producer:
      properties:
        security.protocol: SASL_SSL
        sasl.mechanism: SCRAM-SHA-512
        sasl.jaas.config: INJECTED_PRODUCER_JAAS_CONFIG
~~~

Verify property binding against your Spring Boot version and how the application constructs custom `KafkaAdmin`/`KafkaTemplate`/`ConsumerFactory` beans.

## 7. SASL mechanism mismatch

Client and broker must agree on the configured mechanism. Common mechanisms:

- **PLAIN**: username/password; use only over TLS in production unless an approved security exception exists.
- **SCRAM-SHA-256 / SCRAM-SHA-512**: challenge-response based on secrets registered on the broker.
- **OAUTHBEARER**: token-based authentication.
- **GSSAPI**: Kerberos.
- Other mechanisms depending on Kafka distribution and broker configuration.

Examples of mismatches:

- Client declares `SCRAM-SHA-512`, but the broker listener only enables `SCRAM-SHA-256`.
- Client uses `GSSAPI` while the listener does not support Kerberos.
- Client configures a SASL mechanism while `security.protocol` is `SSL`.
- Client connects to the wrong listener/port using a different security protocol.
- Broker principal was provisioned for a different mechanism than the client.

Verify the exact **bootstrap endpoint and listener**. A Kafka cluster can expose multiple listeners, each with its own protocol, authentication, and principal mapping.

## 8. SCRAM username/password and JAAS

When using SCRAM, the Kafka client needs an appropriate login module with username/password. Common mistakes:

- Secret mounted under the wrong key or wrong file path.
- Trailing whitespace/newline in username.
- Password improperly escaped in YAML/JAAS.
- Secret rotation updated only the Kubernetes Secret while existing clients still hold old credentials.
- Client connecting to the wrong broker listener.
- Principal not yet provisioned with SCRAM credentials on the cluster.
- Client and broker disagreeing on the SCRAM mechanism.

Never log JAAS config contents because they can include passwords. When debugging, log only **mechanism, secret version/reference, source type, and approved principal**, never secret values.

When using multiple clients, verify each factory receives the right JAAS config. A working `ConsumerFactory` does not guarantee `KafkaAdmin` or the producer is configured properly.

## 9. OAUTHBEARER and token expiry

With `OAUTHBEARER`, the client typically needs a callback/login handler to fetch tokens. Failures can stem from:

- Expired token.
- Wrong issuer.
- Audience not matching the broker.
- Insufficient scope/claims.
- Clock skew between client, identity provider, and broker.
- TLS not trusting the identity provider.
- Callback handler failing to load client secret/credentials.
- Failed token refresh or token cache holding stale values.

Never put access tokens, refresh tokens, or client secrets into spans, logs, or exception messages. Record only an allowlisted error category such as `oauth_token_expired` or `oauth_issuer_mismatch`.

For token rotation, verify that the callback handler actually fetches fresh tokens and that the Kafka client supports re-authentication for your version. Do not assume changing an environment variable automatically updates the token on an open Kafka connection.

## 10. Kerberos/GSSAPI

If using Kerberos, these elements must align:

- Client principal.
- Keytab and file permissions.
- Kafka broker service principal name.
- DNS and hostname resolution.
- Realm and `krb5` configuration.
- Clock synchronization.
- Ticket lifetime and renewal policy.
- SASL mechanism `GSSAPI`.

Client-side property example:

~~~properties
security.protocol=SASL_SSL
sasl.mechanism=GSSAPI
sasl.kerberos.service.name=kafka
sasl.jaas.config=com.sun.security.auth.module.Krb5LoginModule required useKeyTab=true storeKey=true keyTab="/secure/path/client.keytab" principal="orders-client@EXAMPLE.COM";
~~~

Paths and principals are placeholder data. Never print keytabs, JAAS secrets, or ticket caches into logs. If initial login succeeds yet tickets fail to renew, outages can appear only after the service has run for a period of time.

## 11. TLS truststore and certificate failures

TLS failures can be mistaken for authentication failures because both break Kafka connections.

Symptoms:
- PKIX path building failed.
- Certificate expired or not yet valid.
- Hostname verification failure.
- Unknown CA.
- Bad certificate when the broker requires client certificates.
- TLS protocol/cipher mismatch.

The truststore verifies the broker's certificate chain. The keystore is used when the client must present its own certificate, such as in mutual TLS.

Example configuration:

~~~yaml
spring:
  kafka:
    properties:
      security.protocol: SASL_SSL
      ssl.truststore.location: /secure/path/kafka.truststore
      ssl.truststore.password: INJECTED_TRUSTSTORE_SECRET
      ssl.keystore.location: /secure/path/client.keystore
      ssl.keystore.password: INJECTED_KEYSTORE_SECRET
      ssl.key.password: INJECTED_PRIVATE_KEY_SECRET
~~~

If only broker verification via truststore is needed, the client may not need a keystore. Do not configure client certificates when the broker does not require them unless policy mandates it.

Never disable hostname verification or switch to trust-all as a "quick fix." Doing so weakens transport security and hides certificate provisioning errors.

## 12. Authentication differs from authorization in ACLs

Once the broker authenticates the principal, it applies ACLs/authorizers for each operation.

Example permissions to consider:

| Client Role | Resource | Typically Required Operations |
|---|---|---|
| Consumer | Topic | `READ`, `DESCRIBE` |
| Consumer | Group | `READ` |
| Producer | Topic | `WRITE`, possibly `DESCRIBE` depending on operation |
| Transactional producer | Transactional ID | `WRITE`, `DESCRIBE` as required |
| Admin/health checker | Cluster/topic | Specific describe/admin permissions |

Actual permissions depend on the operation, broker authorizer, Kafka version, and security policy. Do not grant broader permissions just to make a health check pass.

A consumer can authenticate successfully yet hit `TopicAuthorizationException` when fetching a topic. A health check calling describe-cluster can fail due to missing cluster `DESCRIBE` even while the consumer reads topics normally. Therefore, health checks must test **the exact required capability**.

## 13. Producers and consumers can have different principals

Within one service, separating principals can reduce blast radius:

~~~text
orders-reader:
  READ orders.events
  READ group orders-service

orders-writer:
  WRITE orders.projected

orders-admin-observer:
  DESCRIBE certain required resources
~~~

If producer and consumer share a principal, grant least-privilege permissions for all operations. If principals are split, configure credentials per client factory and test secret rotation for each identity.

Never infer "Kafka is connected" from a single client. A successful producer send does not prove the consumer is allowed to join a group; a successful consumer poll does not prove the producer has `WRITE` ACLs.

## 14. Authentication failures at startup and runtime

Failures can occur at multiple points:

| Phase | Example | Action |
|---|---|---|
| Application startup | `KafkaAdmin` cannot authenticate | Check admin client config and startup policy |
| Consumer start | SASL/TLS handshake fails | Check consumer principal and listener |
| Consumer poll/fetch | Token expired or ACL revoked | Check runtime auth/reauth and permissions |
| Producer send | Wrong producer credentials or missing `WRITE` ACL | Check producer identity and topic ACL |
| Transaction begin/commit | Transactional ID ACL or producer fencing | Check transaction identity and ownership |
| Health check | Probe client lacks required permissions | Check health check principal/operation |
| Credential rotation | Old client still using old secret | Recreate/refresh clients per supported mechanism |

An error appearing at startup differs from one appearing after several hours of uptime. Runtime failures can surface only when a token/certificate expires or a connection must re-authenticate.

## 15. Spring Kafka listener containers and authentication errors

Listener containers run `KafkaConsumer` in the background. Authentication errors can be thrown from client operations like poll or fetch; the consumer thread can log errors, stop, or fail to recover as expected depending on Kafka client/Spring Kafka version and exception type.

Do not assume **CommonErrorHandler** can retry every authentication failure. Error handlers primarily handle exceptions from listener record processing; authentication failures in the Kafka client protocol/connection happen outside business listeners and are not normal record failures.

When errors occur:

1. Read the root cause and broker logs.
2. Check whether the container is still running or has stopped.
3. Check whether polling/assignments continue.
4. Check whether the exception repeats on every reconnect.
5. Verify credentials/mechanism and broker listener.
6. Fix secret/ACL/trust chain.
7. Recreate or restart the exact client/container if needed.
8. Confirm the consumer receives records and offsets advance.

Never swallow authentication exceptions inside a listener and return success. Never commit offsets to skip over credential issues.

## 16. KafkaTemplate and producer send failures

`KafkaTemplate` sends messages asynchronously. Authentication/authorization errors can surface via the send future or producer client logs.

Example error handling without logging payloads:

~~~java
kafkaTemplate.send("orders.created", event)
    .whenComplete((result, error) -> {
        if (error != null) {
            log.error(
                "Kafka publish failed: topic={}, errorType={}",
                "orders.created",
                error.getClass().getSimpleName()
            );
            publishHealthState.recordFailure(
                classifyKafkaFailure(error)
            );
        } else {
            publishHealthState.recordSuccess();
        }
    });
~~~

`publishHealthState` and `classifyKafkaFailure` are illustrative domain helpers. Do not log `event.toString()`, raw keys, or uncontrolled exception messages.

If using a transactional `KafkaTemplate`, a successful send future does not mean the transaction committed. Transactional producer health state must be updated from the corresponding transaction lifecycle outcome, not just send acknowledgement.

## 17. KafkaAdmin/AdminClient can have different permissions

Spring Kafka can use `KafkaAdmin` to create/inspect topics or perform administrative operations. `AdminClient` can be configured with separate credentials or shared properties.

An `AdminClient`-based health check can fail because:
- Admin principal has wrong credentials.
- Principal lacks cluster `DESCRIBE` permission.
- Broker does not support the configured listener/protocol.
- Timeout/network issue.
- Cluster is unavailable.

This **does not always prove the consumer principal cannot fetch**. If the health indicator calls `describeCluster`, it tests that principal's ability to describe the cluster, without proving `WRITE`/`READ` on every topic.

Define the health contract around the application's role and actual principal. Never grant cluster-admin to a consumer just to turn a dashboard `UP`.

## 18. Inspecting credentials without leaking secrets

A sound debugging workflow checks:

- Secret reference/version.
- File mount path and file permissions.
- Whether the environment variable **exists**, without printing its value.
- Approved username/principal.
- SASL mechanism and `security.protocol`.
- Broker listener endpoint/port.
- Certificate subject/issuer/expiry, without printing private keys.
- Permitted token expiry/audience/issuer metadata.
- JAAS module class and config structure.
- Principal ACLs via an authorized admin process.

Never write log statements such as:

~~~java
log.info("Kafka JAAS config: {}", jaasConfig);
log.info("Kafka password: {}", password);
log.info("OAuth token: {}", token);
~~~

When needing to verify whether two secrets match, use secret manager/version metadata or approved verification tooling—never print passwords to terminals or logs.

## 19. Secret injection in Spring Boot

An application can receive credentials via environment variables, mounted secret files, config trees, or a secret manager. Ensure:

- Placeholders resolve properly at startup.
- Secrets are never committed in `application.yml`.
- Effective configuration containing passwords is never printed.
- Secrets are not exposed on Actuator `env`/`configprops` endpoints.
- Secret files have minimal read permissions.
- Rotation has an owner and rollout procedure.
- Each Kafka client receives the right credential scope.

If using Spring Boot config import/config tree, verify actual paths and property names. Do not assume a newly mounted file automatically updates an already-initialized bean or Kafka client.

## 20. Credential rotation: why a plan is required

Credential rotation can create a window where some instances use old secrets and others use new secrets. If the broker accepts only one credential at a time, an uncoordinated rollout can cause an outage.

A rotation plan typically includes:

1. Provision new credentials or certificates.
2. Ensure brokers or the identity provider accept the new credentials.
3. Update the secret store and version reference.
4. Roll out or refresh Kafka clients via a supported mechanism.
5. Verify producer, consumer, and admin operations.
6. Monitor authentication failures and reconnect rates.
7. Once all clients use the new credentials, revoke the old credentials.
8. Verify no remaining instances or batch jobs still use the old credentials.

If the broker/identity provider supports credential overlap, leverage the overlap window for zero-downtime rollouts. Otherwise, use a maintenance window or controlled cutover.

## 21. Secret updates do not automatically refresh all Kafka clients

Changing a Pod's environment variables usually requires creating a new Pod. A mounted secret file can be updated by Kubernetes, yet an already-created Kafka client does not necessarily re-read the file or swap credentials on existing connections.

Depending on mechanism:
- OAuth callback handlers can fetch new tokens via refresh mechanisms.
- Kerberos login modules can renew tickets per configuration.
- SCRAM credentials are typically used when the client authenticates a connection; reconnect/recreate may be needed to adopt new secrets.
- TLS certificates may be read when building the SSL context; rotation must define how contexts/connections are rebuilt.

Do not assume **Spring Cloud refresh** automatically swaps every property inside `ConsumerFactory`/`ProducerFactory` and running Kafka clients. Inspect client lifecycles, callback handlers, and framework version.

A safe rollout typically creates new clients with the new secret, verifies operation, and then retires old clients.

## 22. Recovering clients after fixing credentials

Once invalid credentials are fixed, do not merely clear the alert. Verify:

1. The new secret version reached the right instances.
2. New Kafka clients are using that config.
3. TLS/SASL handshakes succeed.
4. Producers can perform required send operations.
5. Consumers can join groups and fetch permitted topics.
6. Transactional producers can initialize/commit if the service uses transactions.
7. ACLs still align with the new principal.
8. Consumer lag starts falling and listener success rate rises.
9. Auth exceptions no longer repeat on reconnect.
10. Readiness returns to `UP` only once mandatory capabilities are operational.

If existing clients cannot refresh credentials, recreate the exact factory/container safely via lifecycle. Avoid restarting all services when only one principal is affected.

## 23. Readiness and liveness must stay separate

In Kubernetes/Spring Boot Actuator, **readiness** and **liveness** have distinct meanings:

- **Readiness**: should the instance accept more traffic/work under the application contract?
- **Liveness**: is the process alive and able to continue operating?

If Kafka is a mandatory dependency for an order-processing service, prolonged authentication failures can make the service **not ready**. However, that does not automatically prove the JVM needs a restart.

Do not turn broker authentication failures into immediate liveness failures. If credentials are wrong due to secret deployment, repeatedly restarting with the exact same config cannot fix the problem and creates a crash loop.

For consumer workers receiving no HTTP traffic, readiness can still drive deployment orchestration/availability; clearly define whether it means "connected and able to process workload" or only "process started."

## 24. Spring Boot Actuator readiness probes

Spring Boot Actuator can enable Kubernetes probe endpoints in supported versions:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
~~~

Readiness/liveness endpoints are typically exposed under Actuator health probe paths. Exact configuration depends on Spring Boot version and management server setup.

A readiness group can include required health contributors, such as readiness state and a Kafka capability indicator if configured by the application:

~~~yaml
management:
  endpoint:
    health:
      group:
        readiness:
          include: readinessState,kafkaAccess
~~~

Use the contributor name `kafkaAccess` only if the application actually registers that indicator. Never add a contributor merely to make it appear on a dashboard; check which operation the indicator performs and which principal it uses.

**Liveness should focus on process/application state**, not depend directly on Kafka if a broker outage does not mean the JVM is dead.

## 25. A Kafka health indicator does not prove all permissions

A Kafka health indicator may run an administrative operation or describe the cluster. If that operation succeeds, it proves the client used for the health check can perform that operation.

It does not automatically prove:
- The consumer has `READ` ACLs on all topics.
- The consumer has `READ` permission on the specific group.
- The producer has `WRITE` ACLs on output topics.
- The transactional producer has permissions on the transactional ID.
- The consumer listener is processing records successfully.
- Offset commits are advancing.
- Downstream databases/APIs are healthy.

Conversely, a health check failing due to missing cluster `DESCRIBE` does not necessarily mean the listener principal cannot consume.

Name health details accurately for the verified capability, e.g., `kafka-admin-describe` rather than `kafka-processing-ready`.

## 26. Readiness by application capability

A sound policy should reflect the actual role:

| Service Role | Critical Capability |
|---|---|
| Kafka producer API | Can publish to mandatory topics |
| Kafka consumer worker | Can authenticate, join group, and fetch from target topics |
| Kafka Streams app | Can read inputs, write outputs, and use internal topics/state stores per ACLs |
| Transactional processor | Can read inputs and commit transactions/outputs/offsets |
| Admin utility | Has required administrative operation permissions |
| Optional integration | Can degrade without marking the entire service unready if domain allows |

A check calling only `describeCluster` cannot prove a producer API has `WRITE` ACLs. An empty poll is also not conclusive proof of fetching successfully from target topics. Readiness should rely on **role-appropriate operations**, or runtime state updated from real operations.

Do not generate synthetic messages in production topics solely to probe unless safe synthetic traffic and cleanup are designed.

## 27. Example dedicated health state for Kafka capability

An application can record the latest outcome of real Kafka operations and expose it via `HealthIndicator`. Simple example:

~~~java
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.stereotype.Component;

@Component
public class KafkaAccessState {

    public record Snapshot(
            boolean available,
            String operation,
            String failureKind) {
    }

    private final AtomicReference<Snapshot> current =
            new AtomicReference<>(
                new Snapshot(false, "not_verified", "unknown")
            );

    public void success(String operation) {
        current.set(new Snapshot(true, operation, "none"));
    }

    public void failure(String operation, String kind) {
        current.set(new Snapshot(false, operation, kind));
    }

    public Snapshot snapshot() {
        return current.get();
    }
}
~~~

Health indicator:

~~~java
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component("kafkaAccess")
public class KafkaAccessHealthIndicator implements HealthIndicator {

    private final KafkaAccessState state;

    public KafkaAccessHealthIndicator(KafkaAccessState state) {
        this.state = state;
    }

    @Override
    public Health health() {
        var snapshot = state.snapshot();

        if (snapshot.available()) {
            return Health.up()
                    .withDetail("operation", snapshot.operation())
                    .build();
        }

        return Health.down()
                .withDetail("operation", snapshot.operation())
                .withDetail("failureKind", snapshot.failureKind())
                .build();
    }
}
~~~

This is an example state-based health indicator; it does not perform Kafka authentication itself. Producer/consumer integrations must update state after **appropriate operation successes/failures**, and freshness/last-success timestamps must be managed.

Never store raw exception messages or credentials in health details. When using multiple clients, keep separate state for producer, consumer, and admin rather than a single shared boolean.

## 28. Do not let health checks create an authentication storm

A probe can run every few seconds. If every call creates a new `AdminClient`, queries cluster metadata, and closes the client, an authentication failure can generate heavy connections, retries, and logs.

Mitigations:

- Reuse clients/health contributors per framework design.
- Never create a new `KafkaAdmin`/`AdminClient` on every health request.
- Never send synthetic messages continuously into business topics.
- Enforce short, explicit timeouts on probes.
- Cache results for a reasonable window where appropriate.
- Separate readiness operations from deep diagnostics.
- Never log passwords/tokens when probes fail.
- Rate-limit or deduplicate repeated health errors.

Health checks must observe the system, not overload an already troubled broker.

## 29. Kubernetes readiness behavior when Kafka auth fails

When a readiness probe fails, Kubernetes normally marks the Pod **NotReady** and removes it from matching Service endpoints. It does not automatically restart the container solely because readiness failed.

When a liveness probe fails, kubelet can restart the container after the configured failure count.

A common strategy:

~~~text
Kafka auth failure
  |
  +--> Readiness: DOWN if Kafka is a mandatory dependency
  |
  +--> Liveness: UP if JVM/process is still operating
  |
  +--> Alert: credential/authentication incident
  |
  +--> Recovery: fix secret/ACL and refresh clients
  |
  +--> Readiness: UP after capability verification
~~~

If a worker does not serve HTTP requests, readiness semantics still need alignment with the deployment system. A NotReady Pod can affect rollouts and autoscaling; do not use readiness to hide persistent failures without alerts.

## 30. Startup readiness and consumer assignment

A consumer application may start the JVM and create listener containers without holding assignments or being able to fetch topics yet.

Stages:

~~~text
PROCESS_STARTED
  -> CONFIG_LOADED
  -> KAFKA_CLIENT_CREATED
  -> AUTHENTICATION_SUCCEEDED
  -> GROUP_JOINED
  -> PARTITIONS_ASSIGNED
  -> REQUIRED_FETCH_OPERATION_SUCCEEDED
  -> READY
~~~

This is a suggested state model, not standard Spring Kafka enum states.

Readiness for critical consumers may need to wait for assignment and proof that the client can run required operations. However, do not wait for a real business record before marking ready if topics can sit idle for long periods. Assignment/authenticated operation state combined with SLAs can be used, provided you know which operation actually verifies read permission.

Spring Kafka application events such as consumer started/stopped and partitions assigned/revoked can assist lifecycle observation. A started event alone does not prove fetch permission or processing success.

## 31. Authorization failures should not be "fixed" by restarting

If authentication succeeds yet the consumer lacks `READ` ACLs, restarting recreates the exact same principal with the exact same missing permissions. The error will repeat.

Operations requiring specific permissions:

- `READ` on topics.
- `READ` on consumer groups.
- `WRITE` on output topics.
- `DESCRIBE` on topics/clusters when clients perform metadata operations.
- Transactional ID permissions for transactional producers.
- Topic create/alter permissions for `AdminClient` if the application performs them.

Grant least-privilege permissions to the principal. If the broker authorizer supports policy inheritance or prefix ACLs, check the actual policy before granting broad access.

Never grant superuser just to make a health indicator turn `UP`.

## 32. Layered investigation workflow

When receiving an authentication failure:

**Layer 1 — Client identity**

1. Identify client type: consumer, producer, admin, or transactional producer.
2. Identify the approved principal/username/certificate subject.
3. Identify secret reference/version.
4. Check the exact Kafka bootstrap endpoint/listener.

**Layer 2 — Protocol**

5. Check `security.protocol`.
6. Check `sasl.mechanism`.
7. Check JAAS module/callback handler.
8. Check TLS trust chain/hostname/client certificate.
9. Check token/ticket validity and clock skew.

**Layer 3 — Broker/identity provider**

10. Check broker authentication logs.
11. Check which mechanisms the listener supports.
12. Check whether the principal is provisioned properly.
13. Check identity provider/token issuer if OAuth.
14. Check Kerberos service principal/keytab if GSSAPI.

**Layer 4 — Authorization**

15. Check topic/group/cluster/transactional ID ACLs.
16. Check the exact denied operation.
17. Distinguish the health-check principal from the workload principal.

**Layer 5 — Application health**

18. Check container running/assignment state.
19. Check producer future/consumer poll errors.
20. Update readiness per capability.
21. Verify after fixing and document root cause.

## 33. Zero-downtime credential rotation

A rotation rollout should avoid a state where brokers revoke old credentials before clients adopt new credentials.

Recommended workflow:

1. Create new credentials/certificates/tokens.
2. Provision brokers or the identity provider to accept the new credentials.
3. Store in the secret manager with an explicit version.
4. Update workload config.
5. Determine whether Kafka clients need restart/recreation or callback refresh.
6. Roll out instance by instance or client group by client group.
7. Verify producer/consumer/admin operations with the new principal.
8. Monitor `AuthenticationException` and reconnects.
9. Wait until the entire fleet stops using old credentials.
10. Revoke old credentials.
11. Check that scheduled jobs, batch workers, and tools have also been rotated.

If overlapping credentials are unavailable, use a maintenance window or coordinated cutover. Never revoke old credentials before confirming new clients work.

## 34. Secret updates do not automatically refresh all Kafka clients

Changing a Pod's environment variables usually requires creating a new Pod. A mounted secret file can be updated by Kubernetes, yet an already-created Kafka client does not necessarily re-read the file or swap credentials on existing connections.

Depending on mechanism:
- OAuth callback handlers can fetch new tokens via refresh mechanisms.
- Kerberos login modules can renew tickets per configuration.
- SCRAM credentials are typically used when the client authenticates a connection; reconnect/recreate may be needed to adopt new secrets.
- TLS certificates may be read when building the SSL context; rotation must define how contexts/connections are rebuilt.

Do not assume **Spring Cloud refresh** automatically swaps every property inside `ConsumerFactory`/`ProducerFactory` and running Kafka clients. Inspect client lifecycles, callback handlers, and framework version.

A safe rollout typically creates new clients with the new secret, verifies operation, and then retires old clients.

## 35. Recovering clients after fixing credentials

Once invalid credentials are fixed, do not merely clear the alert. Verify:

1. The new secret version reached the right instances.
2. New Kafka clients are using that config.
3. TLS/SASL handshakes succeed.
4. Producers can perform required send operations.
5. Consumers can join groups and fetch permitted topics.
6. Transactional producers can initialize/commit if the service uses transactions.
7. ACLs still align with the new principal.
8. Consumer lag starts falling and listener success rate rises.
9. Auth exceptions no longer repeat on reconnect.
10. Readiness returns to `UP` only once mandatory capabilities are operational.

If existing clients cannot refresh credentials, recreate the exact factory/container safely via lifecycle. Avoid restarting all services when only one principal is affected.

## 36. Metrics and logging for authentication incidents

Useful metrics:

| Metric | Purpose |
|---|---|
| `kafka.auth.failure.count` | Auth failure count |
| `kafka.authorization.failure.count` | AuthZ denial count |
| `kafka.client.reconnect.count` | Client reconnects |
| `kafka.client.connection.error.count` | Connection errors |
| `kafka.consumer.assignment.count` | Partition assignment |
| `kafka.consumer.poll.rate` | Poll loop |
| `kafka.consumer.lag` | Backlog |
| `kafka.producer.send.failure` | Publish failures |
| `kafka.transaction.abort.count` | Transaction failures |
| `kafka.readiness.state` | Capability status |
| `kafka.credential.version` | Approved version/reference, never the secret |
| `kafka.auth.last_success_timestamp` | Most recent successful operation |

Metric names are suggested conventions; some require custom instrumentation. Never use usernames, tokens, raw exceptions, or event IDs as metric tags if they create high cardinality or expose secrets.

Safe structured log:

~~~text
event=kafka_authentication_failure
service=orders-service
instance=orders-pod-2
client_type=consumer
principal=orders-reader
mechanism=SCRAM-SHA-512
security_protocol=SASL_SSL
failure_kind=sasl_authentication
secret_version=kv-2026-11
listener_id=ordersListener
~~~

Log `principal` only when allowed by policy. Never log JAAS strings, passwords, OAuth tokens, private keys, or raw headers.

## 37. Alerting and noise reduction

Authentication failures can fire on every reconnect, so a single bad credential can generate many logs.

Best practices:

- Group by service, instance, client type, and approved principal.
- Deduplicate repeated events within an incident.
- Distinguish AuthN from AuthZ and TLS/network.
- Correlate with secret rotation/deployment timelines.
- Alert when readiness stays down continuously or workload lag exceeds SLA.
- Do not page on every reconnect once an incident is open.
- Alert separately when a credential rotation approaches the end of its overlap window.
- Escalate when production-critical ACL permissions are missing.
- Avoid restart loops during widespread broker/identity provider outages.

A single auth failure during rollout may be transient; multiple instances failing simultaneously with the same principal usually warrant investigating shared secrets/configs/provisioning.

## 38. Integration tests for authentication failures

Do not only mock exceptions. Include tests across each layer:

1. **Invalid SASL credentials**: broker rejects handshake; client cannot execute operations.
2. **Wrong SASL mechanism**: client/broker mismatch produces the expected error.
3. **TLS trust failure**: client does not trust certificate chain; verify classification is not confused with ACLs.
4. **Authorization denied**: authentication succeeds, yet principal lacks `READ`/`WRITE`/Group permissions.
5. **Credential rotation**: old and new clients operate under the overlap/rollout policy.
6. **OAuth token expiry**: callback refresh or readiness transition works per supported mechanism.
7. **Consumer recovery**: after fixing credentials and recreating clients, consumer joins group and fetches.
8. **Producer recovery**: after fixing, sends succeed and transactions commit if required by workload.
9. **Health behavior**: readiness goes `DOWN` when mandatory capabilities fail; liveness does not fail solely on invalid broker credentials.
10. **Health check permissions**: indicator does not require broader permissions than the workload.
11. **Secret safety**: logs/spans/health details contain no passwords/tokens.
12. **Retry storm protection**: repeated auth errors are deduplicated and do not trigger infinite restarts.

With test broker containers, authentication/ACL features must be configured accordingly; not every default image supports full SCRAM/OAuth/Kerberos. When using mocked brokers, document limitations since mocks may not simulate real handshakes/ACLs.

## 39. Checking readiness in tests

A readiness test should verify **semantics**, not just HTTP status:

- When the application starts without authenticating to Kafka, readiness does not report `UP` if Kafka is a mandatory dependency.
- Liveness remains `UP` when the JVM and process are healthy.
- Once the principal is fixed and the client executes required operations, readiness returns to `UP`.
- An `AdminClient` `DESCRIBE` error does not force readiness `DOWN` if the workload does not need that operation and policy does not require it.
- A consumer lacking topic `READ` ACLs must not be considered ready for a consume workload.
- A producer lacking `WRITE` ACLs must not be considered ready for a publish workload.
- Health responses contain only error categories and safe metadata.

If a service has multiple independent capabilities, separate readiness groups per capability may be needed instead of a single application-wide Kafka boolean.

## 40. Production runbook for authentication failures

**Identify**

1. Identify service/instance/client type/listener ID.
2. Collect exception class and safe root cause.
3. Identify principal, security protocol, and mechanism.
4. Identify broker listener/endpoint and start time.

**Check authentication**

5. Check secret reference/version and injection.
6. Check JAAS/module/callback configuration.
7. Check OAuth issuer/audience/expiry or Kerberos principal/ticket.
8. Check TLS certificate chain, expiry, hostname, and keystore/truststore.
9. Cross-check broker authentication logs.

**Check authorization**

10. Verify the principal is properly provisioned.
11. Check ACLs for topic/group/cluster/transactional ID.
12. Check whether health-check principal and operation are appropriate.
13. Never grant broad permissions or superuser as a temporary patch.

**Recover**

14. Update credentials/ACLs/certificates in the proper place.
15. Refresh or recreate Kafka clients per supported mechanism.
16. Restart only affected containers/instances if needed, avoiding fleet-wide restarts.
17. Verify producer sends or consumer fetches actually succeed.
18. Check lag, offsets, transactions, and duplicate side effects.

**Readiness and close incident**

19. Keep readiness `DOWN` while mandatory capabilities remain unoperational.
20. Keep liveness `UP` if the process is healthy.
21. Wait for an operation success with the right principal before marking ready.
22. Record root cause, secret version, and rotation actions.
23. Verify old credentials were revoked after the overlap window.

## 41. Common implementation mistakes

**Confusing authentication with authorization.** Changing a password when an ACL is missing will not fix the error.

**Using a single AdminClient health check to represent all clients.** It does not prove consumers/producers have permission for business operations.

**Granting superuser to workloads.** Increases blast radius and hides ACL gaps.

**Logging JAAS/passwords/tokens.** Creates extra copies of secrets inside logs.

**Using SASL_PLAINTEXT on unprotected networks.** Credentials may travel unencrypted on the wire.

**Disabling TLS hostname verification or using trust-all.** Hides certificate errors and weakens broker authentication.

**Updating a Kubernetes Secret without refreshing Kafka clients.** Existing clients may continue using old credentials.

**Restarting pods via liveness on auth failure.** The same bad config causes a crash loop.

**Treating container running as authenticated.** Lifecycle state does not prove operations succeed.

**Treating Admin describe success as consume permission.** `READ`/Group ACLs are separate.

**Not separating producer/consumer principals when needed.** One failing client can obscure the other.

**Retrying authentication infinitely without backoff.** Creates connection/authentication storms.

**Closing the incident once the handshake succeeds.** The workload may still lack topic/group/transaction permissions.

## 42. Pre-production checklist

**Identity and protocol**

- [ ] Each Kafka client uses the right principal.
- [ ] `security.protocol` and `sasl.mechanism` match the broker listener.
- [ ] JAAS/callback configuration is correct.
- [ ] TLS truststore/keystore are configured as needed.
- [ ] OAuth/Kerberos token/ticket refresh is planned.
- [ ] Secrets never appear in source/logs/spans/Actuator.

**Authorization**

- [ ] Consumer has required `READ`/Group permissions.
- [ ] Producer has `WRITE` permission on topics.
- [ ] Transactional producer has transactional ID permissions.
- [ ] Admin/health checks hold only required permissions.
- [ ] No superuser is used for normal workloads.

**Health/readiness**

- [ ] Readiness reflects mandatory Kafka capabilities.
- [ ] Liveness does not depend directly on broker outages.
- [ ] Health checks use the right principal and operation.
- [ ] Container running is not treated as proof of authentication.
- [ ] Readiness recovers only after actual operation success.

**Rotation and recovery**

- [ ] Secret versioning and overlap/rollout policies exist.
- [ ] Known which clients must be recreated after rotation.
- [ ] Auth failures are deduplicated and backed off.
- [ ] No restart loops during broker/identity provider outages.
- [ ] Runbooks exist for ACLs, TLS, SASL, and OAuth/Kerberos.
- [ ] Post-recovery checks cover lag, offsets, transactions, and idempotency.

**Testing**

- [ ] Tested invalid credentials and mechanism mismatch.
- [ ] Tested TLS trust and authorization separately.
- [ ] Tested credential rotation.
- [ ] Tested readiness/liveness behavior.
- [ ] Tested producer/consumer capabilities separately.
- [ ] Tested that logs and spans never leak secrets.

## 43. Conclusion

An **authentication failure** in Spring Kafka can prevent producers, consumers, `KafkaAdmin`, or transactional producers from performing operations. Handling it accurately requires distinguishing **authentication** (verifying the principal) from **authorization** (permissions on topics, groups, clusters, and transactional IDs), while separating SASL, TLS, OAuth, and Kerberos errors from network timeouts.

In **Health and readiness**, never treat container running as proof that Kafka is authenticated, and never use liveness to restart continuously when credentials are wrong. Readiness should reflect the Kafka capabilities genuinely required for the application's role; health checks must use the right principal/operation without demanding broader permissions than the workload.

When remediating, inspect client type, protocol, mechanism, secret version, certificates/tokens/tickets, broker logs, and ACLs. Perform rotations with overlap where possible, refresh/recreate the exact Kafka clients, verify produce/consume/transaction operations succeed, and only then mark ready. **Never log credentials, never grant superuser as a temporary workaround, and never close an incident just because a handshake succeeded.**
