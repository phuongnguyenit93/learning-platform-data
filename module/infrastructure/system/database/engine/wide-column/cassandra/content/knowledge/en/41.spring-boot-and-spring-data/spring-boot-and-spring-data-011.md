# Optimistic Locking via `@Version` and Conditional Updates

## 1. Scenario: Two People Edit the Same Configuration — Who Wins?

A Spring Boot service manages device operating modes in **Apache Cassandra**. Administrators A and B both open the settings screen for `device-7`, and both see mode `AUTO`. A switches it to `MAINTENANCE`, while B switches it to `MANUAL`. If the backend runs a `SELECT`, mutates the Java object, and runs a normal `UPDATE`, both writes succeed; one change overwrites the other under Cassandra's mutation reconciliation rules with zero conflict notification to the users.

~~~mermaid
sequenceDiagram
    participant A as Admin A
    participant B as Admin B
    participant API as Spring Boot API
    participant DB as Cassandra
    A->>API: GET device-7
    API->>DB: SELECT mode, version
    DB-->>A: AUTO, version=7
    B->>API: GET device-7
    API->>DB: SELECT mode, version
    DB-->>B: AUTO, version=7
    A->>API: PUT MAINTENANCE, expectedVersion=7
    API->>DB: UPDATE ... IF version=7
    DB-->>API: applied=true, version=8
    API-->>A: Success, version=8
    B->>API: PUT MANUAL, expectedVersion=7
    API->>DB: UPDATE ... IF version=7
    DB-->>API: applied=false
    API-->>B: Conflict; reload version=8
~~~

In this scenario, the goal is **no silent lost updates**. A is accepted; B's request must learn the data changed, reload, and decide what to do next. This is **optimistic concurrency control**.

In Spring Data Cassandra, a Java property annotated with **`@Version`** enables automatic stale-entity detection on save, backed by Cassandra's **lightweight transactions (LWT)**. You can also write explicit CQL `INSERT ... IF NOT EXISTS`, `UPDATE ... IF version = ?`, and `DELETE ... IF version = ?` and inspect **`[applied]`**. Both approaches add coordination work and are not free magic.

This lesson belongs to the **Spring Boot and Spring Data** chapter of the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module, connecting the wide-column model, partition keys, replicas/coordinators, read/write consistency, Java operations, and production error handling.

**Learning Objectives:**

1. Recognize *lost updates* during read–modify–write in Cassandra and understand why timestamps/LWW cannot replace version checks.
2. Understand `@Version`, new-entity detection, `IF NOT EXISTS`, `IF version = ?`, and `OptimisticLockingFailureException`.
3. Write conditional CQL targeting the **full primary key** and inspect `[applied]` instead of relying solely on HTTP status.
4. Distinguish LWT's **regular consistency** (`LOCAL_QUORUM`) from **serial consistency** (`SERIAL`/`LOCAL_SERIAL`).
5. Use Spring Boot, Spring Data repositories/templates, or Java Driver 4.x to implement explicit conflict detection.
6. Design HTTP `If-Match`/ETag preconditions, case-aware retries, idempotency, and 409/412 responses without losing data.
7. Evaluate Paxos overhead, hot partitions, TTL/tombstones, multi-DC semantics, and run real concurrency tests.

> **Scope:** examples use Spring Boot 3.x, Spring Data Cassandra 4.x, Java Driver 4.x, and Cassandra with `NetworkTopologyStrategy`, full replicas, and DC `dc1`. Exact API names, patch versions, Paxos features, metrics, and behaviors must be verified against your running versions. Never test in production without proper tests, permissions, and runbooks.

## 2. What Does Optimistic Locking Protect?

### 2.1. Three Ways to Handle Concurrent Writes

| Approach | Possible Outcome | When Appropriate |
| --- | --- | --- |
| **Unconditional `UPDATE`** | One mutation wins per Cassandra's timestamp/cell semantics; callers may never know their read was stale. | Overwritable data, idempotent events/upserts, or an external authoritative ordering source. |
| **CQL `IF version = ?`** | Mutates only if the row's version still matches the expected value; returns `[applied]`. | Single-row / narrow read–modify–write needing lost-update detection. |
| **Spring Data `@Version`** | Repository/template checks and increments version on save; mismatches throw an exception. | Spring Data CRUD entities requiring single-row concurrency control. |
| **External pessimistic/distributed lock** | Acquires a lock before mutating; needs leases, fencing, and failure recovery. | Specialized workflows; avoid by default due to high operational complexity. |

In Cassandra, **last-write-wins (LWW)** by cell timestamp does not mean "the later HTTP request always wins" in application wall-clock terms. Timestamps can be coordinator- or client-supplied; replays, clock skew, and tombstones affect reconciliation. Never compare timestamps after writing to detect whether two admins conflicted.

### 2.2. Optimistic Locking Does Not Lock a Row Across an HTTP Request

An app might read `version=7`, wait three minutes while a user edits a form, and then submit. **No lock is held during those three minutes.** On save, Cassandra checks the condition at LWT execution time; if the version is no longer 7, the write is rejected.

That is why it is called "optimistic": most of the time writers do not collide, so concurrent reads are unblocked and conflicts are caught at write time. In exchange, **every conditional mutation** pays Paxos coordination cost even when uncontested.

### 2.3. Single-Entity Consistency Scope

Spring Data Cassandra officially documents `@Version` as supporting **single-entity operations**, **not batch operations**. It does not turn an operation touching two tables, two partitions, or multiple CQL statements into a multi-row ACID transaction.

~~~text
Supported logical use case:
  Read one device_settings row -> change mode -> save if version matches.

NOT automatically atomic:
  Save device_settings row
  + append audit row
  + publish Kafka event
  + update secondary projection
~~~

If two tables must reflect the same change, design a **durable event/outbox at an appropriate source, CDC/reconciliation, or idempotent projection updater**. An LWT on the settings table never creates a transaction spanning Kafka or other tables.

## 3. LWT and Paxos: Conditions Are Checked at Replicas, Not in Java

### 3.1. How Does This Differ from an `if` in the Service?

Anti-pattern:

~~~java
DeviceSetting setting = repository.findById(key).orElseThrow();
if (setting.getVersion().equals(expectedVersion)) {
    setting.setMode(newMode);
    repository.saveWithoutVersionCondition(setting); // Hypothetical API: anti-pattern
}
~~~

`saveWithoutVersionCondition` is a **hypothetical name illustrating the bug**, not a real Spring Data API. Between `SELECT` and `UPDATE`, another writer can mutate the row, so **checking in Java memory is insufficient**. The condition must travel **inside the mutation** to Cassandra.

~~~mermaid
flowchart TD
    A["Client sends UPDATE ... IF version=7"] --> B["Coordinator receives conditional mutation"]
    B --> C["Replicas run LWT/Paxos consensus phase"]
    C --> D{"Is version still 7?"}
    D -->|Yes| E["Propose/accept new mutation; version=8"]
    D -->|No| F["Do not apply; report conflict"]
    E --> G["Return applied=true once applied per CL"]
    F --> H["Return applied=false"]
~~~

This diagram is a **conceptual model**: phase counts, round-trips, fast paths, and Paxos mechanics vary by Cassandra version, contention, and topology. Do not assert a fixed round-trip count across all releases. The key point: condition evaluation uses **consensus across eligible replicas**, never an arbitrary single-replica read followed by an overwrite.

### 3.2. `IF NOT EXISTS`, `IF EXISTS`, and `IF version` Differ

| Condition | Primary Guarantee | Does Not Guarantee |
| --- | --- | --- |
| `INSERT ... IF NOT EXISTS` | Creates only if the target row does not exist per conditional semantics. | Does not create transactions with other rows/tables; cannot blindly retry with a new ID. |
| `UPDATE ... IF EXISTS` | Modifies only if the row exists. | **Does not detect** another writer modifying the row concurrently; both updates can succeed back-to-back. |
| `UPDATE ... IF version=7` | Modifies only if version matches expectation. | Cannot protect versions if another writer bypasses it without incrementing `version`. |
| `DELETE ... IF version=7` | Deletes only while the row still has version 7. | Does not stop another workflow from deleting and recreating unconditionally. |

**`IF EXISTS` is not full optimistic locking**: it checks existence only, not specific state. `IF version = ?` is row/condition-scoped *compare-and-set* (CAS).

### 3.3. Serial Consistency and Regular Consistency Are Two Distinct Choices

For conditional mutations, Cassandra has two consistency dimensions:

- **Serial consistency** (`SERIAL` or `LOCAL_SERIAL`) governs the consensus scope for the conditional/Paxos phase.
- **Regular consistency** (e.g., `LOCAL_QUORUM`) governs response/applied-visibility requirements for the regular write phase.

Never use `SERIAL` as a synonym for `LOCAL_QUORUM`. Never call `LOCAL_QUORUM` "optimistic locking": a `LOCAL_QUORUM` write **without `IF`** is still an unconditional write.

## 4. Lab CQL: One Settings Row per Tenant and Device

### 4.1. Keyspace and Partition Key

Assume a lab with **three full replicas in `dc1`**; run these with schema-creation privileges in the lab:

~~~sql
CREATE KEYSPACE IF NOT EXISTS telemetry_locking
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

CREATE TABLE IF NOT EXISTS telemetry_locking.device_settings (
  tenant_id text,
  device_id text,
  mode text,
  updated_at timestamp,
  updated_by text,
  version bigint,
  PRIMARY KEY ((tenant_id, device_id))
);
~~~

**Key choice:** `(tenant_id, device_id)` is a composite **partition key**; each tenant–device pair forms a single-row configuration partition. Cassandra hashes the full composite key for token routing and natural replica placement. Reading one device's settings requires both key components, avoiding `SELECT *` or cluster-wide `mode` scans.

This example does not replace wide-column event timeline tables; it illustrates a small **keyed state-update table** where LWT performance is predictable. If a row carries huge collections/hotspots or updates thousands of times per second per device, LWT itself becomes a bottleneck.

`version bigint` is a CQL data column maintained by the app/mapper. Cassandra **never auto-increments `version`** on normal `UPDATE`s, so every write path must enforce it consistently.

### 4.2. Setting Consistency in `cqlsh`

~~~sql
-- These are cqlsh commands, NOT CQL sent from Java Driver.
CONSISTENCY LOCAL_QUORUM;
SERIAL CONSISTENCY LOCAL_SERIAL;
~~~

With RF=3 full replicas in `dc1`, `LOCAL_QUORUM` typically needs two responses. `LOCAL_SERIAL` scopes the serial phase to the local DC per version semantics. If **multiple DCs allow contending writes to the same key**, never assume `LOCAL_SERIAL` in each DC provides global ordering: evaluate `SERIAL` and the latency/correctness trade-offs of multi-DC design.

Check **`cqlsh` syntax and serial consistency support** for your Cassandra version (`HELP` in `cqlsh`). In Java Driver, both CLs are configured independently on statements/profiles.

## 5. CQL Practice: Conditional Create, Update, Conflict Rejection, and Delete

### 5.1. Create Only If Absent

~~~sql
INSERT INTO telemetry_locking.device_settings
  (tenant_id, device_id, mode, updated_at, updated_by, version)
VALUES
  ('tenant-a', 'device-7', 'AUTO',
   '2026-11-21T09:00:00Z', 'operator-a', 0)
IF NOT EXISTS;
~~~

A successful conditional mutation normally returns column **`[applied]` = true**. Repeating the statement on the same key returns **`[applied]` = false** once the row exists, instead of upserting.

~~~text
Attempt 1 (empty lab):
  [applied] = true

Attempt 2 (same primary key):
  [applied] = false
  Result may also contain current column values.
~~~

Do not assume the extra columns returned on failure always share the exact same shape across versions; Java code should check the **applied flag** and perform a controlled re-read if current state is needed.

### 5.2. Update with Version Check

~~~sql
UPDATE telemetry_locking.device_settings
SET mode = 'MAINTENANCE',
    updated_at = '2026-11-21T09:01:00Z',
    updated_by = 'operator-a',
    version = 1
WHERE tenant_id = 'tenant-a'
  AND device_id = 'device-7'
IF version = 0;
~~~

When the row holds `version = 0`, the mutation applies and `version` becomes `1`. Re-running the exact same statement yields `[applied] = false` because `version` is no longer `0`.

~~~sql
SELECT tenant_id, device_id, mode, version, updated_at, updated_by
FROM telemetry_locking.device_settings
WHERE tenant_id = 'tenant-a'
  AND device_id = 'device-7';
~~~

**Never check `version` with a `SELECT` and then send an `UPDATE` without `IF`.** The window between the two requests still harbors a race condition.

### 5.3. Same Version, Two Writers

Suppose B has not seen A's update yet and submits:

~~~sql
UPDATE telemetry_locking.device_settings
SET mode = 'MANUAL',
    updated_at = '2026-11-21T09:02:00Z',
    updated_by = 'operator-b',
    version = 1
WHERE tenant_id = 'tenant-a'
  AND device_id = 'device-7'
IF version = 0;
~~~

B's request is **not applied** because version is now 1. If B still wants to apply a change against the newer state, B must re-read, validate permissions/business rules, and submit a new request **with `expectedVersion=1, nextVersion=2`**. Never blindly bump `expectedVersion` after a failure.

### 5.4. `IF EXISTS` Is Insufficient to Prevent Lost Updates

~~~sql
-- Counterexample: both A and B can apply sequentially,
-- as long as the row still exists.
UPDATE telemetry_locking.device_settings
SET mode = 'MANUAL'
WHERE tenant_id = 'tenant-a'
  AND device_id = 'device-7'
IF EXISTS;
~~~

`IF EXISTS` prevents an update from resurrecting a deleted/absent row; it **never checks which version the user read**. Use `IF version = ?` or the equivalent business predicate when comparing state.

### 5.5. Delete with Version Check

~~~sql
DELETE FROM telemetry_locking.device_settings
WHERE tenant_id = 'tenant-a'
  AND device_id = 'device-7'
IF version = 1;
~~~

Applies only if version is still 1. `DELETE` writes a **tombstone** requiring replication/repair/compaction and a proper grace period. If you want an audit trail or must block recreating the same key, a *soft delete* with version/generation or a business tombstone table may fit better; **never assume physical deletion prevents recreation**.

### 5.6. Distinguishing CQL from SQL

| Cassandra | Interpretation |
| --- | --- |
| `INSERT` without `IF NOT EXISTS` | Upserts on the primary key; does not throw a SQL-style PK duplicate error. |
| `UPDATE` without `IF` | Creates or updates the row; does not detect lost updates. |
| `UPDATE ... IF version=?` | Conditional mutation via LWT/Paxos; must inspect `[applied]`. |
| `DELETE ... IF version=?` | Checks state before deleting; still writes a tombstone when applied. |
| `BEGIN BATCH` | Not an RDBMS multi-partition ACID transaction; does not replace `@Version`. |

**Correctness note:** examples in 5.1–5.5 assume a clean lab start. If you ran statements multiple times, `version` may have changed or the row may be deleted; reset data **in an authorized lab** before repeating tests.

## 6. Spring Boot Integration: Dependencies and Base Configuration

### 6.1. Starter and BOM

Example `pom.xml` on Spring Boot 3.x (illustrated with 3.4.x); choose your actual patch per project BOM/security policy:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example.telemetry</groupId>
  <artifactId>spring-cassandra-locking</artifactId>
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
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>
</project>
~~~

**Why avoid pinning separate Spring Data / Java Driver versions?** The Spring Boot BOM coordinates compatible libraries. Arbitrary JAR overrides can trigger class/method/codec/runtime errors even when compilation passes. On another Boot version, inspect the **resolved dependency graph** and release notes rather than assuming Cassandra server shares Spring Data's version numbers.

**`3.4.0` is an illustrative version only, not a latest recommendation or verified production patch.**

### 6.2. Connecting to Cassandra in Spring Boot 3.x

~~~yaml
# application.yml — all sensitive variables/endpoints must come from environment config.
spring:
  application:
    name: telemetry-locking-api
  cassandra:
    contact-points: ${CASSANDRA_CONTACT_POINTS}
    port: ${CASSANDRA_PORT:9042}
    local-datacenter: ${CASSANDRA_LOCAL_DC}
    keyspace-name: telemetry_locking
    username: ${CASSANDRA_APP_USER}
    password: ${CASSANDRA_APP_PASSWORD}
    schema-action: none
~~~

- `spring.cassandra.*` is the prefix for **Boot 3.x** lines; Boot 2.x may use `spring.data.cassandra.*`. Check **property metadata** for your running Boot version when upgrading.
- Enable CQL authentication matching your cluster; production requires **TLS server verification**, secret managers, and network policies — never commit passwords to Git.
- `local-datacenter` must equal the snitch's DC name, not a self-invented cloud region. Wrong values prevent routing to nodes.
- `schema-action: none` avoids auto-creating/dropping schemas at startup; migration pipelines own DDL/RF, never the API role.
- Never instantiate a `CqlSession` per HTTP request; inject the Spring-managed session bean when using Core APIs.
- Never let `application-dev.yml` fall back to production when variables are missing. Dev, staging, and prod need isolated clusters, credentials, TLS trust, and data.

### 6.3. Choosing Consistency Intentionally

For this lab, regular CL `LOCAL_QUORUM` and serial CL `LOCAL_SERIAL` are **examples**. Spring Data repositories may apply default profile/driver configs to generated statements. **Measure and verify effective settings** per version; never assume `@Version` auto-applies the right CL for every topology.

~~~hocon
# Driver 4.x example: apply via tested config loader/customization.
datastax-java-driver {
  basic.request {
    consistency = LOCAL_QUORUM
    serial-consistency = LOCAL_SERIAL
    timeout = 3 seconds
  }
}
~~~

These settings do not alter Cassandra server `read_request_timeout_in_ms` or `cas_contention_timeout_in_ms`. HOCON takes effect only when the **config loader is actually active** and not overridden by Spring/custom builders. In active-active multi-DC, consider `SERIAL` instead of defaulting to `LOCAL_SERIAL`; evaluate latency and semantics trade-offs on your exact Cassandra version.

## 7. Spring Data: Composite Keys Are a Token-Placement Contract

### 7.1. `@PrimaryKeyClass`

~~~java
// DeviceKey.java
package example.telemetry;

import java.io.Serializable;
import java.util.Objects;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyClass;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyColumn;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyType;

@PrimaryKeyClass
public class DeviceKey implements Serializable {
    private static final long serialVersionUID = 1L;

    @PrimaryKeyColumn(
        name = "tenant_id", ordinal = 0, type = PrimaryKeyType.PARTITIONED)
    private String tenantId;

    @PrimaryKeyColumn(
        name = "device_id", ordinal = 1, type = PrimaryKeyType.PARTITIONED)
    private String deviceId;

    public DeviceKey() {}

    public DeviceKey(String tenantId, String deviceId) {
        this.tenantId = tenantId;
        this.deviceId = deviceId;
    }

    public String getTenantId() { return tenantId; }
    public void setTenantId(String value) { tenantId = value; }

    public String getDeviceId() { return deviceId; }
    public void setDeviceId(String value) { deviceId = value; }

    @Override
    public boolean equals(Object o) {
        if (this == o) return true;
        if (!(o instanceof DeviceKey)) return false;
        DeviceKey that = (DeviceKey) o;
        return Objects.equals(tenantId, that.tenantId)
            && Objects.equals(deviceId, that.deviceId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(tenantId, deviceId);
    }
}
~~~

**Two `PARTITIONED` fields** form the entire partition key here, with no clustering columns. If a schema adds clustering columns, declare matching types and ordinals. A `DeviceKey` missing `tenantId` can break **tenant isolation and token routing**. Entity mapping never replaces business authorization: the service must verify the caller can access that tenant/device.

## 8. `@Version` on Entities: Spring Data Attaches Write Checks

### 8.1. Entity Mapping the CQL Table

~~~java
// DeviceSetting.java
package example.telemetry;

import java.time.Instant;
import org.springframework.data.annotation.Version;
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("device_settings")
public class DeviceSetting {
    @PrimaryKey
    private DeviceKey key;

    @Column("mode")
    private String mode;

    @Column("updated_at")
    private Instant updatedAt;

    @Column("updated_by")
    private String updatedBy;

    @Version
    @Column("version")
    private Long version;

    public DeviceSetting() {}

    public DeviceSetting(
            DeviceKey key, String mode, Instant updatedAt, String updatedBy) {
        this.key = key;
        this.mode = mode;
        this.updatedAt = updatedAt;
        this.updatedBy = updatedBy;
        // For a new entity, use null so Spring Data detects it as new.
        this.version = null;
    }

    public DeviceKey getKey() { return key; }
    public void setKey(DeviceKey value) { key = value; }

    public String getMode() { return mode; }
    public void setMode(String value) { mode = value; }

    public Instant getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(Instant value) { updatedAt = value; }

    public String getUpdatedBy() { return updatedBy; }
    public void setUpdatedBy(String value) { updatedBy = value; }

    public Long getVersion() { return version; }
    public void setVersion(Long value) { version = value; }
}
~~~

**Key import details to check:**

- `@Version` is **`org.springframework.data.annotation.Version`**, not JPA's `jakarta.persistence.Version`. Using the wrong annotation silently disables Spring Data Cassandra version checks.
- `Long` is a **nullable wrapper**, fitting Spring Data's convention: `null` signals a new entity, initialized to `0` on successful insert. New-entity detection also depends on `Persistable` if implemented.
- `@Column("version")` requires a CQL `version bigint` column. Never use a `counter` column for `@Version`.
- After successful conditional updates, version steps `0 → 1 → 2...`; rejected updates must be handled as **conflicts**, not successful writes.
- Entities map Cassandra rows, **not** a JPA persistence context with automatic dirty checking.

### 8.2. Version Lifecycle

~~~mermaid
stateDiagram-v2
    [*] --> New: version == null
    New --> Stored0: INSERT IF NOT EXISTS applied
    New --> Conflict: Row already exists
    Stored0 --> Stored1: UPDATE IF version=0
    Stored0 --> Conflict: Another writer bumped version
    Stored1 --> Stored2: UPDATE IF version=1
    Stored1 --> Conflict: Stale snapshot used
    Conflict --> Reload: Return 409/412; user decides again
    Reload --> Stored2: Retry if still valid
~~~

This diagram models the nullable `Long` flow, **not a complete retry policy**. If a row is deleted and recreated, version resets; if business logic must prevent ABA anomalies, add an **immutable generation/incarnation ID or lifecycle tombstones** rather than relying solely on version counters.

### 8.3. `@Version` Is a Row Field, Not `writetime`

| `version bigint` | CQL Write Timestamp |
| --- | --- |
| Maintained by app/framework as a **logical sequence number** on conditional writes. | Microsecond timestamp used by Cassandra storage semantics for cell reconciliation. |
| Checked via `IF version = ?`. | Determines winning cells and tombstone precedence. |
| Incremented per business contract; not a timestamp. | Not a reliable count of "user edits". |
| Can be corrupted if a writer bypasses and omits incrementing it. | Affected by clock skew, custom timestamps, compaction, and repair. |

**Never replace `@Version` by comparing `updatedAt` in Java**, because a race persists between `SELECT` and `UPDATE`. Even if custom CQL uses `updated_at` as a CAS predicate, the condition must go **inside the mutation**, with precision, nullability, and uniqueness handled carefully.

## 9. Repository: Conditional Creation and Saving

### 9.1. Repository by Composite Key

~~~java
// DeviceSettingRepository.java
package example.telemetry;

import org.springframework.data.cassandra.repository.CassandraRepository;

public interface DeviceSettingRepository
        extends CassandraRepository<DeviceSetting, DeviceKey> {
}
~~~

You do not need to write `UPDATE ... IF version=?` manually for entity save paths **where Spring Data Cassandra supports optimistic locking**. Spring Data tracks `@Version` on supported single-entity operations using Cassandra LWTs. However, when using custom `@Query` or raw Core Driver bypassing repositories, **never assume queries automatically get version checks**.

### 9.2. Creating a New Entity via `CassandraTemplate.insert`

~~~java
// DeviceSettingBootstrap.java
package example.telemetry;

import java.time.Instant;
import org.springframework.data.cassandra.core.CassandraTemplate;
import org.springframework.stereotype.Service;

@Service
public class DeviceSettingBootstrap {
    private final CassandraTemplate template;

    public DeviceSettingBootstrap(CassandraTemplate template) {
        this.template = template;
    }

    public DeviceSetting createOnce(
            String tenantId, String deviceId, String operator) {
        DeviceSetting fresh = new DeviceSetting(
            new DeviceKey(tenantId, deviceId),
            "AUTO",
            Instant.now(),
            operator);

        // @Version Long is null -> treated as new, conditional INSERT.
        // If the row already exists, Spring Data may throw
        // OptimisticLockingFailureException.
        return template.insert(fresh);
    }
}
~~~

Per official Spring Data docs, **inserting an entity with null version** creates version `0` using `INSERT ... IF NOT EXISTS`, rejecting duplicate inserts. Verify on your exact Spring Data version because `template.insert`, `repository.save`, `Persistable.isNew()`, and custom converters affect new-entity detection.

**Note:** `@Version` does not auto-generate `tenantId`/`deviceId`. The full primary key must exist beforehand. Never write `null` for partition keys.

### 9.3. Updating via `repository.save`

~~~java
// Service snippet assuming repository is injected.
DeviceKey key = new DeviceKey("tenant-a", "device-7");
DeviceSetting current = repository.findById(key).orElseThrow();

Long versionBefore = current.getVersion(); // e.g. 0
current.setMode("MAINTENANCE");
current.setUpdatedBy("operator-a");
current.setUpdatedAt(Instant.now());

DeviceSetting saved = repository.save(current);
Long versionAfter = saved.getVersion();    // normally 1 after update
~~~

If another writer modified the row after `findById`, saving the stale entity triggers **`OptimisticLockingFailureException`** (`org.springframework.dao`). This differs from `ReadTimeout`/`WriteTimeout`: a confirmed conflict means the **conditional mutation was not applied**, whereas a timeout leaves the outcome uncertain.

### 9.4. Why Isn't `saveAll` a Multi-Entity Transaction?

Spring Data Cassandra guarantees optimistic locking only per supported **single-entity operation**. `saveAll` issues multiple operations, each succeeding or failing independently; it **does not wrap a list of entities in a multi-partition transaction**.

~~~text
Update entity A version=3 -> applied.
Update entity B version=8 -> conflict.

Possible outcome:
  A changed, B was rejected.
Never assume saveAll rolled back entirely to initial state.
~~~

When A and B must succeed or fail together, design data within one atomicity boundary or use a durable mutation log/reconciliation. Never add Spring `@Transactional` assuming SQL/JPA-style Cassandra transactions.

## 10. Real Race Condition: Two Service Instances Editing One Entity

### 10.1. Without `@Version`

~~~text
T0: A SELECT mode=AUTO
T1: B SELECT mode=AUTO
T2: A UPDATE mode=MAINTENANCE (ACK)
T3: B UPDATE mode=MANUAL       (ACK)

No conflict flag.
Final value depends on timestamp/mutation reconciliation.
User A may never know their change was overwritten.
~~~

### 10.2. With `@Version`

~~~text
T0: A SELECT mode=AUTO, version=5
T1: B SELECT mode=AUTO, version=5
T2: A SAVE IF version=5 -> applied=true, version=6
T3: B SAVE IF version=5 -> applied=false

A: succeeds.
B: OptimisticLockingFailureException.
Row preserves A's change; not silently overwritten by B.
~~~

**These states are illustrative only.** A real concurrency test must never assume writer A always wins; when two requests race on the same version, **at most one eligible conditional mutation applies** under normal consensus, while the other hits conflict or timeout depending on failure conditions.

### 10.3. Distinguishing Three Outcomes

| Outcome | Evidence | Action |
| --- | --- | --- |
| **Applied** | LWT confirmed condition met and mutation accepted per CL. | Return new object/version; log audit/metrics per policy. |
| **Not applied / version mismatch** | `[applied]=false` or optimistic locking exception confirmed conflict. | Return 409/412; ask caller to reload/resolve conflict. |
| **Unknown / timeout** | Request timed out or connection dropped during condition or apply phase. | Never assume failed; inspect version/state and idempotency before retrying. |

**Attach correlation IDs and request IDs** (not every timeout should be retried). If a write triggers side effects outside Cassandra, use a dedup/outbox mechanism so the app knows whether an attempt already ran.

## 11. Service Layer: Preserving Expected Version from Client to Cassandra

A common HTTP design bug is **re-reading the latest entity and always saving**, ignoring the version the browser saw when opening the form. That still causes *lost updates* at the UX level even when the repository uses `@Version`:

~~~text
Browser B sends expectedVersion=5 from a stale form.
Service re-reads version=6 yet DOES NOT compare against expectedVersion.
Service applies B's change onto version=6 and saves; CAS succeeds.
=> Overwrote A's decision against the user's intent.
~~~

Therefore, the service must validate **`expectedVersion` from the client**, while `repository.save` uses CAS to close the race window **after the service re-reads**.

### 11.1. Service with Precondition and Conflict Handling

~~~java
// DeviceSettingsService.java
package example.telemetry;

import java.time.Instant;
import java.util.Objects;
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.stereotype.Service;

@Service
public class DeviceSettingsService {
    private final DeviceSettingRepository repository;

    public DeviceSettingsService(DeviceSettingRepository repository) {
        this.repository = repository;
    }

    public DeviceSetting changeMode(
            String tenantId,
            String deviceId,
            long expectedVersion,
            String mode,
            String operator) {

        if (!("AUTO".equals(mode)
                || "MANUAL".equals(mode)
                || "MAINTENANCE".equals(mode))) {
            throw new IllegalArgumentException("Unsupported device mode");
        }

        DeviceKey key = new DeviceKey(tenantId, deviceId);
        DeviceSetting current = repository.findById(key)
            .orElseThrow(() -> new DeviceSettingNotFoundException());

        // Compare browser's expectedVersion against freshly read state.
        if (!Objects.equals(current.getVersion(), expectedVersion)) {
            throw new StaleDeviceVersionException();
        }

        current.setMode(mode);
        current.setUpdatedAt(Instant.now());
        current.setUpdatedBy(operator);

        try {
            // With @Version: CAS closes the race between read and save.
            return repository.save(current);
        } catch (OptimisticLockingFailureException conflict) {
            throw new StaleDeviceVersionException(conflict);
        }
    }

    public static final class DeviceSettingNotFoundException
            extends RuntimeException {}

    public static final class StaleDeviceVersionException
            extends RuntimeException {
        public StaleDeviceVersionException() {
            super("Device setting changed; reload before editing");
        }
        public StaleDeviceVersionException(Throwable cause) {
            super("Device setting changed; reload before editing", cause);
        }
    }
}
~~~

**Scope:** this is a lab service for one entity. Production must enforce **tenant authorization** and operator identity before calling the repository, enforce rate/timeout limits, avoid logging sensitive data, and define explicit contracts when Cassandra returns **unknown**, not just conflicts.

### 11.2. Two Version Checks Protect Different Windows

1. **Checking `expectedVersion` from HTTP:** prevents a user with a stale form from overwriting a change already committed when the request began.
2. **`@Version`/LWT on save:** prevents races occurring **between the service's read and the service's write**.

Having #1 without #2 still leaves a race; having #2 while ignoring the browser's version produces "fetch latest state and apply stale command" surprises.

### 11.3. When Receiving Non-Conflict Exceptions

Never catch every `RuntimeException` and throw `StaleDeviceVersionException`. `Unauthorized`, `Unavailable`, `CASWriteTimeout`, request timeouts, mapping/codec errors, and schema mismatches **do not prove** the version changed. Let them propagate to proper error handlers returning transient/indeterminate errors or triggering runbook reconciliation.

## 12. HTTP `ETag` / `If-Match`: Passing Preconditions Through the API

A standard pattern for browsers to send back the observed version:

~~~http
GET /api/tenants/tenant-a/devices/device-7/settings

HTTP/1.1 200 OK
ETag: "7"
Content-Type: application/json

{"mode":"AUTO","version":7}
~~~

Then the client sends:

~~~http
PUT /api/tenants/tenant-a/devices/device-7/settings/mode
If-Match: "7"
Content-Type: application/json

{"mode":"MAINTENANCE"}
~~~

If someone else saved version 8, the API responds:

~~~http
HTTP/1.1 412 Precondition Failed
Content-Type: application/problem+json

{"title":"Version conflict","detail":"Reload the setting and retry"}
~~~

**HTTP 412** fits failed **`If-Match` preconditions**; **409 Conflict** is also widely used for domain conflicts not driven by `If-Match`. Pick one clear contract, test it, and never turn 409/412 into 500s.

### 12.1. Controller Validating Numeric `ETag`s

~~~java
// DeviceSettingsController.java
package example.telemetry;

import java.util.Objects;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/tenants/{tenantId}/devices/{deviceId}/settings")
public class DeviceSettingsController {
    public record ModeRequest(String mode) {}
    public record ModeResponse(String mode, long version) {}

    private final DeviceSettingsService service;

    public DeviceSettingsController(DeviceSettingsService service) {
        this.service = service;
    }

    @PutMapping("/mode")
    public ResponseEntity<ModeResponse> setMode(
            @PathVariable String tenantId,
            @PathVariable String deviceId,
            @RequestHeader("If-Match") String ifMatch,
            @RequestBody ModeRequest request) {

        // Sample API accepts only strong ETag like "7"; rejects W/"7"
        // or "*" unless their semantics are explicitly defined.
        if (!ifMatch.matches("\"[0-9]+\"")) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Expected strong numeric ETag");
        }
        long expected;
        try {
            expected = Long.parseLong(
                ifMatch.substring(1, ifMatch.length() - 1));
        } catch (NumberFormatException invalid) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Invalid version number");
        }

        // Assumes caller/tenant authorization is enforced in a service filter.
        DeviceSetting saved = service.changeMode(
            tenantId, deviceId, expected, request.mode(), "api-operator");

        return ResponseEntity.ok()
            .eTag("\"" + Objects.requireNonNull(saved.getVersion()) + "\"")
            .body(new ModeResponse(saved.getMode(), saved.getVersion()));
    }

    @ExceptionHandler(DeviceSettingsService.StaleDeviceVersionException.class)
    public ResponseEntity<String> stale() {
        return ResponseEntity.status(HttpStatus.PRECONDITION_FAILED)
            .body("Version conflict; reload current resource");
    }

    @ExceptionHandler(DeviceSettingsService.DeviceSettingNotFoundException.class)
    public ResponseEntity<String> missing() {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
            .body("Device setting not found");
    }
}
~~~

**This is an educational API**, not a complete production HTTP implementation. Production needs tenant authorization, input validation, no hardcoded operator names, payload caps, state-safe error responses, and **428 Precondition Required** when a mandatory header is missing. Ensure ETags are unaffected by unrelated serialization changes and test behind reverse proxies/caches.

When the API returns version 8 after a write, the client must store the **new ETag** for subsequent edits. Browsers must never increment 7 to 8 locally and retry a stale form without re-reading or resolving the conflict.

## 13. Java Driver Core: Emitting Conditional CQL and Reading `wasApplied()`

Spring Data `@Version` works cleanly for entity CRUD. When a statement should **update only a few columns** or explicitly set per-request CL/serial CL, use Java Driver 4.x directly — **provided all writers to the row still obey the version protocol**.

### 13.1. Prepared CAS Update

~~~java
// ConditionalModeUpdate.java
package example.telemetry;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import java.time.Instant;

public final class ConditionalModeUpdate {
    private final CqlSession session;
    private final PreparedStatement cas;

    public ConditionalModeUpdate(CqlSession session) {
        this.session = session;
        this.cas = session.prepare(
            "UPDATE telemetry_locking.device_settings " +
            "SET mode = ?, updated_at = ?, updated_by = ?, version = ? " +
            "WHERE tenant_id = ? AND device_id = ? IF version = ?");
    }

    public boolean trySetMode(
            String tenantId, String deviceId,
            long expectedVersion, String newMode, String operator) {
        if (expectedVersion == Long.MAX_VALUE) {
            throw new IllegalArgumentException("Version overflow");
        }

        BoundStatement statement = cas.bind(
                newMode,
                Instant.now(),
                operator,
                expectedVersion + 1,
                tenantId,
                deviceId,
                expectedVersion)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setSerialConsistencyLevel(DefaultConsistencyLevel.LOCAL_SERIAL);

        ResultSet result = session.execute(statement);
        // For conditional CQL mutations, true = condition met and applied.
        return result.wasApplied();
    }
}
~~~

`setSerialConsistencyLevel` is a Java Driver 4.x statement method; `LOCAL_SERIAL` scopes the LWT phase per topology. `wasApplied()` **is not** "received HTTP 200"; it reports whether the conditional statement applied. If `execute()` throws a timeout, **there is no `ResultSet` to call `wasApplied()` on**, and the outcome may be uncertain.

### 13.2. Never Mix Incompatible Version Schemes

If repositories use `@Version Long` while a backfill job runs:

~~~sql
-- ANTI-PATTERN: skips checking and incrementing version.
UPDATE telemetry_locking.device_settings
SET mode = 'AUTO'
WHERE tenant_id = 'tenant-a'
  AND device_id = 'device-7';
~~~

the job alters `mode` while **leaving `version` unchanged**, allowing a stale client to pass `IF version = 7` later and overwrite it. Every write path (API, batch, migration, admin tool) must either:

- Obey **one shared CAS/version contract**, or
- Run inside a write-frozen maintenance window with audited reconciliation/cutover and approved risk.

**Never** run conditional writers and unconditional writers concurrently on the same row and claim optimistic locking is enforced.

### 13.3. Why Not Just `UPDATE ... IF mode = 'AUTO'`?

A conditional update can compare a business column instead of a version:

~~~sql
UPDATE telemetry_locking.device_settings
SET mode = 'MAINTENANCE'
WHERE tenant_id = 'tenant-a'
  AND device_id = 'device-7'
IF mode = 'AUTO';
~~~

This works if **business rules only care about `mode`**. Yet another change (e.g., `updated_by`, policy quotas, or another field) could leave `mode` unchanged, letting a stale client pass the condition anyway. **A version incremented on every meaningful mutation** detects a broader set of concurrent edits. Pick predicates matching the invariant to protect, never treating version as ceremony.

## 14. `SERIAL` and `LOCAL_SERIAL` in Multi-Datacenter Systems

### 14.1. Single DC

Assuming `NetworkTopologyStrategy {'dc1':3}`, three full replicas:

| Setting | Scope | Meaning |
| --- | --- | --- |
| `LOCAL_QUORUM` regular CL | Local DC `dc1` | Local quorum response for regular read/write phase. |
| `LOCAL_SERIAL` serial CL | Serial phase inside local DC | Conditional coordination per version/replica placement. |
| `SERIAL` serial CL | Broader than local; spans DCs per multi-DC policy | Needed for cross-DC conditional ordering; adds WAN dependency/latency. |

One request uses **both regular and serial CL** for its two phases. Choose `SERIAL` only when the consistency contract requires cross-DC scope; **never assume it improves performance**.

### 14.2. Two DCs Both Accepting Writers

~~~mermaid
flowchart TD
    A["Writer A in dc1"] --> C["Row (tenant-a, device-7) replicated in dc1/dc2"]
    B["Writer B in dc2"] --> C
    C --> D{"Approved LWT scope?"}
    D -->|Separate LOCAL_SERIAL per DC| E["Assess cross-DC ordering/visibility conflict risk"]
    D -->|Global SERIAL scope| F["Broader consensus, WAN latency, and availability trade-offs"]
    E --> G["Test real conflicts, outages, and recovery"]
    F --> G
~~~

With `NetworkTopologyStrategy {'dc1':3,'dc2':3}`, an active-active app across both DCs must **lock down invariants**: can two admins in two DCs edit the same device simultaneously? Do conditional writes require **cluster-wide linearizability**? If yes, design/verify serial CL per Cassandra version docs and budget for cross-DC latency and WAN outage impact.

**Never pick `LOCAL_SERIAL`** casually just because each service sits "near a replica". `LOCAL_SERIAL` limits consensus locally; async cross-DC propagation and WAN lag break naive "single global writer" assumptions.

### 14.3. Serial Reads Are Not Normal Reads

Per Cassandra docs, serial consistency can be used for conditional/serial reads of state near ongoing LWTs. Never switch all `SELECT`s to `SERIAL` out of habit. For normal reads, a partition-key `SELECT` at the right regular CL avoids unnecessary Paxos overhead. **Never treat `SERIAL` as "latest read at `LOCAL_ONE` cost".**

## 15. TTL, Deletes, Tombstones, and Reset Versions

### 15.1. Versions Must Live as Long as the Protected Invariant

For time-series data, TTL is great for auto-expiration. Yet `device_settings` holds **concurrency-control state and version**. If `version` TTLs out while state remains alive, the version vanishes before users save:

~~~text
09:00: mode = MANUAL, version = 7
09:05: version cell expires via TTL; mode cell remains alive
09:06: API sends IF version = 7
       -> condition fails because version no longer exists as before
~~~

Never slap `default_time_to_live` onto a control/settings table when transactions rely on stable versions. If settings must expire, define **whole-row lifecycle, version/generation, recreate semantics, and auditing**.

### 15.2. TTL Does Not Depend on `updated_at`

~~~sql
-- Illustrative example of a TTL'd column only; DO NOT use on
-- device_settings participating in @Version without lifecycle design.
UPDATE telemetry_locking.device_settings
USING TTL 300
SET updated_by = 'temporary-operator'
WHERE tenant_id = 'tenant-a'
  AND device_id = 'device-7';
~~~

TTL follows Cassandra write-time semantics, **not the timestamp stored in `updated_at`**. When a cell expires, physical reclamation happens via tombstones/SSTables/compaction — never assume files vanish instantly. Restores or retries with fresh TTL can unexpectedly **extend** retention.

### 15.3. Deletes and ABA Anomalies

Example:

~~~text
Row generation 1: tenant-a/device-7, version=2, mode=MANUAL
Row deleted -> tombstone
Recreated with same primary key -> version=0

An old client that read version=0 in generation 1
can confuse the new state if comparing version numbers alone across complex lifecycles.
~~~

This is an **ABA** risk: a state/version returns to an earlier value while representing a **different data generation**. Where recreating the same identity is disallowed or lifecycles must be distinguished, use an immutable **incarnation/generation ID** or **soft deletes** with monotonic versions. Keep audit/projection tables aligned with delete/restore contracts.

### 15.4. Tombstones, Repair, and `gc_grace_seconds`

Applied conditional deletes still write tombstones. Replicas can miss mutations during outages/partitions, so plan **repairs** and appropriate grace periods before tombstones can safely purge. **Never shrink `gc_grace_seconds` casually** to save disk, as returning stale replicas can resurrect zombie data.

**In short:** optimistic locking protects concurrent writes by version; it **does not solve retention, expiration, tombstones, replays, or backup restores**.

## 16. Distinguishing Conflicts, Timeouts, Unavailable, and App Errors

A production system must classify outcomes before deciding whether to retry.

| Result / Error | Do We Know If Conditional Mutation Applied? | Handling |
| --- | --- | --- |
| `wasApplied() == true` | Confirmed applied by driver per CL semantics. | Return new version; record success metric. |
| `wasApplied() == false` | Confirmed condition **was not met** for this attempt. | Conflict; do not overwrite someone else's data. |
| `OptimisticLockingFailureException` for stale version | Spring Data confirmed optimistic lock conflict on supported path. | Return 409/412; ask caller to reload/merge or abort. |
| `Unavailable` | Insufficient replicas for CL at request time. | Check RF/DC/nodes; never raise timeouts or drop CL blindly. |
| `ReadTimeout` | Read did not finish within deadline. | May run bounded safe read retry; never return "not found". |
| `WriteTimeout` / CAS timeout | **Uncertain** how far the request progressed. | Read/reconcile state, keep request ID; avoid blind non-idempotent retries. |
| Driver request timeout / connection lost | No reliable response received. | Find root cause/traffic issues; treat outcome as unknown if sent. |
| `Unauthorized` | CQL role lacks permission. | Fix RBAC/identity; never loop retries or switch to superuser. |
| Schema/codec mismatch | CQL or Java mapping incompatible. | Fix schema/driver/converters; never mask as conflict. |

**Never write `catch (Exception ignored) { return false; }`** around CAS. It disguises infrastructure or permission errors as "version mismatch", misleading callers into wrong actions.

### 16.1. Retrying Conflicts Differs from Retrying Timeouts

- **Confirmed conflict:** the current CAS did not apply; ask the user to review updated state. For **commutative** updates or approved auto-merge rules, re-read and recompute the mutation with strict **max attempts and deadlines**.
- **Indeterminate timeout:** it may already have applied. Before retrying, inspect **current state** and verify **operation ID/version/desired state**, because retrying `IF version=old` can return `false` simply because **your own first attempt succeeded**, not because someone else intervened.
- **Unavailable:** replicas are missing for the CL; fast retries only add load. Fix topology and capacity.
- **Auth/schema/validation:** never auto-retry identical inputs as transient errors.

### 16.2. CAS `false` After a Timeout Does Not Prove the First Attempt Failed

~~~text
Client sends: IF version=7, SET version=8, mode=MANUAL
Cassandra may have applied it, yet the response was lost.
Client retries identically: IF version=7 -> applied=false (now at 8).

If the service interprets retry applied=false as "operation failed",
it reports failure even though mode=MANUAL was persisted.
~~~

To distinguish **"my own request already succeeded"** from **"another writer changed state"**, consider storing a `last_operation_id`/mutation ID in the same row alongside the conditional update and checking it during reconciliation, with clear uniqueness/retention rules. For side effects outside Cassandra, maintain a durable idempotency log/outbox — **never** rely solely on `mode` matching.

### 16.3. Set Retry Budgets and Backoff

~~~text
Example policy (not a Cassandra default):
  Total API deadline: 800 ms
  CAS attempts: max 2 if business rules truly permit
  Backoff: bounded exponential + jitter
  Never auto-retry: Unauthorized, InvalidQuery, stale If-Match
  Unknown timeout: reconciliation / idempotency policy
  Fleet-wide retry budget: explicit error/traffic cap
~~~

Setting only a **retry count** without deadlines and in-flight budgets still allows retry storms. Never call `Thread.sleep` inside driver/event-loop callbacks; use bounded async schedulers/backoff.

## 17. LWT Cost: Every Condition Adds Coordination

### 17.1. Why Are LWTs More Expensive Than Normal Upserts?

Unconditional `INSERT`/`UPDATE` skips serial consensus. `IF NOT EXISTS` or `IF version` requires eligible replicas to run **consensus/state checks**, adding round-trips, CPU, network traffic, contention risk, and latency—especially across slow WANs/DCs.

~~~mermaid
flowchart LR
    A["Normal write: INSERT / UPDATE"] --> B["Coordinator"]
    B --> C["Replicas + regular CL ACK"]
    D["LWT: UPDATE ... IF version"] --> E["Coordinator"]
    E --> F["Serial agreement / Paxos"]
    F --> G["Conditional mutation + regular CL"]
    G --> H["applied true/false or error"]
~~~

Never claim "LWT is always exactly N times slower" for all clusters; step counts, Paxos optimizations, contention, replica health, and topology **vary by version**. Benchmark on your target workload.

### 17.2. Simulated Measurement Example

| Metric (Simulated) | Normal `UPDATE` | `UPDATE` with `IF version` |
| --- | ---: | ---: |
| App-side read/modify/write | Optional | Often reads first for business state. |
| Median latency | 3 ms | 11 ms |
| p99 latency | 15 ms | 42 ms |
| Conflict rate | Undetected | 4% |
| Replica/client round-trips | Fewer | Additional conditional/consensus phase |
| Lost-update risk | Present if based on stale read | Reduced when all writers follow version protocol |

**These numbers are completely synthetic**, not benchmarks or Cassandra thresholds. They illustrate why you must measure **p95/p99, CAS contention, rejections/conflicts, coordinator/replica latency, and CPU/network**, rather than judging solely by Java code brevity.

### 17.3. Hot Partitions and Contention

A table with a **single** partition key like `global_config` funnels every writer company-wide into one partition and LWT contention domain. If 5,000 clients edit one version per second, most read a stale version and **collide** or suffer tail latency spikes.

With `PRIMARY KEY ((tenant_id,device_id))`, distinct devices hash to different tokens/replicas, spreading load — yet **one ultra-hot device** still contends on one row. Remedies include:

- A **single-writer/owner** per hot key serializing commands from an upstream queue.
- Moving from "every heartbeat bumps mode/version" to append-only events or bounded aggregations.
- Per-tenant/device rate limits, valid read caching, and idempotency.
- Separating state genuinely needing CAS from telemetry events suited to normal writes.

**Never use LWT on every event ingestion** just to "guarantee better data". For append-only time-series, immutable event IDs and idempotent upserts often suffice; reserve LWT for invariants that truly need compare-and-set.

### 17.4. Metrics for CAS

| Source | Metrics to Track | Meaning |
| --- | --- | --- |
| Spring API | `cas_success`, `cas_conflict`, `cas_timeout`, `cas_unknown`, p95/p99. | Separate business conflicts from backend failures. |
| Driver | Request latency, retry attempts, in-flight, throttler queue, coordinator spread. | Catch client-side overload and routing issues. |
| Cassandra | Version-specific CAS/Paxos latency/contention, read/write latency, dropped/pending tasks. | Spot coordination bottlenecks. |
| Replica JVM/OS | CPU, GC, disk latency, network RTT/retransmits. | Separate physical capacity issues from `@Version` code. |
| Application | ETag/`If-Match` mismatches, sampled hot-key contention, retry age/budget. | Spot UX/clients sending stale state. |

**Never attach `tenant_id`, `device_id`, request UUIDs, or raw payloads to metric labels** where cardinality or sensitivity is high. Stick to `query_name`, `outcome`, `environment`, `local_dc`, and endpoint; investigate hot keys via safe sampling.

## 18. Batches, Counters, and Multiple Tables: Abstraction Limits

### 18.1. `@Version` Does Not Replace Multi-Entity Transactions

Suppose one request runs sequentially:

~~~text
1. UPDATE device_settings IF version=7 -> applied=true
2. INSERT device_audit_event            -> timeout
3. UPDATE site_settings                -> applied=false
~~~

You cannot claim the sequence rolled back as a transaction just because step 1 used `@Version`. If audit events are mandatory, consider a **durable command log** plus idempotent workers updating projections/audits, with explicit ordering and failure reconciliation.

### 18.2. Counters Have Separate Semantics

Never use a `counter` column as `version` with `SET version = version + 1 IF ...`; Cassandra counter updates and CAS have incompatible limits. **Logical versions** use standard integer types (e.g., `bigint`) incremented by the app inside the **conditional mutation**.

### 18.3. LWT Does Not Provide Global Uniqueness Across Arbitrary Keys

`INSERT ... IF NOT EXISTS` protects only the **exact primary key/condition**. If two tenants use distinct partition keys, ensuring an `email` or `deviceSerial` appears only once system-wide is **not** guaranteed by CAS on `(tenant_id,device_id)`. You need a dedicated **uniqueness-claim table** keyed by the unique value with idempotency/reconciliation workflows, or another fitting data model.

Never run a full-table `SELECT` to check "no one used this serial yet" followed by `INSERT`: a race still exists between `SELECT` and `INSERT`, and the scan is prohibitively expensive.

### 18.4. Never Use `IF` as a Substitute for Data Modeling

CQL `UPDATE ... IF` on a **full primary key** prevents row-level lost updates, yet never turns `WHERE mode='AUTO' ALLOW FILTERING` into an indexed bulk conditional update. For conditional batch changes, drive partition/keys from a known source or query-driven table, bound concurrency, and handle per-row results/idempotency.

## 19. Testing Spring Data `@Version` Against Real Cassandra

### 19.1. Why Mocked Unit Tests Are Insufficient

A unit test mocking `DeviceSettingRepository.save` to return `version+1` passes easily, yet **never proves Spring Data emitted CQL LWTs**. Integration tests need:

1. Project-supported Cassandra version, native protocol, and matching driver.
2. Keyspace and schema **with `version bigint`** and the exact composite partition key.
3. Two separate entity instances reading the same version.
4. Writer 1 saving cleanly; writer 2 with the stale snapshot being rejected.
5. Duplicate-key creation and stale-entity deletion behaving properly.
6. Regular CL/serial CL, TLS/RBAC/permissions matching the test environment.

### 19.2. JUnit Integration Test for Stale Versions

~~~java
// DeviceSettingVersionIT.java
package example.telemetry;

import java.time.Instant;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.test.context.ActiveProfiles;
import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
@ActiveProfiles("test")
class DeviceSettingVersionIT {
    @Autowired DeviceSettingRepository repository;

    @Test
    void staleEntityCannotOverwriteSuccessfulUpdate() {
        DeviceKey key = new DeviceKey(
            "tenant-test", "device-" + UUID.randomUUID());

        DeviceSetting fresh = new DeviceSetting(
            key, "AUTO", Instant.now(), "test-seed");
        DeviceSetting created = repository.save(fresh);
        assertThat(created.getVersion()).isEqualTo(0L);

        // Two objects read separately yet sharing version=0.
        DeviceSetting copyA = repository.findById(key).orElseThrow();
        DeviceSetting copyB = repository.findById(key).orElseThrow();
        assertThat(copyA.getVersion()).isEqualTo(copyB.getVersion());

        copyA.setMode("MAINTENANCE");
        copyA.setUpdatedAt(Instant.now());
        copyA.setUpdatedBy("test-a");
        DeviceSetting accepted = repository.save(copyA);
        assertThat(accepted.getVersion()).isEqualTo(1L);

        copyB.setMode("MANUAL");
        copyB.setUpdatedAt(Instant.now());
        copyB.setUpdatedBy("test-b");
        assertThrows(OptimisticLockingFailureException.class,
            () -> repository.save(copyB));

        DeviceSetting finalState = repository.findById(key).orElseThrow();
        assertThat(finalState.getMode()).isEqualTo("MAINTENANCE");
        assertThat(finalState.getVersion()).isEqualTo(1L);
    }
}
~~~

**Conditions for trustworthy tests:**

- `application-test.yml` must point to an **isolated test cluster** with proper keyspaces/DDL and replicas. Never hit production, and never let the app context auto-create/drop unapproved tables.
- Each test uses a unique key so runs do not pollute each other. Clean up via test policy/TTL; if `deleteById` skips version checks on some path, never cite cleanup as proof of optimistic deletion.
- If using custom `@Version` converters or `Persistable`, test both new-entity detection and initial `null -> 0` versioning.
- If `@Version` is ignored (e.g., wrong import), `save` acts as a plain upsert and the stale test **fails** — catching the bug as intended.
- A single-threaded stale-copy test is easy to reproduce; add **parallel stress tests** to observe real contention and timeouts, not just sequential correctness.

### 19.3. Testing Two Concurrent Requests

Never spawn two tasks that **read** state after the first already wrote; they will read different versions and miss the race. Instead:

~~~text
1. Seed a DeviceSetting at version=0.
2. Read copyA and copyB BEFORE releasing the barrier.
3. Release a barrier so both threads call repository.save(copyX) concurrently.
4. Tally outcomes: one applied, one optimistic conflict
   (assuming no timeouts or node failures).
5. Re-read state and verify final mode/version matches the winning writer.
6. Repeat across unique keys while measuring p99 and CAS contention.
~~~

Under failure injection (replica down, packet loss, GC pauses, multi-DC), **timeouts/unknowns** can occur, so assertions must not treat every error as a version conflict. Never use `Thread.sleep` hoping to trigger a race; use barriers/latches to coordinate deterministically.

### 19.4. Edge-Case Test Matrix

| Test | Expectation |
| --- | --- |
| New insert `@Version Long == null`. | Created via conditional insert with initial version 0. |
| Duplicate full-PK insert. | Does not overwrite existing entity; reports duplicate/conflict per Spring Data. |
| Two `version=0` snapshots saved sequentially. | First becomes `version=1`, second throws optimistic locking failure. |
| Delete entity using a stale snapshot. | Does not delete newer data when using a version-checked delete path. |
| Custom `deleteById(key)` or raw CQL. | **Never assume** version checks; inspect generated statements/contracts. |
| Null version on existing row from migration. | Never silently treat as new and overwrite; migrate/backfill versions first. |
| HTTP user sends `If-Match:"7"`, DB is at version 8. | Return 412/409 before CAS; never apply stale command. |
| CAS timeout followed by retry. | Reconcile state/operation ID; never report guaranteed success/failure when unknown. |
| 100 writers hitting the same key. | Contention/latency stay bounded; no retry storms or backend overload. |
| Two DCs both accepting writes. | Serial scope and data correctness meet contract; never equate local with global. |
| TTL/delete/recreate on same key. | Generation/identity and retention behave cleanly with no unexpected ABA bugs. |
| Non-Spring-Data writer bypassing version. | Tests catch data drift and policy violations. |

## 20. Reactive Spring Data: `@Version` Still Requires Conflict Handling

For Spring WebFlux apps with the matching reactive starter, Spring Data Cassandra offers reactive repositories/templates. `@Version` still enforces **entity optimistic locking**, yet outcomes materialize **when the publisher is subscribed/executed**, not merely when constructing a `Mono`.

~~~java
// ReactiveDeviceSettingRepository.java
package example.telemetry;

import org.springframework.data.cassandra.repository.ReactiveCassandraRepository;

public interface ReactiveDeviceSettingRepository
        extends ReactiveCassandraRepository<DeviceSetting, DeviceKey> {
}
~~~

Conceptual service snippet in a reactive app:

~~~java
// Snippet inside a reactive service, not a standalone class.
Mono<DeviceSetting> result = reactiveRepository.findById(key)
    .switchIfEmpty(Mono.error(new DeviceSettingNotFoundException()))
    .flatMap(current -> {
        if (!Objects.equals(current.getVersion(), expectedVersion)) {
            return Mono.error(new StaleDeviceVersionException());
        }
        current.setMode(newMode);
        current.setUpdatedAt(Instant.now());
        return reactiveRepository.save(current);
    })
    .onErrorMap(OptimisticLockingFailureException.class,
        conflict -> new StaleDeviceVersionException(conflict));
~~~

`Mono`, `Objects`, `Instant`, and exceptions come from Java/Reactor/app code; do not paste without imports/beans. **Never write:**

~~~java
// ANTI-PATTERN: hides every conflict and Cassandra error behind an empty Mono.
reactiveRepository.save(current)
    .onErrorResume(error -> Mono.empty());
~~~

Turning `OptimisticLockingFailureException` into `Mono.empty()` tricks the HTTP layer into returning 200/404 wrongly. Use `onErrorMap` or typed error handlers, and never call `block()` on the event loop. When using Reactor retries, filter strictly for **genuinely transient errors** — never auto-retry stale preconditions infinitely.

**Reactive does not make Paxos free:** CQL conditions, round-trips, serial CL, replica contention, and Cassandra server cost remain identical for the same query. It only changes how Java waits for I/O and schedules pipelines.

## 21. Runbook When Conflicts or CAS Timeouts Spike

### 21.1. When `cas_conflict` Rises

1. Confirm the **failure type**: `OptimisticLockingFailureException` from stale state, `wasApplied=false`, or a timeout misclassified as a conflict?
2. Inspect **request rates per query/workload**, active users, client `If-Match` ages, retry counts, and how long users keep forms open.
3. Hunt for **batch jobs, schedulers, or admin tools** bypassing `@Version` and mutating `mode`.
4. Analyze **hot keys** using privacy-safe sampling; avoid high-cardinality tenant/device metric labels.
5. Evaluate whether users need **manual merges**, partial-field edits, or commutative operation semantics.
6. If one key is ultra-hot, consider single-writer queues or rate limits by design instead of tight retry loops.
7. Check Cassandra CAS contention, coordinator/replica p99, and CPU/network; avoid confusing normal conflicts with failing nodes.

### 21.2. When `CAS timeout` Rises

1. Measure client request timeouts, regular/serial CL, latency/queues/throttlers, and retry amplification.
2. Check `nodetool status`, `tpstats`, `compactionstats`, `proxyhistograms`, and version-specific CAS/Paxos metrics on **every DC/replica**.
3. Check GC logs, network retransmits/WAN RTT, and disk latency; look for repair/streaming/compaction contention.
4. Determine whether **multiple writers hit the same key** or `SERIAL` across the WAN is degraded.
5. **Never silently lower serial CL** or swap `LOCAL_QUORUM` to cut timeouts; evaluate correctness and get formal approval.
6. Prevent retry storms; enforce **bounded in-flight requests, queues, retry budgets, and backoff**. Throttle batch/maintenance loads if over capacity.
7. For unknown outcomes, run **version/state/`lastOperationId` reconciliation**; never mint new operation IDs on retries if doing so duplicates side effects.
8. After recovery, run regression tests and post-incident checks against RPO/RTO/SLO and consistency contracts.

### 21.3. Related Commands and Signals

~~~bash
# On lab nodes or per approved production operational runbooks.
nodetool status
nodetool info
nodetool tpstats
nodetool compactionstats
nodetool proxyhistograms
nodetool gcstats
nodetool tablestats telemetry_locking.device_settings
~~~

Exact commands/metrics vary by Cassandra version; `status` `UN` does not prove a specific partition is uncontended. Enable tracing **selectively**, never across 100% of traffic during heavy LWT contention because tracing adds overhead. Correlate logs by **UTC timestamp, node/DC, query name, and change ID**, redacting tenant/device IDs and payloads per policy.

## 22. Case Study: Hot Row and Auto-Retries Turn 409s into an Outage

### 22.1. Simulated Context

A system controls one shared gateway (`tenant-a/gateway-1`) for 3,000 users. After a campaign, many UI clients simultaneously read `version=11` and try switching `mode`. The service is configured to **retry three times without backoff on optimistic conflicts**.

| Simulated Metric | Before Peak | During Retry Storm | Interpretation |
| --- | ---: | ---: | --- |
| Unique user write requests/s | 20 | 800 | Higher incoming demand. |
| Avg CAS attempts/request | 1.0 | 2.7 | Retries amplify traffic. |
| Est. CAS attempts/s | 20 | 2,160 | Grows much faster than user requests. |
| Conflict rate | 2% | 78% | Many clients hold stale versions of the same key. |
| CAS p99 | 24 ms | 310 ms | Contention/queuing/WAN can contribute. |
| Unknown / timeout outcomes | Low | Rising | Harder to tell conflicts apart from backend failures. |

**Numbers are solely for learning analysis, not Cassandra benchmarks.**

### 22.2. Why Is Retrying a Stale Version Wrong?

If the client still holds `version=11` while the server moved to `version=12`, sending `IF version=11` three more times **will never make the condition pass**. And if the service silently re-reads `version=12` and writes the user's old `version=11` decision on top, it **overwrites the newer decision** without user consent.

### 22.3. Remediation Steps

1. Return **412 Precondition Failed** with refresh/review guidance for `If-Match` updates.
2. Auto-merge only operations with **safe semantics**, such as truly independent metadata fields — never blindly overwrite machine state.
3. Bound **in-flight CAS per key/tenant** and fleet-wide with bounded queues and rate limits.
4. For an ultra-hot shared gateway, consider a **single-writer** command processor recording intents to a durable log and applying versioned state sequentially.
5. Separate legitimate `conflict`s from `timeout/unavailable` on dashboards so user behavior does not pollute infrastructure error SLOs.
6. Test multi-DC serial consistency, node failures, and config rollbacks before reopening full traffic.

**Expected outcome:** reduced load amplification and preserved user intent — not artificially lowering HTTP 409 counts by ignoring preconditions.

## 23. When to Use `@Version`, Manual `IF`, or Another Design?

| Need | Usually Sensible Choice | Why |
| --- | --- | --- |
| Single-row config CRUD via Spring Data | **`@Version Long`** + repository/template. | Clear entity contract, minimal boilerplate, built-in conflict exception. |
| Conditional update of just a few columns | **Prepared CQL `IF version=?`** via Driver Core. | Controls projection/mutation/serial CL and `wasApplied`. |
| Create a singleton resource once | **`INSERT ... IF NOT EXISTS`**. | Protects the same primary key from duplicate upserts. |
| Prevent update from creating a row without caring about stale values | **`UPDATE ... IF EXISTS`** if existence alone matters. | Provides no version conflict detection. |
| Append-only events with stable UUIDs | **Unconditional idempotent upsert** when contract allows. | Avoids unnecessary Paxos overhead. |
| Continuously incrementing counters/metrics | Proper counter/aggregation model; **never emulate counters with `@Version`**. | Different retry semantics and throughput profile. |
| Multi-table projections/audits | Durable command log / CDC / reconciliation. | Single-row CAS is not atomic across tables or systems. |
| Global uniqueness | Dedicated uniqueness-claim table tested for conflicts. | `IF NOT EXISTS` on another key cannot guard global uniqueness. |
| Hot row with thousands of writers | Single writer / queue / rate control or state redesign. | LWT contention drives conflicts and tail latency. |
| Active-active multi-DC on the same key | Deliberate global `SERIAL`, topology, and SLO design. | `LOCAL_SERIAL` does not provide global ordering by default. |
| Long-lived UI edit forms | HTTP `If-Match` + CAS + conflict UX. | Protects user intent from stale updates. |

### 23.1. Decision Flow

~~~mermaid
flowchart TD
    A["Mutation on Cassandra"] --> B{"Need lost-update / conditional check?"}
    B -->|No| C["Unconditional write, idempotency, and proper CL"]
    B -->|Yes| D{"Single-row Spring Data entity?"}
    D -->|Yes| E["@Version Long + repository/template"]
    D -->|No / column-specific| F["Prepared CQL IF ... + wasApplied"]
    E --> G["Lock regular CL + serial CL per topology"]
    F --> G
    G --> H["Enforce across all writers, API If-Match, and retry budget"]
    H --> I["Test concurrency, delete/TTL, timeouts, and multi-DC"]
    I --> J{"Correctness + p99 + contention acceptable?"}
    J -->|Yes| K["Canary and roll out with monitoring"]
    J -->|No| L["Reduce contention, remodel, or choose alternative"]
~~~

## 24. Common True/False Statements

| Statement | True / False | Explanation |
| --- | --- | --- |
| "Spring Data Cassandra `@Version` uses LWT." | **True** | Conditional insert/update/delete on single entities. |
| "`@Version` acts like a lock held from GET to PUT." | **False** | CAS checks at mutation time; no lock spans the HTTP round-trip. |
| "Every `repository.save` with `@Version` is a normal upsert." | **False** | Spring Data uses conditional operations on versioned entities per supported APIs. |
| "Checking version in Java then running `UPDATE` without `IF` suffices." | **False** | Races still happen between read and write. |
| "`IF EXISTS` always prevents lost updates." | **False** | Checks existence only, not what the user read. |
| "When `IF version=7` returns `applied=false`, the new mode was written." | **False** | Condition failed; the conditional mutation did not apply. |
| "A write timeout proves no replica wrote the data." | **False** | Outcome may be unknown; reconcile state. |
| "Retrying the same CAS after a timeout can return false because the first attempt succeeded." | **True** | Version was already incremented by the first attempt. |
| "`LOCAL_QUORUM` automatically enables Paxos." | **False** | Requires conditional CQL/`@Version` path; regular CL differs from serial CL. |
| "`LOCAL_SERIAL` always gives cross-DC global linearizability." | **False** | Scoped to local DC; evaluate multi-DC semantics. |
| "`saveAll` with `@Version` is an atomic list transaction." | **False** | Version locking applies per single-entity operation, not batches. |
| "Cassandra auto-increments `version bigint` on every `UPDATE`." | **False** | All writers must follow a unified conditional/version protocol. |
| "`updated_at` acts like `@Version` for concurrency." | **False** | Timestamp fields do not perform CAS without explicit `IF`. |
| "`@Version Long` can start null and initialize to 0 on insert." | **True** | Per Spring Data examples; test on your exact version/mapper. |
| "Deleting and recreating the same key cannot cause ABA." | **False** | Version/generation can reset; define lifecycle contracts. |
| "CQL CAS is free when there is no conflict." | **False** | Still pays Paxos/coordination overhead. |
| "Mocking the repository in unit tests proves LWTs execute." | **False** | Requires integration tests on real Cassandra. |
| "Browser HTTP `If-Match` and DB CAS protect two distinct race windows." | **True** | One catches stale forms; the other catches write-time races. |

## 25. Self-Check Exercises with Answers

**Exercise 1.** Two admins read `version=3`. A writes `mode=MANUAL` and B writes `mode=MAINTENANCE` using plain `UPDATE`s. Is one guaranteed to see a version conflict?

**Answer:** **No.** Unconditional writes reconcile via Cassandra timestamp/cell semantics. To detect lost updates, use `UPDATE ... IF version=3` or Spring Data `@Version` across all writers.

**Exercise 2.** Why is `if (row.getVersion()==expected) repository.saveWithoutCondition(row)` unsafe?

**Answer:** Another writer can mutate the row between read and update (**TOCTOU race**). Version checks must travel **inside the conditional mutation** and execute in Cassandra via LWT.

**Exercise 3.** Which package must Spring Data Cassandra import `@Version` from for optimistic locking?

**Answer:** **`org.springframework.data.annotation.Version`**. Never substitute `jakarta.persistence.Version` out of JPA habit. Mapping also needs a matching CQL column, e.g., `version bigint`.

**Exercise 4.** A new entity has `@Version Long version=null`. Per official Spring Data examples, what version does the first successful insert set?

**Answer:** **0**. Inserting uses `IF NOT EXISTS`; if the full primary key already exists, it does not apply and the framework throws an optimistic conflict on supported paths. Test if using `Persistable` or custom mappings.

**Exercise 5.** Row `tenant-a/device-7` is at `version=7`. CQL `UPDATE SET mode='MANUAL',version=8 ... IF version=7` runs twice. What happens?

**Answer:** The first run can return `[applied]=true` bumping version to 8; the second returns **`[applied]=false`** because version is no longer 7. Never automatically blame another writer when a duplicate retry fails.

**Exercise 6.** Does `IF EXISTS` stop two admins from overwriting each other's mode while the row exists?

**Answer:** **No.** `IF EXISTS` checks existence, not what the user read; both updates apply sequentially. Use `IF version=?` when the invariant is preventing lost updates.

**Exercise 7.** A conditional write specifies `LOCAL_QUORUM` regular CL and `LOCAL_SERIAL` serial CL. Do they do the same thing?

**Answer:** **No.** Serial CL governs the conditional/Paxos phase; regular CL governs the write/visibility phase. Never assume `LOCAL_QUORUM` activates LWT.

**Exercise 8.** A cluster has RF=3 in `dc1` and one replica goes down. How many full replicas must respond for `LOCAL_QUORUM`, and can LWTs succeed?

**Answer:** **Two**. If the remaining two replicas are up and satisfy serial/regular CL requirements, the request **can** succeed; never assume quorum alone guarantees every LWT succeeds under all conditions.

**Exercise 9.** The same device is written from both `dc1` and `dc2`. Can you use `LOCAL_SERIAL` in both DCs to guarantee a single global order?

**Answer:** **No.** `LOCAL_SERIAL` scopes serial consensus to the local DC. Evaluate actual multi-DC contention, version semantics, and global `SERIAL` with its WAN latency trade-offs.

**Exercise 10.** An API receives `If-Match:"7"`, yet the service reads version 8 from the DB and saves with the version-8 object. Why is this wrong for a form edit?

**Answer:** The service ignored the **client precondition**; it applies a stale form decision onto newer state. Compare `expectedVersion=7` against DB `version=8` and return 412/409 rather than substituting 8.

**Exercise 11.** After a CAS `WriteTimeout`, a retry with the same `expectedVersion` returns `applied=false`. Can you conclude the first attempt was rejected?

**Answer:** **No.** The first attempt may have applied and bumped the version while the response was lost. Read/reconcile `version`, `mode`, and `lastOperationId` if present per your idempotency contract.

**Exercise 12.** `repository.saveAll` updates A cleanly and hits a conflict on B. Does `@Version` roll back A automatically?

**Answer:** **No.** Spring Data `@Version` supports single-entity operations, not multi-row atomic transactions. Use reconciliation workflows or single-partition data modeling when all-or-nothing is required.

**Exercise 13.** If a batch job runs an unconditional `UPDATE mode='AUTO'` without incrementing version, is optimistic locking still intact across writers?

**Answer:** **No.** The batch alters `mode` while leaving the old version untouched; a subsequent CAS still sees the expected version and overwrites it. Every writer must follow the same version contract or run inside controlled maintenance windows.

**Exercise 14.** Why shouldn't you set a TTL on the `version` column shorter than the configuration's lifetime?

**Answer:** `version` can expire while state stays alive, breaking `IF version=?` and lifecycle invariants. Manage expiry/deletion/generation for the **entire business state** rather than expiring `version` arbitrarily.

**Exercise 15.** Deleting an entity at version 8 and recreating the same primary key at version 0: what risk arises if an old client still holds version 0 from the prior generation?

**Answer:** **ABA / version-reuse** risk in complex lifecycles. Use an immutable generation/incarnation ID, soft deletes, or uniqueness policies when generations must never be confused.

**Exercise 16.** Should you use `@Version` and LWT on every append-only telemetry event when producers already assign stable UUIDs?

**Answer:** **Not necessarily.** If idempotent upserts by full primary key preserve invariants, LWT adds needless Paxos overhead. Reserve conditional mutations for invariants that genuinely require existence/state checks.

**Exercise 17.** 15 Java pods each run 80 in-flight CAS requests before retries. What is the theoretical fleet concurrency cap?

**Answer:** `15 × 80 = 1,200` concurrent CAS requests across the fleet. That is neither 1,200 requests/second throughput nor connection count; if 80% contend on one key, servers can still bottleneck severely despite having many nodes.

**Exercise 18.** A JUnit test mocking the repository increments version and passes. Does that prove real Cassandra executes `IF version`?

**Answer:** **Not yet.** Run integration tests on real Cassandra with exact DDL, reading two entities at the same version, saving A, verifying B throws an optimistic conflict, and checking effective serial/regular CL and code paths.

**Exercise 19.** What is wrong when a service catches all `RuntimeException`s and returns HTTP 409?

**Answer:** `Unauthorized`, `Unavailable`, timeouts, and codec errors get misreported as version conflicts. Map only **confirmed conflicts** to 409/412; preserve accurate semantics and observability for all other errors.

**Exercise 20.** An API updating device `mode` is hit by 3,000 admins concurrently, raising CAS conflict rates. First, should you raise retries or reduce concurrency/redesign ownership?

**Answer:** **Do not blindly retry.** Analyze contention, concurrent writers per key, ETag age, and SLOs. You may need single-writer queues and UI conflict resolution; adding retries for stale versions only amplifies load.

## 26. Production Rollout Checklist for Optimistic Locking

~~~text
DATA MODEL / CQL
[ ] Table uses full primary key matching queries; no ALLOW FILTERING.
[ ] version bigint column exists; all meaningful mutations increment version.
[ ] Never use counter as version; never alter partition/clustering keys ad hoc.
[ ] Conditional insert/update/delete and [applied] semantics understood.
[ ] TTL/delete/recreate has explicit generation/lifecycle; never breaks version.
[ ] Cross-table audits/projections use reconciliation/idempotency.

SPRING DATA / JAVA
[ ] Uses org.springframework.data.annotation.Version with nullable Long.
[ ] Entity mapping and new-entity detection verified via integration tests.
[ ] Repository/template performs single-entity operations per supported lock paths.
[ ] saveAll/batches never treated as multi-entity transactions.
[ ] Zero raw CQL writers bypassing or failing to increment version.
[ ] Core Driver custom CAS includes exact WHERE and IF, checking wasApplied().
[ ] One Spring-managed CqlSession; never create sessions per request.

CONSISTENCY / RELIABILITY
[ ] Regular CL and serial CL approved per RF/DC and workload.
[ ] Multi-DC setups have explicit LOCAL_SERIAL vs. SERIAL decisions.
[ ] Confirmed conflicts separated from timeouts/unknown outcomes and Unavailable.
[ ] Idempotency/operation IDs, reconciliation, and retry budgets implemented.
[ ] Admission, in-flight caps, and queues bounded; hot-key contention measured.
[ ] Never drop CL or raise timeouts blindly to hide errors.

HTTP / SECURITY
[ ] Client If-Match/ETag compared against freshly read state before CAS.
[ ] 409/412/404/503 mapped accurately per API contract.
[ ] Users authorized per tenant/device, not CQL RBAC alone.
[ ] TLS peer verification, secret manager, and least-privilege roles active.
[ ] Never log passwords, raw payloads, or sensitive keys in metric labels.

TEST / OPERATIONS
[ ] Tested version-0 inserts, stale updates, conditional deletes, and duplicates.
[ ] Tested concurrent same-version snapshots with single-winner conflict behavior.
[ ] Tested LWT timeouts, CAS false after unknown retries, and client disconnects.
[ ] Tested multi-DC, replica failures, and version TTL/delete/recreate.
[ ] Dashboards track CAS p50/p95/p99, contention/conflicts, timeouts, and retries.
[ ] Canaried/load-tested with realistic traffic/data; rollback plan ready.
~~~

~~~mermaid
flowchart TD
    A["Client wants to change a Cassandra row's state"] --> B["Read state + version and issue ETag"]
    B --> C["Client sends update with prior If-Match"]
    C --> D{"Client version still matches re-read state?"}
    D -->|No| E["412/409: conflict; require user decision"]
    D -->|Yes| F["Spring Data @Version or CQL IF version=?"]
    F --> G["LWT/Paxos per serial CL, regular CL"]
    G --> H{"Outcome?"}
    H -->|Applied| I["Return new version; success metric"]
    H -->|Not applied| E
    H -->|Timeout / Unknown| J["Reconcile state/operation ID, bounded retry"]
    J --> K["Never assume write failed; keep deadline"]
    I --> L["Metrics, canary, investigate contention if rising"]
    E --> L
    K --> L
~~~

## 27. References and Conclusion

Key principles in this lesson can be verified against official documentation:

1. [Spring Data Cassandra — Persisting Entities, Optimistic Locking](https://docs.spring.io/spring-data/cassandra/reference/cassandra/template.html): `@Version`, `IF NOT EXISTS`, `IF version`, `OptimisticLockingFailureException`, single-entity scope.
2. [Spring Data Cassandra — Mapping](https://docs.spring.io/spring-data/cassandra/reference/object-mapping.html): role of `@Version` and entity mapping.
3. [Spring Data — Repository Entity State Detection](https://docs.spring.io/spring-data/cassandra/reference/repositories/core-concepts.html): nullable version/new detection, `Persistable`, IDs.
4. [Apache Cassandra — CQL Data Manipulation](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html): `INSERT IF NOT EXISTS`, `UPDATE/DELETE IF`, TTL, timestamps, batches, and Paxos cost.
5. [Apache Cassandra — cqlsh, Consistency and Serial Consistency](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/cqlsh.html): regular/serial CL and conditional update behavior.
6. [DataStax Java Driver 4.17 — Statement API](https://docs.datastax.com/en/latest-java-driver-api/com/datastax/oss/driver/api/core/cql/Statement.html): `setConsistencyLevel`, `setSerialConsistencyLevel`, timeouts, and statement options. Consult the exact driver version docs when upgrading.

**Conclusion:** optimistic locking via **Spring Data Cassandra `@Version`** is not a Java mutex, a cross-HTTP lock, or a multi-table transaction. It relies on **LWT/Paxos** to check **versions directly inside the mutation** and accept or reject a single-entity update. `INSERT ... IF NOT EXISTS` guards key creation; `UPDATE/DELETE ... IF version=?` guards read state; `[applied]` or `OptimisticLockingFailureException` signals confirmed conflicts. Being production-ready requires guarding **HTTP `If-Match`, every writer, TTL/delete/generation lifecycles, regular and serial CL, multi-DC semantics, indeterminate timeout retries, rate/contention limits, and integration tests**. Use LWT **when invariants demand it** rather than enabling it on every write, because stronger correctness always pairs with capacity planning and operational observability.
