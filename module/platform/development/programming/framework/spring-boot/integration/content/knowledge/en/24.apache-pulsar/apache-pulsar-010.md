# Authentication, TLS, and Client Resource Control

In Spring Boot, Apache Pulsar connects to the application through `PulsarClient`, framework-created producers/consumers, `PulsarTemplate`, and `@PulsarListener`. An integration flow can run smoothly in development yet fail in production because a token expired, a TLS certificate had a hostname mismatch, or message queues grew unbounded when the broker slowed down.

This lesson establishes how to configure and verify **identity, transport security, authorization, and resource budgets** for the Pulsar Java client. Examples connect to a Spring Boot service receiving HTTP requests to create orders, writing to a database, and emitting an `OrderCreated` event to topic `persistent://commerce/orders/order-created`; another consumer processes the event via the broker and may call downstream HTTP or DB services. The goal is preserving data contracts, transactions, deduplication, and predictable failure behavior when connectivity is unstable.

## 1. Distinguishing TLS, Authentication, and Authorization

| Layer | Problem solved | Must verify |
| --- | --- | --- |
| **TLS** | Secures the transport channel between client and broker/proxy; verifies server identity | CA, certificate chain, SAN/hostname, certificate expiry, protocol |
| **Authentication** | Establishes who the client/role is | Token, OAuth2, or mTLS client certificate; expiry and refresh mechanism |
| **Authorization** | What the role is allowed to do on tenant/namespace/topic | Scoped `produce`, `consume`, and admin permissions |

TLS does not automatically grant topic access permissions. A valid token does not replace verifying the broker certificate. Successfully connecting to the service URL does not prove the role can publish or consume on every topic.

~~~mermaid
flowchart LR
    A[Spring Boot] --> B[TLS handshake and server verification]
    B --> C[Broker/proxy]
    C --> D[Authentication: establish role]
    D --> E{Authorization}
    E -->|Permitted| F[Produce / consume topic]
    E -->|Denied| G[Reject operation]
~~~

The cluster itself must enable TLS, the authentication provider, and authorization; client-side configuration alone cannot substitute for broker configuration. With mTLS, the broker must also trust the client CA and map client certificates to identities/roles per cluster policy.

## 2. Pulsar Binary Endpoint vs Admin API

The Pulsar binary protocol and REST Admin API are two separate connection paths:

| Component | Illustrative Service URL | Notes |
| --- | --- | --- |
| Unencrypted binary client | `pulsar://broker.example:6650` | Only in environments explicitly permitting plaintext |
| TLS binary client | `pulsar+ssl://pulsar.example:6651` | Used by producers/consumers connecting to broker or proxy |
| HTTP Admin | `http://admin.example:8080` | Unencrypted REST admin |
| HTTPS Admin | `https://admin.example:8443` | TLS-protected REST admin |

Ports `6650`, `6651`, `8080`, and `8443` are common conventions, not mandatory defaults when clusters use custom listeners or proxies. Never put an `https://...` URL into `spring.pulsar.client.service-url` or `pulsar+ssl://...` as the Admin URL.

When connecting directly to multiple brokers, the client looks up a topic and connects to the broker's advertised address (`advertisedListeners`). Ensure both the initial endpoint **and the post-lookup brokers** are reachable over the network on the expected scheme/port, with DNS names matching server certificate SANs. Behind a proxy or load balancer, verify where TLS terminates and whether the backend hop is encrypted.

**Rule:** keep `allowTlsInsecureConnection(false)` and enable hostname verification. If a certificate fails, fix the CA/truststore, DNS, SAN, or expired certificate; never disable verification to bypass errors.

## 3. Spring Boot Example: Token Authentication and TLS

With a Spring Boot starter matching your project, the framework auto-configures `PulsarClient`, producer/consumer factories, and integration components. Gradle example:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-pulsar'
}
~~~

Application configuration sourcing the token from a secret manager or environment variables:

~~~yaml
# application.yml - contains no real tokens
spring:
  pulsar:
    client:
      service-url: ${PULSAR_SERVICE_URL}
      authentication:
        plugin-class-name: org.apache.pulsar.client.impl.auth.AuthenticationToken
        param:
          token: ${PULSAR_AUTH_TOKEN}
      connection-timeout: 10s
      operation-timeout: 30s
      threads:
        io: 2
        listener: 4

app:
  pulsar:
    tls:
      ca-file: ${PULSAR_CA_FILE}
~~~

Deployment example: `PULSAR_SERVICE_URL=pulsar+ssl://pulsar.internal.example:6651`, CA at `/etc/pulsar/tls/ca.pem`, and a token issued for the service's role. Never commit tokens, private keys, or passwords to Git, logs, or container images. Never prepend `Bearer ` unless your auth plugin expects it.

Parameter names under `spring.pulsar.client.authentication.param.*` **must match the exact names** required by the plugin. Spring Boot does not perform relaxed binding on these map keys. For example, the OAuth2 plugin expects `issuerUrl`; `issuer-url` or `issuerurl` are not equivalent. When sourcing values from environment variables, declare the exact key name in `application.yml` rather than relying on env vars converting to camelCase.

### 3.1. Configuring TLS via `PulsarClientBuilderCustomizer`

Per Spring for Apache Pulsar documentation, detailed TLS settings may require `PulsarClientBuilderCustomizer`; do not assume your Spring Boot version provides comprehensive `spring.pulsar.client.tls.*` properties. The example below uses the Java client API `org.apache.pulsar.client.api` (API v4), commonly used by Spring Pulsar:

~~~java
import org.apache.pulsar.client.api.SizeUnit;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.pulsar.core.PulsarClientBuilderCustomizer;

@Configuration
class PulsarClientConfig {
    @Bean
    PulsarClientBuilderCustomizer securePulsar(
            @Value("${app.pulsar.tls.ca-file}") String caFile) {
        return builder -> builder
                .tlsTrustCertsFilePath(caFile)
                .allowTlsInsecureConnection(false)
                .enableTlsHostnameVerification(true)
                .connectionsPerBroker(1)
                .memoryLimit(64, SizeUnit.MEGA_BYTES);
    }
}
~~~

`caFile` must point to an actual CA mounted inside the pod with read permissions. If the certificate is already trusted via the JVM's default truststore, a separate CA path may be unnecessary depending on setup, though hostname verification must remain enabled. `connectionsPerBroker(1)` and `memoryLimit(64, SizeUnit.MEGA_BYTES)` are **starting values for benchmarking**, not universal optimums.

Java API v5 changes certain resource configuration types (such as how memory limits are expressed). Copy this snippet only when targeting the matching client API and Spring Pulsar version; when moving to v5, consult the v5 documentation.

### 3.2. Admin API Requires Separate Configuration

Spring Boot can auto-configure `PulsarAdministration`/`PulsarAdmin`. If the application **genuinely needs** the Admin API, configure its URL and authentication separately:

~~~yaml
spring:
  pulsar:
    admin:
      service-url: ${PULSAR_ADMIN_URL}
      authentication:
        plugin-class-name: org.apache.pulsar.client.impl.auth.AuthenticationToken
        param:
          token: ${PULSAR_ADMIN_TOKEN}
~~~

`PULSAR_ADMIN_URL` may look like `https://pulsar-admin.internal.example:8443`. With an internal CA, the Admin client also requires matching TLS/trust/hostname configuration, typically via `PulsarAdminBuilderCustomizer`. Trusting a CA on the binary client does not imply the Admin client shares that trust setup. Separate admin roles from producer/consumer roles; in production, provision topics, namespaces, and ACLs via provisioning pipelines rather than granting runtime apps superuser rights.

## 4. Token, OAuth2, and mTLS: Choosing by Environment

| Mechanism | Identity mechanism | Operational responsibilities |
| --- | --- | --- |
| Token/JWT | `AuthenticationToken` plugin receives an issued token | Token expiry, issuer/audience if applicable, refresh, revocation |
| OAuth2 | `AuthenticationOAuth2` with parameters like `issuerUrl`, `privateKey`, `audience` | Token fetch permissions, secrets, connectivity to identity provider |
| mTLS PEM | Client certificate and private key; broker maps identity/role | Mutual CA trust, private keys, renewal, and SANs |
| mTLS JKS | Keystore/truststore and matching TLS auth plugin | Passwords, store format, file paths, certificate lifecycle |

Example mTLS PEM setup on the client builder:

~~~java
import org.apache.pulsar.client.api.AuthenticationFactory;

// Alternative option replacing token authentication:
builder
    .authentication(AuthenticationFactory.TLS(
            "/etc/pulsar/tls/client.cert.pem",
            "/etc/pulsar/tls/client.key-pk8.pem"))
    .tlsTrustCertsFilePath("/etc/pulsar/tls/ca.pem")
    .allowTlsInsecureConnection(false)
    .enableTlsHostnameVerification(true);
~~~

Never combine mTLS authentication with the token plugin without knowing which auth setting takes effect on the builder: the two snippets show **two distinct options**. mTLS works only when the broker requires/accepts client certs and configures the matching provider/role mapping.

Regardless of plugin, test all three cases: valid authorized credentials succeed; invalid credentials are rejected; valid credentials **lacking topic permission** are also rejected.

## 5. Applying Least Privilege per Topic and Role

In an ordering system, identities can be separated as follows:

| Service/actor | Topic scope | Required permissions |
| --- | --- | --- |
| `order-api` | `persistent://commerce/orders/order-created` | `produce` |
| `order-projection` | Same topic | `consume` |
| `event-auditor` | Dedicated audit topic | Scoped `consume` for audit |
| `infra-provisioner` | Managed namespaces | Controlled admin rights; kept away from runtime apps |

Never hand the same superuser token to every service, since compromising any container would expose the entire cluster. When a single application needs both producer and consumer with strict privilege separation, consider two separate identities/clients or split processes along permission boundaries.

Being permitted to `consume` from a topic does not mean event contents are inherently trustworthy. Consumers must still validate schema, tenant, version, event ID, business fields, and target system authorization. Avoid placing passwords, access tokens, or unnecessary personal data in payloads or message properties. Particularly sensitive data may require payload-level encryption independent of transport TLS.

## 6. Rotating Secrets and Certificates

Security policies only hold when operated continuously:

1. **Provisioning secrets:** use a secret manager or Kubernetes Secret, mount certificates/keys as read-only files, and restrict human and workload access to least privilege.
2. **Environment isolation:** production roles/tokens must never be reused in development/staging.
3. **Expiration tracking:** monitor token and certificate expiry with advance alerts and assigned rotation owners.
4. **Credential reload:** updating a file on disk does not guarantee the client/plugin reloads it immediately. Verify whether your plugin supports live refresh or requires rolling restarts/client recreation.
5. **CA rotation:** maintain an overlap trust window where both old and new CAs are trusted, and check broker/proxy hostnames before retiring the old CA.
6. **Prevent leaks:** never log the raw Spring Environment, authentication config, tokens, private keys, or URLs with embedded credentials; lock down Actuator/config endpoints.

A testable rotation procedure: issue new token → update secret source → rolling-restart replicas or refresh via plugin → verify produce/consume → revoke old token. When zero downtime is mandatory, verify client refresh and retry behavior in your exact deployed version.

## 7. `PulsarClient` Is a Shared Lifecycle Resource

`PulsarClient` manages network I/O, threads, lookups, connections, and memory buffers. Creating a new client on **every HTTP request, every event publish, or every message receive** leaks or explodes sockets, threads, and memory with traffic.

~~~mermaid
flowchart TD
    A[Spring Boot ApplicationContext] --> B[PulsarClient managed per cluster / identity]
    B --> C[ProducerFactory / PulsarTemplate]
    B --> D[ConsumerFactory / PulsarListener]
    C --> E[Pending producer messages]
    D --> F[Prefetch / processing consumers]
    E --> G[Broker]
    F --> G
~~~

Prefer the Spring Boot auto-configured `PulsarClient` and Spring Pulsar's managed producer factory/cache. When multiple clusters or identities are required, create separate clients deliberately while summing total resource usage across all clients in the pod. If creating clients manually, take responsibility for closing producers, consumers, and clients on shutdown; never close a Spring-managed bean after a single request.

### 7.1. Key Parameters

| Parameter | Effect | Configuration risk |
| --- | --- | --- |
| `ioThreads` | Threads managing connections and network I/O | Too few starves event loops; too many wastes CPU |
| `listenerThreads` | Threads executing Pulsar client callbacks/listeners | Slow callbacks can starve threads; too many wastes resources |
| `connectionsPerBroker` | Connections from client to each broker | Too many increases sockets and broker overhead; too few may cap throughput |
| `memoryLimit` (API v4) | Buffer memory budget managed by Pulsar client | Unbounded or overly high creates memory pressure |
| `connectionTimeout` | Wait limit when opening connections | Too long delays surfacing network failures |
| `operationTimeout` | Limit for client metadata/control operations | Too short triggers false timeouts; too long stalls callers |
| Client/producer/consumer count | Total connections, queues, callbacks, subscriptions | Multiplies quickly across replicas, topics, and partitions |

`memoryLimit` does not bound total **JVM RSS, heap, or direct memory**. Application objects, JSON serialization, callback queues, Netty buffers, and business threads can allocate outside Pulsar client accounting. In Java client API v5, syntax and pending-send limits differ from API v4; follow version-specific documentation.

Setting `ioThreads(2)`, `listenerThreads(4)`, and `connectionsPerBroker(1)` is only a baseline. Measure CPU, socket counts, latency, throughput, memory, and broker load before increasing.

## 8. Producer Backpressure When Brokers Slow Down

Producers often send asynchronously to avoid blocking HTTP threads. However, if new `sendAsync()` calls outpace broker acknowledgments, pending messages grow until buffers or memory exhaust.

With client API v4, you can bound pending messages directly on the producer:

~~~java
import java.util.concurrent.TimeUnit;
import org.apache.pulsar.client.api.Producer;
import org.apache.pulsar.client.api.Schema;

// client is a PulsarClient created/managed with the application lifecycle.
Producer<String> producer = client.newProducer(Schema.STRING)
        .topic("persistent://commerce/orders/order-created")
        .maxPendingMessages(1_000)
        .blockIfQueueFull(false)
        .enableBatching(true)
        .batchingMaxPublishDelay(10, TimeUnit.MILLISECONDS)
        .create();
~~~

With `blockIfQueueFull(false)`, the application receives an error immediately when the queue cannot accept more messages and must handle it, e.g., retrying via an outbox. With `true`, callers wait for space, risking blocking critical threads. Defaults and pending queue bounds differ between Java API v4 and v5, especially for partitioned producers; never assume fixed numbers across versions.

~~~java
producer.newMessage()
        .key(orderId)
        .property("eventId", eventId)
        .value(eventJson)
        .sendAsync()
        .whenComplete((messageId, error) -> {
            if (error != null) {
                // Record publish failure; retain outbox record for retry.
            } else {
                // Pulsar acknowledgment: allow updating outbox status.
            }
        });
~~~

This snippet illustrates completion handling; production components need semaphores/bounded work queues and proper exception handling. If thousands of requests queue `sendAsync` ahead of completion, enforce **application-level in-flight limits** rather than relying solely on the producer pending queue.

**Never infer "timeout means the broker did not write the message."** The broker may have persisted it while the ack dropped. A retry can produce a duplicate; stable event IDs, outboxes, and idempotent consumers handle uncertain outcomes. Broker-side deduplication, if enabled, has specific scope and configuration rules and does not replace all business checks.

Batching boosts throughput yet adds wait latency. When consumers use `Key_Shared` subscriptions for per-key processing, verify the producer enables **key-based batching** or disables batching where required; standard batching can disrupt key distribution. Compression saves bandwidth at the cost of CPU; benchmark with real payloads.

## 9. Consumer Controls: Prefetch, Concurrency, and Acknowledgment

Pulsar consumers prefetch messages to cut network round trips; multiplied across partitions, consumers, and replicas, receive buffers can consume significant memory. `receiverQueueSize` in API v4 tunes prefetched messages; partitioned consumer aggregate caps vary by version and must also be checked.

~~~java
import org.apache.pulsar.client.api.Consumer;
import org.apache.pulsar.client.api.Schema;
import org.apache.pulsar.client.api.SubscriptionType;

Consumer<String> consumer = client.newConsumer(Schema.STRING)
        .topic("persistent://commerce/orders/order-created")
        .subscriptionName("order-projection")
        .subscriptionType(SubscriptionType.Key_Shared)
        .receiverQueueSize(200)
        .subscribe();
~~~

This is a Java client example; in Spring Boot, normally use `@PulsarListener` with `ConsumerFactory` and `ConsumerBuilderCustomizer` or `spring.pulsar.consumer.*` / `spring.pulsar.listener.*` properties. Never manually instantiate consumers inside every listener invocation.

Estimate receive memory as replicas × receivers/partitions × prefetched messages × payload size, plus batch/deserialization overhead. This is an approximation because internal dispatch and caps vary by version. High listener concurrency will not speed up processing if the DB pool or downstream HTTP service is already saturated.

- **Ack after successful processing:** DB transactions must commit before treating the message as handled per contract. Configure the right ack mode/container.
- **At-least-once and redelivery:** when consumers crash or acks fail, events reappear; protect with idempotency keys, unique constraints, or DB versions.
- **Bounded retries:** distinguish transient errors like DB timeouts from unrecoverable payload/schema failures; apply backoff and DLQs to stop poison pills from stalling subscriptions.
- **Ordering:** `Shared` makes no global ordering promise; `Key_Shared` relies on proper keys and batching. Never build business invariants on unverified ordering assumptions.
- **Intake throttling:** if DB/HTTP downstream slows, reduce concurrency/prefetch or add bulkheads instead of scaling parallelism endlessly.

## 10. Transaction Boundaries, Retries, and Idempotency

In HTTP → DB → Pulsar flows, DB commit succeeding while publish fails is a real failure mode. A Pulsar transaction does not automatically encompass a relational database transaction. When "committed orders must eventually emit events," apply a **transactional outbox**:

~~~mermaid
flowchart LR
    A[HTTP creates order] --> B[DB Transaction]
    B --> C[Write order and outbox record]
    C --> D[Commit]
    D --> E[Outbox publisher]
    E --> F[Producer sends to Pulsar]
    F --> G[Consumer]
    G --> H[DB commit and ack]
~~~

An independent publisher polls the outbox, calls the Pulsar producer, and marks sent only upon appropriate acknowledgment. On publish timeouts, retry with the same event ID and assume **duplicate sends are possible**. Consumers persist processed event IDs or check business versions inside the DB transaction to prevent repeated side effects.

When client security fails (certificates, tokens, ACLs), never retry infinitely or fall back to plaintext connections; raise alerts and retain outbox records until resolved. For low-criticality telemetry, apps may define a metered drop policy; for transactional events, never drop silently. Failure policies must follow business contracts.

When a Spring Integration flow or adapter wraps Pulsar send/receive, document explicitly whether retries belong to the adapter, broker, or HTTP/DB layer, because stacked retries across layers multiply downstream execution.

## 11. Systematic Troubleshooting

| Symptom | Causes to verify | Resolution |
| --- | --- | --- |
| TLS handshake failed | Wrong CA, hostname/SAN mismatch, expired cert | Verify trust chain, DNS, advertised broker addresses, system clock |
| Authentication failed | Bad/expired token, wrong auth plugin params, broken mTLS role mapping | Check secret source, plugin, token refresh/certificates |
| Authorization denied | Role lacks topic/namespace permission | Grant scoped `produce`/`consume`; avoid superuser tokens |
| Only Admin API fails | `https://` URL, separate Admin token or trust config | Check `spring.pulsar.admin.*` and customizers |
| Connects yet publishes slowly | Overloaded broker, full pending queue, network, batching | Measure p95/p99, queue depth, timeouts, resource pressure |
| Consumer backlog climbs | Slow DB/HTTP, excessive retries, unsuitable concurrency | Measure process time, DLQ, lower prefetch, throttle downstream |
| JVM memory climbs | Producer pending queue, receiver queue, direct buffers, retained objects | Profile heap/direct memory, check client budgets and callbacks |
| Connection breaks after rollout | CA, token, DNS, permissions, or version changed | Diff rollout config/credentials and run full integration checks |

Distinguish HTTP `401`/`403` from Admin REST against Pulsar binary protocol exceptions; never blindly translate binary errors into HTTP status codes. When TLS/auth/ACLs fail, fix configuration/identity before tuning retries.

## 12. Observability and Protecting Sensitive Data

Metrics and logs together should answer: "can clients authenticate?", "is the broker keeping up with send/receive rates?", and "were business events processed accurately?"

| Signal | Example measurements | Meaning |
| --- | --- | --- |
| Security | TLS/auth failures, authorization denials, token expiry | Detects identity/transport failures |
| Producer | Publish rate, send latency, errors/timeouts, pending messages | Detects backpressure, lost acks |
| Consumer | Ack rate, backlog, redeliveries, DLQ, process latency | Detects overloaded targets or poison messages |
| JVM and broker | CPU, heap/direct memory, threads, sockets, broker connections | Validates resource budgets |
| Business | Outbox pending age, delivery lag, duplicate events blocked | Tracks integration correctness and lag |

Micrometer/Actuator, tracing, and Pulsar client/broker metrics depend on deployment wiring; verify metrics are actually emitted in your version. Logs should record service, environment, topic, subscription, correlation ID, event ID, and error category, while **never** logging tokens, secrets, private keys, or sensitive raw payloads. Avoid high-cardinality metric tags like event ID, user ID, or message ID.

Alerts should cover post-rollout auth failure spikes, upcoming certificate expiration, sustained high producer pending queues, memory nearing quota, stalled outbox records, abnormal DLQ inflows, and rising consumer backlogs paired with degrading DB latency.

## 13. Pre-Production Test Scenarios

Testing against an unauthenticated plaintext broker checks only basic logic—it proves nothing about production TLS/auth/ACLs. Maintain an integration environment with TLS, token/mTLS, roles, and topic ACLs mirroring production.

| Scenario | How to induce | Expected outcome |
| --- | --- | --- |
| Valid role | Right CA, token/cert, granted topic permission | Produce/consume succeeds |
| Wrong CA or hostname | Alternate CA or hostname missing from SAN | Handshake rejected; no plaintext fallback |
| Expired/revoked token | Rotate or supply expired credentials | Explicit authentication failure and alert |
| Role lacks `produce` | Consumer identity attempts publish | Broker rejects |
| Role lacks `consume` | Producer identity attempts subscribe | Broker rejects |
| Unprivileged admin role | Runtime role attempts topic creation | Admin operation rejected |
| Slow broker / network drop | Throttle, drop connections, burst concurrent sends | Pending queue, memory, and retries stay bounded |
| Slow consumer | Slow DB/HTTP downstream across partitions | Backlog and latency measured; pod stays within resources |
| Lost ack | Broker persists yet caller times out | Safe retry; consumer blocks duplicate event |
| Poison message | Repeated invalid payload/schema | Bounded retries, routed to DLQ/alerted |
| Credential rotation | Swap CA or token while replicas run | Verified refresh or rolling restart procedure |

Load tests must measure CPU, socket/thread counts, heap and direct memory, message throughput, p95/p99 publish latency, consumer backlog, and business lag across replicas. Never run a single `@PulsarListener` smoke test and assume the setup survives a broker outage.

## 14. Deployment Checklist for Dev and Ops Teams

- [ ] Correct service URL scheme (`pulsar+ssl://` for binary, `https://` for admin) and listener ports.
- [ ] Trust chain and hostname verification work on both initial bootstrap endpoints and post-lookup brokers.
- [ ] Tokens/mTLS/OAuth2 scoped to the right environment with exact plugin parameters and rotation plan.
- [ ] Producer/consumer/admin roles hold least-privilege permissions per tenant, namespace, and topic.
- [ ] `PulsarClient` reused across the Spring lifecycle; client/connection/thread counts measured.
- [ ] Memory, pending producer sends, and receiver queues bounded relative to replica/partition counts.
- [ ] Consumer acks, redeliveries, DLQs, and idempotency aligned with DB transactions.
- [ ] On broker or credential errors, critical events stay preserved in the outbox; never downgrade TLS.
- [ ] Alerts, metrics, and tests cover TLS, auth, ACLs, broker outages, and resource exhaustion.

**Conclusion:** Pulsar client security and resource control are integral parts of the integration contract, not mere connection tweaks. TLS protects and authenticates endpoints; authentication/authorization constrain identity and permissions; and budgets for connections, threads, queues, and memory—paired with outbox/idempotency—keep Spring Boot predictable when brokers slow, disconnect, or transactions retry.

### References

- [Spring Boot — Apache Pulsar Support](https://docs.spring.io/spring-boot/reference/messaging/pulsar.html): starters, auto-configuration, client/admin, producer/consumer.
- [Spring for Apache Pulsar — Pulsar Client](https://docs.spring.io/spring-pulsar/reference/reference/pulsar/pulsar-client.html): TLS, auth plugins, token/OAuth2/mTLS, customizers.
- [Apache Pulsar — Set up Java client](https://pulsar.apache.org/docs/client-libraries/java-setup/): client API, memory budgets, pending producer queues, version differences.

Examples use Java client API v4; before applying in production, verify exact behavior against the Spring Boot, Spring Pulsar, and Pulsar Java client versions managed in your project, particularly for knobs changed in API v5.
