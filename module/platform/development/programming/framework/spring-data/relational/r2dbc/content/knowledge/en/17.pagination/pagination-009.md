# Handling Data Changes While Users Browse Multiple Pages

Pagination is typically implemented by splitting a result set into fixed-size pages. However, data in the database can change while a user reads page 1, moves to page 2, and continues to page 3. Another user may insert a new record, delete a displayed record, or update a field used for sorting. When that happens, the result set of the later query no longer matches the result set of the earlier query.

If the application only uses `LIMIT` and `OFFSET`, these mutations can cause a record to appear twice, be skipped, or cause the total page count to shift mid-session. This is not necessarily an R2DBC bug; it is the consequence of executing multiple independent queries against a mutating dataset.

In Spring Data Relational R2DBC, you must choose a pagination strategy and data-consistency contract aligned with business needs. Common options include offset pagination, keyset/cursor pagination, bounding by a data watermark, snapshots, or data versioning. The UI also needs a policy for how to react when the current page has changed.

This lesson explains the anomalies that occur during multi-page browsing, how to reduce duplicates and skips with deterministic ordering, how to implement queries with SQL/`DatabaseClient`, the limitations of transactions held across multiple requests, and how to design the user experience when new data appears.

## 1. Why Do Data Changes Make Pagination Unstable?

Suppose an order list is sorted newest first, with 10 rows per page:

~~~sql
SELECT id, order_number, created_at
FROM purchase_order
ORDER BY created_at DESC, id DESC
LIMIT 10 OFFSET 0;
~~~

A user opens the first page and receives orders ranked 100 down to 91. Before they open the next page, a new order is inserted at the top of the list. When querying page 2 with `OFFSET 10`, every subsequent row shifts down by one position. Row 91 can reappear on page 2 even though it was already shown on page 1.

Conversely, if a row from the previous page is deleted, subsequent rows shift up by one position. The next page query still skips the original number of rows via `OFFSET`, so a row can be skipped.

There are three main categories of changes:

- **Insert:** a new record is added ahead of or inside the region being paginated.
- **Delete:** a deleted record shifts subsequent rows upward in position.
- **Update:** a record changes a filter field or sort field, causing it to enter or leave the result set, or move to a different position in the order.

Common anomalies:

| Change Between Two Requests | Potential Consequence with OFFSET |
|---|---|
| Inserting a row before the next page's position | Old rows can repeat on a subsequent page |
| Deleting a row from an earlier page | Unread rows can be skipped |
| Updating a sort key value | Rows can jump across page boundaries |
| Updating a filter field | Rows can appear in or vanish from the result set |
| Multiple concurrent mutations | Page count, total rows, and page contents fall out of sync |

The core issue is that each pagination request typically runs a fresh query against the database state at the time of that query.

## 2. OFFSET Pagination and Examples of Duplication or Skipping

Offset pagination selects a slice within an ordered result:

~~~sql
SELECT id, order_number, created_at
FROM purchase_order
WHERE status = 'OPEN'
ORDER BY created_at DESC, id DESC
LIMIT :pageSize OFFSET :offset;
~~~

With `pageSize = 10`:

- Page 0 has `offset = 0`.
- Page 1 has `offset = 10`.
- Page 2 has `offset = 20`.

### 2.1. Inserts Causing Duplicate Records

Initial state:

~~~text
Order before insert:
[100, 99, 98, 97, 96, 95, 94, 93, 92, 91, 90, 89, ...]

Page 1 (OFFSET 0):
[100, 99, 98, 97, 96, 95, 94, 93, 92, 91]
~~~

A new order `101` is inserted at the top of the list:

~~~text
Order after insert:
[101, 100, 99, 98, 97, 96, 95, 94, 93, 92, 91, 90, ...]

Page 2 (OFFSET 10):
[91, 90, 89, 88, 87, 86, 85, 84, 83, 82]
~~~

`91` appears on both pages. The user sees a duplicate order even though every query executed strictly according to `LIMIT/OFFSET`.

### 2.2. Deletes Causing Skipped Records

Page 1 returned rows `100` down to `91`. Then row `100` is deleted:

~~~text
Order after delete:
[99, 98, 97, 96, 95, 94, 93, 92, 91, 90, 89, ...]

Page 2 (OFFSET 10):
[89, 88, 87, 86, 85, 84, 83, 82, 81, 80]
~~~

Row `90` was not on page 1, yet shifted from position 10 to position 9 after the deletion. The page 2 query starts at position 10 and skips `90`.

This is why offset pagination suits infrequently changing lists or contexts where slight drift is acceptable, but does not provide a consistent traversal when data mutates continuously.

## 3. Always Use a Stable and Unique Order

A paginated query must have `ORDER BY`. Without ordering, the database does not guarantee requests return rows in the same sequence.

Even with `ORDER BY created_at DESC`, multiple rows can share the same timestamp. Order among rows with identical timestamps remains undefined. Add a unique key as a secondary criterion:

~~~sql
ORDER BY created_at DESC, id DESC
~~~

Here:

- `created_at` determines the business order.
- `id` breaks ties when multiple rows share the same timestamp.

A stable order must satisfy:

1. Every row in the result set has a deterministic position.
2. If the primary sort field can repeat, a secondary criterion is present.
3. The final criterion should be a unique key.
4. Sort directions remain consistent across pages.
5. Sort key values should rarely change during browsing.

Stable ordering does not prevent inserts or deletes from shifting offsets on its own. It eliminates nondeterminism caused by tied values or missing `ORDER BY`, and is a prerequisite for keyset pagination to work properly.

Avoid sorting with `ORDER BY` on a field that mutates constantly unless business logic demands that order. If a list is meant to be chronological by creation, `created_at` is generally far better than fields like `status`, `priority`, or `last_modified_at`, which can change while users browse.

## 4. What Is Keyset Pagination?

Keyset pagination (also called seek pagination) uses values from the last row of the current page as a bookmark to query the next page. Instead of asking the database to skip the first N rows, the query asks for rows appearing after the read bookmark in sort order.

With descending order on `created_at` and `id`:

~~~sql
SELECT id, order_number, created_at
FROM purchase_order
WHERE status = :status
  AND (
       created_at < :lastCreatedAt
       OR (created_at = :lastCreatedAt AND id < :lastId)
  )
ORDER BY created_at DESC, id DESC
LIMIT :pageSize;
~~~

The first page has no cursor:

~~~sql
SELECT id, order_number, created_at
FROM purchase_order
WHERE status = :status
ORDER BY created_at DESC, id DESC
LIMIT :pageSize;
~~~

The application stores the value pair of the last row, such as `lastCreatedAt` and `lastId`. When the user requests the next page, the application passes those two values into the query.

### 4.1. Illustrating the Cursor Flow

~~~text
First query
       |
       v
[100, 99, 98, 97, 96]
       |
       v
Cursor = sort keys of row 96
       |
       v
Next query:
fetch rows after cursor 96
       |
       v
[95, 94, 93, 92, 91]
       |
       v
New cursor = sort keys of row 91
~~~

If a new row `101` is inserted at the top of the list after the first page, the next query still looks for rows smaller than cursor `96`. The new row falls ahead of the cursor and does not push unread rows to different positions like OFFSET does.

### 4.2. Cursors Must Hold All Sort Keys

If ordering is:

~~~sql
ORDER BY created_at DESC, id DESC
~~~

the cursor must keep both `created_at` and `id`. Keeping only the timestamp is insufficient because multiple rows can share the same timestamp; the next query can duplicate or skip rows sharing that timestamp.

With multi-column ordering, the cursor must carry all values needed to pinpoint the last position. If nullable columns or mixed sort directions are involved, comparison predicates must accurately reflect database semantics.

### 4.3. Keyset Does Not Automatically Create a Snapshot

Keyset pagination prevents inserts ahead of the cursor from shifting unread row positions. However, it does not freeze the entire dataset.

If an unread row's sort key is updated to move ahead of the cursor, that row may not appear on subsequent pages. If an already-read row's sort key is updated to move past the cursor, it can reappear. If filter fields change, rows can enter or leave the result set.

Therefore, keyset pagination is especially effective when ordering relies on immutable or nearly immutable columns, such as monotonically increasing keys or unmodified creation timestamps.

## 5. How to Implement Keyset in Spring Data R2DBC

Queries can be declared via `@Query` or executed with `DatabaseClient`. Example repository methods for the first page and next page:

~~~java
public interface OrderRepository
        extends ReactiveCrudRepository<Order, Long> {

    @Query("""
        SELECT id, order_number, created_at, status
        FROM purchase_order
        WHERE status = :status
        ORDER BY created_at DESC, id DESC
        LIMIT :limit
        """)
    Flux<Order> findFirstSlice(
            OrderStatus status,
            int limit);

    @Query("""
        SELECT id, order_number, created_at, status
        FROM purchase_order
        WHERE status = :status
          AND (
              created_at < :lastCreatedAt
              OR (created_at = :lastCreatedAt AND id < :lastId)
          )
        ORDER BY created_at DESC, id DESC
        LIMIT :limit
        """)
    Flux<Order> findNextSlice(
            OrderStatus status,
            LocalDateTime lastCreatedAt,
            Long lastId,
            int limit);
}
~~~

This is an illustrative pattern; named-parameter binding syntax and limit support depend on the Spring Data version, driver, and dialect. If method parameters are not bound by name in your project configuration, use `@Param` to specify names explicitly.

The service can fetch one extra row to determine whether a next page exists:

~~~java
Mono<OrderSlice> nextOrders(
        OrderStatus status,
        OrderCursor cursor,
        int pageSize) {

    Flux<Order> query = cursor == null
            ? orderRepository.findFirstSlice(status, pageSize + 1)
            : orderRepository.findNextSlice(
                    status,
                    cursor.createdAt(),
                    cursor.id(),
                    pageSize + 1);

    return query.collectList()
            .map(rows -> {
                boolean hasNext = rows.size() > pageSize;

                List<Order> content = hasNext
                        ? rows.subList(0, pageSize)
                        : rows;

                OrderCursor nextCursor = content.isEmpty()
                        ? null
                        : OrderCursor.from(
                                content.get(content.size() - 1));

                return new OrderSlice(content, nextCursor, hasNext);
            });
}
~~~

`OrderSlice` and `OrderCursor` are application-defined DTOs. Example records:

~~~java
public record OrderCursor(
        LocalDateTime createdAt,
        Long id) {
}

public record OrderSlice(
        List<Order> content,
        OrderCursor nextCursor,
        boolean hasNext) {
}
~~~

The `pageSize + 1` technique reveals whether another row exists without running `COUNT(*)` on every request. When an extra row is present, return `pageSize` rows and set `hasNext = true`.

For very large result sets, `collectList()` can be avoided by handling the publisher in an API-appropriate way while retaining at most `pageSize + 1` elements. Regardless, the database query should still enforce the row limit directly in SQL.

## 6. Cursors Must Bind to Query Filters and Ordering

A cursor is meaningful only within the query context that produced it. If the first page was read with:

- `status = OPEN`
- `created_at DESC, id DESC`
- a specific tenant scope

then the next page must use the exact same filter, tenant, and sort order.

If a client sends an old cursor while changing filters or sorting, the cursor can point to an invalid position in the new result set. You can store the following inside the cursor:

- Sort key values of the last row.
- Filter version or identifier.
- Tenant/data-scope identifier if needed.
- Cursor format version to support API evolution.

A cursor can be encoded as an opaque string so clients do not construct sort key values manually. When a cursor is sent back by a client, validate its format, data types, and permissions. If the cursor contains sensitive info or impacts access scope, sign or encrypt it according to security requirements; never trust filters/tenants merely because they are embedded in a cursor.

Never use a cursor as an authorization mechanism. Every request must still verify that the user has permission to read the target dataset.

## 7. Handling Sort Key Updates During Browsing

Keyset works best when sort columns do not change after record creation. However, not every business domain can rely on immutable fields.

For example, a task list sorted by `priority DESC, id DESC`. Another user may raise the priority of an unread task. That task moves ahead of the cursor. When querying the next page, it may no longer be returned.

There are three ways to handle this:

1. **Choose rarely changing sort keys:** use `created_at`, a sequence, or a stable identifier where business logic allows.
2. **Accept a continuously updating list:** allow items to shift; the UI should support refreshing and surfacing changes.
3. **Require a consistent snapshot:** freeze the dataset by timestamp, version, or database snapshot if the business requires browsing a fixed set.

You cannot simultaneously guarantee immediate visibility of all new edits, fixed page positions, and zero duplicates/skips in all cases without defining consistent semantics. Pick clear product behavior.

## 8. Using a High-Water Mark to Bound the Result Set

One way to limit the impact of new inserts is capturing a high-water mark on the first query and reading only records that do not exceed it.

For example, if `id` is monotonically increasing and aligns with creation semantics, the first query fetches the maximum ID:

~~~sql
SELECT MAX(id)
FROM purchase_order
WHERE status = :status;
~~~

Suppose the mark is `1000`. All subsequent pages add the condition:

~~~sql
WHERE status = :status
  AND id <= :maxId
  AND id < :lastId
ORDER BY id DESC
LIMIT :pageSize;
~~~

New rows with IDs above the mark will not enter the browsed set. The cursor remains the last ID of the previous page.

This mark has limitations:

- Suitable only when IDs increase monotonically and are never reused.
- IDs allocated before transaction commit can create gaps or commit orders differing from ID allocation order.
- New records created with older IDs or backfilled data can still fall inside the mark.
- An ID mark does not freeze row contents if other properties are updated.
- Filter changes can still alter results if filtered fields are updated.

`created_at <= :asOf` can be used instead of ID when timestamps are server-assigned and immutable. However, transactions created before the mark that commit afterward or backfilled data can still complicate semantics. A high-water mark bounds the dataset by a chosen rule; it is not automatically a complete database snapshot.

## 9. Consistent Snapshots and Transactions

If the business requires every page to reflect the exact same data state, a snapshot concept is needed.

Some databases support transaction isolation such as `REPEATABLE READ` or snapshot isolation. Within a single transaction, multiple SELECT statements can read the same snapshot depending on the RDBMS and isolation level.

For example, a transaction could perform:

1. Read the first page.
2. Read the next page.
3. Read remaining pages.
4. Commit when finished.

However, paging in web applications usually spans multiple HTTP requests, and users may pause for minutes between clicks. Keeping a transaction open across that entire span is generally unsuitable:

- Connections stay occupied for too long.
- Old snapshots retain row versions or raise vacuum/undo pressure depending on the database.
- Transactions can time out or be interrupted.
- Lock contention increases and affects other requests.
- Difficult to recover when users close tabs or lose connectivity.

Therefore, never hold a reactive transaction open just so users can step across pages at leisure. Reactive transactions in R2DBC are meant to wrap a single short use case—such as reading/writing multiple tables in one request—not a long-lived browsing session.

If a true multi-request snapshot is required, use a dedicated mechanism supported by the database or application, such as an expiring snapshot token, a staging table holding the ID list, versioned data, or an immutable export. This is an architectural decision with storage and operational costs.

## 10. Counting Total Rows When Data Changes

Offset pagination often shows total page count by running an extra query:

~~~sql
SELECT COUNT(*)
FROM purchase_order
WHERE status = :status;
~~~

And then the page query:

~~~sql
SELECT id, order_number, created_at
FROM purchase_order
WHERE status = :status
ORDER BY created_at DESC, id DESC
LIMIT :limit OFFSET :offset;
~~~

If an insert or delete happens between the two queries, `totalElements` and page contents can reflect two different states. Even when executed back-to-back, two independent SQL statements under default isolation can observe different snapshots.

Therefore:

- Treat the total row count as informational at query time unless a consistent snapshot is enforced.
- Do not assume `totalPages` remains valid after a user pauses and navigates pages.
- If the UI does not need total pages, using `hasNext` is simpler and cheaper.
- If exact totals matching the same snapshot are required, design an appropriate transaction/snapshot and weigh its cost.

With keyset pagination, `hasNext` can be determined by fetching `pageSize + 1` rows. This avoids counting the entire result set.

## 11. Handling Changes in the User Interface

The backend can choose cursors or snapshots, yet the UI still needs a clear policy when the list mutates.

### 11.1. New Records Appear

If a user is on page 3 and new records appear at the top of the list:

- Do not automatically prepend them into the current page, as that shifts every visible row.
- Show a "New data available" banner or a "Refresh" button.
- When the user chooses to refresh, return them to the first page or issue a fresh cursor.
- If the business needs real-time updates, use a dedicated live-update mechanism and handle duplicate IDs.

### 11.2. Current Records Are Deleted

If a row on the current page is deleted:

- Render the page with fewer than the standard number of rows.
- Optionally backfill one row from the next page if UX requires keeping the count full.
- If the current page becomes empty due to deletions, navigate back to the previous page or show an empty state with a back button.
- With offset pagination, backfilling requires recalculating offsets and risks observing shifting data; avoid unbounded query loops.

### 11.3. Records Change Status or No Longer Match Filters

Suppose a user is viewing `OPEN` orders while an order transitions to `CLOSED`. When loading the next page, that record no longer belongs to the result set.

This is a valid filter change. The UI can update that row immediately upon receiving an event, or reflect the change only when the user refreshes. The API should return data matching current filters without assuming earlier lists remain intact.

### 11.4. Client-Side Deduplication

When using offset on mutating data, the UI might receive an ID already shown on an earlier page. The client can deduplicate by ID to avoid rendering two identical rows:

~~~javascript
const byId = new Map(existingItems.map(item => [item.id, item]));

for (const item of incomingPage) {
  byId.set(item.id, item);
}

const mergedItems = [...byId.values()];
~~~

Deduplication only fixes duplicate display. It does not recover records skipped due to offset shifts. If users need exhaustive traversal or accurate data exports, use keyset/snapshots rather than relying on deduplication.

## 12. API Design for Offset and Cursor

An offset API typically looks like:

~~~http
GET /orders?status=OPEN&page=2&size=20&sort=createdAt,desc
~~~

Response might include:

~~~json
{
  "content": [],
  "page": 2,
  "size": 20,
  "totalElements": 145,
  "totalPages": 8
}
~~~

Totals can shift as data is inserted or deleted. Clients should treat them as a snapshot from when the response was generated.

A cursor API typically looks like:

~~~http
GET /orders?status=OPEN&limit=20
GET /orders?status=OPEN&limit=20&after=eyJjcmVhdGVkQXQiOi...
~~~

Response:

~~~json
{
  "content": [],
  "nextCursor": "eyJjcmVhdGVkQXQiOi...",
  "hasNext": true
}
~~~

Cursors should be server-generated opaque tokens. Clients simply send the token back on the next request without modifying embedded sort key values.

If filters or sorting change, the server should reject incompatible cursors or require starting a new pagination sequence. A cursor version field can handle format evolution over time.

## 13. Building Safe Queries with DatabaseClient

`DatabaseClient` lets you bind values such as filters, cursors, and limits:

~~~java
Flux<Order> findAfter(
        OrderStatus status,
        LocalDateTime lastCreatedAt,
        Long lastId,
        int pageSize) {

    return databaseClient.sql("""
            SELECT id, order_number, created_at, status
            FROM purchase_order
            WHERE status = :status
              AND (
                  created_at < :lastCreatedAt
                  OR (
                      created_at = :lastCreatedAt
                      AND id < :lastId
                  )
              )
            ORDER BY created_at DESC, id DESC
            LIMIT :pageSize
            """)
            .bind("status", status.name())
            .bind("lastCreatedAt", lastCreatedAt)
            .bind("lastId", lastId)
            .bind("pageSize", pageSize)
            .map((row, metadata) -> new Order(
                    row.get("id", Long.class),
                    row.get("order_number", String.class),
                    row.get("created_at", LocalDateTime.class),
                    row.get("status", String.class)))
            .all();
}
~~~

The pattern above assumes `created_at` is non-null and Java types match the driver. If columns are nullable, specify null ordering explicitly and write the matching cursor predicate. If the dialect does not support binding limit this way, use the limit mechanism supported by your driver/database.

Column names and `ASC`/`DESC` keywords cannot be bound as parameter values. If clients can select sort orders, map choices against a server-side allowlist of columns and directions. Never concatenate client-supplied sort strings directly into SQL.

## 14. Indexes and Performance of Paginated Queries

Large offsets can be costly because the database must find and skip many rows before returning the requested slice. For instance, `OFFSET 100000` can scan across a large result region.

Keyset can usually leverage indexes over filters and sort keys. For the query:

~~~sql
WHERE status = :status
  AND (
      created_at < :lastCreatedAt
      OR (created_at = :lastCreatedAt AND id < :lastId)
  )
ORDER BY created_at DESC, id DESC
LIMIT :pageSize;
~~~

An index to consider:

~~~sql
CREATE INDEX ix_order_status_created_id
ON purchase_order(status, created_at DESC, id DESC);
~~~

Actual indexes depend on the database, selectivity, filter predicates, sort directions, and workload. Do not create indexes merely because `ORDER BY` exists; inspect execution plans and benchmark on production-like data.

If filters vary frequently, a single index may not cover every combination. Prioritize the most critical queries and avoid adding excessive indexes that slow down inserts and updates.

## 15. Choosing a Strategy Based on Business Requirements

| Need | Suitable Strategy | Trade-off |
|---|---|---|
| Small lists, rarely changing | Offset pagination | Easy to use, clear total pages; can still drift if data mutates |
| Pages must jump to any number | Offset pagination | Large offsets can be slow and contents can shift |
| Large data, continuous inserts | Keyset/cursor | More stable forward progression; hard to jump to arbitrary page numbers |
| Ordering on immutable columns | Keyset/cursor | Reduces duplicates/skips from inserts ahead of cursor |
| Constantly changing sort keys | Snapshots or accepting refresh | Keyset can still be affected by moving rows |
| Reports/exports needing a fixed dataset | Snapshots, versions, or staging | Consumes extra resources and requires snapshot lifecycle management |
| UI needs to know if more data exists | `pageSize + 1` and `hasNext` | Does not provide exact total page counts |
| UI must show total page counts | Count query | Totals can change between requests |

No single strategy fits every screen. Determine whether users need to jump to arbitrary pages, browse continuously, or export a fixed dataset.

## 16. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Paginating with OFFSET without ORDER BY | Results across requests are unstable | Add deterministic ordering |
| ORDER BY solely on a repeatable timestamp | Rows with equal timestamps can swap relative positions | Add a unique key as tie-breaker |
| Thinking ORDER BY prevents all drift on inserts/deletes | Offsets still shift when preceding row counts change | Use keyset or snapshots as needed |
| Cursor contains only part of the sort key | Can duplicate or skip rows sharing sort keys | Store all sort keys, including the unique tie-breaker |
| Using keyset with frequently mutated sort keys | Rows can move across the cursor | Choose immutable keys or define update semantics |
| Counting total and fetching page assuming identical state | `totalElements` may mismatch page content | Treat count as point-in-time info or use a snapshot |
| Holding a transaction open while users browse for minutes | Ties up connections and retains snapshots long | Keep each request's transaction short; use dedicated snapshots if mandatory |
| Using `created_at <= asOf` and assuming an absolute snapshot | Backfills or late-committing transactions can still appear | Recognize watermark limits or use true versions/snapshots |
| Deduplicating in the UI and assuming no data was lost | Skipped records are never recovered | Pick proper pagination; deduplication is display-only |
| Prepending new items into the current page | Visible rows shift and cursor/offset go out of sync | Notify of new data and refresh intentionally |
| Concatenating sort strings directly into SQL | SQL injection risk and invalid queries | Whitelist sort columns and directions |
| Using very large OFFSET on huge tables | Queries become expensive | Consider keyset and appropriate indexes |

## 17. Workflow for Designing a Consistent Pagination Experience

When building screens where multiple users may update data concurrently, decide:

1. Do users need to jump to arbitrary page numbers, or only move forward/backward?
2. Are records frequently inserted, deleted, or modified in sort keys?
3. Does ordering have a unique, stable secondary criterion?
4. Can sort keys be edited after creation?
5. Should users see new data immediately, or browse a consistent dataset?
6. Is an exact total page count mandatory, or is `hasNext` sufficient?
7. When changes happen, will the UI auto-refresh, show a banner, or accept live updates?
8. Is the cursor bound to current filters, sort, and tenant?
9. Do queries have appropriate indexes and row limits enforced in the database?
10. Do integration tests simulate inserts, deletes, and updates between page fetches?

A useful test scenario:

- Fetch the first page with a small page size.
- Insert a new row whose sort key precedes the first page.
- Fetch the next page and verify keyset does not re-emit the previous page's last row.
- Delete an already-read row and check next-page behavior.
- Update an unread row's sort key to verify the chosen semantics.
- Change filters or sort while sending an old cursor and verify the server rejects or handles it properly.
- Verify the final page with no remaining rows and `hasNext = false`.

## 18. Takeaways

- Data changing between requests can cause offset pagination to duplicate or skip records.
- Always include a deterministic `ORDER BY` and append a unique key as a tie-breaker.
- Keyset/cursor pagination uses the last row's sort keys to query what follows, avoiding shifts from inserts ahead of the cursor.
- Cursors must hold all sort keys and bind to the corresponding filters, sort order, and access scope.
- Keyset is not a snapshot; updates to sort keys or filters can still move rows into or out of the traversed range.
- A high-water mark can bound new records by a specific rule, but does not guarantee an absolute snapshot.
- Never keep reactive transactions open across a user's multi-page browsing session.
- Count queries and page queries can observe different data states; treat totals as point-in-time figures without a snapshot.
- UIs should have explicit policies for new, deleted, or status-changed records; deduplication does not recover skipped rows.
- Use `pageSize + 1` to determine `hasNext` when total row counts are unnecessary.
- Bind filter/cursor values; whitelist column names and sort directions because identifiers cannot be bound as value parameters.
- Test behavior when inserts, deletes, and updates occur between page loads against the target database.
