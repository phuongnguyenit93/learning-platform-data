# Keyset Pagination and Deterministic Ordering Conditions

> **Topic:** Database Engine Relational Oracle  
> **Chapter:** Advanced Queries  
> **Objective:** Design keyset pagination (seek pagination) in Oracle; establish deterministic result ordering using unique keys; write next-page predicates for single or multiple sort columns; select suitable indexes; create secure cursor tokens; handle data changes between requests; and distinguish efficient pagination from requirements to read against a consistent snapshot.

## 1. Why Is Keyset Pagination Needed?

An admin screen needs to display a list of orders, 25 rows at a time. The familiar pagination approach is OFFSET:

~~~sql
SELECT order_id, created_at, customer_id, total_amount
FROM orders
WHERE status = :p_status
ORDER BY created_at DESC
OFFSET 10000 ROWS
FETCH NEXT 25 ROWS ONLY;
~~~

The statement instructs Oracle to skip the first 10,000 rows in order and return the next 25 rows. When the offset is large, the database often has to process many rows before reaching the target range. Efficiency depends on the execution plan and indexes, yet large OFFSETs are generally unsuitable for very long lists or users frequently paging deep.

Data can also change between two requests. If new rows are inserted or old rows are deleted before the offset position, rows on subsequent pages can shift. Users may see a duplicate row or miss a row.

**Keyset pagination** fetches the next page based on the values of the last row returned on the previous page. Rather than asking to "skip 10,000 rows", the application asks to "fetch rows after this last key in the exact sort order". This approach is also called **seek pagination** because the database can seek from the key in an appropriate index instead of scanning past the entire offset.

For example, if the order is **created_at DESC, order_id DESC**, the previous page's cursor might be **created_at = 2026-11-14 09:40:00** and **order_id = 850**. The next page retrieves rows following that key pair in the same order.

## 2. Prerequisite: ORDER BY Must Establish a Unique Total Order

### 2.1. A single non-unique column is not stable enough

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
ORDER BY created_at DESC;
~~~

Oracle sorts by timestamp descending, but does not define the relative order among rows sharing the same timestamp. Across two executions, the order of tied rows can vary due to execution plans, indexes, parallelism, or data changes.

If a page ends in the middle of a group of rows sharing the same timestamp, a cursor containing only CREATED_AT cannot pinpoint the next row accurately. Output can skip or duplicate rows.

### 2.2. Adding a unique key as a tie-breaker

If ORDER_ID is the primary key, use:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
ORDER BY created_at DESC, order_id DESC;
~~~

The order is defined by the pair: CREATED_AT descending; when timestamps tie, ORDER_ID descending. Because ORDER_ID is unique, no two rows share the exact same full sort key.

> **The columns in ORDER BY must form a total order over the result set.** Typically use business sort columns followed by the primary key or a unique key as the final tie-breaker.

### 2.3. Prefer stable sort keys

A column may change while a user pages through results, such as UPDATED_AT, STATUS, or PRIORITY. If that value changes, a row can move from after the cursor to before the cursor or vice versa.

To minimize this risk, pick sort keys that rarely change or are immutable by business rules, such as CREATED_AT and the primary key. If sorting by a mutable column is required, clarify whether the system accepts rows shifting between requests or requires reading against a fixed snapshot.

## 3. The First Page

Suppose the table is:

~~~sql
CREATE TABLE lab_orders (
    order_id NUMBER PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    status VARCHAR2(20 CHAR) NOT NULL,
    created_at TIMESTAMP(6) WITH TIME ZONE NOT NULL,
    total_amount NUMBER(14,2) NOT NULL
);
~~~

On Oracle Database 12c and later:

~~~sql
SELECT order_id,
       customer_id,
       status,
       created_at,
       total_amount
FROM lab_orders
WHERE status = :p_status
ORDER BY created_at DESC, order_id DESC
FETCH FIRST :p_page_size ROWS ONLY;
~~~

`:p_status` and `:p_page_size` are bind variables. Bind the proper data types and enforce a server-side page size cap (e.g., 1–100) so clients cannot request an arbitrary volume of rows. The first page has no cursor yet, so no continuation key predicate is needed.

### 3.1. Knowing whether a next page exists

A practical technique is asking the database to return `page_size + 1` rows:

~~~sql
SELECT order_id,
       customer_id,
       status,
       created_at,
       total_amount
FROM lab_orders
WHERE status = :p_status
ORDER BY created_at DESC, order_id DESC
FETCH FIRST :p_fetch_size ROWS ONLY;
~~~

The application binds `p_fetch_size = page_size + 1`. If it receives at most `page_size` rows, there is no next page at query time. If it receives `page_size + 1` rows, at least one more row exists. Return only the first `page_size` rows to the user.

Build the cursor from **the last row actually returned**, never from the extra `(page_size + 1)`-th lookahead row. If you build the cursor from the extra row, the next request starts after that row and skips the unshown lookahead row itself.

## 4. Next Page with Two DESC Keys

Suppose the previous page ended at:

~~~text
created_at = 2026-11-14 09:40:00.000000 +00:00
order_id   = 850
~~~

The sort order is:

~~~sql
ORDER BY created_at DESC, order_id DESC
~~~

To fetch rows after the last row on that page, either the timestamp must be smaller than the cursor timestamp, or the timestamp is equal and `order_id` is smaller than the cursor ID.

~~~sql
SELECT order_id,
       customer_id,
       status,
       created_at,
       total_amount
FROM lab_orders
WHERE status = :p_status
  AND (
        created_at < :p_last_created_at
        OR (
            created_at = :p_last_created_at
            AND order_id < :p_last_order_id
        )
      )
ORDER BY created_at DESC, order_id DESC
FETCH FIRST :p_page_size ROWS ONLY;
~~~

This is an explicit lexicographic comparison written for the key pair.

### 4.1. Illustrating the page boundary

~~~text
created_at             order_id
---------------------  --------
10:00:00               900
09:59:00               898
09:59:00               897
09:45:00               870
09:40:00               850  <-- end of previous page
09:40:00               849
09:39:00               848
09:38:00               840
~~~

The next page must start with `09:40 | 849`. The condition `created_at < 09:40` alone would skip this row because it shares the cursor's timestamp. The second branch handles the tied-timestamp group.

Writing only `created_at < :p_last_created_at` drops remaining rows sharing the page-end timestamp. Writing only `order_id < :p_last_order_id` could return rows with newer timestamps but smaller IDs, breaking the overall sort order. You must express the full ordering across every key in ORDER BY.

## 5. Keyset for ASC Ordering

If the ordering is:

~~~sql
ORDER BY created_at ASC, order_id ASC
~~~

then rows after the cursor have larger keys:

~~~sql
SELECT order_id,
       customer_id,
       created_at,
       total_amount
FROM lab_orders
WHERE status = :p_status
  AND (
        created_at > :p_last_created_at
        OR (
            created_at = :p_last_created_at
            AND order_id > :p_last_order_id
        )
      )
ORDER BY created_at ASC, order_id ASC
FETCH FIRST :p_page_size ROWS ONLY;
~~~

| Sort direction | Next-row comparison |
|---|---|
| ASC | Subsequent key is greater than cursor |
| DESC | Subsequent key is less than cursor |

With multiple columns, apply the comparison direction per key level. Do not flip all comparison signs in the same direction if ORDER BY mixes directions.

## 6. Multiple Sort Columns and Mixed Directions

Suppose a screen prioritizes tasks as:

~~~sql
ORDER BY priority DESC,
         created_at ASC,
         order_id ASC
~~~

Higher priority comes first; for the same priority, earlier creation time comes first; if both match, smaller order ID comes first.

The cursor stores three values from the end of the page: `last_priority`, `last_created_at`, and `last_order_id`.

~~~sql
SELECT order_id, priority, created_at
FROM lab_tasks
WHERE
       priority < :p_last_priority
    OR (
           priority = :p_last_priority
       AND created_at > :p_last_created_at
    )
    OR (
           priority = :p_last_priority
       AND created_at = :p_last_created_at
       AND order_id > :p_last_order_id
    )
ORDER BY priority DESC,
         created_at ASC,
         order_id ASC
FETCH FIRST :p_page_size ROWS ONLY;
~~~

Smaller priority follows in DESC order. When priority ties, larger `created_at` follows in ASC order. When both tie, larger `order_id` follows in ASC order.

For a general ordering:

~~~sql
ORDER BY k1 DESC, k2 ASC, k3 DESC, id ASC
~~~

the continuation predicate takes the form:

~~~sql
WHERE
       k1 < :last_k1
    OR (k1 = :last_k1 AND k2 > :last_k2)
    OR (k1 = :last_k1 AND k2 = :last_k2
                         AND k3 < :last_k3)
    OR (k1 = :last_k1 AND k2 = :last_k2
                         AND k3 = :last_k3
                         AND id > :last_id)
~~~

For each key, the next key is evaluated only when all preceding keys are equal. The final key should make the tuple unique. When using expressions or varied data types, document the cursor contract covering ordering, comparison semantics, and data types.

## 7. NULLs and Sort Ordering

Comparing against NULL does not yield ordinary TRUE/FALSE, but UNKNOWN. Therefore, keyset pagination on nullable columns requires explicit NULLS FIRST/NULLS LAST handling.

### 7.1. Prefer NOT NULL keys

When business rules allow, declare cursor columns NOT NULL:

~~~sql
created_at TIMESTAMP(6) WITH TIME ZONE NOT NULL,
order_id NUMBER PRIMARY KEY
~~~

This is the simplest way to write predicates.

### 7.2. If columns are nullable, include a null-rank in the ordering

For example, placing NULLs last when sorting priority ascending:

~~~sql
ORDER BY
    CASE WHEN priority IS NULL THEN 1 ELSE 0 END ASC,
    priority ASC,
    order_id ASC
~~~

The ordering has three keys: null rank (0 for non-NULL values, 1 for NULL); priority ascending within the non-NULL group; order ID ascending as tie-breaker.

The cursor must store null rank, priority (when non-NULL), and order ID. When both cursor and candidate row fall in the NULL group, skip comparing priority and compare order_id.

~~~sql
WHERE null_rank > :p_last_null_rank
   OR (
        null_rank = :p_last_null_rank
        AND (
             (
                 :p_last_null_rank = 0
                 AND (
                      priority > :p_last_priority
                      OR (
                          priority = :p_last_priority
                          AND order_id > :p_last_order_id
                      )
                 )
             )
             OR (
                 :p_last_null_rank = 1
                 AND order_id > :p_last_order_id
             )
        )
   )
~~~

In an actual query, `NULL_RANK` can be the repeated CASE expression or named in a CTE/inline view. ORDER BY and the predicate must use the exact same expression.

Do not use arbitrary sentinel values like `NVL(priority, -999999)` unless the data domain guarantees that value can never occur legitimately. If a sentinel collides with real data, keys collapse and the predicate breaks.

## 8. Indexes Supporting Keyset Pagination

For a query filtering status, then sorting by timestamp and ID:

~~~sql
WHERE status = :p_status
  AND (
       created_at < :p_last_created_at
       OR (
           created_at = :p_last_created_at
           AND order_id < :p_last_order_id
       )
  )
ORDER BY created_at DESC, order_id DESC
FETCH FIRST :p_page_size ROWS ONLY
~~~

A candidate index:

~~~sql
CREATE INDEX ix_lab_orders_page
ON lab_orders (
    status,
    created_at DESC,
    order_id DESC
);
~~~

STATUS is filtered by equality, so it precedes the sort keys. If a tenant filter is also present, evaluate an index like:

~~~sql
CREATE INDEX ix_lab_orders_tenant_page
ON lab_orders (
    tenant_id,
    status,
    created_at DESC,
    order_id DESC
);
~~~

This is only a candidate index. Actual design depends on predicates, selectivity, sort directions, returned columns, table size, write frequency, and other queries.

### 8.1. Tie-breaker inside the index

If ORDER BY is `CREATED_AT DESC, ORDER_ID DESC`, an index on only status and created_at may not fully represent the sort order when many rows share the same timestamp. Adding `order_id` lets the index carry the complete ordering.

Oracle can scan a B-tree in reverse in certain situations; you do not always need both ASC and DESC indexes. With mixed sort directions, check each column's direction and the execution plan.

### 8.2. Do not mechanically include every SELECT column in the index

Wide indexes can avoid table access in some queries but consume storage and increase INSERT/UPDATE/DELETE cost, redo/undo, and maintenance overhead. Create covering indexes only when workload and benchmarks demonstrate a net benefit.

## 9. Inspecting the Execution Plan

Keyset can reduce work compared to large OFFSETs, yet it does not guarantee Oracle will always choose an index seek or always run faster.

~~~sql
EXPLAIN PLAN FOR
SELECT order_id,
       created_at,
       customer_id,
       total_amount
FROM lab_orders
WHERE status = 'OPEN'
  AND (
       created_at < TIMESTAMP '2026-11-14 09:40:00'
       OR (
           created_at = TIMESTAMP '2026-11-14 09:40:00'
           AND order_id < 850
       )
  )
ORDER BY created_at DESC, order_id DESC
FETCH FIRST 25 ROWS ONLY;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

When privileged and executed with runtime statistics enabled, inspect the cursor plan:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE +ALIAS'
    )
);
~~~

Pay attention to index range scans, access/filter predicates, STOPKEY/row-limiting operations, E-Rows vs. A-Rows, buffers, physical reads, elapsed time, and large sorts. EXPLAIN PLAN is an estimated plan; DISPLAY_CURSOR with actual statistics lets you observe actual execution once statistics are gathered.

## 10. OFFSET vs. Keyset: Choosing Based on Requirements

| Criterion | OFFSET/FETCH | Keyset/seek |
|---|---|---|
| Determining a page | Skip N rows then fetch next | Find rows after the previous page's last key |
| First page | Simple | Simple |
| Deep pagination | May process many skipped rows | Can seek from an index by cursor |
| Jump directly to page 500 | More convenient | Unnatural without a cursor |
| Deterministic order | Still requires unique ORDER BY | Strictly requires unique order |
| Inserts/deletes before page position | Can shift offset positions | Less prone to shifting from inserts/deletes before cursor |
| Sort key updated | Can duplicate/drop rows | Can still duplicate/drop rows if key moves |
| Client-side cursor | Not needed | Must store last-page keys |
| Best fit | Small tables, arbitrary page numbers | Feeds, next/previous APIs, large lists |

If users must jump directly to page 120, OFFSET is easier to express. If the UI mainly navigates sequentially or scrolls continuously, keyset is usually worth considering.

## 11. Data Changing Between Page Requests

Keyset solves locating the next position by key, but does not automatically create a consistent snapshot across multiple requests.

### 11.1. New rows added before the cursor

In DESC order, suppose the cursor is at 09:40. Later a new order at 10:05 is inserted. The next-page condition requires keys smaller than the cursor, so order 10:05 sits ahead of the cursor and does not appear on the next page. Users can refresh the top of the list to see new orders.

### 11.2. New rows added after the cursor

If a new row is inserted with a timestamp older than the cursor (for example, backdated imported data), it may appear on a subsequent page even though it did not exist when the first page was opened.

### 11.3. Deleted rows

Deleting a row already displayed on an earlier page generally does not shift subsequent rows the way OFFSET does. An unread row that gets deleted simply will not appear on the next page.

### 11.4. Updated sort keys

If a row changes CREATED_AT or PRIORITY between requests, it can cross the cursor boundary. A previously shown row may move below the cursor and reappear; an unseen row may move above the cursor and be skipped; filter-column changes can cause rows to enter or leave the result set.

Use immutable keys whenever possible. If sorting by mutable columns and strict consistency is required, use an explicit snapshot or versioning mechanism.

## 12. Consistent Snapshots with SCN

If multiple pages must reflect the exact same point-in-time data state, you can capture the SCN when starting the browsing session and use Flashback Query `AS OF SCN` where supported.

Retrieve the SCN:

~~~sql
SELECT DBMS_FLASHBACK.GET_SYSTEM_CHANGE_NUMBER AS snapshot_scn
FROM dual;
~~~

Use the same SCN on every request:

~~~sql
SELECT order_id,
       created_at,
       customer_id,
       total_amount
FROM lab_orders AS OF SCN :p_snapshot_scn
WHERE status = :p_status
  AND (
       created_at < :p_last_created_at
       OR (
           created_at = :p_last_created_at
           AND order_id < :p_last_order_id
       )
  )
ORDER BY created_at DESC, order_id DESC
FETCH FIRST :p_page_size ROWS ONLY;
~~~

The first page must also use the same SCN, just without the cursor predicate. If joining multiple tables, apply the same SCN to all tables that must be read consistently.

Flashback Query requires UNDO data to remain available throughout the read window; privileges and database configuration may require DBA setup. Long-running browsing sessions may hit errors when UNDO is no longer retained, such as ORA-01555 in related scenarios. SCN snapshots are not free; weigh session duration, request rate, and operational overhead. Not all tables/objects or query types support Flashback identically.

When strict snapshots are unnecessary, keyset with immutable keys is usually simpler.

## 13. Cursor Tokens for APIs

An API can package the last-page keys into an opaque cursor token. Illustrative internal payload:

~~~json
{
  "version": 1,
  "sort": "createdAt_desc_orderId_desc",
  "lastCreatedAt": "2026-11-14T09:40:00.123456Z",
  "lastOrderId": 850,
  "pageSize": 25,
  "filterHash": "...",
  "snapshotScn": null
}
~~~

The server serializes and signs the token with HMAC or encrypts it per policy. The client merely sends the token back without modifying values.

Fields to bind into the token: token version; sort definition and per-column direction; exact values of all sort keys; relevant filters/scope (tenant, status, date range) or their fingerprint; page size if fixed by the API; snapshot SCN if using Flashback; expiration timestamp if cursors have a TTL.

The token must never allow a client to swap tenants or filters to bypass permissions. Even with a signed token, the server must re-verify authorization on every request.

### 13.1. Preserving precision and data types

If a column is TIMESTAMP(6), the cursor must retain all six fractional-second digits. Rounding timestamps can cause boundary predicates to skip or duplicate rows.

For NUMBER, avoid converting large IDs into JavaScript Numbers if they risk exceeding safe integer precision; use numeric strings or lossless formats. For TSTZ, preserve the instant and explicit timezone conventions.

Never embed arbitrary SQL inside a token. The server maps sort modes via an allowlist and binds all values. A cursor token also does not replace authentication or authorization.

## 14. Java/JDBC: Binding Cursor Values with Proper Types

Next-page example with `CREATED_AT TIMESTAMP WITH TIME ZONE` and `ORDER_ID NUMBER`:

~~~java
String sql = """
    SELECT order_id, customer_id, created_at, total_amount
    FROM lab_orders
    WHERE status = ?
      AND (
            created_at < ?
            OR (created_at = ? AND order_id < ?)
          )
    ORDER BY created_at DESC, order_id DESC
    FETCH FIRST ? ROWS ONLY
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, status);
    // Example where driver supports OffsetDateTime/JDBC 4.2 for TSTZ.
    ps.setObject(2, lastCreatedAt);
    ps.setObject(3, lastCreatedAt);
    ps.setLong(4, lastOrderId);
    ps.setInt(5, pageSize);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Map each row into response.
        }
    }
}
~~~

Both timestamp placeholders receive the same cursor value and column-compatible data type. The Oracle JDBC driver must support OffsetDateTime mapping for the actual column type; check your driver version. If using TIMESTAMP without time zone, the contract must specify the time zone/instant convention clearly. Page size must be validated server-side before binding. The first-page query has no cursor predicate; avoid unnecessary ORs that hinder optimization.

Never concatenate cursor values into SQL strings. Cursors are input data; proper typed binding prevents quoting bugs, NLS issues, precision loss, and SQL injection.

## 15. Fetching the Previous Page

Keyset naturally supports moving forward. To fetch the previous page, take the cursor at **the start of the current page** and reverse the search direction.

Standard display order:

~~~sql
ORDER BY created_at DESC, order_id DESC
~~~

To find rows preceding the first row of the current page, compare for larger keys and reverse the query order:

~~~sql
SELECT order_id,
       created_at,
       customer_id,
       total_amount
FROM lab_orders
WHERE status = :p_status
  AND (
       created_at > :p_first_created_at
       OR (
           created_at = :p_first_created_at
           AND order_id > :p_first_order_id
       )
  )
ORDER BY created_at ASC, order_id ASC
FETCH FIRST :p_page_size ROWS ONLY;
~~~

The query retrieves rows closest to the boundary in reverse ASC order. The application reverses the received rows before displaying them in DESC order.

For example, the display order is 100, 99, 98, 97, 96, 95. The current page starts at 96. The previous-page query fetches 97, 98, 99 in ASC order; the application reverses them to 99, 98, 97 for DESC display. Test first/last pages, tied key groups, and the case where no previous page exists.

## 16. Sorting by Expressions or User-Selected Columns

If ORDER BY is `CUSTOMER_NAME ASC, CUSTOMER_ID ASC`, the cursor stores both values. Next predicate:

~~~sql
WHERE customer_name > :p_last_customer_name
   OR (
       customer_name = :p_last_customer_name
       AND customer_id > :p_last_customer_id
   )
~~~

Pay attention to collation, case-insensitive sorting, and accent sensitivity. If ORDER BY uses `LOWER(customer_name)`, the predicate must use the same expression or normalized value; indexes should align (e.g., a function-based index).

With CASE:

~~~sql
ORDER BY
    CASE WHEN priority = 'URGENT' THEN 0
         WHEN priority = 'NORMAL' THEN 1
         ELSE 2
    END,
    created_at DESC,
    order_id DESC
~~~

The cursor must include the CASE rank, timestamp, and ID. The predicate must compare all three keys accordingly. If the expression is used frequently, consider a virtual column or function-based index.

If an API supports multiple sort modes (newest, highest amount, or customer name), each mode needs a fixed ORDER BY from an allowlist, a complete and unique set of cursor keys, a seek predicate matching each column's direction, suitable candidate indexes, and an explicit token version/sort mode. Do not share a single generic cursor predicate across all sort modes.

## 17. FETCH FIRST and Oracle 11g

### 17.1. Oracle 12c and later

~~~sql
SELECT ...
FROM ...
WHERE ...
ORDER BY ...
FETCH FIRST :p_page_size ROWS ONLY;
~~~

You can use FETCH NEXT in equivalent contexts. Check the specific release to confirm rowcount bind support in the syntax you use.

### 17.2. Oracle 11g with ROWNUM

If the system does not support FETCH FIRST, use an inline view with ORDER BY and cap rows in the outer query block:

~~~sql
SELECT *
FROM (
    SELECT order_id,
           customer_id,
           created_at,
           total_amount
    FROM lab_orders
    WHERE status = :p_status
      AND (
           created_at < :p_last_created_at
           OR (
               created_at = :p_last_created_at
               AND order_id < :p_last_order_id
           )
      )
    ORDER BY created_at DESC, order_id DESC
)
WHERE ROWNUM <= :p_page_size;
~~~

ROWNUM is applied in the outer query block after the inline view establishes order. Placing ROWNUM in the same query block before sorting grabs an arbitrary set of rows and sorts only those, rather than the top N rows in the intended order.

Once you use a cursor predicate to seek the next slice of the order, you normally do not need OFFSET. Adding a large OFFSET still forces the database to discard rows and forfeits the seek advantage.

## 18. Do You Need a Total Result Count?

A UI might want to show "1–25 of 82,341 orders". Knowing the exact total requires a COUNT over the same filter set:

~~~sql
SELECT COUNT(*) AS total_rows
FROM lab_orders
WHERE status = :p_status;
~~~

COUNT can be expensive on large datasets, complex filters, or JOINs. Keyset does not need total page count to fetch the next page. You can omit the total and indicate only "has next page" using `page_size + 1`; run COUNT separately only when needed; or display an estimate/cached count if business rules allow and the UI clearly labels it as approximate. Use the same snapshot SCN for COUNT and page data if point-in-time consistency is required.

## 19. Common Pitfalls

| Mistake | Consequence | Fix |
|---|---|---|
| ORDER BY on a non-unique column | Relative order among tied rows is undefined | Add PK/unique key as tie-breaker |
| Cursor keeps only the first column | Drops rows tied on boundary values | Store all sort keys |
| DESC sort using `>` for next page | Fetches rows before the cursor | For DESC, use `<` per key |
| ASC sort using `<` | Fetches the wrong side | For ASC, use `>` |
| Mixed sort directions flipped uniformly | Predicate disagrees with ORDER BY | Write each lexicographic branch per column direction |
| Nullable sort key without NULL handling | Comparisons become UNKNOWN, dropping rows | Use NOT NULL or null-rank with matching predicate |
| Timestamp rounded in cursor | Duplicates/skips rows near boundary | Preserve full precision and data type |
| No unique tie-breaker | Multiple rows share the full cursor key | Append PK/unique key at the end |
| Sort key changes between requests | Rows can cross the cursor boundary | Use immutable keys or snapshots |
| Filters change across pages | Pages no longer come from the same set | Bind filter contract into cursor |
| Client tampers with token | Alters query position or scope | Sign tokens, validate, and re-authorize |
| Very large OFFSET | Forces processing many skipped rows | Use keyset for sequential navigation |
| Assuming keyset creates a snapshot | Inserts/updates can still appear | Use AS OF SCN if strict snapshot is needed |
| Overly wide indexes | Increases write cost and storage | Design for workload and check plans |
| Building cursor from lookahead row | Skips the unreturned lookahead row on next page | Build cursor from the last actually returned row |

## 20. Hands-On Lab on a Practice Schema

The examples create tables only in an authorized lab schema.

### 20.1. Create table and sample data

~~~sql
CREATE TABLE lab_page_orders (
    order_id NUMBER PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    status VARCHAR2(20 CHAR) NOT NULL,
    created_at TIMESTAMP(6) WITH TIME ZONE NOT NULL,
    total_amount NUMBER(14,2) NOT NULL
);

INSERT INTO lab_page_orders VALUES (
    101, 10, 'OPEN',
    TIMESTAMP '2026-11-14 10:00:00 +00:00', 100
);
INSERT INTO lab_page_orders VALUES (
    102, 11, 'OPEN',
    TIMESTAMP '2026-11-14 09:59:00 +00:00', 200
);
INSERT INTO lab_page_orders VALUES (
    103, 12, 'OPEN',
    TIMESTAMP '2026-11-14 09:59:00 +00:00', 300
);
INSERT INTO lab_page_orders VALUES (
    104, 13, 'OPEN',
    TIMESTAMP '2026-11-14 09:58:00 +00:00', 400
);
INSERT INTO lab_page_orders VALUES (
    105, 14, 'OPEN',
    TIMESTAMP '2026-11-14 09:57:00 +00:00', 500
);
COMMIT;
~~~

### 20.2. Create index

~~~sql
CREATE INDEX ix_lab_page_orders
ON lab_page_orders (
    status,
    created_at DESC,
    order_id DESC
);
~~~

### 20.3. First page (page size = 2)

~~~sql
SELECT order_id, created_at, total_amount
FROM lab_page_orders
WHERE status = 'OPEN'
ORDER BY created_at DESC, order_id DESC
FETCH FIRST 2 ROWS ONLY;
~~~

Output:

~~~text
101 | 10:00:00
103 | 09:59:00
~~~

Orders 102 and 103 share the same timestamp; `order_id DESC` places 103 ahead of 102.

### 20.4. Next page

The last row of the previous page is `(09:59:00 +00:00, 103)`:

~~~sql
SELECT order_id, created_at, total_amount
FROM lab_page_orders
WHERE status = 'OPEN'
  AND (
       created_at < TIMESTAMP '2026-11-14 09:59:00 +00:00'
       OR (
           created_at = TIMESTAMP '2026-11-14 09:59:00 +00:00'
           AND order_id < 103
       )
  )
ORDER BY created_at DESC, order_id DESC
FETCH FIRST 2 ROWS ONLY;
~~~

Output:

~~~text
102 | 09:59:00
104 | 09:58:00
~~~

Order 102 has the same timestamp as the cursor but a smaller ID, so it is returned on the next page. If only `created_at < cursor` had been used, order 102 would have been missed.

### 20.5. Last page

Cursor is `(09:58:00, 104)`:

~~~sql
SELECT order_id, created_at, total_amount
FROM lab_page_orders
WHERE status = 'OPEN'
  AND (
       created_at < TIMESTAMP '2026-11-14 09:58:00 +00:00'
       OR (
           created_at = TIMESTAMP '2026-11-14 09:58:00 +00:00'
           AND order_id < 104
       )
  )
ORDER BY created_at DESC, order_id DESC
FETCH FIRST 2 ROWS ONLY;
~~~

The remaining output is order 105.

### 20.6. Comparing with OFFSET

~~~sql
SELECT order_id, created_at, total_amount
FROM lab_page_orders
WHERE status = 'OPEN'
ORDER BY created_at DESC, order_id DESC
OFFSET 2 ROWS FETCH NEXT 2 ROWS ONLY;
~~~

With unchanged data, the logical result matches the second page. However, keyset locates the next page by cursor without needing `OFFSET 2`. On large datasets, the difference in work becomes far more pronounced.

### 20.7. Testing new data between requests

1. Fetch the first page and retain the ending cursor.
2. Insert a new order with a `created_at` newer than the cursor.
3. Run the next-page query with the old cursor.
4. Observe that the new order sits ahead of the cursor and does not appear on the next page.
5. Refresh the first page to see the new order.

Next, insert an order with a `created_at` older than the cursor. That row can appear on the next page. This illustrates that keyset does not automatically create a snapshot.

### 20.8. Clean up lab table

~~~sql
DROP TABLE lab_page_orders PURGE;
~~~

Drop only lab objects you created yourself.

## 21. API Pagination Design Workflow

An API can expose two request forms:

~~~http
GET /api/orders?status=OPEN&pageSize=25
GET /api/orders?cursor=<opaque-token>
~~~

Server workflow:

1. Authenticate user and tenant.
2. If no cursor is provided, run the first-page query.
3. If a cursor is provided, verify signature, version, expiration, and sort/filter contract.
4. Map sort mode via an allowlist.
5. Bind cursor keys with exact data types.
6. Fetch `page_size + 1` rows to detect whether a next page exists.
7. Return `page_size` rows and build `nextCursor` from the last actually returned row.
8. Re-apply mandatory authorization and filters.
9. Omit `nextCursor` if no further page exists.

Illustrative response:

~~~json
{
  "items": [
    {
      "orderId": 103,
      "createdAt": "2026-11-14T09:59:00Z",
      "totalAmount": 300
    }
  ],
  "hasNextPage": true,
  "nextCursor": "<opaque-token>"
}
~~~

Returning `totalCount` is optional. If the UI needs a total count, handle it with a separate COUNT query and clarify whether it shares the same snapshot as the page data.

## 22. Pre-Production Checklist

- [ ] ORDER BY has a unique tie-breaker at the end.
- [ ] Cursor contains all sort key values of the last row on the page.
- [ ] Next-page predicate reflects each column's ASC/DESC order accurately.
- [ ] Nullable sort keys handle NULLS FIRST/LAST consistently.
- [ ] Cursor data types and precision preserve database values intact.
- [ ] Filters, tenant scope, and sort mode remain consistent across pages.
- [ ] Cursor tokens are signed/verified and versioned.
- [ ] Server validates page size and authorization on every request.
- [ ] Indexes are designed for filter + sort and execution plans have been inspected.
- [ ] Using `page_size + 1` when checking for next page without running COUNT.
- [ ] Cursor is built from the last row actually returned, not the lookahead row.
- [ ] If sort keys are mutable, snapshot/consistency policy is defined.
- [ ] If consistent snapshots are needed, AS OF SCN and UNDO retention have been evaluated.
- [ ] Tested tied timestamps, ID tie-breakers, first/last pages, and inserts/deletes/updates between requests.
- [ ] Benchmarked against OFFSET on datasets of representative size and distribution.

## 23. Key Takeaways

- **Keyset pagination** retrieves the next page using the keys of the previous page's last row, not by counting rows to skip.
- **ORDER BY must uniquely determine order**; add the primary key or a unique key as a tie-breaker.
- Cursors must hold **every sort key**, with matching data types, precision, and sort direction.
- For DESC, subsequent rows have smaller keys; for ASC, subsequent rows have larger keys. For mixed directions, compare each tier in its own direction.
- **NULLs require explicit rules**; NOT NULL keys keep predicates simpler.
- Indexes typically start with equality filters, followed by sort keys and tie-breakers; verify with the execution plan.
- Keyset can avoid the overhead of skipping large offsets, though it does not guarantee the optimizer always chooses an index seek.
- Keyset avoids page drift from inserts/deletes before the cursor, but **does not automatically create a snapshot**.
- If sort keys change, rows can still cross boundaries and be duplicated or skipped.
- Use `AS OF SCN` when business rules require reading pages on the same snapshot and the environment satisfies Flashback/UNDO requirements.
- Cursor tokens must be validated, bound to the filter/sort contract, and never replace authorization.
- If jumping directly to arbitrary page numbers is required, OFFSET may fit better; for sequential traversal over large lists, keyset is generally worth considering.

### Oracle Documentation to Consult

- [Oracle Database SQL Language Reference](https://docs.oracle.com/en/database/) — SELECT, row_limiting_clause, ORDER BY, ROWNUM, and Flashback Query.
- [Oracle Database SQL Tuning Guide](https://docs.oracle.com/en/database/) — access paths, index range scans, stopkey, and query optimization.
- [Oracle Database Performance Tuning Guide](https://docs.oracle.com/en/database/) — execution plans, runtime statistics, and DBMS_XPLAN.
- [Oracle Database Concepts](https://docs.oracle.com/en/database/) — B-tree indexes, consistency, and multiversion read consistency.
- [Oracle Database Application Developer's Guide - Fundamentals](https://docs.oracle.com/en/database/) — bind variables, SQL execution, and application design.

Verify `FETCH FIRST` syntax, row-limit binds, Flashback Query, and optimizer behavior against your exact Oracle release and JDBC driver. Confirm correctness first via unique ordering and boundary-case tests, then measure performance on representative workloads.
