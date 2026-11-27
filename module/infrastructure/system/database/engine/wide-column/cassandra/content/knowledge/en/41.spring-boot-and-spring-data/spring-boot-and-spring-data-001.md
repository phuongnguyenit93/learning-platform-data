# Configuring Cassandra in Spring Boot and the Library Version Matrix

## 1. Scenario: One Application, Three Environments, and Four Library Layers

A team builds a **Java/Spring Boot** application that stores sensor events in **Apache Cassandra**. On a developer machine, the application connects successfully to a single-node Cassandra instance. In staging, it reports `NoHostAvailable` or authentication errors. In production, a developer upgrades the Java Driver version alone in `pom.xml`, while Spring Boot still manages Spring Data Cassandra according to the old dependency set; the system starts up, but some repositories or codecs fail at runtime.

The problem does not lie in a single YAML line. When using Cassandra with Spring Boot, at least **four layers** must work in coordination:

1. **Spring Boot**: auto-configuration, dependency management/BOM, profiles, lifecycle, Actuator, and externalized configuration.
2. **Spring Data Cassandra**: entity mapping, `CassandraTemplate`, repositories, mapping/conversions, and query abstraction.
3. **Apache Cassandra Java Driver**: `CqlSession`, native protocol, routing, pooling, request timeout, TLS, authentication, and paging.
4. **Cassandra server/cluster**: CQL schema, partition/clustering key, replication factor, datacenter, consistency level, compaction/repair, and disk/network.

Changing the version of one layer **does not automatically** make the other layers compatible. At the same time, a valid Spring configuration file **does not guarantee** efficient Cassandra queries: a repository can still emit a CQL statement missing the partition key, or a query can read too many SSTables/tombstones.

This lesson belongs to the **Spring Boot and Spring Data** chapter in the **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA** module, aimed at understanding distributed architecture, the wide-column model, replication/CL, CQL practice, and connecting from Java.

**Learning Objectives:**

1. Distinguish the responsibilities of the Spring Boot starter, Spring Data Cassandra, Java Driver, and Cassandra server.
2. Configure `spring.cassandra.*` on **Spring Boot 3.x**, separate dev/staging/prod, and understand why Boot 2.x may use a different prefix.
3. Use a BOM instead of mixing versions arbitrarily; read a **release-line compatibility matrix** and verify real dependencies with Maven/Gradle.
4. Create a CQL schema, composite primary key entity, repository, and service with **Spring Data Cassandra**.
5. Understand the differences between repository/template, direct `CqlSession` access, the Java Driver mapper, and reactive Cassandra.
6. Apply local DC, RF/CL, request deadlines, paging, TLS, least-privilege roles, secrets, and health checks.
7. Diagnose autoconfiguration, dependency mismatch, schema drift, auth, and performance issues; plan upgrades with testing and rollback.

> **Scope/versions:** the main configuration examples target **Spring Boot 3.x** with Java 17+ and the corresponding Spring Data Cassandra. The matrix in Section 5 describes **guiding major/minor release lines**, not locked patch versions for every release. To select the exact current artifacts and versions, you must check the **Spring Boot BOM, release notes, Spring Data release train, Java Driver, and Cassandra support matrix** for the exact version you plan to deploy. Do not treat illustrative version numbers as "latest" recommendations.

## 2. The Four Connection Layers and the Flow of a Cassandra Request

~~~mermaid
flowchart TD
    A["REST Controller / Scheduled job"] --> B["Service: validation + auth + deadline"]
    B --> C["Spring Data Repository / CassandraTemplate"]
    B --> D["CqlSession Core API when custom CQL is needed"]
    C --> E["Spring Data Cassandra mapping/conversions"]
    E --> D
    D --> F["Java Driver: pool, routing, timeout, retry, TLS"]
    F --> G["Cassandra coordinator"]
    G --> H["Natural replicas by token + RF + CL"]
    H --> I["Memtable, SSTable, commit log, disk"]
~~~

| Layer | Provides | Does Not Provide |
| --- | --- | --- |
| **Spring Boot** | Bean creation, configuration via `application.yml`, profiles, lifecycle, BOM, and integrated observability. | Does not automatically create query-optimal data models or ensure data resides in the right partition. |
| **Spring Data Cassandra** | `@Table`, `@PrimaryKeyClass`, `CassandraRepository`, `CassandraTemplate`, mapping/converters, and repository queries. | Does not automatically provide SQL joins, JPA persistence context/dirty checking, or RDBMS-style multi-partition transactions. |
| **Java Driver 4.x** | `CqlSession`, native protocol, prepared statements, node discovery, token-aware routing when full keys are supplied, paging, and retries. | Does not automatically decide RF/CL, fix hot partitions, or make expensive `ALLOW FILTERING` queries cheap. |
| **Cassandra server** | CQL storage, token placement, replica reads/writes, repair/compaction, tombstones/TTL, and replication. | Does not know which Spring profile the service is using or the HTTP deadline of the gateway. |

### 2.1. Auto-configuration Is Not Magic

When the classpath contains the starters and is not disabled by custom beans, Spring Boot can configure `CqlSession`, Spring Data infrastructure, and repositories. However, it needs essential inputs such as the proper **contact points, local datacenter, keyspace, auth, and TLS**. A `CqlSession` that connects only proves the native protocol path to some nodes works; it does not prove:

- Every node is `UN`, replicas satisfy quorum, or the cluster has no pending repair.
- The CQL table exists and the `@PrimaryKey` mapping matches the real primary key.
- The API bounds bucket/page/byte counts and uses the contractually required consistency level.
- The account has only the required permissions and the connection has full peer/TLS verification.

### 2.2. Do Not Confuse Spring Data Cassandra with the Java Driver Mapper

**Spring Data Cassandra** is Spring's abstraction, with `CassandraRepository`, `CassandraTemplate`, and `@Table`. **Java Driver Object Mapper** is a separate module in Driver 4.x with `@Entity`, `@Dao`, `@Mapper`, and an annotation processor. The two mapping systems **do not have interchangeable annotations**.

A project can use Spring Data for CRUD and `CqlSession` for specialized CQL, but should not enable both mappers simultaneously just because the libraries are available. Clear boundaries are needed to avoid generating uncontrolled queries for the same business workflow.

## 3. Choosing a Starter: Blocking or Reactive?

### 3.1. Maven BOM with Spring Boot Parent

Example **Spring Boot 3.x project** using blocking Spring Data Cassandra:

~~~xml
<!-- pom.xml: replace BOOT_VERSION with a project-approved 3.x version. -->
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example.telemetry</groupId>
  <artifactId>telemetry-cassandra</artifactId>
  <version>1.0.0-SNAPSHOT</version>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.4.0</version>
    <relativePath/>
  </parent>

  <properties>
    <java.version>17</java.version>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-data-cassandra</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>
</project>
~~~

**`3.4.0` here is a fixed example to illustrate POM structure**, not advice to run the very first patch release in production. A real project should choose a **supported/tested patch**, then keep it consistent via lock/dependency management and a security update process.

**Key point:** do not manually add `<version>` for `spring-data-cassandra`, `java-driver-core`, or Spring Data modules when using the Boot BOM without a verified reason. The BOM selects **a release-level compatible set of dependencies**, whereas overriding individual artifacts can produce `NoSuchMethodError`, `ClassNotFoundException`, or codec errors.

### 3.2. Reactive Starter Is an Architectural Choice, Not a Free Booster

If the application needs a Reactive Streams pipeline from WebFlux/Reactor to Cassandra, Boot versions support the corresponding reactive starter, typically `spring-boot-starter-data-cassandra-reactive`. When using it, you must:

- Verify the **exact artifact/version** in the project's BOM.
- Use reactive repositories/templates per Spring Data guidance, with `Mono`/`Flux` and appropriate demand semantics.
- Never call `block()` on a Netty/event-loop thread; bound concurrency/buffers and query fan-out.
- Do not migrate an entire app from Spring MVC to reactive solely hoping CQL queries will run faster.

~~~text
Blocking application:
  Spring MVC -> CassandraRepository / CassandraTemplate

Reactive application:
  Spring WebFlux -> ReactiveCassandraRepository /
                    ReactiveCassandraTemplate

Core Driver option:
  CqlSession -> executeAsync -> CompletionStage<AsyncResultSet>
~~~

**`CompletionStage` is not automatically a `Flux<Row>`**, and an async result may contain only the first page. Large result sets require explicit demand/paging handling.

## 4. BOM and Dependency Graph: The Source of Truth for Runtime Versions

### 4.1. What Does the BOM Manage?

The Spring Boot BOM (`spring-boot-dependencies`) manages a set of versions including Spring Framework, the Spring Data release train, the driver, and related libraries. When using the Spring Boot parent, dependency management is usually applied automatically. If the project uses its own parent, it can **import the BOM**:

~~~xml
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-dependencies</artifactId>
      <version>${spring-boot.version}</version>
      <type>pom</type>
      <scope>import</scope>
    </dependency>
  </dependencies>
</dependencyManagement>
~~~

When importing the BOM, the `spring-boot.version` property must be set to an approved version; do not copy both the parent and the BOM into the POM without understanding version resolution rules. With **Gradle**, use the appropriate plugin/BOM/dependency-management strategy and inspect the resolved configuration, rather than inferring from `build.gradle` when platform or resolution overrides exist.

### 4.2. Three Different Numbers Commonly Confused

~~~text
Spring Boot version        : version of the framework/bootstrap + BOM
Spring Data Cassandra ver. : version of the Spring data module
Java Driver version        : version of the native protocol client implementation
Apache Cassandra server   : version of the database cluster
~~~

For example, **Spring Boot 3.4.x** does not mean Cassandra server **3.4.x**, nor does it mean Java Driver **3.4.x**. The version numbers of these projects **do not move in lockstep**.

### 4.3. Inspect Real Dependencies (Not Just Declared POM Entries)

~~~bash
# Run inside the application's Maven project, not in the Cassandra lab.
./mvnw dependency:tree -Dincludes=org.springframework.data:spring-data-cassandra
./mvnw dependency:tree -Dincludes=com.datastax.oss:java-driver-core
./mvnw dependency:tree -Dincludes=org.springframework:spring-core

# Gradle example if the project actually uses Gradle:
./gradlew dependencyInsight --dependency spring-data-cassandra --configuration runtimeClasspath
./gradlew dependencyInsight --dependency java-driver-core --configuration runtimeClasspath
~~~

The group/artifact names of the Java Driver and starters **can change across release lines**; the commands above illustrate checking a familiar Driver 4.x coordinate and do not guarantee all future releases use the same coordinates. When the output is empty, inspect the full `dependency:tree`/resolved graph, BOM imports, and docs for the running version. In production, store a **resolved dependency report + SBOM/lockfile**, not just the versions in `pom.xml`.

## 5. Version Matrix: Spring Boot, Spring Data, Java, and Cassandra Driver

### 5.1. Guiding Release-Line Matrix

| Spring Boot Line | Spring Framework (Line) | Spring Data Cassandra (Typical Line) | Common Minimum Java | Key Configuration / Notes |
| --- | --- | --- | --- | --- |
| **2.7.x** | 5.3.x | **3.4.x** in Spring Data 2021.2 | Java 8+ per Boot line support | Many Cassandra properties live under `spring.data.cassandra.*`; upgrading to Boot 3 requires reviewing Jakarta/Java 17. |
| **3.0.x** | 6.0.x | **4.0.x** in Spring Data 2022.0 | **Java 17+** | Spring Boot 3, Spring Framework 6; many `javax.*` APIs moved to `jakarta.*`. |
| **3.1.x** | 6.0.x | **4.1.x** in Spring Data 2023.0 | Java 17+ | Check minor changes in Spring Data and the BOM-pinned driver. |
| **3.2.x** | 6.1.x | **4.2.x** in Spring Data 2023.1 | Java 17+ | Cassandra configured via `spring.cassandra.*` in Boot 3. |
| **3.3.x** | 6.1.x | **4.3.x** in Spring Data 2024.0 | Java 17+ | Keep the BOM aligned; test mapping/metrics and paging when updating. |
| **3.4.x** | 6.2.x | **4.4.x** in Spring Data 2024.1 | Java 17+ | Illustrative line in the POM; do not pick a patch blindly without verification. |
| **3.5.x** | 6.2.x | **4.5.x** in Spring Data 2025.0 | Java 17+ | Verify the patch BOM, exact JDK, and dependency constraints. |
| **4.0.x** | 7.0.x (Boot 4 line direction) | **5.0.x** in the corresponding new Spring Data line | Check JDK requirements of the specific Boot 4 release | Major upgrade: check migration docs, starters/modules, packages, config properties, and actual driver; **do not copy 3.x config without testing**. |

**How to use this table:** this is a **release-line mapping for learning and planning**, not an official lockfile for the patch you are running. The Spring Boot BOM of a **specific patch release** determines the Spring Data patch, Java Driver patch, Micrometer, Reactor, and transitive dependencies. Version milestones and support status can change; check the release train/BOM before choosing a release for a new system.

### 5.2. Java Driver and Cassandra Server Are **Two Separate Axes**

Do not equate "Spring Boot 3.4 = Java Driver 4.4" or "Spring Data 4.4 = Cassandra server 4.4". Instead:

| Tier | How to Choose Version | What Must Be Verified |
| --- | --- | --- |
| **Spring Boot + Framework** | Pick a supported Boot release and follow its BOM. | JDK, lifecycle, auto-configuration, major release breaking changes. |
| **Spring Data Cassandra** | Use the line managed by the Boot BOM. | Mapping annotations, repository/query API, template, reactive module. |
| **Cassandra Java Driver 4.x** | Normally take the BOM-pinned driver; override only with justification and compatibility tests. | Native protocol, `CqlSession`, node/DC discovery, TLS/auth, codecs, metrics. |
| **Cassandra server 3.x/4.x/5.x** | Choose per the driver/Spring Data **support matrix** and cluster upgrade path. | Protocol/feature compatibility, SSTable format, schema, RF/CL, repair/compaction. |
| **JDK** | Per the specific Boot/driver release. | Runtime/toolchain, TLS ciphers, GC, Docker image, build plugins. |

**Note:** Driver 4.x can connect to multiple Cassandra versions over compatible native protocols, but that **does not automatically mean every new Cassandra 5.x feature is fully supported by Spring Data mapping**. Especially for vector types/SAI/new features or custom codecs, you must test in practice and consult the matrix for the driver version in use.

### 5.3. Dependency Conflict Example

~~~text
Boot 3.x POM manages:
  Spring Data Cassandra 4.x
  Java Driver per BOM 4.x patch A

Developer manually forces:
  java-driver-core 4.x patch B
  java-driver-query-builder patch C
  Spring Data Cassandra 4.x patch D

Possible impact:
  - ClassNotFoundException / NoSuchMethodError
  - mismatched codec/mapper/method signatures
  - out-of-sync reactive/metrics modules
  - unexpected TLS/protocol/config behavior
~~~

Not every override is wrong: sometimes a security patch requires upgrading the driver within a compatible range. However, you must **align modules in the same family**, read compatibility notes, run a clean build/integration tests, and update the SBOM/lockfile. Do not use **`-DskipTests`** to hide compatibility errors.

## 6. Designing the Cassandra Keyspace and Table Before Starting the Application

### 6.1. Lab CQL Schema

Assume a DC `dc1` with enough nodes for RF=3 and `LOCAL_QUORUM`. Run CQL via `cqlsh` using a schema-admin role on a **lab cluster**:

~~~sql
CREATE KEYSPACE IF NOT EXISTS telemetry_spring
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

CREATE TABLE IF NOT EXISTS telemetry_spring.events_by_device_day (
  device_id text,
  event_day date,
  event_time timestamp,
  event_id uuid,
  event_type text,
  payload text,
  PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

Rationale for the schema:

- **Composite partition key `(device_id, event_day)`**: bounds history into daily buckets and routes tokens/replicas by device and day.
- **Clustering key `(event_time, event_id)`**: supports time-range reads within a day and disambiguates two events sharing the same timestamp.
- **`event_type` and `payload`** are regular columns. If you need to find all `ALARM` events across many devices by site, consider a query-driven table/projection rather than just writing a `findByEventType` repository method with `ALLOW FILTERING`.
- RF 3 means three full replicas in `dc1`; `LOCAL_QUORUM` requires two responses from the local DC. Do not use an RF 3 example on a single node and expect real quorum.

### 6.2. Writing and Reading Fixed Sample Data

~~~sql
CONSISTENCY LOCAL_QUORUM;

INSERT INTO telemetry_spring.events_by_device_day
  (device_id, event_day, event_time, event_id, event_type, payload)
VALUES
  ('device-7', '2026-11-21', '2026-11-21T09:00:00Z',
   123e4567-e89b-42d3-a456-426614174001, 'HEARTBEAT', 'ok');

INSERT INTO telemetry_spring.events_by_device_day
  (device_id, event_day, event_time, event_id, event_type, payload)
VALUES
  ('device-7', '2026-11-21', '2026-11-21T09:01:00Z',
   123e4567-e89b-42d3-a456-426614174002, 'TEMPERATURE', '21.6');

SELECT event_time, event_id, event_type, payload
FROM telemetry_spring.events_by_device_day
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21'
  AND event_time >= '2026-11-21T09:00:00Z'
  AND event_time < '2026-11-21T10:00:00Z'
LIMIT 100;
~~~

`CONSISTENCY` is a **cqlsh** command, not a CQL statement passed verbatim to a repository or the Java Driver. The `event_day` value in the application must be derived from the **UTC date of `event_time`**, used consistently across both ingestion and backfill. A different timezone can cause events to be written into the wrong day partition.

### 6.3. Schema Migration Does Not Belong to the Service User

**Do not let a production application automatically create/drop keyspaces or tables on every restart.** A typical process includes:

1. Version-controlled DDL, with schema and token/partition/compaction impact reviewed.
2. A dedicated migration role or pipeline with the necessary `CREATE/ALTER` permissions.
3. A service role with only `SELECT`/`MODIFY` on the exact tables needed.
4. Schema agreement and integration tests passing before opening traffic.
5. v1/v2 migration when changing partition/clustering keys: create the new table, dual-write/CDC, backfill, reconcile, and canary cutover; **never `ALTER TABLE` to change the primary key**.

## 7. `spring.cassandra.*`: Minimal Configuration on Boot 3.x

### 7.1. Base Configuration File

~~~yaml
# src/main/resources/application.yml (example for Spring Boot 3.x)
spring:
  application:
    name: telemetry-api
  cassandra:
    contact-points: ${CASSANDRA_CONTACT_POINTS}
    port: ${CASSANDRA_PORT:9042}
    local-datacenter: ${CASSANDRA_LOCAL_DC}
    keyspace-name: telemetry_spring
    username: ${CASSANDRA_USERNAME}
    password: ${CASSANDRA_PASSWORD}
    schema-action: none
~~~

**How to interpret this:**

- `contact-points` are initial node discovery endpoints, **not** the full list of replicas for every partition. The driver tracks topology and can open pools to discovered nodes.
- `local-datacenter` must match the **DC name in the cluster's snitch metadata**, not an assumed cloud region. Misconfiguration can cause abnormal routing or no available nodes.
- `keyspace-name` is the default keyspace for certain Spring Data/driver paths; entity/table mapping still needs to match the schema.
- `username/password` only applies if the cluster enables matching authentication. Environment variables are an example of externalized config; production may choose a secret manager or workload identity.
- `schema-action: none` expresses the intent **not to let the app auto-create/drop schemas**. Verify the key name and `SchemaAction` for your specific Boot/Spring Data version; do not rely on Boot auto-fixing production schemas.
- Never hardcode production addresses/credentials in source, and **never fall back** to a dev contact point if a required variable is missing.

**Important difference:** in many **Spring Boot 2.x** versions, the Cassandra prefix may be under `spring.data.cassandra.*`. On **Boot 3.x**, examples use `spring.cassandra.*`. When upgrading, consult the **configuration metadata documentation for the running Boot version** and inspect effective properties; an old unbound property name can silently make the app use wrong defaults.

### 7.2. `application-dev.yml` and `application-prod.yml`

~~~yaml
# application-dev.yml — synthetic data, lab node, no prod credentials.
spring:
  cassandra:
    contact-points: ${DEV_CASSANDRA_HOST:127.0.0.1}
    port: ${DEV_CASSANDRA_PORT:9042}
    local-datacenter: ${DEV_CASSANDRA_DC:dc1}
    keyspace-name: telemetry_spring
~~~

~~~yaml
# application-prod.yml — must be supplied with dedicated environment variables/secrets.
spring:
  cassandra:
    contact-points: ${PROD_CASSANDRA_CONTACT_POINTS}
    port: ${PROD_CASSANDRA_PORT:9042}
    local-datacenter: ${PROD_CASSANDRA_LOCAL_DC}
    keyspace-name: telemetry_spring
    username: ${PROD_CASSANDRA_USERNAME}
    password: ${PROD_CASSANDRA_PASSWORD}
~~~

Splitting files illustrates **Spring profiles**. In practice, use **consistent variable naming and avoid having both the base file and a profile file define credentials from different sources**. For applications needing fail-closed isolation, validate `spring.profiles.active`, expected cluster/DC, and required properties before accepting traffic; never default to `dev` when the production profile is missing.

~~~bash
# CLI example to select environment, containing no passwords:
java -jar telemetry-api.jar --spring.profiles.active=dev
~~~

**Warning on secrets:** environment variables can still leak via dumps/logs/proc introspection by privileged actors. Production should use an approved secret manager, IAM, and rotation; never commit `application-prod.yml` with real passwords or print the entire effective environment when debugging.

## 8. When Is Separate Java Driver Configuration Needed?

Spring Boot manages common Cassandra properties, while behaviors such as **pooling, request timeout, page size, throttler, metrics/tracing, SSL, and retry policy** can be controlled at **Driver 4.x** or via supported customizers.

### 8.1. Java Driver HOCON Example

~~~hocon
# Example datastax-java-driver config for controlled testing.
datastax-java-driver {
  basic.request {
    timeout = 2 seconds
    consistency = LOCAL_QUORUM
    page-size = 100
  }
  advanced.connection.pool {
    local.size = 1
  }
  advanced.request-throttler {
    class = ConcurrencyLimitingRequestThrottler
    max-concurrent-requests = 200
    max-queue-size = 400
  }
}
~~~

**Principles:**

1. Numbers like `2s/100/200/400` are **lab values**, not standard production SLOs/limits.
2. `page-size` bounds the **target number of rows per page**, not bytes per page; CQL `LIMIT` controls the logical row count returned by the statement.
3. `local.size` is the number of connections per pool/node in driver config, **not** total in-flight API requests. The native protocol multiplexes multiple requests over a connection.
4. The driver request throttler limits one driver/session scope and **does not automatically bound** HTTP queues or fleet-wide pod counts; application-level admission/backpressure is still needed.
5. `LOCAL_QUORUM` is a Cassandra consistency contract, not a "nonblocking" property; with RF 3 in one DC it requires two full replica responses.
6. **An option may already have a Boot equivalent**; check override precedence and effective driver config for your Boot/Driver versions so HOCON and `application.yml` do not conflict.
7. Option names, throttler classes, and support/versions can change. If the driver does not load HOCON, do not claim throttling is active just because the file exists.

### 8.2. Do Not Accidentally Create Two `CqlSession` Instances

A common anti-pattern is letting Boot auto-configure a `CqlSession` while a service calls `CqlSession.builder().build()` per request. Consequences:

- Two or more unnecessary pools/control connections, metadata discovery, and TLS/auth overhead.
- Spring Data repositories use session A while custom code uses session B with different DC/CL/credentials.
- Difficult session shutdown, inconsistent metrics, and broken backpressure control.

**Right approach:** prefer **injecting the Spring-managed `CqlSession`** into services when the Core API is needed. Only define a custom session bean for a justified requirement (multiple distinct clusters/identities) and with full awareness of Boot auto-configuration and lifecycle impacts.

## 9. Consistency, Keyspace, and Topology Cannot Be Hidden Behind Properties

### 9.1. Local DC and Natural Replicas

~~~mermaid
flowchart TD
    A["Spring Repository / CqlSession"] --> B["Driver chooses coordinator per policy/local DC"]
    B --> C["Hash partition key (device_id,event_day) into token"]
    C --> D["Natural replicas per NetworkTopologyStrategy"]
    D --> E["LOCAL_QUORUM: wait for 2/3 full replicas in dc1"]
    E --> F["Return result or timeout/unavailable"]
~~~

A request can succeed with `LOCAL_QUORUM` as soon as two local replicas respond; **this does not prove all replicas hold identical data**, nor does it replace repair. If the application runs in `dc2`, you must verify keyspace RF per DC, the local DC property, and cross-DC/failover behavior per the SLA contract.

### 9.2. Three Error Types to Distinguish

| Scenario | Possible Cause | Will Changing Timeout Fix It? |
| --- | --- | --- |
| `Unavailable` under `LOCAL_QUORUM` | Insufficient replicas matching CL/DC/RF. | **No.** Inspect topology/replicas. |
| Read/write timeout | Replica/coordinator did not respond in time; disk/GC/queue/compaction/network. | May change wait time, **does not fix root cause**. |
| Authentication/authorization failure | Wrong role/credentials/TLS/truststore or CQL permissions. | **No.** Fix identity/secret/permissions. |

**Do not automatically downgrade `LOCAL_QUORUM` to `LOCAL_ONE` on errors**, as that changes the consistency contract; it requires business approval and measuring data divergence if policy permits.

## 10. Spring Data Cassandra: Mapping Composite Primary Keys

In Cassandra, **the partition key and clustering key are the row's identity**, not mere attributes for sorting in Java. For `events_by_device_day`, we must map all **four components** of the primary key.

### 10.1. `@PrimaryKeyClass` for Composite Keys

~~~java
// EventKey.java — Spring Data Cassandra, not Java Driver @Entity.
package example.telemetry;

import java.io.Serializable;
import java.time.Instant;
import java.time.LocalDate;
import java.util.Objects;
import java.util.UUID;
import org.springframework.data.cassandra.core.cql.Ordering;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyClass;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyColumn;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyType;

@PrimaryKeyClass
public class EventKey implements Serializable {
    private static final long serialVersionUID = 1L;

    @PrimaryKeyColumn(
        name = "device_id", ordinal = 0, type = PrimaryKeyType.PARTITIONED)
    private String deviceId;

    @PrimaryKeyColumn(
        name = "event_day", ordinal = 1, type = PrimaryKeyType.PARTITIONED)
    private LocalDate eventDay;

    @PrimaryKeyColumn(
        name = "event_time", ordinal = 2,
        type = PrimaryKeyType.CLUSTERED, ordering = Ordering.DESCENDING)
    private Instant eventTime;

    @PrimaryKeyColumn(
        name = "event_id", ordinal = 3, type = PrimaryKeyType.CLUSTERED)
    private UUID eventId;

    public EventKey() {}

    public EventKey(String deviceId, LocalDate eventDay,
                    Instant eventTime, UUID eventId) {
        this.deviceId = deviceId;
        this.eventDay = eventDay;
        this.eventTime = eventTime;
        this.eventId = eventId;
    }

    public String getDeviceId() { return deviceId; }
    public void setDeviceId(String value) { deviceId = value; }

    public LocalDate getEventDay() { return eventDay; }
    public void setEventDay(LocalDate value) { eventDay = value; }

    public Instant getEventTime() { return eventTime; }
    public void setEventTime(Instant value) { eventTime = value; }

    public UUID getEventId() { return eventId; }
    public void setEventId(UUID value) { eventId = value; }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof EventKey)) return false;
        EventKey that = (EventKey) other;
        return Objects.equals(deviceId, that.deviceId)
            && Objects.equals(eventDay, that.eventDay)
            && Objects.equals(eventTime, that.eventTime)
            && Objects.equals(eventId, that.eventId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(deviceId, eventDay, eventTime, eventId);
    }
}
~~~

### 10.2. Why Must `ordinal` and `type` Be Specified Explicitly?

| Annotation | CQL Component | Purpose |
| --- | --- | --- |
| `@PrimaryKeyColumn(... PARTITIONED, ordinal=0)` | `device_id` | First part of the composite partition key. |
| `@PrimaryKeyColumn(... PARTITIONED, ordinal=1)` | `event_day` | Second part of the partition key. |
| `@PrimaryKeyColumn(... CLUSTERED, ordinal=2)` | `event_time` | First clustering column, DESC order. |
| `@PrimaryKeyColumn(... CLUSTERED, ordinal=3)` | `event_id` | Clustering tie-breaker. |

The `ordinal`/`type` values must **match the real schema**; do not change annotations expecting to "change the partition key" in Cassandra. To add `event_hour` to the partition key or reverse clustering order, you must **create a new table and migrate the data**, not merely edit the Java class.

The key class's `equals/hashCode` must rely on **stable identity**; avoid using a mutable object as a `HashMap` key and mutating `eventTime` while stored. For CQL `timestamp`, precision is typically **millisecond-level**, not preserving arbitrary nanoseconds of `Instant` by default; test round-trips if the domain carries sub-millisecond precision.

### 10.3. `@Table` and `@PrimaryKey`

~~~java
// EventEntity.java
package example.telemetry;

import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("events_by_device_day")
public class EventEntity {
    @PrimaryKey
    private EventKey key;

    @Column("event_type")
    private String eventType;

    @Column("payload")
    private String payload;

    public EventEntity() {}

    public EventEntity(EventKey key, String eventType, String payload) {
        this.key = key;
        this.eventType = eventType;
        this.payload = payload;
    }

    public EventKey getKey() { return key; }
    public void setKey(EventKey value) { key = value; }

    public String getEventType() { return eventType; }
    public void setEventType(String value) { eventType = value; }

    public String getPayload() { return payload; }
    public void setPayload(String value) { payload = value; }
}
~~~

**Note:** Spring Data annotations live in `org.springframework.data.cassandra.core.mapping`, **not** `com.datastax.oss.driver.api.mapper.annotations.Entity`. The default keyspace in this example is configured via `spring.cassandra.keyspace-name`. If multiple keyspaces exist, define explicit mapping paths and templates/sessions rather than expecting every repository to locate the right keyspace automatically.

## 11. `CassandraRepository`: Concise CRUD Still Requires CQL Design

### 11.1. Repository by Primary Key

~~~java
// EventRepository.java
package example.telemetry;

import java.time.Instant;
import java.time.LocalDate;
import java.util.List;
import org.springframework.data.cassandra.repository.CassandraRepository;
import org.springframework.data.cassandra.repository.Query;
import org.springframework.data.repository.query.Param;

public interface EventRepository
        extends CassandraRepository<EventEntity, EventKey> {

    // CQL has full partition key, clustering range, and fixed LIMIT.
    @Query(
        "SELECT device_id, event_day, event_time, event_id, " +
        "event_type, payload " +
        "FROM telemetry_spring.events_by_device_day " +
        "WHERE device_id = :deviceId AND event_day = :eventDay " +
        "AND event_time >= :fromInclusive " +
        "AND event_time < :toExclusive LIMIT 100")
    List<EventEntity> findWindow(
        @Param("deviceId") String deviceId,
        @Param("eventDay") LocalDate eventDay,
        @Param("fromInclusive") Instant fromInclusive,
        @Param("toExclusive") Instant toExclusive);
}
~~~

**Strengths:** Spring Data generates the repository implementation, maps entities, and supports basic CRUD operations. `findById(EventKey)` is a **full primary key** lookup. The `findWindow` query writes **explicit CQL** so the partition/range constraints are clear. Named parameter syntax, return types, and query binding behavior must be tested against your exact Spring Data Cassandra minor version.

**Do not write** a method like `findByEventType(String type)` assuming Spring Data can efficiently scan all partitions. `event_type` is a regular column; Cassandra does not natively support arbitrary derived queries like SQL repositories. Using `ALLOW FILTERING` on large tables typically causes full scans and high cost, not a production-optimal solution.

### 11.2. `save` Is Not a Unique Insert Transaction

`repository.save(entity)` typically produces an **upsert** mutation according to Spring Data's mapping. It has no JPA persistence context/dirty checking, no automatic row locking, and does not prevent overwriting an existing row with the same primary key. Cases to check:

- If two producers write the same primary key, Cassandra resolves conflicts by **mutation timestamp** and per-cell semantics, not HTTP request order.
- `null` fields in an entity may be mapped to **cell deletes/tombstones** or ignored depending on configuration; do not load a **partial column projection** into an entity and call `save` to update one field without understanding the null/unset strategy.
- TTL is typically measured from write time, not `event_time`; repeated writes can alter retention.
- A write timeout does not prove no replica wrote the data; retrying with a new UUID can create duplicates.

**To update only `payload`**, you can run a CQL `UPDATE ... SET payload=? WHERE` with the full key via template/Driver instead of saving a partially populated entity.

### 11.3. Service Bounding Queries Within One UTC Day

~~~java
// EventReadService.java
package example.telemetry;

import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class EventReadService {
    private final EventRepository repository;

    public EventReadService(EventRepository repository) {
        this.repository = repository;
    }

    public List<EventEntity> readOneDay(
            String deviceId, Instant fromInclusive, Instant toExclusive) {
        if (deviceId == null || deviceId.isBlank()) {
            throw new IllegalArgumentException("deviceId is required");
        }
        if (fromInclusive == null || toExclusive == null ||
            !fromInclusive.isBefore(toExclusive)) {
            throw new IllegalArgumentException("Invalid half-open window");
        }

        LocalDate day = fromInclusive
            .atZone(ZoneOffset.UTC).toLocalDate();
        Instant nextDayStart = day.plusDays(1)
            .atStartOfDay(ZoneOffset.UTC).toInstant();

        if (toExclusive.isAfter(nextDayStart)) {
            throw new IllegalArgumentException(
                "Window crosses UTC day; split into bounded buckets");
        }
        return repository.findWindow(
            deviceId, day, fromInclusive, toExclusive);
    }
}
~~~

**Benefit:** the service does not silently drop the next day when calling a query bound to **one `event_day`**. When a multi-day range is needed, the service must split it into UTC buckets, **bound bucket count/concurrency**, merge/sort, and enforce a **global LIMIT**. Never call `findAll()` and filter in Java to bypass table design.

**Security note:** in a real endpoint, verify the caller is authorized to access `deviceId` before calling the repository. CQL RBAC at the keyspace/table level **does not enforce tenant IDs** inside partition keys.

## 12. When to Use `CassandraTemplate` and Direct `CqlSession`?

### 12.1. Template When You Don't Want a Repository for Every Query

`CassandraTemplate` (or `CassandraOperations`) provides entity/query-oriented operations for business logic outside repositories. The example below reads one row by full key, **without creating a new session**:

~~~java
// EventTemplateService.java
package example.telemetry;

import org.springframework.data.cassandra.core.CassandraTemplate;
import org.springframework.stereotype.Service;

@Service
public class EventTemplateService {
    private final CassandraTemplate template;

    public EventTemplateService(CassandraTemplate template) {
        this.template = template;
    }

    public EventEntity getByKey(EventKey key) {
        // Actual template API must be verified against your Spring Data version.
        return template.selectOneById(key, EventEntity.class);
    }
}
~~~

The template reduces entity-mapping boilerplate, yet **still generates CQL executed through the Java Driver**. When template APIs or parameter binding differ across versions, check the Spring Data reference docs and generated CQL in integration tests; never assume every template method is a partition lookup.

### 12.2. Core Driver for Fine-Grained Statement Control

`CqlSession` is normally already a Boot-managed bean. Inject this bean for use cases requiring **prepared statements, routing, page size, CL, tracing, or narrow DTO reads**:

~~~java
// EventSummaryService.java
package example.telemetry;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.Instant;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import org.springframework.stereotype.Service;

@Service
public class EventSummaryService {
    public record EventSummary(Instant time, UUID eventId, String type) {}

    private final CqlSession session;
    private final PreparedStatement select;

    public EventSummaryService(CqlSession session) {
        this.session = session;
        this.select = session.prepare(
            "SELECT event_time, event_id, event_type " +
            "FROM telemetry_spring.events_by_device_day " +
            "WHERE device_id = ? AND event_day = ? " +
            "AND event_time >= ? AND event_time < ? LIMIT 100");
    }

    public List<EventSummary> read(
            String deviceId, LocalDate day, Instant from, Instant until) {
        BoundStatement query = select.bind(deviceId, day, from, until)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setPageSize(50);

        List<EventSummary> values = new ArrayList<>();
        for (Row row : session.execute(query)) {
            values.add(new EventSummary(
                row.getInstant("event_time"),
                row.getUuid("event_id"),
                row.getString("event_type")));
        }
        return values;
    }
}
~~~

**Why can Core be suitable for a timeline?** It reads only three columns instead of `payload`, reducing bytes transferred/deserialized; performance differences may come primarily from **column projection**, not necessarily from bypassing Spring Data mapping. When benchmarking mapper/repository versus Core, compare **identical CQL/CL/page size/rows** before drawing conclusions about abstraction overhead.

**Never** create a `CqlSession` per request or call `session.prepare(...)` on every HTTP call. A long-lived session maintains pooling/metadata; prepared statements should be reused.

### 12.3. Choosing the Tool by Query Need

| Need | Tool to Consider | What It Does Not Solve Automatically |
| --- | --- | --- |
| CRUD lookup by full primary key | `CassandraRepository` | Does not provide JPA transactions/dirty checking. |
| Ad-hoc entity-oriented queries | `CassandraTemplate` | Does not make a `WHERE` missing the partition key cheap. |
| Specialized CQL/narrow DTO, custom page/CL | `CqlSession` + prepared statements | Must map `Row` manually and handle paging/timeouts. |
| Reactive pipeline | Reactive repository/template or driver reactive APIs | No automatic backpressure if code buffers unbounded results. |
| Multi-partition reports/aggregations | Dedicated data model/projection/analytics | Cannot be fixed with `findAll()` or larger connection pools. |

## 13. Spring Data Reactive Cassandra and Backpressure Limits

If a project chooses the appropriate reactive starter, it can use `ReactiveCassandraRepository` with `Flux`/`Mono`, provided you **verify a consistent Spring Boot/Spring Data/Reactor/Driver version set**.

~~~java
// ReactiveEventRepository.java — for use in a reactive application.
package example.telemetry;

import java.time.Instant;
import java.time.LocalDate;
import org.springframework.data.cassandra.repository.Query;
import org.springframework.data.cassandra.repository.ReactiveCassandraRepository;
import org.springframework.data.repository.query.Param;
import reactor.core.publisher.Flux;

public interface ReactiveEventRepository
        extends ReactiveCassandraRepository<EventEntity, EventKey> {

    @Query(
        "SELECT device_id, event_day, event_time, event_id, " +
        "event_type, payload FROM telemetry_spring.events_by_device_day " +
        "WHERE device_id = :deviceId AND event_day = :eventDay " +
        "AND event_time >= :fromInclusive " +
        "AND event_time < :toExclusive LIMIT 100")
    Flux<EventEntity> findWindow(
        @Param("deviceId") String deviceId,
        @Param("eventDay") LocalDate eventDay,
        @Param("fromInclusive") Instant fromInclusive,
        @Param("toExclusive") Instant toExclusive);
}
~~~

**Do not** call `Flux.collectList()` on millions of rows and claim the pipeline solved memory usage. CQL `LIMIT 100` is a **server-side** bound per statement; if an API spans multiple buckets, you still need bounds on bucket count, rows/byte budget, concurrency, and global ordering. A `timeout` on a reactive stream does not prove Cassandra stopped processing the already-sent request.

~~~java
// Snippet inside a reactive service, not a complete class:
Flux<EventEntity> stream = reactiveRepo
    .findWindow(deviceId, day, from, until)
    .take(50) // Client-side cap; does not replace CQL LIMIT 100
    .timeout(java.time.Duration.ofMillis(800));
~~~

**Do not mix blocking repositories with the Netty event-loop** by calling `repository.findWindow(...)` inside a reactive `map` callback: it can block worker threads. If a blocking library must be used in a reactive system, isolate it on a bounded dedicated scheduler and measure the impact; better yet, choose the right data-access model upfront.

## 14. TLS, Authentication, and CQL Permissions in Spring Boot

A connection config can have the right contact points and DC yet remain **insecure** if it sends passwords in plaintext or disables server certificate verification.

### 14.1. Components to Prepare

| Component | Source | What Must Be Proven |
| --- | --- | --- |
| **Client TLS** | Cassandra native transport TLS and Spring/driver SSL config. | TLS handshake succeeds; server identity/CA/hostname valid per policy. |
| **Username/password or auth provider** | Secret manager/identity service. | Dedicated CQL role per service/environment; no superuser. |
| **RBAC** | Appropriate `GRANT SELECT`, `GRANT MODIFY`. | Read-only endpoint cannot `INSERT/ALTER`; writer job cannot create roles. |
| **Network policy** | VPC/firewall/service mesh as appropriate. | Dev/staging cannot reach prod CQL; internode/JMX not publicly exposed. |
| **Secrets rotation** | Vault/KMS/secret store. | Password/certificate rotation causes no prolonged outage; rollback/expiry alerts exist. |
| **Logs/metrics** | Actuator, driver logging, Micrometer. | No leaked passwords, raw payloads, or sensitive partition keys. |

### 14.2. Per-Table Permission Example

~~~sql
-- LAB: conditional admin commands, do not run with an application role.
CREATE ROLE IF NOT EXISTS telemetry_reader
WITH LOGIN = true AND PASSWORD = 'replace-with-managed-secret';

GRANT SELECT ON TABLE telemetry_spring.events_by_device_day
TO telemetry_reader;

CREATE ROLE IF NOT EXISTS telemetry_writer
WITH LOGIN = true AND PASSWORD = 'replace-with-managed-secret';

GRANT SELECT ON TABLE telemetry_spring.events_by_device_day
TO telemetry_writer;
GRANT MODIFY ON TABLE telemetry_spring.events_by_device_day
TO telemetry_writer;
~~~

These illustrative commands assume Cassandra has enabled the corresponding **authentication/authorization**. The password string is a lab placeholder; never copy it into source or tickets. A `GRANT` alone does nothing if the cluster still uses `AllowAllAuthorizer` or auth is disabled; check the **effective security configuration**, and separately protect `system_auth`, TLS, and OS/JMX permissions.

### 14.3. TLS/Secret Configuration Must Follow the Version

Depending on the Boot/Java Driver version, enabling SSL may use properties like `spring.cassandra.ssl.*`, Driver `SslEngineFactory` config, or a supported **session builder/config customizer**. Never copy an out-of-version TLS snippet and disable verification just to "make it run". The runbook must state:

1. Server `client_encryption_options` and corresponding cert chain.
2. Client trust material, hostname/SAN policy, and keystore if mTLS is used.
3. Management of password/truststore/keystore secrets via secret store, never logged.
4. Integration tests with valid cert, wrong cert, expired cert, and rotation.
5. Verification that clients cannot fall back to plaintext when production mandates TLS.

**CQL security does not replace JMX/OS security:** a Spring Data account with `SELECT` does not inherently have permission to run `nodetool` or read SSTables on the filesystem, and vice versa.

## 15. Actuator Health and Metrics: `UP` Is Not Data Correctness

With `spring-boot-starter-actuator` and Cassandra infrastructure present, Spring Boot can expose a Cassandra health indicator. However, **health `UP` does not mean every partition/replica reads and writes correctly**.

### 15.1. Three Distinct Layers of Checks

~~~text
Liveness:
  Can the process/app serve and is it unstuck?

Readiness:
  Does the app have valid config, session, schema, role, and eligibility for traffic?

Data/functional correctness:
  Do real queries by partition/key/CL, TTL/deletes, and result mapping behave properly?
~~~

Do not use a health endpoint every second to scan a large table; health checks must be **lightweight, bounded, and deadlined**. On a real cluster, a node can still show `UN` in `nodetool status` while queries on a hot partition are slow due to disk/compaction/tombstones.

### 15.2. Minimum Dashboard

| Layer | Metric | Question Answered |
| --- | --- | --- |
| **API/Spring** | HTTP p50/p95/p99, request rate, errors/timeouts, thread pool/queue. | What are users experiencing? |
| **Spring Data** | Query names, repository call counts, rows returned, mapping errors. | Are there N+1 queries or bloated entity reads? |
| **Java Driver** | Request latency/errors, retry attempts, connections, in-flight/throttler queue if supported. | Is the driver queuing/misrouting or is the backend slow? |
| **JVM** | Heap/RSS/direct memory, GC pauses, CPU, threads. | Are mapping/page size/payloads causing memory pressure? |
| **Cassandra** | Read/write latency, `tpstats`, compaction, SSTables, tombstones, disk/network. | Where are coordinators/replicas bottlenecked? |
| **Config/security** | Config version, local DC, TLS/auth failures, secret expiry, dependency/SBOM. | Is there post-deploy drift or an expiring certificate? |

When enabling Micrometer/Actuator, **do not assume all Driver 4.x metrics are exported automatically**: verify the required dependency/module and version-specific metrics wiring. Never attach `deviceId`, `eventId`, raw CQL literals, or credentials as histogram labels; cardinality and data leakage will spike.

### 15.3. Inspecting Nodes with `nodetool`

~~~bash
nodetool status
nodetool info
nodetool tpstats
nodetool compactionstats
nodetool gcstats
nodetool proxyhistograms
nodetool tablestats telemetry_spring.events_by_device_day
~~~

Exact commands/metrics depend on the Cassandra version. Rising `tpstats` pending tasks and disk await alongside p99 latency suggest a backend bottleneck; increasing pools or timeouts from Spring will not fix the physical cause. Selective tracing helps inspect coordinator/replica execution for a CQL statement; **never enable tracing for 100% of production traffic**.

## 16. Failing Fast When Misconfigured for the Wrong Cluster or Datacenter

A syntactically valid `application-prod.yml` can still point to a **staging cluster**. When credentials are shared or overly permissive, this is worse than an obvious connection error: the app can read/write the wrong data while HTTP still returns 200.

### 16.1. Declaring Expected Cluster Identity

~~~yaml
# Added in environment config, using real values provided at deploy time.
app:
  cassandra:
    expected-cluster-name: ${CASSANDRA_EXPECTED_CLUSTER_NAME}
    expected-datacenter: ${CASSANDRA_LOCAL_DC}
~~~

These keys are **application-defined properties**, not built-in Spring Boot Cassandra settings. You can write a startup guard that checks metadata from Cassandra:

~~~java
// CassandraClusterGuard.java
package example.telemetry;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class CassandraClusterGuard implements ApplicationRunner {
    private final CqlSession session;
    private final String expectedName;
    private final String expectedDc;

    public CassandraClusterGuard(
            CqlSession session,
            @Value("${app.cassandra.expected-cluster-name}") String expectedName,
            @Value("${app.cassandra.expected-datacenter}") String expectedDc) {
        this.session = session;
        this.expectedName = expectedName;
        this.expectedDc = expectedDc;
    }

    @Override
    public void run(ApplicationArguments args) {
        Row row = session.execute(
            SimpleStatement.newInstance(
                "SELECT cluster_name, data_center FROM system.local")
                .setConsistencyLevel(DefaultConsistencyLevel.ONE)
        ).one();

        if (row == null ||
            !expectedName.equals(row.getString("cluster_name")) ||
            !expectedDc.equals(row.getString("data_center"))) {
            throw new IllegalStateException(
                "Cassandra cluster/DC mismatch; refusing startup");
        }
    }
}
~~~

**Scope of this check:**

- `system.local` holds information for the responding node. Checking one node does not prove every node matches the intended topology; also cross-check **driver metadata, DC/rack, release versions, and network policy**.
- A startup guard is only an **additional defense layer**, not a substitute for IAM/TLS, RBAC, and network isolation. If a service spans multiple DCs or has approved failover, the verification logic must reflect that actual policy.
- Never log credentials/secrets upon mismatch. You may log the approved expected cluster ID and non-sensitive actual metadata.
- Reading `system.local` requires appropriate permissions and compatibility; verify behavior on your chosen Cassandra/driver versions.
- When failing fast, readiness must fail; **never** silently fall back to an unauthorized endpoint.

## 17. Pagination and Load Bounding with Spring Data

A repository returning `List<EventEntity>` can give the illusion that all results are already in RAM and reads are harmless. In Cassandra, `LIMIT`, page size, token ranges, and TTL/tombstone data govern the real cost.

### 17.1. `LIMIT`, Page Size, and HTTP Page Are Different

| Concept | Meaning | What Not to Assume |
| --- | --- | --- |
| **CQL `LIMIT 100`** | Maximum logical result rows for the statement. | Does not mean replicas only read 100 physical cells. |
| **Java Driver page size** | Target row count per native protocol page. | Not a byte limit or total query row cap. |
| **HTTP page/cursor** | A user-facing slice of results; a cursor may encode state across multiple buckets/queries. | Does not mean Cassandra has cheap RDBMS-style `OFFSET`. |
| **Cassandra paging state** | Page state token used by driver/server per query/protocol. | Should not be treated as an immutable cursor across all schemas/versions/deploys. |
| **Time bucket** | Partition `(device_id,event_day)`. | `ORDER BY` within a bucket does not create global ordering across days. |

For an API "fetch the 50 newest events in the last seven days", the service must decide a strategy to **read the needed days**, pick candidates, merge by `(event_time,event_id)`, bound partition/row/byte counts, and construct an **API-contract cursor**. Never assume `Pageable` in Spring Data Cassandra supports `OFFSET 100000` at constant cost like a relational database.

### 17.2. N+1 Repository Calls

~~~java
// ANTI-PATTERN if devices has thousands of elements.
for (String deviceId : deviceIds) {
    // Each device/day is a separate partition query.
    eventRepository.findWindow(deviceId, day, from, until);
}
~~~

A loop over 10,000 devices can trigger **10,000 CQL round-trips**. If called concurrently/async without bounds, it can overload coordinators/replicas. Consider:

- **A table by site/hour** or query-specific projection if the endpoint genuinely needs site-wide aggregation.
- **Rollups/materialized results** for statistics rather than scanning raw events across all devices.
- If fan-out is unavoidable, enforce **bounded concurrency** per app/fleet, deadlines, byte/page budgets, and backpressure.
- Never "fix" this with `ALLOW FILTERING` or unbounded pool/timeout increases.

### 17.3. Spring Data Mapping and `SELECT *`

Reading the full entity can pull huge `payload` values. If an endpoint only needs `event_time,event_type`, use a **narrow CQL projection** and map an appropriate DTO/projection, or create a separate summary table. A fair benchmark must separate:

1. Query/network/byte transfer cost.
2. Spring Data mapping/converter cost.
3. JSON serialization and API response cost.
4. Cassandra server cost: SSTables/tombstones, disk/compaction/CL.

Do not conclude "Spring Data is slow" when comparing against a Core API query that selects fewer columns; the two paths are not doing **the same work**.

## 18. Testing Configuration and Repositories Before Deployment

### 18.1. Three Testing Layers

| Layer | Purpose | Example |
| --- | --- | --- |
| **Unit/config binding** | Validate required properties, environment allowlists, defaults, and absence of secrets. | Missing `CASSANDRA_LOCAL_DC` fails startup. |
| **Integration with real/lab Cassandra** | Verify CQL schema, entity mapping, CL, auth/TLS, TTL, tombstones, and paging. | Save/read full key within one daily partition. |
| **Load/resilience** | Verify p95/p99, pool/in-flight, GC, replica down, compaction, and multi-DC. | RF=3, `LOCAL_QUORUM`, one controlled slow replica. |

Mocking the repository in unit tests checks service logic, but **does not test emitted CQL or native protocol compatibility**. Real integration tests against the target Cassandra/Driver/Boot versions are required.

### 18.2. JUnit Example with Pre-Seeded Sentinel Data

Assume a **dedicated test environment** already has the keyspace/table and sentinel row `device-7` from Section 6; CI can provision this via Testcontainers or a lab Cassandra per runbook. This example only verifies end-to-end mapping:

~~~java
// EventRepositoryIT.java
package example.telemetry;

import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@ActiveProfiles("test")
class EventRepositoryIT {
    @Autowired EventRepository repository;

    @Test
    void readsKnownEventUsingCompositeKey() {
        EventKey key = new EventKey(
            "device-7",
            LocalDate.of(2026, 11, 21),
            Instant.parse("2026-11-21T09:00:00Z"),
            UUID.fromString("123e4567-e89b-42d3-a456-426614174001"));

        EventEntity event = repository.findById(key).orElseThrow();
        assertThat(event.getEventType()).isEqualTo("HEARTBEAT");
        assertThat(event.getPayload()).isEqualTo("ok");
    }
}
~~~

**To keep tests genuinely independent**:

1. CI spins up the **approved Cassandra version** in an isolated network, never using production contact points.
2. Run DDL/keyspace/schema and seed data **before the Spring context requires repositories**; with Testcontainers, configure dynamic properties/service connections for the exact version.
3. Use `application-test.yml` with the **container's actual DC**, an RF matching node count, and the tested consistency level. A single-node RF=1 Cassandra cannot replace an RF=3 quorum test.
4. Enable auth/TLS in a dedicated suite if production requires it; verify read-only roles are denied writes.
5. Confirm tests ran against the **real dependency graph**, not just a mocked `EventRepository`.

### 18.3. Mandatory Behavioral Test Suite

~~~text
[ ] Spring context creates the exact single CqlSession/mapper/template needed.
[ ] dev/staging/prod/test profiles point to the right cluster/DC; missing secret fails fast.
[ ] Schema/table exist; composite key mapping matches all 4 components.
[ ] INSERT/SELECT via CQL partition lookup returns expected values and event_time.
[ ] Queries spanning UTC midnight read two buckets without dropping events.
[ ] Queries with small LIMIT/page return the contractual row count.
[ ] Verify null/unset/TTL and deletes do not create unexpected tombstones.
[ ] Read/write timeout and Unavailable are not converted into empty results.
[ ] Write retries reuse a stable key; no random UUID generated per attempt.
[ ] RF=3/LOCAL_QUORUM is tested on a genuine multi-replica topology.
[ ] TLS peer/cert/credential/role allow and deny work properly.
[ ] Java Driver core/codec/Spring Data are compatible with no runtime linkage errors.
~~~

## 19. Upgrading Spring Boot 2.x → 3.x → 4.x: Controlled Layer-by-Layer Changes

### 19.1. Upgrading from Boot 2.x to 3.x

Changes often extend well beyond Cassandra:

- Boot 3 requires **Java 17+** and Spring Framework 6; web/validation/security apps use **`jakarta.*`** instead of many legacy `javax.*` APIs.
- Spring Data Cassandra moves from the **3.x line to 4.x** per the corresponding release train/BOM.
- The Cassandra config prefix **`spring.data.cassandra.*` in Boot 2.x** may need to move to **`spring.cassandra.*` in Boot 3.x**; verify every property and effective config.
- Clean up explicit overrides and stale transitive dependencies; never force an old driver JAR just to make missing classes "reappear".
- Test `CqlSession`, repositories, custom converters, `@PrimaryKeyColumn`, reactive return types, and Actuator health.

### 19.2. Upgrading from Boot 3.x to 4.x

This is a **major migration**: you must read the release notes/migration guide for the specific Boot 4 version, verify the corresponding Spring Framework 7/Spring Data versions, Java baseline, starter/module names, config properties, transaction/observability/security APIs, and **driver/BOM**. Never assume "bumping `<version>` is enough" or keep all 3.x properties without testing.

### 19.3. Compatibility Matrix to Lock Down for Every Change

~~~text
Change ID:
Current Boot exact patch:
Target Boot exact patch:
Spring Framework resolved:
Spring Data Cassandra resolved:
Cassandra Java Driver core resolved:
Mapper/metrics/reactive modules resolved:
JDK build:
Cassandra server source/target version:
Native protocol/feature requirements:
Active contact points and local DC:
Keyspace RF by DC and chosen CL:
Security/TLS/secret references:
Integration/load/recovery tests:
Rollback/restore conditions:
~~~

**Do not upgrade Cassandra server major and Spring Boot/Driver major simultaneously** unless there is a compelling reason and a rehearsed rollback/recovery plan. Isolating changes helps pinpoint regressions and avoids incompatible binary/SSTable/schema states after an upgrade.

## 20. Diagnosing Common Failures After Adding the Starter

| Symptom | Plausible Hypothesis | Check / Remediation |
| --- | --- | --- |
| Spring does not create `CqlSession` bean | Missing starter, excluded auto-config, custom bean, or another classpath condition. | Check condition evaluation report, dependency tree, and bean graph. |
| `NoHostAvailable`/session init fails | Wrong contact points, port/firewall, DC metadata, TLS/auth, or nodes down. | Check network, local DC, handshake, and node status. |
| `AuthenticationException` | Cluster requires auth; wrong credentials/role/secret. | Check auth provider, secret version, credential rotation; never switch to superuser. |
| `Unauthorized` on SELECT | Role lacks table/keyspace permissions. | Grant minimal `GRANT SELECT`, test allow/deny. |
| Query reports missing table/keyspace | Default keyspace or schema migration not run, wrong identifier. | `DESCRIBE KEYSPACE/TABLE`, compare entity/table mapping. |
| Repository mapping exception | `timestamp/date/uuid` type mismatch, renamed column, UDT/codec drift. | Compare CQL schema and Java mapping; run integration tests. |
| `NoSuchMethodError`/linkage error | Inconsistent Spring Data/Driver/codec versions from override/transitive conflict. | Inspect **resolved dependency graph**; revert to BOM/supported versions. |
| Prod profile still connects to dev | Wrong `spring.profiles.active`, property precedence, or env fallback. | Fail-fast expected cluster/DC; audit redacted effective config. |
| `LOCAL_QUORUM` reports `Unavailable` on 1-node lab | Incompatible RF/replica count. | Use proper test topology or intentionally set lab RF/CL; do not blame the driver. |
| p99 increases after adding repository | Query projection, N+1, paging, TTL/tombstones, or mapping/GC. | Compare actual CQL and bytes, measure client/server, benchmark fairly vs Core full/narrow. |
| App reports `UP` but endpoints time out | Health query too narrow; hot partition/slow replica. | Functional canary, partition metrics, latency/compaction/GC. |
| Write timeout followed by duplicate data | Retry generated new event ID or non-idempotent mutation. | Stable key, durable retry/reconciliation, and timestamp/TTL policy. |

### 20.1. Structured Debugging Flow

~~~mermaid
flowchart TD
    A["Spring Boot Cassandra error"] --> B{"Cannot create CqlSession?"}
    B -->|Yes| C["Starter/BOM, properties, TLS/auth, DC/contact points"]
    B -->|No| D{"Repository/mapper/CQL error?"}
    D -->|Yes| E["CQL schema, @PrimaryKey, converters, driver version"]
    D -->|No| F["Measure API/driver p99, queue, retries, rows/bytes"]
    F --> G{"Replica/compaction/disk/tombstone bottleneck?"}
    G -->|Yes| H["Fix data model, shed load, storage/repair per runbook"]
    G -->|No| I["Check mapping/GC, query fan-out, network/TLS"]
    C --> J["Integration test + canary"]
    E --> J
    H --> J
    I --> J
    J --> K{"SLO, security, and correctness met?"}
    K -->|No| L["Controlled rollback of config/artifact"]
    K -->|Yes| M["Gradual rollout, record evidence"]
~~~

## 21. Effective Configuration: Valid YAML Does Not Mean the Driver Received the Value

A project can contain three configuration sources:

1. **Spring Boot's** `application.yml`, `application-*.yml`, system properties, environment variables, Config Server/secret store.
2. **Java Driver's** `application.conf`/HOCON and `DriverConfigLoader`.
3. Application-defined `@Bean` customizers, `CqlSessionBuilder`, or custom `CqlSession`.

Do not guess precedence for every option merely by reading one file. Depending on version and customizers, one property may be translated by Boot into a driver option while another is overridden by a custom loader. **Define a single authoritative owner per option and write a test verifying effective runtime values.**

### 21.1. Configuration Ownership Matrix

| Parameter | Recommended Owner | Verification Method |
| --- | --- | --- |
| Expected cluster/environment | Deployment config and app startup guard. | Compare `system.local`/driver metadata; fail readiness on mismatch. |
| Contact points, port, local DC | **Version-appropriate** Spring Boot Cassandra properties. | Connection diagnostics, DC metadata, and network policy. |
| Keyspace name | Spring Boot + DDL provisioning. | Query schema and entity mapping; no prod auto-create. |
| Username/secret reference | Secret management/Boot external config. | Auth tests, rotation rehearsal; never log secret values. |
| TLS/trust/hostname policy | Security config via supported Boot/Driver mechanism. | Test valid and invalid CA/cert/hostname. |
| Request CL, timeout, page size | One clear policy: Boot or driver profile. | Effective driver config, query canary, and request tracing. |
| Pool/throttler/retry | Version-pinned driver config/profile. | Driver metrics/queues, overload tests. |
| RBAC/replication/schema | Cassandra cluster/DDL migrations. | `DESCRIBE`, role allow/deny, nodetool, and CQL tests. |

### 21.2. Never Echo Secrets When Debugging

Log only non-sensitive values at the needed level, for example:

~~~text
service              = telemetry-api
environment          = staging
boot_version         = <resolved-version>
spring_data_version  = <resolved-version>
driver_core_version  = <resolved-version>
config_revision      = git:abcdef12
expected_cluster_id  = cassandra-staging
local_dc             = dc1
keyspace             = telemetry_spring
tls_required         = true
request_profile      = interactive
~~~

**Never log:** passwords, private keys, tokens, raw truststore/keystore contents, raw payloads, or CQL containing literal user data. Actuator config endpoints must also be protected and have sensitive values masked; never expose `/actuator/env` or `/actuator/configprops` publicly.

### 21.3. Checklist When Migrating Properties

When migrating `spring.data.cassandra.*` to `spring.cassandra.*`:

1. Inventory all current config keys **without dumping production secrets**.
2. Cross-check each key's name/type/default/unit against the **new Boot version's configuration metadata**.
3. Create a test configuration missing a required variable and confirm the app **fails fast**.
4. Create a test with a wrong `local-datacenter` and confirm the app **does not silently** accept the wrong cluster.
5. Compare effective request timeout, CL, page size, auth/TLS, and bean graph against the baseline.
6. Run load tests with production-like data, change as few variables at a time as possible, canary, and keep rollback ready.

A **migration helper** (if provided by Spring Boot in the relevant version) only helps spot some renamed properties; it does not replace behavioral compatibility tests, and temporary helpers should not remain in production dependencies indefinitely.

## 22. Case Study: Overridden Dependency and Queries Suddenly Failing

### 22.1. Simulated Context

An application runs Boot 3.x with the BOM managing Spring Data Cassandra and the Java Driver. An internal library asks for a different driver feature, so a developer forces `java-driver-core` to a newer patch, **without aligning** companion driver modules. CI builds cleanly, but an endpoint using a custom codec/mapper throws `NoSuchMethodError` under traffic.

| Milestone | Observation | Hypothesis to Verify |
| --- | --- | --- |
| T0 | POM changed only one Driver version line. | The build graph may still contain other driver modules at an older version. |
| T1 | Unit tests mocking repositories all pass. | Mocks do not load the full native driver/codec runtime. |
| T2 | Spring Boot application context boots. | Does not prove all query/codec paths were exercised. |
| T3 | `GET /events` fails with linkage error on a rare data shape. | Possible version mismatch or old/new API incompatibility. |
| T4 | Developer increases Cassandra request timeout. | Cannot fix a JVM method linkage error. |

### 22.2. Proper Investigation Steps

1. Capture the **stack trace/failing class**, keeping sensitive CQL literals out of logs.
2. Inspect the **resolved runtime dependency tree/SBOM**, not just directly declared dependencies.
3. Compare `java-driver-core`, mapper/metrics/reactive modules, and Spring Data Cassandra against the **BOM of the running Boot patch**.
4. Try removing the override to return to BOM-pinned dependencies; if an override is mandatory for security, pick a **compatible artifact set** and run integration tests.
5. Test startup, CQL/codecs/custom types, auth/TLS, paging, and load on production-like staging.
6. Canary a subset of pods, watch errors/p99; roll back artifacts on regression.

**Do not assume every `NoSuchMethodError` is the Driver's fault**, as it may involve Spring Framework/Reactor/Jackson/other extensions. However, right after a dependency change, the first step is **verifying actual classpath/runtime linkage**, not enlarging the Cassandra pool or adding retries.

### 22.3. Another Case: Boot Starts Up, Yet Repository Reads the Wrong Keyspace

A staging service has `spring.cassandra.keyspace-name=telemetry_spring` in `application.yml`, while custom code creates a separate `CqlSession` with its own default keyspace; Spring Data uses Boot's session and the custom DAO uses the other. One path returns data; the other reports the table does not exist.

**Fix:** consolidate configuration under a single **Spring-managed session/identity**, use **fully qualified table names in CQL where disambiguation matters**, and check the bean graph, expected cluster/DC, and roles. Do not "fix" it by adding `USE` statements or spinning up new sessions per request.

## 23. Common Anti-Patterns

| Anti-Pattern | Consequence | Right Approach |
| --- | --- | --- |
| Copying `spring.data.cassandra.*` from Boot 2.x to 3.x unchecked. | Properties may fail to bind; runtime uses wrong defaults. | Check version-specific configuration metadata and test effective config. |
| Setting arbitrary `<version>` tags on Spring Data and Driver when using Boot BOM. | Dependency drift and runtime linkage/codec bugs. | Prefer the BOM; make targeted overrides with integration tests. |
| Assuming Spring Data 4.4 means Cassandra server 4.4. | Wrong server/Driver support matrix selection. | Separate the four version axes: Boot, Data, Driver, server. |
| Setting `local-datacenter` to an arbitrary cloud region name. | Wrong-DC routing/connection failures. | Use the DC name from snitch metadata. |
| Using a 1-node lab with RF=3 and expecting `LOCAL_QUORUM` to survive node down. | Not enough real natural replicas. | Test proper topology/CL; distinguish lab RF from production RF. |
| Treating a single `repository.save` as a multi-table transaction. | Partial writes/data drift. | Durable mutation log/CDC/reconciliation. |
| Assuming `@Table` is enough to create production tables. | Missing schema or schema drift. | Versioned schema migrations with a separate role. |
| Assuming derived repository queries optimize any `WHERE`. | Missing partition key, full scans, or rejected queries. | Design tables per query and inspect emitted CQL. |
| Calling `findAll()` to fetch millions of entities and filtering in Java. | Spikes in I/O, heap, GC, and p99. | Bounded partition/range lookups, rollups, or projections. |
| Assuming `LIMIT 100` means the server reads at most 100 cells. | Ignores tombstone/SSTable scan costs. | Benchmark server read cost, TTL/delete/compaction. |
| Calling `block()` on a reactive `Flux` inside a Netty event-loop. | Loses nonblocking benefits, starves the event loop. | End-to-end reactive or isolated bounded scheduler. |
| Creating a new `CqlSession` per request in Spring Boot. | Connection churn, TLS/auth/metadata overhead. | Inject singleton/managed session. |
| App auto-runs `DROP/CREATE` schema on restart. | Data-loss/race risk and overly broad app privileges. | Migration pipeline with approval/backup/rollback. |
| Using production credentials in dev and disabling TLS verification. | Data exposure and uncontained blast radius. | Per-environment identities/TLS/secrets. |
| Treating Actuator `UP` as proof all replicas/quorum are healthy. | Misses hot partitions and corrupt/stale data. | Functional canary + server metrics + correctness tests. |
| Increasing timeouts to cure `NoSuchMethodError` or `Unauthorized`. | Masks the cause without fixing the error. | Properly classify JVM/classpath, auth, and Cassandra failures. |

## 24. Self-Check Exercises with Answers

**Exercise 1.** A Spring Boot 3.x app configures `spring.data.cassandra.contact-points` from a Boot 2.x guide and fails to connect as expected. What is the most important check?

**Answer:** Check the **configuration metadata/prefix for the running Boot patch**, typically `spring.cassandra.*` on Boot 3.x, then verify effective contact points, local DC, and the bean graph. Do not simply increase timeouts.

**Exercise 2.** Does Spring Boot 3.4.x with Spring Data Cassandra 4.4.x mean the Cassandra cluster must run server 4.4.x?

**Answer:** **No.** Spring Data's version is for the Java library; Cassandra server is a separate project. Choose per the driver/native protocol support matrix and schema/feature requirements.

**Exercise 3.** A developer upgrades `java-driver-core` alone while leaving mapper/metrics modules old, then sees `NoSuchMethodError`. How should this be investigated?

**Answer:** Inspect the **resolved dependency graph/SBOM**, Boot BOM, companion Driver modules, and Spring Data; remove or align the override after verification and run integration tests. Do not assume it is a Cassandra compaction bug.

**Exercise 4.** Why can't `spring.cassandra.local-datacenter` simply be filled with a cloud region name?

**Answer:** The driver needs the **datacenter name reported by the cluster/snitch**, not an arbitrary region string. A wrong DC can exclude nodes from local routing or increase cross-DC latency.

**Exercise 5.** Given `PRIMARY KEY ((device_id,event_day),event_time,event_id)`, a `@PrimaryKeyClass` only marks `device_id` as the partition key. Is the mapping correct?

**Answer:** **No.** `event_day` is the second component of the partition key; `event_time,event_id` are clustering columns. Ordinals and types must match the actual DDL.

**Exercise 6.** An API needs events from 23:45 UTC on Nov 20 to 00:15 UTC on Nov 21. The service calls `findWindow` for Nov 20 and returns the result. What is missing?

**Answer:** It must also read the **Nov 21 bucket**, merge by time/tie-breaker, apply a global limit/pagination, and bound fan-out. A query with a fixed `event_day` reads only one daily partition.

**Exercise 7.** With RF=3 and `LOCAL_QUORUM` in `dc1`, how many full replicas must respond?

**Answer:** **Two**. This does not prove all replicas are synchronized, nor does it replace repair.

**Exercise 8.** A staging cluster has only one node, yet the keyspace has RF=3 and the client uses `LOCAL_QUORUM`. Why might tests fail?

**Answer:** Available full replicas do not satisfy the required quorum. Use a proper multi-node topology for resilience tests or intentionally set lab RF/CL, rather than arbitrarily lowering production consistency.

**Exercise 9.** Calling `repository.save` on an entity populated with only two columns while other fields are `null`: is it guaranteed to update only those two columns?

**Answer:** **Not guaranteed.** Nulls may be written as tombstones or ignored depending on Spring Data mapping/configuration. Use an explicit column-level update statement or verify the null/unset strategy before writing.

**Exercise 10.** Does a Spring Data Cassandra repository provide transactions/dirty checking like JPA Hibernate?

**Answer:** **Not by default.** Cassandra has its own mutation/batch/LWT semantics; mutating a Java object does not auto-persist to the DB, and multi-table operations do not become relational ACID transactions just because a repository is used.

**Exercise 11.** `CassandraRepository.findAll()` returns millions of rows and the app calls `stream().filter(...)` after loading. What is wrong?

**Answer:** Cassandra may have to scan/transfer huge numbers of partitions/bytes; the app retains entities and triggers GC pressure. Design **query-driven tables** with full partition keys and clustering ranges/limits.

**Exercise 12.** Spring Boot manages one `CqlSession`, yet a service creates another session on every HTTP request. What are the risks?

**Answer:** Connection churn, metadata/TLS/auth overhead, and divergent CQL configurations. Inject the Spring-managed `CqlSession`; create multiple sessions only when genuinely connecting to distinct logical clusters/identities.

**Exercise 13.** `/actuator/health` returns UP while an API reading a hot partition has an 8-second p99. Is this contradictory?

**Answer:** **No.** Health may only check connectivity or a lightweight query, whereas a specific partition suffers from disk/tombstones/compaction/GC. Workload-representative canary queries and both client/replica metrics are needed.

**Exercise 14.** Does adding `spring-boot-starter-data-cassandra-reactive` automatically make all blocking repositories reactive and make CQL faster?

**Answer:** **No.** You must use version-appropriate reactive repositories/templates, avoid blocking the event-loop, and manage demand/concurrency. Server query cost still depends on data model, CL, and resources.

**Exercise 15.** Why should `application-prod.yml` never contain Cassandra passwords or fall back to a dev `local-datacenter`?

**Answer:** Secrets can leak via source control, and wrong-environment fallbacks can touch the wrong cluster/DC. Use a secret manager, fail-fast checks, a startup guard, and per-environment TLS/roles.

**Exercise 16.** Unit tests mocking `EventRepository` pass after upgrading Boot/Driver. Does that prove native protocol/mapper/DDL compatibility?

**Answer:** **Not yet.** Mocks never talk to Cassandra. You need integration tests against a real cluster/version/schema or isolated container covering CQL/CL/auth/TLS, paging, and failure modes.

**Exercise 17.** An API only needs `event_time,event_type`, but the repository reads a 200 KiB/row `payload`. What should be examined first?

**Answer:** Reduce **column projection/bytes** via CQL/DTO or a query-driven summary table, then benchmark. Switching mapping libraries while still selecting the large payload may not solve the bottleneck.

**Exercise 18.** A team wants to change the partition key from `device_id` to `(device_id,event_day)` by editing `@PrimaryKeyClass` and deploying. Is that enough?

**Answer:** **No.** The partition key governs token placement/replicas and CQL schema. You must create a new table, backfill/catch up mutations, handle TTL/deletes, reconcile, and follow a canary/rollback procedure.

## 25. Operations Checklist and Decision Diagram

~~~text
VERSION / DEPENDENCY
[ ] Choose a supported Spring Boot patch release and record exact JDK.
[ ] Follow the BOM; record resolved Spring Data Cassandra, Java Driver, and modules.
[ ] Never force individual artifacts without compatibility tests.
[ ] Review migration guides when moving Boot 2.x -> 3.x -> 4.x.
[ ] Verify Cassandra server/native protocol/feature support.

CQL / DATA MODEL
[ ] Keyspace NTS/RF per DC; tables/projections match query shapes.
[ ] Composite partition/clustering keys in @PrimaryKeyClass match CQL.
[ ] event_day computed consistently in UTC with bounded time windows.
[ ] LIMIT/column projection/page/byte budgets and fan-out are bounded.
[ ] Schema migrations are never executed by the production app role.

SPRING / SESSION
[ ] Correct blocking or reactive starter for the application model.
[ ] application.yml profiles match the Boot version; no stale ignored properties.
[ ] One Spring-managed CqlSession per logical cluster/identity.
[ ] Inject repositories/templates/sessions; never create sessions per request.
[ ] Effective local DC, CL, timeout, throttler, and page size verified.

SECURITY / ENVIRONMENT
[ ] Dev/staging/prod have separate clusters, roles, networks, secrets, and certs/CAs.
[ ] TLS server peer validation enabled per policy; no trust-all.
[ ] Secret manager credentials support rotation and fail closed.
[ ] App never uses superuser; CQL RBAC and tenant authorization enforced.
[ ] Startup guard rejects expected cluster/DC mismatches.

TEST / OBSERVABILITY / RELEASE
[ ] Integration tests run against real Cassandra with provisioned schema.
[ ] RF/CL, TTL/deletes, null/unset, paging, and large payloads tested.
[ ] Startup failure, auth/TLS failure, and dependency linkage errors tested.
[ ] API p95/p99, driver in-flight/retries/queues, JVM GC, and disk/compaction monitored.
[ ] Actuator health does not replace functional canaries/data correctness tests.
[ ] Canary per instance group, with stop criteria and artifact/config rollback.
~~~

~~~mermaid
flowchart TD
    A["Spring Boot app needs Cassandra"] --> B["Pick Boot/JDK and use BOM"]
    B --> C["Verify Spring Data + Driver + server compatibility"]
    C --> D["Create keyspace/tables per query, RF/DC, and CL"]
    D --> E["Configure spring.cassandra.*, TLS, roles, and Spring profiles"]
    E --> F["Map @PrimaryKeyClass/@Table + Repository/Template"]
    F --> G["Use managed CqlSession for specialized CQL if needed"]
    G --> H["Integration tests, dependency graph, paging, auth, and failover"]
    H --> I{"Correctness + SLO + security met?"}
    I -->|No| J["Fix version/config/query/permissions and re-test"]
    J --> C
    I -->|Yes| K["Production canary and monitor JVM/driver/replicas"]
    K --> L["Keep rollback ready; expand rollout when stable"]
~~~

**Summary:** integrating Cassandra in Spring Boot requires coordinating the **Spring Boot BOM, Spring Data Cassandra, Java Driver, and Cassandra server version**, rather than just adding a starter and setting contact points. On Boot 3.x, configuration typically uses **`spring.cassandra.*`**, with separated dev/staging/prod profiles, verified local DC, TLS, secrets, RF/CL, and a single long-lived managed `CqlSession`. `CassandraRepository`/`CassandraTemplate` reduce boilerplate but **do not replace partition keys, clustering keys, TTL/tombstones, quorum, repair, or query cost control**. A version matrix is a starting guide; **the BOM/resolved dependency graph and integration tests on the exact patch release are the real proof of compatibility**. Safe deployment always requires versioned schemas, correctness verification, p99/resource monitoring, canarying, and a clear rollback plan.
