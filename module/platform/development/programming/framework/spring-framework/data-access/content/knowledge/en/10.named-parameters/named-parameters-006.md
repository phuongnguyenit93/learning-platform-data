# List Parameters for IN and Database Parameter Limits

## 1. Lesson Objectives

In Spring JDBC, `WHERE id IN (:ids)` is very convenient when filtering by a **variable-length list of IDs**. However, `:ids` is not a magic single parameter that every DBMS natively understands as a whole set of values: `NamedParameterJdbcTemplate` typically **expands the list into multiple JDBC bind placeholders**.

For example, three IDs produce effective SQL equivalent to `WHERE id IN (?, ?, ?)`, and Spring binds the three values in order. When a list grows to thousands or millions of values, the SQL grows too, potentially hitting limits on `IN` expression counts, statement bind parameters, SQL length, and execution cost.

This lesson helps you:

1. Understand `NamedParameterJdbcTemplate`'s `List`/`Iterable` expansion mechanism and how it differs from plain `JdbcTemplate`.
2. Pass lists into `IN (:ids)` safely using `MapSqlParameterSource` or `Map.of(...)`.
3. Handle **empty lists**, duplicate IDs, `null` elements, result ordering, list mutation during queries, and `NOT IN` with `NULL`.
4. Distinguish the **expression limit of a single IN list** from the **bind parameter limit of an entire SQL statement**, accounting for other conditions and repeated uses of the same list.
5. Choose strategies—**request caps, deduplication, chunking into multiple SQL statements, ID batching**—and know when to switch to **temporary tables, staging tables, SQL arrays/`ANY`, table-valued parameters, or joining against data already in the DB**.
6. Run a Java 17+ example with Spring Boot, H2, `NamedParameterJdbcTemplate`, migration/seed SQL, and edge-case tests.

**Core message:** named parameters help manage safe binding; **they do not eliminate database limits**. You must design input bounds, query splitting, and result semantics right in the repository contract.

## 2. Why Can't One JDBC Placeholder Represent Multiple Elements Automatically?

In plain JDBC, a `?` in a `PreparedStatement` represents **one parameter slot** in SQL syntax:

```sql
SELECT id, sku FROM products WHERE id = ?;
```

If you need three IDs with `IN` syntax, you normally need three bind slots:

```sql
SELECT id, sku FROM products WHERE id IN (?, ?, ?);
```

You cannot generally write `IN (?)` and call `statement.setObject(1, List.of(1L, 2L, 3L))` expecting the database to flatten a Java `List` into three values. The driver may reject `List`, or have a separate array mechanism—yet an **SQL array** is a different data type and comparison operator than `IN (?, ?, ?)`.

Spring's `NamedParameterJdbcTemplate` provides an expansion layer:

```sql
SELECT id, sku FROM products WHERE id IN (:ids);
```

Your code passes `ids = List.of(1L, 2L, 3L)`. Spring inspects the list, builds an SQL string with the right number of placeholders, and binds each value. Developers do not have to manually concatenate three `?` markers or ID values into SQL.

### 2.1. Illustrating Expansion

Application-authored SQL:

```sql
SELECT id, sku
FROM products
WHERE id IN (:ids)
  AND active = :active;
```

Application parameters:

```text
ids    = [3, 1, 4]
active = true
```

Expanded SQL shape (illustrative, not an execution log):

```sql
SELECT id, sku
FROM products
WHERE id IN (?, ?, ?)
  AND active = ?;
```

The total number of bind slots is **4**, not 2: three slots for `ids` and one for `active`. If `ids` has 500 elements, the corresponding query has **501 bind positions**.

This matters for pool statement caches, SQL size, parse time, and engine limits. The `:ids` syntax belongs to Spring's layer; databases generally do not accept `:ids` verbatim over JDBC.

### 2.2. How NamedParameterJdbcTemplate Differs from JdbcTemplate

| Query Approach | Input `List` | Primary Behavior |
| --- | --- | --- |
| `NamedParameterJdbcTemplate` with `IN (:ids)` | `List<Long>` | Spring generates `?` markers matching element count |
| `JdbcTemplate` with `IN (?, ?, ?)` | Three separate values | SQL author explicitly supplied enough placeholders |
| `JdbcTemplate` with `IN (?)` and one `List<Long>` | One Java List at one slot | **Not** automatically expanded into three IN bind values |
| PostgreSQL `= ANY (?)` with JDBC `Array` | One SQL array | Database-specific mechanism; **not** Spring list expansion |
| SQL Server table-valued parameter (TVP) | One table-typed parameter | SQL Server/driver-specific mechanism and schema type |

Do not confuse a `List` expanded into **multiple parameters** with an **SQL array parameter**. The two approaches have different limits, optimizer plans, and DB compatibility.

## 3. Basic Syntax with NamedParameterJdbcTemplate

### 3.1. Using Map.of for Simple Queries

```java
import java.util.List;
import java.util.Map;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

// namedJdbc is an injected NamedParameterJdbcTemplate bean.
List<Long> ids = List.of(1L, 3L, 4L);

List<String> skus = namedJdbc.query(
        """
        SELECT sku
        FROM products
        WHERE id IN (:ids)
        ORDER BY id
        """,
        Map.of("ids", ids),
        (rs, rowNum) -> rs.getString("sku")
);
```

This is a Java fragment inside a method with `namedJdbc` supplied by Spring; running it requires the `products` table from section 7. `ORDER BY id` establishes deterministic DB ordering by ID; it does **not** preserve the caller-supplied order of `ids`.

`List.of(...)` is an immutable list that forbids null elements. Avoid passing an `ArrayList` that another thread might mutate while the statement is being prepared/bound; prefer copying inputs into a dedicated collection before querying, along with validation.

### 3.2. Using MapSqlParameterSource for Multiple Parameters

```java
import java.util.List;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;

var params = new MapSqlParameterSource()
        .addValue("ids", List.of(1L, 3L))
        .addValue("active", true);

List<String> skus = namedJdbc.query(
        """
        SELECT sku
        FROM products
        WHERE id IN (:ids)
          AND active = :active
        ORDER BY id
        """,
        params,
        (rs, rowNum) -> rs.getString("sku")
);
```

`MapSqlParameterSource` works well when you want readable parameter setup, explicit `java.sql.Types` registration (especially for `null`), and future extensibility. The IDs in `ids` are bound in element order; `active` is bound separately.

**Note:** parameter names are fixed in code (`ids`, `active`), while caller-supplied values must be bound, never concatenated directly into the SQL string.

### 3.3. SQL Injection: Bind Values, Not Syntax

Wrong:

```java
// Wrong: concatenating arbitrary values into SQL.
String sql = "SELECT * FROM products WHERE sku IN ("
        + rawUserInput + ")";
```

Right:

```java
var params = new MapSqlParameterSource(
        "skus",
        List.of("BOOK", "PEN")
);

namedJdbc.query(
        "SELECT id, sku FROM products WHERE sku IN (:skus)",
        params,
        (rs, rowNum) -> rs.getString("sku")
);
```

Spring expands the list into placeholders and binds **data**, never interpreting SKUs as SQL keywords. However, if a caller selects column/table names or an `ORDER BY` expression, that is **SQL syntax** and cannot be made safe with a bind placeholder; use a fixed source-code whitelist.

## 4. Edge Cases to Handle Before Calling the DB

### 4.1. Empty List: `IN ()` Is Not Portable

If `ids = []`, some DBMSs raise an error on `WHERE id IN ()`. Spring documentation also does not promise identical semantics across every driver/dialect when passing an empty list to `IN (:ids)`. **Do not rely on Spring generating valid SQL for an empty list.**

For a query fetching products whose IDs belong to a list, standard semantics is **no IDs → empty result**:

```java
public List<Product> findByIds(List<Long> ids) {
    if (ids.isEmpty()) {
        return List.of(); // no need to touch the database
    }
    // Proceed to query IN (:ids) with a non-empty list.
}
```

This is an illustrative fragment; `Product` is an application-defined type. When accepting an external `Collection`, check `ids != null` before `isEmpty()` or reject null with a clear message.

If business logic intends "no filter selected" ⇒ **return all records**, do not attach that semantics merely to an empty list. Define two distinct states, such as `filterAbsent` (no condition applied) vs. `ids=[]` (filter matching nothing). Conflating the two can leak data or return huge datasets.

### 4.2. `NOT IN` with an Empty List

`NOT IN (:ids)` cannot simply substitute `ids=[]` into `IN ()` and expect "everything". It is especially dangerous to share one empty-branch shortcut for both `IN` and `NOT IN`.

Common set semantics:

- `x IN emptySet` is always false ⇒ no records.
- `x NOT IN emptySet` is always true ⇒ no exclusion filter needed, **while still preserving tenant/authorization filters**.

This is set-level semantics. Translating it into executable SQL must be made explicit in the application, not left to the dialect.

### 4.3. `NULL` Values Inside the List

Under SQL's three-valued logic, the expression:

```sql
SELECT id
FROM products
WHERE id IN (1, NULL);
```

does not mean `id = 1 OR id IS NULL`. If `id` is NULL, comparing against NULL is not true; if `id` is not 1, the result can be UNKNOWN and filtered out by `WHERE`. Worse still:

```sql
SELECT id
FROM products
WHERE id NOT IN (1, NULL);
```

can return **zero rows** even when many IDs differ from 1, because the NULL element prevents the comparison from evaluating to TRUE as expected. Therefore, for lists of primary keys or NOT NULL foreign keys, **reject Java null elements** upfront. If you genuinely need to include NULL column values, add an explicit, properly parenthesized `OR column IS NULL` condition.

`MapSqlParameterSource` can register an explicit SQL type when binding a scalar null:

```java
params.addValue("deletedBefore", null, java.sql.Types.TIMESTAMP);
```

Never use a "NULL element inside an IN list" to represent a set containing SQL NULL.

### 4.4. Duplicate IDs

`IN (3, 1, 3)` has the same membership meaning as `IN (3, 1)` for normal IDs; the query will not automatically return two copies of row `id=3` just because the input contains ID 3 twice.

If the API should return objects **once per ID**, deduplicate with `LinkedHashSet` both to cut placeholder count and to preserve first-appearance order. If business logic requires preserving input duplicates or weights, that is a different requirement, and `IN` alone does not have "multiset" or "repeat rows by ID multiplicity" semantics.

### 4.5. Input Order Does Not Dictate SQL Order

Passing `ids = [3, 1]` does not force SQL to return `[3, 1]`. `WHERE id IN (:ids)` only checks membership; it makes no guarantee about `ResultSet` order. You can either:

- Let the DB return rows using a consistent `ORDER BY` (e.g., `ORDER BY created_at DESC, id DESC`); or
- Map results by ID and reconstruct a `List` in deduplicated input order if the API contract requires caller-specified order.

The runnable example in section 7 illustrates the second approach.

### 4.6. Results May Omit Missing or Filtered-Out IDs

If input contains `[1, 2, 999]` and ID 999 does not exist, the query returns at most two products. With `AND active = true`, inactive products are also omitted.

The repository should explicitly state one of two contracts:

- **Filter**: return records that actually exist and satisfy conditions; missing IDs are omitted.
- **Require all**: if any ID is missing, raise a business error, optionally listing missing IDs (if the caller is authorized to know), enforcing consistency appropriately.

Never assume "missing means database corruption" or synthesize dummy records to match input length.

## 5. Two Frequently Confused Limits

### 5.1. Expression Limit Inside a Single IN List

A DBMS may limit the **number of items/expressions in a single IN list**. For example, **Oracle Database 19c** documentation specifies a maximum of **1,000 expressions** in an `IN` `expression_list`. Exceeding it raises `ORA-01795`.

Yet this limit is **not invariant across Oracle versions**: **Oracle Database 26ai** documentation describes up to **65,535 expressions** in an `expression_list`. Thus, claiming "Oracle always only allows 1,000 values" is an overgeneralization. Verify the **exact version** you run and the `IN` structure (single-column vs. multi-column tuple).

Even when a database allows huge lists, that does not guarantee good performance: longer SQL consumes more parse/plan resources, hurts plan caching, and can trigger suboptimal execution plans.

### 5.2. Total Bind Parameter Limit for the Entire Statement

A separate limit applies to the **total number of bound parameters in the expanded statement**, including:

- Each element of the `:ids` list.
- Other scalars such as `:tenantId`, `:active`, `:startAt`, `:endAt`.
- Elements in **any** other lists such as `:statuses`, `:regions`.
- Each repeated occurrence of the same named parameter list if the query uses it more than once.

Example:

```sql
SELECT id, sku
FROM products
WHERE (id IN (:ids) OR backup_id IN (:ids))
  AND tenant_id = :tenantId
  AND active = :active;
```

With 400 IDs in `ids`, there are **2 × 400 + 2 = 802 bind positions**, not 402. Every occurrence of `:ids` still requires its own group of placeholders in the executed SQL. Never count just one list's length and conclude the statement stays under limits.

A query can stay within the **single IN list** limit yet still breach the **total bind parameters** limit when multiple conditions are combined.

### 5.3. Reference Limit Table (Must Be Verified per DBMS and Version)

| Platform | Reference Number | What Kind of Limit? | Notes |
| --- | --- | --- | --- |
| **Oracle Database 19c** | **1,000** | Expressions in an `IN expression_list` | Typical error `ORA-01795`; not a "total JDBC bind" limit |
| **Oracle Database 26ai** | **65,535** | Expressions in an `IN expression_list` per that version's docs | Do not apply the new limit to Oracle 19c/21c systems |
| **SQL Server** | **2,100** | Common parameter limit per protocol/procedure/statement | Must subtract other parameters; not an isolated 2,100-item IN limit |
| **PostgreSQL pgJDBC extended query protocol** | **65,535** | Bind parameters per statement in extended query protocol | Does not mean you should send 65k-item `IN` lists; driver/protocol and query shape matter |
| **SQLite before 3.32.0** | **999** default | Maximum host parameter index | Customizable at compile/config time |
| **SQLite 3.32.0+** | **32,766** default | Maximum host parameter index | Can be lowered via runtime/build settings |
| **H2 and other DBMSs** | Version/config dependent | Parameters, SQL length, optimizer, and memory | Never use H2 numbers as production limits |

**Verification sources:** Spring JDBC [Passing in Lists of Values for IN Clause](https://docs.spring.io/spring-framework/reference/data-access/jdbc/parameter-handling.html), [Oracle 19c IN Condition](https://docs.spring.io/en/database/oracle/oracle-database/19/sqlrf/IN-Condition.html), [Oracle 26ai IN Condition](https://docs.spring.io/en/database/oracle/oracle-database/26/sqlrf/IN-Condition.html), [Microsoft SQL Server capacity](https://learn.microsoft.com/en-us/sql/sql-server/maximum-capacity-specifications-for-sql-server), [pgJDBC](https://jdbc.postgresql.org/documentation/use/), and [SQLite limits](https://www.sqlite.org/limits.html).

Numbers in this table are **technical ceilings**, not recommended batch sizes. Spring notes that the JDBC standard does not guarantee portable support for more than 100 values in an `IN` list. If building code that runs across dialects, choose a policy **tested per DB/driver**, rather than extrapolating from the largest number found online.

### 5.4. Parameter Budget Formula

For each SQL statement, model the budget as:

```text
P = total bind positions from all expanded lists
    + scalar binds
    + other binds (tuples, bound LIMIT/OFFSET, ...)
```

If a list of length `N` is used `R` times alongside `S` scalars:

```text
P = R × N + S
```

For example, `:ids` appears twice with three scalars and a statement budget of 2,000: `N` must satisfy `2N + 3 ≤ 2000`, so `N ≤ 998` (integer floor). Yet if the DB also enforces a 1,000-item limit on a **single** `IN`, the effective limit is `min(998, 1000) = 998`.

With a single `IN (:ids)`, one scalar `:active`, and an assumed 2,100 bind-position limit, a batch could reach `2,099` bind positions; however, on Oracle 19c with a 1,000-item `IN` limit, the batch still cannot exceed 1,000. In production, add a **safety margin** and calibrate against real workloads.

General formula for a list repeated `R ≥ 1` times:

```text
batchSize <= min(
    perInExpressionLimit,
    floor((statementParameterLimit - fixedParameters) / R),
    operationalBatchPolicy
)
```

If `statementParameterLimit - fixedParameters ≤ 0` or the result is less than 1, the current query shape cannot run: change the SQL structure or switch strategy (temp table, array, TVP, etc.). Count a tuple `(a,b)` as **two bind values per tuple**, and also check dialect-specific tuple-count limits if applicable.

## 6. When Lists Grow Large: Strategies and Trade-offs

### 6.1. Simple Approach: Cap IDs in the Request

If a use case should only fetch tens or hundreds of records, enforce an input limit and return a validation error when exceeded, rather than silently building massive SQL. Also consider:

- Deduplicate IDs before measuring effective query size.
- Enforce total request body caps and max accepted IDs to prevent resource exhaustion.
- Enforce authorization/tenant checks for **every ID**, not assuming inclusion in the list grants read access.
- Cap maximum returned rows/bytes, not just bind parameter counts.

This is a **business/API limit**, distinct from database technical limits. An engine might support 65k placeholders while the API caps requests at 500 IDs to protect p99 latency.

### 6.2. Splitting into Multiple Statements (Chunking)

When a moderately large list must be read, split IDs into small-enough batches and run multiple independent SQL statements:

```text
ids = [1..1200]
maxPerStatement = 500

statement 1: id IN (:ids) with 500 IDs (+ scalars)
statement 2: id IN (:ids) with 500 IDs (+ scalars)
statement 3: id IN (:ids) with 200 IDs (+ scalars)
```

These are **three SQL statements**, each staying within 500 `IN` elements. With one additional `active` scalar, total bind positions are 501, 501, and 201 respectively.

Pros: easy with `NamedParameterJdbcTemplate`, needs no temporary-table privileges or DB extensions, and results are straightforward to manage. Cons:

- Multiple network round trips and parse/bind cycles; latency may exceed a single query.
- Separate batches may observe different data states under concurrent writes; if snapshot consistency is required, use an appropriate transaction/isolation level.
- Results must be merged/deduplicated and sorted according to the caller contract if needed; never assume DB returns match input order.
- For `UPDATE/DELETE`, multiple separate batches risk **partial success** if a later batch fails unless wrapped in a transaction or proper compensation mechanism.

**Do not** confuse chunking with splitting lists inside a single SQL statement:

```sql
-- Two IN lists only work around the per-list expression limit.
-- Total binds still equal the sum of all ? markers in one SQL.
WHERE id IN (:idsPart1) OR id IN (:idsPart2)
```

If the bottleneck is the **total bind parameter limit per statement**, combining with `OR` in the same statement solves **nothing**. True chunking must execute **multiple statements** (or switch data structures).

### 6.3. Querying via a Temporary Table or Staging Table

With tens of thousands of IDs and complex joins, a more effective approach is usually:

1. Create or provision a staging/temp table with an ID column and optional `request_key`.
2. Load IDs via `batchUpdate`/bulk-load with proper constraints/deduplication.
3. Query with `JOIN staging_ids ON staging_ids.id = products.id`.
4. Clean up data and resources per transaction/session lifecycle.

Conceptual SQL example (temp-table creation syntax and lifecycle depend on DBMS):

```sql
SELECT p.id, p.sku
FROM products p
JOIN staging_ids s ON s.id = p.id
WHERE s.request_key = :requestKey
  AND p.active = :active;
```

The advantage is handling huge ID sets without building `IN` clauses with thousands of `?` markers. The cost is managing staging-table lifecycle, ID-loading transactions, indexes, permissions, failure cleanup, and concurrency isolation. With connection pools, **session-scoped temp tables** do not magically transfer across pooled connections: loading and querying must share the same connection/transaction per DBMS rules. Prevent request A's leftover rows from leaking to request B on a reused connection.

If IDs **already reside in another DB table**, prefer `JOIN` or `EXISTS` directly instead of loading IDs into Java and sending them back in a giant list:

```sql
SELECT p.id, p.sku
FROM products p
WHERE EXISTS (
    SELECT 1
    FROM permitted_products ap
    WHERE ap.product_id = p.id
      AND ap.user_id = :userId
);
```

`permitted_products` is just an illustrative table holding access rights. This also lets the database optimize joins and indexes.

### 6.4. PostgreSQL: SQL Array and ANY Instead of Expanded IN

PostgreSQL supports comparing a scalar against an SQL array:

```sql
SELECT id, sku
FROM products
WHERE id = ANY (?);
```

Binding **one JDBC `Array` of type `bigint[]`** to `?` sends the whole ID set through **one bind position** (not expanded by `NamedParameterJdbcTemplate` into N slots). However, this is **PostgreSQL-specific** and requires driver support for `java.sql.Array`, plus attention to lifetime, timeouts, and payload size.

Example fragment **for PostgreSQL only—not for the H2 app in section 7**:

```java
List<Product> products = jdbcTemplate.execute(
        (org.springframework.jdbc.core.ConnectionCallback<List<Product>>)
        connection -> {
            java.sql.Array sqlArray = connection.createArrayOf(
                    "int8",
                    ids.toArray(Long[]::new)
            );
            try {
                try (var statement = connection.prepareStatement(
                        """
                        SELECT id, sku, active
                        FROM products
                        WHERE id = ANY (?)
                          AND active = ?
                        """
                )) {
                    statement.setArray(1, sqlArray);
                    statement.setBoolean(2, true);

                    try (var rs = statement.executeQuery()) {
                        List<Product> result = new java.util.ArrayList<>();
                        while (rs.next()) {
                            result.add(new Product(
                                    rs.getLong("id"),
                                    rs.getString("sku"),
                                    rs.getBoolean("active")
                            ));
                        }
                        return result;
                    }
                }
            } finally {
                sqlArray.free();
            }
        }
);
```

`ids` is a validated `List<Long>`, `jdbcTemplate` is a `JdbcTemplate` bean, and `Product` is the record from section 7. `JdbcTemplate`'s callback keeps the connection scoped to the callback and translates `SQLException`; `PreparedStatement` and `ResultSet` are closed with try-with-resources, and `sqlArray.free()` runs afterward. Never use `IN (?)` with an `Array` assuming identical semantics; PostgreSQL uses `= ANY (?)`.

A massive SQL array still incurs creation/serialization/parsing, memory, and query-plan costs; a single bind position **does not mean** unlimited payload size. Depending on workload, `UNNEST(...)` + join or an indexed temp table with statistics may perform better.

### 6.5. SQL Server: Table-Valued Parameters

SQL Server supports **table-valued parameters (TVPs)** for passing a schema-typed set of rows to a stored procedure or statement via the corresponding driver. TVPs are often sensible when a request sends thousands of keys or multi-column records. A `List<Long>` is **not** automatically treated as a TVP by `NamedParameterJdbcTemplate`; you must define an SQL Server table type and use the Microsoft JDBC driver API or a compatible access layer.

Per-statement total parameter considerations still apply, yet a TVP passes as a structured table-typed parameter rather than expanding into thousands of scalar placeholders. Measure execution plans, cardinality estimation, TVP schema, indexing strategy, and permissions on user-defined table types.

### 6.6. Lists of Multi-Column Tuples

Spring supports `List<Object[]>` to expand tuple conditions when supported by the DBMS:

```sql
SELECT id, tenant_id
FROM products
WHERE (tenant_id, id) IN (:pairs);
```

Data setup fragment:

```java
List<Object[]> pairs = new ArrayList<>();
pairs.add(new Object[] {7L, 100L});
pairs.add(new Object[] {7L, 101L});

var params = new MapSqlParameterSource("pairs", pairs);
```

Equivalent expanded SQL shape:

```sql
WHERE (tenant_id, id) IN ((?, ?), (?, ?));
```

For 400 two-column pairs, you may need **800 bind values**, not 400. Also, row-value comparison syntax and expression-list limits vary across DBMSs. When pair counts grow very large, a two-column staging table joined on the composite key usually offers cleaner semantics, indexing, and performance.

**Security note:** if tenant ID comes from session/authorization context, never let clients submit `(tenantId, id)` pairs as proof of permission. Tenant context must be resolved server-side and enforced in the query.

## 7. Runnable Example: Spring Boot + Java 17 + H2

The following application demonstrates the full flow:

- Input may contain duplicate IDs, non-existent IDs, or inactive IDs.
- Returns `List<Product>` in **first-appearance unique ID order** from the request.
- Skips querying when input is empty.
- Rejects `null` or non-positive IDs.
- Deduplicates to reduce placeholders, capping requests at 5,000 **distinct** IDs.
- Chunks each SQL query to at most 500 IDs; each query also has one `:active` scalar, yielding at most 501 bind positions for this query.
- Avoids forcing input order via SQL `ORDER BY`; indexes results by ID and reassembles in Java.

This example teaches **semantics and limit management**. The number 500 is not a universal recommendation for every DB; real applications must pick based on engine/driver limits, remaining scalars, and benchmarks.

### 7.1. Project Structure

```text
named-in-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/inlist/
    │   │   ├── Product.java
    │   │   ├── ProductJdbcRepository.java
    │   │   └── NamedInApplication.java
    │   └── resources/
    │       ├── application.yml
    │       ├── schema.sql
    │       └── data.sql
    └── test/java/demo/inlist/
        └── ProductJdbcRepositoryTest.java
```

### 7.2. Gradle Build

`settings.gradle`:

```groovy
rootProject.name = 'named-in-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

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
```

Spring Boot 3.3.x provides `JdbcTemplate` and `NamedParameterJdbcTemplate` when a datasource is configured. H2 is purely an educational database for reproducing the example without installing a server; real limit checks require integration tests on a production-like DBMS.

### 7.3. SQL Schema and Fixed Seed Data

`src/main/resources/schema.sql`:

```sql
CREATE TABLE products (
    id BIGINT PRIMARY KEY,
    sku VARCHAR(40) NOT NULL UNIQUE,
    active BOOLEAN NOT NULL
);
```

`src/main/resources/data.sql`:

```sql
INSERT INTO products (id, sku, active)
VALUES
    (1, 'BOOK', TRUE),
    (2, 'PEN', FALSE),
    (3, 'NOTE', TRUE),
    (4, 'BAG', TRUE);
```

With this schema, `id` is PK, so querying by `id IN (...)` never returns the same product multiple times. If the repository JOINs a one-to-many child table, result uniqueness can change and require dedicated mapping/deduplication; never blindly reuse this assumption.

`src/main/resources/application.yml`:

```yaml
spring:
  datasource:
    url: jdbc:h2:mem:named_in_demo;DB_CLOSE_DELAY=-1
    driver-class-name: org.h2.Driver
    username: sa
    password:
  sql:
    init:
      mode: always
```

Spring initializes the H2 datasource and runs `schema.sql` and `data.sql`. Data is ephemeral in the JVM, needing no production passwords.

### 7.4. Return Type

`src/main/java/demo/inlist/Product.java`:

```java
package demo.inlist;

public record Product(long id, String sku, boolean active) {}
```

A Java 17 record represents one row's result, avoiding exposing `ResultSet` or `Map<String,Object>` directly to upper layers.

### 7.5. Repository with Deduplication, Input Cap, Chunking, and Order Restoration

`src/main/java/demo/inlist/ProductJdbcRepository.java`:

```java
package demo.inlist;

import java.util.ArrayList;
import java.util.Collection;
import java.util.HashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;

import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class ProductJdbcRepository {
    // Policy for this lesson's query: 500 IDs + 1 scalar (:active).
    private static final int MAX_IDS_PER_QUERY = 500;
    private static final int MAX_UNIQUE_IDS_PER_REQUEST = 5_000;

    private static final String SQL = """
            SELECT id, sku, active
            FROM products
            WHERE id IN (:ids)
              AND active = :active
            """;

    private static final RowMapper<Product> PRODUCT_ROW =
            (rs, rowNum) -> new Product(
                    rs.getLong("id"),
                    rs.getString("sku"),
                    rs.getBoolean("active")
            );

    private final NamedParameterJdbcTemplate jdbc;

    public ProductJdbcRepository(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<Product> findActiveInRequestedOrder(
            Collection<Long> inputIds
    ) {
        Objects.requireNonNull(inputIds, "inputIds");

        // Deduplicate in order of first appearance while validating caller IDs.
        LinkedHashSet<Long> unique = new LinkedHashSet<>();
        for (Long id : inputIds) {
            if (id == null || id <= 0) {
                throw new IllegalArgumentException(
                        "Every product ID must be positive and non-null"
                );
            }

            unique.add(id);
            if (unique.size() > MAX_UNIQUE_IDS_PER_REQUEST) {
                throw new IllegalArgumentException(
                        "Too many distinct product IDs"
                );
            }
        }

        // Must short-circuit before IN (:ids) when list is empty.
        if (unique.isEmpty()) {
            return List.of();
        }

        List<Long> orderedIds = new ArrayList<>(unique);
        Map<Long, Product> foundById = new HashMap<>();

        // Multiple SQL statements, not multiple INs in 1 SQL.
        for (int start = 0;
             start < orderedIds.size();
             start += MAX_IDS_PER_QUERY) {

            int end = Math.min(
                    start + MAX_IDS_PER_QUERY,
                    orderedIds.size()
            );
            List<Long> batch = orderedIds.subList(start, end);

            var parameters = new MapSqlParameterSource()
                    .addValue("ids", batch)
                    .addValue("active", true);

            List<Product> rows = jdbc.query(
                    SQL,
                    parameters,
                    PRODUCT_ROW
            );

            for (Product product : rows) {
                foundById.put(product.id(), product);
            }
        }

        // SQL IN does not preserve input order.
        return orderedIds.stream()
                .map(foundById::get)
                .filter(Objects::nonNull)
                .toList();
    }
}
```

**Review the seven design choices carefully:**

1. **Validation:** `inputIds` must be non-null; each ID must be non-null and positive. Null elements are rejected before `IN`, avoiding three-valued logic issues and ambiguous mapping errors.
2. **Stable deduplication:** `LinkedHashSet` removes duplicate IDs while preserving first-seen order. `[3, 1, 3, 999, 2]` becomes `[3, 1, 999, 2]`.
3. **Max request size:** 5,000 distinct IDs is an illustrative policy, not a hard limit of H2 or any DBMS. If you also need to cap **total raw input elements including duplicates**, add an upfront size check before the loop to block huge requests with millions of duplicates.
4. **Empty input:** returns an empty list without issuing `IN ()` SQL. This implements membership filtering, not an endpoint where "absent filter returns all".
5. **Chunking:** each `jdbc.query(...)` call sends at most 500 IDs plus one `active` scalar—at most 501 JDBC bind values per statement for this SQL. No single query ever carries all 5,000 IDs.
6. **Mapping:** `RowMapper<Product>` maps each row to an object. Since `id` is `PRIMARY KEY` and there is no multiplying JOIN, `Map.put(product.id(), product)` cannot overwrite another valid record; if the schema or query changes, re-verify that assumption.
7. **Ordering:** DB results may differ from requested ID order. `orderedIds.stream()` rebuilds results in input order, dropping missing or inactive IDs. The returned `List` is unmodifiable via Java 17 `Stream.toList()`.

**Concurrency note:** when running multiple chunked SELECTs, the database can change between chunks. If the use case requires a single snapshot, use a read-only transaction with DBMS-appropriate isolation and measure snapshot retention cost; otherwise, document that results span multiple queries and may reflect concurrent updates. Never hold a transaction open across slow HTTP calls just to stitch results together.

### 7.6. Console Demo Application

`src/main/java/demo/inlist/NamedInApplication.java`:

```java
package demo.inlist;

import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class NamedInApplication {
    public static void main(String[] args) {
        SpringApplication.run(NamedInApplication.class, args);
    }

    @Bean
    CommandLineRunner runExample(ProductJdbcRepository products) {
        return args -> {
            var requested = List.of(3L, 1L, 3L, 999L, 2L);
            var selected =
                    products.findActiveInRequestedOrder(requested);

            System.out.println(
                    "ids=" + selected.stream().map(Product::id).toList()
            );
            System.out.println(
                    "skus=" + selected.stream().map(Product::sku).toList()
            );
            System.out.println(
                    "empty="
                    + products.findActiveInRequestedOrder(List.of()).size()
            );
        };
    }
}
```

Run in a Gradle project with a wrapper:

```bash
./gradlew bootRun
```

On Windows PowerShell use `.\gradlew.bat bootRun`. If there is no wrapper yet, generate one with a preinstalled Gradle or run `gradle bootRun`. Java source and directory paths must match the package and filenames above.

After Spring Boot startup logs, the exact three `System.out.println` lines from the demo are:

```text
ids=[3, 1]
skus=[NOTE, BOOK]
empty=0
```

Explanation: 3 and 1 exist and are active; 3 was repeated in the request but returned once; ID 999 does not exist; 2 exists but is inactive; empty list runs no query.

## 8. Testing with JUnit 5

File `src/test/java/demo/inlist/ProductJdbcRepositoryTest.java`:

```java
package demo.inlist;

import java.util.Arrays;
import java.util.List;
import java.util.stream.LongStream;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class ProductJdbcRepositoryTest {

    @Autowired
    ProductJdbcRepository repository;

    @Test
    void deduplicatesAndPreservesRequestedOrder() {
        List<Product> products =
                repository.findActiveInRequestedOrder(
                        List.of(3L, 1L, 3L, 4L, 1L)
                );
        assertEquals(
                List.of(3L, 1L, 4L),
                products.stream().map(Product::id).toList()
        );
    }

    @Test
    void dropsMissingAndInactiveRows() {
        List<Product> products =
                repository.findActiveInRequestedOrder(
                        List.of(999L, 2L, 1L)
                );
        assertEquals(1, products.size());
        assertEquals("BOOK", products.get(0).sku());
    }

    @Test
    void emptyListReturnsEmptyResult() {
        assertTrue(
                repository.findActiveInRequestedOrder(List.of()).isEmpty()
        );
    }

    @Test
    void rejectsNullOrNonPositiveElements() {
        assertThrows(
                IllegalArgumentException.class,
                () -> repository.findActiveInRequestedOrder(
                        Arrays.asList(1L, null)
                )
        );
        assertThrows(
                IllegalArgumentException.class,
                () -> repository.findActiveInRequestedOrder(
                        List.of(0L)
                )
        );
    }

    @Test
    void readsAcrossThreeChunks() {
        List<Long> ids = LongStream.rangeClosed(1, 1_200)
                .boxed()
                .toList();

        List<Product> products =
                repository.findActiveInRequestedOrder(ids);

        assertEquals(
                List.of(1L, 3L, 4L),
                products.stream().map(Product::id).toList()
        );
    }

    @Test
    void capsDistinctRequestIds() {
        List<Long> ids = LongStream.rangeClosed(1, 5_001)
                .boxed()
                .toList();

        assertThrows(
                IllegalArgumentException.class,
                () -> repository.findActiveInRequestedOrder(ids)
        );
    }
}
```

Run:

```bash
./gradlew test
```

Six tests verify contract behavior. `readsAcrossThreeChunks` sends 1,200 IDs across **three statements** of 500 + 500 + 200 `IN` elements (plus one `active` parameter per statement). Having only four rows in the DB does not affect chunk splitting; the test confirms combined results keep IDs 1, 3, and 4.

**Testing limitation:** H2 does not prove real Oracle 19c or SQL Server limits. To test vendor constraints, run integration tests with the same query and boundary sizes on the **exact DBMS/driver version** used in production (e.g., via Testcontainers), measuring CPU, statement preparation time, round trips, and returned row counts.

## 9. Counting Bind Parameters Accurately with Multiple Conditions

Suppose a repository builds:

```sql
SELECT p.id, p.sku
FROM products p
WHERE p.tenant_id = :tenantId
  AND p.status IN (:statuses)
  AND p.id IN (:ids)
  AND p.created_at >= :fromDate
  AND p.created_at < :toDate;
```

If `ids = 600`, `statuses = 4`, and there are three scalars `tenantId`, `fromDate`, `toDate`, the statement uses `600 + 4 + 3 = 607` bind positions. If the SQL also adds `p.parent_id IN (:ids)`, it becomes `1,207` positions.

Count by **expanded placeholder count**, not merely by **distinct named parameter** count. If a vendor limit is 999 in a given setup, 600 IDs in `ids` still breaches the limit when used twice.

A budget calculation helper can be verified in plain Java:

```java
public final class BindBudget {
    private BindBudget() {}

    public static int maxListItems(
            int perInExpressionLimit,
            int statementParamLimit,
            int fixedParamCount,
            int occurrences,
            int operationalLimit
    ) {
        if (perInExpressionLimit < 1
                || statementParamLimit < 1
                || fixedParamCount < 0
                || occurrences < 1
                || operationalLimit < 1) {
            throw new IllegalArgumentException("Invalid limits");
        }
        int free = statementParamLimit - fixedParamCount;
        int byTotal = free / occurrences;
        int maximum = Math.min(
                Math.min(perInExpressionLimit, byTotal),
                operationalLimit
        );
        if (maximum < 1) {
            throw new IllegalArgumentException("No bind budget remains");
        }
        return maximum;
    }

    public static void main(String[] args) {
        System.out.println(maxListItems(1000, 2000, 3, 2, 500));
        System.out.println(maxListItems(1000, 2100, 1, 1, 500));
    }
}
```

This is a standalone Java class (`BindBudget.java`), runnable on Java 17:

```bash
javac BindBudget.java
java BindBudget
```

Exact stdout:

```text
500
500
```

First example: remaining budget is `2000 - 3 = 1997`, list appears twice so `floor(1997/2) = 998`, applying `perInExpressionLimit=1000` and `operationalLimit=500` gives 500. Second example: `(2100 - 1)/1 = 2099`, bounded by `min(1000, 500)` gives 500.

**Helper limitation:** it assumes each list item consumes **one bind position per occurrence**; for `List<Object[]>` with 2- or 3-column tuples, multiply by the bind positions per tuple. When multiple distinct lists exist, subtract the binds of the other lists and scalars separately. This is a design formula, not an API that queries the database for its limits.

## 10. Common Production Risks

### 10.1. Exceeding Database Limits: Where Do Errors Surface?

Depending on DBMS/driver, errors may happen during SQL preparation, parsing, binding, or execution. Spring JDBC usually translates `SQLException` into the `DataAccessException` hierarchy, though exact subclasses and messages depend on the translator and vendor.

Never catch all `DataAccessException` and return empty results: doing so disguises a severe technical failure as "no products found". When inputs can grow large, **validate/chunk upfront**, test against the production version, and map unexpected errors to safe responses while logging the root cause internally.

### 10.2. N+1 and Excessive Round Trips When Chunks Are Too Small

If a request has 5,000 IDs and chunk size is 10, you issue 500 SQL queries, potentially inflating latency. A chunk size of 500 issues 10 queries; still measure query time/plan, network overhead, and DB concurrency.

Increasing chunk size is not always faster: very long SQL can strain parsing and plan caches, especially when list lengths vary wildly per request. Consider bucketing list sizes per a tested policy or switching to staging tables/arrays for large sets.

Do not run unbounded parallel chunks: each concurrent query consumes a pool connection and adds DB load. Respect concurrency limits and pool capacity when using parallelism.

### 10.3. Prepared-Statement Cache and SQL Shapes

`WHERE id IN (?, ?)` and `WHERE id IN (?, ?, ?)` are two distinct SQL texts. Too many shape variants reduce driver/server statement-cache effectiveness; reducing shape counts or using array/table approaches can help, though you must measure. Never "optimize" by inlining raw IDs as literals, which breaks binding and opens injection risks.

### 10.4. Transactions and Consistency Across Multiple Chunks

Returning a consistent point-in-time snapshot may not hold if chunks run in separate transactions or under default isolation allowing non-repeatable reads. For reporting/financial workflows requiring consistency, define semantics clearly:

- If "near-current" results suffice, multiple independent SELECTs may be fine.
- If consistency is mandatory, use a transaction with appropriate isolation/snapshot settings, or load IDs into staging and run one join; verify DB lock/snapshot retention behavior.
- For chunked `UPDATE/DELETE` requiring all-or-nothing, wrap at the **service/use-case boundary**; for very large jobs, prefer idempotent/checkpointed jobs over one giant transaction.

Never hold a transaction open across slow HTTP calls between batches; that wastes connections/locks and does not achieve atomicity with remote services.

### 10.5. Authorization and Multi-Tenant Isolation

If a frontend submits `ids=[...]`, the server cannot assume the user is permitted to view all listed records. Queries still require `tenant_id = :tenantId` or user/group access predicates, with tenant ID resolved server-side.

Deduplication and chunking must preserve every such filter **in every statement**, never dropping filters on later batches. Total bind counts must include tenant/permission parameters. An ID missing from results could be non-existent, inactive, or unauthorized; error responses must respect policies against leaking record existence.

### 10.6. Memory, Caching, and Request Body Overhead

Even if the DB accepts 65,535 parameters, an HTTP request carrying tens of thousands of IDs incurs JSON parsing, validation, memory allocation, logging, and caching costs. Enforce request-size limits, rate limits, and max distinct IDs; avoid logging full ID lists if sensitive. Log ID counts, request ID, duration, and batch-count metrics instead.

### 10.7. Query Plans for Long IN Lists

When `id` has a B-tree index or PRIMARY KEY, engines optimize small `IN` lists effectively; for very long lists with high match ratios, repeated index probes can lose to sequential scans or joins. Statistics, skew, selectivity, and optimizers vary across DBMSs. Inspect execution plans and real metrics rather than deciding based solely on placeholder counts.

In PostgreSQL, compare `EXPLAIN (ANALYZE, BUFFERS)` across `IN`, `= ANY(array)`, and temp-table joins in a test environment. Only run `EXPLAIN ANALYZE` on write statements if you understand it **actually executes** the statement; use a rolled-back transaction or test DB.

## 11. Distinguishing batchUpdate from IN Chunking

These are two distinct problems:

**A. One SQL statement reading/affecting multiple IDs:**

```sql
SELECT id, sku FROM products WHERE id IN (:ids);
```

Here `ids` is **one list expanded into multiple bind positions within a single statement**. Statement and IN-list limits apply directly.

**B. Running the same SQL statement many times with different bind sets:**

```sql
UPDATE products SET active = :active WHERE id = :id;
```

`NamedParameterJdbcTemplate.batchUpdate(...)` takes **an array of parameter sources** for multiple executions of the statement. Each execution carries binds for **one record**; it does not turn `:id` into an `IN` list. This is JDBC batch execution, optimizing write round trips.

Using `batchUpdate` does **not** fix a statement whose `IN (:ids)` holds 20,000 items; if each item's SQL in the batch still expands 20,000 values, per-statement limits still apply.

For updating many IDs, you can choose per-ID `batchUpdate`, chunked `UPDATE ... WHERE id IN (...)`, or loading staging + `UPDATE ... FROM`/`MERGE` per dialect. Choose based on atomicity, speed, and DB locking.

## 12. Strategy Decision Table

| Scale / Need | Preferred Option to Evaluate | Why |
| --- | --- | --- |
| 0 IDs, membership-filter semantics | Return empty before querying | Avoids `IN ()` |
| A few to a few hundred IDs | `NamedParameterJdbcTemplate` + `IN (:ids)` | Simple, safe binding |
| Moderately many IDs under request cap | Deduplicate + chunk into multiple statements | Avoids hitting per-statement limits |
| Tens of thousands of IDs, repeated queries or complex joins | Staging/temp table + join | Avoids huge placeholder counts |
| PostgreSQL, large list, membership read | SQL array + `= ANY (?)` or `UNNEST` | Single array bind, still benchmark |
| SQL Server, large lists/datasets | TVP or temp table | Table-valued structure avoids thousands of scalar binds |
| IDs already exist in another DB table | `JOIN` / `EXISTS` | Avoids round-tripping data through app |
| Many composite key pairs | Small tuple list or two-column staging table | Each tuple consumes multiple binds; dialect limits apply |
| Output must match input ID order | Map by PK then reorder | `IN` does not promise order |
| Atomic updates across batches | Service-level transaction or staging-based update | Prevents partial success |

Some cases require **combining** approaches: request cap + deduplication + chunking + metrics, or staging + transaction + TTL cleanup. No single batch size is optimal for every engine.

## 13. Pre-Merge Review Checklist

- Can `ids` be empty? If so, are semantics and branching explicit?
- Are `null` elements rejected or handled per SQL three-valued logic, especially with `NOT IN`?
- Are duplicate IDs deduplicated in line with the output contract?
- Does the query preserve input order or use DB sorting instead of relying on `IN` order?
- Are all inputs bound as values rather than concatenated as SQL literals?
- Does the total bind position count include **all** lists, scalars, tuples, and repeated named parameters?
- Have limits been verified against the **exact DBMS version and driver** in use rather than numbers for another system?
- Is batch size smaller than the IN-list limit, total parameter limit, and operational threshold?
- Does chunking genuinely execute multiple statements rather than combining multiple `IN`s in one SQL and exceeding total bind budget?
- Are request caps, timeouts, rate limits, memory bounds, and logging policies in place for large lists?
- Are tenant/authorization filters present **in every batch**?
- For multi-statement reads/updates, are isolation, atomicity, and retry/idempotency defined?
- Have execution plans, p95/p99 latency, round trips, SQL parsing, and connection usage been measured as ID counts grow?
- Are there integration tests for 0/1/n IDs, duplicates, NULLs, missing IDs, inactive rows, batch boundaries, and the real DB version?

## 14. Self-Check Exercises

**Exercise 1 — Parameter expansion.** Given `ids = [10, 20, 30]`, `statuses = ["OPEN", "PAID"]`, and one `tenantId`, how many bind positions does `WHERE id IN (:ids) AND status IN (:statuses) AND tenant_id = :tenantId` have? Write the equivalent placeholder form.

**Exercise 2 — Total limit.** A system has a 2,000 total bind-position policy; a query uses `IN (:ids)` twice and four scalars. If the per-`IN` limit is 1,000, what is the theoretical maximum list size? What if the operational policy sets a maximum of 500?

**Exercise 3 — Empty handling.** API `POST /products/filter` receives `ids=[]`. Design two distinct contracts: (a) empty means no products; (b) omitted filter means fetch all. Show why `ids: []` must be distinguished from an omitted `ids` field.

**Exercise 4 — NULL.** Why might `WHERE sku NOT IN ('BOOK', NULL)` fail to return product `PEN`? Design validation rejecting nulls, and if NULL column values should be included, write an explicit `IS NULL` condition.

**Exercise 5 — Chunking.** A list of 1,200 IDs, chunk size 500, one `active` scalar per SQL. How many statements run, and how many bind positions are in each? If you instead wrote `id IN (:p1) OR id IN (:p2) OR id IN (:p3)` in **one** SQL statement, what is the total parameter count?

**Exercise 6 — Choosing a solution.** 50,000 IDs need to join two tables in PostgreSQL, and another 50,000 IDs must be sent to SQL Server. List pros and cons of chunking, array/ANY, staging tables, and TVPs (where supported), especially regarding round trips, optimizer behavior, transactions, cleanup, and drivers.

**Answer hints:** (1) `3+2+1=6` binds; (2) `floor((2000-4)/2)=998`, operational policy 500 ⇒ 500; (3) explicit empty ⇒ empty result, omitted filter returns all only if permitted by contract and still enforces authorization/pagination; (4) three-valued logic—reject null elements, add deliberate `OR sku IS NULL` when intended; (5) three statements with 501, 501, 201; combining in one SQL still yields 1,203 binds; (6) benchmark on the specific DBMS/driver instead of applying one number or pattern to every engine.

## 15. Conclusion

`NamedParameterJdbcTemplate` makes SQL readable and passes lists safely via `IN (:ids)`, yet under the hood it **expands lists into multiple placeholders**. Therefore:

- **Few IDs:** use a simple named list.
- **Zero IDs:** short-circuit according to defined semantics.
- **Many IDs:** cap requests, validate/deduplicate, calculate total bind budget, split into multiple statements, or use an appropriate database-native structure.
- **Very large sets:** prefer joins with tables/staging or benchmarked arrays/TVPs instead of generating SQL with massive placeholder counts.
- **Correct results:** remember `IN` guarantees neither ordering nor row duplication per input occurrence; enforce missing-row rules, tenant filters, isolation, and rollbacks per business contract.

Good design does more than avoid "too many parameters" errors. It keeps SQL binding safe, bounds resource usage, produces predictable results, and lets you evolve strategies cleanly as data scales.

## 16. References

- Spring Framework — [Passing in Lists of Values for IN Clause](https://docs.spring.io/spring-framework/reference/data-access/jdbc/parameter-handling.html).
- Spring Framework — [NamedParameterJdbcTemplate Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jdbc/core/namedparam/NamedParameterJdbcTemplate.html).
- Spring Framework — [MapSqlParameterSource Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jdbc/core/namedparam/MapSqlParameterSource.html).
- Oracle Database 19c — [IN Condition](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/IN-Condition.html), version-specific expression-list limit.
- Oracle Database 26ai — [IN Condition](https://docs.oracle.com/en/database/oracle/oracle-database/26/sqlrf/IN-Condition.html), updated version-specific limit.
- Microsoft SQL Server — [Maximum Capacity Specifications](https://learn.microsoft.com/en-us/sql/sql-server/maximum-capacity-specifications-for-sql-server); [Using table-valued parameters](https://learn.microsoft.com/en-us/sql/connect/jdbc/using-table-valued-parameters).
- pgJDBC — [Initializing the Driver / use documentation](https://jdbc.postgresql.org/documentation/use/), extended protocol bind limits.
- SQLite — [Limits in SQLite](https://www.sqlite.org/limits.html), host parameter number and configurable limits.
- PostgreSQL — [Array Functions and Operators](https://www.postgresql.org/docs/current/functions-array.html), [Array Comparisons](https://www.postgresql.org/docs/current/functions-comparisons.html).
