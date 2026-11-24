# Reviewing Version Changes Across Clients, Drivers, Brokers, and Spring Data

A Spring Boot application can compile cleanly after a dependency upgrade and still fail in live environments: the Redis client connects yet cannot read cached data from the previous release, the JDBC driver changes its authentication mechanism or returned column types, a Kafka consumer fetches records yet cannot decode payloads, or Spring Data changes query derivation. Conversely, a broker may be upgraded independently of the application, exposing old assumptions about protocol negotiation, ACK semantics, timeouts, or metadata.

Therefore, **reviewing version changes** requires evaluating source code, dependency graphs, wire protocols, stored data, in-flight state, deployment rollouts, and rollback paths together. This topic sits in the **Troubleshooting and Upgrades** chapter of **SPRING_BOOT_INTEGRATION**: organizing Spring Boot integration flows across HTTP clients, databases, caches, brokers, and Spring Integration adapters with focus on configuration, data contracts, transactions, failures, deduplication, testing, and observability.

## 1. Learning Objectives

After this lesson, learners will be able to:

1. Map the versions of Spring Boot, Spring Framework, Spring Data, Spring Integration, client libraries, drivers, databases, and message brokers in a service.
2. Distinguish **binary compatibility**, **API compatibility**, **protocol compatibility**, **data-format compatibility**, and **operational behavior compatibility**.
3. Inspect dependency graphs and release notes for your exact versions, spotting overrides that skew BOM-managed components.
4. Build an **old/new client – old/new server** compatibility matrix, including rolling-deploy windows where old and new apps run side by side.
5. Design contract, integration, failover, and rollback tests across JDBC, Redis, HTTP, Kafka/RabbitMQ/JMS, and Spring Data.
6. Propose phased upgrade procedures, stop gates, and safe recovery plans for data, schemas, messages/offsets, and caches.

## 2. Upgrading Versions Means Changing a Dependency Graph

In an integration application, there is rarely a single "Redis version" or "Kafka version." Every connection spans at least the application, client library, wire protocol, and remote server—plus serialization, TLS, schemas, and Spring Data/Spring Integration layers.

~~~mermaid
flowchart TD
    APP["Spring Boot application"] --> BOM["Boot-managed dependency set / BOM"]
    BOM --> SD["Spring Data + Spring Data store modules"]
    BOM --> SI["Spring Integration adapters"]
    BOM --> HTTP["HTTP client / Reactor Netty / HttpClient"]
    BOM --> JDBC["JDBC driver / Hibernate / connection pool"]
    BOM --> MSG["Kafka / AMQP / JMS client"]
    SD --> REDIS["Redis client: Lettuce / Jedis"]
    SD --> ORM["JPA / JDBC / repository abstraction"]
    JDBC --> DB[("Database server")]
    REDIS --> RS[("Redis server / Sentinel / Cluster")]
    MSG --> BROKER[("Message broker + topic/queue")]
    HTTP --> API["External HTTP service"]
    SI --> DB
    SI --> BROKER
    SI --> API
~~~

Upgrading one dependency ripples through many others. Even a Spring Boot minor release routinely bumps managed versions of Spring Data, Hibernate, drivers, Micrometer, Reactor, and clients. If an app overrides one child library manually, it can run an untested combination even though every individual jar is "the latest."

### 2.1. Six Compatibility Layers

| Layer | Question to Answer | Failure Example |
|---|---|---|
| **Compile / API** | Does source code still match classes, methods, annotations, and properties? | Package moved from `javax` to `jakarta`; method removed |
| **Binary / runtime** | Do loaded runtime jars match the APIs compiled against? | `NoSuchMethodError`, `NoClassDefFoundError`, `LinkageError` |
| **Protocol / connectivity** | Does the new client negotiate protocol, TLS, SASL, ACLs, and auth with the current server? | Handshake failure, unsupported protocol, auth refused |
| **Stored data / payloads** | Can the new version read historical data, and can old versions read new writes? | JSON type metadata shifted; Avro schema incompatible |
| **Processing semantics** | Did transactions, ACKs, retries, timeouts, ordering, commit/rollback, or dedup change? | Duplicate transactions; consumer committing offsets prematurely |
| **Operational behavior** | Do metrics, health probes, topology discovery, deployment, startup, and rollback stay valid? | Readiness fails post-client upgrade; slow failovers |

**Technical conclusion:** "a green build" checks only parts of the first two layers; you must test against real servers and pre-existing data to verify the remaining layers.

## 3. First Step: Build a Version and Integration Inventory

Before upgrading, record an inventory from the **live running environment**, not solely from build files in source control.

| Component | What to Capture | Evidence Source |
|---|---|---|
| Java / runtime | Actual Java version, vendor, JDK/JRE flags | Runtime logs, image digests, deployment manifests |
| Spring Boot / Framework | Plugin version, BOM, resolved dependencies, active profiles | Build files, dependency tree, startup info |
| Spring Data | Release train and JPA, JDBC, Redis, Mongo modules if present | Effective `runtimeClasspath` |
| Spring Integration | Core + HTTP/JDBC/Kafka/AMQP/SFTP/JMS adapters | Dependency tree and bean configurations |
| HTTP client | `RestClient`/`RestTemplate`/`WebClient`, Apache HttpClient/Reactor Netty, TLS config | Client beans, dependency graph |
| DB driver | JDBC driver, connection pool, Hibernate dialect, DB server version | Resolved dependencies, JDBC metadata, DB query |
| Redis | Lettuce/Jedis, server, Sentinel/Cluster topology, serializers | Client config, `INFO`, startup logs |
| Broker | Kafka/RabbitMQ/JMS client, broker, wire protocol, group/queue settings | Broker admin API, config, client logs |
| Serialization | Jackson/Avro/Protobuf, schema registry, content types, header conventions | Contract tests, message fixtures |
| Infrastructure | Container images, TLS certificates, proxies, service mesh, DNS | Deployment and runtime configs |

Never include tokens, passwords, private keys, connection strings with secrets, or customer data in version reports. Use normalized identifiers, environment names, and commit/image digests for comparison.

### 3.1. Document Who Owns Each Version

- **Managed by Boot / BOM:** prefer omitting explicit versions on starters and BOM-managed dependencies unless documented.
- **Intentional overrides:** record the module, overridden version, reason, compatibility evidence, and planned removal date.
- **Transitive dependencies:** external SDKs can still pull unexpected versions onto the classpath.
- **Independent infrastructure:** databases or brokers managed by platform teams follow separate upgrade schedules; reading app Git history alone misses half the picture.

When multiple microservices share a topic or database schema, inventory **all sibling clients**, not just the service currently upgrading.

## 4. Inspecting Dependency Graphs and Managing BOMs

With Gradle, inspect resolved versions before changing anything:

~~~bash
# Example Gradle commands run in the target project during an upgrade.
./gradlew dependencies --configuration runtimeClasspath

./gradlew dependencyInsight \
  --configuration runtimeClasspath \
  --dependency spring-data-redis

./gradlew dependencyInsight \
  --configuration runtimeClasspath \
  --dependency kafka-clients

./gradlew dependencyInsight \
  --configuration runtimeClasspath \
  --dependency postgresql
~~~

With Maven:

~~~bash
./mvnw dependency:tree
./mvnw help:effective-pom
~~~

Look specifically for:

- Are **two dependency paths** pulling different versions of the same artifact?
- Which version won at runtime and why (BOM, constraint, override, nearest definition)?
- Did an unrelated SDK drag in an obsolete client causing duplicate classes or stale APIs?
- Was one **Spring Data module** bumped independently while Spring Framework or Spring Data Commons stayed on another release train?
- Are conflicting logging, JSON, Netty, Jackson, SSL provider, or `jakarta`/`javax` artifacts present?

Archive resolved dependency logs **before** and **after** changes. Compare what actually lands on `runtimeClasspath`, not just what build scripts declare.

### 4.1. Keep Related Dependencies Aligned on One Version Train

In Spring Boot, starters and dependency management provide tested, aligned versions. A build file letting the BOM govern versions looks like:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '<spring-boot-version>'
    id 'io.spring.dependency-management' version '<dependency-management-plugin-version>'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    implementation 'org.springframework.kafka:spring-kafka'
    implementation 'org.springframework.integration:spring-integration-core'
    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

This illustrates Gradle structure using **placeholders** for versions, not a copy-pasteable build script. Follow your chosen Spring Boot Gradle plugin and dependency-management guide; many projects import Boot's BOM via Gradle `platform(...)` without the `dependency-management` plugin.

**Never bump Spring Data Commons alone** just to "get the latest" without checking the entire Spring Data release train and store modules. When overriding a dependency for a CVE, audit impacted APIs/behaviors, run full tests, and document the override so it is not forgotten.

### 4.2. Reading Startup Failures Post-Upgrade

Startup errors provide high-signal clues:

| Symptom | Investigation Direction |
|---|---|
| `NoSuchMethodError` | Runtime jar version differs from compile-time version; run `dependencyInsight` |
| `ClassNotFoundException` / `NoClassDefFoundError` | Missing dependency, relocated package, or binary conflict |
| `BeanCreationException` | Removed/renamed property, altered bean config, missing driver/health dependency |
| `UnsatisfiedDependencyException` | Auto-configuration conditions changed or component no longer registered |
| `UnsupportedClassVersionError` | Bytecode compiled for a newer Java version than runtime |
| `ClassCastException` during deserialization | Serializer/type metadata or class package name changed |
| Authentication / SSL handshake failure | TLS/cipher/cert/credential/protocol or server security policy changed |

Never silence symptoms by disabling auto-configurations or deleting health checks. Find the first root cause in the exception chain, verify which dependency actually loaded, and build a minimal reproduction.

## 5. Release Notes and Compatibility Matrices: Check Both Directions

Upgrades roll out in one of two orders:

- **Upgrade clients first:** new app talks to old server/broker.
- **Upgrade servers first:** old app talks to new server/broker.

Both directions must be verified because rolling deployments leave **old and new clients coexisting**.

| Matrix | Old Server / Broker | New Server / Broker |
|---|---|---|
| **Old Client** | Working baseline | Must test when upgrading infrastructure first |
| **New Client** | Must test when upgrading applications first | Final post-upgrade target state |

Expand this matrix across **old/new producers, old/new consumers, and old/new payload schemas**, since a broker upgrade can succeed while passing payloads older services fail to parse.

### 5.1. Which Documents to Read

For every changed component pair:

1. **System requirements** and **supported versions** for the exact target release.
2. **Migration / upgrade guides** from source version to target version, including intermediate hops.
3. **Release notes / changelogs**, breaking changes, deprecations, and security advisories.
4. Server/broker **protocol & compatibility** docs covering wire formats and client auth.
5. Changes to **default configuration**: timeouts, retries, serializers, pooling, auto-creation, consumer ACKs, TLS, and metrics.
6. **Rollback / rolling-upgrade** procedures and irreversible cutoffs, particularly around persisted formats or broker feature levels.

Never assume every new major client works with every old major server. Compatibility guarantees differ across Kafka, PostgreSQL, Redis, RabbitMQ, and drivers. **Confirm supported combinations in official release matrices before deploying**; examples in this lesson never substitute for vendor support matrices.

## 6. Reviewing Spring Boot, Spring Framework, Spring Data, and Spring Integration

A Spring Boot bump propagates API and implementation shifts across sibling framework layers.

### 6.1. Spring Data Repositories and Query Semantics

Check:

- **Derived repository methods:** method names, property/association traversal, sorting, pagination, null handling.
- **Custom queries:** JPQL/native SQL, named parameters, projections, constructor expressions, query validation.
- **Transactions:** `readOnly`, propagation, isolation, lazy loading, flush/commit timing changes.
- **Data conversions:** enum mapping, UUIDs, `Instant`/`LocalDateTime`, numeric precision/scale, custom converters.
- **Optimistic locking:** `@Version` behavior on stale updates.
- **JPA provider:** Spring Data JPA typically pairs with Hibernate; Hibernate/dialect bumps can alter generated SQL without changing repository code.
- **Schema migrations:** Flyway/Liquibase execution ordering relative to context startup.

**Critical test focus:** verify **database state and transaction effects**, not merely that repository methods were invoked. A derived query changing parameter binding can return different rows without throwing any exception.

### 6.2. Spring Data Redis and Lettuce / Jedis

Changes in Spring Data Redis or Redis clients can impact:

- Key/value/hash serializers, Java type metadata, or JSON polymorphism.
- Command return types, pipelined transactions, and conversions.
- Timeouts, reconnects, connection pooling, Sentinel/Cluster topology refresh.
- Redis protocol (RESP), ACL/TLS, cluster advertised hostnames, `MOVED`/`ASK` redirection.
- Redis cache TTLs, prefixes, key naming, and invalidation.

If caches store **JDK serialization** or class names, moving packages or classes breaks reading legacy entries. When Redis holds **sessions, locks, idempotency markers, or critical state**, flushing Redis cannot be your default upgrade plan.

### 6.3. Spring Integration Adapters

Across HTTP, JDBC, Kafka, AMQP, JMS, Redis, SFTP, and file inbound adapters:

- Check bean/DSL APIs and factory signatures in the target release.
- Preserve channel contracts: synchronous `DirectChannel` vs. asynchronous `ExecutorChannel`.
- Verify **pollers**, scheduling, `maxMessagesPerPoll`, timeouts, and `errorChannel`.
- Check transaction advice, ACK boundaries, retries, and dead-letter/recoverers.
- Confirm headers, payload conversion, charset/content-type, and correlation IDs stay intact.
- For **idempotent receivers** or metadata stores, verify state formats, keys, and TTL compatibility.

A new adapter that receives messages cleanly while shifting ACK timing introduces silent data-loss or duplicate risks that happy-path tests miss.

### 6.4. Java Runtime and Jakarta Namespace

Across major Spring Boot/Framework boundaries, verify Java runtime minimums, third-party libraries, and Servlet/JPA/JMS **`javax.*` vs. `jakarta.*`** namespaces. Spring Boot 3 uses modern Jakarta EE APIs; legacy code or SDKs tied to `javax` EE packages require migration.

Never find-and-replace every **`javax.*`** to **`jakarta.*`** blindly: Java SE packages like **`javax.net`** remain valid. Migrate only APIs listed in the official namespace migration guides.

## 7. JDBC Drivers and Databases: Check Transactions, Types, and TLS

JDBC drivers translate Java SQL and connection calls into database wire protocols. Driver bumps can alter runtime behavior without touching entities or repositories.

| Area | What to Test | Common Regressions |
|---|---|---|
| **Connectivity** | JDBC URLs, DNS, socket timeouts, TLS, auth mechanisms | Works locally, fails TLS/auth in production |
| **Pooling** | Validation queries, `maxLifetime`/`idleTimeout`, leak detection, driver socket timeouts | Pool exhaustion, hung threads, flaky reconnects |
| **Data types** | UUID, JSON/JSONB, timezones, timestamps, decimal precision, enums, `bytea` | Time skew, precision loss, mapping errors |
| **SQL behavior** | Prepared statements, batch inserts, generated keys, fetch size, cursors | Duplicate keys, memory spikes, query regressions |
| **Transactions** | Isolation, autocommit, savepoints, rollbacks, commit timeouts | Wrong retries or uncertain commit outcomes |
| **Metadata / schema** | Dialects, SQL generation, migration order, identifier quoting | Generated queries incompatible with schema |
| **Observability** | Error codes, SQLStates, exception translation, metrics | Retry classifiers misclassify driver faults |

### 7.1. Exception Classification May Need Updating

Spring translates driver failures into `DataAccessException` subclasses, yet exact mappings from SQLStates/vendor codes and retryability must be re-verified after upgrades.

For example:

- **Deadlocks / lock timeouts** may be safely retried in idempotent transactions.
- **Unique constraint violations** may signal expected business duplicates or true conflicts—never retry blindly.
- **Connection reset during `COMMIT`** leaves an uncertain outcome; never assume the transaction rolled back.
- **Auth failures** and **missing columns** are permanent configuration/schema errors; never retry in loops.

Maintain unit/integration tests covering exception translation for every failure mode your app handles. Never assume identical exception class names mean underlying SQLStates or causes stayed unchanged.

### 7.2. Schemas Must Stay Compatible During Rolling Deploys

When old and new app instances share a database during rollout, migrate via **expand → migrate → contract**:

~~~mermaid
flowchart LR
    A["1. Expand: add backward-compatible columns/tables/constraints"] --> B["2. Deploy app supporting old + new schemas"]
    B --> C["3. Controlled backfill / data migration"]
    C --> D["4. Switch reads/writes to new schema"]
    D --> E["5. Verify zero legacy clients remain"]
    E --> F["6. Contract: drop legacy structures in a later release"]
~~~

Never alter types or drop columns still read or written by the previous release if rollback safety matters. Backfill and validate existing rows before enforcing new constraints. On large tables, assess table locks, migration duration, index builds, and latency impacts—driver upgrades never erase schema risks.

## 8. HTTP Clients: From Outbound Requests to Lost Responses

Upgrading `RestTemplate`, `RestClient`, `WebClient`, Apache HttpClient, Reactor Netty, or HTTP SDKs can shift:

- Default connect/read/response timeouts and overall deadlines.
- Redirect handling, proxy resolution, TLS truststores, hostname checks, DNS caching.
- Connection pooling, keep-alive, idle eviction, HTTP/1.1 vs. HTTP/2 negotiation.
- JSON serialization, charsets, compression, content negotiation.
- Mapping HTTP 4xx/5xx/429 responses to exceptions and retry triggers.
- Header propagation: `Authorization`, `Idempotency-Key`, `traceparent`, correlation IDs.
- Built-in SDK or load-balancer retries stacking on top of application retries.

**A timeout does not mean the server failed.** If a side-effecting HTTP POST times out after the server committed, query status by request ID or supply idempotency keys before retrying. Client upgrades sometimes shift timeout rates, exposing duplicate bugs even when business logic didn't change.

### 8.1. HTTP Contracts to Preserve

| Check | What to Verify |
|---|---|
| URL, method, query | Unchanged path encoding, query params, and redirect rules |
| Headers | `Authorization`, `Content-Type`, idempotency keys, correlation IDs |
| Payloads | JSON field names, nulls/defaults, numeric precision, enums, dates/times |
| Response mapping | 2xx/4xx/5xx status handling, bodies, error mapping |
| Timeouts / retries | Total attempts hitting server, backoff, deadlines, retry safety |
| TLS / proxies | Hostname verification, cert trust, proxies, DNS in live-like infra |
| Streaming | Large bodies streamed safely without OOM; streams closed on error |

Use HTTP stubs (WireMock/MockWebServer) for request-contract checks, plus at least one real/fault-injected transport test covering timeouts, retries, and connection reuse.

## 9. Redis Servers and Clients: Data Compatibility and Failover

Teams often treat Redis as "disposable cache." That holds only for non-critical recomputable caches where cold-cache fallback load is acceptable. Redis frequently stores sessions, distributed locks, rate limiters, idempotency markers, or Redis Streams.

### 9.1. Questions When Upgrading Redis / Lettuce / Jedis

1. Does the new client connect to the **current server** with TLS, ACLs, RESP, and cluster settings?
2. Does the old client connect cleanly to the **new server** during rolling upgrades?
3. Can the new serializer decode existing keys/values/hashes—and can the old app read data written by the new app?
4. Did key prefixes, TTLs, cache names, session IDs, lock tokens, or idempotency markers shift?
5. During Sentinel/Cluster failovers, does the client refresh primary/slot topology and handle redirections properly?
6. For Redis Streams, do consumer groups, pending entries, ACKs, replays, and retention match contracts?

### 9.2. Testing Against Historical Bytes Written by the Old Release

A **wire-format compatibility test** reads fixture bytes produced by the previous serializer and committed in test resources:

~~~java
// Conceptual example: read legacy bytes saved in test resources.
@Test
void newSerializerCanReadLegacyValue() throws Exception {
    byte[] legacyBytes;
    try (var stream = getClass().getResourceAsStream(
            "/contracts/redis/order-v1.bin")) {
        assertThat(stream).isNotNull();
        legacyBytes = stream.readAllBytes();
    }

    Object decoded = redisTemplate.getValueSerializer()
            .deserialize(legacyBytes);

    assertThat(decoded).isInstanceOf(OrderSnapshot.class);
    assertThat(((OrderSnapshot) decoded).status()).isEqualTo("PAID");
}
~~~

This is an **illustrative snippet**: `redisTemplate`, `OrderSnapshot`, AssertJ, and binary fixtures must be implemented in your project. Never generate fixtures using the new serializer to test legacy compatibility—that proves nothing about reading old data.

For recomputable caches, migrating to a new prefix/namespace with warm-up avoids cross-version collisions. For sessions, idempotency keys, and locks, plan explicit format migration so coexisting old and new instances agree on state.

### 9.3. Failovers and Timeouts

In Redis Cluster, clients must refresh topologies and follow redirections. In Redis Sentinel, clients must discover the new primary; commands issued mid-failover can time out. Never treat automatic retries as safe for `INCR`, `LPUSH`, `XADD`, or lock acquisitions: commands may execute even when the response drops.

**Post-upgrade tests** should simulate disconnects and failovers in matching topologies, measuring recovery times, timeout counts, and legacy data reads. A single standalone Redis container cannot validate Sentinel or Cluster failover when production runs clustered.

## 10. Kafka: Client–Broker Compatibility, Schemas, and Consumer Groups

Upgrading Kafka clients or brokers affects protocol negotiation, security, producer delivery, consumer group assignment, offsets, and transactions/idempotency. Kafka defines release-specific client/broker compatibility rules—**never guess compatibility solely from version numbers**.

| Area | What to Verify |
|---|---|
| **Client ↔ broker** | Version support, API version negotiation, SASL/TLS, advertised endpoints, ACLs |
| **Producer** | Acks, retries, idempotence, `max.in.flight`, batching, compression, transactional IDs |
| **Consumer** | Group protocol/assignment, rebalances, `max.poll.interval`, auto/manual commit, offset resets |
| **Schemas** | Avro/Protobuf/JSON Schema compatibility, schema registry, nullability, enum evolution |
| **Kafka Streams / TX** | Changelogs/state stores, application IDs, transaction state and recovery |
| **Operations** | Topic config, retention, compaction, metadata/feature levels, rolling broker upgrades/rollbacks |
| **Spring Kafka** | Listener containers, error handlers, recoverers/DLT, ACK modes, message converters |

### 10.1. New Producers and Old Consumers Must Coexist

During rolling deploys:

- New producers emit payloads with new fields while old consumers must still decode them.
- New consumers drain days-old backlog written by old producers; new decoders must read old shapes.
- New consumer instances join the same group as old instances, potentially triggering rebalances or partition shifts.
- Messages sitting in retry/DLT topics carry headers from the old version; new listeners must handle or isolate them.

**Testing only new producer → new consumer is insufficient.** Test both cross-version directions and keep a topic populated with historical messages for replay drills.

### 10.2. Offsets and ACKs Must Never Be Overlooked

If an upgrade or refactor alters ACK modes, committing offsets **before DB side effects commit** loses messages on crashes. Committing offsets after DB commits causes redeliveries if ACKs drop, requiring idempotent consumers.

Test scenario:

~~~mermaid
sequenceDiagram
    participant K as Kafka Broker
    participant C as Spring Kafka Consumer
    participant D as Business DB
    K->>C: Deliver event E
    C->>D: Persist business effect
    D-->>C: Commit OK
    C--xK: Offset commit lost / process crash
    K->>C: Redeliver event E
    C->>D: Apply with unique eventId
    D-->>C: Already processed, no duplicate effect
    C->>K: Commit offset
~~~

Kafka transactions and exactly-once processing have strictly defined scopes inside Kafka. Never treat Kafka transactions as atomic across external databases. Across DB boundaries, rely on unique keys, inbox/outbox, and idempotency to guarantee business correctness.

### 10.3. Broker Upgrades Have Their Own Playbooks

For Kafka clusters, follow exact release procedures for rolling restarts, quorum/controllers, metadata/feature levels, and downgrade cutoffs. Advancing metadata/feature levels can block downgrades even if older binaries still start. Never upgrade brokers and flip new cluster features simultaneously without verified backups and recovery plans.

Measure at least consumer lag, rebalance counts/durations, produce/consume errors, throughput, p95/p99 latency, under-replicated partitions, and DLT rates before, during, and after upgrades.

## 11. RabbitMQ, AMQP, JMS, and Other Brokers

For RabbitMQ or JMS brokers, verify **client libraries, Spring adapters, broker servers, wire protocols**, and **topology** separately.

### 11.1. RabbitMQ / AMQP

- Check Java client, Spring AMQP, Spring Integration AMQP adapter, and RabbitMQ server compatibility matrices.
- Audit **queue/exchange/binding declarations**, arguments, durability, TTLs, dead-lettering, and quorum vs. classic queue behavior.
- Verify **prefetch**, manual/auto ACKs, publisher confirms, returns, retries/requeues, and consumer concurrency.
- Inspect disconnect recovery, heartbeats, connection/channel limits, and broker alarms.
- Test publish timeouts after broker acceptance—never retry assuming the message wasn't queued.
- Maintain cross-version compatibility between old/new producers and consumers.

A common failure is **`PRECONDITION_FAILED`** when a new app declares an existing queue with modified arguments. That is a topology/contract change, not a transient error to retry forever.

### 11.2. JMS and Providers

In JMS upgrades, besides broker compatibility, watch for **`javax.jms` to `jakarta.jms`** shifts across framework stacks. Verify provider client drivers, listener containers, session transactions, acknowledgements, redelivery policies, and DLQs. Never assume bumping an API dependency upgrades the underlying provider driver's namespace automatically.

Also test session recovery after failovers: messages delivered without ACKs redeliver, so handlers must be idempotent.

## 12. Payloads and Schemas: Data Compatibility Beats Version Strings

Many post-upgrade outages originate not from wire protocols, but from altered message/record formats colliding with millions of persisted records.

### 12.1. Format Read–Write Matrix

| Writer | Reader | What to Check |
|---|---|---|
| **Old producer** | **New consumer** | New consumer decodes backlog, nulls/enums/defaults, and legacy schemas |
| **New producer** | **Old consumer** | Old consumer ignores new fields safely or rejects cleanly per contract |
| **Old cache writer** | **New cache reader** | Serialization, key prefixes, value types, TTLs |
| **New cache writer** | **Old cache reader** | Rollback binaries can still read state written by the new release |
| **Old DB writer** | **New DB reader** | New schema mappings read legacy rows cleanly |
| **New DB writer** | **Old DB reader** | Rolling deployments and rollbacks survive new columns/enums |

Define **backward compatibility** and **forward compatibility** per reader/writer pair. Never assume adding a JSON field is universally safe: strict consumers reject unknown fields, and exhaustive enum switches crash without defaults.

### 12.2. Changes That Routinely Break Contracts

- Renaming JSON fields or changing object nesting.
- Changing **int64** to **string**, or **decimal** to floating-point losing precision.
- Switching timestamps from UTC to local timezones or changing string formats.
- Adding enum values unknown to older consumers.
- Changing `Content-Type` or type headers used by converters.
- Removing required fields or altering semantic meaning under the same field name.
- Changing Redis serializers that embed Java class names.
- Shifting null, empty, default, or version-field policies.

When using a schema registry, verify actual subject/version compatibility settings; a passing registry check still needs consumer contract tests to catch semantic shifts.

### 12.3. Safe Contract Change Procedure

1. Capture fixtures or snapshots from **the legacy release** before upgrading.
2. Test the new reader against legacy fixtures.
3. Test the old reader against data written by the new writer whenever overlap or rollback exists.
4. Roll out parallel compatibility in writers (dual-read/dual-write only when controlled and justified).
5. Run checkpointed, idempotent backfills and verify counts/reconciliation.
6. Remove old schema/fields only after zero old consumers or legacy replay needs remain.

## 13. Configuration and Default Behavior: The Easy-to-Miss Layer

Version bumps can keep class names and APIs intact while silently changing **default values**. Always diff **effective configuration** before and after, not just keys explicitly listed in `application.yml`.

| Category | What Can Shift | Test Scenario |
|---|---|---|
| Timeouts | Connect, socket, command, request, idle | Dependency runs 2–5× slower than baseline |
| Retries | Attempts, backoff, jitter, exception matching | HTTP 429/503, DB deadlocks, post-side-effect timeouts |
| Pools | Min/max idle, max lifetime, queues | Load spikes; dependency drops then recovers |
| Serialization | Jackson naming/typing, date/time formats | Round-trips and legacy-version fixture decoding |
| Error handling | Exception mapping, DLQ, recoverers | Corrupt records, poison messages, failed ACKs |
| Health / readiness | Which dependencies are mandatory | Optional Redis cache down while DB stays healthy; required broker down |
| TLS / auth | Protocols/ciphers, CAs, credentials | Certificate rollovers, ACL denials, SASL failures |
| Metrics / tracing | Meter names, tags, trace propagation | Dashboards and alerts still trigger on failures |
| Schedulers / consumers | Thread counts, prefetch, poll intervals, rebalances | Under load and during rolling deploys |

With Spring Boot Actuator, align health/readiness probes with **actual business serviceability**. Never configure pod-restart loops triggered when an optional cache temporarily drops.

## 14. Layered Upgrade Testing

Scale test realism and cost progressively:

~~~mermaid
flowchart TD
    A["Dependency diff + compile + static checks"] --> B["Unit tests: mapping, validators, exception classification"]
    B --> C["Contract tests: old/new payloads, SQL, HTTP"]
    C --> D["Integration tests against matching DB/Redis/broker versions"]
    D --> E["Failure tests: timeouts, failovers, retries, restarts"]
    E --> F["Staging shadow/canary + SLO measurement"]
    F --> G["Monitored rollout + rollback gates"]
~~~

### 14.1. Minimum Compatibility Test Matrix

| Scenario | Test | Evidence to Collect |
|---|---|---|
| New client → old server | Connect + read/write + fault paths | Protocol, TLS, latency, correctness |
| Old client → new server | Connect + critical operations | Infrastructure upgrade won't break existing apps |
| Old producer → new consumer | Replay historical messages | Payload decode and DB outcome match |
| New producer → old consumer | Emit new schema during overlap | Old consumer handles or rejects predictably |
| New DB schema → old app | Read/write during expand window | Binary rollback remains functional |
| Old cache → new app | Read real snapshotted keys/values | TTL/type/serializer compatibility |
| New app → old cache on rollback | Run old version over new-written state | Zero crashes, zero lost sessions/state |
| Broker / client failover | Disconnect/restart test node | Bounded retries, zero lost/duplicated effects |
| API timeout after commit | Stub drops response post-commit | Idempotency/reconciliation prevents duplicates |
| Heavy batch load | Load, cold caches, multiple partitions | Throughput/lag/p99 within SLOs |

Use **Testcontainers** pinned to exact target DB/Redis/broker versions; remember a single Kafka or standalone Redis container never proves multi-node cluster failover. Network partitions, leader elections, and rolling broker upgrades require cluster topologies.

### 14.2. Assertions That Actually Matter

Kafka/HTTP/DB tests must assert more than "no exception thrown." Verify:

- **Target data reflects exactly one business effect** per event ID/idempotency key across redeliveries and HTTP retries.
- **Transactions roll back** co-transactional resources while external side effects reconcile cleanly.
- **Entity ordering** holds by business key/version across consumer rebalances.
- **Checkpoints / offsets** never advance ahead of durable commits.
- **Legacy cache entries** decode during upgrades, and new entries don't crash rollbacks when shared.
- **Health, metrics, and traces** surface failures like baseline and fire alerts properly.

### 14.3. Differential Testing Across Two Versions

Where feasible, replay identical sanitized inputs against current and candidate versions in isolated environments, comparing:

- Contracted HTTP/JSON responses (normalizing non-deterministic fields like UUIDs/timestamps).
- SQL row counts, unique keys, versions, and transaction outcomes.
- Event payloads, headers, partition keys, ordering, and DLQs.
- Latency percentiles, throughput, thread/connection counts, and memory usage.
- Exception distributions, retry counts, and recovery behavior.

If using **shadow traffic**, disable external side effects or route them to isolated sinks—never replay live payment/order mutations into production.

## 15. Phased Upgrade Plan and Rollback Readiness

Every upgrade needs an **owner, acceptance criteria, stop gates**, and a **verified rollback path**. Changing multiple tightly coupled layers simultaneously obscures root causes.

### 15.1. Phases

1. **Baseline:** capture dependency graph, image digests, SLOs, error rates, p95/p99, consumer lag, DB pools, Redis failover metrics, and duplicate rates.
2. **Change analysis:** review release notes, breaking changes, support matrices, and security advisories; log scope, urgency, deprecations, and risk owners.
3. **Local / CI verification:** upgrade in a branch; run compile, contract tests, and old/new client-server integration suites.
4. **Production-like staging:** test rolling deploys, restarts/reconnects, backlog replays, schema migrations, and rolling back apps over candidate-written data.
5. **Canary:** roll out to a small controlled slice; compare error/latency/lag against baseline on matching traffic.
6. **Progressive rollout:** expand instances/partitions within monitoring capacity while keeping compatible paths intact.
7. **Verification:** confirm zero unintended loss/duplication, healthy alerts/lag/transactions; update docs and runbooks.
8. **Contract cleanup:** remove legacy compatibility code/schemas only after zero old clients remain and rollback no longer needs them.

**Avoid** upgrading the broker, changing payload schemas, and bumping the JDBC driver in one combined rollout unless technically forced and backed by isolated tests and rollback steps.

### 15.2. Acceptance Gates and Stop Criteria

These thresholds are **illustrative examples**—replace them with your service's SLOs:

| Indicator | Example Watch Condition | Decision |
|---|---|---|
| HTTP 5xx / gRPC errors | Significant jump vs. baseline in canary cohort | Halt rollout, investigate |
| p95 / p99 latency | Breaches request budget during evaluation window | Pause/optimize or roll back |
| DB connection pools | Pool exhaustion or sustained wait queues | Reduce traffic to candidate |
| Redis reconnects / timeouts | Sudden spikes or slow failover recovery | Halt client/topology upgrade |
| Consumer lag | Continuous growth with inability to drain | Halt rollout, inspect assignment/throughput |
| Duplicates / unknown results | Duplicate business effects or unresolved states | Pause risky operations, reconcile |
| DLQ / quarantine | Spike tied to new schema | Halt new producer, inspect payloads |

**Rollback is not always redeploying the old image.** If the candidate wrote schemas or payloads incompatible with the old binary, reverting binaries alone worsens outages. Verify rollback compatibility **before** enabling new formats or establish explicit data-recovery steps.

### 15.3. When Servers or Brokers Must Upgrade First

For platform-managed databases or brokers:

- Confirm every active client version is compatible with the target server.
- Follow vendor rolling-upgrade sequences strictly.
- Never advance cluster feature levels or disable legacy protocols until all clients have migrated.
- Protect backups/snapshots and metadata; evaluate downgrade constraints separately.
- Monitor all connected clients, not only the primary service driving the upgrade.

## 16. Post-Upgrade Troubleshooting: Evidence-Based Triage

When failures occur, resist blaming "the new Spring Boot"—trace symptoms to the failing boundary.

### 16.1. Triage Workflow

1. **Capture symptoms:** onset time, canary cohort, request/message IDs, root-cause exceptions, broker/DB logs, active feature flags.
2. **Diff versions:** live binaries and `runtimeClasspath` before/after, image digests, plugins/BOMs, effective configs/defaults, server/broker versions.
3. **Classify layer:** startup/API, protocol/auth/TLS, serializer/schema, query/transaction, ACK/retry, or topology.
4. **Reproduce safely:** replay legacy fixtures, connect to matching server versions, simulate timeouts/failovers, trace side effects by request ID.
5. **Contain blast radius:** use feature flags or canary routing; halt new-format producers if breaking old consumers.
6. **Decide action:** roll back if data contracts remain compatible, hotfix config/mappers, or pause and reconcile uncertain operations.
7. **Confirm recovery:** error rates fall, backlogs drain, zero duplicates/data loss, alerts and traces remain functional.
8. **Document root cause:** capture true cause, missing tests, and update the upgrade checklist.

### 16.2. Symptom → Checkpoint Table

| Post-Upgrade Symptom | Primary Hypothesis | Proof |
|---|---|---|
| Compiles fine, startup `NoSuchMethodError` | Binary incompatibility / dependency override | Effective dependency graph and classpath |
| Fails only on old cached entries | Serializer, type metadata, package rename | Replay snapshotted legacy bytes |
| DB queries much slower | SQL generation, driver fetch size, plan/index | SQL logs, `EXPLAIN`, connection/latency metrics |
| TLS errors after driver/client bump | Ciphers, truststore, hostname, cert chain | Controlled handshake test and server logs |
| Kafka consumers rebalance continuously | Group protocol behavior, poll interval, processing time | Group logs, lag, assignment events |
| DLQ spikes despite healthy broker | Payload/schema/headers/exception converter | Replay pre-upgrade messages |
| Redis Cluster connects to seed yet commands fail | Advertised node addresses, topology refresh, redirections | Network reachability to every node, client logs |
| Duplicates after HTTP retries | Post-commit timeout, changed retry defaults | Server-side request IDs and side-effect counts |
| Health endpoint flips `DOWN` | Readiness indicator/config/defaults changed | Health group config and truly required dependencies |
| Rollback app fails after DB migration | New schema broke backward compatibility | Rollback test against post-migration snapshot |

Prove causes with layer-specific evidence. Never "fix" issues by raising timeouts endlessly, swallowing exceptions, disabling TLS checks, or skipping corrupt data silently.

## 17. Case Study: Upgrading Spring Boot and Kafka Client in an Order Service

A service accepts REST requests, stores **orders** and **outbox** rows in PostgreSQL, publishes **OrderCreated** to Kafka, and another consumer reads events to update a Redis cache. The team upgrades Spring Boot and BOM-managed libraries while keeping the Kafka broker and PostgreSQL server unchanged initially.

~~~mermaid
flowchart LR
    API["HTTP POST /orders"] --> DB[("PostgreSQL: orders + outbox")]
    DB --> OUT["Outbox Publisher"]
    OUT --> K[("Kafka topic orders.events")]
    K --> C["Old and new consumers coexisting"]
    C --> R[("Redis cache")]
    REG["Schema contract fixtures + replay"] -.-> OUT
    REG -.-> C
    MET["Error/lag/duplicates/p99 dashboards"] -.-> DB
    MET -.-> C
~~~

**Pre-identified risks:**

- Spring Data JPA/Hibernate may alter generated SQL or timestamp/UUID mapping.
- JDBC driver or pool defaults may shift connection timeouts and exception translation.
- Kafka client/Spring Kafka may alter default error handlers, ACK behavior, or metrics.
- New producers might emit enum/header formats older consumers cannot parse.
- New Redis serializers/key prefixes could break rollback reads of newly cached entries.

**Test plan:**

1. Export the current dependency graph and review every override.
2. Verify **POST /orders** writes one order row and one outbox event inside one transaction.
3. Feed legacy payload fixtures into the new consumer, and candidate payloads into the old consumer.
4. Simulate producer publish succeeding while ACK drops; verify idempotent event IDs prevent duplicate business effects on retry.
5. Simulate consumer committing DB before offset commit; verify redelivery yields one business effect.
6. Decode legacy Redis key/value byte fixtures; if formats change, deploy a new cache namespace with a rollback plan.
7. Deploy canary monitoring HTTP p99, JDBC pools, consumer lag, DLQs, and duplicate counts.
8. Expand rollout only after verifying rollback against candidate-written schemas and messages.

**Simulated incident:** during canary, DLT rates spike. Inspection reveals old consumers fail to recognize a new enum value emitted by candidate producers. Remediation: stop emitting the new enum, restore the old writer contract, upgrade all consumers first, and re-enable the producer feature afterward—never crank up DLT retries when payloads remain unreadable.

**Exit criteria:** zero unintended loss or duplication on accepted transactions, compatible schemas across the mixed-version window, draining backlogs, accurate alerts, and verified rollback without corrupting newly persisted data.

## 18. Version Change Review Checklist

- [ ] Captured baseline **live runtime** versions, dependency graph, configs, image digests, topology, and SLOs.
- [ ] Built old/new client × old/new server/broker matrices for every critical integration.
- [ ] Read system requirements, supported-version matrices, migration guides, and release notes for exact target versions.
- [ ] Verified BOM alignment and overrides; avoided mixing incompatible Spring Data release trains or Framework/Integration modules.
- [ ] Verified Java runtime, `jakarta`/`javax` namespaces, build plugins, and binary compatibility.
- [ ] Tested SQL queries/transactions/SQLStates and JDBC pools/TLS against real database versions.
- [ ] Tested Redis serializers, key prefixes, TTLs, failovers, and legacy bytes prior to upgrade.
- [ ] Tested HTTP timeouts, status mappings, retries, TLS, idempotency keys, and payload conversions.
- [ ] Tested broker ACKs/offsets, redeliveries, DLTs, consumer groups, cross-version producer/consumer pairs, and schema fixtures.
- [ ] Tested Spring Integration channels, pollers, `errorChannel`, ACKs, and transaction boundaries if used.
- [ ] Tested rolling deployments, expand–contract schemas, and binary rollbacks over candidate-written data.
- [ ] Verified latency, throughput, consumer lag, DB pools, retries/duplicates, and uncertain-outcome handling.
- [ ] Prepared canary gates, alerts, stop criteria, and layered recovery plans.
- [ ] Assigned owners, updated runbooks, archived compatibility evidence, and scheduled legacy code/config cleanup.

**Key takeaway:** client, driver, broker, and Spring Data version strings are labels covering numerous technical contracts. Safe upgrades prove **both old and new applications speak cleanly with sources and targets, decode required historical data, preserve error/ACK/transaction semantics, and recover cleanly when any step fails**. That proof comes from dependency graphs, compatibility matrices, contract fixtures, integration tests, fault injection, and monitored rollouts.
