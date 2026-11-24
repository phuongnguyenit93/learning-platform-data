# Designing Safe Repeatable Runners for Data Seeding or Cache Warm-Up in Spring Boot

## 1. The Problem: Startup Is Not a Once-Only Event

A Spring Boot application often performs several tasks after creating the ApplicationContext yet before being considered fully started:

- **Seeding baseline data:** creating a system account, default statuses, standard code catalogs, or required configuration if they do not exist yet.
- **Warming up caches:** reading frequently accessed records from the primary data source to reduce latency on initial requests.
- **Checking mandatory conditions:** verifying minimal data/configuration is ready before serving.
- **Preparing lookup structures:** building an immutable snapshot, in-memory index, or mapping table generated from current data.

In Spring Boot, **ApplicationRunner** and **CommandLineRunner** are suitable hooks for this kind of work after context refresh succeeds. However, production environments do not guarantee that each application, pod, or job starts strictly once:

- Pods may be restarted by deployments, autoscaling, or runtime errors.
- An instance may die mid-seed; orchestration will rerun it.
- Multiple replicas may start concurrently and race to create a default record.
- Operators may redeploy the same version.
- Tests may create contexts multiple times.
- A runner may be invoked again manually in tests or controlled recovery procedures.

Therefore, the goal is not **"execute strictly once,"** but **"no matter how many times it runs, it never corrupts valid state."** This property is called **idempotency**.

### Practical Definition

For an initialization operation F on state S, idempotency is commonly expressed as:

~~~text
F(F(S)) = F(S)
~~~

Meaning running it again does not alter the desired outcome. In real systems, define "does not alter" per data and side effect:

- For seeding: do not generate duplicate records; do not overwrite values modified by administrators.
- For warm-up: the final cache holds one valid lookup copy from the current source, without accumulating or overlaying broken snapshots.
- For external actions: do not resend emails, recharge payments, or recreate external resources if the system already completed the operation previously.

**Idempotent does not automatically mean "exactly once."** A step may execute multiple times; good design ensures repeated runs produce the same desired state or are detected as already processed.

## 2. Where Do Runners Sit in the Spring Boot Lifecycle?

In the default successful startup flow:

~~~text
SpringApplication.run(args)
          |
          v
Prepare Environment and create ApplicationContext
          |
          v
Load BeanDefinitions, refresh Context
          |
          +--> Initialize non-lazy singletons
          +--> @PostConstruct / BeanPostProcessor
          +--> ContextRefreshedEvent
          |
          v
ApplicationStartedEvent
          |
          v
ApplicationRunner / CommandLineRunner
          |
          +--> seed missing mandatory data
          +--> read source data
          +--> build cache snapshot
          +--> verify results and return
          |
          v
ApplicationReadyEvent
          |
          v
ReadinessState.ACCEPTING_TRAFFIC
          |
          v
SpringApplication.run returns
~~~

**ApplicationRunner** has **run(ApplicationArguments args)**; **CommandLineRunner** has **run(String... args)**. Both are discovered by Spring Boot as beans and executed **after ApplicationContext refresh** and **before ApplicationReadyEvent**. They suit startup work using already-created Spring beans such as **JdbcTemplate**, repositories, transaction services, or cache managers.

### What Runners Guarantee — and Do Not Guarantee

| Condition | Meaning |
| --- | --- |
| Runner starts | Context refreshed successfully |
| Runner completes normally | **Synchronous** work inside `run` has returned |
| All runners complete | Spring Boot can proceed to publish ApplicationReadyEvent |
| Runner throws unhandled exception | Boot treats startup as failed, does not publish normal ApplicationReadyEvent |
| Runner merely submits a Future and returns | **Does not guarantee** background work finished when app is ready |
| Web server bound its port | Does not guarantee direct client requests wait for runners to finish |
| ApplicationReadyEvent published | Does not guarantee external dependencies stay healthy later |

In Kubernetes environments, use a proper **readiness probe** to control traffic admission. An open TCP port is not proof that mandatory data/caches are ready.

## 3. Dividing Work Into Two Groups with Clear Contracts

### 3.1. Seeding Baseline Data: Protecting the Source of Truth

A safe seed operation must answer:

1. **Existence condition:** which stable identifier (natural key/unique key) identifies the record?
2. **Data immutability:** may an already-edited record be overwritten?
3. **Atomicity:** are checking and writing data safe when multiple instances run concurrently?
4. **Transactions:** if seeding multiple related tables, is a half-written state acceptable?
5. **Repeatability:** after a mid-step crash, does the next run finish the remainder without creating duplicates?
6. **Versioning:** when seeding new versioned data, is a migration tool needed rather than repeated startup operations?

Example: a catalog with code **DEFAULT**. A safe goal is **"if DEFAULT does not exist, create it; if it exists, leave it unchanged."** If an operator renames DEFAULT's display name, restarts must not automatically revert to the old name unless that is an explicitly stated business rule.

### 3.2. Cache Warm-Up: Building a Replaceable Derived State

A cache is usually **derived data**, not the source of truth. Proper warm-up means:

1. Read from a consistent and reliable primary source.
2. Build a new snapshot **outside the data structure currently read by clients**.
3. Validate invariants: sufficient data, appropriate size, unique/non-null keys.
4. **Atomically publish/swap** the new snapshot or update the cache under a controlled strategy.
5. If rebuilding fails, **never publish a half-built snapshot**; decide whether to retain the old snapshot, fail startup, or mark readiness based on criticality.

For local caches, snapshots can be lost on every restart; that is normal. Idempotency here does not require surviving restarts in memory, but rather **after each successful warm-up, the cache reflects accurate data**.

## 4. Anti-Patterns to Avoid

| Common Mistake | Why It Is Unsafe | Better Approach |
| --- | --- | --- |
| Unconditional INSERT on every startup | Creates duplicates or unique constraint errors | Use a unique business key and appropriate insert-if-absent / DB upsert |
| SELECT to check absence, then INSERT | Two replicas can both observe absence | Let the database enforce unique keys and handle conflicts |
| "Seeding" by UPDATE-ing all values every time | Overwrites valid operator changes | Clearly define immutable vs. default-only data |
| Ignoring all DataAccessExceptions | Masks lost connections, bad schemas, permission errors | Handle only expected duplicate-key errors; surface all others |
| Appending to a list/map on every warm-up | Cache accumulates stale entries or wrong data | Build a fresh snapshot and replace in a controlled way |
| Cache.clear() then gradually put before readers | Readers observe empty or partial caches | Atomic swap or consistency-supporting cache refresh mechanism |
| Using @PostConstruct for long DB calls | Context still initializing beans; hard to govern readiness | Use runners/services after refresh when appropriate |
| Runner submits async task and returns | Boot may emit ready before cache is built | Await bounded task or manage readiness explicitly |
| Relying on JVM synchronized to prevent duplicate seed | Lock only works inside one instance | Unique constraints/transactions or distributed coordination |
| Expecting "execute once" via an in-memory boolean | Restarts or other replicas do not see that state | Durable markers/versions/unique keys in the source of truth |

## 5. Designing Idempotent Seeding at the Database Layer

### 5.1. Enforce a Real Unique Constraint

Suppose a catalog table:

~~~sql
CREATE TABLE catalog (
    code VARCHAR(40) PRIMARY KEY,
    display_name VARCHAR(120) NOT NULL
);
~~~

**code** is a stable business key. The database guarantees that even if **two replicas** simultaneously try to create **code=DEFAULT**, only one record can exist.

### 5.2. Avoid Check-Then-Insert Races

The logic below is **not safe enough** under concurrent execution:

~~~java
if (!repository.existsById("DEFAULT")) {
    repository.save(new CatalogItem("DEFAULT", "Default"));
}
~~~

This is an **illustrative JPA snippet**, not standalone runnable code. Processes A and B can both receive **exists=false**, then both INSERT. With a primary key, one process receives a constraint error; without a constraint, data is duplicated.

A safer approach is **pushing the invariant into the database**:

- PostgreSQL: **INSERT ... ON CONFLICT (code) DO NOTHING** for default-only seeds.
- Some databases have **MERGE** or other insert-if-absent syntax; verify transaction/isolation and semantics for each engine.
- If no unified no-op-on-conflict syntax is available, attempt **INSERT** and handle only **DuplicateKeyException** for the expected constraint.
- For multi-table seeds, define transaction boundaries and constraint ordering.

**Avoid blindly using ON CONFLICT DO UPDATE** when the requirement is creating defaults once: UPDATE can overwrite user-modified values. Business rules must dictate whether a seed is **immutable reference data**, **default-only**, or **versioned correction**.

### 5.3. Ignore Only Explicitly Accepted Errors

~~~java
try {
    jdbcTemplate.update(
            "INSERT INTO catalog(code, display_name) VALUES (?, ?)",
            "DEFAULT", "Default");
} catch (DuplicateKeyException alreadyExists) {
    // A record with the same code already exists: do not overwrite.
}
~~~

The snippet above is an **illustrative code fragment** requiring JdbcTemplate/DuplicateKeyException imports and a table with a unique key. For invalid data, connection loss, missing schemas, or wrong permissions, the program **must not** catch **Exception** and silently continue. When seeding is mandatory, those real failures must fail startup and be logged properly.

Still, even with DuplicateKeyException, make sure the violated constraint is genuinely the key your logic allows to already exist. If a table has multiple unique constraints and the INSERT could violate another constraint, use SQL targeting **the exact business key** on conflict or classify errors more precisely.

## 6. Complete Java 17+ Example: Repeatable Catalog Seeding and Cache Warm-Up

This example uses **Spring Boot 3.5.x**, Java 17+, Maven, **Spring JDBC**, and **file-backed H2**. File-backed H2 is used so data **persists across application restarts**; using only in-memory H2 creates a fresh database on every process run and cannot verify data preservation across restarts.

The program will:

1. Create the table using a repeatable SQL script in H2.
2. Inside **ApplicationRunner**, attempt to insert the DEFAULT catalog record via INSERT.
3. If DEFAULT already exists, preserve its existing value.
4. Read the entire table into a temporary map.
5. Replace the local cache with an **immutable snapshot** via a **volatile** reference assignment.
6. **Invoke the same logic twice** in a single launch and print row/cache counts.
7. When restarting the program against the same H2 file, avoid creating duplicate records.

### 6.1. Creating the Maven Project

Using **Spring Initializr**, choose **Java 17+**, **Spring Boot 3.5.x**, group **com.example**, artifact **repeatable-startup**, package **com.example.demo**. Select:

- **JDBC API / Spring JDBC** (corresponding to Spring Boot Starter JDBC).
- **H2 Database**.

In the Initializr-generated POM, the equivalent core dependencies are:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
        <groupId>com.h2database</groupId>
        <artifactId>h2</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

This is **only the dependencies section**, not a standalone pom.xml file. Let Spring Boot's parent/BOM manage compatible versions. Spring Web is unnecessary because this exercise uses a **non-web application**.

File structure:

~~~text
repeatable-startup/
├── pom.xml
├── mvnw
├── mvnw.cmd
└── src/main/
    ├── java/com/example/demo/RepeatableStartupApplication.java
    └── resources/
        ├── application.properties
        └── schema.sql
~~~

### 6.2. Configuring the DataSource and SQL Init

File **src/main/resources/application.properties**:

~~~properties
spring.application.name=repeatable-startup
spring.main.web-application-type=none
spring.datasource.url=jdbc:h2:file:./repeatable-seed-db;DB_CLOSE_ON_EXIT=FALSE
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
~~~

- **jdbc:h2:file:./repeatable-seed-db** creates/stores the H2 database on the filesystem relative to the working directory; database files remain when the process exits normally.
- **DB_CLOSE_ON_EXIT=FALSE** ensures H2 does not rely on its own JVM shutdown hook to close the database; the Spring-managed DataSource pool still closes normally.
- **spring.sql.init.mode=always** instructs Boot to execute SQL initialization scripts even for file-based datasources rather than relying solely on embedded-database detection.
- **spring.main.web-application-type=none** lets the project run runners and exit without needing an HTTP server.

In real projects, never store production passwords in source code. H2 here is strictly for learning; production typically uses PostgreSQL/MySQL and an appropriate migration tool.

File **src/main/resources/schema.sql**:

~~~sql
CREATE TABLE IF NOT EXISTS catalog (
    code VARCHAR(40) PRIMARY KEY,
    display_name VARCHAR(120) NOT NULL
);
~~~

**CREATE TABLE IF NOT EXISTS** is H2 syntax used in this example, not a guarantee that the exact same script runs on every database. When the application starts a second time, this script neither recreates nor deletes existing data.

Note: do not put **DROP TABLE** or **TRUNCATE** into startup schema scripts if your goal is preserving seeded data across restarts.

### 6.3. Complete Java Program

Create **src/main/java/com/example/demo/RepeatableStartupApplication.java**:

~~~java
package com.example.demo;

import java.util.HashMap;
import java.util.Map;
import java.util.Optional;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootApplication
public class RepeatableStartupApplication {

    public static void main(String[] args) {
        SpringApplication.run(RepeatableStartupApplication.class, args);
    }

    @Bean
    LookupCache lookupCache() {
        return new LookupCache();
    }

    @Bean
    ApplicationRunner seedAndWarmUp(
            JdbcTemplate jdbcTemplate,
            LookupCache cache) {

        return args -> {
            // Two passes in the same startup to verify repeatability.
            for (int pass = 1; pass <= 2; pass++) {
                ensureDefaultRow(jdbcTemplate);
                warmUpCache(jdbcTemplate, cache);

                Long rows = jdbcTemplate.queryForObject(
                        "SELECT COUNT(*) FROM catalog", Long.class);

                System.out.println("pass=" + pass
                        + ", rows=" + rows
                        + ", cache=" + cache.size()
                        + ", default="
                        + cache.find("DEFAULT").orElse("MISSING"));
            }
        };
    }

    private static void ensureDefaultRow(JdbcTemplate jdbcTemplate) {
        try {
            jdbcTemplate.update(
                    "INSERT INTO catalog(code, display_name) "
                            + "VALUES (?, ?)",
                    "DEFAULT", "Default");
        } catch (DuplicateKeyException alreadyExists) {
            // PRIMARY KEY code already exists; keep existing record.
        }
    }

    private static void warmUpCache(
            JdbcTemplate jdbcTemplate, LookupCache cache) {

        Map<String, String> next = new HashMap<>();

        jdbcTemplate.query(
                "SELECT code, display_name FROM catalog",
                rs -> {
                    next.put(
                            rs.getString("code"),
                            rs.getString("display_name"));
                });

        // Publish snapshot only after reading completes successfully.
        cache.replace(next);
    }

    static final class LookupCache {
        private volatile Map<String, String> snapshot = Map.of();

        void replace(Map<String, String> data) {
            snapshot = Map.copyOf(data);
        }

        int size() {
            return snapshot.size();
        }

        Optional<String> find(String code) {
            return Optional.ofNullable(snapshot.get(code));
        }
    }
}
~~~

**This is a complete Java file**, not pseudocode, when placed inside a project with the dependencies above. Maven provides Spring JDBC/H2 on the classpath; you cannot compile/run solely with **javac RepeatableStartupApplication.java** without supplying the Spring libraries.

### 6.4. Explaining the Key Mechanisms

**ApplicationRunner** is invoked by Spring Boot after refresh. **JdbcTemplate** and **LookupCache** are already beans eligible for injection into the runner.

**ensureDefaultRow(...)** attempts to INSERT with primary key DEFAULT:

- If absent, adds one record.
- If already present, H2 returns a duplicate-key error; Spring JDBC translates it to **DuplicateKeyException**. The program treats this specific case as "already seeded."
- Any other data-access errors are not caught here; they fail the runner and prevent normal ready publication.
- Because no UPDATE is issued, user-edited `display_name` values are not overwritten.

**warmUpCache(...)** builds a fresh **Map next** instead of mutating the map readers are currently using. Once the JDBC query succeeds completely, **cache.replace(next)** calls **Map.copyOf** and assigns the volatile reference. Every reader sees either **the complete old snapshot or the complete new snapshot**, never a cleared or half-populated map.

**volatile** provides cross-thread visibility of the snapshot reference. It does not turn **reading DB + publishing cache** into a cross-system transaction; if the DB changes right after the query, the cache can still quickly become stale. For near-real-time updates, add TTLs, invalidation, or refresh strategies.

Because the example uses a single runner performing both steps in sequence, **seeding must succeed before warm-up runs**. It does not depend on incidental ordering between two separate runners.

### 6.5. First Run and Verification

From the project root directory:

~~~bash
# Linux/macOS
./mvnw spring-boot:run

# Windows PowerShell or Command Prompt:
# .\mvnw.cmd spring-boot:run
~~~

With a fresh database and no other configuration changes, the two lines explicitly printed by the program are:

~~~text
pass=1, rows=1, cache=1, default=Default
pass=2, rows=1, cache=1, default=Default
~~~

These are the lines from the runner, **not all of stdout** (Maven/Spring Boot emit other logs). Two consecutive passes do not add a second record.

### 6.6. Re-Running After a Restart

Stop the process if running, then run the exact same command from the **same working directory**. H2 preserves the database files. **CREATE TABLE IF NOT EXISTS** does not wipe the table, and duplicate-key INSERTs are handled.

With the database still containing only the DEFAULT record from before, the runner's output remains:

~~~text
pass=1, rows=1, cache=1, default=Default
pass=2, rows=1, cache=1, default=Default
~~~

This tests **re-running the same startup logic**, not simulating "a blank database every time." If you added extra rows or edited DEFAULT's name, the counts and name in the output reflect current data—which is the right behavior, not a bug.

### 6.7. Proving Seeding Does Not Overwrite Existing Edits

Use an H2 SQL client or H2 Console to connect to the database file while the application is stopped, change DEFAULT's `display_name` to **"Admin-Edited Name"**, then restart. The runner still executes INSERT, yet because the key exists it does not overwrite. The cache loads from the table and picks up the new name.

By contrast, if seeding used **MERGE** with a default "when matched then UPDATE" clause, that name would be overwritten back to **"Default"** on restart. This illustrates why you must clarify whether seeding is **default-only** or **synchronization/update**.

### 6.8. Limitations of the Example

- File-backed H2 is for learning and single-machine runs. **Never share an H2 file as a multi-pod database**.
- **schema.sql** suits demos; production typically uses versioned migrations and controlled release workflows.
- The table has only one primary key and one expected INSERT pattern, so catching DuplicateKeyException is intentional. With more complex schemas, inspect the exact allowed conflict.
- The cache is a **per-process local snapshot**, not automatically synchronized across replicas. If a distributed cache is needed, add invalidation/versioning protocols.
- The runner executes two passes to demonstrate idempotency. Production typically runs once per startup; it may rerun under controlled retry workflows.

## 7. Multi-Table Seeding: Transactions and Recovery Checkpoints

Suppose seeding must create **role** and **role_permission**. If inserting role succeeds and then an error occurs before inserting permission, the next run must know what is still missing. Options include:

- **Transaction for a business unit of work:** use **TransactionTemplate** or a **@Transactional** service method via a Spring proxy so all related changes commit together.
- **Each step independently idempotent:** roles are inserted-if-absent, permission associations have a composite unique key (role_id, permission_code), and re-running fills in missing pieces.
- **Durable version marker:** write a version marker **after** all required steps succeed; never mark completion before real data commits.
- **Migration tool:** for schema/reference data tightly tied to release versions, consider Flyway/Liquibase rather than putting every mutation into runners.

Example transaction-boundary structure (illustrative code snippet, not a standalone file):

~~~java
transactionTemplate.executeWithoutResult(status -> {
    ensureRoleExists();
    ensureRolePermissionExists();
    markSeedVersionComplete();
});
~~~

The **ensure...** methods must be implemented with idempotent operations and appropriate unique constraints; `transactionTemplate` must be configured from the PlatformTransactionManager for the right datasource.

**Important:** placing **@Transactional** directly on the initialization method or calling a **@Transactional** method via **this.someMethod()** may bypass the Spring AOP proxy; do not assume it creates a transaction. Extract logic into an injected Spring service called through its proxy, or use **TransactionTemplate** when explicit boundaries are needed.

If a job has side effects outside the DB (messages, APIs, emails), a single database transaction **does not guarantee atomicity** across external systems. Consider outbox patterns, idempotency keys, durable job states, and retry policies.

## 8. Multiple Concurrent Replicas: Idempotency Differs from Mutual Exclusion

Suppose pods A and B start simultaneously and both invoke seeding:

~~~text
Pod A: INSERT DEFAULT ----+
                          +----> DB with PRIMARY KEY(code)
Pod B: INSERT DEFAULT ----+
                                  |
                         One INSERT succeeds
                         The other hits duplicate key
                                  |
                         Both proceed to read DEFAULT
                                  |
                         Each pod warms its own cache
~~~

**The DB unique constraint** enforces the invariant **"one record per code."** It is stronger than `synchronized`, `AtomicBoolean`, or in-JVM locks because all pods must go through the same data source.

Not every problem can be solved by a unique key alone. When an expensive side-effecting task truly must be executed by only one worker at a time, you may need:

- Durable job records with a unique job key + status.
- Transactional claiming (SELECT FOR UPDATE or a DB-appropriate claim mechanism).
- Distributed locks/leases, with **fencing tokens** if external resources must guard against stale owners.
- Idempotency keys supported by target APIs.
- Retries + recovery after crashes/timeouts.

**Distributed locks do not replace idempotency.** Leases can expire while an old worker is still running; crashes can occur right after a side effect yet before saving state. Safe designs account for claiming, side effects, and recovery together.

For per-replica local caches, having multiple pods read the DB and populate caches is usually acceptable, provided the DB handles the load. With many pods or huge warm-up datasets, add rate limiting, batching/pagination, shared caches, or staggered startup strategies to avoid a **thundering herd**.

## 9. Safe Cache Warm-Up on Reruns and Failures

### 9.1. Atomic Snapshots

A flawed implementation:

~~~java
cache.clear();
for (Entry entry : repository.findAll()) {
    cache.put(entry.code(), entry.value());
}
~~~

This is **illustrative pseudocode**, not a runnable class. If the query/loop fails midway, the cache holds only partial data. While the loop runs, readers observe an incomplete cache.

Improved approach:

~~~java
Map<String, String> next = loadAndValidateAllEntries();
cacheReference.set(Map.copyOf(next));
~~~

The snippet above assumes **loadAndValidateAllEntries()** and **AtomicReference<Map<String,String>> cacheReference** already exist. Core idea: **build → validate → publish**.

You can use **AtomicReference** or a **volatile** field to publish the entire immutable map. For large datasets, account for temporary doubled RAM usage (old snapshot + new snapshot), build duration, and data revision/epoch differences.

### 9.2. Still Need a Strategy for Cache Misses

Warm-up does not guarantee the cache will contain every future key. On a cache miss:

- Re-query the database or primary source (cache-aside).
- Use appropriate TTLs and invalidation.
- Bound concurrent requests reloading the same key (single-flight if needed).
- If a key is mandatory for system operation, update readiness or return a clear error rather than silently using a wrong value.

**Do not use a cache as the source of truth** when data mutates frequently without consistency mechanisms.

### 9.3. "Required" vs. "Best-Effort" Warm-Up

| Policy | When Warm-Up Fails | Consequence |
| --- | --- | --- |
| **Mandatory before ready** | Runner throws exception or blocks readiness, per design | Instance receives no traffic without required preconditions |
| **Best effort** | Logs/metrics emitted, startup continues; falls back on cache miss | Faster startup, though first requests may be slower |
| **Asynchronous warm-up** | Runner spawns background task and returns | **Does not guarantee** task finishes before ApplicationReadyEvent |
| **Partial warm-up** | Preloads hot keys only, loads remaining keys on demand | Must plan for misses and cold-start latency |

If async runners are a real requirement, use **Future/CompletableFuture** with deadlines, error handling, and readiness coordination. Never assume Boot waits for child tasks after a runner returns.

A sensible failure policy for required data: schema mismatch/lost connection -> **fail fast**, do not advertise readiness. For a pure speed-optimization cache -> **best effort** may be acceptable if a fallback path to source data always exists.

## 10. Ordering Across Multiple Runners

Spring Boot allows multiple **ApplicationRunner** and **CommandLineRunner** beans in the same application. When ordering is needed, use **@Order** or **Ordered** on runner beans.

Conceptual example:

~~~java
@Bean
@Order(10)
ApplicationRunner seedRunner() {
    return args -> seedDefaults();
}

@Bean
@Order(20)
ApplicationRunner warmupRunner() {
    return args -> rebuildCache();
}
~~~

This is an **illustrative configuration snippet**, requiring implementations of **seedDefaults()**, **rebuildCache()**, and imports for **Bean**, **Order**, **ApplicationRunner**. The methods above are not a standalone Java file.

Use order only when **stages genuinely have dependencies**. If warm-up must run after seeding, using **one orchestrating runner** as in section 6's runnable example can be simpler and avoids implicit ordering dependencies across runners contributed by multiple modules.

**@Order creates neither a transaction, nor a distributed lock, nor cross-pod synchronization.** It affects only runner execution order within a single SpringApplication startup.

Never write logic relying on order between two runners sharing the same order if the framework guarantees no stable order between them.

## 11. Distinguishing Seeding, Migrations, and Runtime Repairs

| Need | Typically Suitable Tool/Hook | Notes |
| --- | --- | --- |
| Create a few missing default records | Runner + DB unique key/insert-if-absent | Reruns do not overwrite valid data |
| Versioned schema evolution | Flyway/Liquibase migrations | Versioned, manages order and checksums |
| Update immutable reference data per release | Migration/versioned script | Do not accidentally overwrite user customizations |
| Rebuild local cache at startup | ApplicationRunner or cache service startup hook | Build/swap snapshot, failure policy |
| Continuously changing data | Cache-aside, TTL, invalidation, CDC/events | One-time startup warm-up is not enough |
| Risky production data repair | Dedicated admin job with audit and dry run | Never run destructive fixes on every replica startup |
| Background scheduled synchronization | Idempotent scheduler/worker | Protect concurrency, retries, observability |

**Seeding via Runners does not replace database migrations.** Runners execute after Boot refreshes the context; a datasource used by an ORM or other beans may require a valid schema **before then**. For versioned schemas, migrations should run before components depending on the schema.

When a record genuinely must change across versions, do not vaguely "add another seed every time." Define version conditions, transactions, audit trails, and rollback capability upfront.

## 12. Testing to Prove "Safe Repeatability"

Do not run only the happy path once. A practical test suite should cover scenarios such as:

| Test | Initial Data | Action | Expectation |
| --- | --- | --- | --- |
| Fresh start | Empty table | Run seed then warm-up | Creates exact DEFAULT, cache holds value |
| Repeat in process | DEFAULT already exists | Rerun same logic | Row count unchanged, cache accurate |
| Restart | DB file preserved | Stop/start process | No extra DEFAULT created |
| Manual edit preservation | DEFAULT has custom display_name | Rerun | New name preserved and loaded into cache |
| Concurrent startup | Two processes seed same key | Run in parallel | At most one DEFAULT, no data loss |
| DB unavailable | No DB connection | Run required seed | Startup fails clearly, error not masked |
| Failed cache read | Query fails mid-snapshot build | Re-run warm-up | Incomplete snapshot not published |
| Cache staleness | DB changes after warm-up | Read key | Miss/TTL/invalidation follows strategy |
| Additional records | Table has extra codes | Run warm-up | Cache includes valid codes, does not wipe DB |
| Crash mid-seed | Partial new data written | Restart and rerun | Transaction rolls back or missing step compensated idempotently |

### Assertions for the Demo

With a clean database, after two passes in the runner:

~~~text
COUNT(catalog) = 1
cache.size()   = 1
cache.DEFAULT  = "Default"
~~~

After restarting against the same DB, those conditions still hold. If `display_name` is changed in the DB, verify the cache reads **the value from the DB**, not a hardcoded default.

When writing real integration tests for Spring Boot 3.5, you can use **@SpringBootTest**, **JdbcTemplate**, and an appropriate test database. To simulate a real restart, do not rely solely on a fresh in-memory H2 recreated per test and claim cross-process persistence was verified; use a file/temporary database or database integration test container as appropriate.

## 13. Logging, Metrics, and Failure Handling

A production runner should log observable details without leaking sensitive data:

- Task name and seed logic version.
- Counts of records **newly created**, **already existing**, and **failed**.
- Seed duration, warm-up duration, and snapshot size.
- DB/cache dependency status with appropriate metrics.
- Start/completion timestamps and failure reasons sufficient for tracing.
- Processed keys/tenants if aligned with security policies and metric cardinality limits.

Do not log tokens, passwords, personal data, or thousands of keys to stdout just to inspect warm-up.

### Controlled Retries

If the DB is temporarily unavailable:

1. Retry only recoverable (transient) error types.
2. Enforce attempt limits, deadlines, exponential backoff, and jitter when multiple replicas retry concurrently.
3. Once retries are exhausted, choose **fail startup** or **degraded readiness** per business requirements.
4. Keep operations idempotent so retries never corrupt already-written data.
5. Never retry infinitely inside a runner, hanging startup with no signal.

Schema violations or misconfigurations are errors you **must not** retry blindly. A DuplicateKeyException for an already-existing expected key is normal in seed-if-absent, yet that is no reason to ignore all other database errors.

## 14. Self-Check Questions

**Question 1.** Why must a runner that "only runs at startup" still be idempotent?

**Question 2.** Two replicas both observe **existsById=false** and then insert. Why is a Java-layer check alone insufficient?

**Question 3.** A DEFAULT row is renamed by an administrator. After a restart, should seeding leave it unchanged or reset it to default? Which rule governs this?

**Question 4.** Why is **cache.clear()** followed by incremental puts dangerous with concurrent readers? How do volatile/AtomicReference snapshots improve this?

**Question 5.** A runner submits a CompletableFuture and returns immediately. Can you conclude warm-up finished before ApplicationReadyEvent?

**Question 6.** Does @Order on two runners replace unique constraints or distributed locks?

**Question 7.** When is a migration tool needed instead of placing all SQL in runners?

**Question 8.** If a cache is purely a performance optimization and the DB can still serve directly, must a warm-up failure always fail startup?

**Suggested Answers:**

1. Because restarts, redeploys, retries, and multiple replicas cause the operation to run repeatedly.
2. Both processes read stale state simultaneously; unique constraints/atomic DB operations are needed to prevent duplicates.
3. For default-if-absent seeding, leave it unchanged; for immutable/versioned corrections, establish an explicit update contract.
4. Readers see an empty/partial cache; immutable snapshots are published atomically after loading finishes.
5. No; Spring Boot only awaits the runner method completing, not self-spawned async tasks.
6. No; @Order only orders within a single application instance.
7. When schema/reference data requires versioning, auditing, ordered migrations, and clear rollback/repair paths.
8. Not necessarily; best-effort with a fallback path can work depending on SLO/readiness policies.

## 15. Pre-Deployment Design Checklist

- [ ] Clearly defined success criteria for seed/warm-up and behavior on re-invocation?
- [ ] Unique/business keys enforced in the **database**, not only checked in Java?
- [ ] Operator-modified data preserved per contract?
- [ ] Transaction boundaries sufficient to prevent partial data?
- [ ] If multiple replicas exist, race/conflict strategy clearly defined?
- [ ] Not catching and ignoring all exceptions?
- [ ] Cache **built/validated/published** instead of risky clear-and-refill?
- [ ] Cache miss strategy, TTL, or invalidation present when source data changes?
- [ ] Mandatory vs. best-effort warm-up explicitly decided?
- [ ] Synchronous runner actually awaits mandatory steps before returning?
- [ ] Readiness and liveness used in their proper roles?
- [ ] Retry limits, timeouts, logging, metrics, and restart/concurrency tests in place?
- [ ] Schema/version migrations separated from startup seeding where needed?

## 16. Summary

**ApplicationRunner/CommandLineRunner are the right place for work after refresh and before ApplicationReadyEvent. Yet running at startup does not mean running only once.** Designs must tolerate restarts, retries, and multiple instances operating concurrently while maintaining valid state.

Two key practical rules:

1. **Idempotent seeding:** use stable business keys + constraints at the data source, insert-if-absent, and proper transactions; never overwrite valid changes simply because the app restarted.
2. **Idempotent warm-up:** read from the source of truth, build a complete new snapshot, and publish only after loading/validation succeeds; decide explicitly whether to block readiness or allow best effort.

### Official References

- Spring Boot 3.5 — SpringApplication, ApplicationRunner/CommandLineRunner, and application events: https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html
- Spring Boot 3.5 — Database Initialization: https://docs.spring.io/spring-boot/3.5/reference/how-to/data-initialization.html
- Spring Boot 3.5 — Application Availability and probes: https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html#features.spring-application.application-availability
- Spring Framework — JDBC, JdbcTemplate, and exception translation: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Framework — Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/transaction.html
- Spring Framework — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html

The runnable example uses **Spring Boot 3.5.x, Spring Framework 6.x, Java 17+, and H2**. For projects using different versions or databases, verify the corresponding Javadocs and SQL dialects before deploying prototypes to production.