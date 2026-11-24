# IN with Value Sets and the Empty List Case

## 1. The Problem: ID Lists of Variable Size

In Spring Framework data-access, SQL queries frequently need to filter by **a set of values supplied by the application**: a list of customer IDs, selected product codes, valid statuses, granted permission codes, or a batch of orders to process.

Example:

```sql
SELECT id, name
FROM customer
WHERE id IN (1, 3, 5)
ORDER BY id;
```

However, at runtime, the application may receive `List<Long> ids` with 0, 1, 3, or hundreds of elements. Thus you cannot hardcode three elements in SQL. Three distinct problems must be solved:

1. **Turning element count into matching SQL parameters:** `IN (?, ?, ?)` for three values; never concatenate user data directly into SQL.
2. **Defining behavior when the list is empty:** `IN ()` is not reliable SQL syntax across DBMSs; SQL may fail or behave dialect-specifically.
3. **Preserving semantics and business safety:** `IN` and `NOT IN` behave differently with empty lists, `NULL`, and `UPDATE`/`DELETE` operations.

This lesson demonstrates with Java 17+, `JdbcTemplate`, `NamedParameterJdbcTemplate`, and common standard SQL. Each example only runs with the proper DB/schema/driver and Spring configuration; the standalone JDK 17 program in section 16 is noted separately.

**Initial takeaway:** `IN` with an empty list is not merely a syntax error to "patch so it runs"; first determine **what business result set is desired**, then choose a safe handling strategy.

## 2. Understanding SQL IN Semantics Before Writing Java

Common syntax:

```sql
WHERE id IN (1, 3, 5)
```

It can be understood roughly as:

```sql
WHERE id = 1 OR id = 3 OR id = 5
```

If `id` equals one of those values, the predicate is true. Conversely, `NOT IN (1, 3, 5)` corresponds to "not equal to any" in SQL logic:

```sql
WHERE id <> 1 AND id <> 3 AND id <> 5
```

However, SQL uses **three-valued logic**: TRUE, FALSE, and UNKNOWN (typically represented via `NULL`), unlike ordinary comparisons in Java. This matters especially for `NOT IN`.

Example with a non-null `id` column:

| ID | `id IN (1, 3)` | `id NOT IN (1, 3)` |
| ---: | --- | --- |
| 1 | TRUE | FALSE |
| 2 | FALSE | TRUE |
| 3 | TRUE | FALSE |
| 4 | FALSE | TRUE |

If the input list conceptually represents the empty set, the mathematically sound interpretation is:

- **`id IN []`:** no ID belongs to the empty set → **return no rows**.
- **`id NOT IN []`:** no ID is excluded → **do not apply the exclusion filter** (keep all other conditions).

Note that the symbols `IN []` and `NOT IN []` above are *explanatory notation*, **not executable SQL**. Nor should you assume every DB accepts `IN ()`. In application code, write dedicated handling branches or construct an SQL expression supported by the DB.

### Why Does `IN (?)` Not Accept a List as a Single Value?

A `?` in `PreparedStatement` is **one JDBC parameter slot**, not a default mechanism to automatically expand a `List` into multiple slots.

Misintended code:

```java
String sql = "SELECT id FROM customer WHERE id IN (?)";
jdbcTemplate.query(
    sql,
    (rs, row) -> rs.getLong("id"),
    "1,3,5"
);
```

The string `"1,3,5"` is **a single string value**, not three integers. Depending on the DB/driver, the query may match nothing, fail type conversion, or compare wrongly. Similarly, do not assume passing `List.of(1L, 3L, 5L)` into one `?` will make JDBC understand three elements.

The proper approach in plain JDBC is to **generate the exact number of question marks**, or use a Spring API with list parameter expansion.

## 3. Input Validation Rules Before Building SQL

Define the input contract right at the repository/service boundary:

| Input | Possible Interpretation | Recommended Behavior for INCLUDE Queries |
| --- | --- | --- |
| `null` for the whole list | Missing input or programming bug | Report input error; **do not silently treat as empty** unless API defines so |
| `[]` | Caller selected zero IDs | Return empty list without calling DB; or use FALSE predicate if SQL must run |
| `[3]` | One ID selected | `IN (?)` and one parameter |
| `[3, 1]` | Two IDs selected | `IN (?, ?)` and two parameters |
| `[3, 1, 3]` | ID 3 appears twice | Can deduplicate before binding; `IN` results do not duplicate rows |
| `[3, null]` | Contains `NULL` element, error-prone | For ID lists, **reject or strip null per explicit contract**, never pass unknowingly |

A safe helper for `Long` IDs typically does:

1. Check that the list is not `null`.
2. Check that no element is `null` (when business logic uses non-nullable ID keys).
3. Optionally remove duplicate IDs with `distinct()` to avoid extra placeholders.
4. Keep the normalized list scoped to the call; do not rely on the caller not mutating the passed list later.

Example:

```java
private static List<Long> checkedIds(List<Long> ids) {
    Objects.requireNonNull(ids, "ids");
    if (ids.stream().anyMatch(Objects::isNull)) {
        throw new IllegalArgumentException("ids cannot contain null");
    }
    return ids.stream().distinct().toList();
}
```

The snippet above requires importing `List` and `Objects`; in Java 17, `Stream.toList()` produces an unmodifiable list. Do not blindly apply `distinct()` if the application needs to preserve **occurrence counts** of each value for another operation; for `IN` set filters, duplicates are generally unnecessary.

## 4. Approach 1 — JdbcTemplate with Dynamic Placeholders

With `JdbcTemplate`, the number of `?` markers must match the number of bound values. One way to build the placeholder string **solely from list size**, never from user values:

```java
String marks = String.join(
    ", ",
    Collections.nCopies(ids.size(), "?")
);
```

| ID Count | `marks` | Resulting SQL |
| ---: | --- | --- |
| 1 | `?` | `WHERE id IN (?)` |
| 2 | `?, ?` | `WHERE id IN (?, ?)` |
| 3 | `?, ?, ?` | `WHERE id IN (?, ?, ?)` |
| 0 | empty string | **Never run `WHERE id IN ()`** |

Query method example (Spring integration code, requires `JdbcTemplate` and `Customer` type already declared):

```java
public List<Customer> findByIdsJdbc(List<Long> inputIds) {
    List<Long> ids = checkedIds(inputIds);
    if (ids.isEmpty()) {
        return List.of();
    }

    String marks = String.join(
        ", ", Collections.nCopies(ids.size(), "?")
    );
    String sql = """
        SELECT id, name
        FROM customer
        WHERE id IN (%s)
        ORDER BY id
        """.formatted(marks);

    return jdbcTemplate.query(
        sql,
        (rs, rowNum) -> new Customer(
            rs.getLong("id"), rs.getString("name")
        ),
        ids.toArray()
    );
}
```

Explanation:

- **The empty branch runs before** SQL construction, avoiding `IN ()`.
- Only `?`/commas are inserted into SQL structure, **never actual ID numbers**.
- `ids.toArray()` supplies `Object[]` for `query(String, RowMapper<T>, Object... args)`, so each value is bound individually.
- `RowMapper` maps each returned row to `Customer`.
- `ORDER BY id` makes query ordering deterministic; `IN` itself **does not preserve input ID list order**.
- With zero IDs, `List.of()` is returned without acquiring a connection; this differs from health-check queries and is intentional behavior.

**Use this snippet only inside a class with `jdbcTemplate` and an appropriate `Customer` record**; section 6 provides a complete repository class. Never call `String.format`/`formatted` with user-supplied strings as an "SQL template"; here the template is fixed in code and inserts *only* the question-mark list.

### Common Security Mistake

Do not write:

```java
// Unsafe if elements come from unprotected input:
String sql = "SELECT id FROM customer WHERE id IN (" +
             userSuppliedCsv + ")";
```

The example above pastes raw user strings into SQL, opening the door to syntax errors or SQL injection. Bind every value; having the placeholder string vary **by count** is not the same as concatenating input values into SQL.

## 5. Approach 2 — NamedParameterJdbcTemplate with List

`NamedParameterJdbcTemplate` lets you name a parameter and **expands a value list** into the required number of JDBC placeholders:

```java
String sql = """
    SELECT id, name
    FROM customer
    WHERE id IN (:ids)
    ORDER BY id
    """;

MapSqlParameterSource params =
    new MapSqlParameterSource("ids", ids);

List<Customer> customers = namedJdbcTemplate.query(
    sql,
    params,
    (rs, rowNum) -> new Customer(
        rs.getLong("id"), rs.getString("name")
    )
);
```

When `ids = List.of(3L, 1L)`, Spring processes the named parameter `:ids`, creates corresponding JDBC slots (conceptually like `IN (?, ?)`), and binds `3` and `1`. Note that `:ids` is Spring-layer syntax, **not syntax accepted directly by every JDBC driver**.

Key points to remember:

- List elements go through parameter binding; Spring never concatenates values into SQL.
- Not every `:ids` equals a single `?`. For collections, Spring expands it to match the element count.
- The name `ids` must match between the SQL and `MapSqlParameterSource`.
- **`NamedParameterJdbcTemplate` does not decide empty-set semantics on behalf of business logic.** When the list is empty, the expanded SQL can become invalid or DB-dependent; pick an empty policy **before calling query**.
- The API can also bind other parameters alongside `ids`, such as `tenantId`, `status`.

For many parameters or long SQL statements, named parameters are generally easier to read and avoid positional swap bugs compared to counting `?` manually. For a very short query in a codebase already using `JdbcTemplate`, dynamic placeholder generation remains valid.

### Why Should Neither Approach Blindly Accept Empty Lists?

There is no cross-DB guarantee that calling `NamedParameterJdbcTemplate.query` with `ids=[]` always returns 0 rows. Some DB/driver/SQL combinations reject `IN ()`. More importantly, **`NOT IN []`** operations have completely different semantics. Therefore the empty-list decision must live in the business/repository layer rather than relying on incidental framework behavior.

## 6. Complete Spring JDBC Class: Both Query Approaches and Empty Branches

The following example is for a Spring Boot/Framework application with `JdbcTemplate` and `NamedParameterJdbcTemplate` beans and the `customer` table from section 7. Necessary imports and types are provided for the class; `spring-jdbc` and `spring-context` are required on the classpath. This is integration code, **not a standalone Java program runnable with `javac` alone**.

File `CustomerInRepository.java`:

```java
import java.util.Collections;
import java.util.List;
import java.util.Objects;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public final class CustomerInRepository {
    public record Customer(long id, String name) {}

    private static final RowMapper<Customer> ROW_MAPPER =
        (rs, rowNum) -> new Customer(
            rs.getLong("id"),
            rs.getString("name")
        );

    private final JdbcTemplate jdbc;
    private final NamedParameterJdbcTemplate namedJdbc;

    public CustomerInRepository(
            JdbcTemplate jdbc,
            NamedParameterJdbcTemplate namedJdbc) {
        this.jdbc = jdbc;
        this.namedJdbc = namedJdbc;
    }

    private static List<Long> checkedIds(List<Long> values) {
        Objects.requireNonNull(values, "ids");
        if (values.stream().anyMatch(Objects::isNull)) {
            throw new IllegalArgumentException(
                "ids cannot contain null"
            );
        }
        return values.stream().distinct().toList();
    }

    public List<Customer> findByIdsJdbc(List<Long> input) {
        List<Long> ids = checkedIds(input);
        if (ids.isEmpty()) {
            return List.of();
        }

        String marks = String.join(
            ", ", Collections.nCopies(ids.size(), "?")
        );
        String sql = """
            SELECT id, name
            FROM customer
            WHERE id IN (%s)
            ORDER BY id
            """.formatted(marks);

        return jdbc.query(sql, ROW_MAPPER, ids.toArray());
    }

    public List<Customer> findByIdsNamed(List<Long> input) {
        List<Long> ids = checkedIds(input);
        if (ids.isEmpty()) {
            return List.of();
        }

        return namedJdbc.query(
            """
            SELECT id, name
            FROM customer
            WHERE id IN (:ids)
            ORDER BY id
            """,
            new MapSqlParameterSource("ids", ids),
            ROW_MAPPER
        );
    }

    // Tenant-scoped deletion. Empty = delete nothing.
    public int deleteForTenant(long tenantId, List<Long> input) {
        List<Long> ids = checkedIds(input);
        if (ids.isEmpty()) {
            return 0;
        }

        return namedJdbc.update(
            """
            DELETE FROM customer
            WHERE tenant_id = :tenantId
              AND id IN (:ids)
            """,
            new MapSqlParameterSource()
                .addValue("tenantId", tenantId)
                .addValue("ids", ids)
        );
    }

    // For NOT IN read query: empty = exclude no IDs.
    // Important: still retain tenant_id so other tenants are not accessed.
    public List<Customer> findExceptForTenant(
            long tenantId, List<Long> excludedInput) {
        List<Long> excluded = checkedIds(excludedInput);

        MapSqlParameterSource params =
            new MapSqlParameterSource("tenantId", tenantId);

        if (excluded.isEmpty()) {
            return namedJdbc.query(
                """
                SELECT id, name
                FROM customer
                WHERE tenant_id = :tenantId
                ORDER BY id
                """,
                params,
                ROW_MAPPER
            );
        }

        return namedJdbc.query(
            """
            SELECT id, name
            FROM customer
            WHERE tenant_id = :tenantId
              AND id NOT IN (:excluded)
            ORDER BY id
            """,
            params.addValue("excluded", excluded),
            ROW_MAPPER
        );
    }
}
```

The four methods demonstrate two policies that must not be confused:

- `findByIdsJdbc([])` and `findByIdsNamed([])` return `[]` without executing a query.
- `deleteForTenant(tenantId, [])` returns `0` modified rows without executing `DELETE`.
- `findExceptForTenant(tenantId, [])` **still queries customers in the matching tenant** and applies no exclusion filter.
- `findExceptForTenant(tenantId, [1, 3])` uses `id NOT IN (:excluded)` with both values bound.

Security lesson: `WHERE tenant_id = :tenantId` is mandatory in tenant-scoped methods. Never let an empty branch accidentally drop authorization predicates just because you intended to omit `IN` or `NOT IN`.

DB lesson: `deleteForTenant` should only be called in flows with proper authentication/authorization and transaction management where needed. Different write operations may require `@Transactional` and auditing; empty-list handling does not replace transaction policies.

## 7. Sample Data and Expected Results

You can create a dedicated schema in H2 or PostgreSQL to verify:

```sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    name VARCHAR(80) NOT NULL
);

INSERT INTO customer (id, tenant_id, name) VALUES
    (1, 10, 'Lan'),
    (2, 10, 'Minh'),
    (3, 10, 'Vy'),
    (4, 20, 'An');
```

Examples when running against the sample table using the two include/exclude approaches:

| Call | Effective SQL/Predicate | Result |
| --- | --- | --- |
| `findByIdsNamed([1])` | `id IN (?)` | Lan |
| `findByIdsNamed([3, 1])` | `id IN (?, ?)` | Lan, Vy (by `ORDER BY id`) |
| `findByIdsJdbc([3, 1, 3])` | `id IN (?, ?)` after `distinct()` | Lan, Vy; Vy not duplicated |
| `findByIdsNamed([])` | No SQL executed | Empty list |
| `findExceptForTenant(10, [1])` | `tenant_id=10 AND id NOT IN (?)` | Minh, Vy |
| `findExceptForTenant(10, [])` | Only `tenant_id=10` | Lan, Minh, Vy |
| `findExceptForTenant(20, [])` | Only `tenant_id=20` | An |

If `findByIdsNamed([1,4])` does not take a tenant parameter, the query could return both Lan and An. This is **why query methods in multi-tenant apps generally require a tenant filter**, not a reason to avoid `IN`. The initial include example in the lesson is purely for binding illustration; in real authorization-enforced systems, add a verified filter.

Do not assume `IN (3, 1)` returns Vy before Lan. `IN` is a membership test, not a result ordering clause. To get deterministic ordering, use `ORDER BY`; to match the exact **input list order**, design custom DB sorting or reorder results by the input list in Java.

## 8. Empty Case: Distinguishing INCLUDE and EXCLUDE

This is the core part of the lesson.

### 8.1. Empty Include List → Empty Result

If the feature is "find customers whose ID is in the selected IDs" and the user selected zero IDs, **no customer matches**. Three ways to express this:

**Option A — early return (usually clearest):**

```java
if (ids.isEmpty()) {
    return List.of();
}
```

Makes no DB call, avoids `IN ()`, and reduces load.

**Option B — always-FALSE predicate when SQL must still run:**

```sql
SELECT id, name
FROM customer
WHERE 1 = 0;
```

If there is a tenant filter, write `WHERE tenant_id = ? AND 1 = 0`. The query executes, yet filter logic matches zero rows. This fits callers needing a uniform SQL execution path, though it is not required for every use case.

**Option C — DB-specific constructs:** temporary tables, joining against a value set, or DB-specific arrays and operators. These solutions depend on dialect/infrastructure and are not universal substitutes.

Never unconditionally use `IN (NULL)` as an "empty normalization trick": `NULL` carries UNKNOWN logic, which can cause discrepancies when negated with `NOT IN` or combined with other joins/expressions. If the app wants FALSE, express FALSE explicitly.

### 8.2. Empty Exclude List → Exclude Nothing

Requirement "fetch customers in tenant 10, excluding the specified IDs":

- `excluded=[1,3]`: fetch ID 2 in tenant 10.
- `excluded=[]`: no ID excluded; fetch IDs 1, 2, 3 in tenant 10.

The right way for read queries is to **omit only the `NOT IN` predicate**, keeping all other business predicates:

```sql
-- Branch with values:
SELECT id, name
FROM customer
WHERE tenant_id = :tenantId
  AND id NOT IN (:excluded)
ORDER BY id;

-- Empty excluded branch:
SELECT id, name
FROM customer
WHERE tenant_id = :tenantId
ORDER BY id;
```

However, for write operations like `DELETE ... NOT IN (:excluded)`, "exclude no IDs" can turn into **deleting all rows matching the other conditions**. Never automatically drop `NOT IN` and run `DELETE` on an empty list; define business rules to **reject empty lists** or require an explicit, permission-checked "apply to all" mode.

### 8.3. Explicit Policy by Operation Type

| Request Form | Potentially Safe Empty-List Policy | Risk if Handled Wrongly |
| --- | --- | --- |
| `SELECT ... WHERE id IN (:ids)` | Return `[]` / `WHERE 1=0` | `IN ()` SQL error |
| `COUNT ... WHERE id IN (:ids)` | Return 0 if counting only selected IDs; or SQL FALSE | SQL error, or unintentionally counting whole table |
| `UPDATE ... WHERE id IN (:ids)` | Return 0 updated rows | Accidentally dropping `WHERE` updates in bulk |
| `DELETE ... WHERE id IN (:ids)` | Return 0, do not execute SQL | Unwanted data deletion |
| `SELECT ... WHERE id NOT IN (:ids)` | Drop only `NOT IN`, keep other predicates | Accidentally dropping tenant/ACL |
| `DELETE ... WHERE id NOT IN (:ids)` | Usually **reject empty** per fail-closed contract | Can delete most or all of the table |

There is no single `if (ids.isEmpty()) return List.of()` that fits **every** method. The empty branch must match operation semantics, return type, and scope-widening risk.

## 9. NULL in the List: SQL Three-Valued Logic Trap

A list containing a `null` element is **not the same** as an empty list. Example:

```sql
-- When id = 1, result is TRUE.
WHERE id IN (1, NULL)

-- When id = 2, 1 does not match; comparing with NULL gives UNKNOWN.
-- WHERE condition does not select UNKNOWN rows.
WHERE id IN (1, NULL)

-- For id = 2, NOT IN (1, NULL) is also UNKNOWN,
-- so row id=2 is NOT selected as many expect.
WHERE id NOT IN (1, NULL)
```

Assuming a non-nullable `id` column, compare:

| `id` Value | `id IN (1, NULL)` | `id NOT IN (1, NULL)` |
| ---: | --- | --- |
| 1 | TRUE | FALSE |
| 2 | UNKNOWN | UNKNOWN |
| 3 | UNKNOWN | UNKNOWN |

In `WHERE`, only rows evaluating to TRUE are kept. Thus `NOT IN (1, NULL)` can make a query return **0 rows**, even though IDs 2 and 3 clearly differ from 1.

**Recommendation for ID lists:** reject null elements right in Java, as in `checkedIds()`. If business logic genuinely wants to include a nullable column whose value is SQL NULL, express it separately with `IS NULL`:

```sql
-- Want id in the ID set or id IS NULL:
WHERE id IN (?, ?) OR id IS NULL
```

When combining `AND` and `OR` with other conditions, **place parentheses carefully**:

```sql
WHERE tenant_id = ?
  AND (external_code IN (?, ?) OR external_code IS NULL)
```

Never write `WHERE external_code IN (NULL)` expecting rows where `external_code IS NULL`. The proper syntax for NULL is `IS NULL`; normal comparison expressions obey three-valued logic.

With `NOT IN`, when excluded data comes from a secondary table that may contain NULLs, one option is `NOT EXISTS` with an appropriate correlated predicate; however, you must still clarify expected behavior when the main table's column is NULL. Do not swap syntax merely to mask unclear requirements.

## 10. NOT IN with Subqueries and NOT EXISTS

For example, finding customers **without** a record in `customer_blocklist`:

```sql
SELECT c.id, c.name
FROM customer c
WHERE NOT EXISTS (
    SELECT 1
    FROM customer_blocklist b
    WHERE b.customer_id = c.id
)
ORDER BY c.id;
```

`NOT EXISTS` returns TRUE when the subquery yields no matching rows. If `b.customer_id` is nullable, `b.customer_id = c.id` does not treat a NULL value as equal to the customer ID; NULL rows in the blocklist will not eliminate every customer as `NOT IN (SELECT ...)` risks doing.

For comparison, the query:

```sql
SELECT c.id
FROM customer c
WHERE c.id NOT IN (
    SELECT b.customer_id FROM customer_blocklist b
);
```

can return unexpected results whenever the subquery yields at least one `NULL`, because `NOT IN` operates under SQL UNKNOWN logic. `NOT EXISTS` usually expresses "no matching related record" more cleanly.

This is the case where **the value set comes from a table**; when input is a Java `List<Long>`, `NamedParameterJdbcTemplate` remains suitable and must handle empty lists before execution.

## 11. Dynamic Filters Combining Tenant, Status, and Authorization

Suppose a service may only read rows for the current tenant and the user selects some IDs:

```sql
SELECT id, name
FROM customer
WHERE tenant_id = :tenantId
  AND id IN (:ids)
ORDER BY id;
```

If `ids=[]` and the meaning is "zero IDs selected," return `[]`. If `ids=[1,4]`, the query must still preserve `tenant_id=:tenantId`; ID 4 belonging to tenant 20 will not be returned when the active tenant is 10.

**Never write an empty branch like**:

```sql
-- DANGEROUS: OR 1=1 defeats all filtering.
WHERE tenant_id = :tenantId
   OR 1 = 1
```

Nor should you use `WHERE id IN (:ids) OR :emptyFlag = TRUE` unless you have thoroughly verified semantics and permission boundaries. When `emptyFlag` is true, an `OR` condition can widen results beyond what the user is authorized to read if parentheses are missing or combined poorly.

Two safe patterns when an include list is empty:

1. **Early return** in service/repository: clear, executes no query.
2. **FALSE predicate** placed properly inside the overall predicate: `WHERE tenant_id = :tenantId AND 1 = 0`.

In systems with row-level security, tenant isolation should still be protected across multiple layers per appropriate architecture; repository code should never be assumed to be the sole line of defense.

## 12. Duplicates, Ordering, and Data Types

### 12.1. IN Does Not Duplicate Rows When Input Has Duplicates

`id IN (1, 1, 3)` is a **filter predicate**, not a JOIN against a three-row table. If `customer` only has one row for ID 1, the query will not return Lan twice just because the ID list contains 1 twice.

Deduplicate inputs when multiplicity is not needed:

```java
List<Long> unique = inputIds.stream().distinct().toList();
```

In Java 17, `distinct()` on an ordered stream from a `List` preserves first-seen order. However, **SQL result order** still depends on `ORDER BY`, not on the order of `unique`.

### 12.2. Want to Preserve Exact Client Input ID Order?

For example, `inputIds=[3, 1]` yet SQL `ORDER BY id` returns `[1, 3]`. If the API must return exact `[3, 1]`:

- Query once, build a `Map<Long, Customer>` by ID, then iterate `inputIds` in Java to order results (explicitly deciding whether repeated IDs duplicate output).
- Or use DB-specific ordering syntax like `CASE` or dialect ordering functions; bind values properly and check query cost.

Do not assume `IN (...)` preserves order. Nor should you force all results into input order when business rules require pagination or sorting by another column.

### 12.3. Data Types and Conversion

If `id` is `BIGINT`, use `Long`/`setLong` accordingly. For UUID, String, or enums, verify the column's actual type and how the driver binds it rather than passing everything as SQL strings for implicit DB casting. If explicit SQL type specification is needed (especially for NULLs), Spring provides `SqlParameterValue` or `MapSqlParameterSource.registerSqlType`, though in this lesson null IDs are forbidden so NULL handling inside the list is unnecessary.

## 13. When Multiple IN Conditions Appear Together

A query with two independent lists:

```sql
SELECT id, name
FROM customer
WHERE tenant_id IN (:tenantIds)
  AND id IN (:customerIds)
ORDER BY id;
```

If each set is a mandatory INCLUDE filter, **if either set is empty**, the combined result is empty. You can return early before sending SQL:

```java
if (tenantIds.isEmpty() || customerIds.isEmpty()) {
    return List.of();
}
```

However, if one filter is **optional**, distinguish carefully:

- Does a `null` parameter mean "do not apply filter" per the API contract?
- Does `[]` mean "zero values selected" or "no filter"?
- Is the caller allowed to omit the tenant filter?

Never use an ambiguous `List` and silently guess. You can create a request DTO separating the two intents:

```java
record FilterByIds(boolean enabled, List<Long> ids) {}
```

This is an illustrative type without constructor validation. If `enabled=true, ids=[]`, "filtering by an empty set" typically returns 0 rows; if `enabled=false`, the system may omit the filter **if access permissions allow**. "No filter" must never be inferred automatically from an empty list in sensitive operations.

## 14. Large Lists: Driver, DB, and Performance Limits

`NamedParameterJdbcTemplate` helps expand lists, yet **does not eliminate SQL/DB/driver limits**. Spring Framework specifically notes that DBMSs often cap the number of expressions in an `IN` list. For example, Spring docs cite Oracle's `1000`-expression limit in an `IN` list; other DBs and versions have different constraints, including total parameters per statement.

For very large lists, consider:

1. **Capping input size at the API** based on real needs: do not let an arbitrary request build SQL with tens of thousands of placeholders without justification.
2. **Measuring prepare, parse/plan, and execution time:** SQL changing `?` count per list length creates many statement shapes; statement/plan caching may become less effective.
3. **Using a temporary/staging/keyed relation table** to store the ID set and `JOIN` when lists are large enough and supported by the system.
4. **Using DB-specific solutions**: PostgreSQL has SQL arrays and `id = ANY(array_expression)`; an empty array yields FALSE with standard comparison operators. However, JDBC `Array` binding, type names, NULL handling, and resource cleanup are driver-dependent; it is not universal standard SQL.
5. **Chunking/batching** when genuinely needed, while ensuring query semantics, pagination, sorting, transactions, and result merging stay accurate.

### Chunking Requires Care with AND/OR

If you must split `IN` into multiple groups inside **one SQL query**, the right combinator for include is usually **OR**:

```sql
WHERE tenant_id = ?
  AND (
      id IN (?, ?, ?)
      OR id IN (?, ?, ?)
  )
```

Yet for **NOT IN** filters, meaning "not in any excluded group" usually requires **AND**:

```sql
WHERE tenant_id = ?
  AND id NOT IN (?, ?, ?)
  AND id NOT IN (?, ?, ?)
```

With inputs containing NULL, transformations must account for UNKNOWN logic; never generate SQL mechanically without testing. Moreover, splitting into **multiple queries** and concatenating output lists can break global ordering, `LIMIT/OFFSET` bounds, data snapshots, and uniqueness. A single SQL with many `OR` branches still cannot exceed DB-wide total parameter limits. For large lists, staging tables and `JOIN`s are often better.

Do not try to pick a universal "optimal threshold" across all DBs and systems. Test against your application's actual schema, indexes, data, and workload.

## 15. Testing Edge Cases

At minimum, test:

| Test Case | Input | Expectation |
| --- | --- | --- |
| Empty | `[]` | INCLUDE returns `[]` / DML IN returns 0; never produces `IN ()` |
| Single element | `[1]` | One `?` or one value in named list; returns row 1 |
| Multiple elements | `[3, 1]` | Two binds; results follow `ORDER BY`, not input order |
| Duplicates | `[3, 1, 3]` | Rows not duplicated; two binds if normalized |
| No matching ID in DB | `[999]` | Empty list, yet **SQL was executed** |
| `null` list | `null` | Explicit input error, not treated as "no filter" |
| Contains null element | `[1, null]` | Rejected or follows explicit rule; never unknowingly forms `NOT IN (..., NULL)` |
| Empty exclude | `[]` | `NOT IN` omitted in read query; tenant/ACL always preserved |
| Empty DELETE IN | `[]` | `DELETE` not run; 0 rows |
| Empty DELETE NOT IN | `[]` | Must have reject/explicit all-scope policy; never auto-delete broadly |
| More values than DB limit | Large list | Input error or switches to another strategy |
| ID from another tenant | `[1,4]`, tenant 10 | Must not return ID 4 when API is tenant-scoped |
| Ordering | `[3,1]` | Verify results match `ORDER BY id` or explicit reorder policy |

Two distinct test groups:

- **Unit tests**: verify normalization helpers, empty branches, placeholder count and bound parameter count, ordering, null guards, and no SQL generated for empty when designed that way.
- **Integration tests**: use the matching DB and real Spring JDBC, verifying `NamedParameterJdbcTemplate` list expansion, SQL execution, type binding, and preserved tenant predicates. For deletes/updates, test inside rolled-back transactions or a dedicated test DB.

Specifically, testing `[]` **must not only assert that no exception is thrown**. Check that the repository does not accidentally query all rows or perform broad writes.

## 16. Standalone Java 17 Program: IN Plan and Empty Branch

This example **does not access a DB and does not use Spring**. It illustrates deciding whether SQL will execute, generating placeholders by ID count, removing duplicates, and simulating rows returned after `ORDER BY id`.

Create `InListPolicyDemo.java`:

```java
import java.util.Collections;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.HashSet;

public final class InListPolicyDemo {
    record InPlan(boolean execute, String sql, List<Long> parameters) {}

    static InPlan plan(List<Long> ids) {
        Objects.requireNonNull(ids, "ids");
        if (ids.stream().anyMatch(Objects::isNull)) {
            throw new IllegalArgumentException("ids cannot contain null");
        }
        List<Long> unique = ids.stream().distinct().toList();
        if (unique.isEmpty()) {
            return new InPlan(false, "", List.of());
        }
        String marks = String.join(", ", Collections.nCopies(unique.size(), "?"));
        String sql = "SELECT id FROM customer WHERE id IN (" + marks + ") ORDER BY id";
        return new InPlan(true, sql, unique);
    }

    static List<Long> simulateDatabase(InPlan plan) {
        if (!plan.execute()) {
            return List.of();
        }
        Set<Long> wanted = new HashSet<>(plan.parameters());
        return List.of(1L, 2L, 3L).stream()
            .filter(wanted::contains)
            .toList();
    }

    public static void main(String[] args) {
        InPlan withIds = plan(List.of(3L, 1L, 3L));
        System.out.println(withIds.sql());
        System.out.println("bind=" + withIds.parameters());
        System.out.println("rows=" + simulateDatabase(withIds));

        InPlan empty = plan(List.of());
        System.out.println("empty.execute=" + empty.execute());
        System.out.println("empty.bind=" + empty.parameters());
        System.out.println("empty.rows=" + simulateDatabase(empty));
    }
}
```

Compile with JDK 17 or higher:

```bash
javac --release 17 InListPolicyDemo.java
java InListPolicyDemo
```

Exact output:

```text
SELECT id FROM customer WHERE id IN (?, ?) ORDER BY id
bind=[3, 1]
rows=[1, 3]
empty.execute=false
empty.bind=[]
empty.rows=[]
```

Output explanation:

- Input `[3,1,3]` normalizes to `[3,1]` → two placeholders.
- `rows=[1,3]` is the list after simulating DB reads per `ORDER BY id`, not necessarily matching bind order.
- For the empty list, `execute=false`; no `IN ()`, no DB call, and simulated row set is empty.
- `InPlan` is a custom record for learning, **not a Spring class**. In real repositories, parameters are bound with `JdbcTemplate` or `NamedParameterJdbcTemplate`, rather than using Java filters instead of SQL.

This is also how to separate logic for unit testing: `plan(...)` needs no DB connection; with real Spring, separate tests can cover the repository.

## 17. Common Mistakes and Fixes

### Mistake 1: Passing a CSV String as One Parameter

`id IN (?)` with `"1,3"` is not equivalent to `id IN (1,3)`. Fix with dynamic placeholders or named parameter list expansion.

### Mistake 2: Letting Empty Lists Flow Straight into SQL

Producing `IN ()` can cause syntax errors. Fix: handle `isEmpty()` before calling the DB; define return values matching business rules.

### Mistake 3: Treating Empty Lists and Null Lists as Identical

`null` may mean "parameter omitted," "no filter," or an error; `[]` usually means "empty set selected." Define the API contract instead of conflating them.

### Mistake 4: Handling `NOT IN []` the Same as `IN []`

For read queries, `NOT IN []` usually means "exclude nobody," not returning empty. For writes, dropping the predicate when empty can cause **broad UPDATE/DELETE**; fail closed.

### Mistake 5: Using `IN (NULL)` as an Empty Expression

This can cause differences under three-valued logic, especially when negated and combined with other predicates. If FALSE is desired, use an early return or explicit FALSE predicate.

### Mistake 6: Allowing `null` into `NOT IN`

`NOT IN (1, NULL)` often turns many rows into UNKNOWN so they are not selected. Fix: validate non-null inputs, or design explicit NULL semantics; consider `NOT EXISTS` for subqueries.

### Mistake 7: Concatenating Values Straight into SQL

Concatenating untrusted IDs/strings into SQL risks injection. Fix: insert only **question-mark structure** derived from element count, while passing values through binding.

### Mistake 8: Dynamically Substituting Table/Column Names with `?`

`?` only binds **values**, not identifiers or SQL keywords. If columns must vary, select from an allowlist of permitted columns.

### Mistake 9: Using `IN` Expecting to Preserve User ID Order

`IN (3,1)` does not guarantee `[3,1]` output. Fix: use `ORDER BY` or input-based reordering logic when genuinely required.

### Mistake 10: Thinking Duplicate Inputs Make SQL Return Duplicate Rows

`IN (3,3)` is a predicate; it does not make a DB row appear twice. If a query returns duplicates, check `JOIN`s/data before blaming the list.

### Mistake 11: Skipping Tenant Checks When Filtering by IDs

A valid list can still contain IDs outside the caller's scope. Fix: every SQL query must retain tenant/authorization conditions, including empty and `NOT IN` branches.

### Mistake 12: Trusting Unbounded List Expansion

DBs/drivers cap expression or parameter counts. Fix: reject oversized lists, measure performance, and use staging tables or DB-specific arrays where appropriate.

### Mistake 13: Splitting Multiple `NOT IN` Groups and Joining with OR

`id NOT IN (1,2) OR id NOT IN (3,4)` is almost always broader than excluding both groups. Fix: for non-null sets and "not in any" logic, combine with **AND**.

### Mistake 14: Paginating Each Chunk and Merging Arbitrarily

`LIMIT/OFFSET` on individual chunks is not equivalent to paginating the merged result. Fix: plan global querying and ordering before chunking.

### Mistake 15: Failing to Distinguish "0 Matching Rows" from "No SQL Run"

`findByIds([999])` still runs a query and gets 0 rows; `findByIds([])` under this lesson's policy **runs no query**. This can affect auditing/metrics, so test per operational requirements.

## 18. Self-Check Questions

**1. Why not write `WHERE id IN (?)` and bind a string `"1,2,3"`?**  
Because one `?` is one JDBC parameter; a CSV string does not automatically split into three values. You need three placeholders or named parameter expansion.

**2. With `ids = List.of(4L, 1L)`, how many `?` does the dynamic JDBC approach create?**  
Two; e.g., `IN (?, ?)` passing two separate bound values.

**3. If `ids=[]` and this is a "select exact requested IDs" query, what is the result?**  
An empty list or a FALSE predicate. Never call `IN ()` blindly.

**4. If `excludedIds=[]` for a `NOT IN` read query, should it return empty?**  
No; when intent is "exclude nobody," omit only the exclusion condition and retain other predicates like tenant.

**5. Why is an empty branch for `DELETE ... WHERE id NOT IN (:ids)` dangerous?**  
Because dropping `NOT IN` can make `DELETE` affect every remaining matching row, or even the whole table if other `WHERE` conditions are absent. Reject empty or require an explicit full-scope mode.

**6. Does `[1, 1, 3]` produce three rows from a table containing only IDs 1 and 3?**  
No. `IN` is a predicate; each table row is selected by the condition, not multiplied by input repetition count.

**7. Does `id NOT IN (1, NULL)` return ID 2?**  
In `WHERE`, normally no: the condition evaluates to UNKNOWN because NULL is in the list, so the row is not selected.

**8. Does `IN (3, 1)` guarantee returning ID 3 before ID 1?**  
No. Ordering depends on `ORDER BY` or post-query sorting policy.

**9. When a list has thousands of IDs, is increasing SQL length alone enough?**  
No. You must check DB/driver limits, total parameters, parse/plan cost, indexing, and alternative strategies (staging tables, DB-specific arrays, semantically accurate batching).

**10. If there are two INCLUDE filters and one list is empty, should you drop the empty filter so the query isn't "too restrictive"?**  
Not if the empty list means "no values selected": the overall result must be empty. Only omit a filter when the contract explicitly marks it optional and the caller is authorized to do so.

## 19. Takeaways

- `IN` is a **membership test**, does not determine ordering, and does not duplicate rows from repeated IDs.
- A JDBC `?` represents **one value**, so `JdbcTemplate` needs as many `?` as elements; `NamedParameterJdbcTemplate` can expand `IN (:ids)` from a `List`.
- **Always handle empty lists before execution**: empty include usually returns empty; empty exclude usually omits only the exclusion predicate in read queries; sensitive write operations should fail closed.
- Never conflate `null` and `[]`; never pass `NULL` elements into `NOT IN` without explicit semantics.
- Build SQL solely from trusted structure (`?` markers), binding values separately; never concatenate CSV/user values into SQL.
- Preserve tenant, authorization, status, and other predicates across empty branches.
- Monitor list sizes, DB/driver limits, and performance; for large inputs consider staging tables, `JOIN`s, DB-specific arrays, or verified batching.
- Test 0, 1, and N elements; duplicates, nulls, nonexistent IDs, cross-tenant IDs, and both `IN`/`NOT IN` before deploying to production.

### References

- [Spring Framework — Passing in Lists of Values for IN Clause](https://docs.spring.io/spring-framework/reference/data-access/jdbc/parameter-handling.html)
- [Spring Framework — Choosing an Approach for JDBC Database Access](https://docs.spring.io/spring-framework/reference/data-access/jdbc/choose-style.html)
- [Spring Framework Javadoc — NamedParameterJdbcTemplate](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/namedparam/NamedParameterJdbcTemplate.html)
- [Spring Framework Javadoc — JdbcTemplate](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html)
- [PostgreSQL — Row and Array Comparisons (IN, NOT IN, ANY)](https://www.postgresql.org/docs/current/functions-comparisons.html)
