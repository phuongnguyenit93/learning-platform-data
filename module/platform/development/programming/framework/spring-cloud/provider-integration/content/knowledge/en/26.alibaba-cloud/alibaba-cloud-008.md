# Replacing Legacy Starters When No Compatible Version Exists

A Spring Boot project may currently use an older Spring Cloud Alibaba starter while needing to upgrade Spring Boot, Spring Cloud, or Java to a newer version. When the current release train lacks a compatible starter, forcing Maven to pull a close version or overriding transitive dependencies often leads to unpredictable failures: the application may compile yet fail at startup, lose auto-configuration, or break when invoking services.

The sustainable approach is to identify **the capability the starter provides**, then replace it with a standard Spring abstraction, an official Alibaba Cloud Java SDK, or an internal adapter. Not every starter must be replaced by another starter. For RDS and Redis, Spring Boot already provides standard integrations; for OSS, RocketMQ, or provider-specific APIs, official SDKs can be the right fit; for discovery, circuit breaking, and distributed transactions, you must carefully evaluate semantic equivalence before switching libraries.

This lesson focuses on the process of replacing legacy starters in Spring Boot applications integrated with Alibaba Cloud. The goal is to preserve business behavior, control dependencies, and establish a clear upgrade path as the framework ecosystem evolves.

After completing this lesson, you will be able to:

- Identify incompatible starters using release trains and dependency trees.
- Decouple a starter's functionality from business code before changing libraries.
- Choose among Spring Boot/Spring Cloud abstractions, official SDKs, and self-managed adapters.
- Replace integrations across data, messaging, discovery/config, traffic protection, and object storage.
- Plan testing, rollout, and rollback without having to upgrade the entire system simultaneously.

## 1. Why Do Legacy Starters Become Incompatible?

A starter typically bundles dependencies and auto-configuration so an application can consume a service with minimal setup. However, a starter is not a platform-independent API. It typically depends on:

- The Spring Boot version and how Spring Boot registers auto-configuration.
- Spring Framework, Spring Cloud Commons, and the Spring Cloud release train.
- The Java baseline, such as moving from Java 8/11 to Java 17/21.
- The Jakarta namespace (`jakarta.*`) replacing Java EE (`javax.*`) in newer Spring Framework generations.
- Client SDK versions, HTTP clients, serializers, logging, and transitive libraries.
- Configuration loading mechanisms, bootstrap contexts, bean lifecycles, and observability/metrics hooks.

An old starter may still compile against newer dependencies while remaining untested in that combination. Even starting up cleanly does not prove that service registration, config refresh, message publishing, or transactions behave properly.

### 1.1. Distinguishing Three Types of Issues

| Issue Type | Symptoms | Approach |
|---|---|---|
| No compatible release | Official release train does not list your Spring Boot/Spring Cloud version | Pick a supported version set or replace the starter's capability |
| Dependency conflict | `NoSuchMethodError`, `ClassNotFoundException`, `NoClassDefFoundError`, linkage errors, or multiple versions appearing | Inspect the dependency tree, BOMs, and dependency convergence |
| API/configuration changes | App starts, but properties no longer take effect, beans are missing, or behavior differs | Check migration guides, auto-configuration conditions, and integration tests |

Do not assume every startup failure is caused by the starter. First grab the full stack trace, identify the failing class/method, and trace which dependency provides that class.

### 1.2. Checking Compatibility Before Deciding

With Maven, inspect the dependency tree and effective versions:

```bash
mvn -q dependency:tree -Dverbose
mvn -q help:effective-pom
```

You can filter by relevant library groups if the output is too long:

```bash
mvn dependency:tree -Dincludes=com.alibaba.cloud,com.alibaba.nacos,io.seata,com.alibaba.csp,org.apache.rocketmq
```

With Gradle, use `dependencies` and `dependencyInsight` on the relevant configuration, such as `runtimeClasspath`. Check both compile and runtime classpaths because some errors only surface at runtime.

Before editing dependencies, record:

1. Current Spring Boot, Spring Framework, Spring Cloud, and Java versions.
2. Spring Cloud Alibaba release train and starters currently in use.
3. Actual client SDKs pulled in, including transitive dependencies.
4. Which beans, annotations, properties, and APIs application code invokes.
5. Behaviors that must be preserved: retries, timeouts, serialization, transactions, discovery, config refresh, metrics, and health checks.

Cross-check the official compatibility matrix and migration guide for that exact release. Do not assume two numerically close versions are compatible. Never manually pin a newer client version to "fix" an error if the starter has never been tested with that client.

## 2. Principles for Selecting a Replacement

There are three main paths. Choose the path that introduces the least coupling while satisfying functional and operational needs.

### 2.1. Prefer Standard Spring Abstractions

If the capability already exists in Spring Boot or Spring Cloud, use that abstraction first. For example:

- JDBC, JPA, and Redis: Spring Boot Data starters.
- HTTP clients: `RestClient`, `WebClient`, or HTTP interfaces appropriate to your Spring version.
- Circuit breakers: Spring Cloud CircuitBreaker with a supported implementation such as Resilience4j.
- Messaging: Spring Cloud Stream when a compatible binder exists, or an internal abstraction when using a client directly.
- Health checks and metrics: Spring Boot Actuator/Micrometer.

Standard abstractions reduce business-layer coupling to a single vendor. However, abstractions may not expose every Alibaba Cloud-specific feature; when needed, keep provider-specific logic inside an adapter.

### 2.2. Use Official SDKs When Provider Features Are Needed

For specialized services such as Object Storage Service (OSS), the official SDK typically offers APIs closely aligned with the product: multipart uploads, presigned URLs, versioning, lifecycle, or security options. Using an SDK does not automatically require a Spring starter; the application can define client beans and call the SDK through a service adapter.

The advantage is keeping pace with service APIs without waiting for a community starter. In return, application code must manage client lifecycles, credential providers, timeouts, retries, connection pools, and error mapping.

### 2.3. Create an Internal Adapter to Isolate the SDK

Do not let SDK types leak across controllers, domains, and business services. Define an interface tailored to your application's needs, then implement it using the current SDK. For example:

```java
public interface ObjectStorage {
    StoredObject put(String key, byte[] content, String contentType);

    byte[] get(String key);

    void delete(String key);
}
```

An `AliyunObjectStorage` implementation can invoke the OSS SDK; a test implementation can use a fake or local emulator if available. When changing SDKs or switching cloud providers, changes stay mostly confined to the adapter and configuration.

Adapters should reflect your application's real use cases. Avoid building bloated interfaces that mirror an entire vendor API, as that merely shifts coupling from the SDK to an equally rigid interface.

## 3. Replacement Map by Alibaba Cloud Capability

The following table serves as a starting point for categorizing starters. Exact artifact names and APIs must be verified against your target release; do not treat this table as a claim that every product has a one-to-one drop-in starter replacement.

| Legacy Capability | Typically Suitable Replacement | Key Aspects to Preserve or Evaluate |
|---|---|---|
| Connecting to ApsaraDB RDS | Spring Boot JDBC/JPA + engine JDBC driver | Transactions, pooling, TLS, migrations, SQL, and timeouts |
| Connecting to Tair/Redis | Spring Boot Data Redis + Lettuce/Jedis | Auth, TLS, cluster/proxy mode, serialization, and TTL |
| OSS | Alibaba Cloud OSS Java SDK wrapped in an internal adapter | Credential provider, multipart, retries, URLs, and bucket/object permissions |
| RocketMQ | Official RocketMQ Java client; or a compatible Spring Cloud Stream binder | Producer/consumer lifecycle, groups, retries, ordering, ACLs, and idempotency |
| Nacos discovery/config | Supported Nacos client or migrating to another discovery/config platform | Registry semantics, config refresh, namespaces, health, and bootstrap |
| Sentinel | Controlled Sentinel core integration or Spring Cloud CircuitBreaker/Resilience4j | Flow control/hotspots are not equivalent to a basic circuit breaker |
| Seata | Seata client/server in a compatible release; or local transactions + outbox/Saga/TCC | Global transactions, compensation, locking, timeouts, and failure recovery |
| Credentials and secrets | Platform credential providers/secret managers | Rotation, workload identity, least privilege, and auditing |

Some replacements are equivalent in intent yet differ in semantics. For example, Resilience4j provides configurable circuit breakers, retries, rate limiters, and bulkheads; it does not automatically replicate Sentinel's resource-based flow control, hotspot parameters, or dashboard rules. Likewise, outbox/Saga is not a clone of Seata AT; it is an architectural choice with a different consistency model.

## 4. Replacing Data Starters with Spring Boot Data

This is usually the easiest group to replace because RDS and Redis already have standard Spring Boot integrations. Applications do not need an Alibaba-specific starter just to create a JDBC `DataSource` or a Redis connection factory.

### 4.1. RDS via JDBC/JPA

Replace the legacy starter with `spring-boot-starter-jdbc` or `spring-boot-starter-data-jpa` and the matching engine driver:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>
    <dependency>
        <groupId>com.mysql</groupId>
        <artifactId>mysql-connector-j</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
```

Example configuration for an RDS private endpoint using environment variables:

```yaml
spring:
  datasource:
    url: ${RDS_JDBC_URL}
    username: ${RDS_USERNAME}
    password: ${RDS_PASSWORD}
    hikari:
      maximum-pool-size: ${RDS_POOL_MAX:10}
      connection-timeout: 30000
  jpa:
    open-in-view: false
    hibernate:
      ddl-auto: validate
```

Leave schema migrations to Flyway/Liquibase. Size `maximum-pool-size` according to total replica count and RDS connection limits. When TLS is enabled, configure the driver to verify certificates/hostnames per engine documentation; never disable TLS verification just to make connections succeed.

### 4.2. Tair via Spring Data Redis

Replace the legacy starter with:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-redis</artifactId>
</dependency>
```

Configure endpoint and credentials:

```yaml
spring:
  data:
    redis:
      host: ${REDIS_HOST}
      port: ${REDIS_PORT:6379}
      username: ${REDIS_USERNAME:}
      password: ${REDIS_PASSWORD}
      timeout: 2s
      ssl:
        enabled: ${REDIS_SSL_ENABLED:false}
```

For password-only accounts, omit `username` if required by the account type or client version. For custom accounts, pass username and password separately. Check Tair's cluster/proxy mode configuration; a proxy endpoint can be used like a normal Redis endpoint, whereas direct connections may require a cluster-aware client.

After replacing, test every behavior previously provided by the old starter: serialization, key prefixes, TTLs, connection timeouts, reconnects, TLS, health indicators, and metrics. Do not only check `PING`; run real operations against keys in a dedicated test namespace.

## 5. Replacing the OSS Starter with the SDK and an Adapter

If the legacy OSS starter is incompatible, the application can use the OSS Java SDK directly. Choose the SDK generation actively maintained and documented by Alibaba Cloud at deployment time; never mix APIs from older and newer SDK generations in the same code or pin an unverified version.

### 5.1. Designing the Application Boundary

A small interface keeps the domain free from vendor `OSSClient`, request objects, or exception classes:

```java
public interface DocumentStorage {
    void upload(String documentId, byte[] bytes, String contentType);

    DownloadedDocument download(String documentId);

    void remove(String documentId);
}
```

The adapter implementation is responsible for:

- Mapping `documentId` to a safe object key without directly using user-supplied paths.
- Selecting the bucket from environment configuration and verifying matching bucket/region settings.
- Building the client with a credential provider rather than embedding AccessKey/SecretKey in code.
- Setting connect/read timeouts, bounded retries, and multipart thresholds by file size.
- Translating SDK exceptions into meaningful application errors while preserving the cause for diagnostics.
- Closing the client on application shutdown when the SDK requires explicit lifecycle management.

### 5.2. Configuring Credentials and Permissions

Within Alibaba Cloud, prefer workload/role identity mechanisms suited to the runtime (such as ECS RAM roles or platform-supported workload identities) over long-lived AccessKeys in files. If AccessKeys must be used, store them in a secret manager, restrict bucket/object permissions, rotate them, and never log credentials.

Separate permissions for upload, download, delete, and presigned URL generation. A service that only uploads documents does not need bucket-delete or bucket-wide list permissions. Keep buckets private and issue presigned URLs scoped strictly to the required expiration, HTTP method, and object.

### 5.3. Testing the Adapter

Unit tests can mock the client interface or transport at the adapter layer. Integration tests need a dedicated test bucket, an isolated prefix, and restricted credentials. Test byte-for-byte upload/download, content types, object keys, permission denials, timeouts, retries, and multipart uploads. Never run automated object-deletion tests against production buckets.

## 6. Replacing the RocketMQ Starter When the Binder Is Incompatible

If the current RocketMQ Binder does not support your release train, there are two options:

1. Choose a compatible binder/release published and tested with your project's Spring Cloud Stream version.
2. Use the official RocketMQ Java client directly, wrapping producers/consumers in an internal adapter.

Do not upgrade the binder or transitive client independently and assume binary compatibility. The binder and client may depend on a tightly coupled set of broker APIs and behaviors.

### 6.1. Keeping the Event Contract Independent of the Client

Define events using application contracts rather than using SDK internal message objects as domain events:

```java
public record OrderCreated(
    String eventId,
    String orderId,
    long occurredAtEpochMillis,
    int schemaVersion
) {}

public interface OrderEventPublisher {
    void publish(OrderCreated event);
}
```

The RocketMQ implementation serializes the event with the chosen serializer, attaches appropriate keys/tags/headers, and sends it via the client. Consumers deserialize the message back into the internal contract before invoking application services. This lets you swap clients without modifying domain logic.

### 6.2. Behaviors That Must Not Be Overlooked

- Producers must handle timeouts and ambiguous send outcomes: the broker may have received the message even if the client never received the response.
- Consumers must be idempotent because messages can be redelivered.
- Configure stable consumer group names separated by application/environment.
- Define retry policies, backoff, retry limits, and dead-letter queues.
- If per-aggregate ordering is required, use message keys/sharding keys and the appropriate ordered mode; do not assume topic-wide ordering.
- Monitor backlog, consumer lag, message age, retries, and DLQs.
- Manage ACLs/credentials, TLS, and endpoints per ApsaraMQ for RocketMQ instance.

If business logic must guarantee an event is emitted after a database commit, use a transactional outbox or transaction messages according to broker capabilities and architecture. Do not simply call `publish()` after `repository.save()` and assume the two operations are atomic. An outbox persists business data and the event record inside the same local database transaction; a publisher retries emitting the event while consumers handle messages idempotently.

## 7. Replacing Nacos, Sentinel, and Seata Starters: Semantic Evaluation Required

This group is harder to replace because starters may hook deeply into Spring lifecycles, discovery, rule engines, or transaction propagation. Before switching, catalog every feature currently in use.

### 7.1. Nacos Discovery/Config

If the Nacos starter lacks a compatible release:

- Check whether a standalone supported Nacos Java client exists independently of the starter; if using it directly, build an adapter managing registration, subscriptions, config fetching, and lifecycle.
- If running on Kubernetes, evaluate Kubernetes Services/DNS for discovery and ConfigMaps/Secrets or an appropriate config platform for configuration. Switching requires reviewing health checks, rollouts, namespaces, and config update workflows.
- If standardizing on Spring Cloud Commons, evaluate a compatible `DiscoveryClient` implementation or another discovery platform. Verify load balancing, instance metadata, health checks, and deregistration on shutdown.
- For centralized config, choose a config service with supported refresh mechanics. Do not write custom config polling that mutates beans arbitrarily at runtime.

If calling the Nacos Java client directly, do not scatter it across every business service. The adapter should expose an internal contract for resolving services/config. Test scenarios including registry disconnect, stale instances, config updates, and application startup while Nacos is unavailable.

### 7.2. Sentinel Traffic Protection

If basic circuit breaking is needed, Spring Cloud CircuitBreaker with Resilience4j can be a natural choice. However, compare feature coverage carefully:

| Feature Currently Used | Replacement Capability to Evaluate |
|---|---|
| Error-rate/latency circuit breaker | Resilience4j CircuitBreaker can cover this with matching threshold/window settings |
| Bounded retries | Resilience4j Retry or client retry policies; avoid nested retries |
| Bulkhead/concurrency limits | Resilience4j Bulkhead or concurrency limits on executors/clients |
| Per-resource rate limiting | Resilience4j RateLimiter or gateway/platform rate limiting |
| Parameter-based hotspot throttling | Requires custom gateway/application design or retaining a mechanism supporting this feature |
| Dynamic dashboard rules and rule persistence | Must replace rule management, storage, distribution, and auditing together |

Do not swap Sentinel for a basic circuit breaker and claim all rules were preserved. If hotspot parameters or system protection are in use, inventory every rule and design equivalent safeguards. Use meaningful business fallbacks rather than returning fake data to mask dependency failures.

### 7.3. Seata Distributed Transactions

If no compatible Seata client/server combination exists, never patch bytecode, override internal dependencies, or pair mismatched client and TC releases just to get past startup errors.

First confirm whether the system genuinely requires distributed transactions or only used the annotation out of convenience:

- If data lives in a single database, prefer Spring's local transactions (`@Transactional`).
- If an event must be emitted after a database commit, consider a transactional outbox.
- For multi-step, long-running workflows or external systems, consider Saga with compensation and a durable state machine.
- If reservation/confirm/cancel semantics can be designed, TCC may fit, provided every step is idempotent and handles repeated calls.
- If Seata semantics are still mandatory, keep Seata on a supported Spring Boot/Cloud version or isolate that service as an independently upgraded workload. Verify database, driver, TC, and client against the same compatibility matrix.

Outbox, Saga, TCC, and Seata AT have distinct consistency models. Switching between them requires changing business design, state tracking, retries, and reconciliation—not merely swapping dependencies in `pom.xml`.

## 8. Creating Application-Standard Client Configuration

After replacing a starter, group settings under your application's own namespace instead of scattering vendor properties everywhere. For example:

```yaml
app:
  storage:
    provider: aliyun-oss
    bucket: ${OSS_BUCKET}
    region: ${OSS_REGION}
    endpoint: ${OSS_ENDPOINT}
  messaging:
    provider: rocketmq
    topic-order-created: ${ORDER_CREATED_TOPIC}
    consumer-group: ${ORDER_CONSUMER_GROUP}
```

These properties are an internal contract, not properties automatically understood by Spring or Alibaba Cloud. The application's `@ConfigurationProperties` class should validate values, construct client beans, and fail fast if endpoints/credentials are missing. Never put secrets in ordinary config namespaces; reference runtime secrets only.

Example configuration structure:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.storage")
public record StorageProperties(
    @NotBlank String provider,
    @NotBlank String bucket,
    @NotBlank String region,
    @NotBlank String endpoint
) {}
```

Register properties using the mechanism appropriate for your Spring Boot version, such as `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`. If the project still uses an older Spring Boot with `javax.validation`, do not blindly copy the `jakarta.validation` import from this example; match the namespace of your current Java/Spring generation.

## 9. Controlled Migration Process

A starter replacement should proceed one capability at a time, deployed independently where architecture permits.

### Step 1: Build an Inventory

Document starters, auto-configured beans, annotations, properties, transitive SDKs, and dependent business flows. Use the dependency tree, Spring Boot's condition evaluation report (`--debug`), and startup logs to identify which beans are created.

### Step 2: Define Contracts and Baselines

Specify observable behavior before changing anything: requests/responses, event schemas, transaction boundaries, timeouts, retries, ordering, serialization, error mapping, and metrics. Create integration tests for critical paths. This baseline catches regressions where a replacement silently drops a feature.

### Step 3: Choose an Approach and Verify Licensing/Support

Check official compatibility matrices, Java baselines, release cadences, licenses, and maintenance status. Assign ownership for upgrading client SDKs, patching CVEs, tracking breaking changes, and operating endpoints. For managed services, confirm your region/edition supports the required features and protocols.

### Step 4: Isolate Dependencies

Create a dedicated adapter or Spring configuration for that capability. Keep controllers and domain code from depending directly on vendor SDKs. Keep contracts stable and move endpoints, timeouts, credentials, and pools into runtime configuration.

### Step 5: Replace Dependencies and Clean Up Legacy Ones

Remove the old starter once the new implementation completely replaces it. Never leave two competing auto-configurations creating duplicate beans. Use a supported BOM to manage versions; verify dependency convergence and avoid arbitrary transitive overrides.

### Step 6: Multi-Layer Testing

- Unit tests for adapters and error mapping.
- Context tests verifying Spring creates the expected beans and binds properties properly.
- Integration tests against test services or Testcontainers where appropriate.
- Contract tests for message schemas and inter-service APIs.
- Failure tests: timeouts, network drops, invalid credentials, unavailable brokers, duplicate messages, config refreshes, consumer restarts, and transaction rollbacks.
- Security tests: least privilege, TLS validation, zero secrets in logs, and denial of out-of-scope resource access.

### Step 7: Canary Rollout and Observation

Deploy first to one instance group or a low-risk service. Compare error rates, latency, connection counts, message lag, retries, and business outcomes before and after. Retain artifact/config rollback readiness in case the new adapter misbehaves. Never run two consumers in the same group or two publishers concurrently without understanding duplicate/ordering effects.

### Step 8: Remove Legacy Paths After Verification

Once the new path is stable, remove old properties, beans, dependencies, and legacy adapter code. Run a final dependency tree check to confirm the old starter is no longer pulled in transitively. Update runbooks, dashboards, and local development guides.

## 10. Example Post-Migration Dependency and Configuration Check

With Maven, the Spring Boot BOM should manage Spring Boot starter versions. The Spring Cloud BOM and Spring Cloud Alibaba BOM must be chosen per the official compatibility matrix; never pick an arbitrary BOM solely to force one artifact to a newer version.

Illustrative POM structure:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>${spring-boot.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
        <!-- Import Spring Cloud / Spring Cloud Alibaba BOM only when
             the versions are verified compatible with the Boot version above. -->
    </dependencies>
</dependencyManagement>
```

In real projects, the Spring Boot parent or existing dependency management may already import the Boot BOM; avoid redundant duplicate imports. Centralize version properties in one deliberate place and use Maven Enforcer/dependency convergence to catch version conflicts.

After replacing dependencies, verify:

```bash
mvn -q clean verify
mvn -q dependency:tree -Dverbose
```

Run the application with `--debug` in a test environment if you need to inspect the condition evaluation report. Verify there are no unexpected competing `DataSource`, `RedisConnectionFactory`, `ObjectMapper`, producer, or consumer beans. For Spring Boot 3+, scan libraries still referencing `javax.*` and verify Jakarta compatibility across integrations.

## 11. Common Errors When Replacing Starters

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `NoSuchMethodError` after startup | Client SDK and starter use mismatched API versions | Inspect dependency tree, eliminate version conflicts, and align BOM/release train |
| `ClassNotFoundException` or `NoClassDefFoundError` | Dependency excluded or API moved packages | Identify the artifact providing the class, check Java/Jakarta namespaces, and inspect runtime classpath |
| Spring stops creating expected beans | Old auto-configuration was removed or conditions no longer match | Declare beans/configuration explicitly or use a standard starter; inspect the condition report |
| Old properties stop taking effect | Prefix/property names or bootstrap mechanism changed | Check migration guides and test binding with `@ConfigurationProperties` |
| Nacos config fails to refresh | New adapter only reads config at startup or listener is unregistered | Design refresh explicitly; refresh only beans safe for runtime reconfiguration |
| Redis connects, but commands fail auth | Username/password handling changed across account types/clients | Check account type and configure separate fields properly |
| Messages sent or processed twice | Ambiguous producer timeout or non-idempotent consumer | Event IDs, idempotency keys, outbox, and bounded retries |
| Circuit breaker behaves differently from Sentinel | Partial replacement with an implementation that has different semantics | Map rules carefully, add rate limits/hotspot guards at the right layer, and load-test |
| Global transaction hangs or rolls back partially | Client/TC/database are not a supported combination or boundary changed | Check mode, datasource proxy, TC, undo logs, and recovery; never force incompatible versions together |

## 12. Pre-Release Checklist

- [ ] Verified Spring Boot, Spring Cloud, Spring Cloud Alibaba, Java, and SDK versions against compatibility docs.
- [ ] Identified every capability provided by the legacy starter and behaviors to preserve.
- [ ] Selected standard abstractions, official SDKs, or appropriate adapters for each capability.
- [ ] Eliminated dependency conflicts, duplicate auto-configurations, and competing beans.
- [ ] Configured endpoints, credentials, TLS, timeouts, and retries via runtime config/secret stores.
- [ ] Enforced least privilege on IAM/RAM roles and ACLs.
- [ ] Added integration tests for relevant data, messaging, discovery/config, or transaction flows.
- [ ] Tested timeouts, duplicates, restarts, retries, rollbacks, and disconnects.
- [ ] Updated metrics, logs, tracing, dashboards, and runbooks for the new implementation.
- [ ] Prepared a canary/rollback plan with clear rollout stop criteria.
- [ ] Removed legacy starters/properties/code after confirming full replacement.

## 13. Conclusion

When a legacy starter has no compatible version, replace it according to the capability it provides. Spring Boot Data fits RDS and Redis; official SDKs fit specialized APIs like OSS; the RocketMQ client can be wrapped in an adapter when the binder is incompatible; and Nacos, Sentinel, and Seata require careful semantic evaluation before switching solutions. Compatibility matrices, dependency trees, contract tests, and observable rollouts keep upgrades controlled. The objective is keeping business contracts stable while drawing clear boundaries around provider dependencies.

## References

- [Spring Boot Reference Documentation](https://docs.spring.io/spring-boot/reference/): dependency management, auto-configuration, data access, configuration properties, and Actuator.
- [Spring Cloud Reference](https://docs.spring.io/spring-cloud/docs/current/reference/html/): Spring Cloud Commons, LoadBalancer, CircuitBreaker, and integration abstractions.
- [Spring Cloud Alibaba Documentation](https://sca.aliyun.com/en/docs/): release trains, compatibility, and version-specific integration guides.
- [Alibaba Cloud SDK for Java](https://www.alibabacloud.com/help/en/sdk/developer-reference/java): SDK selection, credentials, and calling Alibaba Cloud service APIs.
- [Alibaba Cloud OSS SDK Documentation](https://www.alibabacloud.com/help/en/oss/developer-reference/overview-14): Object Storage Service SDK and APIs.
- [Apache RocketMQ Documentation](https://rocketmq.apache.org/docs/): Java client, producers, consumers, retries, and transaction messages.
- [Seata Documentation](https://seata.apache.org/docs/): Seata transaction modes, architecture, and compatibility.
- [Sentinel Documentation](https://sentinelguard.io/en-us/docs/introduction.html): flow control, circuit breaking, and rule management.
