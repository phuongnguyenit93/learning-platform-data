# Organizing Durable Audit Storage and Distinguishing It from Ephemeral Memory

## 1. Starting from the question: after the application stops, where is the evidence?

An audit event describes an action that needs tracing: who performed it, at what time, what action occurred, which target was affected, and with what outcome. For example: account `alice` successfully approved invoice `invoice-42`.

If events sit only in a Java list, reading them back right after writing may succeed. Yet when the JVM terminates, that list disappears. A management UI currently displaying an event does not prove the system has long-term audit history.

This lesson focuses on the storage target and event path in Spring Boot Actuator: distinguishing in-memory stores from durable stores, implementing `AuditEventRepository` with JDBC, verifying across two Java processes, and identifying what else must be designed in production operations.

**Model to remember:** the producer creates the event; the repository receives and queries it; the storage system governs durability; the endpoint only provides a read path. These four roles do not substitute for one another.

## 2. How do ephemeral memory, buffers, and durable stores differ?

| Criterion | JVM in-memory store | Durable database audit store |
| --- | --- | --- |
| Where records live | Objects in process memory | Data committed by the database per durability configuration |
| When JVM restarts | Creates a new store, losing old data | Readable again if using the same database and data is still retained |
| Across multiple app replicas | Each replica has its own history | Can share a store for centralized lookup |
| When capacity fills | Bounded store may evict old records | Needs capacity planning, partitioning, and retention policy |
| Write cost | Typically low, no storage I/O wait | Involves I/O, latency, and possible connection errors |
| Typical purpose | Learning, observing most recent events | Retaining history for investigation and reconciliation per system requirements |

**Durable** means data is designed to survive defined classes of failures. It does not mean "impossible to lose in any scenario". For example, a database on the application host's disk can survive JVM restarts yet still be lost if the disk fails without a recovery backup.

This property depends on commit timing, the database's write mechanism, OS page caches, and storage hardware. Merely seeing a write API call succeed is insufficient to infer power-loss resilience of the whole system. See [PostgreSQL: Reliability](https://www.postgresql.org/docs/current/wal-reliability.html).

Further distinctions are needed:

- **Buffer:** holds events waiting to be forwarded. An in-RAM queue decouples processing rates but is lost with the process.
- **Cache:** keeps a copy for fast reads; the source data must live independently elsewhere. If an event exists only in cache, the cache is acting as the sole store.
- **Durable queue:** can hold events awaiting writes to the target store if persistence, acknowledgments, and retention are configured appropriately. Do not infer this merely because the system has a message broker.
- **Audit store:** the component responsible for retaining history for a defined period, providing queries, and supporting recovery.

A system may use all four components. You must specify where a record resides and which component confirmed holding it at each point in time.

## 3. Roles of APIs in Spring Boot Actuator

### 3.1. The AuditEventRepository contract

In Spring Boot 3.3.x, the repository has two primary operations:

```java
void add(AuditEvent event);

List<AuditEvent> find(String principal, Instant after, String type);
```

This is an API signature excerpt, not a standalone Java file.

`add` accepts an event. `find` searches by actor (`principal`), timestamp (`after`), and event type (`type`). For each search parameter, `null` means no restriction on that criterion; `after` means events occurring **strictly after** the supplied instant. When implemented in SQL, the corresponding condition is `occurred_at > :after`.

This interface does not dictate whether the backend must be RAM, JDBC, or another storage system; nor does it provide pagination or a stable event ID protocol for automatic deduplication. See [AuditEventRepository 3.3 Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/audit/AuditEventRepository.html).

### 3.2. InMemoryAuditEventRepository is useful but bounded

`InMemoryAuditEventRepository` keeps data inside the process and caps the number of retained events. Increasing capacity only extends the observation window; it does not make data survive JVM restarts.

Spring provides this implementation for development convenience and recommends building an alternative repository for production environments. Adding Actuator does not mean you already have a durable audit store. See [Spring Boot 3.3: Auditing](https://docs.spring.io/spring-boot/3.3/reference/actuator/auditing.html).

### 3.3. Do not equate auditing with HTTP history or Spring Data auditing

An HTTP exchange describes a request/response round-trip, such as path and status code. An audit event describes a meaningful action requiring traceability. One HTTP request can produce multiple events, zero events, or fail before business work begins.

`HttpExchangeRepository` and `AuditEventRepository` are two separate contracts. Replacing the audit repository does not automatically make HTTP history durable. Spring also recommends limiting `InMemoryHttpExchangeRepository` to development environments; see [Recording HTTP Exchanges](https://docs.spring.io/spring-boot/3.3/reference/actuator/http-exchanges.html).

Fields like "last modified by" or "last modified date" on an entity also do not create a history of every action. If an invoice row is repeatedly overwritten, its final state cannot fully answer who tried to do what earlier.

## 4. Organizing the write path and defining when data is retained

A simple synchronous write path can be structured as follows:

```text
Action requiring auditing
    -> construct selected event data
    -> AuditEventRepository.add(...)
    -> INSERT into database
    -> commit succeeds
    -> continue per application policy

Read path:
Authorized reader
    -> endpoint or query service
    -> AuditEventRepository.find(...)
    -> database
```

The diagram illustrates a design idea and does not claim every `add` call always commits on its own. If the call participates in an open transaction, the `INSERT` may succeed and then roll back with that transaction.

With an asynchronous write path, mark the states explicitly:

```text
Created -> sits in RAM -> held durably by intermediary system
        -> committed by target audit store
```

The first two states do not prove the event has been durably stored. When a process dies after enqueueing in RAM but before writing to the database, events can be lost. When the target store commits yet the sender misses the acknowledgment, retries can create duplicate records.

If a business change and its audit event must move together, one option is writing both in the same database transaction. If forwarding to another system is required, you can use a **transactional outbox**: write the business state and pending-delivery record in the same transaction, then have a forwarder read and resend as needed. The receiver still needs deduplication using a stable event ID.

For rejected logins or failed actions, the requirement may be to retain the event even when the business transaction rolls back. In that case, design an appropriate separate transaction boundary. Do not mechanically apply the same boundary to every event type.

These are architectural choices, not built-in guarantees of `AuditApplicationEvent` or the name "audit repository".

## 5. Designing records and organizing the store

An initial schema typically needs the following information:

| Field | Role |
| --- | --- |
| `event_id` | Identifies the event; if retries are needed, the ID must stay stable across attempts |
| `occurred_at` | Timestamp when the action occurred |
| `recorded_at` | Timestamp when the store received/saved it, useful when events arrive late |
| `principal_name` | Identity of the performing user or service, taken from a trusted context |
| `event_type` | Stable event type name, such as `INVOICE_APPROVED` |
| `target_id`, `outcome` | Affected target and outcome of the action |
| `correlation_id` | Links to the request or execution flow for investigation |
| `schema_version` | Interprets the data structure properly when formats evolve |

These are business model suggestions; Actuator's `AuditEvent` only has timestamp, principal, type, and an extra data map. The remaining fields must be standardized inside `data` or added at the storage layer.

Key decisions:

1. **Timestamps:** represent points in time with `Instant`; standardize UTC storage and precision when mapping to SQL. Do not use local time without offsets when correlating across servers. Clocks across machines can still drift, so timestamps alone do not establish strict causal ordering.
2. **Indexes:** derive from real queries. Lookups by actor and time may need a composite index; queries by event type or tenant may need another index. Do not index every JSON field out of habit.
3. **Multi-tenancy:** enforce tenant isolation at the query and authorization layers. `principal` is a filter criterion, not a cross-tenant data protection mechanism.
4. **Retention:** set policies by event type and purpose; do not assume keeping all data forever. Long-term retention, policy-based deletion, and backups are three distinct tasks.
5. **Recovery:** test restoring backups and re-verify row counts, timestamps, and read permissions. Having backup files without testing restoration leaves actual recovery capability unknown.
6. **Authorization:** separate write, query, schema-management, and deletion permissions. The event-writing application normally does not need permission to update or delete historical records.
7. **Sensitive data:** keep only necessary data. Do not store passwords, tokens, session cookies, or entire requests by default. Identities and contact addresses may also require restricted access.

**Durable storage and tamper resistance are two different properties.** A database row can survive restarts yet still be altered by an account with `UPDATE` privileges. If tamper detection is required, add corresponding design controls: restricted privileges, append-only storage, independent administrative audit trails, signatures, or specialized storage. A hash placed next to the data is insufficient if the same actor can modify both.

## 6. Hands-on: two Java processes, one file-backed store

The following example runs standalone in a learning directory, using Java 17+ and Maven 3.6.3+. JDK 21 can be used. Library versions are pinned to the lesson's Spring Boot 3.3.x branch; this is not a recommendation for choosing versions in a production system.

The program uses Actuator's real auditing API without starting an HTTP server. The goal is to isolate the storage test: the first process writes, and the second process only reads. There is no need to build fake business endpoints to prove durability.

### 6.1. Structure and dependencies

Create a new directory `audit-store-lab` with the structure:

```text
audit-store-lab/
├── pom.xml
└── src/main/java/demo/
    ├── JdbcAuditEventRepository.java
    └── AuditStoreDemo.java
```

Contents of `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.13</version>
    <relativePath/>
  </parent>
  <groupId>example</groupId>
  <artifactId>audit-store-lab</artifactId>
  <version>1.0.0</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-actuator</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-jdbc</artifactId>
    </dependency>
    <dependency>
      <groupId>com.fasterxml.jackson.core</groupId>
      <artifactId>jackson-databind</artifactId>
    </dependency>
    <dependency>
      <groupId>com.h2database</groupId>
      <artifactId>h2</artifactId>
      <scope>runtime</scope>
    </dependency>
  </dependencies>
</project>
```

The parent manages dependency versions. `spring-boot-actuator` provides `AuditEvent` and repository types; `spring-jdbc` provides JDBC utilities; Jackson converts selected data to JSON; H2 is the database driver.

### 6.2. Implementing the JDBC repository

File `src/main/java/demo/JdbcAuditEventRepository.java`:

```java
package demo;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.boot.actuate.audit.AuditEvent;
import org.springframework.boot.actuate.audit.AuditEventRepository;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

public final class JdbcAuditEventRepository implements AuditEventRepository {
    private static final Set<String> ALLOWED_KEYS = Set.of(
            "action", "targetId", "outcome", "correlationId");

    private final NamedParameterJdbcTemplate jdbc;
    private final ObjectMapper json;

    public JdbcAuditEventRepository(
            NamedParameterJdbcTemplate jdbc, ObjectMapper json) {
        this.jdbc = jdbc;
        this.json = json;
    }

    @Override
    public void add(AuditEvent event) {
        Map<String, Object> safeData = new LinkedHashMap<>();
        event.getData().forEach((key, value) -> {
            if (ALLOWED_KEYS.contains(key) && value instanceof String text) {
                if (text.length() > 256) {
                    throw new IllegalArgumentException("Audit field too long: " + key);
                }
                safeData.put(key, text);
            }
        });

        var parameters = new MapSqlParameterSource()
                .addValue("id", UUID.randomUUID().toString())
                .addValue("at", utc(event.getTimestamp()))
                .addValue("principal", event.getPrincipal())
                .addValue("type", event.getType())
                .addValue("data", encode(safeData));

        jdbc.update("""
                INSERT INTO audit_event
                    (event_id, occurred_at, principal_name, event_type, data_json)
                VALUES (:id, :at, :principal, :type, :data)
                """, parameters);
    }

    @Override
    public List<AuditEvent> find(String principal, Instant after, String type) {
        StringBuilder sql = new StringBuilder("""
                SELECT occurred_at, principal_name, event_type, data_json
                FROM audit_event WHERE 1 = 1
                """);
        var parameters = new MapSqlParameterSource();

        if (principal != null) {
            sql.append(" AND principal_name = :principal");
            parameters.addValue("principal", principal);
        }
        if (after != null) {
            sql.append(" AND occurred_at > :after");
            parameters.addValue("after", utc(after));
        }
        if (type != null) {
            sql.append(" AND event_type = :type");
            parameters.addValue("type", type);
        }
        sql.append(" ORDER BY occurred_at, event_id");

        return jdbc.query(sql.toString(), parameters, (rs, rowNumber) ->
                new AuditEvent(
                        rs.getObject("occurred_at", OffsetDateTime.class).toInstant(),
                        rs.getString("principal_name"),
                        rs.getString("event_type"),
                        decode(rs.getString("data_json"))));
    }

    private static OffsetDateTime utc(Instant instant) {
        return OffsetDateTime.ofInstant(instant, ZoneOffset.UTC);
    }

    private String encode(Map<String, Object> data) {
        try {
            return json.writeValueAsString(data);
        } catch (JsonProcessingException ex) {
            throw new IllegalArgumentException("Cannot encode audit data", ex);
        }
    }

    private Map<String, Object> decode(String text) {
        try {
            return json.readValue(text, new TypeReference<Map<String, Object>>() {});
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException("Cannot decode stored audit data", ex);
        }
    }
}
```

Points to read carefully:

- The SQL statement uses named parameters for external data. String concatenation only appends fixed clauses and never concatenates `principal` or `type` values directly into SQL.
- The three filters are independent and can each be skipped with `null`. `after` uses `>`, not `>=`.
- Timestamps are written as `OffsetDateTime` in UTC and read back as `Instant`.
- `data` is restricted by an allowlist of keys and accepts only string values. Arbitrary complex data in security events is not automatically serialized as full object graphs.
- The example rejects allowed strings longer than 256 characters. This is a lab rule, not a general limit of `AuditEvent`.
- Encoding errors, SQL errors, and JSON parsing errors are propagated. Do not catch all errors and pretend writes succeeded or return an empty list.
- `ORDER BY occurred_at, event_id` produces deterministic query order for existing records; random UUIDs do not represent actual action order.

This repository generates a new UUID on every `add`. That suffices for testing individual writes, yet **does not prevent duplicates on retries**. Do not call it an "exactly once" solution. A system requiring retries must identify the same event with a stable ID generated before the first attempt.

The key allowlist also does not guarantee value contents are always safe: a `correlationId` or `targetId` can still carry data that should not be stored if the producer breaks conventions. Control both event creation and store query permissions.

### 6.3. Write and read program

File `src/main/java/demo/AuditStoreDemo.java`:

```java
package demo;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.boot.actuate.audit.AuditEvent;
import org.springframework.boot.actuate.audit.InMemoryAuditEventRepository;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.Map;

public class AuditStoreDemo {
    public static void main(String[] args) throws Exception {
        if (args.length != 1
                || (!args[0].equals("write") && !args[0].equals("read"))) {
            throw new IllegalArgumentException("Use write or read");
        }

        Files.createDirectories(Path.of("data"));
        var source = new DriverManagerDataSource(
                "jdbc:h2:file:./data/audit;WRITE_DELAY=0", "sa", "");
        var jdbc = new NamedParameterJdbcTemplate(source);

        jdbc.getJdbcTemplate().execute("""
                CREATE TABLE IF NOT EXISTS audit_event (
                    event_id VARCHAR(36) PRIMARY KEY,
                    occurred_at TIMESTAMP(9) WITH TIME ZONE NOT NULL,
                    principal_name VARCHAR(200) NOT NULL,
                    event_type VARCHAR(100) NOT NULL,
                    data_json CLOB NOT NULL
                )
                """);
        jdbc.getJdbcTemplate().execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_principal_time
                ON audit_event (principal_name, occurred_at, event_id)
                """);

        var durable = new JdbcAuditEventRepository(jdbc, new ObjectMapper());
        var memory = new InMemoryAuditEventRepository(2);
        Instant at = Instant.parse("2026-01-01T00:00:00Z");

        if (args[0].equals("write")) {
            var event = new AuditEvent(at, "alice", "INVOICE_APPROVED", Map.of(
                    "action", "approve",
                    "targetId", "invoice-42",
                    "outcome", "success",
                    "correlationId", "request-7",
                    "password", "DO_NOT_STORE"));
            memory.add(event);
            durable.add(event);
        }

        var events = durable.find("alice", null, "INVOICE_APPROVED");
        System.out.println("mode=" + args[0]);
        System.out.println("memory.count=" + memory.find(null, null, null).size());
        System.out.println("durable.count=" + events.size());
        System.out.println("durable.afterExact="
                + durable.find("alice", at, "INVOICE_APPROVED").size());
        System.out.println("durable.afterBefore="
                + durable.find("alice", at.minusSeconds(1), "INVOICE_APPROVED").size());
        System.out.println("durable.wrongPrincipal="
                + durable.find("bob", null, null).size());
        System.out.println("durable.passwordStored="
                + events.stream().anyMatch(e -> e.getData().containsKey("password")));
        if (!events.isEmpty()) {
            System.out.println("durable.target=" + events.get(0).getData().get("targetId"));
        }
    }
}
```

The URL `jdbc:h2:file:./data/audit` creates a file-backed store in the working directory. Do not use `jdbc:h2:mem:...` for a test meant to survive across two JVMs. Setting `DB_CLOSE_DELAY=-1` on an in-memory database also does not keep it alive past JVM termination.

`WRITE_DELAY=0` tells H2 not to delay writes by the configured interval; the test below still only proves reopening after normal process termination. Do not extrapolate the result into a certification against power loss or disk failure. See [H2: Connection Modes and In-Memory Databases](https://h2database.com/html/features.html).

The table uses `TIMESTAMP(9) WITH TIME ZONE` for H2. When moving to another backend, adjust DDL, JSON column types, and timestamp precision for that backend; do not copy the DDL verbatim and assume every database supports it identically.

`DriverManagerDataSource` opens direct connections so the lab stays easy to follow. In a real application, use a managed `DataSource` with connection pooling and appropriate configuration. Creating the table in `main` is for the practice lab only; production schemas should be managed with versioned migrations.

### 6.4. Compiling and running two JVMs

Run from the `audit-store-lab` directory. On the first run, Maven needs network access to fetch dependencies. Use a fresh practice directory without `data/audit.mv.db` so the counts below match exactly.

On PowerShell:

```powershell
mvn -q package dependency:build-classpath "-Dmdep.outputFile=classpath.txt"
$cp = "target/classes;" + (Get-Content -LiteralPath classpath.txt -Raw).Trim()
java -cp $cp demo.AuditStoreDemo write
java -cp $cp demo.AuditStoreDemo read
```

On Linux/macOS, after the same Maven command:

```bash
cp="target/classes:$(cat classpath.txt)"
java -cp "$cp" demo.AuditStoreDemo write
java -cp "$cp" demo.AuditStoreDemo read
```

Maven performs compilation; each `java` command above spawns a new process. Do not open two concurrent processes against the same embedded H2 file in this lab.

Stdout of the first `write` run:

```text
mode=write
memory.count=1
durable.count=1
durable.afterExact=0
durable.afterBefore=1
durable.wrongPrincipal=0
durable.passwordStored=false
durable.target=invoice-42
```

Stdout of the `read` run immediately afterward:

```text
mode=read
memory.count=0
durable.count=1
durable.afterExact=0
durable.afterBefore=1
durable.wrongPrincipal=0
durable.passwordStored=false
durable.target=invoice-42
```

Explanation of each piece of evidence:

1. `memory.count` drops from 1 to 0 because the second JVM creates a fresh RAM repository.
2. `durable.count` remains 1 because the second JVM reopens the same file-backed store; the `read` branch adds no event.
3. Passing `after` equal to the event's exact timestamp yields 0. One second earlier yields 1, confirming the "strictly after" semantics.
4. Filtering for `bob` returns 0 because the record belongs to `alice`.
5. The `password` key was placed in the event with a dummy value for illustration, yet was not written to the JDBC store because it was not on the allowlist.
6. The allowed `targetId` is read back, showing supplementary data is not discarded wholesale.

If you run `write` one more time, the JDBC record count increases: the example has no deduplication mechanism yet. If you run `read` from a different working directory, the relative path may point to a different database. Both behaviors must be ruled out before concluding a storage bug exists.

Do not delete the data file during the re-read test. To repeat from an empty state without affecting old data, create a new practice directory.

## 7. Integrating the repository into a Spring Boot application

The snippet below is **integration code**, not a standalone runnable program. Assume the Spring Boot application already has Actuator, JDBC, Jackson, database driver, `DataSource`, and a migration-created schema. Place the configuration class in a scanned package and reuse the repository class from the lab.

```java
package demo;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.boot.actuate.audit.AuditEventRepository;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

@Configuration(proxyBeanMethods = false)
public class AuditStorageConfiguration {
    @Bean
    AuditEventRepository auditEventRepository(
            NamedParameterJdbcTemplate jdbc, ObjectMapper objectMapper) {
        return new JdbcAuditEventRepository(jdbc, objectMapper);
    }
}
```

The application must configure its backend explicitly per environment. Do not register both a RAM repository and a JDBC repository at the same time and leave bean selection to chance via dependency injection.

Producers can write directly through `AuditEventRepository` or publish `AuditApplicationEvent` for Boot's audit infrastructure to receive when configured appropriately. Choose one write path per event; doing both can write twice. The in-process application event mechanism is not a durable queue by itself. Both integration styles are described in [Spring Boot: Custom Auditing](https://docs.spring.io/spring-boot/3.3/reference/actuator/auditing.html#actuator.auditing.custom).

Providing the repository bean and exposing read access over HTTP are two separate decisions. In a web application, you may choose to expose `auditevents` if operators genuinely need it, but you must configure authentication, authorization, and access limits. Do not expose audit history publicly simply because you moved data to a database.

The `auditevents` endpoint queries through the repository; being able to read the endpoint does not prove data persists long-term. The endpoint itself also does not replace a large-scale history search interface with pagination and dedicated permission policies. See [Actuator Web API: Audit Events](https://docs.spring.io/spring-boot/api/rest/actuator/auditevents.html).

## 8. Parts to add before running in production

### 8.1. Defining behavior when writes fail

No single choice fits every event:

| Option | Benefit | Trade-off to address |
| --- | --- | --- |
| Wait for synchronous write before proceeding | Detects write errors immediately in the execution flow | Increases latency; depends on store availability |
| Write state and audit/outbox in the same transaction | Preserves consistent relationship in one database | Must clarify success/failure events and rollback boundaries |
| Send via durable intermediary | Decouples ingestion rate from target store write rate | Needs delivery acks, backlog limits, retries, and deduplication |
| Allow proceeding even if audit fails | Avoids blocking certain allowed operations | Must accept data gaps and make them observable |

Policy must align with the criticality of the action. When the requirement is "must not proceed unless evidence is retained", you cannot merely log the error and return success. If proceeding is accepted, document clearly the scope of potential data loss.

When a connection drops right after commit, the caller may not know whether the write succeeded. Retries must reuse the same event ID and deduplication constraint; do not generate a new ID per send.

### 8.2. Bounding reads and capacity

`find` in the example returns every record matching the criteria, which suits a small lab dataset. Do not use this pattern unchanged to open years of history in a single request.

In large systems, design a dedicated query service with time windows, page sizes, and stable cursors, typically based on a timestamp/event-ID pair. Do not silently add `LIMIT 100` inside the repository and mislead readers into thinking they received complete history.

Plan for generation rate, event size, indexes, retention period, partitioning, and long-term archival. Policy-based deletion processes require separate permissions and appropriate administrative audit trails.

### 8.3. Observing the audit write path itself

Observe at least write failures, write latency, retry counts, backlog size, and age of undelivered events. If there is a path that drops events, the drop count must be visible; do not lose data silently when a queue fills.

Do not use individual `event_id` values or individual usernames as metric tags with unbounded cardinality. Metrics report write-path health, while event details live in the access-controlled store.

Verify multiple application replicas writing to and reading from the same store, restoring from backups, JSON schema evolution, and clock synchronization. "Moved from List to SQL" solves only part of the problem.

## 9. Verifying by scenarios, not just seeing one record

| Scenario | What to observe |
| --- | --- |
| Write then read in the same JVM | Verifies basic flow; does not prove survival across restarts |
| Write, exit JVM, start new JVM read-only | Durable store data remains; new RAM store is empty |
| Exceed RAM store capacity | Older records may be evicted; must not be treated as complete history |
| Query with `after` at exact timestamp | Events at the exact boundary are not returned |
| Omit each filter with `null` | Drops only the corresponding filter without unintentionally dropping others |
| Target store unreachable | Observe the right block/continue/retry policy without false success |
| Resend the same event | With complete deduplication design, creates no duplicate business record |
| Payload contains sensitive fields | Only policy-permitted information appears in the store |
| Two application replicas | Authorized readers can query centralized history as designed |
| Restore to a new store | Data and read permissions restore within the stated scope |

The two-JVM test above illustrated normal reopening, time/actor filters, and data allowlisting. Power-loss, load-saturation, multi-node, and recovery scenarios require dedicated operational tests; do not treat them as passed based solely on this lesson's stdout.

## 10. Common mistakes and self-check exercises

Easy mistakes to make:

- Using an in-memory repository for history that must be kept long-term, then raising capacity when discovering missing events.
- Switching to SQL but putting data in ephemeral container storage; replacing the container wipes the store.
- Keeping backups only on the application host without a backup/restore policy.
- Swallowing write errors or returning an empty list when the database fails, causing "unreadable" to be misread as "no events".
- Adding `@Async` and concluding events are now durably stored.
- Treating HTTP `200` as proof a business action succeeded, or equating all HTTP exchanges with auditing.
- Accepting `principal` from a user-supplied request field and treating it as a verified identity.
- Writing all of `event.getData()` without deciding which fields are permitted.
- Writing audit records inside a transaction that rolls back while expecting to keep failure trails.
- Assuming a SQL store is automatically tamper-proof or treating an Actuator endpoint as a full history search tool.

**Exercise 1:** In a three-replica application, each replica uses `InMemoryAuditEventRepository`. Why does querying through a load balancer sometimes show the event and sometimes not?

**Answer hint:** Each JVM holds a separate store. The write request and the read request can hit different replicas. A shared store or suitable centralized collection architecture is needed; sticky sessions alone do not prevent data loss when a replica stops.

**Exercise 2:** In the lab, run `write` twice and then run `read`. Predict the counts and explain.

**Answer hint:** Starting from an empty store, JDBC has 2 records because each `add` generates a new UUID; the `read` run has `memory.count=0`. `durable.afterBefore` equals 2, while `durable.afterExact` remains 0. Data surviving across JVMs does not equate to duplicate-write prevention.

**Exercise 3:** An application returns success immediately after putting an event into an in-RAM `BlockingQueue`. The process stops before the writer thread drains the event. Can complete history be claimed?

**Answer hint:** No. The event had not reached a durable storage point. Change the confirmation path, use a durable intermediary, or accept and explicitly document the gap per policy.

After this lesson, the criterion for evaluating an audit store is not "does the endpoint return JSON", but knowing where data is held, when it is confirmed, which failure modes it survives, who can read or modify it, and what test evidence supports those conclusions.
