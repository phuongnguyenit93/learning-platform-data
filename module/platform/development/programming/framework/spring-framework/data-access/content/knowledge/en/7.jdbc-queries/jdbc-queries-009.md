# Pagination, Explicit Sorting, and Total Count Queries When Needed

## Lesson Objectives

A search API may match tens of thousands of records, while the screen displays only 20–50 records per turn. With Spring JDBC, we need to design SQL that retrieves **exactly one page**, with **deterministic ordering**, while deciding **when to count the total number of records**.

After this lesson, you should be able to:

1. Write `ORDER BY`, `LIMIT`, `OFFSET`, and matching parameters in `JdbcTemplate`.
2. Explain why paginating without explicit sorting, or sorting by a non-unique column, can return unstable pages.
3. Safely compute offset from page/size, validate maximum size, and handle pages past the end of the dataset.
4. Run `SELECT COUNT(*)` only when the UI/API contract genuinely needs `totalElements` or `totalPages`; distinguish **Page** and **Slice**.
5. Recognize the cost of large offsets, compare with **keyset/cursor pagination**, and understand the impact of data changing between requests.
6. Implement a complete **Java 17+, Spring JdbcTemplate, and H2** example, verifying its output against sample data.

Examples use `LIMIT ... OFFSET ...` syntax supported by H2 and PostgreSQL. Other DBMSs may use `FETCH FIRST`, `OFFSET ... FETCH`, or equivalent syntax; pagination and sorting principles stay the same, though you must verify the actual dialect.

## 1. Why Not Return the Entire Result Set?

Suppose the `tasks` table contains 500,000 tasks. Calling:

```sql
SELECT id, title, created_at
FROM tasks
WHERE tenant_id = 7 AND status = 'OPEN';
```

asks the database to return every matching row. Even with good indexes, the network, JDBC driver, `RowMapper`, JVM memory, and client all incur heavy overhead. For a paginated table, the sensible approach is fetching only the rows to display.

Server-side pagination is not the same as fetching 500,000 rows and calling `list.subList(...)` in Java. Doing it in Java still loads and maps the entire result before slicing, solving nothing about data volume.

Minimum query structure:

```sql
SELECT id, title, created_at
FROM tasks
WHERE tenant_id = ?
  AND status = ?
ORDER BY created_at DESC, id DESC
LIMIT ?
OFFSET ?;
```

- `WHERE` restricts the dataset by tenant, status, and access-control rules.
- `ORDER BY` establishes **a stable order within a given data state**.
- `LIMIT` is the maximum number of rows returned.
- `OFFSET` is the number of leading rows in that order to skip.
- `?` markers are JDBC placeholders for **values**, bound via `JdbcTemplate`.

Here `id` is a unique primary key. When multiple rows share the same `created_at`, `id DESC` acts as a tie-breaker to eliminate arbitrary reordering among equal timestamps.

## 2. ORDER BY Must Be Explicit and Sufficient to Distinguish Every Row

### 2.1. Without ORDER BY, There Is No Guaranteed Order

A query without `ORDER BY` **is not guaranteed** to return rows by PK, insertion order, or the order "seen on the previous run". The database can switch execution plans, pick a different index, run in parallel, or store physical data differently.

Error-prone example:

```sql
SELECT id, title FROM tasks
WHERE tenant_id = 7
LIMIT 10 OFFSET 10;
```

`LIMIT/OFFSET` alone does not define which 10 rows are "page 2". In pagination, `ORDER BY` belongs in the query actually sent to the DBMS, not merely `Collections.sort()` on ten already-fetched rows.

### 2.2. One Non-Unique Sort Column Is Still Not Enough

Consider the data:

| id | created_at | title |
| ---: | --- | --- |
| 11 | 2025-01-02 09:00:00 | A |
| 12 | 2025-01-02 09:00:00 | B |
| 13 | 2025-01-03 09:00:00 | C |
| 14 | 2025-01-03 09:00:00 | D |
| 15 | 2025-01-04 09:00:00 | E |

If you only write `ORDER BY created_at DESC`, rows 13/14 and 11/12 have **tied sort keys**. Order within each tied group can vary between executions, causing a row to appear on two pages or be skipped when a page boundary falls between tied rows.

Writing:

```sql
ORDER BY created_at DESC, id DESC
```

produces a total ordering across rows when `id` is unique. For identical timestamps, `id` decides placement. In this example `created_at` is declared `NOT NULL`; if a sort column is nullable, standardize the NULL rule and the DBMS's `NULLS FIRST/LAST` syntax.

**Note:** Deterministic ordering does **not** mean multi-request results remain static if rows are inserted, deleted, or updated between requests. Those are two separate concerns: *tie-breaking* and *snapshot consistency*.

### 2.3. ASC/DESC, Tie-Breaker Key, and Consistency

- `ASC`: ascending; `DESC`: descending.
- Choose ordering per business logic, e.g., newest tasks first is `created_at DESC`.
- Add a unique tie-breaker key like `id DESC` for stability when timestamps match.
- In cursor pagination, the "after last row" condition must match **the same direction** as `ORDER BY`.
- If a user switches sort from "newest" to "oldest", the old cursor is invalid for the new order; start over.

Never use `ORDER BY RANDOM()` for standard pagination; random order changes constantly and is usually expensive.

### 2.4. ORDER BY Cannot Bind Column Names with Question Marks

Prepared statement `?` placeholders are for **values**, not SQL identifiers or keywords. A statement like this will not sort by the desired column:

```sql
-- Wrong intent: ? is not a SQL column name.
SELECT id, title FROM tasks ORDER BY ? LIMIT ?;
```

For client-selectable sorting, map input against an **allowlist of permitted columns and directions**, then assemble the `ORDER BY` clause. Java example (standalone sort-handling snippet, not yet a repository):

```java
static String allowedOrderBy(String requestedSort) {
    return switch (requestedSort) {
        case "newest" -> "created_at DESC, id DESC";
        case "oldest" -> "created_at ASC, id ASC";
        case "title" -> "title ASC, id ASC";
        default -> throw new IllegalArgumentException("Unsupported sort");
    };
}
```

Never concatenate `request.getSort()` directly into SQL. Using an allowlist both mitigates SQL injection and ensures every option includes a unique tie-breaker. When sorting text, collations and case sensitivity may differ across DBMSs; define the desired behavior.

## 3. LIMIT/OFFSET: Computing a Page

### 3.1. Choosing 0-Based or 1-Based Page Numbering

In many internal or Spring Data-style APIs, `page=0` is the first page. With `size=3`:

| page (0-based) | size | offset | Fetches |
| ---: | ---: | ---: | --- |
| 0 | 3 | 0 | Rows 1–3 per ORDER BY |
| 1 | 3 | 3 | Rows 4–6 |
| 2 | 3 | 6 | Rows 7–9 |

Formula:

```text
offset = page * size
LIMIT size OFFSET offset
```

If a public API exposes `page=1` for the first page, use `offset = (page - 1) * size` after validating `page >= 1`. **Do not mix the two conventions** between backend and UI; document it clearly in the API contract.

### 3.2. Validate Before Sending SQL

Check:

- `page >= 0` under zero-based convention.
- `size >= 1` and a reasonable upper bound, e.g., `size <= 100`.
- Cast before multiplying: `long offset = (long) page * size`; multiplying as `int` with large values can overflow into a negative offset.
- If the database/driver or API policy caps offsets, reject values above the supported limit.
- With `size + 1` when implementing Slice, reject oversized `size` so it cannot overflow; `1..100` is safe.

Input errors should be returned cleanly at the web layer (typically HTTP 400 for invalid parameters) instead of letting an obscure database `SQLException` bubble up.

### 3.3. A SQL Page Can Return Fewer Than size Rows

`LIMIT 20` means "at most 20", not "always 20". If the query has 7 rows left at the end of the dataset, it returns 7. If `OFFSET` goes past the end of the list, `query` returns an empty list; that does **not mean total results equal 0**. To know the total, you need a corresponding count/metadata source.

With `JdbcTemplate`:

```java
List<TaskView> items = jdbc.query(
        """
        SELECT id, title, created_at
        FROM tasks
        WHERE tenant_id = ? AND status = ?
        ORDER BY created_at DESC, id DESC
        LIMIT ? OFFSET ?
        """,
        TASK_MAPPER,
        tenantId, status, size, offset);
```

This is a **snippet** assuming variables and `TASK_MAPPER` exist; section 8 has the complete program. `query` returns an empty list when there are no rows. Never use `queryForObject` for a page containing 0..N rows.

## 4. Querying the Total: Is COUNT(*) Needed?

There are two separate pieces of information:

- `items`: data for the **current page**, fetched via `LIMIT/OFFSET`.
- `totalElements`: total rows matching **all filter conditions**, **without LIMIT/OFFSET**.

Example:

```sql
SELECT COUNT(*)
FROM tasks
WHERE tenant_id = ?
  AND status = ?;
```

In Java:

```java
Long total = jdbc.queryForObject(
        "SELECT COUNT(*) FROM tasks WHERE tenant_id = ? AND status = ?",
        Long.class,
        tenantId, status);
```

`COUNT(*)` without `GROUP BY` returns one row even when there is no data, with value 0. `Long` is not derived from the page size's `int` type; use `long/Long` for totals since row counts can exceed 2.1 billion. In the demo, `COUNT(*)` is non-NULL so `Long` can be unboxed; consider nullability checks for other SQL scalar queries.

### 4.1. When Counting Is Needed

Counting fits when the UI/API must know:

- "6 results total".
- "Page 1 of 2".
- A list of page numbers allowing direct jumps or a "last page" button.
- An admin report requiring exact filtered record totals.

Once you have `total` and `size > 0`, total pages can be computed as:

```java
long totalPages = total / size + (total % size == 0 ? 0 : 1);
```

This avoids `total + size - 1`, which could overflow near `Long.MAX_VALUE`. When total is 0, `totalPages = 0` by the convention of pages containing data; the UI can display "0 results" instead of "page 1/0".

### 4.2. When Not to Count on Every Request

`COUNT(*)` is a **separate** query. With complex filters, JOINs, large data, or certain DBMSs, it can consume substantial CPU/I/O. If the UI only offers **"Load more"** or "Next page", skip counting and use a **Slice**, fetching `size + 1` rows:

```sql
SELECT id, title, created_at
FROM tasks
WHERE tenant_id = ?
  AND status = ?
ORDER BY created_at DESC, id DESC
LIMIT ? OFFSET ?;
```

Bind `limit = size + 1`. If more than `size` rows come back, **at least one next row** exists in the data state at query time; return at most `size` rows to the client along with a `hasNext` flag. Skip `COUNT(*)`.

**Limitation:** Slice's `hasNext` does not tell you total pages and does not guarantee the next page will still have rows if data changes. It answers a lighter question than counting.

### 4.3. COUNT Must Use the Exact Same Conditions as the List

A very common bug:

```sql
-- List is scoped to current tenant and filtered by status:
SELECT id, title
FROM tasks
WHERE tenant_id = ? AND status = 'OPEN'
ORDER BY created_at DESC, id DESC
LIMIT ? OFFSET ?;

-- Wrong count because tenant or status was forgotten:
SELECT COUNT(*) FROM tasks;
```

Then UI totals do not match the results, and counting without tenant scoping can also **leak data volume info** from other tenants.

The `COUNT(*)` query must keep the **exact same business and authorization filters** as the items query: tenant, status, date ranges, search terms, soft delete, ACLs... `ORDER BY` is unnecessary for counting the whole set; `LIMIT/OFFSET` must never be included in the total count.

A good practice is treating the "filter" as a single contract and verifying via tests that both SQL statements evolve in sync. When conditions grow complex, use a controlled SQL builder, named parameters, or a query framework; never concatenate user data into SQL strings.

### 4.4. JOINs Can Multiply Counted Rows

If a task has multiple tags, joining `task_tags` creates multiple rows per task:

```sql
SELECT t.id, t.title
FROM tasks t
JOIN task_tags g ON g.task_id = t.id
WHERE t.tenant_id = ? AND g.name IN (?, ?);
```

If one task has both tags, it appears multiple times. `COUNT(*)` over the JOIN counts **post-JOIN rows**, not distinct tasks. When the contract is "count unique tasks", you may need:

```sql
SELECT COUNT(DISTINCT t.id)
FROM tasks t
JOIN task_tags g ON g.task_id = t.id
WHERE t.tenant_id = ? AND g.name IN (?, ?);
```

The page-fetching query must also resolve duplicates properly (e.g., via `EXISTS`, a CTE/subquery selecting unique IDs, or another strategy). Do not fix only the count with `DISTINCT` while items still return duplicate rows; this is a query design issue that must be handled consistently.

If a query uses `GROUP BY`, `HAVING`, or grouping aggregates, counting **the number of filtered groups** may require wrapping the query in a subquery (omitting unnecessary ORDER BY/LIMIT) and running `COUNT(*)` outside. The goal is counting **the exact entity the API paginates**.

## 5. Page vs. Slice: Choosing by API Contract

| Criterion | Page with count | Slice without count |
| --- | --- | --- |
| Page data | Query with `LIMIT/OFFSET` | Query fetching `size + 1` rows |
| Queries per call in typical JDBC implementation | Two: page + count | One: items |
| Has `totalElements` | Yes | No |
| Has `totalPages` | Derived from count/size | No |
| Knows if next page exists | Derived from count (at that point in time) | Inferred from the `(size + 1)`th row |
| Suitable UI | Page numbers, total results, last-page button | "Show more", load more, feeds |
| Risks/trade-offs | Count can be costly; count and items may see different snapshots | No total count; large offsets can still be costly |

Spring Data has `Page`/`Slice` abstractions. However, `JdbcTemplate` **does not automatically build** `Page<T>` or run count queries for you from SQL. With plain JDBC, you can return result records like `TaskPage` and `TaskSlice` in the example below.

Common usage:

- Screens with page numbers **and** total results: Page + count.
- Infinite scrolling or "Load more": Slice.
- Report exports: usually not interactive pagination; may need dedicated streaming/batching.
- Large time-ordered feeds with cursors: keyset, not necessarily offset.

## 6. Consistency When Data Changes

### 6.1. OFFSET Can Shift Boundaries

Suppose the first page returns IDs `[105, 104, 103]` ordered by `created_at DESC, id DESC` with `size=3`. Before the client requests the next page, a new task `106` is inserted at the top. Running `OFFSET 3` on the updated set may start the next page at `103` — duplicating a row from the previous page.

Conversely, if an earlier row is deleted or updated out of the filter, offset can cause the client to **skip** a row.

Key points:

- **A unique tie-breaker** guarantees clear ordering within a single data state.
- It **does not freeze the dataset** across separate HTTP requests.
- Applications may accept this drift for frequently changing lists; if not, adopt a more consistent pagination model.

### 6.2. Page Query and COUNT Query Can See Different Snapshots

In a typical Page implementation, `SELECT ... LIMIT/OFFSET` and `SELECT COUNT(*)` are two separate statements. If data changes between them, the page may return 3 rows while `total` reflects another moment. Even within one transaction, the **isolation level** dictates whether two statements see the same snapshot. For example, under PostgreSQL `READ COMMITTED`, two `SELECT`s in the same transaction can see different snapshots; using `REPEATABLE READ` for a transaction provides a consistent snapshot within that transaction, though it still cannot span independent HTTP requests.

Never promise a perfectly stable count over a continuously mutating list. If reconciliation or high accuracy is required, design snapshots, watermarks, or matching transactions and accept the trade-offs.

### 6.3. When to Use Keyset/Cursor Pagination?

Large offsets like `OFFSET 100000` can force the database to scan and discard many rows before returning the requested page. A suitable B-tree index helps, yet offset cost still tends to grow with page depth.

**Keyset pagination** does not say "skip 100,000 rows"; it says "fetch rows **after the last sort key** of the previous page".

With order `created_at DESC, id DESC` and the previous page's last key `(lastCreatedAt, lastId)`:

```sql
SELECT id, title, created_at
FROM tasks
WHERE tenant_id = ?
  AND status = ?
  AND (
       created_at < ?
       OR (created_at = ? AND id < ?)
  )
ORDER BY created_at DESC, id DESC
LIMIT ?;
```

For example, if the first page is `[15, 14, 13]` and row 13 has `created_at = 2025-01-03 09:00:00`, the cursor for the next page is `(2025-01-03 09:00:00, 13)`; the next query fetches `[12, 11, 18]`. Row 14 shares the timestamp with 13 but has a larger id, so it already appeared on the previous page and is not returned again.

In some DBMSs like PostgreSQL, row-value comparisons work when columns are non-NULL:

```sql
AND (created_at, id) < (?, ?)
```

However, verify syntax and data-type rules on your DBMS. The two-branch `OR` predicate above matches descending order on both columns; mixing ASC/DESC or sorting nullable columns requires different predicate logic.

**Advantages:** keyset queries can seek directly to the index range after the cursor and reduce duplicate/skipped rows from inserts ahead of the cursor.

**Limitations:**

- Inconvenient for jumping straight to "page 800" without knowing its cursor.
- Requires **deterministic** sorting, keeping sort keys in the cursor, and preserving the same filters across pages.
- If sort-key values themselves are updated, keyset can still skip/repeat records; it is not a full historical snapshot.
- Public cursors should be opaque tokens holding needed values, version/sort/filter info, and a signature/HMAC if tampering must be prevented. Never rely on a cursor to replace SQL tenant/authorization checks.
- Nullable sort columns require explicit NULL policies and keyset expressions.

In Spring JDBC, cursor pagination is simply a different SQL query with placeholders for `lastCreatedAt` and `lastId`, without changing the fundamentals of `JdbcTemplate.query(...)`.

## 7. Indexes and Execution Plans for Pagination

A production query often runs repeatedly with the same filter + sort:

```sql
SELECT id, title, created_at
FROM tasks
WHERE tenant_id = ?
  AND status = ?
ORDER BY created_at DESC, id DESC
LIMIT ? OFFSET ?;
```

In PostgreSQL with sizable data, a candidate to **evaluate** is a B-tree index:

```sql
CREATE INDEX tasks_tenant_status_created_id_idx
ON tasks (tenant_id, status, created_at DESC, id DESC);
```

Reason: `tenant_id` and `status` are equality predicates; `created_at DESC, id DESC` matches the fetch order. A matching index can let the database return a page without sorting the entire result set. It can also support keyset predicates.

**However, indexes are not an automatic cure-all:**

- Small tables or low-selectivity filters may favor sequential scans.
- `COUNT(*)` queries can choose a different plan from page queries; an index does not make counting "free".
- Indexes add storage and write maintenance overhead on insert/update/delete.
- A sort-supporting index does not completely eliminate the cost of a huge `OFFSET`.
- Inspect `EXPLAIN`/`EXPLAIN ANALYZE` on your DBMS and realistic data, checking row estimates, filters, sorts, and buffer/I/O before deciding.

Creating indexes is unnecessary in the small H2 demo below: a handful of rows runs quickly via table scan and does not reflect production behavior.

## 8. Runnable Practice: Spring JDBC + H2 + Java 17

The following program demonstrates two query styles:

1. **Page**: returns items and exact `COUNT(*)` for the filter at each statement's execution time.
2. **Slice**: fetches one extra row to determine `hasNext` without counting.

It also demonstrates why `ORDER BY created_at DESC, id DESC` yields deterministic results when timestamps tie.

### 8.1. Project Structure

```text
jdbc-paging-demo/
├── build.gradle
└── src/main/java/example/JdbcPagingDemo.java
```

### 8.2. build.gradle

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.12'
    implementation 'org.springframework:spring-jdbc:6.2.12'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'example.JdbcPagingDemo'
}
```

Assumes a Gradle version supporting Java 17 or a matching Gradle Wrapper is installed. Needs Maven Central access to download libraries if not cached. No Spring Boot or separate database server is required.

### 8.3. Complete Java File

Create `src/main/java/example/JdbcPagingDemo.java`:

```java
package example;

import java.sql.Timestamp;
import java.time.LocalDateTime;
import java.util.List;
import javax.sql.DataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

@Configuration
public class JdbcPagingDemo {
    record TaskView(long id, String title, LocalDateTime createdAt) {}
    record TaskPage(List<TaskView> items, int page, int size, long total) {}
    record TaskSlice(List<TaskView> items, boolean hasNext) {}

    private static final RowMapper<TaskView> TASK_MAPPER =
            (rs, rowNumber) -> new TaskView(
                    rs.getLong("id"),
                    rs.getString("title"),
                    rs.getTimestamp("created_at").toLocalDateTime()
            );

    private static final String PAGE_SQL = """
            SELECT id, title, created_at
            FROM tasks
            WHERE tenant_id = ? AND status = ?
            ORDER BY created_at DESC, id DESC
            LIMIT ? OFFSET ?
            """;

    private static final String COUNT_SQL = """
            SELECT COUNT(*)
            FROM tasks
            WHERE tenant_id = ? AND status = ?
            """;

    @Bean
    DataSource dataSource() {
        DriverManagerDataSource source = new DriverManagerDataSource();
        source.setDriverClassName("org.h2.Driver");
        source.setUrl("jdbc:h2:mem:paging_demo;DB_CLOSE_DELAY=-1");
        source.setUsername("sa");
        source.setPassword("");
        return source;
    }

    @Bean
    JdbcTemplate jdbcTemplate(DataSource dataSource) {
        return new JdbcTemplate(dataSource);
    }

    private static void validate(int page, int size) {
        if (page < 0 || size < 1 || size > 100) {
            throw new IllegalArgumentException(
                    "page must be >= 0, size must be 1..100");
        }
    }

    static TaskPage fetchPage(
            JdbcTemplate jdbc, long tenantId, String status,
            int page, int size) {
        validate(page, size);
        long offset = (long) page * size;

        List<TaskView> items = jdbc.query(
                PAGE_SQL, TASK_MAPPER,
                tenantId, status, size, offset);

        Long total = jdbc.queryForObject(
                COUNT_SQL, Long.class, tenantId, status);

        // COUNT(*) without GROUP BY always returns one non-null row.
        return new TaskPage(items, page, size, total);
    }

    static TaskSlice fetchSlice(
            JdbcTemplate jdbc, long tenantId, String status,
            int page, int size) {
        validate(page, size);
        long offset = (long) page * size;

        // Fetch 1 extra row instead of running COUNT(*).
        List<TaskView> fetched = jdbc.query(
                PAGE_SQL, TASK_MAPPER,
                tenantId, status, size + 1, offset);

        boolean hasNext = fetched.size() > size;
        List<TaskView> visible = List.copyOf(
                fetched.subList(0, Math.min(size, fetched.size())));
        return new TaskSlice(visible, hasNext);
    }

    static void insert(
            JdbcTemplate jdbc, long id, long tenantId, String status,
            String timestamp, String title) {
        jdbc.update(
                """
                INSERT INTO tasks (id, tenant_id, status, created_at, title)
                VALUES (?, ?, ?, ?, ?)
                """,
                id, tenantId, status,
                Timestamp.valueOf(timestamp), title);
    }

    private static List<Long> ids(List<TaskView> tasks) {
        return tasks.stream().map(TaskView::id).toList();
    }

    public static void main(String[] args) {
        try (var ctx = new AnnotationConfigApplicationContext(
                JdbcPagingDemo.class)) {
            JdbcTemplate jdbc = ctx.getBean(JdbcTemplate.class);

            jdbc.execute("""
                    CREATE TABLE tasks (
                        id BIGINT PRIMARY KEY,
                        tenant_id BIGINT NOT NULL,
                        status VARCHAR(12) NOT NULL,
                        created_at TIMESTAMP NOT NULL,
                        title VARCHAR(40) NOT NULL
                    )
                    """);

            insert(jdbc, 11, 7, "OPEN",   "2025-01-02 09:00:00", "A");
            insert(jdbc, 12, 7, "OPEN",   "2025-01-02 09:00:00", "B");
            insert(jdbc, 13, 7, "OPEN",   "2025-01-03 09:00:00", "C");
            insert(jdbc, 14, 7, "OPEN",   "2025-01-03 09:00:00", "D");
            insert(jdbc, 15, 7, "OPEN",   "2025-01-04 09:00:00", "E");
            insert(jdbc, 16, 7, "CLOSED", "2025-01-05 09:00:00", "F");
            insert(jdbc, 17, 8, "OPEN",   "2025-01-06 09:00:00", "G");
            insert(jdbc, 18, 7, "OPEN",   "2025-01-01 09:00:00", "H");

            TaskPage p0 = fetchPage(jdbc, 7, "OPEN", 0, 3);
            TaskPage p1 = fetchPage(jdbc, 7, "OPEN", 1, 3);
            TaskPage p2 = fetchPage(jdbc, 7, "OPEN", 2, 3);

            System.out.println(
                    "page0=" + ids(p0.items()) + ",total=" + p0.total());
            System.out.println(
                    "page1=" + ids(p1.items()) + ",total=" + p1.total());
            System.out.println(
                    "page2=" + ids(p2.items()) + ",total=" + p2.total());

            TaskSlice s0 = fetchSlice(jdbc, 7, "OPEN", 0, 3);
            TaskSlice s1 = fetchSlice(jdbc, 7, "OPEN", 1, 3);

            System.out.println(
                    "slice0=" + ids(s0.items()) +
                    ",hasNext=" + s0.hasNext());
            System.out.println(
                    "slice1=" + ids(s1.items()) +
                    ",hasNext=" + s1.hasNext());

            long totalPages =
                    p0.total() / p0.size() +
                    (p0.total() % p0.size() == 0 ? 0 : 1);
            System.out.println("totalPages=" + totalPages);
        }
    }
}
```

**Technical highlights:**

- `JdbcTemplate.query(...)` accepts parameters in exact order `tenantId, status, size, offset`, matching the `?` placeholders in `PAGE_SQL`.
- `fetchPage` runs two SQL statements: items and count. `COUNT_SQL` keeps the same `tenant_id/status` filter without `ORDER BY` or `LIMIT/OFFSET`.
- `fetchSlice` runs a single query requesting `size + 1` rows, then returns at most `size` rows to the client.
- `validate` rejects `size=0`, oversized pages, and negative pages; `(long) page * size` prevents `int` multiplication overflow.
- Rows ID 13 and 14 share `created_at`, as do 11 and 12. The secondary key `id DESC` determines exact order.
- `DriverManagerDataSource` fits demos, not production connection pooling. `DB_CLOSE_DELAY=-1` keeps in-memory H2 alive across connection closes in the same JVM.

### 8.4. Run Command and Stdout

From the directory containing `build.gradle`:

```bash
gradle run
```

If a Gradle Wrapper exists, use `./gradlew run` (Linux/macOS) or `gradlew.bat run` (Windows). Gradle prints its own build logs. **Lines printed by the Java program** are:

```text
page0=[15, 14, 13],total=6
page1=[12, 11, 18],total=6
page2=[],total=6
slice0=[15, 14, 13],hasNext=true
slice1=[12, 11, 18],hasNext=false
totalPages=2
```

Result explanation:

1. There are 8 rows total in the table, but `tenant_id=7 AND status='OPEN'` selects only **6 rows**: 11, 12, 13, 14, 15, 18. ID 16 is excluded (CLOSED); ID 17 is excluded (tenant 8).
2. Sorted newest first, then descending by ID: `15, 14, 13, 12, 11, 18`.
3. Page 0, size 3, offset 0 returns `[15,14,13]`; page 1, offset 3 returns `[12,11,18]`.
4. Page 2, offset 6 returns empty, while total **remains 6**. `COUNT(*)` cannot be derived from the last page's `items.size()`.
5. Slice 0 requests up to 4 rows, sees the 4th row so `hasNext=true` while displaying 3. Slice 1 retrieves only the remaining 3 rows, so `hasNext=false`.
6. `totalPages = 6 / 3 = 2` non-empty pages, numbered 0 and 1.

This is not a multi-query transactional consistency demo: the two statements in `fetchPage` run sequentially and sample data does not mutate between them, so output is deterministic.

## 9. Packaging into a Spring Application Repository/API

### 9.1. Where Logic Should Live

A sensible separation of responsibilities:

```text
HTTP controller
  -> validate/canonicalize page, size, sort
  -> application service
     -> TaskRepository
        -> JdbcTemplate.query(...) for items
        -> JdbcTemplate.queryForObject(...) for COUNT if needed
     -> return TaskPage / TaskSlice
  -> JSON response
```

Do not build `LIMIT/OFFSET` SQL inside the controller. The repository knows columns/tables/queries; the service knows business policies; the controller knows HTTP and input parameter binding.

A Page-style response can look like:

```json
{
  "items": [
    {"id": 15, "title": "E"},
    {"id": 14, "title": "D"},
    {"id": 13, "title": "C"}
  ],
  "page": 0,
  "size": 3,
  "totalElements": 6,
  "totalPages": 2
}
```

A Slice-style response can look like:

```json
{
  "items": [
    {"id": 15, "title": "E"},
    {"id": 14, "title": "D"},
    {"id": 13, "title": "C"}
  ],
  "page": 0,
  "size": 3,
  "hasNext": true
}
```

These are **sample JSON contracts**, not output generated automatically by the Java demo program. Do not expose `totalElements=6` in a Slice without actually counting. If the API needs a count only on the first page, document that contract explicitly rather than changing response shapes silently between requests.

### 9.2. What Must the API Contract Clarify?

- Whether pages start at **0 or 1**.
- Default size and maximum size.
- Allowed sorts and tie-breaker keys used to stabilize ordering.
- Whether `totalElements`/`totalPages` are returned or only `hasNext`.
- Behavior when a page exceeds the end of the result set: empty list or another convention.
- Tenant/user and time-range filter criteria applied consistently.
- Accuracy/point-in-time semantics of totals under concurrent updates.
- For cursors, token expiration and which filter/sort it is bound to.

In multi-tenant systems, **never** trust a client-supplied `tenantId` without verifying the user is authorized to access that tenant. Both the list SQL and count SQL must enforce equivalent authorization scopes.

### 9.3. A Repository Supporting Client-Chosen Sorting

When letting clients pick `newest` or `oldest`, use the allowlist from section 2.4 and either use fixed SQL statements per sort or insert an allowlisted `ORDER BY` fragment. Bind only `tenantId`, `status`, `size`, and `offset` as data values. Never construct an `ORDER BY` clause from unvalidated request strings.

As filters grow from two conditions to many optional criteria, keep filter logic synchronized between the items and count queries. You can extract shared filter construction into a controlled SQL builder or use named parameters, and test the resulting SQL across filter combinations.

## 10. Edge Cases and Bugs to Test

| Scenario | Expected / what to check |
| --- | --- |
| `page=0, size=3` | Offset 0, returns up to first 3 rows in order |
| `page=1, size=3` | Offset 3, returns up to next 3 rows |
| Filter matches nothing | Empty items; Page has count = 0; Slice has `hasNext=false` |
| Page beyond end | Empty items; Page may still have `total > 0` |
| `size=0`, negative, or over limit | Validation error before calling JDBC |
| `page < 0` | Validation error |
| Two rows with identical timestamps | Unique tie-breaker guarantees explicit order |
| Sort field not in allowlist | Reject input, never concatenate arbitrary SQL |
| Row inserted/deleted between two requests | OFFSET may duplicate/skip rows; evaluate cursor or snapshot |
| Total query forgets tenant/filter | Wrong count and possible info leak; test list/count same scope |
| JOIN creates duplicates | Entity count must consider `DISTINCT`/`EXISTS`/unique-id paging |
| Very large `OFFSET` | Can be slow; inspect query plan and consider keyset |
| Data changes between two SQL statements in one page | `items` and `total` may reflect different snapshots |

### 10.1. Useful Test Cases

1. Seed fewer rows than one page; assert `items.size()`, `total`, and `hasNext`.
2. Seed exact full page; Slice must report no next page.
3. Seed one more row than page size; Slice must report `hasNext=true`.
4. Seed pairs of rows with identical `created_at`; verify `id` ordering and no lost rows across page boundaries.
5. Query `page=2` when only 2 pages exist; verify empty items yet non-zero total.
6. Concatenate IDs across all pages and compare against an unpaginated query over **a fixed dataset**; verify no duplicates and no omissions.
7. Seed rows in another tenant and another status; verify count excludes out-of-scope rows.
8. Test unsupported sort values, oversized `size`, negative `page`, and huge `page`.
9. For real systems running PostgreSQL/MySQL, run integration tests on that DBMS; H2 does not emulate every difference in NULL sorting, execution plans, or drivers.

## 11. Misconceptions to Avoid

**"LIMIT/OFFSET alone is proper pagination."** Wrong: explicit `ORDER BY` is mandatory; without sorting, pages have no stable meaning.

**"ORDER BY created_at gives deterministic order."** Not guaranteed: multiple rows can share the same timestamp. Add a unique tie-breaker key.

**"COUNT(*) is always free."** Wrong: counting can be expensive, especially with complex filters and large tables. Run it only when the contract requires it.

**"total = items.size()."** Wrong: that is only the current page's row count, not the total across all matching records.

**"An empty page proves the database has no data."** Wrong: an offset beyond the end also yields an empty page.

**"A ? placeholder can dynamically supply the ORDER BY column name from user input."** Wrong: placeholders bind data values, not SQL identifiers/keywords. Use an allowlist.

**"Adding a secondary PK to ORDER BY prevents duplicates across requests."** Wrong: data mutations shift offsets; keyset or snapshots may fit better.

**"A single transaction always makes page and count see the same snapshot."** False across all DBMSs and isolation levels; verify specific snapshot guarantees.

**"An index completely eliminates the cost of OFFSET 1,000,000."** Wrong: the database may still walk many index entries to skip the offset; keyset is an alternative when suitable.

## 12. Self-Check Questions

1. With `page=4`, `size=25`, and 0-based pages, what is the offset? What if pages are 1-based?
2. Why might `ORDER BY created_at DESC` be insufficient? Add an appropriate tie-breaker key.
3. If `query` returns 0 rows on page 5, why must you not conclude `totalElements=0`?
4. A screen has a "Show more" button without page numbers. Do you need `COUNT(*)`?
5. If `size=20`, how many rows should Slice request at most to compute `hasNext`?
6. Why must the count query and item query share identical tenant and status filters?
7. With a one-to-many tags JOIN, when do `COUNT(*)` and `COUNT(DISTINCT t.id)` differ?
8. When a new row is inserted at the top of the list between two requests, what bug can offset pagination cause?
9. With `ORDER BY created_at DESC, id DESC` and cursor `(T, 42)`, what timestamp/id condition must subsequent rows satisfy?
10. Can `request.sort` be interpolated directly into SQL? What is the safer approach?

**Key takeaway:** Proper JDBC pagination = **correct filters + explicit ORDER BY with a unique tie-breaker + validated LIMIT/OFFSET**. Fetch **COUNT(*)** only when total counts are required; if you only need "is there a next page?", fetch **size + 1**. For large or fast-changing datasets, consider **keyset pagination** and explicit result-consistency policies.

### Further Reading

- Spring Framework: [JDBC core — JdbcTemplate](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html).
- Spring Framework: [JdbcTemplate Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html).
- PostgreSQL: [LIMIT and OFFSET](https://www.postgresql.org/docs/current/queries-limit.html).
- PostgreSQL: [Indexes and ORDER BY](https://www.postgresql.org/docs/current/indexes-ordering.html).
- PostgreSQL: [Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html).
