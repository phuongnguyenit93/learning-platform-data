# Testing SQL Statements, Filter Conditions, and Affected Row Counts

In a **Spring Boot application using JDBC**, a SQL query can execute without throwing an exception and still be **business-wrong**: a SELECT returns another tenant's data, a WHERE clause combines AND/OR without parentheses, archived records leak into results, an UPDATE touches too many rows, or a DELETE returns 0 while the API reports success. Therefore, SQL testing must verify **the exact record set, filter predicates, boundary values, affected row counts, and post-statement data state**.

This lesson focuses on **`JdbcTemplate`**, `PreparedStatement` parameter binding, **SELECT/UPDATE/DELETE**, affected-row counts of **0, 1, or N**, version-based optimistic updates, JDBC `batchUpdate`, NULLs, LIKE, and SQL injection prevention. The sample project runs with **Java 17, Spring Boot 3.4.5, Spring JDBC, H2, JUnit Jupiter, and `@JdbcTest`**. Tests execute real SQL against the embedded database; `JdbcTemplate` is never mocked. Stated results are **expected from code**, not Gradle logs executed during authoring.

## 1. What Is Correct SQL? Do Not Only Ask "Did It Return Data?"

Suppose a system has a `task_items` table where each row belongs to a tenant. Requirement: "List OPEN BUGs with priority at least 4, not archived, belonging to TENANT_A, sorted by priority descending then ID ascending."

A buggy SQL query might:

- Omit **`tenant_key = ?`**, leaking TENANT_B's tasks.
- Use **`priority > ?`** instead of **`>= ?`**, dropping records right on the threshold.
- Omit **`archived = FALSE`**, allowing soft-deleted tasks into the results.
- Have missing parentheses when mixing **AND/OR**, causing one branch to bypass the tenant filter.
- Lack a total **`ORDER BY`** order, making tests flaky whenever the DB changes query plans.
- Concatenate user input directly into SQL, risking injection.
- Only assert **`size() == 2`**; two wrong IDs can also yield size 2.

The fixture in this lesson is crafted so each bug above has a counterexample row:

| ID | Tenant | Category | Status | Priority | Archived | Meaning |
| ---: | --- | --- | --- | ---: | --- | --- |
| 1 | TENANT_A | BUG | OPEN | 5 | false | Matches |
| 2 | TENANT_A | FEATURE | OPEN | 2 | false | Different category/priority |
| 3 | TENANT_A | BUG | DONE | 3 | false | Different status |
| 4 | TENANT_B | BUG | OPEN | 5 | false | Different tenant; leaks if tenant filter omitted |
| 5 | TENANT_A | BUG | OPEN | 1 | true | Soft deleted |
| 6 | TENANT_A | BUG | OPEN | 5 | false | Matches; shares priority with ID 1 |
| 7 | TENANT_B | FEATURE | DONE | 4 | false | Catches OR without parentheses |

The right result for the target query is **[1, 6]**. Tests should assert **exact ordered IDs** and each row's attributes, plus negative cases for tenant B, archived rows, and priority boundaries.

## 2. SELECT with JdbcTemplate and Explicit WHERE Predicates

~~~sql
SELECT id, tenant_key, category, status,
       priority, version, title, reviewer, archived
FROM task_items
WHERE tenant_key = ?
  AND category = ?
  AND status = 'OPEN'
  AND priority >= ?
  AND archived = FALSE
ORDER BY priority DESC, id ASC;
~~~

The **`?`** markers are placeholders for **`PreparedStatement` values**. With `JdbcTemplate`, values must be supplied in the exact order:

~~~java
List<TaskRow> rows = jdbc.query(
        sql,
        rowMapper,
        "TENANT_A", "BUG", 4);
~~~

This is an excerpt, not a standalone program; section 7 contains the complete class. Binding prevents values from altering SQL structure, though it does not add authorization filters automatically. You must still write `WHERE tenant_key` explicitly.

**Cases to assert:**

| Input | Expected IDs |
| --- | --- |
| TENANT_A / BUG / minPriority=4 | [1,6] |
| TENANT_A / BUG / minPriority=5 | [1,6] |
| TENANT_A / BUG / minPriority=6 | [] |
| TENANT_B / BUG / minPriority=4 | [4] |
| TENANT_A / FEATURE / minPriority=4 | [] |

Two tasks with `priority=5` verify the **`id ASC`** tie-breaker. Never rely on natural INSERT order or primary-key scan order: without `ORDER BY`, SQL does not guarantee result order.

### Do Not Assert Only COUNT(*)

**`COUNT(*)`** counts rows matching a predicate. It **does not replace** asserting the actual list of IDs or values. A query missing a tenant filter can produce the same count on another fixture while returning the wrong set of rows. If business rules require strictly rows **1 and 6**, tests must name those two IDs.

## 3. AND/OR: Parentheses Preserve the Tenant Filter

Suppose we want unarchived tasks for tenant A with status OPEN **or** DONE.

**Correct:**

~~~sql
SELECT id
FROM task_items
WHERE tenant_key = ?
  AND archived = FALSE
  AND (status = 'OPEN' OR status = 'DONE')
ORDER BY id;
~~~

**Wrong:**

~~~sql
SELECT id
FROM task_items
WHERE tenant_key = ?
  AND archived = FALSE
  AND status = 'OPEN'
  OR status = 'DONE'
ORDER BY id;
~~~

Because **AND has higher precedence than OR**, the wrong query is equivalent to:

~~~text
(tenant_key = ? AND archived = FALSE AND status = 'OPEN')
OR status = 'DONE'
~~~

Every DONE row from other tenants leaks through. The fixture includes **ID 7 / TENANT_B / DONE** specifically to catch this bug. The right result for TENANT_A is **[1,2,3,6]**; seeing 7 indicates a data-leak risk.

Complex queries with multiple OR/IN branches should test each branch plus a row intentionally crafted to match the wrong branch. When building dynamic WHERE clauses, avoid concatenating user input into SQL; use **`NamedParameterJdbcTemplate`** with named values or `JdbcTemplate` positional binding and group predicates explicitly.

## 4. SQL NULL, LIKE, and Special Characters

### 4.1. NULL Requires IS NULL

To find tasks with no reviewer assigned:

~~~sql
SELECT id FROM task_items
WHERE tenant_key = ?
  AND reviewer IS NULL
  AND archived = FALSE
ORDER BY id;
~~~

**`reviewer = NULL`** never evaluates to TRUE in SQL three-valued logic; comparing against NULL produces UNKNOWN, and WHERE filters out the row. Empty string **`''`** is not equivalent to NULL across all DBs either. The fixture has both NULL and non-NULL reviewers, so the right test returns **[1,3]** for unarchived TENANT_A tasks.

### 4.2. PreparedStatement Does Not Automatically Escape LIKE Wildcards

In **LIKE**, percent **`%`** and underscore **`_`** are wildcards. Even when bound via `PreparedStatement`, a user-entered **`%`** still acts as a wildcard unless escaped. To search for a **literal percent sign** inside `title`, pick an escape character such as **`!`**:

~~~sql
SELECT id FROM task_items
WHERE tenant_key = ?
  AND archived = FALSE
  AND title LIKE ? ESCAPE '!'
ORDER BY id;
~~~

Java turns the fragment into a literal pattern:

~~~java
String escaped = fragment
        .replace("!", "!!")
        .replace("%", "!%")
        .replace("_", "!_");
String pattern = "%" + escaped + "%";
~~~

When `fragment` is **`%`**, the pattern becomes **`%!%%`**: any prefix, literal percent sign, any suffix. The fixture has title **`Plan 100% complete`** at ID 2, so the expected IDs are **[2]**. Without escaping, the pattern matches nearly every title.

### 4.3. Input Values Must Be Data, Not SQL Code

**Do not do this:**

~~~java
String unsafe = "UPDATE task_items SET title = '"
        + userTitle + "' WHERE id = " + id;
~~~

This is an **intentionally wrong example**. Input containing quotes or comment markers can alter the SQL statement. Use:

~~~java
jdbc.update(
        "UPDATE task_items SET title=? WHERE id=? AND tenant_key=?",
        userTitle, id, tenant);
~~~

When letting users pick an ORDER BY column name, **identifiers cannot be bound with `?`**. Use a server-side allowlist—e.g., accepting only `"priority"` or `"id"` and mapping to SQL constants. Never trust a raw `sortKey` straight from the request.

## 5. JdbcTemplate.update: What Does the Affected Row Count Mean?

`JdbcTemplate.update(...)` returns an **`int` update count** reported by the JDBC driver. It serves as evidence of how many rows the statement affected per driver/DB semantics. Scenarios:

| Count | Common Contract | What to Verify Next |
| ---: | --- | --- |
| **0** | No matching row, or not counted as affected by driver | No wrong row was modified; determine conflict/not-found/unauthorized if business requires |
| **1** | One row affected | Did it hit the intended ID/tenant, state, and version? |
| **N > 1** | Bulk operation or overly broad WHERE | Is N the expected count, and are out-of-scope rows untouched? |
| **Exception** | Constraint, syntax, connection, transaction error... | Right exception category, rollback, and final data state |

**Do not deduce from `count=0` that the ID does not exist.** The statement has multiple predicates: the ID might exist under another tenant, stale version, invalid status, or `archived=true`. The API layer should avoid leaking whether a resource belongs to another tenant just because a caller probed an ID.

Additionally, some engines/drivers distinguish **rows matched** from **rows actually modified** when an UPDATE writes the exact same value. Do not write portable expectations that "a no-op UPDATE always returns 0" across all databases. In this example, the versioned UPDATE **actually changes status and increments version**, making the count check unambiguous.

## 6. UPDATE by ID, Tenant, Version, and Status

~~~sql
UPDATE task_items
SET status = 'DONE',
    version = version + 1
WHERE id = ?
  AND tenant_key = ?
  AND version = ?
  AND status = 'OPEN'
  AND archived = FALSE;
~~~

With **ID 1, TENANT_A, expectedVersion=0**, the first call returns **1** and transitions OPEN -> DONE, version 0 -> 1. A second call still passing `expectedVersion=0` returns **0**, because version and status changed. For **ID 6** at version 2 when passing `expectedVersion=1`, it returns **0**. For ID 4 belonging to tenant B when passing TENANT_A, it also returns **0**.

This is a database-level **compare-and-set**: the version predicate is checked inside the UPDATE itself rather than running SELECT and checking in Java beforehand. That reduces **lost update** risks under concurrent requests. Still, it does not replace overall business conflict handling or transaction policy.

**0 rows has more than one cause**: missing ID, wrong tenant, stale version, DONE status, or archived. If distinct domain errors must be reported, the service must design an authorized follow-up lookup without leaking the existence of another tenant's ID.

### Bulk Update Intentionally Affecting N Rows

~~~sql
UPDATE task_items
SET archived = TRUE, version = version + 1
WHERE tenant_key = ?
  AND status = 'DONE'
  AND archived = FALSE;
~~~

In the fixture, TENANT_A has exactly **one unarchived DONE row** (ID 3). The archive command returns **1**, and a repeat run returns **0**. ID 7 is DONE for TENANT_B so it must remain `archived=false`. Omitting the tenant predicate fails both count and state checks.

### DELETE Must Also Check Surviving Rows

~~~sql
DELETE FROM task_items
WHERE tenant_key = ?
  AND archived = TRUE;
~~~

For TENANT_A, this SQL deletes ID 5 and returns **1**; running again returns **0**. TENANT_A's row count drops from **5 to 4**, but more importantly **ID 4 of tenant B and A's unarchived tasks stay intact**. A DELETE test that only asserts `count=1` is insufficient: a buggy DELETE can also remove one row, just the **wrong row**.

## 7. Runnable Project: Spring Boot 3.4.5, Spring JDBC, and H2

The project uses a manual SQL repository, a Java record for a row, and `@JdbcTest` executing SQL against embedded H2. Tests do not depend on a web server or external DB.

**Structure:**

~~~text
settings.gradle
build.gradle
src/main/java/com/example/sqlqa/SqlQaApplication.java
src/main/java/com/example/sqlqa/TaskRow.java
src/main/java/com/example/sqlqa/TaskItemJdbcRepository.java
src/test/resources/application.properties
src/test/resources/schema.sql
src/test/resources/data.sql
src/test/java/com/example/sqlqa/TaskItemJdbcRepositoryTest.java
~~~

### 7.1. Gradle and Test Configuration

**settings.gradle**

~~~groovy
rootProject.name = 'spring-jdbc-sql-qa'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.4.5'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**src/test/resources/application.properties**

~~~properties
spring.datasource.generate-unique-name=true
spring.sql.init.mode=always
~~~

**`spring-boot-starter-jdbc`** configures `DataSource` and `JdbcTemplate`. **`spring-boot-starter-test`** brings JUnit Jupiter and Spring TestContext. Embedded H2 runs on the test classpath. **`@JdbcTest`** rolls back each test method by default; the datasource is an embedded DB and ordinary `@Component` repositories are not auto-scanned. The test uses **`@Import`** to register the real repository.

**`schema.sql`** and **`data.sql`** sit in `src/test/resources` and are loaded by SQL initialization when the test `ApplicationContext` starts. In projects already using Flyway/Liquibase/production schemas, pick one dedicated migration/fixture strategy to avoid duplicate table creation scripts.

### 7.2. Schema with Tenant and Soft-Delete

**src/test/resources/schema.sql**

~~~sql
CREATE TABLE task_items (
    id BIGINT PRIMARY KEY,
    tenant_key VARCHAR(40) NOT NULL,
    category VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL,
    priority INTEGER NOT NULL,
    version INTEGER NOT NULL,
    title VARCHAR(120) NOT NULL,
    reviewer VARCHAR(60),
    archived BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX idx_task_tenant_status
    ON task_items (tenant_key, status, archived, priority);
~~~

Fixture IDs are supplied explicitly so tests do not depend on auto-increment sequences. **`reviewer` is nullable** to test `IS NULL`. **`archived`** is the soft-delete flag. **`version`** is an integer column for SQL optimistic updates, not JPA `@Version` (this project does not use JPA).

### 7.3. Fixtures Containing Both Matching and Non-Matching Rows

**src/test/resources/data.sql**

~~~sql
INSERT INTO task_items
 (id, tenant_key, category, status, priority,
  version, title, reviewer, archived)
VALUES
 (1, 'TENANT_A', 'BUG', 'OPEN', 5,
  0, 'Bug A-1', NULL, FALSE),
 (2, 'TENANT_A', 'FEATURE', 'OPEN', 2,
  0, 'Plan 100% complete', 'Mai', FALSE),
 (3, 'TENANT_A', 'BUG', 'DONE', 3,
  1, 'Bug A-done', NULL, FALSE),
 (4, 'TENANT_B', 'BUG', 'OPEN', 5,
  0, 'Bug B-1', NULL, FALSE),
 (5, 'TENANT_A', 'BUG', 'OPEN', 1,
  0, 'Already archived', NULL, TRUE),
 (6, 'TENANT_A', 'BUG', 'OPEN', 5,
  2, 'Bug A-2', 'An', FALSE),
 (7, 'TENANT_B', 'FEATURE', 'DONE', 4,
  0, 'Other tenant done', 'Bao', FALSE);
~~~

Never pare a fixture down to a single row; otherwise SQL missing tenant/status/archived predicates could still pass. Having **ID 7 DONE from another tenant** catches OR grouping mistakes, **ID 5 archived** catches missing soft-delete filters, **ID 1 and 6 sharing priority** tests the tie-breaker, and **ID 2 with `%`** tests LIKE escaping.

### 7.4. Application and Return Data Type

**src/main/java/com/example/sqlqa/SqlQaApplication.java**

~~~java
package com.example.sqlqa;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SqlQaApplication {
    public static void main(String[] args) {
        SpringApplication.run(SqlQaApplication.class, args);
    }
}
~~~

**src/main/java/com/example/sqlqa/TaskRow.java**

~~~java
package com.example.sqlqa;

public record TaskRow(
        long id,
        String tenantKey,
        String category,
        String status,
        int priority,
        int version,
        String title,
        String reviewer,
        boolean archived) {
}
~~~

The Java record lets tests access fields via `id()`, `tenantKey()`, `status()`, etc. This is **not a JPA entity**, has no dirty checking, and every update goes through `JdbcTemplate.update`.

### 7.5. JDBC Repository Executing SQL Statements

**src/main/java/com/example/sqlqa/TaskItemJdbcRepository.java**

~~~java
package com.example.sqlqa;

import java.util.Arrays;
import java.util.List;
import java.util.Optional;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;

@Repository
public class TaskItemJdbcRepository {
    private final JdbcTemplate jdbc;

    private static final String COLUMNS = """
            SELECT id, tenant_key, category, status,
                   priority, version, title, reviewer, archived
            FROM task_items
            """;

    private static final RowMapper<TaskRow> MAPPER =
            (rs, number) -> new TaskRow(
                    rs.getLong("id"),
                    rs.getString("tenant_key"),
                    rs.getString("category"),
                    rs.getString("status"),
                    rs.getInt("priority"),
                    rs.getInt("version"),
                    rs.getString("title"),
                    rs.getString("reviewer"),
                    rs.getBoolean("archived"));

    public TaskItemJdbcRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<TaskRow> findOpenCritical(
            String tenant, String category, int minimum) {
        return jdbc.query(COLUMNS + """
                WHERE tenant_key = ?
                  AND category = ?
                  AND status = 'OPEN'
                  AND priority >= ?
                  AND archived = FALSE
                ORDER BY priority DESC, id ASC
                """, MAPPER, tenant, category, minimum);
    }

    public List<TaskRow> findActiveOpenOrDone(String tenant) {
        return jdbc.query(COLUMNS + """
                WHERE tenant_key = ?
                  AND archived = FALSE
                  AND (status = 'OPEN' OR status = 'DONE')
                ORDER BY id
                """, MAPPER, tenant);
    }

    public List<TaskRow> findUnassigned(String tenant) {
        return jdbc.query(COLUMNS + """
                WHERE tenant_key = ?
                  AND reviewer IS NULL
                  AND archived = FALSE
                ORDER BY id
                """, MAPPER, tenant);
    }

    public List<TaskRow> searchLiteralTitle(
            String tenant, String fragment) {
        String escaped = fragment.replace("!", "!!")
                .replace("%", "!%")
                .replace("_", "!_");
        String pattern = "%" + escaped + "%";

        return jdbc.query(COLUMNS + """
                WHERE tenant_key = ?
                  AND archived = FALSE
                  AND title LIKE ? ESCAPE '!'
                ORDER BY id
                """, MAPPER, tenant, pattern);
    }

    public Optional<TaskRow> findForTenant(
            long id, String tenant) {
        List<TaskRow> rows = jdbc.query(COLUMNS + """
                WHERE id = ? AND tenant_key = ?
                """, MAPPER, id, tenant);
        return rows.stream().findFirst();
    }

    public int closeOpenWithVersion(
            long id, String tenant, int expectedVersion) {
        return jdbc.update("""
                UPDATE task_items
                SET status = 'DONE', version = version + 1
                WHERE id = ?
                  AND tenant_key = ?
                  AND version = ?
                  AND status = 'OPEN'
                  AND archived = FALSE
                """, id, tenant, expectedVersion);
    }

    public int changeTitle(
            long id, String tenant, String title) {
        return jdbc.update("""
                UPDATE task_items
                SET title = ?
                WHERE id = ?
                  AND tenant_key = ?
                  AND archived = FALSE
                """, title, id, tenant);
    }

    public int archiveDone(String tenant) {
        return jdbc.update("""
                UPDATE task_items
                SET archived = TRUE, version = version + 1
                WHERE tenant_key = ?
                  AND status = 'DONE'
                  AND archived = FALSE
                """, tenant);
    }

    public int deleteArchived(String tenant) {
        return jdbc.update("""
                DELETE FROM task_items
                WHERE tenant_key = ?
                  AND archived = TRUE
                """, tenant);
    }

    public int[] raisePriorities(String tenant, long... ids) {
        List<Object[]> args = Arrays.stream(ids)
                .mapToObj(id -> new Object[]{tenant, id})
                .toList();

        return jdbc.batchUpdate("""
                UPDATE task_items
                SET priority = priority + 1
                WHERE tenant_key = ?
                  AND id = ?
                  AND archived = FALSE
                """, args);
    }
}
~~~

Key aspects to protect in this repository:

- Every business query **receives `tenant` via a bind parameter**; SELECT/UPDATE/DELETE all include explicit predicates.
- **`COLUMNS`** is the shared SELECT field list; `RowMapper` turns `ResultSet` into `TaskRow` by column name.
- **`findOpenCritical`** verifies `>=`, `archived`, and the `ORDER BY` tie-breaker.
- **`findActiveOpenOrDone`** groups OR with parentheses.
- **`findUnassigned`** uses `IS NULL`.
- **`searchLiteralTitle`** escapes wildcards and uses `LIKE ... ESCAPE '!'`.
- **`findForTenant`** returns `Optional` for 0 rows; `queryForObject` on 0 rows would throw `EmptyResultDataAccessException`.
- **`closeOpenWithVersion`** is an atomic SQL predicate for optimistic updates.
- **`changeTitle`** binds input strictly as data, even when containing quotes.
- **`archiveDone`** may affect multiple rows while staying scoped by tenant/status.
- **`deleteArchived`** must remove only already-archived rows.
- **`raisePriorities`** is a JDBC batch update across multiple argument sets; interpret the count array according to the JDBC driver.

There are no mocked repositories or `JdbcTemplate` stubs in the suite: the goal of the lesson is proving **real SQL execution**.

## 8. JUnit 5 Tests with @JdbcTest and @Import

**src/test/java/com/example/sqlqa/TaskItemJdbcRepositoryTest.java**

~~~java
package com.example.sqlqa;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@JdbcTest
@Import(TaskItemJdbcRepository.class)
class TaskItemJdbcRepositoryTest {
    @Autowired
    private TaskItemJdbcRepository repository;

    @Autowired
    private JdbcTemplate jdbc;

    @Test
    void selectChecksEveryPredicateAndStableOrder() {
        List<TaskRow> rows = repository.findOpenCritical(
                "TENANT_A", "BUG", 4);

        assertEquals(List.of(1L, 6L),
                rows.stream().map(TaskRow::id).toList());
        assertTrue(rows.stream().allMatch(row ->
                row.tenantKey().equals("TENANT_A")
                && row.category().equals("BUG")
                && row.status().equals("OPEN")
                && row.priority() >= 4
                && !row.archived()));
    }

    @Test
    void boundaryAndWrongTenantAreExcluded() {
        assertEquals(List.of(1L, 6L),
                repository.findOpenCritical("TENANT_A", "BUG", 5)
                        .stream().map(TaskRow::id).toList());

        assertTrue(repository.findOpenCritical(
                "TENANT_A", "BUG", 6).isEmpty());

        assertEquals(List.of(4L),
                repository.findOpenCritical("TENANT_B", "BUG", 4)
                        .stream().map(TaskRow::id).toList());

        assertTrue(repository.findOpenCritical(
                "TENANT_A", "FEATURE", 4).isEmpty());
    }

    @Test
    void orGroupDoesNotLeakOtherTenants() {
        List<Long> ids = repository.findActiveOpenOrDone("TENANT_A")
                .stream().map(TaskRow::id).toList();

        assertEquals(List.of(1L, 2L, 3L, 6L), ids);
        assertFalse(ids.contains(7L));
        assertFalse(ids.contains(5L));
    }

    @Test
    void nullAndLikeHavePreciseSemantics() {
        assertEquals(List.of(1L, 3L),
                repository.findUnassigned("TENANT_A")
                        .stream().map(TaskRow::id).toList());

        List<TaskRow> matches =
                repository.searchLiteralTitle("TENANT_A", "%");
        assertEquals(List.of(2L),
                matches.stream().map(TaskRow::id).toList());
        assertEquals("Plan 100% complete", matches.get(0).title());
    }

    @Test
    void findByIdCannotIgnoreTenant() {
        assertTrue(repository.findForTenant(
                4L, "TENANT_A").isEmpty());
        assertEquals("TENANT_B",
                repository.findForTenant(4L, "TENANT_B")
                        .orElseThrow().tenantKey());
    }

    @Test
    void exactOneThenZeroOnOptimisticUpdate() {
        int first = repository.closeOpenWithVersion(
                1L, "TENANT_A", 0);
        assertEquals(1, first);

        TaskRow changed = repository.findForTenant(
                1L, "TENANT_A").orElseThrow();
        assertEquals("DONE", changed.status());
        assertEquals(1, changed.version());

        assertEquals(0, repository.closeOpenWithVersion(
                1L, "TENANT_A", 0));
        assertEquals(0, repository.closeOpenWithVersion(
                6L, "TENANT_A", 1));
        assertEquals(0, repository.closeOpenWithVersion(
                4L, "TENANT_A", 0));

        assertEquals("OPEN",
                repository.findForTenant(4L, "TENANT_B")
                        .orElseThrow().status());
        assertEquals("OPEN",
                repository.findForTenant(6L, "TENANT_A")
                        .orElseThrow().status());
    }

    @Test
    void preparedParametersPreventTitleSqlInjection() {
        String suspicious = "x', status='DONE' --";
        assertEquals(1, repository.changeTitle(
                1L, "TENANT_A", suspicious));

        TaskRow row = repository.findForTenant(
                1L, "TENANT_A").orElseThrow();
        assertEquals(suspicious, row.title());
        assertEquals("OPEN", row.status());

        assertEquals(0, repository.changeTitle(
                4L, "TENANT_A", "wrong tenant"));
        assertEquals("Bug B-1",
                repository.findForTenant(4L, "TENANT_B")
                        .orElseThrow().title());
    }

    @Test
    void bulkArchiveChecksCountAndUntouchedTenant() {
        assertEquals(1, repository.archiveDone("TENANT_A"));
        assertEquals(0, repository.archiveDone("TENANT_A"));

        TaskRow archived = repository.findForTenant(
                3L, "TENANT_A").orElseThrow();
        assertTrue(archived.archived());
        assertEquals(2, archived.version());

        TaskRow other = repository.findForTenant(
                7L, "TENANT_B").orElseThrow();
        assertFalse(other.archived());
        assertEquals(0, other.version());
    }

    @Test
    void deletionAffectsOnlyArchivedRows() {
        long before = jdbc.queryForObject(
                "SELECT COUNT(*) FROM task_items "
                        + "WHERE tenant_key = 'TENANT_A'",
                Long.class);
        assertEquals(5L, before);

        assertEquals(1, repository.deleteArchived("TENANT_A"));
        assertEquals(0, repository.deleteArchived("TENANT_A"));

        long after = jdbc.queryForObject(
                "SELECT COUNT(*) FROM task_items "
                        + "WHERE tenant_key = 'TENANT_A'",
                Long.class);
        assertEquals(4L, after);
        assertEquals(0, jdbc.queryForObject(
                "SELECT COUNT(*) FROM task_items WHERE id=5",
                Integer.class).intValue());
        assertEquals(1, jdbc.queryForObject(
                "SELECT COUNT(*) FROM task_items WHERE id=4",
                Integer.class).intValue());
    }

    @Test
    void batchReturnsPerStatementCounts() {
        int[] affected = repository.raisePriorities(
                "TENANT_A", 1L, 2L, 4L);
        assertArrayEquals(new int[]{1, 1, 0}, affected);

        assertEquals(6, repository.findForTenant(
                1L, "TENANT_A").orElseThrow().priority());
        assertEquals(3, repository.findForTenant(
                2L, "TENANT_A").orElseThrow().priority());
        assertEquals(5, repository.findForTenant(
                4L, "TENANT_B").orElseThrow().priority());
    }
}
~~~

**Why `@Import`?** `@JdbcTest` focuses on JDBC infrastructure and database setup and does not auto-scan regular business `@Repository` beans. **`@Import(TaskItemJdbcRepository.class)`** registers the real repository implementation so tests execute real SQL rather than mocks.

**Why are the tests independent?** `@JdbcTest` runs each test method in a transaction and **rolls back** by default. Therefore updates/deletes in an earlier test do not remove fixtures for later tests. Schema and data load when the test context initializes. If replaced by a real HTTP `@SpringBootTest`, `@Transactional` on a JUnit test method does not auto-rollback server request threads; separate cleanup is required.

### 8.1. Evidence from SELECT and Filters

- **`selectChecksEveryPredicateAndStableOrder`** verifies `[1,6]` and all row conditions.
- **`boundaryAndWrongTenantAreExcluded`** catches `>` instead of `>=`, omitted tenant filter, or wrong category.
- **`orGroupDoesNotLeakOtherTenants`** catches missing AND/OR parentheses via ID 7 tenant B DONE.
- **`nullAndLikeHavePreciseSemantics`** catches `reviewer = NULL` and unescaped `%` in LIKE via expected IDs `[1,3]` / `[2]`.
- **`findByIdCannotIgnoreTenant`** proves ID 4 exists yet cannot be read under TENANT_A.

### 8.2. Evidence from UPDATE/DELETE

- **`exactOneThenZeroOnOptimisticUpdate`**: first call modifies ID 1 (`count=1`) and increments version; stale ID 1, stale ID 6, and wrong-tenant ID 4 all return 0; excluded rows remain unchanged.
- **`preparedParametersPreventTitleSqlInjection`**: input containing quotes and comment markers is stored verbatim without altering SQL structure or status.
- **`bulkArchiveChecksCountAndUntouchedTenant`**: only ID 3 DONE of tenant A is archived; counts 1 then 0; ID 7 DONE of tenant B stays untouched.
- **`deletionAffectsOnlyArchivedRows`**: only archived ID 5 of A is deleted, A count drops 5→4, ID 4 of tenant B remains.
- **`batchReturnsPerStatementCounts`**: H2 returns `[1,1,0]` for updating ID 1 A, ID 2 A, and ID 4 B under tenant A; also verifies priorities after update.

**Do not assert only the returned count.** An UPDATE with a faulty WHERE clause can affect 1 row—just not the target row. Hence the tests read data back after operations.

## 9. Running Tests and Expected Results

Create a Gradle Wrapper compatible with JDK 17 and Spring Boot 3.4.x. In the project directory run:

~~~bash
./gradlew clean test
./gradlew test --tests com.example.sqlqa.TaskItemJdbcRepositoryTest
~~~

On Windows use **`gradlew.bat`** with the same arguments. The tests are **designed to PASS** when files, dependencies, and configuration match the lesson; this is **expected from code**, not observed Gradle stdout.

Expected results table:

| Test | Key Values |
| --- | --- |
| selectChecksEveryPredicateAndStableOrder | ID [1,6] |
| boundaryAndWrongTenantAreExcluded | [1,6], [], [4], [] |
| orGroupDoesNotLeakOtherTenants | [1,2,3,6], no ID7 |
| nullAndLikeHavePreciseSemantics | Reviewer NULL [1,3], literal % [2] |
| exactOneThenZeroOnOptimisticUpdate | Counts 1,0,0,0; ID1 DONE/version1 |
| preparedParametersPreventTitleSqlInjection | Count 1, status remains OPEN |
| bulkArchiveChecksCountAndUntouchedTenant | Counts 1 then 0, ID7 unchanged |
| deletionAffectsOnlyArchivedRows | DELETE 1 then 0, A total 5→4 |
| batchReturnsPerStatementCounts | Batch [1,1,0], B unaffected |

Do not pin tests to identical SQL stdout or execution plans across databases: drivers, query optimizers, and dialects differ. The contract lies in **results and state**, not SQL log whitespace.

## 10. Affected Rows: Crucial Misconceptions

### 10.1. 0 Rows Does Not Reveal the Reason

With a multi-predicate UPDATE, **`0`** can mean the ID does not exist, the tenant is unauthorized, `expectedVersion` is stale, status is already DONE, or `archived=true`. A multi-tenant API should not respond in a way that lets a client deduce whether another tenant's ID exists. Pick 404/409/403 responses according to a controlled policy rather than guessing the cause from the count alone.

### 10.2. Counting Before UPDATE Does Not Guarantee the UPDATE Count

If a prior `SELECT COUNT(*)` finds 1 matching row, another transaction can alter state before the UPDATE runs. **Counting before an UPDATE does not make the update atomic**. For optimistic concurrency, put the version check directly in the **UPDATE's WHERE clause**, then use the update count as a compare-and-set signal.

### 10.3. Matched vs. Changed Rows Are Driver-Specific

A SQL UPDATE setting a column to its current value may report either matched rows or modified rows depending on the DB/config. Never write portable tests expecting count to always be 0 for a no-op. This example uses **`version = version + 1`**, so every successful update produces an actual change.

### 10.4. Batch Counts Have Special Status Codes

JDBC `batchUpdate` can return **`Statement.SUCCESS_NO_INFO = -2`** (succeeded without a specific row count) or **`Statement.EXECUTE_FAILED = -3`** depending on error handling/driver. Never sum **`[1,-2,0]`** to `-1` and infer total affected rows. When a batch fails, inspect the translated `DataAccessException`/`BatchUpdateException`, transaction rollback, per-row state, and required atomicity.

H2 tests in this lesson **expect `[1,1,0]`**, while a production driver may report differently; test on the real engine/driver whenever exact counts are part of the business contract.

### 10.5. One Bulk Statement Differs from a JDBC Batch

**`UPDATE ... WHERE tenant_key=?`** updates N rows in **a single SQL statement**, and `JdbcTemplate.update` returns one count. **`JdbcTemplate.batchUpdate`** executes a `PreparedStatement` with N parameter sets and returns an **array of counts**. The two differ in transaction behavior, error handling, and performance. Never reuse the exact same assertions across both approaches.

## 11. Logging SQL, Inspecting Queries, and Avoiding "Green Mock" Tests

You can enable logging for diagnostics:

~~~properties
logging.level.org.springframework.jdbc.core.JdbcTemplate=DEBUG
logging.level.org.springframework.jdbc.core.StatementCreatorUtils=TRACE
~~~

Enable this logging only in test/dev when needed; parameter values can contain sensitive data. Logs show SQL and bind values, yet **do not prove WHERE is right**. You still need fixtures with counterexample rows and behavioral assertions.

A Mockito test like **`verify(jdbcTemplate).update(sql, params)`** verifies that a Java builder passes the expected argument list, but misses SQL syntax errors, wrong column names, or constraint violations. For the goals of this lesson, **`@JdbcTest` with a real database** provides far stronger evidence.

DataSource proxies/spies can assert SQL structure in systems requiring hints, query routing, or statement-count limits. Never couple a unit test to exact SQL whitespace or aliases when the contract to protect is the business row set. For performance, inspect query plans/`EXPLAIN` on the real database with representative data volumes.

## 12. Where Does H2 Differ from Production Databases?

H2 is suited for testing JDBC wiring, basic SQL syntax, parameter binding, WHERE logic, and row update results. Watch for these differences:

- PostgreSQL/MySQL/Oracle dialects and syntax (`UPSERT`, `RETURNING`, functions, JSON types).
- Collations, case sensitivity, Unicode, and LIKE matching.
- JDBC update-count semantics for matched vs. changed rows.
- Isolation, locking, deadlocks, and optimistic/pessimistic conflicts.
- Constraint timing, foreign keys, unique indexes, and transaction behavior.
- Query plans/index usage and large-dataset performance.
- Flyway/Liquibase schema migrations in production.

Whenever a feature depends on vendor behavior, supplement with **Testcontainers** running the deployment-matched database engine and version. A green H2 test does not prove production SQL dialect, transaction isolation, or query plans.

## 13. @Sql, TestContext Transactions, and Rollback

Spring TestContext lets you seed scripts with **`@Sql`** before or after a test method. Note that **`@SqlConfig(transactionMode=ISOLATED)`** runs the script in its own transaction and commits it, so the test method's rollback will not remove that data. Never mix committed seed scripts with an assumption that "all data rolls back".

In the project above, the SQL initializer loads schema and data on test context startup, while DML inside test methods is rolled back by `@JdbcTest`. If you genuinely want to prove commit visibility, write a dedicated transaction-lifecycle test rather than relying on default rollback and inferring another client sees the row.

**`@JdbcTest` is not `@SpringBootTest`**: the slice does not automatically load every `@Service`, MVC controller, or security filter. It is sufficient to prove a SQL repository against `DataSource`/H2 and test transactions. To test controller → service → SQL, add a full-context integration test, keeping in mind that HTTP server threads run outside the JUnit test method's transaction.

**JUnit preemptive timeout warning:** Spring transactions are normally thread-bound. If `assertTimeoutPreemptively` or another framework executes the test body on a different thread, DML may run outside the test-managed transaction and fail to roll back as expected. Use non-preemptive timeouts or manage transactions explicitly.

## 14. Dynamic Queries and NamedParameterJdbcTemplate

When category/status filters are lists, **`NamedParameterJdbcTemplate`** binds collections cleanly for `IN` clauses:

~~~java
String sql = """
    SELECT id FROM task_items
    WHERE tenant_key = :tenant
      AND category IN (:categories)
      AND archived = FALSE
    ORDER BY id
    """;

MapSqlParameterSource params = new MapSqlParameterSource()
        .addValue("tenant", "TENANT_A")
        .addValue("categories", List.of("BUG", "FEATURE"));

List<Long> ids = namedJdbc.queryForList(
        sql, params, Long.class);
~~~

This is an **excerpt**, not part of the runnable source; it requires imports, a `NamedParameterJdbcTemplate namedJdbc` field, and explicit handling of empty category lists. Some DBs reject **`IN ()`**, so decide whether an empty list means "no match" or "no filter" before constructing SQL. Never concatenate user input directly into `IN (...)`.

Sort columns and directions also need an allowlist:

~~~java
String column = switch (sortKey) {
    case "priority" -> "priority";
    case "id" -> "id";
    default -> throw new IllegalArgumentException("invalid sort");
};
~~~

This excerpt lives in a method with `sortKey`. Append only `ASC`/`DESC` from an enum or allowlist afterward. `PreparedStatement` protects **values**, not column or table identifiers.

## 15. Common SQL Bugs and How to Catch Them

| SQL Bug | Symptom | Required Assertion |
| --- | --- | --- |
| Missing tenant filter | Tenant B ID leaks | Exact ordered IDs, assert absence of ID4/7 |
| Unparenthesized OR | Tenant B DONE leaks into tenant A | Fixture ID7, expected `[1,2,3,6]` |
| `>` instead of `>=` | Drops ID right at priority threshold | Priority=5, min=5 returns `[1,6]` |
| Missing `archived=false` | ID5 appears | Expected list excludes ID5 |
| `ORDER BY` missing tie-breaker | Unstable ordering | ID1 and ID6 share priority, `id ASC` |
| `reviewer = NULL` | Misses NULL reviewers | `IS NULL` test expects `[1,3]` |
| Unescaped `%` in LIKE | Matches too many rows | Literal `%` matches only ID2 |
| Direct SQL string concatenation | Injection / syntax error | Suspicious title stored verbatim |
| UPDATE missing `expectedVersion` | Stale request overwrites row | Wrong version returns count 0 |
| UPDATE missing tenant | Modifies tenant B's ID4 | Tenant A updating ID4 returns 0, B unchanged |
| Bulk UPDATE missing status | Archives OPEN rows | ID3 changes, ID1/2/6 stay active |
| DELETE missing `archived` | Deletes active tasks | Only ID5 disappears |
| Asserting only affected count | Deleting wrong row also gives count 1 | Read back IDs and untouched rows |
| Summing batch counts wrongly | Contains `-2`/`-3` | Check JDBC codes and final data state |
| Mocking JDBC instead of DB | Misses syntax/schema bugs | `@JdbcTest` + H2 |
| Green alone, fails in suite | Fixture/transaction/context state leak | Rollback, SQL init, clear `@Sql` policy |
| H2 green, prod broken | Different dialect/driver/isolation | Testcontainers real DB engine |

## 16. Self-Check Exercises

**A.** SELECT returns the expected two rows, except one belongs to TENANT_B. Is asserting `size == 2` enough? **No.** Assert exact IDs and tenant, not just count.

**B.** What risk does `WHERE tenant=? AND status='OPEN' OR status='DONE'` carry? **Unparenthesized OR** can bypass the tenant check for the DONE branch.

**C.** `SELECT COUNT(*)` before UPDATE returns 1; is the subsequent UPDATE guaranteed to return count 1? **No.** Data or transactions can change concurrently; use the real UPDATE count.

**D.** If UPDATE returns 0, does that prove the ID does not exist? **No.** Wrong tenant, stale version, wrong status, or archived can all yield 0.

**E.** Does `PreparedStatement` escape `%` inside LIKE automatically? **No.** Escape pattern wildcards explicitly when searching for literal characters.

**F.** Must an UPDATE with the same old value return 0 on every DB? **No.** Matched vs. changed row counts depend on the driver.

**G.** `@JdbcTest` modifies a row, yet the next test still sees the old fixture. Why? Test DML is rolled back after each method.

**H.** Does DELETE returning count 1 prove the intended ID was deleted? **Not yet.** Verify row identity and that surviving rows are intact.

**I.** Can batch result `[1,-2,0]` be summed to `-1` affected rows? **No.** `-2` is `SUCCESS_NO_INFO`, not a negative row count.

**J.** Does H2 passing prove PostgreSQL uses the same query plan and locking? **No.** Test against the real engine.

**K.** Does a test verifying Mockito `JdbcTemplate.update` invocation prove the SQL is valid? **No**; the SQL never ran against a DB.

**L.** Why is a versioned UPDATE stronger than SELECT-check-UPDATE? Because **`WHERE version` and `SET version+1`** form a single compare-and-set SQL statement, reducing races between two separate operations.

### QA Checklist

- Are there enough fixtures for both matching rows and rows that **must not match**?
- Do SELECT tests assert exact IDs, ordering, tenant/category/status/priority/archived?
- Are AND/OR grouped with parentheses, and NULL checked via `IS NULL`?
- Does LIKE escape `%`/`_` when matching literals?
- Are user values bound via `?` or named parameters, and identifiers/sort keys allowlisted?
- Do UPDATE/DELETE assert **0/1/N per contract** and **post-operation state**?
- Are rows **outside WHERE** asserted untouched?
- Do optimistic updates use a version predicate rather than checking only in Java?
- Do `batchUpdate` counts handle driver-specific `-2`/`-3`?
- Does `@JdbcTest` include the real repository via `@Import` and reliable H2 fixtures?
- Are rollback vs. commit and HTTP server threads kept distinct?
- Are production DB engine tests present for SQL dialect, collation, and isolation when needed?

**Conclusion:** Reliable SQL tests verify far more than whether a statement runs without error. For **SELECT**, protect the exact ID set, tenant isolation, predicates, and `ORDER BY`. For **UPDATE/DELETE**, assert affected row counts, read back **the exact modified rows**, and confirm out-of-scope rows stay untouched. **`@JdbcTest` + H2** catches errors early and fast; whenever behavior depends on the driver or production database, add integration tests on the real engine.

## Official Documentation

- Spring Framework — JDBC Core and `JdbcTemplate` query/update: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Boot 3.4 — `@JdbcTest` Javadoc, embedded DB, and rollback: https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/test/autoconfigure/jdbc/JdbcTest.html
- Spring Boot 3.4 — Slice Auto-configuration: https://docs.spring.io/spring-boot/3.4/appendix/test-auto-configuration/slices.html
- Spring Framework — TestContext `@Sql`: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/executing-sql.html
- Spring Framework — Test-managed Transactions: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html