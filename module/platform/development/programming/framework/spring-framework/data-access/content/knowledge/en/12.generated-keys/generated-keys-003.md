# Keyed Updates to Avoid Accidentally Modifying Multiple Rows in Spring JDBC

> **Goal:** Write and review `UPDATE` statements that affect **only the record identified by its key**; combine `WHERE`, parameterization with `JdbcTemplate`, primary/composite keys, affected row count checks, and optimistic locking. Understand why an unconditional `UPDATE` or one using a non-unique condition can modify data in bulk, as well as how to protect the application when multiple users update concurrently.

**Context:** Spring Framework → Data Access → **Updates and Generated Keys**. This lesson focuses on updating an *existing* record by key; retrieving generated keys after `INSERT` is mentioned for contrast, not as a replacement for the main topic. Practical examples use Java 17+, Spring Boot 3.5.16, Spring JDBC, and H2.

## 1. Why is an unkeyed UPDATE a dangerous operation?

An SQL `UPDATE` statement applies to **every row matching the `WHERE` condition**. If `WHERE` is omitted, the typical scope is the entire table. If the condition is not unique, 2, 20, or millions of records may match.

Suppose the `documents` table has three rows:

| tenant_id | id | title | version |
| --- | ---: | --- | ---: |
| tenant-a | 101 | Draft | 0 |
| tenant-a | 102 | Second | 0 |
| tenant-b | 101 | Other | 0 |

**Dangerous statements:**

```sql
-- WRONG: no WHERE; all documents can have their title overwritten.
UPDATE documents SET title = 'Reviewed';

-- WRONG: tenant_id is a broad filter, not identifying a single document.
UPDATE documents SET title = 'Reviewed'
WHERE tenant_id = 'tenant-a';

-- WRONG in this example: id is shared across two tenants.
UPDATE documents SET title = 'Reviewed'
WHERE id = 101;
```

**Correct statement with a database-enforced composite key:**

```sql
UPDATE documents
SET title = ?
WHERE tenant_id = ? AND id = ?;
```

In the example schema, `PRIMARY KEY (tenant_id, id)` guarantees at most one row matches **both** components. With the complete statement, the database pinpoints the exact document in the exact tenant.

What matters is not just “adding a `WHERE`”; it is having a **`WHERE` with database-enforced uniqueness and sufficient security scope**.

## 2. Which keys are sufficient to uniquely identify a single row?

Common key types:

| Key type | Example condition | Guarantees at most one row? | Notes |
| --- | --- | --- | --- |
| Single-column primary key | `WHERE id = ?` | Yes, when `id` is the table's `PRIMARY KEY` | Do not skip access control checks |
| Composite primary key | `WHERE tenant_id = ? AND id = ?` | Yes, when that exact pair is `PRIMARY KEY` | Must include all components |
| Unique key / unique index | `WHERE external_code = ?` | Yes if DB actually enforces appropriate uniqueness | Watch out for NULL/collation/partial unique |
| Unconstrained natural key | `WHERE email = ?` | **No guarantee** | Can duplicate, change email, normalize differently |
| Status/group | `WHERE status = 'PENDING'` | No | This is a filter for a bulk operation |
| Tenant only | `WHERE tenant_id = ?` | No | Usually many records belong to the same tenant |

**Check the DDL/migrations**, not just Java field names. A column named `id` does not by itself prove it is a primary key; a UUID or business code does not automatically have uniqueness unless an appropriate constraint is declared.

Common design guidelines:

- Single-tenant table or globally unique key: `id BIGINT PRIMARY KEY`; `WHERE id = ?` is a good starting point.
- Multi-tenant table: `PRIMARY KEY (tenant_id, id)` or `UNIQUE (tenant_id, business_key)`; `WHERE` uses the full key, with tenant taken from an authenticated security context.
- Business keys that change over time: prefer a stable technical key for `UPDATE`, keeping a separate unique constraint on the business key if needed.
- Multi-column composite key: never omit a column just because current test data “has no duplicate rows yet”.

**Do not arbitrarily substitute an exact condition with `LIMIT 1`.** Some databases do not support `UPDATE ... LIMIT`; even where supported, picking one row arbitrarily among duplicates merely masks a data-modeling bug.

## 3. Golden rule: keyed UPDATE + parameter binding + row count check

A Spring JDBC pattern using `JdbcTemplate`:

```java
// Snippet inside a DAO with injected JdbcTemplate jdbc.
public void rename(long id, String title) {
    int changed = jdbc.update(
        "UPDATE documents SET title = ? WHERE id = ?",
        title, id);

    if (changed != 1) {
        throw new IllegalStateException(
            "Expected one updated row, got " + changed);
    }
}
```

This is an **illustrative snippet** for a table with a unique `id` in the schema. This snippet **is not enough to guarantee rollback if the code is not inside a transaction**; section 7 analyzes that.

Meaning of the three actions:

1. `WHERE id = ?` scopes the statement by a DB-enforced key.
2. `jdbc.update(sql, title, id)` binds data separately, avoiding input concatenation and SQL injection. Argument order must match `?` order: **title first, id second**.
3. The `changed` return value of `JdbcTemplate.update` is the row count reported as affected by the JDBC driver. A proper primary-key UPDATE must match **at most one row**; handle counts of 0, 1, or abnormal values differently.

**A crucial point:** **checking the count after UPDATE does not replace a unique `WHERE` and a transaction**. If `WHERE` is too broad, the statement may have already updated many rows **before** Java sees `changed > 1`. If running in auto-commit mode, the changes may already be committed and cannot be undone merely by throwing an exception afterward.

## 4. Interpreting the affected row count accurately

`JdbcTemplate.update(...)` and `PreparedStatement.executeUpdate()` return an `int` representing affected rows per JDBC/driver rules. In a keyed update:

| Row count (`int changed`) | Initial interpretation | Usually appropriate response |
| ---: | --- | --- |
| `0` | No row matched the predicate; could be missing, wrong tenant, or stale version | Return 404/409 or domain error per contract; do not fake success |
| `1` | One row reported affected by the driver | Can treat as success given proper schema/predicate and DB semantics |
| `> 1` | Predicate or data violated the “one row” invariant | Report severe error, roll back transaction, investigate key condition/DDL |
| SQL throws exception | Constraint, type, deadlock, connection, permission… | Let Spring translate to `DataAccessException`; decide retry/rollback by error kind |

**Driver exception:** “affected/matched/changed rows” counts can differ across DBMSs and driver modes, especially when assigning the **exact same old value**, with triggers, or with views. If you need to distinguish “row exists” from “value actually changed”, do not apply one universal rule across all DBs; inspect the running JDBC driver and dialect and write integration tests.

With optimistic locking (`WHERE version = ?`), `0` is especially important: it can indicate a **concurrent overwrite was prevented**, though the count alone does not distinguish “row was deleted” from “version no longer matches”. Mapping to HTTP 404/409 must follow the business model.

### How to classify results in a service

```java
int count = repository.renameIfVersion(tenantId, id,
                                       expectedVersion, newTitle);

if (count == 1) {
    return; // Success.
}
if (count == 0) {
    throw new IllegalStateException(
        "Document missing or version changed");
}
throw new IllegalStateException(
    "Invariant violation: updated " + count + " rows");
```

This is an illustrative snippet, not a standalone runnable file. For contracts where 0 is not an error, you can return an enum `UPDATED / NO_MATCH` instead of throwing an exception, provided callers clearly understand the meaning.

## 5. Writing safe WHERE clauses for single-tenant and multi-tenant tables

### Single-column primary key table

```sql
CREATE TABLE products (
    id BIGINT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    price DECIMAL(12, 2) NOT NULL
);
```

```java
// Snippet: jdbc is an injected JdbcTemplate; id and name are valid.
int rows = jdbc.update(
    "UPDATE products SET name = ? WHERE id = ?",
    name, id);
```

Because `id` is the primary key, a single query cannot match two different products by `id`. Adding an extra condition such as `AND status = 'ACTIVE'` is reasonable if only active items may be edited, though when count equals 0 you must recognize it could be rejected due to status, not only “missing id”.

### Composite primary key table

```sql
CREATE TABLE documents (
    tenant_id VARCHAR(32) NOT NULL,
    id BIGINT NOT NULL,
    title VARCHAR(120) NOT NULL,
    version INTEGER NOT NULL,
    PRIMARY KEY (tenant_id, id)
);
```

```java
int rows = jdbc.update(
    "UPDATE documents SET title = ? " +
    "WHERE tenant_id = ? AND id = ?",
    title, tenantId, id);
```

The DB guarantees the tenant/id pair is unique. **However, `tenantId` must come from a trusted access-control context**, never blindly accepting any tenant ID self-reported by the client. You can combine DB row-level security if supported by the system/DB, but that does not replace authentication/authorization checks.

### Keys with NULL values

Primary keys cannot be NULL. If using a nullable column in a condition, SQL `WHERE nullable_col = NULL` is never a valid comparison under SQL three-valued logic; you need `IS NULL` or a dialect-specific null-safe comparison. Standard unique key designs avoid ambiguous nullable keys.

### When using soft delete

Add the status condition:

```sql
UPDATE documents
SET title = ?
WHERE tenant_id = ? AND id = ? AND deleted_at IS NULL;
```

If `changed=0`, the document may not exist, may already be soft-deleted, or the tenant may be wrong. Avoid automatically retrying without `deleted_at IS NULL` just to obtain count 1, because doing so could modify a record that was business-deleted.

## 6. Optimistic locking: keying the right row can still overwrite fresh data

A primary key solves **“accidentally modifying multiple records”**, but does not solve **“two requests modifying the same record concurrently”**.

Example:

```text
T0: document (tenant-a, 101) = title "Draft", version 0

T1: user A reads version 0
T2: user B also reads version 0

T3: A saves "Final"
T4: B saves "Old edit" based on stale data

If both UPDATEs only use WHERE id=101,
B can overwrite A's change (lost update).
```

**Prevention for read-modify-write:** store a `version` column and require the version to match what the client read.

```sql
UPDATE documents
SET title = ?,
    version = version + 1
WHERE tenant_id = ?
  AND id = ?
  AND version = ?;
```

Meaning:

- **`tenant_id, id`**: uniquely locates the document.
- **`version = ?`**: requires that no one has updated the state since the caller read it.
- **`version = version + 1`**: atomically updates the version in the same statement when the update succeeds.
- `rowsAffected == 1`: the update was applied to the expected version.
- `rowsAffected == 0`: one of the predicates no longer holds; do not overwrite newer data with a stale version.

Java pattern:

```java
int count = jdbc.update(
    """
    UPDATE documents
    SET title = ?, version = version + 1
    WHERE tenant_id = ? AND id = ? AND version = ?
    """,
    newTitle, tenantId, id, expectedVersion);

if (count == 0) {
    throw new IllegalStateException(
        "Version conflict or document not found");
}
if (count != 1) {
    throw new IllegalStateException(
        "Expected one row, got " + count);
}
```

A version-checked SQL update **is evaluated by the DB in the same statement**, which is safer than:

```text
SELECT ... WHERE id = ?;
if (version == expected) {
    UPDATE ... WHERE id = ?;  <-- Easy race between SELECT and UPDATE
}
```

**Note:** optimistic locking does not eliminate all conflicts. The application must resolve conflicts: ask the user to reload and compare, perform a controlled merge, or retry when the operation is idempotent/pure. Never retry infinitely or overwrite silently. The demo in section 11 simulates two sequential requests using the same stale version to demonstrate `0` on the second call; that is not yet a true multi-threaded stress test.

### Numeric version or timestamp?

An incrementing `INTEGER/BIGINT version` is usually easy to reason about and test. Timestamps can collide when two operations fall within the DB's time precision, across timezones, or under driver rounding; do not blindly replace it with an auto-generated timestamp. Choose the strategy based on schema and concurrency needs. In JPA, `@Version` has built-in support; in **plain JdbcTemplate** you must write the version check and increment yourself.

## 7. Transactions: is checking row count enough to roll back?

A single `UPDATE` is atomic at the DB statement level, yet **one business operation** may involve multiple statements: updating the document, adding an audit entry, deducting quota, creating a notification outbox row.

In Spring, place `@Transactional` on a **public service invoked through a Spring proxy**, so JDBC operations sharing the datasource/manager participate in the transaction.

```java
// Conceptual snippet: repository and auditWriter are configured.
@Transactional
public void approveDocument(String tenantId, long id) {
    int changed = repository.approve(tenantId, id);
    if (changed != 1) {
        throw new IllegalStateException(
            "Exactly one document expected");
    }
    auditWriter.recordApproved(tenantId, id);
}
```

Goal: when the UPDATE or audit INSERT fails under rollback rules, both roll back. **Do not let UPDATE commit first and check the count afterward** in a non-transactional DAO, especially when predicate uniqueness is uncertain. Even when only one SQL statement on a PK table is needed, the primary-key scope must still be right; do not use `@Transactional` to “fix” SQL missing a `WHERE`.

**Spring's default rules** (unless configured otherwise): unchecked `RuntimeException`/`Error` triggers rollback; checked exceptions do not automatically trigger rollback. If using checked business exceptions, consider `@Transactional(rollbackFor = MyCheckedException.class)` or an appropriate policy.

**Proxy/self-invocation:** `this.approveDocument(...)` inside the same object may not pass through the AOP transaction proxy. Another controller/runner/service calling the public method on the Spring bean proxy matches default proxy mode. Do not place the annotation on a method and blindly assume every call path is transactional.

### A particularly dangerous bug

```java
// WRONG regarding rollback guarantee under autocommit:
int changed = jdbc.update(
    "UPDATE documents SET title = ? WHERE tenant_id = ?",
    title, tenantId); // May have already committed modifying multiple rows!

if (changed > 1) {
    throw new IllegalStateException("Too many rows");
}
```

Once the exception is thrown, **there is no guarantee that auto-committed changes are undone**. Prevent the incident first with a DB-enforced unique key `WHERE`; transactions protect atomicity across multiple steps and enable rollback if an invariant is violated.

## 8. Checking business conditions right inside WHERE

Not every state change only needs `id`/`version`. You can place extra conditions in SQL to protect invariants atomically.

### Transition only from DRAFT to APPROVED

```sql
UPDATE documents
SET status = 'APPROVED',
    version = version + 1
WHERE tenant_id = ?
  AND id = ?
  AND status = 'DRAFT'
  AND version = ?;
```

If `0`: the document may not exist, may already be approved, may be deleted, or may have a stale version. This is a **conditional state transition**, better than `SELECT status` followed by an unchecked `UPDATE` under races.

### Never deduct a balance below zero

```sql
UPDATE wallets
SET balance = balance - ?,
    version = version + 1
WHERE wallet_id = ?
  AND balance >= ?;
```

The amount parameter is bound **twice**: once for the subtraction, once for the threshold. `wallet_id` is a primary/unique key. In a real wallet, you must also control amount `> 0`, currency/scale, idempotency, multi-account transactions, auditing, and lock contention. This SQL example simply shows that **the balance check predicate and modification reside in the same statement**.

### Never replace a key with a non-unique condition

```sql
-- Missing key: every PENDING order could become APPROVED.
UPDATE orders SET status = 'APPROVED'
WHERE status = 'PENDING';

-- Correct if order_id is PRIMARY KEY and the state transition is allowed:
UPDATE orders SET status = 'APPROVED'
WHERE order_id = ? AND status = 'PENDING';
```

Add business conditions **after** the key condition, not **in place of** the key condition. This makes missing keys easy to spot during code review.

## 9. Pessimistic locking and isolation: when is SELECT FOR UPDATE needed?

Optimistic locking is usually suitable when conflicts are infrequent. For workflows that must read multiple columns, make complex decisions, and then update, you can use **pessimistic row locking** via DB features.

```sql
-- Common syntax; support and locking behavior vary across DBs.
SELECT id, balance
FROM wallets
WHERE wallet_id = ?
FOR UPDATE;
```

**Conditions for proper usage:**

- Execute SELECT and UPDATE **inside the same transaction**; do not use auto-commit and expect the lock to remain held until the next statement.
- `WHERE` still uses the key and security scope.
- Verify that the database/driver/isolation level supports the syntax and desired lock semantics.
- Keep transactions short; avoid slow network/API calls while holding row locks.
- Deadlocks/lock wait timeouts can occur; have a bounded retry strategy if business logic allows.

Do not use `FOR UPDATE` if you only need to update a single field with one `UPDATE ... WHERE id = ? AND version = ?` statement. Adding unnecessary locks can cause contention and reduce throughput.

### Isolation does not replace a proper predicate

Choosing `READ_COMMITTED`, `REPEATABLE_READ`, or `SERIALIZABLE` determines which concurrency anomalies are reduced/prevented depending on the DB; **no isolation level can save an `UPDATE` missing a key**. Every row matching `WHERE` remains eligible to be updated.

## 10. How do generated keys relate to keyed UPDATEs?

The topic “Updates and Generated Keys” can cause confusion between two distinct stages:

1. **INSERT:** the database generates a new key (`IDENTITY`, sequence, DB-side UUID…). Code can retrieve it via JDBC `getGeneratedKeys` or Spring `KeyHolder`.
2. **UPDATE:** uses a **known key** stored/read from business data to update the exact row. A normal `UPDATE` does not “generate a new key” or automatically pick the newest record.

In Spring JDBC, INSERT code often looks like:

```java
// Illustrative snippet; requires JdbcTemplate jdbc and matching schema.
KeyHolder holder = new GeneratedKeyHolder();
int inserted = jdbc.update(connection -> {
    PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO products(name) VALUES (?)",
        new String[] {"id"});
    ps.setString(1, "Keyboard");
    return ps;
}, holder);

Number generatedId = holder.getKey();
```

Requires importing `org.springframework.jdbc.support.KeyHolder`, `GeneratedKeyHolder`, and `java.sql.PreparedStatement`. This is not a standalone runnable example and only works when `id` is DB-generated and the driver supports generated keys. `getKey()` can also be unsuitable when multiple keys/columns exist; check the output. For composite PK tables, key generation mechanisms may differ.

**After INSERT, keep the exact record's key** rather than guessing with `SELECT MAX(id)` or “fetching the last row”. Both guessing methods fail when multiple requests insert concurrently. When updating, bind the retrieved id into `WHERE` and check the count.

```sql
UPDATE products
SET name = ?
WHERE id = ?;
```

When only updating regular columns, do not modify `id` (the referenced key) without an explicit migration/foreign-key design.

## 11. Complete program: composite key, strict update, and optimistic locking

A **Java 17+**, Maven, **Spring Boot 3.5.16**, Spring JDBC, and H2 in-memory example. It demonstrates:

- A document is uniquely identified only by the `(tenant_id, id)` pair.
- A transactional method requires **exactly one row** to be updated.
- A non-existent id throws a domain error in the service rather than faking success.
- Two writes using the same `expectedVersion=0`: the first succeeds, the second does not overwrite.
- A document in another tenant with the same id remains untouched.

**This is a multi-file Maven project.** Do not compile individual sources alone with `javac` without the Spring/H2 classpath.

### 11.1. Project structure

```text
keyed-update-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/com/example/keyupdate/
        │   ├── KeyUpdateApplication.java
        │   └── DocumentService.java
        └── resources/
            ├── application.properties
            ├── schema.sql
            └── data.sql
```

### 11.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>keyed-update-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
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
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

The Spring Boot JDBC starter provides `JdbcTemplate` and transaction infrastructure matching the auto-configured datasource. H2 is an embedded database for demo purposes, with no production data.

### 11.3. src/main/resources/schema.sql

```sql
CREATE TABLE documents (
    tenant_id VARCHAR(32) NOT NULL,
    id BIGINT NOT NULL,
    title VARCHAR(120) NOT NULL,
    version INTEGER NOT NULL,
    PRIMARY KEY (tenant_id, id)
);
```

**Why is the PK two columns?** The example intentionally creates two tenants sharing `id=101` to prove `WHERE id=?` is **insufficient** with this design. The DB enforces uniqueness of the tenant/id pair.

### 11.4. src/main/resources/data.sql

```sql
INSERT INTO documents (tenant_id, id, title, version)
VALUES
    ('tenant-a', 101, 'Draft', 0),
    ('tenant-a', 102, 'Second', 0),
    ('tenant-b', 101, 'Other', 0);
```

### 11.5. src/main/resources/application.properties

```properties
spring.main.web-application-type=none
spring.main.banner-mode=off
logging.level.root=ERROR
spring.datasource.url=jdbc:h2:mem:keyedupdate;DB_CLOSE_DELAY=-1
spring.sql.init.mode=always
```

### 11.6. src/main/java/com/example/keyupdate/DocumentService.java

```java
package com.example.keyupdate;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentService {

    private final JdbcTemplate jdbc;

    public DocumentService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    // Never modifies more than one document: tenant_id + id is the composite PK.
    // RuntimeException on 0 rows causes the transaction to roll back.
    @Transactional
    public int renameStrict(String tenantId, long id, String newTitle) {
        int changed = jdbc.update(
            "UPDATE documents SET title = ? " +
            "WHERE tenant_id = ? AND id = ?",
            newTitle, tenantId, id);

        if (changed != 1) {
            throw new IllegalStateException(
                "Expected exactly one updated document; got " + changed);
        }
        return changed;
    }

    // Optimistic locking: version must match within the same UPDATE statement.
    @Transactional
    public int renameIfVersion(
            String tenantId, long id, int expectedVersion,
            String newTitle) {

        int changed = jdbc.update(
            """
            UPDATE documents
            SET title = ?, version = version + 1
            WHERE tenant_id = ? AND id = ? AND version = ?
            """,
            newTitle, tenantId, id, expectedVersion);

        // 0: missing row, wrong tenant, or stale version.
        // Caller decides whether to report conflict or inspect further.
        if (changed > 1) {
            throw new IllegalStateException(
                "Invariant violation: " + changed + " rows");
        }
        return changed;
    }
}
```

**Practical note:** the public service is Spring-managed, so `@Transactional` applies when callers invoke it through the bean proxy. `IllegalStateException` is unchecked, fitting Spring's default rollback behavior. The composite key is enforced by `PRIMARY KEY`, so `changed > 1` cannot happen when SQL/schema are correct; the check still makes the invariant explicit at the DAO/service boundary.

### 11.7. src/main/java/com/example/keyupdate/KeyUpdateApplication.java

```java
package com.example.keyupdate;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootApplication
public class KeyUpdateApplication {

    public static void main(String[] args) {
        SpringApplication.run(KeyUpdateApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(DocumentService service, JdbcTemplate jdbc) {
        return args -> {
            int updated = service.renameStrict(
                    "tenant-a", 101L, "Reviewed");
            System.out.println("strict-updated=" + updated);

            try {
                service.renameStrict("tenant-a", 999L, "Ignored");
            } catch (IllegalStateException ex) {
                System.out.println("missing=NOT_FOUND");
            }

            int fresh = service.renameIfVersion(
                    "tenant-a", 101L, 0, "Final");
            System.out.println("optimistic-updated=" + fresh);

            int stale = service.renameIfVersion(
                    "tenant-a", 101L, 0, "Unexpected");
            System.out.println("optimistic-stale=" + stale);

            String document = jdbc.queryForObject(
                "SELECT title || '|' || version FROM documents " +
                "WHERE tenant_id = ? AND id = ?",
                String.class, "tenant-a", 101L);
            System.out.println("document=" + document);

            String otherTenant = jdbc.queryForObject(
                "SELECT title FROM documents " +
                "WHERE tenant_id = ? AND id = ?",
                String.class, "tenant-b", 101L);
            System.out.println("other-tenant=" + otherTenant);
        };
    }
}
```

**Run** from the `keyed-update-demo` directory after installing JDK 17+ and Maven:

```bash
mvn spring-boot:run
```

**Lines explicitly printed by the application** (excluding Maven/Spring output):

```text
strict-updated=1
missing=NOT_FOUND
optimistic-updated=1
optimistic-stale=0
document=Final|1
other-tenant=Other
```

### 11.8. Analysis of each result

1. `strict-updated=1`: `WHERE tenant_id='tenant-a' AND id=101` matches one row. Title changes from `Draft` to `Reviewed`.
2. `missing=NOT_FOUND`: id 999 does not exist, update count = 0; the service throws an unchecked exception and the Spring transaction rolls back. No new document is created.
3. `optimistic-updated=1`: document version 0 is updated to `Final` and version increments to 1 **in the same UPDATE**.
4. `optimistic-stale=0`: the next call still requires version 0, while the DB now has version 1, so it **does not overwrite** title with `Unexpected`.
5. `document=Final|1`: final read proves both title and version are accurate.
6. `other-tenant=Other`: tenant-b uses the same id 101, yet its title remains intact, proving the composite key constrained the scope.

The demo uses H2 and executes sequentially; it proves predicate/version logic, but **does not prove load capacity, real race conditions, or isolation across all databases**. In real projects, write integration tests with the production DB or Testcontainers, verifying multi-tenancy security and concurrent requests.

**Never run an unkeyed UPDATE on production data “just to see how many rows it affects”.** To demonstrate scope bugs, use a test environment, a controlled rolled-back transaction, or evaluate beforehand with `SELECT COUNT(*)` using the same predicate (though a prior SELECT does not replace uniqueness constraints/atomic updates under concurrency).

## 12. Named parameters help avoid swapping keys and values

With multiple parameters of the same `String` or `long` type, positional `?` placeholders are easy to pass in the wrong order. `NamedParameterJdbcTemplate` makes each role explicit:

```java
// Snippet: NamedParameterJdbcTemplate named is injected.
MapSqlParameterSource params = new MapSqlParameterSource()
    .addValue("tenant", tenantId)
    .addValue("documentId", id)
    .addValue("title", newTitle)
    .addValue("version", expectedVersion);

int changed = named.update(
    """
    UPDATE documents
    SET title = :title, version = version + 1
    WHERE tenant_id = :tenant
      AND id = :documentId
      AND version = :version
    """,
    params);
```

Requires importing `org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate` and `MapSqlParameterSource`. Named parameters are still prepared-statement parameterization; they do **not** allow substituting a dynamic table/column name with `:tableName`. Every named value must come from a validated/authorized source, especially the tenant.

**Do not choose between `?` and `:name` by guessing which query looks “shorter”:** both are valid. Pick a consistent style, verify parameter order/types, test actual SQL, and preserve transaction semantics.

## 13. SqlUpdate object, plain JDBC, and batchUpdate

### 13.1. Spring JDBC's SqlUpdate

In legacy codebases you may encounter `org.springframework.jdbc.object.SqlUpdate`:

```java
// Snippet requiring DataSource ds and imports.
SqlUpdate op = new SqlUpdate(ds,
        "UPDATE documents SET title = ? " +
        "WHERE tenant_id = ? AND id = ?");
op.declareParameter(new SqlParameter("title", Types.VARCHAR));
op.declareParameter(new SqlParameter("tenant", Types.VARCHAR));
op.declareParameter(new SqlParameter("id", Types.BIGINT));
op.setRequiredRowsAffected(1);
op.compile();

int rows = op.update("Final", "tenant-a", 101L);
```

`setRequiredRowsAffected(1)` requires exactly one row; `setMaxRowsAffected(1)` only checks that the configured maximum is not exceeded. These are **post-execution count checks**; they do not turn a non-unique `WHERE` into a unique one. If rollback on anomaly is needed, an appropriate transaction is still required. `compile()` prepares the Spring object; it does **not** run the UPDATE.

### 13.2. Plain PreparedStatement

```java
// Snippet inside a method with java.sql.Connection con.
String sql =
    "UPDATE documents SET title = ? " +
    "WHERE tenant_id = ? AND id = ?";

try (PreparedStatement ps = con.prepareStatement(sql)) {
    ps.setString(1, newTitle);
    ps.setString(2, tenantId);
    ps.setLong(3, id);
    int changed = ps.executeUpdate();
}
```

`PreparedStatement` parameter indexes start at **1**. With plain JDBC, whoever owns `Connection` must decide transaction handling and cleanup. `JdbcTemplate` reduces this boilerplate. Both still need a proper SQL predicate.

### 13.3. Batch update across multiple keys

```java
// Snippet for a DAO with JdbcTemplate jdbc and a list of DocumentChange.
int[] counts = jdbc.batchUpdate(
    "UPDATE documents SET title = ? " +
    "WHERE tenant_id = ? AND id = ?",
    changes,
    changes.size(),
    (ps, change) -> {
        ps.setString(1, change.title());
        ps.setString(2, change.tenantId());
        ps.setLong(3, change.id());
    });
```

Here `changes` is an application-defined list of `DocumentChange` records; this is an illustrative snippet, not a standalone project. The `batchUpdate(String, Collection<T>, int, ParameterizedPreparedStatementSetter<T>)` overload in Spring JDBC returns **`int[][]`** per batch, not `int[]`. If you use the `batchUpdate(String, BatchPreparedStatementSetter)` overload, the return type is **`int[]`**. When refactoring/testing, pick the right overload and matching return type instead of copying signatures blindly.

**Read batch results carefully:** JDBC uses sentinel values `Statement.SUCCESS_NO_INFO` (`-2`) or `EXECUTE_FAILED` (`-3`) depending on the driver. Never assume every entry has an exact count of 1. If the batch operation must be atomic, use a transaction and handle exceptions/partial failures appropriately.

### 13.4. Intentional unkeyed updates in data jobs

A migration/bulk update task may intentionally update many rows:

```sql
UPDATE documents
SET archived = TRUE
WHERE retention_due < CURRENT_DATE
  AND archived = FALSE;
```

This is **not** a single-record keyed update, but a bulk business operation. It requires elevated privileges, predicate verification, a migration plan, data safeguards, observability, and rollback/backup plans. Do not apply the “every UPDATE must touch one row” rule to bulk jobs; instead, clearly distinguish operation types and control scope accordingly.

## 14. Testing to catch overly broad updates and lost updates

### Key-based functional tests

Start with multiple rows sharing similarities:

- Two rows with the same `tenant_id` but different `id`.
- Two tenants using the same `id`.
- Two rows with the same title/status, different keys.
- A non-existent id.
- A soft-deleted row or invalid status.
- Two requests using the same stale `version`.

After each operation, **re-query all potentially affected rows** in the fixture rather than only checking the row count. On multi-tenant tables, prove that an update for tenant-a did not alter tenant-b.

Conceptual assertion example:

```java
int count = service.renameIfVersion("tenant-a", 101L, 0, "New");
assertEquals(1, count);

int stale = service.renameIfVersion("tenant-a", 101L, 0, "Old");
assertEquals(0, stale);

// Verify the final title/version and that tenant-b's record
// remains intact using JdbcTemplate or the repository.
```

The `assertEquals` snippet requires JUnit and dedicated test data; it is not part of the `CommandLineRunner` example. When using `@JdbcTest`, `@SpringBootTest`, or `@Transactional` tests, understand test-framework rollback, datasources, and fixture initialization before concluding production safety.

### Testing transaction rollback on abnormal counts

In a test environment, create a `@Transactional` service invoking an operation that fails an invariant, throws an exception, and then query to confirm data is unchanged. More importantly: **independently evaluate predicates/constraints**, because rollback is a safety net, not a substitute for preventing mass updates when the statement executes.

### True concurrency testing

Use two transactions/threads with a latch or concurrency testing tool so both read the same version and then update concurrently. Expect one transaction to update successfully while the other **cannot silently overwrite**; depending on the DB, a conflict/lock timeout/deadlock may occur. If retrying, the retry must reload state and apply a merge policy rather than reusing stale data.

## 15. Common mistakes and fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Missing `WHERE` | Modifies the entire table | Write and review key-based predicates |
| Only `WHERE tenant_id=?` on a multi-document table | Modifies all rows of that tenant | Include full `tenant_id AND id` |
| Only `WHERE id=?` in a composite PK | Modifies the same id across tenants | Bind all key components |
| Assuming column name `id` means primary key | No uniqueness guarantee | Inspect migrations/DDL |
| Using non-unique email/name/status | Multiple rows can match | Use stable unique keys and DB constraints |
| Using `UPDATE ... LIMIT 1` to hide scope bugs | Picks an arbitrary row, dialect-dependent | Proper `WHERE` and constraints |
| Only checking `rows>1` after autocommit | Multiple rows already committed | Unique predicate + transaction |
| Ignoring `rows=0` | Reports “success” when no row matched | Domain error, 404/409, or NO_MATCH |
| Assuming `0` always means not found | Confuses stale version/tenant/status | Distinguish per contract and authorized lookup |
| Swapping `title,tenant,id` in bindings | Wrong update or JDBC type error | Match every `?` and parameter |
| Concatenating input directly into SQL | SQL injection | Prepared statements/named parameters |
| Taking an unauthenticated tenant id | Cross-tenant modification | Tenant from security context, DB policy |
| Keying only by PK without version protection | Lost update | `WHERE version=?` + increment |
| SELECT version then UPDATE only by id | Time-of-check/time-of-use race | Check version inside the same UPDATE |
| Forgetting to increment `version` after update | Stale check becomes ineffective | Atomic `version=version+1` |
| Retrying old version infinitely | High conflict rate, may overwrite logic | Bounded reload/merge |
| Thinking `@Transactional` works on self-calls | Bypasses proxy | Call via Spring bean proxy |
| Treating `SqlUpdate.setRequiredRowsAffected` as SQL LIMIT | Does not stop multiple rows from being modified before check | DB uniqueness + transaction |
| Using `SELECT MAX(id)` to update a newly inserted row | Concurrency race picks wrong row | `KeyHolder`/`getGeneratedKeys` |
| Treating `JdbcTemplate.batchUpdate` as having one single count | Loses per-batch info | Pick right overload and handle `int[]`/`int[][]` |
| Keeping transactions open while calling external APIs | Long locks, timeouts | Shrink transactions; use outbox when needed |

## 16. Code review workflow for keyed UPDATEs

When reviewing a PR containing an `UPDATE`, ask in order:

1. **Is there a `WHERE`?** If not, is this an explicitly authorized and controlled bulk migration?
2. **Which key does `WHERE` use?** Primary key, composite PK, or unique key? Is there an actual DB constraint?
3. **Is there tenant/authorization scoping?** Does the tenant value come from a trusted source or arbitrary request input?
4. **Is binding safe?** `?` or named parameters, in the right order and type?
5. **How are counts `0/1/>1` handled?** Does it report missing row, conflict, or invariant violation per contract?
6. **Is a lost update possible?** If read-modify-write, is appropriate versioning/state check/locking used?
7. **Where is the transaction boundary?** Single statement or multi-statement; does it roll back when count mismatches?
8. **If generated keys are involved:** is the key taken from INSERT in the same transaction or guessed via `MAX(id)`?
9. **If batching is involved:** which overload, what return count type, and are JDBC sentinels handled?
10. **Are enough similar rows tested?** At least two rows in the same tenant and two tenants sharing an id (if multi-tenant).
11. **Are errors observable?** Logs/metrics for row counts, transaction failures, deadlocks/conflicts without logging sensitive data.

A key concluding question: **“Is there evidence in both schema and tests that a single call updates only the selected record without touching neighboring rows?”** If not, do not trust that the SQL merely looks specific enough.

## 17. Self-check questions

**1.** A table has `PRIMARY KEY(id)`. Can `UPDATE products SET name=? WHERE id=?` match two rows with the same id?  
**Answer:** No, if the DB truly enforces the primary key; under normal conditions at most one row matches. You still need to check `0` and access permissions.

**2.** A table has `PRIMARY KEY(tenant_id,id)`, with the same id 101 in tenants A and B. Is `WHERE id=101` safe?  
**Answer:** No; it can update both. Use `tenant_id=? AND id=?` with an authenticated tenant.

**3.** `UPDATE` returns 2, and Java throws an exception afterward. Is the data guaranteed to roll back?  
**Answer:** No, if the statement auto-committed; only a transaction can roll back under appropriate rules. Most importantly, keep predicates/constraints unique.

**4.** `UPDATE ... WHERE id=? AND version=?` returns 0. Does that guarantee the record was deleted?  
**Answer:** No; it could also be wrong tenant, filtered status, stale version, or specific DB semantics. Classify according to the contract.

**5.** Two requests both read version 0; the first increments version to 1, while the second still sends 0. Expected result?  
**Answer:** The second does not overwrite, returning `rows=0` if the version predicate is evaluated atomically by the DB.

**6.** Does `setRequiredRowsAffected(1)` on Spring `SqlUpdate` turn the SQL into `UPDATE ... LIMIT 1`?  
**Answer:** No; it checks the count after execution, without altering SQL scope.

**7.** Why shouldn't you use `SELECT MAX(id)` to find a newly created row and then update it?  
**Answer:** Other connections can insert concurrently, returning an id that does not belong to your operation. Use generated keys from the INSERT itself.

**8.** When is a multi-row `UPDATE` valid?  
**Answer:** When it is an intentionally designed bulk operation with its own predicates, permissions, rollback, and observability; distinct from keyed single-entity updates.

## Official references

- Spring Framework — `JdbcTemplate` and update SQL: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Framework — `@Transactional` settings and proxies: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — default rollback rules: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html
- Spring Framework API — `JdbcTemplate`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html
- Spring Framework API — `SqlUpdate` and `setRequiredRowsAffected`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/object/SqlUpdate.html
- Spring Framework — JDBC batch operations: https://docs.spring.io/spring-framework/reference/data-access/jdbc/advanced.html
- Spring Boot 3.5 — SQL databases/H2: https://docs.spring.io/spring-boot/3.5/reference/data/sql.html
- Java SE 17 — `PreparedStatement.executeUpdate()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/PreparedStatement.html
- Java SE 17 — JDBC batch counts: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Statement.html

**Conclusion:** To update **one** record safely, use **`UPDATE ... WHERE` containing a database-enforced unique key**, bind parameters instead of concatenating strings, **handle the affected row count properly**, add a **version** check under concurrency, and set **transaction boundaries** matching business requirements. Checking the row count is an error-detection step — **not** a license to write an overly broad predicate.